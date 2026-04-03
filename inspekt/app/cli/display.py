"""
Display commands for Inspekt Browser Bridge CLI.

This module provides commands for browser display control:
- zoom: Get/set browser zoom level (in, out, reset, arbitrary %)
- viewport: Get/set browser viewport dimensions
"""

import asyncio
import json
import sys

import click

from inspekt.app.cli.icons import success, error, info, warning
from inspekt.core.schemas.display import VIEWPORT_PRESETS


def _run_async(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def _zoom_label(percentage: int) -> str | None:
    """Get a human-readable label for well-known zoom levels."""
    labels = {
        100: "Default zoom level",
        200: "WCAG 1.4.4 — Resize Text",
        400: "WCAG 1.4.10 — Reflow",
    }
    return labels.get(percentage)


def _viewport_label(width: int) -> str | None:
    """Get a human-readable label for well-known viewport widths."""
    for name, (w, _h, desc) in VIEWPORT_PRESETS.items():
        if w == width:
            return desc
    return None


def _vm_toast(message: str, toast_type: str = "dark") -> None:
    """Show a toast in the Inspekt VM control panel via OSC escape relay."""
    import os
    if os.environ.get("INSPEKT_RESTRICTED") != "1":
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://localhost:8888/toast",
            data=json.dumps({"message": message, "type": toast_type}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=2)
        # Signal control panel terminal handler to fetch and display the toast
        sys.stdout.write("\033]1337;toast\007")
        sys.stdout.flush()
    except Exception:
        pass  # Best-effort


# ============================================================================
# Zoom Command Group
# ============================================================================

class ZoomGroup(click.Group):
    """
    Custom Click Group that handles both numeric arguments and subcommands.

    Allows:
    - `inspekt zoom` → show current zoom level
    - `inspekt zoom 150` → set zoom to 150%
    - `inspekt zoom in` → subcommand: zoom in
    - `inspekt zoom out` → subcommand: zoom out
    - `inspekt zoom reset` → subcommand: zoom reset
    - `inspekt zoom --wcag` → set to 200%
    - `inspekt zoom --reflow` → set to 400%
    """

    def parse_args(self, ctx, args):
        """Check if first arg is numeric; if so, treat as zoom level, not subcommand."""
        if args and not args[0].startswith('-'):
            first = args[0]
            # If it looks numeric, it's a zoom level — not a subcommand
            try:
                float(first)
                # Store the level and remove from args so the group handles it
                ctx.ensure_object(dict)
                ctx.obj['_zoom_level'] = first
                args = args[1:]
            except ValueError:
                pass  # Not numeric — let Click dispatch to subcommand

        return super().parse_args(ctx, args)


@click.group(cls=ZoomGroup, invoke_without_command=True)
@click.option("--wcag", is_flag=True, help="Set zoom to 200% (WCAG 1.4.4 Resize Text)")
@click.option("--reflow", is_flag=True, help="Set zoom to 400% (WCAG 1.4.10 Reflow)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def zoom(ctx, wcag, reflow, as_json):
    """Get or set browser zoom level.

    Without arguments, shows the current zoom level.
    With a number, sets the zoom to that percentage.

    \b
    Examples:
        inspekt zoom              # Show current zoom
        inspekt zoom 150          # Set to 150%
        inspekt zoom in           # Step to next level
        inspekt zoom out          # Step to previous level
        inspekt zoom reset        # Reset to 100%
        inspekt zoom --wcag       # Set to 200% (WCAG 1.4.4)
        inspekt zoom --reflow     # Set to 400% (WCAG 1.4.10)
        inspekt zoom --json       # Output as JSON
    """
    if ctx.invoked_subcommand is not None:
        return

    ctx.ensure_object(dict)
    ctx.obj['_as_json'] = as_json
    level_str = ctx.obj.get('_zoom_level')

    from inspekt.core.schemas.display import ZoomSetParams

    if wcag:
        _set_zoom(ZoomSetParams(level=200), as_json=as_json)
    elif reflow:
        _set_zoom(ZoomSetParams(level=400), as_json=as_json)
    elif level_str:
        try:
            level = int(float(level_str))
        except ValueError:
            click.echo(error(f"Invalid zoom level: {level_str}"), err=True)
            sys.exit(1)
        _set_zoom(ZoomSetParams(level=level), as_json=as_json)
    else:
        _get_zoom(as_json=as_json)


def _get_zoom(as_json: bool = False):
    """Show the current zoom level."""
    from inspekt.core.commands.base import EmptyParams
    from inspekt.core.handlers.display import get_zoom

    result = _run_async(get_zoom(EmptyParams()))
    if not result.success:
        click.echo(error(result.message or "Failed to get zoom level"), err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps({"zoom": result.percentage}))
        return

    label = _zoom_label(result.percentage)
    if label:
        click.echo(f"Current zoom level is {result.percentage}% ({label})")
    else:
        click.echo(f"Current zoom level is {result.percentage}%")


def _print_zoom_result(result, as_json: bool = False):
    """Format and print zoom set result, with optional VM toast."""
    if as_json:
        click.echo(json.dumps({"zoom": result.percentage}))
        return

    label = _zoom_label(result.percentage)
    if result.previous_zoom is not None:
        prev_pct = round(result.previous_zoom * 100)
        msg = f"Zoom: {prev_pct}% → {result.percentage}%"
    else:
        msg = f"Zoom: {result.percentage}%"
    if label:
        msg += f" ({label})"
    click.echo(success(msg))

    toast = f"Zoom: {result.percentage}%"
    if label:
        toast += f" — {label}"
    _vm_toast(toast)


def _set_zoom(params, as_json: bool = False):
    """Execute a zoom set operation and display the result."""
    from inspekt.core.handlers.display import set_zoom

    result = _run_async(set_zoom(params))
    if not result.success:
        click.echo(error(result.message or "Failed to set zoom"), err=True)
        sys.exit(1)
    _print_zoom_result(result, as_json=as_json)


@zoom.command("in")
def zoom_in():
    """Zoom in to the next predefined level.

    Predefined levels: 25%, 33%, 50%, 67%, 75%, 80%, 90%, 100%,
    110%, 125%, 150%, 175%, 200%, 250%, 300%, 400%, 500%.
    """
    from inspekt.core.schemas.display import ZoomSetParams
    _set_zoom(ZoomSetParams(action="in"))


@zoom.command("out")
def zoom_out():
    """Zoom out to the previous predefined level.

    Predefined levels: 25%, 33%, 50%, 67%, 75%, 80%, 90%, 100%,
    110%, 125%, 150%, 175%, 200%, 250%, 300%, 400%, 500%.
    """
    from inspekt.core.schemas.display import ZoomSetParams
    _set_zoom(ZoomSetParams(action="out"))


@zoom.command()
def reset():
    """Reset zoom to 100%."""
    from inspekt.core.schemas.display import ZoomSetParams
    _set_zoom(ZoomSetParams(action="reset"))


# ============================================================================
# Viewport Command Group
# ============================================================================

# Default step size for wider/narrower (in pixels)
VIEWPORT_STEP_DEFAULT = 100


class ViewportGroup(click.Group):
    """
    Custom Click Group that handles numeric arguments alongside subcommands.

    Allows:
    - `inspekt viewport` → show current dimensions
    - `inspekt viewport 1024` → set width to 1024px
    - `inspekt viewport 1024 768` → set width and height
    - `inspekt viewport 1024 auto` → set width, auto-height (VM)
    - `inspekt viewport mobile` → subcommand: preset
    - `inspekt viewport wider` → subcommand: relative adjust
    """

    def parse_args(self, ctx, args):
        """Check if first arg is numeric; if so, consume width (and optional height) before subcommand dispatch."""
        if args and not args[0].startswith('-'):
            first = args[0]
            try:
                int(first)
                # First arg is a number — it's a width value
                ctx.ensure_object(dict)
                ctx.obj['_viewport_width'] = first
                args = args[1:]
                # Check for optional second arg (height or "auto")
                if args and not args[0].startswith('-'):
                    second = args[0]
                    if second.lower() == 'auto':
                        ctx.obj['_viewport_height'] = 'auto'
                        args = args[1:]
                    else:
                        try:
                            int(second)
                            ctx.obj['_viewport_height'] = second
                            args = args[1:]
                        except ValueError:
                            pass  # Not a number or "auto" — leave for subcommand dispatch
            except ValueError:
                pass  # Not numeric — let Click dispatch to subcommand

        return super().parse_args(ctx, args)


@click.group(cls=ViewportGroup, invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def viewport(ctx, as_json):
    """Get or set browser viewport dimensions.

    Without arguments, shows the current viewport size.
    With one number, sets the width (height unchanged).
    With two numbers, sets both width and height.
    Use "auto" as height to fill the available display (VM only).

    \b
    Examples:
        inspekt viewport              # Show current dimensions
        inspekt viewport 1024         # Set width to 1024px
        inspekt viewport 1024 768     # Set width and height
        inspekt viewport 1024 auto    # Set width, auto-height (VM)
        inspekt viewport mobile       # Preset: 375px (iPhone SE)
        inspekt viewport tablet       # Preset: 768px (iPad portrait)
        inspekt viewport desktop      # Preset: 1280px (standard desktop)
        inspekt viewport wide         # Preset: 1920px (Full HD)
        inspekt viewport wider        # Grow width by 100px
        inspekt viewport narrower     # Shrink width by 100px
        inspekt viewport wider 50     # Grow width by 50px
        inspekt viewport --json       # Output as JSON
    """
    if ctx.invoked_subcommand is not None:
        return

    ctx.ensure_object(dict)
    ctx.obj['_as_json'] = as_json
    width_str = ctx.obj.get('_viewport_width')
    height_str = ctx.obj.get('_viewport_height')

    if width_str:
        try:
            width = int(width_str)
        except ValueError:
            click.echo(error(f"Invalid width: {width_str}"), err=True)
            sys.exit(1)

        auto_height = bool(height_str and height_str.lower() == 'auto')
        height = None
        if height_str and not auto_height:
            try:
                height = int(height_str)
            except ValueError:
                click.echo(error(f"Invalid height: {height_str}"), err=True)
                sys.exit(1)

        _set_viewport(width, height, auto_height=auto_height, as_json=as_json)
    else:
        _get_viewport(as_json=as_json)


def _get_viewport(as_json: bool = False):
    """Show the current viewport dimensions."""
    from inspekt.core.commands.base import EmptyParams
    from inspekt.core.handlers.display import get_viewport

    result = _run_async(get_viewport(EmptyParams()))
    if not result.success:
        click.echo(error(result.message or "Failed to get viewport"), err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps({"width": result.width, "height": result.height}))
        return

    label = _viewport_label(result.width)
    if label:
        click.echo(f"Current viewport is {result.width}×{result.height} ({label})")
    else:
        click.echo(f"Current viewport is {result.width}×{result.height}")


def _set_viewport(
    width: int,
    height: int | None = None,
    preset_desc: str | None = None,
    auto_height: bool = False,
    as_json: bool = False,
):
    """Set viewport to specific dimensions."""
    from inspekt.core.handlers.display import set_viewport
    from inspekt.core.schemas.display import ViewportSetParams

    params = ViewportSetParams(width=width, height=height, auto_height=auto_height)
    result = _run_async(set_viewport(params))
    if not result.success:
        click.echo(error(result.message or "Failed to set viewport"), err=True)
        sys.exit(1)

    if as_json:
        click.echo(json.dumps({"width": result.width, "height": result.height}))
        return

    if result.previous_width is not None:
        msg = f"Viewport: {result.previous_width}×{result.previous_height} → {result.width}×{result.height}"
    else:
        msg = f"Viewport: {result.width} × {result.height}"
    desc = preset_desc or _viewport_label(result.width)
    if desc:
        msg += f" ({desc})"
    click.echo(success(msg))

    # VM toast
    _vm_toast(f"Viewport: {result.width} × {result.height}")


def _adjust_viewport(delta: int):
    """Adjust viewport width by a relative amount."""
    from inspekt.core.commands.base import EmptyParams
    from inspekt.core.handlers.display import get_viewport

    # Get current width
    result = _run_async(get_viewport(EmptyParams()))
    if not result.success:
        click.echo(error(result.message or "Failed to get current viewport"), err=True)
        sys.exit(1)

    new_width = max(320, min(3840, result.width + delta))
    if new_width == result.width:
        click.echo(warning(f"Already at {'maximum' if delta > 0 else 'minimum'} width ({result.width}px)"))
        return

    _set_viewport(new_width)


# ── Preset subcommands ─────────────────────────────────────────────────────

@viewport.command()
def mobile():
    """Set viewport to 375px width (iPhone SE / small mobile)."""
    w, h, desc = VIEWPORT_PRESETS["mobile"]
    _set_viewport(w, h, preset_desc=desc)


@viewport.command()
def tablet():
    """Set viewport to 768px width (iPad portrait / tablet)."""
    w, h, desc = VIEWPORT_PRESETS["tablet"]
    _set_viewport(w, h, preset_desc=desc)


@viewport.command()
def desktop():
    """Set viewport to 1280px width (standard desktop)."""
    w, h, desc = VIEWPORT_PRESETS["desktop"]
    _set_viewport(w, h, preset_desc=desc)


@viewport.command()
def wide():
    """Set viewport to 1920px width (Full HD / wide desktop)."""
    w, h, desc = VIEWPORT_PRESETS["wide"]
    _set_viewport(w, h, preset_desc=desc)


# ── Relative adjustment subcommands ────────────────────────────────────────

@viewport.command()
@click.argument("pixels", required=False, default=VIEWPORT_STEP_DEFAULT, type=int)
def wider(pixels):
    """Grow viewport width.

    Increases width by PIXELS (default: 100). Useful for iteratively
    finding responsive breakpoints.

    \b
    Examples:
        inspekt viewport wider        # +100px
        inspekt viewport wider 50     # +50px
        inspekt viewport wider 1      # +1px (fine-tune)
    """
    _adjust_viewport(pixels)


@viewport.command()
@click.argument("pixels", required=False, default=VIEWPORT_STEP_DEFAULT, type=int)
def narrower(pixels):
    """Shrink viewport width.

    Decreases width by PIXELS (default: 100). Useful for iteratively
    finding responsive breakpoints.

    \b
    Examples:
        inspekt viewport narrower        # -100px
        inspekt viewport narrower 50     # -50px
        inspekt viewport narrower 1      # -1px (fine-tune)
    """
    _adjust_viewport(-pixels)


# ── Fit subcommand (VM only) ──────────────────────────────────────────────

@viewport.command()
def fit():
    """Fit viewport to the VNC canvas size (VM only).

    Resizes the X display to match the current VNC container dimensions,
    undoing any manual viewport changes. This restores the 1:1 mapping
    between the VNC canvas and the VM display.

    Only works inside the Inspekt VM.
    """
    from inspekt.core.handlers.display import _is_vm, _vm_request

    if not _is_vm():
        click.echo(error("viewport fit is only available inside the Inspekt VM"), err=True)
        sys.exit(1)

    result = _vm_request("POST", "/fit")

    if result.get("ok"):
        res = result.get("resolution", "")
        if result.get("changed"):
            click.echo(success(f"Viewport fitted to canvas ({res})"))
            _vm_toast(f"Viewport: {res} (fitted to canvas)")
        else:
            click.echo(info(f"Viewport already fits canvas ({res})"))
    else:
        click.echo(error(result.get("error", "Failed to fit viewport")), err=True)
        sys.exit(1)
