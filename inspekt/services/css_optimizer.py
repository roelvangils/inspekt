"""
CSS optimization utilities using Lightning CSS.

Requires: npm install -g lightningcss-cli
"""
from __future__ import annotations

import re
import subprocess

import click


def alphabetize_css_properties(css_content: str) -> str:
    """
    Alphabetize CSS properties within each rule block.

    Sorts properties alphabetically while preserving:
    - Comments attached to properties (e.g., color names)
    - Nested rules (sorted recursively)
    - Overall structure and formatting

    Args:
        css_content: CSS string with properties to sort

    Returns:
        CSS with properties sorted alphabetically within each rule
    """

    def sort_block(match: re.Match) -> str:
        """Sort properties within a single CSS block."""
        before_brace = match.group(1)  # Selector or nested selector
        content = match.group(2)  # Block content

        # Split content into lines
        lines = content.split("\n")

        # Separate properties from nested rules and other content
        properties = []
        nested_blocks = []
        current_property = []
        brace_depth = 0

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Track brace depth for nested rules
            brace_depth += line.count("{") - line.count("}")

            if brace_depth > 0 or "{" in line:
                # Part of a nested rule
                nested_blocks.append(line)
            elif stripped.startswith("/*") and ":" not in stripped:
                # Standalone comment, attach to next property
                current_property.append(line)
            elif ":" in stripped and stripped.endswith(";"):
                # This is a property
                current_property.append(line)
                properties.append("\n".join(current_property))
                current_property = []
            elif ":" in stripped and "/*" in stripped and "*/" in stripped:
                # Property with inline comment
                current_property.append(line)
                properties.append("\n".join(current_property))
                current_property = []
            else:
                # Could be a property continuation or other content
                if current_property:
                    current_property.append(line)
                else:
                    # Standalone line (probably part of property)
                    properties.append(line)

        # Sort properties by the property name (first word before colon)
        def get_sort_key(prop: str) -> str:
            # Find the property name (skip comments, get first word before :)
            for line in prop.split("\n"):
                line = line.strip()
                if line.startswith("/*"):
                    continue
                if ":" in line:
                    return line.split(":")[0].strip().lower()
            return prop.lower()

        properties.sort(key=get_sort_key)

        # Reconstruct the block
        result_lines = []
        for prop in properties:
            result_lines.append(prop)

        # Add nested blocks at the end
        if nested_blocks:
            if result_lines:
                result_lines.append("")  # Blank line before nested rules
            result_lines.extend(nested_blocks)

        # Reconstruct with proper indentation
        content_str = "\n".join(result_lines)
        return f"{before_brace}{{{content_str}\n}}"

    # Process CSS blocks - match selector { content }
    # This is a simplified approach; for production, consider a proper CSS parser
    result = css_content

    # Use Prettier's output format: each block is properly formatted
    # We'll process the formatted CSS line by line
    lines = result.split("\n")
    output_lines = []
    current_selector = []
    current_block = []
    brace_depth = 0
    in_block = False

    for line in lines:
        if "{" in line and brace_depth == 0:
            # Start of a new block
            current_selector = [line.split("{")[0]]
            rest = line.split("{", 1)[1] if "{" in line else ""
            current_block = [rest] if rest.strip() else []
            brace_depth = line.count("{") - line.count("}")
            in_block = True
        elif in_block:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                # End of block
                if "}" in line:
                    before_close = line.rsplit("}", 1)[0]
                    if before_close.strip():
                        current_block.append(before_close)

                # Sort this block's properties
                block_content = "\n".join(current_block)
                sorted_props = sort_properties_in_block(block_content)

                # Output the sorted block
                selector = "".join(current_selector).strip()
                output_lines.append(f"{selector} {{")
                if sorted_props.strip():
                    output_lines.append(sorted_props)
                output_lines.append("}")

                current_block = []
                current_selector = []
                in_block = False
                brace_depth = 0
            else:
                current_block.append(line)
        else:
            output_lines.append(line)

    return "\n".join(output_lines)


# 5-category system for CSS property grouping
# Categories: 1=Layout, 2=Box, 3=Typography, 4=Animation, 5=Other
CSS_CATEGORY_NAMES = {
    1: "Layout",
    2: "Box",
    3: "Typography",
    4: "Animation",
    5: "Other",
}

# Maps CSS properties to their category (1-5)
# Properties not listed default to category 5 (Other)
CSS_PROPERTY_CATEGORY = {
    # Category 1: Layout - display, sizing, flexbox, grid
    "display": 1,
    "box-sizing": 1,
    "float": 1,
    "clear": 1,
    "width": 1,
    "min-width": 1,
    "max-width": 1,
    "height": 1,
    "min-height": 1,
    "max-height": 1,
    "overflow": 1,
    "overflow-x": 1,
    "overflow-y": 1,
    # Flexbox
    "flex": 1,
    "flex-direction": 1,
    "flex-wrap": 1,
    "flex-flow": 1,
    "flex-grow": 1,
    "flex-shrink": 1,
    "flex-basis": 1,
    "justify-content": 1,
    "justify-items": 1,
    "justify-self": 1,
    "align-content": 1,
    "align-items": 1,
    "align-self": 1,
    "place-content": 1,
    "place-items": 1,
    "place-self": 1,
    "order": 1,
    "gap": 1,
    "row-gap": 1,
    "column-gap": 1,
    # Grid
    "grid": 1,
    "grid-template": 1,
    "grid-template-columns": 1,
    "grid-template-rows": 1,
    "grid-template-areas": 1,
    "grid-auto-columns": 1,
    "grid-auto-rows": 1,
    "grid-auto-flow": 1,
    "grid-column": 1,
    "grid-row": 1,
    "grid-area": 1,

    # Category 2: Box - position, spacing, borders
    "position": 2,
    "top": 2,
    "right": 2,
    "bottom": 2,
    "left": 2,
    "inset": 2,
    "z-index": 2,
    "margin": 2,
    "margin-top": 2,
    "margin-right": 2,
    "margin-bottom": 2,
    "margin-left": 2,
    "margin-block": 2,
    "margin-inline": 2,
    "padding": 2,
    "padding-top": 2,
    "padding-right": 2,
    "padding-bottom": 2,
    "padding-left": 2,
    "padding-block": 2,
    "padding-inline": 2,
    "border": 2,
    "border-width": 2,
    "border-style": 2,
    "border-color": 2,
    "border-top": 2,
    "border-top-width": 2,
    "border-top-style": 2,
    "border-top-color": 2,
    "border-right": 2,
    "border-right-width": 2,
    "border-right-style": 2,
    "border-right-color": 2,
    "border-bottom": 2,
    "border-bottom-width": 2,
    "border-bottom-style": 2,
    "border-bottom-color": 2,
    "border-left": 2,
    "border-left-width": 2,
    "border-left-style": 2,
    "border-left-color": 2,
    "border-radius": 2,
    "border-top-left-radius": 2,
    "border-top-right-radius": 2,
    "border-bottom-right-radius": 2,
    "border-bottom-left-radius": 2,
    "outline": 2,
    "outline-width": 2,
    "outline-style": 2,
    "outline-color": 2,
    "outline-offset": 2,

    # Category 3: Typography - text appearance
    "color": 3,
    "font": 3,
    "font-family": 3,
    "font-size": 3,
    "font-weight": 3,
    "font-style": 3,
    "font-variant": 3,
    "line-height": 3,
    "letter-spacing": 3,
    "word-spacing": 3,
    "text-align": 3,
    "text-decoration": 3,
    "text-decoration-color": 3,
    "text-decoration-line": 3,
    "text-decoration-style": 3,
    "text-decoration-thickness": 3,
    "text-transform": 3,
    "text-indent": 3,
    "text-shadow": 3,
    "text-overflow": 3,
    "white-space": 3,
    "word-break": 3,
    "word-wrap": 3,
    "overflow-wrap": 3,
    "hyphens": 3,
    "direction": 3,
    "writing-mode": 3,

    # Category 4: Animation - motion and transforms
    "transform": 4,
    "transform-origin": 4,
    "transition": 4,
    "transition-property": 4,
    "transition-duration": 4,
    "transition-timing-function": 4,
    "transition-delay": 4,
    "animation": 4,
    "animation-name": 4,
    "animation-duration": 4,
    "animation-timing-function": 4,
    "animation-delay": 4,
    "animation-iteration-count": 4,
    "animation-direction": 4,
    "animation-fill-mode": 4,
    "animation-play-state": 4,

    # Category 5 (Other) is the default - no need to list properties
}

# CSS property ordering - defines sort order within each category
# Format: category * 100 + order_within_category
CSS_PROPERTY_ORDER = {
    # Layout (100-199) - display, sizing, flexbox, grid
    "display": 100,
    "box-sizing": 101,
    "float": 102,
    "clear": 103,
    "width": 110,
    "min-width": 111,
    "max-width": 112,
    "height": 113,
    "min-height": 114,
    "max-height": 115,
    "overflow": 116,
    "overflow-x": 117,
    "overflow-y": 118,
    # Flexbox (120-139)
    "flex": 120,
    "flex-direction": 121,
    "flex-wrap": 122,
    "flex-flow": 123,
    "flex-grow": 124,
    "flex-shrink": 125,
    "flex-basis": 126,
    "justify-content": 127,
    "justify-items": 128,
    "justify-self": 129,
    "align-content": 130,
    "align-items": 131,
    "align-self": 132,
    "place-content": 133,
    "place-items": 134,
    "place-self": 135,
    "order": 136,
    "gap": 137,
    "row-gap": 138,
    "column-gap": 139,
    # Grid (140-159)
    "grid": 140,
    "grid-template": 141,
    "grid-template-columns": 142,
    "grid-template-rows": 143,
    "grid-template-areas": 144,
    "grid-auto-columns": 145,
    "grid-auto-rows": 146,
    "grid-auto-flow": 147,
    "grid-column": 148,
    "grid-row": 149,
    "grid-area": 150,

    # Box (200-299) - position, spacing, borders
    "position": 200,
    "inset": 201,
    "top": 202,
    "right": 203,
    "bottom": 204,
    "left": 205,
    "z-index": 206,
    "margin": 210,
    "margin-top": 211,
    "margin-right": 212,
    "margin-bottom": 213,
    "margin-left": 214,
    "margin-block": 215,
    "margin-inline": 216,
    "padding": 220,
    "padding-top": 221,
    "padding-right": 222,
    "padding-bottom": 223,
    "padding-left": 224,
    "padding-block": 225,
    "padding-inline": 226,
    "border": 230,
    "border-width": 231,
    "border-style": 232,
    "border-color": 233,
    "border-top": 234,
    "border-top-width": 235,
    "border-top-style": 236,
    "border-top-color": 237,
    "border-right": 238,
    "border-right-width": 239,
    "border-right-style": 240,
    "border-right-color": 241,
    "border-bottom": 242,
    "border-bottom-width": 243,
    "border-bottom-style": 244,
    "border-bottom-color": 245,
    "border-left": 246,
    "border-left-width": 247,
    "border-left-style": 248,
    "border-left-color": 249,
    "border-radius": 250,
    "border-top-left-radius": 251,
    "border-top-right-radius": 252,
    "border-bottom-right-radius": 253,
    "border-bottom-left-radius": 254,
    "outline": 260,
    "outline-width": 261,
    "outline-style": 262,
    "outline-color": 263,
    "outline-offset": 264,

    # Typography (300-399)
    "color": 300,
    "font": 301,
    "font-family": 302,
    "font-size": 303,
    "font-weight": 304,
    "font-style": 305,
    "font-variant": 306,
    "line-height": 307,
    "letter-spacing": 308,
    "word-spacing": 309,
    "text-align": 310,
    "text-decoration": 311,
    "text-decoration-color": 312,
    "text-decoration-line": 313,
    "text-decoration-style": 314,
    "text-decoration-thickness": 315,
    "text-transform": 316,
    "text-indent": 317,
    "text-shadow": 318,
    "text-overflow": 319,
    "white-space": 320,
    "word-break": 321,
    "word-wrap": 322,
    "overflow-wrap": 323,
    "hyphens": 324,
    "direction": 325,
    "writing-mode": 326,

    # Animation (400-499)
    "transform": 400,
    "transform-origin": 401,
    "transition": 410,
    "transition-property": 411,
    "transition-duration": 412,
    "transition-timing-function": 413,
    "transition-delay": 414,
    "animation": 420,
    "animation-name": 421,
    "animation-duration": 422,
    "animation-timing-function": 423,
    "animation-delay": 424,
    "animation-iteration-count": 425,
    "animation-direction": 426,
    "animation-fill-mode": 427,
    "animation-play-state": 428,

    # Other (500+) - alphabetized
}


def get_property_category(prop_name: str) -> int:
    """
    Get the category ID for a CSS property.

    Returns:
        1 = Layout (display, sizing, flexbox, grid)
        2 = Box (position, margin, padding, border, outline)
        3 = Typography (color, font-*, text-*, line-height)
        4 = Animation (transition, animation, transform)
        5 = Other (everything else, alphabetized)
    """
    prop_name = prop_name.lower().strip()

    # Check for exact match in category dict
    if prop_name in CSS_PROPERTY_CATEGORY:
        return CSS_PROPERTY_CATEGORY[prop_name]

    # Check for prefix matches for properties not explicitly listed
    prefix_to_category = {
        # Layout prefixes
        "flex-": 1,
        "grid-": 1,
        "justify-": 1,
        "align-": 1,
        # Box prefixes
        "margin-": 2,
        "padding-": 2,
        "border-": 2,
        "outline-": 2,
        # Typography prefixes
        "font-": 3,
        "text-": 3,
        # Animation prefixes
        "transition-": 4,
        "animation-": 4,
        "transform-": 4,
    }

    for prefix, category in prefix_to_category.items():
        if prop_name.startswith(prefix):
            return category

    return 5  # Default to "Other"


def get_property_sort_key(prop_name: str) -> tuple[int, str]:
    """
    Get sort key for a CSS property.

    Returns a tuple of (priority, name) where:
    - priority: Lower numbers come first (category * 100 + order)
    - name: For alphabetical sorting within same priority
    """
    prop_name = prop_name.lower().strip()

    # Check for exact match in order dict
    if prop_name in CSS_PROPERTY_ORDER:
        return (CSS_PROPERTY_ORDER[prop_name], prop_name)

    # For properties not explicitly listed, use category * 100 + 99
    # and sort alphabetically within that
    category = get_property_category(prop_name)
    return (category * 100 + 99, prop_name)


def sort_properties_in_block(block_content: str, add_category_comments: bool = True) -> str:
    """
    Sort CSS properties within a block using logical property ordering.

    Properties are grouped by category (positioning, box model, typography, etc.)
    with optional comment headers for each group.
    """
    lines = block_content.split("\n")
    properties = []
    nested = []
    current_lines = []
    brace_depth = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        open_braces = line.count("{")
        close_braces = line.count("}")

        if brace_depth > 0 or open_braces > 0:
            # We're in or entering a nested block
            nested.append(line)
            brace_depth += open_braces - close_braces
        elif ":" in stripped:
            # This is a property line
            current_lines.append(line)
            if stripped.endswith(";") or ("/*" in stripped and "*/" in stripped):
                properties.append("\n".join(current_lines))
                current_lines = []
        elif stripped.startswith("/*"):
            # Comment - attach to next property
            current_lines.append(line)
        else:
            if current_lines:
                current_lines.append(line)
                # Check if this continuation line completes the property
                # (e.g., last value in a multi-line transition ending with ";")
                if stripped.endswith(";") or (";" in stripped and "/*" in stripped and "*/" in stripped):
                    properties.append("\n".join(current_lines))
                    current_lines = []

    # Don't forget remaining lines
    if current_lines:
        properties.append("\n".join(current_lines))

    # Extract property name for sorting
    def get_prop_name(prop: str) -> str:
        for line in prop.split("\n"):
            line = line.strip()
            if line.startswith("/*"):
                continue
            if ":" in line:
                return line.split(":")[0].strip().lower()
        return ""

    # Sort using logical property ordering
    properties.sort(key=lambda p: get_property_sort_key(get_prop_name(p)))

    # Build result with category comments
    result = []
    current_category = None

    # Detect indentation from first property
    indent = "  "  # Default
    if properties:
        first_line = properties[0].split("\n")[0]
        leading_spaces = len(first_line) - len(first_line.lstrip())
        indent = " " * leading_spaces

    # Pre-calculate which categories are present
    categories_in_block = set(get_property_category(get_prop_name(p)) for p in properties)
    has_multiple_categories = len(categories_in_block) > 1

    for prop in properties:
        prop_name = get_prop_name(prop)
        category = get_property_category(prop_name)

        # Add category comment when category changes
        if add_category_comments and category != current_category and has_multiple_categories:
            category_name = CSS_CATEGORY_NAMES.get(category)

            if category_name:
                if result:  # Add blank line before new category (except first)
                    result.append("")
                result.append(f"{indent}/* {category_name} */")

            current_category = category

        result.append(prop)

    # Add nested blocks at the end
    if nested:
        result.append("")  # Blank line before nested
        result.extend(nested)

    return "\n".join(result)


def optimize_css(
    css_content: str,
    format_output: bool = True,
    convert_to_oklch: bool = False,
    add_color_names: bool = False,
    alphabetize: bool = True,
    rounded_props: set[str] | None = None,
    computed_props: set[str] | None = None,
    heuristic_comments: bool = False,
    column_format: str | None = None,
    cross_ref_values: dict[str, str] | None = None,
) -> str:
    """
    Optimize CSS using Lightning CSS, then format with Prettier.

    Performs:
    - Merging longhand properties into shorthands
    - Removing redundant rules
    - Merging adjacent rules with same selectors
    - Optionally converting colors to oklch format
    - Optionally adding human-readable color name comments
    - Optionally alphabetizing properties within each rule
    - Adding computed/rounded value comments for tracked properties
    - Optionally adding heuristic comments for property-value patterns

    Args:
        css_content: Raw CSS string (supports CSS nesting)
        format_output: Whether to format with Prettier (default: True)
        convert_to_oklch: Convert colors to oklch format (default: False)
        add_color_names: Add color name comments (default: False)
        alphabetize: Sort properties alphabetically (default: True)
        rounded_props: Set of property names that were rounded (for comments)
        computed_props: Set of property names with decimal values (for comments)
        heuristic_comments: Add helpful comments based on property-value patterns (default: False)
        column_format: Column alignment format - "two" for 2-column layout (prop, value+comment)
                      or "three" for 3-column layout (prop, value, comment). None disables.

    Returns:
        Optimized (and optionally formatted) CSS string
    """
    try:
        # Step 1: Optimize with Lightning CSS
        # Lightning CSS reads from stdin if no input file is given
        result = subprocess.run(
            [
                "lightningcss",
                "--minify",  # Enable minification (includes shorthand merging)
                "--error-recovery",  # Skip invalid rules gracefully
            ],
            input=css_content,
            capture_output=True,
            text=True,
            check=True,
        )
        optimized = result.stdout

        # Step 2: Convert colors to oklch (includes color names)
        # oklch conversion changes values, so must run before Prettier
        if convert_to_oklch:
            from inspekt.services.css_color_converter import convert_colors_to_oklch

            optimized = convert_colors_to_oklch(optimized)

        # Step 3: Format with Prettier for readability
        if format_output:
            formatted = format_css_with_prettier(optimized)
            if formatted:
                optimized = formatted

        # Step 4: Alphabetize properties (after formatting for clean output)
        if alphabetize:
            optimized = alphabetize_css_properties(optimized)

        # Step 5: Add computed/rounded value comments
        # These are added AFTER optimization because Lightning CSS strips comments
        from inspekt.services.css_color_converter import add_rounded_property_comments

        if rounded_props:
            optimized = add_rounded_property_comments(
                optimized, rounded_props, "Browser-computed"
            )
        elif computed_props:
            optimized = add_rounded_property_comments(
                optimized, computed_props, "Browser-computed"
            )

        # Step 6: Add color name comments (when not using oklch conversion)
        # Runs AFTER Prettier so comments don't cause unwanted line wrapping
        if add_color_names and not convert_to_oklch:
            from inspekt.services.css_color_converter import add_color_name_comments

            optimized = add_color_name_comments(optimized)

        # Step 7: Add heuristic comments for property-value patterns
        # Must run after color names to merge with them (e.g. "White, Invisible text")
        if heuristic_comments:
            from inspekt.services.css_color_converter import add_heuristic_comments

            optimized = add_heuristic_comments(optimized)

        # Step 7.5: Add cross-reference comments (authored → computed)
        if cross_ref_values:
            from inspekt.services.css_color_converter import add_cross_ref_comments

            optimized = add_cross_ref_comments(optimized, cross_ref_values)

        # Step 8: Apply column formatting if requested
        if column_format:
            optimized = format_css_columns(optimized, column_format)

        # Step 9: Deduplicate color descriptions
        # Must run AFTER all reordering (alphabetisation, column formatting)
        # so "first occurrence" matches the final output order.
        if convert_to_oklch or add_color_names:
            from inspekt.services.css_color_converter import dedup_color_descriptions

            optimized = dedup_color_descriptions(optimized)

        return optimized
    except subprocess.CalledProcessError as e:
        click.echo(f"Error running lightningcss: {e.stderr}", err=True)
        return css_content  # Return original on error


def format_css_with_prettier(css_content: str) -> str | None:
    """Format CSS using Prettier."""
    try:
        result = subprocess.run(
            ["prettier", "--stdin-filepath", "styles.css", "--parser", "css"],
            input=css_content,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def format_css_columns(css_content: str, column_format: str) -> str:
    """
    Format CSS properties in aligned columns.

    Args:
        css_content: CSS string to format
        column_format: "two" for 2-column layout (property aligned, value+comment together)
                      "three" for 3-column layout (property, value, comment aligned separately)

    Returns:
        CSS with aligned columns
    """
    lines = css_content.split("\n")
    result = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Pass through empty lines and standalone section comments
        if not stripped or (stripped.startswith("/*") and stripped.endswith("*/")):
            result.append(line)
            i += 1
            continue

        # Check if this is a selector opening a block
        if stripped.endswith("{"):
            result.append(line)
            i += 1
            # Process this block
            block_result, i = _process_css_block(lines, i, column_format)
            result.extend(block_result)
            continue

        # Pass through any other lines (closing braces, etc.)
        result.append(line)
        i += 1

    return "\n".join(result)


def _process_css_block(lines: list[str], start_idx: int, column_format: str) -> tuple[list[str], int]:
    """
    Process a CSS block, handling properties, nested blocks, and multi-line values.

    Returns:
        Tuple of (formatted lines, next index to process)
    """
    # First pass: collect all items in this block to calculate column widths
    block_items = []  # List of tuples: ("property", lines, parsed) or ("passthrough", lines, None) or ("nested", lines, None)
    block_indent = ""
    i = start_idx

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Determine indentation from first content line
        if not block_indent and stripped and not stripped.startswith("/*"):
            block_indent = line[:len(line) - len(line.lstrip())]

        # End of block
        if stripped == "}":
            block_items.append(("close", [line], None))
            i += 1
            break

        # Empty line or section comment - marks a section boundary
        if not stripped or (stripped.startswith("/*") and stripped.endswith("*/")):
            block_items.append(("section", [line], None))
            i += 1
            continue

        # Nested block (selector with {)
        if stripped.endswith("{"):
            block_items.append(("nested_start", [line], None))
            i += 1
            # Recursively process nested block
            nested_result, i = _process_css_block(lines, i, column_format)
            block_items.append(("nested_content", nested_result, None))
            continue

        # Check if this is a property line (has colon)
        if ":" in stripped:
            # Collect the full property (may span multiple lines)
            prop_lines, i = _collect_full_property(lines, i)
            full_prop = " ".join(line.strip() for line in prop_lines)

            # Check if this is a simple single-line property we can format
            parsed = _parse_property_line(full_prop)
            if parsed and len(prop_lines) == 1 and _is_simple_value(parsed[1]):
                block_items.append(("property", prop_lines, parsed))
            elif len(prop_lines) > 1:
                # Multi-line property - store for later formatting with block's column width
                block_items.append(("multiline", prop_lines, None))
            else:
                # Complex single-line property - pass through as-is
                block_items.append(("passthrough", prop_lines, None))
            continue

        # Unknown line, pass through
        block_items.append(("passthrough", [line], None))
        i += 1

    # Second pass: calculate column widths from ALL simple properties in each section
    result = []
    section_start = 0

    while section_start < len(block_items):
        # Find the end of this section (next section comment or end)
        section_end = section_start
        while section_end < len(block_items):
            item_type = block_items[section_end][0]
            if item_type == "section" and section_end > section_start:
                break
            if item_type == "close":
                break
            section_end += 1

        # Collect all simple properties in this section for width calculation
        section_properties = []
        for idx in range(section_start, section_end):
            item_type, item_lines, parsed = block_items[idx]
            if item_type == "property":
                section_properties.append(parsed)

        # Calculate max widths for this section
        max_prop_len = max((len(p[0]) for p in section_properties), default=0)
        max_value_len = max((len(p[1]) for p in section_properties), default=0)

        # Output items in this section with consistent formatting
        for idx in range(section_start, section_end):
            item_type, item_lines, parsed = block_items[idx]

            if item_type == "property":
                formatted = _format_single_property(parsed, block_indent, column_format, max_prop_len, max_value_len)
                result.append(formatted)
            elif item_type == "multiline":
                # Format multi-line property with block's column width
                formatted_lines = _format_multiline_property(item_lines, block_indent, max_prop_len)
                result.extend(formatted_lines)
            elif item_type == "nested_start" or item_type == "nested_content":
                result.extend(item_lines)
            else:
                # passthrough, section comments, etc.
                result.extend(item_lines)

        # Include the section boundary if present
        if section_end < len(block_items):
            item_type, item_lines, _ = block_items[section_end]
            if item_type == "section" or item_type == "close":
                result.extend(item_lines)
                section_start = section_end + 1
            else:
                section_start = section_end
        else:
            section_start = section_end

    return result, i


def _format_multiline_property(prop_lines: list[str], block_indent: str, block_prop_len: int = 0) -> list[str]:
    """
    Format a multi-line property with comma-separated values.

    Only formats values that look like property-value pairs (like transitions):
        transition:
            background-color      0.2s,
            border-color          0.2s,
            color                 0.2s;

    Does NOT format font-family or other values where words should stay together.

    Args:
        prop_lines: List of lines making up the property
        block_indent: Base indentation for the block
        block_prop_len: The block's max property length (for alignment with other properties)

    Returns:
        Formatted lines
    """
    if len(prop_lines) < 2:
        return prop_lines

    # First line is the property declaration (e.g., "transition:")
    result = [prop_lines[0]]

    # Parse continuation lines to find name/value pairs
    value_lines = prop_lines[1:]
    parsed_values = []
    all_formattable = True

    for line in value_lines:
        stripped = line.strip()
        # Determine the indentation of this line
        line_indent = line[:len(line) - len(line.lstrip())]

        # Try to parse as "name value," or "name value;"
        # Split on whitespace, first part is name, rest is value
        parts = stripped.split(None, 1)
        if len(parts) == 2:
            name, value = parts
            # Only consider it formattable if:
            # 1. The name looks like a CSS property (contains hyphen) or color (starts with #)
            # 2. The value looks like a CSS value (time, percentage, number, or contains parentheses)
            is_property_like = "-" in name or name.startswith("#")
            stripped_value = value.rstrip(",;")
            # CSS measurement must start with a digit to avoid matching
            # font names like "Sans" (which endswith "s" like a time unit)
            is_css_measurement = (
                len(stripped_value) > 1
                and stripped_value[0].isdigit()
                and stripped_value.endswith(("s", "ms", "%", "px", "em", "rem"))
            )
            is_value_like = (
                is_css_measurement or
                stripped_value.replace(".", "").isdigit() or
                "(" in value or
                value.startswith("#")
            )
            if is_property_like or is_value_like:
                parsed_values.append((line_indent, name, value, True))
            else:
                parsed_values.append((line_indent, stripped, None, False))
                all_formattable = False
        else:
            # Can't parse (single token like "sans-serif;"), keep as-is
            parsed_values.append((line_indent, stripped, None, False))
            all_formattable = False

    # Only apply column formatting if all lines are formattable
    if not all_formattable:
        # Return original lines unchanged
        return prop_lines

    # Use block's property length for alignment, or calculate from local names
    max_name_len = max(
        (len(pv[1]) for pv in parsed_values if pv[2] is not None),
        default=0
    )
    # Use the larger of block width or local width for alignment
    target_width = max(block_prop_len, max_name_len + 2)

    # Format each value line
    for line_indent, name, value, formattable in parsed_values:
        if value is not None and formattable:
            # Pad the name to align with block's property column
            name_padded = name.ljust(target_width)
            result.append(f"{line_indent}{name_padded}{value}")
        else:
            # Couldn't parse or not formattable, keep original
            result.append(f"{line_indent}{name}")

    return result


def _format_single_property(parsed: tuple, indent: str, column_format: str, max_prop_len: int, max_value_len: int) -> str:
    """Format a single property with given column widths."""
    prop_name, value, comment = parsed

    # Pad property name
    prop_padded = prop_name.ljust(max_prop_len + 2)

    if column_format == "three":
        # Three visual columns: property, value (padded), comment
        if comment:
            value_padded = value.ljust(max_value_len + 2)
            return f"{indent}{prop_padded}{value_padded}{comment};"
        else:
            return f"{indent}{prop_padded}{value};"
    else:
        # Two visual columns: property, value+comment together
        if comment:
            return f"{indent}{prop_padded}{value} {comment};"
        else:
            return f"{indent}{prop_padded}{value};"


def _collect_full_property(lines: list[str], start_idx: int) -> tuple[list[str], int]:
    """
    Collect all lines that make up a single CSS property (handling multi-line values).

    Returns:
        Tuple of (list of lines, next index to process)
    """
    prop_lines = [lines[start_idx]]
    i = start_idx + 1

    # Count parentheses to detect multi-line values
    paren_depth = lines[start_idx].count("(") - lines[start_idx].count(")")

    # Check if property is complete on this line
    # A property is complete if parentheses are balanced and it contains a semicolon
    # (the semicolon may be before a trailing comment like "value; /* comment */")
    first_stripped = lines[start_idx].strip()
    if paren_depth == 0 and ";" in first_stripped:
        return prop_lines, i

    # Collect continuation lines until we find the closing
    while i < len(lines) and paren_depth > 0:
        line = lines[i]
        prop_lines.append(line)
        paren_depth += line.count("(") - line.count(")")
        i += 1

    # Also check if we need to continue until semicolon
    # (check for ";" anywhere in line to handle trailing comments like "value; /* comment */")
    if prop_lines and ";" not in prop_lines[-1]:
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            # Stop at block boundaries
            if stripped == "}" or stripped.endswith("{"):
                break
            prop_lines.append(line)
            i += 1
            if ";" in stripped:
                break

    return prop_lines, i


def _is_simple_value(value: str) -> bool:
    """
    Check if a value is simple (single-line, no function calls with multiple args).
    """
    # If it contains unbalanced parentheses or newlines, it's complex
    if "\n" in value:
        return False
    # If parentheses are balanced and don't contain commas, it's simple
    if "(" in value:
        paren_depth = 0
        for char in value:
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
        if paren_depth != 0:
            return False
    return True


def _parse_property_line(line: str) -> tuple[str, str, str] | None:
    """
    Parse a CSS property line into (property_name_with_colon, value, comment).

    Args:
        line: CSS property line like "width: 249px; /* Browser-computed */"

    Returns:
        Tuple of (property_with_colon, value, comment) or None if can't parse
    """
    # Match pattern: property: value; /* optional comment */
    # Or: property: value /* comment */;

    # First, check for comment
    comment = ""
    comment_match = re.search(r'/\*.*?\*/', line)
    if comment_match:
        comment = comment_match.group(0)
        # Remove comment from line for easier parsing
        line_no_comment = line[:comment_match.start()] + line[comment_match.end():]
    else:
        line_no_comment = line

    # Remove all trailing semicolons and whitespace
    line_no_comment = line_no_comment.strip().rstrip(";").strip()

    # Split by first colon
    if ":" not in line_no_comment:
        return None

    colon_idx = line_no_comment.index(":")
    prop_name = line_no_comment[:colon_idx].strip() + ":"
    value = line_no_comment[colon_idx + 1:].strip()

    # Clean any remaining semicolons from value
    value = value.rstrip(";").strip()

    return (prop_name, value, comment)
