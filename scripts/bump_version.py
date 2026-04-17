#!/usr/bin/env python3
"""Write the version from VERSION into every manifest that needs it.

Idempotent — running twice is a no-op. Uses regex over raw text so
formatting stays stable (no JSON/TOML reserialization).

Usage:
    # Set a new version and propagate:
    echo "1.2.0" > VERSION
    python scripts/bump_version.py

    # Or via make:
    make version NEW=1.2.0
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent


@dataclass
class VersionFile:
    path: Path
    pattern: re.Pattern[str]
    rewrite: Callable[[re.Match[str], str], str]
    label: str


def _quoted_string(match: re.Match[str], new: str) -> str:
    # Keeps the surrounding prefix (e.g. `version = "`) and closing quote.
    return f"{match.group(1)}{new}{match.group(3)}"


def _pyproject_version(match: re.Match[str], new: str) -> str:
    # pyproject.toml: version = "1.0.0"
    return f'version = "{new}"'


FILES: list[VersionFile] = [
    VersionFile(
        path=REPO / "pyproject.toml",
        pattern=re.compile(r'^version\s*=\s*"[^"]*"', re.MULTILINE),
        rewrite=lambda m, v: f'version = "{v}"',
        label="pyproject.toml",
    ),
    VersionFile(
        path=REPO / "extensions" / "chrome" / "manifest.json",
        pattern=re.compile(r'("version"\s*:\s*")([^"]*)(")'),
        rewrite=_quoted_string,
        label="extensions/chrome/manifest.json",
    ),
    VersionFile(
        path=REPO / "extensions" / "firefox" / "manifest.json",
        pattern=re.compile(r'("version"\s*:\s*")([^"]*)(")'),
        rewrite=_quoted_string,
        label="extensions/firefox/manifest.json",
    ),
    VersionFile(
        path=REPO / "apps" / "desktop" / "package.json",
        pattern=re.compile(r'("version"\s*:\s*")([^"]*)(")'),
        rewrite=_quoted_string,
        label="apps/desktop/package.json",
    ),
    VersionFile(
        path=REPO / "apps" / "desktop" / "src-tauri" / "tauri.conf.json",
        pattern=re.compile(r'("version"\s*:\s*")([^"]*)(")'),
        rewrite=_quoted_string,
        label="apps/desktop/src-tauri/tauri.conf.json",
    ),
    VersionFile(
        path=REPO / "apps" / "desktop" / "src-tauri" / "Cargo.toml",
        pattern=re.compile(r'^(version\s*=\s*")([^"]*)(")', re.MULTILINE),
        rewrite=_quoted_string,
        label="apps/desktop/src-tauri/Cargo.toml",
    ),
    VersionFile(
        path=REPO / "apps" / "pdf-viewer" / "package.json",
        pattern=re.compile(r'("version"\s*:\s*")([^"]*)(")'),
        rewrite=_quoted_string,
        label="apps/pdf-viewer/package.json",
    ),
    VersionFile(
        path=REPO / "apps" / "pdf-viewer" / "src-tauri" / "tauri.conf.json",
        pattern=re.compile(r'("version"\s*:\s*")([^"]*)(")'),
        rewrite=_quoted_string,
        label="apps/pdf-viewer/src-tauri/tauri.conf.json",
    ),
    VersionFile(
        path=REPO / "apps" / "pdf-viewer" / "src-tauri" / "Cargo.toml",
        pattern=re.compile(r'^(version\s*=\s*")([^"]*)(")', re.MULTILINE),
        rewrite=_quoted_string,
        label="apps/pdf-viewer/src-tauri/Cargo.toml",
    ),
]


def read_version() -> str:
    raw = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    if not raw:
        print("VERSION file is empty", file=sys.stderr)
        sys.exit(2)
    if not re.match(r"^\d+\.\d+\.\d+", raw):
        print(f"VERSION '{raw}' does not look like semver", file=sys.stderr)
        sys.exit(2)
    return raw


def apply(v: str) -> list[str]:
    touched: list[str] = []
    for vf in FILES:
        if not vf.path.exists():
            print(f"skip (missing): {vf.label}")
            continue
        original = vf.path.read_text(encoding="utf-8")
        new = vf.pattern.sub(lambda m: vf.rewrite(m, v), original, count=1)
        if new == original:
            continue
        vf.path.write_text(new, encoding="utf-8")
        touched.append(vf.label)
    return touched


def main() -> int:
    v = read_version()
    changed = apply(v)
    if not changed:
        print(f"already at {v}")
        return 0
    print(f"bumped to {v}:")
    for label in changed:
        print(f"  {label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
