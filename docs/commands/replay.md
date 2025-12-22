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

## Preflight Validation

Before replay begins, Inspekt automatically validates the recording file to catch issues early. This includes:

- **YAML syntax** - Checks for parsing errors, tabs, encoding issues
- **Required fields** - Verifies each step has required action type and target
- **File references** - Confirms external files (for uploads) exist
- **Timestamp order** - Warns if steps have out-of-order timestamps
- **Time gaps** - Warns about suspiciously long pauses between steps

### Validation Output

If errors are found, replay is blocked:

```
✗ Error: Step 5: external file not found: uploads/photo.jpg
  💡 Expected: /path/to/recording_files/photo.jpg
     Re-record the upload or restore the file.

Found 1 error(s)
```

If only warnings are found, you're prompted to continue:

```
⚠ Warning: Steps 5-6 have a 45 second gap
  💡 Long pauses may indicate missed interactions during recording.

✓ recording.yaml is valid with 1 warning(s)
Continue with replay? [Y/n]
```

### Skipping Validation

For speed or trusted files, skip validation:

```bash
# Skip via command line flag
inspekt replay recording.yaml --skip-validation

# Or disable globally in config.json
{
  "replay": {
    "validate": false
  }
}
```

### Standalone Validation

Validate without replaying using `inspekt validate`:

```bash
inspekt validate                    # Validate most recent recording
inspekt validate my-recording.yaml  # Validate specific file
inspekt validate --strict           # Treat warnings as errors
inspekt validate --json             # JSON output for CI/tooling
```

See [inspekt validate](validate.md) for full documentation.

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
| `--skip-validation` | `false` | Skip preflight validation checks |
| `--video [PATH]` | `none` | Record replay to video file (MP4/WebM). Use `--video` for auto-naming. |
| `--fps INTEGER` | `10` | Video frame rate (5-30), also configurable in config.json |
| `--open` | `false` | Open video file in default application after creation |
| `--reveal` | `false` | Reveal video file in file explorer after creation |
| `--match-viewport` | `false` | Resize browser to match recorded viewport dimensions |
| `--match-zoom-level` | `false` | Set browser zoom to match recorded zoom level |
| `--faithful` | `false` | Use captured focus styles for pixel-perfect keyboard navigation (if available) |

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

# Video recording
inspekt replay login.yaml --video              # Auto-name: login_replay.mp4
inspekt replay login.yaml --video=journey.mp4  # Custom filename
inspekt replay login.yaml --video=demo.webm    # WebM format
inspekt replay login.yaml --video --fps=15     # Custom frame rate
inspekt replay login.yaml --video --open       # Open video after encoding

# Viewport and zoom matching
inspekt replay responsive-test.yaml --match-viewport      # Match recorded viewport
inspekt replay visual-test.yaml --match-zoom-level        # Match recorded zoom
inspekt replay pixel-perfect.yaml --match-viewport --match-zoom-level  # Match both
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

## Viewport and Zoom Matching

When replaying a recording, your browser's current viewport size and zoom level may differ from when the recording was made. This can cause:

- **Click misses** - Elements may be in different positions or off-screen
- **Layout differences** - Responsive designs may show different content
- **Visual regressions** - Screenshots or visual comparisons may fail
- **Scroll issues** - Elements may need different scroll positions

### Warning at Replay Start

If your browser's viewport or zoom differs from the recording, Inspekt shows a warning:

```
⚠ Your browser's current viewport and zoom level are different from the recording.
  This might be intentional. For a faithful replay, use:
    inspekt replay --match-viewport  (recorded: 1920×1080, current: 1440×900)
    inspekt replay --match-zoom-level  (recorded: 100%, current: 125%)
```

This warning is informational - replay continues unless you use the matching flags.

### When to Use Viewport/Zoom Matching

| Scenario | Recommendation |
|----------|----------------|
| **Pixel-perfect visual testing** | Use both `--match-viewport` and `--match-zoom-level` |
| **Responsive design testing** | Use `--match-viewport` to test at specific breakpoints |
| **Accessibility zoom testing** | Record at high zoom, replay with `--match-zoom-level` |
| **CI/CD pipelines** | Always use matching flags for consistent results |
| **Manual debugging** | Usually not needed - warning can be ignored |
| **Cross-device testing** | Don't use matching - test at current device size |

### Recording with Viewport/Zoom Requirements

When creating recordings that depend on specific viewport or zoom settings, mark them during recording:

```bash
# Mark viewport as important (e.g., testing responsive breakpoints)
inspekt record --match-viewport mobile-nav-test.yaml

# Mark zoom level as important (e.g., accessibility testing at 200%)
inspekt record --match-zoom-level high-zoom-test.yaml

# Mark both as requirements
inspekt record --match-viewport --match-zoom-level regression-test.yaml
```

When these flags are used during recording, the YAML file stores the requirements:

```yaml
state:
  viewport:
    width: 1920
    height: 1080
  browser_zoom_level: 1.0
  require_viewport_match: true   # From --match-viewport
  require_zoom_match: false      # From --match-zoom-level
```

### Replay with Matching

```bash
# Resize browser to match recorded viewport (1920×1080)
inspekt replay responsive-test.yaml --match-viewport

# Set zoom to match recording (e.g., 125%)
inspekt replay zoom-test.yaml --match-zoom-level

# Match both viewport and zoom for pixel-perfect replay
inspekt replay visual-regression.yaml --match-viewport --match-zoom-level
```

### How Viewport Matching Works

Replay uses cached viewport offsets for fast, reliable resizing:

1. **Check cached offsets**: Inspekt looks for previously calibrated offsets in config.json
2. **If cached**: Apply offsets and resize the window instantly
3. **If not cached or stale**: Run a calibration loop to determine correct offsets
4. **macOS**: Uses AppleScript to resize the browser window (most reliable)
5. **Other platforms**: Falls back to JavaScript `window.resizeTo()` (may be blocked by browser)
6. **If resize fails**: Shows a warning and suggests manual resizing

This means the first replay with `--match-viewport` may take a moment to calibrate, but subsequent replays resize instantly.

### How Zoom Matching Works

Uses the Chrome extension API (`chrome.tabs.setZoom()`) to set the exact zoom level. This works reliably across all platforms where the Inspekt extension is installed.

### Practical Examples

#### Testing a Mobile Navigation Menu

```bash
# Record at mobile viewport size
# 1. Manually resize browser to 375×667 (iPhone SE)
# 2. Record the interaction
inspekt record --match-viewport mobile-menu.yaml

# Replay at the same size (auto-resizes browser)
inspekt replay mobile-menu.yaml --match-viewport
```

#### Accessibility Testing at High Zoom

```bash
# Record at 200% zoom for accessibility testing
# 1. Set browser zoom to 200% (Ctrl/Cmd + Plus)
# 2. Record the interaction
inspekt record --match-zoom-level high-zoom-test.yaml

# Replay at 200% zoom (auto-sets zoom level)
inspekt replay high-zoom-test.yaml --match-zoom-level
```

#### Visual Regression Testing in CI

```bash
# Record the golden baseline
inspekt record --match-viewport --match-zoom-level baseline.yaml

# In CI, replay with exact matching
inspekt replay baseline.yaml --match-viewport --match-zoom-level --video
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

## Video Recording

Record your replay sessions as video files (MP4 or WebM) for documentation, bug reports, or sharing with your team.

### Prerequisites

**ffmpeg is required** for video recording. If it's not installed, Inspekt will offer to install it automatically:

```
ffmpeg not found. Install with: brew install ffmpeg? [Y/n]
```

Platform-specific installation:
- **macOS**: `brew install ffmpeg`
- **Ubuntu/Debian**: `sudo apt install ffmpeg`
- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### Basic Usage

```bash
# Record to auto-named file (login-flow_replay.mp4)
inspekt replay login-flow.yaml --video

# Record to specific filename
inspekt replay login-flow.yaml --video=journey.mp4

# Record as WebM (VP9 codec)
inspekt replay login-flow.yaml --video=demo.webm
```

### Frame Rate

The default frame rate is 10 FPS, which provides a good balance between file size and smoothness. You can adjust it:

```bash
# Higher frame rate for smoother video
inspekt replay login-flow.yaml --video --fps=15

# Lower frame rate for smaller files
inspekt replay login-flow.yaml --video --fps=5
```

Valid range: 5-30 FPS.

### Configuration

Set default video settings in `config.json`:

```json
{
  "video": {
    "fps": 10,
    "quality": 80,
    "format": "mp4"
  }
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `fps` | `10` | Frame rate (5-30) |
| `quality` | `80` | JPEG quality for frames (50-100) |
| `format` | `mp4` | Default output format (`mp4` or `webm`) |

CLI options (`--fps`) override config file settings.

### Output

After encoding completes, Inspekt shows the video details:

```
✓ Video saved: /path/to/journey.mp4
  2.4 MB • 45.0s • 450 frames @ 10 FPS
```

The file path is **clickable** in terminals that support OSC 8 hyperlinks (iTerm2, Windows Terminal, modern Linux terminals).

### Video Dimensions

The video dimensions **exactly match your browser's viewport size** at the time of recording. This ensures pixel-perfect output for visual testing and documentation.

For example:
- Viewport 1920×1080 → Video 1920×1080
- Viewport 1000×500 → Video 1000×500
- Viewport 375×667 (mobile) → Video 375×667

**Tip:** Use `--match-viewport` to ensure consistent video dimensions across different machines:

```bash
# Record at exact viewport dimensions stored in the YAML
inspekt replay responsive-test.yaml --match-viewport --video
```

This is especially useful for:
- **Visual regression testing** - Compare videos frame-by-frame
- **Documentation** - Consistent dimensions across team members
- **Responsive testing** - Record at specific breakpoints (mobile, tablet, desktop)

### Visual Overlay

Video recordings include Inspekt's visual feedback overlay:

- **Target indicator** - Pulsing circle showing click targets
- **Typing indicator** - Shows text being typed
- **Step progress** - Current step number and action

This helps viewers understand what actions are being performed.

### Best Practices

**For documentation:**
```bash
# Slow replay with video for clear demonstration
inspekt replay tutorial.yaml --slow --video=tutorial.mp4
```

**For bug reports:**
```bash
# Record the failing replay
inspekt replay failing-test.yaml --video=bug-report.mp4
```

**For CI/CD artifacts:**
```bash
# Record test runs for review
inspekt replay smoke-test.yaml --video=smoke-test-$(date +%Y%m%d).mp4
```

### Limitations

- Video recording uses Chrome DevTools Protocol, which requires DevTools-compatible browsers
- Very long recordings may use significant disk space (frames are cached before encoding)
- The visual overlay is always included in the video (cannot be disabled separately)

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
