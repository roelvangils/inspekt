"""
Interaction command handlers.

Implements: click_element, type_text
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from inspekt.core.schemas.interaction import (
    ClickElementParams,
    ClickElementResponse,
    TypeTextParams,
    TypeTextResponse,
)

if TYPE_CHECKING:
    from inspekt.services.bridge_executor import BridgeExecutor
    from inspekt.services.script_loader import ScriptLoader

logger = logging.getLogger(__name__)


def get_executor() -> BridgeExecutor:
    """Get the bridge executor instance."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


def get_script_loader() -> ScriptLoader:
    """Get the script loader instance."""
    from inspekt.services.script_loader import ScriptLoader

    return ScriptLoader()


async def click_element(params: ClickElementParams) -> ClickElementResponse:
    """
    Click an element by CSS selector.

    Supports single, double, and right-click.
    The selector '$0' targets the DevTools-inspected element.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load click_element.js script
        script = await script_loader.load_script_async("click_element.js")

        # Substitute placeholders
        script = script_loader.substitute_placeholders(
            script,
            {
                "SELECTOR": params.selector,
                "CLICK_TYPE": params.click_type or "single",
            },
        )

        result = await asyncio.to_thread(executor.execute, script, 10.0)

        if result.get("ok"):
            data = result.get("result", {})
            return ClickElementResponse(
                success=True,
                element_found=True,
                element_text=data.get("element_text"),
                message="Element clicked successfully",
            )
        else:
            return ClickElementResponse(
                success=False,
                element_found=False,
                element_text=None,
                message=result.get("error", "Click failed"),
            )

    except Exception as e:
        logger.error(f"Click element error: {e}")
        return ClickElementResponse(
            success=False,
            element_found=False,
            element_text=None,
            message=f"Error: {e!s}",
        )


async def type_text(params: TypeTextParams) -> TypeTextResponse:
    """
    Type text into the currently focused element.

    Simulates realistic typing with configurable speed.
    Optionally submits the form or presses Enter after typing.
    """
    executor = get_executor()

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
        result = await asyncio.to_thread(executor.execute, code, timeout)

        if result.get("ok"):
            data = result.get("result", {})
            return TypeTextResponse(
                success=True,
                characters_typed=data.get("characters_typed", len(params.text)),
                message="Text typed successfully",
            )
        else:
            return TypeTextResponse(
                success=False,
                characters_typed=0,
                message=result.get("error", "Typing failed"),
            )

    except Exception as e:
        logger.error(f"Type text error: {e}")
        return TypeTextResponse(
            success=False,
            characters_typed=0,
            message=f"Error: {e!s}",
        )
