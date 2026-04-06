# inspekt extract - Extract Content from Web Pages

The `inspekt extract` command group extracts structured content from web pages:

- **`inspekt extract article`** - Extract article content as clean Markdown with YAML frontmatter
- **`inspekt extract images`** - Download all images with optional AI-powered categorization

## Quick Start

```bash
# Extract article to stdout
inspekt extract article

# Save to file
inspekt extract article -o article.md

# Use Defuddle engine (better for modern sites)
inspekt extract article --engine defuddle

# Skip YAML frontmatter, use H1 heading instead
inspekt extract article --no-frontmatter

# Cache images locally
inspekt extract article --cache-images

# Remove images entirely
inspekt extract article --exclude-images

# Strip inline formatting for text-to-speech
inspekt extract article --flatten

# Show extraction stats
inspekt extract article --verbose

# Get JSON output for scripting
inspekt extract article --json
```

## Why Use Inspekt Extract?

### The Inspekt Advantage

Unlike web clippers or "save as PDF" tools, Inspekt extracts **clean, semantic content**:

- **Markdown output** - Clean, portable format that works everywhere
- **YAML frontmatter** - Structured metadata (title, author, date, URL)
- **No clutter** - Navigation, ads, and sidebars are removed
- **Your browser session** - Works on logged-in content, paywalled articles
- **Two extraction engines** - Choose the best tool for each site

**Example workflow:**
```bash
# Navigate to an article
inspekt go https://example.com/blog/great-article

# Extract as Markdown
inspekt extract article -o ~/notes/great-article.md
```

## Extraction Engines

Inspekt offers two article extraction engines. Each has strengths depending on the site structure.

### Readability (Default)

[Mozilla Readability](https://github.com/mozilla/readability) is the library that powers Firefox Reader View. It's battle-tested and works well on most news sites and blogs.

```bash
inspekt extract article --engine readability
```

**Strengths:**
- Mature, well-tested codebase
- Aggressive filtering removes more non-article content
- Used by millions via Firefox Reader View
- Good for traditional news sites

**Best for:**
- News articles (CNN, BBC, NYT)
- Blog posts
- Documentation pages
- Static content sites

### Defuddle

[Defuddle](https://github.com/kepano/defuddle) is a modern alternative created by the Obsidian team. It was built specifically because Readability "didn't work well for many sites."

```bash
inspekt extract article --engine defuddle
```

**Strengths:**
- More conservative filtering (keeps uncertain content)
- Uses mobile stylesheet analysis to detect non-essential elements
- Extracts Schema.org metadata (JSON-LD)
- Better handling of footnotes, math, and code blocks
- Active development by the Obsidian team

**Best for:**
- Single-page applications (SPAs)
- Modern React/Vue/Next.js sites
- Sites with complex layouts
- Academic content with footnotes/equations

### Choosing an Engine

| Scenario | Recommended Engine |
|----------|-------------------|
| News articles | `readability` |
| Blog posts | `readability` |
| React/Vue apps | `defuddle` |
| Academic papers | `defuddle` |
| Sites with math/code | `defuddle` |
| When Readability fails | `defuddle` |

### Setting the Default Engine

You can set your preferred engine in the config file:

```yaml
# ~/.config/inspekt/config.yaml
extract:
  engine: defuddle  # or "readability"
```

Then use without the flag:
```bash
inspekt extract article  # Uses your configured default
```

## Command Options

### Engine Selection

```bash
--engine, -e [readability|defuddle]    Extraction engine
```

**Examples:**
```bash
# Explicit engine selection
inspekt extract article --engine readability
inspekt extract article -e defuddle

# Uses config default or "readability"
inspekt extract article
```

### Output Location

```bash
--output, -o <path>    Save to file instead of stdout
```

**Examples:**
```bash
# Save to specific file
inspekt extract article -o article.md

# Save to directory (auto-generates filename)
inspekt extract article -o ~/notes/

# Output to stdout (default)
inspekt extract article
```

### Image Handling

```bash
--cache-images      Download and cache images locally
--exclude-images    Remove images from the output
```

These options are **mutually exclusive** - you can use one or the other, but not both.

#### Cache Images Locally

When `--cache-images` is enabled, images are:
1. Downloaded to `~/.cache/inspekt/images/`
2. Named using URL hash (e.g., `a1b2c3d4e5f6.jpg`)
3. Referenced by local path in the Markdown

```bash
# Keep remote image URLs (default)
inspekt extract article -o article.md

# Cache images locally
inspekt extract article --cache-images -o article.md
```

**Output with `--cache-images`:**
```markdown
![Alt text](/Users/you/.cache/inspekt/images/a1b2c3d4.jpg)
```

**Output without (default):**
```markdown
![Alt text](https://example.com/images/photo.jpg)
```

#### Exclude Images

Remove all images from the output entirely:

```bash
inspekt extract article --exclude-images
```

This removes:
- Inline images: `![alt](url)`
- Reference-style images: `![alt][ref]`
- Image reference definitions

**Use case:** Creating text-only versions for accessibility tools, text-to-speech, or reducing file size.

### Frontmatter Options

```bash
--no-frontmatter    Skip YAML frontmatter, add title as H1 heading instead
```

**Default output (with frontmatter):**
```markdown
---
title: Article Title
author: Jane Doe
date: '2026-01-04T12:00:00Z'
url: https://example.com/article
---

Article content here...
```

**Output with `--no-frontmatter`:**
```markdown
# Article Title

Article content here...
```

**Use case:** When you want clean Markdown without YAML metadata, or when importing into systems that don't support frontmatter.

### Text-to-Speech Preparation

```bash
--flatten    Strip inline formatting (links, bold, italic) for TTS
```

Removes inline Markdown formatting while preserving the text content:

| Markdown | Flattened |
|----------|-----------|
| `[link text](url)` | `link text` |
| `**bold text**` | `bold text` |
| `*italic text*` | `italic text` |
| `` `code` `` | `code` |
| `~~strikethrough~~` | `strikethrough` |

**Example:**
```bash
# Original
inspekt extract article
# Output: "met [tot op het allerlaatste moment onzekerheid](https://...)"

# Flattened
inspekt extract article --flatten
# Output: "met tot op het allerlaatste moment onzekerheid"
```

**Use case:** Preparing articles for text-to-speech engines, screen readers, or plain text export.

**Combining options for TTS:**
```bash
inspekt extract article --no-frontmatter --exclude-images --flatten -o article.txt
```

### Verbose Output

```bash
--verbose, -v    Show extraction details (cache status, stats)
```

Shows additional information during extraction:

**On cache hit:**
```
  Cache hit (2m old, hit #3)
```

**On fresh extraction:**
```
  Extracted: Article Title Here...
  1,234 words · 8,567 chars · 3 images · by Author Name
```

**Use case:** Debugging, monitoring extraction performance, or seeing content statistics.

### Output Formats

```bash
--json    Output as JSON with metadata
```

**Markdown output (default):**
```markdown
---
title: Article Title
author: Jane Doe
date: '2026-01-04T12:00:00Z'
url: https://example.com/article
site: Example Blog
lang: en
---

# Article Title

Article content here...
```

**JSON output:**
```json
{
  "markdown": "---\ntitle: Article Title\n...",
  "metadata": {
    "title": "Article Title",
    "author": "Jane Doe",
    "date": "2026-01-04T12:00:00Z",
    "url": "https://example.com/article",
    "siteName": "Example Blog",
    "lang": "en"
  },
  "stats": {
    "content_length": 5432,
    "image_count": 3
  },
  "engine": "readability"
}
```

### Cache Control

```bash
--force-refresh    Bypass cache, re-extract content
```

Inspekt caches extracted article content to avoid redundant processing. When you extract an article:

1. **First extraction** - Full extraction is performed, result is cached
2. **Subsequent extractions** - Cached result is returned instantly
3. **With `--force-refresh`** - Cache is bypassed, fresh extraction is performed

**Cache behavior:**

| Scenario | Result |
|----------|--------|
| Same URL, same engine | Returns cached content |
| Same URL, different engine | Fresh extraction (engines are cached separately) |
| Different URL | Fresh extraction |
| `--cache-images` | Not cached (local paths would be invalid) |

**Cache settings:**

- **Location:** `~/.config/inspekt/action_cache.db` (SQLite)
- **TTL:** 7 days (configurable via `cache.extract.ttl_days`)
- **Max entries:** 100 per engine

**Disabling cache:**

```yaml
# ~/.config/inspekt/config.yaml
cache:
  extract:
    enabled: false
```

## Output Format

### YAML Frontmatter

The extracted Markdown includes YAML frontmatter with article metadata:

```yaml
---
title: 'Article Title'           # From <title> or og:title
author: Jane Doe                  # From byline or meta tags
date: '2026-01-04T12:00:00Z'     # Publication date (ISO 8601)
url: https://example.com/article  # Canonical URL
site: Example Blog                # Site name
lang: en                          # Language code
---
```

### Markdown Body

The article content is converted to clean Markdown:

- **Headings** - Converted to ATX style (`# Heading`)
- **Links** - Preserved with URLs
- **Images** - `![alt](url)` format
- **Lists** - Unordered use `-`, ordered use numbers
- **Code** - Inline and fenced blocks preserved
- **Emphasis** - `*italic*` and `**bold**`

## Post-Processing Filters

After extraction, Inspekt applies post-processing filters to remove common unwanted content that sometimes leaks through the extraction engines. This includes reading time indicators, audio player buttons, "related articles" sections, and other UI elements.

### How It Works

Filters are defined in a YAML file and matched line-by-line against the extracted Markdown:

- **Pattern matching** - Uses wildcards (`*` = any characters, `?` = single character)
- **Case-insensitive** - Patterns match regardless of case
- **Line-based** - Each line is checked; matching lines are removed entirely

### Filter File Location

Filters are stored in:
```
inspekt/data/extract_filters.yaml
```

### Default Filters

The default filter file includes patterns for:

| Category | Examples |
|----------|----------|
| Audio buttons | "Artikel luisteren", "Listen to article", "LUISTER" |
| Reading time | "*min", "* minutes", "* minuten" |
| Share prompts | "Share on *", "Deel dit artikel" |
| Related content | "## Lees ook*", "Geselecteerd door de redactie*" |
| Skip links | "Direct naar *", "Skip to *" |
| Newsletter | "Subscribe to *", "Schrijf je in *" |

### Adding Custom Filters

Edit the YAML file to add your own patterns:

```yaml
# inspekt/data/extract_filters.yaml
filters:
  # Your custom filters
  - "Advertisement"
  - "Sponsored content"
  - "Click here to *"

  # Wildcards
  - "* comments"        # Matches "5 comments", "42 comments"
  - "Read more about *" # Matches "Read more about this topic"
```

### Pattern Syntax

| Pattern | Matches |
|---------|---------|
| `*min` | "2min", "5min", "10min" |
| `* min` | "2 min", "5 min" (with space) |
| `* minutes` | "5 minutes", "10 minutes" |
| `Share on *` | "Share on Twitter", "Share on Facebook" |
| `## Lees ook*` | Markdown heading "## Lees ook:" |
| `Published*` | "Published: Jan 4", "Published 2026" |

### Example: Site-Specific Filters

If you frequently extract from a specific site with unique UI elements:

```yaml
filters:
  # Existing filters...

  # Site-specific: Example News
  - "Example News Premium"
  - "Unlock full article*"
  - "Members only*"

  # Site-specific: Tech Blog
  - "Join our Discord*"
  - "Watch on YouTube*"
```

### Reloading Filters

Filters are cached for performance. They reload automatically when you run a new extraction command. For development, you can force a reload by restarting Python or calling `reload_extract_filters()` programmatically.

## Use Cases

### 1. Save Articles for Later

```bash
# Extract article to read offline
inspekt extract article -o ~/reading/article.md

# With images for offline viewing
inspekt extract article --cache-images -o ~/reading/article.md

# Clean version without frontmatter
inspekt extract article --no-frontmatter -o ~/reading/article.md
```

### 2. Build a Knowledge Base

```bash
# Extract to Obsidian vault
inspekt extract article -o ~/obsidian/clippings/article.md

# Use Defuddle for better Obsidian compatibility
inspekt extract article -e defuddle -o ~/obsidian/clippings/article.md
```

### 3. Research & Note-Taking

```bash
# Extract multiple articles
for url in "${URLS[@]}"; do
    inspekt go "$url"
    sleep 2
    inspekt extract article -o ~/research/
done
```

### 4. Content Migration

```bash
# Extract content for CMS import
inspekt extract article --json | jq '.markdown' > content.md
```

### 5. Accessibility Review

```bash
# Extract content structure for review
inspekt extract article | head -50
```

### 6. Text-to-Speech Preparation

```bash
# Prepare article for TTS: no frontmatter, no images, no inline formatting
inspekt extract article --no-frontmatter --exclude-images --flatten -o ~/tts/article.txt

# With verbose output to see word count
inspekt extract article --no-frontmatter --exclude-images --flatten -v -o ~/tts/article.txt
```

## How It Works

### Extraction Pipeline

1. **Load engine library** - Readability.js or Defuddle
2. **Clone document** - Create isolated copy for processing
3. **Pre-process** - Remove navigation, ads, sidebars
4. **Extract content** - Identify and extract main article
5. **Parse metadata** - Title, author, date from meta tags/JSON-LD
6. **Convert to Markdown** - HTML to clean Markdown
7. **Generate frontmatter** - YAML header with metadata
8. **Cache images** (optional) - Download and replace URLs

### Engine Comparison

| Feature | Readability | Defuddle |
|---------|-------------|----------|
| Filtering approach | Aggressive | Conservative |
| `<nav>` handling | Via preprocessing | Native |
| Schema.org extraction | No | Yes |
| Math/LaTeX support | No | Yes (MathML) |
| Code block handling | Basic | Language-aware |
| Footnote normalization | No | Yes |
| Mobile stylesheet analysis | No | Yes |

### Pre-processing (Readability)

Because Readability only checks `role="navigation"` (not `<nav>` tags), Inspekt pre-processes the document to remove:

- `<nav>` elements
- `[role="navigation"]` elements
- `[role="banner"]` (page headers)
- `[role="contentinfo"]` (page footers)
- Page-level `<header>` and `<footer>` (not inside `<article>`)

This ensures navigation is properly removed even on sites that don't use ARIA roles.

## Troubleshooting

### Navigation Still Appears

**Issue:** Extracted content includes menu items or navigation links

**Solutions:**
```bash
# Try Defuddle (more conservative filtering)
inspekt extract article -e defuddle

# Check if it's inside the article element
inspekt eval 'document.querySelector("article nav")?.outerHTML'
```

### Content Missing

**Issue:** Important content is missing from extraction

**Solutions:**
```bash
# Try Defuddle (keeps uncertain content)
inspekt extract article -e defuddle

# Check JSON output for what was extracted
inspekt extract article --json | jq '.stats'
```

### Wrong Title/Author

**Issue:** Metadata is incorrect or missing

**Solutions:**
```bash
# Check what metadata exists on the page
inspekt eval 'JSON.stringify({
  ogTitle: document.querySelector("meta[property=\"og:title\"]")?.content,
  author: document.querySelector("meta[name=\"author\"]")?.content,
  jsonLd: document.querySelector("script[type=\"application/ld+json\"]")?.textContent
})'
```

### No Content Extracted

**Error:** "This page may not be an article"

The page might not have recognizable article structure. Try:
```bash
# Use Defuddle
inspekt extract article -e defuddle

# Check if there's an <article> element
inspekt eval 'document.querySelector("article")?.outerHTML.substring(0, 200)'
```

---

## inspekt extract images

Download all images from the current page with optional AI-powered categorization.

### Quick Start

```bash
# Download all images
inspekt extract images

# Generate HTML gallery with lightbox
inspekt extract images --gallery

# Generate gallery with AI categorization
inspekt extract images --gallery --categorize

# Filter by dimensions
inspekt extract images --min-width 200 --min-height 200

# Optimize images during download
inspekt extract images --optimize

# Get highest resolution from srcset
inspekt extract images --prefer-best-quality
```

### Image Categorization

The `--categorize` flag uses AI (CLIP model) to automatically classify each image into categories like photographs, illustrations, charts, logos, etc. This is useful for:

- **Quickly identifying image types** in a large gallery
- **Filtering images** by category in the gallery UI
- **Accessibility audits** - finding images that may need specific alt-text treatment

#### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        IMAGE CATEGORIZATION PIPELINE                        │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────┐
  │  Image   │      │  SVG? Render │      │    CLIP      │      │ Category │
  │   File   │─────▶│   to PNG     │─────▶│   Model      │─────▶│  Result  │
  │          │      │  (512×512)   │      │              │      │          │
  └──────────┘      └──────────────┘      └──────────────┘      └──────────┘
       │                   │                     │                    │
       │                   │                     │                    │
       ▼                   ▼                     ▼                    ▼
   .jpg .png           cairosvg            Zero-shot            Category +
   .webp .gif          renders             classification       Confidence
   .svg .avif          vector to           against 8            (0-100%)
                       raster              category labels

                              CATEGORY LABELS
              ┌─────────────────────────────────────────────┐
              │  • photograph    • chart_or_graph           │
              │  • illustration  • table_as_image           │
              │  • infographic   • text_as_image            │
              │  • logo_or_icon  • decorative               │
              └─────────────────────────────────────────────┘

                           CONFIDENCE LEVELS
              ┌─────────────────────────────────────────────┐
              │  🟢 High   (≥60%)  - Solid badge            │
              │  🟡 Medium (40-60%) - Badge with ~          │
              │  🔴 Low    (<40%)  - Badge with ?           │
              └─────────────────────────────────────────────┘
```

#### Category Types

| Category | Badge Color | Description | Alt-Text Guidance |
|----------|-------------|-------------|-------------------|
| **Photograph** | 🔵 Blue | Real-world photos of people, places, objects | Describe who/what, setting, actions |
| **Illustration** | 🟣 Violet | Drawings, clipart, artistic renderings | Describe subject and style |
| **Infographic** | 🩷 Pink | Data visualization with explanatory text | Summarize main message |
| **Chart/Graph** | 🩵 Cyan | Bar charts, line graphs, pie charts | Describe type, data, trends |
| **Table as Image** | 🔴 Red | Tabular data rendered as image | ⚠️ Convert to real table |
| **Text as Image** | 🟠 Orange | Screenshots, scanned documents | ⚠️ Use actual text |
| **Logo/Icon** | 🟢 Emerald | Brand logos, icons, symbols | Use organization name |
| **Decorative** | ⚫ Gray | Backgrounds, borders, patterns | Mark as artifact |

#### Gallery Features

When using `--gallery --categorize`, the generated HTML gallery includes:

1. **Category badges** on each image card (color-coded by type)
2. **Category filter dropdown** to show only specific types
3. **Confidence indicators** (?, ~, or solid) showing classification certainty

### Accessibility Heuristics

The gallery automatically audits each image's **accessible name** (the text that screen readers announce) and flags common problems. Issues appear as an **INFO badge** on the image card with a tooltip listing all detected warnings.

These heuristics catch real-world CMS mistakes — filenames used as alt text, leaked HTML entities, placeholder names, and more. No configuration is needed; they run automatically on every gallery.

#### How It Works

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ACCESSIBILITY HINT PIPELINE                           │
└─────────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────┐
  │  Image   │      │  Accessible  │      │   20 Rule    │      │  Hints   │
  │   Card   │─────▶│  Name +      │─────▶│   Heuristic  │─────▶│  Badge   │
  │          │      │  Metadata    │      │   Engine     │      │ +Tooltip │
  └──────────┘      └──────────────┘      └──────────────┘      └──────────┘
       │                   │                     │                    │
       │                   │                     │                    │
       ▼                   ▼                     ▼                    ▼
   GalleryImage         name, source,        Pattern-match        ⚠ INFO badge
   dataclass            is_linked,           and content          with list of
                        source_type          analysis             warnings
```

#### Heuristic Reference

The engine checks **20 heuristics** in severity order. Heuristics #1–#3 apply to the image's *structure* (missing alt, decorative status, background image). Heuristics #4–#20 only fire when the image **has** an accessible name, checking its *quality*.

##### Structural Checks (#1–#3)

These detect fundamental accessibility problems regardless of the name's content.

| # | Condition | Warning | Why it matters |
|---|-----------|---------|----------------|
| 1 | `<img>` has no `alt` attribute | "The image has no `alt` attribute. This is mandatory for all `<img>` elements." | Missing `alt` is a WCAG Level A failure (1.1.1). Screen readers may fall back to the filename, which is rarely meaningful. |
| 2 | Decorative image (`alt=""`) inside a link | "This image is marked as decorative, but it's inside a link. The link may have no accessible name." | When a linked image is the *only* content of the link, marking it decorative leaves the link completely invisible to screen readers. |
| 3 | CSS background image | "Background images can't have text alternatives. Make sure they don't convey important information." | Background images are invisible to assistive technology. If they convey meaning, the content must be provided another way. |

##### Name-Quality Checks (#4–#10)

These identify names that *exist* but are likely not useful descriptions.

| # | Condition | Warning | Why it matters |
|---|-----------|---------|----------------|
| 4 | Name matches the image filename (>85% similarity or substring match) | "The accessible name matches the filename, indicating the editor likely didn't set a custom name." | CMS tools often default to the filename as alt text. Names like `DSC_4521` or `hero-banner-v2` don't describe the image. |
| 5 | Name ≤ 3 characters | "The accessible name is very short and likely not descriptive enough." | Single words or abbreviations rarely convey the image's purpose. |
| 6 | Name > 80 characters | "Accessible names should ideally stay under 80 characters. Consider shortening it." | Overly long names are tedious to listen to. Consider using `aria-describedby` for lengthy descriptions. |
| 7 | Starts with "image of", "picture of", "photo of", "graphic of" | "Screen readers already announce 'image' before the name, so the prefix is redundant." | A screen reader will say "image, image of a sunset" — the word "image" is announced twice. |
| 8 | Generic placeholder name (`image`, `photo`, `untitled`, `placeholder`, `banner`, `hero`, `img_123`, `dsc_456`) | "This looks like a placeholder name rather than a meaningful description." | These names indicate the content author didn't replace the default or placeholder text. |
| 9 | Contains filename-like characters (`__`, `--`, `/`, `\`, or file extension like `.jpg`) | "This looks like a filename was used as the accessible name rather than a description." | Only fires when #4 didn't already flag the name. Catches partial filename leaks like `header__2x.webp`. |
| 10 | Name matches the nearest heading on the page (>85% similarity) | "An adjacent heading on the page uses the same text, so this name may be redundant." | Duplicating heading text in the alt attribute creates repetitive content for screen reader users who already heard the heading. |

##### Content Checks (#11–#20)

These catch specific anti-patterns commonly seen in CMS-generated alt text.

| # | Condition | Warning | Why it matters |
|---|-----------|---------|----------------|
| 11 | Contains `©`, `®`, `™`, or `(c)` | "The accessible name contains copyright or trademark symbols. Alt text should describe the image, not convey legal information." | Common on footer logos where CMS editors paste `© 2024 Company` as alt text. Legal notices belong in page text, not image descriptions. |
| 12 | Contains HTML tags (`<br>`, `<span>`, etc.) | "The accessible name contains what looks like HTML tags. Tags are not rendered in accessible names and will be read aloud as-is." | WYSIWYG editors sometimes leak raw HTML into alt attributes. Screen readers will read `<br>` as "less-than br greater-than". |
| 13 | Contains `\n`, `\r`, or HTML entities (`&amp;`, `&nbsp;`, `&#...;`) | "The accessible name contains encoded characters or line breaks that won't render correctly in assistive technology." | Malformed CMS output. Encoded entities in alt text are read literally: "photo ampersand amp semicolon art". |
| 14 | ALL UPPERCASE (≥ 4 letter characters, > 70% uppercase) | "The accessible name is in all caps, which some screen readers may spell out letter by letter." | VoiceOver and JAWS may interpret all-caps text as an abbreviation and spell it out: "C-O-M-P-A-N-Y B-A-N-N-E-R". The 4-character minimum avoids false positives on legitimate abbreviations like `FAQ`, `PDF`, or `SVG`. |
| 15 | Linked image with "logo" in name but no link destination described | "This linked image mentions 'logo' but doesn't describe where the link goes. Consider something like 'Company name – home'." | Only fires when `is_linked=True`. For linked images, the link *destination* matters more than describing the logo's appearance. "Acme Corp – home" is more useful than "Acme Corp logo". |
| 16 | Contains `http://`, `https://`, or `www.` | "The accessible name contains a URL, which is not a meaningful description for screen reader users." | URLs pasted as alt text are extremely common in CMS content. A URL like `https://cdn.example.com/img/hero-2024.jpg` tells the user nothing about the image's content. |
| 17 | Entire name is digits, or matches `#123`, `item-123`, `id-456`, `img-789`, `asset-012` | "The accessible name appears to be a numeric ID rather than a description." | Database IDs or asset management numbers leaking into alt text. The image's internal tracking number is meaningless to users. |
| 18 | Leading/trailing whitespace or multiple consecutive spaces | "The accessible name has irregular spacing that may cause awkward pauses in screen reader output." | Copy-paste artifacts from CMS editors. Extra spaces create unnatural pauses in speech output and indicate sloppy content management. |
| 19 | Ends with image dimensions (`1200x600`, `1200×600`, `32px`) | "The accessible name includes image dimensions, which don't help users understand the content." | Image metadata leaking into alt text. Dimensions like `Banner 1200x600` describe the container, not the content. |
| 20 | Contains "click", "click here", "tap", or "press" | "The accessible name contains interaction instructions. Describe the image content instead." | Instruction-based alt text is an anti-pattern. The alt should describe *what the image shows*, not *what to do with it*. Interaction is already conveyed by the element's role. |

#### Examples

Here are some real-world accessible names and which heuristics they trigger:

```
"DSC_0042.jpg"                    → #4 (filename match), #9 (filename characters)
"img"                             → #5 (too short), #8 (generic placeholder)
"Photo of the team standing in front of the office building on a sunny
 day with everyone smiling and wearing company t-shirts"
                                  → #6 (too long), #7 (redundant prefix)
"© 2024 Acme Corporation"         → #11 (copyright symbols)
"Buy now<br>Free shipping"        → #12 (HTML tags)
"John&amp;Jane's Photo"           → #13 (HTML entities)
"SUMMER SALE BANNER"              → #14 (all caps)
"Company logo"  (linked)          → #15 (linked logo without destination)
"https://cdn.example.com/hero.jpg"→ #16 (URL as alt text)
"asset-49281"                     → #17 (numeric ID)
"  Product showcase  "            → #18 (excessive whitespace)
"Promotional banner 1920x1080"    → #19 (image dimensions)
"Click here to learn more"        → #20 (interaction instructions)
```

!!! tip "Multiple heuristics can fire at once"
    A single image can trigger multiple warnings. For example, `"IMAGE OF CLICK HERE © 2024"` would fire #7 (redundant prefix), #11 (copyright), #14 (all caps), and #20 (click instructions). All warnings appear together in the tooltip.

!!! note "No false positives on abbreviations"
    Heuristic #14 (all caps) requires at least 4 letter characters and > 70% uppercase ratio. This means legitimate abbreviations like `FAQ`, `PDF`, `SVG`, and `NASA logo` won't trigger the warning.

### Installation

Image categorization requires additional dependencies:

```bash
# Install AI classification dependencies
pip install inspekt[image-ai]
```

This installs:
- `torch` - PyTorch for model inference
- `torchvision` - Image processing for CLIP
- `transformers` - Hugging Face CLIP model
- `cairosvg` - SVG rendering for classification

!!! tip "Auto-install prompt"
    If you run `--categorize` without the dependencies, Inspekt will offer to install them automatically.

### Limitations

!!! warning "Convenience Feature"
    Image categorization is a **convenience feature** for quick triage, not a definitive classification system. Always verify categories manually for important use cases.

**Technical limitations:**

| Limitation | Details |
|------------|---------|
| **Model size** | CLIP ViT-B/32 (~600MB) is downloaded on first use |
| **Speed** | ~0.5-2 seconds per image (CPU), faster on GPU/Apple Silicon |
| **Accuracy** | ~70-85% for clear images; ambiguous images may be misclassified |
| **SVG quality** | Depends on cairosvg rendering; complex SVGs may not render perfectly |
| **Edge cases** | Screenshots of photos, photos of illustrations, etc. may confuse the model |

**When NOT to rely on categorization:**

- ❌ Automated accessibility compliance decisions
- ❌ Legal or regulatory documentation
- ❌ Production alt-text generation without human review
- ❌ Detecting sensitive or inappropriate content

**When categorization IS useful:**

- ✅ Quick visual triage of large image collections
- ✅ Identifying potential accessibility issues (text-as-image, tables-as-image)
- ✅ Filtering gallery by image type
- ✅ Getting a starting point for manual review

### Command Options

```bash
inspekt extract images [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--output-dir, -d` | Output directory (default: `~/Downloads/{domain}/images/`) |
| `--gallery` | Generate HTML gallery with lightbox |
| `--categorize` | Classify images by type using AI |
| `--thumbnail-width` | Thumbnail width for gallery (default: 300px) |
| `--optimize` | Convert JPG→WebP, optimize PNG with oxipng |
| `--resize-to-width` | Resize images to max width (downscale only) |
| `--resize-to-height` | Resize images to max height (downscale only) |
| `--min-width` | Skip images narrower than this |
| `--max-width` | Skip images wider than this |
| `--min-height` | Skip images shorter than this |
| `--max-height` | Skip images taller than this |
| `--prefer-best-quality` | Download highest resolution from srcset |
| `--include-background-images` | Include CSS background images (default: yes) |
| `--no-background-images` | Exclude CSS background images |
| `--json` | Output results as JSON |
| `--open` | Open output directory after download |
| `--quiet, -q` | Suppress progress output |
| `--force-refresh` | Re-download even if files exist locally |

### Examples

```bash
# Basic gallery
inspekt extract images --gallery

# Gallery with AI categorization
inspekt extract images --gallery --categorize

# High-quality images only, categorized
inspekt extract images --gallery --categorize --min-width 400 --min-height 300

# Optimize and categorize
inspekt extract images --gallery --categorize --optimize

# JSON output with categories
inspekt extract images --categorize --json

# Quiet mode for scripting
inspekt extract images --gallery --categorize -q
```

---

## Related Commands

- `inspekt summarize` - AI-powered article summary
- `inspekt save` - Save full page as self-contained HTML
- `inspekt describe` - AI description for screen readers
- `inspekt outline` - Extract heading hierarchy

## Learn More

**Article extraction:**

- [Mozilla Readability](https://github.com/mozilla/readability) - Firefox Reader View engine
- [Defuddle](https://github.com/kepano/defuddle) - Obsidian's modern extraction engine
- [Markdownify](https://github.com/matthewwithanm/python-markdownify) - HTML to Markdown conversion

**Image categorization:**

- [OpenAI CLIP](https://github.com/openai/CLIP) - Contrastive Language-Image Pre-training model
- [Hugging Face Transformers](https://huggingface.co/openai/clip-vit-base-patch32) - CLIP model weights
- [CairoSVG](https://cairosvg.org/) - SVG to PNG rendering library
