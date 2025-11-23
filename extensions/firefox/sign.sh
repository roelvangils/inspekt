#!/bin/bash
# Sign Firefox extension with Mozilla
# This creates a signed .xpi file that can be permanently installed

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Signing Inspekt Firefox Extension${NC}"
echo ""

# Load API credentials from .env file
if [ ! -f ".env" ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please create .env file with your Mozilla API credentials:"
    echo "  WEB_EXT_API_KEY=your-jwt-issuer"
    echo "  WEB_EXT_API_SECRET=your-jwt-secret"
    echo ""
    echo "Get credentials from: https://addons.mozilla.org/en-US/developers/addon/api/key/"
    exit 1
fi

# Source the .env file
set -a
source .env
set +a

# Validate credentials are set
if [ -z "$WEB_EXT_API_KEY" ] || [ -z "$WEB_EXT_API_SECRET" ]; then
    echo -e "${RED}Error: API credentials not set in .env file${NC}"
    echo "Please edit .env and add your credentials:"
    echo "  WEB_EXT_API_KEY=your-jwt-issuer"
    echo "  WEB_EXT_API_SECRET=your-jwt-secret"
    exit 1
fi

if [ "$WEB_EXT_API_KEY" = "your-jwt-issuer-here" ] || [ "$WEB_EXT_API_SECRET" = "your-jwt-secret-here" ]; then
    echo -e "${RED}Error: Please replace placeholder credentials in .env file${NC}"
    echo "Edit .env and add your actual Mozilla API credentials"
    exit 1
fi

# Get version from manifest
VERSION=$(grep '"version"' manifest.json | sed 's/.*"version": "\(.*\)".*/\1/')
echo -e "Version: ${GREEN}${VERSION}${NC}"
echo ""

# Create output directory for signed extension
mkdir -p "web-ext-artifacts"

echo -e "${YELLOW}Signing extension with Mozilla...${NC}"
echo "This may take a minute..."
echo ""

# Create temporary staging directory with all files
STAGING_DIR=$(mktemp -d)
echo "Staging files for signing in: $STAGING_DIR"

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

# Sign the extension from staging directory
# --channel=unlisted creates a signed .xpi without publishing to AMO
cd "$STAGING_DIR"
web-ext sign \
    --api-key="$WEB_EXT_API_KEY" \
    --api-secret="$WEB_EXT_API_SECRET" \
    --channel=unlisted \
    --artifacts-dir="$OLDPWD/web-ext-artifacts"
cd "$OLDPWD"

# Clean up staging directory
rm -rf "$STAGING_DIR"

echo ""
echo -e "${GREEN}✓${NC} Extension signed successfully!"
echo ""

# Find the signed file (web-ext names it with the full version and ID)
SIGNED_FILE=$(ls -t web-ext-artifacts/*.xpi 2>/dev/null | head -1)

if [ -n "$SIGNED_FILE" ]; then
    echo -e "Signed extension: ${BLUE}${SIGNED_FILE}${NC}"
    echo ""
    echo "Installation instructions for Zen Browser:"
    echo "  1. Open Zen Browser"
    echo "  2. Go to about:addons"
    echo "  3. Click the gear icon ⚙️  → 'Install Add-on From File...'"
    echo "  4. Select: ${SIGNED_FILE}"
    echo ""
    echo -e "${GREEN}The signed extension will be permanently installed!${NC}"
else
    echo -e "${YELLOW}Note: Signed file will be in web-ext-artifacts/ directory${NC}"
fi
