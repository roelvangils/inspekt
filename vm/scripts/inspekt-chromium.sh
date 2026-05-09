#!/bin/bash
# Inspekt Chromium Wrapper Script
# Launches Chromium with flags sourced from inspekt-config.yaml. Media-query
# overrides (dark mode, reduced motion, etc.) are applied at runtime via the
# control server's /emulate endpoints, not via startup flags.

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
    # EU/Belgium DMA: skip the "choose your search engine" screen on first run
    --disable-search-engine-choice-screen
    # Skip "Restore pages?" bubble after a crash — would block the kiosk
    --disable-session-crashed-bubble
    # Disable built-in component extensions (Hangouts, Cloud Print stubs)
    # that make background network calls
    --disable-component-extensions-with-background-pages
    # Disable all chrome://flags experiments — keeps every VM identical
    --no-experiments

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
    # Suppress the "Chrome is being debugged by extension" infobar
    # (we attach to CDP on 9222 from extensions / scripts)
    --silent-debugger-extension-api
    # Deterministic colour output regardless of host display profile —
    # makes screenshot comparisons reproducible across machines
    --force-color-profile=srgb

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
    # - OptimizationGuideOnDeviceModel: Disable on-device AI model downloads
    # - LensOverlay/LensStandalone: Disable Google Lens overlay features
    # - ReadAnything: Disable Reading Mode side panel
    # - SidePanelPinning: Disable side-panel pin controls
    # - DesktopPWAsLinkCapturing: Disable "Open in app?" PWA dialogs
    --disable-features=Translate,TranslateUI,MediaRouter,GlobalMediaControls,DialMediaRouteProvider,NetworkServiceInProcess,OutOfBlinkCors,Presentation,CastMediaRouteProvider,CastStreamingMediaRouteProvider,RemotePlayback,AudioServiceOutOfProcess,AutofillServerCommunication,OptimizationGuideModelDownloading,OptimizationHints,OptimizationGuideOnDeviceModel,InterestGroupStorage,BrowsingTopics,PrivacySandboxSettings4,ChromeWhatsNewUI,CalculateNativeWinOcclusion,LensOverlay,LensStandalone,ReadAnything,SidePanelPinning,DesktopPWAsLinkCapturing

    # Extension
    --load-extension=/opt/inspekt/extensions/chrome

    # Use profile with automatic downloads enabled
    --user-data-dir=/root/.config/chromium
)

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

# ---------------------------------------------------------------
# Chromium managed policies → /etc/chromium/policies/managed/inspekt.json
# Built from sensible defaults + browser.policies / browser.policies-extra
# in inspekt-config.yaml. Policies are read once at chromium startup, so
# this runs every time the wrapper launches.
# ---------------------------------------------------------------
POLICY_DIR=/etc/chromium/policies/managed
mkdir -p "$POLICY_DIR"
/opt/inspekt/.venv/bin/python3 - "$CONFIG_FILE" "$POLICY_DIR/inspekt.json" <<'PYPOL'
import json, sys
from pathlib import Path

cfg_path, out_path = sys.argv[1], sys.argv[2]

# kebab-case (YAML) → (CamelCase policy name, default, optional coercer)
KNOWN = {
    "translate-enabled":              ("TranslateEnabled",              False, None),
    "sync-disabled":                  ("SyncDisabled",                  True,  None),
    "password-manager-enabled":       ("PasswordManagerEnabled",        False, None),
    "autofill-address-enabled":       ("AutofillAddressEnabled",        False, None),
    "autofill-credit-card-enabled":   ("AutofillCreditCardEnabled",     False, None),
    "default-browser-setting-enabled":("DefaultBrowserSettingEnabled",  False, None),
    "promotional-tabs-enabled":       ("PromotionalTabsEnabled",        False, None),
    "metrics-reporting-enabled":      ("MetricsReportingEnabled",       False, None),
    "search-suggest-enabled":         ("SearchSuggestEnabled",          False, None),
    "safe-browsing-protection-level": ("SafeBrowsingProtectionLevel",   0,     int),
    # BrowserSignin: 0=disabled, 1=optional, 2=forced. Accept either int or
    # the strings false/optional/forced for the user-facing key.
    "browser-signin": (
        "BrowserSignin", 0,
        lambda v: (
            v if isinstance(v, int) and not isinstance(v, bool)
            else {"false": 0, "optional": 1, "forced": 2, False: 0, True: 1}.get(
                v.lower() if isinstance(v, str) else v, 0
            )
        ),
    ),
}

out = {pol_name: default for (pol_name, default, _) in KNOWN.values()}

try:
    import yaml  # PyYAML, already installed via mitmproxy venv
    cfg = yaml.safe_load(Path(cfg_path).read_text()) or {}
    browser = cfg.get("browser") or {}
    user = browser.get("policies") or {}
    for kebab, (pol_name, _default, coerce) in KNOWN.items():
        if kebab in user:
            v = user[kebab]
            out[pol_name] = coerce(v) if coerce else v
    for raw_name, raw_val in (browser.get("policies-extra") or {}).items():
        out[raw_name] = raw_val
except FileNotFoundError:
    pass  # No config file — defaults apply
except Exception as e:
    sys.stderr.write(f"[inspekt-chromium] policy generation warning: {e}\n")

Path(out_path).write_text(json.dumps(out, indent=2))
PYPOL
echo "[inspekt-chromium] Wrote managed policies → $POLICY_DIR/inspekt.json"

# Launch Chromium with the configured arguments
exec /usr/bin/chromium "${CHROME_ARGS[@]}" "${HOME_URL:-http://inspekt/status}"
