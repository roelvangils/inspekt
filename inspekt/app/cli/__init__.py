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

# Utility commands (from util.py)
cli.add_lazy_command("info", "util", "info")
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


# ============================================================================
# Export main CLI
# ============================================================================

def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()


__all__ = ["cli", "main"]
