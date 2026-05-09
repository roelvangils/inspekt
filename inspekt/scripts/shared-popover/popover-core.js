/**
 * Inspekt Unified Popover Core Module
 *
 * Shared popover state management, navigation, and features for both
 * Axe and IBM accessibility audit badges.
 *
 * This module provides:
 * - Unified popover state management
 * - Navigation between violations (prev/next)
 * - Skip similar functionality
 * - Detach/drag functionality
 * - Badge dimming for skipped rules
 * - Direction-aware animations
 *
 * Usage:
 *   const popoverCore = window.__inspektPopoverCore__;
 *   popoverCore.addViolation(element, 'axe', {...});
 *   popoverCore.navigateToViolation(0);
 */

(function() {
    'use strict';

    // ============================================================
    // UNIFIED POPOVER STATE
    // ============================================================

    /**
     * Global state for popover navigation and management
     * Shared across all popovers (any accessibility engine)
     */
    const popoverState = {
        violations: [],           // Array of unified violation objects
        currentIndex: -1,         // Currently displayed violation index
        activeEngines: [],        // List of active engine IDs
        skippedRuleIds: {},       // Skipped rule IDs per engine (dynamic)
        detachedState: {          // Global detached state for ALL popovers
            isDetached: false,
            x: 0,
            y: 0,
            isDragging: false,
            offsetX: 0,
            offsetY: 0
        }
    };

    /**
     * Initialize skippedRuleIds for given engines
     * @param {Array} engines - List of engine IDs (e.g., ['axe', 'eac', 'hcs', 'sia'])
     */
    function initSkippedRuleIds(engines) {
        popoverState.activeEngines = engines || ['axe', 'eac'];
        popoverState.skippedRuleIds = {};
        popoverState.activeEngines.forEach(engineId => {
            popoverState.skippedRuleIds[engineId] = new Set();
        });
    }

    // Initialize with default engines for backwards compatibility
    initSkippedRuleIds(['axe', 'eac']);

    // ============================================================
    // HELPER FUNCTIONS
    // ============================================================

    /**
     * Escapes HTML to prevent XSS.
     * @param {string} text - Text to escape
     * @returns {string} Escaped text
     */
    function escapeHtml(text) {
        if (typeof text !== 'string') return text;
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Get violation data by index
     * @param {number} index - Violation index
     * @returns {Object|null} Violation data or null
     */
    function getViolationByIndex(index) {
        return popoverState.violations[index] || null;
    }

    /**
     * Get current violation index from open popover
     * @returns {number} Current index or -1
     */
    function getCurrentViolationIndex() {
        return popoverState.currentIndex;
    }

    /**
     * Check if a violation should be skipped based on skipped rules
     * A violation is skipped only if ALL its rules from ALL sources are skipped
     * @param {Object} violation - Unified violation object
     * @returns {boolean} True if violation should be skipped
     */
    function shouldSkipViolation(violation) {
        // Iterate over all active engines dynamically
        for (const engineId of popoverState.activeEngines) {
            if (violation.sources[engineId] && violation.sources[engineId].length > 0) {
                const allSkipped = violation.sources[engineId].every(v =>
                    popoverState.skippedRuleIds[engineId]?.has(v.ruleId)
                );
                if (!allSkipped) return false;
            }
        }

        // If we get here, all rules from all sources are skipped
        return true;
    }

    /**
     * Get next non-skipped violation index
     * @returns {number} Next index or -1 if none
     */
    function getNextViolationIndex() {
        const current = popoverState.currentIndex;
        const totalViolations = popoverState.violations.length;

        if (totalViolations === 0) return -1;

        for (let i = 1; i <= totalViolations; i++) {
            const nextIndex = (current + i) % totalViolations;
            const violation = popoverState.violations[nextIndex];

            if (!shouldSkipViolation(violation)) {
                return nextIndex;
            }
        }

        return -1; // All violations are skipped
    }

    /**
     * Get previous non-skipped violation index
     * @returns {number} Previous index or -1 if none
     */
    function getPreviousViolationIndex() {
        const current = popoverState.currentIndex;
        const totalViolations = popoverState.violations.length;

        if (totalViolations === 0) return -1;

        for (let i = 1; i <= totalViolations; i++) {
            const prevIndex = (current - i + totalViolations) % totalViolations;
            const violation = popoverState.violations[prevIndex];

            if (!shouldSkipViolation(violation)) {
                return prevIndex;
            }
        }

        return -1; // All violations are skipped
    }

    /**
     * Toggle skip similar for a specific rule in a specific source
     * @param {string} source - 'axe' or 'ibm'
     * @param {string} ruleId - The rule ID to toggle
     * @returns {boolean} New skip state (true if now skipped)
     */
    function toggleSkipRule(source, ruleId) {
        if (!popoverState.skippedRuleIds[source]) return false;

        if (popoverState.skippedRuleIds[source].has(ruleId)) {
            popoverState.skippedRuleIds[source].delete(ruleId);
            return false;
        } else {
            popoverState.skippedRuleIds[source].add(ruleId);
            return true;
        }
    }

    /**
     * Toggle skip similar for current violation's primary rule
     * @returns {boolean} New skip state (true if now skipped)
     */
    function toggleSkipSimilar() {
        if (popoverState.currentIndex === -1) return false;

        const currentViolation = popoverState.violations[popoverState.currentIndex];
        if (!currentViolation) return false;

        // Get the primary rule (first rule from first available source)
        // Iterate over active engines in order to find the first available source
        let source, ruleId;
        for (const engineId of popoverState.activeEngines) {
            if (currentViolation.sources[engineId] && currentViolation.sources[engineId].length > 0) {
                source = engineId;
                ruleId = currentViolation.sources[engineId][0].ruleId;
                break;
            }
        }

        if (!source || !ruleId) return false;

        return toggleSkipRule(source, ruleId);
    }

    /**
     * Apply dimming to badges based on skipped rules
     */
    function updateBadgeDimming() {
        popoverState.violations.forEach(v => {
            const badge = document.getElementById(v.badgeId);
            if (badge) {
                if (shouldSkipViolation(v)) {
                    badge.classList.add('inspekt-badge--dimmed');
                    badge.disabled = true;
                } else {
                    badge.classList.remove('inspekt-badge--dimmed');
                    badge.disabled = false;
                }
            }
        });
    }

    // ============================================================
    // NAVIGATION
    // ============================================================

    /**
     * Update navigation button states and counter
     * @param {HTMLElement} popover - The popover element
     */
    function updateNavigationControls(popover) {
        // The popover's actual class names use the `inspekt-axe-nav__*`
        // prefix (see popover-content.js:147+). The original `inspekt-nav__*`
        // selectors here matched nothing — counter stayed at the hardcoded
        // "1/1" forever and prev/next buttons were never enabled/disabled.
        const prevBtn = popover.querySelector('.inspekt-axe-nav__prev');
        const nextBtn = popover.querySelector('.inspekt-axe-nav__next');
        const counter = popover.querySelector('.inspekt-axe-nav__counter');
        const skipInput = popover.querySelector('.inspekt-axe-nav__skip-input');

        const total = popoverState.violations.length;
        const current = popoverState.currentIndex + 1; // 1-based for display

        // Update counter
        if (counter) {
            counter.textContent = `${current}/${total}`;
        }

        // Check if we can navigate
        const canGoNext = getNextViolationIndex() !== -1;
        const canGoPrev = getPreviousViolationIndex() !== -1;

        if (prevBtn) prevBtn.disabled = !canGoPrev;
        if (nextBtn) nextBtn.disabled = !canGoNext;

        // Update skip similar switch state
        if (skipInput) {
            const currentViolation = popoverState.violations[popoverState.currentIndex];
            if (currentViolation) {
                skipInput.checked = shouldSkipViolation(currentViolation);
            }
        }
    }

    /**
     * Navigate to a violation by index. Slides the popover from its
     * previous anchored position to the new one; content swap is
     * instant. NO fade, NO scale, NO cross-fade — the only thing that
     * animates is the popover's position.
     *
     * Implementation: pure FLIP. Capture the current popover's on-screen
     * rect, hide it, show the next one (which appears at its natural
     * anchored position), then animate the new popover's transform from
     * the OLD position back to (0, 0) over 200 ms. Browser interpolates
     * the translate; no other property changes.
     *
     * Skipped in detached mode (popover stays where the user dragged it
     * — no movement to animate) and on initial open (no previous popover
     * to slide from).
     *
     * @param {number} targetIndex - Index to navigate to
     */
    function navigateToViolation(targetIndex) {
        if (targetIndex < 0 || targetIndex >= popoverState.violations.length) return;

        const targetViolation = popoverState.violations[targetIndex];
        if (!targetViolation) return;

        // Update active badge styling
        document.querySelectorAll('.inspekt-badge--active').forEach(b =>
            b.classList.remove('inspekt-badge--active')
        );
        const activeBadge = document.getElementById(targetViolation.badgeId);
        if (activeBadge) activeBadge.classList.add('inspekt-badge--active');

        const targetPopover = document.getElementById(targetViolation.popoverId);
        if (!targetPopover) return;

        const currentIndex = popoverState.currentIndex;

        // Capture the previous popover's screen rect BEFORE we hide it —
        // this is the FLIP "from" position. Skipped for initial open (no
        // current popover) and for detached mode (no movement needed).
        let fromRect = null;
        if (currentIndex >= 0 && !popoverState.detachedState.isDetached) {
            const cv = popoverState.violations[currentIndex];
            if (cv && cv.popoverId !== targetViolation.popoverId) {
                const cp = document.getElementById(cv.popoverId);
                if (cp && cp.matches(':popover-open')) {
                    fromRect = cp.getBoundingClientRect();
                    cp.hidePopover();
                }
            }
        }

        popoverState.currentIndex = targetIndex;
        targetPopover.showPopover();
        updateNavigationControls(targetPopover);

        if (fromRect) {
            const toRect = targetPopover.getBoundingClientRect();
            const dx = fromRect.left - toRect.left;
            const dy = fromRect.top  - toRect.top;
            // Skip animation if the delta is sub-pixel — same anchor or
            // visually identical position.
            if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
                targetPopover.animate(
                    [
                        { transform: `translate(${dx}px, ${dy}px)` },
                        { transform: 'translate(0, 0)' },
                    ],
                    { duration: 200, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', fill: 'none' }
                );
            }
        }
    }

    // ============================================================
    // DETACH/DRAG FUNCTIONALITY
    // ============================================================

    /**
     * Toggle detach/reattach state for ALL popovers
     * @param {HTMLElement} popover - The popover element
     */
    function toggleDetach(popover) {
        const detachButton = popover.querySelector('.inspekt-axe-nav__detach');
        const isDetached = popoverState.detachedState.isDetached;

        if (isDetached) {
            // Reattach
            popoverState.detachedState.isDetached = false;
            popover.classList.remove('inspekt-axe-popover--detached');
            popover.style.left = '';
            popover.style.top = '';
            if (detachButton) {
                detachButton.classList.remove('inspekt-axe-nav__detach--active');
                detachButton.setAttribute('aria-pressed', 'false');
                detachButton.title = 'Detach popover (drag freely on page)';
            }
            disableDragging(popover);
        } else {
            // Detach
            const rect = popover.getBoundingClientRect();
            popoverState.detachedState.isDetached = true;
            popoverState.detachedState.x = rect.left;
            popoverState.detachedState.y = rect.top;
            popoverState.detachedState.isDragging = false;
            popover.classList.add('inspekt-axe-popover--detached');
            popover.style.left = rect.left + 'px';
            popover.style.top = rect.top + 'px';
            if (detachButton) {
                detachButton.classList.add('inspekt-axe-nav__detach--active');
                detachButton.setAttribute('aria-pressed', 'true');
                detachButton.title = 'Reattach popover to badge';
            }
            enableDragging(popover);
        }
    }

    /**
     * Enable drag functionality for a detached popover
     * @param {HTMLElement} popover - The popover element
     */
    function enableDragging(popover) {
        const popoverId = popover.id;
        const nav = popover.querySelector('.inspekt-axe-nav');
        if (!nav) return;

        const onMouseDown = (e) => {
            if (!popoverState.detachedState.isDetached) return;

            popoverState.detachedState.isDragging = true;
            popoverState.detachedState.offsetX = e.clientX - parseFloat(popover.style.left);
            popoverState.detachedState.offsetY = e.clientY - parseFloat(popover.style.top);
            popover.classList.add('inspekt-axe-popover--dragging');
            e.preventDefault();
        };

        const onMouseMove = (e) => {
            if (!popoverState.detachedState.isDetached || !popoverState.detachedState.isDragging) return;

            popoverState.detachedState.x = e.clientX - popoverState.detachedState.offsetX;
            popoverState.detachedState.y = e.clientY - popoverState.detachedState.offsetY;
            popover.style.left = popoverState.detachedState.x + 'px';
            popover.style.top = popoverState.detachedState.y + 'px';
        };

        const onMouseUp = () => {
            if (!popoverState.detachedState.isDetached) return;

            popoverState.detachedState.isDragging = false;
            popover.classList.remove('inspekt-axe-popover--dragging');
        };

        const onTouchStart = (e) => {
            if (!popoverState.detachedState.isDetached) return;

            const touch = e.touches[0];
            popoverState.detachedState.isDragging = true;
            popoverState.detachedState.offsetX = touch.clientX - parseFloat(popover.style.left);
            popoverState.detachedState.offsetY = touch.clientY - parseFloat(popover.style.top);
            popover.classList.add('inspekt-axe-popover--dragging');
            e.preventDefault();
        };

        const onTouchMove = (e) => {
            if (!popoverState.detachedState.isDetached || !popoverState.detachedState.isDragging) return;

            const touch = e.touches[0];
            popoverState.detachedState.x = touch.clientX - popoverState.detachedState.offsetX;
            popoverState.detachedState.y = touch.clientY - popoverState.detachedState.offsetY;
            popover.style.left = popoverState.detachedState.x + 'px';
            popover.style.top = popoverState.detachedState.y + 'px';
            e.preventDefault();
        };

        const onTouchEnd = () => {
            if (!popoverState.detachedState.isDetached) return;

            popoverState.detachedState.isDragging = false;
            popover.classList.remove('inspekt-axe-popover--dragging');
        };

        // Store listeners for cleanup
        nav._dragListeners = { mousedown: onMouseDown, touchstart: onTouchStart };
        document._dragListeners = document._dragListeners || {};
        document._dragListeners[popoverId] = {
            mousemove: onMouseMove,
            mouseup: onMouseUp,
            touchmove: onTouchMove,
            touchend: onTouchEnd
        };

        nav.addEventListener('mousedown', onMouseDown);
        nav.addEventListener('touchstart', onTouchStart);
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd);
    }

    /**
     * Disable drag functionality for a popover
     * @param {HTMLElement} popover - The popover element
     */
    function disableDragging(popover) {
        const popoverId = popover.id;
        const nav = popover.querySelector('.inspekt-axe-nav');

        if (nav && nav._dragListeners) {
            nav.removeEventListener('mousedown', nav._dragListeners.mousedown);
            nav.removeEventListener('touchstart', nav._dragListeners.touchstart);
            delete nav._dragListeners;
        }

        if (document._dragListeners && document._dragListeners[popoverId]) {
            const listeners = document._dragListeners[popoverId];
            document.removeEventListener('mousemove', listeners.mousemove);
            document.removeEventListener('mouseup', listeners.mouseup);
            document.removeEventListener('touchmove', listeners.touchmove);
            document.removeEventListener('touchend', listeners.touchend);
            delete document._dragListeners[popoverId];
        }
    }

    // ============================================================
    // POPOVER OPEN HANDLER
    // ============================================================

    /**
     * Handle popover open event to update current index
     * @param {HTMLElement} popover - The popover element
     */
    function handlePopoverOpen(popover) {
        const popoverId = popover.id;
        const violationIndex = popoverState.violations.findIndex(v => v.popoverId === popoverId);
        if (violationIndex >= 0) {
            popoverState.currentIndex = violationIndex;
            updateNavigationControls(popover);
        }

        // Restore detached state if enabled
        if (popoverState.detachedState.isDetached) {
            const detachButton = popover.querySelector('.inspekt-axe-nav__detach');
            popover.classList.add('inspekt-axe-popover--detached');
            popover.style.left = popoverState.detachedState.x + 'px';
            popover.style.top = popoverState.detachedState.y + 'px';
            if (detachButton) {
                detachButton.classList.add('inspekt-axe-nav__detach--active');
                detachButton.setAttribute('aria-pressed', 'true');
                detachButton.title = 'Reattach popover to badge';
            }
            enableDragging(popover);
        }
    }

    // ============================================================
    // VIOLATION MANAGEMENT
    // ============================================================

    /**
     * Add a violation to the unified state
     * @param {Object} violation - Unified violation object with:
     *   - index: number
     *   - badgeId: string
     *   - popoverId: string
     *   - element: DOM element
     *   - sources: { axe: [...], ibm: [...] }
     *   - highestImpact: string
     */
    function addViolation(violation) {
        popoverState.violations.push(violation);
    }

    /**
     * Clear all violations (for fresh audit)
     */
    function clearViolations() {
        popoverState.violations = [];
        popoverState.currentIndex = -1;
        // Clear all engine Sets dynamically
        for (const engineId of popoverState.activeEngines) {
            if (popoverState.skippedRuleIds[engineId]) {
                popoverState.skippedRuleIds[engineId].clear();
            }
        }
    }

    /**
     * Get all violations
     * @returns {Array} All violations
     */
    function getViolations() {
        return popoverState.violations;
    }

    /**
     * Get violation count
     * @returns {number} Number of violations
     */
    function getViolationCount() {
        return popoverState.violations.length;
    }

    // ============================================================
    // RESET STATE
    // ============================================================

    /**
     * Reset the popover state (for new audit)
     * @param {Array} engines - Optional list of engine IDs to reinitialize
     */
    function reset(engines) {
        popoverState.violations = [];
        popoverState.currentIndex = -1;
        popoverState.detachedState.isDetached = false;
        popoverState.detachedState.isDragging = false;
        // Reinitialize skipped rule IDs for engines
        if (engines) {
            initSkippedRuleIds(engines);
        } else {
            // Clear existing Sets
            for (const engineId of popoverState.activeEngines) {
                if (popoverState.skippedRuleIds[engineId]) {
                    popoverState.skippedRuleIds[engineId].clear();
                }
            }
        }
    }

    // ============================================================
    // PUBLIC API
    // ============================================================

    window.__inspektPopoverCore__ = {
        // State
        state: popoverState,

        // Helpers
        escapeHtml,

        // Engine initialization
        initSkippedRuleIds,

        // Violation management
        addViolation,
        clearViolations,
        getViolations,
        getViolationCount,
        getViolationByIndex,
        getCurrentViolationIndex,

        // Navigation
        navigateToViolation,
        getNextViolationIndex,
        getPreviousViolationIndex,
        updateNavigationControls,

        // Skip similar
        toggleSkipSimilar,
        toggleSkipRule,
        shouldSkipViolation,
        updateBadgeDimming,

        // Detach/drag
        toggleDetach,
        enableDragging,
        disableDragging,
        handlePopoverOpen,

        // Reset
        reset
    };

})();
