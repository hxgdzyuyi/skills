import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mp_article_project.py"
SPEC = importlib.util.spec_from_file_location("mp_article_project", SCRIPT)
project = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = project
SPEC.loader.exec_module(project)


class ProjectTests(unittest.TestCase):
    def test_missing_hugo_returns_two(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch.object(project, "find_hugo", return_value=None):
                self.assertEqual(
                    project.main(["doctor", "--root", directory]),
                    project.EXIT_HUGO_MISSING,
                )

    def test_empty_directory_is_initialized_through_hugo(self):
        def fake_new_site(_hugo, root):
            (root / "archetypes").mkdir()
            (root / "config.toml").write_text('title = "generated"\n', encoding="utf-8")
            return True, "created"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            success, changes = project.initialize_project(
                root, "/fake/hugo", new_site_runner=fake_new_site
            )
            self.assertTrue(success, changes)
            self.assertTrue((root / "hugo.toml").is_file())
            self.assertFalse((root / "config.toml").exists())
            self.assertEqual(project.doctor_findings(root), [])

    def test_nonempty_directory_is_updated_incrementally(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / "keep.txt"
            original.write_text("keep", encoding="utf-8")
            success, changes = project.initialize_project(root, "/fake/hugo")
            self.assertTrue(success, changes)
            self.assertEqual(original.read_text(encoding="utf-8"), "keep")

            created, article = project.create_article(root, "hello-world", "你好，世界")
            self.assertTrue(created, article)
            article_path = Path(article)
            self.assertTrue(article_path.is_file())
            self.assertTrue((article_path.parent / "assets").is_dir())
            self.assertIn('title: "你好，世界"', article_path.read_text(encoding="utf-8"))

    def test_conflict_stops_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            conflict = root / "layouts" / "wechat" / "single.html"
            conflict.parent.mkdir(parents=True)
            conflict.write_text("custom", encoding="utf-8")
            success, messages = project.initialize_project(root, "/fake/hugo")
            self.assertFalse(success)
            self.assertTrue(any("文件冲突" in message for message in messages))
            self.assertFalse((root / "hugo.toml").exists())


if __name__ == "__main__":
    unittest.main()
