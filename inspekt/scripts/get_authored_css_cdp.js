/**
 * Get authored CSS values via Chrome DevTools Protocol (CDP)
 *
 * Uses CSS.getMatchedStylesForNode() to retrieve the original authored CSS values
 * (clamp, calc, var, rem, etc.) instead of browser-resolved computed values.
 *
 * Communicates with the extension's background script via window.postMessage,
 * following the same 3-layer bridge pattern as get_event_listeners_cdp.js.
 *
 * Placeholders:
 * - SOURCE_TYPE_PLACEHOLDER: 'inspected' | 'focused'
 * - ELEMENT_COUNT_PLACEHOLDER: number of elements in the computed tree
 */

(async function() {
    const sourceType = 'SOURCE_TYPE_PLACEHOLDER';
    const expectedElementCount = ELEMENT_COUNT_PLACEHOLDER;
    const requestId = 'css-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

    // Step 1: Get the root element
    let rootElement;
    if (sourceType === 'inspected') {
        rootElement = window.__INSPEKT_INSPECTED_ELEMENT__;
        if (!rootElement && typeof window.inspektStore === 'function') {
            const stored = window.inspektStore();
            if (stored && stored.element) {
                rootElement = stored.element;
            }
        }
    } else if (sourceType === 'focused') {
        let active = document.activeElement;
        while (active && active.shadowRoot && active.shadowRoot.activeElement) {
            active = active.shadowRoot.activeElement;
        }
        rootElement = active;
    }

    if (!rootElement) {
        return {
            ok: false,
            error: sourceType === 'inspected'
                ? 'No element is currently inspected.'
                : 'No element is currently focused.'
        };
    }

    // Step 2: Traverse depth-first and assign data-inspekt-css-id attributes
    // Must match the same traversal order as get_computed_css.js processElement()
    const elements = [];
    function markElements(el) {
        el.setAttribute('data-inspekt-css-id', String(elements.length));
        elements.push(el);
        const children = Array.from(el.children);
        for (const child of children) {
            markElements(child);
        }
    }

    try {
        markElements(rootElement);
    } catch (e) {
        return {
            ok: false,
            error: 'Failed to mark elements: ' + e.message
        };
    }

    // Step 3: Send request through bridge and wait for response
    return new Promise((resolve) => {
        const timeout = setTimeout(() => {
            window.removeEventListener('message', handler);
            cleanup();
            resolve({
                ok: false,
                error: 'CDP authored CSS request timed out (extension may not support this feature)',
                source: sourceType
            });
        }, 30000); // 30s timeout — N CDP calls may be slow

        const handler = (event) => {
            if (event.source !== window) return;
            const msg = event.data;
            if (msg?.type === 'INSPEKT_AUTHORED_CSS_RESPONSE' &&
                msg?.source === 'inspekt-extension' &&
                msg?.requestId === requestId) {
                clearTimeout(timeout);
                window.removeEventListener('message', handler);
                cleanup();
                resolve(msg.response);
            }
        };

        window.addEventListener('message', handler);
        window.postMessage({
            type: 'INSPEKT_GET_AUTHORED_CSS',
            source: 'inspekt-page',
            requestId: requestId,
            elementSource: sourceType,
            elementCount: elements.length
        }, '*');
    });

    // Step 4: Clean up data-inspekt-css-id attributes
    function cleanup() {
        for (const el of elements) {
            try {
                el.removeAttribute('data-inspekt-css-id');
            } catch (e) {
                // Element may have been removed from DOM
            }
        }
    }
})()
