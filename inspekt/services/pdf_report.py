"""
PDF Accessibility Report Generator.

Generates a self-contained, accessible HTML report with:
- Cover page preview (first page thumbnail)
- Enhanced document metadata
- Basic check results with severity badges
- veraPDF validation results with issue screenshots
- Text layer vs OCR comparison (scanned document detection)
- Remediation guidance
- WCAG reference links

External assets (images) are stored in a `{report_name}_assets/` folder
to keep the HTML file small and enable lazy loading.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import PDFEnhancedMetadata, PDFFullResult
    from inspekt.services.pdf_issue_visualizer import VisualizationResult
    from inspekt.services.pdf_ocr import TextDiscrepancyResult
    from inspekt.services.pdf_report_data import PDFReportData
    from inspekt.services.pdf_scoring import AccessibilityScore
    from inspekt.services.simple_pdf_checker import SimplePDFResult

logger = logging.getLogger(__name__)


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(str(text)) if text else ""


def _get_severity_class(severity: str) -> str:
    """Get CSS class for severity level."""
    return f"severity-{severity}"


def _get_status_class(status: str) -> str:
    """Get CSS class for check status."""
    return f"status-{status}"


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


# Status icons for check results
STATUS_ICONS = {
    "pass": "✓",
    "fail": "✗",
    "warn": "⚠",
    "skip": "○",
}


def _render_status_icon(status: str) -> str:
    """Render check status as a Unicode icon."""
    return STATUS_ICONS.get(status, "?")


def _render_wcag_link(wcag_sc: str | None, wcag_level: str | None = None) -> str:
    """
    Render WCAG success criterion as a clickable link.

    Args:
        wcag_sc: WCAG success criterion (e.g., "1.1.1")
        wcag_level: WCAG conformance level (e.g., "A", "AA")

    Returns:
        HTML string with link, or "-" if no criterion provided
    """
    if not wcag_sc:
        return "-"

    # Convert "1.1.1" to "1-1-1" for the URL
    url_fragment = wcag_sc.replace(".", "-").lower()
    url = f"https://www.w3.org/WAI/WCAG21/Understanding/{url_fragment}"
    link = f'<a href="{url}" target="_blank" rel="noopener">WCAG {wcag_sc}</a>'

    if wcag_level:
        return f"{link} ({wcag_level})"
    return link


def _render_check_row(check) -> str:
    """
    Render a single accessibility check as a table row.

    Args:
        check: Check object with status, severity, name, message, wcag_sc, wcag_level

    Returns:
        HTML string for a table row
    """
    status_icon = _render_status_icon(check.status)
    wcag_ref = _render_wcag_link(check.wcag_sc, getattr(check, "wcag_level", None))

    # Build the check message, with special handling for figure_alt_text
    message = _escape_html(check.message)

    # For figure_alt_text check failures, add link to Content Audit Images section
    check_id = getattr(check, "check_id", None)
    if check_id == "figure_alt_text" and check.status == "fail":
        details = getattr(check, "details", {}) or {}
        figures_missing = details.get("figures_missing_alt", 0)
        figures_total = details.get("figures_total", 0)

        # Build a custom message with link
        if figures_total > 0 and figures_missing > 0:
            if figures_missing == figures_total:
                # 100% case - all images missing alt text
                message = (
                    f"All {figures_total} Figure tags are missing alternative text. "
                    f'<a href="#audit-images">See Content Audit → Images</a> for details.'
                )
            else:
                # Partial case
                percentage = (figures_missing / figures_total) * 100
                message = (
                    f"{figures_missing} of {figures_total} Figure tags ({percentage:.0f}%) missing alternative text. "
                    f'<a href="#audit-images">See Content Audit → Images</a> for details.'
                )

    return f"""
    <tr class="{_get_status_class(check.status)} {_get_severity_class(check.severity)}">
        <td class="check-name">{_escape_html(check.name)}</td>
        <td class="check-status">
            <span class="status-icon">{status_icon}</span>
            <span class="status-text">{check.status}</span>
        </td>
        <td class="check-severity">
            <span class="severity-badge">{check.severity}</span>
        </td>
        <td class="check-message">{message}</td>
        <td class="check-wcag">{wcag_ref}</td>
    </tr>
    """


def _render_summary_grid(passed: int, failed: int, warnings: int = 0) -> str:
    """
    Render a summary statistics grid with passed/failed/warning counts.

    Args:
        passed: Number of passed checks
        failed: Number of failed checks
        warnings: Number of warnings (optional)

    Returns:
        HTML string for the summary grid
    """
    items = [
        f'''<div class="summary-item passed">
            <span class="summary-count">{passed}</span>
            <span class="summary-label">Passed</span>
        </div>''',
        f'''<div class="summary-item failed">
            <span class="summary-count">{failed}</span>
            <span class="summary-label">Failed</span>
        </div>''',
    ]

    if warnings > 0:
        items.append(f'''<div class="summary-item warnings">
            <span class="summary-count">{warnings}</span>
            <span class="summary-label">Warnings</span>
        </div>''')

    return f'<div class="summary-grid">{"".join(items)}</div>'


# =============================================================================
# Page Size and Paper Format Detection
# =============================================================================

# Standard paper sizes in points (1 inch = 72 points)
PAPER_SIZES = {
    # ISO A Series
    "A0": (2384, 3370),
    "A1": (1684, 2384),
    "A2": (1191, 1684),
    "A3": (842, 1191),
    "A4": (595, 842),
    "A5": (420, 595),
    "A6": (298, 420),
    # ISO B Series
    "B4": (709, 1001),
    "B5": (499, 709),
    # North American
    "US Letter": (612, 792),
    "US Legal": (612, 1008),
    "US Tabloid": (792, 1224),
    "US Executive": (522, 756),
    # Other common sizes
    "US Statement": (396, 612),
    "Ledger": (1224, 792),
}

# =============================================================================
# Accessibility Score Colors
# =============================================================================

# Score color thresholds for accessibility grading
SCORE_COLORS = {
    "excellent": "#22c55e",  # 90-100: Green (A)
    "good": "#84cc16",       # 80-89: Lime (B)
    "fair": "#eab308",       # 70-79: Yellow (C)
    "poor": "#f97316",       # 60-69: Orange (D)
    "failing": "#ef4444",    # 0-59: Red (F)
}

# Score thresholds (lower bound for each grade)
SCORE_THRESHOLDS = {
    "excellent": 90,
    "good": 80,
    "fair": 70,
    "poor": 60,
    "failing": 0,
}


def _identify_paper_size(width_pts: float, height_pts: float, tolerance: float = 3.0) -> tuple[str | None, str]:
    """
    Identify standard paper size and orientation from dimensions in points.

    Args:
        width_pts: Page width in points
        height_pts: Page height in points
        tolerance: Tolerance in points for matching (default 3.0)

    Returns:
        tuple: (paper_name or None, orientation: "portrait" or "landscape")
    """
    # Determine orientation
    if width_pts > height_pts:
        orientation = "landscape"
        # Swap for comparison (paper sizes are defined portrait)
        w, h = height_pts, width_pts
    else:
        orientation = "portrait"
        w, h = width_pts, height_pts

    # Try to match against known paper sizes
    for name, (std_w, std_h) in PAPER_SIZES.items():
        if abs(w - std_w) <= tolerance and abs(h - std_h) <= tolerance:
            return name, orientation

    return None, orientation


def _get_page_size_icon_svg(width_pts: float, height_pts: float, size: int = 32) -> str:
    """
    Generate an SVG icon representing the page dimensions and aspect ratio.

    Args:
        width_pts: Page width in points
        height_pts: Page height in points
        size: Icon size in pixels

    Returns:
        SVG string
    """
    # Calculate aspect ratio for the icon
    max_dim = max(width_pts, height_pts)
    scale = (size - 8) / max_dim  # Leave 4px margin on each side

    icon_w = width_pts * scale
    icon_h = height_pts * scale

    # Center the rectangle
    x = (size - icon_w) / 2
    y = (size - icon_h) / 2

    # Color based on orientation
    fill_color = "#e0f2fe" if width_pts <= height_pts else "#fef3c7"
    stroke_color = "#3b82f6" if width_pts <= height_pts else "#f59e0b"

    return f'''<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg">
        <rect x="{x:.1f}" y="{y:.1f}" width="{icon_w:.1f}" height="{icon_h:.1f}"
              fill="{fill_color}" stroke="{stroke_color}" stroke-width="1.5" rx="1"/>
        <line x1="{x + icon_w/2:.1f}" y1="{y + 2:.1f}" x2="{x + icon_w/2:.1f}" y2="{y + icon_h - 2:.1f}"
              stroke="{stroke_color}" stroke-width="0.5" stroke-dasharray="2,2" opacity="0.5"/>
    </svg>'''


# =============================================================================
# Creator/Producer Icons
# =============================================================================

# SVG icons for common PDF creation tools (simplified, inline-friendly)
CREATOR_ICONS = {
    # Adobe products
    "indesign": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#49021F"/>
        <path d="M8 6v12h2V6H8zM13.5 18h2v-3.5h1c2.21 0 4-1.567 4-3.5s-1.79-3.5-4-3.5h-3v10.5zm2-8.5h1c1.1 0 2 .672 2 1.5s-.9 1.5-2 1.5h-1v-3z" fill="#FF3366"/>
    </svg>''',
    "illustrator": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#310000"/>
        <path d="M12 6l-5 12h2.5l1-2.5h3l1 2.5H17L12 6zm-1 7.5L12 10l1 3.5h-2zM18 9h2v2h-2V9z" fill="#FF9A00"/>
    </svg>''',
    "acrobat": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#B30B00"/>
        <path d="M6 6h12v2H6V6zM6 10h8v2H6v-2zM6 14h10v2H6v-2zM6 18h6v2H6v-2z" fill="white"/>
    </svg>''',
    "photoshop": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#001E36"/>
        <path d="M6 6v12h2v-4h2c2.21 0 4-1.79 4-4s-1.79-4-4-4H6zm2 2h2c1.1 0 2 .9 2 2s-.9 2-2 2H8V8zM15 10h2c1.66 0 3 1.34 3 3v1h-3v-1c0-.55-.45-1-1-1h-1v6h-2v-8h2z" fill="#31A8FF"/>
    </svg>''',
    # Microsoft products
    "word": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#2B579A"/>
        <path d="M6 5l2 14h2l1.5-9L13 19h2l2-14h-2l-1 9-1.5-9h-2L9 14l-1-9H6z" fill="white"/>
    </svg>''',
    "powerpoint": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#D24726"/>
        <path d="M7 5v14h2v-5h3c2.21 0 4-1.79 4-4.5S14.21 5 12 5H7zm2 2h3c1.1 0 2 1.12 2 2.5S13.1 12 12 12H9V7z" fill="white"/>
    </svg>''',
    "excel": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#217346"/>
        <path d="M7 6l3.5 6L7 18h2.5l2.5-4 2.5 4H17l-3.5-6L17 6h-2.5L12 10 9.5 6H7z" fill="white"/>
    </svg>''',
    # Other tools
    "latex": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#008080"/>
        <text x="12" y="16" font-family="serif" font-size="10" fill="white" text-anchor="middle">L<tspan baseline-shift="sub" font-size="8">A</tspan>T<tspan baseline-shift="sub" font-size="8">E</tspan>X</text>
    </svg>''',
    "quark": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#5C2D91"/>
        <text x="12" y="16" font-family="sans-serif" font-size="12" font-weight="bold" fill="white" text-anchor="middle">Q</text>
    </svg>''',
    "pages": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#FF9500"/>
        <path d="M6 4h8l4 4v12H6V4zm7 1v4h4" fill="none" stroke="white" stroke-width="1.5"/>
    </svg>''',
    "libreoffice": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#18A303"/>
        <path d="M6 4h8l4 4v12H6V4z" fill="none" stroke="white" stroke-width="1.5"/>
        <path d="M9 10h6M9 13h6M9 16h4" stroke="white" stroke-width="1"/>
    </svg>''',
    "default": '''<svg width="20" height="20" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="24" height="24" rx="4" fill="#6B7280"/>
        <path d="M6 4h8l4 4v12H6V4z" fill="none" stroke="white" stroke-width="1.5"/>
        <path d="M14 4v4h4" fill="none" stroke="white" stroke-width="1.5"/>
    </svg>''',
}


def _get_creator_icon(creator: str | None, producer: str | None) -> tuple[str, str]:
    """
    Get SVG icon and tool name based on creator/producer strings.

    Args:
        creator: PDF Creator metadata
        producer: PDF Producer metadata

    Returns:
        tuple: (svg_icon_string, tool_name)
    """
    combined = f"{creator or ''} {producer or ''}".lower()

    if "indesign" in combined:
        return CREATOR_ICONS["indesign"], "Adobe InDesign"
    elif "illustrator" in combined:
        return CREATOR_ICONS["illustrator"], "Adobe Illustrator"
    elif "photoshop" in combined:
        return CREATOR_ICONS["photoshop"], "Adobe Photoshop"
    elif "acrobat" in combined or "adobe pdf" in combined:
        return CREATOR_ICONS["acrobat"], "Adobe Acrobat"
    elif "word" in combined or "microsoft office word" in combined:
        return CREATOR_ICONS["word"], "Microsoft Word"
    elif "powerpoint" in combined:
        return CREATOR_ICONS["powerpoint"], "Microsoft PowerPoint"
    elif "excel" in combined:
        return CREATOR_ICONS["excel"], "Microsoft Excel"
    elif "latex" in combined or "pdftex" in combined or "xetex" in combined or "luatex" in combined:
        return CREATOR_ICONS["latex"], "LaTeX"
    elif "quark" in combined:
        return CREATOR_ICONS["quark"], "QuarkXPress"
    elif "pages" in combined:
        return CREATOR_ICONS["pages"], "Apple Pages"
    elif "libreoffice" in combined or "openoffice" in combined:
        return CREATOR_ICONS["libreoffice"], "LibreOffice"
    else:
        return CREATOR_ICONS["default"], None


# =============================================================================
# Language Detection and Verification
# =============================================================================

def _detect_language_from_text(text: str, sample_size: int = 5000) -> str | None:
    """
    Detect language from text using simple heuristics.

    This is a lightweight detection based on character frequency and common words.
    For more accurate detection, consider using the langdetect library.

    Args:
        text: Text to analyze
        sample_size: Max characters to analyze

    Returns:
        ISO 639-1 language code or None
    """
    if not text or len(text.strip()) < 50:
        return None

    sample = text[:sample_size].lower()

    # Common word patterns for different languages
    language_indicators = {
        "en": ["the", "and", "is", "in", "to", "of", "a", "for", "that", "with"],
        "nl": ["de", "het", "een", "van", "en", "in", "op", "te", "voor", "met"],
        "fr": ["le", "la", "les", "de", "et", "en", "un", "une", "est", "pour"],
        "de": ["der", "die", "das", "und", "in", "ist", "von", "mit", "für", "auf"],
        "es": ["el", "la", "de", "que", "y", "en", "los", "un", "es", "por"],
        "it": ["il", "la", "di", "che", "e", "in", "un", "per", "non", "con"],
        "pt": ["o", "a", "de", "que", "e", "em", "um", "para", "com", "não"],
    }

    # Count word matches for each language
    scores = {}
    words = set(sample.split())

    for lang, indicators in language_indicators.items():
        score = sum(1 for word in indicators if word in words)
        if score > 0:
            scores[lang] = score

    if not scores:
        return None

    # Return language with highest score (minimum 2 matches)
    best_lang = max(scores, key=scores.get)
    if scores[best_lang] >= 2:
        return best_lang

    return None


# Language code to name mapping
LANGUAGE_NAMES = {
    "en": "English",
    "en-US": "English (US)",
    "en-GB": "English (UK)",
    "en-AU": "English (Australia)",
    "nl": "Dutch",
    "nl-NL": "Dutch (Netherlands)",
    "nl-BE": "Dutch (Belgium)",
    "fr": "French",
    "fr-FR": "French (France)",
    "fr-BE": "French (Belgium)",
    "fr-CA": "French (Canada)",
    "de": "German",
    "de-DE": "German (Germany)",
    "de-AT": "German (Austria)",
    "de-CH": "German (Switzerland)",
    "es": "Spanish",
    "es-ES": "Spanish (Spain)",
    "it": "Italian",
    "pt": "Portuguese",
    "pt-BR": "Portuguese (Brazil)",
    "ja": "Japanese",
    "zh": "Chinese",
    "ko": "Korean",
    "ar": "Arabic",
    "ru": "Russian",
    "pl": "Polish",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
}


def _get_language_display_name(lang_code: str | None) -> str | None:
    """Get human-readable language name from ISO code."""
    if not lang_code:
        return None

    # Try exact match first
    if lang_code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[lang_code]

    # Try base language code (e.g., "en" from "en-US")
    base_code = lang_code.split("-")[0].lower()
    if base_code in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[base_code]

    return lang_code.upper()


def _normalize_language_code(lang_code: str | None) -> str | None:
    """Normalize language code for comparison."""
    if not lang_code:
        return None
    return lang_code.split("-")[0].lower()


def generate_pdf_report(
    result: "PDFFullResult",
    output_path: Path | str | None = None,
    pdf_path: Path | str | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> str:
    """
    Generate an HTML accessibility report for a PDF document.

    Args:
        result: PDFFullResult from the PDF checker
        output_path: Optional path to save the report. If None, returns HTML string.
        pdf_path: Path to the original PDF (for rendering screenshots)
        config_overrides: Override configuration options:
            - show-cover-page: bool (default True)
            - show-issue-screenshots: bool (default True)
            - show-metadata: bool (default True)
            - show-text-discrepancy-section: bool (default True)
            - no-cover, no-screenshots, no-ocr: CLI flags

    Returns:
        HTML string of the report
    """
    from inspekt.config import get_pdf_report_config

    # Merge config with overrides
    config = get_pdf_report_config()
    if config_overrides:
        config.update(config_overrides)

    meta = result.basic.metadata
    checks = result.basic.checks

    # Determine PDF path for rendering
    if pdf_path is None:
        pdf_path = meta.file_path

    # Initialize asset manager if we're saving to file
    assets = None
    if output_path:
        from inspekt.services.pdf_report_assets import PDFReportAssets

        assets = PDFReportAssets(output_path)

    # Generate executive summary section (accessibility score)
    executive_summary_section = _generate_executive_summary_section(result, config)

    # Generate new sections
    cover_section = ""
    if config.get("show-cover-page", True) and assets:
        cover_section = _generate_cover_section(pdf_path, assets, config)

    issue_screenshots_section = ""
    if config.get("show-issue-screenshots", True) and result.verapdf and assets:
        issue_screenshots_section = _generate_issue_screenshots_section(
            pdf_path, result.verapdf.violations, assets, config
        )

    text_discrepancy_section = ""
    if config.get("show-text-discrepancy-section", True):
        text_discrepancy_section = _generate_text_discrepancy_section(pdf_path, config)

    # Generate structure tree section
    structure_tree_section = _generate_structure_tree_section(pdf_path, config)

    # Generate tag visualization section (Phase 2)
    tag_visualization_section = _generate_tag_visualization_section(pdf_path, config)

    # Generate interactive preview section (Phase 6)
    interactive_preview_section = _generate_interactive_preview_section(pdf_path, config)

    # Generate content audit section
    content_audit_section = _generate_content_audit_section(pdf_path, config)

    # Generate remediation roadmap section
    remediation_roadmap_section = _generate_remediation_section(result, pdf_path, config)

    # Build check rows using helper function
    check_rows = [_render_check_row(check) for check in checks]

    # Build veraPDF section if available
    verapdf_section = ""
    if result.verapdf:
        vera = result.verapdf
        compliance_class = "compliant" if vera.compliant else "non-compliant"
        compliance_text = "Compliant" if vera.compliant else "Non-Compliant"

        violation_rows = []
        for v in vera.violations[:50]:  # Limit to 50
            page_info = f"Page {v.page_number + 1}" if v.page_number is not None else "-"
            violation_rows.append(f"""
            <tr>
                <td class="violation-rule"><code>{_escape_html(v.rule_id)}</code></td>
                <td class="violation-clause">{_escape_html(v.clause)}</td>
                <td class="violation-page">{page_info}</td>
                <td class="violation-desc">{_escape_html(v.description)}</td>
            </tr>
            """)

        more_violations = ""
        if len(vera.violations) > 50:
            more_violations = f'<p class="more-violations">... and {len(vera.violations) - 50} more violations</p>'

        verapdf_section = f"""
        <section class="verapdf-results">
            <h2>PDF/{vera.profile.upper()} Validation</h2>
            <div class="compliance-status {compliance_class}">
                <span class="compliance-icon">{('✓' if vera.compliant else '✗')}</span>
                <span class="compliance-text">PDF/{vera.profile.upper()} {compliance_text}</span>
            </div>
            <dl class="verapdf-meta">
                <dt>Passed Rules</dt><dd>{vera.passed_rules}</dd>
                <dt>Failed Rules</dt><dd>{vera.failed_rules}</dd>
                <dt>Total Violations</dt><dd>{vera.total_violations}</dd>
                {f'<dt>veraPDF Version</dt><dd>{vera.verapdf_version}</dd>' if vera.verapdf_version else ''}
            </dl>
            {f'''
            <h3>Violations</h3>
            <table class="violations-table">
                <thead>
                    <tr>
                        <th>Rule</th>
                        <th>Clause</th>
                        <th>Page</th>
                        <th>Description</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(violation_rows)}
                </tbody>
            </table>
            {more_violations}
            ''' if violation_rows else '<p class="no-violations">No violations found!</p>'}
        </section>
        """

    # Build remediation section
    remediation_items = []
    for check in checks:
        if check.status in ("fail", "warn"):
            check_info = _get_check_info(check.check_id)
            if check_info and check_info.get("remediation"):
                remediation_items.append(f"""
                <div class="remediation-item">
                    <h4>{_escape_html(check.name)}</h4>
                    <p class="remediation-text">{_escape_html(check_info['remediation'])}</p>
                </div>
                """)

    remediation_section = ""
    if remediation_items:
        remediation_section = f"""
        <section id="remediation" class="remediation">
            <h2>Remediation Guidance</h2>
            {''.join(remediation_items)}
        </section>
        """

    # Summary counts
    summary = result.basic

    # Generate the unified About This Document section
    about_section = _generate_about_document_section(pdf_path, assets, config)

    # Generate disclaimer section
    disclaimer_section = _generate_disclaimer_section()

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF Accessibility Report - {_escape_html(meta.file_path.name)}</title>
    <style>
        {_get_all_css()}
    </style>
</head>
<body>
    {_generate_toc_nav()}

    <div class="container main-content">
        <header>
            <h1><span class="icon icon-document"></span>PDF Accessibility Report</h1>
        </header>

        {about_section}

        {executive_summary_section}

        <section id="summary" class="summary">
            <h2>Summary</h2>
            <div class="summary-grid">
                <div class="summary-item passed">
                    <span class="summary-count">{summary.passed}</span>
                    <span class="summary-label">Passed</span>
                </div>
                <div class="summary-item failed">
                    <span class="summary-count">{summary.failed}</span>
                    <span class="summary-label">Failed</span>
                </div>
                {f'''<div class="summary-item warnings">
                    <span class="summary-count">{summary.warnings}</span>
                    <span class="summary-label">Warnings</span>
                </div>''' if summary.warnings > 0 else ''}
            </div>
        </section>

        <section id="basic-checks" class="basic-checks">
            <h2>Essential Accessibility Checks</h2>
            <label class="filter-checkbox">
                <input type="checkbox" id="showFailedOnly" onchange="filterChecks(this.checked)">
                Show failed checks only
            </label>
            <table class="checks-table">
                <thead>
                    <tr>
                        <th>Check</th>
                        <th>Status</th>
                        <th>Severity</th>
                        <th>Details</th>
                        <th>WCAG</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(check_rows)}
                </tbody>
            </table>
        </section>

        {verapdf_section}

        {issue_screenshots_section}

        {_generate_simple_section(result)}

        {text_discrepancy_section}

        {structure_tree_section}

        {tag_visualization_section}

        {interactive_preview_section}

        {content_audit_section}

        {remediation_roadmap_section}

        {remediation_section}

        {disclaimer_section}

        <footer>
            <p>Generated by <a href="https://github.com/roelvangils/inspekt">Inspekt</a> on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </footer>
    </div>
    {_get_interactive_js()}
    {_get_toc_js()}
</body>
</html>
"""

    if output_path:
        output_path = Path(output_path)
        # Add .html extension if not present
        if not output_path.suffix:
            output_path = output_path.with_suffix('.html')
        output_path.write_text(html_content)

        # Clean up orphaned assets
        if assets:
            assets.cleanup_orphaned()

    return html_content


def _generate_toc_nav() -> str:
    """Generate the sticky table of contents navigation."""
    return """
    <nav class="toc-nav" aria-label="Table of Contents">
        <div class="toc-header">
            <span class="toc-icon">☰</span>
            <span class="toc-title">Contents</span>
        </div>
        <ul class="toc-list" role="list">
            <li><a href="#about">About This Document</a></li>
            <li><a href="#score">Accessibility Score</a></li>
            <li><a href="#summary">Summary</a></li>
            <li><a href="#basic-checks">Basic Checks</a></li>
            <li><a href="#text-analysis">Text Layer Analysis</a></li>
            <li><a href="#structure">Structure Tree</a></li>
            <li><a href="#interactive-preview">Interactive Preview</a></li>
            <li class="toc-group">
                <a href="#content-audit">Content Audit</a>
                <ul class="toc-sublist" role="list">
                    <li><a href="#audit-images">Images</a></li>
                    <li><a href="#audit-tables">Tables</a></li>
                    <li><a href="#audit-forms">Forms</a></li>
                    <li><a href="#audit-links">Links</a></li>
                    <li><a href="#audit-lists">Lists</a></li>
                </ul>
            </li>
            <li><a href="#remediation-roadmap">Remediation Roadmap</a></li>
            <li><a href="#remediation">Remediation Advice</a></li>
            <li><a href="#disclaimer">Disclaimer</a></li>
        </ul>
        <button class="toc-toggle" aria-expanded="true" aria-controls="toc-list">
            <span class="visually-hidden">Toggle navigation</span>
            <span class="toc-toggle-icon">‹</span>
        </button>
    </nav>
    """


def _get_all_css() -> str:
    """
    Return complete CSS for the PDF accessibility report.

    Combines all CSS from:
    - _get_report_css(): Base styles, layout, components
    - _get_toc_css(): Table of contents navigation
    - _get_interactive_css(): Interactive features, lightbox, tabs
    """
    return f"""
        /* ============= BASE STYLES & COMPONENTS ============= */
        {_get_report_css()}

        /* ============= TABLE OF CONTENTS ============= */
        {_get_toc_css()}

        /* ============= INTERACTIVE FEATURES ============= */
        {_get_interactive_css()}
    """


def _get_toc_css() -> str:
    """Return CSS for the sticky table of contents navigation."""
    return """
        /* TOC Navigation - Sticky Sidebar */
        .toc-nav {
            position: fixed;
            left: 0;
            top: 0;
            bottom: 0;
            width: 220px;
            background: var(--bg-white);
            border-right: 1px solid var(--border-color);
            padding: 1rem 0;
            overflow-y: auto;
            z-index: 100;
            transition: transform 0.3s ease, width 0.3s ease;
        }

        .toc-nav.collapsed {
            transform: translateX(-180px);
        }

        .toc-header {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 0.5rem;
        }

        .toc-icon {
            font-size: 1.25rem;
            color: var(--text-secondary);
        }

        .toc-title {
            font-weight: 600;
            color: var(--text-primary);
        }

        .toc-list {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .toc-list li {
            margin: 0;
        }

        .toc-list a {
            display: block;
            padding: 0.5rem 1rem;
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.875rem;
            border-left: 3px solid transparent;
            transition: all 0.2s ease;
        }

        .toc-list a:hover,
        .toc-list a:focus {
            color: var(--text-primary);
            background: var(--bg-light);
            border-left-color: var(--color-moderate);
        }

        .toc-list a.active {
            color: var(--text-primary);
            background: var(--bg-light);
            border-left-color: var(--color-pass);
            font-weight: 500;
        }

        .toc-sublist {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .toc-sublist a {
            padding-left: 2rem;
            font-size: 0.8125rem;
        }

        .toc-toggle {
            position: absolute;
            right: -12px;
            top: 50%;
            transform: translateY(-50%);
            width: 24px;
            height: 48px;
            background: var(--bg-white);
            border: 1px solid var(--border-color);
            border-radius: 0 4px 4px 0;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s;
        }

        .toc-toggle:hover {
            background: var(--bg-light);
        }

        .toc-toggle-icon {
            font-size: 1rem;
            color: var(--text-secondary);
            transition: transform 0.3s;
        }

        .toc-nav.collapsed .toc-toggle-icon {
            transform: rotate(180deg);
        }

        /* Main content offset for TOC */
        .main-content {
            margin-left: 220px;
            transition: margin-left 0.3s ease;
        }

        .toc-nav.collapsed + .main-content {
            margin-left: 40px;
        }

        /* Hide TOC on mobile/narrow screens */
        @media (max-width: 1024px) {
            .toc-nav {
                display: none;
            }
            .main-content {
                margin-left: 0;
            }
        }

        /* Print styles - hide TOC */
        @media print {
            .toc-nav {
                display: none;
            }
            .main-content {
                margin-left: 0;
            }
        }

        .visually-hidden {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
        }

        /* About This Document section layout */
        .about-document {
            background: var(--bg-white);
        }

        .about-layout {
            display: flex;
            flex-wrap: wrap;
            gap: 2rem;
            align-items: flex-start;
        }

        .about-cover {
            flex-shrink: 0;
            max-width: 33.333%;  /* Never wider than 1/3 of container */
        }

        .about-metadata {
            flex: 1;
            min-width: 300px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
        }

        .about-metadata .metadata-group {
            background: var(--bg-light);
            border-radius: 0.375rem;
            padding: 1rem;
        }

        .about-metadata .metadata-group h3 {
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin: 0 0 0.75rem 0;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border-color);
        }

        .about-metadata dl {
            margin: 0;
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 0.375rem 1rem;
        }

        .about-metadata dt {
            color: var(--text-secondary);
            font-size: 0.8125rem;
        }

        .about-metadata dd {
            margin: 0;
            font-size: 0.875rem;
            color: var(--text-primary);
        }

        .about-metadata a {
            color: var(--color-moderate);
            text-decoration: none;
        }

        .about-metadata a:hover {
            text-decoration: underline;
        }

        .download-link::after {
            content: ' ↓';
            font-size: 0.75em;
            opacity: 0.7;
        }

        /* Disclaimer section */
        .disclaimer-section {
            background: var(--bg-light);
            border: 1px solid var(--border-color);
        }

        .disclaimer-section h2 {
            font-size: 1.125rem;
            color: var(--text-secondary);
        }

        .disclaimer-content {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
        }

        .disclaimer-group h3 {
            font-size: 0.875rem;
            color: var(--text-primary);
            margin: 0 0 0.5rem 0;
        }

        .disclaimer-group p,
        .disclaimer-group ul {
            font-size: 0.8125rem;
            color: var(--text-secondary);
            margin: 0;
            line-height: 1.5;
        }

        .disclaimer-group ul {
            padding-left: 1.25rem;
            margin-top: 0.25rem;
        }

        .disclaimer-group li {
            margin-bottom: 0.25rem;
        }
    """


def _get_toc_js() -> str:
    """Return JavaScript for TOC interactivity."""
    return """
    <script>
    (function() {
        // TOC toggle functionality
        const tocNav = document.querySelector('.toc-nav');
        const tocToggle = document.querySelector('.toc-toggle');

        if (tocToggle && tocNav) {
            tocToggle.addEventListener('click', function() {
                tocNav.classList.toggle('collapsed');
                const isCollapsed = tocNav.classList.contains('collapsed');
                tocToggle.setAttribute('aria-expanded', !isCollapsed);
            });
        }

        // Active section highlighting with Intersection Observer
        const sections = document.querySelectorAll('section[id]');
        const tocLinks = document.querySelectorAll('.toc-list a');

        if (sections.length && tocLinks.length) {
            const observerOptions = {
                rootMargin: '-20% 0px -60% 0px',
                threshold: 0
            };

            const observer = new IntersectionObserver(function(entries) {
                entries.forEach(function(entry) {
                    if (entry.isIntersecting) {
                        const id = entry.target.getAttribute('id');
                        tocLinks.forEach(function(link) {
                            link.classList.remove('active');
                            if (link.getAttribute('href') === '#' + id) {
                                link.classList.add('active');
                            }
                        });
                    }
                });
            }, observerOptions);

            sections.forEach(function(section) {
                observer.observe(section);
            });
        }

        // Smooth scroll for TOC links
        tocLinks.forEach(function(link) {
            link.addEventListener('click', function(e) {
                e.preventDefault();
                const targetId = this.getAttribute('href').substring(1);
                const targetSection = document.getElementById(targetId);
                if (targetSection) {
                    targetSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    // Update URL without scrolling
                    history.pushState(null, null, '#' + targetId);
                }
            });
        });
    })();
    </script>
    """



def _generate_disclaimer_section() -> str:
    """Generate the disclaimer section with report methodology and copyright info."""
    return """
    <section id="disclaimer" class="disclaimer-section">
        <h2>Disclaimer</h2>
        <div class="disclaimer-content">
            <div class="disclaimer-group">
                <h3>About This Report</h3>
                <p>
                    This accessibility report was automatically generated by Inspekt, an open-source
                    PDF accessibility checking tool. The report provides an assessment based on
                    automated checks and should be used as a starting point for accessibility review.
                </p>
            </div>

            <div class="disclaimer-group">
                <h3>Checking Methodology</h3>
                <p>This report uses multiple checking engines:</p>
                <ul>
                    <li><strong>pikepdf</strong> – Basic PDF structure analysis</li>
                    <li><strong>PyMuPDF</strong> – Content extraction and rendering</li>
                    <li><strong>veraPDF</strong> – PDF/UA validation (when enabled)</li>
                    <li><strong>Tesseract OCR</strong> – Text layer comparison</li>
                </ul>
            </div>

            <div class="disclaimer-group">
                <h3>Limitations</h3>
                <p>
                    Automated testing cannot catch all accessibility issues. Manual review by
                    accessibility experts is recommended for comprehensive compliance assessment.
                    This report does not constitute legal advice regarding PDF/UA or WCAG conformance.
                </p>
            </div>

            <div class="disclaimer-group">
                <h3>Standards Referenced</h3>
                <ul>
                    <li>WCAG 2.1 (Web Content Accessibility Guidelines)</li>
                    <li>PDF/UA-1 (ISO 14289-1)</li>
                    <li>Matterhorn Protocol 1.1</li>
                    <li>Section 508 (US)</li>
                </ul>
            </div>
        </div>
        <p style="margin-top: 1rem; font-size: 0.75rem; color: var(--text-secondary);">
            © Inspekt is open-source software. Report generated for informational purposes only.
        </p>
    </section>
    """


def _get_report_css() -> str:
    """Return the CSS stylesheet for the report."""
    return """
        :root {
            /* Status colors */
            --color-pass: #22c55e;
            --color-fail: #ef4444;
            --color-warn: #eab308;
            --color-skip: #6b7280;

            /* Severity colors */
            --color-critical: #dc2626;
            --color-serious: #f59e0b;
            --color-moderate: #06b6d4;
            --color-minor: #3b82f6;

            /* Semantic background/text pairs */
            --bg-success: #dcfce7;
            --text-success: #166534;
            --bg-error: #fee2e2;
            --text-error: #991b1b;
            --bg-error-dark: #b91c1c;
            --bg-warning: #fef3c7;
            --text-warning: #92400e;
            --bg-warning-border: #ffc107;
            --text-warning-dark: #856404;
            --bg-info: #dbeafe;
            --text-info: #1e40af;
            --bg-info-light: #f0f9ff;
            --bg-info-code: #e0f2fe;

            /* Severity backgrounds */
            --bg-critical: #fef2f2;
            --bg-serious: #fffbeb;
            --text-serious: #b45309;
            --bg-moderate: #ecfeff;
            --text-moderate: #0e7490;
            --bg-minor: #eff6ff;

            /* Base colors */
            --bg-light: #f8fafc;
            --bg-white: #ffffff;
            --bg-neutral: #f0f0f0;
            --bg-neutral-dark: #f5f5f5;
            --bg-tag: #e2e8f0;
            --text-primary: #1e293b;
            --text-secondary: #64748b;
            --border-color: #e2e8f0;
        }

        * { box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: var(--text-primary);
            background: var(--bg-light);
            margin: 0;
            padding: 2rem;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
        }

        h1, h2, h3, h4 {
            margin-top: 0;
            color: var(--text-primary);
        }

        h1 {
            font-size: 1.875rem;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 0.5rem;
        }

        h2 {
            font-size: 1.5rem;
            margin-top: 2rem;
        }

        section {
            background: var(--bg-white);
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }

        /* Executive Summary */
        .executive-summary {
            background: linear-gradient(135deg, var(--bg-white) 0%, var(--bg-light) 100%);
        }

        /* Knockout Warning */
        .knockout-warning {
            display: flex;
            align-items: flex-start;
            gap: 1rem;
            background: var(--bg-critical);
            border: 2px solid var(--color-critical);
            border-radius: 0.5rem;
            padding: 1rem 1.5rem;
            margin-bottom: 1.5rem;
        }

        .knockout-icon {
            font-size: 1.5rem;
            color: var(--color-critical);
            flex-shrink: 0;
        }

        .knockout-content {
            flex: 1;
        }

        .knockout-content strong {
            display: block;
            color: var(--text-error);
            font-size: 1.125rem;
            margin-bottom: 0.25rem;
        }

        .knockout-content p {
            margin: 0;
            color: var(--bg-error-dark);
            font-size: 0.9375rem;
        }

        .score-container {
            display: flex;
            gap: 2rem;
            align-items: center;
            flex-wrap: wrap;
        }

        .score-circle {
            position: relative;
            width: 160px;
            height: 160px;
            flex-shrink: 0;
        }

        .score-ring {
            width: 100%;
            height: 100%;
            transform: rotate(-90deg);
        }

        .score-ring-bg {
            fill: none;
            stroke: var(--bg-light);
            stroke-width: 8;
        }

        .score-ring-fill {
            fill: none;
            stroke: var(--score-color, #22c55e);
            stroke-width: 8;
            stroke-linecap: round;
            transition: stroke-dasharray 0.5s ease;
        }

        .score-content {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            text-align: center;
        }

        .score-value {
            display: block;
            font-size: 2.5rem;
            font-weight: 700;
            line-height: 1;
            color: var(--text-primary);
        }

        .score-grade {
            display: block;
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--score-color, #22c55e);
        }

        .score-details {
            flex: 1;
            min-width: 200px;
        }

        .score-description {
            font-size: 1.125rem;
            font-weight: 500;
            margin: 0 0 1rem 0;
            color: var(--text-primary);
        }

        .score-stats {
            display: flex;
            gap: 1rem;
            margin-bottom: 1rem;
        }

        .score-stats .stat {
            padding: 0.5rem 1rem;
            border-radius: 0.375rem;
            text-align: center;
        }

        .score-stats .stat.passed { background: var(--bg-success); color: var(--text-success); }
        .score-stats .stat.failed { background: var(--bg-error); color: var(--text-error); }
        .score-stats .stat.warnings { background: var(--bg-warning); color: var(--text-warning); }

        .score-stats .stat-value {
            display: block;
            font-size: 1.5rem;
            font-weight: 700;
        }

        .score-stats .stat-label {
            font-size: 0.75rem;
            text-transform: uppercase;
        }

        .severity-breakdown {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .severity-count {
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }

        /* Vibrant severity badge colors */
        .severity-count.critical { background: #fecaca; color: #dc2626; }
        .severity-count.serious { background: #fed7aa; color: #ea580c; }
        .severity-count.moderate { background: #fef08a; color: #ca8a04; }
        .severity-count.minor { background: #e5e7eb; color: #6b7280; }

        .no-issues {
            color: var(--text-success);
            font-weight: 500;
        }

        .category-breakdown {
            margin-top: 1.5rem;
            padding-top: 1.5rem;
            border-top: 1px solid var(--border-color);
        }

        .category-breakdown h3 {
            font-size: 1rem;
            margin-bottom: 1rem;
        }

        .category-rows {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 0.5rem 1.5rem;
        }

        @media (max-width: 768px) {
            .category-rows {
                grid-template-columns: 1fr;
            }
        }

        .category-row {
            display: grid;
            grid-template-columns: 140px 1fr 50px 80px;
            gap: 0.75rem;
            align-items: center;
            margin-bottom: 0.5rem;
        }

        .category-label {
            font-size: 0.875rem;
            color: var(--text-secondary);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }

        .category-bar-container {
            height: 8px;
            background: var(--bg-light);
            border-radius: 4px;
            overflow: hidden;
        }

        .category-bar {
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s ease;
        }

        .category-score {
            font-weight: 600;
            text-align: right;
            font-size: 0.875rem;
        }

        .category-issues {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        /* Document Info with 3D Book Preview */
        .document-info {
            display: flex;
            flex-wrap: wrap;
            gap: 1.5rem;
            align-items: flex-start;
        }

        .document-info > h2 {
            width: 100%;
            flex-basis: 100%;
            margin-bottom: 0;
        }

        .book-preview-column {
            flex-shrink: 0;
        }

        .document-meta-column {
            flex: 1;
            min-width: 250px;
        }

        .document-meta-column .document-meta {
            height: 100%;
        }

        /* Cover Preview */
        .cover-preview-column {
            flex-shrink: 0;
        }

        .cover-image {
            display: block;
            max-height: 400px;
            max-width: 100%;
            border-radius: 4px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        }

        /* Responsive - stack on mobile */
        @media (max-width: 768px) {
            .document-info {
                flex-direction: column;
            }

            .cover-preview-column {
                width: 100%;
                display: flex;
                justify-content: center;
            }

            .document-meta-column {
                width: 100%;
            }
        }

        @media (max-width: 640px) {
            .cover-image {
                max-height: 280px;
            }
        }

        /* Print */
        @media print {
            .cover-image {
                box-shadow: none;
                border: 1px solid #ccc;
            }
        }

        /* Metadata */
        .document-meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }

        .meta-item {
            background: var(--bg-light);
            padding: 0.75rem 1rem;
            border-radius: 0.375rem;
        }

        .meta-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            color: var(--text-secondary);
            margin-bottom: 0.25rem;
        }

        .meta-value {
            font-weight: 600;
        }

        /* Enhanced Metadata */
        .enhanced-metadata .metadata-groups {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1.5rem;
        }

        .enhanced-metadata .metadata-group {
            background: var(--bg-light);
            padding: 1rem 1.25rem;
            border-radius: 0.5rem;
        }

        .enhanced-metadata .metadata-group h3 {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0 0 0.75rem 0;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--border-color);
        }

        .enhanced-metadata dl {
            display: grid;
            grid-template-columns: auto 1fr;
            gap: 0.5rem 1rem;
            margin: 0;
        }

        .enhanced-metadata dt {
            font-weight: normal;
            color: var(--text-secondary);
            font-size: 0.875rem;
        }

        .enhanced-metadata dd {
            margin: 0;
            font-weight: 500;
            font-size: 0.875rem;
            word-break: break-word;
        }

        .enhanced-metadata .ua-badge {
            display: inline-block;
            background: var(--bg-success);
            color: var(--text-success);
            padding: 0.125rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8125rem;
            font-weight: 600;
        }

        .enhanced-metadata .not-set {
            color: var(--text-secondary);
            font-style: italic;
            font-weight: normal;
        }

        .enhanced-metadata .suspects-warning {
            display: inline-block;
            background: var(--bg-warning);
            color: var(--text-warning);
            padding: 0.125rem 0.5rem;
            border-radius: 4px;
            font-size: 0.8125rem;
        }

        /* Summary */
        .summary-grid {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }

        .summary-item {
            padding: 1rem 1.5rem;
            border-radius: 0.375rem;
            text-align: center;
            min-width: 100px;
        }

        .summary-item.passed { background: var(--bg-success); color: var(--text-success); }
        .summary-item.failed { background: var(--bg-error); color: var(--text-error); }
        .summary-item.warnings { background: var(--bg-warning); color: var(--text-warning); }

        .summary-count {
            font-size: 2rem;
            font-weight: 700;
            display: block;
        }

        .summary-label {
            font-size: 0.875rem;
            opacity: 0.8;
        }

        /* Tables */
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }

        th, td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }

        th {
            background: var(--bg-light);
            font-weight: 600;
            font-size: 0.875rem;
        }

        /* Status icons */
        .status-icon {
            font-size: 1.25rem;
            margin-right: 0.5rem;
        }

        .status-pass .status-icon { color: var(--color-pass); }
        .status-fail .status-icon { color: var(--color-fail); }
        .status-warn .status-icon { color: var(--color-warn); }
        .status-skip .status-icon { color: var(--color-skip); }

        /* Prevent status text from wrapping */
        .check-status,
        td .status-icon {
            white-space: nowrap;
        }

        /* Severity badges */
        .severity-badge {
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .severity-critical .severity-badge { background: var(--bg-critical); color: var(--color-critical); }
        .severity-serious .severity-badge { background: var(--bg-serious); color: var(--text-serious); }
        .severity-moderate .severity-badge { background: var(--bg-moderate); color: var(--text-moderate); }
        .severity-minor .severity-badge { background: var(--bg-minor); color: var(--color-minor); }

        /* Filter checkbox */
        .filter-checkbox {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.5rem 1rem;
            background: var(--bg-light);
            border-radius: 0.375rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
            cursor: pointer;
            margin-bottom: 1rem;
        }

        .filter-checkbox:hover {
            background: var(--border-color);
        }

        .filter-checkbox input[type="checkbox"] {
            width: 1rem;
            height: 1rem;
            cursor: pointer;
        }

        /* veraPDF */
        .compliance-status {
            display: flex;
            align-items: center;
            padding: 1rem;
            border-radius: 0.5rem;
            font-size: 1.25rem;
            font-weight: 600;
        }

        .compliance-status.compliant {
            background: var(--bg-success);
            color: var(--text-success);
        }

        .compliance-status.non-compliant {
            background: var(--bg-error);
            color: var(--text-error);
        }

        .compliance-icon {
            font-size: 1.5rem;
            margin-right: 0.75rem;
        }

        .verapdf-meta {
            display: flex;
            gap: 2rem;
            margin: 1rem 0;
        }

        .verapdf-meta dt {
            font-weight: normal;
            color: var(--text-secondary);
        }

        .verapdf-meta dd {
            font-weight: 600;
            margin-left: 0;
        }

        /* Issue Screenshots Gallery */
        .issue-gallery {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }

        .issue-card {
            border: 1px solid var(--border-color);
            border-radius: 8px;
            overflow: hidden;
            background: var(--bg-white);
        }

        .issue-card img {
            width: 100%;
            height: auto;
            display: block;
            background: var(--bg-neutral);
        }

        .issue-card-body {
            padding: 1rem;
        }

        .issue-card-title {
            font-weight: 600;
            margin: 0 0 0.5rem 0;
            font-size: 0.875rem;
        }

        .issue-card-desc {
            font-size: 0.8125rem;
            color: var(--text-secondary);
            margin: 0;
        }

        .issue-card-page {
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-top: 0.5rem;
        }

        /* Text Discrepancy Warning */
        .text-discrepancy-warning {
            background: var(--bg-warning);
            border: 1px solid var(--bg-warning-border);
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }

        .text-discrepancy-warning h4 {
            color: var(--text-warning-dark);
            margin: 0 0 0.5rem 0;
        }

        .text-discrepancy-warning p {
            margin: 0;
            color: var(--text-warning-dark);
        }

        .discrepancy-stats {
            display: flex;
            gap: 2rem;
            margin-top: 1rem;
        }

        .discrepancy-stats dt {
            font-weight: normal;
            color: var(--text-secondary);
        }

        .discrepancy-stats dd {
            margin: 0;
            font-weight: 600;
        }

        .ocr-unavailable {
            background: var(--bg-light);
            padding: 1rem;
            border-radius: 0.5rem;
            color: var(--text-secondary);
        }

        /* Remediation */
        .remediation-item {
            background: var(--bg-light);
            padding: 1rem;
            border-radius: 0.375rem;
            margin-bottom: 1rem;
            border-left: 4px solid var(--color-warn);
        }

        .remediation-item h4 {
            margin-bottom: 0.5rem;
        }

        .remediation-text {
            margin: 0;
            color: var(--text-secondary);
        }

        /* Links */
        a {
            color: var(--color-minor);
            text-decoration: none;
        }

        a:hover {
            text-decoration: underline;
        }

        /* Footer */
        footer {
            text-align: center;
            color: var(--text-secondary);
            font-size: 0.875rem;
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-color);
        }

        code {
            background: var(--bg-light);
            padding: 0.125rem 0.25rem;
            border-radius: 0.25rem;
            font-size: 0.875em;
        }

        /* Utility components */
        .sampling-notice {
            background: var(--bg-info-light);
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
            border-left: 4px solid var(--color-minor);
        }

        .sampling-notice-title {
            color: var(--text-info);
            font-weight: 600;
        }

        .sampling-notice-text {
            margin-top: 0.5rem;
            font-size: 0.875rem;
            color: var(--text-secondary);
        }

        .sampling-notice-code {
            background: var(--bg-info-code);
            padding: 0.125rem 0.375rem;
            border-radius: 3px;
            font-size: 0.8125rem;
        }

        .totally-inaccessible-warning {
            background: var(--bg-error);
            color: var(--text-error);
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }

        .text-muted {
            color: var(--text-secondary);
        }

        .text-link {
            color: var(--color-minor);
            text-decoration: none;
            font-size: 0.875rem;
        }

        .text-link:hover {
            text-decoration: underline;
        }

        .thumb-image {
            max-width: 125px;   /* 25% larger than original 100px */
            max-height: 162px;  /* 25% larger than original 130px */
            border: 1px solid var(--border-color);
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            cursor: zoom-in;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --bg-light: #1e293b;
                --bg-white: #0f172a;
                --text-primary: #f1f5f9;
                --text-secondary: #94a3b8;
                --border-color: #334155;
            }
        }

        /* CSS-based icons (replacing emojis for consistency) */
        .icon {
            display: inline-block;
            width: 1em;
            height: 1em;
            vertical-align: -0.125em;
            background-size: contain;
            background-repeat: no-repeat;
            background-position: center;
            margin-right: 0.375rem;
        }

        .icon-document {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/%3E%3Cpolyline points='14,2 14,8 20,8'/%3E%3Cline x1='16' y1='13' x2='8' y2='13'/%3E%3Cline x1='16' y1='17' x2='8' y2='17'/%3E%3C/svg%3E");
        }

        .icon-chart {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Crect x='3' y='3' width='18' height='18' rx='2'/%3E%3Cline x1='8' y1='12' x2='8' y2='17'/%3E%3Cline x1='12' y1='8' x2='12' y2='17'/%3E%3Cline x1='16' y1='10' x2='16' y2='17'/%3E%3C/svg%3E");
        }

        .icon-image {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Crect x='3' y='3' width='18' height='18' rx='2'/%3E%3Ccircle cx='8.5' cy='8.5' r='1.5'/%3E%3Cpolyline points='21,15 16,10 5,21'/%3E%3C/svg%3E");
        }

        .icon-form {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7'/%3E%3Cpath d='M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z'/%3E%3C/svg%3E");
        }

        .icon-link {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71'/%3E%3Cpath d='M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'/%3E%3C/svg%3E");
        }

        .icon-search {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cline x1='21' y1='21' x2='16.65' y2='16.65'/%3E%3C/svg%3E");
        }

        .icon-tool {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z'/%3E%3C/svg%3E");
        }

        .icon-tip {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cline x1='9' y1='18' x2='15' y2='18'/%3E%3Cline x1='10' y1='22' x2='14' y2='22'/%3E%3Cpath d='M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14'/%3E%3C/svg%3E");
        }

        .icon-pages {
            background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Crect x='2' y='3' width='14' height='18' rx='2'/%3E%3Cpath d='M16 3v18h4a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-4z'/%3E%3C/svg%3E");
        }
    """


def _generate_executive_summary_section(
    result: "PDFFullResult",
    config: dict,
) -> str:
    """Generate the executive summary section with accessibility score."""
    if not config.get("show-score", True):
        return ""

    from inspekt.services.pdf_scoring import calculate_accessibility_score, ScoreCategory

    score = calculate_accessibility_score(result)

    # Build category bars
    category_bars = []
    for category in ScoreCategory:
        cat_score = score.category_scores.get(category)
        if cat_score:
            bar_width = cat_score.score
            bar_color = _get_score_color(cat_score.score)
            issues_text = f"{cat_score.issues_count} issue{'s' if cat_score.issues_count != 1 else ''}" if cat_score.issues_count > 0 else "No issues"
            category_bars.append(f"""
            <div class="category-row">
                <div class="category-label">{category.value}</div>
                <div class="category-bar-container">
                    <div class="category-bar" style="width: {bar_width}%; background-color: {bar_color};"></div>
                </div>
                <div class="category-score">{cat_score.score:.0f}</div>
                <div class="category-issues">{issues_text}</div>
            </div>
            """)

    # Severity breakdown
    severity_items = []
    if score.critical_count > 0:
        severity_items.append(f'<span class="severity-count critical">{score.critical_count} critical</span>')
    if score.serious_count > 0:
        severity_items.append(f'<span class="severity-count serious">{score.serious_count} serious</span>')
    if score.moderate_count > 0:
        severity_items.append(f'<span class="severity-count moderate">{score.moderate_count} moderate</span>')
    if score.minor_count > 0:
        severity_items.append(f'<span class="severity-count minor">{score.minor_count} minor</span>')

    severity_html = " ".join(severity_items) if severity_items else '<span class="no-issues">No issues found</span>'

    # Knockout warning
    knockout_html = ""
    if score.knockout_applied:
        reasons_list = ", ".join(score.knockout_reasons)
        knockout_html = f"""
        <div class="knockout-warning">
            <span class="knockout-icon">⚠</span>
            <div class="knockout-content">
                <strong>Score capped at {score.knockout_cap:.0f}%</strong>
                <p>{reasons_list}</p>
            </div>
        </div>
        """

    return f"""
    <section id="score" class="executive-summary">
        <h2>Accessibility Score</h2>
        {knockout_html}
        <div class="score-container">
            <div class="score-circle" style="--score-color: {score.color};">
                <svg viewBox="0 0 100 100" class="score-ring">
                    <circle cx="50" cy="50" r="45" class="score-ring-bg"/>
                    <circle cx="50" cy="50" r="45" class="score-ring-fill"
                        style="stroke-dasharray: {score.score * 2.83} 283;"/>
                </svg>
                <div class="score-content">
                    <span class="score-value">{score.score:.0f}</span>
                    <span class="score-grade">{score.grade.value}</span>
                </div>
            </div>
            <div class="score-details">
                <p class="score-description">{_escape_html(score.description)}</p>
                <div class="severity-breakdown">
                    {severity_html}
                </div>
            </div>
        </div>
        <div class="category-breakdown">
            <h3>Score by Category</h3>
            <div class="category-rows">
                {''.join(category_bars)}
            </div>
        </div>
    </section>
    """


def _get_score_color(score: float) -> str:
    """Get CSS color for a score value based on accessibility grade thresholds."""
    if score >= SCORE_THRESHOLDS["excellent"]:
        return SCORE_COLORS["excellent"]
    elif score >= SCORE_THRESHOLDS["good"]:
        return SCORE_COLORS["good"]
    elif score >= SCORE_THRESHOLDS["fair"]:
        return SCORE_COLORS["fair"]
    elif score >= SCORE_THRESHOLDS["poor"]:
        return SCORE_COLORS["poor"]
    else:
        return SCORE_COLORS["failing"]


def _generate_cover_section(
    pdf_path: Path | str,
    assets: "PDFReportAssets",
    config: dict,
) -> str:
    """Generate the document cover preview for embedding in document info section."""
    from inspekt.services.pdf_renderer import is_pymupdf_available, PDFRenderer

    if not is_pymupdf_available():
        return ""

    try:
        max_height = config.get("cover-max-height", 400)
        with PDFRenderer(pdf_path) as renderer:
            cover_bytes = renderer.render_cover(max_height=max_height)

        if cover_bytes:
            cover_path = assets.save_cover(cover_bytes)
            return f"""
                <div class="cover-preview-column">
                    <img src="{cover_path}" alt="First page of the PDF document" class="cover-image" loading="lazy">
                </div>"""
    except Exception as e:
        logger.warning(f"Failed to generate cover preview: {e}")

    return ""


def _generate_about_document_section(
    pdf_path: Path | str,
    assets: "PDFReportAssets",
    config: dict,
) -> str:
    """
    Generate the unified 'About This Document' section.

    Combines document information and metadata into a single, well-organized section
    with groups for Basic Information, Technical Details, and Accessibility.
    """
    from inspekt.services.pdf_checker import extract_enhanced_metadata, format_date_human_readable
    from inspekt.services.pdf_ocr import extract_pdf_text

    meta = extract_enhanced_metadata(pdf_path)
    if not meta:
        return ""

    # Generate cover preview
    cover_html = _generate_cover_section(pdf_path, assets, config)

    # Helper to create DuckDuckGo search link for author
    def _author_link(author: str) -> str:
        """Create a DuckDuckGo search link for the author."""
        import urllib.parse
        query = urllib.parse.quote(author)
        return f'<a href="https://duckduckgo.com/?q={query}" target="_blank" rel="noopener noreferrer" title="Search for {_escape_html(author)} on DuckDuckGo">{_escape_html(author)}</a>'

    # Group 1: Basic Information
    basic_items = []
    # Make filename a clickable download link
    file_path_str = str(meta.file_path.absolute()) if meta.file_path.is_absolute() else str(meta.file_path)
    basic_items.append(f'<dt>Filename</dt><dd><a href="{_escape_html(file_path_str)}" download class="download-link">{_escape_html(meta.file_path.name)}</a></dd>')
    basic_items.append(f"<dt>File Size</dt><dd>{_format_file_size(meta.file_size)}</dd>")
    basic_items.append(f"<dt>Pages</dt><dd>{meta.page_count}</dd>")
    if meta.pdf_version:
        basic_items.append(f"<dt>PDF Version</dt><dd>{meta.pdf_version}</dd>")
    if meta.title:
        basic_items.append(f"<dt>Title</dt><dd>{_escape_html(meta.title)}</dd>")
    if meta.author:
        basic_items.append(f"<dt>Author</dt><dd>{_author_link(meta.author)}</dd>")
    if meta.subject:
        basic_items.append(f"<dt>Subject</dt><dd>{_escape_html(meta.subject)}</dd>")
    if meta.keywords:
        basic_items.append(f"<dt>Keywords</dt><dd>{_escape_html(meta.keywords)}</dd>")

    # Dates
    if meta.creation_date:
        display_date = format_date_human_readable(meta.creation_date)
        basic_items.append(f"<dt>Created</dt><dd>{_escape_html(display_date)}</dd>")
    if meta.modification_date:
        display_date = format_date_human_readable(meta.modification_date)
        basic_items.append(f"<dt>Modified</dt><dd>{_escape_html(display_date)}</dd>")

    # Group 2: Technical Details
    tech_items = []

    # Creator/Producer with icon
    if meta.creator or meta.producer:
        creator_icon, tool_name = _get_creator_icon(meta.creator, meta.producer)
        if tool_name:
            creator_display = f'''<span class="creator-with-icon">{creator_icon} {_escape_html(tool_name)}</span>'''
            if meta.creator and meta.creator.lower() != tool_name.lower():
                creator_display += f'<br><span class="creator-detail">{_escape_html(meta.creator)}</span>'
        else:
            creator_display = f'''<span class="creator-with-icon">{creator_icon} {_escape_html(meta.creator or meta.producer)}</span>'''
        tech_items.append(f"<dt>Creator</dt><dd>{creator_display}</dd>")

    if meta.producer and (not meta.creator or meta.producer != meta.creator):
        tech_items.append(f"<dt>Producer</dt><dd>{_escape_html(meta.producer)}</dd>")

    # Page size with standard name
    if meta.page_dimensions and len(meta.page_dimensions) > 0:
        w, h = meta.page_dimensions[0]
        w_in = w / 72
        h_in = h / 72
        paper_name, orientation = _identify_paper_size(w, h)
        size_icon = _get_page_size_icon_svg(w, h, size=32)

        size_parts = []
        if paper_name:
            size_parts.append(f"<strong>{paper_name}</strong>")
        size_parts.append(f'{w_in:.1f}" × {h_in:.1f}"')
        size_parts.append(f'<span class="orientation-badge orientation-{orientation}">{orientation.capitalize()}</span>')

        page_size_html = f'''
        <span class="page-size-display">
            <span class="page-size-icon">{size_icon}</span>
            <span class="page-size-info">{" · ".join(size_parts)}</span>
        </span>
        '''
        tech_items.append(f"<dt>Page Size</dt><dd>{page_size_html}</dd>")

    if meta.is_encrypted:
        tech_items.append('<dt>Encrypted</dt><dd>Yes ⚠</dd>')

    # Group 3: Accessibility
    a11y_items = []

    # Check if document is tagged by looking for structure tree
    is_tagged = False
    try:
        import pikepdf
        with pikepdf.open(pdf_path) as pdf:
            is_tagged = "/StructTreeRoot" in pdf.Root
    except Exception:
        pass

    # Tagged status
    if is_tagged:
        a11y_items.append('<dt>Tagged PDF</dt><dd><span class="status-pass">Yes ✓</span></dd>')
    else:
        a11y_items.append('<dt>Tagged PDF</dt><dd><span class="status-fail">No ✗</span></dd>')

    # PDF/UA
    if meta.has_ua_marker:
        level = meta.conformance_level or "PDF/UA"
        a11y_items.append(f'<dt>PDF/UA</dt><dd><span class="ua-badge">{_escape_html(level)}</span></dd>')
    else:
        a11y_items.append('<dt>PDF/UA</dt><dd><span class="not-set">Not declared</span></dd>')

    # Language with detection
    declared_lang = meta.language
    detected_lang = None

    try:
        sample_text = ""
        for page_num in range(min(3, meta.page_count)):
            page_text = extract_pdf_text(pdf_path, page_num)
            if page_text:
                sample_text += page_text + " "
            if len(sample_text) > 5000:
                break
        if sample_text.strip():
            detected_lang = _detect_language_from_text(sample_text)
    except Exception:
        pass

    if declared_lang:
        lang_display_name = _get_language_display_name(declared_lang) or declared_lang
        if detected_lang:
            declared_norm = _normalize_language_code(declared_lang)
            detected_norm = _normalize_language_code(detected_lang)
            detected_name = _get_language_display_name(detected_lang)

            if declared_norm == detected_norm:
                lang_html = f'''
                <span class="lang-verified">
                    {_escape_html(lang_display_name)}
                    <span class="lang-check" title="Detected language matches declared language">✓</span>
                </span>
                '''
            else:
                lang_html = f'''
                <span class="lang-mismatch">
                    {_escape_html(lang_display_name)}
                    <span class="lang-warning" title="Detected language ({detected_name}) may differ from declared">⚠</span>
                </span>
                <span class="lang-detected">Detected: {_escape_html(detected_name or detected_lang)}</span>
                '''
        else:
            lang_html = _escape_html(lang_display_name)
        a11y_items.append(f"<dt>Language</dt><dd>{lang_html}</dd>")
    else:
        if detected_lang:
            detected_name = _get_language_display_name(detected_lang)
            a11y_items.append(f'''
            <dt>Language</dt>
            <dd>
                <span class="not-set">Not specified</span>
                <span class="lang-detected">Detected: {_escape_html(detected_name or detected_lang)}</span>
            </dd>
            ''')
        else:
            a11y_items.append('<dt>Language</dt><dd><span class="not-set">Not specified</span></dd>')

    if meta.has_suspects_flag:
        a11y_items.append('<dt>OCR Quality</dt><dd><span class="suspects-warning">⚠ Document may have OCR errors</span></dd>')

    # Build the complete section
    return f"""
    <section id="about" class="about-document">
        <h2>About This Document</h2>
        <div class="about-layout">
            {f'<div class="about-cover">{cover_html}</div>' if cover_html else ''}
            <div class="about-metadata">
                <div class="metadata-group">
                    <h3>Basic Information</h3>
                    <dl>{''.join(basic_items)}</dl>
                </div>
                {f'''<div class="metadata-group">
                    <h3>Technical Details</h3>
                    <dl>{''.join(tech_items)}</dl>
                </div>''' if tech_items else ''}
                <div class="metadata-group">
                    <h3>Accessibility</h3>
                    <dl>{''.join(a11y_items)}</dl>
                </div>
            </div>
        </div>
    </section>
    """


def _generate_issue_screenshots_section(
    pdf_path: Path | str,
    violations: list,
    assets: "PDFReportAssets",
    config: dict,
) -> str:
    """Generate the issue screenshots gallery section."""
    from inspekt.services.pdf_issue_visualizer import visualize_pdf_issues

    if not violations:
        return ""

    result = visualize_pdf_issues(pdf_path, violations, assets, config)
    if not result or not result.has_visualizations:
        return ""

    successful = result.successful_screenshots
    if not successful:
        return ""

    cards = []
    for viz in successful[:12]:  # Limit to 12 screenshots
        severity_class = _get_severity_class(viz.severity)
        cards.append(f"""
        <div class="issue-card {severity_class}">
            <img src="{viz.screenshot_path}" alt="Screenshot of issue: {_escape_html(viz.rule_id)}" loading="lazy">
            <div class="issue-card-body">
                <h4 class="issue-card-title">{_escape_html(viz.rule_id)}</h4>
                <p class="issue-card-desc">{_escape_html(viz.description[:150])}{'...' if len(viz.description) > 150 else ''}</p>
                <p class="issue-card-page">Page {viz.page_num + 1}</p>
            </div>
        </div>
        """)

    return f"""
    <section class="issue-screenshots">
        <h2>Issue Locations ({len(successful)} captured)</h2>
        <p class="text-muted" style="margin-bottom: 1rem;">
            Visual preview of accessibility issues found in the document
        </p>
        <div class="issue-gallery">
            {''.join(cards)}
        </div>
    </section>
    """


def _generate_text_discrepancy_section(pdf_path: Path | str, config: dict) -> str:
    """Generate the text discrepancy analysis section with tabbed page-by-page view."""
    from inspekt.services.pdf_ocr import analyze_text_discrepancy, generate_diff_html

    result = analyze_text_discrepancy(pdf_path, config)

    if not result.ocr_available:
        return f"""
        <section id="text-analysis" class="text-analysis">
            <h2>Text Layer Analysis</h2>
            <div class="ocr-unavailable">
                <p>OCR comparison unavailable: {_escape_html(result.unavailable_reason or 'Unknown error')}</p>
                <p><em>Install Tesseract OCR to enable text layer comparison.</em></p>
            </div>
        </section>
        """

    if result.pages_analyzed == 0:
        return ""

    # Generate sampling notice if applicable
    sampling_notice_html = ""
    if result.is_sampled:
        sampling_notice_html = f"""
        <div class="sampling-notice">
            <span class="sampling-notice-title">📊 Sampled Analysis:</span> {_escape_html(result.sampling_description or '')}
            <p class="sampling-notice-text">
                For large documents, a representative sample of pages is analyzed (first 10, last 5, plus random middle pages).
                Use <code class="sampling-notice-code">--ocr-all-pages</code> to analyze every page.
            </p>
        </div>
        """

    warning_html = ""
    if result.is_likely_scanned:
        warning_html = """
        <div class="text-discrepancy-warning">
            <h4>⚠ Document appears to be scanned</h4>
            <p>This PDF contains primarily image-based content. Screen readers and text search may not work correctly.</p>
        </div>
        """
    elif result.pages_with_discrepancy > 0:
        warning_html = f"""
        <div class="text-discrepancy-warning">
            <h4>⚠ Text layer discrepancies detected</h4>
            <p>{result.pages_with_discrepancy} of {result.pages_analyzed} pages have significant differences between the embedded text and visible content.</p>
        </div>
        """

    stats = f"""
    <dl class="discrepancy-stats">
        <dt>Pages analyzed</dt><dd>{result.pages_analyzed}</dd>
        <dt>Overall similarity</dt><dd>{result.overall_similarity:.0%}</dd>
        <dt>Image-only pages</dt><dd>{result.image_only_pages}</dd>
        <dt>Pages with issues</dt><dd>{result.pages_with_discrepancy}</dd>
    </dl>
    """

    # Generate PDF file URL for page links
    pdf_path = Path(pdf_path)
    pdf_file_url = f"file://{pdf_path.absolute()}"

    # Build tabbed page-by-page interface
    if result.page_comparisons:
        # Generate tabs
        tabs_html = []
        panels_html = []
        total_pages = len(result.page_comparisons)

        for i, page in enumerate(result.page_comparisons):
            is_first = i == 0
            has_issue = page.has_significant_discrepancy
            tab_class = "tab"
            if is_first:
                tab_class += " active"
            if has_issue:
                tab_class += " warning"

            # Tab button
            warning_indicator = " ⚠" if has_issue else ""
            tabs_html.append(
                f'<button class="{tab_class}" data-page="{page.page_num + 1}" '
                f'aria-selected="{str(is_first).lower()}">'
                f'Page {page.page_num + 1}{warning_indicator}</button>'
            )

            # Panel content
            panel_class = "page-panel"
            if is_first:
                panel_class += " active"

            similarity_class = "good" if page.similarity >= 0.9 else "warning" if page.similarity >= 0.7 else "poor"

            # Generate diff HTML if available
            diff_html = ""
            if page.diff_result and page.diff_result.has_changes:
                diff_html = generate_diff_html(page.diff_result, side="both")

            # Generate thumbnail HTML with lightbox and navigation
            thumbnail_html = ""
            if page.thumbnail_base64:
                thumb_src = f"data:image/png;base64,{page.thumbnail_base64}"
                # Use larger lightbox image if available, otherwise fall back to thumbnail
                lightbox_src = (
                    f"data:image/png;base64,{page.lightbox_base64}"
                    if page.lightbox_base64
                    else thumb_src
                )
                thumbnail_html = f"""
                <div class="page-thumbnail" style="flex-shrink: 0;">
                    <img src="{thumb_src}"
                         alt="Page {page.page_num + 1} thumbnail"
                         loading="lazy"
                         class="lightbox-trigger thumb-image"
                         data-lightbox-src="{lightbox_src}"
                         data-lightbox-caption="Page {page.page_num + 1} · {page.similarity:.0%} match"
                         data-lightbox-group="pages"
                         data-lightbox-index="{i}"
                         data-lightbox-total="{total_pages}">
                </div>
                """

            # Generate PDF page link
            pdf_page_url = f"{pdf_file_url}#page={page.page_num + 1}"
            pdf_link_html = f"""
            <a href="{pdf_page_url}" class="pdf-page-link text-link" target="_blank">
                Open in PDF viewer ↗
            </a>
            """

            panels_html.append(f"""
            <div class="{panel_class}" data-page="{page.page_num + 1}">
                <div class="page-header-info" style="display: flex; gap: 1rem; margin-bottom: 1rem; align-items: flex-start;">
                    {thumbnail_html}
                    <div class="page-info-block" style="flex: 1;">
                        <h4 style="margin: 0 0 0.5rem 0; font-size: 1rem;">Page {page.page_num + 1}</h4>
                        {pdf_link_html}
                        <div class="page-summary" style="margin-top: 0.5rem;">
                            <span class="similarity similarity-{similarity_class}">{page.similarity:.0%} match</span>
                            <span class="char-counts">
                                PDF: {page.pdf_char_count} chars &nbsp;|&nbsp; OCR: {page.ocr_char_count} chars
                            </span>
                        </div>
                    </div>
                </div>
                <div class="text-comparison">
                    <div class="text-column pdf-text">
                        <h4>PDF Text Layer</h4>
                        <pre>{_escape_html(page.pdf_text) if page.pdf_text else '<em>No text extracted</em>'}</pre>
                    </div>
                    <div class="text-column ocr-text">
                        <h4>OCR Result</h4>
                        <pre>{_escape_html(page.ocr_text) if page.ocr_text else '<em>No text detected</em>'}</pre>
                    </div>
                </div>
                {diff_html}
            </div>
            """)

        tabbed_interface = f"""
        <div class="text-layer-analysis">
            <div class="page-nav-container">
                <button class="nav-arrow prev" onclick="navigatePage(-1)" aria-label="Previous page">‹</button>
                <div class="page-tabs vertical">
                    {''.join(tabs_html)}
                </div>
                <button class="nav-arrow next" onclick="navigatePage(1)" aria-label="Next page">›</button>
            </div>
            <div class="tab-content">
                {''.join(panels_html)}
            </div>
        </div>
        """
    else:
        tabbed_interface = ""

    return f"""
    <section id="text-analysis" class="text-analysis">
        <h2>Text Layer Analysis</h2>
        {sampling_notice_html}
        {warning_html}
        {stats}
        {tabbed_interface}
    </section>
    """


def _get_check_info(check_id: str) -> dict | None:
    """Get check metadata from the JSON config."""
    from inspekt.services.pdf_checker import get_check_info

    return get_check_info(check_id)


def _generate_structure_tree_section(
    pdf_path: Path | str,
    config: dict,
) -> str:
    """Generate the structure tree visualization section."""
    if not config.get("show-structure", True):
        return ""

    try:
        from inspekt.services.pdf_structure_extractor import PDFStructureExtractor

        with PDFStructureExtractor(pdf_path) as extractor:
            result = extractor.extract()

        if not result.has_structure:
            return f"""
            <section id="structure" class="structure-tree collapsible">
                <h2 class="section-header"><span class="icon icon-chart"></span>Structure Tree</h2>
                <div class="section-content">
                    <div class="no-structure-warning">
                        <p>⚠ This document does not have a structure tree (not tagged).</p>
                        <p>A structure tree is required for screen reader accessibility.</p>
                    </div>
                </div>
            </section>
            """

        # Build tree HTML
        tree_html = _build_tree_html(result.root) if result.root else ""

        # Statistics summary
        stats = result.statistics
        stats_html = f"""
        <div class="structure-stats">
            <div class="stat-item">
                <span class="stat-value">{stats.total_nodes}</span>
                <span class="stat-label">Total nodes</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{stats.heading_count}</span>
                <span class="stat-label">Headings</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{stats.figure_count}</span>
                <span class="stat-label">Figures</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{stats.table_count}</span>
                <span class="stat-label">Tables</span>
            </div>
            <div class="stat-item">
                <span class="stat-value">{stats.link_count}</span>
                <span class="stat-label">Links</span>
            </div>
        </div>
        """

        # Validation issues
        validation_html = ""
        if result.validation.issues:
            issues_list = "".join(f"<li>{_escape_html(issue)}</li>" for issue in result.validation.issues)
            validation_html = f"""
            <div class="validation-issues">
                <h4>⚠ Structure Issues</h4>
                <ul>{issues_list}</ul>
            </div>
            """

        return f"""
        <section id="structure" class="structure-tree collapsible">
            <h2 class="section-header"><span class="icon icon-chart"></span>Structure Tree</h2>
            <div class="section-content">
                {stats_html}
                {validation_html}
                <div class="tree-container">
                    {tree_html}
                </div>
            </div>
        </section>
        """

    except Exception as e:
        logger.warning(f"Failed to generate structure tree: {e}")
        return ""


def _build_tree_html(node, depth: int = 0) -> str:
    """Recursively build HTML for structure tree."""
    if depth > 10:  # Prevent infinite recursion
        return ""

    tag_class = "tag-heading" if node.is_heading else "tag-standard"
    if node.has_issues:
        tag_class += " has-issues"

    # Build node content
    content = f'<span class="tag {tag_class}">{_escape_html(node.tag_type)}</span>'
    if node.text_content:
        preview = node.text_content[:50] + "..." if len(node.text_content) > 50 else node.text_content
        content += f' <span class="tag-preview">"{_escape_html(preview)}"</span>'
    if node.alt_text:
        content += f' <span class="tag-alt">(alt: {_escape_html(node.alt_text[:30])})</span>'
    if node.has_issues:
        content += ' <span class="tag-warning">⚠</span>'

    if not node.children:
        return f'<li>{content}</li>'

    children_html = "".join(_build_tree_html(child, depth + 1) for child in node.children[:20])
    if len(node.children) > 20:
        children_html += f'<li class="more-items">... and {len(node.children) - 20} more</li>'

    return f"""
    <li>
        <details{'open' if depth < 2 else ''}>
            <summary>{content}</summary>
            <ul>{children_html}</ul>
        </details>
    </li>
    """


def _generate_tag_visualization_section(
    pdf_path: Path | str,
    config: dict,
) -> str:
    """Generate the tag visualization overlay section (Phase 2)."""
    if not config.get("show-tags", False):
        return ""

    try:
        from inspekt.services.pdf_tag_visualizer import PDFTagVisualizer, parse_page_range, TAG_COLORS

        with PDFTagVisualizer(pdf_path) as visualizer:
            # Determine which pages to visualize
            page_spec = config.get("tag-pages")
            if visualizer._fitz_doc:
                max_pages = len(visualizer._fitz_doc)
            else:
                return ""

            if page_spec:
                pages = parse_page_range(page_spec, max_pages)
            else:
                # Default: first 5 pages
                pages = list(range(min(5, max_pages)))

            if not pages:
                return ""

            # Generate visualizations
            visualizations = visualizer.visualize_pages(pages, dpi=150)

        if not visualizations:
            return ""

        # Build page tabs
        tab_buttons = []
        page_panels = []

        for idx, viz in enumerate(visualizations):
            is_active = "active" if idx == 0 else ""

            # Tab button
            tag_count = len(viz.tags) if viz.tags else 0
            tab_buttons.append(f'''
                <button class="tag-viz-tab {is_active}" data-page="{viz.page_num}" onclick="showTagVizPage({viz.page_num})">
                    Page {viz.display_page}
                    <span class="tag-count">({tag_count} tags)</span>
                </button>
            ''')

            # Page panel
            image_html = ""
            if viz.image_base64:
                image_html = f'''
                    <img src="data:image/png;base64,{viz.image_base64}"
                         alt="Tag visualization for page {viz.display_page}"
                         class="tag-viz-image lightbox-trigger"
                         data-lightbox-src="data:image/png;base64,{viz.image_base64}"
                         data-lightbox-caption="Tag Visualization - Page {viz.display_page}"
                         loading="lazy"
                         style="max-width: 100%; height: auto; border: 1px solid #e5e7eb; border-radius: 8px;">
                '''
            else:
                image_html = '<p class="no-tags">No tags with bounding boxes found on this page.</p>'

            page_panels.append(f'''
                <div class="tag-viz-panel {is_active}" data-page="{viz.page_num}">
                    {image_html}
                </div>
            ''')

        # Build legend
        legend_items = []
        used_tags = set()
        for viz in visualizations:
            for tag in viz.tags:
                used_tags.add(tag.tag_type)

        for tag_type in sorted(used_tags):
            color = TAG_COLORS.get(tag_type, TAG_COLORS.get("Unknown", "#9ca3af"))
            legend_items.append(f'''
                <span class="legend-item" style="display: inline-flex; align-items: center; gap: 4px; margin-right: 12px;">
                    <span style="width: 12px; height: 12px; background: {color}; border-radius: 2px;"></span>
                    <span style="font-size: 0.85rem;">{tag_type}</span>
                </span>
            ''')

        legend_html = f'''
            <div class="tag-legend" style="margin-top: 1rem; padding: 0.75rem; background: #f9fafb; border-radius: 6px; line-height: 2;">
                <strong style="font-size: 0.85rem; color: #4b5563;">Legend:</strong>
                {''.join(legend_items[:20])}
                {f'<span style="color: #6b7280; font-size: 0.85rem;">... and {len(legend_items) - 20} more</span>' if len(legend_items) > 20 else ''}
            </div>
        '''

        # JavaScript for tab switching
        tab_js = '''
        <script>
        function showTagVizPage(pageNum) {
            // Update tabs
            document.querySelectorAll('.tag-viz-tab').forEach(tab => {
                tab.classList.toggle('active', tab.dataset.page == pageNum);
            });
            // Update panels
            document.querySelectorAll('.tag-viz-panel').forEach(panel => {
                panel.classList.toggle('active', panel.dataset.page == pageNum);
            });
        }
        </script>
        '''

        return f'''
        <section id="tag-visualization" class="tag-visualization collapsible">
            <h2 class="section-header"><span class="icon icon-eye"></span>Tag Structure Visualization</h2>
            <div class="section-content">
                <p class="section-description" style="margin-bottom: 1rem; color: #6b7280;">
                    Visual overlay showing PDF tag boundaries, types, and reading order.
                    Each colored rectangle represents a tagged element in the document structure.
                </p>

                <div class="tag-viz-tabs" style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem;">
                    {''.join(tab_buttons)}
                </div>

                <div class="tag-viz-container" style="position: relative;">
                    {''.join(page_panels)}
                </div>

                {legend_html}

                {tab_js}
            </div>
        </section>

        <style>
            .tag-viz-tab {{
                padding: 0.5rem 1rem;
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                background: white;
                cursor: pointer;
                font-size: 0.9rem;
                transition: all 0.2s;
            }}
            .tag-viz-tab:hover {{
                border-color: #3b82f6;
            }}
            .tag-viz-tab.active {{
                background: #3b82f6;
                color: white;
                border-color: #3b82f6;
            }}
            .tag-viz-tab .tag-count {{
                opacity: 0.7;
                font-size: 0.8rem;
            }}
            .tag-viz-panel {{
                display: none;
            }}
            .tag-viz-panel.active {{
                display: block;
            }}
            .tag-viz-image {{
                cursor: zoom-in;
            }}
        </style>
        '''

    except ImportError as e:
        logger.warning(f"Tag visualization dependencies not available: {e}")
        return ""
    except Exception as e:
        logger.warning(f"Failed to generate tag visualization: {e}")
        return ""


def _generate_interactive_preview_section(
    pdf_path: Path | str,
    config: dict,
) -> str:
    """
    Generate the interactive HTML preview section (Phase 6).

    Provides Equidox-style interactive preview with:
    - Clickable tag regions on rendered PDF pages
    - Keyboard navigation (Tab/Shift+Tab)
    - Details panel showing tag info
    - Reading order visualization
    - Zoom controls
    """
    if not config.get("show-interactive-preview", False):
        return ""

    try:
        from pathlib import Path as PathLib
        import base64
        import json

        from inspekt.services.pdf_tag_visualizer import PDFTagVisualizer, TAG_COLORS

        # Determine which page to visualize (already 0-indexed from CLI)
        page_num = config.get("interactive-page", 0)
        if page_num < 0:
            page_num = 0

        with PDFTagVisualizer(pdf_path) as visualizer:
            if not visualizer._fitz_doc:
                return ""

            max_pages = len(visualizer._fitz_doc)
            if page_num >= max_pages:
                page_num = 0

            # Get page dimensions
            page = visualizer._fitz_doc[page_num]
            page_width = page.rect.width
            page_height = page.rect.height

            # Extract tags for this page
            tags = visualizer.extract_page_tags(page_num)

            if not tags:
                return ""

            # Render the page as a base64 image (without tag overlays - JS will draw them)
            import fitz
            dpi = 150
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image_bytes = pix.tobytes("png")
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            # Convert tags to JSON-serializable format
            tags_json = []
            for tag in tags:
                tags_json.append({
                    "tag_type": tag.tag_type,
                    "bbox": tag.bbox if tag.bbox else None,
                    "reading_order": tag.reading_order,
                    "text_preview": tag.text_preview[:100] if tag.text_preview else None,
                    "alt_text": tag.alt_text,
                    "has_issues": tag.has_issues,
                })

        # Read the JavaScript component
        js_path = PathLib(__file__).parent.parent / "static" / "js" / "pdf-preview.js"
        if js_path.exists():
            preview_js = js_path.read_text()
        else:
            # Fallback: inline minimal JS
            logger.warning(f"PDF preview JavaScript not found at {js_path}")
            preview_js = "console.warn('PDF preview JS not found');"

        # Read the CSS
        css_path = PathLib(__file__).parent.parent / "static" / "css" / "pdf-preview.css"
        if css_path.exists():
            preview_css = css_path.read_text()
        else:
            preview_css = ""

        # Build the section HTML
        return f'''
        <section id="interactive-preview" class="interactive-preview-section collapsible">
            <h2 class="section-header"><span class="icon icon-cursor"></span>Interactive Preview</h2>
            <div class="section-content">
                <p class="section-description" style="margin-bottom: 1rem; color: #6b7280;">
                    Click on tag regions to view details, or use <kbd>Tab</kbd> / <kbd>Shift+Tab</kbd> to navigate through the reading order.
                    Page {page_num + 1} of {max_pages}.
                </p>

                <div id="pdf-interactive-preview-container"></div>

                <div class="preview-keyboard-hints" style="margin-top: 1rem; font-size: 0.875rem; color: #6b7280;">
                    <strong>Keyboard shortcuts:</strong>
                    <kbd>Tab</kbd> Next tag &nbsp;|&nbsp;
                    <kbd>Shift+Tab</kbd> Previous tag &nbsp;|&nbsp;
                    <kbd>Esc</kbd> Deselect
                </div>
            </div>
        </section>

        <style>
            {preview_css}

            .interactive-preview-section kbd {{
                display: inline-block;
                padding: 2px 6px;
                font-size: 0.8rem;
                font-family: monospace;
                background: #f3f4f6;
                border: 1px solid #d1d5db;
                border-radius: 4px;
                box-shadow: 0 1px 0 #d1d5db;
            }}
        </style>

        <script>
            {preview_js}

            // Initialize the interactive preview when DOM is ready
            document.addEventListener('DOMContentLoaded', function() {{
                if (typeof PDFInteractivePreview !== 'undefined') {{
                    const preview = new PDFInteractivePreview('pdf-interactive-preview-container', {{
                        pageImage: 'data:image/png;base64,{image_base64}',
                        tags: {json.dumps(tags_json)},
                        pageWidth: {page_width},
                        pageHeight: {page_height},
                        dpi: {dpi},
                        showReadingOrder: true,
                        showLabels: true,
                        onTagSelect: function(tag, index) {{
                            console.log('Selected tag:', tag.tag_type, 'at index', index);
                        }}
                    }});
                }} else {{
                    console.error('PDFInteractivePreview class not found');
                }}
            }});
        </script>
        '''

    except ImportError as e:
        logger.warning(f"Interactive preview dependencies not available: {e}")
        return ""
    except Exception as e:
        logger.warning(f"Failed to generate interactive preview: {e}")
        import traceback
        traceback.print_exc()
        return ""


def _generate_content_audit_section(
    pdf_path: Path | str,
    config: dict,
) -> str:
    """Generate the content audit section (images, tables, forms, links)."""
    if not config.get("show-content-audit", True):
        return ""

    try:
        from inspekt.services.pdf_content_auditor import PDFContentAuditor

        # Enable thumbnails for images
        include_thumbnails = config.get("show-image-thumbnails", True)

        with PDFContentAuditor(pdf_path) as auditor:
            result = auditor.audit()

            # Extract thumbnails and lightbox images if enabled
            if include_thumbnails and result.images:
                for img in result.images[:20]:  # Limit to displayed images
                    thumbnail, lightbox = auditor.get_image_dual_size(
                        img.page,
                        img.index,
                        thumbnail_size=100,
                        lightbox_size=600,
                    )
                    img.thumbnail_base64 = thumbnail
                    img.lightbox_base64 = lightbox

            # AI Image Classification (Phase 1)
            if config.get("classify-images") and result.images:
                ai_provider = config.get("ai-provider")
                use_clip = True  # Try CLIP first (fast, local)
                use_vision_ai = ai_provider is not None  # Use Vision AI if provider specified

                logger.info(f"Classifying {len(result.images)} images...")
                auditor.classify_images(
                    result.images[:20],  # Limit to displayed images
                    use_clip=use_clip,
                    use_vision_ai=use_vision_ai,
                    ai_provider=ai_provider,
                )

            # AI Alt-Text Generation (Phase 3)
            if config.get("generate-alt-text") and result.images:
                ai_provider = config.get("ai-provider")

                # Get document title for context
                try:
                    import pikepdf
                    with pikepdf.open(pdf_path) as pdf:
                        doc_title = str(pdf.docinfo.get("/Title", "")) or None
                except Exception:
                    doc_title = None

                logger.info("Generating AI alt-text suggestions...")
                auditor.generate_alt_text_suggestions(
                    result.images[:20],  # Limit to displayed images
                    ai_provider=ai_provider,
                    document_title=doc_title,
                )

        sections = []

        # Images audit
        if result.total_images > 0:
            # Group images by page
            images_by_page: dict[int, list] = {}
            for img in result.images[:50]:  # Limit to 50 images
                page = img.display_page
                if page not in images_by_page:
                    images_by_page[page] = []
                images_by_page[page].append(img)

            # Get PDF file URL for page links
            pdf_file_url = _escape_html(str(pdf_path))

            # Collect unique categories and statuses for filter options
            all_categories = set()
            for img in result.images[:50]:
                if img.image_category:
                    all_categories.add(img.image_category)

            # Build category options for filter
            category_options = ['<option value="all">All categories</option>']
            category_display_names = {
                "photograph": "Photograph",
                "illustration": "Illustration",
                "infographic": "Infographic",
                "chart_or_graph": "Chart/Graph",
                "table_as_image": "Table as Image",
                "text_as_image": "Text as Image",
                "logo_or_icon": "Logo/Icon",
                "decorative": "Decorative",
                "unknown": "Unknown",
            }
            for cat in sorted(all_categories):
                display = category_display_names.get(cat, cat.replace("_", " ").title())
                category_options.append(f'<option value="{cat}">{display}</option>')

            # Build image rows grouped by page
            image_rows = []
            global_idx = 0
            for page_num in sorted(images_by_page.keys()):
                page_images = images_by_page[page_num]
                # Page group header with link to PDF page
                image_rows.append(f'''
                <tr class="page-group-header" data-page="{page_num}">
                    <td colspan="5">
                        <a href="{pdf_file_url}#page={page_num}" target="_blank" title="Open page {page_num} in PDF">
                            Page {page_num} <span class="external-link-icon">↗</span>
                        </a>
                        <span style="color: var(--text-secondary); font-weight: normal; margin-left: 1rem;">({len(page_images)} image{'s' if len(page_images) != 1 else ''})</span>
                    </td>
                </tr>
                ''')

                for img in page_images:
                    status_icon = "✓" if img.status == "pass" else "✗" if img.status == "fail" else "○"
                    status_class = f"status-{img.status}"

                    # Determine alt text status for filtering
                    alt_status = "decorative" if img.is_decorative else ("available" if img.has_alt_text else "missing")

                    alt_display = _escape_html(img.alt_text[:50]) if img.alt_text else '<span class="missing">Missing</span>'
                    if img.is_decorative:
                        alt_display = '<span class="decorative">Decorative</span>'

                    # Thumbnail cell with lightbox support
                    thumbnail_html = ""
                    if img.thumbnail_base64:
                        thumb_src = f"data:image/png;base64,{img.thumbnail_base64}"
                        lightbox_src = (
                            f"data:image/png;base64,{img.lightbox_base64}"
                            if img.lightbox_base64
                            else thumb_src
                        )
                        alt_text = _escape_html(img.alt_text) if img.alt_text else f"Image on page {img.display_page}"
                        thumbnail_html = f'''<img src="{thumb_src}" alt="Preview" class="image-thumbnail lightbox-trigger"
                            data-lightbox-src="{lightbox_src}"
                            data-lightbox-caption="Page {img.display_page} · {int(img.width)}×{int(img.height)} · {alt_text}"
                            data-lightbox-group="images"
                            data-lightbox-index="{global_idx}"
                            loading="lazy"
                            style="cursor: zoom-in;">'''
                    else:
                        thumbnail_html = '<span class="no-preview">No preview</span>'

                    # Category badge with color coding
                    category_html = ""
                    category_value = img.image_category or "unknown"
                    if img.image_category:
                        category_colors = {
                            "photograph": "#3b82f6",
                            "illustration": "#8b5cf6",
                            "infographic": "#ec4899",
                            "chart_or_graph": "#06b6d4",
                            "table_as_image": "#ef4444",
                            "text_as_image": "#f97316",
                            "logo_or_icon": "#10b981",
                            "decorative": "#6b7280",
                            "unknown": "#9ca3af",
                        }
                        color = category_colors.get(img.image_category, "#9ca3af")
                        display_name = img.category_display_name
                        confidence = f"{img.category_confidence:.0%}" if img.category_confidence else ""
                        warning_icon = " ⚠️" if img.category_needs_warning else ""
                        category_html = f'''<span class="category-badge" style="background: {color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.75rem; white-space: nowrap;" title="Confidence: {confidence}">{display_name}{warning_icon}</span>'''
                    else:
                        category_html = '<span class="category-unclassified">—</span>'

                    # AI suggestion display
                    ai_suggestion_html = ""
                    if img.ai_suggested_alt and not img.has_alt_text:
                        escaped_suggestion = _escape_html(img.ai_suggested_alt)
                        ai_suggestion_html = f'''
                        <div class="ai-suggestion" style="margin-top: 0.5rem; padding: 0.5rem; background: #f0f9ff; border-left: 3px solid #3b82f6; border-radius: 0 4px 4px 0; font-size: 0.85rem;">
                            <span style="color: #3b82f6; font-weight: 500;">✨ AI Suggestion:</span>
                            <span class="suggestion-text" style="color: #1e40af;">"{escaped_suggestion}"</span>
                            <button class="copy-suggestion" onclick="navigator.clipboard.writeText('{escaped_suggestion.replace("'", "\\'")}'); this.textContent='✓ Copied!'; setTimeout(() => this.textContent='📋', 1500);" style="margin-left: 0.5rem; padding: 2px 6px; border: 1px solid #93c5fd; border-radius: 3px; background: white; cursor: pointer; font-size: 0.75rem;" title="Copy to clipboard">📋</button>
                        </div>'''

                    alt_cell_content = alt_display + ai_suggestion_html

                    image_rows.append(f"""
                    <tr class="{status_class}" data-category="{category_value}" data-alt-status="{alt_status}" data-status="{img.status}" data-page="{page_num}">
                        <td class="thumbnail-cell">{thumbnail_html}</td>
                        <td>{int(img.width)}×{int(img.height)}</td>
                        <td class="category-cell">{category_html}</td>
                        <td class="alt-text-cell">{alt_cell_content}</td>
                        <td><span class="status-icon">{status_icon}</span></td>
                    </tr>
                    """)
                    global_idx += 1

            # Count images by category for summary
            category_counts = {}
            for img in result.images:
                cat = img.image_category or "unknown"
                category_counts[cat] = category_counts.get(cat, 0) + 1

            category_summary = ", ".join(
                f"{count} {cat.replace('_', ' ')}" for cat, count in sorted(category_counts.items()) if cat != "unknown"
            ) if any(img.image_category for img in result.images) else ""

            # Guidance panel
            guidance_html = ""
            if any(img.image_category for img in result.images):
                guidance_html = '''
                <details class="guidance-panel" style="margin-top: 1rem; padding: 1rem; background: #fefce8; border-radius: 8px; border: 1px solid #fde047;">
                    <summary style="cursor: pointer; font-weight: 500; color: #854d0e;">📚 Alt-Text Writing Guidance by Category</summary>
                    <div style="margin-top: 1rem; display: grid; gap: 0.75rem;">
                        <div><strong style="color: #3b82f6;">📷 Photograph:</strong> Describe who/what is shown, the setting, and relevant actions or emotions.</div>
                        <div><strong style="color: #8b5cf6;">🎨 Illustration:</strong> Describe the subject and style, focusing on information conveyed.</div>
                        <div><strong style="color: #ec4899;">📊 Infographic:</strong> Summarize the main message. Consider a detailed text alternative.</div>
                        <div><strong style="color: #06b6d4;">📈 Chart/Graph:</strong> Describe chart type, data visualized, axis labels, and key trends.</div>
                        <div><strong style="color: #ef4444;">⚠️ Table as Image:</strong> CONVERT TO REAL TABLE. If kept, describe all headers and data.</div>
                        <div><strong style="color: #f97316;">⚠️ Text as Image:</strong> USE ACTUAL TEXT. Include verbatim transcription of visible text.</div>
                        <div><strong style="color: #10b981;">🏷️ Logo/Icon:</strong> Use the organization/brand name (e.g., "Acme Corp logo").</div>
                        <div><strong style="color: #6b7280;">✨ Decorative:</strong> Mark as artifact (no alt text needed).</div>
                    </div>
                </details>'''

            # Filter controls
            filter_html = f'''
            <div class="image-filters">
                <label>
                    Category:
                    <select id="filter-category" onchange="filterImageTable()">
                        {''.join(category_options)}
                    </select>
                </label>
                <label>
                    Alt Text:
                    <select id="filter-alt" onchange="filterImageTable()">
                        <option value="all">All</option>
                        <option value="missing">Missing</option>
                        <option value="available">Available</option>
                        <option value="decorative">Decorative</option>
                    </select>
                </label>
                <label>
                    Status:
                    <select id="filter-status" onchange="filterImageTable()">
                        <option value="all">All</option>
                        <option value="pass">Pass ✓</option>
                        <option value="fail">Fail ✗</option>
                        <option value="skip">Skipped</option>
                    </select>
                </label>
                <span class="filter-count" id="filter-count" role="status" aria-live="polite">Showing all {len(result.images[:50])} images</span>
                <button type="button" class="filter-reset" onclick="resetImageFilters()" title="Reset all filters">Reset</button>
            </div>
            '''

            sections.append(f"""
            <div id="audit-images" class="audit-subsection">
                <h3><span class="icon icon-image"></span>Images ({result.total_images})</h3>
                <p class="audit-summary">
                    {result.images_without_alt} missing alt text,
                    {result.images_decorative} decorative
                    {f"<br><span style='color: #6b7280; font-size: 0.9em;'>Categories: {category_summary}</span>" if category_summary else ""}
                </p>
                {filter_html}
                <table class="audit-table image-audit-table">
                    <thead><tr><th>Preview</th><th>Size</th><th>Category</th><th>Alt Text</th><th>Status</th></tr></thead>
                    <tbody>{''.join(image_rows)}</tbody>
                </table>
                {guidance_html}
            </div>
            """)

        # Tables audit
        if result.total_tables > 0:
            table_rows = []
            for tbl in result.tables[:20]:
                status_icon = "✓" if tbl.status == "pass" else "✗" if tbl.status == "fail" else "⚠"
                status_class = f"status-{tbl.status}"
                headers_display = "✓" if tbl.has_headers else "❌ Missing"
                table_rows.append(f"""
                <tr class="{status_class}">
                    <td>{tbl.display_page}</td>
                    <td>{tbl.size_str}</td>
                    <td>{headers_display}</td>
                    <td>{tbl.scope_type or '-'}</td>
                    <td><span class="status-icon">{status_icon}</span></td>
                </tr>
                """)

            sections.append(f"""
            <div id="audit-tables" class="audit-subsection">
                <h3><span class="icon icon-chart"></span>Tables ({result.total_tables})</h3>
                <p class="audit-summary">
                    {result.tables_without_headers} missing headers
                </p>
                <table class="audit-table">
                    <thead><tr><th>Page</th><th>Size</th><th>Headers</th><th>Scope</th><th>Status</th></tr></thead>
                    <tbody>{''.join(table_rows)}</tbody>
                </table>
            </div>
            """)

        # Forms audit
        if result.total_form_fields > 0:
            form_rows = []
            for fld in result.forms[:20]:
                status_icon = "✓" if fld.status == "pass" else "✗" if fld.status == "fail" else "⚠"
                status_class = f"status-{fld.status}"
                label_display = _escape_html(fld.accessible_name[:40]) if fld.accessible_name else "❌ Missing"
                form_rows.append(f"""
                <tr class="{status_class}">
                    <td>{fld.display_page}</td>
                    <td>{fld.field_type}</td>
                    <td>{label_display}</td>
                    <td>{"✓" if fld.has_tooltip else "❌"}</td>
                    <td><span class="status-icon">{status_icon}</span></td>
                </tr>
                """)

            sections.append(f"""
            <div id="audit-forms" class="audit-subsection">
                <h3><span class="icon icon-form"></span>Form Fields ({result.total_form_fields})</h3>
                <p class="audit-summary">
                    {result.fields_without_labels} missing labels
                </p>
                <table class="audit-table">
                    <thead><tr><th>Page</th><th>Type</th><th>Label</th><th>Tooltip</th><th>Status</th></tr></thead>
                    <tbody>{''.join(form_rows)}</tbody>
                </table>
            </div>
            """)

        # Links audit
        if result.total_links > 0:
            link_rows = []
            # Get PDF file path for page links
            pdf_file_url = _escape_html(str(pdf_path))

            for link in result.links[:20]:
                status_icon = "✓" if link.status == "pass" else "✗" if link.status == "fail" else "⚠"
                status_class = f"status-{link.status}"

                # Make page number a clickable link to PDF page
                page_num = getattr(link, 'page_num', None)
                if page_num is not None:
                    page_link = f'<a href="{pdf_file_url}#page={page_num}" target="_blank" class="page-link" title="Open page {page_num} in PDF">{link.display_page}</a>'
                else:
                    page_link = link.display_page

                # Link text
                text_display = _escape_html(link.link_text[:50]) if link.link_text else '<span class="missing">❌ Missing</span>'

                # Consolidate link text and destination into one cell
                dest_html = ""
                if link.destination:
                    dest_escaped = _escape_html(link.destination)
                    dest_truncated = link.destination[:60] + "..." if len(link.destination) > 60 else link.destination
                    if link.destination_type == "uri" and link.destination.startswith(("http://", "https://")):
                        # External link - make clickable
                        dest_html = f'<a href="{dest_escaped}" target="_blank" rel="noopener noreferrer" class="link-url" title="{dest_escaped}">{_escape_html(dest_truncated)}</a>'
                    elif link.is_internal:
                        # Internal link (goto page, etc.)
                        dest_html = f'<span class="link-url" title="{dest_escaped}">{_escape_html(dest_escaped[:40])}</span>'
                    else:
                        dest_html = f'<span class="link-url" title="{dest_escaped}">{_escape_html(dest_truncated)}</span>'

                # Build combined cell with text and destination stacked
                combined_cell = f'''<td class="link-combined-cell">
                    <span class="link-text">{text_display}</span>
                    {dest_html}
                </td>'''

                link_rows.append(f"""
                <tr class="{status_class}">
                    <td>{page_link}</td>
                    {combined_cell}
                    <td>{link.destination_type}</td>
                    <td><span class="status-icon">{status_icon}</span></td>
                </tr>
                """)

            sections.append(f"""
            <div id="audit-links" class="audit-subsection">
                <h3><span class="icon icon-link"></span>Links ({result.total_links})</h3>
                <p class="audit-summary">
                    {result.links_non_descriptive} non-descriptive,
                    {result.links_missing_text} missing text
                </p>
                <table class="audit-table link-audit-table">
                    <thead><tr><th>Page</th><th>Link</th><th>Type</th><th>Status</th></tr></thead>
                    <tbody>{''.join(link_rows)}</tbody>
                </table>
            </div>
            """)

        # Lists audit
        if result.total_lists > 0:
            list_rows = []
            for lst in result.lists[:20]:
                status_icon = "✓" if lst.status == "pass" else "✗" if lst.status == "fail" else "⚠"
                status_class = f"status-{lst.status}"

                # Build structure info
                structure_parts = []
                if lst.item_count > 0:
                    structure_parts.append(f"{lst.item_count} items")
                if lst.items_with_label > 0:
                    structure_parts.append(f"{lst.items_with_label} Lbl")
                if lst.items_with_body > 0:
                    structure_parts.append(f"{lst.items_with_body} LBody")
                if lst.nested_list_count > 0:
                    structure_parts.append(f"{lst.nested_list_count} nested")
                structure_str = ", ".join(structure_parts) if structure_parts else "-"

                # Show issues if any
                issues_html = ""
                if lst.issues:
                    issues_escaped = "; ".join(_escape_html(i) for i in lst.issues[:2])
                    issues_html = f'<span class="list-issues" title="{issues_escaped}">{issues_escaped[:40]}{"..." if len(issues_escaped) > 40 else ""}</span>'
                else:
                    issues_html = '<span class="no-issues">None</span>'

                list_rows.append(f"""
                <tr class="{status_class}">
                    <td>{lst.display_page}</td>
                    <td>{lst.item_count}</td>
                    <td>{structure_str}</td>
                    <td class="issues-cell">{issues_html}</td>
                    <td><span class="status-icon">{status_icon}</span></td>
                </tr>
                """)

            sections.append(f"""
            <div id="audit-lists" class="audit-subsection">
                <h3><span class="icon icon-list"></span>Lists ({result.total_lists})</h3>
                <p class="audit-summary">
                    {result.lists_with_issues} with structure issues
                </p>
                <table class="audit-table list-audit-table">
                    <thead><tr><th>Page</th><th>Items</th><th>Structure</th><th>Issues</th><th>Status</th></tr></thead>
                    <tbody>{''.join(list_rows)}</tbody>
                </table>
            </div>
            """)

        if not sections:
            return ""

        return f"""
        <section id="content-audit" class="content-audit collapsible">
            <h2 class="section-header"><span class="icon icon-search"></span>Content Audit</h2>
            <div class="section-content">
                {''.join(sections)}
            </div>
        </section>
        """

    except Exception as e:
        logger.warning(f"Failed to generate content audit: {e}")
        return ""


def _generate_remediation_section(
    result: "PDFFullResult",
    pdf_path: Path | str,
    config: dict,
) -> str:
    """Generate the remediation roadmap section."""
    if not config.get("show-remediation", True):
        return ""

    try:
        from inspekt.services.remediation_planner import generate_remediation_plan, RemediationPriority

        plan = generate_remediation_plan(result)

        if plan.task_count == 0:
            return """
            <section id="remediation-roadmap" class="remediation-roadmap collapsible">
                <h2 class="section-header"><span class="icon icon-tool"></span>Remediation Roadmap</h2>
                <div class="section-content">
                    <p class="no-tasks">✓ No remediation tasks required. Document appears to be accessible!</p>
                </div>
            </section>
            """

        # Build task cards by priority
        priority_sections = []
        for priority in RemediationPriority:
            tasks = plan.get_tasks_by_priority(priority)
            if not tasks:
                continue

            task_cards = []
            for task in tasks:
                wcag_badges = " ".join(
                    f'<span class="wcag-badge">{crit}</span>'
                    for crit in task.wcag_criteria[:3]
                )

                steps_html = ""
                if task.steps:
                    steps_list = "".join(f"<li>{_escape_html(step)}</li>" for step in task.steps[:6])
                    steps_html = f"""
                    <details class="task-steps">
                        <summary>Step-by-step instructions</summary>
                        <ol>{steps_list}</ol>
                    </details>
                    """

                task_cards.append(f"""
                <div class="task-card" data-priority="{priority.name.lower()}">
                    <div class="task-header">
                        <span class="task-title">{_escape_html(task.title)}</span>
                        <span class="task-effort">{task.effort.value}</span>
                    </div>
                    <div class="task-body">
                        <p class="task-description">{_escape_html(task.description)}</p>
                        <div class="task-meta">
                            <span class="task-pages"><span class="icon icon-pages"></span>{task.pages_summary}</span>
                            <span class="task-count">{task.affected_count} issue(s)</span>
                        </div>
                        <div class="task-wcag">{wcag_badges}</div>
                        {steps_html}
                        {f'<p class="task-note"><span class="icon icon-tip"></span>{_escape_html(task.notes)}</p>' if task.notes else ''}
                    </div>
                </div>
                """)

            priority_sections.append(f"""
            <div class="priority-group {priority.name.lower()}">
                <h3>{priority.icon} {priority.label} ({len(tasks)} task{'s' if len(tasks) != 1 else ''})</h3>
                {''.join(task_cards)}
            </div>
            """)

        summary = f"""
        <div class="remediation-summary">
            <div class="summary-stat">
                <span class="stat-value">{plan.task_count}</span>
                <span class="stat-label">Tasks</span>
            </div>
            <div class="summary-stat">
                <span class="stat-value">{plan.total_issues}</span>
                <span class="stat-label">Issues</span>
            </div>
            <div class="summary-stat">
                <span class="stat-value">{plan.estimated_total_effort}</span>
                <span class="stat-label">Est. Effort</span>
            </div>
        </div>
        """

        return f"""
        <section id="remediation-roadmap" class="remediation-roadmap collapsible">
            <h2 class="section-header"><span class="icon icon-tool"></span>Remediation Roadmap</h2>
            <div class="section-content">
                {summary}
                {''.join(priority_sections)}
            </div>
        </section>
        """

    except Exception as e:
        logger.warning(f"Failed to generate remediation roadmap: {e}")
        return ""


def _get_interactive_css() -> str:
    """Return CSS for interactive features."""
    return """
        /* Collapsible sections */
        .collapsible .section-header {
            cursor: pointer;
            user-select: none;
            display: flex;
            align-items: center;
        }

        .collapsible .section-header::before {
            content: '▼';
            margin-right: 0.5rem;
            font-size: 0.75rem;
            transition: transform 0.2s;
        }

        .collapsible.collapsed .section-header::before {
            transform: rotate(-90deg);
        }

        .collapsible.collapsed .section-content {
            display: none;
        }

        /* Structure tree */
        .structure-stats {
            display: flex;
            gap: 1.5rem;
            flex-wrap: wrap;
            margin-bottom: 1rem;
        }

        .structure-stats .stat-item {
            text-align: center;
        }

        .structure-stats .stat-value {
            display: block;
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-primary);
        }

        .structure-stats .stat-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        .tree-container {
            max-height: 400px;
            overflow-y: auto;
            background: var(--bg-light);
            padding: 1rem;
            border-radius: 0.5rem;
        }

        .tree-container ul {
            list-style: none;
            padding-left: 1.5rem;
            margin: 0;
        }

        .tree-container > ul {
            padding-left: 0;
        }

        .tree-container li {
            margin: 0.25rem 0;
        }

        .tree-container details > summary {
            cursor: pointer;
        }

        .tag {
            display: inline-block;
            padding: 0.125rem 0.5rem;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.875rem;
            background: var(--bg-tag);
        }

        .tag-heading {
            background: var(--bg-info);
            color: var(--text-info);
        }

        .tag.has-issues {
            background: var(--bg-error);
        }

        .tag-preview {
            color: var(--text-secondary);
            font-style: italic;
            font-size: 0.8125rem;
        }

        .tag-alt {
            color: var(--text-success);
            font-size: 0.8125rem;
        }

        .tag-warning {
            color: var(--color-warn);
        }

        .validation-issues {
            background: var(--bg-warning);
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }

        .validation-issues h4 {
            margin: 0 0 0.5rem 0;
            color: var(--text-warning);
        }

        .validation-issues ul {
            margin: 0;
            padding-left: 1.5rem;
        }

        .no-structure-warning {
            background: var(--bg-error);
            padding: 1rem;
            border-radius: 0.5rem;
            color: var(--text-error);
        }

        /* Content audit */
        .audit-subsection {
            margin-bottom: 1.5rem;
        }

        .audit-subsection h3 {
            font-size: 1.125rem;
            margin-bottom: 0.5rem;
        }

        .audit-summary {
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            font-size: 0.875rem;
        }

        .audit-table {
            font-size: 0.875rem;
        }

        .audit-table th {
            background: var(--bg-light);
        }

        /* Zebra stripes for all tables */
        .audit-table tbody tr:nth-child(even),
        .table tbody tr:nth-child(even),
        table.striped tbody tr:nth-child(even) {
            background: var(--bg-light);
        }

        /* Page groups in image audit table */
        .image-audit-table .page-group-header {
            background: var(--bg-neutral-dark);
            font-weight: 600;
            font-size: 0.9rem;
        }

        .image-audit-table .page-group-header td {
            padding: 0.75rem 1rem;
            border-bottom: 2px solid var(--border-color);
        }

        .image-audit-table .page-group-header a {
            color: var(--text-primary);
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        .image-audit-table .page-group-header a:hover {
            color: var(--color-pass);
        }

        .image-audit-table .page-group-header .external-link-icon {
            font-size: 0.75rem;
            opacity: 0.6;
        }

        /* Image thumbnails in audit - 10% larger */
        .image-audit-table .thumbnail-cell {
            width: 90px;
            padding: 0.5rem;
        }

        .image-thumbnail {
            max-width: 80px;
            max-height: 80px;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            object-fit: contain;
            background: var(--bg-neutral-dark);
        }

        .no-preview {
            display: inline-block;
            width: 80px;
            height: 55px;
            background: var(--bg-light);
            border-radius: 4px;
            text-align: center;
            line-height: 55px;
            font-size: 0.7rem;
            color: var(--text-secondary);
        }

        /* Image audit filters */
        .image-filters {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 1rem;
            padding: 0.75rem 1rem;
            background: var(--bg-light);
            border-radius: 6px;
            align-items: center;
        }

        .image-filters label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .image-filters select {
            padding: 0.4rem 0.6rem;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            font-size: 0.85rem;
            background: var(--bg-white);
            color: var(--text-primary);
        }

        .image-filters .filter-count {
            margin-left: auto;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        .image-audit-table tr.filtered-out {
            display: none;
        }

        .image-audit-table .page-group-header.filtered-out {
            display: none;
        }

        .image-filters select option:disabled {
            color: var(--text-muted, #9ca3af);
            font-style: italic;
        }

        .image-filters select.filter-active {
            border-color: var(--color-pass);
            background-color: #f0fdf4;
        }

        .filter-reset {
            padding: 0.4rem 0.8rem;
            font-size: 0.8rem;
            background: transparent;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            color: var(--text-secondary);
            cursor: pointer;
            margin-left: 0.5rem;
        }

        .filter-reset:hover {
            background: var(--bg-light);
            color: var(--text-primary);
        }

        .filter-reset:focus {
            outline: 2px solid var(--color-primary, #3b82f6);
            outline-offset: 2px;
        }

        .missing {
            color: var(--color-fail);
            font-weight: 500;
        }

        .decorative {
            color: var(--text-secondary);
            font-style: italic;
        }

        /* Text Layer Analysis - Tabbed Interface */
        .text-layer-analysis {
            display: flex;
            gap: 1rem;
            margin-top: 1.5rem;
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            overflow: hidden;
        }

        .page-tabs.vertical {
            display: flex;
            flex-direction: column;
            min-width: 100px;
            max-width: 120px;
            background: var(--bg-light);
            border-right: 1px solid var(--border-color);
            max-height: 600px;  /* Increased from 400px to fit ~20 pages */
            overflow-y: auto;
        }

        .page-tabs .tab {
            padding: 0.75rem 1rem;
            text-align: left;
            border: none;
            background: none;
            cursor: pointer;
            font-size: 0.875rem;
            color: var(--text-secondary);
            transition: all 0.15s ease;
            border-left: 3px solid transparent;
        }

        .page-tabs .tab:hover {
            background: rgba(0,0,0,0.05);
        }

        .page-tabs .tab.active {
            background: var(--bg-white);
            color: var(--text-primary);
            font-weight: 500;
            border-left-color: var(--color-pass);
        }

        .page-tabs .tab.warning {
            color: var(--color-warn);
        }

        .page-tabs .tab.warning.active {
            border-left-color: var(--color-warn);
        }

        /* Page navigation container with arrows */
        .page-nav-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            min-width: 100px;
            max-width: 120px;
            background: var(--bg-light);
            border-right: 1px solid var(--border-color);
        }

        .nav-arrow {
            width: 100%;
            padding: 0.5rem;
            border: none;
            background: var(--bg-light);
            color: var(--text-secondary);
            font-size: 1.25rem;
            cursor: pointer;
            transition: all 0.15s ease;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .nav-arrow:hover {
            background: var(--border-color);
            color: var(--text-primary);
        }

        .nav-arrow:disabled {
            opacity: 0.3;
            cursor: not-allowed;
        }

        .nav-arrow.prev {
            border-bottom: 1px solid var(--border-color);
        }

        .nav-arrow.next {
            border-top: 1px solid var(--border-color);
        }

        .page-nav-container .page-tabs.vertical {
            flex: 1;
            border-right: none;
        }

        .tab-content {
            flex: 1;
            padding: 1rem;
            overflow-y: auto;
            max-height: 600px;  /* Increased from 400px to fit ~20 pages */
        }

        .page-panel {
            display: none;
        }

        .page-panel.active {
            display: block;
        }

        .page-summary {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid var(--border-color);
        }

        .similarity {
            font-weight: 600;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.875rem;
        }

        .similarity-good {
            background: var(--bg-success);
            color: var(--text-success);
        }

        .similarity-warning {
            background: var(--bg-warning);
            color: var(--text-warning);
        }

        .similarity-poor {
            background: var(--bg-error);
            color: var(--text-error);
        }

        .char-counts {
            font-size: 0.8125rem;
            color: var(--text-secondary);
        }

        .text-comparison {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .text-column h4 {
            font-size: 0.8125rem;
            font-weight: 600;
            margin: 0 0 0.5rem 0;
            color: var(--text-secondary);
        }

        .text-column pre {
            background: var(--bg-light);
            padding: 0.75rem;
            border-radius: 0.375rem;
            font-size: 0.8125rem;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 200px;
            overflow-y: auto;
            margin: 0;
        }

        /* Diff highlighting */
        .diff-comparison {
            margin-top: 1rem;
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .diff-side h4 {
            font-size: 0.8125rem;
            margin: 0 0 0.5rem 0;
        }

        .diff-side pre {
            background: var(--bg-light);
            padding: 0.75rem;
            border-radius: 0.375rem;
            font-size: 0.8125rem;
            max-height: 150px;
            overflow-y: auto;
            margin: 0;
        }

        .diff-delete {
            background: var(--bg-error);
            color: var(--text-error);
            text-decoration: line-through;
        }

        .diff-insert {
            background: var(--bg-success);
            color: var(--text-success);
        }

        .diff-replace {
            background: var(--bg-warning);
            color: var(--text-warning);
        }

        /* Remediation roadmap */
        .remediation-summary {
            display: flex;
            gap: 2rem;
            margin-bottom: 1.5rem;
            flex-wrap: wrap;
        }

        .remediation-summary .summary-stat {
            text-align: center;
            padding: 1rem 1.5rem;
            background: var(--bg-light);
            border-radius: 0.5rem;
        }

        .remediation-summary .stat-value {
            display: block;
            font-size: 1.5rem;
            font-weight: 700;
        }

        .remediation-summary .stat-label {
            font-size: 0.75rem;
            color: var(--text-secondary);
        }

        .priority-group {
            margin-bottom: 1.5rem;
        }

        .priority-group h3 {
            font-size: 1rem;
            margin-bottom: 0.75rem;
            padding-bottom: 0.5rem;
            border-bottom: 2px solid var(--border-color);
        }

        .priority-group.critical h3 { border-color: var(--color-critical); }
        .priority-group.high h3 { border-color: var(--color-serious); }
        .priority-group.medium h3 { border-color: var(--color-warn); }
        .priority-group.low h3 { border-color: var(--color-minor); }

        .task-card {
            background: var(--bg-light);
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 0.75rem;
        }

        .task-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.5rem;
        }

        .task-title {
            font-weight: 600;
        }

        .task-effort {
            font-size: 0.75rem;
            padding: 0.125rem 0.5rem;
            background: var(--bg-white);
            border-radius: 4px;
            color: var(--text-secondary);
        }

        .task-description {
            margin: 0 0 0.5rem 0;
            color: var(--text-secondary);
            font-size: 0.875rem;
        }

        .task-meta {
            display: flex;
            gap: 1rem;
            font-size: 0.75rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
        }

        .task-wcag {
            display: flex;
            gap: 0.25rem;
            flex-wrap: wrap;
        }

        .wcag-badge {
            font-size: 0.6875rem;
            padding: 0.125rem 0.375rem;
            background: var(--bg-info);
            color: var(--text-info);
            border-radius: 4px;
        }

        .task-steps {
            margin-top: 0.5rem;
        }

        .task-steps summary {
            cursor: pointer;
            font-size: 0.875rem;
            color: var(--color-minor);
        }

        .task-steps ol {
            margin: 0.5rem 0 0 0;
            padding-left: 1.5rem;
            font-size: 0.8125rem;
        }

        .task-note {
            margin: 0.5rem 0 0 0;
            font-size: 0.8125rem;
            color: var(--text-secondary);
            font-style: italic;
        }

        .no-tasks {
            color: var(--text-success);
            font-weight: 500;
        }

        /* Text diff styles */
        .diff-comparison {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1rem;
        }

        .diff-side {
            background: var(--bg-light);
            padding: 1rem;
            border-radius: 0.5rem;
        }

        .diff-side h4 {
            margin: 0 0 0.5rem 0;
            font-size: 0.875rem;
        }

        .diff-side pre {
            margin: 0;
            white-space: pre-wrap;
            word-break: break-word;
            font-size: 0.8125rem;
        }

        .diff-delete {
            background: var(--bg-error);
            text-decoration: line-through;
        }

        .diff-insert {
            background: var(--bg-success);
        }

        .diff-replace {
            background: var(--bg-warning);
        }

        /* Page size display */
        .page-size-display {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .page-size-icon {
            display: inline-flex;
            align-items: center;
        }

        .page-size-info {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
        }

        .orientation-badge {
            font-size: 0.75rem;
            padding: 0.125rem 0.5rem;
            border-radius: 9999px;
            font-weight: 500;
        }

        .orientation-portrait {
            background: var(--bg-info-code);
            color: var(--text-info);
        }

        .orientation-landscape {
            background: var(--bg-warning);
            color: var(--text-serious);
        }

        /* Creator icons */
        .creator-with-icon {
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
        }

        .creator-with-icon svg {
            vertical-align: middle;
            flex-shrink: 0;
        }

        .creator-detail {
            font-size: 0.8125rem;
            color: var(--text-secondary);
        }

        /* Language verification */
        .lang-verified {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
        }

        .lang-check {
            color: var(--color-pass);
            font-weight: bold;
        }

        .lang-mismatch {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
        }

        .lang-warning {
            color: var(--color-warn);
        }

        .lang-detected {
            display: block;
            font-size: 0.8125rem;
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }

        /* Link audit table */
        .link-audit-table {
            table-layout: fixed;
        }

        /* Link audit table with consolidated columns */
        .link-audit-table th:nth-child(1) { width: 60px; }   /* Page */
        .link-audit-table th:nth-child(2) { width: auto; }   /* Link (combined text + destination) */
        .link-audit-table th:nth-child(3) { width: 80px; }   /* Type */
        .link-audit-table th:nth-child(4) { width: 60px; }   /* Status */

        .link-text-cell {
            max-width: 200px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .link-dest-cell {
            max-width: 250px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .link-destination {
            color: var(--color-minor);
            text-decoration: none;
            font-size: 0.8125rem;
        }

        .link-destination:hover {
            text-decoration: underline;
        }

        .link-internal {
            color: var(--text-secondary);
            font-size: 0.8125rem;
            font-style: italic;
        }

        /* Consolidated link cell with text and destination stacked */
        .link-combined-cell {
            display: flex;
            flex-direction: column;
            gap: 0.125rem;
            max-width: 400px;
        }

        .link-text {
            font-weight: 500;
            color: var(--text-primary);
        }

        .link-url {
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-decoration: none;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .link-url:hover {
            text-decoration: underline;
            color: var(--color-moderate);
        }

        /* Clickable page link in audit tables */
        .page-link {
            color: var(--color-moderate);
            text-decoration: none;
            font-weight: 500;
        }

        .page-link:hover {
            text-decoration: underline;
        }

        .link-destination-text {
            color: var(--text-secondary);
            font-size: 0.8125rem;
        }

        .link-no-dest {
            color: var(--text-secondary);
        }

        /* Lightbox styles - arrows positioned outside content */
        .lightbox-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0, 0, 0, 0.92);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
            opacity: 0;
            visibility: hidden;
            transition: opacity 0.2s ease, visibility 0.2s ease;
        }

        .lightbox-overlay.active {
            opacity: 1;
            visibility: visible;
        }

        .lightbox-content {
            position: relative;
            max-width: calc(100vw - 160px);
            max-height: 90vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }

        .lightbox-image {
            max-width: 100%;
            max-height: 80vh;
            object-fit: contain;
            border-radius: 4px;
            box-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
        }

        .lightbox-caption {
            color: white;
            font-size: 0.875rem;
            margin-top: 1rem;
            text-align: center;
            max-width: 600px;
        }

        .lightbox-close {
            position: fixed;
            top: 20px;
            right: 20px;
            width: 44px;
            height: 44px;
            background: rgba(255, 255, 255, 0.15);
            border: none;
            border-radius: 50%;
            color: white;
            font-size: 28px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            z-index: 10001;
        }

        .lightbox-close:hover {
            background: rgba(255, 255, 255, 0.25);
            transform: scale(1.05);
        }

        /* Navigation arrows positioned at screen edges */
        .lightbox-nav {
            position: fixed;
            top: 50%;
            transform: translateY(-50%);
            width: 56px;
            height: 56px;
            background: rgba(255, 255, 255, 0.1);
            border: none;
            border-radius: 50%;
            color: white;
            font-size: 28px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s ease;
            z-index: 10001;
        }

        .lightbox-nav:hover {
            background: rgba(255, 255, 255, 0.2);
            transform: translateY(-50%) scale(1.05);
        }

        .lightbox-nav:disabled {
            opacity: 0.2;
            cursor: not-allowed;
        }

        .lightbox-nav:disabled:hover {
            transform: translateY(-50%);
            background: rgba(255, 255, 255, 0.1);
        }

        .lightbox-prev {
            left: 24px;
        }

        .lightbox-next {
            right: 24px;
        }

        .lightbox-counter {
            color: rgba(255, 255, 255, 0.7);
            font-size: 0.8rem;
            margin-top: 0.75rem;
        }

        @media (max-width: 768px) {
            .lightbox-content {
                max-width: calc(100vw - 100px);
            }
            .lightbox-nav {
                width: 44px;
                height: 44px;
                font-size: 22px;
            }
            .lightbox-prev {
                left: 12px;
            }
            .lightbox-next {
                right: 12px;
            }
        }

        /* Print styles */
        @media print {
            .collapsible.collapsed .section-content { display: block; }
            .section-header::before { display: none; }
            .tree-container { max-height: none; }
            .lightbox-overlay { display: none !important; }
        }
    """


def _get_interactive_js() -> str:
    """Return JavaScript for interactive features."""
    return """
    <script>
        // Collapsible sections
        document.querySelectorAll('.collapsible .section-header').forEach(header => {
            header.addEventListener('click', () => {
                header.closest('.collapsible').classList.toggle('collapsed');
            });
        });

        // Filter by severity (if filter controls exist)
        window.filterBySeverity = function(severity) {
            document.querySelectorAll('.issue-card, .task-card').forEach(card => {
                if (severity === 'all') {
                    card.style.display = '';
                } else {
                    card.style.display = card.dataset.severity === severity ? '' : 'none';
                }
            });
        };

        // Filter checks table to show only failed checks
        window.filterChecks = function(showFailedOnly) {
            document.querySelectorAll('.checks-table tbody tr').forEach(row => {
                if (showFailedOnly) {
                    row.style.display = row.classList.contains('status-fail') ? '' : 'none';
                } else {
                    row.style.display = '';
                }
            });
        };

        // Jump to page
        window.jumpToPage = function(pageNum) {
            const el = document.querySelector('[data-page="' + pageNum + '"]');
            if (el) el.scrollIntoView({ behavior: 'smooth' });
        };

        // Expand/collapse all
        window.expandAll = function() {
            document.querySelectorAll('.collapsible').forEach(s => s.classList.remove('collapsed'));
        };
        window.collapseAll = function() {
            document.querySelectorAll('.collapsible').forEach(s => s.classList.add('collapsed'));
        };

        // Page tabs for text layer analysis
        document.querySelectorAll('.page-tabs .tab').forEach(tab => {
            tab.addEventListener('click', () => {
                const container = tab.closest('.text-layer-analysis');
                const pageNum = tab.dataset.page;

                // Deactivate all tabs and panels
                container.querySelectorAll('.tab').forEach(t => {
                    t.classList.remove('active');
                    t.setAttribute('aria-selected', 'false');
                });
                container.querySelectorAll('.page-panel').forEach(p => {
                    p.classList.remove('active');
                });

                // Activate selected tab and panel
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');
                const panel = container.querySelector('.page-panel[data-page="' + pageNum + '"]');
                if (panel) panel.classList.add('active');
            });
        });

        // Navigate between pages using arrow buttons
        window.navigatePage = function(direction) {
            const container = document.querySelector('.text-layer-analysis');
            if (!container) return;

            const tabs = Array.from(container.querySelectorAll('.page-tabs .tab'));
            const activeTab = container.querySelector('.page-tabs .tab.active');
            if (!activeTab || tabs.length === 0) return;

            const currentIndex = tabs.indexOf(activeTab);
            const newIndex = currentIndex + direction;

            // Check bounds
            if (newIndex >= 0 && newIndex < tabs.length) {
                tabs[newIndex].click();
                // Scroll the new tab into view
                tabs[newIndex].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        };

        // Image audit table filter functionality
        window.filterImageTable = function() {
            const table = document.querySelector('.image-audit-table');
            if (!table) return;

            const rows = Array.from(table.querySelectorAll('tbody tr:not(.page-group-header)'));
            const pageHeaders = table.querySelectorAll('tbody tr.page-group-header');

            const categorySelect = document.getElementById('filter-category');
            const altSelect = document.getElementById('filter-alt');
            const statusSelect = document.getElementById('filter-status');

            const categoryFilter = categorySelect?.value || 'all';
            const altFilter = altSelect?.value || 'all';
            const statusFilter = statusSelect?.value || 'all';

            // Helper to count matches for a given filter combination
            function countMatches(rows, categoryVal, altVal, statusVal) {
                return rows.filter(row => {
                    const catMatch = categoryVal === 'all' || row.dataset.category === categoryVal;
                    const altMatch = altVal === 'all' || row.dataset.altStatus === altVal;
                    const statusMatch = statusVal === 'all' || row.dataset.status === statusVal;
                    return catMatch && altMatch && statusMatch;
                }).length;
            }

            // Update select options with counts (given other active filters)
            function updateSelectCounts(select, filterType) {
                if (!select) return;
                Array.from(select.options).forEach(opt => {
                    // Store original label if not already stored
                    const baseLabel = opt.dataset.baseLabel || opt.textContent.replace(/\\s*\\(\\d+\\)$/, '');
                    opt.dataset.baseLabel = baseLabel;

                    let count;
                    if (filterType === 'category') {
                        count = countMatches(rows, opt.value, altFilter, statusFilter);
                    } else if (filterType === 'alt') {
                        count = countMatches(rows, categoryFilter, opt.value, statusFilter);
                    } else if (filterType === 'status') {
                        count = countMatches(rows, categoryFilter, altFilter, opt.value);
                    }

                    opt.textContent = `${baseLabel} (${count})`;
                    // Only disable non-"all" options with zero matches
                    opt.disabled = opt.value !== 'all' && count === 0;
                });

                // Add/remove active filter class
                if (select.value !== 'all') {
                    select.classList.add('filter-active');
                } else {
                    select.classList.remove('filter-active');
                }
            }

            // Update all select option counts
            updateSelectCounts(categorySelect, 'category');
            updateSelectCounts(altSelect, 'alt');
            updateSelectCounts(statusSelect, 'status');

            // Apply filters to rows
            let visibleCount = 0;
            const pagesWithVisible = new Set();

            rows.forEach(row => {
                const categoryMatch = categoryFilter === 'all' || row.dataset.category === categoryFilter;
                const altMatch = altFilter === 'all' || row.dataset.altStatus === altFilter;
                const statusMatch = statusFilter === 'all' || row.dataset.status === statusFilter;

                if (categoryMatch && altMatch && statusMatch) {
                    row.classList.remove('filtered-out');
                    visibleCount++;
                    pagesWithVisible.add(row.dataset.page);
                } else {
                    row.classList.add('filtered-out');
                }
            });

            // Show/hide page headers based on whether they have visible images
            pageHeaders.forEach(header => {
                if (pagesWithVisible.has(header.dataset.page)) {
                    header.classList.remove('filtered-out');
                } else {
                    header.classList.add('filtered-out');
                }
            });

            // Update count display
            const countEl = document.getElementById('filter-count');
            if (countEl) {
                const total = rows.length;
                if (visibleCount === 0) {
                    countEl.textContent = 'No images match the current filters';
                } else if (visibleCount === total) {
                    const imageWord = total === 1 ? 'image' : 'images';
                    countEl.textContent = `Showing all ${total} ${imageWord}`;
                } else {
                    const imageWord = visibleCount === 1 ? 'image' : 'images';
                    countEl.textContent = `Showing ${visibleCount} of ${total} ${imageWord}`;
                }
            }
        };

        // Reset all image filters to default
        window.resetImageFilters = function() {
            const categorySelect = document.getElementById('filter-category');
            const altSelect = document.getElementById('filter-alt');
            const statusSelect = document.getElementById('filter-status');

            if (categorySelect) categorySelect.value = 'all';
            if (altSelect) altSelect.value = 'all';
            if (statusSelect) statusSelect.value = 'all';

            filterImageTable();
        };

        // Initialize filter counts on page load
        document.addEventListener('DOMContentLoaded', function() {
            if (document.querySelector('.image-audit-table')) {
                filterImageTable();
            }
        });

        // Lightbox functionality
        (function() {
            // Create lightbox DOM structure - nav buttons outside content for fixed positioning
            const overlay = document.createElement('div');
            overlay.className = 'lightbox-overlay';
            overlay.innerHTML = `
                <button class="lightbox-close" aria-label="Close lightbox">&times;</button>
                <button class="lightbox-nav lightbox-prev" aria-label="Previous image">&#8249;</button>
                <button class="lightbox-nav lightbox-next" aria-label="Next image">&#8250;</button>
                <div class="lightbox-content">
                    <img class="lightbox-image" src="" alt="">
                    <div class="lightbox-caption"></div>
                    <div class="lightbox-counter"></div>
                </div>
            `;
            document.body.appendChild(overlay);

            const lightboxImage = overlay.querySelector('.lightbox-image');
            const lightboxCaption = overlay.querySelector('.lightbox-caption');
            const lightboxCounter = overlay.querySelector('.lightbox-counter');
            const prevBtn = overlay.querySelector('.lightbox-prev');
            const nextBtn = overlay.querySelector('.lightbox-next');
            const closeBtn = overlay.querySelector('.lightbox-close');

            let currentGroup = [];
            let currentIndex = 0;

            function openLightbox(trigger) {
                const src = trigger.dataset.lightboxSrc;
                const group = trigger.dataset.lightboxGroup;

                // Find all images in the same group
                if (group) {
                    currentGroup = Array.from(document.querySelectorAll(`[data-lightbox-group="${group}"]`));
                    currentIndex = currentGroup.indexOf(trigger);
                } else {
                    currentGroup = [trigger];
                    currentIndex = 0;
                }

                updateLightbox();
                overlay.classList.add('active');
                document.body.style.overflow = 'hidden';
            }

            function updateLightbox() {
                const trigger = currentGroup[currentIndex];
                const src = trigger.dataset.lightboxSrc;
                const caption = trigger.dataset.lightboxCaption || '';
                const alt = trigger.alt || trigger.querySelector('img')?.alt || 'Image';

                lightboxImage.src = src;
                lightboxImage.alt = alt;

                // Update caption
                if (caption) {
                    lightboxCaption.textContent = caption;
                    lightboxCaption.style.display = 'block';
                } else {
                    lightboxCaption.style.display = 'none';
                }

                // Update counter and nav buttons
                if (currentGroup.length > 1) {
                    lightboxCounter.textContent = `${currentIndex + 1} / ${currentGroup.length}`;
                    lightboxCounter.style.display = 'block';
                    prevBtn.style.display = 'flex';
                    nextBtn.style.display = 'flex';
                    // Disable buttons at boundaries (optional - or keep wrap-around)
                    prevBtn.disabled = false;
                    nextBtn.disabled = false;
                } else {
                    lightboxCounter.style.display = 'none';
                    prevBtn.style.display = 'none';
                    nextBtn.style.display = 'none';
                }
            }

            function closeLightbox() {
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }

            function showPrev() {
                if (currentGroup.length > 1) {
                    currentIndex = (currentIndex - 1 + currentGroup.length) % currentGroup.length;
                    updateLightbox();
                }
            }

            function showNext() {
                if (currentGroup.length > 1) {
                    currentIndex = (currentIndex + 1) % currentGroup.length;
                    updateLightbox();
                }
            }

            // Event listeners for triggers
            document.querySelectorAll('.lightbox-trigger').forEach(trigger => {
                trigger.addEventListener('click', () => openLightbox(trigger));
            });

            // Close button
            closeBtn.addEventListener('click', closeLightbox);

            // Click outside to close
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) closeLightbox();
            });

            // Navigation buttons
            prevBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                showPrev();
            });
            nextBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                showNext();
            });

            // Keyboard navigation
            document.addEventListener('keydown', (e) => {
                if (!overlay.classList.contains('active')) return;

                switch (e.key) {
                    case 'Escape':
                        closeLightbox();
                        break;
                    case 'ArrowLeft':
                        showPrev();
                        break;
                    case 'ArrowRight':
                        showNext();
                        break;
                }
            });
        })();
    </script>
    """


def _generate_simple_section(result: "PDFFullResult") -> str:
    """Generate the SimplePDFChecker results section for the HTML report."""
    if not result.simple:
        return ""

    simple = result.simple
    checks = simple.checks

    # Build check rows using helper function
    check_rows = [_render_check_row(check) for check in checks]

    # Build additional info section
    additional_info = []
    meta = simple.metadata

    if meta.form_field_count > 0:
        additional_info.append(f"<dt>Form Fields</dt><dd>{meta.form_field_count}</dd>")
    if meta.has_xfa:
        additional_info.append('<dt>XFA Forms</dt><dd><span style="color: var(--color-warn);">Yes (accessibility barrier)</span></dd>')
    if meta.has_xmp:
        additional_info.append("<dt>XMP Metadata</dt><dd>Yes</dd>")
    if meta.language_display_name:
        additional_info.append(f"<dt>Language</dt><dd>{_escape_html(meta.language)} ({_escape_html(meta.language_display_name)})</dd>")

    additional_info_html = ""
    if additional_info:
        additional_info_html = f"""
        <dl class="simple-meta">
            {''.join(additional_info)}
        </dl>
        """

    # Totally inaccessible warning
    inaccessible_warning = ""
    if simple.is_totally_inaccessible:
        inaccessible_warning = """
        <div class="totally-inaccessible-warning">
            <strong>⚠ Document is totally inaccessible</strong>
            <p style="margin: 0.5rem 0 0 0;">This document is either a scanned image, protected against assistive technology, or untagged.</p>
        </div>
        """

    return f"""
        <section class="simple-checks">
            <h2>Simple Accessibility Checks ({len(checks)} checks)</h2>
            <p style="color: var(--text-secondary); margin-bottom: 1rem;">
                Based on Luxembourg simplA11yPDFCrawler methodology
            </p>
            {inaccessible_warning}
            <div class="summary-grid" style="margin-bottom: 1rem;">
                <div class="summary-item passed">
                    <span class="summary-count">{simple.passed}</span>
                    <span class="summary-label">Passed</span>
                </div>
                <div class="summary-item failed">
                    <span class="summary-count">{simple.failed}</span>
                    <span class="summary-label">Failed</span>
                </div>
                {f'''<div class="summary-item warnings">
                    <span class="summary-count">{simple.warnings}</span>
                    <span class="summary-label">Warnings</span>
                </div>''' if simple.warnings > 0 else ''}
            </div>
            {additional_info_html}
            <table>
                <thead>
                    <tr>
                        <th>Check</th>
                        <th>Status</th>
                        <th>Severity</th>
                        <th>Details</th>
                        <th>WCAG</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(check_rows)}
                </tbody>
            </table>
        </section>
    """


# =============================================================================
# Template-Based Report Generation (New API)
# =============================================================================


def generate_report_data_from_result(
    pdf_path: Path | str,
    result: "PDFFullResult",
    config: dict | None = None,
) -> "PDFReportData":
    """
    Generate structured report data from PDF check results.

    This is the first step in the two-step report generation process:
    1. Generate data (this function) - can be saved as JSON
    2. Render to HTML (render_html_from_data)

    Args:
        pdf_path: Path to the PDF file
        result: PDFFullResult from the checker
        config: Optional configuration dict

    Returns:
        PDFReportData instance ready for JSON export or HTML rendering
    """
    from inspekt.services.pdf_report_generator import generate_report_data

    return generate_report_data(pdf_path, result, config)


def generate_json_report(
    pdf_path: Path | str,
    result: "PDFFullResult",
    output_path: Path | str | None = None,
    config: dict | None = None,
    indent: int = 2,
) -> str:
    """
    Generate a JSON accessibility report.

    The JSON contains all the data needed to render an HTML report later.
    This enables:
    - Caching report data
    - Generating HTML from saved JSON
    - API responses with raw data
    - Custom report formats

    Args:
        pdf_path: Path to the PDF file
        result: PDFFullResult from the checker
        output_path: Optional path to save the JSON file
        config: Optional configuration dict
        indent: JSON indentation (default 2)

    Returns:
        JSON string

    Example:
        >>> json_str = generate_json_report(pdf_path, result)
        >>> html_str = render_html_from_json_string(json_str)
    """
    from inspekt.services.pdf_report_generator import generate_report_data
    from inspekt.services.pdf_report_renderer import export_json_report

    report_data = generate_report_data(pdf_path, result, config)
    return export_json_report(report_data, output_path, indent)


def render_html_from_data(
    report_data: "PDFReportData",
    output_path: Path | str | None = None,
) -> str:
    """
    Render HTML report from structured data.

    Args:
        report_data: PDFReportData instance
        output_path: Optional path to save the HTML file

    Returns:
        HTML string
    """
    from inspekt.services.pdf_report_renderer import render_html_report

    html_content = render_html_report(report_data)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding="utf-8")

    return html_content


def render_html_from_json_file(
    json_path: Path | str,
    output_path: Path | str | None = None,
) -> str:
    """
    Render HTML report from a JSON file.

    This is the key function for generating HTML from saved JSON data.

    Args:
        json_path: Path to the JSON report file
        output_path: Optional path to save the HTML file

    Returns:
        HTML string
    """
    from inspekt.services.pdf_report_renderer import render_html_from_json

    html_content = render_html_from_json(json_path)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding="utf-8")

    return html_content


def render_html_from_json_string(json_str: str) -> str:
    """
    Render HTML report from a JSON string.

    Args:
        json_str: JSON string containing report data

    Returns:
        HTML string
    """
    from inspekt.services.pdf_report_renderer import render_html_from_json_string as _render

    return _render(json_str)


def generate_template_based_report(
    pdf_path: Path | str,
    result: "PDFFullResult",
    output_path: Path | str | None = None,
    json_output_path: Path | str | None = None,
    config: dict | None = None,
) -> tuple[str, str | None]:
    """
    Generate both HTML and optionally JSON reports using the template system.

    This is the recommended function for new code. It uses:
    1. PDFReportData for structured data
    2. Jinja2 templates for HTML rendering
    3. Optional JSON export for data persistence

    Args:
        pdf_path: Path to the PDF file
        result: PDFFullResult from the checker
        output_path: Optional path to save the HTML file
        json_output_path: Optional path to save the JSON file
        config: Optional configuration dict

    Returns:
        Tuple of (html_string, json_string or None)

    Example:
        >>> html, json_data = generate_template_based_report(
        ...     pdf_path, result,
        ...     output_path="report.html",
        ...     json_output_path="report.json"
        ... )
    """
    from inspekt.services.pdf_report_generator import generate_report_data
    from inspekt.services.pdf_report_renderer import render_html_report, export_json_report

    # Generate structured data
    report_data = generate_report_data(pdf_path, result, config)

    # Render HTML
    html_content = render_html_report(report_data)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html_content, encoding="utf-8")

    # Export JSON if requested
    json_content = None
    if json_output_path:
        json_content = export_json_report(report_data, json_output_path)

    return html_content, json_content
