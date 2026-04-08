# Inspekt URL Scheme - Quick Start

## What is it?

The `inspekt://` URL scheme lets you trigger Inspekt commands from **anywhere on macOS**:
- Browser bookmarks and bookmarklets
- Alfred workflows
- Shortcuts.app automations
- Raycast scripts
- AppleScript
- Any app that can open URLs

## Prerequisites

1. **Servers running:**
   ```bash
   inspekt api start -d
   ```

2. **Browser open with extension:**
   - Open Chrome/Chromium
   - Navigate to any webpage
   - Extension automatically connects

3. **Verify connection:**
   ```bash
   inspekt info
   ```
   Should return page info without errors.

## Basic Usage

### Simple Commands
```
inspekt://info                    # Get page info (copies to clipboard)
inspekt://eval?code=document.title  # Execute JavaScript
inspekt://reload                  # Reload current page
```

### With Output Modes
```
inspekt://info?output=notification   # Show in notification only
inspekt://info?output=dialog         # Show in dialog popup
inspekt://info?output=both          # Clipboard + notification
inspekt://info?output=silent        # No output (errors still show)
```

### AI Commands
```
inspekt://summarize                 # Summarize article (to clipboard)
inspekt://summarize?output=dialog   # Summarize (show in dialog)
inspekt://describe                  # Describe page visually
inspekt://outline                   # Extract page outline
inspekt://ask?q=What is the main point?  # Ask a question
```

### Navigation
```
inspekt://open?url=https://example.com
inspekt://back
inspekt://forward
inspekt://reload
```

### Interaction
```
inspekt://click?selector=button
inspekt://type?text=Hello%20World&selector=input
inspekt://type?text=Test&speed=0    # Human-like typing
inspekt://paste?text=Quick%20text
```

### Content Extraction
```
inspekt://selection?format=text
inspekt://selection?format=html
inspekt://selection?format=markdown
```

### Cookies
```
inspekt://cookies?action=list
inspekt://cookies?action=get&name=sessionid
inspekt://cookies?action=set&name=test&value=hello
inspekt://cookies?action=delete&name=test
```

## Smart Defaults

**Data commands** (copy to clipboard by default):
- `eval`, `info`, `selection`, `cookies`, `screenshot`
- `summarize`, `describe`, `outline`, `ask`

**Action commands** (notification only by default):
- `open`, `back`, `forward`, `reload`, `click`, `type`, `paste`

Override with `?output=mode` parameter.

## Testing

Open the test page:
```bash
open /Users/roelvangils/inspekt_bridge/url_handler/test_links.html
```

Or try from Terminal:
```bash
open "inspekt://eval?code=document.title"
```

## Troubleshooting

### "No browser connected" error
1. Ensure servers are running: `inspekt api start -d`
2. Open Chrome with any webpage
3. Check DevTools console for: `[Inspekt] Connected via WebSocket`

### Commands not working
1. Verify URL format: `inspekt://command?param=value` (not `&` for first param)
2. Check logs: `tail -f ~/inspekt_url_handler.log`
3. Reload extension and refresh browser tab

### AI commands timeout
1. Ensure page has article content (not just navigation/UI)
2. Check `mods` is installed: `which mods`
3. Commands have 120s timeout - be patient

## Use Cases

### Bookmarklet
Create a browser bookmark with URL:
```
inspekt://summarize?output=dialog
```

### Alfred Workflow
1. Create new workflow
2. Add "Open URL" action
3. Set URL to `inspekt://eval?code={query}`

### Shortcuts.app
1. New Shortcut
2. Add "Open URLs" action
3. Set to `inspekt://info?output=notification`

### AppleScript
```applescript
tell application "System Events"
    open location "inspekt://eval?code=document.title"
end tell
```

## Next Steps

- See full documentation: `/Users/roelvangils/inspekt_bridge/docs/url-scheme.md`
- Troubleshooting guide: `/Users/roelvangils/inspekt_bridge/docs/troubleshooting.md`
- HTTP API docs: `/Users/roelvangils/inspekt_bridge/docs/api/http-api.md`
