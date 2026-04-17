#!/bin/bash

# Zen Browser Bridge - Chrome Extension Build Script
# Creates a ZIP package for distribution and Chrome Web Store submission

set -e  # Exit on error

VERSION=$(grep '"version"' manifest.json | head -1 | sed 's/.*"version": "\(.*\)".*/\1/')
BUILD_DIR="build"
PACKAGE_NAME="zen-browser-bridge-chrome-${VERSION}"
ZIP_FILE="${BUILD_DIR}/${PACKAGE_NAME}.zip"

echo "🔨 Building Zen Browser Bridge Chrome Extension v${VERSION}"
echo ""

# Create build directory
mkdir -p "${BUILD_DIR}"

# Remove old build if exists
if [ -f "${ZIP_FILE}" ]; then
    echo "🗑️  Removing old build: ${ZIP_FILE}"
    rm "${ZIP_FILE}"
fi

echo "📦 Creating ZIP package…"

# Create ZIP with only necessary files
zip -r "${ZIP_FILE}" \
    manifest.json \
    background.js \
    content.js \
    popup/ \
    icons/ \
    -x "*.DS_Store" \
    -x "__MACOSX/*" \
    -x "*.git*" \
    -x "build/*" \
    -x "*.md" \
    -x "build.sh" \
    -x "node_modules/*" \
    -x "test/*" \
    -x ".vscode/*"

echo ""
echo "✅ Build complete!"
echo ""
echo "📄 Package: ${ZIP_FILE}"
echo "📊 Size: $(du -h "${ZIP_FILE}" | cut -f1)"
echo ""
echo "🧪 Next steps:"
echo "  1. Test the extension:"
echo "     - Open chrome://extensions/"
echo "     - Enable Developer mode"
echo "     - Click 'Load unpacked'"
echo "     - Select this directory"
echo ""
echo "  2. For Chrome Web Store submission:"
echo "     - Read CHROME_WEB_STORE.md"
echo "     - Upload ${ZIP_FILE} to Chrome Web Store Developer Dashboard"
echo ""
echo "🎉 Ready for distribution!"
