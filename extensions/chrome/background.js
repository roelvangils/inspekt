/**
 * Inspekt - Background Service Worker (Chrome)
 *
 * This script runs in the extension background and handles:
 * - CSP bypass using scripting.executeScript API
 * - Message routing between content scripts and tabs
 * - Extension lifecycle management
 */

console.log('[Inspekt Extension] Background service worker loaded');

// Re-inject content scripts when extension is installed or updated
// This ensures content scripts are available without requiring page refresh
chrome.runtime.onInstalled.addListener(async (details) => {
    console.log('[Inspekt] Extension installed/updated:', details.reason);

    if (details.reason === 'install' || details.reason === 'update') {
        // Get all open tabs
        const tabs = await chrome.tabs.query({});

        for (const tab of tabs) {
            // Only inject into http/https pages (not chrome://, about:, etc.)
            if (tab.url?.startsWith('http')) {
                try {
                    // Inject content scripts
                    await chrome.scripting.executeScript({
                        target: { tabId: tab.id },
                        files: ['permissions.js', 'content.js', 'modules/hidden-elements.js']
                    });
                    console.log('[Inspekt] Re-injected content scripts into tab:', tab.id, tab.url);
                } catch (e) {
                    // Ignore errors for tabs we can't access
                    console.log('[Inspekt] Could not inject into tab:', tab.id, e.message);
                }
            }
        }
    }
});

// VM detection: Check if running inside the Browser VM (Linux + Chromium)
// In the VM, the bridge runs on port 8767 (HTTP) / 8768 (WebSocket) instead of 8765 / 8766
const isVMEnvironment = navigator.userAgent.includes('Linux') &&
                        (navigator.userAgent.includes('Chromium') || navigator.userAgent.includes('Chrome'));
const BRIDGE_HTTP_PORT = isVMEnvironment ? 8767 : 8765;
const BRIDGE_HTTP_URL = `http://127.0.0.1:${BRIDGE_HTTP_PORT}`;

if (isVMEnvironment) {
    console.log('[Inspekt Extension] VM environment detected - using bridge port', BRIDGE_HTTP_PORT);
}

// Track which tabs have Inspekt active
const activeTabs = new Set();

// Track which tabs have throttle prevention enabled
const throttlePreventionTabs = new Set();

// Replay mode state (stored in memory, cleared when extension restarts)
let replayModeEnabled = false;
let replayVisualScript = null;

// Track DevTools connections for HAR requests
const devToolsConnections = new Map();
const pendingHARRequests = new Map();

// CDP Dialog Interception state
// When enabled, intercepts alert/confirm/prompt via Chrome DevTools Protocol
const dialogInterception = {
    enabled: false,
    tabId: null,
    debuggerAttached: false,
    queue: [],  // Array of { type: 'alert'|'confirm'|'prompt', message: string, result: any }
    processing: false,  // Mutex to prevent race conditions with rapid dialogs
};

// Event queue for sequential CDP dialog processing
let cdpDialogEventQueue = [];
let processingCdpDialogEvents = false;

// Listen for tab updates to inject into new pages
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
    if (changeInfo.status === 'complete') {
        console.log('[Inspekt] Tab updated:', tab.url);
        activeTabs.add(tabId);

        // Inject console hooks when page loads (for console capture feature)
        if (tab.url?.startsWith('http')) {
            injectConsoleHooks(tabId);
        }

        // Inject visual script when replay mode is active
        if (replayModeEnabled && replayVisualScript && tab.url?.startsWith('http')) {
            console.log('[Inspekt] Tab completed - replay mode active, injecting visual script for:', tab.url);
            await injectReplayVisualScript(tabId);
        } else if (replayModeEnabled) {
            console.log('[Inspekt] Tab completed but NOT injecting:', {
                replayModeEnabled,
                hasScript: !!replayVisualScript,
                url: tab.url
            });
        }

        // Update icon when page finishes loading
        await updateIconForTab(tabId, tab);
    }
});

// Listen for tab removal to clean up
chrome.tabs.onRemoved.addListener((tabId) => {
    activeTabs.delete(tabId);
    tabConnectionStatus.delete(tabId);
    throttlePreventionTabs.delete(tabId);
});

// Listen for tab activation
chrome.tabs.onActivated.addListener(async (activeInfo) => {
    activeTabs.add(activeInfo.tabId);

    // Update icon when switching tabs
    try {
        const tab = await chrome.tabs.get(activeInfo.tabId);
        await updateIconForTab(activeInfo.tabId, tab);
    } catch (error) {
        console.error('[Inspekt] Error updating icon on tab activation:', error);
    }
});

// Listen for storage changes (permission updates)
chrome.storage.onChanged.addListener(async (changes, areaName) => {
    if (areaName === 'sync') {
        // Update all tab icons when permissions or bypass status changes
        if (changes.inspekt_allowed_domains || changes.inspekt_temp_bypass) {
            console.log('[Inspekt] Permissions changed, updating all icons');
            await updateAllTabIcons();

            // Notify all tabs to re-check permissions and reconnect if needed
            // This enables commands to work immediately after adding a domain (no page refresh)
            const tabs = await chrome.tabs.query({});
            for (const tab of tabs) {
                try {
                    await chrome.tabs.sendMessage(tab.id, {
                        type: 'PERMISSIONS_CHANGED'
                    });
                } catch (e) {
                    // Tab may not have content script loaded (e.g., chrome:// pages)
                }
            }
        }
    }
});

// Track WebSocket connection status per tab
const tabConnectionStatus = new Map();

// Listen for messages from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[Inspekt] Message from content script:', message.type);

    if (message.type === 'INJECT_MAIN_WORLD_VARS') {
        // Inject version variables into MAIN world
        injectMainWorldVars(sender.tab.id)
            .then(() => injectOverlayBusMain(sender.tab.id))
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

    if (message.type === 'DOMAIN_ADD') {
        // Add domain to allowed list
        handleDomainAdd(message.domain)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'DOMAIN_REMOVE') {
        // Remove domain from allowed list
        handleDomainRemove(message.domain)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'DOMAIN_LIST') {
        // List all allowed domains
        handleDomainList()
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'DOMAIN_BYPASS') {
        // Set temporary bypass
        handleDomainBypass(message.duration)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'SYNC_ALLOWED_DOMAINS') {
        // Sync domains from SQLite to browser storage
        handleDomainSync(message.domains)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'NAVIGATE') {
        console.log('[Inspekt] NAVIGATE message received:', {
            url: message.url,
            requestId: message.requestId,
            useCallback: message.useCallback,
            timeout: message.timeout,
            senderTabId: sender.tab?.id
        });
        // =============================================================================
        // CHROME NAVIGATION - DESIGN DECISIONS
        // =============================================================================
        //
        // Chrome uses a HYBRID approach for detecting navigation completion:
        // 1. PRIMARY: Event listener on chrome.tabs.onUpdated (efficient, event-driven)
        // 2. BACKUP: Polling via chrome.tabs.get() every 500ms (catches edge cases)
        //
        // Unlike Firefox, Chrome's onUpdated events ARE reliable when registered from
        // message handlers. However, we keep polling as a backup for edge cases like
        // certain redirects or slow-loading sites where events may be missed.
        //
        // CALLBACK vs STANDARD MODE:
        // - Callback mode: Background POSTs result to bridge server (used when content
        //   script will be destroyed, which is the case for cross-origin navigation)
        // - Standard mode: Returns result to content script (for same-page nav)
        //
        // The websocket-client.js sets requestId and useCallback=true for navigations.
        // =============================================================================

        // Navigate to URL using chrome.tabs.update() - this properly handles page navigation
        // The content script will be destroyed during navigation, so we use a callback
        // approach where background POSTs the result directly to the bridge server
        if (message.requestId && message.useCallback) {
            // Callback mode: POST result directly to bridge (content script won't survive)
            console.log('[Inspekt] Using callback mode for navigation, timeout:', message.timeout || 30);
            handleNavigationWithCallback(
                sender.tab?.id,
                message.url,
                message.waitFor,
                message.timeout || 30,
                message.requestId,
                message.bridgePort || BRIDGE_HTTP_PORT
            );
            // Respond immediately - the actual result will be sent via HTTP callback
            sendResponse({ ok: true, pending: true, message: 'Navigation started, result will be sent via callback' });
        } else {
            // Standard mode: return result to content script (for same-page navigations)
            handleNavigation(sender.tab?.id, message.url, message.waitFor, message.timeout || 30)
                .then(sendResponse)
                .catch(error => sendResponse({ ok: false, error: String(error) }));
        }
        return true; // Keep channel open for async response
    }

    if (message.type === 'HIDE_INSPECTOR_OVERLAY') {
        // Try to hide Chrome DevTools inspector overlay using CDP
        // Works when DevTools is closed; when DevTools is open, the overlay can't be hidden
        hideInspectorOverlay(sender.tab?.id)
            .then(() => sendResponse({ ok: true }))
            .catch(() => sendResponse({ ok: false }));  // Fail silently - DevTools is likely open
        return true; // Keep channel open for async response
    }

    if (message.type === 'CAPTURE_VISIBLE_TAB') {
        // Capture screenshot of visible tab (simple capture only, processing done in content script)
        chrome.tabs.captureVisibleTab(null, { format: 'png' })
            .then(dataUrl => sendResponse({ ok: true, dataUrl: dataUrl }))
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CAPTURE_FULL_PAGE') {
        // Capture full page screenshot using Chrome DevTools Protocol
        captureFullPageWithCDP(sender.tab.id, message.options)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CAPTURE_ELEMENT_CDP') {
        // Capture specific element using Chrome DevTools Protocol with clip region
        // Used for elements larger than viewport that can't be captured with captureVisibleTab
        captureElementWithCDP(sender.tab.id, message.options)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'FORCE_PSEUDO_STATE') {
        // Force CSS pseudo-state on element via CDP CSS.forcePseudoState
        forcePseudoStateViaCDP(sender.tab.id, message.state, message.selector)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CLEAR_PSEUDO_STATE') {
        // Clear forced CSS pseudo-state
        clearPseudoStateViaCDP(sender.tab.id)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'GET_HAR') {
        // Get HAR data from DevTools (if DevTools is open for this tab)
        getHARFromDevTools(sender.tab?.id || message.tabId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'GET_CONSOLE_LOGS') {
        // Get captured console logs from the page
        getConsoleLogs(sender.tab?.id || message.tabId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CLEAR_CONSOLE_LOGS') {
        // Clear the console logs buffer in the page
        clearConsoleLogs(sender.tab?.id || message.tabId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CSP_BYPASS_ENABLE') {
        // Enable CSP bypass for a domain using declarativeNetRequest
        handleCspBypassEnable(message.domain)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CSP_BYPASS_DISABLE') {
        // Disable CSP bypass for a domain
        handleCspBypassDisable(message.domain)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CSP_BYPASS_STATUS') {
        // Get CSP bypass status for a domain
        handleCspBypassStatus(message.domain)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CSP_BYPASS_GLOBAL') {
        // Enable/disable global CSP bypass for ALL domains
        handleCspBypassGlobal(message.enabled)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'CSP_BYPASS_GLOBAL_STATUS') {
        // Get global CSP bypass status
        getGlobalCspBypassStatus()
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'THROTTLE_PREVENTION_ENABLE') {
        // Enable throttle prevention for the current tab using CDP
        const tabId = message.tabId || sender.tab?.id;
        if (!tabId) {
            sendResponse({ ok: false, error: 'No tab ID provided' });
            return false;
        }
        handleThrottlePreventionEnable(tabId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'THROTTLE_PREVENTION_DISABLE') {
        // Disable throttle prevention for the current tab
        const tabId = message.tabId || sender.tab?.id;
        if (!tabId) {
            sendResponse({ ok: false, error: 'No tab ID provided' });
            return false;
        }
        handleThrottlePreventionDisable(tabId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'THROTTLE_PREVENTION_STATUS') {
        // Get throttle prevention status for the current tab
        const tabId = message.tabId || sender.tab?.id;
        if (!tabId) {
            sendResponse({ ok: false, error: 'No tab ID provided' });
            return false;
        }
        sendResponse({
            ok: true,
            enabled: throttlePreventionTabs.has(tabId)
        });
        return false;
    }

    if (message.type === 'REPLAY_MODE_ENABLE') {
        // Enable replay mode - store visual script and inject on page loads
        console.log('[Inspekt] REPLAY_MODE_ENABLE received, script length:', message.visualScript?.length);
        handleReplayModeEnable(message.visualScript, sender.tab?.id)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'REPLAY_MODE_DISABLE') {
        // Disable replay mode
        handleReplayModeDisable()
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'REPLAY_MODE_STATUS') {
        // Get replay mode status
        sendResponse({
            ok: true,
            enabled: replayModeEnabled,
            hasScript: !!replayVisualScript
        });
        return false;
    }

    // ========== CDP ACCESSIBILITY & EVENT LISTENERS ==========

    if (message.type === 'GET_EVENT_LISTENERS') {
        // Get event listeners via CDP DOMDebugger.getEventListeners
        // Requires debugger attachment
        getEventListenersViaCDP(sender.tab.id, message.source || 'inspected')
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'GET_ACCESSIBILITY_TREE') {
        // Get partial accessibility tree via CDP Accessibility.getPartialAXTree
        getAccessibilityTreeViaCDP(sender.tab.id, message.source || 'inspected', message.depth || 10)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'GET_AUTHORED_CSS') {
        // Get authored CSS values via CDP CSS.getMatchedStylesForNode
        getAuthoredCSSViaCDP(sender.tab.id, message.source || 'inspected', message.elementCount || 0)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    // ========== DOWNLOAD MONITORING ==========

    if (message.type === 'START_DOWNLOAD_MONITORING') {
        // Start monitoring downloads for a recording session
        startDownloadMonitoring(sender.tab?.id || message.tabId, message.sessionId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'STOP_DOWNLOAD_MONITORING') {
        // Stop monitoring downloads for a session
        const result = stopDownloadMonitoring(message.sessionId);
        sendResponse(result);
        return false;
    }

    if (message.type === 'GET_SESSION_DOWNLOADS') {
        // Get list of downloads captured during a session
        const result = getSessionDownloads(message.sessionId);
        sendResponse(result);
        return false;
    }

    if (message.type === 'GET_DOWNLOAD_FILE_CONTENT') {
        // Get download file content as base64
        getDownloadFileContent(message.downloadId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'ENABLE_DIALOG_INTERCEPTION') {
        // Enable CDP-level dialog interception for replay
        // queue: Array of { type: 'alert'|'confirm'|'prompt', result: any }
        enableDialogInterception(sender.tab.id, message.queue || [])
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'DISABLE_DIALOG_INTERCEPTION') {
        // Disable CDP dialog interception
        disableDialogInterception()
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'QUEUE_DIALOG_RESULT') {
        // Add a dialog result to the queue (for dynamic queueing during replay)
        if (dialogInterception.enabled) {
            dialogInterception.queue.push({
                type: message.dialogType,
                result: message.result
            });
            sendResponse({ ok: true, queueLength: dialogInterception.queue.length });
        } else {
            sendResponse({ ok: false, error: 'Dialog interception not enabled' });
        }
        return false;
    }

    if (message.type === 'START_SCREENCAST') {
        // Start CDP screencast for video recording
        console.log('[Inspekt] START_SCREENCAST received, tabId:', sender.tab.id, 'settings:', message.settings);
        startScreencast(sender.tab.id, message.settings, message.requestId)
            .then(response => {
                console.log('[Inspekt] START_SCREENCAST response:', response);
                sendResponse(response);
            })
            .catch(error => {
                console.error('[Inspekt] START_SCREENCAST error:', error);
                sendResponse({ ok: false, error: String(error) });
            });
        return true; // Keep channel open for async response
    }

    if (message.type === 'STOP_SCREENCAST') {
        // Stop CDP screencast
        stopScreencast(sender.tab.id, message.requestId)
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'START_SMOOTH_CAPTURE') {
        // Start timer-based smooth capture (constant FPS screenshots)
        console.log('[Inspekt] START_SMOOTH_CAPTURE received, settings:', message.settings);
        startSmoothCapture(sender.tab.id, message.settings)
            .then(response => {
                console.log('[Inspekt] START_SMOOTH_CAPTURE response:', response);
                sendResponse(response);
            })
            .catch(error => {
                console.error('[Inspekt] START_SMOOTH_CAPTURE error:', error);
                sendResponse({ ok: false, error: String(error) });
            });
        return true; // Keep channel open for async response
    }

    if (message.type === 'STOP_SMOOTH_CAPTURE') {
        // Stop timer-based smooth capture
        stopSmoothCapture()
            .then(sendResponse)
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    // ========== ZOOM LEVEL CONTROL ==========

    if (message.type === 'GET_ZOOM_LEVEL') {
        // Get the actual browser zoom level for a tab
        chrome.tabs.getZoom(sender.tab.id)
            .then(zoomFactor => sendResponse({ ok: true, zoomFactor }))
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    // ========== CDP KEY DISPATCH (for real keyboard events) ==========

    if (message.type === 'DISPATCH_KEY_CDP') {
        // Send a real key event via CDP Input.dispatchKeyEvent
        // This triggers :focus-visible unlike synthetic JavaScript events
        const { key, modifiers = [] } = message;
        dispatchKeyViaCDP(sender.tab.id, key, modifiers)
            .then(result => sendResponse({ ok: true, ...result }))
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }

    if (message.type === 'SET_ZOOM_LEVEL') {
        // Set the browser zoom level for a tab
        chrome.tabs.setZoom(sender.tab.id, message.zoomFactor)
            .then(() => sendResponse({ ok: true }))
            .catch(error => sendResponse({ ok: false, error: String(error) }));
        return true; // Keep channel open for async response
    }
});

// ============================================================================
// DEVTOOLS CONNECTION HANDLING (for HAR requests)
// ============================================================================

/**
 * Listen for connections from DevTools pages
 */
chrome.runtime.onConnect.addListener((port) => {
    // Check if this is a DevTools connection
    if (port.name.startsWith('devtools-')) {
        const tabId = parseInt(port.name.replace('devtools-', ''));
        console.log('[Inspekt] DevTools connected for tab:', tabId);

        // Store the connection
        devToolsConnections.set(tabId, port);

        // Handle messages from DevTools
        port.onMessage.addListener((message) => {
            console.log('[Inspekt] Message from DevTools:', message);

            if (message.type === 'HAR_RESPONSE') {
                // Resolve the pending HAR request
                const pending = pendingHARRequests.get(message.requestId);
                if (pending) {
                    if (message.error) {
                        pending.reject(new Error(message.error));
                    } else {
                        pending.resolve(message.data);
                    }
                    pendingHARRequests.delete(message.requestId);
                }
            }
        });

        // Clean up on disconnect
        port.onDisconnect.addListener(() => {
            console.log('[Inspekt] DevTools disconnected for tab:', tabId);
            devToolsConnections.delete(tabId);
        });
    }
});

/**
 * Request HAR data from DevTools for a specific tab
 */
async function getHARFromDevTools(tabId) {
    // Check if DevTools is connected for this tab
    const port = devToolsConnections.get(tabId);

    if (!port) {
        return {
            ok: false,
            error: 'DevTools not open for this tab. Open DevTools (F12) to capture full network data.',
            hint: 'The HAR export requires Chrome DevTools to be open. Use "inspekt network" for basic network data without DevTools.'
        };
    }

    // Generate a unique request ID
    const requestId = `har-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

    // Create a promise that will be resolved when DevTools responds
    return new Promise((resolve, reject) => {
        // Set up timeout
        const timeout = setTimeout(() => {
            pendingHARRequests.delete(requestId);
            reject(new Error('HAR request timed out'));
        }, 10000); // 10 second timeout

        // Store the promise callbacks
        pendingHARRequests.set(requestId, {
            resolve: (data) => {
                clearTimeout(timeout);
                resolve(data);
            },
            reject: (error) => {
                clearTimeout(timeout);
                reject(error);
            }
        });

        // Send request to DevTools
        try {
            port.postMessage({
                type: 'GET_HAR',
                requestId: requestId
            });
        } catch (error) {
            clearTimeout(timeout);
            pendingHARRequests.delete(requestId);
            reject(error);
        }
    });
}

/**
 * Copy image blob to clipboard via offscreen document
 * DevTools panels have restricted clipboard access, and service workers don't have ClipboardItem
 * So we use an offscreen document which has full DOM APIs
 */
async function copyImageToClipboard(dataUrl) {
    try {
        // Ensure offscreen document exists
        await setupOffscreenDocument();

        console.log('[Inspekt] Sending clipboard write request to offscreen document…');

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
                window.__INSPEKT_BRIDGE_VERSION__ = '4.2.1';
                window.__INSPEKT_BRIDGE_EXTENSION__ = true;
                window.__INSPEKT_WS_CONNECTED__ = false; // Will be updated by content script

                // DevTools integration
                if (typeof window.__INSPEKT_DEVTOOLS_MONITOR__ === 'undefined') {
                    window.__INSPEKT_DEVTOOLS_MONITOR__ = true;

                    window.inspektStore = function(element) {
                        if (element && element.nodeType === 1) {
                            window.__INSPEKT_INSPECTED_ELEMENT__ = element;
                            const tag = element.tagName.toLowerCase();
                            const id = element.id ? '#' + element.id : '';
                            const cls = element.className && typeof element.className === 'string' ?
                                '.' + element.className.split(' ').filter(c => c).join('.') : '';
                            console.log('%c[Inspekt]%c ✓ Element stored: <' + tag + id + cls + '>',
                                'color: #0066ff; font-weight: bold', 'color: #00aa00');
                            console.log('[Inspekt] Run in terminal: inspekt inspected');
                            return 'Stored: <' + tag + id + cls + '>';
                        }
                        console.error('[Inspekt] ✗ Invalid element. Usage: inspektStore($0)');
                        return 'ERROR: Please provide a valid element';
                    };

                    console.log('%c[Inspekt]%c DevTools integration ready',
                        'color: #0066ff; font-weight: bold', 'color: inherit');
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
 * Inject the Overlay Bus MAIN-world stub (window.InspektOverlayBus).
 *
 * The isolated-world counterpart (overlay-bus.js content script) holds the
 * WebSocket and observers; this stub is the MAIN-world API surface that
 * feature scripts (run_axe.js, inspect, recorder, …) call to emit overlay
 * data. Bridge is window.postMessage with INSPEKT_OVERLAY_* envelopes.
 *
 * Injected via files: rather than func: so the script is parsed once per
 * tab and gets standard CSP/source-map treatment. The path is mapped via
 * web_accessible_resources is unnecessary — chrome.scripting.executeScript
 * with files: works for extension-bundled files regardless of WAR.
 */
async function injectOverlayBusMain(tabId) {
    try {
        await chrome.scripting.executeScript({
            target: { tabId: tabId },
            world: 'MAIN',
            files: ['overlay-bus-main.js'],
        });
    } catch (error) {
        // Non-fatal — outside VM mode the bus producer never connects so
        // feature scripts fall through to the in-page DOM path. Log only at
        // debug level.
        console.debug('[Inspekt] overlay-bus-main injection skipped:', error?.message || error);
    }
}

/**
 * Execute JavaScript code with CSP handling
 *
 * Uses AsyncFunction for code execution. Works on most sites.
 * For strict CSP sites, CSP bypass is automatically enabled when:
 * 1. Yolo/bypass mode is active, OR
 * 2. User manually enables it in the popup
 */
async function executeWithCSPBypass(tabId, code, requestId) {
    try {
        console.log('[Inspekt] Executing code…');

        const result = await executeDirectly(tabId, code, requestId);

        // If execution failed due to CSP, try to auto-enable bypass if yolo mode is active
        if (!result.ok && result.error &&
            (result.error.includes('EvalError') ||
             result.error.includes('Content Security Policy') ||
             result.error.includes('unsafe-eval'))) {

            console.log('[Inspekt] CSP blocking execution');

            const tab = await chrome.tabs.get(tabId);
            const domain = new URL(tab.url).hostname;

            // Check if CSP bypass is already enabled
            const cspBypassEnabled = await isCspBypassEnabled(domain);

            if (!cspBypassEnabled) {
                // Check if yolo/bypass mode is active
                const bypassStatus = await getTempBypassStatus();

                if (bypassStatus.enabled) {
                    // Yolo mode is active - auto-enable CSP bypass for this domain
                    console.log('[Inspekt] Yolo mode active, auto-enabling CSP bypass for:', domain);

                    const cspResult = await handleCspBypassEnable(domain);

                    if (cspResult.ok) {
                        // CSP bypass enabled, but page needs refresh
                        return {
                            ok: false,
                            result: null,
                            error: 'CSP_AUTO_ENABLED: CSP bypass has been automatically enabled for this domain. Refreshing page…',
                            requestId: requestId,
                            cspBlocked: true,
                            autoEnabled: true,
                            domain: domain
                        };
                    }
                }

                // No yolo mode or auto-enable failed
                return {
                    ok: false,
                    result: null,
                    error: 'CSP_BLOCKED: This site has strict Content Security Policy. Enable "CSP Bypass" in the Inspekt popup for this domain, then refresh the page. Or run `inspekt yolo` to bypass all restrictions.',
                    requestId: requestId,
                    cspBlocked: true
                };
            }

            // CSP bypass is enabled but still failing - might be meta tag CSP
            return {
                ok: false,
                result: null,
                error: 'CSP_META_TAG: This site uses CSP via meta tag which cannot be bypassed. The site must be modified or use a different approach.',
                requestId: requestId,
                cspBlocked: true
            };
        }

        return result;

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
 * Check if CSP bypass is enabled for a domain
 */
async function isCspBypassEnabled(domain) {
    try {
        const result = await chrome.storage.sync.get('inspekt_csp_bypass_domains');
        const cspBypassDomains = result['inspekt_csp_bypass_domains'] || {};
        return !!cspBypassDomains[domain];
    } catch (error) {
        return false;
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
                    // Strip trailing semicolons to avoid syntax error in return wrapper
                    const cleanCode = codeToExecute.trim().replace(/;+$/, '');
                    const fn = new AsyncFunction('return (' + cleanCode + ')');
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

/**
 * Domain management functions
 * These handle domain permission requests from the bridge server via WebSocket
 */

async function handleDomainAdd(domain) {
    try {
        const STORAGE_KEY = 'inspekt_allowed_domains';
        const result = await chrome.storage.sync.get(STORAGE_KEY);
        const allowedDomains = result[STORAGE_KEY] || {};

        const alreadyExists = !!allowedDomains[domain];

        // Add domain with metadata
        allowedDomains[domain] = {
            addedAt: new Date().toISOString(),
            permanent: true
        };

        await chrome.storage.sync.set({ [STORAGE_KEY]: allowedDomains });

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
        const result = await chrome.storage.sync.get(STORAGE_KEY);
        const allowedDomains = result[STORAGE_KEY] || {};

        const existed = !!allowedDomains[domain];

        if (allowedDomains[domain]) {
            delete allowedDomains[domain];
            await chrome.storage.sync.set({ [STORAGE_KEY]: allowedDomains });
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
        const result = await chrome.storage.sync.get(STORAGE_KEY);
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
            const result = await chrome.storage.sync.get(TEMP_BYPASS_KEY);
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
                await chrome.storage.sync.remove(TEMP_BYPASS_KEY);
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
            await chrome.storage.sync.remove(TEMP_BYPASS_KEY);

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

        await chrome.storage.sync.set({ [TEMP_BYPASS_KEY]: bypass });

        // Update all tab icons to show bypass state
        await updateAllTabIcons();

        return {
            ok: true,
            enabled: true,
            expiresAt: bypass.expiresAt,
            durationMinutes: duration,
            remainingMinutes: duration
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
        await chrome.storage.sync.set({ [STORAGE_KEY]: domains });

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
// NAVIGATION HANDLING
// ============================================================================

/**
 * Navigate to a URL using chrome.tabs.update()
 * Uses hybrid detection: event-driven (primary) + polling (backup) for maximum reliability.
 *
 * @param {number} tabId - The tab ID to navigate (or null for active tab)
 * @param {string} url - The URL to navigate to
 * @param {string|null} waitFor - Wait condition: 'load' or 'networkidle'
 * @param {number} timeout - Timeout in seconds (default 30)
 * @returns {Promise<{ok: boolean, url?: string, title?: string, error?: string}>}
 *
 * ARCHITECTURE NOTE: Chrome uses HYBRID detection (events + polling)
 * -----------------------------------------------------------------
 * Primary: chrome.tabs.onUpdated listener - fast, efficient, works 95% of the time
 * Backup: Polling via chrome.tabs.get() - catches remaining 5% (some redirects, etc.)
 *
 * This differs from Firefox which uses POLLING ONLY because Firefox's onUpdated
 * events don't fire reliably when registered from message handlers.
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
            const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!activeTab) {
                return { ok: false, error: 'No active tab found' };
            }
            targetTabId = activeTab.id;
        }

        // Get current URL before navigation (for same-origin detection)
        const initialTab = await chrome.tabs.get(targetTabId);
        const initialUrl = initialTab.url;
        const targetUrl = new URL(url);

        console.log('[Inspekt] Starting navigation:', { from: initialUrl, to: url, timeout });

        return new Promise((resolve) => {
            const timeoutMs = timeout * 1000;
            const pollInterval = 500; // Backup polling every 500ms
            let resolved = false;
            let timeoutId;
            let pollId;

            const cleanup = () => {
                if (timeoutId) clearTimeout(timeoutId);
                if (pollId) clearInterval(pollId);
                chrome.tabs.onUpdated.removeListener(listener);
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

            // Helper to check if navigation completed
            const checkNavigationComplete = async (tab, source) => {
                try {
                    const currentUrl = new URL(tab.url);

                    // Success conditions:
                    // 1. Exact URL match, OR
                    // 2. Origin matches target (with www normalization) AND page changed
                    const exactMatch = tab.url === url;
                    const hostsMatch = normalizeHost(currentUrl.hostname) === normalizeHost(targetUrl.hostname);
                    const protocolMatches = currentUrl.protocol === targetUrl.protocol;
                    const originMatches = hostsMatch && protocolMatches;
                    const pageChanged = tab.url !== initialUrl;

                    if (exactMatch || (originMatches && pageChanged)) {
                        // Handle networkidle wait
                        if (waitFor === 'networkidle') {
                            console.log('[Inspekt] Waiting for network idle…');
                            await new Promise(r => setTimeout(r, 1000));
                        }

                        console.log(`[Inspekt] Navigation complete (${source}):`, {
                            targetUrl: url,
                            finalUrl: tab.url,
                            title: tab.title
                        });

                        return { ok: true, url: tab.url, title: tab.title };
                    }
                } catch (e) {
                    // URL parse error, continue waiting
                }
                return null;
            };

            // Primary: Event-driven listener
            const listener = async (updatedTabId, changeInfo, tab) => {
                if (updatedTabId !== targetTabId) return;

                if (changeInfo.status === 'complete') {
                    const result = await checkNavigationComplete(tab, 'event');
                    if (result) finish(result);
                }
            };

            // Backup: Polling (catches cases where event doesn't fire)
            // WHY: Some sites (like Amazon) have complex redirect chains where the
            // onUpdated event fires before the final URL is reached. Polling ensures
            // we catch the final state even if events are missed.
            pollId = setInterval(async () => {
                try {
                    const tab = await chrome.tabs.get(targetTabId);
                    if (tab.status === 'complete' && tab.url !== initialUrl) {
                        const result = await checkNavigationComplete(tab, 'polling');
                        if (result) finish(result);
                    }
                } catch (e) {
                    // Tab may not exist anymore
                }
            }, pollInterval);

            // Timeout handler
            timeoutId = setTimeout(async () => {
                try {
                    const finalTab = await chrome.tabs.get(targetTabId);
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

            // Register listener BEFORE starting navigation
            chrome.tabs.onUpdated.addListener(listener);

            // Start navigation
            chrome.tabs.update(targetTabId, { url: url }).catch(err => {
                console.error('[Inspekt] chrome.tabs.update failed:', err);
                finish({ ok: false, error: `chrome.tabs.update failed: ${err.message}` });
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
// CSP BYPASS MANAGEMENT (using declarativeNetRequest)
// ============================================================================

// Track rule IDs for CSP bypass (use unique IDs based on domain hash)
const CSP_BYPASS_STORAGE_KEY = 'inspekt_csp_bypass_domains';

/**
 * Generate a unique rule ID for a domain
 * Uses a simple hash to create consistent IDs
 */
function getDomainRuleId(domain) {
    let hash = 0;
    for (let i = 0; i < domain.length; i++) {
        const char = domain.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32-bit integer
    }
    // Use positive number between 1000-999999 to avoid conflicts
    return 1000 + Math.abs(hash % 999000);
}

/**
 * Enable CSP bypass for a domain
 * Uses declarativeNetRequest to remove CSP headers
 */
async function handleCspBypassEnable(domain) {
    try {
        const ruleId = getDomainRuleId(domain);

        // Create rule to remove CSP headers for this domain
        const rule = {
            id: ruleId,
            priority: 1,
            action: {
                type: 'modifyHeaders',
                responseHeaders: [
                    { header: 'Content-Security-Policy', operation: 'remove' },
                    { header: 'Content-Security-Policy-Report-Only', operation: 'remove' },
                    { header: 'X-Content-Security-Policy', operation: 'remove' } // Legacy IE header
                ]
            },
            condition: {
                urlFilter: `||${domain}`,
                resourceTypes: ['main_frame', 'sub_frame']
            }
        };

        // Add the rule
        await chrome.declarativeNetRequest.updateDynamicRules({
            addRules: [rule],
            removeRuleIds: [ruleId] // Remove any existing rule with same ID first
        });

        // Store in sync storage
        const result = await chrome.storage.sync.get(CSP_BYPASS_STORAGE_KEY);
        const cspBypassDomains = result[CSP_BYPASS_STORAGE_KEY] || {};
        cspBypassDomains[domain] = {
            enabled: true,
            ruleId: ruleId,
            enabledAt: new Date().toISOString()
        };
        await chrome.storage.sync.set({ [CSP_BYPASS_STORAGE_KEY]: cspBypassDomains });

        console.log(`[Inspekt] CSP bypass enabled for ${domain} (rule ID: ${ruleId})`);

        return {
            ok: true,
            domain: domain,
            ruleId: ruleId,
            message: `CSP bypass enabled for ${domain}. Refresh the page for changes to take effect.`
        };
    } catch (error) {
        console.error('[Inspekt] Failed to enable CSP bypass:', error);
        return {
            ok: false,
            error: String(error)
        };
    }
}

/**
 * Disable CSP bypass for a domain
 */
async function handleCspBypassDisable(domain) {
    try {
        const ruleId = getDomainRuleId(domain);

        // Remove the rule
        await chrome.declarativeNetRequest.updateDynamicRules({
            removeRuleIds: [ruleId]
        });

        // Update storage
        const result = await chrome.storage.sync.get(CSP_BYPASS_STORAGE_KEY);
        const cspBypassDomains = result[CSP_BYPASS_STORAGE_KEY] || {};
        delete cspBypassDomains[domain];
        await chrome.storage.sync.set({ [CSP_BYPASS_STORAGE_KEY]: cspBypassDomains });

        console.log(`[Inspekt] CSP bypass disabled for ${domain}`);

        return {
            ok: true,
            domain: domain,
            message: `CSP bypass disabled for ${domain}. Refresh the page for changes to take effect.`
        };
    } catch (error) {
        console.error('[Inspekt] Failed to disable CSP bypass:', error);
        return {
            ok: false,
            error: String(error)
        };
    }
}

/**
 * Get CSP bypass status for a domain
 */
async function handleCspBypassStatus(domain) {
    try {
        const result = await chrome.storage.sync.get(CSP_BYPASS_STORAGE_KEY);
        const cspBypassDomains = result[CSP_BYPASS_STORAGE_KEY] || {};

        if (cspBypassDomains[domain]) {
            return {
                ok: true,
                domain: domain,
                enabled: true,
                ruleId: cspBypassDomains[domain].ruleId,
                enabledAt: cspBypassDomains[domain].enabledAt
            };
        }

        return {
            ok: true,
            domain: domain,
            enabled: false
        };
    } catch (error) {
        return {
            ok: false,
            error: String(error)
        };
    }
}

// Global CSP bypass constants
const CSP_BYPASS_GLOBAL_STORAGE_KEY = 'inspekt_csp_bypass_global';
const CSP_BYPASS_GLOBAL_RULE_ID = 999; // Fixed rule ID for global bypass

/**
 * Enable or disable global CSP bypass for ALL domains
 * Uses a single rule with broad URL matching
 */
async function handleCspBypassGlobal(enabled) {
    try {
        if (enabled) {
            // Create rule to remove CSP headers for ALL http/https URLs
            const rule = {
                id: CSP_BYPASS_GLOBAL_RULE_ID,
                priority: 2, // Higher priority than domain-specific rules
                action: {
                    type: 'modifyHeaders',
                    responseHeaders: [
                        { header: 'Content-Security-Policy', operation: 'remove' },
                        { header: 'Content-Security-Policy-Report-Only', operation: 'remove' },
                        { header: 'X-Content-Security-Policy', operation: 'remove' }
                    ]
                },
                condition: {
                    urlFilter: '|http*',
                    resourceTypes: ['main_frame', 'sub_frame']
                }
            };

            // Add the rule
            await chrome.declarativeNetRequest.updateDynamicRules({
                addRules: [rule],
                removeRuleIds: [CSP_BYPASS_GLOBAL_RULE_ID]
            });

            // Store state in sync storage
            await chrome.storage.sync.set({
                [CSP_BYPASS_GLOBAL_STORAGE_KEY]: {
                    enabled: true,
                    enabledAt: new Date().toISOString()
                }
            });

            console.log('[Inspekt] Global CSP bypass ENABLED');

            return {
                ok: true,
                enabled: true,
                message: 'Global CSP bypass enabled. Refresh pages for changes to take effect.'
            };
        } else {
            // Remove the global rule
            await chrome.declarativeNetRequest.updateDynamicRules({
                removeRuleIds: [CSP_BYPASS_GLOBAL_RULE_ID]
            });

            // Update storage
            await chrome.storage.sync.set({
                [CSP_BYPASS_GLOBAL_STORAGE_KEY]: {
                    enabled: false
                }
            });

            console.log('[Inspekt] Global CSP bypass DISABLED');

            return {
                ok: true,
                enabled: false,
                message: 'Global CSP bypass disabled. Refresh pages for changes to take effect.'
            };
        }
    } catch (error) {
        console.error('[Inspekt] Failed to toggle global CSP bypass:', error);
        return {
            ok: false,
            error: String(error)
        };
    }
}

/**
 * Get global CSP bypass status
 */
async function getGlobalCspBypassStatus() {
    try {
        const result = await chrome.storage.sync.get(CSP_BYPASS_GLOBAL_STORAGE_KEY);
        const globalBypass = result[CSP_BYPASS_GLOBAL_STORAGE_KEY] || { enabled: false };
        return {
            ok: true,
            enabled: globalBypass.enabled || false,
            enabledAt: globalBypass.enabledAt
        };
    } catch (error) {
        return {
            ok: false,
            enabled: false,
            error: String(error)
        };
    }
}

// ============================================================================
// THROTTLE PREVENTION (Background Tab Responsiveness)
// ============================================================================

/**
 * Enable throttle prevention for a tab using CDP's Emulation.setCPUThrottlingRate
 * This prevents Chrome from throttling the tab when it's in the background,
 * keeping JavaScript timers and callbacks responsive.
 */
async function handleThrottlePreventionEnable(tabId) {
    try {
        // Check if already enabled
        if (throttlePreventionTabs.has(tabId)) {
            return {
                ok: true,
                enabled: true,
                message: 'Throttle prevention already active for this tab.'
            };
        }

        const debuggerVersion = '1.3';

        // Attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                const error = chrome.runtime.lastError?.message;
                if (error) {
                    if (error.includes('Another debugger')) {
                        reject(new Error('Cannot enable: DevTools or another debugger is attached. Close DevTools and try again.'));
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    resolve();
                }
            });
        });

        console.log('[Inspekt] CDP debugger attached for throttle prevention on tab:', tabId);

        // Set CPU throttling rate to 1 (no throttling)
        // Chrome uses higher rates (2-4) for background tabs
        await new Promise((resolve, reject) => {
            chrome.debugger.sendCommand(
                { tabId },
                'Emulation.setCPUThrottlingRate',
                { rate: 1 },
                (result) => {
                    const error = chrome.runtime.lastError?.message;
                    if (error) {
                        reject(new Error(error));
                    } else {
                        resolve(result);
                    }
                }
            );
        });

        console.log('[Inspekt] Throttle prevention enabled for tab:', tabId);

        // Track this tab
        throttlePreventionTabs.add(tabId);

        return {
            ok: true,
            enabled: true,
            message: 'Throttle prevention enabled. Tab will stay responsive in background.'
        };
    } catch (error) {
        console.error('[Inspekt] Failed to enable throttle prevention:', error);
        return {
            ok: false,
            error: String(error)
        };
    }
}

/**
 * Disable throttle prevention for a tab
 */
async function handleThrottlePreventionDisable(tabId) {
    try {
        // Check if enabled
        if (!throttlePreventionTabs.has(tabId)) {
            return {
                ok: true,
                enabled: false,
                message: 'Throttle prevention was not active for this tab.'
            };
        }

        // Detach debugger (this automatically restores normal throttling behavior)
        await new Promise((resolve, reject) => {
            chrome.debugger.detach({ tabId }, () => {
                const error = chrome.runtime.lastError?.message;
                if (error) {
                    // If already detached, that's fine
                    console.log('[Inspekt] Debugger already detached:', error);
                }
                resolve();
            });
        });

        console.log('[Inspekt] Throttle prevention disabled for tab:', tabId);

        // Remove from tracking
        throttlePreventionTabs.delete(tabId);

        return {
            ok: true,
            enabled: false,
            message: 'Throttle prevention disabled. Normal background tab throttling restored.'
        };
    } catch (error) {
        console.error('[Inspekt] Failed to disable throttle prevention:', error);
        // Still remove from tracking to avoid inconsistent state
        throttlePreventionTabs.delete(tabId);
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
 * This runs in MAIN world to intercept the actual console calls
 */
async function injectConsoleHooks(tabId) {
    try {
        await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: () => {
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
            }
        });
        console.log('[Inspekt] Console hooks injected for tab:', tabId);
    } catch (error) {
        // Silently fail for restricted pages (chrome://, about:, etc.)
        console.log('[Inspekt] Could not inject console hooks:', error.message);
    }
}

/**
 * Get console logs from page
 */
async function getConsoleLogs(tabId) {
    try {
        const results = await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: () => {
                const logs = window.__INSPEKT_CONSOLE_LOGS__ || [];
                return {
                    ok: true,
                    entries: logs,
                    count: logs.length,
                    hooked: !!window.__INSPEKT_CONSOLE_HOOKED__
                };
            }
        });

        if (results && results[0]) {
            return results[0].result;
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
        const results = await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: () => {
                if (window.__INSPEKT_CONSOLE_LOGS__) {
                    window.__INSPEKT_CONSOLE_LOGS__.length = 0;
                    return { ok: true, message: 'Console buffer cleared' };
                }
                return { ok: true, message: 'No console buffer to clear' };
            }
        });

        if (results && results[0]) {
            return results[0].result;
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
        const result = await chrome.storage.sync.get('inspekt_allowed_domains');
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
        const result = await chrome.storage.sync.get('inspekt_temp_bypass');
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
        const tabs = await chrome.tabs.query({});
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
    await chrome.action.setBadgeText({ tabId, text: '✓' });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: '#00AA00' });
}

/**
 * Set icon to "bypass" state (orange with minutes or unlock)
 */
async function setBypassIcon(tabId, minutes) {
    const text = minutes > 99 ? '🔓' : String(minutes);
    await chrome.action.setBadgeText({ tabId, text });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: '#FF9800' });
}

/**
 * Set icon to "connecting" state (yellow with dots)
 */
async function setConnectingIcon(tabId) {
    await chrome.action.setBadgeText({ tabId, text: '…' });
    await chrome.action.setBadgeBackgroundColor({ tabId, color: '#FFEB3B' });
}

/**
 * Set icon to default state (no badge)
 */
async function setDefaultIcon(tabId) {
    await chrome.action.setBadgeText({ tabId, text: '' });
}

// ============================================================================
// CDP FULL PAGE SCREENSHOT
// ============================================================================

/**
 * Capture full page screenshot using Chrome DevTools Protocol
 * @param {number} tabId - Tab ID to capture
 * @param {Object} options - Screenshot options
 * @returns {Promise<Object>} Screenshot result with base64 data
 */
async function captureFullPageWithCDP(tabId, options = {}) {
    const debuggerVersion = '1.3';
    let attached = false;

    try {
        // Step 1: Attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                if (chrome.runtime.lastError) {
                    const error = chrome.runtime.lastError.message;
                    if (error.includes('Another debugger')) {
                        reject(new Error('Cannot capture: another debugger is attached. Close DevTools and try again.'));
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    attached = true;
                    resolve();
                }
            });
        });

        console.log('[Inspekt] CDP debugger attached for full page capture');

        // Hide DevTools element highlight overlay (prevents dimension box in screenshots)
        try {
            await sendDebuggerCommand(tabId, 'Overlay.hideHighlight', {});
        } catch (e) {
            console.log('[Inspekt] Could not hide highlight overlay:', e.message);
        }

        // Step 2: Get page layout metrics
        const metrics = await sendDebuggerCommand(tabId, 'Page.getLayoutMetrics', {});
        const contentSize = metrics.cssContentSize || metrics.contentSize;
        const width = Math.ceil(contentSize.width);
        const height = Math.ceil(contentSize.height);

        console.log('[Inspekt] Page dimensions:', width, 'x', height);

        // Check for maximum height limit (Chrome has 16384px limit)
        const maxHeight = options.maxHeight || 16384;
        const captureHeight = Math.min(height, maxHeight);
        const truncated = height > captureHeight;

        if (truncated) {
            console.log('[Inspekt] Page truncated from', height, 'to', captureHeight);
        }

        // Step 3: Override device metrics to match full page
        const deviceScaleFactor = options.scale || 1;
        await sendDebuggerCommand(tabId, 'Emulation.setDeviceMetricsOverride', {
            width: width,
            height: captureHeight,
            deviceScaleFactor: deviceScaleFactor,
            mobile: false
        });

        // Small delay to ensure metrics are applied
        await new Promise(resolve => setTimeout(resolve, 100));

        // Step 4: Capture screenshot
        const format = options.format || 'png';
        const screenshotParams = {
            format: format,
            captureBeyondViewport: true,
            fromSurface: true,
            clip: {
                x: 0,
                y: 0,
                width: width,
                height: captureHeight,
                scale: 1
            }
        };

        if (format === 'jpeg' || format === 'jpg') {
            screenshotParams.format = 'jpeg';
            screenshotParams.quality = Math.round((options.quality || 0.92) * 100);
        }

        const screenshotResult = await sendDebuggerCommand(tabId, 'Page.captureScreenshot', screenshotParams);

        console.log('[Inspekt] Screenshot captured');

        // Step 5: Clear device metrics override
        await sendDebuggerCommand(tabId, 'Emulation.clearDeviceMetricsOverride', {});

        // Step 6: Detach debugger
        await detachDebugger(tabId);
        attached = false;

        console.log('[Inspekt] CDP debugger detached');

        // Build data URL
        const mimeType = format === 'jpeg' || format === 'jpg' ? 'image/jpeg' :
                         format === 'webp' ? 'image/webp' : 'image/png';

        return {
            ok: true,
            dataUrl: `data:${mimeType};base64,${screenshotResult.data}`,
            width: width * deviceScaleFactor,
            height: captureHeight * deviceScaleFactor,
            fullHeight: height,
            truncated: truncated,
            apiUsed: 'chrome.debugger (CDP)'
        };

    } catch (error) {
        console.error('[Inspekt] CDP capture error:', error);

        // Ensure debugger is detached on error
        if (attached) {
            try {
                await detachDebugger(tabId);
            } catch (detachError) {
                console.error('[Inspekt] Failed to detach debugger:', detachError);
            }
        }
        throw error;
    }
}

/**
 * Capture a specific element using Chrome DevTools Protocol with clip region
 *
 * Used for elements that exceed viewport size and can't be captured
 * with the standard captureVisibleTab method.
 *
 * @param {number} tabId - Tab ID to capture
 * @param {Object} options - Capture options with clip region
 * @returns {Promise<Object>} Screenshot result with base64 data
 */
async function captureElementWithCDP(tabId, options = {}) {
    const debuggerVersion = '1.3';
    let attached = false;

    try {
        // Step 1: Attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                if (chrome.runtime.lastError) {
                    const error = chrome.runtime.lastError.message;
                    if (error.includes('Another debugger')) {
                        reject(new Error('Cannot capture: another debugger is attached. Close DevTools and try again.'));
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    attached = true;
                    resolve();
                }
            });
        });

        console.log('[Inspekt] CDP debugger attached for element capture');

        // Hide DevTools element highlight overlay (the dimension box shown when inspecting)
        // This prevents the overlay from appearing in screenshots
        try {
            await sendDebuggerCommand(tabId, 'Overlay.hideHighlight', {});
        } catch (e) {
            // Overlay domain may not be available - not critical, continue
            console.log('[Inspekt] Could not hide highlight overlay:', e.message);
        }

        // Extract clip region from options
        const clip = options.clip;
        if (!clip || typeof clip.x !== 'number' || typeof clip.y !== 'number' ||
            typeof clip.width !== 'number' || typeof clip.height !== 'number') {
            throw new Error('Invalid clip region: x, y, width, and height are required');
        }

        // Apply margin to clip region
        const margin = options.margin || 0;
        const clipWithMargin = {
            x: Math.max(0, clip.x - margin),
            y: Math.max(0, clip.y - margin),
            width: clip.width + (margin * 2),
            height: clip.height + (margin * 2),
            scale: options.scale || 1
        };

        // Step 2: Set transparent background if isolate mode
        if (options.isolate) {
            // Set the browser's default background to transparent
            await sendDebuggerCommand(tabId, 'Emulation.setDefaultBackgroundColorOverride', {
                color: { r: 0, g: 0, b: 0, a: 0 }
            });
            // Brief pause for compositor to apply the change
            await new Promise(resolve => setTimeout(resolve, 50));
        }

        // Step 3: Capture screenshot with clip
        const format = options.format || 'png';
        const screenshotParams = {
            format: format,
            captureBeyondViewport: true,
            fromSurface: true,  // Chrome requires this - fromSurface: false is not allowed
            clip: clipWithMargin,
            // For isolated captures, omit the default background to get true transparency
            ...(options.isolate ? { omitBackground: true } : {})
        };

        if (format === 'jpeg' || format === 'jpg') {
            screenshotParams.format = 'jpeg';
            screenshotParams.quality = Math.round((options.quality || 0.92) * 100);
        }

        const screenshotResult = await sendDebuggerCommand(tabId, 'Page.captureScreenshot', screenshotParams);

        // Step 4: Reset background color override if we set it
        if (options.isolate) {
            await sendDebuggerCommand(tabId, 'Emulation.setDefaultBackgroundColorOverride', {});
        }

        console.log('[Inspekt] Element screenshot captured via CDP');

        // Step 3: Detach debugger
        await detachDebugger(tabId);
        attached = false;

        console.log('[Inspekt] CDP debugger detached');

        // Build data URL
        const mimeType = format === 'jpeg' || format === 'jpg' ? 'image/jpeg' :
                         format === 'webp' ? 'image/webp' : 'image/png';

        const scale = options.scale || 1;

        return {
            ok: true,
            dataUrl: `data:${mimeType};base64,${screenshotResult.data}`,
            width: Math.round(clipWithMargin.width * scale),
            height: Math.round(clipWithMargin.height * scale),
            selector: options.selector || 'element',
            tagName: options.tagName || 'ELEMENT',
            apiUsed: 'chrome.debugger (CDP)',
            usedCDPFallback: true
        };

    } catch (error) {
        console.error('[Inspekt] CDP element capture error:', error);

        // Ensure debugger is detached on error
        if (attached) {
            try {
                await detachDebugger(tabId);
            } catch (detachError) {
                console.error('[Inspekt] Failed to detach debugger:', detachError);
            }
        }
        throw error;
    }
}

/**
 * Send command to Chrome DevTools Protocol
 */
function sendDebuggerCommand(tabId, method, params) {
    return new Promise((resolve, reject) => {
        chrome.debugger.sendCommand({ tabId }, method, params, (result) => {
            if (chrome.runtime.lastError) {
                reject(new Error(chrome.runtime.lastError.message));
            } else {
                resolve(result);
            }
        });
    });
}

/**
 * Detach debugger from tab
 */
function detachDebugger(tabId) {
    return new Promise((resolve, reject) => {
        chrome.debugger.detach({ tabId }, () => {
            if (chrome.runtime.lastError) {
                // Ignore "not attached" errors
                if (chrome.runtime.lastError.message.includes('not attached')) {
                    resolve();
                } else {
                    reject(new Error(chrome.runtime.lastError.message));
                }
            } else {
                resolve();
            }
        });
    });
}

/**
 * Try to hide the Chrome DevTools inspector overlay
 *
 * When an element is selected in DevTools (Elements panel), Chrome shows an overlay
 * with dimensions (e.g., "1007px × 993px"). This overlay is captured by screenshots.
 *
 * This function attempts to hide the overlay using the CDP Overlay.hideHighlight command.
 * It will fail silently if DevTools is already attached (which prevents us from using
 * the debugger API), but the brief attempt often triggers the overlay to refresh/hide.
 */
async function hideInspectorOverlay(tabId) {
    if (!tabId) {
        return; // No tab ID, can't proceed
    }

    let attached = false;
    try {
        // Try to attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, '1.3', () => {
                if (chrome.runtime.lastError) {
                    // DevTools is likely already attached
                    reject(new Error(chrome.runtime.lastError.message));
                } else {
                    resolve();
                }
            });
        });
        attached = true;

        // Send the hide highlight command
        await sendDebuggerCommand(tabId, 'Overlay.hideHighlight', {});

        // Immediately detach to minimize disruption
        await detachDebugger(tabId);
        attached = false;

    } catch (e) {
        // Expected to fail when DevTools is open - that's OK
        // The delay in the calling code will still help settle any overlays
        if (attached) {
            try {
                await detachDebugger(tabId);
            } catch (detachError) {
                // Ignore detach errors
            }
        }
    }
}

// Note: Screenshot processing is handled in content.js where DOM APIs are available
// Background script only handles the raw capture via chrome.tabs.captureVisibleTab

// ============================================================================
// CDP PSEUDO-STATE FORCING (for :hover, :focus, etc. screenshots)
// ============================================================================

// Session state for pseudo-state management
let pseudoStateSession = {
    nodeId: null,
    tabId: null,
    attached: false
};

/**
 * Force CSS pseudo-state on element via CDP CSS.forcePseudoState
 *
 * This is the same approach used by Chrome DevTools when you force element states
 * in the Elements panel. It properly triggers all CSS rules including:
 * - :hover, :focus, :focus-visible, :focus-within, :active, :target
 * - Works with Shadow DOM
 * - Works with dynamically-added styles
 *
 * @param {number} tabId - Tab ID
 * @param {string} state - Pseudo-state without colon ('hover', 'focus', etc.)
 * @param {string|null} selector - CSS selector or null for inspected element
 */
async function forcePseudoStateViaCDP(tabId, state, selector) {
    const debuggerVersion = '1.3';

    try {
        // Attach debugger if not already attached
        if (!pseudoStateSession.attached || pseudoStateSession.tabId !== tabId) {
            await new Promise((resolve, reject) => {
                chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                    if (chrome.runtime.lastError) {
                        const error = chrome.runtime.lastError.message;
                        if (error.includes('already attached')) {
                            // Already attached is fine
                            resolve();
                        } else {
                            reject(new Error(error));
                        }
                    } else {
                        resolve();
                    }
                });
            });
            pseudoStateSession.attached = true;
            pseudoStateSession.tabId = tabId;
        }

        // Enable required CDP domains
        await sendDebuggerCommand(tabId, 'DOM.enable', {});
        await sendDebuggerCommand(tabId, 'CSS.enable', {});

        // Get document root
        const doc = await sendDebuggerCommand(tabId, 'DOM.getDocument', { depth: 0 });
        const rootNodeId = doc.root.nodeId;

        // Get element nodeId
        let nodeId;
        if (selector) {
            // Use provided CSS selector
            const queryResult = await sendDebuggerCommand(tabId, 'DOM.querySelector', {
                nodeId: rootNodeId,
                selector: selector
            });
            nodeId = queryResult.nodeId;
        } else {
            // For inspected element, inject a temporary marker and query for it
            const [result] = await chrome.scripting.executeScript({
                target: { tabId },
                func: () => {
                    const el = window.__INSPEKT_INSPECTED_ELEMENT__;
                    if (!el) return null;
                    // Add temporary data attribute for identification
                    el.dataset.inspektPseudoTarget = 'true';
                    return '[data-inspekt-pseudo-target="true"]';
                }
            });

            const tempSelector = result?.result;
            if (!tempSelector) {
                throw new Error('No inspected element available. Select an element in DevTools first.');
            }

            const queryResult = await sendDebuggerCommand(tabId, 'DOM.querySelector', {
                nodeId: rootNodeId,
                selector: tempSelector
            });
            nodeId = queryResult.nodeId;

            // Clean up temp attribute
            await chrome.scripting.executeScript({
                target: { tabId },
                func: () => {
                    const el = document.querySelector('[data-inspekt-pseudo-target="true"]');
                    if (el) delete el.dataset.inspektPseudoTarget;
                }
            });
        }

        if (!nodeId) {
            throw new Error('Element not found in DOM');
        }

        // Store nodeId for cleanup later
        pseudoStateSession.nodeId = nodeId;

        // Apply pseudo-state
        // CSS.forcePseudoState expects array of pseudo-classes without colons
        await sendDebuggerCommand(tabId, 'CSS.forcePseudoState', {
            nodeId: nodeId,
            forcedPseudoClasses: [state]
        });

        console.log('[Inspekt] Forced pseudo-state:', state, 'on nodeId:', nodeId);

        return { ok: true, nodeId: nodeId, method: 'cdp' };

    } catch (error) {
        console.error('[Inspekt] Failed to force pseudo-state via CDP:', error);
        throw error;
    }
}

/**
 * Clear forced pseudo-state from element
 */
async function clearPseudoStateViaCDP(tabId) {
    try {
        if (pseudoStateSession.nodeId && pseudoStateSession.tabId === tabId) {
            // Clear by setting empty array
            await sendDebuggerCommand(tabId, 'CSS.forcePseudoState', {
                nodeId: pseudoStateSession.nodeId,
                forcedPseudoClasses: []
            });

            console.log('[Inspekt] Cleared pseudo-state for nodeId:', pseudoStateSession.nodeId);

            pseudoStateSession.nodeId = null;
        }

        // Detach debugger to clean up
        if (pseudoStateSession.attached && pseudoStateSession.tabId === tabId) {
            try {
                await detachDebugger(tabId);
            } catch (e) {
                // Ignore detach errors
            }
            pseudoStateSession.attached = false;
            pseudoStateSession.tabId = null;
        }

        return { ok: true };
    } catch (error) {
        console.error('[Inspekt] Failed to clear pseudo-state:', error);
        // Don't throw - clearing is best-effort
        return { ok: true, warning: String(error) };
    }
}

// ============================================================================
// CDP EVENT LISTENERS (for getting addEventListener handlers)
// ============================================================================

/**
 * Get event listeners attached to an element via CDP DOMDebugger.getEventListeners
 * This retrieves all event listeners including those added via addEventListener().
 *
 * @param {number} tabId - Tab ID
 * @param {string} source - 'inspected' or 'focused'
 * @returns {Promise<Object>} Object with listeners array
 */
async function getEventListenersViaCDP(tabId, source) {
    const debuggerVersion = '1.3';

    try {
        // Attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                if (chrome.runtime.lastError) {
                    const error = chrome.runtime.lastError.message;
                    if (error.includes('already attached')) {
                        resolve();
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    resolve();
                }
            });
        });

        // Enable required CDP domains
        await sendDebuggerCommand(tabId, 'DOM.enable', {});
        await sendDebuggerCommand(tabId, 'DOMDebugger.enable', {});
        await sendDebuggerCommand(tabId, 'Runtime.enable', {});

        // Get the element's remote object ID
        // First inject a marker to find the element (MAIN world to access window.__INSPEKT_INSPECTED_ELEMENT__)
        const [result] = await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: (src) => {
                let el;
                if (src === 'inspected') {
                    el = window.__INSPEKT_INSPECTED_ELEMENT__;
                } else if (src === 'focused') {
                    let active = document.activeElement;
                    while (active && active.shadowRoot && active.shadowRoot.activeElement) {
                        active = active.shadowRoot.activeElement;
                    }
                    el = active;
                }
                if (!el) return null;
                // Store element temporarily for Runtime.evaluate access
                window.__INSPEKT_CDP_TARGET_ELEMENT__ = el;
                return true;
            },
            args: [source]
        });

        if (!result?.result) {
            await detachDebugger(tabId);
            return {
                ok: false,
                error: source === 'inspected' ? 'No element selected' : 'No element focused'
            };
        }

        // Get remote object reference to the element
        const evalResult = await sendDebuggerCommand(tabId, 'Runtime.evaluate', {
            expression: 'window.__INSPEKT_CDP_TARGET_ELEMENT__',
            returnByValue: false
        });

        if (!evalResult.result || !evalResult.result.objectId) {
            await detachDebugger(tabId);
            return { ok: false, error: 'Could not get element reference' };
        }

        const objectId = evalResult.result.objectId;

        // Get event listeners
        const listenersResult = await sendDebuggerCommand(tabId, 'DOMDebugger.getEventListeners', {
            objectId: objectId,
            depth: 1  // Only element itself, not ancestors
        });

        // Clean up temp variable (MAIN world)
        await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: () => { delete window.__INSPEKT_CDP_TARGET_ELEMENT__; }
        });

        // Format listeners for output
        const listeners = (listenersResult.listeners || []).map(listener => {
            return {
                type: listener.type,
                useCapture: listener.useCapture,
                passive: listener.passive,
                once: listener.once,
                handler: listener.handler ? {
                    type: listener.handler.type,
                    className: listener.handler.className,
                    description: listener.handler.description ?
                        (listener.handler.description.length > 200 ?
                            listener.handler.description.substring(0, 200) + '…' :
                            listener.handler.description) : null
                } : null,
                // Include source location if available
                scriptId: listener.scriptId || null,
                lineNumber: listener.lineNumber || null,
                columnNumber: listener.columnNumber || null
            };
        });

        // Detach debugger
        await detachDebugger(tabId);

        return {
            ok: true,
            listeners: listeners,
            count: listeners.length
        };

    } catch (error) {
        console.error('[Inspekt] Failed to get event listeners via CDP:', error);

        // Try to detach debugger on error
        try { await detachDebugger(tabId); } catch (e) { /* ignore */ }

        return {
            ok: false,
            error: String(error),
            hint: 'Event listener retrieval requires debugger access. This may fail if another debugger is attached.'
        };
    }
}

// ============================================================================
// CDP ACCESSIBILITY TREE
// ============================================================================

/**
 * Get partial accessibility tree for an element via CDP Accessibility.getPartialAXTree
 *
 * @param {number} tabId - Tab ID
 * @param {string} source - 'inspected' or 'focused'
 * @param {number} depth - Maximum depth to retrieve (default: 10)
 * @returns {Promise<Object>} Object with nodes array
 */
async function getAccessibilityTreeViaCDP(tabId, source, depth = 10) {
    const debuggerVersion = '1.3';

    try {
        // Attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                if (chrome.runtime.lastError) {
                    const error = chrome.runtime.lastError.message;
                    if (error.includes('already attached')) {
                        resolve();
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    resolve();
                }
            });
        });

        // Enable required CDP domains
        await sendDebuggerCommand(tabId, 'DOM.enable', {});
        await sendDebuggerCommand(tabId, 'Accessibility.enable', {});

        // Get document and find element's node ID
        const doc = await sendDebuggerCommand(tabId, 'DOM.getDocument', { depth: 0 });
        const rootNodeId = doc.root.nodeId;

        // Get element via injected script (MAIN world to access window.__INSPEKT_INSPECTED_ELEMENT__)
        const [result] = await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: (src) => {
                let el;
                if (src === 'inspected') {
                    el = window.__INSPEKT_INSPECTED_ELEMENT__;
                } else if (src === 'focused') {
                    let active = document.activeElement;
                    while (active && active.shadowRoot && active.shadowRoot.activeElement) {
                        active = active.shadowRoot.activeElement;
                    }
                    el = active;
                }
                if (!el) return null;
                // Add temporary marker
                el.dataset.inspektAxTreeTarget = 'true';
                return '[data-inspekt-ax-tree-target="true"]';
            },
            args: [source]
        });

        const tempSelector = result?.result;
        if (!tempSelector) {
            await detachDebugger(tabId);
            return {
                ok: false,
                error: source === 'inspected' ? 'No element selected' : 'No element focused'
            };
        }

        // Get DOM nodeId for element
        const queryResult = await sendDebuggerCommand(tabId, 'DOM.querySelector', {
            nodeId: rootNodeId,
            selector: tempSelector
        });
        const nodeId = queryResult.nodeId;

        // Clean up marker (MAIN world to access same element)
        await chrome.scripting.executeScript({
            target: { tabId },
            world: 'MAIN',
            func: () => {
                const el = document.querySelector('[data-inspekt-ax-tree-target="true"]');
                if (el) delete el.dataset.inspektAxTreeTarget;
            }
        });

        if (!nodeId) {
            await detachDebugger(tabId);
            return { ok: false, error: 'Element not found in DOM' };
        }

        // Get partial accessibility tree for the element
        // fetchRelatives: false to get only this element and its children
        const axTreeResult = await sendDebuggerCommand(tabId, 'Accessibility.getPartialAXTree', {
            nodeId: nodeId,
            fetchRelatives: false,
            depth: depth
        });

        // Detach debugger
        await detachDebugger(tabId);

        // Format nodes for output
        const nodes = (axTreeResult.nodes || []).map(node => {
            return {
                nodeId: node.nodeId,
                ignored: node.ignored,
                ignoredReasons: node.ignoredReasons,
                role: node.role ? { value: node.role.value, type: node.role.type } : null,
                name: node.name ? {
                    value: node.name.value,
                    type: node.name.type,
                    sources: node.name.sources ? node.name.sources.map(s => ({
                        type: s.type,
                        value: s.value ? s.value.value : null,
                        attribute: s.attribute,
                        attributeValue: s.attributeValue ? s.attributeValue.value : null,
                        superseded: s.superseded,
                        nativeSource: s.nativeSource,
                        nativeSourceValue: s.nativeSourceValue ? s.nativeSourceValue.value : null
                    })) : null
                } : null,
                description: node.description ? { value: node.description.value } : null,
                value: node.value ? { value: node.value.value, type: node.value.type } : null,
                properties: (node.properties || []).map(prop => ({
                    name: prop.name,
                    value: prop.value ? { value: prop.value.value, type: prop.value.type } : null
                })),
                childIds: node.childIds || [],
                backendDOMNodeId: node.backendDOMNodeId
            };
        });

        return {
            ok: true,
            nodes: nodes,
            rootNodeId: nodes.length > 0 ? nodes[0].nodeId : null,
            count: nodes.length
        };

    } catch (error) {
        console.error('[Inspekt] Failed to get accessibility tree via CDP:', error);

        // Try to detach debugger on error
        try { await detachDebugger(tabId); } catch (e) { /* ignore */ }

        return {
            ok: false,
            error: String(error),
            hint: 'Accessibility tree retrieval requires debugger access.'
        };
    }
}

// ============================================================================
// CDP AUTHORED CSS (original CSS values via CSS.getMatchedStylesForNode)
// ============================================================================

/**
 * Resolve the CSS cascade from CDP's getMatchedStylesForNode result.
 *
 * Returns a flat map of { propName: { value, selector, important } }
 * representing the winning value for each property.
 *
 * @param {Object} matchedResult - Result from CSS.getMatchedStylesForNode
 * @returns {Object} Flat map of winning property values
 */
function resolveCascade(matchedResult) {
    const winning = {};  // { propName: { value, selector, important } }

    // matchedCSSRules are ordered by specificity (lowest first, highest last)
    for (const match of (matchedResult.matchedCSSRules || [])) {
        const rule = match.rule;
        if (rule.origin === 'user-agent' || rule.origin === 'injected') continue;

        const selector = rule.selectorList?.text || '';

        for (const prop of rule.style.cssProperties) {
            if (prop.disabled) continue;
            const isImportant = prop.important || false;
            const existing = winning[prop.name];

            // !important beats non-important; otherwise last rule wins (higher specificity)
            if (!existing || isImportant || !existing.important) {
                winning[prop.name] = { value: prop.value, selector, important: isImportant };
            }
        }

        // Also capture shorthand entries (margin: 0 auto, etc.)
        for (const sh of (rule.style.shorthandEntries || [])) {
            if (!winning[sh.name] || !winning[sh.name].important) {
                winning[sh.name] = { value: sh.value, selector, important: false };
            }
        }
    }

    // Inline style overrides everything (except !important in stylesheets)
    if (matchedResult.inlineStyle) {
        for (const prop of matchedResult.inlineStyle.cssProperties) {
            if (prop.disabled) continue;
            const existing = winning[prop.name];
            // Inline always wins unless existing has !important from stylesheet
            if (!existing || !existing.important || prop.important) {
                winning[prop.name] = { value: prop.value, selector: 'inline', important: true };
            }
        }
    }

    return winning;
}

/**
 * Get authored CSS values for marked elements via CDP CSS.getMatchedStylesForNode.
 *
 * Elements must already have data-inspekt-css-id="0", "1", etc. attributes
 * set by the MAIN world script (get_authored_css_cdp.js).
 *
 * @param {number} tabId - Chrome tab ID
 * @param {string} source - 'inspected' or 'focused'
 * @param {number} elementCount - Number of marked elements
 * @returns {Promise<Object>} { ok: true, elements: { "0": {...}, "1": {...} } }
 */
async function getAuthoredCSSViaCDP(tabId, source, elementCount) {
    const debuggerVersion = '1.3';

    try {
        // Attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                if (chrome.runtime.lastError) {
                    const error = chrome.runtime.lastError.message;
                    if (error.includes('already attached')) {
                        resolve();
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    resolve();
                }
            });
        });

        // Enable required CDP domains
        await sendDebuggerCommand(tabId, 'DOM.enable', {});
        await sendDebuggerCommand(tabId, 'CSS.enable', {});

        // Get document root
        const doc = await sendDebuggerCommand(tabId, 'DOM.getDocument', { depth: -1 });
        const rootNodeId = doc.root.nodeId;

        // Loop over all marked elements
        const elements = {};

        for (let i = 0; i < elementCount; i++) {
            const selector = `[data-inspekt-css-id="${i}"]`;

            try {
                const queryResult = await sendDebuggerCommand(tabId, 'DOM.querySelector', {
                    nodeId: rootNodeId,
                    selector: selector
                });

                if (!queryResult || !queryResult.nodeId) {
                    // Element not found — skip silently
                    continue;
                }

                const matchedResult = await sendDebuggerCommand(tabId, 'CSS.getMatchedStylesForNode', {
                    nodeId: queryResult.nodeId
                });

                if (matchedResult) {
                    elements[String(i)] = resolveCascade(matchedResult);
                }
            } catch (elementError) {
                // Skip individual element errors (e.g., cross-origin)
                console.warn(`[Inspekt] CDP CSS error for element ${i}:`, elementError.message);
            }
        }

        // Detach debugger
        await detachDebugger(tabId);

        return {
            ok: true,
            elements: elements,
            count: Object.keys(elements).length
        };

    } catch (error) {
        console.error('[Inspekt] Failed to get authored CSS via CDP:', error);

        // Try to detach debugger on error
        try { await detachDebugger(tabId); } catch (e) { /* ignore */ }

        return {
            ok: false,
            error: String(error),
            hint: 'Authored CSS retrieval requires debugger access. Close DevTools if open.'
        };
    }
}

// ============================================================================
// CDP KEY DISPATCH (for real keyboard events)
// ============================================================================

// CDP key session state - keeps debugger attached during replay for better performance
let cdpKeySession = {
    tabId: null,
    attached: false,
    detachTimeout: null,
    DETACH_DELAY_MS: 10000  // Auto-detach after 10 seconds of inactivity
};

/**
 * Dispatch a key event via CDP Input.dispatchKeyEvent
 * This sends a "real" key event through the browser's input pipeline,
 * triggering :focus-visible unlike synthetic JavaScript events.
 *
 * This is the same approach used by Playwright and Puppeteer.
 *
 * The debugger is kept attached during replay sessions for better performance,
 * and auto-detaches after 10 seconds of inactivity.
 */
async function dispatchKeyViaCDP(tabId, key, modifiers = []) {
    const debuggerVersion = '1.3';

    // Build modifier flags: Alt=1, Ctrl=2, Meta=4, Shift=8
    let modifierFlags = 0;
    if (modifiers.includes('alt')) modifierFlags |= 1;
    if (modifiers.includes('ctrl')) modifierFlags |= 2;
    if (modifiers.includes('meta')) modifierFlags |= 4;
    if (modifiers.includes('shift')) modifierFlags |= 8;

    // Key code mappings for common keys
    // windowsVirtualKeyCode is used cross-platform in CDP
    // text: character produced by the key (empty for navigation keys)
    // Navigation keys use 'rawKeyDown' type, text-producing keys use 'keyDown'
    const keyMappings = {
        'Tab': { windowsVirtualKeyCode: 9, code: 'Tab', text: '' },
        'Enter': { windowsVirtualKeyCode: 13, code: 'Enter', text: '\r' },
        'Escape': { windowsVirtualKeyCode: 27, code: 'Escape', text: '' },
        'Space': { windowsVirtualKeyCode: 32, code: 'Space', text: ' ' },
        ' ': { windowsVirtualKeyCode: 32, code: 'Space', text: ' ' },
        'Backspace': { windowsVirtualKeyCode: 8, code: 'Backspace', text: '' },
        'Delete': { windowsVirtualKeyCode: 46, code: 'Delete', text: '' },
        'ArrowUp': { windowsVirtualKeyCode: 38, code: 'ArrowUp', text: '' },
        'ArrowDown': { windowsVirtualKeyCode: 40, code: 'ArrowDown', text: '' },
        'ArrowLeft': { windowsVirtualKeyCode: 37, code: 'ArrowLeft', text: '' },
        'ArrowRight': { windowsVirtualKeyCode: 39, code: 'ArrowRight', text: '' },
        'Home': { windowsVirtualKeyCode: 36, code: 'Home', text: '' },
        'End': { windowsVirtualKeyCode: 35, code: 'End', text: '' },
        'PageUp': { windowsVirtualKeyCode: 33, code: 'PageUp', text: '' },
        'PageDown': { windowsVirtualKeyCode: 34, code: 'PageDown', text: '' },
    };

    const keyInfo = keyMappings[key] || { windowsVirtualKeyCode: 0, code: key, text: '' };

    // CDP event type: 'rawKeyDown' for navigation keys (Tab, arrows, etc.)
    // 'keyDown' for text-producing keys (letters, space, enter)
    // rawKeyDown triggers native browser behavior like Tab focus navigation
    const keyDownType = keyInfo.text ? 'keyDown' : 'rawKeyDown';

    // Clear any pending auto-detach timeout
    if (cdpKeySession.detachTimeout) {
        clearTimeout(cdpKeySession.detachTimeout);
        cdpKeySession.detachTimeout = null;
    }

    try {
        // Check if we need to attach (different tab or not attached)
        const needsAttach = !cdpKeySession.attached ||
                           cdpKeySession.tabId !== tabId ||
                           screencastState.active;  // Screencast manages its own debugger

        if (needsAttach && !screencastState.active) {
            // Attach debugger (if not already attached)
            await new Promise((resolve, reject) => {
                chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                    if (chrome.runtime.lastError) {
                        const error = chrome.runtime.lastError.message;
                        // If already attached (e.g., by screencast or previous session), that's fine
                        if (error.includes('already attached')) {
                            cdpKeySession.attached = true;
                            cdpKeySession.tabId = tabId;
                            resolve();
                        } else if (error.includes('Another debugger')) {
                            // DevTools is open - we can't use CDP
                            reject(new Error('CDP unavailable: DevTools is open'));
                        } else {
                            reject(new Error(error));
                        }
                    } else {
                        cdpKeySession.attached = true;
                        cdpKeySession.tabId = tabId;
                        console.log('[Inspekt] CDP debugger attached for key dispatch');
                        resolve();
                    }
                });
            });
        }

        // Send keyDown event (rawKeyDown for navigation keys, keyDown for text keys)
        const keyDownParams = {
            type: keyDownType,
            key: key,
            code: keyInfo.code,
            windowsVirtualKeyCode: keyInfo.windowsVirtualKeyCode,
            nativeVirtualKeyCode: keyInfo.windowsVirtualKeyCode,
            modifiers: modifierFlags
        };
        // Add text parameter for keys that produce text (required for keyDown type)
        if (keyInfo.text) {
            keyDownParams.text = keyInfo.text;
            keyDownParams.unmodifiedText = keyInfo.text;
        }
        await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', keyDownParams);

        // Small delay between keyDown and keyUp (mimics real typing)
        await new Promise(r => setTimeout(r, 10));

        // Send keyUp event
        await sendDebuggerCommand(tabId, 'Input.dispatchKeyEvent', {
            type: 'keyUp',
            key: key,
            code: keyInfo.code,
            windowsVirtualKeyCode: keyInfo.windowsVirtualKeyCode,
            nativeVirtualKeyCode: keyInfo.windowsVirtualKeyCode,
            modifiers: modifierFlags
        });

        // Schedule auto-detach after inactivity (unless screencast is using debugger)
        if (!screencastState.active) {
            cdpKeySession.detachTimeout = setTimeout(async () => {
                if (cdpKeySession.attached && !screencastState.active) {
                    try {
                        await detachDebugger(cdpKeySession.tabId);
                        console.log('[Inspekt] CDP debugger auto-detached after inactivity');
                    } catch (e) {
                        // Ignore detach errors
                    }
                    cdpKeySession.attached = false;
                    cdpKeySession.tabId = null;
                }
            }, cdpKeySession.DETACH_DELAY_MS);
        }

        console.log(`[Inspekt] CDP key dispatched: ${key}${modifiers.length ? ' + ' + modifiers.join('+') : ''}`);
        return { dispatched: true, key, modifiers };

    } catch (error) {
        console.warn('[Inspekt] CDP key dispatch failed:', error.message);
        // Mark session as not attached on error
        cdpKeySession.attached = false;
        cdpKeySession.tabId = null;
        throw error;
    }
}

// Clean up CDP key session when tab is closed or navigated
chrome.tabs.onRemoved.addListener((tabId) => {
    if (cdpKeySession.tabId === tabId) {
        if (cdpKeySession.detachTimeout) {
            clearTimeout(cdpKeySession.detachTimeout);
        }
        cdpKeySession.attached = false;
        cdpKeySession.tabId = null;
        cdpKeySession.detachTimeout = null;
    }
});

// ============================================================================
// SCREENCAST (VIDEO RECORDING) FUNCTIONS
// ============================================================================

// Screencast state
let screencastState = {
    active: false,
    tabId: null,
    debuggerAttached: false,
    settings: {},
    firstFrameLogged: false,  // For debugging frame metadata
    bannerHeight: 0,          // Height of automation banner (for cropping)
    originalHeight: 0         // Original viewport height before debugger
};

/**
 * Start CDP screencast for video recording.
 * Streams frames from the browser to be collected by the bridge server.
 */
async function startScreencast(tabId, settings = {}, requestId = null) {
    const debuggerVersion = '1.3';

    if (screencastState.active) {
        return { ok: true, message: 'Screencast already active' };
    }

    try {
        // First, try to detach any stale debugger from previous attempts
        try {
            await new Promise((resolve) => {
                chrome.debugger.detach({ tabId }, () => {
                    // Ignore errors - there may not be a debugger attached
                    chrome.runtime.lastError; // Clear the error
                    resolve();
                });
            });
        } catch (e) {
            // Ignore detach errors
        }

        // Small delay after detach
        await new Promise(r => setTimeout(r, 100));

        // Attach debugger
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                if (chrome.runtime.lastError) {
                    const error = chrome.runtime.lastError.message;
                    if (error.includes('Another debugger')) {
                        reject(new Error('Video recording requires closing DevTools (F12). Please close the browser developer tools and try again.'));
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    resolve();
                }
            });
        });

        screencastState.debuggerAttached = true;
        console.log('[Inspekt] CDP debugger attached for screencast');

        // Enable Page domain
        await sendDebuggerCommand(tabId, 'Page.enable', {});

        // Try to hide the automation banner via CDP (experimental)
        // Note: Emulation domain is always available, no .enable() needed
        try {
            await sendDebuggerCommand(tabId, 'Emulation.setAutomationOverride', { enabled: false });
            console.log('[Inspekt] Automation override disabled (banner may be hidden)');
        } catch (e) {
            // This is expected to fail on most Chrome versions - the method is experimental
            console.log('[Inspekt] Automation override not available (expected):', e.message);
        }

        // Calculate frame interval from FPS
        const fps = settings.fps || 10;
        const quality = settings.quality || 80;
        const format = settings.format || 'jpeg';

        // Get viewport dimensions AFTER debugger is attached
        // This captures the actual available space (accounting for any automation banner)
        let maxWidth = settings.maxWidth || 4096;
        let maxHeight = settings.maxHeight || 4096;
        let preDebuggerHeight = settings.preDebuggerHeight || null;  // Passed from Python
        let bannerHeight = 0;

        try {
            // Query the actual viewport dimensions from the tab
            const [result] = await chrome.scripting.executeScript({
                target: { tabId },
                func: () => ({ width: window.innerWidth, height: window.innerHeight }),
                world: 'MAIN'
            });
            if (result && result.result) {
                maxWidth = result.result.width;
                maxHeight = result.result.height;

                // Calculate banner height if we have pre-debugger height
                if (preDebuggerHeight && preDebuggerHeight > maxHeight) {
                    bannerHeight = preDebuggerHeight - maxHeight;
                    console.log('[Inspekt] Detected automation banner height:', bannerHeight, 'px');
                }

                console.log('[Inspekt] Screencast using viewport dimensions:', maxWidth, 'x', maxHeight);
            }
        } catch (e) {
            console.log('[Inspekt] Could not get viewport dimensions, using defaults:', maxWidth, 'x', maxHeight);
        }

        // Store banner height for later reporting
        screencastState.bannerHeight = bannerHeight;
        screencastState.originalHeight = preDebuggerHeight || maxHeight;

        // Start screencast
        const screencastParams = {
            format: format,
            quality: quality,
            maxWidth: maxWidth,
            maxHeight: maxHeight,
            everyNthFrame: Math.max(1, Math.round(60 / fps)) // Approximate frame interval
        };

        // IMPORTANT: Set state BEFORE starting screencast to avoid race condition
        // CDP may start sending frame events immediately after Page.startScreencast
        screencastState.active = true;
        screencastState.tabId = tabId;
        screencastState.settings = settings;
        screencastState.firstFrameLogged = false;  // Reset for next session

        await sendDebuggerCommand(tabId, 'Page.startScreencast', screencastParams);

        console.log('[Inspekt] Screencast started at ~' + fps + ' FPS, target dimensions:', maxWidth, 'x', maxHeight);

        return {
            ok: true,
            message: 'Screencast started',
            width: maxWidth,
            height: maxHeight,
            bannerHeight: bannerHeight,
            originalHeight: preDebuggerHeight || maxHeight
        };

    } catch (error) {
        console.error('[Inspekt] Screencast start error:', error);

        // Clean up on error
        if (screencastState.debuggerAttached) {
            try {
                await detachDebugger(tabId);
            } catch (e) {
                console.error('[Inspekt] Failed to detach debugger:', e);
            }
        }
        screencastState.active = false;
        screencastState.debuggerAttached = false;

        throw error;
    }
}

/**
 * Stop CDP screencast.
 */
async function stopScreencast(tabId, requestId = null) {
    if (!screencastState.active) {
        return { ok: true, message: 'Screencast not active' };
    }

    try {
        // Stop screencast
        await sendDebuggerCommand(screencastState.tabId, 'Page.stopScreencast', {});

        console.log('[Inspekt] Screencast stopped');

        // Detach debugger
        if (screencastState.debuggerAttached) {
            await detachDebugger(screencastState.tabId);
            screencastState.debuggerAttached = false;
        }

        screencastState.active = false;
        screencastState.tabId = null;

        return { ok: true, message: 'Screencast stopped' };

    } catch (error) {
        console.error('[Inspekt] Screencast stop error:', error);

        // Force clean up
        screencastState.active = false;
        if (screencastState.debuggerAttached) {
            try {
                await detachDebugger(screencastState.tabId);
            } catch (e) {
                // Ignore
            }
        }
        screencastState.debuggerAttached = false;
        screencastState.tabId = null;

        throw error;
    }
}

// ============================================================================
// SMOOTH CAPTURE (TAB CAPTURE + MEDIARECORDER FOR VIDEO)
// ============================================================================

// Smooth capture state - uses tabCapture + MediaRecorder for proper video
// This provides real video recording like tab sharing in video calls
let smoothCaptureState = {
    active: false,
    tabId: null,
    startTime: null
};

/**
 * Ensure the offscreen document exists for video capture
 */
async function ensureOffscreenDocument() {
    const existingContexts = await chrome.runtime.getContexts({
        contextTypes: ['OFFSCREEN_DOCUMENT']
    });

    if (existingContexts.length > 0) {
        console.log('[Inspekt] Offscreen document already exists');
        return;
    }

    console.log('[Inspekt] Creating offscreen document for video capture');
    await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA'],
        justification: 'Recording tab video for replay capture'
    });
}

/**
 * Start smooth video capture using tabCapture + MediaRecorder.
 * This is the proper way to record browser tabs, like screen sharing.
 */
async function startSmoothCapture(tabId, settings = {}) {
    if (smoothCaptureState.active) {
        return { ok: true, message: 'Smooth capture already active' };
    }

    const fps = Math.max(5, Math.min(30, settings.fps || 15));
    const quality = Math.max(50, Math.min(100, settings.quality || 80));

    console.log(`[Inspekt] Starting smooth capture at ${fps} FPS, quality ${quality}, tabId: ${tabId}`);

    try {
        // Ensure offscreen document exists
        console.log('[Inspekt] Creating offscreen document…');
        await ensureOffscreenDocument();
        console.log('[Inspekt] Offscreen document ready');

        // Get a media stream ID for the tab
        console.log('[Inspekt] Getting media stream ID for tab…');
        const streamId = await new Promise((resolve, reject) => {
            chrome.tabCapture.getMediaStreamId({ targetTabId: tabId }, (id) => {
                if (chrome.runtime.lastError) {
                    console.error('[Inspekt] tabCapture.getMediaStreamId error:', chrome.runtime.lastError.message);
                    reject(new Error(chrome.runtime.lastError.message));
                } else if (!id) {
                    console.error('[Inspekt] tabCapture.getMediaStreamId returned empty ID');
                    reject(new Error('No stream ID returned'));
                } else {
                    resolve(id);
                }
            });
        });

        console.log('[Inspekt] Got media stream ID:', streamId.substring(0, 30) + '…');

        // Tell offscreen document to start recording
        console.log('[Inspekt] Sending start message to offscreen document…');
        const response = await chrome.runtime.sendMessage({
            type: 'OFFSCREEN_START_VIDEO_CAPTURE',
            target: 'offscreen',
            streamId: streamId,
            settings: { fps, quality }
        });

        console.log('[Inspekt] Offscreen response:', response);

        if (!response?.success) {
            throw new Error(response?.error || 'Failed to start video capture in offscreen document');
        }

        smoothCaptureState.active = true;
        smoothCaptureState.tabId = tabId;
        smoothCaptureState.startTime = Date.now();

        console.log('[Inspekt] Smooth capture started successfully');

        return {
            ok: true,
            message: 'Smooth capture started',
            fps: fps,
            quality: quality
        };

    } catch (error) {
        console.error('[Inspekt] Failed to start smooth capture:', error);
        // Return error instead of throwing to provide better feedback
        return {
            ok: false,
            error: String(error.message || error)
        };
    }
}

/**
 * Stop smooth video capture and return the video data.
 */
async function stopSmoothCapture() {
    if (!smoothCaptureState.active) {
        return { ok: true, message: 'Smooth capture not active' };
    }

    const duration = (Date.now() - smoothCaptureState.startTime) / 1000;
    console.log(`[Inspekt] Stopping smooth capture after ${duration.toFixed(1)}s`);

    try {
        // Tell offscreen document to stop recording and get the video data
        const response = await chrome.runtime.sendMessage({
            type: 'OFFSCREEN_STOP_VIDEO_CAPTURE',
            target: 'offscreen'
        });

        // Reset state
        smoothCaptureState.active = false;
        smoothCaptureState.tabId = null;
        smoothCaptureState.startTime = null;

        if (!response?.success) {
            throw new Error(response?.error || 'Failed to stop video capture');
        }

        const videoData = response.videoData;
        if (videoData) {
            console.log(`[Inspekt] Smooth capture stopped: ${videoData.size} bytes, ${videoData.duration?.toFixed(1)}s`);
            console.log(`[Inspekt] Video data base64 length: ${videoData.data?.length || 0}`);

            // Post video data to bridge server
            try {
                console.log(`[Inspekt] Posting video to ${BRIDGE_HTTP_URL}/video/captured…`);
                const postResponse = await fetch(`${BRIDGE_HTTP_URL}/video/captured`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        data: videoData.data,
                        mimeType: videoData.mimeType,
                        size: videoData.size,
                        duration: videoData.duration
                    })
                });

                if (!postResponse.ok) {
                    console.error(`[Inspekt] Failed to post video: HTTP ${postResponse.status}`);
                    const errorText = await postResponse.text();
                    console.error(`[Inspekt] Error response: ${errorText}`);
                } else {
                    const postResult = await postResponse.json();
                    console.log(`[Inspekt] Video posted successfully:`, postResult);
                }
            } catch (postError) {
                console.error(`[Inspekt] Error posting video to bridge:`, postError);
            }

            return {
                ok: true,
                message: 'Smooth capture stopped',
                duration: videoData.duration,
                size: videoData.size
            };
        } else {
            console.log('[Inspekt] Smooth capture stopped but no video data');
            return {
                ok: true,
                message: 'Smooth capture stopped (no data)',
                duration: duration
            };
        }

    } catch (error) {
        console.error('[Inspekt] Failed to stop smooth capture:', error);

        // Reset state even on error
        smoothCaptureState.active = false;
        smoothCaptureState.tabId = null;
        smoothCaptureState.startTime = null;

        throw error;
    }
}

// ============================================================================
// REPLAY MODE MANAGEMENT
// ============================================================================

/**
 * Enable replay mode - store visual script and inject into current tab
 * When enabled, the visual script will be auto-injected on every page load
 */
async function handleReplayModeEnable(visualScript, currentTabId) {
    try {
        replayModeEnabled = true;
        replayVisualScript = visualScript;

        console.log('[Inspekt] Replay mode ENABLED');

        // Immediately inject into current tab if provided
        if (currentTabId) {
            await injectReplayVisualScript(currentTabId);
        }

        return {
            ok: true,
            enabled: true,
            message: 'Replay mode enabled. Visual script will be auto-injected on page loads.'
        };
    } catch (error) {
        console.error('[Inspekt] Failed to enable replay mode:', error);
        return {
            ok: false,
            error: String(error)
        };
    }
}

/**
 * Disable replay mode and clean up
 */
async function handleReplayModeDisable() {
    try {
        replayModeEnabled = false;
        replayVisualScript = null;

        console.log('[Inspekt] Replay mode DISABLED');

        return {
            ok: true,
            enabled: false,
            message: 'Replay mode disabled.'
        };
    } catch (error) {
        console.error('[Inspekt] Failed to disable replay mode:', error);
        return {
            ok: false,
            error: String(error)
        };
    }
}

/**
 * Inject the stored visual script into a tab
 * Uses chrome.scripting.executeScript with MAIN world for full page access
 *
 * Note: We use a <script> element injection approach because new Function()
 * is blocked by CSP on many sites. The <script> element with textContent
 * bypasses CSP when injected from an extension's executeScript.
 */
async function injectReplayVisualScript(tabId) {
    if (!replayVisualScript) {
        console.log('[Inspekt] No visual script stored, skipping injection');
        return;
    }

    try {
        await chrome.scripting.executeScript({
            target: { tabId: tabId },
            world: 'MAIN',
            func: (scriptCode) => {
                try {
                    // Check if already injected
                    if (window.__INSPEKT_VISUAL__) {
                        console.log('[Inspekt] Visual script already present');
                        return { ok: true, alreadyPresent: true };
                    }

                    // Create and inject a script element
                    // This approach works even with strict CSP because the script
                    // is injected from a privileged extension context
                    const script = document.createElement('script');
                    script.textContent = scriptCode;
                    (document.head || document.documentElement).appendChild(script);
                    script.remove(); // Clean up after execution

                    // Verify injection worked
                    if (window.__INSPEKT_VISUAL__) {
                        console.log('[Inspekt] Visual script injected via replay mode');
                        return { ok: true, injected: true };
                    } else {
                        // Fallback to new Function if script element didn't work
                        // (might be blocked by CSP, but worth trying)
                        console.log('[Inspekt] Script element failed, trying new Function fallback');
                        const fn = new Function(scriptCode);
                        fn();
                        console.log('[Inspekt] Visual script injected via new Function fallback');
                        return { ok: true, injected: true, method: 'newFunction' };
                    }
                } catch (e) {
                    console.error('[Inspekt] Failed to inject visual script:', e);
                    return { ok: false, error: String(e) };
                }
            },
            args: [replayVisualScript]
        });

        console.log('[Inspekt] Visual script injection complete for tab:', tabId);
    } catch (error) {
        console.error('[Inspekt] Failed to inject visual script into tab:', tabId, error);
    }
}

// ============================================================================
// DOWNLOAD MONITORING FOR RECORDINGS
// ============================================================================

// Track active download monitoring sessions
const downloadListeners = new Map();

// MIME type mapping for file extensions (used when Chrome doesn't provide MIME type)
const EXTENSION_MIME_MAP = {
    '.pdf': 'application/pdf',
    '.txt': 'text/plain',
    '.json': 'application/json',
    '.csv': 'text/csv',
    '.html': 'text/html',
    '.htm': 'text/html',
    '.xml': 'application/xml',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.svg': 'image/svg+xml',
    '.webp': 'image/webp',
    '.ico': 'image/x-icon',
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.mp3': 'audio/mpeg',
    '.wav': 'audio/wav',
    '.ogg': 'audio/ogg',
    '.zip': 'application/zip',
    '.gz': 'application/gzip',
    '.tar': 'application/x-tar',
    '.rar': 'application/vnd.rar',
    '.7z': 'application/x-7z-compressed',
    '.doc': 'application/msword',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.xls': 'application/vnd.ms-excel',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.ppt': 'application/vnd.ms-powerpoint',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.rtf': 'application/rtf',
    '.js': 'application/javascript',
    '.css': 'text/css',
    '.md': 'text/markdown',
    '.yaml': 'application/x-yaml',
    '.yml': 'application/x-yaml',
};

/**
 * Infer MIME type from filename if Chrome didn't provide one.
 * Chrome's downloads API often returns undefined/null for MIME type,
 * especially for PDFs and other document types.
 * @param {string} filename - The filename to check
 * @param {string|null|undefined} providedMime - MIME type from Chrome API
 * @returns {string} The inferred or provided MIME type
 */
function inferMimeType(filename, providedMime) {
    // If Chrome provided a valid MIME type (not the default), use it
    if (providedMime && providedMime !== 'application/octet-stream') {
        return providedMime;
    }

    // Try to infer from file extension
    if (filename) {
        const ext = filename.toLowerCase().match(/\.[^.]+$/)?.[0];
        if (ext && EXTENSION_MIME_MAP[ext]) {
            return EXTENSION_MIME_MAP[ext];
        }
    }

    // Fall back to generic binary type
    return 'application/octet-stream';
}

/**
 * Start monitoring downloads for a recording session
 * @param {number} tabId - Tab ID to monitor
 * @param {string} sessionId - Unique session identifier
 */
async function startDownloadMonitoring(tabId, sessionId) {
    // Check if already monitoring this session
    if (downloadListeners.has(sessionId)) {
        return { ok: true, sessionId, message: 'Already monitoring' };
    }

    // Create listener state for this session
    const listener = {
        tabId: tabId,
        downloads: new Map(),  // downloadId -> download info
        onCreated: null,
        onChanged: null
    };

    // Listen for new downloads
    listener.onCreated = (downloadItem) => {
        // Track downloads from the recording tab or any tab (tabId -1 = unknown source)
        // Filter by tab if needed: downloadItem.tabId !== tabId && downloadItem.tabId !== -1
        console.log('[Inspekt] Download started:', downloadItem.id, downloadItem.filename, 'tab:', downloadItem.tabId);

        // Extract filename first (needed for MIME type inference)
        const filename = downloadItem.filename ? downloadItem.filename.split(/[\\/]/).pop() : 'unknown';

        const downloadInfo = {
            id: downloadItem.id,
            url: downloadItem.url || downloadItem.finalUrl || '',
            filename: filename,
            fullPath: downloadItem.filename || '',
            mime_type: inferMimeType(filename, downloadItem.mime),
            size: downloadItem.fileSize || downloadItem.totalBytes || 0,
            download_start: Date.now(),
            download_end: null,
            state: 'in_progress',
            referrer: downloadItem.referrer || '',
            tabId: downloadItem.tabId
        };

        listener.downloads.set(downloadItem.id, downloadInfo);

        // Notify content script about download start
        chrome.tabs.sendMessage(tabId, {
            type: 'INSPEKT_DOWNLOAD_STARTED',
            sessionId: sessionId,
            download: downloadInfo
        }).catch(() => {
            // Tab may not be ready yet, that's ok
        });
    };

    // Listen for download state changes
    listener.onChanged = (delta) => {
        const download = listener.downloads.get(delta.id);
        if (!download) return;

        // Update download info
        if (delta.state) {
            download.state = delta.state.current;
            if (delta.state.current === 'complete') {
                download.download_end = Date.now();
            }
        }

        if (delta.filename) {
            download.fullPath = delta.filename.current;
            download.filename = delta.filename.current.split(/[\\/]/).pop();
        }

        if (delta.fileSize) {
            download.size = delta.fileSize.current;
        }

        if (delta.totalBytes) {
            download.size = delta.totalBytes.current;
        }

        if (delta.mime) {
            // Apply inference in case Chrome's update is still generic
            download.mime_type = inferMimeType(download.filename, delta.mime.current);
        }

        // Notify on completion or failure (only once per download)
        if (delta.state?.current === 'complete' || delta.state?.current === 'interrupted') {
            // Prevent duplicate completion messages
            if (download.completionSent) {
                console.log('[Inspekt] Download completion already sent, skipping:', delta.id);
                return;
            }
            download.completionSent = true;

            console.log('[Inspekt] Download finished:', delta.id, download.state, download.filename);

            chrome.tabs.sendMessage(tabId, {
                type: 'INSPEKT_DOWNLOAD_COMPLETE',
                sessionId: sessionId,
                download: download
            }).catch(() => {
                // Tab may have navigated, that's ok
            });
        }
    };

    // Register listeners
    chrome.downloads.onCreated.addListener(listener.onCreated);
    chrome.downloads.onChanged.addListener(listener.onChanged);

    // Store listener state
    downloadListeners.set(sessionId, listener);

    console.log('[Inspekt] Download monitoring started for session:', sessionId, 'tab:', tabId);

    return { ok: true, sessionId };
}

/**
 * Stop monitoring downloads for a session
 * @param {string} sessionId - Session identifier
 */
function stopDownloadMonitoring(sessionId) {
    const listener = downloadListeners.get(sessionId);
    if (listener) {
        // Remove event listeners
        if (listener.onCreated) {
            chrome.downloads.onCreated.removeListener(listener.onCreated);
        }
        if (listener.onChanged) {
            chrome.downloads.onChanged.removeListener(listener.onChanged);
        }

        downloadListeners.delete(sessionId);
        console.log('[Inspekt] Download monitoring stopped for session:', sessionId);
    }

    return { ok: true, sessionId };
}

/**
 * Get list of downloads captured during a session
 * @param {string} sessionId - Session identifier
 */
function getSessionDownloads(sessionId) {
    const listener = downloadListeners.get(sessionId);
    if (!listener) {
        return { ok: false, error: 'No monitoring session found' };
    }

    const downloads = Array.from(listener.downloads.values());
    return { ok: true, downloads, count: downloads.length };
}

/**
 * Read download file content as base64
 * Note: This requires the file to exist at the download location
 * @param {number} downloadId - Browser download ID
 */
async function getDownloadFileContent(downloadId) {
    try {
        // Search for the download
        const [item] = await chrome.downloads.search({ id: downloadId });
        if (!item) {
            return { ok: false, error: 'Download not found' };
        }

        if (!item.filename || item.state !== 'complete') {
            return { ok: false, error: 'Download not complete or no filename' };
        }

        // Read file using fetch with file:// URL
        // Note: This works in extension context but may have security restrictions
        try {
            const response = await fetch(`file://${item.filename}`);
            const blob = await response.blob();

            return new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = () => {
                    resolve({
                        ok: true,
                        content: reader.result,  // data:mime;base64,...
                        filename: item.filename.split(/[\\/]/).pop(),
                        fullPath: item.filename,
                        mime_type: item.mime || blob.type,
                        size: blob.size
                    });
                };
                reader.onerror = () => {
                    resolve({ ok: false, error: 'Failed to read file: ' + reader.error });
                };
                reader.readAsDataURL(blob);
            });
        } catch (fetchError) {
            // file:// fetch may be blocked, return path info instead
            return {
                ok: true,
                content: null,
                filename: item.filename.split(/[\\/]/).pop(),
                fullPath: item.filename,
                mime_type: item.mime,
                size: item.fileSize || item.totalBytes,
                note: 'File content not accessible via fetch, use path to read externally'
            };
        }
    } catch (error) {
        return { ok: false, error: String(error) };
    }
}

// ============================================================================
// CDP DIALOG INTERCEPTION (for bullet-proof alert/confirm/prompt handling)
// ============================================================================

/**
 * Enable CDP-level dialog interception
 * Uses Chrome DevTools Protocol to intercept JavaScript dialogs before they block
 * @param {number} tabId - Tab to intercept dialogs on
 * @param {Array} queue - Pre-queued dialog results [{ type, result }, ...]
 */
async function enableDialogInterception(tabId, queue = []) {
    const debuggerVersion = '1.3';

    try {
        // Disable any existing interception first
        if (dialogInterception.enabled) {
            await disableDialogInterception();
        }

        // Attach debugger to tab
        await new Promise((resolve, reject) => {
            chrome.debugger.attach({ tabId }, debuggerVersion, () => {
                if (chrome.runtime.lastError) {
                    const error = chrome.runtime.lastError.message;
                    if (error.includes('Another debugger')) {
                        reject(new Error('Cannot enable dialog interception: DevTools is open. Close DevTools or use the DevTools to handle dialogs.'));
                    } else {
                        reject(new Error(error));
                    }
                } else {
                    resolve();
                }
            });
        });

        console.log('[Inspekt] CDP debugger attached for dialog interception on tab:', tabId);

        // Enable Page domain to receive dialog events
        await sendDebuggerCommand(tabId, 'Page.enable', {});

        // Update state
        dialogInterception.enabled = true;
        dialogInterception.tabId = tabId;
        dialogInterception.debuggerAttached = true;
        dialogInterception.queue = queue;

        console.log('[Inspekt] Dialog interception enabled with', queue.length, 'queued results');

        return {
            ok: true,
            message: `Dialog interception enabled for tab ${tabId}`,
            queueLength: queue.length
        };

    } catch (error) {
        console.error('[Inspekt] Failed to enable dialog interception:', error);

        // Clean up on failure
        dialogInterception.enabled = false;
        dialogInterception.tabId = null;
        dialogInterception.debuggerAttached = false;
        dialogInterception.queue = [];

        throw error;
    }
}

/**
 * Disable CDP dialog interception and detach debugger
 */
async function disableDialogInterception() {
    try {
        if (dialogInterception.debuggerAttached && dialogInterception.tabId) {
            await detachDebugger(dialogInterception.tabId);
            console.log('[Inspekt] CDP debugger detached from dialog interception');
        }
    } catch (error) {
        console.error('[Inspekt] Error detaching debugger:', error);
    }

    // Reset state
    dialogInterception.enabled = false;
    dialogInterception.tabId = null;
    dialogInterception.debuggerAttached = false;
    dialogInterception.queue = [];

    return { ok: true, message: 'Dialog interception disabled' };
}

/**
 * Handle CDP Page.javascriptDialogOpening event
 * Called when alert/confirm/prompt is triggered BEFORE it blocks
 */
async function handleJavaScriptDialogOpening(tabId, params) {
    // Mutex: Wait if another dialog is being processed (prevents race conditions)
    while (dialogInterception.processing) {
        await new Promise(r => setTimeout(r, 10));
    }
    dialogInterception.processing = true;

    try {
        const { type, message, defaultPrompt, hasBrowserHandler } = params;

        console.log('[Inspekt] JavaScript dialog intercepted:', { type, message, defaultPrompt });

        // Find matching result from queue (includes duration for replay timing)
        let result;
        let duration = 1500;  // Default 1.5 seconds

        // Try to match by type AND message first (most accurate)
        let queueIndex = dialogInterception.queue.findIndex(
            q => q.type === type && q.message === message
        );

        // Fallback: match by type only if no exact match (backward compatibility)
        const fallbackIndex = queueIndex === -1
            ? dialogInterception.queue.findIndex(q => q.type === type)
            : -1;

        // Log mismatches for debugging
        if (queueIndex === -1 && fallbackIndex !== -1) {
            const expected = dialogInterception.queue[fallbackIndex];
            console.warn(`[Inspekt] Dialog message mismatch - Expected: "${expected.message}", Actual: "${message}"`);
            queueIndex = fallbackIndex;  // Use fallback
        }

        if (queueIndex === -1 && fallbackIndex === -1 && dialogInterception.queue.length > 0) {
            console.error(`[Inspekt] Unexpected dialog appeared - Type: ${type}, Message: "${message}", No matching entry in queue.`);
        }

        if (queueIndex !== -1) {
            const queuedItem = dialogInterception.queue[queueIndex];
            result = queuedItem.result;
            duration = queuedItem.duration || 1500;
            dialogInterception.queue.splice(queueIndex, 1);  // Remove from queue
            console.log('[Inspekt] Using queued result:', result, 'duration:', duration, '- remaining queue:', dialogInterception.queue.length);
        } else {
            // Default results if not in queue
            if (type === 'alert') {
                result = true;  // Alert just needs to be dismissed
            } else if (type === 'confirm') {
                result = true;  // Default to OK for confirm
            } else if (type === 'prompt') {
                result = defaultPrompt || '';  // Use default or empty string
            }
            console.log('[Inspekt] No queued result, using default:', result);
        }

        // Determine accept value (for confirm/prompt)
        const accept = type === 'alert' ? true :
                       type === 'confirm' ? (result === true) :
                       type === 'prompt' ? (result !== null) : true;

        // For prompt, the result is the text to enter
        const promptText = type === 'prompt' && result !== null ? String(result) : undefined;

        // Dismiss the dialog with our result
        await sendDebuggerCommand(tabId, 'Page.handleJavaScriptDialog', {
            accept: accept,
            promptText: promptText
        });

        console.log('[Inspekt] Dialog handled:', { accept, promptText });

        // Notify content script to show synthetic overlay for visual feedback
        try {
            await chrome.tabs.sendMessage(tabId, {
                type: 'SHOW_DIALOG_OVERLAY',
                dialogType: type,
                message: message,
                result: result,
                duration: duration  // How long to show overlay (matches recorded duration)
            });
        } catch (e) {
            // Content script may not be ready, that's OK
            console.log('[Inspekt] Could not send overlay notification:', e.message);
        }

    } catch (error) {
        console.error('[Inspekt] Failed to handle dialog:', error);
    } finally {
        // Release mutex
        dialogInterception.processing = false;
    }
}

/**
 * Process CDP dialog events sequentially (prevents race conditions)
 */
async function processCdpDialogEventQueue() {
    if (processingCdpDialogEvents) return;
    processingCdpDialogEvents = true;

    while (cdpDialogEventQueue.length > 0) {
        const { tabId, params } = cdpDialogEventQueue.shift();
        await handleJavaScriptDialogOpening(tabId, params);
    }

    processingCdpDialogEvents = false;
}

// Listen for CDP events (debugger events)
// Uses event queue to ensure sequential processing (prevents race conditions with rapid dialogs)
chrome.debugger.onEvent.addListener((source, method, params) => {
    if (method === 'Page.javascriptDialogOpening') {
        if (dialogInterception.enabled && source.tabId === dialogInterception.tabId) {
            // Queue the event for sequential processing
            cdpDialogEventQueue.push({ tabId: source.tabId, params });
            processCdpDialogEventQueue();
        }
    }

    // Handle screencast frames for video recording
    if (method === 'Page.screencastFrame') {
        // Debug: Log every frame event received
        console.log('[Inspekt] screencastFrame received, active:', screencastState.active,
                    'sourceTab:', source.tabId, 'expectedTab:', screencastState.tabId);

        if (screencastState.active && source.tabId === screencastState.tabId) {
            // Log first frame metadata for debugging video dimensions
            if (!screencastState.firstFrameLogged && params.metadata) {
                console.log('[Inspekt] First screencast frame metadata:', params.metadata);
                screencastState.firstFrameLogged = true;
            }

            // POST frame directly to bridge server (bypasses content script which gets lost on navigation)
            // Include metadata for dimension tracking
            fetch(`${BRIDGE_HTTP_URL}/screencast/frame`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    timestamp: Date.now() / 1000,
                    data: params.data,
                    metadata: params.metadata  // Include CDP metadata (deviceWidth, deviceHeight, etc.)
                })
            }).then(resp => {
                if (!resp.ok) console.log('[Inspekt] Frame POST failed:', resp.status);
            }).catch(err => {
                console.log('[Inspekt] Frame POST error:', err);
            });

            // Acknowledge the frame so Chrome sends the next one
            sendDebuggerCommand(source.tabId, 'Page.screencastFrameAck', {
                sessionId: params.sessionId
            }).catch(() => {
                // Ignore ack errors
            });
        } else {
            console.log('[Inspekt] Skipping frame - state mismatch');
        }
    }
});

// Clean up dialog interception when debugger is detached (e.g., user opens DevTools)
chrome.debugger.onDetach.addListener((source, reason) => {
    if (dialogInterception.enabled && source.tabId === dialogInterception.tabId) {
        console.log('[Inspekt] Debugger detached from dialog interception tab, reason:', reason);
        dialogInterception.enabled = false;
        dialogInterception.tabId = null;
        dialogInterception.debuggerAttached = false;
        // Keep queue in case we re-enable
    }

    // Clean up screencast state if debugger is detached during recording
    if (screencastState.active && source.tabId === screencastState.tabId) {
        console.log('[Inspekt] Debugger detached during screencast, reason:', reason);

        // Notify bridge server that recording was interrupted (user opened DevTools, tab closed, etc.)
        const interruptReason = reason === 'target_closed' ? 'tab closed' :
                                reason === 'canceled_by_user' ? 'user opened DevTools' :
                                reason || 'unknown';

        // Send notification to bridge server about the interruption
        fetch(`${BRIDGE_HTTP_URL}/screencast/interrupted`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                reason: interruptReason,
                tabId: source.tabId,
                framesCaptured: screencastState.frameCount || 0
            })
        }).catch(err => {
            console.log('[Inspekt] Could not notify bridge of screencast interruption:', err.message);
        });

        screencastState.active = false;
        screencastState.tabId = null;
        screencastState.debuggerAttached = false;
    }
});

// Log extension initialization
console.log('[Inspekt Extension] Version:', chrome.runtime.getManifest().version);
console.log('[Inspekt Extension] CSP bypass active - works on all websites!');
