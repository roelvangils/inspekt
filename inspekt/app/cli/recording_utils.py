"""
Shared utilities for recording and replay commands.

This module exists to avoid circular imports between record.py and replay.py.
"""

import base64
import re
import sys
from pathlib import Path
from typing import Optional

import click

# Terminal control for suppressing keyboard echo during recording/replay (Unix-only)
try:
    import termios
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False


class TerminalEchoSuppressor:
    """Suppress keyboard echo in the terminal during recording/replay.

    This prevents escape sequences (like ^[[Z for Shift+Tab) from appearing
    in the terminal when the user accidentally types while the terminal
    is focused instead of the browser.

    Only Ctrl+C (handled by signal) will still work to stop the operation.
    """

    def __init__(self):
        self.original_settings = None
        self.fd = None

    def suppress(self) -> bool:
        """Start suppressing keyboard echo. Returns True if successful."""
        if not HAS_TERMIOS:
            return False

        try:
            # Check if stdin is a TTY (won't work in pipes/redirects)
            if not sys.stdin.isatty():
                return False

            self.fd = sys.stdin.fileno()
            self.original_settings = termios.tcgetattr(self.fd)

            # Set terminal to cbreak mode (no echo, char-by-char input)
            # But we don't actually read input - we just prevent echo
            new_settings = termios.tcgetattr(self.fd)
            # Disable echo (ECHO) and canonical mode (ICANON)
            new_settings[3] = new_settings[3] & ~(termios.ECHO | termios.ICANON)
            # Set minimum chars to 0 and timeout to 0 (non-blocking)
            new_settings[6][termios.VMIN] = 0
            new_settings[6][termios.VTIME] = 0
            termios.tcsetattr(self.fd, termios.TCSANOW, new_settings)
            return True
        except Exception:
            self.original_settings = None
            return False

    def restore(self):
        """Restore original terminal settings."""
        if self.original_settings is not None and self.fd is not None:
            try:
                termios.tcsetattr(self.fd, termios.TCSANOW, self.original_settings)
            except Exception:
                pass
            self.original_settings = None


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

    Searches for files matching standard naming conventions:
    - 'inspekt_*.yaml' (current naming convention)
    - 'recording_*.yaml' (legacy naming convention)

    Falls back to any '*.yaml' file if none of the above are found.
    Returns the most recently modified file across all matching patterns.

    Returns:
        Path to the most recent recording file, or None if not found.
    """
    cwd = Path.cwd()

    # Collect files from both naming conventions
    recording_files = list(cwd.glob("inspekt_*.yaml"))
    recording_files.extend(cwd.glob("recording_*.yaml"))

    # Fall back to any YAML file if no standard-named files found
    if not recording_files:
        recording_files = list(cwd.glob("*.yaml"))

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
