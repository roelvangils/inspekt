"""
Sitemap command - Discover, display, and navigate sitemaps.

Provides a tree view of a site's sitemap.xml, with interactive navigation
and auto-discovery via robots.txt. Supports sitemap index files, caching,
filtering, and direct navigation to any listed URL.
"""

from __future__ import annotations

import json
import sys
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
    Format an ISO date string as a human-friendly relative date.

    '2025-03-17T12:48:04+00:00'   → '1 year ago'
    '2026-01-08T07:29:42.204Z'    → '3 months ago'
    '2026-04-01'                   → '3 days ago'
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
        return humanize.naturaltime(dt)

    except ImportError:
        return iso_str[:10]


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
ELBOW = "\u2514"     # └
DASH = "\u2500"      # ─


def _render_tree(node, prefix: str = "", is_last: bool = True, filter_path: str = "", lines: list | None = None, is_root: bool = True) -> list[str]:
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

    # Root node
    if is_root:
        # Show root entry index if the root itself is a URL in the sitemap
        if node.has_entry:
            idx_str = click.style(f"[{node.entry_index}]", fg="bright_black")
            root_label = f"{click.style(node.name, fg='cyan', bold=True)} {idx_str}"
        else:
            root_label = click.style(node.name, fg="cyan", bold=True)
        lines.append(root_label)

        # Render children
        children = _filtered_children(node, filter_path)
        for i, (name, child) in enumerate(children):
            is_last_child = i == len(children) - 1
            _render_tree(child, "", is_last_child, filter_path, lines, is_root=False)

        return lines

    # Build connector
    connector = f"{ELBOW}{DASH}{DASH} " if is_last else f"{TEE}{DASH}{DASH} "

    # Format the node name
    if node.has_entry:
        idx_str = click.style(f"[{node.entry_index}]", fg="bright_black")

        # Show title instead of slug when available
        if node.entry.title:
            name_str = click.style(node.entry.title, fg="white")
        else:
            name_str = click.style(node.name, fg="white")

        # Add metadata hints (relative date, priority) in dim grey
        meta_parts = []
        if node.entry.lastmod:
            meta_parts.append(click.style(f"({_format_date(node.entry.lastmod)})", fg="bright_black"))
        if node.entry.priority and node.entry.priority != "0.5":
            meta_parts.append(click.style(f"(p={node.entry.priority})", fg="yellow"))

        meta_str = f" {' '.join(meta_parts)}" if meta_parts else ""
        label = f"{prefix}{connector}{idx_str} {name_str}{meta_str}"
    else:
        # Directory node (no URL, just a path segment)
        # Show language name for language-code directories (e.g., "en/" → "English (21 pages)")
        lang_name = _LANG_NAMES.get(node.name.lower())
        if lang_name:
            page_count = _count_entries(node)
            name_str = click.style(lang_name, fg="blue", bold=True)
            pages_word = "page" if page_count == 1 else "pages"
            count_str = click.style(f"({page_count} {pages_word})", fg="bright_black")
            label = f"{prefix}{connector}{name_str} {count_str}"
        else:
            name_str = click.style(f"{node.name}/", fg="blue")
            label = f"{prefix}{connector}{name_str}"

    lines.append(label)

    # Prepare child prefix (must align with the 4-char connector "├── ")
    child_prefix = prefix + ("    " if is_last else f"{PIPE}   ")

    # Render children
    children = _filtered_children(node, filter_path)
    for i, (name, child) in enumerate(children):
        is_last_child = i == len(children) - 1
        _render_tree(child, child_prefix, is_last_child, filter_path, lines, is_root=False)

    return lines


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
# Interactive mode
# ============================================================================

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

    # Build lines for gum: "title  (slug)" — gum searches the full line,
    # so both title and slug are searchable. We map the selected line back to its URL.
    lines = []
    line_to_url = {}
    for item in items:
        title = item.get("title") or item["path"]
        slug = item["path"]
        if item.get("title"):
            display = f"{title}  ({slug})"
        else:
            display = slug
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

            if len(matches) == 1:
                return matches[0]["url"]

            # Show matches — display title if available, slug otherwise
            for item in matches[:20]:
                idx_str = click.style(f"[{item['index']}]", fg="bright_black")
                display = item.get("title") or item["path"]
                click.echo(f"  {idx_str} {display}")

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


# Schemes and hostnames that indicate internal/non-web pages
_INTERNAL_SCHEMES = {"inspekt", "chrome", "chrome-error", "about", "data", "blob", "file"}
_INTERNAL_HOSTS = {"inspekt", "localhost"}


def _get_origin(override_url: str | None) -> str:
    """Get the origin from the browser or an override URL."""
    if override_url:
        parsed = urlparse(override_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        # Assume it's a bare domain
        return f"https://{override_url}"

    executor = get_executor()
    result = executor.execute("window.location.origin", timeout=5.0)

    if not result.get("ok"):
        click.echo(f"Error: Could not get current page URL: {result.get('error')}", err=True)
        sys.exit(1)

    origin = str(result.get("result", ""))
    if isinstance(result.get("result"), dict):
        origin = str(result["result"].get("result", ""))

    if not origin or origin == "null":
        click.echo("Error: No page loaded in the browser", err=True)
        sys.exit(1)

    # Check for internal/non-web URLs (inspekt://, chrome://, http://inspekt, etc.)
    parsed = urlparse(origin)
    if parsed.scheme in _INTERNAL_SCHEMES or parsed.hostname in _INTERNAL_HOSTS:
        print_error("This command requires a real website (http/https)")
        print_hint("Navigate to a website first, then try again")
        sys.exit(0)

    return origin


# ============================================================================
# Main command
# ============================================================================

@click.command()
@click.argument("url", required=False)
@click.option("--flat", is_flag=True, help="Show flat URL list instead of tree")
@click.option("--filter", "filter_path", type=str, help="Filter URLs by path (e.g., /blog)")
@click.option("--lang", type=str, help="Filter by language path prefix (e.g., nl, en, fr)")
@click.option("--open", "open_index", type=int, help="Navigate to URL by index number")
@click.option("--interactive", "-i", is_flag=True, help="Interactive fuzzy search picker")
@click.option("--stats", is_flag=True, help="Show sitemap statistics")
@click.option("--no-flatten", is_flag=True, help="Show sitemap index without expanding child sitemaps")
@click.option("--refresh", is_flag=True, help="Force re-fetch (bypass cache)")
@click.option("--no-titles", is_flag=True, help="Skip fetching page titles")
@click.option("--debug-titles", is_flag=True, hidden=True, help="Debug title fetching")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def sitemap(url, flat, filter_path, lang, open_index, interactive, stats, no_flatten, refresh, no_titles, debug_titles, output_json):
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

    # Fetch page titles on fresh fetches (not from cache — failed titles won't retry)
    if not no_titles and not from_cache and result.entries:
        needs_fetch = any(not e.title for e in result.entries)
        if needs_fetch:
            total = sum(1 for e in result.entries if not e.title)

            # Send progress to stderr so it doesn't corrupt --json output
            err = output_json

            def _progress(completed, total):
                pct = completed * 100 // total
                click.echo(f"\r  Fetching titles\u2026 {completed}/{total} ({pct}%)", nl=False, err=err)

            click.echo(f"  Fetching titles for {total} pages\u2026", err=err)
            fetched = fetch_titles(
                result.entries, max_concurrent=30, timeout=10.0, progress_callback=_progress
            )
            click.echo(f"\r  Fetching titles\u2026 {fetched}/{total} found" + " " * 10, err=err)

            # Strip the common site name from all titles
            site_name = detect_site_name(result.entries)
            if site_name:
                for entry in result.entries:
                    if entry.title:
                        entry.title = strip_site_name(entry.title, site_name)

            # Re-cache with cleaned titles
            save_to_cache(result)

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
        click.echo(f"  {icon}{click.style('Sitemap Index', fg='cyan', bold=True)}  {click.style(result.source_url, fg='bright_black')}")
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

    # Navigate to a specific URL by index
    if open_index is not None:
        if open_index < 1 or open_index > len(result.entries):
            print_error(f"Index {open_index} out of range (1-{len(result.entries)})")
            sys.exit(1)
        entry = result.entries[open_index - 1]
        _navigate_to(entry.loc)
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

    _display_sitemap(result, flat, filter_path, from_cache)


def _display_sitemap(result, flat: bool, filter_path: str, from_cache: bool = False):
    """Display sitemap as tree or flat list."""
    click.echo()

    # Header
    icon = get_icon("Sitemaps") or ""
    if icon:
        icon += " "
    via = f"cache ({result.discovered_via})" if from_cache else result.discovered_via
    click.echo(f"  {icon}{click.style('Sitemap', fg='cyan', bold=True)}  {click.style(result.source_url, fg='bright_black')}")
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
    print_hint("Use `--open N` to navigate to a URL by its number (e.g., `inspekt sitemap --open 5`)")
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
    click.echo(f"  {icon}{click.style('Sitemap Statistics', fg='cyan', bold=True)}  {click.style(result.source_url, fg='bright_black')}")
    click.echo()

    # Summary table
    summary_rows = [
        ["Total URLs", str(stats["total_urls"])],
        ["Child Sitemaps", str(stats.get("child_sitemaps", 0))],
        ["URLs with lastmod", str(stats.get("urls_with_lastmod", 0))],
        ["URLs without lastmod", str(stats.get("urls_without_lastmod", 0))],
    ]

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
