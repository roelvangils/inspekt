#!/usr/bin/env python3
"""
Inspekt URL Scheme Handler (v2 - Registry-based)

Handles inspekt:// URLs by reading from the unified command registry.
This version auto-discovers commands that have URL scheme support.

Examples:
    inspekt://open?url=https://example.com
    inspekt://click?selector=button#submit
    inspekt://eval?code=document.title
"""

import sys
import urllib.parse
import subprocess
import json
import os
import shutil
import asyncio
import logging
from pathlib import Path

# Set up logging for debugging
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s: %(message)s'
)

# Add the inspekt package to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_url_scheme_commands():
    """Get all commands with URL scheme support from the registry."""
    from inspekt.core.commands import register_all_commands
    from inspekt.core.registry import get_registry

    register_all_commands()
    registry = get_registry()

    return registry.get_for_url_scheme()


def parse_inspekt_url(url):
    """Parse an inspekt:// URL into command and parameters."""
    if url.startswith("inspekt://"):
        url = url[len("inspekt://"):]

    if "?" in url:
        path, query_string = url.split("?", 1)
        params = dict(urllib.parse.parse_qsl(query_string))
    else:
        path = url
        params = {}

    return path, params


def get_inspekt_path():
    """
    Get the path to the inspekt CLI using smart discovery.

    Priority order:
    1. INSPEKT_CLI_PATH environment variable (explicit override)
    2. shutil.which() - finds inspekt in PATH
    3. Common installation locations
    4. Fallback to "inspekt" and hope it works
    """
    # 1. Environment variable override (highest priority)
    if env_path := os.environ.get("INSPEKT_CLI_PATH"):
        if os.path.exists(env_path):
            return env_path

    # 2. Use shutil.which (respects PATH, works with pyenv when initialized)
    if which_path := shutil.which("inspekt"):
        return which_path

    # 3. Common installation locations (fallback for GUI apps without full PATH)
    common_paths = [
        "/usr/local/bin/inspekt",
        "/opt/homebrew/bin/inspekt",
        os.path.expanduser("~/.local/bin/inspekt"),
        # pyenv locations (when PATH isn't set up)
        os.path.expanduser("~/.pyenv/shims/inspekt"),
    ]

    for path in common_paths:
        if os.path.exists(path):
            return path

    # 4. Fallback - let the system try to resolve it
    return "inspekt"


def coerce_url_params(params: dict) -> dict:
    """
    Coerce URL query string params to appropriate Python types.

    URL params are always strings, but handlers expect proper types:
    - "true"/"false" → bool
    - "123" → int (if it looks like a number)
    """
    coerced = {}
    for key, value in params.items():
        if isinstance(value, str):
            # Boolean coercion
            if value.lower() in ("true", "1", "yes"):
                coerced[key] = True
            elif value.lower() in ("false", "0", "no"):
                coerced[key] = False
            # Integer coercion (for params like margin)
            elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
                coerced[key] = int(value)
            else:
                coerced[key] = value
        else:
            coerced[key] = value
    return coerced


def execute_direct(cmd_def, params):
    """
    Execute a command by calling its handler directly.

    This is ~2-3x faster than spawning a subprocess because:
    - No Python interpreter startup time
    - Registry already loaded
    - Direct function call vs. CLI parsing

    Returns: dict with 'ok', 'output', and optionally 'error'
    """
    handler = cmd_def.get_handler()
    if not handler:
        return None  # Signal to use CLI fallback

    try:
        # Coerce URL string params to proper Python types
        coerced_params = coerce_url_params(params)

        # Validate params using the command's schema
        validated_params = cmd_def.params_schema(**coerced_params)

        # Call the async handler
        result = asyncio.run(handler(validated_params))

        # Convert Pydantic response to dict for output
        if hasattr(result, 'model_dump'):
            result_dict = result.model_dump()
        elif hasattr(result, 'dict'):
            result_dict = result.dict()
        else:
            result_dict = result

        # Check for success field in response
        success = result_dict.get('success', True)

        # Format output as human-readable text
        output_text = format_response_for_output(cmd_def, result_dict)

        return {
            "ok": success,
            "output": output_text,
            "error": result_dict.get('message', '') if not success else '',
            "raw_result": result_dict  # Preserve raw response for special handling (e.g., screenshots)
        }

    except SystemExit as e:
        # BridgeExecutor calls sys.exit(1) on errors (domain not authorized, timeout, etc.)
        # SystemExit is a BaseException, not an Exception, so we must catch it explicitly
        exit_code = e.code if hasattr(e, 'code') else 1
        logging.warning(f"Direct execution exited with code {exit_code}")
        return {
            "ok": False,
            "output": "",
            "error": f"Command failed (exit code {exit_code})",
            "raw_result": {"success": False, "message": f"Command failed (exit code {exit_code})"}
        }

    except Exception as e:
        logging.error(f"Direct execution failed: {e}")
        return None  # Signal to use CLI fallback


def format_response_for_output(cmd_def, result):
    """Format a response dict as human-readable output text."""
    # For navigation commands, just return the message
    if 'message' in result:
        return result.get('message', '')

    # For extraction commands with content
    if 'content' in result:
        return result.get('content', '')

    # For other responses, return as JSON
    return json.dumps(result, indent=2)


def execute_via_cli(cmd_def, command_name, params):
    """
    Execute a command via CLI subprocess.

    This is the fallback for commands without direct handlers.
    """
    inspekt = get_inspekt_path()
    cli_name = cmd_def.get_cli_name()

    cmd = [inspekt, cli_name]

    # Handle common param patterns
    if "url" in params and command_name == "open":
        cmd.append(params["url"])
    elif "code" in params and command_name == "eval":
        cmd.append(params["code"])
    elif "selector" in params and command_name == "click":
        cmd.append(params["selector"])
    elif "text" in params and command_name == "type":
        cmd.append(params["text"])
        if "selector" in params:
            cmd.extend(["--selector", params["selector"]])
    elif "text" in params and command_name == "paste":
        cmd.append(params["text"])
        if "selector" in params:
            cmd.extend(["--selector", params["selector"]])
    elif "format" in params and command_name == "selection":
        cmd.append(params["format"])
        cmd.append("--raw")
    elif command_name == "cookies" and "action" in params:
        action = params.get("action", "list")
        cmd.append(action)
        if action in ["get", "delete"] and "name" in params:
            cmd.append(params["name"])
        elif action == "set" and "name" in params and "value" in params:
            cmd.extend([params["name"], params["value"]])
        cmd.append("--json")
    # AI commands
    elif command_name == "summarize":
        if "format" in params:
            cmd.extend(["--format", params["format"]])
        if "language" in params:
            cmd.extend(["--language", params["language"]])
    elif command_name == "describe":
        if "language" in params:
            cmd.extend(["--language", params["language"]])
    elif command_name == "ask":
        if "question" in params:
            cmd.append(params["question"])
    elif command_name == "do":
        if "instruction" in params:
            cmd.append(params["instruction"])

    # Add common flags
    if params.get("json") == "true":
        cmd.append("--json")

    timeout = cmd_def.url_scheme_timeout

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr}
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"error": str(e)}


def execute_command_from_registry(command_name, params, commands_by_scheme):
    """
    Execute a command using registry information.

    Execution strategy:
    1. Try direct handler call (fast path, ~2-3x faster)
    2. Fall back to CLI subprocess if handler unavailable or fails
    """
    cmd_def = commands_by_scheme.get(command_name)

    if not cmd_def:
        return {"error": f"Unknown command: {command_name}"}

    # Try direct execution first (fast path)
    result = execute_direct(cmd_def, params)

    if result is not None:
        return result

    # Fall back to CLI (slow path, but handles all commands)
    return execute_via_cli(cmd_def, command_name, params)


def copy_to_clipboard(text):
    """Copy text to macOS clipboard."""
    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE, close_fds=True)
    process.communicate(text.encode('utf-8'))


def copy_image_to_clipboard(image_data: bytes, format: str = "png") -> bool:
    """
    Copy image data to macOS clipboard using osascript.

    This is a simplified version that skips optimization and metadata
    since we're copying directly to clipboard, not saving to a file.

    Args:
        image_data: Raw image bytes
        format: Image format ('png', 'jpeg')

    Returns:
        True if successful, False otherwise
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
        f.write(image_data)
        temp_path = f.name

    try:
        # Use appropriate clipboard type based on format
        if format == "jpeg":
            clipboard_type = "«class JPEG»"
        else:
            clipboard_type = "«class PNGf»"

        script = f'set the clipboard to (read (POSIX file "{temp_path}") as {clipboard_type})'
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        Path(temp_path).unlink(missing_ok=True)


def show_notification(title, message, subtitle=None):
    """Show macOS notification."""
    script = f'display notification "{message}" with title "{title}"'
    if subtitle:
        script = f'display notification "{message}" with title "{title}" subtitle "{subtitle}"'
    subprocess.run(["osascript", "-e", script])


def show_dialog(title, message):
    """Show macOS dialog with OK button for long text."""
    message_escaped = message.replace('"', '\\"').replace("'", "\\'")
    script = f'display dialog "{message_escaped}" with title "{title}" buttons {{"OK"}} default button "OK"'
    subprocess.run(["osascript", "-e", script])


def handle_output(result, command, output_mode, raw_result=None):
    """Handle command output based on output mode."""
    import base64

    # Log for debugging
    log_file = os.path.expanduser("~/inspekt_url_handler.log")
    with open(log_file, "a") as f:
        f.write(f"handle_output called: command={command}, output_mode={output_mode}\n")
        f.write(f"  raw_result keys: {raw_result.keys() if raw_result else 'None'}\n")
        f.write(f"  raw_result.get('data'): {bool(raw_result.get('data')) if raw_result else 'N/A'}\n")

    if not result.get("ok"):
        error_msg = result.get("error", "Command failed")
        show_notification("Inspekt Error", error_msg[:100], command)
        return False

    # Special handling for screenshot command with image data
    if command == "screenshot" and raw_result and raw_result.get("data"):
        with open(log_file, "a") as f:
            f.write(f"  Screenshot special handling triggered!\n")

        if output_mode in ["clipboard", "both"]:
            try:
                image_data = base64.b64decode(raw_result["data"])
                image_format = raw_result.get("format", "png")
                success = copy_image_to_clipboard(image_data, image_format)
                with open(log_file, "a") as f:
                    f.write(f"  copy_image_to_clipboard returned: {success}\n")
                if not success:
                    show_notification("Inspekt Error", "Failed to copy image to clipboard", "screenshot")
                    return False
            except Exception as e:
                with open(log_file, "a") as f:
                    f.write(f"  Exception copying image: {e}\n")
                show_notification("Inspekt Error", f"Failed to copy image: {e}", "screenshot")
                return False

        if output_mode != "silent":
            show_notification("Inspekt", "Screenshot copied to clipboard", "✓ screenshot")
        return True

    output = result.get("output", "").strip()

    if not output:
        if output_mode != "silent":
            show_notification("Inspekt", f"Command '{command}' completed", "✓")
        return True

    if output_mode in ["clipboard", "both"]:
        copy_to_clipboard(output)

    if output_mode == "dialog":
        show_dialog(f"Inspekt: {command}", output[:2000])
    elif output_mode in ["notification", "both"]:
        if len(output) > 200:
            show_notification("Inspekt", "Result ready (click to view)", f"✓ {command}")
            show_dialog(f"Inspekt: {command}", output[:2000])
        else:
            show_notification("Inspekt", output, f"✓ {command}")

    if output_mode == "clipboard":
        show_notification("Inspekt", "Copied to clipboard", f"✓ {command}")

    return True


def main():
    """Main entry point for URL handler."""
    log_file = os.path.expanduser("~/inspekt_url_handler.log")

    if len(sys.argv) < 2:
        with open(log_file, "a") as f:
            f.write("ERROR: No URL provided\n")
        print("Usage: inspekt_url_handler.py <inspekt://...>")
        sys.exit(1)

    url = sys.argv[1]

    with open(log_file, "a") as f:
        f.write(f"\n=== NEW REQUEST (v2) ===\n")
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

    # Get commands from registry
    try:
        url_scheme_commands = get_url_scheme_commands()
        commands_by_scheme = {cmd.url_scheme: cmd for cmd in url_scheme_commands}

        with open(log_file, "a") as f:
            f.write(f"Available URL schemes: {list(commands_by_scheme.keys())}\n")
    except Exception as e:
        with open(log_file, "a") as f:
            f.write(f"Failed to load registry: {e}\n")
        show_notification("Inspekt Error", f"Failed to load registry: {str(e)}")
        sys.exit(1)

    # Determine output mode from registry (or use override from URL params)
    if "output" in params:
        output_mode = params.pop("output")
        if output_mode not in ["clipboard", "notification", "both", "dialog", "silent"]:
            output_mode = "clipboard"
    else:
        # Get from registry - this is the SINGLE SOURCE OF TRUTH
        cmd_def = commands_by_scheme.get(command)
        output_mode = cmd_def.url_scheme_output_mode if cmd_def else "clipboard"

    with open(log_file, "a") as f:
        f.write(f"Output mode: '{output_mode}'\n")
        f.write(f"Executing command: '{command}'\n")

    # Execute command
    try:
        result = execute_command_from_registry(command, params, commands_by_scheme)
        with open(log_file, "a") as f:
            f.write(f"Result: {result}\n")

        success = handle_output(result, command, output_mode, raw_result=result.get("raw_result"))
        if not success:
            sys.exit(1)

    except Exception as e:
        show_notification("Inspekt Error", str(e), "Exception")
        sys.exit(1)


if __name__ == "__main__":
    main()
