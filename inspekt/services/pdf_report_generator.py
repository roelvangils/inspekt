"""
PDF Report Data Generator.

Generates PDFReportData from PDF check results. This is the bridge between
the raw check results and the structured report data that can be serialized
to JSON or rendered to HTML.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from inspekt.services.pdf_report_data import (
    CURRENT_SCHEMA_VERSION,
    AccessibilityScoreData,
    AssetManifest,
    AssetReference,
    BasicChecksData,
    CategoryScoreData,
    CheckResultData,
    ContentAuditData,
    ContrastAnalysisData,
    ContrastIssueData,
    # New in v2.0
    CoverImageData,
    DocumentMetadata,
    FormFieldAuditData,
    ImageAuditData,
    InteractivePreviewData,
    IssueScreenshotData,
    LinkAuditData,
    PageTextComparisonData,
    PDFReportData,
    RemediationRoadmapData,
    RemediationTaskData,
    SimpleChecksData,
    SimplePDFCheckData,
    StructureNodeData,
    StructureTreeData,
    TableAuditData,
    TextLayerAnalysisData,
    VeraPDFResultsData,
    VeraPDFViolationData,
)

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import PDFFullResult

logger = logging.getLogger(__name__)


def generate_report_data(
    pdf_path: Path | str,
    result: PDFFullResult,
    config: dict | None = None,
) -> PDFReportData:
    """
    Generate complete report data from PDF check results.

    Args:
        pdf_path: Path to the PDF file
        result: PDFFullResult from the checker
        config: Optional configuration dict with the following options:
            - show-content-audit (bool, default True): Include content audit section
            - show-text-analysis (bool, default True): Include text layer analysis
            - show-structure (bool, default True): Include structure tree
            - show-remediation (bool, default True): Include remediation roadmap
            - show-cover-page (bool, default True): Include cover page image
            - check-contrast (bool, default True): Include contrast analysis
            - interactive-preview (bool, default True): Include interactive preview metadata
            - show-issue-screenshots (bool, default True): Include violation screenshots

    Returns:
        PDFReportData ready for JSON serialization or HTML rendering
    """
    config = config or {}
    pdf_path = Path(pdf_path)

    report = PDFReportData(
        report_version="1.0",
        schema_version=CURRENT_SCHEMA_VERSION,
        generated_at=datetime.now().isoformat(),
        generator="Inspekt PDF Checker",
    )

    # Generate each section
    report.metadata = _generate_metadata(pdf_path, result)
    report.score = _generate_score_data(result)
    report.basic_checks = _generate_basic_checks(result)

    # Simple checks (NEW in v2.0) - if available from result
    if result.simple:
        report.simple_checks = _generate_simple_checks(result)

    # Optional sections based on config
    if config.get("show-content-audit", True):
        report.content_audit = _generate_content_audit(pdf_path, config)

    if config.get("show-text-analysis", True):
        report.text_layer = _generate_text_layer_analysis(pdf_path, config)

    if config.get("show-structure", True):
        report.structure = _generate_structure_tree(pdf_path)

    if config.get("show-remediation", True):
        report.remediation = _generate_remediation_roadmap(result, pdf_path)

    if result.verapdf:
        report.verapdf = _generate_verapdf_results(result)

    # NEW in v2.0: Cover image
    if config.get("show-cover-page", True):
        report.cover_image = _generate_cover_image(pdf_path, config)

    # NEW in v2.0: Contrast analysis
    if config.get("check-contrast", True):
        report.contrast_analysis = _generate_contrast_analysis(pdf_path, config)

    # NEW in v2.0: Issue screenshots (for veraPDF violations)
    if config.get("show-issue-screenshots", True) and result.verapdf:
        report.issue_screenshots = _generate_issue_screenshots(pdf_path, result, config)

    # NEW in v2.0: Interactive preview metadata
    if config.get("interactive-preview", True):
        report.interactive_preview = _generate_interactive_preview(pdf_path, config)

    return report


def _generate_metadata(pdf_path: Path, result: PDFFullResult) -> DocumentMetadata:
    """Generate document metadata section."""
    from inspekt.services.pdf_checker import extract_enhanced_metadata

    meta = extract_enhanced_metadata(pdf_path)

    if meta:
        return DocumentMetadata(
            file_path=str(pdf_path),
            file_name=pdf_path.name,
            file_size=meta.file_size,
            page_count=meta.page_count,
            title=meta.title,
            author=meta.author,
            subject=meta.subject,
            keywords=meta.keywords,
            creator=meta.creator,
            producer=meta.producer,
            pdf_version=meta.pdf_version,
            language=meta.language,
            creation_date=meta.creation_date,
            modification_date=meta.modification_date,
            is_encrypted=meta.is_encrypted,
            page_dimensions=meta.page_dimensions,
            has_ua_marker=meta.has_ua_marker,
            conformance_level=meta.conformance_level,
            has_suspects_flag=meta.has_suspects_flag,
            # Enhanced metadata
            is_linearized=meta.is_linearized,
            trapped=meta.trapped,
            xmp_metadata=meta.xmp_metadata,
            custom_metadata=meta.custom_metadata,
            version_count=meta.version_count,
        )
    else:
        # Fallback to basic info
        return DocumentMetadata(
            file_path=str(pdf_path),
            file_name=pdf_path.name,
            file_size=pdf_path.stat().st_size if pdf_path.exists() else 0,
            page_count=result.basic.page_count if result.basic else 0,
            title=result.basic.title if result.basic else None,
            author=result.basic.author if result.basic else None,
            language=result.basic.language if result.basic else None,
        )


def _generate_score_data(result: PDFFullResult) -> AccessibilityScoreData:
    """Generate accessibility score data."""
    from inspekt.services.pdf_scoring import calculate_accessibility_score

    score = calculate_accessibility_score(result)

    category_scores = []
    for cat, cs in score.category_scores.items():
        category_scores.append(CategoryScoreData(
            category=cat.value,
            score=cs.score,
            weight=cs.weight,
            weighted_score=cs.weighted_score,
            issues_count=cs.issues_count,
            critical_count=cs.critical_count,
            serious_count=cs.serious_count,
            moderate_count=cs.moderate_count,
            minor_count=cs.minor_count,
        ))

    return AccessibilityScoreData(
        score=score.score,
        grade=score.grade.value,
        grade_label=score.grade.label,
        color=score.color,
        passed_checks=score.passed_checks,
        failed_checks=score.failed_checks,
        warnings=score.warnings,
        total_violations=score.total_violations,
        critical_count=score.critical_count,
        serious_count=score.serious_count,
        moderate_count=score.moderate_count,
        minor_count=score.minor_count,
        category_scores=category_scores,
        knockout_applied=score.knockout_applied,
        knockout_reasons=score.knockout_reasons,
        knockout_cap=score.knockout_cap,
        uncapped_score=score.uncapped_score,
    )


def _generate_basic_checks(result: PDFFullResult) -> BasicChecksData:
    """Generate basic checks data."""
    basic = result.basic

    # Build lookup dict for check statuses
    check_status = {c.check_id: c.status for c in basic.checks}

    # Derive boolean flags from check results
    is_tagged = check_status.get("tagged") == "pass"
    has_title = check_status.get("title") == "pass"
    has_language = check_status.get("language") == "pass"
    has_bookmarks = check_status.get("bookmarks") == "pass"
    is_linearized = check_status.get("linearized") == "pass"

    checks = []
    for check in basic.checks:
        # Build WCAG criteria list from wcag_sc if available
        wcag_criteria = []
        if check.wcag_sc:
            wcag_criteria.append(check.wcag_sc)

        checks.append(CheckResultData(
            check_id=check.check_id,
            name=check.name,
            description=check.message,  # PDFCheckResult uses 'message' not 'description'
            status=check.status,
            severity=check.severity,
            category=getattr(check, "category", None),
            message=check.message,
            wcag_criteria=wcag_criteria,
            remediation=None,  # Not available in PDFCheckResult
        ))

    return BasicChecksData(
        is_tagged=is_tagged,
        has_title=has_title,
        has_language=has_language,
        has_bookmarks=has_bookmarks,
        is_linearized=is_linearized,
        checks=checks,
    )


def _generate_content_audit(pdf_path: Path, config: dict) -> ContentAuditData | None:
    """Generate content audit data with optional thumbnails."""
    try:
        from inspekt.services.pdf_content_auditor import PDFContentAuditor

        include_thumbnails = config.get("show-image-thumbnails", True)

        with PDFContentAuditor(pdf_path) as auditor:
            result = auditor.audit()

            # Extract thumbnails if enabled
            if include_thumbnails and result.images:
                for img in result.images[:20]:
                    thumbnail = auditor.get_image_thumbnail(
                        img.page,
                        img.index,
                        max_size=100,
                    )
                    img.thumbnail_base64 = thumbnail

        # Convert to data classes
        images = [
            ImageAuditData(
                page=img.display_page,
                index=img.index,
                width=img.width,
                height=img.height,
                has_alt_text=img.has_alt_text,
                alt_text=img.alt_text,
                is_decorative=img.is_decorative,
                image_type=img.image_type,
                status=img.status,
                issues=img.issues,
                thumbnail_base64=img.thumbnail_base64,
            )
            for img in result.images[:20]
        ]

        tables = [
            TableAuditData(
                page=tbl.display_page,
                index=tbl.index,
                row_count=tbl.row_count,
                col_count=tbl.col_count,
                has_headers=tbl.has_headers,
                header_cells=tbl.header_cells,
                has_scope=tbl.has_scope,
                is_layout_table=tbl.is_layout_table,
                status=tbl.status,
                issues=tbl.issues,
            )
            for tbl in result.tables[:20]
        ]

        forms = [
            FormFieldAuditData(
                page=f.display_page,
                index=f.index,
                field_name=f.field_name,
                field_type=f.field_type,
                has_label=f.has_label,
                label_text=f.label_text,
                has_tooltip=f.has_tooltip,
                tooltip_text=f.tooltip_text,
                is_required=f.is_required,
                status=f.status,
                issues=f.issues,
            )
            for f in result.forms[:20]
        ]

        links = [
            LinkAuditData(
                page=lnk.display_page,
                index=lnk.index,
                link_text=lnk.link_text,
                destination=lnk.display_destination,
                destination_type=lnk.destination_type,
                is_internal=lnk.is_internal,
                is_descriptive=lnk.is_descriptive,
                status=lnk.status,
                issues=lnk.issues,
            )
            for lnk in result.links[:20]
        ]

        return ContentAuditData(
            total_images=result.total_images,
            images_without_alt=result.images_without_alt,
            images_decorative=result.images_decorative,
            images=images,
            total_tables=result.total_tables,
            tables_without_headers=result.tables_without_headers,
            tables_layout=result.tables_layout,
            tables=tables,
            total_form_fields=result.total_form_fields,
            fields_without_labels=result.fields_without_labels,
            forms=forms,
            total_links=result.total_links,
            links_non_descriptive=result.links_non_descriptive,
            links_missing_text=result.links_missing_text,
            links=links,
        )

    except Exception as e:
        logger.warning(f"Failed to generate content audit: {e}")
        return None


def _extract_missing_excerpts(
    pdf_text: str,
    ocr_text: str,
    max_excerpts: int = 3,
    min_excerpt_len: int = 20,
    max_excerpt_len: int = 80,
) -> list[str]:
    """
    Extract excerpts of text that appear in OCR but not in PDF text layer.

    Uses difflib to find segments that are insertions (in OCR but not PDF).
    Returns up to max_excerpts meaningful excerpts.
    """
    from difflib import SequenceMatcher

    if not ocr_text or not pdf_text:
        # If PDF is empty but OCR has text, return start of OCR text
        if ocr_text and not pdf_text:
            excerpt = ocr_text[:max_excerpt_len].strip()
            if len(ocr_text) > max_excerpt_len:
                excerpt += "…"
            return [excerpt] if excerpt else []
        return []

    # Normalize for comparison
    pdf_normalized = pdf_text.lower()
    ocr_normalized = ocr_text.lower()

    # Split into words for more meaningful comparison
    pdf_words = pdf_normalized.split()
    ocr_words = ocr_normalized.split()

    if not ocr_words:
        return []

    # Use SequenceMatcher to find differences
    matcher = SequenceMatcher(None, pdf_words, ocr_words)
    excerpts = []

    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if len(excerpts) >= max_excerpts:
            break

        # Look for insertions (text in OCR but not in PDF)
        if tag in ("insert", "replace"):
            missing_words = ocr_words[j1:j2]
            if len(missing_words) >= 3:  # At least 3 words
                excerpt = " ".join(missing_words)
                if len(excerpt) >= min_excerpt_len:
                    if len(excerpt) > max_excerpt_len:
                        excerpt = excerpt[:max_excerpt_len].rsplit(" ", 1)[0] + "…"
                    excerpts.append(excerpt)

    return excerpts


def _generate_text_layer_analysis(pdf_path: Path, config: dict) -> TextLayerAnalysisData:
    """Generate text layer analysis data."""
    from inspekt.services.pdf_ocr import analyze_text_discrepancy

    result = analyze_text_discrepancy(pdf_path, config)

    if not result.ocr_available:
        return TextLayerAnalysisData(
            ocr_available=False,
            unavailable_reason=result.unavailable_reason,
        )

    # Generate file:// URL for PDF page links
    # Note: page_num is 0-indexed, PDF viewers expect 1-indexed in #page=N
    pdf_file_url_base = f"file://{pdf_path.absolute()}"

    page_comparisons = []
    for pc in result.page_comparisons:
        # Calculate accessible percentage and missing chars FIRST
        # (we need these to determine status)
        if pc.ocr_char_count > 0:
            accessible_percentage = int((pc.pdf_char_count / pc.ocr_char_count) * 100)
            accessible_percentage = min(100, max(0, accessible_percentage))  # Clamp 0-100
        else:
            accessible_percentage = 100 if pc.pdf_char_count == 0 else 100

        missing_char_count = max(0, pc.ocr_char_count - pc.pdf_char_count)

        # Calculate what percentage of visible content is missing
        if pc.ocr_char_count > 0:
            missing_percentage = (missing_char_count / pc.ocr_char_count) * 100
        else:
            missing_percentage = 0

        # Compute status and recommendation based on ACTUAL missing content
        # (not just similarity differences which could be OCR errors)
        if pc.is_image_only:
            status = "image_only"
            recommendation = "This page has no text layer. Re-scan with OCR enabled or recreate from source document."
        elif missing_percentage > 10:
            # More than 10% of visible content is missing from text layer
            status = "partial"
            recommendation = "Re-run OCR with manual review, or regenerate PDF from source with proper text export."
        elif pc.pdf_char_count == 0 and pc.ocr_char_count > 20:
            # No PDF text but OCR found significant content
            status = "image_only"
            recommendation = "This page has no text layer. Re-scan with OCR enabled or recreate from source document."
        else:
            # PDF has same or more content than OCR detected - text layer is complete
            status = "complete"
            recommendation = None

        # Extract missing excerpts by finding text in OCR but not in PDF
        # Only do this for pages with actual missing content
        if status != "complete":
            missing_excerpts = _extract_missing_excerpts(pc.pdf_text, pc.ocr_text, max_excerpts=3)
        else:
            missing_excerpts = []

        page_comparisons.append(PageTextComparisonData(
            page=pc.page_num + 1,  # 1-indexed for display
            pdf_text=pc.pdf_text,
            ocr_text=pc.ocr_text,
            similarity=pc.similarity,
            pdf_char_count=pc.pdf_char_count,
            ocr_char_count=pc.ocr_char_count,
            has_significant_discrepancy=pc.has_significant_discrepancy,
            is_image_only=pc.is_image_only,
            thumbnail_base64=pc.thumbnail_base64,
            lightbox_base64=pc.lightbox_base64,
            pdf_page_url=f"{pdf_file_url_base}#page={pc.page_num + 1}",
            status=status,
            accessible_percentage=accessible_percentage,
            missing_char_count=missing_char_count,
            missing_excerpts=missing_excerpts,
            recommendation=recommendation,
        ))

    return TextLayerAnalysisData(
        ocr_available=True,
        pages_analyzed=result.pages_analyzed,
        pages_with_discrepancy=result.pages_with_discrepancy,
        image_only_pages=result.image_only_pages,
        overall_similarity=result.overall_similarity,
        is_likely_scanned=result.is_likely_scanned,
        page_comparisons=page_comparisons,
        is_sampled=result.is_sampled,
        total_document_pages=result.total_document_pages,
        sampling_description=result.sampling_description,
    )


def _generate_structure_tree(pdf_path: Path) -> StructureTreeData:
    """Generate structure tree data."""
    try:
        from inspekt.services.pdf_structure_extractor import PDFStructureExtractor

        with PDFStructureExtractor(pdf_path) as extractor:
            result = extractor.extract()

        if not result.has_structure:
            return StructureTreeData(has_structure=False)

        # Convert structure nodes recursively
        root_node = None
        if result.root:
            root_node = _convert_structure_node(result.root)

        stats = result.statistics

        return StructureTreeData(
            has_structure=True,
            total_nodes=stats.total_nodes,
            heading_count=stats.heading_count,
            figure_count=stats.figure_count,
            table_count=stats.table_count,
            list_count=stats.list_count,
            form_count=stats.form_count,
            root=root_node,
            validation_errors=result.validation_errors if hasattr(result, 'validation_errors') else [],
        )

    except Exception as e:
        logger.warning(f"Failed to generate structure tree: {e}")
        return StructureTreeData(has_structure=False)


def _convert_structure_node(node, depth: int = 0) -> StructureNodeData | None:
    """Recursively convert structure node to data class."""
    if depth > 10:
        return None

    children = []
    if node.children:
        for child in node.children[:20]:  # Limit children
            child_node = _convert_structure_node(child, depth + 1)
            if child_node:
                children.append(child_node)

    return StructureNodeData(
        tag_type=node.tag_type,
        text_content=node.text_content[:50] if node.text_content else None,
        alt_text=node.alt_text[:30] if node.alt_text else None,
        is_heading=node.is_heading,
        has_issues=node.has_issues,
        children=children,
    )


def _generate_remediation_roadmap(
    result: PDFFullResult,
    pdf_path: Path,
) -> RemediationRoadmapData | None:
    """Generate remediation roadmap data."""
    try:
        from inspekt.services.remediation_planner import generate_remediation_plan

        # generate_remediation_plan expects (result, structure, content_audit)
        # not (result, pdf_path) - pass None for optional params
        plan = generate_remediation_plan(result, structure=None, content_audit=None)

        if not plan or not plan.tasks:
            return None

        tasks = [
            RemediationTaskData(
                task_id=task.task_id,
                title=task.title,
                description=task.description,
                # Convert enums to string values for JSON serialization
                priority=task.priority.value if hasattr(task.priority, 'value') else str(task.priority),
                category=task.category,
                estimated_effort=task.effort.value if hasattr(task.effort, 'value') else str(task.effort),
                affected_pages=task.affected_pages,
                pages_summary=task.pages_summary,
                wcag_criteria=task.wcag_criteria,
                notes=task.notes,
            )
            for task in plan.tasks[:30]  # Limit tasks
        ]

        return RemediationRoadmapData(
            total_tasks=plan.task_count,  # property that returns len(tasks)
            critical_tasks=plan.critical_count,
            high_priority_tasks=plan.high_count,
            medium_priority_tasks=plan.medium_count,
            low_priority_tasks=plan.low_count,
            tasks=tasks,
        )

    except Exception as e:
        logger.warning(f"Failed to generate remediation roadmap: {e}")
        return None


def _generate_verapdf_results(result: PDFFullResult) -> VeraPDFResultsData | None:
    """Generate veraPDF results data."""
    if not result.verapdf:
        return None

    vp = result.verapdf

    violations = [
        VeraPDFViolationData(
            rule_id=v.rule_id,
            clause=v.clause,
            test_number=v.test_number,
            description=v.description,
            severity=v.severity,
            object_type=getattr(v, "object_type", None),
            context=getattr(v, "context", None),
            page=getattr(v, "page", None),
        )
        for v in vp.violations[:100]  # Limit violations
    ]

    return VeraPDFResultsData(
        ran_validation=True,
        is_compliant=vp.compliant,
        profile=vp.profile,
        violations_count=len(vp.violations),
        violations=violations,
    )


# =============================================================================
# NEW in v2.0: Simple Checks
# =============================================================================


def _generate_simple_checks(result: PDFFullResult) -> SimpleChecksData | None:
    """Generate Simple PDF Checker results data."""
    if not result.simple:
        return None

    simple = result.simple

    checks = [
        SimplePDFCheckData(
            check_id=c.check_id,
            name=c.name,
            status=c.status,
            severity=c.severity,
            message=c.message,
            wcag_sc=c.wcag_sc,
            wcag_level=c.wcag_level,
        )
        for c in simple.checks
    ]

    return SimpleChecksData(
        ran_checks=True,
        is_totally_inaccessible=simple.is_totally_inaccessible,
        total_checks=len(simple.checks),
        passed=simple.passed,
        failed=simple.failed,
        warnings=simple.warnings,
        skipped=simple.skipped,
        critical_count=simple.critical_count,
        serious_count=simple.serious_count,
        moderate_count=simple.moderate_count,
        minor_count=simple.minor_count,
        checks=checks,
    )


# =============================================================================
# NEW in v2.0: Cover Image
# =============================================================================


def _generate_cover_image(pdf_path: Path, config: dict) -> CoverImageData | None:
    """
    Generate cover page image data.

    Renders the first page of the PDF as a preview image.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            doc.close()
            return None

        page = doc[0]

        # Render at reasonable size for cover preview
        dpi = config.get("cover-dpi", 150)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)

        # Convert to base64 PNG
        import base64
        import io

        from PIL import Image

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Resize if too large (max 800px width for reasonable file size)
        max_width = config.get("cover-max-width", 800)
        if img.width > max_width:
            ratio = max_width / img.width
            new_height = int(img.height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

        doc.close()

        return CoverImageData(
            image_base64=image_b64,
            width=img.width,
            height=img.height,
        )

    except Exception as e:
        logger.warning(f"Failed to generate cover image: {e}")
        return None


# =============================================================================
# NEW in v2.0: Contrast Analysis
# =============================================================================


def _generate_contrast_analysis(pdf_path: Path, config: dict) -> ContrastAnalysisData | None:
    """
    Generate color contrast analysis data.

    Uses the pdf_contrast_checker service to detect text with insufficient contrast.
    """
    try:
        from inspekt.services.pdf_contrast_checker import analyze_with_cache

        # Get config options
        dpi = config.get("contrast-dpi", 200)
        max_pages = config.get("contrast-max-pages", 5)
        max_issues = config.get("contrast-max-issues", 5)

        result = analyze_with_cache(
            pdf_path=pdf_path,
            max_pages=max_pages,
            dpi=dpi,
            max_issues_per_page=max_issues,
        )

        if not result:
            return ContrastAnalysisData(
                ran_analysis=False,
                unavailable_reason="Analysis failed",
            )

        # Convert issues to data classes
        issues = []
        for page_result in result.pages:
            for issue in page_result.issues:
                issues.append(ContrastIssueData(
                    page=issue.display_page,
                    foreground_color=issue.fg_hex,
                    background_color=issue.bg_hex,
                    contrast_ratio=round(issue.contrast_ratio, 2),
                    required_ratio=issue.required_ratio,
                    level=issue.wcag_level,
                    text_sample=issue.text_sample[:50] if issue.text_sample else None,
                    bbox=issue.bbox,
                    screenshot_base64=issue.screenshot_b64,
                ))

        return ContrastAnalysisData(
            ran_analysis=True,
            pages_analyzed=result.total_pages_analyzed,
            issues_found=result.total_issues,
            aa_failures=result.serious_issues + result.moderate_issues,
            aaa_failures=0,  # We don't track AAA separately yet
            issues=issues,
        )

    except ImportError as e:
        logger.warning(f"Contrast checker dependencies not available: {e}")
        return ContrastAnalysisData(
            ran_analysis=False,
            unavailable_reason="Required dependencies not installed (pytesseract, numpy)",
        )
    except Exception as e:
        logger.warning(f"Failed to generate contrast analysis: {e}")
        return ContrastAnalysisData(
            ran_analysis=False,
            unavailable_reason=str(e),
        )


# =============================================================================
# NEW in v2.0: Issue Screenshots
# =============================================================================


def _generate_issue_screenshots(
    pdf_path: Path,
    result: PDFFullResult,
    config: dict,
) -> list[IssueScreenshotData]:
    """
    Generate screenshots for veraPDF violations.

    Only generates screenshots for violations that have page and bbox information.
    """
    if not result.verapdf or not result.verapdf.violations:
        return []

    try:
        import base64
        import io

        import fitz  # PyMuPDF
        from PIL import Image

        screenshots = []
        doc = fitz.open(pdf_path)
        max_screenshots = config.get("max-issue-screenshots", 20)

        for idx, violation in enumerate(result.verapdf.violations[:max_screenshots]):
            # Skip if no page info
            page_num = getattr(violation, "page_number", None)
            if page_num is None:
                continue

            # Page is 1-indexed from veraPDF
            if page_num < 1 or page_num > doc.page_count:
                continue

            page = doc[page_num - 1]
            bbox = getattr(violation, "bbox", None)

            try:
                # Render the page region
                dpi = config.get("screenshot-dpi", 150)
                mat = fitz.Matrix(dpi / 72, dpi / 72)

                if bbox:
                    # Crop to bbox with padding
                    x0, y0, x1, y1 = bbox
                    padding = 20
                    rect = fitz.Rect(
                        max(0, x0 - padding),
                        max(0, y0 - padding),
                        min(page.rect.width, x1 + padding),
                        min(page.rect.height, y1 + padding),
                    )
                    pix = page.get_pixmap(matrix=mat, clip=rect, alpha=False)
                else:
                    # Full page thumbnail
                    pix = page.get_pixmap(matrix=mat, alpha=False)

                # Convert to base64 PNG
                img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                # Limit size
                max_width = 400
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_height = int(img.height * ratio)
                    img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)

                buffer = io.BytesIO()
                img.save(buffer, format="PNG", optimize=True)
                image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

                screenshots.append(IssueScreenshotData(
                    violation_index=idx,
                    rule_id=violation.rule_id,
                    page=page_num,
                    screenshot_base64=image_b64,
                    bbox=tuple(bbox) if bbox else None,
                ))

            except Exception as e:
                logger.debug(f"Failed to capture screenshot for violation {idx}: {e}")
                continue

        doc.close()
        return screenshots

    except ImportError as e:
        logger.warning(f"Screenshot generation dependencies not available: {e}")
        return []
    except Exception as e:
        logger.warning(f"Failed to generate issue screenshots: {e}")
        return []


# =============================================================================
# NEW in v2.0: Interactive Preview
# =============================================================================


def _generate_interactive_preview(pdf_path: Path, config: dict) -> InteractivePreviewData | None:
    """
    Generate interactive preview metadata.

    This tracks which pages have been rendered for the interactive tag visualization.
    The actual rendering happens in the HTML report generation.
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(pdf_path)
        page_count = doc.page_count
        doc.close()

        max_pages = config.get("interactive-pages", 5)
        if max_pages == 0:
            # 0 means all pages
            pages_to_render = list(range(1, page_count + 1))
        else:
            # Render first N pages
            pages_to_render = list(range(1, min(max_pages, page_count) + 1))

        return InteractivePreviewData(
            enabled=True,
            pages_rendered=len(pages_to_render),
            pages_with_overlays=pages_to_render,
        )

    except Exception as e:
        logger.warning(f"Failed to generate interactive preview metadata: {e}")
        return InteractivePreviewData(enabled=False)
