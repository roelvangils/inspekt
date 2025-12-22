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

# After adding assertions, tidy up the file
inspekt record tidy my-flow.yaml
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
| **Downloads** | File downloads with MIME type, size, and content |
| **Uploads** | File uploads with content stored externally |

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
| `--open` | `false` | Open the recording in your default application after saving |
| `--reveal` | `false` | Reveal the recording in file explorer after saving |
| `-i, --interactive` | `false` | Step through replay manually (requires `--replay`) |
| `--no-audio` | `false` | Disable audio feedback during replay |
| `--no-visual` | `false` | Disable visual feedback during replay |
| `--no-feedback` | `false` | Disable both audio and visual feedback during replay |
| `--capture-state` | `false` | Capture cookies, localStorage, and scroll position |
| `--storage-keys KEYS` | `none` | Comma-separated localStorage/sessionStorage keys to capture |
| `--checksum` | `false` | Generate DOM structure checksum for verification |
| `--match-viewport` | `false` | Mark viewport size as a requirement for faithful replay |
| `--match-zoom-level` | `false` | Mark zoom level as a requirement for faithful replay |
| `--viewport WIDTHxHEIGHT` | `none` | Resize browser to specific viewport before recording (e.g., `1024x768`) |
| `--faithful` | `false` | Capture focus styles for pixel-perfect keyboard navigation replay (experimental) |
| `-f, --force` | `false` | Overwrite existing file without prompting |

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

# Record and open in default application
inspekt record --open checkout.yaml

# Record and immediately replay to verify (with visual/audio feedback)
inspekt record --replay checkout.yaml

# Record and step through replay interactively
inspekt record --replay -i checkout.yaml

# Record, open in default application, then replay to verify
inspekt record --open --replay checkout.yaml

# Capture page state for reproducible replay
inspekt record --capture-state login-flow.yaml

# Capture specific localStorage keys
inspekt record --capture-state --storage-keys "theme,language,preferences" app-test.yaml

# Generate DOM checksum for state verification
inspekt record --checksum --capture-state checkout.yaml

# Mark viewport as important for this recording
inspekt record --match-viewport responsive-test.yaml

# Mark both viewport and zoom as requirements
inspekt record --match-viewport --match-zoom-level pixel-perfect-test.yaml

# Record at a specific viewport size (resizes browser before recording)
inspekt record --viewport 1024x768 tablet-flow.yaml

# Record at mobile viewport
inspekt record --viewport 375x667 mobile-flow.yaml

# Capture focus styles for pixel-perfect keyboard navigation replay (experimental)
inspekt record --faithful keyboard-a11y-test.yaml

# Overwrite existing file without prompting (useful for automation)
inspekt record --force checkout.yaml
```

## Recording to an Existing File

When you record to a file that already exists, Inspekt shows information about the existing recording and offers four options:

```
⚠ File already exists: checkout.yaml
  Created: 2025-12-16 10:03
  Steps: 12
  URL: https://example.com/checkout

What would you like to do?

  [1] Create a new timestamped recording (20251216_checkout.yaml)
  [2] Overwrite the existing recording (all 12 steps will be lost)
  [3] Append steps to the existing recording (metadata will remain intact)
  [4] Cancel

Choose [1/2/3/4] (1):
```

### Options Explained

| Option | Description |
|--------|-------------|
| **[1] Create timestamped** | Creates a new file with today's date prefix (e.g., `20251216_checkout.yaml`). The original file is preserved. This is the default. |
| **[2] Overwrite** | Replaces the existing file completely. All previous steps are lost. |
| **[3] Append** | Adds new steps to the end of the existing recording. Metadata (URL, timestamps) from the original recording is preserved. Useful for extending a recording session. |
| **[4] Cancel** | Abort without recording. |

### Bypassing the Prompt

Use `--force` to skip the prompt and overwrite automatically:

```bash
# Overwrite without asking (useful in CI/CD or scripts)
inspekt record --force checkout.yaml
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

### `inspekt record tidy`

Comprehensive cleanup of a recording file. Validates, normalizes, and improves the recording while preserving user customizations.

```bash
inspekt record tidy recording.yaml              # Full tidy
inspekt record tidy recording.yaml --dry-run    # Preview changes
inspekt record tidy recording.yaml --force      # Replace all comments
inspekt record tidy recording.yaml -q           # Quiet mode (summary only)
```

**Operations performed (all enabled by default):**

| Operation | Description |
|-----------|-------------|
| **Validate YAML** | Check syntax, abort if invalid |
| **Detect fragile selectors** | Warn about auto-generated IDs, long CSS paths, `:nth-child` |
| **Validate timestamps** | Warn if timestamps are out of order |
| **Re-number steps** | Sequential numbering (0001, 0002, 0003...) |
| **Enrich comments** | Add assertion info to auto-generated comments |
| **Normalize keys** | Consistent key order (action, target, expect...) |
| **Remove empty values** | Clean up null/empty fields |
| **Fix indentation** | Consistent 2-space indentation |

**Options:**

| Option | Description |
|--------|-------------|
| `--dry-run` | Preview changes without modifying the file |
| `--force` | Replace ALL comments (ignores user customizations) |
| `--no-comments` | Skip comment updates |
| `--no-normalize` | Skip key order normalization |
| `--no-clean` | Skip empty value removal |
| `-q, --quiet` | Only show warnings and summary |

**Example output:**

```
$ inspekt record tidy checkout-flow.yaml --dry-run

Previewing changes for checkout-flow.yaml...

⚠ Fragile Selectors Detected:
  Step 0003: Index-based selector (:nth-child)
            div.products > div:nth-child(2) > button

⚠ Timestamp Issues:
  Step 0005: timestamp 2500ms is out of order (previous: 3000ms)

Comments:
  Step 0001: Navigate to https://example.com (preserved)
  Step 0002: Click on button 'Add to Cart'
           → Click on button 'Add to Cart' and wait for '.cart-count' to appear

Summary:
  Comments enriched: 1
  Comments preserved: 4
  Keys normalized: 5
  Fragile selectors: 1
  Timestamp issues: 1
  Total steps: 5

Dry run complete. No changes were made.
```

**When to use:**

- After adding assertions (`expect:`) to steps
- After adding conditions (`skip_if:`, `wait_for:`)
- After deleting or reordering steps
- Before committing recordings to version control
- To validate and clean up imported recordings

**How comment customization detection works:**

1. Generates a "base" comment (without assertion info) for each step
2. Compares with the existing comment
3. If they match → comment was auto-generated → enrich with assertion info
4. If they differ → user customized it → preserve their text

**Example workflow:**

```bash
# 1. Record a flow
inspekt record my-flow.yaml

# 2. Edit the file to add assertions
#    - Add expect: visible: ".success-message" to a step

# 3. Tidy up to update comments and normalize
inspekt record tidy my-flow.yaml
```

**Before tidy:**
```yaml
# Step 0002 · Click on button 'Submit'
- timestamp: 2500
  action: click
  target:
    selector: "#submit"
    accessible_name: Submit
  expect:
    visible: ".success-message"
```

**After tidy:**
```yaml
# Step 0002 · Click on button 'Submit' and wait for '.success-message' to appear
- timestamp: 2500
  action: click
  target:
    selector: "#submit"
    accessible_name: Submit
  expect:
    visible: ".success-message"
```

**Preserved custom comments:**

If you've written a custom comment like:
```yaml
# Step 0003 · Submit the registration form
```

Instead of the auto-generated:
```yaml
# Step 0003 · Click on button 'Create Account'
```

The tidy command will detect this customization and preserve your text (only updating the step number if needed).

**Fragile selector warnings:**

The tidy command warns about selectors that may break when the page changes:

- **Auto-generated IDs**: `#react-select-*`, `#ember*`, `#ng-*`, etc.
- **Index-based selectors**: `:nth-child()`, `:nth-of-type()`
- **Long CSS paths**: Selectors with 5+ levels of nesting

These warnings help you identify steps that may need more robust selectors (like `data-testid` attributes).

## Recording File Format (YAML)

### File Structure (v1.1)

```yaml
# Inspekt Recording v1.1
# Generated: 2025-12-02T10:30:00+00:00
# Duration: 45.2s
# URL: https://example.com/login

metadata:
  version: "1.1"
  created_at: "2025-12-02T10:30:00+00:00"
  duration_ms: 45200
  starting_url: "https://example.com/login"
  user_agent: "Mozilla/5.0..."
  recorded_on:
    platform: "darwin"
    browser: "Chrome"
    browser_version: "131.0"

state:
  viewport:
    width: 1920
    height: 1080
  zoom: 1.0
  scroll:
    x: 0
    y: 0
  # Optional - only if --capture-state was used:
  cookies: "base64-encoded-json..."
  local_storage: "base64-encoded-json..."
  session_storage: "base64-encoded-json..."
  checksum: "sha256:abc123..."

# Optional - manually added preconditions
preconditions:
  required:
    - selector: "#login-form"
      description: "Login form must exist"
  url_pattern: "https://example.com/*"

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

#### download
Records file downloads triggered during the session.

```yaml
- timestamp: 6000
  action: download
  download:
    filename: "report.pdf"
    url: "https://example.com/files/report.pdf"
    mime_type: "application/pdf"
    size: 524288
    download_start: 1733000000000
    download_end: 1733000002500
    external_path: "inspekt_20251201_103000_example_com_files/downloads/report.pdf"
```

The `external_path` points to where the file is saved in the recording's `_files/downloads/` directory.

**Recording Safety Limits:**

To prevent accidental misuse and runaway recordings, Inspekt enforces these safety limits:

*Download Limits:*

| Limit | Value | Description |
|-------|-------|-------------|
| **Maximum downloads per session** | 10 | Recording auto-stops after 10 downloads |
| **Maximum file size** | 25 MB | Files larger than 25MB are skipped (not recorded) |

When the download limit is reached:

1. The current download is skipped with a warning in the YAML
2. Recording automatically stops and saves
3. A message is displayed: "Download limit (10) reached - recording auto-stopped for security"

If a download exceeds the size limit, it appears in the recording as:

```yaml
- timestamp: 5000
  action: download
  download:
    filename: "large-video.mp4"
    size: 104857600
    skipped: true
    skip_reason: "File size (100.0MB) exceeds 25MB limit"
```

!!! tip "Need more downloads?"
    If your test scenario requires more than 10 downloads, split it into multiple recording sessions or manually add download steps to the YAML file.

*Action Rate Limit:*

To prevent runaway recordings from held keys, injected code, or loops, Inspekt monitors the action rate:

| Limit | Value | Description |
|-------|-------|-------------|
| **Maximum actions per second** | 5 | Recording auto-stops if exceeded |

When the rate limit is exceeded:

1. Recording automatically stops and saves
2. A message is displayed: "Action rate limit (5/second) exceeded. Recording has been stopped as a precaution."

This protects against scenarios like:
- Accidentally holding down a key (generating rapid keypress events)
- JavaScript code triggering synthetic events in a loop
- Infinite scrolling or rapid navigation scripts

**Adding download assertions:**

```yaml
- timestamp: 6000
  action: download
  download:
    filename: "report.pdf"
    external_path: "..."
  expect:
    download_mime_type: "application/pdf"
    download_min_size: 1024
    download_filename_contains: "report"
```

See [Download Assertions](#download-assertions) for all available checks.

#### upload
Records file uploads to form inputs.

```yaml
- timestamp: 7000
  action: upload
  target:
    selector: "input[type='file']"
  files:
    - name: "document.pdf"
      type: "application/pdf"
      size: 102400
      external_path: "inspekt_20251201_103000_example_com_files/uploads/document.pdf"
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

### Download Assertions

When a `download` action is recorded, you can add assertions to verify the downloaded file:

```yaml
- timestamp: 8000
  action: download
  download:
    filename: "report.pdf"
    external_path: "inspekt_..._files/downloads/report.pdf"
  expect:
    # File type checks
    download_mime_type: "application/pdf"
    download_filename_contains: "report"
    download_filename_matches: "^report-\\d{4}\\.pdf$"

    # Size checks
    download_min_size: 1024        # At least 1KB
    download_max_size: 10485760    # At most 10MB

    # Content checks
    download_content_contains: "Annual Report"
    download_checksum: "sha256:abc123..."

    # Shell command checks (advanced)
    download_shell:
      command: "pdfinfo"           # Allowlisted command
      contains: "Pages:"           # Output must contain this
```

**Available download assertions:**

| Assertion | Description |
|-----------|-------------|
| `download_mime_type` | Expected MIME type (e.g., "application/pdf") |
| `download_min_size` | Minimum file size in bytes |
| `download_max_size` | Maximum file size in bytes |
| `download_filename_contains` | Substring that filename must contain |
| `download_filename_matches` | Regex pattern for filename |
| `download_content_contains` | Text that file content must contain |
| `download_checksum` | Expected checksum (format: "sha256:..." or "md5:...") |
| `download_shell` | Run allowlisted shell command on file |

**Allowlisted shell commands:**

For security, only these commands can be used with `download_shell`:

| Command | Purpose |
|---------|---------|
| `file` | Detect file type |
| `pdfinfo` | PDF metadata |
| `identify` | Image info (ImageMagick) |
| `exiftool` | EXIF metadata |
| `wc` | Word/line count |
| `head` | First N lines |
| `tail` | Last N lines |
| `grep` | Search content |
| `md5sum` | MD5 checksum |
| `sha256sum` | SHA256 checksum |
| `stat` | File stats |
| `strings` | Extract strings |

## File Storage

### How Downloaded Files Are Saved

When you stop recording (`Ctrl+C`), Inspekt saves downloaded files to a `_files/downloads/` subdirectory:

```
recording.yaml
recording_files/
├── downloads/
│   ├── report.pdf
│   └── data.csv
└── uploads/
    └── image.png
```

**File retrieval strategies (in order of preference):**

1. **Direct copy** (default): Copy from Chrome's download location
   - Most reliable method
   - Works when Inspekt runs on the same machine as Chrome

2. **Base64 fallback**: Decode from in-memory content
   - Used when Chrome's download folder is inaccessible
   - Necessary for Docker containers, remote sessions, or VM environments

**When direct copy fails:**

In containerized environments (Docker, remote VMs), Chrome's download folder may not be accessible from the host where Inspekt saves recordings. In these cases:

- The browser extension captures file content as base64
- This is decoded and saved when the recording is saved
- A warning is shown if neither method succeeds

**Docker/VM considerations:**

When running `inspekt vm` (Docker browser), downloads go to Chrome's folder *inside the container*. The file is captured via base64 and saved when you stop recording. This works automatically but may be slower for large files.

**Manual file recovery:**

If a download wasn't captured (warning shown), you can:

1. Find the file in Chrome's Downloads folder
2. Copy it to `{recording}_files/downloads/`
3. Update the YAML to set `external_path` correctly

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
