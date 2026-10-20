#!/usr/bin/env python3
"""Offline tests for staged draft assembly and its output guarantees."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import assemble_thread as assembler


class AssembleThreadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.article_path = self.root / "article.json"
        self.source_path = self.root / "source.md"
        self.plan_path = self.root / "blocks.json"
        self.meta_path = self.root / "thread-meta.json"
        self.drafts = self.root / "drafts"
        self.out = self.root / "output"
        self.drafts.mkdir()
        self.source_path.write_text("# 原文标题\n\n第一主题的原文。\n第二主题的原文。\n", encoding="utf-8")
        self.article = {
            "kind": "article", "source_url": "https://example.org/article",
            "resolved_url": "https://example.org/article", "title": "原文标题", "author": None,
            "images": [{"id": "img-123", "url": "https://example.org/figure.png"}],
        }
        self.plan = {"schema_version": 1, "blocks": [
            {"id": "block-02", "title": "第一主题", "summary": "第一主题的实质摘要。",
             "source_ranges": [{"start_line": 3, "end_line": 3}], "preserve": ["关键事实"]},
            {"id": "block-01", "title": "第二主题", "summary": "第二主题的实质摘要。",
             "source_ranges": [{"start_line": 4, "end_line": 4}], "preserve": []},
        ]}
        self.meta = {"title": "中文成稿", "summary": "原文涉及两个主题。", "tags": [], "images": []}
        self.write_json(self.article_path, self.article)
        self.write_json(self.plan_path, self.plan)
        self.write_json(self.meta_path, self.meta)
        # Files are created in reverse plan order, and IDs do not sort into plan order.
        for block in reversed(self.plan["blocks"]):
            self.write_json(self.drafts / f"{block['id']}.json", {
                "id": block["id"], "title": block["title"],
                "text": f"{block['title']}的完整中文摘要。", "image_ids": [],
            })

    def write_json(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def run_cli(self, **overrides):
        paths = {"article": self.article_path, "source": self.source_path, "plan": self.plan_path,
                 "drafts": self.drafts, "meta": self.meta_path, "out": self.out}
        paths.update(overrides)
        argv = [item for name, path in paths.items() for item in (f"--{name}", str(path))]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = assembler.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_plan_order_text_only_and_inputs_remain_unchanged(self):
        inputs = [self.article_path, self.source_path, self.plan_path, self.meta_path, *self.drafts.iterdir()]
        before = {path: path.read_bytes() for path in inputs}
        code, stdout, stderr = self.run_cli()
        self.assertEqual(0, code, stderr)
        thread = json.loads((self.out / "thread.json").read_text(encoding="utf-8"))
        self.assertEqual(["block-02", "block-01"], [block["id"] for block in thread["blocks"]])
        self.assertEqual([], thread["images"])
        self.assertTrue(all(block["image_ids"] == [] for block in thread["blocks"]))
        self.assertEqual(1, thread["schema_version"])
        self.assertEqual(["thread.json"], [path.name for path in self.out.iterdir()])
        self.assertEqual(str((self.out / "thread.json").resolve()), json.loads(stdout)["output"])
        self.assertEqual(before, {path: path.read_bytes() for path in inputs})

    def test_source_image_schema_is_compatible(self):
        self.meta["images"] = [{"id": "img-123", "description": "与第一主题对应的原图"}]
        self.write_json(self.meta_path, self.meta)
        draft_path = self.drafts / "block-02.json"
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        draft["image_ids"] = ["img-123"]
        self.write_json(draft_path, draft)
        code, stdout, stderr = self.run_cli()
        self.assertEqual(0, code, stderr)
        self.assertEqual(1, json.loads(stdout)["images"])

    def test_missing_planned_draft_fails_without_output(self):
        (self.drafts / "block-01.json").unlink()
        code, _, stderr = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("missing planned draft", stderr)
        self.assertFalse(self.out.exists())

    def test_duplicate_plan_id_and_mismatched_draft_id_fail(self):
        self.plan["blocks"][1]["id"] = "block-02"
        self.write_json(self.plan_path, self.plan)
        code, _, stderr = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("duplicate planned block id", stderr)
        self.plan["blocks"][1]["id"] = "block-01"
        self.write_json(self.plan_path, self.plan)
        draft_path = self.drafts / "block-02.json"
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        draft["id"] = "block-99"
        self.write_json(draft_path, draft)
        code, _, stderr = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("does not match plan", stderr)

    def test_invalid_source_ranges_fail(self):
        invalid = [
            [], [{"start_line": 0, "end_line": 3}], [{"start_line": 4, "end_line": 3}],
            [{"start_line": 3, "end_line": 5}], [{"start_line": True, "end_line": 3}],
            [{"start_line": "3", "end_line": 3}], [{"start_line": 3, "end_line": 3, "extra": 1}],
        ]
        for ranges in invalid:
            with self.subTest(ranges=ranges):
                plan = copy.deepcopy(self.plan)
                plan["blocks"][0]["source_ranges"] = ranges
                self.write_json(self.plan_path, plan)
                code, _, _ = self.run_cli()
                self.assertEqual(2, code)
                self.assertFalse(self.out.exists())

    def test_empty_source_and_invalid_plan_fields_fail(self):
        self.source_path.write_text("", encoding="utf-8")
        code, _, stderr = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("source lines 1..0", stderr)
        for field, value in (("summary", ""), ("preserve", "关键事实"), ("preserve", [None])):
            with self.subTest(field=field, value=value):
                plan = copy.deepcopy(self.plan)
                plan["blocks"][0][field] = value
                with self.assertRaises(assembler.ValidationError):
                    assembler.validate_plan(plan, 4)

    def test_validation_failure_preserves_existing_output(self):
        self.out.mkdir()
        output_path = self.out / "thread.json"
        output_path.write_text("保留已有结果", encoding="utf-8")
        draft_path = self.drafts / "block-02.json"
        draft = json.loads(draft_path.read_text(encoding="utf-8"))
        draft["image_ids"] = ["invented-image"]
        self.write_json(draft_path, draft)
        code, _, stderr = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("undeclared image", stderr)
        self.assertEqual("保留已有结果", output_path.read_text(encoding="utf-8"))
        self.assertEqual(["thread.json"], [path.name for path in self.out.iterdir()])

    def test_output_must_not_collide_with_inputs(self):
        self.out.mkdir()
        output_path = self.out / "thread.json"
        output_path.symlink_to(self.source_path)
        original_source = self.source_path.read_bytes()
        code, _, stderr = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("must not overwrite an input", stderr)
        self.assertEqual(original_source, self.source_path.read_bytes())
        self.assertTrue(output_path.is_symlink())

    def test_link_card_cannot_assemble_multiple_blocks(self):
        self.article["kind"] = "link_card"
        self.write_json(self.article_path, self.article)
        code, _, stderr = self.run_cli()
        self.assertEqual(2, code)
        self.assertIn("exactly one block", stderr)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
