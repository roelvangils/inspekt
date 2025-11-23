"""Robots.txt API endpoint.

This module provides an HTTP API endpoint for fetching and parsing robots.txt files
from the current browser page. It reuses the logic from the CLI robots command.
"""

import re
from typing import Any
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()

# Try to import protego for RFC 9309 compliance
try:
    from protego import Protego
    HAS_PROTEGO = True
except ImportError:
    HAS_PROTEGO = False
    # Fall back to urllib.robotparser
    from urllib.robotparser import RobotFileParser


# ============================================================================
# Response Models
# ============================================================================

class RobotsMetadata(BaseModel):
    """Metadata about the robots.txt file."""
    size: int = Field(..., description="File size in bytes")
    lines: int = Field(..., description="Number of lines")
    encoding: str = Field(..., description="Character encoding")
    contentType: str = Field(..., description="HTTP Content-Type header")
    lastModified: str | None = Field(None, description="Last-Modified header")
    etag: str | None = Field(None, description="ETag header")
    finalUrl: str | None = Field(None, description="Final URL after redirects")


class RobotsRule(BaseModel):
    """A single robots.txt rule (Allow or Disallow)."""
    directive: str = Field(..., description="Directive type (Allow or Disallow)")
    path: str = Field(..., description="Path pattern")
    line: int = Field(..., description="Line number in robots.txt")


class RobotsGroup(BaseModel):
    """A user-agent group with rules."""
    userAgents: list[str] = Field(..., description="List of user-agents")
    rules: list[RobotsRule] = Field(..., description="List of rules for this group")
    crawlDelay: float | None = Field(None, description="Crawl delay in seconds")
    requestRate: str | None = Field(None, description="Request rate limit")


class RobotsComment(BaseModel):
    """A comment from the robots.txt file."""
    line: int = Field(..., description="Line number")
    text: str = Field(..., description="Comment text")


class RobotsValidation(BaseModel):
    """Validation results for robots.txt."""
    errors: list[str] = Field(default_factory=list, description="Syntax errors")
    warnings: list[str] = Field(default_factory=list, description="Warnings and recommendations")


class RobotsResponse(BaseModel):
    """Complete robots.txt response."""
    url: str = Field(..., description="URL of the robots.txt file")
    status: int = Field(..., description="HTTP status code")
    exists: bool = Field(..., description="Whether robots.txt exists")
    metadata: RobotsMetadata | None = Field(None, description="File metadata")
    groups: list[RobotsGroup] = Field(default_factory=list, description="User-agent groups")
    sitemaps: list[str] = Field(default_factory=list, description="Sitemap URLs")
    comments: list[RobotsComment] = Field(default_factory=list, description="Comments")
    raw: str | None = Field(None, description="Raw robots.txt content")
    validation: RobotsValidation | None = Field(None, description="Validation results")
    error: str | None = Field(None, description="Error message if fetch failed")


# ============================================================================
# Helper Functions (from CLI robots.py)
# ============================================================================

def _fetch_robots_txt(robots_url: str) -> dict[str, Any]:
    """
    Fetch robots.txt from the given URL.

    Args:
        robots_url: Full URL to robots.txt

    Returns:
        Dictionary with fetch results including status, metadata, and content
    """
    try:
        response = requests.get(
            robots_url,
            timeout=5,
            headers={"User-Agent": "Inspekt-API-RobotsTxt-Checker"},
            allow_redirects=True
        )

        # Check if robots.txt is too large (RFC 9309: should be < 500KB)
        content_length = response.headers.get("Content-Length")
        if content_length and int(content_length) > 500 * 1024:
            return {
                "url": robots_url,
                "status": 413,
                "exists": False,
                "error": f"robots.txt too large: {int(content_length) / 1024:.1f}KB (max 500KB per RFC 9309)"
            }

        if response.status_code == 200:
            # Calculate actual size
            content = response.text
            size_bytes = len(content.encode('utf-8'))

            # Extract metadata
            metadata = {
                "size": size_bytes,
                "lines": len(content.splitlines()),
                "encoding": response.encoding or "utf-8",
                "contentType": response.headers.get("Content-Type", "unknown")
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
                "metadata": metadata
            }
        else:
            return {
                "url": robots_url,
                "status": response.status_code,
                "exists": False,
                "error": f"HTTP {response.status_code}"
            }

    except requests.Timeout:
        return {
            "url": robots_url,
            "status": 0,
            "exists": False,
            "error": "Request timeout after 5 seconds"
        }
    except requests.ConnectionError as e:
        return {
            "url": robots_url,
            "status": 0,
            "exists": False,
            "error": f"Connection error: {str(e)}"
        }
    except requests.RequestException as e:
        return {
            "url": robots_url,
            "status": 0,
            "exists": False,
            "error": f"Request failed: {str(e)}"
        }


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
    rp = Protego.parse(content)

    # Extract groups (user-agents with their rules)
    groups = []
    current_agents = []
    current_rules = []
    current_crawl_delay = None
    current_request_rate = None

    lines = content.splitlines()
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()

        if not stripped or stripped.startswith('#'):
            continue

        if ':' in stripped:
            directive, _, value = stripped.partition(':')
            directive = directive.strip().lower()
            value = value.strip()

            if directive == 'user-agent':
                # Start new group if we have rules
                if current_agents and current_rules:
                    groups.append({
                        "userAgents": current_agents,
                        "rules": current_rules,
                        **({"crawlDelay": current_crawl_delay} if current_crawl_delay else {}),
                        **({"requestRate": current_request_rate} if current_request_rate else {})
                    })
                    current_rules = []
                    current_crawl_delay = None
                    current_request_rate = None

                current_agents.append(value)

            elif directive in ('allow', 'disallow'):
                current_rules.append({
                    "directive": directive.capitalize(),
                    "path": value,
                    "line": line_num
                })

            elif directive == 'crawl-delay':
                try:
                    current_crawl_delay = float(value)
                except ValueError:
                    pass

            elif directive == 'request-rate':
                current_request_rate = value

    # Add last group
    if current_agents and current_rules:
        groups.append({
            "userAgents": current_agents,
            "rules": current_rules,
            **({"crawlDelay": current_crawl_delay} if current_crawl_delay else {}),
            **({"requestRate": current_request_rate} if current_request_rate else {})
        })

    # Extract sitemaps
    sitemaps = []
    for line in lines:
        if line.strip().lower().startswith('sitemap:'):
            _, _, sitemap_url = line.partition(':')
            sitemaps.append(sitemap_url.strip())

    # Extract comments
    comments = []
    for line_num, line in enumerate(lines, 1):
        if '#' in line:
            # Handle inline comments
            comment_start = line.index('#')
            comment_text = line[comment_start:].strip()
            if comment_text:
                comments.append({
                    "line": line_num,
                    "text": comment_text
                })

    return {
        "groups": groups,
        "sitemaps": sitemaps,
        "comments": comments,
        "raw": content
    }


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

        if stripped.startswith('#'):
            comments.append({
                "line": line_num,
                "text": stripped
            })
            continue

        if ':' in stripped:
            directive, _, value = stripped.partition(':')
            directive = directive.strip().lower()
            value = value.strip()

            if directive == 'user-agent':
                # Start new group if we have rules
                if current_agents and current_rules:
                    groups.append({
                        "userAgents": current_agents,
                        "rules": current_rules
                    })
                    current_rules = []

                current_agents.append(value)

            elif directive in ('allow', 'disallow'):
                current_rules.append({
                    "directive": directive.capitalize(),
                    "path": value,
                    "line": line_num
                })

            elif directive == 'sitemap':
                sitemaps.append(value)

    # Add last group
    if current_agents and current_rules:
        groups.append({
            "userAgents": current_agents,
            "rules": current_rules
        })

    return {
        "groups": groups,
        "sitemaps": sitemaps,
        "comments": comments,
        "raw": content
    }


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
    non_standard = ['crawl-delay', 'request-rate', 'visit-time', 'host']
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip().lower()
        if ':' in stripped:
            directive = stripped.split(':', 1)[0].strip()
            if directive in non_standard:
                warnings.append(f"Non-standard directive '{directive}' at line {line_num} (may not be supported by all crawlers)")

    # Check for invalid user-agent tokens
    user_agent_pattern = re.compile(r'^[a-zA-Z0-9_-]+$|^\*$')
    for group in parsed_data.get("groups", []):
        for agent in group.get("userAgents", []):
            if agent != '*' and not user_agent_pattern.match(agent):
                warnings.append(f"User-agent '{agent}' contains non-standard characters")

    # Check for empty groups
    for group in parsed_data.get("groups", []):
        if not group.get("rules"):
            warnings.append(f"User-agent group {group.get('userAgents')} has no rules")

    # Warn if using urllib instead of protego
    if not HAS_PROTEGO:
        warnings.append("Using urllib.robotparser instead of protego (install with: pip install protego for full RFC 9309 compliance)")

    return {
        "errors": errors,
        "warnings": warnings
    }


# ============================================================================
# API Endpoint
# ============================================================================

@router.get("", response_model=RobotsResponse)
def get_robots_txt(
    validate: bool = Query(False, description="Include validation errors and warnings")
):
    """
    Fetch and parse robots.txt for the current browser page.

    Retrieves the robots.txt file from the current page's origin,
    parses it according to RFC 9309, and returns the rules, sitemaps,
    and metadata in structured JSON format.

    This endpoint gets the current URL from the active browser tab via the
    bridge executor, constructs the robots.txt URL, fetches it, and parses
    the content.

    Args:
        validate: Whether to include validation errors and warnings in response

    Returns:
        Structured robots.txt data including groups, sitemaps, comments, and metadata

    Raises:
        HTTPException: If bridge server is unreachable, browser not connected,
                      or robots.txt fetch fails

    Examples:
        ```bash
        # Get robots.txt for current page
        curl http://localhost:8000/api/robots

        # Get robots.txt with validation
        curl "http://localhost:8000/api/robots?validate=true"
        ```

        Response:
        ```json
        {
          "url": "https://example.com/robots.txt",
          "status": 200,
          "exists": true,
          "metadata": {
            "size": 1234,
            "lines": 45,
            "encoding": "utf-8",
            "contentType": "text/plain"
          },
          "groups": [
            {
              "userAgents": ["*"],
              "rules": [
                {"directive": "Disallow", "path": "/admin", "line": 3}
              ]
            }
          ],
          "sitemaps": ["https://example.com/sitemap.xml"],
          "comments": [],
          "raw": "User-agent: *\\nDisallow: /admin\\n..."
        }
        ```
    """
    # Get current URL from browser
    try:
        from inspekt.client import BridgeClient

        client = BridgeClient()
        result = client.execute("window.location.href", timeout=5.0)

        if not result.get("ok"):
            raise HTTPException(
                status_code=503,
                detail=f"Failed to get current URL from browser: {result.get('error')}"
            )

        current_url = result.get("result")
        if isinstance(current_url, dict):
            current_url = current_url.get("url") or current_url

    except ConnectionError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not connect to bridge server: {str(e)}"
        )
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Timeout getting URL from browser"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting current URL: {str(e)}"
        )

    # Construct robots.txt URL from origin
    try:
        parsed = urlparse(str(current_url))
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid URL from browser: {current_url}"
            )

        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error parsing URL: {str(e)}"
        )

    # Fetch robots.txt
    robots_data = _fetch_robots_txt(robots_url)

    if not robots_data.get("exists"):
        # robots.txt not found - return minimal response
        return RobotsResponse(
            url=robots_url,
            status=robots_data.get("status", 0),
            exists=False,
            error=robots_data.get("error")
        )

    # Parse robots.txt content
    content = robots_data.get("content", "")
    parsed_data = _parse_robots_txt(content, robots_url)

    # Prepare response
    response_data = {
        "url": robots_url,
        "status": robots_data.get("status"),
        "exists": robots_data.get("exists"),
        "metadata": robots_data.get("metadata"),
        **parsed_data
    }

    # Add validation if requested
    if validate:
        validation_results = _validate_robots_txt(content, parsed_data)
        response_data["validation"] = validation_results

    return RobotsResponse(**response_data)
