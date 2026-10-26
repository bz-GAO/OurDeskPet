"""Opt-in rendering regression tests; no audio capture or API calls."""
import os
import unittest
from unittest.mock import patch
from rinayaki.live import events as ev
from rinayaki.live.sinks.subtitle_window import SubtitleWindow


@unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'),'opt-in native UI')
class SubtitleStabilityTests(unittest.TestCase):
    def setUp(self):
        self.window = SubtitleWindow()
        self.window._root.deiconify()
        self.window._root.update()

    def tearDown(self):
        root = self.window._root
        for job in root.tk.call('after','info'):
            root.after_cancel(job)
        root.destroy()

    def expected(self):
        w = self.window
        entries = list(w._history)
        if w._partial and w._display_mode != 'translation':
            entries.append({'source':w._partial,'translation':'…'})
        rows=[]
        for entry in entries:
            if w._display_mode!='translation':
                rows.append((entry['source'],'source'))
            if w._display_mode!='source':
                rows.append((entry['translation'] or '…','translation'))
            rows.append(('', 'gap'))
        return rows

    def top_row(self):
        top=self.window._canvas.canvasy(0)-6
        height=0
        for index,step in enumerate(self.window._row_heights):
            height+=step
            if height>top:
                return self.window._rendered_rows[index]
        return None

    def test_partial_translation_modes_and_history_eviction(self):
        w = self.window
        for index in range(1005):
            w._apply(ev.final_transcript(str(index),f'字幕 {index} 😀\n次の行',0,1))
        w._redraw()
        for index in range(1005,1010):
            w._apply(ev.final_transcript(str(index),f'字幕 {index}',0,1))
            w._redraw()
            self.assertEqual(w._rendered_rows,self.expected())
        w._apply(ev.translation('1008','很长的翻译\n第二行','原文','mock',0))
        w._apply(ev.partial_transcript('未完成 😀',0,1))
        with patch.object(w._canvas,'update_idletasks',side_effect=AssertionError('nested paint')):
            w._redraw()
        self.assertEqual(w._rendered_rows,self.expected())
        for mode in ('source','translation','bilingual'):
            w._set_display_mode(mode)
            self.assertEqual(w._rendered_rows,self.expected())

    def test_same_height_tail_update_and_history_reading_do_not_jump(self):
        w = self.window
        for index in range(80):
            w._apply(ev.final_transcript(str(index),f'原文 {index}',0,1))
        w._apply(ev.partial_transcript('途中A',0,1))
        w._redraw()
        w._root.update()
        w._canvas.yview_moveto(1)
        w._root.update()
        before = self.top_row()
        w._apply(ev.partial_transcript('途中B',0,1))
        w._redraw()
        w._root.update()
        self.assertEqual(self.top_row(),before)
        w._canvas.yview_moveto(0.4)
        w._root.update()
        before_text = self.top_row()
        w._apply(ev.translation('2','早前一句的译文\n新增行','原文','mock',0))
        w._redraw()
        w._root.update()
        self.assertEqual(self.top_row(),before_text)
        with patch.object(w._status_label,'configure') as changed:
            w._redraw()
            changed.assert_not_called()

    def test_stream_revisions_and_newlines_replace_the_same_segment(self):
        w = self.window
        w._apply(ev.final_transcript('stream', '原文', 0, 1))
        for text in ('译', '译文\n第二行', '修订', '修订后的译文'):
            w._apply(ev.translation_partial('stream', text))
            w._redraw()
            w._root.update()
            self.assertEqual(w._rendered_rows, self.expected())
            self.assertEqual(len(w._history), 1)
        w._apply(ev.translation_error('stream', 'disconnected'))
        w._redraw()
        self.assertTrue(any('未完成' in text for text,_kind in w._rendered_rows))
