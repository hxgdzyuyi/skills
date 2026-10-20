#!/usr/bin/env python3
"""Assemble completed per-block drafts in plan order into validated thread.json.

This checks file completeness and source line references, not semantic coverage.
Codex must compare the drafts with the source and the plan's fact checklist.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from render_thread import (
    BLOCK_FIELDS, ValidationError, load_json, require_fields, require_id,
    require_list, require_object, require_string, validate_article, validate_thread,
)


def validate_plan(value: Any, source_line_count: int) -> dict[str, Any]:
    plan = require_object(value, "plan")
    require_fields(plan, {"schema_version", "blocks"}, "plan")
    if type(plan["schema_version"]) is not int or plan["schema_version"] != 1:
        raise ValidationError("plan.schema_version must be the integer 1")
    blocks = require_list(plan["blocks"], "plan.blocks")
    if not blocks:
        raise ValidationError("plan.blocks must contain at least one block")
    ids: set[str] = set()
    for index, entry in enumerate(blocks):
        location = f"plan.blocks[{index}]"
        block = require_object(entry, location)
        require_fields(block, {"id", "title", "summary", "source_ranges", "preserve"}, location)
        identifier = require_id(block["id"], f"{location}.id")
        if identifier in ids:
            raise ValidationError(f"duplicate planned block id: {identifier}")
        ids.add(identifier)
        require_string(block["title"], f"{location}.title", single_line=True)
        require_string(block["summary"], f"{location}.summary")
        for fact_index, fact in enumerate(require_list(block["preserve"], f"{location}.preserve")):
            require_string(fact, f"{location}.preserve[{fact_index}]")
        ranges = require_list(block["source_ranges"], f"{location}.source_ranges")
        if not ranges:
            raise ValidationError(f"{location}.source_ranges must contain at least one range")
        for range_index, entry in enumerate(ranges):
            range_location = f"{location}.source_ranges[{range_index}]"
            span = require_object(entry, range_location)
            require_fields(span, {"start_line", "end_line"}, range_location)
            start, end = span["start_line"], span["end_line"]
            if type(start) is not int or type(end) is not int or not 1 <= start <= end <= source_line_count:
                raise ValidationError(
                    f"{range_location} must be a 1-based inclusive range within source lines 1..{source_line_count}"
                )
    return plan


def load_completed_thread(args: argparse.Namespace) -> tuple[dict[str, Any], list[Path], dict[str, Any]]:
    article = validate_article(load_json(args.article))
    source_line_count = len(args.source.read_text(encoding="utf-8").splitlines())
    plan = validate_plan(load_json(args.plan), source_line_count)
    metadata = require_object(load_json(args.meta), "meta")
    require_fields(metadata, {"title", "summary", "tags", "images"}, "meta")
    inputs = [args.article, args.source, args.plan, args.meta]
    blocks = []
    for planned in plan["blocks"]:
        draft_path = args.drafts / f"{planned['id']}.json"
        if not draft_path.is_file():
            raise ValidationError(f"missing planned draft: {draft_path}")
        draft = require_object(load_json(draft_path), f"draft {planned['id']}")
        require_fields(draft, BLOCK_FIELDS, f"draft {planned['id']}")
        if draft["id"] != planned["id"]:
            raise ValidationError(f"draft id does not match plan: {draft_path}")
        inputs.append(draft_path)
        blocks.append(draft)
    thread = {"schema_version": 1, **metadata, "blocks": blocks}
    validate_thread(thread, article)
    return thread, inputs, article


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("article", "source", "plan", "drafts", "meta", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args(argv)
    temporary_path = None
    try:
        thread, inputs, article = load_completed_thread(args)
        output_path = args.out.resolve() / "thread.json"
        for input_path in inputs:
            if output_path.resolve() == input_path.resolve() or (
                output_path.exists() and os.path.samefile(output_path, input_path)
            ):
                raise ValidationError(f"output path must not overwrite an input file: {input_path}")
        args.out.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.out, prefix=".thread-", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(thread, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, output_path)
        temporary_path = None
        print(json.dumps({"output": str(output_path), "blocks": len(thread["blocks"]),
                          "images": len(thread["images"]), "kind": article["kind"]}, ensure_ascii=False))
        return 0
    except (ValidationError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"assemble_thread: {error}", file=sys.stderr)
        return 2
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
