#!/bin/bash
set -e

echo "=== Inspekt Browser VM ==="
echo "Resolution: ${VNC_RESOLUTION}"
echo "noVNC Port: ${NOVNC_PORT}"
echo "Home URL: ${HOME_URL}"

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
