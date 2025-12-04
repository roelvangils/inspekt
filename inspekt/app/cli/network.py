"""
Network inspection commands - View network requests from the browser.

This module provides commands for inspecting network requests using the
Performance API:
- network: Show all network requests in a table
- network script: Filter by script resources
- network stylesheet: Filter by CSS resources
- network fetch: Filter by fetch/XHR requests
- network image: Filter by image resources
- network font: Filter by font resources

Note: Uses Performance API which has limitations (no status codes, headers,
or response bodies). For full HAR export, DevTools must be open.
"""

import json
import sys
from typing import Optional

import click

from inspekt.app.cli.table import Table, format_size, format_time, format_status, get_type_color
from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader


def _get_network_data(executor: BridgeExecutor, loader: ScriptLoader) -> dict:
    """Execute the network script and return the data."""
    try:
        code = loader.load_script_sync("get_network.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        result = executor.execute(code, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        data = result.get("result", {})

        if data.get("error"):
            click.echo(f"Error: {data['error']}", err=True)
            sys.exit(1)

        return data

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _truncate(s: str, max_len: int) -> str:
    """Truncate string to max length with ellipsis."""
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _display_table(entries: list, show_domain: bool = False, summary: dict = None):
    """Display network entries in a formatted ASCII table with auto-width columns."""
    if not entries:
        click.echo("No network requests found.", err=True)
        return

    # Define columns based on options
    if show_domain:
        headers = ["Domain", "Name", "Type", "Size", "Time", "Proto"]
        alignments = ["left", "left", "left", "right", "right", "left"]
    else:
        headers = ["Name", "Type", "Size", "Time", "Proto"]
        alignments = ["left", "left", "right", "right", "left"]

    # Build all rows first for auto-width calculation
    rows = []
    row_colors = []
    total_size = 0
    total_time = 0

    for entry in entries:
        name = entry["name"]
        type_str = entry["type"]
        size_bytes = entry["transferSize"]
        time_ms = entry["timing"]["total"]
        size = format_size(size_bytes)
        time_val = format_time(time_ms)
        protocol = entry["protocol"]

        total_size += size_bytes
        total_time += time_ms

        # Add cached marker to name
        if entry.get("cached"):
            name = name + " (cached)"

        # Get type color
        type_color = get_type_color(type_str)

        if show_domain:
            domain = entry["domain"]
            if entry.get("external"):
                domain = domain + " ↗"
            rows.append([domain, name, type_str, size, time_val, protocol])
            row_colors.append([None, None, type_color, None, None, None])
        else:
            rows.append([name, type_str, size, time_val, protocol])
            row_colors.append([None, type_color, None, None, None])

    # Create table with auto-width and title
    title = f"Network Requests ({len(entries)})"
    table = Table(headers, alignments=alignments, title=title)
    table.set_data(rows)
    table.print_header()

    for values, colors in zip(rows, row_colors):
        table.print_row(values, colors)

    # Print summary row with totals
    if show_domain:
        summary_row = ["Total", f"{len(entries)} requests", "", format_size(total_size), format_time(total_time // len(entries) if entries else 0), ""]
    else:
        summary_row = [f"{len(entries)} requests", "", format_size(total_size), format_time(total_time // len(entries) if entries else 0), ""]
    table.print_summary(summary_row)

    table.print_footer()


def _display_summary(summary: dict):
    """Display summary statistics."""
    click.echo()
    click.echo(click.style("Summary:", bold=True))
    click.echo(f"  Total requests: {summary['totalRequests']}")
    click.echo(f"  Total transfer: {format_size(summary['totalTransferSize'])}")
    click.echo(f"  Average time:   {format_time(summary['averageDuration'])}")

    if summary.get("cachedRequests", 0) > 0:
        click.echo(f"  Cached:         {summary['cachedRequests']}")

    if summary.get("externalRequests", 0) > 0:
        click.echo(f"  External:       {summary['externalRequests']}")

    # Type breakdown
    if summary.get("byType"):
        click.echo()
        click.echo("  By type:")
        for type_name, count in sorted(summary["byType"].items(), key=lambda x: -x[1]):
            click.echo(f"    {type_name}: {count}")

    # Slowest request
    if summary.get("slowestRequest"):
        slow = summary["slowestRequest"]
        click.echo()
        click.echo(f"  Slowest: {_truncate(slow['name'], 40)} ({format_time(slow['duration'])})")

    # Largest request
    if summary.get("largestRequest") and summary["largestRequest"]["size"] > 0:
        large = summary["largestRequest"]
        click.echo(f"  Largest: {_truncate(large['name'], 40)} ({format_size(large['size'])})")


def _try_har_silently(executor: BridgeExecutor) -> Optional[dict]:
    """Try to get HAR data without showing errors.

    Returns HAR data if DevTools is open and data is available,
    otherwise returns None.
    """
    import requests
    import json as json_module

    try:
        response = requests.get(
            "http://127.0.0.1:8765/network/har",
            timeout=5.0  # Short timeout for auto-detection
        )
        try:
            data = response.json()
            # Check if HAR succeeded and has entries
            if data.get("ok") and data.get("entries"):
                return data
        except json_module.JSONDecodeError:
            pass
    except Exception:
        pass

    return None


def _show_devtools_hint():
    """Show a hint about opening DevTools for more information."""
    click.echo()
    click.echo(
        click.style("Tip: ", fg="cyan", bold=True) +
        "Open DevTools (F12) and refresh the page to see HTTP status codes, headers, and error details."
    )


def _run_network_command(
    resource_type: Optional[str] = None,
    output_json: bool = False,
    sort_by: str = "start",
    show_domain: bool = False,
    only_external: bool = False,
    limit: Optional[int] = None,
    force_basic: bool = False,
):
    """Common implementation for network commands."""
    executor = BridgeExecutor()
    loader = ScriptLoader()

    executor.ensure_server_running()

    # Try HAR first (if DevTools is open) - unless force_basic is set
    har_data = None
    using_har = False

    if not force_basic:
        har_data = _try_har_silently(executor)
        if har_data:
            using_har = True

    if using_har and har_data:
        # Use HAR data (richer information with status codes)
        entries = har_data.get("entries", [])
        summary = har_data.get("summary", {})

        # Filter by type if specified
        if resource_type:
            entries = [e for e in entries if e.get("type") == resource_type]
            # Update summary counts
            summary["totalRequests"] = len(entries)
            summary["totalTransferSize"] = sum(e.get("transferSize", 0) for e in entries)

        # Filter external only
        if only_external:
            # Determine page domain from first document entry
            page_domain = None
            for e in entries:
                if e.get("type") == "document":
                    page_domain = e.get("domain")
                    break
            if page_domain:
                entries = [e for e in entries if e.get("domain") != page_domain]

        # Sort entries (HAR uses different field names)
        sort_keys = {
            "start": lambda e: e.get("startedDateTime", ""),
            "time": lambda e: -(e.get("timing", {}).get("total", 0) if isinstance(e.get("timing"), dict) else 0),
            "size": lambda e: -e.get("transferSize", 0),
            "name": lambda e: e.get("name", "").lower(),
            "type": lambda e: e.get("type", ""),
            "status": lambda e: e.get("status", 0),
        }

        if sort_by in sort_keys:
            entries = sorted(entries, key=sort_keys[sort_by])

        # Apply limit
        if limit:
            entries = entries[:limit]

        # Output
        if output_json:
            output = {
                "source": "devtools",
                "url": har_data.get("url"),
                "timestamp": har_data.get("timestamp"),
                "entries": entries,
                "summary": summary,
            }
            click.echo(json.dumps(output, indent=2))
        else:
            _display_har_table(entries, show_domain=show_domain, show_status=True)
            _display_har_summary(summary)
    else:
        # Fall back to Performance API (basic info)
        data = _get_network_data(executor, loader)
        entries = data.get("entries", [])
        summary = data.get("summary", {})

        # Filter by type if specified
        if resource_type:
            entries = [e for e in entries if e["type"] == resource_type]
            # Update summary counts
            summary["totalRequests"] = len(entries)
            summary["totalTransferSize"] = sum(e["transferSize"] for e in entries)

        # Filter external only
        if only_external:
            entries = [e for e in entries if e["external"]]

        # Sort entries
        sort_keys = {
            "start": lambda e: e["startTime"],
            "time": lambda e: -e["timing"]["total"],
            "size": lambda e: -e["transferSize"],
            "name": lambda e: e["name"].lower(),
            "type": lambda e: e["type"],
        }

        if sort_by in sort_keys:
            entries = sorted(entries, key=sort_keys[sort_by])

        # Apply limit
        if limit:
            entries = entries[:limit]

        # Output
        if output_json:
            output = {
                "source": "performance_api",
                "url": data.get("url"),
                "timestamp": data.get("timestamp"),
                "entries": entries,
                "summary": summary,
            }
            click.echo(json.dumps(output, indent=2))
        else:
            _display_table(entries, show_domain=show_domain)
            _display_summary(summary)
            # Show hint about DevTools
            _show_devtools_hint()


@click.group(invoke_without_command=True)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--sort",
    "sort_by",
    type=click.Choice(["start", "time", "size", "name", "type"]),
    default="start",
    help="Sort by field (default: start time)",
)
@click.option("--domain", "show_domain", is_flag=True, help="Show domain column")
@click.option("--external", "only_external", is_flag=True, help="Show only external requests")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of results")
@click.pass_context
def network(ctx, output_json, sort_by, show_domain, only_external, limit):
    """
    Show network requests from the current page.

    Automatically detects if Chrome DevTools is open. When DevTools is open,
    shows enhanced data including HTTP status codes (200, 404, 500, etc.) and
    headers. Otherwise falls back to the Performance API.

    Use subcommands to filter by resource type:
        inspekt network script      # Only scripts
        inspekt network stylesheet  # Only CSS
        inspekt network fetch       # Only fetch/XHR
        inspekt network image       # Only images
        inspekt network font        # Only fonts
        inspekt network har         # Force HAR mode (DevTools required)

    Examples:
        inspekt network                    # All requests (auto-detects DevTools)
        inspekt network --json             # Output as JSON
        inspekt network --sort=time        # Sort by duration (slowest first)
        inspekt network --sort=size        # Sort by size (largest first)
        inspekt network --external         # Only external requests
        inspekt network --domain           # Show domain column
        inspekt network -n 20              # Limit to 20 results
    """
    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["output_json"] = output_json
    ctx.obj["sort_by"] = sort_by
    ctx.obj["show_domain"] = show_domain
    ctx.obj["only_external"] = only_external
    ctx.obj["limit"] = limit

    # If no subcommand, show all
    if ctx.invoked_subcommand is None:
        _run_network_command(
            output_json=output_json,
            sort_by=sort_by,
            show_domain=show_domain,
            only_external=only_external,
            limit=limit,
        )


@network.command(name="script")
@click.pass_context
def network_script(ctx):
    """Show only JavaScript resources."""
    _run_network_command(
        resource_type="script",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="stylesheet")
@click.pass_context
def network_stylesheet(ctx):
    """Show only CSS resources."""
    _run_network_command(
        resource_type="stylesheet",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="css")
@click.pass_context
def network_css(ctx):
    """Show only CSS resources (alias for stylesheet)."""
    _run_network_command(
        resource_type="stylesheet",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="fetch")
@click.pass_context
def network_fetch(ctx):
    """Show only fetch/XHR requests."""
    _run_network_command(
        resource_type="fetch",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="xhr")
@click.pass_context
def network_xhr(ctx):
    """Show only XHR requests."""
    _run_network_command(
        resource_type="xhr",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="image")
@click.pass_context
def network_image(ctx):
    """Show only image resources."""
    _run_network_command(
        resource_type="image",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="font")
@click.pass_context
def network_font(ctx):
    """Show only font resources."""
    _run_network_command(
        resource_type="font",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="document")
@click.pass_context
def network_document(ctx):
    """Show only document/HTML resources."""
    _run_network_command(
        resource_type="document",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="svg")
@click.pass_context
def network_svg(ctx):
    """Show only SVG resources."""
    _run_network_command(
        resource_type="svg",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="video")
@click.pass_context
def network_video(ctx):
    """Show only video resources."""
    _run_network_command(
        resource_type="video",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


@network.command(name="audio")
@click.pass_context
def network_audio(ctx):
    """Show only audio resources."""
    _run_network_command(
        resource_type="audio",
        output_json=ctx.obj["output_json"],
        sort_by=ctx.obj["sort_by"],
        show_domain=ctx.obj["show_domain"],
        only_external=ctx.obj["only_external"],
        limit=ctx.obj["limit"],
    )


# _format_status is now imported from table.py as format_status


def _get_har_data(executor: BridgeExecutor) -> dict:
    """Get HAR data from DevTools via bridge server."""
    import json
    import requests

    try:
        response = requests.get(
            "http://127.0.0.1:8765/network/har",
            timeout=20.0
        )
        try:
            return response.json()
        except json.JSONDecodeError as e:
            # Show what we actually received for debugging
            text = response.text[:200] if len(response.text) > 200 else response.text
            return {
                "ok": False,
                "error": f"Invalid JSON response: {e}",
                "hint": f"Response preview: {text!r}"
            }
    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "Bridge server not running. Start it with: inspekt start"
        }
    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "error": "Request timed out. Is DevTools open?"
        }
    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }


def _display_har_table(entries: list, show_domain: bool = False, show_status: bool = True):
    """Display HAR entries in a formatted ASCII table with auto-width columns."""
    if not entries:
        click.echo("No network requests found.", err=True)
        return

    # Define columns based on options
    if show_domain and show_status:
        headers = ["Domain", "Name", "Status", "Type", "Size", "Time"]
        alignments = ["left", "left", "right", "left", "right", "right"]
    elif show_domain:
        headers = ["Domain", "Name", "Type", "Size", "Time"]
        alignments = ["left", "left", "left", "right", "right"]
    elif show_status:
        headers = ["Name", "Status", "Type", "Size", "Time"]
        alignments = ["left", "right", "left", "right", "right"]
    else:
        headers = ["Name", "Type", "Size", "Time"]
        alignments = ["left", "left", "right", "right"]

    # Build all rows first for auto-width calculation
    rows = []
    row_colors = []
    total_size = 0
    total_time = 0

    for entry in entries:
        name = entry.get("name", "")
        status = entry.get("status", 0)
        type_str = entry.get("type", "other")
        size_bytes = entry.get("transferSize", 0)
        timing = entry.get("timing", {})
        time_ms = timing.get("total", 0) if isinstance(timing, dict) else 0
        size = format_size(size_bytes)
        time_val = format_time(time_ms)

        total_size += size_bytes
        total_time += time_ms

        # Add cached marker to name
        if entry.get("fromCache"):
            name = name + " (cached)"

        # Get colors
        type_color = get_type_color(type_str)

        # Build row based on columns
        if show_domain and show_status:
            domain = entry.get("domain", "")
            # Format status with color (but raw value for table)
            status_color = None
            if status >= 500:
                status_color = "red"
            elif status >= 400:
                status_color = "yellow"
            elif status >= 300:
                status_color = "cyan"
            elif status >= 200:
                status_color = "green"

            rows.append([domain, name, str(status) if status else "-", type_str, size, time_val])
            row_colors.append([None, None, status_color, type_color, None, None])
        elif show_domain:
            domain = entry.get("domain", "")
            rows.append([domain, name, type_str, size, time_val])
            row_colors.append([None, None, type_color, None, None])
        elif show_status:
            status_color = None
            if status >= 500:
                status_color = "red"
            elif status >= 400:
                status_color = "yellow"
            elif status >= 300:
                status_color = "cyan"
            elif status >= 200:
                status_color = "green"

            rows.append([name, str(status) if status else "-", type_str, size, time_val])
            row_colors.append([None, status_color, type_color, None, None])
        else:
            rows.append([name, type_str, size, time_val])
            row_colors.append([None, type_color, None, None])

    # Create table with auto-width and title
    title = f"Network Requests ({len(entries)})"
    table = Table(headers, alignments=alignments, title=title)
    table.set_data(rows)
    table.print_header()

    for values, colors in zip(rows, row_colors):
        table.print_row(values, colors)

    # Print summary row with totals
    avg_time = total_time // len(entries) if entries else 0
    if show_domain and show_status:
        summary_row = ["Total", f"{len(entries)} requests", "", "", format_size(total_size), format_time(avg_time)]
    elif show_domain:
        summary_row = ["Total", f"{len(entries)} requests", "", format_size(total_size), format_time(avg_time)]
    elif show_status:
        summary_row = [f"{len(entries)} requests", "", "", format_size(total_size), format_time(avg_time)]
    else:
        summary_row = [f"{len(entries)} requests", "", format_size(total_size), format_time(avg_time)]
    table.print_summary(summary_row)

    table.print_footer()


def _display_har_summary(summary: dict):
    """Display HAR summary statistics."""
    click.echo()
    click.echo(click.style("Summary:", bold=True))
    click.echo(f"  Total requests: {summary.get('totalRequests', 0)}")
    click.echo(f"  Total transfer: {format_size(summary.get('totalTransferSize', 0))}")
    click.echo(f"  Average time:   {format_time(summary.get('averageDuration', 0))}")

    # Status breakdown
    by_status = summary.get("byStatus", {})
    if by_status:
        click.echo()
        click.echo("  By status:")
        for status_group, count in sorted(by_status.items(), key=lambda x: int(x[0])):
            status_label = {
                "200": "2xx (Success)",
                "300": "3xx (Redirect)",
                "400": "4xx (Client Error)",
                "500": "5xx (Server Error)",
            }.get(str(status_group), f"{status_group}xx")
            click.echo(f"    {status_label}: {count}")

    # Error counts
    if summary.get("errors", 0) > 0:
        click.echo(click.style(f"  Errors:         {summary['errors']}", fg="red"))

    if summary.get("redirects", 0) > 0:
        click.echo(f"  Redirects:      {summary['redirects']}")

    if summary.get("cached", 0) > 0:
        click.echo(f"  Cached:         {summary['cached']}")

    # Type breakdown
    by_type = summary.get("byType", {})
    if by_type:
        click.echo()
        click.echo("  By type:")
        for type_name, count in sorted(by_type.items(), key=lambda x: -x[1]):
            click.echo(f"    {type_name}: {count}")

    # Slowest request
    slowest = summary.get("slowestRequest")
    if slowest:
        click.echo()
        status_str = f" ({slowest.get('status', '')})" if slowest.get('status') else ""
        click.echo(f"  Slowest: {_truncate(slowest.get('name', ''), 35)}{status_str} ({format_time(slowest.get('duration', 0))})")

    # Largest request
    largest = summary.get("largestRequest")
    if largest and largest.get("size", 0) > 0:
        status_str = f" ({largest.get('status', '')})" if largest.get('status') else ""
        click.echo(f"  Largest: {_truncate(largest.get('name', ''), 35)}{status_str} ({format_size(largest.get('size', 0))})")


@network.command(name="har")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--sort",
    "sort_by",
    type=click.Choice(["start", "time", "size", "name", "type", "status"]),
    default="start",
    help="Sort by field (default: start time)",
)
@click.option("--domain", "show_domain", is_flag=True, help="Show domain column")
@click.option("--external", "only_external", is_flag=True, help="Show only external requests")
@click.option("--errors", "only_errors", is_flag=True, help="Show only failed requests (4xx/5xx)")
@click.option("--limit", "-n", type=int, default=None, help="Limit number of results")
@click.option(
    "--type",
    "resource_type",
    type=click.Choice(["script", "stylesheet", "fetch", "image", "font", "document"]),
    default=None,
    help="Filter by resource type",
)
@click.option("--raw", "raw_har", is_flag=True, help="Output raw HAR format (for import into other tools)")
def network_har(output_json, sort_by, show_domain, only_external, only_errors, limit, resource_type, raw_har):
    """
    Get full network data from DevTools (HAR format).

    This command requires Chrome DevTools to be open (F12) for the active tab.
    It provides complete network data including:

    - HTTP status codes (200, 404, 500, etc.)
    - Request and response headers
    - Full timing breakdown
    - Initiator information

    If DevTools is not open, you'll get an error. Use `inspekt network`
    for basic network data that works without DevTools.

    Examples:
        inspekt network har                    # Full HAR data
        inspekt network har --json             # Output as JSON
        inspekt network har --errors           # Only failed requests
        inspekt network har --type=script      # Only scripts
        inspekt network har --sort=status      # Sort by status code
        inspekt network har --raw              # Raw HAR for export
    """
    executor = BridgeExecutor()
    executor.ensure_server_running()

    data = _get_har_data(executor)

    if not data.get("ok", False):
        error = data.get("error", "Unknown error")
        hint = data.get("hint", "")
        click.echo(click.style(f"Error: {error}", fg="red"), err=True)
        if hint:
            click.echo(click.style(f"Hint: {hint}", fg="yellow"), err=True)
        sys.exit(1)

    # If raw HAR requested, output and exit
    if raw_har:
        raw_data = data.get("rawHAR", data)
        click.echo(json.dumps(raw_data, indent=2))
        return

    entries = data.get("entries", [])
    summary = data.get("summary", {})

    # Filter by type
    if resource_type:
        entries = [e for e in entries if e.get("type") == resource_type]

    # Filter external only
    if only_external:
        domain = None
        # Try to get current domain from first document entry
        for e in entries:
            if e.get("type") == "document":
                domain = e.get("domain")
                break
        if domain:
            entries = [e for e in entries if e.get("domain") != domain]

    # Filter errors only
    if only_errors:
        entries = [e for e in entries if e.get("status", 0) >= 400]

    # Sort entries
    sort_keys = {
        "start": lambda e: e.get("startedDateTime", ""),
        "time": lambda e: -(e.get("timing", {}).get("total", 0) if isinstance(e.get("timing"), dict) else 0),
        "size": lambda e: -e.get("transferSize", 0),
        "name": lambda e: e.get("name", "").lower(),
        "type": lambda e: e.get("type", ""),
        "status": lambda e: e.get("status", 0),
    }

    if sort_by in sort_keys:
        entries = sorted(entries, key=sort_keys[sort_by])

    # Apply limit
    if limit:
        entries = entries[:limit]

    # Update summary for filtered results
    if resource_type or only_external or only_errors:
        summary["totalRequests"] = len(entries)
        summary["totalTransferSize"] = sum(e.get("transferSize", 0) for e in entries)

    # Output
    if output_json:
        output = {
            "source": "devtools",
            "url": data.get("url"),
            "timestamp": data.get("timestamp"),
            "entries": entries,
            "summary": summary,
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(click.style("HAR Data (DevTools)", bold=True, fg="green"))
        click.echo(click.style("Status codes and headers available!", fg="bright_black"))
        click.echo()
        _display_har_table(entries, show_domain=show_domain)
        _display_har_summary(summary)


# Export for programmatic use
def get_network_requests(
    resource_type: Optional[str] = None,
    only_external: bool = False,
) -> dict:
    """
    Get network requests programmatically.

    Args:
        resource_type: Filter by type (script, stylesheet, fetch, image, font, etc.)
        only_external: Only return external requests

    Returns:
        Dict with 'entries' list and 'summary' statistics
    """
    executor = BridgeExecutor()
    loader = ScriptLoader()

    executor.ensure_server_running()
    data = _get_network_data(executor, loader)

    entries = data.get("entries", [])

    if resource_type:
        entries = [e for e in entries if e["type"] == resource_type]

    if only_external:
        entries = [e for e in entries if e["external"]]

    return {
        "url": data.get("url"),
        "timestamp": data.get("timestamp"),
        "entries": entries,
        "summary": data.get("summary", {}),
    }
