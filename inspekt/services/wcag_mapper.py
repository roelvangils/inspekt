"""
WCAG Mapping Service for PDF Accessibility.

Maps ISO 14289-1 (PDF/UA-1) violations to WCAG 2.1 success criteria,
enabling accessibility teams to understand PDF issues in web accessibility terms.

The mapping covers:
- PDF/UA-1 clauses (7.x sections)
- ISO 32000-1 specific rules
- Matterhorn Protocol checkpoints
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from inspekt.services.pdf_checker import VeraPDFViolation


@dataclass
class WCAGCriterion:
    """A single WCAG success criterion."""

    id: str  # e.g., "1.1.1"
    title: str  # e.g., "Non-text Content"
    level: str  # A, AA, or AAA
    principle: str  # Perceivable, Operable, Understandable, Robust

    @property
    def url(self) -> str:
        """WCAG 2.1 Understanding document URL."""
        # Convert 1.1.1 to 1-1-1 format for URL
        slug = self.id.replace(".", "-")
        return f"https://www.w3.org/WAI/WCAG21/Understanding/{slug.lower()}"


@dataclass
class WCAGMapping:
    """Mapping from a PDF rule to WCAG criteria."""

    rule_id: str  # Original PDF/UA or ISO rule ID
    title: str
    wcag_criteria: list[WCAGCriterion] = field(default_factory=list)
    wcag_level: str = "A"  # Highest WCAG level required
    category: str = "structure"
    remediation_hint: str = ""

    @property
    def wcag_ids(self) -> list[str]:
        """List of WCAG criterion IDs."""
        return [c.id for c in self.wcag_criteria]

    @property
    def wcag_titles(self) -> list[str]:
        """List of WCAG criterion titles."""
        return [c.title for c in self.wcag_criteria]


@dataclass
class ViolationWithWCAG:
    """A veraPDF violation enriched with WCAG mapping."""

    violation: "VeraPDFViolation"
    mapping: WCAGMapping | None
    wcag_criteria: list[WCAGCriterion] = field(default_factory=list)

    @property
    def has_wcag_mapping(self) -> bool:
        """Check if this violation has WCAG mapping."""
        return self.mapping is not None and len(self.wcag_criteria) > 0

    @property
    def wcag_summary(self) -> str:
        """Brief WCAG summary for display."""
        if not self.wcag_criteria:
            return "No WCAG mapping"
        criteria = [f"{c.id} ({c.level})" for c in self.wcag_criteria]
        return ", ".join(criteria)


class WCAGMapper:
    """
    Maps PDF accessibility violations to WCAG 2.1 criteria.

    Loads mapping data from the pdfua_wcag_mapping.json file and
    provides methods to enrich violations with WCAG information.
    """

    def __init__(self):
        self._mapping_data = _load_mapping_data()
        self._wcag_reference = self._build_wcag_reference()
        self._rule_mappings = self._build_rule_mappings()

    def _build_wcag_reference(self) -> dict[str, WCAGCriterion]:
        """Build lookup table for WCAG criteria."""
        reference = {}
        for crit_id, data in self._mapping_data.get("wcag_reference", {}).items():
            reference[crit_id] = WCAGCriterion(
                id=crit_id,
                title=data.get("title", ""),
                level=data.get("level", "A"),
                principle=data.get("principle", ""),
            )
        return reference

    def _build_rule_mappings(self) -> dict[str, WCAGMapping]:
        """Build lookup table for rule-to-WCAG mappings."""
        mappings = {}

        # Process PDF/UA clause mappings
        for clause, data in self._mapping_data.get("mappings", {}).items():
            wcag_ids = data.get("wcag_criteria", [])
            wcag_criteria = [
                self._wcag_reference.get(crit_id)
                for crit_id in wcag_ids
                if crit_id in self._wcag_reference
            ]

            mappings[clause] = WCAGMapping(
                rule_id=clause,
                title=data.get("title", ""),
                wcag_criteria=[c for c in wcag_criteria if c],
                wcag_level=data.get("wcag_level", "A"),
                category=data.get("category", "structure"),
                remediation_hint=data.get("remediation_hint", ""),
            )

        # Process ISO 32000-1 rule mappings
        for rule_id, data in self._mapping_data.get("iso_32000_mappings", {}).items():
            wcag_ids = data.get("wcag_criteria", [])
            wcag_criteria = [
                self._wcag_reference.get(crit_id)
                for crit_id in wcag_ids
                if crit_id in self._wcag_reference
            ]

            mappings[rule_id] = WCAGMapping(
                rule_id=rule_id,
                title=data.get("title", ""),
                wcag_criteria=[c for c in wcag_criteria if c],
                wcag_level=data.get("wcag_level", "A"),
                category=data.get("category", "structure"),
                remediation_hint=data.get("remediation_hint", ""),
            )

        # Process Matterhorn Protocol mappings
        for checkpoint, data in self._mapping_data.get("matterhorn_mappings", {}).items():
            wcag_ids = data.get("wcag_criteria", [])
            wcag_criteria = [
                self._wcag_reference.get(crit_id)
                for crit_id in wcag_ids
                if crit_id in self._wcag_reference
            ]

            mappings[checkpoint] = WCAGMapping(
                rule_id=checkpoint,
                title=data.get("title", ""),
                wcag_criteria=[c for c in wcag_criteria if c],
                wcag_level=data.get("wcag_level", "A"),
                category=data.get("category", "structure"),
                remediation_hint=data.get("remediation_hint", ""),
            )

        return mappings

    def get_mapping(self, rule_id: str) -> WCAGMapping | None:
        """
        Get WCAG mapping for a rule ID.

        Tries multiple matching strategies:
        1. Exact match
        2. ISO rule ID extraction
        3. Matterhorn checkpoint extraction
        4. PDF/UA clause extraction

        Args:
            rule_id: The rule ID from veraPDF (e.g., "ISO-32000-1-7.18.1-1")

        Returns:
            WCAGMapping if found, None otherwise
        """
        # Try exact match first
        if rule_id in self._rule_mappings:
            return self._rule_mappings[rule_id]

        # Normalize rule ID
        normalized = rule_id.upper().strip()

        # Try ISO 32000-1 pattern: ISO-32000-1-{section}-{test}
        iso_match = re.match(r"ISO-32000-1-([\d.]+)(?:-\d+)?", normalized, re.IGNORECASE)
        if iso_match:
            section = iso_match.group(1)
            # Try progressively shorter matches
            for length in range(len(section.split(".")), 0, -1):
                partial = ".".join(section.split(".")[:length])
                key = f"ISO-32000-1-{partial}"
                if key in self._rule_mappings:
                    return self._rule_mappings[key]

        # Try Matterhorn pattern: {checkpoint}-{test}
        mh_match = re.match(r"(\d{2})-(\d{3})", normalized)
        if mh_match:
            checkpoint = f"{mh_match.group(1)}-{mh_match.group(2)}"
            if checkpoint in self._rule_mappings:
                return self._rule_mappings[checkpoint]

        # Try PDF/UA clause pattern: 7.x
        clause_match = re.search(r"\b(7\.\d+(?:\.\d+)?)\b", rule_id)
        if clause_match:
            clause = clause_match.group(1)
            if clause in self._rule_mappings:
                return self._rule_mappings[clause]

        return None

    def map_violation(self, violation: "VeraPDFViolation") -> ViolationWithWCAG:
        """
        Enrich a single violation with WCAG mapping.

        Args:
            violation: A VeraPDFViolation instance

        Returns:
            ViolationWithWCAG with mapping information
        """
        mapping = self.get_mapping(violation.rule_id)
        wcag_criteria = mapping.wcag_criteria if mapping else []

        return ViolationWithWCAG(
            violation=violation,
            mapping=mapping,
            wcag_criteria=wcag_criteria,
        )

    def map_violations(
        self, violations: list["VeraPDFViolation"]
    ) -> list[ViolationWithWCAG]:
        """
        Enrich a list of violations with WCAG mappings.

        Args:
            violations: List of VeraPDFViolation instances

        Returns:
            List of ViolationWithWCAG with mapping information
        """
        return [self.map_violation(v) for v in violations]

    def get_wcag_summary(
        self, violations: list["VeraPDFViolation"]
    ) -> dict[str, list["VeraPDFViolation"]]:
        """
        Group violations by WCAG criterion.

        Args:
            violations: List of VeraPDFViolation instances

        Returns:
            Dict mapping WCAG criterion IDs to lists of violations
        """
        summary: dict[str, list["VeraPDFViolation"]] = {}

        for violation in violations:
            mapping = self.get_mapping(violation.rule_id)
            if mapping:
                for criterion in mapping.wcag_criteria:
                    if criterion.id not in summary:
                        summary[criterion.id] = []
                    summary[criterion.id].append(violation)

        return summary

    def get_wcag_criterion(self, criterion_id: str) -> WCAGCriterion | None:
        """Get WCAG criterion details by ID."""
        return self._wcag_reference.get(criterion_id)

    def get_all_criteria(self) -> list[WCAGCriterion]:
        """Get all WCAG criteria in the reference."""
        return list(self._wcag_reference.values())


@lru_cache(maxsize=1)
def _load_mapping_data() -> dict:
    """Load the WCAG mapping data from JSON file."""
    data_path = Path(__file__).parent.parent / "data" / "pdfua_wcag_mapping.json"

    try:
        with open(data_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        import logging
        logging.getLogger(__name__).warning(f"Failed to load WCAG mapping: {e}")
        return {"mappings": {}, "iso_32000_mappings": {}, "matterhorn_mappings": {}, "wcag_reference": {}}


# Singleton instance for convenience
_mapper_instance: WCAGMapper | None = None


def get_wcag_mapper() -> WCAGMapper:
    """Get the singleton WCAGMapper instance."""
    global _mapper_instance
    if _mapper_instance is None:
        _mapper_instance = WCAGMapper()
    return _mapper_instance


def map_violations_to_wcag(
    violations: list["VeraPDFViolation"],
) -> list[ViolationWithWCAG]:
    """
    Convenience function to map violations to WCAG criteria.

    Args:
        violations: List of VeraPDFViolation instances

    Returns:
        List of ViolationWithWCAG with mapping information
    """
    return get_wcag_mapper().map_violations(violations)


def get_wcag_summary(
    violations: list["VeraPDFViolation"],
) -> dict[str, list["VeraPDFViolation"]]:
    """
    Convenience function to group violations by WCAG criterion.

    Args:
        violations: List of VeraPDFViolation instances

    Returns:
        Dict mapping WCAG criterion IDs to lists of violations
    """
    return get_wcag_mapper().get_wcag_summary(violations)
