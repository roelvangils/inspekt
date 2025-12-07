"""Record browser interactions to a YAML file for later replay."""

import json
import signal
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import click
import yaml

from inspekt.app.cli.icons import success as success_icon
from inspekt.client import BridgeClient
from inspekt.config import get_audio_config
from inspekt.services.audio import CLIAudio
from inspekt.domain.recording import (
    ExpectInfo,
    Recording,
    RecordingMetadata,
    RecordingStep,
    ScrollInfo,
    TargetInfo,
    ViewportInfo,
)
from .formatting import (
    format_duration,
    format_step_for_display,
    format_system_message,
    get_recordings_dir,
)

# Save built-in open before it gets shadowed
_builtin_open = open


def generate_filename(url: str, timestamp: datetime) -> str:
    """Generate a descriptive filename from URL and timestamp.

    Format: recording_{domain}_{path}_{timestamp}.yaml
    """
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").replace(".", "_").replace(":", "_")
    path = parsed.path.strip("/").replace("/", "_")[:30] or "index"
    ts = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"recording_{domain}_{path}_{ts}.yaml"


def convert_js_event_to_step(event: dict) -> RecordingStep:
    """Convert a JavaScript event object to a RecordingStep."""
    action = event.get("action")
    timestamp = event.get("timestamp", 0)

    # Build target info if present
    target = None
    if event.get("target"):
        t = event["target"]
        target = TargetInfo(
            selector=t.get("selector", ""),
            fallback_selectors=t.get("fallback_selectors", []),
            text=t.get("text"),
            accessible_name=t.get("accessible_name"),
            tag=t.get("tag"),
            role=t.get("role"),
        )

    # Build scroll info if present
    scroll = None
    if event.get("scroll"):
        s = event["scroll"]
        scroll = ScrollInfo(
            x=s.get("x", 0),
            y=s.get("y", 0),
            deltaX=s.get("deltaX", 0),
            deltaY=s.get("deltaY", 0),
        )

    # Get click_at position [x%, y%] if present
    click_at = event.get("click_at")

    return RecordingStep(
        timestamp=timestamp,
        action=action,
        url=event.get("url"),
        target=target,
        value=event.get("value"),
        sensitive=event.get("sensitive", False),
        key=event.get("key"),
        modifiers=event.get("modifiers", []),
        scroll=scroll,
        command=event.get("command"),
        click_at=click_at,
        expect=None,  # User adds expectations manually
    )


class RecordingYAMLDumper(yaml.SafeDumper):
    """Custom YAML dumper for readable recording files."""

    pass


def str_representer(dumper, data):
    """Use literal style for multi-line strings."""
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


def datetime_representer(dumper, data):
    """ISO format for datetime."""
    return dumper.represent_scalar("tag:yaml.org,2002:str", data.isoformat())


RecordingYAMLDumper.add_representer(str, str_representer)
RecordingYAMLDumper.add_representer(datetime, datetime_representer)


def save_recording_to_yaml(recording: Recording, filepath: Path) -> None:
    """Save recording to YAML file with human-readable formatting."""
    header = f"""# Inspekt Recording v{recording.metadata.version}
# Generated: {recording.metadata.created_at.isoformat()}
# Duration: {recording.metadata.duration_ms / 1000:.1f}s
# URL: {recording.metadata.starting_url}
#
# Edit this file to:
# - Add 'expect:' assertions to steps
# - Insert 'inspekt' command steps for accessibility checks
# - Remove unwanted steps
#
# Example assertion:
#   expect:
#     visible: ".success-message"
#     url_contains: "/dashboard"

"""
    # Convert to dict, excluding None values
    data = recording.model_dump(exclude_none=True)

    # Remove empty lists and default values for cleaner output
    def clean_dict(d):
        if isinstance(d, dict):
            return {
                k: clean_dict(v)
                for k, v in d.items()
                if v is not None and v != [] and v != {} and v is not False
            }
        elif isinstance(d, list):
            return [clean_dict(item) for item in d]
        return d

    data = clean_dict(data)

    # Generate YAML content
    yaml_content = yaml.dump(
        data,
        Dumper=RecordingYAMLDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

    # Post-process to add accessible name comments before steps
    lines = yaml_content.split('\n')
    output_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Check if this is a step entry (starts with "- action:")
        if line.strip().startswith('- action:'):
            # Look ahead for accessible_name in this step's target
            accessible_name = None
            j = i + 1
            indent_level = len(line) - len(line.lstrip())

            while j < len(lines):
                next_line = lines[j]
                # Stop if we hit the next step or end of steps
                if next_line.strip().startswith('- action:') or (next_line.strip() and not next_line.startswith(' ' * (indent_level + 1))):
                    break
                # Look for accessible_name
                if 'accessible_name:' in next_line:
                    # Extract the value
                    parts = next_line.split('accessible_name:', 1)
                    if len(parts) > 1:
                        accessible_name = parts[1].strip().strip('"').strip("'")
                j += 1

            # Add comment if we found an accessible name
            if accessible_name:
                output_lines.append(f'  # → {accessible_name}')

        output_lines.append(line)
        i += 1

    with _builtin_open(filepath, "w") as f:
        f.write(header)
        f.write('\n'.join(output_lines))


def get_recording_metadata(filepath: Path) -> Optional[dict]:
    """Extract metadata from recording file without full parse."""
    try:
        with _builtin_open(filepath) as f:
            data = yaml.safe_load(f)
        if not data or "metadata" not in data:
            return None
        meta = data["metadata"]
        return {
            "name": filepath.name,
            "path": filepath,
            "created_at": meta.get("created_at"),
            "duration_ms": meta.get("duration_ms", 0),
            "steps": len(data.get("steps", [])),
            "url": meta.get("starting_url", ""),
        }
    except Exception:
        return None


@click.group(invoke_without_command=True)
@click.option(
    "-o", "--output",
    "output",
    default=None,
    help="Output filename (auto-generated if not specified)",
)
@click.option(
    "--include-hover/--no-hover",
    default=True,
    help="Record hover events on interactive elements",
)
@click.option(
    "--mask-passwords/--no-mask-passwords",
    default=True,
    help="Mask password input values in recording",
)
@click.option(
    "--min-hover-duration",
    type=int,
    default=200,
    help="Minimum hover duration in ms to record (default: 200)",
)
@click.option(
    "--replay",
    is_flag=True,
    help="Automatically replay the recording after saving to verify it works",
)
@click.option(
    "--no-audio",
    "no_audio",
    is_flag=True,
    help="Disable audio feedback during replay (requires --replay)",
)
@click.option(
    "--no-visual",
    "no_visual",
    is_flag=True,
    help="Disable visual feedback during replay (requires --replay)",
)
@click.option(
    "--no-feedback",
    "no_feedback",
    is_flag=True,
    help="Disable both audio and visual feedback during replay (requires --replay)",
)
@click.pass_context
def record(
    ctx,
    output: Optional[str],
    include_hover: bool,
    mask_passwords: bool,
    min_hover_duration: int,
    replay: bool,
    no_audio: bool,
    no_visual: bool,
    no_feedback: bool,
):
    """
    Record browser interactions to a YAML file.

    Starts recording all user actions on the currently open browser page.
    Press Ctrl+C to stop recording and save the file.

    The recording can later be replayed with 'inspekt replay' and edited
    to add assertions for automated testing.

    \b
    Commands:
        inspekt record tutorial           # Interactive tutorial
        inspekt record list               # List all recordings
        inspekt record show FILE          # Show recording details
        inspekt record delete FILE        # Delete a recording

    \b
    Examples:
        inspekt record                    # Auto-generates filename
        inspekt record -o login-flow.yaml # Specific filename
        inspekt record --no-hover         # Skip hover events
        inspekt record --replay           # Record and replay to verify
        inspekt record --replay --no-feedback  # Replay without audio/visual
    """
    # If a subcommand was invoked, don't run recording
    if ctx.invoked_subcommand is not None:
        return

    # Original recording logic follows
    client = BridgeClient()

    if not client.is_alive():
        click.echo(
            "Error: Bridge server is not running. Start it with: inspekt start",
            err=True,
        )
        sys.exit(1)

    # Load the recording script
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    script_path = scripts_dir / "record_events.js"

    try:
        with _builtin_open(script_path) as f:
            script_template = f.read()
    except FileNotFoundError:
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    # Load and inject the visual/audio script for start/stop sounds
    visual_script = None
    visual_script_path = scripts_dir / "replay_visual.js"
    try:
        with _builtin_open(visual_script_path) as f:
            visual_script = f.read()
        # Inject the script
        client.execute(visual_script, timeout=10.0)
    except FileNotFoundError:
        pass  # Visual script is optional for recording

    # Configuration for the browser script
    # Generate a unique recording ID for IndexedDB persistence
    recording_id = f"rec_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    config = {
        "includeHover": include_hover,
        "maskPasswords": mask_passwords,
        "minHoverDuration": min_hover_duration,
        "audio": True,  # Always enable audio feedback during recording
        "recordingId": recording_id,
    }
    config_json = json.dumps(config)

    # Prepare start code
    start_code = script_template.replace("ACTION_PLACEHOLDER", "start")
    start_code = start_code.replace("CONFIG_PLACEHOLDER", config_json)

    # Start recording
    try:
        result = client.execute(start_code, timeout=10.0)

        if not result.get("ok"):
            click.echo(f"Error starting recording: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        start_url = response.get("startUrl", "")
        start_time = datetime.now(timezone.utc)
        viewport = response.get("viewport", {"width": 1920, "height": 1080})
        zoom = response.get("zoom", 1.0)
        user_agent = response.get("userAgent", "")

        # Track which browser tab we started recording in
        # This prevents accidentally resuming in a different tab
        recording_browser_index = client.get_current_browser_index()

        # Focus the browser window (macOS only)
        # This helps the user start recording immediately
        import platform
        if platform.system() == "Darwin":
            try:
                from inspekt.services.applescript_utils import focus_browser_window

                # Detect browser from user agent
                browser_name = "Chrome"  # Default
                if "Firefox" in user_agent:
                    browser_name = "Firefox"
                elif "Edg" in user_agent:
                    browser_name = "Edge"
                elif "Brave" in user_agent:
                    browser_name = "Brave"
                elif "Safari" in user_agent and "Chrome" not in user_agent:
                    browser_name = "Safari"

                focus_browser_window(browser_name)
            except Exception:
                pass  # Focus is optional - don't fail recording if it doesn't work

        # Play start sound (target the specific browser we're recording in)
        if visual_script:
            try:
                client.execute("window.__INSPEKT_VISUAL__.audio.playStart()", timeout=5.0, browser_index=recording_browser_index)
                time.sleep(0.4)  # Wait for start sound to complete
            except Exception:
                pass  # Audio is optional

        # Display recording header
        from inspekt.config import is_nerdfont_enabled
        record_icon = "\U000f044a " if is_nerdfont_enabled() else ""  # 󰑊 nf-md-record
        recording_label = click.style(f"{record_icon}Recording", fg="red", bold=True)
        ctrl_c = click.style(" Ctrl+C ", fg="black", bg="bright_yellow")
        click.echo(f"\n{recording_label}: {start_url}")
        click.echo(f"Press {ctrl_c} to stop and save\n")

        # Prepare poll and stop codes
        poll_code = script_template.replace("ACTION_PLACEHOLDER", "poll")
        poll_code = poll_code.replace("CONFIG_PLACEHOLDER", config_json)

        stop_code = script_template.replace("ACTION_PLACEHOLDER", "stop")
        stop_code = stop_code.replace("CONFIG_PLACEHOLDER", config_json)

        # Collected steps
        all_steps: list[RecordingStep] = []

        # Track seen event timestamps to prevent duplicates after resume
        seen_timestamps: set[int] = set()

        # Step counter for display
        step_count = 0

        # Track recording start time for resume (milliseconds since epoch)
        recording_start_epoch_ms = int(start_time.timestamp() * 1000)

        # Track last known URL for navigation detection
        last_known_url = start_url

        # Prepare resume code template
        def get_resume_code(current_elapsed_ms: int) -> str:
            """Generate resume code with the correct start time offset."""
            # Calculate what the inherited start time should be
            # so that getTimestamp() in JS returns correct elapsed time
            inherited_start = recording_start_epoch_ms
            resume_config = {
                **config,
                "inheritedStartTime": inherited_start,
                "recordingId": recording_id,  # Pass recording ID for IndexedDB recovery
            }
            resume_code = script_template.replace("ACTION_PLACEHOLDER", "resume")
            resume_code = resume_code.replace("CONFIG_PLACEHOLDER", json.dumps(resume_config))
            return resume_code

        # Signal handler for Ctrl+C
        def stop_recording(sig, frame):
            nonlocal all_steps

            click.echo("\n\nStopping recording...")

            # Play stop/completion sound (target the specific browser we're recording in)
            if visual_script:
                try:
                    client.execute("window.__INSPEKT_VISUAL__.audio.playStop()", timeout=5.0, browser_index=recording_browser_index)
                except Exception:
                    pass  # Audio is optional

            try:
                # Stop recording and get final events (target the specific browser)
                stop_result = client.execute(stop_code, timeout=5.0, browser_index=recording_browser_index)

                if stop_result.get("ok"):
                    stop_response = stop_result.get("result", {})
                    final_events = stop_response.get("events", [])
                    js_duration = stop_response.get("duration", 0)

                    # Convert remaining events
                    for event in final_events:
                        # Skip if we already have this event (by timestamp)
                        if not any(s.timestamp == event.get("timestamp") for s in all_steps):
                            step = convert_js_event_to_step(event)
                            all_steps.append(step)

                    # Use JS duration if valid, otherwise calculate from CLI start time
                    # JS duration can be wrong after navigation/resume
                    if js_duration and js_duration > 0:
                        duration_ms = js_duration
                    else:
                        duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                else:
                    duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            except Exception as e:
                click.echo(f"Warning: Error during stop: {e}", err=True)
                duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # Build recording
            recording = Recording(
                metadata=RecordingMetadata(
                    version="1.0",
                    created_at=start_time,
                    duration_ms=duration_ms,
                    starting_url=start_url,
                    viewport=ViewportInfo(
                        width=viewport.get("width", 1920),
                        height=viewport.get("height", 1080),
                    ),
                    zoom=zoom,
                    user_agent=user_agent or None,
                ),
                steps=all_steps,
            )

            # Determine output path
            if output:
                output_path = Path(output)
                if not output_path.suffix:
                    output_path = output_path.with_suffix(".yaml")
            else:
                output_path = get_recordings_dir() / generate_filename(start_url, start_time)

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save recording
            try:
                save_recording_to_yaml(recording, output_path)
                click.echo("\n" + "─" * 70)
                click.secho(success_icon("Recording saved"), fg="green", bold=True)
                click.echo(f"  File:     {output_path}")
                click.echo(f"  Duration: {format_duration(duration_ms)}")
                # Count steps excluding hovers
                non_hover_steps = sum(1 for s in all_steps if s.action != "hover")
                hover_steps = len(all_steps) - non_hover_steps
                if hover_steps > 0:
                    click.echo(f"  Steps:    {non_hover_steps} (hover actions excluded)")
                else:
                    click.echo(f"  Steps:    {len(all_steps)}")
                if replay:
                    click.echo(f"\nStarting verification replay...")
                else:
                    click.echo(f"\nReplay with: inspekt replay {output_path.name}")
            except Exception as e:
                click.echo(f"Error saving recording: {e}", err=True)
                sys.exit(1)

            # Auto-replay if --replay flag was set
            if replay:
                # Reset signal handler to default so Ctrl+C during replay exits normally
                signal.signal(signal.SIGINT, signal.SIG_DFL)

                # Close the recording client's HTTP session to prevent connection issues
                # The replay command will create its own BridgeClient
                try:
                    client._session.close()
                except Exception:
                    pass

                # Create a fresh client for pre-replay setup
                from inspekt.app.cli.replay import replay as replay_cmd
                replay_client = BridgeClient()

                # Refresh the page before replay to reset state (focus, scroll position, etc.)
                click.echo()
                click.echo("Refreshing page before replay...")
                try:
                    replay_client.execute("location.reload()", timeout=5.0)
                    # Wait for page to start reloading
                    time.sleep(0.5)
                    # Wait for page to be ready
                    for _ in range(20):  # Max 10 seconds
                        result = replay_client.execute("document.readyState", timeout=3.0)
                        if result.get("ok") and result.get("result") == "complete":
                            break
                        time.sleep(0.5)
                except Exception:
                    pass  # Continue anyway

                # Inject audio for countdown sounds
                countdown_scripts_dir = Path(__file__).parent.parent.parent / "scripts"
                countdown_visual_path = countdown_scripts_dir / "replay_visual.js"
                try:
                    with _builtin_open(countdown_visual_path) as f:
                        countdown_visual_script = f.read()
                    replay_client.execute(countdown_visual_script, timeout=10.0)
                except Exception:
                    pass  # Continue without audio

                # Countdown with audio feedback
                countdown_beep = """
                (function() {
                    const visual = window.__INSPEKT_VISUAL__;
                    if (visual && visual.audio) {
                        visual.audio.init();
                        // Play a short beep (different pitch for each number)
                        const ctx = visual.audio.ctx || new (window.AudioContext || window.webkitAudioContext)();
                        if (ctx) {
                            const osc = ctx.createOscillator();
                            const gain = ctx.createGain();
                            osc.connect(gain);
                            gain.connect(ctx.destination);
                            osc.frequency.value = FREQ_PLACEHOLDER;
                            osc.type = 'sine';
                            gain.gain.setValueAtTime(0.2, ctx.currentTime);
                            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
                            osc.start(ctx.currentTime);
                            osc.stop(ctx.currentTime + 0.15);
                        }
                    }
                })()
                """

                click.echo()
                frequencies = {3: 440, 2: 523, 1: 659}  # A4, C5, E5 - ascending
                for i in range(3, 0, -1):
                    click.echo(f"\rStarting replay in {i}...", nl=False)
                    try:
                        beep_code = countdown_beep.replace("FREQ_PLACEHOLDER", str(frequencies[i]))
                        replay_client.execute(beep_code, timeout=1.0)
                    except Exception:
                        pass
                    time.sleep(1.0)
                click.echo("\r" + " " * 30 + "\r", nl=False)  # Clear the countdown line

                # Close the setup client
                try:
                    replay_client._session.close()
                except Exception:
                    pass

                # Verify browser is actually responsive before starting replay
                # is_alive() only checks server, we need to verify browser responds too
                replay_client = BridgeClient()

                # First check server is alive
                if not replay_client.is_alive():
                    click.echo(
                        "Error: Bridge server connection lost. "
                        f"Try running: inspekt replay {output_path.name}",
                        err=True,
                    )
                    sys.exit(1)

                # Now verify browser is responsive by executing a simple command
                # Retry a few times in case page is still loading
                max_retries = 5
                browser_ready = False
                for attempt in range(max_retries):
                    try:
                        result = replay_client.execute("document.readyState", timeout=3.0)
                        if result.get("ok"):
                            browser_ready = True
                            break
                    except Exception:
                        pass
                    if attempt < max_retries - 1:
                        time.sleep(0.5)

                if not browser_ready:
                    click.echo(
                        "Error: Browser not responding. Page may still be loading. "
                        f"Try running: inspekt replay {output_path.name}",
                        err=True,
                    )
                    sys.exit(1)

                # Close the verification client
                try:
                    replay_client._session.close()
                except Exception:
                    pass

                try:
                    # Create a new context and invoke replay
                    ctx = click.Context(replay_cmd)
                    # Determine visual/audio settings (default is ON, --no-* disables)
                    disable_visual = no_visual or no_feedback
                    disable_audio = no_audio or no_feedback

                    ctx.invoke(
                        replay_cmd,
                        recording_file=str(output_path),
                        speed=1.0,
                        slow=False,
                        very_slow=False,
                        instant=False,
                        step_delay=0,  # No delay for verification replay
                        dry_run=False,
                        start_step=1,
                        end_step=None,
                        skip_hover=True,  # Skip hovers during verification
                        skip=(),
                        pause_on_fail=False,
                        verbose=False,
                        no_visual=disable_visual,
                        no_audio=disable_audio,
                        no_feedback=False,  # Already handled above
                        lock=False,
                    )
                except SystemExit as e:
                    # Replay exits with code 1 on failure
                    sys.exit(e.code)
                except Exception as e:
                    click.echo(f"Error during replay: {e}", err=True)
                    sys.exit(1)

            sys.exit(0)

        signal.signal(signal.SIGINT, stop_recording)

        # Track consecutive errors for better handling
        consecutive_errors = 0
        max_consecutive_errors = 30  # About 3 seconds of errors before warning
        waiting_for_reconnect = False

        # Inactivity tracking
        last_activity_time = time.time()
        inactivity_warning_shown = False
        INACTIVITY_WARNING_SECONDS = 30
        INACTIVITY_STOP_SECONDS = 60

        # Debug mode - set INSPEKT_DEBUG=1 to enable
        import os
        debug_mode = os.environ.get("INSPEKT_DEBUG") == "1"

        def debug_log(msg: str):
            if debug_mode:
                click.echo(f"  [DEBUG] {msg}", err=True)

        # Main polling loop
        while True:
            # Check for inactivity
            inactive_seconds = time.time() - last_activity_time

            if inactive_seconds >= INACTIVITY_STOP_SECONDS:
                # Auto-stop due to inactivity
                click.echo(format_system_message("No activity for 60 seconds. Stopping recording."))
                # Trigger the stop handler
                import os
                os.kill(os.getpid(), signal.SIGINT)
                break

            if inactive_seconds >= INACTIVITY_WARNING_SECONDS and not inactivity_warning_shown:
                click.echo(format_system_message("No activity for 30 seconds. Recording will stop in 30 seconds."))
                inactivity_warning_shown = True

            try:
                debug_log("Sending poll request...")
                # Always target the specific browser tab where recording started
                result = client.execute(poll_code, timeout=2.0, browser_index=recording_browser_index)
                debug_log(f"Poll result: ok={result.get('ok')}, has_result={result.get('result') is not None}")

                # Reset error count on successful communication
                if consecutive_errors > 0 and waiting_for_reconnect:
                    click.echo(format_system_message("Reconnected"))
                consecutive_errors = 0
                waiting_for_reconnect = False

                if result.get("ok"):
                    response = result.get("result", {})

                    # Handle case where result might be a string (serialization issue)
                    if isinstance(response, str):
                        debug_log(f"Warning: response is a string, not dict: {response[:100]}")
                        try:
                            response = json.loads(response)
                        except json.JSONDecodeError:
                            response = {}

                    debug_log(f"Response: recordingActive={response.get('recordingActive')}, currentUrl={response.get('currentUrl', 'N/A')[:50] if response.get('currentUrl') else 'N/A'}")

                    # Check if recording is still active
                    recording_active = response.get("recordingActive", True)

                    if not recording_active:
                        # Recording was lost (likely due to page navigation)
                        debug_log("Recording inactive detected - navigation likely occurred")
                        # Get the new URL from the response
                        new_url = response.get("currentUrl", "")
                        debug_log(f"New URL: {new_url}, Last known URL: {last_known_url}")

                        if new_url and new_url != last_known_url:
                            # Calculate elapsed time for the navigation event
                            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                            # Add navigation event
                            nav_step = RecordingStep(
                                timestamp=elapsed_ms,
                                action="navigate",
                                url=new_url,
                            )
                            all_steps.append(nav_step)
                            step_count += 1

                            # Display navigation
                            nav_event = {"action": "navigate", "url": new_url}
                            display = format_step_for_display(nav_event, step_count, elapsed_ms)
                            click.echo(display)

                            last_known_url = new_url

                        # Resume recording on the new page (same tab, after navigation)
                        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                        # Re-inject visual script for stop sound (lost on navigation)
                        # Target the specific browser tab where recording started
                        if visual_script:
                            try:
                                client.execute(visual_script, timeout=5.0, browser_index=recording_browser_index)
                            except Exception:
                                pass

                        resume_code = get_resume_code(elapsed_ms)
                        debug_log("Sending resume command...")
                        # Target the specific browser tab where recording started
                        resume_result = client.execute(resume_code, timeout=5.0, browser_index=recording_browser_index)
                        debug_log(f"Resume result: ok={resume_result.get('ok')}, result={resume_result.get('result')}")

                        if resume_result.get("ok"):
                            # Recording resumed successfully
                            debug_log("Recording resumed successfully")
                            # Extract domain from URL for display
                            from urllib.parse import urlparse
                            resumed_url = new_url or last_known_url
                            try:
                                parsed = urlparse(resumed_url)
                                domain = parsed.netloc or resumed_url
                            except Exception:
                                domain = resumed_url
                            click.echo(format_system_message(f"Recording resumed on {domain}"))
                            # Reset inactivity tracking
                            last_activity_time = time.time()
                            inactivity_warning_shown = False
                        else:
                            # Failed to resume - might be on a restricted page
                            debug_log(f"Resume failed: {resume_result.get('error')}")
                            click.echo(format_system_message("Recording paused - waiting for supported page"))

                        continue  # Skip to next poll iteration

                    # Normal case: recording is active, process events
                    events = response.get("events", [])

                    if events:
                        # Reset inactivity tracking when we get events
                        last_activity_time = time.time()
                        inactivity_warning_shown = False

                    for event in events:
                        # Deduplicate events based on timestamp (prevents duplicates after resume)
                        event_timestamp = event.get("timestamp", 0)
                        if event_timestamp in seen_timestamps:
                            debug_log(f"Skipping duplicate event at timestamp {event_timestamp}")
                            continue
                        seen_timestamps.add(event_timestamp)

                        step = convert_js_event_to_step(event)
                        all_steps.append(step)
                        step_count += 1

                        # Calculate elapsed time from recording start
                        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                        # Update last known URL for navigate events
                        if event.get("action") == "navigate":
                            last_known_url = event.get("url", last_known_url)

                        # Display real-time feedback with step number and elapsed time
                        display = format_step_for_display(event, step_count, elapsed_ms)
                        click.echo(display)

                else:
                    # Poll failed - might be due to navigation
                    debug_log(f"Poll failed: {result.get('error')}")

            except (ConnectionError, TimeoutError) as e:
                # Handle connection errors gracefully (page might be navigating)
                consecutive_errors += 1
                debug_log(f"Connection/Timeout error #{consecutive_errors}: {type(e).__name__}: {e}")

                # Check if original browser tab is still available
                current_browser_count = client.get_browser_count()
                if recording_browser_index is not None and current_browser_count <= recording_browser_index:
                    # Original tab is no longer available - auto-stop recording
                    click.echo(format_system_message("Recording tab was closed. Stopping recording."))
                    import os
                    os.kill(os.getpid(), signal.SIGINT)
                    break

                if consecutive_errors == 10 and not waiting_for_reconnect:
                    # First warning after ~1 second of errors
                    click.echo(format_system_message("Waiting for browser to reconnect..."))
                    waiting_for_reconnect = True
                elif consecutive_errors >= max_consecutive_errors and consecutive_errors % 30 == 0:
                    # Periodic warning every 3 seconds
                    click.echo(format_system_message("Still waiting for browser connection..."))

            except Exception as e:
                # Other errors - log if verbose, otherwise ignore
                consecutive_errors += 1
                debug_log(f"Exception #{consecutive_errors}: {type(e).__name__}: {e}")

            time.sleep(0.1)  # Poll every 100ms

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


@record.command("list")
@click.option("--limit", "-n", type=int, default=None, help="Show only the last N recordings")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def list_recordings(limit: Optional[int], output_json: bool):
    """
    List all saved recordings.

    Shows recordings from ~/.inspekt/recordings/ with metadata including
    date, duration, step count, and starting URL.

    \b
    Examples:
        inspekt record list              # List all recordings
        inspekt record list --limit 10   # Show last 10
        inspekt record list --json       # JSON output
    """
    recordings_dir = get_recordings_dir()

    if not recordings_dir.exists():
        if output_json:
            click.echo("[]")
        else:
            click.echo("No recordings found.")
        return

    # Collect recordings
    recordings = []
    for filepath in recordings_dir.glob("*.yaml"):
        meta = get_recording_metadata(filepath)
        if meta:
            recordings.append(meta)

    # Sort by creation date (newest first)
    recordings.sort(key=lambda r: r.get("created_at") or "", reverse=True)

    # Apply limit
    if limit:
        recordings = recordings[:limit]

    if not recordings:
        if output_json:
            click.echo("[]")
        else:
            click.echo("No recordings found.")
        return

    # Output
    if output_json:
        import json
        output = []
        for r in recordings:
            output.append({
                "name": r["name"],
                "path": str(r["path"]),
                "created_at": r["created_at"].isoformat() if hasattr(r.get("created_at"), "isoformat") else str(r.get("created_at")),
                "duration_ms": r["duration_ms"],
                "steps": r["steps"],
                "url": r["url"],
            })
        click.echo(json.dumps(output, indent=2))
        return

    # Table output
    click.echo(f"\nRecordings ({recordings_dir})\n")
    click.echo("─" * 90)
    click.echo(f"{'NAME':<45} {'DATE':<12} {'DURATION':<10} {'STEPS':<6} URL")
    click.echo("─" * 90)

    for r in recordings:
        name = r["name"]
        if len(name) > 44:
            name = name[:41] + "..."

        # Format date
        created = r.get("created_at")
        if hasattr(created, "strftime"):
            date_str = created.strftime("%b %d %Y")
        elif isinstance(created, str):
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                date_str = dt.strftime("%b %d %Y")
            except:
                date_str = str(created)[:10]
        else:
            date_str = "N/A"

        # Format duration
        duration = format_duration(r["duration_ms"])

        # Format URL (truncate)
        url = r["url"]
        if url.startswith("https://"):
            url = url[8:]
        elif url.startswith("http://"):
            url = url[7:]
        if len(url) > 30:
            url = url[:27] + "..."

        click.echo(f"{name:<45} {date_str:<12} {duration:<10} {r['steps']:<6} {url}")

    click.echo("─" * 90)
    click.echo(f"Total: {len(recordings)} recording(s)")


@record.command("show")
@click.argument("recording_file", type=click.Path(exists=True))
def show_recording(recording_file: str):
    """
    Show details of a recording file.

    Displays metadata and step summary for a recording.

    \b
    Examples:
        inspekt record show login-flow.yaml
        inspekt record show ~/.inspekt/recordings/example_com_20251202.yaml
    """
    filepath = Path(recording_file)

    try:
        with _builtin_open(filepath) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        click.echo(f"Error reading file: {e}", err=True)
        sys.exit(1)

    if not data or "metadata" not in data:
        click.echo("Invalid recording file format.", err=True)
        sys.exit(1)

    meta = data["metadata"]
    steps = data.get("steps", [])

    click.echo(f"\nRecording: {filepath.name}")
    click.echo("─" * 60)
    click.echo(f"URL:      {meta.get('starting_url', 'N/A')}")

    # Format created date
    created = meta.get("created_at")
    if hasattr(created, "strftime"):
        click.echo(f"Created:  {created.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        click.echo(f"Created:  {created}")

    click.echo(f"Duration: {format_duration(meta.get('duration_ms', 0))}")
    click.echo(f"Steps:    {len(steps)}")

    # Viewport info
    viewport = meta.get("viewport", {})
    if viewport:
        click.echo(f"Viewport: {viewport.get('width')}x{viewport.get('height')}")

    # Step summary by type
    action_counts = {}
    for step in steps:
        action = step.get("action", "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

    if action_counts:
        click.echo(f"\nActions:  {', '.join(f'{k}: {v}' for k, v in sorted(action_counts.items()))}")

    # Show first few steps
    click.echo("\n─" * 60)
    click.echo("Steps preview:\n")

    for i, step in enumerate(steps[:10]):
        display = format_step_for_display(step, i + 1, step.get("timestamp", 0))
        click.echo(display)

    if len(steps) > 10:
        click.echo(f"\n  ... and {len(steps) - 10} more steps")

    click.echo(f"\nReplay with: inspekt replay {filepath}")


@record.command("delete")
@click.argument("recording_file", type=click.Path(exists=True))
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def delete_recording(recording_file: str, force: bool):
    """
    Delete a recording file.

    \b
    Examples:
        inspekt record delete login-flow.yaml
        inspekt record delete --force old-recording.yaml
    """
    filepath = Path(recording_file)

    if not force:
        click.echo(f"Delete recording: {filepath.name}?")
        if not click.confirm("Are you sure?"):
            click.echo("Cancelled.")
            return

    try:
        filepath.unlink()
        click.secho(success_icon(f"Deleted: {filepath.name}"), fg="green")
    except Exception as e:
        click.echo(f"Error deleting file: {e}", err=True)
        sys.exit(1)


@record.command("tutorial")
@click.option(
    "--speak",
    is_flag=True,
    help="Use text-to-speech to announce each action",
)
def record_tutorial(speak: bool):
    """
    Interactive tutorial for the record command.

    Learn how inspekt record works through a simulated recording session
    with audio and visual feedback.

    \b
    Examples:
        inspekt record tutorial           # Show descriptions as text
        inspekt record tutorial --speak   # Use text-to-speech
    """
    from typing import get_args
    from inspekt.domain.recording import ActionType

    client = BridgeClient()

    if not client.is_alive():
        click.echo(
            "Error: Bridge server is not running. Start it with: inspekt start",
            err=True,
        )
        sys.exit(1)

    # Introduction
    click.echo()
    click.secho("  INSPEKT RECORD TUTORIAL", fg="cyan", bold=True)
    click.echo()
    click.echo("  " + "─" * 50)
    click.echo()
    click.echo("  `inspekt record` allows you to capture an exact")
    click.echo("  browsing session from the terminal.")
    click.echo()
    click.echo("  It tracks:")
    click.echo("    • Keyboard shortcuts")
    click.echo("    • Scroll actions and mouse clicks")
    click.echo("    • Text you type, checkboxes you toggle, etc.")
    click.echo()
    click.echo("  Each session is saved as a human-readable YAML file,")
    click.echo("  which can later be converted into tests by adding")
    click.echo("  assertions.")
    click.echo()
    click.echo("  To replay a session, run:")
    click.secho("    inspekt replay path/to/recording.yaml", fg="yellow")
    click.echo()
    click.echo("  " + "─" * 50)
    click.echo()

    # Load the replay_visual.js script for audio
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    visual_script_path = scripts_dir / "replay_visual.js"

    try:
        with _builtin_open(visual_script_path) as f:
            visual_script = f.read()
    except Exception:
        visual_script = None

    # Get audio config
    audio_config = get_audio_config()
    audio_output = audio_config["output"]  # "cli" | "browser" | "off"
    audio_volume = audio_config["volume"]

    # Set up audio based on config
    cli_audio: CLIAudio | None = None
    use_browser_audio = False

    if audio_output == "off":
        click.echo(format_system_message("Audio disabled in config - continuing without sound"))
        click.echo()
        click.echo("  Press Enter to see all supported action types...")
        input()
    elif audio_output == "cli":
        # CLI audio: no browser interaction needed
        cli_audio = CLIAudio(volume=audio_volume)
        click.echo()
        click.echo("  Press Enter to hear all action types with audio feedback...")
        input()
    else:
        # Browser audio: inject script and require user interaction
        script_loaded = False
        if visual_script:
            try:
                result = client.execute(visual_script, timeout=5.0)
                if result.get("ok"):
                    script_loaded = True
            except Exception as e:
                click.echo(format_system_message(f"Failed to load audio script: {e}"), err=True)

        if not script_loaded:
            click.echo(format_system_message("Browser audio not available - using CLI audio"))
            cli_audio = CLIAudio(volume=audio_volume)
            click.echo()
            click.echo("  Press Enter to see all supported action types...")
            input()
        else:
            use_browser_audio = True
            # Prompt to continue - ask user to click in browser first for audio
            click.echo("  To hear sound effects, click anywhere in your browser window,")
            click.echo("  then press Enter here to continue...")
            click.echo()
            input()

            # Now initialize audio after user has clicked in browser
            try:
                init_result = client.execute("""
                    (function() {
                        if (!window.__INSPEKT_VISUAL__) {
                            return { ok: false, error: 'Visual module not found' };
                        }
                        try {
                            window.__INSPEKT_VISUAL__.audio.init();
                            window.__INSPEKT_VISUAL__.audio.warmUp();
                            // Try to play a test sound
                            window.__INSPEKT_VISUAL__.audio.playClick();
                            return { ok: true, state: 'initialized' };
                        } catch (e) {
                            return { ok: false, error: e.message };
                        }
                    })()
                """, timeout=3.0)

                if init_result.get("ok"):
                    audio_result = init_result.get("result", {})
                    if not audio_result.get("ok"):
                        click.echo(format_system_message(f"Audio error: {audio_result.get('error', 'unknown')}"))
            except Exception as e:
                click.echo(format_system_message(f"Audio init error: {e}"))

    # Get all action types dynamically from the ActionType Literal
    all_actions = list(get_args(ActionType))

    # Sample steps for each action type - these demonstrate the format
    sample_steps = {
        "navigate": {
            "action": "navigate",
            "url": "https://example.com/products",
        },
        "click": {
            "action": "click",
            "target": {
                "selector": "button.submit-btn",
                "accessible_name": "Submit Form",
                "tag": "button",
            },
        },
        "rightclick": {
            "action": "rightclick",
            "target": {
                "selector": "div.context-menu-trigger",
                "accessible_name": "Options",
                "tag": "div",
            },
        },
        "activate": {
            "action": "activate",
            "target": {
                "selector": "a.nav-link",
                "accessible_name": "Home",
                "tag": "a",
            },
        },
        "type": {
            "action": "type",
            "value": "hello@example.com",
            "target": {
                "selector": "input#email",
                "tag": "input",
                "attributes": {"type": "email"},
            },
        },
        "keypress": {
            "action": "keypress",
            "key": "Tab",
            "modifiers": [],
            "target": {
                "selector": "input#search",
                "accessible_name": "Search products",
                "tag": "input",
            },
        },
        "hover": {
            "action": "hover",
            "target": {
                "selector": "a.dropdown-toggle",
                "accessible_name": "Menu",
                "tag": "a",
            },
        },
        "check": {
            "action": "check",
            "value": "newsletter",
            "target": {
                "selector": "input#subscribe",
                "accessible_name": "Subscribe to newsletter",
                "tag": "input",
            },
        },
        "uncheck": {
            "action": "uncheck",
            "target": {
                "selector": "input#marketing",
                "accessible_name": "Receive marketing emails",
                "tag": "input",
            },
        },
        "select": {
            "action": "select",
            "value": "nl",
            "option_text": "Netherlands",
            "target": {
                "selector": "select#country",
                "tag": "select",
            },
        },
        "scroll": {
            "action": "scroll",
            "scroll": {
                "x": 0,
                "y": 450,
                "deltaX": 0,
                "deltaY": 350,
            },
        },
        "inspekt": {
            "action": "inspekt",
            "command": "axe --level 2aa",
        },
        "radio": {
            "action": "radio",
            "value": "express",
            "target": {
                "selector": "input#shipping-express",
                "accessible_name": "Express shipping",
                "tag": "input",
            },
        },
        "plugin": {
            "action": "plugin",
            "command": "contrast-checker",
        },
        "failure": {
            "action": "failure",
            "error": "Element not found: #missing-button",
        },
    }

    # Human-readable descriptions for TTS
    action_descriptions = {
        "navigate": "Navigate to a URL",
        "click": "Mouse click on element",
        "rightclick": "Right-click for context menu",
        "activate": "Keyboard activation with Enter or Space",
        "type": "Type text into input field",
        "keypress": "Press a keyboard shortcut",
        "hover": "Hover over an element",
        "check": "Check a checkbox",
        "uncheck": "Uncheck a checkbox",
        "radio": "Select a radio button",
        "select": "Select from a dropdown",
        "scroll": "Scroll the page",
        "plugin": "Run an Inspekt plugin",
        "inspekt": "Run an Inspekt command",
        "failure": "When an action fails",
    }

    # Display simulated recording output
    click.echo()
    click.secho("  Recording started...", fg="green")
    click.echo()

    # Play start playback sound
    if cli_audio:
        cli_audio.play_start_playback()
    elif use_browser_audio:
        try:
            client.execute("""
                (function() {
                    if (window.__INSPEKT_VISUAL__) {
                        window.__INSPEKT_VISUAL__.audio.playStartPlayback();
                    }
                })()
            """, timeout=2.0)
        except Exception:
            pass
        time.sleep(0.5)

    click.echo("  " + "─" * 56)
    click.echo()

    # Show each action type (excluding 'failure' which we demo separately at the end)
    step_num = 0
    elapsed_ms = 0

    for action in all_actions:
        step_num += 1
        elapsed_ms += 1000  # Add 1 second per step

        # Get sample step data
        step_data = sample_steps.get(action, {"action": action})

        # Format and display using the shared formatting function
        display = format_step_for_display(step_data, step_num, elapsed_ms)
        click.echo(display)

        # Get description for this action
        description = action_descriptions.get(action, action)

        # Play audio for this action
        if cli_audio:
            cli_audio.play_for_action(action)
        elif use_browser_audio:
            try:
                audio_result = client.execute(
                    f"""
                    (function() {{
                        if (window.__INSPEKT_VISUAL__) {{
                            window.__INSPEKT_VISUAL__.audio.playForAction('{action}');
                            return {{ played: true, action: '{action}' }};
                        }}
                        return {{ played: false, error: 'no visual module' }};
                    }})()
                    """,
                    timeout=2.0,
                )
                # Debug: show if calls are succeeding
                if not audio_result.get("ok"):
                    click.echo(format_system_message(f"Audio call failed for {action}"))
            except Exception as e:
                click.echo(format_system_message(f"Audio play error: {e}"))

        if speak:
            # Speak the action description via browser TTS
            try:
                client.execute(
                    f"""
                    (function() {{
                        if ('speechSynthesis' in window) {{
                            window.speechSynthesis.cancel();
                            const u = new SpeechSynthesisUtterance("{description}");
                            u.rate = 1.1;
                            u.volume = 0.8;
                            window.speechSynthesis.speak(u);
                        }}
                    }})();
                    """,
                    timeout=2.0,
                )
            except Exception:
                pass

            # Wait for speech to complete
            time.sleep(1.5)
        else:
            # Show description as italic text below the action
            click.secho(f"     {description}", fg="bright_black", italic=True)
            click.echo()  # Blank line between actions

            # Pause between actions
            time.sleep(1.0)

    # Play stop playback sound
    if cli_audio:
        cli_audio.play_stop_playback()
    elif use_browser_audio:
        try:
            client.execute("""
                (function() {
                    if (window.__INSPEKT_VISUAL__) {
                        window.__INSPEKT_VISUAL__.audio.playStopPlayback();
                    }
                })()
            """, timeout=2.0)
        except Exception:
            pass
        time.sleep(0.5)

    click.echo()
    click.echo("  " + "─" * 56)
    click.secho(f"  Recording stopped. {step_num} action types demonstrated.", fg="green")
    click.echo()

    # Demonstrate failure sound (not a recorded action, but a replay outcome)
    click.echo()
    click.secho("  BONUS: Failure Sound", fg="red", bold=True)
    click.echo()
    click.echo("  When a replay step fails (element not found, timeout, etc.),")
    click.echo("  you'll hear this sound:")
    click.echo()
    time.sleep(0.5)

    # Show the failure step display (use step_num + 1 for display)
    failure_step = sample_steps.get("failure", {"action": "failure"})
    click.echo(f"  {click.style('✗', fg='red')}    00:00  {click.style('failure', fg='red')}   → Element not found: #missing-button")

    if speak:
        description = action_descriptions.get("failure", "Action failed")
        try:
            client.execute(
                f"""
                (function() {{
                    if ('speechSynthesis' in window) {{
                        window.speechSynthesis.cancel();
                        const u = new SpeechSynthesisUtterance("{description}");
                        u.rate = 1.1;
                        u.volume = 0.8;
                        window.speechSynthesis.speak(u);
                    }}
                }})();
                """,
                timeout=2.0,
            )
        except Exception:
            pass
    else:
        click.secho(f"     {action_descriptions.get('failure', 'Action failed')}", fg="bright_black", italic=True)

    # Play failure sound
    if cli_audio:
        cli_audio.play_failure()
    elif use_browser_audio:
        try:
            client.execute("""
                (function() {
                    if (window.__INSPEKT_VISUAL__) {
                        window.__INSPEKT_VISUAL__.audio.playError();
                    }
                })()
            """, timeout=2.0)
        except Exception:
            pass
        time.sleep(0.8)

    click.echo()

    # Capabilities summary with short IDs
    click.echo()
    click.secho("  KEY CAPABILITIES", fg="cyan", bold=True)
    click.echo()
    click.echo("  NAV    Track page navigations and URL changes")
    click.echo("  CLICK  Capture mouse clicks with smart selectors")
    click.echo("  KEYS   Log keyboard shortcuts (Ctrl+S, Tab, Enter)")
    click.echo("  TYPE   Record text input (passwords are masked)")
    click.echo("  FORMS  Handle checkboxes, radios, and dropdowns")
    click.echo("  SCROLL Track scroll position changes")
    click.echo("  A11Y   Compute accessible names per WCAG standards")
    click.echo()

    # Documentation reference
    click.echo("  " + "─" * 56)
    click.echo()
    click.echo("  For more information, see the documentation:")
    click.secho("    docs/guide/recording-replay.md", fg="yellow")
    click.secho("    docs/guide/recording-roadmap.md", fg="yellow")
    click.echo()
    click.echo("  Start recording with:")
    click.secho("    inspekt record", fg="green")
    click.echo()
