"""Record browser interactions to a YAML file for later replay."""

import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import click
import yaml

from inspekt.client import BridgeClient
from inspekt.domain.recording import (
    ExpectInfo,
    PositionInfo,
    Recording,
    RecordingMetadata,
    RecordingStep,
    TargetInfo,
    ViewportInfo,
)

# Save built-in open before it gets shadowed
_builtin_open = open


def get_recordings_dir() -> Path:
    """Get the default directory for storing recordings."""
    recordings_dir = Path.home() / ".inspekt" / "recordings"
    recordings_dir.mkdir(parents=True, exist_ok=True)
    return recordings_dir


def generate_filename(url: str, timestamp: datetime) -> str:
    """Generate a descriptive filename from URL and timestamp."""
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").replace(".", "_").replace(":", "_")
    path = parsed.path.strip("/").replace("/", "_")[:30] or "index"
    ts = timestamp.strftime("%Y%m%d_%H%M%S")
    return f"{domain}_{path}_{ts}.yaml"


def format_step_for_display(step: dict) -> str:
    """Format a step for real-time terminal display."""
    action = step.get("action", "unknown")
    target = step.get("target", {})
    selector = target.get("selector", "") if target else ""
    accessible_name = target.get("accessible_name", "") if target else ""

    if action == "navigate":
        url = step.get("url", "")
        # Truncate long URLs
        if len(url) > 60:
            url = url[:57] + "..."
        return f"  navigate: {url}"

    elif action == "click":
        name = accessible_name or target.get("text", "")[:30] if target else ""
        if name:
            return f"  click: {selector[:40]} \"{name}\""
        return f"  click: {selector[:50]}"

    elif action == "type":
        value = step.get("value", "")
        if step.get("sensitive"):
            return f"  type: {selector[:40]} (password)"
        char_count = len(value)
        return f"  type: {selector[:40]} ({char_count} chars)"

    elif action == "keypress":
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])
        if modifiers:
            key_str = "+".join(modifiers) + "+" + key
        else:
            key_str = key
        return f"  keypress: {key_str}"

    elif action == "hover":
        name = accessible_name or target.get("text", "")[:30] if target else ""
        if name:
            return f"  hover: {selector[:40]} \"{name}\""
        return f"  hover: {selector[:50]}"

    elif action == "inspekt":
        cmd = step.get("command", "")
        return f"  inspekt: {cmd}"

    return f"  {action}: {json.dumps(step)[:50]}"


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

    # Build position info if present
    position = None
    if event.get("position"):
        p = event["position"]
        position = PositionInfo(
            x=p.get("x", 0),
            y=p.get("y", 0),
            viewport_relative=p.get("viewport_relative", True),
        )

    return RecordingStep(
        timestamp=timestamp,
        action=action,
        url=event.get("url"),
        target=target,
        position=position,
        value=event.get("value"),
        sensitive=event.get("sensitive", False),
        key=event.get("key"),
        modifiers=event.get("modifiers", []),
        command=event.get("command"),
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

    with _builtin_open(filepath, "w") as f:
        f.write(header)
        yaml.dump(
            data,
            f,
            Dumper=RecordingYAMLDumper,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        )


@click.command()
@click.argument("output", required=False, default=None)
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
def record(
    output: Optional[str],
    include_hover: bool,
    mask_passwords: bool,
    min_hover_duration: int,
):
    """
    Record browser interactions to a YAML file.

    Starts recording all user actions on the currently open browser page.
    Press Ctrl+C to stop recording and save the file.

    The recording can later be replayed with 'inspekt replay' and edited
    to add assertions for automated testing.

    \b
    Examples:
        inspekt record                    # Auto-generates filename
        inspekt record login-flow.yaml    # Specific filename
        inspekt record --no-hover         # Skip hover events
    """
    client = BridgeClient()

    if not client.is_alive():
        click.echo(
            "Error: Bridge server is not running. Start it with: inspekt start",
            err=True,
        )
        sys.exit(1)

    # Load the recording script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "record_events.js"

    try:
        with _builtin_open(script_path) as f:
            script_template = f.read()
    except FileNotFoundError:
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    # Configuration for the browser script
    config = {
        "includeHover": include_hover,
        "maskPasswords": mask_passwords,
        "minHoverDuration": min_hover_duration,
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

        click.echo(f"Recording: {start_url}")
        click.echo("Press Ctrl+C to stop and save\n")

        # Prepare poll and stop codes
        poll_code = script_template.replace("ACTION_PLACEHOLDER", "poll")
        poll_code = poll_code.replace("CONFIG_PLACEHOLDER", config_json)

        stop_code = script_template.replace("ACTION_PLACEHOLDER", "stop")
        stop_code = stop_code.replace("CONFIG_PLACEHOLDER", config_json)

        # Collected steps
        all_steps: list[RecordingStep] = []

        # Signal handler for Ctrl+C
        def stop_recording(sig, frame):
            nonlocal all_steps

            click.echo("\n\nStopping recording...")

            try:
                # Stop recording and get final events
                stop_result = client.execute(stop_code, timeout=5.0)

                if stop_result.get("ok"):
                    stop_response = stop_result.get("result", {})
                    final_events = stop_response.get("events", [])
                    duration_ms = stop_response.get("duration", 0)

                    # Convert remaining events
                    for event in final_events:
                        # Skip if we already have this event (by timestamp)
                        if not any(s.timestamp == event.get("timestamp") for s in all_steps):
                            step = convert_js_event_to_step(event)
                            all_steps.append(step)
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
                click.echo(f"\nRecording saved to: {output_path}")
                click.echo(f"Duration: {duration_ms / 1000:.1f}s | Steps: {len(all_steps)}")
            except Exception as e:
                click.echo(f"Error saving recording: {e}", err=True)
                sys.exit(1)

            sys.exit(0)

        signal.signal(signal.SIGINT, stop_recording)

        # Main polling loop
        while True:
            try:
                result = client.execute(poll_code, timeout=2.0)

                if result.get("ok"):
                    response = result.get("result", {})
                    events = response.get("events", [])

                    for event in events:
                        step = convert_js_event_to_step(event)
                        all_steps.append(step)

                        # Display real-time feedback
                        display = format_step_for_display(event)
                        click.echo(display)

            except Exception as e:
                # Silently ignore polling errors, continue recording
                pass

            time.sleep(0.1)  # Poll every 100ms

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)
