# Keyboard Focus Replay: How Inspekt Achieves Faithful Tab Navigation

Inspekt's Tab key replay goes far beyond what traditional browser automation tools like Puppeteer, Playwright, or Selenium can achieve. This document explains the technical challenges of keyboard focus replay and how Inspekt solves them.

## The Problem with Traditional Automation

When you press Tab in a browser, several things happen:

1. **Browser focus moves** to the next focusable element
2. **`:focus` CSS pseudo-class** activates on the new element
3. **`:focus-visible`** activates if keyboard navigation is detected
4. **Hidden elements become visible** (skip links, sr-only elements)
5. **Focus rings appear** using the site's native styling

Traditional automation tools fail to reproduce this faithfully:

| Tool | How it handles Tab | What's missing |
|------|-------------------|----------------|
| **Puppeteer** | `page.keyboard.press('Tab')` | No visual focus indicators, `:focus-visible` doesn't trigger |
| **Playwright** | `page.keyboard.press('Tab')` | Same issues as Puppeteer |
| **Selenium** | `sendKeys(Keys.TAB)` | Focus often doesn't move correctly, no visual feedback |
| **Cypress** | `cy.tab()` (plugin) | Synthetic events, limited CSS activation |

### Why This Matters for Accessibility Testing

If you're testing keyboard accessibility, you need to see:
- Which elements receive focus
- Whether focus indicators are visible
- Whether skip links appear when focused
- Whether focus order matches expectations

Without faithful focus reproduction, automated accessibility testing misses critical issues.

---

## Inspekt's Multi-Tier Approach

Inspekt uses a sophisticated multi-tier system to ensure faithful Tab replay:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tab Key Pressed During Replay                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 0: Force Visibility                                       │
│  ─────────────────────────────────────────────────────────────  │
│  Make hidden elements visible (skip links, sr-only)             │
│  Smart detection: only override off-screen positioning          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 1: CDP Key Dispatch                                       │
│  ─────────────────────────────────────────────────────────────  │
│  Send real Tab via Chrome DevTools Protocol                     │
│  Browser handles focus movement authentically                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 2: Focus Detection                                        │
│  ─────────────────────────────────────────────────────────────  │
│  Try: focusin events → :focus selector → step target fallback   │
│  Works even when document.hasFocus() is false                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 3: Native Focus Styling Check                             │
│  ─────────────────────────────────────────────────────────────  │
│  Check if :focus-visible is already showing                     │
│  If yes → done (keyboard modality worked)                       │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 4: CSS Polyfill                                           │
│  ─────────────────────────────────────────────────────────────  │
│  Clone site's :focus/:focus-visible rules                       │
│  Apply via [data-inspekt-focus-visible] attribute               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  TIER 5: Overlay Fallback                                       │
│  ─────────────────────────────────────────────────────────────  │
│  If all else fails, show coordinate-based focus ring            │
│  Works for Shadow DOM components that resist styling            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technical Deep Dive

### 1. CDP for Authentic Focus Movement

Unlike synthetic JavaScript events, Inspekt uses Chrome DevTools Protocol to send real keyboard events:

```javascript
// Puppeteer/Playwright approach (synthetic)
await page.keyboard.press('Tab');
// Problem: Browser may not update internal focus state correctly

// Inspekt approach (authentic)
await chrome.debugger.sendCommand(target, 'Input.dispatchKeyEvent', {
    type: 'keyDown',
    key: 'Tab',
    code: 'Tab',
    // ... native key properties
});
```

**Why CDP is better:**
- Focus moves exactly as it would with a real keypress
- Browser's internal tab order algorithm is used
- Works with Shadow DOM focus delegation
- Triggers focus trap handlers correctly

### 2. The `document.hasFocus()` Problem

When replay runs from a CLI, the terminal has OS-level focus, not the browser. This means:

```javascript
document.hasFocus()        // false
document.activeElement     // returns BODY (useless)
document.querySelector(':focus')  // returns null
```

**Inspekt's solution: Step Target Fallback**

The recording already captured which element receives focus. We use that information:

```javascript
// CDP moved focus, but we can't detect it via DOM APIs
// Fall back to the recorded target
if (!focusedElement && step.target?.selector) {
    const findResult = findElement(step.target);
    if (findResult.element) {
        focusedElement = findResult.element;
    }
}
```

### 3. Force Visibility for Hidden Elements

Skip links and screen-reader-only elements use CSS tricks to hide themselves:

```css
.u-sr-only {
    position: absolute;
    clip: rect(1px, 1px, 1px, 1px);
    width: 1px;
    height: 1px;
    overflow: hidden;
}

.u-sr-only:focus {
    position: static;
    clip: auto;
    width: auto;
    height: auto;
}
```

The `:focus` rules don't apply during replay (because `document.hasFocus()` is false). Inspekt forces visibility using a **smart detection approach**:

**Tier 0: Conditional Force Visibility**

Visibility overrides are only applied to elements that are **actually hidden** using sr-only patterns. Regular visible elements are left untouched to preserve their styling:

```javascript
// Detect if element is hidden using sr-only patterns
const isLikelyHidden = (
    computed.display === 'none' ||
    computed.visibility === 'hidden' ||
    computed.opacity === '0' ||
    (parseFloat(computed.width) <= 1 && parseFloat(computed.height) <= 1) ||
    computed.clip.includes('rect') ||
    computed.clipPath === 'inset(100%)' ||
    (computed.position === 'absolute' && parseFloat(computed.left) < -9000)
);

// Only apply to hidden elements
if (isLikelyHidden) {
    const forceVisibleStyles = {
        'clip': 'auto',
        'clip-path': 'none',
        'width': 'auto',
        'height': 'auto',
        'overflow': 'visible',
        'opacity': '1',
        'visibility': 'visible'
    };
    // Applied with !important to override hiding CSS
    element.style.setProperty(prop, value, 'important');
}
```

This ensures regular elements (buttons, links) rely solely on the CSS polyfill for focus styling, while hidden elements (skip links, sr-only) get visibility overrides.

**Tier 2: Layout via CSS Polyfill (not inline)**

We intentionally do NOT set `position`, `left`, `top`, or `margin` inline. Instead, the CSS polyfill handles layout:

```javascript
// Original hiding CSS:
.sr-only { position: absolute; left: -9999px; }  // specificity (0,1,0)

// Polyfill creates cloned rule with higher specificity:
.sr-only[data-inspekt-focus-visible] { position: static; }  // specificity (0,2,0)
```

**Key insight:** Setting position inline would override the polyfill (inline styles beat external CSS). By leaving layout to the polyfill, we preserve the site's exact `:focus` positioning styles.

**Tier 2.5: Record-Time Style Capture**

Some sites store their sr-only `:focus` rules in **cross-origin stylesheets** (e.g., CDN-hosted CSS). JavaScript can't read these due to CORS security, so the polyfill has no rules to clone.

Different sites use completely different techniques to reveal hidden elements:
- **VDAB**: Uses `margin: 18px 0 0 18px` to offset from corner
- **bol.com**: Uses `padding` and removes `clip-path`, stays at position 0,0
- **Bootstrap**: Uses various techniques depending on version

**The Solution: Capture During Recording**

Instead of guessing styles at replay time, Inspekt now captures the **exact computed styles** of sr-only elements during recording, while they are focused and visible:

```yaml
# Recording captures focus_styles for sr-only elements
- timestamp: 11112
  action: keypress
  target:
    selector: '#js--skip-links-menu-main-content'
    accessible_name: Ga naar de inhoud
    tag: a
    focus_styles:  # Captured while element was focused
      position: absolute
      margin: 18px 0px 0px 18px
      padding: 0px
      clip: auto
      clipPath: none
      width: auto
      height: auto
  key: Tab
```

**During Replay**: The captured `focus_styles` are applied exactly, ensuring the element looks identical to how it appeared during recording:

```javascript
if (step.target?.focus_styles) {
    // Apply the exact styles that were captured during recording
    for (const [prop, value] of Object.entries(step.target.focus_styles)) {
        focusedElement.style.setProperty(prop, value, 'important');
    }
}
```

**Backwards Compatibility**: Older recordings without `focus_styles` fall back to visibility-only fixes (Tier 0), which make elements visible but don't guess at positioning.

### 4. CSS Rule Cloning Polyfill

Inspekt scans all stylesheets and clones `:focus` and `:focus-visible` rules:

```javascript
// Original site CSS
.btn:focus-visible {
    outline: 2px solid blue;
}

// Inspekt creates a clone
.btn[data-inspekt-focus-visible] {
    outline: 2px solid blue;
}
```

When an element receives Tab focus, we add the `data-inspekt-focus-visible` attribute, and the cloned rules apply the site's exact focus styling.

**Smart Rule Filtering:**

The polyfill filters out rules that *remove* focus styling (like CSS resets):

```css
/* These rules are NOT cloned - they hide focus indicators */
a:focus { outline: none; }
button:focus { box-shadow: none; }

/* These rules ARE cloned - they add visible focus indicators */
a:focus { box-shadow: 0 0 0 3px blue; }
button:focus-visible { outline: 2px solid currentColor; }
```

This prevents "reset" rules from overriding the polyfill's fallback focus indicator.

**This works for:**
- `:focus` rules (skip link visibility)
- `:focus-visible` rules (keyboard focus indicators)
- Rules inside `@media` queries
- Rules inside `@layer` blocks
- Shadow DOM stylesheets

### 5. Shadow DOM Support

Web Components with Shadow DOM encapsulate their styles. Inspekt handles this throughout the recording and replay lifecycle:

**During Recording:**
1. **Deep active element detection** - `document.activeElement` returns the shadow host, not the inner element. Inspekt's `getDeepActiveElement()` drills down via `shadowRoot.activeElement`
2. **Piercing selectors** - Records both inner selector AND shadow host path: `"#shadow-host >>> .inner-button"`
3. **Full target info** - Captures `shadow_host` and `piercing_selector` fields for Shadow DOM elements

```yaml
# Recording captures Shadow DOM path
- timestamp: 3500
  action: keypress
  target:
    selector: 'button.access-menu-toggle__button'
    shadow_host: 'div.vl-global-header'
    piercing_selector: 'div.vl-global-header >>> button.access-menu-toggle__button'
    accessible_name: Aanmelden
  key: Tab
```

**During Replay:**
1. **Scans Shadow DOMs** for focus-related CSS rules
2. **Injects polyfill styles** into each Shadow Root
3. **Uses piercing selectors** to find elements inside Shadow DOM
4. **Falls back to overlay** when Shadow DOM resists attribute-based styling

```javascript
// Find element inside Shadow DOM using piercing selector
function findWithPiercingSelector(selector) {
    const parts = selector.split(' >>> ');
    let current = document.querySelector(parts[0]);
    for (let i = 1; i < parts.length && current; i++) {
        current = current.shadowRoot?.querySelector(parts[i]);
    }
    return current;
}
```

### 6. Cleanup Between Steps

When focus moves to the next element, Inspekt cleans up:

```javascript
// Before each Tab step, restore previous element's styles
const prevForceVisible = document.querySelectorAll('[data-inspekt-force-visible]');
for (const el of prevForceVisible) {
    if (el._inspektRestoreStyles) {
        el._inspektRestoreStyles();  // Restore original inline styles
    }
}
```

This ensures:
- Skip links hide again when focus moves away
- No style pollution between steps
- Page looks correct at each step

---

## Comparison: Inspekt vs. Traditional Tools

| Feature | Puppeteer | Playwright | Selenium | Inspekt |
|---------|-----------|------------|----------|---------|
| Real Tab key events | Synthetic | Synthetic | Synthetic | **CDP (real)** |
| `:focus-visible` triggers | No | No | No | **Yes (polyfill)** |
| Skip links become visible | No | No | No | **Yes (force-visible)** |
| Site's focus styles shown | No | No | No | **Yes (CSS cloning)** |
| Shadow DOM focus | Partial | Partial | No | **Full support** |
| Works without browser focus | No | No | No | **Yes (step target fallback)** |
| Focus ring overlay fallback | No | No | No | **Yes** |

---

## Real-World Example: VDAB.be Skip Links

The VDAB website has skip navigation links that:
1. Are hidden using `clip: rect(1px, 1px, 1px, 1px)` and `width: 1px`
2. Become visible on `:focus` with proper positioning
3. Show the site's focus styling (blue outline)

**With Puppeteer:**
```
Tab → (nothing visible happens) → Tab → (nothing visible)
```

**With Inspekt:**
```
Tab → "Ga naar de inhoud" appears in top-left with blue outline
Tab → "Vind een job" appears with focus styling
Tab → "Vind een opleiding" appears...
```

---

## Configuration

Focus visibility features are enabled by default during replay. No configuration needed.

For debugging, you can check the browser console for:
```
[Inspekt FocusVisible] Injected 19 focus polyfill rules
```

---

## Summary

Inspekt's keyboard focus replay is built on the principle of **faithful reproduction**. Every technique we use is designed to make replay look exactly like real keyboard navigation:

1. **CDP dispatch** for authentic focus movement
2. **Step target fallback** when browser APIs fail
3. **Smart force-visibility** for hidden elements
4. **CSS rule cloning** for site-native focus styles
5. **Shadow DOM injection** for web components
6. **Overlay fallback** as last resort

This makes Inspekt the only browser automation tool that can accurately test keyboard accessibility by showing exactly what a keyboard user would see.
