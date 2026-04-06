"""
Unified progress step definitions for PDF accessibility checking.

This module defines the canonical list of progress steps used by both
the CLI and GUI interfaces. It serves as the single source of truth
for step IDs, labels, and ordering.

Usage:
    from inspekt.services.progress_steps import PROGRESS_STEPS, get_step_label, emit_step

    # In CLI:
    with emit_step("core"):
        run_core_checks()

    # Get step info:
    label = get_step_label("ocr")  # "Analyze text layer (local OCR)"
"""

from dataclasses import dataclass
from typing import Optional
import json


@dataclass
class ProgressStep:
    """A single progress step definition."""

    id: str
    label: str
    description: str
    optional: bool = False  # If True, step may be skipped based on config


# Canonical list of progress steps in order
PROGRESS_STEPS: list[ProgressStep] = [
    ProgressStep(
        id="core",
        label="Run core accessibility checks",
        description="Basic PDF/UA compliance checks including tagging, title, language",
    ),
    ProgressStep(
        id="cover",
        label="Create cover preview",
        description="Generate cover page thumbnail for the report",
        optional=True,
    ),
    ProgressStep(
        id="ocr",
        label="Analyze text layer (local OCR)",
        description="Compare PDF text layer against OCR to detect missing text",
        optional=True,
    ),
    ProgressStep(
        id="contrast",
        label="Analyze color contrast",
        description="Check text/background color contrast ratios against WCAG",
        optional=True,
    ),
    ProgressStep(
        id="structure",
        label="Extract structure tree",
        description="Parse and validate the PDF's logical structure tree",
    ),
    ProgressStep(
        id="content",
        label="Extract images & tables",
        description="Audit images for alt text and tables for proper headers",
        optional=True,
    ),
    ProgressStep(
        id="thumbnails",
        label="Generate thumbnails",
        description="Create thumbnail previews for images in the report",
        optional=True,
    ),
    ProgressStep(
        id="classify",
        label="Classify images (local ML)",
        description="Use local ML to categorize images (photo, chart, etc.)",
        optional=True,
    ),
    ProgressStep(
        id="build",
        label="Build report",
        description="Compile all check results into the final report structure",
    ),
    ProgressStep(
        id="save",
        label="Save report",
        description="Write the report to the output file",
    ),
]

# Create lookup dictionaries
_STEPS_BY_ID = {step.id: step for step in PROGRESS_STEPS}
_STEP_ORDER = {step.id: i for i, step in enumerate(PROGRESS_STEPS)}


def get_step_label(step_id: str) -> str:
    """Get the display label for a step ID."""
    step = _STEPS_BY_ID.get(step_id)
    return step.label if step else step_id


def get_step_description(step_id: str) -> str:
    """Get the description for a step ID."""
    step = _STEPS_BY_ID.get(step_id)
    return step.description if step else ""


def get_step_order(step_id: str) -> int:
    """Get the order index for a step ID (-1 if not found)."""
    return _STEP_ORDER.get(step_id, -1)


def get_all_step_ids() -> list[str]:
    """Get all step IDs in order."""
    return [step.id for step in PROGRESS_STEPS]


def export_steps_json() -> str:
    """Export steps as JSON for use by external tools (GUI, etc.)."""
    return json.dumps(
        [
            {
                "id": step.id,
                "label": step.label,
                "description": step.description,
                "optional": step.optional,
            }
            for step in PROGRESS_STEPS
        ],
        indent=2,
    )


def match_step_from_message(message: str) -> Optional[str]:
    """
    Try to match a CLI output message to a step ID.

    This enables the GUI to track progress by parsing stderr output.

    Args:
        message: A line of CLI output

    Returns:
        The matching step ID, or None if no match
    """
    msg = message.lower()

    # Match patterns to step IDs
    patterns = {
        "core": ["core accessibility", "essential checks", "basic checks"],
        "cover": ["cover preview", "cover page"],
        "ocr": ["text layer", "ocr", "text discrepancy"],
        "contrast": ["color contrast", "contrast analysis"],
        "structure": ["structure tree", "extract structure"],
        "content": ["images & tables", "extract images", "content audit"],
        "thumbnails": ["thumbnail", "generate thumb"],
        "classify": ["classify", "classification", "local ml"],
        "build": ["build report", "generate report", "report data"],
        "save": ["save report", "export", "json report", "complete"],
    }

    for step_id, keywords in patterns.items():
        if any(kw in msg for kw in keywords):
            return step_id

    return None


# For CLI: context manager that emits step progress
class StepEmitter:
    """
    Context manager for emitting step progress in CLI.

    Usage:
        emitter = StepEmitter(quiet=False)
        with emitter.step("core"):
            run_core_checks()
    """

    def __init__(self, quiet: bool = False, json_mode: bool = False):
        self.quiet = quiet
        self.json_mode = json_mode
        self._current_step: Optional[str] = None

    def step(self, step_id: str):
        """Return a context manager for a step."""
        return _StepContext(self, step_id)

    def emit_start(self, step_id: str):
        """Emit step start (called by context manager)."""
        self._current_step = step_id
        if not self.quiet:
            label = get_step_label(step_id)
            if self.json_mode:
                print(json.dumps({"event": "step_start", "step_id": step_id, "label": label}))
            # For CLI, the actual output is handled by print_checkbox_step

    def emit_end(self, step_id: str, note: Optional[str] = None):
        """Emit step end (called by context manager)."""
        self._current_step = None
        if not self.quiet and self.json_mode:
            print(json.dumps({"event": "step_end", "step_id": step_id, "note": note}))


class _StepContext:
    """Context manager for a single step."""

    def __init__(self, emitter: StepEmitter, step_id: str):
        self.emitter = emitter
        self.step_id = step_id
        self.note: Optional[str] = None

    def __enter__(self):
        self.emitter.emit_start(self.step_id)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.emitter.emit_end(self.step_id, self.note)
        return False

    def skip(self, reason: str):
        """Mark this step as skipped with a reason."""
        self.note = reason
