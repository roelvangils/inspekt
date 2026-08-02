"""
CSS property heuristic comments.

Provides automatic helpful comments for CSS property-value pairs.

Features:
- Exact match comments for common property-value combinations
- Special handlers for TRBL shorthands, opacity, border-radius
- Pattern-based comments with value capture for dynamic values
- Case-insensitive matching
- Comment merging with existing comments

Usage:
    from inspekt.services.css_property_comments import get_property_comment

    comment = get_property_comment("display", "flex")  # "Flexbox container"
    comment = get_property_comment("border-radius", "8px")  # "8px rounded corners"
    comment = get_property_comment("margin", "0 8px 0 0")  # "8px right margin"
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable
from functools import lru_cache
from re import Pattern

# =============================================================================
# EXACT MATCH COMMENTS
# =============================================================================
# Format: {"property": {"value": "comment"}}
# Case-insensitive matching for both property and value

EXACT_COMMENTS: dict[str, dict[str, str]] = {
    # Layout & Display
    "display": {
        "none": "Hidden from layout",
        "block": "Block-level element",
        "inline": "Inline element",
        "inline-block": "Inline with block properties",
        "flex": "Flexbox container",
        "grid": "Grid container",
        "contents": "Only children rendered",
        "flow-root": "Block with clearfix (contains floats)",
        "inline-flex": "Inline flexbox container",
        "inline-grid": "Inline grid container",
        "table": "Table-like layout",
        "table-cell": "Table cell behavior",
        "table-row": "Table row behavior",
        "list-item": "Generates list marker",
    },
    # Flexbox
    "flex": {
        "1": "Grow to fill space",
        "none": "Fixed size",
        "0 0 auto": "Don't grow or shrink",
        "1 1 0%": "Flexible, start from zero",
        "1 1 auto": "Flexible, natural size",
    },
    "flex-direction": {
        "row": "Horizontal layout",
        "column": "Vertical layout",
        "row-reverse": "Reverse horizontal",
        "column-reverse": "Reverse vertical",
    },
    "flex-wrap": {
        "nowrap": "Single line",
        "wrap": "Allow wrapping",
        "wrap-reverse": "Wrap upward",
    },
    "flex-grow": {
        "0": "Cannot grow",
        "1": "Can grow",
    },
    "flex-shrink": {
        "0": "Cannot shrink",
        "1": "Can shrink",
    },
    "flex-basis": {
        "0": "Start from zero",
        "auto": "Natural size",
    },
    "align-items": {
        "center": "Center vertically",
        "flex-start": "Align to top",
        "flex-end": "Align to bottom",
        "stretch": "Fill container height",
        "baseline": "Align to text baseline",
    },
    "align-content": {
        "center": "Center vertically",
        "flex-start": "Pack to top",
        "flex-end": "Pack to bottom",
        "stretch": "Stretch to fill",
        "space-between": "Space between rows",
        "space-around": "Space around rows",
    },
    "align-self": {
        "auto": "Inherit from parent",
        "center": "Center this item",
        "flex-start": "Align to top",
        "flex-end": "Align to bottom",
        "stretch": "Fill container height",
    },
    "justify-content": {
        "center": "Center horizontally",
        "flex-start": "Align to start",
        "flex-end": "Align to end",
        "space-between": "Space between items",
        "space-around": "Space around items",
        "space-evenly": "Equal space distribution",
    },
    "justify-items": {
        "center": "Center items horizontally",
        "start": "Align items to start",
        "end": "Align items to end",
        "stretch": "Stretch items",
    },
    "place-items": {
        "center": "Center both directions",
        "start": "Start both directions",
        "stretch": "Stretch both directions",
    },
    # Grid
    "grid-column": {
        "span 2": "Span 2 columns",
        "span 3": "Span 3 columns",
        "1 / -1": "Full width",
    },
    "grid-row": {
        "span 2": "Span 2 rows",
        "span 3": "Span 3 rows",
        "1 / -1": "Full height",
    },
    "grid-template-columns": {
        "1fr 2fr": "1:2 ratio columns",
        "1fr 1fr": "Two equal columns",
        "1fr 1fr 1fr": "Three equal columns",
    },
    "grid-template-rows": {
        "auto 1fr auto": "Header, content, footer",
        "auto 1fr": "Header + content",
    },
    # Position
    "position": {
        "static": "Normal flow",
        "relative": "Relative to normal position",
        "absolute": "Relative to positioned ancestor",
        "fixed": "Relative to viewport",
        "sticky": "Sticky positioning",
    },
    "inset": {
        "0": "Fill positioned parent",
    },
    "top": {
        "0": "No offset from top",
        "auto": "Auto top positioning",
    },
    "bottom": {
        "0": "No offset from bottom",
        "auto": "Auto bottom positioning",
    },
    "left": {
        "0": "No offset from left",
        "auto": "Auto left positioning",
    },
    "right": {
        "0": "No offset from right",
        "auto": "Auto right positioning",
    },
    "z-index": {
        "-1": "Below default layer",
        "0": "Default layer",
        "1": "Above default layer",
        "auto": "Parent stacking context",
    },
    # Box Model
    "box-sizing": {
        "border-box": "Include padding/border in width",
        "content-box": "Exclude padding/border from width",
    },
    "margin": {
        "0": "No margin",
        "auto": "Center horizontally",
        "0 auto": "Center horizontally (no vertical margin)",
    },
    "margin-inline": {
        "auto": "Center horizontally (LTR/RTL aware)",
    },
    "padding": {
        "0": "No padding",
    },
    # Sizing
    "width": {
        "100%": "Full parent width",
        "100vw": "Full viewport width",
        "auto": "Natural width",
        "max-content": "Fit content width",
        "min-content": "Minimum content width",
        "fit-content": "Shrink to fit content",
    },
    "height": {
        "0": "Collapsed height",
        "100%": "Full parent height",
        "100vh": "Full viewport height",
        "100dvh": "Full dynamic viewport height",
        "100svh": "Full small viewport height",
        "100lvh": "Full large viewport height",
        "auto": "Natural height",
        "max-content": "Fit content height",
        "min-content": "Minimum content height",
    },
    "min-width": {
        "0": "No minimum width",
    },
    "min-height": {
        "100vh": "At least full viewport",
        "100dvh": "At least full dynamic viewport",
        "100svh": "At least full small viewport",
        "100lvh": "At least full large viewport",
        "0": "No minimum height",
    },
    "max-width": {
        "none": "No maximum width",
        "100%": "Don't exceed parent",
    },
    "max-height": {
        "none": "No maximum height",
    },
    # Typography
    "color": {
        "currentcolor": "Inherit text color",
        "transparent": "Invisible text",
        "inherit": "Inherit from parent",
    },
    "font-family": {
        "monospace": "System monospace (typically Courier New or Menlo)",
        "system-ui": "Platform UI font (San Francisco on macOS, Segoe UI on Windows, Roboto on Android)",
        "serif": "Browser default serif (typically Times New Roman)",
        "sans-serif": "Browser default sans-serif (typically Arial)",
        "cursive": "Cursive/handwriting style (varies by platform)",
        "fantasy": "Decorative style (varies by platform)",
        "inherit": "Inherit from parent",
    },
    "font-style": {
        "italic": "Italic text",
        "oblique": "Oblique (slanted) text",
        "normal": "Upright text",
    },
    "font-weight": {
        "100": "Thin weight",
        "200": "Extra-light weight",
        "300": "Light weight",
        "400": "Normal weight",
        "500": "Medium weight",
        "600": "Semi-bold weight",
        "700": "Bold weight",
        "800": "Extra-bold weight",
        "900": "Black weight",
        "normal": "Normal weight",
        "bold": "Bold weight",
    },
    "text-align": {
        "left": "Left aligned",
        "right": "Right aligned",
        "center": "Center aligned",
        "justify": "Justified text",
        "start": "Start aligned",
        "end": "End aligned",
    },
    "text-transform": {
        "uppercase": "ALL CAPS",
        "lowercase": "all lowercase",
        "capitalize": "Title Case",
        "none": "No transformation",
    },
    "white-space": {
        "nowrap": "No line breaks",
        "pre": "Preserve whitespace",
        "pre-wrap": "Preserve whitespace, wrap",
        "pre-line": "Collapse space, keep newlines",
        "normal": "Normal wrapping",
    },
    "word-break": {
        "break-all": "Break anywhere",
        "keep-all": "Keep words together",
        "normal": "Normal word breaks",
    },
    "overflow-wrap": {
        "break-word": "Break long words",
        "anywhere": "Break anywhere if needed",
    },
    "text-overflow": {
        "ellipsis": "Truncate with …",
        "clip": "Clip overflow",
    },
    "hyphens": {
        "auto": "Auto-hyphenate for word breaks",
        "manual": "Manual hyphenation",
        "none": "No hyphenation",
    },
    # Visual
    "opacity": {
        "0": "Fully transparent (invisible)",
        "0.1": "Almost invisible",
        "0.15": "Nearly invisible",
        "0.2": "Mostly transparent",
        "0.25": "Mostly transparent",
        "0.3": "Faint",
        "0.4": "Translucent",
        "0.5": "Semi-transparent",
        "0.6": "Partially transparent",
        "0.7": "Mostly visible",
        "0.75": "Mostly visible",
        "0.8": "Slightly transparent",
        "0.85": "Nearly opaque",
        "0.9": "Almost fully opaque",
        "0.95": "Barely transparent",
        "1": "Fully opaque",
    },
    "visibility": {
        "visible": "Element visible",
        "hidden": "Hidden but takes space",
        "collapse": "Collapsed (tables)",
    },
    "border-color": {
        "transparent": "Invisible border",
        "currentcolor": "Match text color",
    },
    "border-radius": {
        "50%": "Circle",
        "0": "No rounding",
    },
    "border-width": {
        "0": "No border",
        "1px": "Thin border",
    },
    # Overflow
    "overflow": {
        "visible": "Content can overflow",
        "hidden": "Hide overflow",
        "scroll": "Always show scrollbars",
        "auto": "Scrollbars when needed",
        "clip": "Clip without scrollbars",
    },
    "overflow-x": {
        "hidden": "Hide horizontal overflow",
        "auto": "Horizontal scroll when needed",
        "scroll": "Always horizontal scroll",
    },
    "overflow-y": {
        "hidden": "Hide vertical overflow",
        "auto": "Vertical scroll when needed",
        "scroll": "Always vertical scroll",
    },
    "scroll-behavior": {
        "smooth": "Smooth scrolling",
        "auto": "Instant scrolling",
    },
    "scroll-snap-align": {
        "start": "Snap to start",
        "center": "Snap to center",
        "end": "Snap to end",
    },
    # Interaction
    "cursor": {
        "pointer": "Clickable",
        "auto": "Default cursor",
        "text": "Text selection",
        "move": "Moveable",
        "grab": "Draggable",
        "grabbing": "Being dragged",
        "not-allowed": "Disabled",
        "wait": "Loading",
        "help": "Help available",
        "crosshair": "Precision selection",
        "default": "Arrow cursor",
        "none": "Hide cursor",
    },
    "pointer-events": {
        "none": "Not clickable",
        "auto": "Clickable",
    },
    "user-select": {
        "none": "Not selectable",
        "text": "Text selectable",
        "all": "Select all on click",
        "auto": "Default selection",
    },
    "touch-action": {
        "none": "Disable all touch gestures",
        "manipulation": "Allow pan/pinch, disable double-tap zoom",
        "auto": "All touch gestures",
        "pan-x": "Horizontal scroll only (no zoom)",
        "pan-y": "Vertical scroll only (no zoom)",
        "pinch-zoom": "Pinch zoom only",
        "pan-x pan-y": "Scroll both axes (no zoom)",
    },
    # Animation
    "animation-direction": {
        "alternate": "Back and forth",
        "reverse": "Play backwards",
        "alternate-reverse": "Back and forth (reversed)",
        "normal": "Play forward",
    },
    "animation-fill-mode": {
        "forwards": "Keep end state",
        "backwards": "Apply start state before",
        "both": "Both directions",
        "none": "No fill",
    },
    "animation-iteration-count": {
        "infinite": "Loop forever",
        "1": "Play once",
    },
    "animation-play-state": {
        "paused": "Pause animation",
        "running": "Play animation",
    },
    "transition-timing-function": {
        "ease": "Ease timing",
        "ease-in": "Start slow",
        "ease-out": "End slow",
        "ease-in-out": "Ease in-out",
        "linear": "Linear timing",
    },
    # Transform
    "transform-origin": {
        "center": "Transform around center",
        "top left": "Transform from top-left",
        "top right": "Transform from top-right",
        "bottom left": "Transform from bottom-left",
        "bottom right": "Transform from bottom-right",
    },
    # Background
    "background-size": {
        "cover": "Cover entire area",
        "contain": "Fit within area",
        "100% 100%": "Stretch to fill",
    },
    "background-position": {
        "center": "Center image",
        "top": "Top of container",
        "bottom": "Bottom of container",
        "top left": "Top-left corner",
        "top right": "Top-right corner",
        "0 0": "Top-left origin",
        "0px 0px": "Top-left origin",
        "0% 0%": "Top-left origin",
    },
    "background-repeat": {
        "no-repeat": "Single image",
        "repeat": "Tile image",
        "repeat-x": "Horizontal repeat",
        "repeat-y": "Vertical repeat",
    },
    "background-attachment": {
        "fixed": "Fixed during scroll",
        "scroll": "Scrolls with content",
        "local": "Scrolls with element",
    },
    # Object fit
    "object-fit": {
        "cover": "Cover container",
        "contain": "Fit within container",
        "fill": "Stretch to fill",
        "none": "Natural size",
        "scale-down": "Smaller of contain/none",
    },
    "object-position": {
        "center": "Center image",
        "top": "Top of container",
        "bottom": "Bottom of container",
    },
    # Outline
    "outline": {
        "none": "Remove outline (check a11y)",
        "0": "Remove outline (check a11y)",
    },
    "outline-width": {
        "0": "No outline (check focus visibility)",
    },
    # Container queries
    "container-type": {
        "inline-size": "Container query target (tracks width)",
        "size": "Container query target (tracks width + height)",
        "normal": "No container queries",
    },
    # Isolation
    "isolation": {
        "isolate": "New stacking context (z-index boundary)",
        "auto": "No stacking context",
    },
    # Will-change
    "will-change": {
        "transform": "GPU hint for transform animation",
        "opacity": "GPU hint for opacity animation",
        "auto": "No optimization hint",
        "scroll-position": "Optimize for scroll changes",
        "contents": "Optimize for content changes",
    },
    # Content visibility & containment
    "content-visibility": {
        "auto": "Skip rendering when off-screen (performance)",
        "hidden": "Hidden but state preserved (like off-screen)",
    },
    "contain": {
        "strict": "Full containment (size + layout + paint)",
        "content": "Layout + paint containment",
        "layout": "Isolate internal layout from page",
        "paint": "Clip descendants to element bounds",
        "size": "Size independent of children",
        "style": "Scope counters/quotes to element",
        "inline-size": "Inline size independent of children",
        "layout paint": "Isolate layout/paint from rest of page",
        "layout style paint": "Isolate layout/style/paint from page",
    },
    # Text rendering & fonts
    "text-rendering": {
        "optimizelegibility": "Better kerning, slower rendering",
        "optimizespeed": "Fastest rendering, no ligatures",
        "geometricprecision": "Precise scaling, no rounding",
    },
    "font-display": {
        "swap": "Show fallback, swap when loaded",
        "optional": "Use only if already cached",
        "block": "Hide text until font loads (3s)",
        "fallback": "Brief blank, then fallback font",
    },
    "appearance": {
        "none": "Remove native styling",
        "auto": "Native OS form styling",
        "textfield": "Style as text input (remove spinner)",
        "menulist-button": "Native dropdown button appearance",
    },
    "-webkit-appearance": {
        "none": "Remove native styling",
    },
    "-moz-appearance": {
        "none": "Remove native styling",
    },
    # Resize
    "resize": {
        "none": "Cannot resize",
        "both": "Resizable in both directions",
        "horizontal": "Resizable horizontally only",
        "vertical": "Resizable vertically only",
    },
    # Writing & direction
    "writing-mode": {
        "vertical-rl": "Vertical text, right-to-left",
        "horizontal-tb": "Horizontal text, top-to-bottom",
        "vertical-lr": "Vertical text, left-to-right",
        "sideways-rl": "Sideways text, right-to-left",
        "sideways-lr": "Sideways text, left-to-right",
    },
    "direction": {
        "rtl": "Right-to-left text",
        "ltr": "Left-to-right text",
    },
    # Table
    "table-layout": {
        "fixed": "Fixed column widths (faster)",
    },
    "border-collapse": {
        "collapse": "Merge cell borders",
    },
    # 3D & rendering
    "backface-visibility": {
        "hidden": "Hide back face (3D)",
    },
    "-webkit-font-smoothing": {
        "antialiased": "Thinner font rendering (macOS)",
    },
    "text-size-adjust": {
        "100%": "Prevent font boosting on mobile",
        "none": "Prevent mobile text inflation",
    },
    "-webkit-text-size-adjust": {
        "100%": "Prevent font boosting on mobile",
        "none": "Prevent mobile text inflation",
    },
    # Color scheme & accessibility
    "color-scheme": {
        "light dark": "Support both color schemes natively",
        "light": "Light mode only",
        "dark": "Dark mode only",
        "only light": "Force light mode, prevent dark override",
        "only dark": "Force dark mode, prevent light override",
    },
    "overscroll-behavior": {
        "none": "Prevent scroll chaining",
        "contain": "Prevent scroll chaining to parent",
        "auto": "Default scroll chaining",
    },
    "overscroll-behavior-y": {
        "none": "Prevent vertical scroll chaining",
        "contain": "Stop vertical scroll chaining",
    },
    "overscroll-behavior-x": {
        "none": "Prevent horizontal scroll chaining",
        "contain": "Stop horizontal scroll chaining",
    },
    "forced-color-adjust": {
        "none": "Opt out of Windows High Contrast recoloring",
        "auto": "Auto-adjust for High Contrast mode",
        "preserve-parent-color": "Inherit parent color in High Contrast",
    },
    # Text decoration & list
    "text-decoration": {
        "none": "No text decoration",
        "underline": "Underlined",
    },
    "list-style": {
        "none": "No list markers",
    },
    # All property (resets)
    "all": {
        "unset": "Reset all styles",
        "inherit": "Inherit all from parent",
        "initial": "Reset all to initial",
        "revert": "Revert all to browser default",
        "revert-layer": "Revert all to previous layer",
    },
    # Text wrapping
    "text-wrap": {
        "balance": "Balance line lengths (max ~6 lines)",
        "pretty": "Prevent orphaned words on last line",
        "stable": "Keep lines stable during editing",
        "nowrap": "Prevent text wrapping",
    },
    "text-wrap-style": {
        "balance": "Balance line lengths (max ~6 lines)",
        "pretty": "Prevent orphaned words on last line",
        "stable": "Keep lines stable during editing",
    },
    "text-wrap-mode": {
        "wrap": "Allow text wrapping",
        "nowrap": "Prevent text wrapping",
    },
    # Content
    "content": {
        "none": "No generated content",
        '""': "Empty pseudo-element (used for layout)",
        "''": "Empty pseudo-element (used for layout)",
        "open-quote": "Insert opening quotation mark",
        "close-quote": "Insert closing quotation mark",
        "no-open-quote": "Increment quote depth without content",
        "no-close-quote": "Decrement quote depth without content",
    },
    # Blend modes
    "mix-blend-mode": {
        "normal": "No blending",
        "multiply": "Darken by multiplying colors",
        "screen": "Lighten by screening colors",
        "overlay": "Darken darks, lighten lights",
        "darken": "Keep darkest color values",
        "lighten": "Keep lightest color values",
        "color-dodge": "Brighten with glowing effect",
        "color-burn": "Darken with increased contrast",
        "hard-light": "Intense overlay blending",
        "soft-light": "Subtle overlay blending",
        "difference": "High-contrast color inversion",
        "exclusion": "Low-contrast color inversion",
        "hue": "Use hue, keep base luminosity",
        "saturation": "Use saturation, keep base hue",
        "color": "Use hue+saturation, keep luminosity",
        "luminosity": "Use luminosity, keep base color",
        "plus-lighter": "Additive blending (lightens)",
    },
    "background-blend-mode": {
        "multiply": "Darken by multiplying bg layers",
        "screen": "Lighten by screening bg layers",
        "overlay": "Darken darks, lighten lights in bg",
    },
    # Font features
    "font-variant-numeric": {
        "ordinal": "Ordinal markers (1st, 2nd)",
        "slashed-zero": "Zero with slash (0 vs O)",
        "lining-nums": "Numbers aligned on baseline",
        "oldstyle-nums": "Numbers with descenders",
        "proportional-nums": "Varying-width numbers",
        "tabular-nums": "Equal-width numbers (for tables)",
        "diagonal-fractions": "Diagonal fraction glyphs",
        "stacked-fractions": "Stacked fraction glyphs",
    },
    "font-variant-ligatures": {
        "none": "Disable all ligatures",
        "common-ligatures": "Enable fi, fl ligatures",
        "no-common-ligatures": "Disable fi, fl ligatures",
        "discretionary-ligatures": "Enable decorative ligatures",
        "no-discretionary-ligatures": "Disable decorative ligatures",
        "contextual": "Enable contextual alternates",
        "no-contextual": "Disable contextual alternates",
    },
    "font-variant-caps": {
        "small-caps": "Small capitals",
        "all-small-caps": "All letters as small capitals",
        "petite-caps": "Petite capitals",
        "all-petite-caps": "All letters as petite capitals",
        "unicase": "Mix of small caps and normal",
        "titling-caps": "Capitals designed for titles",
    },
    "font-variant": {
        "none": "Disable all ligatures and features",
        "small-caps": "Small capitals",
        "all-small-caps": "All letters as small capitals",
    },
    # Image & shape
    "image-rendering": {
        "smooth": "Bilinear interpolation (photos)",
        "crisp-edges": "Sharp edges, no blurring",
        "pixelated": "Nearest-neighbor scaling (pixel art)",
    },
    "shape-outside": {
        "margin-box": "Wrap text around margin shape",
        "border-box": "Wrap text around border shape",
        "padding-box": "Wrap text around padding shape",
        "content-box": "Wrap text around content shape",
    },
    # Print & pagination
    "break-inside": {
        "avoid": "Prevent page/column breaks inside",
        "avoid-page": "Prevent page breaks inside",
        "avoid-column": "Prevent column breaks inside",
    },
    "page-break-inside": {
        "avoid": "Prevent page breaks inside",
    },
    "orphans": {
        "2": "Min 2 lines at page bottom (default)",
        "3": "Min 3 lines at page bottom",
    },
    "widows": {
        "2": "Min 2 lines at page top (default)",
        "3": "Min 3 lines at page top",
    },
    "print-color-adjust": {
        "economy": "Browser may strip colors for printing",
        "exact": "Preserve colors when printing",
    },
    "-webkit-print-color-adjust": {
        "economy": "Browser may strip colors for printing",
        "exact": "Preserve colors when printing",
    },
    # Text & bidi
    "text-orientation": {
        "mixed": "Rotate horizontal scripts, keep vertical",
        "upright": "Keep all characters upright",
        "sideways": "Lay out all characters sideways",
    },
    "unicode-bidi": {
        "isolate": "Isolate bidirectional text",
        "bidi-override": "Override bidirectional algorithm",
        "isolate-override": "Isolate + override bidi",
        "embed": "Embed bidirectional text",
        "plaintext": "Determine direction from content",
    },
    # Scroll snap
    "scroll-snap-type": {
        "none": "No scroll snapping",
        "x proximity": "Loose horizontal snap scrolling",
        "y proximity": "Loose vertical snap scrolling",
        "both mandatory": "Snap in both directions",
    },
    # Form styling
    "accent-color": {
        "auto": "Browser default accent color",
    },
    "caret-color": {
        "transparent": "Hide text cursor",
    },
    # Decoration & lists
    "text-decoration-style": {
        "solid": "Solid line",
        "double": "Double line",
        "dotted": "Dotted line",
        "dashed": "Dashed line",
        "wavy": "Wavy line (often = spelling error)",
    },
    "list-style-type": {
        "none": "No list marker",
        "disc": "Filled circle marker",
        "circle": "Hollow circle marker",
        "square": "Square marker",
        "decimal": "1, 2, 3…",
        "decimal-leading-zero": "01, 02, 03…",
        "lower-roman": "i, ii, iii…",
        "upper-roman": "I, II, III…",
        "lower-alpha": "a, b, c…",
        "upper-alpha": "A, B, C…",
        "disclosure-open": "Open disclosure triangle",
        "disclosure-closed": "Closed disclosure triangle",
    },
    # Tab size
    "tab-size": {
        "2": "2-space tab width",
        "4": "4-space tab width",
        "8": "8-space tab width (default)",
    },
    # Place content & items
    "place-content": {
        "center": "Center content both directions",
        "space-between": "Space between both directions",
        "space-around": "Space around both directions",
        "space-evenly": "Equal spacing both directions",
        "stretch": "Stretch content both directions",
    },
    "place-items": {
        "center": "Center both directions",
        "start": "Start both directions",
        "stretch": "Stretch both directions",
        "end": "End both directions",
        "baseline": "Align to text baseline",
    },
    # Grid auto sizing
    "grid-auto-rows": {
        "auto": "Rows size to content",
        "min-content": "Rows shrink to smallest content",
        "max-content": "Rows expand to largest content",
        "1fr": "Equal-height rows",
        "auto max-content": "Alternating: auto then max-content rows",
        "auto min-content": "Alternating: auto then min-content rows",
    },
    "grid-auto-columns": {
        "auto": "Columns size to content",
        "min-content": "Columns shrink to smallest content",
        "max-content": "Columns expand to largest content",
        "1fr": "Equal-width columns",
    },
    "grid-auto-flow": {
        "row": "Fill rows first",
        "column": "Fill columns first",
        "dense": "Fill gaps aggressively",
        "row dense": "Fill rows first, pack dense",
        "column dense": "Fill columns first, pack dense",
    },
    # Scroll snap
    "scroll-snap-stop": {
        "always": "Must stop at this snap point",
        "normal": "May skip this snap point",
    },
    # Modern CSS features
    "field-sizing": {
        "content": "Auto-grow to fit content",
        "fixed": "Fixed size (default)",
    },
    "interpolate-size": {
        "allow-keywords": "Enable transitions to/from auto",
    },
    "hanging-punctuation": {
        "first": "Hang opening quotes into margin",
        "last": "Hang closing punctuation into margin",
        "first last": "Hang opening and closing punctuation",
        "first force-end": "Hang opening quotes and stops",
        "allow-end": "Hang stops if they don't fit",
        "force-end": "Always hang stops into margin",
    },
    # Text underline from-font
    "text-underline-offset": {
        "auto": "Browser default underline offset",
        "from-font": "Use font's underline position",
    },
}


# =============================================================================
# GLOBAL VALUE COMMENTS
# =============================================================================
# These CSS keywords apply to ANY property and have the same meaning everywhere.
# Checked before property-specific comments.

GLOBAL_VALUE_COMMENTS: dict[str, str] = {
    "inherit": "Use parent's value",
    "initial": "Use initial value",
    "unset": "Remove all declarations",
    "revert": "Use browser default",
    "revert-layer": "Revert to previous cascade layer",
}


# =============================================================================
# PATTERN COMMENTS
# =============================================================================
# Format: (property_regex, value_regex, comment_template)
# Use {0}, {1}, etc. for captured groups from value_regex
# Patterns are checked in order; first match wins

PATTERN_COMMENTS: list[tuple[str, str, str]] = [
    # Gap values
    (r"^gap$", r"^(\d+(?:\.\d+)?)(rem|px|em)$", "{0}{1} gap"),
    (r"^column-gap$", r"^(\d+(?:\.\d+)?)(rem|px|em)$", "{0}{1} horizontal gap"),
    (r"^row-gap$", r"^(\d+(?:\.\d+)?)(rem|px|em)$", "{0}{1} vertical gap"),
    # Grid auto rows/columns
    (r"^grid-auto-rows$", r"^minmax\((\d+(?:\.\d+)?)(px|rem),\s*(auto|1fr|max-content)\)$", "Rows min {0}{1}, grow to {2}"),
    (r"^grid-auto-columns$", r"^minmax\((\d+(?:\.\d+)?)(px|rem),\s*(auto|1fr|max-content)\)$", "Columns min {0}{1}, grow to {2}"),
    # Grid template columns
    (r"^grid-template-columns$", r"repeat\((\d+),\s*1fr\)", "{0} equal columns"),
    (r"^grid-template-columns$", r"repeat\(auto-fill,\s*minmax\((\d+(?:\.\d+)?)(px|rem),\s*1fr\)\)", "Auto-fill grid, min {0}{1} per column"),
    (r"^grid-template-columns$", r"repeat\(auto-fit,\s*minmax\((\d+(?:\.\d+)?)(px|rem),\s*1fr\)\)", "Auto-fit grid, min {0}{1} per column (collapses empty)"),
    (r"^grid-template-columns$", r"^minmax\((\d+(?:\.\d+)?)(px|rem),\s*(\d+(?:\.\d+)?)(px|rem)\)\s+1fr$", "{0}{1}\u2013{2}{3} sidebar + flexible main"),
    (r"^grid-template-columns$", r"^(\d+(?:\.\d+)?)(px|rem)\s+1fr$", "{0}{1} fixed + flexible"),
    (r"^grid-column$", r"^span\s+(\d+)$", "Span {0} columns"),
    (r"^grid-row$", r"^span\s+(\d+)$", "Span {0} rows"),
    # Grid area — named area (simple identifier, no slashes/digits-only)
    (r"^grid-area$", r"^([a-zA-Z][\w-]*)$", 'Placed in "{0}" grid area'),
    # Border radius (single-value patterns; multi-value handled by SPECIAL_HANDLERS)
    (r"^border-radius$", r"^(\d+(?:\.\d+)?)(px|rem|em)$", "{0}{1} rounded corners"),
    # Logical padding (not handled by SPECIAL_HANDLERS)
    (r"^padding-block$", r"^(\d+(?:\.\d+)?)(px|rem|em)$", "{0}{1} vertical padding"),
    (r"^padding-inline$", r"^(\d+(?:\.\d+)?)(px|rem|em)$", "{0}{1} horizontal padding"),
    # Position offsets
    (r"^(top|bottom)$", r"^(\d+(?:\.\d+)?)(px|rem|em|%)$", "{1}{2} from top/bottom"),
    (r"^(left|right)$", r"^(\d+(?:\.\d+)?)(px|rem|em|%)$", "{1}{2} from left/right"),
    # Z-index (4+ digits = very high)
    (r"^z-index$", r"^(\d{4,})$", "Layer {0} (very high)"),
    (r"^z-index$", r"^(\d+)$", "Layer {0}"),
    (r"^z-index$", r"^-(\d+)$", "Layer -{0} (below)"),
    # Font size
    (r"^font-size$", r"^(\d+(?:\.\d+)?)(rem)$", "{0}rem relative to root"),
    (r"^font-size$", r"^(\d+(?:\.\d+)?)(em)$", "{0}em relative to parent"),
    (r"^font-size$", r"^(\d+(?:\.\d+)?)(vw)$", "{0}vw viewport width"),
    (r"^font-size$", r"^(\d+(?:\.\d+)?)(px)$", "{0}px font"),
    # Line height
    (r"^line-height$", r"^(\d+(?:\.\d+)?)$", "{0}x line height"),
    # Letter/word spacing
    (r"^letter-spacing$", r"^(\d+(?:\.\d+)?)(em)$", "{0}em letter spacing"),
    (r"^letter-spacing$", r"^-(\d+(?:\.\d+)?)(em)$", "-{0}em tight spacing"),
    (r"^word-spacing$", r"^(\d+(?:\.\d+)?)(em)$", "{0}em word spacing"),
    # Aspect ratio
    (r"^aspect-ratio$", r"^auto\s+(\d+)\s*/\s*(\d+)$", "Intrinsic ratio, fallback {0}:{1}"),
    (r"^aspect-ratio$", r"^(\d+)\s*/\s*(\d+)$", "{0}:{1} aspect ratio"),
    (r"^aspect-ratio$", r"^(\d+(?:\.\d+)?)$", "{0}:1 aspect ratio"),
    # Scroll offsets (for sticky headers)
    (r"^scroll-margin-top$", r"^(\d+(?:\.\d+)?)(px|rem|em)$", "{0}{1} scroll offset (e.g. for sticky header)"),
    (r"^scroll-padding-top$", r"^(\d+(?:\.\d+)?)(px|rem|em)$", "{0}{1} scroll snap offset (e.g. for sticky header)"),
    # Animation range (scroll-driven)
    (r"^animation-range$", r"^entry\s+(\d+)%\s+exit\s+(\d+)%$", "Animate between {0}% entered and {1}% exited"),
    # Max/min dimensions
    (r"^max-height$", r"^(\d+(?:\.\d+)?)(vh)$", "Max {0}% of viewport height"),
    (r"^max-width$", r"^(\d+(?:\.\d+)?)(vw)$", "Max {0}% of viewport width"),
    (r"^max-width$", r"^(\d+(?:\.\d+)?)(px|rem|em)$", "Max {0}{1} width"),
    # Animation/transition timing
    (r"^animation-duration$", r"^(\d+(?:\.\d+)?)(s|ms)$", "{0}{1} duration"),
    (r"^animation-delay$", r"^(\d+(?:\.\d+)?)(s|ms)$", "{0}{1} delay"),
    (r"^transition-duration$", r"^(\d+(?:\.\d+)?)(s|ms)$", "{0}{1} duration"),
    (r"^transition-delay$", r"^(\d+(?:\.\d+)?)(s|ms)$", "{0}{1} delay"),
    (r"^transition$", r"^all\s+(\d+(?:\.\d+)?)(s)$", "Smooth {0}s transition"),
    (r"^transition$", r"^opacity\s+(\d+(?:\.\d+)?)(s)$", "{0}s fade transition"),
    (r"^transition$", r"^transform\s+(\d+(?:\.\d+)?)(s)$", "{0}s transform transition"),
    # Transform
    (r"^transform$", r"rotate\((\d+(?:\.\d+)?)deg\)", "Rotate {0} degrees"),
    (r"^transform$", r"rotate\(-(\d+(?:\.\d+)?)deg\)", "Rotate -{0} degrees"),
    (r"^transform$", r"scale\((\d+(?:\.\d+)?)\)", "Scale {0}x"),
    (r"^transform$", r"translateX\((\d+(?:\.\d+)?)(px|rem|%)\)", "Move {0}{1} right"),
    (r"^transform$", r"translateX\(-(\d+(?:\.\d+)?)(px|rem|%)\)", "Move {0}{1} left"),
    (r"^transform$", r"translateY\((\d+(?:\.\d+)?)(px|rem|%)\)", "Move {0}{1} down"),
    (r"^transform$", r"translateY\(-(\d+(?:\.\d+)?)(px|rem|%)\)", "Move {0}{1} up"),
    # Filter
    (r"^filter$", r"blur\((\d+(?:\.\d+)?)(px)\)", "{0}px blur"),
    (r"^filter$", r"brightness\((\d+(?:\.\d+)?)\)", "{0}x brightness"),
    (r"^filter$", r"contrast\((\d+(?:\.\d+)?)\)", "{0}x contrast"),
    (r"^filter$", r"grayscale\(100%\)", "Grayscale"),
    (r"^filter$", r"grayscale\((\d+)%\)", "{0}% grayscale"),
    (r"^backdrop-filter$", r"blur\((\d+(?:\.\d+)?)(px)\)", "{0}px background blur"),
    # Outline offset
    (r"^outline-offset$", r"^(\d+(?:\.\d+)?)(px)$", "{0}px offset"),
    # Scroll snap
    (r"^scroll-snap-type$", r"^x\s+mandatory$", "Horizontal snap scrolling"),
    (r"^scroll-snap-type$", r"^y\s+mandatory$", "Vertical snap scrolling"),
    # Text decoration
    (r"^text-decoration$", r"line-through", "Strikethrough"),
    # Box shadow with inset
    (r"^box-shadow$", r"^inset\s+", "Inner shadow"),
    # Counters
    (r"^counter-reset$", r"reversed\(([^)]+)\)", "Reversed counter '{0}' (counts down)"),
    (r"^counter-reset$", r"list-item\s+(\d+)", "Restart list numbering at {0}"),
    (r"^counter-reset$", r"^(\w[\w-]*)\s*$", "Initialize counter '{0}' to 0"),
    (r"^counter-increment$", r"^(\w[\w-]*)\s*$", "Increment counter '{0}'"),
    (r"^counter-increment$", r"^(\w[\w-]*)\s+(\d+)$", "Increment counter '{0}' by {1}"),
    # Content with counters/attr
    (r"^content$", r"counter\(([^)]+)\)", "Display counter '{0}'"),
    (r"^content$", r"counters\(([^,]+)", "Display nested counter '{0}'"),
    (r"^content$", r"attr\(([^)]+)\)", "Display attribute '{0}'"),
    # Clip-path shapes
    (r"^clip-path$", r"^inset\(50%\)$", "Clip to nothing (visually hidden pattern)"),
    (r"^clip-path$", r"^inset\(", "Rectangular clip"),
    (r"^clip-path$", r"^circle\(", "Circular clip"),
    (r"^clip-path$", r"^ellipse\(", "Elliptical clip"),
    (r"^clip-path$", r"^polygon\(", "Polygonal clip shape"),
    (r"^clip-path$", r"^path\(", "SVG path clip"),
    # Shape-outside
    (r"^shape-outside$", r"^circle\(", "Wrap text around circle"),
    (r"^shape-outside$", r"^ellipse\(", "Wrap text around ellipse"),
    (r"^shape-outside$", r"^polygon\(", "Wrap text around polygon"),
    (r"^shape-outside$", r"url\(", "Wrap text around image shape"),
    # Mask
    (r"^mask-image$", r"url\(", "Image mask"),
    (r"^mask-image$", r"linear-gradient\(", "Gradient mask (fade effect)"),
    # CSS functions (match ANY property — clamp() handled by _describe_clamp)
    (r".", r"(?<!-)env\(safe-area-inset-", "Safe area for device notch/rounded corners"),
    (r".", r"env\(keyboard-inset-", "Virtual keyboard inset"),
    (r".", r"env\(titlebar-area-", "PWA title bar area"),
    # Font features (OpenType tags)
    (r"^font-feature-settings$", r'"liga"\s*0', "Disable standard ligatures"),
    (r"^font-feature-settings$", r'"kern"\s*0', "Disable kerning"),
    (r"^font-feature-settings$", r'"smcp"', "Small capitals (OpenType)"),
    (r"^font-feature-settings$", r'"c2sc"', "Capitals to small caps"),
    (r"^font-feature-settings$", r'"onum"', "Oldstyle (text) figures"),
    (r"^font-feature-settings$", r'"lnum"', "Lining (uppercase) figures"),
    (r"^font-feature-settings$", r'"tnum"', "Tabular (monospaced) figures"),
    (r"^font-feature-settings$", r'"pnum"', "Proportional figures"),
    (r"^font-feature-settings$", r'"frac"', "Automatic fractions"),
    (r"^font-feature-settings$", r'"zero"', "Slashed zero"),
    (r"^font-feature-settings$", r'"swsh"', "Swash characters"),
    (r"^font-feature-settings$", r'"ss(\d{2})"', "Stylistic set {0}"),
    # Column layout
    (r"^column-count$", r"^(\d+)$", "{0}-column layout"),
    # Visually hidden patterns
    (r"^clip$", r"rect\(\s*[01]px", "Visually hidden (screen reader only)"),
    # Underline offset
    (r"^text-underline-offset$", r"^(\d+(?:\.\d+)?)(px|em|rem)$", "{0}{1} underline offset"),
    # Orphans/widows dynamic
    (r"^orphans$", r"^(\d+)$", "Min {0} lines at page bottom"),
    (r"^widows$", r"^(\d+)$", "Min {0} lines at page top"),
    # Tab size dynamic
    (r"^tab-size$", r"^(\d+)$", "{0}-space tab width"),
    # Custom list marker string
    (r"^list-style-type$", r'^"([^"]+)"$', 'Custom list marker: "{0}"'),
    # var() fallback — must be LAST so property-specific patterns take priority
    (r".", r"var\(--([^,)]+)", "Uses --{0}"),
]


# =============================================================================
# TIP EXAMPLES
# =============================================================================
# Curated (property, value) pairs for CLI tips - comments looked up from EXACT_COMMENTS

TIP_EXAMPLE_KEYS: list[tuple[str, str]] = [
    ("flex-direction", "column"),
    ("flex-shrink", "0"),
    ("visibility", "hidden"),
    ("touch-action", "none"),
    ("animation-iteration-count", "infinite"),
    ("isolation", "isolate"),
    ("box-sizing", "border-box"),
    ("border-radius", "50%"),
    ("text-transform", "uppercase"),
    ("width", "100vw"),
]


def get_random_tip_example() -> tuple[str, str, str]:
    """
    Get a random example for use in CLI tips.

    Returns:
        Tuple of (property, value, comment)
    """
    prop, value = random.choice(TIP_EXAMPLE_KEYS)
    comment = EXACT_COMMENTS[prop][value]
    return (prop, value, comment)


# =============================================================================
# SPECIAL HANDLERS
# =============================================================================
# Functions that generate comments for properties needing richer logic than
# exact matches or simple regex patterns can provide.

# CSS value token regex — matches a single token like "8px", "1rem", "0", "-4px"
_VALUE_TOKEN_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:px|rem|em|%|vw|vh)?$|^0$")


def _describe_opacity(prop: str, value: str) -> str | None:
    """Natural language description for arbitrary opacity values."""
    try:
        f = float(value)
    except ValueError:
        return None
    if f < 0 or f > 1:
        return None
    if f == 0:
        return "Fully transparent (invisible)"
    if f <= 0.15:
        return "Almost invisible"
    if f <= 0.25:
        return "Mostly transparent"
    if f <= 0.35:
        return "Faint"
    if f <= 0.45:
        return "Translucent"
    if f <= 0.55:
        return "Semi-transparent"
    if f <= 0.65:
        return "Partially transparent"
    if f <= 0.75:
        return "Mostly visible"
    if f <= 0.85:
        return "Slightly transparent"
    if f <= 0.9:
        return "Nearly opaque"
    if f < 1:
        return "Almost fully opaque"
    return "Fully opaque"


def _describe_trbl_shorthand(prop: str, value: str) -> str | None:
    """Describe margin/padding/border-width/inset TRBL shorthands in natural language."""
    # Bail on functions like calc(), var(), env()
    if "(" in value:
        return None

    tokens = value.split()
    if not tokens or len(tokens) > 4:
        return None

    # Bail if any token contains 'auto' or isn't a simple value
    for t in tokens:
        if t == "auto" or not _VALUE_TOKEN_RE.match(t):
            return None

    # Expand shorthand to [top, right, bottom, left]
    if len(tokens) == 1:
        top = right = bottom = left = tokens[0]
    elif len(tokens) == 2:
        top = bottom = tokens[0]
        right = left = tokens[1]
    elif len(tokens) == 3:
        top = tokens[0]
        right = left = tokens[1]
        bottom = tokens[2]
    else:
        top, right, bottom, left = tokens

    sides = [top, right, bottom, left]
    labels = ["top", "right", "bottom", "left"]

    # All zeros → let exact match handle it (e.g., "No margin")
    if all(s == "0" for s in sides):
        return None

    # All same value
    if top == right == bottom == left:
        return f"{top} on all sides"

    # Property-specific suffix for single-side descriptions
    suffix_map = {
        "margin": " margin",
        "padding": " padding",
        "border-width": " border",
        "inset": " offset",
    }
    suffix = suffix_map.get(prop, "")

    # Count non-zero sides
    non_zero = [(labels[i], sides[i]) for i in range(4) if sides[i] != "0"]

    # Single non-zero side → "8px right margin"
    if len(non_zero) == 1:
        label, val = non_zero[0]
        return f"{val} {label}{suffix}"

    # Symmetric pairs
    tb_same = top == bottom
    lr_same = right == left

    if tb_same and lr_same:
        # Both pairs match but differ from each other
        parts = []
        if top != "0":
            parts.append(f"{top} top/bottom")
        if right != "0":
            parts.append(f"{right} left/right")
        if not parts:
            return None
        return ", ".join(parts)

    # Top/bottom same, left and right differ (or vice versa)
    # Build individual side descriptions, collapsing equal pairs
    part_groups: list[str] = []

    if tb_same and top != "0":
        part_groups.append(f"{top} top/bottom")
    elif not tb_same:
        if top != "0":
            part_groups.append(f"{top} top")
        if bottom != "0":
            part_groups.append(f"{bottom} bottom")

    if lr_same and right != "0":
        part_groups.append(f"{right} left/right")
    elif not lr_same:
        if right != "0":
            part_groups.append(f"{right} right")
        if left != "0":
            part_groups.append(f"{left} left")

    if not part_groups:
        return None

    # If we'd list all 4 individually, use the explicit order
    if len(part_groups) >= 4 or (not tb_same and not lr_same and len(non_zero) == 4):
        return f"{top} top, {right} right, {bottom} bottom, {left} left"

    return ", ".join(part_groups)


_CORNER_LABELS = ["top-left", "top-right", "bottom-right", "bottom-left"]


def _describe_border_radius(prop: str, value: str) -> str | None:
    """Describe border-radius with corner names."""
    # Bail on slash syntax (elliptical radii) and functions
    if "/" in value or "(" in value:
        return None

    tokens = value.split()
    if len(tokens) < 2 or len(tokens) > 4:
        return None

    # Bail if tokens aren't simple values
    for t in tokens:
        if not _VALUE_TOKEN_RE.match(t):
            return None

    # Expand shorthand to 4 corners
    if len(tokens) == 2:
        corners = [tokens[0], tokens[1], tokens[0], tokens[1]]
    elif len(tokens) == 3:
        corners = [tokens[0], tokens[1], tokens[2], tokens[1]]
    else:
        corners = list(tokens)

    # All same → fall through to pattern "Xpx rounded corners"
    if len(set(corners)) == 1:
        return None

    non_zero = [(i, corners[i]) for i in range(4) if corners[i] != "0"]
    if not non_zero:
        return None

    # All non-zero corners have the same value
    values = {v for _, v in non_zero}
    if len(values) == 1:
        val = non_zero[0][1]
        corner_names = "/".join(_CORNER_LABELS[i] for i, _ in non_zero)
        if len(non_zero) == 1:
            return f"{val} {corner_names} only"
        return f"{val} {corner_names}"

    # Different values per corner — list them all
    parts = [f"{corners[i]} {_CORNER_LABELS[i]}" for i in range(4) if corners[i] != "0"]
    return ", ".join(parts)


# =============================================================================
# FONT-FAMILY HANDLER (generic families + Google Fonts detection)
# =============================================================================

# Descriptions for CSS generic font families and well-known system fonts
_FONT_FAMILY_COMMENTS: dict[str, str] = {
    # CSS generic families
    "system-ui": "Platform UI font (San Francisco on macOS, Segoe UI on Windows, Roboto on Android)",
    "ui-serif": "Platform serif (New York on macOS, Georgia on Windows)",
    "ui-sans-serif": "Platform sans-serif (San Francisco on macOS, Segoe UI on Windows)",
    "ui-monospace": "Platform monospace (SF Mono on macOS, Cascadia Mono on Windows)",
    "ui-rounded": "Platform rounded (SF Pro Rounded on macOS)",
    "serif": "Browser default serif (typically Times New Roman)",
    "sans-serif": "Browser default sans-serif (typically Arial)",
    "monospace": "System monospace (typically Courier New or Menlo)",
    "cursive": "Cursive/handwriting style (varies by platform)",
    "fantasy": "Decorative style (varies by platform)",
    "math": "Math typesetting font",
    "emoji": "System emoji font",
    "fangsong": "Chinese fangsong typeface style",
    # Legacy system font keywords (pre-system-ui era)
    "-apple-system": "Apple system font (legacy, prefer system-ui)",
    "blinkmacsystemfont": "Chrome system font on macOS (legacy, prefer system-ui)",
}


def _extract_first_font_family(value: str) -> str:
    """Extract the first font family name from a CSS font-family value."""
    first = value.split(",")[0].strip()
    # Strip quotes
    if (first.startswith('"') and first.endswith('"')) or \
       (first.startswith("'") and first.endswith("'")):
        first = first[1:-1]
    return first


def _describe_font_family(_prop: str, value: str) -> str | None:
    """Describe font families: generic CSS families, system fonts, and Google Fonts."""
    name = _extract_first_font_family(value)
    if not name:
        return None

    name_lower = name.lower()

    # Check generic/system font families first
    if name_lower in _FONT_FAMILY_COMMENTS:
        return _FONT_FAMILY_COMMENTS[name_lower]

    # Check Google Fonts
    from inspekt.data import load_google_fonts
    fonts = load_google_fonts()
    original = fonts.get(name_lower)
    if original:
        encoded = original.replace(" ", "+")
        return f"Source: https://fonts.google.com/specimen/{encoded}"

    return None


# =============================================================================
# VALUE-LEVEL HANDLERS (apply to any property)
# =============================================================================

_CLAMP_RE = re.compile(r"clamp\((.+)\)", re.IGNORECASE)

_VIEWPORT_UNITS: dict[str, str] = {
    "vw": "% of viewport width",
    "vh": "% of viewport height",
    "cqi": "% of container inline size",
    "cqb": "% of container block size",
}


def _describe_clamp_value(raw: str) -> str:
    """Describe a single clamp() argument with unit-aware semantics."""
    val = raw.strip()

    # calc(...) → just say "calculated value"
    if val.startswith("calc("):
        return "calculated value"

    # Pure numeric + viewport/container unit (e.g. "5vw", "3cqi")
    for unit, desc in _VIEWPORT_UNITS.items():
        m = re.match(rf"^(\d+(?:\.\d+)?){unit}$", val, re.IGNORECASE)
        if m:
            return f"{m.group(1)}{desc}"

    # Anything else (compound like "2vw + 0.5rem", plain "50%", "1rem") → keep as-is
    return val


def _describe_clamp(_prop: str, value: str) -> str | None:
    """Describe clamp() with semantic unit descriptions."""
    m = _CLAMP_RE.search(value)
    if not m:
        return None

    inner = m.group(1)

    # Split on top-level commas (respecting nested parens)
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in inner:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    parts.append("".join(current).strip())

    if len(parts) != 3:
        return None

    min_val, pref_val, max_val = parts
    pref_desc = _describe_clamp_value(pref_val)
    return f"Fluid: {pref_desc}, min {min_val}, max {max_val}"


def _describe_grid_template(_prop: str, value: str) -> str | None:
    """Describe grid-template shorthand with named areas."""
    # Look for quoted area names like "header" "main" "footer"
    area_names = re.findall(r'"([^"]+)"', value)
    if not area_names:
        return None

    count = len(area_names)

    # Check for column definition after /
    col_part = ""
    if "/" in value:
        col_section = value.split("/", 1)[1].strip()
        col_part = f", columns: {col_section}"

    areas_str = ", ".join(f'"{a}"' for a in area_names)
    return f"{count}-row named grid ({areas_str}){col_part}"


SPECIAL_HANDLERS: dict[str, Callable[[str, str], str | None]] = {
    "margin": _describe_trbl_shorthand,
    "padding": _describe_trbl_shorthand,
    "border-width": _describe_trbl_shorthand,
    "inset": _describe_trbl_shorthand,
    "border-radius": _describe_border_radius,
    "opacity": _describe_opacity,
    "font-family": _describe_font_family,
    "grid-template": _describe_grid_template,
}


# =============================================================================
# COMPILED PATTERNS CACHE
# =============================================================================

@lru_cache(maxsize=1)
def _get_compiled_patterns() -> list[tuple[Pattern, Pattern, str]]:
    """Compile all pattern regexes for faster matching."""
    compiled = []
    for prop_pattern, value_pattern, template in PATTERN_COMMENTS:
        compiled.append((
            re.compile(prop_pattern, re.IGNORECASE),
            re.compile(value_pattern, re.IGNORECASE),
            template,
        ))
    return compiled


# =============================================================================
# PUBLIC API
# =============================================================================

def get_property_comment(prop: str, value: str) -> str | None:
    """
    Get a heuristic comment for a CSS property-value pair.

    Args:
        prop: CSS property name (e.g., "display", "border-radius")
        value: CSS property value (e.g., "flex", "8px")

    Returns:
        Human-readable comment string, or None if no comment available

    Examples:
        >>> get_property_comment("display", "flex")
        "Flexbox container"
        >>> get_property_comment("border-radius", "8px")
        "8px rounded corners"
        >>> get_property_comment("margin", "inherit")
        "Use parent's value"
        >>> get_property_comment("unknown", "value")
        None
    """
    # Normalize inputs
    prop_lower = prop.lower().strip()
    value_normalized = value.strip()
    value_lower = value_normalized.lower()

    # Check global CSS keywords first (apply to any property)
    if value_lower in GLOBAL_VALUE_COMMENTS:
        return GLOBAL_VALUE_COMMENTS[value_lower]

    # Try exact match (fast O(1) lookup)
    if prop_lower in EXACT_COMMENTS:
        prop_values = EXACT_COMMENTS[prop_lower]
        if value_lower in prop_values:
            return prop_values[value_lower]

    # Try special handlers (rich logic for TRBL shorthands, opacity, etc.)
    if prop_lower in SPECIAL_HANDLERS:
        result = SPECIAL_HANDLERS[prop_lower](prop_lower, value_normalized)
        if result:
            return result

    # Try value-level functions (clamp, etc. — apply to any property)
    clamp_result = _describe_clamp(prop_lower, value_normalized)
    if clamp_result:
        return clamp_result

    # Try pattern matching (slower, but supports dynamic values)
    for prop_regex, value_regex, template in _get_compiled_patterns():
        if prop_regex.match(prop_lower):
            value_match = value_regex.search(value_normalized)
            if value_match:
                # Format template with captured groups
                groups = value_match.groups()
                try:
                    return template.format(*groups)
                except (IndexError, KeyError):
                    # Template has more placeholders than captured groups
                    return template

    return None


def merge_comments(existing: str | None, heuristic: str | None) -> str | None:
    """
    Merge an existing comment with a heuristic comment.

    Args:
        existing: Existing comment text (may be None)
        heuristic: Heuristic comment to add (may be None)

    Returns:
        Merged comment string, or None if both are None

    Examples:
        >>> merge_comments("White", "Invisible text")
        "White, Invisible text"
        >>> merge_comments("White", None)
        "White"
        >>> merge_comments(None, "Flexbox container")
        "Flexbox container"
    """
    if not heuristic:
        return existing
    if not existing:
        return heuristic

    # Avoid duplicates (case-insensitive check)
    if heuristic.lower() in existing.lower():
        return existing
    if existing.lower() in heuristic.lower():
        return heuristic

    return f"{existing}, {heuristic}"


# =============================================================================
# SELECTOR COMMENTS
# =============================================================================
# Format: (selector_regex, comment)
# Checked against the full selector string (before the opening brace)

SELECTOR_COMMENTS: list[tuple[str, str]] = [
    # Accessibility patterns
    (r"\.sr-only\b", "Content for screen readers only"),
    (r"\.visually-hidden\b", "Content for screen readers only"),
    (r"\.screen-reader-text\b", "Content for screen readers only"),
    (r"\.a11y-hidden\b", "Content for screen readers only"),
    (r"\.skip-link\b", "Skip navigation link for keyboard users"),
    (r"\.skip-to-content\b", "Skip navigation link for keyboard users"),
    (r"\.skip-to-main\b", "Skip navigation link for keyboard users"),
    # Clearfix
    (r"\.clearfix\b", "Contains floated children"),
    # Media queries (at-rule context)
    (r"prefers-reduced-motion", "Respects motion sensitivity preference"),
    (r"prefers-color-scheme:\s*dark", "Dark mode styles"),
    (r"prefers-color-scheme:\s*light", "Light mode styles"),
    (r"prefers-contrast", "Respects contrast preference"),
    (r"forced-colors", "Windows High Contrast mode"),
    # Common utility classes
    (r"\.container\b", "Content width constraint"),
    (r"\.wrapper\b", "Content width constraint"),
    # Focus patterns
    (r":focus-visible\b", "Keyboard-only focus indicator"),
    (r":focus-within\b", "Parent has focused descendant"),
    # Pseudo-elements
    (r"::before\b", "Generated content before element"),
    (r"::after\b", "Generated content after element"),
    (r"::placeholder\b", "Input placeholder text styling"),
    (r"::selection\b", "Text selection styling"),
    (r"::marker\b", "List marker styling"),
    (r"::first-line\b", "First line of text block"),
    (r"::first-letter\b", "Drop cap / initial letter"),
    (r"::backdrop\b", "Fullscreen/dialog/popover background overlay"),
    (r"::view-transition", "View transition animation"),
    # State patterns
    (r":disabled\b", "Disabled state"),
    (r":checked\b", "Checked state (checkbox/radio)"),
    (r":required\b", "Required form field"),
    (r":invalid\b", "Invalid form input"),
    (r":valid\b", "Valid form input"),
    (r":empty\b", "Element with no children"),
    (r":not\(", "Negation selector"),
    (r":has\(", "Parent selector (has matching descendant)"),
    (r":is\(", "Matches any of the listed selectors"),
    (r":where\(", "Zero-specificity version of :is()"),
    (r":nth-child\(", "Positional child selector"),
    (r":popover-open\b", "Popover in open state"),
    # Modern at-rules
    (r"@container\b", "Container query (responsive to parent)"),
    (r"@layer\b", "Cascade layer declaration"),
    (r"@starting-style\b", "Entry animation initial state"),
]


@lru_cache(maxsize=1)
def _get_compiled_selector_patterns() -> list[tuple[Pattern, str]]:
    """Compile all selector pattern regexes for faster matching."""
    return [
        (re.compile(pattern, re.IGNORECASE), comment)
        for pattern, comment in SELECTOR_COMMENTS
    ]


def get_selector_comment(selector: str) -> str | None:
    """
    Get a comment for a CSS selector if it matches a known pattern.

    Args:
        selector: CSS selector string (e.g., ".sr-only", "::before")

    Returns:
        Human-readable comment string, or None if no comment available

    Examples:
        >>> get_selector_comment(".sr-only")
        "Content for screen readers only"
        >>> get_selector_comment("::before")
        "Generated content before element"
        >>> get_selector_comment("div.unknown")
        None
    """
    for pattern, comment in _get_compiled_selector_patterns():
        if pattern.search(selector):
            return comment
    return None
