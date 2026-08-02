"""Pydantic models for API request/response validation."""

from typing import Any

from pydantic import BaseModel, Field


# Base response model
class CommandResponse(BaseModel):
    """Standard response format for all command executions."""

    ok: bool = Field(..., description="Whether the command executed successfully")
    result: Any | None = Field(None, description="Command result data")
    error: str | None = Field(None, description="Error message if ok=False")
    url: str | None = Field(None, description="Current page URL")
    title: str | None = Field(None, description="Current page title")


# Navigation models
class NavigateRequest(BaseModel):
    """Request model for navigating to a URL."""

    url: str = Field(..., description="URL to navigate to", examples=["https://example.com"])
    wait: bool = Field(False, description="Wait for page to finish loading")
    timeout: int = Field(30, description="Timeout in seconds when using wait", ge=1, le=300)


class ScrollRequest(BaseModel):
    """Request model for scroll commands."""

    smooth: bool = Field(False, description="Use smooth scrolling animation")


# Execution models
class EvalRequest(BaseModel):
    """Request model for executing JavaScript code."""

    code: str = Field(..., description="JavaScript code to execute", examples=["document.title"])
    timeout: float = Field(10.0, description="Execution timeout in seconds", ge=0.1, le=300.0)


class ExecRequest(BaseModel):
    """Request model for executing JavaScript from file."""

    file_path: str = Field(..., description="Path to JavaScript file")
    timeout: float = Field(10.0, description="Execution timeout in seconds", ge=0.1, le=300.0)


# Extraction models
class LinksRequest(BaseModel):
    """Request model for extracting links."""

    include_text: bool = Field(True, description="Include link text in output")
    filter_pattern: str | None = Field(None, description="Regex pattern to filter URLs")


class DescribeRequest(BaseModel):
    """Request model for AI page description."""

    language: str | None = Field(None, description="Language for AI output (overrides config)")
    debug: bool = Field(False, description="Show the full prompt instead of calling AI")


class SummarizeRequest(BaseModel):
    """Request model for AI article summarization."""

    language: str | None = Field(None, description="Language for AI output")
    debug: bool = Field(False, description="Show the full prompt instead of calling AI")


class IndexRequest(BaseModel):
    """Request model for indexing page content."""

    save: bool = Field(True, description="Save indexed content to cache")


class AskRequest(BaseModel):
    """Request model for asking questions about indexed content."""

    question: str = Field(..., description="Question to ask about the page")
    debug: bool = Field(False, description="Show the full prompt instead of calling AI")
    no_cache: bool = Field(False, description="Force re-index instead of using cache")


# Interaction models
class ClickRequest(BaseModel):
    """Request model for clicking elements."""

    selector: str = Field(..., description="CSS selector for element to click")
    timeout: float = Field(10.0, description="Timeout in seconds")


class TypeRequest(BaseModel):
    """Request model for typing text."""

    text: str = Field(..., description="Text to type")
    selector: str | None = Field(None, description="CSS selector for input element")


class PasteRequest(BaseModel):
    """Request model for pasting text."""

    text: str = Field(..., description="Text to paste")
    selector: str | None = Field(None, description="CSS selector for input element")


# Inspection models
class ScreenshotRequest(BaseModel):
    """Request model for taking screenshots."""

    output_path: str | None = Field(None, description="Path to save screenshot")
    full_page: bool = Field(False, description="Capture full page")


# Accessibility models
class AxeRequest(BaseModel):
    """Request model for running axe-core accessibility audit."""

    level: str = Field("2aa", description="WCAG conformance level (2a, 2aa, 2aaa, 21a, 21aa, 22aa)")
    tags: str | None = Field(
        None, description="Additional comma-separated tags (e.g., 'best-practice,experimental')"
    )
    include_passes: bool = Field(False, description="Include passing checks in output")
    include_incomplete: bool = Field(
        False, description="Include incomplete checks (require manual review)"
    )
    timeout: float = Field(30.0, description="Execution timeout in seconds", ge=0.1, le=300.0)


class AutocompleteRequest(BaseModel):
    """Request model for checking autocomplete attributes on form fields."""

    confidence_threshold: float = Field(
        0.5,
        description="Minimum confidence (0-1) to consider autocomplete required per WCAG 2.1 SC 1.3.5",
        ge=0.0,
        le=1.0,
    )
    include_hidden: bool = Field(False, description="Include hidden input fields in analysis")
    include_disabled: bool = Field(False, description="Include disabled input fields in analysis")
    timeout: float = Field(30.0, description="Execution timeout in seconds", ge=0.1, le=300.0)
