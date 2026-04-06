"""
High-level headless browser context for Inspekt commands.

Provides a command-agnostic async context manager that handles all the
complexity of headless browser setup, state mirroring, and cleanup.
"""

import asyncio
import base64
import json
from typing import Any, Optional

from inspekt.services.headless.chrome import HeadlessChrome
from inspekt.services.headless.cdp import CDPClient, CDPSession
from inspekt.services.headless.state import BrowserState, StateMirror


class HeadlessContext:
    """
    High-level async context manager for headless browser operations.

    This is the primary interface for all Inspekt commands that need
    headless browser functionality. It handles:
    - Launching headless Chrome
    - Optional session mirroring from live browser
    - Environment matching (viewport, DPR, color scheme)
    - Page navigation and load waiting
    - Clean shutdown

    Example usage:

        # Screenshot with session mirroring
        async with HeadlessContext(url=url, mirror_session=True) as ctx:
            image = await ctx.screenshot(selector=".card", isolate=True)

        # Accessibility testing
        async with HeadlessContext(url=url, mirror_session=True) as ctx:
            await ctx.execute_script(inject_axe_script)
            results = await ctx.execute_script(run_axe_script)

        # Content extraction
        async with HeadlessContext(url=url) as ctx:
            html = await ctx.get_html()
            article = await ctx.execute_script(readability_script)
    """

    def __init__(
        self,
        url: Optional[str] = None,
        mirror_session: bool = False,
        viewport: Optional[tuple[int, int]] = None,
        dpr: Optional[float] = None,
        color_scheme: Optional[str] = None,
        timeout: float = 30.0,
        bridge_client: Optional[Any] = None,
    ):
        """
        Initialize headless context configuration.

        Args:
            url: URL to navigate to. If None and mirror_session=True,
                 will use the URL from the live browser.
            mirror_session: If True, extract and apply browser state
                           (cookies, storage, preferences) from live browser.
            viewport: Override viewport size (width, height).
                     If None, uses live browser viewport or default (1920, 1080).
            dpr: Override device pixel ratio.
                 If None, uses live browser DPR or default (1.0).
            color_scheme: Override color scheme ("light" or "dark").
                         If None, uses live browser preference or "light".
            timeout: Page load timeout in seconds (default: 30).
            bridge_client: Optional bridge client for state extraction.
                          If None and mirror_session=True, will create one.
        """
        self._url = url
        self._mirror_session = mirror_session
        self._viewport = viewport
        self._dpr = dpr
        self._color_scheme = color_scheme
        self._timeout = timeout
        self._bridge_client = bridge_client

        # Runtime state (set during __aenter__)
        self._chrome: Optional[HeadlessChrome] = None
        self._cdp_client: Optional[CDPClient] = None
        self._session: Optional[CDPSession] = None
        self._state: Optional[BrowserState] = None
        self._current_url: str = ""

    async def __aenter__(self) -> "HeadlessContext":
        """
        Set up headless browser environment.

        Steps:
        1. Extract state from live browser (if mirror_session)
        2. Launch headless Chrome
        3. Connect via CDP
        4. Apply browser state
        5. Navigate to URL
        6. Wait for page load

        Returns:
            Self for use in async with block

        Raises:
            RuntimeError: If setup fails (Chrome not found, connection error, etc.)
        """
        try:
            # Step 1: Extract state from live browser if requested
            if self._mirror_session:
                await self._extract_live_state()

            # Determine final URL
            if self._url:
                self._current_url = self._url
            elif self._state and self._state.url:
                self._current_url = self._state.url
            else:
                raise RuntimeError(
                    "No URL specified. Provide --url or use --mirror-session "
                    "to capture from live browser."
                )

            # Step 2: Launch headless Chrome
            self._chrome = await HeadlessChrome.launch(headless=True)

            # Step 3: Connect via CDP
            ws_url = await self._chrome.get_websocket_url()
            self._cdp_client = CDPClient()
            await self._cdp_client.connect(ws_url)

            # Create a new page/tab
            page_ws_url = await self._chrome.new_page()
            page_client = CDPClient()
            await page_client.connect(page_ws_url)
            self._session = CDPSession(page_client)

            # Step 4: Apply browser state
            await self._apply_state()

            # Step 5: Navigate to URL
            await self._session.navigate(
                self._current_url,
                wait_until="load",
                timeout=self._timeout,
            )

            # Step 6: Additional wait for dynamic content
            await self._wait_for_ready()

            return self

        except Exception as e:
            # Clean up on failure
            await self._cleanup()
            raise RuntimeError(f"Failed to initialize headless context: {e}") from e

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up headless browser resources."""
        await self._cleanup()

    # ─────────────────────────────────────────────────────────────────
    # Properties
    # ─────────────────────────────────────────────────────────────────

    @property
    def url(self) -> str:
        """Current page URL."""
        return self._current_url

    @property
    def cdp(self) -> CDPSession:
        """
        Direct CDP session access for advanced use cases.

        Use this when you need CDP features not exposed by HeadlessContext.
        """
        if self._session is None:
            raise RuntimeError("HeadlessContext not initialized")
        return self._session

    @property
    def state(self) -> Optional[BrowserState]:
        """Browser state (if session mirroring was used)."""
        return self._state

    # ─────────────────────────────────────────────────────────────────
    # Common Operations
    # ─────────────────────────────────────────────────────────────────

    async def execute_script(self, script: str, await_promise: bool = True) -> Any:
        """
        Execute JavaScript in page context.

        Args:
            script: JavaScript code to execute
            await_promise: If True, await Promise results

        Returns:
            Result of script execution

        Example:
            title = await ctx.execute_script("document.title")
            elements = await ctx.execute_script("document.querySelectorAll('a').length")
        """
        if self._session is None:
            raise RuntimeError("HeadlessContext not initialized")

        return await self._session.execute(script, await_promise=await_promise)

    async def screenshot(
        self,
        selector: Optional[str] = None,
        full_page: bool = False,
        isolate: bool = False,
        format: str = "png",
        quality: Optional[int] = None,
        omit_background: bool = False,
    ) -> bytes:
        """
        Capture screenshot of page, viewport, or element.

        Args:
            selector: CSS selector for element screenshot.
                     If None, captures viewport (or full page if full_page=True).
            full_page: Capture full scrollable page (ignored if selector provided).
            isolate: If True with selector, hide all other elements.
            format: Image format - "png", "jpeg", or "webp".
            quality: JPEG/WebP quality (0-100). Ignored for PNG.
            omit_background: Make background transparent (PNG only).

        Returns:
            Screenshot image data as bytes

        Example:
            # Viewport screenshot
            image = await ctx.screenshot()

            # Full page
            image = await ctx.screenshot(full_page=True)

            # Element screenshot
            image = await ctx.screenshot(selector=".hero")

            # Isolated element
            image = await ctx.screenshot(selector=".card", isolate=True)
        """
        if self._session is None:
            raise RuntimeError("HeadlessContext not initialized")

        # Element screenshot with optional isolation
        if selector:
            return await self._screenshot_element(
                selector=selector,
                isolate=isolate,
                format=format,
                quality=quality,
                omit_background=omit_background,
            )

        # Full page or viewport screenshot
        return await self._session.screenshot(
            format=format,
            quality=quality,
            full_page=full_page,
            omit_background=omit_background,
        )

    async def get_html(self) -> str:
        """
        Get page HTML source.

        Returns:
            Full HTML content of the page
        """
        if self._session is None:
            raise RuntimeError("HeadlessContext not initialized")

        return await self._session.get_html()

    async def get_cookies(self) -> list[dict]:
        """
        Get all cookies for current page.

        Returns:
            List of cookie dictionaries
        """
        if self._session is None:
            raise RuntimeError("HeadlessContext not initialized")

        return await self._session.get_cookies()

    async def wait_for_selector(
        self,
        selector: str,
        timeout: float = 5.0,
    ) -> bool:
        """
        Wait for element to appear in DOM.

        Args:
            selector: CSS selector to wait for
            timeout: Maximum wait time in seconds

        Returns:
            True if element found, False if timeout
        """
        if self._session is None:
            raise RuntimeError("HeadlessContext not initialized")

        return await self._session.wait_for_selector(selector, timeout=timeout)

    async def wait_for_network_idle(
        self,
        idle_time: float = 0.5,
        timeout: float = 30.0,
    ) -> None:
        """
        Wait for network activity to settle.

        Useful after navigation or interactions that trigger async requests.

        Args:
            idle_time: How long network must be idle (seconds)
            timeout: Maximum wait time (seconds)
        """
        if self._session is None:
            raise RuntimeError("HeadlessContext not initialized")

        # Enable network domain for monitoring
        await self._session.client.send("Network.enable")

        pending_requests = set()
        idle_start: Optional[float] = None

        def on_request_started(params):
            nonlocal idle_start
            request_id = params.get("requestId")
            if request_id:
                pending_requests.add(request_id)
                idle_start = None

        def on_request_finished(params):
            nonlocal idle_start
            request_id = params.get("requestId")
            if request_id in pending_requests:
                pending_requests.discard(request_id)
            if not pending_requests and idle_start is None:
                idle_start = asyncio.get_event_loop().time()

        # Subscribe to network events
        unsub1 = self._session.client.subscribe("Network.requestWillBeSent", on_request_started)
        unsub2 = self._session.client.subscribe("Network.loadingFinished", on_request_finished)
        unsub3 = self._session.client.subscribe("Network.loadingFailed", on_request_finished)

        try:
            start_time = asyncio.get_event_loop().time()
            idle_start = start_time if not pending_requests else None

            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    break

                if idle_start is not None:
                    idle_elapsed = asyncio.get_event_loop().time() - idle_start
                    if idle_elapsed >= idle_time:
                        break

                await asyncio.sleep(0.05)

        finally:
            unsub1()
            unsub2()
            unsub3()

    async def set_scroll_position(self, x: int = 0, y: int = 0) -> None:
        """
        Set page scroll position.

        Args:
            x: Horizontal scroll position
            y: Vertical scroll position
        """
        await self.execute_script(f"window.scrollTo({x}, {y})")

    async def pause_animations(self) -> None:
        """
        Pause all CSS animations and transitions.

        Useful for consistent screenshots of animated content.
        """
        await self.execute_script("""
            document.querySelectorAll('*').forEach(el => {
                el.style.animationPlayState = 'paused';
                el.style.transitionDuration = '0s';
            });
        """)

    # ─────────────────────────────────────────────────────────────────
    # Internal Methods
    # ─────────────────────────────────────────────────────────────────

    async def _extract_live_state(self) -> None:
        """Extract browser state from live Chrome via extension."""
        if self._bridge_client is None:
            # Import here to avoid circular dependency
            from inspekt.client import BridgeClient

            self._bridge_client = BridgeClient()
            # BridgeClient is synchronous HTTP - no connect() needed

        self._state = await StateMirror.extract_from_extension(self._bridge_client)

    async def _apply_state(self) -> None:
        """Apply browser state to headless session."""
        if self._session is None:
            return

        # Build effective state from mirrored state and overrides
        if self._state:
            # Start with mirrored state
            effective_viewport = self._viewport or self._state.viewport
            effective_dpr = self._dpr if self._dpr is not None else self._state.dpr
            effective_color_scheme = self._color_scheme or self._state.color_scheme

            # Apply full mirrored state
            await StateMirror.inject_to_cdp(self._session, self._state)

            # Apply any overrides
            if self._viewport or self._dpr is not None:
                await self._session.set_viewport(
                    width=effective_viewport[0],
                    height=effective_viewport[1],
                    device_scale_factor=effective_dpr,
                )

            if self._color_scheme:
                await self._session.emulate_media(color_scheme=effective_color_scheme)

        else:
            # No mirrored state - apply defaults/overrides only
            viewport = self._viewport or (1920, 1080)
            dpr = self._dpr if self._dpr is not None else 1.0
            color_scheme = self._color_scheme or "light"

            await self._session.set_viewport(
                width=viewport[0],
                height=viewport[1],
                device_scale_factor=dpr,
            )

            await self._session.emulate_media(color_scheme=color_scheme)

            # Hide scrollbars
            await self._session.hide_scrollbars()

    async def _wait_for_ready(self) -> None:
        """Wait for page to be fully ready after navigation."""
        # Wait for any initial dynamic content
        try:
            await self.wait_for_network_idle(idle_time=0.3, timeout=5.0)
        except Exception:
            pass  # Best effort - page might still be usable

        # Small additional delay for JS rendering
        await asyncio.sleep(0.1)

    async def _screenshot_element(
        self,
        selector: str,
        isolate: bool = False,
        format: str = "png",
        quality: Optional[int] = None,
        omit_background: bool = False,
    ) -> bytes:
        """
        Capture screenshot of a specific element.

        Uses the same isolation approach as the regular screenshot command.
        """
        # Find element and get its bounding box
        element_info = await self.execute_script(f"""
            (function() {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return {{ error: 'Element not found', selector: {json.dumps(selector)} }};

                const rect = el.getBoundingClientRect();
                return {{
                    ok: true,
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height
                }};
            }})()
        """)

        if not element_info.get("ok"):
            raise RuntimeError(f"Element not found: {selector}")

        # Apply isolation if requested
        if isolate:
            await self._apply_isolation(selector)

        try:
            # Capture screenshot with clip region
            clip = {
                "x": element_info["x"],
                "y": element_info["y"],
                "width": element_info["width"],
                "height": element_info["height"],
                "scale": 1,
            }

            return await self._session.screenshot(
                format=format,
                quality=quality,
                clip=clip,
                omit_background=omit_background,
            )

        finally:
            # Remove isolation
            if isolate:
                await self._remove_isolation()

    async def _apply_isolation(self, selector: str) -> None:
        """Apply CSS isolation to highlight only the selected element."""
        await self.execute_script(f"""
            (function() {{
                // Remove any existing isolation
                document.querySelectorAll('#inspekt-headless-isolation').forEach(el => el.remove());

                const target = document.querySelector({json.dumps(selector)});
                if (!target) return;

                // Generate unique selector path for the target
                function getUniquePath(el) {{
                    if (el.id) return '#' + CSS.escape(el.id);
                    if (el === document.body) return 'body';
                    if (el === document.documentElement) return 'html';

                    const parent = el.parentElement;
                    if (!parent) return el.tagName.toLowerCase();

                    const siblings = Array.from(parent.children);
                    const index = siblings.indexOf(el) + 1;
                    return getUniquePath(parent) + ' > ' + el.tagName.toLowerCase() + ':nth-child(' + index + ')';
                }}

                const uniqueSelector = getUniquePath(target);

                // Create isolation stylesheet
                const style = document.createElement('style');
                style.id = 'inspekt-headless-isolation';
                style.textContent = `
                    /* Hide everything */
                    body > *:not(script):not(style):not(link) {{
                        visibility: hidden !important;
                    }}

                    /* Show target and ancestors */
                    ${{uniqueSelector}},
                    ${{uniqueSelector}} * {{
                        visibility: visible !important;
                    }}
                `;

                document.head.appendChild(style);
            }})()
        """)

    async def _remove_isolation(self) -> None:
        """Remove CSS isolation."""
        await self.execute_script("""
            document.querySelectorAll('#inspekt-headless-isolation').forEach(el => el.remove());
        """)

    async def _cleanup(self) -> None:
        """Clean up all resources."""
        # Close page CDP client
        if self._session and self._session.client:
            try:
                await self._session.client.close()
            except Exception:
                pass

        # Close browser CDP client
        if self._cdp_client:
            try:
                await self._cdp_client.close()
            except Exception:
                pass

        # Close Chrome process
        if self._chrome:
            try:
                await self._chrome.close()
            except Exception:
                pass

        self._session = None
        self._cdp_client = None
        self._chrome = None
