"""Language settings shared by the launcher and pipeline."""
SOURCE_LABELS = {'自动识别': 'auto', '中文': 'zh', 'English': 'en', '日本語': 'ja'}
TARGET_LABELS = {'简体中文': 'zh-Hans', 'English': 'en', '日本語': 'ja'}
NAMES = {'auto': 'auto', 'zh': 'Chinese', 'zh-Hans': 'Chinese', 'en': 'English', 'ja': 'Japanese'}
def validate_languages(source, target):
    if source not in SOURCE_LABELS.values() or target not in TARGET_LABELS.values():
        raise ValueError('不支持的语言设置。')
    return source, target
def asr_hints(source):
    validate_languages(source, 'zh-Hans')
    return () if source == 'auto' else (source,)
def stored_languages(record):
    return validate_languages(record.get('source_language', 'ja'), record.get('target_language', 'zh-Hans'))

def validate_speaker_count(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
        raise ValueError('说话人数须为 1 到 100 的整数，或选择自动识别。')
    return value

def stored_speaker_count(record):
    return validate_speaker_count(record.get('speaker_count'))
