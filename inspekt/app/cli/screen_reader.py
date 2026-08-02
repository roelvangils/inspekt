"""
Screen reader simulator CLI commands.

Provides the `inspekt sr` command group with:
- sr walk: Walk through a page with screen reader announcements
- sr compare: Side-by-side comparison of JAWS, NVDA, and VoiceOver
- sr announce: Announce a specific element
"""

import asyncio
import json
import sys

import click

from inspekt.app.cli.icons import get_icon, get_indicator

# ── Shared options for enrichment flags ───────────────────────


def _enrichment_options(f):
    """Shared Click options for controlling which extra columns to show."""
    f = click.option(
        "--show-description",
        is_flag=True,
        help="Show aria-describedby / aria-description",
    )(f)
    f = click.option(
        "--show-focusable",
        is_flag=True,
        help="Show whether each element is keyboard-focusable",
    )(f)
    f = click.option(
        "--show-tooltip",
        is_flag=True,
        help="Show title attribute (when not used as name)",
    )(f)
    f = click.option(
        "--show-href",
        is_flag=True,
        help="Show link URLs",
    )(f)
    f = click.option(
        "--show-value",
        is_flag=True,
        help="Show form field values and placeholders",
    )(f)
    f = click.option(
        "--show-table-headers",
        is_flag=True,
        help="Show associated table column/row headers",
    )(f)
    f = click.option(
        "--show-secondary",
        is_flag=True,
        help="Show secondary announcements (description/tooltip per SR)",
    )(f)
    f = click.option(
        "--show-bugs",
        is_flag=True,
        help="Flag known screen reader bugs that affect elements",
    )(f)
    f = click.option(
        "--show-all",
        is_flag=True,
        help="Show all enriched information",
    )(f)
    return f


def _build_show_flags(show_description, show_focusable, show_tooltip, show_href,
                      show_value, show_table_headers, show_secondary, show_bugs,
                      show_all):
    """Build a dict of which enrichment columns to display."""
    if show_all:
        return {
            "description": True, "focusable": True, "tooltip": True,
            "href": True, "value": True, "table_headers": True,
            "secondary": True, "bugs": True,
        }
    return {
        "description": show_description,
        "focusable": show_focusable,
        "tooltip": show_tooltip,
        "href": show_href,
        "value": show_value,
        "table_headers": show_table_headers,
        "secondary": show_secondary,
        "bugs": show_bugs,
    }


# ── Command Group ──────────────────────────────────────────────


@click.group(invoke_without_command=True)
@click.pass_context
def sr(ctx):
    """Screen reader simulator.

    Simulate how JAWS, NVDA, and VoiceOver would announce page content.

    \b
    Commands:
        walk      Walk the page in reading order
        compare   Side-by-side comparison of all three SRs
        announce  Announce a specific element

    \b
    Examples:
        inspekt sr walk
        inspekt sr walk --screen-reader jaws --show-focusable
        inspekt sr compare --show-all
        inspekt sr announce --selector 'h1'
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ── Walk Command ───────────────────────────────────────────────


@sr.command()
@click.option(
    "--screen-reader",
    "-s",
    type=click.Choice(["jaws", "nvda", "voiceover", "all"]),
    default="all",
    help="Screen reader to simulate (default: all)",
)
@click.option(
    "--verbosity",
    "-V",
    type=click.Choice(["high", "medium", "low"]),
    default="high",
    help="Verbosity level (default: high)",
)
@click.option(
    "--max-elements",
    "-n",
    type=int,
    default=500,
    help="Maximum elements to walk (default: 500)",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json", "diff"]),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--json",
    "-j",
    "json_flag",
    is_flag=True,
    help="Output as JSON (shortcut for --format json)",
)
@_enrichment_options
@click.pass_context
def walk(ctx, screen_reader, verbosity, max_elements, output_format, json_flag,
         show_description, show_focusable, show_tooltip, show_href,
         show_value, show_table_headers, show_secondary, show_bugs,
         show_all):
    """Walk through the page showing screen reader announcements.

    Linearizes the page into reading order and shows what each screen
    reader would announce for every element.

    \b
    Examples:
        inspekt sr walk
        inspekt sr walk --screen-reader jaws
        inspekt sr walk -s nvda --show-focusable --show-description
        inspekt sr walk --show-all
        inspekt sr walk --format json
    """
    from inspekt.core.handlers.screen_reader import sr_walk
    from inspekt.core.schemas.screen_reader import SRWalkParams

    params = SRWalkParams(
        screen_reader=screen_reader,
        verbosity=verbosity,
        max_elements=max_elements,
    )

    result = asyncio.run(sr_walk(params))

    if not result.success:
        from inspekt.app.cli.table import print_error

        print_error(result.error or "Walk failed")
        sys.exit(1)

    show = _build_show_flags(
        show_description, show_focusable, show_tooltip, show_href,
        show_value, show_table_headers, show_secondary, show_bugs,
        show_all,
    )

    if json_flag:
        output_format = "json"

    if output_format == "json":
        from inspekt.app.cli.table import print_json
        print_json(result.model_dump(), summary=f"sr walk ({screen_reader})")
        return

    if output_format == "diff" or screen_reader == "all":
        _print_comparison(result, show=show)
    else:
        _print_single_sr(result, screen_reader, show=show)

    _emit_sr_walk_signal(result, screen_reader)


# ── Compare Command ────────────────────────────────────────────


@sr.command()
@click.option(
    "--verbosity",
    "-V",
    type=click.Choice(["high", "medium", "low"]),
    default="high",
    help="Verbosity level (default: high)",
)
@click.option(
    "--max-elements",
    "-n",
    type=int,
    default=500,
    help="Maximum elements to walk (default: 500)",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    help="Output format (default: table)",
)
@click.option(
    "--json",
    "-j",
    "json_flag",
    is_flag=True,
    help="Output as JSON (shortcut for --format json)",
)
@click.option(
    "--differences-only",
    "-d",
    is_flag=True,
    help="Only show elements where screen readers differ",
)
@_enrichment_options
@click.pass_context
def compare(ctx, verbosity, max_elements, output_format, json_flag, differences_only,
            show_description, show_focusable, show_tooltip, show_href,
            show_value, show_table_headers, show_secondary, show_bugs,
         show_all):
    """Compare announcements across JAWS, NVDA, and VoiceOver.

    Shows a side-by-side comparison of how each screen reader would
    announce every element on the page.

    \b
    Examples:
        inspekt sr compare
        inspekt sr compare --differences-only
        inspekt sr compare --show-focusable --show-description
        inspekt sr compare --show-all
    """
    from inspekt.core.handlers.screen_reader import sr_walk
    from inspekt.core.schemas.screen_reader import SRWalkParams

    params = SRWalkParams(
        screen_reader="all",
        verbosity=verbosity,
        max_elements=max_elements,
    )

    result = asyncio.run(sr_walk(params))

    if not result.success:
        from inspekt.app.cli.table import print_error

        print_error(result.error or "Compare failed")
        sys.exit(1)

    show = _build_show_flags(
        show_description, show_focusable, show_tooltip, show_href,
        show_value, show_table_headers, show_secondary, show_bugs,
        show_all,
    )

    if json_flag:
        output_format = "json"

    if output_format == "json":
        from inspekt.app.cli.table import print_json
        print_json(result.model_dump(), summary="sr compare")
        return

    _print_comparison(result, differences_only=differences_only, show=show)
    _emit_sr_walk_signal(result, "all", differences_only=differences_only)


# ── Announce Command ───────────────────────────────────────────


@sr.command()
@click.option(
    "--selector",
    "-s",
    default=None,
    help="CSS selector of element to announce (default: focused element)",
)
@click.option(
    "--screen-reader",
    "-r",
    type=click.Choice(["jaws", "nvda", "voiceover", "all"]),
    default="all",
    help="Screen reader to simulate (default: all)",
)
@click.option(
    "--verbosity",
    "-V",
    type=click.Choice(["high", "medium", "low"]),
    default="high",
    help="Verbosity level (default: high)",
)
@click.pass_context
def announce(ctx, selector, screen_reader, verbosity):
    """Announce a specific element.

    Shows what JAWS, NVDA, and VoiceOver would say for the given element.
    If no selector is provided, announces the currently focused element.

    \b
    Examples:
        inspekt sr announce
        inspekt sr announce --selector 'h1'
        inspekt sr announce --selector 'button.submit' -r jaws
    """
    from inspekt.core.handlers.screen_reader import sr_announce
    from inspekt.core.schemas.screen_reader import SRAnnounceParams

    params = SRAnnounceParams(
        selector=selector,
        screen_reader=screen_reader,
        verbosity=verbosity,
    )

    result = asyncio.run(sr_announce(params))

    if not result.success:
        from inspekt.app.cli.table import print_error

        print_error(result.error or "Announce failed")
        sys.exit(1)

    _print_announce(result)


# ── Copyable-data signal (VM terminal toast) ──────────────────


def _emit_sr_walk_signal(result, screen_reader: str, differences_only: bool = False) -> None:
    """Emit a "Data ready to copy" toast for sr walk/compare output.

    Builds a plain-text Markdown table and uses the full model_dump as JSON.
    No-op outside the VM (gated inside emit_copyable_data).
    """
    from inspekt.app.cli.table import emit_copyable_data

    items = result.announcements
    if differences_only:
        items = [a for a in items if len({a.jaws, a.nvda, a.voiceover}) > 1]
    if not items:
        return

    if screen_reader in ("jaws", "nvda", "voiceover"):
        headers = ["#", "Role", "Announcement"]
        rows = [
            [str(a.index), a.role, getattr(a, screen_reader, "") or ""]
            for a in items
        ]
    else:
        headers = ["#", "Element", "JAWS", "NVDA", "VoiceOver"]
        rows = [
            [
                str(a.index),
                f"{a.role} {a.name}".strip() if a.name else a.role,
                a.jaws or "",
                a.nvda or "",
                a.voiceover or "",
            ]
            for a in items
        ]

    summary = f"{len(items)} announcement{'s' if len(items) != 1 else ''}"
    emit_copyable_data(
        headers=headers,
        rows=rows,
        json_data=result.model_dump(),
        summary=summary,
    )


# ── Enrichment Formatting Helpers ─────────────────────────────


def _format_enrichment_suffix(a, show):
    """Build enrichment details to append to the announcement text.

    Returns a dimmed string to show below the announcement, or None.
    Only shows positive signals (focusable yes, not "not focusable" for every element).
    """
    parts = []

    if show.get("focusable") and a.is_focusable:
        tab_info = f" (tabindex={a.tab_index})" if a.tab_index is not None and a.tab_index != 0 else ""
        parts.append(click.style(f"focusable{tab_info}", fg="green"))

    if show.get("description") and a.description:
        desc_short = a.description[:60] + "…" if len(a.description) > 60 else a.description
        parts.append(click.style(f"desc: {desc_short}", fg="yellow"))

    if show.get("tooltip") and a.tooltip:
        tooltip_short = a.tooltip[:60] + "…" if len(a.tooltip) > 60 else a.tooltip
        parts.append(click.style(f"title: {tooltip_short}", fg="yellow"))

    if show.get("href") and a.href:
        href_short = a.href[:70] + "…" if len(a.href) > 70 else a.href
        parts.append(click.style(f"→ {href_short}", dim=True))

    if show.get("value"):
        if a.value:
            parts.append(click.style(f'value: "{a.value}"', fg="blue"))
        if a.placeholder:
            parts.append(click.style(f'placeholder: "{a.placeholder}"', dim=True))

    if show.get("table_headers"):
        if a.table_column_header:
            parts.append(click.style(f"col: {a.table_column_header}", fg="magenta"))
        if a.table_row_header:
            parts.append(click.style(f"row: {a.table_row_header}", fg="magenta"))

    if show.get("secondary"):
        secondary = a.jaws_secondary or a.nvda_secondary or a.voiceover_secondary
        if secondary:
            sec_short = secondary[:60] + "…" if len(secondary) > 60 else secondary
            parts.append(click.style(f"[after pause] {sec_short}", fg="yellow", dim=True))

    if show.get("bugs") and a.known_bugs:
        from inspekt.core.handlers.screen_reader import get_bug_details

        for bug_id in a.known_bugs:
            bug = get_bug_details(bug_id)
            if bug:
                severity_colors = {
                    "critical": "red", "serious": "red",
                    "moderate": "yellow", "minor": "bright_black",
                }
                color = severity_colors.get(bug.get("severity", ""), "yellow")
                desc = bug.get("description", "")
                desc_short = desc[:80] + "…" if len(desc) > 80 else desc
                parts.append(click.style(
                    f"Bug [{bug.get('severity', '?')}]: {desc_short}",
                    fg=color,
                ))

    return "  ".join(parts) if parts else None


def _make_detail_row(enrichment, num_columns):
    """Build a detail row: empty cells except the last one with enrichment text."""
    row = [""] * num_columns
    row[-1] = enrichment
    return row


# ── Output Formatting ─────────────────────────────────────────


def _print_comparison(result, differences_only=False, show=None):
    """Print side-by-side comparison of screen reader announcements."""
    from inspekt.app.cli.table import Table, print_hint

    show = show or {}
    has_enrichment = any(show.values())

    click.echo()

    items = result.announcements
    if differences_only:
        items = [
            a for a in items
            if len({a.jaws, a.nvda, a.voiceover}) > 1
        ]

    if not items:
        if differences_only:
            click.echo(
                f"  {get_indicator('pass')} All screen readers announce the same content."
            )
        else:
            click.echo("  No elements found on the page.")
        click.echo()
        return

    # Title
    title = "Screen Reader Comparison"
    if result.title:
        title += f" — {result.title}"
    if differences_only:
        title += " (differences only)"

    table = Table(
        headers=["#", "Element", "JAWS", "NVDA", "VoiceOver"],
        title=title,
        icon=get_indicator("accessibility"),
    )

    # Build rows with optional enrichment detail rows
    display_rows = []  # list of (row_data, is_detail_row)
    for a in items:
        jaws_text = a.jaws or ""
        nvda_text = a.nvda or ""
        vo_text = a.voiceover or ""

        all_same = jaws_text == nvda_text == vo_text

        # Build element description
        element_desc = click.style(a.role, fg="cyan")
        if a.name:
            name_short = a.name[:30] + "…" if len(a.name) > 30 else a.name
            element_desc += f" {name_short}"

        if all_same and not differences_only:
            display_rows.append(([
                str(a.index), element_desc, jaws_text,
                click.style("↑ same", dim=True),
                click.style("↑ same", dim=True),
            ], False))
        else:
            display_rows.append(([
                str(a.index), element_desc, jaws_text, nvda_text, vo_text,
            ], False))

        # Add enrichment detail row if applicable
        enrichment = _format_enrichment_suffix(a, show) if has_enrichment else None
        if enrichment:
            display_rows.append((_make_detail_row(enrichment, 5), True))

    # For set_data, only pass non-detail rows (detail rows have empty cells
    # that shouldn't influence column width calculation)
    data_rows = [r for r, is_detail in display_rows if not is_detail]
    table.set_data(data_rows)
    table.print_header()
    for row, is_detail in display_rows:
        if is_detail:
            # Print detail row with dimmed style
            table.print_row(row, colors=[None, None, None, None, None])
        else:
            table.print_row(row)
    table.print_footer()

    # Summary
    click.echo()
    _print_summary(result)

    click.echo()

    # Tips
    if not has_enrichment:
        print_hint("Use `--show-all` to include description, focusable, tooltip, links, and more")
    if not differences_only:
        print_hint("Use `--differences-only` to show only elements where SRs differ")


def _print_single_sr(result, screen_reader, show=None):
    """Print announcements for a single screen reader."""
    from inspekt.app.cli.table import Table, print_hint

    show = show or {}
    has_enrichment = any(show.values())

    click.echo()

    sr_names = {"jaws": "JAWS", "nvda": "NVDA", "voiceover": "VoiceOver"}
    sr_name = sr_names.get(screen_reader, screen_reader)

    title = f"{sr_name} Announcements"
    if result.title:
        title += f" — {result.title}"

    table = Table(
        headers=["#", "Role", "Announcement"],
        title=title,
        icon=get_indicator("accessibility"),
    )

    display_rows = []  # list of (row_data, is_detail_row)
    for a in result.announcements:
        text = getattr(a, screen_reader, None) or ""
        role_styled = click.style(a.role, fg="cyan")
        display_rows.append(([str(a.index), role_styled, text], False))

        # Add enrichment detail row if applicable
        enrichment = _format_enrichment_suffix(a, show) if has_enrichment else None
        if enrichment:
            display_rows.append((_make_detail_row(enrichment, 3), True))

    data_rows = [r for r, is_detail in display_rows if not is_detail]
    table.set_data(data_rows)
    table.print_header()
    for row, is_detail in display_rows:
        table.print_row(row)
    table.print_footer()

    click.echo()
    _print_summary(result)
    click.echo()

    if not has_enrichment:
        print_hint("Use `--show-all` to include description, focusable, tooltip, and more")
    print_hint("Use `inspekt sr compare` for side-by-side with all three screen readers")


def _print_announce(result):
    """Print a single element's announcement."""
    from inspekt.app.cli.table import Table

    click.echo()

    table = Table(
        headers=["Screen Reader", "Announcement"],
        title=f"Element: {result.selector or 'focused'}",
        icon=get_indicator("accessibility"),
    )

    rows = []
    if result.role:
        rows.append(
            [click.style("Role", dim=True), click.style(result.role, fg="cyan")]
        )
    if result.name:
        rows.append([click.style("Name", dim=True), result.name])

    if result.jaws:
        rows.append([click.style("JAWS", fg="blue"), result.jaws])
    if result.nvda:
        rows.append([click.style("NVDA", fg="magenta"), result.nvda])
    if result.voiceover:
        rows.append([click.style("VoiceOver", fg="white"), result.voiceover])

    table.set_data(rows)
    table.print_header(skip_column_headers=True)
    for row in rows:
        table.print_row(row)
    table.print_footer()
    click.echo()


def _print_summary(result):
    """Print summary statistics."""
    summary = result.summary
    if not summary:
        return

    parts = []
    if summary.headings:
        parts.append(f"{summary.headings} headings")
    if summary.links:
        parts.append(f"{summary.links} links")
    if summary.buttons:
        parts.append(f"{summary.buttons} buttons")
    if summary.form_fields:
        parts.append(f"{summary.form_fields} form fields")
    if summary.images:
        parts.append(f"{summary.images} images")
    if summary.landmarks:
        parts.append(f"{summary.landmarks} landmarks")
    if summary.tables:
        parts.append(f"{summary.tables} tables")
    if summary.lists:
        parts.append(f"{summary.lists} lists")

    click.echo(
        f"  {result.element_count} elements  |  "
        + "  |  ".join(parts)
    )

    if result.difference_count > 0:
        click.echo(
            f"  {click.style(str(result.difference_count), fg='yellow')} "
            f"elements announced differently across screen readers"
        )
