"""Navigation API endpoints."""

from fastapi import APIRouter, HTTPException, Depends
from inspekt.app.api.models import NavigateRequest, CommandResponse
from inspekt.app.api.dependencies import get_bridge_executor
from inspekt.services.navigation_service import NavigationService

router = APIRouter()


@router.post("/open", response_model=CommandResponse)
def navigate_to_url(request: NavigateRequest):
    """
    Navigate to a URL.

    This endpoint mirrors the `inspekt open` CLI command.

    Args:
        request: Navigation request with URL, wait flag, and timeout

    Returns:
        Command execution result

    Examples:
        ```bash
        curl -X POST http://localhost:8767/api/navigation/open \\
          -H "Content-Type: application/json" \\
          -d '{"url": "https://example.com", "wait": true}'
        ```
    """
    service = NavigationService()
    result = service.navigate_to_url(url=request.url, wait=request.wait, timeout=request.timeout)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Navigation failed"))

    return result


@router.post("/back", response_model=CommandResponse)
def go_back():
    """
    Go back to the previous page in browser history.

    This endpoint mirrors the `inspekt back` CLI command.

    Returns:
        Command execution result

    Examples:
        ```bash
        curl -X POST http://localhost:8767/api/navigation/back
        ```
    """
    service = NavigationService()
    result = service.go_back()

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Go back failed"))

    return result


@router.post("/forward", response_model=CommandResponse)
def go_forward():
    """
    Go forward to the next page in browser history.

    This endpoint mirrors the `inspekt forward` CLI command.

    Returns:
        Command execution result

    Examples:
        ```bash
        curl -X POST http://localhost:8767/api/navigation/forward
        ```
    """
    service = NavigationService()
    result = service.go_forward()

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Go forward failed"))

    return result


@router.post("/reload", response_model=CommandResponse)
def reload_page(hard: bool = False):
    """
    Reload the current page.

    This endpoint mirrors the `inspekt reload` CLI command.

    Args:
        hard: If true, bypass cache (hard reload)

    Returns:
        Command execution result

    Examples:
        ```bash
        # Normal reload
        curl -X POST http://localhost:8767/api/navigation/reload

        # Hard reload
        curl -X POST "http://localhost:8767/api/navigation/reload?hard=true"
        ```
    """
    service = NavigationService()
    result = service.reload_page(hard=hard)

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Reload failed"))

    return result


@router.post("/pageup", response_model=CommandResponse)
def scroll_page_up():
    """
    Scroll up one page (one viewport height).

    This endpoint mirrors the `inspekt pageup` CLI command.

    Returns:
        Command execution result

    Examples:
        ```bash
        curl -X POST http://localhost:8767/api/navigation/pageup
        ```
    """
    service = NavigationService()
    result = service.scroll_page_up()

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Scroll up failed"))

    return result


@router.post("/pagedown", response_model=CommandResponse)
def scroll_page_down():
    """
    Scroll down one page (one viewport height).

    This endpoint mirrors the `inspekt pagedown` CLI command.

    Returns:
        Command execution result

    Examples:
        ```bash
        curl -X POST http://localhost:8767/api/navigation/pagedown
        ```
    """
    service = NavigationService()
    result = service.scroll_page_down()

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Scroll down failed"))

    return result


@router.post("/top", response_model=CommandResponse)
def scroll_to_top():
    """
    Scroll to the top of the page.

    This endpoint mirrors the `inspekt top` CLI command.

    Returns:
        Command execution result

    Examples:
        ```bash
        curl -X POST http://localhost:8767/api/navigation/top
        ```
    """
    service = NavigationService()
    result = service.scroll_to_top()

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Scroll to top failed"))

    return result


@router.post("/bottom", response_model=CommandResponse)
def scroll_to_bottom():
    """
    Scroll to the bottom of the page.

    This endpoint mirrors the `inspekt bottom` CLI command.

    Returns:
        Command execution result

    Examples:
        ```bash
        curl -X POST http://localhost:8767/api/navigation/bottom
        ```
    """
    service = NavigationService()
    result = service.scroll_to_bottom()

    if not result.get("ok"):
        raise HTTPException(status_code=500, detail=result.get("error", "Scroll to bottom failed"))

    return result
