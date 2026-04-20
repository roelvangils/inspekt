"""
VM terminal helper: typo-tolerant command suggestions.

Called by the restricted zsh's command_not_found_handler when a user types
something zsh can't resolve. Prints up to three close matches from the full
Click command list, one per line, so the handler can present them as
"Did you mean: axe, ask, autocomplete?". Exits silently on no match.

Hidden from --help; removed from the shortcut symlink set in the VM image.
"""

from __future__ import annotations

import difflib
import os

import click

# The shortcut directory populated by the VM Dockerfile is the single source of
# truth for commands the restricted user can actually invoke — hidden helpers
# (including `suggest` itself) and denylisted commands have already been
# excluded there. Falling back to the full CLI list is fine for non-VM use.
_VM_COMMANDS_DIR = "/opt/inspekt/commands"


def _usable_command_names() -> list[str]:
    try:
        entries = os.listdir(_VM_COMMANDS_DIR)
    except OSError:
        from inspekt.app.cli import cli as root_cli

        return list(root_cli.list_commands(click.Context(root_cli)))

    return [n for n in entries if not n.startswith(".")]


@click.command("suggest", hidden=True)
@click.argument("name", required=False)
def suggest(name: str | None) -> None:
    """Print fuzzy matches for NAME against the user-invokable command list."""
    if not name:
        return

    for match in difflib.get_close_matches(name, _usable_command_names(), n=3, cutoff=0.55):
        click.echo(match)
