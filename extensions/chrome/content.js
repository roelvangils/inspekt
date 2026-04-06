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

        // Handle GET_OVERLAY_POSITION requests from MAIN world
        if (message && message.type === 'INSPEKT_GET_OVERLAY_POSITION' && message.source === 'inspekt-page') {
            try {
                const result = await chrome.storage.local.get('inspekt_overlay_corner');
                window.postMessage({
                    type: 'INSPEKT_OVERLAY_POSITION_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    corner: result.inspekt_overlay_corner || 'bottom-left'
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_OVERLAY_POSITION_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    corner: 'bottom-left' // Default on error
                }, location.origin);
            }
        }

        // Handle SAVE_OVERLAY_POSITION requests from MAIN world
        if (message && message.type === 'INSPEKT_SAVE_OVERLAY_POSITION' && message.source === 'inspekt-page') {
            try {
                await chrome.storage.local.set({ inspekt_overlay_corner: message.corner });
                window.postMessage({
                    type: 'INSPEKT_OVERLAY_POSITION_SAVED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    ok: true
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_OVERLAY_POSITION_SAVED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    ok: false,
                    error: String(error)
                }, location.origin);
            }
        }

        // Handle GET_EXTENSION_FONT_URLS requests from MAIN world
        if (message && message.type === 'INSPEKT_GET_FONT_URLS' && message.source === 'inspekt-page') {
            try {
                const fontUrls = {
                    regular: chrome.runtime.getURL('fonts/JetBrainsMonoNerdFont-Regular.woff2'),
                    bold: chrome.runtime.getURL('fonts/JetBrainsMonoNerdFont-Bold.woff2')
                };
                window.postMessage({
                    type: 'INSPEKT_FONT_URLS_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    fontUrls: fontUrls
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_FONT_URLS_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    fontUrls: null,
                    error: String(error)
                }, location.origin);
            }
        }

        // Handle CDP KEY DISPATCH requests from MAIN world
        // This allows replay_step.js to send "real" key events via CDP,
        // which triggers :focus-visible unlike synthetic JavaScript events.
        // Same approach as Playwright and Puppeteer.
        if (message && message.type === 'INSPEKT_DISPATCH_KEY_CDP' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'DISPATCH_KEY_CDP',
                    key: message.key,
                    modifiers: message.modifiers || []
                });
                window.postMessage({
                    type: 'INSPEKT_CDP_KEY_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_CDP_KEY_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
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
                } else if (mode === 'node-cdp') {
                    // Node screenshot with CDP fallback for oversized elements
                    // Uses chrome.debugger to capture beyond viewport bounds
                    result = await chrome.runtime.sendMessage({
                        type: 'CAPTURE_ELEMENT_CDP',
                        options: options
                    });
                } else if (mode === 'selection-cdp') {
                    // Selection screenshot with CDP for precise clip region
                    // Uses chrome.debugger to capture a user-selected region
                    result = await chrome.runtime.sendMessage({
                        type: 'CAPTURE_ELEMENT_CDP',
                        options: options
                    });
                } else {
                    // Node and viewport modes use CAPTURE_VISIBLE_TAB + processing

                    // Try to hide DevTools inspector overlay before capture
                    // This uses CDP Overlay.hideHighlight - works when DevTools is closed
                    // When DevTools is open, the overlay can't be hidden programmatically
                    try {
                        await chrome.runtime.sendMessage({ type: 'HIDE_INSPECTOR_OVERLAY' });
                    } catch (e) {
                        // CDP unavailable - DevTools has debugger attached, overlay will be visible
                    }

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

        // ========== ELEMENT PICKER BRIDGE ==========

        // Handle ACTIVATE_PICKER requests from MAIN world
        // This allows page scripts to trigger the element picker without DevTools
        if (message && message.type === 'INSPEKT_ACTIVATE_PICKER' && message.source === 'inspekt-page') {
            try {
                // Inject the element picker script using src attribute (CSP-safe)
                // Using script.src instead of script.textContent avoids CSP inline-script blocks
                // The file must be listed in web_accessible_resources in manifest.json
                const script = document.createElement('script');
                const requestId = message.requestId;

                script.onload = () => {
                    // Script loaded and executed successfully
                    window.postMessage({
                        type: 'INSPEKT_PICKER_RESPONSE',
                        source: 'inspekt-extension',
                        requestId: requestId,
                        response: { ok: true, message: 'Picker activated' }
                    }, location.origin);
                    // Remove script tag after execution to keep DOM clean
                    script.remove();
                };

                script.onerror = (err) => {
                    // Script failed to load
                    window.postMessage({
                        type: 'INSPEKT_PICKER_RESPONSE',
                        source: 'inspekt-extension',
                        requestId: requestId,
                        response: { ok: false, error: 'Failed to load element picker script' }
                    }, location.origin);
                };

                // Add cache-busting query param to force browser to re-execute script each time
                // Without this, browsers cache external scripts and won't re-run on subsequent activations
                script.src = chrome.runtime.getURL('element_picker.js') + '?t=' + Date.now();
                (document.head || document.documentElement).appendChild(script);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_PICKER_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // ========== PSEUDO-STATE FORCING BRIDGE ==========

        // Handle FORCE_PSEUDO_STATE requests from MAIN world
        if (message && message.type === 'INSPEKT_FORCE_PSEUDO_STATE' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'FORCE_PSEUDO_STATE',
                    state: message.state,
                    selector: message.selector
                });

                window.postMessage({
                    type: 'INSPEKT_PSEUDO_STATE_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_PSEUDO_STATE_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: {
                        ok: false,
                        error: String(error)
                    }
                }, location.origin);
            }
        }

        // Handle CLEAR_PSEUDO_STATE requests from MAIN world
        if (message && message.type === 'INSPEKT_CLEAR_PSEUDO_STATE' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'CLEAR_PSEUDO_STATE'
                });

                window.postMessage({
                    type: 'INSPEKT_CLEAR_PSEUDO_STATE_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_CLEAR_PSEUDO_STATE_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: {
                        ok: false,
                        error: String(error)
                    }
                }, location.origin);
            }
        }

        // ========== DOWNLOAD MONITORING BRIDGE ==========

        // Handle START_DOWNLOAD_MONITORING requests from MAIN world
        if (message && message.type === 'INSPEKT_START_DOWNLOAD_MONITORING' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'START_DOWNLOAD_MONITORING',
                    sessionId: message.sessionId
                });

                window.postMessage({
                    type: 'INSPEKT_DOWNLOAD_MONITORING_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_DOWNLOAD_MONITORING_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle STOP_DOWNLOAD_MONITORING requests from MAIN world
        if (message && message.type === 'INSPEKT_STOP_DOWNLOAD_MONITORING' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'STOP_DOWNLOAD_MONITORING',
                    sessionId: message.sessionId
                });

                window.postMessage({
                    type: 'INSPEKT_DOWNLOAD_MONITORING_STOPPED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_DOWNLOAD_MONITORING_STOPPED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle START_SCREENCAST requests from MAIN world (video recording)
        if (message && message.type === 'INSPEKT_START_SCREENCAST' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'START_SCREENCAST',
                    settings: message.settings,
                    requestId: message.requestId
                });

                window.postMessage({
                    type: 'INSPEKT_SCREENCAST_STARTED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response || { ok: true }
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_SCREENCAST_STARTED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle STOP_SCREENCAST requests from MAIN world (video recording)
        if (message && message.type === 'INSPEKT_STOP_SCREENCAST' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'STOP_SCREENCAST',
                    requestId: message.requestId
                });

                window.postMessage({
                    type: 'INSPEKT_SCREENCAST_STOPPED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response || { ok: true }
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_SCREENCAST_STOPPED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle START_SMOOTH_CAPTURE requests from MAIN world (timer-based video recording)
        if (message && message.type === 'INSPEKT_START_SMOOTH_CAPTURE' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'START_SMOOTH_CAPTURE',
                    settings: message.settings,
                    requestId: message.requestId
                });

                window.postMessage({
                    type: 'INSPEKT_SMOOTH_CAPTURE_STARTED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response || { ok: true }
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_SMOOTH_CAPTURE_STARTED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle STOP_SMOOTH_CAPTURE requests from MAIN world (timer-based video recording)
        if (message && message.type === 'INSPEKT_STOP_SMOOTH_CAPTURE' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'STOP_SMOOTH_CAPTURE',
                    requestId: message.requestId
                });

                window.postMessage({
                    type: 'INSPEKT_SMOOTH_CAPTURE_STOPPED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response || { ok: true }
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_SMOOTH_CAPTURE_STOPPED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle GET_DOWNLOAD_CONTENT requests from MAIN world
        if (message && message.type === 'INSPEKT_GET_DOWNLOAD_CONTENT' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'GET_DOWNLOAD_FILE_CONTENT',
                    downloadId: message.downloadId
                });

                window.postMessage({
                    type: 'INSPEKT_DOWNLOAD_CONTENT_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_DOWNLOAD_CONTENT_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // ========== CDP DIALOG INTERCEPTION BRIDGE ==========

        // Handle ENABLE_DIALOG_INTERCEPTION requests from MAIN world
        if (message && message.type === 'INSPEKT_ENABLE_DIALOG_INTERCEPTION' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'ENABLE_DIALOG_INTERCEPTION',
                    queue: message.queue || []
                });

                window.postMessage({
                    type: 'INSPEKT_DIALOG_INTERCEPTION_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_DIALOG_INTERCEPTION_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle DISABLE_DIALOG_INTERCEPTION requests from MAIN world
        if (message && message.type === 'INSPEKT_DISABLE_DIALOG_INTERCEPTION' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'DISABLE_DIALOG_INTERCEPTION'
                });

                window.postMessage({
                    type: 'INSPEKT_DIALOG_INTERCEPTION_DISABLED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_DIALOG_INTERCEPTION_DISABLED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle QUEUE_DIALOG_RESULT requests from MAIN world
        if (message && message.type === 'INSPEKT_QUEUE_DIALOG_RESULT' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'QUEUE_DIALOG_RESULT',
                    dialogType: message.dialogType,
                    result: message.result
                });

                window.postMessage({
                    type: 'INSPEKT_DIALOG_RESULT_QUEUED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_DIALOG_RESULT_QUEUED',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // ========== ZOOM LEVEL BRIDGE ==========

        // Handle GET_ZOOM_LEVEL requests from MAIN world
        if (message && message.type === 'INSPEKT_GET_ZOOM_LEVEL' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'GET_ZOOM_LEVEL'
                });

                window.postMessage({
                    type: 'INSPEKT_ZOOM_LEVEL_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_ZOOM_LEVEL_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }

        // Handle SET_ZOOM_LEVEL requests from MAIN world
        if (message && message.type === 'INSPEKT_SET_ZOOM_LEVEL' && message.source === 'inspekt-page') {
            try {
                const response = await chrome.runtime.sendMessage({
                    type: 'SET_ZOOM_LEVEL',
                    zoomFactor: message.zoomFactor
                });

                window.postMessage({
                    type: 'INSPEKT_ZOOM_SET_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                window.postMessage({
                    type: 'INSPEKT_ZOOM_SET_RESPONSE',
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: { ok: false, error: String(error) }
                }, location.origin);
            }
        }
    });

    // Listen for download events from background script and forward to MAIN world
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
        // Forward download start/complete events to MAIN world
        if (message.type === 'INSPEKT_DOWNLOAD_STARTED' || message.type === 'INSPEKT_DOWNLOAD_COMPLETE') {
            window.postMessage({
                type: message.type,
                source: 'inspekt-extension',
                sessionId: message.sessionId,
                download: message.download
            }, location.origin);
            sendResponse({ ok: true });
            return true;
        }

        // Forward dialog overlay notification to MAIN world (for visual feedback during CDP interception)
        if (message.type === 'SHOW_DIALOG_OVERLAY') {
            window.postMessage({
                type: 'INSPEKT_SHOW_DIALOG_OVERLAY',
                source: 'inspekt-extension',
                dialogType: message.dialogType,
                message: message.message,
                result: message.result,
                duration: message.duration  // How long to show overlay (matches recorded duration)
            }, location.origin);
            sendResponse({ ok: true });
            return true;
        }

        // Forward screencast frames to bridge server (for video recording)
        if (message.type === 'SCREENCAST_FRAME') {
            const ws = window.__inspekt_ws__;
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'screencast_frame',
                    timestamp: message.timestamp,
                    data: message.data
                }));
            }
            sendResponse({ ok: true });
            return true;
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
                    extensionVersion: window.__INSPEKT_BRIDGE_VERSION__ || null,
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

                    // Screencast (video recording) should work regardless of tab visibility
                    const isScreencastManagement = ['START_SCREENCAST', 'STOP_SCREENCAST'].includes(message.type);

                    // Debug logging for screencast
                    if (isScreencastManagement) {
                        console.log('[Inspekt Content] SCREENCAST message detected:', message.type, 'isFrontTab:', isFrontTab());
                    }

                    // Skip visibility check for identify commands, axe commands, pong responses, domain management, CSP management, console management, and screencast
                    if (!isFrontTab() && !isIdentifyCommand && !isAxeCommand && !isDomainManagement && !isCspManagement && !isConsoleManagement && !isScreencastManagement && message.type !== 'pong') {
                        console.log('[Inspekt] Message dropped - tab not visible/active:', message.type);
                        return;
                    }

                    if (message.type === 'execute') {
                        const requestId = message.request_id;
                        const code = message.code;

                        // Send ACK immediately so bridge knows we received the request
                        ws.send(JSON.stringify({ type: 'execute_ack', request_id: requestId }));

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
                            await InspektPermissions.setPermanentBypass(enabled);

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

                    } else if (message.type === 'START_SCREENCAST') {
                        // Start screencast (video recording)
                        console.log('[Inspekt Content] START_SCREENCAST received, requestId:', message.requestId);
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'START_SCREENCAST',
                                settings: message.settings,
                                requestId: message.requestId
                            });

                            console.log('[Inspekt Content] START_SCREENCAST response from background:', response);
                            ws.send(JSON.stringify({
                                type: 'screencast_ack',
                                requestId: message.requestId,
                                ok: response?.ok ?? true,
                                error: response?.error
                            }));
                            console.log('[Inspekt Content] screencast_ack sent');
                        } catch (err) {
                            console.error('[Inspekt Content] START_SCREENCAST error:', err);
                            ws.send(JSON.stringify({
                                type: 'screencast_ack',
                                requestId: message.requestId,
                                ok: false,
                                error: err.message
                            }));
                        }

                    } else if (message.type === 'STOP_SCREENCAST') {
                        // Stop screencast (video recording)
                        try {
                            const response = await chrome.runtime.sendMessage({
                                type: 'STOP_SCREENCAST',
                                requestId: message.requestId
                            });

                            ws.send(JSON.stringify({
                                type: 'screencast_ack',
                                requestId: message.requestId,
                                ok: response?.ok ?? true,
                                error: response?.error
                            }));
                        } catch (err) {
                            console.error('[Inspekt] STOP_SCREENCAST error:', err);
                            ws.send(JSON.stringify({
                                type: 'screencast_ack',
                                requestId: message.requestId,
                                ok: false,
                                error: err.message
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
                const allowed = await InspektPermissions.isAllowed();
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
            const allowed = await InspektPermissions.isAllowed();
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
