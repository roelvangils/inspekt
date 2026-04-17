// =============================================
// Restart Modal & Tab Persistence
// =============================================

// Pinned tab persistence (stored by URL since tab IDs change across restarts)
function getPinnedUrls() {
    try { return JSON.parse(localStorage.getItem('inspekt_pinned_tabs')) || []; }
    catch { return []; }
}

function savePinnedUrls() {
    const pinnedUrls = tabs.filter(t => t.pinned).map(t => t.url);
    localStorage.setItem('inspekt_pinned_tabs', JSON.stringify(pinnedUrls));
}

// Per-tab reload options (clear cache/cookies/storage on reload)
function getReloadOptions(tabUrl) {
    try {
        const all = JSON.parse(localStorage.getItem('inspekt_tab_reload_options')) || {};
        return all[tabUrl] || { clearCache: false, clearCookies: false, clearStorage: false };
    } catch { return { clearCache: false, clearCookies: false, clearStorage: false }; }
}

function setReloadOption(tabUrl, key, value) {
    try {
        const all = JSON.parse(localStorage.getItem('inspekt_tab_reload_options')) || {};
        if (!all[tabUrl]) all[tabUrl] = { clearCache: false, clearCookies: false, clearStorage: false };
        all[tabUrl][key] = value;
        localStorage.setItem('inspekt_tab_reload_options', JSON.stringify(all));
    } catch (e) { console.warn('[ReloadOptions] Failed to save:', e); }
}

// Save current tabs to localStorage (survives container restarts)
function saveTabsToStorage() {
    const tabData = tabs.map(t => ({ url: t.url, title: t.title, pinned: !!t.pinned }));
    localStorage.setItem('inspekt_saved_tabs', JSON.stringify(tabData));
    console.log('[Restart] Saved', tabData.length, 'tabs to localStorage');
}

// Restore tabs from localStorage
async function restoreTabsFromStorage() {
    const saved = localStorage.getItem('inspekt_saved_tabs');
    if (!saved) return;

    try {
        const tabData = JSON.parse(saved);
        localStorage.removeItem('inspekt_saved_tabs'); // Clear after reading

        if (tabData.length === 0) return;

        showToast(`Restoring ${tabData.length} tab(s)…`);
        console.log('[Restart] Restoring tabs:', tabData);

        // Collect pinned URLs to restore pinned state after tabs are created
        const restoredPinnedUrls = tabData.filter(t => t.pinned).map(t => t.url);

        for (let i = 0; i < tabData.length; i++) {
            const tab = tabData[i];
            // First tab: navigate current tab, rest: create new tabs
            if (i === 0) {
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/navigate?url=${encodeURIComponent(tab.url)}`);
            } else {
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=${encodeURIComponent(tab.url)}`);
            }
            await new Promise(r => setTimeout(r, 500)); // Small delay between tabs
        }

        // Persist pinned URLs so fetchTabs can restore pinned state
        if (restoredPinnedUrls.length > 0) {
            localStorage.setItem('inspekt_pinned_tabs', JSON.stringify(restoredPinnedUrls));
        }

        showToast('Tabs restored!', 'success');
    } catch (e) {
        console.error('[Restart] Failed to restore tabs:', e);
    }
}

// Open restart modal
function openRestartModal() {
    document.getElementById('restartModalOverlay').classList.add('open');
}

// Close restart modal
function closeRestartModal() {
    document.getElementById('restartModalOverlay').classList.remove('open');
}

