"""
`inspekt man` command group.

Manages on-disk UNIX man pages for Inspekt. The build step (regenerating from
the live CLI + CommandRegistry) requires `pandoc` and the source checkout;
the install/uninstall/path/status steps work from any installed copy by
reading the pre-built `.1`/`.7` files shipped in `inspekt/man/`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from inspekt import __version__

SHIPPED_PACKAGE = "inspekt"
SHIPPED_SUBDIR = "man"
DEFAULT_USER_MAN = Path.home() / ".local" / "share" / "man"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _shipped_man_dir() -> Path | None:
    """Return the on-disk directory holding the shipped `.1` / `.7` files."""
    try:
        from importlib.resources import files
    except ImportError:  # Python <3.9
        return None
    try:
        root = files(SHIPPED_PACKAGE) / SHIPPED_SUBDIR
    except (FileNotFoundError, ModuleNotFoundError):
        return None
    if not root.is_dir():
        return None
    return Path(str(root))


def _shipped_pages() -> list[Path]:
    src = _shipped_man_dir()
    if src is None:
        return []
    return sorted(p for p in src.iterdir() if p.suffix in {".1", ".7"})


def _system_man_dir() -> Path:
    """Pick a sensible system man root."""
    if shutil.which("brew"):
        try:
            prefix = subprocess.check_output(
                ["brew", "--prefix"], text=True, stderr=subprocess.DEVNULL
            ).strip()
            if prefix:
                return Path(prefix) / "share" / "man"
        except subprocess.CalledProcessError:
            pass
    return Path("/usr/local/share/man")


def _resolve_target_root(scope: str) -> Path:
    return DEFAULT_USER_MAN if scope == "user" else _system_man_dir()


def _section_dir(root: Path, section: str) -> Path:
    return root / f"man{section}"


def _install_one(src: Path, root: Path) -> Path:
    """Copy a single man page to the right `manN/` subdir; return target path."""
    section = src.suffix.lstrip(".")
    target_dir = _section_dir(root, section)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / src.name
    shutil.copy2(src, target)
    return target


def _is_on_manpath(root: Path) -> bool:
    """Best-effort check: is `root` discoverable by `man`?"""
    try:
        out = subprocess.check_output(["manpath"], text=True, stderr=subprocess.DEVNULL)
        return str(root) in out.split(":")
    except (FileNotFoundError, subprocess.CalledProcessError):
        manpath_env = os.environ.get("MANPATH", "")
        return str(root) in manpath_env.split(":")


def _installed_pages(root: Path) -> list[Path]:
    pages: list[Path] = []
    for section in ("1", "7"):
        d = _section_dir(root, section)
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.name.startswith("inspekt") and p.suffix == f".{section}":
                pages.append(p)
    return sorted(pages)


# ---------------------------------------------------------------------------
# Group + commands
# ---------------------------------------------------------------------------


@click.group()
def man():
    """Manage Inspekt man pages.

    \b
    Examples:
        inspekt man install            # install user-level pages
        inspekt man rebuild            # personalize plugins page
        inspekt man path               # show install location
        inspekt man status             # show installed pages

    Generation requires pandoc and the source checkout; install/uninstall
    work from any pip- or Homebrew-installed copy.
    """


@man.command("build")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Where to write generated files (default: build/man/ in the repo).",
)
@click.option(
    "--no-per-command",
    is_flag=True,
    help="Only build inspekt(1) and inspekt-plugins(7); skip per-command pages.",
)
@click.option(
    "--include-plugins",
    is_flag=True,
    help="Embed the current user's plugins into inspekt-plugins(7).",
)
@click.option(
    "--commit-to-package",
    is_flag=True,
    help="Also copy generated files into inspekt/man/ for shipping in the wheel.",
)
def man_build(
    output_dir: Path | None,
    no_per_command: bool,
    include_plugins: bool,
    commit_to_package: bool,
):
    """Regenerate man pages from the live CLI and registry.

    Requires pandoc and the source checkout. Most users do not need this -
    pre-built pages are shipped with Inspekt and exposed via `inspekt man
    install`. Use `man build` if you are developing Inspekt itself or
    customizing the Markdown sources in docs/man/.
    """
    from inspekt.app.cli.table import print_error, print_hint

    repo_root = _find_repo_root()
    if repo_root is None:
        print_error(
            "Cannot find scripts/build_man.py. `inspekt man build` only works "
            "from a source checkout."
        )
        print_hint("Use `inspekt man install` to install the shipped pages instead.")
        sys.exit(1)

    cmd = [sys.executable, str(repo_root / "scripts" / "build_man.py")]
    if output_dir:
        cmd += ["--output-dir", str(output_dir)]
    if no_per_command:
        cmd += ["--no-per-command"]
    if include_plugins:
        cmd += ["--include-plugins"]
    if commit_to_package:
        cmd += ["--commit-to-package"]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


@man.command("install")
@click.option(
    "--user/--system",
    "user_scope",
    default=True,
    help="Install for the current user (default) or system-wide.",
)
def man_install(user_scope: bool):
    """Copy shipped man pages into a directory on MANPATH.

    Default scope is `--user` (writes to ~/.local/share/man). Use
    `--system` to install under Homebrew's prefix (or /usr/local/share/man),
    which may require sudo.
    """
    from inspekt.app.cli.icons import get_status_icon
    from inspekt.app.cli.table import print_error, print_hint

    pages = _shipped_pages()
    if not pages:
        print_error("No shipped man pages found in this Inspekt installation.")
        print_hint("Run `make build-man` from a source checkout, or update Inspekt.")
        sys.exit(1)

    scope = "user" if user_scope else "system"
    root = _resolve_target_root(scope)

    try:
        root.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print_error(
            f"Permission denied creating {root}. "
            f"Try `sudo inspekt man install --system` or use `--user`."
        )
        sys.exit(1)

    installed: list[Path] = []
    for src in pages:
        try:
            installed.append(_install_one(src, root))
        except PermissionError:
            print_error(f"Permission denied writing to {root}. Try sudo, or `--user`.")
            sys.exit(1)

    click.secho(
        f"{get_status_icon('pass')} Installed {len(installed)} man pages to {root}",
        fg="green",
    )
    if not _is_on_manpath(root):
        print_hint(
            f'{root} is not on your MANPATH. Add it with: `export MANPATH="{root}:$MANPATH"`'
        )
    click.echo("Try: `man inspekt`")


@man.command("uninstall")
@click.option(
    "--user/--system",
    "user_scope",
    default=True,
    help="Uninstall from user (default) or system scope.",
)
def man_uninstall(user_scope: bool):
    """Remove previously installed Inspekt man pages."""
    from inspekt.app.cli.icons import get_status_icon

    scope = "user" if user_scope else "system"
    root = _resolve_target_root(scope)
    pages = _installed_pages(root)
    if not pages:
        click.echo(f"No Inspekt man pages installed at {root}")
        return
    for p in pages:
        try:
            p.unlink()
        except PermissionError:
            click.secho(
                f"Permission denied removing {p}. Try sudo, or `--user`.",
                fg="red",
                err=True,
            )
            sys.exit(1)
    click.secho(
        f"{get_status_icon('pass')} Removed {len(pages)} man pages from {root}",
        fg="green",
    )


@man.command("rebuild")
def man_rebuild():
    """Regenerate inspekt-plugins(7) with this machine's installed plugins.

    Writes the personalized page to ~/.local/share/man/man7/inspekt-plugins.7,
    shadowing the system page when `man` looks it up.
    """
    from inspekt.app.cli.icons import get_status_icon
    from inspekt.app.cli.table import print_error, print_hint

    try:
        from scripts.build_man import (  # type: ignore
            _build_plugins_page,
            convert_to_roff,
            render_markdown,
        )
    except ImportError:
        # Fall back to running the script as a subprocess - works when
        # installed via pip/brew where `scripts/` is not importable.
        repo_root = _find_repo_root()
        if repo_root is None:
            print_error(
                "Cannot regenerate the plugins page from an installed copy yet. "
                "Run from a source checkout, or install pandoc and the inspekt "
                "source tree."
            )
            print_hint(
                "This will be supported in a future release; for now `inspekt "
                "plugin list` shows your plugins."
            )
            sys.exit(1)
        cmd = [
            sys.executable,
            str(repo_root / "scripts" / "build_man.py"),
            "--no-per-command",
            "--include-plugins",
            "--output-dir",
            str(Path.home() / ".local" / "state" / "inspekt" / "man"),
        ]
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as exc:
            sys.exit(exc.returncode)
        regenerated_dir = Path.home() / ".local" / "state" / "inspekt" / "man"
        src = regenerated_dir / "inspekt-plugins.7"
    else:
        import datetime as _dt
        import tempfile

        page = _build_plugins_page(
            version=__version__,
            build_date=_dt.date.today().isoformat(),
            include_plugins=True,
        )
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            md_dir = tmp_path / "md"
            render_markdown([page], md_dir)
            convert_to_roff(md_dir, tmp_path)
            src = tmp_path / "inspekt-plugins.7"
            target = _section_dir(DEFAULT_USER_MAN, "7") / "inspekt-plugins.7"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            click.secho(
                f"{get_status_icon('pass')} Wrote personalized inspekt-plugins(7) to {target}",
                fg="green",
            )
            return

    target = _section_dir(DEFAULT_USER_MAN, "7") / "inspekt-plugins.7"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    click.secho(
        f"{get_status_icon('pass')} Wrote personalized inspekt-plugins(7) to {target}",
        fg="green",
    )


@man.command("path")
@click.option(
    "--user/--system",
    "user_scope",
    default=True,
    help="Show user (default) or system path.",
)
def man_path(user_scope: bool):
    """Print where `inspekt man install` writes (or would write) man pages."""
    scope = "user" if user_scope else "system"
    root = _resolve_target_root(scope)
    click.echo(str(root))
    if not _is_on_manpath(root):
        click.secho(
            f"warning: {root} is not on your MANPATH",
            fg="yellow",
            err=True,
        )


@man.command("status")
def man_status():
    """Show whether man pages are installed and how they compare to this version."""
    from inspekt.app.cli.icons import get_indicator, get_status_icon
    from inspekt.app.cli.table import Table, format_status_icon

    shipped = _shipped_pages()
    user_root = DEFAULT_USER_MAN
    sys_root = _system_man_dir()
    user_pages = _installed_pages(user_root)
    sys_pages = _installed_pages(sys_root)

    click.echo()
    table = Table(
        ["Property", "Value"],
        title="Inspekt man pages",
        icon=get_indicator("info_circle"),
    )

    if shipped:
        shipped_status = f"{format_status_icon('pass')} " + click.style(
            f"{len(shipped)} pages", fg="green"
        )
    else:
        shipped_status = f"{format_status_icon('warning')} " + click.style(
            "none (not built)", fg="yellow"
        )

    user_status = _scope_status(user_pages, user_root)
    sys_status = _scope_status(sys_pages, sys_root)

    rows = [
        ["Inspekt version", __version__],
        ["Shipped", shipped_status],
        ["User scope", user_status],
        ["System scope", sys_status],
    ]
    table.set_data(rows)
    table.print_header(skip_column_headers=True)
    for row in rows:
        table.print_row(row)
    table.print_footer()

    if not user_pages and not sys_pages and shipped:
        click.echo()
        click.echo("  Install with: " + click.style("inspekt man install", fg="cyan"))
    elif user_pages or sys_pages:
        click.echo()
        click.echo(f"  {get_status_icon('info')} Try: " + click.style("man inspekt", fg="cyan"))


def _scope_status(pages: list[Path], root: Path) -> str:
    from inspekt.app.cli.table import format_status_icon

    if not pages:
        return f"{format_status_icon('warning')} " + click.style("not installed", fg="yellow")
    on_path = _is_on_manpath(root)
    extra = "" if on_path else " (not on MANPATH)"
    return f"{format_status_icon('pass')} " + click.style(
        f"{len(pages)} pages at {root}{extra}", fg="green"
    )


def _find_repo_root() -> Path | None:
    """Walk up from this file looking for scripts/build_man.py."""
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "scripts" / "build_man.py"
        if candidate.exists():
            return parent
    return None


__all__ = ["man"]
