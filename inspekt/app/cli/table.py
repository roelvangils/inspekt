"""
Reusable table formatting utilities for CLI output.

This module provides consistent ASCII table formatting across all inspekt commands
using Unicode box-drawing characters for a polished appearance.

Example usage:
    from inspekt.app.cli.table import Table

    # Auto-width with title (recommended):
    table = Table(["Name", "Status", "Size"], title="Network Requests")
    table.set_data([
        ["example.js", "200", "1.2 KB"],
        ["style.css", "404", "0 B"],
    ])
    table.print_header()
    table.print_row(["example.js", "200", "1.2 KB"], colors=[None, "green", None])
    table.print_row(["style.css", "404", "0 B"], colors=[None, "red", None])
    table.print_summary(["Total", "", "1.2 KB"])  # Optional summary row
    table.print_footer()

    # Manual widths (backwards compatible):
    table = Table(["Name", "Status", "Size"], widths=[30, 8, 10])
"""

import json as _json
import re
import shutil
from typing import Any, Optional

from contextlib import contextmanager

import click


# Regex pattern for detecting numeric values (including formatted ones)
NUMERIC_PATTERN = re.compile(
    r"^-?\d+(\.\d+)?\s*(B|KB|MB|GB|TB|ms|s|m|h|%)?$|^-$"
)

# Regex pattern for stripping ANSI escape codes
ANSI_ESCAPE_PATTERN = re.compile(r"\x1b\[[0-9;]*m")

# OSC 8 hyperlink wrappers: \x1b]8;;URL\x1b\\TEXT\x1b]8;;\x1b\\
# Keeps the visible TEXT, drops the wrapping escapes.
OSC8_OPEN_PATTERN = re.compile(r"\x1b\]8;[^\x1b]*\x1b\\")
OSC8_CLOSE_PATTERN = re.compile(r"\x1b\]8;;\x1b\\")

# Nerdfont glyphs live in the Unicode Private Use Areas. They render as boxes
# outside the terminal, so strip them for Markdown export.
NERDFONT_PATTERN = re.compile(r"[\ue000-\uf8ff\U000f0000-\U000ffffd]")


def strip_ansi(text: str) -> str:
    """Strip ANSI escape codes from text."""
    return ANSI_ESCAPE_PATTERN.sub("", text)


def strip_for_markdown(text: str) -> str:
    """Strip ANSI, OSC 8 hyperlinks, and Nerdfont glyphs from a cell value."""
    if not text:
        return ""
    text = str(text)
    text = OSC8_CLOSE_PATTERN.sub("", text)
    text = OSC8_OPEN_PATTERN.sub("", text)
    text = ANSI_ESCAPE_PATTERN.sub("", text)
    text = NERDFONT_PATTERN.sub("", text)
    return text.strip()


def _markdown_cell(value: Any) -> str:
    """Prepare a single cell for a GFM pipe table."""
    text = strip_for_markdown("" if value is None else str(value))
    # Escape pipes, collapse newlines — GFM cells can't span lines.
    text = text.replace("|", "\\|").replace("\r\n", " ").replace("\n", " <br> ")
    return text or " "


def rows_to_markdown(headers: list[str], rows: list[list[Any]]) -> str:
    """Render headers + rows as a GFM pipe table."""
    clean_headers = [_markdown_cell(h) for h in headers]
    body = [[_markdown_cell(v) for v in row] for row in rows]

    header_line = "| " + " | ".join(clean_headers) + " |"
    separator = "| " + " | ".join(["---"] * len(clean_headers)) + " |"
    row_lines = ["| " + " | ".join(row) + " |" for row in body]

    return "\n".join([header_line, separator, *row_lines])


def emit_copyable_data(
    *,
    headers: Optional[list[str]] = None,
    rows: Optional[list[list[Any]]] = None,
    json_data: Any = None,
    summary: str = "",
    table_md: Optional[str] = None,
) -> None:
    """Emit a ``Data ready to copy`` toast signal for the VM terminal.

    Gated on INSPEKT_ISOLATED=1 so it's a no-op outside the VM. Either
    ``headers`` + ``rows`` (to auto-build a Markdown table) or a pre-built
    ``table_md`` may be supplied — omit both for a JSON-only toast.
    ``json_data`` is serialized with ``json.dumps(..., indent=2)``; pass
    ``None`` for a Markdown-only toast.
    """
    from inspekt.config import is_isolated_mode

    if not is_isolated_mode():
        return

    if table_md is None and headers is not None and rows is not None:
        table_md = rows_to_markdown(headers, rows)

    json_text: Optional[str] = None
    if json_data is not None:
        try:
            json_text = _json.dumps(json_data, indent=2, ensure_ascii=False, default=str)
        except Exception:
            json_text = None

    if not table_md and not json_text:
        return

    from inspekt.app.cli.util import _vm_data_signal
    _vm_data_signal(json_text, table_md, summary)


def print_json(data: Any, *, summary: str = "") -> None:
    """Pretty-print ``data`` as JSON and, in the VM, emit a copy toast.

    Centralizes the ``--json`` output path so every command's JSON mode
    gets the [JSON] copy button in the VM terminal without each call site
    duplicating the toast logic. Outside the VM, this is just a prettier
    ``click.echo(json.dumps(...))``.
    """
    json_text = _json.dumps(data, indent=2, ensure_ascii=False, default=str)
    click.echo(json_text)

    from inspekt.config import is_isolated_mode
    if not is_isolated_mode():
        return

    from inspekt.app.cli.util import _vm_data_signal
    _vm_data_signal(json_text, None, summary)


def visible_len(text: str) -> int:
    """Calculate the visible length of text, ignoring ANSI escape codes."""
    return len(strip_ansi(text))


class Table:
    """
    A class for rendering formatted ASCII tables with box-drawing characters.

    Supports automatic width calculation based on content, with terminal-aware
    fitting to prevent tables from exceeding terminal width.

    Attributes:
        headers: List of column header strings
        widths: List of column widths (in characters), can be auto-calculated
        alignments: List of alignments ('left', 'right', 'center') per column
    """

    def __init__(
        self,
        headers: list[str],
        widths: Optional[list[int]] = None,
        alignments: Optional[list[str]] = None,
        border_color: int | str = 240,  # Dark gray (ANSI 256 color)
        title: Optional[str] = None,
        icon: Optional[str] = None,
    ):
        """
        Initialize a new Table.

        Args:
            headers: Column header strings
            widths: Column widths in characters. If None, use set_data() to auto-calculate.
            alignments: Column alignments ('left', 'right', 'center'). Defaults to 'left'.
            border_color: Color for table borders (default: 240, dark gray)
            title: Optional title to display in the table header
            icon: Optional Nerdfont icon to display before the title
        """
        self.headers = headers
        self.widths = widths
        self.alignments = alignments or ["left"] * len(headers)
        self.border_color = border_color
        self.title = title
        self.icon = icon

        if widths is not None and len(headers) != len(widths):
            raise ValueError("headers and widths must have the same length")
        if len(self.alignments) != len(headers):
            raise ValueError("alignments must have the same length as headers")

    @staticmethod
    def get_terminal_width() -> int:
        """Get terminal width, defaulting to 80 if unavailable."""
        try:
            return shutil.get_terminal_size().columns
        except Exception:
            return 80

    @staticmethod
    def calculate_widths(
        headers: list[str],
        rows: list[list[str]],
        max_total_width: Optional[int] = None,
    ) -> list[int]:
        """
        Calculate optimal column widths from headers and data.

        Args:
            headers: Column header strings
            rows: List of row data (each row is a list of cell values)
            max_total_width: Maximum total table width. If exceeded, shrink widest columns.

        Returns:
            List of column widths
        """
        # Start with header widths
        widths = [len(str(h)) for h in headers]

        # Expand to fit data
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(widths):
                    widths[i] = max(widths[i], len(str(cell)))

        if max_total_width:
            # Calculate overhead: borders (│) + padding (1 space each side per cell)
            # Format: │ col │ col │ = (len(widths) + 1) borders + len(widths)*2 padding
            overhead = len(widths) + 1 + (len(widths) * 2)
            available = max_total_width - overhead

            # Shrink widest columns until we fit (minimum column width: 5)
            while sum(widths) > available and max(widths) > 5:
                max_idx = widths.index(max(widths))
                widths[max_idx] -= 1

        return widths

    def set_data(
        self, rows: list[list[str]], fit_terminal: bool = True, auto_align: bool = True
    ) -> None:
        """
        Set row data and calculate widths automatically.

        Args:
            rows: List of row data (each row is a list of cell values)
            fit_terminal: If True, shrink columns to fit terminal width
            auto_align: If True, auto-detect numeric columns and right-align them
        """
        max_width = self.get_terminal_width() if fit_terminal else None
        self.widths = self.calculate_widths(self.headers, rows, max_width)

        # Ensure table is wide enough for the title (if set)
        if self.title:
            # Title needs to fit within the table width
            # Total width = sum(widths) + 3*num_cols + 1 (borders + padding)
            # Title content area = total_width - 4 (2 borders + 2 padding)
            current_total_width = sum(self.widths) + 3 * len(self.widths) + 1
            title_content_area = current_total_width - 4
            # Calculate display title length (including icon if present)
            display_title_len = len(self.title)
            if self.icon:
                display_title_len += len(self.icon) + 2  # icon + two spaces
            if title_content_area < display_title_len:
                # Need to expand the table to fit the title
                extra = display_title_len - title_content_area
                self.widths[-1] += extra

        # Auto-detect numeric columns and set right alignment
        if auto_align and rows:
            for col_idx in range(len(self.headers)):
                # Check if all non-empty values in this column are numeric
                values = [row[col_idx] for row in rows if col_idx < len(row)]
                non_empty = [v for v in values if v and str(v).strip()]
                if non_empty and all(
                    NUMERIC_PATTERN.match(str(v).strip()) for v in non_empty
                ):
                    self.alignments[col_idx] = "right"

    def _ensure_widths(self) -> None:
        """Ensure widths are set before rendering."""
        if self.widths is None:
            raise ValueError(
                "Table widths not set. Either pass widths to __init__ or call set_data() first."
            )

    def _align_text(self, text: str, width: int, alignment: str) -> str:
        """Align text within a given width, handling ANSI escape codes."""
        # Calculate the visible length (ignoring ANSI codes)
        vis_len = visible_len(text)
        # Calculate padding needed
        padding_needed = width - vis_len
        if padding_needed <= 0:
            return text
        if alignment == "right":
            return " " * padding_needed + text
        elif alignment == "center":
            left_pad = padding_needed // 2
            right_pad = padding_needed - left_pad
            return " " * left_pad + text + " " * right_pad
        else:  # left
            return text + " " * padding_needed

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text with ellipsis if too long, handling ANSI escape codes."""
        vis_len = visible_len(text)
        if vis_len <= max_len:
            return text
        # Need to truncate - count visible characters and preserve ANSI codes
        result = []
        visible_count = 0
        i = 0
        while i < len(text) and visible_count < max_len - 1:
            # Check if we're at an ANSI escape sequence
            match = ANSI_ESCAPE_PATTERN.match(text, i)
            if match:
                # Include the ANSI code but don't count towards visible length
                result.append(match.group())
                i = match.end()
            else:
                result.append(text[i])
                visible_count += 1
                i += 1
        # Add ellipsis and reset any open ANSI codes
        return "".join(result) + "\u2026\x1b[0m"  # … + reset

    def _format_row(
        self,
        columns: list[str],
        colors: Optional[list[Optional[str]]] = None,
        bold: bool = False,
        row_bg: Optional[str] = None,
        highlight_marker: bool = False,
    ) -> str:
        """
        Format a single table row.

        Args:
            columns: List of cell values
            colors: Optional list of colors for each cell
            bold: Whether to make the entire row bold
            row_bg: Optional background color for the entire row
            highlight_marker: If True, prepend asterisk to first column (for accessibility)

        Returns:
            Formatted row string with 1 space padding on each side
        """
        self._ensure_widths()

        if colors is None:
            colors = [None] * len(columns)

        parts = []
        for i, col in enumerate(columns):
            # Add asterisk marker to first column if highlighting
            col_str = str(col)
            if i == 0 and highlight_marker:
                col_str = col_str + " *"
            # Truncate if too long
            truncated = self._truncate(col_str, self.widths[i])
            # Align to width
            aligned = self._align_text(truncated, self.widths[i], self.alignments[i])
            # Apply color if specified
            if colors[i] or bold or row_bg:
                aligned = click.style(aligned, fg=colors[i], bold=bold, bg=row_bg)
            parts.append(aligned)

        # Use styled borders with 1 space padding on each side
        border = click.style("\u2502", fg=self.border_color)  # │
        # Apply background to padding spaces and inner borders if row_bg is set
        # First and last borders don't get background for a more natural look
        if row_bg:
            space = click.style(" ", bg=row_bg)
            border_bg = click.style("\u2502", fg=self.border_color, bg=row_bg)  # │ with background
            return border + space + (space + border_bg + space).join(parts) + space + border
        return border + " " + (" " + border + " ").join(parts) + " " + border

    def _format_separator(
        self, top: bool = False, bottom: bool = False, header: bool = False
    ) -> str:
        """
        Format a horizontal separator line.

        Args:
            top: Use top border characters (┌ ┬ ┐)
            bottom: Use bottom border characters (└ ┴ ┘)
            header: Use header separator characters (same as middle: ├ ┼ ┤)

        Returns:
            Formatted separator string
        """
        self._ensure_widths()

        if top:
            left, mid, right = "\u256d", "\u252c", "\u256e"  # ╭ ┬ ╮ (rounded corners)
        elif bottom:
            left, mid, right = "\u2570", "\u2534", "\u256f"  # ╰ ┴ ╯ (rounded corners)
        else:
            left, mid, right = "\u251c", "\u253c", "\u2524"  # ├ ┼ ┤

        # Width + 2 for 1 space padding on each side
        parts = [("\u2500" * (w + 2)) for w in self.widths]  # ─
        line = left + mid.join(parts) + right
        return click.style(line, fg=self.border_color)

    def _get_total_width(self) -> int:
        """Calculate total table width including borders and padding."""
        self._ensure_widths()
        # Format: │ col │ col │ = sum(widths) + 3*num_cols + 1
        return sum(self.widths) + (len(self.widths) * 3) + 1

    def _format_title_bar(self) -> list[str]:
        """Format the title bar with top border."""
        self._ensure_widths()
        total_width = self._get_total_width()

        # Top border (full width, no column separators)
        top_line = click.style(
            "\u256d" + ("\u2500" * (total_width - 2)) + "\u256e",  # ╭───╮
            fg=self.border_color,
        )

        # Build title with optional icon
        display_title = self.title
        if self.icon:
            display_title = f"{self.icon}  {self.title}"  # Two spaces for visual separation

        # Title row (centered, bold, bright white)
        title_text = display_title.center(total_width - 4)
        title_styled = click.style(title_text, bold=True, fg="bright_white")
        border = click.style("\u2502", fg=self.border_color)  # │
        title_line = border + " " + title_styled + " " + border

        # Separator between title and header (double line with column separators)
        sep_parts = [("\u2550" * (w + 2)) for w in self.widths]  # ═
        sep_line = click.style(
            "\u255e" + "\u2564".join(sep_parts) + "\u2561",  # ╞═╤═╡
            fg=self.border_color,
        )

        return [top_line, title_line, sep_line]

    def print_header(self, skip_column_headers: bool = False) -> None:
        """Print the table header with top border (and title bar if set).

        Args:
            skip_column_headers: If True, only print the title bar without column headers.
                                 Useful for key-value tables where headers aren't needed.
        """
        if self.title:
            # Print title bar first
            for line in self._format_title_bar():
                click.echo(line, color=True)
            # Skip header row if single column (title serves as header) or explicitly requested
            if len(self.headers) == 1 or skip_column_headers:
                return
            # Then header row and separator
            click.echo(self._format_row(self.headers, bold=True), color=True)
            click.echo(self._format_separator(header=True), color=True)
        else:
            # Standard header without title
            click.echo(self._format_separator(top=True), color=True)
            if not skip_column_headers:
                click.echo(self._format_row(self.headers, bold=True), color=True)
                click.echo(self._format_separator(header=True), color=True)

    # Default highlight background color (ANSI 256 dark gray)
    HIGHLIGHT_BG = 236

    def print_row(
        self,
        values: list[str],
        colors: Optional[list[Optional[str]]] = None,
        row_bg: Optional[int | str] = None,
        highlight: bool = False,
    ) -> None:
        """
        Print a table row.

        Args:
            values: List of cell values
            colors: Optional list of colors for each cell
            row_bg: Optional background color for the entire row (overrides highlight)
            highlight: If True, use default highlight background color and add asterisk marker
        """
        bg = row_bg if row_bg is not None else (self.HIGHLIGHT_BG if highlight else None)
        click.echo(self._format_row(values, colors, row_bg=bg, highlight_marker=highlight), color=True)

    def print_separator(self) -> None:
        """Print a horizontal separator between rows."""
        click.echo(self._format_separator(), color=True)

    def _format_double_separator(self) -> str:
        """Format a double-line separator for summary rows."""
        self._ensure_widths()
        # Use box-drawing double horizontal (═)
        parts = [("\u2550" * (w + 2)) for w in self.widths]  # ═
        line = "\u255e" + "\u256a".join(parts) + "\u2561"  # ╞═╪═╡
        return click.style(line, fg=self.border_color)

    def print_summary(
        self,
        values: list[str],
        colors: Optional[list[Optional[str]]] = None,
    ) -> None:
        """
        Print a summary row with double-line separator above it.

        Args:
            values: List of cell values for the summary row
            colors: Optional list of colors for each cell
        """
        click.echo(self._format_double_separator(), color=True)
        click.echo(self._format_row(values, colors, bold=True), color=True)

    def print_footer(self) -> None:
        """Print the table footer (bottom border)."""
        click.echo(self._format_separator(bottom=True), color=True)

    def print_empty_message(self, message: str = "No data to display.") -> None:
        """Print an empty table with a message."""
        self._ensure_widths()
        click.echo(self._format_separator(top=True), color=True)
        # Calculate total width for message centering
        # Format: │ col │ col │ = sum(widths) + 3*num_cols + 1
        total_width = sum(self.widths) + (len(self.widths) * 3) + 1
        msg_cell = message.center(total_width - 4)
        border = click.style("\u2502", fg=self.border_color)
        click.echo(border + " " + msg_cell + " " + border, color=True)
        click.echo(self._format_separator(bottom=True), color=True)


def format_size(bytes_size: int) -> str:
    """Format bytes as human-readable size."""
    if bytes_size == 0:
        return "-"
    elif bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    else:
        return f"{bytes_size / (1024 * 1024):.1f} MB"


def format_time(ms: int) -> str:
    """Format milliseconds as human-readable time."""
    if ms == 0:
        return "-"
    elif ms < 1000:
        return f"{ms} ms"
    else:
        return f"{ms / 1000:.2f} s"


def format_status(status: int) -> str:
    """Format HTTP status code with color."""
    if status == 0:
        return click.style("-", fg="bright_black")
    elif 200 <= status < 300:
        return click.style(str(status), fg="green")
    elif 300 <= status < 400:
        return click.style(str(status), fg="cyan")
    elif 400 <= status < 500:
        return click.style(str(status), fg="yellow")
    elif status >= 500:
        return click.style(str(status), fg="red")
    else:
        return str(status)


def get_type_color(resource_type: str) -> Optional[str]:
    """Get the color for a resource type."""
    type_colors = {
        "script": "yellow",
        "stylesheet": "magenta",
        "fetch": "cyan",
        "xhr": "cyan",
        "image": "green",
        "font": "blue",
        "document": "white",
        "svg": "green",
        "video": "magenta",
        "audio": "magenta",
    }
    return type_colors.get(resource_type)


def format_status_icon(
    status: str | bool | None, with_color: bool = True
) -> str:
    """
    Format status with appropriate icon.

    Uses Nerdfont glyphs when enabled in config, otherwise falls back to
    standard Unicode symbols.

    Args:
        status: Status value (bool, string like 'pass'/'fail', or None)
        with_color: Whether to apply color styling

    Returns:
        Styled status icon: ✓/ (green), ✗/ (red), or ○/ (gray)
    """
    from inspekt.app.cli.icons import get_status_icon

    # Try Nerdfont icon first
    nerdfont_icon = get_status_icon(status)

    if status is True or status in ("pass", "passed", "ok", "success", "yes", "valid"):
        icon = nerdfont_icon if nerdfont_icon else "\u2713"  # ✓
        color = "green" if with_color else None
    elif status is False or status in ("fail", "failed", "error", "no", "invalid"):
        icon = nerdfont_icon if nerdfont_icon else "\u2717"  # ✗
        color = "red" if with_color else None
    elif status in ("warn", "warning"):
        icon = nerdfont_icon if nerdfont_icon else "\u26a0"  # ⚠
        color = "yellow" if with_color else None
    else:
        icon = nerdfont_icon if nerdfont_icon else "\u25cb"  # ○
        color = "bright_black" if with_color else None

    if color:
        return click.style(icon, fg=color)
    return icon


def wrap_text(
    text: str,
    width: Optional[int] = None,
    indent: str = "",
    subsequent_indent: Optional[str] = None,
) -> str:
    """
    Wrap text to fit within terminal width, breaking at word boundaries.

    Args:
        text: The text to wrap
        width: Maximum line width (defaults to terminal width)
        indent: Prefix for the first line
        subsequent_indent: Prefix for subsequent lines (defaults to same as indent)

    Returns:
        Wrapped text as a single string with newlines

    Example:
        >>> wrap_text("This is a long warning message…", indent="  ")
        "  This is a long warning message that
          wraps nicely to fit the terminal."
    """
    import textwrap

    if width is None:
        try:
            width = shutil.get_terminal_size().columns
        except Exception:
            width = 80

    if subsequent_indent is None:
        subsequent_indent = indent

    # Account for indent in available width
    available_width = width - len(indent)
    if available_width < 20:
        available_width = 20  # Minimum reasonable width

    wrapper = textwrap.TextWrapper(
        width=available_width,
        initial_indent=indent,
        subsequent_indent=subsequent_indent,
        break_long_words=True,
        break_on_hyphens=True,
    )

    return wrapper.fill(text)


def print_wrapped(
    text: str,
    width: Optional[int] = None,
    indent: str = "",
    subsequent_indent: Optional[str] = None,
    fg: Optional[str] = None,
    bold: bool = False,
    err: bool = False,
) -> None:
    """
    Print text wrapped to fit within terminal width.

    Args:
        text: The text to wrap and print
        width: Maximum line width (defaults to terminal width)
        indent: Prefix for the first line
        subsequent_indent: Prefix for subsequent lines (defaults to same as indent)
        fg: Foreground color for the text
        bold: Whether to make the text bold
        err: Whether to print to stderr

    Example:
        >>> print_wrapped("This is a long warning…", fg="yellow")
    """
    wrapped = wrap_text(text, width, indent, subsequent_indent)

    if fg or bold:
        wrapped = click.style(wrapped, fg=fg, bold=bold)

    click.echo(wrapped, err=err, color=True)


# =============================================================================
# Icon-Prefixed Message Utilities
# =============================================================================
#
# For terminal-width text wrapping with icon prefixes:
#
# - format_icon_message(message, icon) - returns wrapped string
# - print_warning("message") - yellow ⚠ prefix
# - print_hint("message") - blue lightbulb icon prefix
# - print_error("message") - red ✗ prefix, prints to stderr
# - print_success("message") - green ✓ prefix
#
# Example:
#     from inspekt.app.cli.table import print_warning, print_hint
#
#     print_warning("This is a long warning that will wrap nicely")
#     print_hint("This tip will also wrap to fit the terminal")
#
# Output format (with 2-space continuation indent):
#     ⚠ This recording requires viewport
#       matching (require_viewport_match: true).
#       Auto-enabling --match-viewport for
#       faithful replay.
# =============================================================================


def _style_with_inline_code(text: str, base_fg: str, bold: bool = False) -> str:
    """
    Style text with inline code support using backticks.

    Text wrapped in `backticks` is styled cyan, while the rest uses
    the base foreground color. This allows highlighting command flags
    and code snippets within messages.

    Args:
        text: The text to style, may contain `backtick` wrapped code
        base_fg: Base foreground color for non-code text (e.g., "yellow", "blue")
        bold: Whether to make non-code text bold

    Returns:
        Styled string with cyan inline code and base-colored regular text

    Example:
        >>> _style_with_inline_code("Use `--slow` for better results", "blue")
        # Returns: blue "Use " + cyan "--slow" + blue " for better results"
    """
    import re

    # Pattern to match `code` (backtick-wrapped text)
    pattern = r'`([^`]+)`'

    # Find all matches and their positions
    parts = []
    last_end = 0

    for match in re.finditer(pattern, text):
        # Add text before this match (in base color)
        if match.start() > last_end:
            before_text = text[last_end:match.start()]
            parts.append(click.style(before_text, fg=base_fg, bold=bold))

        # Add the code snippet (in cyan italic, no backticks)
        code_text = match.group(1)
        parts.append(click.style(code_text, fg="cyan", italic=True))

        last_end = match.end()

    # Add any remaining text after the last match
    if last_end < len(text):
        parts.append(click.style(text[last_end:], fg=base_fg, bold=bold))

    # If no backticks found, just style the whole thing
    if not parts:
        return click.style(text, fg=base_fg, bold=bold)

    return "".join(parts)


def format_icon_message(
    message: str,
    icon: str = "",
    width: Optional[int] = None,
) -> str:
    """
    Format a message with icon prefix and proper text wrapping.

    The message text wraps to fit terminal width with continuation
    lines indented by 2 spaces to align after the icon.

    Args:
        message: The message text (without icon)
        icon: Icon to prefix (e.g., "⚠", "✓", "ℹ")
        width: Max width (defaults to terminal width)

    Returns:
        Wrapped text with icon prefix and 2-space continuation indent

    Example:
        >>> format_icon_message("Long warning message…", icon="⚠")
        "⚠ Long warning message that
          wraps to next line."
    """
    prefix = f"{icon} " if icon else ""
    subsequent_indent = "  "  # Fixed 2-space indent for continuation lines

    return wrap_text(
        message,
        width=width,
        indent=prefix,
        subsequent_indent=subsequent_indent,
    )


def print_warning(message: str, bold: bool = False, err: bool = False) -> None:
    """
    Print a yellow warning message with ⚠ icon and text wrapping.

    Supports inline code: text in `backticks` is highlighted in cyan.

    Args:
        message: The warning message text (without icon). Use `backticks` for code.
        bold: Whether to make the text bold
        err: Whether to print to stderr

    Example:
        >>> print_warning("Use `--match-viewport` for faithful replay")
        ⚠ Use --match-viewport for faithful
          replay
    """
    formatted = format_icon_message(message, icon="⚠")
    styled = _style_with_inline_code(formatted, base_fg="yellow", bold=bold)
    click.echo(styled, err=err)


def print_hint(message: str, bold: bool = False) -> None:
    """
    Print a blue hint/tip message with lightbulb icon and text wrapping.

    Supports inline code: text in `backticks` is highlighted in cyan.

    Args:
        message: The hint message text (without prefix). Use `backticks` for code.
        bold: Whether to make the text bold

    Example:
        >>> print_hint("Use `--slow` for more reliable playback")
         Use --slow for more reliable
          playback
    """
    # Lightbulb icon: \uf400 (nf-oct-light_bulb)
    formatted = format_icon_message(message, icon="\uf400")
    styled = _style_with_inline_code(formatted, base_fg="blue", bold=bold)
    click.echo(styled)


def print_error(message: str, bold: bool = True, err: bool = True) -> None:
    """
    Print a red error message with ✗ icon and text wrapping.

    Supports inline code: text in `backticks` is highlighted in cyan.

    Args:
        message: The error message text (without icon). Use `backticks` for code.
        bold: Whether to make the text bold (default: True)
        err: Whether to print to stderr (default: True)

    Example:
        >>> print_error("Could not connect to browser")
        ✗ Could not connect to browser
    """
    formatted = format_icon_message(message, icon="✗")
    styled = _style_with_inline_code(formatted, base_fg="red", bold=bold)
    click.echo(styled, err=err)


def print_step(label: str, status: str = "running", **kwargs) -> None:
    """Print a step indicator with status."""
    icons = {"running": "•", "done": "✓", "error": "✗", "skip": "○"}
    colors = {"running": "blue", "done": "green", "error": "red", "skip": "bright_black"}
    icon = click.style(icons.get(status, "•"), fg=colors.get(status, "blue"))
    click.echo(f"  {icon} {label}")


@contextmanager
def print_checkbox_step(label: str, checked: bool = False, **kwargs):
    """Context manager that prints a checkbox-style step indicator.

    Shows ○ on entry, ✓ on success, ✗ on failure.
    """
    icon = click.style("○", fg="bright_black")
    click.echo(f"  {icon} {label}")
    try:
        yield
        # Overwrite with success
        click.echo(f"\033[1A\033[2K  {click.style('✓', fg='green')} {label}")
    except Exception:
        click.echo(f"\033[1A\033[2K  {click.style('✗', fg='red')} {label}")
        raise


class ProgressChecklist:
    """A checklist that displays step progress with checkbox indicators."""

    def __init__(self, step_names: list[str]):
        self.step_names = step_names

    def start(self):
        """Print all steps as pending."""
        for name in self.step_names:
            icon = click.style("○", fg="bright_black")
            click.echo(f"  {icon} {name}")

    @contextmanager
    def step(self, index: int):
        """Context manager that marks a step as in-progress, then done."""
        name = self.step_names[index]
        # Move up to the correct line and mark as in-progress
        lines_up = len(self.step_names) - index
        click.echo(f"\033[{lines_up}A\033[2K  {click.style('◉', fg='cyan')} {name}", nl=False)
        click.echo(f"\033[{lines_up}B\r", nl=False)
        try:
            yield
            # Mark as done
            click.echo(f"\033[{lines_up}A\033[2K  {click.style('✓', fg='green')} {name}", nl=False)
            click.echo(f"\033[{lines_up}B\r", nl=False)
        except Exception:
            click.echo(f"\033[{lines_up}A\033[2K  {click.style('✗', fg='red')} {name}", nl=False)
            click.echo(f"\033[{lines_up}B\r", nl=False)
            raise


def print_success(message: str, bold: bool = False) -> None:
    """
    Print a green success message with ✓ icon and text wrapping.

    Supports inline code: text in `backticks` is highlighted in cyan.

    Args:
        message: The success message text (without icon). Use `backticks` for code.
        bold: Whether to make the text bold

    Example:
        >>> print_success("Recording saved to `output.yaml`")
        ✓ Recording saved to output.yaml
    """
    formatted = format_icon_message(message, icon="✓")
    styled = _style_with_inline_code(formatted, base_fg="green", bold=bold)
    click.echo(styled)
