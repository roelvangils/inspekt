"""Selection command - Get selected text from the browser."""

import json
import subprocess
import sys

import click

from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader


def get_selection_data():
    """Helper function to get selection data from browser."""
    executor = BridgeExecutor()
    executor.ensure_server_running()

    # Load the get_selection.js script
    loader = ScriptLoader()
    try:
        code = loader.load_script_sync("get_selection.js")
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        result = executor.execute(code, timeout=60.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        response = result.get("result", {})

        if not response.get("hasSelection"):
            return None

        return response

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def html_to_markdown(html_content):
    """Convert HTML to Markdown using html2markdown CLI."""
    try:
        # Use full path to html2markdown to work when called from GUI apps
        # that don't have /opt/homebrew/bin in PATH
        result = subprocess.run(
            ["/opt/homebrew/bin/html2markdown"],
            input=html_content,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # Fallback: return HTML if conversion fails
            return html_content
    except Exception:
        # Fallback: return HTML if conversion fails
        return html_content


def display_selection(response, content_type="text", show_tip=True):
    """Display selection in formatted output."""
    text = response.get("text", "")
    length = response.get("length", 0)

    # Determine what to display based on content_type
    if content_type == "text":
        content = text
        display_name = "Selected Text"
    elif content_type == "html":
        content = response.get("html", "")
        display_name = "Selected HTML"
    elif content_type == "markdown":
        html = response.get("html", "")
        content = html_to_markdown(html) if html else text
        display_name = "Selected Markdown"
    else:
        content = text
        display_name = "Selected Text"

    # Show header with character count
    if len(content) > 200:
        click.echo(f"{display_name} (showing first 200 of {len(content)} characters):\n")
        click.echo(f'"{content[:200]}…"\n')
    else:
        click.echo(f"{display_name} ({len(content)} characters):\n")
        click.echo(f'"{content}"\n')

    # Position info
    pos = response.get("position", {})
    click.echo("Position:")
    click.echo(f"  x={pos.get('x')}, y={pos.get('y')}")
    click.echo(f"  Size: {pos.get('width')}×{pos.get('height')}\n")

    # Container element
    container = response.get("container", {})
    if container.get("tag"):
        click.echo("Container:")
        tag = container['tag']
        click.echo(f"  Tag: <{tag}>")
        if container.get("id"):
            click.echo(f"  ID: {container['id']}")
        if container.get("class"):
            click.echo(f"  Class: {container['class']}")
        click.echo("")

    # Show tip
    if show_tip:
        click.echo(f"Tip: Use `zen selection {content_type} --raw` for raw output.")


@click.group(invoke_without_command=True)
@click.option("--json", "output_json", is_flag=True, help="Output as JSON with all formats")
@click.pass_context
def selection(ctx, output_json):
    """Get the current text selection in the browser."""
    # If no subcommand is provided and --json flag is used, return all formats
    if ctx.invoked_subcommand is None and output_json:
        response = get_selection_data()

        if response is None:
            click.echo(json.dumps({
                "hasSelection": False,
                "text": "",
                "html": "",
                "markdown": "",
                "length": 0
            }, indent=2))
            sys.exit(0)

        # Generate markdown from HTML
        html = response.get("html", "")
        text_content = response.get("text", "")
        markdown_content = html_to_markdown(html) if html else text_content

        # Return all three formats
        output = {
            "hasSelection": True,
            "text": text_content,
            "html": html,
            "markdown": markdown_content,
            "length": response.get("length", 0),
            "position": response.get("position", {}),
            "container": response.get("container", {})
        }
        click.echo(json.dumps(output, indent=2))
        sys.exit(0)
    elif ctx.invoked_subcommand is None:
        # No subcommand and no --json flag, show help
        click.echo(ctx.get_help())
        sys.exit(0)


@selection.command()
@click.option("--raw", is_flag=True, help="Output only the raw text without formatting")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def text(raw, output_json):
    """Get selected text (plain text)."""
    response = get_selection_data()

    if response is None:
        if output_json:
            click.echo(json.dumps({"hasSelection": False, "text": "", "length": 0}, indent=2))
        elif not raw:
            click.echo("No text selected")
            click.echo("Hint: Select some text in the browser first, then run: zen selection text")
        sys.exit(0)

    text_content = response.get("text", "")

    # JSON mode: output only text data
    if output_json:
        output = {
            "hasSelection": True,
            "text": text_content,
            "length": response.get("length", 0)
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the text, nothing else
    if raw:
        click.echo(text_content)
        return

    # Formatted display
    display_selection(response, content_type="text")


@selection.command()
@click.option("--raw", is_flag=True, help="Output only the raw HTML without formatting")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def html(raw, output_json):
    """Get selected HTML."""
    response = get_selection_data()

    if response is None:
        if output_json:
            click.echo(json.dumps({"hasSelection": False, "html": "", "length": 0}, indent=2))
        elif not raw:
            click.echo("No text selected")
            click.echo("Hint: Select some text in the browser first, then run: zen selection html")
        sys.exit(0)

    html_content = response.get("html", "")

    # JSON mode: output only html data
    if output_json:
        output = {
            "hasSelection": True,
            "html": html_content,
            "length": response.get("length", 0)
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the HTML, nothing else
    if raw:
        click.echo(html_content)
        return

    # Formatted display
    display_selection(response, content_type="html")


@selection.command()
@click.option("--raw", is_flag=True, help="Output only the raw Markdown without formatting")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def markdown(raw, output_json):
    """Get selected text as Markdown (converted from HTML)."""
    response = get_selection_data()

    if response is None:
        if output_json:
            click.echo(json.dumps({"hasSelection": False, "markdown": "", "length": 0}, indent=2))
        elif not raw:
            click.echo("No text selected")
            click.echo("Hint: Select some text in the browser first, then run: zen selection markdown")
        sys.exit(0)

    html_content = response.get("html", "")
    text_content = response.get("text", "")
    markdown_content = html_to_markdown(html_content) if html_content else text_content

    # JSON mode: output only markdown data
    if output_json:
        output = {
            "hasSelection": True,
            "markdown": markdown_content,
            "length": response.get("length", 0)
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the markdown, nothing else
    if raw:
        click.echo(markdown_content)
        return

    # Formatted display
    display_selection(response, content_type="markdown")


# Keep the old 'selected' command for backward compatibility (deprecated)
@click.command()
@click.option("--raw", is_flag=True, help="Output only the text without formatting")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
def selected(raw, output_json):
    """
    [DEPRECATED] Get the current text selection in the browser.

    Please use 'zen selection text' instead.
    """
    click.echo("Warning: 'zen selected' is deprecated. Use 'zen selection text' instead.\n", err=True)

    response = get_selection_data()

    if response is None:
        if output_json:
            click.echo(json.dumps({"hasSelection": False, "text": "", "length": 0}, indent=2))
        elif not raw:
            click.echo("No text selected")
            click.echo("Hint: Select some text in the browser first, then run: zen selection text")
        sys.exit(0)

    text_content = response.get("text", "")

    # JSON mode: output only text data (for backward compatibility)
    if output_json:
        output = {
            "hasSelection": True,
            "text": text_content,
            "length": response.get("length", 0)
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the text, nothing else
    if raw:
        click.echo(text_content, nl=False)
        return

    # Old-style display (for backward compatibility)
    click.echo(f"Selected Text ({response.get('length', 0)} characters):")
    click.echo("")

    # Show text (with proper formatting for long selections)
    if len(text_content) <= 200:
        click.echo(f'"{text_content}"')
    else:
        # Show first 200 chars with ellipsis
        click.echo(f'"{text_content[:200]}..."')
        click.echo("")
        click.echo(f"(showing first 200 of {len(text_content)} characters)")

    # Position info
    pos = response.get("position", {})
    click.echo("\nPosition:")
    click.echo(f"  x={pos.get('x')}, y={pos.get('y')}")
    click.echo(f"  Size: {pos.get('width')}×{pos.get('height')}px")

    # Container element
    container = response.get("container", {})
    if container.get("tag"):
        click.echo("\nContainer:")
        click.echo(f"  Tag:   <{container['tag']}>")
        if container.get("id"):
            click.echo(f"  ID:    {container['id']}")
        if container.get("class"):
            click.echo(f"  Class: {container['class']}")

    # HTML if different from text
    html = response.get("html", "")
    if html and html.strip() != text_content.strip():
        click.echo("\nHTML:")
        if len(html) <= 200:
            click.echo(f"  {html}")
        else:
            click.echo(f"  {html[:200]}...")
