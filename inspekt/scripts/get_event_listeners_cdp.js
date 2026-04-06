/**
 * Get event listeners via Chrome DevTools Protocol (CDP)
 *
 * Uses window.postMessage to communicate with the extension's background script,
 * which attaches the debugger and calls DOMDebugger.getEventListeners.
 *
 * Placeholders:
 * - SOURCE_TYPE_PLACEHOLDER: 'inspected' | 'focused' | 'selection'
 */

(async function() {
    const sourceType = 'SOURCE_TYPE_PLACEHOLDER';
    const requestId = 'evt-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

    return new Promise((resolve) => {
        const timeout = setTimeout(() => {
            window.removeEventListener('message', handler);
            resolve({
                ok: false,
                error: 'CDP event listeners request timed out (extension may not support this feature)',
                source: sourceType
            });
        }, 15000);

        const handler = (event) => {
            if (event.source !== window) return;
            const msg = event.data;
            if (msg?.type === 'INSPEKT_EVENT_LISTENERS_RESPONSE' &&
                msg?.source === 'inspekt-extension' &&
                msg?.requestId === requestId) {
                clearTimeout(timeout);
                window.removeEventListener('message', handler);
                resolve(msg.response);
            }
        };

        window.addEventListener('message', handler);
        window.postMessage({
            type: 'INSPEKT_GET_EVENT_LISTENERS',
            source: 'inspekt-page',
            requestId: requestId,
            elementSource: sourceType
        }, '*');
    });
})()
