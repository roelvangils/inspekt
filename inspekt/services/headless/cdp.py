"""
Chrome DevTools Protocol (CDP) client.

Provides WebSocket-based communication with Chrome's DevTools Protocol,
supporting both low-level command/response patterns and event subscriptions.
"""

import asyncio
import base64
import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import websockets

if TYPE_CHECKING:
    from websockets.client import WebSocketClientProtocol


class CDPError(Exception):
    """Error from CDP command execution."""

    def __init__(self, code: int, message: str, data: dict | None = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"CDP Error {code}: {message}")


class CDPClient:
    """
    Low-level Chrome DevTools Protocol WebSocket client.

    Handles:
    - WebSocket connection management
    - Command/response matching via message IDs
    - Event subscription and dispatch

    Example:
        client = CDPClient()
        await client.connect(ws_url)
        result = await client.send("Page.navigate", {"url": "https://example.com"})
        await client.close()
    """

    def __init__(self):
        self._ws: WebSocketClientProtocol | None = None
        self._message_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: dict[str, list[Callable]] = {}
        self._receive_task: asyncio.Task | None = None
        self._handler_tasks: set[asyncio.Task] = set()
        self._closed = False

    async def connect(self, websocket_url: str) -> None:
        """
        Connect to Chrome's CDP WebSocket.

        Args:
            websocket_url: CDP WebSocket URL (e.g., ws://127.0.0.1:9222/devtools/browser/...)
        """
        self._ws = await websockets.connect(
            websocket_url,
            max_size=100 * 1024 * 1024,  # 100MB for large screenshots
            ping_interval=30,
            ping_timeout=10,
        )
        self._closed = False

        # Start receive loop
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def send(self, method: str, params: dict | None = None, timeout: float = 30.0) -> dict:
        """
        Send CDP command and await response.

        Args:
            method: CDP method name (e.g., "Page.navigate")
            params: Method parameters (optional)
            timeout: Response timeout in seconds

        Returns:
            Result from CDP command

        Raises:
            CDPError: If command returns an error
            TimeoutError: If response not received in time
        """
        if self._ws is None or self._closed:
            raise RuntimeError("CDP client not connected")

        # Generate unique message ID
        self._message_id += 1
        msg_id = self._message_id

        # Create future for response
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_id] = future

        # Send command
        message = {"id": msg_id, "method": method}
        if params:
            message["params"] = params

        try:
            await self._ws.send(json.dumps(message))

            # Wait for response
            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except TimeoutError:
            self._pending.pop(msg_id, None)
            raise TimeoutError(f"CDP command {method} timed out after {timeout}s")

        except Exception:
            self._pending.pop(msg_id, None)
            raise

    def subscribe(self, event: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        """
        Subscribe to CDP events.

        Args:
            event: Event name (e.g., "Page.loadEventFired")
            callback: Function to call when event occurs

        Returns:
            Unsubscribe function
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []

        self._event_handlers[event].append(callback)

        # Return unsubscribe function
        def unsubscribe():
            if event in self._event_handlers:
                try:
                    self._event_handlers[event].remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    async def close(self) -> None:
        """Close WebSocket connection."""
        self._closed = True

        # Cancel receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            self._ws = None

        # Cancel pending futures
        for future in self._pending.values():
            if not future.done():
                future.cancel()
        self._pending.clear()

    async def _receive_loop(self) -> None:
        """Background task to receive and dispatch messages."""
        try:
            async for message in self._ws:
                if self._closed:
                    break

                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    continue

                # Handle command response
                if "id" in data:
                    msg_id = data["id"]
                    future = self._pending.pop(msg_id, None)
                    if future and not future.done():
                        if "error" in data:
                            error = data["error"]
                            future.set_exception(
                                CDPError(
                                    code=error.get("code", -1),
                                    message=error.get("message", "Unknown error"),
                                    data=error.get("data"),
                                )
                            )
                        else:
                            future.set_result(data.get("result", {}))

                # Handle event
                elif "method" in data:
                    event_name = data["method"]
                    params = data.get("params", {})

                    handlers = self._event_handlers.get(event_name, [])
                    for handler in handlers:
                        try:
                            result = handler(params)
                            # Support async handlers (hold a reference so the
                            # task isn't garbage collected mid-flight)
                            if asyncio.iscoroutine(result):
                                task = asyncio.create_task(result)
                                self._handler_tasks.add(task)
                                task.add_done_callback(self._handler_tasks.discard)
                        except Exception:
                            pass  # Don't let handler errors break the loop

        except websockets.ConnectionClosed:
            pass
        except asyncio.CancelledError:
            pass


class CDPSession:
    """
    High-level CDP session for a specific page/tab.

    Provides convenient methods for common operations like navigation,
    JavaScript execution, and screenshots.

    Example:
        session = CDPSession(client, target_id)
        await session.navigate("https://example.com")
        result = await session.execute("document.title")
        screenshot = await session.screenshot()
    """

    def __init__(self, client: CDPClient, target_id: str | None = None):
        self.client = client
        self.target_id = target_id

    async def navigate(
        self,
        url: str,
        wait_until: str = "load",
        timeout: float = 30.0,
    ) -> None:
        """
        Navigate to URL and wait for page load.

        Args:
            url: URL to navigate to
            wait_until: Wait condition - "load", "domcontentloaded", or "networkidle"
            timeout: Navigation timeout in seconds
        """
        # Enable Page domain
        await self.client.send("Page.enable")

        # Set up load event listener
        load_event = asyncio.Event()

        if wait_until == "load":
            event_name = "Page.loadEventFired"
        elif wait_until == "domcontentloaded":
            event_name = "Page.domContentEventFired"
        else:
            event_name = "Page.loadEventFired"

        def on_load(params):
            load_event.set()

        unsubscribe = self.client.subscribe(event_name, on_load)

        try:
            # Navigate
            await self.client.send("Page.navigate", {"url": url})

            # Wait for load event
            await asyncio.wait_for(load_event.wait(), timeout=timeout)

        finally:
            unsubscribe()

    async def execute(self, expression: str, await_promise: bool = True) -> Any:
        """
        Execute JavaScript in page context.

        Args:
            expression: JavaScript expression to evaluate
            await_promise: Whether to await if result is a Promise

        Returns:
            Result of the expression
        """
        await self.client.send("Runtime.enable")

        result = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": await_promise,
            },
        )

        if "exceptionDetails" in result:
            exception = result["exceptionDetails"]
            text = exception.get("text", "")
            if "exception" in exception:
                text = exception["exception"].get("description", text)
            raise RuntimeError(f"JavaScript error: {text}")

        remote_object = result.get("result", {})

        # Handle different value types
        if remote_object.get("type") == "undefined":
            return None
        elif "value" in remote_object:
            return remote_object["value"]
        else:
            return remote_object

    async def screenshot(
        self,
        format: str = "png",
        quality: int | None = None,
        clip: dict | None = None,
        full_page: bool = False,
        omit_background: bool = False,
    ) -> bytes:
        """
        Capture screenshot.

        Args:
            format: Image format - "png", "jpeg", or "webp"
            quality: JPEG/WebP quality (0-100)
            clip: Clip region {x, y, width, height, scale}
            full_page: Capture full scrollable page
            omit_background: Make background transparent (PNG only)

        Returns:
            Screenshot image data as bytes
        """
        params: dict[str, Any] = {"format": format}

        if quality is not None and format in ("jpeg", "webp"):
            params["quality"] = quality

        if clip:
            params["clip"] = clip
            params["captureBeyondViewport"] = True

        if full_page:
            # Get full page dimensions
            metrics = await self.client.send("Page.getLayoutMetrics")
            content_size = metrics.get("cssContentSize") or metrics.get("contentSize", {})

            params["clip"] = {
                "x": 0,
                "y": 0,
                "width": content_size.get("width", 1920),
                "height": content_size.get("height", 1080),
                "scale": 1,
            }
            params["captureBeyondViewport"] = True

        if omit_background:
            params["omitBackground"] = True

        result = await self.client.send("Page.captureScreenshot", params)
        return base64.b64decode(result["data"])

    async def get_html(self) -> str:
        """Get page HTML source."""
        result = await self.client.send(
            "Runtime.evaluate",
            {
                "expression": "document.documentElement.outerHTML",
                "returnByValue": True,
            },
        )
        return result.get("result", {}).get("value", "")

    async def get_cookies(self) -> list[dict]:
        """Get all cookies for current page."""
        result = await self.client.send("Network.getCookies")
        return result.get("cookies", [])

    async def set_cookies(self, cookies: list[dict]) -> None:
        """Set cookies."""
        await self.client.send("Network.setCookies", {"cookies": cookies})

    async def wait_for_selector(
        self,
        selector: str,
        timeout: float = 5.0,
        poll_interval: float = 0.1,
    ) -> bool:
        """
        Wait for element to appear in DOM.

        Args:
            selector: CSS selector
            timeout: Maximum wait time in seconds
            poll_interval: How often to check

        Returns:
            True if found, False if timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                result = await self.execute(f"!!document.querySelector({json.dumps(selector)})")
                if result:
                    return True
            except Exception:
                pass

            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                return False

            await asyncio.sleep(poll_interval)

    async def emulate_media(
        self,
        color_scheme: str | None = None,
        reduced_motion: str | None = None,
    ) -> None:
        """
        Emulate media features.

        Args:
            color_scheme: "light" or "dark"
            reduced_motion: "reduce" or "no-preference"
        """
        features = []

        if color_scheme:
            features.append({"name": "prefers-color-scheme", "value": color_scheme})

        if reduced_motion:
            features.append({"name": "prefers-reduced-motion", "value": reduced_motion})

        if features:
            await self.client.send("Emulation.setEmulatedMedia", {"features": features})

    async def set_viewport(
        self,
        width: int,
        height: int,
        device_scale_factor: float = 1.0,
        mobile: bool = False,
    ) -> None:
        """
        Set viewport size and device scale factor.

        Args:
            width: Viewport width in pixels
            height: Viewport height in pixels
            device_scale_factor: Device pixel ratio (e.g., 2.0 for retina)
            mobile: Emulate mobile device
        """
        await self.client.send(
            "Emulation.setDeviceMetricsOverride",
            {
                "width": width,
                "height": height,
                "deviceScaleFactor": device_scale_factor,
                "mobile": mobile,
            },
        )

    async def set_user_agent(self, user_agent: str, language: str | None = None) -> None:
        """
        Set user agent and language.

        Args:
            user_agent: User agent string
            language: Accept-Language header value
        """
        params = {"userAgent": user_agent}
        if language:
            params["acceptLanguage"] = language

        await self.client.send("Network.setUserAgentOverride", params)

    async def set_timezone(self, timezone_id: str) -> None:
        """
        Set timezone.

        Args:
            timezone_id: Timezone identifier (e.g., "America/New_York")
        """
        await self.client.send("Emulation.setTimezoneOverride", {"timezoneId": timezone_id})

    async def hide_scrollbars(self) -> None:
        """Hide scrollbars for cleaner screenshots."""
        await self.client.send("Emulation.setScrollbarsHidden", {"hidden": True})
