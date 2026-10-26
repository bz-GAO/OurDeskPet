import unittest

from rinayaki.cue_segmentation import source_cues_from_asr


class CueSegmentationTests(unittest.TestCase):
    def test_long_sentence_uses_word_times_without_changing_text(self):
        words = []
        for index in range(36):
            words.append({'begin_time': index * 320, 'end_time': (index + 1) * 320,
                          'text': '言葉', 'punctuation': '、' if index in {11, 23} else ''})
        sentence = {'begin_time': 0, 'end_time': len(words)*320, 'text': ''.join(w['text']+w['punctuation'] for w in words),
                    'speaker_id': 0, 'words': words}
        cues = source_cues_from_asr({'sentences':[sentence]})
        self.assertGreaterEqual(len(cues),3)
        self.assertEqual(''.join(cue['source_text'] for cue in cues),sentence['text'])
        self.assertEqual(cues[0]['start_ms'],0)
        self.assertEqual(cues[-1]['end_ms'],sentence['end_time'])
        self.assertTrue(all(cue['end_ms']-cue['start_ms']<=5500 for cue in cues))
        self.assertTrue(all(cue['speaker_id']==0 for cue in cues))

    def test_missing_or_inconsistent_words_preserve_original_sentence(self):
        sentence={'begin_time':10,'end_time':1000,'text':'こんにちは。','words':[{'begin_time':10,'end_time':1000,'text':'wrong'}]}
        cues=source_cues_from_asr({'sentences':[sentence]})
        self.assertEqual(len(cues),1)
        self.assertEqual(cues[0]['source_text'],'こんにちは。')
