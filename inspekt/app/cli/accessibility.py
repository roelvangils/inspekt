"""
Accessibility testing and audit commands.

This module provides commands for testing web accessibility:
- axe: Run axe-core accessibility audit on current page
- autocomplete: Check autocomplete attributes per WCAG 2.1 SC 1.3.5

These commands help identify WCAG violations and accessibility issues.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC
from pathlib import Path

import click

from inspekt.app.cli.base import builtin_open
from inspekt.app.cli.icons import (
    alert,
    bug,
    celebrate,
    error,
    get_icon,
    get_status_icon,
    stopwatch,
    success,
)
from inspekt.app.cli.icons import warning as warn_icon
from inspekt.app.cli.inspection import _print_tips_section
from inspekt.app.cli.output import pluralize
from inspekt.app.cli.table import Table, print_wrapped
from inspekt.client import BridgeClient

# ============================================================================
# Engine Tracking - Prevent Re-injection and Exclude Inspekt UI
# ============================================================================

# Selectors for Inspekt UI elements that should be excluded from a11y scans
INSPEKT_UI_SELECTORS = [
    '[data-inspekt-badge]',
    '[data-inspekt-axe-popover]',
    '[data-inspekt-ibm-popover]',
    '.inspekt-axe-popover',
    '.inspekt-ibm-popover',
    '#inspekt-badge-styles',
    '#inspekt-axe-popover-styles',
    '#inspekt-axe-popover-additional-styles',
    '#inspekt-ibm-popover-styles',
    '#inspekt-ibm-badge-styles',
]


def _load_engine_tracker(client) -> bool:
    """
    Load the engine tracker script if not already loaded.

    This provides window.__inspektIsEngineLoaded__ and related functions
    to prevent re-injecting engine libraries on repeated audits.

    Returns:
        True if tracker is ready, False on error
    """
    tracker_path = Path(__file__).parent.parent.parent / "scripts" / "engine-tracker.js"

    try:
        with builtin_open(tracker_path) as f:
            tracker_script = f.read()

        # Always load the full tracker script to ensure all functions are available
        # (in case page was refreshed or partial load occurred)
        check_and_load = f"""
(function() {{
    {tracker_script}
    return window.__inspektTrackerInitialized__ === true;
}})()
"""
        result = client.execute(check_and_load, timeout=5.0)
        return result.get("ok") and result.get("result") is True
    except Exception:
        return False


def _is_engine_loaded(client, engine: str) -> bool:
    """
    Check if an engine library is already loaded in the browser.

    Args:
        client: Bridge client for browser communication
        engine: Engine identifier (axe, ace, htmlcs, sia)

    Returns:
        True if engine is already loaded, False otherwise
    """
    check_code = f"window.__inspektIsEngineLoaded__ ? window.__inspektIsEngineLoaded__('{engine}') : false"
    try:
        result = client.execute(check_code, timeout=2.0)
        return result.get("ok") and result.get("result")
    except Exception:
        return False


def _mark_engine_loaded(client, engine: str) -> bool:
    """
    Mark an engine as loaded to prevent re-injection.

    Args:
        client: Bridge client for browser communication
        engine: Engine identifier (axe, ace, htmlcs, sia)

    Returns:
        True if successfully marked, False otherwise
    """
    mark_code = f"window.__inspektMarkEngineLoaded__ && window.__inspektMarkEngineLoaded__('{engine}')"
    try:
        result = client.execute(mark_code, timeout=2.0)
        return result.get("ok")
    except Exception:
        return False


def _filter_inspekt_ui_violations(violations: list, selector_key: str = 'selector') -> list:
    """
    Remove violations that occur within Inspekt's own UI elements.

    This is used as a post-filter for engines that don't support exclude options.

    Args:
        violations: List of violation dicts
        selector_key: Key name for the selector field in violation dict

    Returns:
        Filtered list with Inspekt UI violations removed
    """
    filtered = []
    for v in violations:
        selector = v.get(selector_key, '')
        # Handle both string and list selectors
        if isinstance(selector, list):
            selector = ' '.join(str(s) for s in selector)
        else:
            selector = str(selector)

        # Check if this violation is within Inspekt UI
        is_inspekt_ui = any(
            ui_sel.replace('[', '').replace(']', '').replace('.', '').replace('#', '')
            in selector
            for ui_sel in INSPEKT_UI_SELECTORS
        )

        if not is_inspekt_ui:
            filtered.append(v)

    return filtered


# ============================================================================
# Engine Registry for Multi-Engine Accessibility Testing
# ============================================================================

AVAILABLE_ENGINES = {
    "axe": {
        "name": "Axe-core",
        "abbr": "AXE",
        "color": "cyan",
        "description": "Deque's industry-standard accessibility checker",
        "performance": "fast",
    },
    "eac": {
        "name": "Equal Access Checker",
        "abbr": "EAC",
        "color": "magenta",
        "description": "IBM's comprehensive WCAG checker",
        "performance": "slow",
    },
    "hcs": {
        "name": "HTML CodeSniffer",
        "abbr": "HCS",
        "color": "yellow",
        "description": "Pa11y's WCAG 2.1 checker",
        "performance": "medium",
    },
    "sia": {
        "name": "Alfa",
        "abbr": "SIA",
        "color": "blue",
        "description": "ACT-Rules based conformance testing engine",
        "performance": "medium",
    },
}

DEFAULT_ENGINE_ORDER = ["axe", "eac", "hcs", "sia"]


def _validate_and_normalize_engines(engines: str | tuple[str, ...] | None) -> list[str]:
    """
    Validate engine names and return normalized list.

    Args:
        engines: Comma-separated engine string (e.g. "axe,eac"),
                 tuple of engine names, or None for defaults

    Returns:
        List of validated engine names in execution order

    Raises:
        click.UsageError: If an invalid engine name is provided
    """
    if not engines:
        return DEFAULT_ENGINE_ORDER.copy()

    # Support comma-separated string (from --engines option)
    if isinstance(engines, str):
        engine_names = [e.strip() for e in engines.split(",") if e.strip()]
    else:
        engine_names = list(engines)

    if not engine_names:
        return DEFAULT_ENGINE_ORDER.copy()

    normalized = []
    seen = set()

    for engine in engine_names:
        engine_lower = engine.lower()

        if engine_lower not in AVAILABLE_ENGINES:
            available = ", ".join(sorted(AVAILABLE_ENGINES.keys()))
            raise click.UsageError(
                f"Unknown engine '{engine}'. Available: {available}"
            )

        if engine_lower in seen:
            click.echo(
                click.style(
                    f"Warning: Engine '{engine}' specified multiple times, using first occurrence",
                    fg="yellow"
                ),
                err=True
            )
            continue

        seen.add(engine_lower)
        normalized.append(engine_lower)

    return normalized


def _parse_rule_ids(rule_options: tuple[str, ...]) -> list[str]:
    """
    Parse rule IDs from multiple option flags and comma-separated values.

    Supports both formats:
        --disable-rule color-contrast --disable-rule label
        --disable-rule color-contrast,label

    Args:
        rule_options: Tuple of rule ID strings (from multiple flags)

    Returns:
        Flat list of individual rule IDs
    """
    rule_ids = []
    for item in rule_options:
        # Split on commas and strip whitespace
        parts = [r.strip() for r in item.split(',') if r.strip()]
        rule_ids.extend(parts)
    return rule_ids


def _build_axe_config(
    level: str,
    tags: str | None,
    include_passes: bool,
    include_incomplete: bool,
    disable_rules: list[str] | None = None,
    enable_rules: list[str] | None = None
) -> dict:
    """
    Build axe-core configuration object from CLI arguments.

    Args:
        level: WCAG level (2a, 2aa, 2aaa, 21a, 21aa, 22aa)
        tags: Additional comma-separated tags
        include_passes: Whether to include passing checks
        include_incomplete: Whether to include incomplete checks
        disable_rules: List of rule IDs to disable (e.g., ['color-contrast', 'label'])
        enable_rules: List of rule IDs to run exclusively (all others disabled)

    Returns:
        Configuration dict for axe.run()

    Note:
        enable_rules takes precedence over disable_rules if both are specified.
        When enable_rules is set, only those specific rules will run.
    """
    config = {"resultTypes": ["violations"]}

    # Add optional result types
    if include_passes:
        config["resultTypes"].append("passes")
    if include_incomplete:
        config["resultTypes"].append("incomplete")

    # If enable_rules is specified, run ONLY those rules (ignore level/tags)
    if enable_rules:
        config["runOnly"] = {
            "type": "rule",
            "values": enable_rules
        }
        return config

    # Otherwise, use WCAG level-based tags
    level_mapping = {
        "2a": ["wcag2a"],
        "2aa": ["wcag2a", "wcag2aa"],
        "2aaa": ["wcag2a", "wcag2aa", "wcag2aaa"],
        "21a": ["wcag2a", "wcag21a"],
        "21aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        "22aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
    }

    # Get base tags from level
    axe_tags = level_mapping.get(level.lower(), ["wcag2a", "wcag2aa"])

    # Add additional tags if specified
    if tags:
        additional_tags = [tag.strip() for tag in tags.split(",")]
        axe_tags.extend(additional_tags)

    config["runOnly"] = {
        "type": "tag",
        "values": axe_tags
    }

    # Disable specific rules if requested
    if disable_rules:
        config["rules"] = {rule_id: {"enabled": False} for rule_id in disable_rules}

    return config


def _separator_line(fg: str = "bright_black") -> str:
    """
    Create a separator line that spans the terminal width.

    Args:
        fg: Foreground color for the line (default: bright_black)

    Returns:
        Styled separator line
    """
    try:
        terminal_width = click.get_terminal_size()[0]
    except Exception:
        # Fallback to 80 if terminal size cannot be determined
        terminal_width = 80

    return click.style("─" * terminal_width, fg=fg)


def _parse_selectors(selector_list: tuple[str, ...]) -> list[str]:
    """
    Parse selectors from multiple --exclude flags and comma-separated values.

    Args:
        selector_list: Tuple of selector strings (from multiple --exclude flags)

    Returns:
        Flat list of individual selectors
    """
    selectors = []
    for item in selector_list:
        # Split on commas and strip whitespace
        parts = [s.strip() for s in item.split(',') if s.strip()]
        selectors.extend(parts)
    return selectors


def _validate_selectors(client: BridgeClient, selectors: list[str], timeout: float) -> dict[str, dict]:
    """
    Validate CSS selectors by testing them in the browser.

    Args:
        client: Bridge client for executing JavaScript
        selectors: List of CSS selectors to validate
        timeout: Timeout for JavaScript execution

    Returns:
        Dictionary mapping selector to validation result
    """
    if not selectors:
        return {}

    validation_script = f"""
    (function() {{
        const selectors = {json.dumps(selectors)};
        const results = {{}};

        for (const sel of selectors) {{
            try {{
                const elements = document.querySelectorAll(sel);
                results[sel] = {{ valid: true, count: elements.length }};
            }} catch (e) {{
                results[sel] = {{ valid: false, error: e.message }};
            }}
        }}

        return results;
    }})()
    """

    result = client.execute(validation_script, timeout=timeout)

    if not result.get("ok"):
        raise RuntimeError(f"Failed to validate selectors: {result.get('error')}")

    return result.get("result", {})


def _build_axe_context(client: BridgeClient, scoped: str | None, exclude_selectors: list[str], timeout: float, require_panel_selection: bool = False) -> tuple[str, str | None]:
    """
    Build the axe context parameter based on scoped and exclude options.

    Args:
        client: Bridge client for executing JavaScript
        scoped: Scoped value ("inspected" or CSS selectors)
        exclude_selectors: List of selectors to exclude
        timeout: Timeout for JavaScript execution

    Returns:
        Tuple of (context_expression, warning_message)
        - context_expression: JavaScript expression for axe.run() context
        - warning_message: Optional warning message to display to user
    """
    warning = None

    # Handle scoped=inspected
    if scoped and scoped.lower() == "inspected":
        # Check if element is inspected
        check_script = """
        (function() {
            const el = window.__INSPEKT_INSPECTED_ELEMENT__;
            if (!el || el.nodeType !== 1) {
                return { ok: false, error: 'No element inspected' };
            }

            // Get a CSS selector for the element
            function getCSSPath(el) {
                if (el.id) return '#' + el.id;
                if (el === document.body) return 'body';

                let path = [];
                while (el && el.nodeType === 1) {
                    let selector = el.nodeName.toLowerCase();
                    if (el.id) {
                        selector = '#' + el.id;
                        path.unshift(selector);
                        break;
                    } else if (el.className && typeof el.className === 'string') {
                        selector += '.' + el.className.trim().split(/\\s+/).join('.');
                    }
                    path.unshift(selector);
                    el = el.parentElement;
                }
                return path.join(' > ');
            }

            return {
                ok: true,
                selector: getCSSPath(el),
                nodeName: el.nodeName.toLowerCase(),
                selectionSource: window.__INSPEKT_SELECTION_SOURCE__ || 'unknown'
            };
        })()
        """

        result = client.execute(check_script, timeout=timeout)

        if not result.get("ok"):
            raise RuntimeError(f"Failed to check inspected element: {result.get('error')}")

        data = result.get("result", {})
        if not data.get("ok"):
            click.echo("Error: No element inspected. Use the Chrome DevTools inspector or Inspekt panel to select an element first.", err=True)
            sys.exit(1)

        selector = data.get("selector", "unknown")
        node_name = data.get("nodeName", "unknown")
        selection_source = data.get("selectionSource", "unknown")

        # Check if panel selection is required
        if require_panel_selection and selection_source != "panel":
            source_label = {
                "devtools": "Chrome DevTools inspector",
                "unknown": "unknown method"
            }.get(selection_source, selection_source)

            click.echo("Error: Element must be selected using Inspekt panel picker.", err=True)
            click.echo(f"Current selection source: {source_label}", err=True)
            click.echo("", err=True)
            click.echo("To select via Inspekt panel:", err=True)
            click.echo("  1. Open Chrome DevTools (F12)", err=True)
            click.echo("  2. Click on the 'Inspekt' panel tab", err=True)
            click.echo("  3. Click the 'Pick Element' button", err=True)
            click.echo("  4. Click the element you want to test", err=True)
            sys.exit(1)

        # Show selection source confirmation if panel selection was required
        if require_panel_selection:
            click.echo(click.style(success("Element selected via Inspekt panel picker"), fg="green"), err=True)

        # Display scoped element with separator lines
        click.echo("Scoping to inspected element:", err=True)
        click.echo(_separator_line(), err=True)
        click.echo(f"{click.style(node_name, fg='cyan')} ({selector})", err=True)
        click.echo(_separator_line(), err=True)
        click.echo("", err=True)

        # Build context with inspected element
        if exclude_selectors:
            context_expr = json.dumps({
                "include": "window.__INSPEKT_INSPECTED_ELEMENT__",
                "exclude": exclude_selectors
            })
            # Replace the quoted window reference with actual reference
            context_expr = context_expr.replace('"window.__INSPEKT_INSPECTED_ELEMENT__"', 'window.__INSPEKT_INSPECTED_ELEMENT__')
        else:
            context_expr = "window.__INSPEKT_INSPECTED_ELEMENT__"

        warning = "Some rules may show incomplete results when scoped to a single element (e.g., duplicate-id, heading-order, landmark rules)."

    # Handle scoped with CSS selectors
    elif scoped:
        # Parse comma-separated selectors
        scoped_selectors = [s.strip() for s in scoped.split(',') if s.strip()]

        # Validate scoped selectors
        validation = _validate_selectors(client, scoped_selectors, timeout)

        # Check for invalid selectors
        invalid = [sel for sel, info in validation.items() if not info.get("valid")]
        if invalid:
            click.echo("Error: Invalid CSS selectors in --scoped:", err=True)
            for sel in invalid:
                error = validation[sel].get("error", "Unknown error")
                click.echo(f"  - '{sel}': {error}", err=True)
            sys.exit(1)

        # Warn about selectors that match no elements
        empty = [sel for sel, info in validation.items() if info.get("count") == 0]
        if empty:
            click.echo(click.style("Warning:", fg="yellow") + " Some --scoped selectors match no elements:", err=True)
            for sel in empty:
                click.echo(f"  - '{sel}'", err=True)
            click.echo("", err=True)

        # Build context
        if exclude_selectors:
            context_expr = json.dumps({
                "include": scoped_selectors,
                "exclude": exclude_selectors
            })
        else:
            # Single selector can be a string, multiple must be array
            if len(scoped_selectors) == 1:
                context_expr = json.dumps(scoped_selectors[0])
            else:
                context_expr = json.dumps(scoped_selectors)

        # Display scoped selectors with separator lines
        selector_preview = ', '.join(scoped_selectors[:3])
        if len(scoped_selectors) > 3:
            selector_preview += f' (+{len(scoped_selectors) - 3} more)'

        click.echo("Scoping to:", err=True)
        click.echo(_separator_line(), err=True)
        click.echo(click.style(selector_preview, fg='cyan'), err=True)
        click.echo(_separator_line(), err=True)
        click.echo("", err=True)

    # Handle exclude-only (no scoped)
    elif exclude_selectors:
        context_expr = json.dumps({"exclude": exclude_selectors})

        # Display excluded selectors with separator lines
        selector_preview = ', '.join(exclude_selectors[:3])
        if len(exclude_selectors) > 3:
            selector_preview += f' (+{len(exclude_selectors) - 3} more)'

        click.echo("Excluding:", err=True)
        click.echo(_separator_line(), err=True)
        click.echo(click.style(selector_preview, fg='cyan'), err=True)
        click.echo(_separator_line(), err=True)
        click.echo("", err=True)

    # No scoped or exclude
    else:
        context_expr = "document"

    return context_expr, warning


# Table formatting functions moved to inspekt.app.cli.table module


def _get_impact_color(impact: str) -> str:
    """Get color for impact level."""
    colors = {
        "critical": "red",
        "serious": "yellow",
        "moderate": "blue",
        "minor": "bright_black"
    }
    return colors.get(impact, "white")


def _list_available_rules(client: BridgeClient, timeout: float, output_json: bool) -> None:
    """List all available axe-core rules."""
    # Load axe-core library
    axe_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "axe-core.min.js"
    if not axe_lib_path.exists():
        click.echo(f"Error: axe-core library not found: {axe_lib_path}", err=True)
        sys.exit(1)

    # Load the list_axe_rules script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "list_axe_rules.js"
    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        # Read axe-core library
        with builtin_open(axe_lib_path) as f:
            axe_lib = f.read()

        # Read list rules script
        with builtin_open(script_path) as f:
            list_script = f.read()

        # Combine: axe-core library + list script
        script = f"""(async function() {{
    // Load axe-core library
    {axe_lib}

    // List rules
    const result = await {list_script};
    return result;
}})()"""

        # Execute the script
        result = client.execute(script, timeout=timeout)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        data = result.get("result", {})

        if not data.get("ok"):
            click.echo(f"Error fetching rules: {data.get('error')}", err=True)
            sys.exit(1)

        rules = data.get("rules", [])
        stats = data.get("stats", {})

        if output_json:
            # Output as JSON
            from inspekt.app.cli.table import print_json
            print_json(
                {"rules": rules, "stats": stats, "axeVersion": data.get("axeVersion")},
                summary=f"{len(rules)} axe rules",
            )
            return

        # Group rules by WCAG level
        wcag_groups = {
            "wcag2a": [],
            "wcag2aa": [],
            "wcag21aa": [],
            "wcag22aa": [],
            "best-practice": [],
            "other": []
        }

        for rule in rules:
            tags = rule.get("tags", [])
            if "wcag22aa" in tags:
                wcag_groups["wcag22aa"].append(rule)
            elif "wcag21aa" in tags:
                wcag_groups["wcag21aa"].append(rule)
            elif "wcag2aa" in tags:
                wcag_groups["wcag2aa"].append(rule)
            elif "wcag2a" in tags:
                wcag_groups["wcag2a"].append(rule)
            elif "best-practice" in tags:
                wcag_groups["best-practice"].append(rule)
            else:
                wcag_groups["other"].append(rule)

        # Display groups with tables
        group_info = [
            ("wcag2a", "WCAG 2.0 Level A", "2a"),
            ("wcag2aa", "WCAG 2.0 Level AA", "2aa"),
            ("wcag21aa", "WCAG 2.1 Level AA", "21aa"),
            ("wcag22aa", "WCAG 2.2 Level AA", "22aa"),
            ("best-practice", "Best Practice", "best-practice"),
            ("other", "Other", None),
        ]

        click.echo()
        total_shown = 0

        for group_key, group_label, level_flag in group_info:
            group_rules = wcag_groups.get(group_key, [])
            if not group_rules:
                continue

            # Sort rules alphabetically by ID
            group_rules.sort(key=lambda r: r.get("id", ""))

            # Build table data
            rows = []
            for rule in group_rules:
                rule_id = rule.get("id", "")
                description = rule.get("description", "")
                rows.append([rule_id, description])

            # Create table with title showing count and level flag
            title = f"{group_label} ({len(group_rules)} rules)"
            table = Table(
                headers=["Rule ID", "Description"],
                title=title,
            )
            table.set_data(rows)

            # Print table
            table.print_header()
            for row in rows:
                rule_id, description = row
                table.print_row(
                    [rule_id, description],
                    colors=["green", None]
                )
            table.print_footer()

            # Show level flag hint
            if level_flag:
                from inspekt.app.cli.table import _style_with_inline_code
                hint = f"  Use: `inspekt axe --level {level_flag}`" if level_flag != "best-practice" else "  Use: `inspekt axe --tags best-practice`"
                click.echo(_style_with_inline_code(hint, base_fg="bright_black"))

            click.echo()
            total_shown += len(group_rules)

        # Summary
        click.echo(click.style(f"Total: {total_shown} rules (axe-core v{data.get('axeVersion', 'unknown')})", fg="bright_black"))
        click.echo()

        # Show usage hints
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(click.style("Usage Examples:", bold=True))
        click.echo(_style_with_inline_code("  `inspekt axe --rule color-contrast`        ", base_fg="white") + click.style("# Check single rule", fg="bright_black"))
        click.echo(_style_with_inline_code("  `inspekt axe --enable-rule color-contrast` ", base_fg="white") + click.style("# Check only this rule", fg="bright_black"))
        click.echo(_style_with_inline_code("  `inspekt axe --disable-rule label`         ", base_fg="white") + click.style("# Exclude specific rule", fg="bright_black"))
        click.echo()

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _auto_select_element(selector: str, rule_id: str) -> bool:
    """
    Auto-select and highlight an element in the browser.

    Uses the inspection API to store the element and apply visual highlight.
    Silently fails if the API is unavailable.

    Args:
        selector: CSS selector for the element
        rule_id: The Axe rule ID (for logging)

    Returns:
        True if selection succeeded, False otherwise
    """
    try:
        import requests

        # Call the inspection API
        response = requests.post(
            'http://127.0.0.1:8765/api/inspection/inspect',
            json={'selector': selector},
            timeout=5
        )

        if response.ok:
            return True
    except Exception:
        # Silently fail - don't interrupt the main audit output
        pass

    return False


def _format_detailed_violation_output(violations: list[dict], url: str, rule_id: str, no_select: bool = False) -> None:
    """Format violations with detailed information for single-rule checks."""
    if not violations:
        click.echo()
        click.echo(click.style(success(f"No violations found for rule: {rule_id}"), fg="green", bold=True))
        click.echo()
        click.echo(f"Tested: {url}")
        return

    # Should only be one violation (single rule check)
    violation = violations[0]

    # Header
    click.echo()
    click.echo(click.style(f"Rule: {violation.get('id', 'unknown')}", fg="cyan", bold=True))
    click.echo(click.style(f"Impact: {violation.get('impact', 'unknown')}", fg=_get_impact_color(violation.get('impact', 'unknown'))))
    click.echo(f"Help: {violation.get('help', '')}")

    help_url = violation.get('helpUrl', '')
    if help_url:
        click.echo(f"Documentation: {click.style(help_url, fg='blue', underline=True)}")

    click.echo()
    click.echo(click.style(f"Description: {violation.get('description', '')}", dim=True))
    click.echo()

    # Nodes (individual violations)
    nodes = violation.get('nodes', [])
    node_count = len(nodes)

    if node_count == 0:
        click.echo(click.style("No failing elements found.", fg="yellow"))
        return

    violation_word = "violation" if node_count == 1 else "violations"
    click.echo(click.style(f"Found {node_count} {violation_word}:", bold=True))
    click.echo()

    for i, node in enumerate(nodes, 1):
        # Node separator
        if i > 1:
            click.echo(click.style("─" * 80, fg="bright_black"))
            click.echo()

        # Node number and impact
        impact = node.get('impact', 'unknown')
        impact_color = _get_impact_color(impact)
        click.echo(click.style(f"{i}. ", bold=True) + click.style(f"[{impact}]", fg=impact_color))
        click.echo()

        # Target (CSS selector)
        target = node.get('target', [])
        if target:
            # Format target as a CSS selector path
            target_str = ' > '.join(str(t) for t in target)
            click.echo(click.style("   Selector:", bold=True))
            click.echo(f"   {click.style(target_str, fg='yellow')}")
            click.echo()

        # HTML snippet
        html = node.get('html', '')
        if html:
            click.echo(click.style("   HTML:", bold=True))
            # Truncate very long HTML snippets
            if len(html) > 200:
                html = html[:197] + "…"
            click.echo(f"   {click.style(html, fg='bright_black')}")
            click.echo()

        # Failure summary
        failure_summary = node.get('failureSummary', '')
        if failure_summary:
            click.echo(click.style("   Issue:", bold=True))
            # Format failure summary with indentation
            lines = failure_summary.split('\n')
            for line in lines:
                if line.strip():
                    click.echo(f"   {line.strip()}")
            click.echo()

    # Auto-select element if single violation and not disabled
    if not no_select and node_count == 1 and nodes[0].get('target'):
        target = nodes[0].get('target', [])
        if target:
            # Convert target array to CSS selector
            # Axe returns selectors as array, join with descendant combinator
            selector = ' '.join(str(t) for t in target)

            if _auto_select_element(selector, rule_id):
                click.echo()
                click.echo(click.style(success("Element auto-selected and highlighted in browser"), fg="green"))
                click.echo(f"  Selector: {click.style(selector, fg='yellow')}")
                from inspekt.app.cli.table import _style_with_inline_code
                click.echo(_style_with_inline_code("  Run `inspekt inspected` to view full element details", base_fg="white"))

    # Footer
    click.echo()
    click.echo(f"Tested: {url}")


def _format_table_output(violations: list[dict], url: str, summary: dict, compact: bool = False) -> None:
    """Format violations as a table.

    Args:
        violations: List of violation dicts
        url: The URL that was tested
        summary: Summary dict with counts
        compact: If True, only show table without summary (for persistent mode)
    """
    if not violations:
        click.echo()
        click.echo(click.style(success("No accessibility violations found!"), fg="green", bold=True))
        if not compact:
            click.echo(f"Tested: {url}")
            click.echo(f"Passes: {summary.get('passCount', 0)}")
        return

    # Sort violations by impact (critical -> serious -> moderate -> minor)
    impact_order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
    violations = sorted(violations, key=lambda v: impact_order.get(v.get("impact", "minor"), 4))

    # Build all rows first for auto-width calculation
    headers = ["Rule", "Impact", "Count", "Description"]
    alignments = ["left", "left", "right", "left"]

    rows = []
    row_colors = []
    total_count = 0

    for violation in violations:
        rule_id = violation.get("id", "unknown")
        impact = violation.get("impact", "unknown")
        count = violation.get("nodeCount", 0)
        description = violation.get("description", "")

        total_count += count
        rows.append([rule_id, impact, str(count), description])
        row_colors.append([None, _get_impact_color(impact), None, None])

    # Create table with auto-width and title
    violation_count = summary.get('violationCount', len(violations))
    title = f"Accessibility Violations ({violation_count})"
    icon = get_icon("Accessibility")
    table = Table(headers, alignments=alignments, title=title, icon=icon)
    table.set_data(rows)
    table.print_header()

    for row_data, colors in zip(rows, row_colors, strict=False):
        table.print_row(row_data, colors)

    # Summary row
    summary_row = [f"{len(violations)} rules", "", str(total_count), ""]
    table.print_summary(summary_row)

    table.print_footer()

    # VM terminal: offer a "Data ready to copy" toast
    from inspekt.app.cli.table import emit_copyable_data
    emit_copyable_data(
        headers=headers,
        rows=rows,
        json_data={"violations": violations, "summary": summary, "url": url},
        summary=f"{len(violations)} violation{'s' if len(violations) != 1 else ''}",
    )

    # Summary (skip in compact mode)
    if compact:
        return

    click.echo()
    violation_word = "violation" if violation_count == 1 else "violations"
    click.echo(click.style(f"Summary: Found {violation_count} {violation_word} on {url}", bold=True))

    # Format counts: use "—" (em dash, dark gray) for 0, otherwise show number
    def format_count(count):
        if count == 0:
            return click.style("\u2014", fg="bright_black")
        return str(count)

    click.echo(f"  Critical:   {format_count(summary.get('criticalCount', 0))}")
    click.echo(f"  Serious:    {format_count(summary.get('seriousCount', 0))}")
    click.echo(f"  Moderate:   {format_count(summary.get('moderateCount', 0))}")
    click.echo(f"  Minor:      {format_count(summary.get('minorCount', 0))}")
    click.echo(f"  Passes:     {summary.get('passCount', 0)}")
    if summary.get('incompleteCount', 0) > 0:
        click.echo(f"  Incomplete: {summary.get('incompleteCount', 0)} (use --include-incomplete to see details)")


@click.command()
@click.option(
    "--threshold",
    type=float,
    default=0.5,
    help="Minimum confidence (0-1) to consider autocomplete required (default: 0.5)"
)
@click.option(
    "--include-hidden",
    is_flag=True,
    help="Include hidden input fields in analysis"
)
@click.option(
    "--include-disabled",
    is_flag=True,
    help="Include disabled input fields in analysis"
)
@click.option(
    "--json",
    "-j",
    "output_json",
    is_flag=True,
    help="Output results as JSON"
)
@click.option(
    "--timeout",
    type=float,
    default=30.0,
    help="Execution timeout in seconds (default: 30)"
)
def autocomplete(threshold, include_hidden, include_disabled, output_json, timeout):
    """
    Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5.

    Analyzes all form fields (input, textarea, select) on the current page and
    predicts appropriate autocomplete attributes using multi-language heuristics.

    The check uses 7 weighted matching strategies:
    - Label text (weight: 5) - highest reliability
    - Placeholder text (weight: 4)
    - Name attribute (weight: 2)
    - ID attribute (weight: 2)
    - Field type (weight: 1)
    - Input type (weight: 1)
    - Form type (weight: 1) - login vs signup detection

    Supports multi-language keyword matching (English, German, Dutch) with
    fuzzy substring matching for robust field identification.

    Examples:

        # Basic check (default 0.5 threshold)
        inspekt autocomplete

        # Strict check (higher confidence threshold)
        inspekt autocomplete --threshold 0.7

        # Include hidden and disabled fields
        inspekt autocomplete --include-hidden --include-disabled

        # JSON output for programmatic use
        inspekt autocomplete --json
    """
    try:
        import asyncio

        from inspekt.services.autocomplete_service import get_autocomplete_service

        client = BridgeClient()
        service = get_autocomplete_service()

        # Run the autocomplete check
        result = asyncio.run(service.check_autocomplete(
            bridge_executor=client,
            confidence_threshold=threshold,
            include_hidden=include_hidden,
            include_disabled=include_disabled
        ))

        if output_json:
            # JSON output
            from inspekt.app.cli.table import print_json
            analyzed = result.get("summary", {}).get("analyzed", 0)
            print_json(result, summary=f"autocomplete check ({analyzed} fields)")
            return

        # Check for errors
        if "error" in result and result.get("summary", {}).get("analyzed", 0) == 0:
            click.echo(click.style(f"Error: {result.get('error')}", fg="red"), err=True)
            sys.exit(1)

        # Format terminal output
        summary = result.get("summary", {})
        fields = result.get("fields", [])

        # Summary statistics (no header, cleaner alignment)
        click.echo()
        click.echo(click.style("Summary:", bold=True))
        click.echo(f"  Total fields:         {summary.get('total', 0)}")
        click.echo(f"  Analyzed:             {summary.get('analyzed', 0)}")
        click.echo(f"  Needs autocomplete:   {summary.get('needsAutocomplete', 0)}")
        click.echo(f"  Has autocomplete:     {summary.get('hasAutocomplete', 0)}")
        click.echo(f"  Correct autocomplete: {summary.get('hasCorrectAutocomplete', 0)}")

        violations = summary.get('violations', 0)
        warnings = summary.get('warnings', 0)

        # Format counts: use "None" for 0
        violations_text = violations if violations > 0 else "None"
        warnings_text = "None" if warnings == 0 else str(warnings)

        if violations > 0:
            click.echo(f"  {click.style('✗ Violations:', fg='red', bold=True)}         {violations_text}")
        else:
            click.echo(f"  {click.style('✓ Violations:', fg='green')}         {violations_text}")

        if warnings > 0:
            click.echo(f"  {click.style('⚠ Warnings:', fg='yellow', bold=True)}           {warnings_text}")
        else:
            click.echo(f"  {click.style('✓ Warnings:', fg='green')}           {warnings_text}")

        click.echo()

        # Group fields by status
        violation_fields = [f for f in fields if f.get('level') == 'violation']
        warning_fields = [f for f in fields if f.get('level') == 'warning']
        pass_fields = [f for f in fields if f.get('level') == 'pass']

        # Show violations
        if violation_fields:
            click.echo(click.style("❌ WCAG 2.1 SC 1.3.5 Violations:", bold=True, fg="red"))
            click.echo()
            for field in violation_fields:
                selector = field.get('selector', 'unknown')
                predicted = field.get('predictedAutocomplete', 'none')
                confidence = field.get('confidence', 0)
                label = field.get('label') or 'None'
                message = field.get('message', '')

                click.echo(f"  Field:     {selector}")
                click.echo(f"  Label:     {label}")
                click.echo(f"  Should be: {predicted} (confidence: {confidence:.0%})")
                click.echo(f"  Issue:     {message}")
                click.echo()

        # Show warnings
        if warning_fields:
            click.echo(click.style("⚠️  Warnings:", bold=True, fg="yellow"))
            click.echo()
            for field in warning_fields:
                selector = field.get('selector', 'unknown')
                predicted = field.get('predictedAutocomplete', 'none')
                confidence = field.get('confidence', 0)
                message = field.get('message', '')

                click.echo(f"  {click.style('Field:', fg='bright_black')} {selector}")
                click.echo(f"  {click.style('Predicted:', fg='cyan')} {predicted} (confidence: {confidence:.0%})")
                click.echo(f"  {click.style('Note:', fg='yellow')} {message}")
                click.echo()

        # Show passing fields with details
        if pass_fields:
            correct_fields = [f for f in pass_fields if f.get('status') == 'correct']
            if correct_fields:
                click.echo(click.style(f"✅ {len(correct_fields)} field(s) have correct autocomplete attributes:", fg="green"))
                click.echo()
                for field in correct_fields:
                    selector = field.get('selector', 'unknown')
                    current = field.get('currentAutocomplete', 'none')
                    label = field.get('label') or 'None'
                    confidence = field.get('confidence', 0)

                    click.echo(f"  Field:        {selector}")
                    click.echo(f"  Label:        {label}")
                    click.echo(f"  Autocomplete: {current} (confidence: {confidence:.0%})")
                    click.echo()

        # Footer with WCAG info
        click.echo(click.style("─" * 60, fg="bright_black"))
        if violations == 0:
            click.echo(click.style(success("Page is compliant with WCAG 2.1 SC 1.3.5"), fg="green", bold=True))
        else:
            click.echo(click.style(error(f"Found {violations} WCAG 2.1 SC 1.3.5 violation(s)"), fg="red", bold=True))

        click.echo(click.style(f"Confidence threshold: {threshold} | Multi-language: EN, DE, NL, FR", fg="bright_black"))
        click.echo()

        # VM terminal: offer a "Data ready to copy" toast
        from inspekt.app.cli.table import emit_copyable_data
        ac_rows = [
            [
                f.get("selector", ""),
                f.get("level", ""),
                f.get("label") or "",
                f.get("currentAutocomplete") or "",
                f.get("predictedAutocomplete") or "",
                f"{int((f.get('confidence') or 0) * 100)}%",
            ]
            for f in fields
        ]
        emit_copyable_data(
            headers=["Selector", "Level", "Label", "Current", "Predicted", "Confidence"],
            rows=ac_rows,
            json_data=result,
            summary=f"{len(fields)} field{'s' if len(fields) != 1 else ''}",
        )

        # Exit with error code if violations found
        if violations > 0:
            sys.exit(1)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================
# IBM EQUAL ACCESS COMMAND
# ============================================================


def _build_ibm_config(
    level: str,
    include_passes: bool,
    include_recommendations: bool,
) -> dict:
    """
    Build IBM Equal Access configuration object from CLI arguments.

    Args:
        level: WCAG level (2a, 2aa, 2aaa, 21a, 21aa, 22aa)
        include_passes: Whether to include passing checks
        include_recommendations: Whether to include recommendations

    Returns:
        Configuration dict for IBM checker
    """
    # Map level to IBM policy
    level_to_policies = {
        "2a": ["WCAG_2_0"],
        "2aa": ["WCAG_2_0"],
        "2aaa": ["WCAG_2_0"],
        "21a": ["WCAG_2_1"],
        "21aa": ["WCAG_2_1"],
        "22aa": ["WCAG_2_2"],
    }

    policies = level_to_policies.get(level.lower(), ["WCAG_2_2"])

    # Build report levels
    report_levels = ["violation", "potentialviolation"]
    if include_recommendations:
        report_levels.extend(["recommendation", "potentialrecommendation"])
    if include_passes:
        report_levels.append("pass")

    return {
        "policies": policies,
        "reportLevels": report_levels,
        "__level": level,
    }


def _get_ibm_level_color(level: str) -> str:
    """Get color for IBM level."""
    colors = {
        "violation": "red",
        "potentialviolation": "yellow",
        "recommendation": "blue",
        "potentialrecommendation": "cyan",
        "manual": "bright_black",
        "pass": "green"
    }
    return colors.get(level, "white")


def _format_ibm_level(level: str) -> str:
    """Get human-readable level name."""
    names = {
        "violation": "Violation",
        "potentialviolation": "Needs Review",
        "recommendation": "Recommendation",
        "potentialrecommendation": "Potential",
        "manual": "Manual",
        "pass": "Pass"
    }
    return names.get(level, level)


def _format_ibm_table_output(issues, summary, url, compact=False):
    """Format IBM Equal Access results as a CLI table."""
    if not issues:
        click.echo(click.style(success("No accessibility issues found."), bold=True))
        return

    headers = ["Rule", "Level", "Count", "Message"]
    alignments = ["left", "left", "right", "left"]

    # Group issues by rule ID
    rule_groups = {}
    for issue in issues:
        rule_id = issue.get("ruleId", "unknown")
        if rule_id not in rule_groups:
            rule_groups[rule_id] = {
                "level": issue.get("level", "violation"),
                "message": issue.get("message", "")[:60],
                "count": 0
            }
        rule_groups[rule_id]["count"] += 1

    rows = []
    row_colors = []
    total_count = 0

    for rule_id, data in sorted(rule_groups.items()):
        level = data["level"]
        count = data["count"]
        message = data["message"]

        total_count += count
        rows.append([rule_id, _format_ibm_level(level), str(count), message])
        row_colors.append([None, _get_ibm_level_color(level), None, None])

    # Create table
    issue_count = sum(1 for i in issues if i.get("level") != "pass")
    title = f"IBM Equal Access Issues ({issue_count})"
    icon = get_icon("Accessibility")
    table = Table(headers, alignments=alignments, title=title, icon=icon)
    table.set_data(rows)
    table.print_header()

    for row_data, colors in zip(rows, row_colors, strict=False):
        table.print_row(row_data, colors)

    # Summary row
    summary_row = [f"{len(rule_groups)} rules", "", str(total_count), ""]
    table.print_summary(summary_row)

    table.print_footer()

    # VM terminal: offer a "Data ready to copy" toast
    from inspekt.app.cli.table import emit_copyable_data
    emit_copyable_data(
        headers=headers,
        rows=rows,
        json_data={"issues": issues, "summary": summary, "url": url},
        summary=f"{issue_count} issue{'s' if issue_count != 1 else ''}",
    )

    if compact:
        return

    click.echo()
    issue_word = "issue" if issue_count == 1 else "issues"
    click.echo(click.style(f"Summary: Found {issue_count} {issue_word} on {url}", bold=True))

    def format_count(count):
        if count == 0:
            return click.style("\u2014", fg="bright_black")
        return str(count)

    click.echo(f"  Violations:           {format_count(summary.get('violation', 0))}")
    click.echo(f"  Needs Review:         {format_count(summary.get('potentialviolation', 0))}")
    click.echo(f"  Recommendations:      {format_count(summary.get('recommendation', 0))}")
    click.echo(f"  Potential:            {format_count(summary.get('potentialrecommendation', 0))}")
    click.echo(f"  Passes:               {format_count(summary.get('pass', 0))}")


@click.command()
@click.option(
    "--level",
    type=click.Choice(["2a", "2aa", "2aaa", "21a", "21aa", "22aa"], case_sensitive=False),
    default="21aa",
    help="WCAG conformance level to test (default: 21aa)"
)
@click.option(
    "--rule",
    type=str,
    help="Check specific accessibility rule by ID"
)
@click.option(
    "--list-rules",
    is_flag=True,
    help="List all available IBM Equal Access rules and exit"
)
@click.option(
    "--include-passes",
    is_flag=True,
    help="Include passing checks in output"
)
@click.option(
    "--include-recommendations",
    is_flag=True,
    help="Include recommendations in output"
)
@click.option(
    "--json",
    "-j",
    "output_json",
    is_flag=True,
    help="Output full results as JSON"
)
@click.option(
    "--timeout",
    type=float,
    default=30.0,
    help="Timeout in seconds (default: 30)"
)
@click.option(
    "--scoped",
    type=str,
    help="Scope tests to specific elements. Use 'inspected' for the currently inspected element, or provide CSS selectors"
)
@click.option(
    "--exclude",
    type=str,
    multiple=True,
    help="Exclude elements from testing"
)
@click.option(
    "--show-badges/--no-show-badges",
    default=None,
    help="Show numbered severity badges on elements with issues"
)
@click.option(
    "--interactive",
    is_flag=True,
    default=False,
    help="Make badges clickable with detailed popover information"
)
def ibm(level, rule, list_rules, include_passes, include_recommendations, output_json, timeout, scoped, exclude, show_badges, interactive):
    """
    Run IBM Equal Access accessibility audit on the current page.

    Analyzes the page for WCAG conformance violations using IBM's Equal Access
    accessibility checker. By default, tests against WCAG 2.2 Level AA standards.

    The audit runs in your current browser tab, testing the actual rendered page
    state including any JavaScript-generated content.

    Examples:
        # Basic WCAG audits
        inspekt ibm                                    # WCAG 2.2 Level AA audit
        inspekt ibm --level 21aa                       # WCAG 2.1 Level AA audit
        inspekt ibm --include-recommendations          # Show all recommendations

        # Interactive badges
        inspekt ibm --interactive                      # Clickable badges with popovers
        inspekt ibm --no-show-badges                   # Disable badges

        # Scoped testing
        inspekt ibm --scoped inspected                 # Test only inspected element
        inspekt ibm --scoped "main"                    # Test only main element

        # Output formats
        inspekt ibm --json                             # Full JSON output
        inspekt ibm --list-rules                       # Show available rules
    """
    # Create bridge client
    from inspekt.client import BridgeClient
    client = BridgeClient()

    # Handle --list-rules
    if list_rules:
        ace_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "ace.min.js"
        list_script_path = Path(__file__).parent.parent.parent / "scripts" / "list_ibm_rules.js"

        if not ace_lib_path.exists():
            click.echo(f"Error: IBM Equal Access library not found: {ace_lib_path}", err=True)
            click.echo("Run 'inspekt start' to download the library.", err=True)
            sys.exit(1)

        try:
            with builtin_open(ace_lib_path) as f:
                ace_lib = f.read()
            with builtin_open(list_script_path) as f:
                list_script = f.read()

            # Inject library - expose ace to global scope
            ace_lib_wrapped = f"(function() {{ {ace_lib}; window.ace = ace; return typeof window.ace !== 'undefined'; }})()"
            result = client.execute(ace_lib_wrapped, timeout=15.0)
            if not result.get("ok") or not result.get("result"):
                click.echo("Error loading IBM Equal Access library", err=True)
                sys.exit(1)

            # Execute list script
            result = client.execute(list_script, timeout=timeout)
            if not result.get("ok"):
                click.echo(f"Error listing rules: {result.get('error')}", err=True)
                sys.exit(1)

            data = result.get("result", {})
            if output_json:
                from inspekt.app.cli.table import print_json
                print_json(data, summary=f"{len(data.get('rules', []))} IBM rules")
            else:
                rules = data.get("rules", [])
                stats = data.get("stats", {})

                click.echo(click.style(f"IBM Equal Access Rules ({len(rules)} total)", bold=True))
                click.echo()

                for rule_data in rules:
                    click.echo(f"  {click.style(rule_data['id'], fg='cyan')}")
                    if rule_data.get('description'):
                        click.echo(f"    {rule_data['description'][:80]}")
                    if rule_data.get('wcag'):
                        wcag_str = ', '.join(rule_data['wcag'])
                        click.echo(click.style(f"    WCAG: {wcag_str}", fg='bright_black'))
                    click.echo()

                click.echo(click.style("Statistics:", bold=True))
                for key, value in stats.get('byLevel', {}).items():
                    click.echo(f"  {key}: {value}")

        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        return

    # Build config
    config = _build_ibm_config(level, include_passes, include_recommendations)

    # Build context
    if scoped:
        if scoped.lower() == "inspected":
            config["__context"] = "inspected"
        else:
            config["__context"] = scoped

    # Determine if badges should be shown
    if show_badges is None:
        from inspekt.config import load_config
        config_data = load_config()
        show_badges = config_data.get("ibm", {}).get("show-badges", True)

    if interactive and not show_badges:
        click.echo("Error: --interactive requires --show-badges to be enabled", err=True)
        sys.exit(1)

    config["__showBadges"] = show_badges and not output_json
    config["__interactiveBadges"] = interactive and show_badges and not output_json

    # Load IBM Equal Access library
    ace_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "ace.min.js"
    if not ace_lib_path.exists():
        click.echo(f"Error: IBM Equal Access library not found: {ace_lib_path}", err=True)
        click.echo("Run 'inspekt start' to download the library.", err=True)
        sys.exit(1)

    script_path = Path(__file__).parent.parent.parent / "scripts" / "run_ibm.js"
    popover_core_path = Path(__file__).parent.parent.parent / "scripts" / "shared-popover" / "popover-core.js"
    popover_content_path = Path(__file__).parent.parent.parent / "scripts" / "shared-popover" / "popover-content.js"

    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    if not popover_core_path.exists():
        click.echo(f"Error: Popover core not found: {popover_core_path}", err=True)
        sys.exit(1)

    if not popover_content_path.exists():
        click.echo(f"Error: Popover content not found: {popover_content_path}", err=True)
        sys.exit(1)

    try:
        with builtin_open(ace_lib_path) as f:
            ace_lib = f.read()
        with builtin_open(popover_core_path) as f:
            popover_core = f.read()
        with builtin_open(popover_content_path) as f:
            popover_content = f.read()
        with builtin_open(script_path) as f:
            audit_script = f.read()

        # Replace config placeholder
        audit_script = audit_script.replace("__IBM_CONFIG__", json.dumps(config))

        # Inject library - expose ace to global scope
        # The library defines `var ace` so we need to assign it to window after execution
        ace_lib_wrapped = f"(function() {{ {ace_lib}; window.ace = ace; return typeof window.ace !== 'undefined'; }})()"
        result = client.execute(ace_lib_wrapped, timeout=15.0)
        if not result.get("ok"):
            click.echo(f"Error loading IBM Equal Access: {result.get('error')}", err=True)
            sys.exit(1)
        if not result.get("result"):
            click.echo("Error: IBM Equal Access library failed to load", err=True)
            sys.exit(1)

        # Inject popover core for unified badge/popover system
        result = client.execute(popover_core, timeout=5.0)
        if not result.get("ok"):
            click.echo(f"Error loading popover core: {result.get('error')}", err=True)
            sys.exit(1)

        # Inject popover content module
        result = client.execute(popover_content, timeout=5.0)
        if not result.get("ok"):
            click.echo(f"Error loading popover content: {result.get('error')}", err=True)
            sys.exit(1)

        # Show warnings
        warnings = ["Traditional accessibility checkers identify only about 20–50% of WCAG issues and may produce false positives. You cannot rely on these results to claim WCAG compliance."]
        click.echo(click.style("WARNING", fg="yellow", bold=True), err=True)
        print_wrapped(warnings[0], err=True)
        click.echo("", err=True)

        # Show progress
        level_names = {
            "2a": "WCAG 2.0 Level A",
            "2aa": "WCAG 2.0 Level AA",
            "2aaa": "WCAG 2.0 Level AAA",
            "21a": "WCAG 2.1 Level A",
            "21aa": "WCAG 2.1 Level AA",
            "22aa": "WCAG 2.2 Level AA",
        }
        level_label = level_names.get(level.lower(), f"WCAG {level.upper()}")
        click.echo(f"Running IBM Equal Access Check ({level_label})…", err=True)

        # Execute audit
        result = client.execute(audit_script, timeout=timeout)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        data = result.get("result", {})
        if not data.get("ok"):
            click.echo(f"Error: {data.get('error')}", err=True)
            sys.exit(1)

        audit_result = data.get("result", {})
        issues = audit_result.get("issues", [])
        summary = audit_result.get("summary", {})

        # Get page info from results
        url = audit_result.get("url", "unknown")
        page_title = audit_result.get("title", "")

        if output_json:
            from datetime import datetime
            output = {
                "url": url,
                "title": page_title,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "tool": "IBM Equal Access",
                "config": {
                    "level": level,
                    "policies": config.get("policies", []),
                },
                "issues": issues,
                "summary": summary,
            }
            from inspekt.app.cli.table import print_json
            print_json(output, summary=f"{len(issues)} IBM issues")
        else:
            _format_ibm_table_output(issues, summary, url)

            # Show badge stats
            badge_stats = audit_result.get("badgeStats")
            if badge_stats and badge_stats.get("badgesCreated", 0) > 0:
                click.echo()
                click.echo(click.style(f"Created {badge_stats['badgesCreated']} badges on page", fg="bright_black"))

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


# ============================================================
# COMBINED A11Y COMMAND
# ============================================================

# IBM rule to WCAG SC mapping (IBM issues don't include this at runtime)
IBM_RULE_TO_WCAG = {
    "a_text_purpose": ["2.4.4", "4.1.2"],
    "applet_alt_exists": ["1.1.1"],
    "application_content_accessible": ["1.1.1", "2.1.1"],
    "area_alt_exists": ["1.1.1"],
    "aria_accessiblename_exists": ["4.1.2"],
    "aria_activedescendant_tabindex_valid": ["2.1.1"],
    "aria_activedescendant_valid": ["4.1.2"],
    "aria_attribute_allowed": ["4.1.2"],
    "aria_attribute_conflict": ["4.1.2"],
    "aria_attribute_exists": ["4.1.2"],
    "aria_attribute_required": ["4.1.2"],
    "aria_attribute_value_valid": ["4.1.2"],
    "aria_banner_label_unique": ["2.4.1"],
    "aria_banner_single": ["2.4.1"],
    "aria_child_valid": ["4.1.2"],
    "aria_complementary_label_unique": ["2.4.1"],
    "aria_content_in_landmark": ["2.4.1"],
    "aria_contentinfo_label_unique": ["2.4.1"],
    "aria_contentinfo_misuse": ["4.1.2"],
    "aria_contentinfo_single": ["2.4.1"],
    "aria_descendant_valid": ["4.1.2"],
    "aria_form_label_unique": ["2.4.1"],
    "aria_hidden_focus_misuse": ["4.1.2"],
    "aria_id_unique": ["4.1.2"],
    "aria_main_label_unique": ["2.4.1"],
    "aria_navigation_label_unique": ["2.4.1"],
    "aria_parent_required": ["4.1.2"],
    "aria_region_label_unique": ["2.4.1"],
    "aria_role_allowed": ["4.1.2"],
    "aria_role_valid": ["4.1.2"],
    "aria_search_label_unique": ["2.4.1"],
    "aria_toolbar_label_unique": ["4.1.2"],
    "blink_css_review": ["2.2.2"],
    "blink_elem_deprecated": ["2.2.2"],
    "canvas_content_described": ["1.1.1"],
    "combobox_autocomplete_valid": ["4.1.2"],
    "combobox_haspopup_valid": ["4.1.2"],
    "combobox_popup_reference": ["4.1.2"],
    "dir_attribute_valid": ["1.3.2"],
    "element_tabbable_visible": ["2.4.7"],
    "element_tabbable_unobscured": ["2.4.11"],
    "embed_alt_exists": ["1.1.1"],
    "embed_noembed_exists": ["1.1.1"],
    "emoticons_alt_exists": ["1.1.1"],
    "fieldset_legend_valid": ["1.3.1"],
    "figure_label_exists": ["1.1.1"],
    "form_font_color": ["1.4.1"],
    "form_submit_button_exists": ["3.2.2"],
    "frame_src_valid": ["4.1.2"],
    "frame_title_exists": ["2.4.1"],
    "heading_content_exists": ["1.3.1"],
    "heading_markup_misuse": ["1.3.1"],
    "html_lang_exists": ["3.1.1"],
    "html_lang_valid": ["3.1.1"],
    "html_skipnav_exists": ["2.4.1"],
    "iframe_interactive_tabbable": ["2.1.1"],
    "imagebutton_alt_exists": ["1.1.1"],
    "img_alt_background": ["1.1.1"],
    "img_alt_decorative": ["1.1.1"],
    "img_alt_misuse": ["1.1.1"],
    "img_alt_valid": ["1.1.1"],
    "img_ismap_misuse": ["1.1.1"],
    "img_longdesc_misuse": ["1.1.1"],
    "input_fields_grouped": ["1.3.1"],
    "input_haspopup_conflict": ["4.1.2"],
    "input_label_exists": ["1.3.1", "4.1.2"],
    "input_label_visible": ["3.3.2"],
    "input_onchange_review": ["3.2.2"],
    "input_placeholder_label_visible": ["3.3.2"],
    "label_content_exists": ["1.3.1"],
    "label_name_visible": ["2.5.3"],
    "label_ref_valid": ["1.3.1"],
    "list_structure_proper": ["1.3.1"],
    "marquee_elem_avoid": ["2.2.2"],
    "media_alt_brief": ["1.1.1"],
    "media_alt_exists": ["1.1.1", "1.2.1"],
    "media_autostart_controllable": ["1.4.2"],
    "media_keyboard_controllable": ["2.1.1"],
    "media_live_captioned": ["1.2.4"],
    "media_text_equiv_exists": ["1.2.1"],
    "media_track_available": ["1.2.2", "1.2.5"],
    "meta_redirect_optional": ["2.2.1"],
    "meta_refresh_delay": ["2.2.1"],
    "meta_viewport_zoomable": ["1.4.4"],
    "noembed_content_exists": ["1.1.1"],
    "object_text_exists": ["1.1.1"],
    "page_title_exists": ["2.4.2"],
    "page_title_valid": ["2.4.2"],
    "script_focus_blur_review": ["2.1.1"],
    "script_onclick_misuse": ["2.1.1"],
    "script_onclick_require": ["2.1.1"],
    "script_select_review": ["2.1.1"],
    "select_options_grouped": ["1.3.1"],
    "skip_main_described": ["2.4.1"],
    "skip_main_exists": ["2.4.1"],
    "style_background_decorative": ["1.1.1"],
    "style_before_after_review": ["1.3.1"],
    "style_color_misuse": ["1.4.1"],
    "style_focus_visible": ["2.4.7"],
    "style_highcontrast_visible": ["1.4.3"],
    "style_hover_persistent": ["1.4.13"],
    "style_viewport_resizable": ["1.4.4"],
    "table_caption_empty": ["1.3.1"],
    "table_caption_nested": ["1.3.1"],
    "table_headers_exists": ["1.3.1"],
    "table_headers_ref_valid": ["1.3.1"],
    "table_layout_linearized": ["1.3.2"],
    "table_scope_valid": ["1.3.1"],
    "table_structure_misuse": ["1.3.1"],
    "table_summary_redundant": ["1.3.1"],
    "target_spacing_sufficient": ["2.5.8"],
    "text_block_heading": ["1.3.1"],
    "text_contrast_sufficient": ["1.4.3"],
    "text_quoted_correctly": ["1.3.1"],
    "text_sensory_misuse": ["1.3.3"],
    "text_spacing_valid": ["1.4.12"],
    "text_whitespace_valid": ["1.3.2"],
    "widget_tabbable_exists": ["2.1.1"],
    "widget_tabbable_single": ["2.1.1"],
}

# WCAG Success Criteria descriptions for combined output
WCAG_SC_DESCRIPTIONS = {
    "1.1.1": "Non-text Content",
    "1.2.1": "Audio-only and Video-only",
    "1.2.2": "Captions",
    "1.2.3": "Audio Description or Media Alternative",
    "1.2.4": "Captions (Live)",
    "1.2.5": "Audio Description",
    "1.3.1": "Info and Relationships",
    "1.3.2": "Meaningful Sequence",
    "1.3.3": "Sensory Characteristics",
    "1.3.4": "Orientation",
    "1.3.5": "Identify Input Purpose",
    "1.3.6": "Identify Purpose",
    "1.4.1": "Use of Color",
    "1.4.2": "Audio Control",
    "1.4.3": "Contrast (Minimum)",
    "1.4.4": "Resize Text",
    "1.4.5": "Images of Text",
    "1.4.6": "Contrast (Enhanced)",
    "1.4.7": "Low or No Background Audio",
    "1.4.8": "Visual Presentation",
    "1.4.9": "Images of Text (No Exception)",
    "1.4.10": "Reflow",
    "1.4.11": "Non-text Contrast",
    "1.4.12": "Text Spacing",
    "1.4.13": "Content on Hover or Focus",
    "2.1.1": "Keyboard",
    "2.1.2": "No Keyboard Trap",
    "2.1.4": "Character Key Shortcuts",
    "2.2.1": "Timing Adjustable",
    "2.2.2": "Pause, Stop, Hide",
    "2.3.1": "Three Flashes or Below",
    "2.4.1": "Bypass Blocks",
    "2.4.2": "Page Titled",
    "2.4.3": "Focus Order",
    "2.4.4": "Link Purpose (In Context)",
    "2.4.5": "Multiple Ways",
    "2.4.6": "Headings and Labels",
    "2.4.7": "Focus Visible",
    "2.4.11": "Focus Not Obscured (Minimum)",
    "2.5.1": "Pointer Gestures",
    "2.5.2": "Pointer Cancellation",
    "2.5.3": "Label in Name",
    "2.5.4": "Motion Actuation",
    "2.5.5": "Target Size (Enhanced)",
    "2.5.6": "Concurrent Input Mechanisms",
    "2.5.7": "Dragging Movements",
    "2.5.8": "Target Size (Minimum)",
    "3.1.1": "Language of Page",
    "3.1.2": "Language of Parts",
    "3.2.1": "On Focus",
    "3.2.2": "On Input",
    "3.2.3": "Consistent Navigation",
    "3.2.4": "Consistent Identification",
    "3.2.6": "Consistent Help",
    "3.3.1": "Error Identification",
    "3.3.2": "Labels or Instructions",
    "3.3.3": "Error Suggestion",
    "3.3.4": "Error Prevention",
    "3.3.7": "Redundant Entry",
    "3.3.8": "Accessible Authentication",
    "4.1.1": "Parsing",
    "4.1.2": "Name, Role, Value",
    "4.1.3": "Status Messages",
}

# WCAG Success Criteria levels and versions for conformance filtering
# Structure: SC number -> {"level": "A"|"AA"|"AAA", "version": "2.0"|"2.1"|"2.2"}
WCAG_SC_LEVELS = {
    # WCAG 2.0 Level A
    "1.1.1": {"level": "A", "version": "2.0"},
    "1.2.1": {"level": "A", "version": "2.0"},
    "1.2.2": {"level": "A", "version": "2.0"},
    "1.2.3": {"level": "A", "version": "2.0"},
    "1.3.1": {"level": "A", "version": "2.0"},
    "1.3.2": {"level": "A", "version": "2.0"},
    "1.3.3": {"level": "A", "version": "2.0"},
    "1.4.1": {"level": "A", "version": "2.0"},
    "1.4.2": {"level": "A", "version": "2.0"},
    "2.1.1": {"level": "A", "version": "2.0"},
    "2.1.2": {"level": "A", "version": "2.0"},
    "2.2.1": {"level": "A", "version": "2.0"},
    "2.2.2": {"level": "A", "version": "2.0"},
    "2.3.1": {"level": "A", "version": "2.0"},
    "2.4.1": {"level": "A", "version": "2.0"},
    "2.4.2": {"level": "A", "version": "2.0"},
    "2.4.3": {"level": "A", "version": "2.0"},
    "2.4.4": {"level": "A", "version": "2.0"},
    "3.1.1": {"level": "A", "version": "2.0"},
    "3.2.1": {"level": "A", "version": "2.0"},
    "3.2.2": {"level": "A", "version": "2.0"},
    "3.3.1": {"level": "A", "version": "2.0"},
    "3.3.2": {"level": "A", "version": "2.0"},
    "4.1.1": {"level": "A", "version": "2.0"},
    "4.1.2": {"level": "A", "version": "2.0"},
    # WCAG 2.0 Level AA
    "1.2.4": {"level": "AA", "version": "2.0"},
    "1.2.5": {"level": "AA", "version": "2.0"},
    "1.4.3": {"level": "AA", "version": "2.0"},
    "1.4.4": {"level": "AA", "version": "2.0"},
    "1.4.5": {"level": "AA", "version": "2.0"},
    "2.4.5": {"level": "AA", "version": "2.0"},
    "2.4.6": {"level": "AA", "version": "2.0"},
    "2.4.7": {"level": "AA", "version": "2.0"},
    "3.1.2": {"level": "AA", "version": "2.0"},
    "3.2.3": {"level": "AA", "version": "2.0"},
    "3.2.4": {"level": "AA", "version": "2.0"},
    "3.3.3": {"level": "AA", "version": "2.0"},
    "3.3.4": {"level": "AA", "version": "2.0"},
    # WCAG 2.0 Level AAA
    "1.2.6": {"level": "AAA", "version": "2.0"},
    "1.2.7": {"level": "AAA", "version": "2.0"},
    "1.2.8": {"level": "AAA", "version": "2.0"},
    "1.2.9": {"level": "AAA", "version": "2.0"},
    "1.4.6": {"level": "AAA", "version": "2.0"},
    "1.4.7": {"level": "AAA", "version": "2.0"},
    "1.4.8": {"level": "AAA", "version": "2.0"},
    "1.4.9": {"level": "AAA", "version": "2.0"},
    "2.1.3": {"level": "AAA", "version": "2.0"},
    "2.2.3": {"level": "AAA", "version": "2.0"},
    "2.2.4": {"level": "AAA", "version": "2.0"},
    "2.2.5": {"level": "AAA", "version": "2.0"},
    "2.3.2": {"level": "AAA", "version": "2.0"},
    "2.4.8": {"level": "AAA", "version": "2.0"},
    "2.4.9": {"level": "AAA", "version": "2.0"},
    "2.4.10": {"level": "AAA", "version": "2.0"},
    "3.1.3": {"level": "AAA", "version": "2.0"},
    "3.1.4": {"level": "AAA", "version": "2.0"},
    "3.1.5": {"level": "AAA", "version": "2.0"},
    "3.1.6": {"level": "AAA", "version": "2.0"},
    "3.2.5": {"level": "AAA", "version": "2.0"},
    "3.3.5": {"level": "AAA", "version": "2.0"},
    "3.3.6": {"level": "AAA", "version": "2.0"},
    # WCAG 2.1 new Level A criteria
    "2.1.4": {"level": "A", "version": "2.1"},
    "2.5.1": {"level": "A", "version": "2.1"},
    "2.5.2": {"level": "A", "version": "2.1"},
    "2.5.3": {"level": "A", "version": "2.1"},
    "2.5.4": {"level": "A", "version": "2.1"},
    # WCAG 2.1 new Level AA criteria
    "1.3.4": {"level": "AA", "version": "2.1"},
    "1.3.5": {"level": "AA", "version": "2.1"},
    "1.4.10": {"level": "AA", "version": "2.1"},
    "1.4.11": {"level": "AA", "version": "2.1"},
    "1.4.12": {"level": "AA", "version": "2.1"},
    "1.4.13": {"level": "AA", "version": "2.1"},
    "4.1.3": {"level": "AA", "version": "2.1"},
    # WCAG 2.1 new Level AAA criteria
    "1.3.6": {"level": "AAA", "version": "2.1"},
    "2.5.5": {"level": "AAA", "version": "2.1"},
    "2.5.6": {"level": "AAA", "version": "2.1"},
    # WCAG 2.2 new Level A criteria
    "3.2.6": {"level": "A", "version": "2.2"},
    "3.3.7": {"level": "A", "version": "2.2"},
    # WCAG 2.2 new Level AA criteria
    "2.4.11": {"level": "AA", "version": "2.2"},
    "2.4.12": {"level": "AA", "version": "2.2"},
    "2.4.13": {"level": "AA", "version": "2.2"},
    "2.5.7": {"level": "AA", "version": "2.2"},
    "2.5.8": {"level": "AA", "version": "2.2"},
    "3.3.8": {"level": "AA", "version": "2.2"},
    "3.3.9": {"level": "AA", "version": "2.2"},
}


def _sc_matches_level(sc: str, level: str) -> bool:
    """Check if a WCAG Success Criterion matches the requested conformance level.

    Args:
        sc: Success Criterion number (e.g., "1.4.3")
        level: Conformance level ("2a", "2aa", "2aaa", "21a", "21aa", "22aa")

    Returns:
        True if the SC should be included for the given level
    """
    sc_info = WCAG_SC_LEVELS.get(sc)
    if not sc_info:
        # Unknown SC - include by default to avoid hiding issues
        return True

    sc_level = sc_info["level"]
    sc_version = sc_info["version"]

    # Parse the requested level
    # Format: "2a", "2aa", "2aaa", "21a", "21aa", "22aa"
    level_lower = level.lower()

    # Determine requested WCAG version
    if level_lower.startswith("22"):
        req_version = "2.2"
        req_level = level_lower[2:].upper()  # "aa" -> "AA"
    elif level_lower.startswith("21"):
        req_version = "2.1"
        req_level = level_lower[2:].upper()
    elif level_lower.startswith("2"):
        req_version = "2.0"
        req_level = level_lower[1:].upper()
    else:
        return True  # Unknown format, include by default

    # Check version compatibility
    # WCAG 2.0 only includes 2.0 criteria
    # WCAG 2.1 includes 2.0 and 2.1 criteria
    # WCAG 2.2 includes 2.0, 2.1, and 2.2 criteria
    if req_version == "2.0" and sc_version != "2.0":
        return False
    if req_version == "2.1" and sc_version == "2.2":
        return False
    # 2.2 includes all versions

    # Check level compatibility (A ⊂ AA ⊂ AAA)
    # Level A only includes A criteria
    # Level AA includes A and AA criteria
    # Level AAA includes A, AA, and AAA criteria
    if req_level == "A" and sc_level != "A":
        return False
    # AAA includes all levels
    return not (req_level == "AA" and sc_level == "AAA")


def _build_enriched_report_data(
    url: str,
    level: str,
    engine_list: list[str],
    engine_results: dict,
    consolidated: dict,
    versions: dict,
    include_recommendations: bool = False,
) -> dict:
    """Build the canonical enriched report data dict.

    This is a pure-data function (no click.echo calls) that computes
    all analysis data and returns a structured dict suitable for
    JSON serialization or HTML report rendering.

    Args:
        url: The audited URL
        level: WCAG conformance level (e.g. "21aa")
        engine_list: List of engine names in execution order
        engine_results: Dict mapping engine name to its raw results
        consolidated: Level-filtered consolidated results by WCAG SC
        versions: Dict mapping engine name to version string
        include_recommendations: Whether to include recommendations

    Returns:
        Enriched report data dict
    """
    from datetime import datetime

    # Helper to count violations from filtered consolidated results
    def count_filtered_violations(engine: str) -> int:
        count = 0
        for _sc, data in consolidated.items():
            status = data.get(f"{engine}_status", "pass")
            sc_count = data.get(f"{engine}_count", 0)
            if status in ("violation", "potentialviolation"):
                count += sc_count
        return count

    # Sort SCs
    def sc_sort_key(sc):
        parts = sc.split(".")
        return tuple(int(p) for p in parts)

    sorted_scs = sorted(consolidated.keys(), key=sc_sort_key)

    # Compute disagreements and disparities
    issues_count = 0
    disagreements = []
    disparities = []

    for sc in sorted_scs:
        data = consolidated[sc]
        engine_fails = {
            eng: data.get(f"{eng}_status") not in ("pass",)
            for eng in engine_list
        }
        engine_counts = {
            eng: data.get(f"{eng}_count", 0)
            for eng in engine_list
        }
        failing_engines = [eng for eng, fails in engine_fails.items() if fails]
        passing_engines = [eng for eng, fails in engine_fails.items() if not fails]

        if failing_engines:
            issues_count += 1

        # Disagreements
        if failing_engines and passing_engines:
            disagreements.append({
                "sc": sc,
                "description": WCAG_SC_DESCRIPTIONS.get(sc, ""),
                "conformance_level": WCAG_SC_LEVELS.get(sc, {}).get("level", ""),
                "failing_engines": [
                    {"engine": eng, "abbr": AVAILABLE_ENGINES[eng]["abbr"], "count": engine_counts[eng]}
                    for eng in failing_engines
                ],
                "passing_engines": [
                    {"engine": eng, "abbr": AVAILABLE_ENGINES[eng]["abbr"]}
                    for eng in passing_engines
                ],
            })

        # Disparities
        if len(failing_engines) >= 2:
            counts = [engine_counts[eng] for eng in failing_engines if engine_counts[eng] > 0]
            if len(counts) >= 2:
                min_c, max_c = min(counts), max(counts)
                if min_c > 0 and max_c / min_c >= 2:
                    disparities.append({
                        "sc": sc,
                        "description": WCAG_SC_DESCRIPTIONS.get(sc, ""),
                        "conformance_level": WCAG_SC_LEVELS.get(sc, {}).get("level", ""),
                        "counts": {eng: engine_counts[eng] for eng in engine_list},
                        "ratio": round(max_c / min_c, 1),
                    })

    # Engine correlation
    correlation = _calculate_engine_correlation(consolidated, engine_list)

    # Build enriched engines dict
    engines_data = {}
    for engine in engine_list:
        eng_result = engine_results.get(engine, {})
        eng_detail: dict = {
            "name": AVAILABLE_ENGINES[engine]["name"],
            "abbr": AVAILABLE_ENGINES[engine]["abbr"],
            "version": versions.get(engine, "unknown"),
            "violations": count_filtered_violations(engine),
            "error": eng_result.get("error"),
        }

        # Enriched fields: passes and incomplete counts
        if engine == "axe":
            eng_detail["passes"] = len(eng_result.get("passes", []))
            eng_detail["incomplete"] = len(eng_result.get("incomplete", []))
            # Impact summary from violations
            impact_counts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
            for v in eng_result.get("violations", []):
                impact = v.get("impact", "minor")
                count = v.get("nodeCount", len(v.get("nodes", [])))
                impact_counts[impact] = impact_counts.get(impact, 0) + count
            eng_detail["impact_summary"] = impact_counts
        elif engine == "eac":
            issues = eng_result.get("issues", [])
            eng_detail["passes"] = len([i for i in issues if i.get("level") == "pass"])
            eng_detail["incomplete"] = 0
        elif engine == "hcs":
            messages = eng_result.get("messages", [])
            eng_detail["passes"] = 0  # HCS doesn't report passes
            eng_detail["incomplete"] = len([m for m in messages if m.get("type") == 2])
        elif engine == "sia":
            outcomes = eng_result.get("outcomes", [])
            eng_detail["passes"] = len([o for o in outcomes if o.get("outcome") == "passed"])
            eng_detail["incomplete"] = len(eng_result.get("cantTell", []))

        engines_data[engine] = eng_detail

    # Enrich consolidated with descriptions and levels
    enriched_consolidated = {}
    for sc in sorted_scs:
        entry = dict(consolidated[sc])  # Copy
        entry["description"] = WCAG_SC_DESCRIPTIONS.get(sc, "")
        sc_info = WCAG_SC_LEVELS.get(sc, {})
        entry["conformance_level"] = sc_info.get("level", "")
        entry["wcag_version"] = sc_info.get("version", "")
        enriched_consolidated[sc] = entry

    # Build output
    output: dict = {
        "url": url,
        "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "level": level,
        "engines": engines_data,
        "execution_order": engine_list,
        "consolidated": enriched_consolidated,
        "analysis": {
            "total_criteria_with_issues": issues_count,
            "agreement_percentage": correlation["agreement_percentage"],
            "total_criteria_evaluated": correlation["total_scs"],
            "full_agreement_count": correlation["full_agreement"],
            "disagreements": disagreements,
            "disparities": disparities,
        },
        "engine_details": _extract_engine_rule_details(engine_results, engine_list),
    }

    # Recommendations
    if include_recommendations:
        recommendations = _collect_recommendations(engine_results, engine_list)
        recommendations_by_sc: dict[str, list] = {}
        for rec in recommendations:
            sc = rec["sc"] or "unknown"
            if sc not in recommendations_by_sc:
                recommendations_by_sc[sc] = []
            recommendations_by_sc[sc].append({
                "engine": rec["engine"],
                "rule_id": rec["rule_id"],
                "level": rec["level"],
                "message": rec["message"],
            })
        output["recommendations"] = {
            "total": len(recommendations),
            "by_sc": recommendations_by_sc,
        }

    return output


def _get_contextual_tips(
    engine_list: list[str],
    issue_count: int,
    level: str,
    show_badges: bool = False,
    interactive: bool = False,
    verbose: bool = False,
    show_passes: bool = False,
    include_recommendations: bool = False,
) -> list[tuple[str, str, str | None]]:
    """Generate contextual tips based on audit results and options used.

    Returns a list of (flag, description, example) tuples, max 2 tips.
    Tips are prioritized based on what would be most helpful given the context.
    Examples should use backticks for inline code styling.
    """
    tips = []
    is_single_engine = len(engine_list) == 1
    engine_name = engine_list[0] if is_single_engine else ""

    # Priority 1: Visualization tips (when issues found and not using badges)
    if issue_count > 0 and not show_badges:
        example = f"`inspekt a11y {engine_name} --show-badges --interactive`" if is_single_engine else "`inspekt a11y --show-badges --interactive`"
        tips.append((
            "--show-badges --interactive",
            "Visualize issues on page with clickable fix suggestions",
            example
        ))

    # Priority 2: Verbose tip (when not already verbose)
    if not verbose:
        example = f"`inspekt a11y {engine_name} --verbose`" if is_single_engine else "`inspekt a11y --verbose`"
        tips.append((
            "--verbose",
            "Show detailed per-rule breakdown with element counts",
            example
        ))

    # Priority 2b: JSON export tip (when already using verbose)
    if verbose:
        tips.append((
            "--json -o report.json",
            "Create a comprehensive (multi-engine) report",
            None
        ))

    # Priority 2c: Recommendations tip (when not already using recommendations)
    if not include_recommendations:
        tips.append((
            "--include-recommendations",
            "Include best practices and items that need manual review",
            None
        ))

    # Priority 3: Scope tip (when many issues found)
    if issue_count > 10:
        tips.append((
            "--scoped inspected",
            "Focus testing on the element you're inspecting in DevTools",
            None
        ))

    # Priority 4: Level tips
    if issue_count == 0 and level != "22aa":
        tips.append((
            "--level 22aa",
            "Test against stricter WCAG 2.2 AA criteria",
            None
        ))
    elif issue_count > 10 and level not in ("2a", "21a"):
        tips.append((
            "--level 2a",
            "Focus on Level A (most critical) issues first",
            None
        ))

    # Priority 5: Engine tips
    if is_single_engine:
        other_engines = [e for e in ["axe", "eac", "hcs", "sia"] if e != engine_name]
        tips.append((
            f"inspekt a11y {' '.join(other_engines[:2])}",
            "Try other engines for different perspectives on accessibility issues",
            None
        ))
    else:
        tips.append((
            "inspekt a11y <engine>",
            "Run a single engine for faster results",
            "`inspekt a11y --info` to list engines"
        ))

    # Priority 6: Show passes tip (when no issues and not already showing passes)
    if issue_count == 0 and not show_passes:
        tips.append((
            "--show-passes",
            "See which WCAG criteria are explicitly passing",
            None
        ))

    # Return max 3 tips
    return tips[:3]


def _extract_wcag_from_axe_tags(tags: list[str]) -> list[str]:
    """Extract WCAG SC numbers from Axe tags.

    Axe uses tags like 'wcag111' for 1.1.1, 'wcag143' for 1.4.3, etc.
    """
    import re
    wcag_scs = []
    for tag in tags:
        # Match patterns like wcag111, wcag143, wcag2411, etc.
        match = re.match(r'^wcag(\d)(\d)(\d+)$', tag)
        if match:
            p, g, sc = match.groups()
            wcag_scs.append(f"{p}.{g}.{sc}")
    return wcag_scs


def _extract_wcag_from_ibm(wcag_list: list[str]) -> list[str]:
    """Extract WCAG SC numbers from IBM wcag array.

    IBM returns WCAG SCs directly like ['1.1.1', '4.1.2'] or sometimes ['ARIA'].
    """
    import re
    wcag_scs = []
    for item in wcag_list:
        # Only include numeric SC (skip 'ARIA', etc.)
        if re.match(r'^\d+\.\d+\.\d+$', item):
            wcag_scs.append(item)
    return wcag_scs


def _extract_wcag_from_htmlcs_code(code: str) -> list[str]:
    """Extract WCAG SC numbers from HTMLCS code.

    HTMLCS uses codes like 'WCAG2AA.Principle1.Guideline1_3.1_3_1.H44'
    where '1_3_1' is the SC (1.3.1).
    """
    import re
    wcag_scs = []

    # Look for pattern like '1_3_1' in the code (SC with underscores)
    match = re.search(r'\.(\d+)_(\d+)_(\d+)\.', code)
    if match:
        p, g, sc = match.groups()
        wcag_scs.append(f"{p}.{g}.{sc}")

    return wcag_scs


def _extract_wcag_from_sia(requirements: list) -> list[str]:
    """Extract WCAG SC numbers from Alfa requirements.

    Alfa uses requirements like 'wcag:1.1.1' or 'wcag:2.4.4'.
    """
    import re
    wcag_scs = []

    for req in requirements:
        if isinstance(req, str):
            # Format: 'wcag:1.1.1' or 'wcag21:1.4.11'
            match = re.search(r'wcag\d*:(\d+\.\d+\.\d+)', req)
            if match:
                wcag_scs.append(match.group(1))

    return wcag_scs


def _get_tool_versions() -> dict[str, str]:
    """Load tool versions from version JSON files."""
    versions = {"axe": "unknown", "eac": "unknown", "hcs": "unknown", "sia": "unknown"}

    axe_version_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "axe-core.version.json"
    ibm_version_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "ace.version.json"
    htmlcs_version_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "htmlcs.version.json"
    sia_version_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "sia.version.json"

    try:
        if axe_version_path.exists():
            with builtin_open(axe_version_path) as f:
                data = json.load(f)
                versions["axe"] = data.get("version", "unknown")
    except Exception:
        pass

    try:
        if ibm_version_path.exists():
            with builtin_open(ibm_version_path) as f:
                data = json.load(f)
                versions["eac"] = data.get("version", "unknown")
    except Exception:
        pass

    try:
        if htmlcs_version_path.exists():
            with builtin_open(htmlcs_version_path) as f:
                data = json.load(f)
                versions["hcs"] = data.get("version", "unknown")
    except Exception:
        pass

    try:
        if sia_version_path.exists():
            with builtin_open(sia_version_path) as f:
                data = json.load(f)
                versions["sia"] = data.get("version", "unknown")
    except Exception:
        pass

    return versions


# Cache duration for npm release dates (1 day in seconds)
_RELEASE_DATE_CACHE_TTL = 86400

# Engine ID to npm package mapping
_ENGINE_NPM_PACKAGES = {
    "axe": "axe-core",
    "eac": "accessibility-checker-engine",
    "hcs": "html_codesniffer",
    "sia": "@siteimprove/alfa-rules",
}


def _get_release_date_cache_path() -> Path:
    """Get path to the release date cache file."""
    cache_dir = Path(__file__).parent.parent.parent.parent / ".cache"
    cache_dir.mkdir(exist_ok=True)
    return cache_dir / "engine_release_dates.json"


def _fetch_npm_release_date(package: str, version: str, timeout: float = 5.0) -> str | None:
    """Fetch release date for a specific package version from npm."""
    from inspekt.services import http_client

    try:
        url = f"https://registry.npmjs.org/{package}"
        response = http_client.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        times = data.get("time", {})
        if version and version in times:
            # Parse ISO date and return just the date part
            date_str = times[version]
            return date_str[:10]  # "2025-12-10T12:19:48.474Z" -> "2025-12-10"
    except Exception:
        pass

    return None


def _get_engine_release_dates(versions: dict[str, str]) -> dict[str, str]:
    """
    Get release dates for installed engine versions.

    Uses a 1-day cache to avoid hitting npm on every call.
    Falls back to hardcoded dates from engines.json if fetch fails.
    """
    from inspekt.data import load_engine_metadata

    # Load fallback dates from engines.json
    metadata = load_engine_metadata()
    fallback_dates = {
        engine_id: info.get("latest_update", "unknown")
        for engine_id, info in metadata.items()
    }

    cache_path = _get_release_date_cache_path()
    cached_data = {}
    cache_valid = False

    # Try to load cached data
    try:
        if cache_path.exists():
            with builtin_open(cache_path) as f:
                cached_data = json.load(f)

            # Check if cache is still valid (less than 1 day old)
            cache_time = cached_data.get("_timestamp", 0)
            if time.time() - cache_time < _RELEASE_DATE_CACHE_TTL:
                cache_valid = True
    except Exception:
        pass

    # If cache is valid, return cached dates (with fallbacks for missing)
    if cache_valid:
        result = {}
        for engine_id in versions:
            version = versions[engine_id]
            cache_key = f"{engine_id}:{version}"
            if cache_key in cached_data:
                result[engine_id] = cached_data[cache_key]
            else:
                result[engine_id] = fallback_dates.get(engine_id, "unknown")
        return result

    # Fetch fresh dates from npm
    result = {}
    new_cache = {"_timestamp": time.time()}

    for engine_id, version in versions.items():
        if version == "unknown":
            result[engine_id] = fallback_dates.get(engine_id, "unknown")
            continue

        package = _ENGINE_NPM_PACKAGES.get(engine_id)
        if not package:
            result[engine_id] = fallback_dates.get(engine_id, "unknown")
            continue

        # Try to fetch from npm
        release_date = _fetch_npm_release_date(package, version)

        if release_date:
            result[engine_id] = release_date
            new_cache[f"{engine_id}:{version}"] = release_date
        else:
            # Fall back to hardcoded date
            result[engine_id] = fallback_dates.get(engine_id, "unknown")

    # Save cache (silently ignore errors)
    try:
        with builtin_open(cache_path, "w") as f:
            json.dump(new_cache, f)
    except Exception:
        pass

    return result


def _run_axe_audit(client, level: str, timeout: float, include_recommendations: bool = False) -> dict:
    """Run Axe audit and return results."""
    axe_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "axe-core.min.js"
    script_path = Path(__file__).parent.parent.parent / "scripts" / "run_axe.js"

    if not axe_lib_path.exists():
        return {"error": "axe-core not found", "violations": [], "passes": []}

    try:
        # Load engine tracker first (prevents re-injection)
        _load_engine_tracker(client)

        with builtin_open(axe_lib_path) as f:
            axe_lib = f.read()
        with builtin_open(script_path) as f:
            audit_script = f.read()

        # Build minimal config - include incomplete when recommendations requested
        config = _build_axe_config(level, None, True, include_recommendations)
        config["__showBadges"] = False  # No badges for combined

        # Exclude Inspekt UI elements from the scan (axe native exclude option)
        config["exclude"] = INSPEKT_UI_SELECTORS

        # Replace placeholder
        audit_script = audit_script.replace("__AXE_CONFIG__", json.dumps(config))

        # Check if axe is already loaded (skip injection if so)
        if not _is_engine_loaded(client, 'axe'):
            # Inject library
            axe_lib_wrapped = f"(function() {{ {axe_lib} return typeof axe !== 'undefined'; }})()"
            result = client.execute(axe_lib_wrapped, timeout=15.0)
            if not result.get("ok") or not result.get("result"):
                return {"error": "Failed to load axe-core", "violations": [], "passes": []}
            # Mark engine as loaded
            _mark_engine_loaded(client, 'axe')

        # Run audit
        result = client.execute(audit_script, timeout=timeout)
        if not result.get("ok"):
            return {"error": result.get("error"), "violations": [], "passes": []}

        data = result.get("result", {})
        if not data.get("ok"):
            return {"error": data.get("error"), "violations": [], "passes": []}

        return {
            "violations": data.get("violations", []),
            "passes": data.get("passes", []),
            "incomplete": data.get("incomplete", []),
            "url": data.get("url", ""),
        }
    except Exception as e:
        return {"error": str(e), "violations": [], "passes": []}


def _run_ibm_audit(client, level: str, timeout: float, include_recommendations: bool = False) -> dict:
    """Run IBM Equal Access audit and return results."""
    ace_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "ace.min.js"
    script_path = Path(__file__).parent.parent.parent / "scripts" / "run_ibm.js"

    if not ace_lib_path.exists():
        return {"error": "IBM Equal Access not found", "issues": [], "summary": {}}

    try:
        # Load engine tracker first (prevents re-injection)
        _load_engine_tracker(client)

        with builtin_open(ace_lib_path) as f:
            ace_lib = f.read()
        with builtin_open(script_path) as f:
            audit_script = f.read()

        # Build config - include recommendations when requested
        config = _build_ibm_config(level, True, include_recommendations)
        config["__showBadges"] = False  # No badges for combined

        # Replace placeholder
        audit_script = audit_script.replace("__IBM_CONFIG__", json.dumps(config))

        # Check if ace is already loaded (skip injection if so)
        if not _is_engine_loaded(client, 'ace'):
            # Inject library
            ace_lib_wrapped = f"(function() {{ {ace_lib}; window.ace = ace; return typeof window.ace !== 'undefined'; }})()"
            result = client.execute(ace_lib_wrapped, timeout=15.0)
            if not result.get("ok") or not result.get("result"):
                return {"error": "Failed to load IBM Equal Access", "issues": [], "summary": {}}
            # Mark engine as loaded
            _mark_engine_loaded(client, 'ace')

        # Run audit
        result = client.execute(audit_script, timeout=timeout)
        if not result.get("ok"):
            return {"error": result.get("error"), "issues": [], "summary": {}}

        data = result.get("result", {})
        if not data.get("ok"):
            return {"error": data.get("error"), "issues": [], "summary": {}}

        audit_result = data.get("result", {})

        # Filter out violations from Inspekt's own UI elements
        issues = audit_result.get("issues", [])
        issues = _filter_inspekt_ui_violations(issues, selector_key='path')

        return {
            "issues": issues,
            "summary": audit_result.get("summary", {}),
            "url": audit_result.get("url", ""),
        }
    except Exception as e:
        return {"error": str(e), "issues": [], "summary": {}}


def _run_htmlcs_audit(client, level: str, timeout: float, include_recommendations: bool = False) -> dict:
    """Run HTML_CodeSniffer audit and return results."""
    htmlcs_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "htmlcs.min.js"
    script_path = Path(__file__).parent.parent.parent / "scripts" / "run_htmlcs.js"

    if not htmlcs_lib_path.exists():
        return {"error": "HTML_CodeSniffer not found", "messages": [], "summary": {}}

    try:
        # Load engine tracker first (prevents re-injection)
        _load_engine_tracker(client)

        with builtin_open(htmlcs_lib_path) as f:
            htmlcs_lib = f.read()
        with builtin_open(script_path) as f:
            audit_script = f.read()

        # Build config - map WCAG level to HTMLCS standard
        level_mapping = {
            "2a": "WCAG2A",
            "2aa": "WCAG2AA",
            "2aaa": "WCAG2AAA",
            "21a": "WCAG2A",
            "21aa": "WCAG2AA",
            "22aa": "WCAG2AA",  # HTMLCS doesn't support 2.2 yet
        }
        standard = level_mapping.get(level.lower(), "WCAG2AA")

        config = {
            "standard": standard,
            "includeNotices": include_recommendations,  # Notices = best practices
            "includeWarnings": True,
        }

        # Replace placeholder
        audit_script = audit_script.replace("__HTMLCS_CONFIG__", json.dumps(config))

        # Check if htmlcs is already loaded (skip injection if so)
        if not _is_engine_loaded(client, 'htmlcs'):
            # Inject library
            htmlcs_lib_wrapped = f"(function() {{ {htmlcs_lib}; return typeof HTMLCS !== 'undefined'; }})()"
            result = client.execute(htmlcs_lib_wrapped, timeout=15.0)
            if not result.get("ok") or not result.get("result"):
                return {"error": "Failed to load HTML_CodeSniffer", "messages": [], "summary": {}}
            # Mark engine as loaded
            _mark_engine_loaded(client, 'htmlcs')

        # Run audit
        result = client.execute(audit_script, timeout=timeout)
        if not result.get("ok"):
            return {"error": result.get("error"), "messages": [], "summary": {}}

        data = result.get("result", {})
        if not data.get("ok"):
            return {"error": data.get("error"), "messages": [], "summary": {}}

        # Filter out violations from Inspekt's own UI elements
        messages = data.get("messages", [])
        messages = _filter_inspekt_ui_violations(messages, selector_key='selector')

        return {
            "messages": messages,
            "summary": data.get("summary", {}),
            "url": data.get("url", ""),
        }
    except Exception as e:
        return {"error": str(e), "messages": [], "summary": {}}


def _run_sia_audit(client, level: str, timeout: float, include_recommendations: bool = False) -> dict:
    """Run Alfa audit and return results."""
    sia_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "sia.min.js"
    script_path = Path(__file__).parent.parent.parent / "scripts" / "run_sia.js"
    version_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "sia.version.json"

    if not sia_lib_path.exists():
        return {"error": "Alfa not found", "outcomes": [], "summary": {}}

    try:
        # Load engine tracker first (prevents re-injection)
        _load_engine_tracker(client)

        with builtin_open(sia_lib_path, encoding="utf-8") as f:
            sia_lib = f.read()
        with builtin_open(script_path, encoding="utf-8") as f:
            audit_script = f.read()

        # Get version for injection
        version = "unknown"
        try:
            if version_path.exists():
                with builtin_open(version_path) as f:
                    version = json.load(f).get("version", "unknown")
        except Exception:
            pass

        # Build config - map WCAG level to Alfa conformance
        level_mapping = {
            "2a": "WCAG2.0:A",
            "2aa": "WCAG2.0:AA",
            "2aaa": "WCAG2.0:AAA",
            "21a": "WCAG2.1:A",
            "21aa": "WCAG2.1:AA",
            "22aa": "WCAG2.2:AA",
        }
        conformance = level_mapping.get(level.lower(), "WCAG2.2:AA")

        config = {
            "conformance": conformance,
            "includePassed": False,
            "includeCantTell": include_recommendations,  # cantTell = needs manual review
            "includeInapplicable": False,
            "__version__": version,
        }

        # Replace placeholder
        audit_script = audit_script.replace("__SIA_CONFIG__", json.dumps(config))

        # Check if sia is already loaded (skip injection if so)
        if not _is_engine_loaded(client, 'sia'):
            # Inject library - Alfa uses 'var Alfa=' so we need to explicitly export to window
            sia_lib_wrapped = f"(function() {{ {sia_lib}; window.Alfa = Alfa; return typeof window.Alfa !== 'undefined'; }})()"
            result = client.execute(sia_lib_wrapped, timeout=30.0)
            if not result.get("ok") or not result.get("result"):
                return {"error": "Failed to load Alfa", "outcomes": [], "summary": {}}
            # Mark engine as loaded
            _mark_engine_loaded(client, 'sia')

        # Run audit
        result = client.execute(audit_script, timeout=timeout)
        if not result.get("ok"):
            return {"error": result.get("error"), "outcomes": [], "summary": {}}

        data = result.get("result", {})
        if not data.get("ok"):
            # Include stack trace for debugging
            error_msg = data.get("error", "Unknown error")
            stack = data.get("stack", "")
            return {"error": error_msg, "stack": stack, "outcomes": [], "summary": {}}

        # Filter out violations from Inspekt's own UI elements
        outcomes = data.get("outcomes", [])
        outcomes = _filter_inspekt_ui_violations(outcomes, selector_key='target')

        return {
            "outcomes": outcomes,
            "summary": data.get("summary", {}),
            "url": data.get("url", ""),
            "version": data.get("version", version),
        }
    except Exception as e:
        return {"error": str(e), "outcomes": [], "summary": {}}


def _inject_badges_into_page(client, engine_list: list, level: str, timeout: float, interactive: bool, dev_css: bool, include_recommendations: bool = False):
    """Inject accessibility badges into the current page.

    Called after the main CLI audit output is complete. Runs the unified audit script
    to create clickable badges on elements with violations. Note that this runs the
    audits again in the browser to create proper badge attachments.

    Supports any combination of engines: axe, eac, hcs, sia.

    Args:
        include_recommendations: If True, also show badges for recommendations (dotted outline)
    """
    # Engine library configuration
    ENGINE_LIBS = {
        "axe": ("axe-core.min.js", "axe-core"),
        "eac": ("ace.min.js", "IBM Equal Access"),
        "hcs": ("htmlcs.min.js", "HTML CodeSniffer"),
        "sia": ("sia.min.js", "Siteimprove Alfa"),
    }

    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    vendor_dir = scripts_dir / "vendor"

    # Required shared scripts
    popover_core_path = scripts_dir / "shared-popover" / "popover-core.js"
    popover_content_path = scripts_dir / "shared-popover" / "popover-content.js"
    a11y_script_path = scripts_dir / "run_a11y.js"

    # Check shared files exist
    for path, name in [(popover_core_path, "popover-core"), (popover_content_path, "popover-content"),
                       (a11y_script_path, "run_a11y")]:
        if not path.exists():
            click.echo(click.style(f"Warning: Could not inject badges ({name} not found)", fg="yellow"), err=True)
            return

    # Build list of engine libraries to load
    engine_libs_to_load = []
    for engine_id in engine_list:
        if engine_id in ENGINE_LIBS:
            lib_file, lib_name = ENGINE_LIBS[engine_id]
            lib_path = vendor_dir / lib_file
            if not lib_path.exists():
                click.echo(click.style(f"Warning: Could not inject badges ({lib_name} not found)", fg="yellow"), err=True)
                return
            engine_libs_to_load.append((engine_id, lib_path, lib_name))

    # Show brief progress
    click.echo(err=True)
    click.echo(click.style("Injecting badges…", bold=True), err=True)

    try:
        # Load shared scripts
        with builtin_open(popover_core_path) as f:
            popover_core = f.read()
        with builtin_open(popover_content_path) as f:
            popover_content = f.read()
        with builtin_open(a11y_script_path) as f:
            a11y_script = f.read()

        # Load engine libraries
        engine_libs = {}
        for engine_id, lib_path, _lib_name in engine_libs_to_load:
            with builtin_open(lib_path) as f:
                engine_libs[engine_id] = f.read()

        # Build config with engine list and per-engine configs
        config = {
            "__showBadges": True,
            "__interactiveBadges": interactive,
            "__devCss": dev_css,
            "__engines": engine_list,
            "__includeRecommendations": include_recommendations,
        }

        # Add engine-specific configs
        if "axe" in engine_list:
            config["axeRunOnly"] = _get_axe_run_only(level)
            config["axeExclude"] = INSPEKT_UI_SELECTORS  # Exclude Inspekt UI from scan
        if "eac" in engine_list:
            config["ibmGuidelines"] = _get_ibm_guidelines(level)
            if include_recommendations:
                # Add recommendation levels for IBM
                config["ibmReportLevels"] = ["violation", "potentialviolation", "recommendation", "potentialrecommendation"]
        if "hcs" in engine_list:
            config["hcsStandard"] = _get_hcs_standard(level)
            if include_recommendations:
                config["hcsIncludeNotices"] = True
        if "sia" in engine_list:
            config["siaConformance"] = _get_sia_conformance(level)
            if include_recommendations:
                config["siaIncludeCantTell"] = True

        # Replace config placeholder
        a11y_script = a11y_script.replace("__A11Y_CONFIG__", json.dumps(config))

        # Inject engine libraries dynamically
        ENGINE_WRAPPERS = {
            "axe": lambda lib: f"(function() {{ {lib} return typeof axe !== 'undefined'; }})()",
            "eac": lambda lib: f"(function() {{ {lib}; window.ace = ace; return typeof window.ace !== 'undefined'; }})()",
            "hcs": lambda lib: f"(function() {{ {lib}; return typeof HTMLCS !== 'undefined'; }})()",
            "sia": lambda lib: f"(function() {{ {lib}; window.Alfa = Alfa; return typeof window.Alfa !== 'undefined'; }})()",
        }

        for engine_id, _lib_path, lib_name in engine_libs_to_load:
            lib_content = engine_libs[engine_id]
            wrapped = ENGINE_WRAPPERS[engine_id](lib_content)
            result = client.execute(wrapped, timeout=15.0)
            if not result.get("ok") or not result.get("result"):
                click.echo(click.style(f"  Warning: Failed to load {lib_name}", fg="yellow"), err=True)
                return

        # Inject popover core
        result = client.execute(popover_core, timeout=5.0)
        if not result.get("ok"):
            click.echo(click.style("  Warning: Failed to load popover core", fg="yellow"), err=True)
            return

        # Inject popover content
        result = client.execute(popover_content, timeout=5.0)
        if not result.get("ok"):
            click.echo(click.style("  Warning: Failed to load popover content", fg="yellow"), err=True)
            return

        # Run unified audit (creates badges)
        result = client.execute(a11y_script, timeout=timeout)

        if not result.get("ok"):
            click.echo(click.style(f"  Warning: Badge injection failed - {result.get('error')}", fg="yellow"), err=True)
            return

        data = result.get("result", {})
        if not data.get("ok"):
            click.echo(click.style(f"  Warning: Badge injection failed - {data.get('error')}", fg="yellow"), err=True)
            return

        audit_result = data.get("result", {})
        badge_stats = audit_result.get("badgeStats", {})

        if badge_stats:
            badges_created = badge_stats.get("badgesCreated", 0)
            click.echo(click.style(f"  Created {badges_created} clickable {pluralize(badges_created, 'badge')}", fg="green"), err=True)

            if interactive:
                click.echo(click.style("  Click any badge to see details. Use arrow keys to navigate.", fg="bright_black"), err=True)
        else:
            click.echo(click.style("  No badges created (no elements with violations found)", fg="bright_black"), err=True)
            # Show Alfa-specific note if it's the only engine
            if engine_list == ["sia"]:
                click.echo(click.style("  Note: Alfa's bundled format doesn't provide element references.", fg="bright_black"), err=True)
                click.echo(click.style("  Use `inspekt a11y axe sia` to see Alfa issues in combined badges.", fg="bright_black"), err=True)

    except Exception as e:
        click.echo(click.style(f"  Warning: Badge injection failed - {e}", fg="yellow"), err=True)


def _run_unified_a11y_with_badges(client, engine_list: list, level: str, timeout: float, interactive: bool, dev_css: bool, url: str, versions: dict):
    """Run unified a11y audit with badges injected into the page.

    Note: This function is now deprecated. Use the main a11y() command with --show-badges
    which calls _inject_badges_into_page() after showing the comprehensive CLI output.

    Supports any combination of engines: axe, eac, hcs, sia.
    """
    # Engine library configuration
    ENGINE_LIBS = {
        "axe": ("axe-core.min.js", "axe-core"),
        "eac": ("ace.min.js", "IBM Equal Access"),
        "hcs": ("htmlcs.min.js", "HTML CodeSniffer"),
        "sia": ("sia.min.js", "Siteimprove Alfa"),
    }

    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    vendor_dir = scripts_dir / "vendor"

    # Required shared scripts
    popover_core_path = scripts_dir / "shared-popover" / "popover-core.js"
    popover_content_path = scripts_dir / "shared-popover" / "popover-content.js"
    a11y_script_path = scripts_dir / "run_a11y.js"

    # Check shared files exist
    for path, name in [(popover_core_path, "popover-core"), (popover_content_path, "popover-content"),
                       (a11y_script_path, "run_a11y")]:
        if not path.exists():
            click.echo(click.style(f"Error: {name} not found at {path}", fg="red"), err=True)
            return

    # Build list of engine libraries to load
    engine_libs_to_load = []
    for engine_id in engine_list:
        if engine_id in ENGINE_LIBS:
            lib_file, lib_name = ENGINE_LIBS[engine_id]
            lib_path = vendor_dir / lib_file
            if not lib_path.exists():
                click.echo(click.style(f"Error: {lib_name} not found at {lib_path}", fg="red"), err=True)
                return
            engine_libs_to_load.append((engine_id, lib_path, lib_name))

    # Show progress
    click.echo(click.style("Running Accessibility Audit with Badges", bold=True), err=True)
    click.echo(f"URL: {url}", err=True)
    click.echo(err=True)

    # Show engines being used
    engine_names = [AVAILABLE_ENGINES[e]['name'] for e in engine_list if e in AVAILABLE_ENGINES]
    click.echo(f"Engines: {', '.join(engine_names)}", err=True)
    click.echo(err=True)

    try:
        # Load shared scripts
        with builtin_open(popover_core_path) as f:
            popover_core = f.read()
        with builtin_open(popover_content_path) as f:
            popover_content = f.read()
        with builtin_open(a11y_script_path) as f:
            a11y_script = f.read()

        # Load engine libraries
        engine_libs = {}
        for engine_id, lib_path, _lib_name in engine_libs_to_load:
            with builtin_open(lib_path) as f:
                engine_libs[engine_id] = f.read()

        # Build config with engine list and per-engine configs
        config = {
            "__showBadges": True,
            "__interactiveBadges": interactive,
            "__devCss": dev_css,
            "__engines": engine_list,
        }

        # Add engine-specific configs
        if "axe" in engine_list:
            config["axeRunOnly"] = _get_axe_run_only(level)
            config["axeExclude"] = INSPEKT_UI_SELECTORS  # Exclude Inspekt UI from scan
        if "eac" in engine_list:
            config["ibmGuidelines"] = _get_ibm_guidelines(level)
        if "hcs" in engine_list:
            config["hcsStandard"] = _get_hcs_standard(level)
        if "sia" in engine_list:
            config["siaConformance"] = _get_sia_conformance(level)

        # Replace config placeholder
        a11y_script = a11y_script.replace("__A11Y_CONFIG__", json.dumps(config))

        # Calculate total steps: engine libs + popover core + popover content + audit
        total_steps = len(engine_libs_to_load) + 3
        current_step = 0

        # Inject engine libraries dynamically
        # Each wrapper ensures the library is globally accessible
        ENGINE_WRAPPERS = {
            "axe": lambda lib: f"(function() {{ {lib} return typeof axe !== 'undefined'; }})()",
            "eac": lambda lib: f"(function() {{ {lib}; window.ace = ace; return typeof window.ace !== 'undefined'; }})()",
            "hcs": lambda lib: f"(function() {{ {lib}; return typeof HTMLCS !== 'undefined'; }})()",
            "sia": lambda lib: f"(function() {{ {lib}; window.Alfa = Alfa; return typeof window.Alfa !== 'undefined'; }})()",
        }

        for engine_id, _lib_path, lib_name in engine_libs_to_load:
            current_step += 1
            click.echo(f"  {current_step}/{total_steps} Injecting {lib_name}…", err=True)
            lib_content = engine_libs[engine_id]
            wrapped = ENGINE_WRAPPERS[engine_id](lib_content)
            result = client.execute(wrapped, timeout=15.0)
            if not result.get("ok") or not result.get("result"):
                click.echo(click.style(f"      Failed to load {lib_name}", fg="red"), err=True)
                return

        # Inject popover core
        current_step += 1
        click.echo(f"  {current_step}/{total_steps} Injecting popover core…", err=True)
        result = client.execute(popover_core, timeout=5.0)
        if not result.get("ok"):
            click.echo(click.style("      Failed to load popover core", fg="red"), err=True)
            return

        # Inject popover content
        current_step += 1
        click.echo(f"  {current_step}/{total_steps} Injecting popover content…", err=True)
        result = client.execute(popover_content, timeout=5.0)
        if not result.get("ok"):
            click.echo(click.style("      Failed to load popover content", fg="red"), err=True)
            return

        # Run unified audit
        current_step += 1
        click.echo(f"  {current_step}/{total_steps} Running unified audit…", err=True)
        result = client.execute(a11y_script, timeout=timeout)

        if not result.get("ok"):
            click.echo(click.style(f"        Error: {result.get('error')}", fg="red"), err=True)
            return

        data = result.get("result", {})
        if not data.get("ok"):
            click.echo(click.style(f"        Error: {data.get('error')}", fg="red"), err=True)
            return

        audit_result = data.get("result", {})
        badge_stats = audit_result.get("badgeStats", {})
        engine_stats = audit_result.get("engineStats", {})

        click.echo(err=True)
        click.echo(click.style("Audit Complete!", fg="green", bold=True))
        click.echo()

        # Display per-engine stats dynamically using names from AVAILABLE_ENGINES
        for engine_id in engine_list:
            if engine_id in AVAILABLE_ENGINES:
                engine_name = AVAILABLE_ENGINES[engine_id]["name"]
                count = engine_stats.get(engine_id, {}).get("count", 0)
                click.echo(f"  {engine_name}: {count}")

        click.echo()

        if badge_stats:
            click.echo(click.style(f"Badges created: {badge_stats.get('badgesCreated', 0)}", bold=True))

            # Show per-engine breakdown if multiple engines
            if len(engine_list) > 1:
                per_engine = badge_stats.get("perEngine", {})
                for engine_id in engine_list:
                    if engine_id in per_engine:
                        engine_name = AVAILABLE_ENGINES.get(engine_id, {}).get("name", engine_id)
                        click.echo(f"  {engine_name} only: {per_engine[engine_id]}")
                combined = badge_stats.get("withMultipleSources", badge_stats.get("withBothSources", 0))
                if combined > 0:
                    click.echo(f"  Multiple engines: {combined}")

            if interactive:
                click.echo()
                click.echo(click.style("Click any badge to see details. Use arrow keys to navigate.", fg="bright_black"))
        else:
            click.echo(click.style("No issues found - no badges created.", fg="green"))

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)


def _get_axe_run_only(level: str) -> dict:
    """Get axe-core runOnly config for a WCAG level."""
    level_tags = {
        "2a": ["wcag2a"],
        "2aa": ["wcag2a", "wcag2aa"],
        "2aaa": ["wcag2a", "wcag2aa", "wcag2aaa"],
        "21a": ["wcag2a", "wcag21a"],
        "21aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        "22aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
    }
    tags = level_tags.get(level, ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    return {"type": "tag", "values": tags}


def _get_ibm_guidelines(level: str) -> list:
    """Get IBM guidelines for a WCAG level."""
    level_guidelines = {
        "2a": ["WCAG_2_0"],
        "2aa": ["WCAG_2_0"],
        "2aaa": ["WCAG_2_0"],
        "21a": ["WCAG_2_1"],
        "21aa": ["WCAG_2_1"],
        "22aa": ["WCAG_2_2"],
    }
    return level_guidelines.get(level, ["WCAG_2_2"])


def _get_hcs_standard(level: str) -> str:
    """Get HTML CodeSniffer standard for a WCAG level."""
    # HTMLCS only supports up to WCAG 2.1
    level_standards = {
        "2a": "WCAG2A",
        "2aa": "WCAG2AA",
        "2aaa": "WCAG2AAA",
        "21a": "WCAG2A",
        "21aa": "WCAG2AA",
        "22aa": "WCAG2AA",  # Falls back to 2.1 AA
    }
    return level_standards.get(level, "WCAG2AA")


def _get_sia_conformance(level: str) -> str:
    """Get Siteimprove Alfa conformance level."""
    level_conformance = {
        "2a": "WCAG2.0:A",
        "2aa": "WCAG2.0:AA",
        "2aaa": "WCAG2.0:AAA",
        "21a": "WCAG2.1:A",
        "21aa": "WCAG2.1:AA",
        "22aa": "WCAG2.2:AA",
    }
    return level_conformance.get(level, "WCAG2.2:AA")


def _consolidate_by_wcag(axe_results: dict, ibm_results: dict) -> dict:
    """Consolidate Axe and IBM results by WCAG Success Criterion."""
    consolidated = {}

    # Process Axe violations
    for violation in axe_results.get("violations", []):
        tags = violation.get("tags", [])
        wcag_scs = _extract_wcag_from_axe_tags(tags)
        count = violation.get("nodeCount", len(violation.get("nodes", [])))
        impact = violation.get("impact", "unknown")

        for sc in wcag_scs:
            if sc not in consolidated:
                consolidated[sc] = {
                    "axe_status": "pass",
                    "axe_count": 0,
                    "axe_impact": None,
                    "ibm_status": "pass",
                    "ibm_count": 0,
                    "ibm_level": None,
                }
            # Set to worst status
            if consolidated[sc]["axe_status"] == "pass" or \
               (consolidated[sc]["axe_status"] == "incomplete" and impact in ["critical", "serious"]):
                consolidated[sc]["axe_status"] = "violation"
            consolidated[sc]["axe_count"] += count
            if consolidated[sc]["axe_impact"] is None or \
               ["minor", "moderate", "serious", "critical"].index(impact) > \
               ["minor", "moderate", "serious", "critical"].index(consolidated[sc]["axe_impact"] or "minor"):
                consolidated[sc]["axe_impact"] = impact

    # Process Axe incomplete
    for incomplete in axe_results.get("incomplete", []):
        tags = incomplete.get("tags", [])
        wcag_scs = _extract_wcag_from_axe_tags(tags)
        count = incomplete.get("nodeCount", len(incomplete.get("nodes", [])))

        for sc in wcag_scs:
            if sc not in consolidated:
                consolidated[sc] = {
                    "axe_status": "pass",
                    "axe_count": 0,
                    "axe_impact": None,
                    "ibm_status": "pass",
                    "ibm_count": 0,
                    "ibm_level": None,
                }
            if consolidated[sc]["axe_status"] == "pass":
                consolidated[sc]["axe_status"] = "incomplete"
                consolidated[sc]["axe_count"] += count

    # Process IBM issues
    for issue in ibm_results.get("issues", []):
        level = issue.get("level", "violation")
        rule_id = issue.get("ruleId", "")

        # Get WCAG SCs from issue or static mapping
        wcag_list = issue.get("wcag", [])
        wcag_scs = _extract_wcag_from_ibm(wcag_list)

        # Fall back to static mapping if no WCAG in issue
        if not wcag_scs and rule_id in IBM_RULE_TO_WCAG:
            wcag_scs = IBM_RULE_TO_WCAG[rule_id]

        if not wcag_scs:
            continue

        for sc in wcag_scs:
            if sc not in consolidated:
                consolidated[sc] = {
                    "axe_status": "pass",
                    "axe_count": 0,
                    "axe_impact": None,
                    "ibm_status": "pass",
                    "ibm_count": 0,
                    "ibm_level": None,
                }

            if level == "pass":
                continue  # Don't override with pass

            # Set to worst status
            level_priority = {"pass": 0, "manual": 1, "recommendation": 2,
                            "potentialrecommendation": 2, "potentialviolation": 3, "violation": 4}
            current_priority = level_priority.get(consolidated[sc]["ibm_status"], 0)
            new_priority = level_priority.get(level, 0)

            if new_priority > current_priority:
                consolidated[sc]["ibm_status"] = level
                consolidated[sc]["ibm_level"] = level
            consolidated[sc]["ibm_count"] += 1

    return consolidated


def _run_engines_in_order(
    client,
    engine_list: list[str],
    level: str,
    timeout: float,
    versions: dict[str, str],
    quiet: bool = False,
    include_recommendations: bool = False
) -> dict[str, dict]:
    """
    Run accessibility engines in specified order.

    Engines are run sequentially to ensure consistent behavior when
    scripts have DOM side effects.

    Args:
        client: Bridge client for browser communication
        engine_list: List of engine names in execution order
        level: WCAG level to test
        timeout: Timeout per engine
        versions: Dict of engine versions
        quiet: If True, suppress all progress output (for JSON mode)
        include_recommendations: If True, include recommendations/best practices

    Returns:
        Dict mapping engine name to its results
    """
    results = {}
    total = len(engine_list)
    is_single = total == 1

    # Import metadata lookup
    from inspekt.data import get_engine_metadata, get_engine_provider

    for idx, engine in enumerate(engine_list, 1):
        engine_info = AVAILABLE_ENGINES[engine]
        version = versions.get(engine, "unknown")
        provider = get_engine_provider(engine)
        metadata = get_engine_metadata(engine)
        reports_potential = metadata.get("reports_potential_violations", False)

        # Build styled engine name (bright yellow) with provider
        styled_name = click.style(engine_info['name'], fg="bright_yellow")
        name_with_provider = f"{styled_name} by {provider}"

        # Use simpler format for single engine
        if not quiet:
            if is_single:
                click.echo(f"Running {name_with_provider} ({version})…", err=True)
            else:
                click.echo(f"  {idx}/{total} Running {name_with_provider} ({version})…", err=True)

        start_time = time.time()
        try:
            if engine == "axe":
                engine_result = _run_axe_audit(client, level, timeout, include_recommendations)
            elif engine == "eac":
                engine_result = _run_ibm_audit(client, level, timeout, include_recommendations)
            elif engine == "hcs":
                engine_result = _run_htmlcs_audit(client, level, timeout, include_recommendations)
            elif engine == "sia":
                engine_result = _run_sia_audit(client, level, timeout, include_recommendations)
            else:
                engine_result = {"error": f"Unknown engine: {engine}"}

            results[engine] = engine_result
            elapsed = time.time() - start_time

            # Report progress (simpler indent for single engine)
            if not quiet:
                indent = "  " if is_single else "      "
                if engine_result.get("error"):
                    error_msg = engine_result['error']
                    # Provide more user-friendly messages for known Alfa errors
                    if engine == "sia" and "withoutFragment" in error_msg:
                        msg = warn_icon("Skipped (internal library error on this page)")
                        click.echo(click.style(f"{indent}{msg}", fg="yellow"), err=True)
                        bug_msg = bug("This is a known issue with Alfa on some pages")
                        click.echo(click.style(f"{indent}{bug_msg}", fg="bright_black"), err=True)
                    else:
                        msg = warn_icon(f"Warning: {error_msg}")
                        click.echo(click.style(f"{indent}{msg}", fg="yellow"), err=True)
                else:
                    v_count = _count_violations(engine_result, engine)
                    potential_qualifier = " (potential)" if reports_potential else ""
                    if v_count == 0:
                        # No violations - celebrate!
                        msg = celebrate(f"No{potential_qualifier} violations found")
                        click.echo(click.style(f"{indent}{msg}", fg="green"), err=True)
                    else:
                        # Found violations - use alert icon
                        # Include recommendations count when --include-recommendations is used
                        if include_recommendations:
                            rec_count = _count_recommendations(engine_result, engine)
                            if rec_count > 0:
                                msg = alert(f"Found {v_count}{potential_qualifier} {pluralize(v_count, 'violation')} (and {rec_count} {pluralize(rec_count, 'recommendation')})")
                            else:
                                msg = alert(f"Found {v_count}{potential_qualifier} {pluralize(v_count, 'violation')}")
                        else:
                            msg = alert(f"Found {v_count}{potential_qualifier} {pluralize(v_count, 'violation')}")
                        click.echo(click.style(f"{indent}{msg}", fg="yellow"), err=True)
                # Time elapsed with stopwatch icon
                time_msg = stopwatch(f"Took {elapsed:.1f} seconds")
                click.echo(click.style(f"{indent}{time_msg}", fg="bright_black"), err=True)

        except Exception as e:
            elapsed = time.time() - start_time
            if not quiet:
                indent = "  " if is_single else "      "
                click.echo(click.style(f"{indent}Error: {e}", fg="red"), err=True)
                time_msg = stopwatch(f"Took {elapsed:.1f} seconds")
                click.echo(click.style(f"{indent}{time_msg}", fg="bright_black"), err=True)
            results[engine] = {"error": str(e)}

    return results


def _count_violations(result: dict, engine: str) -> int:
    """Count violations from engine result.

    For Alfa, returns rule count (not element count) to match other engines.
    """
    if engine == "axe":
        return len(result.get("violations", []))
    elif engine == "eac":
        return result.get("summary", {}).get("violation", 0)
    elif engine == "hcs":
        # Count errors (type 1) as violations
        return result.get("summary", {}).get("errorCount", 0)
    elif engine == "sia":
        # Return rule count for cleaner summary (elements are shown separately)
        # Handle both camelCase (JS) and snake_case (Python) key formats
        summary = result.get("summary", {})
        return summary.get("failedRuleCount") or summary.get("failed_rule_count") or 0
    return 0


def _count_alfa_elements(result: dict) -> int:
    """Count total element-level violations for Alfa."""
    # Handle both camelCase (JS) and snake_case (Python) key formats
    summary = result.get("summary", {})
    return summary.get("failedCount") or summary.get("failed_count") or 0


def _count_recommendations(result: dict, engine: str) -> int:
    """Count recommendations/incomplete checks from engine result.

    Different engines use different terminology:
    - axe: 'incomplete' (checks that need manual review)
    - eac: 'recommendation' and 'potentialrecommendation' in summary
    - hcs: type 3 messages (notices)
    - sia: 'cantTell' (items requiring manual verification)
    """
    if engine == "axe":
        return len(result.get("incomplete", []))
    elif engine == "eac":
        summary = result.get("summary", {})
        return summary.get("recommendation", 0) + summary.get("potentialrecommendation", 0)
    elif engine == "hcs":
        # Type 3 = notice (recommendations)
        messages = result.get("messages", [])
        return sum(1 for m in messages if m.get("type") == 3)
    elif engine == "sia":
        return len(result.get("cantTell", []))
    return 0


def _calculate_engine_correlation(consolidated: dict, engine_list: list[str]) -> dict:
    """Calculate agreement statistics across engines.

    Returns:
        dict with:
        - total_scs: Total SCs evaluated
        - full_agreement: SCs where all engines agree (all pass or all fail)
        - disagreement: SCs where engines disagree
        - agreement_percentage: Percentage of full agreement
    """
    total = 0
    full_agreement = 0

    for _sc, data in consolidated.items():
        statuses = []
        for eng in engine_list:
            status = data.get(f"{eng}_status", "pass")
            # Normalize to pass/fail for comparison
            is_fail = status not in ("pass",)
            statuses.append(is_fail)

        total += 1
        failing_count = sum(statuses)

        if failing_count == 0 or failing_count == len(engine_list):
            # All agree (all pass or all fail)
            full_agreement += 1

    return {
        "total_scs": total,
        "full_agreement": full_agreement,
        "disagreement": total - full_agreement,
        "agreement_percentage": round(full_agreement / total * 100) if total > 0 else 0
    }


def _consolidate_by_wcag_multi(
    engine_results: dict[str, dict],
    engine_list: list[str]
) -> dict:
    """
    Consolidate results from multiple engines by WCAG Success Criterion.

    Args:
        engine_results: Dict mapping engine name to its raw results
        engine_list: List of engine names in execution order

    Returns:
        Dict mapping WCAG SC to consolidated results with per-engine status
    """
    consolidated = {}

    def ensure_sc_entry(sc: str):
        """Ensure SC entry exists with fields for all engines."""
        if sc not in consolidated:
            consolidated[sc] = {}
            for eng in engine_list:
                consolidated[sc][f"{eng}_status"] = "pass"
                consolidated[sc][f"{eng}_count"] = 0
                consolidated[sc][f"{eng}_impact"] = None

    # Process each engine's results
    for engine in engine_list:
        results = engine_results.get(engine, {})

        if engine == "axe":
            # Process Axe violations
            for violation in results.get("violations", []):
                tags = violation.get("tags", [])
                wcag_scs = _extract_wcag_from_axe_tags(tags)
                count = violation.get("nodeCount", len(violation.get("nodes", [])))
                impact = violation.get("impact", "unknown")

                for sc in wcag_scs:
                    ensure_sc_entry(sc)
                    if consolidated[sc][f"{engine}_status"] == "pass" or \
                       (consolidated[sc][f"{engine}_status"] == "incomplete" and impact in ["critical", "serious"]):
                        consolidated[sc][f"{engine}_status"] = "violation"
                    consolidated[sc][f"{engine}_count"] += count
                    # Track worst impact
                    impact_order = ["minor", "moderate", "serious", "critical"]
                    current_impact = consolidated[sc][f"{engine}_impact"]
                    if current_impact is None or \
                       (impact in impact_order and impact_order.index(impact) > impact_order.index(current_impact or "minor")):
                        consolidated[sc][f"{engine}_impact"] = impact

            # Process Axe incomplete
            for incomplete in results.get("incomplete", []):
                tags = incomplete.get("tags", [])
                wcag_scs = _extract_wcag_from_axe_tags(tags)
                count = incomplete.get("nodeCount", len(incomplete.get("nodes", [])))

                for sc in wcag_scs:
                    ensure_sc_entry(sc)
                    if consolidated[sc][f"{engine}_status"] == "pass":
                        consolidated[sc][f"{engine}_status"] = "incomplete"
                        consolidated[sc][f"{engine}_count"] += count

        elif engine == "eac":
            # Process IBM issues
            for issue in results.get("issues", []):
                level = issue.get("level", "violation")
                rule_id = issue.get("ruleId", "")

                # Get WCAG SCs from issue or static mapping
                wcag_list = issue.get("wcag", [])
                wcag_scs = _extract_wcag_from_ibm(wcag_list)

                # Fall back to static mapping if no WCAG in issue
                if not wcag_scs and rule_id in IBM_RULE_TO_WCAG:
                    wcag_scs = IBM_RULE_TO_WCAG[rule_id]

                if not wcag_scs:
                    continue

                for sc in wcag_scs:
                    ensure_sc_entry(sc)

                    if level == "pass":
                        continue

                    # Set to worst status
                    level_priority = {
                        "pass": 0, "manual": 1, "recommendation": 2,
                        "potentialrecommendation": 2, "potentialviolation": 3, "violation": 4
                    }
                    current_priority = level_priority.get(consolidated[sc][f"{engine}_status"], 0)
                    new_priority = level_priority.get(level, 0)

                    if new_priority > current_priority:
                        consolidated[sc][f"{engine}_status"] = level
                    consolidated[sc][f"{engine}_count"] += 1

        elif engine == "hcs":
            # Process HTMLCS messages
            for msg in results.get("messages", []):
                msg_type = msg.get("type", 3)  # 1=error, 2=warning, 3=notice
                code = msg.get("code", "")

                # Extract WCAG SC from code (e.g., WCAG2AA.Principle1.Guideline1_3.1_3_1.H44)
                wcag_scs = _extract_wcag_from_htmlcs_code(code)

                if not wcag_scs:
                    continue

                for sc in wcag_scs:
                    ensure_sc_entry(sc)

                    # Map message type to status
                    if msg_type == 1:  # Error
                        if consolidated[sc][f"{engine}_status"] in ["pass", "incomplete"]:
                            consolidated[sc][f"{engine}_status"] = "violation"
                        consolidated[sc][f"{engine}_count"] += 1
                    elif msg_type == 2:  # Warning
                        if consolidated[sc][f"{engine}_status"] == "pass":
                            consolidated[sc][f"{engine}_status"] = "review"
                        consolidated[sc][f"{engine}_count"] += 1
                    # Notices (type 3) are informational, don't count as issues

        elif engine == "sia":
            # Process Alfa outcomes
            for outcome in results.get("outcomes", []):
                outcome_type = outcome.get("outcome", "")
                if outcome_type != "failed":
                    continue  # Only count failed outcomes as violations

                # Extract WCAG SCs from requirements
                requirements = outcome.get("requirements", [])
                wcag_scs = _extract_wcag_from_sia(requirements)

                if not wcag_scs:
                    continue

                for sc in wcag_scs:
                    ensure_sc_entry(sc)
                    if consolidated[sc][f"{engine}_status"] == "pass":
                        consolidated[sc][f"{engine}_status"] = "violation"
                    consolidated[sc][f"{engine}_count"] += 1
                    # Alfa doesn't provide impact levels, default to "serious"
                    if consolidated[sc][f"{engine}_impact"] is None:
                        consolidated[sc][f"{engine}_impact"] = "serious"

    return consolidated


def _print_pivoted_results_table(
    consolidated: dict,
    engine_list: list[str],
    sorted_scs: list[str],
    issues_count: int
) -> None:
    """
    Print results in pivoted table format (one row per engine per WCAG SC).

    Args:
        consolidated: Dict mapping WCAG SC to engine results
        engine_list: List of engine IDs in order
        sorted_scs: Sorted list of WCAG SC numbers
        issues_count: Number of criteria with issues
    """
    is_single_engine = len(engine_list) == 1

    # Build table headers - hide Engine column for single engine
    if is_single_engine:
        headers = ["WCAG SC", "Level", "Status", "Description"]
        alignments = ["left", "left", "left", "left"]
    else:
        headers = ["WCAG SC", "Level", "Engine", "Status", "Description"]
        alignments = ["left", "left", "left", "left", "left"]

    rows = []
    row_colors = []
    separator_after = []  # Track which rows need separators after them

    for sc_idx, sc in enumerate(sorted_scs):
        data = consolidated[sc]
        desc = WCAG_SC_DESCRIPTIONS.get(sc, "")

        # Get conformance level for this SC
        sc_info = WCAG_SC_LEVELS.get(sc, {})
        sc_level = sc_info.get("level", "")

        for eng_idx, engine in enumerate(engine_list):
            status = data.get(f"{engine}_status", "pass")
            count = data.get(f"{engine}_count", 0)

            status_text, status_color = _get_combined_status_info(status, count, engine)
            engine_color = AVAILABLE_ENGINES[engine]["color"]

            # Only show SC, level, and description on first engine row
            sc_display = sc if eng_idx == 0 else ""
            level_display = sc_level if eng_idx == 0 else ""
            desc_display = desc if eng_idx == 0 else ""

            if is_single_engine:
                rows.append([sc_display, level_display, status_text, desc_display])
                row_colors.append([None, None, status_color, None])
            else:
                engine_abbr = AVAILABLE_ENGINES[engine]["abbr"]
                rows.append([sc_display, level_display, engine_abbr, status_text, desc_display])
                row_colors.append([None, None, engine_color, status_color, None])

        # Mark separator after each SC group (except last) - only for multi-engine
        if not is_single_engine and sc_idx < len(sorted_scs) - 1:
            separator_after.append(len(rows) - 1)

    # Create and print table
    title = f"Accessibility Audit Results ({issues_count} criteria with issues)"
    icon = get_icon("Accessibility")
    table = Table(headers, alignments=alignments, title=title, icon=icon)
    table.set_data(rows)
    table.print_header()

    for idx, (row_data, colors) in enumerate(zip(rows, row_colors, strict=False)):
        table.print_row(row_data, colors)
        # Add separator between SC groups for readability (multi-engine only)
        if idx in separator_after:
            table.print_separator()

    table.print_footer()


def _get_combined_status_info(status: str, count: int, tool: str) -> tuple[str, str]:
    """Get status text and color for combined table cell.

    Returns:
        Tuple of (display_text, color)
    """
    if status == "pass" or count == 0:
        return ("pass", "green")

    if tool == "axe":
        colors = {"violation": "red", "incomplete": "yellow"}
        color = colors.get(status, "white")
        return (f"fail ({count})", color)
    else:  # ibm
        colors = {
            "violation": "red",
            "potentialviolation": "yellow",
            "recommendation": "blue",
            "potentialrecommendation": "cyan",
            "manual": "bright_black"
        }
        color = colors.get(status, "white")
        label = "fail" if status == "violation" else "review" if "potential" in status else status[:6]
        return (f"{label} ({count})", color)


def _collect_recommendations(engine_results: dict, engine_list: list[str]) -> list[dict]:
    """Collect recommendation-level issues from all engines.

    Args:
        engine_results: Dict mapping engine name to its raw results
        engine_list: List of engine names in execution order

    Returns:
        List of recommendation dicts with keys: engine, sc, message, rule_id
    """
    recommendations = []

    for engine in engine_list:
        result = engine_results.get(engine, {})
        if result.get("error"):
            continue

        if engine == "eac":
            for issue in result.get("issues", []):
                level = issue.get("level", "")
                if level in ("recommendation", "potentialrecommendation"):
                    rule_id = issue.get("ruleId", "")
                    # Use IBM rule mapping to get WCAG SCs
                    wcag_scs = IBM_RULE_TO_WCAG.get(rule_id, [])
                    sc = wcag_scs[0] if wcag_scs else ""
                    recommendations.append({
                        "engine": engine,
                        "sc": sc,
                        "message": issue.get("message", ""),
                        "rule_id": rule_id,
                        "level": level,
                    })

        elif engine == "hcs":
            for msg in result.get("messages", []):
                if msg.get("type") == 3:  # type 3 = notice
                    code = msg.get("code", "")
                    wcag_scs = _extract_wcag_from_htmlcs_code(code)
                    sc = wcag_scs[0] if wcag_scs else ""
                    recommendations.append({
                        "engine": engine,
                        "sc": sc,
                        "message": msg.get("message", ""),
                        "rule_id": code,
                        "level": "notice",
                    })

        elif engine == "sia":
            for item in result.get("cantTell", []):
                requirements = item.get("requirements", [])
                wcag_scs = _extract_wcag_from_sia(requirements)
                sc = wcag_scs[0] if wcag_scs else ""
                recommendations.append({
                    "engine": engine,
                    "sc": sc,
                    "message": item.get("message", ""),
                    "rule_id": item.get("rule", ""),
                    "level": "cantTell",
                })

        elif engine == "axe":
            for item in result.get("incomplete", []):
                tags = item.get("tags", [])
                wcag_scs = _extract_wcag_from_axe_tags(tags)
                sc = wcag_scs[0] if wcag_scs else ""
                recommendations.append({
                    "engine": engine,
                    "sc": sc,
                    "message": item.get("description", ""),
                    "rule_id": item.get("id", ""),
                    "level": "incomplete",
                })

    return recommendations


def _print_recommendations_section(engine_results: dict, engine_list: list[str]) -> None:
    """Print recommendations summary table.

    Shows a dedicated table with recommendations from all engines,
    grouped by WCAG SC and engine.

    Args:
        engine_results: Dict mapping engine name to its raw results
        engine_list: List of engine names in execution order
    """
    recommendations = _collect_recommendations(engine_results, engine_list)

    if not recommendations:
        return

    # Group by SC and engine
    grouped: dict[tuple[str, str], dict] = {}
    for rec in recommendations:
        key = (rec["sc"], rec["engine"])
        if key not in grouped:
            grouped[key] = {"count": 0, "message": rec["message"], "rule_id": rec["rule_id"]}
        grouped[key]["count"] += 1

    if not grouped:
        return

    # Only show Engine column when multiple engines are used
    show_engine_column = len(engine_list) > 1

    # Build table
    if show_engine_column:
        headers = ["WCAG SC", "Level", "Engine", "Count", "Description"]
        alignments = ["left", "left", "left", "right", "left"]
    else:
        headers = ["WCAG SC", "Level", "Count", "Description"]
        alignments = ["left", "left", "right", "left"]

    rows = []
    row_colors = []

    for (sc, engine), data in sorted(grouped.items(), key=lambda x: (x[0][0] or "zzz", x[0][1])):
        engine_abbr = AVAILABLE_ENGINES[engine]["abbr"]
        engine_color = AVAILABLE_ENGINES[engine]["color"]

        # Get SC level
        sc_info = WCAG_SC_LEVELS.get(sc, {})
        sc_level = sc_info.get("level", "")

        # Truncate message
        msg = data["message"][:50] + "…" if len(data["message"]) > 50 else data["message"]

        if show_engine_column:
            rows.append([sc or "—", sc_level, engine_abbr, str(data["count"]), msg])
            row_colors.append([None, None, engine_color, "cyan", None])
        else:
            rows.append([sc or "—", sc_level, str(data["count"]), msg])
            row_colors.append([None, None, "cyan", None])

    total = sum(d["count"] for d in grouped.values())
    title = f"Recommendations ({total} items)"
    icon = get_icon("tip")  # Lightbulb icon

    # Import Table locally to match existing pattern
    from inspekt.app.cli.table import Table

    click.echo()
    table = Table(headers, alignments=alignments, title=title, icon=icon)
    table.set_data(rows)
    table.print_header()
    for row_data, colors in zip(rows, row_colors, strict=False):
        table.print_row(row_data, colors)
    table.print_footer()


def _extract_engine_rule_details(engine_results: dict, engine_list: list[str]) -> dict:
    """Extract structured rule-level details from each engine's raw results.

    This is the data-only counterpart of _print_engine_rule_tables().
    Returns structured dicts instead of printing to the terminal.

    Args:
        engine_results: Dict mapping engine name to its raw results
        engine_list: List of engine names in execution order

    Returns:
        Dict mapping engine name to structured violation/pass/incomplete data
    """
    details = {}

    for engine in engine_list:
        result = engine_results.get(engine, {})
        if result.get("error"):
            details[engine] = {"error": result["error"]}
            continue

        engine_detail: dict = {"violations": [], "passes": [], "incomplete": [], "impact_summary": {}}

        if engine == "axe":
            violations = result.get("violations", [])
            impact_order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
            violations = sorted(violations, key=lambda v: impact_order.get(v.get("impact", "minor"), 4))

            impact_counts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
            for v in violations:
                rule_id = v.get("id", "unknown")
                impact = v.get("impact", "minor")
                nodes = v.get("nodes", [])
                count = v.get("nodeCount", len(nodes))
                impact_counts[impact] = impact_counts.get(impact, 0) + count

                node_details = []
                for node in nodes[:10]:  # Cap at 10 nodes per rule
                    node_details.append({
                        "selector": ", ".join(node.get("target", [])) if isinstance(node.get("target"), list) else str(node.get("target", "")),
                        "html": node.get("html", ""),
                        "failure_summary": node.get("failureSummary", ""),
                    })

                engine_detail["violations"].append({
                    "rule_id": rule_id,
                    "impact": impact,
                    "count": count,
                    "description": v.get("description", ""),
                    "help_url": v.get("helpUrl", ""),
                    "nodes": node_details,
                })

            engine_detail["impact_summary"] = impact_counts

            # Passes
            for p in result.get("passes", []):
                engine_detail["passes"].append({
                    "rule_id": p.get("id", "unknown"),
                    "count": p.get("nodeCount", len(p.get("nodes", []))),
                    "description": p.get("description", ""),
                })

            # Incomplete
            for inc in result.get("incomplete", []):
                engine_detail["incomplete"].append({
                    "rule_id": inc.get("id", "unknown"),
                    "count": inc.get("nodeCount", len(inc.get("nodes", []))),
                    "description": inc.get("description", ""),
                })

        elif engine == "eac":
            issues = result.get("issues", [])
            violations = [i for i in issues if i.get("level") == "violation"]

            # Group by rule
            rule_groups: dict[str, dict] = {}
            for issue in violations:
                rule_id = issue.get("ruleId", "unknown")
                if rule_id not in rule_groups:
                    rule_groups[rule_id] = {"count": 0, "message": issue.get("message", ""), "nodes": []}
                rule_groups[rule_id]["count"] += 1
                if len(rule_groups[rule_id]["nodes"]) < 10:
                    # path can be a dict {"dom": "…"} or a plain string
                    path = issue.get("path", "")
                    if isinstance(path, dict):
                        dom_path = path.get("dom", "")
                    else:
                        dom_path = str(path) if path else ""
                    selector = ", ".join(dom_path.split(" > ")[-3:]) if dom_path else ""
                    rule_groups[rule_id]["nodes"].append({
                        "selector": selector,
                        "html": issue.get("snippet", ""),
                        "failure_summary": issue.get("message", ""),
                    })

            for rule_id, data in sorted(rule_groups.items()):
                engine_detail["violations"].append({
                    "rule_id": rule_id,
                    "impact": "violation",
                    "count": data["count"],
                    "description": data["message"],
                    "help_url": "",
                    "nodes": data["nodes"],
                })

            # Passes and recommendations as passes
            passes = [i for i in issues if i.get("level") == "pass"]
            pass_groups: dict[str, int] = {}
            for p in passes:
                rid = p.get("ruleId", "unknown")
                pass_groups[rid] = pass_groups.get(rid, 0) + 1
            for rid, cnt in sorted(pass_groups.items()):
                engine_detail["passes"].append({"rule_id": rid, "count": cnt, "description": ""})

        elif engine == "hcs":
            messages = result.get("messages", [])
            errors = [m for m in messages if m.get("type") == 1]

            # Group by code
            code_groups: dict[str, dict] = {}
            for msg in errors:
                code = msg.get("code", "unknown")
                if code not in code_groups:
                    code_groups[code] = {"count": 0, "message": msg.get("message", ""), "nodes": []}
                code_groups[code]["count"] += 1
                if len(code_groups[code]["nodes"]) < 10:
                    code_groups[code]["nodes"].append({
                        "selector": msg.get("selector", ""),
                        "html": msg.get("context", ""),
                        "failure_summary": msg.get("message", ""),
                    })

            for code, data in sorted(code_groups.items()):
                engine_detail["violations"].append({
                    "rule_id": code,
                    "impact": "error",
                    "count": data["count"],
                    "description": data["message"],
                    "help_url": "",
                    "nodes": data["nodes"],
                })

            # Warnings as incomplete
            warnings = [m for m in messages if m.get("type") == 2]
            warn_groups: dict[str, int] = {}
            for w in warnings:
                wcode = w.get("code", "unknown")
                warn_groups[wcode] = warn_groups.get(wcode, 0) + 1
            for wcode, cnt in sorted(warn_groups.items()):
                engine_detail["incomplete"].append({"rule_id": wcode, "count": cnt, "description": ""})

        elif engine == "sia":
            outcomes = result.get("outcomes", [])
            failed = [o for o in outcomes if o.get("outcome") == "failed"]

            # Group by rule
            rule_groups_sia: dict[str, dict] = {}
            for outcome in failed:
                rule_url = outcome.get("rule", "unknown")
                rule_id = rule_url.split("/")[-1] if "/" in rule_url else rule_url
                title_text = outcome.get("title", rule_id)
                if rule_id not in rule_groups_sia:
                    rule_groups_sia[rule_id] = {"count": 0, "title": title_text, "nodes": []}
                rule_groups_sia[rule_id]["count"] += 1
                if len(rule_groups_sia[rule_id]["nodes"]) < 10:
                    target = outcome.get("target", "")
                    rule_groups_sia[rule_id]["nodes"].append({
                        "selector": target if isinstance(target, str) else str(target),
                        "html": "",
                        "failure_summary": outcome.get("message", ""),
                    })

            for rule_id, data in sorted(rule_groups_sia.items()):
                engine_detail["violations"].append({
                    "rule_id": rule_id,
                    "impact": "serious",
                    "count": data["count"],
                    "description": data["title"],
                    "help_url": f"https://alfa.siteimprove.com/rules/{rule_id}" if rule_id.startswith("sia-") else "",
                    "nodes": data["nodes"],
                })

            # Passed outcomes
            passed = [o for o in outcomes if o.get("outcome") == "passed"]
            pass_groups_sia: dict[str, int] = {}
            for o in passed:
                rule_url = o.get("rule", "unknown")
                rid = rule_url.split("/")[-1] if "/" in rule_url else rule_url
                pass_groups_sia[rid] = pass_groups_sia.get(rid, 0) + 1
            for rid, cnt in sorted(pass_groups_sia.items()):
                engine_detail["passes"].append({"rule_id": rid, "count": cnt, "description": o.get("title", "")})

            # cantTell as incomplete
            cant_tell = result.get("cantTell", [])
            ct_groups: dict[str, int] = {}
            for ct in cant_tell:
                rule_url = ct.get("rule", "unknown")
                rid = rule_url.split("/")[-1] if "/" in rule_url else rule_url
                ct_groups[rid] = ct_groups.get(rid, 0) + 1
            for rid, cnt in sorted(ct_groups.items()):
                engine_detail["incomplete"].append({"rule_id": rid, "count": cnt, "description": ""})

        details[engine] = engine_detail

    return details


def _print_engine_rule_tables(engine_results: dict, engine_list: list[str]) -> None:
    """
    Print rule-level violation tables for each engine (verbose mode).

    Args:
        engine_results: Dict mapping engine name to its raw results
        engine_list: List of engine names in execution order
    """
    for engine in engine_list:
        result = engine_results.get(engine, {})
        if result.get("error"):
            continue

        engine_info = AVAILABLE_ENGINES[engine]
        engine_name = engine_info["name"]

        # Extract violations based on engine type
        if engine == "axe":
            violations = result.get("violations", [])
            if not violations:
                click.echo(f"\n{click.style(engine_name, bold=True)}: No violations")
                continue

            # Sort by impact
            impact_order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
            violations = sorted(violations, key=lambda v: impact_order.get(v.get("impact", "minor"), 4))

            # Build rows
            headers = ["Rule", "Impact", "Count", "Description"]
            alignments = ["left", "left", "right", "left"]
            rows = []
            row_colors = []
            total_count = 0
            impact_counts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}

            for v in violations:
                rule_id = v.get("id", "unknown")
                impact = v.get("impact", "minor")
                count = v.get("nodeCount", len(v.get("nodes", [])))
                desc = v.get("description", "")

                total_count += count
                impact_counts[impact] = impact_counts.get(impact, 0) + count
                rows.append([rule_id, impact, str(count), desc])
                row_colors.append([None, _get_impact_color(impact), None, None])

            title = f"{engine_name} Violations ({len(violations)})"
            table = Table(headers, alignments=alignments, title=title)
            table.set_data(rows)
            table.print_header()
            for row_data, colors in zip(rows, row_colors, strict=False):
                table.print_row(row_data, colors)
            summary_row = [f"{len(violations)} rules", "", str(total_count), ""]
            table.print_summary(summary_row)
            table.print_footer()

            # Impact summary
            _print_impact_counts(impact_counts, result.get("passes", []), result.get("incomplete", []))

        elif engine == "eac":
            issues = result.get("issues", [])
            violations = [i for i in issues if i.get("level") == "violation"]
            if not violations:
                click.echo(f"\n{click.style(engine_name, bold=True)}: No violations")
                continue

            # Group by rule
            rule_groups = {}
            for issue in violations:
                rule_id = issue.get("ruleId", "unknown")
                if rule_id not in rule_groups:
                    rule_groups[rule_id] = {"count": 0, "message": issue.get("message", "")}
                rule_groups[rule_id]["count"] += 1

            headers = ["Rule", "Impact", "Count", "Description"]
            alignments = ["left", "left", "right", "left"]
            rows = []
            row_colors = []
            total_count = 0

            for rule_id, data in sorted(rule_groups.items()):
                total_count += data["count"]
                # Truncate message to 60 chars
                msg = data["message"][:60] + "…" if len(data["message"]) > 60 else data["message"]
                rows.append([rule_id, "critical", str(data["count"]), msg])
                row_colors.append([None, _get_impact_color("critical"), None, None])

            title = f"{engine_name} Violations ({len(rule_groups)})"
            table = Table(headers, alignments=alignments, title=title)
            table.set_data(rows)
            table.print_header()
            for row_data, colors in zip(rows, row_colors, strict=False):
                table.print_row(row_data, colors)
            summary_row = [f"{len(rule_groups)} rules", "", str(total_count), ""]
            table.print_summary(summary_row)
            table.print_footer()

        elif engine == "hcs":
            messages = result.get("messages", [])
            errors = [m for m in messages if m.get("type") == 1]  # type 1 = error
            if not errors:
                click.echo(f"\n{click.style(engine_name, bold=True)}: No errors")
                continue

            # Group by code
            code_groups = {}
            for msg in errors:
                code = msg.get("code", "unknown")
                if code not in code_groups:
                    code_groups[code] = {"count": 0, "message": msg.get("message", "")}
                code_groups[code]["count"] += 1

            headers = ["Rule", "Impact", "Count", "Description"]
            alignments = ["left", "left", "right", "left"]
            rows = []
            row_colors = []
            total_count = 0

            for code, data in sorted(code_groups.items()):
                total_count += data["count"]
                # Truncate message to 60 chars
                msg = data["message"][:60] + "…" if len(data["message"]) > 60 else data["message"]
                rows.append([code[:30], "critical", str(data["count"]), msg])
                row_colors.append([None, _get_impact_color("critical"), None, None])

            title = f"{engine_name} Violations ({len(code_groups)})"
            table = Table(headers, alignments=alignments, title=title)
            table.set_data(rows)
            table.print_header()
            for row_data, colors in zip(rows, row_colors, strict=False):
                table.print_row(row_data, colors)
            summary_row = [f"{len(code_groups)} rules", "", str(total_count), ""]
            table.print_summary(summary_row)
            table.print_footer()

        elif engine == "sia":
            outcomes = result.get("outcomes", [])
            failed = [o for o in outcomes if o.get("outcome") == "failed"]
            if not failed:
                click.echo(f"\n{click.style(engine_name, bold=True)}: No violations")
                continue

            # Group by rule (extract rule ID from URL)
            rule_groups = {}
            for outcome in failed:
                rule_url = outcome.get("rule", "unknown")
                # Extract rule ID from URL: "https://alfa.siteimprove.com/rules/sia-r1" -> "sia-r1"
                rule_id = rule_url.split("/")[-1] if "/" in rule_url else rule_url
                title_text = outcome.get("title", rule_id)
                if rule_id not in rule_groups:
                    rule_groups[rule_id] = {"count": 0, "title": title_text}
                rule_groups[rule_id]["count"] += 1

            headers = ["Rule", "Impact", "Count", "Description"]
            alignments = ["left", "left", "right", "left"]
            rows = []
            row_colors = []
            total_count = 0

            for rule_id, data in sorted(rule_groups.items()):
                total_count += data["count"]
                rows.append([rule_id, "serious", str(data["count"]), data["title"]])
                row_colors.append([None, _get_impact_color("serious"), None, None])

            title = f"{engine_name} Violations ({len(rule_groups)})"
            table = Table(headers, alignments=alignments, title=title)
            table.set_data(rows)
            table.print_header()
            for row_data, colors in zip(rows, row_colors, strict=False):
                table.print_row(row_data, colors)
            summary_row = [f"{len(rule_groups)} rules", "", str(total_count), ""]
            table.print_summary(summary_row)
            table.print_footer()


def _print_impact_counts(impact_counts: dict, passes: list, incomplete: list) -> None:
    """Print impact summary counts for axe-style engines."""
    def format_count(count):
        if count == 0:
            return click.style("\u2014", fg="bright_black")
        return str(count)

    click.echo(f"  Critical:   {format_count(impact_counts.get('critical', 0))}")
    click.echo(f"  Serious:    {format_count(impact_counts.get('serious', 0))}")
    click.echo(f"  Moderate:   {format_count(impact_counts.get('moderate', 0))}")
    click.echo(f"  Minor:      {format_count(impact_counts.get('minor', 0))}")
    click.echo(f"  Passes:     {len(passes)}")
    if len(incomplete) > 0:
        click.echo(f"  Incomplete: {len(incomplete)} (use --include-incomplete to see details)")


def _show_engine_list():
    """Display a table of available accessibility engines."""
    from inspekt.app.cli.icons import get_indicator
    from inspekt.app.cli.table import Table, _style_with_inline_code, format_icon_message
    from inspekt.data import load_engine_metadata
    from inspekt.services.engines import get_engine

    metadata = load_engine_metadata()

    headers = ["ID", "Name", "Provider", "Latest Version", "Installed", "Status"]
    alignments = ["left", "left", "left", "right", "right", "left"]
    rows = []
    row_colors = []
    has_updates = False

    for engine_id in DEFAULT_ENGINE_ORDER:
        if engine_id not in metadata:
            continue

        info = metadata[engine_id]

        # Get version info and check for updates
        try:
            engine = get_engine(engine_id)
            is_installed = engine.is_installed()
            update_available, current_version, latest_version, release_date = engine.is_update_available()

            # Format latest version with date
            if latest_version and release_date:
                # release_date is ISO format, extract just the date part
                date_part = release_date[:10] if release_date else ""
                latest_display = f"{latest_version} ({date_part})"
            elif latest_version:
                latest_display = latest_version
            else:
                latest_display = "-"

            # Installed version
            installed_display = current_version if current_version else "-"

            # Status
            if not is_installed:
                status = "not installed"
                status_color = "yellow"
            elif update_available:
                status = "update available"
                status_color = "yellow"
                has_updates = True
            else:
                status = "installed"
                status_color = "green"

        except Exception:
            latest_display = "-"
            installed_display = "-"
            status = "error"
            status_color = "red"

        rows.append([
            engine_id,
            info["official_name"],
            info["provider"],
            latest_display,
            installed_display,
            status
        ])
        row_colors.append([
            "cyan",  # ID
            None,    # Name
            None,    # Provider
            None,    # Latest Version
            None,    # Installed
            status_color
        ])

    table = Table(headers, alignments=alignments, title="Available Accessibility Engines", icon="\uf085")
    table.set_data(rows)
    table.print_header()
    for row_data, colors in zip(rows, row_colors, strict=False):
        table.print_row(row_data, colors)
    table.print_footer()

    # Show update tip if updates are available
    if has_updates:
        tip_icon = get_indicator("tip") or ""
        formatted = format_icon_message("To update engines, run `inspekt restart --update`", icon=f"{tip_icon} ")
        styled = _style_with_inline_code(formatted, base_fg="yellow", bold=False)
        click.echo(styled)


def _show_engine_info(engine_id: str):
    """Display detailed metadata for a specific engine."""
    from inspekt.data import load_engine_metadata
    from inspekt.services.engines import get_engine

    metadata = load_engine_metadata()

    if engine_id not in metadata:
        available = ", ".join(sorted(metadata.keys()))
        raise click.UsageError(f"Unknown engine '{engine_id}'. Available: {available}")

    info = metadata[engine_id]

    # Get runtime info
    try:
        engine = get_engine(engine_id)
        current_version = engine.get_current_version() or "not installed"
        is_installed = engine.is_installed()

        # Get release date (cached, with fallback)
        versions = {engine_id: current_version}
        release_dates = _get_engine_release_dates(versions)
        release_date = release_dates.get(engine_id, info.get("latest_update", "unknown"))

        # Check for updates
        update_available, _, latest_version, _ = engine.is_update_available()
        if not latest_version:
            latest_version = "unknown"

        if is_installed:
            if update_available:
                status = f"Update available ({latest_version})"
                status_color = "yellow"
            else:
                status = "Up to date"
                status_color = "green"
        else:
            status = "Not installed"
            status_color = "red"
    except Exception as e:
        current_version = "error"
        latest_version = "unknown"
        release_date = info.get("latest_update", "unknown")
        status = f"Error: {e}"
        status_color = "red"

    # Display info
    click.echo()
    click.echo(click.style(f"  {info['official_name']}", bold=True))
    click.echo(click.style(f"  {'-' * len(info['official_name'])}", fg="bright_black"))
    click.echo()
    click.echo(f"  Provider:          {info['provider']}")
    click.echo(f"  License:           {info['license']}")
    click.echo(f"  WCAG Support:      {', '.join(info['wcag_support'])}")
    click.echo(f"  Homepage:          {info['official_url']}")
    click.echo(f"  Last Updated:      {release_date}")
    click.echo()
    click.echo(f"  Installed Version: {current_version}")
    click.echo(f"  Latest Version:    {latest_version}")
    click.echo("  Status:            " + click.style(status, fg=status_color))
    click.echo()
    click.echo(f"  {info['description']}")
    click.echo()

    # Show rule table
    _print_engine_rules_table(engine_id)


def _print_engine_rules_table(engine_id: str) -> None:
    """Print comprehensive rule table for an engine."""
    from inspekt.data import load_engine_rules

    rules_data = load_engine_rules(engine_id)
    rules = rules_data.get("rules", [])

    if not rules:
        click.echo("  No rule data available for this engine.", err=True)
        click.echo()
        return

    # Calculate column widths
    id_width = max(len(r["id"]) for r in rules)
    id_width = max(id_width, 4)  # Minimum "Rule" header
    desc_width = 50  # Fixed width, truncate if needed
    act_width = 3  # "ACT" header

    # Border color for consistent styling
    border_color = "bright_black"
    border = click.style("│", fg=border_color)

    # Prepare separator lines
    top_line = f"  ╭{'─' * (id_width + 2)}┬{'─' * (desc_width + 2)}┬{'─' * (act_width + 2)}╮"
    header_sep = f"  ├{'─' * (id_width + 2)}┼{'─' * (desc_width + 2)}┼{'─' * (act_width + 2)}┤"
    bottom_line = f"  ╰{'─' * (id_width + 2)}┴{'─' * (desc_width + 2)}┴{'─' * (act_width + 2)}╯"

    # Header
    total = len(rules)
    act_count = sum(1 for r in rules if r.get("act_rule"))

    click.echo(click.style(f"  Supported Rules ({total})", bold=True))
    click.echo()
    click.echo(click.style(top_line, fg=border_color))

    # Column headers - style borders explicitly
    header = (
        f"  {border} {click.style('Rule'.ljust(id_width), bold=True)} "
        f"{border} {click.style('Description'.ljust(desc_width), bold=True)} "
        f"{border} {click.style('ACT', bold=True)} {border}"
    )
    click.echo(header)
    click.echo(click.style(header_sep, fg=border_color))

    # Rows - style all borders to prevent color bleeding
    for rule in rules:
        rule_id = rule["id"][:id_width].ljust(id_width)
        description = rule.get("description", "")
        if len(description) > desc_width:
            description = description[: desc_width - 1] + "…"
        description = description.ljust(desc_width)

        act_indicator = click.style("✓", fg="green") if rule.get("act_rule") else click.style("—", fg=border_color)

        row = f"  {border} {rule_id} {border} {description} {border}  {act_indicator} {border}"
        click.echo(row)

    click.echo(click.style(bottom_line, fg=border_color))

    # Summary
    click.echo()
    if act_count > 0:
        pct = int(act_count / total * 100)
        click.echo(f"  {act_count}/{total} rules ({pct}%) aligned with W3C ACT Rules")
    else:
        click.echo(click.style("  This engine does not implement W3C ACT Rules", fg="yellow"))
    click.echo()


@click.command()
@click.option(
    "--engines",
    "-e",
    "engines",
    type=str,
    default=None,
    help="Engines to run, comma-separated (default: axe,eac,hcs). Available: axe, eac, hcs, sia"
)
@click.option(
    "--list-engines",
    is_flag=True,
    help="List available accessibility engines and exit"
)
@click.option(
    "--level",
    type=click.Choice(["2a", "2aa", "2aaa", "21a", "21aa", "22aa"], case_sensitive=False),
    default="21aa",
    help="WCAG conformance level to test (default: 21aa)"
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "html"], case_sensitive=False),
    default=None,
    help="Output format: json (machine-readable) or html (interactive report)"
)
@click.option(
    "--json",
    "-j",
    "json_flag",
    is_flag=True,
    help="Output as JSON (shortcut for --format json)"
)
@click.option(
    "--timeout",
    type=float,
    default=60.0,
    help="Timeout in seconds for each engine (default: 60)"
)
@click.option(
    "--show-passes",
    is_flag=True,
    help="Include WCAG criteria where all engines pass"
)
@click.option(
    "--include-recommendations",
    is_flag=True,
    help="Include recommendations and best practices from all engines"
)
@click.option(
    "--show-badges",
    is_flag=True,
    help="Show unified badges on elements with issues (run in browser)"
)
@click.option(
    "--interactive",
    is_flag=True,
    help="Make badges clickable with detailed popover information (requires --show-badges)"
)
@click.option(
    "--dev-css",
    is_flag=True,
    hidden=True,
    help="Load CSS from local server for development"
)
@click.option(
    "--all-disagreements",
    is_flag=True,
    help="Show all disagreements instead of limiting to 10"
)
@click.option(
    "--info",
    is_flag=True,
    help="Show engine metadata, version info, and complete rule listing with ACT alignment"
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed rule-level tables for each engine"
)
@click.option(
    "--scoped",
    type=str,
    help="Scope tests to specific elements. Use 'inspected' for the currently inspected element, or provide CSS selectors (comma-separated)"
)
@click.option(
    "--exclude",
    type=str,
    multiple=True,
    help="Exclude elements from testing. Can be comma-separated selectors or multiple --exclude flags"
)
@click.option(
    "--rule",
    type=str,
    help="Test a single axe-core rule by ID (only works with axe engine)"
)
@click.option(
    "--disable-rule",
    type=str,
    multiple=True,
    metavar="RULE_ID",
    help="Disable specific rules by ID (axe engine only). Supports comma-separated values."
)
@click.option(
    "--enable-rule",
    type=str,
    multiple=True,
    metavar="RULE_ID",
    help="Run ONLY these rules (axe engine only). Supports comma-separated values."
)
@click.option(
    "--persistent",
    is_flag=True,
    help="Monitor and re-run audit on each page navigation (press Ctrl+C to stop)"
)
@click.option(
    "--no-compliance-warning",
    is_flag=True,
    help="Suppress the warning about automated checker limitations"
)
@click.option(
    "--summary-only",
    is_flag=True,
    help="Show only summary, agreement, and disagreements (skip detailed WCAG table)"
)
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(),
    help="Save output to file (requires --format)"
)
@click.option(
    "--no-open",
    is_flag=True,
    help="Don't auto-open the HTML report in the browser"
)
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Run audit in headless Chrome (no browser extension required)"
)
@click.option(
    "--mirror-session",
    is_flag=True,
    default=False,
    help="Mirror cookies/storage from live browser for authenticated pages (implies --headless)"
)
@click.option(
    "--url",
    "headless_url",
    default=None,
    help="URL to audit in headless mode (required with --headless unless --mirror-session)"
)
def a11y(engines, list_engines, level, output_format, json_flag, timeout, show_passes, include_recommendations, show_badges, interactive, dev_css, all_disagreements, info, verbose, scoped, exclude, rule, disable_rule, enable_rule, persistent, no_compliance_warning, summary_only, output_file, no_open, headless, mirror_session, headless_url):
    """
    Run combined accessibility audit with selected engines.

    Runs the specified accessibility checkers in order and consolidates
    results by WCAG Success Criterion, showing all engine outcomes
    for comparison.

    ENGINE SELECTION:

    By default, runs all available engines: axe, eac, hcs.
    Use --engines/-e with comma-separated names to select specific engines.

    Order matters: engines execute in the order specified, which may
    affect results when scripts have side effects (e.g., DOM mutations).

    This helps identify:

    \b
    - Issues caught by one tool but not others
    - Conflicting assessments between tools
    - Comprehensive coverage of WCAG criteria

    \b
    Examples:
        inspekt a11y                       # All engines (axe, eac, hcs)
        inspekt a11y -e axe                # Axe-core only
        inspekt a11y -e eac                # Equal Access Checker only
        inspekt a11y -e axe,eac            # axe and eac only
        inspekt a11y -e eac,axe            # eac first, then axe
        inspekt a11y --level 21aa          # WCAG 2.1 AA
        inspekt a11y --format json         # JSON output
        inspekt a11y --format html         # HTML report (opens in browser)
        inspekt a11y --show-badges         # Show badges on page
        inspekt a11y --list-engines        # List available engines
        inspekt a11y -e axe --info         # Show engine metadata

    \b
    Available Engines:
        axe      Axe-core (Deque Systems) - industry standard
        eac      Equal Access Checker (IBM) - comprehensive WCAG coverage
        hcs      HTML CodeSniffer (Squiz Labs) - WCAG 2.1 checker
    """
    from inspekt.app.cli.table import Table, _style_with_inline_code

    # Handle --list-engines flag
    if list_engines:
        _show_engine_list()
        return

    # Handle --info flag - show engine metadata and exit
    if info:
        engine_list_parsed = _validate_and_normalize_engines(engines) if engines else []
        if len(engine_list_parsed) != 1:
            raise click.UsageError("--info requires exactly one engine (e.g., 'inspekt a11y -e axe --info')")

        engine_id = engine_list_parsed[0]
        _show_engine_info(engine_id)
        return

    from inspekt.client import BridgeClient

    # Validate and normalize engine list
    engine_list = _validate_and_normalize_engines(engines)

    # --json / -j is a shortcut for --format json
    if json_flag and not output_format:
        output_format = "json"

    # Validate axe-specific options
    axe_specific_options = []
    if rule:
        axe_specific_options.append("--rule")
    if disable_rule:
        axe_specific_options.append("--disable-rule")
    if enable_rule:
        axe_specific_options.append("--enable-rule")

    if axe_specific_options and "axe" not in engine_list:
        opts_str = ", ".join(axe_specific_options)
        click.echo(click.style(f"Warning: {opts_str} only work with the axe engine", fg="yellow"), err=True)

    # Validate mutually exclusive options
    if enable_rule and disable_rule:
        raise click.UsageError("--enable-rule and --disable-rule are mutually exclusive")

    if enable_rule and rule:
        raise click.UsageError("--enable-rule and --rule are mutually exclusive")

    if output_file and not output_format:
        raise click.UsageError("--output requires --format")

    # Persistent mode not yet implemented for multi-engine
    if persistent:
        click.echo(click.style("Note: --persistent is not yet fully implemented for multi-engine mode", fg="yellow"), err=True)

    # ========== HEADLESS MODE ==========
    if headless or mirror_session:
        import asyncio

        from inspekt.services.headless import HeadlessContext
        from inspekt.services.script_loader import ScriptLoader

        # mirror_session implies headless
        if mirror_session:
            headless = True

        # Validate: headless requires --url or --mirror-session
        if not headless_url and not mirror_session:
            raise click.UsageError("--headless requires --url or --mirror-session")

        # Some features not available in headless mode
        if show_badges:
            click.echo(click.style("Note: --show-badges not available in headless mode (no visual display)", fg="yellow"), err=True)
        if interactive:
            click.echo(click.style("Note: --interactive not available in headless mode", fg="yellow"), err=True)

        # Currently only axe is supported in headless mode
        if engine_list != ["axe"]:
            raise click.UsageError("Headless mode currently only supports axe engine. Use: inspekt a11y axe --headless")

        async def run_headless_audit():
            """Run axe-core audit in headless Chrome."""
            loader = ScriptLoader()

            if not output_format:
                if mirror_session:
                    click.echo(click.style("  Headless mode with session mirroring", fg="blue"), err=True)
                else:
                    click.echo(click.style("  Headless mode", fg="blue"), err=True)

            try:
                async with HeadlessContext(
                    url=headless_url,
                    mirror_session=mirror_session,
                    timeout=timeout,
                ) as ctx:
                    url = ctx.url
                    if not output_format:
                        click.echo(f"URL: {url}", err=True)
                        click.echo(err=True)

                    # Inject axe-core
                    axe_script = loader.load_script_sync("run_axe.js")

                    # Build options for axe
                    axe_options = {
                        "level": level,
                        "showBadges": False,  # No badges in headless
                        "interactive": False,
                        "includePass": show_passes,
                        "includeRecommendations": include_recommendations,
                    }

                    if scoped:
                        axe_options["scoped"] = scoped
                    if exclude:
                        axe_options["exclude"] = list(exclude)
                    if rule:
                        axe_options["rule"] = rule
                    if disable_rule:
                        axe_options["disableRules"] = list(disable_rule)
                    if enable_rule:
                        axe_options["enableRules"] = list(enable_rule)

                    # Replace placeholder and execute
                    import json as json_module
                    code = axe_script.replace("OPTIONS_PLACEHOLDER", json_module.dumps(axe_options))

                    if not output_format:
                        click.echo("Running axe-core audit…", err=True)

                    result = await ctx.execute_script(code)

                    return {"ok": True, "result": result, "url": url}

            except Exception as e:
                return {"ok": False, "error": str(e)}

        # Run async audit
        audit_result = asyncio.run(run_headless_audit())

        if not audit_result.get("ok"):
            if output_format == "json":
                click.echo(json.dumps({"ok": False, "error": audit_result.get("error")}))
            else:
                click.echo(f"Error: {audit_result.get('error')}", err=True)
            sys.exit(1)

        result = audit_result.get("result", {})
        url = audit_result.get("url", "unknown")

        # Process axe results
        if not result.get("ok"):
            if output_format == "json":
                click.echo(json.dumps({"ok": False, "error": result.get("error", "Unknown error")}))
            else:
                click.echo(f"Error: {result.get('error', 'Unknown error')}", err=True)
            sys.exit(1)

        violations = result.get("violations", [])
        passes = result.get("passes", [])
        incomplete = result.get("incomplete", [])

        # Output results
        if output_format == "json":
            output_data = {
                "ok": True,
                "url": url,
                "engine": "axe",
                "level": level,
                "violations": violations,
                "passes": passes if show_passes else [],
                "incomplete": incomplete,
                "summary": {
                    "violations": len(violations),
                    "passes": len(passes),
                    "incomplete": len(incomplete),
                }
            }
            json_str = json.dumps(output_data, indent=2)
            if output_file:
                Path(output_file).write_text(json_str)
                click.echo(f"Results saved to {output_file}", err=True)
            else:
                from inspekt.app.cli.table import print_json
                print_json(output_data, summary=f"a11y audit ({len(violations)} violations)")
        else:
            # Print summary
            click.echo(err=True)
            click.echo(click.style("Summary", bold=True), err=True)
            click.echo(f"  Violations: {len(violations)}", err=True)
            click.echo(f"  Passes: {len(passes)}", err=True)
            click.echo(f"  Incomplete: {len(incomplete)}", err=True)
            click.echo(err=True)

            if violations:
                click.echo(click.style("Violations:", bold=True, fg="red"), err=True)
                for v in violations:
                    impact = v.get("impact", "unknown")
                    impact_color = {"critical": "red", "serious": "yellow", "moderate": "cyan", "minor": "white"}.get(impact, "white")
                    from inspekt.app.cli.sitemap import wrap_styled_line
                    for line in wrap_styled_line(
                        prefix=f"  [{click.style(impact, fg=impact_color)}] {v.get('id')}: ",
                        text=v.get('description', ''),
                    ):
                        click.echo(line, err=True)
                    click.echo(f"    Affected: {len(v.get('nodes', []))} element(s)", err=True)
                click.echo(err=True)

        return  # Exit early - headless mode complete

    client = BridgeClient()
    client.quiet = bool(output_format)  # Suppress warnings in format mode

    # Get URL first
    url_result = client.execute("window.location.href", timeout=5.0)
    url = url_result.get("result", "unknown") if url_result.get("ok") else "unknown"

    # Get tool versions
    versions = _get_tool_versions()

    # Note: Badge injection happens at the end of the normal audit flow
    # This ensures consistent CLI output whether or not badges are requested

    # Show progress header (unless format output)
    is_single_engine = len(engine_list) == 1
    if not output_format:
        click.echo(click.style("Running Accessibility Audit", bold=True), err=True)
        click.echo(f"URL: {url}", err=True)
        click.echo(err=True)

        # Only show "Engines:" line for multiple engines
        if not is_single_engine:
            engine_names = [f"{AVAILABLE_ENGINES[e]['name']} ({AVAILABLE_ENGINES[e]['abbr']})" for e in engine_list]
            click.echo(f"Engines: {', '.join(engine_names)}", err=True)
            # Warn about slow engines
            slow_engines = [AVAILABLE_ENGINES[e]['name'] for e in engine_list if AVAILABLE_ENGINES[e].get('performance') == 'slow']
            if slow_engines:
                engines_str = ", ".join(slow_engines)
                click.echo(click.style(f"Note: {engines_str} may take longer to complete on complex pages.", fg="bright_black"), err=True)
            click.echo(err=True)

    # Run engines in order
    total_start = time.time()
    engine_results = _run_engines_in_order(client, engine_list, level, timeout, versions, quiet=bool(output_format), include_recommendations=include_recommendations)
    total_elapsed = time.time() - total_start

    if not output_format:
        click.echo(err=True)
        # Only show total time for multiple engines
        if not is_single_engine:
            click.echo(f"The scanning took {total_elapsed:.1f} seconds in total", err=True)
            click.echo(err=True)

        # Show warning about automated checker limitations (unless disabled via CLI or config)
        from inspekt.config import get_a11y_config
        a11y_config = get_a11y_config()
        show_warning = a11y_config.get("show-compliance-warning", True) and not no_compliance_warning

        if show_warning:
            click.echo(click.style("WARNING", fg="yellow", bold=True), err=True)
            warning_text = "Traditional accessibility checkers identify only about 20–50% of WCAG issues and may produce false positives. You cannot rely on these results to claim WCAG compliance."
            print_wrapped(warning_text, err=True)
            click.echo(err=True)

    # Show per-engine rule tables in verbose mode (skip in format mode)
    if verbose and not output_format:
        _print_engine_rule_tables(engine_results, engine_list)
        click.echo()

    # Consolidate results
    consolidated = _consolidate_by_wcag_multi(engine_results, engine_list)

    # Filter by WCAG conformance level
    # This ensures only SCs matching the requested level are shown
    consolidated = {
        sc: data for sc, data in consolidated.items()
        if _sc_matches_level(sc, level)
    }

    # URL was already retrieved at the start

    # Helper to count violations from filtered consolidated results
    def count_filtered_violations(engine: str) -> int:
        """Count violations for an engine from the level-filtered consolidated results."""
        count = 0
        for _sc, data in consolidated.items():
            status = data.get(f"{engine}_status", "pass")
            sc_count = data.get(f"{engine}_count", 0)
            # Count violations and potential violations
            if status in ("violation", "potentialviolation"):
                count += sc_count
        return count

    if output_format in ("json", "html"):
        enriched = _build_enriched_report_data(
            url=url,
            level=level,
            engine_list=engine_list,
            engine_results=engine_results,
            consolidated=consolidated,
            versions=versions,
            include_recommendations=include_recommendations,
        )

        if output_format == "json":
            json_str = json.dumps(enriched, indent=2)
            if output_file:
                output_path = Path(output_file)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                click.echo(success(f"Report saved to: {output_path}"), err=True)
            else:
                from inspekt.app.cli.table import print_json
                print_json(enriched, summary="a11y report")
            return

        if output_format == "html":
            from inspekt.services.a11y_report import generate_a11y_report_html
            html_content = generate_a11y_report_html(enriched)

            if output_file:
                path = Path(output_file)
            else:
                from datetime import datetime
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace(".", "_")
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = Path.cwd() / f"inspekt_a11y_{domain}_{timestamp_str}.html"

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html_content, encoding="utf-8")
            click.echo(success(f"Report saved to: {path}"), err=True)

            if not no_open:
                import webbrowser
                webbrowser.open(f"file://{path.resolve()}")
            return

    # Filter results - show SCs where any engine found issues
    if not show_passes:
        consolidated = {
            sc: data for sc, data in consolidated.items()
            if any(data.get(f"{eng}_status") != "pass" for eng in engine_list)
        }

    if not consolidated:
        engine_word = "any engine" if len(engine_list) > 1 else engine_list[0]
        click.echo(click.style(success(f"No accessibility issues found by {engine_word}!"), fg="green", bold=True))
        click.echo(f"Tested: {url}")
        # Show contextual tips even when no issues found
        if not output_format:
            click.echo()
            tips = _get_contextual_tips(
                engine_list=engine_list,
                issue_count=0,
                level=level,
                show_badges=show_badges,
                interactive=interactive,
                verbose=verbose,
                show_passes=show_passes,
                include_recommendations=include_recommendations,
            )
            _print_tips_section(tips)
        return

    # Sort by SC number
    def sc_sort_key(sc):
        parts = sc.split(".")
        return tuple(int(p) for p in parts)

    sorted_scs = sorted(consolidated.keys(), key=sc_sort_key)

    # Analyze results for disagreements and disparities
    issues_count = 0
    disagreements = []  # SCs where some engines fail and others pass
    disparities = []    # SCs where all fail but counts differ significantly

    for sc in sorted_scs:
        data = consolidated[sc]

        # Check which engines fail
        engine_fails = {
            eng: data.get(f"{eng}_status") not in ("pass",)
            for eng in engine_list
        }
        engine_counts = {
            eng: data.get(f"{eng}_count", 0)
            for eng in engine_list
        }

        failing_engines = [eng for eng, fails in engine_fails.items() if fails]
        passing_engines = [eng for eng, fails in engine_fails.items() if not fails]

        # Count as issue if any engine found something
        if failing_engines:
            issues_count += 1

        # Track disagreements (some fail, others pass)
        if failing_engines and passing_engines:
            disagreements.append({
                "sc": sc,
                "failing_engines": failing_engines,
                "passing_engines": passing_engines,
                "counts": {eng: engine_counts[eng] for eng in failing_engines}
            })

        # Track disparities (all fail but counts differ by 2x or more)
        if len(failing_engines) >= 2:
            counts = [engine_counts[eng] for eng in failing_engines if engine_counts[eng] > 0]
            if len(counts) >= 2:
                min_c, max_c = min(counts), max(counts)
                if min_c > 0 and max_c / min_c >= 2:
                    disparities.append({
                        "sc": sc,
                        "counts": engine_counts,
                        "min_count": min_c,
                        "max_count": max_c,
                        "ratio": max_c / min_c
                    })

    # Build and print pivoted table (one row per engine per WCAG SC)
    if not summary_only:
        _print_pivoted_results_table(consolidated, engine_list, sorted_scs, issues_count)

    # VM terminal: offer a "Data ready to copy" toast
    from inspekt.app.cli.table import emit_copyable_data
    a11y_headers = ["WCAG SC"] + [f"{eng} status" for eng in engine_list] + [f"{eng} count" for eng in engine_list]
    a11y_rows = []
    for sc in sorted_scs:
        d = consolidated[sc]
        row = [sc]
        for eng in engine_list:
            row.append(str(d.get(f"{eng}_status", "")))
        for eng in engine_list:
            row.append(str(d.get(f"{eng}_count", 0)))
        a11y_rows.append(row)
    emit_copyable_data(
        headers=a11y_headers,
        rows=a11y_rows,
        json_data={
            "url": url,
            "level": level,
            "engines": engine_list,
            "consolidated": consolidated,
            "issues_count": issues_count,
            "disagreements": disagreements,
            "disparities": disparities,
        },
        summary=f"{issues_count} WCAG criteria with issues",
    )

    # Summary - simpler for single engine
    click.echo()
    if is_single_engine:
        click.echo(click.style(f"Summary: {issues_count} WCAG {pluralize(issues_count, 'criterion', 'criteria')} with issues", bold=True))
    else:
        click.echo(click.style(f"Summary: {issues_count} WCAG criteria with issues", bold=True))
        for engine in engine_list:
            engine_name = AVAILABLE_ENGINES[engine]["name"]
            engine_result = engine_results.get(engine, {})
            # Check if engine had an error
            if engine_result.get("error"):
                click.echo(click.style(f"  {engine_name}: skipped (error)", fg="yellow"))
            elif engine == "sia":
                # Show both rules and element count for Alfa
                v_count = _count_violations(engine_result, engine)
                elem_count = _count_alfa_elements(engine_result)
                click.echo(f"  {engine_name}: {v_count} {pluralize(v_count, 'rule')} ({elem_count} {pluralize(elem_count, 'element')})")
            else:
                v_count = _count_violations(engine_result, engine)
                click.echo(f"  {engine_name}: {v_count} {pluralize(v_count, 'violation')}")

    # Show engine agreement insight (only for multiple engines)
    if not is_single_engine:
        correlation = _calculate_engine_correlation(consolidated, engine_list)
        agreement_pct = correlation["agreement_percentage"]
        disagreement_count = correlation["disagreement"]

        # Choose color and icon based on agreement level
        if agreement_pct >= 90:
            color = "green"
            icon = get_status_icon("pass") or ""
        elif agreement_pct >= 70:
            color = "yellow"
            icon = get_status_icon("warning") or ""
        else:
            color = "red"
            icon = get_status_icon("fail") or ""

        # Add space after icon if present
        icon_str = f"{icon} " if icon else ""

        click.echo()
        click.echo(click.style(
            f"{icon_str}Engine agreement: {agreement_pct}% "
            f"({correlation['full_agreement']}/{correlation['total_scs']} criteria)",
            fg=color
        ))

        if disagreement_count > 0:
            click.echo(click.style(
                f"  {disagreement_count} {pluralize(disagreement_count, 'criterion', 'criteria')} "
                f"with mixed results (see Disagreements below)",
                fg="bright_black"
            ))

    # Show disagreements
    if disagreements:
        click.echo()
        limit = None if all_disagreements else 10
        display_disagreements = disagreements if limit is None else disagreements[:limit]

        headers = ["WCAG SC", "Level", "Description", "Failing Engines", "Passing Engines"]
        alignments = ["left", "left", "left", "left", "left"]
        rows = []
        row_colors = []

        for item in display_disagreements:
            sc = item["sc"]
            sc_info = WCAG_SC_LEVELS.get(sc, {})
            sc_level = sc_info.get("level", "")
            desc = WCAG_SC_DESCRIPTIONS.get(sc, "")

            # Format failing engines with counts (use uppercase abbreviations)
            failing_parts = []
            for eng in item["failing_engines"]:
                count = item["counts"].get(eng, 0)
                abbr = AVAILABLE_ENGINES[eng]["abbr"]
                failing_parts.append(f"{abbr} ({count})")
            failing_str = ", ".join(failing_parts)

            # Format passing engines (use uppercase abbreviations)
            passing_str = ", ".join(AVAILABLE_ENGINES[eng]["abbr"] for eng in item["passing_engines"])

            rows.append([sc, sc_level, desc, failing_str, passing_str])
            row_colors.append(["yellow", None, None, "red", "green"])

        table = Table(headers, alignments=alignments, title="Disagreements", icon=get_status_icon("warning"))
        table.set_data(rows)
        table.print_header()
        for row_data, colors in zip(rows, row_colors, strict=False):
            table.print_row(row_data, colors)
        table.print_footer()

        remaining = len(disagreements) - len(display_disagreements)
        if remaining > 0:
            click.echo(_style_with_inline_code(f"  …and {remaining} more (use `--all-disagreements` to show all)", base_fg="bright_black"))

    # Show disparities
    if disparities:
        click.echo()
        limit = None if all_disagreements else 10
        display_disparities = disparities if limit is None else disparities[:limit]

        headers = ["WCAG SC", "Level", "Description", "Counts"]
        alignments = ["left", "left", "left", "left"]
        rows = []
        row_colors = []

        for item in display_disparities:
            sc = item["sc"]
            sc_info = WCAG_SC_LEVELS.get(sc, {})
            sc_level = sc_info.get("level", "")
            desc = WCAG_SC_DESCRIPTIONS.get(sc, "")

            # Format counts for all engines (use uppercase abbreviations)
            count_parts = []
            for eng in engine_list:
                count = item["counts"].get(eng, 0)
                abbr = AVAILABLE_ENGINES[eng]["abbr"]
                count_parts.append(f"{abbr}: {count}")
            counts_str = " vs ".join(count_parts)

            rows.append([sc, sc_level, desc, counts_str])
            row_colors.append(["cyan", None, None, "cyan"])

        table = Table(headers, alignments=alignments, title="Disparities", icon=get_status_icon("review"))
        table.set_data(rows)
        table.print_header()
        for row_data, colors in zip(rows, row_colors, strict=False):
            table.print_row(row_data, colors)
        table.print_footer()

        remaining = len(disparities) - len(display_disparities)
        if remaining > 0:
            click.echo(_style_with_inline_code(f"  …and {remaining} more (use `--all-disagreements` to show all)", base_fg="bright_black"))

    # Show recommendations section (when --include-recommendations is used)
    if include_recommendations:
        _print_recommendations_section(engine_results, engine_list)

    # Show contextual tips section
    if not output_format:
        click.echo()
        tips = _get_contextual_tips(
            engine_list=engine_list,
            issue_count=issues_count,
            level=level,
            show_badges=show_badges,
            interactive=interactive,
            verbose=verbose,
            show_passes=show_passes,
            include_recommendations=include_recommendations,
        )
        _print_tips_section(tips)

    # Inject badges after showing all CLI output (if requested)
    if show_badges and issues_count > 0:
        _inject_badges_into_page(client, engine_list, level, timeout, interactive, dev_css, include_recommendations)


@click.command(name="a11y-reset")
def a11y_reset():
    """
    Reset accessibility audit state and remove all badges/popovers.

    This removes all Inspekt accessibility UI elements from the page
    (badges, popovers, styles) and clears engine tracking state so
    a fresh audit can be run.

    Useful when:
    - You want to re-run audits with a clean slate
    - Badges are cluttering the page
    - You want to clear persistent mode state

    \b
    Example:
        inspekt a11y-reset
    """
    from inspekt.config import get_bridge_port
    from inspekt.services.bridge_executor import BridgeExecutor

    executor = BridgeExecutor(port=get_bridge_port())

    if not executor.is_server_running():
        click.secho("Error: Bridge server is not running.", fg="red", err=True)
        click.echo("Start it with: inspekt start", err=True)
        sys.exit(1)

    if not executor.has_active_browser_connection():
        click.secho("Error: No browser connected.", fg="red", err=True)
        sys.exit(1)

    # Execute the reset function from engine-tracker.js
    result = executor.execute(
        "window.__inspektResetAll__ ? window.__inspektResetAll__() : { ok: false, error: 'Tracker not loaded' }",
        timeout=5.0,
        skip_domain_check=True
    )

    if not result.get("ok"):
        click.secho(f"Error: {result.get('error', 'Unknown error')}", fg="red", err=True)
        sys.exit(1)

    data = result.get("result", {})
    if data.get("ok"):
        click.secho(success("All accessibility badges and state cleared"), fg="green")
    else:
        error_msg = data.get("error", "Tracker not initialized - no state to clear")
        click.secho(f"Note: {error_msg}", fg="yellow")
