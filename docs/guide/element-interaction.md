# Element Interaction

Master element interaction in Inspekt. Learn how to click, inspect, highlight, wait for elements, send keyboard input, and take screenshots - all from your terminal.

## Overview

Inspekt provides specialized commands for interacting with page elements:

- `inspekt click` - Click elements
- `inspekt double-click` / `inspekt right-click` - Double-click and right-click
- `inspekt wait` - Wait for elements to appear/disappear
- `inspekt send` - Type text into elements
- `inspekt inspect` / `inspekt inspected` - Inspect elements
- `inspekt highlight` - Highlight elements visually
- `inspekt screenshot` - Screenshot elements

## Clicking Elements

### Basic Click

```bash
inspekt click "button#submit"
```

Clicks the first element matching the selector.

### Click Examples

```bash
# Click button by ID
inspekt click "#submit-btn"

# Click link by class
inspekt click ".nav-link"

# Click by complex selector
inspekt click "nav > ul > li:first-child > a"

# Click by attribute
inspekt click "[data-action='delete']"

# Click by text content (using eval)
inspekt eval "Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Submit')).click()"
```

### Using Inspected Element

You can click the currently inspected element (from DevTools):

```bash
# In DevTools, select an element ($0)
# In browser console: inspektStore($0)

# Then click it
inspekt click
# or explicitly
inspekt click "$0"
```

### Double Click

Double-click elements for actions that require it:

```bash
inspekt double-click "div.editable"
inspekt double-click ".file-item"
```

### Right Click (Context Menu)

Trigger context menus:

```bash
inspekt right-click "a.download-link"
inspekt right-click ".file-item"
```

!!! tip "Click Types"
    - `inspekt click` - Single left click
    - `inspekt double-click` - Double left click
    - `inspekt right-click` - Right click (context menu)

---

## Waiting for Elements

The `inspekt wait` command waits for elements to appear, become visible, become hidden, or contain specific text.

### Wait for Element to Exist

```bash
# Wait up to 30 seconds (default)
inspekt wait "button#submit"

# Custom timeout
inspekt wait ".modal" --timeout 10
```

### Wait for Element to be Visible

```bash
inspekt wait ".modal-dialog" --visible

# With custom timeout
inspekt wait ".notification" --visible --timeout 15
```

### Wait for Element to be Hidden

```bash
inspekt wait ".loading-spinner" --hidden

# Wait for modal to close
inspekt wait ".modal-overlay" --hidden --timeout 20
```

### Wait for Specific Text

```bash
# Wait for element with specific text
inspekt wait "div.result" --text "Success"

# Wait for error message
inspekt wait ".message" --text "Error" --visible
```

### Wait Use Cases

**Wait for page load:**
```bash
inspekt wait "main.content" --visible
```

**Wait for AJAX content:**
```bash
inspekt wait ".dynamic-content" --visible --timeout 20
```

**Wait for form validation:**
```bash
# Fill form
inspekt eval "document.querySelector('#email').value = 'test@example.com'"

# Submit
inspekt click "#submit-btn"

# Wait for success message
inspekt wait ".success-message" --visible
```

**Wait for loading to finish:**
```bash
# Click action that shows spinner
inspekt click ".load-more"

# Wait for spinner to disappear
inspekt wait ".spinner" --hidden
```

!!! warning "Timeout Default"
    Default timeout is **30 seconds**. Adjust with `--timeout` flag.

---

## Sending Keyboard Input

The `inspekt send` command types text character by character, simulating keyboard input.

### Basic Text Input

```bash
inspekt send "Hello World"
```

Types into the currently focused element.

### Send to Specific Element

```bash
# Type into email input
inspekt send "test@example.com" --selector "input[type=email]"

# Type into search box
inspekt send "query text" --selector "input[name=search]"

# Type into textarea
inspekt send "Multi-line text here" --selector "textarea#message"
```

### Form Filling Examples

**Login form:**
```bash
inspekt send "user@example.com" --selector "#email"
inspekt send "password123" --selector "#password"
inspekt click "#login-btn"
```

**Search form:**
```bash
inspekt send "Inspekt documentation" --selector "input[name=q]"
inspekt click "button[type=submit]"
```

**Comment form:**
```bash
inspekt send "Great article!" --selector "textarea#comment"
inspekt send "John Doe" --selector "input#name"
inspekt click "button#post-comment"
```

### Typing Speed

The `send` command types at a realistic speed (character by character). For instant value setting, use `inspekt eval`:

```bash
# Instant value (no events)
inspekt eval "document.querySelector('#email').value = 'test@example.com'"

# Typed input (fires input events)
inspekt send "test@example.com" --selector "#email"
```

!!! tip "Input Events"
    `inspekt send` fires proper keyboard events, which may trigger validation, autocomplete, and other event listeners.

---

## Inspecting Elements

### Inspect Element

Select and store an element for inspection:

```bash
inspekt inspect "h1"
```

**Output:**
```
Element: H1
Text: Welcome to Example
Classes: page-title, main-heading
ID: title
```

### Inspect by Selector

```bash
# By ID
inspekt inspect "#header"

# By class
inspekt inspect ".main-content"

# By complex selector
inspekt inspect "nav > ul > li:first-child > a"

# By attribute
inspekt inspect "[data-id='123']"
```

### Get Inspected Element Details

After inspecting an element, get detailed information:

```bash
inspekt inspected
```

**Output:**
```json
{
  "tagName": "H1",
  "textContent": "Welcome to Example",
  "id": "title",
  "className": "page-title main-heading",
  "attributes": {
    "id": "title",
    "class": "page-title main-heading",
    "data-section": "hero"
  },
  "boundingBox": {
    "x": 100,
    "y": 50,
    "width": 600,
    "height": 80
  }
}
```

### Using DevTools Integration

You can also store the currently selected element in DevTools:

1. Open DevTools (F12)
2. Select an element (inspect tool or click in Elements panel)
3. In console, run: `inspektStore($0)`
4. Then use: `inspekt inspected`

!!! tip "Workflow"
    Use `inspekt inspect` to find elements programmatically, or use DevTools + `inspektStore($0)` for visual selection.

---

## Highlighting Elements

Visually highlight elements on the page with colored outlines.

### Basic Highlight

```bash
inspekt highlight "h1, h2"
```

Highlights all matching elements with a red dashed outline.

### Custom Color

```bash
inspekt highlight "a" --color blue
inspekt highlight ".error" --color red
inspekt highlight ".success" --color green
inspekt highlight ".warning" --color orange
```

### Clear Highlights

```bash
inspekt highlight --clear
```

Removes all highlights from the page.

### Highlight Use Cases

**Debugging layout:**
```bash
inspekt highlight "div"
```

**Find all links:**
```bash
inspekt highlight "a" --color blue
```

**Highlight errors:**
```bash
inspekt highlight ".error-message" --color red
```

**Accessibility audit:**
```bash
# Highlight images without alt text
inspekt eval "
  document.querySelectorAll('img:not([alt])').forEach(img => {
    img.style.outline = '3px solid red';
  });
  'Highlighted images without alt text';
"
```

---

## Screenshots

Take screenshots of specific elements.

### Screenshot Element

```bash
inspekt screenshot --selector "h1" --output screenshot.png
```

### Screenshot Examples

```bash
# Screenshot by selector
inspekt screenshot --selector "#header" --output header.png

# Screenshot with auto-generated filename
inspekt screenshot --selector ".hero-section"

# Screenshot of inspected element
inspekt inspect "h1"
inspekt screenshot --selector "$0" --output title.png
```

### Screenshot Use Cases

**Visual regression testing:**
```bash
inspekt screenshot --selector ".hero" --output hero-$(date +%Y%m%d).png
```

**Documentation:**
```bash
inspekt screenshot --selector ".component-example" --output docs/component.png
```

**Bug reports:**
```bash
inspekt screenshot --selector ".error-dialog" --output bug-screenshot.png
```

!!! note "Screenshot Format"
    Screenshots are saved as PNG files. The `--output` flag is optional; a timestamp-based filename is generated if omitted.

---

## CSS Selectors Explained

Inspekt uses standard CSS selectors. Here's a quick reference:

### Basic Selectors

| Selector | Example | Description |
|----------|---------|-------------|
| Element | `div` | Select by tag name |
| Class | `.button` | Select by class |
| ID | `#submit` | Select by ID |
| Attribute | `[type="text"]` | Select by attribute |
| Universal | `*` | Select all elements |

### Combinators

| Combinator | Example | Description |
|------------|---------|-------------|
| Descendant | `div p` | All `<p>` inside `<div>` |
| Child | `div > p` | Direct children only |
| Adjacent sibling | `h1 + p` | `<p>` immediately after `<h1>` |
| General sibling | `h1 ~ p` | All `<p>` siblings after `<h1>` |

### Pseudo-classes

| Pseudo-class | Example | Description |
|--------------|---------|-------------|
| `:first-child` | `li:first-child` | First child element |
| `:last-child` | `li:last-child` | Last child element |
| `:nth-child(n)` | `li:nth-child(2)` | Nth child element |
| `:not(selector)` | `:not(.active)` | Elements not matching |
| `:hover` | `a:hover` | Hovered elements |

### Complex Selectors

```bash
# Multiple classes
inspekt click ".button.primary"

# Attribute with value
inspekt click "[data-action='submit']"

# Attribute contains
inspekt click "[class*='modal']"

# Attribute starts with
inspekt click "[id^='btn-']"

# Attribute ends with
inspekt click "[href$='.pdf']"

# Multiple selectors
inspekt highlight "h1, h2, h3"

# Complex combination
inspekt click "nav > ul > li:first-child > a.active"
```

---

## Interactive Examples

### Example 1: Form Automation

```bash
# Fill login form
inspekt send "user@example.com" --selector "#email"
inspekt send "password123" --selector "#password"
inspekt click "#remember-me"
inspekt click "#login-btn"

# Wait for redirect or error
inspekt wait ".dashboard, .error-message" --visible --timeout 10
```

### Example 2: Modal Interaction

```bash
# Open modal
inspekt click "#open-modal"

# Wait for modal to appear
inspekt wait ".modal-dialog" --visible

# Interact with modal
inspekt send "Test message" --selector ".modal textarea"
inspekt click ".modal button.confirm"

# Wait for modal to close
inspekt wait ".modal-dialog" --hidden
```

### Example 3: Dynamic Content

```bash
# Click "Load More" button
inspekt click ".load-more"

# Wait for spinner to disappear
inspekt wait ".loading-spinner" --hidden

# Count new items
inspekt eval "document.querySelectorAll('.item').length"
```

### Example 4: Multi-step Flow

```bash
# Step 1: Fill first form
inspekt send "John" --selector "#first-name"
inspekt send "Doe" --selector "#last-name"
inspekt click "#next-btn"

# Step 2: Wait and fill second form
inspekt wait "#email" --visible
inspekt send "john@example.com" --selector "#email"
inspekt send "1234567890" --selector "#phone"
inspekt click "#submit-btn"

# Step 3: Wait for confirmation
inspekt wait ".success-message" --visible --text "Success"
```

### Example 5: Visual Testing

```bash
# Highlight all buttons
inspekt highlight "button" --color blue

# Inspect specific button
inspekt inspect "button.primary"

# Take screenshot
inspekt screenshot --selector "button.primary" --output button.png

# Clear highlights
inspekt highlight --clear
```

---

## Advanced Patterns

### Conditional Clicking

```bash
# Click only if element exists
inspekt eval "
  const button = document.querySelector('#optional-btn');
  if (button) {
    button.click();
    return 'Clicked';
  }
  return 'Button not found';
"
```

### Click All Matching Elements

```bash
# Click all checkboxes
inspekt eval "
  document.querySelectorAll('input[type=checkbox]').forEach(cb => cb.click());
  return 'Clicked all checkboxes';
"
```

### Wait with Polling

```bash
inspekt eval "
  async function waitForElement(selector, timeout = 30000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const element = document.querySelector(selector);
      if (element) return element;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error('Timeout');
  }

  const element = await waitForElement('.dynamic-content');
  return element.textContent;
"
```

### Hover Simulation

```bash
inspekt eval "
  const element = document.querySelector('.menu-item');
  const event = new MouseEvent('mouseover', {
    bubbles: true,
    cancelable: true,
    view: window
  });
  element.dispatchEvent(event);
  return 'Hovered over element';
"
```

### Focus and Blur

```bash
# Focus element
inspekt eval "document.querySelector('#email').focus()"

# Blur element
inspekt eval "document.querySelector('#email').blur()"

# Type after focusing
inspekt eval "document.querySelector('#email').focus()"
inspekt send "test@example.com" --selector "#email"
```

---

## Troubleshooting

### Element Not Found

**Error:**
```
Error: Element not found: .missing-selector
```

**Solutions:**
1. Verify selector is correct
2. Wait for element to load: `inspekt wait ".selector" --visible`
3. Check if element is in iframe (not supported directly)
4. Use DevTools to test selector

### Click Not Working

**Possible causes:**
- Element is not visible
- Element is disabled
- JavaScript event handler expecting different event
- Element is covered by another element

**Solutions:**
```bash
# Check if visible
inspekt eval "document.querySelector('.btn')?.offsetParent !== null"

# Check if disabled
inspekt eval "document.querySelector('.btn')?.disabled"

# Force click with JavaScript
inspekt eval "document.querySelector('.btn').click()"

# Dispatch click event
inspekt eval "document.querySelector('.btn').dispatchEvent(new MouseEvent('click', {bubbles: true}))"
```

### Element Changes After Action

Some elements are replaced after interaction (e.g., React re-renders). Re-select after action:

```bash
# Wrong - selector may be stale
inspekt click ".btn"
inspekt eval "document.querySelector('.btn').textContent"

# Correct - re-select after action
inspekt click ".btn"
inspekt wait ".success-message" --visible
inspekt eval "document.querySelector('.success-message').textContent"
```

---

## Best Practices

### 1. Use Specific Selectors

```bash
# Good - specific
inspekt click "#submit-btn"
inspekt click "[data-testid='submit-button']"

# Avoid - too generic
inspekt click "button"
inspekt click ".btn"
```

### 2. Wait Before Interacting

```bash
# Good - wait for element
inspekt wait "#modal" --visible
inspekt click "#modal .confirm-btn"

# Risky - element may not exist yet
inspekt click "#modal .confirm-btn"
```

### 3. Handle Errors Gracefully

```bash
# Use optional chaining
inspekt eval "document.querySelector('.maybe-missing')?.click() ?? 'Element not found'"
```

### 4. Verify Actions

```bash
# Click and verify
inspekt click "#submit-btn"
inspekt wait ".success-message" --visible --text "Saved"
```

---

## Next Steps

- **[Data Extraction](data-extraction.md)** - Extract structured data from pages
- **[Control Mode](control-mode.md)** - Keyboard-only navigation
- **[Advanced Usage](advanced.md)** - Complex patterns and scripting

---

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `inspekt click "selector"` | Click element | `inspekt click "#submit"` |
| `inspekt double-click "selector"` | Double-click | `inspekt double-click ".file"` |
| `inspekt right-click "selector"` | Right-click | `inspekt right-click ".context"` |
| `inspekt wait "selector"` | Wait for element | `inspekt wait ".modal" --visible` |
| `inspekt send "text"` | Type text | `inspekt send "hello" --selector "#input"` |
| `inspekt inspect "selector"` | Inspect element | `inspekt inspect "h1"` |
| `inspekt inspected` | Get inspected details | `inspekt inspected` |
| `inspekt highlight "selector"` | Highlight elements | `inspekt highlight "a" --color blue` |
| `inspekt screenshot --selector` | Screenshot element | `inspekt screenshot --selector "h1"` |
