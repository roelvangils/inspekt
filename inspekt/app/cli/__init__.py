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


@cli.group()
def completion():
    """Shell tab completion setup.

    Generate completion scripts or install them automatically.

    \b
    Examples:
        inspekt completion install    # Auto-detect shell and install
        inspekt completion status     # Check if installed
        inspekt completion bash       # Output bash script
    """
    pass


def _get_completion_script(shell: str) -> str:
    """Generate the completion script for a shell."""
    from click.shell_completion import get_completion_class
    completion_class = get_completion_class(shell)
    completer = completion_class(cli, {}, "inspekt", "_INSPEKT_COMPLETE")
    return completer.source()


def _detect_shell() -> str | None:
    """Detect the current shell from environment."""
    import os
    from pathlib import Path
    shell_path = os.environ.get("SHELL", "")
    shell_name = Path(shell_path).name if shell_path else ""

    if "zsh" in shell_name:
        return "zsh"
    elif "bash" in shell_name:
        return "bash"
    elif "fish" in shell_name:
        return "fish"
    return None


def _get_rc_file(shell: str):
    """Get the config file path for a shell."""
    from pathlib import Path
    if shell == "zsh":
        return Path.home() / ".zshrc"
    elif shell == "fish":
        return Path.home() / ".config" / "fish" / "completions" / "inspekt.fish"
    else:
        return Path.home() / ".bashrc"


def _is_completion_installed(rc_file) -> bool:
    """Check if completion is already installed."""
    if not rc_file.exists():
        return False
    content = rc_file.read_text()
    return "# inspekt shell completion" in content or "_INSPEKT_COMPLETE" in content


@completion.command("bash")
def completion_bash():
    """Output bash completion script.

    \b
    To install manually:
        inspekt completion bash >> ~/.bashrc
        source ~/.bashrc
    """
    click.echo(_get_completion_script("bash"))


@completion.command("zsh")
def completion_zsh():
    """Output zsh completion script.

    \b
    To install manually:
        inspekt completion zsh >> ~/.zshrc
        source ~/.zshrc
    """
    click.echo(_get_completion_script("zsh"))


@completion.command("fish")
def completion_fish():
    """Output fish completion script.

    \b
    To install manually:
        inspekt completion fish > ~/.config/fish/completions/inspekt.fish
    """
    click.echo(_get_completion_script("fish"))


@completion.command("install")
@click.option("--shell", "-s", type=click.Choice(["bash", "zsh", "fish"]),
              help="Shell to install for (auto-detected if not specified)")
@click.option("--force", "-f", is_flag=True, help="Reinstall even if already installed")
def completion_install(shell: str | None, force: bool):
    """Install shell completion automatically.

    Detects your shell and adds completion to your config file.

    \b
    Examples:
        inspekt completion install           # Auto-detect
        inspekt completion install -s zsh    # Specify shell
        inspekt completion install --force   # Reinstall
    """
    import sys

    # Auto-detect shell
    if shell is None:
        shell = _detect_shell()
        if shell is None:
            click.echo("Could not detect shell. Use --shell to specify.", err=True)
            sys.exit(1)
        click.echo(f"Detected shell: {shell}")

    rc_file = _get_rc_file(shell)

    # Check if already installed
    if _is_completion_installed(rc_file) and not force:
        click.secho(f"Completion already installed in {rc_file}", fg="green")
        click.echo("Use --force to reinstall.")
        return

    # Generate script
    script = _get_completion_script(shell)

    # Install
    try:
        if shell == "fish":
            rc_file.parent.mkdir(parents=True, exist_ok=True)
            rc_file.write_text(script)
        else:
            with open(rc_file, "a") as f:
                f.write(f"\n# inspekt shell completion\n{script}\n")

        click.secho(f"Completion installed to {rc_file}", fg="green")
        click.echo(f"\nReload with: source {rc_file}")

    except PermissionError:
        click.echo(f"Permission denied: {rc_file}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@completion.command("uninstall")
@click.option("--shell", "-s", type=click.Choice(["bash", "zsh", "fish"]),
              help="Shell to uninstall from (auto-detected if not specified)")
def completion_uninstall(shell: str | None):
    """Remove shell completion from config file.

    \b
    Examples:
        inspekt completion uninstall
        inspekt completion uninstall -s zsh
    """
    import sys

    if shell is None:
        shell = _detect_shell()
        if shell is None:
            click.echo("Could not detect shell. Use --shell to specify.", err=True)
            sys.exit(1)

    rc_file = _get_rc_file(shell)

    if not _is_completion_installed(rc_file):
        click.echo(f"Completion not found in {rc_file}")
        return

    # Remove completion lines
    if shell == "fish":
        # Fish uses separate file, just delete it
        if rc_file.exists():
            rc_file.unlink()
            click.secho(f"Removed {rc_file}", fg="green")
    else:
        # Remove from bash/zsh rc file
        lines = rc_file.read_text().splitlines()
        new_lines = []
        skip_block = False

        for line in lines:
            if "# inspekt shell completion" in line:
                skip_block = True
                continue
            if skip_block and ("_INSPEKT_COMPLETE" in line or line.strip() == ""):
                if "_INSPEKT_COMPLETE" in line:
                    skip_block = False
                continue
            skip_block = False
            new_lines.append(line)

        rc_file.write_text("\n".join(new_lines) + "\n")
        click.secho(f"Removed completion from {rc_file}", fg="green")

    click.echo(f"Reload with: source {rc_file}")


@completion.command("status")
def completion_status():
    """Check if shell completion is installed."""
    shell = _detect_shell()
    if shell is None:
        click.echo("Could not detect shell.")
        return

    rc_file = _get_rc_file(shell)

    click.echo(f"Shell:  {shell}")
    click.echo(f"Config: {rc_file}")

    if _is_completion_installed(rc_file):
        click.secho("Status: installed", fg="green")
    else:
        click.secho("Status: not installed", fg="yellow")
        click.echo("\nRun: inspekt completion install")


@cli.command()
@click.option('--install-completion', is_flag=True, help='Automatically install shell completion')
def setup(install_completion: bool):
    """Interactive setup wizard for new users.

    Detects your shell and helps configure:
    - Tab completion for commands
    - Useful tips for getting started

    Run with --install-completion to automatically add completion to your shell config.
    """
    # Detect current shell
    shell = _detect_shell() or "bash"
    rc_file = _get_rc_file(shell)

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

    already_installed = _is_completion_installed(rc_file)

    if already_installed:
        click.secho("  Tab completion is already installed.", fg="green")
    elif install_completion:
        # Auto-install completion using shared logic
        script = _get_completion_script(shell)

        if shell == 'fish':
            rc_file.parent.mkdir(parents=True, exist_ok=True)
            rc_file.write_text(script)
        else:
            with open(rc_file, 'a') as f:
                f.write(f"\n# inspekt shell completion\n{script}\n")

        click.secho(f"  Completion installed to {rc_file}", fg="green")
        click.echo()
        click.secho("  Reload your shell or run:", fg="yellow")
        click.echo(f"    source {rc_file}")
    else:
        click.echo("  Tab completion is not installed.")
        click.echo()
        click.echo("  To enable, run:")
        click.echo()
        click.secho("    inspekt completion install", fg="green")

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


@cli.command()
def config():
    """Open the configuration file in your default editor.

    If no config file exists, creates one at ~/.config/inspekt.json
    with default settings.
    """
    import json
    from pathlib import Path

    from inspekt.config import find_config_file, DEFAULT_CONFIG
    from inspekt.app.cli.util import open_or_download

    config_path = find_config_file()

    if config_path is None:
        # Create default config at XDG location
        config_path = Path.home() / ".config" / "inspekt.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        click.echo(f"Created new config file: {config_path}")

    # Open in default editor (or download if in VM)
    open_or_download(config_path)
    click.echo(f"Opening: {config_path}")


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

# Validation commands (from validation.py)
cli.add_lazy_command("validate", "validation", "validate")

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
