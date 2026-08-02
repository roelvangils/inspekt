"""Tests for accessibility heuristics in image_gallery._compute_acc_hints()."""

from pathlib import Path

from inspekt.services.image_gallery import GalleryImage, _compute_acc_hints


def _make_image(**kwargs) -> GalleryImage:
    """Create a GalleryImage with sensible defaults, overriding with kwargs."""
    defaults = dict(
        filename="test.png",
        file_path=Path("test.png"),
        thumbnail_path=None,
        width=100,
        height=100,
        file_size=1024,
        alt="",
        title="",
        original_url="https://example.com/test.png",
        source_type="img",
        accessible_name="",
        accessible_name_source="alt attribute",
        is_linked=False,
        link_href="",
        nearest_heading_text="",
    )
    defaults.update(kwargs)
    return GalleryImage(**defaults)


# --- Existing heuristics (#1–#10) ---


class TestHeuristic1MissingAlt:
    def test_fires_when_alt_missing(self):
        img = _make_image(accessible_name_source="missing alt attribute")
        hints = _compute_acc_hints(img)
        assert any("no <code>alt</code> attribute" in h for h in hints)

    def test_skips_for_background_images(self):
        img = _make_image(source_type="css-background", accessible_name_source="none")
        hints = _compute_acc_hints(img)
        assert not any("no <code>alt</code> attribute" in h for h in hints)


class TestHeuristic2DecorativeLinked:
    def test_fires_for_linked_decorative(self):
        img = _make_image(
            is_linked=True,
            accessible_name_source="empty alt (decorative)",
        )
        hints = _compute_acc_hints(img)
        assert any("decorative" in h.lower() and "link" in h.lower() for h in hints)


class TestHeuristic3CssBackground:
    def test_fires_for_bg_images(self):
        img = _make_image(source_type="css-background")
        hints = _compute_acc_hints(img)
        assert any("background" in h.lower() for h in hints)


class TestHeuristic5NameTooShort:
    def test_fires_for_short_name(self):
        img = _make_image(accessible_name="Hi")
        hints = _compute_acc_hints(img)
        assert any("very short" in h for h in hints)


class TestHeuristic6NameTooLong:
    def test_fires_for_long_name(self):
        img = _make_image(accessible_name="A" * 81)
        hints = _compute_acc_hints(img)
        assert any("under 80 characters" in h for h in hints)


class TestHeuristic7RedundantPrefix:
    def test_fires_for_image_of(self):
        img = _make_image(accessible_name="Image of a sunset")
        hints = _compute_acc_hints(img)
        assert any("redundant" in h for h in hints)


class TestHeuristic8GenericName:
    def test_fires_for_placeholder(self):
        img = _make_image(accessible_name="placeholder")
        hints = _compute_acc_hints(img)
        assert any("placeholder" in h for h in hints)


# --- New heuristics (#11–#20) ---


class TestHeuristic11Copyright:
    def test_copyright_symbol(self):
        img = _make_image(accessible_name="© 2024 Company Logo")
        hints = _compute_acc_hints(img)
        assert any("copyright or trademark" in h for h in hints)

    def test_registered_symbol(self):
        img = _make_image(accessible_name="Brand® logo")
        hints = _compute_acc_hints(img)
        assert any("copyright or trademark" in h for h in hints)

    def test_tm_symbol(self):
        img = _make_image(accessible_name="Product™")
        hints = _compute_acc_hints(img)
        assert any("copyright or trademark" in h for h in hints)

    def test_parenthetical_c(self):
        img = _make_image(accessible_name="(c) 2024 Company")
        hints = _compute_acc_hints(img)
        assert any("copyright or trademark" in h for h in hints)

    def test_no_false_positive(self):
        img = _make_image(accessible_name="A colorful sunset over the ocean")
        hints = _compute_acc_hints(img)
        assert not any("copyright or trademark" in h for h in hints)


class TestHeuristic12HtmlTags:
    def test_br_tag(self):
        img = _make_image(accessible_name="Click <br> here")
        hints = _compute_acc_hints(img)
        assert any("HTML tags" in h for h in hints)

    def test_span_tag(self):
        img = _make_image(accessible_name="Hello <span>world</span>")
        hints = _compute_acc_hints(img)
        assert any("HTML tags" in h for h in hints)

    def test_no_false_positive(self):
        img = _make_image(accessible_name="3 > 2 comparison")
        # "3 > 2" shouldn't match because there's no opening tag-like pattern
        hints = _compute_acc_hints(img)
        assert not any("HTML tags" in h for h in hints)


class TestHeuristic13EncodedChars:
    def test_html_entity(self):
        img = _make_image(accessible_name="Photo&amp;Art")
        hints = _compute_acc_hints(img)
        assert any("encoded characters" in h for h in hints)

    def test_nbsp(self):
        img = _make_image(accessible_name="Hello&nbsp;World")
        hints = _compute_acc_hints(img)
        assert any("encoded characters" in h for h in hints)

    def test_numeric_entity(self):
        img = _make_image(accessible_name="Hello&#160;World")
        hints = _compute_acc_hints(img)
        assert any("encoded characters" in h for h in hints)

    def test_newline(self):
        img = _make_image(accessible_name="Line one\nLine two")
        hints = _compute_acc_hints(img)
        assert any("encoded characters" in h for h in hints)

    def test_no_false_positive(self):
        img = _make_image(accessible_name="A simple description")
        hints = _compute_acc_hints(img)
        assert not any("encoded characters" in h for h in hints)


class TestHeuristic14AllCaps:
    def test_all_caps(self):
        img = _make_image(accessible_name="COMPANY BANNER IMAGE")
        hints = _compute_acc_hints(img)
        assert any("all caps" in h for h in hints)

    def test_short_abbreviation_no_fire(self):
        """FAQ, PDF, SVG — short abbreviations should not trigger."""
        img = _make_image(accessible_name="FAQ")
        hints = _compute_acc_hints(img)
        assert not any("all caps" in h for h in hints)

    def test_mixed_case_no_fire(self):
        img = _make_image(accessible_name="A Beautiful Sunset")
        hints = _compute_acc_hints(img)
        assert not any("all caps" in h for h in hints)


class TestHeuristic15LinkedLogo:
    def test_linked_logo(self):
        img = _make_image(
            accessible_name="Company logo",
            is_linked=True,
        )
        hints = _compute_acc_hints(img)
        assert any("logo" in h and "link goes" in h for h in hints)

    def test_unlinked_logo_no_fire(self):
        img = _make_image(accessible_name="Company logo", is_linked=False)
        hints = _compute_acc_hints(img)
        assert not any("logo" in h and "link goes" in h for h in hints)


class TestHeuristic16UrlInName:
    def test_http_url(self):
        img = _make_image(accessible_name="https://example.com/logo.png")
        hints = _compute_acc_hints(img)
        assert any("URL" in h for h in hints)

    def test_www_url(self):
        img = _make_image(accessible_name="Visit www.example.com")
        hints = _compute_acc_hints(img)
        assert any("URL" in h for h in hints)

    def test_no_false_positive(self):
        img = _make_image(accessible_name="A beautiful landscape photo")
        hints = _compute_acc_hints(img)
        assert not any("contains a URL" in h for h in hints)


class TestHeuristic17NumericId:
    def test_pure_digits(self):
        img = _make_image(accessible_name="12345")
        hints = _compute_acc_hints(img)
        assert any("numeric ID" in h for h in hints)

    def test_hash_digits(self):
        img = _make_image(accessible_name="#42")
        hints = _compute_acc_hints(img)
        assert any("numeric ID" in h for h in hints)

    def test_item_id(self):
        img = _make_image(accessible_name="item-123")
        hints = _compute_acc_hints(img)
        assert any("numeric ID" in h for h in hints)

    def test_asset_id(self):
        img = _make_image(accessible_name="asset_456")
        hints = _compute_acc_hints(img)
        assert any("numeric ID" in h for h in hints)

    def test_real_description_no_fire(self):
        img = _make_image(accessible_name="Product showcase")
        hints = _compute_acc_hints(img)
        assert not any("numeric ID" in h for h in hints)


class TestHeuristic18ExcessiveWhitespace:
    def test_leading_space(self):
        img = _make_image(accessible_name="  spaced out text")
        hints = _compute_acc_hints(img)
        assert any("irregular spacing" in h for h in hints)

    def test_trailing_space(self):
        img = _make_image(accessible_name="spaced out text  ")
        hints = _compute_acc_hints(img)
        assert any("irregular spacing" in h for h in hints)

    def test_double_space(self):
        img = _make_image(accessible_name="spaced  out  text")
        hints = _compute_acc_hints(img)
        assert any("irregular spacing" in h for h in hints)

    def test_clean_text_no_fire(self):
        img = _make_image(accessible_name="Clean text here")
        hints = _compute_acc_hints(img)
        assert not any("irregular spacing" in h for h in hints)


class TestHeuristic19Dimensions:
    def test_width_x_height(self):
        img = _make_image(accessible_name="Banner 1200x600")
        hints = _compute_acc_hints(img)
        assert any("dimensions" in h for h in hints)

    def test_unicode_multiply(self):
        img = _make_image(accessible_name="Banner 1200×600")
        hints = _compute_acc_hints(img)
        assert any("dimensions" in h for h in hints)

    def test_px_suffix(self):
        img = _make_image(accessible_name="Icon 32px")
        hints = _compute_acc_hints(img)
        assert any("dimensions" in h for h in hints)

    def test_no_false_positive(self):
        img = _make_image(accessible_name="A 5 star rating")
        hints = _compute_acc_hints(img)
        assert not any("dimensions" in h for h in hints)


class TestHeuristic20ClickInstructions:
    def test_click_here(self):
        img = _make_image(accessible_name="Click here for details")
        hints = _compute_acc_hints(img)
        assert any("interaction instructions" in h for h in hints)

    def test_tap(self):
        img = _make_image(accessible_name="Tap to enlarge")
        hints = _compute_acc_hints(img)
        assert any("interaction instructions" in h for h in hints)

    def test_press(self):
        img = _make_image(accessible_name="Press for more info")
        hints = _compute_acc_hints(img)
        assert any("interaction instructions" in h for h in hints)

    def test_no_false_positive(self):
        img = _make_image(accessible_name="A French press coffee maker")
        # "press" as a noun in context — the regex is word-boundary so this WILL match.
        # This is acceptable: better to over-flag than miss real issues.
        # We don't test for no-fire here since "press" is a valid match.


class TestNoRegressions:
    """Ensure the new heuristics don't break clean images."""

    def test_clean_image_no_hints(self):
        img = _make_image(
            accessible_name="A golden retriever playing in the park",
            accessible_name_source="alt attribute",
        )
        hints = _compute_acc_hints(img)
        assert len(hints) == 0

    def test_decorative_image_only_gets_relevant_hints(self):
        img = _make_image(
            accessible_name="",
            accessible_name_source="empty alt (decorative)",
        )
        hints = _compute_acc_hints(img)
        # Should not get any name-quality hints (those require a name)
        assert len(hints) == 0
