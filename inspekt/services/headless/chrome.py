"""
Headless Chrome process management.

Handles launching Chrome in headless mode with remote debugging enabled,
finding the Chrome binary on different platforms, and graceful shutdown.
"""

import asyncio
import os
import platform
import shutil
import signal
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import ClassVar

import httpx


class ChromeNotFoundError(Exception):
    """Raised when Chrome binary cannot be found."""

    def __init__(self, searched_paths: list[str]):
        self.searched_paths = searched_paths
        paths_str = "\n  • ".join(searched_paths)
        super().__init__(
            f"Chrome not found. Searched:\n  • {paths_str}\n\n"
            "Install Chrome or set INSPEKT_CHROME_PATH environment variable."
        )


class ChromeLaunchError(Exception):
    """Raised when Chrome fails to launch."""

    pass


class HeadlessChrome:
    """
    Low-level headless Chrome process management.

    Handles:
    - Finding Chrome binary on macOS/Linux/Windows
    - Launching with --headless=new and remote debugging
    - Getting CDP WebSocket URL
    - Graceful shutdown

    Example:
        chrome = await HeadlessChrome.launch()
        ws_url = await chrome.get_websocket_url()
        # ... use CDP via ws_url ...
        await chrome.close()
    """

    # Chrome binary search paths by platform
    CHROME_PATHS: ClassVar[dict[str, list[str]]] = {
        "Darwin": [  # macOS
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        ],
        "Linux": [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/snap/bin/chromium",
        ],
        "Windows": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ],
    }

    def __init__(
        self,
        process: subprocess.Popen,
        debug_port: int,
        user_data_dir: Path | None = None,
        temp_dir: tempfile.TemporaryDirectory | None = None,
    ):
        self.process = process
        self.debug_port = debug_port
        self.user_data_dir = user_data_dir
        self._temp_dir = temp_dir  # Keep reference to prevent cleanup
        self._closed = False

    @classmethod
    async def launch(
        cls,
        headless: bool = True,
        user_data_dir: Path | None = None,
        port: int | None = None,
        timeout: float = 30.0,
    ) -> "HeadlessChrome":
        """
        Launch Chrome with remote debugging enabled.

        Args:
            headless: Run in headless mode (default: True)
            user_data_dir: Custom user data directory (default: temp dir)
            port: Debugging port (default: random available port)
            timeout: Startup timeout in seconds (default: 30)

        Returns:
            HeadlessChrome instance

        Raises:
            ChromeNotFoundError: If Chrome binary not found
            ChromeLaunchError: If Chrome fails to start
        """
        # Find Chrome binary
        chrome_path = await cls.find_chrome_binary()

        # Get available port
        if port is None:
            port = cls._get_available_port()

        # Create temp user data dir if not provided
        temp_dir = None
        if user_data_dir is None:
            temp_dir = tempfile.TemporaryDirectory(prefix="inspekt-chrome-")
            user_data_dir = Path(temp_dir.name)

        # Build Chrome arguments
        args = [
            str(chrome_path),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-client-side-phishing-detection",
            "--disable-default-apps",
            "--disable-extensions",
            "--disable-hang-monitor",
            "--disable-popup-blocking",
            "--disable-prompt-on-repost",
            "--disable-sync",
            "--disable-translate",
            "--metrics-recording-only",
            "--safebrowsing-disable-auto-update",
            "--password-store=basic",
            "--use-mock-keychain",
        ]

        if headless:
            # Use new headless mode (Chrome 112+) for identical rendering
            args.append("--headless=new")

        # Launch Chrome process
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Don't inherit parent's signal handlers
                start_new_session=True,
            )
        except Exception as e:
            if temp_dir:
                temp_dir.cleanup()
            raise ChromeLaunchError(f"Failed to launch Chrome: {e}") from e

        instance = cls(
            process=process,
            debug_port=port,
            user_data_dir=user_data_dir,
            temp_dir=temp_dir,
        )

        # Wait for Chrome to be ready
        try:
            await instance._wait_for_ready(timeout=timeout)
        except Exception as e:
            await instance.close()
            raise ChromeLaunchError(f"Chrome failed to start: {e}") from e

        return instance

    @classmethod
    async def find_chrome_binary(cls) -> Path:
        """
        Auto-detect Chrome binary location.

        Checks:
        1. INSPEKT_CHROME_PATH environment variable
        2. Platform-specific default locations
        3. PATH (via shutil.which)

        Returns:
            Path to Chrome binary

        Raises:
            ChromeNotFoundError: If Chrome not found
        """
        searched = []

        # Check environment variable first
        env_path = os.environ.get("INSPEKT_CHROME_PATH")
        if env_path:
            path = Path(env_path)
            searched.append(str(path))
            if path.exists() and os.access(path, os.X_OK):
                return path

        # Check platform-specific paths
        system = platform.system()
        paths = cls.CHROME_PATHS.get(system, [])

        for path_str in paths:
            path = Path(path_str)
            searched.append(str(path))
            if path.exists() and os.access(path, os.X_OK):
                return path

        # Check PATH
        for name in [
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "chrome",
        ]:
            which_path = shutil.which(name)
            if which_path:
                return Path(which_path)
            searched.append(f"{name} (in PATH)")

        raise ChromeNotFoundError(searched)

    async def get_websocket_url(self) -> str:
        """
        Get CDP WebSocket URL for the browser.

        Returns:
            WebSocket URL for CDP connection
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://127.0.0.1:{self.debug_port}/json/version")
            data = response.json()
            return data["webSocketDebuggerUrl"]

    async def get_page_targets(self) -> list[dict]:
        """
        Get list of page targets (tabs).

        Returns:
            List of target info dicts
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(f"http://127.0.0.1:{self.debug_port}/json/list")
            return [t for t in response.json() if t.get("type") == "page"]

    async def new_page(self, url: str = "about:blank") -> str:
        """
        Create a new page/tab.

        Args:
            url: Initial URL to navigate to

        Returns:
            WebSocket URL for the new page
        """
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"http://127.0.0.1:{self.debug_port}/json/new",
                params={"url": url},
            )
            data = response.json()
            return data["webSocketDebuggerUrl"]

    async def close(self) -> None:
        """
        Gracefully close Chrome and clean up.
        """
        if self._closed:
            return

        self._closed = True

        # Try graceful shutdown first
        if self.process.poll() is None:
            try:
                # Send SIGTERM
                if platform.system() != "Windows":
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                else:
                    self.process.terminate()

                # Wait up to 5 seconds for graceful exit
                try:
                    await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(None, self.process.wait),
                        timeout=5.0,
                    )
                except TimeoutError:
                    # Force kill if graceful shutdown fails
                    if platform.system() != "Windows":
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    else:
                        self.process.kill()
                    self.process.wait()
            except ProcessLookupError:
                pass  # Already dead

        # Clean up temp directory
        if self._temp_dir:
            try:
                self._temp_dir.cleanup()
            except Exception:
                pass  # Best effort cleanup

    async def _wait_for_ready(self, timeout: float = 30.0) -> None:
        """
        Wait for Chrome to be ready to accept connections.

        Args:
            timeout: Maximum time to wait in seconds

        Raises:
            TimeoutError: If Chrome doesn't start in time
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check if process died
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode() if self.process.stderr else ""
                raise ChromeLaunchError(f"Chrome exited unexpectedly: {stderr}")

            # Try to connect
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://127.0.0.1:{self.debug_port}/json/version",
                        timeout=1.0,
                    )
                    if response.status_code == 200:
                        return  # Ready!
            except Exception:
                pass  # Not ready yet

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Chrome did not start within {timeout} seconds")

            # Wait before retry
            await asyncio.sleep(0.1)

    @staticmethod
    def _get_available_port() -> int:
        """Get a random available port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def __del__(self):
        """Ensure cleanup on garbage collection."""
        if not self._closed and self.process.poll() is None:
            try:
                self.process.terminate()
            except Exception:
                pass
