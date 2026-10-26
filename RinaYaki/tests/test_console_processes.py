import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch

from scripts import full_video_pipeline as pipeline
from scripts import desk_bridge, yaki_ui


@unittest.skipUnless(os.name == 'nt', 'Windows console hiding')
class ConsoleProcessTests(unittest.TestCase):
    def test_pipeline_tool_runs_without_console_window(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(pipeline.subprocess, 'run') as command:
            command.return_value = subprocess.CompletedProcess(['tool'], 0, '', '')
            pipeline.run(['tool'], log_path=Path(folder) / 'tool.log')
            self.assertEqual(command.call_args.kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)

    def test_embedded_worker_uses_windowless_python(self):
        with patch.object(desk_bridge.subprocess, 'Popen') as launch:
            desk_bridge.start_worker(Path('example-job'), 'prepare')
        self.assertEqual(Path(launch.call_args.args[0][0]).name, 'pythonw.exe')
        self.assertEqual(launch.call_args.kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)

    def test_standalone_worker_uses_windowless_python(self):
        window = SimpleNamespace(managed_job=Path('example-job'), status=Mock(),
                                 start=Mock(), next_button=Mock(), show_page=Mock(),
                                 close_web_sessions=Mock())
        with patch.object(yaki_ui, 'is_direct_project', return_value=True), \
                patch.object(yaki_ui.subprocess, 'Popen') as launch:
            yaki_ui.App.spawn_worker(window, 'prepare')
        self.assertEqual(Path(launch.call_args.args[0][0]).name, 'pythonw.exe')
        self.assertEqual(launch.call_args.kwargs['creationflags'], subprocess.CREATE_NO_WINDOW)
        window.close_web_sessions.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
