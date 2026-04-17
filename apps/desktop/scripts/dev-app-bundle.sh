#!/bin/bash
# Creates a minimal .app bundle around the debug binary so macOS TCC
# can find the Info.plist for privacy permission prompts (microphone,
# speech recognition). Required because `tauri dev` runs as a bare
# executable with no .app bundle.
#
# Also starts the Vite dev server (needed for the launcher/preferences
# pages which use WebviewUrl::App).

set -euo pipefail

APP_NAME="Inspekt Browser VM"
BUNDLE_ID="be.fronteers.inspekt-browser-vm"
BINARY="inspekt-browser-vm"

cd "$(dirname "$0")/.."

TARGET_DIR="src-tauri/target/debug"
APP_DIR="target/dev-bundle/${APP_NAME}.app"
CONTENTS="${APP_DIR}/Contents"

# Clean WKWebView cache (same as the regular dev script)
rm -rf ~/Library/WebKit/be.fronteers.inspekt-browser-vm ~/Library/Caches/be.fronteers.inspekt-browser-vm 2>/dev/null || true

# Start Vite dev server in background (serves preferences.html etc.)
echo "Starting Vite dev server…"
bun run vite --port 1421 &
VITE_PID=$!
trap "kill $VITE_PID 2>/dev/null" EXIT

# Wait for Vite to be ready
for i in $(seq 1 30); do
    if curl -s http://localhost:1421 > /dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

# Build the debug binary
echo "Building debug binary…"
cargo build --manifest-path src-tauri/Cargo.toml

# Create .app structure
mkdir -p "${CONTENTS}/MacOS"
mkdir -p "${CONTENTS}/Resources"

# Copy the binary (codesign requires regular files, not symlinks)
cp -f "${TARGET_DIR}/${BINARY}" "${CONTENTS}/MacOS/${BINARY}"

# Write Info.plist with bundle metadata + privacy keys
cat > "${CONTENTS}/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>CFBundleExecutable</key>
	<string>${BINARY}</string>
	<key>CFBundleIdentifier</key>
	<string>${BUNDLE_ID}</string>
	<key>CFBundleName</key>
	<string>${APP_NAME}</string>
	<key>CFBundlePackageType</key>
	<string>APPL</string>
	<key>CFBundleVersion</key>
	<string>0.1.0</string>
	<key>NSHighResolutionCapable</key>
	<true/>
	<key>NSMicrophoneUsageDescription</key>
	<string>Inspekt uses the microphone for voice-activated page navigation</string>
	<key>NSSpeechRecognitionUsageDescription</key>
	<string>Inspekt uses speech recognition to transcribe voice commands</string>
</dict>
</plist>
PLIST

# Ad-hoc codesign with entitlements (required on Apple Silicon + macOS 15+)
if [ -f "src-tauri/Entitlements.plist" ]; then
    codesign --force --sign - --entitlements src-tauri/Entitlements.plist "${APP_DIR}"
else
    codesign --force --sign - "${APP_DIR}"
fi

echo "Built: ${APP_DIR}"
echo "Opening app (Vite server running in background, Ctrl+C to stop)…"
open "${APP_DIR}"

# Keep script alive so Vite stays running until Ctrl+C
wait $VITE_PID
