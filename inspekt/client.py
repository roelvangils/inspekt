"""
Client library for communicating with the Inspekt server.
"""

import os
import re
import time
from pathlib import Path
from typing import Any

import requests


def _verbose_log(message: str, data: Any = None) -> None:
    """Log verbose output if INSPEKT_VERBOSE is set."""
    if os.environ.get('INSPEKT_VERBOSE') != '1':
        return

    timestamp = time.strftime('%H:%M:%S')
    if data is not None:
        import sys
        print(f"[{timestamp}] {message}: {data}", file=sys.stderr)
    else:
        import sys
        print(f"[{timestamp}] {message}", file=sys.stderr)


def get_expected_userscript_version() -> str | None:
    """
    Read the expected userscript version from userscript_ws.js file.

    Returns:
        Version string (e.g., '3.2') or None if file not found
    """
    # Try to find userscript_ws.js in the project directory
    # Look in common locations relative to this file
    current_dir = Path(__file__).parent.parent  # Go up from zen/ to project root
    userscript_path = current_dir / "userscript_ws.js"

    if not userscript_path.exists():
        # Try current working directory
        userscript_path = Path.cwd() / "userscript_ws.js"

    if not userscript_path.exists():
        return None

    try:
        with open(userscript_path) as f:
            content = f.read()
            # Look for @version or window.__ZEN_BRIDGE_VERSION__
            # Try @version first (from userscript header)
            version_match = re.search(r"@version\s+(\S+)", content)
            if version_match:
                return version_match.group(1)

            # Try window.__ZEN_BRIDGE_VERSION__ as fallback
            version_match = re.search(
                r'window\.__ZEN_BRIDGE_VERSION__\s*=\s*[\'"]([^\'"]+)[\'"]', content
            )
            if version_match:
                return version_match.group(1)
    except Exception:
        pass

    return None


class BridgeClient:
    """Client for communicating with Inspekt server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.base_url = f"http://{host}:{port}"
        self.host = host
        self.port = port
        self.timeout = 5
        self._version_checked = False  # Track if we've already shown version warning
        self._cached_version = None  # Cache the version to avoid multiple requests
        self._last_retry_result = None  # Store retry result for domain prompt flow
        # Use a session for connection pooling (prevents port exhaustion on long operations)
        self._session = requests.Session()

    def _extract_domain(self, url: str) -> str | None:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            hostname = parsed.netloc or parsed.hostname
            if hostname and ':' in hostname:
                hostname = hostname.split(':')[0]
            return hostname
        except Exception:
            return None

    def _handle_domain_prompt(self, url: str, code: str, timeout: float) -> bool:
        """
        Handle domain authorization prompt.

        Returns True if domain was added and retry succeeded, False otherwise.
        """
        import sys
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
                self._last_retry_result = self.execute(code, timeout=timeout, _skip_domain_check=True)
                return self._last_retry_result.get("ok", False)

            # Prompt user
            click.echo(f"\nDomain '{normalized}' is not in the allowed list.", err=True)
            click.echo("", err=True)

            response = click.prompt(
                "Would you like to add it now? [Y/n]",
                type=str,
                default="Y",
                show_default=False
            )

            if response.lower() in ('n', 'no'):
                click.echo(f"\nDomain not added. You can add it later with:", err=True)
                click.echo(f"  inspekt domain add {normalized}", err=True)
                click.echo("", err=True)
                click.echo("Or temporarily allow all domains with:", err=True)
                click.echo("  inspekt domain bypass [DURATION IN MINUTES]", err=True)
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

            click.echo("")

            # Give browser time to update its internal state
            time.sleep(1.0)

            # Retry execution
            self._last_retry_result = self.execute(code, timeout=timeout, _skip_domain_check=True)
            return self._last_retry_result.get("ok", False)

        except Exception as e:
            import click
            click.echo(f"Error handling domain prompt: {e}", err=True)
            return False

    def _sync_domains_to_browser(self) -> bool:
        """Sync domains from SQLite to browser extension. Returns True if successful."""
        _verbose_log("Syncing domains to browser extension")
        try:
            from inspekt.services.domain_service import get_domain_service
            sync_start = time.time()
            domains = get_domain_service().get_domains_for_browser_sync()
            _verbose_log(f"Domains to sync", len(domains))
            response = self._session.post(
                f"{self.base_url}/domains/sync",
                json={"domains": domains},
                timeout=10.0  # Wait for browser to confirm
            )
            _verbose_log("Sync response", f"status={response.status_code}, time={time.time() - sync_start:.3f}s")
            if response.status_code == 200:
                data = response.json()
                return data.get("ok", False)
            return False
        except Exception as e:
            _verbose_log("Sync failed", str(e))
            return False

    def is_alive(self) -> bool:
        """Check if bridge server is running."""
        try:
            response = self._session.get(f"{self.base_url}/health", timeout=self.timeout)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def get_status(self) -> dict[str, Any] | None:
        """Get bridge server status."""
        try:
            response = self._session.get(f"{self.base_url}/health", timeout=self.timeout)
            if response.status_code == 200:
                return response.json()
        except requests.RequestException:
            pass
        return None

    def get_userscript_version(self) -> str | None:
        """Get installed userscript version from browser."""
        # Return cached version if available
        if self._cached_version:
            return self._cached_version

        try:
            # Support both new (INSPEKT) and legacy (ZEN) variable names
            result = self.execute("window.__INSPEKT_BRIDGE_VERSION__ || window.__ZEN_BRIDGE_VERSION__ || 'unknown'", timeout=2.0)
            if result.get("ok"):
                self._cached_version = result.get("result")
                return self._cached_version
        except Exception:
            pass
        return None

    def check_userscript_version(self, show_warning: bool = True) -> str | None:
        """
        Check if browser userscript/extension version matches expected version.

        Args:
            show_warning: If True, print warning to stderr when versions don't match

        Returns:
            Warning message if versions don't match, None if they match or check fails
        """
        if self._version_checked:
            return None  # Already checked this session

        self._version_checked = True

        try:
            expected_version = get_expected_userscript_version()
            if not expected_version:
                return None  # Can't find userscript file, skip check

            # Get installed version and check if using extension
            # Support both new (INSPEKT) and legacy (ZEN) variable names
            try:
                response = self._session.post(
                    f"{self.base_url}/run",
                    json={"code": "(window.__INSPEKT_BRIDGE_VERSION__ || window.__ZEN_BRIDGE_VERSION__ || 'unknown') + '|' + ((window.__INSPEKT_BRIDGE_EXTENSION__ || window.__ZEN_BRIDGE_EXTENSION__) ? 'ext' : 'user')"},
                    timeout=self.timeout,
                )
                response.raise_for_status()
                data = response.json()
                request_id = data.get("request_id")

                # Poll for result (short timeout)
                for _ in range(10):  # Max 1 second
                    result_response = self._session.get(
                        f"{self.base_url}/result",
                        params={"request_id": request_id},
                        timeout=self.timeout,
                    )
                    if result_response.status_code == 200:
                        result = result_response.json()
                        if result.get("ok"):
                            result_str = result.get("result", "unknown|user")
                            installed_version, install_type = result_str.split("|") if "|" in result_str else (result_str, "user")
                            # Cache the version
                            self._cached_version = installed_version
                            break
                    time.sleep(0.1)
                else:
                    return None  # Timeout getting version
            except Exception:
                return None  # Failed to get version

            # Extension version 4.x.x is always compatible (no version check needed)
            if install_type == "ext":
                if installed_version.startswith("4."):
                    return None  # Extension is compatible, no warning
                elif not installed_version or installed_version == "unknown":
                    # Extension detected but version unknown - still OK
                    return None  # Extension bypasses version check

            if not installed_version or installed_version == "unknown":
                # Userscript not installed or old version without version variable
                warning = (
                    f"\n⚠️  WARNING: Could not detect userscript version in browser.\n"
                    f"   Expected version: {expected_version}\n"
                    f"   Please update your userscript from: userscript_ws.js\n"
                )
                if show_warning:
                    import sys

                    print(warning, file=sys.stderr)
                return warning

            if installed_version != expected_version:
                warning = (
                    f"\n⚠️  WARNING: Userscript version mismatch!\n"
                    f"   Installed: {installed_version}\n"
                    f"   Expected:  {expected_version}\n"
                    f"   Please update your userscript from: userscript_ws.js\n"
                )
                if show_warning:
                    import sys

                    print(warning, file=sys.stderr)
                return warning

        except Exception:
            pass  # Silently ignore errors in version check

        return None  # Versions match or check failed

    def execute(self, code: str, timeout: float = 10.0, _skip_domain_check: bool = False) -> dict[str, Any]:
        """
        Execute JavaScript code in the browser and wait for result.

        Args:
            code: JavaScript code to execute
            timeout: Maximum time to wait for result in seconds
            _skip_domain_check: Internal flag to prevent recursion during domain check

        Returns:
            Dictionary with execution result

        Raises:
            ConnectionError: If bridge server is not running
            TimeoutError: If execution takes longer than timeout
            RuntimeError: If code execution fails in browser
        """
        _verbose_log("BridgeClient.execute() called", {"timeout": timeout, "code_length": len(code)})

        if not self.is_alive():
            raise ConnectionError("Bridge server is not running. Start it with: inspekt start")

        # Check userscript version on first execute (only once per client instance)
        if not self._version_checked:
            self.check_userscript_version(show_warning=True)

        # Submit code
        try:
            # Use execution timeout + buffer for HTTP request (not the 5s default)
            # This allows slow operations to complete
            http_timeout = timeout + 5
            _verbose_log("Submitting code to bridge", f"POST {self.base_url}/run")
            submit_start = time.time()
            response = self._session.post(
                f"{self.base_url}/run", json={"code": code}, timeout=http_timeout
            )
            response.raise_for_status()
            data = response.json()
            _verbose_log("Code submitted", f"status={response.status_code}, time={time.time() - submit_start:.3f}s")

            if not data.get("ok"):
                raise RuntimeError(f"Failed to submit code: {data.get('error')}")

            request_id = data["request_id"]
            _verbose_log("Request ID assigned", request_id)
        except requests.RequestException as e:
            raise ConnectionError(f"Failed to submit code: {e}")

        # Poll for result (server does long polling, so we don't need to poll frequently)
        _verbose_log("Starting to poll for result")
        start_time = time.time()
        poll_interval = 1.0  # Server does long polling, so 1s between polls is fine
        csp_checked = False
        poll_count = 0

        while time.time() - start_time < timeout:
            poll_count += 1
            try:
                # Calculate remaining timeout for this request
                # Server does long polling up to 180s, so set HTTP timeout accordingly
                remaining_time = timeout - (time.time() - start_time)
                request_timeout = max(remaining_time + 10, 30)  # At least 30 seconds for long poll

                response = self._session.get(
                    f"{self.base_url}/result",
                    params={"request_id": request_id},
                    timeout=request_timeout,
                )

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status", "unknown")

                    if status == "completed":
                        _verbose_log(f"Result received (poll #{poll_count})", f"time={time.time() - start_time:.3f}s, ok={data.get('ok')}")

                    # Check if result contains CSP error
                    if data.get("status") == "completed" and not data.get("ok"):
                        error = data.get("error", "")
                        if "EvalError" in error or "Content Security Policy" in error:
                            raise RuntimeError(
                                "Content Security Policy (CSP) blocks JavaScript execution on this page.\n\n"
                                "This website has security restrictions that prevent eval() and dynamic code execution.\n\n"
                                "Common affected sites: GitHub, Gmail, banking sites, government portals, extension pages.\n\n"
                                "Solutions:\n"
                                "  • Navigate to a different website without strict CSP\n"
                                "  • Test on simple sites like example.com or wikipedia.org\n"
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
                                    json={"code": "window.__ZEN_BRIDGE_CSP_BLOCKED__"},
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
                                        if csp_data.get("status") == "completed" and csp_data.get("result") == True:
                                            raise RuntimeError(
                                                "Content Security Policy (CSP) is blocking Inspekt on this site.\n\n"
                                                "This website has security restrictions that prevent WebSocket connections "
                                                "to localhost.\n\n"
                                                "Common affected sites: GitHub, Gmail, banking sites, government portals.\n\n"
                                                "Solutions:\n"
                                                "  • Test Inspekt on other websites without strict CSP\n"
                                                "  • Check browser console (F12) for detailed CSP warnings\n"
                                                "  • Read troubleshooting guide: https://roelvangils.github.io/zen-bridge/troubleshooting/csp-issues/\n\n"
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
                        is_domain_error = any(phrase in error_msg for phrase in [
                            "not allowed to access this domain",
                            "domain not authorized",
                            "not authorized"
                        ])

                        if is_domain_error:
                            _verbose_log("Domain authorization error detected", data.get("url", "unknown"))
                            url = data.get("url", "")
                            if url and self._handle_domain_prompt(url, code, timeout):
                                # User added domain, retry was successful
                                # The retry result is returned by _handle_domain_prompt
                                return self._last_retry_result
                            # User declined or retry failed, return original error

                    return data

            except requests.RequestException as e:
                raise ConnectionError(f"Failed to get result: {e}")

        _verbose_log(f"Timeout after {poll_count} polls", f"elapsed={time.time() - start_time:.3f}s")
        raise TimeoutError(
            f"No response from browser after {timeout} seconds.\n\n"
            "Possible causes:\n"
            "  • No browser tab is open with the userscript active\n"
            "  • Content Security Policy (CSP) is blocking the connection\n"
            "  • Browser userscript manager (Tampermonkey/Violentmonkey) is disabled\n\n"
            "Troubleshooting:\n"
            "  • Open browser console (F12) and check for Inspekt messages\n"
            "  • Look for CSP warnings in red/orange\n"
            "  • Verify: inspekt status\n"
            "  • Read: https://roelvangils.github.io/zen-bridge/troubleshooting/csp-issues/"
        )

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
