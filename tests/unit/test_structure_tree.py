"""
Unit tests for Structure Tree Panel enhancements.

Tests for interactive structure tree features including:
- Tag-specific CSS classes
- Heading previews
- Figure tooltips with data attributes
- Expand/collapse controls
- Resizable panel
- Info panel with legend
"""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestStructureNodeFigureIndex:
    """Tests for figure_index field in StructureNode."""

    def test_figure_index_default_none(self):
        """Test that figure_index defaults to None."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="Figure", children=[])
        assert node.figure_index is None

    def test_figure_index_can_be_set(self):
        """Test that figure_index can be set to an integer."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="Figure", children=[], figure_index=5)
        assert node.figure_index == 5

    def test_figure_index_with_other_tag_types(self):
        """Test figure_index with non-Figure tag types."""
        from inspekt.services.pdf_structure_extractor import StructureNode

        # figure_index can be set on any node type (though typically only for Figures)
        node = StructureNode(tag_type="P", children=[], figure_index=3)
        assert node.figure_index == 3


class TestBuildTreeHtml:
    """Tests for _build_tree_html function."""

    def test_basic_node_rendering(self):
        """Test basic node HTML rendering."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="P", children=[], text_content="Hello world")
        html = _build_tree_html(node)

        assert '<span class="tag tag-P"' in html
        assert ">P</span>" in html
        assert "Hello world" in html

    def test_heading_tag_class(self):
        """Test that heading tags get proper CSS classes."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        for level in range(1, 7):
            tag = f"H{level}"
            node = StructureNode(tag_type=tag, children=[], text_content="Section Title")
            html = _build_tree_html(node)

            assert f'class="tag tag-{tag}"' in html
            assert "heading-preview" in html  # Headings should have bold preview

    def test_heading_preview_truncation(self):
        """Test that heading previews are truncated at 30 characters."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        long_text = "A" * 50  # 50 character text
        node = StructureNode(tag_type="H1", children=[], text_content=long_text)
        html = _build_tree_html(node)

        # Should be truncated to 30 chars + "…"
        assert "A" * 30 + "…" in html
        assert "A" * 50 not in html

    def test_non_heading_text_preview(self):
        """Test that non-heading text preview uses tag-preview class."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="P", children=[], text_content="Paragraph text")
        html = _build_tree_html(node)

        assert "tag-preview" in html
        assert '"Paragraph text"' in html

    def test_figure_with_thumbnail_data_attribute(self):
        """Test that Figure tags with figure_index get data-thumbnail attribute."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="Figure", children=[], figure_index=0)
        thumbnails = {0: "base64encodeddata"}
        html = _build_tree_html(node, figure_thumbnails=thumbnails)

        assert 'data-thumbnail="base64encodeddata"' in html

    def test_figure_without_thumbnail(self):
        """Test that Figure tags without thumbnails don't get data-thumbnail."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="Figure", children=[], figure_index=0)
        html = _build_tree_html(node, figure_thumbnails={})

        assert "data-thumbnail" not in html

    def test_alt_text_rendering(self):
        """Test that alt text is rendered correctly."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="Figure", children=[], alt_text="Image description")
        html = _build_tree_html(node)

        assert "tag-alt" in html
        assert "[alt: Image description]" in html

    def test_alt_text_truncation(self):
        """Test that alt text is truncated at 30 characters."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        long_alt = "B" * 50
        node = StructureNode(tag_type="Figure", children=[], alt_text=long_alt)
        html = _build_tree_html(node)

        assert "B" * 30 + "…" in html
        assert "B" * 50 not in html

    def test_has_issues_class(self):
        """Test that nodes with issues get has-issues class."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        node = StructureNode(tag_type="Figure", children=[], issues=["Missing alt text"])
        html = _build_tree_html(node)

        assert "has-issues" in html
        assert "tag-warning" in html

    def test_nested_children(self):
        """Test rendering of nested children."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        child = StructureNode(tag_type="P", children=[], text_content="Child paragraph")
        parent = StructureNode(tag_type="Sect", children=[child])
        html = _build_tree_html(parent)

        assert "tag-Sect" in html
        assert "tag-P" in html
        assert "Child paragraph" in html
        assert "<details" in html  # Parent should use details/summary

    def test_depth_limit(self):
        """Test that recursion is limited to prevent infinite recursion."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        # Create deeply nested structure (15 levels + 1 deepest)
        node = StructureNode(tag_type="Deep", children=[], text_content="Deepest")
        for _ in range(15):  # 15 levels deep
            node = StructureNode(tag_type="Wrapper", children=[node])

        html = _build_tree_html(node)
        # Depth limit is > 10, so recursion stops after depth 10
        # This means 11 wrappers appear (depths 0-10), and "Deep" does not appear
        assert "tag-Deep" not in html  # The deepest node should not appear

    def test_children_limit(self):
        """Test that children are limited to 20 with 'more' indicator."""
        from inspekt.services.pdf_report import _build_tree_html
        from inspekt.services.pdf_structure_extractor import StructureNode

        children = [StructureNode(tag_type="P", children=[], text_content=f"Para {i}") for i in range(25)]
        parent = StructureNode(tag_type="Sect", children=children)
        html = _build_tree_html(parent)

        assert "more-items" in html
        assert "... and 5 more" in html


class TestGenerateStructureTreeSection:
    """Tests for _generate_structure_tree_section function."""

    @patch("inspekt.services.pdf_structure_extractor.PDFStructureExtractor")
    def test_section_contains_toolbar(self, mock_extractor_class):
        """Test that generated section contains the toolbar."""
        from inspekt.services.pdf_report import _generate_structure_tree_section
        from inspekt.services.pdf_structure_extractor import StructureNode

        # Setup mock
        mock_result = MagicMock()
        mock_result.has_structure = True
        mock_result.was_truncated = False
        mock_result.root = StructureNode(tag_type="Document", children=[])
        mock_result.statistics.total_nodes = 10
        mock_result.statistics.heading_count = 2
        mock_result.statistics.figure_count = 1
        mock_result.statistics.table_count = 0
        mock_result.statistics.link_count = 0
        mock_result.validation.issues = []

        mock_instance = MagicMock()
        mock_instance.extract.return_value = mock_result
        mock_instance._max_nodes = 5000
        mock_extractor_class.return_value.__enter__.return_value = mock_instance

        config = {"show-structure": True}
        html = _generate_structure_tree_section("/test.pdf", config)

        assert "structure-tree-toolbar" in html
        assert "toggle-all-btn" in html

    @patch("inspekt.services.pdf_structure_extractor.PDFStructureExtractor")
    def test_section_contains_resize_handle(self, mock_extractor_class):
        """Test that generated section contains the resize handle."""
        from inspekt.services.pdf_report import _generate_structure_tree_section
        from inspekt.services.pdf_structure_extractor import StructureNode

        mock_result = MagicMock()
        mock_result.has_structure = True
        mock_result.was_truncated = False
        mock_result.root = StructureNode(tag_type="Document", children=[])
        mock_result.statistics.total_nodes = 10
        mock_result.statistics.heading_count = 2
        mock_result.statistics.figure_count = 1
        mock_result.statistics.table_count = 0
        mock_result.statistics.link_count = 0
        mock_result.validation.issues = []

        mock_instance = MagicMock()
        mock_instance.extract.return_value = mock_result
        mock_instance._max_nodes = 5000
        mock_extractor_class.return_value.__enter__.return_value = mock_instance

        config = {"show-structure": True}
        html = _generate_structure_tree_section("/test.pdf", config)

        assert "resize-handle" in html

    @patch("inspekt.services.pdf_structure_extractor.PDFStructureExtractor")
    def test_section_contains_info_panel(self, mock_extractor_class):
        """Test that generated section contains the info panel with legend."""
        from inspekt.services.pdf_report import _generate_structure_tree_section
        from inspekt.services.pdf_structure_extractor import StructureNode

        mock_result = MagicMock()
        mock_result.has_structure = True
        mock_result.was_truncated = False
        mock_result.root = StructureNode(tag_type="Document", children=[])
        mock_result.statistics.total_nodes = 10
        mock_result.statistics.heading_count = 2
        mock_result.statistics.figure_count = 1
        mock_result.statistics.table_count = 0
        mock_result.statistics.link_count = 0
        mock_result.validation.issues = []

        mock_instance = MagicMock()
        mock_instance.extract.return_value = mock_result
        mock_instance._max_nodes = 5000
        mock_extractor_class.return_value.__enter__.return_value = mock_instance

        config = {"show-structure": True}
        html = _generate_structure_tree_section("/test.pdf", config)

        assert "structure-tree-info" in html
        assert "color-legend" in html
        assert "legend-swatch" in html
        assert "Headings (H1-H6)" in html

    @patch("inspekt.services.pdf_structure_extractor.PDFStructureExtractor")
    def test_section_contains_keyboard_hint(self, mock_extractor_class):
        """Test that generated section contains keyboard modifier hint."""
        from inspekt.services.pdf_report import _generate_structure_tree_section
        from inspekt.services.pdf_structure_extractor import StructureNode

        mock_result = MagicMock()
        mock_result.has_structure = True
        mock_result.was_truncated = False
        mock_result.root = StructureNode(tag_type="Document", children=[])
        mock_result.statistics.total_nodes = 10
        mock_result.statistics.heading_count = 2
        mock_result.statistics.figure_count = 1
        mock_result.statistics.table_count = 0
        mock_result.statistics.link_count = 0
        mock_result.validation.issues = []

        mock_instance = MagicMock()
        mock_instance.extract.return_value = mock_result
        mock_instance._max_nodes = 5000
        mock_extractor_class.return_value.__enter__.return_value = mock_instance

        config = {"show-structure": True}
        html = _generate_structure_tree_section("/test.pdf", config)

        assert "<kbd>Ctrl</kbd>" in html
        assert "<kbd>Cmd</kbd>" in html

    @patch("inspekt.services.pdf_structure_extractor.PDFStructureExtractor")
    def test_section_contains_tooltip_container(self, mock_extractor_class):
        """Test that generated section contains the tooltip container."""
        from inspekt.services.pdf_report import _generate_structure_tree_section
        from inspekt.services.pdf_structure_extractor import StructureNode

        mock_result = MagicMock()
        mock_result.has_structure = True
        mock_result.was_truncated = False
        mock_result.root = StructureNode(tag_type="Document", children=[])
        mock_result.statistics.total_nodes = 10
        mock_result.statistics.heading_count = 2
        mock_result.statistics.figure_count = 1
        mock_result.statistics.table_count = 0
        mock_result.statistics.link_count = 0
        mock_result.validation.issues = []

        mock_instance = MagicMock()
        mock_instance.extract.return_value = mock_result
        mock_instance._max_nodes = 5000
        mock_extractor_class.return_value.__enter__.return_value = mock_instance

        config = {"show-structure": True}
        html = _generate_structure_tree_section("/test.pdf", config)

        assert 'id="structure-figure-tooltip"' in html
        assert "structure-figure-tooltip" in html

    @patch("inspekt.services.pdf_structure_extractor.PDFStructureExtractor")
    def test_section_contains_filter_checkboxes(self, mock_extractor_class):
        """Test that generated section contains the filter checkboxes."""
        from inspekt.services.pdf_report import _generate_structure_tree_section
        from inspekt.services.pdf_structure_extractor import StructureNode

        mock_result = MagicMock()
        mock_result.has_structure = True
        mock_result.was_truncated = False
        mock_result.root = StructureNode(tag_type="Document", children=[])
        mock_result.statistics.total_nodes = 10
        mock_result.statistics.heading_count = 2
        mock_result.statistics.figure_count = 1
        mock_result.statistics.table_count = 0
        mock_result.statistics.link_count = 0
        mock_result.validation.issues = []

        mock_instance = MagicMock()
        mock_instance.extract.return_value = mock_result
        mock_instance._max_nodes = 5000
        mock_extractor_class.return_value.__enter__.return_value = mock_instance

        config = {"show-structure": True}
        html = _generate_structure_tree_section("/test.pdf", config)

        # Check for "Hide generic tags" checkbox
        assert 'id="hide-generic-tags"' in html
        assert 'for="hide-generic-tags"' in html
        assert "Hide generic tags" in html

        # Check for "Hide all identical siblings" checkbox
        assert 'id="hide-all-identical-siblings"' in html
        assert 'for="hide-all-identical-siblings"' in html
        assert "Hide all identical siblings" in html

        # Check for toolbar-checkbox class
        assert "toolbar-checkbox" in html

        # Check for toolbar separator
        assert "toolbar-separator" in html

    def test_section_disabled_returns_empty(self):
        """Test that section returns empty when show-structure is False."""
        from inspekt.services.pdf_report import _generate_structure_tree_section

        config = {"show-structure": False}
        html = _generate_structure_tree_section("/test.pdf", config)

        assert html == ""


class TestStaticAssetLoading:
    """Tests for CSS and JS loading functions."""

    def test_get_structure_tree_css_loads_file(self):
        """Test that CSS loading function returns content."""
        from inspekt.services.pdf_report import _get_structure_tree_css

        css = _get_structure_tree_css()

        assert len(css) > 0
        assert ".structure-tree-container" in css
        assert ".toggle-all-btn" in css
        assert ".tag-H1" in css

    def test_get_structure_tree_js_loads_file(self):
        """Test that JS loading function returns content."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert len(js) > 0
        assert "class StructureTree" in js
        assert "expandAll" in js
        assert "collapseAll" in js

    def test_css_file_exists(self):
        """Test that the CSS file exists in the expected location."""
        css_path = Path(__file__).parent.parent.parent / "inspekt" / "static" / "css" / "structure-tree.css"
        assert css_path.exists(), f"CSS file should exist at {css_path}"

    def test_js_file_exists(self):
        """Test that the JS file exists in the expected location."""
        js_path = Path(__file__).parent.parent.parent / "inspekt" / "static" / "js" / "structure-tree.js"
        assert js_path.exists(), f"JS file should exist at {js_path}"


class TestCssTagColors:
    """Tests for WCAG-compliant tag colors in CSS."""

    def test_all_heading_colors_defined(self):
        """Test that all heading level colors are defined."""
        from inspekt.services.pdf_report import _get_structure_tree_css

        css = _get_structure_tree_css()

        for level in range(1, 7):
            assert f".tag-H{level}" in css, f"H{level} color should be defined"

    def test_common_tag_colors_defined(self):
        """Test that common tag colors are defined."""
        from inspekt.services.pdf_report import _get_structure_tree_css

        css = _get_structure_tree_css()

        required_tags = [
            "P", "Span", "Figure", "Table", "L", "LI", "Link", "Form",
            "Document", "Part", "Sect"
        ]

        for tag in required_tags:
            assert f".tag-{tag}" in css, f"{tag} color should be defined"

    def test_dark_mode_styles_defined(self):
        """Test that dark mode styles are defined."""
        from inspekt.services.pdf_report import _get_structure_tree_css

        css = _get_structure_tree_css()

        assert "prefers-color-scheme: dark" in css

    def test_toolbar_checkbox_styles_defined(self):
        """Test that toolbar checkbox styles are defined."""
        from inspekt.services.pdf_report import _get_structure_tree_css

        css = _get_structure_tree_css()

        assert ".toolbar-checkbox" in css
        assert "cursor: pointer" in css

    def test_sibling_toggle_styles_defined(self):
        """Test that sibling toggle button styles are defined."""
        from inspekt.services.pdf_report import _get_structure_tree_css

        css = _get_structure_tree_css()

        assert ".sibling-toggle" in css
        assert ".sibling-toggle-item" in css
        assert ".sibling-group" in css

    def test_toolbar_separator_styles_defined(self):
        """Test that toolbar separator styles are defined."""
        from inspekt.services.pdf_report import _get_structure_tree_css

        css = _get_structure_tree_css()

        assert ".toolbar-separator" in css

class TestJavaScriptFeatures:
    """Tests for JavaScript feature implementations."""

    def test_js_contains_expand_collapse(self):
        """Test that JS contains expand/collapse functionality."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "expandAll" in js
        assert "collapseAll" in js
        assert "toggleAll" in js

    def test_js_contains_keyboard_modifiers(self):
        """Test that JS contains keyboard modifier handling."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "ctrlKey" in js
        assert "metaKey" in js
        assert "initKeyboardModifiers" in js

    def test_js_contains_resize_handle(self):
        """Test that JS contains resize handle functionality."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "initResizeHandle" in js
        assert "resize-handle" in js
        assert "localStorage" in js

    def test_js_contains_figure_tooltips(self):
        """Test that JS contains figure tooltip functionality."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "initFigureTooltips" in js
        assert "data-thumbnail" in js
        assert "positionTooltip" in js

    def test_js_contains_accessibility_features(self):
        """Test that JS contains accessibility features."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "aria-expanded" in js
        assert "aria-label" in js
        assert "tabindex" in js

    def test_js_contains_generic_tags_constant(self):
        """Test that JS contains the GENERIC_TAGS constant."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "GENERIC_TAGS" in js
        assert "'Span'" in js
        assert "'Div'" in js
        assert "'NonStruct'" in js
        assert "'Private'" in js

    def test_js_contains_filter_checkbox_handling(self):
        """Test that JS contains filter checkbox initialization and handling."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "initFilterCheckboxes" in js
        assert "hide-generic-tags" in js
        assert "hide-all-identical-siblings" in js
        assert "hideGenericTags" in js
        assert "hideIdenticalSiblings" in js

    def test_js_contains_sibling_grouping_functionality(self):
        """Test that JS contains sibling grouping methods."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "collapseIdenticalSiblings" in js
        assert "processIdenticalSiblings" in js
        assert "createSiblingGroup" in js
        assert "sibling-group" in js
        assert "sibling-toggle" in js
        assert "hidden-sibling" in js

    def test_js_contains_generic_tag_filtering(self):
        """Test that JS contains generic tag filtering method."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "filterGenericTags" in js
        assert "applyFilters" in js

    def test_js_contains_preference_persistence(self):
        """Test that JS contains preference save/load functionality."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "savePreferences" in js
        assert "loadPreferences" in js
        assert "inspekt-structure-tree-prefs" in js

    def test_js_contains_generic_tag_tooltip_update(self):
        """Test that JS contains method to update generic tag count tooltip."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "updateGenericTagTooltip" in js
        assert "countGenericTags" in js

    def test_js_contains_identical_siblings_tooltip_update(self):
        """Test that JS contains method to update identical siblings count tooltip."""
        from inspekt.services.pdf_report import _get_structure_tree_js

        js = _get_structure_tree_js()

        assert "updateIdenticalSiblingsTooltip" in js
        assert "countIdenticalSiblings" in js
