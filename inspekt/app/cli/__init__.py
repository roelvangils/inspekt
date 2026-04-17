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


def _no_tips_callback(ctx, param, value):
    """Eager callback for --no-tips: sets INSPEKT_NO_TIPS env var.

    Used by both the top-level cli group and by CustomGroup._inject_global_options()
    which adds --no-tips to every subcommand. The env var is checked by
    tips_enabled() in config.py, which gates print_hint() and _print_tips_section().
    """
    if value:
        import os
        os.environ['INSPEKT_NO_TIPS'] = '1'


@click.group(cls=CustomGroup)
@click.version_option(version=__version__)
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output (timing, requests, state changes)')
@click.option('--no-tips', is_flag=True, is_eager=True, expose_value=False,
              callback=_no_tips_callback, help='Suppress tips and hints in output')
@click.option('--instance', '-i', 'instance_id', default=None, metavar='ID',
              help='Target specific browser instance by ID, alias, or index (e.g., "b7x2", "homepage", "0")')
@click.pass_context
def cli(ctx, verbose, instance_id):
    """Inspekt - Browser automation and inspection from the command line."""
    import os

    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['instance_id'] = instance_id

    if verbose:
        os.environ['INSPEKT_VERBOSE'] = '1'

    if instance_id:
        os.environ['INSPEKT_INSTANCE'] = instance_id


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
    from inspekt.app.cli.icons import get_indicator
    from inspekt.app.cli.table import Table, format_status_icon

    shell = _detect_shell()
    if shell is None:
        click.echo("Could not detect shell.")
        return

    rc_file = _get_rc_file(shell)
    installed = _is_completion_installed(rc_file)

    click.echo()
    table = Table(["Property", "Value"], title="Shell Completion", icon=get_indicator("terminal"))

    if installed:
        status_text = f"{format_status_icon('pass')} " + click.style("Installed", fg="green")
    else:
        status_text = f"{format_status_icon('warning')} " + click.style("Not installed", fg="yellow")

    data = [
        ["Shell", shell],
        ["Config", str(rc_file)],
        ["Status", status_text],
    ]
    table.set_data(data)
    table.print_header(skip_column_headers=True)
    for row in data:
        table.print_row(row)
    table.print_footer()

    if not installed:
        click.echo()
        click.echo(f"  To install, run: " + click.style("inspekt completion install", fg="cyan"))


@cli.command()
@click.option('--install-completion', is_flag=True, help='Automatically install shell completion')
def setup(install_completion: bool):
    """Interactive setup wizard for new users.

    Detects your shell and helps configure:
    - Tab completion for commands
    - Useful tips for getting started

    Run with --install-completion to automatically add completion to your shell config.
    """
    from inspekt.app.cli.icons import get_icon, get_indicator, get_status_icon
    from inspekt.app.cli.table import Table, format_status_icon

    # Detect current shell
    shell = _detect_shell() or "bash"
    rc_file = _get_rc_file(shell)
    already_installed = _is_completion_installed(rc_file)

    click.echo()

    # === System Info Table ===
    info_table = Table(["Property", "Value"], title="Inspekt Setup", icon=get_indicator("info_circle"))
    info_data = [
        ["Version", __version__],
        ["Shell", shell],
        ["Config", str(rc_file)],
    ]
    info_table.set_data(info_data)
    info_table.print_header(skip_column_headers=True)
    for row in info_data:
        info_table.print_row(row)
    info_table.print_footer()

    click.echo()

    # === Shell Completion Table ===
    completion_table = Table(["Setting", "Status"], title="Shell Completion", icon=get_indicator("terminal"))

    if already_installed:
        status_text = f"{format_status_icon('pass')} " + click.style("Installed", fg="green")
    else:
        status_text = f"{format_status_icon('warning')} " + click.style("Not installed", fg="yellow")

    completion_data = [
        ["Tab completion", status_text],
    ]
    completion_table.set_data(completion_data)
    completion_table.print_header(skip_column_headers=True)
    for row in completion_data:
        completion_table.print_row(row)
    completion_table.print_footer()

    # Handle completion installation
    if not already_installed:
        if install_completion:
            # Auto-install completion using shared logic
            script = _get_completion_script(shell)

            if shell == 'fish':
                rc_file.parent.mkdir(parents=True, exist_ok=True)
                rc_file.write_text(script)
            else:
                with open(rc_file, 'a') as f:
                    f.write(f"\n# inspekt shell completion\n{script}\n")

            click.echo()
            click.secho(f"{get_status_icon('pass')} Completion installed to {rc_file}", fg="green")
            click.echo(f"  Reload your shell or run: source {rc_file}")
        else:
            click.echo()
            click.echo(f"  To enable tab completion, run:")
            click.secho("  inspekt completion install", fg="cyan")

    click.echo()

    # === Quick Tips Table ===
    tips_table = Table(["Command", "Description"], title="Quick Start", icon=get_indicator("tip"))
    tips_data = [
        [click.style("inspekt start", fg="cyan"), "Start the bridge server"],
        [click.style("inspekt status", fg="cyan"), "Check connection status"],
        [click.style("inspekt record", fg="cyan"), "Record browser interactions"],
        [click.style("inspekt replay", fg="cyan"), "Replay a recording"],
        [click.style("inspekt --help", fg="cyan"), "Show all commands"],
    ]
    tips_table.set_data(tips_data)
    tips_table.print_header(skip_column_headers=True)
    for row in tips_data:
        tips_table.print_row(row)
    tips_table.print_footer()

    click.echo()
    from inspekt.app.cli.table import print_hint
    print_hint("Mistype a command? Inspekt suggests corrections! Try `inspekt screenshit` → Did you mean 'screenshot'?")


@cli.command()
def config():
    """Open the configuration file in your default editor.

    If no config file exists, creates one at ~/.config/inspekt.json
    with default settings.
    """
    import json
    from pathlib import Path

    from inspekt.config import find_config_file, DEFAULT_CONFIG
    from inspekt.app.cli.output import OutputHandler

    config_path = find_config_file()

    if config_path is None:
        # Create default config at XDG location
        config_path = Path.home() / ".config" / "inspekt.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        click.echo(f"Created new config file: {config_path}")

    # Open in default editor (or download if in VM)
    OutputHandler.open_file(config_path)
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

# Storage management commands (from storage.py)
# Note: Use 'inspekt storage --cookies' for cookie operations
cli.add_lazy_command("storage", "storage", "storage")

# Domain management commands (from domain.py)
cli.add_lazy_command("domain", "domain", "domain")

# Interaction commands (from interaction.py)
cli.add_lazy_command("type", "interaction", "type_text")
cli.add_lazy_command("paste", "interaction", "paste")
cli.add_lazy_command("press", "interaction", "press")
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
cli.add_lazy_command("focused", "inspection", "focused")
cli.add_lazy_command("screenshot", "inspection", "screenshot")

# Accessibility commands (from accessibility.py)
cli.add_lazy_command("axe", "accessibility", "axe")
cli.add_lazy_command("ibm", "accessibility", "ibm")
cli.add_lazy_command("a11y", "accessibility", "a11y")
cli.add_lazy_command("a11y-reset", "accessibility", "a11y_reset")
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

# Browser instance management commands (from instances.py)
cli.add_lazy_command("instances", "instances", "instances")

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

# Extract command group (from extract.py)
cli.add_lazy_command("extract", "extract", "extract")

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

# Sitemap inspection and navigation (from sitemap.py)
cli.add_lazy_command("sitemap", "sitemap", "sitemap")

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

# Screen reader simulator commands (from screen_reader.py)
cli.add_lazy_command("sr", "screen_reader", "sr")

# PDF accessibility commands (from pdf.py)
cli.add_lazy_command("pdf", "pdf", "pdf")

# Autostart management (macOS LaunchAgent)
cli.add_lazy_command("autostart", "autostart", "autostart")

# Tunnel command (expose local port to VM)
cli.add_lazy_command("tunnel", "tunnel", "tunnel")

# Display commands: zoom and viewport (from display.py)
cli.add_lazy_command("zoom", "display", "zoom")
cli.add_lazy_command("viewport", "display", "viewport")

# Man page management (from man.py)
cli.add_lazy_command("man", "man", "man")


# ============================================================================
# VM Restricted Mode
# ============================================================================
# When INSPEKT_RESTRICTED=1 (set by terminal-server.py in the VM),
# remove commands that are dangerous in a shared/sandboxed terminal.

import os as _os
if _os.environ.get('INSPEKT_RESTRICTED') == '1':
    _RESTRICTED_COMMANDS = {
        'eval', 'exec', 'repl',    # Arbitrary JS execution
        'plugin',                    # Persistent JS plugins
        'yolo',                      # Bypass all security restrictions
        'domain',                    # CSP/domain bypass
        'vm',                        # Docker management (nonsensical inside VM)
        'do',                        # Natural language browser actions
        'mcp',                       # MCP server management
        'autostart',                 # macOS LaunchAgent (nonsensical inside VM)
        'tunnel',                    # Tunneling from inside VM is nonsensical
    }
    for _cmd in _RESTRICTED_COMMANDS:
        cli._lazy_commands.pop(_cmd, None)


# ============================================================================
# Export main CLI
# ============================================================================

def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()


__all__ = ["cli", "main"]
