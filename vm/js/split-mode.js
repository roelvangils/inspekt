// =============================================
// Split Mode
// =============================================

// Common viewport widths for Shift-drag magnetic snap. Module-scoped so
// command-palette.js (concatenated into the same global script) can build
// "Set Canvas to <Device>" entries from the same source of truth.
var DEVICE_SNAPS = [
    { width: 375,  label: 'Mobile' },
    { width: 768,  label: 'Tablet' },
    { width: 1024, label: 'iPad Pro' },
    { width: 1280, label: 'Laptop' },
    { width: 1440, label: 'Desktop' },
    { width: 1920, label: 'Wide' },
];

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
    document.body.classList.toggle('split-vertical', splitOrientation === 'vertical');

    // Reset any maximize state from a previous session
    splitMaximized = null;
    document.body.classList.remove('split-maximized-canvas', 'split-maximized-terminal');

    // Show drag handle
    handle.style.display = '';

    // Set pane size from ratio (drives width in horizontal, height in vertical)
    document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');

    // Prefer the last-used device width over the raw ratio when applicable —
    // device widths survive window resizes more meaningfully. Only relevant
    // in horizontal split (the property is a width). offsetWidth here forces
    // a layout, so we read accurate dimensions after the body class change.
    const savedDeviceWidth = parseInt(localStorage.getItem('splitDeviceWidth') || '0', 10);
    if (savedDeviceWidth > 0 && splitOrientation === 'horizontal') {
        const contentRow = document.getElementById('splitContentRow');
        const totalSize = contentRow ? (contentRow.offsetWidth - 5) : 0;
        if (totalSize > 0 && totalSize > savedDeviceWidth + 300) {
            splitRatio = savedDeviceWidth / totalSize;
            document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');
        }
    }

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
    document.body.classList.remove(
        'split-mode', 'split-flipped', 'split-dragging',
        'split-vertical', 'split-maximized-canvas', 'split-maximized-terminal'
    );
    splitMaximized = null;

    // Retract the floating controls if they happened to be open.
    const controls = handle.querySelector('.split-handle-controls');
    try { if (controls && controls.matches(':popover-open')) controls.hidePopover(); }
    catch {}

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
    // VNC gets the size the terminal previously had, and vice versa.
    splitRatio = 1 - splitRatio;
    document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');
    localStorage.setItem('splitRatio', splitRatio);

    _refitAfterLayout();
}

function toggleSplitOrientation() {
    if (terminalMode !== 'split') return;
    splitOrientation = splitOrientation === 'horizontal' ? 'vertical' : 'horizontal';
    document.body.classList.toggle('split-vertical', splitOrientation === 'vertical');
    localStorage.setItem('splitOrientation', splitOrientation);

    // Clear any maximize state when toggling orientation — the saved ratio
    // takes over again.
    if (splitMaximized) {
        splitMaximized = null;
        document.body.classList.remove('split-maximized-canvas', 'split-maximized-terminal');
    }

    _refitAfterLayout();
}

function toggleMaximizePane(which) {
    if (terminalMode !== 'split') return;
    _setMaximizedPane(splitMaximized === which ? null : which);
    _refitAfterLayout();
}

// Internal: update maximize state without triggering a refit (caller decides).
// Used by both toggleMaximizePane and the drag snap-to-edge path.
function _setMaximizedPane(which) {
    splitMaximized = which;
    document.body.classList.toggle('split-maximized-canvas',   which === 'canvas');
    document.body.classList.toggle('split-maximized-terminal', which === 'terminal');
}

// Set the canvas pane to a specific pixel width — used by the per-device
// command-palette entries. Enters split mode and forces horizontal orientation
// when needed (device widths only make sense for the horizontal split).
function setCanvasToDeviceWidth(px) {
    if (terminalMode !== 'split') enterSplitMode();
    if (splitOrientation === 'vertical') toggleSplitOrientation();

    const contentRow = document.getElementById('splitContentRow');
    if (!contentRow) return;
    const totalSize = contentRow.offsetWidth - 5;
    if (totalSize <= 0 || totalSize < px + 300) {
        if (typeof showToast === 'function') {
            showToast(`Window too narrow for a ${px} px canvas`, 'error');
        }
        return;
    }

    if (splitMaximized) _setMaximizedPane(null);
    splitRatio = px / totalSize;
    document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');
    localStorage.setItem('splitRatio', splitRatio);
    localStorage.setItem('splitDeviceWidth', px);
    _refitAfterLayout();
}

// Shared refit hook used after any layout change. VNC ResizeObserver fires
// automatically; we only need to nudge xterm.
function _refitAfterLayout() {
    requestAnimationFrame(() => {
        if (fitAddon) {
            fitAddon.fit();
            sendTerminalSize();
        }
    });
}

// Persist current split state to localStorage. Called from every code path
// that ends a divider gesture (drag mouseup, dblclick reset, wheel tune) so
// `splitDeviceWidth` always reflects the canvas's actual final width — no
// stale device-width restoration on next reload.
function _savePersistedSplitState() {
    if (splitMaximized) return; // maximize state is intentionally not persisted
    localStorage.setItem('splitRatio', splitRatio);

    // Device-width persistence only meaningful in horizontal split.
    if (splitOrientation !== 'horizontal') {
        localStorage.removeItem('splitDeviceWidth');
        return;
    }
    const contentRow = document.getElementById('splitContentRow');
    if (!contentRow) return;
    const totalSize = contentRow.offsetWidth - 5;
    const canvasPx = splitRatio * totalSize;
    const matched = DEVICE_SNAPS.find(s => Math.abs(canvasPx - s.width) < 5);
    if (matched) {
        localStorage.setItem('splitDeviceWidth', matched.width);
    } else {
        localStorage.removeItem('splitDeviceWidth');
    }
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

    // Shift-drag chip (DEVICE_SNAPS lives at module scope). The chip is shown
    // for the full duration of Shift-held and identifies the nearest device
    // target; the actual snap fires on either mouse release or Shift release.
    const snapChip = document.getElementById('snapChip');

    function _showSnapChip(target) {
        if (!snapChip) return;
        snapChip.textContent = `${target.label} · ${target.width} px`;
        snapChip.classList.add('visible', 'engaged');
    }
    function _hideSnapChip() {
        if (!snapChip) return;
        snapChip.classList.remove('visible', 'engaged');
    }

    // Floating buttons + show-on-hover state. Declared up here so every
    // listener below can reference them.
    const controls = handle.querySelector('.split-handle-controls');
    let _showTimer = null;
    const SHOW_DELAY_MS = 120;
    const ANCHOR_OFFSET_PX = 15; // gap between cursor and the first button

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

        // Hide the floating buttons the instant a drag begins — they're
        // distracting overlays on top of the user's intended action.
        clearTimeout(_showTimer);
        try { if (controls && controls.matches(':popover-open')) controls.hidePopover(); }
        catch {}

        const isVertical = splitOrientation === 'vertical';
        const contentRow = document.getElementById('splitContentRow');
        const totalSize = (isVertical ? contentRow.offsetHeight : contentRow.offsetWidth) - 5; // minus handle thickness
        // `let` because the shift-snap commit reassigns these so the drag
        // can continue smoothly from the snapped position.
        let startCoord = isVertical ? e.clientY : e.clientX;
        let startRatio = splitRatio;
        let lastClientX = e.clientX;
        let lastClientY = e.clientY;

        // Past this many pixels from either edge, we treat the drag as a
        // gesture-based maximize of the adjacent pane.
        const EDGE_SNAP_PX = 30;
        const edgeRatio = EDGE_SNAP_PX / totalSize;

        // Tracks the device target nearest the cursor whenever Shift is held.
        // The actual snap fires on either mouse release or Shift release —
        // whichever comes first — so the user gets a clear committed result
        // (with toast) instead of a janky mid-drag jump.
        let shiftSnapTarget = null;

        function commitShiftSnap() {
            if (!shiftSnapTarget || splitMaximized) return false;
            const target = shiftSnapTarget;
            splitRatio = target.width / totalSize;
            document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');
            localStorage.setItem('splitRatio', splitRatio);
            localStorage.setItem('splitDeviceWidth', target.width);
            if (typeof showToast === 'function') {
                showToast(`Snapped to ${target.label} · ${target.width} px`, 'success');
            }
            _hideSnapChip();
            shiftSnapTarget = null;
            // Reset the drag origin so further mouse movement is relative
            // to the snapped position rather than jumping back to the cursor.
            startCoord = isVertical ? lastClientY : lastClientX;
            startRatio = splitRatio;
            _refitAfterLayout();
            return true;
        }

        function onShiftKeyUp(e) {
            if (e.key === 'Shift') commitShiftSnap();
        }

        function onMouseMove(e) {
            lastClientX = e.clientX;
            lastClientY = e.clientY;

            const delta = (isVertical ? e.clientY : e.clientX) - startCoord;
            let newRatio = splitFlipped
                ? startRatio - (delta / totalSize)
                : startRatio + (delta / totalSize);

            // Edge → maximize. The CSS var is overridden by the maximize body
            // class, so we don't write splitRatio while in the snap zone.
            if (newRatio < edgeRatio) { _setMaximizedPane('terminal'); return; }
            if (newRatio > 1 - edgeRatio) { _setMaximizedPane('canvas'); return; }
            if (splitMaximized) _setMaximizedPane(null);

            // Clamp: minimum 300px for each side
            const minRatio = 300 / totalSize;
            const maxRatio = 1 - (300 / totalSize);
            newRatio = Math.max(minRatio, Math.min(maxRatio, newRatio));

            // Shift held in horizontal split → identify nearest device target
            // and keep the chip permanently visible. No magnetic pull mid-drag
            // — the snap commits on release of either Shift or the mouse.
            if (e.shiftKey && !isVertical) {
                const canvasPx = newRatio * totalSize;
                let nearest = DEVICE_SNAPS[0];
                let nearestDiff = Infinity;
                for (const s of DEVICE_SNAPS) {
                    const d = Math.abs(canvasPx - s.width);
                    if (d < nearestDiff) { nearestDiff = d; nearest = s; }
                }
                shiftSnapTarget = nearest;
                _showSnapChip(nearest);
            } else {
                shiftSnapTarget = null;
                _hideSnapChip();
                for (const snap of SNAP_POINTS) {
                    if (Math.abs(newRatio - snap) < SNAP_THRESHOLD) {
                        newRatio = snap;
                        break;
                    }
                }
            }

            splitRatio = newRatio;
            document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');
        }

        function onMouseUp() {
            // Commit any pending shift snap (fires toast). If shift was
            // already released earlier the keyup handler did this.
            commitShiftSnap();

            isDraggingSplitHandle = false;
            handle.classList.remove('dragging');
            document.body.classList.remove('split-dragging');
            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
            document.removeEventListener('keyup', onShiftKeyUp);
            _hideSnapChip();

            // Refit both panels
            if (fitAddon) {
                fitAddon.fit();
                sendTerminalSize();
            }
            // VNC ResizeObserver fires automatically

            // Persist final state — derives splitDeviceWidth from the actual
            // canvas width, so a shift-committed snap the user then drifted
            // away from won't survive on reload.
            _savePersistedSplitState();

            // If the cursor is no longer over the handle, retract the controls.
            if (!handle.matches(':hover')) {
                const c = handle.querySelector('.split-handle-controls');
                try { if (c && c.matches(':popover-open')) c.hidePopover(); }
                catch {}
            }
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('keyup', onShiftKeyUp);
    });

    // Reveal the controls via the Popover API — promotes them to the
    // browser's top layer, escaping every stacking context (badges,
    // overlays, modals) without z-index. Anchored just below the cursor's
    // entry point so the user has minimal travel to either button. A small
    // enter delay prevents flicker when the cursor merely transits the
    // divider on its way between panes.
    function _positionControls(e) {
        if (!controls) return;
        const rect = handle.getBoundingClientRect();
        if (splitOrientation === 'vertical') {
            // Horizontal divider: anchor LEFT of buttons at cursor X,
            // vertically centered on the divider.
            const x = Math.max(rect.left, Math.min(rect.right, e.clientX)) + ANCHOR_OFFSET_PX;
            const y = rect.top + rect.height / 2;
            controls.style.left = `${x}px`;
            controls.style.top = `${y}px`;
            controls.style.transform = 'translateY(-50%)';
        } else {
            // Vertical divider: anchor TOP of buttons at cursor Y,
            // horizontally centered on the divider.
            const x = rect.left + rect.width / 2;
            const y = Math.max(rect.top, Math.min(rect.bottom, e.clientY)) + ANCHOR_OFFSET_PX;
            controls.style.left = `${x}px`;
            controls.style.top = `${y}px`;
            controls.style.transform = 'translateX(-50%)';
        }
    }

    handle.addEventListener('mouseenter', (e) => {
        _positionControls(e);
        clearTimeout(_showTimer);
        _showTimer = setTimeout(() => {
            try { if (!controls.matches(':popover-open')) controls.showPopover(); }
            catch {}
        }, SHOW_DELAY_MS);
    });

    handle.addEventListener('mouseleave', () => {
        clearTimeout(_showTimer);
        // Stay visible while a drag is in progress — the cursor can leave
        // the strip momentarily but the user's intent is still on the divider.
        if (isDraggingSplitHandle) return;
        try { if (controls && controls.matches(':popover-open')) controls.hidePopover(); }
        catch {}
    });

    // Scroll wheel on the divider fine-tunes the split ratio in 2% steps.
    // Handy for nudging without dragging. Disabled while maximized so the
    // user doesn't accidentally exit maximize via scroll.
    let _wheelSaveTimer = null;
    handle.addEventListener('wheel', (e) => {
        if (terminalMode !== 'split' || splitMaximized) return;
        e.preventDefault();
        const step = 0.02;
        const direction = e.deltaY > 0 ? 1 : -1;
        let next = splitFlipped
            ? splitRatio - direction * step
            : splitRatio + direction * step;
        next = Math.max(0.1, Math.min(0.9, next));
        splitRatio = next;
        document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');
        _refitAfterLayout();
        clearTimeout(_wheelSaveTimer);
        _wheelSaveTimer = setTimeout(_savePersistedSplitState, 200);
    }, { passive: false });

    // Double-click: by default resets to 50/50. While device emulation is
    // active in horizontal split, snap the canvas pane to exactly the
    // emulated device width instead — closes the left/right backdrop strip
    // so the device fits the pane edge-to-edge.
    handle.addEventListener('dblclick', () => {
        if (
            splitOrientation === 'horizontal' &&
            typeof activeDeviceProfileId !== 'undefined' && activeDeviceProfileId &&
            typeof getDeviceProfile === 'function'
        ) {
            const profile = getDeviceProfile(activeDeviceProfileId);
            if (profile) {
                const landscape = deviceOrientation === 'landscape';
                const dW = landscape ? profile.height : profile.width;
                const contentRow = document.getElementById('splitContentRow');
                const totalSize = contentRow ? contentRow.offsetWidth - 5 : 0;
                // Mirror setCanvasToDeviceWidth's 300 px terminal floor.
                if (totalSize > 0 && totalSize - dW >= 300) {
                    splitRatio = dW / totalSize;
                    document.body.style.setProperty('--split-vnc-size', (splitRatio * 100) + '%');
                    _refitAfterLayout();
                    _savePersistedSplitState();
                    return;
                }
            }
        }
        splitRatio = 0.5;
        document.body.style.setProperty('--split-vnc-size', '50%');
        _refitAfterLayout();
        _savePersistedSplitState();
    });

    // The orientation button sits next to the swap button. Block its
    // mousedown from initiating a drag, same as the swap button.
    const orientBtn = handle.querySelector('.split-orient-btn');
    if (orientBtn) {
        orientBtn.addEventListener('mousedown', (e) => e.stopPropagation());
    }
}

const LIGHT_TERMINAL_THEMES = new Set(['tomorrow', 'github', 'catppuccin-latte', 'solarized-light']);

/** Build the xterm-facing copy of a theme: strip the background so the
 *  canvas renderer paints nothing and the blurred overlay panel shows
 *  through uniformly across both the canvas area and the container padding.
 *  The original theme keeps its background — editor.js needs it to build
 *  the matching CodeMirror theme. */
function xtermThemeFor(theme) {
    return { ...theme, background: 'rgba(0, 0, 0, 0)' };
}

function applyTerminalTheme(themeName) {
    if (!terminal) return;
    const theme = TERMINAL_THEMES[themeName];
    if (theme) {
        terminal.options.theme = xtermThemeFor(theme);
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

// ─── Custom overlay scrollbar for the terminal ────────────────────────
// Parallel to scrollbar.js (which drives the VNC viewport). The xterm
// version reads state directly from the Terminal API instead of polling
// the control server.
function _initTerminalScrollbar() {
    const scrollbar = document.getElementById('termScrollbar');
    const track = document.getElementById('termScrollbarTrack');
    const thumb = document.getElementById('termScrollbarThumb');
    const hoverZone = document.getElementById('termScrollbarHoverZone');
    if (!scrollbar || !track || !thumb || !hoverZone || !terminal) return;

    let isDragging = false;
    let dragStartY = 0;
    let dragStartViewportY = 0;
    let hideTimer = null;
    const hideDelay = 1500;

    // Buffer metrics at the moment a read is needed. Recomputed on every
    // update so font-size / resize changes don't need special handling.
    function metrics() {
        const buf = terminal.buffer.active;
        const rows = terminal.rows;
        const total = buf.length;
        const viewportY = buf.viewportY;
        // Scroll is only meaningful when there's scrollback beyond the visible rows.
        const hasScroll = total > rows;
        const maxScroll = Math.max(0, total - rows);
        return { rows, total, viewportY, hasScroll, maxScroll };
    }

    function updateThumb() {
        const m = metrics();
        if (!m.hasScroll) {
            scrollbar.classList.remove('visible');
            return;
        }
        const trackHeight = track.offsetHeight;
        const visibleRatio = m.rows / m.total;
        const thumbHeight = Math.max(30, Math.round(trackHeight * visibleRatio));
        const maxThumbTop = trackHeight - thumbHeight;
        const topRatio = m.maxScroll > 0 ? m.viewportY / m.maxScroll : 0;
        thumb.style.height = thumbHeight + 'px';
        thumb.style.top = Math.round(topRatio * maxThumbTop) + 'px';
    }

    function show() {
        if (!metrics().hasScroll) return;
        scrollbar.classList.add('visible');
        scheduleHide();
    }
    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => {
            if (!isDragging) scrollbar.classList.remove('visible');
        }, hideDelay);
    }

    // xterm fires onScroll whenever the viewport moves — either the user
    // scrolled, or new output pushed the viewport down. Either way we
    // reposition the thumb and briefly surface the scrollbar.
    terminal.onScroll(() => {
        updateThumb();
        show();
    });

    // Thumb drag
    function onDragStart(e) {
        e.preventDefault();
        const m = metrics();
        if (!m.hasScroll) return;
        isDragging = true;
        scrollbar.classList.add('dragging');
        thumb.classList.add('dragging');
        dragStartY = e.clientY;
        dragStartViewportY = m.viewportY;
        thumb.setPointerCapture(e.pointerId);
        thumb.addEventListener('pointermove', onDragMove);
        thumb.addEventListener('pointerup', onDragEnd);
    }
    function onDragMove(e) {
        if (!isDragging) return;
        const m = metrics();
        const trackHeight = track.offsetHeight;
        const thumbHeight = thumb.offsetHeight;
        const maxThumbTop = trackHeight - thumbHeight;
        if (maxThumbTop <= 0 || m.maxScroll <= 0) return;
        const deltaPx = e.clientY - dragStartY;
        const deltaLines = Math.round((deltaPx / maxThumbTop) * m.maxScroll);
        const targetLine = Math.max(0, Math.min(m.maxScroll, dragStartViewportY + deltaLines));
        terminal.scrollToLine(targetLine);
    }
    function onDragEnd(e) {
        isDragging = false;
        scrollbar.classList.remove('dragging');
        thumb.classList.remove('dragging');
        try { thumb.releasePointerCapture(e.pointerId); } catch {}
        thumb.removeEventListener('pointermove', onDragMove);
        thumb.removeEventListener('pointerup', onDragEnd);
        scheduleHide();
        terminal.focus();
    }
    thumb.addEventListener('pointerdown', onDragStart);

    // Track click: jump so the click point becomes the new thumb center.
    track.addEventListener('click', (e) => {
        if (e.target === thumb) return;
        const m = metrics();
        if (!m.hasScroll) return;
        const trackRect = track.getBoundingClientRect();
        const clickRatio = (e.clientY - trackRect.top) / trackRect.height;
        const targetLine = Math.round(clickRatio * m.maxScroll);
        terminal.scrollToLine(Math.max(0, Math.min(m.maxScroll, targetLine)));
        show();
    });

    // Surface on hover along the right edge and when the user wheels.
    hoverZone.addEventListener('mouseenter', show);
    hoverZone.addEventListener('mouseleave', scheduleHide);
    scrollbar.addEventListener('mouseenter', () => clearTimeout(hideTimer));
    scrollbar.addEventListener('mouseleave', () => { if (!isDragging) scheduleHide(); });

    // Initial paint — handles the case where the terminal opens already
    // mid-buffer (e.g. cached session replay).
    updateThumb();
}

let terminalInitialized = false; // Ensure we only connect ONCE

function connectTerminal() {
    if (terminalInitialized) {
        console.log('[Terminal] Already initialized, skipping');
        return;
    }
    terminalInitialized = true;
    console.log('[Terminal] Initializing connection…');

    const container = document.getElementById('terminalContainer');

    // Create terminal
    if (!terminal) {
        console.log('[Terminal] Creating terminal instance');
        const savedTheme = localStorage.getItem('terminalTheme') || 'tokyo-night';
        terminal = new Terminal({
            cursorBlink: true,
            fontSize: parseInt(localStorage.getItem('terminalFontSize')) || 14,
            fontFamily: "'JetBrains Mono NF', 'JetBrains Mono', Menlo, Monaco, monospace",
            theme: xtermThemeFor(TERMINAL_THEMES[savedTheme] || TERMINAL_THEMES['tokyo-night']),
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

        // Drive the custom overlay scrollbar (native xterm scrollbars are
        // hidden via CSS). Same visual/behaviour as the VNC viewport
        // scrollbar — reuses the .virtual-scrollbar component.
        _initTerminalScrollbar();

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

        // Check for structured-data signal and show "Data ready to copy" toast
        DATA_SIGNAL_REGEX.lastIndex = 0;
        if (DATA_SIGNAL_REGEX.test(data)) {
            handleDataSignal();
        }

        // Check for open-tab escape sequences and open each URL in a new tab
        OPENTAB_MARKER_REGEX.lastIndex = 0;
        let openTabMatch;
        while ((openTabMatch = OPENTAB_MARKER_REGEX.exec(data)) !== null) {
            handleOpenTab(openTabMatch[1]);
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
        cleanData = cleanData.replace(DATA_SIGNAL_REGEX, '');
        cleanData = cleanData.replace(OPENTAB_MARKER_REGEX, '');
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
