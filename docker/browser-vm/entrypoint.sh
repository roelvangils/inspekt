#!/bin/bash
set -e

echo "=== Inspekt Browser VM ==="
echo "Resolution: ${VNC_RESOLUTION}"
echo "noVNC Port: ${NOVNC_PORT}"
echo "Home URL: ${HOME_URL}"

# Create inspekt.json so get_data_dir() uses ~/.config/inspekt/ (where the Docker volume is)
echo '{}' > /root/.config/inspekt.json
echo '{}' > /home/inspekt/.config/inspekt.json 2>/dev/null || true

# Add 'inspekt' hostname to /etc/hosts
echo "127.0.0.1 inspekt" >> /etc/hosts
echo "Added 'inspekt' to /etc/hosts"

# Set VM-specific bridge URL for inspekt CLI commands
# The VM runs its own isolated bridge on port 8767 (separate from host's 8765)
export INSPEKT_BRIDGE_URL="http://localhost:8767"
echo "INSPEKT_BRIDGE_URL=${INSPEKT_BRIDGE_URL}" >> /etc/environment
echo "Bridge URL: ${INSPEKT_BRIDGE_URL}"

# Write initial resolution for devtools-manager.sh and resize-display.sh
echo "${VNC_RESOLUTION}" > /tmp/inspekt_resolution

# Configure VNC password if set
if [ -n "${VNC_PASSWORD}" ]; then
    echo "VNC password: (protected)"
    mkdir -p /root/.vnc
    x11vnc -storepasswd "${VNC_PASSWORD}" /root/.vnc/passwd
    # Update supervisor config to use password
    sed -i "s/-nopw/-rfbauth \/root\/.vnc\/passwd/" /etc/supervisor/conf.d/supervisord.conf
else
    echo "VNC password: (none - open access)"
fi

echo "=========================="
echo "Connect via browser: http://localhost:${NOVNC_PORT}"
echo "=========================="

# Sync inspekt config to the terminal user's home (bind-mounted → user-editable copy).
# The bind-mounted root copy is read-only; we copy it to the inspekt user's home
# where it can be edited from the terminal.
if [ -f /root/.config/inspekt.yaml ]; then
    mkdir -p /home/inspekt/.config
    cp /root/.config/inspekt.yaml /home/inspekt/.config/inspekt.yaml
    chown inspekt:inspekt /home/inspekt/.config /home/inspekt/.config/inspekt.yaml
    chmod 644 /home/inspekt/.config/inspekt.yaml
fi

# Initialize mitmproxy config (proxy disabled by default, scripts loaded on demand)
cp /opt/proxy-scripts/default_config.json /tmp/mitmproxy_config.json

# Ensure shared temp files are writable by the restricted terminal user
# Use group permissions instead of world-writable to prevent prompt injection
touch /tmp/.inspekt_domain
chown root:inspekt /tmp/.inspekt_domain
chmod 664 /tmp/.inspekt_domain

# --- Tunnel secret for bore server ---
# Generate a random secret if not provided via environment
if [ -z "${BORE_SECRET}" ]; then
    export BORE_SECRET=$(head -c 16 /dev/urandom | base64 | tr -d '/+=' | head -c 22)
fi
echo "${BORE_SECRET}" > /tmp/.bore_secret
chmod 644 /tmp/.bore_secret
echo "Tunnel secret generated"

# --- Network restrictions for restricted terminal user ---
# Allow inspekt user to reach only required local services.
# Blocks: CDP (9222), all external/internet traffic.
INSPEKT_UID=$(id -u inspekt)

# Allow specific local services
iptables -A OUTPUT -m owner --uid-owner $INSPEKT_UID -o lo -p tcp --dport 80 -j ACCEPT     # inspekt API
iptables -A OUTPUT -m owner --uid-owner $INSPEKT_UID -o lo -p tcp --dport 8080 -j ACCEPT  # mitmproxy (for downloads)
iptables -A OUTPUT -m owner --uid-owner $INSPEKT_UID -o lo -p tcp --dport 8767 -j ACCEPT  # bridge WebSocket
iptables -A OUTPUT -m owner --uid-owner $INSPEKT_UID -o lo -p tcp --dport 8768 -j ACCEPT  # bridge HTTP
iptables -A OUTPUT -m owner --uid-owner $INSPEKT_UID -o lo -p tcp --dport 8888 -j ACCEPT  # control server

# Drop everything else (CDP on 9222, internet, other ports)
iptables -A OUTPUT -m owner --uid-owner $INSPEKT_UID -j DROP

echo "Network restrictions applied for inspekt user (uid=$INSPEKT_UID)"

# Sitemap cache: /var/cache/inspekt/sitemaps — accessible to all users
mkdir -p /var/cache/inspekt/sitemaps
chmod 777 /var/cache/inspekt/sitemaps
chmod 666 /var/cache/inspekt/sitemaps/*.json 2>/dev/null || true

# Clear Chromium caches on every start for privacy and to ensure
# the extension loads fresh code from the bind-mounted source files
CHROMIUM_PROFILE="/root/.config/chromium"
if [ -d "$CHROMIUM_PROFILE/Default" ]; then
    echo "Clearing Chromium caches..."
    rm -rf \
        "$CHROMIUM_PROFILE/Default/Service Worker" \
        "$CHROMIUM_PROFILE/Default/Extension Scripts" \
        "$CHROMIUM_PROFILE/Default/Extension Rules" \
        "$CHROMIUM_PROFILE/Default/Extension State" \
        "$CHROMIUM_PROFILE/Default/GPUCache" \
        "$CHROMIUM_PROFILE/Default/DawnGraphiteCache" \
        "$CHROMIUM_PROFILE/Default/DawnWebGPUCache" \
        "$CHROMIUM_PROFILE/Default/Local Storage" \
        "$CHROMIUM_PROFILE/Default/Session Storage" \
        "$CHROMIUM_PROFILE/Default/Sessions" \
        "$CHROMIUM_PROFILE/Default/blob_storage" \
        "$CHROMIUM_PROFILE/Default/Sync Data" \
        "$CHROMIUM_PROFILE/Default/Sync Extension Settings" \
        "$CHROMIUM_PROFILE/Default/WebStorage" \
        "$CHROMIUM_PROFILE/Default/Shared Dictionary" \
        "$CHROMIUM_PROFILE/Default/Cookies" \
        "$CHROMIUM_PROFILE/Default/Cookies-journal" \
        "$CHROMIUM_PROFILE/Default/History" \
        "$CHROMIUM_PROFILE/Default/History-journal" \
        "$CHROMIUM_PROFILE/Default/Visited Links" \
        "$CHROMIUM_PROFILE/Default/Web Data" \
        "$CHROMIUM_PROFILE/Default/Web Data-journal" \
        "$CHROMIUM_PROFILE/Default/Login Data" \
        "$CHROMIUM_PROFILE/Default/Login Data-journal" \
        "$CHROMIUM_PROFILE/Default/Favicons" \
        "$CHROMIUM_PROFILE/Default/Favicons-journal" \
        "$CHROMIUM_PROFILE/Default/Network Action Predictor" \
        "$CHROMIUM_PROFILE/Default/QuotaManager" \
        "$CHROMIUM_PROFILE/Default/QuotaManager-journal" \
        "$CHROMIUM_PROFILE/Default/shared_proto_db" \
        "$CHROMIUM_PROFILE/Crash Reports" \
        "$CHROMIUM_PROFILE/GraphiteDawnCache" \
        "$CHROMIUM_PROFILE/GrShaderCache" \
        "$CHROMIUM_PROFILE/ShaderCache" \
        2>/dev/null || true
    echo "Chromium caches cleared"
fi

# Start supervisor (manages all processes)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
