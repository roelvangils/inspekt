"""
Unit tests for PDF Accessibility Scoring.

Tests for the accessibility score calculation algorithm.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class TestAccessibilityScore:
    """Unit tests for accessibility score dataclass."""

    def test_score_properties(self):
        """Test AccessibilityScore properties."""
        from inspekt.services.pdf_scoring import (
            AccessibilityGrade,
            AccessibilityScore,
            CategoryScore,
            ScoreCategory,
        )

        category_scores = {
            ScoreCategory.STRUCTURE: CategoryScore(
                category=ScoreCategory.STRUCTURE,
                score=80.0,
                weight=0.25,
                weighted_score=20.0,
                issues_count=2,
                critical_count=1,
                serious_count=1,
                moderate_count=0,
                minor_count=0,
            ),
        }

        score = AccessibilityScore(
            score=80.0,
            grade=AccessibilityGrade.B,
            category_scores=category_scores,
            passed_checks=10,
            failed_checks=5,
            warnings=3,
            critical_count=1,
            serious_count=2,
            moderate_count=1,
            minor_count=1,
        )

        assert score.score == 80.0
        assert score.grade == AccessibilityGrade.B
        assert score.passed_checks == 10
        assert score.failed_checks == 5
        assert score.warnings == 3
        assert score.critical_count == 1
        assert score.serious_count == 2


class TestAccessibilityGrade:
    """Unit tests for AccessibilityGrade enum."""

    def test_grade_values(self):
        """Test that all grade values are correct."""
        from inspekt.services.pdf_scoring import AccessibilityGrade

        assert AccessibilityGrade.A_PLUS.value == "A+"
        assert AccessibilityGrade.A.value == "A"
        assert AccessibilityGrade.B.value == "B"
        assert AccessibilityGrade.C.value == "C"
        assert AccessibilityGrade.D.value == "D"
        assert AccessibilityGrade.F.value == "F"

    def test_grade_from_score(self):
        """Test AccessibilityGrade.from_score() method."""
        from inspekt.services.pdf_scoring import AccessibilityGrade

        # A+ boundary (95-100)
        assert AccessibilityGrade.from_score(100) == AccessibilityGrade.A_PLUS
        assert AccessibilityGrade.from_score(95) == AccessibilityGrade.A_PLUS

        # A boundary (90-94)
        assert AccessibilityGrade.from_score(94) == AccessibilityGrade.A
        assert AccessibilityGrade.from_score(90) == AccessibilityGrade.A

        # B boundary (80-89)
        assert AccessibilityGrade.from_score(89) == AccessibilityGrade.B
        assert AccessibilityGrade.from_score(80) == AccessibilityGrade.B

        # C boundary (70-79)
        assert AccessibilityGrade.from_score(79) == AccessibilityGrade.C
        assert AccessibilityGrade.from_score(70) == AccessibilityGrade.C

        # D boundary (60-69)
        assert AccessibilityGrade.from_score(69) == AccessibilityGrade.D
        assert AccessibilityGrade.from_score(60) == AccessibilityGrade.D

        # F boundary (0-59)
        assert AccessibilityGrade.from_score(59) == AccessibilityGrade.F
        assert AccessibilityGrade.from_score(0) == AccessibilityGrade.F


class TestScoreCalculation:
    """Unit tests for score calculation."""

    def test_perfect_score_for_no_failures(self):
        """A PDF with no failures should get a perfect score."""
        from inspekt.services.pdf_scoring import AccessibilityGrade, calculate_accessibility_score

        # Create mock result with all passes
        mock_result = MagicMock()
        mock_result.basic.passed = 10
        mock_result.basic.failed = 0
        mock_result.basic.warnings = 0
        mock_result.basic.checks = []
        mock_result.verapdf = None
        mock_result.simple = None

        score = calculate_accessibility_score(mock_result)

        assert score.score >= 95  # Should be in A+ range
        assert score.grade in (AccessibilityGrade.A_PLUS, AccessibilityGrade.A)
        assert score.failed_checks == 0

    def test_low_score_for_many_failures(self):
        """A PDF with many critical failures should get a low score."""
        from inspekt.services.pdf_scoring import AccessibilityGrade, calculate_accessibility_score

        # Create mock checks with critical failures
        mock_checks = []
        for i in range(5):
            check = MagicMock()
            check.status = "fail"
            check.severity = "critical"
            check.check_id = f"check_{i}"
            mock_checks.append(check)

        mock_result = MagicMock()
        mock_result.basic.passed = 0
        mock_result.basic.failed = 5
        mock_result.basic.warnings = 0
        mock_result.basic.checks = mock_checks
        mock_result.verapdf = None
        mock_result.simple = None

        score = calculate_accessibility_score(mock_result)

        assert score.score < 60  # Should be in F range
        assert score.grade == AccessibilityGrade.F
        assert score.critical_count == 5


class TestScoreCategory:
    """Unit tests for ScoreCategory enum."""

    def test_all_categories_exist(self):
        """Test that all expected categories exist."""
        from inspekt.services.pdf_scoring import ScoreCategory

        # The actual category names in the implementation
        expected_categories = [
            "STRUCTURE",
            "ALT_TEXT",
            "READING_ORDER",
            "COLOR_CONTRAST",
            "FORMS",
            "LINKS_NAV",  # Note: LINKS_NAV not LINKS
            "METADATA",
        ]

        for cat_name in expected_categories:
            assert hasattr(ScoreCategory, cat_name), f"Missing category: {cat_name}"


class TestCategoryScore:
    """Unit tests for CategoryScore dataclass."""

    def test_category_score_properties(self):
        """Test CategoryScore properties."""
        from inspekt.services.pdf_scoring import CategoryScore, ScoreCategory

        cat_score = CategoryScore(
            category=ScoreCategory.STRUCTURE,
            score=75.0,
            weight=0.25,
            weighted_score=18.75,
            issues_count=5,
            critical_count=1,
            serious_count=2,
            moderate_count=1,
            minor_count=1,
        )

        assert cat_score.category == ScoreCategory.STRUCTURE
        assert cat_score.score == 75.0
        assert cat_score.weight == 0.25
        assert cat_score.weighted_score == 18.75
        assert cat_score.issues_count == 5
        assert cat_score.has_issues  # Should be True when issues_count > 0

    def test_has_issues_property(self):
        """Test has_issues property."""
        from inspekt.services.pdf_scoring import CategoryScore, ScoreCategory

        # No issues
        cat_score_no_issues = CategoryScore(
            category=ScoreCategory.METADATA,
            score=100.0,
            weight=0.10,
            weighted_score=10.0,
            issues_count=0,
            critical_count=0,
            serious_count=0,
            moderate_count=0,
            minor_count=0,
        )
        assert not cat_score_no_issues.has_issues

        # Has issues
        cat_score_with_issues = CategoryScore(
            category=ScoreCategory.METADATA,
            score=80.0,
            weight=0.10,
            weighted_score=8.0,
            issues_count=2,
            critical_count=0,
            serious_count=1,
            moderate_count=1,
            minor_count=0,
        )
        assert cat_score_with_issues.has_issues
