"""
Progress Timing Estimation Service.

This module calculates estimated execution times for PDF accessibility check steps
based on document characteristics obtained from the pre-scan phase.

The timing constants are calibrated from empirical measurements on various
document types and sizes. They serve as estimates and actual times may vary
based on system performance, document complexity, and other factors.

Usage:
    from inspekt.services.pdf_prescan import prescan_pdf
    from inspekt.services.progress_timing import estimate_timing

    prescan = prescan_pdf(Path("document.pdf"))
    timing = estimate_timing(prescan, config={"ocr": True, "contrast": True})
    print(f"Estimated total time: {timing.total_estimated_ms}ms")
"""

from dataclasses import asdict, dataclass, field

from inspekt.services.pdf_prescan import PDFPrescanResult

# =============================================================================
# Timing Constants (milliseconds) - Calibrated from benchmarks
# =============================================================================

# These constants represent typical execution times observed on a modern machine.
# They include base overhead plus per-unit (page/image) costs.

TIMING_CONSTANTS = {
    # Core accessibility checks (tagged, title, language, protection, bookmarks, scanned, alt text)
    "core": {
        "base": 500,  # Fixed overhead
        "per_page": 5,  # Minimal per-page cost (structure inspection)
        "per_image": 10,  # Alt text presence check
    },
    # OCR text layer analysis
    "ocr": {
        "base": 2000,  # Tesseract initialization
        "per_page": 1500,  # OCR + comparison per page
        "first_page_extra": 500,  # Model loading on first page
    },
    # Color contrast analysis
    "contrast": {
        "base": 1000,  # Setup and rendering prep
        "per_page": 500,  # Render + analyze per page
    },
    # Structure tree extraction
    "structure": {
        "base": 500,  # Tree setup
        "per_page": 50,  # Tag traversal per page
    },
    # Content extraction (images, tables, forms, links)
    "content": {
        "base": 1000,  # Setup
        "per_page": 100,  # Page scan
        "per_image": 50,  # Image metadata extraction
    },
    # Image classification (local ML)
    "classify": {
        "base": 1500,  # Model loading
        "per_image": 300,  # Classification per image
        "batch_size": 10,  # Images processed per batch
    },
    # Preview generation (page renders, tag overlays, thumbnails)
    "preview": {
        "base": 500,  # Setup
        "per_page": 200,  # Render + overlay per page
    },
    # Report building
    "build": {
        "base": 500,  # Template prep
        "per_page": 10,  # Data compilation
    },
    # Report saving
    "save": {
        "base": 200,  # File I/O
        "per_page": 5,  # Asset writing
    },
}


@dataclass
class SubstepTiming:
    """Timing information for a substep within a main step."""

    substep_id: str
    label: str
    estimated_ms: int

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class StepTiming:
    """Timing information for a main progress step."""

    step_id: str
    label: str
    estimated_ms: int
    will_run: bool
    substeps: list[SubstepTiming] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "step_id": self.step_id,
            "label": self.label,
            "estimated_ms": self.estimated_ms,
            "will_run": self.will_run,
            "substeps": [s.to_dict() for s in self.substeps],
        }
        return result


@dataclass
class TimingEstimate:
    """Complete timing estimate for all steps."""

    total_estimated_ms: int
    steps: list[StepTiming]

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_estimated_ms": self.total_estimated_ms,
            "steps": [s.to_dict() for s in self.steps],
        }

    def get_step(self, step_id: str) -> StepTiming | None:
        """Get timing for a specific step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None


def estimate_timing(
    prescan: PDFPrescanResult,
    config: dict | None = None,
) -> TimingEstimate:
    """
    Calculate estimated execution time for each step based on document characteristics.

    Args:
        prescan: Result from prescan_pdf() with document characteristics
        config: Configuration options that affect which steps run:
            - ocr: bool (default True) - Run OCR text layer analysis
            - contrast: bool (default True) - Run color contrast analysis
            - classify: bool (default True) - Run image classification
            - preview: bool (default True) - Generate interactive preview
            - max_ocr_pages: int (default 10) - Max pages for OCR
            - max_contrast_pages: int (default 5) - Max pages for contrast
            - max_classify_images: int (default 100) - Max images for classification
            - max_preview_pages: int (default 5) - Max pages for preview

    Returns:
        TimingEstimate with per-step and total timing estimates
    """
    if config is None:
        config = {}

    steps: list[StepTiming] = []
    page_count = prescan.page_count
    image_count = prescan.estimated_image_count

    # Get configuration with defaults
    do_ocr = config.get("ocr", True)
    do_contrast = config.get("contrast", True)
    do_classify = config.get("classify", True)
    do_preview = config.get("preview", True)

    max_ocr_pages = min(config.get("max_ocr_pages", 10), page_count)
    max_contrast_pages = min(config.get("max_contrast_pages", 5), page_count)
    max_classify_images = min(config.get("max_classify_images", 100), image_count)
    max_preview_pages = min(config.get("max_preview_pages", 5), page_count)

    # ----- Step: Core accessibility checks -----
    core_consts = TIMING_CONSTANTS["core"]
    core_time = (
        core_consts["base"]
        + core_consts["per_page"] * page_count
        + core_consts["per_image"] * image_count
    )
    core_substeps = [
        SubstepTiming("tagged", "Check tagged PDF", 50),
        SubstepTiming("title", "Check document title", 30),
        SubstepTiming("language", "Check document language", 30),
        SubstepTiming("protected", "Check protection settings", 30),
        SubstepTiming("bookmarks", "Check bookmarks/outlines", 50),
        SubstepTiming("scanned", "Detect scanned document", 100),
        SubstepTiming("alt_text", "Check figure alt text", core_consts["per_image"] * image_count),
    ]
    steps.append(
        StepTiming(
            step_id="core",
            label="Run core accessibility checks",
            estimated_ms=core_time,
            will_run=True,
            substeps=core_substeps,
        )
    )

    # ----- Step: Analyze document (OCR + Contrast) -----
    analyze_time = 0
    analyze_substeps: list[SubstepTiming] = []

    if do_ocr:
        ocr_consts = TIMING_CONSTANTS["ocr"]
        ocr_time = (
            ocr_consts["base"]
            + ocr_consts["first_page_extra"]
            + ocr_consts["per_page"] * max_ocr_pages
        )
        analyze_time += ocr_time
        analyze_substeps.append(
            SubstepTiming(
                "ocr",
                f"Analyze text layer ({max_ocr_pages} pages)",
                ocr_time,
            )
        )

    if do_contrast:
        contrast_consts = TIMING_CONSTANTS["contrast"]
        contrast_time = contrast_consts["base"] + contrast_consts["per_page"] * max_contrast_pages
        analyze_time += contrast_time
        analyze_substeps.append(
            SubstepTiming(
                "contrast",
                f"Check color contrast ({max_contrast_pages} pages)",
                contrast_time,
            )
        )

    # Only add analyze step if it has work to do
    if analyze_substeps:
        steps.append(
            StepTiming(
                step_id="analyze",
                label="Analyze document",
                estimated_ms=analyze_time,
                will_run=True,
                substeps=analyze_substeps,
            )
        )

    # ----- Step: Extract structure & content -----
    structure_consts = TIMING_CONSTANTS["structure"]
    content_consts = TIMING_CONSTANTS["content"]
    structure_time = (
        structure_consts["base"]
        + structure_consts["per_page"] * page_count
        + content_consts["base"]
        + content_consts["per_page"] * page_count
        + content_consts["per_image"] * image_count
    )
    structure_substeps = [
        SubstepTiming(
            "tree",
            "Extract structure tree",
            structure_consts["base"] + structure_consts["per_page"] * page_count,
        ),
        SubstepTiming("headings", "Extract heading outline", 200),
        SubstepTiming("tables", "Audit tables", 300),
        SubstepTiming("forms", "Audit forms", 200 if prescan.has_forms else 50),
        SubstepTiming("links", "Extract links", 200),
        SubstepTiming("images", "Catalog images", content_consts["per_image"] * image_count),
    ]
    steps.append(
        StepTiming(
            step_id="structure",
            label="Extract structure & content",
            estimated_ms=structure_time,
            will_run=True,
            substeps=structure_substeps,
        )
    )

    # ----- Step: Classify images (optional) -----
    if do_classify and image_count > 0:
        classify_consts = TIMING_CONSTANTS["classify"]
        images_to_classify = min(max_classify_images, image_count)
        classify_time = classify_consts["base"] + classify_consts["per_image"] * images_to_classify
        steps.append(
            StepTiming(
                step_id="classify",
                label="Classify images",
                estimated_ms=classify_time,
                will_run=True,
                substeps=[
                    SubstepTiming(
                        "ml_classify",
                        f"Classify {images_to_classify} images (local ML)",
                        classify_time,
                    ),
                ],
            )
        )

    # ----- Step: Generate preview (optional) -----
    if do_preview:
        preview_consts = TIMING_CONSTANTS["preview"]
        preview_time = preview_consts["base"] + preview_consts["per_page"] * max_preview_pages
        steps.append(
            StepTiming(
                step_id="preview",
                label="Generate preview",
                estimated_ms=preview_time,
                will_run=True,
                substeps=[
                    SubstepTiming(
                        "render",
                        f"Render pages (1-{max_preview_pages})",
                        preview_consts["per_page"] * max_preview_pages,
                    ),
                    SubstepTiming("overlay", "Create tag overlays", 300),
                    SubstepTiming("thumbnails", "Generate thumbnails", 200),
                ],
            )
        )

    # ----- Step: Build report -----
    build_consts = TIMING_CONSTANTS["build"]
    build_time = build_consts["base"] + build_consts["per_page"] * page_count
    steps.append(
        StepTiming(
            step_id="build",
            label="Build report",
            estimated_ms=build_time,
            will_run=True,
            substeps=[
                SubstepTiming("compile", "Compile report data", build_time),
            ],
        )
    )

    # ----- Step: Save report -----
    save_consts = TIMING_CONSTANTS["save"]
    save_time = save_consts["base"] + save_consts["per_page"] * page_count
    steps.append(
        StepTiming(
            step_id="save",
            label="Save report",
            estimated_ms=save_time,
            will_run=True,
            substeps=[
                SubstepTiming("write", "Write report files", save_time),
            ],
        )
    )

    # Calculate total
    total_time = sum(s.estimated_ms for s in steps if s.will_run)

    # Apply complexity multiplier
    if prescan.file_complexity == "complex":
        total_time = int(total_time * 1.3)
        for step in steps:
            step.estimated_ms = int(step.estimated_ms * 1.3)
    elif prescan.file_complexity == "moderate":
        total_time = int(total_time * 1.1)
        for step in steps:
            step.estimated_ms = int(step.estimated_ms * 1.1)

    return TimingEstimate(
        total_estimated_ms=total_time,
        steps=steps,
    )


def format_duration(ms: int) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"
    elif ms < 60000:
        seconds = ms / 1000
        return f"{seconds:.1f}s"
    else:
        minutes = ms // 60000
        seconds = (ms % 60000) / 1000
        if seconds > 0:
            return f"{minutes}m {seconds:.0f}s"
        return f"{minutes}m"
