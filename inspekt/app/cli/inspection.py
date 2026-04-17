"""
Inspection commands - Inspect elements, view details, and capture screenshots.

This module provides commands for element inspection and screenshot capture:
- inspect: Select and inspect elements
- inspected: View inspected element details
- screenshot: Capture element screenshots
"""

import base64
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import click

from inspekt.app.cli.icons import get_section_icon, warning as warn_icon
from inspekt.app.cli.selection import html_output_options
from inspekt.config import get_screenshot_config
from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.formatting_utils import format_filesize
from inspekt.services.script_loader import ScriptLoader

# Save built-in open function before it gets shadowed by Click commands
_builtin_open = open


def sanitize_selector_for_filename(selector: str) -> str:
    """
    Convert a CSS selector to a safe filename component.

    Examples:
        #my-id -> my-id
        .my-class -> my-class
        div:nth-of-type(2) -> div
        .class1.class2 -> class1
    """
    import re

    if not selector:
        return "element"

    # Remove leading # or .
    result = selector.lstrip("#.")

    # Remove :nth-of-type(...), :nth-child(...), etc.
    result = re.sub(r":[a-z-]+\([^)]*\)", "", result)

    # Take only the first class if multiple
    if "." in result:
        result = result.split(".")[0]

    # Replace any remaining unsafe characters with underscore
    result = re.sub(r"[^a-zA-Z0-9_-]", "_", result)

    # Remove leading/trailing underscores and collapse multiple underscores
    result = re.sub(r"_+", "_", result).strip("_")

    return result or "element"


def count_css_properties_in_string(css_content: str) -> int:
    """
    Count the number of CSS properties in a CSS string.

    Counts lines that contain a property declaration (property: value;).
    Ignores comments, selectors, and empty lines.

    Args:
        css_content: CSS string to count properties in

    Returns:
        Number of CSS properties
    """
    count = 0
    for line in css_content.split("\n"):
        stripped = line.strip()
        # Skip empty lines, comments, selectors, and closing braces
        if not stripped or stripped.startswith("/*") or stripped.startswith("//"):
            continue
        if stripped.endswith("{") or stripped == "}":
            continue
        # Count lines with property: value; pattern
        if ":" in stripped and (";" in stripped or stripped.endswith("*/")):
            count += 1
    return count


# Shorthand properties that Lightning CSS can create from longhands
SHORTHAND_PROPERTIES = {
    "margin", "padding",
    "border", "border-width", "border-style", "border-color", "border-radius",
    "border-top", "border-right", "border-bottom", "border-left",
    "background", "background-position",
    "flex", "flex-flow",
    "gap", "grid-gap",
    "inset", "outline", "overflow",
    "transition", "animation",
    "font", "list-style", "text-decoration",
    "place-content", "place-items", "place-self",
}


def count_shorthands_in_css(css_content: str) -> int:
    """
    Count the number of shorthand properties in a CSS string.

    Args:
        css_content: CSS string to analyze

    Returns:
        Number of shorthand properties found
    """
    import re
    count = 0
    for line in css_content.split("\n"):
        stripped = line.strip()
        # Skip non-property lines
        if not stripped or stripped.startswith("/*") or stripped.endswith("{") or stripped == "}":
            continue
        # Extract property name
        match = re.match(r"^([a-z-]+)\s*:", stripped)
        if match:
            prop = match.group(1)
            if prop in SHORTHAND_PROPERTIES:
                count += 1
    return count


# Rendering limits for large snippets
RENDER_LIMIT_DESCENDANTS = 1000        # Max descendant nodes for HTML
RENDER_LIMIT_CSS_PROPERTIES = 50000    # Max initial CSS properties (before treeshaking)
RENDER_LIMIT_CHARACTERS = 10000        # Max characters for any snippet


def _check_render_limits(
    content_type: str,
    character_count: int,
    descendant_count: int | None = None,
    css_property_count: int | None = None,
) -> str | None:
    """
    Check if content exceeds rendering limits.

    Returns a warning message if limits are exceeded, None otherwise.

    Args:
        content_type: "HTML" or "CSS" for the warning message
        character_count: Length of the content string
        descendant_count: Number of descendant nodes (HTML only)
        css_property_count: Number of initial CSS properties (CSS only)
    """
    exceeded = []

    # Check character limit (applies to both HTML and CSS)
    if character_count > RENDER_LIMIT_CHARACTERS:
        exceeded.append(f"{character_count:,} characters (limit: {RENDER_LIMIT_CHARACTERS:,})")

    # Check descendant limit (HTML only)
    if descendant_count is not None and descendant_count > RENDER_LIMIT_DESCENDANTS:
        exceeded.append(f"{descendant_count:,} descendants (limit: {RENDER_LIMIT_DESCENDANTS:,})")

    # Check CSS property limit (CSS only)
    if css_property_count is not None and css_property_count > RENDER_LIMIT_CSS_PROPERTIES:
        exceeded.append(f"{css_property_count:,} CSS properties (limit: {RENDER_LIMIT_CSS_PROPERTIES:,})")

    if not exceeded:
        return None

    # Build friendly warning message
    limits_text = " and ".join(exceeded)
    return (
        f"This {content_type} snippet is too large to render: {limits_text}. "
        f"Select a smaller element or use `--raw` to output without formatting."
    )


def _print_tips_section(tips: list[tuple[str, str, str | None]]) -> None:
    """
    Print a formatted TIPS section with proper text wrapping.

    Args:
        tips: List of (flag, description, example) tuples.
              Example can be None if not applicable.
    """
    from inspekt.app.cli.table import format_icon_message, _style_with_inline_code

    # Print header with lightbulb icon
    click.echo(click.style("\uf400 TIPS", fg="bright_black", bold=True))

    for flag, description, example in tips:
        # Format as: "Use `flag` to description"
        # Wrap the flag in backticks for inline code styling
        flag_formatted = f"`{flag}`" if not flag.startswith("`") else flag

        if example:
            # With example: add "e.g." prefix
            message = f"Use {flag_formatted} to {description.lower()} (e.g. {example})"
        else:
            # Without example
            message = f"Use {flag_formatted} to {description.lower()}"

        # Use format_icon_message for proper wrapping with bullet icon
        formatted = format_icon_message(message, icon="•")
        styled = _style_with_inline_code(formatted, base_fg="bright_black")
        click.echo(styled)


def generate_element_filename(
    domain: str,
    selector: str,
    extension: str,
    source_type: str = "inspected",
    timestamp: str | None = None,
) -> str:
    """
    Generate a timestamped filename for element output.

    Format: YYYYMMDDHHMMSS_{source}_{domain}_{selector}.ext
    Example: 20251222143052_focused_vrt_be_article.css

    Args:
        domain: Page domain (e.g., "vrt.be")
        selector: CSS selector of root element
        extension: File extension without dot (e.g., "css", "html")
        source_type: Either "inspected" or "focused" (for prefix)
        timestamp: Optional timestamp string (generated if not provided)

    Returns:
        Generated filename
    """
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    # Sanitize domain: replace dots with underscores
    safe_domain = domain.replace(".", "_").replace(":", "_")

    # Sanitize selector
    safe_selector = sanitize_selector_for_filename(selector)

    return f"{timestamp}_{source_type}_{safe_domain}_{safe_selector}.{extension}"


def generate_inspected_filename(
    domain: str,
    selector: str,
    extension: str,
    timestamp: str | None = None,
) -> str:
    """
    Generate a timestamped filename for inspected element output (backward compatible).

    Deprecated: Use generate_element_filename() instead.

    Format: YYYYMMDDHHMMSS_domain_selector.ext
    Example: 20251222143052_vrt_be_article.css

    Args:
        domain: Page domain (e.g., "vrt.be")
        selector: CSS selector of root element
        extension: File extension without dot (e.g., "css", "html")
        timestamp: Optional timestamp string (generated if not provided)

    Returns:
        Generated filename
    """
    return generate_element_filename(domain, selector, extension, source_type="inspected", timestamp=timestamp)


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

        // Store reference (set both new and legacy variable names for compatibility)
        window.__INSPEKT_INSPECTED_ELEMENT__ = el;

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


def get_element_data(source_type: str = "inspected"):
    """
    Get element data from browser based on source type.

    Args:
        source_type: Either "inspected" (DevTools) or "focused" (document.activeElement)

    Returns:
        Dictionary with element data or error information
    """
    executor = BridgeExecutor()
    loader = ScriptLoader()

    executor.ensure_server_running()

    # Load the shared script
    try:
        code = loader.load_script_sync("get_element_data.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Replace placeholder with actual source type
    code = code.replace("SOURCE_TYPE_PLACEHOLDER", source_type)

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


def get_inspected_data():
    """Helper function to get inspected element data from browser (DevTools)."""
    return get_element_data(source_type="inspected")


def get_focused_data():
    """Helper function to get focused element data from browser (document.activeElement)."""
    return get_element_data(source_type="focused")


def display_element_info(response, source_type="inspected", output_json=False):
    """
    Display element information (works for both inspected and focused).

    Args:
        response: Element data from get_element_data()
        source_type: "inspected" or "focused" (used in error messages)
        output_json: Output as JSON
    """
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

    # Display the element info (code below continues with existing formatting)
    _display_element_details(response)


def _display_element_details(response):
    """Display formatted element information details."""

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
            text = text[:60] + "…"
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
            accessible_name if len(accessible_name) <= 50 else accessible_name[:50] + "…"
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
                value = str(value)[:50] + "…"
            click.echo(f"  {key}: {value}")


def display_inspected_info(response, output_json=False):
    """
    Display inspected element info (backward compatible wrapper).

    Deprecated: Use display_element_info() instead.
    """
    display_element_info(response, source_type="inspected", output_json=output_json)


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
        inspekt inspected css       Get computed CSS styles as nested CSS
    """
    # If no subcommand is provided, show element info (default behavior)
    if ctx.invoked_subcommand is None:
        response = get_inspected_data()
        display_inspected_info(response, output_json=output_json)
def _display_text_markdown_metadata(response):
    """Display metadata summary for text and markdown commands."""
    from inspekt.app.cli.table import Table
    from inspekt.app.cli.output import pluralize

    tag = response.get("tag", "unknown")
    selector = response.get("selector", "")
    xpath = response.get("xpath", "")
    descendant_count = response.get("descendantCount", 0)
    nesting_depth = response.get("nestingDepth", 0)
    text_length = response.get("textLength", 0)

    # Build statistics rows
    stats_rows = []
    stats_rows.append(["Tag", f"<{tag}>"])
    if descendant_count > 0:
        elem_word = pluralize(descendant_count, "descendant", "descendants")
        stats_rows.append(["Contains", f"{descendant_count} {elem_word}"])
    stats_rows.append(["Depth", f"{nesting_depth} levels from <html>"])
    if text_length > 0:
        stats_rows.append(["Text", f"{text_length:,} characters"])

    # Display summary table
    click.echo()
    table = Table(
        ["Metric", "Value"],
        alignments=["left", "left"],
        title="Element metadata",
        icon="\ue736"  # HTML icon (for consistency with HTML command)
    )
    table.set_data(stats_rows)
    table.print_header(skip_column_headers=True)
    for row in stats_rows:
        table.print_row(row)
    table.print_footer()

    # Show selectors
    click.echo()
    click.echo(click.style("Selector  ", fg="bright_black") + selector)
    if xpath:
        click.echo(click.style("XPath     ", fg="bright_black") + xpath)


@inspected.command()
@click.option("--raw", is_flag=True, help="Output raw content without formatting (auto-enabled when piped)")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def text(raw, copy, output_json):
    """
    Get the text content of the inspected element.

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).
    """
    from inspekt.app.cli.util import copy_text_to_clipboard
    from inspekt.app.cli.table import print_hint

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    response = get_inspected_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not raw:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
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
    if auto_raw:
        click.echo(text_content.rstrip())
        return

    # Formatted display with metadata
    _display_text_markdown_metadata(response)

    click.echo()

    # Display text preview (up to 500 characters) in styled code block
    from inspekt.app.cli.output import print_code_block

    if len(text_content) > 500:
        click.echo(f"Text Preview (first 500 of {len(text_content):,} characters):")
        click.echo()
        print_code_block(text_content[:500])
        click.echo()
        print_hint("Use `--raw` to see the full content")
    else:
        click.echo(f"Text Content ({len(text_content):,} characters):")
        click.echo()
        print_code_block(text_content)


@inspected.command()
@click.option("--raw", is_flag=True, help="Output raw content without formatting (auto-enabled when piped)")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def markdown(raw, copy, output_json):
    """
    Get the inspected element as Markdown (converted from HTML).

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).
    """
    from inspekt.app.cli.selection import html_to_markdown
    from inspekt.app.cli.util import copy_text_to_clipboard
    from inspekt.app.cli.table import print_hint

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    response = get_inspected_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not raw:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
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
    if auto_raw:
        click.echo(markdown_content.rstrip())
        return

    # Formatted display with metadata
    _display_text_markdown_metadata(response)

    click.echo()

    # Display markdown preview (up to 500 characters) in styled code block
    from inspekt.app.cli.output import print_code_block

    if len(markdown_content) > 500:
        click.echo(f"Markdown Preview (first 500 of {len(markdown_content):,} characters):")
        click.echo()
        print_code_block(markdown_content[:500])
        click.echo()
        print_hint("Use `--raw` to see the full content")
    else:
        click.echo(f"Markdown Content ({len(markdown_content):,} characters):")
        click.echo()
        print_code_block(markdown_content)


@inspected.command()
@click.option(
    "--file",
    "file_path",
    default=None,
    is_flag=False,
    flag_value="auto",
    help="Save to file (auto-generates name if no path given)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open file in default application after saving (requires --file)",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal file in file explorer after saving (requires --file)",
)
@click.option(
    "--include-css",
    is_flag=True,
    help="Also generate CSS file (requires --file)",
)
@click.option(
    "--bundled",
    is_flag=True,
    help="Embed CSS in HTML file (requires --include-css)",
)
@click.option(
    "--all-properties",
    is_flag=True,
    help="Include all CSS properties (for --include-css)",
)
@click.option(
    "--include-defaults",
    is_flag=True,
    help="Include CSS defaults (for --include-css)",
)
@click.option(
    "--optimize-css/--no-optimize-css",
    default=True,
    help="Optimize embedded CSS (when using --include-css). Enabled by default.",
)
@click.option(
    "--remove-comments",
    is_flag=True,
    help="Remove all HTML comments from output.",
)
@click.option(
    "--oklch",
    is_flag=True,
    help="Convert CSS colors to oklch format with names (when using --include-css).",
)
@click.option(
    "--alphabetize/--no-alphabetize",
    default=True,
    help="Sort CSS properties alphabetically (when using --include-css). Enabled by default.",
)
@click.option(
    "--rounding/--no-rounding",
    default=True,
    help="Round CSS pixel values to nearest whole pixel (when using --include-css). Enabled by default.",
)
@html_output_options
def html(file_path, open_after, reveal_after, include_css, bundled, all_properties, include_defaults, optimize_css,
         remove_comments, oklch, alphabetize, rounding, raw, copy, output_json, pretty, compact, colors, theme, indent):
    """
    Get the HTML of the inspected element.

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).

    Examples:

        inspekt inspected html                     # Display HTML
        inspekt inspected html --file              # Save to auto-named file
        inspekt inspected html --file snippet.html # Save to specific file
        inspekt inspected html --file --include-css          # HTML + CSS files
        inspekt inspected html --file --include-css --bundled  # Single bundled file
        inspekt inspected html --file --include-css --oklch    # CSS with oklch colors
    """
    from inspekt.app.cli.output import validate_output_options
    from inspekt.app.cli.selection import apply_syntax_highlighting
    from inspekt.config import get_html_selection_config

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    # Validate common output options
    validate_output_options(file_path, copy, output_json, open_after, reveal_after)

    # Validate HTML-specific options
    if include_css and not file_path:
        click.echo("Error: --include-css requires --file", err=True)
        sys.exit(1)
    if bundled and not include_css:
        click.echo("Error: --bundled requires --include-css", err=True)
        sys.exit(1)
    if bundled and compact:
        click.echo(
            "Error: --bundled and --compact cannot be used together.\n"
            "Compact mode removes class names and other attributes that CSS selectors need to apply styles.",
            err=True,
        )
        sys.exit(1)
    # Generate timestamp upfront for matching filenames
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S") if file_path else None

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

    # Get HTML content
    html_content = response.get("htmlContent", "")

    # Process HTML (always strip empty comments, optionally do more)
    # Note: process_html always removes empty comments regardless of other flags
    if pretty or compact or remove_comments:
        from inspekt.services.html_processor import process_html
        html_content = process_html(
            html_content,
            format=pretty,
            compact=compact,
            remove_comments=remove_comments,
            indent=indent
        )
    else:
        # Still strip empty comments even without other processing
        from inspekt.services.html_processor import strip_empty_comments
        html_content = strip_empty_comments(html_content)

    # File output mode
    if file_path:
        from inspekt.services.bridge_executor import BridgeExecutor
        from inspekt.services.css_generator import generate_nested_css, count_properties
        from inspekt.services.script_loader import ScriptLoader

        selector = response.get("selector", "")
        domain = response.get("pageDomain", "localhost")
        page_title = response.get("pageTitle", "Inspekt Export")
        page_lang = response.get("pageLang", "en")

        # Determine HTML filename
        if file_path == "auto":
            html_filename = generate_inspected_filename(domain, selector, "html", timestamp)
        else:
            # Use provided filename, add .html extension if missing
            html_filename = file_path if file_path.endswith(".html") else f"{file_path}.html"

        # Generate CSS if requested
        css_content = None
        property_count = 0
        element_count = 1
        if include_css:
            executor = BridgeExecutor()
            executor.ensure_server_running()
            loader = ScriptLoader()

            js_options = {
                "allProperties": all_properties,
                "includeDefaults": include_defaults,
                "roundPixels": rounding,
            }

            script = loader.load_with_substitution_sync(
                "get_computed_css.js",
                {"OPTIONS_PLACEHOLDER": js_options}
            )

            try:
                css_result = executor.execute(script, timeout=30.0)
                if css_result.get("ok"):
                    css_response = css_result.get("result", {})
                    if css_response.get("ok"):
                        root = css_response.get("root", {})
                        element_count = css_response.get("elementCount", 1)
                        css_content = generate_nested_css(root)
                        property_count = count_properties(root)

                        # Collect rounded/computed props for comment insertion
                        from inspekt.services.css_generator import collect_rounded_props, collect_computed_props
                        rounded_props = collect_rounded_props(root) if rounding else None
                        computed_props = collect_computed_props(root) if not rounding else None

                        # Optionally optimize CSS and/or convert colors to oklch
                        # Color names are always added when optimizing for convenience
                        if optimize_css or oklch or alphabetize:
                            from inspekt.services.css_optimizer import optimize_css as do_optimize_css
                            css_content = do_optimize_css(
                                css_content,
                                convert_to_oklch=oklch,
                                add_color_names=True,
                                alphabetize=alphabetize,
                                rounded_props=rounded_props,
                                computed_props=computed_props,
                            )
            except Exception as e:
                click.echo(f"Warning: Failed to extract CSS: {e}", err=True)

        # Bundled mode: single HTML file with embedded CSS
        if bundled and css_content:
            # Get the root selector from CSS (first line before opening brace)
            root_selector = css_content.split("{")[0].strip()

            # Wrap HTML in a scoped container and update CSS root selector
            # This prevents generic selectors like 'div' from affecting other elements
            scoped_css = css_content.replace(root_selector + " {", ".inspekt-root {", 1)

            # Create full HTML document with embedded style
            bundled_html = f'''<!DOCTYPE html>
<html lang="{page_lang}">
<head>
  <meta charset="utf-8">
  <title>{page_title} — {selector}</title>
  <style>
{scoped_css}
  </style>
</head>
<body>
<div class="inspekt-root">
{html_content}
</div>
</body>
</html>'''

            from inspekt.app.cli.output import OutputHandler

            output_path = Path(html_filename)
            OutputHandler.save_and_handle(
                bundled_html,
                output_path,
                open_after=open_after,
                reveal_after=reveal_after,
                content_type="bundled HTML+CSS",
                details=f"{property_count} properties",
            )
            return

        # Write HTML file
        from inspekt.app.cli.output import OutputHandler

        html_output_path = Path(html_filename)
        OutputHandler.save_and_handle(
            html_content,
            html_output_path,
            content_type="HTML",
        )

        # Write CSS file if requested (not bundled)
        if include_css and css_content:
            css_filename = html_filename.rsplit(".", 1)[0] + ".css"
            css_output_path = Path(css_filename)
            OutputHandler.save_and_handle(
                css_content,
                css_output_path,
                content_type="CSS",
                details=f"{property_count} properties from {element_count} elements",
            )

        # Open/reveal file if requested (open HTML file)
        if open_after:
            OutputHandler.open_file(html_output_path)
        if reveal_after:
            OutputHandler.reveal_file(html_output_path)
        return

    # Copy to clipboard (before syntax highlighting, we want raw content)
    if copy:
        from inspekt.app.cli.output import OutputHandler
        OutputHandler.copy_to_clipboard(html_content)
        sys.exit(0)

    # JSON mode - return un-highlighted HTML with metadata
    if output_json:
        from inspekt.app.cli.output import JsonOutput
        (
            JsonOutput()
            .with_content("html", response.get("htmlContent", ""))
            .with_selector(response.get("selector"), response.get("tag"))
            .with_fields(
                xpath=response.get("xpath", ""),
                descendantCount=response.get("descendantCount", 0),
                nestingDepth=response.get("nestingDepth", 0),
                textLength=response.get("textLength", 0),
                attributeCount=response.get("attributeCount", 0),
            )
            .with_page_metadata(response)
            .print()
        )
        return

    # Raw mode: just print the HTML (no syntax highlighting)
    if auto_raw:
        click.echo(html_content.rstrip())
        return

    # Formatted display with summary table
    from inspekt.app.cli.table import Table
    from inspekt.app.cli.output import pluralize

    # Extract statistics
    tag = response.get("tag", "element")
    selector = response.get("selector", "")
    xpath = response.get("xpath", "")
    descendant_count = response.get("descendantCount", 0)
    nesting_depth = response.get("nestingDepth", 0)
    text_length = response.get("textLength", 0)

    # Build statistics rows
    stats_rows = []
    stats_rows.append(["Tag", f"<{tag}>"])
    if descendant_count > 0:
        elem_word = pluralize(descendant_count, "descendant", "descendants")
        stats_rows.append(["Contains", f"{descendant_count} {elem_word}"])
    stats_rows.append(["Depth", f"{nesting_depth} levels from <html>"])
    if text_length > 0:
        stats_rows.append(["Text", f"{text_length:,} characters"])

    # Display summary table
    click.echo()
    table = Table(
        ["Metric", "Value"],
        alignments=["left", "left"],
        title="HTML from inspected element",
        icon="\ue736"  # HTML icon
    )
    table.set_data(stats_rows)
    table.print_header(skip_column_headers=True)
    for row in stats_rows:
        table.print_row(row)
    table.print_footer()

    # Show selectors
    click.echo()
    click.echo(click.style("Selector  ", fg="bright_black") + selector)
    if xpath:
        click.echo(click.style("XPath     ", fg="bright_black") + xpath)

    # Check rendering limits before attempting to display
    limit_warning = _check_render_limits(
        content_type="HTML",
        character_count=len(html_content),
        descendant_count=descendant_count,
    )

    click.echo()

    if limit_warning:
        # Show warning instead of rendered content
        from inspekt.app.cli.table import print_warning
        print_warning(limit_warning)
    else:
        # Apply syntax highlighting for formatted display
        if colors and sys.stdout.isatty():
            html_content = apply_syntax_highlighting(html_content, theme=theme)

        # Remove empty lines for cleaner output
        clean_html = '\n'.join(line for line in html_content.split('\n') if line.strip())

        # Display HTML content in styled code block
        from inspekt.app.cli.output import print_code_block
        print_code_block(clean_html)

    # Show TIPS
    tips = []
    if not pretty:
        tips.append(("`--pretty`", "Format HTML with indentation", None))
    if not compact:
        tips.append(("`--compact`", "Strip classes, data-* attrs, styles; truncate long text (for documentation only)", None))
    if not remove_comments:
        tips.append(("`--no-comments`", "Remove HTML comments", None))
    if colors:
        tips.append(("`--raw`", "Output without syntax highlighting", None))

    if tips:
        click.echo()
        _print_tips_section(tips)


@inspected.command()
@click.option(
    "--file",
    "file_path",
    default=None,
    is_flag=False,
    flag_value="auto",
    help="Save to file (auto-generates name if no path given)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open file in default application after saving (requires --file)",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal file in file explorer after saving (requires --file)",
)
@click.option("--raw", is_flag=True, help="Output raw content without formatting (auto-enabled when piped)")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--all-properties",
    is_flag=True,
    help="Include all ~300 computed properties (default: common properties only)",
)
@click.option(
    "--include-defaults",
    is_flag=True,
    help="Include browser default values (default: exclude)",
)
@click.option(
    "--optimize/--no-optimize",
    default=True,
    help="Optimize CSS (merge shorthands). Enabled by default.",
)
@click.option(
    "--oklch",
    is_flag=True,
    help="Convert colors to oklch format with human-readable names.",
)
@click.option(
    "--alphabetize/--no-alphabetize",
    default=True,
    help="Sort CSS properties alphabetically. Enabled by default.",
)
@click.option(
    "--rounding/--no-rounding",
    default=True,
    help="Round pixel values to nearest whole pixel. Enabled by default.",
)
@click.option(
    "--heuristic-comments",
    is_flag=True,
    help="Add helpful comments based on property-value patterns (e.g., 'display: flex' -> /* Flexbox container */).",
)
@click.option(
    "--two-columns",
    is_flag=True,
    help="Format output with aligned columns: property and value aligned, comment follows immediately.",
)
@click.option(
    "--three-columns",
    is_flag=True,
    help="Format output with aligned columns: property, value, and comment each in separate columns.",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Compact CSS by shortening data URIs, long URLs, var() names, and animation names.",
)
@click.option(
    "--authored",
    is_flag=True,
    help="Show original authored CSS values (e.g., clamp(), var(), rem) instead of browser-computed values.",
)
def css(file_path, open_after, reveal_after, raw, copy, output_json, all_properties, include_defaults, optimize, oklch, alphabetize, rounding, heuristic_comments, two_columns, three_columns, compact, authored):
    """
    Extract computed CSS styles as nested CSS.

    Generates CSS that reproduces the visual appearance of the inspected
    element and all its children. Uses modern CSS nesting syntax.

    By default, only common CSS properties are included, browser default
    values are excluded, and pixel values are rounded to the nearest pixel.
    Rounded values are marked with /* Computed (Rounded) */ comments.

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).

    Examples:

        inspekt inspected css                    # Optimized CSS (default)
        inspekt inspected css --file             # Save to auto-named file
        inspekt inspected css --file styles.css  # Save to specific file
        inspekt inspected css --no-optimize      # Raw computed styles without optimization
        inspekt inspected css --no-rounding      # Keep decimal pixel values (e.g., 51.77px)
        inspekt inspected css --oklch            # Convert colors to oklch with names
        inspekt inspected css --heuristic-comments  # Add helpful comments (e.g., /* Flexbox container */)
        inspekt inspected css --all-properties   # All ~300 properties
        inspekt inspected css --include-defaults # Include browser defaults
        inspekt inspected css --compact          # Shorten data URIs, long URLs, var() names
        inspekt inspected css --authored         # Show original authored values (clamp(), var(), rem)
        inspekt inspected css --copy             # Copy CSS to clipboard
        inspekt inspected css --raw              # No syntax highlighting
    """
    from inspekt.app.cli.output import validate_output_options
    from inspekt.services.bridge_executor import BridgeExecutor
    from inspekt.services.css_generator import generate_nested_css, count_properties
    from inspekt.services.script_loader import ScriptLoader

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    # Validate flag combinations
    validate_output_options(file_path, copy, output_json, open_after, reveal_after)

    executor = BridgeExecutor()
    executor.ensure_server_running()

    loader = ScriptLoader()

    # Build options for the JS script
    js_options = {
        "allProperties": all_properties,
        "includeDefaults": include_defaults,
        "roundPixels": rounding,
    }

    # Load and execute the script
    script = loader.load_with_substitution_sync(
        "get_computed_css.js",
        {"OPTIONS_PLACEHOLDER": js_options, "SOURCE_TYPE_PLACEHOLDER": "inspected"}
    )

    try:
        result = executor.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})

        if not response.get("ok"):
            click.echo(f"Error: {response.get('error', 'Failed to extract styles')}", err=True)
            sys.exit(1)

        root = response.get("root", {})
        element_count = response.get("elementCount", 1)
        stats = response.get("stats", {})

        # Extract statistics from JavaScript
        total_considered = stats.get("totalConsidered", 0)
        stripped_as_default = stats.get("strippedAsDefault", 0)
        stripped_as_inherited = stats.get("strippedAsInherited", 0)

        # Optionally fetch and merge authored CSS values via CDP
        authored_count = 0
        if authored:
            authored_script = loader.load_with_substitution_sync(
                "get_authored_css_cdp.js",
                {"SOURCE_TYPE_PLACEHOLDER": "inspected", "ELEMENT_COUNT_PLACEHOLDER": element_count}
            )
            try:
                authored_result = executor.execute(authored_script, timeout=30.0)
                if authored_result.get("ok"):
                    authored_response = authored_result.get("result", {})
                    if authored_response.get("ok"):
                        from inspekt.services.css_authored_merger import merge_authored_css
                        authored_map = authored_response.get("elements", {})
                        root = merge_authored_css(root, authored_map)
                        from inspekt.services.css_generator import collect_authored_props
                        authored_count = len(collect_authored_props(root))
            except Exception:
                from inspekt.app.cli.table import print_warning
                print_warning("Could not retrieve authored CSS values. Showing computed values only.")

        # Generate nested CSS
        css_content = generate_nested_css(root)
        property_count = count_properties(root)

        # Collect rounded/computed props for comment insertion after optimization
        from inspekt.services.css_generator import collect_rounded_props, collect_computed_props
        rounded_props = collect_rounded_props(root) if rounding else None
        computed_props = collect_computed_props(root) if not rounding else None

        # Store original property count before optimization
        original_property_count = property_count

        # Optionally optimize CSS and/or convert colors to oklch
        # Color names are always added when optimizing for convenience
        optimized = optimize or oklch or alphabetize or heuristic_comments or two_columns or three_columns
        if optimized:
            from inspekt.services.css_optimizer import optimize_css
            # Collect cross-reference values (authored → computed) when authored mode is active
            cross_ref = None
            if authored and authored_count > 0:
                from inspekt.services.css_generator import collect_cross_ref_values
                cross_ref = collect_cross_ref_values(root)
            css_content = optimize_css(
                css_content,
                convert_to_oklch=oklch,
                add_color_names=True,  # Always add color names
                alphabetize=alphabetize,
                rounded_props=rounded_props,
                computed_props=computed_props,
                heuristic_comments=heuristic_comments,
                column_format="two" if two_columns else ("three" if three_columns else None),
                cross_ref_values=cross_ref,
            )
            # Count properties after optimization to track merged shorthands
            optimized_property_count = count_css_properties_in_string(css_content)
            merged_count = original_property_count - optimized_property_count
            shorthand_count = count_shorthands_in_css(css_content)
            property_count = optimized_property_count
        else:
            merged_count = 0
            shorthand_count = 0

        # Apply compact mode if requested
        if compact:
            from inspekt.services.html_processor import compact_css as compact_css_content
            css_content = compact_css_content(css_content, strip_comments=False)

        from inspekt.app.cli.output import OutputHandler, JsonOutput, pluralize

        # File output mode
        if file_path:
            selector = root.get("selector", root.get("tag", "unknown"))
            domain = response.get("pageDomain", "localhost")

            # Determine filename
            if file_path == "auto":
                output_file = generate_inspected_filename(domain, selector, "css")
            else:
                # Use provided filename, add .css extension if missing
                output_file = file_path if file_path.endswith(".css") else f"{file_path}.css"

            output_path = Path(output_file)
            elem_word = pluralize(element_count, "element")
            prop_word = pluralize(property_count, "property", "properties")
            OutputHandler.save_and_handle(
                css_content,
                output_path,
                open_after=open_after,
                reveal_after=reveal_after,
                content_type="CSS",
                details=f"{property_count} {prop_word} from {element_count} {elem_word}",
            )
            return

        # Copy to clipboard
        if copy:
            elem_word = pluralize(element_count, "element")
            prop_word = pluralize(property_count, "property", "properties")
            OutputHandler.copy_to_clipboard(css_content, quiet=True)
            click.echo(f"Copied CSS to clipboard ({property_count} {prop_word} from {element_count} {elem_word})", err=True)
            sys.exit(0)

        # JSON mode - return CSS with metadata (no full tree)
        if output_json:
            selector = root.get("selector", root.get("tag", "unknown"))
            (
                JsonOutput()
                .with_content("css", css_content)
                .with_selector(selector)
                .with_counts(element_count=element_count, property_count=property_count)
                .with_page_metadata(response)
                .print()
            )
            return

        # Raw mode: just print the CSS
        if auto_raw:
            click.echo(css_content)
            return

        # Formatted display with syntax highlighting
        from inspekt.app.cli.table import Table, print_hint

        # Build summary header
        elem_word = pluralize(element_count, "element")

        # Build table rows for property statistics
        stats_rows = []
        if total_considered > 0:
            total_word = pluralize(total_considered, "property", "properties")
            stats_rows.append(["Scanned", f"{total_considered} {total_word}"])
        if stripped_as_default > 0:
            default_word = pluralize(stripped_as_default, "browser default property", "browser default properties")
            stats_rows.append(["Removed", f"{stripped_as_default} {default_word}"])
        if stripped_as_inherited > 0:
            inherited_word = pluralize(stripped_as_inherited, "inherited duplicate", "inherited duplicates")
            stats_rows.append(["Removed", f"{stripped_as_inherited} {inherited_word}"])
        if authored and authored_count > 0:
            authored_word = pluralize(authored_count, "property", "properties")
            stats_rows.append(["Authored", f"{authored_count} {authored_word} resolved from source stylesheets"])
        if optimized and merged_count > 0:
            merged_word = pluralize(merged_count, "property", "properties")
            shorthand_word = pluralize(shorthand_count, "shorthand", "shorthands")
            stats_rows.append(["Merged", f"{merged_count} {merged_word} into {shorthand_count} {shorthand_word}"])
        prop_word = pluralize(property_count, "effective property", "effective properties")
        stats_rows.append(["Kept", f"{property_count} {prop_word}"])

        # Display statistics table
        click.echo()
        css_title = "Authored + Computed CSS" if authored and authored_count > 0 else "Computed CSS"
        table = Table(
            ["Metric", "Value"],
            alignments=["left", "left"],
            title=f"{css_title} from {element_count} {elem_word}",
            icon="\ue749"  # CSS icon
        )
        table.set_data(stats_rows)
        table.print_header(skip_column_headers=True)
        for row in stats_rows:
            table.print_row(row)
        table.print_footer()

        # Check rendering limits before attempting to display
        limit_warning = _check_render_limits(
            content_type="CSS",
            character_count=len(css_content),
            css_property_count=total_considered,
        )

        click.echo()

        if limit_warning:
            # Show warning instead of rendered content
            from inspekt.app.cli.table import print_warning
            print_warning(limit_warning)
        else:
            # Apply CSS syntax highlighting and display in styled code block
            from inspekt.app.cli.output import print_code_block

            if sys.stdout.isatty() and not raw:
                try:
                    from pygments import highlight
                    from pygments.lexers import CssLexer
                    from pygments.formatters import Terminal256Formatter

                    highlighted = highlight(css_content, CssLexer(), Terminal256Formatter(style="monokai"))
                    print_code_block(highlighted.rstrip())
                except ImportError:
                    print_code_block(css_content)
            else:
                print_code_block(css_content)

        # Show tips for additional options
        tips = []
        if optimized and not oklch:
            tips.append(("`--oklch`", "Display colors in OKLCH (perceptual) format", None))
        if not heuristic_comments:
            from inspekt.services.css_property_comments import get_random_tip_example
            prop, value, comment = get_random_tip_example()
            tips.append(("`--heuristic-comments`", "Add helpful comments", f"`{prop}: {value}` → /* {comment} */"))
        if not all_properties:
            tips.append(("`--all-properties`", "Include the complete computed style (~300 properties)", None))
        if optimized:
            tips.append(("`--no-optimize`", "Output raw data (no shorthand merging)", None))
        if not two_columns and not three_columns:
            tips.append(("`--two-columns`", "Align properties and values in columns", None))
        if not compact:
            tips.append(("`--compact`", "Shorten data URIs, URLs, and long text (breaks CSS; for documentation only)", None))
        if not authored:
            tips.append(("`--authored`", "Show original authored values (clamp(), var(), rem) via Chrome DevTools Protocol", None))

        if tips:
            click.echo()
            _print_tips_section(tips)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@inspected.command("describe")
@click.option(
    "--language", "--lang", type=str, default=None, help="Language for AI output (overrides config)"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--debug", is_flag=True, help="Show detailed debug output (prompts, API calls, image processing)")
def inspected_describe(language, output_json, debug):
    """
    Generate an AI-powered accessibility description of the inspected element.

    Uses vision AI to analyze a screenshot of the element along with its
    metadata to provide a concise, accessibility-focused description.

    The description focuses on:
    - What the element is and its purpose
    - Accessible name and how it's computed
    - Keyboard accessibility
    - Visual accessibility (contrast, focus indicators)
    - Potential accessibility issues

    Examples:
        inspekt inspected describe
        inspekt inspected describe --language nl
        inspekt inspected describe --json
    """
    import asyncio
    from inspekt.core.handlers.ai import element_describe
    from inspekt.core.schemas.ai import ElementDescribeParams
    from inspekt.app.cli.icons import analyze as analyze_icon

    if not output_json:
        click.echo(analyze_icon("Analyzing element with AI…"), err=True)

    params = ElementDescribeParams(source="inspected", language=language, debug=debug)
    result = asyncio.run(element_describe(params))

    if output_json:
        click.echo(json.dumps({
            "description": result.description,
            "element_type": result.element_type,
            "accessible_name": result.accessible_name,
            "source": result.source,
        }, indent=2))
    else:
        if result.description.startswith("Error:"):
            click.echo(result.description, err=True)
            sys.exit(1)

        click.echo()
        click.echo(result.description)
        click.echo()


@inspected.command("ask")
@click.argument("question", type=str)
@click.option(
    "--language", "--lang", type=str, default=None, help="Language for AI output (overrides config)"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--debug", is_flag=True, help="Show detailed debug output (prompts, API calls, image processing)")
def inspected_ask(question, language, output_json, debug):
    """
    Ask a question about the inspected element using AI.

    Uses vision AI to analyze a screenshot of the element along with its
    metadata to answer questions about accessibility, design, or functionality.

    Examples:
        inspekt inspected ask "Is this accessible?"
        inspekt inspected ask "Does this have sufficient contrast?"
        inspekt inspected ask "How would a screen reader announce this?"
        inspekt inspected ask "What WCAG issues does this have?"
    """
    import asyncio
    from inspekt.core.handlers.ai import element_ask
    from inspekt.core.schemas.ai import ElementAskParams
    from inspekt.app.cli.icons import analyze as analyze_icon

    if not output_json:
        click.echo(analyze_icon("Analyzing element with AI…"), err=True)

    params = ElementAskParams(question=question, source="inspected", language=language, debug=debug)
    result = asyncio.run(element_ask(params))

    if output_json:
        click.echo(json.dumps({
            "question": question,
            "answer": result.answer,
            "element_type": result.element_type,
            "source": result.source,
        }, indent=2))
    else:
        if result.answer.startswith("Error:"):
            click.echo(result.answer, err=True)
            sys.exit(1)

        click.echo()
        click.echo(result.answer)
        click.echo()


def get_executor():
    """Helper function to get BridgeExecutor instance."""
    return BridgeExecutor()


@click.group(invoke_without_command=True)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.pass_context
def focused(ctx, output_json):
    """
    Get information about the currently focused element.

    Shows details about the element that currently has keyboard/input focus
    (document.activeElement). Useful for testing focus management, keyboard
    navigation, and form interactions.

    To focus an element:
        1. Press Tab key to navigate between focusable elements
        2. Click an input field, button, link, or other interactive element
        3. Run: inspekt focused

    Or use keyboard shortcuts:
        Alt+Tab, Cmd+Tab: Switch focus between windows
        Tab/Shift+Tab: Navigate between focusable elements

    Subcommands:
        inspekt focused html       Get element as HTML
        inspekt focused markdown   Get element as Markdown
        inspekt focused text       Get element text content
        inspekt focused css        Get computed CSS styles as nested CSS

    Examples:
        # Tab to an input field, then:
        inspekt focused

        # Get focused element's HTML:
        inspekt focused html

        # Get computed CSS for focused element:
        inspekt focused css --file styles.css

        # Monitor focus changes:
        while true; do inspekt focused --json | jq -r '.tag'; sleep 1; done

    See also:
        inspekt inspected  - Get DevTools inspected element
        inspekt watch keyboard  - Monitor all keyboard/focus events
    """
    # If no subcommand is provided, show element info (default behavior)
    if ctx.invoked_subcommand is None:
        response = get_focused_data()
        display_element_info(response, source_type="focused", output_json=output_json)


@focused.command()
@click.option("--raw", is_flag=True, help="Output raw content without formatting (auto-enabled when piped)")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def text(raw, copy, output_json):
    """
    Get the text content of the focused element.

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).
    """
    from inspekt.app.cli.util import copy_text_to_clipboard
    from inspekt.app.cli.table import print_hint

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    response = get_focused_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not auto_raw:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
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

    # Raw mode: just print the text (auto-enabled when piped)
    if auto_raw:
        click.echo(text_content.rstrip())
        return

    # Formatted display with metadata
    _display_text_markdown_metadata(response)

    click.echo()

    # Display text preview (up to 500 characters) in styled code block
    from inspekt.app.cli.output import print_code_block

    if len(text_content) > 500:
        click.echo(f"Text Preview (first 500 of {len(text_content):,} characters):")
        click.echo()
        print_code_block(text_content[:500])
        click.echo()
        print_hint("Use `--raw` to see the full content")
    else:
        click.echo(f"Text Content ({len(text_content):,} characters):")
        click.echo()
        print_code_block(text_content)


@focused.command()
@click.option("--raw", is_flag=True, help="Output raw content without formatting (auto-enabled when piped)")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def markdown(raw, copy, output_json):
    """
    Get the focused element as Markdown (converted from HTML).

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).
    """
    from inspekt.app.cli.selection import html_to_markdown
    from inspekt.app.cli.util import copy_text_to_clipboard
    from inspekt.app.cli.table import print_hint

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    response = get_focused_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not auto_raw:
            click.echo(f"Error: {response['error']}", err=True)
            if response.get("hint"):
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

    # Raw mode: just print the markdown (auto-enabled when piped)
    if auto_raw:
        click.echo(markdown_content.rstrip())
        return

    # Formatted display with metadata
    _display_text_markdown_metadata(response)

    click.echo()

    # Display markdown preview (up to 500 characters) in styled code block
    from inspekt.app.cli.output import print_code_block

    if len(markdown_content) > 500:
        click.echo(f"Markdown Preview (first 500 of {len(markdown_content):,} characters):")
        click.echo()
        print_code_block(markdown_content[:500])
        click.echo()
        print_hint("Use `--raw` to see the full content")
    else:
        click.echo(f"Markdown Content ({len(markdown_content):,} characters):")
        click.echo()
        print_code_block(markdown_content)


@focused.command()
@click.option(
    "--file",
    "file_path",
    default=None,
    is_flag=False,
    flag_value="auto",
    help="Save to file (auto-generates name if no path given)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open file in default application after saving (requires --file)",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal file in file explorer after saving (requires --file)",
)
@click.option(
    "--include-css",
    is_flag=True,
    help="Also generate CSS file (requires --file)",
)
@click.option(
    "--bundled",
    is_flag=True,
    help="Embed CSS in HTML file (requires --include-css)",
)
@click.option(
    "--all-properties",
    is_flag=True,
    help="Include all CSS properties (for --include-css)",
)
@click.option(
    "--include-defaults",
    is_flag=True,
    help="Include CSS defaults (for --include-css)",
)
@click.option(
    "--optimize-css/--no-optimize-css",
    default=True,
    help="Optimize embedded CSS (when using --include-css). Enabled by default.",
)
@click.option(
    "--remove-comments",
    is_flag=True,
    help="Remove all HTML comments from output.",
)
@click.option(
    "--oklch",
    is_flag=True,
    help="Convert CSS colors to oklch format with names (when using --include-css).",
)
@click.option(
    "--alphabetize/--no-alphabetize",
    default=True,
    help="Sort CSS properties alphabetically (when using --include-css). Enabled by default.",
)
@click.option(
    "--rounding/--no-rounding",
    default=True,
    help="Round CSS pixel values to nearest whole pixel (when using --include-css). Enabled by default.",
)
@html_output_options
def html(file_path, open_after, reveal_after, include_css, bundled, all_properties, include_defaults, optimize_css,
         remove_comments, oklch, alphabetize, rounding, raw, copy, output_json, pretty, compact, colors, theme, indent):
    """
    Get the HTML of the focused element.

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).

    Examples:

        inspekt focused html                     # Display HTML
        inspekt focused html --file              # Save to auto-named file
        inspekt focused html --file snippet.html # Save to specific file
        inspekt focused html --file --include-css          # HTML + CSS files
        inspekt focused html --file --include-css --bundled  # Single bundled file
        inspekt focused html --file --include-css --oklch    # CSS with oklch colors
    """
    from inspekt.app.cli.output import validate_output_options
    from inspekt.app.cli.selection import apply_syntax_highlighting
    from inspekt.config import get_html_selection_config

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    # Validate common output options
    validate_output_options(file_path, copy, output_json, open_after, reveal_after)

    # Validate HTML-specific options
    if include_css and not file_path:
        click.echo("Error: --include-css requires --file", err=True)
        sys.exit(1)
    if bundled and not include_css:
        click.echo("Error: --bundled requires --include-css", err=True)
        sys.exit(1)
    if bundled and compact:
        click.echo(
            "Error: --bundled and --compact cannot be used together.\n"
            "Compact mode removes class names and other attributes that CSS selectors need to apply styles.",
            err=True,
        )
        sys.exit(1)
    # Generate timestamp upfront for matching filenames
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S") if file_path else None

    response = get_focused_data()

    if response.get("error"):
        if output_json:
            click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
        elif not auto_raw:
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

    # Get HTML content
    html_content = response.get("htmlContent", "")

    # Process HTML (always strip empty comments, optionally do more)
    if pretty or compact or remove_comments:
        from inspekt.services.html_processor import process_html
        html_content = process_html(
            html_content,
            format=pretty,
            compact=compact,
            remove_comments=remove_comments,
            indent=indent
        )
    else:
        from inspekt.services.html_processor import strip_empty_comments
        html_content = strip_empty_comments(html_content)

    # File output mode
    if file_path:
        from inspekt.services.bridge_executor import BridgeExecutor
        from inspekt.services.css_generator import generate_nested_css, count_properties
        from inspekt.services.script_loader import ScriptLoader

        selector = response.get("selector", "")
        domain = response.get("pageDomain", "localhost")
        page_title = response.get("pageTitle", "Inspekt Export")
        page_lang = response.get("pageLang", "en")

        # Determine HTML filename
        if file_path == "auto":
            html_filename = generate_element_filename(domain, selector, "html", source_type="focused", timestamp=timestamp)
        else:
            html_filename = file_path if file_path.endswith(".html") else f"{file_path}.html"

        # Generate CSS if requested
        css_content = None
        property_count = 0
        element_count = 1
        if include_css:
            executor = BridgeExecutor()
            executor.ensure_server_running()
            loader = ScriptLoader()

            js_options = {
                "allProperties": all_properties,
                "includeDefaults": include_defaults,
                "roundPixels": rounding,
            }

            script = loader.load_with_substitution_sync(
                "get_computed_css.js",
                {"OPTIONS_PLACEHOLDER": js_options, "SOURCE_TYPE_PLACEHOLDER": "focused"}
            )

            try:
                css_result = executor.execute(script, timeout=30.0)
                if css_result.get("ok"):
                    css_response = css_result.get("result", {})
                    if css_response.get("ok"):
                        root = css_response.get("root", {})
                        element_count = css_response.get("elementCount", 1)
                        css_content = generate_nested_css(root)
                        property_count = count_properties(root)

                        from inspekt.services.css_generator import collect_rounded_props, collect_computed_props
                        rounded_props = collect_rounded_props(root) if rounding else None
                        computed_props = collect_computed_props(root) if not rounding else None

                        if optimize_css or oklch or alphabetize:
                            from inspekt.services.css_optimizer import optimize_css as do_optimize_css
                            css_content = do_optimize_css(
                                css_content,
                                convert_to_oklch=oklch,
                                add_color_names=True,
                                alphabetize=alphabetize,
                                rounded_props=rounded_props,
                                computed_props=computed_props,
                            )
            except Exception as e:
                click.echo(f"Warning: Failed to extract CSS: {e}", err=True)

        # Bundled mode: single HTML file with embedded CSS
        if bundled and css_content:
            root_selector = css_content.split("{")[0].strip()
            scoped_css = css_content.replace(root_selector + " {", ".inspekt-root {", 1)

            bundled_html = f'''<!DOCTYPE html>
<html lang="{page_lang}">
<head>
  <meta charset="utf-8">
  <title>{page_title} — {selector}</title>
  <style>
{scoped_css}
  </style>
</head>
<body>
<div class="inspekt-root">
{html_content}
</div>
</body>
</html>'''

            from inspekt.app.cli.output import OutputHandler

            output_path = Path(html_filename)
            OutputHandler.save_and_handle(
                bundled_html,
                output_path,
                open_after=open_after,
                reveal_after=reveal_after,
                content_type="bundled HTML+CSS",
                details=f"{property_count} properties",
            )
            return

        # Write HTML file
        from inspekt.app.cli.output import OutputHandler

        html_output_path = Path(html_filename)
        OutputHandler.save_and_handle(
            html_content,
            html_output_path,
            content_type="HTML",
        )

        # Write CSS file if requested (not bundled)
        if include_css and css_content:
            css_filename = html_filename.rsplit(".", 1)[0] + ".css"
            css_output_path = Path(css_filename)
            OutputHandler.save_and_handle(
                css_content,
                css_output_path,
                content_type="CSS",
                details=f"{property_count} properties from {element_count} elements",
            )

        # Open/reveal file if requested (open HTML file)
        if open_after:
            OutputHandler.open_file(html_output_path)
        if reveal_after:
            OutputHandler.reveal_file(html_output_path)
        return

    # Copy to clipboard (before syntax highlighting, we want raw content)
    if copy:
        from inspekt.app.cli.output import OutputHandler
        OutputHandler.copy_to_clipboard(html_content)
        sys.exit(0)

    # JSON mode - return un-highlighted HTML with metadata
    if output_json:
        from inspekt.app.cli.output import JsonOutput
        (
            JsonOutput()
            .with_content("html", response.get("htmlContent", ""))
            .with_selector(response.get("selector"), response.get("tag"))
            .with_fields(
                xpath=response.get("xpath", ""),
                descendantCount=response.get("descendantCount", 0),
                nestingDepth=response.get("nestingDepth", 0),
                textLength=response.get("textLength", 0),
                attributeCount=response.get("attributeCount", 0),
            )
            .with_page_metadata(response)
            .print()
        )
        return

    # Raw mode: just print the HTML (auto-enabled when piped)
    if auto_raw:
        click.echo(html_content.rstrip())
        return

    # Formatted display with summary table
    from inspekt.app.cli.table import Table
    from inspekt.app.cli.output import pluralize

    # Extract statistics
    tag = response.get("tag", "element")
    selector = response.get("selector", "")
    xpath = response.get("xpath", "")
    descendant_count = response.get("descendantCount", 0)
    nesting_depth = response.get("nestingDepth", 0)
    text_length = response.get("textLength", 0)

    # Build statistics rows
    stats_rows = []
    stats_rows.append(["Tag", f"<{tag}>"])
    if descendant_count > 0:
        elem_word = pluralize(descendant_count, "descendant", "descendants")
        stats_rows.append(["Contains", f"{descendant_count} {elem_word}"])
    stats_rows.append(["Depth", f"{nesting_depth} levels from <html>"])
    if text_length > 0:
        stats_rows.append(["Text", f"{text_length:,} characters"])

    # Display summary table
    click.echo()
    table = Table(
        ["Metric", "Value"],
        alignments=["left", "left"],
        title="HTML from focused element",
        icon="\ue736"
    )
    table.set_data(stats_rows)
    table.print_header(skip_column_headers=True)
    for row in stats_rows:
        table.print_row(row)
    table.print_footer()

    # Show selectors
    click.echo()
    click.echo(click.style("Selector  ", fg="bright_black") + selector)
    if xpath:
        click.echo(click.style("XPath     ", fg="bright_black") + xpath)

    # Check rendering limits before attempting to display
    limit_warning = _check_render_limits(
        content_type="HTML",
        character_count=len(html_content),
        descendant_count=descendant_count,
    )

    click.echo()

    if limit_warning:
        # Show warning instead of rendered content
        from inspekt.app.cli.table import print_warning
        print_warning(limit_warning)
    else:
        # Apply syntax highlighting for formatted display
        if colors and sys.stdout.isatty():
            html_content = apply_syntax_highlighting(html_content, theme=theme)

        # Remove empty lines for cleaner output
        clean_html = '\n'.join(line for line in html_content.split('\n') if line.strip())

        # Display HTML content in styled code block
        from inspekt.app.cli.output import print_code_block
        print_code_block(clean_html)

    # Show TIPS
    tips = []
    if not pretty:
        tips.append(("`--pretty`", "Format HTML with indentation", None))
    if not compact:
        tips.append(("`--compact`", "Strip classes, data-* attrs, styles; truncate long text (for documentation only)", None))
    if not remove_comments:
        tips.append(("`--no-comments`", "Remove HTML comments", None))
    if colors:
        tips.append(("`--raw`", "Output without syntax highlighting", None))

    if tips:
        click.echo()
        _print_tips_section(tips)


@focused.command()
@click.option(
    "--file",
    "file_path",
    default=None,
    is_flag=False,
    flag_value="auto",
    help="Save to file (auto-generates name if no path given)",
)
@click.option(
    "--open",
    "open_after",
    is_flag=True,
    help="Open file in default application after saving (requires --file)",
)
@click.option(
    "--reveal",
    "reveal_after",
    is_flag=True,
    help="Reveal file in file explorer after saving (requires --file)",
)
@click.option("--raw", is_flag=True, help="Output raw CSS without formatting (auto-enabled when piped)")
@click.option("--copy", is_flag=True, help="Copy output to clipboard")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--all-properties",
    is_flag=True,
    help="Include all ~300 computed properties (default: common properties only)",
)
@click.option(
    "--include-defaults",
    is_flag=True,
    help="Include browser default values (default: exclude)",
)
@click.option(
    "--optimize/--no-optimize",
    default=True,
    help="Optimize CSS (merge shorthands). Enabled by default.",
)
@click.option(
    "--oklch",
    is_flag=True,
    help="Convert colors to oklch format with human-readable names.",
)
@click.option(
    "--alphabetize/--no-alphabetize",
    default=True,
    help="Sort CSS properties alphabetically. Enabled by default.",
)
@click.option(
    "--rounding/--no-rounding",
    default=True,
    help="Round pixel values to nearest whole pixel. Enabled by default.",
)
@click.option(
    "--heuristic-comments",
    is_flag=True,
    help="Add helpful comments based on property-value patterns.",
)
@click.option(
    "--two-columns",
    is_flag=True,
    help="Format output with aligned columns: property and value aligned, comment follows immediately.",
)
@click.option(
    "--three-columns",
    is_flag=True,
    help="Format output with aligned columns: property, value, and comment each in separate columns.",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Compact CSS by shortening data URIs, long URLs, var() names, and animation names.",
)
@click.option(
    "--authored",
    is_flag=True,
    help="Show original authored CSS values (e.g., clamp(), var(), rem) instead of browser-computed values.",
)
def css(file_path, open_after, reveal_after, raw, copy, output_json, all_properties, include_defaults, optimize, oklch, alphabetize, rounding, heuristic_comments, two_columns, three_columns, compact, authored):
    """
    Extract computed CSS styles as nested CSS from the focused element.

    When stdout is piped or redirected, decorations are automatically suppressed
    (equivalent to --raw flag).
    """
    from inspekt.app.cli.output import validate_output_options
    from inspekt.services.bridge_executor import BridgeExecutor
    from inspekt.services.css_generator import generate_nested_css, count_properties
    from inspekt.services.script_loader import ScriptLoader

    validate_output_options(file_path, copy, output_json, open_after, reveal_after)

    # Auto-enable raw mode when output is piped/redirected
    auto_raw = raw or not sys.stdout.isatty()

    executor = BridgeExecutor()
    executor.ensure_server_running()
    loader = ScriptLoader()

    js_options = {
        "allProperties": all_properties,
        "includeDefaults": include_defaults,
        "roundPixels": rounding,
    }

    script = loader.load_with_substitution_sync(
        "get_computed_css.js",
        {"OPTIONS_PLACEHOLDER": js_options, "SOURCE_TYPE_PLACEHOLDER": "focused"}
    )

    try:
        result = executor.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})

        if not response.get("ok"):
            click.echo(f"Error: {response.get('error', 'Failed to extract styles')}", err=True)
            sys.exit(1)

        root = response.get("root", {})
        element_count = response.get("elementCount", 1)
        stats = response.get("stats", {})

        total_considered = stats.get("totalConsidered", 0)
        stripped_as_default = stats.get("strippedAsDefault", 0)
        stripped_as_inherited = stats.get("strippedAsInherited", 0)

        # Optionally fetch and merge authored CSS values via CDP
        authored_count = 0
        if authored:
            authored_script = loader.load_with_substitution_sync(
                "get_authored_css_cdp.js",
                {"SOURCE_TYPE_PLACEHOLDER": "focused", "ELEMENT_COUNT_PLACEHOLDER": element_count}
            )
            try:
                authored_result = executor.execute(authored_script, timeout=30.0)
                if authored_result.get("ok"):
                    authored_response = authored_result.get("result", {})
                    if authored_response.get("ok"):
                        from inspekt.services.css_authored_merger import merge_authored_css
                        authored_map = authored_response.get("elements", {})
                        root = merge_authored_css(root, authored_map)
                        from inspekt.services.css_generator import collect_authored_props
                        authored_count = len(collect_authored_props(root))
            except Exception:
                from inspekt.app.cli.table import print_warning
                print_warning("Could not retrieve authored CSS values. Showing computed values only.")

        css_content = generate_nested_css(root)
        property_count = count_properties(root)

        from inspekt.services.css_generator import collect_rounded_props, collect_computed_props
        rounded_props = collect_rounded_props(root) if rounding else None
        computed_props = collect_computed_props(root) if not rounding else None

        original_property_count = property_count

        optimized = optimize or oklch or alphabetize or heuristic_comments or two_columns or three_columns
        if optimized:
            from inspekt.services.css_optimizer import optimize_css
            # Collect cross-reference values (authored → computed) when authored mode is active
            cross_ref = None
            if authored and authored_count > 0:
                from inspekt.services.css_generator import collect_cross_ref_values
                cross_ref = collect_cross_ref_values(root)
            css_content = optimize_css(
                css_content,
                convert_to_oklch=oklch,
                add_color_names=True,
                alphabetize=alphabetize,
                rounded_props=rounded_props,
                computed_props=computed_props,
                heuristic_comments=heuristic_comments,
                column_format="two" if two_columns else ("three" if three_columns else None),
                cross_ref_values=cross_ref,
            )
            optimized_property_count = count_css_properties_in_string(css_content)
            merged_count = original_property_count - optimized_property_count
            shorthand_count = count_shorthands_in_css(css_content)
            property_count = optimized_property_count
        else:
            merged_count = 0
            shorthand_count = 0

        if compact:
            from inspekt.services.html_processor import compact_css as compact_css_content
            css_content = compact_css_content(css_content, strip_comments=False)

        from inspekt.app.cli.output import OutputHandler, JsonOutput, pluralize

        if file_path:
            selector = root.get("selector", root.get("tag", "unknown"))
            domain = response.get("pageDomain", "localhost")

            if file_path == "auto":
                output_file = generate_element_filename(domain, selector, "css", source_type="focused")
            else:
                output_file = file_path if file_path.endswith(".css") else f"{file_path}.css"

            output_path = Path(output_file)
            elem_word = pluralize(element_count, "element")
            prop_word = pluralize(property_count, "property", "properties")
            OutputHandler.save_and_handle(
                css_content,
                output_path,
                open_after=open_after,
                reveal_after=reveal_after,
                content_type="CSS",
                details=f"{property_count} {prop_word} from {element_count} {elem_word}",
            )
            return

        if copy:
            elem_word = pluralize(element_count, "element")
            prop_word = pluralize(property_count, "property", "properties")
            OutputHandler.copy_to_clipboard(css_content, quiet=True)
            click.echo(f"Copied CSS to clipboard ({property_count} {prop_word} from {element_count} {elem_word})", err=True)
            sys.exit(0)

        if output_json:
            selector = root.get("selector", root.get("tag", "unknown"))
            (
                JsonOutput()
                .with_content("css", css_content)
                .with_selector(selector)
                .with_counts(element_count=element_count, property_count=property_count)
                .with_page_metadata(response)
                .print()
            )
            return

        # Raw mode: just print the CSS (auto-enabled when piped)
        if auto_raw:
            click.echo(css_content)
            return

        from inspekt.app.cli.table import Table, print_hint

        elem_word = pluralize(element_count, "element")

        stats_rows = []
        if total_considered > 0:
            total_word = pluralize(total_considered, "property", "properties")
            stats_rows.append(["Scanned", f"{total_considered} {total_word}"])
        if stripped_as_default > 0:
            default_word = pluralize(stripped_as_default, "browser default property", "browser default properties")
            stats_rows.append(["Removed", f"{stripped_as_default} {default_word}"])
        if stripped_as_inherited > 0:
            inherited_word = pluralize(stripped_as_inherited, "inherited duplicate", "inherited duplicates")
            stats_rows.append(["Removed", f"{stripped_as_inherited} {inherited_word}"])
        if authored and authored_count > 0:
            authored_word = pluralize(authored_count, "property", "properties")
            stats_rows.append(["Authored", f"{authored_count} {authored_word} resolved from source stylesheets"])
        if optimized and merged_count > 0:
            merged_word = pluralize(merged_count, "property", "properties")
            shorthand_word = pluralize(shorthand_count, "shorthand", "shorthands")
            stats_rows.append(["Merged", f"{merged_count} {merged_word} into {shorthand_count} {shorthand_word}"])
        prop_word = pluralize(property_count, "effective property", "effective properties")
        stats_rows.append(["Kept", f"{property_count} {prop_word}"])

        click.echo()
        css_title = "Authored + Computed CSS" if authored and authored_count > 0 else "Computed CSS"
        table = Table(
            ["Metric", "Value"],
            alignments=["left", "left"],
            title=f"{css_title} from {element_count} {elem_word}",
            icon="\ue749"
        )
        table.set_data(stats_rows)
        table.print_header(skip_column_headers=True)
        for row in stats_rows:
            table.print_row(row)
        table.print_footer()

        # Check rendering limits before attempting to display
        limit_warning = _check_render_limits(
            content_type="CSS",
            character_count=len(css_content),
            css_property_count=total_considered,
        )

        click.echo()

        if limit_warning:
            # Show warning instead of rendered content
            from inspekt.app.cli.table import print_warning
            print_warning(limit_warning)
        else:
            # Apply CSS syntax highlighting and display in styled code block
            from inspekt.app.cli.output import print_code_block

            if sys.stdout.isatty() and not auto_raw:
                try:
                    from pygments import highlight
                    from pygments.lexers import CssLexer
                    from pygments.formatters import Terminal256Formatter

                    highlighted = highlight(css_content, CssLexer(), Terminal256Formatter(style="monokai"))
                    print_code_block(highlighted.rstrip())
                except ImportError:
                    print_code_block(css_content)
            else:
                print_code_block(css_content)

        tips = []
        if optimized and not oklch:
            tips.append(("`--oklch`", "Display colors in OKLCH (perceptual) format", None))
        if not heuristic_comments:
            from inspekt.services.css_property_comments import get_random_tip_example
            prop, value, comment = get_random_tip_example()
            tips.append(("`--heuristic-comments`", "Add helpful comments", f"`{prop}: {value}` → /* {comment} */"))
        if not all_properties:
            tips.append(("`--all-properties`", "Include the complete computed style (~300 properties)", None))
        if optimized:
            tips.append(("`--no-optimize`", "Output raw data (no shorthand merging)", None))
        if not two_columns and not three_columns:
            tips.append(("`--two-columns`", "Align properties and values in columns", None))
        if not compact:
            tips.append(("`--compact`", "Shorten data URIs, URLs, and long text (breaks CSS; for documentation only)", None))
        if not authored:
            tips.append(("`--authored`", "Show original authored values (clamp(), var(), rem) via Chrome DevTools Protocol", None))

        if tips:
            click.echo()
            _print_tips_section(tips)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.group()
def screenshot():
    """Capture screenshots of elements, viewport, or full page."""
    pass


def screenshot_element_options(func):
    """
    Apply common screenshot element options to a command.

    This decorator applies all options shared between screenshot_node and
    screenshot_focused, reducing code duplication.
    """
    # Define options in reverse order (decorators are applied bottom-to-top)
    options = [
        click.option("--compare", is_flag=True, default=False, help="Create comparison grid showing normal state alongside forced state(s)"),
        click.option("--state", "-S", "states", multiple=True, type=click.Choice(["hover", "focus", "focus-visible", "focus-within", "active", "target"], case_sensitive=False), help="Force CSS pseudo-state(s) on element (repeatable: -S hover -S focus)"),
        click.option("--keep-selection", is_flag=True, default=False, help="Don't clear text selection before capture"),
        click.option("--keep-zoom", is_flag=True, default=False, help="Don't reset zoom to 100% before capture"),
        click.option("--redact-selectors", default=None, help="Additional CSS selectors to redact (comma-separated)"),
        click.option("--redact-style", type=click.Choice(["blur", "bar"], case_sensitive=False), default="bar", help="Redaction style: bar (████ blocks, default) or blur"),
        click.option("--redact/--no-redact", default=True, help="Redact sensitive data before capture (enabled by default for security)"),
        click.option("--metadata/--no-metadata", default=True, help="Embed metadata (URL, timestamp, viewport) in image file (default: enabled)"),
        click.option("--json", "json_output", is_flag=True, help="Output result as JSON (for scripting)"),
        click.option("--quiet", "-q", is_flag=True, help="Suppress output except errors"),
        click.option("--force", "-f", is_flag=True, help="Overwrite existing file without confirmation"),
        click.option("--clipboard", is_flag=True, help="Copy to clipboard instead of saving to file"),
        click.option("--reveal", "reveal_after", is_flag=True, help="Reveal screenshot in file explorer after saving"),
        click.option("--open", "open_after", is_flag=True, help="Open screenshot in default application after saving"),
        click.option("--hide-outline/--keep-outline", default=True, help="Hide element outline during capture (default: yes)"),
        click.option("--scroll-into-view/--no-scroll", default=True, help="Scroll element into view before capture (default: yes)"),
        click.option("--quality", type=click.FloatRange(0.0, 1.0), default=None, help="Quality for lossy formats (0.0-1.0, default: from config)"),
        click.option("--format", type=click.Choice(["png", "jpg", "webp"], case_sensitive=False), default=None, help="Output format (default: from config)"),
        click.option("--max-width", type=int, default=None, help="Resize output to fit within max width (maintains aspect ratio)"),
        click.option("--scale", "--dpr", type=click.IntRange(1, 4), default=None, help="Scale/DPR factor 1-4 (1=standard, 2=retina). Alias: --dpr (default: from config)"),
        click.option("--enable-compression", is_flag=True, default=False, help="Force lossless compression even for files larger than 5 MB"),
        click.option("--disable-compression", is_flag=True, default=False, help="Skip lossless PNG compression entirely"),
        click.option("--margin-color", "-c", default=None, help="Margin color: 'auto' (sample first pixel), hex code like '#fff', or color name (default: from config)"),
        click.option("--margin", "-m", type=int, default=None, help="Margin in pixels around screenshot (default: from config)"),
        click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (default: auto-generated)"),
    ]
    for option in options:
        func = option(func)
    return func


@screenshot.command(name="node")
@click.option(
    "--selector",
    "-s",
    default=None,
    help="CSS selector of element (default: use currently inspected element)",
)
@screenshot_element_options
def screenshot_node(selector, output, margin, margin_color, disable_compression, enable_compression, scale, max_width, format, quality, scroll_into_view, hide_outline, open_after, reveal_after, clipboard, force, quiet, json_output, metadata, redact, redact_style, redact_selectors, keep_zoom, keep_selection, states, compare):
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

        # Capture element with forced :hover state
        inspekt screenshot node --state hover --open

        # Comparison grid (shows normal + hover side by side)
        inspekt screenshot node --state hover --compare --open

        # Multiple states comparison (creates 2x2 grid)
        inspekt screenshot node -S hover -S focus -S active --compare -o button_states.png
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
    if scale is None:
        scale = config["scale"]
    if format is None:
        format = config["format"]
    if quality is None:
        quality = config["quality"]

    # Determine compression mode from flags
    if disable_compression:
        compression = "disabled"
    elif enable_compression:
        compression = "enabled"
    else:
        compression = "auto"

    try:
        # ========== PSEUDO-STATE COMPARISON MODE ==========
        # Handle --compare flag: captures element in multiple states and creates grid
        if compare:
            from inspekt.app.cli import icons
            from inspekt.services.image_grid import compose_state_grid, is_pillow_installed
            from inspekt.services.screenshot_utils import decode_data_url
    
            if not is_pillow_installed():
                click.echo("Error: Comparison screenshots require Pillow. Install with: pip install Pillow", err=True)
                sys.exit(1)
    
            # Load pseudo-state screenshot script
            try:
                pseudo_script = loader.load_script_sync("screenshot_pseudo.js")
            except FileNotFoundError as e:
                click.echo(f"Error: Pseudo-state script not found: {e}", err=True)
                sys.exit(1)
    
            # Build list of states: always include 'normal' first
            # If no states specified with --compare, just show normal
            if states:
                state_list = ['normal'] + [s.lower() for s in states]
            else:
                state_list = ['normal']
    
            if not quiet and not json_output:
                click.echo(icons.camera(f"Capturing {len(state_list)} states: {', '.join(state_list)}"))
    
            # Check for inspected element first
            if not selector:
                check_code = """(function() {
                    if (window.__INSPEKT_INSPECTED_ELEMENT__) return true;
                    try { if (typeof $0 !== 'undefined' && $0) return true; } catch(e) {}
                    return false;
                })()"""
                check_result = executor.execute(check_code, timeout=5.0)
                if not check_result.get("ok") or not check_result.get("result"):
                    if json_output:
                        click.echo(json.dumps({"ok": False, "error": "No element is currently inspected. Use --selector or inspect an element first."}))
                    else:
                        click.echo("Error: No element is currently inspected. Use --selector or inspect an element first.", err=True)
                    sys.exit(1)
    
            # Capture screenshots for each state
            screenshots = []
            tag_name = "element"
            used_fallback = False
            total_rules_injected = 0
    
            for state in state_list:
                if not quiet and not json_output:
                    if state == 'normal':
                        click.echo(icons.info("Capturing normal state…"))
                    else:
                        click.echo(icons.info(f"Forcing :{state} state…"))
    
                # Build options for this state
                state_options = {
                    "selector": selector,
                    "margin": margin,
                    "marginColor": margin_color,
                    "scale": scale,
                    "format": format,
                    "quality": quality,
                    "scrollIntoView": scroll_into_view,
                    "hideOutline": hide_outline,
                    "keepZoom": keep_zoom,
                    "keepSelection": keep_selection,
                }
    
                # Replace placeholders and execute
                code = pseudo_script.replace("'STATE_PLACEHOLDER'", json.dumps(state))
                code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(state_options))
    
                result = executor.execute(code, timeout=30.0)
    
                if not result.get("ok"):
                    click.echo(f"Error executing script for {state} state: {result.get('error')}", err=True)
                    sys.exit(1)
    
                response = result.get("result", {})
                if not response.get("ok"):
                    click.echo(f"Error capturing {state} state: {response.get('error')}", err=True)
                    sys.exit(1)
    
                # Track if fallback was used and how many rules were injected
                if response.get("usedFallback"):
                    used_fallback = True
                    total_rules_injected += response.get("rulesInjected", 0)

                # Get tag name from first capture
                if state == 'normal':
                    tag_name = response.get("tagName", "element")

                # Decode and store screenshot
                try:
                    image_data = decode_data_url(response.get("dataUrl"))
                    screenshots.append((state, image_data))
                except Exception as e:
                    click.echo(f"Error decoding screenshot for {state}: {e}", err=True)
                    sys.exit(1)

            # Show CSS injection note with rules count
            if used_fallback and not quiet and not json_output:
                if total_rules_injected > 0:
                    click.echo(click.style("\ue749  ", fg="blue") + f"Applied {total_rules_injected} CSS rules via injection (DevTools is open)")
                else:
                    click.echo(click.style("\uf071  ", fg="yellow") + "No CSS rules found for pseudo-state (element may not have :focus/:hover styles)")
    
            # Compose grid
            if not quiet and not json_output:
                click.echo(icons.info("Composing comparison grid…"))
    
            try:
                final_image = compose_state_grid(screenshots, columns=2)
            except Exception as e:
                click.echo(f"Error composing grid: {e}", err=True)
                sys.exit(1)
    
            # Get grid dimensions from composed image
            try:
                import io
                from PIL import Image
                with Image.open(io.BytesIO(final_image)) as img:
                    grid_width, grid_height = img.size
            except Exception:
                grid_width, grid_height = 0, 0
    
            # Generate filename suffix for compare mode
            if len(states) == 1:
                compare_suffix = f"_{states[0]}"
            else:
                compare_suffix = "_states"
    
            # Set up variables for the common processing pipeline below
            # The compare mode will fall through to the same processing as regular mode
            compare_mode_image_data = final_image
            compare_mode_response = {
                "ok": True,
                "width": grid_width,
                "height": grid_height,
                "tagName": tag_name,
                "url": None,  # Will be captured from first screenshot if available
                "states": list(state_list),
                "usedFallback": used_fallback,
            }
            # Fall through to common processing pipeline...
    
        # ========== SCREENSHOT CAPTURE ==========
        # Compare mode already has the image data from grid composition
        # Regular mode needs to capture a screenshot
    
        if compare:
            # Compare mode: use the composed grid image
            image_data = compare_mode_image_data
            response = compare_mode_response
            tag_name = response.get("tagName", "element")
            forced_state = None  # States already applied during compare capture
            redacted_count = 0  # Redaction not applied in compare mode (yet)
        else:
            # ========== REGULAR SCREENSHOT MODE ==========
            from inspekt.app.cli import icons
    
            # Determine forced state (if any) for integration with normal flow
            forced_state = states[0].lower() if states else None
    
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
                "keepZoom": keep_zoom,
                "keepSelection": keep_selection,
            }
    
            # Replace placeholders
            code = script.replace("'MODE_PLACEHOLDER'", json.dumps("node"))
            code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options))
    
            # Pre-flight check: verify element exists before any processing
            if not selector:
                # Check if there's an inspected element (same logic as screenshot_unified.js)
                check_code = """(function() {
                    // Try Chrome extension auto-stored element first
                    if (window.__INSPEKT_INSPECTED_ELEMENT__) return true;
                    // Fallback: check for $0 in console context (won't work from extension)
                    try { if (typeof $0 !== 'undefined' && $0) return true; } catch(e) {}
                    return false;
                })()"""
                check_result = executor.execute(check_code, timeout=5.0)
                if not check_result.get("ok") or not check_result.get("result"):
                    if json_output:
                        click.echo(json.dumps({"ok": False, "error": "No element is currently inspected. Use --selector flag or inspect an element first."}))
                    else:
                        click.echo("Error: No element is currently inspected. Use --selector flag or inspect an element first.", err=True)
                    sys.exit(1)
    
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
                                    click.echo(click.style("\uedaa  ", fg="blue") + f"Redacting: {', '.join(messages)}…")
                                else:
                                    click.echo(icons.shield_check("No sensitive elements found to redact"))
    
                except FileNotFoundError:
                    if not quiet and not json_output:
                        click.echo("Warning: Redaction script not found, skipping redaction", err=True)
                except Exception as e:
                    if not quiet and not json_output:
                        click.echo(f"Warning: Redaction failed: {e}", err=True)
    
            # Force pseudo-state if requested (before capture)
            pseudo_state_applied = False
            pseudo_state_fallback = False
            rules_count = 0
            if forced_state:
                try:
                    # Use JavaScript to force pseudo-state via extension
                    force_code = f"""(async function() {{
                        const requestId = 'pseudo-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
    
                        return new Promise((resolve) => {{
                            const timeout = setTimeout(() => {{
                                window.removeEventListener('message', handler);
                                resolve({{ ok: false, error: 'Pseudo-state request timed out' }});
                            }}, 10000);
    
                            const handler = (event) => {{
                                if (event.source !== window) return;
                                const msg = event.data;
                                if (msg?.type === 'INSPEKT_PSEUDO_STATE_RESPONSE' &&
                                    msg?.source === 'inspekt-extension' &&
                                    msg?.requestId === requestId) {{
                                    clearTimeout(timeout);
                                    window.removeEventListener('message', handler);
                                    resolve(msg.response);
                                }}
                            }};
    
                            window.addEventListener('message', handler);
                            window.postMessage({{
                                type: 'INSPEKT_FORCE_PSEUDO_STATE',
                                source: 'inspekt-page',
                                requestId: requestId,
                                state: {json.dumps(forced_state)},
                                selector: {json.dumps(selector)}
                            }}, '*');
                        }});
                    }})()"""
    
                    force_result = executor.execute(force_code, timeout=15.0)
                    # Check CDP success - handle None values at each level
                    cdp_success = False
                    if force_result is not None and force_result.get("ok"):
                        inner_result = force_result.get("result")
                        if isinstance(inner_result, dict) and inner_result.get("ok"):
                            cdp_success = True
                    if cdp_success:
                        pseudo_state_applied = True
                    else:
                        # CDP failed, try CSS injection fallback
                        fallback_code = f"""(function() {{
                            const state = {json.dumps(forced_state)};
                            const selector = {json.dumps(selector)};
                            const element = selector
                                ? document.querySelector(selector)
                                : window.__INSPEKT_INSPECTED_ELEMENT__;
    
                            if (!element) return {{ ok: false, error: 'No element found' }};
    
                            element.dataset.inspektPseudoState = state;
                            const stateRegex = new RegExp(':' + state + '(?![a-zA-Z-])', 'g');
    
                            // Calculate CSS specificity (simplified: count IDs, classes, elements)
                            function getSpecificity(sel) {{
                                const ids = (sel.match(/#[a-zA-Z][a-zA-Z0-9_-]*/g) || []).length;
                                const classes = (sel.match(/\\.[a-zA-Z][a-zA-Z0-9_-]*/g) || []).length;
                                const attrs = (sel.match(/\\[[^\\]]+\\]/g) || []).length;
                                const pseudoClasses = (sel.match(/:[a-zA-Z][a-zA-Z0-9-]*/g) || []).length;
                                const elements = (sel.match(/^[a-zA-Z]+|\\s+[a-zA-Z]+/g) || []).length;
                                return ids * 10000 + (classes + attrs + pseudoClasses) * 100 + elements;
                            }}
    
                            const collectedRules = [];
    
                            for (const sheet of document.styleSheets) {{
                                try {{
                                    for (const rule of sheet.cssRules) {{
                                        if (rule.selectorText?.includes(':' + state)) {{
                                            try {{
                                                const baseSelector = rule.selectorText.replace(stateRegex, '').trim();
                                                if (!baseSelector) continue;
                                                if (element.matches(baseSelector) || element.closest(baseSelector)) {{
                                                    const newSelector = rule.selectorText.replace(
                                                        stateRegex,
                                                        '[data-inspekt-pseudo-state="' + state + '"]'
                                                    );
                                                    // Add !important to all properties
                                                    let cssText = rule.style.cssText;
                                                    cssText = cssText.replace(/;/g, ' !important;');
                                                    if (cssText && !cssText.endsWith(';')) {{
                                                        cssText += ' !important';
                                                    }}
                                                    collectedRules.push({{
                                                        specificity: getSpecificity(rule.selectorText),
                                                        css: newSelector + ' {{ ' + cssText + ' }}'
                                                    }});
                                                }}
                                            }} catch (e) {{}}
                                        }}
                                    }}
                                }} catch (e) {{}}
                            }}
    
                            // Sort by specificity (lowest first, so highest specificity rules come last and win)
                            collectedRules.sort((a, b) => a.specificity - b.specificity);
                            const injectedRules = collectedRules.map(r => r.css);
    
                            if (injectedRules.length > 0) {{
                                const style = document.createElement('style');
                                style.id = 'inspekt-pseudo-state-override';
                                style.textContent = injectedRules.join('\\n');
                                document.head.appendChild(style);
                            }}
    
                            return {{ ok: true, method: 'css-injection', rulesInjected: injectedRules.length }};
                        }})()"""
    
                        fallback_result = executor.execute(fallback_code, timeout=5.0)
                        # Check fallback success - handle None values at each level
                        fallback_success = False
                        if fallback_result is not None and fallback_result.get("ok"):
                            inner_result = fallback_result.get("result")
                            if isinstance(inner_result, dict) and inner_result.get("ok"):
                                fallback_success = True
                        if fallback_success:
                            pseudo_state_applied = True
                            pseudo_state_fallback = True
                            # Store rules count for diagnostic message
                            inner = fallback_result.get("result", {})
                            if isinstance(inner, dict):
                                rules_count = inner.get("rulesInjected", 0)
                except Exception as e:
                    if not quiet and not json_output:
                        click.echo(f"Warning: Could not force pseudo-state: {e}", err=True)
    
                # Show CSS injection status before capture
                if pseudo_state_fallback and not quiet and not json_output:
                    # Note: CDP is unavailable because DevTools is open (required for inspected element)
                    # CSS injection is the expected method for this use case
                    if rules_count > 0:
                        click.echo(click.style("\ue749  ", fg="blue") + f"Applied {rules_count} CSS rules for :{forced_state} state")
    
            # Execute the screenshot capture
            result = executor.execute(code, timeout=60.0)
    
            # Clear pseudo-state after capture
            if forced_state and pseudo_state_applied:
                try:
                    clear_code = """(function() {
                        // Clear CDP state
                        const requestId = 'clear-' + Date.now();
                        window.postMessage({
                            type: 'INSPEKT_CLEAR_PSEUDO_STATE',
                            source: 'inspekt-page',
                            requestId: requestId
                        }, '*');
    
                        // Clear CSS injection
                        const el = document.querySelector('[data-inspekt-pseudo-state]');
                        if (el) delete el.dataset.inspektPseudoState;
                        const style = document.getElementById('inspekt-pseudo-state-override');
                        if (style) style.remove();
    
                        return { ok: true };
                    })()"""
                    executor.execute(clear_code, timeout=5.0)
                except Exception:
                    pass  # Silently ignore cleanup failures
    
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
                # 1. Zoom reset (if zoom was adjusted)
                if response.get("zoomWasReset"):
                    original_zoom = response.get("originalZoom", 1.0)
                    zoom_percent = int(original_zoom * 100)
                    # Use zoom-out icon if original > 1.0 (we're reducing), zoom-in icon if < 1.0 (we're increasing)
                    zoom_icon = "\uf532" if original_zoom > 1.0 else "\uf531"
                    click.echo(click.style(f"{zoom_icon}  ", fg="blue") + f"Resetting zoom level from {zoom_percent}% to 100%…")
    
                # 2. Selection cleared (if text was selected)
                if response.get("selectionCleared"):
                    click.echo(click.style("\U000F09A9  ", fg="blue") + "Clearing text selection…")
    
                # 3. Scroll action (if element was scrolled into view)
                if scroll_dir:
                    click.echo(icons.scroll_action(scroll_dir, f"Scrolling <{tag_name}> into view…"))
    
                # 4. Capture action
                state_suffix = f" with :{forced_state} state" if forced_state else ""
                if selector:
                    click.echo(click.style("\ueada  ", fg="blue") + f"Capturing element{state_suffix}: {selector}")
                else:
                    click.echo(icons.camera(f"Capturing currently inspected element{state_suffix}…"))
    
                # 5. Restore feedback (zoom level and/or text selection)
                zoom_restored = response.get("zoomWasReset")
                selection_restored = response.get("selectionCleared")
                if zoom_restored and selection_restored:
                    click.echo(icons.info("Zoom level and text selection restored"))
                elif zoom_restored:
                    click.echo(icons.info("Zoom level restored"))
                elif selection_restored:
                    click.echo(icons.info("Text selection restored"))
    
                # 6. Restore scroll position (if we scrolled) - use opposite direction
                if scroll_dir:
                    opposite_dir = {"up": "down", "down": "up", "left": "right", "right": "left"}.get(scroll_dir, "up")
                    click.echo(icons.scroll_action(opposite_dir, "Restoring scroll position…"))
    
                # 6. CDP fallback info (if used)
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
    
                # 7. Large dimension warning
                dims = response.get("elementDimensions", {})
                if dims.get("width", 0) > 10000 or dims.get("height", 0) > 10000:
                    click.echo(icons.info(
                        f"Large element captured: {dims.get('width')}×{dims.get('height')}. "
                        "Chrome has a maximum dimension limit of 16384"
                    ))
    
            # Decode image data
            from inspekt.services.screenshot_utils import decode_data_url
    
            try:
                image_data = decode_data_url(response.get("dataUrl"))
            except ValueError as e:
                if json_output:
                    click.echo(json.dumps({"ok": False, "error": str(e)}))
                else:
                    click.echo(f"Error: {e}", err=True)
                sys.exit(1)
    
        # Handle clipboard mode (no file saved)
        if clipboard:
            from inspekt.app.cli.icons import clipboard as clipboard_icon
            from inspekt.app.cli.util import copy_image_to_clipboard

            if copy_image_to_clipboard(image_data, format=format):
                click.echo(
                    clipboard_icon(f"Copied to clipboard ({response.get('width')}×{response.get('height')}px, {format_filesize(len(image_data))})")
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

            # Process in temp file, then move to output when done
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Track dimensions and sizes
            final_width = response.get("width")
            final_height = response.get("height")
            original_file_size = len(image_data)
            final_size = original_file_size
            resized = False
            metadata_added = False

            # Create temp file with same extension
            suffix = output_path.suffix or ".png"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = Path(tmp.name)
                tmp.write(image_data)

            try:
                # Show "Received from Chrome" message
                if not quiet and not json_output:
                    click.echo(icons.chrome_received(f"Received from Chrome: {final_width}×{final_height} ({format_filesize(original_file_size)})"))

                # Resize if max_width specified and image is wider
                if max_width and final_width and final_width > max_width:
                    try:
                        import warnings
                        from PIL import Image

                        # Configure Pillow for large screenshots
                        Image.MAX_IMAGE_PIXELS = 300_000_000
                        warnings.filterwarnings("ignore", category=Image.DecompressionBombWarning)

                        with Image.open(tmp_path) as img:
                            ratio = max_width / img.width
                            new_height = int(img.height * ratio)
                            resized_img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                            save_kwargs = {}
                            if format == "png":
                                save_kwargs["optimize"] = False
                            elif format in ("jpg", "jpeg", "webp"):
                                save_kwargs["quality"] = int(quality * 100) if quality else 92

                            resized_img.save(tmp_path, **save_kwargs)
                            final_width = max_width
                            final_height = new_height
                            resized = True

                            if not quiet and not json_output:
                                click.echo(icons.info(f"Resized: {response.get('width')}x{response.get('height')}px → {max_width}x{new_height}px"))

                    except ImportError:
                        if not quiet and not json_output:
                            click.echo("Note: --max-width requires Pillow. Install with: pip install Pillow", err=True)

                # Embed metadata (before optimization)
                if metadata and format in ("png", "jpg", "jpeg"):
                    try:
                        from inspekt.services.image_metadata import add_metadata, create_metadata

                        if not quiet and not json_output:
                            click.echo(icons.metadata("Adding metadata and re-encoding…"))

                        compression_ratio = None
                        current_size = tmp_path.stat().st_size
                        if len(image_data) > 0 and current_size > 0:
                            compression_ratio = (1 - (current_size / len(image_data))) * 100

                        meta = create_metadata(
                            source_url=response.get("url"),
                            target="element",
                            selector=selector,
                            element_tag=response.get("tagName"),
                            dpr=scale or 2,
                            redacted=redacted_count > 0,
                            original_width=response.get("width"),
                            original_height=response.get("height"),
                            file_size=current_size,
                            compression_ratio=compression_ratio,
                            page_title=response.get("pageTitle"),
                            page_language=response.get("pageLanguage"),
                            prefers_color_scheme=response.get("prefersColorScheme"),
                            prefers_contrast=response.get("prefersContrast"),
                            prefers_reduced_motion=response.get("prefersReducedMotion"),
                            prefers_reduced_transparency=response.get("prefersReducedTransparency"),
                            forced_colors=response.get("forcedColors"),
                            browser_version=response.get("browserVersion"),
                            user_agent=response.get("userAgent"),
                            window_width=response.get("windowWidth"),
                            window_height=response.get("windowHeight"),
                            viewport_width=response.get("viewportWidth"),
                            viewport_height=response.get("viewportHeight"),
                        )

                        add_metadata(tmp_path, meta)
                        metadata_added = True

                    except Exception as e:
                        if not quiet and not json_output:
                            click.echo(f"Warning: Could not add metadata: {e}", err=True)

                # Optimize with oxipng (size-aware)
                compression_applied = False
                compression_skipped = False
                if compression != "disabled" and format == "png":
                    from inspekt.services.image_optimizer import optimize_png
                    from inspekt.services.screenshot_processor import SIZE_1MB, SIZE_2MB, SIZE_5MB

                    file_size = tmp_path.stat().st_size

                    # Handle auto mode with size thresholds
                    if compression == "auto" and file_size > SIZE_5MB:
                        # Skip compression for very large files
                        if not quiet and not json_output:
                            click.echo(icons.optimizing(
                                "Skipping lossless compression for files larger than 5 MB "
                                "(force with --enable-compression)…"
                            ))
                        compression_skipped = True
                    else:
                        # Determine appropriate message based on file size
                        if file_size > SIZE_2MB:
                            message = "Applying lossless compression (slow for larger files; disable with --disable-compression)…"
                        elif file_size > SIZE_1MB:
                            message = "Applying lossless compression (may take a moment)…"
                        else:
                            message = "Applying lossless compression…"

                        if not quiet and not json_output:
                            click.echo(icons.optimizing(message))

                        try:
                            optimized_size = optimize_png(tmp_path)
                            if optimized_size:
                                final_size = optimized_size
                                compression_applied = True
                        except Exception as e:
                            if not quiet and not json_output:
                                click.echo(f"Optimization failed: {e}", err=True)

                # Move temp file to final output
                shutil.move(str(tmp_path), str(output_path))
                final_size = output_path.stat().st_size

                # Display save message
                if not quiet and not json_output:
                    filename_display = output_path.name
                    if auto_generated:
                        click.echo(icons.save(f"Screenshot saved: {filename_display} (filename auto-generated)"))
                    else:
                        click.echo(icons.save(f"Screenshot saved: {filename_display}"))

                    # Show optimization summary (indented)
                    if compression_applied and original_file_size > 0:
                        reduction = ((original_file_size - final_size) / original_file_size) * 100
                        click.echo(icons.optimized_summary(f"Optimized: {format_filesize(original_file_size)} → {format_filesize(final_size)} ({reduction:.1f}% decrease)"))

                    # Display source URL (indented)
                    url = response.get("url", "")
                    if url:
                        click.echo(icons.source_url(f"Source: {url}"))

            finally:
                # Clean up temp file if it still exists
                if tmp_path.exists():
                    tmp_path.unlink()

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
                    "optimized": compression_applied,
                    "compression_skipped": compression_skipped,
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
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.open_file(output_path)

            # Reveal in file explorer if requested
            if reveal_after:
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.reveal_file(output_path)

            # Display contextual hints (unless quiet or json mode)
            if not quiet and not json_output:
                from inspekt.app.cli.table import print_hint

                # Hint about opt-out flags if zoom/selection was reset
                zoom_reset = response.get("zoomWasReset")
                selection_cleared = response.get("selectionCleared")
                if zoom_reset and selection_cleared:
                    print_hint("Use `--keep-zoom` and `--keep-selection` to skip resetting zoom/selection.")
                elif zoom_reset:
                    print_hint("Use `--keep-zoom` to capture at the current zoom level.")
                elif selection_cleared:
                    print_hint("Use `--keep-selection` to keep text selection visible in screenshot.")

                # Hint about larger browser window if CDP fallback or scroll was needed
                if response.get("usedCDPFallback") or response.get("scrolledIntoView"):
                    print_hint("Making the browser window larger may improve results for large elements.")

                # General customization hint
                print_hint("For redacting, quality, format, and scaling options, run `inspekt inspected screenshot --help`.")

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# Add screenshot as an alias under the 'inspected' command group
# This allows: inspekt inspected screenshot (same as: inspekt screenshot node)
inspected.add_command(screenshot_node, name="screenshot")


# Create focused screenshot command - uses shared decorator and forwards all options
@focused.command(name="screenshot")
@screenshot_element_options
@click.pass_context
def screenshot_focused(ctx, **kwargs):
    """
    Capture a screenshot of the currently focused element.

    Takes a screenshot of the element that currently has keyboard focus
    (document.activeElement). Useful for testing focus states and keyboard navigation.

    All options from `inspekt screenshot node` are available.

    Examples:
        # Capture the focused element
        inspekt focused screenshot -o focused.png

        # Tab to a button, then capture it
        inspekt focused screenshot --margin 20 --open

        # Capture with forced :hover state
        inspekt focused screenshot --state hover --compare -o button_states.png

    See also:
        inspekt inspected screenshot  - Capture DevTools inspected element
        inspekt screenshot node       - Capture any element by selector
    """
    # Invoke screenshot_node with selector='focused' and forward all other options
    ctx.invoke(screenshot_node, selector='focused', **kwargs)


@focused.command("describe")
@click.option(
    "--language", "--lang", type=str, default=None, help="Language for AI output (overrides config)"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--debug", is_flag=True, help="Show detailed debug output (prompts, API calls, image processing)")
def focused_describe(language, output_json, debug):
    """
    Generate an AI-powered accessibility description of the focused element.

    Uses vision AI to analyze a screenshot of the keyboard-focused element
    along with its metadata to provide a concise, accessibility-focused description.

    The description focuses on:
    - What the element is and its purpose
    - Accessible name and how it's computed
    - Keyboard accessibility
    - Visual accessibility (contrast, focus indicators)
    - Potential accessibility issues

    Examples:
        inspekt focused describe
        inspekt focused describe --language nl
        inspekt focused describe --json
    """
    import asyncio
    from inspekt.core.handlers.ai import element_describe
    from inspekt.core.schemas.ai import ElementDescribeParams
    from inspekt.app.cli.icons import analyze as analyze_icon

    if not output_json:
        click.echo(analyze_icon("Analyzing focused element with AI…"), err=True)

    params = ElementDescribeParams(source="focused", language=language, debug=debug)
    result = asyncio.run(element_describe(params))

    if output_json:
        click.echo(json.dumps({
            "description": result.description,
            "element_type": result.element_type,
            "accessible_name": result.accessible_name,
            "source": result.source,
        }, indent=2))
    else:
        if result.description.startswith("Error:"):
            click.echo(result.description, err=True)
            sys.exit(1)

        click.echo()
        click.echo(result.description)
        click.echo()


@focused.command("ask")
@click.argument("question", type=str)
@click.option(
    "--language", "--lang", type=str, default=None, help="Language for AI output (overrides config)"
)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--debug", is_flag=True, help="Show detailed debug output (prompts, API calls, image processing)")
def focused_ask(question, language, output_json, debug):
    """
    Ask a question about the focused element using AI.

    Uses vision AI to analyze a screenshot of the keyboard-focused element
    along with its metadata to answer questions about accessibility, design,
    or functionality.

    Examples:
        inspekt focused ask "Is this accessible?"
        inspekt focused ask "Is the focus indicator visible?"
        inspekt focused ask "How would a screen reader announce this?"
        inspekt focused ask "What WCAG issues does this have?"
    """
    import asyncio
    from inspekt.core.handlers.ai import element_ask
    from inspekt.core.schemas.ai import ElementAskParams
    from inspekt.app.cli.icons import analyze as analyze_icon

    if not output_json:
        click.echo(analyze_icon("Analyzing focused element with AI…"), err=True)

    params = ElementAskParams(question=question, source="focused", language=language, debug=debug)
    result = asyncio.run(element_ask(params))

    if output_json:
        click.echo(json.dumps({
            "question": question,
            "answer": result.answer,
            "element_type": result.element_type,
            "source": result.source,
        }, indent=2))
    else:
        if result.answer.startswith("Error:"):
            click.echo(result.answer, err=True)
            sys.exit(1)

        click.echo()
        click.echo(result.answer)
        click.echo()


@screenshot.command(name="viewport")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (required unless --clipboard)")
@click.option(
    "--margin",
    "-m",
    type=int,
    default=None,
    help="Margin in pixels around screenshot",
)
@click.option(
    "--margin-color",
    "-c",
    default=None,
    help="Margin color: 'auto' (sample first pixel), hex code, or color name",
)
@click.option(
    "--disable-compression",
    is_flag=True,
    default=False,
    help="Skip lossless PNG compression entirely",
)
@click.option(
    "--enable-compression",
    is_flag=True,
    default=False,
    help="Force lossless compression even for files larger than 5 MB",
)
@click.option(
    "--scale",
    type=click.IntRange(1, 4),
    default=None,
    help="Scale factor 1-4 for high-DPI screenshots",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default=None,
    help="Output format (png, jpg, webp)",
)
@click.option(
    "--quality",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Quality for lossy formats (0.0-1.0)",
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
@click.option(
    "--keep-zoom",
    is_flag=True,
    default=False,
    help="Don't reset zoom to 100% before capture",
)
@click.option(
    "--keep-selection",
    is_flag=True,
    default=False,
    help="Don't clear text selection before capture",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress all output except errors",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output result as JSON",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing files without prompting",
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
def screenshot_viewport(output, margin, margin_color, disable_compression, enable_compression, scale, format, quality, open_after, reveal_after, clipboard, metadata, keep_zoom, keep_selection, quiet, json_output, force, redact, redact_style, redact_selectors):
    """
    Capture a screenshot of the visible viewport.

    Captures exactly what's visible in the browser window.
    If no output path is specified, a filename is auto-generated.
    Sensitive data (passwords, credit cards, etc.) is automatically redacted.

    Examples:
        inspekt screenshot viewport -o viewport.png
        inspekt screenshot viewport -o view.png --margin 10
        inspekt screenshot viewport --clipboard
        inspekt screenshot viewport --json -o out.png
        inspekt screenshot viewport  # auto-generated filename
        inspekt screenshot viewport --no-redact  # disable redaction
    """
    from inspekt.config import get_screenshot_config
    from inspekt.services.screenshot_utils import (
        decode_data_url,
        validate_screenshot_options,
        display_adjustment_feedback,
        display_capture_feedback,
        display_restoration_feedback,
        get_screenshot_output_path,
    )

    # Load config and apply defaults
    config = get_screenshot_config()
    if margin is None:
        margin = config["margin"]
    if margin_color is None:
        margin_color = config["margin-color"]
    if scale is None:
        scale = config.get("scale", 2)
    if format is None:
        format = config["format"]
    if quality is None:
        quality = config["quality"]

    # Determine compression mode from flags
    if disable_compression:
        compression = "disabled"
    elif enable_compression:
        compression = "enabled"
    else:
        compression = "auto"

    # Validate options (allow auto-generated filename)
    validate_screenshot_options(clipboard, open_after, reveal_after, json_output, output, allow_auto_filename=True)

    # Note if both --open and --reveal are used
    if open_after and reveal_after and not quiet and not json_output:
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
        "keepZoom": keep_zoom,
        "keepSelection": keep_selection,
    }

    code = script.replace("'MODE_PLACEHOLDER'", json.dumps("viewport"))
    code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options))

    # Initialize redaction tracking
    redacted_count = 0
    masked_emails_count = 0
    redacted_elements = []
    redact_script = None

    try:
        from inspekt.app.cli import icons

        # Apply redaction before capture
        if redact:
            try:
                redact_script = loader.load_script_sync("screenshot_redact.js")
                redact_options = {
                    "action": "apply",
                    "style": redact_style.lower(),
                    "includePatterns": True,
                    # No rootSelector - applies to entire visible page
                }
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

                        # Display feedback
                        if not quiet and not json_output:
                            messages = []
                            if redacted_count > 0:
                                style_desc = {"blur": "blur", "bar": "bar"}.get(redact_style.lower(), "bar")
                                messages.append(f"{redacted_count} element(s) with {style_desc}")
                            if masked_emails_count > 0:
                                messages.append(f"{masked_emails_count} email(s) masked")
                            if messages:
                                click.echo(click.style("\uedaa  ", fg="blue") + f"Redacting: {', '.join(messages)}…")

            except FileNotFoundError:
                if not quiet and not json_output:
                    click.echo("Warning: Redaction script not found", err=True)
            except Exception as e:
                if not quiet and not json_output:
                    click.echo(f"Warning: Redaction failed: {e}", err=True)

        result = executor.execute(code, timeout=60.0)

        # Restore redacted elements after capture
        if redact and redact_script and redacted_count > 0:
            try:
                restore_options = {"action": "restore"}
                restore_code = redact_script.replace("OPTIONS_PLACEHOLDER", json.dumps(restore_options))
                executor.execute(restore_code, timeout=10.0)
            except Exception:
                pass  # Silently ignore restore failures - screenshot already captured

        if not result.get("ok"):
            if json_output:
                click.echo(json.dumps({"ok": False, "error": result.get("error")}))
            else:
                click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if not response.get("ok"):
            if json_output:
                click.echo(json.dumps({"ok": False, "error": response.get("error")}))
            else:
                click.echo(f"Error: {response.get('error')}", err=True)
            sys.exit(1)

        # Display adjustment feedback
        display_adjustment_feedback(response, quiet, json_output)

        # Display capture feedback
        display_capture_feedback("viewport", quiet=quiet, json_output=json_output)

        # Restoration message
        display_restoration_feedback(response, quiet, json_output)

        # Decode image data
        try:
            image_data = decode_data_url(response.get("dataUrl"))
        except ValueError as e:
            if json_output:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Handle clipboard mode (no file saved)
        if clipboard:
            from inspekt.app.cli.icons import clipboard as clipboard_icon
            from inspekt.app.cli.util import copy_image_to_clipboard

            if copy_image_to_clipboard(image_data, format=format):
                if json_output:
                    click.echo(json.dumps({
                        "ok": True,
                        "clipboard": True,
                        "width": response.get("width"),
                        "height": response.get("height"),
                        "size_bytes": len(image_data),
                        "url": response.get("url"),
                    }))
                elif not quiet:
                    click.echo(clipboard_icon(f"Copied to clipboard ({format_filesize(len(image_data))})"))
            else:
                if json_output:
                    click.echo(json.dumps({"ok": False, "error": "Failed to copy to clipboard"}))
                else:
                    click.echo("Failed to copy to clipboard", err=True)
                sys.exit(1)
        else:
            # Get output path (auto-generate if not specified)
            output_path, auto_generated = get_screenshot_output_path(
                output,
                mode="viewport",
                page_title=response.get("pageTitle"),
                format=format,
            )

            # Check if file exists and handle overwrite
            if output_path.exists() and not force:
                if json_output:
                    click.echo(json.dumps({"ok": False, "error": f"File already exists: {output_path}"}))
                    sys.exit(1)
                click.echo(f"File already exists: {output_path}", err=True)
                if not click.confirm("Overwrite?"):
                    sys.exit(0)

            # Use ScreenshotProcessor for file operations
            from inspekt.services.screenshot_processor import ScreenshotProcessor

            processor = ScreenshotProcessor(
                output_path=output_path,
                format=format,
                compression=compression,
                metadata=metadata,
                quiet=quiet,
                json_output=json_output,
            )

            tmp_path = None
            try:
                # Save to temp file
                tmp_path = processor.save_to_temp(
                    image_data,
                    width=response.get("width"),
                    height=response.get("height"),
                )

                # Add metadata
                processor.add_metadata(
                    tmp_path,
                    source_url=response.get("url"),
                    target="viewport",
                    dpr=scale or 2,
                    original_width=response.get("width"),
                    original_height=response.get("height"),
                    page_title=response.get("pageTitle"),
                    page_language=response.get("pageLanguage"),
                    prefers_color_scheme=response.get("prefersColorScheme"),
                    prefers_contrast=response.get("prefersContrast"),
                    prefers_reduced_motion=response.get("prefersReducedMotion"),
                    prefers_reduced_transparency=response.get("prefersReducedTransparency"),
                    forced_colors=response.get("forcedColors"),
                    browser_version=response.get("browserVersion"),
                    user_agent=response.get("userAgent"),
                    window_width=response.get("windowWidth"),
                    window_height=response.get("windowHeight"),
                    viewport_width=response.get("viewportWidth"),
                    viewport_height=response.get("viewportHeight"),
                )

                # Optimize PNG
                processor.optimize_png(tmp_path)

                # Finalize (move to output)
                processor.finalize(tmp_path, auto_generated=auto_generated)

                # Display source URL
                processor.display_source_url(response.get("url"))

                # JSON output
                if json_output:
                    result_json = {
                        "ok": True,
                        "path": str(output_path.absolute()),
                        "filename": output_path.name,
                        "auto_generated": auto_generated,
                        "width": response.get("width"),
                        "height": response.get("height"),
                        "original_width": response.get("width"),
                        "original_height": response.get("height"),
                        "size_bytes": processor.final_size,
                        "original_size_bytes": processor.original_size,
                        "resized": False,
                        "optimized": processor.optimized,
                        "compression_skipped": processor.compression_skipped,
                        "metadata_embedded": processor.metadata_added,
                        "redacted": redact,
                        "redacted_style": redact_style.lower() if redact else None,
                        "redacted_count": redacted_count,
                        "masked_emails_count": masked_emails_count if redact else 0,
                        "redacted_elements": redacted_elements if redact else [],
                        "url": response.get("url"),
                        "method": response.get("apiUsed"),
                    }
                    click.echo(json.dumps(result_json))

            finally:
                processor.cleanup(tmp_path)

            # Open in default application if requested
            if open_after:
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.open_file(output_path)

            # Reveal in file explorer if requested
            if reveal_after:
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.reveal_file(output_path)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if json_output:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screenshot.command(name="page")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (required unless --clipboard)")
@click.option(
    "--margin",
    "-m",
    type=int,
    default=None,
    help="Margin in pixels around screenshot (default: 0)",
)
@click.option(
    "--margin-color",
    "-c",
    default=None,
    help="Margin color: 'auto' (sample first pixel), hex code, or color name (default: auto)",
)
@click.option(
    "--disable-compression",
    is_flag=True,
    default=False,
    help="Skip lossless PNG compression entirely",
)
@click.option(
    "--enable-compression",
    is_flag=True,
    default=False,
    help="Force lossless compression even for files larger than 5 MB",
)
@click.option(
    "--scale",
    type=click.IntRange(1, 4),
    default=None,
    help="Scale factor 1-4 (default: 1)",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default=None,
    help="Output format (default: png)",
)
@click.option(
    "--quality",
    type=click.FloatRange(0.0, 1.0),
    default=None,
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
@click.option(
    "--keep-zoom",
    is_flag=True,
    default=False,
    help="Don't reset zoom to 100% before capture",
)
@click.option(
    "--keep-selection",
    is_flag=True,
    default=False,
    help="Don't clear text selection before capture",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress all output except errors",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output result as JSON (implies --quiet for progress messages)",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite output file without prompting",
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
def screenshot_page(output, margin, margin_color, disable_compression, enable_compression, scale, format, quality, max_height, open_after, reveal_after, clipboard, metadata, keep_zoom, keep_selection, quiet, json_output, force, redact, redact_style, redact_selectors):
    """
    Capture a screenshot of the entire page (full height).

    Uses Chrome DevTools Protocol for single-shot full page capture.
    Note: Chrome has a maximum height limit of 16384 pixels.
    If no output path is specified, a filename is auto-generated.
    Sensitive data (passwords, credit cards, etc.) is automatically redacted.

    WARNING: A debugger notification banner will appear briefly during capture.
    This is a Chrome security feature and cannot be disabled.

    Examples:
        inspekt screenshot page -o fullpage.png
        inspekt screenshot page -o page.png --scale 2
        inspekt screenshot page -o page.jpg --format jpg --quality 0.85
        inspekt screenshot page --clipboard
        inspekt screenshot page --json -o out.png
        inspekt screenshot page --no-redact  # disable redaction
        inspekt screenshot page  # auto-generated filename
    """
    from inspekt.config import get_screenshot_config
    from inspekt.services.screenshot_utils import (
        decode_data_url,
        validate_screenshot_options,
        display_adjustment_feedback,
        display_capture_feedback,
        display_restoration_feedback,
        get_screenshot_output_path,
    )

    # Load config and apply defaults
    config = get_screenshot_config()
    if margin is None:
        margin = config["margin"]
    if margin_color is None:
        margin_color = config["margin-color"]
    if scale is None:
        scale = config.get("scale", 1)  # Default 1 for page (full resolution)
    if format is None:
        format = config["format"]
    if quality is None:
        quality = config["quality"]

    # Determine compression mode from flags
    if disable_compression:
        compression = "disabled"
    elif enable_compression:
        compression = "enabled"
    else:
        compression = "auto"

    # Validate options (allow auto-generated filename)
    validate_screenshot_options(clipboard, open_after, reveal_after, json_output, output, allow_auto_filename=True)

    # Note if both --open and --reveal are used
    if open_after and reveal_after and not quiet and not json_output:
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
        "keepZoom": keep_zoom,
        "keepSelection": keep_selection,
    }

    code = script.replace("'MODE_PLACEHOLDER'", json.dumps("page"))
    code = code.replace("OPTIONS_PLACEHOLDER", json.dumps(options))

    # Initialize redaction tracking
    redacted_count = 0
    masked_emails_count = 0
    redacted_elements = []
    redact_script = None

    try:
        from inspekt.app.cli import icons

        # Apply redaction before capture
        if redact:
            try:
                redact_script = loader.load_script_sync("screenshot_redact.js")
                redact_options = {
                    "action": "apply",
                    "style": redact_style.lower(),
                    "includePatterns": True,
                    # No rootSelector - applies to entire page
                }
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

                        # Display feedback
                        if not quiet and not json_output:
                            messages = []
                            if redacted_count > 0:
                                style_desc = {"blur": "blur", "bar": "bar"}.get(redact_style.lower(), "bar")
                                messages.append(f"{redacted_count} element(s) with {style_desc}")
                            if masked_emails_count > 0:
                                messages.append(f"{masked_emails_count} email(s) masked")
                            if messages:
                                click.echo(click.style("\uedaa  ", fg="blue") + f"Redacting: {', '.join(messages)}…")

            except FileNotFoundError:
                if not quiet and not json_output:
                    click.echo("Warning: Redaction script not found", err=True)
            except Exception as e:
                if not quiet and not json_output:
                    click.echo(f"Warning: Redaction failed: {e}", err=True)

        result = executor.execute(code, timeout=120.0)  # Longer timeout for full page

        # Restore redacted elements after capture
        if redact and redact_script and redacted_count > 0:
            try:
                restore_options = {"action": "restore"}
                restore_code = redact_script.replace("OPTIONS_PLACEHOLDER", json.dumps(restore_options))
                executor.execute(restore_code, timeout=10.0)
            except Exception:
                pass  # Silently ignore restore failures - screenshot already captured

        if not result.get("ok"):
            if json_output:
                click.echo(json.dumps({"ok": False, "error": result.get("error")}))
            else:
                click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})
        if not response.get("ok"):
            if json_output:
                click.echo(json.dumps({"ok": False, "error": response.get("error")}))
            else:
                click.echo(f"Error: {response.get('error')}", err=True)
            sys.exit(1)

        # Display adjustment feedback
        display_adjustment_feedback(response, quiet, json_output)

        # Display capture feedback
        display_capture_feedback("page", quiet=quiet, json_output=json_output)

        # Restoration message
        display_restoration_feedback(response, quiet, json_output)

        # Check for truncation warning
        if response.get("truncated") and not quiet and not json_output:
            click.echo(
                f"Warning: Page was truncated from {response.get('fullHeight')}px to {response.get('height')}px",
                err=True,
            )

        # Decode image data
        try:
            image_data = decode_data_url(response.get("dataUrl"))
        except ValueError as e:
            if json_output:
                click.echo(json.dumps({"ok": False, "error": str(e)}))
            else:
                click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Handle clipboard mode (no file saved)
        if clipboard:
            from inspekt.app.cli.icons import clipboard as clipboard_icon
            from inspekt.app.cli.util import copy_image_to_clipboard

            if copy_image_to_clipboard(image_data, format=format):
                if json_output:
                    click.echo(json.dumps({
                        "ok": True,
                        "clipboard": True,
                        "width": response.get("width"),
                        "height": response.get("height"),
                        "size_bytes": len(image_data),
                        "url": response.get("url"),
                        "truncated": response.get("truncated", False),
                    }))
                elif not quiet:
                    click.echo(clipboard_icon(f"Copied to clipboard ({format_filesize(len(image_data))})"))
            else:
                if json_output:
                    click.echo(json.dumps({"ok": False, "error": "Failed to copy to clipboard"}))
                else:
                    click.echo("Failed to copy to clipboard", err=True)
                sys.exit(1)
        else:
            # Get output path (auto-generate if not specified)
            output_path, auto_generated = get_screenshot_output_path(
                output,
                mode="page",
                page_title=response.get("pageTitle"),
                format=format,
            )

            # Check if file exists and handle overwrite
            if output_path.exists() and not force:
                if json_output:
                    click.echo(json.dumps({"ok": False, "error": f"File already exists: {output_path}"}))
                    sys.exit(1)
                click.echo(f"File already exists: {output_path}", err=True)
                if not click.confirm("Overwrite?"):
                    sys.exit(0)

            # Use ScreenshotProcessor for file operations
            from inspekt.services.screenshot_processor import ScreenshotProcessor

            processor = ScreenshotProcessor(
                output_path=output_path,
                format=format,
                compression=compression,
                metadata=metadata,
                quiet=quiet,
                json_output=json_output,
            )

            tmp_path = None
            try:
                # Save to temp file
                tmp_path = processor.save_to_temp(
                    image_data,
                    width=response.get("width"),
                    height=response.get("height"),
                )

                # Add metadata
                processor.add_metadata(
                    tmp_path,
                    source_url=response.get("url"),
                    target="page",
                    dpr=scale or 1,
                    original_width=response.get("width"),
                    original_height=response.get("height"),
                    page_title=response.get("pageTitle"),
                    page_language=response.get("pageLanguage"),
                    prefers_color_scheme=response.get("prefersColorScheme"),
                    prefers_contrast=response.get("prefersContrast"),
                    prefers_reduced_motion=response.get("prefersReducedMotion"),
                    prefers_reduced_transparency=response.get("prefersReducedTransparency"),
                    forced_colors=response.get("forcedColors"),
                    browser_version=response.get("browserVersion"),
                    user_agent=response.get("userAgent"),
                    window_width=response.get("windowWidth"),
                    window_height=response.get("windowHeight"),
                    viewport_width=response.get("viewportWidth"),
                    viewport_height=response.get("viewportHeight"),
                )

                # Optimize PNG
                processor.optimize_png(tmp_path)

                # Finalize (move to output)
                processor.finalize(tmp_path, auto_generated=auto_generated)

                # Display source URL
                processor.display_source_url(response.get("url"))

                # JSON output
                if json_output:
                    result_json = {
                        "ok": True,
                        "path": str(output_path.absolute()),
                        "filename": output_path.name,
                        "auto_generated": auto_generated,
                        "width": response.get("width"),
                        "height": response.get("height"),
                        "original_width": response.get("width"),
                        "original_height": response.get("height"),
                        "size_bytes": processor.final_size,
                        "original_size_bytes": processor.original_size,
                        "resized": False,
                        "optimized": processor.optimized,
                        "compression_skipped": processor.compression_skipped,
                        "metadata_embedded": processor.metadata_added,
                        "redacted": redact,
                        "redacted_style": redact_style.lower() if redact else None,
                        "redacted_count": redacted_count,
                        "masked_emails_count": masked_emails_count if redact else 0,
                        "redacted_elements": redacted_elements if redact else [],
                        "truncated": response.get("truncated", False),
                        "url": response.get("url"),
                        "method": response.get("apiUsed"),
                    }
                    click.echo(json.dumps(result_json))

            finally:
                processor.cleanup(tmp_path)

            # Open in default application if requested
            if open_after:
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.open_file(output_path)

            # Reveal in file explorer if requested
            if reveal_after:
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.reveal_file(output_path)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        if json_output:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screenshot.command(name="selection")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file path (auto-generated if not specified)")
@click.option(
    "--margin",
    "-m",
    type=int,
    default=None,
    help="Margin in pixels around screenshot",
)
@click.option(
    "--margin-color",
    "-c",
    default=None,
    help="Margin color: 'auto' (sample first pixel), hex code, or color name",
)
@click.option(
    "--disable-compression",
    is_flag=True,
    default=False,
    help="Skip lossless PNG compression entirely",
)
@click.option(
    "--enable-compression",
    is_flag=True,
    default=False,
    help="Force lossless compression even for files larger than 5 MB",
)
@click.option(
    "--scale",
    type=click.IntRange(1, 4),
    default=None,
    help="Scale factor 1-4 for high-DPI screenshots",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default=None,
    help="Output format (png, jpg, webp)",
)
@click.option(
    "--quality",
    type=click.FloatRange(0.0, 1.0),
    default=None,
    help="Quality for lossy formats (0.0-1.0)",
)
@click.option(
    "--snap-tolerance",
    type=click.FloatRange(0.0, 1.0),
    default=0.25,
    help="Tolerance for snapping to elements (0.0-1.0, default: 0.25)",
)
@click.option(
    "--no-snap",
    is_flag=True,
    default=False,
    help="Disable element snapping, use raw selection",
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
@click.option(
    "--keep-zoom",
    is_flag=True,
    default=False,
    help="Don't reset zoom to 100% before capture",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress all output except errors",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output result as JSON",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing files without prompting",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Show debug visualization of snap calculation",
)
def screenshot_selection(
    output,
    margin,
    margin_color,
    disable_compression,
    enable_compression,
    scale,
    format,
    quality,
    snap_tolerance,
    no_snap,
    open_after,
    reveal_after,
    clipboard,
    metadata,
    keep_zoom,
    quiet,
    json_output,
    force,
    debug,
):
    """
    Capture a screenshot of a manually selected region.

    Interactively drag to select a region on the page. The selection will
    automatically snap to the combined bounding box of overlapping DOM elements
    if within the tolerance threshold (25% by default).

    Press Enter or click to confirm the selection. Press Escape to cancel.

    Examples:
        inspekt screenshot selection
        inspekt screenshot selection -o region.png
        inspekt screenshot selection --no-snap
        inspekt screenshot selection --snap-tolerance 0.5
        inspekt screenshot selection --clipboard
    """
    import signal
    import time

    from inspekt.app.cli.icons import crosshair as crosshair_icon, snap as snap_icon, info as info_icon, camera as camera_icon, clipboard as clipboard_icon
    from inspekt.config import get_screenshot_config
    from inspekt.services.screenshot_utils import (
        decode_data_url,
        get_screenshot_output_path,
    )

    # Load config and apply defaults
    config = get_screenshot_config()
    if margin is None:
        margin = config["margin"]
    if margin_color is None:
        margin_color = config["margin-color"]
    if scale is None:
        scale = config.get("scale", 2)
    if format is None:
        format = config["format"]
    if quality is None:
        quality = config["quality"]

    # Determine compression mode
    if disable_compression:
        compression = "disabled"
    elif enable_compression:
        compression = "enabled"
    else:
        compression = "auto"

    executor = get_executor()
    loader = ScriptLoader()

    executor.ensure_server_running()

    # Load selection script
    try:
        script_template = loader.load_script_sync("screenshot_selection.js")
    except FileNotFoundError as e:
        if json_output:
            click.echo(json.dumps({"ok": False, "error": f"Selection script not found: {e}"}))
        else:
            click.echo(f"Error: Selection script not found: {e}", err=True)
        sys.exit(1)

    # Build options for JS
    selection_options = {
        "snapTolerance": 0 if no_snap else snap_tolerance,
        "debug": debug,
    }

    # Prepare start code
    start_code = script_template.replace("'ACTION_PLACEHOLDER'", json.dumps("start"))
    start_code = start_code.replace("OPTIONS_PLACEHOLDER", json.dumps(selection_options))

    # Prepare poll code
    poll_code = script_template.replace("'ACTION_PLACEHOLDER'", json.dumps("poll"))
    poll_code = poll_code.replace("OPTIONS_PLACEHOLDER", json.dumps(selection_options))

    # Prepare stop code (for cleanup on Ctrl+C)
    stop_code = script_template.replace("'ACTION_PLACEHOLDER'", json.dumps("stop"))
    stop_code = stop_code.replace("OPTIONS_PLACEHOLDER", json.dumps(selection_options))

    try:
        # Start selection mode
        if not quiet and not json_output:
            click.echo(crosshair_icon("Starting selection mode…"))
            click.echo("  Drag to select a region. Press Enter or click to confirm, Escape to cancel.")

        start_result = executor.execute(start_code, timeout=10.0)
        if not start_result.get("ok"):
            error_msg = start_result.get("error", "Failed to start selection mode")
            if json_output:
                click.echo(json.dumps({"ok": False, "error": error_msg}))
            else:
                click.echo(f"Error: {error_msg}", err=True)
            sys.exit(1)

        # Handle Ctrl+C gracefully
        stop_requested = False

        def handle_sigint(sig, frame):
            nonlocal stop_requested
            stop_requested = True

        original_sigint = signal.signal(signal.SIGINT, handle_sigint)

        selection_result = None
        try:
            # Poll loop - wait for confirmation or cancellation
            while True:
                if stop_requested:
                    executor.execute(stop_code, timeout=5.0)
                    if not quiet and not json_output:
                        click.echo("\nSelection cancelled.")
                    sys.exit(0)

                time.sleep(0.1)  # 100ms poll interval

                poll_result = executor.execute(poll_code, timeout=5.0)
                if not poll_result.get("ok"):
                    continue

                response = poll_result.get("result", poll_result)

                if response.get("cancelled"):
                    if json_output:
                        click.echo(json.dumps({"ok": False, "cancelled": True}))
                    elif not quiet:
                        click.echo("Selection cancelled by user.")
                    sys.exit(0)

                if response.get("confirmed"):
                    selection_result = response
                    break

                # Still waiting for selection
                if not response.get("selectionActive"):
                    # Selection was somehow cancelled
                    sys.exit(0)

        finally:
            signal.signal(signal.SIGINT, original_sigint)

        if not selection_result:
            if json_output:
                click.echo(json.dumps({"ok": False, "error": "No selection made"}))
            else:
                click.echo("Error: No selection made", err=True)
            sys.exit(1)

        # Extract clip coordinates
        clip = selection_result.get("clip")
        snapped = selection_result.get("snapped", False)
        element_count = selection_result.get("elementCount", 0)

        if not clip:
            if json_output:
                click.echo(json.dumps({"ok": False, "error": "No clip coordinates returned"}))
            else:
                click.echo("Error: No clip coordinates returned", err=True)
            sys.exit(1)

        if not quiet and not json_output:
            if snapped:
                click.echo(snap_icon(f"Snapped to {element_count} element{'s' if element_count != 1 else ''}"))
            elif element_count > 0:
                click.echo(info_icon("Selection not snapped (expansion exceeded tolerance)"))

            width = int(clip.get("width", 0))
            height = int(clip.get("height", 0))
            click.echo(camera_icon(f"Capturing selection: {width}x{height}px"))

        # Load the unified screenshot script for capture
        screenshot_script = loader.load_script_sync("screenshot_unified.js")

        # Build screenshot options with clip region
        screenshot_options = {
            "clip": selection_result.get("absoluteClip") or clip,
            "margin": margin,
            "marginColor": margin_color,
            "scale": scale,
            "format": format,
            "quality": quality,
            "keepZoom": keep_zoom,
        }

        # Use selection mode with clip
        screenshot_code = screenshot_script.replace("'MODE_PLACEHOLDER'", json.dumps("selection"))
        screenshot_code = screenshot_code.replace("OPTIONS_PLACEHOLDER", json.dumps(screenshot_options))

        # Execute screenshot capture
        screenshot_result = executor.execute(screenshot_code, timeout=60.0)

        if not screenshot_result.get("ok"):
            error_msg = screenshot_result.get("error", "Screenshot capture failed")
            if json_output:
                click.echo(json.dumps({"ok": False, "error": error_msg}))
            else:
                click.echo(f"Error: {error_msg}", err=True)
            sys.exit(1)

        response = screenshot_result.get("result", screenshot_result)
        if not response.get("ok"):
            error_msg = response.get("error", "Screenshot capture failed")
            if json_output:
                click.echo(json.dumps({"ok": False, "error": error_msg}))
            else:
                click.echo(f"Error: {error_msg}", err=True)
            sys.exit(1)

        # Decode image data
        data_url = response.get("dataUrl")
        if not data_url:
            if json_output:
                click.echo(json.dumps({"ok": False, "error": "No image data returned"}))
            else:
                click.echo("Error: No image data returned", err=True)
            sys.exit(1)

        image_data = decode_data_url(data_url)

        # Handle clipboard output
        if clipboard:
            from inspekt.services.screenshot_utils import copy_image_to_clipboard
            success = copy_image_to_clipboard(image_data, format)
            if success:
                if json_output:
                    click.echo(json.dumps({
                        "ok": True,
                        "clipboard": True,
                        "width": response.get("width"),
                        "height": response.get("height"),
                        "snapped": snapped,
                        "element_count": element_count,
                    }))
                elif not quiet:
                    from inspekt.services.formatting_utils import format_filesize
                    click.echo(clipboard_icon(f"Copied to clipboard ({format_filesize(len(image_data))})"))
            else:
                if json_output:
                    click.echo(json.dumps({"ok": False, "error": "Failed to copy to clipboard"}))
                else:
                    click.echo("Failed to copy to clipboard", err=True)
                sys.exit(1)
        else:
            # Get output path (auto-generate if not specified)
            output_path, auto_generated = get_screenshot_output_path(
                output,
                mode="selection",
                page_title=response.get("pageTitle"),
                format=format,
            )

            # Check if file exists and handle overwrite
            if output_path.exists() and not force:
                if json_output:
                    click.echo(json.dumps({"ok": False, "error": f"File already exists: {output_path}"}))
                    sys.exit(1)
                click.echo(f"File already exists: {output_path}", err=True)
                if not click.confirm("Overwrite?"):
                    sys.exit(0)

            # Use ScreenshotProcessor for file operations
            from inspekt.services.screenshot_processor import ScreenshotProcessor

            processor = ScreenshotProcessor(
                output_path=output_path,
                format=format,
                compression=compression,
                metadata=metadata,
                quiet=quiet,
                json_output=json_output,
            )

            tmp_path = None
            try:
                # Save to temp file
                tmp_path = processor.save_to_temp(
                    image_data,
                    width=response.get("width"),
                    height=response.get("height"),
                )

                # Add metadata
                processor.add_metadata(
                    tmp_path,
                    source_url=response.get("url"),
                    target="selection",
                    dpr=scale or 1,
                    original_width=response.get("width"),
                    original_height=response.get("height"),
                    page_title=response.get("pageTitle"),
                    page_language=response.get("pageLanguage"),
                    prefers_color_scheme=response.get("prefersColorScheme"),
                    prefers_contrast=response.get("prefersContrast"),
                    prefers_reduced_motion=response.get("prefersReducedMotion"),
                    prefers_reduced_transparency=response.get("prefersReducedTransparency"),
                    forced_colors=response.get("forcedColors"),
                    browser_version=response.get("browserVersion"),
                    user_agent=response.get("userAgent"),
                    window_width=response.get("windowWidth"),
                    window_height=response.get("windowHeight"),
                    viewport_width=response.get("viewportWidth"),
                    viewport_height=response.get("viewportHeight"),
                )

                # Optimize PNG
                processor.optimize_png(tmp_path)

                # Finalize (move to output)
                processor.finalize(tmp_path, auto_generated=auto_generated)

                # Display source URL
                processor.display_source_url(response.get("url"))

                # JSON output
                if json_output:
                    result_json = {
                        "ok": True,
                        "path": str(output_path.absolute()),
                        "filename": output_path.name,
                        "auto_generated": auto_generated,
                        "width": response.get("width"),
                        "height": response.get("height"),
                        "size_bytes": processor.final_size,
                        "original_size_bytes": processor.original_size,
                        "optimized": processor.optimized,
                        "compression_skipped": processor.compression_skipped,
                        "metadata_embedded": processor.metadata_added,
                        "snapped": snapped,
                        "element_count": element_count,
                        "url": response.get("url"),
                    }
                    click.echo(json.dumps(result_json))

            finally:
                processor.cleanup(tmp_path)

            # Open in default application if requested
            if open_after:
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.open_file(output_path)

            # Reveal in file explorer if requested
            if reveal_after:
                from inspekt.app.cli.output import OutputHandler
                OutputHandler.reveal_file(output_path)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        # Cleanup on error
        try:
            executor.execute(stop_code, timeout=5.0)
        except Exception:
            pass
        if json_output:
            click.echo(json.dumps({"ok": False, "error": str(e)}))
        else:
            click.echo(f"Error: {e}", err=True)
        sys.exit(1)