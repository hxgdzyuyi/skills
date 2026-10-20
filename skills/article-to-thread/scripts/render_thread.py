#!/usr/bin/env python3
"""Validate an article/thread pair and render a source-attributed Markdown file.

Only Python's standard library is required. Content editing and factual checks
belong to Codex; this script verifies the structural contract and image origins.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import urlsplit


class ValidationError(ValueError):
    """The input does not satisfy the article-to-thread contract."""


THREAD_FIELDS = {"schema_version", "title", "summary", "tags", "blocks", "images"}
BLOCK_FIELDS = {"id", "title", "text", "image_ids"}
IMAGE_FIELDS = {"id", "description"}
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
IMAGE_MARKUP = re.compile(
    r"!\s*\[|<\s*(?:img|picture|svg|iframe|video|source|object|embed)\b",
    re.IGNORECASE,
)


def require_object(value: Any, location: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError(f"{location} must be an object")
    return value


def require_fields(value: dict[str, Any], fields: set[str], location: str) -> None:
    missing = fields - value.keys()
    unknown = value.keys() - fields
    if missing:
        raise ValidationError(f"{location} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise ValidationError(f"{location} has unknown fields: {', '.join(sorted(unknown))}")


def require_string(value: Any, location: str, *, single_line: bool = False) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{location} must be a nonempty string")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in value):
        raise ValidationError(f"{location} contains control characters")
    if single_line and ("\n" in value or "\r" in value):
        raise ValidationError(f"{location} must fit on one line")
    return value.strip()


def require_id(value: Any, location: str) -> str:
    identifier = require_string(value, location, single_line=True)
    if identifier != value or not ID_PATTERN.fullmatch(identifier):
        raise ValidationError(f"{location} must contain only letters, digits, dots, '_' or '-'")
    return identifier


def require_list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{location} must be an array")
    return value


def require_url(value: Any, location: str) -> str:
    url = require_string(value, location, single_line=True)
    if url != value or re.search(r"[\s<>\"\\]", url):
        raise ValidationError(f"{location} must be an absolute HTTP(S) URL without whitespace")
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme.lower() in {"http", "https"} and bool(parsed.hostname)
        # Accessing port also detects malformed or out-of-range port values.
        _ = parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise ValidationError(f"{location} must be an absolute HTTP(S) URL")
    return url


def validate_markdown(value: Any, location: str) -> None:
    text = require_string(value, location)
    if re.search(r"<\s*/?\s*mw:", text, re.IGNORECASE):
        raise ValidationError(f"{location} contains a nonstandard <mw:...> tag")
    if IMAGE_MARKUP.search(text):
        raise ValidationError(f"{location} contains image/embed markup; use image_ids instead")

    # Heading-looking lines inside fenced code are literal code, not headings.
    fence_char = None
    fence_length = 0
    previous = ""
    for line in text.splitlines():
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            marker = fence.group(1)
            if fence_char is None:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length:
                fence_char, fence_length = None, 0
            previous = ""
            continue
        if fence_char is not None:
            continue
        if re.match(r"^ {0,3}#(?:[ \t]|$)", line):
            raise ValidationError(f"{location} contains an H1 heading")
        if previous.strip() and re.fullmatch(r" {0,3}=+[ \t]*", line):
            raise ValidationError(f"{location} contains an H1 heading")
        previous = line


def validate_article(value: Any) -> dict[str, Any]:
    article = require_object(value, "article")
    for name in ("source_url", "resolved_url", "kind", "images"):
        if name not in article:
            raise ValidationError(f"article is missing: {name}")
    require_url(article["source_url"], "article.source_url")
    require_url(article["resolved_url"], "article.resolved_url")
    if not isinstance(article["kind"], str) or article["kind"] not in {"article", "link_card"}:
        raise ValidationError("article.kind must be 'article' or 'link_card'")
    for name in ("title", "author"):
        if article.get(name) is not None and not isinstance(article[name], str):
            raise ValidationError(f"article.{name} must be a string or null")

    ids: set[str] = set()
    urls: set[str] = set()
    for index, entry in enumerate(require_list(article["images"], "article.images")):
        location = f"article.images[{index}]"
        image = require_object(entry, location)
        identifier = require_id(image.get("id"), f"{location}.id")
        url = require_url(image.get("url"), f"{location}.url")
        if identifier in ids:
            raise ValidationError(f"duplicate source image id: {identifier}")
        if url in urls:
            raise ValidationError(f"duplicate source image URL: {url}")
        ids.add(identifier)
        urls.add(url)
        for name in ("alt", "caption", "context"):
            if name in image and not isinstance(image[name], str):
                raise ValidationError(f"{location}.{name} must be a string")
    return article


def validate_thread(value: Any, article: dict[str, Any]) -> dict[str, Any]:
    thread = require_object(value, "thread")
    require_fields(thread, THREAD_FIELDS, "thread")
    if type(thread["schema_version"]) is not int or thread["schema_version"] != 1:
        raise ValidationError("thread.schema_version must be the integer 1")
    require_string(thread["title"], "thread.title", single_line=True)
    validate_markdown(thread["summary"], "thread.summary")

    tags: set[str] = set()
    for index, tag in enumerate(require_list(thread["tags"], "thread.tags")):
        cleaned = require_string(tag, f"thread.tags[{index}]", single_line=True)
        if cleaned in tags:
            raise ValidationError(f"duplicate tag: {cleaned}")
        tags.add(cleaned)

    source_images = {entry["id"]: entry for entry in article["images"]}
    selected_images: set[str] = set()
    for index, entry in enumerate(require_list(thread["images"], "thread.images")):
        location = f"thread.images[{index}]"
        image = require_object(entry, location)
        require_fields(image, IMAGE_FIELDS, location)
        identifier = require_id(image["id"], f"{location}.id")
        require_string(image["description"], f"{location}.description", single_line=True)
        if identifier not in source_images:
            raise ValidationError(f"image id is absent from the source article: {identifier}")
        if identifier in selected_images:
            raise ValidationError(f"duplicate selected image id: {identifier}")
        selected_images.add(identifier)

    blocks = require_list(thread["blocks"], "thread.blocks")
    if not blocks:
        raise ValidationError("thread.blocks must contain at least one block")
    if article["kind"] == "link_card" and len(blocks) != 1:
        raise ValidationError("link_card output must contain exactly one block")
    block_ids: set[str] = set()
    used_images: set[str] = set()
    for index, entry in enumerate(blocks):
        location = f"thread.blocks[{index}]"
        block = require_object(entry, location)
        require_fields(block, BLOCK_FIELDS, location)
        identifier = require_id(block["id"], f"{location}.id")
        if identifier in block_ids:
            raise ValidationError(f"duplicate block id: {identifier}")
        block_ids.add(identifier)
        require_string(block["title"], f"{location}.title", single_line=True)
        validate_markdown(block["text"], f"{location}.text")
        for image_index, image_id in enumerate(require_list(block["image_ids"], f"{location}.image_ids")):
            require_id(image_id, f"{location}.image_ids[{image_index}]")
            if image_id not in selected_images:
                raise ValidationError(f"block references an undeclared image id: {image_id}")
            if image_id in used_images:
                raise ValidationError(f"image id is used more than once: {image_id}")
            used_images.add(image_id)
    unused = selected_images - used_images
    if unused:
        raise ValidationError(f"selected images are unused: {', '.join(sorted(unused))}")
    return thread


def escape_inline(value: str) -> str:
    # Metadata and image descriptions are plain text, not authored Markdown.
    text = " ".join(value.split())
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"([\\`*_[\]{}()#!|])", r"\\\1", text)


def render_thread(article: dict[str, Any], thread: dict[str, Any]) -> str:
    source_images = {entry["id"]: entry for entry in article["images"]}
    descriptions = {entry["id"]: entry["description"] for entry in thread["images"]}
    parts = [f"# {escape_inline(thread['title'])}"]
    metadata = []
    if article.get("author") and article["author"].strip():
        metadata.append(f"作者：{escape_inline(article['author'])}")
    source_label = escape_inline(article.get("title") or "原文")
    metadata.append(f"来源：[{source_label}](<{article['source_url']}>)")
    if article["resolved_url"] != article["source_url"]:
        metadata.append(f"实际页面：[查看原文](<{article['resolved_url']}>)")
    parts.append("  \n".join(metadata))
    if article["kind"] == "link_card":
        parts.append("> **页面摘要（未取得正文）**\n> 仅依据页面公开元信息整理，未取得文章正文。")
    parts.append(thread["summary"].strip())
    for block in thread["blocks"]:
        parts.extend([f"## {escape_inline(block['title'])}", block["text"].strip()])
        for identifier in block["image_ids"]:
            alt = escape_inline(descriptions[identifier])
            parts.append(f"![{alt}](<{source_images[identifier]['url']}>)")
    if thread["tags"]:
        parts.append("标签：" + "、".join(escape_inline(tag) for tag in thread["tags"]))
    return "\n\n".join(parts) + "\n"


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle, object_pairs_hook=unique_object)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", type=Path, required=True, help="extractor's article.json")
    parser.add_argument("--thread", type=Path, required=True, help="Codex-authored thread.json")
    parser.add_argument("--out", type=Path, required=True, help="directory for thread.md")
    args = parser.parse_args(argv)
    temporary_path = None
    try:
        article = validate_article(load_json(args.article))
        thread = validate_thread(load_json(args.thread), article)
        markdown = render_thread(article, thread)
        output_path = args.out.resolve() / "thread.md"
        if output_path in {args.article.resolve(), args.thread.resolve()}:
            raise ValidationError("output path must not overwrite an input file")
        args.out.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=args.out, prefix=".thread-", suffix=".tmp", delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            handle.write(markdown)
        os.replace(temporary_path, output_path)
        temporary_path = None
        print(json.dumps({"output": str(output_path), "blocks": len(thread["blocks"]),
                          "images": len(thread["images"]), "kind": article["kind"]}, ensure_ascii=False))
        return 0
    except (ValidationError, OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"render_thread: {error}", file=sys.stderr)
        return 2
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


if __name__ == "__main__":
    sys.exit(main())
