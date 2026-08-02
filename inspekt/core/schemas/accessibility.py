"""
Accessibility command schemas.

Pydantic models for axe-core audits and autocomplete checks.
"""

from typing import Any

from pydantic import BaseModel, Field

# === Axe Audit Schemas ===


class AxeParams(BaseModel):
    """Parameters for running axe-core accessibility audit."""

    level: str = Field(
        "2aa",
        description="WCAG conformance level (2a, 2aa, 2aaa, 21a, 21aa, 22aa)",
    )
    tags: str | None = Field(
        None,
        description="Additional comma-separated tags (e.g., 'best-practice,experimental')",
    )
    include_passes: bool = Field(False, description="Include passing checks in output")
    include_incomplete: bool = Field(
        False, description="Include incomplete checks (require manual review)"
    )
    timeout: float = Field(30.0, description="Execution timeout in seconds", ge=0.1, le=300.0)


class AxeNode(BaseModel):
    """Information about a single failing element."""

    target: list[str] = Field(..., description="CSS selector path to element")
    html: str = Field(..., description="HTML snippet of the element")
    impact: str = Field(..., description="Impact level: critical, serious, moderate, minor")
    failure_summary: str | None = Field(default=None, description="Description of the failure")


class AxeViolation(BaseModel):
    """A single accessibility violation."""

    id: str = Field(..., description="Rule ID (e.g., 'color-contrast')")
    impact: str = Field(..., description="Impact level: critical, serious, moderate, minor")
    description: str = Field(..., description="What the rule checks")
    help: str = Field(..., description="Short description of how to fix")
    help_url: str = Field(..., description="URL to detailed documentation")
    nodes: list[AxeNode] = Field(..., description="List of failing elements")
    node_count: int = Field(..., description="Number of failing elements")


class AxeSummary(BaseModel):
    """Summary statistics from axe audit."""

    violation_count: int = Field(..., description="Total violations")
    pass_count: int = Field(..., description="Total passes")
    incomplete_count: int = Field(..., description="Checks needing manual review")
    critical_count: int = Field(default=0, description="Critical impact violations")
    serious_count: int = Field(default=0, description="Serious impact violations")
    moderate_count: int = Field(default=0, description="Moderate impact violations")
    minor_count: int = Field(default=0, description="Minor impact violations")


class AxeResult(BaseModel):
    """Result from axe accessibility audit."""

    url: str | None = Field(None, description="URL of audited page")
    title: str | None = Field(None, description="Title of audited page")
    timestamp: str | None = Field(None, description="Timestamp of audit")
    axe_version: str | None = Field(None, description="Version of axe-core used")
    config: dict[str, Any] = Field(default_factory=dict, description="Axe configuration used")
    violations: list[AxeViolation] = Field(
        default_factory=list, description="Accessibility violations found"
    )
    passes: list[dict[str, Any]] = Field(
        default_factory=list, description="Passing checks (if requested)"
    )
    incomplete: list[dict[str, Any]] = Field(
        default_factory=list, description="Incomplete checks (if requested)"
    )
    summary: AxeSummary = Field(..., description="Summary statistics")


class AxeResponse(BaseModel):
    """Response from axe accessibility audit."""

    success: bool = Field(..., description="Whether the audit completed successfully")
    result: AxeResult | None = Field(None, description="Audit results")
    url: str | None = Field(None, description="URL of audited page")
    title: str | None = Field(None, description="Title of audited page")
    message: str = Field(..., description="Status message")


# === Autocomplete Check Schemas ===


class AutocompleteParams(BaseModel):
    """Parameters for checking autocomplete attributes on form fields."""

    confidence_threshold: float = Field(
        0.5,
        description="Minimum confidence (0-1) to consider autocomplete required per WCAG 2.1 SC 1.3.5",
        ge=0.0,
        le=1.0,
    )
    include_hidden: bool = Field(False, description="Include hidden input fields in analysis")
    include_disabled: bool = Field(False, description="Include disabled input fields in analysis")


class AutocompleteField(BaseModel):
    """Analysis result for a single form field."""

    selector: str = Field(..., description="CSS selector for the field")
    tag_name: str = Field(..., description="HTML tag name")
    type: str | None = Field(None, description="Input type attribute")
    label: str | None = Field(None, description="Associated label text")
    current_autocomplete: str | None = Field(
        None, description="Current autocomplete attribute value"
    )
    predicted_autocomplete: str | None = Field(
        None, description="Predicted appropriate autocomplete value"
    )
    confidence: float = Field(..., description="Confidence score (0-1)")
    status: str = Field(..., description="Status: correct, incorrect, missing, unknown")
    level: str = Field(..., description="Level: violation, warning, pass")
    message: str = Field(..., description="Human-readable status message")
    wcag_compliant: bool = Field(..., description="Whether field is WCAG compliant")


class AutocompleteSummary(BaseModel):
    """Summary statistics from autocomplete check."""

    total: int = Field(..., description="Total form fields found")
    analyzed: int = Field(..., description="Fields that could be analyzed")
    needs_autocomplete: int = Field(..., description="Fields that need autocomplete per WCAG")
    has_autocomplete: int = Field(..., description="Fields with autocomplete attribute")
    has_correct_autocomplete: int = Field(..., description="Fields with correct autocomplete value")
    violations: int = Field(..., description="Fields with violations")
    warnings: int = Field(..., description="Fields with warnings")


class AutocompleteResult(BaseModel):
    """Result from autocomplete check."""

    summary: AutocompleteSummary = Field(..., description="Summary statistics")
    fields: list[AutocompleteField] = Field(
        default_factory=list, description="Analysis results per field"
    )


class AutocompleteResponse(BaseModel):
    """Response from autocomplete check."""

    success: bool = Field(..., description="Whether the check completed successfully")
    result: AutocompleteResult | None = Field(None, description="Check results")
    url: str | None = Field(None, description="URL of checked page")
    title: str | None = Field(None, description="Title of checked page")
    message: str = Field(..., description="Status message")
