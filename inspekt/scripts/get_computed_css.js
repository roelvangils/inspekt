/**
 * Extract computed CSS styles from inspected element and all children
 *
 * Returns a tree structure with element info and computed styles.
 * Supports filtering to common properties and excluding browser defaults.
 *
 * Placeholders:
 * - OPTIONS_PLACEHOLDER: { allProperties: boolean, includeDefaults: boolean, roundPixels: boolean }
 */

(function() {
    const options = OPTIONS_PLACEHOLDER;

    // Common CSS properties to include by default (when allProperties is false)
    // NOTE: We only include LONGHAND properties here. Shorthands like 'margin', 'padding',
    // 'border', 'flex', 'grid' etc. are NOT included because:
    // 1. getComputedStyle iteration only yields longhands
    // 2. The iframe defaults only contain longhands
    // 3. Lightning CSS will merge longhands into shorthands in the final output
    const COMMON_PROPERTIES = [
        // Layout
        'display', 'position', 'top', 'right', 'bottom', 'left', 'z-index',
        'width', 'height', 'min-width', 'max-width', 'min-height', 'max-height',
        'margin-top', 'margin-right', 'margin-bottom', 'margin-left',
        'padding-top', 'padding-right', 'padding-bottom', 'padding-left',
        'float', 'clear', 'overflow-x', 'overflow-y',

        // Flexbox (longhands only)
        'flex-direction', 'flex-wrap', 'flex-grow', 'flex-shrink', 'flex-basis',
        'justify-content', 'align-items', 'align-self', 'align-content',
        'row-gap', 'column-gap',
        'order',

        // Grid (longhands only)
        'grid-template-columns', 'grid-template-rows', 'grid-template-areas',
        'grid-column-start', 'grid-column-end', 'grid-row-start', 'grid-row-end',
        'grid-auto-columns', 'grid-auto-rows', 'grid-auto-flow',

        // Typography (longhands only)
        'font-family', 'font-size', 'font-weight', 'font-style', 'font-variant',
        'line-height', 'letter-spacing', 'word-spacing', 'text-align', 'text-decoration-line',
        'text-decoration-style', 'text-decoration-color', 'text-decoration-thickness',
        'text-transform', 'text-indent', 'white-space', 'word-wrap', 'word-break',
        'color',

        // Background (longhands only)
        'background-color', 'background-image', 'background-position-x', 'background-position-y',
        'background-size', 'background-repeat', 'background-attachment', 'background-clip',

        // Border (longhands only)
        'border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width',
        'border-top-style', 'border-right-style', 'border-bottom-style', 'border-left-style',
        'border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color',
        'border-top-left-radius', 'border-top-right-radius',
        'border-bottom-left-radius', 'border-bottom-right-radius',

        // Effects
        'box-shadow', 'text-shadow', 'opacity', 'visibility',
        'transform', 'transform-origin',
        'filter', 'backdrop-filter',

        // Transition/Animation longhands
        'transition-property', 'transition-duration', 'transition-timing-function', 'transition-delay',
        'animation-name', 'animation-duration', 'animation-timing-function', 'animation-delay',
        'animation-iteration-count', 'animation-direction', 'animation-fill-mode', 'animation-play-state',

        // Box model
        'box-sizing',
        'outline-width', 'outline-style', 'outline-color', 'outline-offset',

        // List (longhands only)
        'list-style-type', 'list-style-position', 'list-style-image',

        // Table
        'border-collapse', 'border-spacing', 'table-layout', 'vertical-align',

        // Misc
        'cursor', 'pointer-events', 'user-select', 'content'
    ];

    // Cache for default styles per tag
    const defaultStylesCache = {};

    /**
     * CSS properties that are inherited from parent to child.
     * If a child has the same value as its parent for these properties,
     * the declaration is redundant and can be stripped.
     */
    const INHERITED_PROPERTIES = new Set([
        // Typography
        'color',
        'font-family', 'font-size', 'font-style', 'font-variant', 'font-weight',
        'letter-spacing', 'line-height', 'word-spacing',
        'text-align', 'text-indent', 'text-transform',
        'text-decoration-color',  // Note: text-decoration itself is NOT inherited
        'white-space', 'word-break', 'word-wrap', 'overflow-wrap', 'hyphens',
        // List
        'list-style-type', 'list-style-position', 'list-style-image',
        // Table
        'border-collapse', 'border-spacing',
        // Cursor & visibility
        'cursor', 'visibility',
        // Direction
        'direction', 'writing-mode', 'text-orientation',
        // Quotes
        'quotes',
        // Other
        'orphans', 'widows',
        'tab-size',
    ]);

    /**
     * Known default values for CSS properties.
     * These patterns are always considered "default" regardless of computed comparison.
     * Values can be strings (exact match) or RegExp (pattern match).
     */
    const KNOWN_DEFAULTS = {
        // Grid defaults
        'grid': [/^none\s*\/\s*none\s*\/\s*none\s*\/\s*row\s*\/\s*auto\s*\/\s*auto$/, 'none'],
        'grid-template': ['none', /^none\s*\/\s*none$/],
        'grid-template-columns': ['none'],
        'grid-template-rows': ['none'],
        'grid-template-areas': ['none'],
        'grid-auto-columns': ['auto'],
        'grid-auto-rows': ['auto'],
        'grid-auto-flow': ['row'],
        'grid-column': ['auto', 'auto / auto'],
        'grid-row': ['auto', 'auto / auto'],
        'grid-area': ['auto', /^auto\s*\/\s*auto\s*\/\s*auto\s*\/\s*auto$/],
        'grid-gap': ['normal', 'normal normal'],
        'row-gap': ['normal'],
        'column-gap': ['normal'],
        'gap': ['normal', 'normal normal'],

        // Flex defaults
        'flex': ['0 auto', '0 1 auto'],
        'flex-grow': ['0'],
        'flex-shrink': ['1'],
        'flex-basis': ['auto'],
        'flex-direction': ['row'],
        'flex-wrap': ['nowrap'],
        'flex-flow': ['row', 'row nowrap'],

        // Place/align defaults
        'place-content': ['normal', 'normal normal'],
        'place-items': ['normal', 'normal normal'],
        'place-self': ['auto', 'auto auto'],
        'align-content': ['normal'],
        'align-items': ['normal'],
        'align-self': ['auto'],
        'justify-content': ['normal'],
        'justify-items': ['normal'],
        'justify-self': ['auto'],

        // Position defaults
        'position': ['static'],
        'top': ['auto'],
        'right': ['auto'],
        'bottom': ['auto'],
        'left': ['auto'],
        'inset': ['auto', /^auto\s+auto\s+auto\s+auto$/],
        'z-index': ['auto'],

        // Box model defaults
        'width': ['auto'],
        'height': ['auto'],
        'min-width': ['auto', '0px', '0'],
        'min-height': ['auto', '0px', '0'],
        'max-width': ['none'],
        'max-height': ['none'],

        // Display defaults
        'display': ['inline'],  // Default for most elements, but often overridden
        'visibility': ['visible'],
        'opacity': ['1'],
        'overflow': ['visible'],
        'overflow-x': ['visible'],
        'overflow-y': ['visible'],

        // Text defaults
        'text-align': ['start', 'left'],  // 'start' is spec default, 'left' for LTR
        'white-space': ['normal'],
        'word-break': ['normal'],
        'word-wrap': ['normal'],
        'overflow-wrap': ['normal'],
        'text-indent': ['0px', '0'],
        'text-transform': ['none'],
        'letter-spacing': ['normal'],
        'word-spacing': ['normal'],

        // Border defaults (after normalization, all zeros become 0)
        'border-spacing': ['0px', '0', '0px 0px', '0 0'],
        'border-collapse': ['separate'],

        // Background defaults
        'background': [/^rgba?\(0,\s*0,\s*0,\s*0\)/, 'transparent', 'none'],
        'background-color': [/^rgba?\(0,\s*0,\s*0,\s*0\)/, 'transparent'],
        'background-image': ['none'],
        'background-position': ['0% 0%', '0px 0px'],
        'background-size': ['auto', 'auto auto'],
        'background-repeat': ['repeat'],
        'background-attachment': ['scroll'],
        'background-clip': ['border-box'],
        'background-origin': ['padding-box'],

        // Animation/Transition defaults
        // Expanded form: name duration timing-function delay iteration-count direction fill-mode play-state
        'animation': ['none', /^none\s+0s\s+ease\s+0s\s+1\s+normal\s+none\s+running$/],
        'animation-name': ['none'],
        'animation-duration': ['0s'],
        'animation-timing-function': ['ease'],
        'animation-delay': ['0s'],
        'animation-iteration-count': ['1'],
        'animation-direction': ['normal'],
        'animation-fill-mode': ['none'],
        'animation-play-state': ['running'],
        // Expanded form: property duration timing-function delay
        'transition': ['none', 'all', /^all\s+0s\s+ease\s+0s$/],
        'transition-property': ['all'],
        'transition-duration': ['0s'],
        'transition-delay': ['0s'],
        'transition-timing-function': ['ease'],

        // Transform defaults
        'transform': ['none'],
        'transform-origin': [/^\d+(\.\d+)?px\s+\d+(\.\d+)?px$/],  // Any computed center is default

        // List defaults
        'list-style': ['none', 'disc', /^disc\s+outside\s+none$/],
        'list-style-type': ['disc', 'none'],
        'list-style-position': ['outside'],
        'list-style-image': ['none'],

        // Table defaults
        'table-layout': ['auto'],
        'vertical-align': ['baseline'],

        // Cursor defaults
        'cursor': ['auto'],

        // Pointer events
        'pointer-events': ['auto'],
        'user-select': ['auto'],

        // Shadow defaults
        'box-shadow': ['none'],
        'text-shadow': ['none'],

        // Filter defaults
        'filter': ['none'],
        'backdrop-filter': ['none'],

        // Outline defaults (note: outline can be visible during focus)
        'outline': ['none', /^0px\s+none/],
        'outline-width': ['0px', '0'],
        'outline-style': ['none'],
        'outline-offset': ['0px', '0'],

        // Content
        'content': ['normal', 'none'],

        // Box sizing (content-box is the actual default, border-box is a common reset)
        'box-sizing': ['content-box'],

        // Float/clear
        'float': ['none'],
        'clear': ['none'],

        // Order
        'order': ['0'],
    };

    /**
     * Normalize a CSS value for comparison.
     * Handles whitespace differences, zero units, etc.
     */
    function normalizeValue(value) {
        if (!value || typeof value !== 'string') return value;

        let normalized = value;

        // Normalize whitespace: multiple spaces to single, trim
        normalized = normalized.replace(/\s+/g, ' ').trim();

        // Normalize spaces around separators
        normalized = normalized.replace(/\s*\/\s*/g, ' / ');
        normalized = normalized.replace(/\s*,\s*/g, ', ');

        // Normalize zero values: 0px, 0em, 0%, etc. → 0
        // But be careful not to affect values like "10px" or color values
        normalized = normalized.replace(/\b0(px|em|rem|%|vh|vw|vmin|vmax|ch|ex|cm|mm|in|pt|pc|deg|rad|turn|s|ms)\b/gi, '0');

        // Normalize rgba(0, 0, 0, 0) variations
        normalized = normalized.replace(/rgba?\(\s*0\s*,\s*0\s*,\s*0\s*,\s*0\s*\)/gi, 'rgba(0, 0, 0, 0)');

        return normalized;
    }

    /**
     * Round pixel values to nearest whole pixel.
     * E.g., "389.453125px" → "389px", "30.875px" → "31px"
     *
     * Returns an object with:
     * - value: the rounded value string
     * - wasRounded: true if any rounding occurred
     */
    function roundPixelValues(value, doRounding) {
        if (!value || typeof value !== 'string') return { value, wasRounded: false };

        let wasRounded = false;

        // Match pixel values with decimal places
        const rounded = value.replace(/(\d+\.\d+)px/g, (match, num) => {
            if (doRounding) {
                wasRounded = true;
                return Math.round(parseFloat(num)) + 'px';
            }
            return match;
        });

        return { value: rounded, wasRounded };
    }

    /**
     * Check if a value has decimal pixel values (computed values).
     * Used to detect computed values when rounding is disabled.
     */
    function hasDecimalPixels(value) {
        if (!value || typeof value !== 'string') return false;
        return /\d+\.\d+px/.test(value);
    }

    /**
     * Properties where "auto" default computes to specific pixels.
     * These will be marked as "computed" in the output.
     */
    const AUTO_COMPUTED_PROPERTIES = ['width', 'height', 'min-width', 'min-height'];

    /**
     * Shorthand property groups.
     * When any property in a group has a non-default value, ALL properties in the
     * group should be included so Lightning CSS can merge them into shorthands.
     *
     * Example: If margin-top: 18px is non-default, we also include margin-right: 0px,
     * margin-bottom: 18px, margin-left: 0px so Lightning CSS can output: margin: 18px 0
     */
    const SHORTHAND_GROUPS = {
        // Margin (4-value shorthand: top right bottom left)
        'margin': ['margin-top', 'margin-right', 'margin-bottom', 'margin-left'],

        // Padding (4-value shorthand: top right bottom left)
        'padding': ['padding-top', 'padding-right', 'padding-bottom', 'padding-left'],

        // Border width (4-value shorthand)
        'border-width': ['border-top-width', 'border-right-width', 'border-bottom-width', 'border-left-width'],

        // Border style (4-value shorthand)
        'border-style': ['border-top-style', 'border-right-style', 'border-bottom-style', 'border-left-style'],

        // Border color (4-value shorthand)
        'border-color': ['border-top-color', 'border-right-color', 'border-bottom-color', 'border-left-color'],

        // Border radius (4-value shorthand)
        'border-radius': ['border-top-left-radius', 'border-top-right-radius', 'border-bottom-right-radius', 'border-bottom-left-radius'],

        // Inset (4-value shorthand: top right bottom left)
        'inset': ['top', 'right', 'bottom', 'left'],

        // Background position
        'background-position': ['background-position-x', 'background-position-y'],

        // Overflow
        'overflow': ['overflow-x', 'overflow-y'],

        // Gap (2-value shorthand: row column)
        'gap': ['row-gap', 'column-gap'],

        // Outline
        'outline': ['outline-width', 'outline-style', 'outline-color'],

        // Text decoration (4-value shorthand: line style color thickness)
        'text-decoration': ['text-decoration-line', 'text-decoration-style', 'text-decoration-color', 'text-decoration-thickness'],

        // Transition (4-value shorthand: property duration timing delay)
        'transition': ['transition-property', 'transition-duration', 'transition-timing-function', 'transition-delay'],

        // Flex (3-value shorthand: grow shrink basis)
        'flex': ['flex-grow', 'flex-shrink', 'flex-basis'],

        // Place shorthands (2-value: align + justify)
        'place-items': ['align-items', 'justify-items'],
        'place-content': ['align-content', 'justify-content'],
        'place-self': ['align-self', 'justify-self'],
    };

    /**
     * Build a reverse lookup: longhand property → group name
     */
    const LONGHAND_TO_GROUP = {};
    for (const [groupName, longhands] of Object.entries(SHORTHAND_GROUPS)) {
        for (const prop of longhands) {
            LONGHAND_TO_GROUP[prop] = groupName;
        }
    }

    /**
     * Check if a value matches a known default pattern
     */
    function matchesKnownDefault(prop, value) {
        const defaults = KNOWN_DEFAULTS[prop];
        if (!defaults) return false;

        const normalizedValue = normalizeValue(value);

        for (const pattern of defaults) {
            if (pattern instanceof RegExp) {
                if (pattern.test(value) || pattern.test(normalizedValue)) {
                    return true;
                }
            } else {
                // String comparison (also normalized)
                if (value === pattern || normalizedValue === pattern || normalizedValue === normalizeValue(pattern)) {
                    return true;
                }
            }
        }

        return false;
    }

    /**
     * Check if a value is a default value
     */
    function isDefaultValue(prop, value, defaultStyles) {
        // First check against known default patterns
        if (matchesKnownDefault(prop, value)) {
            return true;
        }

        // Then check against iframe-computed defaults with normalization
        if (defaultStyles && defaultStyles[prop]) {
            const normalizedValue = normalizeValue(value);
            const normalizedDefault = normalizeValue(defaultStyles[prop]);

            if (normalizedValue === normalizedDefault) {
                return true;
            }
        }

        return false;
    }

    /**
     * Get default styles for a tag by creating a temporary element.
     *
     * For certain elements, we need to include attributes that affect default styling:
     * - <a href="…">: links have different cursor/text-decoration than plain <a>
     * - <input type="…">: different types have different defaults
     * - <button>: has different defaults than other elements
     */
    function getDefaultStyles(tagName, element) {
        // Build a cache key that includes relevant attributes
        let cacheKey = tagName;

        // For links, include whether it has href (affects cursor, text-decoration)
        if (tagName === 'a' && element && element.hasAttribute('href')) {
            cacheKey = 'a[href]';
        }
        // For inputs, include type (affects appearance)
        if (tagName === 'input' && element) {
            const type = element.getAttribute('type') || 'text';
            cacheKey = `input[type="${type}"]`;
        }

        if (defaultStylesCache[cacheKey]) {
            return defaultStylesCache[cacheKey];
        }

        // Create temporary element in an iframe to get clean defaults
        const iframe = document.createElement('iframe');
        iframe.style.display = 'none';
        document.body.appendChild(iframe);

        try {
            const iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
            iframeDoc.open();
            iframeDoc.write('<!DOCTYPE html><html><head></head><body></body></html>');
            iframeDoc.close();

            const tempElement = iframeDoc.createElement(tagName);

            // Copy attributes that affect default styling
            if (tagName === 'a' && element && element.hasAttribute('href')) {
                tempElement.setAttribute('href', '#');  // Any href will do
            }
            if (tagName === 'input' && element) {
                const type = element.getAttribute('type');
                if (type) tempElement.setAttribute('type', type);
            }
            if (tagName === 'button' && element) {
                const type = element.getAttribute('type');
                if (type) tempElement.setAttribute('type', type);
            }

            iframeDoc.body.appendChild(tempElement);

            const defaultStyles = {};
            const computed = iframe.contentWindow.getComputedStyle(tempElement);

            for (let prop of computed) {
                defaultStyles[prop] = computed.getPropertyValue(prop);
            }

            defaultStylesCache[cacheKey] = defaultStyles;
            return defaultStyles;
        } finally {
            // Always clean up the iframe, even if an error occurred
            if (iframe.parentNode) {
                iframe.parentNode.removeChild(iframe);
            }
        }
    }

    /**
     * Get computed styles for an element
     *
     * Returns an object with:
     * - styles: the CSS properties and values
     * - roundedProps: array of property names that were rounded
     * - computedProps: array of property names that have decimal pixel values (when not rounding)
     *
     * @param parentStyles - computed styles of the parent element (for filtering redundant inherited props)
     */
    function getComputedStyles(element, allProperties, includeDefaults, roundPixels, parentStyles = null) {
        const computed = window.getComputedStyle(element);
        const tagName = element.tagName.toLowerCase();
        const defaultStyles = includeDefaults ? null : getDefaultStyles(tagName, element);

        const result = {};
        const roundedProps = [];   // Track properties that were rounded
        const computedProps = [];  // Track properties with decimal pixels (when not rounding)
        const properties = allProperties
            ? Array.from(computed)
            : COMMON_PROPERTIES.filter(p => computed.getPropertyValue(p));

        // Track statistics
        let totalPropsConsidered = 0;  // Properties with non-empty values
        let strippedAsDefault = 0;     // Properties stripped because they were default
        let strippedAsInherited = 0;   // Properties stripped because they match parent (inherited)

        // First pass: identify which shorthand groups have at least one non-default value
        const activeGroups = new Set();
        if (!includeDefaults) {
            for (let prop of properties) {
                const value = computed.getPropertyValue(prop);
                if (!value || value === '') continue;
                if (!allProperties && prop.startsWith('-')) continue;

                // Check if this property is part of a shorthand group
                const groupName = LONGHAND_TO_GROUP[prop];
                if (groupName && !isDefaultValue(prop, value, defaultStyles)) {
                    activeGroups.add(groupName);
                }
            }
        }

        // Second pass: collect properties, including all longhands from active groups
        for (let prop of properties) {
            let value = computed.getPropertyValue(prop);

            // Skip empty values
            if (!value || value === '') continue;

            // Skip vendor prefixes unless allProperties is true
            if (!allProperties && prop.startsWith('-')) continue;

            // Count this as a considered property
            totalPropsConsidered++;

            // Check if this property is part of an active shorthand group
            const groupName = LONGHAND_TO_GROUP[prop];
            const inActiveGroup = groupName && activeGroups.has(groupName);

            // Skip default values unless:
            // - includeDefaults is true, OR
            // - the property is part of an active shorthand group (so Lightning CSS can merge)
            if (!includeDefaults && !inActiveGroup && isDefaultValue(prop, value, defaultStyles)) {
                strippedAsDefault++;
                continue;
            }

            // Skip inherited properties that match parent value (redundant)
            // Only do this for non-root elements (where parentStyles exists)
            // But never strip properties that are part of an active shorthand group,
            // because Lightning CSS needs all longhands present to merge the shorthand.
            if (!includeDefaults && !inActiveGroup && parentStyles && INHERITED_PROPERTIES.has(prop)) {
                const parentValue = parentStyles[prop];
                if (parentValue && normalizeValue(value) === normalizeValue(parentValue)) {
                    strippedAsInherited++;
                    continue;
                }
            }

            // Check for decimal pixels before rounding
            const hadDecimalPixels = hasDecimalPixels(value);

            // Round pixel values to nearest whole pixel (if enabled)
            const { value: processedValue, wasRounded } = roundPixelValues(value, roundPixels);
            value = processedValue;

            // Track rounded or computed properties
            if (wasRounded) {
                roundedProps.push(prop);
            } else if (hadDecimalPixels) {
                // Not rounding, but value had decimal pixels - mark as computed
                computedProps.push(prop);
            }

            result[prop] = value;
        }

        return {
            styles: result,
            roundedProps: roundedProps,
            computedProps: computedProps,
            stats: {
                totalConsidered: totalPropsConsidered,
                strippedAsDefault: strippedAsDefault,
                strippedAsInherited: strippedAsInherited,
                kept: Object.keys(result).length
            }
        };
    }

    /**
     * Generate a selector for an element
     */
    function generateSelector(element, parentSelector, siblingIndex, siblingCount) {
        const tagName = element.tagName.toLowerCase();
        const id = element.id;
        const classes = Array.from(element.classList);

        // Prefer ID if available
        if (id) {
            return `#${CSS.escape(id)}`;
        }

        // Use classes if available (escape special characters for valid CSS)
        if (classes.length > 0) {
            return classes.map(c => `.${CSS.escape(c)}`).join('');
        }

        // Use tag name, with :nth-child if needed for uniqueness
        if (siblingCount > 1) {
            // Check if there are other siblings with the same tag
            const parent = element.parentElement;
            if (parent) {
                const sameTagSiblings = Array.from(parent.children).filter(
                    child => child.tagName === element.tagName
                );
                if (sameTagSiblings.length > 1) {
                    const index = sameTagSiblings.indexOf(element) + 1;
                    return `${tagName}:nth-of-type(${index})`;
                }
            }
        }

        return tagName;
    }

    /**
     * Process an element and its children recursively
     */
    function processElement(element, parentSelector = '', siblingIndex = 0, siblingCount = 1, parentStyles = null) {
        const selector = generateSelector(element, parentSelector, siblingIndex, siblingCount);
        const roundPixels = options.roundPixels !== false;  // Default to true
        const { styles, roundedProps, computedProps, stats } = getComputedStyles(
            element, options.allProperties, options.includeDefaults, roundPixels, parentStyles
        );

        // Get computed styles for this element to pass to children
        const computedForChildren = window.getComputedStyle(element);
        const stylesForChildren = {};
        for (const prop of INHERITED_PROPERTIES) {
            stylesForChildren[prop] = computedForChildren.getPropertyValue(prop);
        }

        const children = Array.from(element.children);
        const processedChildren = children.map((child, index) =>
            processElement(child, selector, index, children.length, stylesForChildren)
        );

        return {
            selector: selector,
            tag: element.tagName.toLowerCase(),
            styles: styles,
            roundedProps: roundedProps,    // Properties that were rounded
            computedProps: computedProps,  // Properties with decimal pixels (when not rounding)
            stats: stats,                  // Property statistics for this element
            children: processedChildren
        };
    }

    // Get element based on source type
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

    let element;
    if (sourceType === 'inspected') {
        element = window.__INSPEKT_INSPECTED_ELEMENT__;

        if (!element && typeof window.inspektStore === 'function') {
            const stored = window.inspektStore();
            if (stored && stored.element) {
                element = stored.element;
            }
        }
    } else if (sourceType === 'focused') {
        element = getDeepActiveElement();
    }

    if (!element) {
        const errorMsg = sourceType === 'inspected'
            ? 'No element is currently inspected. Use `inspekt inspect` or select an element in DevTools first.'
            : 'No element is currently focused. Press Tab to focus an interactive element.';
        return {
            ok: false,
            error: errorMsg
        };
    }

    try {
        const root = processElement(element);

        // Aggregate stats from all elements
        function aggregateStats(node) {
            const stats = {
                totalConsidered: node.stats?.totalConsidered || 0,
                strippedAsDefault: node.stats?.strippedAsDefault || 0,
                strippedAsInherited: node.stats?.strippedAsInherited || 0,
                kept: node.stats?.kept || 0
            };
            for (const child of node.children) {
                const childStats = aggregateStats(child);
                stats.totalConsidered += childStats.totalConsidered;
                stats.strippedAsDefault += childStats.strippedAsDefault;
                stats.strippedAsInherited += childStats.strippedAsInherited;
                stats.kept += childStats.kept;
            }
            return stats;
        }

        const totalStats = aggregateStats(root);

        return {
            ok: true,
            root: root,
            elementCount: countElements(root),
            stats: totalStats,  // Aggregated statistics
            // Page metadata for file output
            pageDomain: window.location.hostname || ''
        };
    } catch (e) {
        return {
            ok: false,
            error: `Failed to extract styles: ${e.message}`
        };
    }

    function countElements(node) {
        return 1 + node.children.reduce((sum, child) => sum + countElements(child), 0);
    }
})()
