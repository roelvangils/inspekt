/**
 * Interactive region selection for screenshot capture.
 *
 * Allows users to drag-select a rectangular region on the page.
 * The selection automatically snaps to the combined bounding box of
 * overlapping DOM elements if within the tolerance threshold.
 *
 * Actions:
 * - 'start': Initialize selection mode with crosshair cursor
 * - 'poll': Check for selection state (confirmed, cancelled, or waiting)
 * - 'stop': Force cleanup and stop selection mode
 *
 * Placeholders:
 * - ACTION_PLACEHOLDER: 'start' | 'poll' | 'stop'
 * - OPTIONS_PLACEHOLDER: JSON object with selection options
 */

(function() {
    const action = 'ACTION_PLACEHOLDER';
    const options = OPTIONS_PLACEHOLDER;

    // Default options
    const defaults = {
        snapTolerance: 0.25,      // 25% tolerance for snapping
        highlightColor: '#0066ff', // Selection box color (blue)
        snappedColor: '#00cc66',   // Snapped region color (green)
        overlayOpacity: 0.15       // Selection overlay opacity
    };

    const config = { ...defaults, ...options };

    /**
     * Calculate rectangle from two corner points (handles negative drag)
     */
    function calculateRect(x1, y1, x2, y2) {
        return {
            x: Math.min(x1, x2),
            y: Math.min(y1, y2),
            width: Math.abs(x2 - x1),
            height: Math.abs(y2 - y1)
        };
    }

    /**
     * Check if two rectangles overlap
     */
    function rectsOverlap(r1, r2) {
        return !(
            r2.x > r1.x + r1.width ||
            r2.x + r2.width < r1.x ||
            r2.y > r1.y + r1.height ||
            r2.y + r2.height < r1.y
        );
    }

    /**
     * Inject CSS styles for selection UI
     */
    function injectStyles() {
        if (document.getElementById('inspekt-selection-styles')) return;

        const style = document.createElement('style');
        style.id = 'inspekt-selection-styles';
        style.textContent = `
            /* Full-page overlay with crosshair cursor */
            #inspekt-selection-overlay {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                z-index: 2147483646;
                cursor: crosshair;
                pointer-events: auto;
                background: transparent;
            }

            /* Selection rectangle - raw selection (blue dashed) */
            #inspekt-selection-box {
                position: fixed;
                border: 2px dashed ${config.highlightColor};
                background: rgba(0, 102, 255, ${config.overlayOpacity});
                pointer-events: none;
                z-index: 2147483647;
                display: none;
                box-sizing: border-box;
            }

            /* Snapped region preview (green solid) */
            #inspekt-snapped-box {
                position: fixed;
                border: 3px solid ${config.snappedColor};
                background: rgba(0, 204, 102, 0.15);
                pointer-events: none;
                z-index: 2147483647;
                display: none;
                box-sizing: border-box;
                box-shadow: 0 0 0 4px rgba(0, 204, 102, 0.3);
            }

            /* Instructions tooltip */
            #inspekt-selection-hint {
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0, 0, 0, 0.85);
                color: white;
                padding: 12px 24px;
                border-radius: 8px;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 14px;
                font-weight: 500;
                z-index: 2147483647;
                pointer-events: none;
                white-space: nowrap;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            }

            /* Snap indicator badge */
            #inspekt-snap-badge {
                position: fixed;
                background: ${config.snappedColor};
                color: white;
                padding: 6px 12px;
                border-radius: 4px;
                font-family: system-ui, -apple-system, sans-serif;
                font-size: 12px;
                font-weight: 600;
                z-index: 2147483647;
                pointer-events: none;
                display: none;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
            }

            /* Debug: Combined bounding box preview (yellow dashed) */
            #inspekt-combined-box {
                position: fixed;
                border: 2px dashed #ffcc00;
                background: rgba(255, 204, 0, 0.1);
                pointer-events: none;
                z-index: 2147483645;
                display: none;
                box-sizing: border-box;
            }

            /* Debug: Element highlights */
            .inspekt-debug-element {
                outline: 2px solid #ff4444 !important;
                outline-offset: -2px !important;
            }

            /* Debug info panel */
            #inspekt-debug-panel {
                position: fixed;
                top: 10px;
                right: 10px;
                background: rgba(0, 0, 0, 0.9);
                color: #fff;
                padding: 12px 16px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 11px;
                z-index: 2147483647;
                pointer-events: none;
                max-width: 350px;
                max-height: 300px;
                overflow: auto;
                display: none;
            }

            #inspekt-debug-panel h4 {
                margin: 0 0 8px 0;
                color: #ffcc00;
                font-size: 12px;
            }

            #inspekt-debug-panel .debug-row {
                margin: 4px 0;
                padding: 2px 0;
                border-bottom: 1px solid #333;
            }

            #inspekt-debug-panel .pass { color: #4caf50; }
            #inspekt-debug-panel .fail { color: #f44336; }
            #inspekt-debug-panel .info { color: #2196f3; }
        `;
        document.head.appendChild(style);
    }

    /**
     * Create overlay DOM elements
     */
    function createElements() {
        // Main overlay (captures mouse events)
        const overlay = document.createElement('div');
        overlay.id = 'inspekt-selection-overlay';
        document.body.appendChild(overlay);

        // Selection box (blue dashed)
        const selectionBox = document.createElement('div');
        selectionBox.id = 'inspekt-selection-box';
        document.body.appendChild(selectionBox);

        // Snapped box (green solid)
        const snappedBox = document.createElement('div');
        snappedBox.id = 'inspekt-snapped-box';
        document.body.appendChild(snappedBox);

        // Hint tooltip
        const hint = document.createElement('div');
        hint.id = 'inspekt-selection-hint';
        hint.textContent = 'Drag to select a region';
        document.body.appendChild(hint);

        // Snap badge
        const badge = document.createElement('div');
        badge.id = 'inspekt-snap-badge';
        document.body.appendChild(badge);

        // Debug: Combined bounding box
        const combinedBox = document.createElement('div');
        combinedBox.id = 'inspekt-combined-box';
        document.body.appendChild(combinedBox);

        // Debug: Info panel
        const debugPanel = document.createElement('div');
        debugPanel.id = 'inspekt-debug-panel';
        document.body.appendChild(debugPanel);
    }

    /**
     * Update selection box position and size
     */
    function updateSelectionBox() {
        const state = window.__INSPEKT_SELECTION__;
        if (!state || !state.dragging) return;

        const rect = calculateRect(
            state.startX, state.startY,
            state.currentX, state.currentY
        );

        const box = document.getElementById('inspekt-selection-box');
        if (box) {
            box.style.display = 'block';
            box.style.left = rect.x + 'px';
            box.style.top = rect.y + 'px';
            box.style.width = rect.width + 'px';
            box.style.height = rect.height + 'px';
        }

        // Hide snapped box while dragging
        const snappedBox = document.getElementById('inspekt-snapped-box');
        if (snappedBox) {
            snappedBox.style.display = 'none';
        }

        // Hide badge while dragging
        const badge = document.getElementById('inspekt-snap-badge');
        if (badge) {
            badge.style.display = 'none';
        }
    }

    /**
     * Find all DOM elements that overlap with the selection rectangle
     * Filters to prefer "content" elements over large containers
     */
    function findOverlappingElements() {
        const state = window.__INSPEKT_SELECTION__;
        if (!state || !state.rawRect) return;

        const rect = state.rawRect;
        const allElements = document.querySelectorAll('*');
        const candidates = [];

        for (const el of allElements) {
            // Skip non-visual elements
            if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' ||
                el.tagName === 'NOSCRIPT' || el.tagName === 'BR' ||
                el.tagName === 'HEAD' || el.tagName === 'META' ||
                el.tagName === 'LINK' || el.tagName === 'TITLE' ||
                el.tagName === 'HTML' || el.tagName === 'BODY') continue;

            // Skip our own UI elements
            if (el.id && el.id.startsWith('inspekt-')) continue;

            // Skip invisible elements
            const style = getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            if (parseFloat(style.opacity) === 0) continue;

            const elRect = el.getBoundingClientRect();

            // Skip elements with zero dimensions
            if (elRect.width === 0 || elRect.height === 0) continue;

            // Check for overlap
            if (rectsOverlap(rect, {
                x: elRect.x,
                y: elRect.y,
                width: elRect.width,
                height: elRect.height
            })) {
                // Calculate how much larger the element is than the selection
                const areaRatio = (elRect.width * elRect.height) / (rect.width * rect.height);

                candidates.push({
                    element: el,
                    rect: elRect,
                    areaRatio: areaRatio,
                    // Prefer elements that are similar size or smaller than selection
                    isContentElement: areaRatio <= 4 // Element is at most 4x the selection size
                });
            }
        }

        // Filter strategy:
        // 1. If we have content-sized elements, use only those
        // 2. Otherwise, use the smallest elements that overlap
        const contentElements = candidates.filter(c => c.isContentElement);

        if (contentElements.length > 0) {
            state.overlappingElements = contentElements.map(c => c.element);
        } else if (candidates.length > 0) {
            // Sort by area ratio and take elements up to 10x selection size
            candidates.sort((a, b) => a.areaRatio - b.areaRatio);
            const smallerElements = candidates.filter(c => c.areaRatio <= 10);
            state.overlappingElements = smallerElements.length > 0
                ? smallerElements.map(c => c.element)
                : [candidates[0].element]; // At least use the smallest one
        } else {
            state.overlappingElements = [];
        }
    }

    /**
     * Clear debug highlights from previous calculation
     */
    function clearDebugHighlights() {
        document.querySelectorAll('.inspekt-debug-element').forEach(el => {
            el.classList.remove('inspekt-debug-element');
        });
    }

    /**
     * Show debug visualization of snap calculation
     */
    function showDebugVisualization(rawRect, combinedRect, elements, tolerances, deltas, snapped) {
        // Only show debug visualization if debug mode is enabled
        if (!config.debug) return;

        // Highlight detected elements with red outline
        clearDebugHighlights();
        elements.forEach(el => {
            el.classList.add('inspekt-debug-element');
        });

        // Show combined bounding box (yellow dashed)
        const combinedBox = document.getElementById('inspekt-combined-box');
        if (combinedBox && combinedRect) {
            combinedBox.style.display = 'block';
            combinedBox.style.left = combinedRect.x + 'px';
            combinedBox.style.top = combinedRect.y + 'px';
            combinedBox.style.width = combinedRect.width + 'px';
            combinedBox.style.height = combinedRect.height + 'px';
        }

        // Show debug panel with info
        const debugPanel = document.getElementById('inspekt-debug-panel');
        if (debugPanel) {
            debugPanel.style.display = 'block';

            const passOrFail = (val, max) => val <= max
                ? `<span class="pass">${val.toFixed(0)}px ≤ ${max.toFixed(0)}px ✓</span>`
                : `<span class="fail">${val.toFixed(0)}px > ${max.toFixed(0)}px ✗</span>`;

            debugPanel.innerHTML = `
                <h4>🔍 Snap Debug Info</h4>
                <div class="debug-row">
                    <strong>Selection:</strong> ${Math.round(rawRect.width)}×${Math.round(rawRect.height)}px
                </div>
                <div class="debug-row">
                    <strong>Elements found:</strong> <span class="info">${elements.length}</span>
                    ${elements.slice(0, 5).map(el => {
                        const tag = el.tagName.toLowerCase();
                        const cls = el.className ? '.' + el.className.split(' ')[0] : '';
                        const id = el.id ? '#' + el.id : '';
                        return `<br>&nbsp;&nbsp;• &lt;${tag}${id}${cls}&gt;`;
                    }).join('')}
                    ${elements.length > 5 ? `<br>&nbsp;&nbsp;... and ${elements.length - 5} more` : ''}
                </div>
                <div class="debug-row">
                    <strong>Combined box:</strong> ${combinedRect ? `${Math.round(combinedRect.width)}×${Math.round(combinedRect.height)}px` : 'none'}
                </div>
                <div class="debug-row">
                    <strong>Tolerance (${(config.snapTolerance * 100).toFixed(0)}%):</strong><br>
                    &nbsp;&nbsp;X: ${tolerances.x.toFixed(0)}px, Y: ${tolerances.y.toFixed(0)}px
                </div>
                <div class="debug-row">
                    <strong>Edge deltas:</strong><br>
                    &nbsp;&nbsp;Left: ${passOrFail(deltas.left, tolerances.x)}<br>
                    &nbsp;&nbsp;Right: ${passOrFail(deltas.right, tolerances.x)}<br>
                    &nbsp;&nbsp;Top: ${passOrFail(deltas.top, tolerances.y)}<br>
                    &nbsp;&nbsp;Bottom: ${passOrFail(deltas.bottom, tolerances.y)}
                </div>
                <div class="debug-row">
                    <strong>Result:</strong> ${snapped
                        ? '<span class="pass">SNAPPED ✓</span>'
                        : '<span class="fail">NOT SNAPPED ✗</span>'}
                </div>
            `;
        }
    }

    /**
     * Calculate snapped bounds from overlapping elements
     * Applies 25% tolerance check
     */
    function calculateSnappedBounds() {
        const state = window.__INSPEKT_SELECTION__;
        if (!state || !state.rawRect) return;

        const elements = state.overlappingElements;
        const rawRect = state.rawRect;

        // No elements - use raw selection
        if (!elements || elements.length === 0) {
            state.snapped = false;
            state.snappedRect = { ...rawRect };
            showDebugVisualization(rawRect, null, [], { x: 0, y: 0 }, { left: 0, right: 0, top: 0, bottom: 0 }, false);
            return;
        }

        // Calculate combined bounding box of all overlapping elements
        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;

        for (const el of elements) {
            const r = el.getBoundingClientRect();
            minX = Math.min(minX, r.x);
            minY = Math.min(minY, r.y);
            maxX = Math.max(maxX, r.x + r.width);
            maxY = Math.max(maxY, r.y + r.height);
        }

        const combinedRect = {
            x: minX,
            y: minY,
            width: maxX - minX,
            height: maxY - minY
        };

        // Calculate tolerance based on raw selection size
        const tolerance = config.snapTolerance;
        const toleranceX = rawRect.width * tolerance;
        const toleranceY = rawRect.height * tolerance;

        // Check if combined bounds are within tolerance on each side
        const deltaLeft = Math.abs(combinedRect.x - rawRect.x);
        const deltaTop = Math.abs(combinedRect.y - rawRect.y);
        const deltaRight = Math.abs((combinedRect.x + combinedRect.width) -
                                    (rawRect.x + rawRect.width));
        const deltaBottom = Math.abs((combinedRect.y + combinedRect.height) -
                                     (rawRect.y + rawRect.height));

        const tolerances = { x: toleranceX, y: toleranceY };
        const deltas = { left: deltaLeft, right: deltaRight, top: deltaTop, bottom: deltaBottom };

        // Apply snapping if within tolerance on all sides
        if (deltaLeft <= toleranceX && deltaRight <= toleranceX &&
            deltaTop <= toleranceY && deltaBottom <= toleranceY) {
            state.snapped = true;
            state.snappedRect = combinedRect;
        } else {
            // Expansion too large - use raw selection
            state.snapped = false;
            state.snappedRect = { ...rawRect };
        }

        // Show debug visualization
        showDebugVisualization(rawRect, combinedRect, elements, tolerances, deltas, state.snapped);
    }

    /**
     * Show the snapped preview with visual feedback
     */
    function showSnappedPreview() {
        const state = window.__INSPEKT_SELECTION__;
        if (!state || !state.snappedRect) return;

        const rect = state.snappedRect;
        const selectionBox = document.getElementById('inspekt-selection-box');
        const snappedBox = document.getElementById('inspekt-snapped-box');
        const badge = document.getElementById('inspekt-snap-badge');
        const hint = document.getElementById('inspekt-selection-hint');

        if (state.snapped) {
            // Show snapped box (green)
            if (snappedBox) {
                snappedBox.style.display = 'block';
                snappedBox.style.left = rect.x + 'px';
                snappedBox.style.top = rect.y + 'px';
                snappedBox.style.width = rect.width + 'px';
                snappedBox.style.height = rect.height + 'px';
            }

            // Hide raw selection box
            if (selectionBox) {
                selectionBox.style.display = 'none';
            }

            // Show snap badge
            if (badge) {
                badge.style.display = 'block';
                badge.textContent = `Snapped to ${state.overlappingElements.length} element${state.overlappingElements.length !== 1 ? 's' : ''}`;
                badge.style.left = (rect.x + rect.width / 2) + 'px';
                badge.style.top = (rect.y - 30) + 'px';
                badge.style.transform = 'translateX(-50%)';
            }
        } else {
            // Keep showing raw selection (blue)
            if (selectionBox) {
                selectionBox.style.display = 'block';
                selectionBox.style.left = rect.x + 'px';
                selectionBox.style.top = rect.y + 'px';
                selectionBox.style.width = rect.width + 'px';
                selectionBox.style.height = rect.height + 'px';
            }

            // Hide snapped box
            if (snappedBox) {
                snappedBox.style.display = 'none';
            }

            // Hide badge
            if (badge) {
                badge.style.display = 'none';
            }
        }

        // Update hint
        if (hint) {
            const width = Math.round(rect.width);
            const height = Math.round(rect.height);
            hint.textContent = `${width} x ${height}px - Press Enter or click to capture, Escape to cancel`;
        }
    }

    /**
     * Attach event listeners for drag selection
     */
    function attachEventListeners() {
        const overlay = document.getElementById('inspekt-selection-overlay');
        const state = window.__INSPEKT_SELECTION__;

        if (!overlay || !state) return;

        // Store handlers for cleanup
        state.handlers = {
            mousedown: (e) => {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                state.dragging = true;
                state.startX = e.clientX;
                state.startY = e.clientY;
                state.currentX = e.clientX;
                state.currentY = e.clientY;
                state.rawRect = null;
                state.snappedRect = null;
                state.overlappingElements = [];
                state.snapped = false;
                updateSelectionBox();
            },

            mousemove: (e) => {
                if (!state.dragging) return;
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                state.currentX = e.clientX;
                state.currentY = e.clientY;
                updateSelectionBox();
            },

            mouseup: (e) => {
                if (!state.dragging) return;
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
                state.dragging = false;
                state.currentX = e.clientX;
                state.currentY = e.clientY;

                // Calculate raw selection rectangle
                state.rawRect = calculateRect(
                    state.startX, state.startY,
                    state.currentX, state.currentY
                );

                // Minimum selection size check
                if (state.rawRect.width < 5 || state.rawRect.height < 5) {
                    // Too small - reset
                    state.rawRect = null;
                    const selectionBox = document.getElementById('inspekt-selection-box');
                    if (selectionBox) selectionBox.style.display = 'none';
                    const hint = document.getElementById('inspekt-selection-hint');
                    if (hint) hint.textContent = 'Drag to select a region (selection too small)';
                    return;
                }

                // Find overlapping elements and calculate snapped bounds
                findOverlappingElements();
                calculateSnappedBounds();

                // Show preview
                showSnappedPreview();
            },

            keydown: (e) => {
                if (e.key === 'Escape') {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    state.cancelled = true;
                } else if (e.key === 'Enter' && state.rawRect) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    state.confirmed = true;
                }
            },

            // Click on overlay after selection to confirm
            overlayClick: (e) => {
                // Only confirm if we have a valid selection and not currently dragging
                if (state.rawRect && !state.dragging) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    state.confirmed = true;
                }
            },

            // Block all clicks on document to prevent navigation
            clickBlocker: (e) => {
                if (window.__INSPEKT_SELECTION__?.active) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                }
            }
        };

        overlay.addEventListener('mousedown', state.handlers.mousedown, true);
        document.addEventListener('mousemove', state.handlers.mousemove, true);
        document.addEventListener('mouseup', state.handlers.mouseup, true);
        document.addEventListener('keydown', state.handlers.keydown, true);

        // Block all clicks on document to prevent navigation/refresh
        document.addEventListener('click', state.handlers.clickBlocker, true);

        // Use a small delay before enabling click-to-confirm
        // to prevent accidental immediate confirmation
        setTimeout(() => {
            if (state.active) {
                overlay.addEventListener('click', state.handlers.overlayClick, true);
            }
        }, 500);
    }

    /**
     * Clean up all UI elements and event listeners
     */
    function cleanup() {
        const state = window.__INSPEKT_SELECTION__;

        // Remove event listeners (must use same capture phase as when added)
        if (state?.handlers) {
            const overlay = document.getElementById('inspekt-selection-overlay');
            if (overlay) {
                overlay.removeEventListener('mousedown', state.handlers.mousedown, true);
                overlay.removeEventListener('click', state.handlers.overlayClick, true);
            }
            document.removeEventListener('mousemove', state.handlers.mousemove, true);
            document.removeEventListener('mouseup', state.handlers.mouseup, true);
            document.removeEventListener('keydown', state.handlers.keydown, true);
            document.removeEventListener('click', state.handlers.clickBlocker, true);
        }

        // Clear debug highlights
        clearDebugHighlights();

        // Remove DOM elements
        const elementsToRemove = [
            'inspekt-selection-styles',
            'inspekt-selection-overlay',
            'inspekt-selection-box',
            'inspekt-snapped-box',
            'inspekt-selection-hint',
            'inspekt-snap-badge',
            'inspekt-combined-box',
            'inspekt-debug-panel'
        ];

        for (const id of elementsToRemove) {
            const el = document.getElementById(id);
            if (el) el.remove();
        }

        // Clear state
        delete window.__INSPEKT_SELECTION__;
    }

    /**
     * Start selection mode
     */
    function startSelection() {
        // Check if already active
        if (window.__INSPEKT_SELECTION__?.active) {
            return {
                ok: true,
                message: 'Selection already active'
            };
        }

        // Initialize state
        window.__INSPEKT_SELECTION__ = {
            active: true,
            dragging: false,
            startX: 0,
            startY: 0,
            currentX: 0,
            currentY: 0,
            rawRect: null,
            snappedRect: null,
            overlappingElements: [],
            confirmed: false,
            cancelled: false,
            snapped: false,
            handlers: null
        };

        // Inject styles and create UI
        injectStyles();
        createElements();

        // Attach event listeners
        attachEventListeners();

        return {
            ok: true,
            message: 'Selection mode started',
            instructions: 'Drag to select region. Enter/click to confirm, Escape to cancel.'
        };
    }

    /**
     * Poll for selection state
     */
    function poll() {
        const state = window.__INSPEKT_SELECTION__;

        if (!state || !state.active) {
            return {
                ok: true,
                selectionActive: false,
                message: 'No selection in progress'
            };
        }

        if (state.cancelled) {
            cleanup();
            return {
                ok: true,
                selectionActive: false,
                cancelled: true,
                message: 'Selection cancelled by user'
            };
        }

        if (state.confirmed && state.snappedRect) {
            const finalRect = state.snappedRect;

            // Get scroll position for absolute coordinates
            const scrollX = window.pageXOffset || document.documentElement.scrollLeft;
            const scrollY = window.pageYOffset || document.documentElement.scrollTop;

            // Store result before cleanup
            const result = {
                ok: true,
                selectionActive: false,
                confirmed: true,
                clip: {
                    x: finalRect.x,
                    y: finalRect.y,
                    width: finalRect.width,
                    height: finalRect.height
                },
                // Absolute coordinates for CDP capture
                absoluteClip: {
                    x: finalRect.x + scrollX,
                    y: finalRect.y + scrollY,
                    width: finalRect.width,
                    height: finalRect.height
                },
                snapped: state.snapped,
                elementCount: state.overlappingElements.length,
                devicePixelRatio: window.devicePixelRatio || 1,
                viewportWidth: window.innerWidth,
                viewportHeight: window.innerHeight
            };

            cleanup();
            return result;
        }

        // Still waiting for selection
        return {
            ok: true,
            selectionActive: true,
            dragging: state.dragging,
            hasSelection: !!state.rawRect,
            snapped: state.snapped,
            elementCount: state.overlappingElements?.length || 0
        };
    }

    /**
     * Stop selection mode (force cleanup)
     */
    function stop() {
        cleanup();
        return {
            ok: true,
            message: 'Selection stopped'
        };
    }

    // Main entry point
    try {
        if (action === 'start') {
            return startSelection();
        } else if (action === 'poll') {
            return poll();
        } else if (action === 'stop') {
            return stop();
        } else {
            return {
                ok: false,
                error: `Unknown action: ${action}`
            };
        }
    } catch (error) {
        cleanup();
        return {
            ok: false,
            error: String(error)
        };
    }
})()
