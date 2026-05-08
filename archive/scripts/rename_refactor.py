#!/usr/bin/env python3
"""One-shot rewriter for the folder-rename refactor.

Rewrites every occurrence of the old path strings in every tracked text
file (except .git/, node_modules/, target/, dist/) to the new paths.

Run once, review `git diff`, commit. This script may be deleted afterwards.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Ordered: longer/more-specific strings first so shorter ones don't eat them.
REPLACEMENTS: list[tuple[str, str]] = [
    ("docker/browser-vm", "vm"),
    ("docker/headless", "vm/variants/headless"),
    ("desktop-vm", "apps/desktop"),
    ("desktop-pdf", "apps/pdf-viewer"),
    ("message-bridge.js", "main-world-bridge.js"),
    ("message-bridge", "main-world-bridge"),
]

SKIP_DIRS = {".git", "node_modules", "target", "dist", ".venv", "__pycache__", ".cache"}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".mp4", ".webm", ".woff", ".woff2", ".ttf", ".otf", ".db",
    ".so", ".dylib", ".pyc", ".o", ".a",
}


def iter_tracked_text_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"],
        check=True, capture_output=True, text=True,
    )
    files: list[Path] = []
    for line in result.stdout.splitlines():
        p = REPO / line
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIXES:
            continue
        files.append(p)
    return files


def rewrite(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False
    new = text
    for old, new_s in REPLACEMENTS:
        new = new.replace(old, new_s)
    if new == text:
        return False
    path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    changed: list[Path] = []
    for path in iter_tracked_text_files():
        if rewrite(path):
            changed.append(path.relative_to(REPO))
    if not changed:
        print("no changes")
        return 0
    print(f"rewrote {len(changed)} file(s):")
    for p in sorted(changed):
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
