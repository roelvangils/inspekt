"""
PDF Check Message Loader Service.

Loads and formats internationalized messages for PDF accessibility reports.
Supports placeholder substitution and language fallback to English.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Cache for loaded messages
_MESSAGES_CACHE: dict | None = None


def _get_data_path() -> Path:
    """Get path to the data directory."""
    return Path(__file__).parent.parent / "data"


def _load_messages_file() -> dict:
    """Load the messages JSON file with caching."""
    global _MESSAGES_CACHE

    if _MESSAGES_CACHE is not None:
        return _MESSAGES_CACHE

    messages_path = _get_data_path() / "pdf_check_messages.json"

    if not messages_path.exists():
        raise FileNotFoundError(f"Messages file not found: {messages_path}")

    with open(messages_path, encoding="utf-8") as f:
        _MESSAGES_CACHE = json.load(f)

    return _MESSAGES_CACHE


def load_messages(lang: str = "en") -> dict:
    """
    Load messages for the specified language, falling back to English.

    Args:
        lang: Language code (e.g., "en", "fr", "nl")

    Returns:
        Dictionary of messages for the specified language
    """
    data = _load_messages_file()
    messages = data.get("messages", {})

    # Return requested language if available, otherwise fall back to English
    if lang in messages:
        return messages[lang]

    # Fall back to English
    return messages.get("en", {})


def get_message(key: str, lang: str = "en", **kwargs: Any) -> dict:
    """
    Get a specific message by key with placeholder substitution.

    Args:
        key: Message key (e.g., "no_structure_warning")
        lang: Language code (e.g., "en", "fr", "nl")
        **kwargs: Placeholder values for substitution (e.g., tool_name="Adobe InDesign")

    Returns:
        Dictionary with message fields, with placeholders replaced

    Example:
        >>> get_message("no_structure_warning", "en", tool_name="Adobe InDesign", docs_url="https://...")
        {
            "heading": "Important: This PDF isn't tagged...",
            "explanation": "...",
            "tip_with_tool": "This file originated from <strong>Adobe InDesign</strong>..."
        }
    """
    messages = load_messages(lang)
    message = messages.get(key, {})

    if not message:
        # Fall back to English if message not found in requested language
        english_messages = load_messages("en")
        message = english_messages.get(key, {})

    if not message:
        return {}

    # Apply placeholder substitution to all string fields
    result = {}
    for field_key, field_value in message.items():
        if isinstance(field_value, str):
            try:
                result[field_key] = field_value.format(**kwargs)
            except KeyError:
                # Keep original if placeholder not provided
                result[field_key] = field_value
        else:
            result[field_key] = field_value

    return result


def clear_cache() -> None:
    """Clear the messages cache (useful for testing)."""
    global _MESSAGES_CACHE
    _MESSAGES_CACHE = None
