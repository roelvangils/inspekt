// =============================================
// RFB (noVNC) — direct embedding (no iframe)
// =============================================
// rfb declared in config.js (shared state)
let _rfbReconnectAttempts = 0;
let _vncInitialized = false;
let _isCleaningUp = false;
let _isConnecting = false;  // Prevents overlapping connectVNC calls
let _lastConnectTime = 0;   // Timestamp of last successful connect
const _RFB_MAX_RECONNECT_DELAY = 5000;

// Convert parent-document client coordinates to VM pixel coordinates
function _clientToVm(clientX, clientY) {
    const canvas = document.querySelector('#vncContainer canvas');
    if (!canvas) return { x: clientX, y: clientY };
    const rect = canvas.getBoundingClientRect();
    const resolution = currentResolution || { width: rect.width, height: rect.height };
    return {
        x: Math.round((clientX - rect.left) * resolution.width / rect.width),
        y: Math.round((clientY - rect.top) * resolution.height / rect.height)
    };
}

// Terminal color themes (with semi-transparent backgrounds for blur effect)
const TERMINAL_THEMES = {
    'tokyo-night': {
        background: 'rgba(26, 27, 38, 0.8)', foreground: '#c0caf5', cursor: '#c0caf5', cursorAccent: '#1a1b26',
        selectionBackground: 'rgba(102, 126, 234, 0.4)',
        black: '#15161e', red: '#f7768e', green: '#9ece6a', yellow: '#e0af68',
        blue: '#7aa2f7', magenta: '#bb9af7', cyan: '#7dcfff', white: '#a9b1d6',
        brightBlack: '#414868', brightRed: '#f7768e', brightGreen: '#9ece6a', brightYellow: '#e0af68',
        brightBlue: '#7aa2f7', brightMagenta: '#bb9af7', brightCyan: '#7dcfff', brightWhite: '#c0caf5'
    },
    'dracula': {
        background: 'rgba(40, 42, 54, 0.8)', foreground: '#f8f8f2', cursor: '#f8f8f2',
        selectionBackground: '#44475a',
        black: '#21222c', red: '#ff5555', green: '#50fa7b', yellow: '#f1fa8c',
        blue: '#bd93f9', magenta: '#ff79c6', cyan: '#8be9fd', white: '#f8f8f2',
        brightBlack: '#6272a4', brightRed: '#ff6e6e', brightGreen: '#69ff94', brightYellow: '#ffffa5',
        brightBlue: '#d6acff', brightMagenta: '#ff92df', brightCyan: '#a4ffff', brightWhite: '#ffffff'
    },
    'nord': {
        background: 'rgba(46, 52, 64, 0.8)', foreground: '#d8dee9', cursor: '#eceff4',
        selectionBackground: '#eceff4',
        black: '#3b4252', red: '#bf616a', green: '#a3be8c', yellow: '#ebcb8b',
        blue: '#81a1c1', magenta: '#b48ead', cyan: '#88c0d0', white: '#e5e9f0',
        brightBlack: '#596377', brightRed: '#bf616a', brightGreen: '#a3be8c', brightYellow: '#ebcb8b',
        brightBlue: '#81a1c1', brightMagenta: '#b48ead', brightCyan: '#8fbcbb', brightWhite: '#eceff4'
    },
    'catppuccin-mocha': {
        background: 'rgba(30, 30, 46, 0.8)', foreground: '#cdd6f4', cursor: '#f5e0dc',
        selectionBackground: '#585b70',
        black: '#45475a', red: '#f38ba8', green: '#a6e3a1', yellow: '#f9e2af',
        blue: '#89b4fa', magenta: '#f5c2e7', cyan: '#94e2d5', white: '#a6adc8',
        brightBlack: '#585b70', brightRed: '#f37799', brightGreen: '#89d88b', brightYellow: '#ebd391',
        brightBlue: '#74a8fc', brightMagenta: '#f2aede', brightCyan: '#6bd7ca', brightWhite: '#bac2de'
    },
    'gruvbox-dark': {
        background: 'rgba(40, 40, 40, 0.8)', foreground: '#ebdbb2', cursor: '#ebdbb2',
        selectionBackground: '#665c54',
        black: '#282828', red: '#cc241d', green: '#98971a', yellow: '#d79921',
        blue: '#458588', magenta: '#b16286', cyan: '#689d6a', white: '#a89984',
        brightBlack: '#928374', brightRed: '#fb4934', brightGreen: '#b8bb26', brightYellow: '#fabd2f',
        brightBlue: '#83a598', brightMagenta: '#d3869b', brightCyan: '#8ec07c', brightWhite: '#ebdbb2'
    },
    'monokai-soda': {
        background: 'rgba(26, 26, 26, 0.8)', foreground: '#c4c5b5', cursor: '#f6f7ec',
        selectionBackground: '#343434',
        black: '#1a1a1a', red: '#f4005f', green: '#98e024', yellow: '#fa8419',
        blue: '#9d65ff', magenta: '#f4005f', cyan: '#58d1eb', white: '#c4c5b5',
        brightBlack: '#625e4c', brightRed: '#f4005f', brightGreen: '#98e024', brightYellow: '#e0d561',
        brightBlue: '#9d65ff', brightMagenta: '#f4005f', brightCyan: '#58d1eb', brightWhite: '#f6f6ef'
    },
    'tomorrow': {
        background: 'rgba(255, 255, 255, 0.85)', foreground: '#4d4d4c', cursor: '#4d4d4c',
        selectionBackground: '#d6d6d6',
        black: '#000000', red: '#c82829', green: '#718c00', yellow: '#eab700',
        blue: '#4271ae', magenta: '#8959a8', cyan: '#3e999f', white: '#ffffff',
        brightBlack: '#000000', brightRed: '#c82829', brightGreen: '#718c00', brightYellow: '#eab700',
        brightBlue: '#4271ae', brightMagenta: '#8959a8', brightCyan: '#3e999f', brightWhite: '#ffffff'
    },
    'github': {
        background: 'rgba(244, 244, 244, 0.85)', foreground: '#3e3e3e', cursor: '#3f3f3f',
        selectionBackground: '#a9c1e2',
        black: '#3e3e3e', red: '#970b16', green: '#07962a', yellow: '#c5bb94',
        blue: '#003e8a', magenta: '#e94691', cyan: '#7cc4df', white: '#b2b2b2',
        brightBlack: '#666666', brightRed: '#de0000', brightGreen: '#7ac895', brightYellow: '#d7b600',
        brightBlue: '#2e6cba', brightMagenta: '#f29592', brightCyan: '#00c7cb', brightWhite: '#ffffff'
    },
    'catppuccin-latte': {
        background: 'rgba(239, 241, 245, 0.85)', foreground: '#4c4f69', cursor: '#dc8a78',
        selectionBackground: '#acb0be',
        black: '#5c5f77', red: '#d20f39', green: '#40a02b', yellow: '#df8e1d',
        blue: '#1e66f5', magenta: '#ea76cb', cyan: '#179299', white: '#acb0be',
        brightBlack: '#6c6f85', brightRed: '#de293e', brightGreen: '#49af3d', brightYellow: '#eea02d',
        brightBlue: '#456eff', brightMagenta: '#fe85d8', brightCyan: '#2d9fa8', brightWhite: '#bcc0cc'
    },
    'solarized-light': {
        background: 'rgba(253, 246, 227, 0.85)', foreground: '#657b83', cursor: '#657b83',
        selectionBackground: '#eee8d5',
        black: '#073642', red: '#dc322f', green: '#859900', yellow: '#b58900',
        blue: '#268bd2', magenta: '#d33682', cyan: '#2aa198', white: '#eee8d5',
        brightBlack: '#002b36', brightRed: '#cb4b16', brightGreen: '#586e75', brightYellow: '#657b83',
        brightBlue: '#839496', brightMagenta: '#6c71c4', brightCyan: '#93a1a1', brightWhite: '#fdf6e3'
    }
};

// Shared state (rfb, terminal, terminalSocket, fitAddon, isTerminalOpen,
// hasTerminalSession, isConnected, editorView, editorCurrentPath, editorIsReadOnly,
// editorIsDirty, activePanel, terminalPosition, terminalMode, splitRatio,
// splitFlipped, isDraggingSplitHandle, _lastMouseX, _lastMouseY, _terminalPromptDomain)
// are declared in config.js so they're available to all modules regardless of load order.

// Global mouse position tracking (needed for keyboard-triggered context menus).
// Uses both document-level and pointermove on VNC container because noVNC may
// use setPointerCapture which redirects events away from document listeners.
function _trackMouse(e) { _lastMouseX = e.clientX; _lastMouseY = e.clientY; }
document.addEventListener('mousemove', _trackMouse, { passive: true });
document.addEventListener('pointermove', _trackMouse, { passive: true });

// ── Editor state (CodeMirror compartment — must be after vendor script loads) ──
const editorThemeCompartment = typeof CM !== 'undefined' ? new CM.Compartment() : null;

/**
 * Cosmetically rewrite the terminal prompt when the active URL changes.
 * This is purely visual — the shell's real prompt updates on next Enter
 * via the background domain-fetch mechanism in zshrc.
 */
function updateTerminalPrompt(newUrl) {
    if (!terminal || !hasTerminalSession) return;

    let newDomain;
    try { newDomain = new URL(newUrl).hostname || 'inspekt'; }
    catch { newDomain = 'inspekt'; }

    if (newDomain === _terminalPromptDomain) return;
    const oldDomain = _terminalPromptDomain;
    _terminalPromptDomain = newDomain;

    const buffer = terminal.buffer.active;
    const absRow = buffer.baseY + buffer.cursorY;
    const line = buffer.getLine(absRow);
    if (!line) return;

    const lineText = line.translateToString(true);

    // Match zsh prompt: domain:/path$ optional_user_input
    const escaped = oldDomain.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const match = lineText.match(new RegExp('^' + escaped + ':(\\S*)\\$ (.*)$'));
    if (!match) return;

    const path = match[1];
    const userInput = match[2];
    const viewportRow = buffer.cursorY + 1; // ANSI rows are 1-indexed
    const newCursorCol = buffer.cursorX + (newDomain.length - oldDomain.length) + 1;

    terminal.write(
        '\x1b[' + viewportRow + ';1H' +     // Move to start of prompt line
        '\x1b[2K' +                           // Clear entire line
        '\x1b[32m' + newDomain + '\x1b[0m:' + // Green domain
        '\x1b[34m' + path + '\x1b[0m$ ' +     // Blue path + prompt char
        userInput +                            // Preserve any typed input
        '\x1b[' + viewportRow + ';' + newCursorCol + 'H' // Restore cursor at adjusted column
    );
}

// Splash screen management
function updateSplashStatus(message) {
    const status = document.getElementById('splashStatus');
    if (status) status.textContent = message;
}

function hideSplash() {
    const splash = document.getElementById('splashScreen');
    if (splash) {
        splash.classList.add('hidden');
        // Don't remove from DOM — we need it for reconnection
    }
}

function showSplash(message) {
    const splash = document.getElementById('splashScreen');
    if (splash) {
        splash.classList.remove('hidden');
        updateSplashStatus(message || 'Reconnecting…');
    }
}

// Lightweight reconnection overlay — only covers the VNC canvas area
function showReconnectOverlay(message) {
    let overlay = document.getElementById('vncReconnectOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'vncReconnectOverlay';
        overlay.style.cssText = `
            position: absolute; inset: 0; z-index: 60;
            display: flex; align-items: center; justify-content: center;
            background: var(--bg-page, #1a1a2e); color: #888;
            font-size: 14px; flex-direction: column; gap: 12px;
        `;
        document.getElementById('vncContainer').appendChild(overlay);
    }
    overlay.innerHTML = `
        <div style="width:24px;height:24px;border:2px solid #555;border-top-color:#aaa;border-radius:50%;animation:spin 1s linear infinite"></div>
        <div>${message || 'Reconnecting…'}</div>
        <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
    `;
    overlay.style.display = 'flex';
}

function hideReconnectOverlay() {
    const overlay = document.getElementById('vncReconnectOverlay');
    if (overlay) overlay.style.display = 'none';
}

// Dynamic viewport resize — matches VM resolution to host browser viewport
function setupViewportResize() {
    const container = document.getElementById('vncContainer');
    if (!container) return;

    let lastWidth = 0;
    let lastHeight = 0;
    let debounceTimer = null;
    const dimsEl = document.getElementById('resizeDimensions');

    const observer = new ResizeObserver(entries => {
        // Show live dimensions immediately (before debounce)
        const rect = entries[0]?.contentRect;
        if (rect && dimsEl) {
            let w = Math.round(rect.width);
            let h = Math.round(rect.height);
            if (w % 2 !== 0) w++;
            if (h % 2 !== 0) h++;
            dimsEl.textContent = `${w} × ${h}`;
        }
        // Show dimensions badge during resize
        if (dimsEl) dimsEl.classList.add('visible');
        // Hide overlays during resize (rects are temporarily invalid)
        if (typeof vncOverlay !== 'undefined') {
            vncOverlay.dismiss('inspect-highlight', false);
            vncOverlay.dismiss('inspect-tooltip', false);
        }
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const entry = entries[0];
            if (!entry) return;

            // Use CSS pixels (1:1 mapping with noVNC canvas)
            let width = Math.round(entry.contentRect.width);
            let height = Math.round(entry.contentRect.height);

            // Round to even numbers (X11 preference)
            if (width % 2 !== 0) width++;
            if (height % 2 !== 0) height++;

            // Skip if unchanged
            if (width === lastWidth && height === lastHeight) {
                if (dimsEl) dimsEl.classList.remove('visible');
                if (typeof _inspectTrackingActive !== 'undefined' && _inspectTrackingActive) _pollInspectRect();
                return;
            }
            // Skip unreasonably small sizes
            if (width < 320 || height < 240) {
                if (dimsEl) dimsEl.classList.remove('visible');
                return;
            }

            lastWidth = width;
            lastHeight = height;

            console.log(`[viewport-resize] Requesting ${width}x${height}`);

            fetch(`http://${VNC_HOST}:${CONTROL_PORT}/resize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ width, height, source: 'auto' })
            })
            .then(r => r.json())
            .then(data => {
                if (data.changed) {
                    console.log(`[viewport-resize] Resolution changed to ${data.resolution}`);
                }
                // Short delay to let noVNC receive the new framebuffer, then restore overlay
                setTimeout(() => {
                    if (dimsEl) dimsEl.classList.remove('visible');
                    if (typeof _inspectTrackingActive !== 'undefined' && _inspectTrackingActive) _pollInspectRect();
                }, 200);
            })
            .catch(err => {
                console.warn('[viewport-resize] Resize failed:', err);
                if (dimsEl) dimsEl.classList.remove('visible');
            });
        }, 300); // 300ms debounce
    });

    observer.observe(container);
    console.log('[viewport-resize] ResizeObserver active');
}

// Connect to VNC via direct RFB embedding (no iframe)
let _isReconnect = false;

async function connectVNC() {
    // Prevent overlapping connection attempts
    if (_isConnecting) return;
    _isConnecting = true;

    const container = document.getElementById('vncContainer');

    // Show appropriate UI: full splash on first load, canvas-only overlay on reconnect
    if (_isReconnect) {
        showReconnectOverlay('Reconnecting…');
    } else {
        updateSplashStatus('Connecting to VM…');
    }

    // Clean up previous RFB instance on reconnect.
    // Set _isCleaningUp to prevent the old instance's disconnect event
    // from queuing a duplicate connectVNC() call.
    if (rfb) {
        _isCleaningUp = true;
        try { rfb.disconnect(); } catch (_) {}
        rfb = null;
        _isCleaningUp = false;
    }
    // Remove any leftover noVNC DOM elements from a previous connection
    // RFB creates a <div class="noVNC_screen"> containing the canvas
    const oldScreen = container.querySelector('.noVNC_screen');
    if (oldScreen) oldScreen.remove();

    try {
        // Dynamic import of RFB (ES module, cached by browser after first load)
        const httpProtocol = window.location.protocol;
        const { default: RFB } = await import(`${httpProtocol}//${VNC_HOST}:${VNC_PORT}/core/rfb.js`);

        const wsProtocol = httpProtocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProtocol}//${VNC_HOST}:${VNC_PORT}/websockify`;

        rfb = new RFB(container, wsUrl, { shared: true });
        rfb.resizeSession = true;
        rfb.scaleViewport = true;
        rfb.showDotCursor = false;
        // Override noVNC's overflow:auto on _screen wrapper to prevent
        // a visible scrollbar gutter shadow on the right edge
        if (rfb._screen) rfb._screen.style.overflow = 'hidden';

        // Auto-focus VNC on hover so keyboard input works immediately
        container.addEventListener('mouseenter', () => {
            if (rfb) rfb.focus();
        });
    } catch (err) {
        // RFB constructor or import failed (e.g. websockify not available yet)
        console.warn('[VNC] Connection failed, retrying…', err);
        _isConnecting = false;
        const delay = Math.min(1000 * Math.pow(2, _rfbReconnectAttempts), _RFB_MAX_RECONNECT_DELAY);
        _rfbReconnectAttempts++;
        _isReconnect = true;
        showReconnectOverlay(`Connection failed. Retrying in ${Math.round(delay/1000)}s…`);
        setTimeout(connectVNC, delay);
        return;
    }

    // Connection timeout: if RFB doesn't connect within 5 seconds,
    // tear it down and retry. This handles cases where websockify
    // accepts the WebSocket but can't reach x11vnc (hangs indefinitely).
    const _connectTimeout = setTimeout(() => {
        console.warn('[VNC] Connection timeout — retrying');
        _isCleaningUp = true;
        try { rfb.disconnect(); } catch (_) {}
        rfb = null;
        _isCleaningUp = false;
        _isConnecting = false;
        _isReconnect = true;
        const delay = Math.min(1000 * Math.pow(2, _rfbReconnectAttempts), _RFB_MAX_RECONNECT_DELAY);
        _rfbReconnectAttempts++;
        showReconnectOverlay('Connection timed out. Retrying…');
        setTimeout(connectVNC, delay);
    }, 5000);

    rfb.addEventListener('connect', () => {
        clearTimeout(_connectTimeout);
        _rfbReconnectAttempts = 0;
        _isReconnect = false;
        _isConnecting = false;
        _lastConnectTime = Date.now();
        hideReconnectOverlay();
        updateSplashStatus('VM ready!');

        // Early check: if Chrome is on an internal URL, switch to native
        // view before the splash screen even hides — prevents a flash of
        // the internal page rendered through VNC.
        checkInitialInternalUrl();

        // Set up canvas event interceptors for right-click and hover-inspect
        _setupCanvasEventInterceptors();

        setTimeout(() => {
            hideSplash();
            updateStatus(true);
            // Only initialize these once (not on every reconnect)
            if (!_vncInitialized) {
                _vncInitialized = true;
                setupViewportResize();
                initSplitDragHandle();
                setTimeout(restoreTabsFromStorage, 2000);
            }
            rfb.focus();
            if (window.startScrollbarPolling) window.startScrollbarPolling();
        }, 500);
    });

    rfb.addEventListener('disconnect', (e) => {
        clearTimeout(_connectTimeout);
        if (window.stopScrollbarPolling) window.stopScrollbarPolling();
        // Ignore disconnect events during cleanup (old instance being torn down)
        if (_isCleaningUp) return;

        // Ignore spurious disconnects in the first 3s after connecting.
        // RFB resolution negotiation (resizeSession) can cause brief
        // disconnects that resolve themselves — don't trigger a full
        // reconnection cycle for these.
        const timeSinceConnect = Date.now() - _lastConnectTime;
        if (_lastConnectTime > 0 && timeSinceConnect < 3000) {
            console.log(`[VNC] Ignoring disconnect ${timeSinceConnect}ms after connect (stabilizing)`);
            return;
        }

        _isConnecting = false;
        updateStatus(false);
        _isReconnect = true;
        const delay = Math.min(1000 * Math.pow(2, _rfbReconnectAttempts), _RFB_MAX_RECONNECT_DELAY);
        _rfbReconnectAttempts++;
        console.log(`[VNC] Disconnected after ${timeSinceConnect}ms, retrying in ${delay}ms`);
        showReconnectOverlay('Connection lost. Reconnecting…');
        setTimeout(connectVNC, delay);
    });

    rfb.addEventListener('clipboard', (e) => {
        // Handle clipboard data from VM (future use)
    });
}

/**
 * Quick URL check on startup: ask the control server what URL Chrome is
 * on. If it's an internal http://inspekt/ page, immediately switch to
 * native view so the VNC canvas never shows it.
 */
async function checkInitialInternalUrl() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/url`, {
            signal: AbortSignal.timeout(2000)
        });
        const data = await resp.json();
        if (data.ok && data.url && isInternalUrl(data.url)) {
            // We don't have an activeTabId yet, but fetchTabs will set
            // it shortly. For now, stash the URL and hide VNC preemptively.
            currentUrl = data.url;
            showNativeView(resolveInternalUrl(data.url));
            updateCloudIconState(data.url);
            document.getElementById('urlBar').value = displayUrl(data.url, false);
            // Mark a pending internal state; fetchTabs will assign to the right tab
            _pendingInternalUrl = data.url;
        }
    } catch {
        // Control server not ready yet — fetchTabs will handle it later
    }
}
let _pendingInternalUrl = null;

// Update connection status (shown via toast — no persistent UI element)
let _lastStatusConnected = null;
function updateStatus(connected) {
    isConnected = connected;
    // Only show toasts on actual state changes to avoid spam
    const wasConnected = _lastStatusConnected;
    if (connected === wasConnected) return;
    _lastStatusConnected = connected;

    if (connected) {
        // Only show "reconnected" toast if we were previously disconnected (not on initial load)
        if (wasConnected === false) {
            showToast('Connected', 'success');
        }
    } else {
        showToast('Connection lost', 'error', 5000);
    }
}

// Show toast notification (supports both old and new API)
// Old: showToast('msg', 'success', 3000)
// New: showToast('msg', { type: 'dark', duration: 10000, dismissible: true, action: { label, icon, onClick } })
function showToast(message, optionsOrType = '', duration) {
    const toast = document.getElementById('toast');

    // Backward compatibility: string second arg = old API
    let opts;
    if (typeof optionsOrType === 'string') {
        opts = { type: optionsOrType, duration: duration ?? 3000 };
    } else {
        opts = { type: '', duration: 3000, dismissible: false, action: null, ...optionsOrType };
    }

    // Clear any pending dismiss timer
    clearTimeout(toast._dismissTimer);

    // Build toast content
    let html = `<span class="toast-message">${_esc(message)}</span>`;

    if (opts.action) {
        const iconHtml = opts.action.icon || '';
        html += `<button class="toast-action" aria-label="${_esc(opts.action.label)}">${iconHtml} ${_esc(opts.action.label)}</button>`;
    }

    if (opts.dismissible) {
        html += `<button class="toast-dismiss" aria-label="Dismiss">&times;</button>`;
    }

    toast.innerHTML = html;
    toast.className = 'toast show' + (opts.type ? ' ' + opts.type : '');

    // Wire up action button
    if (opts.action?.onClick) {
        toast.querySelector('.toast-action').addEventListener('click', async (e) => {
            e.stopPropagation();
            await opts.action.onClick();
            _dismissToast();
        }, { once: true });
    }

    // Wire up dismiss button
    if (opts.dismissible) {
        toast.querySelector('.toast-dismiss').addEventListener('click', (e) => {
            e.stopPropagation();
            _dismissToast();
        }, { once: true });
    }

    // Auto-dismiss (0 = stay until manual dismiss)
    if (opts.duration > 0) {
        toast._dismissTimer = setTimeout(_dismissToast, opts.duration);
    }
}

function _dismissToast() {
    const toast = document.getElementById('toast');
    toast.classList.remove('show');
    clearTimeout(toast._dismissTimer);
}

// Toggle dropdown menu
function toggleDropdown(btn) {
    const menu = btn.nextElementSibling;
    const isOpen = menu.classList.contains('show');
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
    if (!isOpen) menu.classList.add('show');
}

// Close dropdowns when clicking outside
document.addEventListener('click', (e) => {
    if (!e.target.closest('.dropdown')) {
        document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
    }
});

// Show Chrome browser
async function showChrome() {
    showToast('Focusing Chrome…');
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/chrome`);
        const data = await response.json();
        showToast(data.message || 'Chrome focused', 'success');
    } catch (e) {
        showToast('Failed to focus Chrome', 'error');
    }
}
