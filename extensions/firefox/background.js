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

// Listen for tab updates to inject into new pages
browser.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete' && tab.active) {
        console.log('[Inspekt] Tab updated:', tab.url);
        activeTabs.add(tabId);
    }
});

// Listen for tab removal to clean up
browser.tabs.onRemoved.addListener((tabId) => {
    activeTabs.delete(tabId);
});

// Listen for tab activation
browser.tabs.onActivated.addListener((activeInfo) => {
    activeTabs.add(activeInfo.tabId);
});

// Listen for messages from content script
browser.runtime.onMessage.addListener((message, sender) => {
    console.log('[Inspekt] Message from content script:', message.type);

    if (message.type === 'EXECUTE_CODE') {
        // Execute code with CSP bypass
        return executeWithCSPBypass(sender.tab.id, message.code, message.requestId);
    }

    if (message.type === 'GET_STATUS') {
        return Promise.resolve({
            version: browser.runtime.getManifest().version,
            active: true,
            tabCount: activeTabs.size
        });
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

// Log extension initialization
console.log('[Inspekt Extension] Version:', browser.runtime.getManifest().version);
console.log('[Inspekt Extension] CSP bypass active - works on all websites!');
