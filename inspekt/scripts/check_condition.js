// Check a condition for skip_if/wait_for
// Receives CONDITION_DATA_PLACEHOLDER with condition details
(function() {
    const condition = CONDITION_DATA_PLACEHOLDER;

    /**
     * Check if an element is visible (not hidden by CSS).
     */
    function isElementVisible(el) {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        return style.display !== 'none' &&
               style.visibility !== 'hidden' &&
               style.opacity !== '0';
    }

    /**
     * Check a single condition.
     * Returns { met: boolean, reason: string }
     */
    function checkCondition(cond) {
        if (!cond) {
            return { met: false, reason: 'No condition specified' };
        }

        // Check visibility
        if (cond.visible) {
            const el = document.querySelector(cond.visible);
            if (el && isElementVisible(el)) {
                return { met: true, reason: `Element is visible: ${cond.visible}` };
            }
            return { met: false, reason: `Element not visible: ${cond.visible}` };
        }

        // Check hidden
        if (cond.hidden) {
            const el = document.querySelector(cond.hidden);
            if (!el || !isElementVisible(el)) {
                return { met: true, reason: `Element is hidden: ${cond.hidden}` };
            }
            return { met: false, reason: `Element is not hidden: ${cond.hidden}` };
        }

        // Check URL contains
        if (cond.url_contains) {
            if (location.href.includes(cond.url_contains)) {
                return { met: true, reason: `URL contains: ${cond.url_contains}` };
            }
            return { met: false, reason: `URL does not contain: ${cond.url_contains}` };
        }

        // Check text contains
        if (cond.text_contains) {
            // Get page text, excluding Inspekt overlay elements
            let pageText = '';
            const walker = document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT,
                {
                    acceptNode: (node) => {
                        // Skip text inside Inspekt overlays
                        let parent = node.parentElement;
                        while (parent) {
                            if (parent.id?.startsWith('inspekt-') || parent.classList?.contains('inspekt-overlay')) {
                                return NodeFilter.FILTER_REJECT;
                            }
                            parent = parent.parentElement;
                        }
                        return NodeFilter.FILTER_ACCEPT;
                    }
                }
            );
            while (walker.nextNode()) {
                pageText += walker.currentNode.textContent;
            }

            const searchText = cond.text_contains;
            const found = cond.ignore_case
                ? pageText.toLowerCase().includes(searchText.toLowerCase())
                : pageText.includes(searchText);
            if (found) {
                return { met: true, reason: `Page contains text: ${cond.text_contains}` };
            }
            return { met: false, reason: `Page does not contain text: ${cond.text_contains}` };
        }

        // Check checkbox/radio is checked
        if (cond.checked) {
            const el = document.querySelector(cond.checked);
            if (el && el.checked) {
                return { met: true, reason: `Element is checked: ${cond.checked}` };
            }
            return { met: false, reason: `Element is not checked: ${cond.checked}` };
        }

        // Check checkbox/radio is unchecked
        if (cond.unchecked) {
            const el = document.querySelector(cond.unchecked);
            if (!el || !el.checked) {
                return { met: true, reason: `Element is unchecked: ${cond.unchecked}` };
            }
            return { met: false, reason: `Element is checked: ${cond.unchecked}` };
        }

        // Check input value
        if (cond.value && cond.value_equals !== undefined) {
            const el = document.querySelector(cond.value);
            if (el) {
                const actualValue = el.value !== undefined ? el.value : el.textContent;
                if (actualValue === cond.value_equals) {
                    return { met: true, reason: `Value matches: ${cond.value}` };
                }
                return { met: false, reason: `Value "${actualValue}" does not match "${cond.value_equals}"` };
            }
            return { met: false, reason: `Element not found: ${cond.value}` };
        }

        return { met: false, reason: 'Unknown condition type' };
    }

    return checkCondition(condition);
})()
