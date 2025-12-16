#!/bin/bash
# DevTools Window Manager for Inspekt Browser VM
# Controls opening, closing, and tiling of DevTools window

DISPLAY=${DISPLAY:-:0}
CDP_PORT=9222
DEVTOOLS_PID_FILE="/tmp/devtools_pid"

# Screen dimensions (1920x1080)
SCREEN_WIDTH=1920
SCREEN_HEIGHT=1080

# Default split: 60% browser, 40% DevTools
MAIN_WIDTH=$((SCREEN_WIDTH * 60 / 100))
DEVTOOLS_WIDTH=$((SCREEN_WIDTH * 40 / 100))

get_devtools_url() {
    # Get the page ID for the first page tab and construct local DevTools URL
    local json=$(curl -s "http://localhost:${CDP_PORT}/json" 2>/dev/null)
    local page_id=$(echo "$json" | python3 -c "
import sys, json
try:
    tabs = json.load(sys.stdin)
    for tab in tabs:
        if tab.get('type') == 'page' and not tab.get('url', '').startswith('chrome://'):
            page_id = tab.get('id', '')
            if page_id:
                print(page_id)
                break
except:
    pass
" 2>/dev/null)

    if [ -n "$page_id" ]; then
        # Use local DevTools frontend bundled with Chromium
        echo "http://localhost:${CDP_PORT}/devtools/inspector.html?ws=localhost:${CDP_PORT}/devtools/page/${page_id}"
    fi
}

find_main_window() {
    # Find main Chromium window (exclude DevTools)
    # Look for windows with "Chromium" in title but not "DevTools"
    local wins=$(xdotool search --name "." 2>/dev/null)
    for win in $wins; do
        local name=$(xdotool getwindowname "$win" 2>/dev/null)
        if [[ "$name" == *"Chromium"* ]] && [[ "$name" != *"DevTools"* ]] && [[ "$name" != *"chrome-devtools"* ]]; then
            echo "$win"
            return 0
        fi
    done
    return 1
}

find_devtools_window() {
    # Find DevTools window
    local wins=$(xdotool search --name "DevTools" 2>/dev/null)
    if [ -n "$wins" ]; then
        echo "$wins" | head -1
        return 0
    fi

    # Also try searching for chrome-devtools URL
    wins=$(xdotool search --name "chrome-devtools" 2>/dev/null)
    if [ -n "$wins" ]; then
        echo "$wins" | head -1
        return 0
    fi

    return 1
}

tile_windows() {
    # Tile main browser (left) and DevTools (right)
    local main_win=$(find_main_window)
    local devtools_win=$(find_devtools_window)

    if [ -n "$main_win" ]; then
        # Unmaximize first, then resize and position
        wmctrl -i -r "$main_win" -b remove,maximized_vert,maximized_horz 2>/dev/null
        xdotool windowmove --sync "$main_win" 0 0
        xdotool windowsize --sync "$main_win" "$MAIN_WIDTH" "$SCREEN_HEIGHT"
        echo "Main browser tiled: 0,0 ${MAIN_WIDTH}x${SCREEN_HEIGHT}"
    fi

    if [ -n "$devtools_win" ]; then
        wmctrl -i -r "$devtools_win" -b remove,maximized_vert,maximized_horz 2>/dev/null
        xdotool windowmove --sync "$devtools_win" "$MAIN_WIDTH" 0
        xdotool windowsize --sync "$devtools_win" "$DEVTOOLS_WIDTH" "$SCREEN_HEIGHT"
        echo "DevTools tiled: ${MAIN_WIDTH},0 ${DEVTOOLS_WIDTH}x${SCREEN_HEIGHT}"
    fi
}

maximize_main() {
    # Maximize main browser window (when DevTools is closed)
    local main_win=$(find_main_window)
    if [ -n "$main_win" ]; then
        xdotool windowmove --sync "$main_win" 0 0
        xdotool windowsize --sync "$main_win" "$SCREEN_WIDTH" "$SCREEN_HEIGHT"
        wmctrl -i -r "$main_win" -b add,maximized_vert,maximized_horz 2>/dev/null
        echo "Main browser maximized"
    fi
}

is_devtools_open() {
    # Check if DevTools window exists
    if [ -f "$DEVTOOLS_PID_FILE" ]; then
        local pid=$(cat "$DEVTOOLS_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi

    # Also check by window name
    local devtools_win=$(find_devtools_window)
    if [ -n "$devtools_win" ]; then
        return 0
    fi

    return 1
}

open_devtools() {
    local url=$(get_devtools_url)
    if [ -z "$url" ]; then
        echo "Error: No debuggable tab found"
        exit 1
    fi

    # Check if DevTools is already open
    if is_devtools_open; then
        echo "DevTools already open, tiling windows"
        tile_windows
        exit 0
    fi

    echo "Opening DevTools: $url"

    # Open DevTools in new Chromium window (app mode for minimal chrome)
    /usr/bin/chromium \
        --no-sandbox \
        --disable-gpu \
        --disable-dev-shm-usage \
        --no-first-run \
        --app="$url" \
        --window-position="$MAIN_WIDTH",0 \
        --window-size="$DEVTOOLS_WIDTH","$SCREEN_HEIGHT" &

    local pid=$!
    echo "$pid" > "$DEVTOOLS_PID_FILE"

    # Wait for window to appear
    sleep 2

    # Tile windows
    tile_windows

    echo "DevTools opened (PID: $pid)"
}

close_devtools() {
    local closed=false

    # Kill by PID file
    if [ -f "$DEVTOOLS_PID_FILE" ]; then
        local pid=$(cat "$DEVTOOLS_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            closed=true
            echo "Closed DevTools process (PID: $pid)"
        fi
        rm -f "$DEVTOOLS_PID_FILE"
    fi

    # Also close by window name as fallback
    local devtools_win=$(find_devtools_window)
    if [ -n "$devtools_win" ]; then
        xdotool windowclose "$devtools_win" 2>/dev/null
        closed=true
        echo "Closed DevTools window"
    fi

    # Wait a moment for window to close
    sleep 0.5

    # Maximize main browser
    maximize_main

    if [ "$closed" = true ]; then
        echo "DevTools closed"
    else
        echo "DevTools was not open"
    fi
}

toggle_devtools() {
    if is_devtools_open; then
        close_devtools
    else
        open_devtools
    fi
}

status_devtools() {
    if is_devtools_open; then
        local pid=""
        if [ -f "$DEVTOOLS_PID_FILE" ]; then
            pid=$(cat "$DEVTOOLS_PID_FILE")
        fi
        echo "{\"open\": true, \"pid\": ${pid:-null}}"
    else
        echo "{\"open\": false}"
    fi
}

case "$1" in
    open)
        open_devtools
        ;;
    close)
        close_devtools
        ;;
    toggle)
        toggle_devtools
        ;;
    tile)
        tile_windows
        ;;
    maximize)
        maximize_main
        ;;
    status)
        status_devtools
        ;;
    *)
        echo "Usage: $0 {open|close|toggle|tile|maximize|status}"
        exit 1
        ;;
esac
