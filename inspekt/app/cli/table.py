"""
Reusable table formatting utilities for CLI output.

This module provides consistent ASCII table formatting across all inspekt commands
using Unicode box-drawing characters for a polished appearance.

Example usage:
    from inspekt.app.cli.table import Table

    table = Table(["Name", "Status", "Size"], [30, 8, 10])
    table.print_header()
    table.print_row(["example.js", "200", "1.2 KB"], colors=[None, "green", None])
    table.print_row(["style.css", "404", "0 B"], colors=[None, "red", None])
    table.print_footer()
"""

from typing import Optional

import click


class Table:
    """
    A class for rendering formatted ASCII tables with box-drawing characters.

    Attributes:
        headers: List of column header strings
        widths: List of column widths (in characters)
        alignments: List of alignments ('left', 'right', 'center') per column
    """

    def __init__(
        self,
        headers: list[str],
        widths: list[int],
        alignments: Optional[list[str]] = None,
        border_color: str = "bright_black",
    ):
        """
        Initialize a new Table.

        Args:
            headers: Column header strings
            widths: Column widths in characters
            alignments: Column alignments ('left', 'right', 'center'). Defaults to 'left'.
            border_color: Color for table borders (default: bright_black)
        """
        self.headers = headers
        self.widths = widths
        self.alignments = alignments or ["left"] * len(headers)
        self.border_color = border_color

        if len(headers) != len(widths):
            raise ValueError("headers and widths must have the same length")
        if len(self.alignments) != len(headers):
            raise ValueError("alignments must have the same length as headers")

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
        return text[: max_len - 3] + "..."

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
            Formatted row string
        """
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

        # Use styled borders
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
        if top:
            left, mid, right = "\u250c", "\u252c", "\u2510"  # ┌ ┬ ┐
        elif bottom:
            left, mid, right = "\u2514", "\u2534", "\u2518"  # └ ┴ ┘
        else:
            left, mid, right = "\u251c", "\u253c", "\u2524"  # ├ ┼ ┤

        parts = [("\u2500" * (w + 2)) for w in self.widths]  # ─
        line = left + mid.join(parts) + right
        return click.style(line, fg=self.border_color)

    def print_header(self) -> None:
        """Print the table header with top border."""
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

    def print_footer(self) -> None:
        """Print the table footer (bottom border)."""
        click.echo(self._format_separator(bottom=True), color=True)

    def print_empty_message(self, message: str = "No data to display.") -> None:
        """Print an empty table with a message."""
        click.echo(self._format_separator(top=True), color=True)
        # Calculate total width for message centering
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
