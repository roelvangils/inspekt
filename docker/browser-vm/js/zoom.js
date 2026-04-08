/**
 * Zoom Controller — Programmatic zoom via the Inspekt extension API.
 *
 * Provides discrete zoom steps matching Chrome's built-in zoom levels,
 * with accessibility-focused messages at key breakpoints (1.5x, 2x, 4x).
 *
 * Globals this module reads:
 *   VNC_HOST, CONTROL_PORT — server connection (from control-panel.html)
 *   showToast(message, type) — toast notifications (from control-panel.html)
 *
 * Globals this module exposes:
 *   handleZoom(action) — 'in', 'out', or 'reset'
 *   currentZoom — current zoom level (number)
 */

// =============================================
// Zoom Controller (programmatic zoom via extension API)
// =============================================

const ZOOM_STEPS = [0.25, 0.33, 0.5, 0.67, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0, 5.0];
const ZOOM_MESSAGES = {
    0.25: 'Minimum zoom level',
    0.5:  'Good for seeing the full layout at a glance',
    1.0:  'Default zoom level',
    1.5:  'Common accessibility zoom level',
    2.0:  'WCAG requires content to be usable at this level',
    3.0:  'Tests extreme zoom for low-vision users',
    4.0:  'WCAG 1.4.10 requires content reflow at this level',
    5.0:  'Maximum zoom level',
};
let currentZoom = 1.0;

async function handleZoom(action) {
    let targetZoom;
    if (action === 'reset') {
        targetZoom = 1.0;
    } else if (action === 'in') {
        const next = ZOOM_STEPS.find(s => s > currentZoom + 0.001);
        targetZoom = next || ZOOM_STEPS[ZOOM_STEPS.length - 1];
    } else {
        const prev = [...ZOOM_STEPS].reverse().find(s => s < currentZoom - 0.001);
        targetZoom = prev || ZOOM_STEPS[0];
    }

    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/zoom`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ level: targetZoom })
        });
        const data = await resp.json();
        if (data.ok) {
            currentZoom = targetZoom;
            showZoomHUD(targetZoom);
        }
    } catch (e) {
        console.warn('[Zoom] Failed:', e);
    }
}

function showZoomHUD(level) {
    const pct = Math.round(level * 100);
    const msg = ZOOM_MESSAGES[level];
    const text = msg ? `Zoom: ${pct}% — ${msg}` : `Zoom: ${pct}%`;
    showToast(text, { type: 'dark', duration: 2000 });
}

// Fetch initial zoom level on load
fetch(`http://${VNC_HOST}:${CONTROL_PORT}/zoom`)
    .then(r => r.json())
    .then(data => { if (data.ok) currentZoom = data.zoom; })
    .catch(() => {});
