#!/usr/bin/env python3
"""Lint standalone and Hugo-bundle WeChat article HTML."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional, Sequence


FORBIDDEN_TAGS = {
    "style",
    "link",
    "script",
    "div",
    "iframe",
    "form",
    "input",
    "object",
    "embed",
}

REQUIRED_FRONT_MATTER = ("title", "date", "description", "draft", "cover")
FRONT_MATTER_RE = re.compile(r"\A---\r?\n(?P<meta>.*?)\r?\n---\r?\n", re.S)


@dataclass
class Finding:
    level: str
    message: str
    line: Optional[int] = None

    def render(self) -> str:
        location = f"line {self.line}: " if self.line else ""
        return f"{self.level}: {location}{self.message}"


class ArticleParser(HTMLParser):
    def __init__(self, mode: str) -> None:
        super().__init__(convert_charrefs=True)
        self.mode = mode
        self.findings: list[Finding] = []

    def error(self, message: str) -> None:
        self.findings.append(Finding("ERROR", message, self.getpos()[0]))

    def warning(self, message: str) -> None:
        self.findings.append(Finding("WARN", message, self.getpos()[0]))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        self.check_tag(tag, attrs)

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, Optional[str]]]
    ) -> None:
        self.check_tag(tag, attrs)

    def check_tag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        values = {name.lower(): (value or "") for name, value in attrs}

        if tag in FORBIDDEN_TAGS:
            self.error(f"禁止使用 <{tag}>")
        for attribute in ("id", "class"):
            if attribute in values:
                self.error(f"正文不得包含 {attribute} 属性")

        style = values.get("style", "")
        compact_style = re.sub(r"\s+", "", style.lower())
        if re.search(
            r"(?:^|;)(?:flex|flex-basis|flex-wrap|gap|row-gap|column-gap)\s*:",
            style,
            re.I,
        ):
            self.error("使用了不稳定的 Flex 属性")
        if "calc(" in compact_style:
            self.error("列宽和布局不得依赖 calc()")

        if tag == "img":
            self.check_image(values, compact_style)

    def check_image(self, attrs: dict[str, str], compact_style: str) -> None:
        source = attrs.get("src", "").strip()
        if not source:
            self.error("图片缺少 src")
            return

        standalone_allowed = source.startswith("https://") or source.startswith("data:image/")
        relative_allowed = (
            source.startswith("assets/")
            and ".." not in Path(source).parts
            and not source.startswith("/")
        )
        if self.mode == "standalone" and not standalone_allowed:
            self.error("独立模式图片必须使用 https:// 或 data:image/")
        if self.mode == "hugo" and not (standalone_allowed or relative_allowed):
            self.error("Hugo 模式图片必须使用 https://、data:image/ 或 assets/ 相对路径")

        required_styles = ("display:block", "max-width:100%", "height:auto")
        for required in required_styles:
            if required not in compact_style:
                self.error(f"图片样式缺少 {required}")

        if source.startswith("data:image/"):
            self.warning("Base64 图片粘贴后可能仍需上传公众号素材库")
        elif source.startswith("https://"):
            self.warning("外链图片粘贴后可能仍需上传公众号素材库")


def split_hugo_file(text: str) -> tuple[Optional[str], str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return None, text
    return match.group("meta"), text[match.end() :]


def lint_text(text: str, mode: str) -> list[Finding]:
    findings: list[Finding] = []
    body = text
    parse_text = text

    if mode == "standalone":
        lower = text.lower()
        if "<!doctype html>" not in lower:
            findings.append(Finding("ERROR", "独立模式缺少 <!doctype html>"))
        if "<html" not in lower or "<body" not in lower:
            findings.append(Finding("ERROR", "独立模式必须包含 html 和 body"))
        body_match = re.search(
            r"<body\b[^>]*>(?P<body>.*?)</body\s*>", text, re.I | re.S
        )
        if body_match:
            body = body_match.group("body")
    else:
        metadata, body = split_hugo_file(text)
        parse_text = body
        if metadata is None:
            findings.append(Finding("ERROR", "Hugo 模式缺少 YAML Front Matter"))
        else:
            for field in REQUIRED_FRONT_MATTER:
                if not re.search(rf"(?m)^\s*{re.escape(field)}\s*:", metadata):
                    findings.append(Finding("ERROR", f"Front Matter 缺少 {field}"))
        lower_body = body.lower()
        if "<!doctype" in lower_body or "<html" in lower_body or "<body" in lower_body:
            findings.append(Finding("ERROR", "Hugo 模式正文不得包含完整文档外壳"))

    if not body.lstrip().lower().startswith("<section"):
        findings.append(Finding("ERROR", "公众号正文必须以 <section> 作为最外层容器"))

    if re.search(r"@(?:media|font-face|keyframes|supports)\b", body, re.I):
        findings.append(Finding("ERROR", "正文不得包含 CSS at-rule"))

    parser = ArticleParser(mode)
    try:
        parser.feed(parse_text)
        parser.close()
    except Exception as exc:
        findings.append(Finding("ERROR", f"HTML 无法解析：{exc}"))
    findings.extend(parser.findings)
    return findings


def lint_file(path: Path, mode: str) -> list[Finding]:
    if not path.is_file():
        return [Finding("ERROR", f"文件不存在：{path}")]
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [Finding("ERROR", "文件不是 UTF-8")]
    return lint_text(text, mode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检查微信公众号兼容 HTML")
    parser.add_argument("file", type=Path)
    parser.add_argument("--mode", choices=("standalone", "hugo"), required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    findings = lint_file(args.file, args.mode)
    for finding in findings:
        print(finding.render())
    errors = [finding for finding in findings if finding.level == "ERROR"]
    if errors:
        print(f"检查失败：{len(errors)} 个错误", file=sys.stderr)
        return 1
    print("检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
