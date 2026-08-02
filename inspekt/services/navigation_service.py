"""Navigation service for browser control operations."""

import json
from typing import Any

from inspekt.services.bridge_executor import get_executor


class NavigationService:
    """Service for browser navigation operations."""

    def __init__(self):
        self.executor = get_executor()

    def navigate_to_url(self, url: str, wait: bool = False, timeout: int = 30) -> dict[str, Any]:
        """
        Navigate to a URL.

        Args:
            url: URL to navigate to
            wait: Whether to wait for page to finish loading
            timeout: Timeout in seconds when using wait

        Returns:
            Result dictionary with ok, result, error fields
        """
        # Basic navigation code (use comma operator, not semicolons, for AsyncFunction wrapping)
        nav_code = f"""(window.location.href = {json.dumps(url)}, true)"""

        # If wait flag is set, wait for page load
        if wait:
            nav_code = f"""
                (async () => {{
                    window.location.href = {json.dumps(url)};

                    // Wait for navigation to complete
                    await new Promise((resolve, reject) => {{
                        const startTime = Date.now();
                        const timeoutMs = {timeout * 1000};

                        const checkLoad = () => {{
                            if (document.readyState === 'complete') {{
                                resolve();
                            }} else if (Date.now() - startTime > timeoutMs) {{
                                reject(new Error('Page load timeout'));
                            }} else {{
                                setTimeout(checkLoad, 100);
                            }}
                        }};

                        if (document.readyState === 'complete') {{
                            resolve();
                        }} else {{
                            window.addEventListener('load', resolve, {{ once: true }});
                            setTimeout(() => reject(new Error('Page load timeout')), timeoutMs);
                        }}
                    }});

                    return {{ ok: true, url: window.location.href }};
                }})();
            """

        result = self.executor.execute(nav_code, timeout=timeout + 5 if wait else 10.0)
        return result

    def go_back(self) -> dict[str, Any]:
        """Go back to the previous page in browser history."""
        code = "window.history.back(), true)"
        result = self.executor.execute(code, timeout=10.0)
        return result

    def go_forward(self) -> dict[str, Any]:
        """Go forward to the next page in browser history."""
        code = "window.history.forward(), true)"
        result = self.executor.execute(code, timeout=10.0)
        return result

    def reload_page(self, hard: bool = False) -> dict[str, Any]:
        """
        Reload the current page.

        Args:
            hard: If True, bypass cache (hard reload)

        Returns:
            Result dictionary
        """
        if hard:
            code = "window.location.reload(true), true)"
        else:
            code = "window.location.reload(), true)"

        result = self.executor.execute(code, timeout=10.0)
        return result

    def scroll_page_up(self) -> dict[str, Any]:
        """Scroll up one page (one viewport height)."""
        code = "window.scrollBy(0, -window.innerHeight), true)"
        result = self.executor.execute(code, timeout=10.0)
        return result

    def scroll_page_down(self) -> dict[str, Any]:
        """Scroll down one page (one viewport height)."""
        code = "window.scrollBy(0, window.innerHeight), true)"
        result = self.executor.execute(code, timeout=10.0)
        return result

    def scroll_to_top(self) -> dict[str, Any]:
        """Scroll to the top of the page."""
        code = "window.scrollTo(0, 0), true)"
        result = self.executor.execute(code, timeout=10.0)
        return result

    def scroll_to_bottom(self) -> dict[str, Any]:
        """Scroll to the bottom of the page."""
        code = "window.scrollTo(0, document.body.scrollHeight), true)"
        result = self.executor.execute(code, timeout=10.0)
        return result
