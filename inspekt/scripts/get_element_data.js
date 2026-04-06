// Get element data for either inspected or focused element
(function() {
    const sourceType = 'SOURCE_TYPE_PLACEHOLDER'; // Replaced at runtime with 'inspected' or 'focused'

    /**
     * Helper: Get deep active element (Shadow DOM support)
     * When focus is inside a Shadow DOM, document.activeElement returns the host,
     * not the actual focused element. This function recursively drills down.
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
    let selectionSource;

    if (sourceType === 'inspected') {
        // Get inspected element from DevTools extension auto-storage
        // The Chrome extension's devtools.js stores the selected element in this global
        // when user clicks on an element in the Elements panel
        element = window.__INSPEKT_INSPECTED_ELEMENT__;

        selectionSource = window.__INSPEKT_SELECTION_SOURCE__ || 'devtools';
    } else if (sourceType === 'focused') {
        // Get currently focused element
        element = getDeepActiveElement();
        selectionSource = 'focus';
    }

    // Error handling: No element
    if (!element || element.nodeType !== 1) {
        if (sourceType === 'inspected') {
            return {
                error: 'No element selected yet',
                hint: 'Right-click an element and select "Inspect", or use the Inspekt DevTools panel'
            };
        } else {
            return {
                error: 'No element currently focused',
                hint: 'Press Tab to focus an interactive element, or click an input/button/link'
            };
        }
    }

    // Error handling: Body/HTML (only for focused)
    if (sourceType === 'focused' && ['BODY', 'HTML'].includes(element.tagName)) {
        return {
            error: 'No element currently focused',
            hint: 'Focus is on document body (no interactive element focused). Press Tab or click an input/button/link.'
        };
    }

    // Error handling: Iframe focus
    if (sourceType === 'focused' && element.tagName === 'IFRAME') {
        return {
            error: 'Focus is inside an iframe',
            hint: 'Cannot access focused element inside cross-origin iframes. Use browser DevTools to inspect iframe contents.'
        };
    }

    // Error handling: Removed element (handles detached/removed elements)
    if (!document.body.contains(element)) {
        if (sourceType === 'inspected') {
            return {
                error: 'Selected element has been removed from the page',
                hint: 'The element may have been removed by JavaScript (e.g., modal close, SPA navigation). Select a new element.'
            };
        } else {
            return {
                error: 'Focused element has been removed from the page',
                hint: 'The element was removed from DOM while focused. This can happen with dynamic content.'
            };
        }
    }

    // Get element information
    const rect = element.getBoundingClientRect();
    const styles = window.getComputedStyle(element);

    // Get CSS selector path
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

    // Get XPath for element
    function getXPath(el) {
        if (el.id) return `//*[@id="${el.id}"]`;
        if (el === document.body) return '/html/body';
        if (el === document.documentElement) return '/html';

        const parent = el.parentNode;
        if (!parent) return '';

        const siblings = Array.from(parent.children).filter(e => e.tagName === el.tagName);
        const index = siblings.indexOf(el) + 1;
        const tagName = el.tagName.toLowerCase();

        return getXPath(parent) + '/' + tagName + (siblings.length > 1 ? `[${index}]` : '');
    }

    // Get nesting depth from <html>
    function getNestingDepth(el) {
        let depth = 0;
        let current = el;
        while (current.parentElement) {
            depth++;
            current = current.parentElement;
        }
        return depth;
    }

    // Get attributes
    const attributes = {};
    for (let i = 0; i < element.attributes.length; i++) {
        const attr = element.attributes[i];
        attributes[attr.name] = attr.value;
    }

    // Get text content (full for API, truncated for display)
    const fullTextContent = (element.textContent || '').trim();
    let textContent = fullTextContent;
    if (textContent.length > 100) {
        textContent = textContent.substring(0, 100) + '...';
    }

    // Get full HTML content (outerHTML includes the element itself)
    const htmlContent = element.outerHTML;

    // Compute accessible name following ARIA specification
    // Based on: https://www.w3.org/TR/accname-1.2/
    function computeAccessibleName(el) {
        let name = '';
        let source = '';

        // Step 1: aria-labelledby (highest priority)
        const labelledBy = el.getAttribute('aria-labelledby');
        if (labelledBy) {
            const ids = labelledBy.trim().split(/\s+/);
            const labels = ids.map(id => {
                const labelEl = document.getElementById(id);
                return labelEl ? labelEl.textContent.trim() : '';
            }).filter(text => text);
            if (labels.length > 0) {
                name = labels.join(' ');
                source = 'aria-labelledby';
                return { name, source };
            }
        }

        // Step 2: aria-label
        const ariaLabel = el.getAttribute('aria-label');
        if (ariaLabel && ariaLabel.trim()) {
            name = ariaLabel.trim();
            source = 'aria-label';
            return { name, source };
        }

        // Step 3: Native labeling mechanisms
        const tagName = el.tagName.toLowerCase();

        // For form controls: associated <label> element
        if (['input', 'select', 'textarea'].includes(tagName) && el.id) {
            const label = document.querySelector(`label[for="${el.id}"]`);
            if (label) {
                name = label.textContent.trim();
                source = '<label for="..."> element';
                return { name, source };
            }
        }

        // For input type="button/submit/reset": value attribute
        if (tagName === 'input' && ['button', 'submit', 'reset'].includes(el.type)) {
            const value = el.getAttribute('value');
            if (value) {
                name = value;
                source = 'value attribute';
                return { name, source };
            }
        }

        // For input type="image": alt attribute
        if (tagName === 'input' && el.type === 'image') {
            const alt = el.getAttribute('alt');
            if (alt) {
                name = alt;
                source = 'alt attribute';
                return { name, source };
            }
        }

        // For img/area: alt attribute
        if (['img', 'area'].includes(tagName)) {
            const alt = el.getAttribute('alt');
            if (alt) {
                name = alt;
                source = 'alt attribute';
                return { name, source };
            } else {
                return { name: '', source: 'missing alt attribute' };
            }
        }

        // For buttons: content
        if (tagName === 'button') {
            name = el.textContent.trim();
            source = 'element content';
            return { name, source };
        }

        // For links: content
        if (tagName === 'a') {
            name = el.textContent.trim();
            source = 'link text content';
            return { name, source };
        }

        // Step 4: title attribute (fallback)
        const title = el.getAttribute('title');
        if (title && title.trim()) {
            name = title.trim();
            source = 'title attribute';
            return { name, source };
        }

        // Step 5: placeholder (for inputs, lowest priority)
        if (['input', 'textarea'].includes(tagName)) {
            const placeholder = el.getAttribute('placeholder');
            if (placeholder && placeholder.trim()) {
                name = placeholder.trim();
                source = 'placeholder attribute';
                return { name, source };
            }
        }

        // Step 6: For other elements, use text content if not empty
        const textContent = el.textContent.trim();
        if (textContent && textContent.length < 200) {
            name = textContent.substring(0, 100);
            source = 'text content';
            return { name, source };
        }

        return { name: '', source: 'none' };
    }

    const accessibleName = computeAccessibleName(element);

    // Get accessibility information
    const a11y = {
        role: element.getAttribute('role') || element.tagName.toLowerCase(),
        accessibleName: accessibleName.name,
        accessibleNameSource: accessibleName.source,
        ariaLabel: element.getAttribute('aria-label') || null,
        ariaDescribedBy: element.getAttribute('aria-describedby') || null,
        ariaLabelledBy: element.getAttribute('aria-labelledby') || null,
        ariaHidden: element.getAttribute('aria-hidden') || null,
        tabIndex: element.tabIndex !== -1 ? element.tabIndex : null,
        focusable: element.tabIndex >= 0 || ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(element.tagName),
        disabled: element.disabled || element.getAttribute('aria-disabled') === 'true',
        alt: element.getAttribute('alt') || null
    };

    // Get semantic information
    const semantic = {
        isInteractive: ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'DETAILS', 'SUMMARY'].includes(element.tagName),
        isFormElement: ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON', 'LABEL'].includes(element.tagName),
        isLandmark: ['HEADER', 'FOOTER', 'NAV', 'MAIN', 'ASIDE', 'SECTION', 'ARTICLE'].includes(element.tagName),
        hasClickHandler: element.onclick !== null || element.getAttribute('onclick') !== null
    };

    // Get computed styles (extended)
    const extendedStyles = {
        display: styles.display,
        position: styles.position,
        zIndex: styles.zIndex,
        opacity: styles.opacity,
        visibility: styles.visibility,
        backgroundColor: styles.backgroundColor,
        color: styles.color,
        fontSize: styles.fontSize,
        fontFamily: styles.fontFamily,
        fontWeight: styles.fontWeight,
        lineHeight: styles.lineHeight,
        margin: styles.margin,
        padding: styles.padding,
        border: styles.border,
        overflow: styles.overflow,
        cursor: styles.cursor
    };

    // Check visibility in detail
    const visibilityDetails = {
        hasSize: rect.width > 0 && rect.height > 0,
        displayNone: styles.display === 'none',
        visibilityHidden: styles.visibility === 'hidden',
        opacityZero: parseFloat(styles.opacity) === 0,
        offScreen: rect.top < -rect.height || rect.left < -rect.width,
        inViewport: rect.top < window.innerHeight && rect.bottom > 0 && rect.left < window.innerWidth && rect.right > 0
    };

    const fullyVisible = visibilityDetails.hasSize &&
                        !visibilityDetails.displayNone &&
                        !visibilityDetails.visibilityHidden &&
                        !visibilityDetails.opacityZero;

    return {
        ok: true,
        tag: element.tagName.toLowerCase(),
        id: element.id || null,
        classes: Array.from(element.classList),
        attributes: attributes,
        textContent: textContent,
        fullTextContent: fullTextContent,
        htmlContent: htmlContent,
        selector: getCSSPath(element),
        dimensions: {
            width: Math.round(rect.width),
            height: Math.round(rect.height),
            top: Math.round(rect.top),
            left: Math.round(rect.left),
            right: Math.round(rect.right),
            bottom: Math.round(rect.bottom)
        },
        styles: extendedStyles,
        visible: fullyVisible,
        visibilityDetails: visibilityDetails,
        accessibility: a11y,
        semantic: semantic,
        childCount: element.children.length,
        descendantCount: element.querySelectorAll('*').length,
        nestingDepth: getNestingDepth(element),
        xpath: getXPath(element),
        textLength: fullTextContent.length,
        attributeCount: element.attributes.length,
        parentTag: element.parentElement ? element.parentElement.tagName.toLowerCase() : null,
        selectionSource: selectionSource,
        selectionTimestamp: Date.now(),
        // Page metadata for file output
        pageTitle: document.title || '',
        pageLang: document.documentElement.lang || '',
        pageDomain: window.location.hostname || ''
    };
})()
