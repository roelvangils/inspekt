"""
PDF Accessibility Checker Service.

This module provides two levels of PDF accessibility checking:

1. PDFBasicChecker: Fast checks using pikepdf for 6 fundamental criteria
   - Tagged PDF structure
   - Document title with DisplayDocTitle
   - Document language
   - AT access protection
   - Navigation bookmarks (for 20+ page documents)
   - Scanned/image-only detection

2. VeraPDFChecker: Full PDF/UA validation using veraPDF (via Docker)
   - Complete Matterhorn Protocol compliance
   - PDF/UA-1 and PDF/UA-2 validation
   - Machine-checkable WCAG criteria

Based on Luxembourg simplA11yPDFCrawler methodology and PDF/UA standards.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pikepdf


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class PDFCheckResult:
    """Result of a single PDF accessibility check."""

    check_id: str
    name: str
    status: Literal["pass", "fail", "warn", "skip"]
    message: str
    severity: Literal["critical", "serious", "moderate", "minor"]
    wcag_sc: str | None = None
    wcag_level: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class PDFMetadata:
    """Basic metadata about the PDF document."""

    file_path: Path
    file_size: int
    page_count: int
    title: str | None = None
    author: str | None = None
    creator: str | None = None
    producer: str | None = None
    language: str | None = None
    is_encrypted: bool = False
    pdf_version: str | None = None


@dataclass
class PDFEnhancedMetadata:
    """
    Extended metadata for PDF accessibility reports.

    Includes additional document properties useful for accessibility analysis
    and report generation, extracted using pikepdf and PyMuPDF.
    """

    # Base metadata (from PDFMetadata)
    file_path: Path
    file_size: int
    page_count: int
    title: str | None = None
    author: str | None = None
    creator: str | None = None
    producer: str | None = None
    language: str | None = None
    is_encrypted: bool = False
    pdf_version: str | None = None

    # Extended metadata
    creation_date: str | None = None  # ISO format string
    modification_date: str | None = None  # ISO format string
    page_dimensions: list[tuple[float, float]] | None = None  # (width, height) per page in points
    has_ua_marker: bool = False  # PDF/UA conformance indicator
    has_suspects_flag: bool = False  # Document may have been OCR'd with errors
    conformance_level: str | None = None  # e.g., "PDF/UA-1", "PDF/A-2a"
    subject: str | None = None  # Document subject/description
    keywords: str | None = None  # Document keywords

    # Enhanced metadata (new fields)
    is_linearized: bool = False  # PDF optimized for fast web viewing
    trapped: str | None = None  # Print trapping: "True", "False", "Unknown"
    xmp_metadata: dict | None = None  # Parsed XMP metadata
    custom_metadata: dict | None = None  # Non-standard docinfo fields
    version_count: int = 1  # Number of incremental save versions

    @classmethod
    def from_basic_metadata(
        cls,
        basic: "PDFMetadata",
    ) -> "PDFEnhancedMetadata":
        """
        Create enhanced metadata starting from basic metadata.

        Args:
            basic: PDFMetadata instance to extend

        Returns:
            PDFEnhancedMetadata with basic fields populated
        """
        return cls(
            file_path=basic.file_path,
            file_size=basic.file_size,
            page_count=basic.page_count,
            title=basic.title,
            author=basic.author,
            creator=basic.creator,
            producer=basic.producer,
            language=basic.language,
            is_encrypted=basic.is_encrypted,
            pdf_version=basic.pdf_version,
        )


# ============================================================================
# Enhanced Metadata Extraction Helpers
# ============================================================================


def _check_linearization(file_path: Path) -> bool:
    """
    Check if a PDF is linearized (optimized for fast web viewing).

    Linearized PDFs have a Linearized dictionary near the start of the file
    that enables progressive rendering before the entire file is downloaded.

    Args:
        file_path: Path to the PDF file

    Returns:
        True if the PDF is linearized
    """
    try:
        # Read first 4KB to find linearization marker
        with open(file_path, "rb") as f:
            header = f.read(4096)

        # Look for /Linearized marker
        # Pattern: /Linearized followed by a number
        return b"/Linearized" in header
    except Exception:
        return False


def _extract_trapped(info) -> str | None:
    """
    Extract the Trapped status from docinfo.

    The /Trapped field indicates whether print trapping has been applied:
    - /True: Trapping has been applied
    - /False: Trapping has not been applied
    - /Unknown: Unknown trapping status

    Args:
        info: pikepdf docinfo dictionary

    Returns:
        "True", "False", "Unknown", or None if not set
    """
    if not info:
        return None

    trapped_value = info.get("/Trapped")
    if trapped_value is None:
        return None

    trapped_str = str(trapped_value).strip()

    # Normalize the value
    if trapped_str in ("/True", "True", "true"):
        return "True"
    elif trapped_str in ("/False", "False", "false"):
        return "False"
    elif trapped_str in ("/Unknown", "Unknown", "unknown"):
        return "Unknown"
    else:
        # If it's a name object, strip the leading /
        if trapped_str.startswith("/"):
            return trapped_str[1:]
        return trapped_str if trapped_str else None


def _parse_xmp_metadata(pdf) -> dict | None:
    """
    Parse XMP metadata from the PDF.

    XMP (Extensible Metadata Platform) is XML-based metadata that can contain
    more detailed information than the standard docinfo dictionary, including
    PDF/A and PDF/UA conformance declarations.

    Args:
        pdf: pikepdf Pdf object

    Returns:
        Dictionary with parsed XMP fields, or None if not available
    """
    try:
        root = pdf.Root

        # Check for Metadata stream
        if "/Metadata" not in root:
            return None

        metadata_stream = root["/Metadata"]
        if not hasattr(metadata_stream, "read_bytes"):
            return None

        xmp_bytes = metadata_stream.read_bytes()
        xmp_text = xmp_bytes.decode("utf-8", errors="ignore")

        result = {}

        # Extract common XMP fields using regex for robust parsing
        # These patterns handle various XMP formats and namespaces

        # xmp:CreatorTool
        match = re.search(r'<xmp:CreatorTool[^>]*>([^<]+)</xmp:CreatorTool>', xmp_text)
        if match:
            result["creator_tool"] = match.group(1).strip()

        # xmp:MetadataDate
        match = re.search(r'<xmp:MetadataDate[^>]*>([^<]+)</xmp:MetadataDate>', xmp_text)
        if match:
            result["metadata_date"] = match.group(1).strip()

        # pdf:Producer
        match = re.search(r'<pdf:Producer[^>]*>([^<]+)</pdf:Producer>', xmp_text)
        if match:
            result["producer"] = match.group(1).strip()

        # PDF/A conformance (pdfaid:part and pdfaid:conformance)
        part_match = re.search(r'<pdfaid:part[^>]*>([^<]+)</pdfaid:part>', xmp_text)
        conf_match = re.search(r'<pdfaid:conformance[^>]*>([^<]+)</pdfaid:conformance>', xmp_text)
        if part_match:
            pdfa_level = f"PDF/A-{part_match.group(1).strip()}"
            if conf_match:
                pdfa_level += conf_match.group(1).strip().lower()
            result["pdfa_conformance"] = pdfa_level

        # PDF/UA conformance (pdfuaid:part)
        match = re.search(r'<pdfuaid:part[^>]*>([^<]+)</pdfuaid:part>', xmp_text)
        if match:
            result["pdfua_conformance"] = f"PDF/UA-{match.group(1).strip()}"

        # dc:title (Dublin Core)
        match = re.search(r'<dc:title[^>]*>.*?<rdf:li[^>]*>([^<]+)</rdf:li>.*?</dc:title>', xmp_text, re.DOTALL)
        if match:
            result["dc_title"] = match.group(1).strip()

        # dc:creator (Dublin Core author)
        match = re.search(r'<dc:creator[^>]*>.*?<rdf:li[^>]*>([^<]+)</rdf:li>.*?</dc:creator>', xmp_text, re.DOTALL)
        if match:
            result["dc_creator"] = match.group(1).strip()

        # dc:description
        match = re.search(r'<dc:description[^>]*>.*?<rdf:li[^>]*>([^<]+)</rdf:li>.*?</dc:description>', xmp_text, re.DOTALL)
        if match:
            result["dc_description"] = match.group(1).strip()

        return result if result else None

    except Exception:
        return None


def _extract_custom_metadata(info) -> dict | None:
    """
    Extract custom (non-standard) metadata fields from docinfo.

    Some PDFs contain additional metadata fields beyond the standard ones.
    This function extracts any fields not in the standard set.

    Args:
        info: pikepdf docinfo dictionary

    Returns:
        Dictionary of custom fields, or None if none found
    """
    if not info:
        return None

    # Standard docinfo fields to exclude
    standard_fields = {
        "/Title", "/Author", "/Subject", "/Keywords",
        "/Creator", "/Producer", "/CreationDate", "/ModDate", "/Trapped"
    }

    custom = {}
    try:
        for key in info.keys():
            key_str = str(key)
            if key_str not in standard_fields:
                value = info.get(key)
                if value is not None:
                    # Clean up the key name (remove leading /)
                    clean_key = key_str.lstrip("/")
                    # Convert value to string, handling various types
                    value_str = str(value).strip()
                    if value_str:
                        custom[clean_key] = value_str
    except Exception:
        pass

    return custom if custom else None


def _get_version_count(file_path: Path) -> int:
    """
    Count the number of incremental save versions in the PDF.

    PDF files can be incrementally updated, appending new content rather than
    rewriting the entire file. Each incremental update creates a new "version"
    that can potentially be extracted to see previous states of the document.

    This is important for accessibility auditing because:
    - Previous versions may contain content that was removed
    - Changes to accessibility features can be tracked
    - Tools like pdfresurrect can extract embedded versions

    Args:
        file_path: Path to the PDF file

    Returns:
        Number of versions (minimum 1 for original)
    """
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(file_path)
        # version_count is the number of incremental saves + 1 for original
        count = getattr(doc, "version_count", 1)
        doc.close()
        return max(count, 1)
    except Exception:
        # Fallback: count %%EOF markers in file
        try:
            with open(file_path, "rb") as f:
                content = f.read()
            # Count %%EOF markers (each version ends with one)
            eof_count = content.count(b"%%EOF")
            return max(eof_count, 1)
        except Exception:
            return 1


def extract_enhanced_metadata(file_path: Path | str) -> PDFEnhancedMetadata | None:
    """
    Extract enhanced metadata from a PDF file.

    Uses pikepdf for most metadata and PyMuPDF for page dimensions.

    Args:
        file_path: Path to the PDF file

    Returns:
        PDFEnhancedMetadata, or None if extraction fails
    """
    try:
        import pikepdf
    except ImportError:
        return None

    file_path = Path(file_path)
    if not file_path.exists():
        return None

    try:
        with pikepdf.open(file_path) as pdf:
            # Get basic info
            info = pdf.docinfo if hasattr(pdf, "docinfo") else {}
            root = pdf.Root

            # Extract metadata fields
            title = str(info.get("/Title", "")).strip() or None
            author = str(info.get("/Author", "")).strip() or None
            creator = str(info.get("/Creator", "")).strip() or None
            producer = str(info.get("/Producer", "")).strip() or None
            subject = str(info.get("/Subject", "")).strip() or None
            keywords = str(info.get("/Keywords", "")).strip() or None

            # Extract dates
            creation_date = _parse_pdf_date(info.get("/CreationDate"))
            modification_date = _parse_pdf_date(info.get("/ModDate"))

            # Get language from catalog
            language = str(root.get("/Lang", "")).strip() or None

            # Check for PDF/UA marker (in MarkInfo or XMP metadata)
            has_ua_marker = False
            has_suspects_flag = False

            if "/MarkInfo" in root:
                mark_info = root["/MarkInfo"]
                # Suspects flag indicates OCR errors may exist
                if "/Suspects" in mark_info:
                    has_suspects_flag = bool(mark_info["/Suspects"])

            # Check for PDF/UA in OutputIntents or XMP
            conformance_level = None
            if "/OutputIntents" in root:
                for intent in root.get("/OutputIntents", []):
                    intent_str = str(intent.get("/OutputConditionIdentifier", ""))
                    if "PDF/UA" in intent_str:
                        has_ua_marker = True
                        conformance_level = intent_str

            # Extract page dimensions using PyMuPDF if available
            page_dimensions = None
            try:
                from inspekt.services.pdf_renderer import is_pymupdf_available, PDFRenderer

                if is_pymupdf_available():
                    with PDFRenderer(file_path) as renderer:
                        page_dimensions = [
                            renderer.get_page_dimensions(i)
                            for i in range(min(renderer.page_count, 100))  # Limit for large docs
                        ]
            except Exception:
                pass  # Page dimensions are optional

            # Extract enhanced metadata using helper functions
            is_linearized = _check_linearization(file_path)
            trapped = _extract_trapped(info)
            xmp_metadata = _parse_xmp_metadata(pdf)
            custom_metadata = _extract_custom_metadata(info)

            # Capture values needed after context closes
            page_count = len(pdf.pages)
            is_encrypted = pdf.is_encrypted
            pdf_version_str = str(pdf.pdf_version)

        # Get version count (outside pikepdf context as it uses PyMuPDF)
        version_count = _get_version_count(file_path)

        # Update PDF/UA marker from XMP if not found in OutputIntents
        if xmp_metadata and not has_ua_marker:
            if "pdfua_conformance" in xmp_metadata:
                has_ua_marker = True
                conformance_level = xmp_metadata["pdfua_conformance"]
            elif "pdfa_conformance" in xmp_metadata:
                # Also note PDF/A conformance
                if not conformance_level:
                    conformance_level = xmp_metadata["pdfa_conformance"]

        return PDFEnhancedMetadata(
            file_path=file_path,
            file_size=file_path.stat().st_size,
            page_count=page_count,
            title=title,
            author=author,
            creator=creator,
            producer=producer,
            language=language,
            is_encrypted=is_encrypted,
            pdf_version=pdf_version_str,
            creation_date=creation_date,
            modification_date=modification_date,
            page_dimensions=page_dimensions,
            has_ua_marker=has_ua_marker,
            has_suspects_flag=has_suspects_flag,
            conformance_level=conformance_level,
            subject=subject,
            keywords=keywords,
            # Enhanced metadata
            is_linearized=is_linearized,
            trapped=trapped,
            xmp_metadata=xmp_metadata,
            custom_metadata=custom_metadata,
            version_count=version_count,
        )
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to extract enhanced metadata: {e}")
        return None


def _parse_pdf_date(date_value) -> str | None:
    """
    Parse a PDF date string to ISO format.

    PDF dates are in format: D:YYYYMMDDHHmmSSOHH'mm'
    Example: D:20231215143022+01'00'

    Args:
        date_value: PDF date string or pikepdf object

    Returns:
        ISO format date string, or None if parsing fails
    """
    if date_value is None:
        return None

    try:
        date_str = str(date_value)

        # Remove D: prefix if present
        if date_str.startswith("D:"):
            date_str = date_str[2:]

        # Extract date components (minimum: YYYY)
        if len(date_str) < 4:
            return None

        year = date_str[0:4]
        month = date_str[4:6] if len(date_str) >= 6 else "01"
        day = date_str[6:8] if len(date_str) >= 8 else "01"
        hour = date_str[8:10] if len(date_str) >= 10 else "00"
        minute = date_str[10:12] if len(date_str) >= 12 else "00"
        second = date_str[12:14] if len(date_str) >= 14 else "00"

        return f"{year}-{month}-{day}T{hour}:{minute}:{second}"
    except Exception:
        return None


def format_date_human_readable(iso_date: str | None) -> str:
    """
    Convert ISO date to human-readable format.

    Args:
        iso_date: ISO format date string (e.g., "2025-03-25T18:41:31")

    Returns:
        Human-readable date (e.g., "March 25, 2025 at 6:41 PM")
        Returns "Unknown" if parsing fails or date is None
    """
    if not iso_date:
        return "Unknown"

    try:
        from datetime import datetime

        # Handle various ISO formats
        dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))

        # Format: "March 25, 2025 at 6:41 PM"
        # strftime with %-d or %#d for non-zero-padded day
        formatted = dt.strftime("%B %d, %Y at %I:%M %p")

        # Remove leading zero from day (e.g., "March 05" -> "March 5")
        # and from hour (e.g., "06:41 PM" -> "6:41 PM")
        import re
        formatted = re.sub(r"(\w+) 0(\d),", r"\1 \2,", formatted)
        formatted = re.sub(r"at 0(\d):", r"at \1:", formatted)

        return formatted
    except (ValueError, TypeError):
        return iso_date  # Return original if parsing fails


@dataclass
class PDFBasicResult:
    """Result of all basic PDF accessibility checks."""

    metadata: PDFMetadata
    checks: list[PDFCheckResult]

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail")

    @property
    def warnings(self) -> int:
        return sum(1 for c in self.checks if c.status == "warn")

    @property
    def skipped(self) -> int:
        return sum(1 for c in self.checks if c.status == "skip")

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail" and c.severity == "critical")

    @property
    def serious_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail" and c.severity == "serious")

    @property
    def moderate_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail" and c.severity == "moderate")


@dataclass
class VeraPDFViolation:
    """A single violation from veraPDF analysis."""

    rule_id: str
    specification: str
    clause: str
    test_number: int
    description: str
    severity: str
    object_type: str | None = None
    context: str | None = None
    # Location fields for issue visualization
    page_number: int | None = None  # 0-indexed page number
    bbox: tuple[float, float, float, float] | None = None  # (x1, y1, x2, y2) in PDF coordinates
    location_path: str | None = None  # Full location path from veraPDF


@dataclass
class VeraPDFResult:
    """Result of veraPDF PDF/UA validation."""

    profile: str
    compliant: bool
    violations: list[VeraPDFViolation]
    passed_rules: int
    failed_rules: int
    processing_time_ms: int | None = None
    verapdf_version: str | None = None

    @property
    def total_violations(self) -> int:
        return len(self.violations)


# ============================================================================
# Check Metadata Loader
# ============================================================================


def load_check_metadata() -> dict[str, Any]:
    """Load PDF check metadata from the JSON configuration file."""
    data_path = Path(__file__).parent.parent / "data" / "pdf_checks.json"
    with open(data_path) as f:
        return json.load(f)


def get_check_info(check_id: str) -> dict[str, Any] | None:
    """Get metadata for a specific check by ID."""
    metadata = load_check_metadata()
    for check in metadata.get("checks", []):
        if check["id"] == check_id:
            return check
    return None


# ============================================================================
# PDFBasicChecker - Fast pikepdf-based checks
# ============================================================================


class PDFBasicChecker:
    """
    Performs 6 basic PDF accessibility checks using pikepdf.

    These checks are fast and don't require external tools. They cover
    the most fundamental accessibility requirements based on the
    Luxembourg simplA11yPDFCrawler methodology.
    """

    def __init__(self):
        self._metadata = load_check_metadata()
        self._checks_info = {c["id"]: c for c in self._metadata.get("checks", [])}

    def check(self, file_path: Path | str) -> PDFBasicResult:
        """
        Run all basic accessibility checks on a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            PDFBasicResult with metadata and all check results

        Raises:
            ImportError: If pikepdf is not installed
            FileNotFoundError: If the PDF file doesn't exist
            pikepdf.PdfError: If the PDF cannot be opened
        """
        try:
            import pikepdf
        except ImportError as e:
            raise ImportError(
                "pikepdf is required for PDF accessibility checking. "
                "Install it with: pip install pikepdf>=8.0.0"
            ) from e

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Open the PDF and extract metadata
        with pikepdf.open(file_path) as pdf:
            metadata = self._extract_metadata(pdf, file_path)

            # Run all checks
            checks = [
                self._check_tagged(pdf),
                self._check_title(pdf),
                self._check_language(pdf),
                self._check_protected(pdf),
                self._check_bookmarks(pdf, metadata.page_count),
                self._check_scanned(pdf),
                self._check_figure_alt_text(pdf),
            ]

        return PDFBasicResult(metadata=metadata, checks=checks)

    def _extract_metadata(self, pdf: "pikepdf.Pdf", file_path: Path) -> PDFMetadata:
        """Extract basic metadata from the PDF."""
        # Get document info dictionary
        info = pdf.docinfo if hasattr(pdf, "docinfo") else {}

        # Get title from info dict or XMP metadata
        title = None
        if info and "/Title" in info:
            title = str(info["/Title"])

        # Get author
        author = None
        if info and "/Author" in info:
            author = str(info["/Author"])

        # Get creator application
        creator = None
        if info and "/Creator" in info:
            creator = str(info["/Creator"])

        # Get PDF producer
        producer = None
        if info and "/Producer" in info:
            producer = str(info["/Producer"])

        # Get language from catalog
        language = None
        root = pdf.Root
        if "/Lang" in root:
            language = str(root["/Lang"])

        # Check encryption
        is_encrypted = pdf.is_encrypted

        # Get PDF version
        pdf_version = f"{pdf.pdf_version}"

        return PDFMetadata(
            file_path=file_path,
            file_size=file_path.stat().st_size,
            page_count=len(pdf.pages),
            title=title if title and title.strip() else None,
            author=author if author and author.strip() else None,
            creator=creator if creator and creator.strip() else None,
            producer=producer if producer and producer.strip() else None,
            language=language,
            is_encrypted=is_encrypted,
            pdf_version=pdf_version,
        )

    def _make_result(
        self,
        check_id: str,
        status: Literal["pass", "fail", "warn", "skip"],
        message: str,
        details: dict[str, Any] | None = None,
    ) -> PDFCheckResult:
        """Create a check result with metadata from the JSON config."""
        check_info = self._checks_info.get(check_id, {})
        return PDFCheckResult(
            check_id=check_id,
            name=check_info.get("name", check_id),
            status=status,
            message=message,
            severity=check_info.get("severity", "moderate"),
            wcag_sc=check_info.get("wcag_sc"),
            wcag_level=check_info.get("wcag_level"),
            details=details or {},
        )

    def _check_tagged(self, pdf: "pikepdf.Pdf") -> PDFCheckResult:
        """
        Check if the PDF is tagged.

        A tagged PDF has a StructTreeRoot in the document catalog and
        MarkInfo/Marked = true.
        """
        root = pdf.Root

        # Check for MarkInfo dictionary with Marked = true
        has_mark_info = False
        is_marked = False
        if "/MarkInfo" in root:
            mark_info = root["/MarkInfo"]
            has_mark_info = True
            if "/Marked" in mark_info:
                is_marked = bool(mark_info["/Marked"])

        # Check for StructTreeRoot
        has_struct_tree = "/StructTreeRoot" in root

        if is_marked and has_struct_tree:
            return self._make_result(
                "tagged",
                "pass",
                "PDF is tagged with a structure tree",
                {"has_mark_info": True, "is_marked": True, "has_struct_tree": True},
            )
        elif has_struct_tree and not is_marked:
            return self._make_result(
                "tagged",
                "warn",
                "PDF has structure tree but MarkInfo/Marked is not set to true",
                {"has_mark_info": has_mark_info, "is_marked": is_marked, "has_struct_tree": True},
            )
        else:
            return self._make_result(
                "tagged",
                "fail",
                "PDF is not tagged (no structure tree found)",
                {"has_mark_info": has_mark_info, "is_marked": is_marked, "has_struct_tree": False},
            )

    def _check_title(self, pdf: "pikepdf.Pdf") -> PDFCheckResult:
        """
        Check if the document has a title and DisplayDocTitle is enabled.

        The title should be in the Info dictionary, and ViewerPreferences
        should have DisplayDocTitle = true.
        """
        # Get title from info dictionary
        info = pdf.docinfo if hasattr(pdf, "docinfo") else {}
        title = None
        if info and "/Title" in info:
            title = str(info["/Title"]).strip()

        has_title = bool(title)

        # Check DisplayDocTitle in ViewerPreferences
        root = pdf.Root
        display_doc_title = False
        if "/ViewerPreferences" in root:
            viewer_prefs = root["/ViewerPreferences"]
            if "/DisplayDocTitle" in viewer_prefs:
                display_doc_title = bool(viewer_prefs["/DisplayDocTitle"])

        if has_title and display_doc_title:
            return self._make_result(
                "title",
                "pass",
                f"Document title is set and displayed: \"{title[:50]}{'...' if len(title) > 50 else ''}\"",
                {"title": title, "display_doc_title": True},
            )
        elif has_title and not display_doc_title:
            return self._make_result(
                "title",
                "warn",
                f"Title is set but DisplayDocTitle is not enabled (viewers will show filename instead)",
                {"title": title, "display_doc_title": False},
            )
        elif not has_title and display_doc_title:
            return self._make_result(
                "title",
                "fail",
                "DisplayDocTitle is enabled but no title is set",
                {"title": None, "display_doc_title": True},
            )
        else:
            return self._make_result(
                "title",
                "fail",
                "No document title is set",
                {"title": None, "display_doc_title": False},
            )

    def _check_language(self, pdf: "pikepdf.Pdf") -> PDFCheckResult:
        """
        Check if the document language is defined.

        The Lang entry should be present in the document catalog.
        """
        root = pdf.Root

        if "/Lang" in root:
            lang = str(root["/Lang"])
            # Validate language code format (basic check)
            if re.match(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", lang):
                return self._make_result(
                    "language",
                    "pass",
                    f"Document language is defined: \"{lang}\"",
                    {"language": lang},
                )
            else:
                return self._make_result(
                    "language",
                    "warn",
                    f"Document language is set but may not be a valid BCP 47 tag: \"{lang}\"",
                    {"language": lang},
                )
        else:
            return self._make_result(
                "language",
                "fail",
                "No document language is defined",
                {"language": None},
            )

    def _check_protected(self, pdf: "pikepdf.Pdf") -> PDFCheckResult:
        """
        Check if the document blocks assistive technology access.

        Some encrypted PDFs prevent text extraction, which blocks screen readers.
        We check both encryption status and permissions.
        """
        if not pdf.is_encrypted:
            return self._make_result(
                "protected",
                "pass",
                "Document is not encrypted",
                {"encrypted": False, "allows_extraction": True},
            )

        # Document is encrypted - check permissions
        # pikepdf exposes allow properties
        allows_extraction = pdf.allow.extract
        allows_accessibility = pdf.allow.accessibility  # Separate flag for AT access

        if allows_accessibility or allows_extraction:
            return self._make_result(
                "protected",
                "pass",
                "Document is encrypted but allows text extraction for accessibility",
                {"encrypted": True, "allows_extraction": allows_extraction, "allows_accessibility": allows_accessibility},
            )
        else:
            return self._make_result(
                "protected",
                "fail",
                "Document encryption blocks assistive technology access",
                {"encrypted": True, "allows_extraction": False, "allows_accessibility": False},
            )

    def _check_bookmarks(self, pdf: "pikepdf.Pdf", page_count: int) -> PDFCheckResult:
        """
        Check if the document has bookmarks (required for 20+ page documents).

        Bookmarks provide an alternative navigation mechanism.
        """
        threshold = self._checks_info.get("bookmarks", {}).get("threshold_pages", 20)

        # Check for Outlines in the catalog
        root = pdf.Root
        has_bookmarks = "/Outlines" in root
        bookmark_count = 0

        if has_bookmarks:
            outlines = root["/Outlines"]
            # Count top-level bookmarks
            if "/Count" in outlines:
                bookmark_count = abs(int(outlines["/Count"]))
            elif "/First" in outlines:
                # Count by traversing
                bookmark_count = 1  # At least one exists

        if page_count < threshold:
            if has_bookmarks:
                return self._make_result(
                    "bookmarks",
                    "pass",
                    f"Document has bookmarks ({bookmark_count} found) - not required for {page_count} pages",
                    {"has_bookmarks": True, "bookmark_count": bookmark_count, "page_count": page_count, "required": False},
                )
            else:
                return self._make_result(
                    "bookmarks",
                    "skip",
                    f"Document has {page_count} pages (bookmarks recommended for {threshold}+ pages)",
                    {"has_bookmarks": False, "bookmark_count": 0, "page_count": page_count, "required": False},
                )
        else:
            # 20+ pages - bookmarks are required
            if has_bookmarks and bookmark_count > 0:
                return self._make_result(
                    "bookmarks",
                    "pass",
                    f"Document has navigation bookmarks ({bookmark_count} found)",
                    {"has_bookmarks": True, "bookmark_count": bookmark_count, "page_count": page_count, "required": True},
                )
            else:
                return self._make_result(
                    "bookmarks",
                    "fail",
                    f"Document has {page_count} pages but no bookmarks for navigation",
                    {"has_bookmarks": False, "bookmark_count": 0, "page_count": page_count, "required": True},
                )

    def _check_scanned(self, pdf: "pikepdf.Pdf") -> PDFCheckResult:
        """
        Check if the PDF is a scanned/image-only document.

        Scanned PDFs typically have:
        - Only images on each page (no text operators)
        - Very few or no fonts
        - Large image resources

        This is a heuristic check - not 100% accurate but catches most cases.
        """
        import pikepdf

        total_pages = len(pdf.pages)
        image_only_pages = 0
        pages_checked = min(total_pages, 5)  # Sample first 5 pages

        for i in range(pages_checked):
            page = pdf.pages[i]

            # Check if page has significant text content
            has_text = False
            has_images = False

            try:
                # Get page contents
                if "/Contents" in page:
                    contents = page["/Contents"]
                    if isinstance(contents, pikepdf.Array):
                        content_stream = b"".join(
                            pikepdf.Object.parse(obj).read_bytes()
                            if hasattr(obj, "read_bytes") else b""
                            for obj in contents
                        )
                    elif hasattr(contents, "read_bytes"):
                        content_stream = contents.read_bytes()
                    else:
                        content_stream = b""

                    # Look for text operators (Tj, TJ, ', ")
                    text_operators = [b"Tj", b"TJ", b"'", b'"']
                    for op in text_operators:
                        if op in content_stream:
                            has_text = True
                            break

                    # Look for image operators (Do with XObject reference)
                    if b"Do" in content_stream:
                        has_images = True

                # Check for XObject images
                if "/Resources" in page:
                    resources = page["/Resources"]
                    if "/XObject" in resources:
                        xobjects = resources["/XObject"]
                        for key in xobjects.keys():
                            xobj = xobjects[key]
                            if "/Subtype" in xobj and str(xobj["/Subtype"]) == "/Image":
                                has_images = True
                                break
            except Exception:
                # If we can't parse, assume it's not scanned
                continue

            if has_images and not has_text:
                image_only_pages += 1

        # If most sampled pages are image-only, flag as scanned
        threshold_ratio = 0.8
        if pages_checked > 0 and (image_only_pages / pages_checked) >= threshold_ratio:
            return self._make_result(
                "scanned",
                "fail",
                f"Document appears to be scanned/image-only ({image_only_pages}/{pages_checked} sampled pages have no text)",
                {"image_only_pages": image_only_pages, "pages_checked": pages_checked, "is_scanned": True},
            )
        else:
            return self._make_result(
                "scanned",
                "pass",
                "Document contains text content (not a scanned image)",
                {"image_only_pages": image_only_pages, "pages_checked": pages_checked, "is_scanned": False},
            )

    def _check_figure_alt_text(self, pdf: "pikepdf.Pdf") -> PDFCheckResult:
        """
        Check if all Figure tags in the structure tree have alt text.

        PDF/UA requires that Figure elements have an Alt attribute providing
        a text alternative for screen readers.
        """
        import pikepdf

        root = pdf.Root

        # If not tagged, skip this check (handled by tagged check)
        if "/StructTreeRoot" not in root:
            return self._make_result(
                "figure_alt_text",
                "skip",
                "Document is not tagged - cannot check Figure alt text",
                {"figures_total": 0, "figures_missing_alt": 0, "skipped": True},
            )

        struct_root = root["/StructTreeRoot"]

        # Count Figure tags and check for Alt attribute
        figures_total = 0
        figures_missing_alt = 0
        figures_with_alt = 0
        missing_examples: list[str] = []

        def traverse(element, path: str = ""):
            nonlocal figures_total, figures_missing_alt, figures_with_alt, missing_examples

            if not isinstance(element, pikepdf.Dictionary):
                return

            # Get structure type
            struct_type = str(element.get("/S", "")).lstrip("/")

            # Check if this is a Figure element
            if struct_type == "Figure":
                figures_total += 1

                # Check for Alt attribute (alternative text)
                has_alt = "/Alt" in element
                if has_alt:
                    alt_value = element["/Alt"]
                    # Check if alt text is non-empty
                    alt_str = str(alt_value) if alt_value else ""
                    if alt_str.strip():
                        figures_with_alt += 1
                    else:
                        figures_missing_alt += 1
                        if len(missing_examples) < 5:
                            missing_examples.append(f"{path}/Figure (empty alt)")
                else:
                    figures_missing_alt += 1
                    if len(missing_examples) < 5:
                        missing_examples.append(f"{path}/Figure")

            # Traverse children
            if "/K" in element:
                kids = element["/K"]
                if isinstance(kids, pikepdf.Array):
                    for i, child in enumerate(kids):
                        child_path = f"{path}/{struct_type}[{i}]" if struct_type else path
                        traverse(child, child_path)
                elif isinstance(kids, pikepdf.Dictionary):
                    child_path = f"{path}/{struct_type}" if struct_type else path
                    traverse(kids, child_path)

        traverse(struct_root)

        # Determine result
        if figures_total == 0:
            return self._make_result(
                "figure_alt_text",
                "pass",
                "No Figure tags found in document",
                {"figures_total": 0, "figures_missing_alt": 0, "figures_with_alt": 0},
            )
        elif figures_missing_alt == 0:
            return self._make_result(
                "figure_alt_text",
                "pass",
                f"All {figures_total} Figure tag{'s' if figures_total != 1 else ''} have alternative text",
                {"figures_total": figures_total, "figures_missing_alt": 0, "figures_with_alt": figures_with_alt},
            )
        else:
            percentage_missing = (figures_missing_alt / figures_total) * 100
            return self._make_result(
                "figure_alt_text",
                "fail",
                f"{figures_missing_alt} of {figures_total} Figure tags ({percentage_missing:.0f}%) missing alternative text",
                {
                    "figures_total": figures_total,
                    "figures_missing_alt": figures_missing_alt,
                    "figures_with_alt": figures_with_alt,
                    "missing_examples": missing_examples,
                },
            )


# ============================================================================
# VeraPDFChecker - Full PDF/UA validation via Docker
# ============================================================================


class VeraPDFChecker:
    """
    Full PDF/UA validation using veraPDF.

    Supports two modes:
    1. Native installation (preferred): Uses locally installed verapdf command
    2. Docker: Uses ghcr.io/verapdf/cli container (x86-only, may not work on Apple Silicon)

    veraPDF is the industry-standard open-source PDF validator that
    provides comprehensive Matterhorn Protocol compliance checking.

    Supported profiles:
    - ua1: PDF/UA-1 (ISO 14289-1)
    - ua2: PDF/UA-2 (ISO 14289-2)
    - wtpdf: WTPDF 1.0 Accessibility
    """

    DOCKER_IMAGE = "ghcr.io/verapdf/cli:latest"
    VALID_PROFILES = ("ua1", "ua2", "wtpdf")

    def __init__(self):
        self._docker_installed: bool | None = None
        self._docker_available: bool | None = None
        self._image_available: bool | None = None
        self._native_available: bool | None = None

    def is_native_available(self) -> bool:
        """Check if veraPDF is installed natively (e.g., via Homebrew).

        Note: Java startup can be slow (10-15s on first run), so we use
        `which` instead of running verapdf directly for faster detection.
        """
        if self._native_available is not None:
            return self._native_available

        try:
            # Use 'which' for fast detection (avoids Java startup time)
            result = subprocess.run(
                ["which", "verapdf"],
                capture_output=True,
                timeout=2,
            )
            self._native_available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._native_available = False

        return self._native_available

    def is_docker_installed(self) -> bool:
        """Check if Docker is installed (but not necessarily running).

        Uses 'which docker' for fast detection without requiring the daemon.
        """
        if self._docker_installed is not None:
            return self._docker_installed

        try:
            result = subprocess.run(
                ["which", "docker"],
                capture_output=True,
                timeout=2,
            )
            self._docker_installed = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._docker_installed = False

        return self._docker_installed

    def is_docker_available(self) -> bool:
        """Check if Docker is installed and running (daemon is active)."""
        if self._docker_available is not None:
            return self._docker_available

        # First check if Docker is installed at all
        if not self.is_docker_installed():
            self._docker_available = False
            return False

        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=10,
            )
            self._docker_available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._docker_available = False

        return self._docker_available

    def is_image_available(self) -> bool:
        """Check if the veraPDF Docker image is available locally."""
        if self._image_available is not None:
            return self._image_available

        if not self.is_docker_available():
            self._image_available = False
            return False

        try:
            result = subprocess.run(
                ["docker", "images", "-q", self.DOCKER_IMAGE],
                capture_output=True,
                text=True,
                timeout=10,
            )
            self._image_available = bool(result.stdout.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            self._image_available = False

        return self._image_available

    def pull_image(self, quiet: bool = False) -> bool:
        """
        Pull the veraPDF Docker image.

        Args:
            quiet: If True, suppress output

        Returns:
            True if pull was successful
        """
        if not self.is_docker_available():
            return False

        try:
            args = ["docker", "pull", self.DOCKER_IMAGE]
            if quiet:
                result = subprocess.run(args, capture_output=True, timeout=300)
            else:
                result = subprocess.run(args, timeout=300)

            if result.returncode == 0:
                self._image_available = True
                return True
        except subprocess.TimeoutExpired:
            pass

        return False

    def check(
        self,
        file_path: Path | str,
        profile: str = "ua1",
        timeout: int = 120,
        force_docker: bool = False,
    ) -> VeraPDFResult:
        """
        Run veraPDF validation on a PDF file.

        Prefers native veraPDF installation (e.g., from Homebrew) for better
        performance and Apple Silicon compatibility. Falls back to Docker if
        native is not available.

        Args:
            file_path: Path to the PDF file
            profile: Validation profile (ua1, ua2, or wtpdf)
            timeout: Maximum time in seconds to wait for validation
            force_docker: If True, use Docker even if native is available

        Returns:
            VeraPDFResult with compliance status and violations

        Raises:
            RuntimeError: If neither native nor Docker veraPDF is available
            ValueError: If profile is not valid
            FileNotFoundError: If the PDF file doesn't exist
        """
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        if profile not in self.VALID_PROFILES:
            raise ValueError(f"Invalid profile '{profile}'. Valid profiles: {', '.join(self.VALID_PROFILES)}")

        # Try native veraPDF first (preferred, especially on Apple Silicon)
        if not force_docker and self.is_native_available():
            return self._check_native(file_path, profile, timeout)

        # Fall back to Docker
        if not self.is_docker_available():
            if self.is_docker_installed():
                # Docker is installed but not running
                raise RuntimeError(
                    "Docker is installed but not running.\n"
                    "Options:\n"
                    "  1. Start Docker Desktop or run: open -a Docker\n"
                    "  2. Install veraPDF natively (recommended): brew install verapdf"
                )
            else:
                raise RuntimeError(
                    "veraPDF is not available.\n"
                    "Install options:\n"
                    "  1. Native (recommended): brew install verapdf\n"
                    "  2. Docker: docker pull ghcr.io/verapdf/cli:latest"
                )

        if not self.is_image_available():
            raise RuntimeError(
                f"veraPDF Docker image not found. Pull it with:\n"
                f"  docker pull {self.DOCKER_IMAGE}\n"
                f"Or install natively: brew install verapdf"
            )

        return self._check_docker(file_path, profile, timeout)

    def _check_native(
        self,
        file_path: Path,
        profile: str,
        timeout: int,
    ) -> VeraPDFResult:
        """Run veraPDF using native installation."""
        cmd = [
            "verapdf",
            "-f", profile,
            "--format", "json",
            str(file_path),
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"veraPDF validation timed out after {timeout} seconds")

        return self._parse_output(result.stdout, result.stderr, profile)

    def _check_docker(
        self,
        file_path: Path,
        profile: str,
        timeout: int,
    ) -> VeraPDFResult:
        """Run veraPDF using Docker container."""
        file_dir = file_path.parent
        file_name = file_path.name

        cmd = [
            "docker", "run", "--rm",
            "-v", f"{file_dir}:/data:ro",
            self.DOCKER_IMAGE,
            "-f", profile,
            "--format", "json",
            f"/data/{file_name}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"veraPDF validation timed out after {timeout} seconds")

        # Check for architecture mismatch or Java errors in stderr
        if result.stderr:
            stderr_lower = result.stderr.lower()
            if "does not match the detected host platform" in stderr_lower:
                raise RuntimeError(
                    "veraPDF Docker image is x86-only and doesn't run natively on Apple Silicon.\n"
                    "Options:\n"
                    "  1. Install veraPDF natively: brew install verapdf\n"
                    "  2. Use basic checks only: inspekt pdf check file.pdf --engine basic"
                )
            if "noclassdeffounderror" in stderr_lower or "exception" in stderr_lower:
                raise RuntimeError(
                    f"veraPDF encountered a Java error (possibly architecture incompatibility).\n"
                    f"Try installing veraPDF natively: brew install verapdf\n"
                    f"Error: {result.stderr[:300]}"
                )

        # Parse the JSON output
        return self._parse_output(result.stdout, result.stderr, profile)

    def _parse_output(self, json_output: str, stderr: str, profile: str) -> VeraPDFResult:
        """Parse veraPDF JSON output into a VeraPDFResult."""
        # Check if output contains Java exception mixed with JSON (truncated output)
        if "Exception" in json_output or "Error" in json_output:
            # Try to extract just the JSON part
            try:
                # Find the start of the JSON
                json_start = json_output.find('{"report"')
                if json_start >= 0:
                    # Try to find a complete JSON object
                    json_output = json_output[json_start:]
            except Exception:
                pass

        try:
            data = json.loads(json_output)
        except json.JSONDecodeError:
            # Check if this looks like an architecture/Java issue
            error_msg = "Failed to parse veraPDF output"
            if stderr and ("exception" in stderr.lower() or "error" in stderr.lower()):
                error_msg = (
                    "veraPDF crashed during validation. This often happens on Apple Silicon Macs.\n"
                    "Try: brew install verapdf (for native ARM64 support)"
                )
            else:
                error_msg = f"Failed to parse veraPDF output: {json_output[:150]}..."

            return VeraPDFResult(
                profile=profile,
                compliant=False,
                violations=[
                    VeraPDFViolation(
                        rule_id="parse-error",
                        specification="veraPDF",
                        clause="N/A",
                        test_number=0,
                        description=error_msg,
                        severity="critical",
                    )
                ],
                passed_rules=0,
                failed_rules=1,
            )

        # Navigate the veraPDF JSON structure
        # Note: veraPDF wraps results in a "report" object
        if "report" in data:
            data = data["report"]

        violations = []
        passed_rules = 0
        failed_rules = 0
        processing_time = None
        verapdf_version = None
        compliant = True

        # Extract version info (releaseDetails is an array of components)
        if "buildInformation" in data:
            build_info = data["buildInformation"]
            if "releaseDetails" in build_info:
                release_details = build_info["releaseDetails"]
                if isinstance(release_details, list) and release_details:
                    # Get version from first component (core)
                    verapdf_version = release_details[0].get("version")
                elif isinstance(release_details, dict):
                    verapdf_version = release_details.get("version")

        # Process validation results
        if "jobs" in data and data["jobs"]:
            job = data["jobs"][0]

            # Get processing time
            if "duration" in job:
                duration = job["duration"]
                processing_time = duration.get("finish", 0) - duration.get("start", 0)

            # Get validation result (can be array or object)
            val_results = job.get("validationResult", [])
            if isinstance(val_results, dict):
                val_results = [val_results]
            elif not isinstance(val_results, list):
                val_results = []

            for val_result in val_results:
                # Check compliance
                if "compliant" in val_result:
                    compliant = compliant and val_result.get("compliant", False)
                else:
                    # If no explicit compliant field, check if there are failed rules
                    details = val_result.get("details", {})
                    if details.get("failedRules", 0) > 0:
                        compliant = False

                # Count passed/failed
                details = val_result.get("details", {})
                passed_rules += details.get("passedRules", 0)
                failed_rules += details.get("failedRules", 0)

                # Extract violations from ruleSummaries
                if "ruleSummaries" in details:
                    for rule_summary in details["ruleSummaries"]:
                        if rule_summary.get("status") == "failed" or rule_summary.get("ruleStatus") == "FAILED":
                            spec = rule_summary.get("specification", "")
                            clause = rule_summary.get("clause", "")
                            test_num = rule_summary.get("testNumber", 0)
                            desc = rule_summary.get("description", "")

                            # Determine severity based on specification
                            severity = "serious"
                            if "shall" in desc.lower():
                                severity = "critical"

                            # Get context and location from checks
                            context = None
                            obj_type = None
                            page_number = None
                            bbox = None
                            location_path = None

                            if "checks" in rule_summary:
                                checks = rule_summary["checks"]
                                if checks:
                                    first_check = checks[0]
                                    context = first_check.get("context")
                                    obj_type = first_check.get("object")

                                    # Extract location data for issue visualization
                                    location = first_check.get("location", "")
                                    if location:
                                        location_path = location

                                        # Extract page number from location path
                                        # Format: root/document[0]/pages[3]/... (0-indexed)
                                        page_match = re.search(r'pages\[(\d+)\]', location)
                                        if page_match:
                                            page_number = int(page_match.group(1))

                                        # Extract bounding box coordinates
                                        # Format: boundingBox[x1,y1,x2,y2]
                                        bbox_match = re.search(
                                            r'boundingBox\[([\d.]+),([\d.]+),([\d.]+),([\d.]+)\]',
                                            location
                                        )
                                        if bbox_match:
                                            bbox = (
                                                float(bbox_match.group(1)),
                                                float(bbox_match.group(2)),
                                                float(bbox_match.group(3)),
                                                float(bbox_match.group(4)),
                                            )

                            violations.append(
                                VeraPDFViolation(
                                    rule_id=f"{spec}-{clause}-{test_num}",
                                    specification=spec,
                                    clause=clause,
                                    test_number=test_num,
                                    description=desc,
                                    severity=severity,
                                    object_type=obj_type,
                                    context=context,
                                    page_number=page_number,
                                    bbox=bbox,
                                    location_path=location_path,
                                )
                            )

        return VeraPDFResult(
            profile=profile,
            compliant=compliant,
            violations=violations,
            passed_rules=passed_rules,
            failed_rules=failed_rules,
            processing_time_ms=processing_time,
            verapdf_version=verapdf_version,
        )


# ============================================================================
# Combined Checker
# ============================================================================


@dataclass
class PDFFullResult:
    """Combined result from basic, simple, and veraPDF checks."""

    basic: PDFBasicResult
    verapdf: VeraPDFResult | None = None
    simple: "SimplePDFResult | None" = None  # From SimplePDFChecker


# Import SimplePDFResult for type checking
if TYPE_CHECKING:
    from inspekt.services.simple_pdf_checker import SimplePDFResult


def check_pdf(
    file_path: Path | str,
    engine: Literal["basic", "simple", "vera", "all"] = "basic",
    vera_profile: str = "ua1",
) -> PDFFullResult:
    """
    Convenience function to check a PDF with specified engines.

    Args:
        file_path: Path to the PDF file
        engine: Which checks to run - "basic", "simple", "vera", or "all"
        vera_profile: veraPDF profile (ua1, ua2, wtpdf)

    Returns:
        PDFFullResult with results from requested engines

    Engines:
        basic: 6 fundamental checks using pikepdf
        simple: 11 checks based on Luxembourg simplA11yPDFCrawler methodology
        vera: Full PDF/UA validation using veraPDF
        all: Run all engines (basic, simple, vera)
    """
    basic_checker = PDFBasicChecker()
    basic_result = basic_checker.check(file_path)

    simple_result = None
    if engine in ("simple", "all"):
        from inspekt.services.simple_pdf_checker import SimplePDFChecker
        simple_checker = SimplePDFChecker()
        simple_result = simple_checker.check(file_path)

    vera_result = None
    if engine in ("vera", "all"):
        vera_checker = VeraPDFChecker()
        vera_result = vera_checker.check(file_path, profile=vera_profile)

    return PDFFullResult(basic=basic_result, verapdf=vera_result, simple=simple_result)
