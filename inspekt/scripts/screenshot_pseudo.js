/**
 * Pseudo-state screenshot script for capturing elements in forced CSS states
 *
 * Forces :hover, :focus, :active, etc. states on an element before capturing.
 * Uses CDP CSS.forcePseudoState with CSS injection fallback.
 *
 * Placeholders:
 * - STATE_PLACEHOLDER: 'hover' | 'focus' | 'focus-visible' | 'focus-within' | 'active' | 'target' | 'normal'
 * - OPTIONS_PLACEHOLDER: JSON object with screenshot options
 */

(async function() {
    const pseudoState = 'STATE_PLACEHOLDER';
    const options = OPTIONS_PLACEHOLDER;

    /**
     * Force pseudo-state via CDP through extension
     */
    async function forcePseudoStateViaCDP(state, selector) {
        const requestId = 'pseudo-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                window.removeEventListener('message', handler);
                resolve({ ok: false, error: 'CDP pseudo-state request timed out' });
            }, 10000);

            const handler = (event) => {
                if (event.source !== window) return;
                const msg = event.data;
                if (msg?.type === 'INSPEKT_PSEUDO_STATE_RESPONSE' &&
                    msg?.source === 'inspekt-extension' &&
                    msg?.requestId === requestId) {
                    clearTimeout(timeout);
                    window.removeEventListener('message', handler);
                    resolve(msg.response);
                }
            };

            window.addEventListener('message', handler);
            window.postMessage({
                type: 'INSPEKT_FORCE_PSEUDO_STATE',
                source: 'inspekt-page',
                requestId: requestId,
                state: state,
                selector: selector
            }, '*');
        });
    }

    /**
     * Clear pseudo-state via CDP
     */
    async function clearPseudoStateViaCDP() {
        const requestId = 'clear-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

        return new Promise((resolve) => {
            const timeout = setTimeout(() => {
                window.removeEventListener('message', handler);
                resolve({ ok: true }); // Best-effort cleanup
            }, 5000);

            const handler = (event) => {
                if (event.source !== window) return;
                const msg = event.data;
                if (msg?.type === 'INSPEKT_CLEAR_PSEUDO_STATE_RESPONSE' &&
                    msg?.source === 'inspekt-extension' &&
                    msg?.requestId === requestId) {
                    clearTimeout(timeout);
                    window.removeEventListener('message', handler);
                    resolve(msg.response);
                }
            };

            window.addEventListener('message', handler);
            window.postMessage({
                type: 'INSPEKT_CLEAR_PSEUDO_STATE',
                source: 'inspekt-page',
                requestId: requestId
            }, '*');
        });
    }

    /**
     * CSS injection fallback for when CDP is unavailable
     * Collects :state rules and applies them via data attribute
     */
    function forcePseudoStateViaCSSInjection(element, state) {
        console.log('[Inspekt] CSS injection fallback for :' + state);

        // Add marker attribute to element
        element.dataset.inspektPseudoState = state;

        // Also add to ancestors for :hover on parent scenarios
        let ancestor = element.parentElement;
        while (ancestor && ancestor !== document.body) {
            ancestor.dataset.inspektPseudoStateChild = state;
            ancestor = ancestor.parentElement;
        }

        // Calculate CSS specificity (simplified: count IDs, classes, elements)
        function getSpecificity(sel) {
            const ids = (sel.match(/#[a-zA-Z][a-zA-Z0-9_-]*/g) || []).length;
            const classes = (sel.match(/\.[a-zA-Z][a-zA-Z0-9_-]*/g) || []).length;
            const attrs = (sel.match(/\[[^\]]+\]/g) || []).length;
            const pseudoClasses = (sel.match(/:[a-zA-Z][a-zA-Z0-9-]*/g) || []).length;
            const elements = (sel.match(/^[a-zA-Z]+|\s+[a-zA-Z]+/g) || []).length;
            return ids * 10000 + (classes + attrs + pseudoClasses) * 100 + elements;
        }

        // Collect matching rules from stylesheets
        const collectedRules = [];
        const stateRegex = new RegExp(`:${state}(?![a-zA-Z-])`, 'g');
        let sheetsChecked = 0;
        let rulesChecked = 0;

        for (const sheet of document.styleSheets) {
            try {
                sheetsChecked++;
                for (const rule of sheet.cssRules) {
                    rulesChecked++;
                    if (rule.selectorText?.includes(`:${state}`)) {
                        // Try to check if rule applies to this element or its ancestors
                        try {
                            const baseSelector = rule.selectorText.replace(stateRegex, '').trim();
                            // Skip empty selectors
                            if (!baseSelector) continue;

                            const appliesToElement = element.matches(baseSelector);
                            const appliesToAncestor = element.closest(baseSelector);

                            if (appliesToElement || appliesToAncestor) {
                                // Transform selector: replace :state with attribute selector
                                const newSelector = rule.selectorText.replace(
                                    stateRegex,
                                    `[data-inspekt-pseudo-state="${state}"]`
                                );

                                // Add !important to all properties for higher specificity
                                let cssText = rule.style.cssText;
                                cssText = cssText.replace(/;/g, ' !important;');
                                if (!cssText.endsWith(';')) {
                                    cssText += ' !important';
                                }

                                collectedRules.push({
                                    specificity: getSpecificity(rule.selectorText),
                                    css: `${newSelector} { ${cssText} }`
                                });
                                console.log('[Inspekt] Found matching rule:', rule.selectorText, '→', newSelector);
                            }
                        } catch (e) {
                            // Complex selector that can't be matched, try injecting anyway
                            const newSelector = rule.selectorText.replace(
                                stateRegex,
                                `[data-inspekt-pseudo-state="${state}"]`
                            );
                            let cssText = rule.style.cssText;
                            cssText = cssText.replace(/;/g, ' !important;');
                            collectedRules.push({
                                specificity: 0, // Unknown specificity, inject first
                                css: `${newSelector} { ${cssText} }`
                            });
                        }
                    }
                }
            } catch (e) {
                // CORS blocks cross-origin stylesheets
                console.log('[Inspekt] Skipped cross-origin stylesheet');
            }
        }

        console.log(`[Inspekt] Checked ${sheetsChecked} stylesheets, ${rulesChecked} rules, found ${collectedRules.length} matching :${state} rules`);

        // Sort by specificity (lowest first, so highest specificity rules come last and win)
        collectedRules.sort((a, b) => a.specificity - b.specificity);
        const injectedRules = collectedRules.map(r => r.css);

        // Inject collected rules
        if (injectedRules.length > 0) {
            const style = document.createElement('style');
            style.id = 'inspekt-pseudo-state-override';
            style.textContent = injectedRules.join('\n');
            document.head.appendChild(style);
            console.log('[Inspekt] Injected', injectedRules.length, 'CSS rules (sorted by specificity)');
        } else {
            console.warn('[Inspekt] No CSS rules found for :' + state + ' - the element may not have ' + state + ' styles defined');
        }

        return {
            ok: true,
            method: 'css-injection',
            rulesInjected: injectedRules.length
        };
    }

    /**
     * Clear CSS injection fallback
     */
    function clearPseudoStateViaCSSInjection(element) {
        // Remove attribute from element
        delete element.dataset.inspektPseudoState;

        // Remove from ancestors
        document.querySelectorAll('[data-inspekt-pseudo-state-child]').forEach(el => {
            delete el.dataset.inspektPseudoStateChild;
        });

        // Remove injected style
        const style = document.getElementById('inspekt-pseudo-state-override');
        if (style) style.remove();
    }

    /**
     * Request screenshot from extension
     */
    async function requestScreenshotFromExtension(captureOptions) {
        const requestId = 'screenshot-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

        return new Promise((resolve) => {
            const timeout = setTimeout(() => {
                window.removeEventListener('message', handler);
                resolve({ ok: false, error: 'Screenshot request timed out' });
            }, 30000);

            const handler = (event) => {
                if (event.source !== window) return;
                const msg = event.data;
                if (msg?.type === 'INSPEKT_SCREENSHOT_RESPONSE' &&
                    msg?.source === 'inspekt-extension' &&
                    msg?.requestId === requestId) {
                    clearTimeout(timeout);
                    window.removeEventListener('message', handler);
                    resolve(msg.response);
                }
            };

            window.addEventListener('message', handler);
            window.postMessage({
                type: 'INSPEKT_CAPTURE_SCREENSHOT',
                source: 'inspekt-page',
                requestId: requestId,
                mode: 'node',
                options: captureOptions
            }, '*');
        });
    }

    /**
     * Get element bounds for screenshot
     */
    function getElementBounds(element) {
        const rect = element.getBoundingClientRect();
        const scrollX = window.scrollX || window.pageXOffset;
        const scrollY = window.scrollY || window.pageYOffset;

        return {
            x: rect.left + scrollX,
            y: rect.top + scrollY,
            width: rect.width,
            height: rect.height,
            viewportX: rect.left,
            viewportY: rect.top
        };
    }

    // ========== MAIN EXECUTION ==========

    try {
        // Get target element
        const element = options.selector
            ? document.querySelector(options.selector)
            : window.__INSPEKT_INSPECTED_ELEMENT__;

        if (!element) {
            return {
                ok: false,
                error: 'No element found. Select an element in DevTools or provide a selector.'
            };
        }

        // Get element info for response
        const tagName = element.tagName?.toLowerCase() || 'element';
        const elementId = element.id || null;
        const bounds = getElementBounds(element);

        // Track which method was used
        let method = 'none';
        let usedFallback = false;
        let rulesInjected = 0;

        // Force pseudo-state (skip for 'normal')
        if (pseudoState !== 'normal') {
            // Try CDP first
            const cdpResult = await forcePseudoStateViaCDP(pseudoState, options.selector);

            // Check if CDP succeeded (handle undefined response)
            if (cdpResult && cdpResult.ok) {
                method = 'cdp';
            } else {
                // CDP failed or unavailable (common when DevTools is open), use CSS injection
                const errorMsg = cdpResult?.error || 'CDP unavailable (DevTools open)';
                console.log('[Inspekt] Using CSS injection for :' + pseudoState + ' (' + errorMsg + ')');
                const cssResult = forcePseudoStateViaCSSInjection(element, pseudoState);
                method = 'css-injection';
                usedFallback = true;
                rulesInjected = cssResult.rulesInjected || 0;

                if (rulesInjected === 0) {
                    console.warn('[Inspekt] No CSS rules found for :' + pseudoState + ' state');
                }
            }

            // Wait for repaint
            await new Promise(r => setTimeout(r, 100));
        }

        // Scroll element into view if requested
        if (options.scrollIntoView !== false) {
            element.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
            await new Promise(r => setTimeout(r, 50));
        }

        // Hide element outline if requested
        let originalOutline = null;
        let originalBoxShadow = null;
        if (options.hideOutline !== false) {
            originalOutline = element.style.outline;
            originalBoxShadow = element.style.boxShadow;
            element.style.outline = 'none';
            element.style.boxShadow = 'none';
        }

        // Build screenshot options
        const screenshotOptions = {
            selector: options.selector,
            tagName: tagName,
            bounds: bounds,
            margin: options.margin || 0,
            marginColor: options.marginColor || 'auto',
            scale: options.scale || 2,
            format: options.format || 'png',
            quality: options.quality || 0.92
        };

        // Capture screenshot
        const screenshotResult = await requestScreenshotFromExtension(screenshotOptions);

        // Restore outline
        if (options.hideOutline !== false) {
            element.style.outline = originalOutline;
            element.style.boxShadow = originalBoxShadow;
        }

        // Clear pseudo-state
        if (pseudoState !== 'normal') {
            if (method === 'cdp') {
                await clearPseudoStateViaCDP();
            } else if (method === 'css-injection') {
                clearPseudoStateViaCSSInjection(element);
            }
        }

        // Return result
        if (!screenshotResult.ok) {
            return screenshotResult;
        }

        return {
            ok: true,
            state: pseudoState,
            method: method,
            usedFallback: usedFallback,
            rulesInjected: rulesInjected,
            dataUrl: screenshotResult.dataUrl,
            width: screenshotResult.width,
            height: screenshotResult.height,
            tagName: tagName,
            elementId: elementId
        };

    } catch (error) {
        console.error('[Inspekt] Pseudo-state screenshot error:', error);

        // Attempt cleanup
        try {
            await clearPseudoStateViaCDP();
        } catch (e) {}

        const el = options.selector
            ? document.querySelector(options.selector)
            : window.__INSPEKT_INSPECTED_ELEMENT__;
        if (el) {
            clearPseudoStateViaCSSInjection(el);
        }

        return {
            ok: false,
            error: String(error)
        };
    }
})()
