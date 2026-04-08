// =============================================
// VNC Viewport Context Menu
// =============================================

function canGoBack() {
    if (!activeTabId) return false;
    return getNavHistory(activeTabId).index > 0;
}

function canGoForward() {
    if (!activeTabId) return false;
    const h = getNavHistory(activeTabId);
    return h.index < h.entries.length - 1;
}

// ── Clipboard abstraction (Tauri plugin → navigator.clipboard → execCommand) ──
// In the Tauri desktop app, window.__TAURI__.clipboardManager provides native
// OS clipboard access that bypasses WKWebView's user-activation restrictions.
// In a regular browser, we fall back to navigator.clipboard, then execCommand.

const _hasTauriClipboard = !!(window.__TAURI__?.clipboardManager);

async function writeClipboard(text) {
    if (_hasTauriClipboard) {
        try {
            await window.__TAURI__.clipboardManager.writeText(text);
            return true;
        } catch (e) {
            console.warn('[Clipboard] Tauri writeText failed:', e);
        }
    }
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        return _writeClipboardFallback(text);
    }
}

async function readClipboard() {
    if (_hasTauriClipboard) {
        try {
            return await window.__TAURI__.clipboardManager.readText();
        } catch (e) {
            console.warn('[Clipboard] Tauri readText failed:', e);
        }
    }
    return navigator.clipboard.readText();
}

async function writeImageToClipboard(pngBlob) {
    if (_hasTauriClipboard && window.__TAURI__?.image?.Image) {
        try {
            const bytes = new Uint8Array(await pngBlob.arrayBuffer());
            const img = await window.__TAURI__.image.Image.fromBytes(bytes);
            await window.__TAURI__.clipboardManager.writeImage(img);
            return true;
        } catch (e) {
            console.warn('[Clipboard] Tauri writeImage failed:', e);
        }
    }
    // Browser fallback — may throw if user activation expired (caller handles)
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': pngBlob })]);
    return true;
}

// Last-resort fallback for browsers where navigator.clipboard also fails
function _writeClipboardFallback(text) {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.cssText = 'position:fixed;left:-9999px;top:-9999px;opacity:0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
}

function copyToClipboard(text) {
    writeClipboard(text).then((ok) => {
        showToast(ok ? 'Copied!' : 'Failed to copy', ok ? 'success' : 'error');
    });
}

async function showVNCContextMenu(pageX, pageY, vmX, vmY) {
    // Debug: show dummy test menu with submenus for development
    if (_DEBUG_DUMMY_MENU) return _showDummyTestMenu(pageX, pageY);

    // --- Real VNC context menu ---
    // Clear any previous host-side overlays when opening a new context menu
    if (activeTabId) _tabInspectState[activeTabId] = { wasTracking: false };
    _stopInspectTracking();
    vncOverlay.dismissAll();

    let info = { selectedText: '', isImage: false, imageSrc: '', isLink: false, linkHref: '', elementTag: '', elementSelector: '' };
    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 2000);
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/context-menu-info?x=${vmX}&y=${vmY}`,
            { signal: controller.signal }
        );
        clearTimeout(timeout);
        const data = await resp.json();
        if (data.ok) info = data;
    } catch (e) {}
    const items = buildVNCContextMenuItems({
        info,
        canGoBack: canGoBack(),
        canGoForward: canGoForward(),
        sitemapReady: _sitemapReady,
        sitemapNav: _sitemapNav,
        lastScreenshotRegion: _lastScreenshotRegion,
        currentUrl,
        isTerminalOpen,
        vmX,
        vmY,
    });
    showContextMenu({ clientX: pageX, clientY: pageY }, items);
}

// Dummy test menu with submenus, headers, disabled items, and enough items to test scrolling.
// Activated by setting _DEBUG_DUMMY_MENU = true above.
function _showDummyTestMenu(pageX, pageY) {
    const t = (msg) => () => showToast(msg, 'success');
    showContextMenu({ clientX: pageX, clientY: pageY }, [
        { header: 'File' },
        { label: 'New File', action: t('New File') },
        { label: 'New from Template', children: [
            { header: 'Documents' },
            { label: 'Blank Document', action: t('Blank Document') },
            { label: 'Letter', action: t('Letter') },
            { label: 'Resume', action: t('Resume') },
            { label: 'Report', action: t('Report') },
            { separator: true },
            { header: 'Spreadsheets' },
            { label: 'Budget', action: t('Budget') },
            { label: 'Invoice', action: t('Invoice') },
            { label: 'Timesheet', action: t('Timesheet') },
            { separator: true },
            { header: 'Presentations' },
            { label: 'Pitch Deck', action: t('Pitch Deck') },
            { label: 'Keynote', action: t('Keynote') },
            { label: 'Workshop', action: t('Workshop') },
        ]},
        { label: 'Open Recent', children: [
            { label: 'quarterly-report.pdf', action: t('quarterly-report.pdf') },
            { label: 'team-photo.png', action: t('team-photo.png') },
            { label: 'meeting-notes.md', action: t('meeting-notes.md') },
            { label: 'budget-2026.xlsx', action: t('budget-2026.xlsx') },
            { label: 'presentation-v3.key', action: t('presentation-v3.key') },
            { separator: true },
            { label: 'Older Files', children: [
                { label: 'archive-jan.zip', action: t('archive-jan.zip') },
                { label: 'backup-feb.sql', action: t('backup-feb.sql') },
                { label: 'draft-proposal.docx', action: t('draft-proposal.docx') },
                { label: 'client-feedback.pdf', action: t('client-feedback.pdf') },
                { label: 'wireframes-v1.fig', action: t('wireframes-v1.fig') },
                { label: 'design-system.sketch', action: t('design-system.sketch') },
                { label: 'api-docs.yaml', action: t('api-docs.yaml') },
                { label: 'test-results.xml', action: t('test-results.xml') },
                { label: 'deployment-log.txt', action: t('deployment-log.txt') },
                { label: 'sprint-retro.md', action: t('sprint-retro.md') },
                { separator: true },
                { label: 'Even Older', children: [
                    { label: 'This submenu should not open (max depth reached)', action: t('nope') },
                ]},
            ]},
            { separator: true },
            { label: 'Clear Recent', action: t('Cleared') },
        ]},
        { separator: true },
        { label: 'Save', action: t('Saved') },
        { label: 'Save As…', action: t('Save As') },
        { label: 'Export As', children: [
            { header: 'Images' },
            { label: 'PNG (Lossless)', action: t('PNG') },
            { label: 'JPEG (High Quality)', action: t('JPEG HQ') },
            { label: 'JPEG (Low Quality)', action: t('JPEG LQ') },
            { label: 'WebP (Compressed)', action: t('WebP') },
            { label: 'AVIF (Modern)', action: t('AVIF') },
            { label: 'TIFF (Uncompressed)', action: t('TIFF') },
            { label: 'BMP (Legacy)', action: t('BMP') },
            { separator: true },
            { header: 'Vector' },
            { label: 'SVG', action: t('SVG') },
            { label: 'PDF', action: t('PDF') },
            { label: 'EPS (Legacy)', action: t('EPS') },
            { separator: true },
            { header: 'Data' },
            { label: 'JSON', action: t('JSON') },
            { label: 'CSV', action: t('CSV') },
            { label: 'XML', action: t('XML') },
            { label: 'YAML', action: t('YAML') },
        ]},
        { label: 'Import From', children: [{ label: 'No sources available' }], disabled: true },
        { separator: true },
        { header: 'Edit' },
        { label: 'Undo', action: t('Undo') },
        { label: 'Redo', action: t('Redo') },
        { separator: true },
        { label: 'Cut', action: t('Cut') },
        { label: 'Copy', action: t('Copy') },
        { label: 'Paste', action: t('Paste') },
        { label: 'Paste Special', children: [
            { label: 'Paste as Plain Text', action: t('Plain Text') },
            { label: 'Paste as HTML', action: t('HTML') },
            { label: 'Paste as Markdown', action: t('Markdown') },
            { label: 'Paste and Match Style', action: t('Match Style') },
            { separator: true },
            { label: 'Paste from Clipboard History', children: [
                { label: 'Clipboard item 1: "Hello world"', action: t('Clip 1') },
                { label: 'Clipboard item 2: "const x = 42;"', action: t('Clip 2') },
                { label: 'Clipboard item 3: "https://example.com"', action: t('Clip 3') },
            ]},
        ]},
        { label: 'Select All', action: t('Select All') },
        { label: 'Find and Replace…', action: t('Find and Replace') },
        { separator: true },
        { header: 'View' },
        { label: 'Zoom In', action: t('Zoom In') },
        { label: 'Zoom Out', action: t('Zoom Out') },
        { label: 'Reset Zoom', action: t('Reset Zoom') },
        { label: 'Toggle Fullscreen', action: t('Fullscreen') },
        { separator: true },
        { label: 'Preferences', action: t('Preferences') },
        { label: 'About', action: t('About') },
        { label: 'Close', action: t('Close') },
    ]);
}


function togglePinTab(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    if (tab) {
        tab.pinned = !tab.pinned;
        savePinnedUrls();
        renderTabs();
        showToast(tab.pinned ? 'Tab pinned' : 'Tab unpinned', 'success');
    }
}

async function refreshTab(tabId) {
    if (tabId !== activeTabId) {
        await activateTab(tabId);
    }
    await reloadPage();
}

async function reloadWithOptions(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    if (!tab) return;
    if (tabId !== activeTabId) {
        await activateTab(tabId);
    }
    const opts = getReloadOptions(tab.url);
    const params = new URLSearchParams({ tab: activeTabId });
    if (opts.clearCache) params.append('clearCache', '1');
    if (opts.clearCookies) params.append('clearCookies', '1');
    if (opts.clearStorage) params.append('clearStorage', '1');

    // For internal pages, just reload the iframe
    if (activeTabId && internalTabs[activeTabId]) {
        const nativeIframe = document.querySelector('#nativeContainer iframe');
        if (nativeIframe) {
            nativeIframe.src = resolveInternalUrl(internalTabs[activeTabId]);
            showToast('Page reloaded', 'success');
        }
        return;
    }

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

async function duplicateTab(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    if (!tab) return;

    if (localTabs[tabId]) {
        duplicateAsLocalTab(tabId);
    } else if (tab.url) {
        try {
            const newTabId = await _addCloudTab(tab.url, tabId);
            if (newTabId) await activateTab(newTabId);
        } catch (err) {
            console.warn('[tabs] Failed to duplicate tab:', err);
        }
    }
}

function duplicateAsLocalTab(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    if (!tab) return;
    const url = localTabs[tabId] ? localTabs[tabId].url : tab.url;
    const title = localTabs[tabId] ? localTabs[tabId].title : null;
    const sourceIndex = tabs.findIndex(t => t.id === tabId);
    activeTabId = _addLocalTab(url, title, sourceIndex);
    renderTabs();
    syncViewport();
}

async function duplicateAsCloudTab(tabId) {
    const url = localTabs[tabId]?.url;
    if (!url || url === 'about:blank') return;
    try {
        const newTabId = await _addCloudTab(url, tabId);
        if (newTabId) await activateTab(newTabId);
    } catch (err) {
        console.warn('[tabs] Failed to duplicate as cloud tab:', err);
    }
}

async function openLinkInNewTab(url) {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/new?url=${encodeURIComponent(url)}`);
        const data = await response.json();
        if (data.ok) {
            // Refresh tabs first, then set activeTabId — prevents the
            // URL polling from reading a stale tabs array for the new tab
            await fetchTabs();
            activeTabId = data.tab.id;
            currentUrl = url;
            document.getElementById('urlBar').value = displayUrl(url, false);
            updateCloudIconState(url);
            renderTabs();
            maybeFetchSitemap(currentUrl);
            refreshSitemapNav(currentUrl);
        } else {
            showToast(data.error || 'Failed to open link', 'error');
        }
    } catch (e) {
        showToast('Failed to open link', 'error');
    }
}

function openInHostBrowser(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    if (!tab || !tab.url || tab.url === 'about:blank') return;
    window.open(tab.url, '_blank');
}

async function closeOtherTabs(tabId) {
    const othersToClose = tabs.filter(t => t.id !== tabId && !t.pinned && !t.keepAlive);
    const skippedPinned = tabs.filter(t => t.id !== tabId && (t.pinned || t.keepAlive)).length;
    for (const t of othersToClose) {
        await _doCloseTab(t.id);
    }
    if (skippedPinned > 0) {
        showToast(`Pinned tab${skippedPinned > 1 ? 's' : ''} kept open`, 'info');
    }
}

async function closeTabsToRight(tabId) {
    const tabIndex = tabs.findIndex(t => t.id === tabId);
    if (tabIndex < 0) return;
    const toClose = tabs.slice(tabIndex + 1).filter(t => !t.pinned && !t.keepAlive);
    const skippedPinned = tabs.slice(tabIndex + 1).filter(t => t.pinned || t.keepAlive).length;
    for (const t of toClose) {
        await _doCloseTab(t.id);
    }
    if (skippedPinned > 0) {
        showToast(`Pinned tab${skippedPinned > 1 ? 's' : ''} kept open`, 'info');
    }
}

async function closeTabsToLeft(tabId) {
    const tabIndex = tabs.findIndex(t => t.id === tabId);
    if (tabIndex <= 0) return;
    const toClose = tabs.slice(0, tabIndex).filter(t => !t.pinned && !t.keepAlive);
    const skippedPinned = tabs.slice(0, tabIndex).filter(t => t.pinned || t.keepAlive).length;
    for (const t of toClose) {
        await _doCloseTab(t.id);
    }
    if (skippedPinned > 0) {
        showToast(`Pinned tab${skippedPinned > 1 ? 's' : ''} kept open`, 'info');
    }
}

function copyTabUrl(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    const url = localTabs[tabId] ? localTabs[tabId].url : tab?.url;
    if (url) {
        writeClipboard(url);
        showToast('URL copied', 'success');
    }
}

function copyTabAsMarkdownLink(tabId) {
    const tab = tabs.find(t => t.id === tabId);
    const url = localTabs[tabId] ? localTabs[tabId].url : tab?.url;
    const title = tab?.title || url || 'Untitled';
    if (url) {
        writeClipboard(`[${title}](${url})`);
        showToast('Markdown link copied', 'success');
    }
}

// --- Tab bar context menu actions ---

async function reopenClosedTab() {
    const entry = closedTabs.pop();
    if (!entry) return;
    if (entry.isLocal) {
        activeTabId = _addLocalTab(entry.url, entry.title);
        renderTabs();
        syncViewport();
    } else {
        try {
            const newTabId = await _addCloudTab(entry.url);
            if (newTabId) await activateTab(newTabId);
        } catch {}
    }
}

async function reopenAllClosedTabs() {
    const toReopen = closedTabs.splice(0);
    for (const entry of toReopen) {
        if (entry.isLocal) {
            _addLocalTab(entry.url, entry.title);
        } else {
            try {
                await _addCloudTab(entry.url);
            } catch {}
        }
    }
    renderTabs();
    showToast(`Reopened ${toReopen.length} tab${toReopen.length > 1 ? 's' : ''}`, 'success');
}

async function reloadAllTabs() {
    let reloaded = 0;
    for (const tab of tabs) {
        if (localTabs[tab.id]) {
            // Local tab: reload the iframe (only if it's the active tab)
            if (tab.id === activeTabId) {
                const iframe = document.querySelector('#nativeContainer iframe');
                if (iframe) {
                    const url = localTabs[tab.id].url;
                    iframe.src = 'about:blank';
                    setTimeout(() => iframe.src = url, 50);
                }
            }
            reloaded++;
        } else if (internalTabs[tab.id]) {
            // Internal tab: reload the iframe (only if it's the active tab)
            if (tab.id === activeTabId) {
                const iframe = document.querySelector('#nativeContainer iframe');
                if (iframe) iframe.src = resolveInternalUrl(internalTabs[tab.id]);
            }
            reloaded++;
        } else {
            // Cloud tab: reload via server (activates tab first for CDP)
            try {
                const params = new URLSearchParams({ tab: tab.id });
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/reload-page?${params.toString()}`);
                reloaded++;
            } catch {}
        }
    }
    showToast(`Reloaded ${reloaded} tab${reloaded > 1 ? 's' : ''}`, 'success');
}

async function closeAllTabs() {
    const toClose = tabs.filter(t => !t.pinned && !t.keepAlive);
    const pinnedCount = tabs.filter(t => t.pinned || t.keepAlive).length;
    for (const t of toClose) {
        await _doCloseTab(t.id);
    }
    if (pinnedCount > 0) {
        showToast(`Pinned tab${pinnedCount > 1 ? 's' : ''} kept open`, 'info');
    }
    // If all tabs closed, create a new one
    if (tabs.length === 0) {
        await createNewTab();
    }
}

function copyAllUrls() {
    const urls = tabs.map(t => localTabs[t.id] ? localTabs[t.id].url : t.url).filter(Boolean);
    writeClipboard(urls.join('\n'));
    showToast(`${urls.length} URL${urls.length > 1 ? 's' : ''} copied`, 'success');
}

function copyAllUrlsAsMarkdown() {
    const links = tabs.map(t => {
        const url = localTabs[t.id] ? localTabs[t.id].url : t.url;
        const title = t.title || url || 'Untitled';
        return url ? `- [${title}](${url})` : null;
    }).filter(Boolean);
    writeClipboard(links.join('\n'));
    showToast(`${links.length} Markdown link${links.length > 1 ? 's' : ''} copied`, 'success');
}

function showTabBarContextMenu(e) {
    e.preventDefault();
    const items = buildTabBarContextMenuItems({ closedTabs, tabs });
    showContextMenu(e, items);
}

// Drag and drop handlers
function handleDragStart(e) {
    draggedTab = e.target;
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', e.target.dataset.tabId);
    // Hide thumbnail immediately during drag
    clearTimeout(thumbnailHoverTimeout);
    hideThumbnailImmediately();
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
}

function handleDragEnter(e) {
    e.preventDefault();
    const tab = e.target.closest('.tab');
    if (tab && tab !== draggedTab) {
        tab.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    const tab = e.target.closest('.tab');
    if (tab) {
        tab.classList.remove('drag-over');
    }
}

function handleDrop(e) {
    e.preventDefault();
    const targetTab = e.target.closest('.tab');
    if (targetTab && draggedTab && targetTab !== draggedTab) {
        const draggedId = draggedTab.dataset.tabId;
        const targetId = targetTab.dataset.tabId;
        const draggedTabObj = tabs.find(t => t.id === draggedId);
        const targetTabObj = tabs.find(t => t.id === targetId);

        if (!draggedTabObj || !targetTabObj) return;

        // Auto pin/unpin when dragging across the pinned/unpinned boundary
        if (targetTabObj.pinned && !draggedTabObj.pinned) {
            draggedTabObj.pinned = true;
            showToast('Tab pinned', 'success');
        } else if (!targetTabObj.pinned && draggedTabObj.pinned) {
            draggedTabObj.pinned = false;
            showToast('Tab unpinned', 'success');
        }

        const draggedIndex = tabs.findIndex(t => t.id === draggedId);
        const targetIndex = tabs.findIndex(t => t.id === targetId);

        // Reorder tabs array
        const [removed] = tabs.splice(draggedIndex, 1);
        tabs.splice(targetIndex, 0, removed);
        savePinnedUrls();
        renderTabs();
    }
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('drag-over'));
}

function handleDragEnd(e) {
    e.target.classList.remove('dragging');
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('drag-over'));
    draggedTab = null;
}

// Poll for tab updates every 2 seconds
setInterval(fetchTabs, 2000);

// Re-apply CDP keep-alive for persisted keep-alive tabs after initial load
setTimeout(() => {
    tabs.filter(t => t.keepAlive && !localTabs[t.id]).forEach(t => {
        fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs/${t.id}/keep-alive?enabled=true`).catch(() => {});
    });
}, 3000);

// Fetch initial plugin icon state (autorun indicator)
(async () => {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins`);
        const data = await resp.json();
        if (data.ok) {
            pluginsCache = data.plugins || [];
            updatePluginIconState();
        }
    } catch (e) { /* control server not ready yet */ }
})();

// Terminal visibility state polling (for recording workflow)
// When inspekt record starts, the CLI signals the control server to hide the terminal
// When recording stops, the CLI signals to show it again
let lastTerminalHiddenState = false;

async function checkTerminalState() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/ui/terminal-state`, {
            signal: AbortSignal.timeout(1000)
        });
        if (resp.ok) {
            const data = await resp.json();
            // Only act on state changes to avoid flickering
            if (data.hidden !== lastTerminalHiddenState) {
                lastTerminalHiddenState = data.hidden;
                if (data.hidden && isTerminalOpen) {
                    // Recording started - hide terminal so user can interact with browser
                    toggleTerminal();
                } else if (!data.hidden && !isTerminalOpen) {
                    // Recording stopped - show terminal again
                    toggleTerminal();
                }
            }
        }
    } catch (e) {
        // Ignore errors - terminal state is optional functionality
    }
}

// Poll terminal state every 1 second
setInterval(checkTerminalState, 1000);

// Check if running in dev mode and update title
async function checkDevMode() {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/dev-mode`);
        if (response.ok) {
            const data = await response.json();
            if (data.dev_mode) {
                document.title = '[DEV] ' + document.title;
                console.log('[Inspekt] Development mode active - source files mounted from host');
            }
        }
    } catch (e) {
        // Ignore errors - dev mode indicator is not critical
    }
}

// VNC canvas event interceptors — replaces the old postMessage bridge.
// With direct RFB embedding, we add capture-phase listeners on the
// VNC container to intercept events BEFORE RFB's canvas handlers.
let _canvasInterceptorsSetup = false;

function _setupCanvasEventInterceptors() {
    if (_canvasInterceptorsSetup) return;
    _canvasInterceptorsSetup = true;

    const container = document.getElementById('vncContainer');

    // Debounce guard: Safari may fire both mouse and pointer events for
    // the same right-click, which could double-trigger the context menu.
    let _lastContextMenuTime = 0;

    // Right-click: always intercept to show custom context menu
    container.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopImmediatePropagation();
        const now = Date.now();
        if (now - _lastContextMenuTime < 200) return;
        _lastContextMenuTime = now;
        if (isHoverInspectActive) deactivateHoverInspect();
        const vm = _clientToVm(e.clientX, e.clientY);
        showVNCContextMenu(e.clientX, e.clientY, vm.x, vm.y);
    }, true);

    // Block right-click pointer events from reaching RFB
    container.addEventListener('pointerdown', (e) => {
        if (e.button === 2) {
            e.preventDefault();
            e.stopImmediatePropagation();
            return;
        }
        // Hover-inspect: intercept left click to lock element
        if (isHoverInspectActive && e.button === 0) {
            e.preventDefault();
            e.stopImmediatePropagation();
            const vm = _clientToVm(e.clientX, e.clientY);
            _handleHoverLock(vm.x, vm.y);
            return;
        }
        // Normal left click: dismiss overlays
        if (e.button === 0) {
            if (_isMenuOpen()) dismissContextMenu();
            if (_inspectTrackingActive && activeTabId) {
                _tabInspectState[activeTabId] = { wasTracking: false };
            }
            _stopInspectTracking();
            vncOverlay.dismissAll(true);
        }
    }, true);

    container.addEventListener('pointerup', (e) => {
        if (e.button === 2) {
            e.preventDefault();
            e.stopImmediatePropagation();
        }
    }, true);

    // Safari fallback: Safari may not reliably fire pointerdown/pointerup
    // with button===2 on canvas elements. Mirror the pointer handlers with
    // mouse event equivalents so right-click interception works cross-browser.
    container.addEventListener('mousedown', (e) => {
        if (e.button === 2) {
            e.preventDefault();
            e.stopImmediatePropagation();
            return;
        }
        if (isHoverInspectActive && e.button === 0) {
            e.preventDefault();
            e.stopImmediatePropagation();
            const vm = _clientToVm(e.clientX, e.clientY);
            _handleHoverLock(vm.x, vm.y);
            return;
        }
        if (e.button === 0) {
            if (_isMenuOpen()) dismissContextMenu();
            if (_inspectTrackingActive && activeTabId) {
                _tabInspectState[activeTabId] = { wasTracking: false };
            }
            _stopInspectTracking();
            vncOverlay.dismissAll(true);
        }
    }, true);

    container.addEventListener('mouseup', (e) => {
        if (e.button === 2) {
            e.preventDefault();
            e.stopImmediatePropagation();
        }
    }, true);

    // Hover-inspect: track pointer moves for element highlighting.
    // Listen on the canvas directly — noVNC may use setPointerCapture
    // which redirects pointermove events to the canvas, bypassing
    // ancestor capture-phase listeners.
    function _attachHoverMoveListener() {
        const canvas = container.querySelector('canvas');
        if (!canvas) { setTimeout(_attachHoverMoveListener, 200); return; }
        canvas.addEventListener('pointermove', (e) => {
            // Always track mouse position — even when noVNC has pointer capture
            _trackMouse(e);
            if (isHoverInspectActive) {
                const vm = _clientToVm(e.clientX, e.clientY);
                _handleHoverMove(vm.x, vm.y);
            }
        }, true);
    }
    _attachHoverMoveListener();
}

// Note: Escape key dismissal for inspect overlay is handled in the
// unified keyboard shortcuts handler below (search "Keyboard shortcuts").

// Note: context menu prevention on VNC container is now handled by
// _setupCanvasEventInterceptors() capture-phase listener.

// Initialize
window.addEventListener('load', () => {
    updateSplashStatus('Loading...');
    initToolbar();
    initVisionSimulator();
    initMotorSimulator();
    setTimeout(connectVNC, 500);
    setInterval(checkHealth, 5000);

    // Connect terminal in background (so it's ready when user opens it)
    setTimeout(connectTerminal, 1000);

    // Check dev mode and update title
    setTimeout(checkDevMode, 1000);

    // Sync theme on initial load (with small delay to let VM start)
    setTimeout(() => syncColorScheme(getColorScheme()), 2000);

    // Restore local tabs and closed tabs from localStorage
    restoreTabSession();

    // Fetch tabs on load (with small delay to let Chrome start)
    // After first fetch, apply saved tab order
    setTimeout(async () => {
        await fetchTabs();
        applySavedTabOrder();
    }, 1500);

    // Seed URL history from Chrome's navigation history
    setTimeout(seedHistoryFromServer, 2000);
});

// ── Tauri native menu bridge ──────────────────────────────────────
// When running inside the Tauri desktop wrapper, native menu items
// dispatch CustomEvents via window.eval(). This listener routes
// each action to the corresponding control-panel function.
window.addEventListener('tauri-menu', (e) => {
    const { action, value } = e.detail || {};

    // Vision simulator ID mapping (Rust menu ID → JS simulation name)
    const VISION_MAP = {
        protanopia: 'protanopia',
        deuteranopia: 'deuteranopia',
        tritanopia: 'tritanopia',
        achromatopsia: 'achromatopsia',
        low_vision: 'low-vision-moderate',
        near_total: 'near-total-loss',
        light_only: 'light-perception',
        cataracts: 'cataracts',
        glaucoma: 'glaucoma',
        tunnel: 'tunnel-vision',
        scotoma: 'central-scotoma',
        hemianopia: 'hemianopia',
        keratoconus: 'keratoconus',
        corneal: 'corneal-scarring',
        floaters: 'diabetic-floaters',
        nystagmus: 'nystagmus',
        diplopia: 'diplopia',
        metamorphopsia: 'metamorphopsia',
        snow: 'visual-snow',
    };

    // Motor simulator ID mapping
    const MOTOR_MAP = {
        parkinsons: 'parkinsons',
        essential: 'essential-tremor',
        spasms: 'muscle-spasm',
        fine: 'limited-mobility',
    };

    switch (action) {
        // ── View toggles ─────────────────────────────────
        case 'terminal':         toggleTerminal(); break;
        case 'split_view':       toggleSplitMode(); break;
        case 'tab_overview':     toggleTabGrid(); break;
        case 'page_info':        togglePageInfo(); break;
        case 'element_inspector': toggleHoverInspect(); break;

        // ── File actions ─────────────────────────────────
        case 'open_location':
            document.getElementById('urlBar')?.focus();
            document.getElementById('urlBar')?.select();
            break;
        case 'upload_files':
            document.getElementById('uploadBrowseBtn')?.click();
            break;

        // ── Command palette ──────────────────────────────
        case 'commandPalette':
            document.getElementById('commandPalette')?.open();
            break;

        // ── Settings / Toolbar ───────────────────────────
        case 'openSettings':
            // Route to command palette with settings filter
            document.getElementById('commandPalette')?.open();
            break;
        case 'customizeToolbar':
            openCustomizeSheet();
            break;

        // ── Audio ────────────────────────────────────────
        case 'toggleAudio':      toggleAudio(); break;

        // ── Screen Reader ────────────────────────────────
        case 'toggleSpeech':
            if (typeof SRCaptionManager !== 'undefined') {
                SRCaptionManager.toggleSpeechLog();
            }
            break;

        // ── Vision Simulator ─────────────────────────────
        case 'setVisionSimulator':
            if (value === 'clear') {
                clearVisionSimulation();
            } else if (VISION_MAP[value]) {
                setVisionSimulation(VISION_MAP[value]);
            }
            break;

        // ── Motor Simulator ──────────────────────────────
        case 'setMotorSimulator':
            if (value === 'clear') {
                clearMotorSimulation();
            } else if (MOTOR_MAP[value]) {
                setMotorSimulation(MOTOR_MAP[value]);
            }
            break;

        // ── Screenshots (element/region — interactive) ───
        case 'screenshot_element':
            toggleHoverInspect(); // enter element selection mode
            break;

        // ── Recordings ───────────────────────────────────
        case 'viewRecordings':
            // Open recordings via command palette
            document.getElementById('commandPalette')?.open({ search: 'recording' });
            break;

        // ── Proxy ────────────────────────────────────────
        case 'manageProxyScripts':
            // Open plugin dropdown
            document.getElementById('pluginBtn')?.click();
            break;

        // ── AI prompts ───────────────────────────────────
        case 'aiAskPrompt':
        case 'aiAskSelectionPrompt':
            document.getElementById('commandPalette')?.open({ search: 'ask' });
            break;

        // ── Keyboard shortcuts ───────────────────────────
        case 'keyboardShortcuts':
            document.getElementById('commandPalette')?.open({ search: 'shortcut' });
            break;

        // ── Theme ────────────────────────────────────────
        case 'themeMatchSystem':
            syncColorScheme(getColorScheme());
            break;

        default:
            console.log('[tauri-menu] Unhandled action:', action, value);
    }
});

// Global context menu suppression: prevent the native macOS context menu
// ("Inspect Element", "View Page Source", etc.) from appearing anywhere in the
// control panel. It targets the control panel page, not the VM browser, so it's
// confusing. We allow the native menu only on text inputs (for Cut/Copy/Paste).
// Areas with custom context menus (VNC, tabs, toolbar) handle their own preventDefault.
document.addEventListener('contextmenu', (e) => {
    const tag = e.target.tagName;
    // Allow native menu on text inputs and textareas (Cut/Copy/Paste needed)
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    // Allow native menu inside contenteditable elements
    if (e.target.isContentEditable) return;
    // Suppress everywhere else
    e.preventDefault();
});

// Terminal buffer parsing: extract last command, output, and working directory
// by scanning backwards for prompt lines matching the zsh prompt format:
// domain:/path$ command
// Match any prompt in the format: something:/path$ command
// The domain part can be any hostname (stad.gent, inspekt, localhost, etc.)
// We use a generic regex rather than matching a specific domain, because
// the domain changes as the user navigates between sites.
// Match zsh prompt: domain:/path$ command
// Allows optional leading whitespace (xterm.js buffer quirk) and
// any hostname characters. The path is non-greedy up to "$ ".
const _PROMPT_REGEX = /^\s*([a-zA-Z0-9._-]+):(\S*)\$\s?(.*?)$/;

function _parseTerminalHistory() {
    if (!terminal) return null;
    const buffer = terminal.buffer.active;
    const totalRows = buffer.baseY + buffer.cursorY;

    // Scan backwards to find the two most recent prompt lines
    let prompts = []; // [{ row, path, command }]
    for (let row = totalRows; row >= 0 && prompts.length < 2; row--) {
        const line = buffer.getLine(row);
        if (!line) continue;
        const text = line.translateToString(true);
        const match = text.match(_PROMPT_REGEX);
        if (match) {
            prompts.push({ row, path: match[2], command: match[3].trim() });
        }
    }

    if (prompts.length === 0) return null;

    const lastPrompt = prompts[0]; // Most recent prompt
    const prevPrompt = prompts[1]; // Previous prompt (has the last executed command)

    // Current working directory from the most recent prompt
    const cwd = lastPrompt.path.replace(/^~/, '/home/inspekt') || '/home/inspekt';
    const cwdDisplay = lastPrompt.path || '~';

    // If there's no previous prompt, we can't extract command/output
    if (!prevPrompt || !prevPrompt.command) {
        return { cwd, cwdDisplay, command: null, output: null };
    }

    // Extract output: lines between previous prompt and current prompt
    const outputLines = [];
    for (let row = prevPrompt.row + 1; row < lastPrompt.row; row++) {
        const line = buffer.getLine(row);
        if (line) outputLines.push(line.translateToString(true));
    }
    // Trim trailing empty lines
    while (outputLines.length > 0 && outputLines[outputLines.length - 1].trim() === '') {
        outputLines.pop();
    }

    return {
        cwd,
        cwdDisplay,
        command: prevPrompt.command,
        output: outputLines.join('\n'),
    };
}

// Terminal context menu
document.getElementById('terminalContainer')?.addEventListener('contextmenu', async (e) => {
    e.preventDefault();
    e.stopPropagation();
    const hasSelection = terminal?.hasSelection?.();
    const history = _parseTerminalHistory();
    const hasCommand = history?.command;
    const hasOutput = history?.output;
    const cwd = history?.cwd || '/home/inspekt';

    // Fetch folder info for smart download items (~5ms localhost)
    let folderInfo = null;
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/folder-info?path=${encodeURIComponent(cwd)}`);
        const data = await resp.json();
        if (data.ok) folderInfo = data;
    } catch {}

    // Build download submenu: individual files + zip-all at the bottom
    let downloadSubmenu = null;

    if (folderInfo && folderInfo.recent_files?.length > 0) {
        const children = folderInfo.recent_files.map(f => ({
            label: `${f.name}  (${f.size === 0 ? 'Empty' : formatBytes(f.size)})`,
            action: () => triggerFileDownload(f.path),
            disabled: !f.downloadable,
            title: !f.downloadable ? 'File exceeds 5 MB limit' : undefined
        }));

        // Append zip-all option after a separator
        if (folderInfo.file_count > 1) {
            const n = folderInfo.file_count;
            const zipLabel = `Download all ${n} files as .zip (${formatBytes(folderInfo.total_size)})`;

            children.push({ separator: true });
            if (folderInfo.can_zip) {
                children.push({
                    label: zipLabel,
                    action: async () => {
                        showToast('Creating zip…', 'info');
                        try {
                            const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/download-zip?path=${encodeURIComponent(cwd)}`);
                            if (!resp.ok) {
                                const err = await resp.json().catch(() => ({}));
                                throw new Error(err.error || `HTTP ${resp.status}`);
                            }
                            const blob = await resp.blob();
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement('a');
                            a.href = url;
                            a.download = `${cwd.split('/').pop() || 'files'}.zip`;
                            a.click();
                            setTimeout(() => URL.revokeObjectURL(url), 1000);
                            showToast('Zip downloaded', 'success');
                        } catch (err) {
                            showToast(`Zip failed: ${err.message}`, 'error');
                        }
                    }
                });
            } else {
                children.push({
                    label: zipLabel,
                    disabled: true,
                    title: folderInfo.exceeded_limits
                        ? 'Folder exceeds limits (max 50 files or 50 MB)'
                        : 'No downloadable files'
                });
            }
        }

        downloadSubmenu = {
            label: 'Download',
            children
        };
    }

    // Build folder navigation submenu
    let folderSubmenu = null;
    const subdirs = folderInfo?.subdirs || [];
    if (subdirs.length > 0) {
        folderSubmenu = {
            label: 'Go to Folder',
            children: subdirs.map(name => ({
                label: name,
                action: () => sendTerminalCd(`${cwd}/${name}`)
            }))
        };
    }

    const parentDir = folderInfo?.parent;
    const cwdDisplay = history?.cwdDisplay || '~';

    const items = [
        // ── Navigation ──
        { navRow: [
            { label: 'Back', icon: NAV_ICONS.back, action: () => terminalGoBack(), disabled: !canTerminalGoBack() },
            { label: 'Forward', icon: NAV_ICONS.forward, action: () => terminalGoForward(), disabled: !canTerminalGoForward() },
            { label: 'Parent Directory', icon: NAV_ICONS.up, action: () => sendTerminalCd(parentDir), disabled: !parentDir },
        ] },
        ...(folderSubmenu ? [folderSubmenu] : []),
        { separator: true },
        // ── Clipboard ──
        { label: 'Copy', action: () => {
            if (hasSelection) {
                writeClipboard(terminal.getSelection());
                terminal.clearSelection();
            }
        }, disabled: !hasSelection },
        { label: 'Paste', action: async () => {
            try {
                const text = await readClipboard();
                if (terminalSocket?.readyState === WebSocket.OPEN) {
                    terminalSocket.send(text);
                }
            } catch {}
        }},
        { label: 'Select All', action: () => terminal?.selectAll?.() },
        { separator: true },
        { label: 'Copy to Clipboard', children: [
            { label: 'Last Command', action: () => {
                writeClipboard(history.command);
                showToast('Command copied', 'success');
            }, disabled: !hasCommand },
            { label: 'Last Output', action: () => {
                writeClipboard(history.output);
                showToast('Output copied', 'success');
            }, disabled: !hasOutput },
            { label: 'Last Command and Output', action: () => {
                writeClipboard(`$ ${history.command}\n${history.output}`);
                showToast('Command and output copied', 'success');
            }, disabled: !hasCommand || !hasOutput },
            { separator: true },
            { label: `Working Directory (${cwdDisplay})`, action: () => {
                writeClipboard(cwd);
                showToast(`Copied: ${cwdDisplay}`, 'success');
            }},
        ]},
        { separator: true },
        // ── File Operations ──
        { label: 'New File…', action: () => {
            const name = prompt('File name:');
            if (name) _sendTerminalCommand(`touch ${_shellQuote(name)}`);
        }},
        { label: 'New Folder…', action: () => {
            const name = prompt('Folder name:');
            if (name) _sendTerminalCommand(`mkdir ${_shellQuote(name)}`);
        }},
        { label: 'List Files', children: [
            { label: 'Simple', action: () => _sendTerminalCommand('ls') },
            { label: 'Detailed', action: () => _sendTerminalCommand('ls -la') },
            { label: 'By Size', action: () => _sendTerminalCommand('ls -lS') },
            { label: 'By Date', action: () => _sendTerminalCommand('ls -lt') },
        ]},
        { label: 'Find File…', action: () => {
            const term = prompt('Search for file name containing:');
            if (term) _sendTerminalCommand(`find . -maxdepth 3 -iname ${_shellQuote('*' + term + '*')} -not -path '*/.*'`);
        }},
        { separator: true },
        // ── Transfer ──
        { label: 'Upload…', action: () => triggerUploadFromToolbar() },
        ...(downloadSubmenu ? [downloadSubmenu] : []),
        { separator: true },
        // ── Inspekt CLI ──
        { label: 'Inspekt', children: [
            { label: 'Page Info', action: () => _sendTerminalCommand('inspekt info') },
            { label: 'Accessibility Audit', action: () => _sendTerminalCommand('inspekt axe') },
            { label: 'Page Outline', action: () => _sendTerminalCommand('inspekt outline') },
            { label: 'Extract Links', action: () => _sendTerminalCommand('inspekt links') },
            { label: 'Take Screenshot', action: () => _sendTerminalCommand('inspekt screenshot') },
        ]},
        { separator: true },
        // ── Terminal Settings ──
        { label: 'Clear', action: () => {
            terminal?.clear();
            if (terminalSocket?.readyState === WebSocket.OPEN) {
                terminalSocket.send('\x0c');
            }
        }},
        { label: 'Larger Text', action: () => adjustTerminalFontSize(1) },
        { label: 'Smaller Text', action: () => adjustTerminalFontSize(-1) },
        { label: terminalMode === 'split' ? 'Floating Terminal' : 'Split View',
          action: () => {
            if (terminalMode === 'split') {
                exitSplitMode();
            } else {
                enterSplitMode();
            }
        }},
        { label: 'Trigger Words…', action: () => {
            openFileInEditor('/home/inspekt/.config/inspekt.yaml');
        }},
    ];

    showContextMenu(e, items);
});

// Output panel context menu
document.getElementById('outputPanelContent')?.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    e.stopPropagation();
    const content = document.getElementById('outputPanelContent');
    const hasContent = content && content.textContent.trim().length > 0;
    showContextMenu(e, [
        { label: 'Copy All', action: () => {
            writeClipboard(content.textContent);
            showToast('Output copied', 'success');
        }, disabled: !hasContent },
        { label: 'Export as Text', action: () => {
            const blob = new Blob([content.textContent], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `inspekt-output-${Date.now()}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        }, disabled: !hasContent },
        { separator: true },
        { label: 'Clear', action: () => {
            content.innerHTML = '';
            closeOutputPanel();
        }},
    ]);
});

// Capture-phase Escape handler: fires BEFORE noVNC's keyboard handler
// can swallow the event. Without this, moving the mouse over the VNC
// canvas gives it focus, and noVNC intercepts Escape before it bubbles
// to our context menu dismiss handler.
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _isMenuOpen()) {
        e.preventDefault();
        e.stopImmediatePropagation();
        dismissContextMenu();
    }
}, true);  // true = capture phase

// Capture-phase keyboard context menu handler.
// Detects platform-specific shortcuts for "show context menu" and routes
// to the appropriate custom context menu based on what's under the cursor.
// Must be capture-phase to intercept before noVNC swallows the key event.
document.addEventListener('keydown', (e) => {
    const isContextMenuKey =
        e.key === 'ContextMenu' ||                                        // Windows/Linux Menu key
        (e.key === 'F10' && e.shiftKey) ||                                // Windows/Linux Shift+F10
        (e.key === 'Enter' && e.ctrlKey && !e.metaKey && !e.altKey);      // macOS Sequoia Control+Return

    if (!isContextMenuKey) return;

    // Don't intercept when typing in inputs or the terminal
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (document.activeElement?.isContentEditable) return;
    if (document.activeElement?.closest('#terminalContainer')) return;

    e.preventDefault();
    e.stopImmediatePropagation();

    // Find the UI area under the cursor and dispatch to the right handler
    const el = document.elementFromPoint(_lastMouseX, _lastMouseY);
    if (!el) return;

    const syntheticEvent = { clientX: _lastMouseX, clientY: _lastMouseY, preventDefault() {}, stopPropagation() {} };

    // VNC canvas
    if (el.closest('#vncContainer')) {
        const vm = _clientToVm(_lastMouseX, _lastMouseY);
        showVNCContextMenu(_lastMouseX, _lastMouseY, vm.x, vm.y);
        return;
    }

    // Individual tab
    const tabEl = el.closest('.tab');
    if (tabEl?.dataset?.tabId) {
        showTabContextMenu(syntheticEvent, tabEl.dataset.tabId);
        return;
    }

    // Tab bar empty area
    if (el.closest('#tabBar')) {
        showTabBarContextMenu(syntheticEvent);
        return;
    }

    // Terminal
    if (el.closest('#terminalContainer')) {
        document.getElementById('terminalContainer').dispatchEvent(
            new MouseEvent('contextmenu', { clientX: _lastMouseX, clientY: _lastMouseY, bubbles: true })
        );
        return;
    }

    // Output panel
    if (el.closest('#outputPanelContent')) {
        document.getElementById('outputPanelContent').dispatchEvent(
            new MouseEvent('contextmenu', { clientX: _lastMouseX, clientY: _lastMouseY, bubbles: true })
        );
        return;
    }
}, true);  // true = capture phase

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Escape to close overlays or toggle terminal
    if (e.key === 'Escape') {
        // Let ninja-keys handle Escape when palette is open — don't close anything else
        { const ninja = document.getElementById('commandPalette'); if (ninja?.visible) return; }
        // Close customize sheet if open
        if (_toolbarCustomizing) {
            e.preventDefault();
            closeCustomizeSheet();
            return;
        }
        // Close page info popout first
        if (pageInfoOpen) {
            e.preventDefault();
            closePageInfo();
            return;
        }
        // Blur URL bar if focused (second Escape after closing dropdown)
        if (document.activeElement === document.getElementById('urlBar')) {
            e.preventDefault();
            document.getElementById('urlBar').blur();
            return;
        }
        // Dismiss context menu first (highest priority)
        if (_isMenuOpen()) {
            e.preventDefault();
            dismissContextMenu();
            return;
        }
        // Dismiss any inspect mode (hover or locked)
        if (isHoverInspectActive || _inspectTrackingActive) {
            e.preventDefault();
            if (isHoverInspectActive) {
                isHoverInspectActive = false;
                document.getElementById('vncContainer').classList.remove('hover-inspect-active');
            }
            if (activeTabId) _tabInspectState[activeTabId] = { wasTracking: false };
            _cleanupAllInspectState();
            return;
        }
        // Close output panel
        if (document.getElementById('outputPanel').classList.contains('open')) {
            e.preventDefault();
            closeOutputPanel();
            return;
        }
        // Close CDP modal
        if (document.getElementById('cdpModalOverlay').classList.contains('open')) {
            e.preventDefault();
            closeCdpModal();
            return;
        }
        // Close restart modal
        if (document.getElementById('restartModalOverlay').classList.contains('open')) {
            e.preventDefault();
            closeRestartModal();
            return;
        }
        // Close grid overlay
        if (gridState.isOpen) {
            e.preventDefault();
            closeTabGrid();
            return;
        }
        // Toggle terminal (open if closed, close if open)
        e.preventDefault();
        toggleTerminal();
        return;
    }

    // Cmd/Ctrl+\ for split mode toggle
    if (e.key === '\\' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (isTerminalOpen || terminalMode === 'split') {
            toggleSplitMode();
        } else {
            // Open terminal in split mode directly
            enterSplitMode();
        }
        return;
    }

    // Cmd/Ctrl+K to toggle command palette (works everywhere)
    if (e.key === 'k' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const ninja = document.getElementById('commandPalette');
        if (ninja) {
            ninja.visible ? ninja.close() : ninja.open();
        }
        return;
    }

    // Ctrl+T for new tab (works everywhere)
    if (e.key === 't' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        createNewTab();
        return;
    }

    // Ctrl+W to close current tab
    if (e.key === 'w' && (e.ctrlKey || e.metaKey) && activeTabId && tabs.length > 1) {
        e.preventDefault();
        closeTab(activeTabId);
        return;
    }

    // Ctrl+Tab / Ctrl+Shift+Tab to cycle tabs
    if (e.key === 'Tab' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        const currentIndex = tabs.findIndex(t => t.id === activeTabId);
        let nextIndex;
        if (e.shiftKey) {
            nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
        } else {
            nextIndex = (currentIndex + 1) % tabs.length;
        }
        activateTab(tabs[nextIndex].id);
        return;
    }

    // Skip other shortcuts if typing in input fields or command palette is open
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
    { const ninja = document.getElementById('commandPalette'); if (ninja?.visible) return; }

    // G for grid view (when not in terminal or grid)
    if (e.key === 'g' && !e.ctrlKey && !e.metaKey && !isTerminalOpen && !gridState.isOpen) {
        e.preventDefault();
        toggleTabGrid();
        return;
    }

    // F for fullscreen
    if (e.key === 'f' && !e.ctrlKey && !e.metaKey && !isTerminalOpen && !gridState.isOpen) {
        e.preventDefault();
        toggleFullscreen();
        return;
    }

    // D for DevTools
    if (e.key === 'd' && !e.ctrlKey && !e.metaKey && !isTerminalOpen && !gridState.isOpen) {
        e.preventDefault();
        toggleDevTools();
    }

    // I for Inspect element mode
    if (e.key === 'i' && !e.ctrlKey && !e.metaKey && !isTerminalOpen && !gridState.isOpen) {
        e.preventDefault();
        toggleHoverInspect();
    }

    // A for Audio
    if (e.key === 'a' && !e.ctrlKey && !e.metaKey && !isTerminalOpen && !gridState.isOpen) {
        e.preventDefault();
        toggleAudio();
    }
});

// Check DevTools status on page load
checkDevToolsStatus();
