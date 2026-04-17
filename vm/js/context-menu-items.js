// =============================================
// Context Menu Item Builders
// =============================================
//
// Pure data builders that return item arrays for showContextMenu().
// Separated from vnc-context-menu.js to isolate menu definitions
// from orchestration logic (fetching, overlay cleanup, etc.).
//
// These builders are only called after all scripts have loaded (on user
// right-click), so globals like NAV_ICONS are safe to reference directly.
// Action callbacks also close over globals (reloadPage, copyToClipboard,
// etc.) which resolve at click time.

/**
 * Build items for the VNC viewport right-click context menu.
 *
 * @param {Object} ctx
 * @param {Object}  ctx.info          — element/selection info from /context-menu-info
 * @param {boolean} ctx.canGoBack
 * @param {boolean} ctx.canGoForward
 * @param {boolean} ctx.sitemapReady  — _sitemapReady
 * @param {Object}  ctx.sitemapNav    — _sitemapNav
 * @param {Object|null} ctx.lastScreenshotRegion — _lastScreenshotRegion
 * @param {string}  ctx.currentUrl
 * @param {boolean} ctx.isTerminalOpen
 * @param {number}  ctx.vmX           — click X in VM coordinates
 * @param {number}  ctx.vmY           — click Y in VM coordinates
 * @returns {Array} items array for showContextMenu()
 */
function buildVNCContextMenuItems(ctx) {
    const { info, sitemapNav, lastScreenshotRegion, currentUrl, vmX, vmY } = ctx;
    const hasSelection = !!info.selectedText;
    const hasLink = !!info.linkHref;
    const hasImage = info.isImage;
    const hasElement = !!info.elementTag;
    const selectorLabel = info.elementSelector || info.elementTag || 'element';

    const items = [];

    // ── Navigation row ──
    items.push({ navRow: [
        { label: 'Reload', icon: NAV_ICONS.reload, action: () => reloadPage() },
        { label: 'Back', icon: NAV_ICONS.back, action: () => goBack(), disabled: !ctx.canGoBack },
        { label: 'Forward', icon: NAV_ICONS.forward, action: () => goForward(), disabled: !ctx.canGoForward },
    ] });

    // ── Sitemap structural navigation ──
    if (ctx.sitemapReady && sitemapNav) {
        const hasSitemapContent = sitemapNav.in_sitemap || sitemapNav.parent;
        if (hasSitemapContent) {
            items.push({ separator: true });

            const parentInfo = sitemapNav.parent;
            if (parentInfo) {
                items.push({
                    label: `\u2191 ${parentInfo.title || parentInfo.path.split('/').filter(Boolean).pop() || 'Home'}`,
                    action: () => _sitemapGoUp(),
                    title: parentInfo.url,
                });
            }

            if (sitemapNav.in_sitemap && sitemapNav.children_total > 0) {
                items.push({
                    label: `\u2193 Child pages (${sitemapNav.children_total})`,
                    children: _buildSitemapSubmenuItems(sitemapNav.children, sitemapNav.children_total),
                });
            }
        }
    }

    items.push({ separator: true });

    // ── Selection actions ──
    if (hasSelection) {
        items.push({ label: 'Copy as Text', action: () => runInspektForClipboard('selection text --raw', 'Text') });
        items.push({ label: 'Copy as Markdown', action: () => runInspektForClipboard('selection markdown --raw', 'Markdown') });
        items.push({ label: 'Copy as HTML (Original)', action: () => runInspektForClipboard('selection html --raw', 'HTML') });
        items.push({ label: 'Copy as HTML (Cleaned up)', action: () => runInspektForClipboard('selection html --compact --raw', 'Cleaned up HTML') });
        items.push({ separator: true });
        items.push({ label: 'Describe Selection', action: () => runInspektAI('selection describe', 'Describing selection', 'Description') });
        items.push({ label: 'Ask About Selection\u2026', action: () => showAskDialog('selection') });
        items.push({ separator: true });
    }

    // ── Link actions ──
    if (hasLink) {
        items.push({ label: 'Open Link in New Tab', action: () => openLinkInNewTab(info.linkHref) });
        items.push({ label: 'Open Link in Host Browser', action: () => window.open(info.linkHref, '_blank') });
        items.push({ label: 'Copy Link Address', action: () => copyToClipboard(info.linkHref) });
        items.push({ separator: true });
    }

    // ── Image actions ──
    if (hasImage) {
        items.push({ label: 'Copy Image', action: () => copyImageToClipboard(info.imageSrc) });
        items.push({ label: 'Copy Image URL', action: () => copyToClipboard(info.imageSrc) });
        items.push({ label: 'Download Image', action: () => downloadImage(info.imageSrc) });
        items.push({ label: 'Open Image in New Tab', action: () => openLinkInNewTab(info.imageSrc) });
        items.push({ separator: true });
        items.push({ label: 'Describe Image (AI)', action: () => runInspektAI('inspected describe', 'Analyzing image', 'Image description') });
        items.push({ separator: true });
    }

    // ── Element actions ──
    if (hasElement) {
        items.push({ label: `Inspect \u2039${selectorLabel}\u203A`, action: async () => {
            try {
                const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspect/set-at-point?x=${vmX}&y=${vmY}`);
                const data = await resp.json();
                if (data.ok) {
                    showInspectOverlay(data.rect, data.selector || selectorLabel);
                    showToast(`Inspecting: ${data.selector || selectorLabel}`, 'success');
                    _showInspectInfoPanel();
                } else {
                    showToast(data.error || 'Could not inspect element', 'error');
                }
            } catch (e) {
                showToast('Failed to inspect element', 'error');
            }
        }});
        items.push({ label: 'Copy Element HTML', action: () => runInspektForClipboard('inspected html --raw', 'Element HTML') });
        items.push({ label: 'Copy Element Text', action: () => runInspektForClipboard('inspected text --raw', 'Element text') });
        if (!hasImage) items.push({ label: 'Describe Element', action: () => runInspektAI('inspected describe', 'Describing element', 'Element description') });
        items.push({ label: 'Ask About Element\u2026', action: () => showAskDialog('inspected') });
        items.push({ separator: true });
    }

    // ── Screenshot submenu ──
    const _ts = () => new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const screenshotChildren = [
        { label: 'Viewport', action: () => screenshotToDownload('/screenshot/viewport', `viewport-${_ts()}.png`) },
        { label: 'Full Page', action: () => screenshotToDownload('/screenshot/page', `fullpage-${_ts()}.png`) },
    ];
    if (hasElement) {
        const shortSelector = (info.elementSelector || info.elementTag).slice(0, 30);
        screenshotChildren.push({ separator: true });
        screenshotChildren.push({ label: `Element \u2039${shortSelector}\u203a`, action: () => {
            screenshotToDownload('/screenshot/element', `element-${(info.elementSelector || 'el').replace(/[^a-z0-9_-]/gi, '_').slice(0, 30)}-${_ts()}.png`);
        }});
    }
    screenshotChildren.push({ separator: true });
    screenshotChildren.push({ label: 'Select Region\u2026', action: () => startRegionSelection() });
    if (lastScreenshotRegion) {
        const r = lastScreenshotRegion;
        screenshotChildren.push({ label: `Repeat Last Region (${Math.round(r.w)}\u00d7${Math.round(r.h)})`, action: () => {
            screenshotToDownload(`/screenshot/region?x=${r.x}&y=${r.y}&w=${r.w}&h=${r.h}`, `region-${Math.round(r.w)}x${Math.round(r.h)}-${_ts()}.png`);
        }});
    }
    screenshotChildren.push({ separator: true });
    screenshotChildren.push({ label: 'Redacted', children: [
        { label: 'Viewport (Blurred)', action: () => screenshotToDownload('/screenshot/redacted?mode=viewport&style=blur', `redacted-viewport-blur-${_ts()}.png`) },
        { label: 'Viewport (Bars \u2588\u2588\u2588\u2588)', action: () => screenshotToDownload('/screenshot/redacted?mode=viewport&style=bar', `redacted-viewport-bar-${_ts()}.png`) },
        { label: 'Full Page (Blurred)', action: () => screenshotToDownload('/screenshot/redacted?mode=page&style=blur', `redacted-fullpage-blur-${_ts()}.png`) },
        { label: 'Full Page (Bars \u2588\u2588\u2588\u2588)', action: () => screenshotToDownload('/screenshot/redacted?mode=page&style=bar', `redacted-fullpage-bar-${_ts()}.png`) },
    ]});
    items.push({ label: 'Screenshot', children: screenshotChildren });

    // ── Debug submenu ──
    const debugChildren = [];
    debugChildren.push({ label: 'Performance Metrics', action: async () => {
        try {
            const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspect/performance`);
            const data = await resp.json();
            if (data.ok) {
                openOutputPanel('Performance Metrics', '\u23f1', formatPerformanceOutput(data.metrics));
            } else {
                showToast(data.error || 'Failed to get metrics', 'error');
            }
        } catch (e) { showToast('Failed to get performance metrics', 'error'); }
    }});
    debugChildren.push({ label: 'Image Analysis', action: async () => {
        try {
            const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspect/images`);
            const data = await resp.json();
            if (data.ok) {
                openOutputPanel('Image Analysis', '\ud83d\uddbc', formatImageAnalysisOutput(data));
            } else {
                showToast(data.error || 'Failed to analyze images', 'error');
            }
        } catch (e) { showToast('Failed to analyze images', 'error'); }
    }});
    debugChildren.push({ label: 'Extract Tables', action: async () => {
        try {
            const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspect/tables`);
            const data = await resp.json();
            if (data.ok) {
                if (data.count === 0) {
                    showToast('No tables found on this page', 'info');
                } else {
                    openOutputPanel('Tables', '\ud83d\udcca', formatTablesOutput(data));
                }
            } else {
                showToast(data.error || 'Failed to extract tables', 'error');
            }
        } catch (e) { showToast('Failed to extract tables', 'error'); }
    }});
    if (hasElement) {
        debugChildren.push({ separator: true });
        debugChildren.push({ label: `Highlight Similar \u2039${selectorLabel}\u203a`, action: async () => {
            // Build a selector from the inspected element's tag + first class
            const tag = info.elementTag || '';
            let sel = tag;
            if (info.elementSelector && info.elementSelector.includes('.')) {
                sel = info.elementSelector.split(' ')[0]; // Use first part of selector
            }
            try {
                const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspect/highlight?selector=${encodeURIComponent(sel)}`);
                const data = await resp.json();
                if (data.ok) {
                    showToast(data.message, 'success');
                } else {
                    showToast(data.error || 'Failed to highlight', 'error');
                }
            } catch (e) { showToast('Failed to highlight elements', 'error'); }
        }});
    }
    items.push({ label: 'Debug', children: debugChildren });

    // ── Footer actions ──
    items.push({ separator: true });
    items.push({ label: 'Copy Page URL', action: () => copyToClipboard(currentUrl || '') });
    items.push({ label: 'Inspect (DevTools)', action: () => toggleDevToolsInVM() });
    items.push({ label: ctx.isTerminalOpen ? 'Hide Terminal' : 'Show Terminal', action: () => toggleTerminal() });

    return items;
}

/**
 * Build items for the tab bar right-click context menu (empty area).
 *
 * @param {Object} ctx
 * @param {Array}  ctx.closedTabs — closedTabs array
 * @param {Array}  ctx.tabs       — tabs array
 * @returns {Array} items array for showContextMenu()
 */
function buildTabBarContextMenuItems(ctx) {
    const items = [
        { label: 'New Cloud Tab', action: () => createNewTab() },
        { label: 'New Local Tab', action: () => createLocalTab() },
        { label: 'Paste and Open URLs', action: () => openUrlsFromClipboard() },
    ];

    if (ctx.closedTabs.length > 0) {
        const last = ctx.closedTabs[ctx.closedTabs.length - 1];
        const label = last.title.length > 30 ? last.title.slice(0, 30) + '…' : last.title;
        items.push({ separator: true });
        items.push({ label: `Reopen Closed Tab (${label})`, action: () => reopenClosedTab() });
        if (ctx.closedTabs.length > 1) {
            items.push({ label: `Reopen All ${ctx.closedTabs.length} Closed Tabs`, action: () => reopenAllClosedTabs() });
        }
    }

    if (ctx.tabs.length >= 2) {
        items.push({ separator: true });
        items.push({ label: 'Reload All Tabs', action: () => reloadAllTabs() });
        items.push({ separator: true });
        items.push({ label: 'Copy All URLs', action: () => copyAllUrls() });
        items.push({ label: 'Copy All URLs as Markdown', action: () => copyAllUrlsAsMarkdown() });
        const unpinnedCount = ctx.tabs.filter(t => !t.pinned).length;
        if (unpinnedCount >= 2) {
            items.push({ separator: true });
            items.push({ label: `Close All ${unpinnedCount} Tabs`, action: () => closeAllTabs() });
        }
    }

    return items;
}
