// =============================================
// DevTools Management
// =============================================

let isDevToolsOpen = false;
let cdpConnectionInfo = null;

// Main DevTools toggle - always shows CDP modal to give user choice
function toggleDevTools() {
    // Always show the CDP setup modal - user can choose remote or in-VM DevTools
    openCdpModal();
}

// Internal function to toggle DevTools in VM
async function toggleDevToolsInVM() {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/devtools/toggle`);
        const data = await response.json();
        if (data.ok) {
            isDevToolsOpen = !isDevToolsOpen;
            updateDevToolsButton();
            showToast(isDevToolsOpen ? 'DevTools opened' : 'DevTools closed');
        } else {
            showToast(data.error || 'Failed to toggle DevTools', 'error');
        }
    } catch (e) {
        showToast('Failed to toggle DevTools: ' + e.message, 'error');
    }
}

function updateDevToolsButton() {
    const btn = document.getElementById('devtoolsBtn');
    if (btn) {
        btn.classList.toggle('devtools-active', isDevToolsOpen);
    }
}

async function checkDevToolsStatus() {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/devtools/status`);
        const data = await response.json();
        if (data.ok) {
            isDevToolsOpen = data.open;
            updateDevToolsButton();
        }
    } catch (e) {
        // Ignore errors on status check
    }
}

// =============================================
// Hover-Inspect Mode (host-side overlay)
// =============================================

let isHoverInspectActive = false;
let _hoverAbortController = null;
let _hoverThrottleTimer = null;

function toggleHoverInspect() {
    if (isHoverInspectActive) {
        deactivateHoverInspect();
        showToast('Inspect mode disabled');
    } else {
        activateHoverInspect();
        showToast('Inspect mode enabled \u2014 hover to highlight, click to lock');
    }
}

/**
 * Clean up ALL inspect-related overlays and state.
 * Call this whenever inspect mode fully exits to prevent orphaned outlines.
 */
function _cleanupAllInspectState() {
    // Cancel any in-flight hover request
    if (_hoverAbortController) {
        _hoverAbortController.abort();
        _hoverAbortController = null;
    }
    // Stop tracking (clears interval, dismisses info panel)
    if (_inspectTrackingActive) {
        _stopInspectTracking();
    }
    // Dismiss all inspect overlays unconditionally
    vncOverlay.dismiss('inspect-highlight', true);
    vncOverlay.dismiss('inspect-tooltip', true);
    vncOverlay.dismiss('inspect-info-panel', true);
    // When using the bus, also tell the producer to drop its tracked
    // inspect overlays so it stops firing observer callbacks. Fire-and-forget.
    if (window.overlayBus && window.overlayBus.connected) {
        fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspect/clear`).catch(() => {});
    }
    // Reset button state
    updateInspectButton();
}

function activateHoverInspect() {
    // Clean up any orphaned overlays from a previous session
    _cleanupAllInspectState();
    isHoverInspectActive = true;
    updateInspectButton();
    document.getElementById('vncContainer').classList.add('hover-inspect-active');
}

function deactivateHoverInspect() {
    isHoverInspectActive = false;
    document.getElementById('vncContainer').classList.remove('hover-inspect-active');
    _cleanupAllInspectState();
}

function updateInspectButton() {
    const btn = document.getElementById('inspectBtn');
    if (btn) {
        btn.classList.toggle('inspect-active', isHoverInspectActive || _inspectTrackingActive);
    }
}

// Handle pointermove from VNC canvas during hover-inspect
async function _handleHoverMove(vmX, vmY) {
    if (!isHoverInspectActive) return;

    // Throttle to ~80ms (12 fps) for smooth but efficient updates
    if (_hoverThrottleTimer) return;
    _hoverThrottleTimer = setTimeout(() => { _hoverThrottleTimer = null; }, 80);

    // Cancel previous in-flight request
    if (_hoverAbortController) _hoverAbortController.abort();
    _hoverAbortController = new AbortController();

    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/inspect/element-at-point?x=${vmX}&y=${vmY}`,
            { signal: _hoverAbortController.signal }
        );
        const data = await resp.json();
        if (data.ok && data.rect && isHoverInspectActive) {
            _positionInspectOverlay(data.rect, data.selector);
        }
    } catch {
        // Aborted or network error — ignore
    }
}

// Handle click-to-lock during hover-inspect
async function _handleHoverLock(vmX, vmY) {
    // Deactivate hover mode first
    deactivateHoverInspect();

    // Commit the element via set-at-point
    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/inspect/set-at-point?x=${vmX}&y=${vmY}`
        );
        const data = await resp.json();
        if (data.ok && data.rect) {
            showInspectOverlay(data.rect, data.selector);
            showToast(`Inspecting: ${data.selector}`, 'success');
            // Fetch and show detailed info panel
            _showInspectInfoPanel();
        } else {
            showToast(data.error || 'Could not inspect element', 'error');
        }
    } catch (e) {
        showToast('Failed to inspect element', 'error');
    }
}

// Fetch element details and render host-side info panel
async function _showInspectInfoPanel() {
    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/inspect/element-details`,
            { signal: AbortSignal.timeout(2000) }
        );
        const d = await resp.json();
        if (!d.ok) return;

        // Build attributes HTML
        let attrsHtml = '';
        if (d.attributes && d.attributes.length > 0) {
            const lines = d.attributes.map(a =>
                `<span class="attr-name">${_esc(a.name)}</span>="<span class="attr-value">${_esc(a.value)}</span>"`
            ).join('<br>');
            attrsHtml = `<div class="info-section"><small>ATTRIBUTES</small><div class="info-section-content" style="font:11px monospace;">${lines}</div></div>`;
        }

        // Build text HTML
        let textHtml = '';
        if (d.text) {
            textHtml = `<div class="info-section"><small>TEXT</small><div class="info-section-content text-content">${_esc(d.text)}</div></div>`;
        }

        // Build styles HTML
        const s = d.styles || {};
        const stylesHtml = `<div class="info-section"><small>STYLES</small><div class="info-section-content styles-grid">
            <div>font: ${_esc(s.fontSize || '')}</div><div>color: ${_esc((s.color || '').slice(0,20))}</div>
            <div>bg: ${_esc((s.backgroundColor || '').slice(0,20))}</div><div>display: ${_esc(s.display || '')}</div>
            <div>position: ${_esc(s.position || '')}</div><div>family: ${_esc(s.fontFamily || '')}</div>
        </div></div>`;

        const r = d.rect || {};
        const panelHtml = `
            <div class="panel-header"><b>Element Inspector</b><button class="panel-close" onclick="_dismissInspectInfoPanel()">\u00d7</button></div>
            <div class="panel-body">
                <div class="selector-box">${_esc(d.selector || '')}</div>
                <div class="info-grid">
                    <div class="info-cell"><small>Size</small><br>${Math.round(r.width || 0)} \u00d7 ${Math.round(r.height || 0)}</div>
                    <div class="info-cell"><small>Position</small><br>${Math.round(r.left || 0)}, ${Math.round(r.top || 0)}</div>
                </div>
                ${attrsHtml}${textHtml}${stylesHtml}
                <div class="panel-footer">Arrow keys to navigate \u2022 C to copy selector \u2022 Escape to dismiss</div>
            </div>`;

        // Render as a vncOverlay element
        vncOverlay.show('inspect-info-panel', null, {
            html: panelHtml,
            className: 'vnc-inspect-info-panel',
            style: { pointerEvents: 'auto' }
        });
    } catch {
        // Silent fail — info panel is optional
    }
}

function _dismissInspectInfoPanel() {
    vncOverlay.dismiss('inspect-info-panel', true);
}

// HTML escape helper
function _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

