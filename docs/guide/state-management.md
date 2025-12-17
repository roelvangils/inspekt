# State Management in Recordings

This guide covers Inspekt's state capture and restoration features for creating reproducible browser tests.

## Overview

Recording format v1.1 introduces a `state` section that captures the browser's state at recording time:

- **Viewport dimensions** - Window size for consistent rendering
- **Scroll position** - Initial scroll offset
- **Cookies** - Authentication and session data
- **localStorage/sessionStorage** - Client-side storage
- **DOM checksum** - Page structure fingerprint

This enables more reliable replay by restoring the exact environment conditions.

---

## Recording State

### Basic Recording (Always Captured)

Every recording automatically captures:

```yaml
state:
  viewport:
    width: 1920
    height: 1080
  zoom: 1.0
  scroll:
    x: 0
    y: 0
```

### Capturing Cookies and Storage

Use `--capture-state` to also capture cookies and storage:

```bash
inspekt record --capture-state login-flow.yaml
```

**Important:** You must specify which storage keys to capture with `--storage-keys`:

```bash
# Capture specific localStorage keys
inspekt record --capture-state --storage-keys "theme,language,userPrefs" app-test.yaml

# Without --storage-keys, only cookies are captured
inspekt record --capture-state login.yaml  # Cookies only
```

This creates:

```yaml
state:
  viewport:
    width: 1920
    height: 1080
  zoom: 1.0
  scroll:
    x: 0
    y: 100
  cookies: "W3sibmFtZSI6InNlc3Npb24iLCJ2YWx1ZSI6ImFiYzEyMyJ9XQ=="
  local_storage: "eyJ0aGVtZSI6ImRhcmsiLCJsYW5ndWFnZSI6ImVuIn0="
```

### Generating DOM Checksum

Add `--checksum` to capture a fingerprint of the page structure:

```bash
inspekt record --checksum checkout-flow.yaml
```

This creates:

```yaml
state:
  viewport:
    width: 1920
    height: 1080
  checksum: "sha256:a1b2c3d4e5f6..."
```

The checksum is a SHA-256 hash of the DOM structure (tags only, ignoring text content and attributes). This helps detect when page structure has changed.

### Full State Capture

Combine all options for complete state capture:

```bash
inspekt record --capture-state --storage-keys "theme,cart,prefs" --checksum full-test.yaml
```

---

## YAML State Section Reference

### Complete Example

```yaml
metadata:
  version: "1.1"
  created_at: "2025-12-12T10:30:00+00:00"
  duration_ms: 45200
  starting_url: "https://example.com"
  user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)..."
  recorded_on:
    platform: "darwin"
    browser: "Chrome"
    browser_version: "131.0.6778.86"

state:
  viewport:
    width: 1920
    height: 1080
  zoom: 1.0
  scroll:
    x: 0
    y: 250
  cookies: "W3sibmFtZSI6InNlc3Npb24iLC..."    # Base64-encoded JSON
  local_storage: "eyJ0aGVtZSI6ImRhcmsifQ=="   # Base64-encoded JSON
  session_storage: "eyJjYXJ0IjoiW10ifQ=="      # Base64-encoded JSON
  checksum: "sha256:a1b2c3d4e5f6g7h8i9j0..."   # DOM structure hash

preconditions:
  required:
    - selector: "#login-form"
      description: "Login form must be present"
    - selector: ".main-navigation"
      description: "Navigation menu required"
  url_pattern: "https://example.com/*"
  title_contains: "Dashboard"

steps:
  # ... recording steps ...
```

### State Fields

| Field | Type | Description |
|-------|------|-------------|
| `viewport` | object | Browser window dimensions (`width`, `height`) |
| `zoom` | float | Device pixel ratio (1.0 = 100%) |
| `scroll` | object | Initial scroll position (`x`, `y`) |
| `cookies` | string | Base64-encoded JSON array of cookie objects |
| `local_storage` | string | Base64-encoded JSON object of key-value pairs |
| `session_storage` | string | Base64-encoded JSON object of key-value pairs |
| `checksum` | string | DOM structure hash (`sha256:...`) |

### Storage Format

Cookies and storage are Base64-encoded JSON for compactness. Example decoded values:

**Cookies:**
```json
[
  {
    "name": "session",
    "value": "abc123",
    "domain": ".example.com",
    "path": "/",
    "secure": true,
    "httpOnly": true,
    "sameSite": "Lax"
  }
]
```

**localStorage:**
```json
{
  "theme": "dark",
  "language": "en",
  "userPrefs": "{\"notifications\":true}"
}
```

---

## Preconditions

Preconditions verify that required elements exist before replay starts. Unlike checksums (which can be overly strict), preconditions let you specify exactly what matters for your test.

### Adding Preconditions

Add a `preconditions` section to your YAML:

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

### Precondition Fields

| Field | Description |
|-------|-------------|
| `required` | List of elements that must exist |
| `required[].selector` | CSS selector to check |
| `required[].description` | Human-readable description (shown on failure) |
| `url_pattern` | URL glob pattern to match |
| `title_contains` | Text that must appear in page title |

### Precondition Behavior

By default, preconditions produce **warnings** but don't stop replay:

```
⚠ Precondition not met: Login form must be present
```

Use `--strict-preconditions` to halt on failure:

```bash
inspekt replay login.yaml --strict-preconditions
```

```
✗ Precondition failed: Login form must be present
  Use --no-strict-preconditions to continue anyway
```

---

## Replaying with State Restoration

### Restoring All State

Use `--restore-state` to restore cookies and storage:

```bash
inspekt replay login.yaml --restore-state
```

This:
1. Navigates to the starting URL
2. Restores cookies (via browser extension)
3. Restores localStorage/sessionStorage
4. Restores scroll position
5. Begins step execution

### Selective Restoration

Restore only specific parts:

```bash
# Restore only cookies
inspekt replay login.yaml --restore-cookies

# Restore only storage
inspekt replay login.yaml --restore-storage
```

### Verifying Checksum

Enable checksum verification to detect page changes:

```bash
inspekt replay checkout.yaml --verify-checksum
```

By default, mismatches produce warnings:

```
⚠ DOM checksum mismatch - page structure differs from recording
```

Use `--strict-checksum` to halt on mismatch:

```bash
inspekt replay checkout.yaml --verify-checksum --strict-checksum
```

### Verbose Output

See restoration details with `--verbose`:

```bash
inspekt replay login.yaml --restore-state --verify-checksum --verbose
```

Output:
```
Replaying: login.yaml
Recorded: December 12, 2025 at 10:30
URL: https://example.com/login
Viewport: 1920x1080
Steps: 12 of 12

  [system] Checking preconditions...
  [system] ✓ Login form must be present
  [system] ✓ Submit button required
  [system] Verifying DOM checksum...
  [system] ✓ DOM checksum matches
  [system] Restoring cookies...
  [system] ✓ Restored 3 cookies
  [system] ✓ Restored 2 localStorage keys
  [system] Restoring scroll position to (0, 250)...

  001  00:00  navigate  → https://example.com/login OK
  ...
```

---

## When to Use State Management

### Good Use Cases

1. **Testing authenticated flows** - Restore session cookies to skip login
2. **Testing user preferences** - Restore localStorage settings
3. **CI/CD environments** - Restore state on fresh browser instances
4. **Detecting page changes** - Use checksum to catch unexpected changes

### When NOT to Use

1. **Sharing recordings** - Cookies may contain sensitive auth tokens
2. **Testing login flows** - Don't restore cookies if testing the login itself
3. **Cross-environment testing** - Cookies may be domain-specific
4. **Long-running tests** - Cookies and tokens expire

### Security Considerations

**Warning:** Captured cookies may contain:
- Session tokens
- Authentication tokens
- API keys
- CSRF tokens

**Best practices:**
- Don't commit recordings with captured state to version control
- Use environment-specific recordings
- Consider using `--restore-cookies` only in isolated CI environments

---

## Replay Settings in YAML

You can also set default replay behavior in the YAML file:

```yaml
replay:
  restore_viewport: true        # ON by default
  restore_scroll: false         # OFF by default
  restore_cookies: false        # OFF by default
  restore_local_storage: false  # OFF by default
  restore_session_storage: false
  verify_preconditions: true    # ON by default
  verify_checksum: false        # OFF by default
  halt_on_precondition_fail: false
  halt_on_checksum_mismatch: false
```

CLI flags override YAML settings.

---

## Troubleshooting

### "Cookie restoration failed"

**Cause:** Browser extension cannot set cookies (may be blocked by browser policy)

**Solutions:**
1. Ensure Inspekt extension is installed and enabled
2. Check that cookies are for the correct domain
3. Verify cookies haven't expired

### "Precondition not met"

**Cause:** Required element doesn't exist on the page

**Solutions:**
1. Verify you're on the correct page
2. Wait for dynamic content to load
3. Update the selector in preconditions
4. Remove outdated preconditions

### "DOM checksum mismatch"

**Cause:** Page structure has changed since recording

**Solutions:**
1. Re-record if page has legitimately changed
2. Use `--no-verify-checksum` to skip check
3. Use preconditions instead (more targeted)

### "Storage restoration failed"

**Cause:** localStorage/sessionStorage cannot be set

**Solutions:**
1. Verify same-origin policy (storage is per-origin)
2. Check that storage isn't full
3. Ensure page has loaded before restoration

---

## Examples

### Example 1: Testing with Session

```bash
# Record while logged in, capturing session cookie
inspekt record --capture-state admin-dashboard.yaml

# Replay with session restored (skips login)
inspekt replay admin-dashboard.yaml --restore-cookies
```

### Example 2: Testing User Preferences

```bash
# Record with dark mode enabled
inspekt record --capture-state --storage-keys "theme,fontSize" ui-test.yaml

# Replay with same preferences
inspekt replay ui-test.yaml --restore-storage
```

### Example 3: CI Pipeline with Strict Verification

```bash
# Record with checksum and preconditions
inspekt record --checksum checkout.yaml

# Manually add preconditions to YAML:
# preconditions:
#   required:
#     - selector: "#cart"
#       description: "Shopping cart must exist"

# Run in CI with strict mode
inspekt replay checkout.yaml \
  --strict-preconditions \
  --verify-checksum \
  --strict-checksum \
  --no-feedback
```

### Example 4: Full State Workflow

```bash
# 1. Record with full state capture
inspekt record \
  --capture-state \
  --storage-keys "cart,preferences,recentlyViewed" \
  --checksum \
  e2e-checkout.yaml

# 2. Review and add preconditions
code e2e-checkout.yaml

# 3. Replay with full restoration and verification
inspekt replay e2e-checkout.yaml \
  --restore-state \
  --verify-checksum \
  --verbose

# 4. Run in CI with strict mode
inspekt replay e2e-checkout.yaml \
  --restore-state \
  --strict-preconditions \
  --strict-checksum \
  --no-feedback
```

---

## Related Documentation

- [inspekt record](../commands/record.md) - Recording command reference
- [inspekt replay](../commands/replay.md) - Replay command reference
- [Recording and Replay Tutorial](recording-replay.md) - Getting started guide
