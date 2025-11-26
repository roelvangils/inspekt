# inspekt save - Save Pages as Offline HTML

The `inspekt save` command captures the current browser tab as a self-contained HTML file with all resources embedded. Using the [SingleFile](https://github.com/gildas-lormeau/SingleFile) library, it preserves the exact state of the page including JavaScript-rendered content, styles, and images.

## Quick Start

```bash
# Save current page (auto-generates filename, saves to ~/Downloads/{domain}/)
inspekt save

# Save with custom filename
inspekt save -o mypage.html

# Save to specific directory
inspekt save -d ~/archives

# Fast save with remote images (smaller file, requires internet)
inspekt save --remote-images

# Skip images entirely (fastest, smallest file)
inspekt save --no-images

# Optimize for large/complex pages
inspekt save --optimize

# Get JSON output for scripting
inspekt save --json
```

## Why Use Inspekt Save?

### The Inspekt Advantage

Unlike browser "Save As" or web archiving tools, Inspekt saves **your current browser state**:

- **Saves YOUR authenticated view** - Capture logged-in dashboards, private content, user settings
- **Preserves JavaScript-rendered content** - Single-page apps, dynamic widgets, lazy-loaded images
- **Maintains current DOM state** - Form values, expanded accordions, active tabs
- **Works offline** - Uses bundled SingleFile library, no CDN dependencies
- **Self-contained output** - Single HTML file with all resources embedded

**Example workflow:**
```bash
# Navigate to your dashboard
inspekt open https://app.example.com/dashboard
# Log in, configure view, expand sections
# Save the exact state you're seeing
inspekt save
```

### What Gets Preserved

- **CSS stylesheets** - Inlined and deduplicated
- **Images** - Converted to base64 data URIs (or kept as URLs with `--remote-images`)
- **Fonts** - Embedded from CSS @font-face rules
- **Canvas elements** - Converted to static images
- **SVG graphics** - Fully preserved with inline styles
- **Current DOM** - Including JavaScript-generated content
- **Favicon** - Embedded in the document

## Command Options

### Output Location

```bash
--output, -o <path>    Custom output filename
--dir, -d <path>       Output directory
```

**Default behavior:**
Files are saved to `~/Downloads/{domain}/` where `{domain}` is extracted from the page URL.

```bash
# Page: https://github.com/user/repo
# Saves to: ~/Downloads/github.com/user_repo_20251126_215500.html

# Custom filename
inspekt save -o backup.html

# Custom directory
inspekt save -d ~/web-archives

# Both
inspekt save -d ~/archives -o important-page.html
```

### Image Handling

```bash
--remote-images    Keep images as remote URLs (smaller file, needs internet)
--no-images        Skip images entirely (fastest, smallest file)
```

**Full embedding (default):**
```bash
inspekt save
# Images converted to base64 data URIs
# File size: 5-50MB depending on images
# Works completely offline
```

**Remote images (recommended for large pages):**
```bash
inspekt save --remote-images
# Images stay as original URLs
# File size: 100KB-1MB typically
# Requires internet to view images
# Much faster to save
```

**No images:**
```bash
inspekt save --no-images
# Images removed from output
# File size: 50-500KB typically
# Fastest save, smallest file
# Good for text-only archival
```

### Optimization

```bash
--optimize    Aggressive optimization for large pages
--compress    Compress HTML/CSS output
```

**When to use `--optimize`:**
- Complex pages with lots of CSS/fonts
- Pages that timeout during normal save
- When file size matters

```bash
# Large, complex page
inspekt save --optimize

# Maximum compression
inspekt save --optimize --compress

# Fast, small output
inspekt save --remote-images --compress
```

**What `--optimize` does:**
- Removes unused CSS rules
- Removes unused fonts
- Removes hidden elements
- Removes alternative images (srcset)
- Removes alternative fonts

### Content Options

```bash
--no-styles         Keep all CSS (don't remove unused)
--include-scripts   Include JavaScript (disabled by default)
--include-frames    Include iframe content (disabled by default)
--raw               Save raw page without processing
```

**Include JavaScript:**
```bash
# Caution: May affect page functionality
inspekt save --include-scripts
```

**Include iframes:**
```bash
# Useful for pages with embedded content
inspekt save --include-frames
```

**Raw page:**
```bash
# Debugging: save without SingleFile processing
inspekt save --raw
```

### Output Modes

```bash
--quiet, -q    Only output file path (for piping)
--json         Output result as JSON
```

**Normal output:**
```
Capturing page (this may take a moment)...
┌──────────┬─────────────────────────────────────────────────────────────────┐
│ Property │ Value                                                           │
├──────────┼─────────────────────────────────────────────────────────────────┤
│      URL │ https://example.com/page                                        │
│     Path │ /Users/you/Downloads/example.com/Page_Title_20251126_215500.html│
│     Size │ 2.3 MB                                                          │
└──────────┴─────────────────────────────────────────────────────────────────┘
```

**Quiet mode (for scripts):**
```bash
FILE=$(inspekt save -q)
echo "Saved to: $FILE"
```

**JSON mode:**
```bash
inspekt save --json | jq '.path'
```

```json
{
  "ok": true,
  "path": "/Users/you/Downloads/example.com/Page_Title_20251126.html",
  "title": "Page Title",
  "url": "https://example.com/page",
  "size": 2400000,
  "sizeFormatted": "2.3 MB"
}
```

## Use Cases

### 1. Archive Important Pages

```bash
# Save receipt after purchase
inspekt save -d ~/receipts -o "order-12345.html"

# Archive article before paywall
inspekt save --remote-images

# Save documentation page
inspekt save -d ~/docs
```

### 2. Capture Authenticated Content

```bash
# Log into your account in browser
# Navigate to the page you want to save
inspekt save

# Save your social media profile
inspekt save -o my-profile.html

# Archive private dashboard
inspekt save --optimize
```

### 3. Web Development Snapshots

```bash
# Save current state for comparison
inspekt save -o before-changes.html

# Make changes to the page
# Save after state
inspekt save -o after-changes.html

# Compare files
diff before-changes.html after-changes.html
```

### 4. Research & Documentation

```bash
# Save search results
inspekt save --remote-images -o "search-results.html"

# Archive competitor's page
inspekt save -d ~/competitive-analysis

# Save tutorial for offline reading
inspekt save --no-images -o tutorial-text.html
```

### 5. Bug Reports & Evidence

```bash
# Capture bug state
inspekt save -o "bug-report-$(date +%Y%m%d).html"

# Save error page
inspekt save --json > error-capture.json

# Archive page state for support ticket
inspekt save -d ~/support-tickets
```

### 6. Batch Archiving

```bash
#!/bin/bash
# archive-pages.sh - Archive multiple pages

URLS=(
    "https://example.com/page1"
    "https://example.com/page2"
    "https://example.com/page3"
)

for url in "${URLS[@]}"; do
    inspekt open "$url"
    sleep 2  # Wait for page load
    inspekt save --remote-images -d ~/archives
done
```

### 7. Scheduled Backups

```bash
# Add to crontab for daily backups
# crontab -e
0 2 * * * cd ~/projects && inspekt save --json >> backup-log.json
```

## Performance Tips

### For Large Pages

```bash
# Use remote images to avoid embedding large images
inspekt save --remote-images

# Enable optimization
inspekt save --optimize

# Combine both
inspekt save --remote-images --optimize
```

### For Speed

```bash
# Skip images entirely
inspekt save --no-images

# Use remote images + compression
inspekt save --remote-images --compress
```

### For Maximum Fidelity

```bash
# Default settings (all resources embedded)
inspekt save

# Include frames for embedded content
inspekt save --include-frames
```

## Troubleshooting

### Timeout on Complex Pages

**Error:**
```
Error: Execution timeout
```

**Solutions:**
```bash
# Use remote images
inspekt save --remote-images

# Enable optimization
inspekt save --optimize

# Combine both
inspekt save --remote-images --optimize
```

### Connection Error on Large Pages

**Error:**
```
Error: Failed to get result: Max retries exceeded
```

**Solution:**
```bash
# Use remote images to reduce payload size
inspekt save --remote-images
```

### Missing Styles

**Issue:** Saved page looks unstyled

**Solutions:**
```bash
# Don't remove unused styles
inspekt save --no-styles

# Check if styles are in iframes
inspekt save --include-frames
```

### File Too Large

**Issue:** Generated file is very large (50MB+)

**Solutions:**
```bash
# Keep images as remote URLs
inspekt save --remote-images

# Enable aggressive optimization
inspekt save --optimize

# Skip images entirely
inspekt save --no-images
```

### Browser Compatibility

**Note:** Firefox tends to be more reliable than Chrome for page saving.

The SingleFile library was originally designed as a browser extension, so Firefox integration is more mature. Chrome's extension architecture handles large payloads differently, which can cause issues with complex pages.

**If you encounter reliability issues:**

1. **Try Firefox** - Switch to Firefox for more consistent results
2. **Use `--remote-images`** - Most reliable option (smaller payload)
3. **Use `--optimize`** - Helps with complex pages
4. **Restart the bridge** - Run `inspekt restart` if things get stuck
5. **Simplify the page** - Close popups, collapse sections before saving

**Pages that work best:**
- Static content pages
- Articles and documentation
- Simple web applications

**Pages that may have issues:**
- Heavy single-page applications (SPAs)
- Pages with complex lazy-loading
- Sites with strict Content Security Policy (CSP)

## How It Works

1. **SingleFile Library** - Inspekt uses the [SingleFile](https://github.com/gildas-lormeau/SingleFile) browser library to capture pages
2. **Live DOM** - Captures the current rendered state, not the original HTML source
3. **Resource Embedding** - CSS, images, and fonts are embedded as data URIs
4. **Self-Contained** - Output is a single HTML file that works offline

### Technical Details

- **Library Size:** ~900KB (loaded once per session)
- **Execution:** Runs in browser context via Chrome extension
- **Timeout:** Up to 180 seconds for complex pages
- **Output:** Valid HTML5 with embedded resources

## Related Commands

- `inspekt screenshot` - Capture visual screenshot
- `inspekt describe` - Get AI description of page
- `inspekt outline` - Extract page structure
- `inspekt links` - Extract all links from page

## Learn More

- **SingleFile Project:** https://github.com/gildas-lormeau/SingleFile
- **SingleFile Options:** https://github.com/gildas-lormeau/SingleFile/blob/master/README.md
