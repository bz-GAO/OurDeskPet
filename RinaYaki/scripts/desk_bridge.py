"""Versioned RinaDesk adapter. Translation logic stays in RinaYaki."""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from rinayaki.languages import validate_languages, validate_speaker_count
from rinayaki.live.capture import list_loopback_devices
from rinayaki.live.session import LiveSettings
from rinayaki.guidance import discover_packs, load_guidance
from rinayaki.settings import load_settings, save_settings
from rinayaki.project_storage import (create_direct_project, control_path,
    is_direct_project, lifecycle_lock, write_local_json)
from rinayaki.styling import DEFAULT_FONT, FONTS, PRESETS, validate_styles
from rinayaki.style_preview import render_live_style_preview, render_style_preview
from rinayaki.video_input import local_thumbnail, normalize_input, preview
from rinayaki.acquisition import options as acquisition_options
from rinayaki.web_session import launch_detached_session

RUNS = ROOT.parent / 'RinaYakiCache'
INDEX = ROOT / '.local/projects.json'


def bridge_description():
    """Describe the tools exposed by this one RinaYaki installation.

    RinaDesk registers the provider path once, then renders each capability as
    a separate tool. ``embedded_ready`` belongs to the individual tool so the
    live page can evolve independently from the mature video workflow.
    """
    return {
        'protocol_version': 1,
        'provider': {'id': 'rinayaki', 'name': 'RinaYaki'},
        'tools': [
            {'id': 'video', 'name': '视频翻译', 'available': True, 'embedded_ready': True},
            {'id': 'live', 'name': '实时翻译', 'available': True, 'embedded_ready': True},
        ],
    }


def image_url(raw):
    if not raw or len(raw) > 8 * 1024 * 1024:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.thumbnail((640, 360))
            output = io.BytesIO()
            image.convert('RGB').save(output, format='JPEG', quality=78, optimize=True)
        return 'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode('ascii')
    except (OSError, ValueError):
        return None


def video_preview(value):
    # Desk never reads a daily browser profile.  It reuses only the isolated,
    # Yaki-owned WebView profile after the user has explicitly logged in.
    result = preview(value, ROOT, use_app_session=True)
    # Locked choices require the native hover/dialog interaction. Keep Desk on
    # verified downloadable qualities until that UI is deliberately mirrored.
    result['qualities'] = [item for item in result.get('qualities', [])
                           if item.get('available', True)]
    result.pop('capabilities', None)
    if result['kind'] == 'local':
        raw = local_thumbnail(result['source'], result['duration'], ROOT)
    else:
        raw = None
        if result.get('thumbnail'):
            try:
                # Match the standalone UI: fetch the image in Python, not in WebView.
                with urlopen(result['thumbnail'], timeout=15) as response:
                    raw = response.read(8 * 1024 * 1024 + 1)
            except (OSError, ValueError):
                pass
    result['thumbnail'] = image_url(raw)
    result['protocol_version'] = 1
    return result


def web_session_open(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError('请输入视频链接或视频号。')
    launched = launch_detached_session(value)
    return {'opened': True, 'site': launched['site'], 'title': launched['title']}


def indexed_jobs():
    try:
        items = json.loads(INDEX.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [Path(item) for item in items if isinstance(item, str)]


def redirected(path):
    """Reject links and Windows junctions when discovering project folders."""
    return path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction())


def register_jobs(jobs):
    """Merge discovered direct projects into the private bridge index."""
    resolved = []
    seen = set()
    for item in [*indexed_jobs(), *jobs]:
        try:
            path = Path(item)
            if redirected(path):
                continue
            path = path.resolve(strict=True)
        except OSError:
            continue
        key = os.path.normcase(str(path))
        if key not in seen and is_direct_project(path):
            seen.add(key)
            resolved.append(path)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    write_local_json(INDEX, [str(path) for path in resolved])


def scan_jobs(value, source=None):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('请选择项目所在文件夹。')
    selected = Path(value).expanduser()
    if not selected.is_absolute():
        raise ValueError('项目文件夹必须使用完整路径。')
    if redirected(selected):
        raise ValueError('所选项目文件夹不能是链接或目录联接。')
    selected = selected.resolve(strict=True)
    if not selected.is_dir() or redirected(selected):
        raise ValueError('所选项目文件夹无效。')

    selected_is_project = is_direct_project(selected)
    candidates = [selected] if selected_is_project else []
    if not selected_is_project:
        for child in selected.iterdir():
            try:
                if child.is_dir() and not redirected(child) and is_direct_project(child):
                    candidates.append(child.resolve(strict=True))
            except OSError:
                continue
    register_jobs(candidates)
    jobs = []
    for candidate in candidates:
        try:
            state = job_status(candidate)
            if not source or state['source'].get('source') == source:
                jobs.append(state)
        except (OSError, ValueError, KeyError):
            continue
    jobs.sort(key=lambda item: item['projectName'].casefold())
    return {'directory': str(selected), 'canCreate': not selected_is_project, 'jobs': jobs[-100:]}


def checked_job(value):
    if not isinstance(value, str):
        raise ValueError('任务路径无效。')
    candidate = Path(value)
    if redirected(candidate):
        raise ValueError('项目文件夹不能是链接或目录联接。')
    candidate = candidate.resolve()
    if not any(not redirected(path) and candidate == path.resolve() for path in indexed_jobs()):
        raise ValueError('这个项目未由 RinaYaki 登记。')
    if not is_direct_project(candidate):
        raise ValueError('项目文件不完整。')
    return candidate


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def job_status(job):
    control = read_json(control_path(job, RUNS))
    try:
        progress = read_json(job / 'intermediates/progress.json')
    except (OSError, ValueError):
        progress = {}
    status = control.get('status', 'new')
    if status in {'running', 'new'}:
        state = {**progress, **control, 'status': status}
    else:
        state = {**progress, **control}
    result = {'job': str(job), 'projectName': control.get('project_name', job.name),
              'source': control.get('source', {}), 'state': state}
    prepared_path = job / 'intermediates/prepared.json'
    if prepared_path.is_file():
        prepared = read_json(prepared_path)
        result['prepared'] = {'key': prepared['key'], 'speakers': prepared['speakers']}
        styles_path = job / 'intermediates/styles.json'
        if styles_path.is_file():
            styles = read_json(styles_path)
            if styles.get('prepared_key') == prepared['key']:
                result['styles'] = styles.get('speakers', {})
    return result


def start_worker(job, phase):
    # The worker has no interactive output; pythonw keeps the whole job off the
    # Windows console subsystem when launched from the embedded desk UI.
    python = ROOT / '.venv/Scripts' / ('pythonw.exe' if os.name == 'nt' else 'python')
    command = [str(python), '-u', str(ROOT / 'scripts/run_ui_job.py'),
               '--project-dir', str(job), '--cache-root', str(RUNS), '--phase', phase]
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def live_options():
    """Return safe, presentation-ready choices for the embedded setup page."""
    device_error = None
    try:
        devices = list_loopback_devices()
    except Exception as error:
        devices = []
        device_error = str(error)
    packs, pack_errors = discover_packs(ROOT)
    return {
        'translationStreaming': True,
        'devices': [{'id': item['id'], 'name': item['name']} for item in devices],
        'deviceError': device_error,
        'fonts': list(dict.fromkeys(FONTS.values())),
        'colorPresets': [{'name': name, 'color': color} for name, color in PRESETS.items()],
        'guidancePacks': [{
            'id': pack.id,
            'name': pack.manifest['name'],
            'version': pack.manifest['version'],
            'sourceLanguage': pack.manifest['source_language'],
            'targetLanguage': pack.manifest['target_language'],
            'draft': pack.draft,
        } for pack in packs],
        'guidanceErrors': pack_errors,
    }


def live_style_preview(request):
    size = request.get('fontSize', 14)
    if isinstance(size, bool) or not isinstance(size, int) or not 10 <= size <= 96:
        raise ValueError('字幕字号无效。')
    mode = request.get('displayMode', 'bilingual')
    if not isinstance(mode, str) or mode not in {'source', 'translation', 'bilingual'}:
        raise ValueError('显示模式无效。')
    samples = {'ja': 'テスト', 'zh': '测试', 'zh-Hans': '测试', 'en': 'Test'}
    source_language = request.get('sourceLanguage', 'ja')
    target_language = request.get('targetLanguage', 'zh-Hans')
    if not isinstance(source_language, str) or not isinstance(target_language, str):
        raise ValueError('语言选项无效。')
    source = samples.get(source_language)
    target = samples.get(target_language)
    if not source or not target:
        raise ValueError('语言选项无效。')
    font = request.get('fontFamily', DEFAULT_FONT)
    if not isinstance(font, str) or font not in FONTS.values():
        raise ValueError('字幕字体无效。')
    image = render_live_style_preview(source, target, display_mode=mode, font_name=font,
        fonts_directory=ROOT/'assets/fonts', outline_color=request.get('subtitleColor', PRESETS['默认']),
        width=720, font_size=size)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return {'image': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')}


def style_options():
    return {'defaultFont': DEFAULT_FONT,
            'fonts': [{'label': label, 'value': value} for label, value in FONTS.items()],
            'presets': [{'label': label, 'value': value} for label, value in PRESETS.items()]}


def style_preview(request):
    text = request.get('text', '')
    font = request.get('font', DEFAULT_FONT)
    color = request.get('color', PRESETS['默认'])
    if not isinstance(text, str) or len(text) > 120:
        raise ValueError('字幕预览文本过长或无效。')
    if not isinstance(font, str) or font not in FONTS.values():
        raise ValueError('请选择受支持的字幕字体。')
    if not isinstance(color, str):
        raise ValueError('描边颜色无效。')
    # Same renderer, bundled files and dimensions as the native offline editor.
    picture = render_style_preview(text, font_name=font, fonts_directory=ROOT/'assets/fonts',
                                   outline_color=color)
    buffer = io.BytesIO()
    picture.save(buffer, format='PNG')
    return {'image': 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode('ascii')}


def start_live(request):
    """Validate live-only choices, then launch the existing independent runtime."""
    if request.get('sourceType', 'local') != 'local':
        raise ValueError('直播音频接口尚未开放，请选择本机音轨。')
    device = request.get('device') or None
    session_name = request.get('sessionName') or None
    if device is not None and (not isinstance(device, str) or len(device) > 1024):
        raise ValueError('本机播放设备无效。')
    if session_name is not None and (not isinstance(session_name, str) or len(session_name) > 120):
        raise ValueError('会话名称过长。')
    record_session = request.get('recordSession', True)
    if not isinstance(record_session, bool):
        raise ValueError('保存录音选项无效。')
    packs = request.get('guidancePacks') or []
    if not isinstance(packs, list):
        raise ValueError('术语包选项无效。')
    allow_draft = request.get('allowDraftGuidance', False)
    if not isinstance(allow_draft, bool):
        raise ValueError('草案术语包选项无效。')
    font_size = request.get('fontSize', 14)
    font_family = request.get('fontFamily', DEFAULT_FONT)
    if isinstance(font_size, bool) or not isinstance(font_size, int):
        raise ValueError('字幕字号无效。')
    if not isinstance(font_family, str):
        raise ValueError('字幕字体无效。')
    shared = load_settings(ROOT)
    live = LiveSettings(
        audio_device=device,
        source_language=request.get('sourceLanguage', 'ja'),
        target_language=request.get('targetLanguage', 'zh-Hans'),
        record_session=record_session,
        display_mode=request.get('displayMode', 'bilingual'),
        subtitle_lines=8,
        subtitle_font_family=font_family,
        subtitle_font_size=font_size,
        subtitle_color=request.get('subtitleColor', PRESETS['默认']),
        translation_engine=shared.live_engine,
        guidance_packs=tuple(packs),
        allow_draft_guidance=allow_draft,
    )
    if not shared.api_key:
        raise ValueError('未配置 DASHSCOPE_API_KEY，请先在 RinaYaki 设置中保存。')
    if live.translation_enabled and live.guidance_packs:
        if not live.uses_livetranslate and not shared.translation_model.startswith('qwen-mt-'):
            raise ValueError('术语指导目前仅支持 Qwen-MT 翻译模型。')
        load_guidance(ROOT, live.guidance_packs, live.source_language,
                      live.target_language, allow_draft=live.allow_draft_guidance)

    python = ROOT / '.venv/Scripts' / ('pythonw.exe' if os.name == 'nt' else 'python')
    if not python.is_file():
        raise ValueError('RinaYaki Python 运行时不完整。')
    command = [str(python), '-m', 'rinayaki.live', '--project-root', str(ROOT),
               '--source', live.source_language, '--target', live.target_language,
               '--translation-engine', live.translation_engine,
               '--display-mode', live.display_mode, '--font-family', live.subtitle_font_family,
               '--font-size', str(live.subtitle_font_size), '--subtitle-color', live.normalized_subtitle_color,
               '--subtitle-lines', str(live.subtitle_lines)]
    if live.audio_device:
        command.extend(['--device', live.audio_device])
    if session_name and session_name.strip():
        command.extend(['--session-name', session_name.strip()])
    if not live.record_session:
        command.append('--no-record')
    if live.translation_enabled:
        for pack_id in live.guidance_packs:
            command.extend(['--guidance-pack', pack_id])
        if live.guidance_packs and live.allow_draft_guidance:
            command.append('--allow-draft-guidance')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=flags)
    return {'launched': True, 'processId': process.pid}


def action(name, request):
    if name == 'web_session_open':
        return web_session_open(request.get('value', ''))
    if name == 'video_preview':
        result = video_preview(str(request.get('value', '')))
        result.pop('protocol_version', None)
        return result
    if name == 'settings':
        return {'settings': load_settings(ROOT).public()}
    if name == 'settings_save':
        return {'settings': save_settings(request, ROOT).public()}
    if name == 'live_options':
        return live_options()
    if name == 'live_style_preview':
        return live_style_preview(request)
    if name == 'style_options':
        return style_options()
    if name == 'style_preview':
        return style_preview(request)
    if name == 'live_start':
        return start_live(request)
    if name == 'live_guidance_open':
        if os.name != 'nt':
            raise ValueError('当前平台不支持打开文件夹。')
        folder = ROOT / 'translation_guidance'
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)
        return {'opened': True}
    if name == 'scan':
        return scan_jobs(request.get('parent'), request.get('source'))
    if name == 'jobs':
        source = request.get('source')
        jobs = []
        for job in indexed_jobs():
            try:
                if is_direct_project(job):
                    state = job_status(job)
                    if not source or state['source'].get('source') == source:
                        jobs.append(state)
            except (OSError, ValueError, KeyError):
                continue
        return {'jobs': jobs[-30:]}
    if name == 'create':
        video = request.get('video') or {}
        kind, source = normalize_input(video.get('source', ''))
        if kind != video.get('kind'):
            raise ValueError('预览信息与视频来源不一致。')
        source_language, target_language = validate_languages(request.get('sourceLanguage'), request.get('targetLanguage'))
        speaker_count = validate_speaker_count(request.get('speakerCount'))
        record = {'kind': kind, 'source': source, 'title': str(video.get('title') or source),
                  'source_language': source_language, 'target_language': target_language}
        if speaker_count is not None:
            record['speaker_count'] = speaker_count
        if kind == 'web':
            record['acquisition'] = acquisition_options(video.get('acquisition'))
        if kind == 'local':
            stat = Path(source).stat()
            record.update(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
        job = create_direct_project(request.get('parent', ''), request.get('name', ''), record, RUNS, INDEX)
        start_worker(job, 'prepare')
        return job_status(job)
    job = checked_job(request.get('job'))
    if name == 'status':
        return job_status(job)
    if name == 'retry':
        state = job_status(job)['state']
        if state.get('status') != 'failed':
            raise ValueError('只有失败的任务可以重试。')
        start_worker(job, state.get('phase') if state.get('phase') in {'prepare', 'export'} else 'prepare')
        return job_status(job)
    if name == 'export':
        state = job_status(job)
        if state['state'].get('status') != 'awaiting_style':
            raise ValueError('请等翻译完成后再导出。')
        prepared = state.get('prepared')
        if not prepared:
            raise ValueError('尚未生成说话人信息。')
        styles = validate_styles(request.get('styles'))
        if set(styles) != set(prepared['speakers']):
            raise ValueError('请设置每个说话人的字幕样式。')
        with lifecycle_lock(job, RUNS):
            write_local_json(job / 'intermediates/styles.json',
                             {'prepared_key': prepared['key'], 'speakers': styles})
        start_worker(job, 'export')
        return job_status(job)
    if name == 'sample':
        prepared = read_json(job / 'intermediates/prepared.json')
        speaker = str(request.get('speaker', ''))
        sample = prepared['speakers'].get(speaker)
        if not sample:
            raise ValueError('找不到该说话人的试听片段。')
        audio = (job / prepared['audio']).resolve()
        if not audio.is_relative_to(job.resolve()) or not audio.is_file():
            raise ValueError('试听文件路径无效。')
        command = [str(ROOT / '.tools/ffmpeg/ffmpeg.exe'), '-v', 'error',
                   '-ss', str(sample['start_ms'] / 1000), '-i', str(audio),
                   '-t', str(min(sample['length_ms'], 6000) / 1000), '-ac', '1', '-ar', '16000',
                   '-c:a', 'pcm_s16le', '-f', 'wav', 'pipe:1']
        flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
        result = subprocess.run(command, capture_output=True, timeout=30, **flags)
        if result.returncode or not result.stdout or len(result.stdout) > 1_000_000:
            raise ValueError('无法读取试听片段。')
        return {'audio': 'data:audio/wav;base64,' + base64.b64encode(result.stdout).decode('ascii')}
    if name == 'open':
        if os.name != 'nt':
            raise ValueError('当前平台不支持打开文件夹。')
        os.startfile(job)
        return {'opened': True}
    raise ValueError('Unsupported bridge request.')


def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1] == 'describe':
            result = bridge_description()
        elif len(sys.argv) == 3 and sys.argv[1] == 'preview':
            result = video_preview(sys.argv[2])
        elif len(sys.argv) == 3 and sys.argv[1] == 'action':
            message = json.loads(sys.argv[2])
            result = {'protocol_version': 2, **action(message['action'], message.get('request') or {})}
        else:
            raise ValueError('Unsupported bridge request.')
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as error:
        print(json.dumps({'error': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
