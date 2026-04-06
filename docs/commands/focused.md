# inspekt focused - Get Information About the Focused Element

The `inspekt focused` command retrieves information about the currently focused element in the browser (the element with keyboard/input focus via `document.activeElement`). This is essential for testing keyboard navigation, focus management, and accessibility compliance.

## Quick Start

```bash
# Tab to an element in the browser, then:
inspekt focused

# Get focused element's HTML
inspekt focused html

# Get focused element's text as Markdown
inspekt focused markdown

# Extract CSS styles from focused element
inspekt focused css

# Get plain text content
inspekt focused text
```

## Why Use Focused vs Inspected?

| Command | Element Source | Use Case |
|---------|---------------|----------|
| `inspekt inspected` | DevTools selection ($0) | Visual inspection, design review |
| `inspekt focused` | `document.activeElement` | Keyboard testing, focus management, accessibility |

**Key difference:** `inspekt focused` captures the *live* focused element, which changes as users Tab through a page. This makes it invaluable for:

- **Keyboard navigation testing** - Verify Tab order works correctly
- **Focus trap debugging** - Ensure modals capture and release focus properly
- **Skip link testing** - Confirm skip links move focus to the right target
- **Form field testing** - Check which input has focus during form interactions

## Commands

### Default (Element Info)

```bash
# Get comprehensive info about the focused element
inspekt focused

# Output as JSON
inspekt focused --json
```

**Output includes:**
- Tag name and selector
- Accessibility information (role, name, focusable state)
- Dimensions and visibility
- Semantic information
- Computed styles

### text

Get the text content of the focused element.

```bash
# Formatted output with metadata table
inspekt focused text

# Raw text only (for piping)
inspekt focused text --raw

# Copy to clipboard
inspekt focused text --copy

# JSON output
inspekt focused text --json
```

**Output format:**
```
╭─────────────────────────────────╮
│        Element metadata         │
╞══════════╤══════════════════════╡
│ Tag      │ <input>               │
│ Depth    │ 4 levels from <html>  │
│ Text     │ 0 characters          │
│ Attributes│ 5 attributes         │
╰──────────┴──────────────────────╯

Selector  form#login > input#username
XPath     //*[@id="username"]

Text Content (0 characters):

```

For content exceeding 500 characters, a hint appears suggesting `--raw` for full content.

### markdown

Get the focused element as Markdown (converted from HTML).

```bash
# Formatted output
inspekt focused markdown

# Raw Markdown only
inspekt focused markdown --raw

# Copy to clipboard
inspekt focused markdown --copy
```

### html

Get the HTML of the focused element with optional CSS.

```bash
# Display HTML with syntax highlighting
inspekt focused html

# Save to auto-named file
inspekt focused html --file

# Save to specific file
inspekt focused html --file button.html

# Include computed CSS
inspekt focused html --file --include-css

# Bundle CSS into HTML
inspekt focused html --file --include-css --bundled

# Format and clean up
inspekt focused html --pretty --remove-comments
```

**Options:**

| Option | Description |
|--------|-------------|
| `--file [PATH]` | Save to file (auto-generates name if no path given) |
| `--open` | Open file in default app after saving |
| `--reveal` | Reveal file in file explorer after saving |
| `--include-css` | Also generate CSS file (requires --file) |
| `--bundled` | Embed CSS in HTML file (requires --include-css) |
| `--pretty` | Format HTML with indentation |
| `--compact` | Strip classes, data-* attrs, styles |
| `--remove-comments` | Remove HTML comments |
| `--copy` | Copy to clipboard |
| `--raw` | Output without syntax highlighting |

### css

Extract computed CSS styles from the focused element and all its children.

```bash
# Default optimized output
inspekt focused css

# With aligned columns
inspekt focused css --two-columns

# With helpful comments
inspekt focused css --heuristic-comments

# Convert colors to OKLCH
inspekt focused css --oklch

# Save to file
inspekt focused css --file styles.css

# Copy to clipboard
inspekt focused css --copy
```

**Options:**

| Option | Description |
|--------|-------------|
| `--file [PATH]` | Save to file (auto-generates name if no path given) |
| `--open` | Open file after saving |
| `--reveal` | Reveal in file explorer |
| `--copy` | Copy to clipboard |
| `--raw` | No syntax highlighting |
| `--all-properties` | Include all ~300 computed properties |
| `--include-defaults` | Include browser default values |
| `--optimize/--no-optimize` | Merge shorthands (default: on) |
| `--oklch` | Convert colors to OKLCH format |
| `--alphabetize/--no-alphabetize` | Sort properties (default: on) |
| `--rounding/--no-rounding` | Round pixel values (default: on) |
| `--heuristic-comments` | Add pattern-based comments |
| `--two-columns` | Align properties and values |
| `--three-columns` | Align properties, values, and comments |
| `--compact` | Shorten data URIs and long URLs |

## Error Handling

The command provides clear error messages for common focus issues:

### No Element Focused

```bash
$ inspekt focused
Error: No element currently focused
  Focus is on document body (no interactive element focused). Press Tab or
  click an input/button/link.
```

**Solution:** Press Tab to focus an interactive element, or click on an input, button, or link.

### Focus Inside Iframe

```bash
$ inspekt focused
Error: Focus is inside an iframe
  Cannot access focused element inside cross-origin iframes. Use browser
  DevTools to inspect iframe contents.
```

**Solution:** Use browser DevTools to inspect elements inside cross-origin iframes.

### Element Removed

```bash
$ inspekt focused
Error: Focused element has been removed from the page
  The element was removed from DOM while focused. This can happen with
  dynamic content.
```

**Solution:** Focus a different element that still exists in the DOM.

## Use Cases

### 1. Testing Keyboard Navigation

Monitor focus as you Tab through a page:

```bash
# In a loop, show which element has focus
while true; do
  inspekt focused --json 2>/dev/null | jq -r '.tag + " " + .selector'
  sleep 0.5
done
```

### 2. Verifying Skip Links

Test that skip links correctly move focus:

```bash
# Focus the skip link
inspekt do "click skip to content"

# Verify focus moved to main content
inspekt focused
# Should show: <main> or similar landmark
```

### 3. Focus Trap Testing

Ensure modal focus stays trapped:

```bash
# Open modal, then Tab repeatedly
inspekt focused --json | jq '.selector'
# Verify focus stays within modal container
```

### 4. Extracting Focused Form Field Styles

Copy styles from a focused input for prototyping:

```bash
# Tab to a form field
inspekt focused css --copy --two-columns
```

### 5. Debugging Focus Visibility

Check if focused element has visible focus styles:

```bash
inspekt focused css | grep -E 'outline|box-shadow|border'
```

### 6. Automated Accessibility Testing

Script focus testing with JSON output:

```bash
# Check if focused element has accessible name
inspekt focused --json | jq '.accessibility.accessibleName'

# Check if focused element is actually focusable
inspekt focused --json | jq '.accessibility.focusable'
```

## Shadow DOM Support

The `focused` command supports elements focused inside Shadow DOM. It uses a deep active element traversal:

```javascript
// Internal traversal logic
function getDeepActiveElement() {
  let active = document.activeElement;
  while (active && active.shadowRoot && active.shadowRoot.activeElement) {
    active = active.shadowRoot.activeElement;
  }
  return active;
}
```

This means focus inside custom elements (like those built with Lit, Polymer, or native Web Components) is correctly detected.

## Related Commands

- `inspekt inspected` - Get DevTools inspected element (different selection source)
- `inspekt watch keyboard` - Monitor all keyboard/focus events in real-time
- `inspekt do` - Execute natural language actions like "click the login button"
- `inspekt press` - Send keyboard keys to the browser

## See Also

- [Element Interaction Guide](../guide/element-interaction.md)
- [Accessibility Testing](../guide/accessibility-testing.md)
- [inspekt inspected css](./inspected-css.md)
