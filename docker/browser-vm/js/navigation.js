// =============================================
// Internal URL (http://inspekt/) Support
// =============================================

// Track which tabs are showing internal content
const internalTabs = {};  // { tabId: inspektUrl }

// Track which tabs are "local" (iframe loaded from host network, not VM)
const localTabs = {};  // { tabId: { url, title } }
const closedTabs = []; // Stack of recently closed tabs (max 10)
const MAX_CLOSED_TABS = 10;

function isLocalTab(tabId) {
    return !!localTabs[tabId];
}

/**
 * Create a local tab and add it to the tabs array.
 * @param {string} url - URL to load in the iframe
 * @param {string} [title] - Tab title (defaults to hostname)
 * @param {number} [insertAfterIndex] - Insert after this index (-1 = append to end)
 * @returns {string} The new tab ID
 */
function _addLocalTab(url, title, insertAfterIndex = -1) {
    const tabId = 'local-' + Date.now();
    const tabTitle = title || (url !== 'about:blank' ? new URL(url).hostname : 'Local Tab');
    localTabs[tabId] = { url, title: tabTitle };
    const tabObj = { id: tabId, url, title: tabTitle, favicon: null, pinned: false, _isLocal: true };
    if (insertAfterIndex >= 0 && insertAfterIndex < tabs.length) {
        tabs.splice(insertAfterIndex + 1, 0, tabObj);
    } else {
        tabs.push(tabObj);
    }
    return tabId;
}

/**
 * Create a cloud tab via the server and optionally insert it after a source tab.
 * @param {string} url - URL to open
 * @param {string} [insertAfterTabId] - Insert after this tab (null = append to end)
 * @returns {Promise<string|null>} The new tab ID, or null on failure
 */
async function _addCloudTab(url, insertAfterTabId = null) {
    const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=${encodeURIComponent(url)}`);
    const data = await response.json();
    if (!data.ok) return null;

    const newTabId = data.tab.id;
    await fetchTabs();

    // Reorder: move new tab to right after the source tab
    if (insertAfterTabId) {
        const newTab = tabs.find(t => t.id === newTabId);
        const sourceIndex = tabs.findIndex(t => t.id === insertAfterTabId);
        if (newTab && sourceIndex >= 0) {
            tabs = tabs.filter(t => t.id !== newTabId);
            tabs.splice(sourceIndex + 1, 0, newTab);
            renderTabs();
        }
    }

    return newTabId;
}

// --- Tab persistence ---
const TAB_STORAGE_KEY = 'inspekt_tab_session';

let _saveTabSessionTimer = null;
function _scheduleSaveTabSession() {
    clearTimeout(_saveTabSessionTimer);
    _saveTabSessionTimer = setTimeout(saveTabSession, 500);
}

function saveTabSession() {
    clearTimeout(_saveTabSessionTimer);
    const session = {
        localTabs: { ...localTabs },
        closedTabs: [...closedTabs],
        tabOrder: tabs.map(t => t.id),
        activeTabId,
    };
    try {
        localStorage.setItem(TAB_STORAGE_KEY, JSON.stringify(session));
    } catch { /* storage full or unavailable */ }
}

function restoreTabSession() {
    try {
        const raw = localStorage.getItem(TAB_STORAGE_KEY);
        if (!raw) return;
        const session = JSON.parse(raw);

        // Restore closed tabs
        if (Array.isArray(session.closedTabs)) {
            closedTabs.push(...session.closedTabs.slice(-MAX_CLOSED_TABS));
        }

        // Restore local tabs
        if (session.localTabs && typeof session.localTabs === 'object') {
            for (const [id, data] of Object.entries(session.localTabs)) {
                if (data?.url) {
                    localTabs[id] = { url: data.url, title: data.title || 'Local Tab' };
                    tabs.push({
                        id,
                        url: data.url,
                        title: data.title || 'Local Tab',
                        favicon: null,
                        pinned: false,
                        _isLocal: true,
                    });
                }
            }
        }

        // Store the saved order and active tab for applying after fetchTabs
        _savedTabOrder = session.tabOrder || null;
        _savedActiveTabId = session.activeTabId || null;
    } catch { /* corrupt data, start fresh */ }
}

// Apply saved tab order after fetchTabs merges server tabs with local tabs
let _savedTabOrder = null;
let _savedActiveTabId = null;

function applySavedTabOrder() {
    if (!_savedTabOrder) return;
    const order = _savedTabOrder;
    _savedTabOrder = null;

    // Sort tabs to match saved order; unknown tabs go to the end
    const orderMap = new Map(order.map((id, i) => [id, i]));
    tabs.sort((a, b) => {
        const ai = orderMap.has(a.id) ? orderMap.get(a.id) : 9999;
        const bi = orderMap.has(b.id) ? orderMap.get(b.id) : 9999;
        return ai - bi;
    });

    // Restore active tab if it still exists
    if (_savedActiveTabId && tabs.find(t => t.id === _savedActiveTabId)) {
        activeTabId = _savedActiveTabId;
    }
    _savedActiveTabId = null;

    renderTabs();
    syncViewport();
}

/**
 * Check if a URL points to the internal Inspekt web interface.
 * These are URLs like http://inspekt/status, http://inspekt/commands, etc.
 */
function isInternalUrl(url) {
    return typeof url === 'string' && /^https?:\/\/inspekt(\/|$)/.test(url);
}

/**
 * Convert an http://inspekt/ URL to a proxied URL via the control server.
 * e.g. http://inspekt/status → http://host:8888/internal/status
 * The control server reverse-proxies to the Inspekt API (port 80 inside the VM).
 */
function resolveInternalUrl(inspektUrl) {
    const pathAndQuery = inspektUrl.replace(/^https?:\/\/inspekt/, '');
    return `http://${VNC_HOST}:${CONTROL_PORT}/internal${pathAndQuery || '/'}`;
}

/**
 * Switch the viewport to show the native iframe (for internal tool pages).
 * The VNC canvas is hidden and the native container is shown.
 */
function showNativeView(httpUrl) {
    // Terminal stays visible (split or floating) when switching to internal tabs
    const vncContainer = document.getElementById('vncContainer');
    const nativeContainer = document.getElementById('nativeContainer');

    vncContainer.classList.add('hidden-for-native');
    nativeContainer.classList.add('active');

    // Reuse existing iframe or create a new one
    let iframe = nativeContainer.querySelector('iframe');
    if (!iframe) {
        iframe = document.createElement('iframe');
        // No sandbox — these are trusted internal pages from our own API server
        nativeContainer.appendChild(iframe);
        // Forward Cmd+K from iframe to parent so the command palette works
        // when an internal tab (iframe) has focus
        iframe.addEventListener('load', () => {
            try {
                iframe.contentWindow.addEventListener('keydown', (e) => {
                    if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        const ninja = document.getElementById('commandPalette');
                        if (ninja) ninja.visible ? ninja.close() : ninja.open();
                    }
                    if (e.key === 'Escape') {
                        const ninja = document.getElementById('commandPalette');
                        if (ninja?.visible) { ninja.close(); e.preventDefault(); }
                    }
                });
            } catch { /* cross-origin iframe — can't inject */ }
        });
    }
    iframe.src = httpUrl;

    // For local tabs: show persistent info bar with "Open as Cloud Tab" escape hatch.
    // We can't reliably detect X-Frame-Options blocking from JS (Chrome shows a
    // cross-origin chrome-error:// page that's indistinguishable from a loaded site),
    // so we always show the bar and let the user dismiss it if the page loaded fine.
    const existingBar = nativeContainer.querySelector('.local-tab-info-bar');
    if (existingBar) existingBar.remove();

    if (activeTabId && localTabs[activeTabId] && httpUrl !== 'about:blank') {
        // Skip the info bar for localhost/127.0.0.1 — those won't have CSP issues
        try {
            const host = new URL(httpUrl).hostname;
            if (host === 'localhost' || host === '127.0.0.1' || host === '::1') {
                // No bar needed
            } else {
                const bar = document.createElement('div');
                bar.className = 'local-tab-info-bar';
                const capturedTabId = activeTabId;
                const capturedUrl = httpUrl;

                const span = document.createElement('span');
                span.append('Inspekt respects this website\u2019s Content-Security-Policy. If it refuses to load, you can open it in a ');
                const cloudLink = document.createElement('a');
                cloudLink.href = '#';
                cloudLink.textContent = 'Cloud Tab';
                cloudLink.addEventListener('click', (ev) => { ev.preventDefault(); convertToCloudTab(capturedTabId, capturedUrl); });
                span.append(cloudLink);
                span.append(' or your ');
                const browserLink = document.createElement('a');
                browserLink.href = '#';
                browserLink.textContent = 'default browser';
                browserLink.addEventListener('click', (ev) => { ev.preventDefault(); window.open(capturedUrl, '_blank'); });
                span.append(browserLink);
                span.append('.');
                bar.append(span);

                const dismiss = document.createElement('button');
                dismiss.className = 'dismiss';
                dismiss.title = 'Dismiss';
                dismiss.textContent = '\u2715';
                dismiss.addEventListener('click', () => bar.remove());
                bar.append(dismiss);

                nativeContainer.appendChild(bar);
            }
        } catch { /* invalid URL, skip bar */ }
    }
}

/**
 * Convert a local tab to a cloud tab by creating a server-side tab.
 */
async function convertToCloudTab(tabId, url) {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=${encodeURIComponent(url)}`);
        const data = await response.json();
        if (data.ok) {
            // Remove the local tab
            delete localTabs[tabId];
            tabs = tabs.filter(t => t.id !== tabId);
            // Switch to the new cloud tab — use activateTab to properly
            // swap the viewport back to VNC and update all state
            await fetchTabs();
            await activateTab(data.tab.id);
            showToast('Opened as Cloud Tab', 'success');
        } else {
            showToast('Failed to open as Cloud Tab', 'error');
        }
    } catch {
        showToast('Failed to open as Cloud Tab', 'error');
    }
}

/**
 * Switch the viewport back to the VNC canvas (for regular web pages).
 */
function showVncView() {
    const vncContainer = document.getElementById('vncContainer');
    const nativeContainer = document.getElementById('nativeContainer');

    nativeContainer.classList.remove('active');
    vncContainer.classList.remove('hidden-for-native');

    // Stop loading any internal page
    const iframe = nativeContainer.querySelector('iframe');
    if (iframe) iframe.src = 'about:blank';
}

/**
 * Update the viewport based on whether the active tab is internal.
 * Called on tab switch and after navigation.
 */
function syncViewport() {
    if (activeTabId && localTabs[activeTabId]) {
        showNativeView(localTabs[activeTabId].url);
    } else if (activeTabId && internalTabs[activeTabId]) {
        showNativeView(resolveInternalUrl(internalTabs[activeTabId]));
    } else {
        showVncView();
    }
    updateFeatureGating();
}

/**
 * Enable/disable VNC-dependent toolbar features based on active tab type.
 */
function updateFeatureGating() {
    const isLocal = activeTabId && isLocalTab(activeTabId);
    document.body.classList.toggle('local-tab-active', !!isLocal);

    // Update tooltips on gated toolbar buttons
    const gatedKeys = ['inspect', 'devtools', 'sr', 'audio', 'auto-scan', 'vision', 'recordings', 'screenshot', 'inspekt'];
    gatedKeys.forEach(key => {
        const wrapper = document.querySelector(`.toolbar-btn-wrapper[data-button-key="${key}"]`);
        if (!wrapper) return;
        const btn = wrapper.querySelector('button');
        if (!btn) return;
        if (isLocal) {
            btn._originalTitle = btn._originalTitle || btn.title;
            btn.title = `${btn._originalTitle} (unavailable for local tabs)`;
        } else if (btn._originalTitle) {
            btn.title = btn._originalTitle;
        }
    });
}

// =============================================
// Browser Navigation
// =============================================

const HISTORY_STORAGE_KEY = 'inspekt_url_history';

let currentUrl = '';
let currentTitle = '';
let visitedHistory = [];       // [{title, url}]
let historyDropdownOpen = false;
let historyActiveIndex = -1;

// Load history from localStorage on startup
try {
    const saved = localStorage.getItem(HISTORY_STORAGE_KEY);
    if (saved) visitedHistory = JSON.parse(saved);
} catch (e) { /* ignore corrupt data */ }

function saveHistory() {
    try {
        localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(visitedHistory));
    } catch (e) { /* ignore quota errors */ }
}

// --- Utility functions ---

function stripScheme(url) {
    return url.replace(/^https?:\/\//, '');
}

function displayUrl(url, showScheme) {
    if (!url || url === 'about:blank') return url || '';
    return showScheme ? url : stripScheme(url);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightMatch(text, filter) {
    if (!filter) return escapeHtml(text);
    const escaped = escapeHtml(text);
    const filterEscaped = escapeHtml(filter);
    const regex = new RegExp('(' + escapeRegex(filterEscaped) + ')', 'gi');
    return escaped.replace(regex, '<mark>$1</mark>');
}

// --- Nav button state ---

function updateNavButtons(canGoBack, canGoForward) {
    document.getElementById('backBtn').disabled = !canGoBack;
    document.getElementById('forwardBtn').disabled = !canGoForward;
}

// --- Per-tab navigation history helpers ---

function getNavHistory(tabId) {
    if (!tabNavHistory[tabId]) {
        tabNavHistory[tabId] = { entries: [], index: -1 };
    }
    return tabNavHistory[tabId];
}

function addToNavHistory(tabId, url) {
    if (!url || url === 'about:blank') return;
    const history = getNavHistory(tabId);
    // Don't add duplicate of current position
    if (history.index >= 0 && history.entries[history.index] === url) return;
    // Truncate any forward history (like a real browser)
    history.entries = history.entries.slice(0, history.index + 1);
    // Add new entry
    history.entries.push(url);
    // Enforce max history size
    if (history.entries.length > MAX_NAV_HISTORY) {
        history.entries.shift();
    }
    history.index = history.entries.length - 1;
}

function updateNavButtonsFromHistory() {
    if (!activeTabId) {
        updateNavButtons(false, false);
        return;
    }
    const history = getNavHistory(activeTabId);
    updateNavButtons(history.index > 0, history.index < history.entries.length - 1);
}

function fetchHistoryState() {
    updateNavButtonsFromHistory();
}

// --- Navigation actions ---

async function goBack() {
    if (!activeTabId) return;
    const history = getNavHistory(activeTabId);
    if (history.index <= 0) return;

    history.index--;
    const targetUrl = history.entries[history.index];
    navHistoryTarget = targetUrl;
    updateNavButtonsFromHistory();

    // If the target is an internal URL, handle locally
    if (isInternalUrl(targetUrl)) {
        internalTabs[activeTabId] = targetUrl;
        currentUrl = targetUrl;
        document.getElementById('urlBar').value = targetUrl;
        updateCloudIconState(targetUrl);
        showNativeView(resolveInternalUrl(targetUrl));
        navHistoryTarget = null;
        return;
    }

    // Navigating back to a normal page — restore VNC if needed
    if (internalTabs[activeTabId]) {
        delete internalTabs[activeTabId];
        showVncView();
    }

    startLoading(null);
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/navigate?url=${encodeURIComponent(targetUrl)}&tab=${activeTabId}`);
        const data = await response.json();
        if (data.ok) {
            setTimeout(updateCurrentUrl, 500);
            setTimeout(() => { if (loadingState === 'loading') completeLoading(); }, 400);
        } else {
            history.index++;  // Revert on failure
            navHistoryTarget = null;
            updateNavButtonsFromHistory();
            errorLoading();
            showToast(data.error || 'Cannot go back', 'error');
        }
    } catch (e) {
        history.index++;  // Revert on failure
        navHistoryTarget = null;
        updateNavButtonsFromHistory();
        errorLoading();
        showToast('Navigation failed', 'error');
    }
}

async function goForward() {
    if (!activeTabId) return;
    const history = getNavHistory(activeTabId);
    if (history.index >= history.entries.length - 1) return;

    history.index++;
    const targetUrl = history.entries[history.index];
    navHistoryTarget = targetUrl;
    updateNavButtonsFromHistory();

    // If the target is an internal URL, handle locally
    if (isInternalUrl(targetUrl)) {
        internalTabs[activeTabId] = targetUrl;
        currentUrl = targetUrl;
        document.getElementById('urlBar').value = targetUrl;
        updateCloudIconState(targetUrl);
        showNativeView(resolveInternalUrl(targetUrl));
        navHistoryTarget = null;
        return;
    }

    // Navigating forward to a normal page — restore VNC if needed
    if (internalTabs[activeTabId]) {
        delete internalTabs[activeTabId];
        showVncView();
    }

    startLoading(null);
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/navigate?url=${encodeURIComponent(targetUrl)}&tab=${activeTabId}`);
        const data = await response.json();
        if (data.ok) {
            setTimeout(updateCurrentUrl, 500);
            setTimeout(() => { if (loadingState === 'loading') completeLoading(); }, 400);
        } else {
            history.index--;  // Revert on failure
            navHistoryTarget = null;
            updateNavButtonsFromHistory();
            errorLoading();
            showToast(data.error || 'Cannot go forward', 'error');
        }
    } catch (e) {
        history.index--;  // Revert on failure
        navHistoryTarget = null;
        updateNavButtonsFromHistory();
        errorLoading();
        showToast('Navigation failed', 'error');
    }
}

async function reloadPage() {
    // Reload internal pages by re-setting the iframe src
    if (activeTabId && internalTabs[activeTabId]) {
        const nativeIframe = document.querySelector('#nativeContainer iframe');
        if (nativeIframe) {
            nativeIframe.src = resolveInternalUrl(internalTabs[activeTabId]);
            showToast('Page reloaded', 'success');
        }
        return;
    }

    // Honor per-tab reload options (clear cache/cookies/storage)
    const activeTab = tabs.find(t => t.id === activeTabId);
    const opts = activeTab ? getReloadOptions(activeTab.url) : { clearCache: false, clearCookies: false, clearStorage: false };
    const params = new URLSearchParams({ tab: activeTabId });
    if (opts.clearCache) params.append('clearCache', '1');
    if (opts.clearCookies) params.append('clearCookies', '1');
    if (opts.clearStorage) params.append('clearStorage', '1');

    startLoading(currentUrl);
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/reload-page?${params.toString()}`);
        const data = await response.json();
        if (data.ok) {
            const cleared = [];
            if (opts.clearCache) cleared.push('cache');
            if (opts.clearCookies) cleared.push('cookies');
            if (opts.clearStorage) cleared.push('storage');
            const msg = cleared.length
                ? `Reloaded (cleared ${cleared.join(', ')})`
                : 'Page reloaded';
            showToast(msg, 'success');
            if (activeTabId) {
                delete thumbnailCache[activeTabId];
                setTimeout(() => captureTabThumbnail(activeTabId), 2000);
            }
            // URL won't change on reload — brief flash for visual feedback
            setTimeout(() => { if (loadingState === 'loading') completeLoading(); }, 400);
        } else {
            errorLoading();
            showToast(data.error || 'Reload failed', 'error');
        }
    } catch (e) {
        errorLoading();
        showToast('Reload failed', 'error');
    }
}

function looksLikeUrl(input) {
    // Has explicit protocol
    if (/^https?:\/\//i.test(input)) return true;
    // Has a dot followed by a TLD-like segment (no spaces)
    if (/^[^\s]+\.[a-z]{2,}(\/.*)?$/i.test(input)) return true;
    // localhost or IP address
    if (/^(localhost|(\d{1,3}\.){3}\d{1,3})(:\d+)?(\/.*)?$/.test(input)) return true;
    return false;
}

async function navigateTo(url) {
    if (!url) return;
    dismissHistoryDropdown();

    // Block internal browser URLs (chrome://, file://, about:, etc.)
    const trimmed = url.trim().toLowerCase();
    if (trimmed.startsWith('chrome://') || trimmed.startsWith('chrome-extension://') ||
        trimmed.startsWith('file://') || trimmed.startsWith('about:') ||
        trimmed.startsWith('javascript:') || trimmed.startsWith('data:text/html')) {
        showToast('This URL is not available in the browser VM', 'error', 3000);
        return;
    }

    // --- Handle local tab navigation (update iframe directly) ---
    if (activeTabId && localTabs[activeTabId]) {
        let localUrl = url.trim();
        if (!localUrl.startsWith('http://') && !localUrl.startsWith('https://')) {
            localUrl = 'https://' + localUrl;
        }
        try { new URL(localUrl); } catch {
            showToast('Invalid URL', 'error');
            return;
        }
        const urlBar = document.getElementById('urlBar');
        urlBar.value = localUrl;
        urlBar.blur();
        currentUrl = localUrl;
        localTabs[activeTabId].url = localUrl;
        localTabs[activeTabId].title = new URL(localUrl).hostname;
        // Update tab title in tabs array
        const tab = tabs.find(t => t.id === activeTabId);
        if (tab) { tab.url = localUrl; tab.title = localTabs[activeTabId].title; }
        renderTabs();
        showNativeView(localUrl);
        return;
    }

    // --- Handle http://inspekt/ internal URLs ---
    if (isInternalUrl(url.trim())) {
        const inspektUrl = url.trim();
        const urlBar = document.getElementById('urlBar');
        urlBar.value = inspektUrl;
        urlBar.blur();
        currentUrl = inspektUrl;

        // Track this tab as internal
        if (activeTabId) {
            internalTabs[activeTabId] = inspektUrl;
            addToNavHistory(activeTabId, inspektUrl);
        }

        addToHistory(inspektUrl, inspektUrl);
        showNativeView(resolveInternalUrl(inspektUrl));
        updateCloudIconState(inspektUrl);
        fetchHistoryState();
        return;
    }

    // --- Normal URL handling (unchanged) ---

    // Search query → DuckDuckGo; URL-like input → navigate directly
    if (!looksLikeUrl(url.trim())) {
        const searchEngine = getConfig('browser.search-engine', 'https://duckduckgo.com/?q=');
        url = searchEngine + encodeURIComponent(url.trim());
    } else if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
    }

    // Leaving an internal page → clear internal state and restore VNC
    if (activeTabId && internalTabs[activeTabId]) {
        delete internalTabs[activeTabId];
        showVncView();
    }

    const urlBar = document.getElementById('urlBar');
    urlBar.value = url;
    urlBar.blur();

    // Handle about:blank immediately
    if (url === 'about:blank') {
        startLoading(url);
        completeLoading();
    } else {
        startLoading(url);
    }

    // Pre-check DNS — if domain doesn't resolve, show branded error page
    // instead of Chromium's default ERR_NAME_NOT_RESOLVED
    try {
        const domain = new URL(url).hostname;
        if (domain && domain !== 'localhost' && domain !== '127.0.0.1' && domain !== 'inspekt') {
            const dnsResp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/dns-check?domain=${encodeURIComponent(domain)}`);
            const dnsData = await dnsResp.json();
            if (dnsData.ok && !dnsData.resolves) {
                // Navigate to our custom error page instead
                const errorUrl = `http://inspekt/error/dns?domain=${encodeURIComponent(domain)}`;
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/navigate?url=${encodeURIComponent(errorUrl)}&tab=${activeTabId}`);
                completeLoading();
                return;
            }
        }
    } catch { /* DNS check failed — proceed with normal navigation */ }

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/navigate?url=${encodeURIComponent(url)}&tab=${activeTabId}`);
        const data = await response.json();
        if (data.ok) {
            // Focus VNC canvas so Tab goes straight to the page
            if (rfb) rfb.focus();
            setTimeout(() => {
                updateCurrentUrl();
                // Add to history after title has been captured
                addToHistory(url, currentTitle || url);
            }, 1500);
            if (activeTabId) {
                delete thumbnailCache[activeTabId];
                setTimeout(() => captureTabThumbnail(activeTabId), 2000);
            }
            setTimeout(fetchHistoryState, 1000);
            // Same-URL navigation (Enter on loaded page): URL won't change,
            // brief flash for visual feedback
            if (url === currentUrl) {
                setTimeout(() => { if (loadingState === 'loading') completeLoading(); }, 400);
            }
        } else {
            errorLoading();
            showToast(data.error || 'Navigation failed', 'error');
        }
    } catch (e) {
        errorLoading();
        showToast('Navigation failed', 'error');
    }
}

// --- URL display & polling ---

async function updateCurrentUrl() {
    // Don't poll Chrome for URL when viewing an internal page
    if (activeTabId && internalTabs[activeTabId]) return;

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/url?tab=${activeTabId}`);
        const data = await response.json();
        if (data.ok && data.url) {
            // Detect navigation completion
            if (loadingState === 'loading' && data.url) {
                const urlChanged = data.url !== loadingPreviousUrl;
                const isReload = loadingExpectedUrl === loadingPreviousUrl;
                // For reload: URL won't change, handled by its own setTimeout
                // For everything else: complete as soon as URL differs from pre-nav URL
                if (!isReload && urlChanged) {
                    completeLoading();
                }
            }
            currentTitle = data.title || '';
            const urlBar = document.getElementById('urlBar');
            const urlChanged = data.url !== currentUrl;
            if (document.activeElement !== urlBar && urlChanged) {
                currentUrl = data.url;
                urlBar.value = displayUrl(currentUrl, false);
            } else if (urlChanged) {
                currentUrl = data.url;
            }
            // Update cloud icon HTTPS state + terminal prompt
            if (urlChanged) {
                updateCloudIconState(currentUrl);
                updateTerminalPrompt(currentUrl);
                // Clear plugin loaded state on navigation
                loadedPlugins.clear();
                if (pluginDropdownOpen) renderPluginList();
                // Trigger autorun plugins on navigation
                triggerAutorunPlugins(currentUrl);
                // Sitemap: auto-fetch on new domain, refresh tree for current page.
                // maybeFetchSitemap resets _sitemapNav synchronously before its
                // first await, so stale data is cleared immediately.
                maybeFetchSitemap(currentUrl);
                refreshSitemapNav(currentUrl);
            }
            // Auto-detect internal URL: if Chrome navigated to http://inspekt/,
            // switch to native iframe view automatically
            if (urlChanged && isInternalUrl(data.url) && activeTabId && !internalTabs[activeTabId]) {
                internalTabs[activeTabId] = data.url;
                showNativeView(resolveInternalUrl(data.url));
            }
            // Track URL changes for back/forward navigation history
            if (urlChanged && activeTabId) {
                if (navHistoryTarget) {
                    // Expected navigation from back/forward — don't add new entry
                    navHistoryTarget = null;
                } else {
                    addToNavHistory(activeTabId, data.url);
                }
            }
            // Refresh back/forward button state from client-side history
            fetchHistoryState();
        }
    } catch (e) {
        // Silently fail
    }
}

// Poll for URL updates every 2 seconds
setInterval(updateCurrentUrl, 2000);

// --- Loading Progress Indicator ---

let loadingState = 'idle'; // idle | loading | completing | error
let loadingProgress = 0;
let loadingTrickleTimer = null;
let loadingFastPollTimer = null;
let loadingExpectedUrl = null;
let loadingStartTime = 0;
let loadingPreviousUrl = '';
const LOADING_MAX_TIMEOUT = 30000;

const RELOAD_SVG = '<svg viewBox="0 0 24 24"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>';
const STOP_SVG = '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';

function startLoading(expectedUrl) {
    // Cancel any in-progress loading
    if (loadingTrickleTimer) clearInterval(loadingTrickleTimer);
    if (loadingFastPollTimer) clearInterval(loadingFastPollTimer);

    loadingState = 'loading';
    loadingProgress = 0;
    loadingExpectedUrl = expectedUrl;
    loadingPreviousUrl = currentUrl;
    loadingStartTime = Date.now();

    const bar = document.getElementById('urlBarProgress');
    bar.className = 'url-bar-progress active';
    setProgress(0);

    // Set tab spinner
    if (activeTabId) setTabLoading(activeTabId, true);

    // Swap reload → stop
    setReloadButtonMode('stop');

    // Start trickle
    loadingTrickleTimer = setInterval(() => {
        if (loadingState !== 'loading') return;

        // Max timeout
        if (Date.now() - loadingStartTime > LOADING_MAX_TIMEOUT) {
            completeLoading();
            return;
        }

        // Trickle algorithm: decreasing increments
        let increment;
        if (loadingProgress < 30) {
            increment = 3 + Math.random() * 5;
        } else if (loadingProgress < 60) {
            increment = 1 + Math.random() * 3;
        } else if (loadingProgress < 85) {
            increment = 0.3 + Math.random();
        } else {
            increment = 0; // Freeze at 85-95%, wait for signal
        }

        loadingProgress = Math.min(loadingProgress + increment, 95);
        setProgress(loadingProgress);
    }, 400);

    // Fast-poll URL during loading (500ms) for quicker completion detection
    loadingFastPollTimer = setInterval(() => {
        if (loadingState !== 'loading') return;
        updateCurrentUrl();
    }, 500);
}

function setProgress(value) {
    const bar = document.getElementById('urlBarProgress');
    bar.style.transform = `scaleX(${value / 100})`;
    bar.setAttribute('aria-valuenow', Math.round(value));
}

function completeLoading() {
    if (loadingState === 'idle') return;
    loadingState = 'completing';

    if (loadingTrickleTimer) {
        clearInterval(loadingTrickleTimer);
        loadingTrickleTimer = null;
    }
    if (loadingFastPollTimer) {
        clearInterval(loadingFastPollTimer);
        loadingFastPollTimer = null;
    }

    // Jump to 100% and fade
    setProgress(100);
    const bar = document.getElementById('urlBarProgress');
    bar.classList.add('complete');

    // Restore reload button and clear spinner
    setReloadButtonMode('reload');
    if (activeTabId) setTabLoading(activeTabId, false);

    // Reset after fade-out
    setTimeout(() => {
        bar.className = 'url-bar-progress';
        bar.style.transform = 'scaleX(0)';
        loadingState = 'idle';
        loadingExpectedUrl = null;
    }, 600);
}

function errorLoading() {
    if (loadingState === 'idle') return;

    if (loadingTrickleTimer) {
        clearInterval(loadingTrickleTimer);
        loadingTrickleTimer = null;
    }
    if (loadingFastPollTimer) {
        clearInterval(loadingFastPollTimer);
        loadingFastPollTimer = null;
    }

    loadingState = 'error';

    // Red fill and fade
    setProgress(100);
    const bar = document.getElementById('urlBarProgress');
    bar.className = 'url-bar-progress active error';

    // Trigger fade after a brief red flash
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            bar.classList.remove('active');
        });
    });

    // Restore reload button and clear spinner
    setReloadButtonMode('reload');
    if (activeTabId) setTabLoading(activeTabId, false);

    // Reset after fade-out
    setTimeout(() => {
        bar.className = 'url-bar-progress';
        bar.style.transform = 'scaleX(0)';
        loadingState = 'idle';
        loadingExpectedUrl = null;
    }, 800);
}

function setReloadButtonMode(mode) {
    const btn = document.getElementById('reloadBtn');
    if (!btn) return;
    if (mode === 'stop') {
        btn.innerHTML = STOP_SVG;
        btn.onclick = stopLoading;
        btn.title = 'Stop loading';
        btn.setAttribute('aria-label', 'Stop loading');
    } else {
        btn.innerHTML = RELOAD_SVG;
        btn.onclick = reloadPage;
        btn.title = 'Reload page';
        btn.setAttribute('aria-label', 'Reload page');
    }
}

function stopLoading() {
    completeLoading();
}

// Initialize reload button handler (no HTML onclick attribute — managed by JS)
setReloadButtonMode('reload');

function setTabLoading(tabId, isLoading) {
    const tabEl = document.querySelector(`.tab[data-tab-id="${tabId}"]`);
    if (!tabEl) return;
    if (isLoading) {
        tabEl.classList.add('loading');
        // Inject spinner if not already present
        if (!tabEl.querySelector('.tab-favicon-spinner')) {
            const spinner = document.createElement('div');
            spinner.className = 'tab-favicon-spinner';
            tabEl.insertBefore(spinner, tabEl.firstChild);
        }
    } else {
        tabEl.classList.remove('loading');
    }
}

// --- Focus/blur lifecycle (scheme show/hide) ---

(function setupUrlBarFocusHandlers() {
    const urlBar = document.getElementById('urlBar');

    urlBar.addEventListener('focus', () => {
        urlBar.value = currentUrl;
        urlBar.select();
        showHistoryDropdown();
    });

    urlBar.addEventListener('blur', () => {
        setTimeout(() => {
            if (!historyDropdownOpen) {
                urlBar.value = displayUrl(currentUrl, false);
            }
        }, 150);
    });
})();

// --- History data management ---

function addToHistory(url, title) {
    if (!url || url === 'about:blank') return;
    // Remove existing entry with same URL
    visitedHistory = visitedHistory.filter(e => e.url !== url);
    // Prepend new entry
    visitedHistory.unshift({ url, title: title || url });
    // Cap at 15
    if (visitedHistory.length > 15) {
        visitedHistory = visitedHistory.slice(0, 15);
    }
    saveHistory();
}

function clearHistory() {
    visitedHistory = [];
    saveHistory();
    dismissHistoryDropdown();
}

async function seedHistoryFromServer() {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/history?tab=${activeTabId}`);
        const data = await response.json();
        if (data.ok && data.entries) {
            let added = false;
            for (const entry of data.entries) {
                if (entry.url && entry.url !== 'about:blank') {
                    // Only add if not already present
                    if (!visitedHistory.some(e => e.url === entry.url)) {
                        visitedHistory.push({ url: entry.url, title: entry.title || entry.url });
                        added = true;
                    }
                }
            }
            // Cap at 15
            if (visitedHistory.length > 15) {
                visitedHistory = visitedHistory.slice(0, 15);
            }
            if (added) saveHistory();
        }
    } catch (e) {
        // Silently fail
    }
}

// --- Cloud icon HTTPS state ---

// SVG constants for the cloud icon button
const CLOUD_SVG = '<svg viewBox="0 0 24 24" width="16" height="16"><path class="cloud-shape" d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96z" fill="currentColor"/><g class="cloud-padlock"><rect x="9" y="12.5" width="6" height="4.5" rx="1" fill="var(--bg-bar)"/><path d="M10.5 12.5V11a1.5 1.5 0 0 1 3 0v1.5" stroke="var(--bg-bar)" stroke-width="1.3" fill="none"/></g></svg>';
const INSPEKT_SVG = '<svg viewBox="0 0 16 16" width="16" height="16"><rect x="1" y="1" width="14" height="14" rx="3" fill="currentColor"/><text x="8" y="12" text-anchor="middle" font-size="10" font-weight="700" font-family="system-ui, sans-serif" fill="var(--bg-bar)">I</text></svg>';

function updateCloudIconState(url) {
    const cloudIcon = document.getElementById('urlBarCloudIcon');
    const pluginIcon = document.getElementById('urlBarPluginIcon');
    if (!cloudIcon) return;

    const isInternal = isInternalUrl(url);

    if (isInternal) {
        // Internal page: show Inspekt placeholder icon, non-clickable
        cloudIcon.classList.remove('secure');
        cloudIcon.classList.add('internal');
        cloudIcon.innerHTML = INSPEKT_SVG;
        cloudIcon.title = 'Inspekt internal page';
        cloudIcon.setAttribute('aria-label', 'Inspekt internal page');
    } else {
        // External page: restore cloud icon and click behavior
        cloudIcon.classList.remove('internal');
        cloudIcon.innerHTML = CLOUD_SVG;
        if (url && url.startsWith('https://')) {
            cloudIcon.classList.add('secure');
            cloudIcon.title = 'Secure connection (HTTPS) — Click for page info';
        } else if (url && url !== 'about:blank') {
            cloudIcon.classList.remove('secure');
            cloudIcon.title = 'Not secure (HTTP) — Click for page info';
        }
        cloudIcon.setAttribute('aria-label', 'Page information');
    }

    // Hide plugin icon on internal Inspekt pages
    if (pluginIcon) {
        pluginIcon.style.display = isInternal ? 'none' : '';
        if (isInternal && pluginDropdownOpen) closePluginDropdown();
    }
}
