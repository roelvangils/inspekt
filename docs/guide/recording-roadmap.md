# Recording & Replay Roadmap

This document outlines planned improvements for the `inspekt record` and `inspekt replay` commands.

## Current Status

The recording and replay system supports:
- Click, right-click, keyboard activation
- Text input with password masking
- Tab navigation with accessible name display
- Checkbox, radio, and select interactions
- Scroll tracking
- Page navigation (including SPAs)
- Visual feedback during replay
- Audio cues for actions
- ACCNAME 1.2 compliant accessible name computation

---

## Planned Improvements

### Phase 1: Reliability

#### Wait for Page Load After Navigation
**Priority:** High | **Effort:** Small

After navigation (explicit or via click), wait for `document.readyState === 'complete'` before executing the next step. Currently replays can fail if the page hasn't fully loaded.

```yaml
# Automatic behavior, no YAML changes needed
- action: click
  target:
    selector: a[href="/products"]
# System waits for page load before next step
- action: click
  target:
    selector: .product-card
```

#### Smart Wait Strategies
**Priority:** High | **Effort:** Medium

Add configurable wait conditions for steps:

```yaml
- action: click
  target:
    selector: "#load-more"
  wait_for:
    visible: ".new-items"      # Wait for element to appear
    networkidle: true          # Wait for network to settle
    timeout: 5000              # Max wait time (ms)
```

#### Retry Logic for Flaky Elements
**Priority:** Medium | **Effort:** Small

Automatically retry finding elements that may take time to render:

```yaml
- action: click
  target:
    selector: ".dynamic-button"
  retry:
    attempts: 3
    interval: 500  # ms between attempts
```

---

### Phase 2: Debugging

#### Screenshot on Failure
**Priority:** High | **Effort:** Small

Automatically capture a screenshot when a replay step fails, saved to `~/.inspekt/failures/`.

```bash
inspekt replay recording.yaml --screenshot-on-failure
```

Output:
```
Step 5 failed: Element not found: .missing-button
Screenshot saved: ~/.inspekt/failures/recording_step5_20241207_143022.png
```

#### Step-by-Step Debug Mode
**Priority:** Medium | **Effort:** Medium

Interactive debugging mode that pauses after each step:

```bash
inspekt replay recording.yaml --debug
```

Features:
- Press Enter to continue to next step
- Press `s` to skip current step
- Press `i` to inspect current page state
- Press `r` to retry current step
- Press `q` to quit

#### Video Recording of Replay
**Priority:** Low | **Effort:** Large

Record the entire replay session as a video file:

```bash
inspekt replay recording.yaml --record-video output.mp4
```

---

### Phase 3: Developer Experience

#### Selector Quality Warnings
**Priority:** Medium | **Effort:** Medium

During recording, analyze selectors and warn about fragile ones:

```
Warning: Fragile selector detected
  Selector: #__next > div:nth-child(3) > div > button
  Suggestion: Add data-testid="submit-button" to this element
```

Detect patterns like:
- Long CSS paths (> 4 levels)
- Auto-generated IDs (`react-select-*`, `ember*`, `ng-*`)
- Index-based selectors (`:nth-child`, `:nth-of-type`)

#### Speed Control
**Priority:** Low | **Effort:** Small

Control replay speed for different use cases:

```bash
inspekt replay recording.yaml --speed slow    # 1s pause between steps
inspekt replay recording.yaml --speed normal  # 300ms pause (default)
inspekt replay recording.yaml --speed fast    # 50ms pause
inspekt replay recording.yaml --speed instant # No visual feedback
```

---

### Phase 4: Assertions

#### Assertion Wizard (Interactive Mode)
**Priority:** High | **Effort:** Large

After recording, interactively add assertions to steps:

```bash
inspekt record --with-assertions
```

Workflow:
1. Record interactions as normal
2. After stopping, enter assertion mode
3. For each step, wizard suggests relevant assertions:

```
Step 3: click on "Add to Cart" button

Suggested assertions:
  [1] Check element visible: .cart-count
  [2] Check text contains: "Added to cart"
  [3] Check element count: .cart-item (currently: 1)
  [4] Check URL contains: /cart
  [5] Skip (no assertion)
  [c] Custom assertion

Select assertion (1-5, c): 1

Added: expect.visible: ".cart-count"
```

The wizard could also:
- Detect DOM changes after each action
- Suggest assertions based on common patterns
- Allow editing assertions in a YAML editor

#### Visual Regression Testing
**Priority:** Medium | **Effort:** Large

Compare screenshots between replay runs:

```yaml
- action: navigate
  url: https://example.com
  expect:
    screenshot: baseline/homepage.png
    threshold: 0.1  # Allow 10% pixel difference
```

---

### Phase 5: Integration

#### Export to Test Frameworks
**Priority:** Medium | **Effort:** Medium

Generate test code from recordings:

```bash
inspekt export recording.yaml --format playwright --output test.spec.ts
inspekt export recording.yaml --format cypress --output test.cy.js
inspekt export recording.yaml --format puppeteer --output test.js
```

Example Playwright output:
```typescript
import { test, expect } from '@playwright/test';

test('recording', async ({ page }) => {
  await page.goto('https://example.com');
  await page.click('button:has-text("Login")');
  await page.fill('input[name="email"]', 'user@example.com');
  await page.fill('input[name="password"]', '••••••••');
  await page.click('button[type="submit"]');
  await expect(page.locator('.dashboard')).toBeVisible();
});
```

#### CI/CD Integration
**Priority:** Low | **Effort:** Medium

Headless replay mode for automated testing:

```bash
inspekt replay recording.yaml --headless --junit-report results.xml
```

Features:
- Run in headless Chrome/Chromium
- Generate JUnit XML reports
- Exit codes for CI (0 = pass, 1 = fail)
- Parallel execution of multiple recordings

---

## Implementation Priority

| Feature | Priority | Effort | Phase |
|---------|----------|--------|-------|
| Wait for page load | High | Small | 1 |
| Smart wait strategies | High | Medium | 1 |
| Screenshot on failure | High | Small | 2 |
| **Assertion wizard** | **High** | **Large** | **4** |
| Retry logic | Medium | Small | 1 |
| Selector warnings | Medium | Medium | 3 |
| Debug mode | Medium | Medium | 2 |
| Export to frameworks | Medium | Medium | 5 |
| Visual regression | Medium | Large | 4 |
| Speed control | Low | Small | 3 |
| Video recording | Low | Large | 2 |
| CI/CD integration | Low | Medium | 5 |

---

## Contributing

If you'd like to contribute to any of these features, please:
1. Open an issue to discuss the approach
2. Reference this roadmap document
3. Follow the existing code patterns in `inspekt/app/cli/record.py` and `inspekt/app/cli/replay.py`
