"""
Robots.txt command - Fetch and parse robots.txt files.

This module provides the robots command for inspecting robots.txt files:
- Fetches robots.txt from the current page's origin
- Parses with RFC 9309 compliance (using protego or urllib fallback)
- Validates syntax and reports errors/warnings
- Outputs in human-readable or JSON format
"""

from __future__ import annotations

import re
import sys
from typing import Any

import click
import requests

from inspekt.app.cli.icons import get_icon
from inspekt.app.cli.table import Table, format_status_icon, print_json
from inspekt.services import http_client

# Try to import protego for RFC 9309 compliance
try:
    from protego import Protego

    HAS_PROTEGO = True
except ImportError:
    HAS_PROTEGO = False
    # Fall back to urllib.robotparser
    from urllib.robotparser import RobotFileParser


@click.command()
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
@click.option("--validate", is_flag=True, help="Show detailed validation errors and warnings")
@click.option(
    "--url", "override_url", type=str, help="Specify URL to inspect (overrides current page)"
)
def robots(output_json, validate, override_url):
    """
    Fetch and parse robots.txt for the current page.

    Retrieves the robots.txt file from the current page's origin,
    parses it according to RFC 9309, and displays the rules, sitemaps,
    and metadata.

    Examples:
        inspekt robots
        inspekt robots --json
        inspekt robots --validate
        inspekt robots --url https://example.com
    """
    from inspekt.app.cli.table import print_error as _print_error
    from inspekt.app.cli.table import print_hint as _print_hint
    from inspekt.services.browser_url import BrowserURLError, InternalURLError, resolve_origin

    try:
        origin = resolve_origin(override_url)
    except InternalURLError:
        _print_error("This command requires a real website (http/https)")
        _print_hint("Navigate to a website first, then try again")
        sys.exit(0)
    except BrowserURLError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    robots_url = f"{origin}/robots.txt"

    # Fetch robots.txt
    robots_data = _fetch_robots_txt(robots_url)

    if not robots_data.get("exists"):
        # robots.txt not found
        if output_json:
            print_json(robots_data, summary="robots.txt not found")
        else:
            click.echo(f"robots.txt: {robots_url}")
            click.echo(f"Status: {robots_data.get('status')} - Not Found")
            click.echo()
            click.echo("Interpretation: No robots.txt means all crawlers are allowed on all paths.")
        sys.exit(0 if robots_data.get("status") == 404 else 1)

    # Parse robots.txt content
    content = robots_data.get("content", "")
    parsed_data = _parse_robots_txt(content, robots_url)

    # Combine metadata and parsed data
    output_data = {
        "url": robots_url,
        "status": robots_data.get("status"),
        "exists": robots_data.get("exists"),
        "metadata": robots_data.get("metadata", {}),
        **parsed_data,
    }

    # Add validation if requested or in JSON mode
    if validate or output_json:
        validation_results = _validate_robots_txt(content, parsed_data)
        output_data["validation"] = validation_results

    # Output results
    if output_json:
        rule_count = sum(len(g.get("rules", [])) for g in output_data.get("groups", []))
        print_json(output_data, summary=f"robots.txt — {rule_count} rules")
    else:
        _display_robots_txt(output_data, validate)


def _fetch_robots_txt(robots_url: str) -> dict[str, Any]:
    """
    Fetch robots.txt from the given URL.

    Args:
        robots_url: Full URL to robots.txt

    Returns:
        Dictionary with fetch results including status, metadata, and content
    """
    try:
        response = http_client.get(
            robots_url,
            timeout=5,
            headers={"User-Agent": "Inspekt-CLI-RobotsTxt-Checker"},
            allow_redirects=True,
        )

        # Check if robots.txt is too large (RFC 9309: should be < 500KB)
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > 500 * 1024:
            return {
                "url": robots_url,
                "status": 413,
                "exists": False,
                "error": f"robots.txt too large: {int(content_length) / 1024:.1f}KB (max 500KB per RFC 9309)",
            }

        if response.status_code == 200:
            # Calculate actual size
            content = response.text
            size_bytes = len(content.encode("utf-8"))

            # Extract metadata
            metadata = {
                "size": size_bytes,
                "lines": len(content.splitlines()),
                "encoding": response.encoding or "utf-8",
                "contentType": response.headers.get("Content-Type", "unknown"),
            }

            # Optional metadata
            if last_modified := response.headers.get("Last-Modified"):
                metadata["lastModified"] = last_modified

            if etag := response.headers.get("ETag"):
                metadata["etag"] = etag

            # Check for redirects
            if response.url != robots_url:
                metadata["finalUrl"] = response.url

            return {
                "url": robots_url,
                "status": 200,
                "exists": True,
                "content": content,
                "metadata": metadata,
            }
        else:
            return {
                "url": robots_url,
                "status": response.status_code,
                "exists": False,
                "error": f"HTTP {response.status_code}",
            }

    except requests.Timeout:
        return {
            "url": robots_url,
            "status": 0,
            "exists": False,
            "error": "Request timeout after 5 seconds",
        }
    except requests.ConnectionError as e:
        return {
            "url": robots_url,
            "status": 0,
            "exists": False,
            "error": f"Connection error: {e!s}",
        }
    except requests.RequestException as e:
        return {"url": robots_url, "status": 0, "exists": False, "error": f"Request failed: {e!s}"}


def _parse_robots_txt(content: str, robots_url: str) -> dict[str, Any]:
    """
    Parse robots.txt content into structured data.

    Args:
        content: Raw robots.txt content
        robots_url: URL of the robots.txt file

    Returns:
        Dictionary with groups, sitemaps, comments, and raw content
    """
    if HAS_PROTEGO:
        return _parse_with_protego(content, robots_url)
    else:
        return _parse_with_urllib(content, robots_url)


def _parse_with_protego(content: str, robots_url: str) -> dict[str, Any]:
    """Parse robots.txt using protego (RFC 9309 compliant)."""
    Protego.parse(content)  # parse for validation; groups are extracted manually below

    # Extract groups (user-agents with their rules)
    groups = []
    current_agents = []
    current_rules = []
    current_crawl_delay = None
    current_request_rate = None

    lines = content.splitlines()
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if ":" in stripped:
            directive, _, value = stripped.partition(":")
            directive = directive.strip().lower()
            value = value.strip()

            if directive == "user-agent":
                # Start new group if we have rules
                if current_agents and current_rules:
                    groups.append(
                        {
                            "userAgents": current_agents,
                            "rules": current_rules,
                            **({"crawlDelay": current_crawl_delay} if current_crawl_delay else {}),
                            **(
                                {"requestRate": current_request_rate}
                                if current_request_rate
                                else {}
                            ),
                        }
                    )
                    current_rules = []
                    current_crawl_delay = None
                    current_request_rate = None

                current_agents.append(value)

            elif directive in ("allow", "disallow"):
                current_rules.append(
                    {"directive": directive.capitalize(), "path": value, "line": line_num}
                )

            elif directive == "crawl-delay":
                try:
                    current_crawl_delay = float(value)
                except ValueError:
                    pass

            elif directive == "request-rate":
                current_request_rate = value

    # Add last group
    if current_agents and current_rules:
        groups.append(
            {
                "userAgents": current_agents,
                "rules": current_rules,
                **({"crawlDelay": current_crawl_delay} if current_crawl_delay else {}),
                **({"requestRate": current_request_rate} if current_request_rate else {}),
            }
        )

    # Extract sitemaps
    sitemaps = []
    for line in lines:
        if line.strip().lower().startswith("sitemap:"):
            _, _, sitemap_url = line.partition(":")
            sitemaps.append(sitemap_url.strip())

    # Extract comments
    comments = []
    for line_num, line in enumerate(lines, 1):
        if "#" in line:
            # Handle inline comments
            comment_start = line.index("#")
            comment_text = line[comment_start:].strip()
            if comment_text:
                comments.append({"line": line_num, "text": comment_text})

    return {"groups": groups, "sitemaps": sitemaps, "comments": comments, "raw": content}


def _parse_with_urllib(content: str, robots_url: str) -> dict[str, Any]:
    """Parse robots.txt using urllib.robotparser (fallback, less RFC 9309 compliant)."""
    rp = RobotFileParser()
    rp.parse(content.splitlines())

    # Manual parsing since urllib doesn't expose structured data easily
    groups = []
    sitemaps = []
    comments = []
    current_agents = []
    current_rules = []

    lines = content.splitlines()
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        if not stripped:
            continue

        if stripped.startswith("#"):
            comments.append({"line": line_num, "text": stripped})
            continue

        if ":" in stripped:
            directive, _, value = stripped.partition(":")
            directive = directive.strip().lower()
            value = value.strip()

            if directive == "user-agent":
                # Start new group if we have rules
                if current_agents and current_rules:
                    groups.append({"userAgents": current_agents, "rules": current_rules})
                    current_rules = []

                current_agents.append(value)

            elif directive in ("allow", "disallow"):
                current_rules.append(
                    {"directive": directive.capitalize(), "path": value, "line": line_num}
                )

            elif directive == "sitemap":
                sitemaps.append(value)

    # Add last group
    if current_agents and current_rules:
        groups.append({"userAgents": current_agents, "rules": current_rules})

    return {"groups": groups, "sitemaps": sitemaps, "comments": comments, "raw": content}


def _validate_robots_txt(content: str, parsed_data: dict[str, Any]) -> dict[str, Any]:
    """
    Validate robots.txt syntax and generate warnings.

    Args:
        content: Raw robots.txt content
        parsed_data: Parsed robots.txt data

    Returns:
        Dictionary with errors and warnings lists
    """
    errors = []
    warnings = []

    lines = content.splitlines()

    # Check for non-standard directives
    non_standard = ["crawl-delay", "request-rate", "visit-time", "host"]
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip().lower()
        if ":" in stripped:
            directive = stripped.split(":", 1)[0].strip()
            if directive in non_standard:
                warnings.append(
                    f"Non-standard directive '{directive}' at line {line_num} (may not be supported by all crawlers)"
                )

    # Check for invalid user-agent tokens
    user_agent_pattern = re.compile(r"^[a-zA-Z0-9_-]+$|^\*$")
    for group in parsed_data.get("groups", []):
        for agent in group.get("userAgents", []):
            if agent != "*" and not user_agent_pattern.match(agent):
                warnings.append(f"User-agent '{agent}' contains non-standard characters")

    # Check for empty groups
    for group in parsed_data.get("groups", []):
        if not group.get("rules"):
            warnings.append(f"User-agent group {group.get('userAgents')} has no rules")

    # Warn if using urllib instead of protego
    if not HAS_PROTEGO:
        warnings.append(
            "Using urllib.robotparser instead of protego (install with: pip install protego for full RFC 9309 compliance)"
        )

    return {"errors": errors, "warnings": warnings}


def _display_robots_txt(data: dict[str, Any], show_validation: bool = False):
    """
    Display robots.txt data in human-readable format.

    Args:
        data: Parsed robots.txt data
        show_validation: Whether to show validation results
    """
    click.echo(f"robots.txt: {data['url']}")
    click.echo()

    # Metadata
    metadata = data.get("metadata", {})
    click.echo(f"Status:          {data['status']} OK")

    if last_modified := metadata.get("lastModified"):
        click.echo(f"Last-Modified:   {last_modified}")

    size = metadata.get("size", 0)
    lines = metadata.get("lines", 0)
    click.echo(f"Size:            {size:,} bytes ({lines} lines)")
    click.echo(f"Encoding:        {metadata.get('encoding', 'unknown')}")

    if final_url := metadata.get("finalUrl"):
        click.echo(f"Final URL:       {final_url} (redirected)")

    click.echo()

    # User-agent groups as table
    groups = data.get("groups", [])
    if groups:
        # Create table for rules with auto-width and title bar
        headers = ["User-agent", "Directive", "Path"]
        alignments = ["left", "left", "left"]
        title = f"User-agent Groups ({len(groups)})"

        # Build all rows first for auto-width calculation
        rows = []
        row_colors = []
        separator_indices = []  # Track where to add separators

        for i, group in enumerate(groups):
            agents = ", ".join(group["userAgents"])
            rules = group.get("rules", [])

            # First rule includes user-agent
            if rules:
                first_rule = rules[0]
                directive = first_rule["directive"]
                path = first_rule["path"] or "/"
                directive_color = "green" if directive == "Allow" else "red"
                rows.append([agents, directive, path])
                row_colors.append([None, directive_color, None])

                # Subsequent rules show empty user-agent cell
                for rule in rules[1:]:
                    directive = rule["directive"]
                    path = rule["path"] or "/"
                    directive_color = "green" if directive == "Allow" else "red"
                    rows.append(["", directive, path])
                    row_colors.append([None, directive_color, None])

            # Show crawl-delay and request-rate as special rows
            if crawl_delay := group.get("crawlDelay"):
                rows.append(["", "Crawl-delay", str(crawl_delay)])
                row_colors.append([None, "cyan", None])

            if request_rate := group.get("requestRate"):
                rows.append(["", "Request-rate", request_rate])
                row_colors.append([None, "cyan", None])

            # Track separator position (except for last group)
            if i < len(groups) - 1:
                separator_indices.append(len(rows))

        # Create table with auto-width and title
        icon = get_icon("Robots")
        table = Table(headers, alignments=alignments, title=title, icon=icon)
        table.set_data(rows)
        table.print_header()

        for idx, (row, colors) in enumerate(zip(rows, row_colors, strict=False)):
            table.print_row(row, colors)
            if idx + 1 in separator_indices:
                table.print_separator()

        table.print_footer()
        click.echo()

    # Sitemaps as table
    sitemaps = data.get("sitemaps", [])
    if sitemaps:
        # Single column table for sitemaps with auto-width and title bar
        sitemap_rows = [[sitemap] for sitemap in sitemaps]
        sitemap_icon = get_icon("Sitemaps")
        sitemap_table = Table(
            ["URL"], alignments=["left"], title=f"Sitemaps ({len(sitemaps)})", icon=sitemap_icon
        )
        sitemap_table.set_data(sitemap_rows)
        sitemap_table.print_header()

        for row in sitemap_rows:
            sitemap_table.print_row(row)

        sitemap_table.print_footer()
        click.echo()

    # Validation
    if show_validation:
        validation = data.get("validation", {})
        errors = validation.get("errors", [])
        warnings = validation.get("warnings", [])

        total_issues = len(errors) + len(warnings)

        if errors or warnings:
            # Build validation rows for auto-width with status icons
            val_rows = []
            val_colors = []
            for error in errors:
                val_rows.append([format_status_icon("error"), "Error", error])
                val_colors.append([None, "red", None])
            for warning in warnings:
                val_rows.append([format_status_icon(None), "Warning", warning])
                val_colors.append([None, "yellow", None])

            # Create validation table with auto-width and title bar
            val_icon = get_icon("Validation")
            val_table = Table(
                ["", "Type", "Message"],
                alignments=["left", "left", "left"],
                title=f"Validation ({total_issues} issues)",
                icon=val_icon,
            )
            val_table.set_data(val_rows)
            val_table.print_header()

            for row, colors in zip(val_rows, val_colors, strict=False):
                val_table.print_row(row, colors)

            val_table.print_footer()
        else:
            click.echo(
                click.style(
                    f"{format_status_icon('pass')} Validation: No errors or warnings", fg="green"
                )
            )
        click.echo()
