# Accessibility Testing

Learn how to test web accessibility using Inspekt's integrated axe-core testing capabilities. Ensure your websites are accessible to all users, comply with WCAG standards, and catch accessibility issues before they reach production.

## Overview

Inspekt provides professional accessibility testing through the `inspekt axe` command, powered by the industry-standard [axe-core](https://github.com/dequelabs/axe-core) library from Deque Systems - the same engine that powers Chrome DevTools Lighthouse accessibility audits.

### Why Accessibility Matters

**Legal compliance:**
- ADA (Americans with Disabilities Act)
- Section 508 (US Federal)
- EN 301 549 (European Union)
- AODA (Ontario, Canada)
- Many countries require WCAG 2.0 or 2.1 Level AA

**Business benefits:**
- **15% of global population** has some form of disability
- Better SEO (accessible sites rank higher)
- Improved usability for everyone
- Reduced legal risk
- Enhanced brand reputation

**Technical benefits:**
- Better semantic HTML structure
- Improved keyboard navigation
- Clearer content hierarchy
- More maintainable code

## Quick Start

```bash
# Navigate to any page
inspekt open https://example.com

# Run accessibility audit
inspekt axe

# View results
```

**Example output:**
```
┌─────────────────┬──────────┬───────┬──────────────────────────┐
│ Rule            │ Impact   │ Count │ Description              │
├─────────────────┼──────────┼───────┼──────────────────────────┤
│ color-contrast  │ serious  │ 12    │ Ensure sufficient cont...│
│ image-alt       │ critical │ 3     │ Images must have alt...  │
│ label           │ serious  │ 5     │ Form elements must...    │
└─────────────────┴──────────┴───────┴──────────────────────────┘

Summary: 3 violations (1 critical, 2 serious)
Passes: 45
```

That's it! You now have a comprehensive accessibility audit of your page.

## The Inspekt Advantage

### Test Authenticated Content

Unlike browser extensions or standalone tools, Inspekt tests **your current browser state**:

```bash
# You log in manually, navigate to dashboard
inspekt open https://app.example.com
# (Log in through browser UI)

# Audit your actual authenticated session
inspekt axe --level 21aa

# Continue to other logged-in pages
inspekt axe
```

**Test areas other tools can't reach:**
- User dashboards
- Account settings
- Admin panels
- Private content
- Checkout flows
- Form validation states

### Test Dynamic States

Test accessibility at any point in your user journey:

```bash
# Test search results after filtering
inspekt open https://store.example.com
# Apply filters in browser (price range, category, etc.)
inspekt axe

# Test modal dialogs
# Click to open modal
inspekt axe  # Tests modal in open state

# Test form error states
# Submit form with validation errors
inspekt axe  # Tests error messages, ARIA live regions
```

### Continuous Testing Workflow

```bash
# 1. Navigate to feature
inspekt open http://localhost:3000/new-feature

# 2. Test
inspekt axe --level 21aa

# 3. Fix issues in code

# 4. Reload
inspekt reload

# 5. Re-test
inspekt axe --level 21aa

# Repeat until clean
```

**Fast iteration** - No browser restart, no re-authentication, no navigation replay.

## Understanding WCAG Levels

WCAG (Web Content Accessibility Guidelines) has three conformance levels:

### Level A (Minimum)

Basic web accessibility - **most critical issues**:
- All images have alt text
- Videos have captions
- Forms have labels
- Headings are in logical order
- Keyboard accessible

**Test with:**
```bash
inspekt axe --level 2a
```

### Level AA (Standard) ⭐ Recommended

Standard for most legal requirements:
- Everything in Level A
- Color contrast meets 4.5:1 ratio
- Visible focus indicators
- Multiple ways to find pages
- Consistent navigation
- Error suggestions

**Test with:**
```bash
inspekt axe --level 2aa      # WCAG 2.0 AA
inspekt axe --level 21aa     # WCAG 2.1 AA (recommended)
inspekt axe --level 22aa     # WCAG 2.2 AA (latest)
```

**Most organizations target WCAG 2.1 Level AA.**

### Level AAA (Enhanced)

Highest level - exceeds legal requirements:
- Everything in Level AA
- Enhanced color contrast (7:1 ratio)
- Sign language interpretation
- Extended audio descriptions
- Very strict requirements

**Test with:**
```bash
inspekt axe --level 2aaa
```

**Note:** Level AAA is rarely required and very difficult to achieve. Most organizations aim for Level AA.

## Common Accessibility Issues

### 1. Color Contrast

**The problem:** Text doesn't have enough contrast against background.

**Why it matters:** Users with low vision or color blindness can't read content.

**WCAG requirement:**
- Normal text: 4.5:1 contrast ratio (AA), 7:1 (AAA)
- Large text (18pt+): 3:1 contrast ratio (AA), 4.5:1 (AAA)

**How to fix:**
```css
/* Bad - insufficient contrast */
.text {
  color: #999999;              /* Light gray */
  background-color: #FFFFFF;    /* White */
  /* Contrast: 2.8:1 ❌ */
}

/* Good - sufficient contrast */
.text {
  color: #595959;              /* Darker gray */
  background-color: #FFFFFF;    /* White */
  /* Contrast: 7:1 ✓ */
}
```

**Testing:**
```bash
inspekt axe --level 21aa
# Look for "color-contrast" violations

# Or check ONLY color contrast issues
inspekt axe --enable-rule color-contrast
```

### 2. Missing Alt Text

**The problem:** Images lack alternative text.

**Why it matters:** Screen readers can't describe images to blind users.

**How to fix:**
```html
<!-- Bad -->
<img src="product.jpg">

<!-- Good - descriptive alt text -->
<img src="product.jpg" alt="Blue wireless headphones with noise cancellation">

<!-- Good - decorative image -->
<img src="decoration.svg" alt="" role="presentation">
```

**Rules:**
- **Informative images:** Describe what the image shows
- **Functional images:** Describe what happens when clicked
- **Decorative images:** Use empty alt (`alt=""`)
- **Complex images:** Provide long description nearby

**Testing:**
```bash
inspekt axe --level 21aa
# Look for "image-alt" violations
```

### 3. Form Labels

**The problem:** Input fields don't have associated labels.

**Why it matters:** Screen reader users don't know what to enter.

**How to fix:**
```html
<!-- Bad - no label -->
<input type="text" name="email">

<!-- Good - explicit label -->
<label for="email">Email Address</label>
<input type="text" id="email" name="email">

<!-- Good - implicit label -->
<label>
  Email Address
  <input type="text" name="email">
</label>

<!-- Good - ARIA label (use sparingly) -->
<input type="text" name="email" aria-label="Email Address">
```

**Testing:**
```bash
inspekt axe --level 21aa
# Look for "label" violations
```

### 4. Keyboard Navigation

**The problem:** Interactive elements can't be accessed via keyboard.

**Why it matters:** Users who can't use a mouse are excluded.

**Requirements:**
- All interactive elements must be focusable (Tab key)
- Focus order must be logical
- Visible focus indicator required
- No keyboard traps (can Tab out)

**How to fix:**
```html
<!-- Bad - div is not keyboard accessible -->
<div onclick="handleClick()">Click me</div>

<!-- Good - button is keyboard accessible -->
<button onclick="handleClick()">Click me</button>

<!-- Good - div made accessible with role and tabindex -->
<div role="button" tabindex="0" onclick="handleClick()" onkeypress="handleClick()">
  Click me
</div>
```

**CSS for focus indicators:**
```css
/* Don't do this! */
*:focus {
  outline: none; /* ❌ Removes focus indicator */
}

/* Do this instead */
button:focus,
a:focus {
  outline: 2px solid #0066CC;
  outline-offset: 2px;
}
```

**Manual testing:**
```bash
# Automated test
inspekt axe --level 21aa

# Manual keyboard test
# 1. Close your mouse/trackpad
# 2. Navigate page using only Tab, Shift+Tab, Enter, Space, Arrow keys
# 3. Verify you can reach all interactive elements
# 4. Verify you can see where focus is
# 5. Verify you can't get stuck (keyboard trap)
```

### 5. Heading Hierarchy

**The problem:** Heading levels skip (H1 → H3) or are out of order.

**Why it matters:** Screen readers use headings for navigation. Logical structure is essential.

**How to fix:**
```html
<!-- Bad - skips H2 -->
<h1>Main Page Title</h1>
<h3>Subsection</h3>  <!-- Skipped H2! -->

<!-- Good - logical hierarchy -->
<h1>Main Page Title</h1>
<h2>Major Section</h2>
<h3>Subsection</h3>
<h3>Another Subsection</h3>
<h2>Another Major Section</h2>
```

**Rules:**
- One H1 per page (page title)
- Don't skip levels (H1 → H3)
- Headings should describe content
- Visual styling ≠ heading level (use CSS)

**Testing:**
```bash
# View heading structure
inspekt outline

# Check for heading-order violations
inspekt axe --level 21aa --tags best-practice
```

### 6. ARIA Usage

**The problem:** ARIA attributes used incorrectly or unnecessarily.

**Why it matters:** Broken ARIA is worse than no ARIA.

**First rule of ARIA:** Don't use ARIA.

Use semantic HTML instead:
```html
<!-- Bad - unnecessary ARIA -->
<div role="button" tabindex="0" aria-pressed="false">Click</div>

<!-- Good - semantic HTML -->
<button>Click</button>
```

**When ARIA is needed:**
```html
<!-- Good - Live region for dynamic updates -->
<div role="alert" aria-live="polite">
  Form submitted successfully!
</div>

<!-- Good - Expanded state for accordion -->
<button aria-expanded="false" aria-controls="panel">
  Show Details
</button>
<div id="panel" hidden>
  Details here...
</div>
```

**Testing:**
```bash
inspekt axe --level 21aa
# Look for ARIA-related violations
```

## Testing Workflow

### Development Workflow

```bash
# 1. Start development server
npm run dev

# 2. Open in browser via Inspekt
inspekt open http://localhost:3000

# 3. Run accessibility audit
inspekt axe --level 21aa

# 4. Fix violations in code

# 5. Reload browser
inspekt reload

# 6. Re-run audit
inspekt axe --level 21aa

# Repeat 4-6 until clean
```

### Pre-Commit Workflow

```bash
# Create git hook: .git/hooks/pre-commit
#!/bin/bash

echo "Running accessibility audit…"

inspekt open http://localhost:3000 --wait
RESULT=$(inspekt axe --level 21aa --json)

CRITICAL=$(echo "$RESULT" | jq '.summary.criticalCount')
SERIOUS=$(echo "$RESULT" | jq '.summary.seriousCount')

if [ "$CRITICAL" -gt 0 ]; then
    echo "❌ Critical accessibility issues found! Fix before committing."
    exit 1
fi

if [ "$SERIOUS" -gt 5 ]; then
    echo "⚠️  Warning: $SERIOUS serious accessibility issues"
fi

echo "✅ Accessibility check passed"
exit 0
```

### CI/CD Workflow

```yaml
# .github/workflows/accessibility.yml
name: Accessibility Testing

on: [push, pull_request]

jobs:
  a11y-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Install Inspekt
        run: pip install inspekt

      - name: Start servers
        run: |
          inspekt start
          npm run dev &
          sleep 5

      - name: Run accessibility audit
        run: |
          inspekt open http://localhost:3000 --wait
          inspekt axe --level 21aa --json > results.json

      - name: Check results
        run: |
          CRITICAL=$(jq '.summary.criticalCount' results.json)
          SERIOUS=$(jq '.summary.seriousCount' results.json)

          if [ "$CRITICAL" -gt 0 ] || [ "$SERIOUS" -gt 0 ]; then
            echo "❌ Accessibility violations found!"
            echo "Critical: $CRITICAL, Serious: $SERIOUS"
            exit 1
          fi

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v2
        with:
          name: accessibility-results
          path: results.json
```

### Manual Testing Checklist

Automated tools catch ~30-40% of issues. Also test manually:

**Keyboard navigation:**
- [ ] Tab through all interactive elements
- [ ] Verify visible focus indicators
- [ ] Test modals/dialogs (can you escape?)
- [ ] Test dropdown menus
- [ ] Test custom widgets

**Screen reader testing:**
- [ ] Test with NVDA (Windows, free)
- [ ] Test with JAWS (Windows, paid)
- [ ] Test with VoiceOver (Mac, built-in)
- [ ] Verify all images have meaningful alt text
- [ ] Verify form labels are announced
- [ ] Verify error messages are announced
- [ ] Test landmark navigation

**Visual testing:**
- [ ] Zoom to 200% (text should reflow)
- [ ] Test high contrast mode
- [ ] Test with color blindness simulation
- [ ] Verify color is not the only indicator

**Mobile testing:**
- [ ] Test with screen reader on mobile
- [ ] Verify touch targets are 44×44 pixels minimum
- [ ] Test with zoom enabled
- [ ] Verify orientation (portrait/landscape)

## Advanced Testing Strategies

### Progressive Enhancement Testing

Test with features disabled:

```bash
# Test with CSS disabled
inspekt eval "document.querySelectorAll('link[rel=stylesheet]').forEach(l => l.remove())"
inspekt axe

# Test with JavaScript disabled
# (Navigate with JS disabled in browser settings)
inspekt axe

# Test with images disabled
inspekt eval "document.querySelectorAll('img').forEach(i => i.remove())"
inspekt axe
```

### Component Library Testing

Test components in isolation:

```bash
# Test all button variants
for variant in primary secondary danger; do
  inspekt open "http://localhost:6006/button-$variant"
  inspekt axe --level 21aa --json > "button-$variant.json"
done

# Aggregate results
jq -s 'map(.summary.violationCount) | add' button-*.json
```

### Regression Testing

Track accessibility over time:

```bash
#!/bin/bash
# Save baseline
inspekt axe --json > baseline.json

# After changes
inspekt axe --json > current.json

# Compare
BASELINE_VIOLATIONS=$(jq '.summary.violationCount' baseline.json)
CURRENT_VIOLATIONS=$(jq '.summary.violationCount' current.json)

if [ "$CURRENT_VIOLATIONS" -gt "$BASELINE_VIOLATIONS" ]; then
  echo "❌ Accessibility regression detected!"
  echo "Was: $BASELINE_VIOLATIONS, Now: $CURRENT_VIOLATIONS"
  exit 1
fi
```

### Multi-Page Testing

Test entire site:

```bash
#!/bin/bash
PAGES=(
  "/"
  "/about"
  "/products"
  "/contact"
  "/blog"
)

for page in "${PAGES[@]}"; do
  echo "Testing $page…"
  inspekt open "https://example.com$page" --wait
  inspekt axe --level 21aa --json > "audit-${page//\//-}.json"
done

# Summary report
echo "Page,Violations,Critical,Serious" > summary.csv
for file in audit-*.json; do
  PAGE=$(echo "$file" | sed 's/audit-//;s/.json//')
  TOTAL=$(jq '.summary.violationCount' "$file")
  CRITICAL=$(jq '.summary.criticalCount' "$file")
  SERIOUS=$(jq '.summary.seriousCount' "$file")
  echo "$PAGE,$TOTAL,$CRITICAL,$SERIOUS" >> summary.csv
done

cat summary.csv
```

## Best Practices Summary

### ✅ Do

- Test early and often during development
- Fix critical and serious issues immediately
- Test with real screen readers, not just automated tools
- Test keyboard navigation manually
- Include accessibility in code review
- Document accessibility standards for your team
- Test authenticated and dynamic states
- Track accessibility metrics over time

### ❌ Don't

- Rely solely on automated testing (catches ~35% of issues)
- Ignore "incomplete" checks (need manual review)
- Use ARIA when semantic HTML suffices
- Remove focus indicators (:focus outline)
- Use color alone to convey information
- Skip manual keyboard testing
- Forget to test with zoom enabled
- Assume your site is accessible without testing

## Helpful Resources

### Learning

- **WebAIM**: https://webaim.org/ - Comprehensive accessibility guides
- **A11y Project**: https://www.a11yproject.com/ - Beginner-friendly resources
- **MDN Accessibility**: https://developer.mozilla.org/en-US/docs/Web/Accessibility
- **W3C WCAG**: https://www.w3.org/WAI/WCAG21/quickref/ - Official guidelines
- **Deque University**: https://dequeuniversity.com/ - In-depth courses

### Tools

- **axe DevTools**: Browser extension for development
- **WAVE**: Visual accessibility evaluation tool
- **Lighthouse**: Built into Chrome DevTools
- **NVDA**: Free screen reader (Windows)
- **VoiceOver**: Built-in screen reader (Mac)
- **Contrast Checker**: https://webaim.org/resources/contrastchecker/

### Testing

- **Screen reader shortcuts**: https://dequeuniversity.com/screenreaders/
- **ARIA Authoring Practices**: https://www.w3.org/WAI/ARIA/apg/
- **Color contrast analyzer**: https://www.tpgi.com/color-contrast-checker/

### Legal

- **ADA**: https://www.ada.gov/
- **Section 508**: https://www.section508.gov/
- **WebAIM Million**: https://webaim.org/projects/million/ - Annual accessibility report

## Related Inspekt Commands

- [`inspekt axe`](/commands/axe.md) - Full command reference
- `inspekt outline` - View semantic heading structure
- `inspekt links` - Test link text clarity
- `inspekt describe` - AI page description (screen reader perspective)
- `inspekt screenshot` - Visual documentation of issues
- `inspekt eval` - Programmatic accessibility testing

## Next Steps

1. **Start testing**: Run `inspekt axe` on your site
2. **Fix critical issues**: Address blocking accessibility barriers
3. **Set standards**: Decide on WCAG level for your organization
4. **Automate**: Add accessibility tests to CI/CD
5. **Educate**: Train team on accessibility best practices
6. **Test manually**: Use screen readers and keyboard navigation
7. **Iterate**: Make accessibility part of every sprint

Remember: **Accessibility is not a feature, it's a requirement.**
