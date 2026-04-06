/**
 * Get accessibility tree via Chrome DevTools Protocol (CDP)
 *
 * Uses window.postMessage to communicate with the extension's background script,
 * which attaches the debugger and calls Accessibility.getPartialAXTree.
 *
 * Placeholders:
 * - SOURCE_TYPE_PLACEHOLDER: 'inspected' | 'focused' | 'selection'
 * - DEPTH_PLACEHOLDER: number (max depth of tree to retrieve)
 */

(async function() {
    const sourceType = 'SOURCE_TYPE_PLACEHOLDER';
    const depth = DEPTH_PLACEHOLDER;
    const requestId = 'axtree-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

    return new Promise((resolve) => {
        const timeout = setTimeout(() => {
            window.removeEventListener('message', handler);
            resolve({
                ok: false,
                error: 'CDP accessibility tree request timed out (extension may not support this feature)',
                source: sourceType
            });
        }, 15000);

        const handler = (event) => {
            if (event.source !== window) return;
            const msg = event.data;
            if (msg?.type === 'INSPEKT_ACCESSIBILITY_TREE_RESPONSE' &&
                msg?.source === 'inspekt-extension' &&
                msg?.requestId === requestId) {
                clearTimeout(timeout);
                window.removeEventListener('message', handler);
                resolve(msg.response);
            }
        };

        window.addEventListener('message', handler);
        window.postMessage({
            type: 'INSPEKT_GET_ACCESSIBILITY_TREE',
            source: 'inspekt-page',
            requestId: requestId,
            elementSource: sourceType,
            depth: depth
        }, '*');
    });
})()
