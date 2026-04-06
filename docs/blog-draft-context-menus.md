# Building macOS-Native Context Menus for the Web: Squircles, Safe Triangles, and Stolen Ideas

*How we rebuilt Apple's context menu system from scratch — and what we discovered about a 40-year-old invention along the way.*

---

## Why Custom Context Menus?

Inspekt VM is a browser inside a browser. It runs Chromium in a Docker container and streams it to your screen via noVNC — a web-based VNC client. The control panel around it (tab bar, toolbar, address bar) is a regular web page. But when you right-click on the VNC canvas, you're not right-clicking *in* the virtual browser — you're right-clicking on a `<canvas>` element in the control panel.

The browser's default context menu ("Inspect Element", "View Page Source") targets the control panel page, not the website being tested inside the VM. So we needed our own.

The goal: make these custom menus **indistinguishable from native macOS menus**. Not "inspired by" — pixel-perfect.

---

## The CSS: Vibrancy, Squircles, and AccentColor

### Platform Detection

We detect the host OS with a tiny inline script in `<head>` (before CSS renders) and set a class on `<html>`:

```js
const _platform = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)
    ? 'macos' : /Win/.test(navigator.platform || navigator.userAgent)
    ? 'windows' : 'other';
document.documentElement.classList.add('os-' + _platform);
```

This lets us write `.os-macos .context-menu { ... }` for macOS-specific styles and `.os-windows .context-menu { ... }` for Windows — completely separate visual targets from the same structural CSS.

### Every Value is a Variable

All visual parameters are CSS custom properties, defined per platform:

```css
.os-macos .context-menu {
    --menu-bg: rgba(30, 30, 30, 0.78);
    --menu-blur: blur(50px) saturate(190%);
    --menu-radius: 6px;
    --menu-accent: AccentColor;
    --menu-item-height: 24px;
    --menu-item-radius: 7px;
    /* ... 20+ more variables */
}
```

This makes pixel-matching iterative: open a native macOS menu next to ours, spot a difference, tweak a single variable, reload.

### The AccentColor Keyword

Here's a CSS feature most developers don't know about: the `AccentColor` keyword. It reads the user's **actual system accent color** from macOS System Settings → Appearance. If they've changed it from blue to purple, `AccentColor` resolves to purple.

```css
--menu-accent: AccentColor;

@supports not (color: AccentColor) {
    --menu-accent: #0A82FF;  /* Fallback: macOS default blue */
}
```

Supported in Chrome 93+ and Safari 15.4+.

### Squircles in CSS

macOS uses G2-continuous curves (squircles) for its rounded corners — not circular `border-radius`. These curves are smoother, with no "kink" at the transition point. As of Chrome 139, CSS supports this:

```css
.os-macos .context-menu {
    --menu-radius: 6px;
    --menu-corner-shape: round;  /* Fallback */
}

@supports (corner-shape: squircle) {
    .os-macos .context-menu {
        --menu-radius: 21px;
        --menu-corner-shape: squircle;
    }
}
```

The `21px` value with `squircle` produces the same visual curve as `6px` with circular `border-radius`. It's a different number because the squircle algorithm interprets the radius differently.

### Vibrancy and the Double Border

macOS menus are translucent with a blur effect (Apple calls it "vibrancy"):

```css
background: rgba(30, 30, 30, 0.78);
backdrop-filter: blur(50px) saturate(190%);
```

They also have a subtle double border — an inner light stroke and an outer dark stroke:

```css
border: 1px solid rgba(255, 255, 255, 0.5);
outline: 0.5px solid rgba(0, 0, 0, 0.7);
```

Using `border` for the inner and `outline` for the outer avoids the `box-shadow` inset approach, which interferes with the blur.

---

## Focus as the Single Source of Truth

Early on, we had a bug: hovering a menu item showed a `:hover` highlight, and pressing an arrow key showed a `:focus` highlight. **Two items appeared selected at the same time.**

We tried a `keyboard-nav` CSS class that toggled between hover and focus styles. It worked, but added complexity — tracking whether the last interaction was mouse or keyboard, removing the class on mouse move, restoring it on key press.

Then we realized: **just use `:focus` for everything.** Focus items on `mouseenter` instead of relying on `:hover`. One mechanism, one highlight, zero ambiguity. And because focused elements are announced by screen readers, accessibility came for free.

```css
/* No :hover styles at all — only :focus */
.context-menu [role="menuitem"]:focus {
    background: var(--menu-accent);
    color: var(--menu-text-selected);
}
```

```js
// Mouse enter focuses the item (same as keyboard arrow)
btn.addEventListener('mouseenter', () => {
    btn.focus({ preventScroll: true });
});
```

When the mouse leaves the menu, focus returns to the menu container. No item is highlighted. When the mouse re-enters or an arrow key is pressed, one item gets focused. Always zero or one — never two.

---

## The Selection Flicker

On macOS, clicking a menu item produces a distinctive blink — the highlight flashes off and on 2-3 times before the menu dismisses. It's subtle, but when it's missing, the menu feels "off."

```css
@keyframes menuItemFlicker {
    0%   { background: var(--menu-accent); color: var(--menu-text-selected); }
    25%  { background: transparent;        color: var(--menu-text); }
    50%  { background: var(--menu-accent); color: var(--menu-text-selected); }
    75%  { background: transparent;        color: var(--menu-text); }
    100% { background: var(--menu-accent); color: var(--menu-text-selected); }
}
```

The `steps(1)` timing function makes the transitions discrete (no smooth fading), and the menu dismisses after 160ms. A stale-menu guard prevents a timeout from dismissing a *different* menu that was opened during the animation.

This is macOS-only — on Windows, items just dismiss instantly.

---

## Keyboard Navigation: Matching Every Detail

Native macOS menus have specific keyboard behaviors that most web implementations get wrong:

- **No preselection.** The menu opens with no item highlighted. The first ArrowDown focuses the first item.
- **No cycling.** ArrowDown at the bottom doesn't wrap to the top. It stops.
- **Home/End/PageUp/PageDown** jump to the first or last item.
- **Type-ahead.** Press "S" to jump to the first item starting with "S."
- **Escape** closes the deepest submenu first, then the root menu.

The hardest part was making Escape work when the VNC canvas had focus. noVNC's keyboard handler intercepts key events on the canvas and sends them to the VM — Escape never bubbles up to our menu dismiss handler. The fix: a **capture-phase** listener that fires before noVNC:

```js
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _isMenuOpen()) {
        e.preventDefault();
        e.stopImmediatePropagation();
        dismissContextMenu();
    }
}, true);  // capture phase
```

We also added keyboard-triggered context menus: **Control+Return** (macOS Sequoia), **Shift+F10** (Windows/Linux), and the **ContextMenu key** (Windows keyboards). These use `document.elementFromPoint()` with globally-tracked mouse coordinates to determine which UI area the cursor is over, then dispatch to the appropriate menu handler.

---

## Submenus: The Menu Stack

Flat menus use a single `activeContextMenu` variable. Submenus need a stack:

```js
let _menuStack = [];  // [{ el, parentItem, lastIdx, safeZoneActive }]
```

Index 0 is the root menu. Each subsequent entry is a submenu opened from the previous level. Max depth: 3 (root + 2 submenu levels).

When a submenu opens, its parent item transitions through two visual states:

1. **`.submenu-parent-open`** — Full accent highlight (same as `:focus`). Applied immediately so there's no visual gap between the parent losing focus and the submenu appearing.
2. **`.submenu-parent-active`** — Dimmed 50% accent with dark text. Applied when focus actually enters the submenu (mouse or keyboard).

This two-state approach was born from a bug: the parent item's highlight disappeared entirely between submenu open and submenu entry. Users saw a flash of "nothing selected."

---

## The Triangle Safe Zone: An Apple Invention from 1986

### The Problem

Hover "Open Recent" and its submenu appears to the right. Now try to click "archive.zip" at the bottom of the submenu. Your mouse moves diagonally — and crosses over "Save" and "Export As" in the parent menu. Each crossing closes the submenu and maybe opens a different one. Frustrating.

### The History

This problem was first solved at **Apple in 1986** by Bruce "Tog" Tognazzini and Jim Batson on the Human Interface Device team. Their solution: an invisible triangular "safe zone" from the cursor to the submenu's edges. While the mouse is inside the triangle, hovering other parent items doesn't close the submenu.

Then Apple **removed it in macOS X** (1999), in one of those baffling regressions that make longtime Mac users question everything. Mayank Rajput describes it as *"making the user experience objectively worse."*

In 2013, **Ben Kamens published a viral blog post** reverse-engineering Amazon's mega-dropdown menu, which used the same triangle technique. Amazon had independently rediscovered (or borrowed) Apple's 1986 invention for their web megamenus. The post made the technique famous in the web development community.

Modern macOS has since **re-added the safe triangle**, bringing the invention full circle after a 20+ year detour.

### Our Implementation

We use the **cross-product sign test** for point-in-triangle detection — six multiplications and six comparisons, no trigonometry:

```js
function _pointInTriangle(px, py, ax, ay, bx, by, cx, cy) {
    const d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by);
    const d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy);
    const d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay);
    return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
}
```

The triangle's three vertices:
1. **Anchor:** The mouse position at the exact moment the submenu opens — a snapshot that stays fixed. This is where the user was when the submenu appeared, and the triangle fans out from this point. If the user was near the right edge of the parent item, the triangle is narrow (precise). If they were further left, it's wider (more forgiving).
2. **Top corner:** The submenu's near-side top
3. **Bottom corner:** The submenu's near-side bottom

We tried several anchor strategies before settling on this one. Using the parent item's edge created degenerate (zero-width) triangles because the edge coincided with the submenu's near edge due to the 5px overlap. Using the item center was stable but didn't adapt to where the user actually was. The mouse snapshot is the most natural — it represents the actual starting point of the diagonal movement.

### The macOS Twist

Apple adds one behavior that Amazon doesn't: **safe zone cancellation.** When you enter the submenu and then move your mouse back to the parent menu, the safe zone is disabled. The next time you hover a different parent item, the submenu closes immediately — no triangle protection.

This prevents menus from getting "stuck" open. Without cancellation, the triangle could keep a submenu alive long after the user clearly intended to move elsewhere.

We track this with a `safeZoneActive` flag on each menu stack entry, toggled by `mouseenter`/`mouseleave` on the submenu.

### Debug Visualization

During development, we added a `_DEBUG_TRIANGLE` flag that draws the safe zone as a colored SVG overlay: green when the cursor is inside (protected), red when outside (submenu will close). This made it easy to tune the triangle geometry — a tool we'd recommend to anyone implementing this pattern.

---

## Scroll Arrows, Not Scrollbars

When a native macOS menu has too many items to fit on screen, it shows small ▲/▼ arrows at the top and bottom edges — not a scrollbar. Hovering the arrows scrolls the menu at 60fps:

```js
let _scrollInterval = null;
scrollUp.addEventListener('mouseenter', () => {
    _scrollInterval = setInterval(() => {
        scrollContainer.scrollTop -= 4;
    }, 16);  // ~60fps
});
```

The scroll container uses `overflow: hidden` (not `auto`) because we handle scrolling manually through the arrows.

---

## Accessibility: Not an Afterthought

Every menu element has proper ARIA attributes:

- `role="menu"` on containers with `aria-label`
- `role="menuitem"` on items with `aria-disabled="true"` for disabled state
- `role="menuitemcheckbox"` with `aria-checked` for toggles
- `role="separator"` for dividers
- `role="presentation"` for section headers
- `aria-haspopup="menu"` and `aria-expanded` for submenu parents

Because we use focus (not hover) as the selection mechanism, screen readers announce the active item correctly at all times. Keyboard navigation works identically to mouse navigation — the same `focusin` handler drives both.

---

## What's Next

We'll be building Windows-style menus (Fluent Design) using the same `--menu-*` CSS variable architecture. The structural code stays identical — only the platform section changes.

We're also exploring whether a **curved safe zone** (like a cone or wedge with smooth edges) would work better than a strict triangle for diagonal movement. Some implementations use SVG paths with curves, which are more forgiving for imprecise mouse movement.

And of course, none of this helps on touch devices — where the "right-click" interaction doesn't exist. That's a different challenge entirely.

---

*The techniques described here are part of the [Inspekt](https://inspekt.dev) browser testing tool. The context menu system is implemented in a single HTML file — all CSS, JavaScript, and ARIA in one place — making it easy to study and adapt.*

### References

- [Breaking down Amazon's mega dropdown](https://bjk5.com/post/44698559168/breaking-down-amazons-mega-dropdown) — Ben Kamens (2013)
- [Better Context Menus With Safe Triangles](https://www.smashingmagazine.com/2023/08/better-context-menus-safe-triangles/) — Smashing Magazine
- [Hover triangles](https://mayank.co/blog/hover-triangles/) — Mayank Rajput
- [No More Menu Rage: useSafeArea](https://www.rippling.com/blog/no-more-menu-rage-smooth-navigation-with-usesafearea) — Rippling Engineering
- [The Ingenious Engineering Trick That Makes Amazon Menus Usable](https://www.technologyreview.com/2013/03/09/179477/the-ingenious-engineering-trick-that-makes-amazon-menus-usable/) — MIT Technology Review
- [WAI-ARIA Menu Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/menu/) — W3C Authoring Practices
