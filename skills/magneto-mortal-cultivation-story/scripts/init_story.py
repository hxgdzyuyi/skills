#!/usr/bin/env python3
"""Initialize a non-destructive workspace for the interactive story."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RELATIVE_DIR = Path(".codex/story-saves/万磁王穿越到凡人修仙传")


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def current_outline() -> str:
    source = (SKILL_DIR / "references" / "初始大纲.md").read_text(encoding="utf-8")
    source = source.replace(
        "# 初始大纲：万磁王穿越到《凡人修仙传》",
        "# 当前大纲：万磁王穿越到《凡人修仙传》",
        1,
    )
    source = source.replace(
        "> 本文件是不可修改的初始蓝图；运行时将副本保存为 `当前大纲.md`，节点允许因用户写入埃里克的言行而偏转。",
        "> 本文件是可变的后续结构蓝图；按用户写入埃里克的言行调整事件，但保留三幕故事功能。",
        1,
    )
    return source


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create missing story files without overwriting existing writing."
    )
    parser.add_argument(
        "--story-dir",
        "--save-dir",
        dest="story_dir",
        type=Path,
        default=DEFAULT_RELATIVE_DIR,
        help="Story directory; defaults inside the current workspace.",
    )
    args = parser.parse_args()

    story_dir = args.story_dir.expanduser().resolve()
    story_dir.mkdir(parents=True, exist_ok=True)

    templates = {
        "当前大纲.md": current_outline(),
        "故事进展.md": (SKILL_DIR / "assets" / "故事进展模板.md").read_text(
            encoding="utf-8"
        ),
    }

    created: list[str] = []
    preserved: list[str] = []
    for filename, content in templates.items():
        target = story_dir / filename
        if write_if_missing(target, content):
            created.append(filename)
        else:
            preserved.append(filename)

    print(
        json.dumps(
            {
                "story_dir": str(story_dir),
                "mode": "continue" if preserved else "new",
                "created": created,
                "preserved": preserved,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
