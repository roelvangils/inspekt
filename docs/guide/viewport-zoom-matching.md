# Viewport and Zoom Matching Guide

This guide explains how to ensure faithful replay of recordings by matching viewport size and browser zoom level between recording and playback.

## Why Viewport and Zoom Matter

When you record browser interactions, Inspekt captures the viewport dimensions and zoom level. During replay, if these values differ, several issues can occur:

### Click Positioning Issues

Click coordinates are calculated relative to the viewport. If the viewport changes:

- **Elements move** - A button at position (500, 300) in a 1920×1080 viewport may be at (250, 150) in a 960×540 viewport
- **Elements disappear** - Items visible at larger viewports may scroll off-screen at smaller ones
- **Overlays block** - Modal dialogs and sticky headers behave differently at different sizes

### Responsive Layout Changes

Modern websites adapt to viewport size:

```
Desktop (1920px)          Tablet (768px)           Mobile (375px)
┌─────────────────┐       ┌───────────┐            ┌─────┐
│ Nav │ Content   │       │ ≡ Content │            │  ≡  │
│     │           │  →    │           │      →     │─────│
│     │           │       │           │            │     │
└─────────────────┘       └───────────┘            └─────┘
```

A recording made at desktop width won't work correctly on mobile if the navigation changes to a hamburger menu.

### Zoom Level Effects

Browser zoom affects:

- **Text size** - Larger text at higher zoom may wrap differently
- **Element dimensions** - CSS pixel values scale with zoom
- **Fixed positioning** - Fixed elements take up proportionally more space
- **Touch targets** - Accessibility zoom (200%+) changes interaction patterns

## When Matching is Essential

### 1. Visual Regression Testing

For screenshot comparisons to work, viewport and zoom must be identical:

```bash
# Record baseline at exact dimensions
inspekt record --match-viewport --match-zoom-level baseline.yaml

# CI job - replay with matching
inspekt replay baseline.yaml --match-viewport --match-zoom-level --video
```

### 2. Responsive Breakpoint Testing

Test specific CSS breakpoints:

```bash
# Test mobile breakpoint (< 768px)
# 1. Resize to 375×667
inspekt record --match-viewport mobile-flow.yaml

# Test tablet breakpoint (768-1024px)
# 1. Resize to 768×1024
inspekt record --match-viewport tablet-flow.yaml

# Replay at exact breakpoints
inspekt replay mobile-flow.yaml --match-viewport
inspekt replay tablet-flow.yaml --match-viewport
```

### 3. Accessibility Zoom Testing

WCAG 2.1 SC 1.4.10 requires content to work at 400% zoom:

```bash
# Test at 200% zoom
# 1. Set browser zoom to 200%
inspekt record --match-zoom-level zoom-200.yaml

# Test at 400% zoom
# 1. Set browser zoom to 400%
inspekt record --match-zoom-level zoom-400.yaml

# Replay at recorded zoom levels
inspekt replay zoom-200.yaml --match-zoom-level
inspekt replay zoom-400.yaml --match-zoom-level
```

### 4. CI/CD Pipelines

Ensure consistent results across different CI environments:

```bash
# .github/workflows/e2e.yml
- name: Run visual tests
  run: |
    inspekt replay tests/checkout.yaml \
      --match-viewport \
      --match-zoom-level \
      --no-feedback
```

## When Matching is NOT Needed

### Manual Debugging

When stepping through a recording to understand behavior, the exact viewport doesn't matter:

```bash
# Interactive debugging - matching not needed
inspekt replay flow.yaml --interactive --verbose
```

### Cross-Device Testing

If you want to verify a flow works at your current device size:

```bash
# Let the warning appear, but continue
inspekt replay flow.yaml
# Warning shown, but replay proceeds at current size
```

### Quick Smoke Tests

For "does it work at all" testing:

```bash
# Fast smoke test - don't worry about exact size
inspekt replay login.yaml --instant
```

## How Inspekt Captures Viewport and Zoom

### During Recording

When you run `inspekt record`, the following are captured:

| Metric | How It's Captured | Stored In |
|--------|-------------------|-----------|
| Viewport width | `window.innerWidth` | `state.viewport.width` |
| Viewport height | `window.innerHeight` | `state.viewport.height` |
| Device pixel ratio | `window.devicePixelRatio` | `state.zoom` |
| Browser zoom level | `chrome.tabs.getZoom()` | `state.browser_zoom_level` |

### The Two Zoom Values

Inspekt captures two zoom-related values:

1. **`zoom` (devicePixelRatio)**: A layout metric that combines:
   - System display scaling (Retina displays = 2.0)
   - Browser zoom percentage
   - This value affects CSS rendering

2. **`browser_zoom_level`**: The actual Chrome zoom setting:
   - 1.0 = 100% zoom
   - 1.25 = 125% zoom
   - 2.0 = 200% zoom
   - This is what users control with Ctrl+Plus/Minus (or ⌘+/⌘- on macOS)

#### Understanding the Relationship

The `zoom` value equals `display_density × browser_zoom_level`:

| Display | Browser Zoom | `zoom` (devicePixelRatio) | `browser_zoom_level` |
|---------|--------------|---------------------------|----------------------|
| Standard (1x) | 100% | 1.0 | 1.0 |
| Standard (1x) | 150% | 1.5 | 1.5 |
| Retina (2x) | 100% | 2.0 | 1.0 |
| Retina (2x) | 150% | 3.0 | 1.5 |
| Retina (2x) | 200% | 4.0 | 2.0 |

**Why capture both?** The `browser_zoom_level` is what Inspekt can restore via the Chrome extension API. The `zoom` (devicePixelRatio) depends on hardware and cannot be changed programmatically.

### Example YAML

```yaml
metadata:
  version: '1.1'
  created_at: '2025-12-16T10:30:00Z'
  starting_url: https://example.com

state:
  viewport:
    width: 1920
    height: 1080
  zoom: 2.0                      # devicePixelRatio (Retina + zoom)
  browser_zoom_level: 1.0        # 100% browser zoom
  require_viewport_match: true   # Viewport matching requested
  require_zoom_match: false      # Zoom matching not requested

steps:
  - timestamp: 0
    action: navigate
    url: https://example.com
```

## How Matching Works

### Viewport Matching (--match-viewport)

Both `inspekt record --viewport` and `inspekt replay --match-viewport` use cached offsets for fast, reliable resizing. If cached offsets are available and valid, resizing is instant. If not, a calibration loop runs to determine the correct offsets.

**On macOS:**
```
1. Check for cached viewport offsets in config.json
2. If cached: Apply offsets and resize instantly
3. If not cached or stale: Run calibration loop
   - AppleScript sends resize command to browser
   - Measure actual viewport via JavaScript
   - Adjust and repeat until exact match
   - Save offsets to config.json
4. Verify the resize achieved exact target dimensions
```

**On Other Platforms:**
```
1. Check for cached viewport offsets in config.json
2. If cached: Apply offsets and attempt resize
3. If not cached: Run calibration loop via JavaScript
4. JavaScript calls window.resizeTo() (may be blocked by browser)
5. If blocked, warning is shown to user
```

### Zoom Matching (--match-zoom-level)

```
1. Inspekt extension receives zoom request
2. chrome.tabs.setZoom() API is called
3. Browser zoom level changes immediately
4. Works reliably on all platforms with the extension
```

## Best Practices

### 1. Be Explicit About Requirements

When viewport/zoom matters, use the flags during recording:

```bash
# Good: Requirements are stored in the file
inspekt record --match-viewport responsive-test.yaml

# Less Good: Requirements not stored, must remember to add flags during replay
inspekt record responsive-test.yaml
```

### 2. Document Your Test Dimensions

Include viewport info in your recording filenames or descriptions:

```bash
# Filename includes dimensions
inspekt record checkout-1920x1080.yaml

# Or add a comment to the YAML
# Test: Checkout flow at desktop breakpoint (1920×1080)
```

### 3. Test Multiple Viewports

Create recordings at key breakpoints:

```bash
# Desktop
inspekt record --match-viewport checkout-desktop.yaml  # 1920×1080

# Tablet
inspekt record --match-viewport checkout-tablet.yaml   # 768×1024

# Mobile
inspekt record --match-viewport checkout-mobile.yaml   # 375×667
```

### 4. Handle Zoom Accessibility Testing

For WCAG compliance, test at common zoom levels:

```bash
# Standard zoom
inspekt record --match-zoom-level checkout-100.yaml    # 100%

# Common accessibility zoom
inspekt record --match-zoom-level checkout-150.yaml    # 150%
inspekt record --match-zoom-level checkout-200.yaml    # 200%

# Maximum WCAG requirement
inspekt record --match-zoom-level checkout-400.yaml    # 400%
```

## Viewport Offset Caching

When you use `--viewport`, Inspekt needs to account for the browser's "chrome" (toolbar, tab bar, scrollbars, etc.) to calculate the correct window size. This section explains how Inspekt learns and remembers these offsets.

### How Offsets Work

The viewport (what you see) is smaller than the window (the entire browser frame):

```
┌─────────────────────────────────────────┐
│  Browser Toolbar, Tabs, Address Bar     │  ← Browser chrome
├─────────────────────────────────────────┤
│                                         │
│                                         │
│            Viewport                     │  ← What you requested
│         (1000 × 1000)                   │
│                                         │
│                                         │
├─────────────────────────────────────────┤
│  Status Bar / DevTools (if open)        │  ← More chrome
└─────────────────────────────────────────┘
          Window (1129 × 1112)               ← Actual window size
```

The **offset** is the difference:
- Width offset = `window_width - viewport_width` (e.g., 129px)
- Height offset = `window_height - viewport_height` (e.g., 112px)

### Calibration Process

The first time you use `--viewport`, Inspekt runs a calibration loop:

```
Resizing viewport to 1000×1000…
  Attempt 1: got 1129×1112, nudging…
  Attempt 2: got 985×988, nudging some more…
  Attempt 3: got 1002×1001, almost there…
✓ Viewport set to 1000×1000, offsets saved to config.
```

**What happens:**
1. Inspekt requests the target viewport size
2. Measures the actual viewport via JavaScript
3. Calculates the error and adjusts
4. Repeats until exact match is achieved
5. Saves the final offsets to your config file

### Cached Offsets

After calibration, offsets are stored in your config file:

```json
{
  "viewport_offsets": {
    "width": 129,
    "height": 112
  }
}
```

**Config file locations** (checked in order):
1. `./config.json` (project directory)
2. `~/.config/inspekt.json` (XDG standard)
3. `~/.inspekt/config.json` (legacy)

Subsequent `--viewport` commands use these cached offsets for instant resizing:

```
Resizing viewport to 1000×1000…
✓ Viewport set to 1000×1000
```

### When Offsets Become Stale

Offsets may become outdated if you:
- Switch to a different browser
- Change browser zoom level significantly
- Open/close DevTools (changes available height)
- Change display scaling settings
- Update your browser (toolbar height may change)

Inspekt automatically detects stale offsets and recalibrates:

```
Resizing viewport to 1000×1000…
  Cached offsets outdated, recalibrating…
  Attempt 1: got 1150×1100, nudging…
✓ Viewport set to 1000×1000, offsets saved to config.
```

### Tips and Best Practices

#### 1. Keep DevTools Closed During Calibration

DevTools panels reduce the available viewport height. If you calibrate with DevTools open, the offsets will be wrong when DevTools is closed.

```bash
# Good: Close DevTools, then record
inspekt record --viewport 1920x1080 test.yaml

# After calibration, you can open DevTools if needed
```

#### 2. Use Consistent Browser Zoom

Browser zoom affects the viewport-to-window ratio. Calibrate at 100% zoom for predictable results:

```bash
# Ensure browser is at 100% zoom (Cmd+0 / Ctrl+0)
inspekt record --viewport 1920x1080 test.yaml
```

#### 3. Recalibrate After Browser Updates

Major browser updates occasionally change toolbar dimensions. If viewport sizing seems off after an update:

```bash
# Delete cached offsets from config.json:
# Remove the "viewport_offsets" key, then run:
inspekt record --viewport 1000x1000 test.yaml
# This forces recalibration
```

#### 4. Different Browsers Have Different Offsets

If you switch between Chrome and Firefox, you may need to recalibrate. Inspekt automatically detects when cached offsets don't produce the expected viewport size and recalibrates.

```bash
# Inspekt detects browser changes and recalibrates automatically
inspekt record --viewport 1920x1080 test.yaml
# If offsets are stale, you'll see:
# "Cached offsets outdated, recalibrating…"
```

#### 5. CI/CD Environments

In headless or containerized environments, browser chrome is often minimal or absent. The offsets will be different (often close to zero):

```yaml
# .github/workflows/e2e.yml
- name: Visual regression tests
  run: |
    # First run calibrates, subsequent runs use cached offsets
    inspekt record --viewport 1920x1080 --no-feedback tests/visual.yaml
```

#### 6. Clearing Cached Offsets

To force recalibration, remove the `viewport_offsets` key from your config file:

```bash
# View current offsets
cat config.json | grep -A3 viewport_offsets

# Edit config.json and remove the viewport_offsets section
# Or delete the entire config to start fresh
```

### Understanding the Math

For those curious about the algorithm:

```
target_viewport = 1000×1000 (what you requested)
initial_window  = 1000×1000 (first attempt)
actual_viewport = 871×888   (what we got - smaller due to chrome)

error = actual - target = -129×-112 (negative = viewport too small)
adjustment = -error = 129×112 (compensate by requesting larger window)

next_window = target - adjustment = 1000 - (-129) = 1129×1112
actual_viewport = 1000×1000 ✓ (matches target!)

saved_offset = adjustment = 129×112
```

On subsequent runs:
```
target_viewport = 800×600
window_to_request = target - saved_offset = 800-129 × 600-112 = 671×488
actual_viewport = 800×600 ✓ (instant match!)
```

## Troubleshooting

### "Could not resize viewport"

**Cause:** Browser security blocks `window.resizeTo()` on non-popup windows.

**Solution:**
- On macOS: Ensure Inspekt has accessibility permissions
- On other platforms: Manually resize the browser window to the dimensions shown in the warning

### "Zoom level not changing"

**Cause:** Extension not responding to zoom requests.

**Solution:**
1. Check the Inspekt extension is enabled
2. Refresh the page and try again
3. Verify the extension has the `tabs` permission

### Large Discrepancy in devicePixelRatio

**Cause:** Recording made on Retina display (2x), replaying on standard display (1x).

**Note:** This is expected behavior. The `browser_zoom_level` will still match correctly - only the `devicePixelRatio` differs due to hardware.

### "Cached offsets outdated, recalibrating…"

**Cause:** The stored viewport offsets no longer produce the expected viewport size. This happens when:
- You switched browsers (Chrome → Firefox)
- You opened/closed DevTools
- Your browser was updated
- Display scaling changed

**Solution:** This is normal! Inspekt automatically recalibrates and saves new offsets. No action needed.

**To prevent frequent recalibration:**
- Keep DevTools closed during recording sessions
- Use consistent browser zoom (100%)
- Use the same browser for all recordings in a project

### Viewport always a few pixels off

**Cause:** Some display/browser combinations have sub-pixel rounding issues.

**Solution:** Inspekt requires exact viewport dimensions and will continue calibrating until achieved. If the browser oscillates between two sizes (e.g., 499px and 501px but never 500px), Inspekt shows a warning after 20 attempts.

To resolve persistent calibration issues:
1. Clear cached offsets from config.json
2. Ensure browser zoom is exactly 100%
3. Close all DevTools panels
4. Ensure the requested viewport doesn't exceed your screen size
5. Run `inspekt record --viewport WxH` again

## See Also

- [inspekt record](../commands/record.md) - Recording command documentation
- [inspekt replay](../commands/replay.md) - Replay command documentation
- [Accessibility Testing](accessibility-testing.md) - Using Inspekt for a11y testing
