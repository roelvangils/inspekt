"""
Accessibility testing and audit commands.

This module provides commands for testing web accessibility:
- axe: Run axe-core accessibility audit on current page

These commands help identify WCAG violations and accessibility issues.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from inspekt.app.cli.base import builtin_open
from inspekt.client import BridgeClient


def _build_axe_config(level: str, tags: str | None, include_passes: bool, include_incomplete: bool) -> dict:
    """
    Build axe-core configuration object from CLI arguments.

    Args:
        level: WCAG level (2a, 2aa, 2aaa, 21a, 21aa, 22aa)
        tags: Additional comma-separated tags
        include_passes: Whether to include passing checks
        include_incomplete: Whether to include incomplete checks

    Returns:
        Configuration dict for axe.run()
    """
    # Map WCAG levels to axe tags
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

    # Build config
    config = {
        "runOnly": {
            "type": "tag",
            "values": axe_tags
        },
        "resultTypes": ["violations"]
    }

    # Add optional result types
    if include_passes:
        config["resultTypes"].append("passes")
    if include_incomplete:
        config["resultTypes"].append("incomplete")

    return config


def _format_table_row(columns: list[str], widths: list[int], colors: list[str | None] = None) -> str:
    """Format a table row with fixed column widths and optional colors."""
    if colors is None:
        colors = [None] * len(columns)

    parts = []
    for i, col in enumerate(columns):
        # Truncate if too long
        if len(col) > widths[i]:
            col = col[:widths[i] - 3] + "..."
        # Pad to width
        padded = col.ljust(widths[i])
        # Apply color if specified
        if colors[i]:
            padded = click.style(padded, fg=colors[i])
        parts.append(padded)

    # Use dark gray for borders
    border = click.style("│", fg="bright_black")
    return border + " " + (" " + border + " ").join(parts) + " " + border


def _format_table_separator(widths: list[int], top: bool = False, bottom: bool = False) -> str:
    """Format a table separator line with dark gray color."""
    if top:
        left, mid, right = "┌", "┬", "┐"
    elif bottom:
        left, mid, right = "└", "┴", "┘"
    else:
        left, mid, right = "├", "┼", "┤"

    parts = [("─" * (w + 2)) for w in widths]
    line = left + mid.join(parts) + right
    return click.style(line, fg="bright_black")


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
            click.echo(json.dumps({"rules": rules, "stats": stats, "axeVersion": data.get("axeVersion")}, indent=2))
            return

        # Display rules in a formatted list
        click.echo()
        click.echo(click.style(f"Available Axe-core Rules (v{data.get('axeVersion', 'unknown')})", bold=True))
        click.echo(click.style(f"Total: {stats.get('total', 0)} rules", fg="bright_black"))
        click.echo()

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

        # Display groups
        group_labels = {
            "wcag2a": "WCAG 2.0 Level A",
            "wcag2aa": "WCAG 2.0 Level AA",
            "wcag21aa": "WCAG 2.1 Level AA",
            "wcag22aa": "WCAG 2.2 Level AA",
            "best-practice": "Best Practice",
            "other": "Other"
        }

        for group_key, group_label in group_labels.items():
            group_rules = wcag_groups.get(group_key, [])
            if not group_rules:
                continue

            click.echo(click.style(f"{group_label} ({len(group_rules)} rules)", fg="cyan", bold=True))
            for rule in group_rules:
                rule_id = rule.get("id", "")
                description = rule.get("description", "")
                # Truncate description if too long
                if len(description) > 80:
                    description = description[:77] + "..."
                click.echo(f"  {click.style(rule_id, fg='green')}: {description}")
            click.echo()

        # Show usage hint
        click.echo(click.style("Usage:", bold=True))
        click.echo("  inspekt axe --rule <rule-id>")
        click.echo()
        click.echo(click.style("Example:", bold=True))
        click.echo("  inspekt axe --rule color-contrast")
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
        click.echo(click.style(f"✓ No violations found for rule: {rule_id}", fg="green", bold=True))
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
                html = html[:197] + "..."
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
                click.echo(click.style("✓ Element auto-selected and highlighted in browser", fg="green"))
                click.echo(f"  Selector: {click.style(selector, fg='yellow')}")
                click.echo(f"  Run {click.style('inspekt inspected', bold=True)} to view full element details")

    # Footer
    click.echo()
    click.echo(f"Tested: {url}")


def _format_table_output(violations: list[dict], url: str, summary: dict) -> None:
    """Format violations as a table."""
    if not violations:
        click.echo()
        click.echo(click.style("✓ No accessibility violations found!", fg="green", bold=True))
        click.echo(f"Tested: {url}")
        click.echo(f"Passes: {summary.get('passCount', 0)}")
        return

    # Sort violations by impact (critical -> serious -> moderate -> minor)
    impact_order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
    violations = sorted(violations, key=lambda v: impact_order.get(v.get("impact", "minor"), 4))

    # Table column widths
    widths = [25, 10, 7, 50]

    # Table header
    click.echo()
    click.echo(_format_table_separator(widths, top=True))
    header = _format_table_row(["Rule", "Impact", "Count", "Description"], widths)
    click.echo(click.style(header, bold=True))
    click.echo(_format_table_separator(widths))

    # Table rows
    for violation in violations:
        rule_id = violation.get("id", "unknown")
        impact = violation.get("impact", "unknown")
        count = violation.get("nodeCount", 0)
        description = violation.get("description", "")

        # Format row with impact color on the impact column
        row_data = [rule_id, impact, str(count), description]
        row_colors = [None, _get_impact_color(impact), None, None]
        row = _format_table_row(row_data, widths, row_colors)
        click.echo(row)

    click.echo(_format_table_separator(widths, bottom=True))

    # Summary
    click.echo()
    violation_count = summary.get('violationCount', 0)
    violation_word = "violation" if violation_count == 1 else "violations"
    click.echo(click.style(f"Summary: Found {violation_count} {violation_word}", bold=True))

    # Format counts: use "None" for 0, otherwise show number
    def format_count(count):
        return "None" if count == 0 else str(count)

    click.echo(f"  Critical: {format_count(summary.get('criticalCount', 0))}")
    click.echo(f"  Serious:  {format_count(summary.get('seriousCount', 0))}")
    click.echo(f"  Moderate: {format_count(summary.get('moderateCount', 0))}")
    click.echo(f"  Minor:    {format_count(summary.get('minorCount', 0))}")
    click.echo()
    click.echo(f"Passes:     {summary.get('passCount', 0)}")
    if summary.get('incompleteCount', 0) > 0:
        click.echo(f"Incomplete: {summary.get('incompleteCount', 0)} (use --include-incomplete to see details)")
    click.echo(f"Tested:     {url}")


@click.command()
@click.option(
    "--level",
    type=click.Choice(["2a", "2aa", "2aaa", "21a", "21aa", "22aa"], case_sensitive=False),
    default="2aa",
    help="WCAG conformance level to test (default: 2aa)"
)
@click.option(
    "--rule",
    type=str,
    help="Check specific accessibility rule by ID (e.g., 'color-contrast', 'link-name')"
)
@click.option(
    "--list-rules",
    is_flag=True,
    help="List all available axe-core rules and exit"
)
@click.option(
    "--tags",
    type=str,
    help="Additional comma-separated tags (e.g., 'best-practice,experimental')"
)
@click.option(
    "--include-passes",
    is_flag=True,
    help="Include passing checks in output"
)
@click.option(
    "--include-incomplete",
    is_flag=True,
    help="Include incomplete checks (require manual review)"
)
@click.option(
    "--json",
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
    "--no-select",
    is_flag=True,
    help="Disable auto-selection of element when single violation is found (only applies to --rule checks)"
)
def axe(level, rule, list_rules, tags, include_passes, include_incomplete, output_json, timeout, no_select):
    """
    Run axe-core accessibility audit on the current page.

    Analyzes the page for WCAG conformance violations using the industry-standard
    axe-core library. By default, tests against WCAG 2 Level AA standards.

    The audit runs in your current browser tab, testing the actual rendered page
    state including any JavaScript-generated content and your authentication state.

    When checking a single rule (--rule) with exactly one violation, the element
    is automatically selected and highlighted in the browser. Use --no-select to
    disable this behavior.

    Examples:
        inspekt axe                                    # WCAG 2.1 Level AA audit
        inspekt axe --level 21aa                       # WCAG 2.1 Level AA audit
        inspekt axe --rule color-contrast              # Check single rule (auto-selects if 1 violation)
        inspekt axe --rule color-contrast --no-select  # Disable auto-selection
        inspekt axe --list-rules                       # List all available rules
        inspekt axe --tags best-practice --include-incomplete
        inspekt axe --json > audit-results.json
    """
    # Validation: --rule and --level are mutually exclusive
    if rule and level != "2aa":  # "2aa" is the default, so it's okay
        click.echo("Error: --rule and --level are mutually exclusive. Use --rule for specific rules or --level for WCAG conformance testing.", err=True)
        sys.exit(1)

    client = BridgeClient()

    if not client.is_alive():
        click.echo("Error: Bridge server is not running. Start it with: inspekt server start", err=True)
        sys.exit(1)

    # Handle --list-rules flag
    if list_rules:
        _list_available_rules(client, timeout, output_json)
        return

    # Build axe configuration
    if rule:
        # Single rule check
        config = {
            "runOnly": {
                "type": "rule",
                "values": [rule]
            },
            "resultTypes": ["violations"]
        }
        # Add optional result types
        if include_passes:
            config["resultTypes"].append("passes")
        if include_incomplete:
            config["resultTypes"].append("incomplete")
    else:
        # WCAG level-based check (existing behavior)
        config = _build_axe_config(level, tags, include_passes, include_incomplete)

    # Load axe-core library (bundled locally)
    axe_lib_path = Path(__file__).parent.parent.parent / "scripts" / "vendor" / "axe-core.min.js"
    if not axe_lib_path.exists():
        click.echo(f"Error: axe-core library not found: {axe_lib_path}", err=True)
        sys.exit(1)

    # Load the run_axe script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "run_axe.js"
    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        # Read axe-core library
        with builtin_open(axe_lib_path) as f:
            axe_lib = f.read()

        # Read audit script
        with builtin_open(script_path) as f:
            audit_script = f.read()

        # Replace config placeholder
        audit_script = audit_script.replace("__AXE_CONFIG__", json.dumps(config))

        # Combine: axe-core library + audit script in a single async IIFE
        # This avoids semicolon issues with AsyncFunction wrapper
        script = f"""(async function() {{
    // Load axe-core library
    {axe_lib}

    // Run audit
    const auditResult = await {audit_script};
    return auditResult;
}})()"""

        # Show warning about automated testing limitations
        click.echo(click.style("WARNING:", fg="yellow", bold=True) + " Automated accessibility testing tools like Axe can detect only 20 to 30% of (potential) WCAG failures. To achieve complete WCAG compliance, it is essential to combine automated scans with manual checks.", err=True)
        click.echo("", err=True)

        # Show progress
        if rule:
            # Rule-specific check
            click.echo(f"Running Accessibility Check (Rule: {rule})", err=True)
        else:
            # WCAG level-based check
            # Map level codes to full standard names
            level_names = {
                "2a": "WCAG 2.0 Level A",
                "2aa": "WCAG 2.1 Level AA",
                "2aaa": "WCAG 2.0 Level AAA",
                "21a": "WCAG 2.1 Level A",
                "21aa": "WCAG 2.1 Level AA",
                "22aa": "WCAG 2.2 Level AA",
            }
            level_label = level_names.get(level.lower(), f"WCAG {level.upper()}")
            if tags:
                level_label += f" + {tags}"
            click.echo(f"Running Accessibility Audit ({level_label})", err=True)

        # Execute the script
        result = client.execute(script, timeout=timeout)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        data = result.get("result", {})

        # Check if script execution failed
        if not data.get("ok"):
            click.echo(f"Error executing axe-core: {data.get('error')}", err=True)
            sys.exit(1)

        # Extract results
        violations = data.get("violations", [])
        passes = data.get("passes", [])
        incomplete_checks = data.get("incomplete", [])
        summary = data.get("summary", {})
        url = data.get("url", "")

        if output_json:
            # Output full JSON
            output_data = {
                "url": url,
                "title": data.get("title", ""),
                "timestamp": data.get("timestamp", ""),
                "axeVersion": data.get("axeVersion", ""),
                "config": config,
                "violations": violations,
                "summary": summary
            }
            if include_passes:
                output_data["passes"] = passes
            if include_incomplete:
                output_data["incomplete"] = incomplete_checks

            click.echo(json.dumps(output_data, indent=2))
            return

        # Adaptive output: detailed for single rule, table for multiple rules/WCAG levels
        if rule:
            # Single rule check: show detailed output
            _format_detailed_violation_output(violations, url, rule, no_select)
        else:
            # WCAG level check: show table output
            _format_table_output(violations, url, summary)

        # Show incomplete checks if requested
        if include_incomplete and incomplete_checks:
            click.echo(click.style("Incomplete Checks (Manual Review Required):", bold=True))
            click.echo()
            for item in incomplete_checks:
                impact = item.get("impact", "unknown")
                color = _get_impact_color(impact)
                click.echo(f"  {click.style('•', fg=color)} {item.get('id')}: {item.get('description')} ({item.get('nodeCount', 0)} elements)")
            click.echo()

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
