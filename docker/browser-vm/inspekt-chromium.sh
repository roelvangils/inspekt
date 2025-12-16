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

    # Window & kiosk mode
    --kiosk
    --window-position=0,0
    --window-size=1920,1080

    # Automation
    --remote-debugging-port=9222
    --autoplay-policy=no-user-gesture-required

    # Disable various Chrome features (consolidated)
    # - Translate/TranslateUI: Disable translation popups
    # - MediaRouter/Cast*: Disable casting features
    # - AudioServiceOutOfProcess: Run audio in main process for container compatibility
    # - AutofillServerCommunication: Don't send form data to Google
    # - OptimizationGuide*: Don't download ML models or hints from Google
    # - InterestGroupStorage/BrowsingTopics: Disable Privacy Sandbox ad tracking
    # - PrivacySandboxSettings4: Disable Privacy Sandbox settings UI
    # - ChromeWhatsNewUI: Disable "What's new" promotional popup
    --disable-features=Translate,TranslateUI,MediaRouter,GlobalMediaControls,DialMediaRouteProvider,NetworkServiceInProcess,OutOfBlinkCors,Presentation,CastMediaRouteProvider,CastStreamingMediaRouteProvider,RemotePlayback,AudioServiceOutOfProcess,AutofillServerCommunication,OptimizationGuideModelDownloading,OptimizationHints,InterestGroupStorage,BrowsingTopics,PrivacySandboxSettings4,ChromeWhatsNewUI

    # Extension
    --load-extension=/opt/inspekt/extensions/chrome

    # Use profile with automatic downloads enabled
    --user-data-dir=/root/.config/chromium
)

# Add dark mode flags if theme is dark
if [ "$THEME" = "dark" ]; then
    CHROME_ARGS+=(--force-dark-mode --enable-features=WebUIDarkMode)
fi

# Launch Chromium with the configured arguments
exec /usr/bin/chromium "${CHROME_ARGS[@]}" "${HOME_URL:-https://example.com}"
