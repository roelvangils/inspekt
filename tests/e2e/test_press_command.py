"""
End-to-end tests for the `inspekt press` command.

These tests verify the press command works correctly with a real browser.
They require the Inspekt bridge server to be running and a browser connected.
"""

import pytest
from click.testing import CliRunner

from inspekt.app.cli import cli


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


class TestPressCommandCLI:
    """Tests for the press command CLI interface."""

    def test_help_shows_usage(self, runner):
        """The --help flag shows usage information."""
        result = runner.invoke(cli, ["press", "--help"])
        assert result.exit_code == 0
        assert "Send keyboard key presses" in result.output
        assert "KEYS" in result.output
        assert "MODIFIERS" in result.output
        assert "WAITS" in result.output

    def test_no_keys_shows_error(self, runner):
        """Calling press with no arguments shows an error."""
        result = runner.invoke(cli, ["press"])
        assert result.exit_code != 0
        # Click will show "Missing argument 'KEYS…'"

    def test_invalid_key_shows_error(self, runner):
        """Invalid key names produce a clear error message."""
        result = runner.invoke(cli, ["press", "NotAValidKey"])
        assert result.exit_code != 0
        assert "Unknown key" in result.output or "Error" in result.output

    def test_wait_exceeds_max_shows_error(self, runner):
        """Wait durations exceeding 60s produce an error."""
        result = runner.invoke(cli, ["press", "Wait(100)"])
        assert result.exit_code != 0
        assert "60" in result.output or "exceeds" in result.output.lower()


class TestPressCommandParsing:
    """Tests for key parsing in the press command (without browser)."""

    def test_parses_single_key(self, runner):
        """Single key like Tab should be parsed."""
        # This will fail at execution (no browser) but parsing should succeed
        result = runner.invoke(cli, ["press", "Tab"])
        # We expect it to fail with bridge error, not parsing error
        if result.exit_code != 0:
            assert "Unknown key" not in result.output

    def test_parses_modifier_combo(self, runner):
        """Modifier combos like Ctrl+A should be parsed."""
        result = runner.invoke(cli, ["press", "Ctrl+A"])
        if result.exit_code != 0:
            assert "Unknown key" not in result.output

    def test_parses_multiple_keys(self, runner):
        """Multiple keys should be parsed."""
        result = runner.invoke(cli, ["press", "Tab", "Tab", "Enter"])
        if result.exit_code != 0:
            assert "Unknown key" not in result.output

    def test_parses_wait_default(self, runner):
        """Wait token should be parsed."""
        result = runner.invoke(cli, ["press", "Tab", "Wait", "Tab"])
        if result.exit_code != 0:
            assert "Unknown key" not in result.output

    def test_parses_wait_custom(self, runner):
        """Wait(N) token should be parsed."""
        result = runner.invoke(cli, ["press", "Tab", "Wait(2)", "Enter"])
        if result.exit_code != 0:
            assert "Unknown key" not in result.output

    def test_case_insensitive(self, runner):
        """Key names should be case-insensitive."""
        result = runner.invoke(cli, ["press", "tab"])
        if result.exit_code != 0:
            assert "Unknown key" not in result.output

        result = runner.invoke(cli, ["press", "TAB"])
        if result.exit_code != 0:
            assert "Unknown key" not in result.output


@pytest.mark.e2e
@pytest.mark.skipif(True, reason="Requires running browser with Inspekt extension")
class TestPressCommandE2E:
    """
    End-to-end tests that require a browser.

    To run these tests:
    1. Start the Inspekt bridge: inspekt start
    2. Open a browser with the Inspekt extension
    3. Navigate to the test page
    4. Run: pytest tests/e2e/test_press_command.py -m e2e
    """

    def test_press_tab_moves_focus(self, runner):
        """Pressing Tab should move focus to the next element."""
        result = runner.invoke(cli, ["press", "Tab"])
        assert result.exit_code == 0
        assert "Pressed" in result.output

    def test_press_shift_tab_moves_focus_backward(self, runner):
        """Pressing Shift+Tab should move focus backward."""
        result = runner.invoke(cli, ["press", "Shift+Tab"])
        assert result.exit_code == 0
        assert "Pressed" in result.output

    def test_press_multiple_tabs(self, runner):
        """Multiple Tab presses should work."""
        result = runner.invoke(cli, ["press", "Tab", "Tab", "Tab"])
        assert result.exit_code == 0
        assert "Pressed 3 key" in result.output

    def test_press_with_wait(self, runner):
        """Wait tokens should cause delays between key presses."""
        import time

        start = time.time()
        result = runner.invoke(cli, ["press", "Tab", "Wait(1)", "Tab"])
        elapsed = time.time() - start

        assert result.exit_code == 0
        assert elapsed >= 1.0  # Should have waited at least 1 second

    def test_press_enter_activates_button(self, runner):
        """Pressing Enter on a button should click it."""
        # First navigate to a button
        runner.invoke(cli, ["press", "Tab", "Tab"])
        # Then press Enter
        result = runner.invoke(cli, ["press", "Enter"])
        assert result.exit_code == 0

    def test_press_with_selector(self, runner):
        """The --selector option should focus an element first."""
        result = runner.invoke(cli, ["press", "Tab", "--selector", "input#input1"])
        assert result.exit_code == 0

    def test_press_ctrl_a_selects_all(self, runner):
        """Ctrl+A should select all text in an input."""
        # Focus an input with text first
        runner.invoke(cli, ["type", "Hello World", "--selector", "input#input1"])
        # Then select all
        result = runner.invoke(cli, ["press", "Ctrl+A"])
        assert result.exit_code == 0

    def test_verbose_shows_details(self, runner):
        """The --verbose flag should show detailed key press info."""
        result = runner.invoke(cli, ["--verbose", "press", "Tab", "Tab"])
        assert result.exit_code == 0 or "Tab" in result.output
