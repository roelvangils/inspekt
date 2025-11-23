/**
 * Inspekt - Content Script (Firefox)
 *
 * This script runs on every page and handles:
 * - WebSocket connection to localhost:8766
 * - Message routing between WebSocket and background script
 * - Window message bridge for extension API access
 */

(function() {
    'use strict';

    // Expose version and status in BOTH isolated world (content script) AND main world (page)
    // Content script world (for content script use)
    window.__INSPEKT_BRIDGE_VERSION__ = '4.3.1';
    window.__INSPEKT_BRIDGE_EXTENSION__ = true;
    window.__INSPEKT_BRIDGE_CSP_BLOCKED__ = false; // Extension bypasses CSP!
    window.__INSPEKT_WS_CONNECTED__ = false;

    // CRITICAL: Also inject into MAIN world so it's accessible when code is executed
    // via browser.tabs.executeScript (which runs in main world, not isolated world)
    const script = document.createElement('script');
    script.textContent = `
        window.__INSPEKT_BRIDGE_VERSION__ = '4.3.1';
        window.__INSPEKT_BRIDGE_EXTENSION__ = true;
        window.__INSPEKT_BRIDGE_CSP_BLOCKED__ = false;
        window.__INSPEKT_WS_CONNECTED__ = false;
    `;
    (document.head || document.documentElement).appendChild(script);
    script.remove();

    console.log('%c[Inspekt Extension]%c Loaded (CSP bypass enabled)',
        'color: #0066ff; font-weight: bold', 'color: inherit');

    // Window Message Bridge
    // Allows MAIN world scripts to communicate with extension APIs
    window.addEventListener('message', async (event) => {
        // Only accept messages from same origin (security)
        if (event.source !== window) return;

        const message = event.data;

        // Handle GET_COOKIES_ENHANCED requests from MAIN world
        if (message && message.type === 'INSPEKT_GET_COOKIES_ENHANCED' && message.source === 'inspekt-page') {
            try {
                // Forward to background script
                const response = await browser.runtime.sendMessage({
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

    // Listen for WebSocket status updates from the WebSocket client
    // and inject them into MAIN world so popup can read them
    window.addEventListener('__inspekt_ws_status_change__', (event) => {
        const status = event.detail;
        const script = document.createElement('script');
        script.textContent = `window.__INSPEKT_WS_CONNECTED__ = ${JSON.stringify(status)};`;
        (document.head || document.documentElement).appendChild(script);
        script.remove();
    });

    // Listen for messages from popup/background requesting connection status
    browser.runtime.onMessage.addListener((message, sender, sendResponse) => {
        if (message.type === 'GET_WS_STATUS') {
            // Return current WebSocket connection status
            const wsConnected = window.__INSPEKT_WS_CONNECTED__;
            const extensionLoaded = window.__INSPEKT_BRIDGE_EXTENSION__;

            const status = (wsConnected === true) ? 'connected' :
                          (extensionLoaded ? 'loaded' : 'not-loaded');

            console.log('[Inspekt Content] GET_WS_STATUS request:', {
                wsConnected,
                extensionLoaded,
                status
            });

            sendResponse({ status: status });
            return true; // Keep channel open for async response
        }
    });

    // Initialize permission check and WebSocket connection
    // This uses the shared WebSocket client from websocket-client.js when available
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            if (typeof InspektWebSocketClient !== 'undefined') {
                InspektWebSocketClient.initialize();
            }
        });
    } else {
        // Document already loaded
        if (typeof InspektWebSocketClient !== 'undefined') {
            InspektWebSocketClient.initialize();
        }
    }

})();
