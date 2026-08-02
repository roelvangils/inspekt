"""Watch commands for monitoring browser events and interactive control."""

import json
import signal
import subprocess
import sys
from pathlib import Path

import click

from inspekt import config as inspekt_config
from inspekt.client import BridgeClient

# Save built-in open before it gets shadowed by Click commands
_builtin_open = open


@click.group()
def watch():
    """Watch browser events in real-time."""
    pass


@watch.command()
def input():
    """
    Watch keyboard input in real-time.

    Streams all keyboard events from the browser to the terminal.
    Press Ctrl+C to stop watching.

    Example:
        inspekt watch input
    """
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code

        click.echo(
            _style_with_inline_code(
                "Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"
            ),
            err=True,
        )
        sys.exit(1)

    # Start watching keyboard
    script_path = Path(__file__).parent.parent.parent / "scripts" / "watch_keyboard.js"
    with _builtin_open(script_path) as f:
        watch_code = f.read()

    try:
        result = client.execute(watch_code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error starting keyboard watcher: {result.get('error')}", err=True)
            sys.exit(1)

        click.echo("Watching keyboard input... (Press Ctrl+C to stop)")
        click.echo("")

        # Now continuously poll for keyboard events
        # We'll use a loop that executes code to check for new events
        poll_code = """
        (function() {
            if (!window.__ZEN_KEYBOARD_EVENTS__) {
                window.__ZEN_KEYBOARD_EVENTS__ = [];
            }
            const events = window.__ZEN_KEYBOARD_EVENTS__.splice(0);
            return events;
        })()
        """

        # Set up signal handler for Ctrl+C
        def stop_watching(sig, frame):
            cleanup_code = """
            (function() {
                const watchId = '__ZEN_KEYBOARD_WATCH__';
                if (window[watchId]) {
                    document.removeEventListener('keydown', window[watchId], true);
                    delete window[watchId];
                }
                if (window.__ZEN_KEYBOARD_EVENTS__) {
                    delete window.__ZEN_KEYBOARD_EVENTS__;
                }
                return 'Keyboard watcher stopped';
            })()
            """
            client.execute(cleanup_code, timeout=2.0)
            click.echo("\n\nStopped watching keyboard input.")
            sys.exit(0)

        signal.signal(signal.SIGINT, stop_watching)

        # Poll for events
        import time

        while True:
            result = client.execute(poll_code, timeout=1.0)
            if result.get("ok"):
                events = result.get("result", [])
                for event in events:
                    click.echo(event, nl=False)
                    sys.stdout.flush()

            time.sleep(0.1)  # Poll every 100ms

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


@watch.command()
def all():
    """
    Watch all user interactions - keyboard, focus, and accessible names.

    Features:
    - Groups regular typing on single lines
    - Shows special keys (Tab, Enter, arrows, modifiers) on separate lines
    - Displays accessible name when tabbing to focusable elements

    Press Ctrl+C to stop watching.

    Example:
        inspekt watch all
    """
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code

        click.echo(
            _style_with_inline_code(
                "Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"
            ),
            err=True,
        )
        sys.exit(1)

    # Load watch_all script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "watch_all.js"

    try:
        with _builtin_open(script_path) as f:
            script_template = f.read()
    except FileNotFoundError:
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    # Start watching
    start_code = script_template.replace("ACTION_PLACEHOLDER", "start")

    try:
        result = client.execute(start_code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error starting watcher: {result.get('error')}", err=True)
            sys.exit(1)

        click.echo("Watching all interactions... (Press Ctrl+C to stop)")
        click.echo("")

        # Poll code
        poll_code = script_template.replace("ACTION_PLACEHOLDER", "poll")

        # Cleanup code
        stop_code = script_template.replace("ACTION_PLACEHOLDER", "stop")

        # Set up signal handler for Ctrl+C
        def stop_watching(sig, frame):
            client.execute(stop_code, timeout=2.0)
            click.echo("\n\nStopped watching.")
            sys.exit(0)

        signal.signal(signal.SIGINT, stop_watching)

        # Poll for events
        import time

        while True:
            result = client.execute(poll_code, timeout=1.0)
            if result.get("ok"):
                response = result.get("result", {})
                if response.get("hasEvents"):
                    events = response.get("events", [])
                    for event in events:
                        event_type = event.get("type")

                        if event_type == "text":
                            # Regular text - print on same line
                            click.echo(event.get("content", ""))

                        elif event_type == "key":
                            # Special key - print with brackets
                            click.echo(f"[{event.get('content', '')}]")

                        elif event_type == "focus":
                            # Focus change - show accessible name
                            accessible_name = event.get("accessibleName", "")
                            element = event.get("element", "")

                            if accessible_name and accessible_name != element:
                                click.echo(f"→ Focus: {accessible_name} {element}")
                            else:
                                click.echo(f"→ Focus: {element}")

            time.sleep(0.1)  # Poll every 100ms

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


@click.command()
def control():
    """
    Control the browser remotely from your terminal.

    All keyboard input from your terminal will be sent directly to the browser,
    allowing you to navigate, type, and interact with the page remotely.

    Supports:
    - Regular text input
    - Special keys (arrows, Enter, Tab, Escape, etc.)
    - Modifier keys (Ctrl, Alt, Shift, Cmd)

    Press Ctrl+D to exit control mode.

    Example:
        inspekt control
    """
    import select
    import sys
    import termios
    import tty

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code

        click.echo(
            _style_with_inline_code(
                "Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"
            ),
            err=True,
        )
        sys.exit(1)

    # Load configuration
    control_config = inspekt_config.get_control_config()
    config_json = json.dumps(control_config)

    # Load control script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "control.js"

    try:
        with _builtin_open(script_path) as f:
            script_template = f.read()
    except FileNotFoundError:
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    # Start control mode
    start_code = script_template.replace("ACTION_PLACEHOLDER", "start")
    start_code = start_code.replace("KEY_DATA_PLACEHOLDER", "{}")
    start_code = start_code.replace("CONFIG_PLACEHOLDER", config_json)

    try:
        result = client.execute(start_code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error starting control mode: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        title = response.get("title", "Unknown")

        click.echo(f"Now controlling: {title}")
        click.echo("Press Ctrl+D to exit\n")

        # Save terminal settings
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            # Put terminal in raw mode
            tty.setraw(fd)

            while True:
                # Check for notifications before reading input
                # Use select with timeout to allow polling
                readable, _, _ = select.select([sys.stdin], [], [], 0.1)  # 100ms timeout

                if not readable:
                    # No input available, check for notifications
                    try:
                        import requests

                        resp = requests.get(
                            f"http://{client.host}:{client.port}/notifications", timeout=0.5
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            if data.get("ok") and data.get("notifications"):
                                for notification in data["notifications"]:
                                    if notification["type"] == "refocus":
                                        message = notification["message"]
                                        sys.stderr.write(f"\r\n{message}\r\n")
                                        sys.stderr.flush()
                                        # Speak if speak-all is enabled
                                        if control_config.get("speak-all"):
                                            try:
                                                subprocess.run(
                                                    ["say", message], check=False, timeout=5
                                                )
                                            except Exception:
                                                pass
                    except Exception:
                        # Silently ignore notification check errors
                        pass
                    continue

                # Read one character
                char = sys.stdin.read(1)

                # Handle Ctrl+D (EOF)
                if char == "\x04":  # Ctrl+D
                    break

                # Map character to key data
                key_data = {}

                # Special key mappings
                if char == "\x1b":  # Escape sequence
                    # Read next characters for arrow keys, etc.
                    next_char = sys.stdin.read(1)
                    if next_char == "[":
                        arrow = sys.stdin.read(1)
                        if arrow == "A":
                            key_data = {"key": "ArrowUp", "code": "ArrowUp"}
                        elif arrow == "B":
                            key_data = {"key": "ArrowDown", "code": "ArrowDown"}
                        elif arrow == "C":
                            key_data = {"key": "ArrowRight", "code": "ArrowRight"}
                        elif arrow == "D":
                            key_data = {"key": "ArrowLeft", "code": "ArrowLeft"}
                        elif arrow == "Z":
                            # Shift+Tab
                            key_data = {"key": "Tab", "code": "Tab", "shift": True}
                        else:
                            # Unknown sequence, skip
                            continue
                    else:
                        # Just Escape key
                        key_data = {"key": "Escape", "code": "Escape"}
                elif char == "\r" or char == "\n":
                    key_data = {"key": "Enter", "code": "Enter"}
                elif char == "\t":
                    key_data = {"key": "Tab", "code": "Tab"}
                elif char == "\x7f":  # Backspace
                    key_data = {"key": "Backspace", "code": "Backspace"}
                elif ord(char) < 32:  # Control character
                    # Handle Ctrl+letter combinations
                    letter = chr(ord(char) + 96)
                    key_data = {"key": letter, "code": f"Key{letter.upper()}", "ctrl": True}
                else:
                    # Regular character
                    key_data = {"key": char, "code": f"Key{char.upper()}" if char.isalpha() else ""}

                # Send key to browser
                send_code = script_template.replace("ACTION_PLACEHOLDER", "send")
                send_code = send_code.replace("KEY_DATA_PLACEHOLDER", json.dumps(key_data))
                send_code = send_code.replace("CONFIG_PLACEHOLDER", config_json)

                result = client.execute(send_code, timeout=60.0)

                # Check if control needs reinitialization (e.g., after page reload)
                # The browser returns {ok: true, result: {ok: false, needsRestart: true}}
                if result.get("ok"):
                    response = result.get("result", {})
                    if isinstance(response, dict) and response.get("needsRestart"):
                        # Auto-restart control mode
                        # Write directly to stderr (works in raw mode)
                        sys.stderr.write("\r\n🔄 Reinitializing after navigation...\r\n")
                        sys.stderr.flush()

                        restart_result = client.execute(start_code, timeout=60.0)
                        if control_config.get("verbose-logging"):
                            sys.stderr.write(f"[CLI] Restart: {restart_result.get('ok')}\r\n")
                            sys.stderr.flush()

                        # Retry the key send
                        result = client.execute(send_code, timeout=60.0)

                        if result.get("ok"):
                            sys.stderr.write("✅ Control restored!\r\n")
                            sys.stderr.flush()

                if result.get("ok"):
                    # Check if we should speak the accessible name
                    response = result.get("result", {})
                    if control_config.get("speak-name") and "accessibleName" in response:
                        accessible_name = response.get("accessibleName", "").strip()
                        role = response.get("role", "")

                        if accessible_name:
                            # Build the text to speak
                            speak_text = accessible_name

                            # Optionally announce role
                            if control_config.get("announce-role") and role:
                                speak_text = f"{role}, {speak_text}"

                            # Use macOS say command
                            try:
                                subprocess.run(["say", speak_text], check=False, timeout=5)
                            except Exception:
                                # Silently ignore if say command fails
                                pass

                    # Display verbose messages if enabled
                    if control_config.get("verbose"):
                        # Check for opening message (when pressing Enter on links/buttons)
                        if "message" in response:
                            message = response["message"]
                            sys.stderr.write(f"\r\n{message}\r\n")
                            sys.stderr.flush()
                            if control_config.get("speak-all"):
                                try:
                                    subprocess.run(["say", message], check=False, timeout=5)
                                except Exception:
                                    pass

                        # Check for "opened" message (right after click)
                        if "openedMessage" in response:
                            message = response["openedMessage"]
                            sys.stderr.write(f"{message}\r\n")
                            sys.stderr.flush()
                            if control_config.get("speak-all"):
                                try:
                                    subprocess.run(["say", message], check=False, timeout=5)
                                except Exception:
                                    pass

                        # Check for refocus message (after page navigation)
                        if "refocusMessage" in response:
                            message = response["refocusMessage"]
                            sys.stderr.write(f"{message}\r\n")
                            sys.stderr.flush()
                            if control_config.get("speak-all"):
                                try:
                                    subprocess.run(["say", message], check=False, timeout=5)
                                except Exception:
                                    pass
                else:
                    # Silently ignore errors, keep going
                    pass

        finally:
            # Restore terminal settings
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

            # Stop control mode
            stop_code = script_template.replace("ACTION_PLACEHOLDER", "stop")
            stop_code = stop_code.replace("KEY_DATA_PLACEHOLDER", "{}")
            stop_code = stop_code.replace("CONFIG_PLACEHOLDER", config_json)
            client.execute(stop_code, timeout=2.0)

            click.echo("\n\nControl mode ended.")

    except Exception as e:
        # Make sure to restore terminal
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except Exception:
            pass
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)
