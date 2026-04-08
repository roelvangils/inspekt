# Inspekt URL Scheme (`inspekt://`)

The `inspekt://` URL scheme allows you to trigger Inspekt commands from anywhere on your Mac - browser links, Shortcuts.app, Alfred, Raycast, or any application that supports URL schemes.

## Quick Start

```bash
# Install the URL handler
./url_handler/install.sh

# Test it
open "inspekt://info"
```

## How It Works

When you open an `inspekt://` URL, macOS:
1. Recognizes the `inspekt://` protocol
2. Launches the Inspekt URL handler app
3. Parses the URL and executes the command
4. Returns the result via clipboard, notification, or both

## URL Format

```
inspekt://<command>?<param1>=<value1>&<param2>=<value2>&output=<mode>
```

### Output Modes

Control where the command output goes with the `output` parameter:

| Mode | Description | Use Case |
|------|-------------|----------|
| `clipboard` (default) | Copy to clipboard + brief notification | Automation, workflows |
| `notification` | Show in macOS notification | Quick feedback |
| `both` | Clipboard + full notification | Maximum visibility |
| `silent` | No output (errors still notify) | Background tasks |

**Examples:**
```
inspekt://eval?code=document.title&output=clipboard
inspekt://selection?format=markdown&output=notification
inspekt://info?output=both
```

## Available Commands

### 📄 Page Information

```
inspekt://info
```
Get current page info (URL, title, dimensions, etc.)

---

### 🧭 Navigation

**Open URL:**
```
inspekt://open?url=https://example.com
```

**Navigate:**
```
inspekt://back
inspekt://forward
inspekt://reload
```

---

### ⚙️ Execute JavaScript

```
inspekt://eval?code=<javascript>
```

**Examples:**
```
inspekt://eval?code=document.title
inspekt://eval?code=document.querySelectorAll('a').length
inspekt://eval?code=window.scrollTo(0,0)
```

**Note:** URL-encode special characters:
- Space: `%20`
- Quotes: `%22`
- Ampersand: `%26`

---

### ✂️ Text Selection

Get selected text in different formats:

```
inspekt://selection?format=text
inspekt://selection?format=html
inspekt://selection?format=markdown
```

**Tip:** Perfect for creating "Copy as Markdown" bookmarklets!

---

### 🖱️ Interaction

**Click element:**
```
inspekt://click?selector=button%23submit
inspekt://click?selector=.primary-button
```

**Type text:**
```
inspekt://type?text=Hello%20World&selector=input
inspekt://type?text=Search%20query&speed=0
```

**Paste text:**
```
inspekt://paste?text=Quick%20paste&selector=textarea
```

---

### 🔍 Inspection

**Inspect element:**
```
inspekt://inspect?selector=h1
inspekt://inspect?selector=%23main-content
```

**Screenshot:**
```
inspekt://screenshot?selector=body
inspekt://screenshot?selector=.hero-section&output=/path/to/image.png
```

---

### 🍪 Cookies

**List all cookies:**
```
inspekt://cookies?action=list
```

**Get specific cookie:**
```
inspekt://cookies?action=get&name=session_id
```

**Set cookie:**
```
inspekt://cookies?action=set&name=theme&value=dark
inspekt://cookies?action=set&name=token&value=abc123&max_age=3600
```

**Delete cookie:**
```
inspekt://cookies?action=delete&name=session_id
```

---

## Usage Examples

### 1. Bookmarklets

Create browser bookmarks that trigger Inspekt:

```javascript
// Copy selection as markdown
javascript:window.location='inspekt://selection?format=markdown'

// Get page title
javascript:window.location='inspekt://eval?code=document.title'

// Quick screenshot
javascript:window.location='inspekt://screenshot?selector=body'
```

### 2. Shortcuts.app

Create iOS/macOS shortcuts:

1. Add "Open URL" action
2. Enter `inspekt://eval?code=document.title&output=clipboard`
3. Add "Get Clipboard" action to use the result

**Example Shortcut:**
```
Open URL: inspekt://selection?format=markdown&output=clipboard
Get Clipboard
Show Result
```

### 3. Alfred Workflows

Create custom Alfred triggers:

```applescript
# Alfred Script Filter
on alfred_script(q)
    do shell script "open 'inspekt://eval?code=" & q & "'"
end alfred_script
```

### 4. Raycast Script Commands

```bash
#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Get Page Title
# @raycast.mode silent

open "inspekt://eval?code=document.title&output=clipboard"
```

### 5. AppleScript

```applescript
-- Execute Inspekt command
tell application "System Events"
    open location "inspekt://info"
end tell

-- Wait and get result from clipboard
delay 1
set pageInfo to the clipboard
```

### 6. Shell Scripts

```bash
#!/bin/bash
# Extract page title and save to file

open "inspekt://eval?code=document.title&output=clipboard"
sleep 1
pbpaste > page_title.txt
```

---

## URL Encoding Reference

Common characters that need encoding:

| Character | Encoded | Example |
|-----------|---------|---------|
| Space | `%20` | `Hello%20World` |
| `"` | `%22` | `%22quoted%22` |
| `#` | `%23` | `button%23submit` |
| `&` | `%26` | `foo%26bar` |
| `=` | `%3D` | `a%3Db` |
| `?` | `%3F` | `what%3F` |

**Quick encode in shell:**
```bash
# Python one-liner
python3 -c "import urllib.parse; print(urllib.parse.quote('your text here'))"

# Or use an online encoder
```

---

## Advanced Examples

### Copy All Links as Markdown

```javascript
javascript:window.location='inspekt://eval?code=' +
  encodeURIComponent('Array.from(document.querySelectorAll("a")).map(a => `[${a.textContent.trim()}](${a.href})`).join("\\n")')
```

### Save Screenshot to Desktop

```
inspekt://screenshot?selector=body&output=~/Desktop/screenshot.png
```

### Monitor Cookie Changes

```bash
#!/bin/bash
while true; do
  open "inspekt://cookies?action=list&output=clipboard"
  sleep 1
  pbpaste > cookies_$(date +%s).json
  sleep 60
done
```

### Extract Data for Analysis

```applescript
-- Get page data and process it
tell application "System Events"
    open location "inspekt://eval?code=document.body.innerText&output=clipboard"
    delay 1
end tell

set pageText to the clipboard
-- Process pageText as needed
```

---

## Installation

### Automatic Installation

```bash
cd /Users/roelvangils/inspekt_bridge
./url_handler/install.sh
```

### Manual Installation

1. **Copy handler script:**
   ```bash
   cp url_handler/inspekt_url_handler.py /usr/local/bin/
   chmod +x /usr/local/bin/inspekt_url_handler.py
   ```

2. **Create app bundle:**
   ```bash
   sudo ./url_handler/install.sh
   ```

3. **Register protocol:**
   ```bash
   /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f /Applications/Inspekt.app
   ```

4. **Test:**
   ```bash
   open "inspekt://info"
   ```

---

## Troubleshooting

### URL handler not working

```bash
# Re-register the protocol
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f /Applications/Inspekt.app

# Check if registered
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -dump | grep inspekt
```

### No output received

1. Check output mode: Add `&output=both` to see both notification and clipboard
2. Check notifications are enabled for Terminal/script runner
3. Try running manually: `/Applications/Inspekt.app/Contents/MacOS/Inspekt "inspekt://info"`

### Commands not executing

1. Make sure bridge server is running: `inspekt server status`
2. Start servers if needed: `inspekt api start -d`
3. Test CLI directly: `inspekt info`

---

## Security Considerations

- URL handlers execute with your user permissions
- Be cautious with untrusted `inspekt://` links (they can run JavaScript in your browser)
- Consider implementing URL whitelisting for production use
- The handler runs locally and doesn't send data anywhere

---

## See Also

- [HTTP API Documentation](api/http-api.md)
- [CLI vs API Guide](guide/cli-vs-api.md)
- [Inspekt CLI Documentation](index.md)
