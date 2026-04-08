#!/bin/bash
# Inspekt Chromium Wrapper Script
# Launches Chromium with theme-aware flags based on /tmp/inspekt_theme

# Read theme preference (default to dark)
THEME=$(cat /tmp/inspekt_theme 2>/dev/null || echo "dark")

# Create Chrome preferences directory
CHROME_PROFILE="/root/.config/chromium/Default"
mkdir -p "$CHROME_PROFILE"

# Create preferences file with automatic downloads allowed
cat > "$CHROME_PROFILE/Preferences" << 'EOF'
{
    "profile": {
        "default_content_setting_values": {
            "automatic_downloads": 1
        },
        "content_settings": {
            "exceptions": {
                "automatic_downloads": {
                    "*,*": {
                        "setting": 1
                    }
                }
            }
        }
    },
    "download": {
        "prompt_for_download": false
    },
    "safebrowsing": {
        "enabled": false
    }
}
EOF

echo "[inspekt-chromium] Created Chrome preferences with automatic downloads allowed"

# Base Chrome arguments
CHROME_ARGS=(
    # Sandbox & Security (safe in isolated VM)
    --no-sandbox
    --test-type
    --disable-web-security
    --ignore-certificate-errors
    --disable-client-side-phishing-detection

    # Performance
    --disable-dev-shm-usage
    --disable-breakpad

    # Disable background services & telemetry
    --disable-background-networking
    --disable-sync
    --disable-domain-reliability
    --disable-component-update
    --disable-field-trial-config
    --metrics-recording-only

    # Disable popups & prompts
    --disable-infobars
    --disable-translate
    --disable-popup-blocking
    --disable-prompt-on-repost
    --no-first-run
    --no-default-browser-check
    --disable-default-apps

    # Allow automatic/multiple downloads without prompting
    --safebrowsing-disable-download-protection
    --allow-running-insecure-content

    # Disable notifications & network prompts
    --disable-notifications
    --disable-hang-monitor
    --deny-permission-prompts
    --disable-remote-playback-api
    --noerrdialogs
    --no-pings
    --password-store=basic

    # Fake camera & microphone so WebRTC/getUserMedia sites work in the VM.
    # Permission prompts are already suppressed by --deny-permission-prompts above.
    --use-fake-device-for-media-stream
    --use-fake-ui-for-media-stream

    # VNC stability: prevent Chromium from throttling when it thinks
    # windows are hidden (VNC can't signal window visibility)
    --disable-backgrounding-occluded-windows
    --disable-renderer-backgrounding
    --disable-background-timer-throttling

    # Accessibility: always build the a11y tree for testing tools
    --force-renderer-accessibility

    # Window & kiosk mode
    --kiosk
    --window-position=0,0
    --start-maximized

    # Automation
    --remote-debugging-port=9222
    --autoplay-policy=no-user-gesture-required

    # HTTP proxy (mitmproxy running locally for traffic interception)
    --proxy-server=http://127.0.0.1:8080
    --proxy-bypass-list="localhost,127.0.0.1,inspekt,<local>"

    # Disable various Chrome features (consolidated)
    # - Translate/TranslateUI: Disable translation popups
    # - MediaRouter/Cast*: Disable casting features
    # - AudioServiceOutOfProcess: Run audio in main process for container compatibility
    # - AutofillServerCommunication: Don't send form data to Google
    # - OptimizationGuide*: Don't download ML models or hints from Google
    # - InterestGroupStorage/BrowsingTopics: Disable Privacy Sandbox ad tracking
    # - PrivacySandboxSettings4: Disable Privacy Sandbox settings UI
    # - ChromeWhatsNewUI: Disable "What's new" promotional popup
    --disable-features=Translate,TranslateUI,MediaRouter,GlobalMediaControls,DialMediaRouteProvider,NetworkServiceInProcess,OutOfBlinkCors,Presentation,CastMediaRouteProvider,CastStreamingMediaRouteProvider,RemotePlayback,AudioServiceOutOfProcess,AutofillServerCommunication,OptimizationGuideModelDownloading,OptimizationHints,InterestGroupStorage,BrowsingTopics,PrivacySandboxSettings4,ChromeWhatsNewUI,CalculateNativeWinOcclusion

    # Extension
    --load-extension=/opt/inspekt/extensions/chrome

    # Use profile with automatic downloads enabled
    --user-data-dir=/root/.config/chromium
)

# Add dark mode flags if theme is dark
if [ "$THEME" = "dark" ]; then
    CHROME_ARGS+=(--force-dark-mode --enable-features=WebUIDarkMode)
fi

# ---------------------------------------------------------------
# Toggleable Chromium flags from inspekt-config.yaml
# Edit via: edit ~/.config/inspekt.yaml
# Apply by: Cmd+K → "Restart Browser"
# ---------------------------------------------------------------
CONFIG_FILE="/home/inspekt/.config/inspekt.yaml"
[ ! -f "$CONFIG_FILE" ] && CONFIG_FILE="/root/.config/inspekt.yaml"

# Helper: read a dotted key path from the YAML config (e.g. "browser.force-reduced-motion")
# Uses Python + PyYAML (already installed via mitmproxy).
# Returns: "true"/"false" for booleans (lowercase), raw value for strings/numbers, empty for null/missing.
_cfg() {
    /opt/inspekt/.venv/bin/python3 - "$CONFIG_FILE" "$1" 2>/dev/null <<'PYCFG'
import yaml, sys
try:
    config_file, key_path = sys.argv[1], sys.argv[2]
    with open(config_file) as f:
        d = yaml.safe_load(f)
    for k in key_path.split('.'):
        d = d.get(k) if isinstance(d, dict) else None
    if d is None or d == '':
        sys.exit(0)
    # Normalize booleans to lowercase "true"/"false"
    if isinstance(d, bool):
        print("true" if d else "false")
    # Validate numbers
    elif isinstance(d, (int, float)):
        print(d)
    else:
        print(d)
except yaml.YAMLError as e:
    print(f"[inspekt-chromium] WARNING: Invalid YAML config: {e}", file=sys.stderr)
except FileNotFoundError:
    pass  # No config file — use defaults
except Exception as e:
    print(f"[inspekt-chromium] WARNING: Config read error: {e}", file=sys.stderr)
PYCFG
}

if [ -f "$CONFIG_FILE" ]; then
    echo "[inspekt-chromium] Reading config from $CONFIG_FILE"

    # Accessibility: prefers-reduced-motion
    if [ "$(_cfg browser.force-reduced-motion)" = "true" ]; then
        CHROME_ARGS+=(--force-prefers-reduced-motion)
        echo "[inspekt-chromium] Enabled: force-reduced-motion"
    fi

    # Accessibility: prefers-contrast: more
    if [ "$(_cfg browser.force-high-contrast)" = "true" ]; then
        CHROME_ARGS+=(--force-prefers-contrast=more)
        echo "[inspekt-chromium] Enabled: force-high-contrast"
    fi

    # Dark mode forced on all web content
    if [ "$(_cfg browser.force-dark-content)" = "true" ]; then
        CHROME_ARGS+=(--enable-features=WebContentsForceDark)
        echo "[inspekt-chromium] Enabled: force-dark-content"
    fi

    # Custom DPI scaling — validate it's a positive number
    SCALE=$(_cfg browser.device-scale-factor)
    if [ -n "$SCALE" ] && echo "$SCALE" | grep -qE '^[0-9]+\.?[0-9]*$'; then
        CHROME_ARGS+=("--force-device-scale-factor=$SCALE")
        echo "[inspekt-chromium] Enabled: device-scale-factor=$SCALE"
    elif [ -n "$SCALE" ]; then
        echo "[inspekt-chromium] WARNING: Invalid device-scale-factor: $SCALE (expected number)"
    fi

    # TLS key logging for Wireshark HTTPS decryption
    if [ "$(_cfg browser.ssl-key-logging)" = "true" ]; then
        CHROME_ARGS+=(--ssl-key-log-file=/tmp/sslkeys.log)
        echo "[inspekt-chromium] Enabled: ssl-key-logging → /tmp/sslkeys.log"
    fi

    # Deterministic rendering (reproducible screenshots)
    if [ "$(_cfg browser.deterministic-rendering)" = "true" ]; then
        CHROME_ARGS+=(--deterministic-mode --run-all-compositor-stages-before-draw)
        echo "[inspekt-chromium] Enabled: deterministic-rendering"
    fi

    # Hide scrollbars (clean screenshots)
    if [ "$(_cfg browser.hide-scrollbars)" = "true" ]; then
        CHROME_ARGS+=(--hide-scrollbars)
        echo "[inspekt-chromium] Enabled: hide-scrollbars"
    fi

    # Homepage override
    HOMEPAGE=$(_cfg browser.homepage)
    if [ -n "$HOMEPAGE" ]; then
        HOME_URL="$HOMEPAGE"
    fi
fi

# Launch Chromium with the configured arguments
exec /usr/bin/chromium "${CHROME_ARGS[@]}" "${HOME_URL:-http://inspekt/status}"
