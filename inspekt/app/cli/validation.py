"""Recording file validation for preflight checks.

This module provides a 4-level validation pipeline for recording files:
- Level 1: Syntax (YAML parsing, encoding, tabs)
- Level 2: Structure (required fields, action types)
- Level 3: Logic (timestamps, file references, selectors)
- Level 4: Warnings (time gaps, long recordings, missing a11y info)
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import click
import yaml


class Severity(Enum):
    """Severity level for validation issues."""

    ERROR = "error"  # Blocks replay
    WARNING = "warning"  # Allows replay with caution


@dataclass
class ValidationIssue:
    """A single validation issue found in a recording file."""

    severity: Severity
    message: str
    tip: str | None = None
    step_num: int | None = None
    line_num: int | None = None
    context: str | None = None  # Show problematic YAML snippet


@dataclass
class ValidationResult:
    """Result of validating a recording file."""

    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidationIssue]:
        """Get all blocking errors."""
        return [i for i in self.issues if i.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[ValidationIssue]:
        """Get all non-blocking warnings."""
        return [i for i in self.issues if i.severity == Severity.WARNING]


# Valid action types from recording.py
VALID_ACTIONS = {
    "navigate",
    "click",
    "rightclick",
    "activate",
    "type",
    "set",
    "keypress",
    "hover",
    "check",
    "uncheck",
    "radio",
    "select",
    "scroll",
    "toggle",
    "dialog",
    "jsdialog",
    "upload",
    "download",
    "plugin",
    "inspekt",
}

# Actions that require a target
ACTIONS_REQUIRING_TARGET = {
    "click",
    "rightclick",
    "activate",
    "type",
    "set",
    "hover",
    "check",
    "uncheck",
    "radio",
    "select",
    "toggle",
    "upload",
}

# Thresholds for warnings
WARNING_TIME_GAP_SECONDS = 30  # Warn if gap between steps exceeds this
WARNING_STEP_COUNT = 100  # Warn if recording has more than this many steps


def get_yaml_context(content: str, line_num: int | None, context_lines: int = 2) -> str:
    """Extract YAML context around a specific line number.

    Args:
        content: Full file content
        line_num: 0-indexed line number (None returns empty)
        context_lines: Number of lines before/after to include

    Returns:
        Formatted context string with line numbers
    """
    if line_num is None:
        return ""

    lines = content.split("\n")
    start = max(0, line_num - context_lines)
    end = min(len(lines), line_num + context_lines + 1)

    result = []
    for i in range(start, end):
        line_indicator = ">" if i == line_num else " "
        result.append(f"  {line_indicator} {i + 1:4d} │ {lines[i]}")

    return "\n".join(result)


def get_yaml_error_tip(error: yaml.YAMLError) -> str:
    """Generate a helpful tip based on the YAML error type."""
    problem = getattr(error, "problem", "") or ""

    if "expected <block end>" in problem:
        return "This often happens when a comment contains newlines or special characters."
    if "found character" in problem and "that cannot start" in problem:
        return "Check for special characters or incorrect indentation."
    if "mapping values are not allowed" in problem:
        return "Check for missing quotes around values with colons."
    if "could not find expected" in problem:
        return "Check for mismatched quotes or brackets."

    return "Check the YAML syntax around this line."


# =============================================================================
# Level 1: Syntax Validation
# =============================================================================


def validate_yaml_syntax(filepath: Path) -> tuple[list[ValidationIssue], str | None]:
    """Check YAML syntax and provide helpful error context.

    Returns:
        Tuple of (issues list, file content if successfully read)
    """
    issues = []
    content = None

    # Check file exists
    if not filepath.exists():
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                message=f"Recording file not found: {filepath}",
                tip="Check the file path and try again.",
            )
        )
        return issues, None

    # Try to read file
    try:
        content = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                message="Invalid character encoding",
                tip="Ensure the file is saved as UTF-8.",
            )
        )
        return issues, None
    except Exception as e:
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                message=f"Cannot read file: {e}",
            )
        )
        return issues, None

    # Check for empty file
    if not content.strip():
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                message="Recording file is empty",
                tip="The file contains no data.",
            )
        )
        return issues, None

    # Check for tab characters
    for i, line in enumerate(content.split("\n"), 1):
        if "\t" in line:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Tab character found at line {i}",
                    tip="YAML requires spaces for indentation, not tabs.",
                    line_num=i,
                    context=line.replace("\t", "→"),
                )
            )

    # Try parsing YAML
    try:
        yaml.safe_load(content)
    except yaml.YAMLError as e:
        # Extract line info from YAML error
        mark = getattr(e, "problem_mark", None)
        line_num = mark.line if mark else None
        context = get_yaml_context(content, line_num) if line_num is not None else None

        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                message=f"YAML syntax error: {getattr(e, 'problem', str(e))}",
                tip=get_yaml_error_tip(e),
                line_num=line_num + 1 if line_num is not None else None,
                context=context,
            )
        )
        return issues, None

    return issues, content


# =============================================================================
# Level 2: Structure Validation
# =============================================================================


def validate_structure(data: dict) -> list[ValidationIssue]:
    """Check recording structure (required fields, valid action types)."""
    issues = []

    # Check for steps section
    if "steps" not in data:
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                message="Missing required 'steps' section",
                tip="Recording must have a 'steps' list.",
            )
        )
        return issues

    steps = data.get("steps", [])

    # Check for empty steps
    if not steps:
        issues.append(
            ValidationIssue(
                severity=Severity.ERROR,
                message="Recording contains no steps",
                tip="Add at least one step to the recording.",
            )
        )
        return issues

    # Validate each step
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: invalid format (expected dictionary)",
                    step_num=i,
                )
            )
            continue

        # Check action type
        action = step.get("action")
        if not action:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: missing 'action' field",
                    tip="Every step must have an action type.",
                    step_num=i,
                )
            )
        elif action not in VALID_ACTIONS:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: unknown action '{action}'",
                    tip=f"Valid actions: {', '.join(sorted(VALID_ACTIONS))}",
                    step_num=i,
                )
            )

        # Check for required target
        if action in ACTIONS_REQUIRING_TARGET:
            target = step.get("target")
            if not target:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        message=f"Step {i}: '{action}' action requires a target",
                        tip="Add a 'target' section with selector information.",
                        step_num=i,
                    )
                )

        # Check timestamp type
        timestamp = step.get("timestamp")
        if timestamp is not None and not isinstance(timestamp, (int, float)):
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: 'timestamp' should be a number, got {type(timestamp).__name__}",
                    step_num=i,
                )
            )

        # Action-specific checks
        if action == "navigate" and not step.get("url"):
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: 'navigate' action missing 'url'",
                    tip="Add 'url:' field to navigate step.",
                    step_num=i,
                )
            )

        if action == "upload" and not step.get("files"):
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: 'upload' action missing 'files' list",
                    tip="Add 'files:' array to upload step.",
                    step_num=i,
                )
            )

        if action == "download" and not step.get("download"):
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: 'download' action missing 'download' info",
                    tip="Add 'download:' field with filename, url, mime_type, size.",
                    step_num=i,
                )
            )

        # Validate download has required fields
        if action == "download" and step.get("download"):
            download = step.get("download", {})
            if not download.get("filename"):
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        message=f"Step {i}: download missing 'filename'",
                        tip="Add 'filename:' field to download.",
                        step_num=i,
                    )
                )

    return issues


# =============================================================================
# Level 3: Logic Validation
# =============================================================================


def validate_logic(data: dict, recording_dir: Path) -> list[ValidationIssue]:
    """Check logical consistency (timestamps, file references, selectors)."""
    issues = []
    steps = data.get("steps", [])

    # Validate timestamps
    issues.extend(validate_timestamps(steps))

    # Validate external file references
    issues.extend(validate_external_files(steps, recording_dir))

    # Validate selectors
    issues.extend(validate_selectors(steps))

    return issues


def validate_timestamps(steps: list) -> list[ValidationIssue]:
    """Check timestamp consistency across steps."""
    issues = []
    prev_timestamp = -1

    # Debounced actions (hover, scroll) use the START time, not when they're recorded.
    # This means they can appear "out of order" in the event queue but with earlier
    # timestamps - this is expected and not a problem.
    DEBOUNCED_ACTIONS = {"hover", "scroll"}

    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue

        timestamp = step.get("timestamp", 0)
        if not isinstance(timestamp, (int, float)):
            continue

        if timestamp < 0:
            issues.append(
                ValidationIssue(
                    severity=Severity.ERROR,
                    message=f"Step {i}: negative timestamp ({timestamp}ms)",
                    tip="Timestamps should be milliseconds from recording start (≥0).",
                    step_num=i,
                )
            )

        # Only update prev_timestamp for non-debounced actions
        # Debounced actions are expected to have earlier timestamps
        action = step.get("action", "")
        if action not in DEBOUNCED_ACTIONS:
            prev_timestamp = timestamp

    return issues


def validate_external_files(steps: list, recording_dir: Path) -> list[ValidationIssue]:
    """Check that all referenced external files exist."""
    issues = []

    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue

        action = step.get("action")

        # Check upload files
        if action == "upload":
            files = step.get("files", [])
            if not isinstance(files, list):
                continue

            for file_info in files:
                if not isinstance(file_info, dict):
                    continue

                external_path = file_info.get("external_path")
                if external_path:
                    full_path = recording_dir / external_path
                    if not full_path.exists():
                        issues.append(
                            ValidationIssue(
                                severity=Severity.ERROR,
                                message=f"Step {i}: external file not found: {external_path}",
                                tip=f"Expected: {full_path}\nRe-record the upload or restore the file.",
                                step_num=i,
                            )
                        )

        # Check download files
        if action == "download":
            download = step.get("download", {})
            if not isinstance(download, dict):
                continue

            external_path = download.get("external_path")
            if external_path:
                full_path = recording_dir / external_path
                if not full_path.exists():
                    # Check if there are assertions that need the original file
                    expect = step.get("expect", {})
                    needs_original = expect.get("download_checksum") is not None

                    if needs_original:
                        # Checksum comparison needs the original file
                        issues.append(
                            ValidationIssue(
                                severity=Severity.ERROR,
                                message=f"Step {i}: download file not found: {external_path}",
                                tip=f"Expected: {full_path}\n"
                                f"The download_checksum assertion requires the original file.\n"
                                f"Re-record the download or restore the file to the during-recording folder.",
                                step_num=i,
                            )
                        )
                    else:
                        # Just a warning - replay will create a new download
                        issues.append(
                            ValidationIssue(
                                severity=Severity.WARNING,
                                message=f"Step {i}: original download file not found: {external_path}",
                                tip="Replay will trigger a new download and save it to during-replay/. "
                                "The original file is only needed for checksum comparisons.",
                                step_num=i,
                            )
                        )

    return issues


def validate_selectors(steps: list) -> list[ValidationIssue]:
    """Check selector validity."""
    issues = []

    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue

        target = step.get("target")
        if not isinstance(target, dict):
            continue

        selector = target.get("selector", "")
        if isinstance(selector, str) and not selector.strip():
            action = step.get("action", "")
            if action in ACTIONS_REQUIRING_TARGET:
                issues.append(
                    ValidationIssue(
                        severity=Severity.ERROR,
                        message=f"Step {i}: selector is empty",
                        tip="Target element needs a valid CSS selector.",
                        step_num=i,
                    )
                )

    return issues


# =============================================================================
# Level 4: Warnings (Non-blocking)
# =============================================================================


def check_warnings(data: dict) -> list[ValidationIssue]:
    """Check for potential issues that don't block replay."""
    issues = []
    steps = data.get("steps", [])

    if not steps:
        return issues

    # Check if first step is navigate (only warn if there's no start_url in metadata)
    first_step = steps[0] if steps else {}
    metadata = data.get("metadata", {})
    has_start_url = metadata.get("start_url") if isinstance(metadata, dict) else None
    if isinstance(first_step, dict) and first_step.get("action") != "navigate" and not has_start_url:
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                message="Recording doesn't start with a `navigate` command",
                tip="Consider adding an initial URL for reliable replay",
            )
        )

    # Check for large time gaps
    prev_timestamp = 0
    for i, step in enumerate(steps, 1):
        if not isinstance(step, dict):
            continue

        timestamp = step.get("timestamp", 0)
        if not isinstance(timestamp, (int, float)):
            continue

        gap_ms = timestamp - prev_timestamp
        gap_seconds = gap_ms / 1000

        if gap_seconds > WARNING_TIME_GAP_SECONDS and i > 1:
            issues.append(
                ValidationIssue(
                    severity=Severity.WARNING,
                    message=f"Steps {i - 1}-{i}: {gap_seconds:.0f} second gap",
                    tip="Long pauses may indicate missed interactions during recording.",
                    step_num=i,
                )
            )

        prev_timestamp = timestamp

    # Check for very long recordings
    if len(steps) > WARNING_STEP_COUNT:
        issues.append(
            ValidationIssue(
                severity=Severity.WARNING,
                message=f"Recording has {len(steps)} steps",
                tip="Very long recordings may be harder to maintain. Consider splitting into smaller recordings.",
            )
        )

    return issues


# =============================================================================
# Main Validation Function
# =============================================================================


def validate_recording_file(filepath: Path) -> ValidationResult:
    """Run all validation checks on a recording file.

    Args:
        filepath: Path to the recording YAML file

    Returns:
        ValidationResult with valid status and list of issues
    """
    issues = []

    # Level 1: Syntax
    syntax_issues, content = validate_yaml_syntax(filepath)
    issues.extend(syntax_issues)

    if any(i.severity == Severity.ERROR for i in issues):
        return ValidationResult(valid=False, issues=issues)

    # Parse YAML (we know it's valid at this point)
    data = yaml.safe_load(content)

    # Level 2: Structure
    structure_issues = validate_structure(data)
    issues.extend(structure_issues)

    if any(i.severity == Severity.ERROR for i in issues):
        return ValidationResult(valid=False, issues=issues)

    # Level 3: Logic
    logic_issues = validate_logic(data, filepath.parent)
    issues.extend(logic_issues)

    # Level 4: Warnings
    warning_issues = check_warnings(data)
    issues.extend(warning_issues)

    has_errors = any(i.severity == Severity.ERROR for i in issues)
    return ValidationResult(valid=not has_errors, issues=issues)


# =============================================================================
# CLI Command
# =============================================================================


@click.command()
@click.argument(
    "recording_file",
    required=False,
    type=click.Path(exists=False),
)
@click.option(
    "--strict",
    is_flag=True,
    help="Treat warnings as errors (exit with error code if warnings found)",
)
@click.option(
    "--json",
    "-j",
    "json_output",
    is_flag=True,
    help="Output results as JSON for tooling integration",
)
def validate(recording_file: str | None, strict: bool, json_output: bool):
    """Validate a recording file before replay.

    Checks for YAML syntax errors, missing files, timestamp issues,
    and other problems that could cause replay failures.

    \b
    Examples:
        inspekt validate                    # Validate most recent recording
        inspekt validate my-recording.yaml  # Validate specific file
        inspekt validate --strict           # Treat warnings as errors
        inspekt validate --json             # JSON output for CI/tooling
    """
    import json
    import sys

    from inspekt.app.cli.recording_utils import find_most_recent_recording

    # Find recording file
    if recording_file is None:
        recent = find_most_recent_recording()
        if recent is None:
            if json_output:
                print(json.dumps({"valid": False, "error": "No recording file found"}))
            else:
                click.echo("Error: No recording file specified and no .yaml files found.", err=True)
            sys.exit(1)
        filepath = recent
        if not json_output:
            click.echo(f"Validating: {filepath.name}")
    else:
        filepath = Path(recording_file)

    # Run validation
    result = validate_recording_file(filepath)

    # JSON output mode
    if json_output:
        output = {
            "valid": result.valid,
            "file": str(filepath),
            "errors": [
                {
                    "message": issue.message,
                    "tip": issue.tip,
                    "step": issue.step_num,
                    "line": issue.line_num,
                }
                for issue in result.errors
            ],
            "warnings": [
                {
                    "message": issue.message,
                    "tip": issue.tip,
                    "step": issue.step_num,
                    "line": issue.line_num,
                }
                for issue in result.warnings
            ],
        }
        print(json.dumps(output, indent=2))

        if not result.valid or (strict and result.warnings):
            sys.exit(1)
        sys.exit(0)

    # Normal output mode
    display_validation_results(result, filepath)

    if not result.valid:
        sys.exit(1)

    if strict and result.warnings:
        click.echo()
        click.secho("Strict mode: treating warnings as errors", fg="red")
        sys.exit(1)

    sys.exit(0)


# =============================================================================
# Display Functions
# =============================================================================


def display_validation_results(result: ValidationResult, filepath: Path) -> None:
    """Display validation results with colors and formatting.

    Args:
        result: ValidationResult from validate_recording_file
        filepath: Path to the recording file (for display)
    """
    filename = filepath.name

    if result.valid and not result.warnings:
        click.secho(f"✓ {filename} validated successfully", fg="green")
        return

    # Show errors first
    for issue in result.errors:
        click.echo()
        click.secho("✗ Error: ", fg="red", bold=True, nl=False)
        click.echo(issue.message)

        if issue.context:
            click.echo()
            click.echo(issue.context)

        if issue.tip:
            click.echo()
            from inspekt.app.cli.table import print_hint
            print_hint(issue.tip)

    # Show warnings
    for issue in result.warnings:
        click.echo()
        from inspekt.app.cli.table import _style_with_inline_code
        click.secho("⚠ ", fg="yellow", nl=False)
        click.echo(_style_with_inline_code(issue.message, base_fg="white"))

        if issue.tip:
            from inspekt.app.cli.table import print_hint
            print_hint(issue.tip)

    # Summary
    click.echo()
    if result.errors:
        click.secho(f"Found {len(result.errors)} error(s)", fg="red", bold=True)
    if result.warnings and result.valid:
        click.secho(f"✓ {filename} is valid with {len(result.warnings)} warning(s)", fg="yellow")
    elif result.warnings:
        click.secho(f"Found {len(result.warnings)} warning(s)", fg="yellow")
