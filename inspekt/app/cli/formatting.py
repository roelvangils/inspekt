"""Shared formatting utilities for record and replay commands."""

import json
import re
from pathlib import Path

import click

from inspekt.app.cli.icons import get_action_icon, get_status_icon


def get_terminal_width() -> int:
    """Get the current terminal width, defaulting to 80 if unavailable."""
    try:
        import shutil
        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def strip_icon_font_chars(text: str) -> str:
    """Strip Private Use Area (PUA) characters used by icon fonts.

    Icon fonts like Font Awesome, Material Icons, etc. use characters in
    Unicode's Private Use Area ranges. These appear as invisible boxes
    or missing glyphs in terminals without the font installed.

    PUA ranges:
    - U+E000 to U+F8FF (Basic Multilingual Plane PUA)
    - U+F0000 to U+FFFFD (Supplementary PUA-A)
    - U+100000 to U+10FFFD (Supplementary PUA-B)
    """
    if not text:
        return text

    # Build pattern for PUA ranges
    # \uE000-\uF8FF covers BMP PUA
    # For supplementary planes, we need to handle surrogate pairs in Python
    result = []
    for char in text:
        code = ord(char)
        # Skip if in any PUA range
        if (0xE000 <= code <= 0xF8FF or      # BMP PUA
            0xF0000 <= code <= 0xFFFFD or    # Supplementary PUA-A
            0x100000 <= code <= 0x10FFFD):   # Supplementary PUA-B
            continue
        result.append(char)

    return ''.join(result)


def sanitize_display_name(text: str, max_length: int = 25) -> str:
    """Sanitize text for display: strip icon fonts and collapse whitespace."""
    if not text:
        return ""
    text = strip_icon_font_chars(text)
    text = " ".join(text.split())  # Collapse whitespace
    return text[:max_length] if len(text) > max_length else text


def truncate_to_width(text: str, max_width: int, suffix: str = "…") -> str:
    """Truncate text to fit within max_width, accounting for ANSI escape codes."""
    # Remove ANSI escape codes to get actual visible length
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    visible_text = ansi_escape.sub('', text)

    if len(visible_text) <= max_width:
        return text

    # Need to truncate - find where to cut
    # We need to keep track of visible chars vs total chars (including ANSI)
    visible_count = 0
    cut_index = 0
    i = 0

    while i < len(text) and visible_count < max_width - len(suffix):
        # Check if we're at an ANSI escape sequence
        match = re.match(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', text[i:])
        if match:
            # Skip the escape sequence entirely
            i += len(match.group())
        else:
            visible_count += 1
            i += 1
        cut_index = i

    # Find any unclosed ANSI sequences and close them
    return text[:cut_index] + click.style(suffix, fg="bright_black")


def format_elapsed(ms: int) -> str:
    """Format milliseconds as MM:SS or HH:MM:SS."""
    total_seconds = ms // 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration (e.g., '1.5s', '2m 30s')."""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        minutes = ms // 60000
        seconds = (ms % 60000) / 1000
        return f"{minutes}m {seconds:.0f}s"


def get_recordings_dir() -> Path:
    """Get the directory for storing recordings from config.

    Default is the current working directory.
    Can be configured in config.json under paths.recordings.
    """
    from inspekt.config import get_paths_config

    paths = get_paths_config()
    recordings_dir = paths["recordings"]

    # Ensure directory exists
    recordings_dir.mkdir(parents=True, exist_ok=True)
    return recordings_dir


def format_step_for_display(
    step: dict,
    step_num: int = 0,
    elapsed_ms: int = 0,
    use_color: bool = True,
    reserve_suffix_width: int = 0,
) -> str:
    """Format a step for terminal display with colors.

    Format: 001  00:00  action    → selector "name" (tag)

    Args:
        step: Step dictionary with action, target, etc.
        step_num: Step number (displayed with leading zeros)
        elapsed_ms: Elapsed time in milliseconds
        use_color: Whether to use ANSI colors
        reserve_suffix_width: Reserve this many characters at the end (for status like " OK")

    Returns:
        Formatted string, truncated to fit terminal width
    """
    action = step.get("action", "unknown")
    target = step.get("target", {})
    selector = target.get("selector", "") if target else ""
    accessible_name = target.get("accessible_name", "") if target else ""
    tag = target.get("tag", "") if target else ""

    # Sanitize accessible_name: strip icon font glyphs and collapse whitespace
    if accessible_name:
        accessible_name = strip_icon_font_chars(accessible_name)
        accessible_name = " ".join(accessible_name.split())

    # Get terminal width for truncation (minus reserved suffix space)
    term_width = get_terminal_width() - reserve_suffix_width

    # Format components
    step_num_str = f"{step_num:03d}"
    elapsed = format_elapsed(elapsed_ms)
    action_str = action.ljust(9)

    # Get action icon (if nerdfont enabled)
    action_icon = get_action_icon(action) if use_color else None

    # Color scheme
    if use_color:
        step_num_colored = click.style(step_num_str, fg="cyan", bold=True)
        elapsed_colored = click.style(elapsed, fg="bright_black")
        arrow = click.style("→", fg="bright_black")

        # Action colors based on type
        action_colors = {
            "navigate": "blue",
            "click": "green",
            "rightclick": "green",
            "activate": "bright_green",
            "type": "yellow",
            "keypress": "magenta",
            "hover": "white",
            "scroll": "blue",
            "check": "green",
            "uncheck": "red",
            "select": "cyan",
            "inspekt": "cyan",
        }
        action_color = action_colors.get(action, "white")

        # Add icon before action if available
        if action_icon:
            action_display = f"{action_icon} {action_str}"
        else:
            action_display = action_str
        action_colored = click.style(action_display, fg=action_color)
    else:
        step_num_colored = step_num_str
        elapsed_colored = elapsed
        arrow = "→"
        action_colored = action_str

    prefix = f"{step_num_colored}  {elapsed_colored}  {action_colored} {arrow}"

    if action == "navigate":
        url = step.get("url", "")
        url_display = click.style(url, fg="blue", underline=True) if use_color else url
        result = f"{prefix} {url_display}"
        return truncate_to_width(result, term_width)

    elif action in ("click", "rightclick", "activate"):
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = selector[:35] if len(selector) > 35 else selector
        tag_display = click.style(f" ({tag})", fg="bright_black") if tag and use_color else (f" ({tag})" if tag else "")
        # Use bright_green for activate to distinguish from mouse click
        name_color = "bright_green" if action == "activate" else "green"
        name_display = click.style(f'"{name}"', fg=name_color) if name and use_color else (f'"{name}"' if name else "")
        if name:
            result = f"{prefix} {sel_display} {name_display}{tag_display}"
        else:
            result = f"{prefix} {sel_display}{tag_display}"
        return truncate_to_width(result, term_width)

    elif action == "type":
        value = step.get("value", "")
        sel_display = selector[:35] if len(selector) > 35 else selector
        # Get input type if available
        input_type = target.get("attributes", {}).get("type", "") if target else ""
        type_display = click.style(f" [{input_type}]", fg="bright_black") if input_type and input_type != "text" and use_color else (f" [{input_type}]" if input_type and input_type != "text" else "")
        if step.get("sensitive"):
            pwd_display = click.style("(password)", fg="red") if use_color else "(password)"
            result = f"{prefix} {sel_display} {pwd_display}"
        else:
            char_count = len(value)
            chars_display = click.style(f"({char_count} chars)", fg="yellow") if use_color else f"({char_count} chars)"
            result = f"{prefix} {sel_display} {chars_display}{type_display}"
        return truncate_to_width(result, term_width)

    elif action == "keypress":
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])
        if modifiers:
            key_str = "+".join(modifiers) + "+" + key
        else:
            key_str = key
        key_display = click.style(key_str, fg="magenta", bold=True) if use_color else key_str

        # For Tab/Shift-Tab, show the accessible name of the focused element
        if key == "Tab" and accessible_name:
            name_display = click.style(f"({accessible_name})", fg="bright_black") if use_color else f"({accessible_name})"
            result = f"{prefix} {key_display} {name_display}"
        else:
            result = f"{prefix} {key_display}"
        return truncate_to_width(result, term_width)

    elif action == "hover":
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = selector[:35] if len(selector) > 35 else selector
        tag_display = click.style(f" ({tag})", fg="bright_black") if tag and use_color else (f" ({tag})" if tag else "")
        name_display = click.style(f'"{name}"', fg="white") if name and use_color else (f'"{name}"' if name else "")
        if name:
            result = f"{prefix} {sel_display} {name_display}{tag_display}"
        else:
            result = f"{prefix} {sel_display}{tag_display}"
        return truncate_to_width(result, term_width)

    elif action == "check":
        # Checkbox or radio button checked
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = selector[:35] if len(selector) > 35 else selector
        value = step.get("value", "")
        # Show value if available (for radio buttons especially)
        value_display = click.style(f'"{value}"', fg="green") if value and use_color else (f'"{value}"' if value else "")
        name_display = click.style(f'"{name}"', fg="green") if name and use_color else (f'"{name}"' if name else "")
        # Prefer value over name for radio buttons
        display = value_display if value else name_display
        if display:
            result = f"{prefix} {sel_display} {display}"
        else:
            result = f"{prefix} {sel_display}"
        return truncate_to_width(result, term_width)

    elif action == "uncheck":
        # Checkbox unchecked
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = selector[:35] if len(selector) > 35 else selector
        name_display = click.style(f'"{name}"', fg="red") if name and use_color else (f'"{name}"' if name else "")
        if name:
            result = f"{prefix} {sel_display} {name_display}"
        else:
            result = f"{prefix} {sel_display}"
        return truncate_to_width(result, term_width)

    elif action == "select":
        # Dropdown/select element
        sel_display = selector[:35] if len(selector) > 35 else selector
        option_text = step.get("option_text", "")
        value = step.get("value", "")
        # Prefer showing option text over raw value
        display_text = option_text or value
        if display_text:
            text_display = click.style(f'"{display_text}"', fg="cyan") if use_color else f'"{display_text}"'
            result = f"{prefix} {sel_display} {text_display}"
        else:
            result = f"{prefix} {sel_display}"
        return truncate_to_width(result, term_width)

    elif action == "scroll":
        scroll = step.get("scroll", {})
        delta_y = scroll.get("deltaY", 0)
        target_y = scroll.get("y", 0)

        # Determine scroll direction
        if delta_y > 0:
            direction = "↓"
            direction_text = "down"
        elif delta_y < 0:
            direction = "↑"
            direction_text = "up"
        else:
            direction = "→"
            direction_text = "horizontal"

        # Format scroll amount
        pixels = abs(delta_y) if delta_y != 0 else abs(scroll.get("deltaX", 0))
        amount = f"{pixels}px {direction_text}"

        if use_color:
            direction_display = click.style(direction, fg="blue", bold=True)
            amount_display = click.style(amount, fg="bright_black")
            result = f"{prefix} {direction_display} {amount_display}"
        else:
            result = f"{prefix} {direction} {amount}"
        return truncate_to_width(result, term_width)

    elif action == "inspekt":
        cmd = step.get("command", "")
        cmd_display = click.style(cmd, fg="cyan") if use_color else cmd
        result = f"{prefix} {cmd_display}"
        return truncate_to_width(result, term_width)

    result = f"{prefix} {json.dumps(step)[:40]}"
    return truncate_to_width(result, term_width)


def format_system_message(message: str, use_color: bool = True) -> str:
    """Format a system message with ... prefix, truncated to terminal width."""
    term_width = get_terminal_width()
    dots = click.style("...", fg="bright_black", bold=True) if use_color else "..."
    msg = click.style(message, fg="bright_black", italic=True) if use_color else message
    result = f"{dots}  {msg}"
    return truncate_to_width(result, term_width)


def format_status(status: str, use_color: bool = True) -> str:
    """Format a status indicator (OK, FAIL, SKIP) with appropriate color and icon."""
    if not use_color:
        return f" {status}"

    status_colors = {
        "OK": "green",
        "FAIL": "red",
        "SKIP": "cyan",
    }
    color = status_colors.get(status, "white")

    # Get status icon if nerdfont enabled
    status_icon = None
    if status == "OK":
        status_icon = get_status_icon("pass")
    elif status == "FAIL":
        status_icon = get_status_icon("fail")
    elif status == "SKIP":
        status_icon = get_status_icon("unknown")

    if status_icon:
        # For OK, just show the green icon without text
        if status == "OK":
            return " " + click.style(status_icon, fg="green")
        return " " + click.style(f"{status_icon} {status}", fg=color)
    return " " + click.style(status, fg=color)
