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

from inspekt.client import BridgeClient
from inspekt.domain.recording import Recording
from inspekt.services.applescript_utils import activate_browser_tab

# Save built-in open before it gets shadowed
_builtin_open = open


def get_recordings_dir() -> Path:
    """Get the default directory for stored recordings."""
    return Path.home() / ".inspekt" / "recordings"


def format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        minutes = ms // 60000
        seconds = (ms % 60000) / 1000
        return f"{minutes}m {seconds:.0f}s"


def format_step_summary(step: dict, index: int) -> str:
    """Format a step for display during replay."""
    action = step.get("action", "unknown")
    target = step.get("target", {})
    selector = target.get("selector", "")[:40] if target else ""
    accessible_name = target.get("accessible_name", "") if target else ""

    prefix = f"[{index + 1}]"

    if action == "navigate":
        url = step.get("url", "")
        if len(url) > 50:
            url = url[:47] + "..."
        return f"{prefix} navigate → {url}"

    elif action == "click":
        name = accessible_name or target.get("text", "")[:25] if target else ""
        if name:
            return f"{prefix} click → {selector} \"{name}\""
        return f"{prefix} click → {selector}"

    elif action == "type":
        char_count = len(step.get("value", ""))
        if step.get("sensitive"):
            return f"{prefix} type → {selector} (password)"
        return f"{prefix} type → {selector} ({char_count} chars)"

    elif action == "keypress":
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])
        if modifiers:
            key_str = "+".join(modifiers) + "+" + key
        else:
            key_str = key
        return f"{prefix} keypress → {key_str}"

    elif action == "hover":
        name = accessible_name or target.get("text", "")[:25] if target else ""
        if name:
            return f"{prefix} hover → {selector} \"{name}\""
        return f"{prefix} hover → {selector}"

    elif action == "inspekt":
        cmd = step.get("command", "")
        return f"{prefix} inspekt → {cmd}"

    return f"{prefix} {action}"


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


def check_inspekt_expectations(command: str, expect: dict, cmd_result: dict) -> list[str]:
    """Check expectations for an inspekt command."""
    failures = []

    if not expect:
        return failures

    # For console commands, check if output is empty
    if "console" in command and expect.get("empty"):
        stdout = cmd_result.get("stdout", "")
        # Check if there are any log entries (non-empty, non-header output)
        lines = [l for l in stdout.strip().split("\n") if l.strip() and not l.startswith("Console")]
        if lines:
            failures.append(f"Expected no console messages, but found: {len(lines)} message(s)")

    # For axe commands, check violations
    if "axe" in command and expect.get("violations") is not None:
        max_violations = expect["violations"]
        stdout = cmd_result.get("stdout", "")
        # Try to parse violation count from output
        # This is a simplified check - axe output format may vary
        if "violation" in stdout.lower():
            # Count violations mentioned
            import re
            matches = re.findall(r"(\d+)\s*violation", stdout.lower())
            if matches:
                actual_violations = int(matches[0])
                if actual_violations > max_violations:
                    failures.append(f"Expected max {max_violations} violations, found {actual_violations}")

    return failures


@click.command()
@click.argument("recording_file", type=click.Path(exists=True))
@click.option(
    "--speed",
    type=float,
    default=1.0,
    help="Playback speed multiplier (e.g., 2.0 for 2x speed, 0.5 for half speed)",
)
@click.option(
    "--step-delay",
    type=int,
    default=500,
    help="Delay between steps in milliseconds (default: 500)",
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
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output for each step",
)
def replay(
    recording_file: str,
    speed: float,
    step_delay: int,
    dry_run: bool,
    start_step: int,
    end_step: Optional[int],
    verbose: bool,
):
    """
    Replay a recorded browser interaction session.

    Executes all steps from a YAML recording file against the current browser.
    Reports all assertion failures at the end (continues on failure).

    \b
    Examples:
        inspekt replay login-flow.yaml           # Replay at normal speed
        inspekt replay login-flow.yaml --speed 2 # Replay at 2x speed
        inspekt replay login-flow.yaml --dry-run # Preview steps
        inspekt replay login-flow.yaml --start-step 5  # Start from step 5
    """
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

    click.echo(f"\nReplaying: {recording_path.name}")
    click.echo(f"URL: {recording.metadata.starting_url}")
    click.echo(f"Steps: {len(steps_to_run)} of {total_steps}", nl=False)
    if start_step > 1 or end_step:
        click.echo(f" (steps {start_idx + 1}-{end_idx})")
    else:
        click.echo()

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

    if not dry_run:
        client = BridgeClient()

        if not client.is_alive():
            click.echo(
                "Error: Bridge server is not running. Start it with: inspekt start",
                err=True,
            )
            sys.exit(1)

        # Focus the browser tab before starting replay (macOS only)
        focus_browser_tab(client, verbose=verbose)

        # Load replay script
        script_path = Path(__file__).parent.parent.parent / "scripts" / "replay_step.js"

        try:
            with _builtin_open(script_path) as f:
                script_template = f.read()
        except FileNotFoundError:
            click.echo(f"Error: Script not found: {script_path}", err=True)
            sys.exit(1)

    # Execute steps
    for i, step in enumerate(steps_to_run):
        actual_index = start_idx + i
        step_dict = step.model_dump(exclude_none=True)

        # Display step
        summary = format_step_summary(step_dict, actual_index)

        if dry_run:
            click.echo(f"  {summary}")
            if step.expect:
                expect_dict = step.expect.model_dump(exclude_none=True)
                click.echo(f"      expect: {expect_dict}")
            continue

        click.echo(f"  {summary}", nl=False)

        # Handle inspekt commands separately
        if step.action == "inspekt" and step.command:
            cmd_result = run_inspekt_command(step.command)

            if cmd_result.get("ok"):
                # Check expectations
                expect_dict = step.expect.model_dump(exclude_none=True) if step.expect else {}
                assertion_failures = check_inspekt_expectations(step.command, expect_dict, cmd_result)

                if assertion_failures:
                    click.secho(" FAIL", fg="red")
                    result.add_failure(actual_index, step_dict, "Assertion failed", assertion_failures)
                    if verbose:
                        for failure in assertion_failures:
                            click.echo(f"      ⚠ {failure}")
                else:
                    click.secho(" OK", fg="green")
                    result.add_success(actual_index, step_dict)
            else:
                click.secho(" FAIL", fg="red")
                result.add_failure(actual_index, step_dict, cmd_result.get("error", "Command failed"))
                if verbose:
                    click.echo(f"      Error: {cmd_result.get('error', 'Unknown')}")

        # Handle type actions with human-like typing
        elif step.action == "type" and step.value:
            target = step.target
            selector = target.selector if target else None

            if not selector:
                click.secho(" FAIL", fg="red")
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
                    click.secho(" OK", fg="green")
                    result.add_success(actual_index, step_dict)
                    if verbose and used_selector != selector:
                        click.echo(f"      (used fallback: {used_selector})")
                else:
                    click.secho(" FAIL", fg="red")
                    result.add_failure(actual_index, step_dict, type_result.get("error", "Typing failed"))
                    if verbose:
                        click.echo(f"      Error: {type_result.get('error', 'Unknown')}")

        else:
            # Execute via JavaScript (for click, hover, keypress, navigate)
            step_json = json.dumps(step_dict)
            code = script_template.replace("STEP_DATA_PLACEHOLDER", step_json)

            try:
                exec_result = client.execute(code, timeout=30.0)

                if exec_result.get("ok"):
                    response = exec_result.get("result", {})

                    if response.get("ok"):
                        # Check for assertion failures
                        assertion_failures = response.get("failures", [])

                        if assertion_failures or response.get("assertionsFailed"):
                            click.secho(" FAIL", fg="yellow")
                            result.add_failure(actual_index, step_dict, "Assertion failed", assertion_failures)
                            if verbose:
                                for failure in assertion_failures:
                                    click.echo(f"      ⚠ {failure}")
                        else:
                            click.secho(" OK", fg="green")
                            result.add_success(actual_index, step_dict)

                            if verbose and response.get("usedSelector"):
                                used = response["usedSelector"]
                                original = step_dict.get("target", {}).get("selector", "")
                                if used != original:
                                    click.echo(f"      (used fallback: {used})")

                        # Handle navigation - wait for page load
                        if response.get("navigated"):
                            time.sleep(1.0)  # Wait for navigation

                    elif response.get("skipped"):
                        click.secho(" SKIP", fg="cyan")
                        result.add_skip(actual_index, step_dict, response.get("message", "Skipped"))
                        if verbose:
                            click.echo(f"      {response.get('message', '')}")

                    else:
                        error = response.get("error", "Unknown error")
                        click.secho(" FAIL", fg="red")
                        result.add_failure(actual_index, step_dict, error)
                        if verbose:
                            click.echo(f"      Error: {error}")

                else:
                    error = exec_result.get("error", "Execution failed")
                    click.secho(" FAIL", fg="red")
                    result.add_failure(actual_index, step_dict, error)
                    if verbose:
                        click.echo(f"      Error: {error}")

            except Exception as e:
                click.secho(" FAIL", fg="red")
                result.add_failure(actual_index, step_dict, str(e))
                if verbose:
                    click.echo(f"      Exception: {e}")

        # Delay between steps (adjusted for speed)
        if not dry_run and i < len(steps_to_run) - 1:
            delay = step_delay / speed / 1000.0
            time.sleep(delay)

    result.end_time = datetime.now()

    # Print summary
    click.echo()
    click.echo("─" * 50)

    if dry_run:
        click.echo(f"Dry run complete. {result.total_steps} steps would be executed.")
        return

    duration = format_duration(result.duration_ms)

    if result.all_passed:
        click.secho(f"✓ All {result.passed_steps} steps passed", fg="green", bold=True)
        click.echo(f"  Duration: {duration}")
    else:
        click.secho(f"✗ {result.failed_steps} of {result.total_steps} steps failed", fg="red", bold=True)
        click.echo(f"  Passed: {result.passed_steps} | Failed: {result.failed_steps} | Skipped: {result.skipped_steps}")
        click.echo(f"  Duration: {duration}")

        # Show failures
        click.echo()
        click.secho("Failures:", fg="red")
        for failure in result.failures:
            click.echo(f"\n  Step {failure['step']}: {failure['action']}")
            if failure.get("selector"):
                click.echo(f"    Selector: {failure['selector']}")
            click.echo(f"    Error: {failure['error']}")
            if failure.get("assertion_failures"):
                for af in failure["assertion_failures"]:
                    click.echo(f"    - {af}")

        sys.exit(1)
