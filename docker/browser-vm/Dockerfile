# Inspekt Browser VM - Chromium + noVNC + Inspekt
# A complete virtual browser environment with Inspekt pre-installed
# Based on Alpine Linux for minimal image size (~1GB)
#
# Build from project root:
#   docker build -t inspekt-browser-vm -f docker/browser-vm/Dockerfile .
#   docker run -d --network host --shm-size=2g inspekt-browser-vm
#   Open http://localhost:6080/control.html in your browser

FROM alpine:3.20

LABEL maintainer="Inspekt" \
      description="Chromium browser with Inspekt extension accessible via noVNC" \
      version="2.0"

# Build arguments
ARG VNC_RESOLUTION=1920x1080
ARG VNC_DEPTH=24

# Environment variables
ENV DISPLAY=:0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080 \
    VNC_RESOLUTION=${VNC_RESOLUTION} \
    VNC_DEPTH=${VNC_DEPTH} \
    HOME_URL="http://inspekt/status" \
    LANG=en_US.UTF-8 \
    # Isolated mode: bypass all domain/CSP checks (safe in isolated VM)
    INSPEKT_ISOLATED=1 \
    # VM-specific bridge URL (isolated from host's bridge on 8765)
    INSPEKT_BRIDGE_URL="http://localhost:8767"
    # Note: For AI features, pass THOTH_API_KEY at runtime:
    #   docker run -e THOTH_API_KEY=xxx ...

# Install all packages in a single layer
RUN apk add --no-cache \
    # Init system
    tini \
    # Process manager
    supervisor \
    # X11 virtual framebuffer
    xvfb \
    # VNC server
    x11vnc \
    # Lightweight window manager
    openbox \
    # Browser
    chromium \
    # Fonts for proper rendering
    font-noto \
    font-noto-emoji \
    ttf-liberation \
    # Window management tools
    xdotool \
    # Python for Inspekt
    python3 \
    py3-pip \
    # WebSocket library
    py3-websockets \
    # Certificate management
    nss-tools \
    ca-certificates \
    # Utilities
    procps \
    curl \
    wget \
    bash \
    jq \
    # Git needed for pip to install Click from GitHub (until 8.3.2 is released)
    git \
    # Video recording for inspekt replay --video
    ffmpeg \
    # Audio support
    pulseaudio \
    pulseaudio-utils \
    gstreamer \
    gstreamer-tools \
    gst-plugins-base \
    gst-plugins-good \
    gst-plugins-bad \
    socat \
    # noVNC and websockify
    novnc \
    && \
    # Create noVNC symlink
    ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html && \
    # Create necessary directories
    mkdir -p /var/log/supervisor /root/.config/openbox /opt/inspekt /opt/certs /run/dbus

# Install mkcert and generate certificates
RUN wget -q "https://dl.filippo.io/mkcert/latest?for=linux/amd64" -O /usr/local/bin/mkcert && \
    chmod +x /usr/local/bin/mkcert && \
    mkcert -install && \
    cd /opt/certs && \
    mkcert inspekt localhost 127.0.0.1 ::1 && \
    mv inspekt+3.pem cert.pem && \
    mv inspekt+3-key.pem key.pem && \
    cp "$(mkcert -CAROOT)/rootCA.pem" /usr/local/share/ca-certificates/mkcert-ca.crt && \
    update-ca-certificates && \
    mkdir -p /root/.pki/nssdb && \
    certutil -d sql:/root/.pki/nssdb -N --empty-password && \
    certutil -d sql:/root/.pki/nssdb -A -t "C,," -n "mkcert CA" -i "$(mkcert -CAROOT)/rootCA.pem"

# Copy Inspekt source code
COPY inspekt /opt/inspekt/inspekt
COPY extensions /opt/inspekt/extensions
COPY prompts /opt/inspekt/prompts
COPY pyproject.toml /opt/inspekt/

# Install Inspekt from source
RUN chmod -R a+rX /opt/inspekt/extensions && \
    cd /opt/inspekt && \
    python3 -m venv .venv && \
    .venv/bin/pip install --no-cache-dir --upgrade pip && \
    .venv/bin/pip install --no-cache-dir -e . && \
    printf '#!/bin/sh\nsource /opt/inspekt/.venv/bin/activate\nexec inspekt "$@"\n' > /usr/local/bin/inspekt && \
    chmod +x /usr/local/bin/inspekt

# Copy VM configuration files
COPY docker/browser-vm/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/browser-vm/openbox-autostart /root/.config/openbox/autostart
COPY docker/browser-vm/openbox-rc.xml /root/.config/openbox/rc.xml
COPY docker/browser-vm/entrypoint.sh /entrypoint.sh
COPY docker/browser-vm/control-server.py /opt/control-server.py
COPY docker/browser-vm/terminal-server.py /opt/terminal-server.py
COPY docker/browser-vm/control-panel.html /usr/share/novnc/control.html
COPY docker/browser-vm/fonts /usr/share/novnc/fonts
COPY docker/browser-vm/inspekt-chromium.sh /opt/inspekt-chromium.sh
COPY docker/browser-vm/devtools-manager.sh /opt/devtools-manager.sh
COPY docker/browser-vm/download.sh /usr/local/bin/download
COPY docker/browser-vm/audio-proxy.sh /opt/audio-proxy.sh
COPY docker/browser-vm/pulse-config.pa /etc/pulse/default.pa

# Inspekt config with nerdfont enabled (for nice icons in terminal)
COPY docker/browser-vm/inspekt-config.json /root/.config/inspekt.json

# Replace noVNC base CSS with custom minimal theme
COPY docker/browser-vm/novnc-base.css /usr/share/novnc/app/styles/base.css

# Customize noVNC HTML and set permissions
RUN chmod +x /entrypoint.sh /root/.config/openbox/autostart /opt/inspekt-chromium.sh \
              /opt/devtools-manager.sh /opt/terminal-server.py /usr/local/bin/download \
              /opt/audio-proxy.sh && \
    # Remove noVNC logo from HTML
    sed -i 's|<h1 class="noVNC_logo" translate="no"><span>no</span><br>VNC</h1>||g' /usr/share/novnc/vnc.html && \
    sed -i 's|<div class="noVNC_logo" translate="no"><span>no</span>VNC</div>||g' /usr/share/novnc/vnc.html && \
    # Update page title
    sed -i 's|<title>noVNC</title>|<title>Inspekt Browser VM</title>|' /usr/share/novnc/vnc.html

# Expose ports
EXPOSE 443 6080 6081 8767 8768 8889 9222

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:6080/ || exit 1

# Use tini as init system
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/entrypoint.sh"]
