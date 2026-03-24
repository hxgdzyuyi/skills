#!/usr/bin/env python3
"""
merge_results.py
Merges all result_*.jsonl files written by Task sub-agents into a single CSV or HTML table.

Usage:
    python3 merge_results.py --input-dir /tmp/gh_work --output ./repo-mentionable-users.csv
    python3 merge_results.py --input-dir /tmp/gh_work --output ./repo-users.html --html
    python3 merge_results.py --input-dir /tmp/gh_work --output ./repo-users --both

Output format: defaults to CSV unless --html flag is provided.
Use --both to generate both CSV and HTML files (--output is used as base name).

Each .jsonl file contains one JSON object per line:
    {"login": "..."}
"""

import argparse
import codecs
import csv
import glob
import json
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge JSONL chunk results into CSV or HTML")
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing result_*.jsonl files (e.g. /tmp/gh_work)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path (or base name if --both is used)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Output as HTML table instead of CSV (default is CSV)",
    )
    parser.add_argument(
        "--both",
        action="store_true",
        help="Output both CSV and HTML files (--output is base name)",
    )
    parser.add_argument(
        "--total-users",
        type=int,
        default=None,
        help="Total users fetched (for summary display). Optional.",
    )
    return parser.parse_args()


def iter_jsonl_files(input_dir: str):
    """Yield (filepath, list_of_records) for every result_*.jsonl file."""
    pattern = os.path.join(input_dir, "result_*.jsonl")
    paths = sorted(glob.glob(pattern))
    if not paths:
        print(f"[merge] WARNING: No result_*.jsonl files found in {input_dir}", file=sys.stderr)
    return paths


def load_jsonl(filepath: str) -> tuple[list[dict], list[str]]:
    """
    Parse a JSONL file. Returns (records, errors).
    Errors are line-level parse failures; a bad line does NOT abort the file.
    """
    records: list[dict] = []
    errors: list[str] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for lineno, raw in enumerate(f, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    records.append(obj)
                except json.JSONDecodeError as exc:
                    errors.append(f"{filepath}:{lineno} — {exc}")
    except OSError as exc:
        errors.append(f"Cannot open {filepath} — {exc}")
    return records, errors


def load_user_index(input_dir: str) -> dict[str, dict]:
    """
    Load the full TSV (gh_users_all.tsv) and build a login → user-info dict.
    This provides url/websiteUrl that are not sent to the LLM.
    """
    tsv_path = os.path.join(input_dir, "gh_users_all.tsv")
    index: dict[str, dict] = {}
    try:
        with open(tsv_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 5:
                    parts.extend([""] * (5 - len(parts)))
                name, login, location, url, website_url = parts[0], parts[1], parts[2], parts[3], parts[4]
                if login:
                    index[login] = {
                        "name": name,
                        "url": url,
                        "websiteUrl": website_url,
                    }
    except OSError as exc:
        print(f"[merge] WARNING: Cannot read {tsv_path} — {exc}", file=sys.stderr)
    return index


def merge(input_dir: str) -> tuple[list[dict], list[str], list[str]]:
    """
    Merge all JSONL chunk results, enriching with url/websiteUrl from the full TSV.
    Returns (deduplicated_records, failed_chunks, all_parse_errors).
    """
    user_index = load_user_index(input_dir)

    seen_logins: set[str] = set()
    merged: list[dict] = []
    failed_chunks: list[str] = []
    all_errors: list[str] = []

    paths = iter_jsonl_files(input_dir)

    for path in paths:
        records, errors = load_jsonl(path)
        if errors:
            # File-level open error → mark whole chunk as failed
            if any("Cannot open" in e for e in errors):
                failed_chunks.append(os.path.basename(path))
            all_errors.extend(errors)

        for rec in records:
            login = rec.get("login", "").strip()
            if not login:
                continue  # skip malformed records without a login
            if login not in seen_logins:
                seen_logins.add(login)
                # Enrich with fields from original TSV
                extra = user_index.get(login, {})
                rec.setdefault("name", extra.get("name", ""))
                rec.setdefault("url", extra.get("url", ""))
                rec.setdefault("websiteUrl", extra.get("websiteUrl", ""))
                merged.append(rec)

    return merged, failed_chunks, all_errors


def write_csv(records: list[dict], output_path: str) -> None:
    """Write records to a UTF-8-with-BOM CSV so Excel opens it correctly."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with codecs.open(output_path, "w", encoding="utf-8-sig") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["用户名", "用户ID", "Github上用户链接", "用户个人主页的链接"])
        for rec in records:
            writer.writerow([
                rec.get("name", ""),
                rec.get("login", ""),
                rec.get("url", ""),
                rec.get("websiteUrl", ""),
            ])


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def write_html(records: list[dict], output_path: str) -> None:
    """Write records to an HTML table with basic styling."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    table {
      border-collapse: collapse;
      width: 100%;
      font-family: Arial, sans-serif;
    }
    th {
      background-color: #4CAF50;
      color: white;
      padding: 12px;
      text-align: left;
      border: 1px solid #ddd;
      font-weight: bold;
    }
    td {
      padding: 10px;
      border: 1px solid #ddd;
    }
    tr:nth-child(even) {
      background-color: #f9f9f9;
    }
    tr:hover {
      background-color: #f0f0f0;
    }
  </style>
</head>
<body>
<table>
<thead>
<tr>
  <th>用户名</th>
  <th>用户ID</th>
  <th>Github上用户链接</th>
  <th>用户个人主页的链接</th>
</tr>
</thead>
<tbody>
""")
        for rec in records:
            f.write("<tr>\n")
            f.write(f"  <td>{escape_html(rec.get('name', ''))}</td>\n")
            f.write(f"  <td>{escape_html(rec.get('login', ''))}</td>\n")
            f.write(f"  <td><a href=\"{escape_html(rec.get('url', ''))}\" target=\"_blank\">{escape_html(rec.get('login', ''))}</a></td>\n")
            website = rec.get('websiteUrl', '')
            if website:
                href = website if website.startswith(('https://', 'http://')) else f'https://{website}'
                f.write(f"  <td><a href=\"{escape_html(href)}\" target=\"_blank\">{escape_html(website)}</a></td>\n")
            else:
                f.write("  <td></td>\n")
            f.write("</tr>\n")
        f.write("""</tbody>
</table>
</body>
</html>
""")


def main() -> None:
    args = parse_args()

    print(f"[merge] Scanning {args.input_dir} for result_*.jsonl files ...")
    records, failed_chunks, all_errors = merge(args.input_dir)

    # ── Write output ──────────────────────────────────────────────────────────
    output_files = []
    if args.both:
        # Generate both CSV and HTML with base name
        base_name = args.output
        # Remove extension if present
        if base_name.endswith(('.csv', '.html')):
            base_name = base_name.rsplit('.', 1)[0]
        csv_path = f"{base_name}.csv"
        html_path = f"{base_name}.html"
        write_csv(records, csv_path)
        write_html(records, html_path)
        output_files = [csv_path, html_path]
    elif args.html:
        write_html(records, args.output)
        output_files = [args.output]
    else:
        write_csv(records, args.output)
        output_files = [args.output]

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n========== Merge Summary ==========")
    if args.total_users is not None:
        print(f"Total users fetched    : {args.total_users}")
    print(f"Target-region users    : {len(records)}")
    for output_file in output_files:
        print(f"Output file            : {os.path.abspath(output_file)}")

    if failed_chunks:
        print(f"\n⚠  Failed chunks ({len(failed_chunks)}) — results may be incomplete:")
        for c in failed_chunks:
            print(f"   • {c}")

    if all_errors:
        print(f"\n⚠  Parse errors ({len(all_errors)}):")
        for e in all_errors[:20]:          # cap output to avoid flooding terminal
            print(f"   {e}")
        if len(all_errors) > 20:
            print(f"   ... and {len(all_errors) - 20} more")

    if not failed_chunks and not all_errors:
        print("✓  All chunks merged successfully.")
    print("====================================\n")


if __name__ == "__main__":
    main()
