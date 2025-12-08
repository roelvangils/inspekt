/**
 * Inspekt - Content Script (Chrome)
 *
 * This script runs on every page and handles:
 * - WebSocket connection to localhost:8766
 * - Message routing between WebSocket and background script
 * - DevTools integration
 */

(function() {
    'use strict';

    // Expose version and status in content script world (isolated)
    window.__INSPEKT_BRIDGE_VERSION__ = '4.2.1';
    window.__INSPEKT_BRIDGE_EXTENSION__ = true;
    window.__INSPEKT_BRIDGE_CSP_BLOCKED__ = false; // Extension bypasses CSP!

    // CRITICAL: Inject into MAIN world via background script
    // (inline script injection is blocked by CSP, even from content scripts)
    chrome.runtime.sendMessage({
        type: 'INJECT_MAIN_WORLD_VARS'
    }).then(() => {
        console.log('[Inspekt] Main world variables injected');
    }).catch(() => {
        // Background script might not be ready yet, that's okay
    });

    // Window Message Bridge
    // Allows MAIN world scripts to communicate with extension APIs
    // MAIN world → window.postMessage → content script → chrome.runtime → background script
    window.addEventListener('message', async (event) => {
        // Only accept messages from same origin (security)
        if (event.source !== window) return;

        const message = event.data;

        // Handle GET_COOKIES_ENHANCED requests from MAIN world
        if (message && message.type === 'INSPEKT_GET_COOKIES_ENHANCED' && message.source === 'inspekt-page') {
            try {
                // Forward to background script
                const response = await chrome.runtime.sendMessage({
                    type: 'GET_COOKIES_ENHANCED'
                });

                // Send response back to MAIN world
                // Security: use location.origin instead of '*' to prevent cross-origin iframes from intercepting
                window.postMessage({
                    type: 'INSPEKT_COOKIES_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                // Send error back to MAIN world
                window.postMessage({
                    type: 'INSPEKT_COOKIES_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: {
                        ok: false,
                        error: String(error)
                    }
                }, location.origin);
            }
        }

        // Handle CAPTURE_SCREENSHOT requests from MAIN world
        if (message && message.type === 'INSPEKT_CAPTURE_SCREENSHOT' && message.source === 'inspekt-page') {
            try {
                const mode = message.mode;
                const options = message.options;

                let result;

                // Full page mode uses CDP directly in background script
                if (mode === 'page') {
                    result = await chrome.runtime.sendMessage({
                        type: 'CAPTURE_FULL_PAGE',
                        options: options
                    });
                } else {
                    // Node and viewport modes use CAPTURE_VISIBLE_TAB + processing
                    const captureResponse = await chrome.runtime.sendMessage({
                        type: 'CAPTURE_VISIBLE_TAB'
                    });

                    if (!captureResponse || !captureResponse.ok) {
                        throw new Error(captureResponse?.error || 'Failed to capture screenshot');
                    }

                    // Process the screenshot in content script (where DOM APIs are available)
                    if (mode === 'node') {
                        result = await processNodeScreenshot(captureResponse.dataUrl, options);
                    } else if (mode === 'viewport') {
                        result = await processViewportScreenshot(captureResponse.dataUrl, options);
                    } else {
                        throw new Error(`Invalid mode: ${mode}`);
                    }
                }

                // Send response back to MAIN world
                window.postMessage({
                    type: 'INSPEKT_SCREENSHOT_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: result
                }, location.origin);
            } catch (error) {
                // Send error back to MAIN world
                window.postMessage({
                    type: 'INSPEKT_SCREENSHOT_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: {
                        ok: false,
                        error: String(error)
                    }
                }, location.origin);
            }
        }
    });

    // Detect if running in VM (Chromium on Linux) and use isolated bridge port
    const isVMBrowser = navigator.userAgent.includes('Linux') &&
                        (navigator.userAgent.includes('Chromium') || navigator.userAgent.includes('Chrome'));
    const WS_PORT = isVMBrowser ? 8768 : 8766;
    const WS_URL = `ws://127.0.0.1:${WS_PORT}/ws`;

    if (isVMBrowser) {
        console.log('[Inspekt] VM environment detected - using isolated bridge port', WS_PORT);
    }

    let ws = null;
    let reconnectTimer = null;
    const RECONNECT_DELAY = 3000;

    console.log('%c[Inspekt Extension]%c Loaded (CSP bypass enabled)',
        'color: #0066ff; font-weight: bold', 'color: inherit');

    function isFrontTab() {
        // Only consider a tab "front" if it's the top-level window (not an iframe)
        // We no longer require visibility - connections are kept alive for hidden tabs too
        return window === window.top;
    }

    function connect() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            return;
        }

        console.log('[Inspekt] Connecting to WebSocket server...');

        try {
            ws = new WebSocket(WS_URL);

            // Notify background script that we're connecting
            chrome.runtime.sendMessage({
                type: 'WS_STATUS_UPDATE',
                connected: 'connecting'
            }).catch(() => {
                // Background script might not be ready
            });

            ws.onopen = () => {
                console.log('%c[Inspekt]%c Connected via WebSocket',
                    'color: #0066ff; font-weight: bold', 'color: inherit');
                if (reconnectTimer) {
                    clearTimeout(reconnectTimer);
                    reconnectTimer = null;
                }
                window.__inspekt_ws__ = ws;

                // Notify background script of connection status
                chrome.runtime.sendMessage({
                    type: 'WS_STATUS_UPDATE',
                    connected: true
                }).catch(() => {
                    // Background script might not be ready
                });

                // Detect browser name from userAgentData (prefer known browsers over generic entries)
                let detectedBrowser = 'Chrome';
                if (navigator.userAgentData?.brands) {
                    const knownBrowsers = ['Google Chrome', 'Chrome', 'Microsoft Edge', 'Brave', 'Opera', 'Vivaldi'];
                    for (const brand of navigator.userAgentData.brands) {
                        if (knownBrowsers.some(known => brand.brand.includes(known))) {
                            detectedBrowser = brand.brand;
                            break;
                        }
                    }
                }

                // Send browser info to server
                const browserInfo = {
                    type: 'browser_info',
                    userAgent: navigator.userAgent,
                    browserName: detectedBrowser,
                    url: window.location.href,
                    title: document.title,
                    extensionVersion: window.__INSPEKT_BRIDGE_VERSION__ || window.__ZEN_BRIDGE_VERSION__ || null,
                    visible: document.visibilityState === 'visible'
                };
                ws.send(JSON.stringify(browserInfo));
            };

            ws.onmessage = async (event) => {
                try {
                    const message = JSON.parse(event.data);
                    console.log('[Inspekt Content] Received WebSocket message:', message.type, message);

                    // Check if this is an identify command (should work even when tab is hidden)
                    const isIdentifyCommand = message.code &&
                        message.code.includes('orange') &&
                        message.code.includes('overlay');

                    // Check if this is an axe accessibility audit (should work even when tab is hidden)
                    // This allows running `inspekt axe` from terminal without browser focus
                    const isAxeCommand = message.code &&
                        message.code.includes('inspekt-axe');

                    // Domain management should work regardless of tab visibility
                    const isDomainManagement = ['DOMAIN_ADD', 'DOMAIN_REMOVE', 'DOMAIN_LIST', 'DOMAIN_BYPASS'].includes(message.type);

                    // CSP bypass management should work regardless of tab visibility
                    const isCspManagement = ['CSP_BYPASS_ENABLE', 'CSP_BYPASS_DISABLE', 'CSP_BYPASS_STATUS', 'CSP_BYPASS_GLOBAL', 'CSP_BYPASS_GLOBAL_STATUS'].includes(message.type);

                    // Console management should work regardless of tab visibility
                    const isConsoleManagement = ['GET_CONSOLE_LOGS', 'CLEAR_CONSOLE_LOGS'].includes(message.type);

                    // Skip visibility check for identify commands, axe commands, pong responses, domain management, CSP management, and console management
                    if (!isFrontTab() && !isIdentifyCommand && !isAxeCommand && !isDomainManagement && !isCspManagement && !isConsoleManagement && message.type !== 'pong') {
                        console.log('[Inspekt] Message dropped - tab not visible/active:', message.type);
                        return;
                    }

                    if (message.type === 'execute') {
                        console.log('[Inspekt Content] Forwarding to background script:', message.code);
                        const requestId = message.request_id;
                        const code = message.code;

                        try {
                            // Send to background script for CSP bypass execution
                            const response = await chrome.runtime.sendMessage({
                                type: 'EXECUTE_CODE',
                                code: code,
                                requestId: requestId
                            });

                            console.log('[Inspekt Content] Response from background:', response);

                            // Send result back via WebSocket
                            ws.send(JSON.stringify({
                                type: 'result',
                                request_id: requestId,
                                ok: response.ok,
                                result: response.result,
                                error: response.error,
                                url: location.href,
                                title: document.title || ''
                            }));
                        } catch (err) {
                            // If background script fails, send error back
                            console.error('[Inspekt] Background script error:', err);
                            ws.send(JSON.stringify({
                                type: 'result',
                                request_id: requestId,
                                ok: false,
                                result: null,
                                error: `Extension error: ${err.message}`,
                                url: location.href,
                                title: document.title || ''
                            }));
                        }

                    } else if (message.type === 'pong') {
                        // Keepalive response

                    } else if (message.type === 'DOMAIN_ADD') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'DOMAIN_ADD',
                                domain: message.domain
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] DOMAIN_ADD error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'DOMAIN_REMOVE') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'DOMAIN_REMOVE',
                                domain: message.domain
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] DOMAIN_REMOVE error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'DOMAIN_LIST') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'DOMAIN_LIST'
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] DOMAIN_LIST error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'DOMAIN_BYPASS') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'DOMAIN_BYPASS',
                                duration: message.duration
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] DOMAIN_BYPASS error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'CSP_BYPASS_ENABLE') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'CSP_BYPASS_ENABLE',
                                domain: message.domain
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] CSP_BYPASS_ENABLE error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'CSP_BYPASS_DISABLE') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'CSP_BYPASS_DISABLE',
                                domain: message.domain
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] CSP_BYPASS_DISABLE error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'CSP_BYPASS_STATUS') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'CSP_BYPASS_STATUS',
                                domain: message.domain
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] CSP_BYPASS_STATUS error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'CSP_BYPASS_GLOBAL') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'CSP_BYPASS_GLOBAL',
                                enabled: message.enabled
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] CSP_BYPASS_GLOBAL error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'CSP_BYPASS_GLOBAL_STATUS') {
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'CSP_BYPASS_GLOBAL_STATUS'
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] CSP_BYPASS_GLOBAL_STATUS error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: { ok: false, error: err.message }
                            }));
                        }

                    } else if (message.type === 'GET_HAR') {
                        // Get HAR data from DevTools (requires DevTools to be open)
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'GET_HAR'
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] GET_HAR error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: false,
                                    error: err.message,
                                    hint: 'Make sure DevTools is open (F12) to capture HAR data.'
                                }
                            }));
                        }

                    } else if (message.type === 'GET_CONSOLE_LOGS') {
                        // Get captured console logs from page
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'GET_CONSOLE_LOGS'
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] GET_CONSOLE_LOGS error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: false,
                                    error: err.message
                                }
                            }));
                        }

                    } else if (message.type === 'CLEAR_CONSOLE_LOGS') {
                        // Clear console logs buffer
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'CLEAR_CONSOLE_LOGS'
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] CLEAR_CONSOLE_LOGS error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: false,
                                    error: err.message
                                }
                            }));
                        }

                    } else if (message.type === 'PERMANENT_BYPASS') {
                        // Enable/disable permanent bypass (for isolated/VM environments)
                        try {
                            const enabled = message.enabled !== false;
                            await ZenPermissions.setPermanentBypass(enabled);

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: true,
                                    enabled: enabled,
                                    message: enabled ?
                                        'Permanent bypass enabled (isolated mode)' :
                                        'Permanent bypass disabled'
                                }
                            }));
                        } catch (err) {
                            console.error('[Inspekt] PERMANENT_BYPASS error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: false,
                                    error: err.message
                                }
                            }));
                        }

                    } else if (message.type === 'REPLAY_MODE_ENABLE') {
                        // Enable replay mode - extension will auto-inject visual script on page loads
                        console.log('[Inspekt Content] REPLAY_MODE_ENABLE received, script length:', message.visualScript?.length);
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'REPLAY_MODE_ENABLE',
                                visualScript: message.visualScript
                            });
                            console.log('[Inspekt Content] REPLAY_MODE_ENABLE response:', response);

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] REPLAY_MODE_ENABLE error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: false,
                                    error: err.message
                                }
                            }));
                        }

                    } else if (message.type === 'REPLAY_MODE_DISABLE') {
                        // Disable replay mode
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'REPLAY_MODE_DISABLE'
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] REPLAY_MODE_DISABLE error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: false,
                                    error: err.message
                                }
                            }));
                        }

                    } else if (message.type === 'REPLAY_MODE_STATUS') {
                        // Get replay mode status
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'REPLAY_MODE_STATUS'
                            });

                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: response
                            }));
                        } catch (err) {
                            console.error('[Inspekt] REPLAY_MODE_STATUS error:', err);
                            ws.send(JSON.stringify({
                                type: 'response',
                                requestId: message.requestId,
                                response: {
                                    ok: false,
                                    error: err.message
                                }
                            }));
                        }
                    }

                } catch (err) {
                    console.error('[Inspekt] Error handling message:', err);
                }
            };

            ws.onclose = (event) => {
                console.log('[Inspekt] Disconnected (code:', event.code, '). Reconnecting...');
                ws = null;
                window.__inspekt_ws__ = null;

                // Notify background script of disconnection
                chrome.runtime.sendMessage({
                    type: 'WS_STATUS_UPDATE',
                    connected: false
                }).catch(() => {
                    // Background script might not be ready
                });

                scheduleReconnect();
            };

            ws.onerror = (error) => {
                console.error('[Inspekt] WebSocket error:', error);
            };

        } catch (err) {
            console.error('[Inspekt] Failed to connect:', err);
            scheduleReconnect();
        }
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;

        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connect();
        }, RECONNECT_DELAY);
    }

    // Keepalive ping every 30 seconds
    setInterval(() => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000);

    // Handle visibility changes - send visibility updates instead of disconnecting
    document.addEventListener('visibilitychange', async () => {
        const isVisible = document.visibilityState === 'visible';

        if (isVisible && window === window.top) {
            // Tab became visible - connect if needed and domain is allowed
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                const allowed = await ZenPermissions.isAllowed();
                if (allowed) {
                    connect();
                }
            } else {
                // Already connected - send visibility update
                ws.send(JSON.stringify({
                    type: 'visibility_change',
                    visible: true
                }));
            }
        } else if (!isVisible && ws && ws.readyState === WebSocket.OPEN) {
            // Tab became hidden - send visibility update but keep connection alive
            console.log('[Inspekt] Tab hidden, sending visibility update (connection stays alive)');
            ws.send(JSON.stringify({
                type: 'visibility_change',
                visible: false
            }));
        }
    });

    // DevTools integration is now injected via background script
    // (inline script injection is blocked by CSP)

    // Initial connection - always connect if this is a front tab
    // Permission check happens on code execution, not on connection
    // This allows the bridge to send permission/bypass commands even before domain is allowed
    async function initializeConnection() {
        if (isFrontTab()) {
            // Always connect to allow bridge to send bypass commands
            // The permission check happens in the message handler before executing code
            console.log('[Inspekt] Initializing connection...');
            connect();
        }
    }

    // Handle permission changes (called when domains are added/removed via CLI)
    // This enables commands to work immediately after adding a domain - no page refresh needed
    async function handlePermissionChange() {
        if (isFrontTab()) {
            const allowed = await ZenPermissions.isAllowed();
            if (allowed && (!ws || ws.readyState !== WebSocket.OPEN)) {
                console.log('[Inspekt] Permissions changed - domain now allowed, reconnecting...');
                connect();
            } else if (!allowed && ws && ws.readyState === WebSocket.OPEN) {
                console.log('[Inspekt] Permissions changed - domain no longer allowed, disconnecting...');
                ws.close();
                ws = null;
                window.__inspekt_ws__ = null;
            }
        }
    }

    initializeConnection();

    // Message listener for DevTools panel requests and permission changes
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        // Handle permission changes from background script
        // This is triggered when domains are added/removed via CLI
        if (message.type === 'PERMISSIONS_CHANGED') {
            handlePermissionChange();
            sendResponse({ ok: true });
            return true;
        }

        if (message.action === 'getElementBounds') {
            // Get element bounds for screenshot
            try {
                const element = document.querySelector(message.selector);
                if (element) {
                    const rect = element.getBoundingClientRect();

                    // Use left/top instead of x/y for better compatibility
                    // These are relative to the viewport (what captureVisibleTab captures)
                    const bounds = {
                        x: rect.left,
                        y: rect.top,
                        width: rect.width,
                        height: rect.height,
                        top: rect.top,
                        left: rect.left,
                        right: rect.right,
                        bottom: rect.bottom
                    };

                    console.log('[Content Script] Element bounds:', bounds);
                    console.log('[Content Script] Window scroll:', window.scrollX, window.scrollY);
                    console.log('[Content Script] Device pixel ratio:', window.devicePixelRatio);

                    sendResponse({
                        success: true,
                        bounds: {
                            ...bounds,
                            devicePixelRatio: window.devicePixelRatio,
                            scrollX: window.scrollX,
                            scrollY: window.scrollY
                        }
                    });
                } else {
                    sendResponse({
                        success: false,
                        error: 'Element not found'
                    });
                }
            } catch (error) {
                sendResponse({
                    success: false,
                    error: error.message
                });
            }
            return true; // Keep message channel open for async response
        } else if (message.action === 'scrollIntoView') {
            // Scroll element into view
            try {
                const element = document.querySelector(message.selector);
                if (element) {
                    element.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center',
                        inline: 'center'
                    });
                    sendResponse({ success: true });
                } else {
                    sendResponse({
                        success: false,
                        error: 'Element not found'
                    });
                }
            } catch (error) {
                sendResponse({
                    success: false,
                    error: error.message
                });
            }
            return true;
        } else if (message.action === 'hideOutline') {
            // Hide both the persistent outline and the highlightBox
            try {
                // Hide persistent outline (legacy system)
                const element = document.querySelector('[data-inspekt-outline="true"]');
                if (element) {
                    // Store current outline styles so we can restore them
                    element.setAttribute('data-inspekt-hidden-outline', element.style.outline || '');
                    element.setAttribute('data-inspekt-hidden-outline-offset', element.style.outlineOffset || '');

                    // Remove outline styles
                    element.style.outline = 'none';
                    element.style.outlineOffset = '';

                    console.log('[Content Script] Persistent outline hidden');
                }

                // Hide highlightBox (new system) by injecting code into page context
                const script = document.createElement('script');
                script.textContent = `
                    (function() {
                        // Store current highlightBox state
                        const highlightBox = document.querySelector('[style*="z-index: 2147483646"]');
                        if (highlightBox && highlightBox.style.display !== 'none') {
                            highlightBox.setAttribute('data-inspekt-hidden-highlight', 'true');
                            highlightBox.style.display = 'none';
                            console.log('[Inspekt] HighlightBox hidden for screenshot');
                        }
                    })();
                `;
                document.documentElement.appendChild(script);
                script.remove();

                console.log('[Content Script] All highlights hidden');
                sendResponse({ success: true });
            } catch (error) {
                sendResponse({
                    success: false,
                    error: error.message
                });
            }
            return true;
        } else if (message.action === 'showOutline') {
            // Restore both the persistent outline and the highlightBox
            try {
                // Restore persistent outline (legacy system)
                const element = document.querySelector('[data-inspekt-outline="true"]');
                if (element) {
                    // Restore outline styles
                    const hiddenOutline = element.getAttribute('data-inspekt-hidden-outline');
                    const hiddenOffset = element.getAttribute('data-inspekt-hidden-outline-offset');

                    if (hiddenOutline !== null) {
                        element.style.outline = hiddenOutline;
                        element.style.outlineOffset = hiddenOffset;

                        // Clean up temporary attributes
                        element.removeAttribute('data-inspekt-hidden-outline');
                        element.removeAttribute('data-inspekt-hidden-outline-offset');
                    }

                    console.log('[Content Script] Persistent outline restored');
                }

                // Restore highlightBox (new system) by injecting code into page context
                const script = document.createElement('script');
                script.textContent = `
                    (function() {
                        // Restore highlightBox if it was hidden
                        const highlightBox = document.querySelector('[data-inspekt-hidden-highlight="true"]');
                        if (highlightBox) {
                            highlightBox.removeAttribute('data-inspekt-hidden-highlight');

                            // Update highlight to restore position
                            if (typeof window.__INSPEKT_UPDATE_HIGHLIGHT__ === 'function') {
                                window.__INSPEKT_UPDATE_HIGHLIGHT__();
                            } else {
                                // Fallback: just show it
                                highlightBox.style.display = 'block';
                            }
                            console.log('[Inspekt] HighlightBox restored after screenshot');
                        }
                    })();
                `;
                document.documentElement.appendChild(script);
                script.remove();

                console.log('[Content Script] All highlights restored');
                sendResponse({ success: true });
            } catch (error) {
                sendResponse({
                    success: false,
                    error: error.message
                });
            }
            return true;
        }
    });

    //=============================================================================
    // Screenshot Processing Functions (DOM APIs available in content script)
    //=============================================================================

    /**
     * Process node screenshot with cropping and options
     */
    async function processNodeScreenshot(dataUrl, options) {
        const {
            bounds,
            selector,
            tagName,
            margin = 0,
            marginColor = 'auto',
            scale = 2,
            quality = 0.92,
            format = 'png'
        } = options;

        return cropImageWithOptions(dataUrl, bounds, {
            margin,
            marginColor,
            scale,
            quality,
            format,
            selector,
            tagName
        });
    }

    /**
     * Process viewport screenshot with options
     */
    async function processViewportScreenshot(dataUrl, options) {
        const {
            margin = 0,
            marginColor = 'auto',
            scale = 2,
            quality = 0.92,
            format = 'png'
        } = options;

        return processImage(dataUrl, {
            margin,
            marginColor,
            scale,
            quality,
            format
        });
    }

    /**
     * Crop image to element bounds with options
     */
    async function cropImageWithOptions(dataUrl, rect, options) {
        const {
            margin = 0,
            marginColor = 'auto',
            scale = 2,
            quality = 0.92,
            format = 'png',
            selector = '',
            tagName = ''
        } = options;

        return new Promise((resolve, reject) => {
            const img = new Image();

            img.onload = () => {
                try {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');

                    const dpr = rect.devicePixelRatio || window.devicePixelRatio || 1;

                    // Calculate source coordinates
                    const sourceX = rect.x * dpr;
                    const sourceY = rect.y * dpr;
                    const sourceWidth = rect.width * dpr;
                    const sourceHeight = rect.height * dpr;

                    // Calculate canvas size with margin
                    const marginScaled = margin * scale;
                    canvas.width = (rect.width * scale) + (marginScaled * 2);
                    canvas.height = (rect.height * scale) + (marginScaled * 2);

                    // Determine background color
                    let bgColor = '#ffffff';
                    if (marginColor === 'auto') {
                        const tempCanvas = document.createElement('canvas');
                        const tempCtx = tempCanvas.getContext('2d');
                        tempCanvas.width = 1;
                        tempCanvas.height = 1;
                        tempCtx.drawImage(img, sourceX, sourceY, 1, 1, 0, 0, 1, 1);
                        const pixelData = tempCtx.getImageData(0, 0, 1, 1).data;
                        if (pixelData[3] > 0) {
                            bgColor = `rgb(${pixelData[0]}, ${pixelData[1]}, ${pixelData[2]})`;
                        }
                    } else {
                        bgColor = marginColor;
                    }

                    // Fill with background
                    ctx.fillStyle = bgColor;
                    ctx.fillRect(0, 0, canvas.width, canvas.height);

                    // Draw image
                    ctx.drawImage(
                        img,
                        sourceX, sourceY, sourceWidth, sourceHeight,
                        marginScaled, marginScaled,
                        rect.width * scale, rect.height * scale
                    );

                    // Convert to format
                    const mimeType = format === 'jpg' ? 'image/jpeg' :
                                   format === 'webp' ? 'image/webp' : 'image/png';
                    const outputDataUrl = canvas.toDataURL(mimeType, quality);

                    // Calculate file size
                    const base64Data = outputDataUrl.split(',')[1];
                    const fileSize = Math.round((base64Data.length * 3) / 4);

                    resolve({
                        ok: true,
                        dataUrl: outputDataUrl,
                        width: canvas.width,
                        height: canvas.height,
                        fileSize: fileSize,
                        selector: selector,
                        tagName: tagName
                    });
                } catch (error) {
                    reject(new Error(`Failed to crop image: ${error.message}`));
                }
            };

            img.onerror = () => reject(new Error('Failed to load source image'));
            img.src = dataUrl;
        });
    }

    /**
     * Process image with margin, scale, format
     */
    async function processImage(dataUrl, options) {
        const {
            margin = 0,
            marginColor = 'auto',
            scale = 1,
            quality = 0.92,
            format = 'png'
        } = options;

        return new Promise((resolve, reject) => {
            const img = new Image();

            img.onload = () => {
                try {
                    const canvas = document.createElement('canvas');
                    const ctx = canvas.getContext('2d');

                    const marginScaled = margin * scale;
                    canvas.width = (img.width * scale) + (marginScaled * 2);
                    canvas.height = (img.height * scale) + (marginScaled * 2);

                    let bgColor = '#ffffff';
                    if (marginColor === 'auto' && margin > 0) {
                        const tempCanvas = document.createElement('canvas');
                        const tempCtx = tempCanvas.getContext('2d');
                        tempCanvas.width = 1;
                        tempCanvas.height = 1;
                        tempCtx.drawImage(img, 0, 0, 1, 1, 0, 0, 1, 1);
                        const pixelData = tempCtx.getImageData(0, 0, 1, 1).data;
                        if (pixelData[3] > 0) {
                            bgColor = `rgb(${pixelData[0]}, ${pixelData[1]}, ${pixelData[2]})`;
                        }
                    } else if (marginColor !== 'auto') {
                        bgColor = marginColor;
                    }

                    ctx.fillStyle = bgColor;
                    ctx.fillRect(0, 0, canvas.width, canvas.height);

                    ctx.drawImage(
                        img,
                        0, 0, img.width, img.height,
                        marginScaled, marginScaled,
                        img.width * scale, img.height * scale
                    );

                    const mimeType = format === 'jpg' ? 'image/jpeg' :
                                   format === 'webp' ? 'image/webp' : 'image/png';
                    const outputDataUrl = canvas.toDataURL(mimeType, quality);

                    const base64Data = outputDataUrl.split(',')[1];
                    const fileSize = Math.round((base64Data.length * 3) / 4);

                    resolve({
                        ok: true,
                        dataUrl: outputDataUrl,
                        width: canvas.width,
                        height: canvas.height,
                        fileSize: fileSize
                    });
                } catch (error) {
                    reject(new Error(`Failed to process image: ${error.message}`));
                }
            };

            img.onerror = () => reject(new Error('Failed to load source image'));
            img.src = dataUrl;
        });
    }

})();
