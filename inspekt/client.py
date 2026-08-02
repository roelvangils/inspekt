"""
Client library for communicating with the Inspekt server.

Supports two transport mechanisms:
- Unix socket (default on macOS/Linux) - faster, more reliable
- HTTP (fallback, required for external access)

Transport selection is automatic based on platform, but can be
overridden via environment variable INSPEKT_TRANSPORT.
"""

import os
import time
from typing import Any

import requests

from inspekt.transport import (
    ConnectionError as TransportConnectionError,
)
from inspekt.transport import (
    Request,
    SyncUnixSocketTransport,
    get_socket_path,
)
from inspekt.transport import (
    TimeoutError as TransportTimeoutError,
)


def _verbose_log(message: str, data: Any = None) -> None:
    """Log verbose output if INSPEKT_VERBOSE is set."""
    if os.environ.get("INSPEKT_VERBOSE") != "1":
        return

    timestamp = time.strftime("%H:%M:%S")
    if data is not None:
        import sys

        print(f"[{timestamp}] {message}: {data}", file=sys.stderr)
    else:
        import sys

        print(f"[{timestamp}] {message}", file=sys.stderr)


def _use_socket_transport() -> bool:
    """Check if socket transport should be used.

    Returns True if:
    - INSPEKT_TRANSPORT is "unix" or "auto" (default)
    - Platform is not Windows
    - Socket file exists (server is running with socket enabled)
    """
    import platform

    transport = os.environ.get("INSPEKT_TRANSPORT", "auto")

    if transport == "http":
        return False

    if platform.system() == "Windows":
        return False

    # Check if socket exists (server running with socket enabled)
    socket_path = get_socket_path()
    return socket_path.exists()


class SocketClientMixin:
    """Mixin that adds socket transport support to BridgeClient.

    Provides socket-based implementations of core methods that can
    be used instead of HTTP when available.
    """

    _socket_transport: SyncUnixSocketTransport | None = None
    # Once a socket call fails within a client instance, stop retrying it.
    # A CLI invocation is one process, so this effectively means "if the
    # socket path misbehaves once, use HTTP for the rest of this command."
    _socket_unhealthy: bool = False

    def _get_socket_transport(self) -> SyncUnixSocketTransport:
        """Get or create socket transport (lazy initialization)."""
        if self._socket_transport is None:
            self._socket_transport = SyncUnixSocketTransport()
        return self._socket_transport

    def _mark_socket_unhealthy(self) -> None:
        """Flip the kill-switch so subsequent calls skip the socket entirely."""
        self._socket_unhealthy = True
        self._close_socket_transport()

    def _close_socket_transport(self) -> None:
        """Close the socket transport if open."""
        if self._socket_transport is not None:
            self._socket_transport.disconnect()
            self._socket_transport = None

    def _socket_health(self) -> dict[str, Any] | None:
        """Check server health via socket transport.

        Returns health data dict or None if unavailable.
        """
        try:
            transport = self._get_socket_transport()
            if not transport.is_connected():
                transport.connect()

            response = transport.send(Request(method="health", params={}), timeout=1.0)

            if response.success:
                return response.data
            return None
        except (TransportConnectionError, TransportTimeoutError):
            return None

    def _socket_run(
        self,
        code: str,
        timeout: float = 10.0,
        browser_index: int | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Execute code via socket transport.

        Args:
            code: JavaScript code to execute
            timeout: Timeout in seconds
            browser_index: Legacy numeric index (0-based)
            instance: Instance identifier (ID, alias, or index string)

        Returns:
            Dict with {"ok": bool, "request_id": str} on success

        Raises:
            ConnectionError: If socket connection fails
            RuntimeError: If server returns error
        """
        transport = self._get_socket_transport()
        if not transport.is_connected():
            transport.connect()

        params = {"code": code}
        if instance is not None:
            # New instance parameter takes precedence
            params["instance"] = instance
        elif browser_index is not None:
            params["browser_index"] = browser_index

        # Post-fix the server's socket `run` is fire-and-forget — it replies
        # with the request_id within milliseconds. Cap this low so a dead or
        # misconfigured socket is detected fast and falls back to HTTP.
        response = transport.send(Request(method="run", params=params), timeout=2.0)

        if not response.success:
            error = response.error or "unknown error"
            if error == "no_browser_connected":
                raise RuntimeError(
                    "No browser connected.\n\n"
                    "Make sure:\n"
                    "  • A browser with the Inspekt extension is open\n"
                    "  • The extension is enabled on the current page\n"
                    "  • The bridge server is running (`inspekt start`)"
                )
            elif error == "browser_not_responding":
                raise RuntimeError(
                    "Browser tab not responding.\n\n"
                    "The browser tab may be frozen or in the background.\n\n"
                    "Try:\n"
                    "  • Click on the browser tab to wake it up\n"
                    "  • Refresh the page\n"
                    "  • Check that the Inspekt extension is enabled"
                )
            elif error == "instance_not_found":
                message = (
                    response.data.get("message", f"Instance '{instance}' not found")
                    if response.data
                    else f"Instance '{instance}' not found"
                )
                raise RuntimeError(
                    f"{message}\n\n"
                    "The specified browser instance could not be found.\n\n"
                    "Use `inspekt instances` to list available browser instances."
                )
            else:
                raise RuntimeError(f"Failed to submit code: {error}")

        return response.data

    def _socket_result(self, request_id: str, timeout: float = 30.0) -> dict[str, Any]:
        """Get execution result via socket transport.

        Returns:
            The result dict from the browser

        Raises:
            ConnectionError: If socket connection fails
            TimeoutError: If result not received in time
        """
        transport = self._get_socket_transport()
        if not transport.is_connected():
            transport.connect()

        response = transport.send(
            Request(method="result", params={"request_id": request_id, "timeout": timeout}),
            timeout=timeout + 5,
        )

        if response.success:
            return response.data

        raise RuntimeError(response.error or "Failed to get result")


class BridgeClient(SocketClientMixin):
    """Client for communicating with Inspekt server."""

    def __init__(self, host: str = "127.0.0.1", port: int | None = None):
        # Allow override via environment variable (for VM isolation)
        # INSPEKT_BRIDGE_URL takes precedence, then INSPEKT_BRIDGE_PORT,
        # then auto-detect based on environment (VM vs normal)
        from inspekt.config import get_bridge_port

        env_url = os.environ.get("INSPEKT_BRIDGE_URL")
        env_port = os.environ.get("INSPEKT_BRIDGE_PORT")

        if env_url:
            self.base_url = env_url.rstrip("/")
            # Extract host/port from URL for compatibility
            from urllib.parse import urlparse

            parsed = urlparse(self.base_url)
            self.host = parsed.hostname or host
            self.port = parsed.port or get_bridge_port()
        else:
            if port is None:
                # Use env var if set, otherwise auto-detect based on environment
                port = int(env_port) if env_port else get_bridge_port()
            self.base_url = f"http://{host}:{port}"
            self.host = host
            self.port = port
        self.timeout = 5
        self._last_retry_result = None  # Store retry result for domain prompt flow
        self.quiet = False  # When True, suppress all warnings (for JSON output mode)
        # Use a session for connection pooling (prevents port exhaustion on long operations)
        self._session = requests.Session()

        # Track if socket transport should be used (auto-detected)
        self._use_socket = _use_socket_transport()
        _verbose_log(
            "BridgeClient initialized", f"use_socket={self._use_socket}, base_url={self.base_url}"
        )

    def _extract_domain(self, url: str) -> str | None:
        """Extract domain from URL."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            hostname = parsed.netloc or parsed.hostname
            if hostname and ":" in hostname:
                hostname = hostname.split(":")[0]
            return hostname
        except Exception:
            return None

    def _handle_domain_prompt(self, url: str, code: str, timeout: float) -> bool:
        """
        Handle domain authorization prompt.

        Returns True if domain was added and retry succeeded, False otherwise.
        """

        import click

        domain = self._extract_domain(url)
        if not domain:
            return False

        try:
            from inspekt.services.domain_service import get_domain_service, normalize_domain

            # Normalize domain (strip www. prefix)
            normalized = normalize_domain(domain)

            # Check if already allowed (might be a sync issue)
            domain_service = get_domain_service()
            if domain_service.is_allowed(normalized):
                # Domain is allowed in SQLite but browser doesn't know yet
                # Try to sync and retry
                self._sync_domains_to_browser()
                time.sleep(0.5)
                self._last_retry_result = self.execute(
                    code, timeout=timeout, _skip_domain_check=True
                )
                return self._last_retry_result.get("ok", False)

            # Prompt user
            click.echo(f"\nDomain '{normalized}' is not in the allowed list.", err=True)
            click.echo("", err=True)

            response = click.prompt(
                "Would you like to add it now? [Y/n]", type=str, default="Y", show_default=False
            )

            if response.lower() in ("n", "no"):
                click.echo("\nDomain not added. You can add it later with:", err=True)
                click.echo(f"  inspekt domain add {normalized}", err=True)
                click.echo("", err=True)
                click.echo("Or bypass all domain checks for 1 hour with:", err=True)
                click.echo("  inspekt yolo", err=True)
                return False

            # Add domain to SQLite
            result = domain_service.add_domain(normalized)
            if not result.get("ok"):
                click.echo("Error: Failed to add domain", err=True)
                return False

            stored_domain = result.get("domain", normalized)
            click.echo(f"✓ Domain added: {stored_domain}")

            # Sync to browser and wait for confirmation
            sync_ok = self._sync_domains_to_browser()
            if sync_ok:
                click.echo("✓ Synced to browser")
            else:
                click.echo("⚠ Browser sync pending (will retry)", err=True)
                # Give browser time to process the sync message
                # (sync message was sent but response timed out - browser may still be processing)
                time.sleep(1.0)

            click.echo("")

            # Retry execution
            # Use shorter timeout for retry since we just synced and browser should respond quickly
            retry_timeout = min(timeout, 15.0)
            self._last_retry_result = self.execute(
                code, timeout=retry_timeout, _skip_domain_check=True, _fast_poll=True
            )
            return self._last_retry_result.get("ok", False)

        except Exception as e:
            import click

            click.echo(f"Error handling domain prompt: {e}", err=True)
            return False

    def _sync_domains_to_browser(self) -> bool:
        """
        Sync domains from SQLite to browser extension.

        Returns True only if at least one browser confirmed the sync.
        This ensures the browser has actually updated its storage.
        """
        _verbose_log("Syncing domains to browser extension")
        try:
            from inspekt.services.domain_service import get_domain_service

            sync_start = time.time()
            domains = get_domain_service().get_domains_for_browser_sync()
            _verbose_log("Domains to sync", len(domains))
            response = self._session.post(
                f"{self.base_url}/domains/sync",
                json={"domains": domains},
                timeout=10.0,  # Wait for browser to confirm
            )
            _verbose_log(
                "Sync response",
                f"status={response.status_code}, time={time.time() - sync_start:.3f}s",
            )
            if response.status_code == 200:
                data = response.json()
                # Check browsers_synced > 0 for actual confirmation
                browsers_synced = data.get("browsers_synced", 0)
                _verbose_log("Browsers synced", browsers_synced)
                return data.get("ok", False) and browsers_synced > 0
            return False
        except Exception as e:
            _verbose_log("Sync failed", str(e))
            return False

    def is_alive(self) -> bool:
        """Check if bridge server is running.

        Uses socket transport when available, falls back to HTTP.
        """
        # Try socket first if available
        if self._use_socket and not self._socket_unhealthy:
            try:
                health = self._socket_health()
                if health is not None:
                    return True
            except Exception:
                pass
            # Socket failed, fall back to HTTP and stop retrying it.
            self._mark_socket_unhealthy()
            _verbose_log("Socket health check failed, trying HTTP")

        # HTTP fallback
        try:
            response = self._session.get(f"{self.base_url}/health", timeout=self.timeout)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_status(self) -> dict[str, Any] | None:
        """Get bridge server status.

        Uses socket transport when available, falls back to HTTP.
        """
        # Try socket first if available
        if self._use_socket and not self._socket_unhealthy:
            try:
                health = self._socket_health()
                if health is not None:
                    return health
            except Exception:
                pass
            self._mark_socket_unhealthy()
            _verbose_log("Socket status check failed, trying HTTP")

        # HTTP fallback
        try:
            response = self._session.get(f"{self.base_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        return None

    def get_current_browser_index(self) -> int | None:
        """Get the index of the most recently active browser.

        Returns the 0-based index of the browser that is currently
        marked as most_recent in the bridge server, or None if no
        browser is connected.
        """
        status = self.get_status()
        if not status:
            return None

        browsers = status.get("browsers", [])
        for i, browser in enumerate(browsers):
            if browser.get("is_most_recent"):
                return i
        return 0 if browsers else None

    def get_browser_count(self) -> int:
        """Get the number of connected browsers."""
        status = self.get_status()
        if not status:
            return 0
        return status.get("connected_browsers", 0)

    def execute(
        self,
        code: str,
        timeout: float = 10.0,
        _skip_domain_check: bool = False,
        browser_index: int | None = None,
        _fast_poll: bool = False,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute JavaScript code in the browser and wait for result.

        Args:
            code: JavaScript code to execute
            timeout: Maximum time to wait for result in seconds
            _skip_domain_check: Internal flag to prevent recursion during domain check
            browser_index: Optional index of specific browser to target (0-based).
                          If None, uses the most recently active browser.
            _fast_poll: Internal flag to use shorter poll timeout (for domain retry scenarios)
            instance: Optional instance identifier (ID, alias, or index string).
                     Takes precedence over browser_index. Can also be set via
                     INSPEKT_INSTANCE environment variable.

        Returns:
            Dictionary with execution result

        Raises:
            ConnectionError: If bridge server is not running
            TimeoutError: If execution takes longer than timeout
            RuntimeError: If code execution fails in browser
        """
        # Check for instance from environment variable if not provided
        if instance is None:
            instance = os.environ.get("INSPEKT_INSTANCE")

        _verbose_log(
            "BridgeClient.execute() called",
            {
                "timeout": timeout,
                "code_length": len(code),
                "browser_index": browser_index,
                "instance": instance,
                "fast_poll": _fast_poll,
                "use_socket": self._use_socket,
            },
        )

        # Try socket transport first (faster, more reliable)
        if self._use_socket and not self._socket_unhealthy and not _skip_domain_check:
            try:
                _verbose_log("Using socket transport")
                start_time = time.time()

                # Submit code via socket
                run_result = self._socket_run(
                    code, timeout=timeout, browser_index=browser_index, instance=instance
                )
                request_id = run_result.get("request_id")

                if not request_id:
                    raise RuntimeError("No request_id returned from server")

                _verbose_log("Socket run succeeded", f"request_id={request_id}")

                # Get result via socket
                remaining_timeout = max(timeout - (time.time() - start_time), 1.0)
                result = self._socket_result(request_id, timeout=remaining_timeout)

                _verbose_log(
                    "Socket result received",
                    f"time={time.time() - start_time:.3f}s, status={result.get('status')}",
                )

                # Handle domain authorization error (needs HTTP for domain prompt flow)
                if not result.get("ok"):
                    error_msg = str(result.get("error", "")).lower()
                    is_domain_error = any(
                        phrase in error_msg
                        for phrase in [
                            "not allowed to access this domain",
                            "domain not authorized",
                            "not authorized",
                        ]
                    )
                    if is_domain_error:
                        _verbose_log("Domain error detected, falling back to HTTP for prompt flow")
                        # Fall through to HTTP to handle domain prompt
                    else:
                        return result

                # Check for pending status (need to poll more)
                if result.get("status") == "pending":
                    # Continue polling via socket
                    while time.time() - start_time < timeout:
                        remaining = max(timeout - (time.time() - start_time), 1.0)
                        result = self._socket_result(request_id, timeout=min(remaining, 5.0))
                        if result.get("status") != "pending":
                            break
                        time.sleep(0.5)

                return result

            except (TransportConnectionError, TransportTimeoutError) as e:
                _verbose_log("Socket transport failed, falling back to HTTP", str(e))
                self._mark_socket_unhealthy()
                # Fall through to HTTP implementation
            except RuntimeError:
                # Re-raise RuntimeError (browser errors) as-is
                raise
            except Exception as e:
                _verbose_log("Socket transport unexpected error", str(e))
                self._mark_socket_unhealthy()
                # Fall through to HTTP implementation

        # HTTP implementation (fallback or primary when socket not available)
        # For fast_poll mode, skip the health check to minimize latency
        if not _fast_poll:
            if not self.is_alive():
                raise ConnectionError("Bridge server is not running. Start it with: inspekt start")

        # Submit code
        try:
            # Use execution timeout + buffer for HTTP request (not the 5s default)
            # This allows slow operations to complete
            # For fast_poll mode, use the raw timeout (fail fast on pre-validation checks)
            http_timeout = timeout if _fast_poll else timeout + 5
            _verbose_log(
                "Submitting code to bridge",
                f"POST {self.base_url}/run, http_timeout={http_timeout}",
            )
            submit_start = time.time()

            # Build request payload
            payload = {"code": code}
            if instance is not None:
                # New instance parameter takes precedence
                payload["instance"] = instance
            elif browser_index is not None:
                payload["browser_index"] = browser_index

            response = self._session.post(
                f"{self.base_url}/run", json=payload, timeout=http_timeout
            )
            _verbose_log(
                "Code submitted",
                f"status={response.status_code}, time={time.time() - submit_start:.3f}s",
            )

            # Parse JSON first to get detailed error messages (before raise_for_status)
            try:
                data = response.json()
            except ValueError:
                # If we can't parse JSON, fall back to HTTP error handling
                response.raise_for_status()
                raise RuntimeError("Invalid response from server")

            if not data.get("ok"):
                error = data.get("error", "unknown error")

                # Handle specific error types with helpful messages
                if error == "browser_not_responding":
                    raise RuntimeError(
                        "Browser tab not responding.\n\n"
                        "The browser tab may be frozen or in the background.\n\n"
                        "Try:\n"
                        "  • Click on the browser tab to wake it up\n"
                        "  • Refresh the page\n"
                        "  • Check that the Inspekt extension is enabled"
                    )
                elif error == "no_browser_connected":
                    raise RuntimeError(
                        "No browser connected.\n\n"
                        "Make sure:\n"
                        "  • A browser with the Inspekt extension is open\n"
                        "  • The extension is enabled on the current page\n"
                        "  • The bridge server is running (`inspekt start`)"
                    )
                elif error == "instance_not_found":
                    message = data.get("message", f"Instance '{instance}' not found")
                    raise RuntimeError(
                        f"{message}\n\n"
                        "The specified browser instance could not be found.\n\n"
                        "Use `inspekt instances` to list available browser instances."
                    )
                else:
                    raise RuntimeError(f"Failed to submit code: {error}")

            request_id = data["request_id"]
            _verbose_log("Request ID assigned", request_id)
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to submit code: {e}")

        # Poll for result (server does long polling, so we don't need to poll frequently)
        _verbose_log("Starting to poll for result")
        start_time = time.time()
        csp_checked = False
        poll_count = 0

        while time.time() - start_time < timeout:
            poll_count += 1
            try:
                # Calculate remaining timeout for this request
                # IMPORTANT: HTTP request timeout must respect the overall operation timeout
                # to prevent indefinite hangs when the bridge is unresponsive
                remaining_time = timeout - (time.time() - start_time)
                if remaining_time <= 0:
                    break  # Overall timeout exceeded, exit the loop

                # Use shorter minimum timeout for domain retry scenarios (browser should respond quickly)
                # For quick checks (pre-validation), use remaining time directly (fail fast)
                if _fast_poll:
                    request_timeout = max(
                        remaining_time + 1, 2
                    )  # At least 2s, but respect overall timeout
                else:
                    # Use remaining time + small buffer, with reasonable min/max bounds
                    # Min of 5s to allow for network latency, but cap at remaining_time + 5s
                    # to ensure we don't hang past the overall timeout
                    request_timeout = max(min(remaining_time + 5, 60), 5)

                response = self._session.get(
                    f"{self.base_url}/result",
                    params={"request_id": request_id},
                    timeout=request_timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "unknown")

                    if status == "completed":
                        _verbose_log(
                            f"Result received (poll #{poll_count})",
                            f"time={time.time() - start_time:.3f}s, ok={data.get('ok')}",
                        )

                    # Check if result contains CSP error
                    if data.get("status") == "completed" and not data.get("ok"):
                        error = data.get("error", "")

                        # Check if CSP bypass was auto-enabled (yolo mode)
                        if "CSP_AUTO_ENABLED" in error:
                            _verbose_log("CSP bypass auto-enabled, refreshing page and retrying…")
                            # Reload the page to apply CSP bypass
                            try:
                                self._session.post(
                                    f"{self.base_url}/execute",
                                    json={"code": "location.reload()"},
                                    timeout=5.0,
                                )
                                # Wait for page to reload
                                time.sleep(2.0)
                                # Retry the original request
                                return self.run(code, timeout=timeout)
                            except Exception as reload_error:
                                _verbose_log(f"Auto-reload failed: {reload_error}")
                                # Fall through to regular CSP error

                        # Check for CSP_BLOCKED error (user needs to enable bypass manually)
                        if "CSP_BLOCKED" in error:
                            raise RuntimeError(
                                "Content Security Policy (CSP) blocks JavaScript execution on this page.\n\n"
                                "Solutions:\n"
                                "  • Run `inspekt yolo` to bypass all restrictions (recommended)\n"
                                "  • Run `inspekt domain csp <domain> --enable` then refresh the page\n"
                                "  • Enable CSP Bypass in the extension popup, then refresh\n\n"
                                f"Technical details: {error[:200]}"
                            )

                        # Legacy CSP error handling
                        if "EvalError" in error or "Content Security Policy" in error:
                            raise RuntimeError(
                                "Content Security Policy (CSP) blocks JavaScript execution on this page.\n\n"
                                "This website has security restrictions that prevent eval() and dynamic code execution.\n\n"
                                "Solutions:\n"
                                "  • Run `inspekt yolo` to bypass all restrictions\n"
                                "  • Run `inspekt domain csp <domain> --enable` then refresh the page\n"
                                "  • Check browser console (F12) for Inspekt CSP warnings\n\n"
                                f"Current site: {data.get('url', 'unknown')}\n\n"
                                f"Technical details: {error[:200]}"
                            )

                    if data.get("status") == "pending":
                        if poll_count == 1:
                            _verbose_log("Waiting for browser response (pending)")
                        # Check for CSP blocking (after 2 seconds of waiting)
                        if not csp_checked and time.time() - start_time > 2.0:
                            csp_checked = True
                            try:
                                # Try to read CSP flag from browser
                                csp_check = self._session.post(
                                    f"{self.base_url}/run",
                                    json={"code": "window.__INSPEKT_BRIDGE_CSP_BLOCKED__"},
                                    timeout=self.timeout,
                                )
                                if csp_check.status_code == 200:
                                    check_data = csp_check.json()
                                    check_id = check_data.get("request_id")

                                    # Quick poll for CSP check result
                                    time.sleep(0.5)
                                    csp_result = self._session.get(
                                        f"{self.base_url}/result",
                                        params={"request_id": check_id},
                                        timeout=self.timeout,
                                    )

                                    if csp_result.status_code == 200:
                                        csp_data = csp_result.json()
                                        if csp_data.get("status") == "completed" and csp_data.get(
                                            "result"
                                        ):
                                            raise RuntimeError(
                                                "Content Security Policy (CSP) is blocking Inspekt on this site.\n\n"
                                                "This website has security restrictions that prevent WebSocket connections "
                                                "to localhost.\n\n"
                                                "Common affected sites: GitHub, Gmail, banking sites, government portals.\n\n"
                                                "Solutions:\n"
                                                "  • Test Inspekt on other websites without strict CSP\n"
                                                "  • Check browser console (F12) for detailed CSP warnings\n"
                                                "  • Read troubleshooting guide: https://roelvangils.github.io/inspekt/troubleshooting/csp-issues/\n\n"
                                                f"Current site: {csp_data.get('url', 'unknown')}"
                                            )
                            except (requests.RequestException, KeyError):
                                pass  # CSP check failed, continue with timeout

                        # Still waiting - server uses long polling so we just need a small delay
                        # before retrying (server holds connection until result ready or timeout)
                        time.sleep(0.5)
                        continue

                    # Check for domain authorization error and prompt user
                    if not _skip_domain_check and not data.get("ok"):
                        error_msg = data.get("error", "").lower()
                        is_domain_error = any(
                            phrase in error_msg
                            for phrase in [
                                "not allowed to access this domain",
                                "domain not authorized",
                                "not authorized",
                            ]
                        )

                        if is_domain_error:
                            _verbose_log(
                                "Domain authorization error detected", data.get("url", "unknown")
                            )
                            url = data.get("url", "")
                            if url and self._handle_domain_prompt(url, code, timeout):
                                # User added domain, retry was successful
                                # The retry result is returned by _handle_domain_prompt
                                return self._last_retry_result
                            # User declined or retry failed, return original error

                    return data

            except requests.RequestException as e:
                raise ConnectionError(f"Failed to get result: {e}")

        _verbose_log(
            f"Timeout after {poll_count} polls", f"elapsed={time.time() - start_time:.3f}s"
        )
        raise TimeoutError(f"No response from browser after {timeout} seconds.")

    def execute_file(self, filepath: str, timeout: float = 10.0) -> dict[str, Any]:
        """
        Execute JavaScript from a file.

        Args:
            filepath: Path to JavaScript file
            timeout: Maximum time to wait for result in seconds

        Returns:
            Dictionary with execution result
        """
        with open(filepath, encoding="utf-8") as f:
            code = f.read()
        return self.execute(code, timeout)

    def enable_replay_mode(self, visual_script: str, timeout: float = 10.0) -> dict[str, Any]:
        """
        Enable replay mode in the browser extension.

        When enabled, the extension auto-injects the visual script on every page load.
        This eliminates the need for Python to poll and inject after navigation.

        Args:
            visual_script: The visual script content to inject on page loads
            timeout: Maximum time to wait for response in seconds

        Returns:
            Dictionary with result (ok, enabled, message)
        """
        url = f"{self.base_url}/replay/enable"
        try:
            response = self._session.post(
                url, json={"visualScript": visual_script}, timeout=timeout
            )
            return response.json()
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Request timed out"}
        except requests.exceptions.ConnectionError:
            return {"ok": False, "error": "Cannot connect to bridge server"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def disable_replay_mode(self, timeout: float = 10.0) -> dict[str, Any]:
        """
        Disable replay mode in the browser extension.

        Args:
            timeout: Maximum time to wait for response in seconds

        Returns:
            Dictionary with result (ok, enabled, message)
        """
        url = f"{self.base_url}/replay/disable"
        try:
            response = self._session.post(url, timeout=timeout)
            return response.json()
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Request timed out"}
        except requests.exceptions.ConnectionError:
            return {"ok": False, "error": "Cannot connect to bridge server"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_replay_mode_status(self, timeout: float = 5.0) -> dict[str, Any]:
        """
        Get replay mode status from the browser extension.

        Args:
            timeout: Maximum time to wait for response in seconds

        Returns:
            Dictionary with result (ok, enabled, hasScript)
        """
        url = f"{self.base_url}/replay/status"
        try:
            response = self._session.get(url, timeout=timeout)
            return response.json()
        except requests.exceptions.Timeout:
            return {"ok": False, "error": "Request timed out"}
        except requests.exceptions.ConnectionError:
            return {"ok": False, "error": "Cannot connect to bridge server"}
        except Exception as e:
            return {"ok": False, "error": str(e)}
