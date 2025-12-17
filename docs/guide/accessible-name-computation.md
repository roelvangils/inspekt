# Accessible Name Computation

Inspekt implements the W3C **Accessible Name and Description Computation 1.2** (ACCNAME 1.2) specification for computing accessible names of elements during recording and replay.

## Overview

When recording user interactions, Inspekt captures the accessible name of focused elements to provide meaningful feedback. This helps users understand which element is being interacted with, especially for elements that don't have visible text labels.

## ACCNAME 1.2 Compliance

Our implementation follows the priority order defined in the ACCNAME 1.2 specification:

### 1. aria-labelledby (Highest Priority)

If an element has `aria-labelledby`, we recursively compute the accessible name from each referenced element.

```html
<button aria-labelledby="label1 label2">...</button>
<span id="label1">Save</span>
<span id="label2">Document</span>
<!-- Accessible name: "Save Document" -->
```

### 2. aria-label

Direct aria-label attribute takes precedence over native HTML semantics.

```html
<button aria-label="Close dialog">X</button>
<!-- Accessible name: "Close dialog" -->
```

### 3. Host Language Label (HTML Semantics)

For form controls, we check associated `<label>` elements:

```html
<label for="email">Email address</label>
<input type="email" id="email">
<!-- Accessible name: "Email address" -->
```

### 4. Native Element Semantics

- **img/area**: `alt` attribute
- **input[type=image]**: `alt` attribute
- **input[type=button/submit/reset]**: `value` attribute
- **svg**: `<title>` child element

```html
<img src="logo.png" alt="Company Logo">
<!-- Accessible name: "Company Logo" -->
```

### 5. Name from Content

For elements with roles that support "name from content" (buttons, links, etc.), we recursively traverse child nodes:

```html
<a href="/products">
  <img src="icon.svg" alt="View">
  Products
</a>
<!-- Accessible name: "View Products" -->
```

### 6. CSS Pseudo-elements

We include text content from `::before` and `::after` pseudo-elements:

```html
<button class="icon-btn">Save</button>
<style>
  .icon-btn::before { content: "💾 "; }
</style>
<!-- Accessible name: "💾 Save" -->
```

### 7. Embedded Control Values

When computing name from content, embedded form controls contribute their current value:

```html
<label>
  Volume: <input type="range" value="50"> %
</label>
<!-- Accessible name: "Volume: 50 %" -->
```

### 8. title Attribute (Fallback)

The `title` attribute serves as a fallback when no other accessible name is available.

### 9. placeholder (Form Inputs Only)

For input and textarea elements, the `placeholder` attribute is used as a last resort.

## Hidden Element Handling

Per ACCNAME 1.2, hidden elements do not contribute to accessible names unless explicitly referenced via `aria-labelledby`. We check for:

- `hidden` HTML attribute
- `aria-hidden="true"`
- CSS `display: none`
- CSS `visibility: hidden`

## Implementation Details

The accessible name computation is implemented in two JavaScript files:

- `inspekt/scripts/record_events.js` - Used during recording
- `inspekt/scripts/replay_step.js` - Used during replay

### Key Functions

| Function | Purpose |
|----------|---------|
| `computeAccessibleName()` | Main entry point, implements priority cascade |
| `computeAccessibleNameFromContent()` | Recursive content traversal |
| `isEffectivelyHidden()` | CSS and ARIA hidden state detection |
| `getPseudoElementText()` | CSS pseudo-element content extraction |

## Supported Features

| Feature | Status |
|---------|--------|
| aria-labelledby (recursive) | ✅ Full support |
| aria-label | ✅ Full support |
| Associated `<label>` elements | ✅ Full support |
| `alt` for img/area/input[type=image] | ✅ Full support |
| `value` for button inputs | ✅ Full support |
| SVG `<title>` element | ✅ Full support |
| Name from content | ✅ Full support |
| CSS pseudo-elements | ✅ Full support |
| Embedded control values | ✅ Full support |
| CSS hidden detection | ✅ Full support |
| `title` attribute fallback | ✅ Full support |
| `placeholder` fallback | ✅ Full support |

## Example Usage

During recording with Tab navigation:

```
Tab → a (Logo)
Tab → button (Open Navigation Menu)
Tab → input (Search products)
Tab → a (View Cart)
```

The accessible names in parentheses are computed following the ACCNAME 1.2 specification, giving users clear feedback about which element is currently focused.

## References

- [W3C ACCNAME 1.2 Specification](https://www.w3.org/TR/accname-1.2/)
- [ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
