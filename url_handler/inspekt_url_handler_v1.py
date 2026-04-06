#!/usr/bin/env python3
"""
Inspekt URL Scheme Handler

Handles inspekt:// URLs and routes them to the appropriate Inspekt commands.

Examples:
    inspekt://open?url=https://example.com
    inspekt://click?selector=button#submit
    inspekt://eval?code=document.title
    inspekt://type?text=Hello&selector=input
    inspekt://screenshot?selector=h1
    inspekt://md-link
"""

import sys
import urllib.parse
import subprocess
import json


def parse_inspekt_url(url):
    """Parse an inspekt:// URL into command and parameters."""
    # Remove inspekt:// prefix
    if url.startswith("inspekt://"):
        url = url[len("inspekt://"):]

    # Split into path and query
    if "?" in url:
        path, query_string = url.split("?", 1)
        params = dict(urllib.parse.parse_qsl(query_string))
    else:
        path = url
        params = {}

    return path, params


def execute_command(command, params):
    """Execute the appropriate inspekt command based on parsed URL."""

    # Navigation commands
    if command == "open":
        url = params.get("url")
        if not url:
            return {"error": "Missing 'url' parameter"}

        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "open", url]
        if params.get("wait") == "true":
            # For CLI, we'd need to add wait support
            pass

        result = subprocess.run(cmd, capture_output=True, text=True)
        return {"ok": result.returncode == 0, "output": result.stdout}

    elif command == "back":
        result = subprocess.run(["/Users/roelvangils/.pyenv/shims/inspekt", "back"], capture_output=True, text=True)
        return {"ok": result.returncode == 0, "output": result.stdout}

    elif command == "forward":
        result = subprocess.run(["/Users/roelvangils/.pyenv/shims/inspekt", "forward"], capture_output=True, text=True)
        return {"ok": result.returncode == 0, "output": result.stdout}

    elif command == "reload":
        result = subprocess.run(["/Users/roelvangils/.pyenv/shims/inspekt", "reload"], capture_output=True, text=True)
        return {"ok": result.returncode == 0, "output": result.stdout}

    # Execution command
    elif command == "eval":
        code = params.get("code")
        if not code:
            return {"error": "Missing 'code' parameter"}

        result = subprocess.run(
            ["/Users/roelvangils/.pyenv/shims/inspekt", "eval", code],
            capture_output=True,
            text=True
        )
        return {"ok": result.returncode == 0, "output": result.stdout}

    # Interaction commands
    elif command == "click":
        selector = params.get("selector")
        if not selector:
            return {"error": "Missing 'selector' parameter"}

        result = subprocess.run(
            ["/Users/roelvangils/.pyenv/shims/inspekt", "click", selector],
            capture_output=True,
            text=True
        )
        return {"ok": result.returncode == 0, "output": result.stdout}

    elif command == "type":
        text = params.get("text")
        if not text:
            return {"error": "Missing 'text' parameter"}

        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "type", text]
        if params.get("selector"):
            cmd.extend(["--selector", params["selector"]])
        if params.get("speed"):
            cmd.extend(["--speed", params["speed"]])

        result = subprocess.run(cmd, capture_output=True, text=True)
        return {"ok": result.returncode == 0, "output": result.stdout}

    elif command == "paste":
        text = params.get("text")
        if not text:
            return {"error": "Missing 'text' parameter"}

        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "paste", text]
        if params.get("selector"):
            cmd.extend(["--selector", params["selector"]])

        result = subprocess.run(cmd, capture_output=True, text=True)
        return {"ok": result.returncode == 0, "output": result.stdout}

    # Inspection commands
    elif command == "inspect":
        selector = params.get("selector")
        if not selector:
            return {"error": "Missing 'selector' parameter"}

        result = subprocess.run(
            ["/Users/roelvangils/.pyenv/shims/inspekt", "inspect", selector],
            capture_output=True,
            text=True
        )
        return {"ok": result.returncode == 0, "output": result.stdout}

    elif command == "screenshot":
        selector = params.get("selector")
        if not selector:
            return {"error": "Missing 'selector' parameter"}

        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "screenshot", "--selector", selector]
        if params.get("output"):
            cmd.extend(["--output", params["output"]])

        result = subprocess.run(cmd, capture_output=True, text=True)
        return {"ok": result.returncode == 0, "output": result.stdout}

    # Selection commands
    elif command == "selection":
        format_type = params.get("format", "text")

        if format_type in ["text", "html", "markdown"]:
            result = subprocess.run(
                ["/Users/roelvangils/.pyenv/shims/inspekt", "selection", format_type, "--raw"],
                capture_output=True,
                text=True
            )
            return {"ok": result.returncode == 0, "output": result.stdout}
        else:
            return {"error": f"Invalid format: {format_type}"}

    # Cookie commands
    elif command == "cookies":
        action = params.get("action", "list")

        if action == "list":
            result = subprocess.run(
                ["/Users/roelvangils/.pyenv/shims/inspekt", "cookies", "list", "--json"],
                capture_output=True,
                text=True
            )
            return {"ok": result.returncode == 0, "output": result.stdout}

        elif action == "get":
            name = params.get("name")
            if not name:
                return {"error": "Missing 'name' parameter"}

            result = subprocess.run(
                ["/Users/roelvangils/.pyenv/shims/inspekt", "cookies", "get", name, "--json"],
                capture_output=True,
                text=True
            )
            return {"ok": result.returncode == 0, "output": result.stdout}

        elif action == "set":
            name = params.get("name")
            value = params.get("value")
            if not name or not value:
                return {"error": "Missing 'name' or 'value' parameter"}

            cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "cookies", "set", name, value]
            if params.get("max_age"):
                cmd.extend(["--max-age", params["max_age"]])
            if params.get("path"):
                cmd.extend(["--path", params["path"]])

            result = subprocess.run(cmd, capture_output=True, text=True)
            return {"ok": result.returncode == 0, "output": result.stdout}

        elif action == "delete":
            name = params.get("name")
            if not name:
                return {"error": "Missing 'name' parameter"}

            result = subprocess.run(
                ["/Users/roelvangils/.pyenv/shims/inspekt", "cookies", "delete", name],
                capture_output=True,
                text=True
            )
            return {"ok": result.returncode == 0, "output": result.stdout}

    # Info command
    elif command == "info":
        result = subprocess.run(
            ["/Users/roelvangils/.pyenv/shims/inspekt", "info"],
            capture_output=True,
            text=True
        )
        # Log detailed error info
        import os
        log_file = os.path.expanduser("~/inspekt_url_handler.log")
        with open(log_file, "a") as f:
            f.write(f"INFO command - returncode: {result.returncode}\n")
            f.write(f"INFO command - stdout: {result.stdout[:200]}\n")
            f.write(f"INFO command - stderr: {result.stderr[:200]}\n")
        return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr}

    # AI commands (need longer timeout)
    elif command == "summarize":
        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "summarize"]
        if params.get("format"):
            cmd.extend(["--format", params["format"]])
        if params.get("language") or params.get("lang"):
            lang = params.get("language") or params.get("lang")
            cmd.extend(["--language", lang])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        # Log detailed error info
        import os
        log_file = os.path.expanduser("~/inspekt_url_handler.log")
        with open(log_file, "a") as f:
            f.write(f"SUMMARIZE command - returncode: {result.returncode}\n")
            f.write(f"SUMMARIZE command - stdout: {result.stdout[:500]}\n")
            f.write(f"SUMMARIZE command - stderr: {result.stderr[:500]}\n")
        return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr}

    elif command == "describe":
        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "describe"]
        if params.get("language") or params.get("lang"):
            lang = params.get("language") or params.get("lang")
            cmd.extend(["--language", lang])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        # Log detailed error info
        import os
        log_file = os.path.expanduser("~/inspekt_url_handler.log")
        with open(log_file, "a") as f:
            f.write(f"DESCRIBE command - returncode: {result.returncode}\n")
            f.write(f"DESCRIBE command - stdout: {result.stdout[:500]}\n")
            f.write(f"DESCRIBE command - stderr: {result.stderr[:500]}\n")
        return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr}

    elif command == "outline":
        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "outline"]
        if params.get("json") == "true":
            cmd.append("--json")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {"ok": result.returncode == 0, "output": result.stdout}

    elif command == "ask":
        question = params.get("question") or params.get("q")
        if not question:
            return {"error": "Missing 'question' or 'q' parameter"}

        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "ask", question]
        if params.get("no_cache") == "true":
            cmd.append("--no-cache")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        # Log detailed error info
        import os
        log_file = os.path.expanduser("~/inspekt_url_handler.log")
        with open(log_file, "a") as f:
            f.write(f"ASK command - returncode: {result.returncode}\n")
            f.write(f"ASK command - stdout: {result.stdout[:500]}\n")
            f.write(f"ASK command - stderr: {result.stderr[:500]}\n")
        return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr}

    # Utility commands
    elif command == "md-link":
        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "md-link"]
        if params.get("json") == "true":
            cmd.append("--json")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return {"ok": result.returncode == 0, "output": result.stdout.strip(), "error": result.stderr}

    else:
        return {"error": f"Unknown command: {command}"}


def copy_to_clipboard(text):
    """Copy text to macOS clipboard."""
    process = subprocess.Popen(
        ['pbcopy'],
        stdin=subprocess.PIPE,
        close_fds=True
    )
    process.communicate(text.encode('utf-8'))


def show_notification(title, message, subtitle=None):
    """Show macOS notification."""
    script = f'display notification "{message}" with title "{title}"'
    if subtitle:
        script = f'display notification "{message}" with title "{title}" subtitle "{subtitle}"'
    subprocess.run(["osascript", "-e", script])


def show_dialog(title, message):
    """Show macOS dialog with OK button for long text."""
    # Escape quotes in message
    message_escaped = message.replace('"', '\\"').replace("'", "\\'")
    script = f'display dialog "{message_escaped}" with title "{title}" buttons {{"OK"}} default button "OK"'
    subprocess.run(["osascript", "-e", script])


def handle_output(result, command, output_mode):
    """Handle command output based on output mode.

    Args:
        result: Command result dict with 'ok', 'output', 'error' keys
        command: Command name for notifications
        output_mode: 'clipboard', 'notification', 'both', 'dialog', or 'silent'
    """
    if not result.get("ok"):
        # Always show errors as notifications
        error_msg = result.get("error", "Command failed")
        show_notification("Inspekt Error", error_msg, command)
        return False

    output = result.get("output", "").strip()

    if not output:
        # No output to display
        if output_mode != "silent":
            show_notification("Inspekt", f"Command '{command}' completed", "✓")
        return True

    # Handle different output modes
    if output_mode in ["clipboard", "both"]:
        copy_to_clipboard(output)

    if output_mode == "dialog":
        # Show full output in dialog
        show_dialog(f"Inspekt: {command}", output[:2000])  # Dialog has length limit

    elif output_mode in ["notification", "both"]:
        # For long output, show notification + dialog
        if len(output) > 200:
            show_notification("Inspekt", "Result ready (click to view)", f"✓ {command}")
            show_dialog(f"Inspekt: {command}", output[:2000])
        else:
            # Short output - just notification
            show_notification("Inspekt", output, f"✓ {command}")

    if output_mode == "clipboard":
        # Show brief confirmation when copying to clipboard
        show_notification("Inspekt", "Copied to clipboard", f"✓ {command}")

    return True


def main():
    """Main entry point for URL handler."""
    # Log to file for debugging
    import os
    log_file = os.path.expanduser("~/inspekt_url_handler.log")

    if len(sys.argv) < 2:
        with open(log_file, "a") as f:
            f.write("ERROR: No URL provided\n")
        print("Usage: inspekt_url_handler.py <inspekt://...>")
        sys.exit(1)

    url = sys.argv[1]

    with open(log_file, "a") as f:
        f.write(f"\n=== NEW REQUEST ===\n")
        f.write(f"Raw URL: {url}\n")

    # Parse URL
    try:
        command, params = parse_inspekt_url(url)
        with open(log_file, "a") as f:
            f.write(f"Parsed command: '{command}'\n")
            f.write(f"Parsed params: {params}\n")
    except Exception as e:
        show_notification("Inspekt Error", f"Invalid URL: {str(e)}")
        sys.exit(1)

    # Get output mode from parameters (default depends on command)
    # AI commands: dialog by default (content to read)
    # Data commands: clipboard by default (content to use/paste)
    # Action commands: notification by default (just confirmation)
    ai_commands = ["summarize", "describe", "ask"]
    data_commands = ["eval", "info", "selection", "inspected", "cookies", "screenshot", "outline", "md-link"]
    action_commands = ["open", "back", "forward", "reload", "click", "double-click", "right-click",
                       "type", "paste", "inspect", "wait", "pageup", "pagedown", "top", "bottom"]

    if "output" in params:
        output_mode = params.pop("output")
    elif command in ai_commands:
        output_mode = "dialog"  # AI commands -> show in dialog to read
    elif command in data_commands:
        output_mode = "clipboard"  # Data commands -> clipboard
    elif command in action_commands:
        output_mode = "notification"  # Action commands -> just notification
    else:
        output_mode = "clipboard"  # Default fallback

    if output_mode not in ["clipboard", "notification", "both", "dialog", "silent"]:
        output_mode = "clipboard"

    with open(log_file, "a") as f:
        f.write(f"Output mode: '{output_mode}'\n")
        f.write(f"Executing command: '{command}'\n")

    # Execute command
    try:
        result = execute_command(command, params)
        with open(log_file, "a") as f:
            f.write(f"Result: {result}\n")

        # Handle output based on mode
        success = handle_output(result, command, output_mode)

        if not success:
            sys.exit(1)

    except Exception as e:
        show_notification("Inspekt Error", str(e), "Exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
