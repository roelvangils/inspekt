# inspekt axe - Accessibility Testing

The `inspekt axe` command runs comprehensive accessibility audits on web pages using the industry-standard [axe-core](https://github.com/dequelabs/axe-core) library. Test for WCAG 2.0, 2.1, and 2.2 conformance directly from your command line.

## Quick Start

```bash
# Basic audit (WCAG 2 Level AA - recommended)
inspekt axe

# Test WCAG 2.1 Level AA
inspekt axe --level 21aa

# Check a specific accessibility rule
inspekt axe --rule color-contrast
inspekt axe --rule link-name

# List all available rules (~104 rules)
inspekt axe --list-rules

# Include best practices beyond WCAG
inspekt axe --tags best-practice

# Export results as JSON
inspekt axe --json > audit-results.json

# Show issues requiring manual review
inspekt axe --include-incomplete
```

## Why Use Inspekt Axe?

### The Inspekt Advantage

Unlike standalone accessibility testing tools, Inspekt runs audits in **your current browser tab**, which means:

✅ **Tests YOUR authenticated state** - Check accessibility of logged-in areas, user dashboards, private content
✅ **Sees what YOU see** - Tests the actual rendered page with all JavaScript executed
✅ **Continues from YOUR position** - Audit the exact page state after interactions, form fills, filters
✅ **No setup required** - No separate browser instance, no configuration files
✅ **Works offline** - Uses bundled axe-core library, no CDN dependencies
✅ **Fast iteration** - Make changes, re-run audit instantly in the same context

**Example workflow:**
```bash
# You navigate and interact manually
inspekt open https://app.example.com
# Log in, apply filters, navigate to specific state
# Then run audit on YOUR current state
inspekt axe --level 21aa
```

### What Gets Tested

Axe-core tests for:

- **Color contrast** - Text readability against backgrounds
- **Keyboard navigation** - All interactive elements keyboard-accessible
- **ARIA usage** - Proper implementation of ARIA attributes
- **Form labels** - All inputs properly labeled
- **Semantic HTML** - Correct use of headings, landmarks, lists
- **Alt text** - Images have alternative text
- **Focus management** - Proper focus indicators and order
- **Screen reader compatibility** - Content accessible to assistive technology
- **And 90+ more rules** across all WCAG levels

## Command Options

### WCAG Conformance Levels

```bash
--level <level>    WCAG conformance level to test
```

**Available levels:**

| Level | Description | Rules Tested |
|-------|-------------|--------------|
| `2a` | WCAG 2.0 Level A (minimum) | ~25 rules |
| `2aa` | **WCAG 2.0 Level AA (default)** | ~35 rules |
| `2aaa` | WCAG 2.0 Level AAA (highest) | ~45 rules |
| `21a` | WCAG 2.1 Level A | ~27 rules |
| `21aa` | **WCAG 2.1 Level AA (recommended)** | ~38 rules |
| `22aa` | **WCAG 2.2 Level AA (latest)** | ~40 rules |

**Examples:**
```bash
# Default - WCAG 2.0 Level AA
inspekt axe

# Most common - WCAG 2.1 Level AA
inspekt axe --level 21aa

# Latest standard - WCAG 2.2 Level AA
inspekt axe --level 22aa

# Strictest - WCAG 2.0 Level AAA
inspekt axe --level 2aaa
```

**Which level should you use?**

- **`2aa`** - Legal minimum for most jurisdictions (ADA, Section 508)
- **`21aa`** - Modern standard, includes mobile accessibility (2018)
- **`22aa`** - Latest standard, includes cognitive accessibility (2023)
- **`2aaa`** - Exceeds legal requirements, very strict

### Additional Rule Tags

```bash
--tags <tags>    Comma-separated additional tags
```

Add supplementary tests beyond WCAG standards:

```bash
# Include Deque's best practices
inspekt axe --tags best-practice

# Include experimental rules
inspekt axe --tags experimental

# Multiple tags
inspekt axe --level 21aa --tags best-practice,experimental
```

**Available tags:**
- `best-practice` - Deque's recommended practices beyond WCAG
- `experimental` - Cutting-edge accessibility rules
- `wcag***` - Specific WCAG tags (auto-included via `--level`)

### Filtering Rules

Control which rules are included or excluded from your audit:

```bash
--disable-rule <rules>    Exclude specific rules (blacklist)
--enable-rule <rules>     Run ONLY these rules (whitelist)
```

Both options support comma-separated values and can be used multiple times.

**Disable specific rules (blacklist):**
```bash
# Exclude color contrast checks
inspekt axe --disable-rule color-contrast

# Exclude multiple rules (comma-separated)
inspekt axe --disable-rule color-contrast,label,link-name

# Exclude multiple rules (multiple flags)
inspekt axe --disable-rule color-contrast --disable-rule label
```

Use `--disable-rule` when you want to run all rules EXCEPT specific ones. This is useful for:
- Ignoring known issues you've documented
- Excluding rules that don't apply to your context
- Focusing on new violations by excluding accepted issues

**Enable specific rules (whitelist):**
```bash
# Check ONLY color contrast
inspekt axe --enable-rule color-contrast

# Check only these two rules
inspekt axe --enable-rule color-contrast,label

# Focus on naming rules
inspekt axe --enable-rule link-name,button-name,image-alt
```

Use `--enable-rule` when you want to run ONLY specific rules (all others disabled). This is useful for:
- Focused testing of specific issues
- Quick checks for known problem areas
- Targeted regression testing

**Note:** `--enable-rule` and `--disable-rule` are mutually exclusive.

### Rule-Specific Testing

Target individual accessibility rules for focused testing:

```bash
--rule <rule-id>    Check specific accessibility rule
--list-rules        List all available axe-core rules
--no-select         Disable auto-selection of elements
```

**Check a specific rule:**
```bash
# Test color contrast only
inspekt axe --rule color-contrast

# Test ARIA attributes
inspekt axe --rule aria-allowed-attr

# Test link text
inspekt axe --rule link-name
```

When checking a single rule, the output format changes to show detailed information for each violation including:
- CSS selector
- HTML snippet
- Detailed failure summary
- Impact level
- Help text and documentation URL

**Example output:**
```
Rule: color-contrast
Impact: serious
Help: Elements must meet minimum color contrast ratio thresholds
Documentation: https://dequeuniversity.com/rules/axe/4.11/color-contrast

Found 2 violations:

1. [serious]
   Selector: .header__text
   HTML: <span class="header__text">Welcome</span>
   Issue: Element has insufficient color contrast of 3.2:1
          Expected contrast ratio of 4.5:1
```

**List all available rules:**
```bash
inspekt axe --list-rules
```

Shows all ~104 axe-core rules organized by WCAG level:
```
WCAG 2.0 Level A (61 rules)
  area-alt: Ensure <area> elements have alternative text
  aria-allowed-attr: Ensure ARIA attributes are valid
  button-name: Ensure buttons have discernible text
  ...

WCAG 2.0 Level AA (3 rules)
  color-contrast: Ensure sufficient color contrast
  ...
```

**Auto-Element Selection:**

When a single-rule check finds exactly one violation, Inspekt automatically:
1. Stores the element in `window.__INSPEKT_INSPECTED_ELEMENT__`
2. Highlights it in the browser with a blue outline
3. Scrolls it into view

```
✓ Element auto-selected and highlighted in browser
  Selector: .header__text
  Run 'inspekt inspected' to view full element details
```

You can then inspect the element details:
```bash
inspekt inspected
```

**Disable auto-selection:**
```bash
inspekt axe --rule color-contrast --no-select
```

### Output Options

```bash
--json                 Output full results as JSON
--include-passes       Include passing checks in output
--include-incomplete   Show issues requiring manual review
```

**Table format (default):**
```bash
inspekt axe
```

Shows violations in a clean table:
```
┌─────────────────┬──────────┬───────┬──────────────────────────┐
│ Rule            │ Impact   │ Count │ Description              │
├─────────────────┼──────────┼───────┼──────────────────────────┤
│ color-contrast  │ serious  │ 12    │ Ensure sufficient cont...│
│ image-alt       │ critical │ 3     │ Images must have alt...  │
└─────────────────┴──────────┴───────┴──────────────────────────┘

Summary: 2 violations
  Critical: 1
  Serious: 1

Passes: 45
Tested: https://example.com
```

**JSON format:**
```bash
inspekt axe --json > results.json
```

Full structured data:
```json
{
  "url": "https://example.com",
  "timestamp": "2025-11-22T21:55:49.951Z",
  "axeVersion": "4.11.0",
  "violations": [
    {
      "id": "color-contrast",
      "impact": "serious",
      "description": "Ensure the contrast…",
      "nodes": [
        {
          "html": "<button>Submit</button>",
          "target": [".btn-primary"],
          "failureSummary": "Fix any of the following:\n  Element has insufficient color contrast…"
        }
      ]
    }
  ],
  "summary": {
    "violationCount": 2,
    "criticalCount": 1,
    "seriousCount": 1
  }
}
```

**Include passing checks:**
```bash
inspekt axe --include-passes --json
```

Adds `passes` array to output showing successful rules.

**Show incomplete checks:**
```bash
inspekt axe --include-incomplete
```

Displays issues that need manual verification:
```
Incomplete Checks (Manual Review Required):

  • color-contrast: Ensure the contrast... (5 elements)
  • label: Form elements must have labels (2 elements)
```

These are issues axe-core cannot automatically determine - you need to manually verify them. **Important**: ~43% of real accessibility issues require manual testing!

### Performance Options

```bash
--timeout <seconds>    Timeout in seconds (default: 30)
```

Axe-core typically takes 5-15 seconds on most pages:

```bash
# Increase timeout for very large pages
inspekt axe --timeout 60

# Decrease for fast iteration
inspekt axe --timeout 15
```

## Understanding Results

### Impact Levels

Violations are categorized by severity:

| Impact | Meaning | Color | Action Required |
|--------|---------|-------|-----------------|
| **Critical** | Severe accessibility barrier | 🔴 Red | Fix immediately |
| **Serious** | Major accessibility issue | 🟡 Yellow | Fix soon |
| **Moderate** | Noticeable accessibility problem | 🔵 Blue | Fix when possible |
| **Minor** | Small accessibility improvement | ⚫ Gray | Nice to have |

**Priority order:**
1. Fix all **Critical** issues first
2. Then **Serious** issues
3. Then **Moderate** issues
4. Then **Minor** issues
5. Finally, review **Incomplete** checks manually

### Common Violations

#### color-contrast (Serious/Critical)

**What it means:** Text doesn't have enough contrast against its background.

**Example failure:**
```
Light gray text (#999999) on white background (#FFFFFF)
Contrast ratio: 2.8:1 - Required: 4.5:1
```

**How to fix:**
```css
/* Before */
.text { color: #999999; }

/* After */
.text { color: #767676; }  /* 4.5:1 ratio ✓ */
```

#### image-alt (Critical)

**What it means:** Images lack alternative text for screen readers.

**Example failure:**
```html
<img src="logo.png">
```

**How to fix:**
```html
<img src="logo.png" alt="Company Logo">
```

#### label (Critical)

**What it means:** Form inputs don't have associated labels.

**Example failure:**
```html
<input type="text" name="email">
```

**How to fix:**
```html
<label for="email">Email Address</label>
<input type="text" id="email" name="email">

<!-- Or -->
<label>
  Email Address
  <input type="text" name="email">
</label>
```

#### list (Serious)

**What it means:** List items (`<li>`) used outside proper list containers.

**Example failure:**
```html
<div>
  <li>Item 1</li>
  <li>Item 2</li>
</div>
```

**How to fix:**
```html
<ul>
  <li>Item 1</li>
  <li>Item 2</li>
</ul>
```

#### heading-order (Moderate)

**What it means:** Heading levels skip (e.g., H1 → H3, skipping H2).

**Example failure:**
```html
<h1>Main Title</h1>
<h3>Subsection</h3>  <!-- Skipped H2! -->
```

**How to fix:**
```html
<h1>Main Title</h1>
<h2>Subsection</h2>
```

#### region (Moderate)

**What it means:** Page content not contained in landmark regions.

**How to fix:**
```html
<header>...</header>
<nav>...</nav>
<main>
  <!-- All main content goes here -->
</main>
<footer>...</footer>
```

### Incomplete Checks Explained

Some accessibility issues cannot be automatically detected. Axe-core flags these as "incomplete" requiring human review.

**Common incomplete checks:**

1. **color-contrast** - Elements with background images or gradients
2. **label** - Inputs that might be labeled via ARIA
3. **link-name** - Links that might have context from surrounding content
4. **image-alt** - Alt text that might be inappropriate despite existing

**How to review:**
1. Inspect each flagged element
2. Use browser DevTools to examine context
3. Test with actual screen reader (NVDA, JAWS, VoiceOver)
4. Verify with keyboard navigation
5. Document manual testing results

## Real-World Examples

### Example 1: E-commerce Product Page

```bash
# Navigate to product page
inspekt open https://store.example.com/products/laptop

# Run comprehensive audit
inspekt axe --level 21aa --tags best-practice --include-incomplete
```

**Common issues found:**
- Color contrast on price badges
- Missing alt text on product images
- Form labels for quantity selectors
- Heading hierarchy in product details
- Keyboard focus on image gallery

### Example 2: Dashboard After Login

```bash
# Navigate and log in manually
inspekt open https://app.example.com
# (Log in through browser)

# Audit authenticated dashboard
inspekt axe --level 22aa --json > dashboard-audit.json
```

**Why manual login?** Inspekt preserves your authentication state, allowing you to test areas other tools can't reach.

### Example 3: Multi-Step Form

```bash
# Navigate to form
inspekt open https://example.com/signup

# Test step 1
inspekt axe --level 21aa

# Proceed to step 2 (click in browser)
# Test step 2
inspekt axe --level 21aa

# Proceed to step 3
# Test step 3
inspekt axe --level 21aa
```

**Audit each step** of complex workflows while maintaining state.

### Example 4: CI/CD Integration

```bash
#!/bin/bash
# accessibility-test.sh

# Navigate to site
inspekt open https://staging.example.com

# Run audit and capture results
inspekt axe --level 21aa --json > axe-results.json

# Parse results and fail if critical/serious violations
CRITICAL=$(jq '.summary.criticalCount' axe-results.json)
SERIOUS=$(jq '.summary.seriousCount' axe-results.json)

if [ "$CRITICAL" -gt 0 ] || [ "$SERIOUS" -gt 0 ]; then
    echo "❌ Accessibility violations found!"
    echo "Critical: $CRITICAL"
    echo "Serious: $SERIOUS"
    exit 1
fi

echo "✅ No critical accessibility issues"
exit 0
```

Run in CI pipeline:
```yaml
# .github/workflows/accessibility.yml
- name: Run accessibility audit
  run: |
    inspekt server start
    ./accessibility-test.sh
```

### Example 5: Component Library Testing

```bash
# Test button component variations
inspekt open file:///path/to/components/buttons.html
inspekt axe --tags best-practice

# Test form components
inspekt open file:///path/to/components/forms.html
inspekt axe --level 21aa

# Test navigation components
inspekt open file:///path/to/components/nav.html
inspekt axe --level 21aa
```

**Test components in isolation** before integrating into production.

## Advanced Usage

### Filtering Results with jq

```bash
# Get only critical violations
inspekt axe --json | jq '.violations[] | select(.impact == "critical")'

# Count violations by impact
inspekt axe --json | jq '.violations | group_by(.impact) | map({impact: .[0].impact, count: length})'

# Extract all failing elements
inspekt axe --json | jq '.violations[].nodes[].html'

# Get violation help URLs
inspekt axe --json | jq '.violations[] | {rule: .id, help: .helpUrl}'
```

### Comparing Before/After

```bash
# Before fixes
inspekt axe --json > before.json

# Make accessibility improvements
# ...

# After fixes
inspekt axe --json > after.json

# Compare
diff <(jq '.summary' before.json) <(jq '.summary' after.json)
```

### Testing Specific Page States

```bash
# Test mobile viewport
inspekt open https://example.com
# Resize browser to mobile viewport
inspekt axe --level 21aa

# Test dark mode
# Toggle dark mode in browser
inspekt axe --level 21aa

# Test with CSS disabled
inspekt eval "document.querySelectorAll('link[rel=stylesheet]').forEach(el => el.disabled = true)"
inspekt axe --level 21aa
```

### Automated Regression Testing

```bash
#!/bin/bash
# regression-test.sh

BASELINE="baseline-audit.json"
CURRENT="current-audit.json"

# Run current audit
inspekt axe --level 21aa --json > "$CURRENT"

# Compare violation counts
BASELINE_COUNT=$(jq '.summary.violationCount' "$BASELINE")
CURRENT_COUNT=$(jq '.summary.violationCount' "$CURRENT")

if [ "$CURRENT_COUNT" -gt "$BASELINE_COUNT" ]; then
    echo "❌ Regression detected! $CURRENT_COUNT violations (was $BASELINE_COUNT)"
    exit 1
fi

echo "✅ No regression ($CURRENT_COUNT violations)"
exit 0
```

## API Integration

The axe command is also available as an HTTP API endpoint.

### Endpoint

```
POST /api/accessibility/axe
```

### Request

```json
{
  "level": "21aa",
  "tags": "best-practice",
  "include_passes": false,
  "include_incomplete": true,
  "timeout": 30.0
}
```

### Response

```json
{
  "ok": true,
  "result": {
    "url": "https://example.com",
    "timestamp": "2025-11-22T21:55:49.951Z",
    "axeVersion": "4.11.0",
    "violations": [...],
    "summary": {
      "violationCount": 3,
      "criticalCount": 1,
      "seriousCount": 2
    }
  }
}
```

### Example API Call

```bash
curl -X POST http://localhost:8000/api/accessibility/axe \
  -H "Content-Type: application/json" \
  -d '{
    "level": "21aa",
    "tags": "best-practice",
    "include_incomplete": true
  }' | jq '.'
```

### Using with MCP (Model Context Protocol)

When running Inspekt as an MCP server for Claude, the axe command is available as:

```
mcp__inspekt__run_axe_audit
```

Claude can automatically run accessibility audits:

```
You: "Check this page for accessibility issues"
Claude: *Uses mcp__inspekt__run_axe_audit on current page*
Claude: "I found 3 accessibility violations:
1. Color contrast issue on navigation links
2. Missing alt text on logo image
3. Form label missing on search input"
```

## Best Practices

### 1. Test Early and Often

Run accessibility audits throughout development:

```bash
# After each feature
git commit -m "Add new feature"
inspekt axe --level 21aa

# Before PRs
inspekt axe --level 21aa --tags best-practice
```

### 2. Fix High-Impact Issues First

Always prioritize:
1. **Critical** violations (users completely blocked)
2. **Serious** violations (users significantly hindered)
3. **Moderate** violations (users inconvenienced)
4. **Minor** violations (improvements)

### 3. Don't Rely on Automation Alone

Automated testing catches ~30-40% of accessibility issues. Also:

- Test with actual screen readers
- Test keyboard navigation manually
- Review incomplete checks carefully
- Involve users with disabilities in testing

### 4. Test Different States

```bash
# Test all interactive states
inspekt axe  # Default state
# Click modal trigger
inspekt axe  # Modal open
# Submit form with errors
inspekt axe  # Error state
```

### 5. Document Your Standards

```bash
# Create accessibility test script
cat > test-a11y.sh << 'EOF'
#!/bin/bash
# Our accessibility standard: WCAG 2.1 AA + best practices
inspekt axe --level 21aa --tags best-practice --json > audit.json

CRITICAL=$(jq '.summary.criticalCount' audit.json)
SERIOUS=$(jq '.summary.seriousCount' audit.json)

echo "Critical: $CRITICAL, Serious: $SERIOUS"

[ "$CRITICAL" -eq 0 ] && [ "$SERIOUS" -eq 0 ]
EOF

chmod +x test-a11y.sh
./test-a11y.sh
```

### 6. Track Progress Over Time

```bash
# Weekly accessibility report
inspekt axe --json > "audit-$(date +%Y-%m-%d).json"

# View trend
echo "Violations over time:"
jq -r '[.timestamp, .summary.violationCount] | @csv' audit-*.json
```

### 7. Test Representative Pages

Audit a representative sample:
- Homepage
- Main navigation/menu
- Forms (login, signup, checkout)
- Content pages (articles, products)
- User dashboards/account pages
- Error pages (404, 500)
- Search results

### 8. Include Stakeholders

Share results with:
- **Developers** - Fix implementation issues
- **Designers** - Address contrast, focus indicators
- **Content team** - Improve alt text, heading structure
- **QA** - Add accessibility to test plans
- **Product** - Prioritize accessibility work

## Troubleshooting

### Timeout on large pages

**Error:**
```
Error: Execution timeout
```

**Solution:**
```bash
inspekt axe --timeout 60
```

### Different results than other tools

**Why:** Different tools test different rules and have different heuristics.

**axe-core is considered the gold standard** because:
- No false positives (if it reports an issue, it's real)
- Maintained by Deque (accessibility experts)
- Powers Chrome DevTools Lighthouse
- Used by Microsoft, Google, W3C

### Empty results

**Possible causes:**
1. Page hasn't loaded yet
2. Content behind authentication
3. Single-page app not fully rendered

**Solutions:**
```bash
# Wait for page load
inspekt open https://example.com --wait

# Then audit
inspekt axe
```

## Learn More

- **axe-core documentation**: https://github.com/dequelabs/axe-core
- **WCAG Guidelines**: https://www.w3.org/WAI/WCAG21/quickref/
- **Deque University**: https://dequeuniversity.com/
- **WebAIM**: https://webaim.org/
- **A11y Project**: https://www.a11yproject.com/

## Related Commands

- `inspekt outline` - View heading structure for semantic analysis
- `inspekt links` - Analyze link text for clarity
- `inspekt screenshot` - Capture accessibility issues visually
- `inspekt eval` - Test ARIA attributes programmatically
- `inspekt describe` - Get AI-powered page description (screen reader perspective)
