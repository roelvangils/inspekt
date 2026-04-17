#!/usr/bin/env python3
"""
Generate Inspekt man pages from the live CLI and CommandRegistry.

Usage:
    python scripts/build_man.py [--output-dir DIR] [--no-per-command]
                                [--include-plugins] [--md-only]

Pipeline:
    Click CLI tree + CommandRegistry  ->  Jinja2 templates in docs/man/
                                      ->  intermediate .md in OUTDIR/md/
                                      ->  pandoc -t man  ->  OUTDIR/*.1, *.7

End users never run this; they use the pre-built files shipped in the wheel.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / "docs" / "man"
DEFAULT_OUTPUT = REPO_ROOT / "build" / "man"
COMMITTED_OUTPUT = REPO_ROOT / "inspekt" / "man"


# ---------------------------------------------------------------------------
# Page data
# ---------------------------------------------------------------------------


@dataclass
class Page:
    """A single man page to write out."""

    slug: str  # filename stem, e.g. "inspekt-axe"
    section: int  # 1 for commands, 7 for overviews
    template: str  # Jinja2 template name relative to TEMPLATE_DIR
    context: dict[str, Any]

    @property
    def md_filename(self) -> str:
        return f"{self.slug}.{self.section}.md"

    @property
    def out_filename(self) -> str:
        return f"{self.slug}.{self.section}"


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def collect_pages(args: argparse.Namespace) -> list[Page]:
    """Build the list of Page objects from the live CLI + registry."""
    # Always document everything - even commands hidden by VM restricted mode.
    os.environ.pop("INSPEKT_RESTRICTED", None)

    from inspekt import __version__
    from inspekt.app.cli import cli
    from inspekt.core.commands import register_all_commands
    from inspekt.core.cli_introspection import get_all_cli_commands_detailed
    from inspekt.core.registry import get_registry

    register_all_commands()
    registry = get_registry()
    by_cli_name: dict[str, Any] = {}
    for cmd in registry.get_all():
        by_cli_name[cmd.get_cli_name()] = cmd

    cli_tree = get_all_cli_commands_detailed(cli)
    top_level = {
        name: meta for name, meta in cli_tree.items() if "." not in name
    }

    version = __version__
    build_date = _dt.date.today().isoformat()

    missing_from_registry: list[str] = []

    grouped = _group_top_level(top_level, by_cli_name)
    main_page = _build_main_page(
        cli=cli,
        version=version,
        build_date=build_date,
        grouped=grouped,
    )
    pages: list[Page] = [main_page]

    if not args.no_per_command:
        for name in sorted(top_level):
            meta = top_level[name]
            if meta.get("hidden"):
                continue
            cmd_def = by_cli_name.get(name)
            if cmd_def is None:
                missing_from_registry.append(name)
            override = _read_optional_override(name)
            related = _related_for(name, top_level)
            pages.append(
                _build_command_page(
                    name=name,
                    meta=meta,
                    cli_tree=cli_tree,
                    cmd_def=cmd_def,
                    registry=registry,
                    override=override,
                    related=related,
                    version=version,
                    build_date=build_date,
                )
            )

    pages.append(
        _build_plugins_page(
            version=version,
            build_date=build_date,
            include_plugins=args.include_plugins,
        )
    )

    if missing_from_registry and args.warn_missing:
        sys.stderr.write(
            "warning: %d CLI commands have no CommandRegistry entry: %s\n"
            % (len(missing_from_registry), ", ".join(missing_from_registry))
        )

    return pages


def _group_top_level(
    top_level: dict[str, dict],
    by_cli_name: dict[str, Any],
) -> dict[str, list[dict]]:
    """Return {category_label: [entry, ...]} sorted by category display order."""
    from inspekt.core.commands.base import CATEGORY_ORDER

    other_label = "Other commands"
    buckets: dict[str, list[dict]] = {}

    for name in sorted(top_level):
        meta = top_level[name]
        if meta.get("hidden"):
            continue
        cmd_def = by_cli_name.get(name)
        if cmd_def is not None:
            label = cmd_def.category.value
        else:
            label = other_label
        entry = {
            "name": name,
            "short_help": _effective_short_help(meta, cmd_def),
        }
        buckets.setdefault(label, []).append(entry)

    ordered: dict[str, list[dict]] = {}
    for cat in CATEGORY_ORDER:
        if cat.value in buckets:
            ordered[cat.value] = buckets.pop(cat.value)
    for remaining in sorted(buckets):
        ordered[remaining] = buckets[remaining]
    return ordered


def _effective_short_help(meta: dict, cmd_def: Any) -> str:
    if cmd_def is not None and cmd_def.description:
        return _first_sentence(cmd_def.description)
    return meta.get("short_help", "") or ""


def _first_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    # Restrict to the first paragraph so we don't pull a sentence from a
    # later one when the first paragraph happens to be a single sentence
    # without a trailing space (e.g. "...page.\n\nAnalyzes...").
    first_para = text.split("\n\n", 1)[0].strip()
    for sep in (". ", ".\n"):
        idx = first_para.find(sep)
        if idx != -1:
            return first_para[: idx + 1].strip()
    # No sentence break inside the first paragraph - collapse internal
    # newlines so the NAME line is one line.
    return " ".join(first_para.split())


# ---------------------------------------------------------------------------
# Page builders
# ---------------------------------------------------------------------------


def _build_main_page(
    *,
    cli: Any,
    version: str,
    build_date: str,
    grouped: dict[str, list[dict]],
) -> Page:
    import click

    global_opts = [p for p in cli.params if isinstance(p, click.Option) and not p.hidden]
    return Page(
        slug="inspekt",
        section=1,
        template="inspekt.1.md",
        context={
            "version": version,
            "build_date": build_date,
            "global_options": _render_options_table(global_opts),
            "commands_by_category": _render_commands_by_category(grouped),
        },
    )


def _build_command_page(
    *,
    name: str,
    meta: dict,
    cli_tree: dict[str, dict],
    cmd_def: Any,
    registry: Any,
    override: str | None,
    related: list[str],
    version: str,
    build_date: str,
) -> Page:
    description = _render_description(meta, cmd_def, registry)
    aliases = list(getattr(cmd_def, "cli_aliases", []) or []) if cmd_def else []

    arguments_section = _render_arguments_table(meta.get("arguments", []))
    options_section = _render_command_options_table(meta.get("options", []))

    if meta.get("is_group"):
        subcommands_section = _render_subcommands(name, cli_tree)
        synopsis = _format_group_synopsis(name)
    else:
        subcommands_section = ""
        synopsis = _format_command_synopsis(name, meta)

    examples = _collect_examples(meta, cmd_def, registry)
    examples_section = _render_examples(examples)

    short_help = _effective_short_help(meta, cmd_def)

    return Page(
        slug=f"inspekt-{name}",
        section=1,
        template="_command.1.md.j2",
        context={
            "version": version,
            "build_date": build_date,
            "name": name,
            "short_help": short_help,
            "synopsis": synopsis,
            "description": description,
            "aliases": aliases,
            "arguments_section": arguments_section,
            "options_section": options_section,
            "subcommands_section": subcommands_section,
            "examples_section": examples_section,
            "override": override or "",
            "related": related,
        },
    )


def _related_for(name: str, top_level: dict[str, dict]) -> list[str]:
    """A handful of cross-references for the SEE ALSO footer."""
    related_map = {
        "open": ["back", "forward", "reload"],
        "back": ["open", "forward"],
        "forward": ["open", "back"],
        "click": ["type", "press", "wait"],
        "type": ["paste", "press", "click"],
        "paste": ["type", "press"],
        "press": ["type", "click"],
        "screenshot": ["save"],
        "axe": ["a11y", "ibm", "autocomplete"],
        "ibm": ["axe", "a11y"],
        "a11y": ["axe", "ibm"],
        "record": ["replay"],
        "replay": ["record"],
        "ask": ["describe", "summarize"],
        "describe": ["ask", "summarize"],
        "summarize": ["ask", "describe"],
        "extract": ["links", "outline"],
        "plugin": [],
        "vm": [],
        "mcp": ["plugin"],
    }
    return [r for r in related_map.get(name, []) if r in top_level]


def _build_plugins_page(
    *,
    version: str,
    build_date: str,
    include_plugins: bool,
) -> Page:
    installed_plugins = ""
    if include_plugins:
        installed_plugins = _render_installed_plugins()
    return Page(
        slug="inspekt-plugins",
        section=7,
        template="inspekt-plugins.7.md",
        context={
            "version": version,
            "build_date": build_date,
            "installed_plugins": installed_plugins,
        },
    )


def _render_installed_plugins() -> str:
    """Return a Markdown definition list of the user's installed plugins."""
    try:
        from inspekt.services.plugin_service import PluginService
    except Exception as exc:  # noqa: BLE001
        return f"*(could not load plugin service: {exc})*"
    try:
        plugins = PluginService().list_plugins()
    except Exception as exc:  # noqa: BLE001
        return f"*(no plugins available: {exc})*"
    if not plugins:
        return "*(no plugins installed)*"

    lines: list[str] = []
    for p in sorted(plugins, key=lambda r: r.get("name", "").lower()):
        name = p.get("name", "?")
        plugin_id = p.get("id", "?")
        category = p.get("category") or "uncategorized"
        autorun = "yes" if p.get("autorun") else "no"
        mcp = "yes" if p.get("mcp_exposed") else "no"
        desc = (p.get("description") or "").strip() or "*(no description)*"
        lines.append(f"**{name}** (`{plugin_id}`)")
        lines.append(
            f":   {desc}  "
            f"\n    *Category:* {category} · *Autorun:* {autorun} · *MCP:* {mcp}"
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Markdown rendering helpers
# ---------------------------------------------------------------------------


def _render_options_table(options: list[Any]) -> str:
    """Render a definition list of Click Option objects (for global options)."""
    if not options:
        return "*(none)*"
    lines: list[str] = []
    for opt in options:
        lines.extend(_format_option_block(_describe_click_option(opt)))
    return "\n".join(lines).rstrip() + "\n"


def _describe_click_option(opt: Any) -> dict:
    """Mirror inspekt.core.cli_introspection._describe_option for raw Click Options."""
    long_name = None
    short_name = None
    for o in opt.opts:
        if o.startswith("--"):
            long_name = o
        elif o.startswith("-") and len(o) == 2:
            short_name = o
    return {
        "name": long_name or (opt.opts[0] if opt.opts else opt.name),
        "short": short_name,
        "secondary": None,
        "type": "FLAG" if opt.is_flag else "TEXT",
        "required": bool(opt.required),
        "default": None,
        "is_flag": bool(opt.is_flag),
        "multiple": bool(getattr(opt, "multiple", False)),
        "help": opt.help or "",
        "metavar": opt.metavar,
    }


def _render_command_options_table(options: list[dict]) -> str:
    if not options:
        return ""
    lines: list[str] = []
    for opt in options:
        lines.extend(_format_option_block(opt))
    return "\n".join(lines).rstrip() + "\n"


def _format_option_block(opt: dict) -> list[str]:
    """Produce a `term\n: description` block for one option."""
    parts: list[str] = []
    if opt.get("short"):
        parts.append(f"**{opt['short']}**")
    if opt.get("name"):
        parts.append(f"**{opt['name']}**")

    type_label = opt.get("type", "TEXT")
    if not opt.get("is_flag"):
        metavar = opt.get("metavar") or type_label
        parts.append(f"*{metavar}*")

    term = ", ".join(parts)
    desc = (opt.get("help") or "").strip() or "*(no description)*"
    extras: list[str] = []
    if opt.get("required"):
        extras.append("required")
    if opt.get("multiple"):
        extras.append("repeatable")
    default = opt.get("default")
    if (
        default not in (None, "", False)
        and not opt.get("is_flag")
        and not _is_sentinel_default(default)
        and "default:" not in desc.lower()
    ):
        extras.append(f"default: `{default}`")
    if extras:
        desc = f"{desc} ({', '.join(extras)})"

    return [term, f":   {desc}", ""]


def _is_sentinel_default(value: Any) -> bool:
    """Detect Click `Sentinel.*` defaults so they don't leak into the docs."""
    if isinstance(value, str) and value.startswith("Sentinel."):
        return True
    return False


def _render_arguments_table(arguments: list[dict]) -> str:
    if not arguments:
        return ""
    lines: list[str] = []
    for arg in arguments:
        metavar = arg.get("metavar") or arg["name"].upper()
        nargs = arg.get("nargs", 1)
        suffix = "..." if nargs == -1 else ""
        required = "required" if arg.get("required") else "optional"
        lines.append(f"*{metavar}*{suffix}")
        lines.append(f":   {required} {arg.get('type', 'TEXT').lower()} argument")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_subcommands(parent_name: str, cli_tree: dict[str, dict]) -> str:
    """List direct subcommands of a Click Group."""
    prefix = f"{parent_name}."
    direct: list[tuple[str, dict]] = []
    for path, meta in cli_tree.items():
        if not path.startswith(prefix):
            continue
        rest = path[len(prefix) :]
        if "." in rest:
            continue  # Skip nested grandchildren - keep page scannable.
        if meta.get("hidden"):
            continue
        direct.append((rest, meta))

    if not direct:
        return ""

    lines: list[str] = []
    for sub_name, meta in sorted(direct):
        short_help = meta.get("short_help") or "*(no description)*"
        lines.append(f"**{sub_name}**")
        lines.append(f":   {short_help}")
        opts = meta.get("options", [])
        if opts:
            opt_summary = ", ".join(
                "**" + (o.get("name") or "") + "**" for o in opts if o.get("name")
            )
            if opt_summary:
                lines.append(f"    *Options:* {opt_summary}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _format_command_synopsis(name: str, meta: dict) -> str:
    parts: list[str] = ["**inspekt**", f"**{name}**"]
    if meta.get("options"):
        parts.append("[*OPTIONS*]")
    for arg in meta.get("arguments", []):
        metavar = arg.get("metavar") or arg["name"].upper()
        nargs = arg.get("nargs", 1)
        suffix = "..." if nargs == -1 else ""
        if arg.get("required"):
            parts.append(f"*{metavar}*{suffix}")
        else:
            parts.append(f"[*{metavar}*{suffix}]")
    return " ".join(parts)


def _format_group_synopsis(name: str) -> str:
    return f"**inspekt** **{name}** [*OPTIONS*] *SUBCOMMAND* [*ARGS*]..."


def _render_description(meta: dict, cmd_def: Any, registry: Any) -> str:
    if cmd_def is not None:
        try:
            text = registry.get_description(cmd_def)
        except Exception:
            text = cmd_def.description
        if text:
            return _normalize_paragraph(text)
    if meta.get("help"):
        return _normalize_paragraph(_strip_examples_section(meta["help"]))
    return "*(no description)*"


def _normalize_paragraph(text: str) -> str:
    """Dedent and collapse excessive blank lines from a docstring."""
    text = textwrap.dedent(text).strip()
    # Replace '\b' marker (Click's no-rewrap signal) with a literal blank line.
    text = text.replace("\b", "")
    # Pandoc only recognizes a Markdown list when there is a blank line
    # before the first item. Insert one when a bullet line follows prose.
    text = _ensure_list_blank_lines(text)
    # Collapse 3+ newlines to 2.
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text


def _ensure_list_blank_lines(text: str) -> str:
    """Insert a blank line before a `- ` list when the previous line is prose."""
    out: list[str] = []
    prev_blank = True
    for line in text.split("\n"):
        stripped = line.lstrip()
        is_bullet = stripped.startswith("- ") or stripped.startswith("* ")
        if is_bullet and not prev_blank and out and not out[-1].lstrip().startswith(("- ", "* ")):
            out.append("")
        out.append(line)
        prev_blank = stripped == ""
    return "\n".join(out)


def _strip_examples_section(text: str) -> str:
    """Remove an Examples: trailing section so we don't double-print examples."""
    import re

    cleaned = re.split(r"\n\s*Examples?:\s*\n", text, maxsplit=1)[0]
    return cleaned.rstrip()


def _collect_examples(meta: dict, cmd_def: Any, registry: Any) -> list[str]:
    examples: list[str] = []
    seen: set[str] = set()
    sources: list[list[str]] = []

    if cmd_def is not None:
        try:
            sources.append(list(registry.get_effective_examples(cmd_def) or []))
        except Exception:
            sources.append(list(cmd_def.examples or []))

    sources.append(list(meta.get("examples") or []))

    for src in sources:
        for ex in src:
            ex = ex.strip()
            if ex and ex not in seen:
                examples.append(ex)
                seen.add(ex)
    return examples


def _render_examples(examples: list[str]) -> str:
    if not examples:
        return ""
    lines: list[str] = []
    for ex in examples:
        lines.append(f"    {ex}")
    return "\n".join(lines) + "\n"


def _render_commands_by_category(grouped: dict[str, list[dict]]) -> str:
    """Build the COMMANDS section of the main page."""
    blocks: list[str] = []
    for category, entries in grouped.items():
        blocks.append(f"## {category}")
        blocks.append("")
        for entry in entries:
            short = entry["short_help"] or "*(no description)*"
            blocks.append(f"**{entry['name']}**")
            blocks.append(f":   {short}")
            blocks.append("")
        blocks.append("")
    return "\n".join(blocks).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Overrides
# ---------------------------------------------------------------------------


def _read_optional_override(name: str) -> str | None:
    path = TEMPLATE_DIR / "overrides" / f"{name}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


# ---------------------------------------------------------------------------
# Rendering and conversion
# ---------------------------------------------------------------------------


def render_markdown(pages: list[Page], md_dir: Path) -> Path:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    md_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(default=False),
        keep_trailing_newline=True,
    )
    for page in pages:
        template = env.get_template(page.template)
        rendered = template.render(**page.context)
        (md_dir / page.md_filename).write_text(rendered, encoding="utf-8")
    return md_dir


def convert_to_roff(md_dir: Path, out_dir: Path) -> None:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        sys.exit(
            "error: pandoc is required to build man pages.\n"
            "       install with `brew install pandoc` (macOS) or `apt install pandoc`."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for md_file in sorted(md_dir.glob("*.md")):
        # Filename pattern: <slug>.<section>.md -> <slug>.<section>
        stem = md_file.name[:-3]  # strip ".md"
        target = out_dir / stem
        subprocess.run(
            [
                pandoc,
                "-s",
                "-f",
                "markdown+pipe_tables+definition_lists+fenced_code_blocks",
                "-t",
                "man",
                "-o",
                str(target),
                str(md_file),
            ],
            check=True,
        )


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else None)
    p.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write generated .md and .1/.7 files (default: build/man/)",
    )
    p.add_argument(
        "--no-per-command",
        action="store_true",
        help="Only write inspekt(1) and inspekt-plugins(7); skip per-command pages.",
    )
    p.add_argument(
        "--include-plugins",
        action="store_true",
        help="Embed an INSTALLED PLUGINS section in inspekt-plugins(7).",
    )
    p.add_argument(
        "--md-only",
        action="store_true",
        help="Render Markdown only; do not invoke pandoc.",
    )
    p.add_argument(
        "--commit-to-package",
        action="store_true",
        help="Also copy generated .1/.7 files to inspekt/man/ for shipping in the wheel.",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress 'wrote N pages' summary.",
    )
    p.add_argument(
        "--no-warn-missing",
        dest="warn_missing",
        action="store_false",
        help="Do not warn about CLI commands missing from the registry.",
    )
    p.set_defaults(warn_missing=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(REPO_ROOT))  # allow running from anywhere
    args = parse_args(argv)
    pages = collect_pages(args)
    md_dir = args.output_dir / "md"
    render_markdown(pages, md_dir)
    if not args.md_only:
        convert_to_roff(md_dir, args.output_dir)
        if args.commit_to_package:
            COMMITTED_OUTPUT.mkdir(parents=True, exist_ok=True)
            for src in args.output_dir.iterdir():
                if src.is_file() and (src.suffix == ".1" or src.suffix == ".7"):
                    shutil.copy2(src, COMMITTED_OUTPUT / src.name)
    if not args.quiet:
        kind = "Markdown files" if args.md_only else "man pages"
        print(f"wrote {len(pages)} {kind} to {args.output_dir}")
        if args.commit_to_package and not args.md_only:
            print(f"also copied .1/.7 files to {COMMITTED_OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
