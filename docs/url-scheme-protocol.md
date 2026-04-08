# Inspekt URL Scheme Protocol

## Overview

The `inspekt://` URL scheme is a custom protocol handler that allows you to trigger Inspekt commands from anywhere on macOS - browsers, Alfred, Raycast, Shortcuts.app, or any application that can open URLs.

## Architecture

### Components

1. **Protocol Registration** - macOS LaunchServices registers `inspekt://`
2. **App Bundle** - `/Applications/Inspekt.app` (AppleScript application)
3. **URL Handler** - `/Users/roelvangils/inspekt_bridge/url_handler/inspekt_url_handler.py`
4. **Bridge Server** - WebSocket server that communicates with browser extension
5. **CLI Commands** - Underlying `inspekt` command-line tools

### Request Flow

```
User Action (Raycast/Browser/etc.)
    ↓
inspekt://command?param=value
    ↓
macOS LaunchServices
    ↓
/Applications/Inspekt.app (AppleScript)
    ↓
inspekt_url_handler.py (Python)
    ↓
Parse URL → Execute CLI command → Handle output
    ↓
Display result (clipboard/notification/dialog)
```

## URL Syntax

```
inspekt://command?param1=value1&param2=value2&output=mode
```

### Components

- **Protocol**: `inspekt://`
- **Command**: The Inspekt command to execute (e.g., `summarize`, `eval`, `click`)
- **Parameters**: Command-specific parameters (URL-encoded)
- **Output Mode**: Optional `output` parameter to control result display

### URL Encoding

Special characters must be URL-encoded:
- Space → `%20`
- `#` → `%23`
- `&` → `%26`
- `?` → `%3F`

**Examples:**
```
inspekt://type?text=Hello%20World          # Space encoded
inspekt://eval?code=document.querySelector('%23header')  # # encoded
inspekt://ask?q=What%20is%20the%20main%20point%3F      # ? encoded
```

## Output Modes

The `output` parameter controls how command results are displayed:

| Mode | Description | Use Case |
|------|-------------|----------|
| `clipboard` | Copy to clipboard + brief notification | Data you want to paste elsewhere |
| `notification` | Show in macOS notification only | Quick confirmations |
| `dialog` | Show in macOS dialog popup | Long text you want to read |
| `both` | Clipboard + notification | Important data you want saved and confirmed |
| `silent` | No output (errors still show) | Background automation |

### Smart Defaults

Commands have intelligent default output modes based on their purpose:

#### AI Commands → `dialog`
Content designed to be read immediately:
- `summarize` - Article summaries
- `describe` - Page descriptions
- `ask` - AI answers to questions

**Example:**
```bash
inspekt://summarize              # Shows in dialog (default)
inspekt://summarize?output=clipboard  # Override: copy to clipboard
```

#### Data Commands → `clipboard`
Content designed to be copied and used:
- `eval` - JavaScript execution results
- `info` - Page information
- `selection` - Selected text/HTML/markdown
- `cookies` - Cookie data
- `screenshot` - Screenshot paths
- `outline` - Page outline/structure

**Example:**
```bash
inspekt://selection?format=markdown   # Copies to clipboard (default)
inspekt://info?output=dialog          # Override: show in dialog
```

#### Action Commands → `notification`
Commands that perform actions (just need confirmation):
- `open` - Navigate to URL
- `back`, `forward`, `reload` - Navigation
- `click`, `type`, `paste` - Interactions
- `inspect` - Element inspection

**Example:**
```bash
inspekt://click?selector=button       # Just shows notification (default)
inspekt://type?text=Hello&output=silent  # Override: no output
```

## Available Commands

### Navigation

```bash
inspekt://open?url=https://example.com
inspekt://back
inspekt://forward
inspekt://reload
```

### JavaScript Execution

```bash
inspekt://eval?code=document.title
inspekt://eval?code=document.querySelectorAll('a').length
```

### AI Commands

```bash
inspekt://summarize                          # Summarize article
inspekt://summarize?format=bullets           # Bullet point summary
inspekt://summarize?lang=en                  # Summary in English
inspekt://describe                           # Describe page visually
inspekt://describe?lang=nl                   # Description in Dutch
inspekt://outline                            # Extract page outline
inspekt://outline?json=true                  # Outline as JSON
inspekt://ask?q=What is this page about?     # Ask a question
inspekt://ask?q=Who is the author?&no_cache=true  # Don't use cache
```

### Content Extraction

```bash
inspekt://selection?format=text              # Plain text
inspekt://selection?format=html              # HTML markup
inspekt://selection?format=markdown          # Markdown format
```

### Interaction

```bash
inspekt://click?selector=button#submit
inspekt://type?text=Hello%20World&selector=input
inspekt://type?text=Test&speed=0             # Human-like typing
inspekt://paste?text=Quick%20text&selector=textarea
```

### Inspection

```bash
inspekt://inspect?selector=h1
inspekt://screenshot?selector=body
inspekt://screenshot?selector=.header&output=/tmp/shot.png
```

### Cookies

```bash
inspekt://cookies?action=list
inspekt://cookies?action=get&name=sessionid
inspekt://cookies?action=set&name=test&value=hello
inspekt://cookies?action=set&name=auth&value=token&max_age=3600
inspekt://cookies?action=delete&name=test
```

### Page Information

```bash
inspekt://info                               # Full page info
inspekt://info?output=dialog                 # Show in dialog
```

## How It Works Internally

### 1. URL Handler Script

Located at: `/Users/roelvangils/inspekt_bridge/url_handler/inspekt_url_handler.py`

**Key Functions:**

```python
def parse_inspekt_url(url):
    """Parse inspekt:// URL into command and parameters."""
    # Removes 'inspekt://' prefix
    # Splits path and query string
    # Returns (command, params_dict)

def execute_command(command, params):
    """Execute the appropriate inspekt command."""
    # Maps URL commands to CLI commands
    # Builds subprocess call with full paths
    # Returns {"ok": bool, "output": str, "error": str}

def handle_output(result, command, output_mode):
    """Handle command output based on mode."""
    # Routes output to clipboard/notification/dialog
    # Shows errors as notifications
    # Returns success/failure
```

### 2. Full Path Resolution

**Critical for GUI apps**: Commands use full paths to avoid PATH issues:

```python
# ✓ Correct - works from Terminal AND GUI apps
["/Users/roelvangils/.pyenv/shims/inspekt", "summarize"]
["/opt/homebrew/bin/mods"]
["/opt/homebrew/bin/html2markdown"]

# ✗ Wrong - only works from Terminal
["inspekt", "summarize"]  # PATH not set in GUI context
["mods"]                  # Won't be found from Raycast
["html2markdown"]         # Fails from Shortcuts.app
```

This is why we use full paths in:
- `inspekt_url_handler.py` - All inspekt command calls
- `inspekt/app/cli/extraction.py` - All mods calls
- `inspekt/app/cli/selection.py` - html2markdown call

### 3. AppleScript App Bundle

Located at: `/Applications/Inspekt.app`

**Purpose**: Receive URL events from macOS and pass to Python handler

**Key Code** (in embedded AppleScript):
```applescript
on open location this_URL
    -- Log the URL for debugging
    set logFile to (path to home folder as text) & "inspekt_applescript.log"
    try
        set logRef to open for access file logFile with write permission
        write ("URL received: " & this_URL & return) to logRef starting at eof
        close access logRef
    end try

    -- Execute Python handler in background
    do shell script "/Users/roelvangils/inspekt_bridge/url_handler/inspekt_url_handler.py " & ¬
        quoted form of this_URL & " >> " & ¬
        quoted form of POSIX path of logFile & " 2>&1 &"
end open location
```

### 4. macOS Registration

**Info.plist** (in `/Applications/Inspekt.app/Contents/Info.plist`):

```xml
<key>CFBundleURLTypes</key>
<array>
    <dict>
        <key>CFBundleURLName</key>
        <string>Inspekt URL</string>
        <key>CFBundleURLSchemes</key>
        <array>
            <string>inspekt</string>
        </array>
        <key>CFBundleTypeRole</key>
        <string>Viewer</string>
    </dict>
</array>
```

After installation, register with:
```bash
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f /Applications/Inspekt.app
```

## Adding New Commands

### Step 1: Add Command to URL Handler

Edit `/Users/roelvangils/inspekt_bridge/url_handler/inspekt_url_handler.py`:

```python
def execute_command(command, params):
    """Execute the appropriate inspekt command based on parsed URL."""

    # ... existing commands ...

    # Add your new command
    elif command == "mycommand":
        # Extract parameters
        my_param = params.get("param")
        if not my_param:
            return {"error": "Missing 'param' parameter"}

        # Build command with FULL PATH
        cmd = ["/Users/roelvangils/.pyenv/shims/inspekt", "mycommand", my_param]

        # Add optional parameters
        if params.get("option"):
            cmd.extend(["--option", params["option"]])

        # Execute with appropriate timeout
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        # Return result
        return {"ok": result.returncode == 0, "output": result.stdout, "error": result.stderr}
```

### Step 2: Set Default Output Mode

In the `main()` function, add your command to the appropriate category:

```python
# AI commands: dialog by default (content to read)
ai_commands = ["summarize", "describe", "ask", "myaicommand"]

# Data commands: clipboard by default (content to use/paste)
data_commands = ["eval", "info", "selection", "mydatacommand"]

# Action commands: notification by default (just confirmation)
action_commands = ["open", "back", "click", "myactioncommand"]
```

### Step 3: Test the Command

```bash
# Test from Terminal first
open "inspekt://mycommand?param=value"

# Check logs
tail -f ~/inspekt_url_handler.log

# Test from GUI app (Raycast, Alfred, etc.)
```

### Step 4: Document the Command

Add to `/Users/roelvangils/inspekt_bridge/url_handler/test_links.html`:

```html
<div class="section">
    <h2>🆕 My Commands</h2>
    <a href="inspekt://mycommand?param=value">My Command</a>
    <a href="inspekt://mycommand?param=value&output=dialog">My Command (dialog)</a>
    <p class="description">Description of what your command does</p>
</div>
```

## Updating Output Defaults

### Change Default for Existing Command

Edit the command categorization in `inspekt_url_handler.py`:

```python
# Move 'outline' from data_commands to ai_commands
ai_commands = ["summarize", "describe", "ask", "outline"]  # Now shows in dialog
data_commands = ["eval", "info", "selection"]              # Removed outline
```

### Add New Output Mode

1. **Add mode constant:**
```python
if output_mode not in ["clipboard", "notification", "both", "dialog", "silent", "mynewmode"]:
    output_mode = "clipboard"
```

2. **Handle in `handle_output()` function:**
```python
def handle_output(result, command, output_mode):
    # ... existing code ...

    if output_mode == "mynewmode":
        # Implement your custom output handling
        my_custom_display(output)
```

## Environment Requirements

### Required Tools

All external tools must be installed and accessible via full path:

```bash
# Inspekt CLI (via pyenv)
/Users/roelvangils/.pyenv/shims/inspekt

# AI tool (via Homebrew)
/opt/homebrew/bin/mods

# HTML to Markdown converter (via Homebrew)
/opt/homebrew/bin/html2markdown
```

### PATH Issues

**Problem**: GUI apps (Raycast, Shortcuts, Alfred) don't have the same PATH as Terminal.

**Solution**: Always use full paths in subprocess calls:

```python
# ✓ Works everywhere
subprocess.run(["/opt/homebrew/bin/mods"], ...)

# ✗ Only works in Terminal
subprocess.run(["mods"], ...)
```

**Finding full paths:**
```bash
which inspekt     # /Users/roelvangils/.pyenv/shims/inspekt
which mods        # /opt/homebrew/bin/mods
which html2markdown  # /opt/homebrew/bin/html2markdown
```

## Debugging

### Log Files

```bash
# URL handler execution log
tail -f ~/inspekt_url_handler.log

# AppleScript app log
tail -f ~/inspekt_applescript.log

# Combined debugging
tail -f ~/inspekt_url_handler.log ~/inspekt_applescript.log
```

### Common Issues

**Issue**: "Unknown command" error
- **Cause**: Using `&` instead of `?` for first parameter
- **Fix**: `inspekt://info?output=both` (not `inspekt://info&output=both`)

**Issue**: Commands work from Terminal but not from Raycast
- **Cause**: PATH not set in GUI context, tools not found
- **Fix**: Use full paths in all subprocess calls

**Issue**: AI commands timeout
- **Cause**: Browser not connected or page has no content
- **Fix**: Ensure browser is open with connected extension

**Issue**: Dialog doesn't appear
- **Cause**: AppleScript security permissions
- **Fix**: System Preferences → Security → Allow Inspekt.app

### Manual Testing

```bash
# Test URL parsing
python3 -c "
from url_handler.inspekt_url_handler import parse_inspekt_url
print(parse_inspekt_url('inspekt://info?output=both'))
"

# Test command execution directly
/Users/roelvangils/.pyenv/shims/inspekt info

# Test from Terminal
open "inspekt://info?output=dialog"

# Test subprocess with full path
python3 -c "
import subprocess
result = subprocess.run(['/Users/roelvangils/.pyenv/shims/inspekt', 'info'],
                       capture_output=True, text=True)
print(result.stdout)
"
```

## Security Considerations

### URL Validation

The handler validates:
- Command is in allowed list
- Required parameters are present
- Output mode is valid

**No arbitrary code execution** - all commands are predefined and mapped to specific CLI tools.

### Sandboxing

Commands run with:
- User's permissions (not elevated)
- Same security context as Terminal
- Browser extension CSP bypass (intentional feature)

### Input Sanitization

- URL parameters are parsed via `urllib.parse.parse_qsl` (safe)
- Values are passed as subprocess arguments (not shell strings)
- AppleScript escapes quotes in dialog messages

## Use Cases

### Browser Bookmarklets

```javascript
// Create bookmark with this URL
inspekt://summarize?output=dialog
```

### Alfred Workflows

1. Create workflow
2. Add "Open URL" action
3. Set URL: `inspekt://eval?code={query}`

### Raycast Scripts

```bash
#!/bin/bash
# @raycast.schemaVersion 1
# @raycast.title Summarize Page
# @raycast.mode silent

open "inspekt://summarize"
```

### Shortcuts.app

1. New Shortcut
2. Add "Open URLs" action
3. URL: `inspekt://ask?q=What is this about?`

### AppleScript Automation

```applescript
tell application "System Events"
    open location "inspekt://eval?code=document.title"
end tell

-- Wait for result (copied to clipboard)
delay 1
set pageTitle to the clipboard
display dialog "Page title: " & pageTitle
```

### Terminal Aliases

```bash
# Add to ~/.zshrc or ~/.bashrc
alias isum='open "inspekt://summarize"'
alias iask='function _iask(){ open "inspekt://ask?q=$1"; }; _iask'
alias isel='open "inspekt://selection?format=markdown"'

# Usage:
# isum
# iask "What is the main point?"
# isel
```

## Performance

### Execution Times

Typical execution times from GUI apps:

- Navigation commands: ~100ms
- JavaScript eval: ~200ms
- Selection/info: ~300ms
- AI commands: 3-15 seconds (depends on content length)

### Optimization

- Uses `--raw` flag for CLI output (no formatting overhead)
- Caches AI responses (subsequent calls instant)
- Runs in background via AppleScript (`&` suffix)

## Future Enhancements

### Potential Additions

1. **Response callbacks**
   ```
   inspekt://summarize?callback=myapp://result
   ```

2. **Batch commands**
   ```
   inspekt://batch?commands=info,summarize,outline
   ```

3. **Custom output handlers**
   ```python
   output_handlers = {
       "clipboard": copy_to_clipboard,
       "notification": show_notification,
       "dialog": show_dialog,
       "custom": my_custom_handler
   }
   ```

4. **Command chaining**
   ```
   inspekt://eval?code=...&then=summarize
   ```

## References

- Main documentation: `/Users/roelvangils/inspekt_bridge/docs/url-scheme.md`
- Quick start: `/Users/roelvangils/inspekt_bridge/docs/url-scheme-quick-start.md`
- Troubleshooting: `/Users/roelvangils/inspekt_bridge/docs/troubleshooting.md`
- Test page: `/Users/roelvangils/inspekt_bridge/url_handler/test_links.html`
- Handler script: `/Users/roelvangils/inspekt_bridge/url_handler/inspekt_url_handler.py`

## Version History

- **v1.0** - Initial URL scheme implementation
- **v1.1** - Added smart output defaults
- **v1.2** - Fixed PATH issues for GUI apps (full paths)
- **v1.3** - Added AI commands (summarize, describe, ask)
- **v1.4** - Dialog output mode for long content
- **v1.5** - AI commands default to dialog mode

---

**Last updated**: 2025-11-13
**Maintainer**: Inspekt Development Team
