# inspekt replay - Replay Recorded Interactions

The `inspekt replay` command executes recorded browser interactions from a YAML file. It's designed for automation, regression testing, and accessibility testing workflows.

## Quick Start

```bash
# Replay most recent recording (auto-finds recording_*.yaml)
inspekt replay

# Replay a specific recording
inspekt replay login-flow.yaml

# Interactive mode - step through manually
inspekt replay login-flow.yaml --interactive

# Preview steps without executing (dry run)
inspekt replay login-flow.yaml --dry-run

# Replay at 2x speed
inspekt replay login-flow.yaml --speed 2

# Quick replay - half speed
inspekt replay login-flow.yaml --slow

# Instant replay - no delays
inspekt replay login-flow.yaml --instant

# Skip all hover actions
inspekt replay login-flow.yaml --skip-hover

# Pause on failures for debugging
inspekt replay login-flow.yaml --pause-on-fail --verbose
```

## Why Use Inspekt Replay?

### Key Features

- **Continue on failure** - Collects all failures and reports at the end
- **Fallback selectors** - Tries alternative selectors if primary fails
- **Auto-scroll** - Automatically scrolls elements into view
- **Assertion support** - Validates expected outcomes
- **Speed control** - Adjust playback speed
- **Partial replay** - Run specific steps only

### Testing Workflow

```bash
# 1. Record a user flow
inspekt record checkout-flow.yaml

# 2. Edit YAML to add assertions
# (see inspekt record documentation)

# 3. Replay for testing
inspekt replay checkout-flow.yaml

# 4. Check results
# ✓ All 12 steps passed
# or
# ✗ 2 of 12 steps failed
```

## Command Options

```bash
inspekt replay [OPTIONS] [RECORDING_FILE]
```

### Arguments

| Argument | Description |
|----------|-------------|
| `RECORDING_FILE` | Path to the YAML recording file. If omitted, automatically uses the most recently modified `recording_*.yaml` file in the current directory. |

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `-i, --interactive` | `false` | Step through replay manually (Enter=next, Space=skip, Escape=cancel) |
| `--speed FLOAT` | `1.0` | Playback speed multiplier |
| `--slow` | `false` | Half speed (0.5x) - same as `--speed 0.5` |
| `--very-slow` | `false` | Quarter speed (0.25x) - same as `--speed 0.25` |
| `--instant` | `false` | No delays between steps - fastest playback |
| `--step-delay INTEGER` | `0` | Delay between steps in milliseconds |
| `--dry-run` | `false` | Show steps without executing |
| `--start-step INTEGER` | `1` | Start from step number (1-indexed) |
| `--end-step INTEGER` | `none` | End at step number (1-indexed, inclusive) |
| `--skip-hover` | `false` | Skip all hover actions |
| `--skip TYPE` | `none` | Skip specific action types (can repeat: `--skip hover --skip keypress`) |
| `--pause-on-fail` | `false` | Pause and wait for Enter after each failure |
| `-v, --verbose` | `false` | Show detailed output for each step |
| `--no-visual` | `false` | Disable visual indicators (enabled by default) |
| `--no-audio` | `false` | Disable audio cues (enabled by default) |
| `--no-feedback` | `false` | Disable both visual and audio feedback |
| `--lock` | `false` | Lock input during replay (hide cursor, ignore input) |
| `--restore-state` | `false` | Restore all captured state (cookies, storage) |
| `--restore-cookies` | `false` | Restore cookies from recording |
| `--restore-storage` | `false` | Restore localStorage/sessionStorage |
| `--verify-checksum` | `false` | Verify DOM structure matches recording |
| `--strict-preconditions` | `false` | Halt if preconditions fail (default: warn) |
| `--strict-checksum` | `false` | Halt if checksum mismatches (default: warn) |

### Examples

```bash
# Auto-find and replay most recent recording
inspekt replay

# Basic replay of specific file
inspekt replay login.yaml

# Interactive mode - step through manually
inspekt replay login.yaml -i
inspekt replay login.yaml --interactive

# Speed presets
inspekt replay login.yaml --slow        # 0.5x speed
inspekt replay login.yaml --very-slow   # 0.25x speed
inspekt replay login.yaml --instant     # No delays

# Fast replay (2x speed)
inspekt replay login.yaml --speed 2

# Custom delay between steps
inspekt replay login.yaml --step-delay 1000

# Skip specific actions
inspekt replay login.yaml --skip-hover              # Skip hovers
inspekt replay login.yaml --skip hover --skip keypress  # Skip multiple

# Debugging
inspekt replay login.yaml --pause-on-fail --verbose  # Pause on failures
inspekt replay login.yaml --dry-run                  # Preview only

# Run steps 5-10 only
inspekt replay login.yaml --start-step 5 --end-step 10

# Verbose output
inspekt replay login.yaml --verbose

# Disable feedback for CI/headless environments
inspekt replay login.yaml --no-feedback

# Disable only audio (keep visual indicators)
inspekt replay login.yaml --no-audio

# Restore captured page state (cookies, storage)
inspekt replay login.yaml --restore-state

# Restore only cookies
inspekt replay login.yaml --restore-cookies

# Verify DOM checksum (warn on mismatch)
inspekt replay login.yaml --verify-checksum --verbose

# Strict mode - halt on precondition or checksum failure
inspekt replay login.yaml --strict-preconditions --strict-checksum
```

## Real-Time Playback

By default, replay uses **real-time timing** based on the original recording timestamps. This means the replay matches exactly how you performed the actions.

### Speed Control

| Option | Effect |
|--------|--------|
| (default) | Real-time playback (1x speed) |
| `--speed 2` | Twice as fast |
| `--speed 0.5` | Half speed |
| `--slow` | Half speed (0.5x) |
| `--very-slow` | Quarter speed (0.25x) |
| `--instant` | Skip all delays (fastest) |

```bash
# Real-time replay (matches original timing)
inspekt replay recording.yaml

# 2x speed for faster testing
inspekt replay recording.yaml --speed 2

# Slow motion for debugging
inspekt replay recording.yaml --slow

# Skip all timing (instant execution)
inspekt replay recording.yaml --instant
```

**Note:** Maximum delay between steps is capped at 30 seconds to avoid excessively long waits during playback.

## Visual and Audio Feedback

By default, replay includes **visual and audio feedback** to help you follow along:

### Visual Feedback
- **Target indicator** - A pulsing circle shows where clicks will occur
- **Typing indicator** - Shows text being typed into fields
- **Navigation indicator** - Visual cue when pages change

### Audio Feedback
- **Click sounds** - Subtle audio cue for each click
- **Typing sounds** - Keyboard-like sounds while typing
- **Navigation sounds** - Audio cue when navigating to new pages
- **Error sounds** - Distinct sound when a step fails

### Disabling Feedback

For CI/CD pipelines or headless environments, you can disable feedback:

```bash
# Disable all feedback (silent mode)
inspekt replay test.yaml --no-feedback

# Disable audio only (useful for shared workspaces)
inspekt replay test.yaml --no-audio

# Disable visual only (keep audio cues)
inspekt replay test.yaml --no-visual
```

## Interactive Mode

Interactive mode (`-i` or `--interactive`) lets you step through a replay manually, controlling each action from your browser.

### How It Works

1. An overlay appears in the bottom-left corner of the browser
2. The overlay shows the current step and what action will be performed
3. You control execution with keyboard keys
4. The CLI shows results as each step completes

### Keyboard Controls

| Key | Action |
|-----|--------|
| **Enter** | Execute the next step |
| **Space** | Skip the next step |
| **Escape** | Cancel the replay |

### Browser Overlay

The overlay displays:
- Step number and total (e.g., "Step 3 of 15")
- Action type with icon (click, type, navigate, etc.)
- Target description (element selector, accessible name)
- Previous step result (dimmed, for context)
- Key hints at the bottom

### Example Usage

```bash
# Start interactive replay
inspekt replay checkout-flow.yaml -i

# Output:
# Replaying: checkout-flow.yaml
# Steps: 15 of 15
#
# Interactive mode: Press Enter to execute, Space to skip, Escape to cancel
#
# 001  00:00  navigate  → https://example.com/shop OK
# 002  00:01  click     → .add-to-cart "Add to Cart" OK
# 003  00:02  click     → #checkout "Checkout" SKIP
# ...
```

### Use Cases

**Debugging a failing step:**
```bash
# Step through to see exactly what happens
inspekt replay failing-test.yaml -i
```

**Learning a recorded flow:**
```bash
# Watch each step execute one at a time
inspekt replay complex-workflow.yaml --interactive
```

**Selective execution:**
```bash
# Skip steps you don't need, execute others
inspekt replay full-flow.yaml -i
```

**Verifying a new recording:**
```bash
# Record and step through immediately
inspekt record --replay -i checkout.yaml
```

### Interactive Mode + Record

You can combine interactive mode with the record command's `--replay` flag:

```bash
# Record a session, then step through the replay to verify
inspekt record --replay --interactive my-flow.yaml
inspekt record --replay -i my-flow.yaml
```

This is useful for verifying that each recorded action replays correctly.

## Output Format

### Normal Output

```
Replaying: login-flow.yaml (last modified)
Recorded: December 12, 2025 at 14:30
URL: https://example.com/login
Viewport: 1280x720
Steps: 12 of 12

  [1] navigate → https://example.com/login OK
  [2] click → #username "Username" OK
  [3] type → #username (8 chars) OK
  [4] keypress → Tab OK
  [5] type → #password (password) OK
  [6] click → button[type='submit'] "Log In" OK
  [7] navigate → https://example.com/dashboard OK

──────────────────────────────────────────────────
✓ All 7 steps passed
  Duration: 4.2s
```

### Failure Output

```
Replaying: checkout.yaml
URL: https://example.com/shop
Steps: 15 of 15

  [1] navigate → https://example.com/shop OK
  [2] click → .product-card "Widget" OK
  [3] click → #add-to-cart "Add to Cart" OK
  [4] click → #checkout "Checkout" FAIL
  ...

──────────────────────────────────────────────────
✗ 2 of 15 steps failed
  Passed: 13 | Failed: 2 | Skipped: 0
  Duration: 8.5s

Failures:

  Step 4: click
    Selector: #checkout
    Error: Element not found: #checkout

  Step 10: click
    Selector: #confirm-order
    Error: Assertion failed
    - Expected element to be visible: .order-confirmation
```

### Verbose Output

With `--verbose`, shows additional details:

```
  [3] type → #username (8 chars) OK
      (used fallback: [data-testid='username-input'])
```

### Dry Run Output

```
Replaying: login-flow.yaml
URL: https://example.com/login
Steps: 7 of 7

[DRY RUN - not executing]

  [1] navigate → https://example.com/login
  [2] click → #username "Username"
  [3] type → #username (8 chars)
  [4] keypress → Tab
  [5] type → #password (password)
  [6] click → button[type='submit'] "Log In"
  [7] navigate → https://example.com/dashboard
      expect: {'url_contains': '/dashboard'}

Dry run complete. 7 steps would be executed.
```

## How Replay Works

### Step Execution

1. **Read step** from YAML file
2. **Find element** using primary selector, then fallbacks
3. **Scroll** element into view
4. **Execute action** (click, type, keypress, hover)
5. **Run assertions** if `expect:` is defined
6. **Wait** for step delay before next step
7. **Continue** to next step (even if failed)
8. **Report** all failures at the end

### Selector Resolution

Replay tries selectors in order until one works:

```yaml
target:
  selector: "#submit-btn"           # Try first
  fallback_selectors:
    - "[data-testid='submit']"      # Try second
    - "form > button"               # Try third
    - "button:nth-of-type(1)"       # Try last
```

If all selectors fail, also tries:
- **Accessible name matching** - Find by ARIA label
- **Text content matching** - Find by visible text

### Auto-Scroll

Before interacting with an element, replay automatically scrolls it into view:

```javascript
element.scrollIntoView({
  behavior: 'instant',
  block: 'center',
  inline: 'center'
});
```

This means **scroll events are not needed in recordings**.

### Step Execution Mode

Control how individual steps are executed using the `mode` property:

| Mode | Behavior |
|------|----------|
| `continue` | Execute normally (default) |
| `skip` | Skip step unconditionally |
| `pause` | Wait for Enter key before executing |

```yaml
# Skip a step unconditionally
- action: hover
  mode: skip
  target:
    selector: "#cookie-banner button"

# Pause before an important step
- action: click
  mode: pause
  target:
    selector: "#submit-order"
    accessible_name: "Place Order"
```

When `mode: pause` is used, replay displays the step and waits:

```
0004   00:03    pause      "Place Order" (button)

⏸ Paused. Press Enter to continue…
```

After pressing Enter, the step executes normally.

!!! tip "When to use mode"
    - Use `mode: skip` to permanently disable steps without deleting them
    - Use `mode: pause` for steps that need manual verification before proceeding
    - Use `skip_if` for conditional skipping based on page state

### Conditional Execution

Before executing a step, replay checks:

1. **skip_if** - If condition is met, skip the step entirely
2. **wait_for** - Wait for condition to be met before executing

```yaml
- action: click
  target:
    selector: "#accept-cookies"
  skip_if:
    hidden: "#cookie-banner"     # Skip if already dismissed
```

### Assertion Handling

Assertions are checked after each step. Failures are collected but don't stop execution:

```yaml
- action: click
  target:
    selector: "#login-btn"
  expect:
    visible: ".dashboard"        # Checked after click
    url_contains: "/dashboard"   # Checked after click
    wait: 3000                   # Wait up to 3s for assertions to pass
```

### Inspekt Commands

Steps with `action: inspekt` run inspekt CLI commands:

```yaml
- action: inspekt
  command: "console --level error"
  expect:
    empty: true
```

This executes: `inspekt console --level error`

## Assertion Reference

### Visibility

```yaml
expect:
  visible: ".success-message"    # Element must be visible
  hidden: ".loading-spinner"     # Element must be hidden or not exist
```

### URL

```yaml
expect:
  url_contains: "/dashboard"     # Current URL must contain string
```

### Text Content

```yaml
expect:
  text_contains: "Welcome"       # Page body must contain text
```

### Focus

```yaml
expect:
  focused: true                  # Target element should have focus after action
```

### Element State

```yaml
expect:
  # Check input value
  value: "#email-input"
  value_equals: "test@example.com"

  # Checkbox/radio state
  checked: "#remember-me"        # Element must be checked
  unchecked: "#opt-out"          # Element must not be checked

  # Enabled/disabled state
  disabled: "#submit-btn"        # Element must be disabled
  enabled: "#cancel-btn"         # Element must be enabled
```

### Element Count

```yaml
expect:
  count: ".list-item"            # Selector to count
  count_equals: 5                # Exact count
  # OR
  count_min: 1                   # At least this many
  count_max: 10                  # At most this many
```

### Wait/Retry

```yaml
expect:
  visible: ".async-content"
  wait: 5000                     # Wait up to 5 seconds for assertion to pass
  retry: 100                     # Check every 100ms (default)
```

Use `wait` for assertions that depend on async operations (AJAX, animations, etc.).

### Console (with inspekt command)

```yaml
- action: inspekt
  command: "console --level error"
  expect:
    empty: true                  # No error messages
```

### Accessibility (with inspekt command)

```yaml
- action: inspekt
  command: "axe --level 2aa"
  expect:
    violations: 0                # No WCAG 2.1 AA violations
```

## Conditional Actions

### skip_if - Skip Step Conditionally

Skip a step if a condition is met. Useful for handling optional UI elements:

```yaml
- action: click
  target:
    selector: "#accept-cookies"
  skip_if:
    hidden: "#cookie-banner"     # Skip if banner already dismissed
```

```yaml
- action: type
  target:
    selector: "#promo-code"
  value: "DISCOUNT20"
  skip_if:
    visible: ".promo-applied"    # Skip if already applied
```

### wait_for - Wait Before Executing

Wait for a condition before executing the step. Useful for dynamic content:

```yaml
- action: click
  target:
    selector: "#dynamic-button"
  wait_for:
    visible: "#dynamic-button"   # Wait for button to appear
    timeout: 5000                # Wait up to 5 seconds
```

```yaml
- action: type
  target:
    selector: "#search-input"
  value: "test query"
  wait_for:
    hidden: ".loading-overlay"   # Wait for loading to finish
    timeout: 10000
```

### Condition Types for skip_if and wait_for

| Condition | Description |
|-----------|-------------|
| `visible: selector` | Element is visible |
| `hidden: selector` | Element is hidden or doesn't exist |
| `text_contains: text` | Page contains text |
| `url_contains: text` | URL contains text |
| `checked: selector` | Checkbox/radio is checked |
| `unchecked: selector` | Checkbox/radio is not checked |
| `value: selector` + `value_equals: value` | Input has specific value |
| `timeout: ms` | Max wait time (for wait_for only) |

## Use Cases

### 1. Regression Testing

```bash
# Run before each deployment
inspekt replay checkout-flow.yaml

# Exit code 0 = all passed
# Exit code 1 = failures
echo $?
```

### 2. CI/CD Integration

```bash
#!/bin/bash
# test.sh

# Start browser and inspekt
inspekt start

# Run all test recordings
FAILED=0
for file in tests/*.yaml; do
    echo "Running: $file"
    if ! inspekt replay "$file"; then
        FAILED=1
    fi
done

exit $FAILED
```

### 3. Smoke Testing

```bash
# Quick check of critical paths
inspekt replay login.yaml --speed 2
inspekt replay checkout.yaml --speed 2
inspekt replay signup.yaml --speed 2
```

### 4. Debugging Failures

```bash
# Run slowly to observe
inspekt replay failing-test.yaml --speed 0.5 --verbose

# Run specific steps
inspekt replay failing-test.yaml --start-step 5 --end-step 8 --verbose
```

### 5. Accessibility Audits

```yaml
# a11y-audit.yaml
steps:
  - action: navigate
    url: "https://example.com"
  - action: inspekt
    command: "axe --level 2aa"
    expect:
      violations: 0
  - action: click
    target:
      selector: "a.products"
  - action: inspekt
    command: "axe --level 2aa"
    expect:
      violations: 0
```

```bash
inspekt replay a11y-audit.yaml
```

### 6. Dynamic Content Testing

Using `wait_for` and `skip_if` for handling dynamic pages:

```yaml
# dynamic-form.yaml
metadata:
  version: '1.0'
  starting_url: https://example.com/form

steps:
  # Dismiss cookie banner if present
  - action: click
    target:
      selector: "#accept-cookies"
    skip_if:
      hidden: "#cookie-banner"

  # Wait for form to load dynamically
  - action: type
    target:
      selector: "#email"
    value: "test@example.com"
    wait_for:
      visible: "#email"
      timeout: 5000

  # Fill password field
  - action: type
    target:
      selector: "#password"
    value: "securepass123"

  # Check the terms checkbox
  - action: click
    target:
      selector: "#accept-terms"
    expect:
      checked: "#accept-terms"

  # Submit and verify
  - action: click
    target:
      selector: "#submit-btn"
    expect:
      visible: ".success-message"
      hidden: ".error-message"
      wait: 3000

  # Verify form values were saved
  - action: navigate
    url: "https://example.com/profile"
    expect:
      value: "#email-display"
      value_equals: "test@example.com"

  # Check for console errors
  - action: inspekt
    command: "console --level error"
    expect:
      empty: true
```

### 7. Performance Benchmarking

```bash
# Time the replay
time inspekt replay checkout.yaml --step-delay 100

# Multiple runs
for i in {1..5}; do
    time inspekt replay checkout.yaml --step-delay 100
done
```

## Error Handling

### Element Not Found

**Error:**
```
Error: Element not found: #checkout
```

**Solutions:**
1. Check if selector is still valid
2. Add fallback selectors
3. Verify page state (logged in, right page, etc.)

### Masked Password

**Error:**
```
Error: Cannot replay masked password. Edit the recording to provide the actual value.
```

**Solution:**
Edit the YAML to replace `••••••••` with actual password (or use environment variable).

### Assertion Failed

**Error:**
```
Error: Assertion failed
- Expected element to be visible: .success-message
```

**Solutions:**
1. Verify the expected behavior is correct
2. Add wait/delay before assertion
3. Check for timing issues

### Timeout

**Error:**
```
Error: Execution timeout
```

**Solutions:**
1. Page may be slow - increase timeout
2. Element may be in iframe
3. Check network conditions

## Best Practices

### 1. Start Fresh

```bash
# Navigate to starting URL first
inspekt open https://example.com
inspekt replay flow.yaml
```

### 2. Use Appropriate Speed

```bash
# Fast for CI
inspekt replay test.yaml --speed 2 --step-delay 200

# Slow for debugging
inspekt replay test.yaml --speed 0.5 --step-delay 1000
```

### 3. Add Meaningful Assertions

```yaml
# Good: Verify actual outcomes
expect:
  visible: ".order-confirmation"
  url_contains: "/order-complete"

# Avoid: Too generic
expect:
  visible: "body"
```

### 4. Handle Dynamic Content

```yaml
# Use stable selectors
target:
  selector: "[data-testid='submit-btn']"
  fallback_selectors:
    - "#submit"
    - "form button[type='submit']"
```

### 5. Check Exit Codes

```bash
inspekt replay test.yaml
if [ $? -eq 0 ]; then
    echo "Tests passed!"
else
    echo "Tests failed!"
    exit 1
fi
```

## Limitations

### No Variables
Values are static. For dynamic data, edit YAML before replay or use templates.

### No Loops
Recordings are linear - no loops or iteration. Use separate recordings for different flows, or use scripting to run replays multiple times.

### Password Handling
Masked passwords (`••••••••`) cannot be replayed. Must edit YAML with actual values.

### Skip Output
When using `--skip` options, skipped steps show "SKIP" in cyan output:
```
  [5] 00:00:03  hover     → nav.menu "Account" SKIP
```

## Related Commands

- `inspekt record` - Create recordings
- `inspekt axe` - Run accessibility audit
- `inspekt console` - Check console messages
- `inspekt screenshot` - Capture page state

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All steps passed |
| `1` | One or more steps failed |
| `130` | Replay cancelled by user (Escape in interactive mode) |
