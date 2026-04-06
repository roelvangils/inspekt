#!/usr/bin/env python3
"""
Build script for minifying Axe popover CSS.

This script concatenates the modular CSS files from inspekt/scripts/axe-popover/
and minifies them into a single string that can be embedded in run_axe.js and run_ibm.js.

Usage:
    python scripts/build_popover_css.py          # Show minified CSS output
    python scripts/build_popover_css.py --apply  # Update run_axe.js and run_ibm.js

CSS Source Files (in order):
    1. tokens.css    - Design tokens (colors, spacing, fonts)
    2. base.css      - Popover base structure
    3. nav.css       - Navigation bar styles
    4. content.css   - Content sections and details
    5. badges.css    - Badge styles (basic - full badge CSS is inline)
    6. animations.css - Entry/exit animations
    7. themes.css    - Dark mode support

Note: Badge styles (.inspekt-badge with impact colors) are handled separately
in each script because they require extensive !important declarations to
override page styles.
"""

import re
import sys
from pathlib import Path


def minify_css(css: str) -> str:
    """
    Simple CSS minifier that preserves functionality.

    This handles:
    - Removing comments
    - Removing unnecessary whitespace
    - Preserving escape sequences like \\25B6 (triangles) and \\2192 (arrows)
    - Escaping backslashes for JavaScript template strings
    """
    # Remove CSS comments (/* ... */)
    css = re.sub(r'/\*[\s\S]*?\*/', '', css)

    # Remove newlines and excessive whitespace
    css = re.sub(r'\s+', ' ', css)

    # Remove spaces around special characters
    css = re.sub(r'\s*([{};:,>+~])\s*', r'\1', css)

    # Remove trailing semicolons before closing braces
    css = re.sub(r';}', '}', css)

    # Remove leading/trailing whitespace
    css = css.strip()

    # Escape backslashes for JavaScript template strings
    # This turns \25B6 into \\25B6 so it works in `template strings`
    css = css.replace('\\', '\\\\')

    return css


def concatenate_css_files(css_dir: Path, unified_css_dir: Path = None) -> str:
    """
    Concatenate CSS files in the correct order.

    The order matters because later files may depend on tokens/variables
    defined in earlier files.

    If unified_css_dir is provided, also include unified popover styles
    (source-tabs.css, ibm-content.css) for multi-engine support.
    """
    file_order = [
        'tokens.css',
        'base.css',
        'nav.css',
        'content.css',
        'badges.css',
        'animations.css',
        'themes.css',
    ]

    css_parts = []

    # Add Google Fonts import first
    css_parts.append('@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap");')

    for filename in file_order:
        filepath = css_dir / filename
        if filepath.exists():
            content = filepath.read_text(encoding='utf-8')
            # Remove any @import statements (we handle those manually)
            content = re.sub(r'@import\s+url\([^)]+\);?\s*', '', content)
            css_parts.append(content)
        else:
            print(f"Warning: {filepath} not found", file=sys.stderr)

    # Add unified popover styles if directory provided
    if unified_css_dir and unified_css_dir.exists():
        unified_files = ['source-tabs.css', 'ibm-content.css']
        for filename in unified_files:
            filepath = unified_css_dir / filename
            if filepath.exists():
                content = filepath.read_text(encoding='utf-8')
                content = re.sub(r'@import\s+url\([^)]+\);?\s*', '', content)
                css_parts.append(content)
            else:
                print(f"Warning: {filepath} not found", file=sys.stderr)

    return '\n'.join(css_parts)


def update_js_file(js_path: Path, minified_css: str, function_name: str) -> bool:
    """
    Update a JS file's CSS function with the new minified CSS.

    Looks for a function like:
        function getPopoverCSS() {
            return `...`;
        }

    And replaces the content between the backticks.
    """
    content = js_path.read_text(encoding='utf-8')

    # Pattern to match the function and its return statement
    # This handles both getPopoverCSS and getIbmPopoverCSS
    pattern = rf'(function {function_name}\(\) \{{\s*(?://[^\n]*\n\s*)*return `)[^`]*(`;\s*\}})'

    # Check if pattern exists
    match = re.search(pattern, content)
    if not match:
        print(f"Warning: Could not find {function_name}() in {js_path}", file=sys.stderr)
        return False

    # Replace using string operations instead of re.sub to avoid backreference issues
    # The CSS content might contain patterns like \25B6 that confuse regex
    start = match.start(1) + len(match.group(1))
    end = match.start(2)
    new_content = content[:start] + minified_css + content[end:]

    if new_content != content:
        js_path.write_text(new_content, encoding='utf-8')
        return True

    return False


def main():
    # Find project root (where this script lives in scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    # CSS source directories
    css_dir = project_root / 'inspekt' / 'scripts' / 'axe-popover'
    unified_css_dir = project_root / 'inspekt' / 'scripts' / 'unified-popover'

    # Target JS files
    run_axe_js = project_root / 'inspekt' / 'scripts' / 'run_axe.js'
    run_ibm_js = project_root / 'inspekt' / 'scripts' / 'run_ibm.js'
    run_a11y_js = project_root / 'inspekt' / 'scripts' / 'run_a11y.js'

    # Check if source directory exists
    if not css_dir.exists():
        print(f"Error: CSS directory not found: {css_dir}", file=sys.stderr)
        sys.exit(1)

    # Concatenate and minify CSS for axe/ibm (base popover CSS)
    print("Reading CSS files from:", css_dir)
    combined_css = concatenate_css_files(css_dir)
    minified_css = minify_css(combined_css)

    # Concatenate and minify unified CSS (includes source-tabs for multi-engine)
    print("Reading unified CSS files from:", unified_css_dir)
    unified_combined_css = concatenate_css_files(css_dir, unified_css_dir)
    unified_minified_css = minify_css(unified_combined_css)

    # Calculate sizes
    original_size = len(combined_css)
    minified_size = len(minified_css)
    reduction = (1 - minified_size / original_size) * 100 if original_size > 0 else 0

    print(f"Base CSS - Original: {original_size:,} bytes, Minified: {minified_size:,} bytes ({reduction:.1f}% reduction)")

    unified_original_size = len(unified_combined_css)
    unified_minified_size = len(unified_minified_css)
    unified_reduction = (1 - unified_minified_size / unified_original_size) * 100 if unified_original_size > 0 else 0

    print(f"Unified CSS - Original: {unified_original_size:,} bytes, Minified: {unified_minified_size:,} bytes ({unified_reduction:.1f}% reduction)")

    # Check for --apply flag
    if '--apply' in sys.argv:
        print("\nApplying changes...")

        updated_files = []

        # Update run_axe.js with base CSS
        if run_axe_js.exists():
            if update_js_file(run_axe_js, minified_css, 'getPopoverCSS'):
                updated_files.append(run_axe_js.name)
        else:
            print(f"Warning: {run_axe_js} not found", file=sys.stderr)

        # Update run_ibm.js with base CSS
        if run_ibm_js.exists():
            if update_js_file(run_ibm_js, minified_css, 'getIbmPopoverCSS'):
                updated_files.append(run_ibm_js.name)
        else:
            print(f"Warning: {run_ibm_js} not found", file=sys.stderr)

        # Update run_a11y.js with unified CSS (includes source-tabs)
        if run_a11y_js.exists():
            if update_js_file(run_a11y_js, unified_minified_css, 'getUnifiedCSS'):
                updated_files.append(run_a11y_js.name)
        else:
            print(f"Warning: {run_a11y_js} not found", file=sys.stderr)

        if updated_files:
            print(f"Updated: {', '.join(updated_files)}")
        else:
            print("No files were updated (CSS may already be up to date)")
    else:
        print("\n--- Base Minified CSS ---")
        print(minified_css[:500] + "..." if len(minified_css) > 500 else minified_css)
        print("\n--- End ---")
        print("\nTo apply changes to run_axe.js, run_ibm.js, and run_a11y.js, run:")
        print("  python scripts/build_popover_css.py --apply")


if __name__ == '__main__':
    main()
