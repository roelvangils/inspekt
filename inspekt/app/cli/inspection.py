"""
Inspection commands - Inspect elements, view details, and capture screenshots.

This module provides commands for element inspection and screenshot capture:
- inspect: Select and inspect elements
- inspected: View inspected element details
- screenshot: Capture element screenshots
"""

import base64
import json
import sys
from datetime import datetime
from pathlib import Path

import click

from inspekt.app.cli.icons import get_section_icon, warning as warn_icon
from inspekt.app.cli.selection import html_output_options
from inspekt.config import get_screenshot_config
from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader

# Save built-in open function before it gets shadowed by Click commands
_builtin_open = open


@click.command()
@click.argument("selector", required=False)
@click.pass_context
def inspect(ctx, selector):
    """
    Select an element and show its details.

    If no selector is provided, shows details of the currently selected element.

    Examples:
        inspekt inspect "h1"              # Select and show details
        inspekt inspect "#header"
        inspekt inspect ".main-content"
        inspekt inspect                   # Show currently selected element
    """
    executor = BridgeExecutor()
    executor.ensure_server_running()

    # If no selector provided, just show the currently marked element
    if not selector:
        # Redirect to 'inspected' command
        return ctx.invoke(inspected)

    # Mark the element
    mark_code = f"""
    (function() {{
        const el = document.querySelector('{selector}');
        if (!el) {{
            return {{ error: 'Element not found: {selector}' }};
        }}

        // Store reference
        window.__ZEN_INSPECTED_ELEMENT__ = el;

        // Highlight it briefly
        const originalOutline = el.style.outline;
        el.style.outline = '3px solid #0066ff';
        setTimeout(() => {{
            el.style.outline = originalOutline;
        }}, 1000);

        return {{ ok: true, message: 'Element marked for inspection' }};
    }})()
    """

    try:
        result = executor.execute(mark_code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if response.get("error"):
            click.echo(f"Error: {response['error']}", err=True)
            sys.exit(1)

        click.echo(f"Selected element: {selector}")

        # Now show details immediately by calling inspected
        click.echo("")
        return ctx.invoke(inspected)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def get_inspected_data():
    """Helper function to get inspected element data from browser."""
    executor = BridgeExecutor()
    loader = ScriptLoader()

    executor.ensure_server_running()

    # Load the get_inspected.js script
    try:
        code = loader.load_script_sync("get_inspected.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        result = executor.execute(code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if response.get("error"):
            return {"error": response["error"], "hint": response.get("hint")}

        return response

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def display_inspected_info(response, output_json=False):
    """Display inspected element info (the default output)."""
    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        else:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
                from inspekt.app.cli.table import print_hint
                print_hint(response['hint'])
        sys.exit(1)

    # JSON output
    if output_json:
        click.echo(json.dumps(response, indent=2))
        return

    # Display info
    click.echo(f"Tag:      <{response['tag']}>")
    click.echo(f"Selector: {response['selector']}")

    if response.get("parentTag"):
        click.echo(f"Parent:   <{response['parentTag']}>")

    if response.get("id"):
        click.echo(f"ID:       {response['id']}")

    if response.get("classes") and len(response["classes"]) > 0:
        click.echo(f"Classes:  {', '.join(response['classes'])}")

    if response.get("textContent"):
        text = response["textContent"]
        if len(text) > 60:
            text = text[:60] + "..."
        click.echo(f"Text:     {text}")

    # Selection source
    selection_source = response.get("selectionSource", "unknown")
    if selection_source != "unknown":
        source_labels = {
            "panel": "Inspekt panel picker",
            "devtools": "Chrome DevTools inspector"
        }
        source_label = source_labels.get(selection_source, selection_source)
        click.echo(f"\nSelected via: {click.style(source_label, fg='cyan')}")

        # Show timestamp if available
        selection_time = response.get("selectionTimestamp")
        if selection_time:
            dt = datetime.fromtimestamp(selection_time / 1000)
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            click.echo(f"Selected at:  {time_str}")

    # Dimensions
    dim = response["dimensions"]
    dim_icon = get_section_icon("dimensions") or ""
    dim_prefix = f"{dim_icon} " if dim_icon else ""
    click.echo(f"\n{dim_prefix}Dimensions:")
    click.echo(f"  Position: x={dim['left']}, y={dim['top']}")
    click.echo(f"  Size:     {dim['width']}×{dim['height']}px")
    click.echo(
        f"  Bounds:   top={dim['top']}, right={dim['right']}, bottom={dim['bottom']}, left={dim['left']}"
    )

    # Visibility
    vis = response.get("visibilityDetails", {})
    click.echo("\nVisibility:")
    click.echo(f"  Visible:     {'Yes' if response.get('visible') else 'No'}")
    click.echo(f"  In viewport: {'Yes' if vis.get('inViewport') else 'No'}")
    if vis.get("displayNone"):
        click.echo("  Issue:       display: none")
    if vis.get("visibilityHidden"):
        click.echo("  Issue:       visibility: hidden")
    if vis.get("opacityZero"):
        click.echo("  Issue:       opacity: 0")
    if vis.get("offScreen"):
        click.echo("  Issue:       positioned off-screen")

    # Accessibility
    a11y = response.get("accessibility", {})
    a11y_icon = get_section_icon("accessibility") or ""
    a11y_prefix = f"{a11y_icon} " if a11y_icon else ""
    click.echo(f"\n{a11y_prefix}Accessibility:")
    click.echo(f"  Role:            {a11y.get('role', 'N/A')}")

    # Accessible Name (computed)
    accessible_name = a11y.get("accessibleName", "")
    name_source = a11y.get("accessibleNameSource", "none")
    if accessible_name:
        # Truncate if too long
        display_name = (
            accessible_name if len(accessible_name) <= 50 else accessible_name[:50] + "..."
        )
        click.echo(f'  Accessible Name: "{display_name}"')
        click.echo(f"  Name computed from: {name_source}")
    else:
        click.echo("  Accessible Name: (none)")
        if name_source == "missing alt attribute":
            click.echo(f"  {warn_icon('Warning: Image missing alt attribute')}")
        elif name_source == "none":
            click.echo(f"  {warn_icon('Warning: No accessible name found')}")

    if a11y.get("ariaLabel"):
        click.echo(f"  ARIA Label:      {a11y['ariaLabel']}")
    if a11y.get("ariaLabelledBy"):
        click.echo(f"  ARIA LabelledBy: {a11y['ariaLabelledBy']}")
    if a11y.get("alt"):
        click.echo(f"  Alt text:        {a11y['alt']}")
    click.echo(f"  Focusable:       {'Yes' if a11y.get('focusable') else 'No'}")
    if a11y.get("tabIndex") is not None:
        click.echo(f"  Tab index:       {a11y['tabIndex']}")
    if a11y.get("disabled"):
        click.echo("  Disabled:        Yes")
    if a11y.get("ariaHidden"):
        click.echo(f"  ARIA Hidden:     {a11y['ariaHidden']}")

    # Semantic info
    semantic = response.get("semantic", {})
    if (
        semantic.get("isInteractive")
        or semantic.get("isFormElement")
        or semantic.get("isLandmark")
    ):
        click.echo("\nSemantic:")
        if semantic.get("isInteractive"):
            click.echo("  Interactive element")
        if semantic.get("isFormElement"):
            click.echo("  Form element")
        if semantic.get("isLandmark"):
            click.echo("  Landmark element")
        if semantic.get("hasClickHandler"):
            click.echo("  Has click handler")

    # Children
    click.echo("\nStructure:")
    click.echo(f"  Children: {response.get('childCount', 0)}")

    # Styles
    styles_icon = get_section_icon("styles") or ""
    styles_prefix = f"{styles_icon} " if styles_icon else ""
    click.echo(f"\n{styles_prefix}Styles:")
    for key, value in response["styles"].items():
        click.echo(f"  {key}: {value}")

    # Attributes
    if response.get("attributes"):
        click.echo("\nAttributes:")
        for key, value in response["attributes"].items():
            if len(str(value)) > 50:
                value = str(value)[:50] + "..."
            click.echo(f"  {key}: {value}")


@click.group(invoke_without_command=True)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def inspected(ctx, output_json):
    """
    Get information about the currently inspected element.

    Shows details about the element from DevTools inspection or from 'inspekt inspect'.

    To capture element from DevTools:
        1. Right-click element → Inspect
        2. In DevTools Console: inspektStore()
        3. Run: inspekt inspected

    Or select programmatically:
        inspekt inspect "h1"
        inspekt inspected

    Subcommands:
        inspekt inspected html      Get element as HTML
        inspekt inspected markdown  Get element as Markdown
        inspekt inspected text      Get element text content
    """
    # If no subcommand is provided, show element info (default behavior)
    if ctx.invoked_subcommand is None:
        response = get_inspected_data()
        display_inspected_info(response, output_json=output_json)


@inspected.command()
@click.option("--raw", is_flag=True, help="Output only the raw text without formatting")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def text(raw, copy, output_json):
    """Get the text content of the inspected element."""
    from inspekt.app.cli.util import copy_text_to_clipboard

    response = get_inspected_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not raw:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
                from inspekt.app.cli.table import print_hint
                print_hint(response['hint'])
        sys.exit(1)

    # Get text content - prefer fullTextContent (full text) over textContent (truncated)
    text_content = response.get("fullTextContent", response.get("textContent", ""))

    # Copy to clipboard
    if copy:
        if copy_text_to_clipboard(text_content):
            click.echo(f"✓ Copied {len(text_content)} characters to clipboard", err=True)
        sys.exit(0)

    # JSON mode
    if output_json:
        output = {
            "hasElement": True,
            "text": text_content,
            "length": len(text_content),
            "tag": response.get("tag"),
            "selector": response.get("selector")
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the text
    if raw:
        click.echo(text_content.rstrip())
        return

    # Formatted display
    if len(text_content) > 200:
        click.echo(f"Text Content (showing first 200 of {len(text_content)} characters):\n")
        click.echo(f'"{text_content[:200]}…"\n')
    else:
        click.echo(f"Text Content ({len(text_content)} characters):\n")
        click.echo(f'"{text_content}"\n')

    click.echo(f"Element:  <{response.get('tag')}> {response.get('selector', '')}")


@inspected.command()
@click.option("--raw", is_flag=True, help="Output only the raw Markdown without formatting")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def markdown(raw, copy, output_json):
    """Get the inspected element as Markdown (converted from HTML)."""
    from inspekt.app.cli.selection import html_to_markdown
    from inspekt.app.cli.util import copy_text_to_clipboard

    response = get_inspected_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not raw:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
                from inspekt.app.cli.table import print_hint
                print_hint(response['hint'])
        sys.exit(1)

    # Get HTML content and convert to markdown
    html_content = response.get("htmlContent", "")
    text_content = response.get("fullTextContent", response.get("textContent", ""))

    # Convert HTML to markdown, fall back to text if no HTML
    markdown_content = html_to_markdown(html_content) if html_content else text_content

    # Copy to clipboard
    if copy:
        if copy_text_to_clipboard(markdown_content):
            click.echo(f"✓ Copied {len(markdown_content)} characters to clipboard", err=True)
        sys.exit(0)

    # JSON mode
    if output_json:
        output = {
            "hasElement": True,
            "markdown": markdown_content,
            "length": len(markdown_content),
            "tag": response.get("tag"),
            "selector": response.get("selector")
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the markdown
    if raw:
        click.echo(markdown_content.rstrip())
        return

    # Formatted display
    if len(markdown_content) > 200:
        click.echo(f"Markdown Content (showing first 200 of {len(markdown_content)} characters):\n")
        click.echo(f'"{markdown_content[:200]}…"\n')
    else:
        click.echo(f"Markdown Content ({len(markdown_content)} characters):\n")
        click.echo(f'"{markdown_content}"\n')

    click.echo(f"Element:  <{response.get('tag')}> {response.get('selector', '')}")


@inspected.command()
@html_output_options
def html(raw, copy, output_json, pretty, compact, colors, theme, indent, line_length):
    """Get the HTML of the inspected element."""
    from inspekt.app.cli.selection import apply_syntax_highlighting
    from inspekt.app.cli.util import copy_text_to_clipboard
    from inspekt.config import get_html_selection_config

    response = get_inspected_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not raw:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
                from inspekt.app.cli.table import print_hint
                print_hint(response['hint'])
        sys.exit(1)

    # Load config defaults
    config = get_html_selection_config()

    # Use config values if flags not explicitly provided
    if pretty is None:
        pretty = config["pretty"]
    if compact is None:
        compact = config["compact"]
    if colors is None:
        colors = config["colors"]
    if theme is None:
        theme = config["theme"]
    if indent is None:
        indent = config["indent"]
    if line_length is None:
        line_length = config["line_length"]

    # Get HTML content
    html_content = response.get("htmlContent", "")

    # Process HTML if pretty or compact flags are set
    if pretty or compact:
        from inspekt.services.html_processor import process_html
        processed = process_html(
            html_content,
            prettier=pretty,
            compact=compact,
            indent=indent,
            line_length=line_length
        )
        if processed is None:
            # Prettier required but not available
            sys.exit(1)
        html_content = processed

    # Copy to clipboard (before syntax highlighting, we want raw content)
    if copy:
        if copy_text_to_clipboard(html_content):
            click.echo(f"✓ Copied {len(html_content)} characters to clipboard", err=True)
        sys.exit(0)

    # Apply syntax highlighting if requested (before JSON/raw output)
    # Only apply if outputting to a terminal (not piped/redirected)
    if colors and not output_json and sys.stdout.isatty():
        html_content = apply_syntax_highlighting(html_content, theme=theme)

    # JSON mode
    if output_json:
        # For JSON output, return un-highlighted HTML
        output = {
            "hasElement": True,
            "html": response.get("htmlContent", ""),  # Return original HTML in JSON
            "length": len(response.get("htmlContent", "")),
            "tag": response.get("tag"),
            "selector": response.get("selector")
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the HTML
    if raw:
        click.echo(html_content.rstrip())
        return

    # Formatted display with separators
    dark_gray = "\033[90m"
    reset = "\033[0m"
    separator = f"{dark_gray}{'—' * 80}{reset}"

    # Remove empty lines for cleaner output
    clean_html = '\n'.join(line for line in html_content.split('\n') if line.strip())

    click.echo(f"HTML Content ({len(response.get('htmlContent', ''))} characters):\n")
    click.echo(separator)
    click.echo(clean_html)
    click.echo(separator)
    click.echo(f"\nElement:  <{response.get('tag')}> {response.get('selector', '')}")


def get_executor():
    """Helper function to get BridgeExecutor instance."""
    return BridgeExecutor()


@click.group()
def screenshot():
    """Capture screenshots of elements, viewport, or full page."""
    pass


@screenshot.command(name="node")
@click.option(
    "--selector",
    "-s",
    default=None,
    help="CSS selector of element (default: use currently inspected element)",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (default: auto-generated)")
@click.option(
    "--margin",
    "-m",
    type=int,
    default=None,
    help="Margin in pixels around screenshot (default: from config)",
)
@click.option(
    "--margin-color",
    "-c",
    default=None,
    help="Margin color: 'auto' (sample first pixel), hex code like '#fff', or color name (default: from config)",
)
@click.option(
    "--optimize/--no-optimize",
    default=None,
    help="Optimize PNG with oxipng to reduce file size (default: from config)",
)
@click.option(
    "--scale",
    "--dpr",
    type=click.IntRange(1, 4),
    default=None,
    help="Scale/DPR factor 1-4 (1=standard, 2=retina). Alias: --dpr (default: from config)",
)
@click.option(
    "--max-width",
    type=int,
    default=None,
    help="Resize output to fit within max width (maintains aspect ratio)",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default=None,
    help="Output format (default: from config)",
)
@click.option(
    "--quality",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Quality for lossy formats (0.0-1.0, default: from config)",
)
@click.option(
    "--scroll-into-view/--no-scroll",
    default=True,
    help="Scroll element into view before capture (default: yes)",
)
@click.option(
    "--hide-outline/--keep-outline",
    default=True,
    help="Hide element outline during capture (default: yes)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open screenshot in default application after saving",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal screenshot in file explorer after saving",
)
@click.option(
    "--clipboard",
    is_flag=True,
    help="Copy to clipboard instead of saving to file",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing file without confirmation",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress output except errors",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output result as JSON (for scripting)",
)
@click.option(
    "--metadata/--no-metadata",
    default=True,
    help="Embed metadata (URL, timestamp, viewport) in image file (default: enabled)",
)
@click.option(
    "--redact/--no-redact",
    default=True,
    help="Redact sensitive data before capture (enabled by default for security)",
)
@click.option(
    "--redact-style",
    type=click.Choice(["blur", "bar"], case_sensitive=False),
    default="bar",
    help="Redaction style: bar (████ blocks, default) or blur",
)
@click.option(
    "--redact-selectors",
    default=None,
    help="Additional CSS selectors to redact (comma-separated)",
)
def screenshot_node(selector, output, margin, margin_color, optimize, scale, max_width, format, quality, scroll_into_view, hide_outline, open_after, reveal_after, clipboard, force, quiet, json_output, metadata, redact, redact_style, redact_selectors):
    """
    Capture a screenshot of a specific element (node).

    By default, captures the currently inspected element from DevTools.
    Use --selector to capture a specific element by CSS selector.

    The screenshot uses the Chrome extension's captureVisibleTab API for
    reliable, high-quality captures that work on all sites (including CSP-protected).

    Examples:
        # Capture currently inspected element
        inspekt screenshot node -o button.png

        # Capture specific element
        inspekt screenshot node --selector "#main" -o main.png

        # With margin and auto color
        inspekt screenshot node -o hero.png --margin 20 --margin-color auto

        # Optimize file size
        inspekt screenshot node -o logo.png --optimize

        # Custom margin color
        inspekt screenshot node -o card.png --margin 10 --margin-color "#f0f0f0"
    """
    # Validate mutually exclusive options
    if clipboard and (open_after or reveal_after):
        click.echo("Error: --clipboard cannot be used with --open or --reveal", err=True)
        sys.exit(1)

    if json_output and (open_after or reveal_after or clipboard):
        click.echo("Error: --json cannot be used with --open, --reveal, or --clipboard", err=True)
        sys.exit(1)

    # Note if both --open and --reveal are used
    if open_after and reveal_after and not quiet:
        click.secho("Note: Using both --open and --reveal", dim=True)

    # quiet implies no interactive prompts
    if quiet:
        force = True  # Don't prompt for overwrite in quiet mode

    executor = get_executor()
    loader = ScriptLoader()

    executor.ensure_server_running()

    # Load config defaults
    config = get_screenshot_config()

    # Apply config defaults for unspecified options
    if margin is None:
        margin = config["margin"]
    if margin_color is None:
        margin_color = config["margin-color"]
    if optimize is None:
        optimize = config["optimize"]
    if scale is None:
        scale = config["scale"]
    if format is None:
        format = config["format"]
    if quality is None:
        quality = config["quality"]

    # Load unified screenshot script
    try:
        script = loader.load_script_sync("screenshot_unified.js")
    except FileNotFoundError as e:
        click.echo(f"Error: Screenshot script not found: {e}", err=True)
        sys.exit(1)

    # Build options
    options = {
        "selector": selector,
        "margin": margin,
        "marginColor": margin_color,
        "scale": scale,
        "format": format,
        "quality": quality,
        "scrollIntoView": scroll_into_view,
        "hideOutline": hide_outline,
    }

    # Replace placeholders
    code = script.replace("'MODE_PLACEHOLDER'", json.dumps("node"))
    code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options))

    try:
        from inspekt.app.cli import icons

        # Apply redaction if requested (before capture)
        redacted_count = 0
        masked_emails_count = 0
        redacted_elements = []
        redact_script = None  # Store script for restore after capture
        if redact:
            try:
                redact_script = loader.load_script_sync("screenshot_redact.js")

                # Build redact options - scope to target element for node screenshots
                redact_options = {
                    "action": "apply",
                    "style": redact_style.lower(),  # blur, bar, or pixelate
                    "includePatterns": True,
                    "rootSelector": selector,  # Only scan within the target element
                }

                # Add custom selectors if provided
                if redact_selectors:
                    custom = [s.strip() for s in redact_selectors.split(",") if s.strip()]
                    redact_options["selectors"] = custom

                redact_code = redact_script.replace("OPTIONS_PLACEHOLDER", json.dumps(redact_options))
                redact_result = executor.execute(redact_code, timeout=30.0)

                if redact_result.get("ok"):
                    redact_response = redact_result.get("result", {})
                    if redact_response.get("ok"):
                        redacted_count = redact_response.get("redactedCount", 0)
                        masked_emails_count = redact_response.get("maskedEmailsCount", 0)
                        redacted_elements = redact_response.get("elements", [])

                        if not quiet and not json_output:
                            messages = []
                            if redacted_count > 0:
                                style_desc = {"blur": "blur", "bar": "bar", "pixelate": "pixelate"}.get(redact_style.lower(), "blur")
                                messages.append(f"{redacted_count} element(s) with {style_desc}")
                            if masked_emails_count > 0:
                                messages.append(f"{masked_emails_count} email(s) masked")
                            if messages:
                                click.echo(icons.info(f"Redacting: {', '.join(messages)}…"))
                            else:
                                click.echo(icons.info("No sensitive elements found to redact"))

            except FileNotFoundError:
                if not quiet and not json_output:
                    click.echo("Warning: Redaction script not found, skipping redaction", err=True)
            except Exception as e:
                if not quiet and not json_output:
                    click.echo(f"Warning: Redaction failed: {e}", err=True)

        # Execute the screenshot capture
        result = executor.execute(code, timeout=60.0)

        # Restore redacted elements after capture (don't leave page blurred)
        if redact_script and redacted_count > 0:
            try:
                restore_options = {"action": "restore"}
                restore_code = redact_script.replace("OPTIONS_PLACEHOLDER", json.dumps(restore_options))
                executor.execute(restore_code, timeout=10.0)
            except Exception:
                pass  # Silently ignore restore failures - screenshot already captured

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if not response.get("ok"):
            click.echo(f"Error: {response.get('error')}", err=True)
            sys.exit(1)

        # Get element tag name for display
        tag_name = response.get("tagName", "element").lower()
        scroll_dir = response.get("scrollDirection", "down") if response.get("scrolledIntoView") else None

        # Display action log in logical order (unless quiet or json mode)
        if not quiet and not json_output:
            # 1. Scroll action (if element was scrolled into view)
            if scroll_dir:
                click.echo(icons.scroll_action(scroll_dir, f"Scrolling <{tag_name}> into view…"))

            # 2. Capture action
            if selector:
                click.echo(icons.screenshot(f"Capturing element: {selector}"))
            else:
                click.echo(icons.screenshot("Capturing currently inspected element…"))

            # 3. Restore scroll position (if we scrolled) - use opposite direction
            if scroll_dir:
                opposite_dir = {"up": "down", "down": "up", "left": "right", "right": "left"}.get(scroll_dir, "up")
                click.echo(icons.scroll_action(opposite_dir, "Restoring scroll position…"))

            # 4. CDP fallback info (if used)
            if response.get("usedCDPFallback"):
                dims = response.get("elementDimensions", {})
                width = dims.get("width", 0)
                height = dims.get("height", 0)
                vw = dims.get("viewportWidth", 0)
                vh = dims.get("viewportHeight", 0)
                click.echo(icons.info(
                    f"Element ({width}×{height}) exceeds viewport ({vw}×{vh}). "
                    "Used full-page capture method and cropped image"
                ))

            # 5. Large dimension warning
            dims = response.get("elementDimensions", {})
            if dims.get("width", 0) > 10000 or dims.get("height", 0) > 10000:
                click.echo(icons.info(
                    f"Large element captured: {dims.get('width')}×{dims.get('height')}. "
                    "Chrome has a maximum dimension limit of 16384"
                ))

        # Get data URL and decode
        data_url = response.get("dataUrl")
        if not data_url:
            click.echo("Error: No image data received", err=True)
            sys.exit(1)

        # Extract base64 data
        if "," in data_url:
            base64_data = data_url.split(",", 1)[1]
        else:
            base64_data = data_url

        # Decode base64 to bytes
        try:
            image_data = base64.b64decode(base64_data)
        except Exception as e:
            click.echo(f"Error decoding image data: {e}", err=True)
            sys.exit(1)

        # Handle clipboard mode (no file saved)
        if clipboard:
            from inspekt.app.cli.icons import clipboard as clipboard_icon
            from inspekt.app.cli.util import copy_image_to_clipboard

            if copy_image_to_clipboard(image_data, format=format):
                file_size_kb = len(image_data) / 1024
                click.echo(
                    clipboard_icon(f"Copied to clipboard ({response.get('width')}×{response.get('height')}px, {file_size_kb:.1f} KB)")
                )
            else:
                click.echo("Failed to copy to clipboard", err=True)
                sys.exit(1)
        else:
            # Generate output filename if not specified
            if output is None:
                # Get element info from response
                tag_name = response.get("tagName", "element").lower()
                element_id = ""

                # Try to extract ID from selector if available
                if selector and "#" in selector:
                    # Extract ID from selector like "#main" or "div#main"
                    parts = selector.split("#")
                    if len(parts) > 1:
                        element_id = parts[1].split(".")[0].split(" ")[0].split("[")[0]

                # Generate timestamp: YYYYMMDDHHMMSS
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

                # Build filename: YYYYMMDDHHMMSS_tagname_id.ext
                if element_id:
                    filename = f"{timestamp}_{tag_name}_{element_id}.{format}"
                else:
                    filename = f"{timestamp}_{tag_name}.{format}"

                # Use screenshots directory from config
                from inspekt.config import get_paths_config

                paths = get_paths_config()
                output = str(paths["screenshots"] / filename)
                auto_generated = True
            else:
                auto_generated = False

            # Prepare output path
            output_path = Path(output)

            # Check if file exists and handle overwrite
            if output_path.exists() and not force:
                if json_output:
                    # In JSON mode, just error out
                    click.echo(json.dumps({"ok": False, "error": f"File already exists: {output_path}"}))
                    sys.exit(1)
                click.echo(f"File already exists: {output_path}", err=True)
                if not click.confirm("Overwrite?"):
                    sys.exit(0)

            # Save image
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with _builtin_open(output_path, "wb") as f:
                f.write(image_data)

            # Track dimensions (may be updated by resize)
            final_width = response.get("width")
            final_height = response.get("height")
            resized = False

            # Resize if max_width specified and image is wider
            if max_width and final_width and final_width > max_width:
                try:
                    from PIL import Image

                    with Image.open(output_path) as img:
                        # Calculate new height maintaining aspect ratio
                        ratio = max_width / img.width
                        new_height = int(img.height * ratio)

                        # Resize with high-quality resampling
                        resized_img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                        # Save with appropriate format settings
                        save_kwargs = {}
                        if format == "png":
                            save_kwargs["optimize"] = False  # oxipng will handle this
                        elif format in ("jpg", "jpeg"):
                            save_kwargs["quality"] = int(quality * 100) if quality else 92
                        elif format == "webp":
                            save_kwargs["quality"] = int(quality * 100) if quality else 92

                        resized_img.save(output_path, **save_kwargs)

                        final_width = max_width
                        final_height = new_height
                        resized = True

                        if not quiet and not json_output:
                            click.echo(icons.info(f"Resized: {response.get('width')}x{response.get('height')}px → {max_width}x{new_height}px"))

                except ImportError:
                    if not quiet and not json_output:
                        click.echo("Note: --max-width requires Pillow. Install with: pip install Pillow", err=True)

            # Get final file size after any resize
            final_size = output_path.stat().st_size
            file_size_kb = final_size / 1024

            # Display save message with filename info (unless quiet/json)
            if not quiet and not json_output:
                filename_display = output_path.name
                if auto_generated:
                    click.echo(icons.save(f"Screenshot saved: {filename_display} (filename auto-generated)"))
                else:
                    click.echo(icons.save(f"Screenshot saved: {filename_display}"))

                # Display dimensions
                click.echo(icons.dimensions(f"Size: {final_width}×{final_height} ({file_size_kb:.1f} KB)"))

            # Optimize with oxipng if requested
            if optimize:
                if format != "png":
                    if not quiet and not json_output:
                        click.echo("Note: --optimize only works with PNG format", err=True)
                else:
                    from inspekt.services.image_optimizer import optimize_png

                    if not quiet and not json_output:
                        click.echo(icons.optimizing("Reducing file size using OxiPNG…"))

                    try:
                        original_size = len(image_data)
                        optimized_size = optimize_png(output_path)

                        if optimized_size:
                            final_size = optimized_size  # Update for JSON
                            if not quiet and not json_output:
                                reduction = ((original_size - optimized_size) / original_size) * 100
                                click.echo(
                                    icons.optimized(f"After optimization: {original_size/1024:.1f} KB → {optimized_size/1024:.1f} KB ({reduction:.1f}% reduction)")
                                )
                        else:
                            if not quiet and not json_output:
                                click.echo("Optimization skipped (oxipng not available)", err=True)
                    except Exception as e:
                        if not quiet and not json_output:
                            click.echo(f"Optimization failed: {e}", err=True)

            # Embed metadata if requested (after optimization, which strips metadata)
            metadata_added = False
            if metadata and format in ("png", "jpg", "jpeg"):
                try:
                    from inspekt.services.image_metadata import add_metadata, create_metadata

                    # Get viewport dimensions from response
                    dims = response.get("elementDimensions", {})
                    viewport_dims = (dims.get("viewportWidth", 0), dims.get("viewportHeight", 0))

                    # Create metadata dict
                    meta = create_metadata(
                        source_url=response.get("url"),
                        viewport=viewport_dims if viewport_dims[0] > 0 else None,
                        target="element",
                        selector=selector,
                        element_tag=response.get("tagName"),
                        dpr=scale or 2,
                        redacted=redacted_count > 0,
                    )

                    # Add metadata to file
                    add_metadata(output_path, meta)
                    metadata_added = True

                    if not quiet and not json_output:
                        click.echo(icons.metadata("Metadata embedded: URL, timestamp, viewport info"))

                except Exception as e:
                    if not quiet and not json_output:
                        click.echo(f"Warning: Could not add metadata: {e}", err=True)

            # Display source URL (unless quiet/json)
            if not quiet and not json_output:
                url = response.get("url", "")
                if url:
                    click.echo(icons.metadata(f"Source: {url}"))

            # JSON output mode
            if json_output:
                result_json = {
                    "ok": True,
                    "path": str(output_path.absolute()),
                    "filename": output_path.name,
                    "width": final_width,
                    "height": final_height,
                    "original_width": response.get("width"),
                    "original_height": response.get("height"),
                    "size_bytes": final_size,
                    "original_size_bytes": len(image_data),
                    "resized": resized,
                    "optimized": optimize and format == "png",
                    "metadata_embedded": metadata_added,
                    "redacted": redact,
                    "redacted_style": redact_style.lower() if redact else None,
                    "redacted_count": redacted_count,
                    "masked_emails_count": masked_emails_count if redact else 0,
                    "redacted_elements": redacted_elements if redact else [],
                    "url": response.get("url"),
                    "method": response.get("apiUsed"),
                    "scrolled_into_view": response.get("scrolledIntoView", False),
                    "used_cdp_fallback": response.get("usedCDPFallback", False),
                }
                click.echo(json.dumps(result_json))
                return

            # Open in default application if requested
            if open_after:
                from inspekt.app.cli.util import open_or_download

                open_or_download(output_path)

            # Reveal in file explorer if requested
            if reveal_after:
                from inspekt.app.cli.util import reveal_or_download

                reveal_or_download(output_path)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Add screenshot as an alias under the 'inspected' command group
# This allows: inspekt inspected screenshot (same as: inspekt screenshot node)
inspected.add_command(screenshot_node, name="screenshot")


@screenshot.command(name="viewport")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (required unless --clipboard)")
@click.option(
    "--margin",
    "-m",
    type=int,
    default=0,
    help="Margin in pixels around screenshot (default: 0)",
)
@click.option(
    "--margin-color",
    "-c",
    default="auto",
    help="Margin color: 'auto' (sample first pixel), hex code, or color name (default: auto)",
)
@click.option(
    "--optimize",
    is_flag=True,
    help="Optimize PNG with oxipng to reduce file size",
)
@click.option(
    "--scale",
    type=click.IntRange(1, 4),
    default=2,
    help="Scale factor 1-4 for high-DPI screenshots (default: 2)",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default="png",
    help="Output format (default: png)",
)
@click.option(
    "--quality",
    type=click.FloatRange(0.0, 1.0),
    default=0.92,
    help="Quality for lossy formats (0.0-1.0, default: 0.92)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open screenshot in default application after saving",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal screenshot in file explorer after saving",
)
@click.option(
    "--clipboard",
    is_flag=True,
    help="Copy to clipboard instead of saving to file",
)
@click.option(
    "--metadata/--no-metadata",
    default=True,
    help="Embed metadata (URL, timestamp, viewport) in image file (default: enabled)",
)
def screenshot_viewport(output, margin, margin_color, optimize, scale, format, quality, open_after, reveal_after, clipboard, metadata):
    """
    Capture a screenshot of the visible viewport.

    Captures exactly what's visible in the browser window.

    Examples:
        inspekt screenshot viewport -o viewport.png
        inspekt screenshot viewport -o view.png --margin 10 --optimize
        inspekt screenshot viewport --clipboard
    """
    # Validate options
    if clipboard and (open_after or reveal_after):
        click.echo("Error: --clipboard cannot be used with --open or --reveal", err=True)
        sys.exit(1)
    if not clipboard and not output:
        click.echo("Error: Either --output or --clipboard is required", err=True)
        sys.exit(1)

    # Note if both --open and --reveal are used
    if open_after and reveal_after:
        click.secho("Note: Using both --open and --reveal", dim=True)

    executor = get_executor()
    loader = ScriptLoader()

    executor.ensure_server_running()

    try:
        script = loader.load_script_sync("screenshot_unified.js")
    except FileNotFoundError as e:
        click.echo(f"Error: Screenshot script not found: {e}", err=True)
        sys.exit(1)

    options = {
        "margin": margin,
        "marginColor": margin_color,
        "scale": scale,
        "format": format,
        "quality": quality,
    }

    code = script.replace("'MODE_PLACEHOLDER'", json.dumps("viewport"))
    code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options))

    try:
        from inspekt.app.cli.icons import screenshot as screenshot_icon

        click.echo(screenshot_icon("Capturing viewport…"))

        result = executor.execute(code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if not response.get("ok"):
            click.echo(f"Error: {response.get('error')}", err=True)
            sys.exit(1)

        # Get data URL and decode
        data_url = response.get("dataUrl")
        if not data_url:
            click.echo("Error: No image data received", err=True)
            sys.exit(1)

        # Extract and decode base64 data
        base64_data = data_url.split(",", 1)[1] if "," in data_url else data_url

        try:
            image_data = base64.b64decode(base64_data)
        except Exception as e:
            click.echo(f"Error decoding image data: {e}", err=True)
            sys.exit(1)

        # Handle clipboard mode (no file saved)
        if clipboard:
            from inspekt.app.cli.icons import clipboard as clipboard_icon
            from inspekt.app.cli.util import copy_image_to_clipboard

            if copy_image_to_clipboard(image_data, format=format):
                file_size_kb = len(image_data) / 1024
                click.echo(clipboard_icon(f"Copied to clipboard ({file_size_kb:.1f} KB)"))
            else:
                click.echo("Failed to copy to clipboard", err=True)
                sys.exit(1)
        else:
            # Save image
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with _builtin_open(output_path, "wb") as f:
                f.write(image_data)

            file_size_kb = len(image_data) / 1024
            click.echo(f"Screenshot saved: {output_path}")
            click.echo(f"Size: {file_size_kb:.1f} KB")

            # Optimize if requested
            if optimize and format == "png":
                from inspekt.services.image_optimizer import optimize_png

                try:
                    original_size = len(image_data)
                    optimized_size = optimize_png(output_path)

                    if optimized_size:
                        reduction = ((original_size - optimized_size) / original_size) * 100
                        click.echo(
                            f"Optimized: {original_size/1024:.1f} KB → {optimized_size/1024:.1f} KB ({reduction:.1f}% reduction)"
                        )
                except Exception as e:
                    click.echo(f"Optimization failed: {e}", err=True)

            # Embed metadata if requested
            if metadata and format in ("png", "jpg", "jpeg"):
                try:
                    from inspekt.services.image_metadata import add_metadata, create_metadata

                    meta = create_metadata(
                        source_url=response.get("url"),
                        viewport=(response.get("width"), response.get("height")),
                        target="viewport",
                        dpr=scale or 2,
                    )
                    add_metadata(output_path, meta)
                    click.echo("Metadata embedded: URL, timestamp, viewport info")
                except Exception as e:
                    click.echo(f"Warning: Could not add metadata: {e}", err=True)

            # Open in default application if requested
            if open_after:
                from inspekt.app.cli.util import open_or_download

                open_or_download(output_path)

            # Reveal in file explorer if requested
            if reveal_after:
                from inspekt.app.cli.util import reveal_or_download

                reveal_or_download(output_path)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screenshot.command(name="page")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (required unless --clipboard)")
@click.option(
    "--margin",
    "-m",
    type=int,
    default=0,
    help="Margin in pixels around screenshot (default: 0)",
)
@click.option(
    "--margin-color",
    "-c",
    default="auto",
    help="Margin color: 'auto' (sample first pixel), hex code, or color name (default: auto)",
)
@click.option(
    "--optimize",
    is_flag=True,
    help="Optimize PNG with oxipng to reduce file size",
)
@click.option(
    "--scale",
    type=click.IntRange(1, 4),
    default=1,
    help="Scale factor 1-4 (default: 1)",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default="png",
    help="Output format (default: png)",
)
@click.option(
    "--quality",
    type=click.FloatRange(0.0, 1.0),
    default=0.92,
    help="Quality for lossy formats (0.0-1.0, default: 0.92)",
)
@click.option(
    "--max-height",
    type=int,
    default=16384,
    help="Maximum capture height in pixels (default: 16384, Chrome limit)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open screenshot in default application after saving",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal screenshot in file explorer after saving",
)
@click.option(
    "--clipboard",
    is_flag=True,
    help="Copy to clipboard instead of saving to file",
)
@click.option(
    "--metadata/--no-metadata",
    default=True,
    help="Embed metadata (URL, timestamp, viewport) in image file (default: enabled)",
)
def screenshot_page(output, margin, margin_color, optimize, scale, format, quality, max_height, open_after, reveal_after, clipboard, metadata):
    """
    Capture a screenshot of the entire page (full height).

    Uses Chrome DevTools Protocol for single-shot full page capture.
    Note: Chrome has a maximum height limit of 16384 pixels.

    WARNING: A debugger notification banner will appear briefly during capture.
    This is a Chrome security feature and cannot be disabled.

    Examples:
        inspekt screenshot page -o fullpage.png
        inspekt screenshot page -o page.png --scale 2
        inspekt screenshot page -o page.jpg --format jpg --quality 0.85
        inspekt screenshot page --clipboard
    """
    # Validate options
    if clipboard and (open_after or reveal_after):
        click.echo("Error: --clipboard cannot be used with --open or --reveal", err=True)
        sys.exit(1)
    if not clipboard and not output:
        click.echo("Error: Either --output or --clipboard is required", err=True)
        sys.exit(1)

    # Note if both --open and --reveal are used
    if open_after and reveal_after:
        click.secho("Note: Using both --open and --reveal", dim=True)

    executor = get_executor()
    loader = ScriptLoader()

    executor.ensure_server_running()

    try:
        script = loader.load_script_sync("screenshot_unified.js")
    except FileNotFoundError as e:
        click.echo(f"Error: Screenshot script not found: {e}", err=True)
        sys.exit(1)

    options = {
        "margin": margin,
        "marginColor": margin_color,
        "scale": scale,
        "format": format,
        "quality": quality,
        "maxHeight": max_height,
    }

    code = script.replace("'MODE_PLACEHOLDER'", json.dumps("page"))
    code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options))

    try:
        from inspekt.app.cli.icons import screenshot as screenshot_icon

        click.echo(screenshot_icon("Capturing full page (debugger will attach briefly)…"))

        result = executor.execute(code, timeout=120.0)  # Longer timeout for full page

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if not response.get("ok"):
            click.echo(f"Error: {response.get('error')}", err=True)
            sys.exit(1)

        # Check for truncation warning
        if response.get("truncated"):
            click.echo(
                f"Warning: Page was truncated from {response.get('fullHeight')}px to {response.get('height')}px",
                err=True,
            )

        # Get data URL and decode
        data_url = response.get("dataUrl")
        if not data_url:
            click.echo("Error: No image data received", err=True)
            sys.exit(1)

        # Extract and decode base64 data
        base64_data = data_url.split(",", 1)[1] if "," in data_url else data_url

        try:
            image_data = base64.b64decode(base64_data)
        except Exception as e:
            click.echo(f"Error decoding image data: {e}", err=True)
            sys.exit(1)

        # Handle clipboard mode (no file saved)
        if clipboard:
            from inspekt.app.cli.icons import clipboard as clipboard_icon
            from inspekt.app.cli.util import copy_image_to_clipboard

            if copy_image_to_clipboard(image_data, format=format):
                file_size_kb = len(image_data) / 1024
                click.echo(
                    clipboard_icon(f"Copied to clipboard ({response.get('width')}×{response.get('height')}px, {file_size_kb:.1f} KB)")
                )
            else:
                click.echo("Failed to copy to clipboard", err=True)
                sys.exit(1)
        else:
            # Save image
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with _builtin_open(output_path, "wb") as f:
                f.write(image_data)

            file_size_kb = len(image_data) / 1024
            click.echo(f"Screenshot saved: {output_path}")
            click.echo(f"Size: {response.get('width')}×{response.get('height')}px ({file_size_kb:.1f} KB)")

            # Optimize if requested
            if optimize and format == "png":
                from inspekt.services.image_optimizer import optimize_png

                try:
                    original_size = len(image_data)
                    optimized_size = optimize_png(output_path)

                    if optimized_size:
                        reduction = ((original_size - optimized_size) / original_size) * 100
                        click.echo(
                            f"Optimized: {original_size/1024:.1f} KB → {optimized_size/1024:.1f} KB ({reduction:.1f}% reduction)"
                        )
                except Exception as e:
                    click.echo(f"Optimization failed: {e}", err=True)

            # Embed metadata if requested
            if metadata and format in ("png", "jpg", "jpeg"):
                try:
                    from inspekt.services.image_metadata import add_metadata, create_metadata

                    meta = create_metadata(
                        source_url=response.get("url"),
                        viewport=(response.get("width"), response.get("height")),
                        target="page",
                        dpr=scale or 1,
                    )
                    add_metadata(output_path, meta)
                    click.echo("Metadata embedded: URL, timestamp, viewport info")
                except Exception as e:
                    click.echo(f"Warning: Could not add metadata: {e}", err=True)

            # Open in default application if requested
            if open_after:
                from inspekt.app.cli.util import open_or_download

                open_or_download(output_path)

            # Reveal in file explorer if requested
            if reveal_after:
                from inspekt.app.cli.util import reveal_or_download

                reveal_or_download(output_path)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
