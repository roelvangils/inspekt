// =============================================
// Tab Management (Real Chrome Tabs via CDP)
// =============================================

let tabs = [];
let activeTabId = null;
let draggedTab = null;

// Per-tab navigation history for back/forward buttons
const tabNavHistory = {};  // { tabId: { entries: [url, ...], index: -1 } }
const MAX_NAV_HISTORY = 50;
let navHistoryTarget = null;  // Expected URL from back/forward navigation

// =============================================
// Tab Thumbnail Management
// =============================================

const tabActivationTimes = {};  // {tabId: timestamp}
const MIN_TIME_FOR_THUMBNAIL = 2000;  // 2 seconds
let thumbnailHoverTimeout = null;
let thumbnailHideTimeout = null;  // Delay before hiding (allows smooth transition between tabs)
const THUMBNAIL_HOVER_DELAY = 300;  // ms before showing thumbnail
const THUMBNAIL_HIDE_DELAY = 100;   // ms delay before hiding (allows transition to next tab)
let currentThumbnailTabId = null;  // Track which tab's thumbnail is showing
const thumbnailCache = {};      // {tabId: base64Data} — avoids redundant fetches
const lastKnownUrls = {};       // {tabId: url} — tracks URL changes to invalidate thumbnails
let thumbnailRequestId = 0;     // monotonic counter — guards against stale async responses

function onTabActivated(tabId) {
    tabActivationTimes[tabId] = Date.now();
    // Also track for auto-scan
    tabVisitTimes[tabId] = { startTime: Date.now(), scanned: false };
}

function shouldCaptureThumbnail(tabId) {
    const activatedAt = tabActivationTimes[tabId];
    if (!activatedAt) return false;
    return (Date.now() - activatedAt) >= MIN_TIME_FOR_THUMBNAIL;
}

async function captureTabThumbnail(tabId) {
    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tabId}/screenshot`);
        delete thumbnailCache[tabId];
    } catch (e) {
        console.warn('[Thumbnails] Failed to capture:', e);
    }
}

function calculateThumbnailPosition(tabElement) {
    const rect = tabElement.getBoundingClientRect();
    const previewWidth = 248;  // 240px img + 8px padding

    // Calculate left position (center under tab, but keep in viewport)
    let left = rect.left + (rect.width / 2) - (previewWidth / 2);
    left = Math.max(8, Math.min(left, window.innerWidth - previewWidth - 8));

    return {
        left: left,
        top: rect.bottom + 8
    };
}

async function showThumbnail(tabId, tabElement) {
    // Don't show thumbnail for about:blank or empty tabs — hide if currently visible
    const tab = tabs.find(t => t.id === tabId);
    if (tab && (!tab.url || tab.url === 'about:blank')) {
        hideThumbnail();
        return;
    }

    // Cancel any pending hide - we're showing a new thumbnail
    clearTimeout(thumbnailHideTimeout);
    thumbnailHideTimeout = null;

    const preview = document.getElementById('thumbnailPreview');
    const currentImg = preview.querySelector('.thumbnail-current');
    const nextImg = preview.querySelector('.thumbnail-next');
    const urlDiv = preview.querySelector('.thumbnail-url');

    // Calculate position first
    const pos = calculateThumbnailPosition(tabElement);

    // If already showing a thumbnail, animate to new position with crossfade
    const isAlreadyVisible = preview.classList.contains('visible') || preview.classList.contains('moving');

    // Same tab already visible - just reposition if needed, no fetch
    if (isAlreadyVisible && currentThumbnailTabId === tabId) {
        preview.style.left = `${pos.left}px`;
        preview.style.top = `${pos.top}px`;
        return;
    }

    // Stale-response guard: increment counter, capture our request ID
    const myRequestId = ++thumbnailRequestId;

    // Helper to get thumbnail data (from cache or network)
    async function getThumbnailData() {
        // Check cache first
        if (thumbnailCache[tabId]) {
            return thumbnailCache[tabId];
        }

        // For the active tab with no cache, trigger a live capture first
        if (tabId === activeTabId) {
            try {
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tabId}/screenshot`);
            } catch (e) {
                // Ignore capture failure, still try to fetch thumbnail
            }
            // Stale check after await
            if (thumbnailRequestId !== myRequestId) return null;
        }

        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tabId}/thumbnail`);
        const data = await response.json();

        if (data.ok && data.thumbnail) {
            thumbnailCache[tabId] = data.thumbnail;
            return data.thumbnail;
        }
        return null;
    }

    if (isAlreadyVisible) {
        // Moving to a different tab - animate position and crossfade
        preview.classList.add('moving');

        // Set new position (will animate due to CSS transition)
        preview.style.left = `${pos.left}px`;
        preview.style.top = `${pos.top}px`;

        // Fetch new thumbnail and crossfade
        try {
            const base64 = await getThumbnailData();
            if (thumbnailRequestId !== myRequestId) return;  // stale

            if (base64) {
                const dataUrl = `data:image/jpeg;base64,${base64}`;

                // Preload image off-screen before showing
                const preload = new Image();
                preload.src = dataUrl;
                try { await preload.decode(); } catch (e) { /* fallback: show anyway */ }
                if (thumbnailRequestId !== myRequestId) return;  // stale

                // Assign decoded image to the next slot (still opacity 0)
                nextImg.src = dataUrl;

                // Fade nextImg in over the still-visible currentImg
                requestAnimationFrame(() => {
                    nextImg.style.opacity = '1';
                });

                // After crossfade completes, swap images back for next transition
                nextImg.addEventListener('transitionend', function onEnd() {
                    nextImg.removeEventListener('transitionend', onEnd);
                    currentImg.src = nextImg.src;
                    // Reset inline opacity so classes take effect again
                    nextImg.style.opacity = '';
                    nextImg.src = '';
                }, { once: true });

                // Update URL
                if (tab) {
                    urlDiv.textContent = tab.url.replace(/^https?:\/\//, '');
                }

                currentThumbnailTabId = tabId;
            }
        } catch (e) {
            console.warn('[Thumbnails] Failed to fetch:', e);
        }
    } else {
        // First show - no animation, just appear
        try {
            const base64 = await getThumbnailData();
            if (thumbnailRequestId !== myRequestId) return;  // stale

            if (base64) {
                const dataUrl = `data:image/jpeg;base64,${base64}`;

                // Preload image off-screen before showing
                const preload = new Image();
                preload.src = dataUrl;
                try { await preload.decode(); } catch (e) { /* fallback: show anyway */ }
                if (thumbnailRequestId !== myRequestId) return;  // stale

                currentImg.src = dataUrl;

                // Update URL
                if (tab) {
                    urlDiv.textContent = tab.url.replace(/^https?:\/\//, '');
                }

                // Set position BEFORE making visible (fixes top-left jump)
                // Disable transition temporarily for initial positioning
                preview.style.transition = 'none';
                preview.style.left = `${pos.left}px`;
                preview.style.top = `${pos.top}px`;

                // Force reflow to apply position immediately
                preview.offsetHeight;

                // Re-enable transitions
                preview.style.transition = '';

                // Now make visible
                preview.classList.add('visible');
                currentThumbnailTabId = tabId;
            }
        } catch (e) {
            console.warn('[Thumbnails] Failed to fetch:', e);
        }
    }
}

function hideThumbnail() {
    // Use a delay so that moving between tabs allows smooth transition
    clearTimeout(thumbnailHideTimeout);
    thumbnailHideTimeout = setTimeout(() => {
        // Invalidate any in-flight showThumbnail() calls
        thumbnailRequestId++;
        const preview = document.getElementById('thumbnailPreview');
        preview.classList.remove('visible');
        preview.classList.remove('moving');
        currentThumbnailTabId = null;
        // Reset crossfade state so next show starts clean
        const nextImg = preview.querySelector('.thumbnail-next');
        if (nextImg) { nextImg.style.opacity = ''; nextImg.src = ''; }
    }, THUMBNAIL_HIDE_DELAY);
}

function hideThumbnailImmediately() {
    clearTimeout(thumbnailHideTimeout);
    // Invalidate any in-flight showThumbnail() calls
    thumbnailRequestId++;
    const preview = document.getElementById('thumbnailPreview');
    preview.classList.remove('visible');
    preview.classList.remove('moving');
    currentThumbnailTabId = null;
    // Reset crossfade state so next show starts clean
    const nextImg = preview.querySelector('.thumbnail-next');
    if (nextImg) { nextImg.style.opacity = ''; nextImg.src = ''; }
}

// =============================================
// Tab Grid Overview
// =============================================

const gridState = {
    isOpen: false,
    scanData: {}  // {tabId: {a11y_violations, console_errors, missing_alt, last_command, thumbnail}}
};

// Auto-scan state
let autoScanEnabled = false;
const tabVisitTimes = {};  // {tabId: {startTime, scanned}}
const AUTO_SCAN_THRESHOLD = 5000;  // 5 seconds

async function toggleTabGrid() {
    if (gridState.isOpen) {
        closeTabGrid();
    } else {
        await openTabGrid();
    }
}

async function openTabGrid() {
    gridState.isOpen = true;
    const overlay = document.getElementById('tabGridOverlay');
    const gridBtn = document.getElementById('gridViewBtn');

    // Show overlay
    overlay.classList.add('open');
    if (gridBtn) gridBtn.classList.add('active');

    // Hide thumbnail preview
    hideThumbnailImmediately();

    // Update tab count
    document.getElementById('gridTabCount').textContent = `${tabs.length} tab${tabs.length !== 1 ? 's' : ''}`;

    // Show loading state and fetch data
    renderTabGridLoading();
    await refreshGridData();
    renderTabGrid();
}

function closeTabGrid() {
    gridState.isOpen = false;
    const overlay = document.getElementById('tabGridOverlay');
    const gridBtn = document.getElementById('gridViewBtn');

    overlay.classList.remove('open');
    if (gridBtn) gridBtn.classList.remove('active');
}

function renderTabGridLoading() {
    const container = document.getElementById('tabGridContainer');
    container.innerHTML = tabs.map(tab => `
        <div class="tab-grid-card loading" data-tab-id="${tab.id}">
            <div class="card-thumbnail"></div>
            <div class="card-info">
                <div class="card-title">${escapeHtml(tab.title || 'New Tab')}</div>
                <div class="card-url">${escapeHtml(tab.url || '')}</div>
            </div>
            <div class="card-stats">
                <span class="stat">Loading...</span>
            </div>
        </div>
    `).join('');
}

async function refreshGridData() {
    try {
        // Trigger scan for all tabs
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/scan-all`);

        // Fetch scan data and thumbnails for each tab in parallel
        const promises = tabs.map(async (tab) => {
            try {
                const [scanResp, thumbResp] = await Promise.all([
                    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tab.id}/scan-data`),
                    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tab.id}/thumbnail`)
                ]);

                const scanData = await scanResp.json();
                const thumbData = await thumbResp.json();

                gridState.scanData[tab.id] = {
                    a11y_violations: scanData.a11y_violations,
                    console_errors: scanData.console_errors,
                    missing_alt: scanData.missing_alt,
                    last_command: scanData.last_command,
                    thumbnail: thumbData.thumbnail
                };
            } catch (e) {
                console.warn('[Grid] Failed to fetch data for tab:', tab.id, e);
                gridState.scanData[tab.id] = {
                    a11y_violations: null,
                    console_errors: null,
                    missing_alt: null,
                    last_command: null,
                    thumbnail: null
                };
            }
        });

        await Promise.all(promises);
    } catch (e) {
        console.error('[Grid] Failed to refresh data:', e);
    }
}

function renderTabGrid() {
    const container = document.getElementById('tabGridContainer');
    container.innerHTML = tabs.map(tab => {
        const data = gridState.scanData[tab.id] || {};
        const isActive = tab.id === activeTabId;

        // Get domain initial for placeholder
        let domainInitial = '?';
        try {
            const url = new URL(tab.url || 'about:blank');
            domainInitial = url.hostname.charAt(0).toUpperCase() || '?';
        } catch (e) {
            domainInitial = tab.title?.charAt(0)?.toUpperCase() || '?';
        }

        return `
            <div class="tab-grid-card ${isActive ? 'active' : ''}"
                 onclick="onGridCardClick('${tab.id}')"
                 oncontextmenu="event.preventDefault(); event.stopPropagation(); showTabContextMenu(event, '${tab.id}')"
                 data-tab-id="${tab.id}">
                <div class="card-thumbnail">
                    ${data.thumbnail
                        ? `<img src="data:image/jpeg;base64,${data.thumbnail}" alt="">`
                        : `<div class="placeholder">${domainInitial}</div>`}
                    ${tabs.length > 1
                        ? `<button class="card-close" onclick="event.stopPropagation(); closeTabFromGrid('${tab.id}')" title="Close tab">×</button>`
                        : ''}
                </div>
                <div class="card-info">
                    <div class="card-title">${escapeHtml(tab.title || 'New Tab')}</div>
                    <div class="card-url">${escapeHtml(tab.url || '')}</div>
                </div>
                <div class="card-stats">
                    <span class="stat stat-a11y ${data.a11y_violations === 0 ? 'zero' : ''}" title="Accessibility issues">
                        ⚠ ${data.a11y_violations ?? '—'}
                    </span>
                    <span class="stat stat-errors ${data.console_errors === 0 ? 'zero' : ''}" title="Console errors">
                        ! ${data.console_errors ?? '—'}
                    </span>
                    <span class="stat stat-alt ${data.missing_alt === 0 ? 'zero' : ''}" title="Images missing alt text">
                        🖼 ${data.missing_alt ?? '—'}
                    </span>
                </div>
                <div class="card-command">
                    Last: ${data.last_command || '—'}
                </div>
            </div>
        `;
    }).join('');
}

function onGridCardClick(tabId) {
    closeTabGrid();
    activateTab(tabId);
}

async function closeTabFromGrid(tabId) {
    await closeTab(tabId);
    // Update tab count
    document.getElementById('gridTabCount').textContent = `${tabs.length} tab${tabs.length !== 1 ? 's' : ''}`;
    // Re-render grid without the closed tab
    delete gridState.scanData[tabId];
    renderTabGrid();
}

// Auto-scan toggle
async function toggleAutoScan(enabled) {
    autoScanEnabled = enabled;
    const toggle = document.querySelector('.toolbar-auto-scan');
    if (toggle) {
        toggle.classList.toggle('active', enabled);
    }

    // Persist to server
    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/settings/auto-scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        console.log('[Auto-scan]', enabled ? 'Enabled' : 'Disabled');
    } catch (e) {
        console.error('[Auto-scan] Failed to save setting:', e);
    }
}

// Auto-scan interval - check every second if we should scan the current tab
setInterval(async () => {
    if (!autoScanEnabled || !activeTabId) return;

    const visit = tabVisitTimes[activeTabId];
    if (visit && !visit.scanned && Date.now() - visit.startTime >= AUTO_SCAN_THRESHOLD) {
        visit.scanned = true;
        try {
            await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${activeTabId}/scan`);
            console.log('[Auto-scan] Scanned tab:', activeTabId);
        } catch (e) {
            console.warn('[Auto-scan] Failed to scan tab:', e);
        }
    }
}, 1000);

// Helper function to escape HTML
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Fetch tabs from server
async function fetchTabs() {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs`);
        const data = await response.json();
        if (data.ok) {
            const serverTabs = data.tabs;

            // Preserve local tab order, but update tab data (title, url, favicon)
            // and handle new/closed tabs
            const serverTabIds = new Set(serverTabs.map(t => t.id));
            const localTabIds = new Set(tabs.map(t => t.id));

            // Preserve local tabs (client-only, not on server)
            const preservedLocalTabs = tabs.filter(t => localTabs[t.id]);

            // Remove tabs that no longer exist on server (excluding local tabs)
            tabs = tabs.filter(t => serverTabIds.has(t.id) || localTabs[t.id]);

            // Update existing tabs with fresh data from server (preserve local-only properties)
            tabs = tabs.map(localTab => {
                const serverTab = serverTabs.find(t => t.id === localTab.id);
                if (serverTab) {
                    serverTab.pinned = localTab.pinned || false;
                    serverTab.keepAlive = localTab.keepAlive || false;
                    return serverTab;
                }
                return localTab;
            });

            // Add new tabs from server (tabs we don't have locally)
            const pinnedUrls = getPinnedUrls();
            const keepAliveUrls = getKeepAliveUrls();
            serverTabs.forEach(serverTab => {
                if (!localTabIds.has(serverTab.id)) {
                    // Restore pinned/keepAlive state from localStorage
                    serverTab.pinned = pinnedUrls.includes(serverTab.url);
                    serverTab.keepAlive = keepAliveUrls.includes(serverTab.url);
                    tabs.push(serverTab);
                }
            });

            // Invalidate thumbnail cache for tabs whose URL changed
            tabs.forEach(tab => {
                if (lastKnownUrls[tab.id] && lastKnownUrls[tab.id] !== tab.url) {
                    delete thumbnailCache[tab.id];
                }
                lastKnownUrls[tab.id] = tab.url;
            });

            renderTabs();
            fetchThemeColors(); // async, non-blocking

            // Update URL bar if we have an active tab
            const activeTab = tabs.find(t => t.id === activeTabId) || tabs[0];
            if (activeTab) {
                // If this is a new active tab, track activation time
                if (activeTabId !== activeTab.id) {
                    onTabActivated(activeTab.id);
                }
                activeTabId = activeTab.id;
                // Initialize activation time if not set
                if (!tabActivationTimes[activeTabId]) {
                    onTabActivated(activeTabId);
                }
                // Don't overwrite URL bar when viewing an internal or local page —
                // Chrome's URL may differ from the native iframe's URL.
                if (!internalTabs[activeTabId] && !localTabs[activeTabId]) {
                    const urlBar = document.getElementById('urlBar');
                    if (document.activeElement !== urlBar) {
                        const urlChanged = activeTab.url !== currentUrl;
                        currentUrl = activeTab.url;
                        urlBar.value = displayUrl(currentUrl, false);
                        if (urlChanged) {
                            updateTerminalPrompt(currentUrl);
                            maybeFetchSitemap(currentUrl);
                            refreshSitemapNav(currentUrl);
                        }
                    }

                    // Detect internal URLs on tab sync (including startup).
                    // Also picks up the pending state from checkInitialInternalUrl().
                    if (isInternalUrl(activeTab.url)) {
                        internalTabs[activeTabId] = activeTab.url;
                        showNativeView(resolveInternalUrl(activeTab.url));
                        updateCloudIconState(activeTab.url);
                    }
                }
                if (_pendingInternalUrl) {
                    _pendingInternalUrl = null;
                }
            }
            // Update back/forward button state
            fetchHistoryState();

            // Handle ?focus= param from tab tear-off (activate the target tab)
            _handleFocusParam();
        }
    } catch (e) {
        console.error('[Tabs] Failed to fetch tabs:', e);
    }
}

// Handle ?focus=<tabId> query parameter (used by tab tear-off).
// On first tab fetch, activate the specified tab and filter the tab bar
// to only show that one tab.
let _focusTabHandled = false;
let _singleTabId = null; // When set, only this tab is shown in the tab bar

function _handleFocusParam() {
    if (_focusTabHandled) return;
    const params = new URLSearchParams(window.location.search);
    const focusId = params.get('focus');
    if (!focusId) { _focusTabHandled = true; return; }
    const tab = tabs.find(t => t.id === focusId);
    if (tab) {
        _focusTabHandled = true;
        _singleTabId = focusId;
        activateTab(focusId);
        renderTabs(); // Re-render to apply single-tab filter
        // Clean up the URL so it doesn't re-trigger on reload
        const cleanUrl = window.location.pathname;
        window.history.replaceState(null, '', cleanUrl);
    }
}

// Tab theme colors cache: {tabId: colorString}
const tabThemeColors = {};
let themeColorFetchPending = false;

async function fetchThemeColors() {
    if (themeColorFetchPending) return;
    themeColorFetchPending = true;
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/theme-colors`, {
            signal: AbortSignal.timeout(3000)
        });
        const data = await resp.json();
        if (data.ok && data.colors) {
            // Update cache and apply to DOM
            let changed = false;
            for (const [tabId, color] of Object.entries(data.colors)) {
                if (tabThemeColors[tabId] !== color) {
                    tabThemeColors[tabId] = color;
                    changed = true;
                }
            }
            // Remove stale entries
            for (const tabId of Object.keys(tabThemeColors)) {
                if (!(tabId in data.colors)) {
                    delete tabThemeColors[tabId];
                    changed = true;
                }
            }
            if (changed) applyThemeColors();
        }
    } catch (e) {
        // Silent fail — theme colors are cosmetic
    } finally {
        themeColorFetchPending = false;
    }
}

function applyThemeColors() {
    document.querySelectorAll('.tab').forEach(tabEl => {
        const tabId = tabEl.dataset.tabId;
        const color = tabThemeColors[tabId];
        if (color) {
            // Parse the color and apply as a translucent tint
            tabEl.style.setProperty('--tab-theme-color', color);
            tabEl.classList.add('has-theme-color');
        } else {
            tabEl.style.removeProperty('--tab-theme-color');
            tabEl.classList.remove('has-theme-color');
        }
    });

    // Match VNC background to active tab's page color so resize
    // gaps blend with the page instead of showing black.
    // Must set rfb.background (the .noVNC_screen div) — that's the
    // element behind the canvas where the black gaps actually appear.
    const activeColor = activeTabId ? tabThemeColors[activeTabId] : null;
    if (rfb) {
        rfb.background = activeColor || '';
    }
    const vncEl = document.getElementById('vncContainer');
    if (vncEl) {
        vncEl.style.backgroundColor = activeColor || '';
    }
}

// Render tabs in the tab bar (smart update to avoid flicker)
function renderTabs() {
    // Sort: pinned tabs first, then unpinned (stable sort preserves relative order)
    tabs.sort((a, b) => (a.pinned ? 0 : 1) - (b.pinned ? 0 : 1));

    // In single-tab mode (tear-off window), only show the focused tab
    const visibleTabs = _singleTabId ? tabs.filter(t => t.id === _singleTabId) : tabs;

    // Persist tab session to localStorage (debounced to avoid thrashing on rapid updates)
    _scheduleSaveTabSession();

    const container = document.getElementById('tabsContainer');
    const newTabBtn = container.querySelector('.new-tab-btn');
    const existingTabEls = container.querySelectorAll('.tab');
    const existingTabMap = new Map();

    // Build map of existing tab elements
    existingTabEls.forEach(el => {
        existingTabMap.set(el.dataset.tabId, el);
    });

    // Track which tabs we've processed
    const processedIds = new Set();

    // Get only .tab children (exclude the new-tab button) for index calculations
    const tabChildren = () => Array.from(container.querySelectorAll('.tab'));

    visibleTabs.forEach((tab, index) => {
        processedIds.add(tab.id);
        let tabEl = existingTabMap.get(tab.id);

        if (tabEl) {
            // Update existing tab element (no DOM recreation = no flicker)
            const wasLoading = tabEl.classList.contains('loading');
            tabEl.className = 'tab' + (tab.id === activeTabId ? ' active' : '') + (wasLoading ? ' loading' : '') + (tab.pinned ? ' tab-pinned' : '') + (tab.keepAlive ? ' tab-keepalive' : '') + (localTabs[tab.id] ? ' tab-local' : '');
            tabEl.dataset.index = index;

            // Update title
            const titleEl = tabEl.querySelector('.tab-title');
            if (titleEl) {
                titleEl.textContent = tab.title || 'New Tab';
                titleEl.title = tab.title || 'New Tab';
            }

            // Update close button visibility
            let closeBtn = tabEl.querySelector('.tab-close');
            if (tabs.length > 1 && !closeBtn) {
                closeBtn = document.createElement('button');
                closeBtn.className = 'tab-close';
                closeBtn.innerHTML = '<svg width="8" height="8" viewBox="0 0 8 8"><path d="M1 1l6 6M7 1l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
                closeBtn.title = 'Close tab';
                closeBtn.onclick = (e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                };
                tabEl.appendChild(closeBtn);
            } else if (tabs.length <= 1 && closeBtn) {
                closeBtn.remove();
            }

            // Move to correct position if needed
            const currentTabs = tabChildren();
            const currentIndex = currentTabs.indexOf(tabEl);
            if (currentIndex !== index) {
                if (index === 0) {
                    container.prepend(tabEl);
                } else {
                    const currentTabs2 = tabChildren();
                    const prevTab = currentTabs2[index - 1];
                    if (prevTab) {
                        prevTab.after(tabEl);
                    }
                }
            }
        } else {
            // Create new tab element — insert before the "+" button
            tabEl = createTabElement(tab, index);
            if (index === 0) {
                container.prepend(tabEl);
            } else {
                const currentTabs = tabChildren();
                const prevTab = currentTabs[index - 1];
                if (prevTab) {
                    prevTab.after(tabEl);
                } else {
                    container.insertBefore(tabEl, newTabBtn);
                }
            }
        }
    });

    // Remove tabs that no longer exist
    existingTabMap.forEach((el, id) => {
        if (!processedIds.has(id)) {
            el.remove();
        }
    });

    // Insert/remove separator between pinned and unpinned tabs
    const oldSep = container.querySelector('.tab-pin-separator');
    if (oldSep) oldSep.remove();
    const pinnedCount = tabs.filter(t => t.pinned).length;
    if (pinnedCount > 0 && pinnedCount < tabs.length) {
        const sep = document.createElement('div');
        sep.className = 'tab-pin-separator';
        const pinnedTabEls = container.querySelectorAll('.tab.tab-pinned');
        const lastPinned = pinnedTabEls[pinnedTabEls.length - 1];
        if (lastPinned) lastPinned.after(sep);
    }

    // Scroll active tab into view (e.g. when many tabs overflow)
    const activeEl = container.querySelector('.tab.active');
    if (activeEl) {
        activeEl.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
    }
}

// Create a new tab element
function createTabElement(tab, index) {
    const tabEl = document.createElement('div');
    tabEl.className = 'tab' + (tab.id === activeTabId ? ' active' : '') + (tab.pinned ? ' tab-pinned' : '') + (tab.keepAlive ? ' tab-keepalive' : '') + (localTabs[tab.id] ? ' tab-local' : '');
    tabEl.draggable = true;
    tabEl.dataset.tabId = tab.id;
    tabEl.dataset.index = index;

    // Favicon
    if (tab.favicon) {
        const favicon = document.createElement('img');
        favicon.className = 'tab-favicon';
        favicon.src = tab.favicon;
        favicon.onerror = () => {
            favicon.style.display = 'none';
            const placeholder = document.createElement('div');
            placeholder.className = 'tab-favicon-placeholder';
            placeholder.textContent = '🌐';
            tabEl.insertBefore(placeholder, tabEl.firstChild);
        };
        tabEl.appendChild(favicon);
    } else {
        const placeholder = document.createElement('div');
        placeholder.className = 'tab-favicon-placeholder';
        placeholder.textContent = '🌐';
        if (localTabs[tab.id]) {
            placeholder.textContent = '';
            placeholder.innerHTML = '<svg width="12" height="12" viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="9" rx="1.5" stroke="currentColor" stroke-width="1.5" fill="none"/><line x1="5" y1="14" x2="11" y2="14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
        }
        tabEl.appendChild(placeholder);
    }

    // Loading spinner (hidden by default, shown via .tab.loading CSS)
    const spinner = document.createElement('div');
    spinner.className = 'tab-favicon-spinner';
    tabEl.appendChild(spinner);

    // Title
    const title = document.createElement('span');
    title.className = 'tab-title';
    title.textContent = tab.title || 'New Tab';
    title.title = tab.title || 'New Tab';
    tabEl.appendChild(title);

    // Close button (only show if more than 1 tab)
    if (tabs.length > 1) {
        const closeBtn = document.createElement('button');
        closeBtn.className = 'tab-close';
        closeBtn.innerHTML = '<svg width="8" height="8" viewBox="0 0 8 8"><path d="M1 1l6 6M7 1l-6 6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
        closeBtn.title = 'Close tab';
        closeBtn.onclick = (e) => {
            e.stopPropagation();
            closeTab(tab.id);
        };
        tabEl.appendChild(closeBtn);
    }

    // Click to activate
    tabEl.onclick = () => activateTab(tab.id);
    tabEl.oncontextmenu = (e) => showTabContextMenu(e, tab.id);
    tabEl.onmousedown = () => {
        clearTimeout(thumbnailHoverTimeout);
        hideThumbnailImmediately();
    };

    // Hover events for thumbnail preview
    tabEl.onmouseenter = () => {
        // Cancel any pending hide immediately
        clearTimeout(thumbnailHideTimeout);
        thumbnailHideTimeout = null;

        const preview = document.getElementById('thumbnailPreview');
        const isVisible = preview.classList.contains('visible') || preview.classList.contains('moving');

        if (isVisible && currentThumbnailTabId !== tab.id) {
            // Thumbnail already showing for different tab - transition immediately
            clearTimeout(thumbnailHoverTimeout);
            showThumbnail(tab.id, tabEl);
        } else if (!isVisible) {
            // Not visible - use normal delay
            clearTimeout(thumbnailHoverTimeout);
            thumbnailHoverTimeout = setTimeout(() => {
                showThumbnail(tab.id, tabEl);
            }, THUMBNAIL_HOVER_DELAY);
        }
    };
    tabEl.onmouseleave = () => {
        clearTimeout(thumbnailHoverTimeout);
        hideThumbnail();
    };

    // Drag events
    tabEl.ondragstart = handleDragStart;
    tabEl.ondragover = handleDragOver;
    tabEl.ondragenter = handleDragEnter;
    tabEl.ondragleave = handleDragLeave;
    tabEl.ondrop = handleDrop;
    tabEl.ondragend = handleDragEnd;

    return tabEl;
}

// Show dropdown menu next to the "+" button
function showNewTabMenu(e) {
    e.stopPropagation();
    // Position the menu below the dropdown arrow button
    const rect = e.currentTarget.getBoundingClientRect();
    showContextMenu({ clientX: rect.left, clientY: rect.bottom + 4 }, [
        { label: 'New Cloud Tab', action: () => createNewTab() },
        { label: 'New Local Tab', action: () => createLocalTab() },
        { separator: true },
        { label: 'Paste and Open URLs', action: () => openUrlsFromClipboard() },
    ]);
}

// Create a new cloud tab
async function createNewTab() {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=http://inspekt/status`);
        const data = await response.json();
        if (data.ok) {
            activeTabId = data.tab.id;
            await fetchTabs();
            showToast('New tab created', 'success');
            // Focus address bar and select text for immediate typing
            const urlBar = document.getElementById('urlBar');
            urlBar.focus();
            urlBar.select();
        } else {
            showToast(data.error || 'Failed to create tab', 'error');
        }
    } catch (e) {
        showToast('Failed to create tab', 'error');
    }
}

// Create a new local tab (iframe loaded from host network)
function createLocalTab() {
    activeTabId = _addLocalTab('about:blank');
    renderTabs();
    syncViewport();
    showToast('Local tab — type a URL to load', 'info');

    // Focus address bar for immediate URL entry
    const urlBar = document.getElementById('urlBar');
    urlBar.value = '';
    urlBar.focus();
    urlBar.select();
}

// Open URLs from clipboard as cloud tabs
async function openUrlsFromClipboard() {
    try {
        const text = await readClipboard();
        const urlRegex = /https?:\/\/[^\s<>"')\]]+/gi;
        const matches = text.match(urlRegex);
        if (!matches || matches.length === 0) {
            showToast('No URLs found in clipboard', 'warning');
            return;
        }

        // Deduplicate and validate
        const unique = [...new Set(matches)].filter(u => {
            try { new URL(u); return true; } catch { return false; }
        });

        if (unique.length === 0) {
            showToast('No valid URLs found in clipboard', 'warning');
            return;
        }

        const urls = unique.slice(0, 15);
        const truncated = unique.length > 15 ? ` (capped at 15 of ${unique.length})` : '';
        showToast(`Opening ${urls.length} tab${urls.length > 1 ? 's' : ''}${truncated}...`, 'success');

        for (const url of urls) {
            try {
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=${encodeURIComponent(url)}`);
            } catch {
                // Silently skip failed tabs
            }
        }

        await fetchTabs();
    } catch (e) {
        if (e.name === 'NotAllowedError') {
            showToast('Clipboard access denied — click the page first', 'warning');
        } else {
            showToast('Failed to read clipboard', 'error');
        }
    }
}

// Activate (switch to) a tab
async function activateTab(tabId) {
    if (tabId === activeTabId) return;

    // Save inspect state for the tab we're leaving
    if (activeTabId) {
        _tabInspectState[activeTabId] = { wasTracking: _inspectTrackingActive };
        if (_inspectTrackingActive) {
            _stopInspectTracking();
            vncOverlay.dismiss('inspect-highlight', false);
            vncOverlay.dismiss('inspect-tooltip', false);
        }
    }

    // Capture thumbnail of current tab before switching (if user spent enough time)
    if (activeTabId && shouldCaptureThumbnail(activeTabId)) {
        // Fire and forget - don't wait for screenshot
        captureTabThumbnail(activeTabId);
    }

    // If switching to a local tab, skip CDP activation — just swap viewport
    if (localTabs[tabId]) {
        activeTabId = tabId;
        onTabActivated(tabId);
        renderTabs();
        currentUrl = localTabs[tabId].url;
        document.getElementById('urlBar').value = currentUrl;
        updateCloudIconState(currentUrl);
        maybeFetchSitemap(currentUrl);
        refreshSitemapNav(currentUrl);
        syncViewport();
        return;
    }

    // If switching to an internal tab, skip CDP activation — just swap viewport
    if (internalTabs[tabId]) {
        activeTabId = tabId;
        onTabActivated(tabId);
        renderTabs();
        currentUrl = internalTabs[tabId];
        document.getElementById('urlBar').value = currentUrl;
        updateCloudIconState(currentUrl);
        fetchHistoryState();
        syncViewport();
        return;
    }

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tabId}/activate`);
        const data = await response.json();
        if (data.ok) {
            activeTabId = tabId;
            onTabActivated(tabId);  // Track when this tab became active
            renderTabs();
            applyThemeColors();
            // Fetch the actual URL from Chrome (not from stale tabs array)
            try {
                const urlResp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/url?tab=${tabId}`);
                const urlData = await urlResp.json();
                if (urlData.ok && urlData.url) {
                    currentUrl = urlData.url;
                    document.getElementById('urlBar').value = displayUrl(currentUrl, false);
                    updateCloudIconState(currentUrl);
                    updateTerminalPrompt(currentUrl);
                }
            } catch (e) {
                // Fallback to tabs array if URL fetch fails
                const tab = tabs.find(t => t.id === tabId);
                if (tab) {
                    currentUrl = tab.url;
                    document.getElementById('urlBar').value = displayUrl(currentUrl, false);
                    updateCloudIconState(currentUrl);
                    updateTerminalPrompt(currentUrl);
                }
            }
            // Refresh sitemap nav for the newly active tab
            maybeFetchSitemap(currentUrl);
            refreshSitemapNav(currentUrl);
            fetchHistoryState();  // Refresh back/forward buttons for this tab

            // Switching to a normal tab — ensure VNC is visible
            syncViewport();

            // Restore inspect state for the tab we're switching to
            const saved = _tabInspectState[tabId];
            if (saved?.wasTracking) {
                try {
                    const resp = await fetch(
                        `http://${VNC_HOST}:${CONTROL_PORT}/inspect/get-rect?tab=${tabId}`,
                        { signal: AbortSignal.timeout(500) }
                    );
                    const rectData = await resp.json();
                    if (rectData.ok && rectData.rect) {
                        showInspectOverlay(rectData.rect, rectData.selector);
                    }
                } catch {}
            }
        } else {
            showToast(data.error || 'Failed to switch tab', 'error');
        }
    } catch (e) {
        showToast('Failed to switch tab', 'error');
    }
}

// Close a tab
async function closeTab(tabId, skipPinProtection) {
    const tab = tabs.find(t => t.id === tabId);

    // Keep Alive protection: tab cannot be closed until released
    if (tab && tab.keepAlive) {
        showToast('This tab is kept alive — release it first', 'warning');
        return;
    }

    // Pinned tab protection: show undo toast instead of closing immediately
    if (tab && tab.pinned && !skipPinProtection) {
        const pinnedUrl = tab.url;
        const pinnedTitle = tab.title;
        let undone = false;

        // Proceed with actual close, but offer undo
        await _doCloseTab(tabId);

        showToast('Pinned tab closed', {
            type: 'warning',
            duration: 5000,
            action: {
                label: 'Undo',
                onClick: async () => {
                    if (undone) return;
                    undone = true;
                    try {
                        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=${encodeURIComponent(pinnedUrl)}`);
                        const data = await resp.json();
                        if (data.ok) {
                            // Mark the new tab as pinned
                            const newTabId = data.tab?.id;
                            if (newTabId) {
                                await fetchTabs();
                                const newTab = tabs.find(t => t.id === newTabId);
                                if (newTab) {
                                    newTab.pinned = true;
                                    savePinnedUrls();
                                    renderTabs();
                                }
                            }
                            showToast('Pinned tab restored', 'success');
                        }
                    } catch (e) {
                        showToast('Failed to restore tab', 'error');
                    }
                }
            }
        });
        return;
    }

    await _doCloseTab(tabId);
}

async function _doCloseTab(tabId) {
    // Save to closed tabs stack before removing
    const closingTab = tabs.find(t => t.id === tabId);
    if (closingTab) {
        const isLocal = !!localTabs[tabId];
        const url = isLocal ? localTabs[tabId].url : closingTab.url;
        if (url && url !== 'about:blank') {
            closedTabs.push({
                url,
                title: closingTab.title || url,
                isLocal,
                closedAt: Date.now(),
            });
            if (closedTabs.length > MAX_CLOSED_TABS) closedTabs.shift();
        }
    }

    delete thumbnailCache[tabId];
    delete lastKnownUrls[tabId];
    delete tabNavHistory[tabId];
    delete _tabInspectState[tabId];
    delete internalTabs[tabId];

    const isLocal = !!localTabs[tabId];
    delete localTabs[tabId];

    if (isLocal) {
        // Local tab — no server-side tab to close
        tabs = tabs.filter(t => t.id !== tabId);
        if (tabId === activeTabId) {
            const next = tabs[0];
            if (next) {
                activeTabId = next.id;
                await activateTab(activeTabId);
            }
        }
        renderTabs();
        return;
    }

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tabId}/close`);
        const data = await response.json();
        if (data.ok) {
            // If we closed the active tab, switch to another
            if (tabId === activeTabId) {
                const remainingTabs = tabs.filter(t => t.id !== tabId);
                if (remainingTabs.length > 0) {
                    activeTabId = remainingTabs[0].id;
                    await activateTab(activeTabId);
                }
            }
            await fetchTabs();
        } else {
            showToast(data.error || 'Failed to close tab', 'error');
        }
    } catch (e) {
        showToast('Failed to close tab', 'error');
    }
}

// See vnc-overlay.js

// See context-menu.js

/** Move a tab one position to the left or right */
function moveTab(tabId, direction) {
    const idx = tabs.findIndex(t => t.id === tabId);
    if (idx < 0) return;
    const targetIdx = idx + direction;
    if (targetIdx < 0 || targetIdx >= tabs.length) return;
    const [moved] = tabs.splice(idx, 1);
    tabs.splice(targetIdx, 0, moved);
    savePinnedUrls();
    renderTabs();
}

/** Keep Alive state: URLs that cannot be closed */
function getKeepAliveUrls() {
    try { return JSON.parse(localStorage.getItem('inspekt_keepalive_tabs')) || []; }
    catch { return []; }
}

function saveKeepAliveUrls() {
    const urls = tabs.filter(t => t.keepAlive).map(t => t.url);
    localStorage.setItem('inspekt_keepalive_tabs', JSON.stringify(urls));
}

async function toggleKeepAlive(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    if (!tab) return;
    tab.keepAlive = !tab.keepAlive;
    saveKeepAliveUrls();
    renderTabs();

    // For cloud tabs: instruct Chromium to prevent freezing/discarding via CDP
    if (!localTabs[tabId]) {
        try {
            await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${tabId}/keep-alive?enabled=${tab.keepAlive}`);
        } catch {}
    }

    showToast(tab.keepAlive ? 'Tab kept alive — won\'t freeze or close' : 'Tab released', 'success');
}

function showTabContextMenu(e, tabId) {
    e.preventDefault();
    const tab = tabs.find(t => t.id === tabId);
    if (!tab) return;

    const tabIndex = tabs.findIndex(t => t.id === tabId);
    const isLocal = !!localTabs[tabId];
    const otherCount = tabs.length - 1;
    const tabsToLeft = tabs.slice(0, tabIndex).filter(t => !t.pinned).length;
    const tabsToRight = tabs.slice(tabIndex + 1).filter(t => !t.pinned).length;

    // ── Tab State ──
    const items = [
        { label: tab.pinned ? 'Unpin Tab' : 'Pin Tab', action: () => togglePinTab(tabId) },
        { label: tab.keepAlive ? 'Release Tab' : 'Keep Alive', action: () => toggleKeepAlive(tabId) },
        { separator: true },
    ];

    // ── Organization ──
    if (isLocal) {
        items.push({ label: 'Duplicate Tab', children: [
            { label: 'As Local Tab', action: () => duplicateTab(tabId) },
            { label: 'As Cloud Tab', action: () => duplicateAsCloudTab(tabId) },
        ]});
    } else {
        items.push({ label: 'Duplicate Tab', children: [
            { label: 'As Cloud Tab', action: () => duplicateTab(tabId) },
            { label: 'As Local Tab', action: () => duplicateAsLocalTab(tabId) },
        ]});
    }
    if (_hasTauriIPC()) {
        items.push({ label: 'Open in New Window', action: () => tearOffTab(tab) });
    }
    items.push(
        { label: 'Move Tab Left', action: () => moveTab(tabId, -1), disabled: tabIndex === 0 },
        { label: 'Move Tab Right', action: () => moveTab(tabId, 1), disabled: tabIndex === tabs.length - 1 },
        { separator: true },
    );

    // ── Reload ──
    if (isLocal) {
        const localUrl = localTabs[tabId].url;
        items.push({ label: 'Reload Page', action: () => {
            const iframe = document.querySelector('#nativeContainer iframe');
            if (iframe) { iframe.src = 'about:blank'; setTimeout(() => iframe.src = localUrl, 50); }
        }});
    } else {
        const opts = getReloadOptions(tab.url);
        const anyClearing = opts.clearCache || opts.clearCookies || opts.clearStorage;
        items.push(
            { label: anyClearing ? 'Reload Page ✦' : 'Reload Page', action: () => reloadWithOptions(tabId) },
            { checkbox: true, label: 'Clear Cache', checked: opts.clearCache,
              onToggle: (v) => setReloadOption(tab.url, 'clearCache', v) },
            { checkbox: true, label: 'Clear Cookies', checked: opts.clearCookies,
              onToggle: (v) => setReloadOption(tab.url, 'clearCookies', v) },
            { checkbox: true, label: 'Clear All Storage', checked: opts.clearStorage,
              onToggle: (v) => setReloadOption(tab.url, 'clearStorage', v) },
        );
    }
    items.push({ separator: true });

    // ── Links ──
    items.push(
        { label: 'Copy URL', action: () => copyTabUrl(tabId) },
        { label: 'Copy as Markdown Link', action: () => copyTabAsMarkdownLink(tabId) },
        { label: 'Open in Host Browser', action: () => isLocal ? window.open(localTabs[tabId].url, '_blank') : openInHostBrowser(tabId) },
    );
    if (!isLocal) {
        items.push({ label: 'Open Fullscreen', action: () => toggleFullscreen() });
    }
    items.push({ separator: true });

    // ── Close (destructive, always last) ──
    if (tabs.length > 1) {
        items.push({ label: 'Close Tab', action: () => closeTab(tabId), disabled: tab.keepAlive });
    }
    if (otherCount >= 1) {
        items.push({ label: otherCount === 1 ? 'Close Other Tab' : `Close ${otherCount} Other Tabs`, action: () => closeOtherTabs(tabId) });
    }
    if (tabsToLeft > 0) {
        items.push({ label: tabsToLeft === 1 ? 'Close Tab to the Left' : `Close ${tabsToLeft} Tabs to the Left`, action: () => closeTabsToLeft(tabId) });
    }
    if (tabsToRight > 0) {
        items.push({ label: tabsToRight === 1 ? 'Close Tab to the Right' : `Close ${tabsToRight} Tabs to the Right`, action: () => closeTabsToRight(tabId) });
    }

    showContextMenu(e, items);
}
