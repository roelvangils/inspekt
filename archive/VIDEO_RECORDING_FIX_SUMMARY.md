# Video Recording Fixes Summary

## Changes Made

### 1. FFprobe Sanity Checks (✅ Complete)

**File:** `inspekt/services/ffmpeg_utils.py`
- Added `get_ffprobe_path()` function
- Added `probe_video()` function to extract video metadata (width, height, duration, fps, codec, file_size)

**File:** `inspekt/app/cli/replay.py`
- Added import for `probe_video`
- After video encoding, displays video info: `Video info: 1920×894 · 0.6s · 18 fps · h264`

### 2. File Size Formatting (✅ Complete)

**File:** `inspekt/app/cli/replay.py` (lines 3177-3181)
- Small files (<1 MB) now show KB instead of "0.0 MB"
- Example: "24.0 KB" instead of "0.0 MB"

### 3. Frame Capture Timing (✅ Complete)

**File:** `inspekt/services/screencast.py`
- Modified `stop()` method:
  - Now stops CDP screencast FIRST
  - Waits 0.3s for frames in transit
  - Collects frames with 3 retry attempts

**File:** `inspekt/bridge_ws.py`
- `/screencast/stop` endpoint no longer clears the frame buffer
- Frames are cleared when retrieved via `/screencast/frames`

### 4. Race Condition Fix (⚠️ Requires Extension Reload)

**File:** `extensions/chrome/background.js`
- Fixed race condition: `screencastState` is now set BEFORE calling `Page.startScreencast`
- Added debug logging to track frame events

## Testing Instructions

### Step 1: Reload Chrome Extension

1. Open Chrome and go to `chrome://extensions/`
2. Find the "Inspekt" extension
3. Click the reload button (↻) to reload the extension
4. Check that it reloaded successfully

### Step 2: Test Video Recording

```bash
inspekt replay example.yaml --video --verbose
```

### Step 3: Check Extension Console

1. On `chrome://extensions/`, click "background page" or "service worker" under Inspekt
2. Look for console logs like:
   - `[Inspekt] Screencast started at ~10 FPS`
   - `[Inspekt] screencastFrame received, active: true, sourceTab: X, expectedTab: X`
   - `[Inspekt] First screencast frame metadata: {...}`

### Step 4: If No Frames

If you still see "No frames captured":

1. Check if the debug logs appear in the extension console
2. If no `screencastFrame received` logs appear, CDP isn't generating events
3. If logs show "state mismatch", the tabId might not be matching
4. If frames are POSTing but not showing up, check the bridge server

### Bridge Server Status

Check if frames are arriving:
```bash
curl -s http://127.0.0.1:8765/screencast/status
```

## Files Changed

- `inspekt/services/ffmpeg_utils.py` - Added ffprobe functions
- `inspekt/services/screencast.py` - Fixed stop timing
- `inspekt/bridge_ws.py` - Fixed buffer clearing
- `inspekt/app/cli/replay.py` - Added ffprobe display, KB formatting
- `extensions/chrome/background.js` - Fixed race condition, added debug logging

## Debug Logging Added

The extension now logs:
- When `Page.screencastFrame` events are received
- Whether state matches (active + tabId)
- Frame POST success/failure

Remove these logs after debugging by editing `background.js` lines 2776-2810.
