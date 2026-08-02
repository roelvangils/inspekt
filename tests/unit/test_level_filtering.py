"""
Unit tests for WCAG level filtering functionality.

Tests the _sc_matches_level function and WCAG_SC_LEVELS data structure
used to filter accessibility audit results by WCAG conformance level.
"""

import pytest

from inspekt.app.cli.accessibility import (
    WCAG_SC_DESCRIPTIONS,
    WCAG_SC_LEVELS,
    _sc_matches_level,
)


class TestWcagScLevelsData:
    """Tests for the WCAG_SC_LEVELS data structure."""

    def test_all_described_scs_have_levels(self):
        """Every SC in WCAG_SC_DESCRIPTIONS should have a level defined."""
        missing = []
        for sc in WCAG_SC_DESCRIPTIONS:
            if sc not in WCAG_SC_LEVELS:
                missing.append(sc)
        assert not missing, f"SCs missing from WCAG_SC_LEVELS: {missing}"

    def test_level_values_are_valid(self):
        """All level values should be A, AA, or AAA."""
        valid_levels = {"A", "AA", "AAA"}
        for sc, info in WCAG_SC_LEVELS.items():
            assert info["level"] in valid_levels, f"Invalid level for {sc}: {info['level']}"

    def test_version_values_are_valid(self):
        """All version values should be 2.0, 2.1, or 2.2."""
        valid_versions = {"2.0", "2.1", "2.2"}
        for sc, info in WCAG_SC_LEVELS.items():
            assert info["version"] in valid_versions, f"Invalid version for {sc}: {info['version']}"

    def test_wcag_20_criteria_count(self):
        """WCAG 2.0 should have the expected number of criteria."""
        wcag20 = [sc for sc, info in WCAG_SC_LEVELS.items() if info["version"] == "2.0"]
        # WCAG 2.0 has 61 success criteria (25 A, 13 AA, 23 AAA)
        assert len(wcag20) >= 60, f"Expected ~61 WCAG 2.0 criteria, got {len(wcag20)}"

    def test_wcag_21_new_criteria(self):
        """WCAG 2.1 added 17 new success criteria."""
        wcag21_new = [sc for sc, info in WCAG_SC_LEVELS.items() if info["version"] == "2.1"]
        assert len(wcag21_new) >= 10, f"Expected ~17 new WCAG 2.1 criteria, got {len(wcag21_new)}"

    def test_wcag_22_new_criteria(self):
        """WCAG 2.2 added 9 new success criteria."""
        wcag22_new = [sc for sc, info in WCAG_SC_LEVELS.items() if info["version"] == "2.2"]
        assert len(wcag22_new) >= 6, f"Expected ~9 new WCAG 2.2 criteria, got {len(wcag22_new)}"


class TestScMatchesLevelBasic:
    """Basic tests for _sc_matches_level function."""

    def test_unknown_sc_returns_true(self):
        """Unknown SCs should be included by default."""
        assert _sc_matches_level("99.99.99", "21aa") is True

    def test_unknown_level_format_returns_true(self):
        """Unknown level formats should include by default."""
        assert _sc_matches_level("1.1.1", "xyz") is True


class TestScMatchesLevelA:
    """Tests for Level A filtering."""

    # WCAG 2.0 Level A criteria
    @pytest.mark.parametrize("sc", [
        "1.1.1",  # Non-text Content
        "1.2.1",  # Audio-only and Video-only
        "1.3.1",  # Info and Relationships
        "2.1.1",  # Keyboard
        "2.4.1",  # Bypass Blocks
        "3.1.1",  # Language of Page
        "4.1.2",  # Name, Role, Value
    ])
    def test_level_a_criteria_match_2a(self, sc):
        """Level A criteria should match 2a."""
        assert _sc_matches_level(sc, "2a") is True

    @pytest.mark.parametrize("sc", [
        "1.1.1", "1.3.1", "2.1.1", "4.1.2",
    ])
    def test_level_a_criteria_match_21a(self, sc):
        """Level A criteria should match 21a."""
        assert _sc_matches_level(sc, "21a") is True

    @pytest.mark.parametrize("sc", [
        "1.4.3",  # Contrast (Minimum) - Level AA
        "2.4.5",  # Multiple Ways - Level AA
        "2.4.7",  # Focus Visible - Level AA
    ])
    def test_level_aa_criteria_excluded_from_2a(self, sc):
        """Level AA criteria should NOT match 2a."""
        assert _sc_matches_level(sc, "2a") is False

    @pytest.mark.parametrize("sc", [
        "1.4.6",  # Contrast (Enhanced) - Level AAA
        "2.4.9",  # Link Purpose (Link Only) - Level AAA
    ])
    def test_level_aaa_criteria_excluded_from_2a(self, sc):
        """Level AAA criteria should NOT match 2a."""
        assert _sc_matches_level(sc, "2a") is False


class TestScMatchesLevelAA:
    """Tests for Level AA filtering."""

    @pytest.mark.parametrize("sc", [
        "1.1.1",  # Level A
        "1.4.3",  # Level AA
        "2.4.7",  # Level AA
    ])
    def test_level_a_and_aa_criteria_match_2aa(self, sc):
        """Level A and AA criteria should match 2aa."""
        assert _sc_matches_level(sc, "2aa") is True

    @pytest.mark.parametrize("sc", [
        "1.4.6",  # Contrast (Enhanced) - Level AAA
        "2.4.9",  # Link Purpose (Link Only) - Level AAA
    ])
    def test_level_aaa_criteria_excluded_from_2aa(self, sc):
        """Level AAA criteria should NOT match 2aa."""
        assert _sc_matches_level(sc, "2aa") is False


class TestScMatchesLevelAAA:
    """Tests for Level AAA filtering."""

    @pytest.mark.parametrize("sc", [
        "1.1.1",  # Level A
        "1.4.3",  # Level AA
        "1.4.6",  # Level AAA
    ])
    def test_all_levels_match_2aaa(self, sc):
        """All levels should match 2aaa."""
        assert _sc_matches_level(sc, "2aaa") is True


class TestScMatchesLevelVersionFiltering:
    """Tests for WCAG version filtering."""

    def test_wcag_21_criteria_excluded_from_20(self):
        """WCAG 2.1 new criteria should NOT match WCAG 2.0 levels."""
        # 2.5.3 is new in WCAG 2.1 (Level A)
        assert _sc_matches_level("2.5.3", "2a") is False
        assert _sc_matches_level("2.5.3", "2aa") is False

    def test_wcag_21_criteria_included_in_21(self):
        """WCAG 2.1 new criteria should match WCAG 2.1 levels."""
        # 2.5.3 is new in WCAG 2.1 (Level A)
        assert _sc_matches_level("2.5.3", "21a") is True
        assert _sc_matches_level("2.5.3", "21aa") is True

    def test_wcag_22_criteria_excluded_from_21(self):
        """WCAG 2.2 new criteria should NOT match WCAG 2.1 levels."""
        # 2.4.11 is new in WCAG 2.2 (Level AA)
        assert _sc_matches_level("2.4.11", "21a") is False
        assert _sc_matches_level("2.4.11", "21aa") is False

    def test_wcag_22_criteria_included_in_22(self):
        """WCAG 2.2 new criteria should match WCAG 2.2 levels."""
        # 2.4.11 is new in WCAG 2.2 (Level AA)
        assert _sc_matches_level("2.4.11", "22aa") is True

    def test_wcag_20_criteria_included_in_21(self):
        """WCAG 2.0 criteria should be included in WCAG 2.1 checks."""
        assert _sc_matches_level("1.1.1", "21a") is True
        assert _sc_matches_level("1.4.3", "21aa") is True

    def test_wcag_20_21_criteria_included_in_22(self):
        """WCAG 2.0 and 2.1 criteria should be included in WCAG 2.2 checks."""
        assert _sc_matches_level("1.1.1", "22aa") is True    # 2.0 Level A
        assert _sc_matches_level("1.4.3", "22aa") is True    # 2.0 Level AA
        assert _sc_matches_level("2.5.3", "22aa") is True    # 2.1 Level A
        assert _sc_matches_level("1.4.12", "22aa") is True   # 2.1 Level AA


class TestScMatchesLevelCaseSensitivity:
    """Tests for case insensitivity of level parameter."""

    @pytest.mark.parametrize("level", ["21aa", "21AA", "21Aa", "21aA"])
    def test_level_case_insensitive(self, level):
        """Level parameter should be case insensitive."""
        assert _sc_matches_level("1.1.1", level) is True
        assert _sc_matches_level("1.4.3", level) is True


class TestScMatchesLevelEdgeCases:
    """Edge case tests for _sc_matches_level."""

    def test_empty_sc(self):
        """Empty SC should return True (include by default)."""
        assert _sc_matches_level("", "21aa") is True

    def test_empty_level(self):
        """Empty level should return True (include by default)."""
        assert _sc_matches_level("1.1.1", "") is True

    def test_specific_wcag_22_criteria(self):
        """Test specific WCAG 2.2 new criteria."""
        # Focus Not Obscured (Minimum) - 2.4.11 - Level AA - WCAG 2.2
        assert _sc_matches_level("2.4.11", "22aa") is True
        assert _sc_matches_level("2.4.11", "21aa") is False

        # Target Size (Minimum) - 2.5.8 - Level AA - WCAG 2.2
        assert _sc_matches_level("2.5.8", "22aa") is True
        assert _sc_matches_level("2.5.8", "21aa") is False

        # Accessible Authentication - 3.3.8 - Level AA - WCAG 2.2
        assert _sc_matches_level("3.3.8", "22aa") is True
        assert _sc_matches_level("3.3.8", "21aa") is False


class TestLevelHierarchy:
    """Tests to verify level hierarchy is correct."""

    def test_a_is_subset_of_aa(self):
        """All Level A criteria that match 2a should also match 2aa."""
        for sc, info in WCAG_SC_LEVELS.items():
            if info["version"] == "2.0" and info["level"] == "A":
                matches_a = _sc_matches_level(sc, "2a")
                matches_aa = _sc_matches_level(sc, "2aa")
                if matches_a:
                    assert matches_aa, f"{sc} matches 2a but not 2aa"

    def test_aa_is_subset_of_aaa(self):
        """All criteria that match 2aa should also match 2aaa."""
        for sc, info in WCAG_SC_LEVELS.items():
            if info["version"] == "2.0":
                matches_aa = _sc_matches_level(sc, "2aa")
                matches_aaa = _sc_matches_level(sc, "2aaa")
                if matches_aa:
                    assert matches_aaa, f"{sc} matches 2aa but not 2aaa"

    def test_21_includes_20(self):
        """WCAG 2.1 should include all WCAG 2.0 criteria."""
        for sc, info in WCAG_SC_LEVELS.items():
            if info["version"] == "2.0":
                matches_20 = _sc_matches_level(sc, "2aa")
                matches_21 = _sc_matches_level(sc, "21aa")
                if matches_20:
                    assert matches_21, f"{sc} matches 2aa but not 21aa"

    def test_22_includes_21(self):
        """WCAG 2.2 should include all WCAG 2.1 criteria."""
        for sc, info in WCAG_SC_LEVELS.items():
            if info["version"] in ("2.0", "2.1"):
                matches_21 = _sc_matches_level(sc, "21aa")
                matches_22 = _sc_matches_level(sc, "22aa")
                if matches_21:
                    assert matches_22, f"{sc} matches 21aa but not 22aa"
