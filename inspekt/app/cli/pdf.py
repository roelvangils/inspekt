"""
PDF Accessibility Checker CLI Commands.

This module provides commands for checking PDF accessibility:
- pdf check: Run accessibility checks on PDF files

These commands help identify PDF/UA compliance issues and WCAG violations
in PDF documents.
"""

from __future__ import annotations

import json
import sys
import time
from glob import glob
from pathlib import Path
from typing import TYPE_CHECKING

import click

from inspekt.app.cli.icons import get_icon, get_indicator
from inspekt.app.cli.inspection import _print_tips_section
from inspekt.app.cli.output import pluralize
from inspekt.app.cli.table import Table, format_status_icon, print_checkbox_step, print_error, print_hint, print_step, print_success, print_warning

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import PDFBasicResult, PDFFullResult, VeraPDFResult
    from inspekt.services.simple_pdf_checker import SimplePDFResult


# ============================================================================
# Formatting Helpers
# ============================================================================


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable form."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"


def _get_severity_color(severity: str) -> str:
    """Get the color for a severity level."""
    colors = {
        "critical": "red",
        "serious": "yellow",
        "moderate": "cyan",
        "minor": "blue",
    }
    return colors.get(severity, "white")


def _format_status(status: str) -> str:
    """Format a check status with icon and color."""
    if status == "pass":
        return format_status_icon("pass") + " " + click.style("pass", fg="green")
    elif status == "fail":
        return format_status_icon("fail") + " " + click.style("fail", fg="red")
    elif status == "warn":
        return format_status_icon("warning") + " " + click.style("warn", fg="yellow")
    elif status == "skip":
        return format_status_icon("skip") + " " + click.style("skip", fg="bright_black")
    else:
        return status


def _format_wcag(sc: str | None, level: str | None) -> str:
    """Format WCAG success criterion reference."""
    if not sc:
        return "-"
    if level:
        return f"{sc} ({level})"
    return sc


# ============================================================================
# Output Formatters
# ============================================================================


def _print_basic_results(result: "PDFBasicResult", verbose: bool = False) -> None:
    """Print basic check results in table format."""
    from inspekt.app.cli.icons import get_indicator

    # Document info summary
    meta = result.metadata
    file_info = f"{meta.file_path.name} ({_format_file_size(meta.file_size)}, {meta.page_count} {pluralize(meta.page_count, 'page')})"

    click.echo()

    # Build the results table
    table = Table(
        ["Check", "Status", "Details"],
        title="PDF Accessibility Check",
        icon=get_indicator("file"),
    )

    rows = []
    for check in result.checks:
        status_str = _format_status(check.status)
        rows.append([check.name, status_str, check.message])

    table.set_data(rows)
    table.print_header()

    for i, check in enumerate(result.checks):
        status_str = _format_status(check.status)

        # Color the check name by severity if it failed
        check_name = check.name
        if check.status == "fail":
            check_name = click.style(check.name, fg=_get_severity_color(check.severity))

        table.print_row([check_name, status_str, check.message])

    # Print summary row
    summary_parts = []
    if result.failed > 0:
        summary_parts.append(click.style(f"{result.failed} failed", fg="red"))
    if result.warnings > 0:
        summary_parts.append(click.style(f"{result.warnings} warning", fg="yellow"))
    if result.passed > 0:
        summary_parts.append(click.style(f"{result.passed} passed", fg="green"))
    if result.skipped > 0:
        summary_parts.append(click.style(f"{result.skipped} skipped", fg="bright_black"))

    table.print_summary([
        f"{len(result.checks)} checks",
        "",
        ", ".join(summary_parts),
    ])
    table.print_footer()

    # Print file info below the table
    click.echo()
    click.echo(f"  File: {file_info}")

    # Print severity breakdown if there are failures
    if result.failed > 0:
        severity_parts = []
        if result.critical_count > 0:
            severity_parts.append(click.style(f"Critical: {result.critical_count}", fg="red"))
        if result.serious_count > 0:
            severity_parts.append(click.style(f"Serious: {result.serious_count}", fg="yellow"))
        if result.moderate_count > 0:
            severity_parts.append(click.style(f"Moderate: {result.moderate_count}", fg="cyan"))
        if severity_parts:
            click.echo(f"  Severity: {', '.join(severity_parts)}")

    # Print metadata if verbose
    if verbose:
        click.echo()
        click.echo("  Metadata:")
        if meta.title:
            click.echo(f"    Title: {meta.title}")
        if meta.author:
            click.echo(f"    Author: {meta.author}")
        if meta.language:
            click.echo(f"    Language: {meta.language}")
        if meta.pdf_version:
            click.echo(f"    PDF Version: {meta.pdf_version}")
        if meta.creator:
            click.echo(f"    Creator: {meta.creator}")
        if meta.producer:
            click.echo(f"    Producer: {meta.producer}")


def _print_simple_results(result: "SimplePDFResult", verbose: bool = False) -> None:
    """Print SimplePDFChecker results in table format."""
    from inspekt.app.cli.icons import get_indicator

    # Document info summary
    meta = result.metadata
    file_info = f"{meta.file_path.name} ({_format_file_size(meta.file_size)}, {meta.page_count} {pluralize(meta.page_count, 'page')})"

    click.echo()

    # Build the results table
    table = Table(
        ["Check", "Status", "Details"],
        title=f"Simple PDF Accessibility Check ({len(result.checks)} checks)",
        icon=get_indicator("file"),
    )

    rows = []
    for check in result.checks:
        status_str = _format_status(check.status)
        rows.append([check.name, status_str, check.message])

    table.set_data(rows)
    table.print_header()

    for i, check in enumerate(result.checks):
        status_str = _format_status(check.status)

        # Color the check name by severity if it failed
        check_name = check.name
        if check.status == "fail":
            check_name = click.style(check.name, fg=_get_severity_color(check.severity))

        table.print_row([check_name, status_str, check.message])

    # Print summary row
    summary_parts = []
    if result.failed > 0:
        summary_parts.append(click.style(f"{result.failed} failed", fg="red"))
    if result.warnings > 0:
        summary_parts.append(click.style(f"{result.warnings} warning", fg="yellow"))
    if result.passed > 0:
        summary_parts.append(click.style(f"{result.passed} passed", fg="green"))
    if result.skipped > 0:
        summary_parts.append(click.style(f"{result.skipped} skipped", fg="bright_black"))

    table.print_summary([
        f"{len(result.checks)} checks",
        "",
        ", ".join(summary_parts),
    ])
    table.print_footer()

    # Print file info below the table
    click.echo()
    click.echo(f"  File: {file_info}")

    # Print "totally inaccessible" warning if applicable
    if result.is_totally_inaccessible:
        click.echo()
        # Determine which specific issue(s) caused this
        issues = []
        scanned = result.get_check("scanned")
        protected = result.get_check("protected")
        tagged = result.get_check("tagged")
        if scanned and scanned.status == "fail":
            issues.append("scanned image-only")
        if protected and protected.status == "fail":
            issues.append("protected against AT")
        if tagged and tagged.status == "fail":
            issues.append("untagged")

        click.echo(click.style("  ⚠ Document is totally inaccessible", fg="red", bold=True))
        if issues:
            click.echo(f"    Reason: {', '.join(issues)}")

    # Print severity breakdown if there are failures
    if result.failed > 0:
        severity_parts = []
        if result.critical_count > 0:
            severity_parts.append(click.style(f"Critical: {result.critical_count}", fg="red"))
        if result.serious_count > 0:
            severity_parts.append(click.style(f"Serious: {result.serious_count}", fg="yellow"))
        if result.moderate_count > 0:
            severity_parts.append(click.style(f"Moderate: {result.moderate_count}", fg="cyan"))
        if severity_parts:
            click.echo(f"  Severity: {', '.join(severity_parts)}")

    # Print metadata if verbose
    if verbose:
        click.echo()
        click.echo("  Metadata:")
        if meta.title:
            click.echo(f"    Title: {meta.title}")
        if meta.author:
            click.echo(f"    Author: {meta.author}")
        if meta.language:
            lang_display = f"{meta.language}"
            if meta.language_display_name:
                lang_display += f" ({meta.language_display_name})"
            click.echo(f"    Language: {lang_display}")
        if meta.pdf_version:
            click.echo(f"    PDF Version: {meta.pdf_version}")
        if meta.creator:
            click.echo(f"    Creator: {meta.creator}")
        if meta.producer:
            click.echo(f"    Producer: {meta.producer}")
        if meta.form_field_count > 0:
            click.echo(f"    Form Fields: {meta.form_field_count}")
        if meta.has_xfa:
            click.echo(click.style("    XFA Forms: Yes (accessibility barrier)", fg="yellow"))
        if meta.has_xmp:
            click.echo("    XMP Metadata: Yes")


def _print_verapdf_results(result: "VeraPDFResult", verbose: bool = False) -> None:
    """Print veraPDF validation results in table format."""
    from inspekt.app.cli.icons import get_indicator

    click.echo()

    # Compliance status
    if result.compliant:
        status_icon = format_status_icon("pass")
        status_text = click.style(f"PDF/{result.profile.upper()} Compliant", fg="green", bold=True)
    else:
        status_icon = format_status_icon("fail")
        status_text = click.style(f"PDF/{result.profile.upper()} Non-Compliant", fg="red", bold=True)

    click.echo(f"  {status_icon} {status_text}")
    click.echo(f"  Rules: {result.passed_rules} passed, {result.failed_rules} failed")

    if result.verapdf_version:
        click.echo(f"  veraPDF: v{result.verapdf_version}")
    if result.processing_time_ms:
        click.echo(f"  Time: {result.processing_time_ms}ms")

    # If there are violations, show them
    if result.violations:
        click.echo()

        # Build violations table
        table = Table(
            ["Rule", "Clause", "Description"],
            title=f"PDF/{result.profile.upper()} Violations ({len(result.violations)})",
            icon=get_indicator("alert"),
        )

        # For width calculation, use full descriptions
        rows = []
        for v in result.violations[:20]:  # Limit to first 20
            rows.append([v.rule_id, v.clause, v.description])

        table.set_data(rows)
        table.print_header()

        # Print rows with multi-line wrapping for description column
        for v in result.violations[:20]:
            table.print_row_multiline(
                [
                    click.style(v.rule_id, fg=_get_severity_color(v.severity)),
                    v.clause,
                    v.description,
                ],
                wrap_columns=[2],  # Wrap description column
                max_lines=3,
            )

        table.print_footer()

        if len(result.violations) > 20:
            click.echo(f"  … and {len(result.violations) - 20} more violations")

        if verbose:
            click.echo()
            click.echo("  Full violation details:")
            for i, v in enumerate(result.violations):
                click.echo()
                click.echo(f"  [{i + 1}] {v.rule_id}")
                click.echo(f"      Clause: {v.clause}")
                click.echo(f"      {v.description}")
                if v.context:
                    click.echo(f"      Context: {v.context}")


def _output_json(result: "PDFFullResult") -> None:
    """Output results as JSON."""
    output = {
        "basic": {
            "metadata": {
                "file_path": str(result.basic.metadata.file_path),
                "file_size": result.basic.metadata.file_size,
                "page_count": result.basic.metadata.page_count,
                "title": result.basic.metadata.title,
                "author": result.basic.metadata.author,
                "language": result.basic.metadata.language,
                "is_encrypted": result.basic.metadata.is_encrypted,
                "pdf_version": result.basic.metadata.pdf_version,
            },
            "summary": {
                "total": len(result.basic.checks),
                "passed": result.basic.passed,
                "failed": result.basic.failed,
                "warnings": result.basic.warnings,
                "skipped": result.basic.skipped,
            },
            "checks": [
                {
                    "id": c.check_id,
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "severity": c.severity,
                    "wcag_sc": c.wcag_sc,
                    "wcag_level": c.wcag_level,
                    "details": c.details,
                }
                for c in result.basic.checks
            ],
        },
    }

    if result.simple:
        output["simple"] = {
            "metadata": {
                "file_path": str(result.simple.metadata.file_path),
                "file_size": result.simple.metadata.file_size,
                "page_count": result.simple.metadata.page_count,
                "title": result.simple.metadata.title,
                "author": result.simple.metadata.author,
                "language": result.simple.metadata.language,
                "language_display_name": result.simple.metadata.language_display_name,
                "is_encrypted": result.simple.metadata.is_encrypted,
                "pdf_version": result.simple.metadata.pdf_version,
                "has_xmp": result.simple.metadata.has_xmp,
                "form_field_count": result.simple.metadata.form_field_count,
                "has_xfa": result.simple.metadata.has_xfa,
            },
            "summary": {
                "total": len(result.simple.checks),
                "passed": result.simple.passed,
                "failed": result.simple.failed,
                "warnings": result.simple.warnings,
                "skipped": result.simple.skipped,
                "is_totally_inaccessible": result.simple.is_totally_inaccessible,
            },
            "checks": [
                {
                    "id": c.check_id,
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "severity": c.severity,
                    "wcag_sc": c.wcag_sc,
                    "wcag_level": c.wcag_level,
                    "details": c.details,
                }
                for c in result.simple.checks
            ],
        }

    if result.verapdf:
        output["verapdf"] = {
            "profile": result.verapdf.profile,
            "compliant": result.verapdf.compliant,
            "passed_rules": result.verapdf.passed_rules,
            "failed_rules": result.verapdf.failed_rules,
            "total_violations": result.verapdf.total_violations,
            "verapdf_version": result.verapdf.verapdf_version,
            "processing_time_ms": result.verapdf.processing_time_ms,
            "violations": [
                {
                    "rule_id": v.rule_id,
                    "specification": v.specification,
                    "clause": v.clause,
                    "test_number": v.test_number,
                    "description": v.description,
                    "severity": v.severity,
                    "object_type": v.object_type,
                    "context": v.context,
                    "page_number": v.page_number,
                    "bbox": list(v.bbox) if v.bbox else None,
                    "location_path": v.location_path,
                }
                for v in result.verapdf.violations
            ],
        }

    click.echo(json.dumps(output, indent=2))


# ============================================================================
# CLI Commands
# ============================================================================


@click.group()
def pdf():
    """PDF accessibility checking tools.

    Check PDF documents for accessibility compliance using basic checks
    (pikepdf) and/or full PDF/UA validation (veraPDF via Docker).

    \b
    Examples:
        inspekt pdf check document.pdf                  # Basic checks
        inspekt pdf check document.pdf --engine vera    # veraPDF only
        inspekt pdf check document.pdf --engine all     # Both engines
        inspekt pdf check "*.pdf"                       # Multiple files
    """
    pass


@pdf.command("check")
@click.argument("files", nargs=-1, required=True)
@click.option(
    "--engine", "-e",
    type=click.Choice(["basic", "simple", "vera", "all"]),
    default="basic",
    help="Which checking engine to use (default: basic)",
)
@click.option(
    "--profile", "-p",
    type=click.Choice(["ua1", "ua2", "wtpdf"]),
    default="ua1",
    help="veraPDF validation profile (default: ua1)",
)
@click.option("--json", "json_output", is_flag=True, help="Output results as JSON")
@click.option("--output", "-o", "output_path", type=click.Path(), help="Save HTML report to file")
@click.option("--json-output", "json_output_path", type=click.Path(), help="Export report data as JSON (for later regeneration)")
@click.option("--json-only", "json_only", is_flag=True, help="Generate JSON data only, no HTML report")
@click.option("--pdfi", "pdfi_output_path", type=click.Path(), help="Export as self-contained .pdfi package (includes PDF, report, and preview images)")
@click.option("--open", "open_report", is_flag=True, help="Open HTML report in browser after generation")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
@click.option("--pull-vera", is_flag=True, help="Pull the veraPDF Docker image before running")
@click.option("--no-cover", is_flag=True, help="Disable cover page preview in HTML report")
@click.option("--no-screenshots", is_flag=True, help="Disable issue screenshots in HTML report")
@click.option("--no-ocr", is_flag=True, help="Disable OCR text layer comparison in HTML report")
@click.option("--ocr-all-pages", is_flag=True, help="Analyze ALL pages for text layer comparison (disables smart sampling, may be slow)")
@click.option("--ocr-lang", default="eng", help="Tesseract language code for OCR (default: eng)")
@click.option("--no-score", is_flag=True, help="Disable accessibility score in HTML report")
@click.option("--no-structure", is_flag=True, help="Disable structure tree visualization in HTML report")
@click.option("--no-content-audit", is_flag=True, help="Disable content audits (images, tables, forms, links) in HTML report")
@click.option("--no-remediation", is_flag=True, help="Disable remediation roadmap in HTML report")
@click.option("--wcag-level", type=click.Choice(["A", "AA", "AAA"]), default=None, help="Filter report by WCAG conformance level")
@click.option("--no-image-classification", is_flag=True, help="Disable local AI image categorization (photograph, chart, text-as-image, etc.)")
@click.option("--max-image-classification", type=int, default=100, help="Maximum images for classification (default: 100, 0=unlimited)")
@click.option("--generate-alt-text", is_flag=True, help="Generate AI alt-text suggestions for images missing alt text (requires API key)")
@click.option("--max-alt-text", type=int, default=10, help="Maximum images for AI alt-text generation (default: 10, 0=unlimited)")
@click.option("--ai-provider", type=click.Choice(["thoth", "anthropic", "openai"]), default=None, help="AI provider for vision analysis (default: thoth)")
@click.option("--show-tags", is_flag=True, help="[Deprecated] Static tag overlay images. Use Interactive Preview instead (enabled by default)")
@click.option("--tag-pages", type=str, default=None, help="[Deprecated] Pages for static tag visualization (e.g., '1,2,3' or '1-5')")
@click.option("--no-contrast", is_flag=True, help="Disable color contrast analysis (enabled by default)")
@click.option("--contrast-pages", type=str, default=None, help="Specific pages for contrast analysis (e.g., '1,2,3' or '1-5')")
@click.option("--contrast-dpi", type=int, default=200, help="Render resolution for contrast check (default: 200, higher=slower but more accurate)")
@click.option("--contrast-max-pages", type=int, default=5, help="Max pages for contrast analysis (default: 5, 0=all)")
@click.option("--contrast-max-issues", type=int, default=5, help="Max unique color issues per page (default: 5)")
@click.option("--no-interactive", is_flag=True, help="Disable interactive HTML preview with clickable tag regions")
@click.option("--interactive-pages", type=int, default=5, help="Number of pages for interactive preview (default: 5, 0=all)")
@click.option(
    "--embed-base64",
    is_flag=True,
    default=False,
    help="Embed images as BASE64 instead of saving as separate files (larger HTML, but self-contained)",
)
@click.option(
    "--structured-progress",
    is_flag=True,
    hidden=True,
    help="Emit JSON progress events to stderr (for desktop app integration)",
)
@click.pass_context
def check(ctx, files: tuple[str, ...], engine: str, profile: str, json_output: bool, output_path: str | None, json_output_path: str | None, json_only: bool, pdfi_output_path: str | None, open_report: bool, verbose: bool, pull_vera: bool, no_cover: bool, no_screenshots: bool, no_ocr: bool, ocr_all_pages: bool, ocr_lang: str, no_score: bool, no_structure: bool, no_content_audit: bool, no_remediation: bool, wcag_level: str | None, no_image_classification: bool, max_image_classification: int, generate_alt_text: bool, max_alt_text: int, ai_provider: str | None, show_tags: bool, tag_pages: str | None, no_contrast: bool, contrast_pages: str | None, contrast_dpi: int, contrast_max_pages: int, contrast_max_issues: int, no_interactive: bool, interactive_pages: int, embed_base64: bool, structured_progress: bool):
    """Check PDF files for accessibility issues.

    Runs accessibility checks on one or more PDF files. Supports glob patterns
    like "*.pdf" or "docs/*.pdf".

    \b
    Engines:
        basic   - Fast pikepdf-based checks (6 fundamental criteria)
        simple  - Luxembourg simplA11yPDFCrawler methodology (11 checks)
        vera    - Full PDF/UA validation via veraPDF
        all     - Run all engines (basic, simple, vera)

    \b
    veraPDF Profiles:
        ua1     - PDF/UA-1 (ISO 14289-1) - most common
        ua2     - PDF/UA-2 (ISO 14289-2) - newer standard
        wtpdf   - WTPDF 1.0 Accessibility

    \b
    Examples:
        inspekt pdf check document.pdf
        inspekt pdf check document.pdf --engine simple
        inspekt pdf check document.pdf --engine vera
        inspekt pdf check "reports/*.pdf" --json
    """
    from inspekt.services.pdf_checker import PDFBasicChecker, VeraPDFChecker, PDFFullResult

    # Initialize structured progress emitter if requested (for desktop app)
    emitter = None
    if structured_progress:
        from inspekt.services.structured_progress import StructuredProgressEmitter
        emitter = StructuredProgressEmitter()

    # Expand glob patterns
    all_files: list[Path] = []
    for pattern in files:
        if "*" in pattern or "?" in pattern:
            matches = glob(pattern, recursive=True)
            all_files.extend(Path(m) for m in matches if m.lower().endswith(".pdf"))
        else:
            all_files.append(Path(pattern))

    if not all_files:
        print_error("No PDF files found matching the given patterns")
        sys.exit(1)

    # Check for missing files
    missing = [f for f in all_files if not f.exists()]
    if missing:
        for f in missing:
            print_error(f"File not found: {f}")
        sys.exit(1)

    # Initialize checkers
    basic_checker = PDFBasicChecker()
    simple_checker = None
    vera_checker = None

    if engine in ("simple", "all"):
        from inspekt.services.simple_pdf_checker import SimplePDFChecker
        simple_checker = SimplePDFChecker()

    if engine in ("vera", "all"):
        vera_checker = VeraPDFChecker()

        # Check for native veraPDF first (preferred on Apple Silicon)
        if vera_checker.is_native_available():
            if not json_output:
                click.echo("Using native veraPDF installation")
        elif vera_checker.is_docker_available():
            # Fall back to Docker
            if pull_vera or not vera_checker.is_image_available():
                if not vera_checker.is_image_available():
                    click.echo(f"Pulling veraPDF Docker image ({VeraPDFChecker.DOCKER_IMAGE})...")
                elif pull_vera:
                    click.echo(f"Updating veraPDF Docker image...")

                if not vera_checker.pull_image(quiet=json_output):
                    print_error("Failed to pull veraPDF Docker image")
                    print_hint("Install veraPDF natively instead: `brew install verapdf`")
                    if engine == "vera":
                        sys.exit(1)
                    else:
                        print_warning("Falling back to basic checks only")
                        engine = "basic"
                        vera_checker = None
        elif vera_checker.is_docker_installed():
            # Docker is installed but not running
            print_error("Docker is installed but not running.")
            print_hint("Start Docker Desktop or run `open -a Docker` to start the Docker daemon.")
            print_hint("Or install veraPDF natively: `brew install verapdf` (recommended)")
            if engine == "vera":
                sys.exit(1)
            else:
                print_warning("Falling back to basic checks only")
                engine = "basic"
                vera_checker = None
        else:
            # Neither native nor Docker installed
            print_error("veraPDF is not available.")
            print_hint("Install veraPDF: `brew install verapdf` (recommended) or install Docker")
            if engine == "vera":
                sys.exit(1)
            else:
                print_warning("Falling back to basic checks only")
                engine = "basic"
                vera_checker = None

    # Process each file
    results: list[tuple[Path, PDFFullResult]] = []
    total_start = time.time()

    for file_path in all_files:
        # Pre-scan and timing estimation (for structured progress)
        if emitter:
            from inspekt.services.pdf_prescan import prescan_pdf
            from inspekt.services.progress_timing import estimate_timing

            prescan = prescan_pdf(file_path)
            timing_config = {
                "ocr": not no_ocr,
                "contrast": not no_contrast,
                "classify": not no_image_classification,
                "preview": not no_interactive,
                "max_ocr_pages": prescan.page_count if ocr_all_pages else 10,
                "max_contrast_pages": contrast_max_pages,
                "max_classify_images": max_image_classification,
                "max_preview_pages": interactive_pages if interactive_pages > 0 else prescan.page_count,
            }
            timing = estimate_timing(prescan, timing_config)
            emitter.emit_prescan(prescan, timing)

        # Continue with file processing
        try:
            # Run basic checks
            if emitter:
                with emitter.step("core", "Run core accessibility checks"):
                    basic_result = basic_checker.check(file_path)
            elif json_output:
                basic_result = basic_checker.check(file_path)
            else:
                with print_checkbox_step("Run core accessibility checks"):
                    basic_result = basic_checker.check(file_path)

            # Run simple checks if requested
            simple_result = None
            if simple_checker and engine in ("simple", "all"):
                try:
                    if emitter:
                        # Simple checks are part of core for structured progress
                        simple_result = simple_checker.check(file_path)
                    elif json_output:
                        simple_result = simple_checker.check(file_path)
                    else:
                        with print_checkbox_step("Run simple accessibility checks"):
                            simple_result = simple_checker.check(file_path)
                except Exception as e:
                    if emitter:
                        emitter.emit_error(f"SimplePDFChecker failed: {e}", "core")
                    elif not json_output:
                        print_warning(f"SimplePDFChecker failed for {file_path.name}: {e}")

            # Run veraPDF if requested
            vera_result = None
            if vera_checker and engine in ("vera", "all"):
                try:
                    if emitter:
                        # veraPDF is part of core for structured progress
                        vera_result = vera_checker.check(file_path, profile=profile)
                    elif json_output:
                        vera_result = vera_checker.check(file_path, profile=profile)
                    else:
                        with print_checkbox_step(f"Run veraPDF validation ({profile.upper()})"):
                            vera_result = vera_checker.check(file_path, profile=profile)
                except Exception as e:
                    if emitter:
                        emitter.emit_error(f"veraPDF failed: {e}", "core")
                    elif not json_output:
                        print_warning(f"veraPDF failed for {file_path.name}: {e}")

            results.append((file_path, PDFFullResult(basic=basic_result, verapdf=vera_result, simple=simple_result)))

        except ImportError as e:
            print_error(str(e))
            sys.exit(1)
        except Exception as e:
            if json_output:
                # For JSON, include error in output
                click.echo(json.dumps({"error": str(e), "file": str(file_path)}))
            else:
                print_error(f"Error checking {file_path.name}: {e}")
            continue

    total_time = time.time() - total_start

    # Generate HTML report if requested
    if output_path and results:
        from inspekt.services.pdf_report import generate_pdf_report
        from inspekt.app.cli.output import OutputHandler

        # Build config overrides from CLI flags
        config_overrides = {}
        if no_cover:
            config_overrides["show-cover-page"] = False
        if no_screenshots:
            config_overrides["show-issue-screenshots"] = False
        if no_ocr:
            config_overrides["show-text-discrepancy-section"] = False
        if ocr_all_pages:
            config_overrides["ocr-analyze-all"] = True
        if ocr_lang != "eng":
            config_overrides["ocr-lang"] = ocr_lang
        if no_score:
            config_overrides["show-score"] = False
        if no_structure:
            config_overrides["show-structure"] = False
        if no_content_audit:
            config_overrides["show-content-audit"] = False
        if no_remediation:
            config_overrides["show-remediation"] = False
        if wcag_level:
            config_overrides["wcag-level"] = wcag_level

        # AI-powered image analysis options
        # Image classification is enabled by default (local, no API cost)
        if no_image_classification:
            config_overrides["classify-images"] = False
        else:
            config_overrides["classify-images"] = True
        config_overrides["max-image-classification"] = max_image_classification
        if generate_alt_text:
            config_overrides["generate-alt-text"] = True
            config_overrides["max-alt-text"] = max_alt_text  # Limit for API costs
        if ai_provider:
            config_overrides["ai-provider"] = ai_provider

        # Tag visualization options (Phase 2) - DEPRECATED
        if show_tags:
            from inspekt.app.cli.table import print_warning
            print_warning("--show-tags is deprecated. Interactive Preview (enabled by default) provides a better experience.")
            config_overrides["show-tags"] = True
        if tag_pages:
            config_overrides["tag-pages"] = tag_pages

        # Color contrast analysis options (Phase 5) - enabled by default
        if no_contrast:
            config_overrides["check-contrast"] = False
        else:
            config_overrides["check-contrast"] = True
        if contrast_pages:
            config_overrides["contrast-pages"] = contrast_pages
        config_overrides["contrast-dpi"] = contrast_dpi
        config_overrides["contrast-max-pages"] = contrast_max_pages
        config_overrides["contrast-max-issues"] = contrast_max_issues

        # Interactive preview options (Phase 6) - enabled by default
        if no_interactive:
            config_overrides["interactive-preview"] = False
        else:
            config_overrides["interactive-preview"] = True
            config_overrides["interactive-pages"] = interactive_pages  # Number of pages to show

        # External assets is now default - only embed BASE64 if explicitly requested
        if not embed_base64:
            config_overrides["external-assets"] = True

        if len(results) == 1:
            report_path = Path(output_path)
            if not report_path.suffix:
                report_path = report_path.with_suffix('.html')

            file_path, result = results[0]
            generate_pdf_report(
                result,
                report_path,
                pdf_path=file_path,
                config_overrides=config_overrides if config_overrides else None,
                show_progress=not emitter,  # Don't show CLI progress if using structured emitter
                progress_emitter=emitter,
            )
            # Success message is now shown by the checklist's "Save report" step

            if open_report:
                OutputHandler.open_file(report_path)
        else:
            # Multiple files - create individual reports
            base_path = Path(output_path)
            for file_path, result in results:
                report_name = file_path.stem + "_accessibility_report.html"
                report_path = base_path.parent / report_name if base_path.suffix else base_path / report_name
                report_path.parent.mkdir(parents=True, exist_ok=True)
                generate_pdf_report(
                    result,
                    report_path,
                    pdf_path=file_path,
                    config_overrides=config_overrides if config_overrides else None,
                    show_progress=not emitter,
                    progress_emitter=emitter,
                )
                if not emitter:
                    click.echo(f"  Report: {report_path}")

            if open_report and results:
                # Open the first report
                first_report = base_path.parent / (results[0][0].stem + "_accessibility_report.html")
                OutputHandler.open_file(first_report)

        # Skip terminal output if generating report
        if not verbose:
            sys.exit(0 if all(r.basic.failed == 0 for _, r in results) else 1)

    # Export JSON data if requested (NEW in v2.0)
    if (json_output_path or json_only) and results:
        from inspekt.services.pdf_report_generator import generate_report_data
        from inspekt.services.pdf_report_renderer import export_json_with_assets

        # Build config for report data generation
        config = {}
        if no_cover:
            config["show-cover-page"] = False
        if no_screenshots:
            config["show-issue-screenshots"] = False
        if no_contrast:
            config["check-contrast"] = False
        else:
            config["check-contrast"] = True
            config["contrast-dpi"] = contrast_dpi
            config["contrast-max-pages"] = contrast_max_pages
            config["contrast-max-issues"] = contrast_max_issues
        if no_interactive:
            config["interactive-preview"] = False
        else:
            config["interactive-preview"] = True
            config["interactive-pages"] = interactive_pages

        for file_path, result in results:
            # Determine JSON output path
            if json_output_path:
                json_path = Path(json_output_path)
                if not json_path.suffix:
                    json_path = json_path.with_suffix('.json')
            else:
                # json_only mode - auto-generate path
                json_path = file_path.with_suffix('.json')

            # Generate report data
            if emitter:
                with emitter.step("build", "Build report"):
                    report_data = generate_report_data(file_path, result, config)
            elif not json_output:  # Only show if not in JSON-only terminal mode
                with print_checkbox_step("Generate report data"):
                    report_data = generate_report_data(file_path, result, config)
            else:
                report_data = generate_report_data(file_path, result, config)

            # Export to JSON with asset extraction for large images
            if emitter:
                with emitter.step("save", "Save report"):
                    json_path, assets_dir = export_json_with_assets(report_data, json_path)
            elif not json_output:
                with print_checkbox_step("Export JSON report"):
                    json_path, assets_dir = export_json_with_assets(report_data, json_path)
            else:
                json_path, assets_dir = export_json_with_assets(report_data, json_path)

            if not json_output and not emitter:
                print_success(f"JSON report saved: {json_path}")
                if assets_dir:
                    click.echo(f"  Assets directory: {assets_dir}")

        if json_only and not output_path and not pdfi_output_path:
            # Exit after JSON export if only JSON was requested
            sys.exit(0 if all(r.basic.failed == 0 for _, r in results) else 1)

    # Export as PDFI package if requested (NEW: self-contained package format)
    if pdfi_output_path and results:
        from inspekt.services.pdf_report_generator import generate_report_data
        from inspekt.services.pdfi_package import generate_pdfi_package

        # Build config for report data generation
        config = {}
        if no_cover:
            config["show-cover-page"] = False
        if no_screenshots:
            config["show-issue-screenshots"] = False
        if no_contrast:
            config["check-contrast"] = False
        else:
            config["check-contrast"] = True
            config["contrast-dpi"] = contrast_dpi
            config["contrast-max-pages"] = contrast_max_pages
            config["contrast-max-issues"] = contrast_max_issues
        config["interactive-preview"] = not no_interactive
        config["interactive-pages"] = interactive_pages

        for file_path, result in results:
            # Determine PDFI output path
            pdfi_path = Path(pdfi_output_path)
            if not pdfi_path.suffix or pdfi_path.suffix.lower() != '.pdfi':
                pdfi_path = pdfi_path.with_suffix('.pdfi')

            # Generate report data
            if emitter:
                with emitter.step("build", "Build report"):
                    report_data = generate_report_data(file_path, result, config)
            else:
                with print_checkbox_step("Generate report data"):
                    report_data = generate_report_data(file_path, result, config)

            # Generate PDFI package
            if emitter:
                with emitter.step("save", "Save report"):
                    output_file = generate_pdfi_package(
                        pdf_path=file_path,
                        report_data=report_data,
                        output_path=pdfi_path,
                        config=config,
                        include_preview=not no_interactive,
                        preview_pages=interactive_pages,
                    )
            else:
                with print_checkbox_step("Create PDFI package"):
                    output_file = generate_pdfi_package(
                        pdf_path=file_path,
                        report_data=report_data,
                        output_path=pdfi_path,
                        config=config,
                        include_preview=not no_interactive,
                        preview_pages=interactive_pages,
                    )

            if not emitter:
                print_success(f"PDFI package saved: {output_file}")
                file_size = output_file.stat().st_size
                if file_size > 1024 * 1024:
                    click.echo(f"  Size: {file_size / (1024 * 1024):.1f} MB")
                else:
                    click.echo(f"  Size: {file_size / 1024:.1f} KB")

            if open_report:
                # Open with default app (on macOS, this should open with Inspekt desktop app)
                OutputHandler.open_file(output_file)

        # Emit completion event for structured progress
        if emitter:
            emitter.emit_complete()

        # Exit after PDFI export
        sys.exit(0 if all(r.basic.failed == 0 for _, r in results) else 1)

    # Output results
    if json_output:
        if len(results) == 1:
            _output_json(results[0][1])
        else:
            # Multiple files - output as array
            all_output = []
            for file_path, result in results:
                all_output.append({
                    "file": str(file_path),
                    "results": json.loads(json.dumps({
                        "basic": {
                            "metadata": {
                                "file_path": str(result.basic.metadata.file_path),
                                "file_size": result.basic.metadata.file_size,
                                "page_count": result.basic.metadata.page_count,
                            },
                            "summary": {
                                "passed": result.basic.passed,
                                "failed": result.basic.failed,
                            },
                        },
                    })),
                })
            click.echo(json.dumps(all_output, indent=2))
    else:
        for file_path, result in results:
            if len(results) > 1:
                click.echo()
                click.echo(click.style(f"═══ {file_path.name} ═══", bold=True))

            # Print basic results (only for basic engine, not when simple is also shown)
            # Simple is a superset of basic, so showing both would duplicate info
            if engine == "basic":
                _print_basic_results(result.basic, verbose=verbose)

            # Print simple results (for simple or all engines)
            # When using 'all', simple replaces basic since it includes all basic checks
            if result.simple and engine in ("simple", "all"):
                _print_simple_results(result.simple, verbose=verbose)

            # Print veraPDF results
            if result.verapdf:
                _print_verapdf_results(result.verapdf, verbose=verbose)

        # Print tips
        click.echo()
        tips = []
        if engine == "basic":
            tips.append(("--engine simple", "Run 11 checks based on simplA11yPDFCrawler", "`inspekt pdf check doc.pdf --engine simple`"))
            tips.append(("--engine vera", "Run full PDF/UA validation with veraPDF", "`inspekt pdf check doc.pdf --engine vera`"))
        elif engine == "simple":
            tips.append(("--engine vera", "Run full PDF/UA validation with veraPDF", None))
        if engine != "all":
            tips.append(("--engine all", "Run all engines (basic, simple, vera)", None))
        tips.append(("--json", "Output results as JSON for automation", None))
        if not output_path:
            tips.append(("--output report", "Generate HTML report", "`inspekt pdf check doc.pdf -o report --open`"))
        if not verbose:
            tips.append(("--verbose", "Show detailed metadata and violation contexts", None))

        if tips:
            _print_tips_section(tips)

        # Summary for multiple files
        if len(results) > 1:
            click.echo()
            total_passed = sum(r.basic.passed for _, r in results)
            total_failed = sum(r.basic.failed for _, r in results)
            click.echo(f"  Checked {len(results)} files in {total_time:.1f}s")
            click.echo(f"  Total: {total_passed} passed, {total_failed} failed")

    # Exit with error code if any failures (check both basic and simple)
    has_failures = any(r.basic.failed > 0 for _, r in results)
    if not has_failures and engine in ("simple", "all"):
        has_failures = any(r.simple.failed > 0 for _, r in results if r.simple)
    if has_failures:
        sys.exit(1)


# =============================================================================
# Render Command (NEW in v2.0) - Generate HTML from saved JSON
# =============================================================================


@pdf.command("render")
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", type=click.Path(), help="Output HTML file path")
@click.option("--open", "open_report", is_flag=True, help="Open HTML report in browser after generation")
def render(json_file: str, output_path: str | None, open_report: bool):
    """Render an HTML report from a saved JSON file.

    This command allows you to regenerate an HTML accessibility report
    from previously exported JSON data. This is useful for:

    \b
    - Regenerating reports after template updates
    - Creating HTML reports from JSON data exported elsewhere
    - Reproducing reports without re-running the PDF checks

    \b
    The JSON file should have been created using `inspekt pdf check --json-output`.

    \b
    Examples:
        inspekt pdf render report.json                    # Output to report.html
        inspekt pdf render report.json -o output.html     # Custom output path
        inspekt pdf render report.json --open             # Open in browser
    """
    from inspekt.services.pdf_report_renderer import render_html_from_json
    from inspekt.app.cli.output import OutputHandler

    json_path = Path(json_file)

    # Determine output path
    if output_path:
        html_path = Path(output_path)
        if not html_path.suffix:
            html_path = html_path.with_suffix('.html')
    else:
        html_path = json_path.with_suffix('.html')

    try:
        with print_checkbox_step("Load JSON report data"):
            pass  # Just for visual feedback

        with print_checkbox_step("Render HTML report"):
            html_content = render_html_from_json(json_path, resolve_assets=True)

        with print_checkbox_step("Save HTML report"):
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(html_content, encoding="utf-8")

        print_success(f"HTML report generated: {html_path}")

        if open_report:
            OutputHandler.open_file(html_path)

    except json.JSONDecodeError as e:
        print_error(f"Invalid JSON file: {e}")
        sys.exit(1)
    except FileNotFoundError as e:
        print_error(f"File not found: {e}")
        sys.exit(1)
    except Exception as e:
        print_error(f"Failed to render report: {e}")
        sys.exit(1)


# =============================================================================
# Viewer Command - Open the standalone HTML viewer
# =============================================================================


@pdf.command("viewer")
@click.option("--serve", is_flag=True, help="Serve on localhost instead of opening as file")
@click.option("--port", type=int, default=8080, help="Port for local server (default: 8080)")
def viewer(serve: bool, port: int):
    """Open the PDF Report Viewer in your browser.

    The viewer is a standalone HTML file that can load any Inspekt PDF
    accessibility report JSON and render it client-side. It works completely
    offline with file:// URLs.

    \b
    Usage:
        inspekt pdf viewer              # Open viewer in browser
        inspekt pdf viewer --serve      # Serve on localhost:8080

    \b
    To use the viewer:
        1. Run `inspekt pdf check document.pdf --json-output report.json`
        2. Open the viewer with `inspekt pdf viewer`
        3. Drag and drop your JSON file onto the viewer

    The viewer supports both v1.0 and v2.0 JSON schema formats and will
    automatically migrate older reports.
    """
    from inspekt.app.cli.output import OutputHandler

    # Get the path to the viewer template
    viewer_path = Path(__file__).parent.parent.parent / "templates" / "pdf_report_viewer.html"

    if not viewer_path.exists():
        print_error(f"Viewer template not found at: {viewer_path}")
        sys.exit(1)

    if serve:
        # Serve on localhost
        import http.server
        import socketserver
        import threading
        import webbrowser

        # Create a simple HTTP server
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(viewer_path.parent), **kwargs)

            def log_message(self, format, *args):
                # Suppress logging
                pass

        try:
            with socketserver.TCPServer(("", port), Handler) as httpd:
                url = f"http://localhost:{port}/pdf_report_viewer.html"
                print_success(f"Serving viewer at {url}")
                print_hint("Press Ctrl+C to stop the server")

                # Open browser
                webbrowser.open(url)

                # Serve until interrupted
                httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nServer stopped.")
        except OSError as e:
            if "Address already in use" in str(e):
                print_error(f"Port {port} is already in use. Try --port with a different port number.")
            else:
                print_error(f"Failed to start server: {e}")
            sys.exit(1)
    else:
        # Open directly as file://
        OutputHandler.open_file(viewer_path)
        print_success(f"Opened viewer: {viewer_path}")
        print_hint("Drag and drop a JSON report file onto the viewer to load it")
