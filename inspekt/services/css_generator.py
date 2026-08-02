"""
CSS Generator Service

Converts element tree with computed styles into nested CSS format.
"""

from __future__ import annotations

from typing import Any


def generate_nested_css(
    element_data: dict[str, Any],
    indent_size: int = 4,
) -> str:
    """
    Convert element tree to nested CSS.

    Args:
        element_data: Element tree from get_computed_css.js
        indent_size: Number of spaces for indentation

    Returns:
        Nested CSS string
    """
    lines: list[str] = []
    _generate_element_css(element_data, lines, 0, indent_size)
    return "\n".join(lines)


def _generate_element_css(
    element: dict[str, Any],
    lines: list[str],
    depth: int,
    indent_size: int,
) -> None:
    """
    Recursively generate CSS for an element and its children.
    """
    indent = " " * (depth * indent_size)
    selector = element.get("selector", element.get("tag", "unknown"))
    styles = element.get("styles", {})
    rounded_props = set(element.get("roundedProps", []))   # Properties that were rounded
    computed_props = set(element.get("computedProps", []))  # Properties with decimal pixels (when not rounding)
    authored_props = set(element.get("authoredProps", []))  # Properties with original authored values
    children = element.get("children", [])

    # Skip elements with no styles and no children with styles
    if not styles and not _has_styled_children(element):
        return

    # Open selector block
    lines.append(f"{indent}{selector} {{")

    # Add style properties
    prop_indent = " " * ((depth + 1) * indent_size)
    for prop, value in sorted(styles.items()):
        # Skip empty values (but keep "none" — it may be needed for shorthand merging)
        if not value:
            continue

        # Add comments for browser-computed values (skip for authored properties)
        if prop in authored_props:
            lines.append(f"{prop_indent}{prop}: {value};")
        elif prop in rounded_props or prop in computed_props:
            lines.append(f"{prop_indent}{prop}: {value}; /* Browser-computed */")
        else:
            lines.append(f"{prop_indent}{prop}: {value};")

    # Add children (nested)
    for child in children:
        child_styles = child.get("styles", {})

        # Only include children that have styles or styled descendants
        if child_styles or _has_styled_children(child):
            if styles:  # Add blank line between properties and nested rules
                lines.append("")
            _generate_element_css(child, lines, depth + 1, indent_size)

    # Close selector block
    lines.append(f"{indent}}}")


def _has_styled_children(element: dict[str, Any]) -> bool:
    """
    Check if element has any children with styles.
    """
    for child in element.get("children", []):
        if child.get("styles"):
            return True
        if _has_styled_children(child):
            return True
    return False


def format_css_compact(css: str) -> str:
    """
    Convert CSS to a more compact format (remove extra whitespace).
    """
    lines = []
    for line in css.split("\n"):
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return " ".join(lines)


def count_properties(element_data: dict[str, Any]) -> int:
    """
    Count total number of CSS properties in the element tree.
    """
    count = len(element_data.get("styles", {}))
    for child in element_data.get("children", []):
        count += count_properties(child)
    return count


def collect_rounded_props(element_data: dict[str, Any]) -> set[str]:
    """
    Collect all property names that were rounded from the element tree.

    Returns a set of property names (e.g., {"width", "height", "font-size"}).
    """
    rounded = set(element_data.get("roundedProps", []))
    for child in element_data.get("children", []):
        rounded.update(collect_rounded_props(child))
    return rounded


def collect_computed_props(element_data: dict[str, Any]) -> set[str]:
    """
    Collect all property names with decimal pixel values (when not rounding).

    Returns a set of property names.
    """
    computed = set(element_data.get("computedProps", []))
    for child in element_data.get("children", []):
        computed.update(collect_computed_props(child))
    return computed


def collect_cross_ref_values(element_data: dict[str, Any]) -> dict[str, str]:
    """
    Collect {prop_name: computed_value} from all nodes with computedValues.

    When multiple elements have the same property with different computed values,
    the first value found (depth-first) is kept — this is a best-effort hint.

    Returns:
        Dict mapping property name to its original computed value.
    """
    cross_ref: dict[str, str] = {}
    _collect_cross_ref_walk(element_data, cross_ref)
    return cross_ref


def _collect_cross_ref_walk(node: dict[str, Any], cross_ref: dict[str, str]) -> None:
    """Walk tree depth-first, collecting first computed value per property."""
    for prop, computed in node.get("computedValues", {}).items():
        if prop not in cross_ref:
            cross_ref[prop] = computed
    for child in node.get("children", []):
        _collect_cross_ref_walk(child, cross_ref)


def collect_authored_props(element_data: dict[str, Any]) -> set[str]:
    """
    Collect all property names that have original authored values (from CDP).

    Returns a set of property names.
    """
    authored = set(element_data.get("authoredProps", []))
    for child in element_data.get("children", []):
        authored.update(collect_authored_props(child))
    return authored
