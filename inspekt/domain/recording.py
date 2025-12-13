"""Data models for browser interaction recordings."""

from datetime import datetime
from typing import Annotated, Literal, Optional

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

    platform: Optional[str] = None  # e.g., "darwin", "win32", "linux"
    browser: Optional[str] = None  # e.g., "Chrome", "Firefox"
    browser_version: Optional[str] = None  # e.g., "131.0"


class ScrollPosition(BaseModel):
    """Scroll position coordinates."""

    x: IntFromFloat = 0
    y: IntFromFloat = 0


class Precondition(BaseModel):
    """A required element for replay to proceed."""

    selector: str
    description: Optional[str] = None


class PreconditionsInfo(BaseModel):
    """Preconditions that must be met before replay starts."""

    required: list[Precondition] = Field(default_factory=list)
    url_pattern: Optional[str] = None  # URL glob pattern
    title_contains: Optional[str] = None


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
    zoom: float = 1.0
    scroll: ScrollPosition = Field(default_factory=ScrollPosition)

    # Optional state capture (only if --capture-state used)
    cookies: Optional[str] = None  # Base64-encoded JSON
    local_storage: Optional[str] = None  # Base64-encoded JSON
    session_storage: Optional[str] = None  # Base64-encoded JSON
    checksum: Optional[str] = None  # DOM structure hash


class RecordingMetadata(BaseModel):
    """Metadata for a recording session."""

    version: str = "1.1"
    created_at: datetime
    duration_ms: int
    starting_url: str
    user_agent: Optional[str] = None
    recorded_on: Optional[RecordedOn] = None


class TargetInfo(BaseModel):
    """Information about a target DOM element."""

    selector: str
    fallback_selectors: list[str] = Field(default_factory=list)
    text: Optional[str] = None
    accessible_name: Optional[str] = None
    tag: Optional[str] = None
    role: Optional[str] = None
    attributes: dict[str, str] = Field(default_factory=dict)
    # Shadow DOM support
    shadow_host: Optional[str] = None  # Selector for the shadow host element
    piercing_selector: Optional[str] = None  # Full selector: "host >>> inner"


class ScrollInfo(BaseModel):
    """Scroll position and delta information."""

    x: IntFromFloat  # Absolute scroll position X
    y: IntFromFloat  # Absolute scroll position Y
    deltaX: IntFromFloat = 0  # Scroll amount X
    deltaY: IntFromFloat = 0  # Scroll amount Y


class ExpectInfo(BaseModel):
    """Optional assertions/expectations for a step."""

    # Element visibility assertions
    visible: Optional[str] = None  # Selector to check visibility
    hidden: Optional[str] = None  # Selector to check hidden

    # Text/URL assertions
    text_contains: Optional[str] = None
    url_contains: Optional[str] = None
    ignore_case: Optional[bool] = None  # Case-insensitive matching for text_contains

    # Focus assertion
    focused: Optional[bool] = None  # Check if target element has focus

    # Element state assertions (new)
    value: Optional[str] = None  # Selector for input value check
    value_equals: Optional[str] = None  # Expected value for input
    checked: Optional[str] = None  # Selector for checkbox/radio that should be checked
    unchecked: Optional[str] = None  # Selector for checkbox/radio that should be unchecked
    disabled: Optional[str] = None  # Selector for element that should be disabled
    enabled: Optional[str] = None  # Selector for element that should be enabled
    count: Optional[str] = None  # Selector to count elements
    count_equals: Optional[int] = None  # Expected count
    count_min: Optional[int] = None  # Minimum count
    count_max: Optional[int] = None  # Maximum count

    # Timing options (new)
    wait: Optional[int] = None  # Max time to wait for assertion (ms)
    retry: Optional[int] = None  # Retry interval (ms), default 100

    # Inspekt command assertions
    empty: Optional[bool] = None  # For console checks (no messages)
    allowed_violations: Optional[int] = Field(default=None, alias="allowed-violations")  # For axe checks (max violations allowed, default 0 if checking axe)

    # Generic output assertions (work with any inspekt command)
    output_contains: Optional[str] = Field(default=None, alias="output-contains")  # Check stdout contains text
    output_not_contains: Optional[str] = Field(default=None, alias="output-not-contains")  # Check stdout doesn't contain text
    output_matches: Optional[str] = Field(default=None, alias="output-matches")  # Check stdout matches regex

    # Metadata
    message: Optional[str] = None  # Description of expectation


ActionType = Literal["navigate", "click", "rightclick", "activate", "type", "keypress", "hover", "check", "uncheck", "radio", "select", "scroll", "plugin", "inspekt"]

# Step execution modes for replay
StepMode = Literal["continue", "skip", "pause"]


class ConditionInfo(BaseModel):
    """Condition for skip_if and wait_for."""

    # Element visibility conditions
    visible: Optional[str] = None  # Selector to check visibility
    hidden: Optional[str] = None  # Selector to check hidden

    # Text/URL conditions
    text_contains: Optional[str] = None
    url_contains: Optional[str] = None
    ignore_case: Optional[bool] = None  # Case-insensitive matching for text_contains

    # Element state conditions
    checked: Optional[str] = None  # Selector for checked checkbox/radio
    unchecked: Optional[str] = None  # Selector for unchecked checkbox/radio
    value: Optional[str] = None  # Selector to check value
    value_equals: Optional[str] = None  # Expected value

    # Timeout for wait_for (ms)
    timeout: Optional[int] = None


class RecordingStep(BaseModel):
    """A single recorded interaction step."""

    timestamp: int  # Milliseconds from recording start
    action: ActionType

    # Action-specific fields
    url: Optional[str] = None  # For navigate action
    target: Optional[TargetInfo] = None  # For click, type, hover, check, uncheck, select
    value: Optional[str] = None  # For type, check, select actions
    option_text: Optional[str] = None  # For select action (display text of selected option)
    sensitive: bool = False  # For type (passwords)
    key: Optional[str] = None  # For keypress action
    modifiers: list[str] = Field(default_factory=list)  # For keypress (ctrl, shift, alt, meta)
    scroll: Optional[ScrollInfo] = None  # For scroll action
    command: Optional[str] = None  # For inspekt action

    # Click position as [x%, y%] within element (more robust than absolute coordinates)
    click_at: Optional[list[int]] = None

    # Conditional execution
    skip_if: Optional[ConditionInfo] = None  # Skip step if condition is true
    wait_for: Optional[ConditionInfo] = None  # Wait for condition before executing

    # Optional assertions
    expect: Optional[ExpectInfo] = None

    # Step execution mode (continue=default, skip, pause)
    mode: Optional[StepMode] = None


class Recording(BaseModel):
    """Complete recording of a browser interaction session."""

    metadata: RecordingMetadata
    state: Optional[StateInfo] = None
    preconditions: Optional[PreconditionsInfo] = None
    replay: Optional[ReplaySettings] = None
    steps: list[RecordingStep] = Field(default_factory=list)

    def to_yaml_dict(self) -> dict:
        """Convert to a dictionary suitable for YAML output.

        Excludes None values and empty lists for cleaner output.
        """
        return self.model_dump(exclude_none=True, exclude_defaults=True)
