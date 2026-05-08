#!/usr/bin/env python3
"""
Refresh inspekt/data/google_fonts.json from the Google Fonts public metadata API.

Usage:
    python scripts/update_google_fonts.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

METADATA_URL = "https://fonts.google.com/metadata/fonts"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "inspekt" / "data" / "google_fonts.json"


def main() -> None:
    # Fetch metadata
    req = urllib.request.Request(METADATA_URL, headers={"User-Agent": "inspekt/update-google-fonts"})
    with urllib.request.urlopen(req) as resp:
        raw = resp.read().decode("utf-8")

    # Google prefixes the JSON with )]}'
    if raw.startswith(")]}'"):
        raw = raw[raw.index("\n") + 1 :]

    data = json.loads(raw)
    families = sorted(f["family"] for f in data["familyMetadataList"])

    # Load existing for diff
    old: list[str] = []
    if OUTPUT_PATH.exists():
        with open(OUTPUT_PATH) as f:
            old = json.load(f)

    # Write
    with open(OUTPUT_PATH, "w") as f:
        json.dump(families, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Stats
    added = set(families) - set(old)
    removed = set(old) - set(families)
    print(f"Total font families: {len(families)}")
    if added:
        print(f"  + {len(added)} new: {', '.join(sorted(added)[:10])}{'…' if len(added) > 10 else ''}")
    if removed:
        print(f"  - {len(removed)} removed: {', '.join(sorted(removed)[:10])}{'…' if len(removed) > 10 else ''}")
    if not added and not removed:
        print("  No changes.")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
