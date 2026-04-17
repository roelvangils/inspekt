#!/bin/bash
# Build script for Firefox extension

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}Building Inspekt Firefox Extension${NC}"

# Get version from manifest.json
VERSION=$(grep '"version"' manifest.json | sed 's/.*"version": "\(.*\)".*/\1/')
echo -e "Version: ${GREEN}${VERSION}${NC}"

# Create build directory
BUILD_DIR="build"
mkdir -p "$BUILD_DIR"

# Package name
PACKAGE_NAME="inspekt-${VERSION}.zip"
XPI_NAME="inspekt-${VERSION}.xpi"

# Remove old packages
rm -f "$BUILD_DIR"/*.zip "$BUILD_DIR"/*.xpi

# Validate required files exist
echo "Validating files..."
REQUIRED_FILES=(
    "manifest.json"
    "background.js"
    "content.js"
    "../shared/popup/popup-base.html"
    "../shared/popup/popup-base.js"
    "../shared/popup/popup-base.css"
    "../shared/core/permissions.js"
    "../shared/core/websocket-client.js"
    "../shared/core/main-world-bridge.js"
    "../shared/modules/hidden-elements.js"
    "css/material-icons.css"
    "fonts/material-icons.woff2"
    "icons/icon-16.png"
    "icons/icon-48.png"
    "icons/icon-128.png"
)

MISSING_FILES=()
for file in "${REQUIRED_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        MISSING_FILES+=("$file")
    fi
done

if [ ${#MISSING_FILES[@]} -gt 0 ]; then
    echo -e "${RED}Error: Missing required files:${NC}"
    for file in "${MISSING_FILES[@]}"; do
        echo "  - $file"
    done
    exit 1
fi

echo -e "${GREEN}✓${NC} All required files present"
echo ""
echo "Packaging extension..."

# Create temporary staging directory
STAGING_DIR=$(mktemp -d)
echo "Staging files in: $STAGING_DIR"

# Copy Firefox-specific files
cp manifest.json "$STAGING_DIR/"
cp background.js "$STAGING_DIR/"
cp content.js "$STAGING_DIR/"
cp -r css "$STAGING_DIR/"
cp -r fonts "$STAGING_DIR/"
cp -r icons "$STAGING_DIR/"

# Copy shared files from parent directory
mkdir -p "$STAGING_DIR/shared"
cp -r ../shared/popup "$STAGING_DIR/shared/"
cp -r ../shared/core "$STAGING_DIR/shared/"
cp -r ../shared/modules "$STAGING_DIR/shared/"

# Create zip from staging directory
cd "$STAGING_DIR"
zip -r "$OLDPWD/$BUILD_DIR/$PACKAGE_NAME" . \
    -x "*.DS_Store" \
    -x "*/__pycache__/*"
cd "$OLDPWD"

# Clean up staging directory
rm -rf "$STAGING_DIR"

# Copy zip to .xpi for Firefox
cp "$BUILD_DIR/$PACKAGE_NAME" "$BUILD_DIR/$XPI_NAME"

echo -e "${GREEN}✓${NC} Extension packaged successfully!"
echo -e "  Zip: ${BLUE}$BUILD_DIR/$PACKAGE_NAME${NC}"
echo -e "  XPI: ${BLUE}$BUILD_DIR/$XPI_NAME${NC}"
echo ""
echo "Next steps for permanent installation:"
echo "  1. Get Firefox Add-on Developer account: https://addons.mozilla.org/developers/"
echo "  2. Sign the extension: https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/"
echo ""
echo "For self-distribution (unsigned):"
echo "  • Use Firefox Developer Edition or Nightly"
echo "  • Set xpinstall.signatures.required = false in about:config"
echo "  • Drag and drop the .xpi file into Firefox"
