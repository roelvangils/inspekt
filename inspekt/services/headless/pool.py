"""
Headless Chrome browser pool for efficient reuse.

Keeps a pool of warm Chrome instances to avoid the cold-start overhead
of launching Chrome for each operation. Particularly useful for batch
operations and repeated commands.
"""

import asyncio
import time

from inspekt.services.headless.cdp import CDPClient, CDPSession
from inspekt.services.headless.chrome import HeadlessChrome


class HeadlessChromePool:
    """
    Pool of warm headless Chrome instances for fast reuse.

    Maintains a single Chrome instance (expandable to multiple) that stays
    running between commands. Automatically cleans up after idle timeout.

    Features:
    - Singleton pattern for global access
    - Automatic warmup on first use
    - Idle timeout with automatic cleanup
    - Health checking before reuse
    - Thread-safe access

    Example:
        # Get a Chrome instance (launches if needed)
        chrome = await HeadlessChromePool.get()

        # Use it for operations
        ws_url = await chrome.get_websocket_url()

        # Release back to pool (optional - automatic)
        await HeadlessChromePool.release(chrome)

        # Force cleanup
        await HeadlessChromePool.shutdown()
    """

    _instance: HeadlessChrome | None = None
    _cdp_client: CDPClient | None = None
    _last_used: float = 0
    _idle_timeout: float = 300.0  # 5 minutes
    _lock: asyncio.Lock = asyncio.Lock()
    _cleanup_task: asyncio.Task | None = None
    _use_count: int = 0

    @classmethod
    async def get(cls, timeout: float = 30.0) -> HeadlessChrome:
        """
        Get a Chrome instance from the pool.

        If no instance exists or the existing one is unhealthy, launches a new one.
        Resets the idle timer on each use.

        Args:
            timeout: Launch timeout in seconds (only for new instances)

        Returns:
            HeadlessChrome instance ready for use

        Raises:
            RuntimeError: If Chrome cannot be launched
        """
        async with cls._lock:
            # Check if existing instance is healthy
            if cls._instance is not None:
                if await cls._is_healthy():
                    cls._last_used = time.time()
                    cls._use_count += 1
                    return cls._instance
                else:
                    # Unhealthy - close and create new
                    await cls._close_instance()

            # Launch new instance
            cls._instance = await HeadlessChrome.launch(
                headless=True,
                timeout=timeout,
            )
            cls._last_used = time.time()
            cls._use_count += 1

            # Start cleanup task if not running
            if cls._cleanup_task is None or cls._cleanup_task.done():
                cls._cleanup_task = asyncio.create_task(cls._idle_cleanup_loop())

            return cls._instance

    @classmethod
    async def release(cls, chrome: HeadlessChrome) -> None:
        """
        Release a Chrome instance back to the pool.

        Currently a no-op since we maintain a single instance, but included
        for API consistency and future pool expansion.

        Args:
            chrome: Chrome instance to release
        """
        # Update last used time
        cls._last_used = time.time()

    @classmethod
    async def shutdown(cls) -> None:
        """
        Shutdown the pool and close all Chrome instances.

        Should be called on application exit for clean shutdown.
        """
        async with cls._lock:
            # Cancel cleanup task
            if cls._cleanup_task and not cls._cleanup_task.done():
                cls._cleanup_task.cancel()
                try:
                    await cls._cleanup_task
                except asyncio.CancelledError:
                    pass
                cls._cleanup_task = None

            # Close instance
            await cls._close_instance()

    @classmethod
    async def warmup(cls) -> None:
        """
        Pre-launch a Chrome instance to avoid cold-start on first use.

        Useful at application startup for latency-sensitive environments.
        """
        await cls.get()

    @classmethod
    def set_idle_timeout(cls, seconds: float) -> None:
        """
        Configure the idle timeout before automatic cleanup.

        Args:
            seconds: Idle timeout in seconds (default: 300)
        """
        cls._idle_timeout = seconds

    @classmethod
    def get_stats(cls) -> dict:
        """
        Get pool statistics.

        Returns:
            Dict with pool status info
        """
        return {
            "active": cls._instance is not None,
            "use_count": cls._use_count,
            "idle_timeout": cls._idle_timeout,
            "last_used": cls._last_used,
            "idle_seconds": time.time() - cls._last_used if cls._last_used else 0,
        }

    @classmethod
    async def _is_healthy(cls) -> bool:
        """Check if the current instance is healthy and responsive."""
        if cls._instance is None:
            return False

        try:
            # Check if process is still running
            if cls._instance.process.poll() is not None:
                return False

            # Try to get version info (quick health check)
            ws_url = await asyncio.wait_for(
                cls._instance.get_websocket_url(),
                timeout=2.0,
            )
            return bool(ws_url)

        except Exception:
            return False

    @classmethod
    async def _close_instance(cls) -> None:
        """Close the current Chrome instance."""
        if cls._instance:
            try:
                await cls._instance.close()
            except Exception:
                pass  # Best effort cleanup
            cls._instance = None

        if cls._cdp_client:
            try:
                await cls._cdp_client.close()
            except Exception:
                pass
            cls._cdp_client = None

    @classmethod
    async def _idle_cleanup_loop(cls) -> None:
        """Background task that cleans up idle instances."""
        try:
            while True:
                await asyncio.sleep(30)  # Check every 30 seconds

                async with cls._lock:
                    if cls._instance is None:
                        break  # Nothing to clean up

                    idle_time = time.time() - cls._last_used
                    if idle_time > cls._idle_timeout:
                        await cls._close_instance()
                        break  # Exit loop - will restart on next get()

        except asyncio.CancelledError:
            pass


# Convenience function for simple usage
async def get_pooled_chrome() -> HeadlessChrome:
    """
    Get a pooled Chrome instance.

    Convenience wrapper around HeadlessChromePool.get().

    Returns:
        HeadlessChrome instance
    """
    return await HeadlessChromePool.get()


# Context manager for automatic cleanup
class PooledHeadlessContext:
    """
    HeadlessContext that uses the Chrome pool for efficiency.

    Same API as HeadlessContext but reuses Chrome instances from the pool
    instead of launching a new one each time.

    Example:
        async with PooledHeadlessContext(url="https://example.com") as ctx:
            title = await ctx.execute_script("document.title")
    """

    def __init__(
        self,
        url: str | None = None,
        mirror_session: bool = False,
        viewport: tuple[int, int] | None = None,
        dpr: float | None = None,
        color_scheme: str | None = None,
        timeout: float = 30.0,
    ):
        self._url = url
        self._mirror_session = mirror_session
        self._viewport = viewport
        self._dpr = dpr
        self._color_scheme = color_scheme
        self._timeout = timeout

        self._chrome: HeadlessChrome | None = None
        self._cdp_client: CDPClient | None = None
        self._session: CDPSession | None = None
        self._current_url: str = ""

    async def __aenter__(self) -> "PooledHeadlessContext":
        """Set up using pooled Chrome instance."""

        try:
            # Get Chrome from pool
            self._chrome = await HeadlessChromePool.get(timeout=self._timeout)

            # Create a new page/tab
            page_ws_url = await self._chrome.new_page(self._url or "about:blank")
            self._cdp_client = CDPClient()
            await self._cdp_client.connect(page_ws_url)
            self._session = CDPSession(self._cdp_client)

            # Apply settings
            viewport = self._viewport or (1920, 1080)
            dpr = self._dpr if self._dpr is not None else 1.0

            await self._session.set_viewport(
                width=viewport[0],
                height=viewport[1],
                device_scale_factor=dpr,
            )

            if self._color_scheme:
                await self._session.emulate_media(color_scheme=self._color_scheme)

            await self._session.hide_scrollbars()

            # Navigate if URL provided
            if self._url:
                await self._session.navigate(self._url, timeout=self._timeout)
                self._current_url = self._url

            return self

        except Exception as e:
            await self._cleanup()
            raise RuntimeError(f"Failed to initialize pooled context: {e}") from e

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up page but keep Chrome in pool."""
        await self._cleanup()
        # Note: We don't close Chrome - it stays in the pool

    @property
    def url(self) -> str:
        return self._current_url

    @property
    def cdp(self) -> CDPSession:
        if self._session is None:
            raise RuntimeError("Context not initialized")
        return self._session

    async def execute_script(self, script: str, await_promise: bool = True):
        if self._session is None:
            raise RuntimeError("Context not initialized")
        return await self._session.execute(script, await_promise=await_promise)

    async def screenshot(self, **kwargs) -> bytes:
        if self._session is None:
            raise RuntimeError("Context not initialized")
        return await self._session.screenshot(**kwargs)

    async def get_html(self) -> str:
        if self._session is None:
            raise RuntimeError("Context not initialized")
        return await self._session.get_html()

    async def _cleanup(self) -> None:
        """Clean up session resources."""
        if self._cdp_client:
            try:
                await self._cdp_client.close()
            except Exception:
                pass
            self._cdp_client = None

        self._session = None
        # Don't close Chrome - it stays in the pool
