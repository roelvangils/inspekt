"""
macOS virtual key codes for native keyboard simulation via AppleScript.

This module provides mappings from JavaScript key names (as used in KeySpec)
to macOS virtual key codes, used with `System Events key code` commands.

Reference: https://eastmanreference.com/complete-list-of-applescript-key-codes
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.key_parser import KeySpec

# macOS virtual key codes
# These are hardware-independent key codes used by System Events
MACOS_KEY_CODES: dict[str, int] = {
    # Navigation
    "Tab": 48,
    "Enter": 36,
    "Return": 36,
    " ": 49,  # Space (KeySpec.key is " " for space)
    "Space": 49,
    "Escape": 53,
    "Backspace": 51,
    "Delete": 117,  # Forward delete
    # Arrow keys
    "ArrowUp": 126,
    "ArrowDown": 125,
    "ArrowLeft": 123,
    "ArrowRight": 124,
    # Page navigation
    "Home": 115,
    "End": 119,
    "PageUp": 116,
    "PageDown": 121,
    "Insert": 114,  # Help key on Mac, closest equivalent
    # Function keys
    "F1": 122,
    "F2": 120,
    "F3": 99,
    "F4": 118,
    "F5": 96,
    "F6": 97,
    "F7": 98,
    "F8": 100,
    "F9": 101,
    "F10": 109,
    "F11": 103,
    "F12": 111,
    # Additional common keys
    "CapsLock": 57,
}

# Letter key codes (a-z)
# These follow a specific pattern on macOS
LETTER_KEY_CODES: dict[str, int] = {
    "a": 0,
    "b": 11,
    "c": 8,
    "d": 2,
    "e": 14,
    "f": 3,
    "g": 5,
    "h": 4,
    "i": 34,
    "j": 38,
    "k": 40,
    "l": 37,
    "m": 46,
    "n": 45,
    "o": 31,
    "p": 35,
    "q": 12,
    "r": 15,
    "s": 1,
    "t": 17,
    "u": 32,
    "v": 9,
    "w": 13,
    "x": 7,
    "y": 16,
    "z": 6,
}

# Number key codes (0-9, top row)
NUMBER_KEY_CODES: dict[str, int] = {
    "0": 29,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "5": 23,
    "6": 22,
    "7": 26,
    "8": 28,
    "9": 25,
}


def get_key_code(key: str) -> int | None:
    """
    Get the macOS virtual key code for a key.

    Args:
        key: The JavaScript KeyboardEvent.key value (e.g., "Tab", "a", "Enter")

    Returns:
        The macOS virtual key code, or None if the key should use keystroke instead
    """
    # Check special keys first
    if key in MACOS_KEY_CODES:
        return MACOS_KEY_CODES[key]

    # Check single lowercase letter
    if len(key) == 1 and key.lower() in LETTER_KEY_CODES:
        return LETTER_KEY_CODES[key.lower()]

    # Check single digit
    if len(key) == 1 and key in NUMBER_KEY_CODES:
        return NUMBER_KEY_CODES[key]

    # Unknown key - will need to use keystroke for printable chars
    return None


def keyspec_to_applescript(spec: "KeySpec") -> str:
    """
    Convert a KeySpec to an AppleScript command for System Events.

    Args:
        spec: The KeySpec object containing key and modifier information

    Returns:
        AppleScript command string (without the "tell application" wrapper)

    Raises:
        ValueError: If the key cannot be converted to AppleScript

    Examples:
        >>> keyspec_to_applescript(KeySpec(type='key', key='Tab', code='Tab'))
        'key code 48'

        >>> keyspec_to_applescript(KeySpec(type='key', key='a', code='KeyA', meta=True))
        'key code 0 using {command down}'

        >>> keyspec_to_applescript(KeySpec(type='key', key='Tab', code='Tab', shift=True, meta=True))
        'key code 48 using {shift down, command down}'
    """
    if spec.type == "wait":
        raise ValueError("Cannot convert wait spec to AppleScript key command")

    if spec.key is None:
        raise ValueError("KeySpec.key cannot be None")

    # Build modifier list
    modifiers: list[str] = []
    if spec.ctrl:
        modifiers.append("control down")
    if spec.alt:
        modifiers.append("option down")
    if spec.shift:
        modifiers.append("shift down")
    if spec.meta:
        modifiers.append("command down")

    # Get key code if available
    key_code = get_key_code(spec.key)

    if key_code is not None:
        # Use key code
        if modifiers:
            modifier_str = ", ".join(modifiers)
            return f"key code {key_code} using {{{modifier_str}}}"
        return f"key code {key_code}"
    else:
        # Use keystroke for printable characters
        # Note: keystroke handles shift internally for uppercase
        escaped_key = spec.key.replace("\\", "\\\\").replace('"', '\\"')

        if modifiers:
            modifier_str = ", ".join(modifiers)
            return f'keystroke "{escaped_key}" using {{{modifier_str}}}'
        return f'keystroke "{escaped_key}"'


def is_native_key_supported(key: str) -> bool:
    """
    Check if a key can be sent natively via AppleScript.

    All printable characters can be sent via keystroke, and special keys
    can be sent via key code. This function always returns True, but
    is provided for API consistency.

    Args:
        key: The JavaScript KeyboardEvent.key value

    Returns:
        True (all keys are supported via either key code or keystroke)
    """
    return True
