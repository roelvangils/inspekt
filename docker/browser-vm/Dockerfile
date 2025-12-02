# Inspekt Browser VM - Minimal Chromium + noVNC
# Optimized for fast boot and small image size
#
# Usage:
#   docker build -t inspekt-browser .
#   docker run -d -p 6080:6080 -e VNC_PASSWORD=secret inspekt-browser
#   Open http://localhost:6080 in your browser

FROM debian:bookworm-slim

LABEL maintainer="Inspekt" \
      description="Minimal Chromium browser accessible via noVNC" \
      version="1.0"

# Build arguments
ARG VNC_RESOLUTION=1280x720
ARG VNC_DEPTH=24

# Environment variables
ENV DEBIAN_FRONTEND=noninteractive \
    DISPLAY=:0 \
    VNC_PORT=5900 \
    NOVNC_PORT=6080 \
    VNC_RESOLUTION=${VNC_RESOLUTION} \
    VNC_DEPTH=${VNC_DEPTH} \
    VNC_PASSWORD="" \
    HOME_URL="about:blank" \
    LANG=en_US.UTF-8 \
    LC_ALL=C.UTF-8

# Install packages in a single layer to minimize image size
RUN set -ex && \
    # Update and install essential packages
    apt-get update && \
    apt-get install -y --no-install-recommends \
        # Init system
        tini \
        # Process manager
        supervisor \
        # X11 virtual framebuffer
        xvfb \
        # VNC server
        x11vnc \
        # noVNC (VNC client in browser)
        novnc \
        websockify \
        # Lightweight window manager
        openbox \
        # Browser
        chromium \
        # Fonts for proper rendering
        fonts-liberation \
        fonts-noto-color-emoji \
        # Utilities
        procps \
        curl \
    && \
    # Create noVNC symlink for easier access
    ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html && \
    # Clean up to reduce image size
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* && \
    # Create necessary directories
    mkdir -p /var/log/supervisor /root/.config/openbox

# Copy configuration files
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY openbox-autostart /root/.config/openbox/autostart
COPY entrypoint.sh /entrypoint.sh

# Make scripts executable
RUN chmod +x /entrypoint.sh /root/.config/openbox/autostart

# Expose noVNC port (VNC port stays internal)
EXPOSE 6080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:6080/ || exit 1

# Use tini as init system for proper signal handling
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/entrypoint.sh"]
