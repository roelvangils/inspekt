"""Selection command - Get selected text from the browser."""

import json
import subprocess
import sys

import click

from inspekt.services.bridge_executor import BridgeExecutor
from inspekt.services.script_loader import ScriptLoader


def html_output_options(fn):
    """Shared Click options for HTML/CSS output formatting."""
    fn = click.option("--indent", type=int, default=2, help="Indentation width")(fn)
    fn = click.option("--theme", type=click.Choice(["monokai", "github", "dracula", "none"]), default="none", help="Syntax highlighting theme")(fn)
    fn = click.option("--colors/--no-colors", default=True, help="Enable ANSI colors in output")(fn)
    fn = click.option("--compact", is_flag=True, help="Compact single-line output")(fn)
    fn = click.option("--pretty", is_flag=True, help="Pretty-print output")(fn)
    fn = click.option("--json", "output_json", is_flag=True, help="Output as JSON")(fn)
    fn = click.option("--copy", is_flag=True, help="Copy output to clipboard")(fn)
    fn = click.option("--raw", is_flag=True, help="Raw output without decorations")(fn)
    return fn


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


def apply_syntax_highlighting(html_content, theme=None):
    """Apply syntax highlighting to HTML using Pygments.

    Args:
        html_content: HTML string to highlight
        theme: Optional Pygments style name (e.g., 'monokai', 'vim', 'github-dark')

    Returns:
        Syntax-highlighted HTML string for terminal display
    """
    try:
        from pygments import highlight
        from pygments.lexers import HtmlLexer
        from pygments.formatters import Terminal256Formatter
        from pygments.styles import get_style_by_name

        # Use Terminal256Formatter for better color support
        formatter_kwargs = {}
        if theme:
            try:
                # Validate theme exists
                style = get_style_by_name(theme)
                formatter_kwargs['style'] = style
            except Exception:
                # Invalid theme, use default
                click.echo(f"Warning: Unknown theme '{theme}', using default", err=True)

        # Apply syntax highlighting with terminal formatter
        formatter = Terminal256Formatter(**formatter_kwargs)
        highlighted = highlight(html_content, HtmlLexer(), formatter)
        return highlighted
    except ImportError:
        # Pygments not available, return original content
        click.echo("Warning: pygments not installed. Install with: pip install pygments", err=True)
        return html_content
    except Exception as e:
        # Any other error, return original content
        click.echo(f"Warning: syntax highlighting failed: {e}", err=True)
        return html_content


def display_selection(response, content_type="text", show_tip=True, pretty=None, compact=None, colors=None, theme=None):
    """Display selection in formatted output."""
    from inspekt.config import get_html_selection_config

    text = response.get("text", "")
    length = response.get("length", 0)

    # Determine what to display based on content_type
    if content_type == "text":
        content = text
        display_name = "Selected Text"
    elif content_type == "html":
        content = response.get("html", "")
        display_name = "Selected HTML"

        # Apply pretty, compact, and syntax highlighting for HTML display
        from inspekt.services.html_processor import process_html
        config = get_html_selection_config()

        # Use provided flags or fall back to config/defaults
        use_pretty = pretty if pretty is not None else config["pretty"]
        use_compact = compact if compact is not None else config["compact"]
        use_colors = colors if colors is not None else config["colors"]
        use_theme = theme if theme is not None else config["theme"]

        # Apply pretty and compact for display mode
        if use_pretty or use_compact:
            content = process_html(content, prettier=use_pretty, compact=use_compact)

        # Apply syntax highlighting if outputting to terminal
        if use_colors and sys.stdout.isatty():
            content = apply_syntax_highlighting(content, theme=use_theme)

    elif content_type == "markdown":
        html = response.get("html", "")
        content = html_to_markdown(html) if html else text
        display_name = "Selected Markdown"
    else:
        content = text
        display_name = "Selected Text"

    # For HTML, show with separator lines
    if content_type == "html":
        # Dark gray color for separators (ANSI code: bright black)
        dark_gray = "\033[90m"
        reset = "\033[0m"
        separator = f"{dark_gray}{'—' * 80}{reset}"
        # Remove empty lines
        content = '\n'.join(line for line in content.split('\n') if line.strip())
        click.echo(f"{display_name} ({len(response.get('html', ''))} characters):\n")
        click.echo(separator)
        click.echo(content)
        click.echo(separator)
        click.echo("")
    else:
        # Show header with character count for other types
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

    # Show tips
    if show_tip:
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo("Tips:")
        click.echo(_style_with_inline_code(f"  • Use `inspekt selection {content_type} --raw` for raw {content_type.upper()} output", base_fg="white"))
        click.echo(_style_with_inline_code(f"  • Type `inspekt selection {content_type} --help` for advanced options", base_fg="white"))


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
            from inspekt.app.cli.table import print_hint
            print_hint("Select some text in the browser first, then run `inspekt selection text`.")
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

    # Raw mode: just print the text, nothing else (strip trailing whitespace)
    if raw:
        click.echo(text_content.rstrip())
        return

    # Formatted display
    display_selection(response, content_type="text")


@selection.command()
@click.option("--raw", is_flag=True, help="Output only the raw HTML without formatting")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option("--pretty/--no-pretty", default=None, help="Format HTML using prettier (default: from config)")
@click.option("--compact/--no-compact", default=None, help="Remove classes and truncate long text (default: from config)")
@click.option("--colors/--no-colors", default=None, help="Apply syntax highlighting (default: from config)")
@click.option("--theme", default=None, help="Syntax highlighting theme (e.g., monokai, vim, github-dark)")
def html(raw, output_json, pretty, compact, colors, theme):
    """Get selected HTML."""
    from inspekt.config import get_html_selection_config

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

    response = get_selection_data()

    if response is None:
        if output_json:
            click.echo(json.dumps({"hasSelection": False, "html": "", "length": 0}, indent=2))
        elif not raw:
            click.echo("No text selected")
            from inspekt.app.cli.table import print_hint
            print_hint("Select some text in the browser first, then run `inspekt selection html`.")
        sys.exit(0)

    html_content = response.get("html", "")

    # Process HTML if pretty or compact flags are set
    if pretty or compact:
        from inspekt.services.html_processor import process_html
        html_content = process_html(html_content, prettier=pretty, compact=compact)

    # Apply syntax highlighting if requested (before JSON/raw output)
    # Only apply if outputting to a terminal (not piped/redirected)
    if colors and not output_json and sys.stdout.isatty():
        html_content = apply_syntax_highlighting(html_content, theme=theme)

    # JSON mode: output only html data
    if output_json:
        output = {
            "hasSelection": True,
            "html": html_content,
            "length": response.get("length", 0)
        }
        click.echo(json.dumps(output, indent=2))
        return

    # Raw mode: just print the HTML, nothing else (strip trailing whitespace)
    if raw:
        click.echo(html_content.rstrip())
        return

    # Formatted display - pass flags to display function
    display_selection(response, content_type="html", pretty=pretty, compact=compact, colors=colors, theme=theme)


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
            from inspekt.app.cli.table import print_hint
            print_hint("Select some text in the browser first, then run `inspekt selection markdown`.")
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

    # Raw mode: just print the markdown, nothing else (strip trailing whitespace)
    if raw:
        click.echo(markdown_content.rstrip())
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

    Please use 'inspekt selection text' instead.
    """
    click.echo("Warning: 'inspekt selected' is deprecated. Use 'inspekt selection text' instead.\n", err=True)

    response = get_selection_data()

    if response is None:
        if output_json:
            click.echo(json.dumps({"hasSelection": False, "text": "", "length": 0}, indent=2))
        elif not raw:
            click.echo("No text selected")
            from inspekt.app.cli.table import print_hint
            print_hint("Select some text in the browser first, then run `inspekt selection text`.")
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
