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

    // =========================================================================
    // CONSTANTS
    // =========================================================================
    const MAX_SCREENSHOT_WIDTH = 2000;
    const MAX_SCREENSHOT_HEIGHT = 4000;

    // =========================================================================
    // PRE-CLEANUP: Remove any leftover state from previous interrupted runs
    // =========================================================================
    // This prevents issues when the command is run multiple times on the same page
    (function cleanupPreviousState() {
        // Remove orphaned isolation style tags (from --isolate mode)
        document.querySelectorAll('#inspekt-isolation-style').forEach(el => el.remove());

        // Remove orphaned pseudo-state styles (from --compare mode)
        document.querySelectorAll('#inspekt-pseudo-state-override').forEach(el => el.remove());

        // Remove orphaned redaction styles (from --redact mode)
        document.querySelectorAll('#inspekt-redact-style').forEach(el => el.remove());

        // Clear stale window state variables
        if (window.__inspekt_redacted_elements__) {
            delete window.__inspekt_redacted_elements__;
        }

        // Remove any leftover hide classes from previous isolation
        document.querySelectorAll('.inspekt-hide-for-capture').forEach(el => {
            el.classList.remove('inspekt-hide-for-capture');
        });
    })();

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
     * Activate element picker to allow user to select an element
     * without opening DevTools
     *
     * @returns {Promise<Object>} Result with ok status
     */
    async function activateElementPicker() {
        try {
            const requestId = 'picker-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

            // Request picker activation from extension
            const pickerPromise = new Promise((resolve) => {
                let timeoutId = null;
                let resolved = false;

                const messageHandler = (event) => {
                    if (event.source !== window) return;
                    const message = event.data;
                    if (message &&
                        message.type === 'INSPEKT_PICKER_RESPONSE' &&
                        message.source === 'inspekt-extension' &&
                        message.requestId === requestId) {
                        resolved = true;
                        if (timeoutId) clearTimeout(timeoutId);
                        window.removeEventListener('message', messageHandler);
                        resolve(message.response);
                    }
                };
                window.addEventListener('message', messageHandler);

                window.postMessage({
                    type: 'INSPEKT_ACTIVATE_PICKER',
                    source: 'inspekt-page',
                    requestId: requestId
                }, '*');

                // Timeout after 2 seconds if no response (extension not available)
                timeoutId = setTimeout(() => {
                    if (resolved) return; // Already got a response, ignore timeout
                    window.removeEventListener('message', messageHandler);
                    resolve({ ok: false, error: 'Extension not available or did not respond in time' });
                }, 2000);
            });

            const pickerResponse = await pickerPromise;
            if (!pickerResponse.ok) {
                return pickerResponse;
            }

            // Wait for user to select an element (polling for __INSPEKT_INSPECTED_ELEMENT__)
            // With timeout of 30 seconds
            const elementPromise = new Promise((resolve) => {
                const startTime = Date.now();
                const timeout = 30000; // 30 seconds

                const checkElement = () => {
                    // Check if element was selected
                    if (window.__INSPEKT_INSPECTED_ELEMENT__) {
                        resolve({ ok: true });
                        return;
                    }

                    // Check if picker was cancelled (no longer active)
                    if (!window.__INSPEKT_PICKER_ACTIVE__ && Date.now() - startTime > 500) {
                        // Picker is no longer active and some time has passed
                        // Either user selected something or cancelled
                        if (window.__INSPEKT_INSPECTED_ELEMENT__) {
                            resolve({ ok: true });
                        } else {
                            resolve({ ok: false, error: 'Element selection cancelled' });
                        }
                        return;
                    }

                    // Check timeout
                    if (Date.now() - startTime > timeout) {
                        resolve({ ok: false, error: 'Element selection timed out' });
                        return;
                    }

                    // Keep polling
                    setTimeout(checkElement, 100);
                };

                checkElement();
            });

            return await elementPromise;

        } catch (e) {
            return { ok: false, error: `Picker activation failed: ${e.message}` };
        }
    }

    /**
     * Collect page metadata for embedding in screenshot
     *
     * @returns {Object} Page metadata including title, language, media queries, browser info
     */
    function collectPageMetadata() {
        // Helper to safely check media query
        const matchMedia = (query) => {
            try {
                return window.matchMedia(query).matches;
            } catch {
                return false;
            }
        };

        // Detect color scheme preference
        let prefersColorScheme = 'light';
        if (matchMedia('(prefers-color-scheme: dark)')) {
            prefersColorScheme = 'dark';
        }

        // Detect contrast preference
        let prefersContrast = 'no-preference';
        if (matchMedia('(prefers-contrast: more)')) {
            prefersContrast = 'more';
        } else if (matchMedia('(prefers-contrast: less)')) {
            prefersContrast = 'less';
        }

        // Detect reduced motion preference
        let prefersReducedMotion = 'no-preference';
        if (matchMedia('(prefers-reduced-motion: reduce)')) {
            prefersReducedMotion = 'reduce';
        }

        // Detect reduced transparency preference
        let prefersReducedTransparency = 'no-preference';
        if (matchMedia('(prefers-reduced-transparency: reduce)')) {
            prefersReducedTransparency = 'reduce';
        }

        // Detect forced colors mode
        let forcedColors = 'none';
        if (matchMedia('(forced-colors: active)')) {
            forcedColors = 'active';
        }

        // Extract Chrome version from user agent
        let browserVersion = null;
        const chromeMatch = navigator.userAgent.match(/Chrome\/(\d+\.\d+\.\d+\.\d+)/);
        if (chromeMatch) {
            browserVersion = chromeMatch[1];
        }

        return {
            pageTitle: document.title || null,
            pageLanguage: document.documentElement.lang || navigator.language || null,
            prefersColorScheme,
            prefersContrast,
            prefersReducedMotion,
            prefersReducedTransparency,
            forcedColors,
            browserVersion,
            userAgent: navigator.userAgent,
            windowWidth: window.outerWidth,
            windowHeight: window.outerHeight,
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight
        };
    }

    /**
     * Get the deeply focused element (traverses Shadow DOM).
     * @returns {Element|null} The focused element or null
     */
    function getDeepActiveElement() {
        let active = document.activeElement;
        while (active && active.shadowRoot && active.shadowRoot.activeElement) {
            active = active.shadowRoot.activeElement;
        }
        return active;
    }

    /**
     * Get element bounds for node screenshots
     *
     * @param {string} selector - CSS selector for element, or special values: 'inspected', 'focused', '$0'
     * @returns {Promise<Object>} Element bounds and metadata
     */
    async function getElementBounds(selector) {
        let element;

        // Handle special case: use currently focused element
        if (selector === 'focused') {
            element = getDeepActiveElement();

            if (!element || element === document.body || element === document.documentElement) {
                return {
                    ok: false,
                    error: 'No element is currently focused. Press Tab or click an element first.'
                };
            }

            if (element.tagName === 'IFRAME') {
                return {
                    ok: false,
                    error: 'Focus is inside an iframe. Cannot capture cross-origin iframe content.'
                };
            }
        }
        // Handle special case: use currently inspected element
        else if (!selector || selector === '$0' || selector === 'inspected') {
            // Helper: check if element is valid (not body/html - we want a specific element)
            const isValidElement = (el) => el && el !== document.body && el !== document.documentElement;

            // Try Chrome extension auto-stored element first
            if (isValidElement(window.__INSPEKT_INSPECTED_ELEMENT__)) {
                element = window.__INSPEKT_INSPECTED_ELEMENT__;
            }

            // Try to get from global inspektStore function
            if (!element && typeof window.inspektStore === 'function') {
                const stored = window.inspektStore();
                if (isValidElement(stored && stored.element)) {
                    element = stored.element;
                }
            }

            // Fallback: try $0 if available (DevTools context)
            if (!element && typeof $0 !== 'undefined' && isValidElement($0)) {
                element = $0;
            }

            if (!element) {
                // No element inspected - try to activate the element picker
                // This allows users to select an element without opening DevTools
                const pickerResult = await activateElementPicker();

                if (!pickerResult.ok) {
                    return {
                        ok: false,
                        error: pickerResult.error || 'No element is currently inspected. Use --selector flag or inspect an element first.',
                        hint: 'Click an element on the page to select it, or use inspekt://screenshot?selector=.my-class'
                    };
                }

                // Check if element was selected after picker (and it's not body/html)
                element = window.__INSPEKT_INSPECTED_ELEMENT__;
                if (!isValidElement(element)) {
                    return {
                        ok: false,
                        error: element ? 'Please select a specific element, not the entire page.' : 'Element selection was cancelled.',
                        hint: 'Click a specific element to select it, then run the screenshot command again.'
                    };
                }
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

        // Reject body/html - require user to select a specific element
        if (element === document.body || element === document.documentElement) {
            return {
                ok: false,
                error: 'Cannot screenshot document body or html element',
                hint: 'Select a specific element. Right-click an element and choose "Inspect".',
                tagName: element.tagName.toLowerCase()
            };
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

        // Check element size limits (unless --force-large is used)
        if (!options.forceLarge) {
            if (rect.width > MAX_SCREENSHOT_WIDTH || rect.height > MAX_SCREENSHOT_HEIGHT) {
                return {
                    ok: false,
                    error: `Element too large: ${Math.round(rect.width)}×${Math.round(rect.height)} exceeds ${MAX_SCREENSHOT_WIDTH}×${MAX_SCREENSHOT_HEIGHT} limit`,
                    hint: 'Use --force-large to capture anyway, or select a smaller element',
                    width: rect.width,
                    height: rect.height,
                    maxWidth: MAX_SCREENSHOT_WIDTH,
                    maxHeight: MAX_SCREENSHOT_HEIGHT
                };
            }
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

    /**
     * Generate a unique CSS selector for an element
     *
     * Creates a selector path using nth-child to ensure uniqueness.
     * Falls back to attribute-based markers for elements that can't be
     * reliably selected via nth-child.
     *
     * @param {HTMLElement} element - Element to generate selector for
     * @returns {string} CSS selector string
     */
    function getUniqueCSSSelector(element) {
        if (!element || element === document.documentElement) return 'html';
        if (element === document.body) return 'body';

        const parts = [];
        let current = element;

        while (current && current !== document.body && current !== document.documentElement) {
            let selector = current.tagName.toLowerCase();

            // Use ID if available and unique
            if (current.id && document.querySelectorAll('#' + CSS.escape(current.id)).length === 1) {
                parts.unshift('#' + CSS.escape(current.id));
                break; // ID is unique, no need to go further
            }

            // Otherwise use nth-child for uniqueness
            const parent = current.parentElement;
            if (parent) {
                const siblings = Array.from(parent.children);
                const index = siblings.indexOf(current) + 1; // nth-child is 1-based
                selector += `:nth-child(${index})`;
            }

            parts.unshift(selector);
            current = current.parentElement;
        }

        // Prepend body if we didn't hit an ID
        if (parts.length > 0 && !parts[0].startsWith('#')) {
            parts.unshift('body');
        }

        return parts.join(' > ');
    }

    /**
     * Isolate an element for transparent screenshot capture (CSS-only approach)
     *
     * Uses a single injected stylesheet instead of modifying inline styles on each
     * element. This prevents visual flashing by batching all style changes into
     * one browser reflow.
     *
     * Strategy:
     * 1. Generate CSS selectors for ancestors
     * 2. Build one stylesheet with all transparency and hiding rules
     * 3. Add a marker class to elements that need hiding
     * 4. Single DOM operation: inject stylesheet
     *
     * @param {HTMLElement} element - The element to isolate
     * @returns {Object} State object for restoration via restoreIsolation()
     */
    function isolateElement(element) {
        const state = {
            hiddenElements: [],  // Elements with added hide class
            styleTag: null       // Injected stylesheet
        };

        // Build ancestor selectors for transparent backgrounds
        const ancestorSelectors = [];
        let current = element.parentElement;
        while (current && current !== document.documentElement) {
            ancestorSelectors.push(getUniqueCSSSelector(current));
            current = current.parentElement;
        }

        // Collect elements to hide: fixed/sticky elements and siblings
        const ancestors = new Set();
        current = element;
        while (current) {
            ancestors.add(current);
            current = current.parentElement;
        }

        // Find fixed/sticky elements to hide (but not ancestors or children of target)
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            if (ancestors.has(el) || element.contains(el)) continue;
            const style = getComputedStyle(el);
            if (style.position === 'fixed' || style.position === 'sticky') {
                state.hiddenElements.push(el);
            }
        }

        // Find siblings to hide (walk up ancestor path)
        current = element;
        while (current && current !== document.documentElement) {
            const parent = current.parentElement;
            if (parent) {
                for (const sibling of parent.children) {
                    if (sibling !== current && !state.hiddenElements.includes(sibling)) {
                        state.hiddenElements.push(sibling);
                    }
                }
            }
            current = parent;
        }

        // Build comprehensive CSS rules in a single string
        const ancestorSelector = ancestorSelectors.length > 0
            ? ', ' + ancestorSelectors.join(', ')
            : '';

        const css = `
            /* Inspekt isolation styles - disable transitions to prevent capture during animation */
            html, body${ancestorSelector} {
                background: transparent !important;
                background-color: transparent !important;
                transition: none !important;
            }

            /* Hide pseudo-elements on html/body */
            html::before, html::after,
            body::before, body::after {
                display: none !important;
                visibility: hidden !important;
                content: none !important;
            }

            /* Hide marked elements */
            .inspekt-hide-for-capture {
                visibility: hidden !important;
            }
        `;

        // Single DOM operation: inject stylesheet
        const styleTag = document.createElement('style');
        styleTag.id = 'inspekt-isolation-style';
        styleTag.textContent = css;
        document.head.appendChild(styleTag);
        state.styleTag = styleTag;

        // Batch add hide class to all elements that need hiding
        // Using classList.add is faster than modifying inline styles
        for (const el of state.hiddenElements) {
            el.classList.add('inspekt-hide-for-capture');
        }

        return state;
    }

    /**
     * Restore page state after isolated screenshot capture
     *
     * @param {Object} state - State object from isolateElement()
     */
    function restoreIsolation(state) {
        // Remove hide class from all marked elements
        for (const el of state.hiddenElements) {
            el.classList.remove('inspekt-hide-for-capture');
        }

        // Remove injected stylesheet
        if (state.styleTag) {
            state.styleTag.remove();
        }
    }

    /**
     * Get current browser zoom level from extension
     *
     * Uses window message bridge to request zoom level from Chrome extension,
     * which has access to the chrome.tabs.getZoom() API.
     *
     * @returns {Promise<number>} Zoom factor (1.0 = 100%)
     */
    async function getZoomLevel() {
        const requestId = 'zoom-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        return new Promise((resolve) => {
            const handler = (event) => {
                if (event.data?.type === 'INSPEKT_ZOOM_LEVEL_RESPONSE' &&
                    event.data?.requestId === requestId) {
                    window.removeEventListener('message', handler);
                    resolve(event.data.response?.zoomFactor || 1.0);
                }
            };
            window.addEventListener('message', handler);
            window.postMessage({
                type: 'INSPEKT_GET_ZOOM_LEVEL',
                source: 'inspekt-page',
                requestId: requestId
            }, '*');
            // Timeout fallback - if extension doesn't respond, assume 100%
            setTimeout(() => {
                window.removeEventListener('message', handler);
                resolve(1.0);
            }, 2000);
        });
    }

    /**
     * Set browser zoom level via extension
     *
     * Uses window message bridge to set zoom level via Chrome extension,
     * which has access to the chrome.tabs.setZoom() API.
     *
     * @param {number} zoomFactor - Zoom factor to set (1.0 = 100%)
     * @returns {Promise<boolean>} True if successful
     */
    async function setZoomLevel(zoomFactor) {
        const requestId = 'zoom-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        return new Promise((resolve) => {
            const handler = (event) => {
                if (event.data?.type === 'INSPEKT_ZOOM_SET_RESPONSE' &&
                    event.data?.requestId === requestId) {
                    window.removeEventListener('message', handler);
                    resolve(event.data.response?.ok || false);
                }
            };
            window.addEventListener('message', handler);
            window.postMessage({
                type: 'INSPEKT_SET_ZOOM_LEVEL',
                source: 'inspekt-page',
                requestId: requestId,
                zoomFactor: zoomFactor
            }, '*');
            // Timeout fallback
            setTimeout(() => {
                window.removeEventListener('message', handler);
                resolve(false);
            }, 2000);
        });
    }

    /**
     * Save current text selection
     *
     * Clones all selection ranges so they can be restored after screenshot.
     * This is important because clearing the selection for a clean screenshot
     * shouldn't permanently lose the user's selection.
     *
     * @returns {Range[]|null} Array of cloned ranges, or null if no selection
     */
    function saveSelection() {
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
            return null;
        }
        // Clone all ranges (some pages may have multiple)
        const ranges = [];
        for (let i = 0; i < selection.rangeCount; i++) {
            ranges.push(selection.getRangeAt(i).cloneRange());
        }
        return ranges;
    }

    /**
     * Clear current text selection
     */
    function clearSelection() {
        window.getSelection().removeAllRanges();
    }

    /**
     * Restore saved text selection
     *
     * @param {Range[]|null} savedRanges - Previously saved ranges from saveSelection()
     */
    function restoreSelection(savedRanges) {
        if (!savedRanges || savedRanges.length === 0) return;
        const selection = window.getSelection();
        selection.removeAllRanges();
        for (const range of savedRanges) {
            try {
                selection.addRange(range);
            } catch (e) {
                // Range may be invalid if DOM changed - silently skip
            }
        }
    }

    /**
     * Analyze element visibility and dimensions relative to viewport
     *
     * Determines if element fits in viewport and calculates absolute position
     * for CDP capture fallback when element exceeds viewport size.
     *
     * @param {HTMLElement} element - Element to analyze
     * @returns {Object} Analysis result with visibility and dimension info
     */
    function analyzeElement(element) {
        const rect = element.getBoundingClientRect();
        const viewport = {
            width: window.innerWidth,
            height: window.innerHeight
        };

        // Get scroll position for absolute coordinates
        const scrollX = window.pageXOffset || document.documentElement.scrollLeft;
        const scrollY = window.pageYOffset || document.documentElement.scrollTop;

        // Calculate overflow in each direction
        const overflowTop = rect.top < 0 ? Math.abs(rect.top) : 0;
        const overflowBottom = rect.bottom > viewport.height ? rect.bottom - viewport.height : 0;
        const overflowLeft = rect.left < 0 ? Math.abs(rect.left) : 0;
        const overflowRight = rect.right > viewport.width ? rect.right - viewport.width : 0;

        return {
            // Element dimensions
            width: rect.width,
            height: rect.height,

            // Position relative to viewport
            top: rect.top,
            left: rect.left,
            bottom: rect.bottom,
            right: rect.right,

            // Viewport dimensions
            viewportWidth: viewport.width,
            viewportHeight: viewport.height,

            // Is element fully visible in viewport?
            isFullyVisible: (
                rect.top >= 0 &&
                rect.left >= 0 &&
                rect.bottom <= viewport.height &&
                rect.right <= viewport.width
            ),

            // Does element fit in viewport at all? (could scroll to show it fully)
            fitsInViewport: (
                rect.width <= viewport.width &&
                rect.height <= viewport.height
            ),

            // Overflow amounts
            overflowTop,
            overflowBottom,
            overflowLeft,
            overflowRight,
            totalOverflow: overflowTop + overflowBottom + overflowLeft + overflowRight,

            // Absolute position (for CDP capture clip region)
            absoluteTop: rect.top + scrollY,
            absoluteLeft: rect.left + scrollX,

            // Device pixel ratio
            devicePixelRatio: window.devicePixelRatio || 1
        };
    }

    // ========================================================================
    // Main Screenshot Logic
    // ========================================================================

    try {
        if (mode === 'node') {
            // Node screenshot: capture specific element

            // Get element bounds (async because it may trigger element picker)
            const elementInfo = await getElementBounds(options.selector);

            if (!elementInfo.ok) {
                return {
                    ok: false,
                    error: elementInfo.error,
                    mode: mode
                };
            }

            // Track what adjustments were made for user feedback
            let scrolledIntoView = false;
            let usedCDPFallback = false;
            let scrollDirection = null;  // 'up', 'down', 'left', 'right', or null
            let zoomWasReset = false;
            let originalZoom = null;
            let savedSelection = null;
            let selectionCleared = false;

            // === PREPARE PAGE STATE FOR SCREENSHOT ===

            // 1. Check and reset zoom level if needed (unless --keep-zoom)
            if (!options.keepZoom) {
                originalZoom = await getZoomLevel();
                if (originalZoom !== 1.0) {
                    await setZoomLevel(1.0);
                    zoomWasReset = true;
                    // Wait for zoom to apply
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
            }

            // 2. Save and clear text selection if any (unless --keep-selection)
            if (!options.keepSelection) {
                savedSelection = saveSelection();
                if (savedSelection) {
                    clearSelection();
                    selectionCleared = true;
                    // Small delay for visual update
                    await new Promise(resolve => setTimeout(resolve, 50));
                }
            }

            // Save original scroll position to restore after capture
            const originalScrollX = window.pageXOffset || document.documentElement.scrollLeft;
            const originalScrollY = window.pageYOffset || document.documentElement.scrollTop;

            // Analyze element visibility before any adjustments
            let analysis = analyzeElement(elementInfo.element);

            // Scroll element into view if requested and not fully visible
            if (options.scrollIntoView !== false && !analysis.isFullyVisible) {
                await scrollIntoView(elementInfo.element);
                // Wait for scroll animation to complete
                await new Promise(resolve => setTimeout(resolve, options.scrollDelay || 200));
                scrolledIntoView = true;

                // Calculate scroll direction (primary direction based on largest delta)
                const newScrollX = window.pageXOffset || document.documentElement.scrollLeft;
                const newScrollY = window.pageYOffset || document.documentElement.scrollTop;
                const deltaX = newScrollX - originalScrollX;
                const deltaY = newScrollY - originalScrollY;

                // Determine primary scroll direction
                if (Math.abs(deltaY) >= Math.abs(deltaX)) {
                    scrollDirection = deltaY > 0 ? 'down' : (deltaY < 0 ? 'up' : null);
                } else {
                    scrollDirection = deltaX > 0 ? 'right' : (deltaX < 0 ? 'left' : null);
                }

                // Re-analyze after scroll
                analysis = analyzeElement(elementInfo.element);
            }

            // Hide outline if requested
            if (options.hideOutline !== false) {
                hideOutline(elementInfo.element);
                // Wait for style to apply
                await new Promise(resolve => setTimeout(resolve, 50));
            }

            // Isolate element for transparent background if requested
            let isolationState = null;
            let elementIsolated = false;
            if (options.isolate) {
                isolationState = isolateElement(elementInfo.element);
                elementIsolated = true;
                // Wait for DOM/style changes to apply
                await new Promise(resolve => setTimeout(resolve, 50));
            }

            try {
                let screenshot;

                // Decide capture method based on element size and isolation mode
                // Note: --isolate requires CDP mode for transparent background support
                const useCDP = !analysis.fitsInViewport || options.isolate;

                if (!useCDP) {
                    // Element fits in viewport - use fast captureVisibleTab method
                    // Update bounds after scroll
                    const rect = elementInfo.element.getBoundingClientRect();
                    const scrollX = window.pageXOffset || document.documentElement.scrollLeft;
                    const scrollY = window.pageYOffset || document.documentElement.scrollTop;

                    const updatedBounds = {
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
                    };

                    screenshot = await requestScreenshotFromExtension('node', {
                        bounds: updatedBounds,
                        selector: elementInfo.selector,
                        tagName: elementInfo.tagName,
                        margin: options.margin || 0,
                        marginColor: options.marginColor || 'auto',
                        scale: options.scale || 2,
                        quality: options.quality || 0.92,
                        format: options.format || 'png'
                    });
                } else {
                    // Use CDP capture - either element exceeds viewport or isolation mode
                    usedCDPFallback = true;

                    // Warn about Chrome's max dimension limit
                    const maxDimension = 16384;
                    const warnLargeDimension = analysis.width > maxDimension || analysis.height > maxDimension;

                    screenshot = await requestScreenshotFromExtension('node-cdp', {
                        clip: {
                            x: analysis.absoluteLeft,
                            y: analysis.absoluteTop,
                            width: Math.min(analysis.width, maxDimension),
                            height: Math.min(analysis.height, maxDimension)
                        },
                        selector: elementInfo.selector,
                        tagName: elementInfo.tagName,
                        margin: options.margin || 0,
                        marginColor: options.marginColor || 'auto',
                        scale: options.isolate ? (options.scale || 2) : (options.scale || 1), // Use 2x for isolate
                        quality: options.quality || 0.92,
                        format: options.format || 'png',
                        warnLargeDimension: warnLargeDimension,
                        originalWidth: analysis.width,
                        originalHeight: analysis.height,
                        isolate: options.isolate || false  // Pass isolate flag to enable transparent background
                    });
                }

                // Restore outline
                if (options.hideOutline !== false) {
                    restoreOutline(elementInfo.element);
                }

                // Restore isolation state
                if (isolationState) {
                    restoreIsolation(isolationState);
                }

                // Restore original scroll position if we scrolled
                if (scrolledIntoView) {
                    window.scrollTo({
                        left: originalScrollX,
                        top: originalScrollY,
                        behavior: 'instant'
                    });
                }

                // === RESTORE PAGE STATE AFTER SCREENSHOT ===

                // Restore text selection
                if (savedSelection) {
                    restoreSelection(savedSelection);
                }

                // Restore zoom level
                if (zoomWasReset && originalZoom !== null) {
                    await setZoomLevel(originalZoom);
                }

                if (!screenshot.ok) {
                    return {
                        ok: false,
                        error: screenshot.error || 'Screenshot capture failed',
                        mode: mode
                    };
                }

                // Collect page metadata for embedding
                const pageMetadata = collectPageMetadata();

                // Clean up picker highlight box after screenshot capture
                // This provides a cleaner UX when using URL scheme
                if (typeof window.__INSPEKT_UPDATE_HIGHLIGHT__ === 'function') {
                    // Clear the inspected element so highlight disappears
                    delete window.__INSPEKT_INSPECTED_ELEMENT__;
                    window.__INSPEKT_UPDATE_HIGHLIGHT__();
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
                    apiUsed: usedCDPFallback ? 'chrome.debugger (CDP)' : 'chrome.tabs.captureVisibleTab',
                    origin: window.location.origin,
                    url: window.location.href,
                    // Adjustment info for CLI feedback
                    scrolledIntoView: scrolledIntoView,
                    scrollDirection: scrollDirection,  // 'up', 'down', 'left', 'right', or null
                    usedCDPFallback: usedCDPFallback,
                    zoomWasReset: zoomWasReset,
                    originalZoom: originalZoom,
                    selectionCleared: selectionCleared,
                    elementIsolated: elementIsolated,  // true if --isolate was used
                    elementDimensions: {
                        width: Math.round(analysis.width),
                        height: Math.round(analysis.height),
                        viewportWidth: analysis.viewportWidth,
                        viewportHeight: analysis.viewportHeight
                    },
                    // Page metadata for embedding
                    ...pageMetadata
                };

            } catch (error) {
                // Ensure outline is restored on error
                if (options.hideOutline !== false) {
                    restoreOutline(elementInfo.element);
                }
                // Restore isolation state on error
                if (isolationState) {
                    restoreIsolation(isolationState);
                }
                // Restore scroll position on error too
                if (scrolledIntoView) {
                    window.scrollTo({
                        left: originalScrollX,
                        top: originalScrollY,
                        behavior: 'instant'
                    });
                }
                // Restore text selection on error
                if (savedSelection) {
                    restoreSelection(savedSelection);
                }
                // Restore zoom level on error
                if (zoomWasReset && originalZoom !== null) {
                    await setZoomLevel(originalZoom);
                }
                throw error;
            }

        } else if (mode === 'viewport') {
            // Viewport screenshot: capture visible viewport

            // Track adjustments for CLI feedback
            let zoomWasReset = false;
            let originalZoom = null;
            let savedSelection = null;
            let selectionCleared = false;

            // === PREPARE PAGE STATE FOR SCREENSHOT ===

            // 1. Check and reset zoom level if needed (unless --keep-zoom)
            if (!options.keepZoom) {
                originalZoom = await getZoomLevel();
                if (originalZoom !== 1.0) {
                    await setZoomLevel(1.0);
                    zoomWasReset = true;
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
            }

            // 2. Save and clear text selection if any (unless --keep-selection)
            if (!options.keepSelection) {
                savedSelection = saveSelection();
                if (savedSelection) {
                    clearSelection();
                    selectionCleared = true;
                    await new Promise(resolve => setTimeout(resolve, 50));
                }
            }

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

            // === RESTORE PAGE STATE AFTER SCREENSHOT ===

            // Restore text selection
            if (savedSelection) {
                restoreSelection(savedSelection);
            }

            // Restore zoom level
            if (zoomWasReset && originalZoom !== null) {
                await setZoomLevel(originalZoom);
            }

            if (!screenshot.ok) {
                return {
                    ok: false,
                    error: screenshot.error || 'Screenshot capture failed',
                    mode: mode
                };
            }

            // Collect page metadata for embedding
            const pageMetadata = collectPageMetadata();

            return {
                ok: true,
                mode: mode,
                dataUrl: screenshot.dataUrl,
                width: screenshot.width,
                height: screenshot.height,
                fileSize: screenshot.fileSize || null,
                apiUsed: 'chrome.tabs.captureVisibleTab',
                origin: window.location.origin,
                url: window.location.href,
                // Adjustment info for CLI feedback
                zoomWasReset: zoomWasReset,
                originalZoom: originalZoom,
                selectionCleared: selectionCleared,
                // Page metadata for embedding
                ...pageMetadata
            };

        } else if (mode === 'page') {
            // Full page screenshot: uses CDP (Chrome DevTools Protocol) for single-shot capture

            // Track adjustments for CLI feedback
            let zoomWasReset = false;
            let originalZoom = null;
            let savedSelection = null;
            let selectionCleared = false;

            // === PREPARE PAGE STATE FOR SCREENSHOT ===

            // 1. Check and reset zoom level if needed (unless --keep-zoom)
            if (!options.keepZoom) {
                originalZoom = await getZoomLevel();
                if (originalZoom !== 1.0) {
                    await setZoomLevel(1.0);
                    zoomWasReset = true;
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
            }

            // 2. Save and clear text selection if any (unless --keep-selection)
            if (!options.keepSelection) {
                savedSelection = saveSelection();
                if (savedSelection) {
                    clearSelection();
                    selectionCleared = true;
                    await new Promise(resolve => setTimeout(resolve, 50));
                }
            }

            // Request screenshot from extension (uses chrome.debugger API)
            const screenshot = await requestScreenshotFromExtension('page', {
                margin: options.margin || 0,
                marginColor: options.marginColor || 'auto',
                scale: options.scale || 1,
                quality: options.quality || 0.92,
                format: options.format || 'png',
                maxHeight: options.maxHeight || 16384
            });

            // === RESTORE PAGE STATE AFTER SCREENSHOT ===

            // Restore text selection
            if (savedSelection) {
                restoreSelection(savedSelection);
            }

            // Restore zoom level
            if (zoomWasReset && originalZoom !== null) {
                await setZoomLevel(originalZoom);
            }

            if (!screenshot.ok) {
                return {
                    ok: false,
                    error: screenshot.error || 'Screenshot capture failed',
                    mode: mode
                };
            }

            // Collect page metadata for embedding
            const pageMetadata = collectPageMetadata();

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
                url: window.location.href,
                // Adjustment info for CLI feedback
                zoomWasReset: zoomWasReset,
                originalZoom: originalZoom,
                selectionCleared: selectionCleared,
                // Page metadata for embedding
                ...pageMetadata
            };

        } else if (mode === 'selection') {
            // Selection screenshot: capture a specific clip region (from interactive selection)
            // Uses CDP for precise clipping

            const clip = options.clip;

            if (!clip || typeof clip.x !== 'number' || typeof clip.y !== 'number' ||
                typeof clip.width !== 'number' || typeof clip.height !== 'number') {
                return {
                    ok: false,
                    error: 'Selection mode requires clip coordinates (x, y, width, height)',
                    mode: mode
                };
            }

            // Validate clip dimensions
            if (clip.width <= 0 || clip.height <= 0) {
                return {
                    ok: false,
                    error: 'Selection clip dimensions must be positive',
                    mode: mode
                };
            }

            // Track adjustments for CLI feedback
            let zoomWasReset = false;
            let originalZoom = null;

            // === PREPARE PAGE STATE FOR SCREENSHOT ===

            // 1. Check and reset zoom level if needed (unless --keep-zoom)
            if (!options.keepZoom) {
                originalZoom = await getZoomLevel();
                if (originalZoom !== 1.0) {
                    await setZoomLevel(1.0);
                    zoomWasReset = true;
                    await new Promise(resolve => setTimeout(resolve, 200));
                }
            }

            // Request screenshot from extension using CDP with clip
            const screenshot = await requestScreenshotFromExtension('selection-cdp', {
                clip: {
                    x: clip.x,
                    y: clip.y,
                    width: clip.width,
                    height: clip.height
                },
                margin: options.margin || 0,
                marginColor: options.marginColor || 'auto',
                scale: options.scale || 2,
                quality: options.quality || 0.92,
                format: options.format || 'png'
            });

            // === RESTORE PAGE STATE AFTER SCREENSHOT ===

            // Restore zoom level
            if (zoomWasReset && originalZoom !== null) {
                await setZoomLevel(originalZoom);
            }

            if (!screenshot.ok) {
                return {
                    ok: false,
                    error: screenshot.error || 'Screenshot capture failed',
                    mode: mode
                };
            }

            // Collect page metadata for embedding
            const pageMetadata = collectPageMetadata();

            return {
                ok: true,
                mode: mode,
                dataUrl: screenshot.dataUrl,
                width: screenshot.width,
                height: screenshot.height,
                fileSize: screenshot.fileSize || null,
                apiUsed: 'chrome.debugger (CDP)',
                origin: window.location.origin,
                url: window.location.href,
                // Adjustment info for CLI feedback
                zoomWasReset: zoomWasReset,
                originalZoom: originalZoom,
                // Page metadata for embedding
                ...pageMetadata
            };

        } else {
            return {
                ok: false,
                error: `Invalid screenshot mode: ${mode}. Must be 'node', 'viewport', 'page', or 'selection'.`,
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
