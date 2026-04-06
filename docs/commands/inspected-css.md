# inspekt inspected css - Extract Computed CSS Styles

The `inspekt inspected css` command extracts computed CSS styles from the currently inspected element and all its children. It generates clean, readable CSS that can reproduce the visual appearance of the selected elements.

## Quick Start

```bash
# First, inspect an element
inspekt inspect ".card"

# Extract CSS with default formatting
inspekt inspected css

# Extract with aligned columns for readability
inspekt inspected css --two-columns

# Save to file
inspekt inspected css --file styles.css

# Copy to clipboard
inspekt inspected css --copy
```

## Why Use CSS Extraction?

### The Inspekt Advantage

Unlike copying styles from DevTools, Inspekt provides:

- **Nested CSS output** - Modern CSS nesting syntax, ready for use
- **Intelligent filtering** - Only includes relevant properties, not all 300+ computed values
- **Automatic optimization** - Merges longhand properties into shorthands
- **Helpful comments** - Adds color names, computed value markers, and pattern-based hints
- **Column alignment** - Format output for maximum readability

**Example workflow:**
```bash
# Select a complex component
inspekt inspect ".hero-section"

# Get optimized CSS with helpful comments
inspekt inspected css --heuristic-comments --two-columns

# Save directly to your project
inspekt inspected css --file src/components/hero.css
```

## Column Formatting

The column formatting options make CSS output significantly easier to read by aligning property names, values, and comments.

### `--two-columns`

Aligns properties and values in two visual columns. Comments follow immediately after values.

```css
box-sizing:             border-box;
width:                  249px /* Computed (Rounded) */;
height:                 540px;
font-family:            Flama, Arial, sans-serif;
text-decoration-color:  #dcdcff /* Hawkes Blue */;
transition:
  background-color      0.2s,
  border-color          0.2s,
  color                 0.2s;
```

**Best for:** Quick scanning of property-value pairs, copying into code.

### `--three-columns`

Aligns properties, values, AND comments in three separate visual columns.

```css
box-sizing:             border-box;
width:                  249px       /* Computed (Rounded) */;
height:                 540px;
font-family:            Flama, Arial, sans-serif;
text-decoration-color:  #dcdcff     /* Hawkes Blue */;
```

**Best for:** Documentation, code reviews, or when you want comments to be highly visible.

### How Column Widths Work

Column widths are calculated per section (separated by blank lines or comments like `/* Layout */`):

```css
.card {
  /* Layout - widths calculated from this section's properties */
  box-sizing:  border-box;
  width:       249px;
  height:      540px;

  /* Typography - separate column widths for this section */
  font-family:            Flama, Arial, sans-serif;
  text-decoration-color:  #dcdcff /* Hawkes Blue */;
}
```

Nested selectors also get their own independent column widths:

```css
.parent {
  text-decoration-color:  #f5f3f0;

  & .child {
    color:    #fff;
    padding:  10px;
  }
}
```

Multi-line values (like `transition` or `linear-gradient`) align with their parent block's column width:

```css
text-decoration-color:  #dcdcff;
transition:
  background-color      0.2s,
  border-color          0.2s,
  color                 0.2s;
display:                inline-block;
```

## Options

| Option | Description |
|--------|-------------|
| `--file [PATH]` | Save to file (auto-generates name if no path given) |
| `--open` | Open file in default app after saving |
| `--reveal` | Reveal file in file explorer after saving |
| `--copy` | Copy output to clipboard |
| `--json` | Output as JSON |
| `--raw` | Output without syntax highlighting |
| `--two-columns` | Format with aligned property and value columns |
| `--three-columns` | Format with aligned property, value, and comment columns |
| `--all-properties` | Include all ~300 computed properties (default: common only) |
| `--include-defaults` | Include browser default values |
| `--optimize` / `--no-optimize` | Merge shorthands (default: on) |
| `--alphabetize` / `--no-alphabetize` | Sort properties alphabetically (default: on) |
| `--rounding` / `--no-rounding` | Round pixel values (default: on) |
| `--oklch` | Convert colors to OKLCH format |
| `--heuristic-comments` | Add helpful pattern-based comments |

## Piping and Automation

The `inspected css` command automatically detects when output is piped or redirected and suppresses decorations (statistics table, tips) for clean, script-friendly output:

```bash
# Piped to file - automatically outputs only CSS without decorations
inspekt inspected css > styles.css

# Piped to grep - no decorations to interfere with pattern matching
inspekt inspected css | grep "color:"

# Piped to tee - clean output with redirection
inspekt inspected css 2>&1 | tee output.log

# In terminal - shows full formatted output with table and tips
inspekt inspected css
```

This follows the Unix philosophy: **verbose in terminals, minimal in pipes**.

### Use Cases

**Save to file without extra formatting:**
```bash
inspekt inspect ".card"
inspekt inspected css > components/card.css
# File contains only the CSS, ready to use
```

**Extract specific styles from pipe:**
```bash
inspekt inspect "body"
inspekt inspected css | grep -A2 "color:"
```

**Process CSS with other tools:**
```bash
inspekt inspect ".hero"
inspekt inspected css | prettier --parser=css
```

To force raw output even in a terminal, use `--raw`:
```bash
inspekt inspected css --raw
```

## Examples

### Basic Extraction

```bash
# Extract CSS from currently inspected element
inspekt inspected css

# Extract with all properties (not just common ones)
inspekt inspected css --all-properties

# Keep browser defaults (normally filtered out)
inspekt inspected css --include-defaults
```

### Formatting Options

```bash
# Aligned columns for readability
inspekt inspected css --two-columns

# With heuristic comments explaining patterns
inspekt inspected css --heuristic-comments --two-columns
# Output: display: flex; /* Flexbox container */

# Convert colors to perceptual OKLCH format
inspekt inspected css --oklch
# Output: color: oklch(0.95 0.01 264) /* Near White */;

# Disable optimization for raw computed values
inspekt inspected css --no-optimize --no-rounding
```

### Output Options

```bash
# Save to auto-named file
inspekt inspected css --file
# Creates: 2025-01-15_example-com_card.css

# Save to specific file
inspekt inspected css --file components/hero.css

# Copy to clipboard (silent)
inspekt inspected css --copy

# JSON output for scripting
inspekt inspected css --json | jq '.css'

# Raw output (no syntax highlighting)
inspekt inspected css --raw
```

### Combining Options

```bash
# Full-featured extraction with column alignment
inspekt inspected css \
  --heuristic-comments \
  --oklch \
  --two-columns \
  --file hero.css

# Quick clipboard copy with formatting
inspekt inspected css --copy --two-columns
```

## Output Format

The command outputs nested CSS using modern CSS nesting syntax:

```css
.hero-section {
  display: flex;
  flex-direction: column;
  padding: 48px;
  background: #1a1a1a /* Woodsmoke */;

  & .hero-title {
    font-size: 48px /* Computed (Rounded) */;
    font-weight: 700;
    color: #fff /* White */;
  }

  & .hero-subtitle {
    font-size: 18px;
    color: #a0a0a0 /* Silver Chalice */;
  }
}
```

### Comment Types

The output includes helpful comments:

- **Color names:** `#fff /* White */` - Human-readable color identification
- **Computed values:** `/* Computed (Rounded) */` - Values that were calculated and rounded
- **Heuristic comments:** `/* Flexbox container */` - Pattern-based explanations (with `--heuristic-comments`)

## Use Cases

### 1. Component Extraction

Extract a complete component's styles:

```bash
inspekt inspect ".product-card"
inspekt inspected css --file product-card.css --heuristic-comments
```

### 2. Design System Documentation

Generate readable documentation of component styles:

```bash
inspekt inspect ".button--primary"
inspekt inspected css --three-columns --heuristic-comments
```

### 3. Quick Prototyping

Copy styles to use in a prototype:

```bash
inspekt inspect ".hero"
inspekt inspected css --copy --two-columns
# Paste into your CSS file
```

### 4. Debugging Layout Issues

See exactly what computed values are applied:

```bash
inspekt inspect ".broken-layout"
inspekt inspected css --no-optimize --all-properties
```

### 5. Color Audit

Extract styles with OKLCH colors for perceptual editing:

```bash
inspekt inspect "body"
inspekt inspected css --oklch --all-properties | grep oklch
```

## Related Commands

- `inspekt inspect` - Select an element to inspect
- `inspekt inspected tree` - View the element hierarchy
- `inspekt inspected html` - Extract the HTML structure
- `inspekt inspected a11y` - Run accessibility checks on the element
