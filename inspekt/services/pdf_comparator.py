"""
PDF Checker Comparator.

This module provides utilities for cross-validating PDF accessibility checkers,
using SimplePDFChecker as an oracle (ground truth) to validate PDFBasicChecker.

The comparator ensures that the common checks between both checkers agree,
giving confidence in the correctness of the basic checker.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import PDFBasicResult, PDFCheckResult
    from inspekt.services.simple_pdf_checker import SimplePDFCheckResult, SimplePDFResult


# Checks that exist in both PDFBasicChecker and SimplePDFChecker
COMMON_CHECK_IDS = ["tagged", "title", "language", "protected", "bookmarks", "scanned"]


@dataclass
class CheckComparison:
    """Comparison result for a single check between two checkers."""

    check_id: str
    basic_status: str
    simple_status: str
    agrees: bool
    basic_message: str
    simple_message: str


@dataclass
class ComparisonResult:
    """Result of comparing PDFBasicChecker and SimplePDFChecker."""

    file_path: Path
    comparisons: list[CheckComparison]

    @property
    def all_agree(self) -> bool:
        """Check if all common checks agree between the two checkers."""
        return all(c.agrees for c in self.comparisons)

    @property
    def disagreements(self) -> list[CheckComparison]:
        """Get list of checks where the two checkers disagree."""
        return [c for c in self.comparisons if not c.agrees]

    @property
    def agreement_count(self) -> int:
        """Number of checks that agree."""
        return sum(1 for c in self.comparisons if c.agrees)

    @property
    def disagreement_count(self) -> int:
        """Number of checks that disagree."""
        return sum(1 for c in self.comparisons if not c.agrees)


def _get_check_by_id(
    checks: list[PDFCheckResult] | list[SimplePDFCheckResult],
    check_id: str,
) -> PDFCheckResult | SimplePDFCheckResult | None:
    """Get a check result by its ID."""
    for check in checks:
        if check.check_id == check_id:
            return check
    return None


def compare_checkers(
    basic_result: PDFBasicResult,
    simple_result: SimplePDFResult,
) -> ComparisonResult:
    """
    Compare results from PDFBasicChecker and SimplePDFChecker.

    Compares the common checks between both checkers and returns
    a detailed comparison result.

    Args:
        basic_result: Result from PDFBasicChecker
        simple_result: Result from SimplePDFChecker

    Returns:
        ComparisonResult with detailed comparison for each common check
    """
    comparisons = []

    for check_id in COMMON_CHECK_IDS:
        basic_check = _get_check_by_id(basic_result.checks, check_id)
        simple_check = _get_check_by_id(simple_result.checks, check_id)

        if basic_check is None or simple_check is None:
            # One of the checkers doesn't have this check
            continue

        # Compare statuses
        # Note: We consider pass/pass, fail/fail, warn/warn as agreement
        # but also pass/warn and warn/pass could be considered acceptable
        agrees = basic_check.status == simple_check.status

        comparisons.append(
            CheckComparison(
                check_id=check_id,
                basic_status=basic_check.status,
                simple_status=simple_check.status,
                agrees=agrees,
                basic_message=basic_check.message,
                simple_message=simple_check.message,
            )
        )

    return ComparisonResult(
        file_path=basic_result.metadata.file_path,
        comparisons=comparisons,
    )


def compare_pdf(file_path: Path | str) -> ComparisonResult:
    """
    Run both checkers on a PDF and compare their results.

    Convenience function that runs both PDFBasicChecker and SimplePDFChecker
    on the same PDF file and compares the results.

    Args:
        file_path: Path to the PDF file

    Returns:
        ComparisonResult with detailed comparison

    Raises:
        FileNotFoundError: If the PDF file doesn't exist
    """
    from inspekt.services.pdf_checker import PDFBasicChecker
    from inspekt.services.simple_pdf_checker import SimplePDFChecker

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    basic_checker = PDFBasicChecker()
    simple_checker = SimplePDFChecker()

    basic_result = basic_checker.check(file_path)
    simple_result = simple_checker.check(file_path)

    return compare_checkers(basic_result, simple_result)


def validate_basic_checker(file_path: Path | str) -> tuple[bool, list[str]]:
    """
    Validate PDFBasicChecker against SimplePDFChecker (oracle).

    This function is intended for use in tests to ensure PDFBasicChecker
    produces correct results by comparing against SimplePDFChecker.

    Args:
        file_path: Path to the PDF file

    Returns:
        Tuple of (all_checks_agree, list_of_error_messages)
    """
    comparison = compare_pdf(file_path)

    if comparison.all_agree:
        return True, []

    errors = []
    for disagreement in comparison.disagreements:
        errors.append(
            f"{comparison.file_path.name}: {disagreement.check_id} mismatch "
            f"(basic={disagreement.basic_status}, simple={disagreement.simple_status})"
        )

    return False, errors
