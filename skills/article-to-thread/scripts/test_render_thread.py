#!/usr/bin/env python3
"""Offline contract and rendering tests for render_thread.py."""

from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

import render_thread as renderer


def article_fixture():
    return {
        "schema_version": 1,
        "title": "Original [article]",
        "author": "A *Writer*",
        "source_url": "https://example.org/original?ref=article",
        "resolved_url": "https://example.org/read/123",
        "kind": "article",
        "images": [{"id": "img-abcdef1234567890", "url": "https://example.org/image(1).png",
                    "alt": "原始文字", "caption": "", "context": "第一段"}],
        "text": "正文仅供 Codex 总结，渲染器不做语义验证。",
    }


def thread_fixture():
    return {
        "schema_version": 1,
        "title": "中文摘要",
        "summary": "文章讨论了测试与内容抽取。",
        "tags": ["测试", "内容抽取"],
        "blocks": [{"id": "block-01", "title": "主要内容", "text": "这是完整的段落。",
                    "image_ids": ["img-abcdef1234567890"]}],
        "images": [{"id": "img-abcdef1234567890", "description": "测试 [示意图]"}],
    }


class RenderThreadTests(unittest.TestCase):
    def setUp(self):
        self.article = article_fixture()
        self.thread = thread_fixture()

    def validate(self, article=None, thread=None):
        checked_article = renderer.validate_article(self.article if article is None else article)
        checked_thread = renderer.validate_thread(self.thread if thread is None else thread, checked_article)
        return checked_article, checked_thread

    def test_source_attribution_and_parenthesized_image_url(self):
        article, thread = self.validate()
        markdown = renderer.render_thread(article, thread)
        self.assertIn("# 中文摘要\n", markdown)
        self.assertIn(r"作者：A \*Writer\*", markdown)
        self.assertIn(r"来源：[Original \[article\]](<https://example.org/original?ref=article>)", markdown)
        self.assertIn("实际页面：[查看原文](<https://example.org/read/123>)", markdown)
        self.assertIn(r"![测试 \[示意图\]](<https://example.org/image(1).png>)", markdown)
        self.assertIn("## 主要内容\n", markdown)
        self.assertTrue(markdown.endswith("标签：测试、内容抽取\n"))

    def test_no_author_and_no_redirect(self):
        self.article["author"] = None
        self.article["title"] = None
        self.article["resolved_url"] = self.article["source_url"]
        article, thread = self.validate()
        markdown = renderer.render_thread(article, thread)
        self.assertNotIn("作者：", markdown)
        self.assertNotIn("实际页面：", markdown)
        self.assertIn("来源：[原文](<https://example.org/original?ref=article>)", markdown)

    def test_images_are_optional_and_inputs_are_not_mutated(self):
        self.thread["images"] = []
        self.thread["blocks"][0]["image_ids"] = []
        article_before, thread_before = copy.deepcopy(self.article), copy.deepcopy(self.thread)
        article, thread = self.validate()
        self.assertNotIn("![", renderer.render_thread(article, thread))
        self.assertEqual(article_before, self.article)
        self.assertEqual(thread_before, self.thread)

    def test_link_card_has_explicit_label_and_exactly_one_block(self):
        self.article["kind"] = "link_card"
        article, thread = self.validate()
        self.assertIn("页面摘要（未取得正文）", renderer.render_thread(article, thread))
        self.thread["blocks"].append({"id": "block-02", "title": "虚构完整正文", "text": "内容。", "image_ids": []})
        with self.assertRaisesRegex(renderer.ValidationError, "exactly one"):
            self.validate()

    def test_duplicate_ids_and_repeated_image_use_fail(self):
        variants = []
        article = copy.deepcopy(self.article)
        article["images"].append(copy.deepcopy(article["images"][0]))
        variants.append((article, self.thread, "duplicate source image id"))
        thread = copy.deepcopy(self.thread)
        thread["images"].append(copy.deepcopy(thread["images"][0]))
        variants.append((self.article, thread, "duplicate selected image id"))
        thread = copy.deepcopy(self.thread)
        thread["blocks"].append(copy.deepcopy(thread["blocks"][0]))
        variants.append((self.article, thread, "duplicate block id"))
        thread = copy.deepcopy(self.thread)
        thread["blocks"][0]["image_ids"].append(thread["blocks"][0]["image_ids"][0])
        variants.append((self.article, thread, "used more than once"))
        thread = copy.deepcopy(self.thread)
        thread["blocks"].append({"id": "block-02", "title": "第二段", "text": "内容。",
                                 "image_ids": [thread["images"][0]["id"]]})
        variants.append((self.article, thread, "used more than once"))
        for article, thread, message in variants:
            with self.subTest(message=message):
                with self.assertRaisesRegex(renderer.ValidationError, message):
                    self.validate(article, thread)

    def test_unknown_or_unused_image_references_fail(self):
        thread = copy.deepcopy(self.thread)
        thread["images"][0]["id"] = "invented-image"
        with self.assertRaisesRegex(renderer.ValidationError, "absent from the source"):
            self.validate(thread=thread)
        thread = copy.deepcopy(self.thread)
        thread["blocks"][0]["image_ids"] = ["invented-image"]
        with self.assertRaisesRegex(renderer.ValidationError, "undeclared image"):
            self.validate(thread=thread)
        thread = copy.deepcopy(self.thread)
        thread["blocks"][0]["image_ids"] = []
        with self.assertRaisesRegex(renderer.ValidationError, "unused"):
            self.validate(thread=thread)

    def test_semantic_field_types_and_unknown_fields_fail(self):
        mutations = [
            lambda t: t.update(schema_version=True),
            lambda t: t.update(title=[]),
            lambda t: t.update(summary=" "),
            lambda t: t.update(tags="标签"),
            lambda t: t.update(blocks=[]),
            lambda t: t.update(images={}),
            lambda t: t.update(source_url="https://unverified.example"),
            lambda t: t["blocks"][0].update(text={}),
            lambda t: t["blocks"][0].update(title="第一行\n第二行"),
            lambda t: t["blocks"][0].update(image_ids="img-abcdef1234567890"),
            lambda t: t["images"][0].update(description=""),
            lambda t: t["images"][0].update(url="https://unverified.example/image.png"),
            lambda t: t["tags"].append("测试"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                thread = copy.deepcopy(self.thread)
                mutate(thread)
                with self.assertRaises(renderer.ValidationError):
                    self.validate(thread=thread)

    def test_body_images_nonstandard_markup_and_h1_fail(self):
        invalid = [
            "# 第二个一级标题\n内容。",
            "一级标题\n===\n内容。",
            "![绕过引用](https://example.org/invented.png)",
            "![绕过引用][ref]\n[ref]: https://example.org/invented.png",
            '<IMG src="https://example.org/invented.png">',
            "<picture>...</picture>",
            '<iframe src="https://example.org"></iframe>',
            "<mw:link>标签</mw:link>",
            "<MW:category>分类</MW:category>",
        ]
        for value in invalid:
            for field in ("text", "summary"):
                with self.subTest(value=value, field=field):
                    thread = copy.deepcopy(self.thread)
                    if field == "text":
                        thread["blocks"][0]["text"] = value
                    else:
                        thread["summary"] = value
                    with self.assertRaises(renderer.ValidationError):
                        self.validate(thread=thread)

    def test_fenced_code_h1_and_tables_remain_valid(self):
        self.thread["blocks"][0]["text"] = "示例：\n\n```text\n# literal\n```\n\n| 项目 | 数量 |\n| --- | ---: |\n| A | 2 |"
        article, thread = self.validate()
        self.assertIn("| A | 2 |", renderer.render_thread(article, thread))

    def test_source_fields_and_image_urls_are_checked(self):
        for name, value in [("source_url", "javascript:alert(1)"), ("resolved_url", "relative/path"),
                            ("source_url", "https://example.org/with space"), ("kind", "other"),
                            ("kind", []), ("author", []), ("images", None)]:
            with self.subTest(name=name, value=value):
                article = copy.deepcopy(self.article)
                article[name] = value
                with self.assertRaises(renderer.ValidationError):
                    self.validate(article=article)
        self.article["images"][0]["url"] = "data:image/png;base64,AAAA"
        with self.assertRaises(renderer.ValidationError):
            self.validate()

    def write_inputs(self, directory, article=None, thread=None):
        article_path, thread_path = directory / "article.json", directory / "thread.json"
        article_path.write_text(json.dumps(self.article if article is None else article), encoding="utf-8")
        thread_path.write_text(json.dumps(self.thread if thread is None else thread), encoding="utf-8")
        return article_path, thread_path

    def run_cli(self, article_path, thread_path, out):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = renderer.main(["--article", str(article_path), "--thread", str(thread_path), "--out", str(out)])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_cli_writes_only_markdown_and_preserves_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            article_path, thread_path = self.write_inputs(directory)
            original_thread = thread_path.read_bytes()
            out = directory / "output"
            code, stdout, stderr = self.run_cli(article_path, thread_path, out)
            self.assertEqual(0, code, stderr)
            self.assertEqual(["thread.md"], [path.name for path in out.iterdir()])
            self.assertEqual(original_thread, thread_path.read_bytes())
            self.assertEqual(str((out / "thread.md").resolve()), json.loads(stdout)["output"])

    def test_invalid_references_do_not_write_or_replace_output(self):
        self.thread["blocks"][0]["image_ids"] = ["invented"]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            article_path, thread_path = self.write_inputs(directory)
            out = directory / "output"
            code, _, stderr = self.run_cli(article_path, thread_path, out)
            self.assertEqual(2, code)
            self.assertIn("undeclared image", stderr)
            self.assertFalse(out.exists())
            out.mkdir()
            output_path = out / "thread.md"
            output_path.write_text("保留此前结果", encoding="utf-8")
            code, _, _ = self.run_cli(article_path, thread_path, out)
            self.assertEqual(2, code)
            self.assertEqual("保留此前结果", output_path.read_text(encoding="utf-8"))

    def test_duplicate_json_keys_fail_before_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            article_path, thread_path = self.write_inputs(directory)
            thread_path.write_text('{"title": "one", "title": "two"}', encoding="utf-8")
            code, _, stderr = self.run_cli(article_path, thread_path, directory / "output")
            self.assertEqual(2, code)
            self.assertIn("duplicate JSON key", stderr)
            self.assertFalse((directory / "output").exists())


if __name__ == "__main__":
    unittest.main()
