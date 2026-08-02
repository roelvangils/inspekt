"""
Accessibility engine metadata loader.

Provides centralized access to engine metadata from engines.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

# Cache for loaded metadata
_METADATA_CACHE: dict[str, Any] | None = None


def _get_data_path() -> Path:
    """Get path to the data directory."""
    return Path(__file__).parent


def load_engine_metadata() -> dict[str, dict[str, Any]]:
    """
    Load all engine metadata from engines.json.

    Returns:
        Dict mapping engine short_name to metadata dict.
        Cached after first load.
    """
    global _METADATA_CACHE

    if _METADATA_CACHE is not None:
        return _METADATA_CACHE

    engines_path = _get_data_path() / "engines.json"

    if not engines_path.exists():
        raise FileNotFoundError(f"Engine metadata file not found: {engines_path}")

    with open(engines_path) as f:
        data = json.load(f)

    # Validate required fields
    required_fields = [
        "official_name",
        "short_name",
        "provider",
        "description",
        "official_url",
        "license",
        "wcag_support",
        "npm_package",
    ]

    for engine_id, engine_data in data.items():
        missing = [f for f in required_fields if f not in engine_data]
        if missing:
            raise ValueError(
                f"Engine '{engine_id}' missing required fields: {', '.join(missing)}"
            )

    _METADATA_CACHE = data
    return data


def get_engine_metadata(short_name: str) -> dict[str, Any]:
    """
    Get metadata for a specific engine.

    Args:
        short_name: Engine short name (axe, ace, hcs)

    Returns:
        Dict with engine metadata

    Raises:
        KeyError: If engine not found
    """
    metadata = load_engine_metadata()

    if short_name not in metadata:
        available = ", ".join(sorted(metadata.keys()))
        raise KeyError(f"Unknown engine '{short_name}'. Available: {available}")

    return metadata[short_name]


def list_engine_ids() -> list[str]:
    """
    Get list of all available engine IDs.

    Returns:
        List of engine short names in display order (as defined in engines.json)
    """
    metadata = load_engine_metadata()
    # Return all engines in the order they appear in engines.json
    return list(metadata.keys())


def get_engine_display_name(short_name: str) -> str:
    """Get the official display name for an engine."""
    return get_engine_metadata(short_name)["official_name"]


def get_engine_provider(short_name: str) -> str:
    """Get the provider/vendor for an engine."""
    return get_engine_metadata(short_name)["provider"]


def get_engine_color(short_name: str) -> str:
    """Get the CLI display color for an engine."""
    return get_engine_metadata(short_name).get("color", "white")


# Cache for loaded rule data
_RULES_CACHE: dict[str, dict] = {}


def load_engine_rules(engine_id: str) -> dict:
    """
    Load rule metadata for a specific accessibility engine.

    Args:
        engine_id: Engine short name (axe, eac, hcs, sia)

    Returns:
        Dict with 'version', 'rules' list, and metadata.
        Each rule has 'id', 'description', and optionally 'act_rule'.
    """
    global _RULES_CACHE

    if engine_id in _RULES_CACHE:
        return _RULES_CACHE[engine_id]

    rules_file = _get_data_path() / "rules" / f"{engine_id}_rules.json"

    if not rules_file.exists():
        return {"version": "unknown", "rules": []}

    with open(rules_file) as f:
        data = json.load(f)

    _RULES_CACHE[engine_id] = data
    return data


def get_rule_count(engine_id: str) -> int:
    """Get total number of rules for an engine."""
    data = load_engine_rules(engine_id)
    return len(data.get("rules", []))


def get_act_aligned_count(engine_id: str) -> int:
    """Get number of rules with ACT alignment for an engine."""
    data = load_engine_rules(engine_id)
    rules = data.get("rules", [])
    return sum(1 for r in rules if r.get("act_rule"))


# =============================================================================
# PDF Tools Data
# =============================================================================

# Cache for PDF tools data
_PDF_TOOLS_CACHE: dict[str, Any] | None = None


def load_pdf_tools() -> dict[str, dict[str, Any]]:
    """
    Load all PDF tools metadata from pdf_tools.json.

    Returns:
        Dict mapping tool_id to tool metadata.
        Cached after first load.
    """
    global _PDF_TOOLS_CACHE

    if _PDF_TOOLS_CACHE is not None:
        return _PDF_TOOLS_CACHE

    tools_path = _get_data_path() / "pdf_tools.json"

    if not tools_path.exists():
        raise FileNotFoundError(f"PDF tools data file not found: {tools_path}")

    with open(tools_path) as f:
        _PDF_TOOLS_CACHE = json.load(f)

    return _PDF_TOOLS_CACHE


def get_pdf_tool(tool_id: str) -> dict[str, Any] | None:
    """
    Get metadata for a specific PDF tool.

    Args:
        tool_id: Tool identifier (e.g., 'adobe_indesign', 'microsoft_word')

    Returns:
        Dict with tool metadata, or None if not found
    """
    tools = load_pdf_tools()
    return tools.get(tool_id)


def list_pdf_tool_ids() -> list[str]:
    """
    Get list of all known PDF tool IDs.

    Returns:
        List of tool IDs
    """
    tools = load_pdf_tools()
    return list(tools.keys())


# =============================================================================
# Google Fonts Data
# =============================================================================

# Cache: lowercase name -> original name for O(1) case-insensitive lookup
_GOOGLE_FONTS_CACHE: dict[str, str] | None = None


def load_google_fonts() -> dict[str, str]:
    """
    Load Google Fonts family names from google_fonts.json.

    Returns:
        Dict mapping lowercase font name to original-cased name.
        Cached after first load. Returns empty dict if file is missing.
    """
    global _GOOGLE_FONTS_CACHE

    if _GOOGLE_FONTS_CACHE is not None:
        return _GOOGLE_FONTS_CACHE

    fonts_path = _get_data_path() / "google_fonts.json"

    if not fonts_path.exists():
        _GOOGLE_FONTS_CACHE = {}
        return _GOOGLE_FONTS_CACHE

    with open(fonts_path) as f:
        names = json.load(f)

    _GOOGLE_FONTS_CACHE = {name.lower(): name for name in names}
    return _GOOGLE_FONTS_CACHE


__all__ = [
    # Engine metadata
    "load_engine_metadata",
    "get_engine_metadata",
    "list_engine_ids",
    "get_engine_display_name",
    "get_engine_provider",
    "get_engine_color",
    "load_engine_rules",
    "get_rule_count",
    "get_act_aligned_count",
    # PDF tools
    "load_pdf_tools",
    "get_pdf_tool",
    "list_pdf_tool_ids",
    # Google Fonts
    "load_google_fonts",
]
