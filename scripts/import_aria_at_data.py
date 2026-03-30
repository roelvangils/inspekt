#!/usr/bin/env python3
"""
Import, validate, and sync screen reader data from external sources.

Sources:
  - a11ysupport.io: Actual SR output strings per role/property/browser
  - W3C ARIA-AT: Keyboard commands, assertions, and test results

Usage:
  python scripts/import_aria_at_data.py --check        # Validate local data
  python scripts/import_aria_at_data.py --coverage      # Check role coverage
  python scripts/import_aria_at_data.py --list-roles    # List remote roles
  python scripts/import_aria_at_data.py --show-output ROLE  # Show SR output for a role
  python scripts/import_aria_at_data.py --sync          # Sync with upstream (diff + update)
  python scripts/import_aria_at_data.py --sync --dry-run  # Show what would change
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "inspekt" / "data" / "screen-reader-rules"

# GitHub raw content URLs
A11Y_SUPPORT_BASE = "https://raw.githubusercontent.com/accessibilitysupported/a11ysupport.io/master/data"

# GitHub API for directory listing
A11Y_SUPPORT_API_ARIA = "https://api.github.com/repos/accessibilitysupported/a11ysupport.io/contents/data/tech/aria"
A11Y_SUPPORT_API_TESTS = "https://api.github.com/repos/accessibilitysupported/a11ysupport.io/contents/data/tests/tech/aria"

# Screen readers we care about
TARGET_SRS = {"jaws", "nvda", "voiceover_macos"}
SR_KEY_MAP = {
    "jaws": "jaws",
    "nvda": "nvda",
    "vo_macos": "voiceover",
    "voiceover_macos": "voiceover",
}


def fetch_json(url: str) -> dict | list | None:
    """Fetch JSON from a URL, return None on error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "inspekt-sr-import/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError) as e:
        print(f"  Warning: Could not fetch {url}: {e}", file=sys.stderr)
        return None


def load_local(filename: str) -> dict:
    """Load a local JSON data file."""
    path = DATA_DIR / filename
    with open(path) as f:
        return json.load(f)


def save_local(filename: str, data: dict) -> None:
    """Save a JSON data file with pretty formatting."""
    path = DATA_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"  Saved: {path}")


# ── Directory Listing ─────────────────────────────────────────


def list_remote_roles() -> list[str]:
    """List all ARIA role files from a11ysupport.io."""
    print("Fetching role list from a11ysupport.io...")
    data = fetch_json(A11Y_SUPPORT_API_ARIA)
    if not data:
        print("  Error: Could not fetch directory listing", file=sys.stderr)
        return []

    roles = []
    for item in data:
        name = item.get("name", "")
        if name.endswith("_role.json"):
            role = name.replace("_role.json", "")
            roles.append(role)

    roles.sort()
    return roles


def list_remote_test_files() -> list[str]:
    """List all test result files from a11ysupport.io."""
    data = fetch_json(A11Y_SUPPORT_API_TESTS)
    if not data:
        return []
    return [item["name"] for item in data if item["name"].endswith(".json")]


# ── Validation ────────────────────────────────────────────────


def check_coverage():
    """Compare our announcements.json coverage against a11ysupport.io roles."""
    print("\n=== Coverage Check ===\n")

    announcements = load_local("announcements.json")
    our_roles = {k for k in announcements.keys() if not k.startswith("_")}
    remote_roles = set(list_remote_roles())

    covered = our_roles & remote_roles
    missing = remote_roles - our_roles
    extra = our_roles - remote_roles

    print(f"\n  Our roles:        {len(our_roles)}")
    print(f"  a11ysupport.io:   {len(remote_roles)}")
    print(f"  Covered:          {len(covered)}")
    print(f"  Missing from us:  {len(missing)}")
    print(f"  Extra in ours:    {len(extra)}")

    if missing:
        print(f"\n  Missing roles:")
        for role in sorted(missing):
            print(f"    - {role}")

    if extra:
        print(f"\n  Extra roles (ours only):")
        for role in sorted(extra):
            print(f"    - {role}")

    if remote_roles:
        pct = len(covered) / len(remote_roles) * 100
        print(f"\n  Coverage: {pct:.0f}%")

    return len(missing) == 0


def validate_announcements():
    """Validate that all announcement templates have required fields."""
    print("\n=== Announcement Validation ===\n")

    announcements = load_local("announcements.json")
    errors = 0
    warnings = 0

    for role, data in announcements.items():
        if role.startswith("_"):
            continue

        for sr in ["jaws", "nvda", "voiceover"]:
            if sr not in data:
                print(f"  ERROR: {role} missing screen reader '{sr}'")
                errors += 1
                continue

            sr_data = data[sr]
            if "enter" not in sr_data:
                print(f"  ERROR: {role}.{sr} missing 'enter' template")
                errors += 1

            enter = sr_data.get("enter", "")
            if "{name}" not in enter and role not in ("separator", "none", "presentation", "paragraph"):
                print(f"  WARNING: {role}.{sr}.enter does not use {{name}} placeholder")
                warnings += 1

    print(f"\n  Roles checked: {sum(1 for k in announcements if not k.startswith('_'))}")
    print(f"  Errors: {errors}")
    print(f"  Warnings: {warnings}")
    return errors == 0


def validate_keyboard_commands():
    """Validate keyboard commands structure."""
    print("\n=== Keyboard Commands Validation ===\n")

    commands = load_local("keyboard-commands.json")
    errors = 0

    for sr in ["jaws", "nvda", "voiceover"]:
        if sr not in commands:
            print(f"  ERROR: Missing screen reader '{sr}'")
            errors += 1
            continue

        sr_data = commands[sr]
        modes = [k for k in sr_data.keys() if not k.startswith("_")]
        for mode in modes:
            mode_data = sr_data[mode]
            if isinstance(mode_data, dict):
                categories = [k for k in mode_data.keys() if not k.startswith("_")]
                total_commands = sum(
                    len(mode_data[cat]) for cat in categories if isinstance(mode_data[cat], dict)
                )
                print(f"  {sr}/{mode}: {total_commands} commands in {len(categories)} categories")

    print(f"\n  Errors: {errors}")
    return errors == 0


# ── Fetch Test Results ────────────────────────────────────────


def fetch_test_result(test_name: str) -> dict | None:
    """Fetch a single test result file from a11ysupport.io."""
    url = f"{A11Y_SUPPORT_BASE}/tests/tech/aria/{test_name}"
    return fetch_json(url)


def extract_failures_from_test(test_data: dict) -> list[dict]:
    """Extract failure entries from an a11ysupport.io test result file.

    Returns list of:
      { screen_reader, browser, assertion_id, result, output, test_id }
    """
    failures = []
    commands = test_data.get("commands", {})

    for at_key, browsers in commands.items():
        sr_key = SR_KEY_MAP.get(at_key)
        if not sr_key:
            continue

        for browser, entries in browsers.items():
            for entry in entries:
                results = entry.get("results", [])
                for r in results:
                    if r.get("result") == "fail":
                        failures.append({
                            "screen_reader": sr_key,
                            "browser": browser,
                            "assertion_id": r.get("feature_assertion_id", ""),
                            "feature_id": r.get("feature_id", ""),
                            "output": entry.get("output", ""),
                            "test_file": test_data.get("id", ""),
                        })
    return failures


def extract_sr_outputs_from_test(test_data: dict) -> list[dict]:
    """Extract actual SR output strings from a test result file.

    Returns list of:
      { screen_reader, browser, output, assertion_id }
    """
    outputs = []
    commands = test_data.get("commands", {})

    for at_key, browsers in commands.items():
        sr_key = SR_KEY_MAP.get(at_key)
        if not sr_key:
            continue

        for browser, entries in browsers.items():
            for entry in entries:
                output = entry.get("output", "")
                if output:
                    outputs.append({
                        "screen_reader": sr_key,
                        "browser": browser,
                        "output": output,
                    })
    return outputs


# ── Show SR Output ────────────────────────────────────────────


def show_sr_output_for_role(role: str):
    """Show actual screen reader outputs from a11ysupport.io for a given role."""
    print(f"\n=== SR Output for role='{role}' ===\n")

    for suffix in ["-role-unnamed", "-role-named", "-role"]:
        test_name = role.replace("_", "-") + suffix + ".json"
        data = fetch_test_result(test_name)
        if data:
            print(f"  Source: {test_name}")
            commands = data.get("commands", {})
            for at_key, browsers in commands.items():
                sr_key = SR_KEY_MAP.get(at_key, at_key)
                for browser, entries in browsers.items():
                    for entry in entries:
                        output = entry.get("output", "")
                        if output:
                            print(f"  {sr_key:12s} + {browser:8s}: {output[:100]}")
            return

    print(f"  No test data found for role '{role}'")


# ── Sync Logic ────────────────────────────────────────────────


class SyncReport:
    """Collects sync diff results."""

    def __init__(self):
        self.new_bug_candidates: list[dict] = []
        self.potentially_fixed: list[dict] = []
        self.new_roles: list[str] = []
        self.changes_made = False

    def has_changes(self) -> bool:
        return bool(self.new_bug_candidates or self.potentially_fixed or self.new_roles)

    def print_summary(self):
        print("\n=== Sync Report ===\n")

        if not self.has_changes():
            print("  No changes detected. Everything is up to date.")
            return

        if self.new_bug_candidates:
            print(f"  NEW BUG CANDIDATES ({len(self.new_bug_candidates)}):")
            for bug in self.new_bug_candidates:
                print(f"    - {bug['screen_reader']} + {bug['browser']}: "
                      f"{bug['feature_id']} / {bug['assertion_id']}")
                if bug.get("output"):
                    print(f"      Output: {bug['output'][:80]}")
            print()

        if self.potentially_fixed:
            print(f"  POTENTIALLY FIXED ({len(self.potentially_fixed)}):")
            for bug in self.potentially_fixed:
                print(f"    - {bug['id']}: {bug['description'][:60]}…")
            print()

        if self.new_roles:
            print(f"  NEW ROLES ({len(self.new_roles)}):")
            for role in self.new_roles:
                print(f"    - {role}")
            print()


def sync_known_bugs(dry_run: bool = False) -> SyncReport:
    """Sync known-bugs.json with a11ysupport.io test results.

    1. Fetch all test result files from a11ysupport.io
    2. Extract failures → new bug candidates
    3. Check if our existing bugs still fail → potentially fixed
    4. Update known-bugs.json if not dry_run
    """
    report = SyncReport()

    # Load our current bugs
    bugs_data = load_local("known-bugs.json")
    our_bugs = bugs_data.get("bugs", [])
    our_bug_ids = {b["id"] for b in our_bugs}

    # Build a lookup of our bugs by role/property + SR
    our_bug_lookup = {}
    for bug in our_bugs:
        key_role = bug.get("role", "")
        key_prop = bug.get("property", "")
        key_sr = bug["screen_reader"]
        our_bug_lookup[(key_role, key_prop, key_sr)] = bug

    print("Fetching test result file list...")
    test_files = list_remote_test_files()
    print(f"  Found {len(test_files)} test files")

    # Collect all failures from upstream
    all_upstream_failures = []
    roles_with_failures = set()

    for i, test_file in enumerate(test_files):
        if i % 10 == 0:
            print(f"  Fetching {i + 1}/{len(test_files)}...", end="\r")

        data = fetch_test_result(test_file)
        if not data:
            continue

        failures = extract_failures_from_test(data)
        all_upstream_failures.extend(failures)
        for f in failures:
            feature = f.get("feature_id", "")
            if "/" in feature:
                roles_with_failures.add(feature.split("/")[1])

    print(f"\n  Total upstream failures: {len(all_upstream_failures)}")

    # Find NEW bug candidates (upstream failures not in our list)
    seen_candidates = set()
    for failure in all_upstream_failures:
        sr = failure["screen_reader"]
        feature = failure.get("feature_id", "")

        # Extract role or property from feature_id (e.g., "aria/alert_role" → "alert")
        role = ""
        prop = ""
        if "/" in feature:
            part = feature.split("/")[1]
            if part.endswith("_role"):
                role = part.replace("_role", "")
            elif part.startswith("aria-") or part.startswith("aria_"):
                prop = part.replace("_attribute", "").replace("_", "-")

        # Check if we already track this
        if (role, prop, sr) in our_bug_lookup:
            continue
        if (role, "", sr) in our_bug_lookup:
            continue
        if ("", prop, sr) in our_bug_lookup:
            continue

        # Deduplicate
        dedup_key = (role or prop, sr, failure["browser"])
        if dedup_key in seen_candidates:
            continue
        seen_candidates.add(dedup_key)

        report.new_bug_candidates.append(failure)

    # Find POTENTIALLY FIXED bugs (in our list but no longer failing upstream)
    for bug in our_bugs:
        bug_role = bug.get("role", "")
        bug_prop = bug.get("property", "")
        bug_sr = bug["screen_reader"]

        # Check if any upstream failure matches this bug
        still_failing = False
        for failure in all_upstream_failures:
            f_sr = failure["screen_reader"]
            f_feature = failure.get("feature_id", "")

            if f_sr != bug_sr:
                continue

            if bug_role and bug_role in f_feature:
                still_failing = True
                break
            if bug_prop and bug_prop.replace("-", "_") in f_feature:
                still_failing = True
                break

        if not still_failing:
            report.potentially_fixed.append(bug)

    # Check for new roles
    announcements = load_local("announcements.json")
    our_roles = {k for k in announcements.keys() if not k.startswith("_")}
    remote_roles = set(list_remote_roles())
    new_roles = remote_roles - our_roles
    if new_roles:
        report.new_roles = sorted(new_roles)

    # Apply changes if not dry run
    if not dry_run and report.has_changes():
        # Add new bug candidates to known-bugs.json
        if report.new_bug_candidates:
            for candidate in report.new_bug_candidates[:20]:  # Cap at 20 new bugs per sync
                role = ""
                prop = ""
                feature = candidate.get("feature_id", "")
                if "/" in feature:
                    part = feature.split("/")[1]
                    if part.endswith("_role"):
                        role = part.replace("_role", "")
                    elif part.startswith("aria-") or part.startswith("aria_"):
                        prop = part.replace("_attribute", "").replace("_", "-")

                new_bug = {
                    "id": f"sync-{candidate['screen_reader']}-{(role or prop).replace('-', '_')}-{candidate['browser']}",
                    "screen_reader": candidate["screen_reader"],
                    "browser": candidate["browser"],
                    "severity": "moderate",
                    "description": f"Upstream test failure: {candidate.get('assertion_id', 'unknown')} "
                                   f"for {feature}. Output: {candidate.get('output', 'N/A')[:100]}",
                    "source_url": "https://a11ysupport.io/",
                }
                if role:
                    new_bug["role"] = role
                if prop:
                    new_bug["property"] = prop

                # Avoid duplicate IDs
                if new_bug["id"] not in our_bug_ids:
                    our_bugs.append(new_bug)
                    our_bug_ids.add(new_bug["id"])

        # Mark potentially fixed bugs (add a "possibly_fixed" flag)
        for fixed in report.potentially_fixed:
            for bug in our_bugs:
                if bug["id"] == fixed["id"]:
                    bug["_possibly_fixed"] = True
                    bug["_checked_date"] = datetime.now().strftime("%Y-%m-%d")

        # Update metadata
        bugs_data["_meta"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
        bugs_data["bugs"] = our_bugs
        save_local("known-bugs.json", bugs_data)
        report.changes_made = True

    return report


# ── Main ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Import, validate, and sync screen reader data from a11ysupport.io and ARIA-AT"
    )
    parser.add_argument("--check", action="store_true", help="Validate local data files")
    parser.add_argument("--coverage", action="store_true", help="Check role coverage against a11ysupport.io")
    parser.add_argument("--list-roles", action="store_true", help="List all ARIA roles from a11ysupport.io")
    parser.add_argument("--show-output", metavar="ROLE", help="Show SR output for a specific role")
    parser.add_argument("--sync", action="store_true", help="Sync with upstream data (fetch + diff + update)")
    parser.add_argument("--dry-run", action="store_true", help="With --sync: show changes without applying")

    args = parser.parse_args()

    if not any([args.check, args.coverage, args.list_roles, args.show_output, args.sync]):
        parser.print_help()
        return

    if args.list_roles:
        roles = list_remote_roles()
        print(f"\nFound {len(roles)} ARIA roles:")
        for r in roles:
            print(f"  - {r}")

    if args.coverage:
        check_coverage()

    if args.check:
        ok1 = validate_announcements()
        ok2 = validate_keyboard_commands()
        if ok1 and ok2:
            print("\n  All validations passed!")
        else:
            print("\n  Some validations failed.")
            sys.exit(1)

    if args.show_output:
        show_sr_output_for_role(args.show_output)

    if args.sync:
        print("\n=== Syncing with a11ysupport.io ===\n")
        report = sync_known_bugs(dry_run=args.dry_run)
        report.print_summary()

        if args.dry_run:
            print("  (Dry run — no files were modified)")
        elif report.changes_made:
            print("  Files updated. Review changes and commit.")
        else:
            print("  No changes needed.")

        # Exit with code 1 if there are changes (useful for CI)
        if report.has_changes():
            sys.exit(1 if args.dry_run else 0)


if __name__ == "__main__":
    main()
