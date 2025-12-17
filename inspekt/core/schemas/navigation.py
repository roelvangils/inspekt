"""
Navigation command schemas.

Input/output models for navigation commands:
- navigate_to_url
- go_back
- go_forward
- reload_page
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class NavigateParams(BaseModel):
    """Parameters for navigate_to_url command."""

    url: str = Field(
        ...,
        description="The URL to navigate to (must start with http:// or https://)",
    )
    wait_for: Optional[Literal["load", "networkidle"]] = Field(
        default=None,
        description="Wait condition: 'load' (DOMContentLoaded), 'networkidle' (no network activity)",
    )
    timeout: Optional[int] = Field(
        default=30,
        description="Navigation timeout in seconds",
    )


class ReloadParams(BaseModel):
    """Parameters for reload_page command."""

    hard: bool = Field(
        default=False,
        description="Hard reload (bypass cache)",
    )


class NavigateResponse(BaseModel):
    """Response from navigation commands."""

    success: bool = Field(
        ...,
        description="Whether the navigation succeeded",
    )
    url: str = Field(
        default="",
        description="The final URL after navigation (may differ due to redirects)",
    )
    title: str = Field(
        default="",
        description="Page title",
    )
    message: Optional[str] = Field(
        default=None,
        description="Success or error message",
    )
