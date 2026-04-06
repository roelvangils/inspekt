"""Unit tests for the PDF tool matcher service."""

from __future__ import annotations

import pytest

from inspekt.services.pdf_tool_matcher import (
    PDFToolMatcher,
    ToolMatch,
    get_creator_info,
    match_pdf_tool,
)


class TestPDFToolMatcher:
    """Tests for the PDFToolMatcher class."""

    @pytest.fixture
    def matcher(self) -> PDFToolMatcher:
        """Create a matcher instance for testing."""
        return PDFToolMatcher()

    def test_exact_match_creator(self, matcher: PDFToolMatcher) -> None:
        """Test exact match on creator field."""
        result = matcher.match("Adobe InDesign", None)
        assert result is not None
        assert result.display_name == "Adobe InDesign"
        assert result.vendor == "Adobe"
        assert result.confidence >= 0.9
        assert result.accessibility_docs_url is not None

    def test_exact_match_producer(self, matcher: PDFToolMatcher) -> None:
        """Test exact match on producer field."""
        result = matcher.match(None, "Microsoft Word")
        assert result is not None
        assert result.display_name == "Microsoft Word"
        assert result.vendor == "Microsoft"

    def test_normalized_match_with_version(self, matcher: PDFToolMatcher) -> None:
        """Test matching with version numbers stripped."""
        result = matcher.match("Adobe InDesign 2024 (Macintosh)", None)
        assert result is not None
        assert result.display_name == "Adobe InDesign"
        assert result.confidence >= 0.7

    def test_contains_match(self, matcher: PDFToolMatcher) -> None:
        """Test substring/contains matching."""
        result = matcher.match("Created with InDesign CC 2022", None)
        assert result is not None
        assert result.display_name == "Adobe InDesign"
        assert 0.7 <= result.confidence <= 0.95

    def test_case_insensitive_match(self, matcher: PDFToolMatcher) -> None:
        """Test case-insensitive matching."""
        result = matcher.match("adobe indesign", None)
        assert result is not None
        assert result.display_name == "Adobe InDesign"

    def test_no_match_returns_none(self, matcher: PDFToolMatcher) -> None:
        """Test that unrecognized tools return None."""
        result = matcher.match("Unknown PDF Creator v1.0", None)
        assert result is None

    def test_both_fields_uses_best_match(self, matcher: PDFToolMatcher) -> None:
        """Test that both creator and producer are checked, best match wins."""
        # InDesign in creator should win over generic producer
        result = matcher.match("Adobe InDesign", "Some Generic Producer")
        assert result is not None
        assert result.display_name == "Adobe InDesign"

    def test_microsoft_word_variations(self, matcher: PDFToolMatcher) -> None:
        """Test various Microsoft Word creator strings."""
        variations = [
            "Microsoft Word",
            "Microsoft Office Word",
            "Word for Mac",
            "Microsoft Word 2019",
        ]
        for creator in variations:
            result = matcher.match(creator, None)
            assert result is not None, f"Failed to match: {creator}"
            assert "Word" in result.display_name or "Microsoft" in result.vendor

    def test_latex_variations(self, matcher: PDFToolMatcher) -> None:
        """Test various LaTeX producer strings."""
        variations = [
            "pdfTeX-1.40.25",
            "XeTeX",
            "LuaTeX",
            "pdfLaTeX",
        ]
        for producer in variations:
            result = matcher.match(None, producer)
            assert result is not None, f"Failed to match: {producer}"
            assert result.display_name == "LaTeX"

    def test_icon_svg_is_valid(self, matcher: PDFToolMatcher) -> None:
        """Test that returned icon SVG is valid."""
        result = matcher.match("Adobe InDesign", None)
        assert result is not None
        assert result.icon_svg.strip().startswith("<svg")
        assert "</svg>" in result.icon_svg

    def test_accessibility_docs_url_present(self, matcher: PDFToolMatcher) -> None:
        """Test that major tools have accessibility docs URLs."""
        tools_with_docs = [
            ("Adobe InDesign", None),
            ("Microsoft Word", None),
            (None, "LibreOffice"),
        ]
        for creator, producer in tools_with_docs:
            result = matcher.match(creator, producer)
            assert result is not None
            assert result.accessibility_docs_url is not None
            assert result.accessibility_docs_url.startswith("http")

    def test_list_tools(self, matcher: PDFToolMatcher) -> None:
        """Test that list_tools returns all known tools."""
        tools = matcher.list_tools()
        assert len(tools) > 20  # We have 40+ tools
        assert "adobe_indesign" in tools
        assert "microsoft_word" in tools
        assert "latex" in tools

    def test_get_tool_info(self, matcher: PDFToolMatcher) -> None:
        """Test getting full tool information by ID."""
        info = matcher.get_tool_info("adobe_indesign")
        assert info is not None
        assert info["display_name"] == "Adobe InDesign"
        assert info["vendor"] == "Adobe"
        assert "patterns" in info

    def test_get_tool_info_not_found(self, matcher: PDFToolMatcher) -> None:
        """Test that get_tool_info returns None for unknown tool."""
        info = matcher.get_tool_info("unknown_tool_xyz")
        assert info is None


class TestConvenienceFunctions:
    """Tests for the convenience functions."""

    def test_match_pdf_tool(self) -> None:
        """Test the match_pdf_tool convenience function."""
        result = match_pdf_tool("Adobe InDesign", None)
        assert result is not None
        assert result.display_name == "Adobe InDesign"

    def test_get_creator_info_with_match(self) -> None:
        """Test get_creator_info with a recognized tool."""
        icon, name, docs_url = get_creator_info("Adobe InDesign", None)
        assert "<svg" in icon
        assert name == "Adobe InDesign"
        assert docs_url is not None

    def test_get_creator_info_no_match(self) -> None:
        """Test get_creator_info with an unrecognized tool."""
        icon, name, docs_url = get_creator_info("Unknown Tool", None)
        assert "<svg" in icon  # Default icon
        assert name is None
        assert docs_url is None

    def test_get_creator_info_none_inputs(self) -> None:
        """Test get_creator_info with None inputs."""
        icon, name, docs_url = get_creator_info(None, None)
        assert "<svg" in icon  # Default icon
        assert name is None
        assert docs_url is None


class TestToolMatch:
    """Tests for the ToolMatch dataclass."""

    def test_tool_match_creation(self) -> None:
        """Test creating a ToolMatch instance."""
        match = ToolMatch(
            tool_id="adobe_indesign",
            display_name="Adobe InDesign",
            vendor="Adobe",
            confidence=1.0,
            icon_svg="<svg></svg>",
            accessibility_docs_url="https://example.com",
            matched_field="creator",
            matched_pattern="InDesign",
        )
        assert match.tool_id == "adobe_indesign"
        assert match.display_name == "Adobe InDesign"
        assert match.confidence == 1.0


class TestFuzzyMatching:
    """Tests for fuzzy matching behavior."""

    @pytest.fixture
    def matcher(self) -> PDFToolMatcher:
        """Create a matcher instance for testing."""
        return PDFToolMatcher()

    def test_fuzzy_match_typo(self, matcher: PDFToolMatcher) -> None:
        """Test fuzzy matching handles minor typos."""
        # Note: fuzzy matching requires pattern length >= 4
        result = matcher.match("Adobe InDesing", None)  # typo in InDesign
        if result:
            # If matched, confidence should be lower
            assert result.confidence < 0.95

    def test_version_stripping(self, matcher: PDFToolMatcher) -> None:
        """Test that version numbers are properly stripped."""
        result = matcher.match("Adobe InDesign 15.0.1 (Windows)", None)
        assert result is not None
        assert result.display_name == "Adobe InDesign"

    def test_platform_stripping(self, matcher: PDFToolMatcher) -> None:
        """Test that platform names are stripped."""
        result = matcher.match("Microsoft Word for Mac", None)
        assert result is not None
        assert "Word" in result.display_name


class TestCaching:
    """Tests for caching behavior."""

    def test_matcher_caches_results(self) -> None:
        """Test that the matcher caches repeated lookups."""
        matcher = PDFToolMatcher()

        # First call
        result1 = matcher.match("Adobe InDesign", None)

        # Second call with same input
        result2 = matcher.match("Adobe InDesign", None)

        # Should return cached result
        assert result1 is result2
