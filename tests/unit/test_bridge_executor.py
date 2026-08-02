"""Unit tests for BridgeExecutor service."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from inspekt.services.bridge_executor import BridgeExecutor, get_executor


def make_connected_executor(**kwargs) -> BridgeExecutor:
    """Executor with a mocked client that passes the server/browser/domain preflights."""
    executor = BridgeExecutor(**kwargs)
    executor._client = Mock()
    executor._client.is_alive.return_value = True
    executor._client.get_status.return_value = {"connected_browsers": 1}
    executor._check_domain_and_prompt = Mock(return_value=True)
    return executor


class TestBridgeExecutorInitialization:
    """Test BridgeExecutor initialization."""

    def test_default_host_port_values(self):
        """Test BridgeExecutor with default host and port values."""
        executor = BridgeExecutor()
        assert executor.host == "127.0.0.1"
        assert executor.port == 8765
        assert executor.max_retries == 3
        assert executor.retry_delay == 0.5

    def test_custom_host_port(self):
        """Test BridgeExecutor with custom host and port."""
        executor = BridgeExecutor(host="192.168.1.100", port=9000)
        assert executor.host == "192.168.1.100"
        assert executor.port == 9000

    def test_max_retries_and_retry_delay_configuration(self):
        """Test max_retries and retry_delay configuration."""
        executor = BridgeExecutor(max_retries=5, retry_delay=1.0)
        assert executor.max_retries == 5
        assert executor.retry_delay == 1.0

    def test_lazy_client_initialization(self):
        """Test that client is not initialized until first access."""
        executor = BridgeExecutor()
        assert executor._client is None

        # Access client property
        with patch("inspekt.services.bridge_executor.BridgeClient") as mock_client_class:
            _ = executor.client  # access triggers lazy initialization
            mock_client_class.assert_called_once_with(host="127.0.0.1", port=8765)
            assert executor._client is not None

    def test_lazy_client_returns_same_instance(self):
        """Test that multiple accesses to client property return same instance."""
        executor = BridgeExecutor()

        with patch("inspekt.services.bridge_executor.BridgeClient") as mock_client_class:
            mock_instance = Mock()
            mock_client_class.return_value = mock_instance

            client1 = executor.client
            client2 = executor.client

            # Should only create client once
            mock_client_class.assert_called_once()
            assert client1 is client2
            assert client1 is mock_instance


class TestServerStatusChecking:
    """Test server status checking methods."""

    def test_is_server_running_returns_true(self):
        """Test is_server_running() when server is alive."""
        executor = BridgeExecutor()
        executor._client = Mock()
        executor._client.is_alive.return_value = True

        assert executor.is_server_running() is True
        executor._client.is_alive.assert_called_once()

    def test_is_server_running_returns_false(self):
        """Test is_server_running() when server is not alive."""
        executor = BridgeExecutor()
        executor._client = Mock()
        executor._client.is_alive.return_value = False

        assert executor.is_server_running() is False
        executor._client.is_alive.assert_called_once()

    @patch("inspekt.services.bridge_executor.click.echo")
    def test_ensure_server_running_success(self, mock_echo):
        """Test ensure_server_running() when server is running."""
        executor = BridgeExecutor()
        executor._client = Mock()
        executor._client.is_alive.return_value = True

        # Should not raise or exit
        executor.ensure_server_running()
        mock_echo.assert_not_called()

    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("inspekt.services.bridge_executor.sys.exit")
    def test_ensure_server_running_failure(self, mock_exit, mock_echo):
        """Test ensure_server_running() when server is not running (should exit)."""
        executor = BridgeExecutor()
        executor._client = Mock()
        executor._client.is_alive.return_value = False

        executor.ensure_server_running()

        mock_echo.assert_called_once_with(
            "Error: Bridge server is not running. Start it with: inspekt start",
            err=True,
        )
        mock_exit.assert_called_once_with(1)


class TestCodeExecution:
    """Test code execution methods."""

    @patch("inspekt.services.bridge_executor.click.echo")
    def test_execute_success(self, mock_echo):
        """Test execute() with successful execution."""
        executor = make_connected_executor()
        executor._client.execute.return_value = {
            "ok": True,
            "result": "Hello World",
            "url": "https://example.com",
        }

        result = executor.execute("console.log('test')")

        assert result["ok"] is True
        assert result["result"] == "Hello World"
        executor._client.execute.assert_called_once_with(
            "console.log('test')", timeout=10.0, _fast_poll=False, instance=None
        )
        mock_echo.assert_not_called()

    @patch("inspekt.services.bridge_executor.time.sleep")
    @patch("inspekt.services.bridge_executor.click.echo")
    def test_execute_with_timeout_and_retry_logic(self, mock_echo, mock_sleep):
        """Test execute() with timeout and retry logic."""
        executor = make_connected_executor(max_retries=3, retry_delay=0.5)

        # First two attempts timeout, third succeeds
        executor._client.execute.side_effect = [
            TimeoutError("Timeout 1"),
            TimeoutError("Timeout 2"),
            {"ok": True, "result": "success"},
        ]

        result = executor.execute("test code", timeout=5.0, retry_on_timeout=True)

        assert result["ok"] is True
        assert result["result"] == "success"
        assert executor._client.execute.call_count == 3

        # Check retry messages
        assert mock_echo.call_count == 2
        mock_echo.assert_any_call(
            "Timeout on attempt 1/3, retrying in 0.5s…", err=True
        )
        mock_echo.assert_any_call(
            "Timeout on attempt 2/3, retrying in 1.0s…", err=True
        )

        # Check exponential backoff
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(0.5)
        mock_sleep.assert_any_call(1.0)

    @patch("inspekt.services.bridge_executor.time.sleep")
    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("inspekt.services.bridge_executor.sys.exit")
    def test_execute_timeout_failure(self, mock_exit, mock_echo, mock_sleep):
        """Test execute() with TimeoutError that exhausts retries."""
        # Make sys.exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)

        executor = make_connected_executor(max_retries=2)
        executor._client.execute.side_effect = TimeoutError("Browser not responding")

        with pytest.raises(SystemExit):
            executor.execute("test code", retry_on_timeout=True)

        # Should show retry messages and then final error
        assert mock_echo.call_count >= 2
        # Final call should be the error
        final_call = mock_echo.call_args
        assert "Error:" in str(final_call)
        mock_exit.assert_called_with(1)

    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("inspekt.services.bridge_executor.sys.exit")
    def test_execute_connection_error(self, mock_exit, mock_echo):
        """Test execute() with ConnectionError."""
        # Make sys.exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)

        executor = make_connected_executor()
        executor._client.execute.side_effect = ConnectionError("Connection failed")

        with pytest.raises(SystemExit):
            executor.execute("test code")

        # Check that error was echoed
        mock_echo.assert_any_call("Error: Connection failed", err=True)
        mock_exit.assert_called_with(1)

    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("inspekt.services.bridge_executor.sys.exit")
    def test_execute_runtime_error(self, mock_exit, mock_echo):
        """Test execute() with RuntimeError."""
        # Make sys.exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)

        executor = make_connected_executor()
        executor._client.execute.side_effect = RuntimeError("Script execution failed")

        with pytest.raises(SystemExit):
            executor.execute("test code")

        # Check that error was echoed
        mock_echo.assert_any_call("Error: Script execution failed", err=True)
        mock_exit.assert_called_with(1)

    @patch("inspekt.services.bridge_executor.click.echo")
    def test_execute_retry_on_timeout_false(self, mock_echo):
        """Test execute() with retry_on_timeout=False uses single attempt."""
        executor = make_connected_executor(max_retries=5)
        executor._client.execute.return_value = {"ok": True, "result": "test"}

        result = executor.execute("test code", retry_on_timeout=False)

        assert result["ok"] is True
        # Should only call execute once even though max_retries is 5
        executor._client.execute.assert_called_once()


class TestFileExecution:
    """Test file execution methods."""

    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("builtins.open", create=True)
    def test_execute_file_success(self, mock_open, mock_echo):
        """Test execute_file() with successful file read and execution."""
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "console.log('from file');"
        mock_open.return_value = mock_file

        executor = make_connected_executor()
        executor._client.execute.return_value = {"ok": True, "result": "success"}

        result = executor.execute_file("/path/to/test.js")

        assert result["ok"] is True
        mock_open.assert_called_once_with("/path/to/test.js", encoding="utf-8")
        executor._client.execute.assert_called_once_with(
            "console.log('from file');", timeout=10.0, _fast_poll=False, instance=None
        )

    @patch("inspekt.services.bridge_executor.sys.exit")
    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("builtins.open", create=True)
    def test_execute_file_with_missing_file(self, mock_open, mock_echo, mock_exit):
        """Test execute_file() with FileNotFoundError."""
        # Make sys.exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)
        mock_open.side_effect = FileNotFoundError("File not found")

        executor = BridgeExecutor()

        with pytest.raises(SystemExit):
            executor.execute_file("/path/to/missing.js")

        mock_echo.assert_called_once_with(
            "Error reading file /path/to/missing.js: File not found", err=True
        )
        mock_exit.assert_called_with(1)

    @patch("inspekt.services.bridge_executor.sys.exit")
    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("builtins.open", create=True)
    def test_execute_file_with_io_error(self, mock_open, mock_echo, mock_exit):
        """Test execute_file() with IOError."""
        # Make sys.exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)
        mock_open.side_effect = OSError("Permission denied")

        executor = BridgeExecutor()

        with pytest.raises(SystemExit):
            executor.execute_file("/path/to/forbidden.js")

        mock_echo.assert_called_once_with(
            "Error reading file /path/to/forbidden.js: Permission denied", err=True
        )
        mock_exit.assert_called_with(1)

    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("builtins.open", create=True)
    def test_execute_file_with_custom_timeout(self, mock_open, mock_echo):
        """Test execute_file() with custom timeout and retry settings."""
        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = "test code"
        mock_open.return_value = mock_file

        executor = make_connected_executor()
        executor._client.execute.return_value = {"ok": True}

        executor.execute_file("/path/test.js", timeout=20.0, retry_on_timeout=True)

        executor._client.execute.assert_called_once_with(
            "test code", timeout=20.0, _fast_poll=False, instance=None
        )


class TestScriptExecutionWithTemplates:
    """Test script execution with template substitution."""

    @patch("inspekt.services.script_loader.ScriptLoader")
    @patch("inspekt.services.bridge_executor.click.echo")
    def test_execute_with_script_success(self, mock_echo, mock_loader_class):
        """Test execute_with_script() success."""
        mock_loader = Mock()
        mock_loader.load_script_sync.return_value = "console.log('loaded script');"
        mock_loader_class.return_value = mock_loader

        executor = make_connected_executor()
        executor._client.execute.return_value = {"ok": True, "result": "executed"}

        result = executor.execute_with_script("test_script.js")

        assert result["ok"] is True
        mock_loader.load_script_sync.assert_called_once_with(
            "test_script.js", substitutions=None
        )
        executor._client.execute.assert_called_once_with(
            "console.log('loaded script');", timeout=10.0, _fast_poll=False, instance=None
        )

    @patch("inspekt.services.script_loader.ScriptLoader")
    @patch("inspekt.services.bridge_executor.click.echo")
    def test_execute_with_script_with_substitutions(self, mock_echo, mock_loader_class):
        """Test execute_with_script() with template substitutions."""
        mock_loader = Mock()
        mock_loader.load_script_sync.return_value = "const action = 'start';"
        mock_loader_class.return_value = mock_loader

        executor = make_connected_executor()
        executor._client.execute.return_value = {"ok": True}

        substitutions = {"ACTION": "start", "VALUE": "42"}
        result = executor.execute_with_script(
            "template.js", substitutions=substitutions, timeout=15.0
        )

        assert result["ok"] is True
        mock_loader.load_script_sync.assert_called_once_with(
            "template.js", substitutions=substitutions
        )
        executor._client.execute.assert_called_once_with(
            "const action = 'start';", timeout=15.0, _fast_poll=False, instance=None
        )

    @patch("inspekt.services.script_loader.ScriptLoader")
    @patch("inspekt.services.bridge_executor.sys.exit")
    @patch("inspekt.services.bridge_executor.click.echo")
    def test_execute_with_script_missing_script(
        self, mock_echo, mock_exit, mock_loader_class
    ):
        """Test execute_with_script() with missing script file."""
        # Make sys.exit raise SystemExit to stop execution
        mock_exit.side_effect = SystemExit(1)

        mock_loader = Mock()
        mock_loader.load_script_sync.side_effect = FileNotFoundError(
            "Script not found: missing.js"
        )
        mock_loader_class.return_value = mock_loader

        executor = BridgeExecutor()

        with pytest.raises(SystemExit):
            executor.execute_with_script("missing.js")

        mock_echo.assert_called_once_with(
            "Error: Script not found: missing.js", err=True
        )
        mock_exit.assert_called_with(1)

    @patch("inspekt.services.script_loader.ScriptLoader")
    @patch("inspekt.services.bridge_executor.click.echo")
    def test_execute_with_script_with_retry_on_timeout(
        self, mock_echo, mock_loader_class
    ):
        """Test execute_with_script() with retry_on_timeout parameter."""
        mock_loader = Mock()
        mock_loader.load_script_sync.return_value = "test code"
        mock_loader_class.return_value = mock_loader

        executor = make_connected_executor()
        executor._client.execute.return_value = {"ok": True}

        executor.execute_with_script("test.js", retry_on_timeout=True)

        # Verify the execute call was made (retry_on_timeout is passed through)
        executor._client.execute.assert_called_once()


class TestResultChecking:
    """Test result checking methods."""

    @patch("inspekt.services.bridge_executor.click.echo")
    def test_check_result_ok_with_successful_result(self, mock_echo):
        """Test check_result_ok() with successful result."""
        executor = BridgeExecutor()
        result = {"ok": True, "result": "success"}

        # Should not raise or exit
        executor.check_result_ok(result)
        mock_echo.assert_not_called()

    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("inspekt.services.bridge_executor.sys.exit")
    def test_check_result_ok_with_failed_result(self, mock_exit, mock_echo):
        """Test check_result_ok() with failed result (should exit)."""
        executor = BridgeExecutor()
        result = {"ok": False, "error": "ReferenceError: foo is not defined"}

        executor.check_result_ok(result)

        mock_echo.assert_called_once_with(
            "Error: ReferenceError: foo is not defined", err=True
        )
        mock_exit.assert_called_once_with(1)

    @patch("inspekt.services.bridge_executor.click.echo")
    @patch("inspekt.services.bridge_executor.sys.exit")
    def test_check_result_ok_with_unknown_error(self, mock_exit, mock_echo):
        """Test check_result_ok() with result missing error message."""
        executor = BridgeExecutor()
        result = {"ok": False}

        executor.check_result_ok(result)

        mock_echo.assert_called_once_with("Error: Unknown error", err=True)
        mock_exit.assert_called_once_with(1)

    @patch("inspekt.services.bridge_executor.click.echo")
    def test_check_result_ok_with_missing_ok_field(self, mock_echo):
        """Test check_result_ok() when 'ok' field is missing (treated as falsy)."""
        executor = BridgeExecutor()

        with patch("inspekt.services.bridge_executor.sys.exit") as mock_exit:
            result = {"result": "something"}  # Missing 'ok' field

            executor.check_result_ok(result)

            mock_echo.assert_called_once_with("Error: Unknown error", err=True)
            mock_exit.assert_called_once_with(1)


class TestStatusAndVersionChecking:
    """Test status and version checking methods."""

    def test_get_status_success(self):
        """Test get_status() returns status dictionary."""
        executor = BridgeExecutor()
        executor._client = Mock()
        executor._client.get_status.return_value = {
            "ok": True,
            "timestamp": 1234567890.0,
            "connected_browsers": 1,
        }

        status = executor.get_status()

        assert status["ok"] is True
        assert status["timestamp"] == 1234567890.0
        executor._client.get_status.assert_called_once()

    def test_get_status_returns_none(self):
        """Test get_status() returns None when server not running."""
        executor = BridgeExecutor()
        executor._client = Mock()
        executor._client.get_status.return_value = None

        status = executor.get_status()

        assert status is None
        executor._client.get_status.assert_called_once()


class TestSingletonPattern:
    """Test singleton pattern for get_executor()."""

    def test_get_executor_returns_instance(self):
        """Test get_executor() returns a BridgeExecutor instance."""
        # Reset global state
        import inspekt.services.bridge_executor

        inspekt.services.bridge_executor._default_executor = None

        executor = get_executor()

        assert isinstance(executor, BridgeExecutor)
        assert executor.host == "127.0.0.1"
        assert executor.port == 8765
        assert executor.max_retries == 3

    def test_get_executor_returns_same_instance(self):
        """Test get_executor() returns same instance (singleton)."""
        # Reset global state
        import inspekt.services.bridge_executor

        inspekt.services.bridge_executor._default_executor = None

        executor1 = get_executor()
        executor2 = get_executor()

        assert executor1 is executor2

    def test_get_executor_with_custom_parameters(self):
        """Test get_executor() with custom parameters."""
        # Reset global state
        import inspekt.services.bridge_executor

        inspekt.services.bridge_executor._default_executor = None

        executor = get_executor(host="localhost", port=9000, max_retries=5)

        assert executor.host == "localhost"
        assert executor.port == 9000
        assert executor.max_retries == 5

    def test_get_executor_ignores_parameters_after_first_call(self):
        """Test get_executor() ignores parameters on subsequent calls (singleton)."""
        # Reset global state
        import inspekt.services.bridge_executor

        inspekt.services.bridge_executor._default_executor = None

        executor1 = get_executor(host="first", port=1111, max_retries=1)
        executor2 = get_executor(host="second", port=2222, max_retries=2)

        # Should be same instance with original parameters
        assert executor1 is executor2
        assert executor2.host == "first"
        assert executor2.port == 1111
        assert executor2.max_retries == 1
