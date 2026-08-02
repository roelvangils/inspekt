"""
CSS Authored Merger Service

Merges original authored CSS values (from CDP CSS.getMatchedStylesForNode)
into the computed CSS tree (from getComputedStyle).

For each property:
- If an authored value exists → use it (preserves clamp, calc, var, rem, etc.)
- Otherwise → keep the computed value as fallback
"""

from __future__ import annotations

from typing import Any


def merge_authored_css(
    computed_tree: dict[str, Any],
    authored_map: dict[str, dict[str, dict]],
) -> dict[str, Any]:
    """
    Walk the computed tree depth-first and enrich properties with authored values.

    Args:
        computed_tree: Element tree from get_computed_css.js (root node)
        authored_map: Map from element index (as string) to authored properties.
                      Each value is a dict of { prop_name: { value, selector, ... } }

    Returns:
        The computed_tree, modified in place, with authored values replacing
        computed values where available. Each element node gains an
        'authoredProps' list tracking which properties came from authored CSS.
    """
    _index = [0]  # Mutable counter for depth-first traversal

    def _walk(node: dict[str, Any]) -> None:
        idx = str(_index[0])
        _index[0] += 1

        styles = node.get("styles", {})
        rounded_props = set(node.get("roundedProps", []))
        computed_props = set(node.get("computedProps", []))
        authored_props: list[str] = []

        element_authored = authored_map.get(idx, {})

        computed_values: dict[str, str] = {}  # {prop: original_computed_value}

        for prop in list(styles.keys()):
            if prop in element_authored:
                authored_entry = element_authored[prop]
                authored_value = (
                    authored_entry.get("value")
                    if isinstance(authored_entry, dict)
                    else authored_entry
                )

                if authored_value and authored_value != styles[prop]:
                    computed_values[prop] = styles[prop]  # Save original computed value
                    styles[prop] = authored_value
                    authored_props.append(prop)

                    # Remove from rounded/computed — authored values have original units
                    rounded_props.discard(prop)
                    computed_props.discard(prop)

        node["styles"] = styles
        node["roundedProps"] = list(rounded_props)
        node["computedProps"] = list(computed_props)
        node["authoredProps"] = authored_props
        node["computedValues"] = computed_values

        for child in node.get("children", []):
            _walk(child)

    _walk(computed_tree)
    return computed_tree
