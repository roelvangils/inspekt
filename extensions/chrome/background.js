/**
 * Inspekt - Background Service Worker (Chrome)
 *
 * This script runs in the extension background and handles:
 * - CSP bypass using scripting.executeScript API
 * - Message routing between content scripts and tabs
 * - Extension lifecycle management
 */

console.log('[Inspekt Extension] Background service worker loaded');

// Track which tabs have Zen Bridge active
const activeTabs = new Set();

// Listen for tab updates to inject into new pages
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.active) {
        console.log('[Inspekt] Tab updated:', tab.url);
        activeTabs.add(tabId);
    }
});

// Listen for tab removal to clean up
chrome.tabs.onRemoved.addListener((tabId) => {
    activeTabs.delete(tabId);
});

// Listen for tab activation
chrome.tabs.onActivated.addListener((activeInfo) => {
    activeTabs.add(activeInfo.tabId);
});

// Track WebSocket connection status per tab
const tabConnectionStatus = new Map();

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[Inspekt] Message from content script:', message.type);

    if (message.type === 'INJECT_MAIN_WORLD_VARS') {
        // Inject version variables into MAIN world
        injectMainWorldVars(sender.tab.id)
            .then(() => sendResponse({ ok: true }))
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'WS_STATUS_UPDATE') {
        // Update connection status and inject into main world
        // status can be: 'connecting', true (connected), or false (disconnected)
        const tabId = sender.tab.id;
        const status = message.connected;
        tabConnectionStatus.set(tabId, status);

        updateConnectionStatusInMainWorld(tabId, status)
            .then(() => sendResponse({ ok: true }))
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true;
    }

    if (message.type === 'EXECUTE_CODE') {
        // Execute code with CSP bypass
        executeWithCSPBypass(sender.tab.id, message.code, message.requestId)
            .then(sendResponse)
            .catch(error => {
                sendResponse({
                    ok: false,
                    result: null,
                    error: String(error),
                    requestId: message.requestId
                });
            });
        return true; // Keep channel open for async response
    }

    if (message.type === 'GET_STATUS') {
        sendResponse({
            version: chrome.runtime.getManifest().version,
            active: true,
            tabCount: activeTabs.size
        });
        return false;
    }

    if (message.type === 'COPY_IMAGE_TO_CLIPBOARD') {
        // Handle clipboard write from DevTools panel (which has restricted permissions)
        copyImageToClipboard(message.blob)
            .then(() => sendResponse({ ok: true }))
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'GET_COOKIES_ENHANCED') {
        // Retrieve detailed cookie information using chrome.cookies API
        getCookiesEnhanced(sender.tab.url)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }
});

/**
 * Copy image blob to clipboard via offscreen document
 * DevTools panels have restricted clipboard access, and service workers don't have ClipboardItem
 * So we use an offscreen document which has full DOM APIs
 */
async function copyImageToClipboard(dataUrl) {
    try {
        // Ensure offscreen document exists
        await setupOffscreenDocument();

        console.log('[Inspekt] Sending clipboard write request to offscreen document...');

        // Get the offscreen document context
        const offscreenContexts = await chrome.runtime.getContexts({
            contextTypes: ['OFFSCREEN_DOCUMENT'],
            documentUrls: [chrome.runtime.getURL('offscreen.html')]
        });

        if (offscreenContexts.length === 0) {
            throw new Error('Offscreen document not found');
        }

        // Send message directly to the offscreen document
        const response = await chrome.runtime.sendMessage({
            type: 'OFFSCREEN_COPY_IMAGE',
            dataUrl: dataUrl,
            target: 'offscreen'
        });

        console.log('[Inspekt] Response from offscreen:', response);

        if (!response || !response.success) {
            throw new Error(response?.error || 'Failed to copy via offscreen document');
        }

        console.log('[Inspekt] Image copied to clipboard via offscreen document');
    } catch (error) {
        console.error('[Inspekt] Failed to copy image to clipboard:', error);
        throw error;
    }
}

/**
 * Setup offscreen document for clipboard operations
 */
async function setupOffscreenDocument() {
    // Check if offscreen document already exists
    const existingContexts = await chrome.runtime.getContexts({
        contextTypes: ['OFFSCREEN_DOCUMENT'],
        documentUrls: [chrome.runtime.getURL('offscreen.html')]
    });

    if (existingContexts.length > 0) {
        return; // Already exists
    }

    // Create offscreen document
    await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['CLIPBOARD'],
        justification: 'Copy screenshots to clipboard from DevTools panel'
    });

    console.log('[Inspekt] Offscreen document created for clipboard operations');

    // Longer delay to ensure offscreen document is fully loaded and ready
    await new Promise(resolve => setTimeout(resolve, 300));
}

/**
 * Update WebSocket connection status in main world
 */
async function updateConnectionStatusInMainWorld(tabId, status) {
    try {
        await chrome.scripting.executeScript({
            target: { tabId: tabId },
            world: 'MAIN',
            func: (connectionStatus) => {
                // Status can be: 'connecting', true (connected), or false (disconnected)
                window.__INSPEKT_WS_CONNECTED__ = connectionStatus;
            },
            args: [status]
        });
    } catch (error) {
        console.error('[Inspekt] Failed to update connection status:', error);
    }
}

/**
 * Inject version variables into MAIN world
 * This must be done via background script because content scripts run in isolated world
 */
async function injectMainWorldVars(tabId) {
    try {
        await chrome.scripting.executeScript({
            target: { tabId: tabId },
            world: 'MAIN',
            func: () => {
                // Version and status variables
                window.__ZEN_BRIDGE_VERSION__ = '4.2.1';
                window.__ZEN_BRIDGE_EXTENSION__ = true;
                window.__ZEN_BRIDGE_CSP_BLOCKED__ = false;
                window.__INSPEKT_BRIDGE_VERSION__ = '4.2.1';
                window.__INSPEKT_BRIDGE_EXTENSION__ = true;
                window.__INSPEKT_WS_CONNECTED__ = false; // Will be updated by content script

                // DevTools integration
                if (typeof window.__ZEN_DEVTOOLS_MONITOR__ === 'undefined') {
                    window.__ZEN_DEVTOOLS_MONITOR__ = true;

                    window.zenStore = function(element) {
                        if (element && element.nodeType === 1) {
                            window.__ZEN_INSPECTED_ELEMENT__ = element;
                            const tag = element.tagName.toLowerCase();
                            const id = element.id ? '#' + element.id : '';
                            const cls = element.className && typeof element.className === 'string' ?
                                '.' + element.className.split(' ').filter(c => c).join('.') : '';
                            console.log('%c[Inspekt]%c ✓ Element stored: <' + tag + id + cls + '>',
                                'color: #0066ff; font-weight: bold', 'color: #00aa00');
                            console.log('[Inspekt] Run in terminal: zen inspected');
                            return 'Stored: <' + tag + id + cls + '>';
                        }
                        console.error('[Inspekt] ✗ Invalid element. Usage: zenStore($0)');
                        return 'ERROR: Please provide a valid element';
                    };

                    console.log('%c[Inspekt]%c DevTools integration ready',
                        'color: #0066ff; font-weight: bold', 'color: inherit');
                    console.log('[Inspekt] To capture inspected element:');
                    console.log('  1. Right-click element → Inspect');
                    console.log('  2. In DevTools Console: zenStore($0)');
                    console.log('  3. In terminal: zen inspected');
                    console.log('');
                    console.log('%c[Inspekt]%c Extension mode: CSP restrictions bypassed! ✓',
                        'color: #0066ff; font-weight: bold', 'color: #00aa00; font-weight: bold');
                }
            }
        });
        console.log('[Inspekt] Version variables and DevTools injected into MAIN world');
    } catch (error) {
        console.error('[Inspekt] Failed to inject variables:', error);
        throw error;
    }
}

/**
 * Execute JavaScript code with multi-tier CSP handling
 *
 * Tier 1: Try direct execution (fast, clean, works on most sites)
 * Tier 2: Fall back to script tag injection (works on strict CSP sites)
 */
async function executeWithCSPBypass(tabId, code, requestId) {
    try {
        // TIER 1: Try direct execution first (fast path)
        console.log('[Inspekt] Attempting direct execution...');

        const directResult = await executeDirectly(tabId, code, requestId);

        // Check if it failed due to CSP
        if (!directResult.ok && directResult.error &&
            (directResult.error.includes('EvalError') ||
             directResult.error.includes('Content Security Policy') ||
             directResult.error.includes('unsafe-eval'))) {

            console.log('[Inspekt] CSP detected, falling back to script tag injection');

            // TIER 2: Fall back to script tag injection
            return await executeViaScriptTag(tabId, code, requestId);
        }

        // Direct execution succeeded or failed for non-CSP reasons
        return directResult;

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
 * TIER 1: Direct execution using AsyncFunction
 * Fast and clean, works on sites without strict CSP
 */
async function executeDirectly(tabId, code, requestId) {
    try {
        const results = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            world: 'MAIN',
            func: async (codeToExecute) => {
                try {
                    // Try using AsyncFunction (blocked by strict CSP)
                    const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
                    const fn = new AsyncFunction('return (' + codeToExecute + ')');
                    let result = await fn();

                    // Handle nested promises
                    if (result && typeof result.then === 'function') {
                        result = await result;
                    }

                    return {
                        ok: true,
                        result: result,
                        error: null
                    };
                } catch (e) {
                    return {
                        ok: false,
                        result: null,
                        error: e.stack || String(e)
                    };
                }
            },
            args: [code]
        });

        if (results && results[0]) {
            const executionResult = await results[0].result;
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
        return {
            ok: false,
            result: null,
            error: String(error),
            requestId: requestId
        };
    }
}

/**
 * TIER 2: Script tag injection (CSP bypass)
 * Works on all sites including those with strict CSP
 * Uses direct code embedding (no eval/Function constructor)
 */
async function executeViaScriptTag(tabId, code, requestId) {
    try {
        const results = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            world: 'MAIN',
            func: (codeToExecute, resultId) => {
                return new Promise((resolve) => {
                    try {
                        // Create a script tag - extensions can inject these even with CSP
                        const script = document.createElement('script');

                        // CRITICAL: Embed the code DIRECTLY into the script tag's source
                        // The code becomes part of the static script content, NOT eval'd
                        // This completely bypasses CSP restrictions
                        script.textContent = `
                            (async function() {
                                try {
                                    // Execute user code directly (no eval, no Function constructor)
                                    // The code below is inserted as raw JavaScript source
                                    const __result__ = await (${codeToExecute});

                                    window['${resultId}'] = {
                                        ok: true,
                                        result: __result__,
                                        error: null
                                    };
                                } catch (e) {
                                    window['${resultId}'] = {
                                        ok: false,
                                        result: null,
                                        error: e.stack || String(e)
                                    };
                                }
                            })();
                        `;

                        // Inject the script (extension privilege allows this despite CSP)
                        (document.head || document.documentElement).appendChild(script);

                        // Poll for result
                        const startTime = Date.now();
                        const checkInterval = setInterval(() => {
                            if (window[resultId] !== undefined) {
                                clearInterval(checkInterval);
                                const result = window[resultId];
                                delete window[resultId];
                                script.remove();
                                resolve(result);
                            } else if (Date.now() - startTime > 30000) {
                                // 30 second timeout
                                clearInterval(checkInterval);
                                script.remove();
                                delete window[resultId];
                                resolve({
                                    ok: false,
                                    result: null,
                                    error: 'Execution timeout (30s)'
                                });
                            }
                        }, 10);

                    } catch (e) {
                        resolve({
                            ok: false,
                            result: null,
                            error: 'Script injection failed: ' + String(e)
                        });
                    }
                });
            },
            args: [code, `__inspektResult_${requestId}`]
        });

        if (results && results[0]) {
            const executionResult = await results[0].result;
            console.log('[Inspekt] Script tag execution successful');

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
        console.error('[Inspekt] Script tag execution error:', error);
        return {
            ok: false,
            result: null,
            error: String(error),
            requestId: requestId
        };
    }
}

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
 * Get detailed cookie information using chrome.cookies API
 * This provides much more metadata than document.cookie
 */
async function getCookiesEnhanced(url) {
    try {
        // Get all cookies for the current URL
        const cookies = await chrome.cookies.getAll({ url: url });

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
            apiUsed: 'chrome.cookies',
            origin: url,
            hostname: new URL(url).hostname
        };
    } catch (error) {
        console.error('[Inspekt] Cookie retrieval error:', error);
        throw new Error(`Failed to retrieve cookies: ${error.message}`);
    }
}

// Log extension initialization
console.log('[Inspekt Extension] Version:', chrome.runtime.getManifest().version);
console.log('[Inspekt Extension] CSP bypass active - works on all websites!');
