"""
Screen reader simulator schemas.

Input/output models for screen reader simulation commands:
- sr_walk: Walk a page with simulated SR output
- sr_compare: Compare announcements across SRs
- sr_announce: Announce a specific element
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SRWalkParams(BaseModel):
    """Parameters for screen reader walk-through."""

    screen_reader: Literal["jaws", "nvda", "voiceover", "all"] = Field(
        default="all",
        description="Screen reader to simulate. Use 'all' for side-by-side comparison.",
    )
    verbosity: Literal["high", "medium", "low"] = Field(
        default="high",
        description="Verbosity level: high (beginner), medium, low (expert)",
    )
    max_elements: int = Field(
        default=500,
        description="Maximum number of elements to walk",
    )
    selector: Optional[str] = Field(
        default=None,
        description="CSS selector to scope the walk to a subtree",
    )
    include_bugs: bool = Field(
        default=True,
        description="Flag known screen reader bugs in the output",
    )


class SRWalkSummary(BaseModel):
    """Summary statistics from a screen reader walk."""

    total_elements: int = Field(..., description="Total elements walked")
    headings: int = Field(default=0, description="Number of headings")
    links: int = Field(default=0, description="Number of links")
    buttons: int = Field(default=0, description="Number of buttons")
    form_fields: int = Field(default=0, description="Number of form fields")
    images: int = Field(default=0, description="Number of images")
    landmarks: int = Field(default=0, description="Number of landmark regions")
    tables: int = Field(default=0, description="Number of tables")
    lists: int = Field(default=0, description="Number of lists")


class SRElementAnnouncement(BaseModel):
    """A single element's screen reader announcement."""

    index: int = Field(..., description="Position in reading order")
    selector: str = Field(..., description="CSS selector for the element")
    tag: str = Field(..., description="HTML tag name")
    role: str = Field(..., description="ARIA role")
    name: str = Field(..., description="Accessible name")
    language: str = Field(default="en", description="Detected language")
    jaws: Optional[str] = Field(default=None, description="JAWS announcement")
    nvda: Optional[str] = Field(default=None, description="NVDA announcement")
    voiceover: Optional[str] = Field(
        default=None, description="VoiceOver announcement"
    )

    # Secondary info
    description: Optional[str] = Field(
        default=None, description="aria-describedby / aria-description content"
    )
    tooltip: Optional[str] = Field(
        default=None,
        description="title attribute (when not already used as accessible name)",
    )
    is_focusable: bool = Field(
        default=False, description="Whether element is keyboard-focusable"
    )
    tab_index: Optional[int] = Field(
        default=None, description="tabindex value (if explicitly set)"
    )

    # Table context (only for table cells)
    table_column_header: Optional[str] = Field(
        default=None, description="Associated column header text"
    )
    table_row_header: Optional[str] = Field(
        default=None, description="Associated row header text"
    )

    # Form context
    value: Optional[str] = Field(
        default=None, description="Current input value"
    )
    placeholder: Optional[str] = Field(
        default=None, description="Placeholder text"
    )

    # Link context
    href: Optional[str] = Field(
        default=None, description="Link destination URL"
    )

    # Secondary announcements (the "after pause" text per SR)
    jaws_secondary: Optional[str] = Field(
        default=None, description="What JAWS says after a pause (description/tooltip)"
    )
    nvda_secondary: Optional[str] = Field(
        default=None, description="What NVDA says after a pause"
    )
    voiceover_secondary: Optional[str] = Field(
        default=None, description="What VoiceOver says as help text"
    )

    # Known bugs
    known_bugs: list[str] = Field(
        default_factory=list,
        description="IDs of known SR bugs that affect this element",
    )


class SRDifference(BaseModel):
    """An element where screen readers announce differently."""

    index: int = Field(..., description="Position in reading order")
    selector: str = Field(..., description="CSS selector")
    role: str = Field(..., description="ARIA role")
    name: str = Field(..., description="Accessible name")
    jaws: Optional[str] = Field(default=None, description="JAWS announcement")
    nvda: Optional[str] = Field(default=None, description="NVDA announcement")
    voiceover: Optional[str] = Field(
        default=None, description="VoiceOver announcement"
    )


class SRWalkResponse(BaseModel):
    """Response from screen reader walk-through."""

    success: bool = Field(..., description="Whether the walk succeeded")
    url: str = Field(default="", description="Page URL")
    title: str = Field(default="", description="Page title")
    element_count: int = Field(default=0, description="Total elements walked")
    announcements: list[SRElementAnnouncement] = Field(
        default_factory=list, description="All element announcements"
    )
    summary: Optional[SRWalkSummary] = Field(
        default=None, description="Summary statistics"
    )
    differences: list[SRDifference] = Field(
        default_factory=list, description="Elements where SRs differ"
    )
    difference_count: int = Field(
        default=0, description="Number of elements with different announcements"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")


class SRAnnounceParams(BaseModel):
    """Parameters for announcing a specific element."""

    selector: Optional[str] = Field(
        default=None,
        description="CSS selector of element to announce. Defaults to focused element.",
    )
    screen_reader: Literal["jaws", "nvda", "voiceover", "all"] = Field(
        default="all",
        description="Screen reader to simulate",
    )
    verbosity: Literal["high", "medium", "low"] = Field(
        default="high",
        description="Verbosity level",
    )


class SRAnnounceResponse(BaseModel):
    """Response from single element announcement."""

    success: bool = Field(..., description="Whether the announcement succeeded")
    selector: Optional[str] = Field(default=None, description="CSS selector used")
    role: Optional[str] = Field(default=None, description="ARIA role")
    name: Optional[str] = Field(default=None, description="Accessible name")
    jaws: Optional[str] = Field(default=None, description="JAWS announcement")
    nvda: Optional[str] = Field(default=None, description="NVDA announcement")
    voiceover: Optional[str] = Field(
        default=None, description="VoiceOver announcement"
    )
    error: Optional[str] = Field(default=None, description="Error message if failed")
