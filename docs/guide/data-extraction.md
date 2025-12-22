# Data Extraction

Master data extraction with Inspekt. Learn how to extract links, generate page outlines, get selected text, download files, and extract structured data from web pages.

## Overview

Inspekt provides specialized commands for data extraction:

- `inspekt links` - Extract and analyze links
- `inspekt outline` - Display page heading structure
- `inspekt selected` - Get selected text
- `inspekt download` - Find and download files
- `inspekt info` - Get page metadata
- `inspekt network` - Inspect network requests

## Extracting Links

The `inspekt links` command extracts all links from a page with powerful filtering options.

### Basic Usage

```bash
inspekt links
```

**Output:**
```
→ Home Page
  https://example.com/

↗ External Resource
  https://other-site.com/page

Total: 15 links (8 internal, 7 external)
```

Shows:
- Link text (anchor text)
- URL
- Internal (→) vs External (↗) indicators
- Summary count

### Filter to Internal Links

```bash
inspekt links --only-internal
```

Shows only links to the same domain.

### Filter to External Links

```bash
inspekt links --only-external
```

Shows only links to other domains.

### URLs Only

```bash
inspekt links --only-urls
```

Outputs just URLs (one per line), perfect for piping:

```
https://example.com/page1
https://example.com/page2
https://external.com/resource
```

### Alphabetical Sorting

```bash
inspekt links --alphabetically
```

Sorts links alphabetically by URL.

### Link Enrichment

Get detailed metadata for external links:

```bash
inspekt links --enrich-external
```

Fetches:
- HTTP status code
- MIME type (content-type)
- File size
- Page title
- Language

**Example output:**
```
↗ Documentation
  https://docs.example.com/
  Status: 200 OK | Type: text/html | Size: 42KB | Lang: en
  Title: Example Docs - Getting Started
```

### JSON Output

```bash
inspekt links --json
```

Outputs structured JSON for scripting:

```json
{
  "links": [
    {
      "text": "Home Page",
      "url": "https://example.com/",
      "internal": true
    },
    {
      "text": "External Resource",
      "url": "https://other-site.com/page",
      "internal": false,
      "status": 200,
      "contentType": "text/html",
      "size": 42170,
      "title": "Resource Title",
      "language": "en"
    }
  ],
  "summary": {
    "total": 15,
    "internal": 8,
    "external": 7
  }
}
```

### Combined Filters

```bash
# External URLs only, alphabetically sorted
inspekt links --only-external --only-urls --alphabetically

# Internal links as JSON
inspekt links --only-internal --json

# External links with enrichment
inspekt links --only-external --enrich-external
```

### Practical Uses

**Export links for analysis:**
```bash
inspekt links --only-external --only-urls > external-links.txt
```

**Count total links:**
```bash
inspekt links --only-urls | wc -l
```

**Find PDF links:**
```bash
inspekt links --only-urls | grep "\.pdf$"
```

**Check broken links:**
```bash
inspekt links --only-urls | xargs -I {} curl -s -o /dev/null -w "%{http_code} {}\n" {}
```

**Extract and process with jq:**
```bash
inspekt links --json | jq '.links[] | select(.internal == false) | .url'
```

---

## Page Outline

Display the heading hierarchy of a page for accessibility audits and SEO analysis.

### Basic Usage

```bash
inspekt outline
```

**Output:**
```
H1 Getting Started
   H2 Installation
      H3 Prerequisites
      H3 Setup
   H2 Configuration
      H3 Basic Settings
      H3 Advanced Options
         H4 Environment Variables

Total: 7 headings
```

### Features

- **Native HTML headings** - H1-H6 elements
- **ARIA headings** - Elements with `role="heading"` and `aria-level`, marked with `[ARIA]`
- **Missing level detection** - Gaps in heading hierarchy shown as `[Missing]` in red
- **Duplicate detection** - Repeated heading text (2nd+ occurrence) marked with `[Duplicate]` in yellow
- **Hierarchical indentation** - Visual tree structure
- **Colored output** - Level labels in gray, text in white, indicators in color

### Accessibility Analysis

The outline command automatically detects common heading issues:

**Example with issues:**
```bash
inspekt outline
```

**Output:**
```
[Missing] H1
H2 Citrus Fruits
   H3 Oranges
   H3 Lemons
      H4 Varieties
         [Missing] H5
         H6 Growing Tips
H2 Tropical Fruits
   [ARIA] H3 Mangoes
      H4 Varieties [Duplicate]
   [ARIA] H3 Pineapples
H1 Stone Fruits
   [Missing] H2
   H3 Peaches

Total: 12 headings (4 ARIA) — 3 missing levels, 1 duplicate
```

**Indicators:**

| Indicator | Color | Meaning |
|-----------|-------|---------|
| `[Missing]` | Red | A heading level was skipped (e.g., H2 → H4) |
| `[Duplicate]` | Yellow | Same heading text appears multiple times |
| `[ARIA]` | Gray | Heading uses `role="heading"` instead of native H1-H6 |

### JSON Output

```bash
inspekt outline --json
```

Returns structured data including issue flags:

```json
{
  "headings": [
    {
      "level": 1,
      "text": "",
      "type": "missing",
      "is_missing": true,
      "is_duplicate": false
    },
    {
      "level": 2,
      "text": "Citrus Fruits",
      "type": "native",
      "is_missing": false,
      "is_duplicate": false
    },
    {
      "level": 3,
      "text": "Mangoes",
      "type": "aria",
      "is_missing": false,
      "is_duplicate": false
    }
  ],
  "summary": {
    "total": 12,
    "aria_count": 4,
    "missing_count": 3,
    "duplicate_count": 1
  }
}
```

### Use Cases

**Accessibility audit:**
```bash
inspekt outline
# Check for:
# - Single H1 at the top
# - No missing levels (red [Missing] indicators)
# - No unintentional duplicates (yellow [Duplicate] indicators)
# - Proper use of native headings vs ARIA
```

**Find issues with jq:**
```bash
# Count missing levels
inspekt outline --json | jq '.summary.missing_count'

# Find all duplicate headings
inspekt outline --json | jq '[.headings[] | select(.is_duplicate)] | length'

# List ARIA headings
inspekt outline --json | jq '.headings[] | select(.type == "aria") | .text'
```

**SEO analysis:**
```bash
inspekt outline | grep "H1"
# Should find exactly one H1, and it shouldn't be [Missing]
```

**Content structure:**
```bash
inspekt outline > page-structure.txt
# Document page organization with issue annotations
```

**Compare pages:**
```bash
inspekt outline > page1.txt
# Navigate to another page
inspekt outline > page2.txt
diff page1.txt page2.txt
```

---

## Selection & Inspected Content

Extract content from browser selections or inspected elements in multiple formats.

### Commands Overview

| Command | Source | Use Case |
|---------|--------|----------|
| `inspekt selection` | Text selected in browser | Copy highlighted content |
| `inspekt inspected` | Element from DevTools | Extract specific DOM elements |

### Quick Examples

```bash
# Get selected text
inspekt selection text

# Get selected HTML (formatted and clean)
inspekt selection html --compact --pretty

# Copy HTML to clipboard
inspekt selection html --copy

# Get inspected element's HTML
inspekt inspected html --compact
```

### Output Formats

Both commands support three output formats:

```bash
# Plain text
inspekt selection text

# HTML (with formatting options)
inspekt selection html --pretty --compact

# Markdown (converted from HTML)
inspekt selection markdown
```

### Compact Mode

The `--compact` flag creates documentation-friendly HTML by removing:

- CSS classes and `data-*` attributes
- Inline styles
- SVG path data → `[PATH DATA]`
- Base64 content → `[DATA]`
- Long random strings → `[STRING]`
- Empty comments
- Long text (20+ words) → `...`

**Example:**
```bash
inspekt selection html --compact --pretty
```

**Before:**
```html
<button class="btn btn-primary shadow-lg"
        data-analytics="cta-click"
        style="background: linear-gradient(...)">
  Click here
</button>
```

**After:**
```html
<button>Click here</button>
```

### Full Documentation

For complete details on all options, see:
**[Selection & Inspected Commands](../commands/selection.md)**

### Legacy Command

The `inspekt selected` command still works but is deprecated:

```bash
# Deprecated - use 'inspekt selection text' instead
inspekt selected
inspekt selected --raw
```

---

## Download Files

Find and download files interactively from the current page.

### Interactive Mode

```bash
inspekt download
```

Presents an interactive menu to select files:

```
Found 15 downloadable files:

IMAGES (8 files)
  1. hero-image.jpg (1920x1080)
  2. logo.png (400x200)
  ...

PDF DOCUMENTS (3 files)
  9. user-guide.pdf
  10. report.pdf
  ...

Select files to download (comma-separated, or 'all'):
>
```

### List Files Only

```bash
inspekt download --list
```

Shows available files without downloading.

### Custom Output Directory

```bash
inspekt download --output ~/Downloads/example-com
```

Downloads to a specific directory.

### Custom Timeout

```bash
inspekt download --timeout 60
```

For large files or slow connections (default: 30s).

### Supported File Types

**Images:**
- jpg, jpeg, png, gif, svg, webp, bmp, ico

**Documents:**
- pdf, docx, xlsx, pptx, txt, csv, md

**Videos:**
- mp4, webm, avi, mov, mkv, flv

**Audio:**
- mp3, wav, ogg, m4a, flac

**Archives:**
- zip, rar, tar, gz, tar.gz, 7z, bz2

### How It Works

The `download` command:

1. Searches for downloadable files:
   - `<img>` elements
   - `<a>` elements linking to files
   - `<video>` and `<audio>` sources
   - CSS background images
   - Data URLs

2. Categorizes files by type

3. Presents interactive selection menu

4. Downloads selected files in parallel

5. Shows progress and file sizes

### Practical Uses

**Download all images:**
```bash
inspekt download
# Select "Download all IMAGES"
```

**Download PDFs from documentation:**
```bash
inspekt download --output ~/Documents/docs
# Select PDF files
```

**Batch download resources:**
```bash
# Navigate to resource page
inspekt download --output ~/Downloads/resources
```

---

## Page Information

Get comprehensive metadata about the current page.

### Basic Info

```bash
inspekt info
```

**Output:**
```
URL:      https://example.com
Title:    Example Domain
Domain:   example.com
Protocol: https:
State:    complete
Size:     1280x720
```

### Extended Information

```bash
inspekt info --extended
```

Includes:

**Language & Encoding:**
- Page language
- Character set
- Direction (LTR/RTL)

**Meta Tags:**
- Description
- Keywords
- Viewport settings
- Author

**Resources:**
- Script count
- Stylesheet count
- Image count
- Cookie count

**Security:**
- HTTPS status
- Mixed content warnings
- Content Security Policy
- Referrer policy
- Robots meta tags

**Accessibility:**
- Landmark count
- Heading structure
- Alt text issues
- ARIA labels

**SEO:**
- Canonical URL
- Open Graph tags
- Twitter Card tags
- Structured data (JSON-LD)
- Robots directives

**Performance:**
- localStorage size
- sessionStorage size
- Service worker status

### JSON Output

```bash
inspekt info --json
```

Structured JSON for parsing:

```bash
inspekt info --json | jq '.url'
inspekt info --json | jq '.title'
inspekt info --json | jq '.extended.seo.canonical'
```

---

## Advanced Extraction with eval

For custom extraction needs, use `inspekt eval`:

### Extract Table Data

```bash
inspekt eval "
  const table = document.querySelector('table');
  const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent.trim());
  const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr =>
    Array.from(tr.cells).map(cell => cell.textContent.trim())
  );
  return {headers, rows};
" --format json > table.json
```

### Extract Product Data

```bash
inspekt eval "
  Array.from(document.querySelectorAll('.product')).map(product => ({
    name: product.querySelector('.product-name').textContent.trim(),
    price: product.querySelector('.product-price').textContent.trim(),
    rating: product.querySelector('.rating')?.textContent,
    image: product.querySelector('img')?.src,
    available: !product.classList.contains('out-of-stock')
  }))
" --format json > products.json
```

### Extract Article Content

```bash
inspekt eval "
  ({
    title: document.querySelector('h1')?.textContent,
    author: document.querySelector('.author')?.textContent,
    date: document.querySelector('time')?.getAttribute('datetime'),
    content: document.querySelector('article')?.textContent.trim(),
    tags: Array.from(document.querySelectorAll('.tag')).map(t => t.textContent.trim())
  })
" --format json > article.json
```

### Extract All Images

```bash
inspekt eval "
  Array.from(document.images).map(img => ({
    src: img.src,
    alt: img.alt,
    width: img.naturalWidth,
    height: img.naturalHeight,
    title: img.title,
    loading: img.loading
  }))
" --format json > images.json
```

### Extract Meta Tags

```bash
inspekt eval "
  const meta = {};
  document.querySelectorAll('meta').forEach(tag => {
    const name = tag.name || tag.property;
    if (name) meta[name] = tag.content;
  });
  return meta;
" --format json > meta.json
```

### Extract Forms

```bash
inspekt eval "
  Array.from(document.forms).map(form => ({
    action: form.action,
    method: form.method,
    id: form.id,
    fields: Array.from(form.elements)
      .filter(el => el.name)
      .map(el => ({
        name: el.name,
        type: el.type,
        required: el.required,
        placeholder: el.placeholder
      }))
  }))
" --format json > forms.json
```

### Extract Structured Data (JSON-LD)

```bash
inspekt eval "
  Array.from(document.querySelectorAll('script[type=\"application/ld+json\"]'))
    .map(script => JSON.parse(script.textContent))
" --format json > structured-data.json
```

---

## Data Cleaning & Processing

### Text Normalization

```bash
inspekt eval "
  const text = document.querySelector('.content').textContent;
  return text
    .trim()
    .replace(/\s+/g, ' ')      // Multiple spaces to single
    .replace(/\n+/g, '\n');     // Multiple newlines to single
" --format raw
```

### HTML Stripping

```bash
inspekt eval "
  const html = document.querySelector('.content').innerHTML;
  const temp = document.createElement('div');
  temp.innerHTML = html;
  return temp.textContent.trim();
" --format raw
```

### Data Validation

```bash
inspekt eval "
  Array.from(document.querySelectorAll('.item'))
    .map(item => ({
      title: item.querySelector('.title')?.textContent.trim(),
      link: item.querySelector('a')?.href
    }))
    .filter(item => item.title && item.link);  // Remove incomplete
" --format json
```

### URL Normalization

```bash
inspekt eval "
  Array.from(document.links).map(a => {
    try {
      return new URL(a.href).href;  // Normalize URL
    } catch {
      return null;
    }
  }).filter(Boolean);
" --format json
```

---

## Batch Extraction Examples

### Scrape Multiple Pages

```bash
#!/bin/bash
# Extract data from multiple pages

URLS=(
  "https://example.com/page1"
  "https://example.com/page2"
  "https://example.com/page3"
)

for url in "${URLS[@]}"; do
  echo "Extracting: $url"
  inspekt open "$url" --wait
  inspekt eval "({title: document.title, links: document.links.length})" --format json >> data.jsonl
done
```

### Export All Page Data

```bash
#!/bin/bash
# Complete page export

PAGE_URL=$(inspekt eval "location.href" --format raw)
PAGE_TITLE=$(inspekt eval "document.title" --format raw)

mkdir -p "export/${PAGE_TITLE}"

# Links
inspekt links --json > "export/${PAGE_TITLE}/links.json"

# Outline
inspekt outline > "export/${PAGE_TITLE}/outline.txt"

# Metadata
inspekt info --json > "export/${PAGE_TITLE}/info.json"

# Screenshots
inspekt screenshot --selector "body" --output "export/${PAGE_TITLE}/screenshot.png"

echo "Exported: ${PAGE_TITLE}"
```

---

## Performance Tips

### 1. Limit Results

```bash
inspekt eval "
  Array.from(document.querySelectorAll('.item'))
    .slice(0, 100)  // First 100 only
    .map(item => item.textContent)
" --format json
```

### 2. Extract Only What You Need

```bash
inspekt eval "
  // Good - extract only titles
  Array.from(document.querySelectorAll('.item'))
    .map(item => item.querySelector('.title').textContent)
"
```

### 3. Use Efficient Selectors

```bash
# Good - specific selector
inspekt eval "document.querySelectorAll('.product .title')"

# Avoid - overly broad
inspekt eval "document.querySelectorAll('*').filter(...)"
```

### 4. Batch DOM Queries

```bash
inspekt eval "
  const container = document.querySelector('.container');
  const items = container.querySelectorAll('.item');  // Query once
  return Array.from(items).map(item => ({
    title: item.querySelector('.title').textContent,
    link: item.querySelector('a').href
  }));
"
```

---

## Next Steps

- **[AI Features](ai-features.md)** - AI-powered summarization and descriptions
- **[Advanced Usage](advanced.md)** - Complex patterns and scripting

---

## Network Requests

Inspekt provides **two methods** for inspecting network requests, each with different capabilities:

| Feature | `inspekt network` | `inspekt network har` |
|---------|------------------|----------------------|
| **API Used** | Performance API | DevTools Network API |
| **Requires DevTools** | No | Yes (F12) |
| **HTTP Status Codes** | No | Yes (200, 404, 500, etc.) |
| **Request Headers** | No | Yes |
| **Response Headers** | No | Yes |
| **Timing Breakdown** | Yes | Yes (more detailed) |
| **Transfer Size** | Yes | Yes |
| **Cache Status** | Yes (heuristic) | Yes (accurate) |
| **Buffer Limit** | ~150-250 entries | Unlimited |
| **Initiator Info** | No | Yes |

### Quick Start

```bash
# Basic network data (works always)
inspekt network

# Full data with status codes (requires DevTools open)
inspekt network har
```

---

### Method 1: Performance API (`inspekt network`)

Works without DevTools. Great for quick performance analysis.

#### Basic Usage

```bash
inspekt network
```

**Output:**
```
Name                                  Type         Size       Time      Proto
-----------------------------------------------------------------------------------
main.js                               script       125.3 KB   245 ms    h2
styles.css                            stylesheet   45.2 KB    120 ms    h2
logo.png                              image        12.1 KB    89 ms     h2
api/data                              fetch        2.3 KB     340 ms    h2

Summary:
  Total requests: 42
  Total transfer: 1.2 MB
  Average time:   156 ms

  By type:
    script: 12
    stylesheet: 5
    image: 18
    fetch: 7

  Slowest: api/data (340 ms)
  Largest: hero.jpg (450.0 KB)
```

#### Filter by Resource Type

```bash
inspekt network script      # JavaScript files
inspekt network stylesheet  # CSS files (or use 'css')
inspekt network fetch       # Fetch/XHR requests
inspekt network xhr         # XHR requests
inspekt network image       # Images
inspekt network font        # Fonts
inspekt network document    # HTML documents
inspekt network svg         # SVG files
inspekt network video       # Video files
inspekt network audio       # Audio files
```

#### Sorting Options

```bash
inspekt network --sort=start  # Chronological order (default)
inspekt network --sort=time   # Slowest first
inspekt network --sort=size   # Largest first
inspekt network --sort=name   # Alphabetical
inspekt network --sort=type   # Grouped by type
```

#### Show Domain Information

```bash
inspekt network --domain      # Add domain column
inspekt network --external    # Only third-party requests
```

#### Limit Results

```bash
inspekt network -n 10                  # Top 10
inspekt network --sort=time -n 5       # 5 slowest
inspekt network --sort=size -n 5       # 5 largest
```

#### JSON Output

```bash
inspekt network --json
inspekt network --json | jq '.summary.byType'
```

---

### Method 2: DevTools HAR (`inspekt network har`)

Full network data with HTTP status codes. **Requires DevTools to be open (F12).**

#### Why Use HAR Mode?

- See **HTTP status codes** (200, 404, 500, etc.)
- Access **request and response headers**
- Get **accurate cache status**
- See **initiator information** (what triggered the request)
- **No buffer limit** - captures all requests
- Export **raw HAR format** for import into other tools

#### Basic Usage

```bash
# Open DevTools first (F12), then:
inspekt network har
```

**Output:**
```
HAR Data (DevTools)
Status codes and headers available!

Name                                  Status   Type         Size       Time
-----------------------------------------------------------------------------------
                                         200   document     15.2 KB    234 ms
main.js                                  200   script       125.3 KB   245 ms
styles.css                               200   stylesheet   45.2 KB    120 ms
api/users                                200   fetch        2.3 KB     340 ms
missing-image.png                        404   image        -          89 ms
api/broken                               500   fetch        512 B      1.2 s

Summary:
  Total requests: 42
  Total transfer: 1.2 MB
  Average time:   156 ms

  By status:
    2xx (Success): 38
    4xx (Client Error): 3
    5xx (Server Error): 1

  Errors: 4
  Cached: 12

  By type:
    script: 12
    stylesheet: 5
    image: 18
    fetch: 7

  Slowest: api/broken (500) (1.2 s)
  Largest: hero.jpg (200) (450.0 KB)
```

#### Filter by Status

```bash
inspekt network har --errors           # Only 4xx and 5xx responses
inspekt network har --sort=status      # Sort by HTTP status code
```

#### Filter by Type

```bash
inspekt network har --type=script      # Only scripts
inspekt network har --type=fetch       # Only API calls
inspekt network har --type=image       # Only images
```

#### Export Raw HAR

Export in standard HAR format for import into Chrome DevTools, Charles Proxy, etc.:

```bash
inspekt network har --raw > page.har
```

#### JSON Output

```bash
inspekt network har --json
inspekt network har --json | jq '.entries[] | select(.status >= 400)'
```

---

### Practical Examples

#### Performance Analysis

```bash
# Find slowest resources
inspekt network --sort=time -n 10

# Find largest resources
inspekt network --sort=size -n 10

# Check all third-party requests
inspekt network --external --domain

# Analyze script loading
inspekt network script --sort=time
```

#### Error Detection (requires DevTools)

```bash
# Find all failed requests
inspekt network har --errors

# Find 404s
inspekt network har --json | jq '.entries[] | select(.status == 404) | .url'

# Find server errors (5xx)
inspekt network har --json | jq '.entries[] | select(.status >= 500)'
```

#### API Analysis (requires DevTools)

```bash
# See all fetch/XHR requests with status codes
inspekt network har --type=fetch

# Find slow API calls
inspekt network har --type=fetch --sort=time

# Export API traffic for debugging
inspekt network har --type=fetch --json > api-calls.json
```

#### Third-Party Audit

```bash
# List all external requests
inspekt network --external --domain

# Count requests by domain
inspekt network --json | jq '.summary.byDomain'

# Find slow third-party resources
inspekt network --external --sort=time -n 10
```

#### Export & Integration

```bash
# Export for spreadsheet analysis
inspekt network --json | jq -r '.entries[] | [.name, .type, .transferSize, .timing.total] | @csv' > network.csv

# Export HAR for Chrome DevTools import
inspekt network har --raw > page.har

# Export for performance monitoring
inspekt network --json | jq '{
  url: .url,
  totalRequests: .summary.totalRequests,
  totalSize: .summary.totalTransferSize,
  avgTime: .summary.averageDuration,
  slowest: .summary.slowestRequest,
  largest: .summary.largestRequest
}' > metrics.json
```

---

### Timing Breakdown

Both methods provide timing information:

| Timing | Description |
|--------|-------------|
| `dns` | DNS lookup time |
| `tcp` / `connect` | TCP connection time |
| `ssl` | SSL/TLS handshake time |
| `ttfb` / `wait` | Time to first byte (server response time) |
| `download` / `receive` | Content download time |
| `total` | Total request duration |

**Example timing analysis:**
```bash
# Find requests with slow DNS
inspekt network --json | jq '.entries[] | select(.timing.dns > 50) | {name, dns: .timing.dns}'

# Find requests with slow server response
inspekt network --json | jq '.entries[] | select(.timing.ttfb > 500) | {name, ttfb: .timing.ttfb}'
```

---

### API & MCP Access

#### REST API

```bash
# Performance API data
curl http://localhost:8767/api/network/

# HAR data (requires DevTools)
curl http://localhost:8767/api/network/har

# Filter by type
curl "http://localhost:8767/api/network/?type=script"
curl "http://localhost:8767/api/network/har?errors_only=true"
```

#### MCP Tools

The network commands are available as MCP tools for AI assistants:

- `get_network_requests` - Performance API data (always works)
- `get_har` - DevTools HAR data (requires DevTools open)

---

### Benefits & Use Cases

#### Performance Optimization
- Identify slow resources blocking page load
- Find oversized images and scripts
- Detect excessive third-party requests
- Measure TTFB and download times

#### Debugging
- Find failed requests (404s, 500s) with HAR mode
- Inspect API responses
- Debug caching issues
- Trace request initiators

#### Security Auditing
- Audit third-party requests
- Check for mixed content
- Review external dependencies
- Monitor data exfiltration

#### SEO & Core Web Vitals
- Analyze Largest Contentful Paint (LCP) resources
- Find render-blocking resources
- Optimize Time to First Byte (TTFB)
- Reduce total page weight

---

### Caveats & Limitations

#### Performance API (`inspekt network`)

| Limitation | Impact | Workaround |
|------------|--------|------------|
| No HTTP status codes | Can't see 404s, 500s | Use `inspekt network har` |
| No headers | Can't inspect request/response headers | Use `inspekt network har` |
| Buffer limit (~150-250) | May miss requests on heavy pages | Capture early, or use HAR |
| Cross-origin restrictions | Some sizes show as 0 | N/A (browser security) |
| Cached resources | Size may be 0 | Check `cached` field |

#### DevTools HAR (`inspekt network har`)

| Limitation | Impact | Workaround |
|------------|--------|------------|
| Requires DevTools open | Won't work headlessly | Use Performance API |
| Only captures after DevTools opened | Misses early requests | Open DevTools before navigating |
| Large HAR files | Slow on heavy pages | Use filters and limits |

#### Best Practice

1. **Quick analysis**: Use `inspekt network`
2. **Need status codes**: Open DevTools (F12), then use `inspekt network har`
3. **CI/CD pipelines**: Use `inspekt network` (no DevTools needed)
4. **Debugging errors**: Use `inspekt network har --errors`

---

## Post-Action Options: --open vs --reveal

Many Inspekt commands that create files support two post-action options:

### --open

Opens the created file in your **default application** for that file type:
- Screenshot → Preview, Photos, or image viewer
- HTML → Web browser
- YAML → Text editor
- Video → Media player

```bash
# Open screenshot in image viewer after saving
inspekt screenshot viewport -o preview.png --open

# Open saved page in browser after saving
inspekt save --open

# Open video after recording replay
inspekt replay login.yaml --video --open
```

**Use case**: When you want to immediately view or edit the content.

### --reveal

Opens your **file explorer** (Finder on macOS, Explorer on Windows) with the file selected:
- macOS: Opens Finder with file highlighted
- Windows: Opens Explorer with file highlighted
- Linux: Opens the containing folder in default file manager

```bash
# Reveal screenshot in Finder after saving
inspekt screenshot viewport -o preview.png --reveal

# Reveal recording file in file explorer
inspekt record --reveal

# Reveal video in Finder
inspekt replay login.yaml --video --reveal
```

**Use case**: When you want to copy, rename, move, or organize the file.

### Inspekt VM Behavior

When running inside the Inspekt VM (Docker container), both `--open` and `--reveal` will **download** the file to your host machine instead, since there's no desktop environment in the VM. The download is triggered automatically in the control panel terminal.

---

## Quick Reference

| Command | Purpose | Example |
|---------|---------|---------|
| `inspekt links` | Extract links | `inspekt links --only-external` |
| `inspekt outline` | Page heading structure with issues | `inspekt outline --json` |
| `inspekt selected` | Get selected text | `inspekt selected --raw` |
| `inspekt download` | Download files | `inspekt download --output ~/Downloads` |
| `inspekt info` | Page metadata | `inspekt info --extended` |
| `inspekt network` | Network requests (Performance API) | `inspekt network --sort=time` |
| `inspekt network har` | Full network data (DevTools) | `inspekt network har --errors` |
