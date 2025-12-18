"""
Unit tests for axe command scoped testing functionality.

Tests the --scoped and --exclude options for the inspekt axe command.
"""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from inspekt.app.cli.accessibility import (
    _build_axe_context,
    _parse_selectors,
    _separator_line,
    _validate_selectors,
    axe,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


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

    context_expr, warning = _build_axe_context(
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

    context_expr, warning = _build_axe_context(
        mock_bridge_client, "main", [], timeout=5.0
    )

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

    context_expr, warning = _build_axe_context(
        mock_bridge_client, "main,nav", [], timeout=5.0
    )

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

    context_expr, warning = _build_axe_context(
        mock_bridge_client, "main", [".ad-banner"], timeout=5.0
    )

    context_obj = json.loads(context_expr)
    assert "include" in context_obj
    assert "exclude" in context_obj
    assert context_obj["include"] == ["main"]
    assert context_obj["exclude"] == [".ad-banner"]


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

    context_expr, warning = _build_axe_context(
        mock_bridge_client, "inspected", [], timeout=5.0
    )

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
# CLI Integration Tests
# =============================================================================


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
def test_axe_exclude_option(mock_open, mock_client_class, runner):
    """Test axe command with --exclude option."""
    # Mock the client
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "header": {"valid": True, "count": 1},
            "footer": {"valid": True, "count": 1},
        },
    }
    mock_client_class.return_value = mock_client

    # Mock file reading
    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    # Second call returns validation result, third returns axe results
    mock_client.execute.side_effect = [
        {  # Selector validation
            "ok": True,
            "result": {
                "header": {"valid": True, "count": 1},
                "footer": {"valid": True, "count": 1},
            },
        },
        {  # Axe results
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0, "passCount": 0},
                "axeVersion": "4.11.0",
            },
        },
    ]

    result = runner.invoke(axe, ["--exclude", "header,footer"])

    assert result.exit_code == 0
    assert "header" in result.output or "footer" in result.output or "Excluding" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
def test_axe_scoped_selector(mock_open, mock_client_class, runner):
    """Test axe command with --scoped option (CSS selector)."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    mock_client.execute.side_effect = [
        {  # Scoped selector validation
            "ok": True,
            "result": {
                "main": {"valid": True, "count": 1},
            },
        },
        {  # Axe results
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0, "passCount": 0},
                "axeVersion": "4.11.0",
            },
        },
    ]

    result = runner.invoke(axe, ["--scoped", "main"])

    assert result.exit_code == 0
    assert "Scoping to:" in result.output or "main" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
def test_axe_scoped_inspected(mock_open, mock_client_class, runner):
    """Test axe command with --scoped inspected option."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    mock_client.execute.side_effect = [
        {  # Check for inspected element
            "ok": True,
            "result": {
                "ok": True,
                "selector": ".product-card",
                "nodeName": "div",
            },
        },
        {  # Axe results
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0, "passCount": 0},
                "axeVersion": "4.11.0",
            },
        },
    ]

    result = runner.invoke(axe, ["--scoped", "inspected"])

    assert result.exit_code == 0
    assert "Scoping to inspected element:" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
def test_axe_scoped_inspected_no_element(mock_client_class, runner):
    """Test axe command with --scoped inspected when no element is inspected."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": False,
            "error": "No element inspected",
        },
    }

    result = runner.invoke(axe, ["--scoped", "inspected"])

    assert result.exit_code != 0
    assert "No element inspected" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
def test_axe_invalid_exclude_selector(mock_client_class, runner):
    """Test axe command with invalid --exclude selector."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "div[class=": {"valid": False, "error": "Expected ']'"},
        },
    }

    result = runner.invoke(axe, ["--exclude", "div[class="])

    assert result.exit_code != 0
    assert "Invalid CSS selectors" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
def test_axe_combined_scoped_and_exclude(mock_open, mock_client_class, runner):
    """Test axe command with both --scoped and --exclude options."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    mock_client.execute.side_effect = [
        {  # Exclude selector validation
            "ok": True,
            "result": {
                ".ad-banner": {"valid": True, "count": 2},
            },
        },
        {  # Scoped selector validation
            "ok": True,
            "result": {
                "main": {"valid": True, "count": 1},
            },
        },
        {  # Axe results
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0, "passCount": 0},
                "axeVersion": "4.11.0",
            },
        },
    ]

    result = runner.invoke(axe, ["--scoped", "main", "--exclude", ".ad-banner"])

    assert result.exit_code == 0
    # Should show both scoping and exclusion messages
    assert "Scoping to:" in result.output or "main" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
def test_axe_multiple_exclude_flags(mock_open, mock_client_class, runner):
    """Test axe command with multiple --exclude flags."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    mock_client.execute.side_effect = [
        {  # Exclude selector validation
            "ok": True,
            "result": {
                "header": {"valid": True, "count": 1},
                "footer": {"valid": True, "count": 1},
                ".ad-banner": {"valid": True, "count": 3},
            },
        },
        {  # Axe results
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0, "passCount": 0},
                "axeVersion": "4.11.0",
            },
        },
    ]

    result = runner.invoke(
        axe, ["--exclude", "header", "--exclude", "footer", "--exclude", ".ad-banner"]
    )

    assert result.exit_code == 0
    assert "Excluding:" in result.output


# =============================================================================
# Selection Source Tests
# =============================================================================


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
def test_axe_require_panel_selection_success(mock_open, mock_client_class, runner):
    """Test axe with --require-panel-selection when element was selected via panel."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    mock_client.execute.side_effect = [
        {  # Check for inspected element with panel source
            "ok": True,
            "result": {
                "ok": True,
                "selector": ".product-card",
                "nodeName": "div",
                "selectionSource": "panel",
            },
        },
        {  # Axe results
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0, "passCount": 0},
                "axeVersion": "4.11.0",
            },
        },
    ]

    result = runner.invoke(axe, ["--scoped", "inspected", "--require-panel-selection"])

    assert result.exit_code == 0
    assert "Element selected via Inspekt panel picker" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
def test_axe_require_panel_selection_devtools_failure(mock_client_class, runner):
    """Test axe with --require-panel-selection when element was selected via DevTools."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "selector": ".product-card",
            "nodeName": "div",
            "selectionSource": "devtools",
        },
    }

    result = runner.invoke(axe, ["--scoped", "inspected", "--require-panel-selection"])

    assert result.exit_code != 0
    assert "Element must be selected using Inspekt panel picker" in result.output
    assert "Chrome DevTools inspector" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
def test_axe_require_panel_selection_without_scoped(mock_client_class, runner):
    """Test that --require-panel-selection fails without --scoped inspected."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    result = runner.invoke(axe, ["--require-panel-selection"])

    assert result.exit_code != 0
    assert "--require-panel-selection can only be used with --scoped inspected" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
def test_axe_require_panel_selection_with_scoped_selector(mock_client_class, runner):
    """Test that --require-panel-selection fails with --scoped selector (not inspected)."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    result = runner.invoke(axe, ["--scoped", "main", "--require-panel-selection"])

    assert result.exit_code != 0
    assert "--require-panel-selection can only be used with --scoped inspected" in result.output


# =============================================================================
# Badge Functionality Tests
# =============================================================================
# Note: Badge injection is now integrated into run_axe.js using elementRef
# These tests verify badge functionality via integration tests


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
@patch("inspekt.config.load_config")
def test_axe_show_badges_enabled_by_default(mock_config, mock_open, mock_client_class, runner):
    """Test that badges are shown by default when config enables them."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    # Config has badges enabled by default
    mock_config.return_value = {
        "axe": {"show-badges": True},
        "ai": {},
        "control": {},
    }

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    # Mock axe results with violations and badge stats
    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "url": "https://example.com",
            "violations": [
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "nodes": [{"target": [".text"]}],
                }
            ],
            "passes": [],
            "incomplete": [],
            "summary": {"violationCount": 1},
            "badgeStats": {
                "ok": True,
                "badgesCreated": 1,
                "badgesFailed": 0,
                "badgesSkipped": 0,
                "totalViolations": 1,
                "maxBadges": 50,
            },
            "axeVersion": "4.11.0",
        },
    }

    result = runner.invoke(axe)

    assert result.exit_code == 0
    assert "violation badge(s) displayed" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
def test_axe_no_show_badges_flag(mock_open, mock_client_class, runner):
    """Test that badges are not shown when --no-show-badges flag is used."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "url": "https://example.com",
            "violations": [
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "nodes": [{"target": [".text"]}],
                }
            ],
            "passes": [],
            "incomplete": [],
            "summary": {"violationCount": 1},
            "axeVersion": "4.11.0",
        },
    }

    result = runner.invoke(axe, ["--no-show-badges"])

    assert result.exit_code == 0
    # Badge text should not appear when disabled
    assert "badge(s) displayed" not in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
@patch("inspekt.config.load_config")
def test_axe_show_badges_with_skipped_warning(mock_config, mock_open, mock_client_class, runner):
    """Test that badges show warning when some are skipped."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_config.return_value = {
        "axe": {"show-badges": True},
        "ai": {},
        "control": {},
    }

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    # Mock axe results with many violations and badge stats showing skipped badges
    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "url": "https://example.com",
            "violations": [
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "nodes": [{"target": [f".element-{i}"]} for i in range(60)],
                }
            ],
            "passes": [],
            "incomplete": [],
            "summary": {"violationCount": 60},
            "badgeStats": {
                "ok": True,
                "badgesCreated": 50,
                "badgesFailed": 0,
                "badgesSkipped": 10,
                "totalViolations": 60,
                "maxBadges": 50,
            },
            "axeVersion": "4.11.0",
        },
    }

    result = runner.invoke(axe)

    assert result.exit_code == 0
    assert "50 violation badge(s) displayed" in result.output
    assert "10 badge(s) skipped" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
@patch("inspekt.config.load_config")
def test_axe_badges_not_shown_for_json_output(mock_config, mock_open, mock_client_class, runner):
    """Test that badges are not shown when using JSON output."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_config.return_value = {
        "axe": {"show-badges": True},
        "ai": {},
        "control": {},
    }

    mock_open.return_value.__enter__.return_value.read.return_value = "// axe-core lib"

    # Mock axe results - badges should not be created for JSON output
    mock_client.execute.return_value = {
        "ok": True,
        "result": {
            "ok": True,
            "url": "https://example.com",
            "violations": [
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "nodes": [{"target": [".text"]}],
                }
            ],
            "passes": [],
            "incomplete": [],
            "summary": {"violationCount": 1},
            "badgeStats": {
                "ok": False,
                "badgesCreated": 0,
                "badgesFailed": 0,
                "badgesSkipped": 0,
            },
            "axeVersion": "4.11.0",
        },
    }

    result = runner.invoke(axe, ["--json"])

    assert result.exit_code == 0
    # Should output JSON, not badge messages
    assert "badge(s) displayed" not in result.output
    # Should contain valid JSON (may have warnings before it)
    # Find the JSON part (starts with '{')
    json_start = result.output.find('{')
    if json_start != -1:
        try:
            output_data = json.loads(result.output[json_start:])
            assert "violations" in output_data
        except json.JSONDecodeError:
            pytest.fail("Output does not contain valid JSON")
    else:
        pytest.fail("Output does not contain JSON")


# =============================================================================
# Interactive Badge Tests
# =============================================================================


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
@patch("inspekt.config.load_config")
def test_axe_interactive_badges_enabled(mock_config, mock_open, mock_client_class, runner):
    """Test that --interactive flag enables interactive badges."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_config.return_value = {
        "axe": {"show-badges": True},
        "ai": {},
        "control": {},
    }

    # Mock file reads - return different content for axe lib and run_axe.js
    axe_lib_mock = Mock()
    axe_lib_mock.read.return_value = "// axe-core library"

    script_mock = Mock()
    script_mock.read.return_value = "(async function() { const config = __AXE_CONFIG__; return await axe.run(document, config); })()"

    mock_open.return_value.__enter__.side_effect = [axe_lib_mock, script_mock]

    # Capture the script that was executed
    executed_script = None

    def capture_execute(script, timeout=None):
        nonlocal executed_script
        executed_script = script
        return {
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [
                    {
                        "id": "color-contrast",
                        "impact": "serious",
                        "nodes": [{"target": [".text"]}],
                    }
                ],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 1},
                "badgeStats": {
                    "ok": True,
                    "badgesCreated": 1,
                    "badgesFailed": 0,
                    "badgesSkipped": 0,
                },
                "axeVersion": "4.11.0",
            },
        }

    mock_client.execute.side_effect = capture_execute

    result = runner.invoke(axe, ["--interactive"])

    assert result.exit_code == 0
    # Verify that __interactiveBadges was set to true in the config
    assert executed_script is not None
    assert '"__interactiveBadges": true' in executed_script or '"__interactiveBadges":true' in executed_script


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
@patch("inspekt.config.load_config")
def test_axe_interactive_without_badges_fails(mock_config, mock_open, mock_client_class, runner):
    """Test that --interactive without --show-badges fails."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_config.return_value = {
        "axe": {"show-badges": False},
        "ai": {},
        "control": {},
    }

    result = runner.invoke(axe, ["--interactive"])

    assert result.exit_code != 0
    assert "--interactive requires --show-badges to be enabled" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
def test_axe_interactive_with_no_show_badges_flag_fails(mock_client_class, runner):
    """Test that --interactive with --no-show-badges flag fails."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    result = runner.invoke(axe, ["--interactive", "--no-show-badges"])

    assert result.exit_code != 0
    assert "--interactive requires --show-badges to be enabled" in result.output


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
@patch("inspekt.config.load_config")
def test_axe_interactive_with_show_badges_explicit(mock_config, mock_open, mock_client_class, runner):
    """Test that --interactive works with explicit --show-badges flag."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_config.return_value = {
        "axe": {"show-badges": False},  # Config has it disabled
        "ai": {},
        "control": {},
    }

    # Mock file reads - return different content for axe lib and run_axe.js
    axe_lib_mock = Mock()
    axe_lib_mock.read.return_value = "// axe-core library"

    script_mock = Mock()
    script_mock.read.return_value = "(async function() { const config = __AXE_CONFIG__; return await axe.run(document, config); })()"

    mock_open.return_value.__enter__.side_effect = [axe_lib_mock, script_mock]

    # Capture the script that was executed
    executed_script = None

    def capture_execute(script, timeout=None):
        nonlocal executed_script
        executed_script = script
        return {
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0},
                "axeVersion": "4.11.0",
            },
        }

    mock_client.execute.side_effect = capture_execute

    result = runner.invoke(axe, ["--interactive", "--show-badges"])

    assert result.exit_code == 0
    # Verify that both flags were passed
    assert executed_script is not None
    assert '"__showBadges": true' in executed_script or '"__showBadges":true' in executed_script
    assert '"__interactiveBadges": true' in executed_script or '"__interactiveBadges":true' in executed_script


@patch("inspekt.app.cli.accessibility.BridgeClient")
@patch("inspekt.app.cli.accessibility.builtin_open")
@patch("inspekt.config.load_config")
def test_axe_interactive_disabled_for_json_output(mock_config, mock_open, mock_client_class, runner):
    """Test that interactive badges are disabled for JSON output."""
    mock_client = Mock()
    mock_client.is_alive.return_value = True
    mock_client_class.return_value = mock_client

    mock_config.return_value = {
        "axe": {"show-badges": True},
        "ai": {},
        "control": {},
    }

    # Mock file reads - return different content for axe lib and run_axe.js
    axe_lib_mock = Mock()
    axe_lib_mock.read.return_value = "// axe-core library"

    script_mock = Mock()
    script_mock.read.return_value = "(async function() { const config = __AXE_CONFIG__; return await axe.run(document, config); })()"

    mock_open.return_value.__enter__.side_effect = [axe_lib_mock, script_mock]

    # Capture the script that was executed
    executed_script = None

    def capture_execute(script, timeout=None):
        nonlocal executed_script
        executed_script = script
        return {
            "ok": True,
            "result": {
                "ok": True,
                "url": "https://example.com",
                "violations": [],
                "passes": [],
                "incomplete": [],
                "summary": {"violationCount": 0},
                "axeVersion": "4.11.0",
            },
        }

    mock_client.execute.side_effect = capture_execute

    result = runner.invoke(axe, ["--interactive", "--json"])

    assert result.exit_code == 0
    # Verify that both flags are false for JSON output
    assert executed_script is not None
    assert '"__showBadges": false' in executed_script or '"__showBadges":false' in executed_script
    assert '"__interactiveBadges": false' in executed_script or '"__interactiveBadges":false' in executed_script
