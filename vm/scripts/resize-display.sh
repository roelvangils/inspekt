#!/bin/bash
# resize-display.sh — Dynamically resize the X display via xrandr
# Usage: resize-display.sh WIDTH HEIGHT
# Returns JSON: {"ok": true, "changed": true/false, "resolution": "WxH"}

set -euo pipefail

DISPLAY="${DISPLAY:-:0}"
export DISPLAY

WIDTH="${1:-1920}"
HEIGHT="${2:-1080}"

# Clamp to valid range. The lower bound matches the JS / Python server
# floors (320×240) so mobile-viewport sizes (e.g. iPhone @ 375 px) actually
# resize the X display instead of being clamped up to 640 — which would
# letterbox the canvas and shrink the rendered fonts.
MIN_W=320; MIN_H=240; MAX_W=3840; MAX_H=2160

(( WIDTH  < MIN_W )) && WIDTH=$MIN_W
(( HEIGHT < MIN_H )) && HEIGHT=$MIN_H
(( WIDTH  > MAX_W )) && WIDTH=$MAX_W
(( HEIGHT > MAX_H )) && HEIGHT=$MAX_H

# Round to even numbers (X11 preference)
(( WIDTH  % 2 != 0 )) && (( WIDTH++ ))
(( HEIGHT % 2 != 0 )) && (( HEIGHT++ ))

RESOLUTION="${WIDTH}x${HEIGHT}"

# Check current resolution — skip if already matching
# xrandr shows mode names like "1440x900_60.00", so extract just the WxH part
CURRENT=$(xrandr --current 2>/dev/null | grep '\*' | awk '{print $1}' | sed 's/_.*//' || echo "")
if [ "$CURRENT" = "$RESOLUTION" ]; then
    echo "{\"ok\": true, \"changed\": false, \"resolution\": \"${RESOLUTION}\"}"
    exit 0
fi

# Generate modeline with cvt
MODELINE=$(cvt "$WIDTH" "$HEIGHT" 60 2>/dev/null | grep "Modeline" | sed 's/Modeline //')
if [ -z "$MODELINE" ]; then
    echo "{\"ok\": false, \"error\": \"cvt failed for ${RESOLUTION}\"}"
    exit 1
fi

# Extract mode name (first token, with quotes)
MODE_NAME=$(echo "$MODELINE" | awk '{print $1}' | tr -d '"')
MODE_PARAMS=$(echo "$MODELINE" | sed 's/^"[^"]*" *//')

# cvt rounds the width up to the nearest multiple of 8 (a CVT requirement
# for valid pixel clocks) — e.g. 375 → 376, 322 → 328. The mode-name embeds
# the ACTUAL width xrandr will apply, so re-extract it and use that for
# everything downstream. Otherwise Chromium gets sized to the unrounded
# request and ends up narrower than the X display, leaving a dead strip on
# the right and clipping the page in the noVNC canvas.
ACTUAL_WH=$(echo "$MODE_NAME" | sed 's/_.*//')
WIDTH=$(echo "$ACTUAL_WH" | cut -d'x' -f1)
HEIGHT=$(echo "$ACTUAL_WH" | cut -d'x' -f2)
RESOLUTION="${WIDTH}x${HEIGHT}"

# Find the output name (e.g., DUMMY0)
OUTPUT=$(xrandr --current 2>/dev/null | grep " connected" | awk '{print $1}' | head -1)
if [ -z "$OUTPUT" ]; then
    echo "{\"ok\": false, \"error\": \"No connected output found\"}"
    exit 1
fi

# Add the new mode (ignore error if it already exists)
xrandr --newmode "$MODE_NAME" $MODE_PARAMS 2>/dev/null || true
xrandr --addmode "$OUTPUT" "$MODE_NAME" 2>/dev/null || true

# Switch to the new mode
if ! xrandr --output "$OUTPUT" --mode "$MODE_NAME" 2>/dev/null; then
    echo "{\"ok\": false, \"error\": \"xrandr --output failed for ${RESOLUTION}\"}"
    exit 1
fi

# Resize the Chromium window to fill the new screen
sleep 0.2
CHROME_WIN=$(xdotool search --name "Chromium" 2>/dev/null | head -1 || true)
if [ -n "$CHROME_WIN" ]; then
    xdotool windowmove --sync "$CHROME_WIN" 0 0 2>/dev/null || true
    xdotool windowsize --sync "$CHROME_WIN" "$WIDTH" "$HEIGHT" 2>/dev/null || true
fi

# Persist current resolution for devtools-manager.sh
echo "${RESOLUTION}" > /tmp/inspekt_resolution

echo "{\"ok\": true, \"changed\": true, \"resolution\": \"${RESOLUTION}\"}"
