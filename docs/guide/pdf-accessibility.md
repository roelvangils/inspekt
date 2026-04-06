# PDF Accessibility Testing

Learn how to check PDF documents for accessibility compliance using Inspekt's PDF accessibility checker. Ensure your PDFs are readable by assistive technologies, comply with PDF/UA standards, and provide an accessible experience for all users.

## Overview

Inspekt provides comprehensive PDF accessibility testing through the `inspekt pdf check` command. Unlike web accessibility testing that runs in a browser, PDF checking analyzes the document structure directly using multiple checking engines.

### What Inspekt PDF Checker Does

- **Structure validation**: Verifies the PDF is properly tagged with a logical structure tree
- **Metadata checks**: Ensures document title, language, and accessibility-related settings are properly configured
- **Content analysis**: Detects scanned/image-only documents, form fields, and potential barriers
- **Full PDF/UA validation**: Complete Matterhorn Protocol compliance checking via veraPDF
- **AI-powered analysis**: Categorize images and generate alt-text suggestions
- **Visual reports**: Generate interactive HTML reports with issue visualization

### Three Checking Engines

| Engine | Checks | Speed | Use Case |
|--------|--------|-------|----------|
| **basic** | 6 | <1s | Quick validation |
| **simple** | 11 | 1-2s | Comprehensive metadata checks |
| **vera** | 100+ | 30-60s | Full PDF/UA compliance |

## Why PDF Accessibility Matters

### Legal Requirements

Accessible PDFs are legally required in many jurisdictions:

- **Section 508** (U.S. Federal) - Requires PDF/UA compliance for government documents
- **EN 301 549** (European Union) - Web and mobile accessibility standard includes PDFs
- **AODA** (Ontario, Canada) - Accessibility for Ontarians with Disabilities Act
- **BITV 2.0** (Germany) - Federal accessibility requirements
- **RGAA** (France) - General accessibility framework

### Business Benefits

- **Wider audience reach** - 15% of the global population has some form of disability
- **Improved usability** - Proper structure benefits everyone, including mobile users
- **Better SEO** - Tagged PDFs are better indexed by search engines
- **Reduced legal risk** - Proactive compliance avoids costly remediation
- **Enhanced reputation** - Demonstrates commitment to inclusion

### Technical Benefits

- **Proper document structure** - Logical reading order and navigation
- **Text extraction** - Copy/paste works correctly
- **Reflow support** - Documents adapt to different screen sizes
- **Assistive technology compatibility** - Screen readers can interpret content

## Limitations of Automated Testing

> **Important:** Automated PDF accessibility checkers identify structural issues but cannot fully validate content quality. You cannot rely solely on automated results to claim PDF/UA compliance.

### What Automation CAN Detect

| Check | What It Validates |
|-------|-------------------|
| Tagged structure | StructTreeRoot and MarkInfo present |
| Alt text presence | Figure tags have Alt or ActualText |
| Document title | Title exists and DisplayDocTitle is set |
| Document language | Valid BCP-47 language code |
| Reading order | Tags exist (but not if order is logical) |
| Table headers | TH elements present in tables |
| Bookmarks | Navigation aids for long documents |

### What Requires Manual Review

| Requirement | Why Automation Can't Test It |
|-------------|------------------------------|
| **Alt text quality** | Tools detect *presence*, not if "Figure 1" adequately describes a complex chart |
| **Reading order correctness** | Tools verify tags exist, but only humans can determine if the order is logical |
| **Color contrast** | PDF contrast checking is complex due to layered content |
| **Language switching** | Proper `Lang` attributes for multilingual content |
| **Decorative images** | Should some figures be marked as artifacts? |
| **Table complexity** | Do headers and scope attributes make sense? |

### Recommended Testing Strategy

1. **Start with automation** - Run `inspekt pdf check` to catch structural issues
2. **Manual structure review** - Verify reading order in a PDF viewer with tags panel
3. **Screen reader testing** - Use NVDA, JAWS, or VoiceOver to read the document
4. **Content review** - Check alt text quality and heading hierarchy
5. **User testing** - Include people with disabilities in your testing

## Quick Start

```bash
# Basic accessibility check (fastest)
inspekt pdf check document.pdf

# More comprehensive checks
inspekt pdf check document.pdf --engine simple

# Full PDF/UA validation
inspekt pdf check document.pdf --engine vera

# Generate HTML report
inspekt pdf check document.pdf --engine simple -o report.html --open

# Check multiple files
inspekt pdf check "reports/*.pdf" --json
```

## Understanding PDF Accessibility Standards

### PDF/UA-1 (ISO 14289-1)

The primary standard for accessible PDFs, published in 2012. PDF/UA-1 requires:

- Tagged PDF structure with proper role mapping
- All content in the structure tree or marked as artifact
- Figures require alternative text
- Tables need proper headers
- Document must specify language

**Test with:** `inspekt pdf check doc.pdf --engine vera --profile ua1`

### PDF/UA-2 (ISO 14289-2)

The updated standard (2024) built on PDF 2.0, adding:

- Better support for mathematical content (MathML)
- Enhanced pronunciation support
- Improved table accessibility
- Ruby annotations for East Asian languages

**Test with:** `inspekt pdf check doc.pdf --engine vera --profile ua2`

### WTPDF 1.0

"Well-Tagged PDF" - A subset focused on document structure:

- Emphasis on correct tag usage
- Reading order validation
- Heading hierarchy

**Test with:** `inspekt pdf check doc.pdf --engine vera --profile wtpdf`

### Matterhorn Protocol

A comprehensive testing guide with 31 checkpoints and 136 failure conditions. veraPDF implements the machine-testable portions of Matterhorn, covering:

1. Document settings (metadata, language)
2. Structure elements (tags, roles)
3. Graphics (figures, artifacts)
4. Headings and paragraphs
5. Tables (headers, scope)
6. Lists (structure)
7. And more...

## Checking Engines

### Basic Engine (6 Checks)

The fastest option using pikepdf for fundamental accessibility criteria:

| Check | Severity | What It Validates |
|-------|----------|-------------------|
| **Tagged** | Critical | StructTreeRoot present with MarkInfo/Marked=true |
| **Title** | Serious | Document title set + DisplayDocTitle enabled |
| **Language** | Serious | Valid BCP-47 language code (e.g., "en-US") |
| **Protected** | Critical | Assistive technology access not blocked |
| **Bookmarks** | Moderate | Navigation bookmarks (required for 20+ pages) |
| **Scanned** | Critical | Not an image-only document |

```bash
inspekt pdf check document.pdf --engine basic
```

### Simple Engine (11 Checks)

Based on Luxembourg's simplA11yPDFCrawler methodology. Includes all basic checks plus:

| Check | Severity | What It Validates |
|-------|----------|-------------------|
| **Forms** | Moderate | Detects AcroForm fields (need labels) |
| **XFA** | Serious | XFA dynamic forms (accessibility barrier) |
| **XMP Metadata** | Minor | Extended metadata presence |

The simple engine also adds:
- Language validation using the langcodes library
- P-bit analysis for protection checking
- Form field counting

```bash
inspekt pdf check document.pdf --engine simple
```

### veraPDF Engine (Full PDF/UA)

Complete Matterhorn Protocol validation via veraPDF:

- 100+ individual tests
- PDF/UA-1, PDF/UA-2, and WTPDF profiles
- Detailed violation reports with context

```bash
# PDF/UA-1 (default)
inspekt pdf check document.pdf --engine vera

# PDF/UA-2
inspekt pdf check document.pdf --engine vera --profile ua2

# WTPDF
inspekt pdf check document.pdf --engine vera --profile wtpdf
```

**Installation options:**
```bash
# Native installation (recommended, especially for Apple Silicon)
brew install verapdf

# Docker (x86 only)
docker pull ghcr.io/verapdf/cli:latest
```

## Content Audits

When generating HTML reports, Inspekt performs content audits on:

### Images

- Count of figures with/without alt text
- Decorative images marked as artifacts
- AI classification (with `--classify-images`)
- AI alt-text suggestions (with `--generate-alt-text`)

### Tables

- Table header detection (TH elements)
- Scope attributes
- Caption presence
- Complex table structure warnings

### Forms

- Field count and types
- Label associations
- Tooltip presence
- XFA form detection

### Links

- Link text analysis
- URL vs descriptive text
- Broken internal links

### Lists

- Proper L/LI/Lbl/LBody structure
- Nesting validation

## AI-Powered Features

### Image Categorization (--classify-images)

Automatically categorizes images into types:

| Category | Description |
|----------|-------------|
| `photograph` | Real-world photos |
| `illustration` | Drawn graphics |
| `infographic` | Information graphics |
| `chart_or_graph` | Data visualizations |
| `table_as_image` | Tabular data as image (needs remediation) |
| `text_as_image` | Text rendered as image (needs remediation) |
| `logo_or_icon` | Brand marks, icons |
| `decorative` | Can be marked as artifact |

```bash
inspekt pdf check doc.pdf -o report.html --classify-images
```

### Alt-Text Suggestions (--generate-alt-text)

Generate AI-powered alt text for images missing descriptions:

```bash
inspekt pdf check doc.pdf -o report.html --generate-alt-text
```

**Provider options:**
```bash
--ai-provider thoth      # Default provider
--ai-provider anthropic  # Claude API
--ai-provider openai     # GPT-4 Vision
```

## Tag Visualization (--show-tags)

Visualize the PDF's tag structure with:

- Color-coded tag boundaries
- Reading order numbers
- Issue indicators for problems

```bash
# Show tags for all pages
inspekt pdf check doc.pdf -o report.html --show-tags

# Show tags for specific pages
inspekt pdf check doc.pdf -o report.html --show-tags --tag-pages "1,2,3"
inspekt pdf check doc.pdf -o report.html --show-tags --tag-pages "1-5"
```

## Color Contrast Analysis (--check-contrast)

Analyze text contrast using OCR-based detection:

- Detects text regions via Tesseract OCR
- Calculates contrast ratios against backgrounds
- Reports WCAG violations (4.5:1 for normal text, 3.0:1 for large text)

```bash
# Check contrast on all pages
inspekt pdf check doc.pdf -o report.html --check-contrast

# Check specific pages (recommended for large documents)
inspekt pdf check doc.pdf -o report.html --check-contrast --contrast-pages "1-5"
```

> **Warning:** Contrast analysis is slow (renders at 300 DPI) and may take several minutes for large documents.

## Interactive Preview (--interactive)

Generate an interactive HTML preview with:

- Clickable tag regions
- Keyboard navigation (Tab/Shift+Tab)
- Details panel showing tag properties
- Reading order visualization

```bash
# Interactive preview of page 1
inspekt pdf check doc.pdf -o report.html --interactive

# Interactive preview of specific page
inspekt pdf check doc.pdf -o report.html --interactive --interactive-page 5
```

## HTML Reports

Generate comprehensive HTML reports with:

```bash
inspekt pdf check document.pdf -o report.html --open
```

### Report Sections

| Section | Description | Disable Flag |
|---------|-------------|--------------|
| Cover page | First page thumbnail | `--no-cover` |
| Score | Accessibility grade (A-F) | `--no-score` |
| Check results | Pass/fail for each criterion | - |
| Structure tree | Tag hierarchy visualization | `--no-structure` |
| Content audit | Images, tables, forms, links | `--no-content-audit` |
| Issue screenshots | Visual indicators of problems | `--no-screenshots` |
| OCR comparison | Text layer vs OCR analysis | `--no-ocr` |
| Remediation | Step-by-step fix guidance | `--no-remediation` |

### Customization Examples

```bash
# Minimal report (just check results)
inspekt pdf check doc.pdf -o report.html \
  --no-cover --no-score --no-structure \
  --no-content-audit --no-screenshots --no-remediation

# Full report with AI features
inspekt pdf check doc.pdf -o report.html \
  --classify-images --generate-alt-text --show-tags --interactive

# Filter by WCAG level
inspekt pdf check doc.pdf -o report.html --wcag-level AA
```

## Performance Guide

| Feature | Speed | Notes |
|---------|-------|-------|
| Basic engine | <1s | Quick structural validation |
| Simple engine | 1-2s | More comprehensive metadata |
| veraPDF | 30-60s | Full PDF/UA, Java startup overhead |
| Content audit | 5-20s | Depends on page count |
| Tag visualization | 10-30s | Renders each page |
| Contrast analysis | Very slow | 300 DPI rendering + OCR |
| AI classification | 2-10s | Per image, API latency |
| Interactive preview | 5-15s | Single page rendering |

### Performance Tips

```bash
# Limit pages for large documents
--tag-pages "1-10"
--contrast-pages "1,5,10"

# Skip slow features for quick checks
--no-ocr --no-screenshots

# Use native veraPDF for faster PDF/UA
brew install verapdf  # Much faster than Docker
```

## Common Issues & Remediation

### 1. Untagged PDF

**Problem:** No structure tree found
**Severity:** Critical
**Fix:** Use Adobe Acrobat Pro's "Make Accessible" wizard or reexport from source application with tags enabled.

### 2. Missing Document Title

**Problem:** No title or DisplayDocTitle not enabled
**Severity:** Serious
**Fix:** Set title in document properties and enable "Display Document Title" in Initial View settings.

### 3. No Document Language

**Problem:** Lang attribute not set
**Severity:** Serious
**Fix:** Set document language in File > Properties > Advanced or via Acrobat's Reading Order panel.

### 4. Scanned/Image-Only

**Problem:** Document contains only images with no text layer
**Severity:** Critical
**Fix:** Run OCR (Recognize Text) in Acrobat or recreate from source document.

### 5. Missing Bookmarks

**Problem:** 20+ page document without navigation
**Severity:** Moderate
**Fix:** Add bookmarks based on heading structure using Acrobat's Bookmarks panel.

### 6. XFA Forms

**Problem:** XFA dynamic forms detected
**Severity:** Serious
**Fix:** Convert to AcroForms or recreate form in a modern editor.

### 7. Images Without Alt Text

**Problem:** Figure elements missing Alt or ActualText
**Severity:** Serious
**Fix:** Add alt text via Acrobat's Accessibility panel or mark decorative images as artifacts.

### 8. Tables Without Headers

**Problem:** Tables missing TH elements or scope
**Severity:** Serious
**Fix:** Use Acrobat's Table Editor to define header cells and scope.

## Comparison with Other Tools

| Feature | Inspekt | PAC 2024 | CommonLook | Equidox |
|---------|---------|----------|------------|---------|
| CLI interface | ✓ | ✗ | ✗ | ✗ |
| PDF/UA validation | ✓ (veraPDF) | ✓ | ✓ | ✓ |
| Matterhorn Protocol | ✓ | ✓ | ✓ | ✓ |
| AI features | ✓ | ✗ | ✗ | ✗ |
| Interactive preview | ✓ | ✓ | ✓ | ✓ |
| Tag visualization | ✓ | ✓ | ✓ | ✓ |
| macOS support | ✓ | ✗ | ✓ | ✗ |
| Linux support | ✓ | ✗ | ✗ | ✗ |
| Batch processing | ✓ | Limited | ✓ | ✓ |
| Free/Open source | ✓ | Free | Paid | Paid |
| Remediation tools | Report only | ✗ | ✓ | ✓ |

## Best Practices

### Do

- **Test early in production** - Check PDFs before publishing
- **Use tagged export** - Export from Word/InDesign with tags enabled
- **Review reading order** - Verify logical flow in Acrobat's Order panel
- **Write meaningful alt text** - Describe image content and purpose
- **Test with screen readers** - Use NVDA, JAWS, or VoiceOver
- **Keep structure simple** - Avoid overly complex layouts
- **Document language changes** - Mark foreign language passages

### Don't

- **Rely solely on automation** - Manual review is essential
- **Use "image of text"** - Use real text whenever possible
- **Skip bookmarks for long docs** - Navigation is crucial
- **Flatten tagged PDFs** - Preserve structure tree
- **Ignore XFA warnings** - Convert to AcroForms
- **Use color alone** - Ensure information isn't color-dependent

## Troubleshooting

### veraPDF Not Found

**Error:** `veraPDF is not available`

**Solutions:**
```bash
# Install natively (recommended)
brew install verapdf

# Or use Docker
docker pull ghcr.io/verapdf/cli:latest
```

### Docker Issues on Apple Silicon

**Error:** `does not match the detected host platform`

**Solution:** Install veraPDF natively instead of Docker:
```bash
brew install verapdf
```

### Timeout on Large Documents

**Error:** `veraPDF validation timed out`

**Solutions:**
- Use `--engine simple` for faster checks
- Limit page ranges: `--tag-pages "1-20"`
- Increase timeout (default is 120s)

### Missing Dependencies

**Error:** `pikepdf is required`

**Solution:**
```bash
pip install pikepdf>=8.0.0
```

### OCR/Contrast Analysis Slow

**Issue:** Contrast analysis taking too long

**Solutions:**
- Limit pages: `--contrast-pages "1-5"`
- Skip OCR: `--no-ocr`
- Use lower DPI (not configurable, but consider skipping for large docs)

## Related Commands

- [`inspekt pdf check`](../commands/pdf.md) - Full command reference
- [`inspekt a11y`](accessibility-testing.md) - Web accessibility testing
- `inspekt axe` - axe-core testing (web pages)

## Next Steps

1. **Check your PDFs** - Run `inspekt pdf check document.pdf`
2. **Review the report** - Generate HTML report with `-o report.html --open`
3. **Fix critical issues** - Address tagged structure, language, title first
4. **Test with veraPDF** - Run full PDF/UA validation with `--engine vera`
5. **Manual verification** - Use screen reader and review reading order
6. **Document your process** - Create remediation workflow for your organization

Remember: **Accessible PDFs benefit everyone, not just users with disabilities.**
