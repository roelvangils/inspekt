// =============================================
// Split Mode
// =============================================

function toggleSplitMode() {
    // Don't enter split if window too narrow
    if (terminalMode === 'floating' && window.innerWidth < 700) return;

    if (terminalMode === 'floating') {
        enterSplitMode();
    } else {
        exitSplitMode();
    }
}

// Exit split mode if window becomes too narrow
window.addEventListener('resize', () => {
    if (terminalMode === 'split' && window.innerWidth < 700) {
        exitSplitMode();
    }
    updateSplitButton();
});

function enterSplitMode() {
    terminalMode = 'split';
    const overlay = document.getElementById('terminalOverlay');
    const handle = document.getElementById('splitDragHandle');

    // Remove floating classes
    overlay.classList.remove('open', 'position-left');
    overlay.inert = false;

    // Activate split mode on body
    document.body.classList.add('split-mode');
    if (splitFlipped) {
        document.body.classList.add('split-flipped');
    }

    // Show drag handle
    handle.style.display = '';

    // Set VNC width from ratio
    document.body.style.setProperty('--split-vnc-width', (splitRatio * 100) + '%');

    // Mark terminal as open
    isTerminalOpen = true;
    const termBtn = document.querySelector('button[onclick="toggleTerminal()"]');
    if (termBtn) termBtn.classList.add('terminal-active');

    // Update button states
    updateSplitButton();
    updatePositionButton();

    // After layout settles, fit terminal and let VNC ResizeObserver fire
    requestAnimationFrame(() => {
        if (fitAddon) {
            fitAddon.fit();
            sendTerminalSize();
        }
        if (terminal) terminal.focus();
    });

    localStorage.setItem('terminalMode', 'split');
}

function exitSplitMode() {
    terminalMode = 'floating';
    const overlay = document.getElementById('terminalOverlay');
    const handle = document.getElementById('splitDragHandle');

    // Remove split classes
    document.body.classList.remove('split-mode', 'split-flipped', 'split-dragging');

    // Hide drag handle
    handle.style.display = 'none';

    // Restore terminal as floating overlay
    if (terminalPosition === 'left') {
        overlay.classList.add('position-left');
    }

    // Update button states
    updateSplitButton();
    updatePositionButton();

    localStorage.setItem('terminalMode', 'floating');

    // After layout restores, refit (VNC ResizeObserver fires automatically)
    requestAnimationFrame(() => {
        if (fitAddon && isTerminalOpen) {
            fitAddon.fit();
            sendTerminalSize();
        }
    });
}

function flipSplitLayout() {
    if (terminalMode !== 'split') return;
    splitFlipped = !splitFlipped;
    document.body.classList.toggle('split-flipped', splitFlipped);
    localStorage.setItem('splitFlipped', splitFlipped);

    // Invert ratio so the divider bar stays in place visually —
    // VNC gets the width the terminal previously had, and vice versa.
    splitRatio = 1 - splitRatio;
    document.body.style.setProperty('--split-vnc-width', (splitRatio * 100) + '%');
    localStorage.setItem('splitRatio', splitRatio);

    // Refit after layout change (VNC ResizeObserver fires automatically)
    requestAnimationFrame(() => {
        if (fitAddon) {
            fitAddon.fit();
            sendTerminalSize();
        }
    });
}

function updateSplitButton() {
    const btn = document.getElementById('splitModeBtn');
    if (!btn) return;
    const tooNarrow = window.innerWidth < 700;
    btn.classList.toggle('active', terminalMode === 'split');
    btn.disabled = tooNarrow;
    btn.title = tooNarrow ? 'Window too narrow for split view' :
                 terminalMode === 'split' ? 'Exit split view' : 'Split view';
}

// Initialize drag handle
function initSplitDragHandle() {
    const handle = document.getElementById('splitDragHandle');
    if (!handle) return;

    const SNAP_POINTS = [0.25, 1/3, 0.5, 2/3, 0.75];
    const SNAP_THRESHOLD = 0.02; // ~15px at typical widths

    // Prevent flip button clicks from triggering drag
    const flipBtn = handle.querySelector('.split-flip-btn');
    if (flipBtn) {
        flipBtn.addEventListener('mousedown', (e) => {
            e.stopPropagation();
        });
    }

    handle.addEventListener('mousedown', (e) => {
        e.preventDefault();

        isDraggingSplitHandle = true;
        handle.classList.add('dragging');
        document.body.classList.add('split-dragging');

        const contentRow = document.getElementById('splitContentRow');
        const totalWidth = contentRow.offsetWidth - 5; // minus handle width
        const startX = e.clientX;
        const startRatio = splitRatio;

        function onMouseMove(e) {
            const deltaX = e.clientX - startX;
            let newRatio = splitFlipped
                ? startRatio - (deltaX / totalWidth)
                : startRatio + (deltaX / totalWidth);

            // Clamp: minimum 300px for each side
            const minRatio = 300 / totalWidth;
            const maxRatio = 1 - (300 / totalWidth);
            newRatio = Math.max(minRatio, Math.min(maxRatio, newRatio));

            // Snap to common ratios
            for (const snap of SNAP_POINTS) {
                if (Math.abs(newRatio - snap) < SNAP_THRESHOLD) {
                    newRatio = snap;
                    break;
                }
            }

            splitRatio = newRatio;
            document.body.style.setProperty('--split-vnc-width', (splitRatio * 100) + '%');
        }

        function onMouseUp() {
            isDraggingSplitHandle = false;
            handle.classList.remove('dragging');
            document.body.classList.remove('split-dragging');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);

            // Refit both panels
            if (fitAddon) {
                fitAddon.fit();
                sendTerminalSize();
            }
            // VNC ResizeObserver fires automatically

            localStorage.setItem('splitRatio', splitRatio);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });

    // Double-click to reset to 50/50
    handle.addEventListener('dblclick', (e) => {
        splitRatio = 0.5;
        document.body.style.setProperty('--split-vnc-width', '50%');
        localStorage.setItem('splitRatio', 0.5);

        requestAnimationFrame(() => {
            if (fitAddon) {
                fitAddon.fit();
                sendTerminalSize();
            }
        });
    });
}

const LIGHT_TERMINAL_THEMES = new Set(['tomorrow', 'github', 'catppuccin-latte', 'solarized-light']);

function applyTerminalTheme(themeName) {
    if (!terminal) return;
    const theme = TERMINAL_THEMES[themeName];
    if (theme) {
        terminal.options.theme = theme;
        localStorage.setItem('terminalTheme', themeName);
        // Tag overlay so CSS can match the theme's light/dark scheme
        const overlay = document.querySelector('.terminal-overlay');
        if (overlay) overlay.dataset.terminalScheme = LIGHT_TERMINAL_THEMES.has(themeName) ? 'light' : 'dark';
        // Sync editor theme with terminal
        syncEditorTheme();
    }
}

/** Adjust terminal font size and persist to localStorage */
function adjustTerminalFontSize(delta) {
    if (!terminal) return;
    const current = terminal.options.fontSize || 14;
    const next = Math.max(8, Math.min(24, current + delta));
    terminal.options.fontSize = next;
    localStorage.setItem('terminalFontSize', next);
    if (fitAddon) fitAddon.fit();
}

let terminalInitialized = false; // Ensure we only connect ONCE

function connectTerminal() {
    if (terminalInitialized) {
        console.log('[Terminal] Already initialized, skipping');
        return;
    }
    terminalInitialized = true;
    console.log('[Terminal] Initializing connection...');

    const container = document.getElementById('terminalContainer');

    // Create terminal
    if (!terminal) {
        console.log('[Terminal] Creating terminal instance');
        const savedTheme = localStorage.getItem('terminalTheme') || 'tokyo-night';
        terminal = new Terminal({
            cursorBlink: true,
            fontSize: parseInt(localStorage.getItem('terminalFontSize')) || 14,
            fontFamily: "'JetBrains Mono NF', 'JetBrains Mono', Menlo, Monaco, monospace",
            theme: TERMINAL_THEMES[savedTheme] || TERMINAL_THEMES['tokyo-night'],
            lineHeight: 1.2,
            letterSpacing: 0
        });
        // Set dropdown to match saved theme and tag overlay for CSS
        document.getElementById('terminalTheme').value = savedTheme;
        const overlay = document.querySelector('.terminal-overlay');
        if (overlay) overlay.dataset.terminalScheme = LIGHT_TERMINAL_THEMES.has(savedTheme) ? 'light' : 'dark';

        fitAddon = new FitAddon.FitAddon();
        terminal.loadAddon(fitAddon);

        // Custom link handler - respects dropdown setting and handles file:// URLs
        const linkHandler = async (event, uri) => {
            event.preventDefault();

            // Handle file:// URLs - download from VM
            if (uri.startsWith('file://')) {
                const filePath = uri.replace('file://', '');
                try {
                    const checkUrl = `http://${VNC_HOST}:${CONTROL_PORT}/file-exists?path=${encodeURIComponent(filePath)}`;
                    const checkResp = await fetch(checkUrl);
                    const data = await checkResp.json();

                    if (data.exists) {
                        showToast(`Downloading: ${data.filename}`, 'success');
                        // Use fetch + blob to avoid cross-origin navigation
                        const downloadUrl = `http://${VNC_HOST}:${CONTROL_PORT}/download?path=${encodeURIComponent(filePath)}`;
                        const downloadResp = await fetch(downloadUrl);
                        if (!downloadResp.ok) throw new Error(`HTTP ${downloadResp.status}`);

                        const blob = await downloadResp.blob();
                        const blobUrl = URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = blobUrl;
                        a.download = data.filename;
                        a.click();
                        setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
                    } else {
                        showToast(`File not found: ${filePath}`, 'error');
                    }
                } catch (err) {
                    console.error('File download failed:', err);
                    showToast(`Error: ${err.message}`, 'error');
                }
                return;
            }

            const linkTarget = document.getElementById('linkTarget').value;
            let openInVM = false;

            if (linkTarget === 'vm') {
                openInVM = true;
            } else if (linkTarget === 'host') {
                openInVM = false;
            } else if (linkTarget === 'auto') {
                // Auto-decide based on hostname
                try {
                    const url = new URL(uri);
                    const hostname = url.hostname.toLowerCase();
                    // Check if localhost, inspekt, or IP address
                    const isLocal = hostname === 'localhost' ||
                                   hostname === 'inspekt' ||
                                   hostname === '127.0.0.1' ||
                                   hostname === '0.0.0.0' ||
                                   /^(\d{1,3}\.){3}\d{1,3}$/.test(hostname) ||  // IPv4
                                   hostname.startsWith('[') ||  // IPv6
                                   hostname === '::1';
                    openInVM = isLocal;
                } catch (e) {
                    openInVM = false;
                }
            }

            if (openInVM) {
                // Open in VM's browser in a NEW TAB via control server
                fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=${encodeURIComponent(uri)}`)
                    .then(response => {
                        if (response.ok) {
                            showToast(`Opening in VM (new tab): ${uri}`, 'success');
                        } else {
                            showToast('Failed to open URL', 'error');
                        }
                    })
                    .catch(() => showToast('Failed to open URL', 'error'));
            } else {
                // Open in host browser in a NEW TAB
                window.open(uri, '_blank', 'noopener,noreferrer');
                showToast(`Opening in host (new tab): ${uri}`, 'success');
            }
        };

        // Standard WebLinksAddon for http/https URLs
        const webLinksAddon = new WebLinksAddon.WebLinksAddon(linkHandler);
        terminal.loadAddon(webLinksAddon);

        // File path link provider - detects /root/... paths and makes them downloadable
        terminal.registerLinkProvider({
            provideLinks: (bufferLineNumber, callback) => {
                const line = terminal.buffer.active.getLine(bufferLineNumber);
                if (!line) {
                    callback(undefined);
                    return;
                }

                const text = line.translateToString(true);

                // Debug: log every line being checked
                if (text.includes('/root') || text.includes('/tmp')) {
                    console.log('[LinkProvider] Checking line:', bufferLineNumber, '→', JSON.stringify(text));
                }

                const links = [];

                // Simple regex: match paths starting with /root/ or /tmp/ etc.
                const regex = /\/(?:root|tmp|home|opt)\/[\w.\-\/]+/g;
                let match;

                while ((match = regex.exec(text)) !== null) {
                    const filePath = match[0];
                    const startX = match.index + 1;
                    const endX = startX + filePath.length;

                    console.log('[LinkProvider] Found path:', filePath, 'at', startX, '-', endX);

                    links.push({
                        range: {
                            start: { x: startX, y: bufferLineNumber + 1 },
                            end: { x: endX, y: bufferLineNumber + 1 }
                        },
                        text: filePath,
                        activate: async (event, text) => {
                            console.log('[LinkProvider] Clicked:', text);
                            try {
                                const checkResp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file-exists?path=${encodeURIComponent(text)}`);
                                const data = await checkResp.json();
                                if (data.exists) {
                                    if (data.size > 1048576) {
                                        showToast('File too large for editor (max 1 MB)', 'error');
                                        return;
                                    }
                                    openFileInEditor(text);
                                } else {
                                    showToast(`File not found: ${text}`, 'error');
                                }
                            } catch (e) {
                                showToast(`Error: ${e.message}`, 'error');
                            }
                        }
                    });
                }

                console.log('[LinkProvider] Returning', links.length, 'links for line', bufferLineNumber);
                callback(links.length > 0 ? links : undefined);
            }
        });
        console.log('[Terminal] LinkProvider registered successfully');

        terminal.open(container);
        console.log('[Terminal] Terminal opened');
        fitAddon.fit();

        // Auto-focus terminal on hover so users can type immediately
        container.addEventListener('mouseenter', () => {
            if (activePanel === 'terminal' && !_uploadActive) {
                terminal.focus();
            }
        });

        // Intercept Escape key to close terminal instead of sending to shell
        terminal.attachCustomKeyEventHandler((event) => {
            // Only capture keys when terminal is actually open/visible
            if (!isTerminalOpen) {
                return false; // Don't capture any keys when terminal is hidden
            }

            if (event.key === 'Escape' && event.type === 'keydown') {
                // In split mode, Escape should not close the terminal —
                // it's a persistent panel, not a dismissible overlay.
                // Let the key pass through to the shell (e.g. cancel a command).
                if (terminalMode === 'split') {
                    return true; // Let xterm.js handle it normally
                }
                // Floating mode: close the terminal overlay
                event.stopPropagation();
                event.preventDefault();
                toggleTerminal();
                return false;
            }

            // Cmd+Shift+K (Mac) or Ctrl+Shift+K to clear terminal
            // (Cmd/Ctrl+K without Shift opens the command palette)
            if (event.key === 'k' && event.type === 'keydown' && event.shiftKey && (event.metaKey || event.ctrlKey)) {
                event.stopPropagation();
                event.preventDefault();
                terminal.clear();  // Clear xterm.js scrollback
                // Send Ctrl+L to PTY to clear screen and redraw prompt
                if (terminalSocket && terminalSocket.readyState === WebSocket.OPEN) {
                    terminalSocket.send('\x0c');
                }
                return false;
            }

            // Cmd+K (Mac) or Ctrl+K to toggle command palette
            if (event.key === 'k' && event.type === 'keydown' && !event.shiftKey && (event.metaKey || event.ctrlKey)) {
                event.stopPropagation();
                event.preventDefault();
                const ninja = document.getElementById('commandPalette');
                if (ninja) ninja.visible ? ninja.close() : ninja.open();
                return false;
            }

            // Allow all other keys to be processed normally (when terminal is open)
            return true;
        });

        // Handle terminal input
        terminal.onData(data => {
            if (terminalSocket && terminalSocket.readyState === WebSocket.OPEN) {
                terminalSocket.send(data);
            }
        });

        // Handle resize — both window-level and container-level (catches
        // CSS transitions, panel toggles, and any other layout changes)
        window.addEventListener('resize', () => {
            if (isTerminalOpen && fitAddon) {
                fitAddon.fit();
                sendTerminalSize();
            }
        });
        const termResizeObserver = new ResizeObserver(() => {
            if (isTerminalOpen && fitAddon) {
                fitAddon.fit();
                sendTerminalSize();
            }
        });
        termResizeObserver.observe(container);
    }

    // Connect WebSocket
    const cols = terminal.cols;
    const rows = terminal.rows;
    const wsUrl = `ws://${VNC_HOST}:${TERMINAL_PORT}?cols=${cols}&rows=${rows}`;

    terminal.writeln('\x1b[33mConnecting to terminal...\x1b[0m');

    terminalSocket = new WebSocket(wsUrl);

    terminalSocket.onopen = () => {
        terminal.writeln('\x1b[32mConnected!\x1b[0m\r\n');
        terminal.focus();
        fitAddon.fit();
        sendTerminalSize();
        hasTerminalSession = true; // Mark that we have an active session
    };

    terminalSocket.onmessage = (event) => {
        const data = event.data;

        // Check for download escape sequences and trigger downloads
        let match;
        DOWNLOAD_MARKER_REGEX.lastIndex = 0; // Reset regex state
        while ((match = DOWNLOAD_MARKER_REGEX.exec(data)) !== null) {
            const filePath = match[1];
            triggerFileDownload(filePath);
        }

        // Check for edit escape sequences and open in editor
        EDIT_MARKER_REGEX.lastIndex = 0;
        let editMatch;
        while ((editMatch = EDIT_MARKER_REGEX.exec(data)) !== null) {
            openFileInEditor(editMatch[1]);
        }

        // Check for upload signal and show upload overlay
        UPLOAD_MARKER_REGEX.lastIndex = 0;
        if (UPLOAD_MARKER_REGEX.test(data)) {
            showUploadOverlay();
        }

        // Check for clipboard signal and relay to host clipboard
        CLIPBOARD_SIGNAL_REGEX.lastIndex = 0;
        if (CLIPBOARD_SIGNAL_REGEX.test(data)) {
            handleClipboardSignal();
        }

        // Check for copyable code block signal and show interactive copy toast
        COPYABLE_SIGNAL_REGEX.lastIndex = 0;
        if (COPYABLE_SIGNAL_REGEX.test(data)) {
            showToast('Code block ready to copy', {
                type: 'dark',
                duration: 10000,
                dismissible: true,
                action: {
                    label: 'Copy',
                    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>',
                    onClick: async () => {
                        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/copyable`);
                        const d = await resp.json();
                        if (d.ok && d.text) {
                            await writeClipboard(d.text);
                            showToast('Copied!', 'success');
                        }
                    }
                }
            });
        }

        // Check for toast signal and show toast in control panel
        TOAST_SIGNAL_REGEX.lastIndex = 0;
        if (TOAST_SIGNAL_REGEX.test(data)) {
            handleToastSignal();
        }

        // Check for hide-terminal escape sequence
        // CLI tools emit this to request terminal auto-hide (e.g., when recording starts)
        HIDE_TERMINAL_REGEX.lastIndex = 0; // Reset before test (global regex)
        const hasHideSignal = HIDE_TERMINAL_REGEX.test(data);
        console.log('[Terminal] Message received, isTerminalOpen:', isTerminalOpen, 'hasHideSignal:', hasHideSignal);
        if (hasHideSignal) {
            console.log('[Terminal] Hide signal detected! Raw data:', JSON.stringify(data.slice(0, 100)));
        }
        if (isTerminalOpen && hasHideSignal) {
            console.log('[Terminal] Hiding terminal now');
            setTimeout(() => {
                toggleTerminal(); // Close terminal and focus VNC
            }, 100);
            // Start polling terminal state so we know when recording ends
            if (typeof startTerminalStatePolling === 'function') startTerminalStatePolling();
        }

        // Strip escape sequences before writing to terminal
        let cleanData = data.replace(DOWNLOAD_MARKER_REGEX, '');
        cleanData = cleanData.replace(EDIT_MARKER_REGEX, '');
        cleanData = cleanData.replace(UPLOAD_MARKER_REGEX, '');
        cleanData = cleanData.replace(HIDE_TERMINAL_REGEX, '');
        cleanData = cleanData.replace(CLIPBOARD_SIGNAL_REGEX, '');
        cleanData = cleanData.replace(COPYABLE_SIGNAL_REGEX, '');
        cleanData = cleanData.replace(TOAST_SIGNAL_REGEX, '');
        terminal.write(cleanData);

        // Scan for trigger words (debounced)
        checkTriggerWords(cleanData);
    };

    terminalSocket.onclose = () => {
        hasTerminalSession = false; // Session ended
        if (isTerminalOpen) {
            terminal.writeln('\r\n\x1b[31mDisconnected from terminal.\x1b[0m');
        }
    };

    terminalSocket.onerror = (error) => {
        terminal.writeln('\r\n\x1b[31mConnection error. Is the VM running?\x1b[0m');
        console.error('[Terminal] WebSocket error:', error);
    };
}

function disconnectTerminal() {
    if (terminalSocket) {
        terminalSocket.close();
        terminalSocket = null;
    }
}

function sendTerminalSize() {
    if (terminalSocket && terminalSocket.readyState === WebSocket.OPEN && terminal) {
        const resizeMsg = JSON.stringify({
            type: 'resize',
            cols: terminal.cols,
            rows: terminal.rows
        });
        terminalSocket.send(resizeMsg);
    }
}

// Legacy function for compatibility
function showTerminal() {
    toggleTerminal();
}

// See audio.js
