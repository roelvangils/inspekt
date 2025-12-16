#!/bin/bash
set -e

echo "=== Inspekt Browser VM ==="
echo "Resolution: ${VNC_RESOLUTION}"
echo "noVNC Port: ${NOVNC_PORT}"
echo "Home URL: ${HOME_URL}"

# Add 'inspekt' hostname to /etc/hosts
echo "127.0.0.1 inspekt" >> /etc/hosts
echo "Added 'inspekt' to /etc/hosts"

# Set VM-specific bridge URL for inspekt CLI commands
# The VM runs its own isolated bridge on port 8767 (separate from host's 8765)
export INSPEKT_BRIDGE_URL="http://localhost:8767"
echo "INSPEKT_BRIDGE_URL=${INSPEKT_BRIDGE_URL}" >> /etc/environment
echo "Bridge URL: ${INSPEKT_BRIDGE_URL}"

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

# Start supervisor (manages all processes)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
