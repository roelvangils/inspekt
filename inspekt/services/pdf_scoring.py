"""
PDF Accessibility Scoring Service.

Calculates a weighted accessibility score (0-100) with letter grade
based on PDF accessibility check results. The score provides an
at-a-glance assessment that answers: "How accessible is this PDF?"

Scoring Algorithm:
1. Check for "knockout" conditions (critical failures that cap the score):
   - Untagged PDF: max score 40%
   - Scanned/image-only: max score 35%
   - AT access blocked: max score 30%

2. Calculate category-weighted score:
   - Structure & Tags: 25%
   - Alternative Text: 20%
   - Reading Order: 15%
   - Color & Contrast: 10%
   - Forms: 10%
   - Links & Navigation: 10%
   - Metadata: 10%

3. Deduct points based on issue severity:
   - Critical issues: -10 points each (max -50)
   - Serious issues: -5 points each (max -30)
   - Moderate issues: -2 points each (max -15)
   - Minor issues: -0.5 points each (max -5)

4. Apply knockout cap (final score cannot exceed knockout limit)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import PDFFullResult, VeraPDFViolation


class AccessibilityGrade(Enum):
    """Letter grades for accessibility scores."""

    A_PLUS = "A+"  # 95-100
    A = "A"  # 90-94
    B = "B"  # 80-89
    C = "C"  # 70-79
    D = "D"  # 60-69
    F = "F"  # 0-59

    @classmethod
    def from_score(cls, score: float) -> AccessibilityGrade:
        """Determine letter grade from numeric score."""
        if score >= 95:
            return cls.A_PLUS
        elif score >= 90:
            return cls.A
        elif score >= 80:
            return cls.B
        elif score >= 70:
            return cls.C
        elif score >= 60:
            return cls.D
        else:
            return cls.F

    @property
    def color(self) -> str:
        """CSS color for the grade."""
        return {
            AccessibilityGrade.A_PLUS: "#22c55e",  # Green
            AccessibilityGrade.A: "#22c55e",  # Green
            AccessibilityGrade.B: "#84cc16",  # Lime
            AccessibilityGrade.C: "#eab308",  # Yellow
            AccessibilityGrade.D: "#f97316",  # Orange
            AccessibilityGrade.F: "#ef4444",  # Red
        }[self]

    @property
    def label(self) -> str:
        """Short label for the grade."""
        return {
            AccessibilityGrade.A_PLUS: "Excellent",
            AccessibilityGrade.A: "Very Good",
            AccessibilityGrade.B: "Good",
            AccessibilityGrade.C: "Fair",
            AccessibilityGrade.D: "Poor",
            AccessibilityGrade.F: "Failing",
        }[self]

    @property
    def description(self) -> str:
        """Human-readable description of the grade."""
        return {
            AccessibilityGrade.A_PLUS: "Excellent - Fully accessible",
            AccessibilityGrade.A: "Very Good - Minor improvements possible",
            AccessibilityGrade.B: "Good - Some issues to address",
            AccessibilityGrade.C: "Fair - Significant improvements needed",
            AccessibilityGrade.D: "Poor - Major accessibility barriers",
            AccessibilityGrade.F: "Failing - Critical accessibility issues",
        }[self]


class ScoreCategory(Enum):
    """Categories for grouping accessibility checks."""

    STRUCTURE = "Structure & Tags"
    ALT_TEXT = "Alternative Text"
    READING_ORDER = "Reading Order"
    COLOR_CONTRAST = "Color & Contrast"
    FORMS = "Forms"
    LINKS_NAV = "Links & Navigation"
    METADATA = "Metadata"


# Category weights (must sum to 1.0)
CATEGORY_WEIGHTS: dict[ScoreCategory, float] = {
    ScoreCategory.STRUCTURE: 0.25,
    ScoreCategory.ALT_TEXT: 0.20,
    ScoreCategory.READING_ORDER: 0.15,
    ScoreCategory.COLOR_CONTRAST: 0.10,
    ScoreCategory.FORMS: 0.10,
    ScoreCategory.LINKS_NAV: 0.10,
    ScoreCategory.METADATA: 0.10,
}

# Map check IDs to categories
CHECK_CATEGORIES: dict[str, ScoreCategory] = {
    # Structure checks
    "tagged": ScoreCategory.STRUCTURE,
    "scanned": ScoreCategory.STRUCTURE,
    # Metadata checks
    "title": ScoreCategory.METADATA,
    "language": ScoreCategory.METADATA,
    "xmp_metadata": ScoreCategory.METADATA,
    # Protection/Access
    "protected": ScoreCategory.STRUCTURE,
    # Navigation
    "bookmarks": ScoreCategory.LINKS_NAV,
    # Forms
    "forms": ScoreCategory.FORMS,
    "xfa": ScoreCategory.FORMS,
    # Alternative text
    "figure_alt_text": ScoreCategory.ALT_TEXT,
}

# Severity point deductions
SEVERITY_DEDUCTIONS: dict[str, float] = {
    "critical": 10.0,
    "serious": 5.0,
    "moderate": 2.0,
    "minor": 0.5,
}

# Maximum deductions per severity (prevents single category from dominating)
MAX_DEDUCTIONS: dict[str, float] = {
    "critical": 50.0,
    "serious": 30.0,
    "moderate": 15.0,
    "minor": 5.0,
}

# Knockout rules - critical failures that cap the maximum achievable score
# These represent fundamental accessibility barriers that cannot be overcome
# by passing other checks. Format: (check_id, description, max_score)
KNOCKOUT_RULES: list[tuple[str, str, float]] = [
    ("untagged", "Document is not tagged", 40.0),
    ("scanned", "Document is scanned/image-only", 35.0),
    ("protected", "Document blocks assistive technology access", 30.0),
]


@dataclass
class CategoryScore:
    """Score breakdown for a single category."""

    category: ScoreCategory
    score: float  # 0-100 for this category
    weight: float  # Weight applied to overall score
    weighted_score: float  # score * weight
    issues_count: int
    critical_count: int
    serious_count: int
    moderate_count: int
    minor_count: int
    affected_items: int = 0  # Actual count of affected items (e.g., 60 images missing alt text)
    affected_items_label: str = ""  # Label for affected items (e.g., "images missing alt text")

    @property
    def has_issues(self) -> bool:
        """Check if category has any issues."""
        return self.issues_count > 0

    @property
    def display_issues(self) -> str:
        """Get human-readable issues text, preferring affected_items when available."""
        if self.affected_items > 0 and self.affected_items_label:
            return f"{self.affected_items} {self.affected_items_label}"
        elif self.issues_count > 0:
            return f"{self.issues_count} issue{'s' if self.issues_count != 1 else ''}"
        else:
            return "No issues"


@dataclass
class AccessibilityScore:
    """Complete accessibility score with breakdown."""

    score: float  # 0-100 overall score
    grade: AccessibilityGrade
    category_scores: dict[ScoreCategory, CategoryScore] = field(default_factory=dict)
    passed_checks: int = 0
    failed_checks: int = 0
    warnings: int = 0
    total_violations: int = 0

    # Breakdown by severity
    critical_count: int = 0
    serious_count: int = 0
    moderate_count: int = 0
    minor_count: int = 0

    # Knockout information
    knockout_applied: bool = False
    knockout_reasons: list[str] = field(default_factory=list)
    knockout_cap: float = 100.0  # Maximum score allowed
    uncapped_score: float = 0.0  # Score before knockout applied

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate as percentage."""
        total = self.passed_checks + self.failed_checks
        return (self.passed_checks / total * 100) if total > 0 else 100.0

    @property
    def color(self) -> str:
        """CSS color for the score."""
        return self.grade.color

    @property
    def description(self) -> str:
        """Human-readable description."""
        return self.grade.description

    def get_top_issues(self, limit: int = 5) -> list[tuple[ScoreCategory, int]]:
        """Get categories with most issues, sorted by issue count."""
        categories_with_issues = [
            (cat, cs.issues_count)
            for cat, cs in self.category_scores.items()
            if cs.has_issues
        ]
        return sorted(categories_with_issues, key=lambda x: x[1], reverse=True)[:limit]


def calculate_accessibility_score(result: PDFFullResult) -> AccessibilityScore:
    """
    Calculate weighted accessibility score based on PDF check results.

    The scoring algorithm:
    1. Checks knockout conditions (critical failures that cap the score)
    2. Starts with 100 points (perfect score)
    3. Deducts points based on issue severity
    4. Applies category weights for balanced scoring
    5. Caps deductions to prevent extreme scores from single issues
    6. Applies knockout cap to final score

    Args:
        result: PDFFullResult from the PDF checker

    Returns:
        AccessibilityScore with complete breakdown
    """
    # Check knockout conditions first
    knockout_cap = 100.0
    knockout_reasons: list[str] = []

    for check in result.basic.checks:
        if check.status == "fail":
            # Check for untagged PDF
            if check.check_id == "tagged":
                knockout_cap = min(knockout_cap, 40.0)
                knockout_reasons.append("Document is not tagged")
            # Check for scanned/image-only
            elif check.check_id == "scanned":
                knockout_cap = min(knockout_cap, 35.0)
                knockout_reasons.append("Document is scanned/image-only")
            # Check for AT access blocked
            elif check.check_id == "protected":
                knockout_cap = min(knockout_cap, 30.0)
                knockout_reasons.append("Document blocks assistive technology access")

    knockout_applied = knockout_cap < 100.0

    # Initialize counters
    passed_checks = 0
    failed_checks = 0
    warnings = 0
    total_violations = 0

    # Track deductions by severity
    severity_totals: dict[str, float] = {
        "critical": 0.0,
        "serious": 0.0,
        "moderate": 0.0,
        "minor": 0.0,
    }

    # Track issues by category
    category_issues: dict[ScoreCategory, dict[str, int]] = {
        cat: {"critical": 0, "serious": 0, "moderate": 0, "minor": 0, "total": 0}
        for cat in ScoreCategory
    }

    # Track affected items count per category (for more detailed display)
    category_affected: dict[ScoreCategory, tuple[int, str]] = {}  # (count, label)

    # Track scaled deductions per category (for accurate category scores)
    category_deductions: dict[ScoreCategory, float] = {cat: 0.0 for cat in ScoreCategory}

    # Process basic checks
    for check in result.basic.checks:
        category = CHECK_CATEGORIES.get(check.check_id, ScoreCategory.STRUCTURE)

        if check.status == "pass":
            passed_checks += 1
        elif check.status == "fail":
            failed_checks += 1
            severity = check.severity.lower()
            if severity in severity_totals:
                deduction = SEVERITY_DEDUCTIONS.get(severity, 0)

                # Scale deduction for figure alt text based on number of missing items
                # A PDF with 1 missing alt text is less serious than one with 63
                if check.check_id == "figure_alt_text" and check.details:
                    figures_missing = check.details.get("figures_missing_alt", 0)
                    figures_total = check.details.get("figures_total", 1)
                    if figures_total > 0 and figures_missing > 0:
                        # Track affected items for display
                        category_affected[ScoreCategory.ALT_TEXT] = (
                            figures_missing,
                            "images missing alt text"
                        )

                        # Apply scaled deduction: each missing alt text adds severity
                        # Use logarithmic scaling to prevent extreme deductions
                        # 1 missing = 1x, 10 missing = 2x, 100 missing = 3x
                        import math
                        scale_factor = 1 + math.log10(max(1, figures_missing))
                        # Also consider percentage missing (worse if ALL are missing)
                        percentage_missing = figures_missing / figures_total
                        # Additional penalty if >50% are missing
                        percentage_factor = 1.5 if percentage_missing > 0.5 else 1.0
                        deduction = deduction * scale_factor * percentage_factor

                severity_totals[severity] += deduction
                category_deductions[category] += deduction
                category_issues[category][severity] += 1
                category_issues[category]["total"] += 1
        elif check.status == "warn":
            warnings += 1
            # Warnings count as minor issues
            severity_totals["minor"] += 0.25
            category_issues[category]["minor"] += 1
            category_issues[category]["total"] += 1

    # Process simple checks if available
    if result.simple:
        for check in result.simple.checks:
            category = CHECK_CATEGORIES.get(check.check_id, ScoreCategory.STRUCTURE)

            if check.status == "pass":
                passed_checks += 1
            elif check.status == "fail":
                failed_checks += 1
                severity = check.severity.lower()
                if severity in severity_totals:
                    deduction = SEVERITY_DEDUCTIONS.get(severity, 0)
                    severity_totals[severity] += deduction
                    category_issues[category][severity] += 1
                    category_issues[category]["total"] += 1
            elif check.status == "warn":
                warnings += 1
                severity_totals["minor"] += 0.25
                category_issues[category]["minor"] += 1
                category_issues[category]["total"] += 1

    # Process veraPDF violations if available
    if result.verapdf:
        total_violations = len(result.verapdf.violations)
        for violation in result.verapdf.violations:
            # Map veraPDF violations to categories based on clause
            category = _categorize_verapdf_violation(violation)
            severity = violation.severity.lower()

            if severity in severity_totals:
                deduction = SEVERITY_DEDUCTIONS.get(severity, 0)
                severity_totals[severity] += deduction
                category_issues[category][severity] += 1
                category_issues[category]["total"] += 1

    # Apply maximum deduction caps
    total_deduction = 0.0
    for severity, total in severity_totals.items():
        max_deduct = MAX_DEDUCTIONS.get(severity, 0)
        capped = min(total, max_deduct)
        total_deduction += capped

    # Calculate uncapped score (minimum 0)
    uncapped_score = max(0.0, 100.0 - total_deduction)

    # Apply knockout cap - this is the key change!
    # An untagged PDF should never score above 40%, regardless of other checks
    score = min(uncapped_score, knockout_cap)

    # Calculate category scores
    category_scores = {}
    for category in ScoreCategory:
        issues = category_issues[category]
        # Use the tracked scaled deduction (accounts for things like 60 missing alt texts)
        cat_deduction = category_deductions.get(category, 0.0)
        cat_score = max(0.0, 100.0 - cat_deduction)
        weight = CATEGORY_WEIGHTS[category]

        # Get affected items info if available
        affected_count, affected_label = category_affected.get(category, (0, ""))

        category_scores[category] = CategoryScore(
            category=category,
            score=cat_score,
            weight=weight,
            weighted_score=cat_score * weight,
            issues_count=issues["total"],
            critical_count=issues["critical"],
            serious_count=issues["serious"],
            moderate_count=issues["moderate"],
            minor_count=issues["minor"],
            affected_items=affected_count,
            affected_items_label=affected_label,
        )

    # Determine grade
    grade = AccessibilityGrade.from_score(score)

    return AccessibilityScore(
        score=round(score, 1),
        grade=grade,
        category_scores=category_scores,
        passed_checks=passed_checks,
        failed_checks=failed_checks,
        warnings=warnings,
        total_violations=total_violations,
        critical_count=int(severity_totals["critical"] / SEVERITY_DEDUCTIONS["critical"])
        if severity_totals["critical"] > 0
        else 0,
        serious_count=int(severity_totals["serious"] / SEVERITY_DEDUCTIONS["serious"])
        if severity_totals["serious"] > 0
        else 0,
        moderate_count=int(severity_totals["moderate"] / SEVERITY_DEDUCTIONS["moderate"])
        if severity_totals["moderate"] > 0
        else 0,
        minor_count=int(severity_totals["minor"] / SEVERITY_DEDUCTIONS["minor"])
        if severity_totals["minor"] > 0
        else 0,
        # Knockout information
        knockout_applied=knockout_applied,
        knockout_reasons=knockout_reasons,
        knockout_cap=knockout_cap,
        uncapped_score=round(uncapped_score, 1),
    )


def _categorize_verapdf_violation(violation: VeraPDFViolation) -> ScoreCategory:
    """
    Categorize a veraPDF violation based on its rule and clause.

    This maps ISO 14289-1 (PDF/UA) clauses to our score categories.
    """
    clause = violation.clause.lower() if violation.clause else ""
    rule_id = violation.rule_id.lower() if violation.rule_id else ""
    description = violation.description.lower() if violation.description else ""

    # Structure and tagging
    if any(kw in clause for kw in ["7.1", "7.2", "structure", "tag", "14.7", "14.8"]):
        return ScoreCategory.STRUCTURE

    # Alternative text
    if any(kw in description for kw in ["alt", "alternative", "figure", "image"]):
        return ScoreCategory.ALT_TEXT

    # Reading order
    if any(kw in description for kw in ["reading", "order", "artifact"]):
        return ScoreCategory.READING_ORDER

    # Color and contrast
    if any(kw in description for kw in ["color", "contrast"]):
        return ScoreCategory.COLOR_CONTRAST

    # Forms
    if any(kw in clause for kw in ["7.6", "form", "acroform", "widget"]):
        return ScoreCategory.FORMS

    # Links and navigation
    if any(kw in description for kw in ["link", "bookmark", "destination", "outline"]):
        return ScoreCategory.LINKS_NAV

    # Metadata
    if any(kw in description for kw in ["title", "lang", "metadata", "xmp"]):
        return ScoreCategory.METADATA

    # Default to structure
    return ScoreCategory.STRUCTURE


def get_score_summary(score: AccessibilityScore) -> str:
    """
    Generate a human-readable summary of the accessibility score.

    Args:
        score: AccessibilityScore to summarize

    Returns:
        Multi-line string summary
    """
    lines = [
        f"Accessibility Score: {score.score}/100 ({score.grade.value})",
        f"Grade: {score.description}",
        "",
        f"Passed: {score.passed_checks} | Failed: {score.failed_checks} | Warnings: {score.warnings}",
    ]

    if score.total_violations > 0:
        lines.append(f"Total Violations: {score.total_violations}")

    # Add severity breakdown if there are issues
    if score.failed_checks > 0 or score.warnings > 0:
        lines.append("")
        lines.append("Issues by Severity:")
        if score.critical_count > 0:
            lines.append(f"  • Critical: {score.critical_count}")
        if score.serious_count > 0:
            lines.append(f"  • Serious: {score.serious_count}")
        if score.moderate_count > 0:
            lines.append(f"  • Moderate: {score.moderate_count}")
        if score.minor_count > 0:
            lines.append(f"  • Minor: {score.minor_count}")

    # Add top problem areas
    top_issues = score.get_top_issues(3)
    if top_issues:
        lines.append("")
        lines.append("Top Problem Areas:")
        for category, count in top_issues:
            lines.append(f"  • {category.value}: {count} issue(s)")

    return "\n".join(lines)
