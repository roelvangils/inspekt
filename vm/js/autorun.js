// =============================================
// Autorun on Navigation
// =============================================
//
// The extension's content script triggers autorun via
// browser_info on ws.onopen, which works on refresh but
// can miss link-click navigations due to WebSocket
// lifecycle timing. This backup mechanism detects URL
// changes via the control panel's polling and triggers
// autorun via the API as a reliable fallback.

let lastAutorunUrl = '';
let lastAutorunTime = 0;
const AUTORUN_DEBOUNCE_MS = 3000;

// Sitemap navigation state
let _sitemapReady = false;               // Has the sitemap been fetched for current origin?
let _sitemapFetchedOrigins = new Set();   // Origins we've already fetched this session
let _sitemapNav = null;                   // Cached tree response for current page

/**
 * Simple glob-style pattern matcher (mirrors Python's fnmatch).
 * Supports '*' (any chars) and '?' (single char).
 */
function globMatch(text, pattern) {
    // Convert glob to regex: escape regex chars, then convert * and ?
    let re = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&');
    re = re.replace(/\*/g, '.*').replace(/\?/g, '.');
    return new RegExp('^' + re + '$', 'i').test(text);
}

/**
 * Check if a URL matches autorun domain/path patterns.
 * Mirrors the Python matches_autorun_pattern() logic.
 */
function matchesAutorunPattern(url, patternsStr) {
    if (!patternsStr || patternsStr.trim() === '' || patternsStr.trim() === '*') return true;
    try {
        const parsed = new URL(url);
        const hostname = parsed.hostname;
        const full = hostname + parsed.pathname;
        for (const raw of patternsStr.split(',')) {
            const pattern = raw.trim();
            if (!pattern) continue;
            if (pattern.includes('/')) {
                // Pattern includes path
                if (globMatch(full, pattern) || globMatch(full, 'www.' + pattern)) return true;
            } else {
                // Domain-only pattern
                if (globMatch(hostname, pattern) || globMatch(hostname, 'www.' + pattern)) return true;
                if (hostname.startsWith('www.') && globMatch(hostname.slice(4), pattern)) return true;
            }
        }
    } catch (e) { /* invalid URL */ }
    return false;
}

/**
 * Trigger autorun plugins for a URL change.
 * Debounced to avoid double-execution when the content script's
 * browser_info also triggers autorun on the bridge side.
 */
async function triggerAutorunPlugins(url) {
    if (!url || !url.startsWith('http') || isInternalUrl(url)) return;

    const now = Date.now();
    if (url === lastAutorunUrl && (now - lastAutorunTime) < AUTORUN_DEBOUNCE_MS) return;
    lastAutorunUrl = url;
    lastAutorunTime = now;

    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/autorun`);
        const data = await resp.json();
        if (!data.ok || !data.plugins || data.plugins.length === 0) return;

        for (const plugin of data.plugins) {
            if (!matchesAutorunPattern(url, plugin.autorun_domains)) continue;
            try {
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/${plugin.id}/run`, { method: 'POST' });
                console.log(`[Autorun] Executed '${plugin.name}' on ${url.slice(0, 60)}`);
            } catch (e) {
                console.warn(`[Autorun] Failed to execute '${plugin.name}':`, e);
            }
        }
    } catch (e) {
        // API not available — silently skip
    }
}

// --- Sitemap auto-fetch and tree pre-loading ---

async function maybeFetchSitemap(url) {
    try {
        const origin = new URL(url).origin;
        if (_sitemapFetchedOrigins.has(origin)) return;

        // New domain — reset state so context menu shows "Loading…" until ready
        _sitemapReady = false;
        _sitemapNav = null;

        // Check if already cached on the server (fast, no fetch)
        const statusResp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/sitemaps/status?origin=${encodeURIComponent(origin)}`);
        const status = await statusResp.json();
        if (status.ok && status.cached) {
            _sitemapFetchedOrigins.add(origin);
            _sitemapReady = true;
            refreshSitemapNav(url);
            return;
        }

        // Fetch sitemap structure in background (XML only, no titles)
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/sitemaps/fetch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origin })
        });
        const data = await resp.json();
        _sitemapFetchedOrigins.add(origin);
        if (data.ok && data.total_urls > 0) {
            _sitemapReady = true;
            showToast(`Sitemap indexed (${data.total_urls} pages)`, 'dark');
            refreshSitemapNav(url);
        } else {
            // No sitemap found — mark as ready so context menu shows
            // "not in sitemap" instead of "Loading…" forever
            _sitemapReady = true;
            _sitemapNav = null;
        }
    } catch (e) {
        // Network error — mark as ready (no data) so the context menu
        // isn't stuck on "Loading…". Origin is NOT added to the set,
        // so navigating within this domain will retry the fetch.
        _sitemapReady = true;
        _sitemapNav = null;
        console.debug('[Sitemap] Auto-fetch failed:', e);
    }
}

let _sitemapNavAbort = null;  // AbortController for in-flight /tree requests

async function refreshSitemapNav(url) {
    // Cancel any in-flight request so stale responses don't overwrite
    if (_sitemapNavAbort) _sitemapNavAbort.abort();
    _sitemapNavAbort = new AbortController();
    const signal = _sitemapNavAbort.signal;

    try {
        const u = new URL(url);
        // If sitemap wasn't auto-fetched yet, check if it was cached
        // by another source (e.g., the CLI `sitemap` command)
        if (!_sitemapReady) {
            const statusResp = await fetch(
                `http://${VNC_HOST}:${CONTROL_PORT}/api/sitemaps/status?origin=${encodeURIComponent(u.origin)}`,
                { signal }
            );
            const status = await statusResp.json();
            if (status.ok && status.cached) {
                _sitemapReady = true;
                _sitemapFetchedOrigins.add(u.origin);
            } else {
                _sitemapNav = null;
                _sitemapReady = true;
                return;
            }
        }
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/api/sitemaps/tree?origin=${encodeURIComponent(u.origin)}&path=${encodeURIComponent(u.pathname)}`,
            { signal }
        );
        const data = await resp.json();
        _sitemapNav = data.ok ? data : null;
    } catch (e) {
        if (e.name === 'AbortError') return;  // superseded by newer request
        _sitemapNav = null;
    }
}

function _sitemapGoUp() {
    if (_sitemapNav && _sitemapNav.parent && _sitemapNav.parent.url) {
        navigateTo(_sitemapNav.parent.url);
    }
}

/**
 * Recursively build context menu items from sitemap children.
 * Leaf nodes navigate on click; branch nodes open a submenu.
 * Branch nodes that are also real pages get an "Open [title]" item
 * at the top of their submenu so the page itself remains navigable.
 */
function _buildSitemapSubmenuItems(children, childrenTotal) {
    const titled = [];
    const untitled = [];

    for (const child of children) {
        const pageExists = child.exists !== false;
        const hasTitle = !!child.title;
        const slug = '/' + (child.path.split('/').filter(Boolean).pop() || '');
        const label = hasTitle ? child.title : slug;

        if (child.children && child.children.length > 0) {
            // Branch node — has sub-children, open as submenu
            const subItems = _buildSitemapSubmenuItems(child.children, child.children_total);
            if (pageExists) {
                subItems.unshift({
                    label: `Open \u201c${label}\u201d`,
                    action: () => navigateTo(child.url),
                });
            }
            (hasTitle ? titled : untitled).push({ label, children: subItems });
        } else if (pageExists) {
            // Leaf node — navigate on click
            (hasTitle ? titled : untitled).push({ label, action: () => navigateTo(child.url) });
        }
    }

    // Titled items first, then untitled items with a header
    const items = [...titled];
    if (untitled.length > 0) {
        if (titled.length > 0) items.push({ separator: true });
        items.push({ header: 'Not in sitemap' });
        items.push(...untitled);
    }
    if (childrenTotal > 25) {
        items.push({ separator: true });
        items.push({
            label: `(${childrenTotal - 25} more pages)`,
            disabled: true,
        });
    }
    return items;
}

// Tab switching — keeps class, aria-selected, and roving tabindex in sync
// for mouse and keyboard activations alike.
document.addEventListener('click', (e) => {
    const tab = e.target.closest('.page-info-tab');
    if (!tab) return;
    pageInfoActiveTab = tab.dataset.tab;
    document.querySelectorAll('.page-info-tab').forEach(t => {
        const active = t.dataset.tab === pageInfoActiveTab;
        t.classList.toggle('active', active);
        t.setAttribute('aria-selected', active ? 'true' : 'false');
        t.setAttribute('tabindex', active ? '0' : '-1');
    });
    renderPageInfoTab(pageInfoActiveTab);
});

function renderPageInfoTab(name) {
    const content = document.getElementById('pageInfoContent');
    if (!pageInfoData) {
        content.innerHTML = '<div class="page-info-loading">No data</div>';
        return;
    }
    const d = pageInfoData[name];
    if (!d) {
        content.innerHTML = '<div class="page-info-loading">No data for this category</div>';
        return;
    }
    const renderers = {
        summary: renderSummaryTab,
        performance: renderPerformanceTab,
        meta: renderMetaTab,
        seo: renderSeoTab,
        security: renderSecurityTab,
        accessibility: renderAccessibilityTab,
        resources: renderResourcesTab,
        storage: renderStorageTab,
        tech: renderTechTab,
        layout: renderLayoutTab
    };
    content.innerHTML = (renderers[name] || (() => ''))(d);
}

function row(key, value) {
    if (value === null || value === undefined) return '';
    return `<div class="page-info-row"><span class="page-info-key">${key}</span><span class="page-info-value">${value}</span></div>`;
}

function badge(text, level) {
    return `<span class="page-info-badge ${level}">${text}</span>`;
}

function sectionTitle(text) {
    return `<div class="page-info-section-title">${text}</div>`;
}

function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function formatMs(ms) {
    if (ms === null || ms === undefined) return '—';
    if (ms < 1000) return ms + ' ms';
    return (ms / 1000).toFixed(2) + ' s';
}

// --- Render functions for each tab ---

function renderSummaryTab(d) {
    const secure = d.isSecure ? badge('HTTPS', 'good') : badge('HTTP', 'bad');
    return [
        row('URL', `<span class="page-info-value wrap" style="font-size:11px">${esc(d.url || '')}</span>`),
        row('Title', esc(d.title || '—')),
        row('Domain', esc(d.domain || '—')),
        row('Protocol', secure),
        row('Viewport', `${d.width || '?'} × ${d.height || '?'}`),
        row('Language', esc(d.device?.language || '—')),
        row('Screen', esc(d.device?.screenResolution || '—')),
        row('DPR', d.device?.devicePixelRatio || '—'),
        row('Touch', d.device?.touchSupport ? 'Yes' : 'No'),
        row('Online', d.device?.onlineStatus ? badge('Yes', 'good') : badge('No', 'bad')),
        row('Cookies', d.cookieCount || 0),
    ].join('');
}

function renderPerformanceTab(d) {
    const lcpBadge = (ms) => {
        if (ms === null || ms === undefined) return '—';
        if (ms < 2500) return badge(formatMs(ms), 'good');
        if (ms < 4000) return badge(formatMs(ms), 'warn');
        return badge(formatMs(ms), 'bad');
    };
    const clsBadge = (v) => {
        if (v === null || v === undefined) return '—';
        const val = v.toFixed(3);
        if (v < 0.1) return badge(val, 'good');
        if (v < 0.25) return badge(val, 'warn');
        return badge(val, 'bad');
    };
    return [
        sectionTitle('Timing'),
        row('Page Load', formatMs(d.pageLoadTime)),
        row('DOM Content Loaded', formatMs(d.domContentLoaded)),
        row('Time to First Byte', formatMs(d.timeToFirstByte)),
        sectionTitle('Paint'),
        row('First Paint', formatMs(d.firstPaint)),
        row('First Contentful Paint', formatMs(d.firstContentfulPaint)),
        row('Largest Contentful Paint', lcpBadge(d.largestContentfulPaint)),
        sectionTitle('Core Web Vitals'),
        row('CLS', clsBadge(d.cls)),
        row('FID', d.fid !== undefined ? formatMs(d.fid) : '—'),
        row('INP', d.inp !== undefined ? formatMs(d.inp) : '—'),
    ].join('');
}

function renderMetaTab(d) {
    let html = '';
    html += sectionTitle('Document');
    html += row('Language', esc(d.specifiedLanguage || '—'));
    html += row('Charset', esc(d.charset || '—'));

    if (d.openGraph && Object.keys(d.openGraph).length > 0) {
        html += sectionTitle('Open Graph');
        for (const [k, v] of Object.entries(d.openGraph)) {
            html += row('og:' + k, esc(v || ''));
        }
    }

    if (d.twitterCard && Object.keys(d.twitterCard).length > 0) {
        html += sectionTitle('Twitter Card');
        for (const [k, v] of Object.entries(d.twitterCard)) {
            html += row('twitter:' + k, esc(v || ''));
        }
    }

    if (d.metaTags && d.metaTags.length > 0) {
        html += sectionTitle(`Meta Tags (${d.metaTags.length})`);
        d.metaTags.slice(0, 15).forEach(tag => {
            const name = tag.name || tag.property || tag['http-equiv'] || 'meta';
            const content = tag.content || '—';
            html += row(esc(name), esc(content));
        });
        if (d.metaTags.length > 15) {
            html += row('…', `+${d.metaTags.length - 15} more`);
        }
    }
    return html;
}

function renderSeoTab(d) {
    let html = '';
    html += row('Canonical', d.canonical ? esc(d.canonical) : '—');
    html += row('Description', d.description ? esc(d.description) : '—');
    html += row('Keywords', d.keywords ? esc(d.keywords) : '—');
    html += row('Robots', d.robots ? esc(d.robots) : '—');
    html += row('Sitemap', d.sitemap ? esc(d.sitemap) : '—');
    html += row('Favicon', d.favicon || '—');
    html += row('Microdata', d.microdataCount || 0);

    if (d.jsonLd && d.jsonLd.length > 0) {
        html += sectionTitle('JSON-LD');
        html += row('Types', d.jsonLd.map(esc).join(', '));
    }

    if (d.alternateLanguages && d.alternateLanguages.length > 0) {
        html += sectionTitle('Hreflang');
        d.alternateLanguages.forEach(al => {
            html += row(esc(al.lang), esc(al.href || ''));
        });
    }
    return html;
}

function renderSecurityTab(d) {
    return [
        row('HTTPS', d.isSecure ? badge('Secure', 'good') : badge('Not Secure', 'bad')),
        row('Mixed Content', d.hasMixedContent ? badge('Detected', 'bad') : badge('None', 'good')),
        row('CSP (meta)', d.cspMeta ? esc(d.cspMeta).substring(0, 80) + (d.cspMeta.length > 80 ? '…' : '') : '—'),
        row('Referrer Policy', d.referrerPolicy ? esc(d.referrerPolicy) : '—'),
    ].join('');
}

function renderAccessibilityTab(d) {
    let html = '';
    html += sectionTitle('Landmarks');
    if (d.landmarks) {
        for (const [role, count] of Object.entries(d.landmarks)) {
            html += row(esc(role), count);
        }
    }
    html += row('Total', d.landmarkCount || 0);

    html += sectionTitle('Headings');
    if (d.headingStructure) {
        for (const [h, count] of Object.entries(d.headingStructure)) {
            if (count > 0) html += row(h.toUpperCase(), count);
        }
    }

    html += sectionTitle('Issues');
    html += row('Images without alt', d.imagesWithoutAlt !== undefined
        ? (d.imagesWithoutAlt > 0 ? badge(d.imagesWithoutAlt, 'bad') : badge('0', 'good'))
        : '—');
    html += row('Total images', d.totalImages || 0);
    if (d.formLabelsIssues) {
        html += row('Form fields', d.formLabelsIssues.total || 0);
        html += row('Missing labels', d.formLabelsIssues.missingLabels > 0
            ? badge(d.formLabelsIssues.missingLabels, 'bad')
            : badge('0', 'good'));
    }
    html += row('Links without text', d.linksWithoutText > 0 ? badge(d.linksWithoutText, 'bad') : badge('0', 'good'));
    html += row('Unlabeled buttons', d.buttonsWithoutLabels > 0 ? badge(d.buttonsWithoutLabels, 'bad') : badge('0', 'good'));

    html += sectionTitle('Features');
    html += row('Skip link', d.hasSkipLink ? badge('Yes', 'good') : badge('No', 'warn'));
    html += row('ARIA attributes', d.ariaAttributeCount || 0);
    html += row('lang attribute', d.hasLangAttribute ? badge('Yes', 'good') : badge('No', 'bad'));
    return html;
}

function renderResourcesTab(d) {
    let html = '';
    html += sectionTitle('Counts');
    html += row('Scripts', d.scriptCount || 0);
    html += row('Stylesheets', d.stylesheetCount || 0);
    html += row('Images', d.imageCount || 0);
    html += row('Links', d.linkCount || 0);
    html += row('Forms', d.formCount || 0);
    html += row('Iframes', d.iframeCount || 0);
    html += row('Videos', d.videos || 0);
    html += row('Audio', d.audio || 0);
    html += row('SVGs', d.svgImages || 0);

    if (d.thirdParty) {
        html += sectionTitle('Third-Party');
        html += row('External domains', d.thirdParty.externalDomainCount || 0);
        if (d.thirdParty.externalDomains && d.thirdParty.externalDomains.length > 0) {
            d.thirdParty.externalDomains.forEach(domain => {
                html += row('', esc(domain));
            });
        }
    }

    if (d.fonts) {
        html += sectionTitle('Fonts');
        html += row('Font files', d.fonts.totalFontFiles || 0);
        if (d.fonts.googleFonts && d.fonts.googleFonts.length > 0) {
            html += row('Google Fonts', d.fonts.googleFonts.map(esc).join(', '));
        }
        if (d.fonts.customFonts && d.fonts.customFonts.length > 0) {
            html += row('Custom fonts', d.fonts.customFonts.map(esc).join(', '));
        }
    }

    if (d.network) {
        html += sectionTitle('Network');
        html += row('Total requests', d.network.totalRequests || 0);
        html += row('Total transfer', formatBytes(d.network.totalSize));
        if (d.network.largestResource) {
            html += row('Largest resource', `${esc(d.network.largestResource.name)} (${formatBytes(d.network.largestResource.size)})`);
        }
    }
    return html;
}

function renderStorageTab(d) {
    let html = '';
    html += sectionTitle('Cookies');
    html += row('Count', d.cookieCount || 0);
    if (d.cookieNames && d.cookieNames.length > 0) {
        d.cookieNames.slice(0, 10).forEach(name => {
            html += row('', esc(name));
        });
        if (d.cookieNames.length > 10) {
            html += row('', `+${d.cookieNames.length - 10} more`);
        }
    }

    html += sectionTitle('Local Storage');
    html += row('Size', formatBytes(d.localStorageSize || 0));
    html += row('Keys', (d.localStorageKeys || []).length);
    if (d.localStorageKeys && d.localStorageKeys.length > 0) {
        d.localStorageKeys.slice(0, 8).forEach(key => {
            html += row('', esc(key));
        });
        if (d.localStorageKeys.length > 8) {
            html += row('', `+${d.localStorageKeys.length - 8} more`);
        }
    }

    html += sectionTitle('Session Storage');
    html += row('Size', formatBytes(d.sessionStorageSize || 0));
    html += row('Keys', (d.sessionStorageKeys || []).length);

    html += sectionTitle('Service Worker');
    html += row('Registered', d.hasServiceWorker ? 'Yes' : 'No');
    return html;
}

function renderTechTab(d) {
    let html = '';
    if (!d || Object.keys(d).length === 0) {
        return '<div class="page-info-loading">No technologies detected</div>';
    }
    for (const [category, items] of Object.entries(d)) {
        html += sectionTitle(esc(category));
        items.forEach(item => {
            html += row('', esc(item));
        });
    }
    return html;
}

function renderLayoutTab(d) {
    return [
        sectionTitle('Viewport'),
        row('Width', d.viewportWidth || '—'),
        row('Height', d.viewportHeight || '—'),
        sectionTitle('Document'),
        row('Width', d.documentWidth || '—'),
        row('Height', d.documentHeight || '—'),
        sectionTitle('Scroll'),
        row('X', d.scrollX || 0),
        row('Y', d.scrollY || 0),
        row('Visible', d.visiblePercentage !== undefined ? Math.round(d.visiblePercentage) + '%' : '—'),
    ].join('');
}

// HTML escape helper for page-info
function esc(str) {
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

// --- Dropdown render/filter/dismiss ---

// Material Design icon paths for per-row action buttons
const HISTORY_ACTION_ICONS = {
    cloud: 'M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96zM19 18H6c-2.21 0-4-1.79-4-4s1.79-4 4-4h.71C7.37 7.69 9.48 6 12 6c3.04 0 5.5 2.46 5.5 5.5v.5H19c1.66 0 3 1.34 3 3s-1.34 3-3 3z',
    local: 'M19 4H5c-1.11 0-2 .89-2 2v12c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6c0-1.11-.9-2-2-2zm0 14H5V8h14v10z',
    host:  'M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z',
};

const HISTORY_ACTION_LABELS = {
    cloud: 'Open as Cloud Tab',
    local: 'Open as Local Tab',
    host:  'Open in Host Browser',
};

function renderHistoryActionButtons() {
    let html = '<div class="history-option-actions">';
    for (const action of ['cloud', 'local', 'host']) {
        html += `<button type="button" class="history-action-btn history-action-${action}" data-action="${action}" title="${HISTORY_ACTION_LABELS[action]}" aria-label="${HISTORY_ACTION_LABELS[action]}" tabindex="-1">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="${HISTORY_ACTION_ICONS[action]}"/></svg>
        </button>`;
    }
    html += '</div>';
    return html;
}

async function handleHistoryAction(action, url) {
    dismissHistoryDropdown();
    try {
        if (action === 'cloud') {
            const newTabId = await _addCloudTab(url);
            if (newTabId && typeof activateTab === 'function') await activateTab(newTabId);
        } else if (action === 'local') {
            const tabId = _addLocalTab(url);
            activeTabId = tabId;
            if (typeof renderTabs === 'function') renderTabs();
            if (typeof syncViewport === 'function') syncViewport();
        } else if (action === 'host') {
            window.open(url, '_blank');
        }
    } catch (err) {
        console.warn('[urlbar] action failed:', action, err);
        if (typeof showToast === 'function') showToast('Action failed', 'error', 2000);
    }
}

function renderHistoryDropdown(filter) {
    const dropdown = document.getElementById('urlHistoryDropdown');
    const trimmedFilter = (filter || '').trim();
    const ranked = rankedHistory(trimmedFilter, 15);

    // Search-engine fallback: when the typed text isn't URL-shaped, offer
    // a direct search as the first option (matching Chrome's default).
    const showSearchRow = trimmedFilter.length > 0 && !looksLikeUrl(trimmedFilter);
    const searchEngine = getConfig('browser.search-engine', 'https://duckduckgo.com/?q=');
    let searchEngineName = 'search';
    try { searchEngineName = new URL(searchEngine).hostname.replace(/^www\./, ''); } catch { /* ignore */ }
    const searchUrl = showSearchRow ? searchEngine + encodeURIComponent(trimmedFilter) : '';

    // Empty-state short-circuits (only when there's literally nothing to show)
    if (!showSearchRow && ranked.length === 0 && visitedHistory.length === 0) {
        dropdown.innerHTML = '<div class="history-empty">No history yet</div>';
        return;
    }
    if (!showSearchRow && ranked.length === 0) {
        dropdown.innerHTML = '<div class="history-empty">No matches</div>';
        return;
    }

    let html = '';
    let optionIndex = 0;

    if (showSearchRow) {
        const cls = 'history-option history-option-search' + (optionIndex === historyActiveIndex ? ' active' : '');
        const ariaSelected = optionIndex === historyActiveIndex ? 'true' : 'false';
        html += `<div class="${cls}" role="option" id="history-opt-${optionIndex}" data-index="${optionIndex}" data-url="${escapeHtml(searchUrl)}" aria-selected="${ariaSelected}">
            <div class="history-search-icon">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden="true"><path d="M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>
            </div>
            <div class="history-option-text">
                <span class="history-option-title">Search <em>${escapeHtml(searchEngineName)}</em> for &ldquo;${escapeHtml(trimmedFilter)}&rdquo;</span>
            </div>
        </div>`;
        optionIndex++;
    }
    ranked.forEach(entry => {
        const cls = 'history-option' + (optionIndex === historyActiveIndex ? ' active' : '');
        const ariaSelected = optionIndex === historyActiveIndex ? 'true' : 'false';
        const titleHtml = highlightMatch(entry.title || entry.url, trimmedFilter);
        const urlHtml = highlightMatch(stripScheme(entry.url), trimmedFilter);
        const faviconHtml = entry.favicon
            ? `<img class="history-option-favicon" src="${escapeHtml(entry.favicon)}" alt="">`
            : `<div class="history-option-favicon-placeholder">🌐</div>`;
        html += `<div class="${cls}" role="option" id="history-opt-${optionIndex}" data-index="${optionIndex}" data-url="${escapeHtml(entry.url)}" aria-selected="${ariaSelected}">
            ${faviconHtml}
            <div class="history-option-text">
                <span class="history-option-title">${titleHtml}</span>
                <span class="history-option-url">${urlHtml}</span>
            </div>
            ${renderHistoryActionButtons()}
        </div>`;
        optionIndex++;
    });

    if (ranked.length > 0) {
        html += '<div class="history-clear" role="button">Clear history</div>';
    }
    dropdown.innerHTML = html;

    // Swap broken favicons for the placeholder
    dropdown.querySelectorAll('.history-option-favicon').forEach(img => {
        img.addEventListener('error', () => {
            const placeholder = document.createElement('div');
            placeholder.className = 'history-option-favicon-placeholder';
            placeholder.textContent = '🌐';
            img.replaceWith(placeholder);
        });
    });

    // Option body: navigate on mousedown (preventDefault keeps URL bar focus).
    // We let action-button clicks fall through — they have their own handlers.
    dropdown.querySelectorAll('.history-option').forEach(opt => {
        opt.addEventListener('mousedown', (e) => {
            if (e.target.closest('.history-action-btn')) return;
            e.preventDefault();
            navigateTo(opt.dataset.url);
        });
    });

    // Action buttons: mousedown preventDefault keeps dropdown open on mouse click;
    // click handles both mouse and keyboard (Enter / Space) activation.
    dropdown.querySelectorAll('.history-action-btn').forEach(btn => {
        btn.addEventListener('mousedown', (e) => e.preventDefault());
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const opt = btn.closest('.history-option');
            if (opt) handleHistoryAction(btn.dataset.action, opt.dataset.url);
        });
    });

    const clearBtn = dropdown.querySelector('.history-clear');
    if (clearBtn) {
        clearBtn.addEventListener('mousedown', (e) => {
            e.preventDefault();
            clearHistory();
        });
    }
}

function showHistoryDropdown() {
    const dropdown = document.getElementById('urlHistoryDropdown');
    const urlBar = document.getElementById('urlBar');
    historyActiveIndex = -1;
    renderHistoryDropdown(urlBar === document.activeElement ? '' : '');
    dropdown.classList.add('show');
    urlBar.setAttribute('aria-expanded', 'true');
    historyDropdownOpen = true;
    document.addEventListener('click', onHistoryOutsideClick, true);
}

function dismissHistoryDropdown() {
    const dropdown = document.getElementById('urlHistoryDropdown');
    const urlBar = document.getElementById('urlBar');
    dropdown.classList.remove('show');
    urlBar.setAttribute('aria-expanded', 'false');
    urlBar.removeAttribute('aria-activedescendant');
    historyDropdownOpen = false;
    historyActiveIndex = -1;
    document.removeEventListener('click', onHistoryOutsideClick, true);
}

function onHistoryOutsideClick(e) {
    const wrapper = document.getElementById('urlBarWrapper');
    if (!wrapper.contains(e.target)) {
        dismissHistoryDropdown();
    }
}

// --- Keyboard handler ---

let historyTypedValue = '';  // What the user actually typed — restored when arrowing past -1

function syncUrlBarToActive() {
    const urlBar = document.getElementById('urlBar');
    const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
    if (historyActiveIndex === -1) {
        urlBar.value = historyTypedValue;
    } else if (options[historyActiveIndex]) {
        urlBar.value = options[historyActiveIndex].dataset.url;
    }
}

(function setupUrlBarKeyboard() {
    const urlBar = document.getElementById('urlBar');

    urlBar.addEventListener('keydown', (e) => {
        // Skip while an IME is composing (CJK / emoji input). Enter or ArrowDown
        // during composition would commit the wrong thing. keyCode 229 is the
        // IE/WebKit fallback when isComposing isn't set.
        if (e.isComposing || e.keyCode === 229) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!historyDropdownOpen) {
                historyTypedValue = urlBar.value;
                showHistoryDropdown();
            } else {
                const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
                if (options.length > 0) {
                    if (historyActiveIndex === -1) historyTypedValue = urlBar.value;
                    historyActiveIndex = Math.min(historyActiveIndex + 1, options.length - 1);
                    updateHistoryActiveOption();
                    syncUrlBarToActive();
                }
            }
        } else if (e.key === 'ArrowUp') {
            if (historyDropdownOpen) {
                e.preventDefault();
                historyActiveIndex = Math.max(historyActiveIndex - 1, -1);
                updateHistoryActiveOption();
                syncUrlBarToActive();
            }
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (historyDropdownOpen && historyActiveIndex >= 0) {
                const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
                if (options[historyActiveIndex]) {
                    navigateTo(options[historyActiveIndex].dataset.url);
                }
            } else {
                navigateTo(urlBar.value);
            }
        } else if (e.key === 'Escape') {
            if (historyDropdownOpen) {
                e.preventDefault();
                e.stopPropagation();
                dismissHistoryDropdown();
                urlBar.value = displayUrl(currentUrl, false);
                // Keep focus — second Escape (global handler) will blur
            }
        } else if (historyDropdownOpen && historyActiveIndex >= 0 &&
                   (e.key === 'Tab' || e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
            // Only enters the action-button row when the user has already
            // picked a suggestion via ArrowUp/ArrowDown. Without that guard,
            // Tab while typing would steal focus into a button unexpectedly.
            const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
            const opt = options[historyActiveIndex];
            if (!opt) return;
            const actions = opt.querySelectorAll('.history-action-btn');
            if (actions.length === 0) return; // search row — fall through to default Tab
            e.preventDefault();
            const backward = e.shiftKey || e.key === 'ArrowLeft';
            (backward ? actions[actions.length - 1] : actions[0]).focus();
        } else if (e.key === 'Delete' && e.shiftKey) {
            // Chrome/Firefox convention: Shift+Delete removes the highlighted
            // history entry from the dropdown (not the search fallback row).
            if (historyDropdownOpen && historyActiveIndex >= 0) {
                const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
                const opt = options[historyActiveIndex];
                if (opt && !opt.classList.contains('history-option-search')) {
                    e.preventDefault();
                    removeFromHistory(opt.dataset.url);
                    renderHistoryDropdown(urlBar.value);
                    // Clamp active index into the (possibly shorter) new list
                    const fresh = document.querySelectorAll('#urlHistoryDropdown .history-option');
                    historyActiveIndex = Math.min(historyActiveIndex, fresh.length - 1);
                    updateHistoryActiveOption();
                    syncUrlBarToActive();
                }
            }
        }
    });

    urlBar.addEventListener('input', () => {
        historyTypedValue = urlBar.value;
        if (!historyDropdownOpen) {
            showHistoryDropdown();
        }
        historyActiveIndex = -1;
        renderHistoryDropdown(urlBar.value);
    });

    // Dismiss when focus leaves the URL bar — unless it moved into the dropdown
    // (action buttons), in which case we want to keep the dropdown open so the
    // user can continue their keyboard flow.
    urlBar.addEventListener('blur', (e) => {
        if (!historyDropdownOpen) return;
        const dropdown = document.getElementById('urlHistoryDropdown');
        if (e.relatedTarget && dropdown.contains(e.relatedTarget)) return;
        dismissHistoryDropdown();
    });
})();

// Keyboard navigation inside the dropdown's action-button row.
// Tab / ArrowRight move to the next button, Shift+Tab / ArrowLeft to the
// previous. Past either end → return to the URL bar. Up/Down still move rows.
(function setupHistoryActionButtonKeyboard() {
    const dropdown = document.getElementById('urlHistoryDropdown');
    if (!dropdown) return;
    dropdown.addEventListener('keydown', (e) => {
        const btn = e.target.closest && e.target.closest('.history-action-btn');
        if (!btn) return;
        const urlBar = document.getElementById('urlBar');
        const opt = btn.closest('.history-option');
        if (!opt) return;
        const buttons = Array.from(opt.querySelectorAll('.history-action-btn'));
        const idx = buttons.indexOf(btn);

        const forward = e.key === 'ArrowRight' || (e.key === 'Tab' && !e.shiftKey);
        const backward = e.key === 'ArrowLeft' || (e.key === 'Tab' && e.shiftKey);

        if (forward) {
            // Keyboard trap: wrap around. The only way out is Up / Down / Esc.
            e.preventDefault();
            buttons[(idx + 1) % buttons.length].focus();
        } else if (backward) {
            e.preventDefault();
            buttons[(idx - 1 + buttons.length) % buttons.length].focus();
        } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
            const newIndex = e.key === 'ArrowDown'
                ? Math.min(historyActiveIndex + 1, options.length - 1)
                : Math.max(historyActiveIndex - 1, -1);
            // urlBar.focus() fires the focus handler in navigation.js, which
            // calls showHistoryDropdown() and resets historyActiveIndex to -1.
            // Set our intended index AFTER that so it isn't stomped.
            urlBar.focus();
            historyActiveIndex = newIndex;
            updateHistoryActiveOption();
            syncUrlBarToActive();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            urlBar.focus();
            dismissHistoryDropdown();
            urlBar.value = displayUrl(currentUrl, false);
        }
        // Enter/Space: let the default button click event fire (handled above)
    });
})();

function updateHistoryActiveOption() {
    const urlBar = document.getElementById('urlBar');
    const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
    options.forEach((opt, i) => {
        const isActive = i === historyActiveIndex;
        opt.classList.toggle('active', isActive);
        opt.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    if (historyActiveIndex >= 0 && options[historyActiveIndex]) {
        urlBar.setAttribute('aria-activedescendant', options[historyActiveIndex].id);
        options[historyActiveIndex].scrollIntoView({ block: 'nearest' });
    } else {
        urlBar.removeAttribute('aria-activedescendant');
    }
}


