#!/usr/bin/env python3
"""Initialize and manage a Hugo project for WeChat articles."""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence, Tuple


EXIT_OK = 0
EXIT_ERROR = 1
EXIT_HUGO_MISSING = 2

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PLUGIN_ROOT / "assets" / "hugo-template"

REQUIRED_FILES = (
    Path("hugo.toml"),
    Path("archetypes/wechat.html"),
    Path("content/wechat/_index.md"),
    Path("layouts/wechat/baseof.html"),
    Path("layouts/wechat/single.html"),
    Path("layouts/wechat/list.html"),
    Path("layouts/partials/wechat/copy-button.html"),
    Path("assets/css/wechat-preview.css"),
    Path("assets/js/wechat-copy.js"),
)

ALTERNATIVE_CONFIGS = (
    Path("config.toml"),
    Path("config.yaml"),
    Path("config.yml"),
    Path("config.json"),
    Path("hugo.yaml"),
    Path("hugo.yml"),
    Path("hugo.json"),
)

MARKER = """[params.mpArticle]
enabled = true
schemaVersion = 1
"""

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKER_RE = re.compile(
    r"(?ms)^\s*\[params\.mpArticle\]\s*$"
    r"(?P<body>.*?)(?=^\s*\[[^\]]+\]\s*$|\Z)"
)

Runner = Callable[[str, Path], Tuple[bool, str]]


def find_hugo() -> Optional[str]:
    return shutil.which("hugo")


def hugo_install_hint() -> str:
    system = platform.system()
    if system == "Darwin":
        command = "brew install hugo"
    elif system == "Windows":
        command = "winget install Hugo.Hugo.Extended"
    else:
        command = "使用系统包管理器安装 Hugo，例如 sudo apt install hugo"
    return (
        "未找到 Hugo。请先安装后重新运行。\n"
        f"建议命令：{command}\n"
        "官方安装说明：https://gohugo.io/installation/"
    )


def hugo_version(hugo: str) -> Tuple[bool, str]:
    try:
        completed = subprocess.run(
            [hugo, "version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return False, f"无法执行 Hugo：{exc}"
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output


def marker_state(config_text: str) -> Tuple[str, str]:
    matches = list(MARKER_RE.finditer(config_text))
    if not matches:
        return "missing", "缺少 [params.mpArticle] 工程标记"
    if len(matches) > 1:
        return "conflict", "存在多个 [params.mpArticle] 配置块"

    body = matches[0].group("body")
    enabled = re.search(r"(?m)^\s*enabled\s*=\s*true\s*(?:#.*)?$", body)
    schema = re.search(r"(?m)^\s*schemaVersion\s*=\s*1\s*(?:#.*)?$", body)
    if enabled and schema:
        return "valid", ""
    return "conflict", "已有 [params.mpArticle]，但 enabled 或 schemaVersion 不兼容"


def doctor_findings(root: Path) -> list[str]:
    findings: list[str] = []
    if not root.exists():
        return [f"项目目录不存在：{root}"]
    if not root.is_dir():
        return [f"项目路径不是目录：{root}"]

    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            findings.append(f"缺少 {relative.as_posix()}")

    config = root / "hugo.toml"
    if config.is_file():
        state, message = marker_state(config.read_text(encoding="utf-8"))
        if state != "valid":
            findings.append(message)
    else:
        alternatives = [str(path) for path in ALTERNATIVE_CONFIGS if (root / path).exists()]
        if alternatives:
            findings.append(
                "项目使用非 hugo.toml 配置，安全模式不会自动迁移："
                + ", ".join(alternatives)
            )
    return findings


def directory_is_effectively_empty(root: Path) -> bool:
    ignored = {".git", ".DS_Store"}
    return not any(entry.name not in ignored for entry in root.iterdir())


def run_hugo_new_site(hugo: str, root: Path) -> Tuple[bool, str]:
    completed = subprocess.run(
        [hugo, "new", "site", str(root), "--force", "--format", "toml"],
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or completed.stderr).strip()
    return completed.returncode == 0, output


def template_files() -> Iterable[Tuple[Path, Path]]:
    for source in sorted(TEMPLATE_ROOT.rglob("*")):
        if source.is_file():
            yield source.relative_to(TEMPLATE_ROOT), source


def preflight(root: Path, allow_generated_config: bool) -> list[str]:
    conflicts: list[str] = []
    config = root / "hugo.toml"

    if not config.exists():
        alternatives = [path for path in ALTERNATIVE_CONFIGS if (root / path).exists()]
        if alternatives and not allow_generated_config:
            conflicts.append(
                "检测到其他 Hugo 配置文件，无法安全创建 hugo.toml："
                + ", ".join(path.as_posix() for path in alternatives)
            )
    else:
        state, message = marker_state(config.read_text(encoding="utf-8"))
        if state == "conflict":
            conflicts.append(message)

    for relative, source in template_files():
        if relative == Path("hugo.toml"):
            continue
        destination = root / relative
        if destination.is_file() and destination.read_bytes() != source.read_bytes():
            conflicts.append(f"文件冲突：{relative.as_posix()}")
        elif destination.exists() and not destination.is_file():
            conflicts.append(f"目标不是普通文件：{relative.as_posix()}")
    return conflicts


def install_template(root: Path) -> list[str]:
    changes: list[str] = []
    config = root / "hugo.toml"

    for relative, source in template_files():
        destination = root / relative
        if relative == Path("hugo.toml") and config.exists():
            continue
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        changes.append(f"新增 {relative.as_posix()}")

    state, _ = marker_state(config.read_text(encoding="utf-8"))
    if state == "missing":
        existing = config.read_text(encoding="utf-8")
        separator = "" if not existing or existing.endswith("\n\n") else "\n"
        config.write_text(existing + separator + MARKER, encoding="utf-8")
        changes.append("更新 hugo.toml：追加 mpArticle 工程标记")
    return changes


def initialize_project(
    root: Path,
    hugo: str,
    new_site_runner: Runner = run_hugo_new_site,
) -> Tuple[bool, list[str]]:
    root.mkdir(parents=True, exist_ok=True)
    empty = directory_is_effectively_empty(root)

    if empty:
        success, output = new_site_runner(hugo, root)
        if not success:
            return False, [f"Hugo 初始化失败：{output}"]

        generated_config = root / "config.toml"
        generated_hugo_config = root / "hugo.toml"
        if generated_config.exists():
            generated_config.unlink()
        if generated_hugo_config.exists():
            generated_hugo_config.unlink()

    conflicts = preflight(root, allow_generated_config=empty)
    if conflicts:
        return False, conflicts

    return True, install_template(root)


def quote_yaml(value: str) -> str:
    compact = " ".join(value.splitlines()).strip()
    return compact.replace("\\", "\\\\").replace('"', '\\"')


def create_article(root: Path, slug: str, title: str) -> Tuple[bool, str]:
    if not SLUG_RE.fullmatch(slug):
        return False, "slug 只能包含小写英文字母、数字和单个连字符"
    if not title.strip():
        return False, "标题不能为空"

    findings = doctor_findings(root)
    if findings:
        return False, "工程不完整：\n" + "\n".join(f"- {item}" for item in findings)

    article_dir = root / "content" / "wechat" / slug
    if article_dir.exists():
        return False, f"文章目录已存在：{article_dir}"

    article_dir.mkdir(parents=True)
    (article_dir / "assets").mkdir()
    timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    content = f"""---
title: "{quote_yaml(title)}"
date: {timestamp}
description: ""
draft: true
cover: ""
---
<section style="color:#3f3f3f;font-size:15px;line-height:1.75;letter-spacing:0.5px;word-break:break-word;">
</section>
"""
    article = article_dir / "index.html"
    article.write_text(content, encoding="utf-8")
    return True, str(article)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="初始化、检查和管理 mp-article Hugo 工程"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command in ("doctor", "init"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--root", default=".", help="Hugo 项目根目录")

    new_parser = subparsers.add_parser("new")
    new_parser.add_argument("--root", default=".", help="Hugo 项目根目录")
    new_parser.add_argument("--slug", required=True)
    new_parser.add_argument("--title", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    hugo = find_hugo()
    if not hugo:
        print(hugo_install_hint(), file=sys.stderr)
        return EXIT_HUGO_MISSING

    version_ok, version_output = hugo_version(hugo)
    if not version_ok:
        print(version_output, file=sys.stderr)
        return EXIT_ERROR

    if args.command == "doctor":
        findings = doctor_findings(root)
        if findings:
            print(f"Hugo：{version_output}")
            print("工程检查未通过：")
            for finding in findings:
                print(f"- {finding}")
            return EXIT_ERROR
        print(f"Hugo：{version_output}")
        print(f"工程完整：{root}")
        return EXIT_OK

    if args.command == "init":
        success, messages = initialize_project(root, hugo)
        stream = sys.stdout if success else sys.stderr
        for message in messages:
            print(message, file=stream)
        if success:
            print(f"工程已就绪：{root}")
            return EXIT_OK
        return EXIT_ERROR

    success, message = create_article(root, args.slug, args.title)
    print(message, file=sys.stdout if success else sys.stderr)
    return EXIT_OK if success else EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
