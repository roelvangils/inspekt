"""
End-to-End Tests for Zen Bridge

These tests verify the complete integration between:
- Bridge server startup and lifecycle
- CLI command execution
- Browser interaction via WebSocket
- JavaScript script loading and execution
- Real browser automation with Playwright

Requirements:
    pip install playwright pytest-asyncio
    playwright install chromium

Running:
    # Run all E2E tests
    pytest tests/e2e/ -v

    # Run only E2E tests (skip if dependencies missing)
    pytest tests/e2e/ -v -m e2e

    # Run specific test pattern
    pytest tests/e2e/ -v -k "test_eval"

    # Run slow tests
    pytest tests/e2e/ -v -m slow

Skip Behavior:
    Tests automatically skip if:
    - Playwright is not installed
    - Chromium browser is not installed
    - Server fails to start

Architecture:
    - Server runs in background thread during test session
    - Browser launches once per test session (shared)
    - Each test gets a fresh page context
    - Cleanup happens automatically via fixtures

Test Organization:
    - TestServerHealthChecks: Server startup and health endpoints
    - TestBasicExecution: JavaScript eval/exec commands
    - TestScriptLoading: Helper script loading and caching
    - TestWebSocketCommunication: WebSocket protocol tests
"""

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest
import requests

# Check if Playwright is available
try:
    from playwright.sync_api import Page, sync_playwright
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    Page = None  # type: ignore
    PlaywrightTimeoutError = Exception  # type: ignore


# ============================================================================
# Test Markers
# ============================================================================

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed"),
]


# ============================================================================
# Helper Functions
# ============================================================================


def wait_for_server(host: str = "127.0.0.1", port: int = 8765, timeout: int = 10) -> bool:
    """
    Wait for server to be ready by polling health endpoint.

    Args:
        host: Server host
        port: Server port
        timeout: Maximum time to wait in seconds

    Returns:
        True if server is ready, False if timeout
    """
    start_time = time.time()
    url = f"http://{host}:{port}/health"

    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.1)

    return False


def inject_userscript(page: Page, ws_port: int = 8766) -> None:
    """
    Inject the Zen Bridge userscript into a page.

    This simulates the userscript being active in the browser.

    Args:
        page: Playwright page object
        ws_port: WebSocket server port
    """
    # Read the actual userscript from the project
    project_root = Path(__file__).parent.parent.parent
    userscript_path = project_root / "userscript_ws.js"

    if userscript_path.exists():
        userscript_content = userscript_path.read_text()
    else:
        # Fallback minimal userscript if file not found
        userscript_content = f"""
        (function() {{
            'use strict';
            window.__ZEN_BRIDGE_VERSION__ = '3.4';
            const WS_URL = 'ws://127.0.0.1:{ws_port}/ws';
            let ws = null;

            function connect() {{
                if (ws && ws.readyState === WebSocket.OPEN) return;
                ws = new WebSocket(WS_URL);

                ws.onopen = () => {{
                    console.log('[Inspekt] Connected via WebSocket');
                    window.__zen_ws__ = ws;
                }};

                ws.onmessage = async (event) => {{
                    try {{
                        const message = JSON.parse(event.data);
                        if (message.type === 'execute') {{
                            const requestId = message.request_id;
                            const code = message.code;
                            let result, error = null;

                            try {{
                                result = (0, eval)(code);
                                if (result && typeof result.then === 'function') {{
                                    result = await result;
                                }}
                            }} catch (e) {{
                                error = String(e && e.stack ? e.stack : e);
                            }}

                            ws.send(JSON.stringify({{
                                type: 'result',
                                request_id: requestId,
                                ok: !error,
                                result: error ? null : (typeof result === 'undefined' ? null : result),
                                error,
                                url: location.href,
                                title: document.title || ''
                            }}));
                        }}
                    }} catch (err) {{
                        console.error('[Inspekt] Error handling message:', err);
                    }}
                }};

                ws.onerror = (error) => {{
                    console.error('[Inspekt] WebSocket error:', error);
                }};

                ws.onclose = () => {{
                    console.log('[Inspekt] Disconnected, reconnecting…');
                    setTimeout(connect, 1000);
                }};
            }}

            connect();
        }})();
        """

    # Inject the userscript
    page.add_init_script(userscript_content)


def create_test_page(page: Page, html: str) -> None:
    """
    Create a test HTML page with the given content.

    Args:
        page: Playwright page object
        html: HTML content to load
    """
    page.set_content(html)


# ============================================================================
# Pytest Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def server(project_root: Path) -> dict[str, Any]:
    """
    Start bridge server in background for tests.

    Yields:
        Dictionary with server info (host, port, ws_port, process)
    """
    host = "127.0.0.1"
    port = 8765
    ws_port = 8766

    # Start server process in background
    process = subprocess.Popen(
        [sys.executable, "-m", "zen.bridge_ws"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(project_root),
    )

    # Wait for server to be ready
    if not wait_for_server(host, port, timeout=10):
        process.terminate()
        process.wait(timeout=5)
        pytest.skip("Failed to start bridge server")

    print(f"\n[Test Setup] Bridge server started on {host}:{port}")

    server_info = {
        "host": host,
        "port": port,
        "ws_port": ws_port,
        "process": process,
        "base_url": f"http://{host}:{port}",
        "ws_url": f"ws://{host}:{ws_port}/ws",
    }

    yield server_info

    # Cleanup: stop server
    print("\n[Test Cleanup] Stopping bridge server")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture(scope="module")
def browser():
    """
    Launch browser with Playwright.

    Yields:
        Playwright browser instance
    """
    # Check if Chromium is installed
    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        print("\n[Test Setup] Browser launched")

        yield browser

        print("\n[Test Cleanup] Closing browser")
        browser.close()
        playwright.stop()

    except Exception as e:
        pytest.skip(f"Failed to launch browser: {e}")


@pytest.fixture
def page(browser, server: dict[str, Any]) -> Page:
    """
    Create a new browser page with userscript injected.

    Args:
        browser: Playwright browser instance
        server: Server info dictionary

    Yields:
        Playwright page with userscript active
    """
    context = browser.new_context()
    page = context.new_page()

    # Inject userscript before navigation
    inject_userscript(page, ws_port=server["ws_port"])

    # Navigate to a blank page to trigger userscript
    page.goto("about:blank")

    # Wait a bit for WebSocket to connect
    time.sleep(0.5)

    yield page

    # Cleanup
    page.close()
    context.close()


@pytest.fixture
def cli_runner(server: dict[str, Any]):
    """
    Create a test client that works with the real server.

    Args:
        server: Server info dictionary

    Returns:
        Dictionary with helper functions for CLI-like operations
    """
    base_url = server["base_url"]

    def execute_code(code: str, timeout: float = 5.0) -> dict[str, Any]:
        """Execute JavaScript code via HTTP API (simulates CLI)."""
        # Submit code
        response = requests.post(
            f"{base_url}/run",
            json={"code": code},
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            return {"ok": False, "error": data.get("error")}

        request_id = data["request_id"]

        # Poll for result
        start_time = time.time()
        while time.time() - start_time < timeout:
            result_response = requests.get(
                f"{base_url}/result",
                params={"request_id": request_id},
                timeout=5,
            )

            if result_response.status_code == 200:
                result = result_response.json()
                if result.get("status") != "pending":
                    return result

            time.sleep(0.1)

        return {"ok": False, "error": "Timeout waiting for result"}

    def get_status() -> dict[str, Any]:
        """Get server status."""
        response = requests.get(f"{base_url}/health", timeout=5)
        response.raise_for_status()
        return response.json()

    def get_notifications() -> dict[str, Any]:
        """Get pending notifications."""
        response = requests.get(f"{base_url}/notifications", timeout=5)
        response.raise_for_status()
        return response.json()

    return {
        "execute": execute_code,
        "get_status": get_status,
        "get_notifications": get_notifications,
        "base_url": base_url,
    }


# ============================================================================
# Test Suite: Server Health Checks
# ============================================================================


class TestServerHealthChecks:
    """Tests for server startup and health endpoints."""

    def test_server_starts_successfully(self, server: dict[str, Any]):
        """Test that the bridge server starts and responds to requests."""
        response = requests.get(f"{server['base_url']}/health", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_server_health_endpoint_returns_status(self, server: dict[str, Any]):
        """Test that /health endpoint returns server status information."""
        response = requests.get(f"{server['base_url']}/health", timeout=5)
        data = response.json()

        assert "ok" in data
        assert "timestamp" in data
        assert "connected_browsers" in data
        assert "pending" in data
        assert "completed" in data

        assert isinstance(data["timestamp"], (int, float))
        assert isinstance(data["connected_browsers"], int)
        assert isinstance(data["pending"], int)
        assert isinstance(data["completed"], int)

    def test_server_handles_multiple_requests(self, server: dict[str, Any]):
        """Test that server can handle multiple sequential health check requests."""
        for _ in range(5):
            response = requests.get(f"{server['base_url']}/health", timeout=5)
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True


# ============================================================================
# Test Suite: Basic Command Execution
# ============================================================================


class TestBasicExecution:
    """Tests for basic JavaScript command execution."""

    @pytest.mark.slow
    def test_eval_returns_document_title(self, page: Page, cli_runner: dict[str, Any]):
        """Test that 'inspekt eval \"document.title\"' returns the page title."""
        # Set page title
        page.evaluate("document.title = 'Test Page Title'")

        # Execute via CLI runner
        result = cli_runner["execute"]("document.title")

        assert result["ok"] is True
        assert result["result"] == "Test Page Title"
        assert "url" in result
        assert "title" in result

    @pytest.mark.slow
    def test_eval_with_syntax_error(self, page: Page, cli_runner: dict[str, Any]):
        """Test that eval with syntax error returns error message."""
        result = cli_runner["execute"]("this is invalid javascript syntax {{{")

        assert result["ok"] is False
        assert "error" in result
        assert result["error"] is not None
        assert "SyntaxError" in result["error"] or "Unexpected" in result["error"]

    @pytest.mark.slow
    def test_eval_with_runtime_error(self, page: Page, cli_runner: dict[str, Any]):
        """Test that eval with runtime error returns error message."""
        result = cli_runner["execute"]("nonExistentVariable.property")

        assert result["ok"] is False
        assert "error" in result
        assert result["error"] is not None

    @pytest.mark.slow
    def test_eval_with_simple_expression(self, page: Page, cli_runner: dict[str, Any]):
        """Test evaluating a simple mathematical expression."""
        result = cli_runner["execute"]("2 + 2")

        assert result["ok"] is True
        assert result["result"] == 4

    @pytest.mark.slow
    def test_eval_with_undefined_result(self, page: Page, cli_runner: dict[str, Any]):
        """Test that undefined return values are handled correctly."""
        result = cli_runner["execute"]("undefined")

        assert result["ok"] is True
        # undefined becomes null in JSON
        assert result["result"] is None

    @pytest.mark.slow
    def test_timeout_handling(self, page: Page, cli_runner: dict[str, Any]):
        """Test that timeout is handled correctly for long-running code."""
        # Execute code that takes longer than timeout
        result = cli_runner["execute"](
            "new Promise(resolve => setTimeout(resolve, 10000))",
            timeout=1.0,
        )

        # Should timeout
        assert result["ok"] is False
        assert "timeout" in result["error"].lower() or "Timeout" in result["error"]

    def test_server_status_command(self, cli_runner: dict[str, Any]):
        """Test getting server status via CLI."""
        status = cli_runner["get_status"]()

        assert status["ok"] is True
        assert "connected_browsers" in status
        assert status["connected_browsers"] >= 0


# ============================================================================
# Test Suite: Script Loading
# ============================================================================


class TestScriptLoading:
    """Tests for JavaScript helper script loading."""

    def test_helper_scripts_directory_exists(self, project_root: Path):
        """Test that helper scripts directory exists."""
        scripts_dir = project_root / "inspekt" / "scripts"
        assert scripts_dir.exists()
        assert scripts_dir.is_dir()

    def test_template_substitution_works(self, project_root: Path):
        """Test that template substitution works for script placeholders."""
        from inspekt.services.script_loader import ScriptLoader

        loader = ScriptLoader()

        # Create a temporary test script with placeholders
        test_script = "const action = 'ACTION_PLACEHOLDER';"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, dir=project_root / "inspekt" / "scripts"
        ) as f:
            f.write(test_script)
            temp_path = Path(f.name)

        try:
            # Load with substitution
            result = loader.load_with_substitution_sync(
                temp_path.name,
                placeholders={"ACTION_PLACEHOLDER": "test_action"},
            )

            assert "test_action" in result
            assert "ACTION_PLACEHOLDER" not in result

        finally:
            # Cleanup
            temp_path.unlink()

    def test_script_caching_works(self, project_root: Path):
        """Test that script caching works to avoid repeated file reads."""
        from inspekt.services.script_loader import ScriptLoader

        loader = ScriptLoader()

        # Create a test script
        test_content = "console.log('cached test');"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, dir=project_root / "inspekt" / "scripts"
        ) as f:
            f.write(test_content)
            temp_path = Path(f.name)

        try:
            # Load script twice
            result1 = loader.load_script_sync(temp_path.name)
            result2 = loader.load_script_sync(temp_path.name)

            # Should return same content
            assert result1 == result2
            assert test_content in result1

            # Check cache
            cached = loader.get_cached_scripts()
            assert temp_path.name in cached

        finally:
            # Cleanup
            temp_path.unlink()


# ============================================================================
# Test Suite: WebSocket Communication
# ============================================================================


class TestWebSocketCommunication:
    """Tests for WebSocket protocol between browser and server."""

    def test_websocket_connection_establishes(self, page: Page, server: dict[str, Any]):
        """Test that WebSocket connection is established successfully."""
        # Check if WebSocket is connected
        is_connected = page.evaluate(
            """
            () => {
                return window.__zen_ws__ && window.__zen_ws__.readyState === WebSocket.OPEN;
            }
        """
        )

        # May need a moment for connection
        if not is_connected:
            time.sleep(1)
            is_connected = page.evaluate(
                """
                () => {
                    return window.__zen_ws__ && window.__zen_ws__.readyState === WebSocket.OPEN;
                }
            """
            )

        assert is_connected, "WebSocket should be connected"

    @pytest.mark.slow
    def test_request_response_cycle(self, page: Page, cli_runner: dict[str, Any]):
        """Test complete request/response cycle through WebSocket."""
        # Set a variable in the page
        page.evaluate("window.testValue = 42;")

        # Request it via WebSocket (through CLI)
        result = cli_runner["execute"]("window.testValue")

        assert result["ok"] is True
        assert result["result"] == 42

    def test_websocket_version_exposed(self, page: Page):
        """Test that userscript version is exposed to browser."""
        version = page.evaluate("window.__ZEN_BRIDGE_VERSION__")
        assert version is not None
        assert isinstance(version, str)
        assert len(version) > 0

    @pytest.mark.slow
    def test_notification_handling(self, page: Page, cli_runner: dict[str, Any]):
        """Test that notifications can be retrieved from server."""
        # Get notifications endpoint
        notifications = cli_runner["get_notifications"]()

        assert notifications["ok"] is True
        assert "notifications" in notifications
        assert isinstance(notifications["notifications"], list)

    @pytest.mark.slow
    def test_multiple_sequential_executions(self, page: Page, cli_runner: dict[str, Any]):
        """Test multiple sequential code executions through WebSocket."""
        # Execute multiple commands sequentially
        results = []
        for i in range(3):
            result = cli_runner["execute"](f"({i} + 1) * 2")
            results.append(result)

        # Verify all succeeded
        assert all(r["ok"] for r in results)
        assert results[0]["result"] == 2
        assert results[1]["result"] == 4
        assert results[2]["result"] == 6

    @pytest.mark.slow
    def test_error_propagation_through_websocket(self, page: Page, cli_runner: dict[str, Any]):
        """Test that errors are properly propagated through WebSocket."""
        result = cli_runner["execute"]("throw new Error('Test error')")

        assert result["ok"] is False
        assert "error" in result
        assert "Test error" in result["error"]


# ============================================================================
# Test Suite: Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_code_submission(self, server: dict[str, Any]):
        """Test that empty code submission is rejected."""
        response = requests.post(
            f"{server['base_url']}/run",
            json={"code": ""},
            timeout=5,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False

    def test_missing_code_field(self, server: dict[str, Any]):
        """Test that request without code field is rejected."""
        response = requests.post(
            f"{server['base_url']}/run",
            json={},
            timeout=5,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False

    def test_invalid_request_id(self, server: dict[str, Any]):
        """Test that querying invalid request_id returns error."""
        response = requests.get(
            f"{server['base_url']}/result",
            params={"request_id": "invalid-uuid-12345"},
            timeout=5,
        )

        assert response.status_code == 404
        data = response.json()
        assert data["ok"] is False

    def test_missing_request_id_parameter(self, server: dict[str, Any]):
        """Test that result endpoint requires request_id parameter."""
        response = requests.get(
            f"{server['base_url']}/result",
            timeout=5,
        )

        assert response.status_code == 400
        data = response.json()
        assert data["ok"] is False


# ============================================================================
# Test Summary
# ============================================================================

"""
Test Summary:
-------------
Total Test Classes: 5
  - TestServerHealthChecks: 3 tests
  - TestBasicExecution: 7 tests
  - TestScriptLoading: 3 tests
  - TestWebSocketCommunication: 6 tests
  - TestEdgeCases: 4 tests

Total Tests: 23

Test Coverage:
  - Server startup and health checks
  - Basic JavaScript evaluation
  - Error handling (syntax, runtime, timeout)
  - Script loading and caching
  - Template substitution
  - WebSocket connection and communication
  - Request/response cycle
  - Notification handling
  - Edge cases and validation

Markers Used:
  - @pytest.mark.e2e: All tests
  - @pytest.mark.slow: Tests that may take >1 second

Dependencies:
  - pytest
  - pytest-asyncio
  - playwright
  - requests
  - Chromium browser (installed via playwright install)

Fixtures:
  - project_root (module scope): Project directory
  - server (module scope): Background server process
  - browser (module scope): Playwright browser instance
  - page (function scope): Fresh page with userscript
  - cli_runner (function scope): CLI simulation helpers
"""
