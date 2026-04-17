# Recording and Replaying Browser Interactions

This tutorial walks you through Inspekt's powerful recording and replay feature. You'll learn how to capture user interactions, add assertions for testing, and automate repetitive tasks.

## What You'll Learn

- Record browser interactions to a YAML file
- Understand the recording file format (v1.1)
- Capture page state (cookies, storage, checksum)
- Record file uploads (content captured via FileReader API)
- Edit recordings to add assertions and preconditions
- Replay recordings for automated testing
- Create accessibility test suites
- Build regression tests for your workflows

## Prerequisites

Before starting, make sure you have:

1. **Inspekt installed** - See [Installation Guide](../getting-started/installation.md)
2. **Browser extension installed** - See [Browser Extensions](../extensions/README.md)
3. **Bridge server running** - Start with `inspekt start`

Verify your setup:

```bash
inspekt status
# Should show: Bridge server is running
```

---

## Part 1: Your First Recording

### Step 1: Open a Page

Let's record a simple interaction. First, open a website in your browser:

```bash
inspekt open https://example.com
```

Or navigate manually to any page in your browser.

### Step 2: Start Recording

```bash
inspekt record my-first-recording.yaml
```

You'll see:

```
Recording: https://example.com
Press Ctrl+C to stop and save
```

### Step 3: Interact with the Page

Now interact with the page normally:

- Click on links and buttons
- Type in form fields
- Press Tab to navigate
- Hover over menus

Each action appears in real-time:

```
  click: a "More information…"
  navigate: https://www.iana.org/help/example-domains
  click: #search-input "Search"
  type: #search-input (6 chars)
  keypress: Enter
```

### Step 4: Stop and Save

Press `Ctrl+C` to stop recording:

```
Stopping recording...

Recording saved to: my-first-recording.yaml
Duration: 23.5s | Steps: 8
```

### Step 5: View Your Recording

Open the YAML file to see what was captured:

```bash
cat my-first-recording.yaml
```

```yaml
# Inspekt Recording v1.0
# Generated: 2025-12-02T14:30:00+00:00
# Duration: 23.5s
# URL: https://example.com

metadata:
  version: "1.0"
  created_at: "2025-12-02T14:30:00+00:00"
  duration_ms: 23500
  starting_url: "https://example.com"
  viewport:
    width: 1920
    height: 1080
  zoom: 1.0

steps:
  - timestamp: 0
    action: navigate
    url: "https://example.com"

  - timestamp: 2340
    action: click
    target:
      selector: "a"
      fallback_selectors:
        - "body > div > p:nth-of-type(2) > a"
      text: "More information…"
      accessible_name: "More information…"
      tag: a
    position:
      x: 245
      y: 367

  - timestamp: 4521
    action: navigate
    url: "https://www.iana.org/help/example-domains"

  # ... more steps
```

---

## Part 2: Understanding the Recording Format

### Metadata and State Sections

Every recording starts with metadata and state information (v1.1 format):

```yaml
metadata:
  version: "1.1"              # Recording format version
  created_at: "2025-12-02…" # When recorded
  duration_ms: 23500          # Total duration
  starting_url: "https://…" # Starting page
  user_agent: "Mozilla/5.0…"
  recorded_on:
    platform: "darwin"        # OS platform
    browser: "Chrome"
    browser_version: "131.0"

state:
  viewport:
    width: 1920               # Browser width
    height: 1080              # Browser height
  zoom: 1.0                   # Device pixel ratio
  scroll:
    x: 0                      # Initial scroll X
    y: 0                      # Initial scroll Y
  # Optional (with --capture-state):
  cookies: "base64…"        # Captured cookies
  local_storage: "base64…"  # Captured storage
  checksum: "sha256:…"      # DOM structure hash
```

See [State Management](state-management.md) for details on capturing and restoring page state.

### Step Types

#### Navigate
URL changes (including SPA navigation):

```yaml
- timestamp: 0
  action: navigate
  url: "https://example.com/page"
```

#### Click
Mouse clicks with element targeting:

```yaml
- timestamp: 1234
  action: click
  target:
    selector: "#submit-btn"
    fallback_selectors:
      - "[data-testid='submit']"
      - "form > button"
    text: "Submit"
    accessible_name: "Submit form"
    tag: button
  position:
    x: 450
    y: 320
```

#### Type
Text input into fields:

```yaml
- timestamp: 2500
  action: type
  target:
    selector: "#email"
    accessible_name: "Email address"
  value: "user@example.com"
```

For password fields, values are masked:

```yaml
- timestamp: 3000
  action: type
  target:
    selector: "#password"
  value: "••••••••"
  sensitive: true
```

#### Keypress
Special keys and keyboard shortcuts:

```yaml
- timestamp: 3500
  action: keypress
  key: "Tab"
  modifiers: []

# With modifiers
- timestamp: 4000
  action: keypress
  key: "s"
  modifiers:
    - ctrl
```

#### Hover
Mouse hover on interactive elements:

```yaml
- timestamp: 5000
  action: hover
  target:
    selector: "nav .dropdown"
    accessible_name: "Menu"
```

#### Upload
File input interactions:

```yaml
- timestamp: 6000
  action: upload
  target:
    selector: "#profile-photo"
    accessible_name: "Profile photo"
    tag: input
    input_type: file
  files:
    - name: "avatar.jpg"
      type: "image/jpeg"
      size: 45678
      lastModified: 1702500000000
      content: "data:image/jpeg;base64,/9j/4AAQSkZJRg…"
```

**How file uploads work:**

1. **Recording**: When you select files, Inspekt uses the `FileReader` API to read the file content as base64
2. **Storage**: Small files (≤100KB) are embedded directly in the YAML; larger files are saved to a separate directory
3. **Replay**: Files are reconstructed using the `DataTransfer` API and set on the input element

**Multiple files:**

```yaml
- timestamp: 6000
  action: upload
  target:
    selector: "#documents"
  files:
    - name: "report.pdf"
      type: "application/pdf"
      size: 125000
      external_path: "recording_files/report.pdf"
    - name: "cover.jpg"
      type: "image/jpeg"
      size: 32000
      content: "data:image/jpeg;base64,…"
```

**Large file storage:**

Files larger than 100KB are saved externally to avoid bloating the YAML:

```
recordings/
├── my-recording.yaml
└── my-recording_files/
    ├── large-document.pdf
    └── video-clip.mp4
```

The YAML references them via `external_path` instead of `content`:

```yaml
files:
  - name: "large-document.pdf"
    type: "application/pdf"
    size: 2500000
    external_path: "my-recording_files/large-document.pdf"
```

> **Security note**: File contents are stored in plain text (base64) in the YAML or as raw files alongside it. Don't share recordings containing sensitive files.

### Target Object

The `target` object identifies elements:

```yaml
target:
  selector: "#main-btn"           # Primary CSS selector
  fallback_selectors:             # Backup selectors (tried in order)
    - "[data-testid='main']"
    - "button.primary"
  text: "Click me"                # Visible text
  accessible_name: "Main action"  # ARIA accessible name
  tag: button                     # HTML tag
  role: button                    # ARIA role
```

**Selector Priority** (from most to least stable):

1. ID: `#element-id`
2. Test ID: `[data-testid="…"]`
3. ARIA label: `[aria-label="…"]`
4. Name attribute: `input[name="…"]`
5. CSS path: `div > form > button`

### Shadow DOM Support

Inspekt has full support for **Web Components with Shadow DOM**. When you interact with elements inside a Shadow DOM, Inspekt automatically:

1. **Records the actual target** - Uses `event.composedPath()` to capture the real element you clicked, not the outer custom element
2. **Generates piercing selectors** - Creates special selectors that can traverse Shadow DOM boundaries
3. **Stores Shadow DOM metadata** - Records both the shadow host and the inner selector

#### Shadow DOM Recording Format

When you click on an element inside a Shadow DOM, the recording includes extra fields:

```yaml
- timestamp: 2500
  action: click
  target:
    selector: "#tag_2"                                    # Inner element selector
    shadow_host: "#odp-search--122343"                    # The custom element host
    piercing_selector: "#odp-search--122343 >>> #tag_2"  # Full path through Shadow DOM
    text: null
    tag: select
```

The `>>>` delimiter indicates a Shadow DOM boundary. During replay, Inspekt:

1. First tries the `piercing_selector` to navigate directly to the element
2. Falls back to `shadow_host` + `selector` combination
3. If those fail, recursively searches through all Shadow roots on the page

#### Example: Web Component Interaction

A page with a custom search component:

```html
<odp-search id="search-widget">
  #shadow-root (open)
    <select id="category">
      <option>Category 1</option>
      <option>Category 2</option>
    </select>
    <input type="text" id="query">
    <button id="search-btn">Search</button>
</odp-search>
```

Recording interactions with this component:

```yaml
# Select from dropdown inside Shadow DOM
- timestamp: 1000
  action: click
  target:
    selector: "#category"
    shadow_host: "#search-widget"
    piercing_selector: "#search-widget >>> #category"
    tag: select

# Type in the search box
- timestamp: 2000
  action: type
  target:
    selector: "#query"
    shadow_host: "#search-widget"
    piercing_selector: "#search-widget >>> #query"
  value: "example search"

# Click the search button
- timestamp: 3000
  action: click
  target:
    selector: "#search-btn"
    shadow_host: "#search-widget"
    piercing_selector: "#search-widget >>> #search-btn"
    accessible_name: "Search"
    tag: button
```

#### Nested Shadow DOM

Inspekt supports multiple levels of Shadow DOM nesting. The piercing selector uses multiple `>>>` delimiters:

```yaml
piercing_selector: "#outer-component >>> #inner-component >>> #button"
```

#### Limitations

- **Closed Shadow DOM**: Elements in closed Shadow roots (`mode: 'closed'`) cannot be accessed or recorded
- **Dynamic Shadow DOM**: Elements created after page load are found via fallback search

### JavaScript Dialogs (alert, confirm, prompt)

Inspekt records interactions with native JavaScript dialogs: `alert()`, `confirm()`, and `prompt()`. These are captured as `jsdialog` actions:

```yaml
# Alert dialog (OK only)
- timestamp: 5000
  action: jsdialog
  dialog_type: alert
  message: "Hello, world!"
  result: true               # Always true (dismissed)

# Confirm dialog (OK/Cancel)
- timestamp: 6000
  action: jsdialog
  dialog_type: confirm
  message: "Are you sure?"
  result: false              # true = OK, false = Cancel

# Prompt dialog (text input + OK/Cancel)
- timestamp: 7000
  action: jsdialog
  dialog_type: prompt
  message: "Enter your name:"
  default_value: "Guest"
  result: "John"             # string = entered text, null = cancelled
```

#### Native vs Synthetic Dialogs

By default, Inspekt uses **native dialogs** during recording. When you trigger an `alert()`, `confirm()`, or `prompt()`, the real browser dialog appears and blocks until you interact with it. This captures authentic user behavior.

For **automation scenarios** (AI agents, browser automation tools, CI/CD), native dialogs are problematic because they block JavaScript execution and cannot be controlled programmatically.

Inspekt provides **synthetic dialogs** as an alternative - HTML overlays that mimic native dialogs but don't block.

#### Enabling Synthetic Dialogs

**Via CLI flag:**

```bash
inspekt record --synthetic-dialogs my-recording.yaml
```

**Via configuration:**

```json
// config.json
{
  "record": {
    "synthetic-dialogs": true
  }
}
```

#### How Synthetic Dialogs Work

When synthetic dialogs are enabled:

1. **Visual Appearance**: HTML overlays that look like native dialogs
2. **Non-blocking**: Functions return immediately with default values:
   - `alert()` returns `undefined` (as normal)
   - `confirm()` returns `true` (OK)
   - `prompt()` returns the default value (or empty string)
3. **Interactable**: You can still click OK/Cancel and type in the overlay
4. **Recording**: The actual result (what you clicked/typed) is recorded

**Important**: Because synthetic dialogs return immediately, page code receives default values before you interact with the overlay. The **recorded result** reflects your actual interaction, so replay will use the correct values.

#### Use Cases for Synthetic Dialogs

| Scenario | Use Synthetic? | Reason |
|----------|---------------|--------|
| Manual testing | No (default) | Authentic user experience |
| AI agent recording | **Yes** | Prevents blocking |
| Browser automation | **Yes** | Enables programmatic control |
| CI/CD environments | **Yes** | No human to click buttons |
| Headless browsers | **Yes** | No UI for native dialogs |

#### Example: Recording with Synthetic Dialogs

```bash
# Start recording with synthetic dialogs enabled
inspekt record --synthetic-dialogs checkout-flow.yaml
```

When the page calls `confirm("Delete this item?")`:

1. A styled HTML overlay appears with "?" icon and "Delete this item?" message
2. The overlay has Cancel and OK buttons
3. You click Cancel
4. The recording captures: `result: false`
5. During replay, `confirm()` will return `false`

#### Replay Behavior

During replay, JavaScript dialogs are **always handled non-blockingly** regardless of how they were recorded:

1. An overlay briefly shows what dialog appeared
2. The recorded result is returned to page code
3. Replay continues without blocking

This ensures consistent, automatable replay regardless of recording method.

---

## Part 3: Adding Assertions

Assertions turn recordings into tests. Edit your YAML file to add `expect:` fields.

### Visibility Assertions

Check if elements are visible after an action:

```yaml
- timestamp: 5500
  action: click
  target:
    selector: "#login-btn"
  expect:
    visible: ".welcome-message"   # Should appear
    hidden: ".login-form"         # Should disappear
```

### URL Assertions

Verify navigation:

```yaml
- timestamp: 5500
  action: click
  target:
    selector: "#login-btn"
  expect:
    url_contains: "/dashboard"
```

### Text Assertions

Check for text content:

```yaml
- timestamp: 6000
  action: navigate
  url: "https://example.com/success"
  expect:
    text_contains: "Thank you for your order"
```

### Console Error Checks

Add an inspekt command to check for JavaScript errors:

```yaml
- timestamp: 7000
  action: inspekt
  command: "console --level error"
  expect:
    empty: true    # No console errors
```

### Accessibility Checks

Add accessibility testing at key points:

```yaml
- timestamp: 8000
  action: inspekt
  command: "axe --level 2aa"
  expect:
    allowed-violations: 0  # No WCAG 2.1 AA violations (default when omitted)
```

### Generic Output Assertions

For any `inspekt` command, you can assert against its output using these fields:

```yaml
# Check output contains specific text
- timestamp: 9000
  action: inspekt
  command: "outline"
  expect:
    output-contains: "h1"                    # Output must contain "h1"
    message: Page should have an h1 heading

# Check output does NOT contain text
- timestamp: 10000
  action: inspekt
  command: "console --level error"
  expect:
    output-not-contains: "TypeError"         # No TypeErrors in console
    message: No JavaScript errors expected

# Check output matches a regex pattern
- timestamp: 11000
  action: inspekt
  command: "info accessibility"
  expect:
    output-matches: "main.*banner.*navigation"  # Check landmark order
    message: Page should have proper landmark structure
```

These assertions work with **any** inspekt command output:

| Assertion | Description |
|-----------|-------------|
| `output-contains` | Passes if output contains the specified text |
| `output-not-contains` | Passes if output does NOT contain the specified text |
| `output-matches` | Passes if output matches the regex pattern (multiline) |

**Combining assertions** - You can use multiple output assertions together:

```yaml
- action: inspekt
  command: "links --filter external"
  expect:
    output-contains: "https://"              # Has external links
    output-not-contains: "javascript:"       # No javascript: links
    output-matches: "\\d+ external links"    # Matches count pattern
```

### Element State Assertions

Check form field states:

```yaml
- timestamp: 4000
  action: click
  target:
    selector: "#accept-terms"
  expect:
    checked: "#accept-terms"       # Checkbox should be checked
    unchecked: "#decline-terms"    # Other checkbox should be unchecked
    enabled: "#submit-btn"         # Submit button should be enabled
    disabled: "#next-btn"          # Next button should be disabled

- timestamp: 5000
  action: type
  target:
    selector: "#email"
  value: "test@example.com"
  expect:
    value: "#email"
    value_equals: "test@example.com"
    focused: true                  # Input should have focus
```

### Element Count Assertions

Check the number of elements matching a selector:

```yaml
# Verify exactly 5 items in list
- timestamp: 6000
  action: click
  target:
    selector: "#load-more"
  expect:
    count: ".list-item"
    count_equals: 5

# Verify at least 3 but no more than 10 results
- timestamp: 7000
  action: click
  target:
    selector: "#search-btn"
  expect:
    count: ".search-result"
    count_min: 3
    count_max: 10
```

### Wait/Retry for Async Content

For dynamic content that takes time to appear:

```yaml
- timestamp: 6000
  action: click
  target:
    selector: "#submit-btn"
  expect:
    visible: ".success-message"
    hidden: ".loading-spinner"
    wait: 5000                    # Wait up to 5 seconds
    retry: 100                    # Check every 100ms
```

### Conditional Actions

Skip steps based on page state:

```yaml
# Skip cookie banner if already dismissed
- timestamp: 500
  action: click
  target:
    selector: "#accept-cookies"
  skip_if:
    hidden: "#cookie-banner"
```

Wait for conditions before executing:

```yaml
# Wait for form to load before typing
- timestamp: 1000
  action: type
  target:
    selector: "#email"
  value: "user@example.com"
  wait_for:
    visible: "#email"
    timeout: 5000
```

### Preconditions

Add preconditions to verify required elements exist before replay starts:

```yaml
preconditions:
  required:
    - selector: "#login-form"
      description: "Login form must be present"
    - selector: "button[type='submit']"
      description: "Submit button required"
  url_pattern: "https://example.com/login*"
  title_contains: "Login"
```

By default, preconditions warn but don't stop replay. Use `--strict-preconditions` to halt on failure.

See [State Management](state-management.md) for more details.

### Expect Options Reference

Complete list of all `expect` assertion options:

| Option | Type | Description |
|--------|------|-------------|
| **Visibility** | | |
| `visible` | selector | Element should be visible |
| `hidden` | selector | Element should be hidden |
| **Content** | | |
| `text_contains` | string | Page should contain text |
| `url_contains` | string | URL should contain substring |
| **Focus** | | |
| `focused` | boolean | Target element should have focus |
| **Form State** | | |
| `value` | selector | Selector for input to check |
| `value_equals` | string | Expected input value |
| `checked` | selector | Checkbox/radio should be checked |
| `unchecked` | selector | Checkbox/radio should be unchecked |
| `enabled` | selector | Element should be enabled |
| `disabled` | selector | Element should be disabled |
| **Element Counting** | | |
| `count` | selector | Selector to count elements |
| `count_equals` | number | Exact expected count |
| `count_min` | number | Minimum count |
| `count_max` | number | Maximum count |
| **Timing** | | |
| `wait` | ms | Max time to wait for assertion |
| `retry` | ms | Retry interval (default: 100) |
| **Inspekt Commands** | | |
| `empty` | boolean | Console should have no messages |
| `allowed-violations` | number | Max axe violations (default: 0) |
| `output-contains` | string | Command output contains text |
| `output-not-contains` | string | Command output doesn't contain |
| `output-matches` | regex | Command output matches pattern |
| **Metadata** | | |
| `message` | string | Description shown on failure |

---

## Part 4: Replaying Recordings

### Basic Replay

```bash
inspekt replay my-first-recording.yaml
```

Output:

```
Replaying: my-first-recording.yaml
URL: https://example.com
Steps: 8 of 8

  [1] navigate → https://example.com OK
  [2] click → a "More information…" OK
  [3] navigate → https://www.iana.org/help/example-domains OK
  [4] click → #search-input "Search" OK
  [5] type → #search-input (6 chars) OK
  [6] keypress → Enter OK
  [7] navigate → https://www.iana.org/search?q=example OK
  [8] click → .result-item OK

──────────────────────────────────────────────────
✓ All 8 steps passed
  Duration: 5.2s
```

### Replay Options

By default, replay uses **real-time timing** - it matches the original pace of your recording.

```bash
# Real-time replay (default - matches original timing)
inspekt replay recording.yaml

# 2x speed (faster)
inspekt replay recording.yaml --speed 2

# Half speed (for debugging)
inspekt replay recording.yaml --slow

# Instant execution (skip all delays)
inspekt replay recording.yaml --instant

# Preview without executing
inspekt replay recording.yaml --dry-run

# Detailed output
inspekt replay recording.yaml --verbose

# Run only steps 3-6
inspekt replay recording.yaml --start-step 3 --end-step 6

# Disable visual/audio feedback (for CI environments)
inspekt replay recording.yaml --no-feedback

# Disable audio only (for shared workspaces)
inspekt replay recording.yaml --no-audio

# State restoration options
inspekt replay recording.yaml --restore-state        # Restore cookies and storage
inspekt replay recording.yaml --restore-cookies      # Restore only cookies
inspekt replay recording.yaml --restore-storage      # Restore only storage

# Verification options
inspekt replay recording.yaml --verify-checksum      # Check DOM structure
inspekt replay recording.yaml --strict-preconditions # Halt on precondition failure
inspekt replay recording.yaml --strict-checksum      # Halt on checksum mismatch
```

### Visual and Audio Feedback

By default, replay includes visual and audio feedback:

- **Visual indicators** - Pulsing circle shows click targets, typing indicator for text input
- **Audio cues** - Subtle sounds for clicks, typing, navigation, and errors

To disable for CI/CD or headless environments:

```bash
inspekt replay test.yaml --no-feedback      # Disable all
inspekt replay test.yaml --no-audio         # Audio only
inspekt replay test.yaml --no-visual        # Visual only
```

### Handling Failures

Replay continues on failure and reports all issues at the end:

```
Replaying: checkout.yaml
URL: https://shop.example.com
Steps: 12 of 12

  [1] navigate → https://shop.example.com OK
  [2] click → .product "Widget Pro" OK
  [3] click → #add-to-cart "Add to Cart" OK
  [4] click → #cart-icon OK
  [5] click → #checkout "Checkout" FAIL
  [6] type → #email (15 chars) OK
  ...

──────────────────────────────────────────────────
✗ 2 of 12 steps failed
  Passed: 10 | Failed: 2 | Skipped: 0
  Duration: 8.5s

Failures:

  Step 5: click
    Selector: #checkout
    Error: Element not found: #checkout

  Step 9: click
    Selector: #confirm
    Error: Assertion failed
    - Expected element to be visible: .order-confirmation
```

---

## Part 5: Practical Examples

### Example 1: Login Flow Test

**Record the login:**

```bash
inspekt record login-test.yaml
# 1. Navigate to login page
# 2. Enter username
# 3. Enter password
# 4. Click login
# 5. Verify dashboard loads
# Press Ctrl+C
```

**Edit to add assertions:**

```yaml
metadata:
  version: "1.0"
  starting_url: "https://app.example.com/login"
  # ...

steps:
  - timestamp: 0
    action: navigate
    url: "https://app.example.com/login"

  - timestamp: 1000
    action: click
    target:
      selector: "#username"

  - timestamp: 1500
    action: type
    target:
      selector: "#username"
    value: "testuser"

  - timestamp: 2000
    action: keypress
    key: "Tab"

  - timestamp: 2500
    action: type
    target:
      selector: "#password"
    value: "secret123"    # Replace masked password!
    sensitive: true

  - timestamp: 3000
    action: click
    target:
      selector: "#login-btn"
    expect:
      url_contains: "/dashboard"
      visible: ".user-menu"
      hidden: ".login-form"

  # Add accessibility check after login
  - timestamp: 4000
    action: inspekt
    command: "axe --level 2aa"
    expect:
      allowed-violations: 0
```

**Run the test:**

```bash
inspekt replay login-test.yaml
```

### Example 2: Form Validation Test

Test that form validation works correctly:

```yaml
metadata:
  version: "1.0"
  starting_url: "https://example.com/signup"

steps:
  - timestamp: 0
    action: navigate
    url: "https://example.com/signup"

  # Submit empty form
  - timestamp: 1000
    action: click
    target:
      selector: "#submit"
    expect:
      visible: ".error-message"
      text_contains: "Email is required"

  # Enter invalid email
  - timestamp: 2000
    action: type
    target:
      selector: "#email"
    value: "not-an-email"

  - timestamp: 2500
    action: click
    target:
      selector: "#submit"
    expect:
      visible: ".error-message"
      text_contains: "Invalid email"

  # Enter valid email
  - timestamp: 3000
    action: click
    target:
      selector: "#email"

  - timestamp: 3100
    action: keypress
    key: "a"
    modifiers: [ctrl]  # Select all

  - timestamp: 3200
    action: type
    target:
      selector: "#email"
    value: "valid@example.com"

  - timestamp: 3500
    action: click
    target:
      selector: "#submit"
    expect:
      hidden: ".error-message"
      visible: ".success-message"
```

### Example 3: Accessibility Test Suite

Create a comprehensive accessibility audit:

```yaml
# a11y-audit.yaml
metadata:
  version: "1.0"
  starting_url: "https://example.com"

steps:
  # Test homepage
  - timestamp: 0
    action: navigate
    url: "https://example.com"

  - timestamp: 1000
    action: inspekt
    command: "axe --level 2aa"
    expect:
      allowed-violations: 0

  # Check for console errors
  - timestamp: 2000
    action: inspekt
    command: "console --level error"
    expect:
      empty: true

  # Test products page
  - timestamp: 3000
    action: click
    target:
      selector: "a[href='/products']"

  - timestamp: 4000
    action: inspekt
    command: "axe --level 2aa"
    expect:
      allowed-violations: 0

  # Test contact page
  - timestamp: 5000
    action: click
    target:
      selector: "a[href='/contact']"

  - timestamp: 6000
    action: inspekt
    command: "axe --level 2aa"
    expect:
      allowed-violations: 0

  - timestamp: 7000
    action: inspekt
    command: "autocomplete"
    expect:
      allowed-violations: 0
```

Run your accessibility suite:

```bash
inspekt replay a11y-audit.yaml
```

### Example 4: E-commerce Checkout Flow

```yaml
metadata:
  version: "1.0"
  starting_url: "https://shop.example.com"

steps:
  # Browse to product
  - timestamp: 0
    action: navigate
    url: "https://shop.example.com"

  - timestamp: 1000
    action: click
    target:
      selector: ".product-card"
      text: "Awesome Widget"

  # Add to cart
  - timestamp: 2000
    action: click
    target:
      selector: "#add-to-cart"
    expect:
      visible: ".cart-notification"
      text_contains: "Added to cart"

  # Go to cart
  - timestamp: 3000
    action: click
    target:
      selector: "#cart-icon"
    expect:
      url_contains: "/cart"
      visible: ".cart-item"

  # Proceed to checkout
  - timestamp: 4000
    action: click
    target:
      selector: "#checkout-btn"
    expect:
      url_contains: "/checkout"

  # Fill shipping info
  - timestamp: 5000
    action: type
    target:
      selector: "#shipping-name"
    value: "John Doe"

  - timestamp: 5500
    action: type
    target:
      selector: "#shipping-address"
    value: "123 Main St"

  - timestamp: 6000
    action: type
    target:
      selector: "#shipping-city"
    value: "New York"

  # No console errors during checkout
  - timestamp: 7000
    action: inspekt
    command: "console --level error"
    expect:
      empty: true

  # Submit order
  - timestamp: 8000
    action: click
    target:
      selector: "#place-order"
    expect:
      url_contains: "/confirmation"
      visible: ".order-number"
      text_contains: "Thank you"
```

---

## Part 6: Best Practices

### Recording Tips

1. **Start fresh** - Begin from a known state (logged out, empty cart, etc.)

2. **Keep it focused** - One workflow per recording

3. **Use stable selectors** - Prefer IDs and data-testid attributes

4. **Skip hover for tests** - Unless testing hover behavior specifically
   ```bash
   inspekt record --no-hover stable-test.yaml
   ```

5. **Name files descriptively**
   ```
   login-success.yaml
   login-invalid-password.yaml
   checkout-guest-user.yaml
   checkout-returning-customer.yaml
   ```

### Editing Tips

1. **Always add assertions** - A recording without assertions isn't a test

2. **Test the happy path AND error cases**

3. **Add accessibility checks at key interactions**

4. **Handle passwords securely**
   - Replace `••••••••` with actual values (don't commit to git)
   - Or use environment variables in a wrapper script

5. **Remove unnecessary steps** - Delete accidental clicks, redundant navigation

### Replay Tips

1. **Use dry-run first**
   ```bash
   inspekt replay test.yaml --dry-run
   ```

2. **Debug with verbose and slow speed**
   ```bash
   inspekt replay test.yaml --verbose --speed 0.5
   ```

3. **Test specific sections**
   ```bash
   inspekt replay test.yaml --start-step 5 --end-step 10
   ```

4. **Use appropriate speed for CI**
   ```bash
   inspekt replay test.yaml --speed 2 --step-delay 200
   ```

---

## Part 7: CI/CD Integration

### Basic Shell Script

```bash
#!/bin/bash
# run-tests.sh

set -e  # Exit on first failure

echo "Starting Inspekt tests…"

# Ensure server is running
inspekt start

# Wait for server
sleep 2

# Run all test recordings
FAILED=0
for file in tests/*.yaml; do
    echo ""
    echo "Running: $file"
    if inspekt replay "$file" --speed 2; then
        echo "✓ Passed: $file"
    else
        echo "✗ Failed: $file"
        FAILED=1
    fi
done

# Report results
echo ""
if [ $FAILED -eq 0 ]; then
    echo "All tests passed!"
    exit 0
else
    echo "Some tests failed!"
    exit 1
fi
```

### GitHub Actions Example

```yaml
# .github/workflows/e2e-tests.yml
name: E2E Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Inspekt
        run: pip install inspekt

      - name: Setup Chrome
        uses: browser-actions/setup-chrome@v1

      - name: Start Inspekt
        run: |
          inspekt start &
          sleep 3

      - name: Run E2E Tests
        run: |
          for file in tests/e2e/*.yaml; do
            inspekt replay "$file" --speed 2
          done
```

---

## Troubleshooting

### "Element not found"

**Cause:** Selector doesn't match any element

**Solutions:**
1. Check if the page structure changed
2. Update the selector in your YAML
3. Add more fallback selectors
4. Ensure you're on the right page first

### "Cannot replay masked password"

**Cause:** Password was masked during recording

**Solution:** Edit the YAML and replace `••••••••` with the actual password

### "Assertion failed"

**Cause:** Expected condition not met

**Solutions:**
1. Verify the expected behavior is correct
2. Add delay before the assertion (increase `--step-delay`)
3. Check for timing issues with dynamic content

### Recording is flaky

**Solutions:**
1. Use `--no-hover` to skip hover events
2. Add explicit waits with increased `--step-delay`
3. Use stable selectors (IDs, data-testid)
4. Record from a consistent starting state

---

## Summary

You've learned how to:

- ✅ Record browser interactions with `inspekt record`
- ✅ Understand the YAML recording format (v1.1)
- ✅ Capture page state with `--capture-state`
- ✅ Record file uploads (small files embedded, large files stored externally)
- ✅ Add assertions and preconditions for testing
- ✅ Replay recordings with `inspekt replay`
- ✅ Restore state with `--restore-state`
- ✅ Create accessibility test suites
- ✅ Integrate with CI/CD pipelines

## Next Steps

- Read the [inspekt record reference](../commands/record.md)
- Read the [inspekt replay reference](../commands/replay.md)
- Learn about [state management](state-management.md)
- Learn about [accessibility testing](accessibility-testing.md)
- Explore [advanced usage patterns](advanced.md)
