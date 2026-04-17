// =============================================
// Theme Sync (Dark/Light Mode)
// =============================================

// Detect host color scheme preference
function getColorScheme() {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

// Sync color scheme to VM
async function syncColorScheme(scheme) {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/theme/${scheme}`, {
            method: 'POST'
        });
        const data = await response.json();
        if (data.ok && data.changed) {
            console.log(`[Theme] Synced to ${scheme} mode`);
            showToast(`Switched to ${scheme} mode`, 'success');
        }
    } catch (e) {
        console.error('[Theme] Failed to sync:', e);
    }
}

// Listen for host theme changes
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    const scheme = e.matches ? 'dark' : 'light';
    console.log(`[Theme] Host changed to ${scheme} mode`);
    syncColorScheme(scheme);
});

