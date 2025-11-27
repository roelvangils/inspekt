"""Extraction API endpoints for getting page data."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from inspekt.app.api.models import CommandResponse
from inspekt.app.api.dependencies import get_bridge_client

router = APIRouter()


def _process_outline_headings(headings: list) -> list:
    """
    Process headings to:
    1. Insert placeholders for missing heading levels
    2. Mark duplicates (2nd+ occurrence)
    3. Pass through ARIA type info
    """
    processed = []
    seen_texts = {}  # text -> first occurrence (case-insensitive)
    expected_level = 1  # Track expected next level

    for heading in headings:
        level = heading["level"]
        text = heading["text"]
        text_lower = text.lower().strip()

        # Insert missing levels before this heading
        while expected_level < level:
            processed.append({
                "level": expected_level,
                "text": "",
                "type": "missing",
                "is_missing": True,
                "is_duplicate": False
            })
            expected_level += 1

        # Check for duplicates (2nd+ occurrence only, skip empty text)
        is_duplicate = text_lower and text_lower in seen_texts
        if text_lower and not is_duplicate:
            seen_texts[text_lower] = True

        processed.append({
            "level": level,
            "text": text,
            "type": heading.get("type", "native"),
            "is_missing": False,
            "is_duplicate": is_duplicate
        })

        # Update expected level: after H2, expect H2 or H3 next
        expected_level = level + 1

    return processed


@router.get("/info", response_model=CommandResponse)
def get_page_info():
    """
    Get information about the current browser tab.

    This endpoint mirrors the `zen info` CLI command and returns
    basic page information like URL, title, domain, etc.

    Returns:
        Command execution result with page information

    Examples:
        ```bash
        curl http://localhost:8767/api/extraction/info
        ```

        Response:
        ```json
        {
          "ok": true,
          "result": {
            "url": "https://example.com",
            "title": "Example Domain",
            "domain": "example.com",
            "protocol": "https:",
            "readyState": "complete",
            "width": 1280,
            "height": 720
          },
          "url": "https://example.com",
          "title": "Example Domain"
        }
        ```
    """
    client = get_bridge_client()

    code = """
        ({
            url: location.href,
            title: document.title,
            domain: location.hostname,
            protocol: location.protocol,
            readyState: document.readyState,
            width: window.innerWidth,
            height: window.innerHeight
        })
    """

    try:
        result = client.execute(code, timeout=10.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to get page info"))

        return result

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Bridge server connection error: {str(e)}")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting page info: {str(e)}")


@router.get("/links")
def get_page_links(include_text: bool = True):
    """
    Extract all links from the current page.

    This endpoint mirrors the `zen links` CLI command.

    Args:
        include_text: Include link text in the response

    Returns:
        List of links with optional text

    Examples:
        ```bash
        # Get all links with text
        curl http://localhost:8767/api/extraction/links

        # Get just URLs
        curl "http://localhost:8767/api/extraction/links?include_text=false"
        ```
    """
    client = get_bridge_client()

    if include_text:
        code = """
            Array.from(document.querySelectorAll('a[href]')).map(a => ({
                href: a.href,
                text: a.textContent.trim()
            }))
        """
    else:
        code = "Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"

    try:
        result = client.execute(code, timeout=10.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to extract links"))

        return result

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Bridge server connection error: {str(e)}")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting links: {str(e)}")


@router.get("/outline")
def get_page_outline():
    """
    Get the page's heading structure as a hierarchical outline.

    This endpoint mirrors the `inspekt outline --json` CLI command.
    Returns all headings (H1-H6 and ARIA headings) with:
    - Missing level detection (gaps in heading hierarchy)
    - Duplicate detection (identical heading text)
    - ARIA heading identification (role="heading" with aria-level)

    Returns:
        Heading structure with analysis metadata

    Examples:
        ```bash
        curl http://localhost:8767/api/extraction/outline
        ```

        Response:
        ```json
        {
          "ok": true,
          "result": {
            "headings": [
              {"level": 1, "text": "", "type": "missing", "is_missing": true, "is_duplicate": false},
              {"level": 2, "text": "Introduction", "type": "native", "is_missing": false, "is_duplicate": false},
              {"level": 3, "text": "Overview", "type": "native", "is_missing": false, "is_duplicate": false}
            ],
            "count": 2,
            "missing_count": 1,
            "duplicate_count": 0,
            "url": "https://example.com",
            "title": "Example Page"
          }
        }
        ```
    """
    client = get_bridge_client()

    # Load the extract_outline.js script
    script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "extract_outline.js"

    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Script not found: {script_path}")

    try:
        with open(script_path) as f:
            script = f.read()

        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Failed to extract outline"))

        data = result.get("result", {})
        headings = data.get("headings", [])

        # Process headings to detect missing levels and duplicates
        processed_headings = _process_outline_headings(headings)

        # Calculate counts
        total_real = len([h for h in processed_headings if not h.get("is_missing")])
        missing_count = len([h for h in processed_headings if h.get("is_missing")])
        duplicate_count = len([h for h in processed_headings if h.get("is_duplicate")])

        return {
            "ok": True,
            "result": {
                "headings": processed_headings,
                "count": total_real,
                "missing_count": missing_count,
                "duplicate_count": duplicate_count,
                "url": data.get("url", ""),
                "title": data.get("title", "")
            }
        }

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Bridge server connection error: {str(e)}")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Request timeout: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting outline: {str(e)}")
