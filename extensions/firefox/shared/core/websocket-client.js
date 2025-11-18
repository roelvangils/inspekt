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
     * Check if this is the front tab (visible and top-level window)
     */
    function isFrontTab() {
        return document.visibilityState === 'visible' && window === window.top;
    }

    /**
     * Update connection status in MAIN world
     */
    function updateMainWorldStatus(connected) {
        isConnected = connected;
        if (typeof window !== 'undefined') {
            window.__INSPEKT_WS_CONNECTED__ = connected;
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

        const browserInfo = {
            type: 'browser_info',
            userAgent: navigator.userAgent,
            browserName: navigator.userAgentData?.brands?.[0]?.brand || 'Unknown',
            url: window.location.href,
            title: document.title,
            extensionVersion: window.__INSPEKT_BRIDGE_VERSION__ || window.__ZEN_BRIDGE_VERSION__ || null
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

            // Check if this is an identify/flash command (should work even when tab is hidden)
            const isIdentifyCommand = message.code &&
                message.code.includes('orange') &&
                message.code.includes('overlay');

            // Skip visibility check for identify commands and pong responses
            if (!isFrontTab() && !isIdentifyCommand && message.type !== 'pong') {
                console.log('[Inspekt] Message dropped - tab not visible/active:', message.type);
                return;
            }

            console.log('[Inspekt] Processing message:', message.type);

            if (message.type === 'execute') {
                const requestId = message.request_id;
                const code = message.code;

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

        console.log('[Inspekt] Connecting to WebSocket server...');

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
                console.log('[Inspekt] Disconnected (code:', event.code, '). Reconnecting...');
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
     * Initialize connection with domain check
     */
    async function initialize() {
        if (isFrontTab()) {
            // Check if domain is allowed (will show opt-in modal if not)
            const allowed = await (typeof ZenPermissions !== 'undefined' ?
                ZenPermissions.checkAndRequest() :
                (typeof InspektPermissions !== 'undefined' ? InspektPermissions.checkAndRequest() : false));

            if (allowed) {
                console.log('[Inspekt] Domain authorized, connecting...');
                connect();
            } else {
                console.log('[Inspekt] Domain not authorized. Connection blocked.');
            }
        }
    }

    /**
     * Handle visibility changes
     */
    document.addEventListener('visibilitychange', async () => {
        if (document.visibilityState === 'visible' && window === window.top) {
            // Tab became visible - connect if needed and domain is allowed
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                const permModule = typeof ZenPermissions !== 'undefined' ? ZenPermissions :
                                   (typeof InspektPermissions !== 'undefined' ? InspektPermissions : null);
                if (permModule) {
                    const allowed = await permModule.isAllowed();
                    if (allowed) {
                        connect();
                    }
                }
            }
        } else if (document.visibilityState === 'hidden') {
            // Tab became hidden - disconnect to save resources
            if (ws && ws.readyState === WebSocket.OPEN) {
                console.log('[Inspekt] Tab hidden, closing connection');
                ws.close();
                ws = null;
                updateMainWorldStatus(false);
                clearKeepaliveTimer();
            }
        }
    });

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
        getWebSocket: () => ws
    };
})();
