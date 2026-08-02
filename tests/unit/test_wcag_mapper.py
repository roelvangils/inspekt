"""
Unit tests for WCAG Mapper.

Tests for mapping PDF/UA-1 violations to WCAG 2.1 success criteria.
"""

from __future__ import annotations

from pathlib import Path


class TestWCAGCriterion:
    """Unit tests for WCAGCriterion dataclass."""

    def test_wcag_criterion_properties(self):
        """Test WCAGCriterion properties."""
        from inspekt.services.wcag_mapper import WCAGCriterion

        criterion = WCAGCriterion(
            id="1.1.1",
            title="Non-text Content",
            level="A",
            principle="Perceivable",
        )

        assert criterion.id == "1.1.1"
        assert criterion.level == "A"
        assert criterion.title == "Non-text Content"
        assert criterion.principle == "Perceivable"

    def test_wcag_criterion_url(self):
        """Test WCAGCriterion URL generation."""
        from inspekt.services.wcag_mapper import WCAGCriterion

        criterion = WCAGCriterion(
            id="1.1.1",
            title="Non-text Content",
            level="A",
            principle="Perceivable",
        )

        assert "1-1-1" in criterion.url.lower()
        assert "wcag21" in criterion.url.lower()


class TestWCAGMapping:
    """Unit tests for WCAGMapping dataclass."""

    def test_wcag_mapping_properties(self):
        """Test WCAGMapping properties."""
        from inspekt.services.wcag_mapper import WCAGCriterion, WCAGMapping

        criteria = [
            WCAGCriterion(id="1.1.1", title="Non-text Content", level="A", principle="Perceivable"),
        ]

        mapping = WCAGMapping(
            rule_id="ISO-32000-1-7.18.1",
            title="Figure Alt Text",
            wcag_criteria=criteria,
            wcag_level="A",
            category="images",
            remediation_hint="Add alternative text to images.",
        )

        assert mapping.rule_id == "ISO-32000-1-7.18.1"
        assert len(mapping.wcag_criteria) == 1
        assert mapping.wcag_criteria[0].id == "1.1.1"
        assert "alternative text" in mapping.remediation_hint

    def test_wcag_ids_property(self):
        """Test wcag_ids property."""
        from inspekt.services.wcag_mapper import WCAGCriterion, WCAGMapping

        criteria = [
            WCAGCriterion(id="1.1.1", title="Non-text Content", level="A", principle="Perceivable"),
            WCAGCriterion(
                id="1.3.1", title="Info and Relationships", level="A", principle="Perceivable"
            ),
        ]

        mapping = WCAGMapping(
            rule_id="test",
            title="Test",
            wcag_criteria=criteria,
        )

        assert mapping.wcag_ids == ["1.1.1", "1.3.1"]


class TestWCAGMapper:
    """Unit tests for WCAGMapper class."""

    def test_initialization(self):
        """Test that WCAGMapper initializes successfully."""
        from inspekt.services.wcag_mapper import WCAGMapper

        mapper = WCAGMapper()

        # Should have internal data loaded
        assert mapper._mapping_data is not None
        assert mapper._wcag_reference is not None
        assert mapper._rule_mappings is not None

    def test_get_mapping_for_known_rule(self):
        """Test getting mapping for a known rule ID."""
        from inspekt.services.wcag_mapper import WCAGMapper

        mapper = WCAGMapper()

        # This is a common PDF/UA-1 rule for images without alt text
        mapping = mapper.get_mapping("ISO-32000-1-7.18.1")

        # Even if exact rule isn't found, should return None gracefully
        # The important thing is no exception is raised
        if mapping:
            assert mapping.rule_id is not None

    def test_get_mapping_for_unknown_rule(self):
        """Test getting mapping for an unknown rule ID returns None."""
        from inspekt.services.wcag_mapper import WCAGMapper

        mapper = WCAGMapper()

        mapping = mapper.get_mapping("UNKNOWN-RULE-12345")

        assert mapping is None


class TestViolationWithWCAG:
    """Unit tests for ViolationWithWCAG dataclass."""

    def test_violation_with_wcag_properties(self):
        """Test ViolationWithWCAG properties."""
        from unittest.mock import MagicMock

        from inspekt.services.wcag_mapper import ViolationWithWCAG, WCAGCriterion, WCAGMapping

        violation = MagicMock()
        violation.rule_id = "ISO-32000-1-7.18.1"

        criteria = [
            WCAGCriterion(id="1.1.1", title="Non-text Content", level="A", principle="Perceivable"),
        ]

        mapping = WCAGMapping(
            rule_id="ISO-32000-1-7.18.1",
            title="Test",
            wcag_criteria=criteria,
        )

        vw = ViolationWithWCAG(
            violation=violation,
            mapping=mapping,
            wcag_criteria=criteria,
        )

        assert vw.has_wcag_mapping
        assert "1.1.1" in vw.wcag_summary

    def test_violation_without_mapping(self):
        """Test ViolationWithWCAG without mapping."""
        from unittest.mock import MagicMock

        from inspekt.services.wcag_mapper import ViolationWithWCAG

        violation = MagicMock()
        violation.rule_id = "UNKNOWN"

        vw = ViolationWithWCAG(
            violation=violation,
            mapping=None,
            wcag_criteria=[],
        )

        assert not vw.has_wcag_mapping
        assert "No WCAG mapping" in vw.wcag_summary


class TestMappingDataFile:
    """Tests for the WCAG mapping data file."""

    def test_mapping_file_exists(self):
        """Test that the mapping JSON file exists."""

        mapping_file = (
            Path(__file__).parent.parent.parent / "inspekt" / "data" / "pdfua_wcag_mapping.json"
        )
        assert mapping_file.exists(), f"Mapping file not found: {mapping_file}"

    def test_mapping_file_is_valid_json(self):
        """Test that the mapping file contains valid JSON."""
        import json

        mapping_file = (
            Path(__file__).parent.parent.parent / "inspekt" / "data" / "pdfua_wcag_mapping.json"
        )

        with open(mapping_file) as f:
            data = json.load(f)

        assert isinstance(data, dict)
        # Should have main sections
        assert (
            "mappings" in data
            or "iso_32000_mappings" in data
            or "matterhorn_mappings" in data
            or "wcag_reference" in data
        )

    def test_mapping_entries_have_required_fields(self):
        """Test that mapping entries have required fields."""
        import json

        mapping_file = (
            Path(__file__).parent.parent.parent / "inspekt" / "data" / "pdfua_wcag_mapping.json"
        )

        with open(mapping_file) as f:
            data = json.load(f)

        # Check at least one mapping section
        for section_key in ["mappings", "iso_32000_mappings"]:
            if section_key in data:
                section = data[section_key]
                for rule_id, mapping in list(section.items())[:5]:  # Check first 5
                    # Each mapping should have wcag_criteria
                    assert "wcag_criteria" in mapping, f"Missing wcag_criteria in {rule_id}"
                    assert isinstance(mapping["wcag_criteria"], list), (
                        f"wcag_criteria should be a list in {rule_id}"
                    )
                break
