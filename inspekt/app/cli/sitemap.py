"""
Sitemap command - Discover, display, and navigate sitemaps.

Provides a tree view of a site's sitemap.xml, with interactive navigation
and auto-discovery via robots.txt. Supports sitemap index files, caching,
filtering, and direct navigation to any listed URL.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter
from dataclasses import dataclass, field
from urllib.parse import urlparse

import click

from inspekt.app.cli.icons import get_icon
from inspekt.app.cli.table import Table, print_hint, print_warning, print_error, print_success
from inspekt.services.bridge_executor import get_executor


# ============================================================================
# Date formatting
# ============================================================================

def _format_date(iso_str: str) -> str:
    """
    Format an ISO date string as a compact relative date.

    '2025-03-17T12:48:04+00:00'   → '1y ago'
    '2026-01-08T07:29:42.204Z'    → '3m ago'
    '2026-04-01'                   → '3d ago'
    '2025-10-20'                   → '1y, 5m ago'
    """
    from datetime import datetime, timezone

    if not iso_str:
        return ""

    try:
        import humanize

        # fromisoformat handles all ISO 8601 variants including milliseconds and Z
        clean = iso_str.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean)
        except ValueError:
            return iso_str[:10]  # Unparseable — show just the date part

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        humanize.deactivate()  # Ensure English
        return _shorten_relative_date(humanize.naturaltime(dt))

    except ImportError:
        return iso_str[:10]


def _shorten_relative_date(text: str) -> str:
    """
    Shorten humanize output to compact notation.

    'a day ago'                → '1d ago'
    '11 days ago'              → '11d ago'
    'a month ago'              → '1m ago'
    '3 months ago'             → '3m ago'
    '1 year, 5 months ago'     → '1y, 5m ago'
    'a year ago'               → '1y ago'
    'an hour ago'              → '1h ago'
    '2 hours ago'              → '2h ago'
    'a minute ago'             → '1min ago'
    """
    # Strip trailing " ago" and reattach after shortening
    if not text.endswith(" ago"):
        return text
    core = text[:-4]  # remove " ago"

    # Replace units in each comma-separated part
    units = {"year": "y", "month": "m", "week": "w", "day": "d", "hour": "h", "minute": "min", "second": "s"}
    parts = [p.strip() for p in core.split(",")]
    short_parts = []
    for part in parts:
        # "a day" / "an hour" → "1d" / "1h"
        m = re.match(r"^an?\s+(\w+)s?$", part)
        if m:
            unit = units.get(m.group(1), m.group(1))
            short_parts.append(f"1{unit}")
            continue
        # "11 days" / "3 months" → "11d" / "3m"
        m = re.match(r"^(\d+)\s+(\w+?)s?$", part)
        if m:
            num, unit_word = m.group(1), m.group(2)
            unit = units.get(unit_word, unit_word)
            short_parts.append(f"{num}{unit}")
            continue
        short_parts.append(part)

    return ", ".join(short_parts) + " ago"


# ISO 639-1 language code → English name (for display in tree)
_LANG_NAMES = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic", "az": "Azerbaijani",
    "be": "Belarusian", "bg": "Bulgarian", "bn": "Bengali", "bs": "Bosnian",
    "ca": "Catalan", "cs": "Czech", "cy": "Welsh",
    "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "eo": "Esperanto", "es": "Spanish", "et": "Estonian", "eu": "Basque",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "fy": "Frisian",
    "ga": "Irish", "gd": "Scottish Gaelic", "gl": "Galician", "gu": "Gujarati",
    "ha": "Hausa", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian", "hy": "Armenian",
    "id": "Indonesian", "is": "Icelandic", "it": "Italian",
    "ja": "Japanese", "jv": "Javanese",
    "ka": "Georgian", "kk": "Kazakh", "km": "Khmer", "kn": "Kannada", "ko": "Korean", "ku": "Kurdish", "ky": "Kyrgyz",
    "la": "Latin", "lb": "Luxembourgish", "lo": "Lao", "lt": "Lithuanian", "lv": "Latvian",
    "mk": "Macedonian", "ml": "Malayalam", "mn": "Mongolian", "mr": "Marathi", "ms": "Malay", "mt": "Maltese", "my": "Burmese",
    "nb": "Norwegian Bokmål", "ne": "Nepali", "nl": "Dutch", "nn": "Norwegian Nynorsk", "no": "Norwegian",
    "pa": "Punjabi", "pl": "Polish", "ps": "Pashto", "pt": "Portuguese",
    "ro": "Romanian", "ru": "Russian", "rw": "Kinyarwanda",
    "si": "Sinhala", "sk": "Slovak", "sl": "Slovenian", "so": "Somali", "sq": "Albanian", "sr": "Serbian", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "te": "Telugu", "tg": "Tajik", "th": "Thai", "tk": "Turkmen", "tl": "Tagalog", "tr": "Turkish",
    "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek",
    "vi": "Vietnamese",
    "zh": "Chinese", "zu": "Zulu",
}



# ============================================================================
# Tree rendering
# ============================================================================

# Box-drawing characters for tree view
PIPE = "\u2502"      # │
TEE = "\u251c"       # ├
ELBOW = "\u2570"     # ╰
DASH = "\u2500"      # ─


def _build_entry_meta(entry) -> str:
    """Build styled metadata string (HTTP status, date, priority) for a sitemap entry."""
    meta_parts = []
    if entry.http_status and entry.http_status != 200:
        color = "red" if entry.http_status >= 400 else "yellow"
        meta_parts.append(click.style(f"({entry.http_status})", fg=color))
    if entry.lastmod:
        meta_parts.append(click.style(f"({_format_date(entry.lastmod)})", fg="bright_black"))
    if entry.priority and entry.priority != "0.5":
        meta_parts.append(click.style(f"(p={entry.priority})", fg="yellow"))
    return f" {' '.join(meta_parts)}" if meta_parts else ""


def wrap_styled_line(
    prefix: str,
    text: str,
    suffix: str = "",
    *,
    cont_prefix: str = "",
    text_style: dict | None = None,
    max_width: int = 0,
) -> list[str]:
    """
    Wrap a styled line so continuation lines align with the text start.

    Use this whenever you display indented text (tree labels, breadcrumbs,
    list items) that might exceed the terminal width. The prefix and suffix
    are never split; only the text body is wrapped at word boundaries.

    Args:
        prefix:      Styled line start (connector, marker, indent). Never wrapped.
        text:        Styled text body. May be wrapped at word boundaries.
        suffix:      Styled tag appended after text (e.g., "← you are here",
                     "(3d ago)"). Kept as an atomic unit — bumped to its own
                     line if it doesn't fit.
        cont_prefix: Styled prefix for continuation lines. Should preserve
                     the visual structure (pipes, indentation) so the wrapped
                     text appears to "hang" under the first line. Defaults to
                     spaces matching the prefix width.
        text_style:  Style kwargs applied to wrapped text fragments on
                     continuation lines (e.g., {"fg": "white"}). If None,
                     continuation text is unstyled.
        max_width:   Maximum visible columns. 0 = auto-detect from terminal.

    Returns:
        List of fully formatted lines ready for click.echo().

    Example::

        # Tree node:  "  ├── [5] Very Long Page Title That Wraps  (3d ago)"
        #             "  │       continuation of the title"
        wrap_styled_line(
            prefix=f"{indent}{connector}{idx_str} ",
            text=click.style(title, fg="white"),
            suffix=meta_str,
            cont_prefix=f"{child_prefix}{' ' * (idx_width + 1)}",
            text_style={"fg": "white"},
        )

        # Breadcrumb:  "       ╰── Articles  ← you are here"
        wrap_styled_line(
            prefix=f"{indent}{connector}",
            text=click.style(name, fg="white", bold=True),
            suffix=click.style("  ← you are here", fg="green"),
            cont_prefix=f"{indent}    ",
            text_style={"fg": "white", "bold": True},
        )
    """
    if max_width <= 0:
        max_width = shutil.get_terminal_size().columns - 2

    if not cont_prefix:
        cont_prefix = " " * len(click.unstyle(prefix))

    prefix_w = len(click.unstyle(prefix))
    text_plain = click.unstyle(text)
    suffix_w = len(click.unstyle(suffix)) if suffix else 0
    cont_w = len(click.unstyle(cont_prefix))

    # Everything fits on one line
    if prefix_w + len(text_plain) + suffix_w <= max_width:
        return [f"{prefix}{text}{suffix}"]

    # Text alone fits — put suffix on next line
    if suffix and prefix_w + len(text_plain) <= max_width:
        return [
            f"{prefix}{text}",
            f"{cont_prefix}{suffix.lstrip()}",
        ]

    # Text needs wrapping — break at word boundaries
    avail = max_width - prefix_w
    text_lines = _wrap_text(text_plain, avail, max_width - cont_w)

    def _style_fragment(t: str) -> str:
        return click.style(t, **text_style) if text_style else t

    result = [f"{prefix}{_style_fragment(text_lines[0])}"]
    for extra in text_lines[1:]:
        result.append(f"{cont_prefix}{_style_fragment(extra)}")

    # Append suffix to the last line if it fits, otherwise on its own line
    if suffix:
        last_plain_len = len(click.unstyle(result[-1]))
        if last_plain_len + suffix_w <= max_width:
            result[-1] += suffix
        else:
            result.append(f"{cont_prefix}{suffix.lstrip()}")

    return result


def _wrap_tree_label(
    head: str, title: str, meta: str, max_width: int, cont_prefix: str
) -> list[str]:
    """Wrap a tree label. Delegates to wrap_styled_line."""
    return wrap_styled_line(
        prefix=head,
        text=title,
        suffix=meta,
        cont_prefix=cont_prefix,
        text_style={"fg": "white"},
        max_width=max_width,
    )


def _wrap_text(text: str, first_width: int, next_width: int) -> list[str]:
    """Split plain text into lines fitting the given widths."""
    lines = []
    remaining = text
    width = first_width

    while remaining:
        if len(remaining) <= width:
            lines.append(remaining)
            break
        # Find word boundary
        break_at = remaining.rfind(" ", 0, width)
        if break_at <= 0:
            break_at = width  # forced break
        lines.append(remaining[:break_at])
        remaining = remaining[break_at:].lstrip()
        width = next_width  # subsequent lines get the continuation width

    return lines or [text]


def _render_tree(node, prefix: str = "", is_last: bool = True, filter_path: str = "", lines: list | None = None, is_root: bool = True, max_width: int = 0) -> list[str]:
    """
    Render a tree node and its children as styled text lines.

    Args:
        node: TreeNode to render
        prefix: Indentation prefix for this level
        is_last: Whether this is the last child of its parent
        filter_path: Optional path prefix filter
        lines: Accumulator for output lines
        is_root: Whether this is the root node

    Returns:
        List of formatted text lines
    """
    if lines is None:
        lines = []

    # Determine max width on first call (account for 2-space margin in _display_tree)
    if max_width <= 0:
        max_width = shutil.get_terminal_size().columns - 2

    # Root node
    if is_root:
        # Show root entry index if the root itself is a URL in the sitemap
        if node.has_entry:
            idx_str = click.style(f"[{node.entry_index}]", fg="bright_black")
            root_label = f"{click.style(node.name, fg='cyan', bold=True)} {idx_str}"
        else:
            root_label = click.style(node.name, fg="cyan", bold=True)
        lines.append(root_label)

        # Render children (with duplicate title grouping)
        children = _filtered_children(node, filter_path)
        children = _group_duplicate_titles(children)

        for i, (name, child_or_group) in enumerate(children):
            is_last_child = i == len(children) - 1
            if isinstance(child_or_group, TitleGroup):
                _render_title_group(
                    child_or_group, prefix="", is_last=is_last_child,
                    lines=lines, max_width=max_width,
                )
            else:
                _render_tree(child_or_group, "", is_last_child, filter_path, lines, is_root=False, max_width=max_width)

        return lines

    # Build connector
    connector = f"{ELBOW}{DASH}{DASH} " if is_last else f"{TEE}{DASH}{DASH} "

    # Prepare child prefix early — also used for continuation lines
    child_prefix = prefix + ("    " if is_last else f"{PIPE}   ")

    # Format the node name
    if node.has_entry:
        idx_str = click.style(f"[{node.entry_index}]", fg="bright_black")
        head = f"{prefix}{connector}{idx_str} "

        # Show title instead of slug when available
        if node.entry.title:
            name_str = click.style(node.entry.title, fg="white")
        else:
            name_str = click.style(node.name, fg="white")

        meta_str = _build_entry_meta(node.entry)

        # Continuation prefix: pipes from ancestors + spaces to align with title
        idx_plain_len = len(f"[{node.entry_index}]")
        cont_prefix = child_prefix + " " * (idx_plain_len + 1)

        lines.extend(_wrap_tree_label(head, name_str, meta_str, max_width, cont_prefix))
    else:
        # Directory node (no URL, just a path segment)
        head = f"{prefix}{connector}"
        lang_name = _LANG_NAMES.get(node.name.lower())
        if lang_name:
            page_count = _count_entries(node)
            name_str = click.style(lang_name, fg="blue", bold=True)
            pages_word = "page" if page_count == 1 else "pages"
            meta_str = f" {click.style(f'({page_count} {pages_word})', fg='bright_black')}"
        else:
            name_str = click.style(f"{node.name}/", fg="blue")
            meta_str = ""
        # Directory labels are short — no wrapping needed
        lines.append(f"{head}{name_str}{meta_str}")

    # Render children (with duplicate title grouping)
    children = _filtered_children(node, filter_path)
    children = _group_duplicate_titles(children)

    for i, (name, child_or_group) in enumerate(children):
        is_last_child = i == len(children) - 1

        if isinstance(child_or_group, TitleGroup):
            _render_title_group(
                child_or_group, prefix=child_prefix, is_last=is_last_child,
                lines=lines, max_width=max_width,
            )
        else:
            _render_tree(child_or_group, child_prefix, is_last_child, filter_path, lines, is_root=False, max_width=max_width)

    return lines


def _render_title_group(group: TitleGroup, prefix: str, is_last: bool, lines: list, max_width: int):
    """Render a group of pages that share the same title."""
    connector = f"{ELBOW}{DASH}{DASH} " if is_last else f"{TEE}{DASH}{DASH} "
    child_prefix = prefix + ("    " if is_last else f"{PIPE}   ")

    # Group header: title + (N pages) or (N pages, M aliases)
    count = len(group.members)
    pages_word = "page" if count == 1 else "pages"
    title_str = click.style(group.title, fg="white")

    if group.alias_locs:
        alias_count = len(group.alias_locs)
        alias_word = "alias" if alias_count == 1 else "aliases"
        count_str = click.style(f"({count} {pages_word}, ", fg="bright_black")
        alias_str = click.style(f"{alias_count} {alias_word}", fg="yellow")
        count_end = click.style(")", fg="bright_black")
        meta_str = f" {count_str}{alias_str}{count_end}"
    else:
        meta_str = f" {click.style(f'({count} {pages_word})', fg='bright_black')}"

    lines.append(f"{prefix}{connector}{title_str}{meta_str}")

    # Sort members by lastmod (most recent first), then render with distinguishing slugs
    members = sorted(group.members, key=lambda x: x[1].entry.lastmod or "", reverse=True)
    slugs = _distinguishing_slug(members)

    for j, (name, node) in enumerate(members):
        is_last_member = j == len(members) - 1
        member_connector = f"{ELBOW}{DASH}{DASH} " if is_last_member else f"{TEE}{DASH}{DASH} "

        idx_str = click.style(f"[{node.entry_index}]", fg="bright_black")
        slug_str = click.style(slugs[node.entry.loc], fg="cyan")

        # Alias indicator
        alias_indicator = click.style(" \u2192 alias", fg="yellow") if node.entry.loc in group.alias_locs else ""

        member_meta = _build_entry_meta(node.entry)
        lines.append(f"{child_prefix}{member_connector}{idx_str} {slug_str}{alias_indicator}{member_meta}")


def _filtered_children(node, filter_path: str) -> list[tuple]:
    """Get filtered and sorted children of a node."""
    children = list(node.children.items())

    if filter_path:
        # Only include children whose subtree contains matching paths
        filtered = []
        for name, child in children:
            if _subtree_matches(child, filter_path):
                filtered.append((name, child))
        children = filtered

    # Sort: directories first (nodes with children), then leaves, alphabetically
    children.sort(key=lambda x: (not x[1].children, x[0].lower()))
    return children


def _count_entries(node) -> int:
    """Count total URL entries in a subtree."""
    count = 1 if node.has_entry else 0
    for child in node.children.values():
        count += _count_entries(child)
    return count


def _subtree_matches(node, filter_path: str) -> bool:
    """Check if any entry in the subtree matches the filter path."""
    if node.has_entry and filter_path.lower() in node.full_path.lower():
        return True
    return any(_subtree_matches(child, filter_path) for child in node.children.values())


# ============================================================================
# Duplicate title grouping
# ============================================================================


@dataclass
class TitleGroup:
    """Virtual group node for sibling pages that share the same title."""
    title: str
    members: list[tuple[str, object]]  # (name, TreeNode) pairs
    alias_locs: set[str] = field(default_factory=set)  # URLs detected as aliases


def _group_duplicate_titles(children: list[tuple]) -> list:
    """
    Group sibling leaf nodes that share the same title.

    Returns a mixed list of (name, TreeNode) tuples and (group_key, TitleGroup) tuples.
    Only groups titles that appear 2+ times among leaf nodes.
    """
    # Count titles among leaf nodes (nodes with entries and no children)
    title_counts = Counter()
    for name, child in children:
        if child.has_entry and not child.children and child.entry.title:
            title_counts[child.entry.title] += 1

    # Titles appearing 2+ times get grouped
    dupe_titles = {t for t, c in title_counts.items() if c >= 2}
    if not dupe_titles:
        return children

    # Build groups and passthrough list
    groups: dict[str, TitleGroup] = {}
    result = []
    for name, child in children:
        title = child.entry.title if child.has_entry and not child.children else None
        if title and title in dupe_titles:
            if title not in groups:
                group = TitleGroup(title=title, members=[])
                groups[title] = group
                result.append((f"__group__{title}", group))
            groups[title].members.append((name, child))
        else:
            result.append((name, child))

    # Detect aliases within each group
    for group in groups.values():
        group.alias_locs = _detect_aliases([node.entry for _, node in group.members])

    return result


def _detect_aliases(entries: list) -> set[str]:
    """
    Detect which entries in a group are aliases of each other.

    Returns set of entry.loc URLs that are aliases (all but the "primary").
    Detection layers:
      1. Same canonical URL
      2. Redirect to same final URL
      3. Same ETag
    """
    if len(entries) < 2:
        return set()

    alias_locs: set[str] = set()
    all_locs = {e.loc for e in entries}

    # Layer 1: Same canonical URL
    canonical_groups: dict[str, list] = {}
    for e in entries:
        if e.canonical_url:
            canonical_groups.setdefault(e.canonical_url, []).append(e)
    for canonical, group in canonical_groups.items():
        if len(group) >= 2:
            # The entry whose loc matches the canonical is the primary
            primary = next((e for e in group if e.loc == canonical), group[0])
            for e in group:
                if e is not primary:
                    alias_locs.add(e.loc)
        elif len(group) == 1 and canonical in all_locs and group[0].loc != canonical:
            alias_locs.add(group[0].loc)

    # Layer 2: Redirect to same target (another entry's loc or shared final_url)
    final_groups: dict[str, list] = {}
    for e in entries:
        if e.final_url:
            final_groups.setdefault(e.final_url, []).append(e)
    for final, group in final_groups.items():
        if len(group) >= 2:
            for e in group[1:]:
                alias_locs.add(e.loc)
        # Single entry redirecting to another entry's loc = alias
        elif len(group) == 1 and final in all_locs and group[0].loc != final:
            alias_locs.add(group[0].loc)

    # Layer 3: Same ETag
    etag_groups: dict[str, list] = {}
    for e in entries:
        if e.etag:
            etag_groups.setdefault(e.etag, []).append(e)
    for etag, group in etag_groups.items():
        if len(group) >= 2:
            for e in group[1:]:
                alias_locs.add(e.loc)

    return alias_locs


def _distinguishing_slug(members: list[tuple[str, object]]) -> dict[str, str]:
    """
    Find the minimal distinguishing slug for each member in a title group.

    Returns dict mapping entry.loc to display slug (e.g., "/contact" or "/nl/page").
    """
    paths = {}
    for name, node in members:
        parsed = urlparse(node.entry.loc)
        paths[node.entry.loc] = parsed.path.rstrip("/") or "/"

    # Try last segment first
    last_segments = {loc: "/" + p.split("/")[-1] for loc, p in paths.items()}
    if len(set(last_segments.values())) == len(last_segments):
        return last_segments

    # Last segments aren't unique — use full path
    return paths


# ============================================================================
# Interactive mode
# ============================================================================

def _sort_by_lastmod(items: list[dict]) -> list[dict]:
    """Sort items by lastmod, most recent first. Items without lastmod go last."""
    with_date = [i for i in items if i.get("lastmod")]
    without_date = [i for i in items if not i.get("lastmod")]
    with_date.sort(key=lambda i: i["lastmod"], reverse=True)
    return with_date + without_date


def _has_gum() -> bool:
    """Check if gum (charmbracelet/gum) is available."""
    import shutil
    return shutil.which("gum") is not None


def _interactive_picker(items: list[dict]) -> str | None:
    """
    Pick a sitemap URL interactively.

    Uses gum filter for a polished fuzzy search TUI when available,
    falls back to a prompt-based picker otherwise.

    Each item has: index, path (slug), title, url, lastmod.
    Display shows titles, but search matches both titles and slugs.
    """
    if _has_gum():
        result = _gum_picker(items)
        if result is not None:
            return result
        # gum failed (no /dev/tty, etc.) — fall through to simple picker
    return _simple_picker(items)


def _gum_picker(items: list[dict]) -> str | None:
    """Fuzzy search picker using gum filter."""
    import subprocess

    # Sort by last modified date (most recent first)
    items = _sort_by_lastmod(items)

    # Build lines for gum: "title  (slug)  (date)" — gum searches the full line,
    # so both title and slug are searchable. We map the selected line back to its URL.
    lines = []
    line_to_url = {}
    for item in items:
        title = item.get("title") or item["path"]
        slug = item["path"]
        date_str = f"  ({_format_date(item['lastmod'])})" if item.get("lastmod") else ""
        if item.get("title"):
            display = f"{title}  ({slug}){date_str}"
        else:
            display = f"{slug}{date_str}"
        lines.append(display)
        line_to_url[display] = item["url"]

    try:
        # Check if /dev/tty is available (gum needs it for keyboard input)
        open("/dev/tty").close()
        return _gum_direct(lines, line_to_url, len(items))
    except OSError:
        pass

    # No /dev/tty — use `script` to allocate a PTY (available via util-linux)
    import shutil
    if shutil.which("script"):
        return _gum_via_script(lines, line_to_url, len(items))

    return None


def _gum_direct(lines: list[str], line_to_url: dict, count: int) -> str | None:
    """Run gum filter directly (when /dev/tty is available)."""
    import subprocess

    try:
        proc = subprocess.Popen(
            [
                "gum", "filter",
                "--placeholder", "Search sitemap\u2026",
                "--height", "20",
                "--header", f"  {count} URLs \u2014 type to search, enter to navigate",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
        )
        stdout, _ = proc.communicate(input="\n".join(lines))

        if proc.returncode != 0:
            return None

        selected_line = stdout.strip()
        return line_to_url.get(selected_line)

    except (FileNotFoundError, OSError):
        return None


def _gum_via_script(lines: list[str], line_to_url: dict, count: int) -> str | None:
    """Run gum filter via `script` which allocates a real PTY (for VM without /dev/tty)."""
    import subprocess
    import tempfile

    try:
        # Write items to a temp file — script takes over stdin for the terminal
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n".join(lines))
            items_path = f.name

        # script -qc runs the command with a PTY, -q suppresses "Script started"
        # gum reads items from the file via redirection, writes selection to a result file
        import os
        result_path = items_path + ".result"

        result = subprocess.run(
            [
                "script", "-qc",
                f'gum filter '
                f'--placeholder "Search sitemap\u2026" '
                f'--height 20 '
                f'--header "  {count} URLs \u2014 type to search, enter to navigate" '
                f'< "{items_path}" > "{result_path}"',
                "/dev/null",
            ],
        )

        os.unlink(items_path)

        if result.returncode != 0:
            if os.path.exists(result_path):
                os.unlink(result_path)
            return None

        if os.path.exists(result_path):
            selected_line = open(result_path).read().strip().replace("\r", "")
            os.unlink(result_path)
            return line_to_url.get(selected_line)

        return None

    except (FileNotFoundError, OSError):
        return None


def _simple_picker(items: list[dict]) -> str | None:
    """Fallback picker using simple prompt input. Searches titles and slugs."""
    click.echo()
    click.echo(click.style("Enter a number or search text to filter:", fg="cyan"))
    click.echo(click.style("(Press Ctrl+C to cancel)", fg="bright_black"))
    click.echo()

    try:
        while True:
            user_input = click.prompt("sitemap", default="", show_default=False)

            if not user_input:
                return None

            # Try as number
            try:
                idx = int(user_input)
                if 1 <= idx <= len(items):
                    return items[idx - 1]["url"]
                else:
                    print_warning(f"Number must be between 1 and {len(items)}")
                    continue
            except ValueError:
                pass

            # Search both titles and slugs
            query = user_input.lower()
            matches = [
                item for item in items
                if query in item["path"].lower() or query in item.get("title", "").lower()
            ]
            if not matches:
                print_warning(f"No URLs matching `{user_input}`")
                continue

            # Sort by last modified date (most recent first)
            matches = _sort_by_lastmod(matches)

            if len(matches) == 1:
                return matches[0]["url"]

            # Show matches — display title if available, slug otherwise
            for item in matches[:20]:
                idx_str = click.style(f"[{item['index']}]", fg="bright_black")
                display = item.get("title") or item["path"]
                lastmod = item.get("lastmod")
                date_str = f"  {click.style(f'({_format_date(lastmod)})', fg='bright_black')}" if lastmod else ""
                click.echo(f"  {idx_str} {display}{date_str}")

            if len(matches) > 20:
                click.echo(click.style(f"  \u2026and {len(matches) - 20} more", fg="bright_black"))

    except (KeyboardInterrupt, EOFError):
        click.echo()
        return None


# ============================================================================
# Navigation helper
# ============================================================================

def _navigate_to(url: str):
    """Navigate the browser to a URL using the bridge."""
    executor = get_executor()
    nav_code = f"(window.location.href = {json.dumps(url)}, true)"
    result = executor.execute(nav_code, timeout=10.0)

    if result.get("ok"):
        print_success(f"Navigating to `{url}`")
    else:
        print_error(f"Navigation failed: {result.get('error', 'Unknown error')}")


# Named targets for --open
_NAMED_TARGETS = {"parent", "up", "next", "prev", "first-child"}

# Valid modes for --where
_WHERE_MODES = ("compact", "nearby", "full")


def _get_current_path() -> str:
    """Get the path portion of the current browser URL."""
    from inspekt.services.browser_url import BrowserURLError, resolve_url

    try:
        full_url = resolve_url()
    except BrowserURLError as e:
        print_error(f"Cannot determine current page: {e}")
        sys.exit(1)

    return urlparse(full_url).path or "/"


def _handle_open_target(target: str, result, origin: str):
    """Handle --open with either a numeric index or a named target."""
    from inspekt.services.sitemap_service import build_tree, find_node_by_path

    # Numeric index — existing behavior
    if target.isdigit():
        index = int(target)
        if index < 1 or index > len(result.entries):
            print_error(f"Index {index} out of range (1-{len(result.entries)})")
            sys.exit(1)
        entry = result.entries[index - 1]
        _navigate_to(entry.loc)
        return

    target = target.lower().strip()
    if target not in _NAMED_TARGETS:
        print_error(f"Unknown target `{target}`. Use a number or one of: {', '.join(sorted(_NAMED_TARGETS))}")
        sys.exit(1)

    # Named targets require knowing where we are in the sitemap tree
    current_path = _get_current_path()
    tree = build_tree(result.entries, origin)
    node, parent = find_node_by_path(tree, current_path)

    if node is None:
        print_error("Current page is not in the sitemap")
        print_hint("Try `inspekt sitemap --refresh` to update the sitemap cache")
        sys.exit(1)

    if target in ("parent", "up"):
        if parent is None:
            print_error("Already at the root of the sitemap")
            sys.exit(0)
        url = f"{origin}{parent.full_path}"
        _navigate_to(url)

    elif target in ("next", "prev"):
        if parent is None:
            print_error("Root has no siblings")
            sys.exit(0)
        siblings = sorted(parent.children.values(), key=lambda n: n.name.lower())
        current_idx = next((i for i, s in enumerate(siblings) if s is node), -1)
        if target == "next":
            if current_idx == len(siblings) - 1:
                print_error("Already at the last sibling")
                sys.exit(0)
            sibling_node = siblings[current_idx + 1]
        else:
            if current_idx == 0:
                print_error("Already at the first sibling")
                sys.exit(0)
            sibling_node = siblings[current_idx - 1]
        _navigate_to(f"{origin}{sibling_node.full_path}")

    elif target == "first-child":
        if not node.children:
            print_error("This page has no child pages")
            sys.exit(0)
        first = sorted(node.children.values(), key=lambda n: n.name.lower())[0]
        url = f"{origin}{first.full_path}"
        _navigate_to(url)


def _get_origin(override_url: str | None) -> str:
    """Get the origin from the browser or an override URL."""
    from inspekt.services.browser_url import BrowserURLError, InternalURLError, resolve_origin

    try:
        return resolve_origin(override_url)
    except InternalURLError:
        print_error("This command requires a real website (http/https)")
        print_hint("Navigate to a website first, then try again")
        sys.exit(0)
    except BrowserURLError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================================
# Main command
# ============================================================================

@click.command()
@click.argument("url", required=False)
@click.option("--flat", is_flag=True, help="Show flat URL list instead of tree")
@click.option("--filter", "filter_path", type=str, help="Filter URLs by path (e.g., /blog)")
@click.option("--lang", type=str, help="Filter by language path prefix (e.g., nl, en, fr)")
@click.option("--open", "open_target", type=str, help="Navigate by index (5) or target (parent, up, next, prev, first-child)")
@click.option("--interactive", "-i", is_flag=True, help="Interactive fuzzy search picker")
@click.option("--where", is_flag=False, flag_value="compact", default=None, help="Breadcrumb: compact (default), nearby (windowed), or full (all siblings)")
@click.option("--neighbors", is_flag=True, help="Show parent, siblings, and children of current page")
@click.option("--from-here", "from_here", is_flag=True, help="Show subtree from current browser page")
@click.option("--stats", is_flag=True, help="Show sitemap statistics")
@click.option("--no-flatten", is_flag=True, help="Show sitemap index without expanding child sitemaps")
@click.option("--refresh", is_flag=True, help="Force re-fetch (bypass cache)")
@click.option("--no-titles", is_flag=True, help="Skip fetching page titles")
@click.option("--debug-titles", is_flag=True, hidden=True, help="Debug title fetching")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def sitemap(url, flat, filter_path, lang, open_target, interactive, where, neighbors, from_here, stats, no_flatten, refresh, no_titles, debug_titles, output_json):
    """
    Discover and browse a site's sitemap.

    Auto-discovers the sitemap via robots.txt or /sitemap.xml fallback.
    Displays URLs as a navigable tree with path-based grouping.

    \b
    Examples:
        inspekt sitemap                         # Auto-discover and show tree
        inspekt sitemap --flat                   # Flat URL list
        inspekt sitemap --filter /blog           # Only show /blog/* URLs
        inspekt sitemap --lang nl                # Only show Dutch pages
        inspekt sitemap --open 5                 # Navigate to URL #5
        inspekt sitemap --open parent            # Navigate to parent page
        inspekt sitemap --open next              # Navigate to next sibling
        inspekt sitemap --open prev              # Navigate to previous sibling
        inspekt sitemap --open first-child       # Navigate to first child page
        inspekt sitemap --where                  # Breadcrumb to current page
        inspekt sitemap --where=nearby           # With surrounding pages at each level
        inspekt sitemap --where=full             # All siblings at every level
        inspekt sitemap --neighbors              # Parent, siblings, and children
        inspekt sitemap --from-here              # Subtree from current page
        inspekt sitemap --from-here -i           # Fuzzy search within subtree
        inspekt sitemap --interactive            # Fuzzy search picker
        inspekt sitemap --stats                  # Show statistics
        inspekt sitemap --no-flatten             # Show sitemap index without expanding
        inspekt sitemap --no-titles               # Skip page title fetching
        inspekt sitemap --refresh                # Bypass cache
        inspekt sitemap https://example.com/sitemap.xml  # Specific sitemap URL
    """
    from inspekt.services.sitemap_service import (
        detect_site_name,
        discover_sitemap,
        fetch_sitemap,
        fetch_titles,
        get_stats,
        load_from_cache,
        save_to_cache,
        strip_site_name,
    )

    # Determine if URL is a direct sitemap URL or an origin
    direct_sitemap_url = None
    if url:
        parsed = urlparse(url)
        if parsed.path.endswith((".xml", ".xml.gz")):
            direct_sitemap_url = url

    # Get the origin
    if direct_sitemap_url:
        parsed = urlparse(direct_sitemap_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
    else:
        origin = _get_origin(url)

    # Check cache first (unless --refresh)
    result = None
    from_cache = False
    if not refresh:
        result = load_from_cache(origin)
        if result:
            from_cache = True

    # Fetch if no cache hit
    if result is None:
        if direct_sitemap_url:
            sitemap_urls = [direct_sitemap_url]
            discovery_method = "direct"
        else:
            # Auto-discover (may return multiple URLs for multilingual sites)
            sitemap_urls, discovery_method = discover_sitemap(origin)
            if not sitemap_urls:
                if output_json:
                    click.echo(json.dumps({"error": "No sitemap found", "origin": origin}))
                else:
                    print_error(f"No sitemap found for `{origin}`")
                    print_hint("Try specifying the URL directly: `inspekt sitemap https://example.com/sitemap.xml`")
                sys.exit(1)

        # Fetch all discovered sitemaps and merge entries (deduplicate by URL)
        result = fetch_sitemap(sitemap_urls[0], flatten=not no_flatten)
        seen_urls = {e.loc for e in result.entries}
        for extra_url in sitemap_urls[1:]:
            extra = fetch_sitemap(extra_url, flatten=not no_flatten)
            for entry in extra.entries:
                if entry.loc not in seen_urls:
                    result.entries.append(entry)
                    seen_urls.add(entry.loc)
            result.errors.extend(extra.errors)
            result.child_sitemaps.extend(extra.child_sitemaps)

        if len(sitemap_urls) > 1:
            result.source_url = f"{sitemap_urls[0]} (+{len(sitemap_urls) - 1} more)"

        result.discovered_via = discovery_method

        if result.errors and not result.entries and not result.child_sitemaps:
            if output_json:
                click.echo(json.dumps({"errors": result.errors, "origin": origin}))
            else:
                for error in result.errors:
                    print_error(error)
            sys.exit(1)

        # Cache under the browser's origin so lookups match
        # (sitemap origin may differ, e.g., elevenways.be vs www.elevenways.be)
        result.origin = origin
        save_to_cache(result)

    # Debug title fetching — test one URL and report diagnostics
    if debug_titles and result.entries:
        from inspekt.services.sitemap_service import debug_title_fetch
        test_url = result.entries[0].loc
        click.echo(f"  Debugging title fetch for: {test_url}")
        click.echo()
        info = debug_title_fetch(test_url)
        for key, value in info.items():
            click.echo(f"  {key}: {value}")
        return

    # --lang converts to a path filter (e.g., --lang nl → /nl/)
    if lang and not filter_path:
        filter_path = f"/{lang.strip('/')}/"

    # --- Size guardrails and title fetching ---
    total = len(result.entries)

    if total > 50_000 and not output_json:
        print_error(f"This sitemap has {total:,} pages — too large to process")
        print_hint("Use `--filter /section` to work with a subset, or `--stats` for an overview")
        sys.exit(0)

    # Count title status once (used by both guardrails and fetch logic)
    already_titled = sum(1 for e in result.entries if e.title)
    already_checked = sum(1 for e in result.entries if not e.title and e.http_status != 0)
    needs_title = sum(1 for e in result.entries if not e.title and e.http_status == 0)

    # Warn before expensive title fetching
    if not no_titles and needs_title > 0 and not output_json:
        if needs_title > 1000 and total > 10_000:
            print_warning(f"This sitemap has {total:,} pages — fetching titles for {needs_title:,} pages may take several minutes")
            if not click.confirm("  Continue?", default=True):
                print_hint("Use `--no-titles` to skip title fetching, or `--filter /section` to limit scope")
                return
        elif needs_title > 500:
            print_warning(f"Fetching titles for {needs_title:,} pages — this may take a while")

    # Fetch page titles
    if not no_titles and needs_title > 0:
        # Send progress to stderr so it doesn't corrupt --json output
        err = output_json

        if already_titled > 0 or already_checked > 0:
            parts = []
            if already_titled > 0:
                parts.append(f"{already_titled} titles cached")
            if already_checked > 0:
                parts.append(f"{already_checked} unreachable")
            click.echo(f"  {', '.join(parts)} (of {total} total)", err=err)

        import time as _time

        # Progress bar with throttle notification
        bar = click.progressbar(
            length=needs_title,
            label="  Fetching titles",
            show_eta=True,
            show_percent=True,
            fill_char=click.style("\u2588", fg="cyan"),
            empty_char=click.style("\u2591", fg="bright_black"),
            file=sys.stderr if err else None,
        )
        _reassured = False
        _last_pos = 0
        _max_concurrent = 20

        def _progress(completed, total, concurrency):
            nonlocal _reassured, _last_pos
            increment = completed - _last_pos
            if increment > 0:
                bar.update(increment)
                _last_pos = completed
            # Show throttle message once when concurrency has actually been reduced
            if not _reassured and concurrency < _max_concurrent:
                _reassured = True
                click.echo(err=err)
                print_hint(f"Slowing down to avoid overloading the server (concurrency: {concurrency}/{_max_concurrent})")

        bar.__enter__()
        try:
            fetched = fetch_titles(
                result.entries, max_concurrent=_max_concurrent, timeout=10.0, progress_callback=_progress
            )
        finally:
            # Ensure bar completes to 100%
            remaining = needs_title - _last_pos
            if remaining > 0:
                bar.update(remaining)
            bar.__exit__(None, None, None)

        click.echo(f"  {fetched} of {needs_title} titles found", err=err)

        # Cache with raw titles (site name stripping happens below for display)
        save_to_cache(result)

    # Strip the common site name from titles for display. This runs on both
    # fresh and cached results so titles collected by the API (which stores
    # raw titles) are also cleaned. strip_site_name is idempotent.
    if not no_titles and result.entries:
        site_name = detect_site_name(result.entries)
        if site_name:
            for entry in result.entries:
                if entry.title:
                    entry.title = strip_site_name(entry.title, site_name)

    # Handle sitemap index (not flattened)
    if result.is_index and not result.entries:
        if output_json:
            click.echo(json.dumps(result.to_dict(), indent=2))
            return

        click.echo()
        icon = get_icon("Sitemaps") or ""
        if icon:
            icon += " "
        via = f"cache ({result.discovered_via})" if from_cache else result.discovered_via
        for line in wrap_styled_line(
            prefix=f"  {icon}{click.style('Sitemap Index', fg='cyan', bold=True)}  ",
            text=click.style(result.source_url, fg='bright_black'),
        ):
            click.echo(line)
        click.echo(f"  {click.style(f'Discovered via {via}', fg='bright_black')}")
        click.echo()

        # Show child sitemaps as a table
        headers = ["#", "Child Sitemap URL"]
        rows = []
        for i, child_url in enumerate(result.child_sitemaps, 1):
            rows.append([str(i), child_url])

        sitemap_icon = get_icon("Sitemaps")
        table = Table(headers, title=f"Child Sitemaps ({len(result.child_sitemaps)})", icon=sitemap_icon)
        table.set_data(rows)
        table.print_header()
        for row in rows:
            table.print_row(row, colors=["bright_black", None])
        table.print_footer()
        click.echo()

        print_hint("Run without `--no-flatten` to expand all child sitemaps")
        return

    # JSON output
    if output_json:
        if stats:
            output = result.to_dict()
            output["stats"] = get_stats(result)
            click.echo(json.dumps(output, indent=2))
        else:
            click.echo(json.dumps(result.to_dict(), indent=2))
        return

    # Stats mode
    if stats:
        _display_stats(result, get_stats(result))
        return

    # --where: breadcrumb from root to current page
    if where:
        if where not in _WHERE_MODES:
            print_error(f"Unknown --where mode `{where}`. Use one of: {', '.join(_WHERE_MODES)}")
            sys.exit(1)
        _display_where(result, origin, mode=where)
        return

    # --neighbors: parent, siblings, children of current page
    if neighbors:
        _display_neighbors(result, origin)
        return

    # Navigate by index or named target
    if open_target is not None:
        _handle_open_target(open_target, result, origin)
        return

    # --from-here: subtree or scoped interactive from current page
    if from_here:
        _display_from_here(result, origin, flat, interactive)
        return

    # Interactive mode
    if interactive:
        entries = result.entries
        if filter_path:
            entries = [e for e in entries if filter_path.lower() in urlparse(e.loc).path.lower()]

        if not entries:
            print_warning("No URLs to display")
            return

        selected = _interactive_picker([
            {
                "index": i + 1,
                "path": urlparse(e.loc).path or "/",
                "title": e.title,
                "url": e.loc,
                "lastmod": e.lastmod,
            }
            for i, e in enumerate(entries)
        ])
        if selected:
            _navigate_to(selected)
        return

    # Display
    if not result.entries:
        print_warning("Sitemap contains no URLs")
        return

    # For very large sitemaps, skip the tree display and show guidance instead
    if len(result.entries) > 5000 and not flat and not filter_path and not output_json:
        click.echo()
        icon = get_icon("Sitemaps") or ""
        if icon:
            icon += " "
        click.echo(f"  {icon}{click.style('Sitemap', fg='cyan', bold=True)}  {click.style(result.source_url, fg='bright_black')}")
        click.echo(f"  {click.style(f'{len(result.entries):,} URLs', fg='bright_black')}")
        click.echo()
        print_warning(f"This sitemap has {len(result.entries):,} pages — too large to display as a tree")
        click.echo()
        print_hint("Use one of these to explore the sitemap:")
        click.echo(f"    {'`--filter /path`':22s} show only a section")
        click.echo(f"    {'`--lang nl`':22s} show only one language")
        click.echo(f"    {'`-i`':22s} interactive fuzzy search")
        click.echo(f"    {'`--from-here`':22s} subtree from current page")
        click.echo(f"    {'`--where`':22s} show your position in the tree")
        click.echo(f"    {'`--neighbors`':22s} show surrounding pages")
        click.echo(f"    {'`--flat`':22s} flat URL list (scrollable)")
        click.echo(f"    {'`--stats`':22s} sitemap statistics")
        return

    _display_sitemap(result, flat, filter_path, from_cache)


# ============================================================================
# Page-centric display functions
# ============================================================================


def _resolve_current_node(result, origin: str):
    """Resolve the current browser page in the sitemap tree.

    Returns (tree, node, parent, current_path) or exits with an error.
    """
    from inspekt.services.sitemap_service import build_tree, find_node_by_path

    current_path = _get_current_path()
    tree = build_tree(result.entries, origin)
    node, parent = find_node_by_path(tree, current_path)

    if node is None:
        print_error("Current page is not in the sitemap")
        print_hint("Try `inspekt sitemap --refresh` to update the sitemap cache")
        sys.exit(1)

    return tree, node, parent, current_path


def _node_display_name(node) -> str:
    """Get the display name for a node: title if available, else slug (unstyled)."""
    if node.entry and node.entry.title:
        return node.entry.title
    return node.name


def _display_where(result, origin: str, mode: str = "compact"):
    """Show breadcrumb from root to current page, with optional sibling context.

    Modes:
        compact: Single breadcrumb path + children of current node (default)
        nearby:  Windowed siblings (~2 before/after) at each level along the path
        full:    All siblings at every level (guarded for large sitemaps)
    """
    from inspekt.services.sitemap_service import find_ancestors

    tree, node, parent, current_path = _resolve_current_node(result, origin)
    ancestors = find_ancestors(tree, current_path)
    max_width = shutil.get_terminal_size().columns - 2

    if mode == "compact":
        _display_where_compact(ancestors, max_width)
    elif mode == "full":
        if len(result.entries) > 500:
            print_error(f"Sitemap has {len(result.entries)} entries — `--where=full` would be too large")
            print_hint("Use `--where=nearby` for a windowed view of siblings at each level")
            return
        _render_where_levels(ancestors, max_width, windowed=False)
    else:  # nearby
        _render_where_levels(ancestors, max_width, windowed=True)


def _display_where_compact(ancestors, max_width: int):
    """Compact breadcrumb: single path from root to current node + children."""
    click.echo()

    current_node = ancestors[-1]
    max_children_shown = 8

    for depth, ancestor in enumerate(ancestors):
        indent = "  " + "     " * depth
        is_current = ancestor is current_node

        if depth == 0:
            click.echo(f"{indent}{click.style(ancestor.name, fg='cyan', bold=True)}")
        else:
            connector = click.style(f"{ELBOW}{DASH}{DASH} ", fg="bright_black")
            cont = indent + "    "
            if is_current:
                style = {"fg": "white", "bold": True}
                suffix = click.style("  \u2190 you are here", fg="green")
            else:
                style = {"fg": "blue", "bold": True}
                suffix = ""
            for line in wrap_styled_line(
                prefix=f"{indent}{connector}",
                text=click.style(_node_display_name(ancestor), **style),
                suffix=suffix,
                cont_prefix=cont,
                text_style=style,
                max_width=max_width,
            ):
                click.echo(line)

    # Children of current node
    _render_where_children(current_node, len(ancestors), max_width, max_children_shown)

    click.echo()
    print_hint("Use `--where=nearby` to see surrounding pages at each level")
    print_hint("Use `--open parent` to navigate up, or `--open first-child` to go deeper")


def _compute_window(total: int, followed_idx: int, radius: int = 2):
    """Compute an anchored sibling window around the followed node.

    Always includes the first and last sibling for context, plus a window
    of `radius` items before/after the followed node. Gaps between anchors
    and the window are collapsed into "(N more)" markers — but never
    "(1 more)" (just show the item instead).

    Returns a list of render instructions:
        ("node", index)  — render the sibling at this index
        ("more", count)  — render a "(N more)" marker
    """
    if total == 0:
        return []

    # Core window around the followed node
    win_start = max(0, followed_idx - radius)
    win_end = min(total, followed_idx + radius + 1)

    # Build the set of indices to show: anchors + window
    show = set(range(win_start, win_end))
    show.add(0)          # first anchor
    show.add(total - 1)  # last anchor

    # Walk through all indices and build render instructions
    items = []
    i = 0
    while i < total:
        if i in show:
            items.append(("node", i))
            i += 1
        else:
            # Count consecutive hidden items
            gap_start = i
            while i < total and i not in show:
                i += 1
            gap = i - gap_start
            # "Never show (1 more)" — just show the item
            if gap == 1:
                items.append(("node", gap_start))
            else:
                items.append(("more", gap))

    return items


def _render_where_levels(ancestors, max_width: int, windowed: bool):
    """Render a proper nested tree showing windowed siblings at each level.

    At each branching point, the followed ancestor's children are rendered
    inline (nested under it with pipe characters), not after all siblings.
    This produces a real tree structure like _render_tree does.
    """
    click.echo()

    # Root
    root = ancestors[0]
    if len(ancestors) == 1:
        # Current page is root — show with marker and children
        suffix = click.style("  \u2190 you are here", fg="green")
        click.echo(f"{click.style(root.name, fg='cyan', bold=True)}{suffix}")
        _render_where_children_inline(root, "", max_width)
    else:
        click.echo(f"{click.style(root.name, fg='cyan', bold=True)}")
        _render_where_branch(ancestors, depth=1, prefix="", max_width=max_width, windowed=windowed)

    click.echo()
    if windowed:
        print_hint("Use `--where=full` to show all siblings at every level")
    else:
        print_hint("Use `--where=nearby` for a more compact view")
    print_hint("Use `--open parent` to navigate up, or `--open first-child` to go deeper")


def _render_where_branch(ancestors, depth: int, prefix: str, max_width: int, windowed: bool):
    """Recursively render one level of the --where tree.

    Shows a windowed set of siblings at this level. For the followed sibling,
    recurses to render the next level nested underneath with pipe continuation.
    """
    ancestor = ancestors[depth]
    is_final = depth == len(ancestors) - 1
    parent_node = ancestors[depth - 1]

    siblings = sorted(parent_node.children.values(), key=lambda n: n.name.lower())
    followed_idx = next((i for i, s in enumerate(siblings) if s is ancestor), 0)

    if windowed:
        items = _compute_window(len(siblings), followed_idx)
    else:
        items = [("node", i) for i in range(len(siblings))]

    styled_pipe = click.style(PIPE, fg="bright_black")

    for item_idx, (kind, value) in enumerate(items):
        is_last_line = item_idx == len(items) - 1
        conn = click.style(f"{ELBOW}{DASH}{DASH} " if is_last_line else f"{TEE}{DASH}{DASH} ", fg="bright_black")
        child_prefix = prefix + ("    " if is_last_line else f"{styled_pipe}   ")
        cont = child_prefix

        if kind == "more":
            more = click.style(f"({value} more)", fg="bright_black", italic=True)
            click.echo(f"{prefix}{conn}{more}")
        else:
            sibling = siblings[value]
            is_followed = sibling is ancestor
            name = _node_display_name(sibling)

            if is_followed:
                if is_final:
                    style = {"fg": "white", "bold": True}
                    suffix = click.style("  \u2190 you are here", fg="green")
                else:
                    style = {"fg": "blue", "bold": True}
                    suffix = ""
                for line in wrap_styled_line(
                    prefix=f"{prefix}{conn}",
                    text=click.style(name, **style),
                    suffix=suffix,
                    cont_prefix=cont,
                    text_style=style,
                    max_width=max_width,
                ):
                    click.echo(line)

                # Recurse: render children of the followed node inline
                if not is_final:
                    _render_where_branch(ancestors, depth + 1, child_prefix, max_width, windowed)
                else:
                    _render_where_children_inline(ancestor, child_prefix, max_width)
            else:
                # Surrounding siblings: mid-gray (242 in 256-color grayscale)
                for line in wrap_styled_line(
                    prefix=f"{prefix}{conn}",
                    text=click.style(name, fg=242),
                    cont_prefix=cont,
                    text_style={"fg": 242},
                    max_width=max_width,
                ):
                    click.echo(line)

                # Show "(N subpages)" hint if this sibling has children
                if sibling.children:
                    _render_subpage_hint(sibling, child_prefix)


def _render_subpage_hint(node, prefix: str):
    """Show a '(N subpages)' hint under a node. Caller must check node.children first."""
    count = len(node.children)
    label = "subpage" if count == 1 else "subpages"
    conn = click.style(f"{ELBOW}{DASH}{DASH} ", fg="bright_black")
    hint = click.style(f"({count} {label})", fg="bright_black", italic=True)
    click.echo(f"{prefix}{conn}{hint}")


def _render_where_children_inline(node, prefix: str, max_width: int):
    """Render children of the current node with first/last anchoring.

    Shows the first item, a "(N more)" gap, and the last item.
    For 3 or fewer children, all are shown. Rendered in mid-gray (242).
    """
    if not node.children:
        return

    child_nodes = sorted(node.children.values(), key=lambda n: n.name.lower())
    total = len(child_nodes)

    # Show first item, "(N more)" gap, and last item.
    # For small lists (≤3), show all items directly.
    if total <= 3:
        items = [("node", i) for i in range(total)]
    else:
        items = [("node", 0), ("more", total - 2), ("node", total - 1)]

    styled_pipe = click.style(PIPE, fg="bright_black")

    for item_idx, (kind, value) in enumerate(items):
        is_last_line = item_idx == len(items) - 1
        conn = click.style(f"{ELBOW}{DASH}{DASH} " if is_last_line else f"{TEE}{DASH}{DASH} ", fg="bright_black")
        child_prefix = prefix + ("    " if is_last_line else f"{styled_pipe}   ")

        if kind == "more":
            more = click.style(f"({value} more)", fg="bright_black", italic=True)
            click.echo(f"{prefix}{conn}{more}")
        else:
            child = child_nodes[value]
            for line in wrap_styled_line(
                prefix=f"{prefix}{conn}",
                text=click.style(_node_display_name(child), fg=242),
                cont_prefix=child_prefix,
                text_style={"fg": 242},
                max_width=max_width,
            ):
                click.echo(line)

            if child.children:
                _render_subpage_hint(child, child_prefix)


def _render_where_children(node, depth: int, max_width: int, max_shown: int = 8):
    """Render children of a node at the given depth (shared by all --where modes)."""
    if not node.children:
        return

    child_indent = "  " + "     " * depth
    cont = child_indent + "    "
    child_nodes = sorted(node.children.values(), key=lambda n: n.name.lower())
    shown = child_nodes[:max_shown]
    remaining = len(child_nodes) - len(shown)

    for i, child in enumerate(shown):
        is_last = (i == len(shown) - 1) and remaining == 0
        conn = click.style(f"{ELBOW}{DASH}{DASH} " if is_last else f"{TEE}{DASH}{DASH} ", fg="bright_black")
        for line in wrap_styled_line(
            prefix=f"{child_indent}{conn}",
            text=click.style(_node_display_name(child), fg="bright_black"),
            cont_prefix=cont,
            text_style={"fg": "bright_black"},
            max_width=max_width,
        ):
            click.echo(line)

    if remaining > 0:
        conn = click.style(f"{ELBOW}{DASH}{DASH} ", fg="bright_black")
        more = click.style(f"({remaining} more)", fg="bright_black")
        click.echo(f"{child_indent}{conn}{more}")


def _display_neighbors(result, origin: str):
    """Show parent, siblings, and children of the current page (--neighbors)."""
    tree, node, parent, current_path = _resolve_current_node(result, origin)
    max_width = shutil.get_terminal_size().columns - 2

    click.echo()

    # Parent section
    if parent:
        arrow = click.style("\u2191", fg="blue")
        if parent.full_path == "/":
            pstyle = {"fg": "cyan"}
        else:
            pstyle = {"fg": "white"}
        for line in wrap_styled_line(
            prefix=f"  {arrow} Parent: ",
            text=click.style(_node_display_name(parent), **pstyle),
            cont_prefix="             ",
            text_style=pstyle,
            max_width=max_width,
        ):
            click.echo(line)
        click.echo()

    # Siblings section (includes current node, highlighted)
    if parent:
        siblings = sorted(parent.children.values(), key=lambda n: n.name.lower())
        click.echo(click.style("  Siblings:", fg="bright_black"))
        for sibling in siblings:
            if sibling is node:
                for line in wrap_styled_line(
                    prefix=f"  {click.style("► ", fg='green')}",
                    text=click.style(_node_display_name(sibling), fg="white", bold=True),
                    suffix=click.style("  \u2190 you are here", fg="green"),
                    cont_prefix="    ",
                    text_style={"fg": "white", "bold": True},
                    max_width=max_width,
                ):
                    click.echo(line)
            else:
                for line in wrap_styled_line(
                    prefix="    ",
                    text=click.style(_node_display_name(sibling), fg="bright_black"),
                    cont_prefix="    ",
                    text_style={"fg": "bright_black"},
                    max_width=max_width,
                ):
                    click.echo(line)
        click.echo()

    # Children section
    if node.children:
        child_nodes = sorted(node.children.values(), key=lambda n: n.name.lower())
        arrow = click.style("\u2193", fg="blue")
        count = len(child_nodes)
        label = "Child" if count == 1 else "Children"
        click.echo(f"  {arrow} {label} ({count}):")
        for child in child_nodes:
            for line in wrap_styled_line(
                prefix="    ",
                text=click.style(_node_display_name(child), fg="bright_black"),
                cont_prefix="    ",
                text_style={"fg": "bright_black"},
                max_width=max_width,
            ):
                click.echo(line)
    else:
        click.echo(click.style("  No child pages", fg="bright_black"))

    click.echo()
    print_hint("Use `--open next/prev` to move between siblings, `--open parent` to go up")


def _collect_subtree_entries(node) -> list:
    """Recursively collect all SitemapEntry objects in a subtree."""
    entries = []
    if node.entry:
        entries.append(node.entry)
    for child in node.children.values():
        entries.extend(_collect_subtree_entries(child))
    return entries


def _display_from_here(result, origin: str, flat: bool, interactive: bool):
    """Show the subtree from the current page (--from-here)."""
    tree, node, parent, current_path = _resolve_current_node(result, origin)

    subtree_entries = _collect_subtree_entries(node)
    if not subtree_entries:
        print_warning("No pages found under the current page")
        return

    # Scoped interactive picker
    if interactive:
        selected = _interactive_picker([
            {
                "index": i + 1,
                "path": urlparse(e.loc).path or "/",
                "title": e.title,
                "url": e.loc,
                "lastmod": e.lastmod,
            }
            for i, e in enumerate(subtree_entries)
        ])
        if selected:
            _navigate_to(selected)
        return

    # Display the subtree
    click.echo()
    count = len(subtree_entries)
    pages_word = "page" if count == 1 else "pages"
    current_name = _node_display_name(node)
    for line in wrap_styled_line(
        prefix=f"  {click.style('Subtree from', fg='bright_black')} ",
        text=click.style(current_name, fg='cyan', bold=True),
        suffix=f"  {click.style(f'({count} {pages_word})', fg='bright_black')}",
    ):
        click.echo(line)
    click.echo()

    if flat:
        max_width = shutil.get_terminal_size().columns - 2
        for entry in subtree_entries:
            path = urlparse(entry.loc).path or "/"
            title = entry.title
            if title:
                path_suffix = click.style(f"  {path}", fg="bright_black")
                for line in wrap_styled_line(
                    prefix="  ",
                    text=click.style(title, fg="white"),
                    suffix=path_suffix,
                    cont_prefix="  ",
                    text_style={"fg": "white"},
                    max_width=max_width,
                ):
                    click.echo(line)
            else:
                click.echo(f"  {path}")
    else:
        lines = _render_tree(node, is_root=True)
        for line in lines:
            click.echo(f"  {line}")

    click.echo()
    print_hint("Combine with `--interactive` to fuzzy search within this subtree")


def _display_sitemap(result, flat: bool, filter_path: str, from_cache: bool = False):
    """Display sitemap as tree or flat list."""
    click.echo()

    # Header
    icon = get_icon("Sitemaps") or ""
    if icon:
        icon += " "
    via = f"cache ({result.discovered_via})" if from_cache else result.discovered_via
    for line in wrap_styled_line(
        prefix=f"  {icon}{click.style('Sitemap', fg='cyan', bold=True)}  ",
        text=click.style(result.source_url, fg='bright_black'),
    ):
        click.echo(line)
    click.echo(f"  {click.style(f'Discovered via {via}', fg='bright_black')}  {click.style(f'{result.total_urls} URLs', fg='bright_black')}")

    if result.fetch_time > 0 and not from_cache:
        click.echo(f"  {click.style(f'Fetched in {result.fetch_time:.2f}s', fg='bright_black')}")

    click.echo()

    if flat:
        _display_flat(result, filter_path)
    else:
        _display_tree(result, filter_path)

    # Hints
    click.echo()

    # Detect available languages from URL path prefixes
    if not filter_path:
        from inspekt.services.sitemap_service import detect_languages
        langs = detect_languages(result.entries)
        if langs:
            lang_str = ", ".join(f"`{l}`" for l in sorted(langs))
            print_hint(f"Languages detected: {lang_str}. Use `--lang nl` to filter by language")

    if not filter_path and result.total_urls > 50:
        print_hint("Use `--filter /path` to narrow down the tree")
    print_hint("Use `--open N` to navigate by index, or `--open parent/next/prev` for structural navigation")
    print_hint("Use `--interactive` for a searchable picker")


def _display_tree(result, filter_path: str):
    """Render the sitemap as a tree."""
    from inspekt.services.sitemap_service import build_tree

    tree = build_tree(result.entries, result.origin)
    lines = _render_tree(tree, filter_path=filter_path or "")

    for line in lines:
        click.echo(f"  {line}")


def _display_flat(result, filter_path: str):
    """Render the sitemap as a flat numbered list."""
    entries = result.entries

    if filter_path:
        entries = [e for e in entries if filter_path.lower() in urlparse(e.loc).path.lower()]

    # Include Title column if any entry has a title
    has_titles = any(e.title for e in entries)

    if has_titles:
        headers = ["#", "URL", "Title", "Last Modified"]
    else:
        headers = ["#", "URL", "Last Modified", "Priority"]

    rows = []
    for i, entry in enumerate(entries, 1):
        parsed = urlparse(entry.loc)
        path = parsed.path or "/"
        if has_titles:
            rows.append([
                str(i),
                path,
                entry.title or "",
                _format_date(entry.lastmod) if entry.lastmod else "",
            ])
        else:
            rows.append([
                str(i),
                path,
                _format_date(entry.lastmod) if entry.lastmod else "",
                entry.priority or "",
            ])

    icon = get_icon("Sitemaps")
    count_label = f"{len(entries)} URLs"
    if filter_path:
        count_label += f" matching '{filter_path}'"
    table = Table(headers, title=count_label, icon=icon)
    table.set_data(rows)
    table.print_header()
    for row in rows:
        if has_titles:
            colors = ["bright_black", None, "cyan", "bright_black"]
        else:
            colors = ["bright_black", None, "bright_black", "yellow" if row[3] else None]
        table.print_row(row, colors=colors)
    table.print_footer()


def _display_stats(result, stats: dict):
    """Display sitemap statistics."""
    click.echo()
    icon = get_icon("Sitemaps") or ""
    if icon:
        icon += " "
    for line in wrap_styled_line(
        prefix=f"  {icon}{click.style('Sitemap Statistics', fg='cyan', bold=True)}  ",
        text=click.style(result.source_url, fg='bright_black'),
    ):
        click.echo(line)
    click.echo()

    # Summary table
    summary_rows = [
        ["Total URLs", str(stats["total_urls"])],
        ["Child Sitemaps", str(stats.get("child_sitemaps", 0))],
        ["URLs with lastmod", str(stats.get("urls_with_lastmod", 0))],
        ["URLs without lastmod", str(stats.get("urls_without_lastmod", 0))],
    ]
    if stats.get("duplicate_title_groups"):
        summary_rows.append(["Duplicate title groups", str(stats["duplicate_title_groups"])])
        summary_rows.append(["Pages with duplicate titles", str(stats["duplicate_title_entries"])])
    if stats.get("non_200_urls"):
        summary_rows.append(["Non-200 HTTP status", str(stats["non_200_urls"])])

    summary_table = Table(["Metric", "Value"], title="Summary", icon=get_icon("Summary"))
    summary_table.set_data(summary_rows)
    summary_table.print_header()
    for row in summary_rows:
        summary_table.print_row(row)
    summary_table.print_footer()
    click.echo()

    # Depth distribution
    depth_dist = stats.get("depth_distribution", {})
    if depth_dist:
        depth_rows = [[str(depth), str(count)] for depth, count in depth_dist.items()]
        depth_table = Table(["Path Depth", "URL Count"], title="Depth Distribution", icon=get_icon("Layout"))
        depth_table.set_data(depth_rows)
        depth_table.print_header()
        for row in depth_rows:
            depth_table.print_row(row)
        depth_table.print_footer()
        click.echo()

    # Change frequency distribution
    freq_dist = stats.get("changefreq_distribution", {})
    if freq_dist:
        freq_rows = [[freq, str(count)] for freq, count in freq_dist.items()]
        freq_table = Table(["Change Frequency", "URL Count"], title="Change Frequency", icon=get_icon("Summary"))
        freq_table.set_data(freq_rows)
        freq_table.print_header()
        for row in freq_rows:
            freq_table.print_row(row)
        freq_table.print_footer()
        click.echo()

    # Priority distribution
    prio_dist = stats.get("priority_distribution", {})
    if prio_dist:
        prio_rows = [[prio, str(count)] for prio, count in prio_dist.items()]
        prio_table = Table(["Priority", "URL Count"], title="Priority", icon=get_icon("Summary"))
        prio_table.set_data(prio_rows)
        prio_table.print_header()
        for row in prio_rows:
            prio_table.print_row(row)
        prio_table.print_footer()
        click.echo()
