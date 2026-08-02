"""Shared formatting utilities for record and replay commands."""

import json
import re
from pathlib import Path

import click

from inspekt.app.cli.icons import (
    get_action_icon,
    get_keypress_icon,
    get_native_control_icon,
    get_status_icon,
    get_step_mode_icon,
)
from inspekt.services.formatting_utils import format_filesize


def get_terminal_width() -> int:
    """Get the current terminal width, defaulting to 80 if unavailable."""
    try:
        import shutil

        return shutil.get_terminal_size().columns
    except Exception:
        return 80


def truncate_text(text: str, max_length: int, suffix: str = "…") -> str:
    """Truncate text to max_length, adding suffix if truncated.

    Args:
        text: The text to truncate
        max_length: Maximum length including suffix
        suffix: String to append when truncated (default: ellipsis)

    Returns:
        Truncated text with suffix, or original if short enough
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


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
        if (
            0xE000 <= code <= 0xF8FF  # BMP PUA
            or 0xF0000 <= code <= 0xFFFFD  # Supplementary PUA-A
            or 0x100000 <= code <= 0x10FFFD
        ):  # Supplementary PUA-B
            continue
        result.append(char)

    return "".join(result)


def sanitize_display_name(text: str, max_length: int = 25) -> str:
    """Sanitize text for display: strip icon fonts and collapse whitespace."""
    if not text:
        return ""
    text = strip_icon_font_chars(text)
    text = " ".join(text.split())  # Collapse whitespace
    return text[:max_length] if len(text) > max_length else text


def unescape_css_selector(selector: str) -> str:
    r"""Unescape CSS selector escape sequences for display.

    CSS.escape() in JavaScript escapes special characters with backslashes:
    - Spaces become backslash-space: `Open\ deze`
    - Colons, dots, etc.: `\:`, `\.`

    This function reverses those escapes for human-readable display.
    """
    if not selector:
        return selector

    # Pattern matches backslash followed by any character
    # CSS escape: \X where X is any character (including space)
    return re.sub(r"\\(.)", r"\1", selector)


def format_selector_display(selector: str, max_length: int = 35) -> str:
    """Format a CSS selector for display: unescape and truncate.

    Args:
        selector: Raw CSS selector (may contain escape sequences)
        max_length: Maximum display length (default: 35)

    Returns:
        Human-readable, truncated selector
    """
    unescaped = unescape_css_selector(selector)
    return unescaped[:max_length] if len(unescaped) > max_length else unescaped


def style_primary_key(key: str) -> str:
    """Style a keyboard key for primary actions (e.g., Ctrl+C to stop).

    Uses bright yellow background with black text for high visibility.
    """
    return click.style(f" {key} ", fg="black", bg="bright_yellow")


def style_secondary_key(key: str) -> str:
    """Style a keyboard key for secondary actions (e.g., undo/redo).

    Uses dark gray background with white text for subtle visibility.
    """
    return click.style(f" {key} ", fg="white", bg="bright_black")


def truncate_to_width(text: str, max_width: int, suffix: str = "…") -> str:
    """Truncate text to fit within max_width, accounting for ANSI escape codes."""
    # Remove ANSI escape codes to get actual visible length
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    visible_text = ansi_escape.sub("", text)

    if len(visible_text) <= max_width:
        return text

    # Need to truncate - find where to cut
    # We need to keep track of visible chars vs total chars (including ANSI)
    visible_count = 0
    cut_index = 0
    i = 0

    while i < len(text) and visible_count < max_width - len(suffix):
        # Check if we're at an ANSI escape sequence
        match = re.match(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", text[i:])
        if match:
            # Skip the escape sequence entirely
            i += len(match.group())
        else:
            visible_count += 1
            i += 1
        cut_index = i

    # Find any unclosed ANSI sequences and close them
    return text[:cut_index] + click.style(suffix, fg="bright_black")


def format_elapsed(ms: int, show_milliseconds: bool = True, use_color: bool = True) -> str:
    """Format milliseconds as MM:SS or MM:SS.mmm.

    Args:
        ms: Elapsed time in milliseconds
        show_milliseconds: Whether to show .mmm suffix (default: True)
        use_color: Whether to style milliseconds in dark gray (default: True)

    Returns:
        Formatted time string, e.g. "01:23" or "01:23.456"
    """
    total_seconds = ms // 1000
    millis = ms % 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    base = f"{minutes:02d}:{seconds:02d}"

    if show_milliseconds:
        ms_str = f".{millis:03d}"
        if use_color:
            return base + click.style(ms_str, fg="bright_black")
        return base + ms_str
    return base


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


def format_step_header(
    use_color: bool = True, indent: bool = False, show_milliseconds: bool = True
) -> str:
    """Format the header row for step display.

    Args:
        use_color: Whether to use ANSI colors
        indent: Whether to include 2-space indent
        show_milliseconds: Whether to account for milliseconds column width (default: True)

    Returns:
        Formatted header string with columns: STEP, START, COMMAND, DETAILS
    """
    import shutil

    # Header aligned to match step format:
    # Without milliseconds: "{indent}{0001}   {00:00}   {icon action      }   details"
    # With milliseconds:    "{indent}{0001}   {00:00.000}   {icon action      }   details"
    #                                4ch     5ch/9ch       ~13ch (icon+sp+10ch)  3sp
    prefix = "  " if indent else ""
    if show_milliseconds:
        # START column: 9 chars (00:00.000), header padded to match
        header = f"{prefix}STEP   START        COMMAND          DETAILS"
    else:
        # START column: 5 chars (00:00)
        header = f"{prefix}STEP   START   COMMAND          DETAILS"

    if use_color:
        # Pad to terminal width for full-width background
        try:
            terminal_width = shutil.get_terminal_size().columns
        except Exception:
            terminal_width = 80
        padded_header = header.ljust(terminal_width)
        return click.style(padded_header, fg="bright_white", bg="black")
    return header


def format_step_for_display(
    step: dict,
    step_num: int = 0,
    elapsed_ms: int = 0,
    use_color: bool = True,
    reserve_suffix_width: int = 0,
    indent: bool = False,
    is_native: bool = False,
    native_mode: bool = False,
    dimmed_icon: bool = False,
    show_milliseconds: bool = True,
) -> str:
    """Format a step for terminal display with colors.

    Format: 0001   00:00.000   󰖟  navigate   details…

    Args:
        step: Step dictionary with action, target, etc.
        step_num: Step number (displayed with leading zeros)
        elapsed_ms: Elapsed time in milliseconds
        use_color: Whether to use ANSI colors
        reserve_suffix_width: Reserve this many characters at the end (for status like " OK")
        indent: Whether to include 2-space indent
        is_native: Whether this action was executed natively (shows platform icon in yellow)
        native_mode: Whether we're in --native replay mode (shows JS icon for non-native steps)
        dimmed_icon: Whether to show platform/JS icon in dark gray (for skipped/merged steps)
        show_milliseconds: Whether to show milliseconds in timestamp (default: True)

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

    # Format components (4 digits for step number, 3 spaces between columns)
    step_num_str = f"{step_num:04d}"
    elapsed = format_elapsed(elapsed_ms, show_milliseconds=show_milliseconds, use_color=use_color)
    action_str = action.ljust(12)

    # For 'set' action, show "set <type>" like "set time", "set date", etc.
    if action == "set":
        input_type = target.get("input_type", "") if target else ""
        # Use shorter display names for input types
        type_display_names = {
            "time": "time",
            "date": "date",
            "datetime-local": "date&time",
            "month": "month",
            "week": "week",
            "range": "range",
            "number": "number",
            "color": "color",
        }
        type_name = type_display_names.get(input_type, input_type)
        if type_name:
            action_str = f"set {type_name}".ljust(12)

    # Get action icon (if nerdfont enabled)
    # For keypress, get the specific icon based on key and modifiers
    # For set, get the native control-specific icon based on input type
    if action == "keypress" and use_color:
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])
        action_icon = get_keypress_icon(key, modifiers)
    elif action == "set" and use_color:
        input_type = target.get("input_type", "") if target else ""
        action_icon = get_native_control_icon(input_type) or get_action_icon(action)
    else:
        action_icon = get_action_icon(action) if use_color else None

    # Color scheme
    if use_color:
        step_num_colored = click.style(step_num_str, fg="cyan", bold=True)
        elapsed_colored = elapsed  # White (default) for actual recorded steps

        # Action colors based on type
        action_colors = {
            "navigate": "blue",
            "click": "green",
            "rightclick": "green",
            "activate": "bright_green",
            "type": "yellow",
            "set": "yellow",
            "keypress": "magenta",
            "hover": "white",
            "scroll": "blue",
            "check": "green",
            "uncheck": "red",
            "radio": "green",
            "select": "cyan",
            "toggle": "cyan",
            "dialog": "magenta",
            "jsdialog": "yellow",
            "upload": "yellow",
            "download": "cyan",
            "inspekt": "cyan",
        }
        action_color = action_colors.get(action, "white")

        # When dimmed, use gray for the entire action (icon + text)
        if dimmed_icon:
            action_color = "bright_black"

        # Add icon before action if available
        # In native mode: show platform icon (yellow) for native steps, JS icon for non-native steps
        # When dimmed_icon=True, show icons in dark gray (for skipped/merged steps)
        js_icon = "\ue60c"  # nf-seti-javascript
        icon_color = "bright_black" if dimmed_icon else "yellow"
        if is_native:
            from inspekt.app.cli.icons import get_platform_icon

            platform_icon = get_platform_icon() or ""
            # Platform icon (yellow normally, dark gray when dimmed)
            action_str_native = action.ljust(10) + click.style(platform_icon, fg=icon_color)
            if action_icon:
                action_display = f"{action_icon} {action_str_native}"
            else:
                action_display = f"  {action_str_native}"
        elif native_mode:
            # Non-native step in native mode - show JS icon (always bright_black)
            action_str_js = action.ljust(10) + click.style(js_icon, fg="bright_black")
            if action_icon:
                action_display = f"{action_icon} {action_str_js}"
            else:
                action_display = f"  {action_str_js}"
        elif action_icon:
            action_display = f"{action_icon} {action_str}"
        else:
            action_display = f"  {action_str}"  # Align with icon width
        action_colored = click.style(action_display, fg=action_color)
    else:
        step_num_colored = step_num_str
        elapsed_colored = elapsed
        action_colored = action_str

    # Build prefix with optional 2-space indent and 3-space column gaps
    indent_str = "  " if indent else ""
    prefix = f"{indent_str}{step_num_colored}   {elapsed_colored}   {action_colored}"

    if action == "navigate":
        url = step.get("url", "")
        url_display = click.style(url, fg="blue", underline=True) if use_color else url
        result = f"{prefix}   {url_display}"
        return truncate_to_width(result, term_width)

    elif action in ("click", "rightclick", "activate"):
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = format_selector_display(selector)
        tag_display = (
            click.style(f" ({tag})", fg="bright_black")
            if tag and use_color
            else (f" ({tag})" if tag else "")
        )
        # Use bright_green for activate to distinguish from mouse click
        name_color = "bright_green" if action == "activate" else "green"
        name_display = (
            click.style(f'"{name}"', fg=name_color)
            if name and use_color
            else (f'"{name}"' if name else "")
        )
        if name:
            # When we have an accessible name, skip the selector (it's redundant)
            result = f"{prefix}   {name_display}{tag_display}"
        else:
            result = f"{prefix}   {sel_display}{tag_display}"
        return truncate_to_width(result, term_width)

    elif action == "type":
        value = step.get("value", "")
        sel_display = format_selector_display(selector)
        # Get input type if available
        input_type = target.get("attributes", {}).get("type", "") if target else ""
        type_display = (
            click.style(f" [{input_type}]", fg="bright_black")
            if input_type and input_type != "text" and use_color
            else (f" [{input_type}]" if input_type and input_type != "text" else "")
        )
        if step.get("sensitive"):
            pwd_display = click.style("(password)", fg="red") if use_color else "(password)"
            result = f"{prefix}   {sel_display} {pwd_display}"
        else:
            char_count = len(value)
            chars_display = (
                click.style(f"({char_count} chars)", fg="yellow")
                if use_color
                else f"({char_count} chars)"
            )
            result = f"{prefix}   {sel_display} {chars_display}{type_display}"
        return truncate_to_width(result, term_width)

    elif action == "set":
        # Native control value set (range, date, time, number, color, etc.)
        value = step.get("value", "")
        sel_display = format_selector_display(selector)
        value_display = click.style(f"({value})", fg="yellow") if use_color else f"({value})"
        result = f"{prefix}   {sel_display} {value_display}"
        return truncate_to_width(result, term_width)

    elif action == "keypress":
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])
        if modifiers:
            key_str = "+".join(modifiers) + "+" + key
        else:
            key_str = key
        key_display = click.style(key_str, fg="magenta", bold=True) if use_color else key_str

        # For Tab/Shift-Tab, show context about the focused element
        if key == "Tab":
            # Special display for native controls (media elements and inputs with closed Shadow DOM)
            if tag == "audio":
                display_name = "Native Audio Player"
            elif tag == "video":
                display_name = "Native Video Player"
            elif tag == "input":
                # Check for native control input types with closed Shadow DOM
                input_type = target.get("input_type", "") if target else ""
                native_control_names = {
                    "range": "Native Range Slider",
                    "date": "Native Date Picker",
                    "time": "Native Time Picker",
                    "datetime-local": "Native Datetime Picker",
                    "month": "Native Month Picker",
                    "week": "Native Week Picker",
                    "number": "Native Number Spinner",
                    "color": "Native Color Picker",
                }
                display_name = native_control_names.get(input_type, accessible_name)
            else:
                display_name = accessible_name

            if display_name:
                name_display = (
                    click.style(f"({display_name})", fg="bright_black")
                    if use_color
                    else f"({display_name})"
                )
                result = f"{prefix}   {key_display} {name_display}"
            else:
                result = f"{prefix}   {key_display}"
        else:
            result = f"{prefix}   {key_display}"
        return truncate_to_width(result, term_width)

    elif action == "hover":
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = format_selector_display(selector)
        tag_display = (
            click.style(f" ({tag})", fg="bright_black")
            if tag and use_color
            else (f" ({tag})" if tag else "")
        )
        name_display = (
            click.style(f'"{name}"', fg="white")
            if name and use_color
            else (f'"{name}"' if name else "")
        )
        if name:
            # When we have an accessible name, skip the selector (it's redundant)
            result = f"{prefix}   {name_display}{tag_display}"
        else:
            result = f"{prefix}   {sel_display}{tag_display}"
        return truncate_to_width(result, term_width)

    elif action == "check":
        # Checkbox or radio button checked
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = format_selector_display(selector)
        value = step.get("value", "")
        # Show value if available (for radio buttons especially)
        value_display = (
            click.style(f'"{value}"', fg="green")
            if value and use_color
            else (f'"{value}"' if value else "")
        )
        name_display = (
            click.style(f'"{name}"', fg="green")
            if name and use_color
            else (f'"{name}"' if name else "")
        )
        # Prefer value over name for radio buttons
        display = value_display if value else name_display
        if display:
            # When we have a display name, skip the selector (it's redundant)
            result = f"{prefix}   {display}"
        else:
            result = f"{prefix}   {sel_display}"
        return truncate_to_width(result, term_width)

    elif action == "uncheck":
        # Checkbox unchecked
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = format_selector_display(selector)
        name_display = (
            click.style(f'"{name}"', fg="red")
            if name and use_color
            else (f'"{name}"' if name else "")
        )
        if name:
            # When we have an accessible name, skip the selector (it's redundant)
            result = f"{prefix}   {name_display}"
        else:
            result = f"{prefix}   {sel_display}"
        return truncate_to_width(result, term_width)

    elif action == "radio":
        # Radio button selected
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        sel_display = format_selector_display(selector)
        value = step.get("value", "")
        # Show value for radio buttons (more meaningful than label)
        value_display = (
            click.style(f'"{value}"', fg="green")
            if value and use_color
            else (f'"{value}"' if value else "")
        )
        name_display = (
            click.style(f'"{name}"', fg="green")
            if name and use_color
            else (f'"{name}"' if name else "")
        )
        # Prefer value over name for radio buttons
        display = value_display if value else name_display
        if display:
            # When we have a display name, skip the selector (it's redundant)
            result = f"{prefix}   {display}"
        else:
            result = f"{prefix}   {sel_display}"
        return truncate_to_width(result, term_width)

    elif action == "select":
        # Dropdown/select element
        sel_display = format_selector_display(selector)
        option_text = step.get("option_text", "")
        value = step.get("value", "")
        # Prefer showing option text over raw value
        display_text = option_text or value
        if display_text:
            text_display = (
                click.style(f'"{display_text}"', fg="cyan") if use_color else f'"{display_text}"'
            )
            result = f"{prefix}   {sel_display} {text_display}"
        else:
            result = f"{prefix}   {sel_display}"
        return truncate_to_width(result, term_width)

    elif action == "scroll":
        scroll = step.get("scroll", {})
        delta_y = scroll.get("deltaY", 0)

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
            result = f"{prefix}   {direction_display} {amount_display}"
        else:
            result = f"{prefix}   {direction} {amount}"
        return truncate_to_width(result, term_width)

    elif action == "toggle":
        # Details/summary toggle
        value = step.get("value", "")  # "open" or "closed"
        accessible_name = target.get("accessible_name", "") if target else ""

        # Determine display based on state
        state_display = value if value else "toggle"
        arrow = "▼" if value == "open" else ("▶" if value == "closed" else "◆")

        if use_color:
            arrow_display = click.style(arrow, fg="cyan", bold=True)
            state_styled = click.style(f"({state_display})", fg="bright_black")
            if accessible_name:
                name_display = click.style(f'"{truncate_text(accessible_name, 30)}"', fg="white")
                result = f"{prefix}   {arrow_display} {name_display} {state_styled}"
            else:
                result = f"{prefix}   {arrow_display} {state_styled}"
        else:
            if accessible_name:
                result = (
                    f'{prefix}   {arrow} "{truncate_text(accessible_name, 30)}" ({state_display})'
                )
            else:
                result = f"{prefix}   {arrow} ({state_display})"
        return truncate_to_width(result, term_width)

    elif action == "dialog":
        # Dialog open/close
        value = step.get("value", "")  # "modal", "modeless", or "close"
        selector = target.get("selector", "") if target else ""

        # Determine display based on state
        if value == "modal":
            state_display = "open modal"
            symbol = "◈"
        elif value == "modeless":
            state_display = "open"
            symbol = "◇"
        elif value == "close":
            state_display = "close"
            symbol = "◆"
        else:
            state_display = value or "dialog"
            symbol = "◇"

        if use_color:
            symbol_display = click.style(symbol, fg="magenta", bold=True)
            sel_display = click.style(format_selector_display(selector, 30), fg="white")
            state_styled = click.style(f"({state_display})", fg="bright_black")
            result = f"{prefix}   {symbol_display} {sel_display} {state_styled}"
        else:
            result = (
                f"{prefix}   {symbol} {format_selector_display(selector, 30)} ({state_display})"
            )
        return truncate_to_width(result, term_width)

    elif action == "jsdialog":
        # JavaScript dialog (alert, confirm, prompt)
        dialog_type = step.get("dialog_type", "alert")
        message = step.get("message", "")
        result_val = step.get("result")

        # Determine result display based on dialog type
        if dialog_type == "alert":
            result_display = ""
        elif dialog_type == "confirm":
            result_display = "OK" if result_val else "Cancel"
        elif dialog_type == "prompt":
            if result_val is None:
                result_display = "Cancel"
            else:
                result_display = f'"{truncate_text(str(result_val), 20)}"'
        else:
            result_display = str(result_val) if result_val is not None else ""

        # Truncate message for display
        msg_display = truncate_text(message, 30) if message else ""

        if use_color:
            type_styled = click.style(f"[{dialog_type}]", fg="yellow", bold=True)
            msg_styled = click.style(f'"{msg_display}"', fg="white") if msg_display else ""
            if result_display:
                result_styled = click.style(f"→ {result_display}", fg="cyan")
                result = f"{prefix}   {type_styled} {msg_styled} {result_styled}"
            else:
                result = f"{prefix}   {type_styled} {msg_styled}"
        else:
            if result_display:
                result = f'{prefix}   [{dialog_type}] "{msg_display}" → {result_display}'
            else:
                result = f'{prefix}   [{dialog_type}] "{msg_display}"'
        return truncate_to_width(result, term_width)

    elif action == "upload":
        # File upload action
        files = step.get("files", [])
        selector = target.get("selector", "") if target else ""

        if len(files) == 0:
            file_desc = "(no files)"
        elif len(files) == 1:
            file_info = files[0]
            file_name = file_info.get("name", "unknown")
            file_size = file_info.get("size", 0)
            size_str = format_filesize(file_size)
            file_desc = f'"{truncate_text(file_name, 25)}" ({size_str})'
        else:
            total_size = sum(f.get("size", 0) for f in files)
            size_str = format_filesize(total_size)
            file_desc = f"{len(files)} files ({size_str} total)"

        if use_color:
            sel_display = click.style(format_selector_display(selector, 20), fg="white")
            file_display = click.style(file_desc, fg="bright_black")
            result = f"{prefix}   {sel_display} {file_display}"
        else:
            result = f"{prefix}   {format_selector_display(selector, 20)} {file_desc}"
        return truncate_to_width(result, term_width)

    elif action == "download":
        # File download action
        download = step.get("download", {})
        filename = download.get("filename", "unknown")
        file_size = download.get("size", 0)
        mime_type = download.get("mime_type", "")

        size_str = format_filesize(file_size)
        file_desc = f'"{truncate_text(filename, 25)}" ({size_str})'

        if use_color:
            file_display = click.style(file_desc, fg="cyan")
            mime_display = click.style(f"[{mime_type}]", fg="bright_black") if mime_type else ""
            result = f"{prefix}   {file_display} {mime_display}"
        else:
            mime_suffix = f" [{mime_type}]" if mime_type else ""
            result = f"{prefix}   {file_desc}{mime_suffix}"
        return truncate_to_width(result, term_width)

    elif action == "inspekt":
        cmd = step.get("command", "")
        cmd_display = click.style(cmd, fg="cyan") if use_color else cmd
        result = f"{prefix}   {cmd_display}"
        return truncate_to_width(result, term_width)

    result = f"{prefix}   {json.dumps(step)[:40]}"
    return truncate_to_width(result, term_width)


def format_skipped_step_for_display(
    step: dict,
    step_num: int = 0,
    elapsed_ms: int = 0,
    use_color: bool = True,
    indent: bool = False,
    show_milliseconds: bool = True,
) -> str:
    """Format a skipped step for terminal display with dimmed style.

    Format: 0003   00:02.000   󰓓  skip       "Accept" button (skipped)

    Args:
        step: Step dictionary with action, target, etc.
        step_num: Step number (displayed with leading zeros)
        elapsed_ms: Elapsed time in milliseconds
        use_color: Whether to use ANSI colors
        indent: Whether to include 2-space indent
        show_milliseconds: Whether to show milliseconds in timestamp (default: True)

    Returns:
        Formatted string in dimmed style indicating the step was skipped
    """
    action = step.get("action", "unknown")
    target = step.get("target", {})
    accessible_name = target.get("accessible_name", "") if target else ""
    tag = target.get("tag", "") if target else ""

    # Sanitize accessible_name
    if accessible_name:
        accessible_name = strip_icon_font_chars(accessible_name)
        accessible_name = " ".join(accessible_name.split())

    # Get terminal width
    term_width = get_terminal_width()

    # Format components
    step_num_str = f"{step_num:04d}"
    # For skipped steps, get plain elapsed (no color) since we apply dimming to entire line
    elapsed = format_elapsed(elapsed_ms, show_milliseconds=show_milliseconds, use_color=False)

    # Get skip icon
    skip_icon = get_step_mode_icon("skip") if use_color else None

    if use_color:
        # Everything dimmed for skipped steps
        step_num_colored = click.style(step_num_str, fg="bright_black")
        elapsed_colored = click.style(elapsed, fg="bright_black")

        # Show skip icon and "skip" as action
        if skip_icon:
            action_display = f"{skip_icon}  {'skip'.ljust(9)}"
        else:
            action_display = f"   {'skip'.ljust(9)}"
        action_colored = click.style(action_display, fg="bright_black")
    else:
        step_num_colored = step_num_str
        elapsed_colored = elapsed
        action_colored = "skip".ljust(9)

    # Build prefix
    indent_str = "  " if indent else ""
    prefix = f"{indent_str}{step_num_colored}   {elapsed_colored}   {action_colored}"

    # Build details based on action type
    if action == "navigate":
        url = step.get("url", "")
        details = url[:40] + "…" if len(url) > 40 else url
    elif action in ("click", "rightclick", "activate", "hover", "check", "uncheck"):
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        tag_suffix = f" ({tag})" if tag else ""
        details = (
            f'"{name}"{tag_suffix}' if name else step.get("target", {}).get("selector", "")[:35]
        )
    elif action == "type":
        char_count = len(step.get("value", ""))
        details = f"({char_count} chars)"
    elif action == "set":
        value = step.get("value", "")
        details = f"({value})"
    elif action == "keypress":
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])
        details = "+".join([*modifiers, key]) if modifiers else key
    elif action == "select":
        option_text = step.get("option_text", "") or step.get("value", "")
        details = f'"{option_text}"' if option_text else ""
    elif action == "scroll":
        scroll = step.get("scroll", {})
        delta_y = scroll.get("deltaY", 0)
        direction = "↓" if delta_y > 0 else ("↑" if delta_y < 0 else "→")
        pixels = abs(delta_y) if delta_y != 0 else abs(scroll.get("deltaX", 0))
        details = f"{direction} {pixels}px"
    elif action == "inspekt":
        details = step.get("command", "")
    else:
        details = ""

    # Add (skipped) suffix
    if use_color:
        details_display = click.style(details, fg="bright_black")
        suffix = click.style(" (skipped)", fg="bright_black", italic=True)
    else:
        details_display = details
        suffix = " (skipped)"

    result = f"{prefix}   {details_display}{suffix}"
    return truncate_to_width(result, term_width)


def format_paused_step_for_display(
    step: dict,
    step_num: int = 0,
    elapsed_ms: int = 0,
    use_color: bool = True,
    indent: bool = False,
    show_milliseconds: bool = True,
) -> str:
    """Format a paused step indicator for terminal display.

    Format: 0003   00:02.000   ⏸  pause      "Submit" button

    Args:
        step: Step dictionary with action, target, etc.
        step_num: Step number (displayed with leading zeros)
        elapsed_ms: Elapsed time in milliseconds
        use_color: Whether to use ANSI colors
        indent: Whether to include 2-space indent
        show_milliseconds: Whether to show milliseconds in timestamp (default: True)

    Returns:
        Formatted string showing the step is paused (before execution)
    """
    action = step.get("action", "unknown")
    target = step.get("target", {})
    accessible_name = target.get("accessible_name", "") if target else ""
    tag = target.get("tag", "") if target else ""

    # Sanitize accessible_name
    if accessible_name:
        accessible_name = strip_icon_font_chars(accessible_name)
        accessible_name = " ".join(accessible_name.split())

    # Get terminal width
    term_width = get_terminal_width()

    # Format components
    step_num_str = f"{step_num:04d}"
    # For paused steps, get plain elapsed (no color) since we apply custom styling
    elapsed = format_elapsed(elapsed_ms, show_milliseconds=show_milliseconds, use_color=False)

    # Get pause icon
    pause_icon = get_step_mode_icon("pause") if use_color else None

    if use_color:
        # Yellow-ish color for paused steps
        step_num_colored = click.style(step_num_str, fg="yellow")
        elapsed_colored = click.style(elapsed, fg="bright_black")

        # Show pause icon and "pause" as action
        if pause_icon:
            action_display = f"{pause_icon}  {'pause'.ljust(9)}"
        else:
            action_display = f"   {'pause'.ljust(9)}"
        action_colored = click.style(action_display, fg="yellow")
    else:
        step_num_colored = step_num_str
        elapsed_colored = elapsed
        action_colored = "pause".ljust(9)

    # Build prefix
    indent_str = "  " if indent else ""
    prefix = f"{indent_str}{step_num_colored}   {elapsed_colored}   {action_colored}"

    # Build details based on action type
    if action == "navigate":
        url = step.get("url", "")
        details = url[:40] + "…" if len(url) > 40 else url
    elif action in ("click", "rightclick", "activate", "hover", "check", "uncheck"):
        name = accessible_name or sanitize_display_name(target.get("text", "") if target else "")
        tag_suffix = f" ({tag})" if tag else ""
        details = (
            f'"{name}"{tag_suffix}' if name else step.get("target", {}).get("selector", "")[:35]
        )
    elif action == "type":
        char_count = len(step.get("value", ""))
        details = f"({char_count} chars)"
    elif action == "set":
        value = step.get("value", "")
        details = f"({value})"
    elif action == "keypress":
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])
        details = "+".join([*modifiers, key]) if modifiers else key
    elif action == "select":
        option_text = step.get("option_text", "") or step.get("value", "")
        details = f'"{option_text}"' if option_text else ""
    elif action == "scroll":
        scroll = step.get("scroll", {})
        delta_y = scroll.get("deltaY", 0)
        direction = "↓" if delta_y > 0 else ("↑" if delta_y < 0 else "→")
        pixels = abs(delta_y) if delta_y != 0 else abs(scroll.get("deltaX", 0))
        details = f"{direction} {pixels}px"
    elif action == "inspekt":
        details = step.get("command", "")
    else:
        details = ""

    if use_color:
        details_display = click.style(details, fg="yellow")
    else:
        details_display = details

    result = f"{prefix}   {details_display}"
    return truncate_to_width(result, term_width)


def format_system_message(
    message: str,
    use_color: bool = True,
    icon: str | None = None,
    elapsed_ms: int | None = None,
    truncate: bool = True,
    show_milliseconds: bool = True,
) -> str:
    """Format a system message with ----   xx:xx[.xxx] prefix to align with step output.

    Aligns with COMMAND column (3 spaces after time, then icon or placeholder, then message).

    Args:
        message: The message text to display
        use_color: Whether to use ANSI colors
        icon: Optional icon to display (e.g., "video" for video recording)
        elapsed_ms: Optional elapsed time in milliseconds (shows actual time instead of --:--)
        truncate: Whether to truncate long messages to terminal width (default True).
                  Set to False for important messages like file paths that shouldn't be cut off.
        show_milliseconds: Whether to show milliseconds in timestamps (default: True)
    """
    from inspekt.app.cli.icons import get_indicator

    term_width = get_terminal_width()

    # Format time: either actual elapsed or placeholder
    if elapsed_ms is not None:
        time_str = format_elapsed(
            elapsed_ms, show_milliseconds=show_milliseconds, use_color=use_color
        )
    else:
        # Placeholder: --:-- or --:--.--- depending on milliseconds setting
        time_str = "--:--.---" if show_milliseconds else "--:--"
        if use_color and show_milliseconds:
            # Style the .--- part in dark gray to match format_elapsed styling
            time_str = "--:--" + click.style(".---", fg="bright_black")

    prefix = (
        click.style(f"----   {time_str}", fg="bright_black") if use_color else f"----   {time_str}"
    )
    msg = click.style(message, fg="bright_black", italic=True) if use_color else message

    # Get icon if specified
    icon_str = ""
    if icon:
        icon_glyph = get_indicator(icon)
        if icon_glyph:
            icon_str = f"{icon_glyph}  "  # icon + 2 spaces after (like other actions)

    # Format: prefix + 3 spaces (separator) + icon/indent + message
    if icon_str:
        result = f"{prefix}   {icon_str}{msg}"  # 3 spaces before icon
    else:
        result = f"{prefix}    {msg}"  # 4 spaces when no icon (3 + 1 indent)

    if truncate:
        return truncate_to_width(result, term_width)
    return result


def format_status(status: str, use_color: bool = True, suffix: str = "") -> str:
    """Format a status indicator (OK, FAIL, SKIP, MERGED) with appropriate color and icon.

    Args:
        status: The status string (OK, FAIL, SKIP, MERGED)
        use_color: Whether to use ANSI colors
        suffix: Optional suffix to append (e.g., "(CDP)" for real key dispatch)
    """
    suffix_str = f" {suffix}" if suffix else ""

    if not use_color:
        return f" {status}{suffix_str}"

    status_colors = {
        "OK": "green",
        "FAIL": "red",
        "SKIP": "yellow",
        "MERGED": "yellow",
    }
    color = status_colors.get(status, "white")

    # Get status icon if nerdfont enabled
    status_icon = None
    if status == "OK":
        status_icon = get_status_icon("pass")
    elif status == "FAIL":
        status_icon = get_status_icon("fail")
    elif status in ("SKIP", "MERGED"):
        status_icon = get_status_icon("skip")

    # Format suffix in dimmed style
    styled_suffix = click.style(suffix_str, fg="bright_black") if suffix_str else ""

    if status_icon:
        # For OK and FAIL, just show the icon without text
        if status == "OK":
            return " " + click.style(status_icon, fg="green") + styled_suffix
        elif status == "FAIL":
            return " " + click.style(status_icon, fg="red") + styled_suffix
        # For SKIP and MERGED, show icon + descriptive text
        elif status == "SKIP":
            return " " + click.style(f"{status_icon} Skipped", fg=color) + styled_suffix
        elif status == "MERGED":
            return " " + click.style(f"{status_icon} Merged", fg=color) + styled_suffix
        return " " + click.style(f"{status_icon} {status}", fg=color) + styled_suffix
    return " " + click.style(status, fg=color) + styled_suffix


def format_assertion_result(message: str, passed: bool, use_color: bool = True) -> str:
    """Format an assertion result aligned with the DETAILS column.

    Example output:
                                 visible: #cookie-banner 󰄬
    """
    from inspekt.app.cli.icons import ASSERTION_ICON
    from inspekt.config import is_nerdfont_enabled

    term_width = get_terminal_width()

    # Indentation to align with DETAILS column
    # Format: 2(indent) + 4(step) + 3(gap) + 5(time) + 3(gap) + 12(cmd) + 3(gap) = 32
    indent = " " * 32

    if not use_color:
        status = "OK" if passed else "FAIL"
        result = f"{indent}{message} {status}"
        return truncate_to_width(result, term_width)

    # Get light bulb icon if nerdfont enabled
    bulb = ASSERTION_ICON if is_nerdfont_enabled() else ""

    # Get pass/fail icon
    if passed:
        status_icon = get_status_icon("pass") or "✓"
        color = "green"
    else:
        status_icon = get_status_icon("fail") or "✗"
        color = "red"

    # Format: indent + light bulb + message + status icon
    bulb_styled = click.style(bulb, fg="bright_black") if bulb else ""
    message_styled = click.style(message, fg=color)
    status_styled = click.style(status_icon, fg=color)

    if bulb:
        result = f"{indent}{bulb_styled} {message_styled} {status_styled}"
    else:
        result = f"{indent}{message_styled} {status_styled}"

    return truncate_to_width(result, term_width)


def format_steps_preview(
    steps: list[dict],
    max_steps: int = 10,
    show_header: bool = True,
    show_remaining_count: bool = True,
) -> None:
    """
    Display a preview of recording steps using replay formatting.

    Used by both `inspekt record info` and `inspekt replay --dry-run`.

    Args:
        steps: List of step dictionaries from a recording
        max_steps: Maximum number of steps to display (default: 10)
        show_header: Whether to show the column header (default: True)
        show_remaining_count: Whether to show "…and X more steps" (default: True)
    """
    if show_header:
        click.echo(format_step_header())

    for i, step in enumerate(steps[:max_steps]):
        timestamp = step.get("timestamp", 0)
        display = format_step_for_display(step, i + 1, timestamp)
        click.echo(display)

    if show_remaining_count and len(steps) > max_steps:
        remaining = len(steps) - max_steps
        click.echo(f"\n  …and {remaining} more steps")
