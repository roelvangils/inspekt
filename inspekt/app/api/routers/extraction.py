"""Extraction API endpoints for getting page data."""

from fastapi import APIRouter, HTTPException
from inspekt.app.api.models import CommandResponse
from inspekt.app.api.dependencies import get_bridge_client

router = APIRouter()


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
