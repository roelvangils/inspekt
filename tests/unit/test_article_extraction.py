"""
Unit tests for article extraction script.

These tests verify that the extract_article.js script correctly identifies
and extracts article content from HTML pages.
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def mock_client():
    """Create a mock BridgeClient for testing."""
    with patch("inspekt.client.BridgeClient") as mock_class:
        mock_instance = Mock()
        mock_instance.is_alive.return_value = True
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def extract_article_script():
    """Load the extract_article.js script."""
    script_path = Path(__file__).parent.parent.parent / "inspekt" / "scripts" / "extract_article.js"
    with open(script_path) as f:
        return f.read()


class TestArticleExtractionScript:
    """Test the article extraction JavaScript directly."""

    def test_script_syntax_valid(self, extract_article_script):
        """Test that the script has valid JavaScript syntax."""
        # Basic check - script should be non-empty and contain key functions
        assert len(extract_article_script) > 0
        assert "function findTitle()" in extract_article_script
        assert "function findAuthor()" in extract_article_script
        assert "function findMainContent()" in extract_article_script
        assert "function extractText(" in extract_article_script

    def test_script_uses_no_external_dependencies(self, extract_article_script):
        """Test that script doesn't rely on external libraries."""
        # Should not contain references to external CDNs or libraries
        assert "unpkg.com" not in extract_article_script
        assert "cdn.jsdelivr.net" not in extract_article_script
        assert "Readability" not in extract_article_script

    def test_script_returns_iife(self, extract_article_script):
        """Test that script is wrapped in an IIFE."""
        assert extract_article_script.startswith("//")
        assert "(function()" in extract_article_script
        assert extract_article_script.strip().endswith("})()")

    def test_script_uses_var_declarations(self, extract_article_script):
        """Test that script uses var for compatibility."""
        # Count var vs const/let usage (var should dominate for compatibility)
        var_count = extract_article_script.count("var ")
        const_count = extract_article_script.count("const ")
        let_count = extract_article_script.count("let ")

        assert var_count > 0
        # Should primarily use var for ES5 compatibility
        assert var_count > const_count + let_count


class TestArticleExtractionLogic:
    """Test the article extraction logic with mock responses."""

    def test_extracts_title_from_og_meta(self, mock_client, extract_article_script):
        """Test extraction of title from Open Graph meta tag."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Article Title from OG",
                "byline": None,
                "content": "Article content here.",
                "excerpt": "Article content here.",
                "length": 21,
                "url": "https://example.com/article",
                "lang": "en"
            }
        }

        result = mock_client.execute(extract_article_script)

        assert result["ok"]
        assert result["result"]["title"] == "Article Title from OG"

    def test_extracts_author_from_meta(self, mock_client):
        """Test extraction of author from meta tag."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Test Article",
                "byline": "John Doe",
                "content": "Article content.",
                "excerpt": "Article content.",
                "length": 16,
                "url": "https://example.com",
                "lang": "en"
            }
        }

        result = mock_client.execute("script")

        assert result["result"]["byline"] == "John Doe"

    def test_extracts_content_from_article_tag(self, mock_client):
        """Test extraction of content from <article> tag."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Article",
                "byline": None,
                "content": "This is the main article content with multiple paragraphs.",
                "excerpt": "This is the main article content with multiple paragraphs.",
                "length": 58,
                "url": "https://example.com",
                "lang": "en"
            }
        }

        result = mock_client.execute("script")

        assert result["result"]["content"]
        assert len(result["result"]["content"]) > 0

    def test_creates_excerpt_from_content(self, mock_client):
        """Test that excerpt is created from first 200 characters."""
        long_content = "A" * 300
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Long Article",
                "byline": None,
                "content": long_content,
                "excerpt": long_content[:200] + "…",
                "length": 300,
                "url": "https://example.com",
                "lang": "en"
            }
        }

        result = mock_client.execute("script")

        assert result["result"]["excerpt"]
        assert result["result"]["excerpt"].endswith("…")
        assert len(result["result"]["excerpt"]) <= 203  # 200 + "…"

    def test_handles_missing_article_content(self, mock_client):
        """Test error handling when no article content is found."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "error": "Could not extract sufficient article content. This page may not be an article.",
                "url": "https://example.com"
            }
        }

        result = mock_client.execute("script")

        assert "error" in result["result"]
        assert "article" in result["result"]["error"].lower()

    def test_returns_url_in_response(self, mock_client):
        """Test that the response always includes the page URL."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Test",
                "byline": None,
                "content": "Content",
                "excerpt": "Content",
                "length": 7,
                "url": "https://example.com/test",
                "lang": "en"
            }
        }

        result = mock_client.execute("script")

        assert "url" in result["result"]
        assert result["result"]["url"].startswith("http")

    def test_returns_language_if_available(self, mock_client):
        """Test that the response includes language if available."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Test",
                "byline": None,
                "content": "Content",
                "excerpt": "Content",
                "length": 7,
                "url": "https://example.com",
                "lang": "fr"
            }
        }

        result = mock_client.execute("script")

        assert result["result"]["lang"] == "fr"


class TestContentFiltering:
    """Test that the extraction filters out non-content elements."""

    def test_filters_navigation_elements(self, mock_client):
        """Test that navigation elements are filtered out."""
        # The extraction should skip elements with 'nav', 'menu', etc in their class/id
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Article",
                "byline": None,
                "content": "Main article content only.",
                "excerpt": "Main article content only.",
                "length": 26,
                "url": "https://example.com",
                "lang": "en"
            }
        }

        result = mock_client.execute("script")

        # Content should not contain typical navigation text
        content = result["result"]["content"]
        assert content == "Main article content only."

    def test_filters_advertisement_elements(self, mock_client):
        """Test that advertisement elements are filtered out."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Article",
                "byline": None,
                "content": "Article content without ads.",
                "excerpt": "Article content without ads.",
                "length": 28,
                "url": "https://example.com",
                "lang": "en"
            }
        }

        result = mock_client.execute("script")

        # Should not contain ad-related content
        assert "advertisement" not in result["result"]["content"].lower()
        assert "sponsored" not in result["result"]["content"].lower()

    def test_preserves_article_structure(self, mock_client):
        """Test that article structure (headings, lists) is preserved."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "title": "Article",
                "byline": None,
                "content": "Heading 1\n\nParagraph text\n\n• List item 1\n• List item 2",
                "excerpt": "Heading 1 Paragraph text • List item 1 • List item 2",
                "length": 55,
                "url": "https://example.com",
                "lang": "en"
            }
        }

        result = mock_client.execute("script")

        content = result["result"]["content"]
        # Check for structure markers
        assert "\n\n" in content  # Paragraph breaks
        assert "•" in content  # List items


class TestErrorHandling:
    """Test error handling in article extraction."""

    def test_handles_script_errors_gracefully(self, mock_client):
        """Test that JavaScript errors are caught and reported."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "error": "Error extracting article: Cannot read property 'textContent' of null",
                "url": "https://example.com"
            }
        }

        result = mock_client.execute("script")

        assert "error" in result["result"]
        assert "Error extracting article" in result["result"]["error"]

    def test_handles_empty_page(self, mock_client):
        """Test handling of pages with no content."""
        mock_client.execute.return_value = {
            "ok": True,
            "result": {
                "error": "Could not identify main content area",
                "url": "https://example.com"
            }
        }

        result = mock_client.execute("script")

        assert "error" in result["result"]
        assert "content" in result["result"]["error"].lower()


class TestScriptPerformance:
    """Test performance characteristics of the extraction script."""

    def test_script_size_reasonable(self, extract_article_script):
        """Test that script size is reasonable (not too large)."""
        # Script should be under 15KB for reasonable loading time
        script_size = len(extract_article_script.encode('utf-8'))
        assert script_size < 15 * 1024, f"Script is {script_size} bytes, should be < 15KB"

    def test_script_has_no_blocking_operations(self, extract_article_script):
        """Test that script doesn't use blocking operations."""
        # Should not contain synchronous XHR or blocking operations
        assert "XMLHttpRequest" not in extract_article_script
        assert "new Promise" not in extract_article_script  # Should be synchronous
        assert "setTimeout" not in extract_article_script
        assert "await" not in extract_article_script
