"""
Structured Progress Emitter for Desktop App Integration.

This module emits JSON progress events to stderr that can be parsed by the
Tauri desktop application for accurate, detailed progress visualization.

The emitter produces single-line JSON objects for each progress event, enabling
real-time parsing and UI updates with:
- Pre-scan document information
- Timing estimates for each step
- Step start/end events
- Substep progress (e.g., "Page 3 of 50")
- Overall progress percentage

Usage:
    from inspekt.services.structured_progress import StructuredProgressEmitter
    from inspekt.services.pdf_prescan import prescan_pdf
    from inspekt.services.progress_timing import estimate_timing

    emitter = StructuredProgressEmitter()

    # Emit pre-scan information
    prescan = prescan_pdf(pdf_path)
    timing = estimate_timing(prescan, config)
    emitter.emit_prescan(prescan, timing)

    # Emit step progress
    with emitter.step("core", "Run core accessibility checks"):
        emitter.substep("core", "tagged", "Check tagged PDF")
        # ... do work ...
        emitter.progress("core", 50)  # 50% complete

    # Emit completion
    emitter.emit_complete()
"""

from __future__ import annotations

import json
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Generator

    from inspekt.services.pdf_prescan import PDFPrescanResult
    from inspekt.services.progress_timing import TimingEstimate


# Event types for progress tracking
EventType = Literal[
    "prescan",      # Document pre-scan completed, timing estimates available
    "step_start",   # Main step started
    "step_progress",  # Progress within a step (percentage)
    "substep",      # Substep started within a main step
    "step_end",     # Main step completed
    "complete",     # All processing complete
    "error",        # Error occurred
]


@dataclass
class ProgressEvent:
    """
    A single progress event to be emitted as JSON.

    All fields are optional except event_type and timestamp_ms (auto-generated).
    The event structure is designed to be easily parsed by the Tauri backend.
    """

    event_type: EventType
    timestamp_ms: int = 0  # Will be set by emitter

    # Step identification
    step_id: str | None = None
    substep_id: str | None = None

    # Display information
    label: str | None = None
    note: str | None = None

    # Progress tracking
    progress_percent: int | None = None  # 0-100 for step progress
    current: int | None = None           # Current item (e.g., page 3)
    total: int | None = None             # Total items (e.g., of 50 pages)

    # Pre-scan data (only for prescan event)
    prescan_result: dict | None = None
    timing_estimate: dict | None = None

    # Completion data (only for complete event)
    total_time_ms: int | None = None

    # Error data (only for error event)
    error_message: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding None values for compact JSON."""
        result = {"event_type": self.event_type, "timestamp_ms": self.timestamp_ms}
        for key, value in asdict(self).items():
            if value is not None and key not in ("event_type", "timestamp_ms"):
                result[key] = value
        return result


class StructuredProgressEmitter:
    """
    Emits JSON progress events to stderr for the desktop app.

    The emitter tracks timing from initialization and includes timestamps
    on all events for accurate duration tracking.

    Thread Safety:
        This class is designed for single-threaded use. For multi-threaded
        scenarios, external synchronization should be used.
    """

    def __init__(self, output_stream=None):
        """
        Initialize the emitter.

        Args:
            output_stream: Stream to write events to (default: sys.stderr)
        """
        self.start_time = time.time()
        self.output_stream = output_stream or sys.stderr
        self._current_step: str | None = None
        self._step_start_times: dict[str, float] = {}

    def _get_timestamp_ms(self) -> int:
        """Get milliseconds elapsed since emitter creation."""
        return int((time.time() - self.start_time) * 1000)

    def _emit(self, event: ProgressEvent) -> None:
        """Emit a progress event as single-line JSON to stderr."""
        event.timestamp_ms = self._get_timestamp_ms()
        json_str = json.dumps(event.to_dict(), separators=(",", ":"))
        print(json_str, file=self.output_stream, flush=True)

    def emit_prescan(
        self,
        prescan: PDFPrescanResult,
        timing: TimingEstimate,
    ) -> None:
        """
        Emit pre-scan results and timing estimates.

        This should be called immediately after pre-scanning the PDF,
        before any processing begins. The frontend uses this to:
        - Display document information (pages, images)
        - Initialize progress bar with estimated total time
        - Prepare step list with individual estimates

        Args:
            prescan: Result from prescan_pdf()
            timing: Result from estimate_timing()
        """
        self._emit(ProgressEvent(
            event_type="prescan",
            prescan_result=prescan.to_dict(),
            timing_estimate=timing.to_dict(),
        ))

    @contextmanager
    def step(
        self,
        step_id: str,
        label: str,
        note: str | None = None,
    ) -> Generator[None, None, None]:
        """
        Context manager for a main step.

        Usage:
            with emitter.step("core", "Run core accessibility checks"):
                # ... do work ...

        The step_start event is emitted on entry, and step_end on exit.
        If an exception occurs, an error event is emitted.

        Args:
            step_id: Unique identifier for the step (matches timing step_id)
            label: Human-readable label for display
            note: Optional note to display with the step
        """
        self._current_step = step_id
        self._step_start_times[step_id] = time.time()

        self._emit(ProgressEvent(
            event_type="step_start",
            step_id=step_id,
            label=label,
            note=note,
        ))

        try:
            yield
            # Emit step end
            step_duration_ms = int((time.time() - self._step_start_times[step_id]) * 1000)
            self._emit(ProgressEvent(
                event_type="step_end",
                step_id=step_id,
                note=f"Completed in {step_duration_ms}ms" if step_duration_ms > 100 else None,
            ))
        except Exception as e:
            self._emit(ProgressEvent(
                event_type="error",
                step_id=step_id,
                error_message=str(e),
            ))
            raise
        finally:
            self._current_step = None

    def step_start(self, step_id: str, label: str, note: str | None = None) -> None:
        """
        Manually emit a step start event (non-context-manager version).

        Use this when you can't use the context manager, but prefer the
        context manager when possible for automatic step_end handling.
        """
        self._current_step = step_id
        self._step_start_times[step_id] = time.time()
        self._emit(ProgressEvent(
            event_type="step_start",
            step_id=step_id,
            label=label,
            note=note,
        ))

    def step_end(self, step_id: str, note: str | None = None) -> None:
        """Manually emit a step end event."""
        start_time = self._step_start_times.get(step_id)
        if start_time:
            step_duration_ms = int((time.time() - start_time) * 1000)
            if note is None and step_duration_ms > 100:
                note = f"Completed in {step_duration_ms}ms"
        self._emit(ProgressEvent(
            event_type="step_end",
            step_id=step_id,
            note=note,
        ))
        if self._current_step == step_id:
            self._current_step = None

    def substep(
        self,
        step_id: str,
        substep_id: str,
        label: str,
        current: int | None = None,
        total: int | None = None,
    ) -> None:
        """
        Emit a substep event within a main step.

        This provides granular progress like "Page 3 of 50" within
        a step like "Analyze text layer (OCR)".

        Args:
            step_id: Parent step identifier
            substep_id: Unique identifier for this substep
            label: Human-readable label (e.g., "Processing page 3")
            current: Current item number (e.g., 3)
            total: Total items (e.g., 50)
        """
        self._emit(ProgressEvent(
            event_type="substep",
            step_id=step_id,
            substep_id=substep_id,
            label=label,
            current=current,
            total=total,
        ))

    def progress(
        self,
        step_id: str,
        percent: int,
        label: str | None = None,
    ) -> None:
        """
        Emit step progress as a percentage.

        Args:
            step_id: Step identifier
            percent: Progress percentage (0-100)
            label: Optional label update
        """
        self._emit(ProgressEvent(
            event_type="step_progress",
            step_id=step_id,
            progress_percent=min(100, max(0, percent)),
            label=label,
        ))

    def emit_complete(self, note: str | None = None) -> None:
        """
        Emit the completion event.

        This should be called when all processing is finished.
        The total_time_ms field allows the frontend to display
        actual vs estimated time.
        """
        total_time = self._get_timestamp_ms()
        self._emit(ProgressEvent(
            event_type="complete",
            total_time_ms=total_time,
            note=note,
        ))

    def emit_error(
        self,
        message: str,
        step_id: str | None = None,
    ) -> None:
        """
        Emit an error event.

        Args:
            message: Error description
            step_id: Associated step (if any)
        """
        self._emit(ProgressEvent(
            event_type="error",
            step_id=step_id or self._current_step,
            error_message=message,
        ))


# Global emitter instance for convenience
_global_emitter: StructuredProgressEmitter | None = None


def get_emitter() -> StructuredProgressEmitter:
    """Get or create the global emitter instance."""
    global _global_emitter
    if _global_emitter is None:
        _global_emitter = StructuredProgressEmitter()
    return _global_emitter


def reset_emitter() -> None:
    """Reset the global emitter (mainly for testing)."""
    global _global_emitter
    _global_emitter = None
