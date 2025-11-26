# inspekt console - Browser Console Message Capture

The `inspekt console` commands let you capture, view, and manage browser console messages from the command line. This is invaluable for debugging JavaScript errors, monitoring application behavior, and capturing diagnostic information without having DevTools open.

## Quick Start

```bash
# Quick expression evaluation (shorthand)
inspekt log "5+5"           # → 10
inspekt log "document.title" # → Example Domain

# View all captured console messages
inspekt console list

# Show only errors
inspekt console list --level error

# Get JSON output for scripting
inspekt console list --json

# Clear the message buffer
inspekt console clear
```

## Why Use Console Capture?

### The Inspekt Advantage

Unlike browser DevTools, Inspekt captures console messages **programmatically**:

- **Capture without DevTools** - No need to have the console panel open
- **Automated testing** - Check for JavaScript errors after interactions
- **Remote debugging** - Monitor console output from the terminal
- **CI/CD integration** - Verify no console errors in automated tests
- **Historical logging** - Messages persist even after page interactions

**Example workflow:**
```bash
# Navigate to your app
inspekt open https://app.example.com

# Perform some actions that might trigger errors
inspekt click "#submit-button"

# Check for any console errors
inspekt console list --level error

# If errors found, get the full context
inspekt console list --json > debug-log.json
```

### What Gets Captured

**Basic logging:**
- **console.log()** - General logging messages
- **console.error()** - Error messages and stack traces
- **console.warn()** - Warning messages
- **console.info()** - Informational messages
- **console.debug()** - Debug-level messages

**Advanced methods (also captured):**
- **console.table()** - Rendered as ASCII tables in output
- **console.dir()** - Object inspection with JSON formatting
- **console.count() / countReset()** - Counter tracking
- **console.time() / timeLog() / timeEnd()** - Timing measurements
- **console.assert()** - Assertion failures
- **console.trace()** - Stack traces
- **console.group() / groupCollapsed()** - Grouping markers

Each captured message includes:
- Log level (error, warn, log, info, debug)
- Timestamp (ISO 8601 format, displayed in local time)
- Message content (serialized to string)

## Commands

### `inspekt console list`

Show captured console messages from the current browser tab.

```bash
inspekt console list [OPTIONS]
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--level` | `-l` | Filter by log level: `all`, `error`, `warn`, `log`, `info`, `debug` (default: `all`) |
| `--limit` | `-n` | Maximum messages to show (default: 100) |
| `--tail` | `-t` | Show most recent messages first |
| `--json` | | Output as JSON for scripting |

**Examples:**

```bash
# Show all messages
inspekt console list

# Show only errors and warnings
inspekt console list --level error
inspekt console list --level warn

# Show last 10 messages, newest first
inspekt console list --limit 10 --tail

# Get JSON for processing
inspekt console list --json | jq '.entries[] | select(.level == "error")'
```

**Output format (default):**
```
14:32:01 [error] Uncaught TypeError: Cannot read property 'x' of undefined
14:32:02 [warn] Deprecation warning: This API will be removed in v2.0
14:32:03 [log] User clicked button
14:32:04 [info] Request completed in 234ms
14:32:05 [debug] State updated: {count: 5}
```

**With eval commands (shows what code produced each log):**
```
14:32:00 ▸ console.log(5+5)
14:32:00 [log] 10
14:32:01 ▸ console.log(document.title)
14:32:01 [log] Example Domain
```

**JSON output format:**
```json
{
  "ok": true,
  "count": 3,
  "entries": [
    {
      "level": "error",
      "timestamp": "2025-11-26T14:32:01.123Z",
      "message": "Uncaught TypeError: Cannot read property 'x' of undefined"
    },
    {
      "level": "warn",
      "timestamp": "2025-11-26T14:32:02.456Z",
      "message": "Deprecation warning: This API will be removed in v2.0"
    },
    {
      "level": "log",
      "timestamp": "2025-11-26T14:32:03.789Z",
      "message": "User clicked button"
    }
  ],
  "hooked": true
}
```

### `inspekt console clear`

Clear the console message buffer. New messages will continue to be captured.

```bash
inspekt console clear [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--json` | Output result as JSON |

**Examples:**

```bash
# Clear the buffer
inspekt console clear

# Clear with JSON confirmation
inspekt console clear --json
```

### `inspekt log` (shorthand)

Quickly evaluate an expression and log the result. This is a convenient shorthand for `inspekt eval "console.log(expression)"`.

```bash
inspekt log EXPRESSION
# or
inspekt console log EXPRESSION
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--timeout` | `-t` | Timeout in seconds (default: 10) |

**Examples:**

```bash
# Simple math
inspekt log "5+5"           # → 10
inspekt log "Math.PI"       # → 3.141592653589793

# DOM queries
inspekt log "document.title"                    # → Example Domain
inspekt log "document.links.length"             # → 42
inspekt log "location.hostname"                 # → example.com

# Array operations
inspekt log "[1,2,3].map(x => x*2)"            # → [2,4,6]
inspekt log "Array.from(document.images).length" # → 5

# Objects
inspekt log "{a: 1, b: 2}"                      # → {"a":1,"b":2}

# Quick debugging
inspekt log "localStorage.length"
inspekt log "document.cookie"
inspekt log "navigator.userAgent"
```

**Tip:** Use `inspekt log` for quick one-off checks. Use `inspekt eval` when you need the return value or want to run more complex code.

## Use Cases

### 1. Debugging JavaScript Errors

Quickly identify JavaScript errors on any page:

```bash
# Navigate to the page
inspekt open https://myapp.com/dashboard

# Wait for page to load, then check for errors
inspekt console list --level error

# If you see errors, get the full log for context
inspekt console list --json > error-report.json
```

### 2. Automated Error Checking

Integrate with shell scripts for automated testing:

```bash
#!/bin/bash
# check-for-errors.sh

inspekt open "$1"
sleep 3

# Check if any errors were logged
ERROR_COUNT=$(inspekt console list --json | jq '.entries | map(select(.level == "error")) | length')

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "Found $ERROR_COUNT JavaScript errors!"
    inspekt console list --level error
    exit 1
else
    echo "No JavaScript errors found"
    exit 0
fi
```

### 3. Monitoring User Interactions

Track what happens when users interact with your app:

```bash
# Clear any existing messages
inspekt console clear

# Perform the interaction
inspekt click "#login-button"
inspekt type "user@example.com"
inspekt click "#submit"

# See what was logged
inspekt console list --tail
```

### 4. Performance Monitoring

Capture timing and performance logs:

```bash
# Many apps log performance metrics to console
inspekt console list --json | jq '.entries[] | select(.message | contains("performance"))'

# Or filter for specific patterns
inspekt console list --json | jq '.entries[] | select(.message | test("took [0-9]+ms"))'
```

### 5. API Response Debugging

Monitor API calls and responses logged to console:

```bash
# Look for network-related logs
inspekt console list --json | jq '.entries[] | select(.message | contains("fetch") or contains("API"))'
```

### 6. Third-Party Script Monitoring

Check what third-party scripts are logging:

```bash
# See all warnings (often from third-party scripts)
inspekt console list --level warn

# Check for any errors from analytics, tracking, etc.
inspekt console list --level error --json | jq '.entries[].message'
```

### 7. Form Validation Debugging

Debug form validation issues:

```bash
# Clear console before testing
inspekt console clear

# Fill out and submit form
inspekt type "invalid-email" --selector "#email"
inspekt click "#submit"

# Check for validation errors logged
inspekt console list
```

### 8. SPA Navigation Debugging

Track console output during single-page app navigation:

```bash
# Clear before navigation
inspekt console clear

# Navigate within SPA
inspekt click "a[href='/settings']"
sleep 2

# Check what was logged during navigation
inspekt console list --tail --limit 20
```

### 9. CI/CD Pipeline Integration

Add to your test pipeline:

```yaml
# .github/workflows/e2e-tests.yml
- name: Check for console errors
  run: |
    inspekt open ${{ env.APP_URL }}
    sleep 5
    ERRORS=$(inspekt console list --json | jq '.entries | map(select(.level == "error")) | length')
    if [ "$ERRORS" -gt 0 ]; then
      echo "::error::Found $ERRORS JavaScript console errors"
      inspekt console list --level error
      exit 1
    fi
```

### 10. Debugging with AI Assistance

Export console logs for AI analysis:

```bash
# Capture full log
inspekt console list --json > console-log.json

# Send to Claude for analysis
cat console-log.json | claude "Analyze these console logs and identify any issues"
```

## How It Works

### Architecture

```
Page loads → Extension injects console hooks → Messages buffered in browser
                                                           ↓
CLI: inspekt console list → HTTP GET /console/logs → WebSocket → Extension
                                                           ↓
                                                    Return buffered messages
```

### Technical Details

1. **Hook Injection**: When a page loads, the extension injects hooks that intercept `console.log`, `console.error`, `console.warn`, `console.info`, and `console.debug` calls.

2. **Message Buffer**: Captured messages are stored in an in-memory buffer in the browser (max 1000 messages, oldest dropped when full).

3. **Serialization**: Arguments passed to console methods are serialized to strings. Objects are JSON.stringify'd, primitives are converted directly.

4. **Original Behavior Preserved**: The original console methods are still called, so messages also appear in DevTools as normal.

## Limitations

- **Buffer size**: Maximum 1000 messages per page. Oldest messages are dropped when the buffer is full.
- **Cross-origin iframes**: Console messages from cross-origin iframes are not captured.
- **Service Workers**: Console messages from Service Workers are not captured.
- **Page navigation**: Buffer is cleared when navigating to a new page.
- **Extension messages**: Some extension-internal messages may appear in the buffer.

## Troubleshooting

### "Console hooks not active"

**Issue:** You see "Note: Console hooks not active. Reload the page to start capturing."

**Solution:** Reload the page to inject the console hooks:
```bash
inspekt reload
# Wait for page to load
inspekt console list
```

### No messages captured

**Issue:** `inspekt console list` shows "No console messages captured."

**Possible causes:**
1. The page hasn't logged anything to the console
2. The page was loaded before the extension was active
3. Messages were logged before hook injection completed

**Solution:**
```bash
# Reload to ensure hooks are active
inspekt reload

# Trigger some console output (if testing)
inspekt eval "console.log('test message')"

# Now check
inspekt console list
```

### Messages not appearing in real-time

**Note:** Console capture is not a real-time streaming feature. Messages are collected and retrieved on-demand when you run `inspekt console list`.

For real-time monitoring, run the command in a loop:
```bash
while true; do
    clear
    inspekt console list --tail --limit 20
    sleep 2
done
```

### Large objects truncated

**Issue:** Large objects logged to console appear truncated.

**Reason:** Objects are JSON.stringify'd for capture. Very large objects or objects with circular references may be truncated or show `[object Object]`.

**Workaround:** Log specific properties or use `JSON.stringify()` explicitly in your code for important objects.

## Related Commands

- `inspekt log` - Quick expression evaluation (shorthand for `eval "console.log(...)"`)
- `inspekt eval` - Execute JavaScript and return the result
- `inspekt repl` - Interactive JavaScript REPL with console output
- `inspekt screenshot` - Capture visual state alongside console errors
- `inspekt axe` - Run accessibility audit (checks for JS errors too)

## API Reference

### HTTP Endpoints

**GET /console/logs**

Retrieve captured console messages.

```bash
curl http://127.0.0.1:8765/console/logs
```

Response:
```json
{
  "ok": true,
  "entries": [...],
  "count": 5,
  "hooked": true
}
```

**POST /console/clear**

Clear the console message buffer.

```bash
curl -X POST http://127.0.0.1:8765/console/clear
```

Response:
```json
{
  "ok": true,
  "message": "Console buffer cleared"
}
```

### MCP Tool

The console functionality is also available via MCP:

```
mcp__inspekt__get_console_logs
mcp__inspekt__clear_console_logs
```

See [MCP Integration](../MCP_INTEGRATION.md) for details.
