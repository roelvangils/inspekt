/**
 * Inspekt - WebSocket Client (Shared)
 *
 * Cross-browser WebSocket connection handler
 * Used by both Chrome and Firefox extensions
 *
 * Dependencies:
 * - BrowserAPI (adapter for chrome/browser APIs)
 * - Permissions module for domain checking
 */

const InspektWebSocketClient = (() => {
    const WS_URL = 'ws://127.0.0.1:8766/ws';
    const RECONNECT_DELAY = 3000;
    const KEEPALIVE_INTERVAL = 30000;

    let ws = null;
    let reconnectTimer = null;
    let keepaliveTimer = null;
    let isConnected = false;

    /**
     * Check if this is the front tab (top-level window, not an iframe)
     * We no longer require visibility - connections are kept alive for hidden tabs too
     */
    function isFrontTab() {
        return window === window.top;
    }

    /**
     * Update connection status in MAIN world
     */
    function updateMainWorldStatus(connected) {
        isConnected = connected;
        if (typeof window !== 'undefined') {
            window.__INSPEKT_WS_CONNECTED__ = connected;

            // Dispatch custom event for content script to update MAIN world
            // (Firefox needs this because tabs.executeScript reads from page context)
            window.dispatchEvent(new CustomEvent('__inspekt_ws_status_change__', {
                detail: connected
            }));
        }
    }

    /**
     * Notify background script of connection status
     */
    async function notifyBackgroundScript(connected, status) {
        try {
            if (typeof chrome !== 'undefined' && chrome.runtime) {
                await chrome.runtime.sendMessage({
                    type: 'WS_STATUS_UPDATE',
                    connected: connected,
                    status: status
                });
            } else if (typeof browser !== 'undefined' && browser.runtime) {
                await browser.runtime.sendMessage({
                    type: 'WS_STATUS_UPDATE',
                    connected: connected,
                    status: status
                });
            }
        } catch (e) {
            // Background script might not be ready
        }
    }

    /**
     * Send browser info to WebSocket server
     */
    function sendBrowserInfo() {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;

        // Detect browser name from userAgentData (prefer known browsers over generic entries)
        let detectedBrowser = 'Unknown';
        if (navigator.userAgentData?.brands) {
            const knownBrowsers = ['Google Chrome', 'Chrome', 'Microsoft Edge', 'Brave', 'Opera', 'Vivaldi', 'Firefox'];
            for (const brand of navigator.userAgentData.brands) {
                if (knownBrowsers.some(known => brand.brand.includes(known))) {
                    detectedBrowser = brand.brand;
                    break;
                }
            }
        }
        // Fallback: try to detect from userAgent string
        if (detectedBrowser === 'Unknown') {
            const ua = navigator.userAgent;
            if (ua.includes('Firefox/')) detectedBrowser = 'Firefox';
            else if (ua.includes('Edg/')) detectedBrowser = 'Edge';
            else if (ua.includes('Chrome/')) detectedBrowser = 'Chrome';
            else if (ua.includes('Safari/')) detectedBrowser = 'Safari';
        }

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
    }

    /**
     * Send keepalive ping
     */
    function sendKeepalive() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
        }
    }

    /**
     * Clear keepalive timer
     */
    function clearKeepaliveTimer() {
        if (keepaliveTimer) {
            clearInterval(keepaliveTimer);
            keepaliveTimer = null;
        }
    }

    /**
     * Start keepalive ping interval
     */
    function startKeepaliveTimer() {
        clearKeepaliveTimer();
        keepaliveTimer = setInterval(sendKeepalive, KEEPALIVE_INTERVAL);
    }

    /**
     * Handle WebSocket message
     */
    async function handleMessage(event) {
        try {
            const message = JSON.parse(event.data);

            // Console management should work regardless of tab visibility
            const isConsoleManagement = ['GET_CONSOLE_LOGS', 'CLEAR_CONSOLE_LOGS'].includes(message.type);

            // Skip visibility check for console management and pong responses
            if (!isFrontTab() && !isConsoleManagement && message.type !== 'pong') {
                return;
            }

            if (message.type === 'execute') {
                const requestId = message.request_id;
                const code = message.code;

                // Check domain authorization before executing code
                const permModule = typeof ZenPermissions !== 'undefined' ? ZenPermissions :
                                   (typeof InspektPermissions !== 'undefined' ? InspektPermissions : null);

                if (!permModule) {
                    ws.send(JSON.stringify({
                        type: 'result',
                        request_id: requestId,
                        ok: false,
                        result: null,
                        error: 'Permission system not available',
                        url: location.href,
                        title: document.title || ''
                    }));
                    return;
                }

                const allowed = await permModule.isAllowed();
                if (!allowed) {
                    // Extract domain from current URL
                    const currentDomain = location.hostname;

                    // Create helpful error message with specific domain
                    const errorMessage = `Sorry, I'm not allowed to access this domain. To add this domain permanently, use the following command:\n\ninspekt domain add ${currentDomain}\n\nAlternatively, you can temporarily allow all domains with this command:\n\ninspekt domain bypass [DURATION IN MINUTES]`;

                    ws.send(JSON.stringify({
                        type: 'result',
                        request_id: requestId,
                        ok: false,
                        result: null,
                        error: errorMessage,
                        url: location.href,
                        title: document.title || ''
                    }));
                    return;
                }

                try {
                    // Send to background script for CSP bypass execution
                    const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                    const response = await runtimeAPI.sendMessage({
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
                // Forward domain add request to background script
                const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                try {
                    const response = await runtimeAPI.sendMessage({
                        type: 'DOMAIN_ADD',
                        domain: message.domain
                    });

                    // Send response back via WebSocket
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: response
                    }));
                } catch (err) {
                    console.error('[Inspekt] Error handling DOMAIN_ADD:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }

            } else if (message.type === 'DOMAIN_REMOVE') {
                // Forward domain remove request to background script
                const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                try {
                    const response = await runtimeAPI.sendMessage({
                        type: 'DOMAIN_REMOVE',
                        domain: message.domain
                    });

                    // Send response back via WebSocket
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: response
                    }));
                } catch (err) {
                    console.error('[Inspekt] Error handling DOMAIN_REMOVE:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }

            } else if (message.type === 'DOMAIN_LIST') {
                // Forward domain list request to background script
                const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                try {
                    const response = await runtimeAPI.sendMessage({
                        type: 'DOMAIN_LIST'
                    });

                    // Send response back via WebSocket
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: response
                    }));
                } catch (err) {
                    console.error('[Inspekt] Error handling DOMAIN_LIST:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }

            } else if (message.type === 'DOMAIN_BYPASS') {
                // Forward domain bypass request to background script
                const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                try {
                    const response = await runtimeAPI.sendMessage({
                        type: 'DOMAIN_BYPASS',
                        duration: message.duration
                    });

                    // Send response back via WebSocket
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: response
                    }));
                } catch (err) {
                    console.error('[Inspekt] Error handling DOMAIN_BYPASS:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }

            } else if (message.type === 'SYNC_ALLOWED_DOMAINS') {
                // Forward domain sync request to background script
                const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                try {
                    const response = await runtimeAPI.sendMessage({
                        type: 'SYNC_ALLOWED_DOMAINS',
                        domains: message.domains
                    });

                    // Send response back via WebSocket
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: response
                    }));
                } catch (err) {
                    console.error('[Inspekt] Error handling SYNC_ALLOWED_DOMAINS:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }

            } else if (message.type === 'GET_CONSOLE_LOGS') {
                // Forward console logs request to background script
                const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                try {
                    const response = await runtimeAPI.sendMessage({
                        type: 'GET_CONSOLE_LOGS'
                    });

                    // Send response back via WebSocket
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: response
                    }));
                } catch (err) {
                    console.error('[Inspekt] Error handling GET_CONSOLE_LOGS:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }

            } else if (message.type === 'CLEAR_CONSOLE_LOGS') {
                // Forward clear console logs request to background script
                const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime : browser.runtime;
                try {
                    const response = await runtimeAPI.sendMessage({
                        type: 'CLEAR_CONSOLE_LOGS'
                    });

                    // Send response back via WebSocket
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: response
                    }));
                } catch (err) {
                    console.error('[Inspekt] Error handling CLEAR_CONSOLE_LOGS:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }

            } else if (message.type === 'PERMANENT_BYPASS') {
                // Enable/disable permanent bypass (for isolated/VM environments)
                const permModule = typeof ZenPermissions !== 'undefined' ? ZenPermissions :
                                   (typeof InspektPermissions !== 'undefined' ? InspektPermissions : null);
                try {
                    if (!permModule || !permModule.setPermanentBypass) {
                        throw new Error('Permission system not available');
                    }

                    const enabled = message.enabled !== false;
                    await permModule.setPermanentBypass(enabled);

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
                    console.error('[Inspekt] Error handling PERMANENT_BYPASS:', err);
                    ws.send(JSON.stringify({
                        type: 'response',
                        requestId: message.requestId,
                        response: { ok: false, error: String(err) }
                    }));
                }
            }

        } catch (err) {
            console.error('[Inspekt] Error handling message:', err);
        }
    }

    /**
     * Connect to WebSocket server
     */
    function connect() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            return;
        }

        console.log('[Inspekt] Connecting to WebSocket server…');

        try {
            ws = new WebSocket(WS_URL);

            notifyBackgroundScript('connecting', 'Connecting to server');

            ws.onopen = () => {
                console.log('%c[Inspekt]%c Connected via WebSocket',
                    'color: #0066ff; font-weight: bold', 'color: inherit');
                updateMainWorldStatus(true);
                notifyBackgroundScript(true, 'Connected');

                if (reconnectTimer) {
                    clearTimeout(reconnectTimer);
                    reconnectTimer = null;
                }

                sendBrowserInfo();
                startKeepaliveTimer();
            };

            ws.onmessage = handleMessage;

            ws.onclose = (event) => {
                console.log('[Inspekt] Disconnected (code:', event.code, '). Reconnecting…');
                ws = null;
                updateMainWorldStatus(false);
                clearKeepaliveTimer();
                notifyBackgroundScript(false, 'Disconnected');
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

    /**
     * Schedule reconnection attempt
     */
    function scheduleReconnect() {
        if (reconnectTimer) return;

        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connect();
        }, RECONNECT_DELAY);
    }

    /**
     * Initialize WebSocket connection
     * Note: Connection is always established, but code execution requires domain authorization
     */
    async function initialize() {
        if (isFrontTab()) {
            console.log('[Inspekt] Initializing WebSocket connection…');
            connect();
        }
    }

    /**
     * Handle visibility changes - send visibility updates instead of disconnecting
     */
    document.addEventListener('visibilitychange', async () => {
        const isVisible = document.visibilityState === 'visible';

        if (isVisible && window === window.top) {
            // Tab became visible - reconnect if needed
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                connect();
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

    /**
     * Handle permission changes (called when domains are added/removed via CLI)
     * This enables commands to work immediately after adding a domain - no page refresh needed
     */
    async function handlePermissionChange() {
        if (isFrontTab()) {
            // Always try to connect/reconnect when permissions change
            // The permission check happens per-request in ws.onmessage
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                console.log('[Inspekt] Permissions changed, reconnecting…');
                connect();
            }
        }
    }

    // Public API
    return {
        initialize,
        connect,
        disconnect: () => {
            if (ws) {
                ws.close();
                ws = null;
                updateMainWorldStatus(false);
                clearKeepaliveTimer();
            }
        },
        isConnected: () => isConnected,
        getWebSocket: () => ws,
        handlePermissionChange
    };
})();
