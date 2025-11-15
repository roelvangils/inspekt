/**
 * Element Picker Script
 *
 * Injected into the page to allow element selection without switching to Elements tab.
 * Provides hover highlighting and click-to-select functionality.
 */

(function() {
    // Prevent multiple activations
    if (window.__INSPEKT_PICKER_ACTIVE__) {
        return { error: 'Picker already active' };
    }

    window.__INSPEKT_PICKER_ACTIVE__ = true;

    let currentHighlight = null;
    let overlay = null;
    let highlightBox = null;
    let tooltip = null;

    // Create visual overlay
    function createOverlay() {
        overlay = document.createElement('div');
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 2147483646;
            cursor: crosshair;
            background: transparent;
            pointer-events: auto;
        `;
        document.body.appendChild(overlay);

        // Create animated highlight box
        highlightBox = document.createElement('div');
        highlightBox.style.cssText = `
            position: fixed;
            pointer-events: none;
            z-index: 2147483646;
            border: 2px solid #0066ff;
            border-radius: 2px;
            background: rgba(0, 102, 255, 0.1);
            transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 0 0 1px rgba(0, 102, 255, 0.3),
                        inset 0 0 0 1px rgba(255, 255, 255, 0.5);
            display: none;
        `;
        document.body.appendChild(highlightBox);

        // Create tooltip
        tooltip = document.createElement('div');
        tooltip.style.cssText = `
            position: fixed;
            padding: 6px 12px;
            background: #0066ff;
            color: white;
            border-radius: 4px;
            font-family: monospace;
            font-size: 12px;
            font-weight: bold;
            pointer-events: none;
            z-index: 2147483647;
            display: none;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            transition: all 0.1s ease-out;
        `;
        document.body.appendChild(tooltip);
    }

    // Get element info for tooltip
    function getElementLabel(el) {
        const tag = el.tagName.toLowerCase();
        const id = el.id ? '#' + el.id : '';
        const cls = el.className && typeof el.className === 'string'
            ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.')
            : '';
        return `<${tag}${id}${cls}>`;
    }

    // Highlight element on hover
    function highlightElement(el) {
        if (currentHighlight === el) return;

        currentHighlight = el;

        // Get element's position
        const rect = el.getBoundingClientRect();

        // Show and position the highlight box
        highlightBox.style.display = 'block';
        highlightBox.style.left = rect.left + 'px';
        highlightBox.style.top = rect.top + 'px';
        highlightBox.style.width = rect.width + 'px';
        highlightBox.style.height = rect.height + 'px';
    }

    // Update highlight position (for scroll events)
    function updateHighlightPosition() {
        if (currentHighlight) {
            const rect = currentHighlight.getBoundingClientRect();
            highlightBox.style.left = rect.left + 'px';
            highlightBox.style.top = rect.top + 'px';
            highlightBox.style.width = rect.width + 'px';
            highlightBox.style.height = rect.height + 'px';
        }
    }

    // Handle scroll
    function handleScroll() {
        updateHighlightPosition();
    }

    // Handle mousemove
    function handleMouseMove(e) {
        e.stopPropagation();

        // Get element at cursor position (ignoring our overlay)
        overlay.style.pointerEvents = 'none';
        const el = document.elementFromPoint(e.clientX, e.clientY);
        overlay.style.pointerEvents = 'auto';

        if (el && el !== document.body && el !== document.documentElement) {
            highlightElement(el);

            // Update tooltip
            tooltip.textContent = getElementLabel(el);
            tooltip.style.display = 'block';
            tooltip.style.left = (e.clientX + 15) + 'px';
            tooltip.style.top = (e.clientY + 15) + 'px';
        }
    }

    // Handle click
    function handleClick(e) {
        e.preventDefault();
        e.stopPropagation();

        // Get element at cursor position
        overlay.style.pointerEvents = 'none';
        const el = document.elementFromPoint(e.clientX, e.clientY);
        overlay.style.pointerEvents = 'auto';

        if (el && el !== document.body && el !== document.documentElement) {
            // Store the selected element
            window.__INSPEKT_INSPECTED_ELEMENT__ = el;

            // Show confirmation
            console.log(
                '%c[Inspekt]%c ✓ Element selected: %c' + getElementLabel(el),
                'color: #0066ff; font-weight: bold',
                'color: inherit',
                'color: #00aa00; font-weight: bold'
            );

            // Clean up and exit picker mode
            cleanup();
        }
    }

    // Handle escape key
    function handleKeyDown(e) {
        if (e.key === 'Escape') {
            console.log('%c[Inspekt]%c Picker cancelled',
                'color: #0066ff; font-weight: bold',
                'color: inherit');
            cleanup();
        }
    }

    // Clean up
    function cleanup() {
        window.__INSPEKT_PICKER_ACTIVE__ = false;

        // Remove overlay and tooltip
        if (overlay && overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }
        if (tooltip && tooltip.parentNode) {
            tooltip.parentNode.removeChild(tooltip);
        }

        // Keep highlightBox for navigation - just hide it initially
        if (highlightBox) {
            highlightBox.style.display = 'none';
        }

        // Remove event listeners
        document.removeEventListener('mousemove', handleMouseMove, true);
        document.removeEventListener('click', handleClick, true);
        document.removeEventListener('keydown', handleKeyDown, true);
        document.removeEventListener('scroll', handleScroll, true);
        window.removeEventListener('resize', updateHighlightPosition);

        // After picking, show highlight on selected element
        if (window.__INSPEKT_INSPECTED_ELEMENT__ && typeof window.__INSPEKT_UPDATE_HIGHLIGHT__ === 'function') {
            window.__INSPEKT_UPDATE_HIGHLIGHT__();
        }
    }

    // Persistent scroll/resize handlers for highlightBox
    function updatePersistentHighlight() {
        const el = window.__INSPEKT_INSPECTED_ELEMENT__;
        if (el && highlightBox && highlightBox.style.display !== 'none') {
            const rect = el.getBoundingClientRect();
            highlightBox.style.left = rect.left + 'px';
            highlightBox.style.top = rect.top + 'px';
            highlightBox.style.width = rect.width + 'px';
            highlightBox.style.height = rect.height + 'px';
        }
    }

    // Global function to update highlight position (used for navigation)
    window.__INSPEKT_UPDATE_HIGHLIGHT__ = function() {
        const el = window.__INSPEKT_INSPECTED_ELEMENT__;

        if (!el) {
            if (highlightBox) {
                highlightBox.style.display = 'none';
                // Remove scroll/resize listeners when hiding
                document.removeEventListener('scroll', updatePersistentHighlight, true);
                window.removeEventListener('resize', updatePersistentHighlight);
            }
            return;
        }

        // Remove any persistent outline from previous element to prevent overlap
        const existingOutline = document.querySelector('[data-inspekt-outline="true"]');
        if (existingOutline) {
            // Restore original styles
            const originalOutline = existingOutline.getAttribute('data-inspekt-original-outline');
            const originalBg = existingOutline.getAttribute('data-inspekt-original-background');
            const originalTransition = existingOutline.getAttribute('data-inspekt-original-transition');

            existingOutline.style.outline = originalOutline || '';
            existingOutline.style.backgroundColor = originalBg || '';
            existingOutline.style.transition = originalTransition || '';

            existingOutline.removeAttribute('data-inspekt-outline');
            existingOutline.removeAttribute('data-inspekt-original-outline');
            existingOutline.removeAttribute('data-inspekt-original-background');
            existingOutline.removeAttribute('data-inspekt-original-transition');
        }

        // Create highlightBox if it doesn't exist yet (navigation before picking)
        if (!highlightBox) {
            highlightBox = document.createElement('div');
            highlightBox.style.cssText = `
                position: fixed;
                pointer-events: none;
                z-index: 2147483646;
                border: 2px solid #0066ff;
                border-radius: 2px;
                background: rgba(0, 102, 255, 0.1);
                transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: 0 0 0 1px rgba(0, 102, 255, 0.3),
                            inset 0 0 0 1px rgba(255, 255, 255, 0.5);
                display: none;
            `;
            document.body.appendChild(highlightBox);
        }

        const rect = el.getBoundingClientRect();

        // Show and position the highlight (will morph smoothly due to CSS transition!)
        highlightBox.style.display = 'block';
        highlightBox.style.left = rect.left + 'px';
        highlightBox.style.top = rect.top + 'px';
        highlightBox.style.width = rect.width + 'px';
        highlightBox.style.height = rect.height + 'px';

        // Add persistent scroll/resize listeners to keep highlight anchored
        document.removeEventListener('scroll', updatePersistentHighlight, true);
        window.removeEventListener('resize', updatePersistentHighlight);
        document.addEventListener('scroll', updatePersistentHighlight, true);
        window.addEventListener('resize', updatePersistentHighlight);
    };

    // Initialize picker
    createOverlay();

    // Add event listeners
    document.addEventListener('mousemove', handleMouseMove, true);
    document.addEventListener('click', handleClick, true);
    document.addEventListener('keydown', handleKeyDown, true);
    document.addEventListener('scroll', handleScroll, true);
    window.addEventListener('resize', updateHighlightPosition);

    console.log(
        '%c[Inspekt]%c 🎯 Picker mode active - Click an element or press ESC to cancel',
        'color: #0066ff; font-weight: bold',
        'color: inherit'
    );

    return { success: true, message: 'Picker activated' };
})();
