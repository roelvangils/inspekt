# inspekt pdf - PDF Accessibility Checking

The `inspekt pdf` command group provides tools for checking PDF documents for accessibility compliance. It supports multiple checking engines from quick structural validation to full PDF/UA compliance testing.

## Quick Start

```bash
# Basic accessibility check (6 checks, <1s)
inspekt pdf check document.pdf

# More comprehensive checks (11 checks, 1-2s)
inspekt pdf check document.pdf --engine simple

# Full PDF/UA validation (100+ checks, 30-60s)
inspekt pdf check document.pdf --engine vera

# Generate HTML report and open in browser
inspekt pdf check document.pdf -o report.html --open

# Check multiple files with JSON output
inspekt pdf check "*.pdf" --json

# Run all engines
inspekt pdf check document.pdf --engine all
```

## Commands

### inspekt pdf check

Check PDF files for accessibility issues.

#### Synopsis

```
inspekt pdf check [OPTIONS] FILES...
```

#### Arguments

| Argument | Description |
|----------|-------------|
| `FILES` | One or more PDF files to check. Supports glob patterns like `*.pdf` or `reports/*.pdf`. |

## Options

### Engine Selection

```bash
--engine, -e {basic|simple|vera|all}
```

Which checking engine to use:

| Engine | Checks | Speed | Description |
|--------|--------|-------|-------------|
| `basic` | 6 | <1s | Fast pikepdf-based structural checks (default) |
| `simple` | 11 | 1-2s | Luxembourg simplA11yPDFCrawler methodology |
| `vera` | 100+ | 30-60s | Full PDF/UA validation via veraPDF |
| `all` | All | 30-60s | Run all engines |

**Examples:**
```bash
inspekt pdf check doc.pdf                    # Default: basic
inspekt pdf check doc.pdf --engine simple    # More comprehensive
inspekt pdf check doc.pdf --engine vera      # Full PDF/UA
inspekt pdf check doc.pdf --engine all       # Everything
inspekt pdf check doc.pdf -e simple          # Short form
```

---

```bash
--profile, -p {ua1|ua2|wtpdf}
```

veraPDF validation profile (only applies when using `--engine vera` or `--engine all`):

| Profile | Standard | Description |
|---------|----------|-------------|
| `ua1` | PDF/UA-1 (ISO 14289-1) | Most common standard (default) |
| `ua2` | PDF/UA-2 (ISO 14289-2) | Newer standard based on PDF 2.0 |
| `wtpdf` | WTPDF 1.0 | Well-Tagged PDF accessibility profile |

**Examples:**
```bash
inspekt pdf check doc.pdf --engine vera                    # PDF/UA-1 (default)
inspekt pdf check doc.pdf --engine vera --profile ua2      # PDF/UA-2
inspekt pdf check doc.pdf --engine vera --profile wtpdf    # WTPDF
inspekt pdf check doc.pdf -e vera -p ua2                   # Short form
```

### Output Options

```bash
--json
```

Output results as JSON instead of formatted table. Useful for scripting and CI/CD integration.

**Example:**
```bash
inspekt pdf check doc.pdf --json > results.json
inspekt pdf check doc.pdf --engine simple --json | jq '.simple.summary'
```

---

```bash
--output, -o PATH
```

Save an HTML report to the specified path. If the path doesn't have a `.html` extension, it will be added automatically.

**Examples:**
```bash
inspekt pdf check doc.pdf -o report.html
inspekt pdf check doc.pdf -o report            # Creates report.html
inspekt pdf check doc.pdf -o reports/doc       # Creates reports/doc.html
```

---

```bash
--open
```

Open the HTML report in the default browser after generation. Requires `--output`.

**Example:**
```bash
inspekt pdf check doc.pdf -o report.html --open
```

---

```bash
--verbose, -v
```

Show detailed output including document metadata and extended violation context.

**Example:**
```bash
inspekt pdf check doc.pdf --verbose
inspekt pdf check doc.pdf -v
```

### Report Section Controls

These options control which sections appear in the HTML report (require `--output`):

```bash
--no-cover              # Disable cover page preview
--no-screenshots        # Disable issue screenshots
--no-score              # Disable accessibility score
--no-structure          # Disable structure tree visualization
--no-content-audit      # Disable content audits (images, tables, forms, links)
--no-remediation        # Disable remediation roadmap
```

**Examples:**
```bash
# Minimal report
inspekt pdf check doc.pdf -o report.html \
  --no-cover --no-screenshots --no-structure --no-remediation

# Just check results and score
inspekt pdf check doc.pdf -o report.html --no-content-audit --no-remediation
```

---

```bash
--wcag-level {A|AA|AAA}
```

Filter report by WCAG conformance level. Only shows issues up to the specified level.

**Examples:**
```bash
inspekt pdf check doc.pdf -o report.html --wcag-level A    # Level A only
inspekt pdf check doc.pdf -o report.html --wcag-level AA   # A + AA
inspekt pdf check doc.pdf -o report.html --wcag-level AAA  # All levels
```

### OCR Options

```bash
--no-ocr
```

Disable OCR text layer comparison in HTML report. Speeds up report generation.

---

```bash
--ocr-all-pages
```

Analyze ALL pages for text layer comparison. Default behavior uses smart sampling. May be slow for large documents.

---

```bash
--ocr-lang CODE
```

Tesseract language code for OCR (default: `eng`). Use for non-English documents.

**Examples:**
```bash
inspekt pdf check doc.pdf -o report.html --ocr-lang deu    # German
inspekt pdf check doc.pdf -o report.html --ocr-lang fra    # French
inspekt pdf check doc.pdf -o report.html --ocr-lang nld    # Dutch
```

### AI Features

```bash
--classify-images
```

Enable AI image categorization. Classifies images as: photograph, illustration, infographic, chart_or_graph, table_as_image, text_as_image, logo_or_icon, decorative.

**Example:**
```bash
inspekt pdf check doc.pdf -o report.html --classify-images
```

---

```bash
--generate-alt-text
```

Generate AI alt-text suggestions for images missing alternative text. Requires API key for the selected provider.

**Example:**
```bash
inspekt pdf check doc.pdf -o report.html --generate-alt-text
```

---

```bash
--ai-provider {thoth|anthropic|openai}
```

AI provider for vision analysis (default: `thoth`).

| Provider | API Key Environment Variable |
|----------|------------------------------|
| `thoth` | Default provider |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |

**Examples:**
```bash
inspekt pdf check doc.pdf -o report.html --generate-alt-text --ai-provider anthropic
inspekt pdf check doc.pdf -o report.html --classify-images --ai-provider openai
```

### Tag Visualization

```bash
--show-tags
```

Include tag visualization overlay in HTML report. Shows color-coded tag boundaries and reading order numbers.

**Example:**
```bash
inspekt pdf check doc.pdf -o report.html --show-tags
```

---

```bash
--tag-pages PAGES
```

Specific pages for tag visualization. Accepts comma-separated values or ranges.

**Examples:**
```bash
inspekt pdf check doc.pdf -o report.html --show-tags --tag-pages "1,2,3"
inspekt pdf check doc.pdf -o report.html --show-tags --tag-pages "1-5"
inspekt pdf check doc.pdf -o report.html --show-tags --tag-pages "1,3,5-10"
```

### Color Contrast Analysis

```bash
--check-contrast
```

Enable color contrast analysis. Uses Tesseract OCR to detect text regions and calculate contrast ratios. **Warning:** This is slow (renders at 300 DPI).

**Example:**
```bash
inspekt pdf check doc.pdf -o report.html --check-contrast
```

---

```bash
--contrast-pages PAGES
```

Specific pages for contrast analysis. Recommended for large documents.

**Examples:**
```bash
inspekt pdf check doc.pdf -o report.html --check-contrast --contrast-pages "1"
inspekt pdf check doc.pdf -o report.html --check-contrast --contrast-pages "1-5"
```

### Interactive Preview

```bash
--interactive
```

Include interactive HTML preview with clickable tag regions and keyboard navigation.

**Example:**
```bash
inspekt pdf check doc.pdf -o report.html --interactive
```

---

```bash
--interactive-page NUMBER
```

Page number for interactive preview (default: 1).

**Example:**
```bash
inspekt pdf check doc.pdf -o report.html --interactive --interactive-page 3
```

### veraPDF Options

```bash
--pull-vera
```

Pull or update the veraPDF Docker image before running. Only needed if using Docker instead of native installation.

**Example:**
```bash
inspekt pdf check doc.pdf --engine vera --pull-vera
```

## Examples

### Basic Usage

```bash
# Quick check
inspekt pdf check document.pdf

# Check with more detail
inspekt pdf check document.pdf --engine simple --verbose

# Full PDF/UA validation
inspekt pdf check document.pdf --engine vera
```

### Batch Processing

```bash
# Check all PDFs in current directory
inspekt pdf check "*.pdf"

# Check all PDFs recursively
inspekt pdf check "**/*.pdf"

# Check specific files
inspekt pdf check report.pdf invoice.pdf manual.pdf

# JSON output for scripting
inspekt pdf check "*.pdf" --json > results.json
```

### HTML Reports

```bash
# Basic report
inspekt pdf check doc.pdf -o report.html --open

# Comprehensive report with AI features
inspekt pdf check doc.pdf -o report.html --open \
  --engine simple \
  --classify-images \
  --generate-alt-text \
  --show-tags

# Minimal report for quick review
inspekt pdf check doc.pdf -o report.html --open \
  --no-cover --no-screenshots --no-structure --no-remediation

# Full analysis (slow but thorough)
inspekt pdf check doc.pdf -o report.html --open \
  --engine vera \
  --show-tags \
  --check-contrast --contrast-pages "1-5" \
  --interactive
```

### CI/CD Integration

```bash
#!/bin/bash
# accessibility-check.sh

inspekt pdf check document.pdf --json > result.json

FAILED=$(jq '.basic.summary.failed' result.json)

if [ "$FAILED" -gt 0 ]; then
    echo "❌ PDF has $FAILED accessibility failures"
    exit 1
fi

echo "✅ PDF passed basic accessibility checks"
exit 0
```

### Using Different Profiles

```bash
# Check against PDF/UA-1 (most common)
inspekt pdf check doc.pdf --engine vera --profile ua1

# Check against PDF/UA-2 (newer standard)
inspekt pdf check doc.pdf --engine vera --profile ua2

# Check against WTPDF
inspekt pdf check doc.pdf --engine vera --profile wtpdf

# Compare all profiles
for profile in ua1 ua2 wtpdf; do
  echo "=== Profile: $profile ==="
  inspekt pdf check doc.pdf --engine vera --profile $profile
done
```

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All checks passed (no failures) |
| `1` | One or more checks failed |

## Understanding Results

### Check Statuses

| Status | Icon | Meaning |
|--------|------|---------|
| `pass` | ✓ | Check passed |
| `fail` | ✗ | Check failed (accessibility barrier) |
| `warn` | ⚠ | Warning (potential issue) |
| `skip` | ○ | Check not applicable |

### Severity Levels

| Severity | Color | Meaning |
|----------|-------|---------|
| `critical` | Red | Severe barrier, must fix |
| `serious` | Yellow | Major issue, should fix |
| `moderate` | Cyan | Noticeable problem |
| `minor` | Blue | Small improvement |

### Basic Engine Checks

| Check | Description | WCAG |
|-------|-------------|------|
| Tagged | PDF has structure tree | 1.3.1 (A) |
| Title | Document title + DisplayDocTitle | 2.4.2 (A) |
| Language | Valid BCP-47 language code | 3.1.1 (A) |
| Protected | AT access not blocked | 4.1.2 (A) |
| Bookmarks | Navigation (20+ pages) | 2.4.5 (AA) |
| Scanned | Not image-only | 1.4.5 (AA) |

### Simple Engine Additional Checks

| Check | Description |
|-------|-------------|
| Forms | AcroForm fields detected |
| XFA | XFA dynamic forms (barrier) |
| XMP Metadata | Extended metadata presence |

## Performance Notes

| Feature | Typical Time | Notes |
|---------|--------------|-------|
| Basic engine | <1 second | Fastest option |
| Simple engine | 1-2 seconds | Good balance |
| veraPDF | 30-60 seconds | Java startup overhead |
| Tag visualization | 10-30 seconds | Depends on page count |
| Contrast analysis | 1-5 min | Very slow (300 DPI) |
| AI classification | 2-10 seconds | Per image, network latency |

### Speed Tips

```bash
# For quick validation
inspekt pdf check doc.pdf --engine basic

# Skip slow features in reports
inspekt pdf check doc.pdf -o report.html --no-ocr --no-screenshots

# Limit page ranges for large documents
inspekt pdf check doc.pdf -o report.html --show-tags --tag-pages "1-10"
inspekt pdf check doc.pdf -o report.html --check-contrast --contrast-pages "1"

# Use native veraPDF (faster than Docker)
brew install verapdf
```

## Troubleshooting

### veraPDF Not Available

```
Error: veraPDF is not available
```

**Solutions:**
```bash
# Install natively (recommended, especially on Apple Silicon)
brew install verapdf

# Or use Docker
docker pull ghcr.io/verapdf/cli:latest
```

### Docker Architecture Mismatch

```
Error: does not match the detected host platform
```

This occurs when running the x86 Docker image on Apple Silicon.

**Solution:** Install veraPDF natively:
```bash
brew install verapdf
```

### Docker Not Running

```
Error: Docker is installed but not running
```

**Solutions:**
```bash
# Start Docker
open -a Docker

# Or install veraPDF natively
brew install verapdf
```

### pikepdf Not Installed

```
Error: pikepdf is required for PDF accessibility checking
```

**Solution:**
```bash
pip install pikepdf>=8.0.0
```

### Timeout Errors

```
Error: veraPDF validation timed out
```

**Solutions:**
- Use `--engine simple` for faster checks
- Check smaller files first
- Verify veraPDF installation works

## Related Commands

- [PDF Accessibility Guide](../guide/pdf-accessibility.md) - Comprehensive user guide
- [Web Accessibility Testing](../guide/accessibility-testing.md) - Testing web pages
- `inspekt a11y` - Multi-engine web accessibility testing
- `inspekt axe` - axe-core web testing

## Learn More

- [PDF/UA Standard](https://www.pdfa.org/pdfua-the-iso-standard-for-accessible-pdf/)
- [veraPDF Documentation](https://docs.verapdf.org/)
- [Matterhorn Protocol](https://www.pdfa.org/resource/matterhorn-protocol/)
- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
