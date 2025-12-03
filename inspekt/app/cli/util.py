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
from inspekt.client import BridgeClient


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
        click.echo("Error: Bridge server is not running. Start it with: inspekt start", err=True)
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
@click.option("--json", "output_json", is_flag=True, help="Output as JSON (requires --list)")
@click.option("-t", "--timeout", type=float, default=30.0, help="Timeout in seconds (default: 30)")
def download(output, list_only, output_json, timeout):
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
        click.echo("Error: Bridge server is not running. Start it with: inspekt start", err=True)
        sys.exit(1)

    # Execute the find_downloads script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "find_downloads.js"

    if not script_path.exists():
        click.echo(f"Error: find_downloads.js script not found at {script_path}", err=True)
        sys.exit(1)

    click.echo("Scanning page for downloadable files...")

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
                click.echo(json.dumps(json_output, indent=2))
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
            click.echo(f"\nDownloading {len(files_to_download)} files...")
        elif selected_data["type"] == "file":
            # Download file(s) - can be a list
            files_to_download = selected_data["files"]
            click.echo(f"\nDownloading {len(files_to_download)} file(s)...")

        # Create output directory if needed
        downloads_dir.mkdir(parents=True, exist_ok=True)

        # Download files
        success_count = 0
        for file_info in files_to_download:
            filename = file_info["filename"]
            url = file_info["url"]
            output_path = downloads_dir / filename

            try:
                click.echo(f"  Downloading {filename}...")
                response = requests.get(url, timeout=30)
                response.raise_for_status()

                with builtin_open(output_path, "wb") as f:
                    f.write(response.content)

                file_size = len(response.content)
                size_mb = file_size / (1024 * 1024)
                if size_mb >= 1:
                    size_str = f"{size_mb:.1f} MB"
                else:
                    size_str = f"{file_size / 1024:.1f} KB"

                click.echo(f"    Saved to {output_path} ({size_str})")
                success_count += 1

            except Exception as e:
                click.echo(f"    Error downloading {filename}: {e}", err=True)

        click.echo(f"\nDownloaded {success_count} of {len(files_to_download)} files successfully.")

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command(name="md-link")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
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
        click.echo("Error: Bridge server is not running. Start it with: inspekt start", err=True)
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
                output_data = {
                    "url": url,
                    "title": cleaned_title,
                    "raw_title": raw_title,
                    "website_name": website_name,
                    "markdown": md_link_str
                }
                click.echo(json.dumps(output_data, indent=2))
            else:
                click.echo(md_link_str)

        else:
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
