import json
import tempfile
import unittest
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from rinayaki import billing

class BillingTests(unittest.TestCase):
    def test_shared_price_examples_match(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures' / 'billing-estimates-v1.json').read_text())
        self.assertEqual((fixture['schema'], fixture['currency'], fixture['amount_unit']), (1, 'CNY', 'micro-CNY'))
        for case in fixture['cases']:
            self.assertEqual(billing.estimate(case['provider'], case['model'], case['usage']),
                             (case['expected_amount_micro'], case['expected_tokens']))

    def test_accounts_usage_and_privacy(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(billing.os.environ, {billing.APP.upper() + '_CONFIG_HOME': folder}):
            usage = {'prompt_tokens': 100, 'completion_tokens': 10, 'prompt_cache_hit_tokens': 50}
            for _ in range(2):
                billing.record('https://api.deepseek.com/v1', 'fake-private-key', 'deepseek-flash', usage, 'same-response')
            data = json.loads((Path(folder) / 'billing.json').read_text())
            self.assertEqual(data['schema'], 2)
            account = data['accounts'][billing.identity('deepseek', 'fake-private-key')]
            self.assertEqual(account['calls'], 1)
            self.assertEqual(account['amount_micro'], 182)
            self.assertNotIn('fake-private-key', json.dumps(data))
            self.assertNotIn('same-response', json.dumps(data))
            billing.record('https://api.deepseek.com', 'fake-private-key', 'unknown-model', usage)
            account = json.loads((Path(folder) / 'billing.json').read_text())['accounts'][billing.identity('deepseek', 'fake-private-key')]
            self.assertEqual(account['unknown'], 1)
    def test_day_rollover_and_corruption_preserved(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(billing.os.environ, {billing.APP.upper() + '_CONFIG_HOME': folder}):
            path = Path(folder) / 'billing.json'
            path.write_text(json.dumps({'schema': 1, 'day': '2000-01-01', 'accounts': {'old': {'calls': 100}}}))
            billing.record('https://api.deepseek.com', 'fake', 'deepseek-flash', {'prompt_tokens': 10, 'completion_tokens': 10})
            migrated = json.loads(path.read_text())
            self.assertNotIn('old', migrated['accounts'])
            self.assertEqual(migrated['history']['2000-01-01']['old']['calls'], 100)
            path.write_text('corrupt')
            billing.record('https://api.deepseek.com', 'fake', 'deepseek-flash', {})
            self.assertEqual(path.read_text(), 'corrupt')
    def test_parallel_writers_do_not_lose_updates(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(billing.os.environ, {billing.APP.upper() + '_CONFIG_HOME': folder}):
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(lambda i: billing.record('https://api.deepseek.com', 'fake', 'deepseek-flash', {'prompt_tokens': 10, 'completion_tokens': 10}, str(i)), range(12)))
            data = json.loads((Path(folder) / 'billing.json').read_text())
            self.assertEqual(next(iter(data['accounts'].values()))['calls'], 12)
    def test_exact_hosts_and_invalid_usage(self):
        self.assertIsNone(billing.provider('https://api.deepseek.com.evil.test'))
        self.assertIsNone(billing.provider('http://api.deepseek.com'))
        self.assertIsNone(billing.provider('https://user@api.deepseek.com'))
        self.assertEqual(billing.estimate('bailian', 'deepseek-v4.1-flash', {'prompt_tokens': 100, 'completion_tokens': 10, 'prompt_cache_hit_tokens': 50}), (182, 110))
        self.assertEqual(billing.estimate('bailian', 'qwen-audio-3.1-asr-flash-filetrans', {'duration': 358, 'total_tokens': 6824}), (78760, 6824))
        self.assertIsNone(billing.estimate('bailian', 'qwen-audio-3.1-asr-flash-filetrans', {'duration': True}))
        self.assertIsNone(billing.estimate('deepseek', 'deepseek-flash', {'prompt_tokens': True, 'completion_tokens': 1}))
        self.assertIsNone(billing.estimate('deepseek', 'deepseek-flash', {'prompt_tokens': 1, 'completion_tokens': 1, 'prompt_cache_hit_tokens': 2}))

    def test_project_receipts_reconcile_without_double_counting(self):
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as project, patch.dict(
            billing.os.environ, {billing.APP.upper() + '_CONFIG_HOME': folder}
        ):
            root = Path(project) / 'intermediates/work'
            (root / '03_asr').mkdir(parents=True)
            for phase in ('04_translation', '05_refinement'):
                (root / phase / 'batches').mkdir(parents=True)
            (root / '03_asr/filetrans.json').write_text(json.dumps({
                'model': 'qwen-audio-3.1-asr-flash-filetrans',
                'usage': {'duration': 358, 'total_tokens': 6824},
                'request_id': 'asr-request',
            }), encoding='utf-8')
            (root / '03_asr/filetrans.task.json').write_text(json.dumps({
                'value': {'task_id': 'asr-task'},
            }), encoding='utf-8')
            (root / '04_translation/batches/001.json').write_text(json.dumps({'result': {
                'model': 'qwen-mt-flash', 'usage': {'prompt_tokens': 316, 'completion_tokens': 169},
                'response_id': 'translation-1',
            }}), encoding='utf-8')
            (root / '05_refinement/batches/001.json').write_text(json.dumps({'result': {
                'model': 'qwen3.8-flash', 'usage': {'prompt_tokens': 763, 'completion_tokens': 398},
                'response_id': 'refinement-1',
            }}), encoding='utf-8')
            settings = SimpleNamespace(
                api_key='current-key', base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                http_api_url='https://dashscope.aliyuncs.com/api/v1',
            )
            self.assertEqual(billing.reconcile_project(project, settings), 3)
            self.assertEqual(billing.reconcile_project(project, settings), 3)
            account = json.loads((Path(folder) / 'billing.json').read_text())['accounts'][
                billing.identity('bailian', 'current-key')
            ]
            self.assertEqual((account['calls'], account['amount_micro'], account['tokens']), (3, 80996, 8470))
