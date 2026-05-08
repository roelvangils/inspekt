#!/usr/bin/env python3
"""One-shot replacement of prose `...` with `…` across tracked text files.

Only matches `...` immediately followed by a closing quote (`"` or `'`) or
a backtick — a strong signal of end-of-string prose. This avoids touching
JS/TS spread operators (`...args`, `[...arr]`), Python unpacking, regex
patterns, and type hints.

Run, review `git diff`, commit, then delete this file.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", "target", "dist", ".venv", "__pycache__", ".cache", "vendor"}
SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
    ".mp4", ".webm", ".woff", ".woff2", ".ttf", ".otf", ".db",
    ".so", ".dylib", ".pyc", ".o", ".a", ".lock",
}

# `...` immediately followed by a string terminator character.
PATTERN = re.compile(r"\.\.\.(?=[\"'`])")


def iter_files():
    result = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"],
        check=True, capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        p = REPO / line
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIXES:
            continue
        yield p


def main() -> int:
    changed = []
    for p in iter_files():
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        new = PATTERN.sub("…", text)
        if new != text:
            p.write_text(new, encoding="utf-8")
            changed.append(p.relative_to(REPO))
    if not changed:
        print("no changes")
        return 0
    print(f"rewrote {len(changed)} file(s):")
    for p in sorted(changed):
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
