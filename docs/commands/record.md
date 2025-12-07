# inspekt record - Record Browser Interactions

The `inspekt record` command captures user interactions with the browser into a human-readable YAML file. These recordings can be replayed with `inspekt replay` for automation, regression testing, and accessibility testing.

## Quick Start

```bash
# Start recording (auto-generates filename)
inspekt record

# Record to specific file
inspekt record my-flow.yaml

# Record without hover events (faster, cleaner)
inspekt record --no-hover

# Press Ctrl+C to stop and save

# List all recordings
inspekt record list

# Show recording details
inspekt record show login-flow.yaml
```

## Why Use Inspekt Record?

### The Inspekt Advantage

Unlike Playwright Recorder or Puppeteer Recorder, Inspekt works with **your current browser session**:

- **Records YOUR authenticated state** - No need to script login flows
- **Works with YOUR cookies and sessions** - Test real user journeys
- **Captures YOUR navigation history** - Continue from where you are
- **Human-readable YAML output** - Easy to edit and understand
- **Built-in accessibility support** - Add a11y assertions to recordings

**Example workflow:**
```bash
# Log into your app manually
# Navigate to the page you want to test
# Start recording
inspekt record checkout-flow.yaml
# Perform the actions you want to automate
# Press Ctrl+C to save
# Edit the YAML to add assertions
# Replay anytime with: inspekt replay checkout-flow.yaml
```

### What Gets Recorded

| Event Type | Description |
|------------|-------------|
| **Clicks** | Mouse clicks with element selector and coordinates |
| **Typing** | Text input (passwords automatically masked) |
| **Keypresses** | Tab, Enter, Arrow keys, modifier combos |
| **Hovers** | Mouse hover on interactive elements (200ms+ duration) |
| **Navigation** | URL changes including SPA navigation |

## Command Options

```bash
inspekt record [OPTIONS] [OUTPUT]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `OUTPUT` | Output filename (optional). If omitted, auto-generates based on URL and timestamp |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--include-hover / --no-hover` | `--include-hover` | Record hover events on interactive elements |
| `--mask-passwords / --no-mask-passwords` | `--mask-passwords` | Mask password input values |
| `--min-hover-duration INTEGER` | `200` | Minimum hover duration in ms to record |
| `--replay` | `false` | Automatically replay the recording after saving |
| `--no-audio` | `false` | Disable audio feedback during replay |
| `--no-visual` | `false` | Disable visual feedback during replay |
| `--no-feedback` | `false` | Disable both audio and visual feedback during replay |

### Examples

```bash
# Auto-generated filename (saves to ~/.inspekt/recordings/)
inspekt record
# Output: ~/.inspekt/recordings/github_com_login_20251202_103000.yaml

# Custom filename
inspekt record login-test.yaml

# Skip hover events for cleaner recordings
inspekt record --no-hover checkout.yaml

# Include actual password values (not recommended for shared files)
inspekt record --no-mask-passwords admin-flow.yaml

# Only record hovers that last 500ms or more
inspekt record --min-hover-duration 500

# Record and immediately replay to verify (with visual/audio feedback)
inspekt record --replay checkout.yaml

# Record and replay silently (for CI environments)
inspekt record --replay --no-feedback checkout.yaml
```

## Subcommands

### `inspekt record tutorial`

Interactive tutorial that demonstrates all action types with audio and visual feedback.

```bash
inspekt record tutorial           # Show descriptions as text
inspekt record tutorial --speak   # Use text-to-speech announcements
```

The tutorial plays through all supported action types with synthesized audio feedback:
- **Session sounds**: Start/stop recording and playback (3-note sequences)
- **Action sounds**: Click, type, navigate, scroll, etc. (1-2 note sounds)
- **Special sounds**: Plugin (bloop-bloop), Inspekt (beep-beep), Failure (dissonant buzz)

This helps you learn what each action sounds like during replay.

### `inspekt record list`

List all saved recordings with metadata.

```bash
inspekt record list              # List all recordings
inspekt record list --limit 10   # Show last 10
inspekt record list --json       # JSON output
```

**Output:**
```
Recordings (~/.inspekt/recordings/)

NAME                                    DATE         DURATION  STEPS  URL
────────────────────────────────────────────────────────────────────────────
github_com_login_20251202_103000.yaml   Dec 02 2025  45.2s     12     github.com/login
example_com_checkout_20251201.yaml      Dec 01 2025  1m 23s    28     example.com/checkout

Total: 2 recording(s)
```

### `inspekt record show`

Show details of a specific recording.

```bash
inspekt record show login-flow.yaml
```

**Output:**
```
Recording: login-flow.yaml
────────────────────────────────────────────────────────
URL:      https://github.com/login
Created:  2025-12-02 10:30:00
Duration: 45.2s
Steps:    12
Viewport: 1920x1080

Actions:  click: 4, keypress: 2, navigate: 2, type: 4

────────────────────────────────────────────────────────
Steps preview:

[ 1] 00:00  navigate  → https://github.com/login
[ 2] 00:01  click     → #login_field "Username or email address" (input)
[ 3] 00:03  type      → #login_field (8 chars)
...

Replay with: inspekt replay login-flow.yaml
```

### `inspekt record delete`

Delete a recording file.

```bash
inspekt record delete login-flow.yaml           # Prompts for confirmation
inspekt record delete --force old-recording.yaml # Skip confirmation
```

## Recording File Format (YAML)

### File Structure

```yaml
# Inspekt Recording v1.0
# Generated: 2025-12-02T10:30:00+00:00
# Duration: 45.2s
# URL: https://example.com/login

metadata:
  version: "1.0"
  created_at: "2025-12-02T10:30:00+00:00"
  duration_ms: 45200
  starting_url: "https://example.com/login"
  viewport:
    width: 1920
    height: 1080
  zoom: 1.0

steps:
  - timestamp: 0
    action: navigate
    url: "https://example.com/login"

  - timestamp: 1234
    action: click
    target:
      selector: "#username"
      fallback_selectors:
        - "[data-testid='username-input']"
        - "input[name='username']"
      accessible_name: "Username"
      tag: input
    position:
      x: 450
      y: 320

  - timestamp: 2500
    action: type
    target:
      selector: "#username"
      accessible_name: "Username"
    value: "testuser"

  - timestamp: 3500
    action: keypress
    key: "Tab"

  - timestamp: 4000
    action: type
    target:
      selector: "#password"
    value: "••••••••"
    sensitive: true

  - timestamp: 5500
    action: click
    target:
      selector: "button[type='submit']"
      accessible_name: "Log In"
```

### Action Types

#### navigate
Records URL navigation events.

```yaml
- timestamp: 0
  action: navigate
  url: "https://example.com/page"
```

#### click
Records mouse click events with element targeting and position.

```yaml
- timestamp: 1234
  action: click
  target:
    selector: "button.submit"
    fallback_selectors:
      - "[data-testid='submit-btn']"
      - "form > button"
    text: "Submit"
    accessible_name: "Submit form"
    tag: button
  position:
    x: 450
    y: 320
```

#### type
Records text input (typing) into form fields.

```yaml
- timestamp: 2500
  action: type
  target:
    selector: "input#email"
    accessible_name: "Email address"
  value: "user@example.com"
```

For password fields:
```yaml
- timestamp: 3000
  action: type
  target:
    selector: "input#password"
  value: "••••••••"
  sensitive: true
```

#### keypress
Records special key presses (Tab, Enter, arrows, etc.).

```yaml
- timestamp: 3500
  action: keypress
  key: "Tab"
  modifiers: []

# With modifiers
- timestamp: 4000
  action: keypress
  key: "a"
  modifiers:
    - ctrl
```

Supported modifiers: `ctrl`, `meta` (Cmd), `alt`, `shift`

#### hover
Records mouse hover on interactive elements.

```yaml
- timestamp: 5000
  action: hover
  target:
    selector: "nav.menu a.dropdown"
    accessible_name: "Account menu"
```

#### inspekt
Special action for running inspekt commands during replay (added manually).

```yaml
- timestamp: 6000
  action: inspekt
  command: "console --level error"
  expect:
    empty: true
```

### Target Object

Each action that interacts with an element has a `target` object:

```yaml
target:
  selector: "primary CSS selector"
  fallback_selectors:
    - "fallback selector 1"
    - "fallback selector 2"
  text: "visible text content"
  accessible_name: "ARIA accessible name"
  tag: "html tag"
  role: "ARIA role"
```

#### Selector Priority

Selectors are generated in order of reliability:

1. **ID selector** - `#element-id` (most stable)
2. **data-testid** - `[data-testid="..."]` (test-friendly)
3. **aria-label** - `[aria-label="..."]` (accessibility-friendly)
4. **name attribute** - `input[name="..."]` (form-friendly)
5. **CSS path** - `div > form > button:nth-of-type(1)` (fallback)

During replay, if the primary selector fails, fallbacks are tried in order.

## Adding Assertions

After recording, edit the YAML file to add `expect:` fields for assertions:

### Visibility Assertions

```yaml
- timestamp: 5500
  action: click
  target:
    selector: "button[type='submit']"
  expect:
    visible: ".success-message"
```

```yaml
expect:
  visible: ".success-message"    # Element should be visible
  hidden: ".error-message"       # Element should be hidden
```

### URL Assertions

```yaml
expect:
  url_contains: "/dashboard"     # URL should contain string
```

### Text Assertions

```yaml
expect:
  text_contains: "Welcome back"  # Page should contain text
```

### Console Assertions (with inspekt command)

```yaml
- timestamp: 6000
  action: inspekt
  command: "console --level error"
  expect:
    empty: true                  # No console errors
```

### Accessibility Assertions (with inspekt command)

```yaml
- timestamp: 7000
  action: inspekt
  command: "axe --level 2aa"
  expect:
    violations: 0                # No WCAG 2.1 AA violations
```

## Use Cases

### 1. Regression Testing

```bash
# Record a critical user flow
inspekt record checkout-flow.yaml

# Edit to add assertions
# Run before each deployment
inspekt replay checkout-flow.yaml
```

### 2. Accessibility Testing

```bash
# Record user journey
inspekt record user-journey.yaml

# Edit YAML to add axe checks at key points:
# - timestamp: 5000
#   action: inspekt
#   command: "axe --level 2aa"
#   expect:
#     violations: 0

inspekt replay user-journey.yaml
```

### 3. Bug Reproduction

```bash
# Record steps to reproduce a bug
inspekt record bug-repro.yaml

# Share with team
# Anyone can replay: inspekt replay bug-repro.yaml
```

### 4. Onboarding Documentation

```bash
# Record common workflows
inspekt record create-project.yaml

# The YAML serves as documentation
# New team members can see exact steps
```

### 5. Smoke Tests

```bash
# Record critical paths
inspekt record --no-hover login.yaml
inspekt record --no-hover create-account.yaml
inspekt record --no-hover checkout.yaml

# Run all as smoke tests
for f in *.yaml; do inspekt replay "$f"; done
```

## Best Practices

### 1. Use Descriptive Filenames

```bash
# Good
inspekt record login-with-2fa.yaml
inspekt record checkout-guest-user.yaml

# Avoid
inspekt record test1.yaml
inspekt record recording.yaml
```

### 2. Keep Recordings Focused

Record one user flow per file:
- ✅ `login.yaml` - just login
- ✅ `add-to-cart.yaml` - just adding items
- ❌ `everything.yaml` - login + browse + checkout

### 3. Add Assertions at Key Points

```yaml
# After login
- action: click
  target:
    selector: "#login-btn"
  expect:
    url_contains: "/dashboard"
    visible: ".welcome-message"

# After form submission
- action: click
  target:
    selector: "#submit"
  expect:
    visible: ".success"
    hidden: ".error"
```

### 4. Use Inspekt Commands for Deep Checks

```yaml
# Check for console errors
- action: inspekt
  command: "console --level error"
  expect:
    empty: true

# Check accessibility
- action: inspekt
  command: "axe"
  expect:
    violations: 0
```

### 5. Handle Passwords Securely

Passwords are masked by default (`••••••••`). For replay:

**Option 1: Environment variables**
```yaml
- action: type
  target:
    selector: "#password"
  value: "${TEST_PASSWORD}"  # Replace before replay
```

**Option 2: Separate credentials file**
```bash
# Don't commit passwords to version control
# Use a local .env or secrets manager
```

### 6. Skip Hover for Cleaner Tests

```bash
# Hovers can make tests flaky
inspekt record --no-hover stable-test.yaml
```

## Limitations

### Dynamic Content
- Elements may not exist at replay time
- Use stable selectors (IDs, data-testid) when possible
- Fallback selectors help with dynamic content

### iFrames
- Same-origin iframes work
- Cross-origin iframes cannot be recorded/replayed

### Shadow DOM
- Standard selectors don't pierce Shadow DOM
- Web components may need special handling

### Timing
- Recording captures timestamps but replay uses fixed delays
- Use `--step-delay` in replay for timing-sensitive flows

## Related Commands

- `inspekt replay` - Replay recorded interactions
- `inspekt watch all` - Watch interactions in real-time (without recording)
- `inspekt control` - Remote control browser from terminal
- `inspekt axe` - Run accessibility audit
- `inspekt console` - Check console messages

## File Locations

**Default recordings directory:**
```
~/.inspekt/recordings/
```

**Auto-generated filenames:**
```
{domain}_{path}_{timestamp}.yaml
```

Example:
```
github_com_login_20251202_103000.yaml
```
