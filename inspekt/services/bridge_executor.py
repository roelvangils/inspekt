"""
Bridge Executor Service - Standardized execution flow for browser commands.

This service wraps the BridgeClient to provide:
- Consistent error handling
- Retry logic with exponential backoff
- Result formatting and validation
- Version checking
- Connection pooling (future enhancement)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import click

from inspekt.client import BridgeClient


def _verbose_log(message: str, data: Any = None) -> None:
    """Log verbose output if INSPEKT_VERBOSE is set."""
    if os.environ.get('INSPEKT_VERBOSE') != '1':
        return

    timestamp = time.strftime('%H:%M:%S')
    if data is not None:
        click.echo(f"[{timestamp}] {message}: {data}", err=True)
    else:
        click.echo(f"[{timestamp}] {message}", err=True)


class BridgeExecutor:
    """Service for executing commands via the bridge with standardized error handling."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        max_retries: int = 3,
        retry_delay: float = 0.5,
    ):
        """
        Initialize the bridge executor.

        Args:
            host: Bridge server host (default: localhost)
            port: Bridge server port (default: 8765)
            max_retries: Maximum number of retry attempts on transient failures
            retry_delay: Initial delay between retries in seconds (exponential backoff)
        """
        self.host = host
        self.port = port
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client: BridgeClient | None = None

    @property
    def client(self) -> BridgeClient:
        """Lazy-initialize the bridge client."""
        if self._client is None:
            self._client = BridgeClient(host=self.host, port=self.port)
        return self._client

    def is_server_running(self) -> bool:
        """
        Check if bridge server is running.

        Returns:
            True if server is alive, False otherwise
        """
        return self.client.is_alive()

    def ensure_server_running(self) -> None:
        """
        Ensure bridge server is running, exit with error if not.

        Exits:
            sys.exit(1) if server is not running
        """
        if not self.is_server_running():
            click.echo(
                "Error: Bridge server is not running. Start it with: inspekt start",
                err=True,
            )
            sys.exit(1)

    def has_active_browser_connection(self) -> bool:
        """
        Check if there are any browser connections.

        Note: This only checks if browsers are connected via WebSocket.
        It cannot detect if the browser tab is inactive or unresponsive.

        Returns:
            True if at least one browser is connected, False otherwise
        """
        status = self.get_status()
        if status is None:
            return False

        # Simply check if any browsers are connected
        return status.get("connected_browsers", 0) > 0

    def execute(
        self,
        code: str,
        timeout: float = 10.0,
        retry_on_timeout: bool = False,
        skip_domain_check: bool = False,
    ) -> dict[str, Any]:
        """
        Execute JavaScript code in browser with error handling and optional retries.

        Args:
            code: JavaScript code to execute
            timeout: Maximum time to wait for result in seconds
            retry_on_timeout: If True, retry on TimeoutError
            skip_domain_check: If True, skip the pre-execution domain check

        Returns:
            Dictionary with execution result:
            {
                "ok": bool,
                "result": Any,  # Present if ok=True
                "error": str,   # Present if ok=False
                "url": str,     # Present for some commands
                "title": str,   # Present for some commands
            }

        Raises:
            SystemExit: If execution fails after retries
        """
        _verbose_log("Starting execution", {"timeout": timeout, "retry_on_timeout": retry_on_timeout})
        start_time = time.time()

        self.ensure_server_running()
        _verbose_log("Server check passed", f"{time.time() - start_time:.3f}s")

        # Check for active browser connections immediately
        if not self.has_active_browser_connection():
            click.echo(
                "Error: Request timeout. Please ensure the extension is installed in Firefox and/or Chrome, and that the Inspekt Panel is visible.",
                err=True,
            )
            sys.exit(1)
        _verbose_log("Browser connection check passed", f"{time.time() - start_time:.3f}s")

        # Fast domain pre-check (avoids long timeout on unauthorized domains)
        if not skip_domain_check:
            _verbose_log("Checking domain permission")
            if not self._check_domain_and_prompt():
                # User declined to add domain
                sys.exit(1)
            _verbose_log("Domain check passed", f"{time.time() - start_time:.3f}s")

        retries = self.max_retries if retry_on_timeout else 1
        delay = self.retry_delay

        for attempt in range(retries):
            try:
                _verbose_log(f"Sending code to browser (attempt {attempt + 1}/{retries})")
                exec_start = time.time()
                result = self.client.execute(code, timeout=timeout)
                _verbose_log(f"Execution completed", f"{time.time() - exec_start:.3f}s")

                # Check if this is a domain permission error (fallback for edge cases)
                if not result.get("ok"):
                    error_msg = result.get("error", "").lower()
                    # Check for various forms of domain authorization errors
                    is_domain_error = any(phrase in error_msg for phrase in [
                        "domain not authorized",
                        "not allowed to access this domain",
                        "not authorized",
                        "domain is not in the allowed list"
                    ])

                    if is_domain_error:
                        # Extract domain from URL
                        url = result.get("url", "")
                        domain = self._extract_domain_from_url(url)

                        if domain and self._prompt_add_domain(domain):
                            # User agreed to add domain, retry execution
                            # Sync confirmation already handled in _prompt_add_domain
                            result = self.client.execute(code, timeout=timeout)

                _verbose_log("Total execution time", f"{time.time() - start_time:.3f}s")
                _verbose_log("Result status", {"ok": result.get("ok"), "has_error": "error" in result})
                return result

            except TimeoutError as e:
                if attempt < retries - 1:
                    click.echo(
                        f"Timeout on attempt {attempt + 1}/{retries}, retrying in {delay:.1f}s...",
                        err=True,
                    )
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff
                    continue
                else:
                    click.echo(f"Error: {e}", err=True)
                    sys.exit(1)

            except (ConnectionError, RuntimeError) as e:
                click.echo(f"Error: {e}", err=True)
                sys.exit(1)

        # Should not reach here
        click.echo("Error: Execution failed after retries", err=True)
        sys.exit(1)

    def _extract_domain_from_url(self, url: str) -> str | None:
        """Extract domain from URL."""
        from urllib.parse import urlparse

        try:
            parsed = urlparse(url)
            hostname = parsed.netloc or parsed.hostname
            # Remove port if present
            if hostname and ':' in hostname:
                hostname = hostname.split(':')[0]
            return hostname
        except Exception:
            return None

    def _is_domain_allowed(self, domain: str) -> bool:
        """Check if domain is in the allowed list (SQLite) or yolo mode is active."""
        from inspekt.services.domain_service import get_domain_service

        try:
            service = get_domain_service()
            # is_allowed() already checks yolo mode first
            return service.is_allowed(domain)
        except Exception:
            return True  # Assume allowed on error

    def _quick_get_current_domain(self) -> str | None:
        """
        Quickly get the current page domain (2s timeout).

        Returns domain string or None if unable to retrieve.
        """
        _verbose_log("Getting current domain (quick check)")
        try:
            result = self.client.execute("location.href", timeout=2.0)
            if result.get("ok"):
                # Successful execution - URL is in result
                url = result.get("result", "")
                domain = self._extract_domain_from_url(url)
                _verbose_log("Current domain", domain)
                return domain
            else:
                # Execution blocked (e.g., domain not authorized)
                # URL is still returned in the response
                url = result.get("url", "")
                if url:
                    domain = self._extract_domain_from_url(url)
                    _verbose_log("Current domain (from blocked response)", domain)
                    return domain
        except Exception as e:
            _verbose_log("Failed to get current domain", str(e))
        return None

    def _check_domain_and_prompt(self) -> bool:
        """
        Check if current domain is allowed, prompt to add if not.

        In isolated mode (Docker VM), always returns True without prompting.

        Returns:
            True if domain is allowed (or was added), False if user declined
        """
        # In isolated mode, skip all domain checks and prompts
        from inspekt.config import is_isolated_mode
        if is_isolated_mode():
            _verbose_log("Isolated mode active, skipping domain check")
            return True

        domain = self._quick_get_current_domain()

        if domain is None:
            _verbose_log("Could not determine current domain, proceeding")
            # Couldn't get domain, proceed with normal execution
            return True

        is_allowed = self._is_domain_allowed(domain)
        _verbose_log(f"Domain '{domain}' allowed", is_allowed)

        if is_allowed:
            return True

        # Domain not allowed - prompt user
        return self._prompt_add_domain(domain)

    def _prompt_add_domain(self, domain: str) -> bool:
        """
        Prompt user to add domain to allowed list.

        Returns:
            True if domain was added, False otherwise
        """
        import requests
        from inspekt.services.domain_service import get_domain_service, normalize_domain

        try:
            # Normalize the domain (strip www. prefix)
            normalized = normalize_domain(domain)

            # Show helpful message
            click.echo(f"\nDomain '{normalized}' is not in the allowed list.", err=True)
            click.echo(f"", err=True)

            # Prompt user
            response = click.prompt(
                f'Would you like to add it now? [Y/n]',
                type=str,
                default="Y",
                show_default=False
            )

            if response.lower() in ('n', 'no'):
                click.echo(f"\nDomain not added. You can add it later with:", err=True)
                click.echo(f"  inspekt domain add {normalized}", err=True)
                click.echo(f"", err=True)
                click.echo(f"Or bypass all domain checks for 1 hour with:", err=True)
                click.echo(f"  inspekt yolo", err=True)
                return False

            # Add to SQLite (automatically normalized)
            domain_service = get_domain_service()
            result = domain_service.add_domain(normalized)

            if not result.get("ok"):
                click.echo(f"Error: Failed to add domain to database", err=True)
                return False

            stored_domain = result.get("domain", normalized)
            click.echo(f"✓ Domain added: {stored_domain}")

            # Sync to browser extension with confirmation
            try:
                _verbose_log("Syncing domains to browser extension")
                sync_start = time.time()
                domains = domain_service.get_domains_for_browser_sync()
                sync_response = requests.post(
                    f"http://{self.host}:{self.port}/domains/sync",
                    json={"domains": domains},
                    timeout=10.0  # Wait for browser confirmation
                )
                _verbose_log("Sync response", f"status={sync_response.status_code}, time={time.time() - sync_start:.3f}s")
                if sync_response.status_code == 200:
                    data = sync_response.json()
                    browsers_synced = data.get("browsers_synced", 0)
                    _verbose_log("Browsers synced", browsers_synced)
                    if data.get("ok") and browsers_synced > 0:
                        click.echo("✓ Synced to browser extension")
                    else:
                        click.echo("⚠ Browser sync pending", err=True)
            except Exception as e:
                _verbose_log("Sync failed (non-critical)", str(e))
                click.echo("⚠ Browser sync pending", err=True)

            click.echo("")  # Blank line before continuing
            return True

        except Exception as e:
            click.echo(f"Error: Failed to add domain: {e}", err=True)
            return False

    def execute_file(
        self,
        filepath: str | Path,
        timeout: float = 10.0,
        retry_on_timeout: bool = False,
        skip_domain_check: bool = False,
    ) -> dict[str, Any]:
        """
        Execute JavaScript from a file.

        Args:
            filepath: Path to JavaScript file
            timeout: Maximum time to wait for result in seconds
            retry_on_timeout: If True, retry on TimeoutError
            skip_domain_check: If True, skip the pre-execution domain check

        Returns:
            Dictionary with execution result

        Raises:
            SystemExit: If file read or execution fails
        """
        try:
            with open(filepath, encoding="utf-8") as f:
                code = f.read()
        except (FileNotFoundError, IOError) as e:
            click.echo(f"Error reading file {filepath}: {e}", err=True)
            sys.exit(1)

        return self.execute(code, timeout=timeout, retry_on_timeout=retry_on_timeout, skip_domain_check=skip_domain_check)

    def execute_with_script(
        self,
        script_name: str,
        substitutions: dict[str, str] | None = None,
        timeout: float = 10.0,
        retry_on_timeout: bool = False,
        skip_domain_check: bool = False,
    ) -> dict[str, Any]:
        """
        Execute a helper script with template substitutions.

        Args:
            script_name: Name of script file in zen/scripts/
            substitutions: Dictionary of placeholder -> value substitutions
            timeout: Maximum time to wait for result in seconds
            retry_on_timeout: If True, retry on TimeoutError
            skip_domain_check: If True, skip the pre-execution domain check

        Returns:
            Dictionary with execution result

        Raises:
            SystemExit: If script not found or execution fails
        """
        # Locate script file
        from inspekt.services.script_loader import ScriptLoader

        loader = ScriptLoader()
        try:
            code = loader.load_script_sync(script_name, substitutions=substitutions)
        except FileNotFoundError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        return self.execute(code, timeout=timeout, retry_on_timeout=retry_on_timeout, skip_domain_check=skip_domain_check)

    def check_result_ok(self, result: dict[str, Any]) -> None:
        """
        Check if result is successful, exit with error if not.

        Args:
            result: Execution result dictionary

        Exits:
            sys.exit(1) if result["ok"] is False
        """
        if not result.get("ok"):
            error = result.get("error", "Unknown error")
            click.echo(f"Error: {error}", err=True)
            sys.exit(1)

    def get_status(self) -> dict[str, Any] | None:
        """
        Get bridge server status.

        Returns:
            Status dictionary or None if server not running
        """
        return self.client.get_status()

    def check_userscript_version(self, show_warning: bool = True) -> str | None:
        """
        Check if userscript version matches expected version.

        Args:
            show_warning: If True, print warning when versions don't match

        Returns:
            Warning message if versions don't match, None otherwise
        """
        return self.client.check_userscript_version(show_warning=show_warning)


# Global executor instance (lazy-initialized)
_default_executor: BridgeExecutor | None = None


def get_executor(
    host: str = "127.0.0.1",
    port: int = 8765,
    max_retries: int = 3,
) -> BridgeExecutor:
    """
    Get the default executor instance (singleton pattern).

    Args:
        host: Bridge server host
        port: Bridge server port
        max_retries: Maximum retry attempts

    Returns:
        Shared BridgeExecutor instance
    """
    global _default_executor
    if _default_executor is None:
        _default_executor = BridgeExecutor(
            host=host, port=port, max_retries=max_retries
        )
    return _default_executor
