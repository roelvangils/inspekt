"""
URL Builder - Generate inspekt:// URLs from CLI commands.

This module provides utilities to convert CLI command invocations
into their equivalent inspekt:// URL scheme format.

The @url_scheme decorator adds a --get-url flag to commands that
support the URL scheme, allowing users to get the URL instead of
executing the command.

Example:
    inspekt md-link --get-url
    # → inspekt://md-link

    inspekt screenshot viewport --margin 20 --get-url
    # → inspekt://screenshot?target=viewport&margin=20
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import click

from inspekt.app.cli.table import print_hint

if TYPE_CHECKING:
    from collections.abc import Callable


def make_url_link(url: str, display_text: str | None = None) -> str:
    """
    Create an OSC 8 terminal hyperlink for a URL.

    Makes URLs clickable in terminals that support OSC 8 (iTerm2, kitty,
    WezTerm, Windows Terminal, xterm.js, and others).
    """
    display = display_text or url
    return f"\033]8;;{url}\033\\{display}\033]8;;\033\\"


def build_inspekt_url(
    url_scheme_name: str,
    params: dict[str, Any],
    defaults: dict[str, Any] | None = None,
) -> str:
    """
    Build an inspekt:// URL from a scheme name and parameters.

    Args:
        url_scheme_name: The URL scheme name (e.g., "screenshot", "md-link")
        params: Dictionary of parameter names to values
        defaults: Optional dictionary of default values to omit from URL

    Returns:
        The complete inspekt:// URL string
    """
    defaults = defaults or {}

    # Separate boolean flags from value params for cleaner URLs
    # Boolean True becomes just "param" instead of "param=true"
    bool_flags: list[str] = []
    value_params: dict[str, str] = {}

    for key, value in params.items():
        # Skip None values
        if value is None:
            continue

        # Skip empty strings
        if isinstance(value, str) and value == "":
            continue

        # Skip values that match defaults
        if key in defaults and value == defaults[key]:
            continue

        # Boolean values: True becomes a flag, False is skipped
        if isinstance(value, bool):
            if value:
                bool_flags.append(key)
            continue

        # List/tuple values: join with commas
        if isinstance(value, (list, tuple)):
            if value:
                value_params[key] = ",".join(str(v) for v in value)
            continue

        # Other values: convert to string
        value_params[key] = str(value)

    base = f"inspekt://{url_scheme_name}"

    # Build query string with flags first, then value params
    query_parts = []
    for flag in bool_flags:
        query_parts.append(quote(flag, safe=""))
    for key, value in value_params.items():
        query_parts.append(f"{quote(key, safe='')}={quote(value, safe='')}")

    if query_parts:
        return f"{base}?{'&'.join(query_parts)}"

    return base


def url_scheme(
    scheme_name: str,
    param_map: dict[str, str] | None = None,
    defaults: dict[str, Any] | None = None,
    extra_params: dict[str, Any] | None = None,
    exclude_params: list[str] | None = None,
) -> Callable:
    """
    Decorator that adds --get-url support to a CLI command.

    When --get-url is provided, outputs the inspekt:// URL instead of
    executing the command.

    Args:
        scheme_name: The URL scheme name (e.g., "screenshot", "md-link")
        param_map: Optional mapping from CLI option names to URL param names.
                   If not provided, CLI option names are used directly.
        defaults: Optional dictionary of default values to omit from URL.
        extra_params: Optional dictionary of fixed parameters to always include.
                     Useful for subcommands (e.g., target="viewport").
        exclude_params: Optional list of CLI param names to exclude from URL.

    Example:
        @click.command()
        @url_scheme("md-link")
        @click.option("--json", "output_json", is_flag=True)
        def md_link(output_json):
            ...

        # Now supports:
        # inspekt md-link --get-url  →  inspekt://md-link

        # For subcommands with fixed parameters:
        @screenshot.command(name="viewport")
        @url_scheme("screenshot", extra_params={"target": "viewport"})
        def screenshot_viewport():
            ...

        # inspekt screenshot viewport --get-url  →  inspekt://screenshot?target=viewport
    """
    param_map = param_map or {}
    defaults = defaults or {}
    extra_params = extra_params or {}
    exclude_params = exclude_params or []

    # Available output modes with descriptions
    OUTPUT_MODES = {
        "clipboard": "copy to clipboard",
        "notification": "show macOS notification",
        "dialog": "show in dialog window",
        "both": "copy to clipboard + notification",
        "silent": "no output, errors only",
    }

    def decorator(f: Callable) -> Callable:
        @click.option(
            "--get-url",
            "get_url",
            is_flag=True,
            help="Output the inspekt:// URL instead of executing",
        )
        @functools.wraps(f)
        def wrapper(*args, get_url: bool = False, **kwargs) -> Any:
            if get_url:
                # Start with extra_params (fixed params like target=viewport)
                url_params = dict(extra_params)

                # Map CLI option names to URL parameter names
                for cli_name, value in kwargs.items():
                    # Skip excluded parameters
                    if cli_name in exclude_params:
                        continue

                    # Use mapping if exists, otherwise use CLI name directly
                    url_name = param_map.get(cli_name, cli_name)
                    url_params[url_name] = value

                # Get default output mode and allowed modes from registry
                default_output_mode = "clipboard"
                allowed_output_modes = None  # None means all allowed
                try:
                    from inspekt.core.commands import register_all_commands
                    from inspekt.core.registry import get_registry

                    register_all_commands()
                    registry = get_registry()
                    cmd_def = registry.get_by_url_scheme(scheme_name)
                    if cmd_def:
                        default_output_mode = cmd_def.url_scheme_output_mode
                        allowed_output_modes = cmd_def.url_scheme_allowed_output_modes
                except Exception:
                    pass  # Fall back to clipboard if registry lookup fails

                # Override: when --speak is used, default to silent
                # (you want to hear the audio, not see dialogs)
                if url_params.get("speak"):
                    default_output_mode = "silent"

                # Build base URL (without output mode)
                base_url = build_inspekt_url(scheme_name, url_params, defaults)

                # Filter output modes to only show allowed ones
                if allowed_output_modes:
                    active_modes = {k: v for k, v in OUTPUT_MODES.items() if k in allowed_output_modes}
                else:
                    active_modes = OUTPUT_MODES

                # Display header
                click.echo()
                click.secho("URL schemes for automation", bold=True)
                click.echo()

                # First show base URL with default behavior explanation
                default_desc = active_modes.get(default_output_mode, default_output_mode)
                click.echo(f"  {make_url_link(base_url)}", nl=False)
                click.secho(f" ({default_desc})", fg="bright_black")

                # Show output mode variants (only allowed ones)
                for mode, description in active_modes.items():
                    # Build URL with this output mode
                    if "?" in base_url:
                        url_with_mode = f"{base_url}&output={mode}"
                    else:
                        url_with_mode = f"{base_url}?output={mode}"

                    # Show with description
                    click.echo(f"  {make_url_link(url_with_mode)}", nl=False)
                    if mode == default_output_mode:
                        click.secho(f" ({description}, default)", fg="bright_black")
                    else:
                        click.secho(f" ({description})", fg="bright_black")

                # Show hints at bottom
                click.echo()
                print_hint("Use with Raycast, Alfred, Apple Shortcuts, shell scripts, or any tool that supports custom URL schemes.")
                if "?" in base_url:
                    jq_example = f"{base_url}&jq=.fieldname"
                else:
                    jq_example = f"{base_url}?jq=.fieldname"
                print_hint(f"Add `jq` parameter for JSON transformation, e.g. `{jq_example}`")
                click.echo()

                return None

            # Normal execution
            return f(*args, **kwargs)

        return wrapper

    return decorator


def print_url_scheme_help(scheme_name: str | None = None) -> None:
    """
    Print help information about URL scheme support.

    Args:
        scheme_name: If provided, show help for specific scheme.
                    Otherwise, list all available schemes.
    """
    from inspekt.core.registry import get_registry

    registry = get_registry()
    url_commands = list(registry.get_for_url_scheme())

    if not url_commands:
        click.secho("No commands with URL scheme support found.", fg="yellow", err=True)
        return

    if scheme_name:
        # Find specific command
        cmd = None
        for c in url_commands:
            if c.url_scheme == scheme_name:
                cmd = c
                break

        if not cmd:
            click.secho(f"No command found with URL scheme '{scheme_name}'", fg="red", err=True)
            return

        click.echo(f"\nURL Scheme: inspekt://{cmd.url_scheme}")
        click.echo(f"Command: {cmd.cli_name or cmd.id}")
        click.echo(f"Description: {cmd.description.split('.')[0]}.")

        if cmd.url_scheme_params:
            click.echo("\nParameters:")
            for param, desc in cmd.url_scheme_params.items():
                click.echo(f"  {param}: {desc}")

        if cmd.url_scheme_examples:
            click.echo("\nExamples:")
            for example in cmd.url_scheme_examples:
                click.echo(f"  {example}")
    else:
        # List all URL schemes
        click.echo("\nAvailable URL Schemes:")
        click.echo("=" * 40)

        for cmd in sorted(url_commands, key=lambda c: c.url_scheme or ""):
            click.echo(f"  inspekt://{cmd.url_scheme}")
