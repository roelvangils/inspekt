"""
Output utilities for CLI commands.

Provides centralized handling for:
- File output with clickable terminal links
- Open/reveal file operations
- Clipboard operations
- Consistent JSON output formatting
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import click


@dataclass
class OutputResult:
    """Result from an output operation."""
    path: Path | None = None
    content: str = ""
    size: int = 0
    copied: bool = False
    opened: bool = False
    revealed: bool = False


class OutputHandler:
    """
    Handles file output, clipboard, and open/reveal operations.

    Centralizes common patterns across CLI commands for:
    - Generating OSC 8 clickable terminal links
    - Saving files with consistent messaging
    - Opening files in default applications
    - Revealing files in file explorer
    - Copying content to clipboard

    Example:
        handler = OutputHandler()

        # Save with clickable link
        path = Path("output.html")
        path.write_text(content)
        handler.print_saved(path, f"{len(content)} characters")

        # Open/reveal
        handler.open_file(path)
        handler.reveal_file(path)
    """

    @staticmethod
    def make_clickable_path(path: Path, display_text: str | None = None) -> str:
        """
        Generate an OSC 8 terminal hyperlink for a file path.

        Creates a clickable link in supported terminals (iTerm2, Hyper,
        Windows Terminal, etc.) that opens the file when clicked.

        Args:
            path: Path to the file
            display_text: Text to display (defaults to path name)

        Returns:
            ANSI escape sequence string with clickable link
        """
        from inspekt.app.cli.util import make_file_link
        return make_file_link(path.resolve(), display_text or str(path))

    @staticmethod
    def print_saved(
        path: Path,
        details: str = "",
        prefix: str = "Saved",
        content_type: str = "",
    ) -> None:
        """
        Print a success message with clickable file path.

        Args:
            path: Path to the saved file
            details: Additional details (e.g., "123 characters", "45 KB")
            prefix: Message prefix (default: "Saved")
            content_type: Content type (e.g., "HTML", "CSS")
        """
        clickable = OutputHandler.make_clickable_path(path)
        type_str = f" {content_type}" if content_type else ""
        detail_str = f" ({details})" if details else ""
        click.echo(f"{prefix}{type_str} to {clickable}{detail_str}", err=True)

    @staticmethod
    def open_file(path: Path) -> bool:
        """
        Open a file in the default application.

        Uses the system's default application for the file type.
        In isolated mode (VM), triggers a download instead.

        Args:
            path: Path to the file to open

        Returns:
            True if successful, False otherwise
        """
        from inspekt.app.cli.util import open_or_download
        return open_or_download(path)

    @staticmethod
    def reveal_file(path: Path) -> bool:
        """
        Reveal a file in the file explorer.

        Opens the containing folder with the file selected/highlighted.
        In isolated mode (VM), triggers a download instead.

        Args:
            path: Path to the file to reveal

        Returns:
            True if successful, False otherwise
        """
        from inspekt.app.cli.util import reveal_or_download
        return reveal_or_download(path)

    @staticmethod
    def copy_to_clipboard(content: str, quiet: bool = False) -> bool:
        """
        Copy text content to the clipboard.

        Args:
            content: Text to copy
            quiet: If True, suppress success message

        Returns:
            True if successful, False otherwise
        """
        from inspekt.app.cli.util import copy_text_to_clipboard

        success = copy_text_to_clipboard(content)
        if success and not quiet:
            click.echo(f"Copied {len(content)} characters to clipboard", err=True)
        return success

    @staticmethod
    def copy_image_to_clipboard(image_data: bytes, format: str = "png") -> bool:
        """
        Copy image data to the clipboard.

        Args:
            image_data: Raw image bytes
            format: Image format (png, jpg, etc.)

        Returns:
            True if successful, False otherwise
        """
        from inspekt.app.cli.util import copy_image_to_clipboard
        return copy_image_to_clipboard(image_data, format=format)

    @staticmethod
    def save_and_handle(
        content: str,
        path: Path,
        open_after: bool = False,
        reveal_after: bool = False,
        content_type: str = "",
        details: str = "",
    ) -> OutputResult:
        """
        Save content to file and optionally open/reveal.

        Combines file writing, success messaging, and post-actions
        into a single operation.

        Args:
            content: Content to write
            path: Output file path
            open_after: Open file in default app after saving
            reveal_after: Reveal file in file explorer after saving
            content_type: Type label for messages (e.g., "HTML", "CSS")
            details: Additional details for success message

        Returns:
            OutputResult with operation details
        """
        # Write file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

        # Print success message
        OutputHandler.print_saved(path, details=details, content_type=content_type)

        result = OutputResult(
            path=path,
            content=content,
            size=len(content),
        )

        # Handle post-actions
        if open_after:
            result.opened = OutputHandler.open_file(path)
        if reveal_after:
            result.revealed = OutputHandler.reveal_file(path)

        return result


class JsonOutput:
    """
    Builder for consistent JSON output across commands.

    Provides a fluent interface for building JSON responses with
    consistent structure and common fields.

    Example:
        output = (
            JsonOutput()
            .with_content("html", html_content)
            .with_selector(selector, tag)
            .with_page_metadata(response)
            .build()
        )
        click.echo(json.dumps(output, indent=2))
    """

    def __init__(self, ok: bool = True):
        """
        Initialize JSON output builder.

        Args:
            ok: Success status (default: True)
        """
        self._data: dict[str, Any] = {"ok": ok}

    def with_content(self, key: str, content: str) -> JsonOutput:
        """
        Add content with automatic length calculation.

        Args:
            key: Key for the content (e.g., "html", "css", "text")
            content: The content string

        Returns:
            Self for chaining
        """
        self._data[key] = content
        self._data["length"] = len(content)
        return self

    def with_selector(self, selector: str, tag: str | None = None) -> JsonOutput:
        """
        Add element selector info.

        Args:
            selector: CSS selector string
            tag: Optional HTML tag name

        Returns:
            Self for chaining
        """
        self._data["selector"] = selector
        if tag:
            self._data["tag"] = tag
        return self

    def with_page_metadata(self, response: dict) -> JsonOutput:
        """
        Add common page metadata from a response dict.

        Extracts pageUrl, pageTitle, and pageDomain from the response.

        Args:
            response: Response dict containing page metadata

        Returns:
            Self for chaining
        """
        self._data["pageUrl"] = response.get("pageUrl")
        self._data["pageTitle"] = response.get("pageTitle")
        self._data["pageDomain"] = response.get("pageDomain")
        return self

    def with_counts(
        self,
        element_count: int | None = None,
        property_count: int | None = None,
    ) -> JsonOutput:
        """
        Add count statistics.

        Args:
            element_count: Number of elements
            property_count: Number of CSS properties

        Returns:
            Self for chaining
        """
        if element_count is not None:
            self._data["elementCount"] = element_count
        if property_count is not None:
            self._data["propertyCount"] = property_count
        return self

    def with_field(self, key: str, value: Any) -> JsonOutput:
        """
        Add an arbitrary field.

        Args:
            key: Field name
            value: Field value

        Returns:
            Self for chaining
        """
        self._data[key] = value
        return self

    def with_fields(self, **kwargs: Any) -> JsonOutput:
        """
        Add multiple arbitrary fields.

        Args:
            **kwargs: Key-value pairs to add

        Returns:
            Self for chaining
        """
        self._data.update(kwargs)
        return self

    def build(self) -> dict[str, Any]:
        """
        Build and return the final JSON dict.

        Returns:
            Dictionary ready for JSON serialization
        """
        return self._data

    def print(self, indent: int = 2) -> None:
        """
        Print the JSON output to stdout.

        Args:
            indent: JSON indentation level (default: 2)
        """
        click.echo(json.dumps(self._data, indent=indent))


def validate_output_options(
    file_path: str | None = None,
    copy: bool = False,
    output_json: bool = False,
    open_after: bool = False,
    reveal_after: bool = False,
) -> None:
    """
    Validate common output option combinations.

    Raises click.UsageError for invalid combinations:
    - --file and --copy together
    - --file and --json together
    - --open or --reveal without --file

    Args:
        file_path: File output path (or "auto")
        copy: Copy to clipboard flag
        output_json: JSON output flag
        open_after: Open after save flag
        reveal_after: Reveal after save flag

    Raises:
        SystemExit: If validation fails
    """
    if file_path and copy:
        click.echo("Error: --file and --copy cannot be used together", err=True)
        sys.exit(1)
    if file_path and output_json:
        click.echo("Error: --file and --json cannot be used together", err=True)
        sys.exit(1)
    if (open_after or reveal_after) and not file_path:
        click.echo("Error: --open and --reveal require --file", err=True)
        sys.exit(1)


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """
    Return singular or plural form based on count.

    Args:
        count: The count to check
        singular: Singular form of the word
        plural: Plural form (defaults to singular + "s")

    Returns:
        Appropriate word form

    Example:
        pluralize(1, "element")  # "element"
        pluralize(5, "element")  # "elements"
        pluralize(1, "property", "properties")  # "property"
        pluralize(5, "property", "properties")  # "properties"
    """
    if plural is None:
        plural = singular + "s"
    return singular if count == 1 else plural


def _strip_background_colors(content: str) -> str:
    """
    Strip all background color codes from ANSI-escaped content.

    Handles both standalone background codes and combined sequences
    like \\033[38;5;N;48;5;Mm where foreground and background are together.

    Args:
        content: String potentially containing ANSI escape sequences

    Returns:
        Content with background colors removed, foreground colors preserved
    """
    import re

    def process_escape_sequence(match: re.Match) -> str:
        """Process a single ANSI escape sequence, removing background codes."""
        codes_str = match.group(1)
        if not codes_str:
            return match.group(0)

        codes = codes_str.split(';')
        filtered_codes = []
        i = 0

        while i < len(codes):
            code = codes[i]

            # Skip background color codes
            if code == '48':
                # 48;5;N (256-color) or 48;2;R;G;B (24-bit)
                if i + 1 < len(codes) and codes[i + 1] == '5':
                    i += 3  # Skip 48;5;N
                    continue
                elif i + 1 < len(codes) and codes[i + 1] == '2':
                    i += 5  # Skip 48;2;R;G;B
                    continue
            elif code in ('40', '41', '42', '43', '44', '45', '46', '47', '49'):
                # Standard background colors 40-47, default 49
                i += 1
                continue
            elif code in ('100', '101', '102', '103', '104', '105', '106', '107'):
                # Bright background colors 100-107
                i += 1
                continue

            filtered_codes.append(code)
            i += 1

        if not filtered_codes:
            return ''  # All codes were background-related

        return f'\033[{";".join(filtered_codes)}m'

    # Match ANSI escape sequences: \033[ followed by codes, ending with m
    ansi_pattern = re.compile(r'\x1b\[([0-9;]*)m')
    return ansi_pattern.sub(process_escape_sequence, content)


def _build_quote_state(text: str) -> list[bool]:
    """
    Precompute quote state for all positions in O(n) time.

    Returns a list where quote_state[i] is True if position i is inside quotes.
    This avoids O(n²) complexity when checking multiple positions.
    """
    quote_state = []
    in_double = False
    in_single = False
    for char in text:
        if char == '"' and not in_single:
            in_double = not in_double
        elif char == "'" and not in_double:
            in_single = not in_single
        quote_state.append(in_double or in_single)
    return quote_state


def _wrap_ansi_line_fast(line: str, max_width: int, ansi_pattern: 're.Pattern') -> list[str]:
    """
    Fast line wrapping for very long lines (>2000 chars).

    Uses simple hard breaks without word-boundary detection or quote awareness.
    Much faster than smart wrapping for SVG paths, base64 data, etc.

    Preserves ANSI formatting across wrapped lines.
    """
    wrapped_lines = []
    active_codes = []
    current_segment = []
    visible_count = 0
    i = 0

    while i < len(line):
        # Check for ANSI escape sequence
        if line[i] == '\x1b' and i + 1 < len(line) and line[i + 1] == '[':
            # Find end of ANSI sequence
            j = i + 2
            while j < len(line) and line[j] != 'm':
                j += 1
            if j < len(line):
                code = line[i : j + 1]
                current_segment.append(code)
                # Track active codes for continuation
                if code == '\033[0m' or code == '\033[m':
                    active_codes = []
                else:
                    active_codes.append(code)
                i = j + 1
                continue

        # Regular character
        current_segment.append(line[i])
        visible_count += 1

        # Check if we need to wrap
        if visible_count >= max_width:
            wrapped_lines.append(''.join(current_segment))
            # Start new segment with active codes
            current_segment = list(active_codes)
            visible_count = 0

        i += 1

    # Add remaining content
    if current_segment:
        wrapped_lines.append(''.join(current_segment))

    return wrapped_lines if wrapped_lines else [line]


def _wrap_ansi_line(
    line: str,
    max_width: int,
    ansi_pattern: 're.Pattern',
    plain_text: str | None = None,
) -> list[str]:
    """
    Wrap a line containing ANSI escape codes to fit within max_width visible chars.

    Uses smart word-aware wrapping:
    - Tries to break at spaces outside of quoted strings
    - Falls back to any space if no safe break point
    - Hard breaks at max_width if no spaces at all

    For very long lines (>2000 chars), uses fast hard-break wrapping to avoid
    performance issues with SVG paths, base64 data, etc.

    Preserves ANSI formatting across wrapped lines by tracking active codes.

    Args:
        line: Line potentially containing ANSI escape sequences
        max_width: Maximum visible character width per line
        ansi_pattern: Compiled regex for matching ANSI sequences
        plain_text: Pre-computed plain text (without ANSI codes) to avoid redundant regex

    Returns:
        List of wrapped line segments
    """
    if max_width <= 0:
        return [line]

    # Use pre-computed plain text if provided, otherwise compute it
    if plain_text is None:
        plain_text = ansi_pattern.sub('', line)

    # If it fits, no wrapping needed
    if len(plain_text) <= max_width:
        return [line]

    # FAST PATH: For very long lines (SVG paths, base64, etc.), use simple hard breaks.
    # Smart word-wrapping is expensive and doesn't benefit data-heavy content.
    if len(plain_text) > 2000:
        return _wrap_ansi_line_fast(line, max_width, ansi_pattern)

    # Build a mapping of plain text positions to original line positions
    plain_to_orig = []
    orig_pos = 0
    for match in ansi_pattern.finditer(line):
        while orig_pos < match.start():
            plain_to_orig.append(orig_pos)
            orig_pos += 1
        orig_pos = match.end()
    while orig_pos < len(line):
        plain_to_orig.append(orig_pos)
        orig_pos += 1

    # Precompute quote state for O(1) lookups (avoids O(n²) on lines with many spaces)
    quote_state = _build_quote_state(plain_text)

    # Find safe break points (spaces outside quotes)
    def find_break_point(start: int, end: int) -> int:
        """Find best break point, preferring spaces outside quotes."""
        # First try: find space outside quotes
        for i in range(end - 1, start, -1):
            if plain_text[i] == ' ' and not quote_state[i]:
                return i + 1

        # Second try: any space (even inside quotes)
        for i in range(end - 1, start, -1):
            if plain_text[i] == ' ':
                return i + 1

        # No space found - hard break
        return end

    # Do the wrapping
    wrapped_lines = []
    active_codes = []
    plain_start = 0

    while plain_start < len(plain_text):
        plain_end = min(plain_start + max_width, len(plain_text))

        if plain_end < len(plain_text):
            break_point = find_break_point(plain_start, plain_end)
        else:
            break_point = plain_end

        # Extract segment from original line
        if plain_start == 0:
            orig_start = 0
        else:
            orig_start = plain_to_orig[plain_start]

        if break_point >= len(plain_text):
            orig_end = len(line)
        else:
            orig_end = plain_to_orig[break_point]

        segment = line[orig_start:orig_end]

        # Prepend active ANSI codes for continuation lines
        if wrapped_lines:
            segment = ''.join(active_codes) + segment

        # Track ANSI codes for next line
        for match in ansi_pattern.finditer(segment):
            code = match.group()
            if code == '\033[0m' or code == '\033[m':
                active_codes = []
            else:
                active_codes.append(code)

        wrapped_lines.append(segment)
        plain_start = break_point

    return wrapped_lines if wrapped_lines else [line]


def print_code_block(content: str, syntax_highlighted: bool = False) -> None:
    """
    Print content in a styled code block with dark background.

    Creates a visually distinct code block appearance with:
    - Dark gray background spanning terminal width
    - 2-space horizontal padding on each side
    - 1-line vertical padding above and below
    - Proper word wrapping for long lines

    Args:
        content: The text content to display (can be multi-line)
        syntax_highlighted: If True, content already has ANSI codes;
                           preserve them but add background
    """
    import re
    import shutil

    # Get terminal width, default to 80
    term_width = shutil.get_terminal_size((80, 24)).columns

    # Use 24-bit true color for very dark gray background (RGB 30,30,30)
    bg_dark = "\033[48;2;30;30;30m"
    reset = "\033[0m"

    # Regex pattern for ALL ANSI escape sequences (for length calculation)
    ansi_pattern = re.compile(r'\x1b\[[0-9;]*m')

    # Strip background colors from content (preserves foreground colors)
    content = _strip_background_colors(content)

    # Calculate available width for content (minus 2-space padding on each side)
    content_width = term_width - 4

    # Print top padding line (solid dark bar)
    click.echo(f"{bg_dark}{' ' * term_width}{reset}")

    # Process each line of content
    for line in content.split('\n'):
        # Calculate visible length (strip ANSI codes for length calculation)
        visible_text = ansi_pattern.sub('', line)
        visible_len = len(visible_text)

        # Check if line needs wrapping
        if visible_len > content_width:
            # Wrap the line (pass pre-computed visible_text to avoid redundant regex)
            wrapped = _wrap_ansi_line(line, content_width, ansi_pattern, visible_text)
            for wrapped_line in wrapped:
                # Calculate visible length of wrapped segment
                wrapped_visible = ansi_pattern.sub('', wrapped_line)
                wrapped_len = len(wrapped_visible)
                right_padding = max(0, term_width - 2 - wrapped_len - 2)
                styled_line = f"{bg_dark}  {wrapped_line}{' ' * (right_padding + 2)}{reset}"
                click.echo(styled_line)
        else:
            # Line fits - no wrapping needed
            right_padding = max(0, term_width - 2 - visible_len - 2)
            styled_line = f"{bg_dark}  {line}{' ' * (right_padding + 2)}{reset}"
            click.echo(styled_line)

    # Print bottom padding line (solid dark bar)
    click.echo(f"{bg_dark}{' ' * term_width}{reset}")
