"""
Interaction command schemas.

Input/output models for interaction commands:
- click_element
- type_text
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ClickElementParams(BaseModel):
    """Parameters for click_element command."""

    selector: str = Field(
        ..., description="CSS selector or '$0' for DevTools-inspected element"
    )
    click_type: Optional[Literal["single", "double", "right"]] = Field(
        default="single", description="Type of click: single, double, or right-click"
    )


class ClickElementResponse(BaseModel):
    """Response from click_element command."""

    success: bool = Field(..., description="Whether click succeeded")
    element_found: bool = Field(default=False, description="Whether the target element was found")
    element_text: Optional[str] = Field(default=None, description="Text content of clicked element")
    message: Optional[str] = Field(default=None, description="Success or error message")


class TypeTextParams(BaseModel):
    """Parameters for type_text command."""

    text: str = Field(..., description="Text to type into the focused element")
    typing_speed: Optional[Literal["instant", "fast", "normal", "slow"]] = Field(
        default="normal", description="Typing speed simulation"
    )
    submit: Optional[bool] = Field(
        default=False, description="Press Enter after typing (submit form)"
    )


class TypeTextResponse(BaseModel):
    """Response from type_text command."""

    success: bool = Field(..., description="Whether typing succeeded")
    characters_typed: int = Field(default=0, description="Number of characters typed")
    message: Optional[str] = Field(default=None, description="Success or error message")
