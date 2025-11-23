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
        zen inspect "h1"              # Select and show details
        zen inspect "#header"
        zen inspect ".main-content"
        zen inspect                   # Show currently selected element
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


@click.command()
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def inspected(output_json):
    """
    Get information about the currently inspected element.

    Shows details about the element from DevTools inspection or from 'zen inspect'.

    To capture element from DevTools:
        1. Right-click element → Inspect
        2. In DevTools Console: zenStore()
        3. Run: inspekt inspected

    Or select programmatically:
        zen inspect "h1"
        inspekt inspected
    """
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
            if output_json:
                click.echo(json.dumps({"error": response['error'], "hint": response.get("hint")}, indent=2))
            else:
                click.echo(f"Error: {response['error']}", err=True)
                if response.get("hint"):
                    click.echo(f"Hint: {response['hint']}", err=True)
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

        # Dimensions
        dim = response["dimensions"]
        click.echo("\nDimensions:")
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
        click.echo("\nAccessibility:")
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
                click.echo("  ⚠️  Warning: Image missing alt attribute")
            elif name_source == "none":
                click.echo("  ⚠️  Warning: No accessible name found")

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
        click.echo("\nStyles:")
        for key, value in response["styles"].items():
            click.echo(f"  {key}: {value}")

        # Attributes
        if response.get("attributes"):
            click.echo("\nAttributes:")
            for key, value in response["attributes"].items():
                if len(str(value)) > 50:
                    value = str(value)[:50] + "..."
                click.echo(f"  {key}: {value}")

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


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
    type=int,
    default=None,
    help="Scale factor for high-DPI screenshots (default: from config)",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default=None,
    help="Output format (default: from config)",
)
@click.option(
    "--quality",
    type=float,
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
def screenshot_node(selector, output, margin, margin_color, optimize, scale, format, quality, scroll_into_view, hide_outline):
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
        if selector:
            click.echo(f"Capturing element: {selector}")
        else:
            click.echo("Capturing currently inspected element...")

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

            output = filename
            click.echo(f"Auto-generated filename: {filename}")

        # Save image
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with _builtin_open(output_path, "wb") as f:
            f.write(image_data)

        file_size_kb = len(image_data) / 1024
        click.echo(f"Screenshot saved: {output_path}")
        click.echo(f"Size: {response.get('width')}×{response.get('height')}px ({file_size_kb:.1f} KB)")

        # Optimize with oxipng if requested
        if optimize:
            if format != "png":
                click.echo("Note: --optimize only works with PNG format", err=True)
            else:
                from inspekt.services.image_optimizer import optimize_png

                try:
                    original_size = len(image_data)
                    optimized_size = optimize_png(output_path)

                    if optimized_size:
                        reduction = ((original_size - optimized_size) / original_size) * 100
                        click.echo(
                            f"Optimized: {original_size/1024:.1f} KB → {optimized_size/1024:.1f} KB ({reduction:.1f}% reduction)"
                        )
                    else:
                        click.echo("Optimization skipped (oxipng not available)", err=True)
                except Exception as e:
                    click.echo(f"Optimization failed: {e}", err=True)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screenshot.command(name="viewport")
@click.option("--output", "-o", type=click.Path(), required=True, help="Output file path")
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
    type=int,
    default=2,
    help="Scale factor for high-DPI screenshots (default: 2)",
)
@click.option(
    "--format",
    type=click.Choice(["png", "jpg", "webp"], case_sensitive=False),
    default="png",
    help="Output format (default: png)",
)
@click.option(
    "--quality",
    type=float,
    default=0.92,
    help="Quality for lossy formats (0.0-1.0, default: 0.92)",
)
def screenshot_viewport(output, margin, margin_color, optimize, scale, format, quality):
    """
    Capture a screenshot of the visible viewport.

    Captures exactly what's visible in the browser window.

    Examples:
        inspekt screenshot viewport -o viewport.png
        inspekt screenshot viewport -o view.png --margin 10 --optimize
    """
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
        click.echo("Capturing viewport...")

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

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@screenshot.command(name="page")
@click.option("--output", "-o", type=click.Path(), required=True, help="Output file path")
def screenshot_page(output):
    """
    Capture a screenshot of the entire page (full height).

    NOTE: This feature is not yet implemented.
    Use 'screenshot viewport' for now.

    Examples:
        inspekt screenshot page -o fullpage.png
    """
    click.echo("Error: Full page screenshots are not yet implemented.", err=True)
    click.echo("Use 'inspekt screenshot viewport' to capture the visible viewport.", err=True)
    sys.exit(1)
