"""Data models for browser interaction recordings."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _to_int(v: int | float) -> int:
    """Convert float to int for scroll values."""
    if isinstance(v, float):
        return int(v)
    return v


IntFromFloat = Annotated[int, BeforeValidator(_to_int)]


class ViewportInfo(BaseModel):
    """Browser viewport dimensions."""

    width: int
    height: int


class RecordedOn(BaseModel):
    """Recording context information."""

    platform: str | None = None  # e.g., "darwin", "win32", "linux"
    browser: str | None = None  # e.g., "Chrome", "Firefox"
    browser_version: str | None = None  # e.g., "131.0"


class ScrollPosition(BaseModel):
    """Scroll position coordinates."""

    x: IntFromFloat = 0
    y: IntFromFloat = 0


class Precondition(BaseModel):
    """A required element for replay to proceed."""

    selector: str
    description: str | None = None


class PreconditionsInfo(BaseModel):
    """Preconditions that must be met before replay starts."""

    required: list[Precondition] = Field(default_factory=list)
    url_pattern: str | None = None  # URL glob pattern
    title_contains: str | None = None


class ReplaySettings(BaseModel):
    """Settings that control replay behavior."""

    # Restoration settings (mostly OFF by default)
    restore_viewport: bool = True
    restore_scroll: bool = False
    restore_cookies: bool = False
    restore_local_storage: bool = False
    restore_session_storage: bool = False

    # Validation settings
    verify_preconditions: bool = True
    verify_checksum: bool = False
    halt_on_precondition_fail: bool = False
    halt_on_checksum_mismatch: bool = False


class StateInfo(BaseModel):
    """Page state captured at recording time."""

    viewport: ViewportInfo
    zoom: float = 1.0  # devicePixelRatio (layout zoom)
    browser_zoom_level: float = 1.0  # Actual Chrome zoom level (1.0 = 100%)
    scroll: ScrollPosition = Field(default_factory=ScrollPosition)

    # Matching requirements (from --match-viewport, --match-zoom-level flags)
    require_viewport_match: bool = False
    require_zoom_match: bool = False

    # Window mode at recording time (fullscreen/kiosk cannot be resized)
    window_mode: Literal["normal", "fullscreen", "kiosk"] | None = None

    # Optional state capture (only if --capture-state used)
    cookies: str | None = None  # Base64-encoded JSON
    local_storage: str | None = None  # Base64-encoded JSON
    session_storage: str | None = None  # Base64-encoded JSON
    checksum: str | None = None  # DOM structure hash


class RecordingMetadata(BaseModel):
    """Metadata for a recording session."""

    version: str = "1.1"
    created_at: datetime
    duration_ms: int
    starting_url: str
    created_by: str | None = None
    user_agent: str | None = None
    recorded_on: RecordedOn | None = None
    faithful: bool = False  # True if focus_styles were captured (experimental)


class TargetInfo(BaseModel):
    """Information about a target DOM element."""

    selector: str
    fallback_selectors: list[str] = Field(default_factory=list)
    text: str | None = None
    accessible_name: str | None = None
    tag: str | None = None
    role: str | None = None
    attributes: dict[str, str] = Field(default_factory=dict)
    # Shadow DOM support
    shadow_host: str | None = None  # Selector for the shadow host element
    piercing_selector: str | None = None  # Full selector: "host >>> inner"
    # Native control input type (for set action)
    input_type: str | None = None  # e.g., "range", "date", "time", "color"
    # Focus styles captured during recording (for sr-only elements)
    # These styles make hidden elements visible when focused
    focus_styles: dict[str, str] | None = None


class ScrollInfo(BaseModel):
    """Scroll position and delta information."""

    x: IntFromFloat  # Absolute scroll position X
    y: IntFromFloat  # Absolute scroll position Y
    deltaX: IntFromFloat = 0  # Scroll amount X
    deltaY: IntFromFloat = 0  # Scroll amount Y


class FileInfo(BaseModel):
    """Information about an uploaded file."""

    name: str  # Original filename
    type: str  # MIME type (e.g., "image/jpeg")
    size: int  # File size in bytes
    lastModified: int | None = None  # Unix timestamp in milliseconds

    # Content storage (mutually exclusive)
    content: str | None = None  # Temporary base64 during transfer (removed before YAML save)
    external_path: str | None = None  # Relative path to saved file


class DownloadInfo(BaseModel):
    """Information about a downloaded file."""

    filename: str  # Saved filename
    url: str  # Download URL
    mime_type: str  # MIME type (e.g., "application/pdf")
    size: int  # File size in bytes
    download_start: int  # Unix timestamp ms when download started
    download_end: int  # Unix timestamp ms when download completed

    # Storage
    external_path: str | None = None  # Relative path to saved file

    # Source path (temporary - used during recording to copy file, removed before YAML save)
    full_path: str | None = None  # Full filesystem path from Chrome's download location

    # Content (fallback - only used if full_path copy fails)
    content: str | None = None  # base64 content during transfer

    # Optional metadata
    content_disposition: str | None = None  # Original Content-Disposition header
    referrer: str | None = None  # Page that triggered download
    download_id: int | None = None  # Browser download ID (for retrieval)


class ExpectInfo(BaseModel):
    """Optional assertions/expectations for a step."""

    # Element visibility assertions
    visible: str | None = None  # Selector to check visibility
    hidden: str | None = None  # Selector to check hidden

    # Text/URL assertions
    text_contains: str | None = None
    url_contains: str | None = None
    ignore_case: bool | None = None  # Case-insensitive matching for text_contains

    # Focus assertion
    focused: bool | None = None  # Check if target element has focus

    # Element state assertions (new)
    value: str | None = None  # Selector for input value check
    value_equals: str | None = None  # Expected value for input
    checked: str | None = None  # Selector for checkbox/radio that should be checked
    unchecked: str | None = None  # Selector for checkbox/radio that should be unchecked
    disabled: str | None = None  # Selector for element that should be disabled
    enabled: str | None = None  # Selector for element that should be enabled
    count: str | None = None  # Selector to count elements
    count_equals: int | None = None  # Expected count
    count_min: int | None = None  # Minimum count
    count_max: int | None = None  # Maximum count

    # Timing options (new)
    wait: int | None = None  # Max time to wait for assertion (ms)
    retry: int | None = None  # Retry interval (ms), default 100

    # Inspekt command assertions
    empty: bool | None = None  # For console checks (no messages)
    allowed_violations: int | None = Field(default=None, alias="allowed-violations")  # For axe checks (max violations allowed, default 0 if checking axe)

    # Generic output assertions (work with any inspekt command)
    output_contains: str | None = Field(default=None, alias="output-contains")  # Check stdout contains text
    output_not_contains: str | None = Field(default=None, alias="output-not-contains")  # Check stdout doesn't contain text
    output_matches: str | None = Field(default=None, alias="output-matches")  # Check stdout matches regex

    # Download assertions
    download_exists: bool | None = None  # File was successfully downloaded
    download_mime_type: str | None = None  # Exact MIME type match
    download_mime_type_contains: str | None = None  # Partial MIME match (e.g., "image/")
    download_size: int | None = None  # Exact file size in bytes
    download_size_min: int | None = None  # Minimum file size
    download_size_max: int | None = None  # Maximum file size
    download_filename: str | None = None  # Expected filename
    download_filename_contains: str | None = None  # Partial filename match
    download_content_contains: str | None = None  # Text content check (text files only)
    download_checksum: str | None = None  # MD5/SHA256 hash (format: "sha256:abc123")
    download_shell: str | None = None  # Shell command from allowlist
    download_timeout: int | None = Field(default=None)  # Download timeout in ms (default 30000)

    # Metadata
    message: str | None = None  # Description of expectation


ActionType = Literal["navigate", "click", "rightclick", "activate", "type", "set", "keypress", "hover", "check", "uncheck", "radio", "select", "scroll", "toggle", "dialog", "jsdialog", "upload", "download", "plugin", "inspekt"]

# Step execution modes for replay
StepMode = Literal["continue", "skip", "pause"]


class ConditionInfo(BaseModel):
    """Condition for skip_if and wait_for."""

    # Element visibility conditions
    visible: str | None = None  # Selector to check visibility
    hidden: str | None = None  # Selector to check hidden

    # Text/URL conditions
    text_contains: str | None = None
    url_contains: str | None = None
    ignore_case: bool | None = None  # Case-insensitive matching for text_contains

    # Element state conditions
    checked: str | None = None  # Selector for checked checkbox/radio
    unchecked: str | None = None  # Selector for unchecked checkbox/radio
    value: str | None = None  # Selector to check value
    value_equals: str | None = None  # Expected value

    # Timeout for wait_for (ms)
    timeout: int | None = None


class RecordingStep(BaseModel):
    """A single recorded interaction step."""

    timestamp: int  # Milliseconds from recording start
    action: ActionType

    # Action-specific fields
    url: str | None = None  # For navigate action
    target: TargetInfo | None = None  # For click, type, hover, check, uncheck, select
    value: str | None = None  # For type, check, select actions
    option_text: str | None = None  # For select action (display text of selected option)
    sensitive: bool = False  # For type (passwords)
    key: str | None = None  # For keypress action
    modifiers: list[str] = Field(default_factory=list)  # For keypress (ctrl, shift, alt, meta)
    scroll: ScrollInfo | None = None  # For scroll action
    command: str | None = None  # For inspekt action
    files: list[FileInfo] | None = None  # For upload action
    download: DownloadInfo | None = None  # For download action

    # For jsdialog action (alert, confirm, prompt)
    dialog_type: str | None = None  # 'alert', 'confirm', or 'prompt'
    message: str | None = None  # Dialog message
    default_value: str | None = None  # Default value for prompt
    result: bool | str | None = None  # User's response (bool for confirm, str for prompt)
    duration: int | None = None  # How long dialog was shown (ms) - for replay timing

    # Click position as [x%, y%] within element (more robust than absolute coordinates)
    click_at: list[int] | None = None

    # Conditional execution
    skip_if: ConditionInfo | None = None  # Skip step if condition is true
    wait_for: ConditionInfo | None = None  # Wait for condition before executing

    # Optional assertions
    expect: ExpectInfo | None = None

    # Step execution mode (continue=default, skip, pause)
    mode: StepMode | None = None

    # Native keyboard mode override (per-step)
    # True = force native (AppleScript), False = force CDP, None = use global --native flag
    native: bool | None = None


class Recording(BaseModel):
    """Complete recording of a browser interaction session."""

    metadata: RecordingMetadata
    state: StateInfo | None = None
    preconditions: PreconditionsInfo | None = None
    replay: ReplaySettings | None = None
    steps: list[RecordingStep] = Field(default_factory=list)

    def to_yaml_dict(self) -> dict:
        """Convert to a dictionary suitable for YAML output.

        Excludes None values and empty lists for cleaner output.
        """
        return self.model_dump(exclude_none=True, exclude_defaults=True)
