#!/usr/bin/env python3
"""Validate hierarchy counts and round coverage for a story outline."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


RANGE_RE = re.compile(r"（(\d+)[—-](\d+)轮）")


def ranges_for(lines: list[str], prefix: str) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    for line in lines:
        if line.startswith(prefix):
            match = RANGE_RE.search(line)
            if not match:
                raise ValueError(f"缺少轮次范围：{line}")
            result.append((int(match.group(1)), int(match.group(2))))
    return result


def expanded(ranges: list[tuple[int, int]]) -> list[int]:
    return [number for start, end in ranges for number in range(start, end + 1)]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("outline", type=Path)
    args = parser.parse_args()

    lines = args.outline.read_text(encoding="utf-8").splitlines()
    acts = [line for line in lines if line.startswith("## 幕")]
    sequences = [line for line in lines if line.startswith("### 序列")]
    scenes = [line for line in lines if line.startswith("#### 场景")]
    beats = [line for line in lines if line.startswith("- 节拍")]

    require(len(acts) == 3, f"幕数量应为 3，实际为 {len(acts)}")
    require(len(sequences) == 6, f"序列数量应为 6，实际为 {len(sequences)}")
    require(len(scenes) == 13, f"场景数量应为 13，实际为 {len(scenes)}")
    require(35 <= len(beats) <= 45, f"节拍数量应在 35—45，实际为 {len(beats)}")

    scene_ranges = ranges_for(lines, "#### 场景")
    beat_ranges = ranges_for(lines, "- 节拍")
    require(
        expanded(scene_ranges) == list(range(1, 101)),
        "场景轮次必须无重叠、无缺口地覆盖 1—100 轮",
    )
    require(
        expanded(beat_ranges) == list(range(1, 101)),
        "节拍轮次必须无重叠、无缺口地覆盖 1—100 轮",
    )
    require(
        all(5 <= end - start + 1 <= 11 for start, end in scene_ranges),
        "每个场景必须持续 5—11 轮",
    )
    require(
        all(1 <= end - start + 1 <= 3 for start, end in beat_ranges),
        "每个节拍必须持续 1—3 轮",
    )

    summary_counts = {
        "幕一句话：": sum(line.startswith("幕一句话：") for line in lines),
        "序列一句话：": sum(line.startswith("序列一句话：") for line in lines),
        "场景一句话：": sum(line.startswith("场景一句话：") for line in lines),
    }
    require(summary_counts["幕一句话："] == 3, "每一幕必须有且只有一句摘要")
    require(summary_counts["序列一句话："] == 6, "每个序列必须有且只有一句摘要")
    require(summary_counts["场景一句话："] == 13, "每个场景必须有且只有一句摘要")

    print(
        f"OK: 3幕 / 6序列 / 13场景 / {len(beats)}节拍，完整覆盖1—100轮：{args.outline}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error
