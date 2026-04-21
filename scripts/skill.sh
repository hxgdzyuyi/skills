#!/usr/bin/env bash
set -euo pipefail

# Install or uninstall a skill from this repo into a global skills directory.
#
# Usage:
#   scripts/skill.sh install   <codex|claude> <skill-name>
#   scripts/skill.sh uninstall <codex|claude> <skill-name>
#   scripts/skill.sh list      <codex|claude>
#
# Install creates a symlink so edits in the repo take effect immediately.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_SRC="$REPO_ROOT/skills"

usage() {
    cat <<EOF
Usage:
  $(basename "$0") install   <codex|claude> <skill-name>
  $(basename "$0") uninstall <codex|claude> <skill-name>
  $(basename "$0") list      <codex|claude>
EOF
    exit 1
}

target_dir() {
    case "$1" in
        codex)  echo "$HOME/.agents/skills" ;;
        claude) echo "$HOME/.claude/skills" ;;
        *) echo "Unknown target: $1 (expected codex|claude)" >&2; exit 1 ;;
    esac
}

cmd_install() {
    local target="$1" name="$2"
    local src="$SKILLS_SRC/$name"
    local dst_dir; dst_dir="$(target_dir "$target")"
    local dst="$dst_dir/$name"

    [[ -d "$src" ]] || { echo "Skill not found: $src" >&2; exit 1; }
    [[ -f "$src/SKILL.md" ]] || { echo "Missing SKILL.md in $src" >&2; exit 1; }

    mkdir -p "$dst_dir"

    if [[ -e "$dst" || -L "$dst" ]]; then
        echo "Already exists: $dst" >&2
        echo "Run uninstall first if you want to replace it." >&2
        exit 1
    fi

    ln -s "$src" "$dst"
    echo "Installed: $dst -> $src"
}

cmd_uninstall() {
    local target="$1" name="$2"
    local dst_dir; dst_dir="$(target_dir "$target")"
    local dst="$dst_dir/$name"

    if [[ ! -e "$dst" && ! -L "$dst" ]]; then
        echo "Not installed: $dst" >&2
        exit 1
    fi

    if [[ -L "$dst" ]]; then
        rm "$dst"
        echo "Removed symlink: $dst"
    else
        echo "Refusing to remove non-symlink: $dst" >&2
        echo "Delete it manually if you really want to." >&2
        exit 1
    fi
}

cmd_list() {
    local target="$1"
    local dst_dir; dst_dir="$(target_dir "$target")"
    [[ -d "$dst_dir" ]] || { echo "(empty) $dst_dir does not exist"; return; }
    ls -la "$dst_dir"
}

[[ $# -ge 1 ]] || usage
action="$1"; shift

case "$action" in
    install)   [[ $# -eq 2 ]] || usage; cmd_install "$1" "$2" ;;
    uninstall) [[ $# -eq 2 ]] || usage; cmd_uninstall "$1" "$2" ;;
    list)      [[ $# -eq 1 ]] || usage; cmd_list "$1" ;;
    *) usage ;;
esac
