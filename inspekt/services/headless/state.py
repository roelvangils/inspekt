"""
Browser state extraction and injection for session mirroring.

Provides mechanisms to extract complete browser state from a live Chrome
instance (via the Inspekt extension) and inject it into a headless browser
session via CDP.
"""

import json
from dataclasses import dataclass, field
from typing import Any

from inspekt.services.headless.cdp import CDPSession


@dataclass
class BrowserState:
    """
    Complete browser state for mirroring between live and headless browsers.

    This dataclass captures everything needed to make a headless browser
    session behave identically to a live browser session, including:
    - Authentication state (cookies, storage)
    - Visual rendering settings (viewport, DPR, color scheme)
    - Locale settings (user agent, language, timezone)

    Example:
        state = BrowserState(
            url="https://example.com/dashboard",
            cookies=[{"name": "session", "value": "abc123", ...}],
            viewport=(1920, 1080),
            dpr=2.0,
            color_scheme="dark"
        )
    """

    # Page location
    url: str = ""

    # Authentication & session state
    cookies: list[dict] = field(default_factory=list)
    local_storage: dict[str, dict[str, str]] = field(default_factory=dict)
    session_storage: dict[str, dict[str, str]] = field(default_factory=dict)

    # Browser identity
    user_agent: str = ""
    language: str = "en-US"

    # Visual rendering
    viewport: tuple[int, int] = (1920, 1080)
    dpr: float = 1.0
    color_scheme: str = "light"  # "light" or "dark"
    reduced_motion: bool = False

    # Locale
    timezone: str = "UTC"

    # Optional: scroll position for exact visual matching
    scroll_x: int = 0
    scroll_y: int = 0

    # Optional: inspected element selector (from DevTools)
    inspected_selector: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary for storage/transmission."""
        return {
            "url": self.url,
            "cookies": self.cookies,
            "localStorage": self.local_storage,
            "sessionStorage": self.session_storage,
            "userAgent": self.user_agent,
            "language": self.language,
            "viewport": list(self.viewport),
            "dpr": self.dpr,
            "colorScheme": self.color_scheme,
            "reducedMotion": self.reduced_motion,
            "timezone": self.timezone,
            "scrollX": self.scroll_x,
            "scrollY": self.scroll_y,
            "inspectedSelector": self.inspected_selector,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BrowserState":
        """Deserialize state from dictionary."""
        return cls(
            url=data.get("url", ""),
            cookies=data.get("cookies", []),
            local_storage=data.get("localStorage", {}),
            session_storage=data.get("sessionStorage", {}),
            user_agent=data.get("userAgent", ""),
            language=data.get("language", "en-US"),
            viewport=tuple(data.get("viewport", [1920, 1080])),
            dpr=data.get("dpr", 1.0),
            color_scheme=data.get("colorScheme", "light"),
            reduced_motion=data.get("reducedMotion", False),
            timezone=data.get("timezone", "UTC"),
            scroll_x=data.get("scrollX", 0),
            scroll_y=data.get("scrollY", 0),
            inspected_selector=data.get("inspectedSelector"),
        )


class StateMirror:
    """
    Extract browser state from live Chrome and inject into headless sessions.

    This class bridges the gap between a user's authenticated browser session
    and a headless Chrome instance, enabling pixel-identical screenshots of
    authenticated content.

    The extraction happens via the Inspekt browser extension, which has access
    to cookies (including HttpOnly), localStorage, and sessionStorage.

    Example:
        # Extract from live browser
        state = await StateMirror.extract_from_extension(client)

        # Inject into headless session
        await StateMirror.inject_to_cdp(session, state)
    """

    @staticmethod
    async def extract_from_extension(bridge_client: Any) -> BrowserState:
        """
        Extract complete browser state from live Chrome via Inspekt extension.

        This method communicates with the Inspekt browser extension to gather:
        - All cookies for the current domain (JS-accessible only)
        - localStorage data
        - sessionStorage data
        - Viewport dimensions and device pixel ratio
        - User preferences (color scheme, reduced motion)
        - Inspected element selector (if any)

        Args:
            bridge_client: Inspekt BridgeClient (synchronous HTTP client)

        Returns:
            BrowserState with all extracted data

        Raises:
            RuntimeError: If extension is not connected or extraction fails
        """
        import asyncio

        # BridgeClient.execute() is synchronous, run in thread pool
        def _execute(code: str) -> dict:
            return bridge_client.execute(code, timeout=10.0)

        # Get all state in a single JavaScript call for efficiency
        state_script = """
            (function() {
                // Get localStorage
                const localStorage_data = {};
                try {
                    for (let i = 0; i < localStorage.length; i++) {
                        const key = localStorage.key(i);
                        localStorage_data[key] = localStorage.getItem(key);
                    }
                } catch(e) {}

                // Get sessionStorage
                const sessionStorage_data = {};
                try {
                    for (let i = 0; i < sessionStorage.length; i++) {
                        const key = sessionStorage.key(i);
                        sessionStorage_data[key] = sessionStorage.getItem(key);
                    }
                } catch(e) {}

                // Get inspected element selector
                let inspectedSelector = null;
                try {
                    const element = window.__INSPEKT_INSPECTED_ELEMENT__;
                    if (element && element.nodeType === 1 && document.body.contains(element)) {
                        function getCSSPath(el) {
                            if (!(el instanceof Element)) return '';
                            const path = [];
                            while (el.nodeType === Node.ELEMENT_NODE) {
                                let selector = el.nodeName.toLowerCase();
                                if (el.id) {
                                    selector += '#' + CSS.escape(el.id);
                                    path.unshift(selector);
                                    break;
                                } else {
                                    let sibling = el;
                                    let nth = 1;
                                    while (sibling.previousElementSibling) {
                                        sibling = sibling.previousElementSibling;
                                        if (sibling.nodeName.toLowerCase() === selector) nth++;
                                    }
                                    if (nth !== 1) selector += ':nth-of-type(' + nth + ')';
                                }
                                path.unshift(selector);
                                el = el.parentNode;
                            }
                            return path.join(' > ');
                        }
                        inspectedSelector = getCSSPath(element);
                    }
                } catch(e) {}

                return {
                    url: window.location.href,
                    origin: window.location.origin,
                    cookies: document.cookie,
                    localStorage: localStorage_data,
                    sessionStorage: sessionStorage_data,
                    userAgent: navigator.userAgent,
                    language: navigator.language,
                    viewport: [window.innerWidth, window.innerHeight],
                    dpr: window.devicePixelRatio,
                    colorScheme: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
                    reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
                    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
                    scrollX: window.scrollX,
                    scrollY: window.scrollY,
                    inspectedSelector: inspectedSelector
                };
            })()
        """

        # Run synchronous HTTP call in thread pool to not block event loop
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, _execute, state_script)

        if not response.get("ok"):
            raise RuntimeError(f"Failed to extract browser state: {response.get('error', 'Unknown error')}")

        result = response.get("result", {})

        # Parse cookies from document.cookie string
        # Note: document.cookie only gives us name=value, not domain/path/etc.
        # We add the current domain so CDP can set them
        cookies = []
        cookie_string = result.get("cookies", "")
        url = result.get("url", "")
        if cookie_string and url:
            # Extract domain from URL
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            domain = parsed_url.hostname or ""

            for cookie in cookie_string.split("; "):
                if "=" in cookie:
                    name, value = cookie.split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value,
                        "domain": domain,
                        "path": "/",
                    })

        # Build local_storage dict with origin as key
        local_storage = {}
        origin = result.get("origin", result.get("url", ""))
        ls_data = result.get("localStorage", {})
        if ls_data:
            local_storage[origin] = ls_data

        # Build session_storage dict with origin as key
        session_storage = {}
        ss_data = result.get("sessionStorage", {})
        if ss_data:
            session_storage[origin] = ss_data

        return BrowserState(
            url=result.get("url", ""),
            cookies=cookies,
            local_storage=local_storage,
            session_storage=session_storage,
            user_agent=result.get("userAgent", ""),
            language=result.get("language", "en-US"),
            viewport=tuple(result.get("viewport", [1920, 1080])),
            dpr=result.get("dpr", 1.0),
            color_scheme=result.get("colorScheme", "light"),
            reduced_motion=result.get("reducedMotion", False),
            timezone=result.get("timezone", "UTC"),
            scroll_x=result.get("scrollX", 0),
            scroll_y=result.get("scrollY", 0),
            inspected_selector=result.get("inspectedSelector"),
        )

    @staticmethod
    async def inject_to_cdp(session: CDPSession, state: BrowserState) -> None:
        """
        Inject browser state into a headless Chrome session via CDP.

        This method configures a headless browser to match the live browser's:
        - Viewport and device pixel ratio
        - Color scheme and reduced motion preferences
        - User agent and language
        - Timezone
        - Cookies (before navigation)
        - localStorage and sessionStorage (after navigation)

        Args:
            session: CDP session for the headless browser
            state: Browser state to inject

        Note:
            Cookies should be injected BEFORE navigation.
            localStorage/sessionStorage should be injected AFTER navigation
            but before page scripts run (via Page.addScriptToEvaluateOnNewDocument).
        """
        # 1. Set viewport and device metrics
        await session.set_viewport(
            width=state.viewport[0],
            height=state.viewport[1],
            device_scale_factor=state.dpr,
        )

        # 2. Set media emulation (color scheme, reduced motion)
        await session.emulate_media(
            color_scheme=state.color_scheme,
            reduced_motion="reduce" if state.reduced_motion else "no-preference",
        )

        # 3. Set user agent and language
        if state.user_agent:
            await session.set_user_agent(
                user_agent=state.user_agent,
                language=state.language,
            )

        # 4. Set timezone
        if state.timezone:
            await session.set_timezone(state.timezone)

        # 5. Inject cookies (before navigation)
        if state.cookies:
            await session.set_cookies(state.cookies)

        # 6. Set up storage injection (will execute before page scripts)
        await StateMirror._setup_storage_injection(session, state)

        # 7. Hide scrollbars for cleaner screenshots
        await session.hide_scrollbars()

    @staticmethod
    async def _setup_storage_injection(session: CDPSession, state: BrowserState) -> None:
        """
        Set up localStorage and sessionStorage injection via CDP.

        Uses Page.addScriptToEvaluateOnNewDocument to inject storage data
        before any page scripts run, ensuring the page sees the same storage
        state as the live browser.
        """
        # Build injection script for localStorage
        storage_script_parts = []

        for _origin, data in state.local_storage.items():
            if data:
                escaped_data = json.dumps(data)
                storage_script_parts.append(f"""
                    try {{
                        const lsData = {escaped_data};
                        for (const [key, value] of Object.entries(lsData)) {{
                            localStorage.setItem(key, value);
                        }}
                    }} catch (e) {{
                        console.warn('[Inspekt] Failed to inject localStorage:', e);
                    }}
                """)

        for _origin, data in state.session_storage.items():
            if data:
                escaped_data = json.dumps(data)
                storage_script_parts.append(f"""
                    try {{
                        const ssData = {escaped_data};
                        for (const [key, value] of Object.entries(ssData)) {{
                            sessionStorage.setItem(key, value);
                        }}
                    }} catch (e) {{
                        console.warn('[Inspekt] Failed to inject sessionStorage:', e);
                    }}
                """)

        if storage_script_parts:
            injection_script = "\n".join(storage_script_parts)
            await session.client.send(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": injection_script},
            )

    @staticmethod
    async def extract_minimal(bridge_client: Any) -> BrowserState:
        """
        Extract minimal state needed for screenshot matching.

        This is a faster alternative to extract_from_extension() that only
        captures visual rendering settings, not authentication state.
        Useful for public pages where session mirroring isn't needed.

        Args:
            bridge_client: Inspekt BridgeClient (synchronous HTTP client)

        Returns:
            BrowserState with viewport, DPR, and color scheme only
        """
        import asyncio

        def _execute(code: str) -> dict:
            return bridge_client.execute(code, timeout=5.0)

        script = """
            (function() {
                return {
                    viewport: [window.innerWidth, window.innerHeight],
                    dpr: window.devicePixelRatio,
                    colorScheme: window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
                    reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches
                };
            })()
        """

        loop = asyncio.get_event_loop()
        env_response = await loop.run_in_executor(None, _execute, script)

        env = env_response.get("result", {}) if env_response.get("ok") else {}

        return BrowserState(
            viewport=tuple(env.get("viewport", [1920, 1080])),
            dpr=env.get("dpr", 1.0),
            color_scheme=env.get("colorScheme", "light"),
            reduced_motion=env.get("reducedMotion", False),
        )
