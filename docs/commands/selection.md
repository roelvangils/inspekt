# Selection & Inspected Commands

Extract HTML, text, and markdown from browser selections and inspected elements. Perfect for documentation, code examples, and content extraction.

## Overview

Inspekt provides two complementary commands for extracting content:

| Command | Source | Use Case |
|---------|--------|----------|
| `inspekt selection` | Text selected in the browser | Copy content you've highlighted |
| `inspekt inspected` | Element from DevTools Inspector | Extract specific DOM elements |

Both commands support multiple output formats (HTML, text, markdown) and share the same processing options.

---

## Quick Start

### Selection Commands

```bash
# Get selected text as plain text
inspekt selection text

# Get selected content as HTML
inspekt selection html

# Get selected content as Markdown
inspekt selection markdown

# Copy HTML directly to clipboard
inspekt selection html --copy
```

### Inspected Commands

```bash
# First, inspect an element in DevTools (right-click → Inspect)
# Then in DevTools Console, run: inspektStore()

# Get element info
inspekt inspected

# Get element's HTML
inspekt inspected html

# Get element's text content
inspekt inspected text

# Get element as Markdown
inspekt inspected markdown

# Get CSS styles (optimized by default)
inspekt inspected css

# Get raw computed styles without optimization
inspekt inspected css --no-optimize

# Take a screenshot of the element
inspekt inspected screenshot -o element.png

# Save HTML and CSS to files
inspekt inspected html --file --include-css

# Create bundled HTML with embedded styles
inspekt inspected html --file --include-css --bundled
```

---

## Output Formats

### Text (`text` subcommand)

Plain text content, stripped of all HTML markup.

```bash
inspekt selection text
inspekt selection text --raw      # No formatting, just text
inspekt selection text --copy     # Copy to clipboard
inspekt selection text --json     # JSON output
```

### HTML (`html` subcommand)

Raw or processed HTML content with optional formatting.

```bash
inspekt selection html
inspekt selection html --raw           # Unformatted HTML
inspekt selection html --pretty        # Format with proper indentation
inspekt selection html --compact       # Clean up for documentation
inspekt selection html --colors        # Syntax highlighting
inspekt selection html --copy          # Copy to clipboard
```

### Markdown (`markdown` subcommand)

HTML converted to Markdown format (requires `html2markdown` CLI tool).

```bash
inspekt selection markdown
inspekt selection markdown --raw       # No formatting
inspekt selection markdown --copy      # Copy to clipboard
```

### CSS (`css` subcommand) — Inspected Only

Extract computed CSS styles from the inspected element and all its children.

```bash
# Get computed CSS styles
inspekt inspected css

# Include all CSS properties (not just common ones)
inspekt inspected css --all-properties

# Include browser default values
inspekt inspected css --include-defaults

# Save to file
inspekt inspected css --file
inspekt inspected css --file styles.css
```

The CSS output uses modern CSS nesting syntax for a clean, hierarchical structure:

```css
.article-content {
    display: flex;
    flex-direction: column;
    gap: 16px;

    h1 {
        font-size: 32px;
        font-weight: 700;
    }

    p {
        line-height: 1.6;
    }
}
```

**Filtering options:**

| Option | Description |
|--------|-------------|
| `--all-properties` | Include all 400+ CSS properties (default: common properties only) |
| `--include-defaults` | Include browser default values (default: non-default only) |

### CSS Processing Pipeline

When you run `inspekt inspected css`, the output goes through several processing stages by default:

1. **Optimization** — Merge longhand properties into shorthands using [Lightning CSS](https://lightningcss.dev/)
2. **Color naming** — Add human-readable color names as comments
3. **Computed markers** — Mark pixel values with 2+ decimal places as `/* Computed */`
4. **Formatting** — Format with Prettier for consistent indentation
5. **Logical ordering** — Sort properties by category (Layout → Typography → Animation → Other)

All stages are enabled by default for the best developer experience. You can disable any stage with flags.

```bash
# Full processing (default)
inspekt inspected css

# Disable specific stages
inspekt inspected css --no-optimize      # Skip shorthand merging
inspekt inspected css --no-alphabetize   # Keep original property order

# Convert colors to oklch format
inspekt inspected css --oklch
```

### Color Names

For convenience, **color names are always added as comments** when CSS is optimized. This helps identify colors at a glance:

```css
.button {
  background-color: #6bb181; /* Silver Tree */
  border-color: #333332; /* Mine Shaft */
  color: #0051c2; /* Science Blue */
}
```

Color names come from the [Name That Color](http://chir.ag/projects/ntc/) database, which includes over 1500 natural-sounding names from Resene, Crayola, and color dictionaries.

### Pixel Rounding

By default, **pixel values are rounded to the nearest whole pixel** for cleaner output. Rounded values are marked with `/* Computed (Rounded) */` comments to indicate they were browser-calculated values:

```css
.vl-link {
  font-size: 20px; /* Computed (Rounded) */
  line-height: 30px; /* Computed (Rounded) */
  outline-offset: 2px;
  padding: 16px;
}
```

Use `--no-rounding` to keep the original decimal values. In this case, values are marked with `/* Computed */`:

```css
.vl-link {
  font-size: 20.25px; /* Computed */
  line-height: 30.38px; /* Computed */
  outline-offset: 2px;
  padding: 16px;
}
```

**Why round?** Authors typically use whole numbers (16px, 24px). Precise decimals like `20.25px` indicate browser-computed values from font scaling, `calc()` expressions, or relative units. Rounding produces cleaner CSS while preserving visual fidelity.

**Note:** When using `--optimize`, comments are stripped by Lightning CSS during shorthand merging. Use `--no-optimize` to preserve the computed value markers.

### oklch Conversion

Use `--oklch` to convert hex/rgb colors to the [oklch color space](https://developer.mozilla.org/en-US/docs/Web/CSS/color_value/oklch):

```bash
inspekt inspected css --oklch
```

**Output:**
```css
.button {
  background-color: oklch(0.7 0.1 153); /* Silver Tree */
  color: oklch(0.47 0.18 264); /* Science Blue */
}
```

**Why oklch?** The oklch color space is perceptually uniform, making it ideal for:
- Creating consistent color palettes
- Adjusting lightness or saturation predictably
- Accessibility-friendly color variations

### Logical Property Ordering

Properties are **sorted by category** by default, not just alphabetically. This groups related properties together in a logical order:

1. **Layout** — `display`, `width/height`, `flex-*`, `grid-*`, `gap`, `overflow`
2. **Box** — `position`, `top/right/bottom/left`, `margin`, `padding`, `border`, `outline`
3. **Typography** — `color`, `font-*`, `line-height`, `text-*`, `white-space`
4. **Animation** — `transition`, `animation`, `transform`
5. **Other** — Everything else: `background`, `box-shadow`, `cursor`, `opacity`, etc. (alphabetized)

When a rule contains properties from multiple categories, **category comments** are automatically inserted:

```css
.card {
  /* Layout */
  display: flex;
  box-sizing: border-box;
  width: 100%;

  /* Box */
  margin: 16px;
  padding: 24px;
  border: 1px solid #ccc; /* Silver */
  border-radius: 8px;

  /* Typography */
  color: #333; /* Mine Shaft */
  font-size: 16px;
  line-height: 1.5;

  /* Animation */
  transition: background-color 0.2s;

  /* Other */
  background-color: #fff; /* White */
  cursor: pointer;
}
```

Use `--no-alphabetize` if you prefer to keep properties in their original (computed) order.

### Shorthand Optimization

**Why optimization?** The CSS extracted by `inspekt inspected css` is **computed styles**, not the original CSS from stylesheets. Browsers expand shorthand properties (like `margin: 16px`) into their longhand equivalents (`margin-top`, `margin-right`, etc.) during computation. Optimization reverses this expansion for readability.

If you need the exact CSS as authored in the stylesheets, inspect the stylesheets directly in DevTools or use your browser's "Copy rule" feature.

**What optimization does:**

| Transformation | Before (computed) | After (optimized) |
|----------------|-------------------|-------------------|
| Merge margin | `margin-top: 16px; margin-right: 16px; margin-bottom: 16px; margin-left: 16px;` | `margin: 16px;` |
| Merge padding | `padding-top: 5px; padding-right: 10px; padding-bottom: 5px; padding-left: 10px;` | `padding: 5px 10px;` |
| Merge border | `border-width: 1px; border-style: solid; border-color: red;` | `border: 1px solid red;` |

**Example:**

Computed styles (raw output with `--no-optimize`):
```css
.card {
    margin-top: 16px;
    margin-right: 16px;
    margin-bottom: 16px;
    margin-left: 16px;
    border-top-width: 1px;
    border-right-width: 1px;
    border-bottom-width: 1px;
    border-left-width: 1px;
    border-top-style: solid;
    border-right-style: solid;
    border-bottom-style: solid;
    border-left-style: solid;
    border-top-color: #ccc;
    border-right-color: #ccc;
    border-bottom-color: #ccc;
    border-left-color: #ccc;
}
```

After optimization (default):
```css
.card {
  border: 1px solid #ccc; /* Silver */
  margin: 16px;
}
```

#### When to use `--no-optimize`

Use `--no-optimize` when you need the raw computed styles:

- Debugging why a specific longhand property has a certain value
- Investigating which individual properties are set
- You need to see exactly what the browser computed

---

## Compact Mode

The `--compact` flag transforms HTML into documentation-friendly output by removing visual noise while preserving semantic structure.

### Use Cases

1. **Documentation Examples** - Clean HTML for tutorials and guides
2. **Code Samples** - Readable snippets without implementation details
3. **Bug Reports** - Reproducible HTML without sensitive data
4. **Design Systems** - Focus on structure, not styling
5. **Accessibility Audits** - See semantic structure clearly

### What Compact Mode Does

| Category | What's Transformed | Replacement |
|----------|-------------------|-------------|
| **Styling** | `class` attributes | Removed |
| **Styling** | `style` attributes | Removed |
| **Data** | `data-*` attributes | Removed |
| **URLs** | Long URLs in `href`, `src`, `action`, etc. | Middle segments replaced with `…` |
| **URLs** | `srcset` URLs | Truncated, size descriptors preserved |
| **JavaScript** | Inline event handlers (`onclick`, `onload`, etc.) | `[JAVASCRIPT]` |
| **Security** | `integrity` hashes | `[HASH]` |
| **Security** | `nonce` values | `[NONCE]` |
| **IDs** | Long `id`, `for`, `name`, `aria-*` attributes | Truncated with `…` |
| **Binary** | Base64-encoded content | `[DATA]` |
| **Graphics** | SVG `<path d="...">` data | `[PATH DATA]` |
| **Graphics** | Polygon/polyline points | `[POINTS]` |
| **Hashes** | Long random strings (20+ chars) | `[STRING]` |
| **Comments** | Empty HTML comments | Removed |
| **Text** | Content longer than 20 words | `…` |

### Comprehensive Example

Here's a real-world example showing all compact transformations:

**Before (raw HTML):**
```html
<article class="article-card featured lazyloaded"
         id="ember-view-12345-article-container-wrapper"
         style="margin: 16px; padding: 24px; background: #fff;"
         data-testid="article-card"
         data-analytics-id="article-123"
         data-loaded="true"
         onclick="trackClick(event)"
         onmouseover="prefetchArticle(123)">

  <header class="article-header flex items-center gap-4">
    <img class="avatar rounded-full"
         src="https://cdn.example.com/avatars/users/profiles/thumbnails/abc123def456ghi789jkl012mno345pqr678.jpg"
         srcset="https://cdn.example.com/avatars/users/profiles/thumbnails/abc123def456ghi789jkl012mno345pqr678.jpg 1x,
                 https://cdn.example.com/avatars/users/profiles/thumbnails/abc123def456ghi789jkl012mno345pqr678@2x.jpg 2x"
         alt="Author avatar">

    <a class="author-link text-blue-600 hover:underline"
       href="https://blog.example.com/authors/profiles/john-doe"
       aria-describedby="ember-view-12345-author-tooltip-container">
      John Doe
    </a>
  </header>

  <h2 class="title text-2xl font-bold mt-4">
    <a href="https://blog.example.com/articles/technology/web-development/2024/accessibility-tips">
      10 Essential Accessibility Tips
    </a>
  </h2>

  <p class="excerpt text-gray-600 mt-2">
    Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
    tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim
    veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex
    ea commodo consequat. Duis aute irure dolor in reprehenderit.
  </p>

  <footer class="article-footer flex justify-between mt-4">
    <button class="btn btn-primary"
            onclick="shareArticle(123)"
            aria-labelledby="ember-view-12345-share-button-label-text">
      <svg class="icon" viewBox="0 0 24 24">
        <path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92-1.31-2.92-2.92-2.92z"/>
      </svg>
      Share
    </button>

    <script src="https://cdn.example.com/js/analytics.min.js"
            integrity="sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K/uxy9rx7HNQlGYl1kPzQho1wx4JwY8wC"
            nonce="abc123xyz789"
            async>
    </script>
  </footer>
  <!-- -->
</article>
```

**After `--compact --pretty`:**
```html
<article id="ember-view-12345-article-co…"
         onclick="[JAVASCRIPT]"
         onmouseover="[JAVASCRIPT]">

  <header>
    <img src="https://cdn.example.com/avatars/…/[STRING].jpg"
         srcset="https://cdn.example.com/avatars/…/[STRING].jpg 1x,
                 https://cdn.example.com/avatars/…/[STRING].jpg 2x"
         alt="Author avatar">

    <a href="https://blog.example.com/authors/…/john-doe"
       aria-describedby="ember-view-12345-author-t…">
      John Doe
    </a>
  </header>

  <h2>
    <a href="https://blog.example.com/articles/…/accessibility-tips">
      10 Essential Accessibility Tips
    </a>
  </h2>

  <p>…</p>

  <footer>
    <button onclick="[JAVASCRIPT]"
            aria-labelledby="ember-view-12345-share-bu…">
      <svg viewBox="0 0 24 24">
        <path d="[PATH DATA]"/>
      </svg>
      Share
    </button>

    <script src="https://cdn.example.com/js/…/analytics.min.js"
            integrity="[HASH]"
            nonce="[NONCE]"
            async>
    </script>
  </footer>
</article>
```

Notice how:

- **Classes and styles removed** — No `class="..."` or `style="..."` clutter
- **Data attributes removed** — `data-testid`, `data-analytics-id` gone
- **URLs truncated** — Long paths become `https://example.com/first/…/last`
- **srcset preserved** — URLs shortened but `1x`, `2x` descriptors kept
- **Event handlers replaced** — `onclick="trackClick(event)"` → `onclick="[JAVASCRIPT]"`
- **Long IDs truncated** — `ember-view-12345-article-container-wrapper` → `ember-view-12345-article-co…`
- **Long aria-* truncated** — References to long IDs are also shortened
- **Integrity hashes hidden** — `sha384-...` → `[HASH]`
- **Nonces hidden** — Random values → `[NONCE]`
- **SVG paths simplified** — Complex path data → `[PATH DATA]`
- **Long text truncated** — Paragraphs over 20 words → `…`
- **Empty comments removed** — `<!-- -->` deleted
- **Random strings replaced** — Hash-like strings → `[STRING]`

### Individual Examples

#### Example 1: SVG Icons

**Before:**
```html
<svg class="icon-heart" data-testid="heart-icon"
     fill="none" viewbox="0 0 20 18" width="20">
  <path d="M13.696 1C16.871 1 19 3.98 19 6.755C19 12.388 10.161 17 10 17C9.839 17 1 12.388 1 6.755C1 3.98 3.129 1 6.304 1C8.119 1 9.311 1.905 10 2.711C10.689 1.905 11.881 1 13.696 1V1Z"
        stroke-linecap="round" stroke-linejoin="round" stroke-width="2">
  </path>
</svg>
```

**After `--compact`:**
```html
<svg fill="none" viewbox="0 0 20 18" width="20">
  <path d="[PATH DATA]"
        stroke-linecap="round" stroke-linejoin="round" stroke-width="2">
  </path>
</svg>
```

#### Example 2: Images with Hashed URLs

**Before:**
```html
<img class="hero-image lazyloaded"
     data-src="original.jpg"
     data-loaded="true"
     src="https://cdn.example.com/7417c52e712555d1ed99f6d96f335a0788cf14642d37024de39eb99835aa31b7.jpg?vh=4f78fd"
     alt="Hero image">
```

**After `--compact`:**
```html
<img src="https://cdn.example.com/[STRING].jpg?vh=4f78fd"
     alt="Hero image">
```

#### Example 3: Base64 Embedded Images

**Before:**
```html
<img class="avatar"
     data-user-id="12345"
     src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
     alt="User avatar">
```

**After `--compact`:**
```html
<img src="data:image/png;base64,[DATA]"
     alt="User avatar">
```

#### Example 4: Navigation with Styling

**Before:**
```html
<nav class="main-nav sticky-top bg-white shadow-sm"
     style="z-index: 1000; padding: 1rem 2rem;"
     data-component="navigation"
     data-analytics="main-nav">
  <a href="/home" class="nav-link active text-primary fw-bold">Home</a>
  <a href="/about" class="nav-link text-muted">About</a>
  <a href="/contact" class="nav-link text-muted">Contact</a>
</nav>
<!-- -->
```

**After `--compact`:**
```html
<nav>
  <a href="/home">Home</a>
  <a href="/about">About</a>
  <a href="/contact">Contact</a>
</nav>
```

#### Example 5: Long Text Content

**Before:**
```html
<p class="article-intro lead">
  Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
  tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim
  veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex
  ea commodo consequat. Duis aute irure dolor in reprehenderit.
</p>
```

**After `--compact`:**
```html
<p>...</p>
```

---

## Formatting Options

### Pretty Printing (`--pretty`)

Formats HTML with proper indentation for consistent, readable output.

```bash
inspekt selection html --pretty
```

**Before:**
```html
<div><ul><li>Item 1</li><li>Item 2</li></ul></div>
```

**After:**
```html
<div>
  <ul>
    <li>Item 1</li>
    <li>Item 2</li>
  </ul>
</div>
```

### Indentation (`--indent`)

Control the number of spaces for indentation (1-8, default: 2).

```bash
inspekt selection html --pretty --indent 4
```

### Syntax Highlighting (`--colors`)

Colorize HTML output for terminal display using Pygments.

```bash
inspekt selection html --colors
inspekt selection html --colors --theme github-dark
```

**Available themes:** `monokai` (default), `vim`, `github-dark`, `dracula`, `one-dark`, `solarized-dark`, `nord`, and [many more](https://pygments.org/styles/).

---

## Clipboard Support

Copy output directly to clipboard with `--copy`:

```bash
# Copy formatted HTML
inspekt selection html --pretty --compact --copy

# Copy plain text
inspekt selection text --copy

# Copy as Markdown
inspekt selection markdown --copy
```

Works cross-platform:
- **macOS:** Uses `pbcopy`
- **Linux:** Uses `xclip` (install with `sudo apt install xclip`)
- **Windows:** Uses `clip`

---

## Configuration

Default settings can be configured in `~/.config/inspekt/config.yaml`:

```yaml
html_selection:
  compact: false          # Default: don't compact
  pretty: true            # Default: format with proper indentation
  colors: true            # Default: syntax highlighting on
  theme: monokai          # Pygments theme
  indent: 2               # Spaces for indentation
```

Command-line flags override configuration:

```bash
# Override config defaults
inspekt selection html --no-pretty --no-colors
inspekt selection html --compact --indent 4
```

---

## JSON Output

Get structured JSON output with `--json`:

### Selection JSON

```bash
inspekt selection --json
```

Returns all formats at once:

```json
{
  "hasSelection": true,
  "text": "Selected text content",
  "html": "<p>Selected text content</p>",
  "markdown": "Selected text content",
  "length": 21,
  "position": {
    "x": 100,
    "y": 200,
    "width": 300,
    "height": 50
  },
  "container": {
    "tag": "article",
    "id": "main-content"
  }
}
```

### Inspected JSON

```bash
inspekt inspected --json
```

Returns comprehensive element data:

```json
{
  "ok": true,
  "tag": "button",
  "id": "submit-btn",
  "classes": ["btn", "btn-primary"],
  "attributes": {
    "type": "submit",
    "disabled": ""
  },
  "textContent": "Submit Form",
  "htmlContent": "<button id=\"submit-btn\" class=\"btn btn-primary\">Submit Form</button>",
  "selector": "form > button#submit-btn",
  "dimensions": {
    "width": 120,
    "height": 40,
    "top": 500,
    "left": 200
  },
  "accessibility": {
    "role": "button",
    "accessibleName": "Submit Form",
    "focusable": true
  }
}
```

---

## Raw Output

Use `--raw` for pipe-friendly output without headers or formatting:

```bash
# Pipe HTML to another tool
inspekt selection html --raw | tidy -i

# Save to file
inspekt selection html --raw > snippet.html

# Count characters
inspekt selection text --raw | wc -c

# Pipe to clipboard (alternative to --copy)
inspekt selection markdown --raw | pbcopy
```

---

## File Output

Save extracted content directly to files with auto-generated or custom filenames. File output is available for `inspekt inspected html`, `inspekt inspected css`, and `inspekt selection html`.

### Basic File Output

```bash
# Auto-generate filename (format: YYYYMMDDHHMMSS_domain_selector.ext)
inspekt inspected html --file
inspekt inspected css --file

# Specify filename
inspekt inspected html --file snippet.html
inspekt inspected css --file styles.css

# Save and open in default application (e.g., VS Code, browser)
inspekt inspected html --file --open
inspekt inspected css --file styles.css --open

# Save and reveal in file explorer (Finder on macOS)
inspekt inspected html --file --reveal
inspekt inspected css --file --reveal

# Selection HTML also supports --file
inspekt selection html --file
inspekt selection html --file selection.html --open
```

Auto-generated filenames include:
- **Timestamp:** `20251222143052`
- **Domain:** `example_com`
- **Selector:** Derived from element's ID, class, or tag name

Example: `20251222143052_example_com_article-content.html`

### HTML with Matching CSS File

Generate both HTML and CSS files with matching timestamps:

```bash
# Creates two files with the same timestamp
inspekt inspected html --file --include-css

# Example output:
# 20251222143052_example_com_article-content.html
# 20251222143052_example_com_article-content.css
```

### Bundled HTML+CSS

Create a single self-contained HTML file with embedded styles:

```bash
inspekt inspected html --file --include-css --bundled
```

This creates a complete HTML document:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Page Title — .article-content</title>
  <style>
.inspekt-root {
    display: flex;
    flex-direction: column;

    h1 {
        font-size: 32px;
    }
}
  </style>
</head>
<body>
<div class="inspekt-root">
  <!-- extracted HTML -->
</div>
</body>
</html>
```

### CSS Filtering with File Output

Control which CSS properties are included:

```bash
# Common properties only (default) - smaller, cleaner output
inspekt inspected html --file --include-css --bundled

# All computed properties - comprehensive but verbose
inspekt inspected html --file --include-css --bundled --all-properties

# Include browser defaults - rarely needed
inspekt inspected html --file --include-css --bundled --include-defaults
```

### Use Cases for Bundled Output

1. **Prototype Sharing** — Share a styled component with colleagues without external dependencies
2. **Bug Reproduction** — Create isolated test cases for bug reports
3. **Design Review** — Extract and share specific page sections for feedback
4. **Archiving** — Save styled snapshots of page elements
5. **Style Debugging** — Analyze computed styles in isolation

### Limitations of Bundled Output

The bundled output uses **computed CSS styles**, not the original authored styles. This has several implications:

| Limitation | Explanation |
|------------|-------------|
| **No custom fonts** | Custom fonts (e.g., 'Roobert', 'Inter') are referenced but not embedded. They fall back to system fonts unless available locally. |
| **Computed values only** | CSS variables (`var(--color)`) are resolved to their computed values. Relative units (`em`, `rem`) become `px`. |
| **Expanded shorthands** | Shorthand properties like `margin: 10px` appear as `margin-top: 10px; margin-right: 10px;` etc. |
| **No pseudo-elements** | `::before` and `::after` content is not captured (computed styles only apply to real elements). |
| **No hover/focus states** | Only the current state is captured, not interactive states. |
| **CSS nesting required** | The output uses modern CSS nesting syntax, requiring Chrome 120+, Firefox 117+, or Safari 17.2+. |
| **No external resources** | Background images and other external resources are referenced by URL but not embedded. |

**Note:** The `--bundled` option cannot be combined with `--compact` because compact mode removes class names and attributes that CSS selectors need to match elements.

For pixel-perfect reproduction, use [`inspekt save`](save.md) to capture the full page with all resources.

---

## Combining Options

Options can be combined for precise control:

```bash
# Clean, formatted HTML for documentation
inspekt selection html --compact --pretty --indent 2

# Compact HTML copied to clipboard
inspekt selection html --compact --copy

# Syntax-highlighted compact HTML
inspekt selection html --compact --pretty --colors --theme github-dark

# Raw compact HTML for scripting
inspekt selection html --compact --raw

# JSON with compact HTML embedded
inspekt selection html --compact --json

# Remove all HTML comments from output
inspekt inspected html --remove-comments

# Clean HTML without comments, formatted for docs
inspekt inspected html --remove-comments --compact --pretty
```

---

## Practical Workflows

### Documentation Workflow

```bash
# 1. Select HTML in browser
# 2. Extract clean, formatted HTML
inspekt selection html --compact --pretty --copy

# 3. Paste into your documentation
```

### Bug Report Workflow

```bash
# 1. Inspect the problematic element
# 2. Extract minimal reproducible HTML
inspekt inspected html --compact --raw > bug-sample.html
```

### Design System Workflow

```bash
# 1. Inspect a component
# 2. Get clean HTML structure
inspekt inspected html --compact --pretty

# Output shows semantic structure without styling noise
```

### Content Migration Workflow

```bash
# 1. Select content in browser
# 2. Convert to Markdown for new CMS
inspekt selection markdown --copy
```

---

## Troubleshooting

### "No text selected"

Make sure you have text selected in the browser before running the command.

### "No element selected yet"

For `inspekt inspected`, you need to:
1. Right-click an element → Inspect
2. In DevTools Console, run: `inspektStore()`
3. Then run: `inspekt inspected`

### "Selected element has been removed from the page"

The element you inspected was removed from the DOM (e.g., modal closed, page navigation). Select a new element.

### "html2markdown not found"

For Markdown conversion, install `html2markdown`:
```bash
pip install html2markdown
# or
npm install -g html-to-markdown
```

---

## Command Reference

### `inspekt selection`

| Subcommand | Description |
|------------|-------------|
| `text` | Plain text output |
| `html` | HTML output |
| `markdown` | Markdown output |

### `inspekt inspected`

| Subcommand | Description |
|------------|-------------|
| (none) | Show element info |
| `text` | Element text content |
| `html` | Element HTML |
| `css` | Element computed CSS styles |
| `markdown` | Element as Markdown |
| `screenshot` | Capture element screenshot (alias for `inspekt screenshot node`)|

### Shared Options

| Option | Description | Default |
|--------|-------------|---------|
| `--raw` | Output only content, no formatting | Off |
| `--copy` | Copy to clipboard | Off |
| `--json` | JSON output | Off |

### HTML-Specific Options

| Option | Description | Default |
|--------|-------------|---------|
| `--pretty` / `--no-pretty` | Format with indentation | From config |
| `--compact` / `--no-compact` | Clean up for docs | From config |
| `--colors` / `--no-colors` | Syntax highlighting | From config |
| `--theme` | Pygments theme name | `monokai` |
| `--indent` | Spaces for indent (1-8) | `2` |
| `--remove-comments` | Remove all HTML comments (inspected only) | Off |

**Note:** Empty HTML comments (`<!---->` and `<!-- -->`) are always automatically removed, regardless of flags.

### CSS-Specific Options (Inspected Only)

| Option | Description | Default |
|--------|-------------|---------|
| `--all-properties` | Include all CSS properties | Off (common only) |
| `--include-defaults` | Include browser default values | Off |
| `--optimize` / `--no-optimize` | Merge shorthands (requires Lightning CSS) | On |
| `--alphabetize` / `--no-alphabetize` | Sort properties by category (Layout, Box, Typography, Animation, Other) | On |
| `--rounding` / `--no-rounding` | Round pixel values to nearest whole pixel | On |
| `--oklch` | Convert colors to oklch format | Off |
| `--colors` / `--no-colors` | Syntax highlighting | From config |
| `--theme` | Pygments theme name | `monokai` |

**Note:** Color names are automatically added as comments when optimization is enabled (e.g., `#6bb181; /* Silver Tree */`).

### File Output Options

| Option | Description | Default |
|--------|-------------|---------|
| `--file` | Save to file (auto-generates name if no path given) | Off |
| `--file <path>` | Save to specified file path | — |
| `--open` | Open file in default application after saving (requires `--file`) | Off |
| `--reveal` | Reveal file in file explorer after saving (requires `--file`) | Off |
| `--include-css` | Generate matching CSS file (requires `--file`, HTML only) | Off |
| `--bundled` | Embed CSS in HTML file (requires `--include-css`, HTML only) | Off |
| `--optimize-css` / `--no-optimize-css` | Optimize embedded CSS (HTML only) | On |
| `--rounding` / `--no-rounding` | Round CSS pixel values to nearest whole pixel | On |
| `--oklch` | Convert CSS colors to oklch format (when using `--include-css`) | Off |
| `--all-properties` | Include all CSS properties in generated CSS | Off |
| `--include-defaults` | Include CSS defaults in generated CSS | Off |
| `--remove-comments` | Remove all HTML comments (HTML only) | Off |

**Note:** The `--file`, `--open`, and `--reveal` options are also available for `inspekt selection html` and `inspekt inspected css`.

**Validation rules:**

- `--include-css` requires `--file`
- `--bundled` requires `--include-css`
- `--bundled` cannot be used with `--compact`
- `--file` cannot be used with `--copy` or `--json`
- `--open` and `--reveal` require `--file`

---

## See Also

- [Data Extraction Guide](../guide/data-extraction.md) - More extraction commands
- [Configuration](../getting-started/configuration.md) - Config file options
- [AI Features](../guide/ai-features.md) - AI-powered content analysis
