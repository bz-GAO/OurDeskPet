"""Native layout checks; no capture, network or paid API calls."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import tkinter.font as tkfont
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import yaki_ui


@unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'),'opt-in native UI')
class LiveLayoutTests(unittest.TestCase):
    def test_scaled_layout_and_preview(self):
        for scaling in (1.33,2.0,2.67):
            with self.subTest(scaling=scaling), tempfile.TemporaryDirectory() as directory, \
                 patch.dict(os.environ,{'RINAYAKI_CONFIG_HOME':directory}), \
                 patch.object(yaki_ui,'list_loopback_devices',return_value=[]):
                window = tk.Tk()
                window.tk.call('tk','scaling',scaling)
                try:
                    app = yaki_ui.App(window)
                    window.update()
                    def visible(widget):
                        self.assertTrue(widget.winfo_ismapped())
                        self.assertGreater(widget.winfo_height(),20)
                        self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                             window.winfo_rooty()+window.winfo_height())
                        self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(),
                                             window.winfo_screenheight())
                    visible(app.start)
                    app.mode_notebook.select(1)
                    window.update()
                    visible(app.live_continue_button)
                    app.advance_live_setup()
                    window.update()
                    visible(app.live_start_button)
                    if scaling == 1.33:
                        self.assertEqual(app.live_display_scroll.canvas.yview(),(0.0,1.0))
                    # At default size forms fit unless the physical screen caps the window.
                    for form in (app.video_scroll,app.live_source_scroll,app.live_display_scroll):
                        self.assertGreater(form.content.winfo_reqwidth(),100)
                    print('scaling',scaling,'window',window.geometry(),
                          'display scroll',app.live_display_scroll.canvas.yview())
                    app.live_font_size.set('18')
                    app.live_subtitle_color.set('#88CCFF')
                    app.live_font_family.set('Arial')
                    items=app.live_preview_canvas.find_all()
                    self.assertEqual(tkfont.Font(font=app.live_preview_canvas.itemcget(items[-1],'font')).actual('size'),18)
                    self.assertEqual(tkfont.Font(font=app.live_preview_canvas.itemcget(items[-1],'font')).actual('family'),'Arial')
                    self.assertEqual(app.live_preview_canvas.itemcget(items[0],'fill'),'#88CCFF')
                    self.assertEqual(app.live_preview_canvas.itemcget(items[8],'text'),'テスト')
                    self.assertEqual(app.live_preview_canvas.itemcget(items[-1],'text'),'测试')
                    app.live_display_mode.set('只显示原文')
                    app.live_source_language.set('English')
                    items=app.live_preview_canvas.find_all()
                    self.assertEqual(len(items),9)
                    self.assertEqual(app.live_preview_canvas.itemcget(items[-1],'text'),'Test')
                    self.assertEqual(tkfont.Font(font=app.live_preview_canvas.itemcget(items[-1],'font')).actual('size'),18)
                    app.live_display_mode.set('只显示译文')
                    self.assertEqual(len(app.live_preview_canvas.find_all()),9)
                    app.live_subtitle_color.set('#')  # Intermediate IME/typing edit is harmless.
                    window.geometry('780x540')
                    window.update()
                    visible(app.live_start_button)
                    canvas = app.live_display_scroll.canvas
                    canvas.yview_moveto(1)
                    window.update()
                    self.assertAlmostEqual(canvas.yview()[1],1.0,places=2)
                    app.show_live_step('source')
                    window.update()
                    visible(app.live_continue_button)
                    app.mode_notebook.select(0)
                    window.update()
                    visible(app.start)
                finally:
                    for job in window.tk.call('after','info'):
                        window.after_cancel(job)
                    window.destroy()

    def test_font_size_cli_roundtrip(self):
        path = Path(__file__).resolve().parents[1]/'src/rinayaki/live/__main__.py'
        spec = importlib.util.spec_from_file_location('rinayaki.live.layout_test_main',path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.build_parser().parse_args(['--font-size','18'])
        self.assertEqual(args.font_size,18)


if __name__ == '__main__':
    unittest.main()
