"""Replay recorded browser interactions from a YAML file."""

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import yaml

from inspekt.app.cli.icons import success, error
from inspekt.client import BridgeClient
from inspekt.config import get_audio_config, get_video_config
from inspekt.domain.recording import Recording
from inspekt.services.applescript_utils import activate_browser_tab
from inspekt.services.audio import CLIAudio
from .formatting import (
    format_assertion_result,
    format_duration,
    format_paused_step_for_display,
    format_skipped_step_for_display,
    format_step_for_display,
    format_step_header,
    format_status,
    format_system_message,
    get_recordings_dir,
)
from .recording_utils import load_external_file_content
from .util import open_or_download

import requests

# Bridge server constants
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765

# Import shared utilities from recording_utils (moved there to avoid circular imports)
from .recording_utils import clean_filename, complete_recording_files, find_most_recent_recording
from inspekt.shared.dialog_styles import DIALOG_STYLES

# Save built-in open before it gets shadowed
_builtin_open = open


def check_csp_bypass_enabled() -> bool:
    """Check if global CSP bypass is enabled in the browser extension."""
    try:
        response = requests.get(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/csp/global",
            timeout=2.0
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("enabled", False)
    except Exception:
        pass
    return False


class ReplayResult:
    """Collects results from a replay session."""

    def __init__(self):
        self.total_steps = 0
        self.passed_steps = 0
        self.failed_steps = 0
        self.skipped_steps = 0
        self.failures: list[dict] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None

    def add_success(self, step_index: int, step: dict):
        self.passed_steps += 1

    def add_failure(self, step_index: int, step: dict, error: str, assertion_failures: list[str] = None):
        self.failed_steps += 1
        failure = {
            "step": step_index + 1,
            "action": step.get("action"),
            "error": error,
            "selector": step.get("target", {}).get("selector") if step.get("target") else None,
            "assertion_failures": assertion_failures or [],
        }
        self.failures.append(failure)

    def add_skip(self, step_index: int, step: dict, reason: str):
        self.skipped_steps += 1

    @property
    def duration_ms(self) -> int:
        if self.start_time and self.end_time:
            return int((self.end_time - self.start_time).total_seconds() * 1000)
        return 0

    @property
    def all_passed(self) -> bool:
        return self.failed_steps == 0


def focus_browser_tab(client: BridgeClient, verbose: bool = False) -> bool:
    """Focus the browser tab using AppleScript (macOS only).

    Returns True if successful, False otherwise.
    """
    if platform.system() != "Darwin":
        if verbose:
            click.echo("  (Tab focus is only supported on macOS)")
        return False

    # Get current page info (URL and user agent)
    code = """
    (function() {
        const ua = navigator.userAgent;
        let browserName = 'Chrome';  // Default
        if (ua.includes('Firefox')) browserName = 'Firefox';
        else if (ua.includes('Edg')) browserName = 'Edge';
        else if (ua.includes('Brave')) browserName = 'Brave';
        else if (ua.includes('Chrome')) browserName = 'Chrome';
        else if (ua.includes('Safari') && !ua.includes('Chrome')) browserName = 'Safari';
        return {
            url: window.location.href,
            browserName: browserName
        };
    })()
    """

    try:
        result = client.execute(code, timeout=5.0)
        if not result.get("ok"):
            if verbose:
                click.echo(f"  (Could not get browser info: {result.get('error')})")
            return False

        page_info = result.get("result", {})
        browser_name = page_info.get("browserName", "Chrome")
        url = page_info.get("url", "")

        if not url:
            if verbose:
                click.echo("  (No URL available for tab activation)")
            return False

        # Activate the browser tab using AppleScript
        activation_result = activate_browser_tab(browser_name, url)

        if activation_result.ok:
            if verbose:
                click.echo(f"  Focused {browser_name} tab")
            return True
        else:
            if verbose:
                click.echo(f"  (Tab focus failed: {activation_result.error})")
            return False

    except Exception as e:
        if verbose:
            click.echo(f"  (Tab focus error: {e})")
        return False


def wait_for_reconnection(
    client: BridgeClient,
    timeout_sec: float = 10.0,
    poll_interval_sec: float = 0.2,
    verbose: bool = False,
) -> bool:
    """Wait for the browser bridge to reconnect after navigation.

    After a page navigation, the WebSocket connection is lost and must be
    re-established by the new page. This function polls until the connection
    is restored.

    Args:
        client: BridgeClient instance
        timeout_sec: Maximum time to wait in seconds
        poll_interval_sec: Time between connection checks
        verbose: Whether to print progress messages

    Returns:
        True if connection was re-established, False if timeout expired
    """
    start_time = time.time()
    consecutive_failures = 0

    while time.time() - start_time < timeout_sec:
        try:
            # Try a simple execution to check if connection is alive
            result = client.execute("(function(){ return { ok: true }; })()", timeout=2.0)

            if result.get("ok"):
                if consecutive_failures > 0 and verbose:
                    # Get current domain for the message
                    try:
                        from urllib.parse import urlparse
                        url_result = client.execute("window.location.href", timeout=1.0)
                        if url_result.get("ok"):
                            url = url_result.get("result", "")
                            domain = urlparse(url).netloc or url
                            click.echo(format_system_message(f"Playback resumed on {domain}", icon="resume"))
                        else:
                            click.echo(format_system_message("Playback resumed", icon="resume"))
                    except Exception:
                        click.echo(format_system_message("Playback resumed", icon="resume"))
                return True

        except Exception:
            pass

        consecutive_failures += 1
        time.sleep(poll_interval_sec)

    return False


def wait_for_page_ready(
    client: BridgeClient,
    timeout_sec: float = 15.0,
    poll_interval_sec: float = 0.3,
    verbose: bool = False,
) -> dict:
    """Wait for the page to be fully loaded after navigation.

    This function waits for document.readyState === 'complete', which indicates
    that the page and all its resources (images, scripts, stylesheets) have loaded.

    Args:
        client: BridgeClient instance
        timeout_sec: Maximum time to wait in seconds
        poll_interval_sec: Time between checks
        verbose: Whether to print progress messages

    Returns:
        dict with 'success' (bool), 'ready_state' (str), and optionally 'elapsed_ms'
    """
    start_time = time.time()

    check_ready_code = """
    (function() {
        return {
            readyState: document.readyState,
            url: window.location.href
        };
    })()
    """

    while time.time() - start_time < timeout_sec:
        try:
            result = client.execute(check_ready_code, timeout=3.0)
            if result.get("ok"):
                response = result.get("result", {})
                ready_state = response.get("readyState", "unknown")

                if ready_state == "complete":
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    if verbose:
                        click.echo(format_system_message(f"Page loaded ({elapsed_ms}ms)"))
                    return {"success": True, "ready_state": ready_state, "elapsed_ms": elapsed_ms}
        except Exception:
            pass

        time.sleep(poll_interval_sec)

    # Timeout
    elapsed_ms = int((time.time() - start_time) * 1000)
    return {"success": False, "ready_state": "timeout", "elapsed_ms": elapsed_ms, "timed_out": True}


def wait_for_visual_script_ready(
    client: BridgeClient,
    visual_script: str,
    timeout_sec: float = 5.0,
    poll_interval_sec: float = 0.05,
    replay_mode: bool = False,
) -> dict:
    """Wait for visual script to be ready after navigation.

    When replay_mode is True (recommended), the extension auto-injects the visual
    script on page load, so we only need to wait for it to be ready. This is much
    faster than the polling+injection approach.

    When replay_mode is False (fallback), we poll and manually inject the script
    after the extension's WebSocket reconnects.

    Args:
        client: BridgeClient instance
        visual_script: The visual script content to inject (only used when replay_mode=False)
        timeout_sec: Maximum time to wait in seconds
        poll_interval_sec: Time between checks
        replay_mode: If True, extension handles injection automatically

    Returns:
        dict with 'success' (bool), 'injected' (bool), 'elapsed_ms' (int)
    """
    start_time = time.time()
    injected = False

    # Check code to verify script is ready
    check_code = (
        "(() => { "
        "  if (typeof window.__INSPEKT_VISUAL__ === 'object' && "
        "      window.__INSPEKT_VISUAL__ !== null && "
        "      typeof window.__INSPEKT_VISUAL__.interactive === 'object') { "
        "    return { ready: true, url: location.href }; "
        "  } "
        "  return { ready: false }; "
        "})()"
    )

    while time.time() - start_time < timeout_sec:
        try:
            check_result = client.execute(check_code, timeout=2.0)

            if check_result.get("ok"):
                result = check_result.get("result", {})
                if isinstance(result, dict) and result.get("ready") is True:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    return {"success": True, "injected": injected, "elapsed_ms": elapsed_ms}

            # Not ready - if not in replay mode, try manual injection
            if not replay_mode:
                client.execute(visual_script, timeout=3.0)
                injected = True
                time.sleep(0.05)

        except Exception:
            pass  # Connection might not be ready yet

        time.sleep(poll_interval_sec)

    # Timeout - one final attempt
    if not replay_mode:
        try:
            client.execute(visual_script, timeout=3.0)
            time.sleep(0.3)
            check = client.execute(check_code, timeout=2.0)
            if check.get("ok"):
                result = check.get("result", {})
                if isinstance(result, dict) and result.get("ready") is True:
                    elapsed_ms = int((time.time() - start_time) * 1000)
                    return {"success": True, "injected": True, "elapsed_ms": elapsed_ms}
        except Exception:
            pass

    elapsed_ms = int((time.time() - start_time) * 1000)
    return {"success": False, "injected": False, "elapsed_ms": elapsed_ms, "timed_out": True}


def send_text_with_typing(client: BridgeClient, text: str, selector: str, clear: bool = True) -> dict:
    """Send text using human-like typing simulation.

    Uses the same approach as 'inspekt type --speed 0' for realistic typing.

    Args:
        client: BridgeClient instance
        text: Text to type
        selector: CSS selector of the element to type into
        clear: Whether to clear existing text first

    Returns:
        Result dict with 'ok' and optionally 'error'
    """
    from inspekt.config import get_typing_config
    from inspekt.services.script_loader import ScriptLoader

    # Focus the element first
    focus_code = f"""
    (function() {{
        const el = document.querySelector({json.dumps(selector)});
        if (!el) {{
            return {{ error: 'Element not found: ' + {json.dumps(selector)} }};
        }}
        el.focus();
        return {{ ok: true }};
    }})()
    """

    result = client.execute(focus_code, timeout=10.0)
    if not result.get("ok"):
        return {"ok": False, "error": result.get("error", "Focus failed")}

    focus_result = result.get("result", {})
    if focus_result.get("error"):
        return {"ok": False, "error": focus_result["error"]}

    # Load send_keys script
    script_loader = ScriptLoader()
    try:
        script = script_loader.load_script_sync("send_keys.js")
    except FileNotFoundError as e:
        return {"ok": False, "error": f"Script not found: {e}"}

    # Get typing configuration
    typing_config = get_typing_config()
    typo_rate = typing_config.get('human-like-typo-rate', 0)

    # Human-like typing speed (delay_ms = -1 triggers human mode in send_keys.js)
    delay_ms = -1

    # Replace placeholders
    code = script.replace("TEXT_PLACEHOLDER", json.dumps(text))
    code = code.replace("DELAY_PLACEHOLDER", str(delay_ms))
    code = code.replace("CLEAR_PLACEHOLDER", "true" if clear else "false")
    code = code.replace("TYPO_RATE_PLACEHOLDER", str(typo_rate))

    # Calculate timeout based on text length
    # Human mode: ~300ms per char (base 240ms + pauses)
    estimated_time = len(text) * 0.3
    timeout = max(estimated_time + 10, 60.0)

    try:
        result = client.execute(code, timeout=timeout)

        if not result.get("ok"):
            return {"ok": False, "error": result.get("error", "Typing failed")}

        response = result.get("result", {})
        if response.get("error"):
            return {"ok": False, "error": response["error"]}

        return {"ok": True, "message": response.get("message", "Text typed successfully")}

    except Exception as e:
        return {"ok": False, "error": str(e)}


def run_inspekt_command(command: str) -> dict:
    """Run an inspekt command and return the result."""
    try:
        # Split command into parts
        parts = command.split()
        full_command = ["python", "-m", "inspekt"] + parts

        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=60,
        )

        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_condition(client: BridgeClient, condition: dict, script_template: str) -> dict:
    """Check if a condition is met.

    Args:
        client: BridgeClient instance
        condition: Condition dict (visible, hidden, text_contains, etc.)
        script_template: The check_condition.js script template

    Returns:
        dict with 'met' (bool), 'reason' (str), and 'ok' (bool for execution success)
    """
    condition_json = json.dumps(condition)
    code = script_template.replace("CONDITION_DATA_PLACEHOLDER", condition_json)

    try:
        exec_result = client.execute(code, timeout=5.0)

        if exec_result.get("ok"):
            response = exec_result.get("result", {})
            return {
                "ok": True,
                "met": response.get("met", False),
                "reason": response.get("reason", ""),
            }
        else:
            return {
                "ok": False,
                "met": False,
                "reason": exec_result.get("error", "Execution failed"),
            }

    except Exception as e:
        return {
            "ok": False,
            "met": False,
            "reason": str(e),
        }


def wait_for_condition(
    client: BridgeClient,
    condition: dict,
    script_template: str,
    timeout_ms: int = 5000,
    poll_interval_ms: int = 100,
) -> dict:
    """Wait for a condition to be met, polling at intervals.

    Args:
        client: BridgeClient instance
        condition: Condition dict
        script_template: The check_condition.js script template
        timeout_ms: Maximum time to wait in milliseconds
        poll_interval_ms: Time between checks in milliseconds

    Returns:
        dict with 'met' (bool), 'reason' (str), 'timed_out' (bool)
    """
    start_time = time.time()
    timeout_sec = timeout_ms / 1000.0
    poll_interval_sec = poll_interval_ms / 1000.0

    last_result = {"met": False, "reason": ""}

    while (time.time() - start_time) < timeout_sec:
        result = check_condition(client, condition, script_template)

        if not result.get("ok"):
            # Execution error, try again
            time.sleep(poll_interval_sec)
            continue

        if result.get("met"):
            return {
                "met": True,
                "reason": result.get("reason", ""),
                "timed_out": False,
            }

        last_result = result
        time.sleep(poll_interval_sec)

    # Final check
    result = check_condition(client, condition, script_template)
    if result.get("met"):
        return {
            "met": True,
            "reason": result.get("reason", ""),
            "timed_out": False,
        }

    return {
        "met": False,
        "reason": last_result.get("reason", "Condition not met"),
        "timed_out": True,
    }


def _generate_assertion_description(expect) -> str | None:
    """Generate a human-readable description of assertions when no message is provided."""
    if not expect:
        return None

    parts = []
    if expect.visible:
        parts.append(f"visible: {expect.visible}")
    if expect.hidden:
        parts.append(f"hidden: {expect.hidden}")
    if expect.text_contains:
        parts.append(f"text contains: {expect.text_contains}")
    if expect.url_contains:
        parts.append(f"URL contains: {expect.url_contains}")
    if expect.focused:
        parts.append("element has focus")
    if expect.checked:
        parts.append(f"checked: {expect.checked}")
    if expect.unchecked:
        parts.append(f"unchecked: {expect.unchecked}")
    if expect.value_equals is not None:
        selector = expect.value or "target"
        parts.append(f"value equals: {expect.value_equals}")
    if expect.count is not None and expect.count_equals is not None:
        parts.append(f"count({expect.count}) = {expect.count_equals}")

    return ", ".join(parts) if parts else None


def check_inspekt_expectations(command: str, expect: dict, cmd_result: dict) -> list[str]:
    """Check expectations for an inspekt command."""
    import re

    failures = []

    if not expect:
        return failures

    stdout = cmd_result.get("stdout", "")

    # For console commands, check if output is empty
    if "console" in command and expect.get("empty"):
        # Check if there are any log entries (non-empty, non-header output)
        lines = [l for l in stdout.strip().split("\n") if l.strip() and not l.startswith("Console")]
        if lines:
            failures.append(f"Expected no console messages, but found: {len(lines)} message(s)")

    # For axe commands, check violations
    # Use "allowed-violations" (default: 0 = strict mode)
    if "axe" in command:
        # Support both "allowed-violations" (preferred) and legacy "violations"
        allowed = expect.get("allowed-violations", expect.get("violations", 0))
        # Try to parse violation count from output
        matches = re.findall(r"(\d+)\s*violation", stdout.lower())
        if matches:
            actual_violations = int(matches[0])
            if actual_violations > allowed:
                failures.append(f"Expected max {allowed} violations, found {actual_violations}")
        elif "0 violations" not in stdout.lower() and allowed == 0:
            # If we can't parse and expect 0, check for "0 violations" text
            if "violation" in stdout.lower():
                failures.append("Expected 0 violations but found some (could not parse count)")

    # Generic output assertions (work with any inspekt command)
    if expect.get("output-contains"):
        text = expect["output-contains"]
        if text not in stdout:
            failures.append(f"Output does not contain: '{text}'")

    if expect.get("output-not-contains"):
        text = expect["output-not-contains"]
        if text in stdout:
            failures.append(f"Output should not contain: '{text}'")

    if expect.get("output-matches"):
        pattern = expect["output-matches"]
        try:
            if not re.search(pattern, stdout, re.MULTILINE):
                failures.append(f"Output does not match pattern: '{pattern}'")
        except re.error as e:
            failures.append(f"Invalid regex pattern '{pattern}': {e}")

    return failures


# =============================================================================
# Download Assertion Checking
# =============================================================================

# Shell command allowlist for download assertions
# These are safe, read-only commands for file inspection
DOWNLOAD_SHELL_ALLOWLIST: dict[str, list[str]] = {
    "file": ["file", "-b"],  # MIME type detection
    "pdfinfo": ["pdfinfo"],  # PDF metadata
    "identify": ["identify", "-format", "%m %w %h"],  # ImageMagick
    "exiftool": ["exiftool", "-j"],  # EXIF metadata
    "wc": ["wc"],  # Word/line/byte count
    "head": ["head"],  # First lines
    "tail": ["tail"],  # Last lines
    "grep": ["grep"],  # Pattern matching
    "md5sum": ["md5sum"],  # MD5 checksum
    "sha256sum": ["sha256sum"],  # SHA256 checksum
    "stat": ["stat"],  # File stats
    "strings": ["strings"],  # Extract printable strings
}


def check_download_assertions(
    download_info: dict,
    expect: dict,
    downloaded_file_path: Path,
) -> list[str]:
    """Check download-specific assertions.

    Args:
        download_info: Download metadata from the step
        expect: ExpectInfo dictionary with assertions
        downloaded_file_path: Path to the downloaded file

    Returns:
        List of failure messages (empty if all passed)
    """
    import hashlib

    failures = []

    if not expect:
        return failures

    file_exists = downloaded_file_path.exists() if downloaded_file_path else False

    # Check file exists
    if expect.get("download_exists"):
        if not file_exists:
            failures.append(f"Downloaded file not found: {downloaded_file_path}")
            return failures  # Can't check other assertions if file doesn't exist

    # Check MIME type
    if expect.get("download_mime_type"):
        expected = expect["download_mime_type"]
        actual = download_info.get("mime_type", "")
        if actual != expected:
            failures.append(f"Expected MIME type '{expected}', got '{actual}'")

    if expect.get("download_mime_type_contains"):
        expected = expect["download_mime_type_contains"]
        actual = download_info.get("mime_type", "")
        if expected not in actual:
            failures.append(f"Expected MIME type to contain '{expected}', got '{actual}'")

    # Check file size
    if expect.get("download_size") is not None:
        expected = expect["download_size"]
        actual = download_info.get("size", 0)
        if actual != expected:
            failures.append(f"Expected size {expected} bytes, got {actual} bytes")

    if expect.get("download_size_min") is not None:
        minimum = expect["download_size_min"]
        actual = download_info.get("size", 0)
        if actual < minimum:
            failures.append(f"File size {actual} bytes is below minimum {minimum} bytes")

    if expect.get("download_size_max") is not None:
        maximum = expect["download_size_max"]
        actual = download_info.get("size", 0)
        if actual > maximum:
            failures.append(f"File size {actual} bytes exceeds maximum {maximum} bytes")

    # Check filename
    if expect.get("download_filename"):
        expected = expect["download_filename"]
        actual = download_info.get("filename", "")
        if actual != expected:
            failures.append(f"Expected filename '{expected}', got '{actual}'")

    if expect.get("download_filename_contains"):
        expected = expect["download_filename_contains"]
        actual = download_info.get("filename", "")
        if expected not in actual:
            failures.append(f"Expected filename to contain '{expected}', got '{actual}'")

    # Check text content (for text files)
    if expect.get("download_content_contains") and file_exists:
        expected_text = expect["download_content_contains"]
        try:
            content = downloaded_file_path.read_text(errors="ignore")
            if expected_text not in content:
                failures.append(f"Downloaded file does not contain: '{expected_text}'")
        except Exception as e:
            failures.append(f"Could not read file content: {e}")

    # Check checksum
    if expect.get("download_checksum") and file_exists:
        checksum_spec = expect["download_checksum"]
        if ":" in checksum_spec:
            algo, expected_hash = checksum_spec.split(":", 1)
        else:
            algo, expected_hash = "md5", checksum_spec

        try:
            file_bytes = downloaded_file_path.read_bytes()

            if algo.lower() == "md5":
                actual_hash = hashlib.md5(file_bytes).hexdigest()
            elif algo.lower() in ("sha256", "sha-256"):
                actual_hash = hashlib.sha256(file_bytes).hexdigest()
            else:
                failures.append(f"Unknown checksum algorithm: {algo}")
                return failures

            if actual_hash.lower() != expected_hash.lower():
                failures.append(f"Checksum mismatch: expected {expected_hash}, got {actual_hash}")
        except Exception as e:
            failures.append(f"Could not compute checksum: {e}")

    # Run shell command
    if expect.get("download_shell") and file_exists:
        shell_result = run_download_shell_command(
            expect["download_shell"],
            downloaded_file_path,
        )
        if not shell_result.get("ok"):
            failures.append(f"Shell command failed: {shell_result.get('error')}")

    return failures


def run_download_shell_command(command: str, file_path: Path) -> dict:
    """Run an allowlisted shell command on a downloaded file.

    Args:
        command: Shell command name (must be in DOWNLOAD_SHELL_ALLOWLIST)
        file_path: Path to the downloaded file

    Returns:
        dict with 'ok', 'stdout', 'stderr', 'returncode'
    """
    import subprocess

    # Parse command (e.g., "file" or "grep pattern")
    parts = command.strip().split(maxsplit=1)
    cmd_name = parts[0]
    cmd_args = parts[1] if len(parts) > 1 else ""

    if cmd_name not in DOWNLOAD_SHELL_ALLOWLIST:
        return {
            "ok": False,
            "error": f"Command '{cmd_name}' not in allowlist. Allowed: {list(DOWNLOAD_SHELL_ALLOWLIST.keys())}",
        }

    try:
        base_cmd = DOWNLOAD_SHELL_ALLOWLIST[cmd_name].copy()

        # Add any additional args
        if cmd_args:
            base_cmd.extend(cmd_args.split())

        # Add file path as last argument
        base_cmd.append(str(file_path))

        result = subprocess.run(
            base_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out (30s)"}
    except FileNotFoundError:
        return {"ok": False, "error": f"Command '{cmd_name}' not found on system"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@click.command()
@click.argument("recording_file", type=click.Path(exists=True), required=False, default=None, shell_complete=complete_recording_files)
@click.option(
    "--speed",
    type=float,
    default=1.0,
    help="Playback speed multiplier (e.g., 2.0 for 2x speed, 0.5 for half speed)",
)
@click.option(
    "--slow",
    is_flag=True,
    help="Half speed (0.5x) - same as --speed 0.5",
)
@click.option(
    "--very-slow",
    is_flag=True,
    help="Quarter speed (0.25x) - same as --speed 0.25",
)
@click.option(
    "--instant",
    is_flag=True,
    help="No delays between steps - fastest playback",
)
@click.option(
    "--step-delay",
    type=int,
    default=0,
    help="Delay between steps in milliseconds (default: 0, instant)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show steps without executing them",
)
@click.option(
    "--start-step",
    type=int,
    default=1,
    help="Start from step number (1-indexed)",
)
@click.option(
    "--end-step",
    type=int,
    default=None,
    help="End at step number (1-indexed, inclusive)",
)
@click.option(
    "--skip-hover",
    is_flag=True,
    help="Skip all hover actions",
)
@click.option(
    "--skip",
    multiple=True,
    type=click.Choice(["hover", "keypress", "type", "click", "navigate"]),
    help="Skip specific action types (can be used multiple times)",
)
@click.option(
    "--pause-on-fail",
    is_flag=True,
    help="Pause and wait for Enter after each failure",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output for each step",
)
@click.option(
    "--no-visual",
    "no_visual",
    is_flag=True,
    help="Disable visual indicators (circle at target, typing indicator)",
)
@click.option(
    "--no-audio",
    "no_audio",
    is_flag=True,
    help="Disable synthesized audio cues for actions",
)
@click.option(
    "--no-feedback",
    "no_feedback",
    is_flag=True,
    help="Disable both visual and audio feedback",
)
@click.option(
    "--lock",
    is_flag=True,
    help="Lock input during replay (hide cursor, ignore keyboard/mouse/scroll)",
)
@click.option(
    "--restore-viewport",
    is_flag=True,
    hidden=True,  # Deprecated: use --match-viewport instead
    help="[DEPRECATED] Use --match-viewport instead",
)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Step through replay manually (Enter=next, Space=skip, Escape=cancel)",
)
@click.option(
    "--stop-on-error",
    "-e",
    is_flag=True,
    help="Stop replay on first failure (assertion or execution error)",
)
@click.option(
    "--skip-tests",
    "-T",
    is_flag=True,
    help="Skip assertion checks (run actions without evaluating expect conditions)",
)
@click.option(
    "--restore-state",
    is_flag=True,
    help="Restore all captured state (cookies, localStorage, sessionStorage)",
)
@click.option(
    "--restore-cookies",
    is_flag=True,
    help="Restore cookies from recording state",
)
@click.option(
    "--restore-storage",
    is_flag=True,
    help="Restore localStorage/sessionStorage from recording state",
)
@click.option(
    "--verify-checksum",
    is_flag=True,
    help="Verify DOM structure checksum matches recording",
)
@click.option(
    "--strict-preconditions",
    is_flag=True,
    help="Halt replay if preconditions are not met (default: warn only)",
)
@click.option(
    "--strict-checksum",
    is_flag=True,
    help="Halt replay if checksum does not match (default: warn only)",
)
@click.option(
    "--progress",
    "-p",
    is_flag=True,
    help="Show compact progress bar instead of step-by-step output",
)
@click.option(
    "--skip-validation",
    is_flag=True,
    help="Skip preflight validation checks",
)
@click.option(
    "--video",
    "video_output",
    type=click.Path(),
    default=None,
    help="Record replay to video file (MP4/WebM). Use filename or --video for auto-naming.",
    is_flag=False,
    flag_value="__auto__",
)
@click.option(
    "--fps",
    "video_fps",
    type=int,
    default=None,
    help="Video frame rate (5-30, uses config default: 10)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open video file in default application after creation",
)
@click.option(
    "--include-effects/--no-effects",
    "include_effects",
    default=False,
    help="Include audio effects in video (click sounds, etc.)",
)
@click.option(
    "--match-viewport",
    is_flag=True,
    help="Attempt to resize browser to match recorded viewport dimensions",
)
@click.option(
    "--match-zoom-level",
    is_flag=True,
    help="Attempt to set browser zoom to match recorded zoom level",
)
def replay(
    recording_file: Optional[str],
    speed: float,
    slow: bool,
    very_slow: bool,
    instant: bool,
    step_delay: int,
    dry_run: bool,
    start_step: int,
    end_step: Optional[int],
    skip_hover: bool,
    skip: tuple,
    pause_on_fail: bool,
    verbose: bool,
    no_visual: bool,
    no_audio: bool,
    no_feedback: bool,
    lock: bool,
    restore_viewport: bool,
    interactive: bool,
    stop_on_error: bool,
    skip_tests: bool,
    restore_state: bool,
    restore_cookies: bool,
    restore_storage: bool,
    verify_checksum: bool,
    strict_preconditions: bool,
    strict_checksum: bool,
    progress: bool,
    skip_validation: bool,
    video_output: Optional[str],
    video_fps: Optional[int],
    open_after: bool,
    include_effects: bool,
    match_viewport: bool,
    match_zoom_level: bool,
):
    """
    Replay a recorded browser interaction session.

    Executes all steps from a YAML recording file against the current browser.
    Reports all assertion failures at the end (continues on failure).

    \b
    Speed options:
        --slow        Half speed (0.5x)
        --very-slow   Quarter speed (0.25x)
        --instant     No delays between steps
        --speed N     Custom speed multiplier

    \b
    Filtering options:
        --skip-hover  Skip all hover actions
        --skip TYPE   Skip specific action types (hover, keypress, type, click)

    \b
    Interactive mode:
        --interactive, -i   Step through manually in the browser
                            Press Enter to execute, Space to skip, Escape to cancel

    \b
    Video recording:
        --video PATH    Record replay to video file (requires ffmpeg)
        --video         Auto-name video file based on recording
        --fps N         Custom frame rate (5-30, default: 10)

    \b
    Examples:
        inspekt replay                             # Replay most recent recording
        inspekt replay login-flow.yaml             # Replay at normal speed
        inspekt replay login-flow.yaml --slow      # Replay at half speed
        inspekt replay login-flow.yaml --instant   # Fast replay, no delays
        inspekt replay login-flow.yaml --skip-hover    # Skip hovers
        inspekt replay login-flow.yaml --dry-run   # Preview steps
        inspekt replay login-flow.yaml --pause-on-fail # Debug failures
        inspekt replay login-flow.yaml -i          # Interactive step-through
        inspekt replay login-flow.yaml --video     # Record to auto-named MP4
        inspekt replay login-flow.yaml --video=journey.mp4  # Custom filename
        inspekt replay login-flow.yaml --video --fps=15     # 15fps video
        inspekt replay login-flow.yaml --video --open       # Record and open video
    """
    # If no recording file specified, find the most recent one
    auto_selected = False
    if recording_file is None:
        recent = find_most_recent_recording()
        if recent is None:
            click.echo("Error: No recording file specified and no .yaml files found in current directory.", err=True)
            sys.exit(1)
        recording_file = str(recent)
        auto_selected = True

    # Handle video recording setup
    screencast_capture = None
    video_recording_enabled = False
    resolved_video_path = None

    if video_output is not None:
        # Check if ffmpeg is installed
        from inspekt.services.ffmpeg_utils import ensure_ffmpeg, get_ffmpeg_version, probe_video, merge_audio_video

        if not ensure_ffmpeg(auto_prompt=True):
            click.echo("Error: ffmpeg is required for video recording.", err=True)
            sys.exit(1)

        # Show ffmpeg version if verbose
        if verbose:
            version = get_ffmpeg_version()
            click.echo(format_system_message(f"Using ffmpeg {version}"))

        # Get video config
        video_config = get_video_config()

        # Resolve video output path
        if video_output == "__auto__":
            # Auto-generate filename from recording file
            rec_path = Path(recording_file)
            video_filename = rec_path.stem + "_replay.mp4"
            resolved_video_path = Path.cwd() / video_filename
        else:
            resolved_video_path = Path(video_output).resolve()
            # Add .mp4 extension if missing
            if not resolved_video_path.suffix:
                resolved_video_path = resolved_video_path.with_suffix(".mp4")

        # Get FPS from CLI or config
        actual_fps = video_fps if video_fps is not None else video_config.get("fps", 10)
        actual_quality = video_config.get("quality", 80)

        # Clamp FPS to valid range
        actual_fps = max(5, min(30, actual_fps))

        video_recording_enabled = True

        # Validate output path is writable before starting replay
        # This prevents wasted time if the path is invalid
        try:
            output_parent = resolved_video_path.parent
            if not output_parent.exists():
                output_parent.mkdir(parents=True, exist_ok=True)
            # Test write access with a temp file
            test_file = output_parent / f".inspekt_write_test_{os.getpid()}"
            test_file.touch()
            test_file.unlink()
        except (OSError, PermissionError) as e:
            click.echo(f"Error: Cannot write to video output path: {resolved_video_path}", err=True)
            click.echo(f"  Reason: {e}", err=True)
            sys.exit(1)

        if dry_run:
            click.echo(f"\n[Video would be recorded to: {resolved_video_path}]")

    # Apply speed presets (priority: interactive > instant > very_slow > slow > speed)
    if interactive:
        # Interactive mode: no timing delays, user controls pace
        step_delay = 0
        speed = float("inf")
        # Interactive mode always enables input lock to prevent Tab/keyboard interference
        lock = True
    elif instant:
        step_delay = 0
        speed = float("inf")  # Effectively no delay
    elif very_slow:
        speed = 0.25
    elif slow:
        speed = 0.5

    # Compute visual/audio from --no-* flags (default is ON)
    # --no-feedback disables both
    # Interactive mode always needs visual (for the overlay)
    if no_feedback and not interactive:
        visual = False
        audio = False
    else:
        visual = not no_visual or interactive  # Interactive mode requires visual
        audio = not no_audio

    # Enable input lock by default when visual feedback is enabled
    # This prevents user interaction during replay (hiding cursor, blocking keyboard/mouse)
    if visual:
        lock = True

    # Get audio config to determine output method
    audio_config = get_audio_config()
    audio_output = audio_config["output"]  # "cli" | "browser" | "off"
    audio_volume = audio_config["volume"]

    # If config says "off", disable audio regardless of CLI flag
    if audio_output == "off":
        audio = False

    # Create CLI audio instance if using CLI audio or if --include-effects is used
    cli_audio: CLIAudio | None = None
    use_browser_audio = False
    if audio:
        if audio_output == "cli":
            cli_audio = CLIAudio(volume=audio_volume)
        else:  # "browser"
            use_browser_audio = True

    # Also create CLI audio if --include-effects is used (for generating audio track)
    if include_effects and cli_audio is None:
        cli_audio = CLIAudio(volume=audio_volume)

    # Build skip set from options
    skip_actions = set(skip)
    if skip_hover:
        skip_actions.add("hover")

    # Load recording
    recording_path = Path(recording_file)

    # Preflight validation (unless skipped via flag or config)
    from inspekt.config import get_replay_config

    replay_config = get_replay_config()
    should_validate = replay_config.get("validate", True) and not skip_validation

    if should_validate:
        from inspekt.app.cli.validation import display_validation_results, validate_recording_file

        validation_result = validate_recording_file(recording_path)

        if not validation_result.valid:
            display_validation_results(validation_result, recording_path)
            sys.exit(1)

        if validation_result.warnings:
            display_validation_results(validation_result, recording_path)
            click.echo()
            if not click.confirm("Continue with replay?", default=True):
                sys.exit(0)
            click.echo()

    try:
        with _builtin_open(recording_path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        click.echo(f"Error loading recording: {e}", err=True)
        sys.exit(1)

    # Parse recording
    try:
        recording = Recording(**data)
    except Exception as e:
        click.echo(f"Error parsing recording: {e}", err=True)
        sys.exit(1)

    steps = recording.steps
    total_steps = len(steps)

    if total_steps == 0:
        click.echo("Recording contains no steps.", err=True)
        sys.exit(1)

    # Apply step range
    start_idx = max(0, start_step - 1)
    end_idx = min(total_steps, end_step) if end_step else total_steps
    steps_to_run = steps[start_idx:end_idx]

    # Format the recording date nicely
    recorded_date = recording.metadata.created_at.strftime("%B %d, %Y at %H:%M")

    # Get file's last modified time from filesystem
    file_mtime = datetime.fromtimestamp(recording_path.stat().st_mtime)
    last_modified = file_mtime.strftime("%B %d, %Y at %H:%M")

    # Build title with optional (last modified) suffix
    title_suffix = " (last modified)" if auto_selected else ""
    title = f"{recording_path.name}{title_suffix}"

    # Support both v1.0 (viewport in metadata) and v1.1 (viewport in state)
    viewport = recording.state.viewport if recording.state else getattr(recording.metadata, 'viewport', None)
    viewport_str = f"{viewport.width}×{viewport.height}" if viewport else "unknown"

    # Build steps string
    steps_str = f"{len(steps_to_run)} of {total_steps}"
    if start_step > 1 or end_step:
        steps_str += f" (steps {start_idx + 1}-{end_idx})"

    # Display metadata in a table
    from inspekt.app.cli.table import Table

    # Build rows for width calculation
    rows = [
        ["Recorded", recorded_date],
        ["Last Modified", last_modified],
        ["URL", recording.metadata.starting_url],
        ["Viewport", viewport_str],
        ["Steps", steps_str],
    ]

    table = Table(["Key", "Value"], title=title, icon="󰨛")
    table.set_data(rows)

    click.echo()
    table.print_header(skip_column_headers=True)
    table.print_row(["Recorded", recorded_date])
    table.print_row(["Last Modified", last_modified])
    table.print_row(["URL", click.style(recording.metadata.starting_url, fg="blue", underline=True)])
    table.print_row(["Viewport", viewport_str])
    table.print_row(["Steps", steps_str])
    table.print_footer()

    if dry_run:
        click.echo("\n[DRY RUN - not executing]\n")
    else:
        click.echo()

    # Initialize result tracking
    result = ReplayResult()
    result.total_steps = len(steps_to_run)
    result.start_time = datetime.now()

    # Connect to browser (unless dry run)
    client = None
    script_template = None
    condition_script_template = None

    if not dry_run:
        client = BridgeClient()

        if not client.is_alive():
            from inspekt.app.cli.table import _style_with_inline_code
            click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
            sys.exit(1)

        # Check CSP bypass status and warn if disabled
        if not check_csp_bypass_enabled():
            click.echo()
            click.secho("  ⚠  CSP bypass is disabled", fg="yellow", bold=True)
            click.echo("     Some sites may not work correctly during replay.")
            click.echo("     Enable it with: inspekt domain csp --enable")
            click.echo("     Or toggle it in the Inspekt extension popup.")
            click.echo()

        # Focus the browser tab before starting replay (macOS only)
        focus_browser_tab(client, verbose=verbose)

        # Issue 12: Handle deprecated --restore-viewport flag
        if restore_viewport:
            click.secho(
                "⚠ --restore-viewport is deprecated. Use --match-viewport instead.",
                fg="yellow",
            )
            match_viewport = True  # Treat as alias

        # Issue 11: Enforce require_viewport_match and require_zoom_match from YAML
        if recording.state:
            if recording.state.require_viewport_match and not match_viewport:
                from inspekt.app.cli.table import print_warning
                print_warning(
                    "This recording requires viewport matching (`require_viewport_match: true`). "
                    "Auto-enabling `--match-viewport` for faithful replay."
                )
                click.echo()  # Extra line break before step table
                match_viewport = True

            if recording.state.require_zoom_match and not match_zoom_level:
                from inspekt.app.cli.table import print_warning
                print_warning(
                    "This recording requires zoom matching (`require_zoom_match: true`). "
                    "Auto-enabling `--match-zoom-level` for faithful replay."
                )
                click.echo()  # Extra line break before step table
                match_zoom_level = True

        # Get current viewport and zoom level for comparison
        current_state_code = """
        (async () => {
            // Get current viewport
            const currentViewport = {
                width: window.innerWidth,
                height: window.innerHeight
            };

            // Get current browser zoom level via message bridge
            let browserZoomLevel = 1.0;
            try {
                browserZoomLevel = await new Promise((resolve) => {
                    const requestId = 'zoom-check-' + Date.now();
                    const handler = (event) => {
                        if (event.data?.type === 'INSPEKT_ZOOM_LEVEL_RESPONSE' &&
                            event.data?.requestId === requestId) {
                            window.removeEventListener('message', handler);
                            resolve(event.data.response?.zoomFactor || 1.0);
                        }
                    };
                    window.addEventListener('message', handler);
                    window.postMessage({
                        type: 'INSPEKT_GET_ZOOM_LEVEL',
                        source: 'inspekt-page',
                        requestId: requestId
                    }, '*');
                    setTimeout(() => resolve(1.0), 2000);
                });
            } catch (e) {
                browserZoomLevel = 1.0;
            }

            return {
                viewport: currentViewport,
                browserZoomLevel: browserZoomLevel,
                devicePixelRatio: window.devicePixelRatio || 1
            };
        })()
        """

        current_state = {}
        try:
            state_result = client.execute(current_state_code, timeout=5.0)
            if state_result.get("ok"):
                current_state = state_result.get("result", {})
        except Exception:
            pass

        current_viewport = current_state.get("viewport", {})
        current_zoom = current_state.get("browserZoomLevel", 1.0)
        current_width = current_viewport.get("width", 0)
        current_height = current_viewport.get("height", 0)

        # Get recorded viewport and zoom from state
        recorded_viewport = recording.state.viewport if recording.state else None
        recorded_zoom = recording.state.browser_zoom_level if recording.state else 1.0
        recorded_window_mode = recording.state.window_mode if recording.state else None

        # Detect current window mode (fullscreen/kiosk/normal)
        # In fullscreen/kiosk mode, viewport cannot be resized
        current_window_mode = None
        in_fullscreen_mode = False
        fullscreen_check_js = """(function(){
            const isFullscreenAPI = !!(document.fullscreenElement ||
                                       document.webkitFullscreenElement ||
                                       document.mozFullScreenElement);
            const viewportEqualsScreen = window.innerWidth === window.screen.width &&
                                          window.innerHeight === window.screen.height;
            const outerEqualsScreen = window.outerWidth === window.screen.width &&
                                       window.outerHeight === window.screen.height;
            return {
                isFullscreen: isFullscreenAPI,
                isKiosk: !isFullscreenAPI && viewportEqualsScreen && outerEqualsScreen,
                mode: isFullscreenAPI ? 'fullscreen' :
                      (viewportEqualsScreen && outerEqualsScreen ? 'kiosk' : 'normal')
            };
        })()"""

        try:
            fs_result = client.execute(fullscreen_check_js, timeout=5.0)
            if fs_result.get("ok"):
                fs_info = fs_result.get("result", {})
                current_window_mode = fs_info.get("mode", "normal")
                in_fullscreen_mode = current_window_mode in ("fullscreen", "kiosk")
        except Exception:
            pass  # Default to normal mode if detection fails

        # Handle mode mismatches between recording and replay
        if recorded_window_mode and current_window_mode:
            if recorded_window_mode != current_window_mode:
                if recorded_window_mode in ("fullscreen", "kiosk") and current_window_mode == "normal":
                    # Recording was in fullscreen, replay is in normal mode
                    click.echo()
                    click.secho(
                        f"Note: Recording was made in {recorded_window_mode} mode, "
                        f"but replay is in normal window mode.",
                        fg="blue",
                    )
                    click.echo(f"   Viewport dimensions may differ. Use --match-viewport to resize.")
                elif current_window_mode in ("fullscreen", "kiosk") and recorded_window_mode == "normal":
                    # Recording was normal, replay is in fullscreen
                    click.echo()
                    click.secho(
                        f"Warning: Recording was made in normal window mode, "
                        f"but replay is in {current_window_mode} mode.",
                        fg="yellow",
                    )
                    click.echo(f"   Exit {current_window_mode} mode (press F11 or Esc) if viewport dimensions need to match.")

        # Check for viewport/zoom mismatch and show warning
        viewport_mismatch = False
        zoom_mismatch = False

        if recorded_viewport and current_width > 0:
            # Issue 21: Use exact matching (0px tolerance) instead of 10px
            viewport_mismatch = (
                current_width != recorded_viewport.width or
                current_height != recorded_viewport.height
            )
        if current_zoom > 0:
            zoom_mismatch = abs(current_zoom - recorded_zoom) > 0.05  # 5% tolerance

        # Show warning if there's a mismatch and no matching flags were provided
        if (viewport_mismatch or zoom_mismatch) and not match_viewport and not match_zoom_level:
            click.echo()
            click.secho(
                "⚠ Your browser's current viewport and zoom level are different from the recording.",
                fg="yellow",
            )
            click.echo("  This might be intentional. For a faithful replay, use:")
            if viewport_mismatch:
                click.echo(f"    inspekt replay --match-viewport  (recorded: {recorded_viewport.width}×{recorded_viewport.height}, current: {current_width}×{current_height})")
            if zoom_mismatch:
                click.echo(f"    inspekt replay --match-zoom-level  (recorded: {recorded_zoom:.0%}, current: {current_zoom:.0%})")
            click.echo()

        # Apply zoom matching if requested
        if match_zoom_level and zoom_mismatch:
            if verbose:
                click.echo(format_system_message(f"Setting zoom level to {recorded_zoom:.0%}..."))

            set_zoom_code = f"""
            (async () => {{
                return new Promise((resolve) => {{
                    const requestId = 'set-zoom-' + Date.now();
                    const handler = (event) => {{
                        if (event.data?.type === 'INSPEKT_ZOOM_SET_RESPONSE' &&
                            event.data?.requestId === requestId) {{
                            window.removeEventListener('message', handler);
                            resolve(event.data.response);
                        }}
                    }};
                    window.addEventListener('message', handler);
                    window.postMessage({{
                        type: 'INSPEKT_SET_ZOOM_LEVEL',
                        source: 'inspekt-page',
                        requestId: requestId,
                        zoomFactor: {recorded_zoom}
                    }}, '*');
                    setTimeout(() => resolve({{ ok: false }}), 2000);
                }});
            }})()
            """

            try:
                zoom_result = client.execute(set_zoom_code, timeout=3.0)
                if zoom_result.get("ok") and zoom_result.get("result", {}).get("ok"):
                    if verbose:
                        click.echo(format_system_message(f"Zoom level set to {recorded_zoom:.0%}"))
                else:
                    from inspekt.app.cli.table import print_warning
                    print_warning(f"Could not set zoom level to {recorded_zoom:.0%}")
            except Exception as e:
                from inspekt.app.cli.table import print_warning
                print_warning(f"Error setting zoom level: {e}")

        # Issue 4: Apply viewport matching with cached offsets (same logic as record.py)
        # Skip viewport matching in fullscreen/kiosk mode (window cannot be resized)
        if match_viewport and viewport_mismatch and recorded_viewport and in_fullscreen_mode:
            # Cannot resize in fullscreen/kiosk mode - show warning and skip
            click.echo()
            click.secho(
                f"Warning: Browser is in {current_window_mode} mode. Cannot resize viewport.",
                fg="yellow",
            )
            click.echo(f"   Recorded viewport: {recorded_viewport.width}×{recorded_viewport.height}")
            click.echo(f"   Current viewport: {current_width}×{current_height}")
            click.echo(f"   Exit {current_window_mode} mode (press F11 or Esc) to enable viewport matching.")
            click.echo()
            # Disable viewport matching for this run
            match_viewport = False

        if match_viewport and viewport_mismatch and recorded_viewport:
            target_width = recorded_viewport.width
            target_height = recorded_viewport.height

            if verbose:
                click.echo(format_system_message(f"Resizing viewport to {target_width}×{target_height}..."))

            # Import config functions for caching
            from inspekt.config import get_viewport_offsets, save_viewport_offsets

            # Helper to get actual viewport
            def get_actual_viewport() -> tuple[int | None, int | None]:
                verify_js = "(function(){ return { width: window.innerWidth, height: window.innerHeight }; })()"
                try:
                    result = client.execute(verify_js, timeout=5.0)
                    if result.get("ok"):
                        dims = result.get("result", {})
                        if isinstance(dims, dict):
                            w = dims.get("width")
                            h = dims.get("height")
                            if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                                return int(w), int(h)
                except Exception:
                    pass
                return None, None

            # Helper to attempt resize
            def attempt_resize(width: int, height: int) -> bool:
                if sys.platform == "darwin":
                    try:
                        from inspekt.services.applescript_utils import resize_browser_window
                        return resize_browser_window(width, height)
                    except Exception:
                        pass

                # JavaScript fallback
                js_resize = f"""(function(){{
                    try {{
                        const chromeWidth = window.outerWidth - window.innerWidth;
                        const chromeHeight = window.outerHeight - window.innerHeight;
                        window.resizeTo({width} + chromeWidth, {height} + chromeHeight);
                        return true;
                    }} catch (e) {{
                        return false;
                    }}
                }})()"""
                try:
                    result = client.execute(js_resize, timeout=5.0)
                    return result.get("ok", False) and result.get("result", False)
                except Exception:
                    return False

            resize_success = False
            cached_offsets = get_viewport_offsets()

            if cached_offsets and cached_offsets["width"] >= 0 and cached_offsets["height"] >= 0:
                # Use cached offsets - single resize attempt
                # Offset is positive (how much larger window is than viewport)
                # So we ADD offset to get the window size that yields target viewport
                adjusted_w = target_width + cached_offsets["width"]
                adjusted_h = target_height + cached_offsets["height"]
                attempt_resize(adjusted_w, adjusted_h)
                time.sleep(0.3)

                actual_w, actual_h = get_actual_viewport()
                # Exact match required
                if actual_w == target_width and actual_h == target_height:
                    if verbose:
                        click.echo(format_system_message(f"Viewport set to {actual_w}×{actual_h}"))
                    resize_success = True
                elif actual_w is not None:
                    if verbose:
                        click.echo(format_system_message(f"Cached offsets outdated (got {actual_w}×{actual_h}), calibrating..."))
                    cached_offsets = None  # Fall through to calibration

            # Calibration loop if cached offsets didn't work
            if not resize_success:
                max_attempts = 20
                adjustment_w, adjustment_h = 0, 0
                viewport_history: list[tuple[int, int]] = []

                for attempt in range(max_attempts):
                    adjusted_w = target_width - adjustment_w
                    adjusted_h = target_height - adjustment_h

                    attempt_resize(adjusted_w, adjusted_h)
                    time.sleep(0.3 * (1.1 ** attempt))  # Exponential backoff

                    actual_w, actual_h = get_actual_viewport()
                    if actual_w is None:
                        time.sleep(0.5)
                        actual_w, actual_h = get_actual_viewport()
                        if actual_w is None:
                            break

                    error_w = actual_w - target_width
                    error_h = actual_h - target_height

                    # Track viewport for oscillation detection
                    viewport_history.append((actual_w, actual_h))

                    # Exact match required
                    if error_w == 0 and error_h == 0:
                        # Save offsets for future use
                        # Note: adjustment is negative (error accumulation), but offset should be positive
                        offset_w = -adjustment_w
                        offset_h = -adjustment_h
                        save_viewport_offsets(offset_w, offset_h)
                        if verbose:
                            click.echo(format_system_message(f"Viewport set to {actual_w}×{actual_h}"))
                        resize_success = True
                        break

                    # Oscillation detection: if we see the same viewport twice in last 4 attempts
                    if len(viewport_history) >= 4:
                        recent = viewport_history[-4:]
                        current = (actual_w, actual_h)
                        if recent.count(current) >= 2:
                            click.secho(
                                f"⚠ Could not achieve the exact viewport (requested {target_width}×{target_height}, "
                                f"achieved {actual_w}×{actual_h}).\n"
                                f"   This issue is related to display scaling. Please try to use even values.",
                                fg="yellow",
                            )
                            break

                    # Adjust for next attempt
                    adjustment_w += error_w
                    adjustment_h += error_h

            # Show error if resize failed and we didn't already show an oscillation message
            if not resize_success:
                # Check if we exited due to oscillation (message already shown)
                oscillation_detected = False
                if len(viewport_history) >= 4:
                    recent = viewport_history[-4:]
                    if viewport_history and recent.count(viewport_history[-1]) >= 2:
                        oscillation_detected = True

                if not oscillation_detected:
                    if viewport_history:
                        last_w, last_h = viewport_history[-1]
                        click.secho(
                            f"⚠ Could not resize viewport to {target_width}×{target_height} "
                            f"(achieved {last_w}×{last_h}). Try manually resizing your browser window.",
                            fg="yellow",
                        )
                    else:
                        click.secho(
                            f"⚠ Could not resize viewport to {target_width}×{target_height}. "
                            "Try manually resizing your browser window.",
                            fg="yellow",
                        )

        # Legacy restore_viewport is now handled above (converted to match_viewport)
        # This block is kept for backwards compatibility but should not trigger
        # since restore_viewport sets match_viewport = True
        if restore_viewport and viewport and not match_viewport:
            target_width = viewport.width
            target_height = viewport.height

            if verbose:
                click.echo(format_system_message(f"Restoring viewport to {target_width}x{target_height}..."))

            # Try to resize the browser window
            resize_code = f"""
            (function() {{
                const targetWidth = {target_width};
                const targetHeight = {target_height};

                // Try to resize the window
                try {{
                    window.resizeTo(
                        targetWidth + (window.outerWidth - window.innerWidth),
                        targetHeight + (window.outerHeight - window.innerHeight)
                    );
                }} catch (e) {{
                    // Resize may be blocked by browser
                }}

                // Return current viewport dimensions
                return {{
                    width: window.innerWidth,
                    height: window.innerHeight,
                    targetWidth: targetWidth,
                    targetHeight: targetHeight
                }};
            }})()
            """

            resize_result = client.execute(resize_code, timeout=5.0)
            if resize_result.get("ok"):
                result_data = resize_result.get("result", {})
                current_width = result_data.get("width", 0)
                current_height = result_data.get("height", 0)

                # Check if resize worked (allow small tolerance)
                width_diff = abs(current_width - target_width)
                height_diff = abs(current_height - target_height)

                if width_diff > 10 or height_diff > 10:
                    click.secho(
                        f"⚠ Viewport mismatch: current {current_width}x{current_height}, "
                        f"recorded {target_width}x{target_height}",
                        fg="yellow",
                    )
                    from inspekt.app.cli.table import print_hint
                    print_hint("Manually resize your browser window for best results.")
                elif verbose:
                    click.echo(format_system_message(f"Viewport set to {current_width}x{current_height}"))

        # Navigate to starting URL and hard reload for clean state
        starting_url = recording.metadata.starting_url
        if starting_url:
            if verbose:
                click.echo(format_system_message(f"Navigating to {starting_url}..."))

            # Navigate to the starting URL
            nav_code = f"""
            (function() {{
                const targetUrl = {json.dumps(starting_url)};
                const currentUrl = location.href;

                // Check if we're already on the correct URL
                if (currentUrl === targetUrl) {{
                    // Same URL - do a hard reload (bypass cache)
                    location.reload(true);
                    return {{ action: 'reload', url: targetUrl }};
                }} else {{
                    // Different URL - navigate to it
                    location.href = targetUrl;
                    return {{ action: 'navigate', url: targetUrl }};
                }}
            }})()
            """

            try:
                nav_result = client.execute(nav_code, timeout=5.0)
                if verbose and nav_result.get("ok"):
                    action = nav_result.get("result", {}).get("action", "navigate")
                    click.echo(format_system_message(f"Page {action}ed"))

                # Wait for page to be fully loaded after navigation/reload
                for attempt in range(30):  # Max 15 seconds
                    time.sleep(0.5)
                    ready_result = client.execute("document.readyState", timeout=3.0)
                    if ready_result.get("ok") and ready_result.get("result") == "complete":
                        break

                # Small additional delay for any post-load JavaScript
                time.sleep(0.3)

            except Exception as e:
                if verbose:
                    click.echo(format_system_message(f"Navigation warning: {e}"))
                # Continue anyway - page might still be usable

        # State restoration and verification (v1.1 format)
        if recording.state:
            import base64

            # Verify preconditions if present
            if recording.preconditions and recording.preconditions.required:
                if verbose:
                    click.echo(format_system_message("Checking preconditions..."))

                for precondition in recording.preconditions.required:
                    check_code = f"""
                        (function() {{
                            try {{
                                const el = document.querySelector({json.dumps(precondition.selector)});
                                return {{ found: !!el }};
                            }} catch (e) {{
                                return {{ found: false, error: e.message }};
                            }}
                        }})()
                    """
                    check_result = client.execute(check_code, timeout=3.0)
                    if check_result.get("ok"):
                        result_data = check_result.get("result", {})
                        if not result_data.get("found"):
                            desc = precondition.description or precondition.selector
                            if strict_preconditions:
                                from inspekt.app.cli.table import print_error, print_hint
                                print_error(f"Precondition failed: {desc}")
                                print_hint("Use `--no-strict-preconditions` to continue anyway.")
                                sys.exit(1)
                            else:
                                from inspekt.app.cli.table import print_warning
                                print_warning(f"Precondition not met: {desc}")
                        elif verbose:
                            desc = precondition.description or precondition.selector
                            click.echo(format_system_message(f"✓ {desc}"))

            # Verify checksum if requested
            if verify_checksum and recording.state.checksum:
                import hashlib
                if verbose:
                    click.echo(format_system_message("Verifying DOM checksum..."))

                checksum_code = """
                    (function() {
                        function getStructure(node) {
                            if (node.nodeType !== 1) return '';
                            const children = Array.from(node.children).map(getStructure).join('');
                            return '<' + node.tagName.toLowerCase() + '>' + children + '</' + node.tagName.toLowerCase() + '>';
                        }
                        return getStructure(document.body);
                    })()
                """
                checksum_result = client.execute(checksum_code, timeout=5.0)
                if checksum_result.get("ok"):
                    structure = checksum_result.get("result", "")
                    current_hash = f"sha256:{hashlib.sha256(structure.encode()).hexdigest()}"

                    if current_hash != recording.state.checksum:
                        if strict_checksum:
                            from inspekt.app.cli.table import print_error
                            print_error("DOM checksum mismatch - page structure has changed")
                            from inspekt.app.cli.table import print_hint
                            print_hint("Use `--no-strict-checksum` to continue anyway.")
                            sys.exit(1)
                        else:
                            from inspekt.app.cli.table import print_warning
                            print_warning("DOM checksum mismatch - page structure differs from recording")
                    elif verbose:
                        click.echo(format_system_message("✓ DOM checksum matches"))

            # Restore cookies if requested
            should_restore_cookies = restore_state or restore_cookies
            if should_restore_cookies and recording.state.cookies:
                if verbose:
                    click.echo(format_system_message("Restoring cookies..."))

                try:
                    cookies_json = base64.b64decode(recording.state.cookies).decode()
                    cookies_list = json.loads(cookies_json)

                    # Use extension bridge to set cookies (supports HttpOnly)
                    restore_code = f"""
                        new Promise((resolve) => {{
                            const requestId = 'set-cookies-' + Date.now();
                            const handler = (event) => {{
                                if (event.data?.type === 'INSPEKT_SET_COOKIES_RESPONSE' &&
                                    event.data?.requestId === requestId) {{
                                    window.removeEventListener('message', handler);
                                    resolve(event.data.response);
                                }}
                            }};
                            window.addEventListener('message', handler);
                            window.postMessage({{
                                type: 'INSPEKT_SET_COOKIES',
                                source: 'inspekt-page',
                                requestId: requestId,
                                cookies: {json.dumps(cookies_list)}
                            }}, '*');
                            setTimeout(() => {{
                                window.removeEventListener('message', handler);
                                resolve({{ ok: false, error: 'timeout' }});
                            }}, 3000);
                        }})
                    """
                    result = client.execute(restore_code, timeout=5.0)
                    if verbose:
                        if result.get("ok"):
                            click.echo(format_system_message(f"✓ Restored {len(cookies_list)} cookies"))
                        else:
                            from inspekt.app.cli.table import print_warning
                            print_warning("Failed to restore cookies")
                except Exception as e:
                    from inspekt.app.cli.table import print_warning
                    print_warning(f"Cookie restoration failed: {e}")

            # Restore localStorage/sessionStorage if requested
            should_restore_storage = restore_state or restore_storage
            if should_restore_storage:
                if recording.state.local_storage:
                    try:
                        storage_json = base64.b64decode(recording.state.local_storage).decode()
                        storage_data = json.loads(storage_json)

                        restore_code = f"""
                            (function() {{
                                const data = {json.dumps(storage_data)};
                                Object.entries(data).forEach(([k, v]) => localStorage.setItem(k, v));
                                return {{ restored: Object.keys(data).length }};
                            }})()
                        """
                        result = client.execute(restore_code, timeout=3.0)
                        if verbose and result.get("ok"):
                            count = result.get("result", {}).get("restored", 0)
                            click.echo(format_system_message(f"✓ Restored {count} localStorage keys"))
                    except Exception as e:
                        from inspekt.app.cli.table import print_warning
                        print_warning(f"`localStorage` restoration failed: {e}")

                if recording.state.session_storage:
                    try:
                        storage_json = base64.b64decode(recording.state.session_storage).decode()
                        storage_data = json.loads(storage_json)

                        restore_code = f"""
                            (function() {{
                                const data = {json.dumps(storage_data)};
                                Object.entries(data).forEach(([k, v]) => sessionStorage.setItem(k, v));
                                return {{ restored: Object.keys(data).length }};
                            }})()
                        """
                        result = client.execute(restore_code, timeout=3.0)
                        if verbose and result.get("ok"):
                            count = result.get("result", {}).get("restored", 0)
                            click.echo(format_system_message(f"✓ Restored {count} sessionStorage keys"))
                    except Exception as e:
                        from inspekt.app.cli.table import print_warning
                        print_warning(f"`sessionStorage` restoration failed: {e}")

            # Restore scroll position if state has scroll data
            if recording.state.scroll and (recording.state.scroll.x > 0 or recording.state.scroll.y > 0):
                scroll_x = recording.state.scroll.x
                scroll_y = recording.state.scroll.y
                if verbose:
                    click.echo(format_system_message(f"Restoring scroll position to ({scroll_x}, {scroll_y})..."))

                scroll_code = f"window.scrollTo({scroll_x}, {scroll_y})"
                client.execute(scroll_code, timeout=2.0)

        # Load scripts
        scripts_dir = Path(__file__).parent.parent.parent / "scripts"

        # Load replay script
        script_path = scripts_dir / "replay_step.js"
        try:
            with _builtin_open(script_path) as f:
                script_template = f.read()
        except FileNotFoundError:
            click.echo(f"Error: Script not found: {script_path}", err=True)
            sys.exit(1)

        # Load condition checking script
        condition_script_path = scripts_dir / "check_condition.js"
        try:
            with _builtin_open(condition_script_path) as f:
                condition_script_template = f.read()
        except FileNotFoundError:
            click.echo(f"Error: Script not found: {condition_script_path}", err=True)
            sys.exit(1)

        # Load download monitoring script for replay
        download_script_path = scripts_dir / "replay_download.js"
        try:
            with _builtin_open(download_script_path) as f:
                download_script_template = f.read()
        except FileNotFoundError:
            click.echo(f"Error: Script not found: {download_script_path}", err=True)
            sys.exit(1)

        # Inject visual feedback script if enabled (also needed for --lock)
        # We use "replay mode" which tells the extension to auto-inject the visual script
        # on every page load. This eliminates the need to poll and inject after navigation.
        replay_mode_enabled = False
        if visual or audio or lock:
            visual_script_path = scripts_dir / "replay_visual.js"
            try:
                with _builtin_open(visual_script_path) as f:
                    visual_script = f.read()

                # Inject shared dialog styles
                visual_script = visual_script.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)

                # Enable replay mode in the extension - this stores the script and
                # auto-injects it on every page load
                replay_mode_result = client.enable_replay_mode(visual_script, timeout=10.0)
                if replay_mode_result.get("ok"):
                    replay_mode_enabled = True
                    if verbose:
                        click.echo(format_system_message("replay mode enabled (auto-inject on navigation)"))
                else:
                    # Fallback: inject script directly (extension might not support replay mode)
                    if verbose:
                        click.echo(format_system_message("replay mode not available, using direct injection"))
                    inject_result = client.execute(visual_script, timeout=10.0)
                    if not inject_result.get("ok"):
                        click.echo(f"Warning: Could not inject visual script: {inject_result.get('error')}", err=True)
                    elif verbose:
                        click.echo(format_system_message("visual feedback script injected"))

                # Verify the visual object was created
                verify_result = client.execute("typeof window.__INSPEKT_VISUAL__", timeout=5.0)
                if verify_result.get("ok") and verify_result.get("result") == "object":
                    # Enable input lock if requested
                    # Uses event blocking to prevent user interference while preserving visual focus outlines
                    if lock:
                        client.execute("window.__INSPEKT_VISUAL__.inputLock.enable()", timeout=5.0)
                        if verbose:
                            click.echo(format_system_message("input locked"))
                    # Clear any previous stop request flag (from previous replay)
                    client.execute("window.__INSPEKT_VISUAL__.clearStopRequest()", timeout=1.0)
                    # Play start sound
                    if cli_audio:
                        # CLI audio: play directly from Python (no browser interaction needed)
                        cli_audio.play_start_playback()
                    elif use_browser_audio:
                        # Browser audio: requires user interaction to unlock (autoplay policy)
                        click.echo()
                        click.echo(
                            click.style("  Audio feedback enabled (browser mode). ", fg="cyan")
                            + "Click anywhere in your browser window to unlock audio."
                        )
                        click.echo(
                            click.style("  Press Enter", fg="cyan", bold=True)
                            + " to start playback..."
                        )
                        input()
                        # Resume audio context after user interaction
                        client.execute("window.__INSPEKT_VISUAL__.audio.ctx && window.__INSPEKT_VISUAL__.audio.ctx.resume()", timeout=5.0)
                        client.execute("window.__INSPEKT_VISUAL__.audio.playStartPlayback()", timeout=5.0)
                        time.sleep(0.5)  # Wait for start sound to complete
                else:
                    click.echo("Warning: Visual script injected but __INSPEKT_VISUAL__ not created", err=True)
                    if verbose:
                        click.echo(format_system_message(f"verify result: {verify_result}"))
            except FileNotFoundError:
                click.echo(f"Warning: Visual script not found: {visual_script_path}", err=True)

    # Print interactive mode message and step header (unless in progress bar mode)
    if not progress:
        if interactive:
            click.secho(
                "⚠ Interactive mode: press Enter to continue to the next step, Space to skip, or Escape to cancel. "
                "Make sure the browser window is active.",
                fg="yellow",
            )
            click.echo()

        click.echo(format_step_header())

    # Progress bar setup for --progress mode
    progress_bar = None
    if progress and not dry_run:
        progress_bar = click.progressbar(
            length=len(steps_to_run),
            label="Replaying",
            show_eta=True,
            show_percent=True,
            fill_char=click.style("█", fg="green"),
            empty_char=click.style("░", fg="bright_black"),
        )
        progress_bar.__enter__()

    # Check if there are any download steps that need monitoring
    has_download_steps = any(s.action == "download" for s in steps_to_run)
    download_monitoring_active = False
    download_session_id = None  # Store session ID for re-injection after navigation
    replay_downloads_dir = None
    replay_timestamp = None

    # Start download monitoring if there are download steps
    if has_download_steps and not dry_run:
        # Create replay downloads directory under the recording's files folder
        # Structure: {recording}_files/downloads/during-replay/{timestamp}/
        replay_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        recording_name = recording_path.stem
        replay_downloads_dir = (
            recording_path.parent
            / f"{recording_name}_files"
            / "downloads"
            / "during-replay"
            / replay_timestamp
        )
        replay_downloads_dir.mkdir(parents=True, exist_ok=True)

        # Start download monitoring
        download_session_id = f"replay-{int(time.time() * 1000)}"
        download_config = json.dumps({
            "action": "start",
            "sessionId": download_session_id
        })
        download_script = download_script_template.replace(
            "DOWNLOAD_CONFIG_PLACEHOLDER", download_config
        )
        start_result = client.execute(download_script, timeout=5.0)
        if start_result.get("ok"):
            download_monitoring_active = True
            if verbose:
                click.echo(format_system_message(f"download monitoring started, files will be saved to: {replay_downloads_dir}"))
        else:
            click.echo(f"Warning: Could not start download monitoring: {start_result.get('error')}", err=True)

    # Measure viewport height BEFORE any debugger attachment
    # This is needed to detect the automation banner height for video cropping
    pre_debugger_viewport_height = 0
    if video_recording_enabled and not dry_run and client:
        try:
            viewport_result = client.execute("({ height: window.innerHeight })", timeout=2.0)
            if viewport_result.get("ok") and viewport_result.get("result"):
                pre_debugger_viewport_height = viewport_result["result"].get("height", 0)
        except Exception:
            pass

    # Collect jsdialog steps for CDP interception
    # Store as list of (index, step) tuples so we can track which are remaining
    jsdialog_steps_with_index = [
        (i, s) for i, s in enumerate(steps_to_run) if s.action == "jsdialog"
    ]
    cdp_dialog_interception_enabled = False

    def build_cdp_dialog_queue(from_index: int = 0) -> list:
        """Build queue of dialog results for CDP interception (steps >= from_index)."""
        queue = []
        for step_idx, js_step in jsdialog_steps_with_index:
            if step_idx < from_index:
                continue  # Skip already-executed steps
            dialog_type = js_step.dialog_type or "alert"
            dialog_result = js_step.result
            # Include duration for replay timing (default 1500ms if not recorded)
            dialog_duration = js_step.duration or 1500
            queue.append({"type": dialog_type, "result": dialog_result, "duration": dialog_duration})
        return queue

    def build_cdp_enable_code(queue: list) -> str:
        """Build JS code to enable CDP dialog interception via extension bridge."""
        queue_json = json.dumps(queue)
        return f"""
(function() {{
    return new Promise((resolve) => {{
        const requestId = 'dialog-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

        const handler = (event) => {{
            if (event.data?.type === 'INSPEKT_DIALOG_INTERCEPTION_RESPONSE' &&
                event.data?.source === 'inspekt-extension' &&
                event.data?.requestId === requestId) {{
                window.removeEventListener('message', handler);
                resolve(event.data.response);
            }}
        }};

        window.addEventListener('message', handler);

        // Request CDP dialog interception from extension
        window.postMessage({{
            type: 'INSPEKT_ENABLE_DIALOG_INTERCEPTION',
            source: 'inspekt-page',
            requestId: requestId,
            queue: {queue_json}
        }}, '*');

        // Timeout after 5 seconds
        setTimeout(() => {{
            window.removeEventListener('message', handler);
            resolve({{ ok: false, error: 'Timeout waiting for extension response' }});
        }}, 5000);
    }});
}})()
"""

    def build_cdp_disable_code() -> str:
        """Build JS code to disable CDP dialog interception."""
        return """
(function() {
    return new Promise((resolve) => {
        const requestId = 'dialog-disable-' + Date.now();

        const handler = (event) => {
            if (event.data?.type === 'INSPEKT_DIALOG_INTERCEPTION_DISABLED' &&
                event.data?.source === 'inspekt-extension' &&
                event.data?.requestId === requestId) {
                window.removeEventListener('message', handler);
                resolve(event.data.response);
            }
        };

        window.addEventListener('message', handler);

        window.postMessage({
            type: 'INSPEKT_DISABLE_DIALOG_INTERCEPTION',
            source: 'inspekt-page',
            requestId: requestId
        }, '*');

        setTimeout(() => {
            window.removeEventListener('message', handler);
            resolve({ ok: true });  // Don't fail on timeout for disable
        }, 2000);
    });
})()
"""

    # Enable CDP dialog interception for replay (bullet-proof, intercepts at browser level)
    # This prevents native alert/confirm/prompt from blocking and shows synthetic overlays
    # ALWAYS enable when visual mode is on - pages may show dialogs even if not in recording
    if not dry_run and client and (visual or lock):
        try:
            queue = build_cdp_dialog_queue(from_index=0)
            enable_code = build_cdp_enable_code(queue)
            intercept_result = client.execute(enable_code, timeout=10.0)

            if intercept_result.get("ok"):
                inner_result = intercept_result.get("result", {})
                if inner_result.get("ok"):
                    cdp_dialog_interception_enabled = True
                    if verbose:
                        if queue:
                            click.echo(format_system_message(f"CDP dialog interception enabled ({len(queue)} dialog(s) queued)"))
                        else:
                            click.echo(format_system_message("CDP dialog interception enabled (no dialogs in recording)"))
                else:
                    # CDP failed (e.g., DevTools open) - JS fallback is enabled via visual script
                    if verbose:
                        error_msg = inner_result.get("error", "Unknown error")
                        click.echo(format_system_message(f"CDP dialog interception unavailable: {error_msg} (using JS fallback)"))
            else:
                # Communication failure - JS fallback is enabled via visual script
                if verbose:
                    click.echo(format_system_message(f"CDP dialog interception failed: {intercept_result.get('error')} (using JS fallback)"))
        except Exception as e:
            # Setup exception - JS fallback is enabled via visual script
            if verbose:
                click.echo(format_system_message(f"CDP dialog interception error: {e} (using JS fallback)"))

    # Start video recording if enabled (BEFORE first step to capture all frames)
    banner_crop_height = 0  # Height of automation banner to crop from video
    banner_compensation_succeeded = False  # Track if we successfully resized to compensate
    original_zoom_level = None  # Store original zoom to restore after video recording
    if video_recording_enabled and not dry_run and client:
        from inspekt.services.screencast import ScreencastCapture

        # ScreencastCapture auto-detects the correct port (8767 in VM, 8765 otherwise)
        screencast_capture = ScreencastCapture(
            fps=actual_fps,
            quality=actual_quality,
        )

        # Reset browser zoom to 100% for consistent video dimensions
        # Browser zoom affects how CDP screencast captures frames
        try:
            get_zoom_js = """
            (async () => {
                return new Promise((resolve) => {
                    const requestId = 'zoom-video-' + Date.now();
                    const handler = (event) => {
                        if (event.data?.type === 'INSPEKT_ZOOM_LEVEL_RESPONSE' &&
                            event.data?.requestId === requestId) {
                            window.removeEventListener('message', handler);
                            resolve(event.data.response?.zoomFactor || 1.0);
                        }
                    };
                    window.addEventListener('message', handler);
                    window.postMessage({
                        type: 'INSPEKT_GET_ZOOM_LEVEL',
                        source: 'inspekt-page',
                        requestId: requestId
                    }, '*');
                    setTimeout(() => resolve(1.0), 2000);
                });
            })()
            """
            zoom_result = client.execute(get_zoom_js, timeout=3.0)
            if zoom_result.get("ok"):
                original_zoom_level = float(zoom_result.get("result", 1.0))

                # Reset to 100% if zoom is different (>5% tolerance)
                if abs(original_zoom_level - 1.0) > 0.05:
                    set_zoom_js = """
                    (async () => {
                        return new Promise((resolve) => {
                            const requestId = 'reset-zoom-' + Date.now();
                            const handler = (event) => {
                                if (event.data?.type === 'INSPEKT_ZOOM_SET_RESPONSE' &&
                                    event.data?.requestId === requestId) {
                                    window.removeEventListener('message', handler);
                                    resolve(event.data.response);
                                }
                            };
                            window.addEventListener('message', handler);
                            window.postMessage({
                                type: 'INSPEKT_SET_ZOOM_LEVEL',
                                source: 'inspekt-page',
                                requestId: requestId,
                                zoomFactor: 1.0
                            }, '*');
                            setTimeout(() => resolve({ ok: false }), 2000);
                        });
                    })()
                    """
                    set_result = client.execute(set_zoom_js, timeout=3.0)
                    if set_result.get("ok") and set_result.get("result", {}).get("ok"):
                        click.echo(format_system_message(
                            f"Reset zoom to 100% for video (was {original_zoom_level:.0%})",
                            icon="video"
                        ))
                        time.sleep(0.2)  # Let browser settle after zoom change

                        # Re-measure viewport height after zoom reset (dimensions may have changed)
                        try:
                            height_result = client.execute("window.innerHeight", timeout=2.0)
                            if height_result.get("ok"):
                                pre_debugger_viewport_height = height_result.get("result", pre_debugger_viewport_height)
                        except Exception:
                            pass
        except Exception as e:
            if verbose:
                click.echo(format_system_message(f"Could not reset zoom: {e}", icon="video"))

        # Detect and compensate for automation banner BEFORE starting screencast
        # The banner appears when debugger is attached (e.g., for CDP dialog interception)
        # We measured pre_debugger_viewport_height before any debugger attachment
        # Skip banner compensation in fullscreen/kiosk mode (window cannot be expanded)
        if pre_debugger_viewport_height > 0 and recorded_viewport and not in_fullscreen_mode:
            try:
                # Measure current viewport (after debugger may have been attached for dialog interception)
                viewport_result = client.execute("({ height: window.innerHeight })", timeout=2.0)
                if viewport_result.get("ok") and viewport_result.get("result"):
                    current_height = viewport_result["result"].get("height", 0)

                    if current_height < pre_debugger_viewport_height:
                        # Banner detected - viewport shrank after debugger attached
                        banner_height = pre_debugger_viewport_height - current_height
                        target_height = recorded_viewport.height

                        # Expand window to restore target viewport height
                        expand_by = target_height - current_height
                        if expand_by > 0:
                            # Use AppleScript to directly expand window bounds
                            # (JS resizeTo is blocked by browsers for security)
                            import platform
                            resize_success = False
                            new_height = current_height

                            if platform.system() == "Darwin":
                                from inspekt.services.applescript_utils import AppleScriptExecutor
                                executor = AppleScriptExecutor()

                                # Iteratively expand until we reach target height
                                # This handles display scaling issues (Retina displays)
                                for attempt in range(5):
                                    remaining = target_height - new_height
                                    if remaining <= 2:  # Close enough
                                        break

                                    # Directly expand window height by the needed amount
                                    expand_script = f'''
tell application "Google Chrome"
    set frontWindow to front window
    set {{x1, y1, x2, y2}} to bounds of frontWindow
    set bounds of frontWindow to {{x1, y1, x2, y2 + {remaining}}}
end tell
'''
                                    as_result = executor.execute(expand_script, timeout=3.0)
                                    if not as_result.ok:
                                        break

                                    time.sleep(0.15)  # Let resize settle

                                    # Check new height
                                    verify_result = client.execute("window.innerHeight", timeout=2.0)
                                    new_height = verify_result.get("result", 0) if verify_result.get("ok") else 0

                                resize_success = new_height >= target_height - 2

                            if resize_success:
                                banner_compensation_succeeded = True  # Don't apply fallback crop
                                click.echo(format_system_message(
                                    f"Compensated for automation banner (viewport now: {new_height}px)",
                                    icon="video"
                                ))
                            else:
                                if verbose:
                                    click.echo(format_system_message(
                                        f"Resize: viewport is {new_height}px (target: {target_height}px)",
                                        icon="video"
                                    ))
                    else:
                        if verbose:
                            click.echo(format_system_message("No banner detected (viewport unchanged)", icon="video"))
            except Exception as e:
                click.echo(format_system_message(f"Could not compensate for banner: {e}", icon="video"))
        else:
            if verbose:
                if in_fullscreen_mode:
                    click.echo(format_system_message(
                        f"Skipping banner compensation (browser in {current_window_mode} mode)",
                        icon="video"
                    ))
                else:
                    click.echo(format_system_message(
                        f"Skipping banner check: pre_height={pre_debugger_viewport_height}, recorded={recorded_viewport is not None}",
                        icon="video"
                    ))

        # Start screencast immediately via postMessage to extension
        # This happens before the loop so first step frames are captured
        time.sleep(0.3)  # Brief stabilization

        screencast_js = f"""
(function() {{
    return new Promise((resolve) => {{
        const requestId = 'screencast-' + Date.now();

        const handler = (event) => {{
            if (event.data?.type === 'INSPEKT_SCREENCAST_STARTED' &&
                event.data?.source === 'inspekt-extension' &&
                event.data?.requestId === requestId) {{
                window.removeEventListener('message', handler);
                resolve(event.data.response);
            }}
        }};

        window.addEventListener('message', handler);

        window.postMessage({{
            type: 'INSPEKT_START_SCREENCAST',
            source: 'inspekt-page',
            requestId: requestId,
            settings: {{ fps: {actual_fps}, quality: {actual_quality}, preDebuggerHeight: {pre_debugger_viewport_height} }}
        }}, '*');

        // Timeout after 5 seconds
        setTimeout(() => {{
            window.removeEventListener('message', handler);
            resolve({{ ok: false, error: 'Timeout waiting for screencast start' }});
        }}, 5000);
    }});
}})()
"""
        try:
            sc_result = client.execute(screencast_js, timeout=10.0)
            if sc_result.get("ok") and sc_result.get("result", {}).get("ok"):
                # Screencast started - debugger is now attached and banner may have appeared
                # Check if banner appeared and try to compensate by expanding window
                sc_response = sc_result.get("result", {})
                reported_banner = sc_response.get("bannerHeight", 0)

                if reported_banner > 0 and not banner_compensation_succeeded and not in_fullscreen_mode:
                    # Banner appeared after debugger attached - try to expand window
                    target_height = recorded_viewport.height if recorded_viewport else 0

                    if target_height > 0:
                        import platform
                        if platform.system() == "Darwin":
                            from inspekt.services.applescript_utils import AppleScriptExecutor
                            executor = AppleScriptExecutor()

                            # Get current viewport height
                            current_h_result = client.execute("window.innerHeight", timeout=2.0)
                            current_height = current_h_result.get("result", 0) if current_h_result.get("ok") else 0

                            # Iteratively expand until we reach target height
                            for attempt in range(5):
                                remaining = target_height - current_height
                                if remaining <= 2:  # Close enough
                                    banner_compensation_succeeded = True
                                    click.echo(format_system_message(
                                        f"Compensated for automation banner (viewport now: {current_height}px)",
                                        icon="video"
                                    ))
                                    break

                                # Expand window height
                                expand_script = f'''
tell application "Google Chrome"
    set frontWindow to front window
    set {{x1, y1, x2, y2}} to bounds of frontWindow
    set bounds of frontWindow to {{x1, y1, x2, y2 + {remaining}}}
end tell
'''
                                as_result = executor.execute(expand_script, timeout=3.0)
                                if not as_result.ok:
                                    break

                                time.sleep(0.15)  # Let resize settle

                                # Check new height
                                verify_result = client.execute("window.innerHeight", timeout=2.0)
                                current_height = verify_result.get("result", 0) if verify_result.get("ok") else 0

                            # Brief stabilization after compensation
                            time.sleep(0.2)

                    # Only use cropping as last resort if expansion failed
                    if not banner_compensation_succeeded and banner_crop_height == 0:
                        banner_crop_height = reported_banner

                video_start_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
                click.echo(format_system_message(f"Recording video at {actual_fps} frames per second…", icon="video", elapsed_ms=video_start_elapsed))
                screencast_capture.set_capturing(True)  # Start collecting frames AFTER compensation

                # Start frame forcer to ensure consistent video frame rate
                # CDP screencast only generates frames when compositor renders;
                # this forces continuous repaints for static pages like Tab navigation
                try:
                    client.execute("window.__INSPEKT_REPLAY_VISUAL__?.frameForcer?.start()", timeout=2.0)
                except Exception:
                    pass  # Frame forcer is optional enhancement

                # Start audio cue recording if --include-effects is enabled
                if include_effects:
                    try:
                        # Start audio recording in JavaScript (captures timestamps when sounds play)
                        client.execute("window.__INSPEKT_REPLAY_VISUAL__.audio.startRecordingForVideo()", timeout=2.0)
                        # Also notify bridge server to start collecting cues
                        import requests
                        requests.post("http://127.0.0.1:8765/audio/start", timeout=2.0)
                        if verbose:
                            click.echo(format_system_message("Recording audio cues for video…", icon="audio"))
                    except Exception as e:
                        if verbose:
                            click.echo(format_system_message(f"Could not start audio cue recording: {e}", icon="warning"))
            else:
                error_msg = sc_result.get("result", {}).get("error", sc_result.get("error", "Unknown error"))
                from inspekt.app.cli.table import print_warning
                print_warning(f"Could not start video recording: {error_msg}")
                # Send stop command to clean up extension state even on failure
                try:
                    client.execute("window.postMessage({type: 'INSPEKT_STOP_SCREENCAST', source: 'inspekt-page'}, '*')", timeout=2.0)
                except Exception:
                    pass
                video_recording_enabled = False
                screencast_capture = None
        except Exception as e:
            from inspekt.app.cli.table import print_warning
            print_warning(f"Video recording error: {e}")
            # Send stop command to clean up extension state even on failure
            try:
                client.execute("window.postMessage({type: 'INSPEKT_STOP_SCREENCAST', source: 'inspekt-page'}, '*')", timeout=2.0)
            except Exception:
                pass
            video_recording_enabled = False
            screencast_capture = None

    # Execute steps
    previous_timestamp = steps_to_run[0].timestamp if steps_to_run else 0
    last_step_navigated = False  # Track if previous step caused navigation
    page_load_wait_ms = 0  # Time spent waiting for page load (subtract from next delay)
    replay_cancelled = False  # Track if user cancelled in interactive mode

    for i, step in enumerate(steps_to_run):
        actual_index = start_idx + i
        step_dict = step.model_dump(exclude_none=True)

        # Load external file content for upload steps
        if step.action == "upload":
            load_external_file_content(step_dict, recording_path.parent)

        step_timestamp = step.timestamp or 0  # Get timestamp from step for display

        # Check if Ctrl+C was pressed in browser (non-interactive mode)
        if not dry_run and client and (visual or lock):
            try:
                stop_check = client.execute("window.__INSPEKT_VISUAL__.isStopRequested()", timeout=1.0)
                if stop_check.get("ok") and stop_check.get("result"):
                    click.echo()
                    click.secho("Replay stopped by user (Ctrl+C in browser).", fg="yellow")
                    replay_cancelled = True
                    break
            except Exception:
                pass  # If check fails, continue with replay

        # Real-time delay: wait based on timestamp difference from previous step
        # Subtract any time already spent waiting for page load
        # Note: CLI audio plays asynchronously, so it doesn't affect timing
        if not dry_run and i > 0 and speed != float("inf"):
            timestamp_diff_ms = step_timestamp - previous_timestamp
            # Subtract time we already waited for page load
            adjusted_diff_ms = timestamp_diff_ms - page_load_wait_ms
            if adjusted_diff_ms > 0:
                delay_sec = (adjusted_diff_ms / 1000.0) / speed
                # Cap maximum delay to avoid excessively long waits (e.g., 30 seconds max)
                delay_sec = min(delay_sec, 30.0)
                if delay_sec > 0.05:  # Only sleep if delay is meaningful (>50ms)
                    time.sleep(delay_sec)
        page_load_wait_ms = 0  # Reset after applying
        previous_timestamp = step_timestamp

        # Check if this action type should be skipped
        if step.action in skip_actions:
            if not progress:
                summary = format_step_for_display(step_dict, actual_index + 1, step_timestamp, reserve_suffix_width=5)
                click.echo(summary, nl=False)
                click.echo(format_status("SKIP"))
            result.add_skip(actual_index, step_dict, f"Skipped by --skip {step.action}")
            if verbose and not progress:
                click.echo(format_system_message(f"skipped: {step.action} in skip list"))
            continue

        # Skip navigate steps that follow a click that already caused navigation
        # The click already triggered the navigation, so this step is redundant
        if step.action == "navigate" and last_step_navigated and i > 0:
            if not progress:
                summary = format_step_for_display(step_dict, actual_index + 1, step_timestamp, reserve_suffix_width=5)
                click.echo(summary, nl=False)
                click.echo(format_status("OK"))
            result.add_success(actual_index, step_dict)  # Count as success since navigation happened
            if verbose and not progress:
                click.echo(format_system_message("navigation already occurred from previous click"))
            last_step_navigated = False  # Reset the flag
            continue

        # Reset navigation flag at start of each step (will be set if this step navigates)
        last_step_navigated = False

        # Display step (skip in progress mode)
        summary = format_step_for_display(step_dict, actual_index + 1, step_timestamp, reserve_suffix_width=5) if not progress else ""

        if dry_run:
            click.echo(summary)
            if step.mode and step.mode != "continue":
                click.echo(format_system_message(f"mode: {step.mode}"))
            if step.skip_if:
                skip_dict = step.skip_if.model_dump(exclude_none=True)
                click.echo(format_system_message(f"skip_if: {skip_dict}"))
            if step.wait_for:
                wait_dict = step.wait_for.model_dump(exclude_none=True)
                click.echo(format_system_message(f"wait_for: {wait_dict}"))
            if step.expect:
                expect_dict = step.expect.model_dump(exclude_none=True)
                click.echo(format_system_message(f"expect: {expect_dict}"))
            continue

        # Check step mode (skip, pause, continue)
        step_mode = step.mode or "continue"

        if step_mode == "skip":
            # Unconditional skip - mode: skip takes precedence over skip_if
            skipped_summary = format_skipped_step_for_display(step_dict, actual_index + 1, step_timestamp)
            if not progress:
                click.echo(skipped_summary)
            result.add_skip(actual_index, step_dict, "mode: skip")
            continue

        if step_mode == "pause" and not interactive:
            # Pause mode - wait for user to press Enter (but not in interactive mode)
            # Show the paused step indicator
            if not progress:
                paused_summary = format_paused_step_for_display(step_dict, actual_index + 1, step_timestamp)
                click.echo(paused_summary)

            # Display pause prompt and wait for Enter
            click.echo()
            click.secho("⏸ Paused.", fg="yellow", bold=True, nl=False)
            click.echo(" Press Enter to continue…", nl=False)

            # Play attention sound via CLI audio (if enabled)
            if visual_script:
                try:
                    client.execute("window.__INSPEKT_VISUAL__.audio.playPause()", timeout=2.0)
                except Exception:
                    pass  # Ignore audio errors

            input()  # Wait for Enter
            click.echo()  # Newline after Enter

        # Check skip_if condition before executing
        if step.skip_if and condition_script_template:
            skip_dict = step.skip_if.model_dump(exclude_none=True)
            skip_result = check_condition(client, skip_dict, condition_script_template)

            if skip_result.get("met"):
                if not progress:
                    click.echo(summary, nl=False)
                    click.echo(format_status("SKIP"))
                result.add_skip(actual_index, step_dict, f"skip_if: {skip_result.get('reason', 'condition met')}")
                if verbose and not progress:
                    click.echo(format_system_message(f"skipped: {skip_result.get('reason', '')}"))
                continue

        # Check wait_for condition before executing
        if step.wait_for and condition_script_template:
            wait_dict = step.wait_for.model_dump(exclude_none=True)
            timeout_ms = step.wait_for.timeout or 5000  # Default 5 seconds

            if verbose and not progress:
                click.echo(format_system_message(f"waiting for condition (timeout: {timeout_ms}ms)..."))

            wait_result = wait_for_condition(
                client,
                wait_dict,
                condition_script_template,
                timeout_ms=timeout_ms,
            )

            if wait_result.get("timed_out"):
                if not progress:
                    click.echo(summary, nl=False)
                    click.echo(format_status("FAIL"))
                result.add_failure(
                    actual_index,
                    step_dict,
                    f"wait_for timed out after {timeout_ms}ms: {wait_result.get('reason', '')}",
                )
                if verbose and not progress:
                    click.echo(format_system_message(f"timeout: {wait_result.get('reason', '')}"))
                continue
            elif verbose and not progress:
                click.echo(format_system_message(f"condition met: {wait_result.get('reason', '')}"))

        # Interactive mode: show overlay and wait for user input
        if interactive and not dry_run:
            # Pause video capture during interactive wait to avoid dead time in video
            if screencast_capture and screencast_capture.is_capturing:
                screencast_capture.set_capturing(False)

            # Build the interactive prompt step
            previous_step_dict = None
            if i > 0:
                previous_step_dict = steps_to_run[i - 1].model_dump(exclude_none=True)

            interactive_step = {
                "action": "interactive_prompt",
                "currentStep": step_dict,
                "previousStep": previous_step_dict,
                "stepNum": actual_index + 1,
                "totalSteps": total_steps,
            }

            interactive_json = json.dumps(interactive_step)
            interactive_code = script_template.replace("STEP_DATA_PLACEHOLDER", interactive_json)

            try:
                interactive_result = client.execute(interactive_code, timeout=300.0)  # Long timeout for user input

                if verbose:
                    result_data = interactive_result.get("result", {})
                    choice = result_data.get("choice", "unknown")
                    warning = result_data.get("warning")
                    if warning:
                        click.echo(format_system_message(f"Interactive: choice={choice}, warning={warning}"))
                    else:
                        click.echo(format_system_message(f"Interactive: choice={choice}"))

                if interactive_result.get("ok"):
                    response = interactive_result.get("result", {})
                    choice = response.get("choice", "next")

                    if choice == "skip":
                        # User pressed Space - skip this step
                        click.echo(summary, nl=False)
                        click.echo(format_status("SKIP"))
                        result.add_skip(actual_index, step_dict, "Skipped by user (interactive mode)")
                        if verbose:
                            click.echo(format_system_message("skipped by user"))
                        # Resume video capture before continuing
                        if screencast_capture:
                            screencast_capture.set_capturing(True)
                        continue
                    elif choice == "cancel":
                        # User pressed Escape - cancel the entire replay
                        click.echo(summary, nl=False)
                        click.echo(click.style(" CANCELLED", fg="yellow"))
                        click.echo()
                        click.secho("Replay cancelled by user.", fg="yellow")
                        replay_cancelled = True
                        # Resume video capture before breaking (for final frame capture)
                        if screencast_capture:
                            screencast_capture.set_capturing(True)
                        break
                    # choice == "next" - continue to execute the step
                else:
                    if verbose:
                        click.echo(format_system_message(f"Interactive prompt failed: {interactive_result.get('error')}"))
            except Exception as e:
                if verbose:
                    click.echo(format_system_message(f"Interactive prompt error: {e}"))

            # Resume video capture after interactive prompt (for "next" choice or errors)
            if screencast_capture:
                screencast_capture.set_capturing(True)

        if replay_cancelled:
            break

        if not progress:
            click.echo(summary, nl=False)

        # Play action sound via CLI audio (if enabled)
        if cli_audio and step.action:
            cli_audio.play_for_action(step.action)

        # Handle inspekt commands separately
        if step.action == "inspekt" and step.command:
            cmd_result = run_inspekt_command(step.command)

            if cmd_result.get("ok"):
                # Check expectations
                expect_dict = step.expect.model_dump(exclude_none=True) if step.expect else {}
                assertion_failures = check_inspekt_expectations(step.command, expect_dict, cmd_result)

                if assertion_failures:
                    if not progress:
                        click.echo(format_status("FAIL"))
                    result.add_failure(actual_index, step_dict, "Assertion failed", assertion_failures)
                    if verbose and not progress:
                        for failure in assertion_failures:
                            click.echo(format_system_message(f"⚠ {failure}"))
                else:
                    if not progress:
                        click.echo(format_status("OK"))
                    result.add_success(actual_index, step_dict)
            else:
                if not progress:
                    click.echo(format_status("FAIL"))
                result.add_failure(actual_index, step_dict, cmd_result.get("error", "Command failed"))
                if verbose and not progress:
                    click.echo(format_system_message(f"Error: {cmd_result.get('error', 'Unknown')}"))

        # Handle download steps - these are markers for downloads triggered by previous actions
        # Downloads happen as side effects of clicks/keypresses, so we don't need to wait
        elif step.action == "download" and step.download:
            download_info = step.download.model_dump() if hasattr(step.download, "model_dump") else step.download
            downloaded_file_path = None

            # Get expectations
            expect_dict = step.expect.model_dump(exclude_none=True) if step.expect else {}

            # Check assertions (on the new file if captured, otherwise skip file-based assertions)
            assertion_failures = check_download_assertions(
                download_info,
                expect_dict,
                downloaded_file_path,
            )

            if assertion_failures:
                if not progress:
                    click.echo(format_status("FAIL"))
                result.add_failure(actual_index, step_dict, "Download assertion failed", assertion_failures)
                if verbose and not progress:
                    for failure in assertion_failures:
                        click.echo(format_system_message(f"⚠ {failure}"))
            else:
                if not progress:
                    click.echo(format_status("OK"))
                result.add_success(actual_index, step_dict)

        # Handle type actions with human-like typing
        elif step.action == "type" and step.value:
            target = step.target
            selector = target.selector if target else None

            if not selector:
                if not progress:
                    click.echo(format_status("FAIL"))
                result.add_failure(actual_index, step_dict, "No selector for type action")
            else:
                # Use fallback selectors if primary fails
                selectors_to_try = [selector]
                if target and target.fallback_selectors:
                    selectors_to_try.extend(target.fallback_selectors)

                typing_success = False
                used_selector = None

                for sel in selectors_to_try:
                    type_result = send_text_with_typing(client, step.value, sel, clear=True)
                    if type_result.get("ok"):
                        typing_success = True
                        used_selector = sel
                        break

                if typing_success:
                    if not progress:
                        click.echo(format_status("OK"))
                    result.add_success(actual_index, step_dict)
                    if verbose and not progress and used_selector != selector:
                        click.echo(format_system_message(f"used fallback: {used_selector}"))
                else:
                    if not progress:
                        click.echo(format_status("FAIL"))
                    result.add_failure(actual_index, step_dict, type_result.get("error", "Typing failed"))
                    if verbose and not progress:
                        click.echo(format_system_message(f"Error: {type_result.get('error', 'Unknown')}"))

        else:
            # Execute via JavaScript (for click, hover, keypress, navigate)
            # Add flags to step data
            step_data = step_dict.copy()
            if skip_tests:
                step_data["skipTests"] = True
            if interactive:
                step_data["isInteractive"] = True
            step_json = json.dumps(step_data)
            code = script_template.replace("STEP_DATA_PLACEHOLDER", step_json)

            # Detect actions that might cause navigation and use shorter timeout
            # Navigation causes the page to unload before response can be sent
            is_click_action = step.action in ("click", "activate")
            is_navigate_action = step.action == "navigate"
            is_enter_keypress = step.action == "keypress" and step.key and step.key.lower() == "enter"
            target = step.target
            action_timeout = 30.0
            might_navigate = False

            # Navigate action always navigates (if URL differs from current)
            if is_navigate_action:
                might_navigate = True
                action_timeout = 3.0

            # Enter keypress on a link navigates
            elif is_enter_keypress and target:
                tag = target.tag or ""
                selector = target.selector or ""
                if tag.lower() == "a" or " > a" in selector or selector.endswith(" a"):
                    might_navigate = True
                    action_timeout = 3.0

            # Click on links/buttons might navigate
            elif is_click_action and target:
                # Check if this might be a navigation link
                # Look for clues in the selector or accessible name
                selector = target.selector or ""
                tag = target.tag or ""
                accessible_name = target.accessible_name or ""

                might_navigate = (
                    tag.lower() == "a" or
                    "href" in selector.lower() or
                    " > a" in selector or
                    selector.endswith(" a") or
                    "button" in tag.lower() or
                    # Common navigation patterns
                    any(x in accessible_name.lower() for x in ["read more", "meer lezen", "lees meer", "open", "go to", "view"])
                )

                if might_navigate:
                    action_timeout = 3.0

            try:
                # Inner try to catch navigation timeouts specifically
                try:
                    exec_result = client.execute(code, timeout=action_timeout)
                    navigation_timeout = False
                except Exception as nav_exc:
                    # Check if this is a timeout on an action that might navigate
                    if might_navigate and "timeout" in str(nav_exc).lower():
                        # Navigation causes page unload before response can be sent
                        # Treat timeout as successful navigation
                        navigation_timeout = True
                        exec_result = {"ok": True, "result": {"ok": True, "navigated": is_navigate_action, "mayNavigate": not is_navigate_action}}
                        if verbose:
                            click.echo(format_system_message("Response lost (navigation in progress)"))
                    else:
                        # Re-raise other exceptions
                        raise

                if exec_result.get("ok"):
                    response = exec_result.get("result", {})

                    if response.get("ok"):
                        # Action succeeded - show OK for the step
                        # For keypress actions, show (CDP) suffix if real key dispatch was used
                        status_suffix = ""
                        if step.action == "keypress" and response.get("method") == "cdp":
                            status_suffix = "(CDP)"
                        if not progress:
                            click.echo(format_status("OK", suffix=status_suffix))

                        # Check for assertion failures (separate from action success)
                        assertion_failures = response.get("failures", [])

                        if assertion_failures or response.get("assertionsFailed"):
                            # Action succeeded but assertion failed
                            result.add_failure(actual_index, step_dict, "Assertion failed", assertion_failures)
                            # Show assertion message with failure indicator
                            if step.expect:
                                assertion_msg = step.expect.message or _generate_assertion_description(step.expect)
                                if assertion_msg:
                                    click.echo(format_assertion_result(assertion_msg, passed=False))
                            if verbose:
                                for failure in assertion_failures:
                                    click.echo(format_system_message(f"⚠ {failure}"))
                        else:
                            result.add_success(actual_index, step_dict)
                            # Show assertion message if present (always, not just verbose)
                            # But only if assertions were actually evaluated (not skipped)
                            if step.expect and not skip_tests:
                                assertion_msg = step.expect.message or _generate_assertion_description(step.expect)
                                if assertion_msg:
                                    click.echo(format_assertion_result(assertion_msg, passed=True))

                            # Show focus fallback note if CSS injection didn't work (Tab navigation)
                            if response.get("focusNote") and not progress:
                                click.echo(format_system_message(response.get("focusNote"), icon="info"))

                            if verbose and response.get("usedSelector"):
                                used = response["usedSelector"]
                                original = step_dict.get("target", {}).get("selector", "")
                                if used != original:
                                    click.echo(format_system_message(f"used fallback: {used}"))

                        # Handle navigation - wait for reconnection and re-inject visual script
                        # Both explicit navigation and link clicks that might navigate
                        navigated = response.get("navigated")
                        may_navigate = response.get("mayNavigate")

                        if navigated or may_navigate:
                            if verbose:
                                if navigated:
                                    click.echo(format_system_message("Waiting for page to load..."))
                                elif may_navigate:
                                    click.echo(format_system_message("Link clicked, checking for navigation..."))

                            # Wait for the page to be fully loaded (document.readyState === 'complete')
                            # Use shorter timeout for mayNavigate since it might not actually navigate
                            if interactive:
                                # Interactive mode: shorter timeout, visual script wait handles reconnection
                                timeout = 8.0 if navigated else 3.0
                            else:
                                timeout = 15.0 if navigated else 5.0
                            page_ready = wait_for_page_ready(
                                client,
                                timeout_sec=timeout,
                                poll_interval_sec=0.3,
                                verbose=verbose,
                            )

                            if not page_ready.get("success") and navigated:
                                if verbose:
                                    click.echo(format_system_message("Warning: Page load incomplete"))
                                # Continue anyway - next step execution will fail if truly problematic

                            # Re-inject visual script after navigation (it's lost on page change)
                            if (visual or audio or lock):
                                visual_ready = wait_for_visual_script_ready(
                                    client,
                                    visual_script,
                                    timeout_sec=5.0,
                                    poll_interval_sec=0.05,
                                    replay_mode=replay_mode_enabled,
                                )

                                if visual_ready.get("success"):
                                    # Re-enable input lock
                                    if lock:
                                        try:
                                            client.execute("window.__INSPEKT_VISUAL__.inputLock.enable()", timeout=5.0)
                                        except Exception:
                                            pass
                                    # Re-initialize audio context after page navigation (browser audio only)
                                    if use_browser_audio:
                                        try:
                                            client.execute("window.__INSPEKT_VISUAL__.audio.init()", timeout=5.0)
                                            if navigated:
                                                # Play navigate sound to indicate page transition
                                                client.execute("window.__INSPEKT_VISUAL__.audio.playNavigate()", timeout=5.0)
                                        except Exception:
                                            pass
                                    # Note: CDP dialog interception persists across navigations
                                    # (it's attached at the browser level via chrome.debugger)
                                elif verbose:
                                    click.echo(format_system_message("Warning: visual script not ready after navigation"))

                            # Re-inject download monitoring after navigation (it's lost on page change)
                            if download_monitoring_active and download_session_id:
                                download_config = json.dumps({
                                    "action": "start",
                                    "sessionId": download_session_id
                                })
                                download_script = download_script_template.replace(
                                    "DOWNLOAD_CONFIG_PLACEHOLDER", download_config
                                )
                                reinject_result = client.execute(download_script, timeout=5.0)
                                if reinject_result.get("ok"):
                                    if verbose:
                                        click.echo(format_system_message("download monitoring re-injected after navigation"))
                                else:
                                    if verbose:
                                        click.echo(format_system_message(f"Warning: could not re-inject download monitoring: {reinject_result.get('error')}"))

                            # Mark that this step caused navigation
                            # Next navigate step can be skipped since navigation already happened
                            last_step_navigated = True
                            # Track how long we waited for page load (subtract from next step's delay)
                            page_load_wait_ms = page_ready.get("elapsed_ms", 0)

                    elif response.get("skipped"):
                        click.echo(format_status("SKIP"))
                        result.add_skip(actual_index, step_dict, response.get("message", "Skipped"))
                        if verbose:
                            click.echo(format_system_message(response.get("message", "")))

                    else:
                        err_msg = response.get("error", "Unknown error")
                        click.echo(format_status("FAIL"))
                        result.add_failure(actual_index, step_dict, err_msg)
                        if verbose:
                            click.echo(format_system_message(f"Error: {err_msg}"))

                else:
                    err_msg = exec_result.get("error", "Execution failed")
                    click.echo(format_status("FAIL"))
                    result.add_failure(actual_index, step_dict, err_msg)
                    if verbose:
                        click.echo(format_system_message(f"Error: {err_msg}"))

            except Exception as e:
                click.echo(format_status("FAIL"))
                result.add_failure(actual_index, step_dict, str(e))
                if verbose:
                    click.echo(format_system_message(f"Exception: {e}"))

        # Pause on failure if requested
        if pause_on_fail and result.failed_steps > 0:
            # Check if this step was the most recent failure
            if result.failures and result.failures[-1]["step"] == actual_index + 1:
                click.echo()
                click.secho("    Paused on failure. Press Enter to continue, 'q' to quit...", fg="yellow")
                user_input = click.getchar()
                if user_input.lower() == 'q':
                    click.echo("\n    Replay aborted by user.")
                    break

        # Stop on first error if requested
        if stop_on_error and result.failed_steps > 0:
            if result.failures and result.failures[-1]["step"] == actual_index + 1:
                click.echo()
                click.secho("Stopped on first error (--stop-on-error).", fg="yellow")
                replay_cancelled = True
                break

        # Collect pending video frames periodically to prevent buffer overflow
        # The bridge server has a 10,000 frame buffer limit - long replays could exceed this
        if screencast_capture and screencast_capture.is_capturing:
            frames_collected = screencast_capture.collect_pending()
            if verbose and frames_collected > 0:
                click.echo(format_system_message(f"collected {frames_collected} video frames"))

            # Check if recording was interrupted (e.g., user opened DevTools)
            interrupt_info = screencast_capture.check_interrupted()
            if interrupt_info:
                reason = interrupt_info.get("reason", "unknown")
                # "tab closed" often happens during cross-origin navigation (Chrome site isolation)
                # This is expected and doesn't prevent video capture - suppress misleading warning
                if reason != "tab closed":
                    click.echo()
                    from inspekt.app.cli.table import print_warning
                    print_warning(f"Video recording interrupted: {reason}. Video will be saved with frames captured so far.")
                screencast_capture.set_capturing(False)  # Mark as no longer capturing

        # Additional fixed delay between steps (on top of real-time timing)
        # Only applies if --step-delay is explicitly set to a non-zero value
        if not dry_run and step_delay > 0 and i < len(steps_to_run) - 1:
            delay = step_delay / 1000.0
            time.sleep(delay)

        # Update progress bar after each step
        if progress_bar:
            progress_bar.update(1)

    # Close progress bar
    if progress_bar:
        progress_bar.__exit__(None, None, None)

    # Stop download monitoring if it was active
    if download_monitoring_active:
        try:
            download_config = json.dumps({"action": "stop"})
            stop_script = download_script_template.replace(
                "DOWNLOAD_CONFIG_PLACEHOLDER", download_config
            )
            stop_result = client.execute(stop_script, timeout=5.0)
            if verbose and stop_result.get("ok"):
                stats = stop_result.get("result", {}).get("stats", {})
                click.echo(format_system_message(f"download monitoring stopped (captured: {stats.get('completed', 0)})"))
        except Exception as e:
            if verbose:
                click.echo(format_system_message(f"could not stop download monitoring: {e}"))

    result.end_time = datetime.now()

    # Stop video recording and encode
    video_saved_path = None
    if video_recording_enabled and screencast_capture:
        try:
            # Stop frame forcer before stopping capture
            try:
                client.execute("window.__INSPEKT_REPLAY_VISUAL__?.frameForcer?.stop()", timeout=2.0)
            except Exception:
                pass  # Frame forcer cleanup is optional

            # Stop capture and get frames
            stop_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
            click.echo(format_system_message("Stopping video capture…", icon="video", elapsed_ms=stop_elapsed))
            frames = screencast_capture.stop()

            if frames:
                # Calculate actual FPS from frame timestamps for correct playback speed
                # frames is list of (timestamp, bytes) tuples
                if len(frames) >= 2:
                    first_ts = frames[0][0]
                    last_ts = frames[-1][0]
                    actual_duration = last_ts - first_ts
                    if actual_duration > 0:
                        real_fps = len(frames) / actual_duration
                        # Clamp to reasonable range (5-60 FPS)
                        real_fps = max(5, min(60, real_fps))
                    else:
                        real_fps = actual_fps
                else:
                    real_fps = actual_fps
                    actual_duration = len(frames) / actual_fps

                encode_start_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
                click.echo(format_system_message(f"Encoding {len(frames)} frames to video…", icon="video", elapsed_ms=encode_start_elapsed))

                # Encode to video
                from inspekt.services.video_encoder import encode_replay_video

                # Determine format from extension
                output_format = resolved_video_path.suffix.lstrip(".").lower()
                if output_format not in ("mp4", "webm"):
                    output_format = "mp4"

                encode_start_time = time.time()
                encode_result = encode_replay_video(
                    frames=frames,
                    output_path=str(resolved_video_path),
                    fps=int(round(real_fps)),  # Use calculated FPS for correct playback
                    format=output_format,
                    progress_callback=None,  # No progress output
                    crop_top=banner_crop_height,  # Crop automation banner from top
                )
                encode_duration = time.time() - encode_start_time

                if encode_result.get("ok"):
                    video_saved_path = resolved_video_path
                    file_size = resolved_video_path.stat().st_size

                    # Format file size appropriately (KB for small files, MB for larger)
                    if file_size < 1024 * 1024:  # Less than 1 MB
                        file_size_str = f"{file_size / 1024:.1f} KB"
                    else:
                        file_size_str = f"{file_size / (1024 * 1024):.1f} MB"

                    # Show encoding done message
                    encode_done_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
                    click.echo(format_system_message(f"Encoding done (took {encode_duration:.1f}s)", icon="video", elapsed_ms=encode_done_elapsed))

                    # Create clickable filename using OSC 8
                    file_uri = resolved_video_path.as_uri()
                    clickable_name = f"\033]8;;{file_uri}\033\\{resolved_video_path.name}\033]8;;\033\\"

                    # Show video saved message
                    saved_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
                    click.echo(format_system_message(f"Video saved: {clickable_name} ({file_size_str})", icon="video", elapsed_ms=saved_elapsed, truncate=False))

                    # Merge audio effects if --include-effects was used
                    if include_effects:
                        try:
                            import requests
                            import tempfile

                            # Stop audio recording in JavaScript
                            client.execute("window.__INSPEKT_REPLAY_VISUAL__.audio.stopRecordingForVideo()", timeout=2.0)

                            # Get audio cues from bridge server
                            cues_response = requests.get("http://127.0.0.1:8765/audio/cues", timeout=5.0)
                            cues_data = cues_response.json()
                            cues = cues_data.get("cues", [])

                            if cues:
                                # Generate audio track
                                audio_start_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
                                click.echo(format_system_message(f"Generating audio track ({len(cues)} effects)…", icon="audio", elapsed_ms=audio_start_elapsed))

                                # Get video duration from probe
                                temp_video_info = probe_video(resolved_video_path)
                                video_duration_ms = int((temp_video_info.get("duration", 0) if temp_video_info else 0) * 1000)

                                if video_duration_ms > 0:
                                    # Generate audio track using CLIAudio
                                    audio_bytes = cli_audio.generate_audio_track(cues, video_duration_ms)

                                    # Save to temp file
                                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_audio:
                                        temp_audio.write(audio_bytes)
                                        temp_audio_path = temp_audio.name

                                    # Merge audio with video
                                    temp_video_path = str(resolved_video_path) + ".temp.mp4"
                                    import shutil
                                    shutil.move(str(resolved_video_path), temp_video_path)

                                    merge_result = merge_audio_video(
                                        temp_video_path,
                                        temp_audio_path,
                                        str(resolved_video_path)
                                    )

                                    # Cleanup temp files
                                    try:
                                        Path(temp_video_path).unlink(missing_ok=True)
                                        Path(temp_audio_path).unlink(missing_ok=True)
                                    except Exception:
                                        pass

                                    if merge_result.get("ok"):
                                        audio_done_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
                                        click.echo(format_system_message(f"Added {len(cues)} audio effects to video", icon="audio", elapsed_ms=audio_done_elapsed))

                                        # Update file size display
                                        new_file_size = resolved_video_path.stat().st_size
                                        if new_file_size < 1024 * 1024:
                                            file_size_str = f"{new_file_size / 1024:.1f} KB"
                                        else:
                                            file_size_str = f"{new_file_size / (1024 * 1024):.1f} MB"
                                    else:
                                        if verbose:
                                            click.echo(format_system_message(f"Could not merge audio: {merge_result.get('error')}", icon="warning"))
                            elif verbose:
                                click.echo(format_system_message("No audio effects recorded", icon="info"))
                        except Exception as e:
                            if verbose:
                                click.echo(format_system_message(f"Audio merge error: {e}", icon="warning"))

                    # Probe video file for sanity check
                    video_info = probe_video(resolved_video_path)
                    if video_info:
                        # Format duration as mm:ss or just seconds for short videos
                        duration_secs = video_info.get("duration", 0)
                        if duration_secs >= 60:
                            mins = int(duration_secs // 60)
                            secs = int(duration_secs % 60)
                            duration_str = f"{mins}:{secs:02d}"
                        else:
                            duration_str = f"{duration_secs:.1f}s"

                        # Build info string with dimensions, duration, fps, and codec
                        width = video_info.get("width", 0)
                        height = video_info.get("height", 0)
                        fps = video_info.get("fps", 0)
                        codec = video_info.get("codec", "unknown")

                        info_parts = []
                        if width and height:
                            info_parts.append(f"{width}×{height}")
                        if duration_secs > 0:
                            info_parts.append(duration_str)
                        if fps > 0:
                            info_parts.append(f"{fps:.0f} fps")
                        if codec and codec != "unknown":
                            info_parts.append(codec)

                        if info_parts:
                            info_str = " · ".join(info_parts)
                            probe_elapsed = int((datetime.now() - result.start_time).total_seconds() * 1000)
                            click.echo(format_system_message(f"Video verified: {info_str}", icon="video", elapsed_ms=probe_elapsed))

                    # Open video file if --open flag was set
                    if open_after:
                        open_or_download(resolved_video_path)
                else:
                    from inspekt.app.cli.table import print_warning
                    print_warning(f"Video encoding failed: {encode_result.get('error')}")
            else:
                from inspekt.app.cli.table import print_warning
                print_warning("No frames captured for video")
        except Exception as e:
            from inspekt.app.cli.table import print_warning
            print_warning(f"Video encoding error: {e}")

        # Restore original zoom level if we changed it
        if original_zoom_level and abs(original_zoom_level - 1.0) > 0.05 and client:
            try:
                restore_zoom_js = f"""
                (async () => {{
                    return new Promise((resolve) => {{
                        const requestId = 'restore-zoom-' + Date.now();
                        const handler = (event) => {{
                            if (event.data?.type === 'INSPEKT_ZOOM_SET_RESPONSE' &&
                                event.data?.requestId === requestId) {{
                                window.removeEventListener('message', handler);
                                resolve(event.data.response);
                            }}
                        }};
                        window.addEventListener('message', handler);
                        window.postMessage({{
                            type: 'INSPEKT_SET_ZOOM_LEVEL',
                            source: 'inspekt-page',
                            requestId: requestId,
                            zoomFactor: {original_zoom_level}
                        }}, '*');
                        setTimeout(() => resolve({{ ok: false }}), 2000);
                    }});
                }})()
                """
                restore_result = client.execute(restore_zoom_js, timeout=3.0)
                if restore_result.get("ok") and restore_result.get("result", {}).get("ok"):
                    if verbose:
                        click.echo(format_system_message(f"Restored zoom to {original_zoom_level:.0%}", icon="video"))
            except Exception:
                pass  # Best effort restoration

    # Play completion sound and cleanup visual overlay
    if not dry_run and client and (visual or audio or lock):
        # Disable input lock first (restore user control)
        if lock:
            try:
                client.execute("window.__INSPEKT_VISUAL__.inputLock.disable()", timeout=5.0)
            except Exception:
                pass  # Best effort

        if cli_audio:
            # CLI audio: play stop and success sounds from Python
            cli_audio.play_stop_playback()
            if result.all_passed:
                time.sleep(0.3)
                cli_audio.play_success()
        elif use_browser_audio:
            # Browser audio: play via Web Audio API
            client.execute("window.__INSPEKT_VISUAL__.audio.playStopPlayback()", timeout=5.0)
            time.sleep(0.5)  # Wait for completion sound
            # Then play success chime if all passed
            if result.all_passed:
                client.execute("window.__INSPEKT_VISUAL__.audio.playSuccess()", timeout=5.0)
        # Clean up visual overlay
        if visual:
            time.sleep(0.3)  # Brief pause before cleanup
            client.execute("window.__INSPEKT_VISUAL__.cleanup()", timeout=5.0)

        # Disable replay mode if it was enabled
        if replay_mode_enabled:
            disable_result = client.disable_replay_mode(timeout=5.0)
            if verbose and disable_result.get("ok"):
                click.echo(format_system_message("replay mode disabled"))

        # Disable CDP dialog interception if it was enabled
        if cdp_dialog_interception_enabled:
            try:
                disable_code = build_cdp_disable_code()
                client.execute(disable_code, timeout=5.0)
                if verbose:
                    click.echo(format_system_message("CDP dialog interception disabled"))
            except Exception:
                pass  # Best effort cleanup

    # Print summary
    click.echo()

    if dry_run:
        click.echo(f"Dry run complete. {result.total_steps} steps would be executed.")
        return

    if replay_cancelled:
        # User cancelled the replay - show partial results
        duration = format_duration(result.duration_ms)
        completed = result.passed_steps + result.failed_steps + result.skipped_steps
        click.secho(f"Replay cancelled after {completed} of {result.total_steps} steps", fg="yellow", bold=True)
        click.echo(f"  Passed: {result.passed_steps} | Failed: {result.failed_steps} | Skipped: {result.skipped_steps}")
        click.echo(f"  Duration: {duration}")
        sys.exit(130)  # Exit code 130 = cancelled by user (like Ctrl+C)

    duration = format_duration(result.duration_ms)

    if result.all_passed:
        click.secho(success(f"All {result.passed_steps} steps passed"), fg="green", bold=True)
        click.echo(f"  Duration: {duration}")
        # Show tip about interactive mode (only if not already using it)
        if not interactive:
            click.echo()
            from inspekt.app.cli.table import print_hint
            print_hint("Use `--interactive` or `-i` to step through manually.")
    else:
        click.secho(error(f"{result.failed_steps} of {result.total_steps} steps failed"), fg="red", bold=True)
        click.echo(f"  Passed: {result.passed_steps} | Failed: {result.failed_steps} | Skipped: {result.skipped_steps}")
        click.echo(f"  Duration: {duration}")

        # Show failures
        click.echo()
        click.secho("Failures:", fg="red")
        has_browser_timeout = False
        for failure in result.failures:
            click.echo(f"\n  Step {failure['step']}: {failure['action']}")
            if failure.get("selector"):
                click.echo(f"    Selector: {failure['selector']}")
            click.echo(f"    Error: {failure['error']}")
            if failure.get("assertion_failures"):
                for af in failure["assertion_failures"]:
                    click.echo(f"    - {af}")
            # Track if any failures are browser timeouts
            if "No response from browser" in failure.get("error", ""):
                has_browser_timeout = True

        # Show browser connection troubleshooting once if needed
        if has_browser_timeout:
            click.echo()
            click.secho("Browser connection issue detected.", fg="yellow", bold=True)
            click.echo()
            click.echo("Possible causes:")
            click.echo("  • No browser tab is open with the Inspekt extension active")
            click.echo("  • The extension is disabled or not installed")
            click.echo("  • Content Security Policy (CSP) is blocking the connection")
            click.echo()
            click.echo("Troubleshooting:")
            from inspekt.app.cli.table import _style_with_inline_code
            click.echo(_style_with_inline_code("  • Open browser console (`F12`) and check for Inspekt messages", base_fg="white"))
            click.echo("  • Look for CSP warnings in red/orange")
            click.echo(_style_with_inline_code("  • Verify connection: `inspekt status`", base_fg="white"))
            click.echo("  • Try refreshing the page or restarting the browser")

        # Show tip for slow pages
        click.echo()
        from inspekt.app.cli.table import print_hint
        print_hint("If pages load slowly, try `--slow` or `--very-slow` for more reliable playback.")

        sys.exit(1)
