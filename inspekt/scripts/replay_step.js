// Replay a single recorded step
// Receives STEP_DATA_PLACEHOLDER with step details
(function() {
    const step = STEP_DATA_PLACEHOLDER;

    // ==================== UTILITY FUNCTIONS ====================

    /**
     * Find element using piercing selector (for Shadow DOM).
     * Format: "hostSelector >>> innerSelector"
     */
    function findWithPiercingSelector(piercingSelector) {
        const parts = piercingSelector.split(' >>> ');
        if (parts.length < 2) {
            return null;
        }

        let current = document.querySelector(parts[0]);
        if (!current) return null;

        for (let i = 1; i < parts.length; i++) {
            if (!current.shadowRoot) {
                // Shadow root not accessible (closed or doesn't exist)
                return null;
            }
            current = current.shadowRoot.querySelector(parts[i]);
            if (!current) return null;
        }

        return current;
    }

    /**
     * Find element in Shadow DOM using host selector and inner selector.
     */
    function findInShadowDOM(hostSelector, innerSelector) {
        const host = document.querySelector(hostSelector);
        if (!host || !host.shadowRoot) {
            return null;
        }
        return host.shadowRoot.querySelector(innerSelector);
    }

    /**
     * Recursively search for element through all Shadow DOM boundaries.
     * This is a fallback when piercing selector fails.
     */
    function findElementRecursive(selector, root = document) {
        // Try in current root first
        try {
            const element = root.querySelector(selector);
            if (element) return element;
        } catch (e) {
            // Invalid selector
        }

        // Search in all Shadow roots
        const allElements = root.querySelectorAll('*');
        for (const el of allElements) {
            if (el.shadowRoot) {
                const found = findElementRecursive(selector, el.shadowRoot);
                if (found) return found;
            }
        }

        return null;
    }

    /**
     * Find an element using primary selector and fallbacks.
     * Supports Shadow DOM via piercing_selector and shadow_host fields.
     * Returns { element, usedSelector, error }
     */
    function findElement(target) {
        if (!target || !target.selector) {
            return { element: null, usedSelector: null, error: 'No selector provided' };
        }

        // 1. Try piercing selector first (for Shadow DOM elements)
        if (target.piercing_selector) {
            const element = findWithPiercingSelector(target.piercing_selector);
            if (element) {
                return { element, usedSelector: target.piercing_selector, error: null };
            }
        }

        // 2. Try shadow_host + selector combination
        if (target.shadow_host) {
            const element = findInShadowDOM(target.shadow_host, target.selector);
            if (element) {
                return { element, usedSelector: `${target.shadow_host} >>> ${target.selector}`, error: null };
            }
        }

        // 3. Try primary selector in light DOM
        try {
            const element = document.querySelector(target.selector);
            if (element) {
                return { element, usedSelector: target.selector, error: null };
            }
        } catch (e) {
            // Invalid selector, try fallbacks
        }

        // 4. Try fallback selectors in light DOM
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

        // 5. Try recursive Shadow DOM search with primary selector
        const shadowElement = findElementRecursive(target.selector);
        if (shadowElement) {
            return { element: shadowElement, usedSelector: `[shadow-search]${target.selector}`, error: null };
        }

        // 6. Try finding by accessible name if provided (including Shadow DOM)
        if (target.accessible_name && target.tag) {
            // Search light DOM
            const candidates = document.querySelectorAll(target.tag);
            for (const el of candidates) {
                const name = computeAccessibleName(el);
                if (name === target.accessible_name) {
                    return { element: el, usedSelector: `[accessible-name="${target.accessible_name}"]`, error: null };
                }
            }
            // Search Shadow DOM recursively for matching tag + accessible name
            const shadowCandidate = findElementByAccessibleName(target.tag, target.accessible_name);
            if (shadowCandidate) {
                return { element: shadowCandidate, usedSelector: `[shadow-accessible-name="${target.accessible_name}"]`, error: null };
            }
        }

        // 7. Try finding by text content if provided
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
     * Find element by tag and accessible name, searching through Shadow DOM.
     */
    function findElementByAccessibleName(tag, accessibleName, root = document) {
        // Search in current root
        const candidates = root.querySelectorAll(tag);
        for (const el of candidates) {
            const name = computeAccessibleName(el);
            if (name === accessibleName) {
                return el;
            }
        }

        // Search in Shadow roots
        const allElements = root.querySelectorAll('*');
        for (const el of allElements) {
            if (el.shadowRoot) {
                const found = findElementByAccessibleName(tag, accessibleName, el.shadowRoot);
                if (found) return found;
            }
        }

        return null;
    }

    /**
     * Calculate click coordinates within an element.
     * Uses click_at: [x%, y%] for position, falls back to center.
     */
    function getClickCoordinates(element, clickAt) {
        const rect = element.getBoundingClientRect();

        if (clickAt && Array.isArray(clickAt) && clickAt.length >= 2) {
            return {
                x: rect.left + (rect.width * clickAt[0] / 100),
                y: rect.top + (rect.height * clickAt[1] / 100)
            };
        }

        // Default to center of element
        return {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2
        };
    }

    /**
     * Check if an element is effectively hidden (not perceivable).
     * Per ACCNAME 1.2: hidden elements should not contribute to accessible name
     * unless referenced by aria-labelledby.
     */
    function isEffectivelyHidden(el) {
        if (!el || el.nodeType !== 1) return true;
        if (el.hidden) return true;
        if (el.getAttribute('aria-hidden') === 'true') return true;

        const style = window.getComputedStyle(el);
        return style.display === 'none' ||
               style.visibility === 'hidden';
    }

    /**
     * Get text content from CSS pseudo-elements (::before, ::after).
     * Per ACCNAME 1.2: pseudo-element content should be included.
     */
    function getPseudoElementText(el) {
        if (!el || el.nodeType !== 1) return '';

        let text = '';

        try {
            const beforeContent = window.getComputedStyle(el, '::before').content;
            if (beforeContent && beforeContent !== 'none' && beforeContent !== 'normal') {
                const beforeText = beforeContent.replace(/^["']|["']$/g, '');
                if (beforeText) text += beforeText + ' ';
            }

            const afterContent = window.getComputedStyle(el, '::after').content;
            if (afterContent && afterContent !== 'none' && afterContent !== 'normal') {
                const afterText = afterContent.replace(/^["']|["']$/g, '');
                if (afterText) text += ' ' + afterText;
            }
        } catch (e) {
            // getComputedStyle may fail in some edge cases
        }

        return text.trim();
    }

    /**
     * Compute accessible name for matching elements.
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

        // For img/area: alt attribute
        if (['img', 'area'].includes(tagName)) {
            const alt = el.getAttribute('alt');
            if (alt) return alt;
        }

        // For input type="image": alt attribute
        if (tagName === 'input' && el.type === 'image') {
            const alt = el.getAttribute('alt');
            if (alt) return alt;
        }

        // For SVG: <title> child element
        if (tagName === 'svg') {
            const titleEl = el.querySelector('title');
            if (titleEl) return titleEl.textContent.trim();
        }

        // For buttons/links: compute name from content (handles img alt, svg title, etc.)
        if (['button', 'a'].includes(tagName)) {
            const name = computeAccessibleNameFromContent(el);
            if (name && name.length < 200) return name;
        }

        const title = el.getAttribute('title');
        if (title) return title.trim();

        return '';
    }

    /**
     * Recursively compute accessible name from element content.
     * Per ACCNAME 1.2: includes pseudo-element content and embedded control values.
     */
    function computeAccessibleNameFromContent(el) {
        if (!el) return '';
        const parts = [];

        // Include ::before pseudo-element content
        const beforeContent = window.getComputedStyle(el, '::before').content;
        if (beforeContent && beforeContent !== 'none' && beforeContent !== 'normal') {
            const beforeStr = beforeContent.replace(/^["']|["']$/g, '');
            if (beforeStr) parts.push(beforeStr);
        }

        for (const child of el.childNodes) {
            if (child.nodeType === Node.TEXT_NODE) {
                const text = child.textContent.trim();
                if (text) parts.push(text);
            } else if (child.nodeType === Node.ELEMENT_NODE) {
                const childTag = child.tagName.toLowerCase();

                // Skip hidden elements (using comprehensive check)
                if (isEffectivelyHidden(child)) continue;

                const childAriaLabel = child.getAttribute('aria-label');
                if (childAriaLabel && childAriaLabel.trim()) {
                    parts.push(childAriaLabel.trim());
                    continue;
                }

                if (['img', 'area'].includes(childTag)) {
                    const alt = child.getAttribute('alt');
                    if (alt) parts.push(alt);
                    continue;
                }

                if (childTag === 'svg') {
                    const titleEl = child.querySelector('title');
                    if (titleEl) {
                        parts.push(titleEl.textContent.trim());
                        continue;
                    }
                }

                // input type="image" - use alt
                if (childTag === 'input' && child.type === 'image') {
                    const alt = child.getAttribute('alt');
                    if (alt) parts.push(alt);
                    continue;
                }

                // Embedded form controls - use their value per ACCNAME 1.2
                if (childTag === 'input' && !['hidden', 'image'].includes(child.type)) {
                    const value = child.value;
                    if (value) parts.push(value);
                    continue;
                }

                if (childTag === 'select') {
                    const selectedOption = child.options[child.selectedIndex];
                    if (selectedOption) {
                        parts.push(selectedOption.text);
                    }
                    continue;
                }

                if (childTag === 'textarea') {
                    const value = child.value;
                    if (value) parts.push(value);
                    continue;
                }

                const childName = computeAccessibleNameFromContent(child);
                if (childName) parts.push(childName);
            }
        }

        // Include ::after pseudo-element content
        const afterContent = window.getComputedStyle(el, '::after').content;
        if (afterContent && afterContent !== 'none' && afterContent !== 'normal') {
            const afterStr = afterContent.replace(/^["']|["']$/g, '');
            if (afterStr) parts.push(afterStr);
        }

        return parts.join(' ').trim();
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
     * Check if clicking an element might cause page navigation.
     * Returns true for links that would navigate within the same tab.
     */
    function mightCauseNavigation(element) {
        // Walk up the DOM to find any ancestor link
        let el = element;
        while (el && el !== document.body) {
            if (el.tagName === 'A') {
                const href = el.getAttribute('href');
                const target = el.getAttribute('target');

                // Skip if no href or javascript: href
                if (!href || href.startsWith('javascript:')) {
                    return false;
                }

                // Skip if target opens in new tab/window
                if (target === '_blank' || target === '_new') {
                    return false;
                }

                // Skip anchor-only links (same page)
                if (href.startsWith('#')) {
                    return false;
                }

                // This link would likely cause navigation
                return true;
            }
            el = el.parentElement;
        }

        // Also check for form submit buttons
        if (element.tagName === 'BUTTON' || (element.tagName === 'INPUT' && element.type === 'submit')) {
            const form = element.closest('form');
            if (form && !form.target) {
                // Form submission without target usually causes navigation
                return true;
            }
        }

        return false;
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
     * Check if an element is a native control input with closed Shadow DOM.
     */
    function isNativeControlInput(element) {
        if (!element || element.tagName !== 'INPUT') return false;
        const type = (element.type || '').toLowerCase();
        return ['range', 'date', 'time', 'datetime-local', 'month', 'week', 'number', 'color'].includes(type);
    }

    /**
     * Type text into an element.
     * For native control inputs (range, date, etc.), sets the value directly.
     */
    function simulateType(element, value) {
        // Focus the element
        if (element.focus) {
            element.focus();
        }

        // Special handling for native control inputs (range, date, time, color, etc.)
        // These inputs use closed Shadow DOM, so we set the value directly via the API
        // rather than typing character by character.
        if (isNativeControlInput(element)) {
            element.value = value;
            element.dispatchEvent(new Event('input', { bubbles: true }));
            element.dispatchEvent(new Event('change', { bubbles: true }));
            return { ok: true, nativeControl: true };
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
     * Get all focusable elements on the page in tab order.
     */
    function getFocusableElements() {
        const selector = [
            'a[href]',
            'button:not([disabled])',
            'input:not([disabled]):not([type="hidden"])',
            'select:not([disabled])',
            'textarea:not([disabled])',
            '[tabindex]:not([tabindex="-1"])',
            '[contenteditable="true"]',
            'audio[controls]',
            'video[controls]'
        ].join(', ');

        const elements = Array.from(document.querySelectorAll(selector));

        // Filter out hidden elements and sort by tabindex
        return elements.filter(el => {
            // Check if visible
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') {
                return false;
            }
            // Check if element or ancestor is hidden
            if (el.offsetParent === null && style.position !== 'fixed') {
                return false;
            }
            return true;
        }).sort((a, b) => {
            const tabA = parseInt(a.getAttribute('tabindex') || '0', 10);
            const tabB = parseInt(b.getAttribute('tabindex') || '0', 10);
            // Positive tabindex comes first, then 0/no tabindex in DOM order
            if (tabA > 0 && tabB > 0) return tabA - tabB;
            if (tabA > 0) return -1;
            if (tabB > 0) return 1;
            return 0; // Keep DOM order for tabindex=0 or no tabindex
        });
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

        // Special handling for Tab key - manually move focus since synthetic events
        // don't trigger browser default focus navigation
        if (key === 'Tab') {
            const focusable = getFocusableElements();
            if (focusable.length > 0) {
                const currentIndex = focusable.indexOf(activeElement);
                let nextIndex;

                if (mods.includes('shift')) {
                    // Shift+Tab: go backwards
                    nextIndex = currentIndex <= 0 ? focusable.length - 1 : currentIndex - 1;
                } else {
                    // Tab: go forwards
                    nextIndex = currentIndex >= focusable.length - 1 ? 0 : currentIndex + 1;
                }

                const nextElement = focusable[nextIndex];
                if (nextElement) {
                    nextElement.focus();
                }
            }
        }

        // Special handling for Enter key
        if (key === 'Enter') {
            // Check if we're in a form and should submit
            const form = activeElement.closest('form');
            if (form && activeElement.tagName !== 'TEXTAREA') {
                // Don't auto-submit, just dispatch the event
            }
        }

        // Special handling for media elements (audio/video)
        // Native media controls use closed Shadow DOM, so synthetic keyboard events
        // don't trigger browser default behaviors. We use the HTMLMediaElement API directly.
        const isMediaElement = activeElement.tagName === 'AUDIO' || activeElement.tagName === 'VIDEO';

        if (isMediaElement) {
            // Space or Enter toggles play/pause
            if (key === ' ' || key === 'Space' || key === 'Enter') {
                if (activeElement.paused) {
                    activeElement.play().catch(() => {}); // Ignore autoplay restrictions
                } else {
                    activeElement.pause();
                }
                activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));
                return { ok: true, mediaAction: activeElement.paused ? 'paused' : 'playing' };
            }

            // Arrow keys for seek/volume
            if (key === 'ArrowLeft') {
                activeElement.currentTime = Math.max(0, activeElement.currentTime - 5);
                activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));
                return { ok: true, mediaAction: 'seek-back' };
            }
            if (key === 'ArrowRight') {
                activeElement.currentTime = Math.min(activeElement.duration || Infinity, activeElement.currentTime + 5);
                activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));
                return { ok: true, mediaAction: 'seek-forward' };
            }
            if (key === 'ArrowUp') {
                activeElement.volume = Math.min(1, activeElement.volume + 0.1);
                activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));
                return { ok: true, mediaAction: 'volume-up' };
            }
            if (key === 'ArrowDown') {
                activeElement.volume = Math.max(0, activeElement.volume - 0.1);
                activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));
                return { ok: true, mediaAction: 'volume-down' };
            }

            // 'M' for mute toggle (common shortcut)
            if (key === 'm' || key === 'M') {
                activeElement.muted = !activeElement.muted;
                activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));
                return { ok: true, mediaAction: activeElement.muted ? 'muted' : 'unmuted' };
            }
        }

        activeElement.dispatchEvent(new KeyboardEvent('keyup', eventInit));

        return { ok: true };
    }

    /**
     * Simulate a right click (context menu) on an element.
     */
    function simulateRightClick(element, position) {
        // Focus the element first
        if (element.focus) {
            element.focus();
        }

        const rect = element.getBoundingClientRect();
        const x = position ? position.x : rect.left + rect.width / 2;
        const y = position ? position.y : rect.top + rect.height / 2;

        // Create and dispatch mouse events for right click
        const eventInit = {
            bubbles: true,
            cancelable: true,
            view: window,
            button: 2,  // Right mouse button
            buttons: 2,
            clientX: x,
            clientY: y,
            screenX: x,
            screenY: y
        };

        element.dispatchEvent(new MouseEvent('mousedown', eventInit));
        element.dispatchEvent(new MouseEvent('mouseup', eventInit));
        element.dispatchEvent(new MouseEvent('contextmenu', eventInit));

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
     * Simulate keyboard activation (Enter key) on an element.
     * This is what happens when you press Enter/Space on a focused element.
     */
    function simulateActivate(element) {
        // Focus the element first
        if (element.focus) {
            element.focus();
        }

        // Dispatch Enter key events
        const eventInit = {
            key: 'Enter',
            code: 'Enter',
            bubbles: true,
            cancelable: true
        };

        element.dispatchEvent(new KeyboardEvent('keydown', eventInit));
        element.dispatchEvent(new KeyboardEvent('keypress', eventInit));
        element.dispatchEvent(new KeyboardEvent('keyup', eventInit));

        // Also dispatch a click event (keyboard activation triggers click)
        // Use detail=0 to indicate keyboard activation
        const rect = element.getBoundingClientRect();
        element.dispatchEvent(new MouseEvent('click', {
            bubbles: true,
            cancelable: true,
            view: window,
            detail: 0,  // 0 indicates keyboard activation
            clientX: rect.left + rect.width / 2,
            clientY: rect.top + rect.height / 2
        }));

        return { ok: true };
    }

    /**
     * Simulate checking a checkbox or radio button.
     */
    function simulateCheck(element) {
        // Focus the element
        if (element.focus) {
            element.focus();
        }

        // Set checked state
        element.checked = true;

        // Dispatch events
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));

        return { ok: true };
    }

    /**
     * Simulate unchecking a checkbox.
     */
    function simulateUncheck(element) {
        // Focus the element
        if (element.focus) {
            element.focus();
        }

        // Set checked state
        element.checked = false;

        // Dispatch events
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));

        return { ok: true };
    }

    /**
     * Simulate selecting an option in a select element.
     * Shows a visual preview of the selection being made.
     *
     * @param {HTMLSelectElement} element - The select element
     * @param {string|string[]} value - The value(s) to select
     * @param {string} optionText - The display text of the option being selected
     */
    function simulateSelect(element, value, optionText) {
        // Focus the element
        if (element.focus) {
            element.focus();
        }

        // Show visual preview of what's being selected
        if (window.__INSPEKT_VISUAL__ && optionText) {
            // Use the option text from recording, or fall back to finding it
            const displayText = optionText;
            window.__INSPEKT_VISUAL__.showSelectPreview(element, displayText, 600);
        } else if (window.__INSPEKT_VISUAL__ && !Array.isArray(value)) {
            // Fall back to finding option text by value
            const option = Array.from(element.options).find(opt => opt.value === value);
            if (option) {
                window.__INSPEKT_VISUAL__.showSelectPreview(element, option.text, 600);
            }
        }

        // Handle multi-select
        if (element.multiple && Array.isArray(value)) {
            // Deselect all first
            for (const option of element.options) {
                option.selected = false;
            }
            // Select the specified values
            for (const option of element.options) {
                if (value.includes(option.value)) {
                    option.selected = true;
                }
            }
        } else {
            // Single select
            element.value = value;
        }

        // Dispatch events
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));

        return { ok: true };
    }

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
     * Run a single pass of assertions (no retry).
     * Returns { ok, failures } where failures is an array of failure messages.
     */
    function checkAssertions(expect, targetSelector) {
        const failures = [];

        if (!expect) {
            return { ok: true, failures: [] };
        }

        // Check visibility
        if (expect.visible) {
            try {
                const el = document.querySelector(expect.visible);
                if (!el) {
                    failures.push(`Expected element to be visible: ${expect.visible}`);
                } else if (!isElementVisible(el)) {
                    failures.push(`Element exists but is not visible: ${expect.visible}`);
                }
            } catch (e) {
                failures.push(`Invalid selector: ${expect.visible} (${e.message})`);
            }
        }

        // Check hidden
        if (expect.hidden) {
            const el = document.querySelector(expect.hidden);
            if (el && isElementVisible(el)) {
                failures.push(`Expected element to be hidden: ${expect.hidden}`);
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

            const searchText = expect.text_contains;
            const found = expect.ignore_case
                ? pageText.toLowerCase().includes(searchText.toLowerCase())
                : pageText.includes(searchText);
            if (!found) {
                failures.push(`Expected page to contain text: "${expect.text_contains}"`);
            }
        }

        // Check focused - verify the target element has focus
        if (expect.focused === true && targetSelector) {
            const targetEl = document.querySelector(targetSelector);
            if (targetEl && document.activeElement !== targetEl) {
                failures.push(`Expected element to be focused: ${targetSelector}`);
            }
        }

        // Check input value
        if (expect.value && expect.value_equals !== undefined) {
            const el = document.querySelector(expect.value);
            if (!el) {
                failures.push(`Cannot check value - element not found: ${expect.value}`);
            } else {
                const actualValue = el.value !== undefined ? el.value : el.textContent;
                if (actualValue !== expect.value_equals) {
                    failures.push(`Expected value "${expect.value_equals}", got "${actualValue}" for: ${expect.value}`);
                }
            }
        }

        // Check checkbox/radio is checked
        if (expect.checked) {
            const el = document.querySelector(expect.checked);
            if (!el) {
                failures.push(`Cannot check checked state - element not found: ${expect.checked}`);
            } else if (!el.checked) {
                failures.push(`Expected element to be checked: ${expect.checked}`);
            }
        }

        // Check checkbox/radio is unchecked
        if (expect.unchecked) {
            const el = document.querySelector(expect.unchecked);
            if (!el) {
                failures.push(`Cannot check unchecked state - element not found: ${expect.unchecked}`);
            } else if (el.checked) {
                failures.push(`Expected element to be unchecked: ${expect.unchecked}`);
            }
        }

        // Check element is disabled
        if (expect.disabled) {
            const el = document.querySelector(expect.disabled);
            if (!el) {
                failures.push(`Cannot check disabled state - element not found: ${expect.disabled}`);
            } else if (!el.disabled && el.getAttribute('aria-disabled') !== 'true') {
                failures.push(`Expected element to be disabled: ${expect.disabled}`);
            }
        }

        // Check element is enabled
        if (expect.enabled) {
            const el = document.querySelector(expect.enabled);
            if (!el) {
                failures.push(`Cannot check enabled state - element not found: ${expect.enabled}`);
            } else if (el.disabled || el.getAttribute('aria-disabled') === 'true') {
                failures.push(`Expected element to be enabled: ${expect.enabled}`);
            }
        }

        // Check element count
        if (expect.count) {
            const elements = document.querySelectorAll(expect.count);
            const actualCount = elements.length;

            if (expect.count_equals !== undefined && actualCount !== expect.count_equals) {
                failures.push(`Expected ${expect.count_equals} elements, found ${actualCount} for: ${expect.count}`);
            }
            if (expect.count_min !== undefined && actualCount < expect.count_min) {
                failures.push(`Expected at least ${expect.count_min} elements, found ${actualCount} for: ${expect.count}`);
            }
            if (expect.count_max !== undefined && actualCount > expect.count_max) {
                failures.push(`Expected at most ${expect.count_max} elements, found ${actualCount} for: ${expect.count}`);
            }
        }

        // Check empty (for console logs - handled externally by Python)
        // Check violations (for axe - handled externally by Python)

        return {
            ok: failures.length === 0,
            failures: failures
        };
    }

    /**
     * Run assertions with optional wait/retry logic.
     * If wait is specified, polls until assertions pass or timeout.
     */
    async function runAssertions(expect, targetSelector) {
        if (!expect) {
            return { ok: true, failures: [] };
        }

        const waitMs = expect.wait || 0;
        const retryMs = expect.retry || 100;

        // If no wait, just run once
        if (waitMs <= 0) {
            return checkAssertions(expect, targetSelector);
        }

        // Poll until success or timeout
        const startTime = Date.now();
        let lastResult = { ok: false, failures: [] };

        while (Date.now() - startTime < waitMs) {
            lastResult = checkAssertions(expect, targetSelector);
            if (lastResult.ok) {
                return lastResult;
            }
            // Wait before retrying
            await new Promise(resolve => setTimeout(resolve, retryMs));
        }

        // Final check after timeout
        lastResult = checkAssertions(expect, targetSelector);
        if (!lastResult.ok) {
            // Add timeout info to failure messages
            lastResult.failures = lastResult.failures.map(f =>
                `${f} (timed out after ${waitMs}ms)`
            );
        }
        return lastResult;
    }

    // ==================== VISUAL/AUDIO FEEDBACK ====================

    /**
     * Get the center position of an element for the visual indicator.
     */
    function getElementCenter(element) {
        const rect = element.getBoundingClientRect();
        return {
            x: rect.left + rect.width / 2 + window.scrollX,
            y: rect.top + rect.height / 2 + window.scrollY
        };
    }

    /**
     * Show visual feedback before an action (move indicator, set color).
     */
    async function showVisualBefore(action, element) {
        const visual = window.__INSPEKT_VISUAL__;
        if (!visual) return;

        if (element) {
            const pos = getElementCenter(element);
            visual.setColor(action);
            await visual.moveTo(pos.x, pos.y, true);
            await visual.fadeIn();
        }
    }

    /**
     * Show visual feedback after an action (pulse).
     */
    async function showVisualAfter(action, success) {
        const visual = window.__INSPEKT_VISUAL__;
        if (!visual) return;

        if (success) {
            await visual.pulse(action);
        } else {
            await visual.showError();
        }
        await visual.fadeOut();
    }

    /**
     * Show typing indicator.
     */
    function showTypingIndicator(element) {
        const visual = window.__INSPEKT_VISUAL__;
        if (visual && element) {
            visual.showTyping(element);
        }
    }

    /**
     * Hide typing indicator.
     */
    function hideTypingIndicator() {
        const visual = window.__INSPEKT_VISUAL__;
        if (visual) {
            visual.hideTyping();
        }
    }

    /**
     * Play audio for an action.
     */
    function playAudio(action) {
        const visual = window.__INSPEKT_VISUAL__;
        if (visual && visual.audio) {
            visual.audio.playForAction(action);
        }
    }

    /**
     * Play error audio.
     */
    function playErrorAudio() {
        const visual = window.__INSPEKT_VISUAL__;
        if (visual && visual.audio) {
            visual.audio.playError();
        }
    }

    // ==================== MAIN EXECUTION ====================

    // Wrap in async IIFE to support wait/retry in assertions
    return (async function() {
        const action = step.action;
        const result = { ok: false, action: action, error: null, failures: [], usedSelector: null };

        try {
            if (action === 'navigate') {
                // Navigate to URL
                const url = step.url;
                if (url && url !== location.href) {
                    playAudio(action);
                    window.location.href = url;
                    result.ok = true;
                    result.navigated = true;
                } else {
                    result.ok = true;
                    result.skipped = true;
                    result.message = 'Already at URL';
                }

            } else if (action === 'scroll') {
                // Scroll to position
                const scroll = step.scroll || {};
                const targetX = scroll.x !== undefined ? scroll.x : window.scrollX;
                const targetY = scroll.y !== undefined ? scroll.y : window.scrollY;

                playAudio(action);

                // Smooth scroll to position
                window.scrollTo({
                    left: targetX,
                    top: targetY,
                    behavior: 'smooth'
                });

                // Wait for scroll to complete (approximate based on distance)
                const distance = Math.abs(targetY - window.scrollY) + Math.abs(targetX - window.scrollX);
                const scrollDuration = Math.min(500, Math.max(150, distance / 3));
                await new Promise(resolve => setTimeout(resolve, scrollDuration));

                result.ok = true;
                result.scrolledTo = { x: targetX, y: targetY };

            } else if (action === 'click') {
                // cursor_target selector is now merged into target.fallback_selectors
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else if (element.type === 'file') {
                    // Skip click for file inputs - the following 'upload' action
                    // will inject the files programmatically without triggering the picker
                    result.ok = true;
                    result.skipped = 'file_input';
                } else {
                    // Check if this click might cause navigation BEFORE clicking
                    const mayNavigate = mightCauseNavigation(element);

                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);

                    // Calculate click position using click_at [x%, y%]
                    const clickCoords = getClickCoordinates(element, step.click_at);
                    simulateClick(element, clickCoords);

                    result.ok = true;
                    result.mayNavigate = mayNavigate;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'rightclick') {
                // cursor_target selector is now merged into target.fallback_selectors
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);

                    // Calculate click position using click_at [x%, y%]
                    const clickCoords = getClickCoordinates(element, step.click_at);
                    simulateRightClick(element, clickCoords);

                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'activate') {
                // Keyboard activation (Enter/Space on focused element)
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else if (element.type === 'file') {
                    // Skip activation for file inputs - the following 'upload' action
                    // will inject the files programmatically without triggering the picker
                    result.ok = true;
                    result.skipped = 'file_input';
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);
                    simulateActivate(element);
                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'type') {
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);

                    // Handle sensitive values (passwords were masked during recording)
                    let value = step.value || '';
                    if (step.sensitive && value.includes('\u2022')) {
                        result.error = 'Cannot replay masked password. Edit the recording to provide the actual value.';
                        playErrorAudio();
                        await showVisualAfter(action, false);
                    } else {
                        showTypingIndicator(element);
                        playAudio(action);
                        simulateType(element, value);
                        hideTypingIndicator();
                        result.ok = true;
                        await showVisualAfter(action, true);
                    }
                }

            } else if (action === 'set') {
                // Set value for native control inputs (range, date, time, color, etc.)
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);

                    // Set value directly (native controls use closed Shadow DOM)
                    element.value = step.value || '';
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));

                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'toggle') {
                // Toggle details/summary element
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);

                    // Find the details element (target is usually the summary)
                    const details = element.closest('details') || element;
                    if (details.tagName === 'DETAILS') {
                        // Set open state based on recorded value
                        const shouldBeOpen = step.value === 'open';
                        if (details.open !== shouldBeOpen) {
                            details.open = shouldBeOpen;
                            details.dispatchEvent(new Event('toggle', { bubbles: true }));
                        }
                    } else {
                        // If not a details element, just click it
                        element.click();
                    }

                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'dialog') {
                // Dialog open/close
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else if (element.tagName !== 'DIALOG') {
                    result.error = 'Target is not a dialog element';
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);

                    const dialogValue = step.value || '';
                    if (dialogValue === 'modal') {
                        if (!element.open) {
                            element.showModal();
                        }
                    } else if (dialogValue === 'modeless') {
                        if (!element.open) {
                            element.show();
                        }
                    } else if (dialogValue === 'close') {
                        if (element.open) {
                            element.close();
                        }
                    }

                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'jsdialog') {
                // JavaScript dialog (alert, confirm, prompt)
                // The dialog was already intercepted by CDP when the triggering action ran
                // This step waits for the overlay to finish (matching recorded duration)
                const dialogType = step.dialog_type || 'alert';
                const message = step.message || '';
                const recordedResult = step.result;
                const duration = step.duration || 1500;

                // Don't play audio - CDP interception already showed the overlay
                // Just wait for the recorded duration so the overlay stays visible
                // Add 300ms buffer for fade animation
                await new Promise(resolve => setTimeout(resolve, duration + 300));

                // Include dialog info in result for CLI output
                result.ok = true;
                result.dialogType = dialogType;
                result.message = message;
                result.dialogResult = recordedResult;

            } else if (action === 'upload') {
                // File upload - recreate files using DataTransfer API
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else if (element.type !== 'file') {
                    result.error = 'Target is not a file input';
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);

                    const fileInfos = step.files || [];
                    const dataTransfer = new DataTransfer();
                    let filesAdded = 0;

                    for (const fileInfo of fileInfos) {
                        let bytes = null;
                        let base64Data = null;

                        // Get content from either inline or external source
                        if (fileInfo.content) {
                            // Inline base64 content
                            base64Data = fileInfo.content.split(',')[1];
                        } else if (fileInfo.external_content) {
                            // Content loaded from external file by Python
                            base64Data = fileInfo.external_content.split(',')[1];
                        }

                        if (base64Data) {
                            // Decode base64 to bytes
                            const binary = atob(base64Data);
                            bytes = new Uint8Array(binary.length);
                            for (let i = 0; i < binary.length; i++) {
                                bytes[i] = binary.charCodeAt(i);
                            }

                            // Create File object
                            const file = new File([bytes], fileInfo.name, {
                                type: fileInfo.type || 'application/octet-stream',
                                lastModified: fileInfo.lastModified || Date.now()
                            });

                            dataTransfer.items.add(file);
                            filesAdded++;
                        } else {
                            console.warn(`Missing content for file: ${fileInfo.name}`);
                        }
                    }

                    if (filesAdded > 0) {
                        element.files = dataTransfer.files;
                        element.dispatchEvent(new Event('change', { bubbles: true }));
                        element.dispatchEvent(new Event('input', { bubbles: true }));
                        result.ok = true;
                    } else {
                        result.error = 'No files could be loaded';
                    }

                    await showVisualAfter(action, result.ok);
                }

            } else if (action === 'download') {
                // Download step - this is a marker for a download that occurred during recording
                // The actual download happened as a result of a previous action (like click)
                // Assertions are handled by Python replay.py, not here
                playAudio(action);

                const downloadInfo = step.download || {};
                const filename = downloadInfo.filename || 'unknown';
                const size = downloadInfo.size || 0;

                result.ok = true;
                result.message = `Download: ${filename} (${size} bytes)`;
                result.downloadInfo = downloadInfo;

            } else if (action === 'keypress') {
                // Keyboard actions: just play audio and execute, no visual indicator
                // (the browser's focus ring provides visual feedback for Tab)
                playAudio(action);
                simulateKeypress(step.key, step.modifiers);
                result.ok = true;

            } else if (action === 'hover') {
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    simulateHover(element);
                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'check') {
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);
                    simulateCheck(element);
                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'uncheck') {
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);
                    simulateUncheck(element);
                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'radio') {
                // Radio button selection (radios can only be checked, not unchecked directly)
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);
                    simulateCheck(element);  // Radio uses same check simulation as checkbox
                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'select') {
                const { element, usedSelector, error } = findElement(step.target);
                result.usedSelector = usedSelector;

                if (!element) {
                    result.error = error;
                    playErrorAudio();
                } else {
                    await scrollToElement(element);
                    await showVisualBefore(action, element);
                    playAudio(action);
                    simulateSelect(element, step.value, step.option_text);
                    result.ok = true;
                    await showVisualAfter(action, true);
                }

            } else if (action === 'inspekt') {
                // Inspekt commands are handled by the CLI, not JavaScript
                result.ok = true;
                result.inspektCommand = step.command;

            } else if (action === 'interactive_prompt') {
                // Interactive mode: show overlay and wait for user input
                const visual = window.__INSPEKT_VISUAL__;
                if (visual && visual.interactive) {
                    // Show the interactive overlay with step info
                    // Note: Assertion overlay from previous step may still be visible
                    visual.interactive.show(
                        step.currentStep,      // Step data for current step
                        step.previousStep,     // Step data for previous step (may be null)
                        step.stepNum,          // Current step number (1-based)
                        step.totalSteps        // Total number of steps
                    );

                    // Wait for user to press Enter, Space, or Escape
                    const choice = await visual.interactive.waitForInput();

                    // Only hide main overlay on cancel (otherwise show() updates it for next step)
                    if (choice === 'cancel') {
                        visual.interactive.hide();
                    }
                    // Always hide assertion overlay (next step may not have assertions)
                    if (visual.assertion) {
                        visual.assertion.hide();
                    }

                    result.ok = true;
                    result.choice = choice;  // 'next', 'skip', or 'cancel'
                } else {
                    // No visual module available, default to 'next'
                    result.ok = true;
                    result.choice = 'next';
                    result.warning = 'Interactive overlay not available';
                }

            } else {
                result.error = `Unknown action: ${action}`;
            }

            // Run assertions if step succeeded and has expectations (unless skipTests is set)
            if (result.ok && step.expect && !step.skipTests) {
                // Get visual module for assertion overlay (if available)
                const visual = window.__INSPEKT_VISUAL__;

                // In interactive mode, show "checking" overlay before evaluating
                // Wrap in try-catch so overlay errors don't break assertion evaluation
                if (step.isInteractive && visual?.assertion) {
                    try {
                        visual.assertion.showChecking(step.expect);
                    } catch (overlayErr) {
                        console.warn('Assertion overlay showChecking failed:', overlayErr);
                    }
                }

                // Pass target selector for focused check
                const targetSelector = step.target?.selector || null;
                const assertionResult = await runAssertions(step.expect, targetSelector);
                result.failures = assertionResult.failures;
                if (!assertionResult.ok) {
                    result.assertionsFailed = true;
                    playErrorAudio();
                }

                // In interactive mode, show result overlay (stays until next step)
                if (step.isInteractive && visual?.assertion) {
                    try {
                        visual.assertion.showResult(
                            step.expect,
                            assertionResult.ok,
                            assertionResult.failures
                        );
                    } catch (overlayErr) {
                        console.warn('Assertion overlay showResult failed:', overlayErr);
                    }
                }
            }

        } catch (e) {
            result.ok = false;
            result.error = `Exception: ${e.message}`;
        }

        return result;
    })();
})()
