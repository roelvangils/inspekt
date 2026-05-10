// =============================================
// Device Profiles (DevTools-style emulation)
// =============================================
//
// Catalog of viewport profiles that can be applied via the device-emulation
// pipeline (CDP Emulation.setDeviceMetricsOverride + setUserAgentOverride +
// setTouchEmulationEnabled). The control panel is the single source of truth;
// the backend is a dumb pass-through that applies whatever metrics it's
// handed via POST /device.
//
// Module-scope `var` so device-emulation.js and command-palette.js can read
// the same list regardless of bundle concatenation order — same convention
// as DEVICE_SNAPS in split-mode.js.

var DEVICE_PROFILES = [
    // --- Specific devices (with UA spoofing) -------------------------------
    {
        id: 'iphone-14',
        label: 'iPhone 14',
        category: 'phone',
        width: 390, height: 844, dpr: 3, mobile: true,
        cornerRadius: 14,
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    },
    {
        id: 'iphone-se',
        label: 'iPhone SE',
        category: 'phone',
        width: 375, height: 667, dpr: 2, mobile: true,
        cornerRadius: 4,
        userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    },
    {
        id: 'pixel-8',
        label: 'Pixel 8',
        category: 'phone',
        width: 412, height: 915, dpr: 2.625, mobile: true,
        cornerRadius: 16,
        userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36',
    },
    {
        id: 'galaxy-s24',
        label: 'Galaxy S24',
        category: 'phone',
        width: 360, height: 780, dpr: 3, mobile: true,
        cornerRadius: 18,
        userAgent: 'Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Mobile Safari/537.36',
    },
    {
        id: 'ipad',
        label: 'iPad',
        category: 'tablet',
        width: 820, height: 1180, dpr: 2, mobile: true,
        cornerRadius: 12,
        userAgent: 'Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    },
    {
        id: 'ipad-pro-11',
        label: 'iPad Pro 11"',
        category: 'tablet',
        width: 834, height: 1194, dpr: 2, mobile: true,
        cornerRadius: 14,
        userAgent: 'Mozilla/5.0 (iPad; CPU OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
    },

    // --- Generic categories (no UA spoofing — neutral breakpoint testing) --
    {
        id: 'generic-mobile',
        label: 'Mobile',
        category: 'phone',
        width: 375, height: 667, dpr: 2, mobile: true,
        cornerRadius: 12,
    },
    {
        id: 'generic-tablet',
        label: 'Tablet',
        category: 'tablet',
        width: 768, height: 1024, dpr: 2, mobile: true,
        cornerRadius: 10,
    },
    {
        id: 'generic-desktop',
        label: 'Desktop',
        category: 'desktop',
        width: 1280, height: 800, dpr: 1, mobile: false,
        cornerRadius: 0,
    },
    {
        id: 'generic-wide',
        label: 'Wide',
        category: 'desktop',
        width: 1920, height: 1080, dpr: 1, mobile: false,
        cornerRadius: 0,
    },
];

function getDeviceProfile(id) {
    if (!id) return null;
    return DEVICE_PROFILES.find(p => p.id === id) || null;
}

// Render a DPR like 2.625 as "2.625×" but 2.0 as "2×".
function formatDpr(dpr) {
    if (Number.isInteger(dpr)) return `${dpr}×`;
    return `${dpr.toFixed(2).replace(/\.?0+$/, '')}×`;
}
