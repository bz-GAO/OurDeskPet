import json
import tempfile
import unittest
from pathlib import Path

from rinayaki.workspace import PROJECT_DIRECTORIES, create_project, safe_project_name


class WorkspaceTests(unittest.TestCase):
    def test_creates_versioned_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project = create_project(Path(temporary_directory), "璃奈 烤肉测试")
            self.assertEqual(project.name, "璃奈 烤肉测试")
            self.assertTrue(all((project / name).is_dir() for name in PROJECT_DIRECTORIES))
            manifest = json.loads((project / "intermediates" / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["status"], "created")

    def test_rejects_empty_safe_name(self) -> None:
        with self.assertRaises(ValueError):
            safe_project_name("...  ")

    def test_rejects_windows_reserved_name(self) -> None:
        with self.assertRaises(ValueError):
            safe_project_name("CON")


if __name__ == "__main__":
    unittest.main()
