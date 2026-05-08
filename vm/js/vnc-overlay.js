/**
 * VNC Overlay Manager — Host-side highlights rendered over the VNC canvas.
 *
 * Manages positioned overlay elements (highlight boxes, tooltips) on top of the
 * VNC container. Used for inspect mode to show element outlines and selector tooltips.
 *
 * Also includes inspect overlay tracking (polling element rects from the VM)
 * and DOM navigation via arrow keys.
 *
 * Globals this module reads:
 *   VNC_HOST, CONTROL_PORT — server connection (from control-panel.html)
 *   showToast(message, type) — toast notifications (from control-panel.html)
 *   updateInspectButton() — update toolbar inspect state (from control-panel.html)
 *   _dismissInspectInfoPanel() — close info panel (from control-panel.html)
 *   _isMenuOpen() — context menu state (from context-menu.js)
 *
 * Globals this module exposes:
 *   vncOverlay — overlay manager object (show, dismiss, dismissAll, update, isVisible)
 *   showInspectOverlay(rect, selector) — start inspect tracking for an element
 *   _stopInspectTracking() — stop inspect polling
 *   _inspectTrackingActive — whether inspect is currently tracking
 *   _tabInspectState — per-tab inspect state preservation
 */

// =============================================
// VNC Overlay Manager (host-side highlights)
// =============================================

const vncOverlay = {
    _container: null,
    _overlays: {},

    _ensureContainer() {
        if (this._container) return this._container;
        const c = document.createElement('div');
        c.id = 'vncOverlayContainer';
        document.getElementById('vncContainer').appendChild(c);
        this._container = c;
        return c;
    },

    show(id, rect, options = {}) {
        this._ensureContainer();
        // Always dismiss existing overlay with same ID first to prevent
        // race conditions with animated dismissals
        this.dismiss(id, false);
        const el = document.createElement('div');
        el.dataset.overlayId = id;
        el.style.position = 'absolute';
        el.style.pointerEvents = 'none';
        this._container.appendChild(el);
        const entry = { element: el };
        this._overlays[id] = entry;
        if (rect) {
            el.style.left = rect.left + 'px';
            el.style.top = rect.top + 'px';
            if (rect.width != null) el.style.width = rect.width + 'px';
            if (rect.height != null) el.style.height = rect.height + 'px';
        }
        if (options.text !== undefined) el.textContent = options.text;
        else if (options.html !== undefined) el.innerHTML = options.html;
        if (options.className) el.className = options.className;
        if (options.style) Object.assign(el.style, options.style);
        el.style.display = 'block';
        return el;
    },

    update(id, rect) {
        const entry = this._overlays[id];
        if (!entry) return;
        const el = entry.element;
        if (rect.left != null) el.style.left = rect.left + 'px';
        if (rect.top != null) el.style.top = rect.top + 'px';
        if (rect.width != null) el.style.width = rect.width + 'px';
        if (rect.height != null) el.style.height = rect.height + 'px';
    },

    dismiss(id, animate = true) {
        const entry = this._overlays[id];
        if (!entry) return;
        const el = entry.element;
        // Always remove from tracking immediately to prevent races
        delete this._overlays[id];
        if (animate) {
            el.style.transition = 'opacity 0.15s ease';
            el.style.opacity = '0';
            setTimeout(() => el.remove(), 150);
        } else {
            el.remove();
        }
    },

    dismissAll(animate = false) {
        for (const id of Object.keys(this._overlays)) {
            this.dismiss(id, animate);
        }
        // Nuclear cleanup: remove any DOM orphans not tracked in _overlays
        if (this._container) {
            const orphans = this._container.querySelectorAll('[data-overlay-id]');
            orphans.forEach(el => el.remove());
        }
    },

    isVisible(id) { return !!this._overlays[id]; }
};

// =============================================
// Inspect overlay tracking
// =============================================

let _inspectTrackingInterval = null;
let _inspectTrackingActive = false;
let _lastInspectMeta = {};  // { siblingIndex, siblingCount }
const _tabInspectState = {};  // { tabId: { wasTracking: bool } }

// Transform a rect from the inner VM browser's CSS px (via getBoundingClientRect
// inside Chromium) into host CSS px relative to #vncContainer (the overlay's
// positioning ancestor). Accounts for canvas offset (letterboxing / centering)
// and noVNC scaleViewport scaling.
function _vmRectToOverlayRect(rect) {
    const container = document.getElementById('vncContainer');
    const canvas = container && container.querySelector('canvas');
    if (!canvas || !container) return rect;
    const cr = canvas.getBoundingClientRect();
    const vr = container.getBoundingClientRect();
    const scaleX = canvas.width  ? cr.width  / canvas.width  : 1;
    const scaleY = canvas.height ? cr.height / canvas.height : 1;
    return {
        left:   rect.left   * scaleX + (cr.left - vr.left),
        top:    rect.top    * scaleY + (cr.top  - vr.top),
        width:  rect.width  * scaleX,
        height: rect.height * scaleY,
    };
}

function _positionInspectOverlay(rect, selector, meta) {
    // Update sibling metadata if provided
    if (meta && meta.siblingIndex) {
        _lastInspectMeta = { siblingIndex: meta.siblingIndex, siblingCount: meta.siblingCount };
    }
    // Convert the VM-side rect to overlay/container coordinates. The original
    // `rect` is still used for the size shown in the tooltip — users want the
    // element's true page size, not its scaled on-screen size.
    const r = _vmRectToOverlayRect(rect);
    const isNew = !vncOverlay.isVisible('inspect-highlight');

    if (isNew) {
        // First show: create with entering class, then remove to trigger fade-in
        vncOverlay.show('inspect-highlight', r, { className: 'vnc-overlay-highlight entering' });
        requestAnimationFrame(() => {
            const entry = vncOverlay._overlays['inspect-highlight'];
            if (entry) entry.element.classList.remove('entering');
        });
    } else {
        // Subsequent updates: just move — CSS transition handles the animation
        vncOverlay.update('inspect-highlight', r);
    }

    // Tooltip: position + content (with optional sibling index)
    let tooltipText = selector;
    if (_lastInspectMeta.siblingIndex && _lastInspectMeta.siblingCount > 1) {
        tooltipText += ` (${_lastInspectMeta.siblingIndex}/${_lastInspectMeta.siblingCount})`;
    }
    tooltipText += ' \u2022 ' + Math.round(rect.width) + '\u00d7' + Math.round(rect.height);
    const tooltipTop = r.top >= 28 ? r.top - 28 : r.top + r.height + 4;
    const tooltipLeft = Math.max(0, r.left);
    const tooltipRect = { left: tooltipLeft, top: tooltipTop };

    if (isNew) {
        vncOverlay.show('inspect-tooltip', null, {
            className: 'vnc-overlay-tooltip entering',
            text: tooltipText,
            style: { left: tooltipLeft + 'px', top: tooltipTop + 'px', width: 'auto', height: 'auto' }
        });
        requestAnimationFrame(() => {
            const entry = vncOverlay._overlays['inspect-tooltip'];
            if (entry) entry.element.classList.remove('entering');
        });
    } else {
        // Move tooltip and update text — CSS transition handles position
        const entry = vncOverlay._overlays['inspect-tooltip'];
        if (entry) {
            entry.element.style.left = tooltipLeft + 'px';
            entry.element.style.top = tooltipTop + 'px';
            entry.element.textContent = tooltipText;
        }
    }
}

function _stopInspectTracking() {
    if (_inspectTrackingInterval) {
        clearTimeout(_inspectTrackingInterval);
        _inspectTrackingInterval = null;
    }
    _inspectTrackingActive = false;
    // Also dismiss the info panel when tracking stops
    _dismissInspectInfoPanel();
    updateInspectButton();
}

async function _pollInspectRect() {
    if (!_inspectTrackingActive) return;
    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/inspect/get-rect`,
            { signal: AbortSignal.timeout(500) }
        );
        const data = await resp.json();
        if (data.ok && data.rect && _inspectTrackingActive) {
            _positionInspectOverlay(data.rect, data.selector, data);
        } else if (!data.ok && _inspectTrackingActive) {
            // Element disconnected from DOM (navigated away, etc.)
            _stopInspectTracking();
            vncOverlay.dismiss('inspect-highlight', true);
            vncOverlay.dismiss('inspect-tooltip', true);
            return;
        }
    } catch {
        // Network error — skip this tick
    }
    // Schedule next poll only AFTER this one completes (no overlap)
    if (_inspectTrackingActive) {
        _inspectTrackingInterval = setTimeout(_pollInspectRect, 200);
    }
}

function showInspectOverlay(rect, selector) {
    _stopInspectTracking();
    vncOverlay.dismiss('inspect-highlight', false);
    vncOverlay.dismiss('inspect-tooltip', false);
    _lastInspectMeta = {};  // Reset sibling info for fresh inspection
    if (!rect || !rect.width || !rect.height) return;

    // Show initial position immediately
    _positionInspectOverlay(rect, selector);

    // Start polling to track scroll, resize, and font size changes.
    // Uses chained setTimeout (not setInterval) to prevent request pile-up.
    _inspectTrackingActive = true;
    _inspectTrackingInterval = setTimeout(_pollInspectRect, 200);
}

// =============================================
// DOM navigation via arrow keys
// =============================================

let _inspectNavPending = false;

async function _navigateInspect(direction) {
    if (_inspectNavPending || !_inspectTrackingActive) return;
    _inspectNavPending = true;
    try {
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/inspect/navigate?direction=${direction}`,
            { signal: AbortSignal.timeout(1000) }
        );
        const data = await resp.json();
        if (data.ok && data.rect) {
            _positionInspectOverlay(data.rect, data.selector, data);
            // Refresh the info panel with the new element's details
            _showInspectInfoPanel();
            // Flash tooltip orange on auto-climb (moved to parent because no sibling)
            if (data.autoClimbed) {
                const entry = vncOverlay._overlays['inspect-tooltip'];
                if (entry) {
                    entry.element.style.background = 'linear-gradient(135deg, #e67e22, #d35400)';
                    setTimeout(() => {
                        if (vncOverlay._overlays['inspect-tooltip'])
                            vncOverlay._overlays['inspect-tooltip'].element.style.background = '';
                    }, 600);
                }
            }
        }
        // If !ok, element doesn't exist in that direction — just stay put
    } catch {
        // Network error — ignore
    } finally {
        _inspectNavPending = false;
    }
}

// Arrow key + shortcut handler for DOM navigation (only active when inspect overlay is showing)
document.addEventListener('keydown', (e) => {
    if (!_inspectTrackingActive || _isMenuOpen()) return;

    // Don't intercept keys when terminal or editor is active
    const termOverlay = document.getElementById('terminalOverlay');
    if (termOverlay && termOverlay.classList.contains('open')) return;
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;

    // Copy selector with 'c' key
    if (e.key === 'c' && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        const entry = vncOverlay._overlays['inspect-tooltip'];
        if (entry) {
            const selector = entry.element.textContent.split(' \u2022 ')[0].split(' (')[0];
            writeClipboard(selector);
            showToast(`Copied: ${selector}`, 'success');
        }
        return;
    }

    const directionMap = {
        'ArrowUp': 'up',
        'ArrowDown': 'down',
        'ArrowLeft': 'left',
        'ArrowRight': 'right'
    };
    const direction = directionMap[e.key];
    if (!direction) return;

    e.preventDefault();
    _navigateInspect(direction);
});
