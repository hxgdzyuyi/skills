#!/usr/bin/env bash
set -euo pipefail

# Install or uninstall a skill from this repo into a skills directory.
#
# Usage:
#   scripts/skill.sh install   <codex|claude> <skill-name> [-p <project-dir>] [-c]
#   scripts/skill.sh uninstall <codex|claude> <skill-name> [-p <project-dir>]
#   scripts/skill.sh list      <codex|claude>              [-p <project-dir>]
#
# Without -p, installs into the global skills directory:
#   codex  -> ~/.agents/skills
#   claude -> ~/.claude/skills
# With -p <project-dir>, installs into that project instead:
#   codex  -> <project-dir>/.agents/skills
#   claude -> <project-dir>/.claude/skills
#
# By default install creates a symlink so edits in the repo take effect
# immediately. Pass -c|--copy to copy the skill directory instead.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_SRC="$REPO_ROOT/skills"

usage() {
    cat <<EOF
Usage:
  $(basename "$0") install   <codex|claude> <skill-name> [-p <project-dir>] [-c]
  $(basename "$0") uninstall <codex|claude> <skill-name> [-p <project-dir>]
  $(basename "$0") list      <codex|claude>              [-p <project-dir>]

Without -p, installs into the global skills directory (~/.agents/skills or
~/.claude/skills). With -p <project-dir>, installs into that project's
.agents/skills or .claude/skills directory instead.

By default install creates a symlink. Pass -c|--copy to copy the skill
directory instead of symlinking it.
EOF
    exit 1
}

# target_dir <codex|claude> [project-dir]
target_dir() {
    local target="$1" project="${2:-}"
    local sub
    case "$target" in
        codex)  sub=".agents/skills" ;;
        claude) sub=".claude/skills" ;;
        *) echo "Unknown target: $target (expected codex|claude)" >&2; exit 1 ;;
    esac

    if [[ -n "$project" ]]; then
        [[ -d "$project" ]] || { echo "Project directory not found: $project" >&2; exit 1; }
        echo "$(cd "$project" && pwd)/$sub"
    else
        echo "$HOME/$sub"
    fi
}

cmd_install() {
    local target="$1" name="$2" project="${3:-}" copy="${4:-}"
    local src="$SKILLS_SRC/$name"
    local dst_dir; dst_dir="$(target_dir "$target" "$project")"
    local dst="$dst_dir/$name"

    [[ -d "$src" ]] || { echo "Skill not found: $src" >&2; exit 1; }
    [[ -f "$src/SKILL.md" ]] || { echo "Missing SKILL.md in $src" >&2; exit 1; }

    mkdir -p "$dst_dir"

    if [[ -e "$dst" || -L "$dst" ]]; then
        echo "Already exists: $dst" >&2
        echo "Run uninstall first if you want to replace it." >&2
        exit 1
    fi

    if [[ -n "$copy" ]]; then
        cp -R "$src" "$dst"
        echo "Installed (copy): $dst"
    else
        ln -s "$src" "$dst"
        echo "Installed: $dst -> $src"
    fi
}

cmd_uninstall() {
    local target="$1" name="$2" project="${3:-}"
    local dst_dir; dst_dir="$(target_dir "$target" "$project")"
    local dst="$dst_dir/$name"

    if [[ ! -e "$dst" && ! -L "$dst" ]]; then
        echo "Not installed: $dst" >&2
        exit 1
    fi

    if [[ -L "$dst" ]]; then
        rm "$dst"
        echo "Removed symlink: $dst"
    elif [[ -d "$dst" && -f "$dst/SKILL.md" ]]; then
        rm -rf "$dst"
        echo "Removed copy: $dst"
    else
        echo "Refusing to remove non-symlink: $dst" >&2
        echo "Delete it manually if you really want to." >&2
        exit 1
    fi
}

cmd_list() {
    local target="$1" project="${2:-}"
    local dst_dir; dst_dir="$(target_dir "$target" "$project")"
    [[ -d "$dst_dir" ]] || { echo "(empty) $dst_dir does not exist"; return; }
    ls -la "$dst_dir"
}

[[ $# -ge 1 ]] || usage
action="$1"; shift

# Parse a trailing/embedded -p|--project <dir> and -c|--copy option;
# collect the rest as positionals.
project=""
copy=""
positional=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--project)
            [[ $# -ge 2 ]] || usage
            project="$2"; shift 2 ;;
        -c|--copy)
            copy="1"; shift ;;
        *)
            positional+=("$1"); shift ;;
    esac
done
set -- "${positional[@]+"${positional[@]}"}"

case "$action" in
    install)   [[ $# -eq 2 ]] || usage; cmd_install "$1" "$2" "$project" "$copy" ;;
    uninstall) [[ $# -eq 2 ]] || usage; cmd_uninstall "$1" "$2" "$project" ;;
    list)      [[ $# -eq 1 ]] || usage; cmd_list "$1" "$project" ;;
    *) usage ;;
esac
