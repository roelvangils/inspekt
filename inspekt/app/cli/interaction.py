"""
Interaction commands for the Inspekt Browser Bridge CLI.

This module provides commands for browser interaction:
- type: Type text character by character
- paste: Paste text instantly
- click: Click on elements
- double-click: Double-click on elements
- right-click: Right-click (context menu) on elements
- wait: Wait for elements or conditions
"""

from __future__ import annotations

import json
import sys

import click

from inspekt.app.cli.base import builtin_open
from inspekt.config import get_typing_config
from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader


def _focus_browser_if_requested(ctx):
    """Placeholder for browser focus-on-command feature."""
    pass


def _send_text(text, selector, delay_ms, clear=True):
    """Helper function to send text to browser."""
    executor = BridgeExecutor()
    executor.ensure_server_running()

    # Focus the element first if selector provided
    if selector:
        focus_code = f"""
        (function() {{
            const el = document.querySelector('{selector}');
            if (!el) {{
                return {{ error: 'Element not found: {selector}' }};
            }}
            el.focus();
            return {{ ok: true }};
        }})()
        """
        result = executor.execute(focus_code, timeout=60.0)
        if not result.get("ok") or result.get("result", {}).get("error"):
            error = result.get("error") or result.get("result", {}).get("error", "Unknown error")
            click.echo(f"Error focusing element: {error}", err=True)
            sys.exit(1)

    # Load and execute the send_keys script
    script_loader = ScriptLoader()
    try:
        script = script_loader.load_script_sync("send_keys.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Get typing configuration
    typing_config = get_typing_config()
    typo_rate = typing_config['human-like-typo-rate']

    # Replace placeholders with properly escaped values
    # Use JSON encoding for proper JavaScript string escaping
    code = script.replace("TEXT_PLACEHOLDER", json.dumps(text))
    code = code.replace("DELAY_PLACEHOLDER", str(delay_ms))
    code = code.replace("CLEAR_PLACEHOLDER", "true" if clear else "false")
    code = code.replace("TYPO_RATE_PLACEHOLDER", str(typo_rate))

    # Calculate timeout based on text length and delay
    # For human mode (-1), estimate ~300ms per character (including pauses)
    # For other modes, estimate based on actual delay
    if delay_ms == -1:
        # Human mode: estimate 300ms per char (base 240ms + pauses)
        estimated_time = len(text) * 0.3
    elif delay_ms == 0:
        # Fast mode: minimal time
        estimated_time = len(text) * 0.05
    else:
        # Custom speed: calculate from delay
        estimated_time = len(text) * delay_ms / 1000.0

    # Add buffer and enforce minimum
    timeout = max(estimated_time + 10, 60.0)

    try:
        result = executor.execute(code, timeout=timeout)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if response.get("error"):
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
                from inspekt.app.cli.table import print_hint
                print_hint(response['hint'])
            sys.exit(1)

        click.echo(response.get("message", "Text sent successfully"))

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@click.argument("text")
@click.option("--selector", "-s", help="CSS selector to focus before typing")
@click.option("--speed", type=int, help="Typing speed in characters per second (default: fastest, 0: human-like)")
@click.option("--clear/--no-clear", default=True, help="Clear existing text before typing (default: true)")
def type_text(text, selector, speed, clear):
    """
    Type text character by character into the browser.

    Types text into the currently focused input field,
    or into a specific element if --selector is provided.

    By default, clears any existing text and types as fast as possible.
    Use --speed to control typing rate and --no-clear to append instead.

    Examples:
        # Type at maximum speed (clears existing text):
        inspekt type "Hello World"

        # Type with human-like random delays (~50 WPM):
        inspekt type "Hello, how are you?" --speed 0

        # Type at 10 characters per second:
        inspekt type "test@example.com" --speed 10

        # Type without clearing existing text:
        inspekt type "append this" --no-clear

        # Type into a specific field:
        inspekt type "password123" --selector "input[type=password]"
    """
    # Calculate delay in milliseconds from speed (chars/sec)
    if speed == 0:
        # Special case: 0 means human-like typing with random delays
        delay_ms = -1  # Signal to JavaScript to use human mode
    elif speed:
        delay_ms = int(1000 / speed)
    else:
        delay_ms = 0  # Fastest (no delay)

    _send_text(text, selector, delay_ms, clear)


@click.command()
@click.argument("text")
@click.option("--selector", "-s", help="CSS selector to focus before pasting")
@click.option("--clear/--no-clear", default=True, help="Clear existing text before pasting (default: true)")
def paste(text, selector, clear):
    """
    Paste text instantly into the browser.

    Pastes text into the currently focused input field,
    or into a specific element if --selector is provided.

    By default, clears any existing text before pasting.
    This is equivalent to 'inspekt type' with maximum speed.

    Examples:
        # Paste (clears existing text):
        inspekt paste "Hello World"

        # Paste without clearing:
        inspekt paste "append this" --no-clear

        # Paste into specific element:
        inspekt paste "test@example.com" --selector "input[type=email]"
    """
    _send_text(text, selector, 0, clear)


@click.command()
@click.argument("text")
@click.option("--selector", "-s", help="CSS selector to focus before typing")
def send(text, selector):
    """
    [DEPRECATED] Send text to the browser by typing it character by character.

    Please use 'inspekt type' or 'inspekt paste' instead.

    Examples:
        inspekt type "Hello World"
        inspekt paste "test@example.com" --selector "input[type=email]"
    """
    click.echo("Warning: 'inspekt send' is deprecated. Use 'inspekt type' or 'inspekt paste' instead.\n", err=True)
    _send_text(text, selector, 0, clear=True)


@click.command(name="click")
@click.argument("selector", required=False, default="$0")
def click_element(selector):
    """
    Click on an element.

    Uses the stored element from 'inspekt inspect' by default, or specify a selector.

    Examples:
        # Click on stored element:
        inspekt inspect "button#submit"
        inspekt click

        # Click directly on element:
        inspekt click "button#submit"
        inspekt click ".primary-button"
    """
    _perform_click(selector, "click")


@click.command(name="double-click")
@click.argument("selector", required=False, default="$0")
def double_click(selector):
    """
    Double-click on an element.

    Uses the stored element from 'inspekt inspect' by default, or specify a selector.

    Examples:
        inspekt double-click "div.item"
        inspekt inspect "div.item"
        inspekt double-click
    """
    _perform_click(selector, "dblclick")


@click.command(name="doubleclick", hidden=True)
@click.argument("selector", required=False, default="$0")
def doubleclick_alias(selector):
    """Alias for double-click command."""
    _perform_click(selector, "dblclick")


@click.command(name="right-click")
@click.argument("selector", required=False, default="$0")
def right_click(selector):
    """
    Right-click (context menu) on an element.

    Uses the stored element from 'inspekt inspect' by default, or specify a selector.

    Examples:
        inspekt right-click "a.download-link"
        inspekt inspect "a.download-link"
        inspekt right-click
    """
    _perform_click(selector, "contextmenu")


@click.command(name="rightclick", hidden=True)
@click.argument("selector", required=False, default="$0")
def rightclick_alias(selector):
    """Alias for right-click command."""
    _perform_click(selector, "contextmenu")


def _perform_click(selector, click_type):
    """Helper function to perform click actions."""
    executor = BridgeExecutor()
    executor.ensure_server_running()

    # Load the click script
    script_loader = ScriptLoader()
    try:
        script = script_loader.load_script_sync("click_element.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Replace placeholders with properly escaped values
    # Replace quoted placeholders with JSON-encoded values
    code = script.replace("'SELECTOR_PLACEHOLDER'", json.dumps(selector))
    code = code.replace("'CLICK_TYPE_PLACEHOLDER'", json.dumps(click_type))

    try:
        result = executor.execute(code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})

        if response.get("error"):
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        # Show confirmation
        action_name = {
            "click": "Clicked",
            "dblclick": "Double-clicked",
            "contextmenu": "Right-clicked",
        }.get(click_type, "Clicked")

        click.echo(f"{action_name}: {response.get('element', 'element')}")
        pos = response.get("position", {})
        if pos:
            click.echo(f"Position: x={pos.get('x')}, y={pos.get('y')}")

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@click.argument("selector")
@click.option("--timeout", "-t", type=int, default=30, help="Timeout in seconds (default: 30)")
@click.option("--visible", is_flag=True, help="Wait for element to be visible")
@click.option("--hidden", is_flag=True, help="Wait for element to be hidden")
@click.option("--text", type=str, help="Wait for element to contain specific text")
def wait(selector, timeout, visible, hidden, text):
    """
    Wait for an element to appear, be visible, hidden, or contain text.

    By default, waits for element to exist in the DOM.

    Examples:
        # Wait for element to exist (up to 30 seconds):
        inspekt wait "button#submit"

        # Wait for element to be visible:
        inspekt wait ".modal" --visible

        # Wait for element to be hidden:
        inspekt wait ".loading-spinner" --hidden

        # Wait for element to contain text:
        inspekt wait "h1" --text "Success"

        # Custom timeout (10 seconds):
        inspekt wait "div.result" --timeout 10
    """
    executor = BridgeExecutor()
    executor.ensure_server_running()

    # Determine wait type
    if hidden:
        wait_type = "hidden"
    elif visible:
        wait_type = "visible"
    elif text:
        wait_type = "text"
    else:
        wait_type = "exists"

    # Load the wait script
    script_loader = ScriptLoader()
    try:
        script = script_loader.load_script_sync("wait_for.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Replace placeholders with properly escaped values
    timeout_ms = timeout * 1000

    code = script.replace("'SELECTOR_PLACEHOLDER'", json.dumps(selector))
    code = code.replace("'WAIT_TYPE_PLACEHOLDER'", json.dumps(wait_type))
    code = code.replace("'TEXT_PLACEHOLDER'", json.dumps(text or ""))
    code = code.replace("TIMEOUT_PLACEHOLDER", str(timeout_ms))

    # Show waiting message
    wait_msg = {
        "exists": f"Waiting for element: {selector}",
        "visible": f"Waiting for element to be visible: {selector}",
        "hidden": f"Waiting for element to be hidden: {selector}",
        "text": f'Waiting for element to contain "{text}": {selector}',
    }.get(wait_type, f"Waiting for: {selector}")

    click.echo(wait_msg)

    try:
        # Use longer timeout for the request (add 5 seconds buffer)
        result = executor.execute(code, timeout=timeout + 5)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})

        if response.get("error"):
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        if response.get("timeout"):
            click.echo(f"✗ Timeout: {response.get('message', 'Operation timed out')}", err=True)
            sys.exit(1)

        # Success!
        waited_sec = response.get("waited", 0) / 1000
        click.echo(f"✓ {response.get('status', 'Condition met')}")
        if response.get("element"):
            click.echo(f"  Element: {response['element']}")
        click.echo(f"  Waited: {waited_sec:.2f}s")

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@click.argument("keys")
def press(keys):
    """
    Press keyboard keys or shortcuts.

    Supports single keys, modifiers, and combinations.

    Examples:
        inspekt press Tab
        inspekt press Enter
        inspekt press "Ctrl+A"
        inspekt press Escape
        inspekt press "Shift+Tab"
    """
    from inspekt.services.key_parser import parse_key_combo

    executor = BridgeExecutor()
    script_loader = ScriptLoader()

    try:
        script = script_loader.load_script_sync("press_keys.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    parsed = parse_key_combo(keys)
    code = script.replace("'KEYS_PLACEHOLDER'", json.dumps(parsed))

    try:
        result = executor.execute(code)
        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)
        click.echo(f"✓ Pressed: {keys}")
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
