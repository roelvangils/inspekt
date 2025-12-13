"""Replay recorded browser interactions from a YAML file."""

import json
import platform
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
from inspekt.config import get_audio_config
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

import requests

# Bridge server constants
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


def complete_recording_files(ctx, param, incomplete):
    """Shell completion for recording files.

    Returns recording_*.yaml files in the current directory that match
    the incomplete input.
    """
    cwd = Path.cwd()
    recording_files = list(cwd.glob("recording_*.yaml"))

    # Filter by incomplete prefix and return filenames
    matches = []
    for f in recording_files:
        name = f.name
        if name.startswith(incomplete) or incomplete in name:
            matches.append(name)

    return sorted(matches, key=lambda x: -cwd.joinpath(x).stat().st_mtime)


def find_most_recent_recording() -> Optional[Path]:
    """
    Find the most recently modified recording file in the current directory.

    Looks for files matching 'recording_*.yaml' and returns the one
    with the most recent modification time.

    Returns:
        Path to the most recent recording file, or None if not found.
    """
    cwd = Path.cwd()
    recording_files = list(cwd.glob("recording_*.yaml"))

    if not recording_files:
        return None

    # Sort by modification time (most recent first)
    recording_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    return recording_files[0]

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
    help="Try to resize browser window to match recorded viewport dimensions",
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
    Examples:
        inspekt replay                             # Replay most recent recording
        inspekt replay login-flow.yaml             # Replay at normal speed
        inspekt replay login-flow.yaml --slow      # Replay at half speed
        inspekt replay login-flow.yaml --instant   # Fast replay, no delays
        inspekt replay login-flow.yaml --skip-hover    # Skip hovers
        inspekt replay login-flow.yaml --dry-run   # Preview steps
        inspekt replay login-flow.yaml --pause-on-fail # Debug failures
        inspekt replay login-flow.yaml -i          # Interactive step-through
    """
    # If no recording file specified, find the most recent one
    auto_selected = False
    if recording_file is None:
        recent = find_most_recent_recording()
        if recent is None:
            click.echo("Error: No recording file specified and no recording_*.yaml files found in current directory.", err=True)
            sys.exit(1)
        recording_file = str(recent)
        auto_selected = True

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

    # Create CLI audio instance if using CLI audio
    cli_audio: CLIAudio | None = None
    use_browser_audio = False
    if audio:
        if audio_output == "cli":
            cli_audio = CLIAudio(volume=audio_volume)
        else:  # "browser"
            use_browser_audio = True

    # Build skip set from options
    skip_actions = set(skip)
    if skip_hover:
        skip_actions.add("hover")

    # Load recording
    recording_path = Path(recording_file)

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
    elif interactive:
        click.echo()
        click.secho("Interactive mode: ", fg="cyan", bold=True, nl=False)
        click.echo("Press ", nl=False)
        click.secho("Enter", fg="green", bold=True, nl=False)
        click.echo(" to execute, ", nl=False)
        click.secho("Space", fg="yellow", bold=True, nl=False)
        click.echo(" to skip, ", nl=False)
        click.secho("Escape", fg="red", bold=True, nl=False)
        click.echo(" to cancel")
        click.echo()
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
            click.echo(
                "Error: Bridge server is not running. Start it with: inspekt start",
                err=True,
            )
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

        # Restore viewport if requested
        if restore_viewport and viewport:
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
                    click.echo("  Tip: Manually resize your browser window for best results.")
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
                                click.secho(f"✗ Precondition failed: {desc}", fg="red")
                                click.echo("  Use --no-strict-preconditions to continue anyway")
                                sys.exit(1)
                            else:
                                click.secho(f"⚠ Precondition not met: {desc}", fg="yellow")
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
                            click.secho("✗ DOM checksum mismatch - page structure has changed", fg="red")
                            click.echo("  Use --no-strict-checksum to continue anyway")
                            sys.exit(1)
                        else:
                            click.secho("⚠ DOM checksum mismatch - page structure differs from recording", fg="yellow")
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
                            click.secho("⚠ Failed to restore cookies", fg="yellow")
                except Exception as e:
                    click.secho(f"⚠ Cookie restoration failed: {e}", fg="yellow")

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
                        click.secho(f"⚠ localStorage restoration failed: {e}", fg="yellow")

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
                        click.secho(f"⚠ sessionStorage restoration failed: {e}", fg="yellow")

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

        # Inject visual feedback script if enabled (also needed for --lock)
        # We use "replay mode" which tells the extension to auto-inject the visual script
        # on every page load. This eliminates the need to poll and inject after navigation.
        replay_mode_enabled = False
        if visual or audio or lock:
            visual_script_path = scripts_dir / "replay_visual.js"
            try:
                with _builtin_open(visual_script_path) as f:
                    visual_script = f.read()

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

    # Print step header (unless in progress bar mode)
    if not progress:
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

    # Execute steps
    previous_timestamp = steps_to_run[0].timestamp if steps_to_run else 0
    last_step_navigated = False  # Track if previous step caused navigation
    page_load_wait_ms = 0  # Time spent waiting for page load (subtract from next delay)
    replay_cancelled = False  # Track if user cancelled in interactive mode

    for i, step in enumerate(steps_to_run):
        actual_index = start_idx + i
        step_dict = step.model_dump(exclude_none=True)
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
                        continue
                    elif choice == "cancel":
                        # User pressed Escape - cancel the entire replay
                        click.echo(summary, nl=False)
                        click.echo(click.style(" CANCELLED", fg="yellow"))
                        click.echo()
                        click.secho("Replay cancelled by user.", fg="yellow")
                        replay_cancelled = True
                        break
                    # choice == "next" - continue to execute the step
                else:
                    if verbose:
                        click.echo(format_system_message(f"Interactive prompt failed: {interactive_result.get('error')}"))
            except Exception as e:
                if verbose:
                    click.echo(format_system_message(f"Interactive prompt error: {e}"))

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
                        if not progress:
                            click.echo(format_status("OK"))

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
                                elif verbose:
                                    click.echo(format_system_message("Warning: visual script not ready after navigation"))

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

    result.end_time = datetime.now()

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
            click.secho("Tip:", fg="cyan", bold=True, nl=False)
            click.echo(" Use ", nl=False)
            click.secho("--interactive", fg="cyan", nl=False)
            click.echo(" or ", nl=False)
            click.secho("-i", fg="cyan", nl=False)
            click.echo(" to step through manually.")
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
            click.echo("  • Open browser console (F12) and check for Inspekt messages")
            click.echo("  • Look for CSP warnings in red/orange")
            click.echo("  • Verify connection: ", nl=False)
            click.secho("inspekt status", fg="cyan")
            click.echo("  • Try refreshing the page or restarting the browser")

        # Show tip for slow pages
        click.echo()
        click.secho("Tip:", fg="yellow", bold=True, nl=False)
        click.echo(" If pages load slowly, try ", nl=False)
        click.secho("--slow", fg="cyan", nl=False)
        click.echo(" or ", nl=False)
        click.secho("--very-slow", fg="cyan", nl=False)
        click.echo(" for more reliable playback.")

        sys.exit(1)
