"""
AI command schemas.

Pydantic models for AI-powered commands:
- summarize: Summarize article content
- describe: Describe page for screen readers
- ask: Answer questions about the page
- do: Execute actions from natural language
- element_describe: AI description of specific element
- element_ask: Ask questions about specific element
"""

from typing import Literal

from pydantic import BaseModel, Field

# === Summarize ===


class SummarizeParams(BaseModel):
    """Parameters for summarize command."""

    format: str = Field(
        default="summary",
        description="Output format: 'summary' (AI summary) or 'full' (full article)",
    )
    language: str | None = Field(
        default=None,
        description="Language for AI output (e.g., 'en', 'nl'). Auto-detected if not specified.",
    )


class SummarizeResponse(BaseModel):
    """Response from summarize command."""

    title: str = Field(description="Article title")
    summary: str = Field(description="AI-generated summary or full article content")
    byline: str | None = Field(default=None, description="Article author/byline")
    cached: bool = Field(default=False, description="Whether result was from cache")


# === Describe ===


class DescribeParams(BaseModel):
    """Parameters for describe command."""

    language: str | None = Field(
        default=None,
        description="Language for AI output. Auto-detected if not specified.",
    )


class DescribeResponse(BaseModel):
    """Response from describe command."""

    description: str = Field(description="AI-generated page description for screen readers")
    cached: bool = Field(default=False, description="Whether result was from cache")


# === Ask ===


class AskParams(BaseModel):
    """Parameters for ask command."""

    question: str = Field(description="Question to ask about the page")


class AskResponse(BaseModel):
    """Response from ask command."""

    answer: str = Field(description="AI-generated answer to the question")
    cached: bool = Field(default=False, description="Whether result was from cache")


# === Do ===


class DoParams(BaseModel):
    """Parameters for do command."""

    instruction: str = Field(description="Natural language instruction for what action to perform")


class DoResponse(BaseModel):
    """Response from do command."""

    success: bool = Field(description="Whether the action was executed")
    element_tag: str | None = Field(default=None, description="Tag of clicked element")
    element_text: str | None = Field(default=None, description="Text content of clicked element")
    confidence: float | None = Field(default=None, description="AI confidence score (0-1)")


# === Markdown Link ===


class MdLinkResponse(BaseModel):
    """Response from md-link command."""

    url: str = Field(description="Page URL")
    title: str = Field(description="Cleaned page title")
    raw_title: str = Field(description="Original page title")
    website_name: str = Field(default="", description="Extracted website name")
    markdown: str = Field(description="Formatted markdown link")


# === Element Describe ===


class ElementDescribeParams(BaseModel):
    """Parameters for element_describe command."""

    source: Literal["inspected", "focused", "selection"] = Field(
        default="inspected",
        description="Element source: 'inspected' ($0 DevTools element), 'focused' (keyboard focus), 'selection' (text selection)",
    )
    language: str | None = Field(
        default=None,
        description="Language for AI output. Auto-detected if not specified.",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug output showing all steps, prompts, and API calls.",
    )


class ElementDescribeResponse(BaseModel):
    """Response from element_describe command."""

    description: str = Field(
        description="AI-generated accessibility-focused description of the element"
    )
    element_type: str = Field(description="HTML tag name of the element")
    accessible_name: str | None = Field(
        default=None, description="Computed accessible name of the element"
    )
    source: str = Field(description="Source type used (inspected, focused, or selection)")


# === Element Ask ===


class ElementAskParams(BaseModel):
    """Parameters for element_ask command."""

    question: str = Field(description="Question to ask about the element")
    source: Literal["inspected", "focused", "selection"] = Field(
        default="inspected",
        description="Element source: 'inspected' ($0 DevTools element), 'focused' (keyboard focus), 'selection' (text selection)",
    )
    language: str | None = Field(
        default=None,
        description="Language for AI output. Auto-detected if not specified.",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug output showing all steps, prompts, and API calls.",
    )
    rich_output: bool = Field(
        default=False,
        description="Collect additional data (HTML, CSS, context) for rich HTML report generation.",
    )
    comprehensive: bool = Field(
        default=False,
        description="Include extended diagnostics in the AI prompt: accessibility audit results, event handlers, and accessibility tree.",
    )


class ElementAskResponse(BaseModel):
    """Response from element_ask command."""

    answer: str = Field(description="AI-generated answer to the question about the element")
    element_type: str = Field(description="HTML tag name of the element")
    source: str = Field(description="Source type used (inspected, focused, or selection)")
    cached: bool = Field(default=False, description="Whether result was from cache")
    rich_data: dict | None = Field(
        default=None,
        description="Additional data for rich HTML report (HTML, CSS, accessibility, page context, element tree). Only populated when rich_output=True.",
    )
