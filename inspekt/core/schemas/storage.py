"""
Storage command schemas.

Input/output models for storage commands:
- get_selected_text
- get_cookies
- set_cookie
"""

from typing import Literal

from pydantic import BaseModel, Field


class GetSelectedTextParams(BaseModel):
    """Parameters for get_selected_text command."""

    format: Literal["text", "html", "markdown"] | None = Field(
        default="text", description="Output format for selected content"
    )


class GetSelectedTextResponse(BaseModel):
    """Response from get_selected_text command."""

    success: bool = Field(..., description="Whether operation succeeded")
    content: str = Field(..., description="Selected text in requested format")
    format: str = Field(..., description="Format of returned content")
    length: int = Field(..., description="Content length in characters")


class CookieInfo(BaseModel):
    """Information about a cookie."""

    name: str = Field(..., description="Cookie name")
    value: str = Field(..., description="Cookie value")
    domain: str = Field(..., description="Cookie domain")
    path: str = Field(..., description="Cookie path")
    secure: bool = Field(..., description="Secure flag")
    httpOnly: bool = Field(..., description="HttpOnly flag")
    sameSite: str | None = Field(default=None, description="SameSite attribute")
    expires: str | None = Field(default=None, description="Expiration date (ISO 8601)")
    session: bool = Field(..., description="Whether it's a session cookie")
    size: int = Field(..., description="Cookie size in bytes")
    party: str | None = Field(default=None, description="First-party or third-party")


class GetCookiesResponse(BaseModel):
    """Response from get_cookies command."""

    success: bool = Field(..., description="Whether operation succeeded")
    cookies: list[CookieInfo] = Field(..., description="List of cookies for current page")
    count: int = Field(..., description="Total number of cookies")


class SetCookieParams(BaseModel):
    """Parameters for set_cookie command."""

    name: str = Field(..., description="Cookie name")
    value: str = Field(..., description="Cookie value")
    domain: str | None = Field(
        default=None, description="Cookie domain (defaults to current domain)"
    )
    path: str | None = Field(default="/", description="Cookie path")
    secure: bool | None = Field(default=False, description="Secure flag")
    httpOnly: bool | None = Field(default=False, description="HttpOnly flag")
    sameSite: Literal["Strict", "Lax", "None"] | None = Field(
        default="Lax", description="SameSite attribute"
    )
    expires: str | None = Field(
        default=None,
        description="Expiration date (ISO 8601 format or seconds from now)",
    )


class SetCookieResponse(BaseModel):
    """Response from set_cookie command."""

    success: bool = Field(..., description="Whether cookie was set successfully")
    message: str | None = Field(default=None, description="Success or error message")
