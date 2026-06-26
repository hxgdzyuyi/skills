#!/usr/bin/env python3
"""为 explain-code skill 规划源码文件和 Markdown 输出路径。"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".nuxt",
    ".turbo",
    ".cache",
    ".pytest_cache",
    "node_modules",
    "bower_components",
    "coverage",
    "dist",
    "build",
    "out",
    "target",
    "vendor",
    "__pycache__",
}

SKIP_SUFFIXES = {
    ".7z",
    ".a",
    ".bmp",
    ".class",
    ".db",
    ".dll",
    ".dylib",
    ".exe",
    ".gif",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".map",
    ".min.css",
    ".min.js",
    ".mp3",
    ".mp4",
    ".o",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".svg",
    ".tar",
    ".webp",
    ".zip",
}


def is_skipped(path: Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_DIRS:
        return True
    name = path.name.lower()
    return any(name.endswith(suffix) for suffix in SKIP_SUFFIXES)


def iter_files(root: Path) -> Iterable[Path]:
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        base = Path(current_root)
        for file_name in files:
            path = base / file_name
            if not is_skipped(path):
                yield path


def has_glob_magic(pattern: str) -> bool:
    return any(char in pattern for char in "*?[")


def gitignored_files(root: Path, paths: Iterable[Path]) -> set[str]:
    rel_paths = [path.relative_to(root).as_posix() for path in paths]
    if not rel_paths:
        return set()

    input_data = ("\0".join(rel_paths) + "\0").encode()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--no-index", "--stdin", "-z"],
            input=input_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except FileNotFoundError:
        return set()

    if result.returncode not in (0, 1):
        return set()

    return {
        item.decode(errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    }


def matched_files(root: Path, patterns: list[str]) -> list[Path]:
    matches: set[Path] = set()

    for pattern in patterns:
        raw = Path(pattern)
        absolute_pattern = raw if raw.is_absolute() else root / raw
        if has_glob_magic(pattern):
            for candidate in glob.iglob(str(absolute_pattern), recursive=True):
                path = Path(candidate)
                if path.is_file() and not is_skipped(path):
                    matches.add(path.resolve())
        elif absolute_pattern.is_dir():
            matches.update(path.resolve() for path in iter_files(absolute_pattern))
        elif absolute_pattern.is_file() and not is_skipped(absolute_pattern):
            matches.add(absolute_pattern.resolve())

    files = sorted(matches)
    ignored = gitignored_files(root, files)
    return [path for path in files if path.relative_to(root).as_posix() not in ignored]


def doc_path(root: Path, source: Path, output_root: Path) -> Path:
    relative = source.relative_to(root)
    return output_root.joinpath(relative).with_suffix(relative.suffix + ".md")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="列出需要解析的源码文件及其 Markdown 文档输出路径。"
    )
    parser.add_argument("patterns", nargs="+", help="需要解析的路径或 glob")
    parser.add_argument("--root", default=".", help="仓库根目录，默认当前目录")
    parser.add_argument(
        "--output-root",
        default="docs/code_explanations",
        help="文档输出根目录，默认 docs/code_explanations",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON，而不是表格")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_root = root / args.output_root
    files = matched_files(root, args.patterns)

    records = [
        {
            "source": path.relative_to(root).as_posix(),
            "doc": doc_path(root, path, output_root).relative_to(root).as_posix(),
        }
        for path in files
    ]

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        for record in records:
            print(f"{record['source']}\t{record['doc']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
