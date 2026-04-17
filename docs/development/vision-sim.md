# Vision Simulator — Technical Reference

The vision simulator applies real-time vision impairment simulations on the VNC canvas in the Inspekt VM control panel. All effects run on the host browser's GPU — the remote Chromium session is completely unaware of them.

## Architecture

```
┌─ Host Browser ──────────────────────────────────────────────┐
│                                                              │
│  #vncContainer (position: relative)                          │
│  ├── <canvas> ← VNC stream (always unmodified)               │
│  ├── CSS filter: url(#svg-filter) blur(...)                  │
│  │   └── Applied to the container, affects all children      │
│  └── #visionFieldOverlay (for tunnel vision / scotoma only)  │
│       ├── backdrop-filter: blur(Npx)                         │
│       ├── background: rgba(0,0,0,...)                        │
│       └── mask-image: radial-gradient(...)                   │
│                                                              │
│  <svg> (hidden, in <body>)                                   │
│  └── <defs> with all <filter> definitions                    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Two rendering paths:**

1. **Color/acuity simulations** — CSS `filter` on `#vncContainer` referencing SVG `<filter>` definitions and/or CSS filter functions (`blur()`, `contrast()`, etc.)
2. **Visual field simulations** — A `<div>` overlay with `backdrop-filter: blur()` and a `mask-image` radial gradient. The mask controls where blur is visible (sharp center / blurred periphery or vice versa).

## Files

| File | Purpose |
|------|---------|
| `vision-sim.js` | Profiles, SVG filter XML, apply/clear logic, mouse tracking, dropdown UI |
| `vision-sim.css` | Overlay positioning, dropdown styling |
| `toolbar.js` | `vision` button in the toolbar registry |
| `control-panel.html` | Command palette entries for quick access |

---

## Color Blindness Filters

All color blindness simulations use `<feColorMatrix type="matrix">` with a 5×4 matrix (20 values). The matrix transforms each pixel's RGBA channels:

```
| R_out |   | a b c d e |   | R_in |
| G_out | = | f g h i j | × | G_in |
| B_out |   | k l m n o |   | B_in |
| A_out |   | p q r s t |   | A_in |
                              |  1   |
```

The last column (e, j, o, t) is an additive offset. All matrices use `color-interpolation-filters="linearRGB"` for physically accurate results (sRGB gamma would distort the math).

### Dichromacies (complete)

#### Protanopia (red-blind, ~1% of males)
No functional red (L) cones. Reds appear dark, red-green distinctions are lost.
```
0.567 0.433 0     0 0
0.558 0.442 0     0 0
0     0.242 0.758 0 0
0     0     0     1 0
```
**To adjust:** The first two rows control how red and green map to the remaining channels. Increasing `0.433` (row 1, col 2) shifts more red perception toward green. Values should sum to ~1.0 per row to preserve luminance.

#### Deuteranopia (green-blind, ~1% of males)
No functional green (M) cones. Uses Chrome/Blink's precise Machado-derived matrix.
```
 0.367  0.861 -0.228 0 0
 0.280  0.673  0.047 0 0
-0.012  0.043  0.969 0 0
 0      0      0     1 0
```
**Note:** Negative values (−0.228, −0.012) capture spectral overlaps that simpler matrices miss. This is the most accurate publicly available deuteranopia matrix.

#### Tritanopia (blue-blind, very rare)
No functional blue (S) cones. Blue-yellow distinctions are lost.
```
0.95 0.05  0     0 0
0    0.433 0.567 0 0
0    0.475 0.525 0 0
0    0     0     1 0
```

#### Achromatopsia (total color blindness)
No functional cones at all — rod monochromacy. This filter is more complex than the others (see dedicated section below).

### Anomalous trichromacy (partial)

These are "weakened" versions — the affected cone type exists but has shifted spectral sensitivity. Matrices are interpolated between the identity matrix and the full dichromacy matrix.

| Condition | Affected | Prevalence |
|-----------|----------|------------|
| Protanomaly | Red-weak | ~1% males |
| Deuteranomaly | Green-weak | ~5% males |
| Tritanomaly | Blue-weak | Very rare |

**To adjust severity:** Linearly interpolate between the identity matrix `[1,0,0,0,0, 0,1,0,0,0, 0,0,1,0,0, 0,0,0,1,0]` and the full dichromacy matrix. For example, 50% deuteranomaly = `0.5 × identity + 0.5 × deuteranopia_matrix`.

---

## Achromatopsia (detailed)

The most complex filter, with a three-stage pipeline:

### Stage 1: Desaturate (feColorMatrix)
Standard luminance conversion using Rec. 601 weights:
```
R_out = G_out = B_out = 0.299R + 0.587G + 0.114B
```

### Stage 2: Photophobia (feComponentTransfer, gamma)
Rod cells saturate under bright light. A gamma curve with exponent < 1 lifts midtones and highlights while preserving darks:
```
output = input^0.6
```
| Input | Output | Effect |
|-------|--------|--------|
| 0.0 (black) | 0.0 | Unchanged |
| 0.3 (dark) | 0.49 | Modest lift |
| 0.6 (mid) | 0.74 | Noticeable wash |
| 0.9 (bright) | 0.94 | Nearly blown out |

**To adjust:** Change `exponent` in the `<feFuncR/G/B type="gamma">` elements.
- Lower exponent (e.g. 0.4) = more aggressive washout
- Higher exponent (e.g. 0.8) = subtler, closer to normal
- Exponent 1.0 = no photophobia effect

### Stage 3: Bloom / halation (feComponentTransfer + feGaussianBlur + feBlend)
Bright areas emit a soft glow that bleeds into surroundings:

1. **Extract brights:** `feComponentTransfer` with `slope=1, intercept=-0.6` — only pixels above 60% brightness produce any output (everything darker maps to zero)
2. **Blur:** `feGaussianBlur stdDeviation="4"` — spreads the bright pixels into a soft halo
3. **Composite:** `feBlend mode="screen"` — adds the glow on top of the base image. Screen blending never darkens, so dark areas are completely unaffected.

**To adjust:**
- `intercept` controls the brightness threshold: −0.6 means only the top 40% glows. Use −0.8 for only the top 20%, or −0.4 for a more pervasive glow.
- `stdDeviation` controls glow radius: 4 = subtle halo, 8 = wide bleed, 12 = very diffuse.
- To disable bloom entirely, remove the three bloom filter primitives (`feComponentTransfer result="brights"`, `feGaussianBlur`, `feBlend`) and the filter will end after the photophobia stage.

### Stage 4: Acuity reduction (CSS blur)
A CSS `blur(0.8px)` is applied alongside the SVG filter for subtle softness simulating ~20/80 acuity.

**To adjust:** Change the `cssFilter` value in the `achromatopsia` profile in `vision-sim.js`. Use `blur(0)` to disable, `blur(2px)` for more severe (~20/200).

---

## Acuity Simulations

These use CSS `filter` functions directly (no SVG):

| Profile | CSS filter | Simulates |
|---------|-----------|-----------|
| Low Vision (mild) | `blur(1.5px)` | ~20/70 acuity |
| Low Vision (moderate) | `blur(3px)` | ~20/100 acuity |
| Low Vision (severe) | `blur(6px)` | ~20/200 acuity |
| Cataracts | SVG (yellowing + desat) + `blur(1.5px)` | Cloudy lens |
| Reduced Contrast | `contrast(0.55) brightness(1.1)` | Washed out |

**To adjust blur:** Change the `cssFilter` string in the profile. Blur values are in CSS pixels, not physical pixels — the effect scales with display resolution.

### Cataracts SVG filter
Combines desaturation and a yellow-brown tint via `feComponentTransfer`:
```
R: slope=0.95, intercept=0.02  (slight warm shift)
G: slope=0.88, intercept=0.02  (reduced green)
B: slope=0.72, intercept=0.01  (significantly reduced blue → yellowing)
```
**To adjust:** The `slope` values control how much of each channel is preserved. Lower blue slope = more yellowing. Add `<feGaussianBlur>` inside the SVG filter for additional lens-clouding blur (currently handled by CSS for simplicity).

---

## Visual Field Simulations

These use a completely different technique: a `<div>` overlay with `backdrop-filter`.

### How it works

1. A `<div id="visionFieldOverlay">` is appended inside `#vncContainer`
2. It has `position: absolute; inset: 0` (covers the entire canvas)
3. `backdrop-filter: blur(Npx)` blurs the canvas underneath
4. `background: rgba(0,0,0,alpha)` adds darkness
5. `mask-image: radial-gradient(...)` controls where the overlay is visible
6. `pointer-events: none` — mouse events pass through to the canvas

Where the mask is **transparent**, the overlay is invisible → sharp canvas. Where **opaque**, the blurred + darkened canvas shows through.

### Mouse tracking

The `overlayMaskFn` is called on every `mousemove` (capture phase) to reposition the gradient center. Coordinates are computed as percentages of the container dimensions.

### Tunnel Vision
```js
overlayBlur: 14,
overlayBg: 'rgba(0, 0, 0, 0.75)',
overlayMaskFn: (x, y) => `radial-gradient(circle at ${x} ${y},
    transparent 8%,        // sharp center
    rgba(0,0,0,0.15) 14%, // blur starts fading in
    rgba(0,0,0,0.4) 24%,  // moderate blur
    rgba(0,0,0,0.7) 35%,  // heavy blur + darkening
    black 55%              // fully obscured
)`
```

**To adjust:**
- `overlayBlur` — peripheral blur intensity (px). Higher = more diffuse.
- `overlayBg` alpha — darkness at the edges. 0.75 = quite dark. Use 0.5 for lighter.
- Gradient stops — control the feathering curve. Move the first `transparent` stop higher (e.g. 15%) for a wider clear area. Move the `black` stop lower (e.g. 40%) for a tighter tunnel.

### Central Scotoma
The inverse of tunnel vision — blurry/dark center, sharp periphery:
```js
overlayBlur: 16,
overlayBg: 'rgba(0, 0, 0, 0.4)',
overlayMaskFn: (x, y) => `radial-gradient(circle at ${x} ${y},
    black 0%,              // fully obscured center
    rgba(0,0,0,0.8) 4%,   // still mostly dark
    rgba(0,0,0,0.5) 8%,   // fading
    rgba(0,0,0,0.2) 13%,  // almost clear
    transparent 20%        // sharp periphery
)`
```

**To adjust:** Same parameters as tunnel vision but inverted gradient direction. Increase the `transparent` stop (e.g. 30%) for a larger scotoma.

---

## Adding a New Simulation

1. **Add a profile** to `VISION_PROFILES` in `vision-sim.js`:
   ```js
   'my-condition': {
       label: 'My Condition',
       group: 'Category',        // groups items in the dropdown
       description: 'Tooltip text',
       svgFilter: 'vision-my-filter',  // optional: SVG filter ID
       cssFilter: 'blur(2px)',          // optional: CSS filter string
       // OR for visual field effects:
       overlayBlur: 10,
       overlayBg: 'rgba(0,0,0,0.5)',
       overlayMaskFn: (x, y) => `radial-gradient(...)`
   }
   ```

2. **If using an SVG filter**, add the `<filter>` definition to `VISION_SVG_FILTERS` in the same file.

3. **Add a command palette entry** in `control-panel.html` (search for `ui:vision-`):
   ```js
   { id: 'ui:vision-my', title: 'Vision: My Condition', section: 'Accessibility',
     keywords: 'vision …', handler: () => setVisionSimulation('my-condition'),
     content: 'Description' },
   ```

4. The toolbar dropdown picks up new profiles automatically — no changes needed.

---

## Performance Notes

- **Color filters (SVG):** ~0.1–0.3ms per frame on integrated GPU. The achromatopsia filter is the heaviest due to its 5-stage pipeline with blur, but still well under 1ms.
- **CSS blur:** GPU-accelerated. `blur(6px)` (severe low vision) is the most expensive at ~0.5ms.
- **Visual field overlay:** `backdrop-filter` creates one extra compositing layer. The `mousemove` handler sets `mask-image` on every frame during mouse movement.
- **When off:** Zero overhead. No filters applied, no overlay in the DOM, no event listeners.

## References

- Machado, Oliveira & Fernandes (2009) — "A Physiologically-based Model for Simulation of Color Vision Deficiency" — source of the color matrices
- Chrome DevTools CVD simulation — source of the precise deuteranopia matrix
- DaltonLens.org — SVG filter accuracy analysis
