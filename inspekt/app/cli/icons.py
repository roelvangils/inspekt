"""
Nerdfont icon registry for CLI output enhancement.

This module provides Nerdfont glyph mappings for various categories and status
indicators. Icons are only used when the `nerdfont` config option is enabled.

Icons are sourced from Nerd Fonts: https://www.nerdfonts.com/cheat-sheet
"""

from __future__ import annotations

# Category icons - maps table/section names to Nerdfont glyphs
CATEGORY_ICONS: dict[str, str] = {
    # Info command tables
    "Summary": "\U000f02fd",           # 󰋽 nf-md-information_outline
    "Browser/Device": "\uf108",        #  nf-fa-desktop
    "Performance": "\uf0e4",           #  nf-fa-tachometer
    "Meta": "\U000f0dd0",              # 󰷐 nf-md-tag_outline
    "SEO": "\U000f0208",               # 󰈈 nf-md-search_web
    "Security": "\uf023",              #  nf-fa-lock
    "Accessibility": "\uf29a",         #  nf-fa-universal_access
    "Resources": "\U000f0214",         # 󰈔 nf-md-file_multiple_outline
    "Storage": "\U000f01bc",           # 󰆼 nf-md-database_outline
    "Tech": "\uf121",                  #  nf-fa-code
    "Domain": "\U000f059f",            # 󰖟 nf-md-web
    "Layout": "\U000f05f0",            # 󰗰 nf-md-view_dashboard_outline
    # Other common categories
    "Network": "\U000f0200",           # 󰈀 nf-md-ethernet
    "Console": "\uf120",               #  nf-fa-terminal
    "Cookies": "\U000f0198",           # 󰆘 nf-md-cookie_outline
    "Links": "\uf0c1",                 #  nf-fa-link
    "Headings": "\U000f02ab",          # 󰊫 nf-md-format_header_pound
    "Headers": "\uf0fd",               #  nf-fa-header
    "Scripts": "\uf121",               #  nf-fa-code (same as Tech)
    "Stylesheets": "\ue749",           #  nf-dev-css3
    "Images": "\uf03e",                #  nf-fa-image
    "Fonts": "\uf031",                 #  nf-fa-font
    "Media": "\uf008",                 #  nf-fa-film
    "Errors": "\uf06a",                #  nf-fa-exclamation_circle
    "Warnings": "\uf071",              #  nf-fa-warning
    # Additional table titles
    "Violations": "\uf06a",            #  nf-fa-exclamation_circle
    "Requests": "\U000f0200",          # 󰈀 nf-md-ethernet
    "Domains": "\U000f059f",           # 󰖟 nf-md-web
    "Robots": "\U000f06a9",            # 󰚩 nf-md-robot
    "Sitemaps": "\U000f0219",          # 󰈙 nf-md-file_tree
    "Recordings": "\uf111",            #  nf-fa-circle (record dot)
    "Validation": "\uf058",            #  nf-fa-check_circle
    "Form": "\uf0ca",                  #  nf-fa-list_ul
    "User-agent": "\U000f06a9",        # 󰚩 nf-md-robot
    "Plugins": "\U000f0a66",           # 󰩦 nf-md-puzzle
}

# Status icons - Nerdfont equivalents for ✓/✗/○/•
STATUS_ICONS: dict[str, str] = {
    "pass": "\U000f012c",              # 󰄬 nf-md-check
    "fail": "\U000f0156",              # 󰅖 nf-md-close (simple cross)
    "warning": "\uf071",               #  nf-fa-warning
    "unknown": "\uf059",               #  nf-fa-question_circle
    "info": "\uf05a",                  #  nf-fa-info_circle
    "progress": "\uf141",              #  nf-fa-ellipsis_h
}

# Special indicator icons
INDICATOR_ICONS: dict[str, str] = {
    "waiting": "\uf251",               #  nf-fa-hourglass_half
    "cached": "\U000f0193",            # 󰆓 nf-md-cached
    "ai": "\U000f06a9",                # 󰚩 nf-md-robot
    "external": "\uf08e",              #  nf-fa-external_link
    "internal": "\uf061",              #  nf-fa-arrow_right
    "bypass": "\uf0e7",                #  nf-fa-bolt
    "command": "\uf054",               #  nf-fa-chevron_right
    "resume": "\ueacf",                #  nf-cod-debug_continue (resume)
    "pause": "\uf04c",                 #  nf-fa-pause (recording paused)
    "undo": "\U000f054c",              # 󰕌 nf-md-undo (undo action)
    "redo": "\U000f044e",              # 󰑎 nf-md-redo (redo action)
    "stop": "\uf04d",                  #  nf-fa-stop (recording stopped)
    "tip": "\uf400",                   #  nf-oct-light_bulb (informational tip)
    "video": "\U000f022b",             # 󰈫 nf-md-filmstrip (video recording)
    "audio": "\U000f057e",             # 󰕾 nf-md-volume_high (audio effects)
}

# Recording action icons - used in record and replay commands
ACTION_ICONS: dict[str, str] = {
    "navigate": "\U000f059f",          # 󰖟 nf-md-web (web navigation)
    "click": "\U000f0cfd",             # 󰳽 nf-md-cursor_default_click
    "rightclick": "\U000f0cfd",        # 󰳽 nf-md-cursor_default_click (same as click)
    "activate": "\U000f0311",          # 󰌑 nf-md-keyboard_return (Enter key)
    "type": "\U000f05e7",              # 󰗧 nf-md-form_textbox
    "set": "\U000f0219",               # 󰈙 nf-md-file_document_edit (default for set)
    "keypress": "\uf11c",              #  nf-fa-keyboard_o (default for other keys)
    "hover": "\U000f0208",             # 󰈈 nf-md-eye (looking at element)
    "scroll": "\U000f0599",            # 󰖙 nf-md-unfold_more_vertical (scroll)
    "check": "\U000f0c52",             # 󰱒 nf-md-checkbox_marked_circle
    "uncheck": "\uf0c8",               #  nf-fa-square (empty square)
    "select": "\U000f1400",            # 󱐀 nf-md-form_dropdown (dropdown)
    "radio": "\U000f043e",             # 󰐾 nf-md-radiobox_marked (radio button)
    "toggle": "\U000f0142",            # 󰅂 nf-md-chevron_down (expand/collapse)
    "dialog": "\U000f05a4",            # 󰖤 nf-md-window_maximize (dialog/modal)
    "jsdialog": "\ue60c",               #  nf-seti-javascript (JS alert/confirm/prompt)
    "upload": "\U000f0552",            # 󰕒 nf-md-upload (file upload)
    "download": "\U000f01da",          # 󰇚 nf-md-download (file download)
    "inspekt": "\uf002",               #  nf-fa-search
}

# Native control set icons - used for 'set' action with different input types
NATIVE_CONTROL_ICONS: dict[str, str] = {
    "time": "\U000f0589",              # 󰖉 nf-md-clock_outline
    "date": "\U000f00ed",              # 󰃭 nf-md-calendar
    "datetime-local": "\U000f00f0",    # 󰃰 nf-md-calendar_clock
    "month": "\U000f00ed",             # 󰃭 nf-md-calendar
    "week": "\U000f00ed",              # 󰃭 nf-md-calendar
    "range": "\ue690",                 #  nf-seti-config
    "number": "\uf4f7",                #  nf-oct-number
    "color": "\U000f03d8",             # 󰏘 nf-md-palette
}

# Step mode icons - used for skip/pause modes in replay
STEP_MODE_ICONS: dict[str, str] = {
    "skip": "\U000f04d3",                 # 󰓓 nf-md-skip_next (skip forward)
    "pause": "\uf04c",                    #  nf-fa-pause (pause)
    "continue": "\U000f040a",             # 󰐊 nf-md-play (play/continue)
}

# Assertion icon - light bulb for expectations
ASSERTION_ICON: str = "\uf400"            #  nf-oct-light_bulb

# Keypress-specific icons - used for different key types
KEYPRESS_ICONS: dict[str, str] = {
    "Tab": "\U000f0312",               # 󰌒 nf-md-keyboard_tab
    "Shift+Tab": "\U000f0325",         # 󰌥 nf-md-keyboard_tab_reverse
    "Enter": "\U000f0311",             # 󰌑 nf-md-keyboard_return
    "default": "\uf11c",               #  nf-fa-keyboard_o
}

# Console log level icons
LOG_LEVEL_ICONS: dict[str, str] = {
    "error": "\uf057",                 #  nf-fa-times_circle
    "warn": "\uf071",                  #  nf-fa-warning
    "log": "\uf05a",                   #  nf-fa-info_circle
    "info": "\uf05a",                  #  nf-fa-info_circle
    "debug": "\uf188",                 #  nf-fa-bug
    "dir": "\uf07b",                   #  nf-fa-folder
    "trace": "\uf0c9",                 #  nf-fa-bars
    "group": "\uf0c9",                 #  nf-fa-bars
    "assert": "\uf06a",                #  nf-fa-exclamation_circle
    "clear": "\uf12d",                 #  nf-fa-eraser
}

# Section header icons
SECTION_ICONS: dict[str, str] = {
    "summary": "\U000f02fd",           # 󰋽 nf-md-information_outline
    "by_type": "\U000f0214",           # 󰈔 nf-md-file_multiple_outline
    "by_status": "\uf0ae",             #  nf-fa-tasks
    "slowest": "\uf017",               #  nf-fa-clock_o
    "largest": "\U000f01bc",           # 󰆼 nf-md-database_outline
    "dimensions": "\U000f05f0",        # 󰗰 nf-md-view_dashboard_outline
    "accessibility": "\uf29a",         #  nf-fa-universal_access
    "styles": "\ue749",                #  nf-dev-css3
    "missing": "\uf071",               #  nf-fa-warning
    "empty": "\uf10c",                 #  nf-fa-circle_o
    "duplicate": "\uf0c5",             #  nf-fa-copy
}


def get_icon(category: str) -> str | None:
    """
    Get the Nerdfont icon for a category.

    Args:
        category: The category name (e.g., "Summary", "Browser/Device")

    Returns:
        The Nerdfont glyph if nerdfont is enabled and category exists,
        None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None
    return CATEGORY_ICONS.get(category)


def get_status_icon(status: str | bool | None) -> str | None:
    """
    Get Nerdfont status icon.

    Args:
        status: Status value (bool, string like 'pass'/'fail', or None)

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None

    if status is True or status in ("pass", "passed", "ok", "success", "yes", "valid"):
        return STATUS_ICONS["pass"]
    elif status is False or status in ("fail", "failed", "error", "no", "invalid"):
        return STATUS_ICONS["fail"]
    elif status in ("warn", "warning"):
        return STATUS_ICONS["warning"]
    else:
        return STATUS_ICONS["unknown"]


def get_indicator(name: str) -> str | None:
    """
    Get a special indicator icon.

    Args:
        name: Indicator name (e.g., "cached", "ai", "external")

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None
    return INDICATOR_ICONS.get(name)


def get_log_level_icon(level: str) -> str | None:
    """
    Get icon for a console log level.

    Args:
        level: Log level (e.g., "error", "warn", "info", "debug")

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None
    return LOG_LEVEL_ICONS.get(level.lower())


def get_section_icon(name: str) -> str | None:
    """
    Get icon for a section header.

    Args:
        name: Section name (e.g., "summary", "by_type", "slowest")

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None
    return SECTION_ICONS.get(name.lower())


def get_action_icon(action: str) -> str | None:
    """
    Get icon for a recording action type.

    Args:
        action: Action name (e.g., "navigate", "click", "type", "hover")

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None
    return ACTION_ICONS.get(action.lower())


def get_native_control_icon(input_type: str) -> str | None:
    """
    Get icon for a native control input type.

    Args:
        input_type: The input type (e.g., "time", "date", "range", "color")

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None
    return NATIVE_CONTROL_ICONS.get(input_type.lower())


def get_keypress_icon(key: str, modifiers: list[str] | None = None) -> str | None:
    """
    Get icon for a specific keypress.

    Args:
        key: The key name (e.g., "Tab", "Enter", "Escape")
        modifiers: List of modifier keys (e.g., ["Shift"], ["Ctrl", "Alt"])

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None

    # Build the key string with modifiers
    if modifiers and "Shift" in modifiers and key == "Tab":
        return KEYPRESS_ICONS.get("Shift+Tab")

    # Check for specific key icons
    if key in KEYPRESS_ICONS:
        return KEYPRESS_ICONS.get(key)

    # Fall back to default keypress icon
    return KEYPRESS_ICONS.get("default")


def get_step_mode_icon(mode: str) -> str | None:
    """
    Get icon for a step execution mode.

    Args:
        mode: Step mode (e.g., "skip", "pause", "continue")

    Returns:
        The Nerdfont glyph if nerdfont is enabled, None otherwise
    """
    from inspekt.config import is_nerdfont_enabled

    if not is_nerdfont_enabled():
        return None
    return STEP_MODE_ICONS.get(mode.lower())


# =============================================================================
# Helper functions for status messages
# =============================================================================


def success(message: str) -> str:
    """
    Format a success message with appropriate icon.

    Args:
        message: The success message text

    Returns:
        Message prefixed with  (nerdfont) or ✓ (fallback)
    """
    from inspekt.config import is_nerdfont_enabled

    icon = STATUS_ICONS["pass"] if is_nerdfont_enabled() else "\u2713"
    return f"{icon} {message}"


def error(message: str) -> str:
    """
    Format an error message with appropriate icon.

    Args:
        message: The error message text

    Returns:
        Message prefixed with  (nerdfont) or ✗ (fallback)
    """
    from inspekt.config import is_nerdfont_enabled

    icon = STATUS_ICONS["fail"] if is_nerdfont_enabled() else "\u2717"
    return f"{icon} {message}"


def warning(message: str) -> str:
    """
    Format a warning message with appropriate icon.

    Args:
        message: The warning message text

    Returns:
        Message prefixed with  (nerdfont) or ⚠ (fallback)
    """
    from inspekt.config import is_nerdfont_enabled

    icon = STATUS_ICONS["warning"] if is_nerdfont_enabled() else "\u26a0"
    return f"{icon} {message}"


def info(message: str) -> str:
    """
    Format an info/neutral message with appropriate icon.

    Args:
        message: The info message text

    Returns:
        Message prefixed with  (nerdfont) or • (fallback)
    """
    from inspekt.config import is_nerdfont_enabled

    icon = STATUS_ICONS["info"] if is_nerdfont_enabled() else "\u2022"
    return f"{icon} {message}"


def progress(message: str) -> str:
    """
    Format a progress/in-progress message with appropriate icon.

    Args:
        message: The progress message text

    Returns:
        Message prefixed with  (nerdfont) or • (fallback)
    """
    from inspekt.config import is_nerdfont_enabled

    icon = STATUS_ICONS["progress"] if is_nerdfont_enabled() else "\u2022"
    return f"{icon} {message}"


def waiting(message: str) -> str:
    """
    Format a waiting/pending message with appropriate icon.

    Args:
        message: The waiting message text

    Returns:
        Message prefixed with  (nerdfont) or ⏳ (fallback)
    """
    from inspekt.config import is_nerdfont_enabled

    icon = INDICATOR_ICONS["waiting"] if is_nerdfont_enabled() else "\u23f3"
    return f"{icon} {message}"


def cached(message: str) -> str:
    """
    Format a cached/from-cache message with appropriate icon.

    Args:
        message: The cached message text

    Returns:
        Message prefixed with 󰆓 (nerdfont) or 💾 (fallback)
    """
    from inspekt.config import is_nerdfont_enabled

    icon = INDICATOR_ICONS["cached"] if is_nerdfont_enabled() else "\U0001f4be"
    return f"{icon} {message}"
