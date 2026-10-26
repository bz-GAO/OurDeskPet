from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import yaki_ui


class LiveLauncherTests(unittest.TestCase):
    def test_engine_is_explicit_without_keys_or_model_repurposing(self):
        command = yaki_ui.build_live_command('python',{
            'source_language':'ja','target_language':'zh-Hans','display_mode':'bilingual',
            'font_family':'test','subtitle_color':'#FFFFFF','translation_engine':'livetranslate',
        })
        self.assertEqual(command[command.index('--translation-engine')+1],'livetranslate')
        self.assertNotIn('--api-key',command)

    def test_source_only_launch_is_explicit_and_secret_free(self):
        command = yaki_ui.build_live_command("pythonw.exe", {
            "device": "loopback-id",
            "source_language": "ja",
            "target_language": "zh-Hans",
            "display_mode": "source",
            "font_family": "Microsoft YaHei UI",
            "font_size": 18,
            "subtitle_color": "#FFFFFF",
            "session_name": "fixture",
            "record_session": False,
        })

        self.assertEqual(command[:3], ["pythonw.exe", "-m", "rinayaki.live"])
        self.assertEqual(command[command.index("--display-mode") + 1], "source")
        self.assertEqual(command[command.index("--device") + 1], "loopback-id")
        self.assertIn("--no-record", command)
        self.assertEqual(command[command.index("--font-size") + 1], "18")
        self.assertFalse(any("key" in value.casefold() for value in command))


@unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'),'opt-in native UI')
class LiveEngineSettingsUiTests(unittest.TestCase):
    def test_settings_selector_saves_and_reopens(self):
        import tkinter as tk
        from tkinter import ttk
        from rinayaki.settings import load_settings
        with tempfile.TemporaryDirectory() as directory, \
             patch.dict(os.environ,{'RINAYAKI_CONFIG_HOME':directory}), \
             patch.object(yaki_ui,'ROOT',Path(directory)), \
             patch.object(yaki_ui,'PROJECT_INDEX',Path(directory)/'index.json'), \
             patch.object(yaki_ui,'list_loopback_devices',return_value=[]):
            window = tk.Tk()
            window.withdraw()
            try:
                app = yaki_ui.App(window)
                app.open_settings()
                self.assertEqual(app.live_engine_combo.get(),'标准（ASR＋MT）')
                self.assertEqual(str(app.live_engine_combo['state']),'readonly')
                app.live_engine_combo.set('LiveTranslate')
                dialog = next(widget for widget in window.winfo_children() if isinstance(widget,tk.Toplevel))
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)
                save = next(widget for widget in descendants(dialog)
                            if isinstance(widget,ttk.Button) and widget['text']=='保存设置')
                save.invoke()
                self.assertEqual(load_settings().live_engine,'livetranslate')
                dialog.destroy()
                app.open_settings()
                self.assertEqual(app.live_engine_combo.get(),'LiveTranslate')
            finally:
                # Tk timers otherwise outlive their Python callback commands
                # when the next GUI test creates an interpreter.
                for timer in window.tk.call('after','info'):
                    window.after_cancel(timer)
                window.destroy()


if __name__ == "__main__":
    unittest.main()
