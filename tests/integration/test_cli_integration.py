"""
Integration tests for CLI commands with services.

These tests verify that CLI commands properly integrate with services
without requiring a running browser. All external dependencies are mocked.

The CLI lives in ``inspekt.app.cli`` (lazy-loading Click group). Commands
use ``BridgeExecutor`` / ``get_executor`` from ``inspekt.services.bridge_executor``
rather than using ``BridgeClient`` directly, so mocks patch the name in the
module where each command looks it up:

- eval / exec  -> ``inspekt.app.cli.exec.BridgeExecutor``
- open         -> ``inspekt.app.cli.navigation.get_executor``
- status/start -> ``inspekt.app.cli.control.BridgeClient`` (+ ``_is_port_open``)
"""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from inspekt.app.cli import cli
from inspekt.app.cli.base import format_output


def combined_output(result):
    """Return stdout plus stderr (Click >= 8.2 no longer mixes them)."""
    output = result.output
    try:
        output += result.stderr
    except (ValueError, AttributeError):
        pass
    return output


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_executor():
    """Mock BridgeExecutor as used by the eval/exec commands."""
    with (
        patch("inspekt.app.cli.exec.BridgeExecutor") as mock_executor_class,
        patch("inspekt.app.cli.exec._get_console_logs_since", return_value=[]),
    ):
        mock_instance = Mock()
        mock_instance.execute.return_value = {
            "ok": True,
            "result": "test result",
            "url": "https://example.com",
            "title": "Test Page",
        }
        mock_instance.execute_file.return_value = {
            "ok": True,
            "result": "file result",
        }
        mock_executor_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_nav_executor():
    """Mock get_executor() as used by the navigation commands (open, etc.)."""
    with patch("inspekt.app.cli.navigation.get_executor") as mock_get_executor:
        mock_instance = Mock()
        mock_instance.execute.return_value = {"ok": True, "result": True}
        mock_instance.check_result_ok.return_value = None
        mock_get_executor.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_control_client():
    """Mock BridgeClient as used by the status/start commands in control.py.

    Also patches ``_is_port_open`` to True so the API server reads as running
    (the status command exits 1 unless both servers are up).
    """
    with (
        patch("inspekt.app.cli.control.BridgeClient") as mock_client_class,
        patch("inspekt.app.cli.control._is_port_open", return_value=True),
    ):
        mock_instance = Mock()
        mock_instance.is_alive.return_value = True
        mock_instance.get_status.return_value = {
            "server_version": "1.0.0",
            "uptime_seconds": 120,
            "host": "127.0.0.1",
            "port": 8765,
            "websocket_port": 8766,
            "connected_browsers": 0,
            "browsers": [],
            "pending_requests": 0,
            "completed_requests": 5,
        }
        mock_client_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_control_client_not_running():
    """Mock BridgeClient that simulates server not running (control.py)."""
    with (
        patch("inspekt.app.cli.control.BridgeClient") as mock_client_class,
        patch("inspekt.app.cli.control._is_port_open", return_value=False),
    ):
        mock_instance = Mock()
        mock_instance.is_alive.return_value = False
        mock_client_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def temp_js_file(tmp_path):
    """Create a temporary JavaScript file for testing."""
    js_file = tmp_path / "test.js"
    js_file.write_text("console.log('test');")
    return str(js_file)


# =============================================================================
# Test CLI Command Invocation
# =============================================================================


class TestCLIInvocation:
    """Test that CLI commands can be invoked via Click's testing utilities."""

    def test_eval_command_with_code_argument(self, runner, mock_executor):
        """Test eval command with code as argument."""
        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 0
        assert "test result" in result.output
        mock_executor.execute.assert_called_once()

    def test_eval_command_with_file_option(self, runner, mock_executor, temp_js_file):
        """Test eval command with --file option."""
        result = runner.invoke(cli, ["eval", "--file", temp_js_file])

        assert result.exit_code == 0
        mock_executor.execute_file.assert_called_once_with(temp_js_file, timeout=10.0)

    def test_eval_command_with_stdin(self, runner, mock_executor):
        """Test eval command reading from stdin."""
        result = runner.invoke(cli, ["eval"], input="console.log('stdin')")

        assert result.exit_code == 0
        mock_executor.execute.assert_called_once()
        call_args = mock_executor.execute.call_args[0][0]
        assert "console.log('stdin')" in call_args

    def test_exec_command_invocation(self, runner, mock_executor, temp_js_file):
        """Test exec command invocation."""
        result = runner.invoke(cli, ["exec", temp_js_file])

        assert result.exit_code == 0
        assert "file result" in result.output
        mock_executor.execute_file.assert_called_once()

    def test_open_command_invocation(self, runner, mock_nav_executor):
        """Test open command invocation."""
        result = runner.invoke(cli, ["open", "https://example.com"])

        assert result.exit_code == 0
        mock_nav_executor.execute.assert_called()

    def test_status_command(self, runner, mock_control_client):
        """Test status command (formerly 'server status')."""
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Running" in result.output
        mock_control_client.is_alive.assert_called()

    def test_help_text_generation_main(self, runner):
        """Test main CLI help text generation."""
        result = runner.invoke(cli, ["--help"])

        assert result.exit_code == 0
        assert "Inspekt" in result.output
        assert "Commands:" in result.output

    def test_help_text_generation_eval(self, runner):
        """Test eval command help text."""
        result = runner.invoke(cli, ["eval", "--help"])

        assert result.exit_code == 0
        assert "Execute JavaScript code" in result.output
        assert "--file" in result.output
        assert "--timeout" in result.output

    def test_error_handling_server_not_running(self, runner):
        """Test error handling when server is not running."""
        with (
            patch("inspekt.app.cli.exec.BridgeExecutor") as mock_executor_class,
            patch("inspekt.app.cli.exec._get_console_logs_since", return_value=[]),
        ):
            mock_instance = Mock()
            mock_instance.execute.side_effect = ConnectionError(
                "Bridge server is not running. Start it with: inspekt start"
            )
            mock_executor_class.return_value = mock_instance

            result = runner.invoke(cli, ["eval", "document.title"])

            assert result.exit_code == 1
            assert "Error" in combined_output(result)


# =============================================================================
# Test Service Integration
# =============================================================================


class TestServiceIntegration:
    """Test that CLI commands properly use services."""

    def test_bridge_executor_integration_execute(self, runner, mock_executor):
        """Test BridgeExecutor is used correctly for code execution."""
        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 0
        mock_executor.execute.assert_called_once()

    def test_bridge_executor_timeout_parameter(self, runner, mock_executor):
        """Test timeout parameter is passed to executor."""
        result = runner.invoke(cli, ["eval", "document.title", "--timeout", "20.0"])

        assert result.exit_code == 0
        mock_executor.execute.assert_called_once()
        call_kwargs = mock_executor.execute.call_args[1]
        assert call_kwargs["timeout"] == 20.0

    def test_configuration_loading_implicit(self, runner, mock_executor):
        """Test configuration is loaded implicitly by commands."""
        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 0

    def test_error_propagation_connection_error(self, runner, mock_executor):
        """Test ConnectionError propagates from service to CLI."""
        mock_executor.execute.side_effect = ConnectionError("Connection failed")

        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 1
        output = combined_output(result)
        assert "Error" in output
        assert "Connection failed" in output

    def test_error_propagation_timeout_error(self, runner, mock_executor):
        """Test TimeoutError propagates from service to CLI."""
        mock_executor.execute.side_effect = TimeoutError("Operation timed out")

        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 1
        output = combined_output(result)
        assert "Error" in output
        assert "timed out" in output

    def test_error_propagation_runtime_error(self, runner, mock_executor):
        """Test RuntimeError propagates from service to CLI."""
        mock_executor.execute.side_effect = RuntimeError("Script failed")

        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 1
        output = combined_output(result)
        assert "Error" in output
        assert "Script failed" in output

    def test_result_validation_ok_false(self, runner, mock_executor):
        """Test result validation when ok=False."""
        mock_executor.execute.return_value = {
            "ok": False,
            "error": "ReferenceError: foo is not defined",
        }

        result = runner.invoke(cli, ["eval", "foo()"])

        assert result.exit_code == 1
        output = combined_output(result)
        assert "Error" in output
        assert "ReferenceError" in output

    def test_client_initialization_with_default_config(self, runner, mock_control_client):
        """Test BridgeClient is initialized with default configuration."""
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        # Client should be created with defaults


# =============================================================================
# Test Script Loading Flow
# =============================================================================


class TestScriptLoading:
    """Test the complete script loading chain."""

    def test_script_loading_from_file(self, runner, mock_executor, temp_js_file):
        """Test script loading from file via execute_file."""
        result = runner.invoke(cli, ["exec", temp_js_file])

        assert result.exit_code == 0
        mock_executor.execute_file.assert_called_once_with(temp_js_file, timeout=10.0)

    def test_script_loading_with_timeout(self, runner, mock_executor, temp_js_file):
        """Test script loading with custom timeout."""
        result = runner.invoke(cli, ["exec", temp_js_file, "--timeout", "30.0"])

        assert result.exit_code == 0
        call_kwargs = mock_executor.execute_file.call_args[1]
        assert call_kwargs["timeout"] == 30.0

    def test_missing_script_handling(self, runner, mock_executor):
        """Test handling of missing script file."""
        result = runner.invoke(cli, ["exec", "/nonexistent/script.js"])

        assert result.exit_code == 2  # Click's file not found error
        output = combined_output(result).lower()
        assert "does not exist" in output or "error" in output

    def test_file_read_via_eval_file_option(self, runner, mock_executor, temp_js_file):
        """Test file reading via eval --file option."""
        result = runner.invoke(cli, ["eval", "--file", temp_js_file])

        assert result.exit_code == 0
        mock_executor.execute_file.assert_called_once()


# =============================================================================
# Test Error Handling
# =============================================================================


class TestErrorHandling:
    """Test error handling across layers."""

    def test_connection_error_handling(self, runner, mock_executor):
        """Test ConnectionError is handled and displayed."""
        mock_executor.execute.side_effect = ConnectionError("Server unavailable")

        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 1
        output = combined_output(result)
        assert "Error" in output
        assert "unavailable" in output

    def test_timeout_error_handling(self, runner, mock_executor):
        """Test TimeoutError is handled and displayed."""
        mock_executor.execute.side_effect = TimeoutError("Request timed out")

        result = runner.invoke(cli, ["eval", "document.title"])

        assert result.exit_code == 1
        assert "Error" in combined_output(result)

    def test_validation_error_handling(self, runner, mock_executor):
        """Test validation errors in result."""
        mock_executor.execute.return_value = {
            "ok": False,
            "error": "TypeError: Cannot read property 'x' of undefined",
        }

        result = runner.invoke(cli, ["eval", "obj.x"])

        assert result.exit_code == 1
        assert "TypeError" in combined_output(result)

    def test_file_not_found_error(self, runner, mock_executor):
        """Test file not found error handling."""
        result = runner.invoke(cli, ["exec", "/path/to/missing.js"])

        assert result.exit_code == 2
        # Click handles file validation

    def test_exit_code_on_execution_failure(self, runner, mock_executor):
        """Test proper exit code on execution failure."""
        mock_executor.execute.return_value = {
            "ok": False,
            "error": "Execution failed",
        }

        result = runner.invoke(cli, ["eval", "invalid()"])

        assert result.exit_code == 1

    def test_exit_code_on_connection_failure(self, runner, mock_executor):
        """Test proper exit code on connection failure."""
        mock_executor.execute.side_effect = ConnectionError("Failed")

        result = runner.invoke(cli, ["eval", "test"])

        assert result.exit_code == 1

    def test_server_not_running_status(self, runner, mock_control_client_not_running):
        """Test status output when server is not running."""
        result = runner.invoke(cli, ["status"])

        assert "Not Running" in result.output

    def test_eval_no_input_error(self, runner, mock_executor):
        """Test error when eval has no code input from stdin."""
        # CliRunner treats stdin as non-tty, so eval reads empty string from stdin
        # Then tries to execute it, which should fail
        mock_executor.execute.side_effect = ConnectionError("Failed to submit code")

        result = runner.invoke(cli, ["eval"], input="")

        assert result.exit_code == 1
        assert "Error" in combined_output(result)


# =============================================================================
# Test Output Formatting
# =============================================================================


class TestOutputFormatting:
    """Test output formatting functions."""

    def test_format_output_auto_string(self):
        """Test auto format with string result."""
        result = {"ok": True, "result": "Hello World"}
        output = format_output(result, "auto")
        assert output == "Hello World"

    def test_format_output_auto_number(self):
        """Test auto format with number result."""
        result = {"ok": True, "result": 42}
        output = format_output(result, "auto")
        assert output == "42"

    def test_format_output_auto_dict(self):
        """Test auto format with dictionary result."""
        result = {"ok": True, "result": {"key": "value"}}
        output = format_output(result, "auto")
        assert '"key"' in output
        assert '"value"' in output

    def test_format_output_auto_list(self):
        """Test auto format with list result."""
        result = {"ok": True, "result": [1, 2, 3]}
        output = format_output(result, "auto")
        assert "[" in output
        assert "1" in output

    def test_format_output_auto_undefined(self):
        """Test auto format with None (undefined) result."""
        result = {"ok": True, "result": None}
        output = format_output(result, "auto")
        assert output == "undefined"

    def test_format_output_json_format(self):
        """Test JSON output format."""
        result = {"ok": True, "result": {"key": "value"}}
        output = format_output(result, "json")
        parsed = json.loads(output)
        assert parsed == {"key": "value"}

    def test_format_output_raw_format(self):
        """Test raw output format."""
        result = {"ok": True, "result": "test value"}
        output = format_output(result, "raw")
        assert output == "test value"

    def test_format_output_raw_format_none(self):
        """Test raw format with None result."""
        result = {"ok": True, "result": None}
        output = format_output(result, "raw")
        assert output == ""

    def test_format_output_error(self):
        """Test format output with error."""
        result = {"ok": False, "error": "Something went wrong"}
        output = format_output(result, "auto")
        assert output == "Error: Something went wrong"

    def test_format_output_error_unknown(self):
        """Test format output with unknown error."""
        result = {"ok": False}
        output = format_output(result, "auto")
        assert output == "Error: Unknown error"

    def test_eval_output_with_format_option(self, runner, mock_executor):
        """Test eval command with --format option."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {"test": "data"},
        }

        result = runner.invoke(cli, ["eval", "getData()", "--format", "json", "--no-console"])

        assert result.exit_code == 0
        # Output should be JSON formatted
        parsed = json.loads(result.output.strip())
        assert parsed == {"test": "data"}

    def test_eval_output_with_url_flag(self, runner, mock_executor):
        """Test eval command with --url flag."""
        result = runner.invoke(cli, ["eval", "document.title", "--url"])

        assert result.exit_code == 0
        assert "https://example.com" in combined_output(result)

    def test_eval_output_with_title_flag(self, runner, mock_executor):
        """Test eval command with --title flag."""
        result = runner.invoke(cli, ["eval", "getData()", "--title"])

        assert result.exit_code == 0
        assert "Test Page" in combined_output(result)


# =============================================================================
# Test Complex Integration Scenarios
# =============================================================================


class TestComplexIntegration:
    """Test complex integration scenarios across multiple components."""

    def test_eval_command_full_flow(self, runner, mock_executor):
        """Test complete eval command flow from CLI to executor."""
        result = runner.invoke(
            cli, ["eval", "document.querySelector('h1').textContent", "--timeout", "15.0"]
        )

        assert result.exit_code == 0
        mock_executor.execute.assert_called_once()
        call_args, call_kwargs = mock_executor.execute.call_args
        assert "document.querySelector" in call_args[0]
        assert call_kwargs["timeout"] == 15.0

    def test_exec_command_full_flow(self, runner, mock_executor, temp_js_file):
        """Test complete exec command flow."""
        result = runner.invoke(cli, ["exec", temp_js_file, "--format", "json"])

        assert result.exit_code == 0
        mock_executor.execute_file.assert_called_once()

    def test_status_full_flow(self, runner, mock_control_client):
        """Test complete status flow."""
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Running" in result.output
        assert "Bridge Server" in result.output

    def test_error_recovery_chain(self, runner, mock_executor):
        """Test error handling chain from executor to CLI output."""
        # Simulate execution error
        mock_executor.execute.return_value = {
            "ok": False,
            "error": "ReferenceError: foo is not defined",
        }

        result = runner.invoke(cli, ["eval", "foo()"])

        assert result.exit_code == 1
        output = combined_output(result)
        assert "Error" in output
        assert "ReferenceError" in output

    def test_multiple_options_integration(self, runner, mock_executor):
        """Test command with multiple options."""
        result = runner.invoke(
            cli,
            [
                "eval",
                "document.title",
                "--timeout",
                "25.0",
                "--format",
                "raw",
                "--url",
                "--title",
            ],
        )

        assert result.exit_code == 0
        # Check timeout was passed
        call_kwargs = mock_executor.execute.call_args[1]
        assert call_kwargs["timeout"] == 25.0
        # Check metadata displayed
        output = combined_output(result)
        assert "URL:" in output or "https://example.com" in output


# =============================================================================
# Test CLI-Specific Behavior
# =============================================================================


class TestCLISpecificBehavior:
    """Test CLI-specific behavior and edge cases."""

    def test_version_option(self, runner):
        """Test --version option."""
        result = runner.invoke(cli, ["--version"])

        assert result.exit_code == 0
        # Should contain version information

    def test_command_without_arguments(self, runner):
        """Test running CLI without arguments shows help."""
        result = runner.invoke(cli, [])

        assert "Inspekt" in result.output or "Commands:" in result.output

    def test_invalid_command(self, runner):
        """Test invalid command shows error."""
        result = runner.invoke(cli, ["nonexistent"])

        assert result.exit_code != 0
        output = combined_output(result)
        assert "Error" in output or "No such command" in output

    def test_eval_stdin_interactive_error(self, runner, mock_executor):
        """Test eval command reads from stdin in test environment."""
        # CliRunner always treats stdin as non-tty, so eval reads from stdin
        # Empty stdin results in empty code being executed
        mock_executor.execute.side_effect = ConnectionError("Failed to submit code")

        result = runner.invoke(cli, ["eval"], input="")

        assert result.exit_code == 1
        assert "Error" in combined_output(result)

    def test_start_when_already_running(self, runner, mock_control_client):
        """Test start command when servers are already running."""
        with (
            patch("inspekt.app.cli.control.subprocess"),
            patch("inspekt.app.cli.control._is_port_open", return_value=True),
        ):
            result = runner.invoke(cli, ["start", "--no-update-check"])

            assert result.exit_code == 0
            assert "already running" in result.output

    def test_open_command_with_url(self, runner, mock_nav_executor):
        """Test open command with URL argument."""
        result = runner.invoke(cli, ["open", "https://example.org"])

        assert result.exit_code == 0
        mock_nav_executor.execute.assert_called()
