"""Opt-in native GUI checks; all background operations are mocked."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import json

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import yaki_ui
from rinayaki.project_storage import write_local_json, set_control


@unittest.skipUnless(os.environ.get('RINAYAKI_TEST_GUI'),'opt-in native UI')
class ProjectUiTests(unittest.TestCase):
    def test_required_destination_resume_and_edit_without_paid_work(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'RINAYAKI_CONFIG_HOME':str(Path(directory)/'user-config')},clear=False), patch.object(yaki_ui,'RUNS',Path(directory)/'cache'), patch.object(yaki_ui,'PROJECT_INDEX',Path(directory)/'.local/projects.json'):
            root=Path(directory)
            window=tk.Tk()
            window.withdraw()
            try:
                app=yaki_ui.App(window)
                self.assertEqual(
                    [app.mode_notebook.tab(index,'text') for index in range(app.mode_notebook.index('end'))],
                    ['视频翻译','实时翻译'])
                self.assertEqual((int(app.cover_frame['width']),int(app.cover_frame['height'])),(310,175))
                self.assertEqual(app.start.pack_info()['fill'],'x')
                self.assertEqual(app.open_project_button.pack_info()['anchor'],'e')
                self.assertEqual(app.live_step,'source')
                self.assertEqual(app.live_source_page.winfo_manager(),'pack')
                app.advance_live_setup()
                self.assertEqual(app.live_step,'display')
                self.assertEqual(app.live_display_page.winfo_manager(),'pack')
                self.assertIn('保存结果',app.live_source_summary.get())
                app.show_live_step('source')
                with patch.object(window,'focus_get',return_value=app.live_session_name_entry), \
                     patch.object(app.mode_notebook,'focus_set') as release:
                    app.advance_live_setup()
                    release.assert_called_once_with()
                app.show_live_step('source')
                self.assertNotIn('自动识别',app.live_source_language_combo['values'])
                app.live_display_mode.set('只显示原文')
                app.update_live_display_mode()
                self.assertEqual(app.live_status.get(),'')
                self.assertEqual(str(app.live_target_language_combo['state']),'disabled')
                self.assertEqual(app.live_start_button['text'],'开始实时识别')
                app.live_display_mode.set('双语显示')
                app.update_live_display_mode()
                self.assertEqual(str(app.live_target_language_combo['state']),'readonly')
                self.assertEqual(app.live_start_button['text'],'开始实时翻译')
                app.selected={'kind':'web','source':'https://www.youtube.com/watch?v=kycUI2dAziw','title':'Fixture','duration':10,
                              'acquisition':{'quality':'auto','authenticated':False}}
                app.open_project_settings()
                self.assertEqual(app.project_parent.get(),'')
                self.assertEqual(app.project_name.get(),'')
                self.assertEqual(app.source_language.get(),'自动识别')
                app.source_language.set('English')
                app.target_language.set('日本語')
                with patch.object(app,'spawn_worker') as spawn:
                    app.confirm_project()
                    spawn.assert_not_called()
                    self.assertEqual(app.screen,'project')
                    app.project_parent.set(str(root))
                    app.project_name.set('第一版')
                    app.confirm_project()
                    spawn.assert_called_once_with('prepare')
                job=app.job
                self.assertEqual(job,root/'第一版')
                self.assertTrue(job.exists())
                self.assertFalse((root/'cache').exists())
                write_local_json(job/'intermediates/prepared.json',{'key':'fixture','speakers':{'0':{'start_ms':0,'length_ms':1000,'text':'hello','translation':'你好'}}})
                set_control(job,root/'cache',status='awaiting_style')
                app.poll()
                self.assertEqual(str(app.next_button['state']),'normal')
                app.open_styles()
                self.assertEqual(app.screen,'style')
                self.assertEqual(str(app.location_button['state']),'disabled')
                config=json.loads((job/'intermediates/destination.local.json').read_text(encoding='utf-8'))
                self.assertEqual(config['project_name'],'第一版')
                self.assertEqual(config['source']['source_language'],'en')
                self.assertEqual(config['source']['target_language'],'ja')
                app.open_project_settings()
                self.assertEqual(app.project_name.get(),'')
                self.assertEqual(len(app.pending_jobs),1)
                app.pending_combo.current(1)
                app.select_pending_job()
                self.assertEqual(app.project_name.get(),'第一版')
                self.assertEqual(app.source_language.get(),'English')
                self.assertEqual(app.target_language.get(),'日本語')
                self.assertEqual(str(app.source_language_combo['state']),'disabled')
                with patch.object(app,'spawn_worker') as spawn:
                    app.confirm_project()
                    spawn.assert_called_once_with('prepare')
                    self.assertEqual(app.job,job)
                final=job
                set_control(job,root/'cache',status='complete',final_dir=str(final))
                app.poll()
                self.assertEqual(app.job,final)
                self.assertEqual(str(app.next_button['state']),'disabled')
            finally:
                window.destroy()
