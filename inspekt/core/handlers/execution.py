"""
Execution command handlers.

Implements: execute_javascript
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from inspekt.core.schemas.execution import (
    ExecuteJavaScriptParams,
    ExecuteJavaScriptResponse,
)

if TYPE_CHECKING:
    from inspekt.services.bridge_executor import BridgeExecutor

logger = logging.getLogger(__name__)


def get_executor() -> BridgeExecutor:
    """Get the bridge executor instance."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


async def execute_javascript(
    params: ExecuteJavaScriptParams,
) -> ExecuteJavaScriptResponse:
    """
    Execute arbitrary JavaScript code in the browser context.

    Returns the result of the expression or any console output.
    """
    executor = get_executor()

    try:
        result = await asyncio.to_thread(
            executor.execute,
            params.code,
            params.timeout or 30,
        )

        if result.get("ok"):
            return ExecuteJavaScriptResponse(
                success=True,
                result=result.get("result"),
                console_output=result.get("console_output"),
                error=None,
            )
        else:
            return ExecuteJavaScriptResponse(
                success=False,
                result=None,
                console_output=None,
                error=result.get("error", "Execution failed"),
            )

    except Exception as e:
        logger.error(f"JavaScript execution error: {e}")
        return ExecuteJavaScriptResponse(
            success=False,
            result=None,
            console_output=None,
            error=str(e),
        )
