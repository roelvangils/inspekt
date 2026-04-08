# Inspekt Browser VM - Chromium + noVNC + Inspekt
# A complete virtual browser environment with Inspekt pre-installed
# Based on Alpine Linux for minimal image size
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
    # PTY allocation (needed by gum for interactive TUI in non-login terminals)
    util-linux \
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
    # Terminal editors (for `edit --nano` flag)
    nano \
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

# Install micro editor (modern terminal editor with intuitive keybindings)
RUN MICRO_VERSION="2.0.14" && \
    ARCH="$(uname -m)" && \
    if [ "$ARCH" = "aarch64" ]; then MICRO_ARCH="linux-arm64"; \
    else MICRO_ARCH="linux64"; fi && \
    wget -q "https://github.com/zyedidia/micro/releases/download/v${MICRO_VERSION}/micro-${MICRO_VERSION}-${MICRO_ARCH}.tar.gz" \
        -O /tmp/micro.tar.gz && \
    tar xzf /tmp/micro.tar.gz -C /tmp/ && \
    mv /tmp/micro-${MICRO_VERSION}/micro /usr/local/bin/micro && \
    chmod +x /usr/local/bin/micro && \
    rm -rf /tmp/micro.tar.gz /tmp/micro-${MICRO_VERSION}

# Install gum (interactive CLI prompts for upload rename flow)
RUN GUM_VERSION="0.17.0" && \
    ARCH="$(uname -m)" && \
    if [ "$ARCH" = "aarch64" ]; then GUM_ARCH="Linux_arm64"; \
    else GUM_ARCH="Linux_x86_64"; fi && \
    wget -q "https://github.com/charmbracelet/gum/releases/download/v${GUM_VERSION}/gum_${GUM_VERSION}_${GUM_ARCH}.tar.gz" \
        -O /tmp/gum.tar.gz && \
    tar xzf /tmp/gum.tar.gz -C /tmp/ && \
    mv /tmp/gum_${GUM_VERSION}_${GUM_ARCH}/gum /usr/local/bin/gum && \
    chmod +x /usr/local/bin/gum && \
    rm -rf /tmp/gum.tar.gz /tmp/gum_${GUM_VERSION}_*

# Install vitetris (tiny terminal Tetris, ~50 KB)
RUN apk add --no-cache --virtual .tetris-build gcc musl-dev make && \
    wget -q https://github.com/vicgeralds/vitetris/archive/refs/tags/v0.59.1.tar.gz -O /tmp/vitetris.tar.gz && \
    cd /tmp && tar xzf vitetris.tar.gz && cd vitetris-0.59.1 && \
    ./configure --without-network && make CFLAGS="-O2 -Wno-implicit-int -Wno-implicit-function-declaration" -j$(nproc) && \
    cp tetris /usr/local/bin/tetris && chmod +x /usr/local/bin/tetris && \
    cd / && rm -rf /tmp/vitetris* && \
    apk del .tetris-build

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

# ── Phase 1: Install dependencies (cached unless pyproject.toml changes) ──
# Copy only pyproject.toml first so pip can resolve and compile deps.
# This layer is cached across builds — PyMuPDF (~160s compile) only rebuilds
# when dependencies change, not on every source code edit.
COPY pyproject.toml /opt/inspekt/

# Create a minimal package stub so pip can install in editable mode.
# The real source is copied in Phase 2 (and mounted in dev mode).
RUN mkdir -p /opt/inspekt/inspekt && \
    echo '__version__ = "0.0.0.dev0"' > /opt/inspekt/inspekt/__init__.py && \
    touch /opt/inspekt/README.md

# PyMuPDF has no pre-built musl/aarch64 wheel, so we need build tools to compile it.
# Build deps are installed and removed in the same layer to keep image small.
RUN apk add --no-cache --virtual .build-deps \
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
    rm -f /usr/local/bin/cc /usr/local/bin/c++ && \
    apk del .build-deps

# ── Phase 1b: Stub out mitmproxy-linux (must be its own layer) ──
# mitmproxy-linux is the eBPF transparent proxy redirector — NOT needed since we use
# --mode regular with Chromium's --proxy-server flag. It requires bpf-linker (eBPF
# toolchain) which is impractical to build on Alpine.
#
# Both mitmproxy-rs AND mitmproxy depend on mitmproxy-linux==0.12.9 on Linux.
# By installing this stub in a committed layer BEFORE pip resolves those packages,
# pip sees the dependency as already satisfied and skips the download/build.
RUN mkdir -p /tmp/mitmproxy-linux-stub/mitmproxy_linux && \
    printf '[project]\nname = "mitmproxy-linux"\nversion = "0.12.9"\n' \
        > /tmp/mitmproxy-linux-stub/pyproject.toml && \
    printf '"""Stub: eBPF transparent proxy not needed in regular proxy mode."""\n' \
        > /tmp/mitmproxy-linux-stub/mitmproxy_linux/__init__.py && \
    /opt/inspekt/.venv/bin/pip install --no-cache-dir /tmp/mitmproxy-linux-stub && \
    rm -rf /tmp/mitmproxy-linux-stub

# ── Phase 1c: Install mitmproxy (compiled deps + core in one shot) ──
# mitmproxy-rs and aioquic need Rust/C compilation on Alpine/aarch64.
# Uses rustup for Rust >= 1.85 (Alpine's Rust 1.83 is too old for edition2024).
# The stub mitmproxy-linux from the previous layer satisfies that dependency.
# Build tools are installed and removed in the same layer to keep image small.
RUN apk add --no-cache --virtual .mitmproxy-build-deps \
        gcc g++ make python3-dev musl-dev libffi-dev openssl-dev curl && \
    ln -sf /usr/bin/gcc /usr/local/bin/cc && \
    ln -sf /usr/bin/g++ /usr/local/bin/c++ && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal && \
    export PATH="/root/.cargo/bin:$PATH" && \
    /opt/inspekt/.venv/bin/pip install --no-cache-dir mitmproxy && \
    rm -f /usr/local/bin/cc /usr/local/bin/c++ && \
    rustup self uninstall -y && \
    rm -rf /root/.cargo /root/.rustup && \
    apk del .mitmproxy-build-deps

# Generate mitmproxy CA certificate and trust it system-wide + in Chromium's NSS database.
# We run mitmdump briefly to auto-generate the CA key pair in /root/.mitmproxy/,
# then install the CA cert using the same pattern as the existing mkcert setup.
RUN /opt/inspekt/.venv/bin/mitmdump --set confdir=/root/.mitmproxy -p 0 & \
    sleep 2 && kill %1 2>/dev/null; \
    cp /root/.mitmproxy/mitmproxy-ca-cert.pem /usr/local/share/ca-certificates/mitmproxy-ca.crt && \
    update-ca-certificates && \
    certutil -d sql:/root/.pki/nssdb -A -t "C,," -n "mitmproxy CA" \
             -i /root/.mitmproxy/mitmproxy-ca-cert.pem

# ── Phase 2: Copy source code (changes frequently, but deps are cached) ──
COPY inspekt /opt/inspekt/inspekt
COPY extensions /opt/inspekt/extensions
COPY prompts /opt/inspekt/prompts

# Set permissions and create the inspekt wrapper script
RUN chmod -R a+rX /opt/inspekt/extensions && \
    printf '#!/bin/zsh\nsource /opt/inspekt/.venv/bin/activate\n/opt/inspekt/.venv/bin/inspekt "$@"\n' > /usr/local/bin/inspekt && \
    chmod +x /usr/local/bin/inspekt

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
RUN for cmd in eval exec repl plugin yolo domain vm do mcp autostart open edit; do \
        rm -f /opt/inspekt/commands/$cmd; \
    done

# Copy proxy-scripts early (needed by allowed-bin setup below)
COPY docker/browser-vm/proxy-scripts /opt/proxy-scripts

# 2) Allowed system utilities — curated symlinks
#    Removed dangerous utils: awk (system()), env (exec), less (!sh escape),
#    xargs (runs commands), chmod (makes scripts executable)
RUN mkdir -p /opt/inspekt/allowed-bin && \
    for cmd in \
        ls cat pwd mkdir touch rm cp mv \
        head tail more grep wc sort uniq tr diff \
        echo date file stat basename dirname realpath uname \
        clear whoami which tee tree cal ps sleep bc \
        uptime base64 md5sum sha256sum watch xxd cut \
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
        > /opt/inspekt/allowed-bin/prettier && chmod +x /opt/inspekt/allowed-bin/prettier && \
    # macOS-style clipboard commands (delegate to xclip with DISPLAY for X11)
    printf '#!/bin/zsh\nDISPLAY=:0 /usr/bin/xclip -selection clipboard\n' \
        > /opt/inspekt/allowed-bin/pbcopy && chmod +x /opt/inspekt/allowed-bin/pbcopy && \
    printf '#!/bin/zsh\nDISPLAY=:0 /usr/bin/xclip -selection clipboard -o\n' \
        > /opt/inspekt/allowed-bin/pbpaste && chmod +x /opt/inspekt/allowed-bin/pbpaste && \
    # Restricted env wrapper: only allows setting VAR=VALUE before running an allowed command.
    # Needed by Click's shell completion (generates: env COMP_WORDS=... inspekt).
    # Blocks: env /usr/bin/python3, env node, etc.
    printf '#!/bin/zsh\nlocal -a env_args\nwhile [[ "$1" == *=* ]]; do env_args+=("$1"); shift; done\ncmd="$1"\nif [[ -z "$cmd" ]]; then /usr/bin/env "${env_args[@]}"; exit; fi\nif [[ -x "/opt/inspekt/commands/$cmd" || -x "/opt/inspekt/allowed-bin/$cmd" ]]; then\n  /usr/bin/env "${env_args[@]}" "$@"\nelse\n  echo "env: not permitted to run: $cmd" >&2; exit 1\nfi\n' \
        > /opt/inspekt/allowed-bin/env && chmod +x /opt/inspekt/allowed-bin/env && \
    # ── macOS-feel commands ──────────────────────────────────────────────
    # open: macOS-compatible URL/file opener (replaces auto-generated inspekt open wrapper)
    # Placed in commands/ to take priority; detects files vs URLs, adds auto-https and -n/-g flags
    cp /opt/proxy-scripts/open /opt/inspekt/commands/open && \
    chmod +x /opt/inspekt/commands/open && \
    # edit: opens files in the control panel editor
    cp /opt/proxy-scripts/edit /opt/inspekt/commands/edit && \
    chmod +x /opt/inspekt/commands/edit && \
    # upload: drag-drop file upload from host browser
    cp /opt/proxy-scripts/upload /opt/inspekt/commands/upload && \
    chmod +x /opt/inspekt/commands/upload && \
    # about + easter eggs
    for cmd in about shrug lenny motivate party cowsay; do \
        cp /opt/proxy-scripts/$cmd /opt/inspekt/commands/$cmd && \
        chmod +x /opt/inspekt/commands/$cmd; \
    done && \
    # screencapture: wrapper around inspekt screenshot
    printf '#!/bin/zsh\nfull=""\nfilename=""\nwhile [[ $# -gt 0 ]]; do\n  case "$1" in\n    -f) full="--full-page"; shift ;;\n    -*) echo "screencapture: unknown option $1" >&2; exit 1 ;;\n    *) filename="$1"; shift ;;\n  esac\ndone\n/opt/inspekt/.venv/bin/inspekt screenshot $full ${filename:+--output "$filename"}\n' \
        > /opt/inspekt/allowed-bin/screencapture && chmod +x /opt/inspekt/allowed-bin/screencapture && \
    # say: text-to-speech via control server
    printf '#!/bin/zsh\nif [[ -z "$*" ]]; then echo "Usage: say <text>" >&2; exit 1; fi\ncurl -sf -X POST http://localhost:8888/sr/speak \\\n  -H "Content-Type: application/json" \\\n  -d "{\"text\": $(printf '\''%%s'\'' "$*" | jq -Rs .)}" > /dev/null 2>&1\nif [[ $? -ne 0 ]]; then\n  echo "say: text-to-speech is not available in this VM session" >&2\n  exit 1\nfi\n' \
        > /opt/inspekt/allowed-bin/say && chmod +x /opt/inspekt/allowed-bin/say && \
    # sw_vers: macOS-style version info
    printf '#!/bin/zsh\nv=$(/opt/inspekt/.venv/bin/inspekt --version 2>/dev/null | head -1)\necho "ProductName:       Inspekt Browser VM"\necho "ProductVersion:    ${v:-unknown}"\necho "BuildVersion:      Alpine $(cat /etc/alpine-release 2>/dev/null || echo unknown)"\necho "KernelVersion:     $(uname -r)"\n' \
        > /opt/inspekt/allowed-bin/sw_vers && chmod +x /opt/inspekt/allowed-bin/sw_vers && \
    # ── Friendly stubs for unavailable commands ──────────────────────────
    printf '#!/bin/zsh\necho "The VM never sleeps — no need for caffeinate." >&2\n' \
        > /opt/inspekt/allowed-bin/caffeinate && chmod +x /opt/inspekt/allowed-bin/caffeinate && \
    printf '#!/bin/zsh\necho "ping: network access is restricted in the VM." >&2\necho "  Use \`curl -I <url>\` to test HTTP endpoints." >&2\nexit 1\n' \
        > /opt/inspekt/allowed-bin/ping && chmod +x /opt/inspekt/allowed-bin/ping && \
    printf '#!/bin/zsh\necho "ssh: not available in the VM terminal." >&2\necho "  Use \`inspekt\` commands to interact with web pages." >&2\nexit 1\n' \
        > /opt/inspekt/allowed-bin/ssh && chmod +x /opt/inspekt/allowed-bin/ssh && \
    printf '#!/bin/zsh\necho "scp: file transfer is not available in the VM." >&2\necho "  Use the Downloads panel to export files." >&2\nexit 1\n' \
        > /opt/inspekt/allowed-bin/scp && chmod +x /opt/inspekt/allowed-bin/scp && \
    # Terminal editors: nano and micro are allowed (no shell escape capabilities)
    ln -sf /usr/bin/nano /opt/inspekt/allowed-bin/nano && \
    ln -sf /usr/local/bin/micro /opt/inspekt/allowed-bin/micro && \
    ln -sf /usr/local/bin/gum /opt/inspekt/allowed-bin/gum && \
    ln -sf /usr/local/bin/tetris /opt/inspekt/allowed-bin/tetris && \
    # vim/vi stubs — point users to available editors
    printf '#!/bin/zsh\necho "vim is not available in the VM. Try one of these instead:" >&2\necho "  nano $@" >&2\necho "  micro $@" >&2\necho "  edit $@    (opens in the graphical editor)" >&2\nexit 1\n' \
        > /opt/inspekt/allowed-bin/vim && chmod +x /opt/inspekt/allowed-bin/vim && \
    ln -sf /opt/inspekt/allowed-bin/vim /opt/inspekt/allowed-bin/vi && \
    printf '#!/bin/zsh\necho "$(basename $0): package installation is not available in the VM." >&2\necho "  The tools you need are pre-installed." >&2\nexit 1\n' \
        > /opt/inspekt/allowed-bin/brew && chmod +x /opt/inspekt/allowed-bin/brew && \
    printf '#!/bin/zsh\necho "sudo: you don'\''t need sudo in the VM." >&2\necho "  inspekt commands already have the access they need." >&2\necho "  Try running your command without sudo." >&2\nexit 1\n' \
        > /opt/inspekt/allowed-bin/sudo && chmod +x /opt/inspekt/allowed-bin/sudo && \
    printf '#!/bin/zsh\necho "top: not available. Use \`uptime\` for system load or \`ps\` for processes." >&2\nexit 1\n' \
        > /opt/inspekt/allowed-bin/top && chmod +x /opt/inspekt/allowed-bin/top && \
    printf '#!/bin/zsh\nif [[ -n "$1" ]]; then\n  if [[ -x "/opt/inspekt/commands/$1" ]]; then\n    /opt/inspekt/.venv/bin/inspekt "$1" --help\n  else\n    echo "No manual entry for $1" >&2\n    echo "  Try: inspekt --help" >&2\n  fi\nelse\n  echo "Use \`inspekt <command> --help\` for documentation." >&2\n  echo "  Example: inspekt screenshot --help" >&2\nfi\n' \
        > /opt/inspekt/allowed-bin/man && chmod +x /opt/inspekt/allowed-bin/man

# Inspekt config must be copied before the permissions step that copies it to /home/inspekt
COPY docker/browser-vm/inspekt-config.yaml /root/.config/inspekt.yaml

# File permissions for restricted user
RUN chmod -R a+rX /opt/inspekt/.venv && \
    chmod -R a+rX /opt/inspekt/inspekt && \
    chmod -R a+rX /opt/inspekt/commands && \
    chmod -R a+rX /opt/inspekt/allowed-bin && \
    mkdir -p /home/inspekt/.config && \
    cp /root/.config/inspekt.yaml /home/inspekt/.config/inspekt.yaml && \
    chown -R inspekt:inspekt /home/inspekt

# Copy VM configuration files
COPY docker/browser-vm/supervisord.conf /etc/supervisor/conf.d/supervisord.conf
COPY docker/browser-vm/openbox-autostart /root/.config/openbox/autostart
COPY docker/browser-vm/openbox-rc.xml /root/.config/openbox/rc.xml
COPY docker/browser-vm/entrypoint.sh /entrypoint.sh
COPY docker/browser-vm/control-server.py /opt/control-server.py
COPY docker/browser-vm/terminal-server.py /opt/terminal-server.py
COPY docker/browser-vm/control-panel.html /usr/share/novnc/control.html
COPY docker/browser-vm/toolbar.css /usr/share/novnc/toolbar.css
COPY docker/browser-vm/toolbar.js /usr/share/novnc/toolbar.js
COPY docker/browser-vm/vision-sim.js /usr/share/novnc/vision-sim.js
COPY docker/browser-vm/vision-sim.css /usr/share/novnc/vision-sim.css
COPY docker/browser-vm/motor-sim.js /usr/share/novnc/motor-sim.js
COPY docker/browser-vm/motor-sim.css /usr/share/novnc/motor-sim.css
COPY docker/browser-vm/fonts /usr/share/novnc/fonts
COPY docker/browser-vm/vendor/codemirror.min.js /usr/share/novnc/vendor/codemirror.min.js
COPY docker/browser-vm/vendor/ninja-keys.min.js /usr/share/novnc/vendor/ninja-keys.min.js
COPY docker/browser-vm/vendor/sortable.min.js /usr/share/novnc/vendor/sortable.min.js
COPY docker/browser-vm/context-menu.js /usr/share/novnc/context-menu.js
COPY docker/browser-vm/vnc-overlay.js /usr/share/novnc/vnc-overlay.js
COPY docker/browser-vm/audio.js /usr/share/novnc/audio.js
COPY docker/browser-vm/zoom.js /usr/share/novnc/zoom.js
COPY docker/browser-vm/scrollbar.js /usr/share/novnc/scrollbar.js
COPY docker/browser-vm/js /usr/share/novnc/js
COPY docker/browser-vm/inspekt-chromium.sh /opt/inspekt-chromium.sh
COPY docker/browser-vm/devtools-manager.sh /opt/devtools-manager.sh
COPY docker/browser-vm/xorg.conf /etc/X11/xorg.conf
COPY docker/browser-vm/resize-display.sh /opt/resize-display.sh
COPY docker/browser-vm/download.sh /usr/local/bin/download
COPY docker/browser-vm/audio-proxy.sh /opt/audio-proxy.sh
COPY docker/browser-vm/audio-server.py /opt/audio-server.py
COPY docker/browser-vm/pulse-config.pa /etc/pulse/default.pa
COPY docker/browser-vm/proxy-scripts /opt/proxy-scripts
COPY docker/browser-vm/pages /opt/pages

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

# Write version info for the `about` command (needs root to query chromium)
RUN mkdir -p /etc/inspekt-versions && \
    chromium --version 2>/dev/null | sed 's/Chromium \([0-9.]*\).*/\1/' | cut -d. -f1-3 > /etc/inspekt-versions/chromium

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

# ── Final cleanup: remove build-time-only tools and dead weight ──
# All removals in a single layer to avoid inflating the image.
# Saves ~80 MB by stripping things only needed during docker build.
RUN \
    # pip is only needed at build time (both system and venv copies)
    rm -rf /opt/inspekt/.venv/lib/python3.12/site-packages/pip /opt/inspekt/.venv/lib/python3.12/site-packages/pip-*.dist-info && \
    rm -rf /usr/lib/python3.12/site-packages/pip /usr/lib/python3.12/site-packages/pip-*.dist-info && \
    # NOTE: do NOT remove setuptools/pkg_resources from system Python — supervisord depends on it
    # setuptools in venv is safe to remove (inspekt doesn't use it at runtime)
    rm -rf /opt/inspekt/.venv/lib/python3.12/site-packages/setuptools /opt/inspekt/.venv/lib/python3.12/site-packages/setuptools-*.dist-info && \
    # mkcert — certs are already generated, binary no longer needed
    rm -f /usr/local/bin/mkcert && \
    # noVNC test suite, docs, and snap packaging — never served
    rm -rf /usr/share/novnc/tests /usr/share/novnc/docs /usr/share/novnc/snap && \
    # Python stdlib modules unused at runtime
    rm -rf /usr/lib/python3.12/ensurepip && \
    rm -rf /usr/lib/python3.12/lib2to3 && \
    rm -rf /usr/lib/python3.12/pydoc_data && \
    rm -rf /usr/lib/python3.12/turtledemo && \
    rm -f /usr/lib/python3.12/turtle.py && \
    # Test suites shipped inside pip packages
    rm -rf /opt/inspekt/.venv/lib/python3.12/site-packages/tornado/test && \
    rm -rf /opt/inspekt/.venv/lib/python3.12/site-packages/jsonschema/tests && \
    rm -rf /opt/inspekt/.venv/lib/python3.12/site-packages/referencing/tests && \
    rm -rf /opt/inspekt/.venv/lib/python3.12/site-packages/jsonschema_specifications/tests && \
    rm -rf /opt/inspekt/.venv/lib/python3.12/site-packages/mitmproxy/test && \
    # Compiled Python bytecode — regenerated on first import, negligible startup cost
    find /opt/inspekt/.venv -name '*.pyc' -delete && \
    find /opt/inspekt/.venv -type d -name '__pycache__' -empty -delete && \
    true

# Expose ports
EXPOSE 443 6080 6081 7835 8767 8768 8889 9222

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost:6080/ || exit 1

# Use tini as init system
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["/entrypoint.sh"]
