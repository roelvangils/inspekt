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

// Tab switching
document.addEventListener('click', (e) => {
    const tab = e.target.closest('.page-info-tab');
    if (!tab) return;
    pageInfoActiveTab = tab.dataset.tab;
    document.querySelectorAll('.page-info-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === pageInfoActiveTab);
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

function renderHistoryDropdown(filter) {
    const dropdown = document.getElementById('urlHistoryDropdown');
    const lowerFilter = (filter || '').toLowerCase();
    const filtered = lowerFilter
        ? visitedHistory.filter(e =>
            e.url.toLowerCase().includes(lowerFilter) ||
            e.title.toLowerCase().includes(lowerFilter))
        : visitedHistory;

    if (filtered.length === 0 && visitedHistory.length === 0) {
        dropdown.innerHTML = '<div class="history-empty">No history yet</div>';
        return;
    }

    if (filtered.length === 0) {
        dropdown.innerHTML = '<div class="history-empty">No matches</div>';
        return;
    }

    let html = '';
    filtered.forEach((entry, i) => {
        const activeClass = i === historyActiveIndex ? ' active' : '';
        const titleHtml = highlightMatch(entry.title || entry.url, filter);
        const urlHtml = highlightMatch(stripScheme(entry.url), filter);
        html += `<div class="history-option${activeClass}" role="option" data-index="${i}" data-url="${escapeHtml(entry.url)}">
            <span class="history-option-title">${titleHtml}</span>
            <span class="history-option-url">${urlHtml}</span>
        </div>`;
    });
    html += '<div class="history-clear" role="button">Clear history</div>';
    dropdown.innerHTML = html;

    // Attach click handlers
    dropdown.querySelectorAll('.history-option').forEach(opt => {
        opt.addEventListener('mousedown', (e) => {
            e.preventDefault(); // Prevent blur
            navigateTo(opt.dataset.url);
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

(function setupUrlBarKeyboard() {
    const urlBar = document.getElementById('urlBar');

    urlBar.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (!historyDropdownOpen) {
                showHistoryDropdown();
            } else {
                const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
                if (options.length > 0) {
                    historyActiveIndex = Math.min(historyActiveIndex + 1, options.length - 1);
                    updateHistoryActiveOption();
                }
            }
        } else if (e.key === 'ArrowUp') {
            if (historyDropdownOpen) {
                e.preventDefault();
                historyActiveIndex = Math.max(historyActiveIndex - 1, -1);
                updateHistoryActiveOption();
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
        }
    });

    urlBar.addEventListener('input', () => {
        if (!historyDropdownOpen) {
            showHistoryDropdown();
        }
        historyActiveIndex = -1;
        renderHistoryDropdown(urlBar.value);
    });
})();

function updateHistoryActiveOption() {
    const options = document.querySelectorAll('#urlHistoryDropdown .history-option');
    options.forEach((opt, i) => {
        opt.classList.toggle('active', i === historyActiveIndex);
    });
    // Scroll active option into view
    if (historyActiveIndex >= 0 && options[historyActiveIndex]) {
        options[historyActiveIndex].scrollIntoView({ block: 'nearest' });
    }
}


