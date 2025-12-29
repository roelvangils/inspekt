"""Record browser interactions to a YAML file for later replay."""

import json
import re
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

from inspekt.app.cli.icons import success as success_icon, get_indicator, get_action_icon
from inspekt.app.cli.interaction import _focus_browser_if_requested
from inspekt.client import BridgeClient
from inspekt.config import get_audio_config, get_record_config
from inspekt.services.audio import CLIAudio
from inspekt.domain.recording import (
    DownloadInfo,
    ExpectInfo,
    FileInfo,
    Recording,
    RecordedOn,
    RecordingMetadata,
    RecordingStep,
    ScrollInfo,
    ScrollPosition,
    StateInfo,
    TargetInfo,
    ViewportInfo,
)
from .formatting import (
    format_duration,
    format_elapsed,
    format_step_for_display,
    format_step_header,
    format_steps_preview,
    format_system_message,
    get_recordings_dir,
)
from .table import Table
from .recording_utils import clean_filename, find_most_recent_recording, complete_recording_files, TerminalEchoSuppressor
from inspekt.app.cli.output import OutputHandler
from inspekt.shared.dialog_styles import DIALOG_STYLES

import requests


class SubcommandAwareGroup(click.Group):
    """
    Custom Click Group that handles optional positional arguments alongside subcommands.

    When the first positional argument matches a subcommand name (without .yaml/.yml extension),
    treat it as a subcommand invocation rather than consuming it as the 'filename' argument.

    This allows both:
    - `inspekt record tutorial` → runs tutorial subcommand
    - `inspekt record tutorial.yaml` → records to file tutorial.yaml
    - `inspekt record show file.yaml` → runs show subcommand with file.yaml arg
    """

    def make_context(self, info_name, args, parent=None, **extra):
        """
        Override to detect subcommand names before the optional filename argument consumes them.

        We check if the first non-option arg matches a subcommand. If so, we temporarily remove
        the filename parameter to prevent it from consuming the subcommand name.
        """
        # Find first non-option argument
        first_positional_idx = None
        for i, arg in enumerate(args):
            if not arg.startswith('-'):
                first_positional_idx = i
                break

        if first_positional_idx is not None:
            first_arg = args[first_positional_idx]
            first_arg_lower = first_arg.lower()
            has_yaml_ext = first_arg_lower.endswith('.yaml') or first_arg_lower.endswith('.yml')

            # If matches a subcommand and doesn't have yaml extension, skip filename param
            if not has_yaml_ext and first_arg in self.commands:
                # Temporarily remove the 'filename' parameter so it doesn't consume this arg
                original_params = self.params
                self.params = [p for p in self.params if p.name != 'filename']
                try:
                    ctx = super().make_context(info_name, args, parent=parent, **extra)
                    # Set filename to None in the context params
                    ctx.params['filename'] = None
                    return ctx
                finally:
                    # Restore original params
                    self.params = original_params

        return super().make_context(info_name, args, parent=parent, **extra)


# Bridge server constants
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765

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


def set_vm_terminal_hidden(hidden: bool) -> None:
    """Signal the VM control panel to hide/show the terminal overlay.

    In VM mode (INSPEKT_ISOLATED=1), the control panel has a web terminal overlay
    that may cover the browser viewport. When recording starts, we hide it so
    the user can immediately interact with the browser. When recording stops,
    we show it again.

    This function does nothing on macOS/normal mode where AppleScript handles
    browser focus instead.

    Args:
        hidden: True to hide terminal, False to show it
    """
    from inspekt.config import is_isolated_mode
    if not is_isolated_mode():
        return  # Only in VM mode

    import urllib.request

    try:
        # Control server runs on port 8888 in VM
        req = urllib.request.Request(
            'http://localhost:8888/ui/terminal-state',
            data=json.dumps({'hidden': hidden}).encode(),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            pass  # We don't need the response

        # Also focus Chrome when hiding terminal (recording starting)
        if hidden:
            urllib.request.urlopen('http://localhost:8888/chrome', timeout=2)
    except Exception:
        pass  # Terminal control is optional - don't fail recording


# =============================================================================
# Pre-recording hints and warnings
# =============================================================================


def _format_closed_shadow_warning(warnings: list) -> str:
    """Format warning message for closed shadow DOM components."""
    lines = []
    lines.append(click.style("⚠ Warning: ", fg="yellow", bold=True) + "This page contains Web Components with closed shadow DOM.")
    lines.append("  Interactions inside these components may not be recorded:")
    for warning in warnings[:5]:
        tag = warning.get("tagName", "unknown")
        lines.append(f"    • {click.style(f'<{tag}>', fg='cyan')}")
    if len(warnings) > 5:
        lines.append(f"    ... and {len(warnings) - 5} more")
    return "\n".join(lines)


def _format_media_hint(media_elements: dict) -> str:
    """Format hint message for media elements."""
    from inspekt.app.cli.table import wrap_text, _style_with_inline_code

    audio_count = media_elements.get("audioCount", 0)
    video_count = media_elements.get("videoCount", 0)

    parts = []
    if audio_count > 0:
        parts.append("an audio player" if audio_count == 1 else f"{audio_count} audio players")
    if video_count > 0:
        parts.append("a video player" if video_count == 1 else f"{video_count} video players")
    element_desc = " and ".join(parts)

    msg = f"This page contains {element_desc} with native controls. Media players are treated as a single `Tab` stop. Use `Space`/`Enter` to play/pause, `Arrow keys` for seek/volume."
    # Lightbulb icon: \uf400 (nf-oct-light_bulb)
    wrapped = wrap_text(msg, indent="", subsequent_indent="  ")
    return click.style("\uf400 ", fg="blue", bold=True) + _style_with_inline_code(wrapped, base_fg="blue")


def _format_native_inputs_hint(native_inputs: dict) -> str:
    """Format hint message for native control inputs."""
    from inspekt.app.cli.table import wrap_text, _style_with_inline_code

    types = native_inputs.get("types", {})
    type_names = {
        "range": "range slider",
        "date": "date picker",
        "time": "time picker",
        "datetime-local": "datetime picker",
        "month": "month picker",
        "week": "week picker",
        "number": "number spinner",
        "color": "color picker"
    }

    type_parts = []
    for input_type, input_count in sorted(types.items()):
        name = type_names.get(input_type, input_type)
        if input_count == 1:
            article = "an" if name[0] in "aeiou" else "a"
            type_parts.append(f"{article} {name}")
        else:
            type_parts.append(f"{input_count} {name}s")

    if len(type_parts) <= 2:
        type_desc = " and ".join(type_parts)
    else:
        type_desc = ", ".join(type_parts[:-1]) + " and " + type_parts[-1]

    total_count = sum(types.values())
    pronoun = "its" if total_count == 1 else "their"
    msg = f"This page has {type_desc}. You can adjust {pronoun} values, but Inspekt intentionally does not record user interactions on native elements. The final selected value will be recorded once you leave the element."
    # Lightbulb icon: \uf400 (nf-oct-light_bulb)
    wrapped = wrap_text(msg, indent="", subsequent_indent="  ")
    return click.style("\uf400 ", fg="blue", bold=True) + _style_with_inline_code(wrapped, base_fg="blue")


def _format_file_inputs_warning(file_inputs: dict) -> str:
    """Format warning message for file inputs."""
    from inspekt.app.cli.table import wrap_text, _style_with_inline_code

    count = file_inputs.get("count", 0)
    count_str = "a file input" if count == 1 else f"{count} file inputs"
    msg = f"This page has {count_str}. Inspekt cannot access the file picker or view files on your computer, but it will record file uploads and save the files for replay (maximum size: `10 MB`). Do not upload sensitive files."
    wrapped = wrap_text(msg, indent="", subsequent_indent="           ")
    return click.style("⚠ Warning: ", fg="yellow", bold=True) + _style_with_inline_code(wrapped, base_fg="yellow")


def _format_js_dialogs_hint(js_dialogs: dict) -> str:
    """Format hint message for JavaScript dialogs."""
    from inspekt.app.cli.table import wrap_text

    msg = (
        "This page may display native JavaScript dialogs. "
        "By default, native dialogs appear during recording. "
        "To interact with synthetic dialogs while recording, use "
        "`inspekt record --synthetic-dialogs`. "
        "During playback, Inspekt always replaces these with synthetic "
        "dialogs that behave identically."
    )
    # Lightbulb icon: \uf400 (nf-oct-light_bulb)
    from inspekt.app.cli.table import _style_with_inline_code
    wrapped = wrap_text(msg, indent="", subsequent_indent="  ")
    return click.style("\uf400 ", fg="blue", bold=True) + _style_with_inline_code(wrapped, base_fg="blue")


def _format_fullscreen_hint(window_mode: dict) -> str:
    """Format hint message for fullscreen/kiosk mode recording."""
    from inspekt.app.cli.table import wrap_text, _style_with_inline_code

    mode = window_mode.get("mode", "fullscreen")
    if mode == "kiosk":
        msg = (
            "Browser is in kiosk mode (viewport fills entire screen). "
            "Window resizing is disabled. Recording will proceed with current dimensions. "
            "Replay will require the same kiosk configuration or a matching viewport size."
        )
    else:
        msg = (
            "Browser is in fullscreen mode (`F11`). Window resizing is disabled. "
            "Recording will proceed with current dimensions. "
            "Exit fullscreen (press `F11` or `Esc`) if you need to resize the viewport."
        )

    # Lightbulb icon: \uf400 (nf-oct-light_bulb)
    wrapped = wrap_text(msg, indent="", subsequent_indent="  ")
    return click.style("\uf400 ", fg="blue", bold=True) + _style_with_inline_code(wrapped, base_fg="blue")


def display_pre_recording_hints(response: dict, synthetic_dialogs: bool = False) -> None:
    """Display all pre-recording hints and warnings based on page analysis.

    Shows warnings (yellow) for potential issues and hints (blue) for
    informational messages about page features.

    Args:
        response: The start response from the recording script
        synthetic_dialogs: Whether --synthetic-dialogs flag is enabled
    """
    messages = []

    # Warnings (yellow) - potential issues
    closed_shadow_warnings = response.get("closedShadowWarnings", [])
    if closed_shadow_warnings:
        messages.append(_format_closed_shadow_warning(closed_shadow_warnings))

    file_inputs = response.get("fileInputs")
    if file_inputs:
        messages.append(_format_file_inputs_warning(file_inputs))

    # Hints (blue) - informational
    media_elements = response.get("mediaElements")
    if media_elements:
        messages.append(_format_media_hint(media_elements))

    native_inputs = response.get("nativeControlInputs")
    if native_inputs:
        messages.append(_format_native_inputs_hint(native_inputs))

    js_dialogs = response.get("jsDialogs")
    if js_dialogs and not synthetic_dialogs:
        messages.append(_format_js_dialogs_hint(js_dialogs))

    window_mode = response.get("windowMode")
    if window_mode and window_mode.get("mode") in ("fullscreen", "kiosk"):
        messages.append(_format_fullscreen_hint(window_mode))

    # Display all messages
    for msg in messages:
        click.echo()
        click.echo(msg)


def generate_filename(url: str, timestamp: datetime) -> str:
    """Generate a descriptive filename from URL and timestamp.

    Format: inspekt_{timestamp}_{domain}_{path}.yaml
    The timestamp is converted to local time for user-friendly filenames.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "").replace(".", "_").replace(":", "_")
    path = parsed.path.strip("/").replace("/", "_")[:30] or "index"
    # Convert to local time for the filename
    local_timestamp = timestamp.astimezone()
    ts = local_timestamp.strftime("%Y%m%d_%H%M%S")
    return f"inspekt_{ts}_{domain}_{path}.yaml"


def compute_file_checksum(file_path: Path) -> str | None:
    """Compute SHA256 checksum of a file.

    Uses chunked reading for memory efficiency with large files.

    Args:
        file_path: Path to the file to checksum

    Returns:
        SHA256 hex digest string, or None if file doesn't exist
    """
    import hashlib

    if not file_path.exists():
        return None

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


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
            input_type=t.get("input_type"),
            focus_styles=t.get("focus_styles"),  # Captured styles for sr-only elements
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

    # Build files list for upload actions
    files = None
    if event.get("files"):
        files = [
            FileInfo(
                name=f.get("name", "unknown"),
                type=f.get("type", "application/octet-stream"),
                size=f.get("size", 0),
                lastModified=f.get("lastModified"),
                content=f.get("content"),
                external_path=f.get("external_path"),
            )
            for f in event["files"]
        ]

    # Build download info for download actions
    download = None
    if event.get("download"):
        d = event["download"]
        download = DownloadInfo(
            filename=d.get("filename", "unknown"),
            url=d.get("url", ""),
            mime_type=d.get("mime_type", "application/octet-stream"),
            size=d.get("size", 0),
            download_start=d.get("download_start", 0),
            download_end=d.get("download_end", 0),
            full_path=d.get("full_path"),  # Chrome's download location for copying
            content=d.get("content"),
            external_path=d.get("external_path"),
            referrer=d.get("referrer"),
            download_id=d.get("download_id"),
        )
        # Pass through internal tracking fields (for checksum-based deduplication)
        # These are not Pydantic fields but are accessed via __dict__ in process_download_files()
        if d.get("_duplicate_of_step") is not None:
            download.__dict__["_duplicate_of_step"] = d["_duplicate_of_step"]
        if d.get("_differs_from_step") is not None:
            download.__dict__["_differs_from_step"] = d["_differs_from_step"]
        if d.get("_save_with_step_id") is not None:
            download.__dict__["_save_with_step_id"] = d["_save_with_step_id"]

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
        files=files,
        download=download,
        # jsdialog fields (for alert, confirm, prompt)
        dialog_type=event.get("dialog_type"),
        message=event.get("message"),
        default_value=event.get("default_value"),
        result=event.get("result"),
        duration=event.get("duration"),
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


def _truncate(text: str, max_len: int = 40) -> str:
    """Truncate text with ellipsis if too long.

    Also collapses whitespace (including newlines) to ensure
    the result is safe for single-line YAML comments.
    """
    # Collapse all whitespace (including newlines) to single spaces
    text = " ".join(text.split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def _describe_target(target: dict) -> str:
    """Generate human-readable target description.

    Prioritizes: accessible_name > text > selector
    Uses tag/role for context (link, button, input, etc.)
    """
    if not target:
        return "element"

    name = target.get("accessible_name") or target.get("text")
    tag = target.get("tag", "element")
    role = target.get("role")

    # Normalize whitespace in name (collapse newlines and multiple spaces)
    if name:
        name = " ".join(name.split())

    if name:
        name = _truncate(name, 30)
        if tag == "a":
            return f"link '{name}'"
        elif tag == "button":
            return f"button '{name}'"
        elif tag == "input":
            input_type = target.get("attributes", {}).get("type", "text")
            return f"{input_type} input '{name}'"
        elif tag == "select":
            return f"dropdown '{name}'"
        elif tag == "textarea":
            return f"text area '{name}'"
        elif role:
            return f"{role} '{name}'"
        else:
            return f"{tag} '{name}'"
    else:
        selector = target.get("selector", "")
        if selector:
            return f"'{_truncate(selector, 35)}'"
        return "element"


def _describe_assertion(expect: dict) -> str:
    """Generate assertion suffix for step comment.

    Returns a suffix string like "and wait for '.modal' to appear"
    or empty string if no meaningful assertion.
    """
    if not expect:
        return ""

    # If there's a custom message, use that
    if expect.get("message"):
        return f" — {_truncate(expect['message'], 50)}"

    parts = []

    # Visibility assertions (most common)
    if expect.get("visible"):
        parts.append(f"wait for '{_truncate(expect['visible'], 25)}' to appear")
    if expect.get("hidden"):
        parts.append(f"wait for '{_truncate(expect['hidden'], 25)}' to disappear")

    # Text/URL assertions
    if expect.get("text_contains"):
        parts.append(f"check page contains '{_truncate(expect['text_contains'], 20)}'")
    if expect.get("url_contains"):
        parts.append(f"check URL contains '{_truncate(expect['url_contains'], 20)}'")

    # Element state assertions
    if expect.get("checked"):
        parts.append(f"verify '{_truncate(expect['checked'], 20)}' is checked")
    if expect.get("unchecked"):
        parts.append(f"verify '{_truncate(expect['unchecked'], 20)}' is unchecked")
    if expect.get("focused"):
        parts.append("verify element has focus")
    if expect.get("value_equals") is not None:
        parts.append(f"verify value equals '{_truncate(str(expect['value_equals']), 15)}'")
    if expect.get("disabled"):
        parts.append(f"verify '{_truncate(expect['disabled'], 20)}' is disabled")

    # Count assertions
    if expect.get("count") and expect.get("count_equals") is not None:
        parts.append(f"verify {expect['count_equals']} elements match '{_truncate(expect['count'], 20)}'")

    # Inspekt-specific assertions
    if expect.get("allowed_violations") is not None or expect.get("allowed-violations") is not None:
        violations = expect.get("allowed_violations") or expect.get("allowed-violations") or 0
        return f" ({violations} violations allowed)"
    if expect.get("empty"):
        return " (expect no messages)"

    if parts:
        # Join with "and" if multiple, but limit to most important
        return " and " + parts[0]

    return ""


def _describe_condition(skip_if: dict = None, wait_for: dict = None) -> str:
    """Generate condition context for step comment.

    Returns prefix/suffix for skip_if or wait_for conditions.
    """
    parts = []

    if skip_if:
        if skip_if.get("visible"):
            parts.append(f"skip if '{_truncate(skip_if['visible'], 20)}' visible")
        elif skip_if.get("hidden"):
            parts.append(f"skip if '{_truncate(skip_if['hidden'], 20)}' hidden")
        elif skip_if.get("text_contains"):
            parts.append(f"skip if page contains '{_truncate(skip_if['text_contains'], 15)}'")

    if wait_for:
        if wait_for.get("visible"):
            parts.append(f"after waiting for '{_truncate(wait_for['visible'], 20)}'")
        elif wait_for.get("hidden"):
            parts.append(f"after '{_truncate(wait_for['hidden'], 20)}' disappears")
        elif wait_for.get("text_contains"):
            parts.append(f"after '{_truncate(wait_for['text_contains'], 15)}' appears")

    if parts:
        return " (" + ", ".join(parts) + ")"
    return ""


def construct_step_comment(step_num: int, step: dict, include_assertions: bool = True) -> str:
    """Generate a human-readable YAML comment for a recording step.

    Args:
        step_num: Step number (1-indexed)
        step: Step dictionary with action, target, expect, etc.
        include_assertions: Whether to include expect/skip_if/wait_for in comment.
            Set to False to generate "base" comment for comparison.

    Returns:
        Comment string like "# Step 001 · Click on button 'Submit'"
    """
    action = step.get("action", "unknown")
    target = step.get("target", {})
    expect = step.get("expect", {}) if include_assertions else {}
    skip_if = step.get("skip_if", {}) if include_assertions else {}
    wait_for = step.get("wait_for", {}) if include_assertions else {}

    # Start with step number
    prefix = f"# Step {step_num:04d} · "

    # Build action description based on type
    if action == "navigate":
        url = step.get("url", "")
        display_url = _truncate(url, 55)
        description = f"Navigate to {display_url}"

    elif action == "click":
        description = f"Click on {_describe_target(target)}"

    elif action == "rightclick":
        description = f"Right-click on {_describe_target(target)}"

    elif action == "activate":
        description = f"Activate {_describe_target(target)} via keyboard"

    elif action == "type":
        value = step.get("value", "")
        sensitive = step.get("sensitive", False)
        target_desc = _describe_target(target)

        if sensitive:
            description = f"Type password into {target_desc}"
        elif value:
            display_value = _truncate(value, 25)
            description = f"Type '{display_value}' into {target_desc}"
        else:
            description = f"Type into {target_desc}"

    elif action == "keypress":
        key = step.get("key", "")
        modifiers = step.get("modifiers", [])

        if modifiers:
            key_combo = "+".join(modifiers) + "+" + key
        else:
            key_combo = key

        # Add context for common keys
        if key == "Tab":
            accessible_name = target.get("accessible_name", "") if target else ""
            if accessible_name:
                description = f"Press {key_combo} (focus moves to '{_truncate(accessible_name, 25)}')"
            else:
                description = f"Press {key_combo}"
        elif key == "Enter":
            description = f"Press {key_combo} to submit"
        elif key == "Escape":
            description = f"Press {key_combo} to close"
        else:
            description = f"Press {key_combo}"

    elif action == "hover":
        description = f"Hover over {_describe_target(target)}"

    elif action == "check":
        value = step.get("value", "")
        name = target.get("accessible_name") or target.get("text") if target else ""
        if value:
            description = f"Check '{_truncate(value, 30)}'"
        elif name:
            description = f"Check checkbox '{_truncate(name, 30)}'"
        else:
            description = f"Check {_describe_target(target)}"

    elif action == "uncheck":
        name = target.get("accessible_name") or target.get("text") if target else ""
        if name:
            description = f"Uncheck checkbox '{_truncate(name, 30)}'"
        else:
            description = f"Uncheck {_describe_target(target)}"

    elif action == "radio":
        value = step.get("value", "")
        if value:
            description = f"Select radio option '{_truncate(value, 30)}'"
        else:
            description = f"Select {_describe_target(target)}"

    elif action == "select":
        option_text = step.get("option_text", "")
        value = step.get("value", "")
        display_option = option_text or value

        if display_option:
            target_desc = _describe_target(target)
            description = f"Select '{_truncate(display_option, 25)}' from {target_desc}"
        else:
            description = f"Select from {_describe_target(target)}"

    elif action == "scroll":
        scroll = step.get("scroll", {})
        delta_y = scroll.get("deltaY", 0)
        delta_x = scroll.get("deltaX", 0)

        if delta_y > 0:
            description = f"Scroll down {delta_y}px"
        elif delta_y < 0:
            description = f"Scroll up {abs(delta_y)}px"
        elif delta_x != 0:
            direction = "right" if delta_x > 0 else "left"
            description = f"Scroll {direction} {abs(delta_x)}px"
        else:
            x, y = scroll.get("x", 0), scroll.get("y", 0)
            description = f"Scroll to position ({x}, {y})"

    elif action == "inspekt":
        command = step.get("command", "")
        description = f"Run 'inspekt {command}'"

    elif action == "plugin":
        command = step.get("command", "")
        description = f"Run plugin: {command}"

    elif action == "jsdialog":
        dialog_type = step.get("dialog_type", "alert")
        message = step.get("message", "")
        result = step.get("result")

        if dialog_type == "alert":
            if message:
                description = f"Alert: '{_truncate(message, 40)}'"
            else:
                description = "Alert dialog"
        elif dialog_type == "confirm":
            result_text = "OK" if result else "Cancel"
            if message:
                description = f"Confirm: '{_truncate(message, 35)}' → {result_text}"
            else:
                description = f"Confirm dialog → {result_text}"
        elif dialog_type == "prompt":
            result_text = f"'{_truncate(str(result), 20)}'" if result else "Cancel"
            if message:
                description = f"Prompt: '{_truncate(message, 30)}' → {result_text}"
            else:
                description = f"Prompt dialog → {result_text}"
        else:
            description = f"JavaScript dialog ({dialog_type})"

    else:
        description = f"{action}"

    # Add assertion context
    assertion_suffix = _describe_assertion(expect)

    # Add condition context
    condition_suffix = _describe_condition(skip_if, wait_for)

    return prefix + description + assertion_suffix + condition_suffix


def _extract_comment_description(comment: str) -> str:
    """Extract the description part after 'Step XXX · '.

    Args:
        comment: Full comment like "# Step 001 · Click on button 'Submit'"

    Returns:
        Just the description: "Click on button 'Submit'"
    """
    match = re.match(r'^#\s*Step\s+\d+\s*·\s*(.*)$', comment)
    return match.group(1).strip() if match else comment.lstrip("# ").strip()


def _detect_fragile_selectors(steps: list) -> list:
    """Detect potentially fragile CSS selectors in recording steps.

    Returns list of (step_num, selector, reason) tuples.
    """
    warnings = []

    # Patterns that indicate fragile selectors
    fragile_patterns = [
        # Auto-generated IDs from frameworks
        (r'#react-select-\d+', "React Select auto-generated ID"),
        (r'#ember\d+', "Ember.js auto-generated ID"),
        (r'#ng-\w+-\d+', "Angular auto-generated ID"),
        (r'#radix-', "Radix UI auto-generated ID"),
        (r'#headlessui-', "Headless UI auto-generated ID"),
        (r'#__next', "Next.js internal ID"),
        (r'#__nuxt', "Nuxt.js internal ID"),
        # Index-based selectors (fragile when content changes)
        (r':nth-child\(\d+\)', "Index-based selector (:nth-child)"),
        (r':nth-of-type\(\d+\)', "Index-based selector (:nth-of-type)"),
    ]

    for i, step in enumerate(steps):
        step_num = i + 1
        target = step.get("target", {})
        selector = target.get("selector", "")

        if not selector:
            continue

        # Check for fragile patterns
        found_pattern = False
        for pattern, reason in fragile_patterns:
            if re.search(pattern, selector):
                warnings.append((step_num, selector, reason))
                found_pattern = True
                break  # One warning per selector

        # Check for overly long CSS paths (> 5 levels deep) - skip if already warned
        if not found_pattern and (selector.count(" > ") >= 5 or selector.count(" ") >= 6):
            warnings.append((step_num, selector, "Long CSS path (may break if DOM structure changes)"))

    return warnings


def _validate_timestamps(steps: list) -> list:
    """Validate that timestamps are in ascending order.

    Returns list of (step_num, timestamp, prev_timestamp, issue) tuples.
    """
    warnings = []
    prev_timestamp = -1

    for i, step in enumerate(steps):
        step_num = i + 1
        timestamp = step.get("timestamp", 0)

        if timestamp < prev_timestamp:
            warnings.append((step_num, timestamp, prev_timestamp, "out of order"))

        prev_timestamp = timestamp

    return warnings


def _normalize_step_keys(step: dict) -> dict:
    """Normalize key order in a step dictionary.

    Preferred order: timestamp, action, url, target, value, key, modifiers,
    scroll, click_at, expect, skip_if, wait_for
    """
    key_order = [
        "timestamp",
        "action",
        "url",
        "target",
        "value",
        "sensitive",
        "key",
        "modifiers",
        "scroll",
        "click_at",
        "command",
        "expect",
        "skip_if",
        "wait_for",
    ]

    # Start with ordered keys
    ordered = {}
    for key in key_order:
        if key in step:
            ordered[key] = step[key]

    # Add any remaining keys not in the order list
    for key in step:
        if key not in ordered:
            ordered[key] = step[key]

    return ordered


def _normalize_target_keys(target: dict) -> dict:
    """Normalize key order in a target dictionary."""
    key_order = [
        "selector",
        "fallback_selectors",
        "text",
        "accessible_name",
        "tag",
        "role",
    ]

    ordered = {}
    for key in key_order:
        if key in target:
            ordered[key] = target[key]

    for key in target:
        if key not in ordered:
            ordered[key] = target[key]

    return ordered


def _clean_empty_values(data: dict) -> dict:
    """Recursively remove empty/null values from a dictionary."""
    if isinstance(data, dict):
        return {
            k: _clean_empty_values(v)
            for k, v in data.items()
            if v is not None and v != [] and v != {} and v != ""
        }
    elif isinstance(data, list):
        return [_clean_empty_values(item) for item in data if item is not None]
    return data


def tidy_recording(
    filepath: Path,
    dry_run: bool = False,
    force_comments: bool = False,
    skip_comments: bool = False,
    skip_normalize: bool = False,
    skip_clean: bool = False,
) -> dict:
    """Tidy up a recording file comprehensively.

    Operations performed:
    1. Validate YAML syntax (abort if invalid)
    2. Detect fragile selectors (warnings only)
    3. Validate timestamp order (warnings only)
    4. Re-number steps sequentially
    5. Enrich comments with assertion info (preserving customizations)
    6. Normalize key order for consistency
    7. Remove empty/null values
    8. Re-serialize with proper indentation

    Args:
        filepath: Path to the recording YAML file
        dry_run: If True, show changes without modifying file
        force_comments: If True, replace ALL comments (ignore user customizations)
        skip_comments: If True, skip comment updates
        skip_normalize: If True, skip key order normalization
        skip_clean: If True, skip empty value removal

    Returns:
        Dict with report: {
            stats: {...},
            comment_changes: [...],
            warnings: {fragile_selectors: [...], timestamps: [...]},
            operations: {...}
        }
    """
    # Read the file
    with _builtin_open(filepath, "r") as f:
        content = f.read()

    # 1. Validate YAML syntax
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML syntax: {e}")

    if not data or "steps" not in data:
        raise ValueError(f"Invalid recording file: missing 'steps' section")

    steps = data["steps"]
    if not steps:
        raise ValueError(f"Invalid recording file: no steps found")

    # Initialize report
    report = {
        "stats": {
            "total_steps": len(steps),
            "comments_enriched": 0,
            "comments_preserved": 0,
            "comments_forced": 0,
            "steps_renumbered": 0,
            "keys_normalized": 0,
            "empty_values_removed": 0,
        },
        "comment_changes": [],
        "warnings": {
            "fragile_selectors": [],
            "timestamps": [],
        },
        "operations": {
            "yaml_validated": True,
            "comments_updated": not skip_comments,
            "keys_normalized": not skip_normalize,
            "empty_cleaned": not skip_clean,
        },
    }

    # 2. Detect fragile selectors (warnings only)
    report["warnings"]["fragile_selectors"] = _detect_fragile_selectors(steps)

    # 3. Validate timestamps (warnings only)
    report["warnings"]["timestamps"] = _validate_timestamps(steps)

    # Parse into Recording model for comment generation
    recording = Recording(**data)

    # 4-7. Process the file - we need to handle comments AND structure
    # Read original comments from file
    lines = content.split("\n")
    original_comments = {}  # step_index -> comment text

    step_index = 0
    in_steps_section = False
    for line in lines:
        if line.strip() == "steps:":
            in_steps_section = True
            continue
        if in_steps_section and line.strip() and not line.startswith(" ") and not line.startswith("-") and not line.startswith("#"):
            in_steps_section = False
        if in_steps_section and line.strip().startswith("# Step"):
            original_comments[step_index] = line.strip()
            step_index += 1

    # Process steps
    new_steps = []
    for i, step in enumerate(steps):
        step_num = i + 1
        step_dict = step.copy()

        # Normalize target keys if present
        if not skip_normalize and "target" in step_dict:
            step_dict["target"] = _normalize_target_keys(step_dict["target"])
            report["stats"]["keys_normalized"] += 1

        # Normalize step keys
        if not skip_normalize:
            step_dict = _normalize_step_keys(step_dict)

        # Clean empty values
        if not skip_clean:
            original_len = len(str(step_dict))
            step_dict = _clean_empty_values(step_dict)
            if len(str(step_dict)) < original_len:
                report["stats"]["empty_values_removed"] += 1

        new_steps.append(step_dict)

    # Generate new comments
    new_comments = {}
    if not skip_comments:
        for i, step in enumerate(new_steps):
            step_num = i + 1
            existing_comment = original_comments.get(i, "")
            existing_desc = _extract_comment_description(existing_comment) if existing_comment else ""

            # Get step from recording model for proper comment generation
            rec_step = recording.steps[i]
            step_model_dict = rec_step.model_dump(exclude_none=True)

            # Generate base comment (without assertions) for comparison
            base_comment = construct_step_comment(step_num, step_model_dict, include_assertions=False)
            base_desc = _extract_comment_description(base_comment)

            # Generate full comment (with assertions)
            full_comment = construct_step_comment(step_num, step_model_dict, include_assertions=True)
            full_desc = _extract_comment_description(full_comment)

            # Decide what to do
            if force_comments:
                new_comments[i] = full_comment
                if existing_desc and existing_desc != full_desc:
                    report["stats"]["comments_forced"] += 1
                    report["comment_changes"].append({
                        "step": step_num,
                        "old": existing_desc,
                        "new": full_desc,
                        "type": "forced",
                    })
            elif not existing_desc or existing_desc == base_desc:
                # No existing comment or user hasn't customized → use full comment
                new_comments[i] = full_comment
                if existing_desc and full_desc != base_desc:
                    report["stats"]["comments_enriched"] += 1
                    report["comment_changes"].append({
                        "step": step_num,
                        "old": existing_desc,
                        "new": full_desc,
                        "type": "enriched",
                    })
            else:
                # User has customized → preserve but update step number
                new_comments[i] = f"# Step {step_num:04d} · {existing_desc}"
                report["stats"]["comments_preserved"] += 1
                report["comment_changes"].append({
                    "step": step_num,
                    "old": existing_desc,
                    "new": existing_desc,
                    "type": "preserved",
                })

            # Check for renumbering
            if existing_comment:
                old_num_match = re.match(r'^#\s*Step\s+(\d+)', existing_comment)
                if old_num_match:
                    old_num = int(old_num_match.group(1))
                    if old_num != step_num:
                        report["stats"]["steps_renumbered"] += 1

    # Build new data structure
    new_data = {}

    # Preserve header comments by keeping metadata order
    key_order = ["steps", "metadata", "state", "preconditions", "replay"]
    for key in key_order:
        if key == "steps":
            new_data["steps"] = new_steps
        elif key in data:
            if not skip_clean:
                new_data[key] = _clean_empty_values(data[key])
            else:
                new_data[key] = data[key]

    # Add any remaining keys
    for key in data:
        if key not in new_data:
            new_data[key] = data[key]

    # Generate output with comments
    if not dry_run:
        # Build header
        metadata = data.get("metadata", {})
        header = f"""# Inspekt Recording v{metadata.get('version', '1.1')}
# Generated: {metadata.get('created_at', 'unknown')}
# Duration: {metadata.get('duration_ms', 0) / 1000:.1f}s
# URL: {metadata.get('starting_url', 'unknown')}
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

        # Build steps section with comments
        steps_yaml = "steps:\n"
        for i, step in enumerate(new_steps):
            if i in new_comments:
                steps_yaml += new_comments[i] + "\n"
            step_yaml = yaml.dump([step], default_flow_style=False, allow_unicode=True, sort_keys=False)
            steps_yaml += step_yaml

        # Build other sections
        other_yaml = ""
        for key in ["metadata", "state", "preconditions", "replay"]:
            if key in new_data and key != "steps":
                section_yaml = yaml.dump({key: new_data[key]}, default_flow_style=False, allow_unicode=True, sort_keys=False)
                other_yaml += section_yaml

        # Write output
        output = header + steps_yaml + other_yaml
        with _builtin_open(filepath, "w") as f:
            f.write(output)

    return report


import base64


def process_upload_files(recording: Recording, filepath: Path) -> None:
    """Process upload steps, saving all files externally.

    All files with content are saved to a separate directory and the YAML
    references them by path. This avoids YAML parsing issues with embedded base64.
    """
    recording_name = filepath.stem
    recording_dir = filepath.parent
    files_dir = None

    for step in recording.steps:
        if step.action != "upload" or not step.files:
            continue

        for file_info in step.files:
            content = file_info.content
            if not content:
                continue

            # All files are saved externally (no inline base64 in YAML)
            if content:
                # Create files directory if needed
                if files_dir is None:
                    files_dir = recording_dir / f"{recording_name}_files"
                    files_dir.mkdir(exist_ok=True)

                # Extract base64 data (remove data URL prefix)
                if "," in content:
                    base64_data = content.split(",")[1]
                else:
                    base64_data = content

                try:
                    file_bytes = base64.b64decode(base64_data)

                    # Handle duplicate filenames by adding suffix
                    file_path = files_dir / file_info.name
                    counter = 1
                    while file_path.exists():
                        stem = Path(file_info.name).stem
                        suffix = Path(file_info.name).suffix
                        file_path = files_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

                    file_path.write_bytes(file_bytes)

                    # Update file_info: remove content, add external_path
                    file_info.content = None
                    file_info.external_path = f"{recording_name}_files/{file_path.name}"
                except Exception as e:
                    # If decoding fails, keep the inline content
                    click.echo(f"Warning: Could not save external file {file_info.name}: {e}", err=True)


def process_download_files(recording: Recording, filepath: Path) -> None:
    """Process download steps, saving downloaded files externally.

    Downloaded files are saved to a 'downloads/during-recording/{timestamp}/'
    subdirectory. The timestamp comes from the recording's creation time.

    Supports checksum-based deduplication:
    - Duplicate downloads (same checksum): reuse external_path from original, don't save again
    - Changed downloads (different checksum): save with step ID suffix (e.g., file_0005.pdf)

    File retrieval strategy (in order of preference):
    1. Copy from full_path (Chrome's download location) - most reliable
    2. Fall back to base64 content if full_path is unavailable or inaccessible
       (e.g., Docker containers, remote sessions where Chrome's download folder
       is not directly accessible from the host)

    If neither method succeeds, the download is recorded without the file content.
    """
    import shutil

    recording_name = filepath.stem
    recording_dir = filepath.parent
    downloads_dir = None

    # Get timestamp from recording metadata for folder name
    timestamp_str = recording.metadata.created_at.strftime("%Y%m%d_%H%M%S")

    # Track saved external_paths by step number (1-based) for duplicate resolution
    saved_paths: dict[int, str] = {}

    for step_number, step in enumerate(recording.steps, start=1):
        if step.action != "download" or not step.download:
            continue

        download_info = step.download
        file_saved = False

        # Check for duplicate flag - identical file already saved
        duplicate_of = getattr(download_info, "_duplicate_of_step", None)
        if duplicate_of is None and hasattr(download_info, "__dict__"):
            duplicate_of = download_info.__dict__.get("_duplicate_of_step")

        if duplicate_of is not None:
            # Reuse external_path from the original download step
            original_path = saved_paths.get(duplicate_of)
            if original_path:
                download_info.external_path = original_path
            # Clear temporary fields
            download_info.full_path = None
            download_info.content = None
            continue  # Skip saving - file already exists

        # Create downloads directory if needed (with during-recording subfolder)
        if downloads_dir is None:
            downloads_dir = (
                recording_dir
                / f"{recording_name}_files"
                / "downloads"
                / "during-recording"
                / timestamp_str
            )
            downloads_dir.mkdir(parents=True, exist_ok=True)

        # Clean filename (remove OS-added indices like "(1)", "(2)")
        cleaned_filename = clean_filename(download_info.filename)

        # Check for rename flag - different content, save with step ID suffix
        save_with_step_id = getattr(download_info, "_save_with_step_id", None)
        if save_with_step_id is None and hasattr(download_info, "__dict__"):
            save_with_step_id = download_info.__dict__.get("_save_with_step_id")

        if save_with_step_id is not None:
            # Rename file to include step ID: filename_0005.ext
            stem = Path(cleaned_filename).stem
            suffix = Path(cleaned_filename).suffix
            cleaned_filename = f"{stem}_{save_with_step_id:04d}{suffix}"

        # Destination path
        dest_path = downloads_dir / cleaned_filename

        # Strategy 1: Copy from Chrome's download location (most reliable)
        if download_info.full_path:
            source_path = Path(download_info.full_path)
            if source_path.exists():
                try:
                    shutil.copy2(source_path, dest_path)
                    file_saved = True
                except Exception as e:
                    click.echo(
                        f"Warning: Could not copy download from {source_path}: {e}",
                        err=True,
                    )

        # Strategy 2: Fall back to base64 content (for Docker/remote scenarios)
        if not file_saved and download_info.content:
            content = download_info.content
            # Extract base64 data (remove data URL prefix)
            if "," in content:
                base64_data = content.split(",")[1]
            else:
                base64_data = content

            try:
                file_bytes = base64.b64decode(base64_data)
                dest_path.write_bytes(file_bytes)
                file_saved = True
            except Exception as e:
                click.echo(
                    f"Warning: Could not decode base64 content for {download_info.filename}: {e}",
                    err=True,
                )

        # Update download_info with new path structure
        if file_saved:
            download_info.external_path = (
                f"{recording_name}_files/downloads/during-recording/{timestamp_str}/{dest_path.name}"
            )
            # Track for duplicate resolution
            saved_paths[step_number] = download_info.external_path

        # Always clear temporary fields before YAML save
        download_info.full_path = None
        download_info.content = None

        # Truncate data URLs (they contain the full file content which is redundant)
        if download_info.url and download_info.url.startswith("data:"):
            # Extract just the MIME type from data URL, e.g., "data:application/json;base64,..."
            # becomes "data:application/json (content saved to external_path)"
            mime_part = download_info.url.split(",")[0] if "," in download_info.url else download_info.url
            download_info.url = f"{mime_part} (content saved to external_path)"

        if not file_saved:
            click.echo(
                f"Warning: Could not save download {download_info.filename} - "
                f"file will need to be manually provided for replay",
                err=True,
            )


# Patterns that may indicate sensitive data in dialog messages or responses
SENSITIVE_PATTERNS = [
    (r'api[_\-\s]?key', 'API key'),
    (r'password', 'password'),
    (r'secret', 'secret'),
    (r'token', 'token'),
    (r'ssn|social.?security', 'Social Security Number'),
    (r'credit.?card', 'credit card'),
    (r'cvv|cvc', 'CVV/CVC'),
    (r'pin.?code|pin.?number', 'PIN'),
]


def check_sensitive_dialog_content(steps: list[RecordingStep]) -> list[str]:
    """Check for potentially sensitive content in jsdialog steps.

    Returns a list of warning messages for any sensitive patterns found.
    """
    warnings = []

    for i, step in enumerate(steps):
        if step.action != 'jsdialog':
            continue

        step_num = i + 1

        # Check message
        if step.message:
            for pattern, label in SENSITIVE_PATTERNS:
                if re.search(pattern, step.message, re.IGNORECASE):
                    warnings.append(
                        f"Step {step_num}: Dialog message may request {label}"
                    )
                    break  # One warning per step message

        # Check result (user's response)
        if step.result and isinstance(step.result, str):
            for pattern, label in SENSITIVE_PATTERNS:
                if re.search(pattern, str(step.result), re.IGNORECASE):
                    warnings.append(
                        f"Step {step_num}: Dialog response may contain {label}"
                    )
                    break  # One warning per step result

    return warnings


def handle_existing_recording_file(output_path: Path) -> Optional[tuple[Path, bool]]:
    """
    Handle the case where the recording output file already exists.
    Called BEFORE recording starts.

    Args:
        output_path: The path to the existing file

    Returns:
        - (Path, append_mode) tuple where append_mode=True means append to existing
        - None if user cancels
    """
    # Load existing recording to show info
    step_count = 0
    try:
        with _builtin_open(output_path) as f:
            data = yaml.safe_load(f)
        existing = Recording(**data)
        step_count = len(existing.steps)
        existing_info = (
            f"  Created: {existing.metadata.created_at.strftime('%Y-%m-%d %H:%M')}\n"
            f"  Steps: {step_count}\n"
            f"  URL: {existing.metadata.starting_url}"
        )
    except Exception:
        existing_info = "  (Could not read existing file)"

    # Generate timestamped filename for display
    timestamp = datetime.now().strftime("%Y%m%d")
    timestamped_name = f"{timestamp}_{output_path.name}"

    # Show warning and options
    from inspekt.app.cli.table import print_warning
    click.echo()
    print_warning(f"File already exists: `{output_path.name}`", bold=True)
    click.echo(existing_info)
    click.echo()
    click.echo("What would you like to do?")
    click.echo()
    click.echo(f"  [1] Create a new timestamped recording ({timestamped_name})")
    step_word = "step" if step_count == 1 else "steps"
    click.echo(f"  [2] Overwrite the existing recording (all {step_count} {step_word} will be lost)")
    click.echo("  [3] Append steps to the existing recording (metadata will remain intact)")
    click.echo("  [4] Cancel")
    click.echo()

    choice = click.prompt("Choose", type=click.Choice(["1", "2", "3", "4"]), default="1")

    if choice == "1":
        # Create timestamped copy (now the default)
        new_path = output_path.parent / timestamped_name
        click.echo(f"Will save as: {timestamped_name}")
        return (new_path, False)

    elif choice == "2":
        # Override - return same path, will overwrite
        click.echo("Will overwrite existing file.")
        return (output_path, False)

    elif choice == "3":
        # Append mode - flag to merge later
        click.echo("Will append to existing recording.")
        return (output_path, True)

    else:  # choice == '4'
        return None  # Cancel


def save_recording_to_yaml(
    recording: Recording,
    filepath: Path,
    cookie_consent_provider: str | None = None,
) -> None:
    """Save recording to YAML file with human-readable formatting."""
    # Build optional cookie consent note
    cookie_consent_note = ""
    if cookie_consent_provider:
        cookie_consent_note = f"""#
# Note: This recording includes Tab navigation inside a {cookie_consent_provider}.
# Cookie consent dialogs manage focus internally, so accessible names may not
# be captured for Tab steps inside the dialog. Replay will still work correctly.
"""

    header = f"""# Inspekt Recording v{recording.metadata.version}
# Generated: {recording.metadata.created_at.isoformat()}
# Duration: {recording.metadata.duration_ms / 1000:.1f}s
# URL: {recording.metadata.starting_url}
#{cookie_consent_note}
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

    # Reorder top-level keys: steps first (main content), then config sections
    ordered_data = {}
    key_order = ["steps", "metadata", "state", "preconditions", "replay"]
    for key in key_order:
        if key in data:
            ordered_data[key] = data[key]
    # Add any remaining keys not in the order list
    for key in data:
        if key not in ordered_data:
            ordered_data[key] = data[key]

    # Pre-build comments for each step using the original step data
    # This gives us access to all fields (expect, skip_if, wait_for, etc.)
    step_comments = []
    for i, step in enumerate(recording.steps):
        step_dict = step.model_dump(exclude_none=True)
        comment = construct_step_comment(i + 1, step_dict)
        step_comments.append(comment)

    # Generate YAML content
    yaml_content = yaml.dump(
        ordered_data,
        Dumper=RecordingYAMLDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

    # Post-process to add comments and blank lines between steps
    lines = yaml_content.split('\n')
    output_lines = []
    step_number = 0
    in_steps_section = False

    for line in lines:
        # Track when we enter/exit the steps section
        if line.strip() == 'steps:':
            in_steps_section = True
            output_lines.append(line)
            continue
        elif in_steps_section and line.strip() and not line.startswith(' ') and not line.startswith('-'):
            # We've exited the steps section (hit another top-level key)
            in_steps_section = False
            # Add section separator before metadata/state
            if output_lines and output_lines[-1].strip():
                output_lines.append('')

        # Check if this is a step entry (starts with "- " at step indent level)
        if in_steps_section and line.startswith('- '):
            # Add blank line before step (except first step)
            if step_number > 0 and output_lines and output_lines[-1].strip():
                output_lines.append('')

            # Insert the pre-built comment
            if step_number < len(step_comments):
                output_lines.append(step_comments[step_number])

            step_number += 1

        output_lines.append(line)

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
        steps = data.get("steps", [])

        # Count assertions (steps with 'expect' field)
        assertions = sum(1 for s in steps if s.get("expect"))

        # Get file modification time
        import os
        from datetime import datetime
        mtime = os.path.getmtime(filepath)
        modified_at = datetime.fromtimestamp(mtime)

        return {
            "name": filepath.name,
            "path": filepath,
            "created_at": meta.get("created_at"),
            "modified_at": modified_at,
            "duration_ms": meta.get("duration_ms", 0),
            "steps": len(steps),
            "assertions": assertions,
            "url": meta.get("starting_url", ""),
        }
    except Exception:
        return None


@click.group(cls=SubcommandAwareGroup, invoke_without_command=True)
@click.argument("filename", required=False, default=None)
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
    "--open",
    "open_after",
    is_flag=True,
    help="Open the recording in default application after saving",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal the recording in file explorer after saving",
)
@click.option(
    "--edit",
    "-e",
    "edit_after",
    is_flag=True,
    hidden=True,
    help="Deprecated: use --open instead",
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
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Step through replay manually (requires --replay)",
)
@click.option(
    "--native",
    "-n",
    is_flag=True,
    help="Use native OS keyboard events during replay (macOS only, requires --replay)",
)
@click.option(
    "--typing-speed",
    type=click.Choice(["instant", "fast", "normal", "slow"]),
    default="normal",
    help="Typing speed for native replay mode (requires --replay --native)",
)
@click.option(
    "--capture-state",
    is_flag=True,
    help="Capture cookies, localStorage, and scroll position for replay",
)
@click.option(
    "--storage-keys",
    type=str,
    default=None,
    help="Comma-separated list of localStorage/sessionStorage keys to capture",
)
@click.option(
    "--checksum",
    is_flag=True,
    help="Generate DOM structure checksum for state verification",
)
@click.option(
    "--synthetic-dialogs",
    is_flag=True,
    help="Use non-blocking HTML overlays for alert/confirm/prompt (for automation)",
)
@click.option(
    "--match-viewport",
    is_flag=True,
    help="Mark viewport size as a requirement for faithful replay",
)
@click.option(
    "--match-zoom-level",
    is_flag=True,
    help="Mark zoom level as a requirement for faithful replay",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Override existing file without prompting",
)
@click.option(
    "--viewport",
    "target_viewport",
    type=str,
    default=None,
    help="Resize browser to specific viewport before recording (e.g., 1024x768)",
)
@click.option(
    "--faithful",
    is_flag=True,
    help="Capture focus styles for pixel-perfect keyboard navigation replay (experimental)",
)
@click.pass_context
def record(
    ctx,
    filename: Optional[str],
    output: Optional[str],
    include_hover: bool,
    mask_passwords: bool,
    min_hover_duration: int,
    replay: bool,
    open_after: bool,
    reveal_after: bool,
    edit_after: bool,
    no_audio: bool,
    no_visual: bool,
    no_feedback: bool,
    interactive: bool,
    native: bool,
    typing_speed: str,
    capture_state: bool,
    storage_keys: Optional[str],
    checksum: bool,
    synthetic_dialogs: bool,
    match_viewport: bool,
    match_zoom_level: bool,
    force: bool,
    target_viewport: Optional[str],
    faithful: bool,
):
    """
    Record browser interactions to a YAML file.

    Starts recording all user actions on the currently open browser page.
    Press Ctrl+C to stop recording and save the file.

    The recording can later be replayed with 'inspekt replay' and edited
    to add assertions for automated testing.

    \b
    Subcommands:
        inspekt record tutorial           # Interactive tutorial
        inspekt record list               # List saved recordings
        inspekt record info <file>        # Show recording details
        inspekt record edit <file>        # Open recording in editor
        inspekt record tidy <file>        # Clean up recording file
        inspekt record delete <file>      # Delete a recording

    \b
    Examples:
        inspekt record                    # Auto-generates filename
        inspekt record my-flow.yaml       # Record to specific file
        inspekt record -o login-flow.yaml # Same, using -o flag
        inspekt record --no-hover         # Skip hover events
        inspekt record --open             # Record and open in default app
        inspekt record --replay           # Record and replay to verify
        inspekt record --replay -i        # Record and step through replay
        inspekt record --open --replay    # Open, then replay to verify

    \b
    Note:
        If a filename matches a subcommand name (e.g., 'list'), use the
        .yaml extension to disambiguate: 'inspekt record list.yaml'
    """
    # If a subcommand was invoked, don't run recording
    if ctx.invoked_subcommand is not None:
        return

    # Merge filename argument with -o option (argument takes precedence)
    if filename is not None:
        output = filename

    # Check for existing file BEFORE starting recording (only for user-specified filenames)
    append_mode = False
    if output and not force:
        check_path = Path(output)
        if not check_path.suffix:
            check_path = check_path.with_suffix(".yaml")
        if check_path.exists():
            result = handle_existing_recording_file(check_path)
            if result is None:
                # User cancelled
                click.echo("Recording cancelled.")
                sys.exit(0)
            check_path, append_mode = result
            # Update output to potentially modified path
            output = str(check_path)

    # Parse --viewport argument (WIDTHxHEIGHT format)
    parsed_viewport = None
    if target_viewport:
        try:
            width_str, height_str = target_viewport.lower().split("x")
            parsed_viewport = (int(width_str), int(height_str))
        except ValueError:
            raise click.ClickException(
                f"Invalid viewport format: {target_viewport}. Use WIDTHxHEIGHT (e.g., 1024x768)"
            )

        # Issue 3: Validate dimensions are positive
        vp_width, vp_height = parsed_viewport
        if vp_width <= 0 or vp_height <= 0:
            raise click.ClickException(
                f"Invalid viewport dimensions: {vp_width}×{vp_height}. "
                f"Width and height must be positive integers."
            )

    # Original recording logic follows
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # In VM mode, hide the terminal overlay so user can interact with browser immediately
    # (this does nothing on macOS/normal mode where AppleScript handles focus)
    set_vm_terminal_hidden(True)

    # Resize viewport if requested (before recording starts)
    if parsed_viewport:
        target_width, target_height = parsed_viewport

        # Check for fullscreen/kiosk mode BEFORE attempting resize
        # In these modes, the window cannot be resized
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
            fullscreen_result = client.execute(fullscreen_check_js, timeout=5.0)
            if fullscreen_result.get("ok"):
                fs_info = fullscreen_result.get("result", {})
                if fs_info.get("isFullscreen") or fs_info.get("isKiosk"):
                    mode_name = "fullscreen" if fs_info.get("isFullscreen") else "kiosk"
                    click.secho(
                        f"Warning: Browser is in {mode_name} mode. Viewport cannot be resized.\n"
                        f"   The --viewport {target_viewport} option will be ignored.\n"
                        f"   Exit {mode_name} mode (press F11 or Esc) to enable viewport resizing.",
                        fg="yellow"
                    )
                    # Skip resize - set parsed_viewport to None
                    parsed_viewport = None
        except Exception:
            pass  # Continue with resize attempt if detection fails

    # Continue with resize if not in fullscreen mode
    if parsed_viewport:
        target_width, target_height = parsed_viewport

        # Import config functions for caching
        from inspekt.config import get_viewport_offsets, save_viewport_offsets

        # Helper to get screen dimensions via JavaScript
        def get_screen_dimensions() -> tuple[int, int] | None:
            """Get screen dimensions to validate viewport request."""
            js = "(function(){ return { width: screen.width, height: screen.height }; })()"
            try:
                result = client.execute(js, timeout=5.0)
                if result.get("ok"):
                    dims = result.get("result", {})
                    if isinstance(dims, dict):
                        w = dims.get("width")
                        h = dims.get("height")
                        if isinstance(w, (int, float)) and isinstance(h, (int, float)):
                            return int(w), int(h)
            except Exception:
                pass
            return None

        # Issue 3: Validate viewport doesn't exceed screen size
        screen_dims = get_screen_dimensions()
        if screen_dims:
            screen_w, screen_h = screen_dims
            if target_width > screen_w or target_height > screen_h:
                raise click.ClickException(
                    f"Viewport {target_width}×{target_height} exceeds screen size {screen_w}×{screen_h}.\n"
                    f"The viewport cannot be larger than your display.\n"
                    f"Consider using a smaller viewport (e.g., --viewport {min(target_width, screen_w)}x{min(target_height, screen_h)}) "
                    f"or connecting a larger monitor."
                )

        click.echo(f"Resizing viewport to {target_width}×{target_height}…")

        # Helper to verify actual viewport via JavaScript
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

        # Helper to attempt resize with better error logging (Issue 7)
        def attempt_resize(width: int, height: int) -> bool:
            # macOS: Use AppleScript (most reliable, can resize any window)
            if sys.platform == "darwin":
                try:
                    from inspekt.services.applescript_utils import resize_browser_window

                    success = resize_browser_window(width, height)
                    if not success:
                        click.echo("  AppleScript resize returned failure", err=True)
                    return success
                except ImportError:
                    click.echo("  AppleScript utils not available", err=True)
                except Exception as e:
                    click.echo(f"  AppleScript error: {e}", err=True)

            # All platforms: Try JavaScript resize (often blocked by browsers for security)
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

        # Check for cached viewport offsets first
        cached_offsets = get_viewport_offsets()
        resize_achieved = False
        need_calibration = False

        if cached_offsets:
            # Issue 9: Validate cached offsets are reasonable before using
            if cached_offsets["width"] < 0 or cached_offsets["height"] < 0:
                click.echo("  Cached offsets invalid (negative), recalibrating…")
                need_calibration = True
            else:
                # Use cached offsets - single resize attempt
                # Offset is positive (how much larger window is than viewport)
                # So we ADD offset to get the window size that yields target viewport
                adjusted_w = target_width + cached_offsets["width"]
                adjusted_h = target_height + cached_offsets["height"]
                attempt_resize(adjusted_w, adjusted_h)
                time.sleep(0.3)

                actual_w, actual_h = get_actual_viewport()
                # Exact match required - no tolerance
                if actual_w == target_width and actual_h == target_height:
                    click.secho(f"✓ Viewport set to {actual_w}×{actual_h}", fg="green")
                    resize_achieved = True
                else:
                    # Cached offsets are stale - recalibrate
                    if actual_w is not None:
                        click.echo(f"  Cached offsets outdated (got {actual_w}×{actual_h}), recalibrating…")
                    else:
                        click.echo("  Could not verify with cached offsets, recalibrating…")
                    need_calibration = True
        else:
            need_calibration = True

        if need_calibration and not resize_achieved:
            import random

            # Calibration loop with fun messages
            # Pool of messages for in-between attempts (shuffled, no repeats until all used)
            nudge_pool = [
                "micro-adjusting…",
                "settling into place…",
                "locking it down…",
                "calibrating…",
                "re-calibrating…",
                "nudging…",
                "nudging some more…",
                "compensating…",
                "honing in…",
                "trimming the edges…",
            ]
            random.shuffle(nudge_pool)
            nudge_index = 0

            def get_nudge_message(attempt_num: int, err_w: int, err_h: int) -> str:
                nonlocal nudge_index, nudge_pool
                # First attempt: always "dialing it in…"
                if attempt_num == 0:
                    return "dialing it in…"
                # 1px off on either dimension: "shaving off that last pixel…"
                if (abs(err_w) == 1 and err_h == 0) or (err_w == 0 and abs(err_h) == 1) or (abs(err_w) == 1 and abs(err_h) == 1):
                    return "shaving off that last pixel…"
                # In-between: use shuffled pool, cycle through without repeats
                msg = nudge_pool[nudge_index % len(nudge_pool)]
                nudge_index += 1
                # Reshuffle when we've used all messages
                if nudge_index >= len(nudge_pool):
                    nudge_index = 0
                    random.shuffle(nudge_pool)
                return msg

            max_attempts = 20
            adjustment_w, adjustment_h = 0, 0
            prev_error_w, prev_error_h = None, None
            base_delay = 0.3

            # Track viewport history for oscillation detection
            viewport_history: list[tuple[int, int]] = []

            for attempt in range(max_attempts):
                adjusted_w = target_width - adjustment_w
                adjusted_h = target_height - adjustment_h

                # Attempt the resize
                attempt_resize(adjusted_w, adjusted_h)

                # Exponential backoff - increase delay on each attempt
                delay = base_delay * (1.1 ** attempt)  # 0.3, 0.33, 0.36, 0.40...
                time.sleep(min(delay, 1.5))  # Cap at 1.5 seconds

                # Verify actual viewport (retry on failure)
                actual_w, actual_h = get_actual_viewport()
                if actual_w is None:
                    # Retry once after brief delay
                    time.sleep(0.5)
                    actual_w, actual_h = get_actual_viewport()

                if actual_w is None:
                    # Can't verify - show platform-specific guidance
                    if sys.platform == "darwin":
                        click.secho(
                            f"⚠ Could not verify viewport. Please manually resize to {target_width}×{target_height}",
                            fg="yellow",
                        )
                    else:
                        click.secho(
                            f"⚠ Could not verify viewport. On {sys.platform}, please manually resize "
                            f"your browser to {target_width}×{target_height}",
                            fg="yellow",
                        )
                    break

                error_w = actual_w - target_width
                error_h = actual_h - target_height

                # Track viewport for oscillation detection
                viewport_history.append((actual_w, actual_h))

                # Exact match required - no tolerance
                if error_w == 0 and error_h == 0:
                    # Calculate viewport offsets (browser chrome compensation)
                    # Typical case: adjustment is negative (we had to resize larger), so offset is positive
                    # Edge case: if viewport matched immediately or was larger, adjustment could be 0 or positive
                    offset_w = max(0, -adjustment_w)  # Clamp to non-negative
                    offset_h = max(0, -adjustment_h)  # Clamp to non-negative
                    if save_viewport_offsets(offset_w, offset_h):
                        click.secho(f"✓ Viewport set to {actual_w}×{actual_h}, offsets saved.", fg="green")
                    else:
                        # Only show warning if offsets were non-zero (meaningful calibration)
                        if offset_w > 0 or offset_h > 0:
                            click.secho(f"✓ Viewport set to {actual_w}×{actual_h} (offsets not saved).", fg="yellow")
                        else:
                            click.secho(f"✓ Viewport set to {actual_w}×{actual_h}.", fg="green")
                    resize_achieved = True
                    break

                # Oscillation detection: check if we've seen this exact viewport before recently
                # If we see the same value twice in the last 4 attempts, we're oscillating
                if len(viewport_history) >= 4:
                    recent = viewport_history[-4:]
                    current = (actual_w, actual_h)
                    # Count occurrences of current viewport in recent history
                    if recent.count(current) >= 2:
                        click.secho(
                            f"⚠ Could not achieve the exact viewport (requested {target_width}×{target_height}, "
                            f"achieved {actual_w}×{actual_h}).\n"
                            f"   This issue is related to display scaling. Please try to use even values.",
                            fg="yellow",
                        )
                        break

                # Check if error magnitude is increasing (diverging)
                if prev_error_w is not None:
                    if abs(error_w) > abs(prev_error_w) + 5 or abs(error_h) > abs(prev_error_h) + 5:
                        click.secho(
                            f"⚠ Viewport diverging: requested {target_width}×{target_height}, "
                            f"achieved {actual_w}×{actual_h}. Browser may not support this size.",
                            fg="yellow",
                        )
                        break

                prev_error_w, prev_error_h = error_w, error_h

                if attempt < max_attempts - 1:
                    # Adjust for next attempt with friendly message
                    adjustment_w += error_w
                    adjustment_h += error_h
                    msg = get_nudge_message(attempt, error_w, error_h)
                    click.echo(f"  Attempt {attempt + 1}: got {actual_w}×{actual_h}, {msg}")
                else:
                    # Max attempts reached - still couldn't hit exact size
                    click.secho(
                        f"⚠ Could not achieve exact viewport after {max_attempts} attempts: "
                        f"requested {target_width}×{target_height}, achieved {actual_w}×{actual_h}.\n"
                        f"   This may be a hardware/browser limitation.",
                        fg="yellow",
                    )

        # Auto-enable viewport matching requirement since user explicitly specified dimensions
        match_viewport = True

    # Load the recording script
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    script_path = scripts_dir / "record_events.js"

    try:
        with _builtin_open(script_path) as f:
            script_template = f.read()
    except FileNotFoundError:
        set_vm_terminal_hidden(False)  # Restore terminal on error
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    # Load and inject the visual/audio script for start/stop sounds
    visual_script = None
    visual_script_path = scripts_dir / "replay_visual.js"
    try:
        with _builtin_open(visual_script_path) as f:
            visual_script = f.read()
        # Inject shared dialog styles
        visual_script = visual_script.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)
        # Inject the script
        client.execute(visual_script, timeout=10.0)
    except FileNotFoundError:
        pass  # Visual script is optional for recording

    # Configuration for the browser script
    # Generate a unique recording ID for IndexedDB persistence
    recording_id = f"rec_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    # Load record config for rate limiting and synthetic dialogs
    record_config = get_record_config()
    max_actions_per_second = record_config.get("max-actions-per-second", 10)
    # CLI flag overrides config setting for synthetic dialogs
    use_synthetic_dialogs = synthetic_dialogs or record_config.get("synthetic-dialogs", False)

    config = {
        "includeHover": include_hover,
        "maskPasswords": mask_passwords,
        "minHoverDuration": min_hover_duration,
        "audio": True,  # Always enable audio feedback during recording
        "recordingId": recording_id,
        "maxActionsPerSecond": max_actions_per_second,
        "syntheticDialogs": use_synthetic_dialogs,
        "captureFocusStyles": faithful,  # Capture focus styles for --faithful replay
    }
    config_json = json.dumps(config)

    # Prepare start code
    start_code = script_template.replace("ACTION_PLACEHOLDER", "start")
    start_code = start_code.replace("CONFIG_PLACEHOLDER", config_json)
    start_code = start_code.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)

    # Start recording
    try:
        result = client.execute(start_code, timeout=10.0)

        if not result.get("ok"):
            error = result.get('error', 'unknown error')
            click.echo()
            click.secho("⚠ The recording could not be started", fg="yellow", bold=True, err=True)
            click.echo(err=True)
            click.echo("  * Ensure that the latest version of the Inspekt extension is installed", err=True)
            click.echo("    and enabled in Firefox or Chrome.", err=True)
            click.echo("  * Make sure that a JavaScript dialog is not blocking access to the page.", err=True)
            click.echo("  * In some cases, you may need to disable CSP. You can do this by clicking", err=True)
            click.echo("    the toggle in the Inspekt UI that appears when you click the icon in", err=True)
            click.echo("    your toolbar.", err=True)
            if error and error != "no_browser_connected":
                click.echo(err=True)
                click.echo(f"  Technical details: {error}", err=True)
            click.echo()
            set_vm_terminal_hidden(False)  # Restore terminal on error
            sys.exit(1)

        response = result.get("result", {})
        start_url = response.get("startUrl", "")
        start_time = datetime.now(timezone.utc)
        viewport = response.get("viewport", {"width": 1920, "height": 1080})
        initial_scroll = response.get("scroll", {"x": 0, "y": 0})
        zoom = response.get("zoom", 1.0)
        user_agent = response.get("userAgent", "")

        # Extract window mode (fullscreen/kiosk/normal)
        window_mode_info = response.get("windowMode", {})
        window_mode = window_mode_info.get("mode") if window_mode_info else None

        # Fetch actual browser zoom level via Chrome extension API
        browser_zoom_level = 1.0
        try:
            zoom_code = """
            (async () => {
                return new Promise((resolve) => {
                    const requestId = 'zoom-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
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
                    // Timeout fallback
                    setTimeout(() => resolve(1.0), 2000);
                });
            })()
            """
            zoom_result = client.execute(zoom_code, timeout=3.0)
            if zoom_result.get("ok") and zoom_result.get("result"):
                browser_zoom_level = float(zoom_result.get("result", 1.0))
        except Exception:
            pass  # Fall back to 1.0 if fetching fails

        # Check CSP bypass status and warn if disabled (only shown after successful start)
        # This is especially important for --replay since replay requires script injection
        if replay and not check_csp_bypass_enabled():
            click.echo()
            click.secho("  ⚠  CSP bypass is disabled", fg="yellow", bold=True)
            click.echo("     Some sites may not work correctly during replay.")
            click.echo("     Enable it with: inspekt domain csp --enable")
            click.echo("     Or toggle it in the Inspekt extension popup.")
            click.echo()

        # Display pre-recording hints and warnings
        display_pre_recording_hints(response, use_synthetic_dialogs)

        # Track which browser tab we started recording in
        # This prevents accidentally resuming in a different tab
        recording_browser_index = client.get_current_browser_index()

        # Focus the browser window (macOS only)
        # This helps the user start recording immediately
        # Use silent=True since focus is automatic for record (not a user-requested option)
        _focus_browser_if_requested(focus=True, silent=True)

        # Play start sound (target the specific browser we're recording in)
        if visual_script:
            try:
                client.execute("window.__INSPEKT_VISUAL__.audio.playStart()", timeout=5.0, browser_index=recording_browser_index)
                time.sleep(0.4)  # Wait for start sound to complete
            except Exception:
                pass  # Audio is optional

        # Display recording header
        from inspekt.config import is_nerdfont_enabled, is_isolated_mode
        record_icon = "\U000f044a " if is_nerdfont_enabled() else ""  # 󰑊 nf-md-record
        recording_label = click.style(f"{record_icon}Now recording", fg="red", bold=True)
        browser_active = click.style("(browser is now active)", fg="bright_black")
        ctrl_c = click.style(" Ctrl+C ", fg="black", bg="bright_yellow")
        stop_location = click.style("(here or in your browser)", fg="bright_black")
        click.echo(f"\n{recording_label}: {start_url} {browser_active}")
        click.echo(f"Press {ctrl_c} {stop_location} to stop and save\n")

        # In VM mode, emit escape sequence to auto-hide terminal
        # This allows the user to immediately interact with the browser
        if is_isolated_mode():
            print('\033]1337;hide-terminal\007', end='', flush=True)

        # Prepare poll and stop codes
        poll_code = script_template.replace("ACTION_PLACEHOLDER", "poll")
        poll_code = poll_code.replace("CONFIG_PLACEHOLDER", config_json)
        poll_code = poll_code.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)

        stop_code = script_template.replace("ACTION_PLACEHOLDER", "stop")
        stop_code = stop_code.replace("CONFIG_PLACEHOLDER", config_json)
        stop_code = stop_code.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)

        # Collected steps
        all_steps: list[RecordingStep] = []

        # Undo stack for redo functionality
        undo_stack: list[RecordingStep] = []

        # Track seen event timestamps to prevent duplicates after resume
        seen_timestamps: set[int] = set()

        # Track download checksums for deduplication: filename → {checksum, step_number}
        download_checksums: dict[str, dict] = {}

        # Step counter for display
        step_count = 0

        # Recording paused state (Ctrl+Shift+P)
        is_paused = False
        pause_start_time: float | None = None  # Track when pause started

        # Header display flag (show header only after first action)
        header_shown = False

        # Track cookie consent dialog interactions
        cookie_consent_hint_shown = False
        cookie_consent_provider: str | None = None  # Name of the provider (e.g., "Usercentrics")

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
            resume_code = resume_code.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)
            return resume_code

        # Flag for clean shutdown (avoid doing I/O in signal handler)
        stop_requested = False

        # Terminal echo suppressor - prevents escape sequences from appearing
        # when user accidentally types in terminal instead of browser
        terminal_suppressor = TerminalEchoSuppressor()

        # Signal handler for Ctrl+C - just sets a flag
        def stop_recording(sig, frame):
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGINT, stop_recording)

        # Cleanup function called from main loop when stop is requested
        def do_cleanup(allow_retry: bool = True):
            nonlocal all_steps

            # Restore terminal settings first (so echo works for prompts/output)
            terminal_suppressor.restore()

            # In VM mode, show the terminal overlay again (recording is stopping)
            set_vm_terminal_hidden(False)

            click.echo("\nStopping recording… " + success_icon(""))

            # Play stop/completion sound (target the specific browser we're recording in)
            if visual_script:
                try:
                    client.execute("window.__INSPEKT_VISUAL__.audio.playStop()", timeout=2.0, browser_index=recording_browser_index)
                except Exception:
                    pass  # Audio is optional

            try:
                # Stop recording and get final events (target the specific browser)
                stop_result = client.execute(stop_code, timeout=2.0, browser_index=recording_browser_index)

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

            # Build state info
            state_info = StateInfo(
                viewport=ViewportInfo(
                    width=viewport.get("width", 1920),
                    height=viewport.get("height", 1080),
                ),
                zoom=zoom,
                browser_zoom_level=browser_zoom_level,
                scroll=ScrollPosition(
                    x=initial_scroll.get("x", 0),
                    y=initial_scroll.get("y", 0),
                ),
                require_viewport_match=match_viewport,
                require_zoom_match=match_zoom_level,
                window_mode=window_mode,  # fullscreen/kiosk/normal
            )

            # Capture additional state if --capture-state flag was used
            if capture_state:
                import base64
                # Capture cookies via extension
                try:
                    cookies_result = client.execute("""
                        new Promise((resolve) => {
                            const requestId = 'cookies-' + Date.now() + '-' + Math.random().toString(36).slice(2);
                            const handler = (event) => {
                                if (event.data?.type === 'INSPEKT_COOKIES_RESPONSE' &&
                                    event.data?.source === 'inspekt-extension' &&
                                    event.data?.requestId === requestId) {
                                    window.removeEventListener('message', handler);
                                    resolve(event.data.response);
                                }
                            };
                            window.addEventListener('message', handler);
                            window.postMessage({
                                type: 'INSPEKT_GET_COOKIES_ENHANCED',
                                source: 'inspekt-page',
                                requestId: requestId
                            }, '*');
                            // Timeout after 3 seconds
                            setTimeout(() => {
                                window.removeEventListener('message', handler);
                                resolve({ ok: false, error: 'timeout' });
                            }, 3000);
                        })
                    """, timeout=5.0, browser_index=recording_browser_index)
                    if cookies_result.get("ok"):
                        cookies_data = cookies_result.get("result", {})
                        if cookies_data.get("ok") and cookies_data.get("cookies"):
                            cookies_json = json.dumps(cookies_data["cookies"])
                            state_info.cookies = base64.b64encode(cookies_json.encode()).decode()
                except Exception as e:
                    click.echo(f"Warning: Failed to capture cookies: {e}", err=True)

                # Capture localStorage/sessionStorage
                storage_keys_list = storage_keys.split(",") if storage_keys else None
                try:
                    storage_code = """
                        (function() {
                            const keys = KEYS_PLACEHOLDER;
                            const getStorage = (storage) => {
                                const result = {};
                                if (keys) {
                                    keys.forEach(k => {
                                        const v = storage.getItem(k.trim());
                                        if (v !== null) result[k.trim()] = v;
                                    });
                                }
                                return result;
                            };
                            return {
                                localStorage: getStorage(localStorage),
                                sessionStorage: getStorage(sessionStorage)
                            };
                        })()
                    """.replace("KEYS_PLACEHOLDER", json.dumps(storage_keys_list) if storage_keys_list else "null")

                    storage_result = client.execute(storage_code, timeout=3.0, browser_index=recording_browser_index)
                    if storage_result.get("ok"):
                        storage_data = storage_result.get("result", {})
                        if storage_data.get("localStorage"):
                            local_json = json.dumps(storage_data["localStorage"])
                            state_info.local_storage = base64.b64encode(local_json.encode()).decode()
                        if storage_data.get("sessionStorage"):
                            session_json = json.dumps(storage_data["sessionStorage"])
                            state_info.session_storage = base64.b64encode(session_json.encode()).decode()
                except Exception as e:
                    click.echo(f"Warning: Failed to capture storage: {e}", err=True)

            # Capture DOM checksum if --checksum flag was used
            if checksum:
                import hashlib
                try:
                    checksum_result = client.execute("""
                        (function() {
                            // Generate a hash of the DOM structure (tags only, no text/attrs)
                            function getStructure(node) {
                                if (node.nodeType !== 1) return '';
                                const children = Array.from(node.children).map(getStructure).join('');
                                return '<' + node.tagName.toLowerCase() + '>' + children + '</' + node.tagName.toLowerCase() + '>';
                            }
                            return getStructure(document.body);
                        })()
                    """, timeout=5.0, browser_index=recording_browser_index)
                    if checksum_result.get("ok"):
                        structure = checksum_result.get("result", "")
                        hash_value = hashlib.sha256(structure.encode()).hexdigest()
                        state_info.checksum = f"sha256:{hash_value}"
                except Exception as e:
                    click.echo(f"Warning: Failed to generate checksum: {e}", err=True)

            # Extract browser info from user agent
            recorded_on = None
            import platform as platform_module
            if user_agent:
                browser_name = "Chrome"  # Default
                browser_version = None
                if "Firefox/" in user_agent:
                    browser_name = "Firefox"
                    import re
                    match = re.search(r"Firefox/([\d.]+)", user_agent)
                    if match:
                        browser_version = match.group(1)
                elif "Edg/" in user_agent:
                    browser_name = "Edge"
                    import re
                    match = re.search(r"Edg/([\d.]+)", user_agent)
                    if match:
                        browser_version = match.group(1)
                elif "Chrome/" in user_agent:
                    import re
                    match = re.search(r"Chrome/([\d.]+)", user_agent)
                    if match:
                        browser_version = match.group(1)

                recorded_on = RecordedOn(
                    platform=platform_module.system().lower(),
                    browser=browser_name,
                    browser_version=browser_version,
                )

            # Build recording
            recording = Recording(
                metadata=RecordingMetadata(
                    version="1.1",
                    created_at=start_time,
                    duration_ms=duration_ms,
                    starting_url=start_url,
                    user_agent=user_agent or None,
                    recorded_on=recorded_on,
                    faithful=faithful,
                ),
                state=state_info,
                steps=all_steps,
            )

            # Check for failed recording (only navigate action = likely JS conflict)
            is_failed_recording = (
                len(all_steps) == 1 and
                all_steps[0].action == "navigate"
            )

            if is_failed_recording:
                # Recording failed - likely due to leftover JS from previous recording
                click.echo()
                click.secho("Attention: ", fg="yellow", bold=True, nl=False)
                click.echo("Recording failed. Only the initial page load was captured.")
                click.echo()
                click.echo("This usually happens when a previous recording's JavaScript")
                click.echo("is still active on the page.")
                click.echo()

                if allow_retry:
                    # Offer to refresh and retry
                    if click.confirm("Refresh the page and try again?", default=True):
                        # Refresh the page
                        try:
                            click.echo("Refreshing page… " + success_icon(""))
                            client.execute("location.reload()", timeout=5.0, browser_index=recording_browser_index)
                            time.sleep(1.5)  # Wait for page reload
                            # Re-focus the browser so user can continue interacting
                            _focus_browser_if_requested(focus=True, silent=True)
                            return "retry"  # Signal to retry
                        except Exception as e:
                            click.echo(f"Error refreshing page: {e}", err=True)
                            sys.exit(1)
                    else:
                        click.echo("Recording discarded.")
                        sys.exit(0)
                else:
                    # No retry for inactivity timeout
                    click.echo("Recording discarded.")
                    sys.exit(0)

            # Determine output path
            if output:
                output_path = Path(output)
                if not output_path.suffix:
                    output_path = output_path.with_suffix(".yaml")
            else:
                output_path = get_recordings_dir() / generate_filename(start_url, start_time)

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Process upload files - save large files externally
            process_upload_files(recording, output_path)

            # Process download files - save downloaded files externally
            process_download_files(recording, output_path)

            # Handle append mode - merge with existing recording
            if append_mode:
                try:
                    with _builtin_open(output_path) as f:
                        existing_data = yaml.safe_load(f)
                    existing = Recording(**existing_data)
                    original_step_count = len(existing.steps)
                    # Prepend existing steps to new recording
                    recording.steps = existing.steps + recording.steps
                    # Keep existing metadata (created_at)
                    recording.metadata.created_at = existing.metadata.created_at
                    # Recalculate duration based on last step
                    if recording.steps:
                        recording.metadata.duration_ms = recording.steps[-1].timestamp or 0
                    new_step_count = len(recording.steps) - original_step_count
                    click.echo(f"Appended {new_step_count} new steps to existing {original_step_count} steps.")
                except Exception as e:
                    click.secho(f"Warning: Could not read existing file for append: {e}", fg="yellow")
                    click.echo("Saving as new recording instead.")

            # Save recording
            try:
                save_recording_to_yaml(recording, output_path, cookie_consent_provider=cookie_consent_provider)

                # Check for potentially sensitive content in dialog steps
                sensitive_warnings = check_sensitive_dialog_content(all_steps)
                if sensitive_warnings:
                    click.echo()
                    click.secho("  ⚠️  Security Warning: Recording may contain sensitive data:", fg="yellow")
                    for warning in sensitive_warnings:
                        click.secho(f"      • {warning}", fg="yellow")
                    click.secho("      Consider reviewing/redacting before sharing this file.", fg="yellow")
                    click.echo()

                # Count steps excluding hovers
                non_hover_steps = sum(1 for s in all_steps if s.action != "hover")

                # Display simplified recording saved info
                click.echo(f"Recording saved to {click.style(output_path.name, bold=True)} ({format_duration(duration_ms)}, {non_hover_steps} actions) " + success_icon(""))

                # Merge --open and --edit (backwards compat) flags
                should_open = open_after or edit_after

                if should_open and replay:
                    click.echo(f"\nOpening file, then starting replay…")
                elif should_open:
                    click.echo(f"\nOpening file…")
                elif replay:
                    click.echo(f"\nStarting verification replay…")
                else:
                    click.echo(f"\nWhat you can do next:")
                    click.echo(f" - Edit:   inspekt record edit {output_path.name}")
                    click.echo(f" - Replay: inspekt replay {output_path.name} --interactive")
            except Exception as e:
                click.echo(f"Error saving recording: {e}", err=True)
                sys.exit(1)

            # Open file if --open flag was set (or deprecated --edit)
            if should_open:
                OutputHandler.open_file(output_path)

            # Reveal file if --reveal flag was set
            if reveal_after:
                OutputHandler.reveal_file(output_path)

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
                click.echo("Refreshing page before replay…")
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
                    # Inject shared dialog styles
                    countdown_visual_script = countdown_visual_script.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)
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

                frequencies = {3: 440, 2: 523, 1: 659}  # A4, C5, E5 - ascending
                for i in range(3, 0, -1):
                    click.echo(f"\rStarting replay in {i}…", nl=False)
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
                        restore_viewport=False,
                        interactive=interactive,
                        stop_on_error=False,
                        skip_tests=False,
                        restore_state=False,
                        restore_cookies=False,
                        restore_storage=False,
                        verify_checksum=False,
                        strict_preconditions=False,
                        strict_checksum=False,
                        progress=False,
                        skip_validation=False,
                        video_output=None,
                        smooth=False,
                        compact=False,
                        video_fps=None,
                        open_after=False,
                        reveal_after=False,
                        include_effects=False,
                        match_viewport=match_viewport,
                        match_zoom_level=match_zoom_level,
                        faithful=faithful,
                        native=native,
                        typing_speed=typing_speed,
                    )
                except SystemExit as e:
                    # Replay exits with code 1 on failure
                    sys.exit(e.code)
                except Exception as e:
                    click.echo(f"Error during replay: {e}", err=True)
                    sys.exit(1)

            sys.exit(0)

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

        # Start suppressing terminal keyboard echo
        # This prevents escape sequences (^[[Z etc) from appearing when user
        # accidentally types in the terminal instead of the browser
        terminal_suppressor.suppress()

        # Main polling loop
        while True:
            # Check if stop was requested (Ctrl+C)
            if stop_requested:
                result = do_cleanup()
                if result == "retry":
                    # Reset state for retry
                    stop_requested = False
                    all_steps = []
                    undo_stack = []
                    step_count = 0
                    is_paused = False
                    pause_start_time = None
                    header_shown = False
                    cookie_consent_hint_shown = False
                    cookie_consent_provider = None
                    seen_timestamps = set()
                    download_checksums = {}
                    last_activity_time = time.time()
                    inactivity_warning_shown = False
                    start_time = datetime.now(timezone.utc)

                    # Re-inject recording script
                    retry_result = client.execute(start_code, timeout=10.0)
                    if not retry_result.get("ok"):
                        click.echo(f"Error restarting recording: {retry_result.get('error')}", err=True)
                        sys.exit(1)

                    retry_response = retry_result.get("result", {})
                    start_url = retry_response.get("startUrl", start_url)

                    # Display recording header again
                    click.echo(f"\n{recording_label}: {start_url}")
                    click.echo(f"Press {ctrl_c} to stop and save\n")

                    # Play start sound
                    if visual_script:
                        try:
                            client.execute("window.__INSPEKT_VISUAL__.audio.playStart()", timeout=5.0, browser_index=recording_browser_index)
                            time.sleep(0.4)
                        except Exception:
                            pass

                    # Re-enable terminal echo suppression for new recording
                    terminal_suppressor.suppress()

                    continue  # Continue polling loop
                break

            # Check for inactivity
            inactive_seconds = time.time() - last_activity_time

            if inactive_seconds >= INACTIVITY_STOP_SECONDS:
                # Auto-stop due to inactivity - custom format with stop icon
                elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                elapsed_str = format_elapsed(elapsed_ms)
                prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                stop_icon = get_indicator("stop") or ""
                icon_str = f"{stop_icon}  " if stop_icon else ""
                msg = click.style("No activity for 60 seconds. Recording stopped.", fg="bright_black", italic=True)
                click.echo(f"{prefix}   {icon_str}{msg}")
                # For inactivity timeout, don't offer retry - just discard if failed
                do_cleanup(allow_retry=False)
                break

            if inactive_seconds >= INACTIVITY_WARNING_SECONDS and not inactivity_warning_shown:
                # Custom format with hourglass icon, timestamp, and ellipsis
                elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                elapsed_str = format_elapsed(elapsed_ms)
                prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                hourglass = "\uf252"  # nf-fa-hourglass_end
                icon_str = f"{hourglass}  "
                msg = click.style("No activity for 30 seconds. Recording will stop in 30 seconds…", fg="bright_black", italic=True)
                click.echo(f"{prefix}   {icon_str}{msg}")
                # Add hint about Ctrl+C (same style as recording start message)
                ctrl_c_styled = click.style(" Ctrl+C ", fg="black", bg="bright_yellow")
                hint = click.style("Press ", fg="bright_black") + ctrl_c_styled + click.style(" to stop and save", fg="bright_black")
                click.echo(f"                  {hint}")
                inactivity_warning_shown = True

            try:
                debug_log("Sending poll request...")
                # Always target the specific browser tab where recording started
                result = client.execute(poll_code, timeout=2.0, browser_index=recording_browser_index)
                debug_log(f"Poll result: ok={result.get('ok')}, has_result={result.get('result') is not None}")

                # Reset error count on successful communication
                if consecutive_errors > 0 and waiting_for_reconnect:
                    click.echo(format_system_message("Reconnected", icon="resume"))
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

                    # Check if stop was requested from browser (Ctrl+C or limit reached)
                    if response.get("stopRequested"):
                        stop_reason = response.get("stopReason")
                        if stop_reason and stop_reason.startswith("download_limit:"):
                            limit = stop_reason.split(":")[1]
                            click.echo(format_system_message(
                                f"Download limit ({limit}) reached. Recording has been stopped as a precaution.",
                                icon="tip"
                            ))
                            debug_log(f"Stop requested from browser (download limit: {limit})")
                        elif stop_reason and stop_reason.startswith("action_rate_limit:"):
                            limit = stop_reason.split(":")[1]
                            click.echo(format_system_message(
                                f"Action rate limit ({limit}/second) exceeded. Recording has been stopped as a precaution.",
                                icon="tip"
                            ))
                            debug_log(f"Stop requested from browser (action rate limit: {limit}/sec)")
                        else:
                            debug_log("Stop requested from browser (Ctrl+C)")
                        result = do_cleanup()
                        if result == "retry":
                            # Reset state for retry (same as Ctrl+C from CLI)
                            all_steps = []
                            undo_stack = []
                            step_count = 0
                            is_paused = False
                            pause_start_time = None
                            header_shown = False
                            cookie_consent_hint_shown = False
                            cookie_consent_provider = None
                            seen_timestamps = set()
                            download_checksums = {}
                            last_activity_time = time.time()
                            inactivity_warning_shown = False
                            start_time = datetime.now(timezone.utc)

                            # Re-inject recording script
                            retry_result = client.execute(start_code, timeout=10.0)
                            if not retry_result.get("ok"):
                                click.echo(f"Error restarting recording: {retry_result.get('error')}", err=True)
                                sys.exit(1)

                            retry_response = retry_result.get("result", {})
                            start_url = retry_response.get("startUrl", start_url)

                            # Display recording header again
                            click.echo(f"\n{recording_label}: {start_url}")
                            click.echo(f"Press {ctrl_c} to stop and save\n")

                            # Play start sound
                            if visual_script:
                                try:
                                    client.execute("window.__INSPEKT_VISUAL__.audio.playStart()", timeout=5.0, browser_index=recording_browser_index)
                                    time.sleep(0.4)
                                except Exception:
                                    pass

                            continue  # Continue polling loop
                        break

                    # =====================================================================
                    # Recording Control Signals (Pause, Undo, Redo)
                    # =====================================================================

                    # Handle pause toggle (Ctrl+Shift+P in browser)
                    if response.get("pauseToggled"):
                        is_paused = response.get("isPaused", False)
                        if is_paused:
                            pause_start_time = time.time()
                            # Show pause message with timestamp
                            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                            elapsed_str = format_elapsed(elapsed_ms)
                            prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                            pause_icon = get_indicator("pause") or ""
                            icon_str = f"{pause_icon}  " if pause_icon else ""
                            msg = click.style("Recording paused", fg="bright_black", italic=True)
                            click.echo(f"{prefix}   {icon_str}{msg}")
                        else:
                            # Calculate pause duration and elapsed time
                            elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                            elapsed_str = format_elapsed(elapsed_ms)
                            pause_duration_sec = int(time.time() - pause_start_time) if pause_start_time else 0
                            pause_start_time = None
                            # Format: "0001   00:56   󰐊  Recording resumed after 45 seconds"
                            prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                            icon_glyph = get_indicator("resume") or ""
                            icon_str = f"{icon_glyph}  " if icon_glyph else ""
                            # Format duration naturally
                            if pause_duration_sec == 0:
                                duration_str = "less than a second"
                            elif pause_duration_sec == 1:
                                duration_str = "one second"
                            else:
                                duration_str = f"{pause_duration_sec} seconds"
                            msg = click.style(f"Resumed after {duration_str}", fg="bright_black", italic=True)
                            click.echo(f"{prefix}   {icon_str}{msg}")

                    # Handle undo request (Ctrl+Shift+Z in browser)
                    if response.get("undoRequested"):
                        # Calculate elapsed time for timestamp
                        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                        elapsed_str = format_elapsed(elapsed_ms)
                        if all_steps:
                            undone_step = all_steps.pop()
                            undo_stack.append(undone_step)
                            # Remember the step number before decrementing
                            undone_step_num = step_count
                            step_count -= 1
                            # Format: "----   00:15   󰕌  Undo #0005 set color" (dark grey timestamp)
                            action = undone_step.action
                            # For "set" actions, include the input type (e.g., "set color", "set range")
                            if action == "set" and undone_step.target and undone_step.target.input_type:
                                action = f"set {undone_step.target.input_type}"
                            prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                            undo_icon = get_indicator("undo") or ""
                            icon_str = f"{undo_icon}  " if undo_icon else ""
                            msg = click.style(f"Undo #{undone_step_num:04d} {action}", fg="bright_black", italic=True)
                            click.echo(f"{prefix}   {icon_str}{msg}")
                        else:
                            # Show red icon for "Nothing to undo" (dark grey timestamp)
                            icon_glyph = get_indicator("undo") or ""
                            prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                            icon_str = click.style(f"{icon_glyph}  ", fg="red") if icon_glyph else ""
                            msg = click.style("Nothing to undo", fg="red")
                            click.echo(f"{prefix}   {icon_str}{msg}")

                    # Handle redo request (Ctrl+Shift+Y in browser)
                    if response.get("redoRequested"):
                        # Calculate elapsed time for timestamp
                        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
                        elapsed_str = format_elapsed(elapsed_ms)
                        if undo_stack:
                            redone_step = undo_stack.pop()
                            all_steps.append(redone_step)
                            step_count += 1
                            # Format: "----   00:15   󰑎  Redo #0005 set color" (dark grey timestamp)
                            action = redone_step.action
                            # For "set" actions, include the input type (e.g., "set color", "set range")
                            if action == "set" and redone_step.target and redone_step.target.input_type:
                                action = f"set {redone_step.target.input_type}"
                            prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                            redo_icon = get_indicator("redo") or ""
                            icon_str = f"{redo_icon}  " if redo_icon else ""
                            msg = click.style(f"Redo #{step_count:04d} {action}", fg="bright_black", italic=True)
                            click.echo(f"{prefix}   {icon_str}{msg}")
                        else:
                            # Show red icon for "Nothing to redo" (dark grey timestamp)
                            icon_glyph = get_indicator("redo") or ""
                            prefix = click.style(f"----   {elapsed_str}", fg="bright_black")
                            icon_str = click.style(f"{icon_glyph}  ", fg="red") if icon_glyph else ""
                            msg = click.style("Nothing to redo", fg="red")
                            click.echo(f"{prefix}   {icon_str}{msg}")

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

                            # Display navigation (no indent during recording)
                            nav_event = {"action": "navigate", "url": new_url}
                            display = format_step_for_display(nav_event, step_count, elapsed_ms, indent=False)
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
                            click.echo(format_system_message(f"Recording resumed on {domain}", icon="resume"))
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

                    # Skip event processing if paused (shouldn't happen since browser blocks too)
                    if is_paused:
                        events = []

                    if events:
                        # Reset inactivity tracking when we get events
                        last_activity_time = time.time()
                        inactivity_warning_shown = False

                        # Clear redo stack when new events are recorded
                        # (standard undo/redo behavior: new actions invalidate redo history)
                        if undo_stack:
                            undo_stack.clear()

                    for event in events:
                        # Deduplicate events based on timestamp (prevents duplicates after resume)
                        event_timestamp = event.get("timestamp", 0)
                        if event_timestamp in seen_timestamps:
                            debug_log(f"Skipping duplicate event at timestamp {event_timestamp}")
                            continue
                        seen_timestamps.add(event_timestamp)

                        # Skip Ctrl+C keypresses - this is the stop signal, not a real action
                        if event.get("action") == "keypress":
                            key = event.get("key", "").lower()
                            modifiers = event.get("modifiers", [])
                            if key == "c" and "ctrl" in modifiers:
                                debug_log("Skipping Ctrl+C keypress (stop signal)")
                                continue

                        step = convert_js_event_to_step(event)
                        all_steps.append(step)
                        step_count += 1

                        # Calculate elapsed time from recording start
                        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

                        # Update last known URL for navigate events
                        if event.get("action") == "navigate":
                            last_known_url = event.get("url", last_known_url)

                        # Display table header before first step
                        if not header_shown:
                            click.echo(format_step_header(indent=False))
                            header_shown = True

                        # For upload events, strip the content field before displaying
                        # (prevents large base64 data from interfering with output)
                        display_event = event
                        if event.get("action") == "upload" and event.get("files"):
                            display_event = {**event}
                            display_event["files"] = [
                                {k: v for k, v in f.items() if k != "content"}
                                for f in event["files"]
                            ]

                        # For download events, check for duplicates or changes
                        if event.get("action") == "download" and event.get("download"):
                            download_info = event["download"]
                            filename = download_info.get("filename")  # Already cleaned by JS
                            full_path = download_info.get("full_path")

                            if filename and full_path:
                                checksum = compute_file_checksum(Path(full_path))

                                if checksum and filename in download_checksums:
                                    prev = download_checksums[filename]
                                    if checksum == prev["checksum"]:
                                        # Identical file - mark for discard
                                        download_info["_duplicate_of_step"] = prev["step_number"]
                                    else:
                                        # Different content - mark for rename with step ID
                                        download_info["_differs_from_step"] = prev["step_number"]
                                        download_info["_save_with_step_id"] = step_count
                                elif checksum:
                                    # First download of this filename
                                    download_checksums[filename] = {
                                        "checksum": checksum,
                                        "step_number": step_count,
                                    }

                        # Display real-time feedback with step number and elapsed time (no indent during recording)
                        display = format_step_for_display(display_event, step_count, elapsed_ms, indent=False)
                        click.echo(display)

                        # Show informational message for download duplicates/changes (after the step display)
                        if event.get("action") == "download" and event.get("download"):
                            download_info = event["download"]
                            if download_info.get("_duplicate_of_step"):
                                orig_step = download_info["_duplicate_of_step"]
                                click.echo(format_system_message(
                                    f"This file is identical to the one we downloaded in step #{orig_step:04d}.",
                                    icon="tip"
                                ))
                            elif download_info.get("_differs_from_step"):
                                orig_step = download_info["_differs_from_step"]
                                click.echo(format_system_message(
                                    f"This file differs from the one we downloaded in step #{orig_step:04d}. A copy is saved.",
                                    icon="tip"
                                ))

                        # Show one-time hint for cookie consent dialog Tab navigation
                        if event.get("in_cookie_consent") and not cookie_consent_hint_shown:
                            provider = event.get("cookie_consent_provider", "cookie consent dialog")
                            cookie_consent_provider = provider  # Store for YAML comment
                            cookie_consent_hint_shown = True
                            click.echo(format_system_message(
                                f"Tab landed in a {provider}. "
                                "These dialogs manage focus internally—accessible names may not be captured. "
                                "Replay will still work correctly.",
                                icon="tip"
                            ))

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
                    # Tab is closed, can't retry
                    do_cleanup(allow_retry=False)
                    break

                if consecutive_errors == 10 and not waiting_for_reconnect:
                    # First warning after ~1 second of errors
                    click.echo(format_system_message("Waiting for browser to reconnect…"))
                    waiting_for_reconnect = True
                elif consecutive_errors >= max_consecutive_errors and consecutive_errors % 30 == 0:
                    # Periodic warning every 3 seconds
                    click.echo(format_system_message("Still waiting for browser connection…"))

            except Exception as e:
                # Other errors - log if verbose, otherwise ignore
                consecutive_errors += 1
                debug_log(f"Exception #{consecutive_errors}: {type(e).__name__}: {e}")

            time.sleep(0.1)  # Poll every 100ms

    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


@record.command("tidy")
@click.argument("file", type=click.Path(exists=True), required=False)
@click.option("--dry-run", is_flag=True, help="Preview changes without modifying the file")
@click.option("--force", is_flag=True, help="Replace ALL comments, ignoring user customizations")
@click.option("--no-comments", is_flag=True, help="Skip comment updates")
@click.option("--no-normalize", is_flag=True, help="Skip key order normalization")
@click.option("--no-clean", is_flag=True, help="Skip empty value removal")
@click.option("--quiet", "-q", is_flag=True, help="Only show warnings and summary")
def tidy(file: Optional[str], dry_run: bool, force: bool, no_comments: bool, no_normalize: bool, no_clean: bool, quiet: bool):
    """
    Tidy up a recording file.

    Performs comprehensive cleanup of a recording YAML file.
    If no file is specified, uses the most recently modified recording.

    \b
    Operations (all enabled by default):
    ✓ Validate YAML syntax (abort if invalid)
    ✓ Detect fragile selectors (warnings only)
    ✓ Validate timestamp order (warnings only)
    ✓ Re-number steps sequentially (0001, 0002, 0003...)
    ✓ Enrich comments with assertion info
    ✓ Normalize key order for consistency
    ✓ Remove empty/null values
    ✓ Fix indentation (2 spaces)

    \b
    Examples:
        inspekt record tidy                             # Tidy last modified
        inspekt record tidy recording.yaml              # Full tidy
        inspekt record tidy recording.yaml --dry-run    # Preview changes
        inspekt record tidy recording.yaml --force      # Replace all comments
        inspekt record tidy recording.yaml -q           # Quiet mode
    """
    # Use last modified file if none specified
    if file is None:
        recent = find_most_recent_recording()
        if recent is None:
            click.echo("Error: No file specified and no .yaml files found.", err=True)
            sys.exit(1)
        filepath = recent
        click.echo(f"Using: {filepath.name} (last modified)\n")
    else:
        filepath = Path(file)

    if not quiet:
        if dry_run:
            click.echo(f"Previewing changes for {click.style(filepath.name, bold=True)}...\n")
        else:
            click.echo(f"Tidying up {click.style(filepath.name, bold=True)}...\n")

    try:
        report = tidy_recording(
            filepath,
            dry_run=dry_run,
            force_comments=force,
            skip_comments=no_comments,
            skip_normalize=no_normalize,
            skip_clean=no_clean,
        )

        stats = report["stats"]
        comment_changes = report["comment_changes"]
        warnings = report["warnings"]

        # Show warnings first (always shown)
        if warnings["fragile_selectors"]:
            click.echo(click.style("⚠ Fragile Selectors Detected:", fg="yellow", bold=True))
            for step_num, selector, reason in warnings["fragile_selectors"]:
                step_label = click.style(f"Step {step_num:04d}", fg="cyan")
                click.echo(f"  {step_label}: {reason}")
                selector_preview = selector[:60] + "…" if len(selector) > 60 else selector
                click.echo(f"            {click.style(selector_preview, fg='bright_black')}")
            click.echo()

        if warnings["timestamps"]:
            click.echo(click.style("⚠ Timestamp Issues:", fg="yellow", bold=True))
            for step_num, ts, prev_ts, issue in warnings["timestamps"]:
                step_label = click.style(f"Step {step_num:04d}", fg="cyan")
                click.echo(f"  {step_label}: timestamp {ts}ms is {issue} (previous: {prev_ts}ms)")
            click.echo()

        # Show comment changes (unless quiet)
        if not quiet and comment_changes:
            click.echo(click.style("Comments:", bold=True))
            for change in comment_changes:
                step_num = change["step"]
                old_desc = change["old"]
                new_desc = change["new"]
                change_type = change["type"]

                step_label = click.style(f"Step {step_num:04d}", fg="cyan", bold=True)
                old_truncated = old_desc[:50] + "…" if len(old_desc) > 50 else old_desc
                new_truncated = new_desc[:50] + "…" if len(new_desc) > 50 else new_desc

                if change_type == "enriched":
                    click.echo(f"  {step_label}: {old_truncated}")
                    click.echo(f"           → {click.style(new_truncated, fg='green')}")
                elif change_type == "forced":
                    click.echo(f"  {step_label}: {click.style(old_truncated, fg='red', strikethrough=True)}")
                    click.echo(f"           → {click.style(new_truncated, fg='yellow')}")
                elif change_type == "preserved":
                    click.echo(f"  {step_label}: {old_truncated} {click.style('(preserved)', fg='bright_black')}")
            click.echo()

        # Summary report
        click.echo(click.style("Summary:", bold=True))

        # Build summary parts
        summary_items = []

        if stats["comments_enriched"] > 0:
            summary_items.append(("Comments enriched", stats["comments_enriched"], "green"))
        if stats["comments_preserved"] > 0:
            summary_items.append(("Comments preserved", stats["comments_preserved"], "cyan"))
        if stats["comments_forced"] > 0:
            summary_items.append(("Comments replaced", stats["comments_forced"], "yellow"))
        if stats["steps_renumbered"] > 0:
            summary_items.append(("Steps renumbered", stats["steps_renumbered"], "yellow"))
        if stats["keys_normalized"] > 0:
            summary_items.append(("Keys normalized", stats["keys_normalized"], "blue"))
        if stats["empty_values_removed"] > 0:
            summary_items.append(("Empty values removed", stats["empty_values_removed"], "magenta"))

        # Show what was skipped
        if no_comments:
            summary_items.append(("Comment updates", "skipped", "bright_black"))
        if no_normalize:
            summary_items.append(("Key normalization", "skipped", "bright_black"))
        if no_clean:
            summary_items.append(("Empty cleanup", "skipped", "bright_black"))

        # Warning counts
        if warnings["fragile_selectors"]:
            summary_items.append(("Fragile selectors", len(warnings["fragile_selectors"]), "yellow"))
        if warnings["timestamps"]:
            summary_items.append(("Timestamp issues", len(warnings["timestamps"]), "yellow"))

        # Display summary
        for label, value, color in summary_items:
            value_str = click.style(str(value), fg=color)
            click.echo(f"  {label}: {value_str}")

        click.echo(f"  Total steps: {stats['total_steps']}")

        # Final status
        click.echo()
        if dry_run:
            click.echo(click.style("Dry run complete.", fg="cyan") + " No changes were made.")
        else:
            click.echo(click.style("✓ File tidied successfully.", fg="green"))

    except ValueError as e:
        click.echo(click.style(f"✗ Validation Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
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

    # Sort by creation date (oldest first, newest at bottom)
    recordings.sort(key=lambda r: r.get("created_at") or "")

    # Apply limit (keep the most recent N, which are at the end after sorting)
    if limit:
        recordings = recordings[-limit:]

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
                "modified_at": r["modified_at"].isoformat() if hasattr(r.get("modified_at"), "isoformat") else str(r.get("modified_at")),
                "duration_ms": r["duration_ms"],
                "steps": r["steps"],
                "assertions": r.get("assertions", 0),
                "url": r["url"],
            })
        click.echo(json.dumps(output, indent=2))
        return

    # Table output using Table class
    from inspekt.app.cli.table import Table
    from datetime import datetime

    def format_datetime(dt) -> str:
        """Format datetime as YY/MM/DD HH:MM in local time."""
        if hasattr(dt, "strftime"):
            return dt.strftime("%y/%m/%d %H:%M")
        elif isinstance(dt, str):
            try:
                parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                # Convert to local time
                local_dt = parsed.astimezone()
                return local_dt.strftime("%y/%m/%d %H:%M")
            except:
                return dt[:14] if len(dt) >= 14 else dt
        return "N/A"

    # Find the most recently modified recording
    last_modified_path = None
    if recordings:
        most_recent = max(recordings, key=lambda r: r.get("modified_at") or datetime.min)
        last_modified_path = most_recent["path"]

    # Build rows
    rows = []
    total_steps = 0
    total_assertions = 0
    total_duration_ms = 0
    for r in recordings:
        # Filename only (no path)
        filename = r["name"]

        # Format created and modified dates
        created_str = format_datetime(r.get("created_at"))
        modified_str = format_datetime(r.get("modified_at"))

        # Format duration
        duration_ms = r["duration_ms"]
        duration = format_duration(duration_ms)

        # Get counts
        steps = r["steps"]
        assertions = r.get("assertions", 0)
        total_steps += steps
        total_assertions += assertions
        total_duration_ms += duration_ms

        rows.append({
            "path": r["path"],
            "values": [filename, created_str, modified_str, duration, str(steps), str(assertions)]
        })

    # Create table with title
    table = Table(
        ["File", "Created", "Modified", "Duration", "Steps", "Assertions"],
        title=f"Recordings ({len(rows)})",
        icon="󰕧",
        alignments=["left", "left", "left", "right", "right", "right"]
    )
    table.set_data([r["values"] for r in rows])

    click.echo()
    table.print_header()
    for r in rows:
        # Highlight last modified row (only if there's more than one row)
        is_last_modified = r["path"] == last_modified_path and len(rows) > 1
        table.print_row(r["values"], highlight=is_last_modified)

    # Print summary with totals
    table.print_summary(["Total", "", "", format_duration(total_duration_ms), str(total_steps), str(total_assertions)])
    table.print_footer()

    # Show tip if no assertions exist
    if total_assertions == 0 and len(rows) > 0:
        click.echo()
        from inspekt.app.cli.table import print_hint, _style_with_inline_code
        print_hint("Add assertions to your recordings to verify expected outcomes.")
        doc_link = click.style("http://localhost:8008/guide/recording-replay/#adding-assertions", fg="blue", underline=True)
        click.echo(f"  See {doc_link}")
        click.echo(_style_with_inline_code("  (requires: `inspekt start --docs`)", base_fg="white"))


@record.command("info")
@click.argument("recording_file", type=click.Path(exists=True), required=False, shell_complete=complete_recording_files)
def show_recording(recording_file: Optional[str]):
    """
    Show details of a recording file.

    Displays metadata and step summary for a recording.
    If no file is specified, uses the most recently modified recording.

    \b
    Examples:
        inspekt record info                # Show last modified recording
        inspekt record info login-flow.yaml
    """
    # Use last modified file if none specified
    if recording_file is None:
        recent = find_most_recent_recording()
        if recent is None:
            click.echo("Error: No recording file specified and no .yaml files found.", err=True)
            sys.exit(1)
        filepath = recent
        click.echo(f"Using: {filepath.name} (last modified)\n")
    else:
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

    # Format created date
    created = meta.get("created_at")
    if hasattr(created, "strftime"):
        created_str = created.strftime("%Y-%m-%d %H:%M:%S")
    else:
        created_str = str(created) if created else "N/A"

    # Viewport info
    viewport = meta.get("viewport", {})
    viewport_str = f"{viewport.get('width')}x{viewport.get('height')}" if viewport else None

    # Build metadata rows
    meta_rows = [
        ["File", filepath.name],
        ["URL", meta.get("starting_url", "N/A")],
        ["Created", created_str],
        ["Duration", format_duration(meta.get("duration_ms", 0))],
        ["Steps", str(len(steps))],
    ]
    if viewport_str:
        meta_rows.append(["Viewport", viewport_str])

    # Recording metadata table (no column headers)
    click.echo()
    meta_table = Table(["Field", "Value"], title="Recording", icon="󰐂")
    meta_table.set_data(meta_rows)
    meta_table.print_header(skip_column_headers=True)
    for row in meta_rows:
        meta_table.print_row(row)
    meta_table.print_footer()

    # Step summary by action type
    action_counts: dict[str, int] = {}
    for step in steps:
        action = step.get("action", "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1

    if action_counts:
        # Actions table with icons
        click.echo()
        action_rows = []
        for action, count in sorted(action_counts.items()):
            icon = get_action_icon(action) or ""
            action_rows.append([icon, action, str(count)])

        action_table = Table(["", "Action", "Count"], title="Actions", icon="󰐊")
        action_table.set_data(action_rows)
        action_table.print_header(skip_column_headers=True)
        for row in action_rows:
            action_table.print_row(row)
        action_table.print_footer()

    # Steps preview using shared formatting
    click.echo()
    format_steps_preview(steps, max_steps=10, show_header=True, show_remaining_count=True)

    click.echo(f"\nReplay with: inspekt replay {filepath}")


@record.command("delete")
@click.argument("recording_file", type=click.Path(exists=True), required=False, shell_complete=complete_recording_files)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
def delete_recording(recording_file: Optional[str], force: bool):
    """
    Delete a recording file.

    If no file is specified, uses the most recently modified recording.

    \b
    Examples:
        inspekt record delete                # Delete last modified recording
        inspekt record delete login-flow.yaml
        inspekt record delete --force old-recording.yaml
    """
    # Use last modified file if none specified
    if recording_file is None:
        recent = find_most_recent_recording()
        if recent is None:
            click.echo("Error: No recording file specified and no .yaml files found.", err=True)
            sys.exit(1)
        filepath = recent
        click.echo(f"Using: {filepath.name} (last modified)\n")
    else:
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


@record.command("edit")
@click.argument("recording_file", type=click.Path(exists=True), required=False, shell_complete=complete_recording_files)
def edit_recording(recording_file: Optional[str]):
    """
    Open a recording file in your default editor.

    If no file is specified, uses the most recently modified recording.

    \b
    Examples:
        inspekt record edit                # Edit last modified recording
        inspekt record edit login-flow.yaml
    """
    import subprocess
    import os

    # Use last modified file if none specified
    if recording_file is None:
        recent = find_most_recent_recording()
        if recent is None:
            click.echo("Error: No recording file specified and no .yaml files found.", err=True)
            sys.exit(1)
        filepath = recent
        click.echo(f"Opening: {filepath.name} (last modified)")
    else:
        filepath = Path(recording_file)
        click.echo(f"Opening: {filepath.name}")

    # Use click.edit() which handles $EDITOR, $VISUAL, and fallback
    try:
        click.edit(filename=str(filepath))
    except click.ClickException as e:
        click.echo(f"Error opening editor: {e}", err=True)
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
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Introduction
    click.echo()
    click.secho("  INSPEKT RECORD TUTORIAL", fg="cyan", bold=True)
    click.echo()
    click.echo("  " + "─" * 50)
    click.echo()
    from inspekt.app.cli.table import _style_with_inline_code
    click.echo(_style_with_inline_code("  `inspekt record` allows you to capture an exact", base_fg="white"))
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
        # Inject shared dialog styles
        visual_script = visual_script.replace("DIALOG_STYLES_PLACEHOLDER", DIALOG_STYLES)
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
        click.echo("  Press Enter to see all supported action types…")
        input()
    elif audio_output == "cli":
        # CLI audio: no browser interaction needed
        cli_audio = CLIAudio(volume=audio_volume)
        click.echo()
        click.echo("  Press Enter to hear all action types with audio feedback…")
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
            click.echo("  Press Enter to see all supported action types…")
            input()
        else:
            use_browser_audio = True
            # Prompt to continue - ask user to click in browser first for audio
            click.echo("  To hear sound effects, click anywhere in your browser window,")
            click.echo("  then press Enter here to continue…")
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
        "set": {
            "action": "set",
            "value": "14:35",
            "target": {
                "selector": "input#time",
                "tag": "input",
                "input_type": "time",
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
        "toggle": {
            "action": "toggle",
            "value": "open",
            "target": {
                "selector": "details > summary",
                "accessible_name": "FAQ: Shipping information",
                "tag": "summary",
            },
        },
        "dialog": {
            "action": "dialog",
            "value": "modal",
            "target": {
                "selector": "#confirm-dialog",
                "tag": "dialog",
            },
        },
        "jsdialog": {
            "action": "jsdialog",
            "dialog_type": "confirm",
            "message": "Are you sure you want to proceed?",
            "result": True,
        },
        "upload": {
            "action": "upload",
            "target": {
                "selector": "#profile-pic",
                "tag": "input",
            },
            "files": [
                {
                    "name": "photo.jpg",
                    "type": "image/jpeg",
                    "size": 45678,
                }
            ],
        },
        "download": {
            "action": "download",
            "download": {
                "url": "https://example.com/report.pdf",
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size": 1048576,
                "download_start": 1700000000000,
                "download_end": 1700000005000,
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
        "set": "Set value on native control",
        "keypress": "Press a keyboard shortcut",
        "hover": "Hover over an element",
        "check": "Check a checkbox",
        "uncheck": "Uncheck a checkbox",
        "radio": "Select a radio button",
        "select": "Select from a dropdown",
        "scroll": "Scroll the page",
        "toggle": "Toggle a details disclosure",
        "dialog": "Open or close a modal dialog",
        "jsdialog": "JavaScript alert, confirm, or prompt dialog",
        "upload": "Upload a file",
        "download": "File download completed",
        "plugin": "Run an Inspekt plugin",
        "inspekt": "Run an Inspekt command",
        "failure": "When an action fails",
    }

    # Display simulated recording output
    click.echo()
    click.secho("  Recording started…", fg="green")
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
