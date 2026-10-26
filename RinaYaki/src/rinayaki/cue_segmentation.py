"""Build readable timed subtitle cues from ASR word timestamps."""

import unicodedata


def _units(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {'W', 'F'} else 1 for char in text)


def _word_text(word: dict) -> str:
    return str(word.get('text', '')) + str(word.get('punctuation', ''))


def _pieces(sentence: dict, *, max_duration_ms: int = 5500, max_units: int = 52) -> list[dict]:
    words = sentence.get('words') or []
    text = str(sentence['text']).strip()
    if not words or ''.join(''.join(_word_text(word) for word in words).split()) != ''.join(text.split()):
        return [{'start_ms': int(sentence['begin_time']), 'end_ms': int(sentence['end_time']), 'source_text': text}]
    try:
        valid = all(int(word['end_time']) > int(word['begin_time']) and
                    int(sentence['begin_time']) <= int(word['begin_time']) < int(word['end_time']) <= int(sentence['end_time'])
                    for word in words)
        valid = valid and all(int(left['end_time']) <= int(right['begin_time']) for left, right in zip(words, words[1:]))
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        return [{'start_ms': int(sentence['begin_time']), 'end_ms': int(sentence['end_time']), 'source_text': text}]
    result = []
    start = 0
    while start < len(words):
        end = start + 1
        content = _word_text(words[start])
        while end < len(words):
            candidate = content + _word_text(words[end])
            duration = int(words[end]['end_time']) - int(words[start]['begin_time'])
            if duration > max_duration_ms or _units(candidate) > max_units:
                break
            content = candidate
            end += 1
        if end < len(words):
            punctuated = [index + 1 for index in range(start, end)
                          if str(words[index].get('punctuation', '')).strip()
                          and int(words[index]['end_time']) - int(words[start]['begin_time']) >= 1800
                          and index + 1 - start >= (end - start) * .55]
            if punctuated:
                end = punctuated[-1]
                content = ''.join(_word_text(word) for word in words[start:end])
        result.append({'start_ms': int(words[start]['begin_time']),
                       'end_ms': int(words[end - 1]['end_time']),
                       'source_text': content.strip()})
        start = end
    return result


def source_cues_from_asr(asr: dict) -> list[dict]:
    cues = []
    for sentence in asr.get('sentences', []):
        if not sentence.get('text') or int(sentence.get('end_time', 0)) <= int(sentence.get('begin_time', 0)):
            continue
        for piece in _pieces(sentence):
            cues.append({'id': f'{len(cues) + 1:04d}', 'speaker_id': sentence.get('speaker_id'), **piece})
    if len(cues) > 9999:
        raise ValueError('视频产生超过 9999 条字幕，请分段处理。')
    return cues
