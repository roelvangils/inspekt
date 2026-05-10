// =============================================
// Device Emulation (DevTools-style)
// =============================================
//
// Applies a DEVICE_PROFILES entry to all open Chromium tabs by POSTing the
// resolved metrics to control-server's /device endpoint. The page reflows to
// the device viewport (innerWidth, navigator.userAgent, ontouchstart) without
// touching the X display dimensions or the canvas pane width.
//
// State persists across:
//   - Tab navigation (server-side reconciler re-applies on /tabs poll).
//   - New tabs (same reconciler).
//   - Control-panel reload (localStorage round-trip + GET /device on init).
//   - Control-server restart (frontend re-issues POST /device if server lost
//     state but localStorage had a profile).
//
// Authoritative state: localStorage. Server state is best-effort.

// Module-scope `var` (consistent with config.js / split-mode.js).
var activeDeviceProfileId = null;
var deviceOrientation = 'portrait';
// Remembered profile for the "Toggle Last Device Emulation" palette
// command. Survives `clearDeviceEmulation` so a single command can flip
// emulation on/off with the most recent profile. Persisted to localStorage
// so it's available after a control-panel reload.
var lastDeviceProfileId = null;

// Wheel events are intentionally NOT intercepted: they pass through to noVNC
// so they scroll the emulated page (the natural expectation). To reach
// clipped edges when the device overflows the pane, drag the gutter wider or
// double-click it to snap to a fitting width.

(function loadDevicePersistence() {
    const id = localStorage.getItem('deviceProfile');
    // localStorage returns null for missing keys, but a previous version may
    // have written the literal string 'null' — treat both as "no profile".
    if (id && id !== 'null' && id !== '') {
        activeDeviceProfileId = id;
    }
    const orient = localStorage.getItem('deviceOrientation');
    if (orient === 'landscape') deviceOrientation = 'landscape';
    const last = localStorage.getItem('lastDeviceProfile');
    if (last && last !== 'null' && last !== '') {
        lastDeviceProfileId = last;
    } else if (activeDeviceProfileId) {
        // First run after the upgrade: seed `last` from the active profile
        // and persist immediately so the value survives a reload even if
        // the user clears emulation before triggering setDeviceProfile.
        lastDeviceProfileId = activeDeviceProfileId;
        localStorage.setItem('lastDeviceProfile', activeDeviceProfileId);
    }
})();

// Rotation is a pure width/height swap — dpr/mobile/UA stay the same — so a
// tiny shared helper avoids the same ternary appearing in 3 places.
function _orientedDims(profile, orientation) {
    const landscape = orientation === 'landscape';
    return {
        width:  landscape ? profile.height : profile.width,
        height: landscape ? profile.width  : profile.height,
    };
}

function _resolveDeviceMetrics(profile, orientation) {
    const { width, height } = _orientedDims(profile, orientation);
    return {
        profile_id: profile.id,
        label: profile.label,
        width, height,
        dpr: profile.dpr,
        mobile: !!profile.mobile,
        user_agent: profile.userAgent || null,
        orientation,
    };
}

async function _postDevice(payload) {
    const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/device`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return resp.json();
}

async function setDeviceProfile(id) {
    const profile = getDeviceProfile(id);
    if (!profile) {
        console.warn('[DeviceEmul] Unknown profile:', id);
        return;
    }
    const payload = _resolveDeviceMetrics(profile, deviceOrientation);
    try {
        const data = await _postDevice(payload);
        if (!data.ok) {
            console.warn('[DeviceEmul] Apply failed:', data.error);
            if (typeof showToast === 'function') {
                showToast(`Device emulation failed: ${data.error || 'unknown'}`, 'error');
            }
            return;
        }
        activeDeviceProfileId = profile.id;
        lastDeviceProfileId = profile.id;
        localStorage.setItem('deviceProfile', profile.id);
        localStorage.setItem('deviceOrientation', deviceOrientation);
        localStorage.setItem('lastDeviceProfile', profile.id);
        renderDeviceBadge();
        _startDeviceVisuals();
        if (typeof showToast === 'function') {
            const o = deviceOrientation === 'landscape' ? ' · landscape' : '';
            showToast(`Emulating ${profile.label}${o}`, 'success');
        }
    } catch (e) {
        console.warn('[DeviceEmul] Apply error:', e);
    }
}

async function clearDeviceEmulation() {
    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/device/clear`, {
            method: 'POST',
        });
    } catch (e) {
        console.warn('[DeviceEmul] Clear error:', e);
    }
    activeDeviceProfileId = null;
    deviceOrientation = 'portrait';
    localStorage.removeItem('deviceProfile');
    localStorage.removeItem('deviceOrientation');
    renderDeviceBadge();
    _stopDeviceVisuals();
    if (typeof showToast === 'function') {
        showToast('Device emulation cleared', 'success');
    }
}

async function rotateDevice() {
    if (!activeDeviceProfileId) return;
    deviceOrientation = deviceOrientation === 'portrait' ? 'landscape' : 'portrait';
    await setDeviceProfile(activeDeviceProfileId);
}

// Power-user accelerator: a single palette command that flips emulation
// on/off with whatever profile was used most recently. Lets users A/B
// between "real" and "mobile" without going through the full picker.
async function toggleLastDeviceEmulation() {
    if (activeDeviceProfileId) {
        await clearDeviceEmulation();
        return;
    }
    if (lastDeviceProfileId) {
        await setDeviceProfile(lastDeviceProfileId);
        return;
    }
    if (typeof showToast === 'function') {
        showToast('No previous device — pick one from the palette first', 'dark');
    }
}

// Called once on init: align the control panel with whatever the server
// believes is active. If localStorage says we should be emulating but the
// server is fresh (e.g. control-server was restarted), re-apply.
async function restoreDeviceEmulation() {
    let serverActive = false;
    let serverEmul = null;
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/device`);
        const data = await resp.json();
        if (data.ok) {
            serverActive = !!data.active;
            serverEmul = data.emulation || null;
        }
    } catch (e) {
        // Server unreachable — fall back to localStorage truth.
    }

    if (activeDeviceProfileId && !serverActive) {
        // Frontend wants emulation, server lost it. Re-apply.
        await setDeviceProfile(activeDeviceProfileId);
        return;
    }
    if (serverActive && serverEmul) {
        // Server has a profile; trust localStorage for the orientation if it
        // matches, otherwise adopt the server's view.
        if (serverEmul.profile_id) {
            activeDeviceProfileId = serverEmul.profile_id;
            localStorage.setItem('deviceProfile', serverEmul.profile_id);
        }
        if (serverEmul.orientation) {
            deviceOrientation = serverEmul.orientation;
            localStorage.setItem('deviceOrientation', deviceOrientation);
        }
        renderDeviceBadge();
        _startDeviceVisuals();
        return;
    }
    // No emulation active anywhere; just make sure the badge is hidden.
    renderDeviceBadge();
    _stopDeviceVisuals();
}

// =============================================
// Visual frame + blurred backdrop
// =============================================
//
// Chromium paints the page in the top-left of the X display and leaves the
// rest of the framebuffer empty (whatever its background colour is). To get a
// DevTools-style centered viewport without that empty strip, we crop the live
// canvas using clip-path and shift it into the pane center with a transform —
// no separate display canvas, no event forwarding, getBoundingClientRect
// stays accurate so noVNC's mouse-coord mapping in vnc.js's _clientToVm just
// keeps working.
//
// We deliberately do NOT touch .noVNC_screen. Resizing it triggers noVNC's
// own scaling logic which races with us; staying out of that fight is what
// finally made the framing reliable.

const DEVICE_BACKDROP_INTERVAL_MS = 200;  // 5 fps — plenty for a blurred bg

let _deviceFrameRO = null;
let _deviceBackdropTimer = null;
let _prevScaleViewport = null;             // remember to restore on clear

function _getDeviceFrameDims() {
    if (!activeDeviceProfileId) return null;
    const profile = getDeviceProfile(activeDeviceProfileId);
    if (!profile) return null;
    const { width, height } = _orientedDims(profile, deviceOrientation);
    return { dW: width, dH: height };
}

function _getNoVNCElements() {
    const container = document.getElementById('vncContainer');
    if (!container) return null;
    // The backdrop is also a <canvas> inside #vncContainer; exclude it.
    const canvas = container.querySelector('canvas:not(.device-backdrop)');
    return { container, canvas };
}

// Centering-offset floors. Asymmetric on purpose: the top floor has to
// clear the .resize-readout / device-badge that lives at top-left of the
// pane (badge bottom is around y=42), so we need ~56px of vertical
// breathing room before the device viewport starts. Horizontal and bottom
// floors stay tight because nothing else competes for space there. When
// the pane is large enough, (paneH-dH)/2 wins and the device ends up
// genuinely centered — the floors only kick in for tight panes.
const DEVICE_FRAME_MIN_PAD = 16;
const DEVICE_FRAME_TOP_PAD = 56;

function _applyDeviceFrame() {
    const els = _getNoVNCElements();
    if (!els || !els.canvas) return;
    const dims = _getDeviceFrameDims();
    if (!dims) return;

    const paneW = els.container.clientWidth;
    const paneH = els.container.clientHeight;
    if (paneW < 50 || paneH < 50) return;

    // Locked scale = 1: device renders at native CSS pixels regardless of
    // pane size. Pane > device → centered with backdrop. Pane < device →
    // device overflows and is clipped by .vnc-container's overflow:hidden.
    // Mirrors Chrome DevTools' device toolbar behaviour and keeps
    // _clientToVm's mapping in vnc.js trivially correct (canvas pixel size
    // and CSS size remain equal so clientX → canvas pixel is 1:1).
    const dW = dims.dW;
    const dH = dims.dH;
    const offsetX = Math.max(DEVICE_FRAME_MIN_PAD, (paneW - dW) / 2);
    const offsetY = Math.max(DEVICE_FRAME_TOP_PAD, (paneH - dH) / 2);

    // Native canvas pixel dims = X display size (kept in sync with pane via
    // the auto-resize ResizeObserver in vnc.js).
    const canvasW = els.canvas.width || paneW;
    const canvasH = els.canvas.height || paneH;

    // Disable noVNC's auto-scale BEFORE touching the canvas. Otherwise its
    // ResizeObserver reacts to our size changes and fights back.
    if (typeof rfb !== 'undefined' && rfb && rfb.scaleViewport !== false) {
        if (_prevScaleViewport === null) _prevScaleViewport = rfb.scaleViewport;
        rfb.scaleViewport = false;
    }

    // clip-path: crop the canvas to the device-area top-left rectangle, with
    // rounded corners per profile (real devices have rounded screens).
    // clip-path also gates pointer-events so the empty pixels Chromium streams
    // can't be clicked by accident.
    const clipRight = Math.max(0, canvasW - dW);
    const clipBottom = Math.max(0, canvasH - dH);
    const profile = getDeviceProfile(activeDeviceProfileId);
    const R = (profile && Number.isFinite(profile.cornerRadius))
        ? profile.cornerRadius : 0;
    Object.assign(els.canvas.style, {
        position: 'absolute',
        left: '0',
        top: '0',
        width: `${canvasW}px`,
        height: `${canvasH}px`,
        transform: `translate(${offsetX}px, ${offsetY}px)`,
        transformOrigin: 'top left',
        clipPath: `inset(0 ${clipRight}px ${clipBottom}px 0 round ${R}px)`,
    });
}

function _resetDeviceFrame() {
    const els = _getNoVNCElements();
    if (!els) return;
    if (els.canvas) {
        for (const prop of [
            'position', 'left', 'top', 'width', 'height',
            'transform', 'transform-origin', 'clip-path',
        ]) {
            els.canvas.style.removeProperty(prop);
        }
    }
    if (typeof rfb !== 'undefined' && rfb && _prevScaleViewport !== null) {
        rfb.scaleViewport = _prevScaleViewport;
    }
    _prevScaleViewport = null;
}

function _drawDeviceBackdrop() {
    const els = _getNoVNCElements();
    const backdrop = document.getElementById('deviceBackdrop');
    const dims = _getDeviceFrameDims();
    if (!els || !els.canvas || !backdrop || !dims) return;

    const paneW = els.container.clientWidth;
    const paneH = els.container.clientHeight;
    if (paneW < 1 || paneH < 1) return;

    if (backdrop.width !== paneW) backdrop.width = paneW;
    if (backdrop.height !== paneH) backdrop.height = paneH;

    const ctx = backdrop.getContext('2d', { alpha: false });
    if (!ctx) return;

    // Sample the same top-left region the foreground frame is showing.
    const sW = Math.min(dims.dW, els.canvas.width);
    const sH = Math.min(dims.dH, els.canvas.height);
    if (sW < 1 || sH < 1) return;
    try {
        ctx.drawImage(els.canvas, 0, 0, sW, sH, 0, 0, paneW, paneH);
    } catch (_) {
        // Canvas may be empty during reload — just skip this tick.
    }
}

// Tiered badge visibility based on pane width.
//   pane >= 320  → full badge (icon + label + meta + rotate + close)
//   pane >= 80   → compact (drop meta — keep label so the user still sees
//                  which device is active)
//   pane <  80   → hide entirely (extreme edge case; absurd pane width)
// Thresholds intentionally use absolute pixel values rather than scaling
// with deviceW: at any reasonable working pane size the user gets the full
// badge. Decoupled from the `hidden` attribute (which renderDeviceBadge owns
// to signal "is emulation active?") via dedicated classes.
function _updateDeviceBadgeFit() {
    const badge = document.getElementById('deviceBadge');
    const container = document.getElementById('vncContainer');
    if (!badge || !container) return;
    const paneW = container.clientWidth;

    badge.classList.remove('compact', 'device-badge--hidden');
    if (paneW < 80) {
        badge.classList.add('device-badge--hidden');
    } else if (paneW < 320) {
        badge.classList.add('compact');
    }
}

function _startDeviceVisuals() {
    _applyDeviceFrame();
    _updateDeviceBadgeFit();

    // 200ms entry fade so the mode change is visually announced. Keyed off a
    // class that's auto-removed on animationend; safe to re-trigger by
    // toggling the class off and back on (e.g. when switching profiles).
    const els = _getNoVNCElements();
    if (els && els.canvas) {
        els.canvas.classList.remove('device-frame-entering');
        // Force reflow so re-adding the class restarts the animation.
        // eslint-disable-next-line no-unused-expressions
        els.canvas.offsetWidth;
        els.canvas.classList.add('device-frame-entering');
        els.canvas.addEventListener('animationend', function _once() {
            els.canvas.classList.remove('device-frame-entering');
            els.canvas.removeEventListener('animationend', _once);
        });
    }

    if (!_deviceFrameRO && typeof ResizeObserver !== 'undefined') {
        const container = document.getElementById('vncContainer');
        if (container) {
            _deviceFrameRO = new ResizeObserver(() => {
                if (activeDeviceProfileId) {
                    _applyDeviceFrame();
                    _updateDeviceBadgeFit();
                }
            });
            _deviceFrameRO.observe(container);
        }
    }

    if (_deviceBackdropTimer) clearInterval(_deviceBackdropTimer);
    _deviceBackdropTimer = setInterval(() => {
        // Idempotent: re-apply framing each tick so we recover if noVNC
        // recreated its DOM (reconnect) or auto-resize changed canvas dims.
        _applyDeviceFrame();
        _drawDeviceBackdrop();
    }, DEVICE_BACKDROP_INTERVAL_MS);
    _drawDeviceBackdrop();

    const backdrop = document.getElementById('deviceBackdrop');
    if (backdrop) backdrop.hidden = false;
}

function _stopDeviceVisuals() {
    if (_deviceBackdropTimer) {
        clearInterval(_deviceBackdropTimer);
        _deviceBackdropTimer = null;
    }
    if (_deviceFrameRO) {
        _deviceFrameRO.disconnect();
        _deviceFrameRO = null;
    }
    _resetDeviceFrame();
    const backdrop = document.getElementById('deviceBackdrop');
    if (backdrop) backdrop.hidden = true;
    // Clear tiered-fit + orientation classes so the next activation starts
    // clean.
    const badge = document.getElementById('deviceBadge');
    if (badge) {
        badge.classList.remove('compact', 'device-badge--hidden', 'device-badge--landscape');
    }
}

// =============================================
// Badge DOM
// =============================================

function renderDeviceBadge() {
    const badge = document.getElementById('deviceBadge');
    if (!badge) return;

    if (!activeDeviceProfileId) {
        badge.hidden = true;
        document.body.classList.remove('device-emulating');
        return;
    }
    const profile = getDeviceProfile(activeDeviceProfileId);
    if (!profile) {
        badge.hidden = true;
        document.body.classList.remove('device-emulating');
        return;
    }
    const { width: w, height: h } = _orientedDims(profile, deviceOrientation);
    const labelEl = badge.querySelector('.device-badge-label');
    const metaEl = badge.querySelector('.device-badge-meta');
    const iconEl = badge.querySelector('.device-badge-icon');
    if (labelEl) labelEl.textContent = profile.label;
    if (metaEl) {
        metaEl.textContent = `${w} × ${h} · ${formatDpr(profile.dpr)}`;
    }
    // Tooltip on the icon repeats the full info so users still discover the
    // device when the badge collapses to its compact form (no meta visible).
    if (iconEl) {
        const o = deviceOrientation === 'landscape' ? ' · landscape' : '';
        iconEl.title = `Emulating ${profile.label} — ${w} × ${h} · ${formatDpr(profile.dpr)}${o}`;
    }
    // Rotate the icon glyph -90° in landscape so orientation is readable
    // at-a-glance even from the badge alone.
    badge.classList.toggle('device-badge--landscape', deviceOrientation === 'landscape');
    badge.hidden = false;
    document.body.classList.add('device-emulating');
}

function _wireDeviceBadgeButtons() {
    const badge = document.getElementById('deviceBadge');
    if (!badge) return;
    const rotateBtn = badge.querySelector('.device-badge-rotate');
    if (rotateBtn) rotateBtn.addEventListener('click', rotateDevice);
    const closeBtn = badge.querySelector('.device-badge-close');
    if (closeBtn) closeBtn.addEventListener('click', clearDeviceEmulation);
    // Click on the label area opens the command palette (filtered to devices).
    badge.addEventListener('click', (e) => {
        // Don't hijack rotate / close button clicks.
        if (e.target.closest('.device-badge-rotate, .device-badge-close')) return;
        const ninja = document.getElementById('commandPalette');
        if (ninja && typeof ninja.open === 'function') ninja.open();
    });
}

// Init: wire badge + restore state once DOM is ready and config has loaded.
function _initDeviceEmulation() {
    _wireDeviceBadgeButtons();
    renderDeviceBadge();
    // Wait for config.js's _configReady so VNC_HOST/CONTROL_PORT are stable.
    const ready = typeof _configReady !== 'undefined'
        ? _configReady
        : Promise.resolve();
    ready.then(restoreDeviceEmulation);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initDeviceEmulation);
} else {
    _initDeviceEmulation();
}
