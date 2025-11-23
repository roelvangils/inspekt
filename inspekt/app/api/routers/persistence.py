"""
Persistence API endpoints - Manage persistent user data.

This module provides HTTP API endpoints for persistent storage:
- POST /api/persistence/hidden - Add element to hidden list
- GET /api/persistence/hidden?domain=example.com - List hidden elements
- DELETE /api/persistence/hidden - Remove hidden element
- DELETE /api/persistence/hidden/all?domain=example.com - Unhide all elements
- GET /api/persistence/stats - Get usage statistics
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from inspekt.services.persistence_service import get_persistence_service

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class AddHiddenElementRequest(BaseModel):
    """Request model for adding hidden element."""

    domain: str = Field(..., description="Domain name (e.g., 'github.com')")
    selector: str = Field(..., description="CSS selector for element")
    reason: str = Field("", description="Optional reason for hiding")

    model_config = {
        "json_schema_extra": {
            "example": {
                "domain": "github.com",
                "selector": ".js-cookie-banner",
                "reason": "Cookie consent banner",
            }
        }
    }


class RemoveHiddenElementRequest(BaseModel):
    """Request model for removing hidden element."""

    domain: str = Field(..., description="Domain name")
    selector: str = Field(..., description="CSS selector")

    model_config = {
        "json_schema_extra": {
            "example": {"domain": "github.com", "selector": ".js-cookie-banner"}
        }
    }


class HiddenElementResponse(BaseModel):
    """Response model for hidden element operations."""

    ok: bool = Field(..., description="Success flag")
    domain: str | None = Field(None, description="Domain")
    selector: str | None = Field(None, description="Selector")
    reason: str | None = Field(None, description="Reason")
    deleted: bool | None = Field(None, description="Whether element was deleted")
    error: str | None = Field(None, description="Error message")


class HiddenElementsListResponse(BaseModel):
    """Response model for listing hidden elements."""

    ok: bool = Field(..., description="Success flag")
    domain: str = Field(..., description="Domain queried")
    count: int = Field(..., description="Number of elements")
    elements: list[dict] = Field(..., description="Hidden elements")
    error: str | None = Field(None, description="Error message")


class UnhideAllResponse(BaseModel):
    """Response model for unhiding all elements."""

    ok: bool = Field(..., description="Success flag")
    domain: str = Field(..., description="Domain")
    count: int = Field(..., description="Number of elements removed")
    error: str | None = Field(None, description="Error message")


class StatsResponse(BaseModel):
    """Response model for statistics."""

    ok: bool = Field(..., description="Success flag")
    total_elements: int = Field(..., description="Total hidden elements")
    total_domains: int = Field(..., description="Total domains with hidden elements")
    top_domains: list[dict] = Field(..., description="Top domains by hidden elements")
    database_path: str = Field(..., description="Database file path")
    error: str | None = Field(None, description="Error message")


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/hidden", response_model=HiddenElementResponse)
def add_hidden_element(request: AddHiddenElementRequest):
    """
    Add an element to the persistent hidden list.

    The element will be automatically hidden on future page loads.

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/persistence/hidden \\
          -H "Content-Type: application/json" \\
          -d '{
            "domain": "github.com",
            "selector": ".js-cookie-banner",
            "reason": "Cookie banner"
          }'
        ```

    Returns:
        HiddenElementResponse with success status and element details
    """
    try:
        service = get_persistence_service()
        result = service.add_hidden_element(
            domain=request.domain, selector=request.selector, reason=request.reason
        )
        return HiddenElementResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hidden", response_model=HiddenElementsListResponse)
def list_hidden_elements(domain: str = Query(..., description="Domain to query")):
    """
    List all hidden elements for a domain.

    Examples:
        ```bash
        curl "http://localhost:8000/api/persistence/hidden?domain=github.com"
        ```

    Args:
        domain: Domain name to query (e.g., 'github.com')

    Returns:
        HiddenElementsListResponse with list of hidden elements
    """
    try:
        service = get_persistence_service()
        elements = service.get_hidden_elements(domain)

        return HiddenElementsListResponse(
            ok=True, domain=domain, count=len(elements), elements=elements, error=None
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/hidden", response_model=HiddenElementResponse)
def remove_hidden_element(request: RemoveHiddenElementRequest):
    """
    Remove an element from the persistent hidden list.

    Examples:
        ```bash
        curl -X DELETE http://localhost:8000/api/persistence/hidden \\
          -H "Content-Type: application/json" \\
          -d '{
            "domain": "github.com",
            "selector": ".js-cookie-banner"
          }'
        ```

    Returns:
        HiddenElementResponse with success status
    """
    try:
        service = get_persistence_service()
        result = service.remove_hidden_element(
            domain=request.domain, selector=request.selector
        )
        return HiddenElementResponse(**result)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/hidden/all", response_model=UnhideAllResponse)
def remove_all_hidden_elements(
    domain: str = Query(..., description="Domain to clear")
):
    """
    Remove all hidden elements for a domain (unhide all).

    Examples:
        ```bash
        curl -X DELETE "http://localhost:8000/api/persistence/hidden/all?domain=github.com"
        ```

    Args:
        domain: Domain name to clear (e.g., 'github.com')

    Returns:
        UnhideAllResponse with count of elements removed
    """
    try:
        service = get_persistence_service()
        result = service.remove_all_hidden_elements(domain)
        return UnhideAllResponse(**result, error=None)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=StatsResponse)
def get_stats():
    """
    Get database statistics.

    Examples:
        ```bash
        curl "http://localhost:8000/api/persistence/stats"
        ```

    Returns:
        StatsResponse with database statistics
    """
    try:
        service = get_persistence_service()
        result = service.get_stats()
        return StatsResponse(**result, error=None)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
