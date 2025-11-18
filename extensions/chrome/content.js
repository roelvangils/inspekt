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
                window.postMessage({
                    type: 'INSPEKT_COOKIES_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, '*');
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
                }, '*');
            }
        }
    });

    const WS_URL = 'ws://127.0.0.1:8766/ws';
    let ws = null;
    let reconnectTimer = null;
    const RECONNECT_DELAY = 3000;

    console.log('%c[Inspekt Extension]%c Loaded (CSP bypass enabled)',
        'color: #0066ff; font-weight: bold', 'color: inherit');

    function isFrontTab() {
        // Only consider a tab "front" if it's visible AND the top-level window
        return document.visibilityState === 'visible' && window === window.top;
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

                // Send browser info to server
                const browserInfo = {
                    type: 'browser_info',
                    userAgent: navigator.userAgent,
                    browserName: navigator.userAgentData?.brands?.[0]?.brand || 'Chrome',
                    url: window.location.href,
                    title: document.title,
                    extensionVersion: window.__INSPEKT_BRIDGE_VERSION__ || window.__ZEN_BRIDGE_VERSION__ || null
                };
                ws.send(JSON.stringify(browserInfo));
            };

            ws.onmessage = async (event) => {
                if (!isFrontTab()) {
                    return;
                }

                try {
                    const message = JSON.parse(event.data);

                    if (message.type === 'execute') {
                        const requestId = message.request_id;
                        const code = message.code;

                        try {
                            // Send to background script for CSP bypass execution
                            const response = await chrome.runtime.sendMessage({
                                type: 'EXECUTE_CODE',
                                code: code,
                                requestId: requestId
                            });

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

    // Handle visibility changes to connect/disconnect appropriately
    document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState === 'visible' && window === window.top) {
            // Tab became visible - connect if needed and domain is allowed
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                const allowed = await ZenPermissions.isAllowed();
                if (allowed) {
                    connect();
                }
            }
        } else if (document.visibilityState === 'hidden') {
            // Tab became hidden - disconnect to save resources
            if (ws && ws.readyState === WebSocket.OPEN) {
                console.log('[Inspekt] Tab hidden, closing connection');
                ws.close();
                ws = null;
                window.__inspekt_ws__ = null;
            }
        }
    });

    // DevTools integration is now injected via background script
    // (inline script injection is blocked by CSP)

    // Initial connection - only connect if this is a visible top-level tab AND domain is allowed
    async function initializeConnection() {
        if (isFrontTab()) {
            // Check if domain is allowed (will show opt-in modal if not)
            const allowed = await ZenPermissions.checkAndRequest();
            if (allowed) {
                console.log('[Inspekt] Domain authorized, connecting...');
                connect();
            } else {
                console.log('[Inspekt] Domain not authorized. Connection blocked.');
            }
        }
    }

    initializeConnection();

    // Message listener for DevTools panel requests
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
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

})();
