"""
Key specification parser for the `inspekt press` command.

Parses key specifications like:
- Simple keys: Tab, Enter, Escape, Space
- Modifier combos: Ctrl+A, Cmd+C, Shift+Tab
- Wait tokens: Wait (0.5s default), Wait(3) for custom delay

All key names are case-insensitive.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# Mapping of lowercase key names to (key, code) tuples
# The 'key' is what JavaScript's KeyboardEvent.key should be
# The 'code' is what JavaScript's KeyboardEvent.code should be
SPECIAL_KEYS: dict[str, tuple[str, str]] = {
    # Navigation
    "tab": ("Tab", "Tab"),
    "enter": ("Enter", "Enter"),
    "return": ("Enter", "Enter"),
    "escape": ("Escape", "Escape"),
    "esc": ("Escape", "Escape"),
    "space": (" ", "Space"),
    "backspace": ("Backspace", "Backspace"),
    "delete": ("Delete", "Delete"),
    "del": ("Delete", "Delete"),
    # Arrow keys
    "arrowup": ("ArrowUp", "ArrowUp"),
    "arrowdown": ("ArrowDown", "ArrowDown"),
    "arrowleft": ("ArrowLeft", "ArrowLeft"),
    "arrowright": ("ArrowRight", "ArrowRight"),
    "up": ("ArrowUp", "ArrowUp"),
    "down": ("ArrowDown", "ArrowDown"),
    "left": ("ArrowLeft", "ArrowLeft"),
    "right": ("ArrowRight", "ArrowRight"),
    # Page navigation
    "home": ("Home", "Home"),
    "end": ("End", "End"),
    "pageup": ("PageUp", "PageUp"),
    "pagedown": ("PageDown", "PageDown"),
    "pgup": ("PageUp", "PageUp"),
    "pgdown": ("PageDown", "PageDown"),
    "insert": ("Insert", "Insert"),
    "ins": ("Insert", "Insert"),
    # Function keys
    **{f"f{i}": (f"F{i}", f"F{i}") for i in range(1, 13)},
}

# Modifier key names (lowercase)
MODIFIER_KEYS = frozenset({
    "ctrl",
    "control",
    "alt",
    "option",  # macOS alt
    "shift",
    "meta",
    "cmd",
    "command",
    "win",
    "windows",
    "super",
})

# Maximum wait duration in seconds
MAX_WAIT_SECONDS = 60.0

# Default wait duration in seconds
DEFAULT_WAIT_SECONDS = 0.5

# Regex for Wait token: Wait or Wait(number)
WAIT_PATTERN = re.compile(r"^wait(?:\(([0-9]*\.?[0-9]+)\))?$", re.IGNORECASE)

# Regex for repeat syntax: Key*N (e.g., Tab*3, Shift+Tab*5)
REPEAT_PATTERN = re.compile(r"^(.+)\*(\d+)$")

# Maximum repeat count
MAX_REPEAT_COUNT = 100


@dataclass
class KeySpec:
    """
    Parsed key specification.

    For type="key":
        - key: The JavaScript KeyboardEvent.key value (e.g., "Tab", "a", "Enter")
        - code: The JavaScript KeyboardEvent.code value (e.g., "Tab", "KeyA", "Enter")
        - ctrl/alt/shift/meta: Modifier key states

    For type="wait":
        - wait_seconds: Duration to wait in seconds
    """

    type: Literal["key", "wait"]
    key: str | None = None
    code: str | None = None
    ctrl: bool = False
    alt: bool = False
    shift: bool = False
    meta: bool = False
    wait_seconds: float | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "type": self.type,
            "key": self.key,
            "code": self.code,
            "ctrl": self.ctrl,
            "alt": self.alt,
            "shift": self.shift,
            "meta": self.meta,
            "wait_seconds": self.wait_seconds,
        }


def parse_key_spec(spec: str) -> KeySpec:
    """
    Parse a single key specification.

    Args:
        spec: Key specification string (e.g., "Tab", "Ctrl+A", "Wait(5)")

    Returns:
        KeySpec object with parsed key data

    Raises:
        ValueError: If spec is invalid, key is unknown, or wait exceeds max

    Examples:
        >>> parse_key_spec("Tab")
        KeySpec(type='key', key='Tab', code='Tab', ...)

        >>> parse_key_spec("Ctrl+A")
        KeySpec(type='key', key='a', code='KeyA', ctrl=True, ...)

        >>> parse_key_spec("Wait")
        KeySpec(type='wait', wait_seconds=0.5)

        >>> parse_key_spec("Wait(3)")
        KeySpec(type='wait', wait_seconds=3.0)
    """
    spec = spec.strip()
    if not spec:
        raise ValueError("Empty key specification")

    # Check for Wait token
    wait_match = WAIT_PATTERN.match(spec)
    if wait_match:
        duration_str = wait_match.group(1)
        if duration_str:
            wait_seconds = float(duration_str)
        else:
            wait_seconds = DEFAULT_WAIT_SECONDS

        if wait_seconds > MAX_WAIT_SECONDS:
            raise ValueError(
                f"Wait duration {wait_seconds}s exceeds maximum of {MAX_WAIT_SECONDS} seconds"
            )
        if wait_seconds < 0:
            raise ValueError("Wait duration cannot be negative")

        return KeySpec(type="wait", wait_seconds=wait_seconds)

    # Parse modifier+key combinations (e.g., "Ctrl+A", "Shift+Tab")
    parts = spec.split("+")
    modifiers = {"ctrl": False, "alt": False, "shift": False, "meta": False}
    key_part = None

    for part in parts:
        part_lower = part.lower().strip()
        if not part_lower:
            continue

        if part_lower in MODIFIER_KEYS:
            # Map modifier aliases to standard names
            if part_lower in ("ctrl", "control"):
                modifiers["ctrl"] = True
            elif part_lower in ("alt", "option"):
                modifiers["alt"] = True
            elif part_lower == "shift":
                modifiers["shift"] = True
            elif part_lower in ("meta", "cmd", "command", "win", "windows", "super"):
                modifiers["meta"] = True
        else:
            # This is the actual key
            if key_part is not None:
                raise ValueError(
                    f"Multiple non-modifier keys in specification: '{spec}'"
                )
            key_part = part

    if key_part is None:
        raise ValueError(f"No key specified in: '{spec}'")

    # Resolve the key
    key_lower = key_part.lower()

    if key_lower in SPECIAL_KEYS:
        key, code = SPECIAL_KEYS[key_lower]
    elif len(key_part) == 1:
        # Single character - use as-is for key, compute code
        char = key_part.lower()  # KeyboardEvent.key is lowercase for letters
        if char.isalpha():
            key = char
            code = f"Key{char.upper()}"
        elif char.isdigit():
            key = char
            code = f"Digit{char}"
        else:
            # Punctuation/symbols
            key = key_part
            code = ""  # Code varies by keyboard layout
    else:
        # Unknown key
        suggestions = _get_key_suggestions(key_lower)
        suggestion_text = ""
        if suggestions:
            suggestion_text = f" Did you mean: {', '.join(suggestions)}?"
        raise ValueError(f"Unknown key: '{key_part}'.{suggestion_text}")

    return KeySpec(
        type="key",
        key=key,
        code=code,
        ctrl=modifiers["ctrl"],
        alt=modifiers["alt"],
        shift=modifiers["shift"],
        meta=modifiers["meta"],
    )


def expand_repeats(spec: str) -> list[str]:
    """
    Expand repeat syntax like Tab*3 to [Tab, Tab, Tab].

    Args:
        spec: Key specification string, possibly with repeat syntax

    Returns:
        List of expanded key specs (single element if no repeat)

    Raises:
        ValueError: If repeat count is invalid (0, negative, or > 100)

    Examples:
        >>> expand_repeats("Tab")
        ['Tab']

        >>> expand_repeats("Tab*3")
        ['Tab', 'Tab', 'Tab']

        >>> expand_repeats("Shift+Tab*2")
        ['Shift+Tab', 'Shift+Tab']
    """
    match = REPEAT_PATTERN.match(spec)
    if match:
        key_part, count_str = match.groups()
        count = int(count_str)

        if count < 1:
            raise ValueError(f"Repeat count must be at least 1, got {count}")
        if count > MAX_REPEAT_COUNT:
            raise ValueError(
                f"Repeat count {count} exceeds maximum of {MAX_REPEAT_COUNT}"
            )

        return [key_part] * count

    return [spec]


def parse_key_sequence(specs: list[str]) -> list[KeySpec]:
    """
    Parse a sequence of key specifications, expanding repeats first.

    Args:
        specs: List of key specification strings (may include repeat syntax)

    Returns:
        List of KeySpec objects

    Raises:
        ValueError: If any spec is invalid

    Examples:
        >>> parse_key_sequence(["Tab", "Wait", "Tab", "Enter"])
        [KeySpec(type='key', key='Tab', ...), KeySpec(type='wait', ...), ...]

        >>> parse_key_sequence(["Tab*3", "Enter"])
        [KeySpec(...), KeySpec(...), KeySpec(...), KeySpec(...)]  # 4 items
    """
    # First, expand any repeat syntax
    expanded = []
    for i, spec in enumerate(specs):
        try:
            expanded.extend(expand_repeats(spec))
        except ValueError as e:
            raise ValueError(f"Invalid key at position {i + 1}: {e}") from e

    # Then parse each expanded spec
    result = []
    for i, spec in enumerate(expanded):
        try:
            result.append(parse_key_spec(spec))
        except ValueError as e:
            raise ValueError(f"Invalid key at position {i + 1}: {e}") from e
    return result


def _get_key_suggestions(unknown_key: str, max_suggestions: int = 3) -> list[str]:
    """
    Get suggestions for an unknown key name using simple string matching.

    Args:
        unknown_key: The unknown key name (lowercase)
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of suggested key names
    """
    all_keys = list(SPECIAL_KEYS.keys())
    suggestions = []

    # First, try prefix matching
    for key in all_keys:
        if key.startswith(unknown_key) or unknown_key.startswith(key):
            suggestions.append(key)

    # Then try substring matching
    if len(suggestions) < max_suggestions:
        for key in all_keys:
            if unknown_key in key or key in unknown_key:
                if key not in suggestions:
                    suggestions.append(key)

    # Limit and format
    suggestions = suggestions[:max_suggestions]
    # Return with proper capitalization
    return [SPECIAL_KEYS[s][0] for s in suggestions]


def get_supported_keys() -> dict[str, list[str]]:
    """
    Get a dictionary of all supported keys organized by category.

    Returns:
        Dictionary with categories as keys and lists of key names as values
    """
    return {
        "Navigation": ["Tab", "Enter", "Escape", "Space", "Backspace", "Delete"],
        "Arrows": ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"],
        "Page": ["Home", "End", "PageUp", "PageDown"],
        "Function": [f"F{i}" for i in range(1, 13)],
        "Modifiers": ["Ctrl", "Alt", "Shift", "Meta/Cmd"],
    }
