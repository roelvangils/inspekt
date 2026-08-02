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

from inspekt.config import get_typing_config
from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader


def _focus_browser_if_requested(ctx):
    """Placeholder for browser focus-on-command feature."""
    pass


def _send_text(text, selector, delay_ms, clear=True, skill=None):
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
    typo_rate = typing_config["human-like-typo-rate"]
    resolved_skill = skill if skill is not None else typing_config["human-like-skill"]

    # Replace placeholders with properly escaped values
    # Use JSON encoding for proper JavaScript string escaping
    code = script.replace("TEXT_PLACEHOLDER", json.dumps(text))
    code = code.replace("DELAY_PLACEHOLDER", str(delay_ms))
    code = code.replace("CLEAR_PLACEHOLDER", "true" if clear else "false")
    code = code.replace("TYPO_RATE_PLACEHOLDER", str(typo_rate))
    code = code.replace("SKILL_PLACEHOLDER", str(resolved_skill))

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

                print_hint(response["hint"])
            sys.exit(1)

        click.echo(response.get("message", "Text sent successfully"))

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@click.argument("text")
@click.option("--selector", "-s", help="CSS selector to focus before typing")
@click.option(
    "--speed",
    type=int,
    help="Characters per second (default: fastest; 0: human-like with realistic rhythm, pauses, and typos)",
)
@click.option(
    "--clear/--no-clear", default=True, help="Clear existing text before typing (default: true)"
)
@click.option(
    "--skill",
    type=float,
    help="Human-mode typist skill, 0.0 (beginner, ~340 cpm) to 1.0 (expert, ~500 cpm). Only with --speed 0.",
)
def type_text(text, selector, speed, clear, skill):
    """
    Type text character by character into the browser.

    Types text into the currently focused input field,
    or into a specific element if --selector is provided.

    By default, clears any existing text and types as fast as possible.
    Use --speed to control typing rate and --no-clear to append instead.

    Human-like mode (`--speed 0`) simulates a real typist: log-normal
    keystroke timing with autocorrelated rhythm, digraph/trigram motor
    chunks (e.g. "the", "ing"), word-onset planning pauses, burst-and-
    micro-pause cadence, fatigue, shift-key delays, and occasional typos
    that are sometimes caught immediately, sometimes only after a few
    more keys. Tune with `--skill` or the `typing.human-like-skill`
    config key (0.0–1.0, default 0.7); tune error rate with
    `typing.human-like-typo-rate` (default 0.05).

    Examples:
        # Type at maximum speed (clears existing text):
        inspekt type "Hello World"

        # Human-like typing at default skill (~7–8 cps, ~430 cpm):
        inspekt type "Hello, how are you?" --speed 0

        # Beginner typist (slower, more errors):
        inspekt type "login failed again" --speed 0 --skill 0.3

        # Expert typist (fast, clean rhythm):
        inspekt type "the quick brown fox" --speed 0 --skill 0.95

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

    _send_text(text, selector, delay_ms, clear, skill=skill)


@click.command()
@click.argument("text")
@click.option("--selector", "-s", help="CSS selector to focus before pasting")
@click.option(
    "--clear/--no-clear", default=True, help="Clear existing text before pasting (default: true)"
)
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
    click.echo(
        "Warning: 'inspekt send' is deprecated. Use 'inspekt type' or 'inspekt paste' instead.\n",
        err=True,
    )
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
@click.argument("keys", nargs=-1, required=True)
def press(keys):
    """
    Send keyboard key presses to the browser.

    Keys are pressed in order; sequences, modifiers, waits, and repeats
    are supported.

    \b
    KEYS:
        Tab Enter Escape Space F5 a …    single keys, pressed in order
        Tab*3                            repeat a key
    \b
    MODIFIERS (combine with +):
        Ctrl+A  Shift+Tab  Alt+F4  Cmd+C
    \b
    WAITS (pauses between keys):
        Wait        0.5 second pause
        Wait(3)     custom pause in seconds (max 60)

    \b
    Examples:
        inspekt press Tab
        inspekt press "Ctrl+A"
        inspekt press Tab Tab Enter
        inspekt press Tab "Wait(2)" Enter
    """
    from inspekt.services.key_parser import parse_key_sequence

    executor = BridgeExecutor()
    script_loader = ScriptLoader()

    try:
        script = script_loader.load_script_sync("press_keys.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        sequence = parse_key_sequence(list(keys))
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    delay_config = {"delay": 0, "delayMin": 0, "delayMax": 0}
    code = script.replace(
        "KEY_SEQUENCE_PLACEHOLDER", json.dumps([s.to_dict() for s in sequence])
    ).replace("DELAY_CONFIG_PLACEHOLDER", json.dumps(delay_config))

    # Waits happen inside the browser, so the bridge timeout must cover them
    total_wait = sum(s.wait_seconds or 0 for s in sequence if s.type == "wait")
    timeout = 10.0 + total_wait

    try:
        result = executor.execute(code, timeout=timeout)
        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)
        click.echo(f"✓ Pressed: {' '.join(keys)}")
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
