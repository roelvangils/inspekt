/**
 * Unified screenshot script for capturing screenshots via Chrome extension
 *
 * Supports three capture modes:
 * - node: Screenshot of a specific element
 * - viewport: Screenshot of visible viewport
 * - page: Screenshot of entire page (with scrolling/stitching)
 *
 * Uses window message bridge to communicate with Chrome extension for
 * reliable screenshot capture using chrome.tabs.captureVisibleTab API.
 *
 * Placeholders:
 * - MODE_PLACEHOLDER: 'node' | 'viewport' | 'page'
 * - OPTIONS_PLACEHOLDER: JSON object with screenshot options
 */

(async function() {
    const mode = 'MODE_PLACEHOLDER';
    const options = OPTIONS_PLACEHOLDER;

    /**
     * Request screenshot from Chrome extension via window message bridge
     *
     * @param {string} captureMode - Screenshot mode (node/viewport/page)
     * @param {Object} captureOptions - Screenshot options
     * @returns {Promise<Object>} Screenshot result with base64 data
     */
    async function requestScreenshotFromExtension(captureMode, captureOptions) {
        // Check if we're in a browser context with window.postMessage
        if (typeof window === 'undefined' || typeof window.postMessage !== 'function') {
            return {
                ok: false,
                error: 'Screenshot API requires browser context with window.postMessage'
            };
        }

        try {
            // Generate unique request ID
            const requestId = 'screenshot-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

            // Create promise that waits for response via window message
            const response = await new Promise((resolve, reject) => {
                // Timeout after 30 seconds (screenshots can take time)
                const timeout = setTimeout(() => {
                    window.removeEventListener('message', messageHandler);
                    resolve({
                        ok: false,
                        error: 'Screenshot request timed out after 30 seconds'
                    });
                }, 30000);

                // Listen for response from extension
                const messageHandler = (event) => {
                    // Only accept messages from same origin
                    if (event.source !== window) return;

                    const message = event.data;
                    if (message &&
                        message.type === 'INSPEKT_SCREENSHOT_RESPONSE' &&
                        message.source === 'inspekt-extension' &&
                        message.requestId === requestId) {

                        clearTimeout(timeout);
                        window.removeEventListener('message', messageHandler);
                        resolve(message.response);
                    }
                };

                window.addEventListener('message', messageHandler);

                // Send request to extension via window.postMessage
                window.postMessage({
                    type: 'INSPEKT_CAPTURE_SCREENSHOT',
                    source: 'inspekt-page',
                    requestId: requestId,
                    mode: captureMode,
                    options: captureOptions
                }, '*');
            });

            return response;
        } catch (e) {
            console.error('[Inspekt] Screenshot request error:', e);
            return {
                ok: false,
                error: `Screenshot request failed: ${e.message}`
            };
        }
    }

    /**
     * Get element bounds for node screenshots
     *
     * @param {string} selector - CSS selector for element
     * @returns {Object} Element bounds and metadata
     */
    function getElementBounds(selector) {
        let element;

        // Handle special case: use currently inspected element
        if (!selector || selector === '$0' || selector === 'inspected') {
            // Try Chrome extension auto-stored element first
            if (window.__INSPEKT_INSPECTED_ELEMENT__) {
                element = window.__INSPEKT_INSPECTED_ELEMENT__;
            }

            // Try userscript stored element
            if (!element && window.__ZEN_INSPECTED_ELEMENT__) {
                element = window.__ZEN_INSPECTED_ELEMENT__;
            }

            // Try to get from global inspektStore function
            if (!element && typeof window.inspektStore === 'function') {
                const stored = window.inspektStore();
                if (stored && stored.element) {
                    element = stored.element;
                }
            }

            // Fallback: try $0 if available (DevTools context)
            if (!element && typeof $0 !== 'undefined' && $0) {
                element = $0;
            }

            if (!element) {
                return {
                    ok: false,
                    error: 'No element is currently inspected. Use --selector flag or inspect an element first.'
                };
            }
        } else {
            // Find element by selector
            element = document.querySelector(selector);

            if (!element) {
                return {
                    ok: false,
                    error: `Element not found: ${selector}`
                };
            }
        }

        // Get element bounds
        const rect = element.getBoundingClientRect();

        if (rect.width === 0 || rect.height === 0) {
            return {
                ok: false,
                error: 'Element has zero dimensions',
                width: rect.width,
                height: rect.height
            };
        }

        // Get scroll position
        const scrollX = window.pageXOffset || document.documentElement.scrollLeft;
        const scrollY = window.pageYOffset || document.documentElement.scrollTop;

        return {
            ok: true,
            element: element,
            bounds: {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
                top: rect.top,
                left: rect.left,
                right: rect.right,
                bottom: rect.bottom,
                scrollX: scrollX,
                scrollY: scrollY,
                devicePixelRatio: window.devicePixelRatio || 1
            },
            selector: selector || 'inspected',
            tagName: element.tagName
        };
    }

    /**
     * Scroll element into view if needed
     *
     * @param {HTMLElement} element - Element to scroll into view
     * @returns {Promise<void>}
     */
    async function scrollIntoView(element) {
        if (!element) return;

        // Check if element is in viewport
        const rect = element.getBoundingClientRect();
        const isInViewport = (
            rect.top >= 0 &&
            rect.left >= 0 &&
            rect.bottom <= window.innerHeight &&
            rect.right <= window.innerWidth
        );

        if (!isInViewport) {
            element.scrollIntoView({
                behavior: 'instant',
                block: 'center',
                inline: 'center'
            });

            // Wait for scroll to complete
            await new Promise(resolve => setTimeout(resolve, 200));
        }
    }

    /**
     * Hide element outline for screenshot
     *
     * @param {HTMLElement} element - Element to hide outline
     */
    function hideOutline(element) {
        if (!element) return;

        // Store original outline
        element.dataset.originalOutline = element.style.outline || '';
        element.dataset.originalBoxShadow = element.style.boxShadow || '';

        // Hide outline
        element.style.outline = 'none';
        element.style.boxShadow = 'none';
    }

    /**
     * Restore element outline after screenshot
     *
     * @param {HTMLElement} element - Element to restore outline
     */
    function restoreOutline(element) {
        if (!element) return;

        // Restore original outline
        if (element.dataset.originalOutline !== undefined) {
            element.style.outline = element.dataset.originalOutline;
            delete element.dataset.originalOutline;
        }

        if (element.dataset.originalBoxShadow !== undefined) {
            element.style.boxShadow = element.dataset.originalBoxShadow;
            delete element.dataset.originalBoxShadow;
        }
    }

    // ========================================================================
    // Main Screenshot Logic
    // ========================================================================

    try {
        if (mode === 'node') {
            // Node screenshot: capture specific element

            // Get element bounds
            const elementInfo = getElementBounds(options.selector);

            if (!elementInfo.ok) {
                return {
                    ok: false,
                    error: elementInfo.error,
                    mode: mode
                };
            }

            // Scroll element into view if requested
            if (options.scrollIntoView !== false) {
                await scrollIntoView(elementInfo.element);
                // Wait for scroll animation to complete
                await new Promise(resolve => setTimeout(resolve, options.scrollDelay || 200));
            }

            // Hide outline if requested
            if (options.hideOutline !== false) {
                hideOutline(elementInfo.element);
                // Wait for style to apply
                await new Promise(resolve => setTimeout(resolve, 50));
            }

            try {
                // Request screenshot from extension
                const screenshot = await requestScreenshotFromExtension('node', {
                    bounds: elementInfo.bounds,
                    selector: elementInfo.selector,
                    tagName: elementInfo.tagName,
                    margin: options.margin || 0,
                    marginColor: options.marginColor || 'auto',
                    scale: options.scale || 2,
                    quality: options.quality || 0.92,
                    format: options.format || 'png'
                });

                // Restore outline
                if (options.hideOutline !== false) {
                    restoreOutline(elementInfo.element);
                }

                if (!screenshot.ok) {
                    return {
                        ok: false,
                        error: screenshot.error || 'Screenshot capture failed',
                        mode: mode
                    };
                }

                return {
                    ok: true,
                    mode: mode,
                    dataUrl: screenshot.dataUrl,
                    width: screenshot.width,
                    height: screenshot.height,
                    selector: elementInfo.selector,
                    tagName: elementInfo.tagName,
                    fileSize: screenshot.fileSize || null,
                    apiUsed: 'chrome.tabs.captureVisibleTab',
                    origin: window.location.origin,
                    url: window.location.href
                };

            } catch (error) {
                // Ensure outline is restored on error
                if (options.hideOutline !== false) {
                    restoreOutline(elementInfo.element);
                }
                throw error;
            }

        } else if (mode === 'viewport') {
            // Viewport screenshot: capture visible viewport

            // Request screenshot from extension
            const screenshot = await requestScreenshotFromExtension('viewport', {
                margin: options.margin || 0,
                marginColor: options.marginColor || 'auto',
                scale: options.scale || 2,
                quality: options.quality || 0.92,
                format: options.format || 'png',
                excludeFixed: options.excludeFixed || false,
                includeScrollbars: options.includeScrollbars || false
            });

            if (!screenshot.ok) {
                return {
                    ok: false,
                    error: screenshot.error || 'Screenshot capture failed',
                    mode: mode
                };
            }

            return {
                ok: true,
                mode: mode,
                dataUrl: screenshot.dataUrl,
                width: screenshot.width,
                height: screenshot.height,
                fileSize: screenshot.fileSize || null,
                apiUsed: 'chrome.tabs.captureVisibleTab',
                origin: window.location.origin,
                url: window.location.href
            };

        } else if (mode === 'page') {
            // Full page screenshot: uses CDP (Chrome DevTools Protocol) for single-shot capture

            // Request screenshot from extension (uses chrome.debugger API)
            const screenshot = await requestScreenshotFromExtension('page', {
                margin: options.margin || 0,
                marginColor: options.marginColor || 'auto',
                scale: options.scale || 1,
                quality: options.quality || 0.92,
                format: options.format || 'png',
                maxHeight: options.maxHeight || 16384
            });

            if (!screenshot.ok) {
                return {
                    ok: false,
                    error: screenshot.error || 'Screenshot capture failed',
                    mode: mode
                };
            }

            return {
                ok: true,
                mode: mode,
                dataUrl: screenshot.dataUrl,
                width: screenshot.width,
                height: screenshot.height,
                fullHeight: screenshot.fullHeight,
                truncated: screenshot.truncated || false,
                fileSize: screenshot.fileSize || null,
                apiUsed: screenshot.apiUsed || 'chrome.debugger (CDP)',
                origin: window.location.origin,
                url: window.location.href
            };

        } else {
            return {
                ok: false,
                error: `Invalid screenshot mode: ${mode}. Must be 'node', 'viewport', or 'page'.`,
                mode: mode
            };
        }

    } catch (error) {
        console.error('[Inspekt] Screenshot error:', error);
        return {
            ok: false,
            error: `Screenshot failed: ${error.message}`,
            mode: mode
        };
    }
})()
