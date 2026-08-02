"""
PDF Tool Matcher Service.

Identifies PDF creation tools from metadata and provides display information.
Uses tiered fuzzy matching to identify tools with confidence scores.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


@dataclass
class ToolMatch:
    """Result of PDF tool matching."""

    tool_id: str
    display_name: str
    vendor: str
    confidence: float
    icon_svg: str
    accessibility_docs_url: str | None
    matched_field: str  # "creator" or "producer"
    matched_pattern: str  # The pattern that matched


# Cache for loaded tools data
_TOOLS_CACHE: dict | None = None
_ICONS_CACHE: dict[str, str] = {}


def _get_data_path() -> Path:
    """Get path to the data directory."""
    return Path(__file__).parent.parent / "data"


def _load_tools_data() -> dict:
    """Load PDF tools data from JSON file."""
    global _TOOLS_CACHE

    if _TOOLS_CACHE is not None:
        return _TOOLS_CACHE

    tools_path = _get_data_path() / "pdf_tools.json"

    if not tools_path.exists():
        raise FileNotFoundError(f"PDF tools data file not found: {tools_path}")

    with open(tools_path) as f:
        _TOOLS_CACHE = json.load(f)

    return _TOOLS_CACHE


def _load_icon(tool_id: str) -> str:
    """Load SVG icon for a tool."""
    if tool_id in _ICONS_CACHE:
        return _ICONS_CACHE[tool_id]

    icons_dir = _get_data_path() / "icons" / "pdf_tools"
    icon_path = icons_dir / f"{tool_id}.svg"

    if icon_path.exists():
        with open(icon_path) as f:
            svg = f.read().strip()
            # Adjust size to 20x20 for inline display
            svg = re.sub(r'width="24"', 'width="20"', svg)
            svg = re.sub(r'height="24"', 'height="20"', svg)
            _ICONS_CACHE[tool_id] = svg
            return svg

    # Fall back to default icon
    default_path = icons_dir / "default.svg"
    if default_path.exists():
        with open(default_path) as f:
            svg = f.read().strip()
            svg = re.sub(r'width="24"', 'width="20"', svg)
            svg = re.sub(r'height="24"', 'height="20"', svg)
            _ICONS_CACHE[tool_id] = svg
            return svg

    # Ultimate fallback - inline default SVG
    return '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#6B7280"/>
        <path d="M7 4h8l4 4v12H7V4z" fill="none" stroke="white" stroke-width="1.5"/>
        <path d="M14 4v4h4" fill="none" stroke="white" stroke-width="1.5"/>
    </svg>'''


def _normalize_string(s: str) -> str:
    """
    Normalize a string for comparison.

    - Lowercase
    - Remove version numbers (e.g., "2024", "15.0", "(19.2)")
    - Remove extra whitespace
    - Remove common suffixes
    """
    if not s:
        return ""

    result = s.lower()

    # Remove version patterns like "2024", "15.0", "(19.2)", "v2.0"
    result = re.sub(r'\b\d+(\.\d+)*\b', '', result)
    result = re.sub(r'\([\d.]+\)', '', result)
    result = re.sub(r'\bv\d+(\.\d+)*\b', '', result)

    # Remove common platform suffixes
    result = re.sub(r'\b(macintosh|mac|windows|linux|win|x64|x86)\b', '', result)

    # Remove common filler words
    result = re.sub(r'\b(version|build|release|pro|professional)\b', '', result)

    # Normalize whitespace
    result = ' '.join(result.split())

    return result.strip()


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def _similarity_score(s1: str, s2: str) -> float:
    """
    Calculate similarity score between two strings (0-1).

    Uses Levenshtein distance normalized by the length of the longer string.
    """
    if not s1 or not s2:
        return 0.0

    s1_lower = s1.lower()
    s2_lower = s2.lower()

    if s1_lower == s2_lower:
        return 1.0

    distance = _levenshtein_distance(s1_lower, s2_lower)
    max_len = max(len(s1), len(s2))

    return 1.0 - (distance / max_len)


class PDFToolMatcher:
    """
    Matches PDF creator/producer strings to known tools.

    Uses tiered matching:
    - Tier 1: Exact match (case-insensitive) → confidence 1.0
    - Tier 2: Normalized match (strip versions) → confidence 0.95
    - Tier 3: Contains match → confidence 0.7-0.9
    - Tier 4: Levenshtein fuzzy match → confidence 0.5-0.7
    """

    def __init__(self):
        """Initialize the matcher with tools data."""
        self._tools = _load_tools_data()

    @lru_cache(maxsize=256)
    def match(
        self,
        creator: str | None,
        producer: str | None,
    ) -> ToolMatch | None:
        """
        Match creator/producer metadata to a known PDF tool.

        Args:
            creator: PDF Creator metadata field
            producer: PDF Producer metadata field

        Returns:
            ToolMatch if a match is found, None otherwise
        """
        # Try matching both fields
        best_match: ToolMatch | None = None
        best_confidence = 0.0

        for field_name, field_value in [("creator", creator), ("producer", producer)]:
            if not field_value:
                continue

            match = self._match_field(field_name, field_value)
            if match and match.confidence > best_confidence:
                best_match = match
                best_confidence = match.confidence

        return best_match

    def _match_field(self, field_name: str, field_value: str) -> ToolMatch | None:
        """Match a single field against all tool patterns."""
        best_match: ToolMatch | None = None
        best_confidence = 0.0

        field_lower = field_value.lower()
        field_normalized = _normalize_string(field_value)

        for tool_id, tool_data in self._tools.items():
            patterns = tool_data.get("patterns", {}).get(field_name, [])

            for pattern in patterns:
                pattern_lower = pattern.lower()
                pattern_normalized = _normalize_string(pattern)

                # Tier 1: Exact match (case-insensitive)
                if field_lower == pattern_lower:
                    confidence = 1.0
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = self._create_match(
                            tool_id, tool_data, confidence, field_name, pattern
                        )

                # Tier 2: Normalized match
                elif field_normalized == pattern_normalized:
                    confidence = 0.95
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = self._create_match(
                            tool_id, tool_data, confidence, field_name, pattern
                        )

                # Tier 3: Contains match
                elif pattern_lower in field_lower:
                    # Score based on how much of the field is matched
                    coverage = len(pattern) / len(field_value)
                    confidence = 0.7 + (0.2 * coverage)  # 0.7 to 0.9
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = self._create_match(
                            tool_id, tool_data, confidence, field_name, pattern
                        )

                # Tier 4: Fuzzy match (only for longer patterns)
                elif len(pattern) >= 4:
                    similarity = _similarity_score(pattern_normalized, field_normalized)
                    if similarity >= 0.7:  # Threshold for fuzzy matching
                        confidence = 0.5 + (0.2 * similarity)  # 0.5 to 0.7
                        if confidence > best_confidence:
                            best_confidence = confidence
                            best_match = self._create_match(
                                tool_id, tool_data, confidence, field_name, pattern
                            )

        return best_match

    def _create_match(
        self,
        tool_id: str,
        tool_data: dict,
        confidence: float,
        matched_field: str,
        matched_pattern: str,
    ) -> ToolMatch:
        """Create a ToolMatch from tool data."""
        return ToolMatch(
            tool_id=tool_id,
            display_name=tool_data["display_name"],
            vendor=tool_data["vendor"],
            confidence=confidence,
            icon_svg=_load_icon(tool_id),
            accessibility_docs_url=tool_data.get("accessibility_docs_url"),
            matched_field=matched_field,
            matched_pattern=matched_pattern,
        )

    def get_tool_info(self, tool_id: str) -> dict | None:
        """Get full tool information by ID."""
        return self._tools.get(tool_id)

    def list_tools(self) -> list[str]:
        """List all known tool IDs."""
        return list(self._tools.keys())


# Convenience function for direct use
@lru_cache(maxsize=1)
def get_matcher() -> PDFToolMatcher:
    """Get a cached PDFToolMatcher instance."""
    return PDFToolMatcher()


def match_pdf_tool(
    creator: str | None,
    producer: str | None,
) -> ToolMatch | None:
    """
    Match PDF creator/producer to a known tool.

    This is a convenience function that uses the cached matcher.

    Args:
        creator: PDF Creator metadata
        producer: PDF Producer metadata

    Returns:
        ToolMatch if found, None otherwise
    """
    return get_matcher().match(creator, producer)


def get_creator_info(
    creator: str | None,
    producer: str | None,
) -> tuple[str, str | None, str | None]:
    """
    Get creator display info for PDF reports.

    This function provides backward compatibility with the previous
    _get_creator_icon function while adding accessibility docs URL.

    Args:
        creator: PDF Creator metadata
        producer: PDF Producer metadata

    Returns:
        Tuple of (icon_svg, tool_name, accessibility_docs_url)
    """
    match = match_pdf_tool(creator, producer)

    if match:
        return (match.icon_svg, match.display_name, match.accessibility_docs_url)

    # Return default icon if no match
    default_icon = _load_icon("default")
    return (default_icon, None, None)
