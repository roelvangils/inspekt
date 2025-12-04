/**
 * Inspekt - Background Script
 *
 * This script runs in the extension background and handles:
 * - CSP bypass using tabs.executeScript API
 * - Message routing between content scripts and tabs
 * - Extension lifecycle management
 */

console.log('[Inspekt Extension] Background script loaded');

// Track which tabs have Inspekt active
const activeTabs = new Set();

// Track WebSocket connection status per tab
const tabConnectionStatus = new Map();

// Listen for tab updates to inject into new pages
browser.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete') {
        console.log('[Inspekt] Tab updated:', tab.url);
        activeTabs.add(tabId);

        // Inject console hooks when page loads (for console capture feature)
        if (tab.url?.startsWith('http')) {
            injectConsoleHooks(tabId);
        }

        // Update icon when page finishes loading
        await updateIconForTab(tabId, tab);
    }
});

// Listen for tab removal to clean up
browser.tabs.onRemoved.addListener((tabId) => {
    activeTabs.delete(tabId);
    tabConnectionStatus.delete(tabId);
});

// Listen for tab activation
browser.tabs.onActivated.addListener(async (activeInfo) => {
    activeTabs.add(activeInfo.tabId);

    // Update icon when switching tabs
    try {
        const tab = await browser.tabs.get(activeInfo.tabId);
        await updateIconForTab(activeInfo.tabId, tab);
    } catch (error) {
        console.error('[Inspekt] Error updating icon on tab activation:', error);
    }
});

// Listen for storage changes (permission updates)
browser.storage.onChanged.addListener(async (changes, areaName) => {
    if (areaName === 'sync') {
        // Update all tab icons when permissions or bypass status changes
        if (changes.inspekt_allowed_domains || changes.inspekt_temp_bypass) {
            console.log('[Inspekt] Permissions changed, updating all icons');
            await updateAllTabIcons();

            // Notify all tabs to re-check permissions and reconnect if needed
            // This enables commands to work immediately after adding a domain (no page refresh)
            const tabs = await browser.tabs.query({});
            for (const tab of tabs) {
                try {
                    await browser.tabs.sendMessage(tab.id, {
                        type: 'PERMISSIONS_CHANGED'
                    });
                } catch (e) {
                    // Tab may not have content script loaded (e.g., about: pages)
                }
            }
        }
    }
});

// Listen for messages from content script
browser.runtime.onMessage.addListener((message, sender) => {
    console.log('[Inspekt] Message from content script:', message.type);

    if (message.type === 'EXECUTE_CODE') {
        // Execute code with CSP bypass
        return executeWithCSPBypass(sender.tab.id, message.code, message.requestId);
    }

    if (message.type === 'WS_STATUS_UPDATE') {
        // Update connection status and inject into main world
        // status can be: 'connecting', true (connected), or false (disconnected)
        const tabId = sender.tab.id;
        const status = message.connected;
        tabConnectionStatus.set(tabId, status);

        return updateConnectionStatusInMainWorld(tabId, status)
            .then(() => ({ ok: true }))
            .catch(error => ({ ok: false, error: String(error) }));
    }

    if (message.type === 'GET_STATUS') {
        return Promise.resolve({
            version: browser.runtime.getManifest().version,
            active: true,
            tabCount: activeTabs.size
        });
    }

    if (message.type === 'GET_COOKIES_ENHANCED') {
        // Retrieve detailed cookie information using browser.cookies API
        return getCookiesEnhanced(sender.tab.url);
    }

    if (message.type === 'DOMAIN_ADD') {
        return handleDomainAdd(message.domain);
    }

    if (message.type === 'DOMAIN_REMOVE') {
        return handleDomainRemove(message.domain);
    }

    if (message.type === 'DOMAIN_LIST') {
        return handleDomainList();
    }

    if (message.type === 'DOMAIN_BYPASS') {
        return handleDomainBypass(message.duration);
    }

    if (message.type === 'SYNC_ALLOWED_DOMAINS') {
        return handleDomainSync(message.domains);
    }

    if (message.type === 'GET_CONSOLE_LOGS') {
        return getConsoleLogs(sender.tab.id);
    }

    if (message.type === 'CLEAR_CONSOLE_LOGS') {
        return clearConsoleLogs(sender.tab.id);
    }
});

/**
 * Execute JavaScript code with CSP bypass
 * Uses tabs.executeScript which bypasses CSP restrictions
 */
async function executeWithCSPBypass(tabId, code, requestId) {
    try {
        console.log('[Inspekt] Executing code in tab', tabId, 'with CSP bypass');

        // UNIVERSAL APPROACH: No detection, no branching
        // Works for expressions, statements, IIFEs, promises, everything
        // Strategy:
        // 1. Execute the code and assign to variable
        // 2. Check if result is a promise and await if needed
        // 3. Return the final result
        //
        // This avoids ALL parentheses matching issues!

        const wrappedCode = `
(async function() {
    try {
        // Execute code - use eval to ensure proper scoping
        const __inspektEval = eval;
        // IMPORTANT: Escape backslashes FIRST to avoid double-escaping
        let __inspektResult = __inspektEval(\`${code.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$')}\`);

        // If it's a promise, await it
        if (__inspektResult && typeof __inspektResult.then === 'function') {
            __inspektResult = await __inspektResult;
        }

        return { ok: true, result: __inspektResult, error: null };
    } catch (e) {
        return { ok: false, result: null, error: String(e.stack || e) };
    }
})();
        `;

        // Execute with CSP bypass
        const results = await browser.tabs.executeScript(tabId, {
            code: wrappedCode,
            runAt: 'document_idle'
        });

        if (results && results[0]) {
            const executionResult = results[0];
            console.log('[Inspekt] Execution successful');

            return {
                ok: executionResult.ok,
                result: executionResult.result,
                error: executionResult.error,
                requestId: requestId
            };
        }

        return {
            ok: false,
            result: null,
            error: 'No result returned from tab',
            requestId: requestId
        };

    } catch (error) {
        console.error('[Inspekt] Execution error:', error);
        return {
            ok: false,
            result: null,
            error: String(error),
            requestId: requestId
        };
    }
}

/**
 * Update WebSocket connection status in main world
 */
async function updateConnectionStatusInMainWorld(tabId, status) {
    try {
        await browser.tabs.executeScript(tabId, {
            code: `window.__INSPEKT_WS_CONNECTED__ = ${JSON.stringify(status)};`,
            runAt: 'document_idle'
        });
        console.log('[Inspekt] Updated connection status in main world:', status);
    } catch (error) {
        console.error('[Inspekt] Failed to update connection status in main world:', error);
        throw error;
    }
}

// ============================================================================
// COOKIE API ENHANCEMENTS
// ============================================================================

/**
 * Helper function to check if a string should be split into an array
 */
function splitDelimitedString(value) {
    // Check for pipe-separated values
    if (value.includes('|')) {
        return value.split('|').map(s => s.trim());
    }

    // Check for comma-separated values
    // Only split if there are multiple items (has commas)
    if (value.includes(',')) {
        const parts = value.split(',').map(s => s.trim());
        // Only treat as array if we have multiple non-empty parts
        if (parts.length > 1 && parts.every(p => p.length > 0)) {
            return parts;
        }
    }

    return null; // Not a delimited string
}

/**
 * Helper function to recursively transform values (including nested objects)
 */
function transformValueRecursive(obj) {
    if (obj === null || obj === undefined) {
        return obj;
    }

    // If it's an array, transform each element
    if (Array.isArray(obj)) {
        return obj.map(item => transformValueRecursive(item));
    }

    // If it's an object, transform each property
    if (typeof obj === 'object') {
        const result = {};
        for (const key in obj) {
            if (obj.hasOwnProperty(key)) {
                result[key] = transformValueRecursive(obj[key]);
            }
        }
        return result;
    }

    // If it's a string, check if it's delimited
    if (typeof obj === 'string') {
        const delimited = splitDelimitedString(obj);
        if (delimited) {
            return delimited;
        }
    }

    // Return as-is for other types (numbers, booleans, etc.)
    return obj;
}

/**
 * Helper function to transform cookie values (parse JSON, split delimited strings)
 */
function transformValue(value) {
    // Try to parse as JSON first
    try {
        const parsed = JSON.parse(value);
        // Recursively transform to handle nested delimited strings
        return transformValueRecursive(parsed);
    } catch (e) {
        // Not valid JSON, check for delimited values at top level
        const delimited = splitDelimitedString(value);
        if (delimited) {
            return delimited;
        }

        // Return as plain string
        return value;
    }
}

/**
 * Get detailed cookie information using browser.cookies API
 * This provides much more metadata than document.cookie
 */
async function getCookiesEnhanced(url) {
    try {
        // Get all cookies for the current URL
        const cookies = await browser.cookies.getAll({ url: url });

        // Extract current domain from URL for party detection
        const currentDomain = new URL(url).hostname;

        // Enhance each cookie with calculated fields
        const enhancedCookies = cookies.map(cookie => {
            const currentTime = Date.now();

            // Calculate cookie size
            const size = cookie.name.length + cookie.value.length;

            // Determine cookie type
            const type = cookie.session ? 'session' : 'persistent';

            // Convert expiration to ISO string (if persistent cookie)
            const expires = cookie.expirationDate
                ? new Date(cookie.expirationDate * 1000).toISOString()
                : null;

            // Determine first-party vs third-party
            const cookieDomain = cookie.domain.startsWith('.')
                ? cookie.domain.substring(1)
                : cookie.domain;
            const isFirstParty = currentDomain.includes(cookieDomain) ||
                                 cookieDomain.includes(currentDomain);
            const party = isFirstParty ? 'first-party' : 'third-party';

            // Parse JSON value
            const valueParsed = transformValue(cookie.value);

            // Time-based properties
            const expiresInMs = cookie.expirationDate ? (cookie.expirationDate * 1000 - currentTime) : null;
            const expiresInMinutes = expiresInMs !== null ? Math.floor(expiresInMs / (1000 * 60)) : null;
            const expiresInHours = expiresInMs !== null ? Math.floor(expiresInMs / (1000 * 60 * 60)) : null;
            const expiresInDays = expiresInMs !== null ? Math.floor(expiresInMs / (1000 * 60 * 60 * 24)) : null;
            const expiresAt = cookie.expirationDate ? new Date(cookie.expirationDate * 1000).toLocaleString() : null;

            // Status flags
            const isExpired = cookie.expirationDate ? (cookie.expirationDate * 1000 < currentTime) : false;
            const isExpiringSoon = expiresInHours !== null && expiresInHours < 24 && expiresInHours > 0;
            const isPersistent = !cookie.session;
            const isLongLived = expiresInDays !== null && expiresInDays > 365;

            // Size properties
            const sizeBytes = new Blob([cookie.name + cookie.value]).size;
            const isLarge = sizeBytes > 4096;

            // Security properties
            const securityFlags = [];
            if (cookie.secure) securityFlags.push('secure');
            if (cookie.httpOnly) securityFlags.push('httpOnly');
            if (cookie.sameSite && cookie.sameSite !== 'no_restriction') securityFlags.push('sameSite');

            let securityScore = 0;
            if (cookie.secure) securityScore += 25;
            if (cookie.httpOnly) securityScore += 25;
            if (cookie.sameSite === 'strict') securityScore += 25;
            else if (cookie.sameSite === 'lax') securityScore += 15;
            if (party === 'first-party') securityScore += 10;

            const isSecure = cookie.secure && cookie.httpOnly && cookie.sameSite !== 'no_restriction';

            // Domain properties
            const isWildcard = cookie.domain.startsWith('.');
            const scope = isWildcard ? 'subdomain' : 'exact';

            return {
                ...cookie,
                // Parsed value
                valueParsed: valueParsed,
                // Existing properties
                size: size,
                type: type,
                expires: expires,
                party: party,
                // Time-based
                expiresInMinutes: expiresInMinutes,
                expiresInHours: expiresInHours,
                expiresInDays: expiresInDays,
                expiresAt: expiresAt,
                // Status flags
                isExpired: isExpired,
                isExpiringSoon: isExpiringSoon,
                isPersistent: isPersistent,
                isLongLived: isLongLived,
                // Size
                sizeBytes: sizeBytes,
                isLarge: isLarge,
                // Security
                securityScore: securityScore,
                securityFlags: securityFlags,
                isSecure: isSecure,
                // Domain
                isWildcard: isWildcard,
                scope: scope
            };
        });

        return {
            ok: true,
            action: 'list',
            cookies: enhancedCookies,
            count: enhancedCookies.length,
            apiUsed: 'browser.cookies',
            origin: url,
            hostname: new URL(url).hostname
        };
    } catch (error) {
        console.error('[Inspekt] Cookie retrieval error:', error);
        return {
            ok: false,
            error: `Failed to retrieve cookies: ${error.message}`
        };
    }
}

/**
 * Domain management functions
 * These handle domain permission requests from the bridge server via WebSocket
 */

async function handleDomainAdd(domain) {
    try {
        const STORAGE_KEY = 'inspekt_allowed_domains';
        const result = await browser.storage.sync.get(STORAGE_KEY);
        const allowedDomains = result[STORAGE_KEY] || {};

        const alreadyExists = !!allowedDomains[domain];

        // Add domain with metadata
        allowedDomains[domain] = {
            addedAt: new Date().toISOString(),
            permanent: true
        };

        await browser.storage.sync.set({ [STORAGE_KEY]: allowedDomains });

        // Update icons for tabs with this domain
        await updateAllTabIcons();

        return {
            ok: true,
            domain: domain,
            already_exists: alreadyExists
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

async function handleDomainRemove(domain) {
    try {
        const STORAGE_KEY = 'inspekt_allowed_domains';
        const result = await browser.storage.sync.get(STORAGE_KEY);
        const allowedDomains = result[STORAGE_KEY] || {};

        const existed = !!allowedDomains[domain];

        if (allowedDomains[domain]) {
            delete allowedDomains[domain];
            await browser.storage.sync.set({ [STORAGE_KEY]: allowedDomains });
        }

        // Update icons for tabs with this domain
        await updateAllTabIcons();

        return {
            ok: true,
            domain: domain,
            not_found: !existed
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

async function handleDomainList() {
    try {
        const STORAGE_KEY = 'inspekt_allowed_domains';
        const result = await browser.storage.sync.get(STORAGE_KEY);
        const allowedDomains = result[STORAGE_KEY] || {};

        return {
            ok: true,
            domains: allowedDomains,
            count: Object.keys(allowedDomains).length
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

async function handleDomainBypass(duration) {
    try {
        const TEMP_BYPASS_KEY = 'inspekt_temp_bypass';

        // If duration is -1, just return current status without modifying
        if (duration === -1) {
            const result = await browser.storage.sync.get(TEMP_BYPASS_KEY);
            const bypass = result[TEMP_BYPASS_KEY];

            if (!bypass || !bypass.enabled) {
                return {
                    ok: true,
                    enabled: false
                };
            }

            // Check if expired
            const now = new Date();
            const expiresAt = new Date(bypass.expiresAt);

            if (now >= expiresAt) {
                // Expired, remove it
                await browser.storage.sync.remove(TEMP_BYPASS_KEY);
                await updateAllTabIcons();
                return {
                    ok: true,
                    enabled: false
                };
            }

            // Calculate remaining minutes
            const remainingMs = expiresAt.getTime() - now.getTime();
            const remainingMinutes = Math.ceil(remainingMs / (60 * 1000));

            return {
                ok: true,
                enabled: true,
                expiresAt: bypass.expiresAt,
                remainingMinutes: remainingMinutes
            };
        }

        if (duration === 0) {
            // Disable bypass
            await browser.storage.sync.remove(TEMP_BYPASS_KEY);

            // Update all tab icons
            await updateAllTabIcons();

            return {
                ok: true,
                enabled: false
            };
        }

        const now = new Date();
        const expiresAt = new Date(now.getTime() + duration * 60 * 1000);

        const bypass = {
            enabled: true,
            expiresAt: expiresAt.toISOString(),
            durationMinutes: duration
        };

        await browser.storage.sync.set({ [TEMP_BYPASS_KEY]: bypass });

        // Update all tab icons to show bypass state
        await updateAllTabIcons();

        return {
            ok: true,
            enabled: true,
            expiresAt: bypass.expiresAt,
            durationMinutes: duration
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

async function handleDomainSync(domains) {
    try {
        const STORAGE_KEY = 'inspekt_allowed_domains';

        // Replace entire domain list with the one from SQLite
        await browser.storage.sync.set({ [STORAGE_KEY]: domains });

        // Update icons for all tabs
        await updateAllTabIcons();

        return {
            ok: true,
            synced: Object.keys(domains).length
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

// ============================================================================
// CONSOLE HOOKS INJECTION (for console capture feature)
// ============================================================================

/**
 * Inject console hooks into page to capture console.log/error/warn/info/debug
 */
async function injectConsoleHooks(tabId) {
    try {
        await browser.tabs.executeScript(tabId, {
            code: `
                (function() {
                    // Don't re-inject if already hooked
                    if (window.__INSPEKT_CONSOLE_HOOKED__) return;
                    window.__INSPEKT_CONSOLE_HOOKED__ = true;

                    const buffer = [];
                    const MAX_MESSAGES = 1000;

                    ['log', 'error', 'warn', 'info', 'debug'].forEach(level => {
                        const original = console[level];
                        console[level] = function(...args) {
                            buffer.push({
                                level,
                                timestamp: new Date().toISOString(),
                                message: args.map(a => {
                                    try {
                                        return typeof a === 'string' ? a : JSON.stringify(a);
                                    } catch {
                                        return String(a);
                                    }
                                }).join(' ')
                            });
                            // Keep buffer size limited
                            if (buffer.length > MAX_MESSAGES) buffer.shift();
                            // Call original console method
                            return original.apply(console, args);
                        };
                    });

                    // Store buffer reference for retrieval
                    window.__INSPEKT_CONSOLE_LOGS__ = buffer;
                })();
            `,
            runAt: 'document_idle'
        });
        console.log('[Inspekt] Console hooks injected for tab:', tabId);
    } catch (error) {
        // Silently fail for restricted pages (about:, moz-extension:, etc.)
        console.log('[Inspekt] Could not inject console hooks:', error.message);
    }
}

/**
 * Get console logs from page
 */
async function getConsoleLogs(tabId) {
    try {
        const results = await browser.tabs.executeScript(tabId, {
            code: `
                (function() {
                    const logs = window.__INSPEKT_CONSOLE_LOGS__ || [];
                    return {
                        ok: true,
                        entries: logs,
                        count: logs.length,
                        hooked: !!window.__INSPEKT_CONSOLE_HOOKED__
                    };
                })();
            `,
            runAt: 'document_idle'
        });

        if (results && results[0]) {
            return results[0];
        }

        return {
            ok: false,
            error: 'No result returned from tab'
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

/**
 * Clear console logs buffer in page
 */
async function clearConsoleLogs(tabId) {
    try {
        const results = await browser.tabs.executeScript(tabId, {
            code: `
                (function() {
                    if (window.__INSPEKT_CONSOLE_LOGS__) {
                        window.__INSPEKT_CONSOLE_LOGS__.length = 0;
                        return { ok: true, message: 'Console buffer cleared' };
                    }
                    return { ok: true, message: 'No console buffer to clear' };
                })();
            `,
            runAt: 'document_idle'
        });

        if (results && results[0]) {
            return results[0];
        }

        return {
            ok: false,
            error: 'No result returned from tab'
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

// ============================================================================
// ICON STATE MANAGEMENT
// ============================================================================

/**
 * Icon states for visual feedback
 */
const ICON_STATES = {
    DEFAULT: 'default',
    ALLOWED: 'allowed',
    BYPASS: 'bypass',
    CONNECTING: 'connecting'
};

/**
 * Determine the appropriate icon state for a tab
 */
async function determineIconState(tabId, tab) {
    try {
        // Skip non-http(s) URLs
        if (!tab.url || (!tab.url.startsWith('http://') && !tab.url.startsWith('https://'))) {
            return { state: ICON_STATES.DEFAULT };
        }

        const domain = new URL(tab.url).hostname;

        // 1. Check temp bypass first (highest priority)
        const bypassStatus = await getTempBypassStatus();
        if (bypassStatus.enabled) {
            return {
                state: ICON_STATES.BYPASS,
                data: { minutes: bypassStatus.remainingMinutes }
            };
        }

        // 2. Check if domain is allowed
        const allowed = await checkDomainAllowed(domain);
        if (allowed) {
            return { state: ICON_STATES.ALLOWED };
        }

        // 3. Check connection status
        const wsConnected = tabConnectionStatus.get(tabId);
        if (wsConnected === 'connecting') {
            return { state: ICON_STATES.CONNECTING };
        }

        // 4. Default state
        return { state: ICON_STATES.DEFAULT };
    } catch (error) {
        console.error('[Inspekt] Error determining icon state:', error);
        return { state: ICON_STATES.DEFAULT };
    }
}

/**
 * Helper to check if domain is allowed using the permission system
 */
async function checkDomainAllowed(domain) {
    try {
        const result = await browser.storage.sync.get('inspekt_allowed_domains');
        const allowedDomains = result['inspekt_allowed_domains'] || {};

        // Check each allowed domain for match (including subdomains)
        for (const allowedDomain of Object.keys(allowedDomains)) {
            if (matchesDomain(domain, allowedDomain)) {
                return true;
            }
        }

        return false;
    } catch (error) {
        console.error('[Inspekt] Error checking domain:', error);
        return false;
    }
}

/**
 * Helper for subdomain matching (same logic as permissions.js)
 */
function matchesDomain(requestedDomain, allowedDomain) {
    if (requestedDomain === allowedDomain) {
        return true;
    }

    if (requestedDomain.endsWith('.' + allowedDomain)) {
        return true;
    }

    if (allowedDomain === 'localhost' && requestedDomain.startsWith('localhost:')) {
        return true;
    }

    const requestedParts = requestedDomain.split(':');
    const allowedParts = allowedDomain.split(':');
    if (requestedParts[0] === allowedParts[0]) {
        return true;
    }

    return false;
}

/**
 * Helper to get temp bypass status
 */
async function getTempBypassStatus() {
    try {
        const result = await browser.storage.sync.get('inspekt_temp_bypass');
        const bypass = result['inspekt_temp_bypass'];

        if (!bypass || !bypass.enabled) {
            return { enabled: false };
        }

        const now = new Date().getTime();
        const expiresAt = new Date(bypass.expiresAt).getTime();

        if (now >= expiresAt) {
            return { enabled: false };
        }

        const remainingMs = expiresAt - now;
        const remainingMinutes = Math.ceil(remainingMs / (60 * 1000));

        return {
            enabled: true,
            remainingMinutes: remainingMinutes
        };
    } catch (error) {
        console.error('[Inspekt] Error getting bypass status:', error);
        return { enabled: false };
    }
}

/**
 * Main function to update icon for a specific tab
 */
async function updateIconForTab(tabId, tab) {
    try {
        const { state, data } = await determineIconState(tabId, tab);

        switch (state) {
            case ICON_STATES.ALLOWED:
                await setAllowedIcon(tabId);
                break;
            case ICON_STATES.BYPASS:
                await setBypassIcon(tabId, data.minutes);
                break;
            case ICON_STATES.CONNECTING:
                await setConnectingIcon(tabId);
                break;
            case ICON_STATES.DEFAULT:
            default:
                await setDefaultIcon(tabId);
                break;
        }
    } catch (error) {
        console.error('[Inspekt] Error updating icon:', error);
    }
}

/**
 * Update icons for all open tabs
 */
async function updateAllTabIcons() {
    try {
        const tabs = await browser.tabs.query({});
        for (const tab of tabs) {
            await updateIconForTab(tab.id, tab);
        }
    } catch (error) {
        console.error('[Inspekt] Error updating all icons:', error);
    }
}

/**
 * Set icon to "allowed" state (green checkmark)
 */
async function setAllowedIcon(tabId) {
    await browser.browserAction.setBadgeText({ tabId, text: '✓' });
    await browser.browserAction.setBadgeBackgroundColor({ tabId, color: '#00AA00' });
}

/**
 * Set icon to "bypass" state (orange with minutes or unlock)
 */
async function setBypassIcon(tabId, minutes) {
    const text = minutes > 99 ? '🔓' : String(minutes);
    await browser.browserAction.setBadgeText({ tabId, text });
    await browser.browserAction.setBadgeBackgroundColor({ tabId, color: '#FF9800' });
}

/**
 * Set icon to "connecting" state (yellow with dots)
 */
async function setConnectingIcon(tabId) {
    await browser.browserAction.setBadgeText({ tabId, text: '...' });
    await browser.browserAction.setBadgeBackgroundColor({ tabId, color: '#FFEB3B' });
}

/**
 * Set icon to default state (no badge)
 */
async function setDefaultIcon(tabId) {
    await browser.browserAction.setBadgeText({ tabId, text: '' });
}

// Log extension initialization
console.log('[Inspekt Extension] Version:', browser.runtime.getManifest().version);
console.log('[Inspekt Extension] CSP bypass active - works on all websites!');
