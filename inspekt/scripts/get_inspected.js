// Get the currently inspected element from DevTools
(function() {
    // First, try to get from our stored variable
    let element = window.__INSPEKT_INSPECTED_ELEMENT__;

    // If not found, try calling the injected function that attempts to access $0
    if (!element && typeof window.__inspektGetInspectedElement === 'function') {
        element = window.__inspektGetInspectedElement();
        // If we got an element, store it
        if (element && element.nodeType === 1) {
            window.__INSPEKT_INSPECTED_ELEMENT__ = element;
        }
    }

    if (!element || element.nodeType !== 1) {
        return {
            error: 'No element selected yet',
            hint: 'Right-click an element and select "Inspect", or use the Inspekt DevTools panel'
        };
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

    // Get attributes
    const attributes = {};
    for (let i = 0; i < element.attributes.length; i++) {
        const attr = element.attributes[i];
        attributes[attr.name] = attr.value;
    }

    // Get text content (truncated)
    let textContent = element.textContent || '';
    textContent = textContent.trim();
    if (textContent.length > 100) {
        textContent = textContent.substring(0, 100) + '...';
    }

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
        parentTag: element.parentElement ? element.parentElement.tagName.toLowerCase() : null,
        selectionSource: window.__INSPEKT_SELECTION_SOURCE__ || 'unknown',
        selectionTimestamp: window.__INSPEKT_SELECTION_TIME__ || null
    };
})()
