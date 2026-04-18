// =============================================
// Terminal File Download
// =============================================

// Regex to detect download escape sequences: OSC 1337 ; download=<path> BEL
const DOWNLOAD_MARKER_REGEX = /\x1b\]1337;download=([^\x07]+)\x07/g;

// Regex to detect edit-file escape sequence: OSC 1337 ; edit=<path> BEL
const EDIT_MARKER_REGEX = /\x1b\]1337;edit=([^\x07]+)\x07/g;

// Regex to detect upload-ready escape sequence: OSC 1337 ; upload BEL
const UPLOAD_MARKER_REGEX = /\x1b\]1337;upload\x07/g;

// Regex to detect hide-terminal escape sequence: OSC 1337 ; hide-terminal BEL
const HIDE_TERMINAL_REGEX = /\x1b\]1337;hide-terminal\x07/g;

// Regex to detect clipboard signal: OSC 1337 ; clipboard BEL
// When detected, fetch clipboard text from control server and copy to host clipboard
const CLIPBOARD_SIGNAL_REGEX = /\x1b\]1337;clipboard\x07/g;

// Regex to detect copyable code block signal: OSC 1337 ; copyable BEL
// When detected, show a floating copy button on the terminal
const COPYABLE_SIGNAL_REGEX = /\x1b\]1337;copyable\x07/g;

// Regex to detect toast signal: OSC 1337 ; toast BEL
// When detected, fetch toast message from control server and show it
const TOAST_SIGNAL_REGEX = /\x1b\]1337;toast\x07/g;

// Regex to detect structured-data signal: OSC 1337 ; data BEL
// When detected, fetch {json, table_md, summary} from /data and show a
// "Data ready to copy" toast with [Table] and/or [JSON] action buttons.
const DATA_SIGNAL_REGEX = /\x1b\]1337;data\x07/g;

// SVGs for the toast actions (kept here so split-mode.js stays readable).
const TABLE_ICON_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3h18v18H3z"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>';
const JSON_ICON_SVG = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3a3 3 0 00-3 3v3a3 3 0 01-3 3 3 3 0 013 3v3a3 3 0 003 3"/><path d="M16 3a3 3 0 013 3v3a3 3 0 003 3 3 3 0 00-3 3v3a3 3 0 01-3 3"/></svg>';

async function handleDataSignal() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/data`);
        const d = await resp.json();
        if (!d.ok) return;

        const actions = [];
        if (d.table_md) {
            actions.push({
                label: 'Table',
                icon: TABLE_ICON_SVG,
                onClick: async () => {
                    await writeClipboard(d.table_md);
                    showToast('Table copied', 'success');
                },
            });
        }
        if (d.json) {
            actions.push({
                label: 'JSON',
                icon: JSON_ICON_SVG,
                onClick: async () => {
                    await writeClipboard(d.json);
                    showToast('JSON copied', 'success');
                },
            });
        }
        if (!actions.length) return;

        const message = d.summary
            ? `Data ready to copy — ${d.summary}`
            : 'Data ready to copy';

        showToast(message, {
            type: 'dark',
            duration: 10000,
            dismissible: true,
            actions,
        });
    } catch (err) {
        console.warn('[Terminal] Data relay failed:', err);
    }
}

async function handleToastSignal() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/toast`);
        const data = await resp.json();
        if (data.ok && data.message) {
            showToast(data.message, { type: data.type || 'dark', duration: 2500 });
        }
    } catch (err) {
        console.warn('[Terminal] Toast relay failed:', err);
    }
}

async function handleClipboardSignal() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/clipboard`);
        const data = await resp.json();
        if (data.ok && data.text) {
            await writeClipboard(data.text);
            // Silent success — the CLI command already prints its own confirmation
        }
    } catch (err) {
        console.warn('[Terminal] Clipboard relay failed:', err);
    }
}

async function triggerFileDownload(filePath) {
    // Use fetch + blob to avoid cross-origin navigation issue
    // (anchor click with download attribute fails cross-origin and navigates instead)
    const filename = filePath.split('/').pop();
    const downloadUrl = `http://${VNC_HOST}:${CONTROL_PORT}/download?path=${encodeURIComponent(filePath)}`;

    try {
        const response = await fetch(downloadUrl);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const blob = await response.blob();
        const blobUrl = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        a.click();

        // Clean up blob URL after download starts
        setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
        showToast(`Downloaded: ${filename}`, 'success');
    } catch (error) {
        console.error('[Download] Failed:', error);
        showToast(`Download failed: ${error.message}`, 'error');
    }
}

// =============================================
// Terminal Management
// =============================================

// Directory history for context menu back/forward navigation.
// Only tracks menu-initiated cd commands (not manual typing).
const _termCwdHistory = [];
let _termCwdPos = -1;  // Index into history; -1 = no menu navigation yet

/** Send a command to the terminal, styled dim+italic to show it was menu-initiated.
 *  Ctrl-U clears any current input before sending. */
function _sendTerminalCommand(cmd) {
    if (!terminalSocket || terminalSocket.readyState !== WebSocket.OPEN) return;
    // Capture the absolute row where the command will be echoed (current prompt line)
    const buf = terminal?.buffer?.active;
    const cmdAbsRow = buf ? buf.baseY + buf.cursorY : -1;

    terminalSocket.send(`\x15${cmd}\r`);

    // Restyle after the shell echoes the command.
    // Uses the saved absolute row so multi-line output doesn't throw off positioning.
    setTimeout(() => {
        if (!terminal || cmdAbsRow < 0) return;
        const currentBuf = terminal.buffer.active;
        const line = currentBuf.getLine(cmdAbsRow);
        if (!line) return;
        const text = line.translateToString(true).trimEnd();
        const splitPos = text.indexOf('$ ');
        if (splitPos === -1) return;
        const prompt = text.slice(0, splitPos + 2);
        const cmdText = text.slice(splitPos + 2);
        // Convert absolute row to viewport-relative (CUP is 1-based)
        const viewportRow = cmdAbsRow - currentBuf.baseY + 1;
        if (viewportRow < 1 || viewportRow > terminal.rows) return; // scrolled off
        terminal.write(
            '\x1b7' +
            `\x1b[${viewportRow};1H` +
            '\x1b[2K' +
            `${prompt}\x1b[2;3m${cmdText}\x1b[0m` +
            '\x1b8'
        );
    }, 100);
}

/** Quote a string for safe use in shell commands */
function _shellQuote(s) {
    return `'${s.replace(/'/g, "'\\''")}'`;
}

/** Send a cd command (quoted) via _sendTerminalCommand */
function _sendCd(dir) {
    _sendTerminalCommand(`cd ${_shellQuote(dir)}`);
}

/** Send a cd command and track it in navigation history */
function sendTerminalCd(targetDir) {
    if (!targetDir) return;
    // Seed history with current dir on first menu navigation
    if (_termCwdHistory.length === 0 || _termCwdPos === -1) {
        const history = _parseTerminalHistory();
        _termCwdHistory.length = 0;
        _termCwdHistory.push(history?.cwd || '/home/inspekt');
        _termCwdPos = 0;
    }
    // Truncate forward history, push new destination
    _termCwdHistory.length = _termCwdPos + 1;
    _termCwdHistory.push(targetDir);
    _termCwdPos = _termCwdHistory.length - 1;
    _sendCd(targetDir);
}

function canTerminalGoBack() {
    return _termCwdPos > 0;
}

function canTerminalGoForward() {
    return _termCwdPos >= 0 && _termCwdPos < _termCwdHistory.length - 1;
}

function terminalGoBack() {
    if (!canTerminalGoBack()) return;
    _termCwdPos--;
    _sendCd(_termCwdHistory[_termCwdPos]);
}

function terminalGoForward() {
    if (!canTerminalGoForward()) return;
    _termCwdPos++;
    _sendCd(_termCwdHistory[_termCwdPos]);
}

function toggleTerminal() {
    const overlay = document.getElementById('terminalOverlay');
    const termBtn = document.querySelector('button[onclick="toggleTerminal()"]');

    if (isTerminalOpen) {
        // Check for unsaved editor changes before closing
        if (!confirmEditorClose()) return;

        // If in split mode, exit split first then close
        if (terminalMode === 'split') {
            exitSplitMode();
        }

        // Hide terminal (keep session alive)
        overlay.classList.remove('open');
        overlay.inert = true; // Make overlay non-interactive while hidden
        if (termBtn) termBtn.classList.remove('terminal-active');
        isTerminalOpen = false;

        // Reset to terminal tab so next open shows terminal
        // (bypass confirm since we already confirmed above)
        if (activePanel === 'editor') {
            activePanel = 'terminal';
            document.getElementById('terminalContainer').style.display = '';
            document.getElementById('editorContainer').style.display = 'none';
            document.getElementById('tabTerminal').classList.add('active');
            document.getElementById('tabEditor').classList.remove('active');
        }

        // Try to auto-focus VNC (best effort, no blocking overlay)
        setTimeout(() => tryFocusVNC(), 100);
    } else {
        // If user's last mode was split, re-enter split mode
        if (localStorage.getItem('terminalMode') === 'split') {
            enterSplitMode();
            return;
        }

        // Show terminal (floating)
        overlay.classList.add('open');
        overlay.inert = false; // Make overlay interactive when shown
        if (termBtn) termBtn.classList.add('terminal-active');
        isTerminalOpen = true;

        // Focus the terminal and sync PTY size
        if (terminal) {
            terminal.focus();
            if (fitAddon) {
                fitAddon.fit();
                sendTerminalSize();
            }
        }
    }
}

function toggleTerminalPosition() {
    if (terminalMode === 'split') {
        flipSplitLayout();
        return;
    }
    const overlay = document.getElementById('terminalOverlay');
    const wasOpen = overlay.classList.contains('open');

    if (wasOpen) {
        overlay.classList.remove('open'); // slide out current side
    }

    setTimeout(() => {
        if (terminalPosition === 'right') {
            overlay.classList.add('position-left');
            terminalPosition = 'left';
        } else {
            overlay.classList.remove('position-left');
            terminalPosition = 'right';
        }
        updatePositionButton();
        localStorage.setItem('terminalPosition', terminalPosition);

        if (wasOpen) {
            // Force reflow then slide in from new side
            void overlay.offsetHeight;
            overlay.classList.add('open');
            if (fitAddon) {
                requestAnimationFrame(() => {
                    fitAddon.fit();
                    sendTerminalSize();
                });
            }
        }
    }, wasOpen ? 320 : 0);
}

function updatePositionButton() {
    const btn = document.getElementById('terminalPositionBtn');
    if (!btn) return;
    const isLeft = terminalPosition === 'left';
    // Arrow pointing toward the other side
    btn.innerHTML = isLeft
        ? '<svg viewBox="0 0 24 24"><path d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6z"/></svg>'
        : '<svg viewBox="0 0 24 24"><path d="M15.41 16.59L10.83 12l4.58-4.59L14 6l-6 6 6 6z"/></svg>';
    btn.title = isLeft ? 'Move to right side' : 'Move to left side';
}

// Restore terminal position on load
(function restoreTerminalPosition() {
    if (terminalPosition === 'left') {
        const overlay = document.getElementById('terminalOverlay');
        if (overlay) overlay.classList.add('position-left');
        updatePositionButton();
    }
})();
