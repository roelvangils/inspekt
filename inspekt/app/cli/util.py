"""
Utility CLI commands for Inspekt.

This module contains utility commands:
- repl: Interactive REPL
- userscript: Show userscript installation instructions
- download: Download page files
- md-link: Get Markdown link for current page
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from inspekt.app.cli.base import builtin_open, format_output
from inspekt.app.cli.exec import _format_console_entry, _get_console_logs_since
from inspekt.app.cli.url_builder import url_scheme
from inspekt.client import BridgeClient
from inspekt.services.formatting_utils import format_filesize


def make_file_link(path: str | Path, display_text: str | None = None) -> str:
    """
    Create an OSC 8 terminal hyperlink for a file path.

    OSC 8 is the standard escape sequence for terminal hyperlinks:
    \\033]8;;URL\\033\\\\TEXT\\033]8;;\\033\\\\

    This makes file paths clickable in terminals that support OSC 8,
    including xterm.js used in the Browser VM control panel.
    """
    path_str = str(path)
    display = display_text or path_str
    # Use file:// URL for local files
    file_url = f"file://{path_str}"
    # OSC 8 escape sequence: \033]8;;URL\033\\TEXT\033]8;;\033\\
    return f"\033]8;;{file_url}\033\\{display}\033]8;;\033\\"


def _handle_vm_download(path: Path) -> bool:
    """
    Handle file download in VM environment.

    Emits an OSC 1337 escape sequence that the control panel's xterm.js
    terminal intercepts to trigger a file download to the host browser.

    This is a shared helper used by both open_or_download() and
    reveal_or_download() since both operations fall back to downloading
    in the VM environment where there's no desktop.

    Args:
        path: Resolved Path object to the file

    Returns:
        True (action always taken in VM context)
    """
    import os

    in_control_panel = os.environ.get('INSPEKT_TERMINAL') == 'control-panel'

    if in_control_panel:
        # VM + control panel: emit escape sequence for download
        # Format: OSC 1337 ; download=<path> BEL
        # The control panel's xterm.js terminal intercepts this sequence
        # and triggers a file download via the control server's /download endpoint
        print(f'\033]1337;download={path}\007', end='')
        print(f'↓ {path.name}')  # User feedback showing download icon
    else:
        # VM but not in control panel (e.g., docker exec)
        # OSC 1337 won't work - inform user how to download
        click.echo(f'📁 {path}')
        from inspekt.app.cli.table import print_hint
        print_hint('Use the control panel terminal (port 6080) for automatic downloads.')
    return True


def open_or_download(path: str | Path) -> bool:
    """
    Open a file in the default application, or download it if in VM.

    In the VM environment (INSPEKT_ISOLATED=1), files cannot be opened
    with xdg-open because there's no desktop environment. Instead, emit
    an OSC 1337 escape sequence that the control panel's terminal
    intercepts to trigger a download to the host browser.

    Note: OSC 1337 downloads only work in the control panel's xterm.js
    terminal, not in docker exec sessions. The terminal-server.py sets
    INSPEKT_TERMINAL=control-panel to indicate the proper terminal.

    Args:
        path: Path to the file to open/download

    Returns:
        True if action was taken, False if file doesn't exist
    """
    from inspekt.config import is_isolated_mode

    path = Path(path).resolve()

    if not path.exists():
        return False

    if is_isolated_mode():
        return _handle_vm_download(path)

    # Normal environment: open with default application
    click.launch(str(path))
    return True


def reveal_or_download(path: str | Path) -> bool:
    """
    Reveal a file in the system file explorer, or download it if in VM.

    In the VM environment (INSPEKT_ISOLATED=1), files cannot be revealed
    because there's no desktop environment. Instead, emit an OSC 1337
    escape sequence that triggers a download (same behavior as open_or_download).

    In normal environments:
    - macOS: Opens Finder with the file selected (open -R)
    - Windows: Opens Explorer with the file selected
    - Linux: Opens the containing folder in the default file manager

    Args:
        path: Path to the file to reveal/download

    Returns:
        True if action was taken, False if file doesn't exist
    """
    import platform
    import subprocess
    from inspekt.config import is_isolated_mode

    path = Path(path).resolve()

    if not path.exists():
        return False

    if is_isolated_mode():
        return _handle_vm_download(path)

    # Normal environment: reveal in file explorer
    system = platform.system()

    try:
        if system == 'Darwin':
            # macOS: open -R reveals the file in Finder with the file selected
            subprocess.run(['open', '-R', str(path)], check=True)
        elif system == 'Windows':
            # Windows: explorer /select,<path> reveals file in Explorer
            # Note: Path must be joined with /select, (no space)
            # Note: explorer.exe returns exit code 1 even on success, so don't use check=True
            subprocess.run(['explorer', f'/select,{path}'])
        else:
            # Linux: open the containing directory (can't select specific file easily)
            # Use xdg-open to open parent directory in default file manager
            subprocess.run(['xdg-open', str(path.parent)], check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        # Fallback: just open the parent directory
        try:
            click.launch(str(path.parent))
            return True
        except Exception:
            return False


def _vm_copyable_signal(text: str) -> None:
    """Signal the control panel that a copyable code block was just printed.

    Posts the raw (unformatted) text to the control server's /copyable endpoint,
    then emits an OSC escape sequence so the control panel can show a copy button.
    """
    import json
    import sys
    import urllib.request

    try:
        req = urllib.request.Request(
            "http://localhost:8888/copyable",
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
        sys.stdout.write("\033]1337;copyable\007")
        sys.stdout.flush()
    except Exception:
        pass  # Best-effort


def _vm_data_signal(json_text: str | None, table_md: str | None, summary: str) -> None:
    """Signal the control panel that a command printed a structured data table.

    Posts a payload to /data and emits OSC 1337 ``data`` so the terminal
    can render a toast with [Table] / [JSON] buttons. Either ``json_text``
    or ``table_md`` may be None — the frontend only renders the buttons
    for which a payload exists. Best-effort, silently no-ops on failure.
    """
    import json
    import sys
    import urllib.request

    try:
        payload = {
            "json": json_text or "",
            "table_md": table_md or "",
            "summary": summary or "",
        }
        req = urllib.request.Request(
            "http://localhost:8888/data",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
        sys.stdout.write("\033]1337;data\007")
        sys.stdout.flush()
    except Exception:
        pass  # Best-effort


def _vm_clipboard_relay(text: str) -> None:
    """Post clipboard text to the control server and signal the control panel.

    In the VM, clipboard copying needs two hops:
    1. HTTP POST to the control server (reliable, handles large payloads)
    2. Short OSC escape sequence through the terminal to signal the control panel
       to fetch the text and call navigator.clipboard.writeText()
    """
    import json
    import sys
    import urllib.request

    try:
        # Post text to control server clipboard relay
        req = urllib.request.Request(
            "http://localhost:8888/clipboard",
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
        # Signal the control panel terminal to fetch and copy
        sys.stdout.write("\033]1337;clipboard\007")
        sys.stdout.flush()
    except Exception:
        pass  # Best-effort; xclip still handles VM-internal clipboard


def copy_text_to_clipboard(text: str) -> bool:
    """
    Copy text to the system clipboard.

    Works cross-platform:
    - macOS: Uses pbcopy
    - Linux: Uses xclip (must be installed)
    - Windows: Uses clip

    In the VM control panel terminal, also emits OSC 52 to bridge
    the clipboard to the host browser.

    Args:
        text: Text string to copy

    Returns:
        True if successful, False otherwise
    """
    import os
    import platform
    import subprocess

    # In VM: relay via control server so the host browser gets the text.
    # Skip xclip entirely — X11 clipboard semantics cause xclip to block
    # indefinitely (it stays alive to serve paste requests as selection owner).
    from inspekt.config import is_isolated_mode
    if is_isolated_mode():
        if os.environ.get("INSPEKT_TERMINAL") == "control-panel":
            _vm_clipboard_relay(text)
        return True

    system = platform.system()

    try:
        if system == "Darwin":  # macOS
            subprocess.run(
                ["pbcopy"],
                input=text.encode("utf-8"),
                check=True,
                capture_output=True,
            )
            return True

        elif system == "Linux":
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode("utf-8"),
                    check=True,
                    capture_output=True,
                    timeout=5,  # Prevent hanging if X display is unavailable
                )
                return True
            except subprocess.TimeoutExpired:
                click.echo(
                    "Warning: xclip timed out (no X display?)",
                    err=True,
                )
                return False
            except FileNotFoundError:
                click.echo(
                    "Error: xclip not installed. Install with: sudo apt install xclip",
                    err=True,
                )
                return False

        elif system == "Windows":
            subprocess.run(
                ["clip"],
                input=text.encode("utf-16"),  # Windows clip expects UTF-16
                check=True,
                capture_output=True,
            )
            return True

        else:
            click.echo(f"Clipboard not supported on {system}", err=True)
            return False

    except subprocess.CalledProcessError as e:
        click.echo(f"Error copying to clipboard: {e}", err=True)
        return False
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        return False


def copy_image_to_clipboard(image_data: bytes, format: str = "png") -> bool:
    """
    Copy image data directly to the system clipboard.

    Works cross-platform:
    - macOS: Uses osascript with a temporary file
    - Linux: Uses xclip (must be installed)

    Args:
        image_data: Raw image bytes (PNG recommended for best compatibility)
        format: Image format ('png', 'jpg', 'webp')

    Returns:
        True if successful, False otherwise
    """
    import platform
    import subprocess
    import tempfile

    system = platform.system()

    if system == "Darwin":  # macOS
        # osascript needs a file path, so use a temp file
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
            f.write(image_data)
            temp_path = f.name
        try:
            script = f'set the clipboard to (read (POSIX file "{temp_path}") as «class PNGf»)'
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False
        finally:
            Path(temp_path).unlink(missing_ok=True)

    elif system == "Linux":
        # xclip can read from stdin
        mime_type = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}.get(
            format, "image/png"
        )
        try:
            subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", mime_type],
                input=image_data,
                check=True,
                capture_output=True,
            )
            return True
        except FileNotFoundError:
            # xclip not installed
            click.echo(
                "Error: xclip not installed. Install with: sudo apt install xclip",
                err=True,
            )
            return False
        except subprocess.CalledProcessError:
            return False

    else:
        click.echo(f"Clipboard not supported on {system}", err=True)
        return False


@click.command()
def repl():
    """
    Start an interactive REPL session.

    Execute JavaScript interactively. Console output is shown automatically.
    Type 'exit' or press Ctrl+D to quit.
    """
    from datetime import datetime, timezone

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    click.echo("Inspekt REPL - Type JavaScript code, 'exit' to quit")
    click.echo("")

    # Get initial page info
    try:
        result = client.execute("({url: location.href, title: document.title})")
        if result.get("ok"):
            data = result.get("result", {})
            click.echo(
                f"Connected to: {data.get('title', 'Unknown')} ({data.get('url', 'Unknown')})"
            )
            click.echo("")
    except Exception:
        pass

    while True:
        try:
            code = click.prompt("inspekt>", prompt_suffix=" ", default="", show_default=False)

            if not code.strip():
                continue

            if code.strip().lower() in ["exit", "quit"]:
                break

            try:
                # Get timestamp before execution
                before_ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

                result = client.execute(code, timeout=10.0)

                # Show console output
                console_entries = _get_console_logs_since(before_ts)
                if console_entries:
                    for entry in console_entries:
                        click.echo(_format_console_entry(entry))

                # Show return value
                output = format_output(result, "auto")
                if output and output.strip():
                    click.echo(click.style("← ", dim=True) + output)

            except (ConnectionError, TimeoutError, RuntimeError) as e:
                click.echo(f"Error: {e}", err=True)

        except (EOFError, KeyboardInterrupt):
            click.echo("")
            break

    click.echo("Goodbye!")


@click.command()
def userscript():
    """Display the userscript that needs to be installed in your browser."""
    script_path = Path(__file__).parent.parent.parent / "userscript.js"

    if script_path.exists():
        click.echo(f"Userscript location: {script_path}")
        click.echo("")
        click.echo("To install:")
        click.echo("1. Install a userscript manager (Tampermonkey, Greasemonkey, Violentmonkey)")
        click.echo("2. Create a new script and paste the contents of userscript.js")
        click.echo("3. Save and enable the script")
        click.echo("")
        click.echo("Or use: cat userscript.js | pbcopy  (to copy to clipboard on macOS)")
    else:
        click.echo(f"Error: userscript.js not found at {script_path}", err=True)
        sys.exit(1)


@click.command()
@click.option(
    "-o",
    "--output",
    type=click.Path(),
    default=None,
    help="Output directory (default: ~/Downloads/<domain>)",
)
@click.option("--list", "list_only", is_flag=True, help="Only list files without downloading")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON (requires --list)")
@click.option("-t", "--timeout", type=float, default=30.0, help="Timeout in seconds (default: 30)")
@click.option("--open", "open_after", is_flag=True, help="Open downloaded file in default application")
@click.option("--reveal", "reveal_after", is_flag=True, help="Reveal downloaded file in file explorer")
def download(output, list_only, output_json, timeout, open_after, reveal_after):
    """
    Find and download files from the current page.

    Discovers images, PDFs, videos, audio files, documents and archives.
    Uses interactive selection with gum choose.

    Examples:

        inspekt download

        inspekt download --output ~/Downloads

        inspekt download --list
    """
    import requests

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Execute the find_downloads script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "find_downloads.js"

    if not script_path.exists():
        click.echo(f"Error: find_downloads.js script not found at {script_path}", err=True)
        sys.exit(1)

    click.echo("Scanning page for downloadable files…")

    try:
        result = client.execute_file(str(script_path), timeout=timeout)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        result_data = result.get("result", {})

        # Handle new format with url and files
        if isinstance(result_data, dict) and "files" in result_data:
            files_by_category = result_data["files"]
            page_url = result_data.get("url", "")
        else:
            # Fallback for old format
            files_by_category = result_data
            page_url = ""

        # Count total files
        total_files = sum(len(files) for files in files_by_category.values())

        if total_files == 0:
            click.echo("No downloadable files found on this page.")
            return

        # Determine output directory
        if output is None:
            # Default: ~/Downloads/<domain>
            try:
                from urllib.parse import urlparse

                domain = urlparse(page_url).hostname or "unknown"
                domain = domain.replace("www.", "")  # Remove www. prefix
                downloads_dir = Path.home() / "Downloads" / domain
            except Exception:
                downloads_dir = Path.home() / "Downloads" / "inspekt-downloads"
        else:
            downloads_dir = Path(output)

        # Build options list for gum choose
        options = []
        option_map = {}  # Map display text to actual data

        # Category labels (lowercase)
        category_names = {
            "images": "images",
            "pdfs": "PDF documents",
            "videos": "videos",
            "audio": "audio files",
            "documents": "documents",
            "archives": "archives",
        }

        # Add "Download all" options per category
        for category, files in files_by_category.items():
            if files:
                count = len(files)
                display = f"Download all {category_names.get(category, category)} ({count} files)"
                options.append(display)
                option_map[display] = {"type": "category", "category": category, "files": files}

        # Add separator
        if options:
            separator = "─" * 60
            options.append(separator)
            option_map[separator] = {"type": "separator"}

        # Add individual files grouped by category
        for category, files in files_by_category.items():
            if files:
                # Add category header
                header = f"--- {category_names.get(category, category.upper())} ---"
                options.append(header)
                option_map[header] = {"type": "header"}

                # Add individual files
                for file_info in files:
                    filename = file_info["filename"]
                    url = file_info["url"]

                    # Try to get file size if in list mode
                    display = f"  {filename}"
                    options.append(display)
                    option_map[display] = {
                        "type": "file",
                        "filename": filename,
                        "url": url,
                        "category": category,
                    }

        # List only mode
        if list_only:
            if output_json:
                # Build JSON output
                json_output = {
                    "total": total_files,
                    "url": page_url,
                    "files": files_by_category
                }
                from inspekt.app.cli.table import print_json
                print_json(json_output, summary=f"{total_files} files")
            else:
                click.echo(f"\nFound {total_files} downloadable files:\n")
                for option in options:
                    if option_map.get(option, {}).get("type") not in ["separator", "category"]:
                        click.echo(option)
            return

        # Simple numbered list selection
        click.echo(f"\nFound {total_files} files. Select what to download:\n")

        # Build simple menu
        menu_options = []

        # Find largest image if we have images
        largest_image = None
        if files_by_category.get("images"):
            images_with_dims = [
                img
                for img in files_by_category["images"]
                if img.get("width", 0) > 0 and img.get("height", 0) > 0
            ]
            if images_with_dims:
                # Find image with largest area
                largest_image = max(
                    images_with_dims, key=lambda img: img.get("width", 0) * img.get("height", 0)
                )

        # Add largest image option first
        if largest_image:
            width = largest_image.get("width", 0)
            height = largest_image.get("height", 0)
            menu_options.append(
                {
                    "text": f"Download the largest image ({width}×{height}px)",
                    "data": {"type": "file", "files": [largest_image]},
                }
            )

        # Add category download options
        for category, files in files_by_category.items():
            if files:
                count = len(files)
                menu_options.append(
                    {
                        "text": f"Download all {category_names.get(category, category)} ({count} files)",
                        "data": {"type": "category", "category": category, "files": files},
                    }
                )

        # Display menu
        for i, opt in enumerate(menu_options, 1):
            click.echo(f" {i}. {opt['text']}")

        click.echo("\nFiles will be saved to:")
        click.echo(f"{downloads_dir}\n")

        try:
            choice = click.prompt("Enter number to download (0 to cancel)", type=int, default=0)

            if choice == 0:
                click.echo("Cancelled.")
                return

            if choice < 1 or choice > len(menu_options):
                click.echo("Invalid selection.")
                return

            selected_data = menu_options[choice - 1]["data"]

        except (KeyboardInterrupt, EOFError):
            click.echo("\nCancelled.")
            return
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            return

        # Process selection (selected_data already set above)
        if not selected_data:
            click.echo("Invalid selection.")
            return

        # Prepare download list
        files_to_download = []

        if selected_data["type"] == "category":
            # Download all files in category
            files_to_download = selected_data["files"]
            click.echo(f"\nDownloading {len(files_to_download)} files…")
        elif selected_data["type"] == "file":
            # Download file(s) - can be a list
            files_to_download = selected_data["files"]
            click.echo(f"\nDownloading {len(files_to_download)} file(s)…")

        # Create output directory if needed
        downloads_dir.mkdir(parents=True, exist_ok=True)

        # In VM, route downloads through mitmproxy (inspekt user has no direct outbound access)
        from inspekt.config import is_isolated_mode
        _download_kwargs = dict(
            proxies={"http": "http://localhost:8080", "https": "http://localhost:8080"},
            verify=False,
        ) if is_isolated_mode() else {}

        # Download files
        success_count = 0
        for file_info in files_to_download:
            filename = file_info["filename"]
            url = file_info["url"]
            output_path = downloads_dir / filename

            try:
                click.echo(f"  Downloading {filename}…")
                response = requests.get(url, timeout=30, **_download_kwargs)
                response.raise_for_status()

                with builtin_open(output_path, "wb") as f:
                    f.write(response.content)

                file_size = len(response.content)
                size_str = format_filesize(file_size)

                click.echo(f"    Saved to {make_file_link(output_path)} ({size_str})")
                success_count += 1

            except Exception as e:
                click.echo(f"    Error downloading {filename}: {e}", err=True)

        click.echo(f"\nDownloaded {success_count} of {len(files_to_download)} files successfully.")

        # Open file or directory if --open flag was set
        if open_after and success_count > 0:
            if success_count == 1:
                # Open the single downloaded file
                open_or_download(output_path)
            else:
                # Multiple files: open the downloads directory
                open_or_download(downloads_dir)

        # Reveal file or directory if --reveal flag was set
        if reveal_after and success_count > 0:
            if success_count == 1:
                # Reveal the single downloaded file
                reveal_or_download(output_path)
            else:
                # Multiple files: reveal the downloads directory
                reveal_or_download(downloads_dir)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command(name="md-link")
@url_scheme("md-link", defaults={"output_json": False})
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
def md_link(output_json):
    """
    Get Markdown link for the current page.

    Returns [title](url) format with cleaned page title.
    Strips website name from title (splits on " |", " -", " –").

    Examples:

        inspekt md-link

        inspekt md-link --json
    """
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Get current page URL and title
    code = """
    ({
        url: location.href,
        title: document.title
    })
    """

    try:
        result = client.execute(code)

        if result.get("ok"):
            data = result.get("result") or {}

            if not data:
                click.echo("Error: No data returned from browser.", err=True)
                sys.exit(1)

            url = data.get("url", "")
            raw_title = data.get("title", "")

            # Clean the title - strip website name
            cleaned_title = raw_title
            website_name = ""

            # Try splitting on common separators
            for separator in [" | ", " - ", " – ", " — "]:
                if separator in raw_title:
                    parts = raw_title.split(separator)
                    # Use the first part as the clean title, last part as website name
                    cleaned_title = parts[0].strip()
                    website_name = parts[-1].strip()
                    break

            # Create markdown link
            md_link_str = f"[{cleaned_title}]({url})"

            if output_json:
                from inspekt.app.cli.table import print_json
                output_data = {
                    "url": url,
                    "title": cleaned_title,
                    "raw_title": raw_title,
                    "website_name": website_name,
                    "markdown": md_link_str
                }
                print_json(output_data, summary="markdown link")
            else:
                click.echo(md_link_str)

        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
