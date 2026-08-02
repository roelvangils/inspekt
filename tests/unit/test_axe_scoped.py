"""
Unit tests for axe scoped testing helpers.

Tests the --scoped and --exclude helper logic used by the `inspekt a11y`
command (the standalone `axe` command was removed in favor of `a11y -e axe`).
"""

import json
from unittest.mock import Mock

import pytest

from inspekt.app.cli.accessibility import (
    _build_axe_context,
    _parse_selectors,
    _separator_line,
    _validate_selectors,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_bridge_client():
    """Mock BridgeClient with common test responses."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "url": "https://example.com",
            "title": "Test Page",
            "violations": [],
            "passes": [],
            "incomplete": [],
            "summary": {
                "violationCount": 0,
                "passCount": 0,
                "incompleteCount": 0,
                "criticalCount": 0,
                "seriousCount": 0,
                "moderateCount": 0,
                "minorCount": 0,
            },
            "axeVersion": "4.11.0",
        },
    }
    return mock_client


# =============================================================================
# Helper Function Tests
# =============================================================================


def test_separator_line():
    """Test that separator line is created correctly."""
    line = _separator_line()
    # Should contain only the horizontal line character
    assert "─" in line
    # Should have at least some characters (default fallback is 80)
    assert len(line.strip()) > 0


def test_separator_line_custom_color():
    """Test that separator line accepts custom color."""
    line = _separator_line(fg="red")
    # Should still contain the line character
    assert "─" in line


def test_parse_selectors_single():
    """Test parsing a single selector."""
    selectors = _parse_selectors(("header",))
    assert selectors == ["header"]


def test_parse_selectors_comma_separated():
    """Test parsing comma-separated selectors."""
    selectors = _parse_selectors(("header,footer,.ad-banner",))
    assert selectors == ["header", "footer", ".ad-banner"]


def test_parse_selectors_multiple_flags():
    """Test parsing multiple --exclude flags."""
    selectors = _parse_selectors(("header", "footer", ".ad-banner"))
    assert selectors == ["header", "footer", ".ad-banner"]


def test_parse_selectors_mixed():
    """Test parsing mixed comma-separated and multiple flags."""
    selectors = _parse_selectors(("header,footer", ".ad-banner", "nav,.sidebar"))
    assert selectors == ["header", "footer", ".ad-banner", "nav", ".sidebar"]


def test_parse_selectors_whitespace():
    """Test parsing selectors with whitespace."""
    selectors = _parse_selectors((" header , footer ", " .ad-banner "))
    assert selectors == ["header", "footer", ".ad-banner"]


def test_parse_selectors_empty():
    """Test parsing empty selector list."""
    selectors = _parse_selectors(())
    assert selectors == []


def test_validate_selectors_valid(mock_bridge_client):
    """Test validation of valid selectors."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "header": {"valid": True, "count": 1},
            "footer": {"valid": True, "count": 1},
        },
    }

    result = _validate_selectors(mock_bridge_client, ["header", "footer"], timeout=5.0)

    assert result["header"]["valid"] is True
    assert result["footer"]["valid"] is True


def test_validate_selectors_invalid(mock_bridge_client):
    """Test validation of invalid selectors."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "div[class=": {"valid": False, "error": "Expected ']' at position 10"},
        },
    }

    result = _validate_selectors(mock_bridge_client, ["div[class="], timeout=5.0)

    assert result["div[class="]["valid"] is False
    assert "error" in result["div[class="]


def test_validate_selectors_no_match(mock_bridge_client):
    """Test validation of selectors that match no elements."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            ".nonexistent": {"valid": True, "count": 0},
        },
    }

    result = _validate_selectors(mock_bridge_client, [".nonexistent"], timeout=5.0)

    assert result[".nonexistent"]["valid"] is True
    assert result[".nonexistent"]["count"] == 0


def test_build_axe_context_document(mock_bridge_client):
    """Test building context for full document (no scoped or exclude)."""
    context_expr, warning = _build_axe_context(mock_bridge_client, None, [], timeout=5.0)

    assert context_expr == "document"
    assert warning is None


def test_build_axe_context_exclude_only(mock_bridge_client):
    """Test building context with only exclude."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "header": {"valid": True, "count": 1},
            "footer": {"valid": True, "count": 1},
        },
    }

    context_expr, _warning = _build_axe_context(
        mock_bridge_client, None, ["header", "footer"], timeout=5.0
    )

    context_obj = json.loads(context_expr)
    assert "exclude" in context_obj
    assert context_obj["exclude"] == ["header", "footer"]


def test_build_axe_context_scoped_selector(mock_bridge_client):
    """Test building context with scoped selector."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "main": {"valid": True, "count": 1},
        },
    }

    context_expr, _warning = _build_axe_context(mock_bridge_client, "main", [], timeout=5.0)

    assert context_expr == '"main"'


def test_build_axe_context_scoped_multiple_selectors(mock_bridge_client):
    """Test building context with multiple scoped selectors."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "main": {"valid": True, "count": 1},
            "nav": {"valid": True, "count": 1},
        },
    }

    context_expr, _warning = _build_axe_context(mock_bridge_client, "main,nav", [], timeout=5.0)

    context_obj = json.loads(context_expr)
    assert context_obj == ["main", "nav"]


def test_build_axe_context_scoped_with_exclude(mock_bridge_client):
    """Test building context with both scoped and exclude."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "main": {"valid": True, "count": 1},
            ".ad-banner": {"valid": True, "count": 2},
        },
    }

    context_expr, _warning = _build_axe_context(
        mock_bridge_client, "main", [".ad-banner"], timeout=5.0
    )

    context_obj = json.loads(context_expr)
    assert "include" in context_obj
    assert "exclude" in context_obj
    assert context_obj["include"] == ["main"]
    assert context_obj["exclude"] == [".ad-banner"]


def test_build_axe_context_scoped_invalid_selector(mock_bridge_client):
    """Test that invalid --scoped selectors exit with an error."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "div[class=": {"valid": False, "error": "Expected ']'"},
        },
    }

    with pytest.raises(SystemExit):
        _build_axe_context(mock_bridge_client, "div[class=", [], timeout=5.0)


def test_build_axe_context_inspected_element(mock_bridge_client):
    """Test building context with inspected element."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "selector": ".product-card",
            "nodeName": "div",
        },
    }

    context_expr, warning = _build_axe_context(mock_bridge_client, "inspected", [], timeout=5.0)

    assert "window.__INSPEKT_INSPECTED_ELEMENT__" in context_expr
    assert warning is not None
    assert "incomplete results" in warning.lower()


def test_build_axe_context_inspected_with_exclude(mock_bridge_client):
    """Test building context with inspected element and exclude."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "selector": ".product-card",
            "nodeName": "div",
        },
    }

    context_expr, warning = _build_axe_context(
        mock_bridge_client, "inspected", [".tooltip"], timeout=5.0
    )

    assert "window.__INSPEKT_INSPECTED_ELEMENT__" in context_expr
    assert ".tooltip" in context_expr or "tooltip" in context_expr
    assert warning is not None


def test_build_axe_context_inspected_no_element(mock_bridge_client):
    """Test building context when no element is inspected."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": False,
            "error": "No element inspected",
        },
    }

    with pytest.raises(SystemExit):
        _build_axe_context(mock_bridge_client, "inspected", [], timeout=5.0)


# =============================================================================
# Panel Selection Requirement Tests
# =============================================================================


def test_build_axe_context_require_panel_selection_success(mock_bridge_client):
    """Test require_panel_selection succeeds when element was selected via panel."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "selector": ".product-card",
            "nodeName": "div",
            "selectionSource": "panel",
        },
    }

    context_expr, _warning = _build_axe_context(
        mock_bridge_client, "inspected", [], timeout=5.0, require_panel_selection=True
    )

    assert "window.__INSPEKT_INSPECTED_ELEMENT__" in context_expr


def test_build_axe_context_require_panel_selection_devtools_failure(mock_bridge_client):
    """Test require_panel_selection fails when element was selected via DevTools."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "selector": ".product-card",
            "nodeName": "div",
            "selectionSource": "devtools",
        },
    }

    with pytest.raises(SystemExit):
        _build_axe_context(
            mock_bridge_client,
            "inspected",
            [],
            timeout=5.0,
            require_panel_selection=True,
        )


def test_build_axe_context_require_panel_selection_unknown_source(mock_bridge_client):
    """Test require_panel_selection fails when selection source is unknown."""
    mock_bridge_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "selector": ".product-card",
            "nodeName": "div",
        },
    }

    with pytest.raises(SystemExit):
        _build_axe_context(
            mock_bridge_client,
            "inspected",
            [],
            timeout=5.0,
            require_panel_selection=True,
        )
