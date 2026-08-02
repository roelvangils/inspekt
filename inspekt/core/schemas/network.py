"""
Network inspection schemas.

Pydantic models for network-related commands:
- get_network_requests: Get network requests via Performance API
- get_har: Get HAR data from DevTools
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

# === Get Network Requests ===


class GetNetworkRequestsParams(BaseModel):
    """Parameters for get_network_requests tool."""

    resource_type: str | None = Field(
        default=None,
        description="Filter by resource type: script, stylesheet, fetch, xhr, image, font, document, svg, video, audio",
    )
    external_only: bool | None = Field(
        default=False,
        description="Only return requests to external domains",
    )
    sort_by: Literal["start", "time", "size", "name", "type"] | None = Field(
        default="start",
        description="Sort field: start (chronological), time (slowest first), size (largest first), name, type",
    )
    limit: int | None = Field(
        default=None,
        description="Maximum number of entries to return",
    )


class GetNetworkRequestsResponse(BaseModel):
    """Response from get_network_requests tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    url: str = Field(default="", description="Page URL")
    timestamp: str = Field(default="", description="Timestamp of the capture (ISO 8601)")
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of network request entries",
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics",
    )
    message: str | None = Field(default=None, description="Success or error message")


# === Get HAR ===


class GetHARParams(BaseModel):
    """Parameters for get_har tool."""

    resource_type: str | None = Field(
        default=None,
        description="Filter by resource type: script, stylesheet, fetch, image, font, document",
    )
    errors_only: bool | None = Field(
        default=False,
        description="Only return failed requests (4xx/5xx status codes)",
    )
    sort_by: Literal["start", "time", "size", "name", "type", "status"] | None = Field(
        default="start",
        description="Sort field",
    )
    limit: int | None = Field(
        default=None,
        description="Maximum number of entries to return",
    )


class GetHARResponse(BaseModel):
    """Response from get_har tool."""

    success: bool = Field(..., description="Whether the operation succeeded")
    source: str = Field(default="devtools", description="Data source (devtools)")
    url: str = Field(default="", description="Page URL")
    timestamp: str = Field(default="", description="Timestamp of the capture (ISO 8601)")
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of HAR entries with status codes and headers",
    )
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description="Summary statistics including status breakdown",
    )
    message: str | None = Field(default=None, description="Success or error message")
