"""
Inspekt CLI - Main entry point.

This module assembles all CLI commands from individual command modules
and creates the main CLI group with Click.

Uses lazy imports to minimize startup time - modules are only imported
when their commands are actually invoked.
"""

from __future__ import annotations

import click

from inspekt import __version__
from inspekt.app.cli.base import CustomGroup


@click.group(cls=CustomGroup)
@click.version_option(version=__version__)
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output (timing, requests, state changes)')
@click.pass_context
def cli(ctx, verbose):
    """Inspekt - Browser automation and inspection from the command line."""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose

    if verbose:
        import os
        os.environ['INSPEKT_VERBOSE'] = '1'


@cli.command()
@click.argument('shell', type=click.Choice(['bash', 'zsh', 'fish']))
def completion(shell: str):
    """Generate shell completion script.

    Install with:

    \b
      # Bash
      inspekt completion bash >> ~/.bashrc

    \b
      # Zsh
      inspekt completion zsh >> ~/.zshrc

    \b
      # Fish
      inspekt completion fish > ~/.config/fish/completions/inspekt.fish

    Then restart your shell or source the file.
    """
    from click.shell_completion import get_completion_class

    # Get the completion class for the requested shell
    completion_class = get_completion_class(shell)

    # Create a completer instance and generate the source script
    completer = completion_class(cli, {}, "inspekt", "_INSPEKT_COMPLETE")
    click.echo(completer.source())


@cli.command()
@click.option('--install-completion', is_flag=True, help='Automatically install shell completion')
def setup(install_completion: bool):
    """Interactive setup wizard for new users.

    Detects your shell and helps configure:
    - Tab completion for commands
    - Useful tips for getting started

    Run with --install-completion to automatically add completion to your shell config.
    """
    import os
    import subprocess
    from pathlib import Path
    from click.shell_completion import get_completion_class

    # Detect current shell
    shell_path = os.environ.get('SHELL', '')
    if 'zsh' in shell_path:
        shell = 'zsh'
        rc_file = Path.home() / '.zshrc'
    elif 'fish' in shell_path:
        shell = 'fish'
        rc_file = Path.home() / '.config' / 'fish' / 'completions' / 'inspekt.fish'
    else:
        shell = 'bash'
        rc_file = Path.home() / '.bashrc'

    click.echo()
    click.secho("  Inspekt Setup Wizard", fg="cyan", bold=True)
    click.secho("  " + "=" * 20, fg="cyan")
    click.echo()

    # Show version
    click.echo(f"  Version: {__version__}")
    click.echo(f"  Shell:   {shell}")
    click.echo()

    # Shell completion
    click.secho("  Shell Completion", fg="yellow", bold=True)
    click.echo("  ----------------")

    # Check if completion is already installed
    completion_marker = "# inspekt shell completion" if shell != 'fish' else "_inspekt_completion"
    already_installed = False

    if rc_file.exists():
        content = rc_file.read_text()
        if completion_marker in content or "_inspekt_completion" in content:
            already_installed = True

    if already_installed:
        click.secho("  Tab completion is already installed.", fg="green")
    elif install_completion:
        # Auto-install completion
        completion_class = get_completion_class(shell)
        completer = completion_class(cli, {}, "inspekt", "_INSPEKT_COMPLETE")
        script = completer.source()

        if shell == 'fish':
            # Fish uses a separate file
            rc_file.parent.mkdir(parents=True, exist_ok=True)
            rc_file.write_text(script)
            click.secho(f"  Completion installed to {rc_file}", fg="green")
        else:
            # Bash/zsh append to rc file
            with open(rc_file, 'a') as f:
                f.write(f"\n# inspekt shell completion\n{script}\n")
            click.secho(f"  Completion added to {rc_file}", fg="green")

        click.echo()
        click.secho("  Reload your shell or run:", fg="yellow")
        if shell == 'fish':
            click.echo(f"    source {rc_file}")
        else:
            click.echo(f"    source {rc_file}")
    else:
        click.echo("  Tab completion is not installed.")
        click.echo()
        click.echo("  To enable, run one of:")
        click.echo()
        click.secho(f"    inspekt setup --install-completion", fg="green")
        click.echo("    # or manually:")
        if shell == 'fish':
            click.echo(f"    inspekt completion {shell} > {rc_file}")
        else:
            click.echo(f"    inspekt completion {shell} >> {rc_file}")

    click.echo()

    # Quick tips
    click.secho("  Quick Tips", fg="yellow", bold=True)
    click.echo("  ----------")
    click.echo("  - Mistype a command? Inspekt suggests corrections:")
    click.secho("      $ inspekt screenshit", fg="white", dim=True)
    click.secho("      Error: Did you mean: 'screenshot'?", fg="white", dim=True)
    click.echo()
    click.echo("  - Start the bridge server:")
    click.echo("      inspekt start")
    click.echo()
    click.echo("  - Check connection status:")
    click.echo("      inspekt status")
    click.echo()
    click.echo("  - Get help on any command:")
    click.echo("      inspekt <command> --help")
    click.echo()


# ============================================================================
# Lazy Command Registration
# ============================================================================
# Commands are only imported when they are actually invoked, improving startup time

# Execution commands (from exec.py)
cli.add_lazy_command("eval", "exec", "eval")
cli.add_lazy_command("exec", "exec", "exec")

# Navigation commands (from navigation.py)
cli.add_lazy_command("open", "navigation", "open")
cli.add_lazy_command("back", "navigation", "back")
cli.add_lazy_command("forward", "navigation", "forward")
cli.add_lazy_command("reload", "navigation", "reload")
cli.add_lazy_command("pageup", "navigation", "pageup")
cli.add_lazy_command("pagedown", "navigation", "pagedown")
cli.add_lazy_command("top", "navigation", "top")
cli.add_lazy_command("bottom", "navigation", "bottom")
cli.add_lazy_command("previous", "navigation", "previous")
cli.add_lazy_command("next", "navigation", "next")
cli.add_lazy_command("refresh", "navigation", "refresh")
cli.add_lazy_command("pgup", "navigation", "pgup")
cli.add_lazy_command("pgdown", "navigation", "pgdown")
cli.add_lazy_command("home", "navigation", "home")
cli.add_lazy_command("end", "navigation", "end")

# Cookie management commands (from cookies.py)
cli.add_lazy_command("cookies", "cookies", "cookies")

# Storage management commands (from storage.py)
cli.add_lazy_command("storage", "storage", "storage")

# Domain management commands (from domain.py)
cli.add_lazy_command("domain", "domain", "domain")

# Interaction commands (from interaction.py)
cli.add_lazy_command("type", "interaction", "type_text")
cli.add_lazy_command("paste", "interaction", "paste")
cli.add_lazy_command("send", "interaction", "send")
cli.add_lazy_command("click", "interaction", "click_element")
cli.add_lazy_command("double-click", "interaction", "double_click")
cli.add_lazy_command("doubleclick", "interaction", "doubleclick_alias")
cli.add_lazy_command("right-click", "interaction", "right_click")
cli.add_lazy_command("rightclick", "interaction", "rightclick_alias")
cli.add_lazy_command("wait", "interaction", "wait")

# Inspection commands (from inspection.py)
cli.add_lazy_command("inspect", "inspection", "inspect")
cli.add_lazy_command("inspected", "inspection", "inspected")
cli.add_lazy_command("screenshot", "inspection", "screenshot")

# Accessibility commands (from accessibility.py)
cli.add_lazy_command("axe", "accessibility", "axe")
cli.add_lazy_command("autocomplete", "accessibility", "autocomplete")

# Selection commands (from selection.py)
cli.add_lazy_command("selection", "selection", "selection")
cli.add_lazy_command("selected", "selection", "selected")

# Unified server management commands (from control.py)
cli.add_lazy_command("start", "control", "start")
cli.add_lazy_command("stop", "control", "stop")
cli.add_lazy_command("restart", "control", "restart")
cli.add_lazy_command("status", "control", "status")
cli.add_lazy_command("queue", "control", "queue")

# MCP server management commands (from mcp.py)
cli.add_lazy_command("mcp", "mcp", "mcp")

# Content extraction commands (from extraction.py)
cli.add_lazy_command("describe", "extraction", "describe")
cli.add_lazy_command("do", "extraction", "do")
cli.add_lazy_command("outline", "extraction", "outline")
cli.add_lazy_command("links", "extraction", "links")
cli.add_lazy_command("summarize", "extraction", "summarize")
cli.add_lazy_command("index", "extraction", "index")
cli.add_lazy_command("ask", "extraction", "ask")

# Watch commands (from watch.py)
cli.add_lazy_command("watch", "watch", "watch")
cli.add_lazy_command("control", "watch", "control")

# Recording commands (from record.py)
cli.add_lazy_command("record", "record", "record")

# Replay commands (from replay.py)
cli.add_lazy_command("replay", "replay", "replay")

# Info command group (from info.py)
cli.add_lazy_command("info", "info", "info")

# Utility commands (from util.py)
cli.add_lazy_command("repl", "util", "repl")
cli.add_lazy_command("userscript", "util", "userscript")
cli.add_lazy_command("download", "util", "download")
cli.add_lazy_command("md-link", "util", "md_link")

# Robots.txt inspection (from robots.py)
cli.add_lazy_command("robots", "robots", "robots")

# Network inspection commands (from network.py)
cli.add_lazy_command("network", "network", "network")

# Page saving commands (from save.py)
cli.add_lazy_command("save", "save", "save")

# Console message commands (from console.py)
cli.add_lazy_command("console", "console", "console")
cli.add_lazy_command("log", "console", "log_expression")  # Shorthand for `console log`

# Yolo mode (top-level command from domain.py)
cli.add_lazy_command("yolo", "domain", "yolo")

# Plugin management commands (from plugin.py)
cli.add_lazy_command("plugin", "plugin", "plugin")

# VM management commands (from vm.py)
cli.add_lazy_command("vm", "vm", "vm")


# ============================================================================
# Export main CLI
# ============================================================================

def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()


__all__ = ["cli", "main"]
