# Screenshot Commands

Capture high-quality screenshots of elements, viewports, or entire pages directly from the command line.

## Overview

Inspekt provides three screenshot modes:

| Command | Captures | Best For |
|---------|----------|----------|
| `inspekt screenshot node` | Specific element | UI components, buttons, cards |
| `inspekt screenshot viewport` | Visible browser area | Above-the-fold content |
| `inspekt screenshot page` | Entire page (full height) | Full page captures |

All modes support margins, format options, optimization, clipboard output, **metadata embedding**, and **sensitive data redaction**.

---

## Quick Start

```bash
# Screenshot the currently inspected element
inspekt inspect "header"
inspekt screenshot node -o header.png

# Screenshot with alias (same as above)
inspekt inspected screenshot -o header.png

# Screenshot the visible viewport
inspekt screenshot viewport -o viewport.png

# Screenshot the entire page
inspekt screenshot page -o fullpage.png

# Copy to clipboard instead of saving
inspekt screenshot node --clipboard
```

---

## Element Screenshots (`screenshot node`)

Capture a specific DOM element with pixel-perfect accuracy.

### Basic Usage

```bash
# Capture currently inspected element
inspekt screenshot node -o element.png

# Capture element by selector
inspekt screenshot node --selector "#hero-banner" -o hero.png
inspekt screenshot node -s ".product-card" -o card.png
```

### How It Works

The `screenshot node` command uses a **hybrid capture approach** to reliably capture any element, regardless of size or position:

```
┌─────────────────────────────────────────────────────────────┐
│                    Element Analysis                          │
├─────────────────────────────────────────────────────────────┤
│  1. Scroll element into view (if not visible)               │
│  2. Analyze element dimensions vs viewport size             │
│  3. Choose optimal capture method:                          │
│                                                             │
│     ┌─────────────────────┬─────────────────────────────┐   │
│     │ Element fits in     │ Element exceeds viewport    │   │
│     │ viewport            │                             │   │
│     ├─────────────────────┼─────────────────────────────┤   │
│     │ Fast capture        │ CDP capture with clip       │   │
│     │ (captureVisibleTab) │ (Page.captureScreenshot)    │   │
│     │                     │                             │   │
│     │ • ~100ms            │ • ~500ms                    │   │
│     │ • No debugger       │ • Brief debugger banner     │   │
│     │ • Works with        │ • Cannot use with           │   │
│     │   DevTools open     │   DevTools open             │   │
│     └─────────────────────┴─────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Automatic Adjustments

The command automatically handles common scenarios:

| Scenario | Adjustment | Feedback |
|----------|------------|----------|
| Element off-screen | Scrolls into view | ` Element was scrolled into view before capture.` |
| Element larger than viewport | Uses CDP fallback | ` Element (1500×2000) exceeds viewport...` |
| Very large element (>10000px) | Captures with warning | ` Large element captured: 12000×800...` |

### Options

```bash
inspekt screenshot node [OPTIONS]

Options:
  -s, --selector TEXT       CSS selector (default: inspected element)
  -o, --output PATH         Output file path (auto-generated if omitted)
  -m, --margin INT          Margin in pixels around element (default: from config)
  -c, --margin-color TEXT   Margin color: 'auto', hex code, or color name
  --scale, --dpr INT        Scale/DPR factor for high-DPI (default: 2)
  --max-width INT           Resize output to fit within max width (maintains aspect ratio)
  --format [png|jpg|webp]   Output format (default: png)
  --quality FLOAT           Quality for lossy formats (0.0-1.0)
  --optimize / --no-optimize  Optimize PNG with oxipng
  --metadata / --no-metadata  Embed metadata in image (default: enabled)
  --redact / --no-redact    Redact sensitive data (default: enabled)
  --redact-style [blur|bar]  Redaction style (default: bar)
  --redact-selectors TEXT   Additional CSS selectors to redact (comma-separated)
  --scroll-into-view / --no-scroll  Scroll element into view (default: yes)
  --hide-outline / --keep-outline   Hide selection outline (default: yes)
  --open                    Open in default app after saving
  --reveal                  Reveal in file explorer after saving
  --clipboard               Copy to clipboard instead of file
  -f, --force               Overwrite existing file without confirmation
  -q, --quiet               Suppress output except errors
  --json                    Output result as JSON (for scripting)
```

### Examples

```bash
# With margin and auto-detected background color
inspekt screenshot node -o card.png --margin 20 --margin-color auto

# High-quality 2x screenshot
inspekt screenshot node -o hero.png --scale 2

# Optimized PNG (smaller file size)
inspekt screenshot node -o logo.png --optimize

# WebP format with custom quality
inspekt screenshot node -o banner.webp --format webp --quality 0.9

# Copy directly to clipboard
inspekt screenshot node --clipboard

# Capture and open immediately
inspekt screenshot node -o preview.png --open
```

---

## Viewport Screenshots (`screenshot viewport`)

Capture exactly what's visible in the browser window.

### Usage

```bash
inspekt screenshot viewport -o viewport.png
inspekt screenshot viewport --clipboard
inspekt screenshot viewport -o view.png --margin 10 --optimize
```

### Options

```bash
inspekt screenshot viewport [OPTIONS]

Options:
  -o, --output PATH         Output file path (required unless --clipboard)
  -m, --margin INT          Margin in pixels (default: 0)
  -c, --margin-color TEXT   Margin color (default: auto)
  --scale INT               Scale factor (default: 2)
  --format [png|jpg|webp]   Output format (default: png)
  --quality FLOAT           Quality for lossy formats (default: 0.92)
  --optimize                Optimize PNG with oxipng
  --metadata / --no-metadata  Embed metadata in image (default: enabled)
  --open                    Open in default app after saving
  --reveal                  Reveal in file explorer after saving
  --clipboard               Copy to clipboard instead of file
```

---

## Full Page Screenshots (`screenshot page`)

Capture the entire page from top to bottom.

### Usage

```bash
inspekt screenshot page -o fullpage.png
inspekt screenshot page -o page.jpg --format jpg --quality 0.85
```

### How It Works

Full page screenshots use Chrome DevTools Protocol (CDP) to:

1. Attach the debugger (a banner appears briefly)
2. Query the full page dimensions
3. Capture the entire content in a single shot
4. Detach the debugger

!!! warning "Debugger Banner"
    A yellow "Chrome is being controlled by automated test software" banner
    will appear briefly during capture. This is a Chrome security feature.

!!! note "DevTools Conflict"
    Full page screenshots cannot be taken while DevTools is open. Close
    DevTools before running `screenshot page`.

### Options

```bash
inspekt screenshot page [OPTIONS]

Options:
  -o, --output PATH         Output file path (required unless --clipboard)
  -m, --margin INT          Margin in pixels (default: 0)
  -c, --margin-color TEXT   Margin color (default: auto)
  --scale INT               Scale factor (1 or 2, default: 1)
  --format [png|jpg|webp]   Output format (default: png)
  --quality FLOAT           Quality for lossy formats (default: 0.92)
  --max-height INT          Maximum capture height (default: 16384)
  --optimize                Optimize PNG with oxipng
  --metadata / --no-metadata  Embed metadata in image (default: enabled)
  --open                    Open in default app after saving
  --reveal                  Reveal in file explorer after saving
  --clipboard               Copy to clipboard instead of file
```

### Chrome Limits

Chrome has a maximum screenshot dimension of **16384 pixels**. Pages taller than this will be truncated:

```bash
$ inspekt screenshot page -o long-page.png
Warning: Page was truncated from 25000px to 16384px
Screenshot saved: long-page.png
```

---

## Margin and Background Color

All screenshot modes support margins with automatic or custom background colors.

### Auto Color Detection

The `auto` margin color samples the top-left pixel of the element/viewport and uses that color for the margin:

```bash
# Auto-detect background color from element
inspekt screenshot node -o card.png --margin 20 --margin-color auto
```

### Custom Colors

```bash
# Hex color
inspekt screenshot node -o dark.png --margin 10 --margin-color "#1a1a1a"

# Named color
inspekt screenshot node -o white.png --margin 10 --margin-color white

# Transparent (PNG only)
inspekt screenshot node -o trans.png --margin 10 --margin-color transparent
```

---

## Output Formats

| Format | Extension | Transparency | Best For |
|--------|-----------|--------------|----------|
| PNG | `.png` | Yes | UI elements, logos, icons |
| JPEG | `.jpg` | No | Photos, complex images |
| WebP | `.webp` | Yes | Modern web, smaller files |

### Quality Setting

For lossy formats (JPEG, WebP), the `--quality` option controls compression:

```bash
# High quality (larger file)
inspekt screenshot node -o photo.jpg --format jpg --quality 0.95

# Lower quality (smaller file)
inspekt screenshot node -o thumb.webp --format webp --quality 0.7
```

---

## PNG Optimization

Use `--optimize` to reduce PNG file size using [oxipng](https://github.com/shssoichiro/oxipng):

```bash
$ inspekt screenshot node -o logo.png --optimize
Screenshot saved: logo.png
Size: 400×200px (45.2 KB)
Optimized: 45.2 KB → 32.1 KB (29.0% reduction)
```

!!! note "oxipng Required"
    Install oxipng for optimization: `brew install oxipng` (macOS) or
    `cargo install oxipng` (cross-platform).

---

## Image Metadata

Screenshots automatically include embedded metadata with capture information. This is **enabled by default** and helps track where screenshots came from.

### What's Embedded

| Metadata Field | Example Value | Description |
|----------------|---------------|-------------|
| `Inspekt:SourceURL` | `https://example.com/page` | URL of the captured page |
| `Inspekt:CaptureTimestamp` | `2025-01-15T14:30:45+00:00` | When the screenshot was taken (ISO 8601) |
| `Inspekt:Viewport` | `1920x1080` | Browser viewport dimensions |
| `Inspekt:Target` | `element` / `viewport` / `page` | What was captured |
| `Inspekt:Selector` | `.hero-banner` | CSS selector (element captures only) |
| `Inspekt:ElementTag` | `div` | HTML tag name (element captures only) |
| `Inspekt:DevicePixelRatio` | `2` | Scale factor used |
| `Inspekt:Redacted` | `true` | Whether sensitive data was redacted |
| `Inspekt:Tool` | `inspekt` | Tool identifier |
| `Inspekt:Version` | `1.0.0` | Inspekt version |

### Viewing Metadata

**macOS Finder:**
1. Right-click image → Get Info
2. Look under "More Info"

**Command line:**
```bash
# Using exiftool
exiftool screenshot.png | grep Inspekt

# Using ImageMagick
identify -verbose screenshot.png | grep Inspekt
```

### Disabling Metadata

```bash
# Disable for a single capture
inspekt screenshot node -o hero.png --no-metadata

# Metadata is stripped when using --optimize (oxipng strips it)
# but Inspekt re-adds it after optimization
```

!!! note "Format Support"
    Metadata embedding works with **PNG** and **JPEG** formats.
    WebP metadata support is not currently available.

---

## Sensitive Data Redaction

Screenshots automatically redact sensitive information before capturing. This is **enabled by default** for security, protecting passwords, credit card numbers, API keys, and other PII from appearing in screenshots.

!!! success "Secure by Default"
    Redaction is enabled by default. Use `--no-redact` to disable it when you explicitly need to capture sensitive data.

### Basic Usage

```bash
# Redaction is automatic (uses bar style by default)
inspekt screenshot node -o form.png

# Disable redaction when needed
inspekt screenshot node -o form.png --no-redact

# Choose a different redaction style
inspekt screenshot node -o form.png --redact-style blur
```

### Redaction Styles

| Style | Appearance | Best For |
|-------|------------|----------|
| `bar` (default) | Block characters (████) | Clear redaction, preserves layout |
| `blur` | Soft text blur | Subtle redaction |

**Security note:** For the `blur` style, the underlying text is first randomized before the visual effect is applied. This provides double protection—even if someone attempts to reverse the blur effect, they'll only see random characters.

```bash
# Bar style (default) - clear block characters
inspekt screenshot node -s ".card" -o form.png

# Blur style - soft blur effect
inspekt screenshot node -s ".card" -o form-blur.png --redact-style blur
```

### What Gets Redacted

**Form fields** (detected by attributes):

| Selector | Detects |
|----------|---------|
| `input[type="password"]` | Password fields |
| `input[autocomplete*="cc-"]` | Credit card fields |
| `input[autocomplete="cc-number"]` | Card numbers |
| `input[autocomplete="cc-csc"]` | CVV/CVC codes |
| `input[name*="ssn"]` | Social Security Numbers |
| `input[name*="api_key"]` | API key fields |
| `input[name*="token"]` | Token fields |

**Text content** (detected by patterns):

| Pattern | Example |
|---------|---------|
| Credit card numbers | `4532 1234 5678 9012` |
| US Social Security Numbers | `123-45-6789` |
| JWT tokens | `eyJhbGciOiJIUzI1NiIs...` |
| AWS access keys | `AKIAIOSFODNN7EXAMPLE` |
| Long API keys | 32+ character alphanumeric strings |

### Email Address Masking

Email addresses receive special treatment: instead of being blurred, they are **masked** to preserve context while hiding the personal part:

| Original | Masked |
|----------|--------|
| `john.doe@company.com` | `j…e@company.com` |
| `jane.smith@example.org` | `j…h@example.org` |
| `ab@test.com` | `a…@test.com` |

This applies to:
- `<input type="email">` fields
- Input fields with `autocomplete="email"`
- Text content containing email addresses

Email masking happens automatically alongside the selected redaction style—you don't need to configure it separately.

### Custom Redaction Selectors

Add your own selectors to redact application-specific sensitive elements:

```bash
# Redact additional elements by selector
inspekt screenshot node -o dashboard.png --redact --redact-selectors ".account-balance, .api-token"

# Multiple selectors (comma-separated)
inspekt screenshot node -o settings.png --redact --redact-selectors "#secret-key, .private-data, [data-sensitive]"
```

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    Redaction Process                         │
├─────────────────────────────────────────────────────────────┤
│  1. Scan target element for sensitive fields/patterns       │
│  2. Apply redaction style (bar or blur)                     │
│  3. Capture screenshot (redacted elements visible)          │
│  4. Restore original page state (remove redaction)          │
│  5. Screenshot saved with sensitive data obscured           │
└─────────────────────────────────────────────────────────────┘
```

The redaction is applied **before** the screenshot is taken, so sensitive data never appears in the captured image. After capture, the page is automatically restored to its original state.

### Example Output

```bash
$ inspekt screenshot node -s ".card" -o form.png
 Redacting: 5 element(s) with bar, 2 email(s) masked
 Capturing element: .card
 Screenshot saved: form.png
 Size: 640×480 (45.3 KB)
 Metadata embedded: URL, timestamp, viewport info
```

### Test Page

A test page with various sensitive data patterns is available:

```bash
open test-site/redaction-test.html
```

---

## Clipboard Support

Copy screenshots directly to the clipboard instead of saving to a file:

```bash
inspekt screenshot node --clipboard
inspekt screenshot viewport --clipboard
inspekt screenshot page --clipboard
```

This works cross-platform:
- **macOS**: Native clipboard support
- **Linux**: Requires `xclip` (`sudo apt install xclip`)
- **Windows**: Native clipboard support

---

## Auto-Generated Filenames

If no output path is specified, filenames are auto-generated:

```bash
$ inspekt screenshot node
Auto-generated filename: 20250122143052_button.png
Screenshot saved: ~/Pictures/inspekt/screenshots/20250122143052_button.png
```

The format is: `YYYYMMDDHHMMSS_tagname[_id].ext`

Configure the screenshots directory in `~/.config/inspekt/config.yaml`:

```yaml
paths:
  screenshots: ~/Pictures/inspekt/screenshots
```

---

## JSON Output for Scripting

Use `--json` to get machine-readable output for automation scripts:

```bash
inspekt screenshot node -o hero.png --json
```

**Example output:**

```json
{
  "ok": true,
  "path": "/Users/you/screenshots/hero.png",
  "filename": "hero.png",
  "width": 800,
  "height": 600,
  "original_width": 800,
  "original_height": 600,
  "size_bytes": 125432,
  "original_size_bytes": 125432,
  "resized": false,
  "optimized": false,
  "metadata_embedded": true,
  "redacted": false,
  "redacted_count": 0,
  "redacted_elements": [],
  "url": "https://example.com/page",
  "method": "captureVisibleTab",
  "scrolled_into_view": false,
  "used_cdp_fallback": false
}
```

### Quiet Mode

Use `--quiet` to suppress all output except errors:

```bash
inspekt screenshot node -o hero.png --quiet
```

This is useful in scripts where you only want to see errors.

---

## Configuration

Default settings can be configured in `~/.config/inspekt/config.yaml`:

```yaml
screenshot:
  margin: 0              # Default margin in pixels
  margin-color: auto     # 'auto', hex, or color name
  scale: 2               # Default scale factor
  format: png            # png, jpg, or webp
  quality: 0.92          # Quality for lossy formats
  optimize: false        # Auto-optimize PNGs
```

Command-line flags override configuration values.

---

## Tips for Best Results

### Maximize Your Browser Window

For the **fastest captures**, ensure your browser viewport is large enough to contain the element:

```
┌────────────────────────────────────────────────────────────┐
│ Viewport Size vs Capture Speed                             │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  Small viewport (800×600)     Large viewport (1920×1080)   │
│  ┌──────────┐                 ┌─────────────────────────┐  │
│  │ Element  │                 │                         │  │
│  │ exceeds  │ → CDP fallback  │    Element fits!        │  │
│  │ viewport │   (~500ms)      │                         │  │
│  │   ↓      │                 │    → Fast capture       │  │
│  └──────────┘                 │      (~100ms)           │  │
│       ↓                       │                         │  │
│  (overflow)                   └─────────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Recommendation**: Before capturing large elements, maximize your browser window or use a high-resolution display.

### Check Element Size First

Use `inspekt inspected` to see element dimensions before capturing:

```bash
$ inspekt inspect "main"
$ inspekt inspected

Dimensions:
  Position: x=0, y=100
  Size:     1200×3500px    # ← This element is tall!
  ...

Visibility:
  In viewport: No          # ← Not fully visible
```

If the element is larger than your viewport, expect the CDP fallback (slightly slower, brief debugger banner).

### Avoid Unnecessary CDP Fallback

The CDP fallback is triggered when:

1. Element **width** exceeds viewport width
2. Element **height** exceeds viewport height

To avoid it:

| Scenario | Solution |
|----------|----------|
| Tall element (e.g., article) | Consider capturing sections separately |
| Wide element (e.g., data table) | Maximize browser or use smaller scale |
| Hero banner | Usually fits—just maximize browser |

### Use `--no-scroll` for Fixed/Sticky Elements

For fixed or sticky positioned elements, disable auto-scroll:

```bash
inspekt screenshot node --selector ".sticky-header" --no-scroll -o header.png
```

### Batch Captures with Shell Scripts

For multiple screenshots, script it:

```bash
#!/bin/bash
for selector in "header" "nav" ".hero" "footer"; do
    inspekt screenshot node -s "$selector" -o "${selector//[.#]/}.png"
done
```

### Use Clipboard for Quick Sharing

Skip the file system entirely:

```bash
# Capture and paste directly into Slack, email, etc.
inspekt screenshot node --clipboard
```

### Optimize for Documentation

For documentation screenshots, use consistent settings:

```bash
# Create an alias for documentation screenshots
alias docshot='inspekt screenshot node --margin 16 --margin-color "#f5f5f5" --scale 2 --optimize'

# Then use it
docshot -o button-primary.png
docshot -o button-secondary.png
```

### Resize Large Screenshots

Use `--max-width` to automatically resize screenshots that are too wide:

```bash
# Resize to fit within 800px width (maintains aspect ratio)
inspekt screenshot node -o hero.png --max-width 800

# Combine with --scale 2 for crisp images at target size
inspekt screenshot node -o hero.png --scale 2 --max-width 1200
```

### Redact Sensitive Data

When capturing forms or dashboards, use `--redact` to blur sensitive information:

```bash
# Blur passwords, credit cards, API keys automatically
inspekt screenshot viewport -o settings.png --redact

# Add custom selectors for app-specific sensitive data
inspekt screenshot node -o profile.png --redact --redact-selectors ".balance, .ssn"
```

### Handle DevTools Conflicts

If you get "another debugger is attached":

1. **Close DevTools** (Cmd/Ctrl + Shift + I)
2. Run your screenshot command
3. Re-open DevTools if needed

Alternatively, for elements that fit in the viewport, the fast capture method works even with DevTools open.

---

## Troubleshooting

### "No element is currently inspected"

You need to select an element first:

```bash
# Option 1: Use inspekt inspect
inspekt inspect "button.primary"
inspekt screenshot node -o button.png

# Option 2: Use --selector flag
inspekt screenshot node --selector "button.primary" -o button.png

# Option 3: Inspect in DevTools + run inspektStore()
# 1. Right-click element → Inspect
# 2. In Console: inspektStore()
# 3. Run: inspekt screenshot node -o element.png
```

### "Cannot capture: another debugger is attached"

Close Chrome DevTools before using `screenshot page` or capturing oversized elements:

```bash
# Close DevTools (Cmd+Option+I or F12), then:
inspekt screenshot page -o fullpage.png
```

### "Element has zero dimensions"

The element may be hidden or not rendered:

```bash
# Check element visibility
inspekt inspected

# Look for:
#   Visible: No
#   Issue: display: none
```

### Screenshots appear blurry

Increase the scale factor:

```bash
inspekt screenshot node -o crisp.png --scale 2
```

---

## See Also

- [Selection Commands](selection.md) - Extract HTML/text from elements
- [Data Extraction Guide](../guide/data-extraction.md) - More extraction tools
- [Configuration](../getting-started/configuration.md) - Config file options
