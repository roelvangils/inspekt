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

import re
import shutil
from typing import Optional

import click


# Regex pattern for detecting numeric values (including formatted ones)
NUMERIC_PATTERN = re.compile(
    r"^-?\d+(\.\d+)?\s*(B|KB|MB|GB|TB|ms|s|m|h|%)?$|^-$"
)


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
    ):
        """
        Initialize a new Table.

        Args:
            headers: Column header strings
            widths: Column widths in characters. If None, use set_data() to auto-calculate.
            alignments: Column alignments ('left', 'right', 'center'). Defaults to 'left'.
            border_color: Color for table borders (default: 240, dark gray)
            title: Optional title to display in the table header
        """
        self.headers = headers
        self.widths = widths
        self.alignments = alignments or ["left"] * len(headers)
        self.border_color = border_color
        self.title = title

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
            if title_content_area < len(self.title):
                # Need to expand the table to fit the title
                extra = len(self.title) - title_content_area
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
        """Align text within a given width."""
        if alignment == "right":
            return text.rjust(width)
        elif alignment == "center":
            return text.center(width)
        else:  # left
            return text.ljust(width)

    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text with ellipsis if too long."""
        if len(text) <= max_len:
            return text
        return text[: max_len - 1] + "\u2026"  # … (single ellipsis character)

    def _format_row(
        self,
        columns: list[str],
        colors: Optional[list[Optional[str]]] = None,
        bold: bool = False,
    ) -> str:
        """
        Format a single table row.

        Args:
            columns: List of cell values
            colors: Optional list of colors for each cell
            bold: Whether to make the entire row bold

        Returns:
            Formatted row string with 1 space padding on each side
        """
        self._ensure_widths()

        if colors is None:
            colors = [None] * len(columns)

        parts = []
        for i, col in enumerate(columns):
            # Truncate if too long
            truncated = self._truncate(str(col), self.widths[i])
            # Align to width
            aligned = self._align_text(truncated, self.widths[i], self.alignments[i])
            # Apply color if specified
            if colors[i]:
                aligned = click.style(aligned, fg=colors[i], bold=bold)
            elif bold:
                aligned = click.style(aligned, bold=True)
            parts.append(aligned)

        # Use styled borders with 1 space padding on each side
        border = click.style("\u2502", fg=self.border_color)  # │
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

        # Title row (centered, bold, bright white)
        title_text = self.title.center(total_width - 4)
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

    def print_header(self) -> None:
        """Print the table header with top border (and title bar if set)."""
        if self.title:
            # Print title bar first
            for line in self._format_title_bar():
                click.echo(line, color=True)
            # Skip header row if single column (title serves as header)
            if len(self.headers) == 1:
                return
            # Then header row and separator
            click.echo(self._format_row(self.headers, bold=True), color=True)
            click.echo(self._format_separator(header=True), color=True)
        else:
            # Standard header without title
            click.echo(self._format_separator(top=True), color=True)
            click.echo(self._format_row(self.headers, bold=True), color=True)
            click.echo(self._format_separator(header=True), color=True)

    def print_row(
        self,
        values: list[str],
        colors: Optional[list[Optional[str]]] = None,
    ) -> None:
        """
        Print a table row.

        Args:
            values: List of cell values
            colors: Optional list of colors for each cell
        """
        click.echo(self._format_row(values, colors), color=True)

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

    Args:
        status: Status value (bool, string like 'pass'/'fail', or None)
        with_color: Whether to apply color styling

    Returns:
        Styled status icon: ✓ (green), ✗ (red), or ○ (gray)
    """
    if status is True or status in ("pass", "passed", "ok", "success", "yes", "valid"):
        icon = "\u2713"  # ✓
        color = "green" if with_color else None
    elif status is False or status in ("fail", "failed", "error", "no", "invalid"):
        icon = "\u2717"  # ✗
        color = "red" if with_color else None
    else:
        icon = "\u25cb"  # ○
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
        >>> wrap_text("This is a long warning message...", indent="  ")
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
        >>> print_wrapped("This is a long warning...", fg="yellow")
    """
    wrapped = wrap_text(text, width, indent, subsequent_indent)

    if fg or bold:
        wrapped = click.style(wrapped, fg=fg, bold=bold)

    click.echo(wrapped, err=err, color=True)
