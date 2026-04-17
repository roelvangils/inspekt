/**
 * Inspekt - Window Message Bridge (Shared)
 *
 * Cross-browser implementation of the window message bridge pattern
 * Allows MAIN world scripts to communicate with extension APIs
 *
 * Flow:
 * MAIN world → window.postMessage → content script → runtime.sendMessage → background script → chrome/browser APIs
 *
 * Security:
 * - Origin verification: always check event.source === window
 * - Message source tags: distinguish 'inspekt-page' from 'inspekt-extension'
 * - Request ID matching: correlate responses to requests
 * - Timeout handling: prevent indefinite waiting
 */

const InspektMessageBridge = (() => {
    // Get the runtime API (chrome or browser)
    const runtimeAPI = typeof chrome !== 'undefined' ? chrome.runtime :
                       typeof browser !== 'undefined' ? browser.runtime : null;

    if (!runtimeAPI) {
        console.warn('[Inspekt] Runtime API not available');
        return null;
    }

    /**
     * Register a handler for a specific message type
     * @param {string} messageType - Type of message (e.g., 'GET_COOKIES_ENHANCED')
     * @param {Function} handler - Async function that handles the request
     */
    function registerHandler(messageType, handler) {
        window.addEventListener('message', async (event) => {
            // Security: only accept messages from same window
            if (event.source !== window) return;

            const message = event.data;

            // Check message format
            if (!message || message.type !== `INSPEKT_${messageType}` || message.source !== 'inspekt-page') {
                return;
            }

            try {
                // Call the handler with background script
                const response = await runtimeAPI.sendMessage({
                    type: messageType,
                    data: message.data
                });

                // Send response back to MAIN world
                // Security: use location.origin instead of '*' to prevent cross-origin iframes from intercepting
                window.postMessage({
                    type: `INSPEKT_${messageType}_RESPONSE`,
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: response
                }, location.origin);
            } catch (error) {
                // Send error back to MAIN world
                window.postMessage({
                    type: `INSPEKT_${messageType}_RESPONSE`,
                    source: 'inspekt-extension',
                    requestId: message.requestId,
                    response: {
                        ok: false,
                        error: String(error)
                    }
                }, location.origin);
            }
        });
    }

    /**
     * Setup cookies enhanced handler
     * Allows MAIN world to access chrome.cookies API
     */
    function setupCookiesBridge() {
        registerHandler('GET_COOKIES_ENHANCED', async () => {
            return await runtimeAPI.sendMessage({
                type: 'GET_COOKIES_ENHANCED'
            });
        });
    }

    /**
     * Setup storage handler
     * Allows MAIN world to access browser/chrome.storage API
     */
    function setupStorageBridge() {
        registerHandler('GET_STORAGE', async (data) => {
            return await runtimeAPI.sendMessage({
                type: 'GET_STORAGE',
                keys: data.keys
            });
        });
    }

    /**
     * Setup all available bridges
     */
    function setupAll() {
        setupCookiesBridge();
        setupStorageBridge();
    }

    // Public API
    return {
        registerHandler,
        setupCookiesBridge,
        setupStorageBridge,
        setupAll
    };
})();

// Initialize all bridges
if (InspektMessageBridge) {
    InspektMessageBridge.setupAll();
}
