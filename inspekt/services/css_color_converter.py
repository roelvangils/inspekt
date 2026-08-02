"""
CSS color and value annotation utilities.

Features:
- Converts CSS colors to oklch format
- Adds human-readable color names as comments
- Marks browser-computed pixel values with /* Browser-computed */

Uses:
- coloraide for color space conversion
- NTC (Name That Color) database for human-readable names
"""

from __future__ import annotations

import math
import re
from functools import lru_cache

from coloraide import Color

from inspekt.services.ntc_colors import NTC_COLORS


def _extract_color_name(css_value: str) -> str | None:
    """
    Try to extract a human-readable color name from a CSS color value.

    Returns the NTC color name (with alpha info if applicable), or None
    if the value doesn't look like a color.
    """
    value = css_value.strip()

    # Hex colors: #rgb, #rrggbb, #rrggbbaa
    hex_match = re.match(r"^#([0-9a-fA-F]{3,8})$", value)
    if hex_match:
        hex_str = hex_match.group(1)
        # Normalize and strip alpha for name lookup
        if len(hex_str) == 3:
            lookup = "".join(c * 2 for c in hex_str)
        elif len(hex_str) == 4:
            lookup = "".join(c * 2 for c in hex_str[:3])
        elif len(hex_str) == 8:
            lookup = hex_str[:6]
        else:
            lookup = hex_str
        return get_color_name(lookup)

    # RGB/RGBA: rgb(r, g, b) / rgba(r, g, b, a) / rgb(r g b / a)
    rgb_match = re.match(
        r"rgba?\(\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)"
        r"(?:\s*[,/]\s*([\d.]+%?))?\s*\)",
        value,
    )
    if rgb_match:
        r, g, b = int(rgb_match.group(1)), int(rgb_match.group(2)), int(rgb_match.group(3))
        hex_str = f"{r:02x}{g:02x}{b:02x}"
        name = get_color_name(hex_str)
        alpha_raw = rgb_match.group(4)
        if alpha_raw:
            if alpha_raw.endswith("%"):
                alpha_frac = float(alpha_raw[:-1]) / 100
            else:
                alpha_frac = float(alpha_raw)
            if alpha_frac <= 0.0:
                return f"{name}, fully transparent"
            elif alpha_frac < 1.0:
                pct = round(alpha_frac * 100)
                return f"{name}, {pct}% opaque"
        return name

    return None


def add_cross_ref_comments(css_content: str, cross_ref_values: dict[str, str]) -> str:
    """
    Add cross-reference comments showing computed values alongside authored values.

    For each CSS property in cross_ref_values, appends a '(resolves to X)' note
    so the user can see both the authored and resolved value.

    If the line already has a comment, the cross-ref is appended inside it.
    Skips lines where the authored and computed values look identical.

    Args:
        css_content: CSS string (post-optimization)
        cross_ref_values: Dict mapping property name to its original computed value

    Returns:
        CSS with cross-reference comments added
    """
    if not cross_ref_values:
        return css_content

    def add_xref_to_line(line: str) -> str:
        stripped = line.strip()

        # Skip non-property lines
        if ":" not in stripped or stripped.startswith("/*"):
            return line

        # Extract property name
        prop_name = stripped.split(":")[0].strip()
        if prop_name not in cross_ref_values:
            return line

        computed = cross_ref_values[prop_name]

        # Extract the authored value from the line for comparison
        # Parse value between ":" and ";" (ignoring comments)
        after_colon = stripped.split(":", 1)[1]
        value_part = after_colon.split(";")[0].strip()
        # Strip any existing comment from the value part
        if "/*" in value_part:
            value_part = value_part[: value_part.index("/*")].strip()

        # Skip if values look the same (no useful cross-ref)
        if value_part == computed:
            return line

        # Skip cross-ref for CSS global keywords (initial, inherit, etc.)
        # — the heuristic comment already explains the semantics
        if value_part in ("initial", "inherit", "unset", "revert", "revert-layer"):
            return line

        xref = f"resolves to {computed}"

        # If the resolved value is a color, append the color name
        color_name = _extract_color_name(computed)
        if color_name:
            xref = f"{xref} ({color_name})"

        indent = line[: len(line) - len(line.lstrip())]

        if "/*" in stripped and "*/" in stripped:
            # Append to existing comment
            # Extract existing comment text to choose the right connector
            comment_start = stripped.index("/*") + 2
            comment_end = stripped.index("*/")
            existing_text = stripped[comment_start:comment_end].strip()

            # "which" flows naturally after variable references ("Uses --foo which resolves to…")
            # A semicolon works better after descriptive comments ("2.6rem relative to root; resolves to…")
            if existing_text.startswith("Uses "):
                connector = f"which {xref} "
            else:
                connector = f"— {xref} "

            return line.replace("*/", f"{connector}*/", 1)
        elif stripped.endswith(";"):
            # Add new comment
            content = stripped[:-1]
            return f"{indent}{content}; /* {xref} */"

        return line

    lines = css_content.split("\n")
    result_lines = [add_xref_to_line(line) for line in lines]
    return "\n".join(result_lines)


def add_computed_value_comments(css_content: str) -> str:
    """
    Add /* Browser-computed */ comments to pixel values with 2+ decimal places.

    Computed CSS values often have precise decimal values (e.g., 20.25px, 30.38px)
    that indicate they were resolved by the browser rather than authored.
    This helps identify which values came from computation vs. explicit styling.

    Args:
        css_content: CSS string with pixel values

    Returns:
        CSS with /* Browser-computed */ comments added to precise pixel values
    """
    # Pattern matches pixel values with 2+ decimal places
    # Examples: 20.25px, 30.38px, 1.234px
    # Does not match: 16px, 1.5px, 0.5px (single decimal or none)
    pixel_pattern = r"(\d+\.\d{2,})(px)"

    def add_computed_comment(match: re.Match) -> str:
        """Add Browser-computed comment to a precise pixel value."""
        number = match.group(1)
        unit = match.group(2)
        return f"{number}{unit} /* Browser-computed */"

    return re.sub(pixel_pattern, add_computed_comment, css_content)


def add_rounded_property_comments(
    css_content: str,
    rounded_props: set[str],
    comment_text: str = "Browser-computed",
) -> str:
    """
    Add comments to specific CSS properties that were rounded.

    This is called AFTER Lightning CSS optimization to re-add comments
    that were stripped during optimization.

    Only adds comments to properties that:
    1. Are in the rounded_props set
    2. Have pixel values (contain 'px')
    3. Don't already have a comment

    Args:
        css_content: CSS string (post-optimization)
        rounded_props: Set of property names that were rounded
        comment_text: Comment text to add (default: "Browser-computed")

    Returns:
        CSS with /* Browser-computed */ comments added to rounded properties
    """
    if not rounded_props:
        return css_content

    # Build a pattern that matches any of the rounded properties
    # Pattern: property-name: value with px; (not already having a comment)
    # We need to be careful not to match properties that already have comments

    def add_comment_to_line(line: str) -> str:
        """Add comment to a line if it matches a rounded property."""
        stripped = line.strip()

        # Skip if line already has a comment or doesn't have a property
        if "/*" in stripped or ":" not in stripped:
            return line

        # Extract property name
        prop_name = stripped.split(":")[0].strip()

        # Check if this property was rounded and has pixel values
        if prop_name in rounded_props and "px" in stripped:
            # Add comment before the semicolon
            if stripped.endswith(";"):
                # Find the indentation
                indent = line[: len(line) - len(line.lstrip())]
                # Remove trailing semicolon, add comment, add semicolon back
                content = stripped[:-1]
                return f"{indent}{content} /* {comment_text} */;"
        return line

    lines = css_content.split("\n")
    result_lines = [add_comment_to_line(line) for line in lines]
    return "\n".join(result_lines)


# Pre-compute RGB values for NTC colors for faster lookup
@lru_cache(maxsize=1)
def _get_ntc_rgb_lookup() -> list[tuple[tuple[int, int, int], str]]:
    """Build a lookup table of (r, g, b) -> name for NTC colors."""
    result = []
    for hex_color, name in NTC_COLORS:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        result.append(((r, g, b), name))
    return result


@lru_cache(maxsize=256)
def get_color_name(hex_color: str) -> str:
    """
    Get human-readable name for a color using the NTC database.

    Uses Euclidean distance in RGB space to find the nearest named color.
    Results are cached for efficiency (typical CSS has many repeated colors).

    Args:
        hex_color: Hex color string (with or without #)

    Returns:
        Human-readable color name
    """
    # Normalize hex color
    hex_color = hex_color.lstrip("#").upper()

    # Handle short hex (e.g., #fff -> #ffffff)
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)

    # Parse RGB
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except (ValueError, IndexError):
        return "Unknown"

    # Find nearest color by RGB distance
    ntc_lookup = _get_ntc_rgb_lookup()
    min_distance = float("inf")
    nearest_name = "Unknown"

    for (nr, ng, nb), name in ntc_lookup:
        # Euclidean distance in RGB space
        distance = math.sqrt((r - nr) ** 2 + (g - ng) ** 2 + (b - nb) ** 2)
        if distance < min_distance:
            min_distance = distance
            nearest_name = name

            # Exact match
            if distance == 0:
                break

    return nearest_name


def hex_to_oklch(hex_color: str) -> tuple[float, float, float] | None:
    """
    Convert a hex color to oklch values.

    Args:
        hex_color: Hex color string (with or without #)

    Returns:
        Tuple of (lightness, chroma, hue) or None if conversion fails
    """
    try:
        c = Color(hex_color)
        oklch = c.convert("oklch")

        # Get values with sensible precision
        lightness = round(oklch["lightness"], 2)
        chroma = round(oklch["chroma"], 2)
        # Hue can be NaN for achromatic colors (black, white, grays)
        hue = oklch["hue"]
        if hue is None or math.isnan(hue):
            hue = 0
        else:
            hue = round(hue)

        return (lightness, chroma, hue)
    except Exception:
        return None


def rgb_to_oklch(
    r: int, g: int, b: int, a: float = 1.0
) -> tuple[float, float, float, float] | None:
    """
    Convert RGB(A) values to oklch.

    Args:
        r, g, b: RGB values (0-255)
        a: Alpha value (0-1)

    Returns:
        Tuple of (lightness, chroma, hue, alpha) or None if conversion fails
    """
    try:
        c = Color("srgb", [r / 255, g / 255, b / 255], a)
        oklch = c.convert("oklch")

        lightness = round(oklch["lightness"], 2)
        chroma = round(oklch["chroma"], 2)
        hue = oklch["hue"]
        if hue is None or math.isnan(hue):
            hue = 0
        else:
            hue = round(hue)

        return (lightness, chroma, hue, a)
    except Exception:
        return None


def _oklch_hue_name(hue: float) -> str:
    """Map an OKLCH hue angle (0–360) to a human-readable color name."""
    if hue < 38:
        return "red"
    if hue < 75:
        return "orange"
    if hue < 100:
        return "yellow"
    if hue < 135:
        return "green"
    if hue < 180:
        return "teal"
    if hue < 220:
        return "cyan"
    if hue < 265:
        return "blue"
    if hue < 300:
        return "violet"
    if hue < 340:
        return "purple"
    return "pink"


def describe_color(hex_color: str) -> str:
    """
    Return a short perceptual description of a color based on its OKLCH values.

    Uses lightness, chroma, and hue to produce descriptions like
    "Almost black with a hint of blue", "Bright yellow", or "Off-white".

    Args:
        hex_color: Hex color string (with or without #)

    Returns:
        Human-readable color description with first letter capitalised
    """
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)

    # Delegate to cached implementation with normalized 6-char lowercase hex
    return _describe_color_cached(hex_color.lower())


@lru_cache(maxsize=256)
def _describe_color_cached(hex6: str) -> str:
    """Cached implementation of describe_color (expects normalized 6-char lowercase hex)."""
    result = hex_to_oklch(f"#{hex6}")
    if result is None:
        return "Unknown"

    L, C, H = result

    hue_name = _oklch_hue_name(H)

    # --- Achromatic (C < 0.01): pure grays ---
    if C < 0.01:
        if L < 0.07:
            return "Black"
        if L < 0.20:
            return "Almost black"
        if L < 0.35:
            return "Very dark gray"
        if L < 0.50:
            return "Dark gray"
        if L < 0.65:
            return "Gray"
        if L < 0.80:
            return "Light gray"
        if L < 0.92:
            return "Pale gray"
        if L <= 0.97:
            return "Off-white"
        return "White"

    # --- Near-neutral (C <= 0.04): hint of hue ---
    if C <= 0.04:
        if L < 0.07:
            return f"Black with a hint of {hue_name}"
        if L <= 0.20:
            return f"Almost black with a hint of {hue_name}"
        if L < 0.35:
            return f"Very dark gray with a hint of {hue_name}"
        if L < 0.50:
            return f"Dark gray with a hint of {hue_name}"
        if L < 0.65:
            return f"Gray with a hint of {hue_name}"
        if L < 0.80:
            return f"Light gray with a hint of {hue_name}"
        if L < 0.92:
            return f"Pale gray with a touch of {hue_name}"
        if L < 0.97:
            return f"Near-white with a touch of {hue_name}"
        return f"White with a touch of {hue_name}"

    # --- Muted (C < 0.09) ---
    if C < 0.09:
        if L < 0.20:
            return f"Very dark muted {hue_name}"
        if L < 0.35:
            return f"Dark muted {hue_name}"
        if L < 0.50:
            return f"Muted {hue_name}"
        if L < 0.65:
            return f"Muted {hue_name}"
        if L < 0.80:
            return f"Light muted {hue_name}"
        if L < 0.92:
            return f"Pale muted {hue_name}"
        return f"Very pale {hue_name}"

    # --- Moderate to vivid (C >= 0.09) ---
    if C >= 0.22:
        saturation = "Vivid"
    elif C >= 0.15:
        if L < 0.50:
            saturation = "Deep"
        else:
            saturation = "Bright"
    else:
        saturation = None

    if L < 0.20:
        lightness_prefix = "Very dark"
    elif L < 0.35:
        lightness_prefix = "Dark"
    elif L < 0.50 or L < 0.65:
        lightness_prefix = ""
    elif L < 0.80:
        lightness_prefix = "Light"
    elif L < 0.92:
        lightness_prefix = "Pale"
    else:
        lightness_prefix = "Very pale"

    # Combine: saturation overrides lightness prefix when present
    if saturation:
        desc = f"{saturation} {hue_name}"
    elif lightness_prefix:
        desc = f"{lightness_prefix} {hue_name}"
    else:
        desc = hue_name.capitalize()

    return desc


def format_color_comment(hex_color: str) -> str:
    """
    Build a combined color comment with NTC name and perceptual description.

    Always emits the full description.  Use `dedup_color_descriptions()` as a
    post-processing pass to strip repeated descriptions after the CSS has been
    reordered/grouped into its final form.

    Args:
        hex_color: Hex color string (with or without #)

    Returns:
        String like: Color: "Black Pearl" (Almost black with a hint of blue)
    """
    name = get_color_name(hex_color)
    description = describe_color(hex_color)
    # When both names are identical (e.g. "Black" / "Black"), skip the redundant description
    if name.lower() == description.lower():
        return f"Color: {name}"
    return f'Color: "{name}" ({description})'


# Matches color comments WITH a description (first-occurrence candidates):
#   /* Color: "Some Name" (Some description) */
#   /* Color: "Some Name" (Some description, 50% opaque) */
#   /* Color: "Some Name" (Some description), Invisible text */
# Captures an optional alpha suffix (e.g. ", 50% opaque" or ", fully transparent")
# so it can be preserved when stripping the color description for repeated names.
_COLOR_WITH_DESC_RE = re.compile(
    r"(?P<before>/\*\s*)"
    r'(?P<prefix>Color:\s*"(?P<name>[^"]+)")'
    r"\s*\([^)]*?"  # (Description...
    r"(?P<alpha>,\s*(?:\d+%\s*opaque|fully\s*transparent))?"  # optional alpha
    r"\)"  # )
    r"(?P<after>\s*(?:,.*)?\s*\*/)"
)

# Matches ANY color comment (with or without description) to extract the name:
#   /* Color: "Some Name" (Some description) */
#   /* Color: "Some Name" */
#   /* Color: "Some Name", Invisible text */
#   /* Color: Black */  (unquoted, when name == description)
_COLOR_ANY_RE = re.compile(
    r'/\*\s*Color:\s*(?:"(?P<name>[^"]+)"|(?P<bare_name>[^"*,()]+?))\s*[,*(/]'
)


def dedup_color_descriptions(css_content: str) -> str:
    """
    Deduplicate color comments in the final CSS output.

    Processes line-by-line in output order and applies two rules:

    1. **First-occurrence rule** — the parenthesised description is kept only
       for the *first* line that mentions a given NTC color name.  Later lines
       are shortened to ``Color: "Name"``.

    2. **Consecutive-line rule** — when two adjacent property lines refer to
       the exact same color name, the second is replaced with
       ``/* Same color */`` to reduce visual noise.

    Must run **after** all reordering (alphabetisation, column formatting).

    Args:
        css_content: Fully processed CSS string with color comments

    Returns:
        CSS with deduplicated color comments
    """
    seen_names: set[str] = set()
    prev_name: str | None = None
    prev_full_comment: str | None = None
    lines = css_content.split("\n")
    result: list[str] = []

    # Extract the full Color comment text from a line
    _color_comment_re = re.compile(r"/\*\s*(Color:[^*]*?)\s*\*/")

    for line in lines:
        # Extract the color name on this line (if any)
        name_match = _COLOR_ANY_RE.search(line)
        if name_match:
            current_name = name_match.group("name") or name_match.group("bare_name")
            if current_name:
                current_name = current_name.strip()
        else:
            current_name = None

        # Extract the full comment text for precise comparison
        comment_match = _color_comment_re.search(line) if current_name else None
        current_full_comment = comment_match.group(1).strip() if comment_match else None

        if current_name is not None:
            # Rule 2: consecutive same-color → "Same color"
            # Compare the full comment (includes alpha info), not just the name,
            # so "#ff0000" and "#ff000080" are NOT treated as the same color.
            if current_name == prev_name and current_full_comment == prev_full_comment:
                # Replace the entire color comment with /* Same color */
                line = re.sub(
                    r"/\*\s*Color:[^*]*\*/",
                    "/* Same color */",
                    line,
                )
            else:
                # Rule 1: strip description for non-first occurrences
                if current_name in seen_names:

                    def _strip_desc(match: re.Match) -> str:
                        alpha = match.group("alpha") or ""
                        if alpha:
                            # Keep alpha as parenthesized suffix: Color: "Red" (50% opaque)
                            alpha_text = alpha.lstrip(", ")
                            return f"{match.group('before')}{match.group('prefix')} ({alpha_text}){match.group('after')}"
                        return (
                            f"{match.group('before')}{match.group('prefix')}{match.group('after')}"
                        )

                    line = _COLOR_WITH_DESC_RE.sub(_strip_desc, line)

                seen_names.add(current_name)

        # Track previous line's color — strictly line-adjacent only.
        # Any non-color line (blank, comment, brace, other property) resets the run.
        if current_name is not None:
            prev_name = current_name
            prev_full_comment = current_full_comment
        else:
            prev_name = None
            prev_full_comment = None

        result.append(line)

    return "\n".join(result)


def add_color_name_comments(css_content: str) -> str:
    """
    Add human-readable color name comments to CSS colors without converting format.

    Every color gets the full description here.  Call `dedup_color_descriptions()`
    after all reordering to strip repeated descriptions in final output order.

    Handles:
    - Hex colors: #fff, #ffffff, #ffffffff (with alpha)
    - RGB colors: rgb(255, 255, 255), rgba(255, 255, 255, 0.5)

    Args:
        css_content: CSS string with hex/rgb colors

    Returns:
        CSS with color name comments added
    """
    # Patterns for CSS colors — capture optional trailing gradient stop position
    # so the comment is placed AFTER the stop, not between color and stop.
    # e.g. "#ff000080 50%" → "#ff000080 50% /* Red (50% opaque) */"
    _gradient_stop_suffix = (
        r"(\s+\d+(?:\.\d+)?(?:%|px|em|rem|vw|vh)?(?:\s+\d+(?:\.\d+)?(?:%|px|em|rem|vw|vh)?)?)?"
    )
    hex_pattern = r"#([0-9a-fA-F]{3,8})\b" + _gradient_stop_suffix
    rgb_pattern = (
        r"rgba?\(\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)"
        + _gradient_stop_suffix
    )

    def _describe_alpha(alpha_fraction: float) -> str | None:
        """Describe an alpha value as human-readable opacity. Returns None for fully opaque."""
        if alpha_fraction >= 1.0:
            return None
        if alpha_fraction <= 0.0:
            return "fully transparent"
        pct = round(alpha_fraction * 100)
        return f"{pct}% opaque"

    def _hex_alpha_fraction(hex_str: str) -> float:
        """Extract alpha fraction from 4- or 8-digit hex. Returns 1.0 for 3/6-digit."""
        if len(hex_str) == 4:
            alpha_hex = hex_str[3] * 2  # expand "a" → "aa"
            return int(alpha_hex, 16) / 255
        if len(hex_str) == 8:
            return int(hex_str[6:8], 16) / 255
        return 1.0

    def _append_alpha_to_comment(comment: str, alpha_desc: str | None) -> str:
        """Append alpha description inside the parenthesised part of a color comment."""
        if not alpha_desc:
            return comment
        # "Color: "Name" (description)" → "Color: "Name" (description, 50% opaque)"
        # "Color: Name" → "Color: Name (50% opaque)"
        if comment.endswith(")"):
            return f"{comment[:-1]}, {alpha_desc})"
        return f"{comment} ({alpha_desc})"

    def add_name_to_hex(match: re.Match) -> str:
        """Add color name comment to a hex color (with optional gradient stop)."""
        hex_str = match.group(1)
        full_match = match.group(0)

        # Normalize hex for name lookup (strip alpha)
        if len(hex_str) == 3:
            lookup_hex = "".join(c * 2 for c in hex_str)
        elif len(hex_str) == 4:
            lookup_hex = "".join(c * 2 for c in hex_str[:3])
        elif len(hex_str) == 8:
            lookup_hex = hex_str[:6]
        elif len(hex_str) == 6:
            lookup_hex = hex_str
        else:
            return full_match

        comment = format_color_comment(lookup_hex)
        alpha_desc = _describe_alpha(_hex_alpha_fraction(hex_str))
        comment = _append_alpha_to_comment(comment, alpha_desc)
        return f"{full_match} /* {comment} */"

    def add_name_to_rgb(match: re.Match) -> str:
        """Add color name comment to an rgb/rgba color (with optional gradient stop)."""
        full_match = match.group(0)

        try:
            r = int(match.group(1))
            g = int(match.group(2))
            b = int(match.group(3))

            hex_str = f"{r:02x}{g:02x}{b:02x}"
            comment = format_color_comment(hex_str)

            # Parse alpha from rgba()
            alpha_raw = match.group(4)
            if alpha_raw:
                if alpha_raw.endswith("%"):
                    alpha_frac = float(alpha_raw[:-1]) / 100
                else:
                    alpha_frac = float(alpha_raw)
                alpha_desc = _describe_alpha(alpha_frac)
                comment = _append_alpha_to_comment(comment, alpha_desc)

            return f"{full_match} /* {comment} */"
        except (ValueError, IndexError):
            return full_match

    # Apply name comments
    result = re.sub(hex_pattern, add_name_to_hex, css_content)
    result = re.sub(rgb_pattern, add_name_to_rgb, result)

    return result


def add_heuristic_comments(css_content: str) -> str:
    """
    Add heuristic comments to CSS properties based on property-value patterns.

    This function analyzes CSS property-value pairs and adds helpful comments
    like "Flexbox container" for `display: flex` or "8px rounded corners" for
    `border-radius: 8px`.

    Comments are merged with existing comments (e.g., color names) using comma
    separator: `color: #fff; /* White, Invisible text */`

    Args:
        css_content: CSS string (post-optimization, formatted)

    Returns:
        CSS with heuristic comments added to properties

    Example:
        Input:  `display: flex;`
        Output: `display: flex; /* Flexbox container */`

        Input:  `color: #fff; /* White */`
        Output: `color: #fff; /* White, Invisible text */`
    """
    from inspekt.services.css_property_comments import (
        get_property_comment,
        get_selector_comment,
        merge_comments,
    )

    def add_comment_to_line(line: str) -> str:
        """Add heuristic comment to a CSS property or selector line if applicable."""
        stripped = line.strip()

        # Selector-level comments: lines ending with { that don't already have a comment
        if stripped.endswith("{") and "/*" not in stripped:
            selector = stripped.rstrip("{").strip()
            comment = get_selector_comment(selector)
            if comment:
                indent = line[: len(line) - len(line.lstrip())]
                return f"{indent}{selector} {{ /* {comment} */"

        # Skip lines that don't have properties
        if ":" not in stripped or not stripped.endswith(";"):
            return line

        # Skip lines that are just comments
        if stripped.startswith("/*"):
            return line

        # Extract property name and value
        # Handle existing comments: `color: #fff; /* White */`
        existing_comment = None
        content = stripped

        if "/*" in stripped and "*/" in stripped:
            # Extract existing comment
            comment_start = stripped.index("/*")
            comment_end = stripped.index("*/") + 2
            existing_comment = stripped[comment_start + 2 : comment_end - 2].strip()
            # Remove comment from content for parsing
            content = stripped[:comment_start].strip()
            if not content.endswith(";"):
                content = content.rstrip() + ";"

        # Parse property: value;
        if ":" not in content:
            return line

        prop_part, value_part = content.split(":", 1)
        prop_name = prop_part.strip()
        # Remove trailing semicolon and whitespace from value
        value = value_part.strip().rstrip(";").strip()

        # Get heuristic comment
        heuristic = get_property_comment(prop_name, value)
        if not heuristic:
            return line

        # Merge with existing comment
        merged = merge_comments(existing_comment, heuristic)

        # Reconstruct the line
        indent = line[: len(line) - len(line.lstrip())]
        base_prop = f"{prop_name}: {value};"

        if merged:
            return f"{indent}{base_prop} /* {merged} */"
        return line

    lines = css_content.split("\n")
    result_lines = [add_comment_to_line(line) for line in lines]
    return "\n".join(result_lines)


def convert_colors_to_oklch(css_content: str, add_names: bool = True) -> str:
    """
    Convert CSS color values to oklch format with optional color names.

    Every color gets the full description here.  Call `dedup_color_descriptions()`
    after all reordering to strip repeated descriptions in final output order.

    Handles:
    - Hex colors: #fff, #ffffff, #ffffffff (with alpha)
    - RGB colors: rgb(255, 255, 255), rgba(255, 255, 255, 0.5)

    Args:
        css_content: CSS string with hex/rgb colors
        add_names: Whether to add color name comments (default: True)

    Returns:
        CSS with colors converted to oklch format
    """
    # Patterns for CSS colors
    # Hex: #fff, #ffffff, #ffff, #ffffffff
    hex_pattern = r"#([0-9a-fA-F]{3,8})\b"

    # RGB/RGBA: rgb(r, g, b) or rgba(r, g, b, a)
    # Also handles modern syntax: rgb(r g b) and rgb(r g b / a)
    rgb_pattern = r"rgba?\(\s*(\d+)\s*[,\s]\s*(\d+)\s*[,\s]\s*(\d+)(?:\s*[,/]\s*([\d.]+%?))?\s*\)"

    def convert_hex(match: re.Match) -> str:
        """Convert a hex color match to oklch."""
        hex_str = match.group(1)
        full_match = match.group(0)

        # Handle different hex lengths
        if len(hex_str) == 3:
            # #rgb -> #rrggbb
            hex_str = "".join(c * 2 for c in hex_str)
            alpha = 1.0
        elif len(hex_str) == 4:
            # #rgba -> #rrggbbaa
            hex_str = "".join(c * 2 for c in hex_str[:3])
            alpha = int(hex_str[3] * 2, 16) / 255
        elif len(hex_str) == 6:
            alpha = 1.0
        elif len(hex_str) == 8:
            alpha = int(hex_str[6:8], 16) / 255
            hex_str = hex_str[:6]
        else:
            return full_match  # Invalid, return as-is

        result = hex_to_oklch(f"#{hex_str}")
        if result is None:
            return full_match

        lightness, chroma, hue = result

        # Format oklch value
        if alpha < 1.0:
            oklch_str = f"oklch({lightness} {chroma} {hue} / {round(alpha, 2)})"
        else:
            oklch_str = f"oklch({lightness} {chroma} {hue})"

        # Add color name as comment
        if add_names:
            comment = format_color_comment(hex_str)
            return f"{oklch_str} /* {comment} */"

        return oklch_str

    def convert_rgb(match: re.Match) -> str:
        """Convert an rgb/rgba color match to oklch."""
        full_match = match.group(0)

        try:
            r = int(match.group(1))
            g = int(match.group(2))
            b = int(match.group(3))
            alpha_str = match.group(4)

            if alpha_str:
                if alpha_str.endswith("%"):
                    alpha = float(alpha_str[:-1]) / 100
                else:
                    alpha = float(alpha_str)
            else:
                alpha = 1.0

            result = rgb_to_oklch(r, g, b, alpha)
            if result is None:
                return full_match

            lightness, chroma, hue, alpha = result

            # Format oklch value
            if alpha < 1.0:
                oklch_str = f"oklch({lightness} {chroma} {hue} / {round(alpha, 2)})"
            else:
                oklch_str = f"oklch({lightness} {chroma} {hue})"

            # Add color name as comment
            if add_names:
                # Convert RGB to hex for name lookup
                hex_str = f"{r:02x}{g:02x}{b:02x}"
                comment = format_color_comment(hex_str)
                return f"{oklch_str} /* {comment} */"

            return oklch_str

        except (ValueError, IndexError):
            return full_match

    # Apply conversions
    result = re.sub(hex_pattern, convert_hex, css_content)
    result = re.sub(rgb_pattern, convert_rgb, result)

    return result
