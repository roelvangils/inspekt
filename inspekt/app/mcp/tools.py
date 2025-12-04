"""
MCP Tool Implementations

Implements all MCP tools for browser automation and inspection.
Tools are async functions that accept Pydantic models and return Pydantic responses.
"""

import asyncio
import json
import logging
from typing import Any

from inspekt.app.mcp import schemas
from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader
from inspekt.services.autocomplete_service import get_autocomplete_service

logger = logging.getLogger(__name__)


class ToolProvider:
    """Provides MCP tool implementations."""

    def __init__(self, executor: BridgeExecutor, script_loader: ScriptLoader):
        """
        Initialize tool provider.

        Args:
            executor: BridgeExecutor instance for browser communication
            script_loader: ScriptLoader instance for loading JavaScript files
        """
        self.executor = executor
        self.script_loader = script_loader

    # ========================================================================
    # Navigation Tools
    # ========================================================================

    async def navigate_to_url(
        self, params: schemas.NavigateToUrlParams
    ) -> schemas.NavigateResponse:
        """
        Navigate to a URL.

        Args:
            params: Navigation parameters

        Returns:
            NavigateResponse with success status and page info
        """
        try:
            # Validate URL
            if not params.url.startswith(("http://", "https://")):
                return schemas.NavigateResponse(
                    success=False,
                    url=params.url,
                    title="",
                    message="URL must start with http:// or https://",
                )

            # Build navigation code
            wait_condition = ""
            if params.wait_for == "load":
                wait_condition = "await new Promise(resolve => window.addEventListener('DOMContentLoaded', resolve, {once: true}));"
            elif params.wait_for == "networkidle":
                # Simple network idle detection (wait for no requests for 500ms)
                wait_condition = """
                await new Promise(resolve => {
                    let timeout;
                    const resetTimeout = () => {
                        clearTimeout(timeout);
                        timeout = setTimeout(resolve, 500);
                    };
                    resetTimeout();
                    // Monitor fetch/xhr (simplified)
                    const origFetch = window.fetch;
                    window.fetch = function(...args) {
                        resetTimeout();
                        return origFetch.apply(this, args).finally(resetTimeout);
                    };
                });
                """

            code = f"""
            (async () => {{
                window.location.href = {json.dumps(params.url)};
                {wait_condition}
                return {{
                    url: window.location.href,
                    title: document.title
                }};
            }})()
            """

            result = await asyncio.to_thread(
            self.executor.execute, code, 30.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                return schemas.NavigateResponse(
                    success=True,
                    url=data.get("url", params.url),
                    title=data.get("title", ""),
                    message="Navigation successful",
                )
            else:
                return schemas.NavigateResponse(
                    success=False,
                    url=params.url,
                    title="",
                    message=f"Navigation failed: {result.get('error', 'Unknown error')}",
                )

        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return schemas.NavigateResponse(
                success=False, url=params.url, title="", message=f"Error: {str(e)}"
            )

    async def go_back(self) -> schemas.NavigateResponse:
        """Navigate browser history backward."""
        try:
            code = """
            (async () => {
                window.history.back();
                await new Promise(resolve => setTimeout(resolve, 500));
                return {
                    url: window.location.href,
                    title: document.title
                };
            })()
            """

            result = await asyncio.to_thread(
            self.executor.execute, code, 10.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                return schemas.NavigateResponse(
                    success=True,
                    url=data.get("url", ""),
                    title=data.get("title", ""),
                    message="Navigated back",
                )
            else:
                return schemas.NavigateResponse(
                    success=False,
                    url="",
                    title="",
                    message=f"Failed: {result.get('error', 'Unknown error')}",
                )

        except Exception as e:
            logger.error(f"Go back error: {e}")
            return schemas.NavigateResponse(
                success=False, url="", title="", message=f"Error: {str(e)}"
            )

    async def reload_page(self, hard: bool = False) -> schemas.NavigateResponse:
        """Reload current page."""
        try:
            code = f"""
            (async () => {{
                window.location.reload({json.dumps(hard)});
                await new Promise(resolve => setTimeout(resolve, 1000));
                return {{
                    url: window.location.href,
                    title: document.title
                }};
            }})()
            """

            result = await asyncio.to_thread(
            self.executor.execute, code, 15.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                return schemas.NavigateResponse(
                    success=True,
                    url=data.get("url", ""),
                    title=data.get("title", ""),
                    message="Page reloaded",
                )
            else:
                return schemas.NavigateResponse(
                    success=False,
                    url="",
                    title="",
                    message=f"Failed: {result.get('error', 'Unknown error')}",
                )

        except Exception as e:
            logger.error(f"Reload error: {e}")
            return schemas.NavigateResponse(
                success=False, url="", title="", message=f"Error: {str(e)}"
            )

    # ========================================================================
    # JavaScript Execution
    # ========================================================================

    async def execute_javascript(
        self, params: schemas.ExecuteJavaScriptParams
    ) -> schemas.ExecuteJavaScriptResponse:
        """Execute arbitrary JavaScript code."""
        try:
            result = await asyncio.to_thread(

                self.executor.execute, params.code, params.timeout or 30

            )

            if result.get("ok"):
                return schemas.ExecuteJavaScriptResponse(
                    success=True,
                    result=result.get("result"),
                    console_output=result.get("console_output"),
                    error=None,
                )
            else:
                return schemas.ExecuteJavaScriptResponse(
                    success=False,
                    result=None,
                    console_output=None,
                    error=result.get("error", "Execution failed"),
                )

        except Exception as e:
            logger.error(f"JavaScript execution error: {e}")
            return schemas.ExecuteJavaScriptResponse(
                success=False, result=None, console_output=None, error=str(e)
            )

    # ========================================================================
    # Data Extraction Tools
    # ========================================================================

    async def extract_links(
        self, params: schemas.ExtractLinksParams
    ) -> schemas.ExtractLinksResponse:
        """Extract links from current page."""
        try:
            # Load the extract_links.js script
            script = await self.script_loader.load_script_async("extract_links.js")

            # Execute the script
            result = await asyncio.to_thread(

                self.executor.execute, script, 15.0

            )

            if result.get("ok"):
                links_data = result.get("result", [])

                # Filter by type if requested
                if params.filter_type and params.filter_type != "all":
                    links_data = [
                        link for link in links_data if link.get("type") == params.filter_type
                    ]

                # Filter anchors if not included
                if not params.include_anchors:
                    links_data = [
                        link for link in links_data if link.get("type") != "anchor"
                    ]

                # Convert to Pydantic models
                links = [
                    schemas.LinkInfo(
                        url=link.get("url", ""),
                        text=link.get("text", ""),
                        title=link.get("title"),
                        type=link.get("type", "internal"),
                    )
                    for link in links_data
                ]

                return schemas.ExtractLinksResponse(
                    success=True, links=links, count=len(links)
                )
            else:
                return schemas.ExtractLinksResponse(
                    success=False, links=[], count=0
                )

        except Exception as e:
            logger.error(f"Extract links error: {e}")
            return schemas.ExtractLinksResponse(success=False, links=[], count=0)

    async def extract_outline(self) -> schemas.ExtractOutlineResponse:
        """Extract page heading hierarchy."""
        try:
            # Load the extract_outline.js script
            script = await self.script_loader.load_script_async("extract_outline.js")

            result = await asyncio.to_thread(
                self.executor.execute, script, 15.0
            )

            if result.get("ok"):
                result_data = result.get("result", {})
                # The script returns {"headings": [...]}
                outline_data = result_data.get("headings", []) if isinstance(result_data, dict) else []

                # Convert to Pydantic models
                outline = [
                    schemas.OutlineItem(
                        level=item.get("level", 1),
                        text=item.get("text", ""),
                        id=item.get("id"),
                    )
                    for item in outline_data
                ]

                return schemas.ExtractOutlineResponse(
                    success=True, outline=outline, count=len(outline)
                )
            else:
                return schemas.ExtractOutlineResponse(success=False, outline=[], count=0)

        except Exception as e:
            logger.error(f"Extract outline error: {e}")
            return schemas.ExtractOutlineResponse(success=False, outline=[], count=0)

    async def extract_page_info(self) -> schemas.PageInfoResponse:
        """Extract comprehensive page metadata."""
        try:
            # Load extended_info.js script
            script = await self.script_loader.load_script_async("extended_info.js")

            result = await asyncio.to_thread(
            self.executor.execute, script, 15.0
        )

            if result.get("ok"):
                data = result.get("result", {})

                return schemas.PageInfoResponse(
                    success=True,
                    url=data.get("url", ""),
                    title=data.get("title", ""),
                    description=data.get("description"),
                    language=data.get("language"),
                    author=data.get("author"),
                    keywords=data.get("keywords"),
                    og_title=data.get("og_title"),
                    og_description=data.get("og_description"),
                    og_image=data.get("og_image"),
                    canonical_url=data.get("canonical_url"),
                    viewport_width=data.get("viewport_width", 0),
                    viewport_height=data.get("viewport_height", 0),
                )
            else:
                # Return minimal response on error
                return schemas.PageInfoResponse(
                    success=False,
                    url="",
                    title="",
                    viewport_width=0,
                    viewport_height=0,
                )

        except Exception as e:
            logger.error(f"Extract page info error: {e}")
            return schemas.PageInfoResponse(
                success=False, url="", title="", viewport_width=0, viewport_height=0
            )

    async def extract_article(self) -> schemas.ExtractArticleResponse:
        """Extract main article content using Mozilla Readability."""
        try:
            # Load extract_article.js script
            script = await self.script_loader.load_script_async("extract_article.js")

            result = await asyncio.to_thread(
            self.executor.execute, script, 15.0
        )

            if result.get("ok"):
                data = result.get("result", {})

                return schemas.ExtractArticleResponse(
                    success=True,
                    title=data.get("title"),
                    byline=data.get("byline"),
                    content=data.get("textContent", ""),
                    excerpt=data.get("excerpt"),
                    length=len(data.get("textContent", "")),
                )
            else:
                return schemas.ExtractArticleResponse(
                    success=False, content="", length=0
                )

        except Exception as e:
            logger.error(f"Extract article error: {e}")
            return schemas.ExtractArticleResponse(success=False, content="", length=0)

    # ========================================================================
    # Element Interaction Tools
    # ========================================================================

    async def click_element(
        self, params: schemas.ClickElementParams
    ) -> schemas.ClickElementResponse:
        """Click an element by selector."""
        try:
            # Load click_element.js script
            script = await self.script_loader.load_script_async("click_element.js")

            # Substitute placeholders
            script = self.script_loader.substitute_placeholders(
                script,
                {
                    "SELECTOR": params.selector,
                    "CLICK_TYPE": params.click_type or "single",
                },
            )

            result = await asyncio.to_thread(
            self.executor.execute, script, 10.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                return schemas.ClickElementResponse(
                    success=True,
                    element_found=True,
                    element_text=data.get("element_text"),
                    message="Element clicked successfully",
                )
            else:
                return schemas.ClickElementResponse(
                    success=False,
                    element_found=False,
                    element_text=None,
                    message=result.get("error", "Click failed"),
                )

        except Exception as e:
            logger.error(f"Click element error: {e}")
            return schemas.ClickElementResponse(
                success=False,
                element_found=False,
                element_text=None,
                message=f"Error: {str(e)}",
            )

    async def type_text(
        self, params: schemas.TypeTextParams
    ) -> schemas.TypeTextResponse:
        """Type text into focused element."""
        try:
            # Build typing code based on speed
            speed_delays = {
                "instant": 0,
                "fast": 50,
                "normal": 100,
                "slow": 200,
            }
            delay = speed_delays.get(params.typing_speed or "normal", 100)

            code = f"""
            (async () => {{
                const text = {json.dumps(params.text)};
                const element = document.activeElement;

                if (!element || element.tagName === 'BODY') {{
                    throw new Error('No element focused');
                }}

                // Type each character
                for (let i = 0; i < text.length; i++) {{
                    const char = text[i];
                    element.value = (element.value || '') + char;

                    // Trigger input event
                    element.dispatchEvent(new Event('input', {{ bubbles: true }}));

                    // Delay between characters
                    if ({delay} > 0) {{
                        await new Promise(resolve => setTimeout(resolve, {delay}));
                    }}
                }}

                // Submit if requested
                if ({json.dumps(params.submit)}) {{
                    const form = element.closest('form');
                    if (form) {{
                        form.submit();
                    }} else {{
                        // Press Enter
                        element.dispatchEvent(new KeyboardEvent('keydown', {{ key: 'Enter', bubbles: true }}));
                    }}
                }}

                return {{
                    characters_typed: text.length
                }};
            }})()
            """

            timeout = max(30, len(params.text) * delay / 1000 + 10)
            result = await asyncio.to_thread(

                self.executor.execute, code, timeout

            )

            if result.get("ok"):
                data = result.get("result", {})
                return schemas.TypeTextResponse(
                    success=True,
                    characters_typed=data.get("characters_typed", len(params.text)),
                    message="Text typed successfully",
                )
            else:
                return schemas.TypeTextResponse(
                    success=False,
                    characters_typed=0,
                    message=result.get("error", "Typing failed"),
                )

        except Exception as e:
            logger.error(f"Type text error: {e}")
            return schemas.TypeTextResponse(
                success=False, characters_typed=0, message=f"Error: {str(e)}"
            )

    # ========================================================================
    # Inspection Tools
    # ========================================================================

    async def get_page_info(self) -> schemas.GetPageInfoResponse:
        """Get lightweight current page information."""
        try:
            code = """
            ({
                url: window.location.href,
                title: document.title,
                viewport_width: window.innerWidth,
                viewport_height: window.innerHeight,
                scroll_x: window.scrollX,
                scroll_y: window.scrollY
            })
            """

            result = await asyncio.to_thread(
            self.executor.execute, code, 5.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                return schemas.GetPageInfoResponse(
                    success=True,
                    url=data.get("url", ""),
                    title=data.get("title", ""),
                    viewport_width=int(data.get("viewport_width", 0)),
                    viewport_height=int(data.get("viewport_height", 0)),
                    scroll_x=int(data.get("scroll_x", 0)),
                    scroll_y=int(data.get("scroll_y", 0)),
                )
            else:
                return schemas.GetPageInfoResponse(
                    success=False,
                    url="",
                    title="",
                    viewport_width=0,
                    viewport_height=0,
                    scroll_x=0,
                    scroll_y=0,
                )

        except Exception as e:
            logger.error(f"Get page info error: {e}")
            return schemas.GetPageInfoResponse(
                success=False,
                url="",
                title="",
                viewport_width=0,
                viewport_height=0,
                scroll_x=0,
                scroll_y=0,
            )

    async def take_screenshot(
        self, params: schemas.TakeScreenshotParams
    ) -> schemas.TakeScreenshotResponse:
        """Take a screenshot of viewport, page, or element."""
        try:
            # Load screenshot script (check if screenshot_unified.js exists)
            try:
                script = await self.script_loader.load_script_async("screenshot_unified.js")
            except FileNotFoundError:
                # Fallback: simple screenshot implementation
                return schemas.TakeScreenshotResponse(
                    success=False,
                    data=None,
                    format=params.format or "png",
                    width=0,
                    height=0,
                    message="Screenshot script not available",
                )

            # Substitute placeholders
            script = self.script_loader.substitute_placeholders(
                script,
                {
                    "TARGET": params.target or "viewport",
                    "SELECTOR": params.selector or "",
                    "FORMAT": params.format or "png",
                    "QUALITY": params.quality or 90,
                },
            )

            result = await asyncio.to_thread(
            self.executor.execute, script, 30.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                return schemas.TakeScreenshotResponse(
                    success=True,
                    data=data.get("data"),
                    format=data.get("format", params.format or "png"),
                    width=data.get("width", 0),
                    height=data.get("height", 0),
                    message="Screenshot captured",
                )
            else:
                return schemas.TakeScreenshotResponse(
                    success=False,
                    data=None,
                    format=params.format or "png",
                    width=0,
                    height=0,
                    message=result.get("error", "Screenshot failed"),
                )

        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return schemas.TakeScreenshotResponse(
                success=False,
                data=None,
                format=params.format or "png",
                width=0,
                height=0,
                message=f"Error: {str(e)}",
            )

    # ========================================================================
    # Selection and Storage Tools
    # ========================================================================

    async def get_selected_text(
        self, params: schemas.GetSelectedTextParams
    ) -> schemas.GetSelectedTextResponse:
        """Get currently selected text."""
        try:
            # Load get_selection.js script
            script = await self.script_loader.load_script_async("get_selection.js")

            result = await asyncio.to_thread(
            self.executor.execute, script, 5.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                content_format = params.format or "text"

                # Extract content based on format
                content = data.get(content_format, data.get("text", ""))

                return schemas.GetSelectedTextResponse(
                    success=True,
                    content=content,
                    format=content_format,
                    length=len(content),
                )
            else:
                return schemas.GetSelectedTextResponse(
                    success=False, content="", format=params.format or "text", length=0
                )

        except Exception as e:
            logger.error(f"Get selected text error: {e}")
            return schemas.GetSelectedTextResponse(
                success=False, content="", format=params.format or "text", length=0
            )

    async def get_cookies(self) -> schemas.GetCookiesResponse:
        """Get cookies for current page."""
        try:
            # Load cookies.js script
            script = await self.script_loader.load_script_async("cookies.js")

            result = await asyncio.to_thread(
            self.executor.execute, script, 10.0
        )

            if result.get("ok"):
                data = result.get("result", {})
                cookies_data = data.get("cookies", [])

                # Convert to Pydantic models
                cookies = [
                    schemas.CookieInfo(
                        name=cookie.get("name", ""),
                        value=cookie.get("value", ""),
                        domain=cookie.get("domain", ""),
                        path=cookie.get("path", "/"),
                        secure=cookie.get("secure", False),
                        httpOnly=cookie.get("httpOnly", False),
                        sameSite=cookie.get("sameSite"),
                        expires=cookie.get("expires"),
                        session=cookie.get("session", True),
                        size=cookie.get("size", 0),
                        party=cookie.get("party"),
                    )
                    for cookie in cookies_data
                ]

                return schemas.GetCookiesResponse(
                    success=True, cookies=cookies, count=len(cookies)
                )
            else:
                return schemas.GetCookiesResponse(success=False, cookies=[], count=0)

        except Exception as e:
            logger.error(f"Get cookies error: {e}")
            return schemas.GetCookiesResponse(success=False, cookies=[], count=0)

    async def set_cookie(
        self, params: schemas.SetCookieParams
    ) -> schemas.SetCookieResponse:
        """Set a cookie."""
        try:
            # Build cookie string
            cookie_parts = [f"{params.name}={params.value}"]

            if params.domain:
                cookie_parts.append(f"domain={params.domain}")
            if params.path:
                cookie_parts.append(f"path={params.path}")
            if params.secure:
                cookie_parts.append("secure")
            if params.sameSite:
                cookie_parts.append(f"samesite={params.sameSite}")
            if params.expires:
                cookie_parts.append(f"expires={params.expires}")

            cookie_string = "; ".join(cookie_parts)

            code = f"""
            (function() {{
                document.cookie = {json.dumps(cookie_string)};
                return {{ success: true }};
            }})()
            """

            result = await asyncio.to_thread(
            self.executor.execute, code, 5.0
        )

            if result.get("ok"):
                return schemas.SetCookieResponse(
                    success=True, message="Cookie set successfully"
                )
            else:
                return schemas.SetCookieResponse(
                    success=False, message=result.get("error", "Failed to set cookie")
                )

        except Exception as e:
            logger.error(f"Set cookie error: {e}")
            return schemas.SetCookieResponse(success=False, message=f"Error: {str(e)}")

    # ========================================================================
    # Accessibility Tools
    # ========================================================================

    async def check_autocomplete(
        self, params: schemas.CheckAutocompleteParams
    ) -> schemas.CheckAutocompleteResponse:
        """
        Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5.

        Analyzes all form fields using multi-language heuristics based on the
        Autocomplete-Check extension logic. Returns violations, warnings, and
        recommendations with confidence scores.

        Args:
            params: Check configuration (confidence threshold, include hidden/disabled)

        Returns:
            Analysis results with summary statistics and per-field predictions
        """
        try:
            service = get_autocomplete_service()

            # Run the autocomplete check using the service
            result = await service.check_autocomplete(
                bridge_executor=self.executor,
                confidence_threshold=params.confidence_threshold or 0.5,
                include_hidden=params.include_hidden or False,
                include_disabled=params.include_disabled or False,
            )

            # Check if there was an error
            if "error" in result and result.get("summary", {}).get("analyzed", 0) == 0:
                return schemas.CheckAutocompleteResponse(
                    success=False,
                    message=result.get("error", "Autocomplete check failed"),
                )

            # Return successful result
            return schemas.CheckAutocompleteResponse(
                success=True,
                summary=result.get("summary"),
                fields=result.get("fields"),
                message=f"Analyzed {result.get('summary', {}).get('analyzed', 0)} form fields: "
                f"{result.get('summary', {}).get('violations', 0)} violations, "
                f"{result.get('summary', {}).get('warnings', 0)} warnings",
            )

        except Exception as e:
            logger.error(f"Autocomplete check error: {e}")
            return schemas.CheckAutocompleteResponse(
                success=False, message=f"Error: {str(e)}"
            )

    async def run_axe(
        self, params: schemas.RunAxeParams
    ) -> schemas.RunAxeResponse:
        """
        Run axe-core accessibility tests on current page.

        Performs WCAG conformance testing using the industry-standard axe-core
        library. Returns violations with impact levels, affected elements,
        and remediation guidance.

        Args:
            params: Axe configuration including WCAG level, rule, and scope

        Returns:
            Audit results with violations, summary, and optional passes/incomplete
        """
        try:
            # Build axe configuration
            if params.rule:
                # Single rule check
                config = {
                    "runOnly": {"type": "rule", "values": [params.rule]},
                    "resultTypes": ["violations"]
                }
            else:
                # WCAG level-based check
                level_mapping = {
                    "2a": ["wcag2a"],
                    "2aa": ["wcag2a", "wcag2aa"],
                    "2aaa": ["wcag2a", "wcag2aa", "wcag2aaa"],
                    "21a": ["wcag2a", "wcag21a"],
                    "21aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
                    "22aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
                }
                axe_tags = level_mapping.get(
                    params.level or "21aa",
                    ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
                )
                config = {
                    "runOnly": {"type": "tag", "values": axe_tags},
                    "resultTypes": ["violations"]
                }

            if params.include_passes:
                config["resultTypes"].append("passes")
            if params.include_incomplete:
                config["resultTypes"].append("incomplete")

            # Disable badges for MCP (no visual output needed)
            config["__showBadges"] = False
            config["__interactiveBadges"] = False

            # Build context expression
            context_expr = "document"
            if params.selector:
                if params.exclude:
                    context_expr = json.dumps({
                        "include": params.selector,
                        "exclude": params.exclude
                    })
                else:
                    context_expr = json.dumps(params.selector)
            elif params.exclude:
                context_expr = json.dumps({"exclude": params.exclude})

            # Load axe-core library
            axe_lib = await self.script_loader.load_script_async(
                "vendor/axe-core.min.js"
            )

            # Load run_axe script
            run_axe_script = await self.script_loader.load_script_async("run_axe.js")

            # Substitute config placeholder
            run_axe_script = run_axe_script.replace(
                "__AXE_CONFIG__", json.dumps(config)
            )
            # Substitute context (first occurrence only)
            run_axe_script = run_axe_script.replace("document", context_expr, 1)

            # First inject axe-core library
            axe_lib_wrapped = (
                f"(function() {{ {axe_lib} return typeof axe !== 'undefined'; }})()"
            )
            inject_result = await asyncio.to_thread(
                self.executor.execute, axe_lib_wrapped, 10.0
            )

            if not inject_result.get("ok") or not inject_result.get("result"):
                return schemas.RunAxeResponse(
                    success=False,
                    message=f"Failed to load axe-core: {inject_result.get('error', 'axe undefined')}"
                )

            # Execute audit script
            result = await asyncio.to_thread(
                self.executor.execute, run_axe_script, 60.0
            )

            if not result.get("ok"):
                return schemas.RunAxeResponse(
                    success=False,
                    message=f"Axe execution failed: {result.get('error')}"
                )

            data = result.get("result", {})

            if not data.get("ok"):
                return schemas.RunAxeResponse(
                    success=False,
                    message=f"Axe audit error: {data.get('error')}"
                )

            # Parse violations into structured format
            violations = []
            for v in data.get("violations", []):
                nodes = [
                    schemas.AxeNode(
                        target=n.get("target", []),
                        html=n.get("html", ""),
                        impact=n.get("impact", "unknown"),
                        failure_summary=n.get("failureSummary")
                    )
                    for n in v.get("nodes", [])
                ]
                violations.append(schemas.AxeViolation(
                    id=v.get("id", ""),
                    impact=v.get("impact", "unknown"),
                    description=v.get("description", ""),
                    help=v.get("help", ""),
                    help_url=v.get("helpUrl", ""),
                    nodes=nodes,
                    node_count=len(nodes)
                ))

            # Parse summary
            summary_data = data.get("summary", {})
            summary = schemas.AxeSummary(
                violation_count=summary_data.get("violationCount", 0),
                pass_count=summary_data.get("passCount", 0),
                incomplete_count=summary_data.get("incompleteCount", 0),
                critical_count=summary_data.get("criticalCount", 0),
                serious_count=summary_data.get("seriousCount", 0),
                moderate_count=summary_data.get("moderateCount", 0),
                minor_count=summary_data.get("minorCount", 0)
            )

            return schemas.RunAxeResponse(
                success=True,
                url=data.get("url", ""),
                violations=violations,
                passes=data.get("passes", []) if params.include_passes else [],
                incomplete=data.get("incomplete", []) if params.include_incomplete else [],
                summary=summary,
                axe_version=data.get("axeVersion"),
                message=f"Found {len(violations)} accessibility violation(s)"
            )

        except Exception as e:
            logger.error(f"Run axe error: {e}")
            return schemas.RunAxeResponse(
                success=False,
                message=f"Error: {str(e)}"
            )

    # ========================================================================
    # Network Tools
    # ========================================================================

    async def get_network_requests(
        self, params: schemas.GetNetworkRequestsParams
    ) -> schemas.GetNetworkRequestsResponse:
        """
        Get network requests from the current page using Performance API.

        Returns detailed information about all resources loaded by the page,
        including timing, size, and type information.

        Note: Uses Performance API which has limitations:
        - No HTTP status codes
        - No request/response headers
        - Buffer limit of ~150-250 entries

        Args:
            params: Filter and sort options

        Returns:
            Network request entries with summary statistics
        """
        try:
            # Load the get_network.js script
            script = await self.script_loader.load_script_async("get_network.js")

            result = await asyncio.to_thread(
                self.executor.execute, script, 30.0
            )

            if result.get("ok"):
                data = result.get("result", {})

                if data.get("error"):
                    return schemas.GetNetworkRequestsResponse(
                        success=False,
                        url="",
                        timestamp="",
                        entries=[],
                        summary={},
                        message=data["error"],
                    )

                entries = data.get("entries", [])
                summary = data.get("summary", {})

                # Filter by type if specified
                if params.resource_type:
                    entries = [e for e in entries if e.get("type") == params.resource_type]
                    # Update summary counts
                    summary["totalRequests"] = len(entries)
                    summary["totalTransferSize"] = sum(e.get("transferSize", 0) for e in entries)

                # Filter external only
                if params.external_only:
                    entries = [e for e in entries if e.get("external")]

                # Sort entries
                sort_keys = {
                    "start": lambda e: e.get("startTime", 0),
                    "time": lambda e: -e.get("timing", {}).get("total", 0),
                    "size": lambda e: -e.get("transferSize", 0),
                    "name": lambda e: e.get("name", "").lower(),
                    "type": lambda e: e.get("type", ""),
                }

                sort_by = params.sort_by or "start"
                if sort_by in sort_keys:
                    entries = sorted(entries, key=sort_keys[sort_by])

                # Apply limit
                if params.limit:
                    entries = entries[:params.limit]

                return schemas.GetNetworkRequestsResponse(
                    success=True,
                    url=data.get("url", ""),
                    timestamp=data.get("timestamp", ""),
                    entries=entries,
                    summary=summary,
                    message=f"Found {len(entries)} network requests",
                )
            else:
                return schemas.GetNetworkRequestsResponse(
                    success=False,
                    url="",
                    timestamp="",
                    entries=[],
                    summary={},
                    message=result.get("error", "Failed to get network data"),
                )

        except Exception as e:
            logger.error(f"Get network requests error: {e}")
            return schemas.GetNetworkRequestsResponse(
                success=False,
                url="",
                timestamp="",
                entries=[],
                summary={},
                message=f"Error: {str(e)}",
            )

    async def get_har(
        self, params: schemas.GetHARParams
    ) -> schemas.GetHARResponse:
        """
        Get full network data from DevTools (HAR format).

        This tool requires Chrome DevTools to be open (F12) for the active tab.
        It provides complete network data including:
        - HTTP status codes (200, 404, 500, etc.)
        - Request and response headers
        - Full timing breakdown
        - Initiator information

        If DevTools is not open, returns an error with a hint to use
        get_network_requests instead.

        Args:
            params: Filter and sort options

        Returns:
            HAR entries with status codes, headers, and summary statistics
        """
        import requests as http_requests

        try:
            # Get HAR data from bridge server (which gets it from DevTools)
            response = http_requests.get(
                "http://127.0.0.1:8765/network/har",
                timeout=20.0
            )
            data = response.json()

            if not data.get("ok", False):
                return schemas.GetHARResponse(
                    success=False,
                    source="devtools",
                    url="",
                    timestamp="",
                    entries=[],
                    summary={},
                    message=data.get("error", "Failed to get HAR data. Is DevTools open (F12)?"),
                )

            entries = data.get("entries", [])
            summary = data.get("summary", {})

            # Filter by type if specified
            if params.resource_type:
                entries = [e for e in entries if e.get("type") == params.resource_type]

            # Filter errors only
            if params.errors_only:
                entries = [e for e in entries if e.get("status", 0) >= 400]

            # Sort entries
            sort_keys = {
                "start": lambda e: e.get("startedDateTime", ""),
                "time": lambda e: -(e.get("timing", {}).get("total", 0) if isinstance(e.get("timing"), dict) else 0),
                "size": lambda e: -e.get("transferSize", 0),
                "name": lambda e: e.get("name", "").lower(),
                "type": lambda e: e.get("type", ""),
                "status": lambda e: e.get("status", 0),
            }

            sort_by = params.sort_by or "start"
            if sort_by in sort_keys:
                entries = sorted(entries, key=sort_keys[sort_by])

            # Apply limit
            if params.limit:
                entries = entries[:params.limit]

            # Update summary for filtered results
            if params.resource_type or params.errors_only:
                summary["totalRequests"] = len(entries)
                summary["totalTransferSize"] = sum(e.get("transferSize", 0) for e in entries)

            return schemas.GetHARResponse(
                success=True,
                source="devtools",
                url=data.get("url", ""),
                timestamp=data.get("timestamp", ""),
                entries=entries,
                summary=summary,
                message=f"Found {len(entries)} requests with status codes and headers",
            )

        except http_requests.exceptions.ConnectionError:
            return schemas.GetHARResponse(
                success=False,
                source="devtools",
                url="",
                timestamp="",
                entries=[],
                summary={},
                message="Bridge server not running. Start it with: inspekt start",
            )
        except http_requests.exceptions.Timeout:
            return schemas.GetHARResponse(
                success=False,
                source="devtools",
                url="",
                timestamp="",
                entries=[],
                summary={},
                message="HAR request timed out. Is Chrome DevTools open (F12)?",
            )
        except Exception as e:
            logger.error(f"Get HAR error: {e}")
            return schemas.GetHARResponse(
                success=False,
                source="devtools",
                url="",
                timestamp="",
                entries=[],
                summary={},
                message=f"Error: {str(e)}",
            )

    # ========================================================================
    # Console Tools
    # ========================================================================

    async def get_console_logs(
        self, params: schemas.GetConsoleLogsParams
    ) -> schemas.GetConsoleLogsResponse:
        """
        Get captured browser console messages.

        Returns console.log, console.error, console.warn, console.info, and
        console.debug messages that were captured since the page loaded.
        Console messages are automatically captured when pages load via
        hooks injected by the browser extension.

        Useful for:
        - Debugging JavaScript errors after user interactions
        - Monitoring application logging output
        - Checking for deprecation warnings
        - Verifying no errors occurred during automated testing

        Note: Only captures messages logged AFTER the page loads and console
        hooks are injected. Buffer is limited to 1000 messages.

        Args:
            params: Filter options (level, limit)

        Returns:
            List of console log entries with timestamps
        """
        import requests as http_requests

        try:
            # Get console logs from bridge server
            response = http_requests.get(
                "http://127.0.0.1:8765/console/logs",
                timeout=15.0
            )
            data = response.json()

            if not data.get("ok", False):
                return schemas.GetConsoleLogsResponse(
                    success=False,
                    entries=[],
                    count=0,
                    hooked=False,
                    message=data.get("error", "Failed to get console logs"),
                )

            entries = data.get("entries", [])
            hooked = data.get("hooked", False)

            # Filter by level if specified
            if params.level and params.level != "all":
                entries = [e for e in entries if e.get("level") == params.level]

            # Apply limit
            if params.limit and params.limit > 0:
                entries = entries[-params.limit:]  # Get most recent

            # Convert to Pydantic models
            console_entries = [
                schemas.ConsoleEntry(
                    level=e.get("level", "log"),
                    timestamp=e.get("timestamp", ""),
                    message=e.get("message", ""),
                )
                for e in entries
            ]

            return schemas.GetConsoleLogsResponse(
                success=True,
                entries=console_entries,
                count=len(console_entries),
                hooked=hooked,
                message=f"Found {len(console_entries)} console message(s)" + (
                    f" (filtered: {params.level})" if params.level != "all" else ""
                ),
            )

        except http_requests.exceptions.ConnectionError:
            return schemas.GetConsoleLogsResponse(
                success=False,
                entries=[],
                count=0,
                hooked=False,
                message="Bridge server not running. Start it with: inspekt start",
            )
        except http_requests.exceptions.Timeout:
            return schemas.GetConsoleLogsResponse(
                success=False,
                entries=[],
                count=0,
                hooked=False,
                message="Console logs request timed out",
            )
        except Exception as e:
            logger.error(f"Get console logs error: {e}")
            return schemas.GetConsoleLogsResponse(
                success=False,
                entries=[],
                count=0,
                hooked=False,
                message=f"Error: {str(e)}",
            )

    async def clear_console_logs(self) -> schemas.ClearConsoleLogsResponse:
        """
        Clear the browser console message buffer.

        Removes all captured console messages from the browser's buffer.
        New messages will continue to be captured after clearing.

        Useful for:
        - Resetting before a specific test or interaction
        - Clearing old messages to focus on new activity
        - Starting fresh monitoring of console output

        Returns:
            Success status and message
        """
        import requests as http_requests

        try:
            # Clear console logs via bridge server
            response = http_requests.post(
                "http://127.0.0.1:8765/console/clear",
                timeout=15.0
            )
            data = response.json()

            if not data.get("ok", False):
                return schemas.ClearConsoleLogsResponse(
                    success=False,
                    message=data.get("error", "Failed to clear console logs"),
                )

            return schemas.ClearConsoleLogsResponse(
                success=True,
                message="Console buffer cleared",
            )

        except http_requests.exceptions.ConnectionError:
            return schemas.ClearConsoleLogsResponse(
                success=False,
                message="Bridge server not running. Start it with: inspekt start",
            )
        except http_requests.exceptions.Timeout:
            return schemas.ClearConsoleLogsResponse(
                success=False,
                message="Clear console logs request timed out",
            )
        except Exception as e:
            logger.error(f"Clear console logs error: {e}")
            return schemas.ClearConsoleLogsResponse(
                success=False,
                message=f"Error: {str(e)}",
            )
