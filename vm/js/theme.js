// =============================================
// Host Media-Query Broadcaster
// =============================================
//
// The VM's Chromium (inside Docker/X11) has no way to read the host OS
// accessibility preferences. The control panel runs in the user's host
// browser, so it CAN read them via `window.matchMedia`. This module sends
// the full set of relevant media-query values to the control server on
// load and whenever any of them change. The server persists them as
// `host_prefs` and re-applies effective features to every open tab via
// CDP Emulation.setEmulatedMedia.

// Media features we mirror. Each entry maps a CSS media-feature name to
// an array of matchMedia queries and the value each one represents. The
// first matching query's value wins; if none match, the last entry
// (which is always the "no preference / off" default) is used.
const HOST_MEDIA_QUERIES = [
    { feature: 'prefers-color-scheme', queries: [
        ['(prefers-color-scheme: dark)', 'dark'],
        ['(prefers-color-scheme: light)', 'light'],
        [null, 'no-preference'],
    ]},
    { feature: 'prefers-reduced-motion', queries: [
        ['(prefers-reduced-motion: reduce)', 'reduce'],
        [null, 'no-preference'],
    ]},
    { feature: 'prefers-contrast', queries: [
        ['(prefers-contrast: more)', 'more'],
        ['(prefers-contrast: less)', 'less'],
        [null, 'no-preference'],
    ]},
    { feature: 'prefers-reduced-transparency', queries: [
        ['(prefers-reduced-transparency: reduce)', 'reduce'],
        [null, 'no-preference'],
    ]},
    { feature: 'forced-colors', queries: [
        ['(forced-colors: active)', 'active'],
        [null, 'none'],
    ]},
    { feature: 'inverted-colors', queries: [
        ['(inverted-colors: inverted)', 'active'],
        [null, 'none'],
    ]},
];

function readHostPrefs() {
    const out = {};
    for (const entry of HOST_MEDIA_QUERIES) {
        for (const [query, value] of entry.queries) {
            if (query === null) {
                out[entry.feature] = value;
                break;
            }
            try {
                if (window.matchMedia(query).matches) {
                    out[entry.feature] = value;
                    break;
                }
            } catch (e) {
                // Browser doesn't know this query — keep scanning.
            }
        }
    }
    return out;
}

async function broadcastHostPrefs() {
    const prefs = readHostPrefs();
    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/host-prefs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(prefs),
        });
        console.log('[HostPrefs] Broadcast', prefs);
    } catch (e) {
        console.warn('[HostPrefs] Broadcast failed:', e);
    }
}

// Wire up change listeners for every query we probe. matchMedia's change
// event only fires on true transitions, so this is cheap — each feature
// change triggers one POST.
for (const entry of HOST_MEDIA_QUERIES) {
    for (const [query] of entry.queries) {
        if (query === null) continue;
        try {
            window.matchMedia(query).addEventListener('change', broadcastHostPrefs);
        } catch (e) {
            // Some very old browsers don't support addEventListener on MQLs.
        }
    }
}

// Initial sync on load.
broadcastHostPrefs();
