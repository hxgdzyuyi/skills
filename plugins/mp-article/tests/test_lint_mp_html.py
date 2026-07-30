import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "lint_mp_html.py"
SPEC = importlib.util.spec_from_file_location("lint_mp_html", SCRIPT)
lint = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = lint
SPEC.loader.exec_module(lint)


class LintTests(unittest.TestCase):
    def errors(self, text, mode):
        return [
            finding.message
            for finding in lint.lint_text(text, mode)
            if finding.level == "ERROR"
        ]

    def test_valid_standalone_article(self):
        html = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>文章</title></head>
<body style="margin:0;">
<section style="font-size:15px;line-height:1.75;color:#3f3f3f;">
<p style="margin:0 0 16px;">正文</p>
</section>
</body></html>"""
        self.assertEqual(self.errors(html, "standalone"), [])

    def test_valid_hugo_article_with_bundle_image(self):
        html = """---
title: "文章"
date: 2026-07-30T00:00:00+08:00
description: ""
draft: true
cover: ""
---
<section style="font-size:15px;line-height:1.75;color:#3f3f3f;">
<img src="assets/cover.png" style="display:block;width:100%;max-width:100%;height:auto;box-sizing:border-box;">
</section>
"""
        self.assertEqual(self.errors(html, "hugo"), [])

    def test_forbidden_markup_and_flex_are_errors(self):
        html = """---
title: "文章"
date: 2026-07-30T00:00:00+08:00
description: ""
draft: true
cover: ""
---
<section class="bad" style="display:flex;gap:12px;">
<div style="flex:1;">错误</div>
</section>
"""
        errors = self.errors(html, "hugo")
        self.assertTrue(any("class" in error for error in errors))
        self.assertTrue(any("<div>" in error for error in errors))
        self.assertTrue(any("Flex" in error for error in errors))

    def test_hugo_article_rejects_document_shell(self):
        html = """---
title: "文章"
date: 2026-07-30T00:00:00+08:00
description: ""
draft: true
cover: ""
---
<!doctype html><html><body><section style="font-size:15px;"></section></body></html>
"""
        errors = self.errors(html, "hugo")
        self.assertTrue(any("完整文档外壳" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
