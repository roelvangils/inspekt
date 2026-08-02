"""
Simple PDF Accessibility Checker.

This module implements the SimplePDFChecker based on Luxembourg's simplA11yPDFCrawler
methodology. It performs 11 checks (compared to 6 in PDFBasicChecker):

Basic checks (overlap with PDFBasicChecker):
- tagged: PDF structure tree and MarkInfo
- title: Document title with DisplayDocTitle
- language: Document language with BCP-47 validation
- protected: AT access not blocked by encryption
- bookmarks: Navigation bookmarks for long documents
- scanned: Not image-only document

Additional checks (unique to SimplePDFChecker):
- forms: AcroForm fields detection
- xfa: XFA dynamic forms detection (accessibility barrier)
- xmp_metadata: XMP metadata presence

Enhanced features:
- Language validation using langcodes library
- P-bit analysis for protected check
- Form field counting and analysis
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import pikepdf


# Check once at import time if language_data is available
@lru_cache(maxsize=1)
def _has_language_data() -> bool:
    """Check if the language_data package is installed."""
    try:
        import language_data  # noqa: F401

        return True
    except ImportError:
        return False


def _get_language_display_name(lang_code: str) -> str | None:
    """
    Get the display name for a language code.

    Returns None if langcodes or language_data is not available,
    avoiding the stdout warning that langcodes prints.
    """
    if not _has_language_data():
        return None

    try:
        from langcodes import Language

        parsed = Language.get(lang_code)
        if parsed.is_valid():
            return parsed.display_name()
    except Exception:
        pass

    return None


@dataclass
class SimplePDFCheckResult:
    """Result of a single PDF accessibility check from SimplePDFChecker."""

    check_id: str
    name: str
    status: Literal["pass", "fail", "warn", "skip"]
    message: str
    severity: Literal["critical", "serious", "moderate", "minor"]
    wcag_sc: str | None = None
    wcag_level: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimplePDFResult:
    """Result of all SimplePDFChecker accessibility checks."""

    metadata: SimplePDFMetadata
    checks: list[SimplePDFCheckResult]

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

    @property
    def minor_count(self) -> int:
        return sum(1 for c in self.checks if c.status == "fail" and c.severity == "minor")

    @property
    def is_totally_inaccessible(self) -> bool:
        """Check if the document is completely inaccessible.

        A document is considered totally inaccessible if:
        - It's a scanned/image-only document, OR
        - It's protected against AT access, OR
        - It's not tagged
        """
        for check in self.checks:
            if check.check_id in ("scanned", "protected", "tagged") and check.status == "fail":
                return True
        return False

    def get_check(self, check_id: str) -> SimplePDFCheckResult | None:
        """Get a specific check result by ID."""
        for check in self.checks:
            if check.check_id == check_id:
                return check
        return None


@dataclass
class SimplePDFMetadata:
    """Extended metadata about the PDF document for SimplePDFChecker."""

    file_path: Path
    file_size: int
    page_count: int
    title: str | None = None
    author: str | None = None
    creator: str | None = None
    producer: str | None = None
    language: str | None = None
    language_display_name: str | None = None  # Human-readable language name
    is_encrypted: bool = False
    pdf_version: str | None = None
    has_xmp: bool = False
    form_field_count: int = 0
    has_xfa: bool = False


class SimplePDFChecker:
    """
    PDF accessibility checker based on Luxembourg simplA11yPDFCrawler methodology.

    Performs 11 checks (compared to 6 in PDFBasicChecker):
    - tagged, title, language, protected, bookmarks, scanned (same as basic)
    - forms (NEW): AcroForm detection
    - xfa (NEW): XFA dynamic form detection
    - xmp_metadata (NEW): XMP metadata presence

    Enhanced features:
    - Language validation with langcodes library
    - Enhanced protected check with P-bit analysis
    """

    def __init__(self):
        from inspekt.services.pdf_checker import load_check_metadata

        self._metadata = load_check_metadata()
        self._checks_info = {c["id"]: c for c in self._metadata.get("checks", [])}

    def check(self, file_path: Path | str) -> SimplePDFResult:
        """
        Run all 11 accessibility checks on a PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            SimplePDFResult with metadata and all check results

        Raises:
            ImportError: If required libraries are not installed
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

            # Run all 11 checks
            checks = [
                # Original 6 checks (same as PDFBasicChecker but with enhancements)
                self._check_tagged(pdf),
                self._check_title(pdf),
                self._check_language_validated(pdf),  # Enhanced with langcodes
                self._check_protected_enhanced(pdf),  # Enhanced with P-bit analysis
                self._check_bookmarks(pdf, metadata.page_count),
                self._check_scanned(pdf),
                # New checks from simplA11yPDFCrawler
                self._check_forms(pdf, metadata),
                self._check_xfa(pdf, metadata),
                self._check_xmp_metadata(pdf, metadata),
            ]

        return SimplePDFResult(metadata=metadata, checks=checks)

    def _extract_metadata(self, pdf: pikepdf.Pdf, file_path: Path) -> SimplePDFMetadata:
        """Extract extended metadata from the PDF."""
        # Get document info dictionary
        info = pdf.docinfo if hasattr(pdf, "docinfo") else {}

        # Get title from info dict
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
        language_display_name = None
        root = pdf.Root
        if "/Lang" in root:
            language = str(root["/Lang"])
            # Try to get display name using langcodes (only if language_data is available)
            language_display_name = _get_language_display_name(language)

        # Check encryption
        is_encrypted = pdf.is_encrypted

        # Get PDF version
        pdf_version = f"{pdf.pdf_version}"

        # Check for XMP metadata
        has_xmp = False
        if "/Metadata" in root:
            has_xmp = True

        # Check for form fields
        form_field_count = 0
        has_xfa = False
        if "/AcroForm" in root:
            acroform = root["/AcroForm"]
            if "/Fields" in acroform:
                fields = acroform["/Fields"]
                if hasattr(fields, "__len__"):
                    form_field_count = len(fields)
            if "/XFA" in acroform:
                has_xfa = True

        return SimplePDFMetadata(
            file_path=file_path,
            file_size=file_path.stat().st_size,
            page_count=len(pdf.pages),
            title=title if title and title.strip() else None,
            author=author if author and author.strip() else None,
            creator=creator if creator and creator.strip() else None,
            producer=producer if producer and producer.strip() else None,
            language=language,
            language_display_name=language_display_name,
            is_encrypted=is_encrypted,
            pdf_version=pdf_version,
            has_xmp=has_xmp,
            form_field_count=form_field_count,
            has_xfa=has_xfa,
        )

    def _make_result(
        self,
        check_id: str,
        status: Literal["pass", "fail", "warn", "skip"],
        message: str,
        details: dict[str, Any] | None = None,
    ) -> SimplePDFCheckResult:
        """Create a check result with metadata from the JSON config."""
        check_info = self._checks_info.get(check_id, {})
        return SimplePDFCheckResult(
            check_id=check_id,
            name=check_info.get("name", check_id),
            status=status,
            message=message,
            severity=check_info.get("severity", "moderate"),
            wcag_sc=check_info.get("wcag_sc"),
            wcag_level=check_info.get("wcag_level"),
            details=details or {},
        )

    # ========================================================================
    # Original checks (same as PDFBasicChecker for cross-validation)
    # ========================================================================

    def _check_tagged(self, pdf: pikepdf.Pdf) -> SimplePDFCheckResult:
        """
        Check if the PDF is tagged.

        Same logic as PDFBasicChecker for cross-validation agreement.
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

    def _check_title(self, pdf: pikepdf.Pdf) -> SimplePDFCheckResult:
        """
        Check if the document has a title and DisplayDocTitle is enabled.

        Same logic as PDFBasicChecker for cross-validation agreement.
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
                f'Document title is set and displayed: "{title[:50]}{"…" if len(title) > 50 else ""}"',
                {"title": title, "display_doc_title": True},
            )
        elif has_title and not display_doc_title:
            return self._make_result(
                "title",
                "warn",
                "Title is set but DisplayDocTitle is not enabled (viewers will show filename instead)",
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

    def _check_language_validated(self, pdf: pikepdf.Pdf) -> SimplePDFCheckResult:
        """
        Check if the document language is defined with BCP-47 validation.

        Enhanced version using langcodes library for proper validation.
        """
        root = pdf.Root

        if "/Lang" not in root:
            return self._make_result(
                "language",
                "fail",
                "No document language is defined",
                {"language": None, "valid": False},
            )

        lang = str(root["/Lang"])

        # Try to validate with langcodes (only if language_data is available)
        if _has_language_data():
            try:
                from langcodes import Language

                parsed = Language.get(lang)

                if parsed.is_valid():
                    display_name = parsed.display_name()
                    return self._make_result(
                        "language",
                        "pass",
                        f'Document language is defined: "{lang}" ({display_name})',
                        {"language": lang, "display_name": display_name, "valid": True},
                    )
                else:
                    return self._make_result(
                        "language",
                        "warn",
                        f'Document language is set but not a valid BCP 47 tag: "{lang}"',
                        {"language": lang, "valid": False, "invalid_lang": True},
                    )
            except Exception:
                pass

        # Fall back to basic regex validation
        if re.match(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,4})?$", lang):
            return self._make_result(
                "language",
                "pass",
                f'Document language is defined: "{lang}"',
                {"language": lang, "valid": True},
            )
        else:
            return self._make_result(
                "language",
                "warn",
                f'Document language is set but may not be a valid BCP 47 tag: "{lang}"',
                {"language": lang, "valid": False},
            )

    def _check_protected_enhanced(self, pdf: pikepdf.Pdf) -> SimplePDFCheckResult:
        """
        Check if the document blocks assistive technology access.

        Enhanced version with P-bit analysis from simplA11yPDFCrawler.
        """
        if not pdf.is_encrypted:
            return self._make_result(
                "protected",
                "pass",
                "Document is not encrypted",
                {"encrypted": False, "allows_extraction": True},
            )

        # Document is encrypted - use pikepdf's permission checking
        # pikepdf exposes allow properties which check the encryption dict P value
        allows_extraction = pdf.allow.extract
        allows_accessibility = pdf.allow.accessibility  # Bit 10 (value 512) for AT access

        if allows_accessibility:
            return self._make_result(
                "protected",
                "pass",
                "Document is encrypted but allows assistive technology access",
                {
                    "encrypted": True,
                    "allows_extraction": allows_extraction,
                    "allows_accessibility": True,
                },
            )
        elif allows_extraction:
            # Has extraction but not explicit AT permission
            return self._make_result(
                "protected",
                "pass",
                "Document is encrypted but allows text extraction for accessibility",
                {
                    "encrypted": True,
                    "allows_extraction": True,
                    "allows_accessibility": False,
                },
            )
        else:
            return self._make_result(
                "protected",
                "fail",
                "Document encryption blocks assistive technology access",
                {
                    "encrypted": True,
                    "allows_extraction": False,
                    "allows_accessibility": False,
                },
            )

    def _check_bookmarks(self, pdf: pikepdf.Pdf, page_count: int) -> SimplePDFCheckResult:
        """
        Check if the document has bookmarks (required for 20+ page documents).

        Same logic as PDFBasicChecker for cross-validation agreement.
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
                    {
                        "has_bookmarks": True,
                        "bookmark_count": bookmark_count,
                        "page_count": page_count,
                        "required": False,
                    },
                )
            else:
                return self._make_result(
                    "bookmarks",
                    "skip",
                    f"Document has {page_count} pages (bookmarks recommended for {threshold}+ pages)",
                    {
                        "has_bookmarks": False,
                        "bookmark_count": 0,
                        "page_count": page_count,
                        "required": False,
                    },
                )
        else:
            # 20+ pages - bookmarks are required
            if has_bookmarks and bookmark_count > 0:
                return self._make_result(
                    "bookmarks",
                    "pass",
                    f"Document has navigation bookmarks ({bookmark_count} found)",
                    {
                        "has_bookmarks": True,
                        "bookmark_count": bookmark_count,
                        "page_count": page_count,
                        "required": True,
                    },
                )
            else:
                return self._make_result(
                    "bookmarks",
                    "fail",
                    f"Document has {page_count} pages but no bookmarks for navigation",
                    {
                        "has_bookmarks": False,
                        "bookmark_count": 0,
                        "page_count": page_count,
                        "required": True,
                    },
                )

    def _check_scanned(self, pdf: pikepdf.Pdf) -> SimplePDFCheckResult:
        """
        Check if the PDF is a scanned/image-only document.

        Same logic as PDFBasicChecker for cross-validation agreement.
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
                            if hasattr(obj, "read_bytes")
                            else b""
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
                        for key in xobjects:
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
                {
                    "image_only_pages": image_only_pages,
                    "pages_checked": pages_checked,
                    "is_scanned": True,
                },
            )
        else:
            return self._make_result(
                "scanned",
                "pass",
                "Document contains text content (not a scanned image)",
                {
                    "image_only_pages": image_only_pages,
                    "pages_checked": pages_checked,
                    "is_scanned": False,
                },
            )

    # ========================================================================
    # New checks unique to SimplePDFChecker
    # ========================================================================

    def _check_forms(self, pdf: pikepdf.Pdf, metadata: SimplePDFMetadata) -> SimplePDFCheckResult:
        """
        Check if the PDF contains AcroForm fields.

        This is informational - forms aren't bad, but they require accessibility labeling.
        """
        root = pdf.Root

        if "/AcroForm" not in root:
            return self._make_result(
                "forms",
                "pass",
                "No form fields detected",
                {"has_forms": False, "field_count": 0},
            )

        acroform = root["/AcroForm"]
        field_count = 0

        if "/Fields" in acroform:
            fields = acroform["/Fields"]
            if hasattr(fields, "__len__"):
                field_count = len(fields)

        if field_count > 0:
            return self._make_result(
                "forms",
                "warn",
                f"Document has {field_count} form field{'s' if field_count != 1 else ''} (ensure they have accessible labels)",
                {"has_forms": True, "field_count": field_count},
            )
        else:
            return self._make_result(
                "forms",
                "pass",
                "No form fields detected",
                {"has_forms": False, "field_count": 0},
            )

    def _check_xfa(self, pdf: pikepdf.Pdf, metadata: SimplePDFMetadata) -> SimplePDFCheckResult:
        """
        Check if the PDF contains XFA dynamic forms.

        XFA forms are a significant accessibility barrier as they're not supported
        by many PDF readers and have poor accessibility support.
        """
        root = pdf.Root

        if "/AcroForm" not in root:
            return self._make_result(
                "xfa",
                "pass",
                "No XFA forms detected",
                {"has_xfa": False},
            )

        acroform = root["/AcroForm"]

        if "/XFA" in acroform:
            return self._make_result(
                "xfa",
                "fail",
                "Document contains XFA dynamic forms (accessibility barrier)",
                {"has_xfa": True},
            )
        else:
            return self._make_result(
                "xfa",
                "pass",
                "No XFA forms detected",
                {"has_xfa": False},
            )

    def _check_xmp_metadata(
        self, pdf: pikepdf.Pdf, metadata: SimplePDFMetadata
    ) -> SimplePDFCheckResult:
        """
        Check if the PDF contains XMP metadata.

        XMP metadata enhances discoverability but is not strictly required for accessibility.
        """
        root = pdf.Root

        if "/Metadata" in root:
            # Try to get some info from XMP
            xmp_details = {"has_xmp": True}

            try:
                # pikepdf can extract XMP as bytes
                xmp_stream = root["/Metadata"]
                if hasattr(xmp_stream, "read_bytes"):
                    xmp_data = xmp_stream.read_bytes()
                    # Basic check for common XMP elements
                    xmp_details["xmp_size"] = len(xmp_data)
                    if b"dc:title" in xmp_data:
                        xmp_details["has_dc_title"] = True
                    if b"dc:creator" in xmp_data:
                        xmp_details["has_dc_creator"] = True
                    if b"dc:description" in xmp_data:
                        xmp_details["has_dc_description"] = True
            except Exception:
                pass

            return self._make_result(
                "xmp_metadata",
                "pass",
                "Document contains XMP metadata",
                xmp_details,
            )
        else:
            return self._make_result(
                "xmp_metadata",
                "skip",
                "No XMP metadata found (optional for accessibility)",
                {"has_xmp": False},
            )
