// Inspekt Axe-core Accessibility Audit Script with Integrated Badge Injection
// Note: axe-core library is injected before this script executes
(async function() {
    try {
        // Verify axe-core is available (it should be loaded before this script)
        if (typeof axe === 'undefined') {
            throw new Error('axe-core library not found - this should not happen');
        }

        // Configuration object injected from Python
        // Will be replaced with actual config via string substitution
        const config = __AXE_CONFIG__;

        // Enable elementRef to get actual DOM node references
        config.elementRef = true;

        // Get show-badges and interactive flags from config (injected by Python)
        const showBadges = config.__showBadges !== false;  // Default true
        const interactiveBadges = config.__interactiveBadges === true;  // Default false
        const devCss = config.__devCss === true;  // Dev mode: load CSS from external server

        // Debug logging for dev mode
        console.log('[Inspekt] Config flags:', {
            showBadges,
            interactiveBadges,
            devCss,
            raw__devCss: config.__devCss
        });

        delete config.__showBadges;  // Don't pass this to axe
        delete config.__interactiveBadges;  // Don't pass this to axe
        delete config.__devCss;  // Don't pass this to axe

        // Global state for popover navigation and management (must be declared early)
        const popoverState = {
            violations: [],           // Array of {index, badgeId, popoverId, ruleId, violation, node}
            currentIndex: -1,         // Currently displayed violation index
            skippedRuleIds: new Set(), // Set of rule IDs that are hidden via "Skip similar"
            detachedState: {          // Global detached state for ALL popovers
                isDetached: false,
                x: 0,
                y: 0,
                isDragging: false,
                offsetX: 0,
                offsetY: 0
            }
        };

        // ============================================================
        // CSS HOT-RELOAD FOR DEV MODE
        // ============================================================

        /**
         * CSS Hot-Reload for dev mode
         * Polls the CSS file and automatically reloads when it changes
         */
        class CSSHotReloader {
            constructor(cssUrl, pollInterval = 1500) {
                this.cssUrl = cssUrl;
                this.pollInterval = pollInterval;
                this.lastModified = null;
                this.intervalId = null;
                this.linkElement = null;
                // Error tracking
                this.consecutiveFailures = 0;
                this.maxFailuresBeforeWarning = 3;
                this.hasWarnedAboutServer = false;
            }

            async start(linkElement) {
                this.linkElement = linkElement;

                // Verify server is reachable before starting
                try {
                    const response = await fetch(this.cssUrl, { method: 'HEAD' });
                    if (!response.ok) {
                        console.warn('%c[Inspekt Dev Mode]%c CSS server returned error. Check server is running: npm run dev:axe-css',
                            'color: #f59e0b; font-weight: bold', 'color: inherit');
                    } else {
                        this.lastModified = response.headers.get('Last-Modified');
                    }
                } catch (error) {
                    console.warn('%c[Inspekt Dev Mode]%c Cannot reach CSS server at %s\n  Start server: npm run dev:axe-css',
                        'color: #f59e0b; font-weight: bold', 'color: inherit', this.cssUrl);
                }

                console.log(`%c[Inspekt Dev Mode]%c CSS hot-reload started (checking every ${this.pollInterval/1000}s)`,
                    'color: #10b981; font-weight: bold', 'color: inherit');

                // Start polling (continues even if initial check failed - server might start later)
                this.intervalId = setInterval(() => this.checkForUpdates(), this.pollInterval);
            }

            stop() {
                if (this.intervalId) {
                    clearInterval(this.intervalId);
                    this.intervalId = null;
                    console.log('%c[Inspekt Dev Mode]%c CSS hot-reload stopped',
                        'color: #10b981; font-weight: bold', 'color: inherit');
                }
            }

            async checkForUpdates() {
                try {
                    // Add cache-busting query param to prevent browser caching HEAD responses
                    const url = `${this.cssUrl}?_=${Date.now()}`;
                    const response = await fetch(url, { method: 'HEAD', cache: 'no-store' });

                    // Reset failure counter on success
                    this.consecutiveFailures = 0;
                    this.hasWarnedAboutServer = false;

                    const lastModified = response.headers.get('Last-Modified');

                    if (this.lastModified && lastModified !== this.lastModified) {
                        this.reloadCSS();
                        console.log(`%c[Inspekt Dev Mode]%c CSS reloaded at ${new Date().toLocaleTimeString()}`,
                            'color: #10b981; font-weight: bold', 'color: inherit');
                    }

                    this.lastModified = lastModified;
                } catch (error) {
                    this.consecutiveFailures++;

                    // Warn once after 3 consecutive failures
                    if (this.consecutiveFailures >= this.maxFailuresBeforeWarning && !this.hasWarnedAboutServer) {
                        this.hasWarnedAboutServer = true;
                        console.warn('%c[Inspekt Dev Mode]%c CSS server not responding. Is it running? Start with: npm run dev:axe-css',
                            'color: #f59e0b; font-weight: bold', 'color: inherit');
                    }
                }
            }

            reloadCSS() {
                if (this.linkElement) {
                    const baseHref = this.linkElement.href.split('?')[0];
                    this.linkElement.href = `${baseHref}?v=${Date.now()}`;
                }
            }
        }

        // ============================================================
        // HELPER FUNCTIONS (must be defined before they are called)
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
         * Get next non-skipped violation index
         * @param {boolean} skipSimilar - Whether to skip violations with skipped rule IDs
         * @returns {number} Next index or -1 if none
         */
        function getNextViolationIndex(skipSimilar) {
            let current = popoverState.currentIndex;
            let totalViolations = popoverState.violations.length;

            if (totalViolations === 0) return -1;

            for (let i = 1; i <= totalViolations; i++) {
                let nextIndex = (current + i) % totalViolations;
                let violation = popoverState.violations[nextIndex];

                if (!skipSimilar || !popoverState.skippedRuleIds.has(violation.ruleId)) {
                    return nextIndex;
                }
            }

            return -1; // All violations are skipped
        }

        /**
         * Get previous non-skipped violation index
         * @param {boolean} skipSimilar - Whether to skip violations with skipped rule IDs
         * @returns {number} Previous index or -1 if none
         */
        function getPreviousViolationIndex(skipSimilar) {
            let current = popoverState.currentIndex;
            let totalViolations = popoverState.violations.length;

            if (totalViolations === 0) return -1;

            for (let i = 1; i <= totalViolations; i++) {
                let prevIndex = (current - i + totalViolations) % totalViolations;
                let violation = popoverState.violations[prevIndex];

                if (!skipSimilar || !popoverState.skippedRuleIds.has(violation.ruleId)) {
                    return prevIndex;
                }
            }

            return -1; // All violations are skipped
        }

        /**
         * Toggle skip similar for current violation's rule
         * @returns {boolean} New skip state (true if now skipped)
         */
        function toggleSkipSimilar() {
            if (popoverState.currentIndex === -1) return false;

            const currentViolation = popoverState.violations[popoverState.currentIndex];
            const ruleId = currentViolation.ruleId;

            if (popoverState.skippedRuleIds.has(ruleId)) {
                popoverState.skippedRuleIds.delete(ruleId);
                return false;
            } else {
                popoverState.skippedRuleIds.add(ruleId);
                return true;
            }
        }

        /**
         * Apply dimming to badges based on skipped rules
         */
        function updateBadgeDimming() {
            popoverState.violations.forEach(v => {
                const badge = document.getElementById(v.badgeId);
                if (badge) {
                    if (popoverState.skippedRuleIds.has(v.ruleId)) {
                        badge.classList.add('inspekt-axe-badge--dimmed');
                        badge.disabled = true;
                    } else {
                        badge.classList.remove('inspekt-axe-badge--dimmed');
                        badge.disabled = false;
                    }
                }
            });
        }

        /**
         * Navigate to a violation by index
         * @param {number} targetIndex - Index to navigate to
         */
        async function navigateToViolation(targetIndex) {
            if (targetIndex < 0 || targetIndex >= popoverState.violations.length) return;

            const targetViolation = popoverState.violations[targetIndex];
            if (!targetViolation) return;

            const currentIndex = popoverState.currentIndex;
            const targetPopover = document.getElementById(targetViolation.popoverId);

            // If no current popover or detached mode, navigate instantly (no transition)
            if (currentIndex < 0 || popoverState.detachedState.isDetached) {
                // Instant navigation (original behavior)
                if (currentIndex >= 0) {
                    const currentViolation = popoverState.violations[currentIndex];
                    if (currentViolation) {
                        const currentPopover = document.getElementById(currentViolation.popoverId);
                        if (currentPopover) {
                            currentPopover.hidePopover();
                        }
                    }
                }

                popoverState.currentIndex = targetIndex;
                if (targetPopover) {
                    targetPopover.showPopover();
                    updateNavigationControls(targetPopover);
                }
                return;
            }

            // Directional transition (only in attached mode)
            const currentViolation = popoverState.violations[currentIndex];
            if (!currentViolation) return;

            const currentPopover = document.getElementById(currentViolation.popoverId);
            if (!currentPopover) return;

            // Get badges to calculate direction
            const currentBadge = document.getElementById(currentViolation.badgeId);
            const targetBadge = document.getElementById(targetViolation.badgeId);

            if (!currentBadge || !targetBadge) {
                // Fallback to instant if badges not found
                currentPopover.hidePopover();
                popoverState.currentIndex = targetIndex;
                if (targetPopover) {
                    targetPopover.showPopover();
                    updateNavigationControls(targetPopover);
                }
                return;
            }

            // Calculate direction
            const direction = calculateDirection(currentBadge, targetBadge);
            const oppositeDirection = getOppositeDirection(direction);

            // Apply exit animation to current popover
            currentPopover.classList.add(`exit-${direction}`);

            // Wait for exit animation to complete (with timeout fallback)
            await new Promise(resolve => {
                let resolved = false;
                const timeoutId = setTimeout(() => {
                    if (!resolved) {
                        resolved = true;
                        currentPopover.removeEventListener('animationend', onAnimationEnd);
                        resolve();
                    }
                }, 200); // 200ms fallback (slightly longer than 150ms animation)

                const onAnimationEnd = (e) => {
                    // Only handle animations on the popover itself (not child elements)
                    if (e.target !== currentPopover) return;
                    // Only handle our exit animations
                    if (!e.animationName.startsWith('popoverExit')) return;

                    if (!resolved) {
                        resolved = true;
                        clearTimeout(timeoutId);
                        currentPopover.removeEventListener('animationend', onAnimationEnd);
                        resolve();
                    }
                };
                currentPopover.addEventListener('animationend', onAnimationEnd);
            });

            // Hide current popover and clean up
            currentPopover.hidePopover();
            currentPopover.classList.remove(`exit-${direction}`);

            // Update current index
            popoverState.currentIndex = targetIndex;

            // Show target popover with entry animation
            if (targetPopover) {
                // Add entry animation class before showing
                targetPopover.classList.add(`enter-from-${oppositeDirection}`);

                // Use double RAF for more reliable paint synchronization
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => {
                        // Show popover
                        targetPopover.showPopover();
                        updateNavigationControls(targetPopover);

                        // Wait for entry animation to complete (with timeout fallback)
                        let entryResolved = false;
                        const entryTimeoutId = setTimeout(() => {
                            if (!entryResolved) {
                                entryResolved = true;
                                targetPopover.removeEventListener('animationend', onEntryAnimationEnd);
                                targetPopover.classList.remove(`enter-from-${oppositeDirection}`);
                            }
                        }, 200);

                        const onEntryAnimationEnd = (e) => {
                            // Only handle animations on the popover itself
                            if (e.target !== targetPopover) return;
                            // Only handle our entry animations
                            if (!e.animationName.startsWith('popoverEnterFrom')) return;

                            if (!entryResolved) {
                                entryResolved = true;
                                clearTimeout(entryTimeoutId);
                                targetPopover.removeEventListener('animationend', onEntryAnimationEnd);
                                targetPopover.classList.remove(`enter-from-${oppositeDirection}`);
                            }
                        };
                        targetPopover.addEventListener('animationend', onEntryAnimationEnd);
                    });
                });
            }
        }

        /**
         * Update navigation button states and counter
         * @param {HTMLElement} popover - The popover element
         */
        function updateNavigationControls(popover) {
            const prevBtn = popover.querySelector('.inspekt-axe-nav__prev');
            const nextBtn = popover.querySelector('.inspekt-axe-nav__next');
            const counter = popover.querySelector('.inspekt-axe-nav__counter');
            const skipBtn = popover.querySelector('.inspekt-axe-nav__skip-similar');

            const total = popoverState.violations.length;
            const current = popoverState.currentIndex + 1; // 1-based for display

            // Update counter (compact format)
            if (counter) {
                counter.textContent = `${current}/${total}`;
            }

            // Check if we can navigate (considering skip similar state)
            const skipSimilarActive = popoverState.skippedRuleIds.size > 0;
            const canGoNext = getNextViolationIndex(skipSimilarActive) !== -1;
            const canGoPrev = getPreviousViolationIndex(skipSimilarActive) !== -1;

            // Update button states
            if (prevBtn) {
                prevBtn.disabled = !canGoPrev;
            }
            if (nextBtn) {
                nextBtn.disabled = !canGoNext;
            }

            // Update skip similar button state
            if (skipBtn) {
                const currentViolation = popoverState.violations[popoverState.currentIndex];
                const isSkipped = popoverState.skippedRuleIds.has(currentViolation.ruleId);
                if (isSkipped) {
                    skipBtn.classList.add('inspekt-axe-nav__skip-similar--active');
                    skipBtn.setAttribute('aria-pressed', 'true');
                } else {
                    skipBtn.classList.remove('inspekt-axe-nav__skip-similar--active');
                    skipBtn.setAttribute('aria-pressed', 'false');
                }
            }
        }

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

            // Restore global detached state if enabled
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

        /**
         * Toggle detach/reattach state for ALL popovers (global state)
         * @param {HTMLElement} popover - The popover element
         */
        function toggleDetach(popover) {
            const detachButton = popover.querySelector('.inspekt-axe-nav__detach');
            const isDetached = popoverState.detachedState.isDetached;

            if (isDetached) {
                // Reattach: Remove detached state and re-enable anchor positioning
                popoverState.detachedState.isDetached = false;
                popover.classList.remove('inspekt-axe-popover--detached');
                popover.style.left = '';
                popover.style.top = '';
                detachButton.classList.remove('inspekt-axe-nav__detach--active');
                detachButton.setAttribute('aria-pressed', 'false');
                detachButton.title = 'Detach popover (drag freely on page)';
                disableDragging(popover);
            } else {
                // Detach: Save current position and enable manual positioning for ALL popovers
                const rect = popover.getBoundingClientRect();
                popoverState.detachedState.isDetached = true;
                popoverState.detachedState.x = rect.left;
                popoverState.detachedState.y = rect.top;
                popoverState.detachedState.isDragging = false;
                popoverState.detachedState.offsetX = 0;
                popoverState.detachedState.offsetY = 0;
                popover.classList.add('inspekt-axe-popover--detached');
                popover.style.left = rect.left + 'px';
                popover.style.top = rect.top + 'px';
                detachButton.classList.add('inspekt-axe-nav__detach--active');
                detachButton.setAttribute('aria-pressed', 'true');
                detachButton.title = 'Reattach popover to badge';
                enableDragging(popover);
            }
        }

        /**
         * Enable drag functionality for a detached popover (uses global state)
         * @param {HTMLElement} popover - The popover element
         */
        function enableDragging(popover) {
            const popoverId = popover.id;
            const nav = popover.querySelector('.inspekt-axe-nav');

            // Mouse events
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

            // Touch events
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

            // Store event listeners on the element for cleanup
            nav._dragListeners = {
                mousedown: onMouseDown,
                touchstart: onTouchStart
            };

            document._dragListeners = document._dragListeners || {};
            document._dragListeners[popoverId] = {
                mousemove: onMouseMove,
                mouseup: onMouseUp,
                touchmove: onTouchMove,
                touchend: onTouchEnd
            };

            // Attach listeners
            nav.addEventListener('mousedown', onMouseDown);
            nav.addEventListener('touchstart', onTouchStart);
            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
            document.addEventListener('touchmove', onTouchMove, { passive: false });
            document.addEventListener('touchend', onTouchEnd);
        }

        /**
         * Disable drag functionality for a popover (cleanup event listeners)
         * @param {HTMLElement} popover - The popover element
         */
        function disableDragging(popover) {
            const popoverId = popover.id;
            const nav = popover.querySelector('.inspekt-axe-nav');

            if (nav._dragListeners) {
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

        /**
         * Calculate direction from current badge to target badge
         * @param {HTMLElement} currentBadge - Current badge element
         * @param {HTMLElement} targetBadge - Target badge element
         * @returns {string} Direction string (up, down, left, right, up-left, up-right, down-left, down-right)
         */
        function calculateDirection(currentBadge, targetBadge) {
            const currentRect = currentBadge.getBoundingClientRect();
            const targetRect = targetBadge.getBoundingClientRect();

            // Calculate center points
            const currentX = currentRect.left + currentRect.width / 2;
            const currentY = currentRect.top + currentRect.height / 2;
            const targetX = targetRect.left + targetRect.width / 2;
            const targetY = targetRect.top + targetRect.height / 2;

            // Calculate deltas
            const deltaX = targetX - currentX;
            const deltaY = targetY - currentY;

            const absDeltaX = Math.abs(deltaX);
            const absDeltaY = Math.abs(deltaY);

            // Determine direction based on deltas
            // Pure horizontal if X delta is significantly larger than Y
            if (absDeltaX > absDeltaY * 2) {
                return deltaX > 0 ? 'right' : 'left';
            }

            // Pure vertical if Y delta is significantly larger than X
            if (absDeltaY > absDeltaX * 2) {
                return deltaY > 0 ? 'down' : 'up';
            }

            // Diagonal directions
            if (deltaY < 0) {
                // Moving up
                return deltaX > 0 ? 'up-right' : 'up-left';
            } else {
                // Moving down
                return deltaX > 0 ? 'down-right' : 'down-left';
            }
        }

        /**
         * Get opposite direction for entry animation
         * @param {string} exitDirection - Exit direction
         * @returns {string} Opposite direction for entry
         */
        function getOppositeDirection(exitDirection) {
            const opposites = {
                'up': 'down',
                'down': 'up',
                'left': 'right',
                'right': 'left',
                'up-left': 'down-right',
                'up-right': 'down-left',
                'down-left': 'up-right',
                'down-right': 'up-left'
            };
            return opposites[exitDirection] || 'down';
        }

        /**
         * Generate Markdown content from violation data
         * @param {number} badgeNumber - The badge number
         * @param {Object} violation - The axe violation object
         * @param {Object} node - The specific node data from the violation
         * @returns {string} Markdown formatted content
         */
        function generateMarkdown(badgeNumber, violation, node) {
            const impact = violation.impact || node.impact || 'minor';
            const impactLabel = impact.charAt(0).toUpperCase() + impact.slice(1);

            let markdown = `# Accessibility Violation #${badgeNumber}\n\n`;
            markdown += `**Impact:** ${impactLabel}\n\n`;
            markdown += `## ${violation.help}\n\n`;
            markdown += `${violation.description}\n\n`;

            // Failure Summary
            if (node.failureSummary) {
                markdown += `### What's Wrong\n\n`;
                markdown += `${node.failureSummary}\n\n`;
            }

            // HTML Snippet
            if (node.html) {
                markdown += `### HTML Snippet\n\n`;
                markdown += `\`\`\`html\n${node.html}\n\`\`\`\n\n`;
            }

            // CSS Selector
            if (node.target && node.target.length > 0) {
                const selectorText = Array.isArray(node.target) ? node.target.join(', ') : node.target;
                markdown += `### CSS Selector\n\n`;
                markdown += `\`${selectorText}\`\n\n`;
            }

            // Fix Details
            if (node.any || node.all || node.none) {
                markdown += `### Fix Details\n\n`;

                if (node.all && node.all.length > 0) {
                    markdown += `#### Required Fixes (all must pass):\n\n`;
                    node.all.forEach((check, idx) => {
                        const status = check.result ? '✓' : '✗';
                        markdown += `${idx + 1}. ${status} ${check.message}\n`;
                    });
                    markdown += `\n`;
                }

                if (node.any && node.any.length > 0) {
                    markdown += `#### Possible Fixes (at least one must pass):\n\n`;
                    node.any.forEach((check, idx) => {
                        const status = check.result ? '✓' : '✗';
                        markdown += `${idx + 1}. ${status} ${check.message}\n`;
                    });
                    markdown += `\n`;
                }

                if (node.none && node.none.length > 0) {
                    markdown += `#### Must Not Occur:\n\n`;
                    node.none.forEach((check, idx) => {
                        const status = check.result ? '✓' : '✗';
                        markdown += `${idx + 1}. ${status} ${check.message}\n`;
                    });
                    markdown += `\n`;
                }
            }

            // WCAG Tags
            if (violation.tags && violation.tags.length > 0) {
                markdown += `### Standards\n\n`;
                markdown += violation.tags.join(', ') + '\n\n';
            }

            // Learn More Link
            if (violation.helpUrl) {
                markdown += `### Learn More\n\n`;
                markdown += `[Deque University - ${violation.id}](${violation.helpUrl})\n`;
            }

            return markdown;
        }

        /**
         * Returns the CSS for interactive popovers.
         * This is the minified content from axe-popover/index.css
         * To update: minify the modular CSS files and paste here.
         * @returns {string} CSS content
         */
        function getPopoverCSS() {
            return `@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap");:root{--gray-50:#f9fafb;--gray-100:#f3f4f6;--gray-200:#e5e7eb;--gray-300:#d1d5db;--gray-400:#9ca3af;--gray-500:#6b7280;--gray-600:#4b5563;--gray-700:#374151;--gray-800:#1f2937;--gray-900:#111827;--blue:#2563eb;--blue-light:#60a5fa;--blue-bg:#eff6ff;--green:#10b981;--green-bg:#f0fdf4;--red:#dc2626;--red-bg:#fef2f2;--orange:#ea580c;--color-text:var(--gray-800);--color-text-muted:var(--gray-500);--color-text-inverse:#ffffff;--color-bg:rgba(255,255,255,0.75);--color-bg-subtle:var(--gray-50);--color-border:var(--gray-200);--color-primary:var(--blue);--impact-critical:var(--red);--impact-serious:var(--orange);--impact-moderate:var(--blue);--impact-minor:var(--gray-500);--font-sans:"Inter",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;--font-mono:ui-monospace,SFMono-Regular,monospace;--text-xs:11px;--text-sm:13px;--text-base:14px;--text-lg:16px;--space-sm:4px;--space-md:8px;--space-lg:16px;--radius-sm:4px;--radius-md:8px;--radius-lg:12px;--shadow-popover:0 20px 60px rgba(0,0,0,0.12),0 8px 20px rgba(0,0,0,0.08);--shadow-badge:0 3px 6px rgba(0,0,0,0.5);--popover-max-width:480px;--popover-min-width:380px;--popover-max-height:80vh;--nav-button-size:28px;--transition-fast:0.15s ease;--transition-base:0.2s ease;--animation-duration:0.15s;--animation-distance:20px;--blur-popover:blur(20px)saturate(180%)}[popover].inspekt-axe-popover{position:absolute;margin:0;inset:unset;position-area:block-end span-inline-end;position-try-fallbacks:--bottom-left,--top-right,--top-left,flip-block,flip-inline;max-width:var(--popover-max-width);min-width:var(--popover-min-width);max-height:var(--popover-max-height);width:max-content;background:var(--color-bg);border:2px solid var(--color-border);border-radius:var(--radius-lg);box-shadow:var(--shadow-popover);backdrop-filter:var(--blur-popover);-webkit-backdrop-filter:var(--blur-popover);font-family:var(--font-sans);font-size:var(--text-lg);line-height:1.5;color:var(--color-text);padding:0;overflow:hidden;overscroll-behavior:contain;transition:opacity var(--transition-base),box-shadow var(--transition-base);&:popover-open{animation:popoverFadeIn var(--animation-duration)ease-out}}@position-try --bottom-left{position-area:block-end span-inline-start}@position-try --top-right{position-area:block-start span-inline-end}@position-try --top-left{position-area:block-start span-inline-start}[popover].inspekt-axe-popover--detached{position:fixed;position-anchor:unset;position-area:unset;position-try-fallbacks:unset;inset:unset;border-color:var(--green);box-shadow:0 25px 70px rgba(0,0,0,0.15),0 10px 25px rgba(0,0,0,0.1)}[popover].inspekt-axe-popover--dragging{cursor:grabbing !important;user-select:none;opacity:0.5 !important;box-shadow:0 30px 80px rgba(0,0,0,0.2),0 12px 30px rgba(0,0,0,0.15)!important;& *{cursor:grabbing !important;user-select:none}}.inspekt-axe-popover__body{&::-webkit-scrollbar{width:8px}&::-webkit-scrollbar-track{background:var(--gray-50)}&::-webkit-scrollbar-thumb{background:var(--gray-300);border-radius:var(--radius-sm);&:hover{background:var(--gray-400)}}}.inspekt-axe-nav{display:flex;align-items:center;justify-content:space-between;gap:var(--space-sm);min-height:40px;padding:var(--space-md)var(--space-lg);background:rgba(31,41,55,0.9);backdrop-filter:blur(10px);border-bottom:1px solid rgba(255,255,255,0.1);border-radius:var(--radius-lg)var(--radius-lg)0 0}.inspekt-axe-nav__group{display:flex;align-items:center;gap:var(--space-sm);flex-shrink:0}.inspekt-axe-nav__drag-handle{display:none}.inspekt-axe-popover--detached .inspekt-axe-nav__drag-handle{display:flex;align-items:center;gap:var(--space-sm);padding:2px var(--space-sm);border-radius:var(--radius-sm);background:rgba(255,255,255,0.05);cursor:grab}.inspekt-axe-nav__grip{display:flex;color:rgba(255,255,255,0.4)}.inspekt-axe-nav__drag-label{font-size:9px;font-weight:600;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:0.5px;user-select:none}.inspekt-axe-nav__counter{min-width:36px;padding:0 2px;text-align:center;font-size:var(--text-sm);font-weight:600;font-variant-numeric:tabular-nums;color:rgba(255,255,255,0.7)}.inspekt-axe-nav__prev,.inspekt-axe-nav__next,.inspekt-axe-nav__detach,.inspekt-axe-nav__close{width:var(--nav-button-size);height:var(--nav-button-size);padding:0;flex-shrink:0;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:var(--radius-md);color:rgba(255,255,255,0.85);cursor:pointer;transition:all var(--transition-fast);&:hover:not(:disabled){background:rgba(255,255,255,0.15);border-color:rgba(255,255,255,0.25);color:white}&:active:not(:disabled){transform:scale(0.95)}&:focus-visible{outline:2px solid var(--blue-light);outline-offset:2px}&:disabled{opacity:0.3;cursor:not-allowed}}.inspekt-axe-nav__close{border-radius:50%;background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.25);color:#fca5a5;&:hover{background:rgba(239,68,68,0.3);border-color:rgba(239,68,68,0.5);color:#fef2f2}}.inspekt-axe-nav__skip-similar{height:var(--nav-button-size);padding:0 var(--space-md);flex-shrink:0;white-space:nowrap;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:var(--radius-md);font-size:var(--text-xs);font-weight:500;color:rgba(255,255,255,0.85);cursor:pointer;transition:all var(--transition-fast);&:hover{background:rgba(255,255,255,0.15);border-color:rgba(255,255,255,0.25);color:white}&:active{transform:scale(0.97)}&:focus-visible{outline:2px solid var(--blue-light);outline-offset:2px}}.inspekt-axe-nav__skip-similar--active{background:var(--blue);border-color:var(--blue);color:white;&:hover{background:#1d4ed8;border-color:#1d4ed8}}.inspekt-axe-nav__detach--active{background:var(--green);border-color:var(--green);color:white;&:hover{background:#059669;border-color:#059669}}.inspekt-axe-popover--detached .inspekt-axe-nav{cursor:grab}.inspekt-axe-popover--dragging .inspekt-axe-nav{cursor:grabbing !important}.inspekt-axe-popover__header{display:flex;align-items:flex-start;gap:var(--space-lg);padding:var(--space-lg);border-bottom:1px solid var(--color-border)}.inspekt-axe-popover__title{flex:1;margin:0;font-size:var(--text-base);font-weight:600;line-height:1.4;color:var(--color-text)}.inspekt-axe-popover__impact-badge{flex-shrink:0;padding:5px 11px;border-radius:var(--radius-md);font-size:var(--text-xs);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-inverse)}.inspekt-axe-popover__impact-badge--critical{background:var(--impact-critical)}.inspekt-axe-popover__impact-badge--serious{background:var(--impact-serious)}.inspekt-axe-popover__impact-badge--moderate{background:var(--impact-moderate)}.inspekt-axe-popover__impact-badge--minor{background:var(--impact-minor)}.inspekt-axe-popover__tablist{display:flex;gap:0;padding:0 var(--space-lg);background:var(--gray-50);border-bottom:1px solid var(--color-border)}.inspekt-axe-popover__tab{position:relative;top:1px;padding:var(--space-md)var(--space-lg);background:transparent;border:none;border-bottom:2px solid transparent;font-size:var(--text-base);font-weight:500;color:var(--color-text-muted);cursor:pointer;transition:all var(--transition-base);&:hover{color:var(--gray-600);background:rgba(0,0,0,0.02)}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:-2px}}.inspekt-axe-popover__tab--active{color:var(--color-primary);border-bottom-color:var(--color-primary);background:white}.inspekt-axe-popover__tabpanel[hidden]{display:none}.inspekt-axe-popover__markdown-panel{padding:0;overflow:hidden}.inspekt-axe-popover__markdown-textarea{width:100%;height:400px;max-height:calc(80vh - 200px);padding:var(--space-lg);background:white;border:none;outline:none;resize:vertical;overflow-y:auto;font-family:var(--font-mono);font-size:var(--text-sm);line-height:1.6;color:var(--color-text);&::selection{background:#bfdbfe}}.inspekt-axe-popover__body{padding:var(--space-lg);max-height:calc(80vh - 150px);overflow-y:auto}.inspekt-axe-popover__section{margin-bottom:var(--space-lg);&:last-child{margin-bottom:0}}.inspekt-axe-popover__section-label{display:block;margin-bottom:var(--space-sm);font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-muted)}.inspekt-axe-popover__section-content{font-size:var(--text-sm);line-height:1.6;color:var(--gray-600)}.inspekt-axe-popover__failure-summary{padding:var(--space-md);background:var(--red-bg);border-radius:var(--radius-md);font-size:var(--text-sm);line-height:1.6;color:#991b1b}.inspekt-axe-popover__code{padding:var(--space-md);background:var(--gray-50);border:1px solid var(--color-border);border-radius:var(--radius-md);overflow-x:auto;font-family:var(--font-mono);font-size:var(--text-sm);line-height:1.5;color:var(--color-text);white-space:pre-wrap;word-wrap:break-word}.inspekt-axe-popover__selector{padding:var(--space-sm)var(--space-md);background:var(--blue-bg);border:1px solid #bfdbfe;border-radius:var(--radius-md);overflow-x:auto;font-family:var(--font-mono);font-size:var(--text-sm);color:#1e40af;word-wrap:break-word}.inspekt-axe-popover__details{border:1px solid var(--color-border);border-radius:var(--radius-md);overflow:hidden;& summary{display:flex;align-items:center;gap:var(--space-md);padding:var(--space-md);background:var(--gray-50);list-style:none;user-select:none;cursor:pointer;font-size:var(--text-sm);font-weight:500;color:var(--gray-600);&::-webkit-details-marker{display:none}&::before{content:"\\25B6";font-size:10px;color:var(--color-text-muted);transition:transform var(--transition-base)}&:hover{background:var(--gray-100)}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:-2px}}&[open] summary::before{transform:rotate(90deg)}}.inspekt-axe-popover__details-content{padding:var(--space-md);background:white}.inspekt-axe-popover__checks{margin-top:var(--space-md)}.inspekt-axe-popover__check-group{margin-bottom:var(--space-md);&:last-child{margin-bottom:0}}.inspekt-axe-popover__check-title{margin-bottom:var(--space-sm);font-size:var(--text-sm);font-weight:600;color:var(--gray-600)}.inspekt-axe-popover__check-list{list-style:none;padding:0;margin:0}.inspekt-axe-popover__check-item{margin-bottom:var(--space-sm);padding:var(--space-md);background:var(--gray-50);border-radius:var(--radius-sm);font-size:var(--text-sm)}.inspekt-axe-popover__check-item--pass{background:var(--green-bg);border-left-color:var(--green);color:#166534}.inspekt-axe-popover__check-item--fail{background:var(--red-bg);border-left-color:var(--red);color:#991b1b}.inspekt-axe-popover__check-message{display:block;margin-bottom:var(--space-sm);font-weight:500}.inspekt-axe-popover__check-data{display:block;font-size:var(--text-xs);color:var(--color-text-muted)}.inspekt-axe-popover__tags{display:flex;flex-wrap:wrap;gap:var(--space-sm);margin-top:var(--space-md)}.inspekt-axe-popover__tag{display:inline-block;padding:3px var(--space-md);background:var(--gray-100);border:1px solid var(--gray-300);border-radius:9999px;font-size:var(--text-xs);font-weight:500;color:var(--gray-600)}.inspekt-axe-popover__tag--wcag{background:var(--blue-bg);border-color:#bfdbfe;color:#1e40af}.inspekt-axe-popover__footer{padding:var(--space-lg);background:var(--gray-50);border-top:1px solid var(--color-border)}.inspekt-axe-popover__learn-more{display:inline-flex;align-items:center;gap:var(--space-sm);padding:var(--space-md)var(--space-lg);background:var(--color-primary);border-radius:var(--radius-md);text-decoration:none;font-size:var(--text-base);font-weight:500;color:var(--color-text-inverse);transition:background var(--transition-base);&:hover{background:#1d4ed8}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:2px}&::after{content:"\\2192"}}button.inspekt-axe-badge{pointer-events:auto;cursor:pointer;border:2px solid white;background:inherit;transition:transform var(--transition-fast),box-shadow var(--transition-fast);&:hover{transform:scale(1.1);box-shadow:var(--shadow-badge)}&:focus-visible{outline:3px solid var(--color-primary);outline-offset:2px;transform:scale(1.1)}&:active{transform:scale(0.95)}}@keyframes popoverFadeIn{from{opacity:0;transform:scale(0.95)}to{opacity:1;transform:scale(1)}}@keyframes popoverExitUp{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(calc(-1 * var(--animation-distance)))}}@keyframes popoverExitDown{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(var(--animation-distance))}}@keyframes popoverExitLeft{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(calc(-1 * var(--animation-distance)))}}@keyframes popoverExitRight{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(var(--animation-distance))}}@keyframes popoverExitUpLeft{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate(calc(-1 * var(--animation-distance)),calc(-1 * var(--animation-distance)))}}@keyframes popoverExitUpRight{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate(var(--animation-distance),calc(-1 * var(--animation-distance)))}}@keyframes popoverExitDownLeft{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate(calc(-1 * var(--animation-distance)),var(--animation-distance))}}@keyframes popoverExitDownRight{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate(var(--animation-distance),var(--animation-distance))}}@keyframes popoverEnterFromUp{from{opacity:0;transform:translateY(calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translateY(0)}}@keyframes popoverEnterFromDown{from{opacity:0;transform:translateY(var(--animation-distance))}to{opacity:1;transform:translateY(0)}}@keyframes popoverEnterFromLeft{from{opacity:0;transform:translateX(calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translateX(0)}}@keyframes popoverEnterFromRight{from{opacity:0;transform:translateX(var(--animation-distance))}to{opacity:1;transform:translateX(0)}}@keyframes popoverEnterFromUpLeft{from{opacity:0;transform:translate(calc(-1 * var(--animation-distance)),calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromUpRight{from{opacity:0;transform:translate(var(--animation-distance),calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromDownLeft{from{opacity:0;transform:translate(calc(-1 * var(--animation-distance)),var(--animation-distance))}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromDownRight{from{opacity:0;transform:translate(var(--animation-distance),var(--animation-distance))}to{opacity:1;transform:translate(0,0)}}[popover].inspekt-axe-popover{&.exit-up{animation:popoverExitUp var(--animation-duration)ease-out forwards}&.exit-down{animation:popoverExitDown var(--animation-duration)ease-out forwards}&.exit-left{animation:popoverExitLeft var(--animation-duration)ease-out forwards}&.exit-right{animation:popoverExitRight var(--animation-duration)ease-out forwards}&.exit-up-left{animation:popoverExitUpLeft var(--animation-duration)ease-out forwards}&.exit-up-right{animation:popoverExitUpRight var(--animation-duration)ease-out forwards}&.exit-down-left{animation:popoverExitDownLeft var(--animation-duration)ease-out forwards}&.exit-down-right{animation:popoverExitDownRight var(--animation-duration)ease-out forwards}&.enter-from-up{animation:popoverEnterFromUp var(--animation-duration)ease-out forwards}&.enter-from-down{animation:popoverEnterFromDown var(--animation-duration)ease-out forwards}&.enter-from-left{animation:popoverEnterFromLeft var(--animation-duration)ease-out forwards}&.enter-from-right{animation:popoverEnterFromRight var(--animation-duration)ease-out forwards}&.enter-from-up-left{animation:popoverEnterFromUpLeft var(--animation-duration)ease-out forwards}&.enter-from-up-right{animation:popoverEnterFromUpRight var(--animation-duration)ease-out forwards}&.enter-from-down-left{animation:popoverEnterFromDownLeft var(--animation-duration)ease-out forwards}&.enter-from-down-right{animation:popoverEnterFromDownRight var(--animation-duration)ease-out forwards}}@media(prefers-contrast:high){[popover].inspekt-axe-popover{border:2px solid currentColor}.inspekt-axe-popover__impact-badge{border:1px solid white}}@media(prefers-color-scheme:dark){:root{--color-text:var(--gray-50);--color-text-muted:var(--gray-400);--color-bg:rgba(31,41,55,0.75);--color-bg-subtle:var(--gray-900);--color-border:var(--gray-700);--green-bg:#14532d;--red-bg:#7f1d1d;--blue-bg:#1e3a5f}.inspekt-axe-popover__header{border-bottom-color:var(--gray-700)}.inspekt-axe-popover__tablist{border-bottom-color:var(--gray-700);background:rgba(17,24,39,0.5)}.inspekt-axe-popover__tab{color:var(--gray-400);&:hover{color:var(--gray-300);background:rgba(255,255,255,0.05)}}.inspekt-axe-popover__tab--active{color:var(--blue-light);border-bottom-color:var(--blue-light);background:rgba(31,41,55,0.5)}.inspekt-axe-popover__markdown-textarea{color:var(--gray-200);background:var(--gray-800)}.inspekt-axe-popover__details{& summary{background:var(--gray-900);color:var(--gray-200);&::before{color:var(--gray-400)}&:hover{background:var(--gray-800)}}}.inspekt-axe-popover__details-content{background:var(--gray-800)}.inspekt-axe-popover__check-item{background:var(--gray-900);border-left-color:var(--gray-600);color:var(--gray-300)}.inspekt-axe-popover__failure-summary{color:#fecaca}.inspekt-axe-popover__tag{background:var(--gray-700);border-color:var(--gray-600);color:var(--gray-300)}.inspekt-axe-popover__tag--wcag{background:var(--blue-bg);border-color:var(--blue);color:#93c5fd}.inspekt-axe-popover__selector{background:var(--blue-bg);border-color:var(--blue);color:#93c5fd}.inspekt-axe-popover__footer{border-top-color:var(--gray-700);background:rgba(17,24,39,0.5)}.inspekt-axe-popover__body{&::-webkit-scrollbar-track{background:var(--gray-900)}&::-webkit-scrollbar-thumb{background:var(--gray-600);&:hover{background:var(--gray-500)}}}.inspekt-axe-nav{background:rgba(17,24,39,0.85);border-bottom-color:rgba(17,24,39,0.3)}.inspekt-axe-nav__prev,.inspekt-axe-nav__next,.inspekt-axe-nav__detach{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover:not(:disabled){background:var(--gray-700);border-color:var(--gray-500)}}.inspekt-axe-nav__skip-similar{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover{background:var(--gray-700);border-color:var(--gray-500)}}.inspekt-axe-nav__skip-similar--active{background:var(--blue);border-color:var(--blue);color:white}.inspekt-axe-nav__close{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover{background:#7f1d1d;border-color:var(--red);color:#fecaca}}.inspekt-axe-nav__counter{color:var(--gray-400)}}`;
        }

        /**
         * Creates a popover element with detailed violation information.
         * @param {string} popoverId - Unique ID for the popover element
         * @param {string} badgeId - ID of the badge that triggers this popover
         * @param {number} badgeNumber - The badge number
         * @param {Object} violation - The axe violation object
         * @param {Object} node - The specific node data from the violation
         * @returns {HTMLElement} The popover element
         */
        function createPopover(popoverId, badgeId, badgeNumber, violation, node) {
            const popover = document.createElement('div');
            popover.id = popoverId;
            popover.setAttribute('popover', 'auto');
            popover.className = 'inspekt-axe-popover';
            popover.setAttribute('data-inspekt-axe-popover', badgeNumber);
            // Set position-anchor directly with a literal value (not via CSS custom property)
            // The OddBird polyfill does NOT support anchor functions through var()
            // Using setAttribute ensures the polyfill can process it
            popover.setAttribute('style', `position-anchor: --badge-${badgeNumber};`);

            const impact = violation.impact || node.impact || 'minor';
            const impactLabel = impact.charAt(0).toUpperCase() + impact.slice(1);

            // Build popover HTML content with navigation strip
            let content = `
                <div class="inspekt-axe-nav">
                    <div class="inspekt-axe-nav__drag-handle">
                        <span class="inspekt-axe-nav__grip" aria-hidden="true">
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                                <circle cx="4" cy="4" r="1.5"/><circle cx="12" cy="4" r="1.5"/>
                                <circle cx="4" cy="8" r="1.5"/><circle cx="12" cy="8" r="1.5"/>
                                <circle cx="4" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/>
                            </svg>
                        </span>
                        <span class="inspekt-axe-nav__drag-label">Drag</span>
                    </div>
                    <div class="inspekt-axe-nav__group inspekt-axe-nav__group--left">
                        <button class="inspekt-axe-nav__prev" type="button" aria-label="Previous violation" title="Previous (←)">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z"/>
                            </svg>
                        </button>
                        <span class="inspekt-axe-nav__counter" aria-live="polite">1/1</span>
                        <button class="inspekt-axe-nav__next" type="button" aria-label="Next violation" title="Next (→)">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
                            </svg>
                        </button>
                    </div>
                    <div class="inspekt-axe-nav__group inspekt-axe-nav__group--right">
                        <button class="inspekt-axe-nav__skip-similar" type="button" aria-pressed="false" title="Skip similar violations">
                            Skip similar
                        </button>
                        <button class="inspekt-axe-nav__detach" type="button" aria-pressed="false" title="Detach popover">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M19 19H5V5h7V3H5c-1.11 0-2 .9-2 2v14c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2v-7h-2v7zM14 3v2h3.59l-9.83 9.83 1.41 1.41L19 6.41V10h2V3h-7z"/>
                            </svg>
                        </button>
                        <button class="inspekt-axe-nav__close" type="button" aria-label="Close" title="Close (Esc)">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/>
                            </svg>
                        </button>
                    </div>
                </div>
                <div class="inspekt-axe-popover__header">
                    <span class="inspekt-axe-popover__impact-badge inspekt-axe-popover__impact-badge--${impact}">${impactLabel}</span>
                    <h3 class="inspekt-axe-popover__title">${escapeHtml(violation.help)}</h3>
                </div>
                <div role="tablist" aria-label="Violation details" class="inspekt-axe-popover__tablist">
                    <button role="tab"
                            aria-selected="true"
                            aria-controls="panel-default-${badgeNumber}"
                            id="tab-default-${badgeNumber}"
                            class="inspekt-axe-popover__tab inspekt-axe-popover__tab--active"
                            tabindex="0"
                            type="button">
                        Default
                    </button>
                    <button role="tab"
                            aria-selected="false"
                            aria-controls="panel-markdown-${badgeNumber}"
                            id="tab-markdown-${badgeNumber}"
                            class="inspekt-axe-popover__tab"
                            tabindex="-1"
                            type="button">
                        Markdown
                    </button>
                </div>
                <div role="tabpanel"
                     id="panel-default-${badgeNumber}"
                     aria-labelledby="tab-default-${badgeNumber}"
                     class="inspekt-axe-popover__tabpanel inspekt-axe-popover__body">
            `;

            // Default tab content
            // Failure Summary
            if (node.failureSummary) {
                content += `
                    <div class="inspekt-axe-popover__section">
                        <span class="inspekt-axe-popover__section-label">What's wrong</span>
                        <div class="inspekt-axe-popover__failure-summary">${escapeHtml(node.failureSummary)}</div>
                    </div>
                `;
            }

            // HTML Snippet (collapsible)
            if (node.html) {
                content += `
                    <div class="inspekt-axe-popover__section">
                        <details class="inspekt-axe-popover__details">
                            <summary>HTML Snippet</summary>
                            <div class="inspekt-axe-popover__details-content">
                                <pre class="inspekt-axe-popover__code">${escapeHtml(node.html)}</pre>
                            </div>
                        </details>
                    </div>
                `;
            }

            // CSS Selector
            if (node.target && node.target.length > 0) {
                const selectorText = Array.isArray(node.target) ? node.target.join(', ') : node.target;
                content += `
                    <div class="inspekt-axe-popover__section">
                        <span class="inspekt-axe-popover__section-label">CSS Selector</span>
                        <div class="inspekt-axe-popover__selector">${escapeHtml(selectorText)}</div>
                    </div>
                `;
            }

            // Detailed Checks (any/all/none)
            if (node.any || node.all || node.none) {
                content += `<div class="inspekt-axe-popover__section">`;
                content += `<span class="inspekt-axe-popover__section-label">Fix Details</span>`;
                content += `<div class="inspekt-axe-popover__checks">`;

                // "All" checks (must all pass)
                if (node.all && node.all.length > 0) {
                    content += `<div class="inspekt-axe-popover__check-group">`;
                    content += `<div class="inspekt-axe-popover__check-title">Required Fixes (all must pass):</div>`;
                    content += `<ul class="inspekt-axe-popover__check-list">`;
                    node.all.forEach(check => {
                        const status = check.result ? 'pass' : 'fail';
                        content += `<li class="inspekt-axe-popover__check-item inspekt-axe-popover__check-item--${status}">`;
                        content += `<span class="inspekt-axe-popover__check-message">${escapeHtml(check.message)}</span>`;
                        content += `</li>`;
                    });
                    content += `</ul></div>`;
                }

                // "Any" checks (at least one must pass)
                if (node.any && node.any.length > 0) {
                    content += `<div class="inspekt-axe-popover__check-group">`;
                    content += `<div class="inspekt-axe-popover__check-title">Possible Fixes (at least one must pass):</div>`;
                    content += `<ul class="inspekt-axe-popover__check-list">`;
                    node.any.forEach(check => {
                        const status = check.result ? 'pass' : 'fail';
                        content += `<li class="inspekt-axe-popover__check-item inspekt-axe-popover__check-item--${status}">`;
                        content += `<span class="inspekt-axe-popover__check-message">${escapeHtml(check.message)}</span>`;
                        content += `</li>`;
                    });
                    content += `</ul></div>`;
                }

                // "None" checks (must all not be present)
                if (node.none && node.none.length > 0) {
                    content += `<div class="inspekt-axe-popover__check-group">`;
                    content += `<div class="inspekt-axe-popover__check-title">Must Not Occur:</div>`;
                    content += `<ul class="inspekt-axe-popover__check-list">`;
                    node.none.forEach(check => {
                        const status = check.result ? 'pass' : 'fail';
                        content += `<li class="inspekt-axe-popover__check-item inspekt-axe-popover__check-item--${status}">`;
                        content += `<span class="inspekt-axe-popover__check-message">${escapeHtml(check.message)}</span>`;
                        content += `</li>`;
                    });
                    content += `</ul></div>`;
                }

                content += `</div></div>`;
            }

            // WCAG Tags
            if (violation.tags && violation.tags.length > 0) {
                content += `
                    <div class="inspekt-axe-popover__section">
                        <span class="inspekt-axe-popover__section-label">Standards</span>
                        <div class="inspekt-axe-popover__tags">
                `;
                violation.tags.forEach(tag => {
                    const isWCAG = tag.toLowerCase().includes('wcag');
                    const tagClass = isWCAG ? 'inspekt-axe-popover__tag--wcag' : '';
                    content += `<span class="inspekt-axe-popover__tag ${tagClass}">${escapeHtml(tag)}</span>`;
                });
                content += `</div></div>`;
            }

            content += `</div>`; // Close default tabpanel

            // Markdown tabpanel with editable textarea
            const markdownContent = generateMarkdown(badgeNumber, violation, node);
            content += `
                <div role="tabpanel"
                     id="panel-markdown-${badgeNumber}"
                     aria-labelledby="tab-markdown-${badgeNumber}"
                     class="inspekt-axe-popover__tabpanel inspekt-axe-popover__markdown-panel"
                     hidden>
                    <textarea class="inspekt-axe-popover__markdown-textarea"
                              aria-label="Markdown formatted violation details (editable)"
                              spellcheck="false">${escapeHtml(markdownContent)}</textarea>
                </div>
            `;

            // Footer with Learn More link
            if (violation.helpUrl) {
                content += `
                    <div class="inspekt-axe-popover__footer">
                        <a href="${escapeHtml(violation.helpUrl)}" target="_blank" rel="noopener noreferrer" class="inspekt-axe-popover__learn-more">
                            Learn more at Deque University
                        </a>
                    </div>
                `;
            }

            popover.innerHTML = content;

            // Add event listeners for navigation buttons
            const prevBtn = popover.querySelector('.inspekt-axe-nav__prev');
            const nextBtn = popover.querySelector('.inspekt-axe-nav__next');
            const closeBtn = popover.querySelector('.inspekt-axe-nav__close');
            const skipBtn = popover.querySelector('.inspekt-axe-nav__skip-similar');
            const detachBtn = popover.querySelector('.inspekt-axe-nav__detach');

            if (prevBtn) {
                prevBtn.addEventListener('click', () => {
                    const prevIndex = getPreviousViolationIndex(popoverState.skippedRuleIds.size > 0);
                    if (prevIndex >= 0) {
                        navigateToViolation(prevIndex);
                    }
                });
            }

            if (nextBtn) {
                nextBtn.addEventListener('click', () => {
                    const nextIndex = getNextViolationIndex(popoverState.skippedRuleIds.size > 0);
                    if (nextIndex >= 0) {
                        navigateToViolation(nextIndex);
                    }
                });
            }

            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    popover.hidePopover();
                });
            }

            if (skipBtn) {
                skipBtn.addEventListener('click', () => {
                    const isNowSkipped = toggleSkipSimilar();
                    updateBadgeDimming();
                    updateNavigationControls(popover);
                });
            }

            if (detachBtn) {
                detachBtn.addEventListener('click', () => {
                    toggleDetach(popover);
                });
            }

            // Tab switching functionality (W3C ARIA APG manual tabs pattern)
            const tabs = popover.querySelectorAll('[role="tab"]');
            const tabPanels = popover.querySelectorAll('[role="tabpanel"]');

            function switchTab(newTab) {
                // Deselect all tabs and hide all panels
                tabs.forEach(tab => {
                    tab.setAttribute('aria-selected', 'false');
                    tab.setAttribute('tabindex', '-1');
                    tab.classList.remove('inspekt-axe-popover__tab--active');
                });
                tabPanels.forEach(panel => {
                    panel.hidden = true;
                });

                // Select new tab and show its panel
                newTab.setAttribute('aria-selected', 'true');
                newTab.setAttribute('tabindex', '0');
                newTab.classList.add('inspekt-axe-popover__tab--active');
                newTab.focus();

                const panelId = newTab.getAttribute('aria-controls');
                const panel = document.getElementById(panelId);
                if (panel) {
                    panel.hidden = false;
                }
            }

            // Add click listeners to tabs
            tabs.forEach(tab => {
                tab.addEventListener('click', () => {
                    switchTab(tab);
                });

                // Add keyboard navigation for tabs
                tab.addEventListener('keydown', (e) => {
                    let targetTab = null;

                    if (e.key === 'ArrowLeft') {
                        const currentIndex = Array.from(tabs).indexOf(tab);
                        const prevIndex = currentIndex === 0 ? tabs.length - 1 : currentIndex - 1;
                        targetTab = tabs[prevIndex];
                    } else if (e.key === 'ArrowRight') {
                        const currentIndex = Array.from(tabs).indexOf(tab);
                        const nextIndex = (currentIndex + 1) % tabs.length;
                        targetTab = tabs[nextIndex];
                    } else if (e.key === 'Home') {
                        targetTab = tabs[0];
                    } else if (e.key === 'End') {
                        targetTab = tabs[tabs.length - 1];
                    }

                    if (targetTab) {
                        e.preventDefault();
                        switchTab(targetTab);
                    }
                });
            });

            // Handle popover toggle event to update state
            popover.addEventListener('toggle', (e) => {
                if (e.newState === 'open') {
                    handlePopoverOpen(popover);
                    // Focus popover so it can receive keyboard events
                    // Use setTimeout to ensure popover is fully rendered
                    setTimeout(() => {
                        popover.setAttribute('tabindex', '-1');
                        popover.focus();
                    }, 0);
                } else if (e.newState === 'closed') {
                    // Reset current index when closed
                    popoverState.currentIndex = -1;
                    // Remove tabindex when closed
                    popover.removeAttribute('tabindex');
                }
            });

            // Add keyboard navigation (for violation navigation, not tabs)
            popover.addEventListener('keydown', (e) => {
                if (e.key === 'Escape') {
                    popover.hidePopover();
                    e.stopPropagation();
                }
                // Only handle Arrow Left/Right for violation navigation if not in textarea or tab
                else if (e.key === 'ArrowLeft' && !e.target.matches('textarea') && !e.target.matches('[role="tab"]')) {
                    const prevIndex = getPreviousViolationIndex(popoverState.skippedRuleIds.size > 0);
                    if (prevIndex >= 0) {
                        navigateToViolation(prevIndex);
                        e.preventDefault();
                    }
                } else if (e.key === 'ArrowRight' && !e.target.matches('textarea') && !e.target.matches('[role="tab"]')) {
                    const nextIndex = getNextViolationIndex(popoverState.skippedRuleIds.size > 0);
                    if (nextIndex >= 0) {
                        navigateToViolation(nextIndex);
                        e.preventDefault();
                    }
                }
            });

            return popover;
        }

        /**
         * Inject numbered badges on page elements with violations.
         * Uses direct DOM element references from axe-core results.
         *
         * @param {Array} violations - Axe-core violation results with element references
         * @param {boolean} interactive - Whether badges should be clickable with popovers
         * @returns {Object} Badge injection statistics
         */
        async function injectBadgesWithElementRefs(violations, interactive = false) {
            // Remove existing badges, popovers, and styles from previous runs
            document.querySelectorAll('[data-inspekt-axe-badge]').forEach(el => el.remove());
            document.querySelectorAll('[data-inspekt-axe-popover]').forEach(el => el.remove());
            const oldStyles = document.getElementById('inspekt-axe-badge-styles');
            if (oldStyles) oldStyles.remove();
            const oldPopoverStyles = document.getElementById('inspekt-axe-popover-styles');
            if (oldPopoverStyles) oldPopoverStyles.remove();

            // Stop CSS hot-reload if running from previous session
            if (window.__inspektCSSHotReloader) {
                window.__inspektCSSHotReloader.stop();
                delete window.__inspektCSSHotReloader;
            }

            // Inject CSS for badges
            const styleEl = document.createElement('style');
            styleEl.id = 'inspekt-axe-badge-styles';
            styleEl.textContent = `
                .inspekt-axe-badge {
                    /* Reset all inherited styles first */
                    all: initial;

                    /* Now explicitly set everything we need */
                    position: absolute !important;
                    border-radius: 50% !important;
                    width: 32px !important;
                    height: 32px !important;
                    min-width: 32px !important;
                    min-height: 32px !important;
                    max-width: 32px !important;
                    max-height: 32px !important;
                    box-sizing: border-box !important;
                    aspect-ratio: 1 !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    flex-direction: row !important;
                    flex-wrap: nowrap !important;
                    flex-shrink: 0 !important;
                    flex-grow: 0 !important;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
                    font-size: 13px !important;
                    font-weight: bold !important;
                    color: white !important;
                    z-index: 2147483647 !important;
                    pointer-events: none !important;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.4) !important;
                    border: 2px solid white !important;
                    user-select: none !important;
                    line-height: 1 !important;
                    transform: none !important;
                    transform-origin: center center !important;
                    overflow: hidden !important;
                    contain: layout style !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    text-align: center !important;
                    vertical-align: baseline !important;
                    writing-mode: horizontal-tb !important;
                    direction: ltr !important;
                }

                /* Impact badge colors - specific enough to override button defaults */
                .inspekt-axe-badge.inspekt-axe-badge--critical,
                button.inspekt-axe-badge.inspekt-axe-badge--critical {
                    background: #dc2626;
                }

                .inspekt-axe-badge.inspekt-axe-badge--serious,
                button.inspekt-axe-badge.inspekt-axe-badge--serious {
                    background: #ea580c;
                }

                .inspekt-axe-badge.inspekt-axe-badge--moderate,
                button.inspekt-axe-badge.inspekt-axe-badge--moderate {
                    background: #2563eb;
                }

                .inspekt-axe-badge.inspekt-axe-badge--minor,
                button.inspekt-axe-badge.inspekt-axe-badge--minor {
                    background: #6b7280;
                }

                .inspekt-axe-badge__text {
                    display: flex !important;
                    gap: 1px !important;
                    align-items: center !important;
                    justify-content: center !important;
                    flex-shrink: 0 !important;
                    flex-grow: 0 !important;
                }

                /* Interactive badge styles (when badges are buttons) */
                button.inspekt-axe-badge {
                    pointer-events: auto !important;
                    cursor: pointer !important;
                    transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.2s ease !important;
                }

                button.inspekt-axe-badge:hover {
                    transform: scale(1.1) !important;
                    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.5) !important;
                }

                button.inspekt-axe-badge:focus-visible {
                    outline: 3px solid #2563eb !important;
                    outline-offset: 2px !important;
                    transform: scale(1.1) !important;
                }

                button.inspekt-axe-badge:active {
                    transform: scale(0.95) !important;
                }

                button.inspekt-axe-badge[id] {
                    anchor-name: var(--anchor-name);
                }

                /* Dimmed badges (skip similar active) */
                button.inspekt-axe-badge--dimmed {
                    opacity: 0.5;
                    pointer-events: none;
                    cursor: not-allowed;
                }

                button.inspekt-axe-badge--dimmed:hover {
                    transform: none;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
                }
            `;
            document.head.appendChild(styleEl);

            // Inject popover CSS if in interactive mode
            if (interactive) {
                if (devCss) {
                    // Dev mode: load CSS from local server for live editing
                    // Start server with: npm run dev:axe-css
                    const cssUrl = 'http://localhost:8000/axe-popover/index.css';
                    const linkEl = document.createElement('link');
                    linkEl.id = 'inspekt-axe-popover-styles';
                    linkEl.rel = 'stylesheet';
                    linkEl.href = cssUrl;
                    document.head.appendChild(linkEl);

                    // Start CSS hot-reload polling
                    const hotReloader = new CSSHotReloader(cssUrl);
                    hotReloader.start(linkEl);

                    // Store reference for cleanup
                    window.__inspektCSSHotReloader = hotReloader;

                    console.log('%c[Inspekt Dev Mode]%c CSS loaded from ' + cssUrl,
                        'color: #10b981; font-weight: bold', 'color: inherit');
                    console.log('%c[Inspekt Dev Mode]%c Start server: npm run dev:axe-css',
                        'color: #10b981; font-weight: bold', 'color: inherit');
                    console.log('%c[Inspekt Dev Mode]%c Hot-reload enabled - save CSS to see changes automatically',
                        'color: #10b981; font-weight: bold', 'color: inherit');
                } else {
                    // Production mode: embed CSS inline
                    const popoverStyleEl = document.createElement('style');
                    popoverStyleEl.id = 'inspekt-axe-popover-styles';
                    popoverStyleEl.textContent = getPopoverCSS();
                    document.head.appendChild(popoverStyleEl);
                }
            }

            const MAX_BADGES = 50;
            let badgeNumber = 1;
            let badgesCreated = 0;
            let badgesFailed = 0;
            let badgesSkipped = 0;

            // Reset global state for new badge injection
            popoverState.violations = [];
            popoverState.currentIndex = -1;
            popoverState.skippedRuleIds.clear();

            // Track badges per element to handle multiple violations on same element
            const elementBadges = new Map(); // DOM element -> badge count

            for (const violation of violations) {
                const impact = violation.impact || 'minor';

                for (const node of violation.nodes) {
                    // Check badge limit
                    if (badgesCreated >= MAX_BADGES) {
                        badgesSkipped++;
                        badgeNumber++;
                        continue;
                    }

                    // DIRECT ELEMENT ACCESS - No querySelector needed!
                    const element = node.element;

                    // Verify element is valid
                    if (!element || element.nodeType !== 1) {
                        badgesFailed++;
                        badgeNumber++;
                        continue;
                    }

                    try {
                        // Get element position
                        const rect = element.getBoundingClientRect();
                        const scrollX = window.pageXOffset || document.documentElement.scrollLeft;
                        const scrollY = window.pageYOffset || document.documentElement.scrollTop;

                        // Calculate horizontal offset for multiple badges on same element
                        const existingCount = elementBadges.get(element) || 0;
                        const horizontalOffset = existingCount * 36; // 32px badge + 4px gap

                        // Generate unique ID for this badge
                        const badgeId = `inspekt-badge-${badgeNumber}`;
                        const popoverId = `inspekt-popover-${badgeNumber}`;

                        // Create badge element (button if interactive, div otherwise)
                        const badge = document.createElement(interactive ? 'button' : 'div');
                        badge.className = `inspekt-axe-badge inspekt-axe-badge--${impact}`;
                        badge.setAttribute('data-inspekt-axe-badge', badgeNumber);
                        badge.setAttribute('data-inspekt-axe-impact', impact);
                        badge.id = badgeId;

                        // If interactive, set up popover trigger
                        if (interactive) {
                            badge.setAttribute('popovertarget', popoverId);
                            badge.setAttribute('type', 'button');
                            // Set anchor-name directly with a literal value (not via CSS custom property)
                            // The OddBird polyfill does NOT support anchor functions through var()
                            // Using setAttribute ensures the polyfill can process it
                            const currentStyle = badge.getAttribute('style') || '';
                            badge.setAttribute('style', currentStyle + `anchor-name: --badge-${badgeNumber};`);
                        }

                        // Create badge text with accessibility attributes
                        const textContent = document.createElement('span');
                        textContent.className = 'inspekt-axe-badge__text';
                        textContent.textContent = badgeNumber;

                        // Capitalize impact for display
                        const impactLabel = impact.charAt(0).toUpperCase() + impact.slice(1);

                        // Add accessibility attributes
                        const ariaLabel = interactive
                            ? `Show details for Accessibility Violation ${badgeNumber} (${impactLabel})`
                            : `Accessibility Violation ${badgeNumber} (${impactLabel})`;
                        textContent.setAttribute('aria-label', ariaLabel);
                        textContent.setAttribute('title', impactLabel);
                        textContent.setAttribute('role', 'text');

                        badge.appendChild(textContent);

                        // Position badge at top-left of element
                        badge.style.left = (rect.left + scrollX - 16 + horizontalOffset) + 'px'; // -16 is half of 32px badge
                        badge.style.top = (rect.top + scrollY - 16) + 'px'; // -16 is half of 32px badge

                        // Add to DOM
                        document.body.appendChild(badge);

                        // Create and add popover if interactive
                        if (interactive) {
                            const popover = createPopover(popoverId, badgeId, badgeNumber, violation, node);
                            document.body.appendChild(popover);

                            // Store violation metadata in global state for navigation
                            popoverState.violations.push({
                                index: badgesCreated, // Zero-based index for navigation
                                badgeId: badgeId,
                                popoverId: popoverId,
                                ruleId: violation.id,
                                violation: violation,
                                node: node
                            });
                        }

                        // Track this element
                        elementBadges.set(element, existingCount + 1);
                        badgesCreated++;

                    } catch (error) {
                        badgesFailed++;
                    }

                    badgeNumber++;
                }
            }

            return {
                ok: true,
                badgesCreated: badgesCreated,
                badgesFailed: badgesFailed,
                badgesSkipped: badgesSkipped,
                totalViolations: badgeNumber - 1,
                maxBadges: MAX_BADGES
            };
        }

        // Run axe-core audit with element references
        const results = await axe.run(document, config);

        // Inject badges immediately (while we have element references)
        let badgeStats = { ok: false, badgesCreated: 0, badgesFailed: 0, badgesSkipped: 0 };
        if (showBadges && results.violations.length > 0) {
            badgeStats = await injectBadgesWithElementRefs(results.violations, interactiveBadges);
        }

        // Check if polyfill is needed (Firefox and other browsers without CSS anchor positioning support)
        const needsPolyfill = !('anchorName' in document.documentElement.style);

        // Load and apply CSS Anchor Positioning polyfill AFTER badges/popovers are created
        if (interactiveBadges && badgeStats.badgesCreated > 0 && needsPolyfill) {
            try {
                console.log('[Inspekt] CSS Anchor Positioning not supported, setting up polyfill...');

                // Generate dynamic CSS rules for each badge/popover pair
                // The polyfill parses stylesheets, so we need anchor positioning in CSS, not inline styles
                const badges = document.querySelectorAll('[data-inspekt-axe-badge]');
                let anchorCSS = '/* Dynamic anchor positioning rules for polyfill */\n';

                badges.forEach((badge) => {
                    const badgeNum = badge.getAttribute('data-inspekt-axe-badge');
                    const badgeId = badge.id;
                    const popoverId = `inspekt-popover-${badgeNum}`;

                    // Create CSS rules that the polyfill can parse
                    anchorCSS += `#${badgeId} { anchor-name: --badge-${badgeNum}; }\n`;
                    anchorCSS += `#${popoverId} { position-anchor: --badge-${badgeNum}; }\n`;
                });

                // Inject the dynamic CSS
                const anchorStyleEl = document.createElement('style');
                anchorStyleEl.id = 'inspekt-axe-anchor-styles';
                anchorStyleEl.textContent = anchorCSS;
                document.head.appendChild(anchorStyleEl);
                console.log('[Inspekt] Injected anchor positioning CSS for', badges.length, 'badges');

                // Load the auto-applying polyfill
                console.log('[Inspekt] Loading CSS Anchor Positioning polyfill...');
                const polyfillScript = document.createElement('script');
                polyfillScript.src = 'https://unpkg.com/@oddbird/css-anchor-positioning@0.8.0/dist/css-anchor-positioning.umd.cjs';
                document.head.appendChild(polyfillScript);

                // Wait for script to load and auto-apply
                await new Promise((resolve, reject) => {
                    polyfillScript.onload = () => {
                        console.log('[Inspekt] CSS Anchor Positioning polyfill loaded and auto-applied');
                        resolve();
                    };
                    polyfillScript.onerror = (err) => {
                        console.error('[Inspekt] Failed to load polyfill:', err);
                        reject(err);
                    };
                    setTimeout(() => reject(new Error('Polyfill load timeout')), 10000);
                });

                console.log('[Inspekt] CSS Anchor Positioning polyfill ready');

                // Auto-detach popover in Firefox (and other browsers without native anchor support)
                // since the polyfill positioning can be wonky - position in top-right corner instead
                console.log('[Inspekt] Auto-detaching popover for Firefox (top-right corner)');
                popoverState.detachedState.isDetached = true;
                popoverState.detachedState.x = window.innerWidth - 440; // 420px max-width + 20px margin
                popoverState.detachedState.y = 20;
            } catch (error) {
                console.error('[Inspekt] Failed to load/apply anchor positioning polyfill:', error);
            }
        }

        // Auto-open first popover in interactive mode
        if (interactiveBadges && badgeStats.badgesCreated > 0 && popoverState.violations.length > 0) {
            // Use double requestAnimationFrame to ensure popover is fully painted
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    const firstViolation = popoverState.violations[0];
                    const firstPopover = document.getElementById(firstViolation.popoverId);
                    if (firstPopover) {
                        // Set current index to 0 (first violation)
                        popoverState.currentIndex = 0;
                        // Show the popover
                        firstPopover.showPopover();
                    }
                });
            });
        }

        // Calculate summary statistics
        const summary = {
            violationCount: results.violations.length,
            passCount: results.passes.length,
            incompleteCount: results.incomplete.length,
            inapplicableCount: results.inapplicable.length,
            criticalCount: results.violations.filter(v => v.impact === 'critical').length,
            seriousCount: results.violations.filter(v => v.impact === 'serious').length,
            moderateCount: results.violations.filter(v => v.impact === 'moderate').length,
            minorCount: results.violations.filter(v => v.impact === 'minor').length
        };

        // Process violations - exclude element refs (can't serialize DOM nodes)
        const violations = results.violations.map(violation => ({
            id: violation.id,
            impact: violation.impact,
            description: violation.description,
            help: violation.help,
            helpUrl: violation.helpUrl,
            tags: violation.tags,
            nodes: violation.nodes.map(node => {
                // Destructure to remove element property
                const { element, ...serializable } = node;
                return {
                    html: serializable.html,
                    target: serializable.target,
                    failureSummary: serializable.failureSummary,
                    impact: serializable.impact
                };
            }),
            nodeCount: violation.nodes.length
        }));

        // Process passes (simplified)
        const passes = results.passes.map(pass => ({
            id: pass.id,
            description: pass.description,
            help: pass.help,
            tags: pass.tags,
            nodeCount: pass.nodes.length
        }));

        // Process incomplete checks
        const incomplete = results.incomplete.map(item => ({
            id: item.id,
            impact: item.impact,
            description: item.description,
            help: item.help,
            helpUrl: item.helpUrl,
            tags: item.tags,
            nodeCount: item.nodes.length
        }));

        return {
            ok: true,
            url: window.location.href,
            title: document.title,
            timestamp: new Date().toISOString(),
            violations: violations,
            passes: passes,
            incomplete: incomplete,
            inapplicable: results.inapplicable.map(r => r.id),
            summary: summary,
            badgeStats: badgeStats,  // Include badge injection results
            axeVersion: axe.version
        };

    } catch (error) {
        return {
            ok: false,
            error: error.message,
            stack: error.stack,
            url: window.location.href
        };
    }
})()
