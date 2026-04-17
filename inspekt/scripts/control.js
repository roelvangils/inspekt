// Remote control - receive and simulate keypresses from CLI
(function() {
    const action = 'ACTION_PLACEHOLDER'; // 'start', 'stop', 'send'
    const keyData = KEY_DATA_PLACEHOLDER;
    const config = CONFIG_PLACEHOLDER;

    if (action === 'start') {
        // If control is already active but functions are missing, allow reinitialization
        const needsReinit = window.__ZEN_CONTROL_ACTIVE__ && !window.__ZEN_CONTROL_UPDATE_HIGHLIGHT__;

        if (window.__ZEN_CONTROL_ACTIVE__ && !needsReinit) {
            return { ok: true, message: 'Control already active' };
        }

        window.__ZEN_CONTROL_ACTIVE__ = true;

        // Persist control state across page reloads using sessionStorage
        try {
            sessionStorage.setItem('__ZEN_CONTROL_ACTIVE__', 'true');
            sessionStorage.setItem('__ZEN_CONTROL_CONFIG__', JSON.stringify(config));
        } catch (e) {
            // Ignore if sessionStorage is not available
        }

        // Track the virtually focused element (independent of browser focus)
        window.__ZEN_CONTROL_CURRENT_ELEMENT__ = document.activeElement || document.body;

        // Add focus highlight styles based on configuration
        const focusOutlineMode = config['focus-outline'] || 'custom';

        if (focusOutlineMode !== 'none' && !document.getElementById('inspekt-control-styles')) {
            const style = document.createElement('style');
            style.id = 'inspekt-control-styles';

            if (focusOutlineMode === 'custom') {
                // Custom blue outline with configurable appearance
                const focusColor = config['focus-color'] || '#0066ff';
                const focusSize = config['focus-size'] || 3;
                const focusGlow = config['focus-glow'] !== false;
                const focusAnimation = config['focus-animation'] !== false;

                // Parse color for rgba if it's hex
                let glowColor = 'rgba(0, 102, 255, 0.3)';
                let glowColorBright = 'rgba(0, 102, 255, 0.5)';
                if (focusColor.startsWith('#')) {
                    const r = parseInt(focusColor.slice(1, 3), 16);
                    const g = parseInt(focusColor.slice(3, 5), 16);
                    const b = parseInt(focusColor.slice(5, 7), 16);
                    glowColor = `rgba(${r}, ${g}, ${b}, 0.3)`;
                    glowColorBright = `rgba(${r}, ${g}, ${b}, 0.5)`;
                }

                const boxShadow = focusGlow
                    ? `0 0 0 2px ${glowColor}, 0 0 12px ${glowColorBright}`
                    : 'none';
                const animation = focusAnimation ? 'inspekt-pulse 2s infinite' : 'none';

                style.textContent = `
                    [data-inspekt-control-focus] {
                        position: relative !important;
                    }
                    [data-inspekt-control-focus]::after {
                        content: '' !important;
                        position: absolute !important;
                        top: -${focusSize + 1}px !important;
                        left: -${focusSize + 1}px !important;
                        right: -${focusSize + 1}px !important;
                        bottom: -${focusSize + 1}px !important;
                        border: ${focusSize}px solid ${focusColor} !important;
                        border-radius: 4px !important;
                        pointer-events: none !important;
                        z-index: 2147483647 !important;
                        box-shadow: ${boxShadow} !important;
                        animation: ${animation} !important;
                    }
                    @keyframes inspekt-pulse {
                        0%, 100% { opacity: 1; }
                        50% { opacity: 0.7; }
                    }
                `;
            } else if (focusOutlineMode === 'original') {
                // Use the browser's original :focus styles
                // Apply the outline/border styles that would normally appear on :focus
                style.textContent = `
                    [data-inspekt-control-focus] {
                        outline: var(--inspekt-original-outline, auto 2px Highlight) !important;
                        outline-offset: var(--inspekt-original-outline-offset, 0) !important;
                    }
                `;
            }

            document.head.appendChild(style);
        }

        // Update visual highlight
        function updateHighlight(element) {
            // Remove previous highlight
            const prev = document.querySelector('[data-inspekt-control-focus]');
            if (prev) {
                prev.removeAttribute('data-inspekt-control-focus');
            }

            // Add highlight to new element (unless focus-outline is 'none')
            if (element && element !== document.body && element !== document.documentElement) {
                window.__ZEN_CONTROL_CURRENT_ELEMENT__ = element;

                // Only add visual highlight if not in 'none' mode
                if (focusOutlineMode !== 'none') {
                    element.setAttribute('data-inspekt-control-focus', '');
                }

                // Scroll into view if configured
                if (config['scroll-on-focus'] !== false) {
                    element.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            }
        }

        // Initial highlight
        updateHighlight(window.__ZEN_CONTROL_CURRENT_ELEMENT__);

        // Store the update function for use by key handler
        window.__ZEN_CONTROL_UPDATE_HIGHLIGHT__ = updateHighlight;

        // Function to generate multiple selector strategies for an element
        window.__ZEN_CONTROL_GENERATE_SELECTORS__ = function(el) {
            if (!el) return [];

            const selectors = [];

            // Strategy 1: ID (most stable)
            if (el.id) {
                selectors.push({
                    type: 'id',
                    value: `#${CSS.escape(el.id)}`
                });
            }

            // Strategy 2: Data attributes (exclude our own control attributes)
            const dataAttrs = Array.from(el.attributes)
                .filter(attr => attr.name.startsWith('data-') && !attr.name.startsWith('data-inspekt-'))
                .map(attr => `[${attr.name}="${CSS.escape(attr.value)}"]`);
            if (dataAttrs.length > 0) {
                selectors.push({
                    type: 'data-attr',
                    value: el.tagName.toLowerCase() + dataAttrs.join('')
                });
            }

            // Strategy 3: ARIA + role
            const ariaLabel = el.getAttribute('aria-label');
            const role = el.getAttribute('role');
            if (ariaLabel || role) {
                let selector = el.tagName.toLowerCase();
                if (role) selector += `[role="${role}"]`;
                if (ariaLabel) selector += `[aria-label="${CSS.escape(ariaLabel)}"]`;
                selectors.push({
                    type: 'aria',
                    value: selector
                });
            }

            // Strategy 4: CSS with classes (+ text for links/buttons)
            if (el.className && typeof el.className === 'string') {
                const classes = el.className.trim().split(/\s+/)
                    .filter(c => c && !c.startsWith('focus') && !c.startsWith('active'))
                    .map(c => `.${CSS.escape(c)}`);
                if (classes.length > 0) {
                    const cssSelector = el.tagName.toLowerCase() + classes.join('');
                    // For links and buttons, combine with text content for uniqueness
                    const text = el.textContent.trim();
                    if (text && text.length < 100 && (el.tagName === 'A' || el.tagName === 'BUTTON')) {
                        selectors.push({
                            type: 'css-class-text',
                            cssSelector: cssSelector,
                            text: text,
                            value: cssSelector + ` (text: "${text}")`  // For debugging
                        });
                    } else {
                        selectors.push({
                            type: 'css-class',
                            value: cssSelector
                        });
                    }
                }
            }

            // Strategy 5: Name attribute (for form elements)
            if (el.name) {
                selectors.push({
                    type: 'name',
                    value: `${el.tagName.toLowerCase()}[name="${CSS.escape(el.name)}"]`
                });
            }

            // Strategy 6: Text content (for links, buttons)
            const text = el.textContent.trim();
            if (text && text.length < 100 && (el.tagName === 'A' || el.tagName === 'BUTTON')) {
                selectors.push({
                    type: 'text',
                    value: text
                });
            }

            return selectors;
        };

        // Function to find element using selector strategies
        window.__ZEN_CONTROL_FIND_ELEMENT__ = function(selectors) {
            for (const selector of selectors) {
                try {
                    if (selector.type === 'css-class-text') {
                        // Combined CSS + text selector for links/buttons
                        const elements = Array.from(document.querySelectorAll(selector.cssSelector));
                        const match = elements.find(el => el.textContent.trim() === selector.text);
                        if (match) return match;
                    } else if (selector.type === 'text') {
                        // For text-based selectors, find all matching elements
                        const elements = Array.from(document.querySelectorAll('a, button'));
                        const match = elements.find(el => el.textContent.trim() === selector.value);
                        if (match) return match;
                    } else {
                        // For CSS selectors
                        const element = document.querySelector(selector.value);
                        if (element) return element;
                    }
                } catch (e) {
                    // Invalid selector, continue to next
                    continue;
                }
            }
            return null;
        };

        // Function to compute accessible name (simplified from get_inspected.js)
        window.__ZEN_CONTROL_GET_ACCESSIBLE_NAME__ = function(el) {
            if (!el || el === document.body || el === document.documentElement) {
                return '';
            }

            // Step 1: aria-labelledby
            const labelledBy = el.getAttribute('aria-labelledby');
            if (labelledBy) {
                const ids = labelledBy.trim().split(/\s+/);
                const labels = ids.map(id => {
                    const labelEl = document.getElementById(id);
                    return labelEl ? labelEl.textContent.trim() : '';
                }).filter(text => text);
                if (labels.length > 0) {
                    return labels.join(' ');
                }
            }

            // Step 2: aria-label
            const ariaLabel = el.getAttribute('aria-label');
            if (ariaLabel && ariaLabel.trim()) {
                return ariaLabel.trim();
            }

            // Step 3: Native labeling
            if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
                const labels = document.querySelectorAll(`label[for="${el.id}"]`);
                if (labels.length > 0) {
                    return labels[0].textContent.trim();
                }
                const parentLabel = el.closest('label');
                if (parentLabel) {
                    return parentLabel.textContent.trim();
                }
            }

            // Step 4: alt attribute (images)
            if (el.tagName === 'IMG') {
                const alt = el.getAttribute('alt');
                if (alt !== null) {
                    return alt.trim();
                }
            }

            // Step 5: value (buttons, inputs)
            if (el.tagName === 'INPUT' && (el.type === 'button' || el.type === 'submit' || el.type === 'reset')) {
                if (el.value) return el.value.trim();
            }

            // Step 6: title attribute
            const title = el.getAttribute('title');
            if (title && title.trim()) {
                return title.trim();
            }

            // Step 7: placeholder
            const placeholder = el.getAttribute('placeholder');
            if (placeholder && placeholder.trim()) {
                return placeholder.trim();
            }

            // Step 8: text content
            const text = el.textContent.trim();
            if (text) {
                return text.substring(0, 100); // Limit length
            }

            return '';
        };

        // Set up auto-refocus if configured
        const autoRefocus = config['auto-refocus'];
        console.log('[Zen Bridge] Auto-refocus config:', autoRefocus);
        console.log('[Zen Bridge] Existing selectors:', window.__ZEN_CONTROL_REFOCUS_SELECTORS__);

        if (autoRefocus === 'always' || autoRefocus === 'only-spa') {
            console.log('[Zen Bridge] Setting up auto-refocus…');
            // Store the current URL to detect navigation
            window.__ZEN_CONTROL_INITIAL_URL__ = location.href;

            // Listen for page loads to attempt refocus
            const refocusHandler = function() {
                const refocusTimeout = config['refocus-timeout'] || 2000;

                console.log('[Zen Bridge] Refocus handler triggered, waiting', refocusTimeout, 'ms');

                setTimeout(() => {
                    if (!window.__ZEN_CONTROL_ACTIVE__) {
                        console.log('[Zen Bridge] Refocus aborted: control not active');
                        return;
                    }

                    // Check if we have stored selectors
                    const storedSelectors = window.__ZEN_CONTROL_REFOCUS_SELECTORS__;
                    if (!storedSelectors || storedSelectors.length === 0) {
                        console.log('[Zen Bridge] No refocus selectors stored');
                        return;
                    }

                    console.log('[Zen Bridge] Attempting refocus with selectors:', storedSelectors);

                    // For 'only-spa', check if we're still on the same origin
                    if (autoRefocus === 'only-spa') {
                        const currentOrigin = new URL(location.href).origin;
                        const initialOrigin = new URL(window.__ZEN_CONTROL_INITIAL_URL__).origin;
                        console.log('[Zen Bridge] Origin check:', currentOrigin, 'vs', initialOrigin);
                        if (currentOrigin !== initialOrigin) {
                            // Different origin, don't refocus
                            console.log('[Zen Bridge] Different origin, skipping refocus');
                            delete window.__ZEN_CONTROL_REFOCUS_SELECTORS__;
                            return;
                        }
                    }

                    // Try to find the element
                    const element = window.__ZEN_CONTROL_FIND_ELEMENT__(storedSelectors);
                    const verbose = config['verbose'] !== false;

                    if (element) {
                        console.log('[Zen Bridge] ✓ Element found, refocusing:', element);
                        // Refocus the element
                        element.focus();
                        window.__ZEN_CONTROL_CURRENT_ELEMENT__ = element;
                        if (window.__ZEN_CONTROL_UPDATE_HIGHLIGHT__) {
                            window.__ZEN_CONTROL_UPDATE_HIGHLIGHT__(element);
                        }

                        // Send immediate notification via WebSocket
                        if (verbose && window.__inspekt_ws__ && window.__inspekt_ws__.readyState === WebSocket.OPEN) {
                            window.__inspekt_ws__.send(JSON.stringify({
                                type: 'refocus_notification',
                                success: true,
                                message: 'Focus restored'
                            }));
                        }

                        // Clear stored selectors
                        delete window.__ZEN_CONTROL_REFOCUS_SELECTORS__;

                        // Also clear from sessionStorage
                        try {
                            sessionStorage.removeItem('__ZEN_CONTROL_REFOCUS_SELECTORS__');
                            sessionStorage.removeItem('__ZEN_CONTROL_INITIAL_URL__');
                        } catch (e) {
                            // Ignore
                        }
                    } else {
                        console.log('[Zen Bridge] ✗ Could not find element to refocus');

                        // Send immediate notification via WebSocket
                        if (verbose && window.__inspekt_ws__ && window.__inspekt_ws__.readyState === WebSocket.OPEN) {
                            window.__inspekt_ws__.send(JSON.stringify({
                                type: 'refocus_notification',
                                success: false,
                                message: 'Focus lost. Starting from top.'
                            }));
                        }

                        // Clear stored selectors
                        delete window.__ZEN_CONTROL_REFOCUS_SELECTORS__;
                    }
                }, refocusTimeout);
            };

            // Listen for various navigation events
            window.addEventListener('load', refocusHandler);
            window.addEventListener('popstate', refocusHandler);

            // For SPAs, also listen for DOM changes
            if (autoRefocus === 'only-spa') {
                const observer = new MutationObserver(() => {
                    // Debounce - only trigger after significant changes
                    clearTimeout(window.__ZEN_CONTROL_MUTATION_TIMEOUT__);
                    window.__ZEN_CONTROL_MUTATION_TIMEOUT__ = setTimeout(refocusHandler, 200);
                });
                observer.observe(document.body, { childList: true, subtree: true });
                window.__ZEN_CONTROL_MUTATION_OBSERVER__ = observer;
            }

            window.__ZEN_CONTROL_REFOCUS_HANDLER__ = refocusHandler;

            // If we're reinitializing and refocus selectors exist, trigger refocus now
            // (The page is already loaded, so 'load' event won't fire again)
            if (window.__ZEN_CONTROL_REFOCUS_SELECTORS__) {
                console.log('[Zen Bridge] Refocus selectors exist, triggering refocus immediately');
                console.log('[Zen Bridge] Stored selectors:', window.__ZEN_CONTROL_REFOCUS_SELECTORS__);
                // Wait a bit for the page to settle, then trigger
                setTimeout(() => {
                    console.log('[Zen Bridge] Executing delayed refocus trigger…');
                    refocusHandler();
                }, 100);
            } else {
                console.log('[Zen Bridge] No refocus selectors found');
            }
        }

        return {
            ok: true,
            message: 'Control started',
            title: document.title,
            url: location.href
        };
    }

    if (action === 'stop') {
        delete window.__ZEN_CONTROL_ACTIVE__;

        // Remove focus highlight listener
        if (window.__ZEN_CONTROL_FOCUS_HANDLER__) {
            document.removeEventListener('focusin', window.__ZEN_CONTROL_FOCUS_HANDLER__, true);
            delete window.__ZEN_CONTROL_FOCUS_HANDLER__;
        }

        // Remove refocus handler
        if (window.__ZEN_CONTROL_REFOCUS_HANDLER__) {
            window.removeEventListener('load', window.__ZEN_CONTROL_REFOCUS_HANDLER__);
            window.removeEventListener('popstate', window.__ZEN_CONTROL_REFOCUS_HANDLER__);
            delete window.__ZEN_CONTROL_REFOCUS_HANDLER__;
        }

        // Disconnect mutation observer
        if (window.__ZEN_CONTROL_MUTATION_OBSERVER__) {
            window.__ZEN_CONTROL_MUTATION_OBSERVER__.disconnect();
            delete window.__ZEN_CONTROL_MUTATION_OBSERVER__;
        }

        // Remove highlight from current element
        const highlighted = document.querySelector('[data-inspekt-control-focus]');
        if (highlighted) {
            highlighted.removeAttribute('data-inspekt-control-focus');
        }

        // Remove styles
        const styles = document.getElementById('inspekt-control-styles');
        if (styles) {
            styles.remove();
        }

        // Clean up stored data
        delete window.__ZEN_CONTROL_REFOCUS_SELECTORS__;

        // Clear sessionStorage
        try {
            sessionStorage.removeItem('__ZEN_CONTROL_ACTIVE__');
            sessionStorage.removeItem('__ZEN_CONTROL_CONFIG__');
            sessionStorage.removeItem('__ZEN_CONTROL_REFOCUS_SELECTORS__');
            sessionStorage.removeItem('__ZEN_CONTROL_INITIAL_URL__');
        } catch (e) {
            // Ignore if sessionStorage is not available
        }

        return { ok: true, message: 'Control stopped' };
    }

    if (action === 'send') {
        if (!window.__ZEN_CONTROL_ACTIVE__) {
            return { ok: false, error: 'Control not active' };
        }

        // Check if helper functions are missing (e.g., after page reload with userscript auto-restart)
        if (!window.__ZEN_CONTROL_UPDATE_HIGHLIGHT__ || !window.__ZEN_CONTROL_GENERATE_SELECTORS__) {
            // Helper functions missing - need full reinitialization
            // Return special status so CLI knows to re-send 'start' command
            console.log('[Zen Bridge] Control functions missing, requesting reinitialization from CLI');
            return {
                ok: false,
                error: 'Control functions missing - reinitializing',
                needsRestart: true
            };
        }

        // Get the target element (use our virtual current element or fallback)
        const target = window.__ZEN_CONTROL_CURRENT_ELEMENT__ || document.activeElement || document.body;

        // Extract key data
        const key = keyData.key;
        const code = keyData.code || '';
        const ctrlKey = keyData.ctrl || false;
        const altKey = keyData.alt || false;
        const shiftKey = keyData.shift || false;
        const metaKey = keyData.meta || false;

        // Create event options
        const eventInit = {
            key: key,
            code: code,
            ctrlKey: ctrlKey,
            altKey: altKey,
            shiftKey: shiftKey,
            metaKey: metaKey,
            bubbles: true,
            cancelable: true,
            composed: true
        };

        // Dispatch keydown event
        const keydownEvent = new KeyboardEvent('keydown', eventInit);
        const keydownPrevented = !target.dispatchEvent(keydownEvent);

        // Handle special keys
        if (key === 'Tab') {
            // Handle Tab - move to next/previous focusable element
            if (!keydownPrevented) {
                // Get all focusable elements
                const focusableSelector = 'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])';
                const focusableElements = Array.from(document.querySelectorAll(focusableSelector))
                    .filter(el => {
                        // Filter out hidden elements
                        const style = window.getComputedStyle(el);
                        return style.display !== 'none' &&
                               style.visibility !== 'hidden' &&
                               !el.disabled;
                    });

                // Use our virtual current element
                const currentElement = window.__ZEN_CONTROL_CURRENT_ELEMENT__ || target;
                const currentIndex = focusableElements.indexOf(currentElement);

                let nextElement;
                const navigationWrap = config['navigation-wrap'] !== false;

                if (shiftKey) {
                    // Shift+Tab - go to previous element
                    if (currentIndex > 0) {
                        nextElement = focusableElements[currentIndex - 1];
                    } else if (navigationWrap) {
                        // Wrap to last element
                        nextElement = focusableElements[focusableElements.length - 1];
                    }
                } else {
                    // Tab - go to next element
                    if (currentIndex < focusableElements.length - 1) {
                        nextElement = focusableElements[currentIndex + 1];
                    } else if (navigationWrap) {
                        // Wrap to first element
                        nextElement = focusableElements[0];
                    }
                }

                if (nextElement) {
                    // Try to focus (might not work if window not active)
                    nextElement.focus();
                    // Update our virtual focus and visual highlight
                    window.__ZEN_CONTROL_CURRENT_ELEMENT__ = nextElement;
                    if (window.__ZEN_CONTROL_UPDATE_HIGHLIGHT__) {
                        window.__ZEN_CONTROL_UPDATE_HIGHLIGHT__(nextElement);
                    }

                    // Store accessible name and role for speak-name feature
                    if (window.__ZEN_CONTROL_GET_ACCESSIBLE_NAME__) {
                        window.__ZEN_CONTROL_LAST_FOCUSED_NAME__ = window.__ZEN_CONTROL_GET_ACCESSIBLE_NAME__(nextElement);
                        window.__ZEN_CONTROL_LAST_FOCUSED_ROLE__ = nextElement.getAttribute('role') || nextElement.tagName.toLowerCase();
                    }
                }
            }
        } else if (key === 'Enter') {
            // Handle Enter - activate the virtually focused element
            const currentElement = window.__ZEN_CONTROL_CURRENT_ELEMENT__ || target;
            const clickDelay = config['click-delay'] || 0;
            const verbose = config['verbose'] !== false;

            // Store element name for verbose messages
            let elementName = '';
            if (verbose && window.__ZEN_CONTROL_GET_ACCESSIBLE_NAME__) {
                elementName = window.__ZEN_CONTROL_GET_ACCESSIBLE_NAME__(currentElement);
            }

            if (!keydownPrevented) {
                // Before clicking, store selectors for auto-refocus
                const autoRefocus = config['auto-refocus'];
                if ((autoRefocus === 'always' || autoRefocus === 'only-spa') &&
                    window.__ZEN_CONTROL_GENERATE_SELECTORS__) {
                    const selectors = window.__ZEN_CONTROL_GENERATE_SELECTORS__(currentElement);
                    console.log('[Zen Bridge] Storing refocus selectors:', selectors);
                    window.__ZEN_CONTROL_REFOCUS_SELECTORS__ = selectors;

                    // Also persist to sessionStorage for page reloads
                    try {
                        sessionStorage.setItem('__ZEN_CONTROL_REFOCUS_SELECTORS__', JSON.stringify(selectors));
                        sessionStorage.setItem('__ZEN_CONTROL_INITIAL_URL__', location.href);
                        console.log('[Zen Bridge] Selectors saved to sessionStorage');
                    } catch (e) {
                        console.error('[Zen Bridge] Failed to save selectors:', e);
                    }
                }

                // Store opening message for verbose output
                if (verbose && elementName) {
                    window.__ZEN_CONTROL_OPENING_MESSAGE__ = `Opening '${elementName}'…`;
                }

                const performClick = () => {
                    if (currentElement.tagName === 'A') {
                        // For links, click them (supports SPAs)
                        currentElement.click();
                        // Keep virtual focus on the link
                        window.__ZEN_CONTROL_CURRENT_ELEMENT__ = currentElement;
                        // Store "opened" message
                        if (verbose && elementName) {
                            window.__ZEN_CONTROL_OPENED_MESSAGE__ = `'${elementName}' Opened`;
                        }
                    } else if (currentElement.tagName === 'BUTTON') {
                        // For buttons, click them
                        currentElement.click();
                        // Keep virtual focus on the button
                        window.__ZEN_CONTROL_CURRENT_ELEMENT__ = currentElement;
                        // Store "opened" message
                        if (verbose && elementName) {
                            window.__ZEN_CONTROL_OPENED_MESSAGE__ = `'${elementName}' Opened`;
                        }
                    } else if (currentElement.tagName === 'INPUT') {
                        if (currentElement.type === 'submit' || currentElement.type === 'button') {
                            // Click submit/button inputs
                            currentElement.click();
                            window.__ZEN_CONTROL_CURRENT_ELEMENT__ = currentElement;
                            if (verbose && elementName) {
                                window.__ZEN_CONTROL_OPENED_MESSAGE__ = `'${elementName}' Opened`;
                            }
                        } else if (currentElement.type === 'checkbox' || currentElement.type === 'radio') {
                            // Toggle checkbox/radio
                            currentElement.click();
                            window.__ZEN_CONTROL_CURRENT_ELEMENT__ = currentElement;
                        } else if (currentElement.form) {
                            // For other inputs in a form, submit the form
                            const submitEvent = new Event('submit', { bubbles: true, cancelable: true });
                            if (currentElement.form.dispatchEvent(submitEvent)) {
                                currentElement.form.submit();
                            }
                        }
                    } else if (currentElement.tagName === 'SELECT') {
                        // For select, just let the normal behavior happen
                    } else if (currentElement.getAttribute('role') === 'button' ||
                               currentElement.getAttribute('role') === 'link') {
                        // For elements with button/link roles, click them
                        currentElement.click();
                        window.__ZEN_CONTROL_CURRENT_ELEMENT__ = currentElement;
                        if (verbose && elementName) {
                            window.__ZEN_CONTROL_OPENED_MESSAGE__ = `'${elementName}' Opened`;
                        }
                    } else if (currentElement.onclick || currentElement.getAttribute('onclick')) {
                        // If it has a click handler, trigger it
                        currentElement.click();
                        window.__ZEN_CONTROL_CURRENT_ELEMENT__ = currentElement;
                        if (verbose && elementName) {
                            window.__ZEN_CONTROL_OPENED_MESSAGE__ = `'${elementName}' Opened`;
                        }
                    }
                };

                if (clickDelay > 0) {
                    setTimeout(performClick, clickDelay);
                } else {
                    performClick();
                }
            }
        } else if (key === 'Backspace') {
            // Handle backspace in input fields
            if (!keydownPrevented && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {
                const start = target.selectionStart;
                const end = target.selectionEnd;
                const value = target.value || '';

                if (start !== end) {
                    // Delete selection
                    target.value = value.substring(0, start) + value.substring(end);
                    target.selectionStart = target.selectionEnd = start;
                } else if (start > 0) {
                    // Delete character before cursor
                    target.value = value.substring(0, start - 1) + value.substring(start);
                    target.selectionStart = target.selectionEnd = start - 1;
                }

                // Trigger input event
                target.dispatchEvent(new Event('input', { bubbles: true }));
            } else if (!keydownPrevented && target.contentEditable === 'true') {
                document.execCommand('delete', false);
            }
        } else if (key === 'Delete') {
            // Handle delete key
            if (!keydownPrevented && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {
                const start = target.selectionStart;
                const end = target.selectionEnd;
                const value = target.value || '';

                if (start !== end) {
                    // Delete selection
                    target.value = value.substring(0, start) + value.substring(end);
                    target.selectionStart = target.selectionEnd = start;
                } else if (start < value.length) {
                    // Delete character after cursor
                    target.value = value.substring(0, start) + value.substring(start + 1);
                    target.selectionStart = target.selectionEnd = start;
                }

                // Trigger input event
                target.dispatchEvent(new Event('input', { bubbles: true }));
            } else if (!keydownPrevented && target.contentEditable === 'true') {
                document.execCommand('forwardDelete', false);
            }
        } else if (key.length === 1 && !ctrlKey && !altKey && !metaKey) {
            // For printable characters, also dispatch keypress and input
            if (!keydownPrevented) {
                target.dispatchEvent(new KeyboardEvent('keypress', eventInit));

                // For input fields, manually insert the character
                if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA') {
                    const start = target.selectionStart;
                    const end = target.selectionEnd;
                    const value = target.value || '';

                    const newValue = value.substring(0, start) + key + value.substring(end);
                    target.value = newValue;
                    target.selectionStart = target.selectionEnd = start + 1;

                    // Trigger input event
                    target.dispatchEvent(new Event('input', { bubbles: true }));
                } else if (target.contentEditable === 'true') {
                    document.execCommand('insertText', false, key);
                }
            }
        }

        // Dispatch keyup event
        target.dispatchEvent(new KeyboardEvent('keyup', eventInit));

        // Prepare return value
        const returnValue = {
            ok: true,
            target: target.tagName.toLowerCase(),
            key: key
        };

        // Include verbose message if set (for Enter key on links/buttons)
        if (window.__ZEN_CONTROL_OPENING_MESSAGE__) {
            returnValue.message = window.__ZEN_CONTROL_OPENING_MESSAGE__;
            delete window.__ZEN_CONTROL_OPENING_MESSAGE__;
        }

        // Include "opened" message if set (after click)
        if (window.__ZEN_CONTROL_OPENED_MESSAGE__) {
            returnValue.openedMessage = window.__ZEN_CONTROL_OPENED_MESSAGE__;
            delete window.__ZEN_CONTROL_OPENED_MESSAGE__;
        }

        // Include refocus message if set (from refocusHandler)
        if (window.__ZEN_CONTROL_REFOCUS_MESSAGE__) {
            returnValue.refocusMessage = window.__ZEN_CONTROL_REFOCUS_MESSAGE__;
            delete window.__ZEN_CONTROL_REFOCUS_MESSAGE__;
        }

        // Include accessible name and role if they were set (from Tab navigation)
        if (window.__ZEN_CONTROL_LAST_FOCUSED_NAME__) {
            returnValue.accessibleName = window.__ZEN_CONTROL_LAST_FOCUSED_NAME__;
            returnValue.role = window.__ZEN_CONTROL_LAST_FOCUSED_ROLE__;
            // Clear the values after returning them
            delete window.__ZEN_CONTROL_LAST_FOCUSED_NAME__;
            delete window.__ZEN_CONTROL_LAST_FOCUSED_ROLE__;
        }

        return returnValue;
    }

    return { ok: false, error: 'Invalid action' };
})()
