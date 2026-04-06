// Get event handlers from inspected or focused element (and its descendants)
(function() {
    const sourceType = 'SOURCE_TYPE_PLACEHOLDER'; // Replaced at runtime with 'inspected' or 'focused'

    /**
     * Helper: Get deep active element (Shadow DOM support)
     */
    function getDeepActiveElement() {
        let active = document.activeElement;
        while (active && active.shadowRoot && active.shadowRoot.activeElement) {
            active = active.shadowRoot.activeElement;
        }
        return active;
    }

    // Get element based on source type
    let element;

    if (sourceType === 'inspected') {
        element = window.__INSPEKT_INSPECTED_ELEMENT__;
    } else if (sourceType === 'focused') {
        element = getDeepActiveElement();
    }

    // Error handling: No element
    if (!element || element.nodeType !== 1) {
        if (sourceType === 'inspected') {
            return {
                ok: false,
                error: 'No element selected yet',
                hint: 'Right-click an element and select "Inspect", or use the Inspekt DevTools panel'
            };
        } else {
            return {
                ok: false,
                error: 'No element currently focused',
                hint: 'Press Tab to focus an interactive element, or click an input/button/link'
            };
        }
    }

    // Error handling: Body/HTML (only for focused)
    if (sourceType === 'focused' && ['BODY', 'HTML'].includes(element.tagName)) {
        return {
            ok: false,
            error: 'No element currently focused',
            hint: 'Focus is on document body. Press Tab or click an input/button/link.'
        };
    }

    // Error handling: Removed element
    if (!document.body.contains(element)) {
        return {
            ok: false,
            error: 'Selected element has been removed from the page',
            hint: 'The element may have been removed by JavaScript. Select a new element.'
        };
    }

    // Event handler attribute names to check
    const eventAttributes = [
        'onclick', 'ondblclick', 'onmousedown', 'onmouseup', 'onmouseover', 'onmouseout',
        'onmousemove', 'onmouseenter', 'onmouseleave', 'oncontextmenu',
        'onkeydown', 'onkeyup', 'onkeypress',
        'onfocus', 'onblur', 'onfocusin', 'onfocusout',
        'onchange', 'oninput', 'onsubmit', 'onreset', 'onselect',
        'onload', 'onerror', 'onscroll', 'onresize',
        'ondrag', 'ondragstart', 'ondragend', 'ondragover', 'ondragenter', 'ondragleave', 'ondrop',
        'ontouchstart', 'ontouchend', 'ontouchmove', 'ontouchcancel',
        'onpointerdown', 'onpointerup', 'onpointermove', 'onpointerover', 'onpointerout',
        'onpointerenter', 'onpointerleave', 'onpointercancel',
        'onwheel', 'onanimationstart', 'onanimationend', 'onanimationiteration',
        'ontransitionstart', 'ontransitionend', 'ontransitionrun', 'ontransitioncancel'
    ];

    /**
     * Get a minimal CSS selector for an element
     */
    function getMinimalSelector(el) {
        if (el.id) {
            return `${el.tagName.toLowerCase()}#${CSS.escape(el.id)}`;
        }
        if (el.className && typeof el.className === 'string') {
            const classes = el.className.trim().split(/\s+/).slice(0, 2).join('.');
            if (classes) {
                return `${el.tagName.toLowerCase()}.${classes}`;
            }
        }
        return el.tagName.toLowerCase();
    }

    /**
     * Get a truncated HTML snippet for an element
     */
    function getHtmlSnippet(el, maxLength = 100) {
        const outerHTML = el.outerHTML || '';
        if (outerHTML.length <= maxLength) {
            return outerHTML;
        }
        // Try to get opening tag only
        const match = outerHTML.match(/^<[^>]+>/);
        if (match && match[0].length <= maxLength) {
            return match[0];
        }
        return outerHTML.substring(0, maxLength) + '...';
    }

    /**
     * Extract event handlers from a single element
     */
    function extractHandlersFromElement(el) {
        const handlers = [];

        for (const attrName of eventAttributes) {
            // Check for HTML attribute (e.g., onclick="...")
            const attrValue = el.getAttribute(attrName);
            if (attrValue) {
                handlers.push({
                    selector: getMinimalSelector(el),
                    type: attrName.replace(/^on/, ''),  // 'click' instead of 'onclick'
                    source: 'attribute',
                    code: attrValue,
                    element: getHtmlSnippet(el)
                });
            }

            // Check for JS property (e.g., element.onclick = ...)
            // Only if different from attribute (to avoid duplicates)
            const propName = attrName;
            if (el[propName] && typeof el[propName] === 'function') {
                // Check if it's from the attribute or set programmatically
                const funcString = el[propName].toString();
                // Attribute handlers have specific patterns
                const isFromAttribute = funcString.includes('return ') && funcString.includes('.call(this');

                if (!isFromAttribute && !attrValue) {
                    handlers.push({
                        selector: getMinimalSelector(el),
                        type: attrName.replace(/^on/, ''),
                        source: 'property',
                        code: funcString.length > 200 ? funcString.substring(0, 200) + '...' : funcString,
                        element: getHtmlSnippet(el)
                    });
                }
            }
        }

        // Check for data-action attributes (common in Stimulus.js)
        const dataAction = el.getAttribute('data-action');
        if (dataAction) {
            handlers.push({
                selector: getMinimalSelector(el),
                type: 'data-action',
                source: 'framework',
                code: dataAction,
                element: getHtmlSnippet(el),
                framework: 'Stimulus'
            });
        }

        // Check for v-on:* attributes (Vue.js)
        for (const attr of el.attributes) {
            if (attr.name.startsWith('v-on:') || attr.name.startsWith('@')) {
                const eventType = attr.name.replace(/^(v-on:|@)/, '');
                handlers.push({
                    selector: getMinimalSelector(el),
                    type: eventType,
                    source: 'framework',
                    code: attr.value,
                    element: getHtmlSnippet(el),
                    framework: 'Vue'
                });
            }
        }

        // Check for ng-click, ng-* attributes (AngularJS)
        for (const attr of el.attributes) {
            if (attr.name.startsWith('ng-') && attr.name !== 'ng-class' && attr.name !== 'ng-style') {
                const eventType = attr.name.replace(/^ng-/, '');
                if (['click', 'change', 'blur', 'focus', 'submit', 'keydown', 'keyup', 'keypress'].includes(eventType)) {
                    handlers.push({
                        selector: getMinimalSelector(el),
                        type: eventType,
                        source: 'framework',
                        code: attr.value,
                        element: getHtmlSnippet(el),
                        framework: 'AngularJS'
                    });
                }
            }
        }

        return handlers;
    }

    // Collect handlers from element and all descendants
    const allHandlers = [];

    // Start with the root element
    const rootHandlers = extractHandlersFromElement(element);
    allHandlers.push(...rootHandlers);

    // Traverse descendants
    const descendants = element.querySelectorAll('*');
    for (const descendant of descendants) {
        const handlers = extractHandlersFromElement(descendant);
        allHandlers.push(...handlers);
    }

    // Build summary by event type
    const summary = {};
    for (const handler of allHandlers) {
        const type = handler.type;
        summary[type] = (summary[type] || 0) + 1;
    }

    // Get element info for display
    const elementInfo = {
        tag: element.tagName.toLowerCase(),
        id: element.id || null,
        selector: getMinimalSelector(element),
        descendantCount: descendants.length
    };

    return {
        ok: true,
        element: elementInfo,
        handlers: allHandlers,
        summary: summary,
        totalCount: allHandlers.length,
        source: sourceType
    };
})()
