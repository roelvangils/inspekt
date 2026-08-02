"""
Cross-validation tests for PDF Accessibility Checkers.

These tests validate that PDFBasicChecker produces correct results by comparing
against SimplePDFChecker (the oracle/ground truth).
"""

from __future__ import annotations

import pytest

# Import fixtures from the PDF fixtures conftest
pytest_plugins = ["tests.fixtures.pdf.conftest"]


# The checks that exist in both PDFBasicChecker and SimplePDFChecker
COMMON_CHECK_IDS = ["tagged", "title", "language", "protected", "bookmarks", "scanned"]


class TestCheckerAgreement:
    """Validate PDFBasicChecker against SimplePDFChecker (oracle)."""

    def test_accessible_pdf_agreement(self, accessible_pdf):
        """Basic and Simple checkers must agree on an accessible PDF."""
        from inspekt.services.pdf_comparator import compare_pdf

        comparison = compare_pdf(accessible_pdf)

        assert comparison.all_agree, (
            f"Checkers disagree on {accessible_pdf.name}:\n"
            + "\n".join(
                f"  - {d.check_id}: basic={d.basic_status}, simple={d.simple_status}"
                for d in comparison.disagreements
            )
        )

    def test_untagged_pdf_agreement(self, untagged_pdf):
        """Basic and Simple checkers must agree on an untagged PDF."""
        from inspekt.services.pdf_comparator import compare_pdf

        comparison = compare_pdf(untagged_pdf)

        assert comparison.all_agree, (
            f"Checkers disagree on {untagged_pdf.name}:\n"
            + "\n".join(
                f"  - {d.check_id}: basic={d.basic_status}, simple={d.simple_status}"
                for d in comparison.disagreements
            )
        )

    def test_no_title_pdf_agreement(self, no_title_pdf):
        """Basic and Simple checkers must agree on a PDF without title."""
        from inspekt.services.pdf_comparator import compare_pdf

        comparison = compare_pdf(no_title_pdf)

        assert comparison.all_agree, (
            f"Checkers disagree on {no_title_pdf.name}:\n"
            + "\n".join(
                f"  - {d.check_id}: basic={d.basic_status}, simple={d.simple_status}"
                for d in comparison.disagreements
            )
        )

    def test_no_language_pdf_agreement(self, no_language_pdf):
        """Basic and Simple checkers must agree on a PDF without language."""
        from inspekt.services.pdf_comparator import compare_pdf

        comparison = compare_pdf(no_language_pdf)

        assert comparison.all_agree, (
            f"Checkers disagree on {no_language_pdf.name}:\n"
            + "\n".join(
                f"  - {d.check_id}: basic={d.basic_status}, simple={d.simple_status}"
                for d in comparison.disagreements
            )
        )

    def test_long_no_bookmarks_pdf_agreement(self, long_no_bookmarks_pdf):
        """Basic and Simple checkers must agree on a long PDF without bookmarks."""
        from inspekt.services.pdf_comparator import compare_pdf

        comparison = compare_pdf(long_no_bookmarks_pdf)

        assert comparison.all_agree, (
            f"Checkers disagree on {long_no_bookmarks_pdf.name}:\n"
            + "\n".join(
                f"  - {d.check_id}: basic={d.basic_status}, simple={d.simple_status}"
                for d in comparison.disagreements
            )
        )

    @pytest.mark.parametrize("check_id", COMMON_CHECK_IDS)
    def test_individual_check_agreement_accessible(self, check_id, accessible_pdf):
        """Each common check should agree on accessible PDF."""
        from inspekt.services.pdf_checker import PDFBasicChecker
        from inspekt.services.simple_pdf_checker import SimplePDFChecker

        basic = PDFBasicChecker()
        simple = SimplePDFChecker()

        basic_result = basic.check(accessible_pdf)
        simple_result = simple.check(accessible_pdf)

        basic_check = None
        simple_check = None

        for c in basic_result.checks:
            if c.check_id == check_id:
                basic_check = c
                break

        for c in simple_result.checks:
            if c.check_id == check_id:
                simple_check = c
                break

        if basic_check is None or simple_check is None:
            pytest.skip(f"Check {check_id} not found in one of the checkers")

        assert basic_check.status == simple_check.status, (
            f"{check_id} mismatch on {accessible_pdf.name}: "
            f"basic={basic_check.status} ({basic_check.message}), "
            f"simple={simple_check.status} ({simple_check.message})"
        )


class TestValidateBasicChecker:
    """Test the validate_basic_checker convenience function."""

    def test_validate_accessible_pdf(self, accessible_pdf):
        """validate_basic_checker should return True for accessible PDF."""
        from inspekt.services.pdf_comparator import validate_basic_checker

        is_valid, errors = validate_basic_checker(accessible_pdf)

        assert is_valid, "Basic checker validation failed:\n" + "\n".join(errors)
        assert len(errors) == 0

    def test_validate_all_fixtures(self, all_pdf_fixtures):
        """validate_basic_checker should pass for all test fixtures."""
        from inspekt.services.pdf_comparator import validate_basic_checker

        all_errors = []
        for pdf_path in all_pdf_fixtures:
            is_valid, errors = validate_basic_checker(pdf_path)
            if not is_valid:
                all_errors.extend(errors)

        assert len(all_errors) == 0, (
            f"Basic checker validation failed for {len(all_errors)} checks:\n"
            + "\n".join(all_errors)
        )


class TestComparisonResult:
    """Test the ComparisonResult class."""

    def test_comparison_result_properties(self, accessible_pdf):
        """ComparisonResult should have correct properties."""
        from inspekt.services.pdf_comparator import compare_pdf

        comparison = compare_pdf(accessible_pdf)

        # Should have comparisons for all common checks
        assert len(comparison.comparisons) == len(COMMON_CHECK_IDS)

        # Properties should be consistent
        assert comparison.agreement_count + comparison.disagreement_count == len(comparison.comparisons)
        assert comparison.all_agree == (comparison.disagreement_count == 0)

    def test_file_path_preserved(self, accessible_pdf):
        """ComparisonResult should preserve the file path."""
        from inspekt.services.pdf_comparator import compare_pdf

        comparison = compare_pdf(accessible_pdf)

        assert comparison.file_path == accessible_pdf
