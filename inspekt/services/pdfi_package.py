"""
PDFI Package Generator.

Creates self-contained .pdfi packages containing:
- report.json: The accessibility report data
- source.pdf: Copy of the original PDF
- manifest.json: Package metadata and file checksums
- assets/: All images (pages, thumbnails, screenshots, etc.)

The .pdfi format is a ZIP archive with a specific structure,
similar to .docx, .epub, or .sketch files.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import shutil
import tempfile
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from inspekt.services.pdf_report_data import PDFReportData

logger = logging.getLogger(__name__)

# Package format version
PDFI_FORMAT_VERSION = "1.0"

# File extension
PDFI_EXTENSION = ".pdfi"


@dataclass
class PackageManifest:
    """Manifest for a .pdfi package."""

    format_version: str = PDFI_FORMAT_VERSION
    created_at: str = ""
    generator: str = "Inspekt PDF Checker"
    source_pdf_name: str = ""
    source_pdf_size: int = 0
    source_pdf_checksum: str = ""  # SHA-256
    report_checksum: str = ""  # SHA-256
    total_assets: int = 0
    assets: list[dict[str, Any]] = field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(asdict(self), indent=indent)


def calculate_checksum(data: bytes) -> str:
    """Calculate SHA-256 checksum of data."""
    return hashlib.sha256(data).hexdigest()


def calculate_file_checksum(path: Path) -> str:
    """Calculate SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class PDFIPackageBuilder:
    """
    Builder for .pdfi packages.

    Usage:
        with PDFIPackageBuilder(output_path) as builder:
            builder.add_source_pdf(pdf_path)
            builder.add_report(report_data)
            builder.add_page_image(page_num, image_bytes)
            builder.add_thumbnail(page_num, image_bytes)
            # ... add more assets
            builder.finalize()
    """

    def __init__(self, output_path: Path | str):
        """
        Initialize the package builder.

        Args:
            output_path: Path for the output .pdfi file (extension added if missing)
        """
        self.output_path = Path(output_path)
        if self.output_path.suffix.lower() != PDFI_EXTENSION:
            self.output_path = self.output_path.with_suffix(PDFI_EXTENSION)

        self.temp_dir: Path | None = None
        self.manifest = PackageManifest(created_at=datetime.now().isoformat())
        self.report_data: dict[str, Any] | None = None
        self._finalized = False

    def __enter__(self) -> "PDFIPackageBuilder":
        """Create temporary directory for building the package."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pdfi_"))
        # Create directory structure
        (self.temp_dir / "assets" / "pages").mkdir(parents=True)
        (self.temp_dir / "assets" / "thumbnails").mkdir(parents=True)
        (self.temp_dir / "assets" / "cover").mkdir(parents=True)
        (self.temp_dir / "assets" / "screenshots").mkdir(parents=True)
        (self.temp_dir / "assets" / "untagged").mkdir(parents=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up temporary directory."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def add_source_pdf(self, pdf_path: Path | str) -> None:
        """
        Add the source PDF to the package.

        Args:
            pdf_path: Path to the original PDF file
        """
        if not self.temp_dir:
            raise RuntimeError("Builder not initialized. Use 'with' statement.")

        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        # Copy PDF to temp directory
        dest_path = self.temp_dir / "source.pdf"
        shutil.copy2(pdf_path, dest_path)

        # Update manifest
        self.manifest.source_pdf_name = pdf_path.name
        self.manifest.source_pdf_size = dest_path.stat().st_size
        self.manifest.source_pdf_checksum = calculate_file_checksum(dest_path)

        logger.debug(f"Added source PDF: {pdf_path.name} ({self.manifest.source_pdf_size} bytes)")

    def add_report(self, report: "PDFReportData | dict[str, Any]") -> None:
        """
        Add the report data to the package.

        Args:
            report: PDFReportData instance or dict
        """
        if not self.temp_dir:
            raise RuntimeError("Builder not initialized. Use 'with' statement.")

        # Convert to dict if needed
        if hasattr(report, "to_dict"):
            self.report_data = report.to_dict()
        else:
            self.report_data = dict(report)

        # Remove any embedded base64 data - we'll reference assets instead
        self._strip_embedded_data()

    def _strip_embedded_data(self) -> None:
        """Remove embedded base64 data from report, replacing with asset references."""
        if not self.report_data:
            return

        # Strip cover image base64
        if self.report_data.get("cover_image") and self.report_data["cover_image"].get("image_base64"):
            # Save the image first
            b64_data = self.report_data["cover_image"]["image_base64"]
            if b64_data:
                self._save_base64_asset(b64_data, "cover", "cover.png")
            self.report_data["cover_image"]["image_base64"] = None
            self.report_data["cover_image"]["asset_path"] = "assets/cover/cover.png"

        # Strip issue screenshot base64
        if self.report_data.get("issue_screenshots"):
            for i, screenshot in enumerate(self.report_data["issue_screenshots"]):
                if screenshot.get("screenshot_base64"):
                    filename = f"issue-{i + 1:03d}.png"
                    self._save_base64_asset(screenshot["screenshot_base64"], "screenshots", filename)
                    screenshot["screenshot_base64"] = None
                    screenshot["asset_path"] = f"assets/screenshots/{filename}"

        # Strip contrast analysis screenshots
        if self.report_data.get("contrast_analysis") and self.report_data["contrast_analysis"].get("issues"):
            for i, issue in enumerate(self.report_data["contrast_analysis"]["issues"]):
                if issue.get("screenshot_base64"):
                    filename = f"contrast-{i + 1:03d}.png"
                    self._save_base64_asset(issue["screenshot_base64"], "screenshots", filename)
                    issue["screenshot_base64"] = None
                    issue["asset_path"] = f"assets/screenshots/{filename}"

        # Strip content audit thumbnails
        if self.report_data.get("content_audit") and self.report_data["content_audit"].get("images"):
            for img in self.report_data["content_audit"]["images"]:
                if img.get("thumbnail_base64"):
                    filename = f"img-p{img.get('page', 0)}-{img.get('index', 0)}.png"
                    self._save_base64_asset(img["thumbnail_base64"], "untagged", filename)
                    img["thumbnail_base64"] = None
                    img["asset_path"] = f"assets/untagged/{filename}"

        # Strip text layer thumbnails
        if self.report_data.get("text_layer") and self.report_data["text_layer"].get("page_comparisons"):
            for comp in self.report_data["text_layer"]["page_comparisons"]:
                if comp.get("thumbnail_base64"):
                    filename = f"textlayer-p{comp.get('page', 0)}.png"
                    self._save_base64_asset(comp["thumbnail_base64"], "screenshots", filename)
                    comp["thumbnail_base64"] = None
                    comp["asset_path"] = f"assets/screenshots/{filename}"

    def _save_base64_asset(self, b64_data: str, subfolder: str, filename: str) -> None:
        """Save base64-encoded data as an asset file."""
        if not self.temp_dir:
            return

        # Handle data URL prefix
        if b64_data.startswith("data:"):
            # Extract base64 part after comma
            b64_data = b64_data.split(",", 1)[1] if "," in b64_data else b64_data

        try:
            image_bytes = base64.b64decode(b64_data)
            dest_path = self.temp_dir / "assets" / subfolder / filename
            dest_path.write_bytes(image_bytes)
            self._add_asset_to_manifest(f"assets/{subfolder}/{filename}", len(image_bytes))
        except Exception as e:
            logger.warning(f"Failed to save asset {filename}: {e}")

    def _add_asset_to_manifest(self, path: str, size: int, checksum: str | None = None) -> None:
        """Add an asset entry to the manifest."""
        if not checksum and self.temp_dir:
            full_path = self.temp_dir / path
            if full_path.exists():
                checksum = calculate_file_checksum(full_path)

        self.manifest.assets.append({
            "path": path,
            "size": size,
            "checksum": checksum,
        })
        self.manifest.total_assets = len(self.manifest.assets)

    def add_page_image(self, page_num: int, image_bytes: bytes) -> str:
        """
        Add a full-size page image to the package.

        Args:
            page_num: Page number (1-indexed)
            image_bytes: PNG image data

        Returns:
            Asset path (e.g., "assets/pages/page-001.png")
        """
        if not self.temp_dir:
            raise RuntimeError("Builder not initialized. Use 'with' statement.")

        filename = f"page-{page_num:03d}.png"
        dest_path = self.temp_dir / "assets" / "pages" / filename
        dest_path.write_bytes(image_bytes)

        asset_path = f"assets/pages/{filename}"
        self._add_asset_to_manifest(asset_path, len(image_bytes))

        logger.debug(f"Added page image: {filename} ({len(image_bytes)} bytes)")
        return asset_path

    def add_thumbnail(self, page_num: int, image_bytes: bytes) -> str:
        """
        Add a page thumbnail to the package.

        Args:
            page_num: Page number (1-indexed)
            image_bytes: PNG image data

        Returns:
            Asset path (e.g., "assets/thumbnails/page-001.png")
        """
        if not self.temp_dir:
            raise RuntimeError("Builder not initialized. Use 'with' statement.")

        filename = f"page-{page_num:03d}.png"
        dest_path = self.temp_dir / "assets" / "thumbnails" / filename
        dest_path.write_bytes(image_bytes)

        asset_path = f"assets/thumbnails/{filename}"
        self._add_asset_to_manifest(asset_path, len(image_bytes))

        logger.debug(f"Added thumbnail: {filename} ({len(image_bytes)} bytes)")
        return asset_path

    def add_page_pdf(self, page_num: int, pdf_bytes: bytes) -> str:
        """
        Add a single-page PDF to the package for vector rendering.

        Args:
            page_num: Page number (1-indexed)
            pdf_bytes: Single-page PDF data

        Returns:
            Asset path (e.g., "assets/pages/page-001.pdf")
        """
        if not self.temp_dir:
            raise RuntimeError("Builder not initialized. Use 'with' statement.")

        filename = f"page-{page_num:03d}.pdf"
        dest_path = self.temp_dir / "assets" / "pages" / filename
        dest_path.write_bytes(pdf_bytes)

        asset_path = f"assets/pages/{filename}"
        self._add_asset_to_manifest(asset_path, len(pdf_bytes))

        logger.debug(f"Added page PDF: {filename} ({len(pdf_bytes)} bytes)")
        return asset_path

    def add_preview_data(self, preview_pages: list[dict[str, Any]], structure_tree: dict | None = None) -> None:
        """
        Add interactive preview data to the report.

        Args:
            preview_pages: List of page data dicts with tags, dimensions, etc.
            structure_tree: Optional structure tree for the tree panel
        """
        if not self.report_data:
            raise RuntimeError("Report must be added before preview data.")

        # Add preview pages to report (image paths reference assets)
        self.report_data["preview_pages"] = preview_pages

        if structure_tree:
            self.report_data["preview_structure_tree"] = structure_tree

    def finalize(self) -> Path:
        """
        Finalize the package by writing all files and creating the ZIP.

        Returns:
            Path to the created .pdfi file
        """
        if not self.temp_dir:
            raise RuntimeError("Builder not initialized. Use 'with' statement.")

        if self._finalized:
            raise RuntimeError("Package already finalized.")

        # Write report.json
        if self.report_data:
            report_json = json.dumps(self.report_data, indent=2, default=str)
            report_path = self.temp_dir / "report.json"
            report_path.write_text(report_json, encoding="utf-8")
            self.manifest.report_checksum = calculate_checksum(report_json.encode("utf-8"))

        # Write manifest.json
        manifest_path = self.temp_dir / "manifest.json"
        manifest_path.write_text(self.manifest.to_json(), encoding="utf-8")

        # Create ZIP file
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(self.output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in self.temp_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(self.temp_dir)
                    zf.write(file_path, arcname)

        self._finalized = True
        logger.info(f"Created PDFI package: {self.output_path} ({self.output_path.stat().st_size} bytes)")

        return self.output_path


class PDFIPackageReader:
    """
    Reader for .pdfi packages.

    Usage:
        with PDFIPackageReader(package_path) as reader:
            report = reader.get_report()
            pdf_path = reader.get_source_pdf()
            page_image = reader.get_asset("assets/pages/page-001.png")
    """

    def __init__(self, package_path: Path | str):
        """
        Initialize the package reader.

        Args:
            package_path: Path to the .pdfi file
        """
        self.package_path = Path(package_path)
        if not self.package_path.exists():
            raise FileNotFoundError(f"Package not found: {package_path}")

        self.temp_dir: Path | None = None
        self._manifest: PackageManifest | None = None
        self._report: dict[str, Any] | None = None

    def __enter__(self) -> "PDFIPackageReader":
        """Extract package to temporary directory."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pdfi_read_"))

        with zipfile.ZipFile(self.package_path, "r") as zf:
            zf.extractall(self.temp_dir)

        logger.debug(f"Extracted package to: {self.temp_dir}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up temporary directory."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    @property
    def manifest(self) -> PackageManifest:
        """Get the package manifest."""
        if not self._manifest:
            if not self.temp_dir:
                raise RuntimeError("Reader not initialized. Use 'with' statement.")

            manifest_path = self.temp_dir / "manifest.json"
            if manifest_path.exists():
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                self._manifest = PackageManifest(**data)
            else:
                self._manifest = PackageManifest()

        return self._manifest

    def get_report(self) -> dict[str, Any]:
        """Get the report data."""
        if not self._report:
            if not self.temp_dir:
                raise RuntimeError("Reader not initialized. Use 'with' statement.")

            report_path = self.temp_dir / "report.json"
            if not report_path.exists():
                raise FileNotFoundError("Package does not contain report.json")

            self._report = json.loads(report_path.read_text(encoding="utf-8"))

        return self._report

    def get_source_pdf_path(self) -> Path | None:
        """Get the path to the extracted source PDF."""
        if not self.temp_dir:
            raise RuntimeError("Reader not initialized. Use 'with' statement.")

        pdf_path = self.temp_dir / "source.pdf"
        return pdf_path if pdf_path.exists() else None

    def get_asset(self, asset_path: str) -> bytes | None:
        """
        Get an asset file's contents.

        Args:
            asset_path: Relative path within the package (e.g., "assets/pages/page-001.png")

        Returns:
            File contents as bytes, or None if not found
        """
        if not self.temp_dir:
            raise RuntimeError("Reader not initialized. Use 'with' statement.")

        full_path = self.temp_dir / asset_path
        if full_path.exists():
            return full_path.read_bytes()
        return None

    def get_asset_path(self, asset_path: str) -> Path | None:
        """
        Get the filesystem path to an extracted asset.

        Args:
            asset_path: Relative path within the package

        Returns:
            Full filesystem path, or None if not found
        """
        if not self.temp_dir:
            raise RuntimeError("Reader not initialized. Use 'with' statement.")

        full_path = self.temp_dir / asset_path
        return full_path if full_path.exists() else None

    def list_assets(self, subfolder: str | None = None) -> list[str]:
        """
        List all assets in the package.

        Args:
            subfolder: Optional subfolder to filter (e.g., "pages", "thumbnails")

        Returns:
            List of asset paths
        """
        if not self.temp_dir:
            raise RuntimeError("Reader not initialized. Use 'with' statement.")

        assets_dir = self.temp_dir / "assets"
        if subfolder:
            assets_dir = assets_dir / subfolder

        if not assets_dir.exists():
            return []

        return [
            str(p.relative_to(self.temp_dir))
            for p in assets_dir.rglob("*")
            if p.is_file()
        ]

    def extract_to(self, destination: Path | str) -> Path:
        """
        Extract the entire package to a destination directory.

        Args:
            destination: Target directory

        Returns:
            Path to the extraction directory
        """
        destination = Path(destination)
        destination.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(self.package_path, "r") as zf:
            zf.extractall(destination)

        return destination


# =============================================================================
# High-level Package Generation
# =============================================================================


def generate_pdfi_package(
    pdf_path: Path | str,
    report_data: "PDFReportData | dict[str, Any]",
    output_path: Path | str,
    config: dict | None = None,
    include_preview: bool = True,
    preview_pages: int = 5,
    content_audit_result: Any = None,
) -> Path:
    """
    Generate a complete .pdfi package from a PDF and its report.

    Args:
        pdf_path: Path to the source PDF
        report_data: The accessibility report data
        output_path: Where to save the .pdfi file
        config: Optional configuration dict
        include_preview: Whether to generate interactive preview data
        preview_pages: Number of pages to render for preview (0 = all)
        content_audit_result: Optional content audit result for untagged images

    Returns:
        Path to the created .pdfi file
    """
    import fitz  # PyMuPDF

    pdf_path = Path(pdf_path)
    output_path = Path(output_path)
    config = config or {}

    logger.info(f"Generating PDFI package for: {pdf_path.name}")

    with PDFIPackageBuilder(output_path) as builder:
        # Add the source PDF
        builder.add_source_pdf(pdf_path)

        # Add the report data
        builder.add_report(report_data)

        # Generate and add preview data if requested
        if include_preview:
            preview_data = _generate_preview_data(
                pdf_path,
                builder,
                num_pages=preview_pages,
                config=config,
                content_audit_result=content_audit_result,
            )
            if preview_data:
                builder.add_preview_data(
                    preview_pages=preview_data["pages"],
                    structure_tree=preview_data.get("structure_tree"),
                )

        return builder.finalize()


def _generate_preview_data(
    pdf_path: Path,
    builder: PDFIPackageBuilder,
    num_pages: int = 5,
    config: dict | None = None,
    content_audit_result: Any = None,
) -> dict | None:
    """
    Generate preview page data and add images to the package.

    Args:
        pdf_path: Path to the PDF
        builder: The package builder to add images to
        num_pages: Number of pages to render (0 = all)
        config: Configuration dict
        content_audit_result: Optional content audit for untagged images

    Returns:
        Dict with 'pages' and 'structure_tree' keys
    """
    import fitz

    config = config or {}

    try:
        from inspekt.services.pdf_tag_visualizer import PDFTagVisualizer
    except ImportError:
        logger.warning("PDFTagVisualizer not available, skipping preview generation")
        return None

    preview_pages = []
    structure_tree = None

    try:
        with PDFTagVisualizer(pdf_path) as visualizer:
            if not visualizer._fitz_doc:
                return None

            total_pages = len(visualizer._fitz_doc)

            # Calculate pages to render
            if num_pages == 0 or num_pages >= total_pages:
                pages_to_render = list(range(total_pages))
            else:
                pages_to_render = list(range(min(num_pages, total_pages)))

            # Extract structure tree
            try:
                from inspekt.services.pdf_structure_extractor import PDFStructureExtractor

                with PDFStructureExtractor(pdf_path) as extractor:
                    result = extractor.extract()
                    if result.has_structure and result.root:
                        structure_tree = _serialize_structure_tree_for_package(result.root)
            except Exception as e:
                logger.debug(f"Failed to extract structure tree: {e}")

            # Render each page
            dpi = 150
            zoom = dpi / 72

            for page_num in pages_to_render:
                page = visualizer._fitz_doc[page_num]
                page_width = page.rect.width
                page_height = page.rect.height

                # Extract tags for this page
                tags = visualizer.extract_page_tags(page_num)

                # Render full-size page image
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                image_bytes = pix.tobytes("png")
                page_image_path = builder.add_page_image(page_num + 1, image_bytes)

                # Render thumbnail (100px height for retina)
                thumb_zoom = 100 / page_height
                thumb_mat = fitz.Matrix(thumb_zoom, thumb_zoom)
                thumb_pix = page.get_pixmap(matrix=thumb_mat, alpha=False)
                thumb_bytes = thumb_pix.tobytes("png")
                thumbnail_path = builder.add_thumbnail(page_num + 1, thumb_bytes)

                # Extract single-page PDF for vector rendering (WebKit feature)
                single_page_doc = fitz.open()
                single_page_doc.insert_pdf(visualizer._fitz_doc, from_page=page_num, to_page=page_num)
                pdf_bytes = single_page_doc.tobytes()
                single_page_doc.close()
                pdf_src_path = builder.add_page_pdf(page_num + 1, pdf_bytes)

                # Convert tags to serializable format
                tags_data = []
                figure_counter = 0

                for tag in tags:
                    tag_data = {
                        "tag_type": tag.tag_type,
                        "bbox": list(tag.bbox) if tag.bbox else None,
                        "reading_order": tag.reading_order,
                        "text_preview": tag.text_preview[:200] if tag.text_preview else None,
                        "alt_text": tag.alt_text,
                        "has_issues": tag.has_issues,
                        "detected_language": tag.detected_language,
                        "node_id": tag.node_id,
                    }

                    if tag.tag_type == "Figure":
                        tag_data["image_page"] = page_num + 1
                        tag_data["image_index"] = figure_counter
                        figure_counter += 1

                    tags_data.append(tag_data)

                # Extract untagged images for this page
                untagged_images = []
                if content_audit_result:
                    for img in getattr(content_audit_result, "images", []):
                        if img.page == page_num and img.bbox:
                            untagged_images.append({
                                "index": img.index,
                                "bbox": list(img.bbox),
                                "width": img.width,
                                "height": img.height,
                            })

                # Extract vector graphics for this page
                vector_graphics = []
                if content_audit_result:
                    for vg in getattr(content_audit_result, "vector_graphics", []):
                        if vg.page == page_num and vg.bbox:
                            vector_graphics.append({
                                "index": vg.index,
                                "bbox": list(vg.bbox),
                                "width": vg.width,
                                "height": vg.height,
                            })

                preview_pages.append({
                    "page_num": page_num + 1,  # 1-indexed
                    "page_width": page_width,
                    "page_height": page_height,
                    "dpi": dpi,
                    "page_image": page_image_path,
                    "pdf_src": pdf_src_path,  # Single-page PDF for vector rendering
                    "thumbnail": thumbnail_path,
                    "tags": tags_data,
                    "untagged_images": untagged_images,
                    "vector_graphics": vector_graphics,
                })

                logger.debug(f"Processed page {page_num + 1}: {len(tags_data)} tags")

    except Exception as e:
        logger.error(f"Failed to generate preview data: {e}")
        return None

    return {
        "pages": preview_pages,
        "structure_tree": structure_tree,
    }


def _serialize_structure_tree_for_package(node: Any, depth: int = 0) -> dict:
    """
    Serialize a structure tree node for the package.

    Args:
        node: Structure node from PDFStructureExtractor
        depth: Current depth (for limiting recursion)

    Returns:
        Serialized node dict
    """
    # Prevent infinite recursion
    if depth > 100:
        return {"tag_type": "…", "children": []}

    serialized = {
        "tag_type": getattr(node, "tag_type", "Unknown"),
        "node_id": getattr(node, "node_id", None),
        "page_number": getattr(node, "page_number", None),
        "text_content": getattr(node, "text_content", None),
        "alt_text": getattr(node, "alt_text", None),
        "is_heading": getattr(node, "is_heading", False),
        "has_issues": getattr(node, "has_issues", False),
        "children": [],
    }

    children = getattr(node, "children", [])
    if children:
        serialized["children"] = [
            _serialize_structure_tree_for_package(child, depth + 1)
            for child in children
        ]

    return serialized
