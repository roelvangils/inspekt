# Inspekt Browser VM - Chromium + noVNC + Inspekt
# A complete virtual browser environment with Inspekt pre-installed
# Based on Alpine Linux for minimal image size (~1GB)
#
# Build from project root:
#   docker build -t inspekt-browser-vm -f docker/browser-vm/Dockerfile .
#   docker run -d --network host --shm-size=2g inspekt-browser-vm
#   Open http://localhost:6080/control.html in your browser

FROM alpine:3.21

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
    # X11 server with dummy video driver (supports xrandr for dynamic resolution)
    xorg-server \
    xf86-video-dummy \
    xrandr \
    libxcvt \
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
    # Clipboard (for inspekt --copy commands)
    xclip \
    # Python for Inspekt
    python3 \
    py3-pip \
    # WebSocket library (needed by control-server.py and terminal-server.py under system Python)
    py3-websockets \
    # Certificate management
    nss-tools \
    ca-certificates \
    # Utilities
    procps \
    curl \
    wget \
    bash \
    zsh \
    jq \
    # Git needed for pip to install Click from GitHub (until 8.3.2 is released)
    git \
    # Video recording for inspekt replay --video
    ffmpeg \
    # PNG optimization for inspekt screenshot --optimize
    oxipng \
    # Audio support
    pulseaudio \
    pulseaudio-utils \
    gstreamer \
    gstreamer-tools \
    gst-plugins-base \
    gst-plugins-good \
    gst-plugins-bad \
    socat \
    # Firewall for user network restrictions
    iptables \
    # websockify (noVNC installed separately from GitHub for latest version)
    websockify \
    # Node.js for lightningcss-cli (CSS optimization)
    nodejs \
    npm \
    # Runtime libraries for PyMuPDF (compiled from source on musl/aarch64)
    freetype harfbuzz jpeg openjpeg jbig2dec mupdf \
    && \
    # Create necessary directories
    mkdir -p /var/log/supervisor /root/.config/openbox /opt/inspekt /opt/certs /run/dbus

# Install noVNC 1.6.0 from GitHub (Alpine's package only has 1.4.0)
# 1.6.0 has keyboard modifier key fixes important for Mac users
RUN NOVNC_VERSION="1.6.0" && \
    wget -q "https://github.com/novnc/noVNC/archive/refs/tags/v${NOVNC_VERSION}.tar.gz" -O /tmp/novnc.tar.gz && \
    mkdir -p /usr/share/novnc && \
    tar xzf /tmp/novnc.tar.gz -C /usr/share/novnc --strip-components=1 && \
    ln -sf /usr/share/novnc/vnc.html /usr/share/novnc/index.html && \
    rm /tmp/novnc.tar.gz

# Install bore tunnel server (allows users to tunnel localhost to VM)
RUN BORE_VERSION="0.5.2" && \
    ARCH="$(uname -m)" && \
    if [ "$ARCH" = "aarch64" ]; then BORE_TARGET="aarch64-unknown-linux-musl"; \
    else BORE_TARGET="x86_64-unknown-linux-musl"; fi && \
    wget -q "https://github.com/ekzhang/bore/releases/download/v${BORE_VERSION}/bore-v${BORE_VERSION}-${BORE_TARGET}.tar.gz" \
        -O /tmp/bore.tar.gz && \
    tar xzf /tmp/bore.tar.gz -C /usr/local/bin/ bore && \
    chmod +x /usr/local/bin/bore && \
    rm /tmp/bore.tar.gz

# Install lightningcss-cli for CSS optimization (inspekt focused css)
RUN npm install -g lightningcss-cli prettier --no-audit --no-fund

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
# PyMuPDF has no pre-built musl/aarch64 wheel, so we need build tools to compile it.
# Build deps are installed and removed in the same layer to keep image small.
RUN chmod -R a+rX /opt/inspekt/extensions && \
    apk add --no-cache --virtual .build-deps \
        gcc g++ make swig \
        python3-dev musl-dev \
        freetype-dev harfbuzz-dev jpeg-dev openjpeg-dev jbig2dec-dev \
        mupdf-dev clang-dev && \
    ln -sf /usr/bin/gcc /usr/local/bin/cc && \
    ln -sf /usr/bin/g++ /usr/local/bin/c++ && \
    cd /opt/inspekt && \
    python3 -m venv .venv && \
    .venv/bin/pip install --no-cache-dir --upgrade pip && \
    .venv/bin/pip install --no-cache-dir -e . && \
    printf '#!/bin/zsh\nsource /opt/inspekt/.venv/bin/activate\n/opt/inspekt/.venv/bin/inspekt "$@"\n' > /usr/local/bin/inspekt && \
    chmod +x /usr/local/bin/inspekt && \
    rm -f /usr/local/bin/cc /usr/local/bin/c++ && \
    apk del .build-deps

# --- Restricted terminal user ---
# The terminal runs as this user to prevent system modification
RUN adduser -D -h /home/inspekt -s /bin/zsh inspekt && \
    mkdir -p /home/inspekt/Downloads && \
    chown -R inspekt:inspekt /home/inspekt

# 1) Inspekt command wrappers — one symlink per CLI command, all pointing to .wrapper
#    This gives tab completion and zero-prefix usage (e.g. "screenshot" instead of "inspekt screenshot")
#    The wrapper uses zsh (not /bin/sh) and includes a denylist for restricted commands.
RUN mkdir -p /opt/inspekt/commands && \
    printf '#!/bin/zsh\ncmd="$(basename "$0")"\ncase "$cmd" in\n    eval|exec|repl|plugin|yolo|domain|vm|do|mcp|autostart)\n        echo "This command is not available in the VM terminal." >&2\n        exit 1\n        ;;\n    *)\n        /opt/inspekt/.venv/bin/inspekt "$cmd" "$@"\n        ;;\nesac\n' \
        > /opt/inspekt/commands/.wrapper && \
    chmod +x /opt/inspekt/commands/.wrapper

# Generate symlinks at build time by reading the Click CLI
RUN /opt/inspekt/.venv/bin/python3 -c "\
from inspekt.app.cli import cli; \
from click import Context; \
import os; \
ctx = Context(cli); \
names = cli.list_commands(ctx); \
[os.symlink('.wrapper', f'/opt/inspekt/commands/{n}') for n in names]; \
print(f'Created {len(names)} command symlinks')"

# Remove symlinks for restricted commands (prevents tab completion showing them)
RUN for cmd in eval exec repl plugin yolo domain vm do mcp autostart; do \
        rm -f /opt/inspekt/commands/$cmd; \
    done

# 2) Allowed system utilities — curated symlinks
#    Removed dangerous utils: awk (system()), env (exec), less (!sh escape),
#    xargs (runs commands), chmod (makes scripts executable)
RUN mkdir -p /opt/inspekt/allowed-bin && \
    for cmd in \
        ls cat pwd mkdir touch rm cp mv \
        head tail more grep wc sort uniq tr \
        echo date file stat basename dirname realpath uname \
        clear whoami which tee \
        curl jq sed; do \
        for dir in /usr/bin /bin; do \
            [ -x "$dir/$cmd" ] && ln -sf "$dir/$cmd" /opt/inspekt/allowed-bin/$cmd && break; \
        done; \
    done && \
    ln -sf /usr/local/bin/download /opt/inspekt/allowed-bin/download && \
    ln -sf /usr/local/bin/inspekt /opt/inspekt/allowed-bin/inspekt && \
    printf '#!/bin/zsh\nPATH=/usr/bin:/usr/local/bin:$PATH /usr/local/bin/lightningcss "$@"\n' \
        > /opt/inspekt/allowed-bin/lightningcss && chmod +x /opt/inspekt/allowed-bin/lightningcss && \
    printf '#!/bin/zsh\nPATH=/usr/bin:/usr/local/bin:$PATH /usr/local/bin/prettier "$@"\n' \
        > /opt/inspekt/allowed-bin/prettier && chmod +x /opt/inspekt/allowed-bin/prettier

# Inspekt config must be copied before the permissions step that copies it to /home/inspekt
COPY docker/browser-vm/inspekt-config.json /root/.config/inspekt.json

# File permissions for restricted user
RUN chmod -R a+rX /opt/inspekt/.venv && \
    chmod -R a+rX /opt/inspekt/inspekt && \
    chmod -R a+rX /opt/inspekt/commands && \
    chmod -R a+rX /opt/inspekt/allowed-bin && \
    mkdir -p /home/inspekt/.config && \
    cp /root/.config/inspekt.json /home/inspekt/.config/inspekt.json && \
    chown -R inspekt:inspekt /home/inspekt

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
COPY docker/browser-vm/xorg.conf /etc/X11/xorg.conf
COPY docker/browser-vm/resize-display.sh /opt/resize-display.sh
COPY docker/browser-vm/download.sh /usr/local/bin/download
COPY docker/browser-vm/audio-proxy.sh /opt/audio-proxy.sh
COPY docker/browser-vm/pulse-config.pa /etc/pulse/default.pa

# Shell config with inspekt completion
COPY docker/browser-vm/bashrc /root/.bashrc
COPY docker/browser-vm/inputrc /root/.inputrc
COPY docker/browser-vm/zshrc /root/.zshrc

# Copy Python binary into venv (not symlink) so inspekt CLI works
# after chmod o-x on system Python. This must run BEFORE chmod.
RUN PYTHON_REAL=$(readlink -f /opt/inspekt/.venv/bin/python3) && \
    rm -f /opt/inspekt/.venv/bin/python3 /opt/inspekt/.venv/bin/python && \
    cp "$PYTHON_REAL" /opt/inspekt/.venv/bin/python3 && \
    ln -s python3 /opt/inspekt/.venv/bin/python && \
    chmod 755 /opt/inspekt/.venv/bin/python3

# Remove execute permission on interpreters/tools for non-root users.
# Root services (supervisord, bridge, API) are unaffected.
RUN chmod o-x /usr/bin/python3 /usr/bin/python3.12 2>/dev/null; \
    chmod o-x /usr/bin/npm 2>/dev/null; \
    chmod o-x /usr/bin/wget 2>/dev/null; \
    chmod o-x /usr/local/bin/mkcert 2>/dev/null; \
    # node and env stay executable — needed by prettier/lightningcss which
    # run as subprocess of inspekt CLI. Direct access is blocked by:
    #   - PATH restriction (node/env not in allowed-bin)
    #   - Shell function overrides (node() in zshrc returns error)
    #   - iptables (no outbound network even if node runs)
    # Ensure busybox stays world-executable — it provides all allowed-bin
    # commands (ls, cat, grep, etc.) and /bin/zsh completion helpers need it
    chmod 755 /bin/busybox 2>/dev/null; \
    true

# Restricted shell config in root-owned ZDOTDIR (prevents .zshenv bypass)
# ZDOTDIR tells zsh where to look for startup files. By pointing it to a
# root-owned directory, the user cannot create/modify .zshenv, .zshrc, etc.
RUN mkdir -p /etc/inspekt-shell
COPY docker/browser-vm/zshrc-restricted /etc/inspekt-shell/.zshrc
RUN touch /etc/inspekt-shell/.zshenv && \
    chown -R root:root /etc/inspekt-shell && \
    chmod 755 /etc/inspekt-shell && \
    chmod 644 /etc/inspekt-shell/.zshrc /etc/inspekt-shell/.zshenv

# Replace noVNC base CSS with custom minimal theme
COPY docker/browser-vm/novnc-base.css /usr/share/novnc/app/styles/base.css

# Customize noVNC HTML and set permissions
RUN chmod +x /entrypoint.sh /root/.config/openbox/autostart /opt/inspekt-chromium.sh \
              /opt/devtools-manager.sh /opt/terminal-server.py /usr/local/bin/download \
              /opt/audio-proxy.sh /opt/resize-display.sh && \
    # Remove noVNC logo from HTML
    sed -i 's|<h1 class="noVNC_logo" translate="no"><span>no</span><br>VNC</h1>||g' /usr/share/novnc/vnc.html && \
    sed -i 's|<div class="noVNC_logo" translate="no"><span>no</span>VNC</div>||g' /usr/share/novnc/vnc.html && \
    # Update page title
    sed -i 's|<title>noVNC</title>|<title>Inspekt Browser VM</title>|' /usr/share/novnc/vnc.html
    # Note: pointer/keyboard event interception previously injected into vnc.html
    # is no longer needed — control-panel.html embeds RFB directly (no iframe),
    # so all event handling happens via capture-phase listeners on the VNC container.

# Expose ports
EXPOSE 443 6080 6081 7835 8767 8768 8889 9222

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:6080/ || exit 1

# Use tini as init system
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/entrypoint.sh"]
