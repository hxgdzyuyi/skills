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
MIN_HUGO_VERSION = (0, 162, 0)
MIN_HUGO_VERSION_TEXT = ".".join(str(part) for part in MIN_HUGO_VERSION)

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PLUGIN_ROOT / "assets" / "hugo-template"

REQUIRED_FILES = (
    Path(".gitignore"),
    Path("AGENTS.md"),
    Path("hugo.toml"),
    Path("archetypes/wechat.html"),
    Path("content/_index.md"),
    Path("layouts/wechat/baseof.html"),
    Path("layouts/wechat/single.html"),
    Path("layouts/wechat/home.html"),
    Path("layouts/partials/wechat/copy-button.html"),
    Path("assets/css/wechat-preview.css"),
    Path("assets/css/mp-article-index.css"),
    Path("assets/js/wechat-copy.js"),
    Path("static/static/weui.min.css"),
    Path("static/static/tencent_portfolio_light.mnicjuz14bbf866e.css"),
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

AGENTS_PATH = Path("AGENTS.md")
AGENTS_MARKER_BEGIN = "<!-- mp-article:begin -->"
AGENTS_MARKER_END = "<!-- mp-article:end -->"
GITIGNORE_PATH = Path(".gitignore")
GITIGNORE_MARKER_BEGIN = "# mp-article:begin"
GITIGNORE_MARKER_END = "# mp-article:end"
BASE_LAYOUT_PATH = Path("layouts/wechat/baseof.html")
WECHAT_ARCHETYPE_PATH = Path("archetypes/wechat.html")
LEGACY_CONTENT_ROOT = Path("content/wechat")
LEGACY_PREVIEW_SIGNATURES = {
    Path("layouts/wechat/baseof.html"): (
        747,
        ('<body>', 'resources.Get "css/wechat-preview.css"', 'partial "wechat/copy-button.html"'),
    ),
    Path("layouts/wechat/single.html"): (
        988,
        ('class="wechat-preview"', 'class="wechat-article-shell"', ".RawContent | safeHTML"),
    ),
    Path("layouts/partials/wechat/copy-button.html"): (
        273,
        ('class="wechat-copy-tools"', 'id="mp-copy-button"', 'id="mp-copy-status"'),
    ),
    Path("assets/css/wechat-preview.css"): (
        3503,
        (".wechat-preview", ".wechat-article-shell", ".wechat-copy-tools"),
    ),
}

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKER_RE = re.compile(
    r"(?ms)^\s*\[params\.mpArticle\]\s*$"
    r"(?P<body>.*?)(?=^\s*\[[^\]]+\]\s*$|\Z)"
)
TABLE_RE = re.compile(r"(?m)^[ \t]*\[[^\]\r\n]+\][ \t]*(?:#.*)?$")
TOP_LEVEL_LANGUAGE_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)languageCode(?P<rest>[ \t]*=[^\r\n]*)"
    r"(?P<newline>\r?\n|$)"
)
TOP_LEVEL_LOCALE_RE = re.compile(
    r"(?m)^[ \t]*locale[ \t]*=[^\r\n]*(?:\r?\n|$)"
)
DISABLE_KINDS_RE = re.compile(
    r"(?m)^(?P<prefix>[ \t]*disableKinds[ \t]*=[ \t]*)"
    r"\[(?P<items>[^\]\r\n]*)\](?P<suffix>[ \t]*(?:#.*)?)$"
)
SECURITY_RE = re.compile(
    r"(?ms)^[ \t]*\[security\][ \t]*(?:#.*)?$"
    r"(?P<body>.*?)(?=^[ \t]*\[[^\]\r\n]+\][ \t]*(?:#.*)?$|\Z)"
)
ALLOW_CONTENT_RE = re.compile(
    r"(?m)^[ \t]*allowContent[ \t]*=[ \t]*(?P<value>[^\r\n]*)$"
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


def parse_hugo_version(output: str) -> Optional[Tuple[int, int, int]]:
    match = re.search(r"\bv(\d+)\.(\d+)\.(\d+)", output)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def split_top_level(config_text: str) -> Tuple[str, str]:
    first_table = TABLE_RE.search(config_text)
    if not first_table:
        return config_text, ""
    return config_text[: first_table.start()], config_text[first_table.start() :]


def language_config_state(config_text: str) -> Tuple[str, str]:
    top_level, _ = split_top_level(config_text)
    language_matches = list(TOP_LEVEL_LANGUAGE_RE.finditer(top_level))
    locale_matches = list(TOP_LEVEL_LOCALE_RE.finditer(top_level))
    if len(language_matches) > 1 or len(locale_matches) > 1:
        return "conflict", "hugo.toml 中存在重复的顶层 locale 或 languageCode"
    if language_matches:
        return "deprecated", "hugo.toml 仍使用已弃用的顶层 languageCode"
    if not locale_matches:
        return "missing", "hugo.toml 缺少顶层 locale"
    return "valid", ""


def security_config_state(config_text: str) -> Tuple[str, str]:
    matches = list(SECURITY_RE.finditer(config_text))
    if not matches:
        return "missing", "hugo.toml 缺少允许公众号 HTML 正文的 security.allowContent"
    if len(matches) > 1:
        return "conflict", "hugo.toml 中存在多个 [security] 配置块"

    allow_matches = list(ALLOW_CONTENT_RE.finditer(matches[0].group("body")))
    if not allow_matches:
        return "missing", "hugo.toml 的 [security] 缺少 allowContent"
    if len(allow_matches) > 1:
        return "conflict", "hugo.toml 的 [security] 存在多个 allowContent"

    value = allow_matches[0].group("value")
    entries = [
        double_quoted or single_quoted
        for double_quoted, single_quoted in re.findall(
            r'"([^"]*)"|\'([^\']*)\'',
            value,
        )
    ]
    if "^text/html$" in entries and "!^text/html$" not in entries:
        return "valid", ""
    return (
        "conflict",
        "已有 security.allowContent 未精确允许 ^text/html$，为避免覆盖安全策略已停止",
    )


def home_kind_state(config_text: str) -> Tuple[str, str]:
    top_level, _ = split_top_level(config_text)
    matches = list(DISABLE_KINDS_RE.finditer(top_level))
    if len(matches) > 1:
        return "conflict", "hugo.toml 中存在多个顶层 disableKinds"
    if not matches:
        return "valid", ""
    values = [
        item.group("value")
        for item in re.finditer(
            r"(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
            matches[0].group("items"),
        )
    ]
    if "home" in values:
        return "disabled", "hugo.toml 的 disableKinds 禁用了首页"
    return "valid", ""


def append_toml_block(config_text: str, block: str) -> str:
    if not config_text:
        return block
    if config_text.endswith("\n\n"):
        return config_text + block
    if config_text.endswith("\n"):
        return config_text + "\n" + block
    return config_text + "\n\n" + block


def migrate_language_config(config_text: str) -> Tuple[str, str]:
    top_level, tables = split_top_level(config_text)
    language_match = TOP_LEVEL_LANGUAGE_RE.search(top_level)
    locale_match = TOP_LEVEL_LOCALE_RE.search(top_level)

    if language_match and locale_match:
        top_level = (
            top_level[: language_match.start()] + top_level[language_match.end() :]
        )
        return top_level + tables, "移除已弃用的顶层 languageCode"

    if language_match:
        key_start = language_match.start() + len(language_match.group("indent"))
        top_level = (
            top_level[:key_start]
            + "locale"
            + top_level[key_start + len("languageCode") :]
        )
        return top_level + tables, "将顶层 languageCode 迁移为 locale"

    separator = "" if not top_level or top_level.endswith("\n") else "\n"
    top_level = top_level + separator + 'locale = "zh-CN"\n'
    if tables and not top_level.endswith("\n\n"):
        top_level += "\n"
    return top_level + tables, "新增顶层 locale"


def add_security_allow_content(config_text: str) -> Tuple[str, str]:
    match = SECURITY_RE.search(config_text)
    if not match:
        return (
            append_toml_block(
                config_text,
                "[security]\nallowContent = ['^text/html$']\n",
            ),
            "新增 security.allowContent HTML 正文白名单",
        )

    body = match.group("body")
    if body.startswith("\r\n"):
        updated_body = "\r\nallowContent = ['^text/html$']\r\n" + body[2:]
    elif body.startswith("\n"):
        updated_body = "\nallowContent = ['^text/html$']\n" + body[1:]
    else:
        updated_body = "\nallowContent = ['^text/html$']\n" + body
    updated = (
        config_text[: match.start("body")]
        + updated_body
        + config_text[match.end("body") :]
    )
    return updated, "补充 [security].allowContent HTML 正文白名单"


def enable_home_kind(config_text: str) -> Tuple[str, str]:
    top_level, tables = split_top_level(config_text)
    match = DISABLE_KINDS_RE.search(top_level)
    if not match:
        return config_text, ""
    entries = [
        (item.group("quote"), item.group("value"))
        for item in re.finditer(
            r"(?P<quote>[\"'])(?P<value>[^\"']+)(?P=quote)",
            match.group("items"),
        )
        if item.group("value") != "home"
    ]
    values = ", ".join(f"{quote}{value}{quote}" for quote, value in entries)
    replacement = (
        match.group("prefix") + "[" + values + "]" + match.group("suffix")
    )
    top_level = top_level[: match.start()] + replacement + top_level[match.end() :]
    return top_level + tables, "从 disableKinds 移除 home"


def prepare_hugo_config(
    config_text: str,
) -> Tuple[Optional[str], list[str], list[str]]:
    conflicts: list[str] = []
    marker_status, marker_message = marker_state(config_text)
    language_status, language_message = language_config_state(config_text)
    security_status, security_message = security_config_state(config_text)
    home_status, home_message = home_kind_state(config_text)

    if marker_status == "conflict":
        conflicts.append(marker_message)
    if language_status == "conflict":
        conflicts.append(language_message)
    if security_status == "conflict":
        conflicts.append(security_message)
    if home_status == "conflict":
        conflicts.append(home_message)
    if conflicts:
        return None, [], conflicts

    updated = config_text
    changes: list[str] = []
    if language_status != "valid":
        updated, message = migrate_language_config(updated)
        changes.append(message)
    if security_status == "missing":
        updated, message = add_security_allow_content(updated)
        changes.append(message)
    if home_status == "disabled":
        updated, message = enable_home_kind(updated)
        changes.append(message)
    if marker_status == "missing":
        updated = append_toml_block(updated, MARKER)
        changes.append("追加 mpArticle 工程标记")
    return updated, changes, []


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


def agents_state(path: Path) -> Tuple[str, str]:
    if not path.exists():
        return "missing", "缺少 AGENTS.md"
    if not path.is_file():
        return "conflict", "AGENTS.md 不是普通文件"
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "conflict", "AGENTS.md 不是 UTF-8 文件"

    has_begin = AGENTS_MARKER_BEGIN in text
    has_end = AGENTS_MARKER_END in text
    if has_begin and has_end:
        return "valid", ""
    if has_begin or has_end:
        return "conflict", "AGENTS.md 中的 mp-article 标记不完整"
    return "missing", "AGENTS.md 未声明使用 mp-article 插件"


def gitignore_state(path: Path) -> Tuple[str, str]:
    if not path.exists():
        return "missing", "缺少 .gitignore"
    if not path.is_file():
        return "conflict", ".gitignore 不是普通文件"
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "conflict", ".gitignore 不是 UTF-8 文件"

    has_begin = GITIGNORE_MARKER_BEGIN in text
    has_end = GITIGNORE_MARKER_END in text
    if has_begin and has_end:
        return "valid", ""
    if has_begin or has_end:
        return "conflict", ".gitignore 中的 mp-article 标记不完整"
    return "missing", ".gitignore 未包含 mp-article 的 Hugo 忽略规则"


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
        config_text = config.read_text(encoding="utf-8")
        for state, message in (
            marker_state(config_text),
            language_config_state(config_text),
            security_config_state(config_text),
            home_kind_state(config_text),
        ):
            if state != "valid":
                findings.append(message)
    else:
        alternatives = [str(path) for path in ALTERNATIVE_CONFIGS if (root / path).exists()]
        if alternatives:
            findings.append(
                "项目使用非 hugo.toml 配置，安全模式不会自动迁移："
                + ", ".join(alternatives)
            )

    agents_status, agents_message = agents_state(root / AGENTS_PATH)
    if agents_status != "valid" and agents_message not in findings:
        findings.append(agents_message)

    gitignore_status, gitignore_message = gitignore_state(root / GITIGNORE_PATH)
    if gitignore_status != "valid" and gitignore_message not in findings:
        findings.append(gitignore_message)
    if (root / LEGACY_CONTENT_ROOT).exists():
        findings.append(
            "检测到旧版 content/wechat 文章目录，需要运行 init 迁移到 content/<slug>"
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


def is_legacy_base_layout(destination: Path, source: Path) -> bool:
    if not destination.is_file():
        return False
    try:
        existing = destination.read_text(encoding="utf-8")
        expected = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return existing.replace(
        ".Site.LanguageCode",
        ".Site.Language.Locale",
    ) == expected


def is_legacy_wechat_archetype(destination: Path, source: Path) -> bool:
    if not destination.is_file():
        return False
    try:
        existing = destination.read_text(encoding="utf-8")
        expected = source.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    normalized_existing = existing.replace("draft: true\n", "", 1)
    legacy_expected = expected.replace("type: wechat\n", "", 1)
    return normalized_existing == legacy_expected


def article_type_state(article: Path) -> Tuple[str, str]:
    try:
        text = article.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return "conflict", f"文章不是 UTF-8 文件：{article}"
    if not text.startswith("---\n"):
        return "conflict", f"文章缺少 YAML Front Matter：{article}"
    end = text.find("\n---", 4)
    if end < 0:
        return "conflict", f"文章 Front Matter 未闭合：{article}"
    type_match = re.search(
        r"(?m)^[ \t]*type[ \t]*:[ \t]*(.+?)[ \t]*$",
        text[4:end],
    )
    if not type_match:
        return "missing", ""
    value = type_match.group(1).strip().strip("\"'")
    if value == "wechat":
        return "valid", ""
    return "conflict", f"文章已有非 wechat 类型：{article}"


def legacy_content_conflicts(root: Path) -> list[str]:
    legacy_root = root / LEGACY_CONTENT_ROOT
    if not legacy_root.exists():
        return []
    if not legacy_root.is_dir():
        return ["旧版 content/wechat 不是目录"]

    conflicts: list[str] = []
    for entry in sorted(legacy_root.iterdir()):
        if entry.name == "_index.md":
            try:
                text = entry.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                conflicts.append("旧版 content/wechat/_index.md 不是 UTF-8 文件")
                continue
            normalized = text.replace('url: "/"\n', "", 1)
            if normalized != '---\ntitle: "公众号文章"\n---\n':
                conflicts.append(
                    "旧版 content/wechat/_index.md 已被自定义，无法自动移除"
                )
            continue
        if not entry.is_dir():
            conflicts.append(f"旧版文章目录包含未知文件：{entry}")
            continue
        article = entry / "index.html"
        if not article.is_file():
            conflicts.append(f"旧版文章 Bundle 缺少 index.html：{entry}")
            continue
        target = root / "content" / entry.name
        if target.exists():
            conflicts.append(f"根级文章目录已存在：{target}")
        state, message = article_type_state(article)
        if state == "conflict":
            conflicts.append(message)
    return conflicts


def add_wechat_type(article: Path) -> bool:
    state, _ = article_type_state(article)
    if state == "valid":
        return False
    text = article.read_text(encoding="utf-8")
    article.write_text("---\ntype: wechat\n" + text[4:], encoding="utf-8")
    return True


def migrate_legacy_content(root: Path) -> list[str]:
    legacy_root = root / LEGACY_CONTENT_ROOT
    if not legacy_root.is_dir():
        return []

    changes: list[str] = []
    legacy_index = legacy_root / "_index.md"
    if legacy_index.is_file():
        legacy_index.unlink()
        changes.append("移除旧版 content/wechat/_index.md")

    for entry in sorted(legacy_root.iterdir()):
        target = root / "content" / entry.name
        shutil.move(str(entry), str(target))
        article = target / "index.html"
        if add_wechat_type(article):
            changes.append(
                f"迁移 content/wechat/{entry.name} 到 content/{entry.name} 并补充 type"
            )
        else:
            changes.append(
                f"迁移 content/wechat/{entry.name} 到 content/{entry.name}"
            )
    legacy_root.rmdir()
    changes.append("移除空的 content/wechat 目录")
    return changes


def is_legacy_preview_template(relative: Path, destination: Path) -> bool:
    signature = LEGACY_PREVIEW_SIGNATURES.get(relative)
    if not signature or not destination.is_file():
        return False
    expected_size, required_fragments = signature
    if destination.stat().st_size != expected_size:
        return False
    try:
        text = destination.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    return all(fragment in text for fragment in required_fragments)


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
        _, _, config_conflicts = prepare_hugo_config(
            config.read_text(encoding="utf-8")
        )
        conflicts.extend(config_conflicts)

    conflicts.extend(legacy_content_conflicts(root))

    for relative, source in template_files():
        if relative in (Path("hugo.toml"), AGENTS_PATH, GITIGNORE_PATH):
            if relative == AGENTS_PATH:
                state, message = agents_state(root / relative)
                if state == "conflict":
                    conflicts.append(message)
            elif relative == GITIGNORE_PATH:
                state, message = gitignore_state(root / relative)
                if state == "conflict":
                    conflicts.append(message)
            continue
        destination = root / relative
        if destination.is_file() and destination.read_bytes() != source.read_bytes():
            is_safe_migration = (
                relative == BASE_LAYOUT_PATH
                and is_legacy_base_layout(destination, source)
            ) or (
                relative == WECHAT_ARCHETYPE_PATH
                and is_legacy_wechat_archetype(destination, source)
            ) or is_legacy_preview_template(
                relative,
                destination,
            )
            if not is_safe_migration:
                conflicts.append(f"文件冲突：{relative.as_posix()}")
        elif destination.exists() and not destination.is_file():
            conflicts.append(f"目标不是普通文件：{relative.as_posix()}")
    return conflicts


def install_template(root: Path) -> list[str]:
    changes: list[str] = []
    config = root / "hugo.toml"

    for relative, source in template_files():
        destination = root / relative
        if relative in (AGENTS_PATH, GITIGNORE_PATH):
            continue
        if relative == Path("hugo.toml") and config.exists():
            continue
        if is_legacy_preview_template(relative, destination):
            shutil.copy2(source, destination)
            changes.append(f"更新 {relative.as_posix()}：同步微信预览环境")
            continue
        if relative == BASE_LAYOUT_PATH and is_legacy_base_layout(destination, source):
            shutil.copy2(source, destination)
            changes.append(
                "更新 layouts/wechat/baseof.html：使用 Site.Language.Locale"
            )
            continue
        if relative == WECHAT_ARCHETYPE_PATH and is_legacy_wechat_archetype(
            destination,
            source,
        ):
            shutil.copy2(source, destination)
            changes.append("更新 archetypes/wechat.html：新文章默认参与构建")
            continue
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        changes.append(f"新增 {relative.as_posix()}")

    existing_config = config.read_text(encoding="utf-8")
    updated_config, config_changes, _ = prepare_hugo_config(existing_config)
    if updated_config is not None and updated_config != existing_config:
        config.write_text(updated_config, encoding="utf-8")
        changes.extend(f"更新 hugo.toml：{change}" for change in config_changes)

    agents = root / AGENTS_PATH
    agents_template = TEMPLATE_ROOT / AGENTS_PATH
    agents_status, _ = agents_state(agents)
    if agents_status == "missing":
        block = agents_template.read_text(encoding="utf-8").strip()
        if agents.exists():
            existing = agents.read_text(encoding="utf-8")
            separator = "" if not existing else ("\n" if existing.endswith("\n") else "\n\n")
            agents.write_text(existing + separator + block + "\n", encoding="utf-8")
            changes.append("更新 AGENTS.md：追加 mp-article 工程说明")
        else:
            shutil.copy2(agents_template, agents)
            changes.append("新增 AGENTS.md")

    gitignore = root / GITIGNORE_PATH
    gitignore_template = TEMPLATE_ROOT / GITIGNORE_PATH
    gitignore_status, _ = gitignore_state(gitignore)
    if gitignore_status == "missing":
        block = gitignore_template.read_text(encoding="utf-8").strip()
        if gitignore.exists():
            existing = gitignore.read_text(encoding="utf-8")
            separator = "" if not existing else ("\n" if existing.endswith("\n") else "\n\n")
            gitignore.write_text(existing + separator + block + "\n", encoding="utf-8")
            changes.append("更新 .gitignore：追加 Hugo 忽略规则")
        else:
            shutil.copy2(gitignore_template, gitignore)
            changes.append("新增 .gitignore")
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

    changes = migrate_legacy_content(root)
    changes.extend(install_template(root))
    return True, changes


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

    article_dir = root / "content" / slug
    if article_dir.exists():
        return False, f"文章目录已存在：{article_dir}"

    article_dir.mkdir(parents=True)
    (article_dir / "assets").mkdir()
    timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    content = f"""---
title: "{quote_yaml(title)}"
type: wechat
date: {timestamp}
description: ""
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
    parsed_version = parse_hugo_version(version_output)
    if parsed_version is None:
        print(f"无法识别 Hugo 版本：{version_output}", file=sys.stderr)
        return EXIT_ERROR
    if parsed_version < MIN_HUGO_VERSION:
        print(
            f"mp-article 要求 Hugo v{MIN_HUGO_VERSION_TEXT} 或更高版本；"
            f"当前为 v{'.'.join(str(part) for part in parsed_version)}。",
            file=sys.stderr,
        )
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
