// Replay a single recorded step
// Receives STEP_DATA_PLACEHOLDER with step details
(function() {
    const step = STEP_DATA_PLACEHOLDER;

    // ==================== UTILITY FUNCTIONS ====================

    /**
     * Find an element using primary selector and fallbacks.
     * Returns { element, usedSelector, error }
     */
    function findElement(target) {
        if (!target || !target.selector) {
            return { element: null, usedSelector: null, error: 'No selector provided' };
        }

        // Try primary selector first
        try {
            const element = document.querySelector(target.selector);
            if (element) {
                return { element, usedSelector: target.selector, error: null };
            }
        } catch (e) {
            // Invalid selector, try fallbacks
        }

        // Try fallback selectors
        const fallbacks = target.fallback_selectors || [];
        for (const selector of fallbacks) {
            try {
                const element = document.querySelector(selector);
                if (element) {
                    return { element, usedSelector: selector, error: null };
                }
            } catch (e) {
                // Invalid selector, continue
            }
        }

        // Try finding by accessible name if provided
        if (target.accessible_name && target.tag) {
            const candidates = document.querySelectorAll(target.tag);
            for (const el of candidates) {
                const name = computeAccessibleName(el);
                if (name === target.accessible_name) {
                    return { element: el, usedSelector: `[accessible-name="${target.accessible_name}"]`, error: null };
                }
            }
        }

        // Try finding by text content if provided
        if (target.text && target.tag) {
            const candidates = document.querySelectorAll(target.tag);
            for (const el of candidates) {
                const text = (el.textContent || '').trim();
                if (text === target.text || text.startsWith(target.text)) {
                    return { element: el, usedSelector: `[text="${target.text}"]`, error: null };
                }
            }
        }

        return {
            element: null,
            usedSelector: null,
            error: `Element not found: ${target.selector}`
        };
    }

    /**
     * Compute accessible name (simplified version for matching).
     */
    function computeAccessibleName(el) {
        if (!el || el.nodeType !== 1) return '';

        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel) return ariaLabel.trim();

        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const ids = labelledBy.trim().split(/\s+/);
            const labels = ids.map(id => {
                const labelEl = document.getElementById(id);
                return labelEl ? labelEl.textContent.trim() : '';
            }).filter(text => text);
            if (labels.length) return labels.join(' ');
        }

        const tagName = el.tagName.toLowerCase();
        if (['input', 'select', 'textarea'].includes(tagName) && el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) return label.textContent.trim();
        }

        if (['button', 'a'].includes(tagName)) {
            return (el.textContent || '').trim().substring(0, 100);
        }

        const title = el.getAttribute('title');
        if (title) return title.trim();

        return '';
    }

    /**
     * Scroll element into view smoothly.
     */
    function scrollToElement(element) {
        element.scrollIntoView({
            behavior: 'instant',
            block: 'center',
            inline: 'center'
        });
        // Small delay for scroll to complete
        return new Promise(resolve => setTimeout(resolve, 100));
    }

    /**
     * Simulate a mouse click on an element.
     */
    function simulateClick(element, position) {
        // Focus the element first
        if (element.focus) {
            element.focus();
        }

        const rect = element.getBoundingClientRect();
        const x = position ? position.x : rect.left + rect.width / 2;
        const y = position ? position.y : rect.top + rect.height / 2;

        // Create and dispatch mouse events
        const eventInit = {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: x,
            clientY: y,
            screenX: x,
            screenY: y
        };

        element.dispatchEvent(new MouseEvent('mousedown', eventInit));
        element.dispatchEvent(new MouseEvent('mouseup', eventInit));
        element.dispatchEvent(new MouseEvent('click', eventInit));

        return { ok: true };
    }

    /**
     * Type text into an element.
     */
    function simulateType(element, value) {
        // Focus the element
        if (element.focus) {
            element.focus();
        }

        // Clear existing value if it's an input/textarea
        if ('value' in element) {
            element.value = '';
            element.dispatchEvent(new Event('input', { bubbles: true }));
        }

        // Type each character
        for (const char of value) {
            // Dispatch keydown
            element.dispatchEvent(new KeyboardEvent('keydown', {
                key: char,
                code: `Key${char.toUpperCase()}`,
                bubbles: true
            }));

            // Update value
            if ('value' in element) {
                element.value += char;
            } else if (element.isContentEditable) {
                element.textContent += char;
            }

            // Dispatch input event
            element.dispatchEvent(new InputEvent('input', {
                data: char,
                inputType: 'insertText',
                bubbles: true
            }));

            // Dispatch keyup
            element.dispatchEvent(new KeyboardEvent('keyup', {
                key: char,
                code: `Key${char.toUpperCase()}`,
                bubbles: true
            }));
        }

        // Dispatch change event at the end
        element.dispatchEvent(new Event('change', { bubbles: true }));

        return { ok: true };
    }

    /**
     * Simulate a keypress.
     */
    function simulateKeypress(key, modifiers) {
        const activeElement = document.activeElement || document.body;
        const mods = modifiers || [];

        const eventInit = {
            key: key,
            code: key.length === 1 ? `Key${key.toUpperCase()}` : key,
            bubbles: true,
            cancelable: true,
            ctrlKey: mods.includes('ctrl'),
            metaKey: mods.includes('meta'),
            altKey: mods.includes('alt'),
            shiftKey: mods.includes('shift')
        };

        activeElement.dispatchEvent(new KeyboardEvent('keydown', eventInit));

        // Special handling for Tab key
        if (key === 'Tab') {
            // Let the browser handle Tab navigation
            // We just dispatch the event, browser will move focus
        }

        // Special handling for Enter key
        if (key === 'Enter') {
            // Check if we're in a form and should submit
            const form = activeElement.closest('form');
            if (form && activeElement.tagName !== 'TEXTAREA') {
                // Don't auto-submit, just dispatch the event
            }
        }

        activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));

        return { ok: true };
    }

    /**
     * Simulate a hover on an element.
     */
    function simulateHover(element) {
        const rect = element.getBoundingClientRect();
        const x = rect.left + rect.width / 2;
        const y = rect.top + rect.height / 2;

        const eventInit = {
            bubbles: true,
            cancelable: true,
            view: window,
            clientX: x,
            clientY: y
        };

        element.dispatchEvent(new MouseEvent('mouseenter', eventInit));
        element.dispatchEvent(new MouseEvent('mouseover', eventInit));

        return { ok: true };
    }

    /**
     * Run assertions on the current page state.
     */
    function runAssertions(expect) {
        const failures = [];

        if (!expect) {
            return { ok: true, failures: [] };
        }

        // Check visibility
        if (expect.visible) {
            const el = document.querySelector(expect.visible);
            if (!el) {
                failures.push(`Expected element to be visible: ${expect.visible}`);
            } else {
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                    failures.push(`Element exists but is not visible: ${expect.visible}`);
                }
            }
        }

        // Check hidden
        if (expect.hidden) {
            const el = document.querySelector(expect.hidden);
            if (el) {
                const style = window.getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0') {
                    failures.push(`Expected element to be hidden: ${expect.hidden}`);
                }
            }
        }

        // Check URL contains
        if (expect.url_contains) {
            if (!location.href.includes(expect.url_contains)) {
                failures.push(`Expected URL to contain "${expect.url_contains}", got "${location.href}"`);
            }
        }

        // Check text contains
        if (expect.text_contains) {
            if (!document.body.textContent.includes(expect.text_contains)) {
                failures.push(`Expected page to contain text: "${expect.text_contains}"`);
            }
        }

        // Check focused
        if (expect.focused === true) {
            // The element that was just interacted with should be focused
            // This is checked by the caller
        }

        // Check empty (for console logs - handled externally)
        // Check violations (for axe - handled externally)

        return {
            ok: failures.length === 0,
            failures: failures
        };
    }

    // ==================== MAIN EXECUTION ====================

    const action = step.action;
    const result = { ok: false, action: action, error: null, failures: [], usedSelector: null };

    try {
        if (action === 'navigate') {
            // Navigate to URL
            const url = step.url;
            if (url && url !== location.href) {
                window.location.href = url;
                result.ok = true;
                result.navigated = true;
            } else {
                result.ok = true;
                result.skipped = true;
                result.message = 'Already at URL';
            }

        } else if (action === 'click') {
            const { element, usedSelector, error } = findElement(step.target);
            result.usedSelector = usedSelector;

            if (!element) {
                result.error = error;
            } else {
                scrollToElement(element);
                simulateClick(element, step.position);
                result.ok = true;
            }

        } else if (action === 'type') {
            const { element, usedSelector, error } = findElement(step.target);
            result.usedSelector = usedSelector;

            if (!element) {
                result.error = error;
            } else {
                scrollToElement(element);

                // Handle sensitive values (passwords were masked during recording)
                let value = step.value || '';
                if (step.sensitive && value.includes('\u2022')) {
                    result.error = 'Cannot replay masked password. Edit the recording to provide the actual value.';
                } else {
                    simulateType(element, value);
                    result.ok = true;
                }
            }

        } else if (action === 'keypress') {
            simulateKeypress(step.key, step.modifiers);
            result.ok = true;

        } else if (action === 'hover') {
            const { element, usedSelector, error } = findElement(step.target);
            result.usedSelector = usedSelector;

            if (!element) {
                result.error = error;
            } else {
                scrollToElement(element);
                simulateHover(element);
                result.ok = true;
            }

        } else if (action === 'inspekt') {
            // Inspekt commands are handled by the CLI, not JavaScript
            result.ok = true;
            result.inspektCommand = step.command;

        } else {
            result.error = `Unknown action: ${action}`;
        }

        // Run assertions if step succeeded and has expectations
        if (result.ok && step.expect) {
            const assertionResult = runAssertions(step.expect);
            result.failures = assertionResult.failures;
            if (!assertionResult.ok) {
                result.assertionsFailed = true;
            }
        }

    } catch (e) {
        result.error = `Exception: ${e.message}`;
    }

    return result;
})()
