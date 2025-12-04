// Record browser events for later replay
// Uses ACTION_PLACEHOLDER pattern: 'start', 'poll', 'stop'
(function() {
    const action = 'ACTION_PLACEHOLDER';
    const config = CONFIG_PLACEHOLDER;

    // ==================== UTILITY FUNCTIONS ====================

    /**
     * Generate CSS selector path for an element.
     * Stops at element with ID for shorter, more stable selectors.
     */
    function getCSSPath(el) {
        if (!(el instanceof Element)) return '';

        const path = [];
        while (el.nodeType === Node.ELEMENT_NODE) {
            let selector = el.nodeName.toLowerCase();

            if (el.id) {
                selector += '#' + CSS.escape(el.id);
                path.unshift(selector);
                break;
            } else {
                let sibling = el;
                let nth = 1;
                while (sibling.previousElementSibling) {
                    sibling = sibling.previousElementSibling;
                    if (sibling.nodeName.toLowerCase() === selector) nth++;
                }
                if (nth !== 1) selector += ':nth-of-type(' + nth + ')';
            }

            path.unshift(selector);
            el = el.parentNode;
        }

        return path.join(' > ');
    }

    /**
     * Generate multiple selectors for an element, ordered by reliability.
     */
    function generateSelectors(element) {
        const selectors = [];

        // 1. ID selector (highest priority)
        if (element.id) {
            selectors.push('#' + CSS.escape(element.id));
        }

        // 2. data-testid variants (common in React/Vue/testing)
        const testIdAttrs = ['data-testid', 'data-test-id', 'data-cy', 'data-test'];
        for (const attr of testIdAttrs) {
            const value = element.getAttribute(attr);
            if (value) {
                selectors.push(`[${attr}="${CSS.escape(value)}"]`);
                break; // Only add one test ID selector
            }
        }

        // 3. aria-label (good for accessibility-focused selectors)
        const ariaLabel = element.getAttribute('aria-label');
        if (ariaLabel) {
            selectors.push(`[aria-label="${CSS.escape(ariaLabel)}"]`);
        }

        // 4. name attribute (for form elements)
        const name = element.getAttribute('name');
        if (name) {
            selectors.push(`${element.tagName.toLowerCase()}[name="${CSS.escape(name)}"]`);
        }

        // 5. Type-specific selectors
        const tag = element.tagName.toLowerCase();
        if (tag === 'input' && element.type) {
            const type = element.type;
            if (element.placeholder) {
                selectors.push(`input[type="${type}"][placeholder="${CSS.escape(element.placeholder)}"]`);
            }
        }

        // 6. Unique text content for buttons/links
        if (['button', 'a'].includes(tag)) {
            const text = (element.textContent || '').trim();
            if (text && text.length < 50 && !text.includes('\n')) {
                // Can't use text in CSS, but it's useful for fallback strategies
            }
        }

        // 7. CSS path (always include as final fallback)
        const cssPath = getCSSPath(element);
        if (cssPath && !selectors.includes(cssPath)) {
            selectors.push(cssPath);
        }

        // Ensure we have at least one selector
        if (selectors.length === 0) {
            selectors.push(cssPath || tag);
        }

        return selectors;
    }

    /**
     * Compute the accessible name for an element following ARIA specification.
     */
    function computeAccessibleName(el) {
        if (!el || el.nodeType !== 1) return '';

        // aria-labelledby (highest priority)
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

        // aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.trim()) {
            return ariaLabel.trim();
        }

        const tagName = el.tagName.toLowerCase();

        // For form controls: associated <label> element
        if (['input', 'select', 'textarea'].includes(tagName) && el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) {
                return label.textContent.trim();
            }
        }

        // For input type="button/submit/reset": value attribute
        if (tagName === 'input' && ['button', 'submit', 'reset'].includes(el.type)) {
            const value = el.getAttribute('value');
            if (value) return value;
        }

        // For img/area: alt attribute
        if (['img', 'area'].includes(tagName)) {
            const alt = el.getAttribute('alt');
            if (alt) return alt;
        }

        // For buttons/links: content
        if (['button', 'a'].includes(tagName)) {
            const text = el.textContent.trim();
            if (text && text.length < 100) return text;
        }

        // title attribute
        const title = el.getAttribute('title');
        if (title && title.trim()) {
            return title.trim();
        }

        // placeholder (for inputs)
        if (['input', 'textarea'].includes(tagName)) {
            const placeholder = el.getAttribute('placeholder');
            if (placeholder && placeholder.trim()) {
                return placeholder.trim();
            }
        }

        return '';
    }

    /**
     * Check if an element is interactive (for hover filtering).
     */
    function isInteractiveElement(element) {
        const interactiveTags = ['a', 'button', 'input', 'select', 'textarea', 'details', 'summary'];
        const tag = element.tagName.toLowerCase();

        if (interactiveTags.includes(tag)) return true;

        // Check for interactive roles
        const role = element.getAttribute('role');
        const interactiveRoles = ['button', 'link', 'menuitem', 'tab', 'checkbox', 'radio', 'option', 'switch'];
        if (role && interactiveRoles.includes(role)) return true;

        // Check for click handlers or tabindex
        if (element.getAttribute('onclick') || element.getAttribute('tabindex') !== null) return true;

        // Check for cursor: pointer style
        const style = window.getComputedStyle(element);
        if (style.cursor === 'pointer') return true;

        return false;
    }

    /**
     * Get target information for an element.
     */
    function getTargetInfo(element) {
        const selectors = generateSelectors(element);
        const text = (element.textContent || '').trim().substring(0, 100);

        return {
            selector: selectors[0],
            fallback_selectors: selectors.slice(1, 4), // Keep up to 3 fallbacks
            text: text || null,
            accessible_name: computeAccessibleName(element) || null,
            tag: element.tagName.toLowerCase(),
            role: element.getAttribute('role') || null
        };
    }

    /**
     * Get the current timestamp relative to recording start.
     */
    function getTimestamp() {
        return Date.now() - window.__INSPEKT_RECORD_START__;
    }

    // ==================== EVENT HANDLERS ====================

    // Click deduplication state - prevents recording both pointerdown and click
    let lastClickRecord = {
        element: null,
        timestamp: 0
    };

    const CLICK_DEDUP_THRESHOLD = 500; // ms - ignore duplicate clicks within this window

    function recordClick(element, event, source) {
        const timestamp = getTimestamp();

        // Check for duplicate (same element within threshold)
        if (lastClickRecord.element === element &&
            (timestamp - lastClickRecord.timestamp) < CLICK_DEDUP_THRESHOLD) {
            return; // Skip duplicate
        }

        // Update dedup state
        lastClickRecord = { element, timestamp };

        window.__INSPEKT_RECORD_EVENTS__.push({
            action: 'click',
            timestamp: timestamp,
            target: getTargetInfo(element),
            position: {
                x: Math.round(event.clientX),
                y: Math.round(event.clientY),
                viewport_relative: true
            }
        });
    }

    function handleClick(event) {
        // Primary button only (left click)
        if (event.button !== 0) return;
        recordClick(event.target, event, 'click');
    }

    function handlePointerDown(event) {
        // Primary button only (left click/touch)
        if (event.button !== 0) return;
        // Only record if it's a pointer type that might not fire click
        // (some frameworks use pointerdown and call preventDefault)
        recordClick(event.target, event, 'pointerdown');
    }

    function handleMouseDown(event) {
        // Primary button only
        if (event.button !== 0) return;
        // Fallback for older browsers or when pointer events aren't available
        recordClick(event.target, event, 'mousedown');
    }

    // Track typing in input fields
    let typingState = {
        element: null,
        startValue: '',
        startTime: 0,
        lastTime: 0
    };

    function flushTypingBuffer() {
        if (!typingState.element) return;

        const currentValue = typingState.element.value || typingState.element.textContent || '';

        // Only record if value actually changed
        if (currentValue !== typingState.startValue) {
            const isPassword = typingState.element.type === 'password';
            const config = window.__INSPEKT_RECORD_CONFIG__ || {};

            window.__INSPEKT_RECORD_EVENTS__.push({
                action: 'type',
                timestamp: typingState.startTime,
                target: getTargetInfo(typingState.element),
                value: (isPassword && config.maskPasswords !== false) ? '\u2022'.repeat(8) : currentValue,
                sensitive: isPassword
            });
        }

        typingState = { element: null, startValue: '', startTime: 0, lastTime: 0 };
    }

    function handleInput(event) {
        const element = event.target;
        const now = getTimestamp();

        // Check if this is a new element or enough time has passed
        if (typingState.element !== element) {
            // Flush previous typing
            flushTypingBuffer();

            // Start new buffer
            typingState = {
                element: element,
                startValue: '', // Will capture final value
                startTime: now,
                lastTime: now
            };
        } else {
            typingState.lastTime = now;
        }
    }

    function handleKeyDown(event) {
        const now = getTimestamp();

        // Check if this is a special key
        const isSpecialKey = event.key === 'Enter' || event.key === 'Tab' ||
                            event.key === 'Escape' || event.key.startsWith('Arrow') ||
                            event.key === 'Backspace' || event.key === 'Delete' ||
                            event.key === 'Home' || event.key === 'End' ||
                            event.key === 'PageUp' || event.key === 'PageDown' ||
                            event.ctrlKey || event.metaKey || event.altKey;

        if (isSpecialKey) {
            // Flush any pending typing first
            flushTypingBuffer();

            // Build modifiers array
            const modifiers = [];
            if (event.ctrlKey) modifiers.push('ctrl');
            if (event.metaKey) modifiers.push('meta');
            if (event.altKey) modifiers.push('alt');
            if (event.shiftKey) modifiers.push('shift');

            // Don't record lone modifier key presses
            if (['Control', 'Meta', 'Alt', 'Shift'].includes(event.key)) {
                return;
            }

            window.__INSPEKT_RECORD_EVENTS__.push({
                action: 'keypress',
                timestamp: now,
                key: event.key,
                modifiers: modifiers
            });
        }
    }

    // Hover tracking state
    let hoverState = {
        element: null,
        enterTime: 0,
        timeout: null
    };

    function handleMouseEnter(event) {
        const element = event.target;
        const config = window.__INSPEKT_RECORD_CONFIG__ || {};

        // Only track hover on interactive elements
        if (!config.includeHover || !isInteractiveElement(element)) {
            return;
        }

        // Clear any pending hover
        if (hoverState.timeout) {
            clearTimeout(hoverState.timeout);
        }

        hoverState = {
            element: element,
            enterTime: getTimestamp(),
            timeout: null
        };
    }

    function handleMouseLeave(event) {
        const element = event.target;
        const config = window.__INSPEKT_RECORD_CONFIG__ || {};
        const minDuration = config.minHoverDuration || 200;

        if (hoverState.element !== element) {
            return;
        }

        const duration = getTimestamp() - hoverState.enterTime;

        // Only record if hover lasted long enough
        if (duration >= minDuration) {
            window.__INSPEKT_RECORD_EVENTS__.push({
                action: 'hover',
                timestamp: hoverState.enterTime,
                target: getTargetInfo(element),
                position: null // Hover doesn't need precise position
            });
        }

        hoverState = { element: null, enterTime: 0, timeout: null };
    }

    // Navigation tracking
    let lastUrl = '';

    function handleNavigation() {
        const currentUrl = location.href;
        if (currentUrl !== lastUrl) {
            window.__INSPEKT_RECORD_EVENTS__.push({
                action: 'navigate',
                timestamp: getTimestamp(),
                url: currentUrl
            });
            lastUrl = currentUrl;
        }
    }

    // ==================== ACTION HANDLERS ====================

    if (action === 'start') {
        // Check if already recording
        if (window.__INSPEKT_RECORD_ACTIVE__) {
            return { ok: true, message: 'Recording already active' };
        }

        // Initialize state
        window.__INSPEKT_RECORD_ACTIVE__ = true;
        window.__INSPEKT_RECORD_START__ = Date.now();
        window.__INSPEKT_RECORD_EVENTS__ = [];
        window.__INSPEKT_RECORD_INDEX__ = 0;
        window.__INSPEKT_RECORD_CONFIG__ = config || {};

        // Store initial URL
        lastUrl = location.href;

        // Record initial navigation
        window.__INSPEKT_RECORD_EVENTS__.push({
            action: 'navigate',
            timestamp: 0,
            url: location.href
        });

        // Attach event listeners
        // Use capture phase (true) to catch events before stopPropagation
        document.addEventListener('click', handleClick, true);
        document.addEventListener('pointerdown', handlePointerDown, true);
        document.addEventListener('mousedown', handleMouseDown, true);
        document.addEventListener('input', handleInput, true);
        document.addEventListener('keydown', handleKeyDown, true);
        document.addEventListener('mouseenter', handleMouseEnter, true);
        document.addEventListener('mouseleave', handleMouseLeave, true);
        window.addEventListener('popstate', handleNavigation);
        window.addEventListener('hashchange', handleNavigation);

        // Store handlers for cleanup
        window.__INSPEKT_RECORD_HANDLERS__ = {
            click: handleClick,
            pointerdown: handlePointerDown,
            mousedown: handleMouseDown,
            input: handleInput,
            keydown: handleKeyDown,
            mouseenter: handleMouseEnter,
            mouseleave: handleMouseLeave,
            popstate: handleNavigation,
            hashchange: handleNavigation
        };

        // Intercept pushState/replaceState for SPA navigation
        const originalPushState = history.pushState;
        const originalReplaceState = history.replaceState;

        history.pushState = function(...args) {
            originalPushState.apply(this, args);
            handleNavigation();
        };

        history.replaceState = function(...args) {
            originalReplaceState.apply(this, args);
            handleNavigation();
        };

        window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__ = originalPushState;
        window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__ = originalReplaceState;

        // Flush typing buffer periodically
        window.__INSPEKT_RECORD_FLUSH_INTERVAL__ = setInterval(() => {
            if (typingState.element && (getTimestamp() - typingState.lastTime) > 500) {
                flushTypingBuffer();
            }
        }, 500);

        return {
            ok: true,
            message: 'Recording started',
            startUrl: location.href,
            startTime: window.__INSPEKT_RECORD_START__,
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            },
            zoom: window.devicePixelRatio || 1,
            userAgent: navigator.userAgent
        };

    } else if (action === 'poll') {
        // Flush any pending typing
        if (typingState.element && (getTimestamp() - typingState.lastTime) > 300) {
            flushTypingBuffer();
        }

        // Get new events since last poll
        const allEvents = window.__INSPEKT_RECORD_EVENTS__ || [];
        const lastIndex = window.__INSPEKT_RECORD_INDEX__ || 0;
        const newEvents = allEvents.slice(lastIndex);

        // Update index
        window.__INSPEKT_RECORD_INDEX__ = allEvents.length;

        return {
            ok: true,
            events: newEvents,
            hasEvents: newEvents.length > 0,
            totalEvents: allEvents.length
        };

    } else if (action === 'stop') {
        // Flush any remaining typing
        flushTypingBuffer();

        // Remove event listeners
        const handlers = window.__INSPEKT_RECORD_HANDLERS__ || {};
        if (handlers.click) document.removeEventListener('click', handlers.click, true);
        if (handlers.pointerdown) document.removeEventListener('pointerdown', handlers.pointerdown, true);
        if (handlers.mousedown) document.removeEventListener('mousedown', handlers.mousedown, true);
        if (handlers.input) document.removeEventListener('input', handlers.input, true);
        if (handlers.keydown) document.removeEventListener('keydown', handlers.keydown, true);
        if (handlers.mouseenter) document.removeEventListener('mouseenter', handlers.mouseenter, true);
        if (handlers.mouseleave) document.removeEventListener('mouseleave', handlers.mouseleave, true);
        if (handlers.popstate) window.removeEventListener('popstate', handlers.popstate);
        if (handlers.hashchange) window.removeEventListener('hashchange', handlers.hashchange);

        // Restore history methods
        if (window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__) {
            history.pushState = window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__;
        }
        if (window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__) {
            history.replaceState = window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__;
        }

        // Clear interval
        if (window.__INSPEKT_RECORD_FLUSH_INTERVAL__) {
            clearInterval(window.__INSPEKT_RECORD_FLUSH_INTERVAL__);
        }

        // Collect final events
        const allEvents = window.__INSPEKT_RECORD_EVENTS__ || [];
        const startTime = window.__INSPEKT_RECORD_START__ || Date.now();
        const duration = Date.now() - startTime;

        // Cleanup
        delete window.__INSPEKT_RECORD_ACTIVE__;
        delete window.__INSPEKT_RECORD_START__;
        delete window.__INSPEKT_RECORD_EVENTS__;
        delete window.__INSPEKT_RECORD_INDEX__;
        delete window.__INSPEKT_RECORD_CONFIG__;
        delete window.__INSPEKT_RECORD_HANDLERS__;
        delete window.__INSPEKT_RECORD_ORIGINAL_PUSH_STATE__;
        delete window.__INSPEKT_RECORD_ORIGINAL_REPLACE_STATE__;
        delete window.__INSPEKT_RECORD_FLUSH_INTERVAL__;

        return {
            ok: true,
            message: 'Recording stopped',
            events: allEvents,
            totalEvents: allEvents.length,
            duration: duration
        };
    }

    return { ok: false, error: 'Invalid action: ' + action };
})()
