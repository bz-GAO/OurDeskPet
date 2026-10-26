"""Daily local usage estimates. Never persist prompts, keys, media or response bodies."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import logging
import os
from pathlib import Path
import time
from urllib.parse import urlsplit

APP = {'rinayaki': 'RinaYaki', 'rinatomo': 'RinaTomo'}[__package__]
LIMIT = 256 * 1024

def provider(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'wss') or parsed.port not in (None, 443) or parsed.username or parsed.password:
        return None
    return {'api.deepseek.com': 'deepseek', 'dashscope.aliyuncs.com': 'bailian',
            'dashscope-intl.aliyuncs.com': 'bailian', 'dashscope-us.aliyuncs.com': 'bailian',
            'maas.qianwenaiapi.com': 'qianwen'}.get(parsed.hostname)

def identity(platform, key):
    return platform + ':' + hashlib.sha256((platform + '\n' + key.strip()).encode()).hexdigest()

def estimate(platform, model, usage):
    def number(*names):
        for name in names:
            value = usage.get(name)
            if type(value) is int and 0 <= value <= 10_000_000:
                return value
        return None
    if platform == 'bailian' and model == 'qwen-audio-3.1-asr-flash-filetrans':
        duration = usage.get('duration')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 0 <= duration <= 10_000_000:
            return None
        # Filetrans is billed by audio duration, not language-model tokens.
        # 0.00022 CNY/s = 220 micro-CNY/s (the same rate used by Desk's gate-2 estimate).
        amount = (Decimal(str(duration)) * Decimal('220')).to_integral_value(rounding=ROUND_CEILING)
        tokens = number('total_tokens') or 0
        return int(amount), tokens
    input_tokens = number('prompt_tokens', 'input_tokens')
    output_tokens = number('completion_tokens', 'output_tokens')
    if input_tokens is None or output_tokens is None:
        return None
    details = usage.get('prompt_tokens_details') or {}
    cached = number('prompt_cache_hit_tokens')
    if cached is None:
        cached = details.get('cached_tokens', 0) if isinstance(details, dict) else 0
    if type(cached) is not int or not 0 <= cached <= input_tokens:
        return None
    rates = None
    if platform == 'deepseek' and model in ('deepseek-flash', 'deepseek-v4-flash', 'deepseek-v4-flash-vision-exp'):
        rates = ('0.04', '2', '8')
    elif platform == 'bailian':
        rates = {'deepseek-v4.1-flash': ('0.04', '2', '8'),
                 'qwen3.8-flash': ('0.8', '0.8', '2.7'),
                 'qwen-audio-3.1-asr-flash': ('0.8', '0.8', '2.7'),
                 'qwen-audio-3.1-asr-flash-streaming': ('6', '6', '4.5'),
                 'qwen-mt-flash': ('0.7', '0.7', '1.95'),
                 'qwen-mt-plus': ('1.8', '1.8', '5.4')}.get(model)
    if rates is None:
        return None
    hit, miss, output = map(Decimal, rates)
    amount = cached * hit + (input_tokens - cached) * miss + output_tokens * output
    return int(amount.to_integral_value(rounding=ROUND_CEILING)), input_tokens + output_tokens

def _home():
    override = os.environ.get(APP.upper() + '_CONFIG_HOME', '').strip()
    if override:
        root = Path(override)
    elif os.name == 'nt':
        root = Path(os.environ['LOCALAPPDATA']) / 'OurDeskPet' / APP
    else:
        root = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / APP.lower()
    if not root.is_absolute():
        raise ValueError('usage directory must be absolute')
    return root

def _check(path):
    for candidate in (path, *path.parents):
        if candidate.exists() or candidate.is_symlink():
            info = candidate.lstat()
            if candidate.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('redirected usage path')

def _daily(ledger, day):
    """Migrate the shared ledger and retain bounded, content-free daily totals."""
    if ledger.get('schema') not in (1, 2):
        raise ValueError('usage schema unsupported')
    accounts = ledger.get('accounts')
    history = ledger.get('history', {})
    if not isinstance(accounts, dict) or not isinstance(history, dict):
        raise ValueError('usage ledger invalid')
    old_day = ledger.get('day')
    if old_day != day:
        if isinstance(old_day, str) and old_day and accounts:
            history[old_day] = {
                account_id: {name: value for name, value in counter.items() if name != 'seen'}
                for account_id, counter in accounts.items() if isinstance(counter, dict)
            }
        accounts = {}
    history.pop(day, None)
    history = {date: history[date] for date in sorted(history)[-31:] if isinstance(history[date], dict)}
    return {'schema': 2, 'day': day, 'accounts': accounts, 'history': history}

@contextmanager
def _lock(root):
    _check(root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / 'billing.lock'
    _check(lock_path)
    with lock_path.open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        deadline = time.monotonic() + 2
        while True:
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('usage writer busy')
                time.sleep(0.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)

def record(base_url, key, model, usage, response_id=None):
    """Record once per accepted response; missing/unsupported usage stays explicit."""
    try:
        platform = provider(base_url)
        if not platform or not key:
            return False
        root = _home()
        day = datetime.now().strftime('%Y-%m-%d')
        with _lock(root):
            path = root / 'billing.json'
            _check(path)
            if path.exists():
                with path.open('rb') as handle:
                    raw = handle.read(LIMIT + 1)
                if len(raw) > LIMIT:
                    raise ValueError('usage file oversized')
                ledger = json.loads(raw)
            else:
                ledger = {'schema': 2, 'day': day, 'accounts': {}, 'history': {}}
            ledger = _daily(ledger, day)
            account = ledger['accounts'].setdefault(identity(platform, key),
                {'calls': 0, 'unknown': 0, 'tokens': 0, 'amount_micro': 0, 'seen': []})
            marker = hashlib.sha256(str(response_id).encode()).hexdigest() if response_id else None
            if marker and marker in account.get('seen', []):
                return True
            if marker:
                account['seen'] = (account.get('seen', []) + [marker])[-256:]
            regional = platform != 'bailian' or urlsplit(base_url).hostname == 'dashscope.aliyuncs.com'
            result = estimate(platform, str(model), usage if isinstance(usage, dict) else {}) if regional else None
            account['calls'] += 1
            if result:
                amount, tokens = result
                account['amount_micro'] += amount
                account['tokens'] += tokens
            else:
                account['unknown'] += 1
            raw = json.dumps(ledger, separators=(',', ':')).encode()
            if len(raw) > LIMIT:
                raise ValueError('usage file oversized')
            temporary = root / ('.billing-' + str(os.getpid()) + '.tmp')
            _check(temporary)
            try:
                with temporary.open('wb') as handle:
                    handle.write(raw); handle.flush(); os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ArithmeticError, TimeoutError):
        logging.getLogger(__name__).warning('Daily usage could not be persisted; credentials were not logged.')
        return False

def reconcile_project(project_dir, settings):
    """Rebuild the central ledger from bounded, already-saved provider receipts.

    API response artifacts are the durable per-project anchor. Replaying them is
    safe because ``record`` deduplicates by provider response/task ID.
    """
    root = Path(project_dir)
    if root.name != 'intermediates':
        root = root / 'intermediates'

    def read(path):
        try:
            value = json.loads(path.read_text(encoding='utf-8'))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    reconciled = 0
    asr = read(root / 'work/03_asr/filetrans.json')
    task = read(root / 'work/03_asr/filetrans.task.json').get('value') or {}
    if asr and record(settings.http_api_url, settings.api_key, asr.get('model'),
                      asr.get('usage'), task.get('task_id') or asr.get('request_id')):
        reconciled += 1
    for folder in ('04_translation', '05_refinement'):
        directory = root / 'work' / folder / 'batches'
        try:
            paths = sorted(directory.glob('*.json'))
        except OSError:
            paths = []
        for path in paths:
            result = read(path).get('result') or {}
            if result and record(settings.base_url, settings.api_key, result.get('model'),
                                 result.get('usage'), result.get('response_id')):
                reconciled += 1
    return reconciled
