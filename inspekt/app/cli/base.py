"""
Shared CLI utilities and base classes.

This module provides common functionality used across all CLI command modules:
- Output formatting
- Language detection
- Custom Click group classes
- Common imports and constants
"""

from __future__ import annotations

import difflib
import json
from typing import Any

import click

from inspekt import config as inspekt_config
from inspekt.services.ai_integration import get_ai_service

# Save built-in functions before they get shadowed by Click commands
builtin_open = open
builtin_next = next


def format_output(result: dict[str, Any], format_type: str = "auto") -> str:
    """
    Format execution result for display.

    Args:
        result: Execution result dictionary with 'ok', 'result', 'error' keys
        format_type: Output format - "json", "raw", or "auto" (default)

    Returns:
        Formatted output string
    """
    if not result.get("ok"):
        error = result.get("error", "Unknown error")
        return f"Error: {error}"

    value = result.get("result")

    if format_type == "json":
        return json.dumps(value, indent=2)
    elif format_type == "raw":
        return str(value) if value is not None else ""
    else:  # auto
        if value is None:
            return "undefined"
        elif isinstance(value, str):
            return value
        elif isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        else:
            return str(value)


def get_ai_language(
    language_override: str | None = None,
    page_lang: str | None = None,
) -> str | None:
    """
    Determine the language for AI operations.

    This is a convenience wrapper around AIIntegrationService.get_target_language()
    for backward compatibility with existing code.

    Priority:
    1. language_override (from --language flag)
    2. config.json ai-language setting
    3. If "auto", detect from page_lang
    4. Default to None (let AI decide)

    Args:
        language_override: Language code from CLI flag
        page_lang: Detected page language

    Returns:
        Language code (e.g., "en", "nl", "fr") or None
    """
    ai_service = get_ai_service()
    return ai_service.get_target_language(
        language_override=language_override,
        page_lang=page_lang,
    )


class CustomGroup(click.Group):
    """
    Custom Click Group that shows all command options in help.

    This extends Click's default Group class to provide more detailed help
    output, including options for each subcommand.

    Also supports lazy loading of commands to minimize startup time.
    Commands are only imported when they are actually invoked.
    """

    # Options that need helpful hints when missing arguments
    _rule_options_hints = {
        "--enable-rule": (
            "Option '--enable-rule' requires a rule ID.\n\n"
            "Examples:\n"
            "  inspekt axe --enable-rule color-contrast\n"
            "  inspekt axe --enable-rule color-contrast,label,link-name\n\n"
            "Run 'inspekt axe --list-rules' to see all available rule IDs."
        ),
        "--disable-rule": (
            "Option '--disable-rule' requires a rule ID.\n\n"
            "Examples:\n"
            "  inspekt axe --disable-rule color-contrast\n"
            "  inspekt axe --disable-rule color-contrast,label,link-name\n\n"
            "Run 'inspekt axe --list-rules' to see all available rule IDs."
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lazy_commands = {}

    def main(self, *args, standalone_mode=True, **kwargs):
        """Override main to provide helpful error messages for specific options."""
        try:
            return super().main(*args, standalone_mode=False, **kwargs)
        except click.UsageError as e:
            # Check if this is a "requires an argument" error for our special options
            error_msg = str(e)
            for opt, hint in self._rule_options_hints.items():
                if f"'{opt}' requires an argument" in error_msg:
                    e = click.UsageError(hint)
                    break

            if standalone_mode:
                e.show()
                raise SystemExit(e.exit_code)
            raise
        except click.ClickException as e:
            if standalone_mode:
                e.show()
                raise SystemExit(e.exit_code)
            raise
        except click.Abort:
            if standalone_mode:
                click.echo("Aborted!", err=True)
                raise SystemExit(1)
            raise

    def add_lazy_command(self, name: str, module_path: str, attr: str):
        """
        Register a command for lazy loading.

        Args:
            name: Command name (e.g., "info", "links")
            module_path: Module path relative to inspekt.app.cli (e.g., "util", "extraction")
            attr: Attribute name to load from module (e.g., "info", "links")
        """
        self._lazy_commands[name] = (module_path, attr)

    def get_command(self, ctx: click.Context, cmd_name: str):
        """
        Get a command, loading it lazily if needed.

        This overrides Click's default get_command to support lazy loading.
        Commands registered via add_lazy_command() are only imported when
        they are actually invoked.

        After loading, global options (like --no-tips) are injected into
        the command so they work in any position. See _inject_global_options().
        """
        # Check if it's a lazy command
        if cmd_name in self._lazy_commands:
            module_path, attr = self._lazy_commands[cmd_name]

            # Import the module and get the command
            import importlib
            module = importlib.import_module(f"inspekt.app.cli.{module_path}")
            cmd = getattr(module, attr)

            # Cache it in the commands dict for future access
            self.commands[cmd_name] = cmd
            self._inject_global_options(cmd)
            return cmd

        # Fall back to default behavior
        cmd = super().get_command(ctx, cmd_name)
        if cmd is not None:
            self._inject_global_options(cmd)
        return cmd

    @staticmethod
    def _inject_global_options(cmd):
        """Inject global options into every command so they work in any position.

        Click only allows group-level options BEFORE the subcommand name:

            inspekt --no-tips sitemap    ← works (group option)
            inspekt sitemap --no-tips    ← would fail without this

        Users naturally put flags after the subcommand, so we inject shared
        options into every command at load time. Each option uses:
        - is_eager=True:       fires before the command's own logic
        - expose_value=False:  doesn't add a parameter to the command function
        - callback:            sets an env var that the feature checks at runtime

        This is the single place where global options are defined for injection.
        The same options are also on the top-level `cli` group (in __init__.py)
        so they appear in `inspekt --help` too.

        To add a new global option: define it here AND on the cli group.
        """
        # Avoid duplicates if command is loaded multiple times
        existing_names = {opt.name for opt in cmd.params if isinstance(opt, click.Option)}
        if "no_tips" in existing_names:
            return

        from inspekt.app.cli import _no_tips_callback
        opt = click.Option(
            ['--no-tips'], is_flag=True, is_eager=True, expose_value=False,
            callback=_no_tips_callback, hidden=True,
        )
        cmd.params.append(opt)

        # Recurse into subcommands of groups (e.g. `inspekt sr walk --no-tips`)
        if isinstance(cmd, click.Group):
            for sub_cmd in cmd.commands.values():
                CustomGroup._inject_global_options(sub_cmd)

    def resolve_command(self, ctx: click.Context, args: list[str]):
        """
        Resolve command with fuzzy matching suggestions.

        If command is not found, suggest similar commands using difflib.
        """
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError as e:
            # Check if it's a "No such command" error
            if "No such command" in str(e) and args:
                cmd_name = args[0]
                all_commands = self.list_commands(ctx)

                # Find close matches (cutoff 0.4 = 40% similarity)
                suggestions = difflib.get_close_matches(
                    cmd_name, all_commands, n=3, cutoff=0.4
                )

                if suggestions:
                    suggestion_text = ", ".join(f"'{s}'" for s in suggestions)
                    raise click.UsageError(
                        f"No such command '{cmd_name}'. Did you mean: {suggestion_text}?"
                    )
            raise

    def list_commands(self, ctx: click.Context):
        """
        List all available commands including lazy ones.

        This ensures that lazy commands appear in help output
        without being loaded.
        """
        # Get regular commands
        regular_commands = list(self.commands.keys())

        # Get lazy commands
        lazy_commands = list(self._lazy_commands.keys())

        # Combine and sort
        all_commands = sorted(set(regular_commands + lazy_commands))
        return all_commands

    def format_help(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        """Format the complete help output."""
        self.format_usage(ctx, formatter)
        self.format_help_text(ctx, formatter)
        self.format_options(ctx, formatter)
        self.format_commands_with_options(ctx, formatter)
        self.format_epilog(ctx, formatter)

    def format_commands_with_options(
        self,
        ctx: click.Context,
        formatter: click.HelpFormatter,
    ) -> None:
        """
        List all commands with their options.

        This provides a more detailed view than the default Click help,
        showing options for each subcommand in the main help output.
        """
        commands = self.list_commands(ctx)

        if len(commands):
            formatter.write_paragraph()
            formatter.write_text("Commands:")
            formatter.write_paragraph()

            for subcommand in commands:
                cmd = self.get_command(ctx, subcommand)
                if cmd is None:
                    continue

                # Write command name and description
                help_text = cmd.get_short_help_str(limit=80)
                formatter.write_text(f"  {subcommand}")
                if help_text:
                    formatter.write_text(f"    {help_text}")

                # Write command options (skip hidden ones like injected --no-tips)
                params = [p for p in cmd.params if isinstance(p, click.Option) and not p.hidden]
                if params:
                    for param in params:
                        opts = ", ".join(param.opts)
                        param_help = param.help or ""
                        default = ""
                        if param.default is not None and not isinstance(param.default, bool):
                            default = f" [default: {param.default}]"
                        formatter.write_text(f"      {opts}  {param_help}{default}")

                formatter.write_paragraph()
