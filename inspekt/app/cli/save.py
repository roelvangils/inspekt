"""
Page saving command - save current page as offline HTML.

This module provides the 'save' command that captures the current browser tab
as a single HTML file with all resources (CSS, images, fonts) embedded inline.

Uses the SingleFile library (https://github.com/gildas-lormeau/SingleFile)
for accurate page capture that preserves the current DOM state including
JavaScript-rendered content.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import click

from inspekt.app.cli.base import builtin_open
from inspekt.app.cli.util import open_or_download, reveal_or_download
from inspekt.client import BridgeClient


def sanitize_filename(title: str, max_length: int = 100) -> str:
    """
    Create a safe filename from a page title.

    Args:
        title: Page title to sanitize
        max_length: Maximum filename length

    Returns:
        Sanitized filename (without extension)
    """
    if not title:
        title = "Untitled"

    # Remove invalid characters
    cleaned = re.sub(r'[<>:"/\\|?*]', "", title)
    # Replace whitespace with underscores
    cleaned = re.sub(r"\s+", "_", cleaned)
    # Remove leading/trailing underscores
    cleaned = cleaned.strip("_")
    # Limit length
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("_")

    return cleaned or "page"


def extract_domain_from_url(url: str) -> str | None:
    """Extract domain from URL."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        hostname = parsed.netloc or parsed.hostname
        if hostname and ":" in hostname:
            hostname = hostname.split(":")[0]
        # Remove www. prefix for cleaner folder names
        if hostname and hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname
    except Exception:
        return None


def generate_output_path(
    title: str,
    url: str,
    output_dir: Path | None = None,
    filename: str | None = None,
) -> Path:
    """
    Generate the output path for the saved page.

    Args:
        title: Page title
        url: Page URL
        output_dir: Output directory (default: config.paths.downloads/{domain}/)
        filename: Custom filename (optional)

    Returns:
        Path object for the output file
    """
    if filename:
        # User specified a filename
        path = Path(filename)
        if not path.suffix:
            path = path.with_suffix(".html")
        if output_dir and not path.is_absolute():
            path = output_dir / path
        return path

    # Generate filename from title and date
    safe_title = sanitize_filename(title)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    generated_name = f"{safe_title}_{date_str}.html"

    if output_dir:
        return output_dir / generated_name

    # Default: save to downloads directory from config, with domain subfolder
    from inspekt.config import get_paths_config

    paths = get_paths_config()
    downloads_dir = paths["downloads"]

    domain = extract_domain_from_url(url)
    if domain:
        default_dir = downloads_dir / domain
        return default_dir / generated_name

    return downloads_dir / generated_name


@click.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: auto-generated from title)",
)
@click.option(
    "--dir",
    "-d",
    "output_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Output directory (default: current directory)",
)
@click.option("--no-images", is_flag=True, help="Skip embedding images (faster, smaller file)")
@click.option(
    "--remote-images",
    is_flag=True,
    help="Keep images as remote URLs instead of embedding (requires internet to view)",
)
@click.option("--no-styles", is_flag=True, help="Skip removing unused styles (keep all CSS)")
@click.option(
    "--include-scripts", is_flag=True, help="Include JavaScript in saved page (disabled by default)"
)
@click.option("--include-frames", is_flag=True, help="Include iframe content (disabled by default)")
@click.option("--compress", is_flag=True, help="Compress HTML output (remove extra whitespace)")
@click.option("--raw", is_flag=True, help="Save raw page without processing (useful for debugging)")
@click.option(
    "--optimize",
    is_flag=True,
    help="Optimize for smaller file size (removes unused styles/fonts, recommended for large pages)",
)
@click.option("--quiet", "-q", is_flag=True, help="Suppress progress output")
@click.option("--json", "output_json", is_flag=True, help="Output result as JSON (for scripting)")
@click.option("--open", "open_after", is_flag=True, help="Open saved file in default application")
@click.option("--reveal", "reveal_after", is_flag=True, help="Reveal saved file in file explorer")
def save(
    output: str | None,
    output_dir: str | None,
    no_images: bool,
    remote_images: bool,
    no_styles: bool,
    include_scripts: bool,
    include_frames: bool,
    compress: bool,
    raw: bool,
    optimize: bool,
    quiet: bool,
    output_json: bool,
    open_after: bool,
    reveal_after: bool,
):
    """
    Save the current page as a single HTML file.

    Captures the current browser tab with all resources embedded inline using
    the SingleFile library. The saved page represents the CURRENT DOM STATE,
    including any JavaScript-rendered content.

    By default, pages are saved to {downloads}/{domain}/ where {downloads} is
    configured in config.json (default: ~/Downloads) and {domain} is extracted
    from the page URL (e.g. ~/Downloads/github.com/Page_Title.html).

    Features:
    - CSS stylesheets (inlined and deduplicated)
    - Images (converted to base64 data URIs)
    - Fonts (embedded from CSS)
    - Canvas elements (converted to images)
    - SVG graphics (fully preserved)
    - Web fonts (embedded)

    The saved file is a complete, self-contained HTML document that can be
    viewed offline in any browser.

    Examples:
        inspekt save                          # Save to ~/Downloads/{domain}/
        inspekt save -o mypage.html           # Save with custom name
        inspekt save -d ~/archives            # Save to specific directory
        inspekt save --remote-images          # Keep image URLs (smaller file, needs internet)
        inspekt save --no-images              # Skip images entirely (fastest)
        inspekt save --include-scripts        # Include JavaScript
        inspekt save --compress               # Minimize file size
    """
    client = BridgeClient()

    if not client.is_alive():
        if output_json:
            click.echo(json.dumps({"ok": False, "error": "Bridge server is not running"}))
        else:
            from inspekt.app.cli.table import _style_with_inline_code

            click.echo(
                _style_with_inline_code(
                    "Error: Bridge server is not running. Start it with `inspekt start`.",
                    base_fg="red",
                ),
                err=True,
            )
        sys.exit(1)

    # Initialize progress bar variable (will be set inside try block if needed)
    progress_bar = None

    try:
        # Build options for SingleFile
        options = {
            # Image handling
            "removeAlternativeImages": no_images,
            "blockImages": no_images,
            # Keep images as remote URLs (don't convert to base64)
            "saveOriginalURLs": remote_images,
            "networkTimeout": 0 if remote_images else 60000,
            # Style handling
            "removeUnusedStyles": not no_styles,
            "removeUnusedFonts": not no_styles,
            # Script handling
            "removeScripts": not include_scripts,
            "blockScripts": not include_scripts,
            # Frame handling
            "removeFrames": not include_frames,
            # Compression
            "compressHTML": compress,
            "compressCSS": compress,
            # Raw mode
            "saveRawPage": raw,
        }

        # Load SingleFile libraries from disk (same approach as axe-core)
        vendor_dir = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "singlefile"
        library_files = [
            "single-file-bootstrap.js",
            "single-file-hooks-frames.js",
            "single-file.js",
        ]

        singlefile_code_parts = []
        for filename in library_files:
            filepath = vendor_dir / filename
            if not filepath.exists():
                if output_json:
                    click.echo(
                        json.dumps(
                            {"ok": False, "error": f"SingleFile library not found: {filepath}"}
                        )
                    )
                else:
                    click.echo(f"Error: SingleFile library not found: {filepath}", err=True)
                sys.exit(1)
            with builtin_open(filepath, encoding="utf-8") as f:
                singlefile_code_parts.append(f.read())

        singlefile_code = "\n".join(singlefile_code_parts)

        # Progress indicator for non-quiet mode
        progress_bar = None
        if not quiet and not output_json:
            if remote_images:
                label = "Capturing page (remote images)"
            elif no_images:
                label = "Capturing page (no images)"
            else:
                label = "Capturing page"

            # Create a progress bar with indeterminate progress (we'll update manually)
            # Using 100 as a fake length, will complete when done
            progress_bar = click.progressbar(
                length=100,
                label=label,
                show_eta=False,
                show_percent=True,
                fill_char=click.style("█", fg="cyan"),
                empty_char=click.style("░", fg="bright_black"),
            )
            progress_bar.__enter__()
            progress_bar.update(10)  # Show initial progress

        # Combine library + capture script into ONE execute call (same pattern as axe-core)
        # This avoids timeout issues and race conditions
        full_script = f"""(async function() {{
    // Load SingleFile library
    {singlefile_code}

    try {{
        // Check if SingleFile is loaded
        if (typeof singlefile === 'undefined' || typeof singlefile.getPageData !== 'function') {{
            return {{
                ok: false,
                error: 'SingleFile library not loaded. typeof singlefile = ' + (typeof singlefile),
                url: window.location.href
            }};
        }}

        // Build options
        const userOptions = {json.dumps(options)};

        const defaultOptions = {{
            // Style handling - optimize flag enables aggressive cleanup
            removeUnusedStyles: {"true" if optimize else "false"},
            removeUnusedFonts: {"true" if optimize else "false"},
            removeImports: false,
            removeAlternativeFonts: {"true" if optimize else "false"},
            removeAlternativeMedias: {"true" if optimize else "false"},
            compressCSS: {"true" if compress else "false"},

            // Element handling
            removeHiddenElements: {"true" if optimize else "false"},
            removeFrames: false,
            removeScripts: true,
            removeAudioSrc: true,
            removeVideoSrc: false,

            // Image handling
            removeAlternativeImages: {"true" if optimize else "false"},
            groupDuplicateImages: {"false" if remote_images else "true"},
            loadDeferredImages: {"false" if remote_images else "true"},
            loadDeferredImagesMaxIdleTime: {"0" if remote_images else "1500"},
            loadDeferredImagesBlockCookies: false,
            loadDeferredImagesBlockStorage: false,
            loadDeferredImagesKeepZoomLevel: false,

            // Output settings
            saveRawPage: false,
            compressHTML: {"true" if compress else "false"},
            insertCanonicalLink: true,
            insertMetaNoIndex: false,
            insertMetaCSP: true,
            insertSingleFileComment: true,
            includeBOM: false,
            insertTextBody: false,
            resolveFragmentIdentifierURLs: false,
            saveFavicon: true,

            // Blocking
            blockScripts: true,
            blockAudios: true,
            blockVideos: false,

            url: window.location.href
        }};

        const options = {{ ...defaultOptions, ...userOptions }};

        let lastProgress = '';
        options.onprogress = (event) => {{
            if (event.type) lastProgress = event.type;
        }};

        const pageData = await singlefile.getPageData(options, undefined, document, window);

        if (!pageData || !pageData.content) {{
            return {{
                ok: false,
                error: 'SingleFile returned empty content',
                url: window.location.href
            }};
        }}

        const title = pageData.title || document.title || 'Untitled';
        const cleanTitle = title.replace(/[<>:"\\/|?*]/g, '').replace(/\\s+/g, '_').substring(0, 100);
        const date = new Date().toISOString().split('T')[0];
        const filename = cleanTitle + '_' + date + '.html';

        return {{
            ok: true,
            content: pageData.content,
            title: pageData.title || document.title,
            filename: pageData.filename || filename,
            url: window.location.href,
            stats: {{
                contentLength: pageData.content.length,
                lastProgress: lastProgress
            }}
        }};

    }} catch (error) {{
        return {{
            ok: false,
            error: error.message || String(error),
            stack: error.stack,
            url: window.location.href
        }};
    }}
}})()
"""

        result = client.execute(full_script, timeout=180.0)

        # Update progress after capture completes
        if progress_bar:
            progress_bar.update(70)  # Capture complete

        if not result.get("ok"):
            if progress_bar:
                progress_bar.update(20)  # Complete the bar before error
                progress_bar.__exit__(None, None, None)
            error_msg = result.get("error", "Unknown error")
            if output_json:
                click.echo(json.dumps({"ok": False, "error": error_msg}))
            else:
                click.echo(f"Error: {error_msg}", err=True)
            sys.exit(1)

        # Get the result from the script
        page_result = result.get("result", {})

        if not page_result.get("ok"):
            if progress_bar:
                progress_bar.update(20)  # Complete the bar before error
                progress_bar.__exit__(None, None, None)
            error_msg = page_result.get("error", "Failed to capture page")
            if output_json:
                click.echo(
                    json.dumps(
                        {"ok": False, "error": error_msg, "stack": page_result.get("stack", "")}
                    )
                )
            else:
                click.echo(f"Error: {error_msg}", err=True)
                if page_result.get("stack"):
                    click.echo(f"Stack: {page_result['stack']}", err=True)
            sys.exit(1)

        # Get the captured content
        content = page_result.get("content", "")
        title = page_result.get("title", "Untitled")
        url = page_result.get("url", "")
        stats = page_result.get("stats", {})

        if not content:
            if progress_bar:
                progress_bar.update(20)
                progress_bar.__exit__(None, None, None)
            if output_json:
                click.echo(json.dumps({"ok": False, "error": "No content captured"}))
            else:
                click.echo("Error: No content captured", err=True)
            sys.exit(1)

        # Determine output path
        output_path = generate_output_path(
            title=title,
            url=url,
            output_dir=Path(output_dir) if output_dir else None,
            filename=output,
        )

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Update progress before writing
        if progress_bar:
            progress_bar.update(15)  # 95% complete

        # Write the file
        with builtin_open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Complete and close progress bar
        if progress_bar:
            progress_bar.update(5)  # 100% complete
            progress_bar.__exit__(None, None, None)

        # Calculate file size
        file_size = len(content.encode("utf-8"))
        size_str = format_size(file_size)

        if output_json:
            click.echo(
                json.dumps(
                    {
                        "ok": True,
                        "path": str(output_path.absolute()),
                        "title": title,
                        "url": url,
                        "size": file_size,
                        "sizeFormatted": size_str,
                        "stats": stats,
                    },
                    indent=2,
                )
            )
        else:
            if not quiet:
                # Simple output format (tables don't work well with long URLs)
                file_url = output_path.absolute().as_uri()
                click.echo(f"\nSaved {url} ({size_str})")
                click.echo(file_url)
            else:
                # Quiet mode: just output the path for piping
                click.echo(str(output_path.absolute()))

        # Open file if --open flag was set (skip for JSON/quiet modes as they're for piping)
        if open_after and not output_json and not quiet:
            open_or_download(output_path)

        # Reveal file if --reveal flag was set (skip for JSON/quiet modes as they're for piping)
        if reveal_after and not output_json and not quiet:
            reveal_or_download(output_path)

    except FileNotFoundError as e:
        if progress_bar:
            progress_bar.__exit__(None, None, None)
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if progress_bar:
            progress_bar.__exit__(None, None, None)
        if output_json:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
