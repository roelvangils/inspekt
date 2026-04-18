// =============================================
// Focus Overlay (click-to-interact prompt)
// =============================================

/**
 * Try to focus the VNC canvas directly without user interaction.
 * With direct RFB embedding, we just call rfb.focus() — no iframe boundary.
 */
function tryFocusVNC() {
    if (!rfb) return false;
    rfb.focus();
    // Also call /chrome/click to focus AND click in the VM-side Chromium
    // This uses xdotool to activate the window and click, enabling keyboard input
    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/chrome/click`).catch(() => {});
    console.log('[Inspekt] Requested VM-side focus via xdotool');
    return true;
}

function showFocusOverlay() {
    const overlay = document.getElementById('focusOverlay');
    overlay.classList.add('visible');
}

function hideFocusOverlay() {
    const overlay = document.getElementById('focusOverlay');
    overlay.classList.remove('visible');

    // After hiding overlay, try to focus the VNC canvas
    // This may work since we just had a real user click
    setTimeout(() => {
        if (rfb) rfb.focus();
        // Also trigger Chrome focus inside VM
        fetch(`http://${VNC_HOST}:${CONTROL_PORT}/chrome`).catch(() => {});
    }, 50);
}


// ── Shift+Tab ─────────────────────────────────────────
// With direct RFB embedding (no iframe), Shift+Tab
// propagates normally through the DOM — no workaround needed.
// See: https://github.com/novnc/noVNC/issues/1413
// ──────────────────────────────────────────────────────────

// ── Shift+Tab fix ──────────────────────────────────────
// noVNC on Mac strips the Shift modifier from Tab when
// encoding through the VNC protocol. The Tab keydown
// event is consumed by noVNC internally (never propagates),
// but the Tab keyup DOES propagate.
//
// Fix: track Shift state via keydown/keyup on the canvas.
// When Tab keyup arrives while Shift is held, send
// XK_ISO_Left_Tab (0xFE20) via rfb.sendKey() — the
// standard X11 keysym for backward tab navigation.
//
// We briefly ungrab the keyboard to prevent noVNC from
// also sending its own (broken) version of the event.
//
// See: https://github.com/novnc/noVNC/issues/1413
// ──────────────────────────────────────────────────────
(function setupShiftTabFix() {
    let shiftHeld = false;
    const _isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
    // Keys to translate from Cmd to Ctrl on macOS (NOT 'c' — clipboard copy is handled separately)
    // Zoom keys (=, -, 0) are handled separately to avoid native Chromium zoom widget
    const _CMD_CTRL_KEYS = new Set(['a', 'v', 'x', 'z', 'f', 'r', 's']);
    const XK_Control_L = 0xFFE3;
    const XK_Shift_L = 0xFFE1;

    // Wait for RFB to be ready, then monkey-patch its keyboard handler
    function attach() {
        if (!rfb || !rfb._keyboard) { setTimeout(attach, 500); return; }

        const canvas = document.querySelector('#vncContainer canvas');
        if (!canvas) { setTimeout(attach, 500); return; }

        // Track Shift state from canvas events (these always propagate)
        canvas.addEventListener('keydown', (e) => {
            if (e.key === 'Shift') shiftHeld = true;
        }, true);
        canvas.addEventListener('keyup', (e) => {
            if (e.key === 'Shift') shiftHeld = false;
        }, true);

        // Monkey-patch noVNC's keyboard event handler to intercept:
        // 1. Tab keys (Shift+Tab fix for macOS noVNC bug)
        // 2. Cmd+key → Ctrl+key translation for macOS users
        //
        // Both must live in this handler because it participates in
        // noVNC's keyboard pipeline — sendKey() calls from here are
        // proven to work (unlike from document-level handlers which
        // are outside noVNC's event flow).
        const kb = rfb._keyboard;
        const origHandler = kb._eventHandlers.keydown;
        const patchedHandler = function(e) {
            // When SR simulator is active, block ALL keys from reaching
            // VNC — the SR handler on document (capture phase) processes
            // keyboard input and translates it to accessibility navigation.
            if (srActive) {
                e.preventDefault();
                e.stopImmediatePropagation();
                return;
            }

            // Tab handling: explicit sendKey for each repeat event
            if (e.code === 'Tab') {
                e.preventDefault();
                e.stopImmediatePropagation();
                if (shiftHeld) {
                    rfb.sendKey(0xFE20, 'Tab', true);   // XK_ISO_Left_Tab
                    rfb.sendKey(0xFE20, 'Tab', false);
                } else {
                    rfb.sendKey(0xFF09, 'Tab', true);   // XK_Tab
                    rfb.sendKey(0xFF09, 'Tab', false);
                }
                return;
            }

            // Cmd/Ctrl+K: open command palette (intercept before noVNC
            // forwards the keystroke to the VM)
            if (e.key === 'k' && !e.altKey && ((_isMac && e.metaKey) || (!_isMac && e.ctrlKey))) {
                e.preventDefault();
                e.stopImmediatePropagation();
                // Release Meta that noVNC sent when Cmd was pressed
                if (_isMac) rfb.sendKey(0xFFE7, 'MetaLeft', false);
                const ninja = document.getElementById('commandPalette');
                if (ninja) ninja.visible ? ninja.close() : ninja.open();
                return;
            }

            // Zoom handling: intercept zoom shortcuts and use the extension
            // API instead of forwarding to Chromium (avoids native zoom widget)
            if (((_isMac && e.metaKey) || (!_isMac && e.ctrlKey)) && !e.altKey) {
                if (e.key === '=' || e.key === '+' || e.key === '-' || e.key === '0') {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    // Release Meta/Ctrl that noVNC may have sent
                    if (_isMac) rfb.sendKey(0xFFE7, 'MetaLeft', false);
                    const action = (e.key === '=' || e.key === '+') ? 'in' : e.key === '-' ? 'out' : 'reset';
                    handleZoom(action);
                    return;
                }
            }

            // macOS Cmd → Ctrl translation: intercept Cmd+key and send
            // the Ctrl equivalent to the Linux VM via sendKey().
            //
            // Critical: noVNC already sent Meta_L (Cmd) keydown to the
            // VM when the user first pressed Cmd. We must release Meta
            // before sending Ctrl+key, otherwise the VM sees
            // Meta+Ctrl+key instead of just Ctrl+key.
            if (_isMac && e.metaKey && !e.altKey) {
                const key = e.key.toLowerCase();
                if (_CMD_CTRL_KEYS.has(key)) {
                    e.preventDefault();
                    e.stopImmediatePropagation();
                    const keysym = key.charCodeAt(0);
                    // Release Meta that noVNC sent when Cmd was pressed
                    rfb.sendKey(0xFFE7, 'MetaLeft', false);   // XK_Meta_L up
                    // Send the Ctrl+key equivalent
                    rfb.sendKey(XK_Control_L, 'ControlLeft', true);
                    if (e.shiftKey) rfb.sendKey(XK_Shift_L, 'ShiftLeft', true);
                    rfb.sendKey(keysym, `Key${key.toUpperCase()}`, true);
                    rfb.sendKey(keysym, `Key${key.toUpperCase()}`, false);
                    if (e.shiftKey) rfb.sendKey(XK_Shift_L, 'ShiftLeft', false);
                    rfb.sendKey(XK_Control_L, 'ControlLeft', false);
                    return;
                }
            }

            return origHandler(e);
        };
        // Swap the listener: remove old, register new
        canvas.removeEventListener('keydown', origHandler);
        canvas.addEventListener('keydown', patchedHandler);
        // Update the reference so ungrab/grab uses our version
        kb._eventHandlers.keydown = patchedHandler;
    }
    attach();
})();

// Cmd+=/Cmd+-/Cmd+0: Zoom in/out/reset — intercept at document level
// (capture phase) to prevent both the local browser and noVNC from
// handling these shortcuts. Zoom is applied via the extension API.
document.addEventListener('keydown', (e) => {
    const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
    const modHeld = isMac ? e.metaKey : e.ctrlKey;
    if (!modHeld || e.altKey) return;
    if (e.key === '=' || e.key === '+' || e.key === '-' || (e.key === '0' && !e.shiftKey)) {
        e.preventDefault();
        e.stopImmediatePropagation();
        const action = (e.key === '=' || e.key === '+') ? 'in' : e.key === '-' ? 'out' : 'reset';
        handleZoom(action);
    }
}, true);

// Cmd+L: focus control panel address bar (macOS only).
// This is at document level because it doesn't interact with VNC —
// the Cmd→Ctrl translation for VNC keys lives in the patched noVNC
// keyboard handler above (setupShiftTabFix).
// Note: Cmd+T/W cannot be intercepted — Chrome handles them at the
// browser level before JavaScript sees them.
if (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) {
    document.addEventListener('keydown', (e) => {
        if (!e.metaKey || e.altKey) return;
        if (e.key.toLowerCase() === 'l') {
            const termOverlay = document.getElementById('terminalOverlay');
            const inTerminal = termOverlay && termOverlay.classList.contains('open');
            const inInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);
            if (inTerminal || inInput || srActive) return;
            e.preventDefault();
            e.stopImmediatePropagation();
            document.getElementById('urlBar')?.focus();
            document.getElementById('urlBar')?.select();
        }
    }, true);
}

// Smart Cmd/Ctrl+C: copy the right thing based on current focus.
//   - Focused <input>/<textarea>:  copy the text selection
//   - Terminal panel open:         copy the xterm selection
//   - Any other DOM selection:     copy window.getSelection().toString()
//   - Otherwise (VNC canvas):      fetch the VM's selection via the bridge
//
// In Tauri, macOS processes menu accelerators before DOM keydown is
// dispatched, so the native Cmd+C menu item (see menu.rs `smart_copy`)
// invokes this function via Rust `window.eval(...)`. In a regular browser
// (non-Tauri), the document listener below calls it directly.
window.__inspektSmartCopy = async function() {
    const ae = document.activeElement;
    const tag = ae?.tagName;

    // 1) <input> / <textarea>: copy the current text selection
    if (tag === 'INPUT' || tag === 'TEXTAREA') {
        const start = ae.selectionStart, end = ae.selectionEnd;
        if (typeof start === 'number' && typeof end === 'number' && start !== end) {
            await writeClipboard(ae.value.substring(start, end));
        }
        return;
    }

    // 2) xterm.js terminal: has its own selection model
    const termOverlay = document.getElementById('terminalOverlay');
    const inTerminal = termOverlay && termOverlay.classList.contains('open');
    if (inTerminal && typeof terminal !== 'undefined' && terminal && terminal.hasSelection && terminal.hasSelection()) {
        await writeClipboard(terminal.getSelection());
        return;
    }

    // 3) SR simulator owns the keyboard; don't steal Cmd+C
    if (typeof srActive !== 'undefined' && srActive) return;

    // 4) Any other DOM selection (contenteditable, regular text, etc.)
    const sel = window.getSelection && window.getSelection();
    if (sel && sel.toString()) {
        await writeClipboard(sel.toString());
        return;
    }

    // 5) Nothing selected host-side → copy the VM's selection
    runInspektForClipboard('selection text --raw', 'Text');
};

// Browser fallback: in Tauri the menu accelerator handles Cmd+C via Rust,
// so we skip this listener there. In a plain browser, nothing else binds
// Cmd+C, so we run the same smart logic from a capture-phase keydown.
// Must be capture phase — noVNC calls stopPropagation() on canvas keys.
if (!window.__TAURI_INTERNALS__) {
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'c' || !(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return;
        const ae = document.activeElement;
        const tag = ae?.tagName;
        // In native inputs / terminal / SR, let the browser's default copy run
        const termOverlay = document.getElementById('terminalOverlay');
        const inTerminal = termOverlay && termOverlay.classList.contains('open');
        const inInput = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
        if (inTerminal || inInput || srActive) return;
        e.preventDefault();
        e.stopPropagation();
        window.__inspektSmartCopy();
    }, true);
}


