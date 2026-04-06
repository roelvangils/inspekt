"""
Unified async JavaScript execution service for MCP and API.

This module provides an async interface for executing JavaScript in the browser,
used by MCP tools and HTTP API endpoints. Unlike the synchronous BridgeClient,
this uses aiohttp for non-blocking HTTP requests.

ARCHITECTURE:
-------------
1. POST to /run - Submit code to browser, get request_id
2. GET /result?request_id=xxx - Long polling to wait for result

This module does NOT:
- Handle interactive prompts (for domain authorization)
- Call sys.exit() on errors
- Do automatic retries with exponential backoff

These are CLI concerns handled separately. This module is for clean async execution.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from inspekt.config import get_bridge_port

logger = logging.getLogger(__name__)


async def execute_javascript(
    code: str,
    timeout: int = 30,
) -> dict[str, Any]:
    """
    Execute JavaScript code in the browser asynchronously.

    This is the async equivalent of BridgeClient.execute(), designed for
    MCP tools and HTTP API endpoints.

    Args:
        code: JavaScript code to execute
        timeout: Timeout in seconds (default 30)

    Returns:
        dict with keys:
            - success: bool - Whether execution succeeded
            - result: Any - The result value (if success)
            - error: str - Error message (if failed)
            - console_output: list - Any console output captured
    """
    bridge_port = get_bridge_port()
    logger.info(f"Executing JavaScript (timeout={timeout}s, code_length={len(code)})")

    try:
        async with aiohttp.ClientSession() as session:
            # Step 1: Submit code to /run endpoint
            async with session.post(
                f"http://127.0.0.1:{bridge_port}/run",
                json={"code": code},
                timeout=aiohttp.ClientTimeout(total=5),  # Quick timeout for submission
            ) as submit_response:
                submit_data = await submit_response.json()

            if not submit_data.get("ok"):
                error = submit_data.get("error", "Unknown error")
                error_message = submit_data.get("message", "")

                # Map specific errors to user-friendly messages
                if error == "browser_not_responding":
                    return {
                        "success": False,
                        "result": None,
                        "console_output": None,
                        "error": error_message or "Browser tab not responding. Try clicking on the tab or refreshing the page.",
                    }
                elif error == "no_browser_connected":
                    return {
                        "success": False,
                        "result": None,
                        "console_output": None,
                        "error": "No browser connected. Make sure a browser with the Inspekt extension is open.",
                    }
                else:
                    return {
                        "success": False,
                        "result": None,
                        "console_output": None,
                        "error": f"Failed to submit code: {error}",
                    }

            request_id = submit_data["request_id"]
            logger.info(f"Code submitted, request_id={request_id}")

            # Step 2: Poll /result endpoint for result (long polling)
            # The bridge server holds the connection until result is ready (up to timeout)
            poll_timeout = aiohttp.ClientTimeout(total=timeout + 10)

            async with session.get(
                f"http://127.0.0.1:{bridge_port}/result",
                params={"request_id": request_id},
                timeout=poll_timeout,
            ) as result_response:
                result_data = await result_response.json()

            # The bridge returns results in two formats:
            # 1. Completed: {ok: true/false, result: ..., error: ...}
            # 2. Pending: {status: "pending"}
            status = result_data.get("status")

            if status == "pending":
                logger.warning(f"Request still pending after timeout")
                return {
                    "success": False,
                    "result": None,
                    "console_output": None,
                    "error": f"No response from browser after {timeout} seconds. The browser tab may be unresponsive.",
                }

            # Completed result (no status field, has ok field)
            if result_data.get("ok"):
                logger.info("JavaScript execution succeeded")
                return {
                    "success": True,
                    "result": result_data.get("result"),
                    "console_output": result_data.get("console_output"),
                    "error": None,
                }
            else:
                error = result_data.get("error", "Execution failed")
                logger.warning(f"JavaScript execution failed: {error}")

                # Check for CSP errors
                if error and ("CSP_BLOCKED" in error or "EvalError" in error or "Content Security Policy" in error):
                    return {
                        "success": False,
                        "result": None,
                        "console_output": None,
                        "error": f"Content Security Policy (CSP) blocks JavaScript execution on this page. Run `inspekt yolo` to bypass.",
                    }

                # Check for domain authorization errors
                if error:
                    error_lower = error.lower()
                    if any(phrase in error_lower for phrase in [
                        "not allowed to access this domain",
                        "domain not authorized",
                        "not authorized"
                    ]):
                        url = result_data.get("url", "")
                        return {
                            "success": False,
                            "result": None,
                            "console_output": None,
                            "error": f"Domain not authorized. Run `inspekt domain add <domain>` to allow access. URL: {url}",
                        }

                return {
                    "success": False,
                    "result": None,
                    "console_output": None,
                    "error": error,
                }

    except aiohttp.ClientError as e:
        logger.error(f"Bridge connection error: {e}")
        return {
            "success": False,
            "result": None,
            "console_output": None,
            "error": f"Bridge connection error: {e}. Is 'inspekt start' running?",
        }
    except TimeoutError:
        logger.error(f"Execution timed out after {timeout}s")
        return {
            "success": False,
            "result": None,
            "console_output": None,
            "error": f"Execution timed out after {timeout}s",
        }
    except Exception as e:
        logger.error(f"Unexpected execution error: {e}")
        return {
            "success": False,
            "result": None,
            "console_output": None,
            "error": f"Error: {str(e)}",
        }
