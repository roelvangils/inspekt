// ==UserScript==
// @name         Inspekt (WebSocket)
// @namespace    inspekt
// @version      3.5
// @description  Execute JavaScript in the active tab via Inspekt CLI (WebSocket version)
// @match        *://*/*
// @run-at       document-idle
// @grant        none
// @connect      127.0.0.1
// @connect      localhost
// @updateURL    https://raw.githubusercontent.com/roelvangils/inspekt/main/userscript_ws.js
// @downloadURL  https://raw.githubusercontent.com/roelvangils/inspekt/main/userscript_ws.js
// ==/UserScript==

(function () {
    'use strict';

    // Expose version for CLI to read
    window.__INSPEKT_BRIDGE_VERSION__ = '3.5';
    window.__INSPEKT_BRIDGE_CSP_BLOCKED__ = false;

    const WS_URL = 'ws://127.0.0.1:8766/ws'; // WebSocket URL
    let ws = null;
    let reconnectTimer = null;
    const RECONNECT_DELAY = 3000; // 3 seconds
    let cspDetected = false; // Track if CSP is blocking us
    let connectionAttempts = 0;

    // Store WebSocket globally so it persists across page navigations
    window.__inspekt_ws__ = null;

    function isFrontTab() {
        // Only execute in the visible top-level frame
        return document.visibilityState === 'visible' && window === window.top;
    }

    function detectCSP() {
        // Check for CSP meta tags
        const cspMeta = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
        if (cspMeta) {
            const content = cspMeta.getAttribute('content') || '';
            if (content.includes('connect-src') && !content.includes('ws://') && !content.includes('localhost')) {
                return 'meta-tag (connect-src blocks WebSocket)';
            }
        }

        // Test if eval is blocked by trying it
        try {
            (0, eval)('1+1');
        } catch (e) {
            if (e instanceof EvalError || (e.message && e.message.includes('Content Security Policy'))) {
                return 'eval blocked by CSP (script-src missing unsafe-eval)';
            }
        }

        return null;
    }

    function showCSPWarning(reason) {
        if (cspDetected) return; // Already warned
        cspDetected = true;

        console.group('%c⚠️ Zen Bridge: CSP Detected', 'color: #ff6600; font-weight: bold; font-size: 14px');
        console.log('%cThis website has Content Security Policy (CSP) restrictions that block Zen Bridge.', 'color: #ff6600');
        console.log('');
        console.log('%cWhat this means:', 'font-weight: bold');
        console.log('• WebSocket connections to localhost are blocked');
        console.log('• Zen commands will not work on this page');
        console.log('');
        console.log('%cWhy this happens:', 'font-weight: bold');
        console.log('• High-security sites (GitHub, banking, government) use CSP');
        console.log('• CSP prevents unauthorized scripts and connections');
        console.log('• This is a security feature, not a bug');
        console.log('');
        console.log('%cWhat you can do:', 'font-weight: bold');
        console.log('• Test Zen Bridge on other websites');
        console.log('• Check documentation: https://roelvangils.github.io/zen-bridge/');
        console.log('• Report CSP issues: https://github.com/roelvangils/zen-bridge/issues');
        console.log('');
        console.log('%cTechnical details:', 'color: #666');
        console.log('• Detection reason:', reason);
        console.log('• Current URL:', window.location.hostname);
        console.groupEnd();

        // Store CSP detection in window for CLI to check
        window.__ZEN_BRIDGE_CSP_BLOCKED__ = true;
    }

    function connect() {
        if (ws && ws.readyState === WebSocket.OPEN) {
            return; // Already connected
        }

        connectionAttempts++;

        // Check for CSP before attempting connection
        const cspCheck = detectCSP();
        if (cspCheck) {
            showCSPWarning(cspCheck);
            return; // Don't attempt connection
        }

        console.log('[Inspekt] Connecting to WebSocket server...');

        try {
            ws = new WebSocket(WS_URL);

            ws.onopen = () => {
                console.log('%c[Inspekt]%c Connected via WebSocket', 'color: #0066ff; font-weight: bold', 'color: inherit');
                // Clear reconnect timer if it exists
                if (reconnectTimer) {
                    clearTimeout(reconnectTimer);
                    reconnectTimer = null;
                }
                // Store globally
                window.__inspekt_ws__ = ws;
            };

            ws.onmessage = async (event) => {
                if (!isFrontTab()) {
                    // Ignore messages if not front tab
                    return;
                }

                try {
                    const message = JSON.parse(event.data);

                    if (message.type === 'execute') {
                        // Execute code
                        const requestId = message.request_id;
                        const code = message.code;

                        let result, error = null;

                        try {
                            // Execute JavaScript in page context
                            result = (0, eval)(code);

                            // Await promises
                            if (result && typeof result.then === 'function') {
                                result = await result;
                            }
                        } catch (e) {
                            // Check if this is a CSP error
                            if (e instanceof EvalError || (e.message && e.message.includes('Content Security Policy'))) {
                                // Set CSP blocked flag so CLI can detect it
                                window.__ZEN_BRIDGE_CSP_BLOCKED__ = true;
                                showCSPWarning('eval blocked by CSP (script-src missing unsafe-eval)');
                            }
                            error = String(e && e.stack ? e.stack : e);
                        }

                        // Send result back
                        ws.send(JSON.stringify({
                            type: 'result',
                            request_id: requestId,
                            ok: !error,
                            result: error ? null : (typeof result === 'undefined' ? null : result),
                            error,
                            url: location.href,
                            title: document.title || ''
                        }));

                    } else if (message.type === 'pong') {
                        // Keepalive response
                    }

                } catch (err) {
                    console.error('[Inspekt] Error handling message:', err);
                }
            };

            ws.onclose = (event) => {
                console.log('[Inspekt] Disconnected (code:', event.code, 'reason:', event.reason || 'none', '). Reconnecting...');
                ws = null;
                window.__inspekt_ws__ = null;
                scheduleReconnect();
            };

            ws.onerror = (error) => {
                // Check if this might be a CSP issue
                if (connectionAttempts > 2 && !cspDetected) {
                    // Multiple failed connections might indicate CSP
                    showCSPWarning('repeated-connection-failures');
                } else {
                    console.error('[Inspekt] WebSocket error:', error);
                }
            };

        } catch (err) {
            // Check if error message indicates CSP
            const errMsg = String(err);
            if (errMsg.includes('CSP') || errMsg.includes('Content Security Policy') || errMsg.includes('connect-src')) {
                showCSPWarning('connection-error');
            } else {
                console.error('[Inspekt] Failed to connect:', err);
            }
            scheduleReconnect();
        }
    }

    function scheduleReconnect() {
        if (reconnectTimer) return; // Already scheduled

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

    // Handle page visibility changes
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            // Tab became visible, ensure connection
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                connect();
            }
        }
    });

    // DevTools integration: Helper to store inspected elements
    if (typeof window.__ZEN_DEVTOOLS_MONITOR__ === 'undefined') {
        window.__ZEN_DEVTOOLS_MONITOR__ = true;

        // Expose inspektStore function for manual element capture
        window.inspektStore = function(element) {
            if (element && element.nodeType === 1) {
                window.__ZEN_INSPECTED_ELEMENT__ = element;
                const tag = element.tagName.toLowerCase();
                const id = element.id ? '#' + element.id : '';
                const cls = element.className && typeof element.className === 'string' ?
                    '.' + element.className.split(' ').filter(c => c).join('.') : '';
                console.log('%c[Inspekt]%c ✓ Element stored: <' + tag + id + cls + '>',
                    'color: #0066ff; font-weight: bold', 'color: #00aa00');
                console.log('[Inspekt] Run in terminal: inspekt inspected');
                return 'Stored: <' + tag + id + cls + '>';
            }
            console.error('[Inspekt] ✗ Invalid element. Usage: inspektStore($0) or inspektStore(document.querySelector(".selector"))');
            return 'ERROR: Please provide a valid element';
        };

        console.log('%c[Inspekt]%c DevTools integration ready', 'color: #0066ff; font-weight: bold', 'color: inherit');
    }

    // Initial connection
    if (isFrontTab()) {
        connect();
    }

    // Auto-restart control mode if it was active before page reload
    function autoRestartControl() {
        try {
            const wasActive = sessionStorage.getItem('__ZEN_CONTROL_ACTIVE__');
            console.log('[Inspekt] Checking control state... wasActive:', wasActive);

            if (wasActive === 'true') {
                const configStr = sessionStorage.getItem('__ZEN_CONTROL_CONFIG__');
                const selectorsStr = sessionStorage.getItem('__ZEN_CONTROL_REFOCUS_SELECTORS__');
                const config = configStr ? JSON.parse(configStr) : {};

                console.log('[Inspekt] Control was active, will auto-restart');
                console.log('[Inspekt] Config:', config);
                console.log('[Inspekt] Has refocus selectors:', !!selectorsStr);

                // Directly re-initialize control mode with minimal setup
                setTimeout(() => {
                    if (window.__ZEN_CONTROL_ACTIVE__) {
                        console.log('[Inspekt] Already restarted, skipping');
                        return; // Already restarted
                    }

                    console.log('[Inspekt] Restoring control state...');
                    window.__ZEN_CONTROL_ACTIVE__ = true;
                    window.__ZEN_CONTROL_CURRENT_ELEMENT__ = document.activeElement || document.body;

                    // Recreate the visual highlight styles
                    const focusOutlineMode = config['focus-outline'] || 'custom';
                    if (focusOutlineMode !== 'none' && !document.getElementById('inspekt-control-styles')) {
                        const style = document.createElement('style');
                        style.id = 'inspekt-control-styles';
                        const focusColor = config['focus-color'] || '#0066ff';
                        const focusSize = config['focus-size'] || 3;
                        const focusGlow = config['focus-glow'] !== false;
                        const focusAnimation = config['focus-animation'] !== false;

                        let glowColor = 'rgba(0, 102, 255, 0.3)';
                        let glowColorBright = 'rgba(0, 102, 255, 0.5)';
                        if (focusColor.startsWith('#')) {
                            const r = parseInt(focusColor.slice(1, 3), 16);
                            const g = parseInt(focusColor.slice(3, 5), 16);
                            const b = parseInt(focusColor.slice(5, 7), 16);
                            glowColor = `rgba(${r}, ${g}, ${b}, 0.3)`;
                            glowColorBright = `rgba(${r}, ${g}, ${b}, 0.5)`;
                        }

                        const boxShadow = focusGlow ? `0 0 0 2px ${glowColor}, 0 0 12px ${glowColorBright}` : 'none';
                        const animation = focusAnimation ? 'inspekt-pulse 2s infinite' : 'none';

                        style.textContent = `
                            [data-inspekt-control-focus] { position: relative !important; }
                            [data-inspekt-control-focus]::after {
                                content: '' !important; position: absolute !important;
                                top: -${focusSize + 1}px !important; left: -${focusSize + 1}px !important;
                                right: -${focusSize + 1}px !important; bottom: -${focusSize + 1}px !important;
                                border: ${focusSize}px solid ${focusColor} !important;
                                border-radius: 4px !important; pointer-events: none !important;
                                z-index: 2147483647 !important;
                                box-shadow: ${boxShadow} !important;
                                animation: ${animation} !important;
                            }
                            @keyframes inspekt-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
                        `;
                        document.head.appendChild(style);
                    }

                    console.log('%c[Inspekt]%c ✓ Control mode automatically restarted after page load',
                        'color: #0066ff; font-weight: bold', 'color: #00aa00');

                    // Check if we need to refocus an element
                    if (selectorsStr) {
                        const selectors = JSON.parse(selectorsStr);
                        console.log('[Inspekt] Will attempt refocus with selectors:', selectors);
                        // We'll handle refocus after the CLI reinitializes all the helper functions
                        window.__ZEN_CONTROL_REFOCUS_SELECTORS__ = selectors;
                        const initialUrl = sessionStorage.getItem('__ZEN_CONTROL_INITIAL_URL__');
                        window.__ZEN_CONTROL_INITIAL_URL__ = initialUrl;

                        // Automatically request full reinitialization via WebSocket
                        console.log('[Inspekt] Requesting automatic reinitialization via WebSocket...');

                        // Function to send reinit request
                        const sendReinitRequest = () => {
                            if (window.__inspekt_ws__ && window.__inspekt_ws__.readyState === WebSocket.OPEN) {
                                window.__inspekt_ws__.send(JSON.stringify({
                                    type: 'reinit_control',
                                    config: config
                                }));
                                console.log('[Inspekt] Auto-reinitialization request sent via WebSocket');
                            } else {
                                console.log('[Inspekt] WebSocket not ready, will send when connected');
                                // Set up one-time listener for when WebSocket connects
                                if (window.__inspekt_ws__) {
                                    const originalOnOpen = window.__inspekt_ws__.onopen;
                                    window.__inspekt_ws__.onopen = (event) => {
                                        if (originalOnOpen) originalOnOpen.call(window.__inspekt_ws__, event);
                                        window.__inspekt_ws__.send(JSON.stringify({
                                            type: 'reinit_control',
                                            config: config
                                        }));
                                        console.log('[Inspekt] Auto-reinitialization request sent (on connect)');
                                    };
                                } else {
                                    // WebSocket not created yet, will be handled by connect() flow
                                    window.__ZEN_PENDING_REINIT__ = config;
                                }
                            }
                        };

                        sendReinitRequest();
                    }
                }, 50);
            } else {
                console.log('[Inspekt] Control was not active, no auto-restart needed');
            }
        } catch (e) {
            console.error('[Inspekt] Error auto-restarting control:', e);
        }
    }

    // Run auto-restart check when page loads
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoRestartControl);
    } else {
        autoRestartControl();
    }

})();
