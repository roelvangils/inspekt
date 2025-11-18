#!/bin/bash
# Build script for Firefox extension - copies shared files

echo "Building Firefox extension..."

# Create shared directory in firefox extension
mkdir -p shared/core shared/popup

# Copy shared core files
cp ../shared/core/permissions.js shared/core/
cp ../shared/core/websocket-client.js shared/core/
cp ../shared/core/message-bridge.js shared/core/

# Copy shared popup files
cp ../shared/popup/popup-base.html shared/popup/
cp ../shared/popup/popup-base.css shared/popup/
cp ../shared/popup/popup-base.js shared/popup/

echo "✅ Shared files copied to firefox/shared/"
echo "You can now load the extension from firefox/ directory"
