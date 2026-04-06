"""
PDF Report Data Models.

Defines the data structures that represent a complete PDF accessibility report.
These models can be serialized to JSON and used as the data source for
generating HTML reports via Jinja2 templates.

The JSON structure is the "contract" - any tool that produces this structure
can generate the same HTML report.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any
import json


class ReportEncoder(json.JSONEncoder):
    """Custom JSON encoder for report data."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return super().default(obj)


# =============================================================================
# Document Metadata
# =============================================================================


@dataclass
class DocumentMetadata:
    """Basic document metadata."""

    file_path: str
    file_name: str
    file_size: int  # bytes
    page_count: int
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: str | None = None
    creator: str | None = None
    producer: str | None = None
    pdf_version: str | None = None
    language: str | None = None
    creation_date: str | None = None  # ISO format
    modification_date: str | None = None  # ISO format
    is_encrypted: bool = False
    page_dimensions: list[tuple[float, float]] | None = None  # (width, height) in points
    has_ua_marker: bool = False
    conformance_level: str | None = None
    has_suspects_flag: bool = False

    # Enhanced metadata (new fields)
    is_linearized: bool = False  # PDF optimized for fast web viewing
    trapped: str | None = None  # Print trapping: "True", "False", "Unknown"
    xmp_metadata: dict | None = None  # Parsed XMP metadata
    custom_metadata: dict | None = None  # Non-standard docinfo fields
    version_count: int = 1  # Number of incremental save versions


# =============================================================================
# Accessibility Score
# =============================================================================


@dataclass
class CategoryScoreData:
    """Score for a single category."""

    category: str  # Category name
    score: float  # 0-100
    weight: float  # 0-1
    weighted_score: float
    issues_count: int
    critical_count: int = 0
    serious_count: int = 0
    moderate_count: int = 0
    minor_count: int = 0


@dataclass
class AccessibilityScoreData:
    """Overall accessibility score with breakdown."""

    score: float  # 0-100
    grade: str  # A, B, C, D, F
    grade_label: str  # "Excellent", "Good", etc.
    color: str  # Hex color for the grade
    passed_checks: int
    failed_checks: int
    warnings: int
    total_violations: int
    critical_count: int
    serious_count: int
    moderate_count: int
    minor_count: int
    category_scores: list[CategoryScoreData] = field(default_factory=list)
    # Knockout information
    knockout_applied: bool = False
    knockout_reasons: list[str] = field(default_factory=list)
    knockout_cap: float = 100.0
    uncapped_score: float = 0.0


# =============================================================================
# Check Results
# =============================================================================


@dataclass
class CheckResultData:
    """Result of a single accessibility check."""

    check_id: str
    name: str
    description: str
    status: str  # "pass", "fail", "warn", "skip"
    severity: str  # "critical", "serious", "moderate", "minor"
    category: str | None = None
    message: str | None = None
    wcag_criteria: list[str] = field(default_factory=list)
    remediation: str | None = None


@dataclass
class BasicChecksData:
    """Basic PDF accessibility checks."""

    is_tagged: bool
    has_title: bool
    has_language: bool
    has_bookmarks: bool
    is_linearized: bool
    checks: list[CheckResultData] = field(default_factory=list)


# =============================================================================
# Content Audit
# =============================================================================


@dataclass
class ImageAuditData:
    """Audit data for a single image."""

    page: int  # 1-indexed for display
    index: int
    width: float
    height: float
    has_alt_text: bool
    alt_text: str | None = None
    is_decorative: bool = False
    image_type: str | None = None
    status: str = "fail"  # "pass", "fail", "warn"
    issues: list[str] = field(default_factory=list)
    thumbnail_base64: str | None = None

    # AI Image Classification (Phase 1 enhancement)
    image_category: str | None = None  # photograph, illustration, chart_or_graph, etc.
    category_confidence: float = 0.0  # 0-1 confidence score
    classification_method: str | None = None  # clip, vision_ai, heuristic
    category_display_name: str | None = None  # Human-readable category name
    category_needs_warning: bool = False  # Whether category warrants a warning
    alt_guidance: str | None = None  # Category-specific alt-text guidance

    # AI Alt-Text Suggestions (Phase 3 enhancement)
    ai_suggested_alt: str | None = None  # AI-generated alt text suggestion
    ai_provider_used: str | None = None  # Which AI provider generated the suggestion


@dataclass
class TableAuditData:
    """Audit data for a single table."""

    page: int  # 1-indexed
    index: int
    row_count: int
    col_count: int
    has_headers: bool
    header_cells: int
    has_scope: bool
    is_layout_table: bool
    status: str = "fail"
    issues: list[str] = field(default_factory=list)


@dataclass
class FormFieldAuditData:
    """Audit data for a single form field."""

    page: int  # 1-indexed
    index: int
    field_name: str | None
    field_type: str
    has_label: bool
    label_text: str | None = None
    has_tooltip: bool = False
    tooltip_text: str | None = None
    is_required: bool = False
    status: str = "fail"
    issues: list[str] = field(default_factory=list)


@dataclass
class LinkAuditData:
    """Audit data for a single link."""

    page: int  # 1-indexed
    index: int
    link_text: str | None
    destination: str | None
    destination_type: str
    is_internal: bool
    is_descriptive: bool
    status: str = "pass"
    issues: list[str] = field(default_factory=list)


@dataclass
class ContentAuditData:
    """Complete content audit results."""

    # All non-default fields first
    total_images: int = 0
    images_without_alt: int = 0
    images_decorative: int = 0

    total_tables: int = 0
    tables_without_headers: int = 0
    tables_layout: int = 0

    total_form_fields: int = 0
    fields_without_labels: int = 0

    total_links: int = 0
    links_non_descriptive: int = 0
    links_missing_text: int = 0

    # Lists with default factories
    images: list[ImageAuditData] = field(default_factory=list)
    tables: list[TableAuditData] = field(default_factory=list)
    forms: list[FormFieldAuditData] = field(default_factory=list)
    links: list[LinkAuditData] = field(default_factory=list)


# =============================================================================
# Text Layer Analysis
# =============================================================================


@dataclass
class PageTextComparisonData:
    """Text comparison for a single page."""

    page: int  # 1-indexed
    pdf_text: str
    ocr_text: str
    similarity: float  # 0-1
    pdf_char_count: int
    ocr_char_count: int
    has_significant_discrepancy: bool
    is_image_only: bool
    thumbnail_base64: str | None = None  # Small thumbnail for display
    lightbox_base64: str | None = None  # Larger image for lightbox view
    pdf_page_url: str | None = None  # URL with #page=N fragment to open PDF at this page

    # New fields for C+D redesign
    status: str = "complete"  # "complete", "partial", "image_only"
    accessible_percentage: int = 100  # How much content is accessible (0-100)
    missing_char_count: int = 0  # Characters missing from text layer
    missing_excerpts: list[str] = field(default_factory=list)  # Sample excerpts of missing content
    recommendation: str | None = None  # Actionable recommendation text


@dataclass
class TextLayerAnalysisData:
    """Text layer analysis results."""

    ocr_available: bool
    unavailable_reason: str | None = None
    pages_analyzed: int = 0
    pages_with_discrepancy: int = 0
    image_only_pages: int = 0
    overall_similarity: float = 1.0
    is_likely_scanned: bool = False
    page_comparisons: list[PageTextComparisonData] = field(default_factory=list)
    # Sampling information
    is_sampled: bool = False  # True if not all pages were analyzed
    total_document_pages: int = 0  # Total pages in the PDF
    sampling_description: str | None = None  # e.g., "50 of 333 pages (sampled)"


# =============================================================================
# Structure Tree
# =============================================================================


@dataclass
class StructureNodeData:
    """A node in the structure tree."""

    tag_type: str
    text_content: str | None = None
    alt_text: str | None = None
    is_heading: bool = False
    has_issues: bool = False
    children: list["StructureNodeData"] = field(default_factory=list)


@dataclass
class StructureTreeData:
    """Structure tree information."""

    has_structure: bool
    total_nodes: int = 0
    heading_count: int = 0
    figure_count: int = 0
    table_count: int = 0
    list_count: int = 0
    form_count: int = 0
    root: StructureNodeData | None = None
    validation_errors: list[str] = field(default_factory=list)


# =============================================================================
# Remediation Tasks
# =============================================================================


@dataclass
class RemediationTaskData:
    """A single remediation task."""

    task_id: str
    title: str
    description: str
    priority: str  # "critical", "high", "medium", "low"
    category: str
    estimated_effort: str  # "trivial", "small", "medium", "large"
    affected_pages: list[int] = field(default_factory=list)
    pages_summary: str = ""
    wcag_criteria: list[str] = field(default_factory=list)
    notes: str | None = None


@dataclass
class RemediationRoadmapData:
    """Remediation roadmap with prioritized tasks."""

    total_tasks: int
    critical_tasks: int
    high_priority_tasks: int
    medium_priority_tasks: int
    low_priority_tasks: int
    tasks: list[RemediationTaskData] = field(default_factory=list)


# =============================================================================
# Cover Image
# =============================================================================


@dataclass
class CoverImageData:
    """Cover page preview image."""

    image_base64: str | None = None  # Base64-encoded PNG (if embedded)
    asset_id: str | None = None  # Reference to external asset (if not embedded)
    width: int = 0
    height: int = 0


# =============================================================================
# Color Contrast Analysis
# =============================================================================


@dataclass
class ContrastIssueData:
    """A single color contrast issue."""

    page: int  # 1-indexed
    foreground_color: str  # Hex color (e.g., "#333333")
    background_color: str  # Hex color (e.g., "#ffffff")
    contrast_ratio: float  # Actual ratio (e.g., 3.5)
    required_ratio: float  # Required ratio (4.5 for AA normal, 3.0 for AA large)
    level: str  # "AA" or "AAA"
    text_sample: str | None = None  # Sample text at this location
    bbox: tuple[float, float, float, float] | None = None  # Bounding box
    screenshot_base64: str | None = None  # Screenshot of the issue (if embedded)
    asset_id: str | None = None  # Reference to external asset (if not embedded)


@dataclass
class ContrastAnalysisData:
    """Color contrast analysis results."""

    ran_analysis: bool = False
    unavailable_reason: str | None = None
    pages_analyzed: int = 0
    issues_found: int = 0
    aa_failures: int = 0
    aaa_failures: int = 0
    issues: list[ContrastIssueData] = field(default_factory=list)


# =============================================================================
# Issue Screenshots (for veraPDF violations)
# =============================================================================


@dataclass
class IssueScreenshotData:
    """Screenshot for a veraPDF violation."""

    violation_index: int  # Index in the violations list
    rule_id: str
    page: int  # 1-indexed
    screenshot_base64: str | None = None  # Base64-encoded image (if embedded)
    asset_id: str | None = None  # Reference to external asset (if not embedded)
    bbox: tuple[float, float, float, float] | None = None  # Bounding box


# =============================================================================
# Simple PDF Checker (Luxembourg methodology)
# =============================================================================


@dataclass
class SimplePDFCheckData:
    """Result from Simple PDF Checker (Luxembourg methodology)."""

    check_id: str
    name: str
    status: str  # "pass", "fail", "warn", "skip"
    severity: str  # "critical", "serious", "moderate", "minor"
    message: str | None = None
    wcag_sc: str | None = None  # WCAG success criterion
    wcag_level: str | None = None  # A, AA, AAA


@dataclass
class SimpleChecksData:
    """Simple PDF Checker results."""

    ran_checks: bool = False
    is_totally_inaccessible: bool = False
    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    critical_count: int = 0
    serious_count: int = 0
    moderate_count: int = 0
    minor_count: int = 0
    checks: list[SimplePDFCheckData] = field(default_factory=list)


# =============================================================================
# Interactive Preview Data
# =============================================================================


@dataclass
class InteractivePreviewData:
    """Data for interactive tag visualization preview."""

    enabled: bool = False
    pages_rendered: int = 0
    pages_with_overlays: list[int] = field(default_factory=list)


# =============================================================================
# Asset Manifest (for external image files)
# =============================================================================


@dataclass
class AssetReference:
    """Reference to an external asset file."""

    asset_id: str  # Unique identifier (e.g., "cover_001", "contrast_p1_001")
    filename: str  # Relative path from JSON file
    asset_type: str  # "cover", "issue_screenshot", "contrast", "thumbnail", etc.
    file_size: int = 0  # Size in bytes
    width: int | None = None
    height: int | None = None
    checksum: str | None = None  # SHA256 for integrity verification


@dataclass
class AssetManifest:
    """Manifest of external assets for the report."""

    assets_directory: str  # Relative path to assets folder (e.g., "report_assets/")
    total_size: int = 0  # Total size of all assets in bytes
    assets: list[AssetReference] = field(default_factory=list)


# =============================================================================
# VeraPDF Results (optional)
# =============================================================================


@dataclass
class VeraPDFViolationData:
    """A single veraPDF violation."""

    rule_id: str
    clause: str | None
    test_number: int | None
    description: str
    severity: str
    object_type: str | None = None
    context: str | None = None
    page: int | None = None


@dataclass
class VeraPDFResultsData:
    """VeraPDF validation results."""

    ran_validation: bool
    is_compliant: bool = False
    profile: str | None = None
    violations_count: int = 0
    violations: list[VeraPDFViolationData] = field(default_factory=list)


# =============================================================================
# Complete Report
# =============================================================================


# Current schema version - increment when adding new fields
CURRENT_SCHEMA_VERSION = "2.0"


@dataclass
class PDFReportData:
    """
    Complete PDF accessibility report data.

    This is the top-level data structure that can be serialized to JSON
    and used as the data source for HTML report generation.

    Schema version history:
    - 1.0: Initial version with basic checks, content audit, text layer, structure, remediation, verapdf
    - 2.0: Added cover_image, contrast_analysis, issue_screenshots, simple_checks,
           interactive_preview, asset_manifest, and schema_version field
    """

    # Report metadata
    report_version: str = "1.0"
    schema_version: str = CURRENT_SCHEMA_VERSION  # For migration support
    generated_at: str = ""  # ISO format timestamp
    generator: str = "Inspekt PDF Checker"

    # Document info
    metadata: DocumentMetadata | None = None

    # Accessibility score
    score: AccessibilityScoreData | None = None

    # Check results
    basic_checks: BasicChecksData | None = None

    # Simple PDF Checker results (Luxembourg methodology) - NEW in v2.0
    simple_checks: SimpleChecksData | None = None

    # Content audit
    content_audit: ContentAuditData | None = None

    # Text layer analysis
    text_layer: TextLayerAnalysisData | None = None

    # Structure tree
    structure: StructureTreeData | None = None

    # Remediation roadmap
    remediation: RemediationRoadmapData | None = None

    # VeraPDF results (optional)
    verapdf: VeraPDFResultsData | None = None

    # Cover page image - NEW in v2.0
    cover_image: CoverImageData | None = None

    # Color contrast analysis - NEW in v2.0
    contrast_analysis: ContrastAnalysisData | None = None

    # Issue screenshots (for veraPDF violations) - NEW in v2.0
    issue_screenshots: list[IssueScreenshotData] = field(default_factory=list)

    # Interactive preview metadata - NEW in v2.0
    interactive_preview: InteractivePreviewData | None = None

    # Asset manifest for external files - NEW in v2.0
    asset_manifest: AssetManifest | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), cls=ReportEncoder, indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> "PDFReportData":
        """Deserialize from JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PDFReportData":
        """Create from dictionary.

        Automatically migrates older schema versions to current format.
        """
        # Migrate older schemas to current version
        data = migrate_schema(data)

        # Recursively convert nested dicts to dataclasses
        if data.get("metadata"):
            data["metadata"] = DocumentMetadata(**data["metadata"])

        if data.get("score"):
            score_data = data["score"]
            if score_data.get("category_scores"):
                score_data["category_scores"] = [
                    CategoryScoreData(**cs) for cs in score_data["category_scores"]
                ]
            data["score"] = AccessibilityScoreData(**score_data)

        if data.get("basic_checks"):
            bc = data["basic_checks"]
            if bc.get("checks"):
                bc["checks"] = [CheckResultData(**c) for c in bc["checks"]]
            data["basic_checks"] = BasicChecksData(**bc)

        # Simple checks (NEW in v2.0)
        if data.get("simple_checks"):
            sc = data["simple_checks"]
            if sc.get("checks"):
                sc["checks"] = [SimplePDFCheckData(**c) for c in sc["checks"]]
            data["simple_checks"] = SimpleChecksData(**sc)

        if data.get("content_audit"):
            ca = data["content_audit"]
            if ca.get("images"):
                ca["images"] = [ImageAuditData(**img) for img in ca["images"]]
            if ca.get("tables"):
                ca["tables"] = [TableAuditData(**t) for t in ca["tables"]]
            if ca.get("forms"):
                ca["forms"] = [FormFieldAuditData(**f) for f in ca["forms"]]
            if ca.get("links"):
                ca["links"] = [LinkAuditData(**lnk) for lnk in ca["links"]]
            data["content_audit"] = ContentAuditData(**ca)

        if data.get("text_layer"):
            tl = data["text_layer"]
            if tl.get("page_comparisons"):
                tl["page_comparisons"] = [
                    PageTextComparisonData(**pc) for pc in tl["page_comparisons"]
                ]
            data["text_layer"] = TextLayerAnalysisData(**tl)

        if data.get("structure"):
            st = data["structure"]
            if st.get("root"):
                st["root"] = _dict_to_structure_node(st["root"])
            data["structure"] = StructureTreeData(**st)

        if data.get("remediation"):
            rem = data["remediation"]
            if rem.get("tasks"):
                rem["tasks"] = [RemediationTaskData(**t) for t in rem["tasks"]]
            data["remediation"] = RemediationRoadmapData(**rem)

        if data.get("verapdf"):
            vp = data["verapdf"]
            if vp.get("violations"):
                vp["violations"] = [VeraPDFViolationData(**v) for v in vp["violations"]]
            data["verapdf"] = VeraPDFResultsData(**vp)

        # Cover image (NEW in v2.0)
        if data.get("cover_image"):
            data["cover_image"] = CoverImageData(**data["cover_image"])

        # Contrast analysis (NEW in v2.0)
        if data.get("contrast_analysis"):
            ca = data["contrast_analysis"]
            if ca.get("issues"):
                ca["issues"] = [ContrastIssueData(**issue) for issue in ca["issues"]]
            data["contrast_analysis"] = ContrastAnalysisData(**ca)

        # Issue screenshots (NEW in v2.0)
        if data.get("issue_screenshots"):
            data["issue_screenshots"] = [
                IssueScreenshotData(**ss) for ss in data["issue_screenshots"]
            ]

        # Interactive preview (NEW in v2.0)
        if data.get("interactive_preview"):
            data["interactive_preview"] = InteractivePreviewData(**data["interactive_preview"])

        # Asset manifest (NEW in v2.0)
        if data.get("asset_manifest"):
            am = data["asset_manifest"]
            if am.get("assets"):
                am["assets"] = [AssetReference(**a) for a in am["assets"]]
            data["asset_manifest"] = AssetManifest(**am)

        return cls(**data)


def _dict_to_structure_node(data: dict) -> StructureNodeData:
    """Recursively convert dict to StructureNodeData."""
    children = []
    if data.get("children"):
        children = [_dict_to_structure_node(c) for c in data["children"]]
    return StructureNodeData(
        tag_type=data["tag_type"],
        text_content=data.get("text_content"),
        alt_text=data.get("alt_text"),
        is_heading=data.get("is_heading", False),
        has_issues=data.get("has_issues", False),
        children=children,
    )


def migrate_schema(data: dict[str, Any]) -> dict[str, Any]:
    """
    Migrate older JSON schema versions to current version.

    This function ensures backward compatibility by adding default values
    for new fields that were introduced in later schema versions.

    Args:
        data: Dictionary loaded from JSON report

    Returns:
        Migrated dictionary compatible with current schema version
    """
    version = data.get("schema_version", "1.0")

    # Make a copy to avoid mutating the original
    data = data.copy()

    # Migration from 1.0 to 2.0
    if version == "1.0":
        # Add schema_version field
        data["schema_version"] = "2.0"

        # Add new fields with None/default values
        if "cover_image" not in data:
            data["cover_image"] = None

        if "contrast_analysis" not in data:
            data["contrast_analysis"] = None

        if "issue_screenshots" not in data:
            data["issue_screenshots"] = []

        if "simple_checks" not in data:
            data["simple_checks"] = None

        if "interactive_preview" not in data:
            data["interactive_preview"] = None

        if "asset_manifest" not in data:
            data["asset_manifest"] = None

        version = "2.0"

    # Future migrations would go here:
    # if version == "2.0":
    #     # Migrate to 3.0
    #     version = "3.0"

    return data


def get_schema_version(data: dict[str, Any]) -> str:
    """Get the schema version from report data, defaulting to 1.0 if not present."""
    return data.get("schema_version", "1.0")
