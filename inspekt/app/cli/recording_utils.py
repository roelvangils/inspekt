"""
Shared utilities for recording and replay commands.

This module exists to avoid circular imports between record.py and replay.py.
"""

import base64
import re
from pathlib import Path
from typing import Optional

import click


def clean_filename(filename: str) -> str:
    """Remove OS-added indices like ' (1)', ' (2)' from filename.

    When Chrome downloads a file that already exists, it adds indices like:
    - document (1).pdf
    - image (2).png

    This function removes those indices to get the original filename.
    """
    # Match pattern: " (N)" before file extension or at end of filename
    return re.sub(r'\s*\(\d+\)(?=\.[^.]+$|$)', '', filename)


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


def load_external_file_content(step_dict: dict, recording_dir: Path) -> dict:
    """Load external file content before sending step to browser for replay.

    This function modifies step_dict in place, adding external_content field
    to files that have external_path.

    For upload actions with files stored externally (>100KB), this reads the
    file from disk and converts it to base64 for sending to the browser.
    """
    if step_dict.get("action") != "upload" or not step_dict.get("files"):
        return step_dict

    for file_info in step_dict["files"]:
        external_path = file_info.get("external_path")
        if external_path and not file_info.get("content"):
            file_path = recording_dir / external_path
            if file_path.exists():
                try:
                    file_bytes = file_path.read_bytes()
                    base64_data = base64.b64encode(file_bytes).decode()
                    mime_type = file_info.get("type", "application/octet-stream")
                    file_info["external_content"] = f"data:{mime_type};base64,{base64_data}"
                except Exception as e:
                    click.echo(f"Warning: Could not load external file {external_path}: {e}", err=True)
            else:
                click.echo(f"Warning: External file not found: {external_path}", err=True)

    return step_dict
