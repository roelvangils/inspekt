/**
 * Inspekt - Background Script
 *
 * This script runs in the extension background and handles:
 * - CSP bypass using tabs.executeScript API
 * - Message routing between content scripts and tabs
 * - Extension lifecycle management
 */

console.log('[Inspekt Extension] Background script loaded');

// VM detection: Check if running inside the Browser VM (Linux + Firefox)
const isVMEnvironment = navigator.userAgent.includes('Linux') &&
                        navigator.userAgent.includes('Firefox');
const BRIDGE_HTTP_PORT = isVMEnvironment ? 8767 : 8765;

if (isVMEnvironment) {
    console.log('[Inspekt Extension] VM environment detected - using bridge port', BRIDGE_HTTP_PORT);
}

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

    if (message.type === 'CHECK_SERVER_RUNNING') {
        // Proxy health check from popup (popups have restricted network access in Firefox)
        return checkServerRunning();
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

    if (message.type === 'NAVIGATE') {
        console.log('[Inspekt] NAVIGATE message received:', {
            url: message.url,
            requestId: message.requestId,
            useCallback: message.useCallback,
            timeout: message.timeout,
            bridgePort: message.bridgePort,
            senderTabId: sender.tab?.id
        });

        // =============================================================================
        // FIREFOX NAVIGATION - CRITICAL DESIGN DECISIONS
        // =============================================================================
        //
        // WHY WE ALWAYS USE CALLBACK MODE:
        // The content script (websocket-client.js) that sends this message will be
        // DESTROYED during page navigation. If we tried to return a response to it,
        // there would be nothing listening. Instead, we use "callback mode" where the
        // background script directly POSTs the navigation result to the bridge server.
        //
        // WHY WE GENERATE requestId IF NOT PROVIDED:
        // The content script sets requestId in websocket-client.js, but in some Firefox
        // versions (including Zen browser), the message properties can arrive as
        // undefined even when explicitly set. By generating a fallback requestId here,
        // we ensure navigation always works.
        //
        // WHY WE USE setTimeout():
        // Firefox can terminate async operations when the message handler returns.
        // Wrapping in setTimeout(fn, 0) ensures the async navigation runs independently
        // of the message handler lifecycle.
        //
        // See also: handleNavigation() for why we use polling instead of events.
        // =============================================================================

        // Always use callback mode for navigation (content script gets destroyed during navigation)
        // Generate requestId if not provided
        const tabId = sender.tab?.id;
        const navUrl = message.url;
        const waitFor = message.waitFor;
        const timeout = message.timeout || 30;
        const requestId = message.requestId || `nav-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const bridgePort = message.bridgePort || BRIDGE_HTTP_PORT;

        console.log('[Inspekt] Using callback mode for navigation:', { requestId, timeout, bridgePort });

        // Use setTimeout to ensure the async operation runs independently
        // of the message handler lifecycle (some browsers kill async tasks when handler returns)
        setTimeout(() => {
            console.log('[Inspekt] Starting navigation via setTimeout');
            handleNavigationWithCallback(tabId, navUrl, waitFor, timeout, requestId, bridgePort)
                .then(result => console.log('[Inspekt] Navigation callback completed:', result))
                .catch(err => console.error('[Inspekt] Navigation callback error:', err));
        }, 0);

        // Respond immediately - the actual result will be sent via HTTP callback
        return Promise.resolve({ ok: true, pending: true, message: 'Navigation started, result will be sent via callback' });
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

// ============================================================================
// NAVIGATION HANDLING
// ============================================================================
//
// CRITICAL: Why we use POLLING instead of EVENTS in Firefox
// ==========================================================
//
// In Chrome, browser.tabs.onUpdated events fire reliably even when registered
// inside a message handler. In Firefox (and Firefox-based browsers like Zen),
// these events often DON'T FIRE when the listener is added during message handling.
//
// This is likely due to:
// 1. Firefox's event loop differs from Chrome's
// 2. The listener registration may not complete before navigation starts
// 3. Firefox may garbage-collect listeners registered in certain contexts
//
// Our solution: Poll browser.tabs.get() every 250ms to check tab.status and tab.url.
// This is slightly less efficient but 100% reliable.
//
// IMPORTANT: Do NOT refactor this to use event listeners without testing on both
// Firefox and Zen browser. The polling approach was adopted after extensive debugging
// revealed that event-based detection fails intermittently in Firefox-based browsers.
//
// ============================================================================

/**
 * Navigate to a URL using browser.tabs.update()
 * Uses polling-based detection via browser.tabs.get() for reliable completion detection.
 * Note: Firefox's browser.tabs.onUpdated event is unreliable when registered from
 * message handlers, so we use polling instead.
 *
 * @param {number} tabId - The tab ID to navigate (or null for active tab)
 * @param {string} url - The URL to navigate to
 * @param {string|null} waitFor - Wait condition: 'load' or 'networkidle'
 * @param {number} timeout - Timeout in seconds (default 30)
 * @returns {Promise<{ok: boolean, url?: string, title?: string, error?: string}>}
 */
async function handleNavigation(tabId, url, waitFor, timeout = 30) {
    try {
        // Validate URL
        if (!url || (!url.startsWith('http://') && !url.startsWith('https://'))) {
            return {
                ok: false,
                error: 'URL must start with http:// or https://'
            };
        }

        // Get the tab to navigate (use active tab if not specified)
        let targetTabId = tabId;
        if (!targetTabId) {
            const [activeTab] = await browser.tabs.query({ active: true, currentWindow: true });
            if (!activeTab) {
                return { ok: false, error: 'No active tab found' };
            }
            targetTabId = activeTab.id;
        }

        // Get current URL before navigation (for same-origin detection)
        const initialTab = await browser.tabs.get(targetTabId);
        const initialUrl = initialTab.url;
        const targetUrl = new URL(url);

        console.log('[Inspekt] Starting navigation:', { from: initialUrl, to: url, timeout });

        return new Promise((resolve) => {
            const timeoutMs = timeout * 1000;
            const pollInterval = 250; // Check every 250ms
            let resolved = false;
            let timeoutId;
            let pollId;

            const cleanup = () => {
                if (timeoutId) clearTimeout(timeoutId);
                if (pollId) clearInterval(pollId);
            };

            const finish = (result) => {
                if (resolved) return;
                resolved = true;
                cleanup();
                resolve(result);
            };

            // Helper to normalize hostname (strip www.)
            // REASON: Many sites redirect www.example.com → example.com or vice versa.
            // Without normalization, github.com navigation would fail because it redirects
            // from www.github.com to github.com, causing a hostname mismatch.
            const normalizeHost = (host) => host.replace(/^www\./, '');
            const targetHost = normalizeHost(targetUrl.hostname);

            // Polling-based detection (more reliable in Firefox than onUpdated events)
            pollId = setInterval(async () => {
                try {
                    const tab = await browser.tabs.get(targetTabId);

                    // Debug log every few polls
                    console.log('[Inspekt] Poll check:', {
                        status: tab.status,
                        url: tab.url,
                        changed: tab.url !== initialUrl
                    });

                    // Check if navigation is complete and URL has changed
                    if (tab.status === 'complete' && tab.url !== initialUrl) {
                        try {
                            const currentUrl = new URL(tab.url);
                            const currentHost = normalizeHost(currentUrl.hostname);

                            // Success conditions:
                            // 1. Exact URL match, OR
                            // 2. Hostname matches target (with www normalization)
                            const exactMatch = tab.url === url;
                            const hostsMatch = currentHost === targetHost;

                            console.log('[Inspekt] URL check:', {
                                exactMatch,
                                hostsMatch,
                                currentHost,
                                targetHost
                            });

                            if (exactMatch || hostsMatch) {
                                // Handle networkidle wait
                                if (waitFor === 'networkidle') {
                                    console.log('[Inspekt] Waiting for network idle...');
                                    await new Promise(r => setTimeout(r, 500));
                                }

                                console.log('[Inspekt] Navigation complete (polling):', {
                                    targetUrl: url,
                                    finalUrl: tab.url,
                                    title: tab.title
                                });

                                finish({ ok: true, url: tab.url, title: tab.title });
                            }
                        } catch (e) {
                            // URL parse error - but page has changed, consider it success
                            console.log('[Inspekt] URL parse issue but page changed, considering success');
                            finish({ ok: true, url: tab.url, title: tab.title || '' });
                        }
                    }
                } catch (e) {
                    // Tab may not exist anymore, will be caught by timeout
                    console.log('[Inspekt] Tab query error during polling:', e.message);
                }
            }, pollInterval);

            // Timeout handler
            timeoutId = setTimeout(async () => {
                try {
                    const finalTab = await browser.tabs.get(targetTabId);
                    console.error('[Inspekt] Navigation timeout after', timeout, 's. Final URL:', finalTab.url);
                    finish({
                        ok: false,
                        error: `Navigation timed out after ${timeout}s. Tab is at: ${finalTab.url}`,
                        url: finalTab.url,
                        title: finalTab.title
                    });
                } catch (e) {
                    finish({
                        ok: false,
                        error: `Navigation timed out after ${timeout}s`
                    });
                }
            }, timeoutMs);

            // Start navigation
            browser.tabs.update(targetTabId, { url: url }).catch(err => {
                console.error('[Inspekt] browser.tabs.update failed:', err);
                finish({ ok: false, error: `browser.tabs.update failed: ${err.message}` });
            });
        });

    } catch (error) {
        console.error('[Inspekt] Navigation error:', error);
        return {
            ok: false,
            error: String(error.message || error)
        };
    }
}

/**
 * Handle navigation with direct HTTP callback to bridge server.
 * This bypasses the content script which gets destroyed during navigation.
 *
 * @param {number} tabId - The tab ID to navigate
 * @param {string} url - The URL to navigate to
 * @param {string|null} waitFor - Wait condition
 * @param {number} timeout - Timeout in seconds
 * @param {string} requestId - Request ID for the callback
 * @param {number} bridgePort - Bridge server port (uses BRIDGE_HTTP_PORT constant by default)
 */
async function handleNavigationWithCallback(tabId, url, waitFor, timeout, requestId, bridgePort = BRIDGE_HTTP_PORT) {
    console.log('[Inspekt] handleNavigationWithCallback:', { url, timeout, requestId, bridgePort });

    try {
        // Perform the navigation with timeout parameter
        const result = await handleNavigation(tabId, url, waitFor, timeout);

        // POST result directly to bridge server (bypasses destroyed content script)
        console.log('[Inspekt] POSTing callback to bridge:', `http://127.0.0.1:${bridgePort}/navigate/callback`);
        await fetch(`http://127.0.0.1:${bridgePort}/navigate/callback`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                requestId: requestId,
                response: result
            })
        });

        return result;
    } catch (error) {
        console.error('[Inspekt] Navigation with callback error:', error);

        // Try to notify bridge of failure
        try {
            await fetch(`http://127.0.0.1:${bridgePort}/navigate/callback`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    requestId: requestId,
                    response: { ok: false, error: String(error.message || error) }
                })
            });
        } catch (e) {
            console.error('[Inspekt] Failed to POST error callback:', e);
        }

        return { ok: false, error: String(error.message || error) };
    }
}

// ============================================================================
// SERVER HEALTH CHECK (for popup status display)
// ============================================================================

/**
 * Check if the Inspekt API server is running
 * This runs in the background script which has full network access
 */
async function checkServerRunning() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        const response = await fetch('http://127.0.0.1:8000/health', {
            method: 'GET',
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        return { running: response.ok };
    } catch (e) {
        // Network error, timeout, or server not running
        return { running: false };
    }
}

// Log extension initialization
console.log('[Inspekt Extension] Version:', browser.runtime.getManifest().version);
console.log('[Inspekt Extension] CSP bypass active - works on all websites!');
