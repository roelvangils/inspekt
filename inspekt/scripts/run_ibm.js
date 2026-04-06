// Inspekt IBM Equal Access Accessibility Audit Script with Unified Badge/Popover System
// Note: ace.js library and popover-core.js are injected before this script executes (when badges enabled)
(async function() {
    try {
        // Verify ace is available (it should be loaded before this script)
        if (typeof ace === 'undefined') {
            throw new Error('IBM Equal Access (ace) library not found - this should not happen');
        }

        // Configuration object injected from Python
        // Will be replaced with actual config via string substitution
        const config = __IBM_CONFIG__;

        // Get show-badges and interactive flags from config (injected by Python)
        const showBadges = config.__showBadges !== false;  // Default true
        const interactiveBadges = config.__interactiveBadges === true;  // Default false
        const devCss = config.__devCss === true;  // Dev mode: load CSS from external server
        const isPersistent = config.__persistent === true;  // Persistent monitoring mode

        // Verify popover-core is available (only needed when badges are enabled)
        let popoverCore = null;
        if (showBadges || interactiveBadges) {
            if (!window.__inspektPopoverCore__) {
                throw new Error('Shared popover core not found - this should not happen');
            }
            popoverCore = window.__inspektPopoverCore__;
        }

        // Debug logging
        console.log('[Inspekt IBM] Config flags:', {
            showBadges,
            interactiveBadges,
            devCss,
            isPersistent,
            policies: config.policies,
            reportLevels: config.reportLevels
        });

        // Clean config flags that shouldn't be passed to ace
        delete config.__showBadges;
        delete config.__interactiveBadges;
        delete config.__devCss;
        delete config.__persistent;

        // ============================================================
        // INSPEKT UI FILTERING
        // ============================================================

        // Selectors for Inspekt UI elements that should be excluded from scans
        const INSPEKT_UI_SELECTORS = [
            '[data-inspekt-badge]',
            '[data-inspekt-popover]',
            '[data-inspekt-axe-popover]',
            '[data-inspekt-ibm-popover]',
            '.inspekt-axe-popover',
            '.inspekt-ibm-popover',
            '#inspekt-badge-styles',
            '#inspekt-axe-popover-styles',
            '#inspekt-axe-popover-additional-styles',
            '#inspekt-ibm-popover-styles',
            '#inspekt-ibm-badge-styles',
            '#inspekt-unified-styles'
        ];

        /**
         * Check if an element is part of Inspekt UI (badge, popover, or their children)
         * @param {Element} element - DOM element to check
         * @returns {boolean} True if element is part of Inspekt UI
         */
        function isInspektUIElement(element) {
            if (!element || element.nodeType !== 1) return false;

            // Check if element itself matches any Inspekt selector
            for (const selector of INSPEKT_UI_SELECTORS) {
                try {
                    if (element.matches(selector)) return true;
                } catch (e) {
                    // Invalid selector, skip
                }
            }

            // Check if element is a descendant of an Inspekt UI element
            for (const selector of INSPEKT_UI_SELECTORS) {
                try {
                    if (element.closest(selector)) return true;
                } catch (e) {
                    // Invalid selector, skip
                }
            }

            return false;
        }

        // ============================================================
        // PERSISTENT MODE SETUP
        // ============================================================
        if (isPersistent) {
            // Initialize persistent state (preserved across re-runs on same page)
            window.__inspektIbmSeenIssues__ = window.__inspektIbmSeenIssues__ || new Set();
            window.__inspektIbmDirty__ = window.__inspektIbmDirty__ || false;
            window.__inspektIbmLastBadgeNumber__ = window.__inspektIbmLastBadgeNumber__ || 0;

            // Only set up listeners once
            if (!window.__inspektIbmPersistentListenersInstalled__) {
                window.__inspektIbmPersistentListenersInstalled__ = true;

                let clickDebounceTimer;
                document.addEventListener('click', (event) => {
                    // Ignore clicks on Inspekt UI elements
                    if (event.target.closest('[data-inspekt-badge], [data-inspekt-popover], .inspekt-axe-popover')) {
                        return;
                    }
                    clearTimeout(clickDebounceTimer);
                    clickDebounceTimer = setTimeout(() => {
                        window.__inspektIbmDirty__ = true;
                    }, 1000);
                }, true);

                // Watch for SPA URL changes
                const originalPushState = history.pushState;
                history.pushState = function(...args) {
                    originalPushState.apply(this, args);
                    window.__inspektIbmDirty__ = true;
                };

                const originalReplaceState = history.replaceState;
                history.replaceState = function(...args) {
                    originalReplaceState.apply(this, args);
                    window.__inspektIbmDirty__ = true;
                };

                window.addEventListener('popstate', () => {
                    window.__inspektIbmDirty__ = true;
                });

                console.log('[Inspekt IBM] Persistent mode listeners installed');
            }
        }

        // ============================================================
        // SEVERITY MAPPING
        // ============================================================

        const IBM_LEVEL_TO_IMPACT = {
            'violation': 'critical',
            'potentialviolation': 'serious',
            'recommendation': 'moderate',
            'potentialrecommendation': 'minor',
            'manual': 'minor'
        };

        function mapIbmLevelToImpact(level) {
            return IBM_LEVEL_TO_IMPACT[level] || 'minor';
        }

        // ============================================================
        // HELPER FUNCTIONS
        // ============================================================

        /**
         * Escapes HTML to prevent XSS.
         */
        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        /**
         * Get a unique selector for an element.
         */
        function getUniqueSelector(element) {
            if (!element || element.nodeType !== 1) return '';

            if (element.id) {
                return `#${CSS.escape(element.id)}`;
            }

            const path = [];
            let current = element;

            while (current && current.nodeType === 1) {
                let selector = current.tagName.toLowerCase();

                if (current.id) {
                    selector = `#${CSS.escape(current.id)}`;
                    path.unshift(selector);
                    break;
                }

                if (current.className && typeof current.className === 'string') {
                    const classes = current.className.trim().split(/\s+/).filter(c => c);
                    if (classes.length > 0) {
                        selector += '.' + classes.map(c => CSS.escape(c)).join('.');
                    }
                }

                // Add nth-child if needed for uniqueness
                const parent = current.parentElement;
                if (parent) {
                    const siblings = Array.from(parent.children).filter(
                        c => c.tagName === current.tagName
                    );
                    if (siblings.length > 1) {
                        const index = siblings.indexOf(current) + 1;
                        selector += `:nth-child(${index})`;
                    }
                }

                path.unshift(selector);
                current = current.parentElement;
            }

            return path.join(' > ');
        }

        /**
         * Get a code snippet for an element.
         */
        function getSnippet(element, maxLength = 150) {
            if (!element || element.nodeType !== 1) return '';

            const outer = element.outerHTML || '';
            if (outer.length <= maxLength) return outer;

            // Get opening tag only
            const tagMatch = outer.match(/^<[^>]+>/);
            if (tagMatch) {
                const openTag = tagMatch[0];
                if (openTag.length <= maxLength) {
                    return openTag + '...';
                }
            }

            return outer.substring(0, maxLength) + '...';
        }

        /**
         * Get human-readable level name.
         */
        function getLevelName(level) {
            const mapping = {
                'violation': 'Violation',
                'potentialviolation': 'Needs Review',
                'recommendation': 'Recommendation',
                'potentialrecommendation': 'Potential Recommendation',
                'manual': 'Manual Check',
                'pass': 'Pass'
            };
            return mapping[level] || level;
        }

        // ============================================================
        // CSS INJECTION (Unified Axe-style CSS)
        // ============================================================

        async function injectIbmPopoverCSS(devMode) {
            const existingStyles = document.getElementById('inspekt-ibm-popover-styles');
            if (existingStyles) return;

            if (devMode) {
                // Dev mode: load from external server
                const link = document.createElement('link');
                link.id = 'inspekt-ibm-popover-styles';
                link.rel = 'stylesheet';
                link.href = 'http://localhost:3456/unified-popover/index.css';
                document.head.appendChild(link);
                // Wait for CSS to load
                await new Promise(resolve => setTimeout(resolve, 100));
            } else {
                // Production mode: inline CSS
                const style = document.createElement('style');
                style.id = 'inspekt-ibm-popover-styles';
                style.textContent = getIbmPopoverCSS();
                document.head.appendChild(style);
            }
        }

        /**
         * Inject badge base styles (separate from popover CSS).
         * These include the critical impact colors and base badge styling.
         */
        function injectBadgeStyles() {
            const existingStyles = document.getElementById('inspekt-ibm-badge-styles');
            if (existingStyles) return;

            const styleEl = document.createElement('style');
            styleEl.id = 'inspekt-ibm-badge-styles';
            styleEl.textContent = `
                .inspekt-badge {
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
                .inspekt-badge.inspekt-badge--critical,
                button.inspekt-badge.inspekt-badge--critical {
                    background: #dc2626 !important;
                }

                .inspekt-badge.inspekt-badge--serious,
                button.inspekt-badge.inspekt-badge--serious {
                    background: #ea580c !important;
                }

                .inspekt-badge.inspekt-badge--moderate,
                button.inspekt-badge.inspekt-badge--moderate {
                    background: #2563eb !important;
                }

                .inspekt-badge.inspekt-badge--minor,
                button.inspekt-badge.inspekt-badge--minor {
                    background: #6b7280 !important;
                }

                .inspekt-badge__text {
                    display: flex !important;
                    gap: 1px !important;
                    align-items: center !important;
                    justify-content: center !important;
                    flex-shrink: 0 !important;
                    flex-grow: 0 !important;
                }

                /* Interactive badge styles (when badges are buttons) */
                button.inspekt-badge {
                    pointer-events: auto !important;
                    cursor: pointer !important;
                    transition: transform 0.15s ease, box-shadow 0.15s ease, opacity 0.2s ease !important;
                }

                button.inspekt-badge:hover {
                    transform: scale(1.1) !important;
                    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.5) !important;
                }

                button.inspekt-badge:focus-visible {
                    outline: 3px solid #2563eb !important;
                    outline-offset: 2px !important;
                    transform: scale(1.1) !important;
                }

                button.inspekt-badge:active {
                    transform: scale(0.95) !important;
                }

                button.inspekt-badge[id] {
                    anchor-name: var(--anchor-name);
                }

                /* Dimmed badges (skip similar active) */
                button.inspekt-badge--dimmed {
                    opacity: 0.5;
                    pointer-events: none;
                    cursor: not-allowed;
                }

                button.inspekt-badge--dimmed:hover {
                    transform: none;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.4);
                }

                /* Pulsing animation for active badge */
                @keyframes inspekt-pulse {
                    0% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.7), 0 2px 4px rgba(0, 0, 0, 0.4); }
                    70% { box-shadow: 0 0 0 12px rgba(37, 99, 235, 0), 0 2px 4px rgba(0, 0, 0, 0.4); }
                    100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0), 0 2px 4px rgba(0, 0, 0, 0.4); }
                }

                button.inspekt-badge--active {
                    animation: inspekt-pulse 1.5s infinite !important;
                }
            `;
            document.head.appendChild(styleEl);
        }

        // ============================================================
        // BADGE/POPOVER INJECTION (Unified System)
        // ============================================================

        /**
         * Remove ALL existing Inspekt badges and popovers from the page.
         * Removes unified, axe-only, and ibm-only elements.
         */
        function removeExistingBadges() {
            // Remove all badges and popovers (any source)
            document.querySelectorAll('[data-inspekt-badge]').forEach(el => el.remove());
            document.querySelectorAll('[data-inspekt-popover]').forEach(el => el.remove());
            document.querySelectorAll('[data-inspekt-axe-popover]').forEach(el => el.remove());
            document.querySelectorAll('[data-inspekt-ibm-popover]').forEach(el => el.remove());
            document.querySelectorAll('.inspekt-axe-popover').forEach(el => el.remove());
            document.querySelectorAll('.inspekt-ibm-popover').forEach(el => el.remove());

            // Remove old IBM badges (backward compatibility)
            document.querySelectorAll('[data-inspekt-ibm-badge]').forEach(el => el.remove());
            document.getElementById('inspekt-ibm-styles')?.remove();

            // Remove all style elements
            ['inspekt-badge-styles', 'inspekt-axe-popover-styles', 'inspekt-axe-popover-additional-styles',
             'inspekt-ibm-popover-styles', 'inspekt-ibm-badge-styles', 'inspekt-unified-styles'].forEach(id => {
                document.getElementById(id)?.remove();
            });
        }

        /**
         * Create and position a badge for an issue.
         */
        function createBadge(issue, index, totalCount) {
            const node = issue.node;
            if (!node || node.nodeType !== 1) return null;

            const impact = mapIbmLevelToImpact(issue.level);

            const badge = document.createElement('button');
            badge.id = `inspekt-ibm-badge-${index}`;
            badge.setAttribute('data-inspekt-badge', index);
            badge.className = `inspekt-badge inspekt-badge--${impact}`;
            badge.textContent = index;
            badge.title = `${getLevelName(issue.level)}: ${issue.ruleId}`;
            badge.type = 'button';

            // Set anchor name for CSS positioning
            badge.style.anchorName = `--ibm-badge-${index}`;

            // Position badge at top-left of element
            const rect = node.getBoundingClientRect();
            badge.style.top = `${window.scrollY + rect.top - 16}px`;
            badge.style.left = `${window.scrollX + rect.left - 16}px`;

            return badge;
        }


        /**
         * Inject badges for all issues using the unified popover system.
         */
        async function injectBadges(issues) {
            removeExistingBadges();

            // Reset popover core state
            popoverCore.reset();

            // Inject CSS
            await injectIbmPopoverCSS(devCss);
            injectBadgeStyles();

            const maxBadges = 100;
            const badgeableIssues = issues.filter(i =>
                i.node && i.node.nodeType === 1 && i.level !== 'pass' && !isInspektUIElement(i.node)
            ).slice(0, maxBadges);

            let badgeCount = 0;
            const totalCount = badgeableIssues.length;

            badgeableIssues.forEach((issue, idx) => {
                const badgeNumber = idx + 1;

                // Create badge
                const badge = createBadge(issue, badgeNumber, totalCount);
                if (!badge) return;

                // Create popover using shared module
                const popoverContent = window.__inspektPopoverContent__;
                const normalizedData = popoverContent.normalizeIbmData(issue);
                const popoverId = `inspekt-ibm-popover-${badgeNumber}`;
                const badgeId = badge.id;
                const popover = popoverContent.createPopover(popoverId, badgeId, badgeNumber, normalizedData, popoverCore);

                document.body.appendChild(badge);
                document.body.appendChild(popover);

                // Build unified violation object for popoverCore
                const unifiedViolation = {
                    index: idx,
                    badgeId: badge.id,
                    popoverId: popover.id,
                    element: issue.node,
                    sources: {
                        axe: [],
                        ibm: [{
                            ruleId: issue.ruleId,
                            level: issue.level,
                            message: issue.message,
                            snippet: issue.snippet
                        }]
                    },
                    highestImpact: mapIbmLevelToImpact(issue.level)
                };

                // Add to popover core state
                popoverCore.addViolation(unifiedViolation);

                // Bind badge click
                if (interactiveBadges) {
                    badge.addEventListener('click', (e) => {
                        e.stopPropagation();
                        popoverCore.navigateToViolation(idx);
                    });
                }

                badgeCount++;
            });

            console.log(`[Inspekt IBM] Created ${badgeCount} unified badges`);
            return badgeCount;
        }

        // ============================================================
        // BUILD CONTEXT
        // ============================================================

        let context = document;

        // Check for scoped context
        if (config.__context === 'inspected' && window.__INSPEKT_INSPECTED_ELEMENT__) {
            context = window.__INSPEKT_INSPECTED_ELEMENT__;
            console.log('[Inspekt IBM] Running on inspected element');
        } else if (config.__context && typeof config.__context === 'string' && config.__context !== 'document') {
            const elements = document.querySelectorAll(config.__context);
            if (elements.length === 1) {
                context = elements[0];
            } else if (elements.length > 1) {
                context = Array.from(elements);
            }
            console.log(`[Inspekt IBM] Running on selector: ${config.__context}`);
        }

        delete config.__context;

        // ============================================================
        // RUN IBM CHECKER
        // ============================================================

        // Create checker instance
        const checker = new ace.Checker();

        // Determine which guidelines/policies to use
        // Map WCAG level to IBM guideline IDs
        const levelToGuidelines = {
            '2a': ['WCAG_2_0'],
            '2aa': ['WCAG_2_0'],
            '2aaa': ['WCAG_2_0'],
            '21a': ['WCAG_2_1'],
            '21aa': ['WCAG_2_1'],
            '22aa': ['WCAG_2_2'],
        };

        let guidelines = config.policies || levelToGuidelines[config.__level || '22aa'] || ['WCAG_2_2'];
        delete config.__level;

        console.log('[Inspekt IBM] Running check with guidelines:', guidelines);

        // Run the check
        const report = await checker.check(context, guidelines);

        console.log('[Inspekt IBM] Check complete:', {
            numExecuted: report.numExecuted,
            ruleTime: report.ruleTime,
            resultCount: report.results?.length || 0
        });

        // ============================================================
        // PROCESS RESULTS
        // ============================================================

        // Filter based on report levels
        const reportLevels = config.reportLevels || ['violation', 'potentialviolation'];

        // Determine the level from value array
        function getLevel(result) {
            if (!result.value || result.value.length < 2) return 'unknown';
            const [policy, confidence] = result.value;

            // Map confidence to level
            if (confidence === 'FAIL') {
                return policy === 'VIOLATION' ? 'violation' : 'potentialviolation';
            } else if (confidence === 'POTENTIAL') {
                return 'potentialviolation';
            } else if (confidence === 'MANUAL') {
                return 'manual';
            } else if (confidence === 'PASS') {
                return 'pass';
            }
            return 'recommendation';
        }

        // Process each result
        const processedResults = (report.results || []).map(result => {
            const level = getLevel(result);
            const node = result.node;

            // Extract WCAG SC numbers from rulesets if available
            let wcag = [];
            // The rule metadata is in report.nls but we need the rulesets
            // For now, we'll include the ruleId which often contains WCAG refs

            return {
                ruleId: result.ruleId,
                reasonId: result.reasonId,
                level: level,
                message: result.message,
                path: result.path?.dom || getUniqueSelector(node),
                snippet: result.snippet || getSnippet(node),
                node: node,
                wcag: wcag,
                category: result.category
            };
        });

        // Filter results by report levels
        const filteredResults = processedResults.filter(r =>
            reportLevels.includes(r.level)
        );

        // Group by level for summary
        const summary = {
            violation: 0,
            potentialviolation: 0,
            recommendation: 0,
            potentialrecommendation: 0,
            manual: 0,
            pass: 0
        };

        processedResults.forEach(r => {
            if (summary.hasOwnProperty(r.level)) {
                summary[r.level]++;
            }
        });

        // ============================================================
        // INJECT BADGES
        // ============================================================

        let badgeStats = null;
        if (showBadges && filteredResults.length > 0) {
            const badgeCount = await injectBadges(filteredResults);
            badgeStats = {
                ok: true,
                badgesCreated: badgeCount,
                totalIssuesOnPage: filteredResults.length
            };
        }

        // ============================================================
        // RETURN RESULTS
        // ============================================================

        // Clean node references for JSON serialization
        const serializableResults = filteredResults.map(r => ({
            ruleId: r.ruleId,
            reasonId: r.reasonId,
            level: r.level,
            message: r.message,
            path: r.path,
            snippet: r.snippet,
            wcag: r.wcag,
            category: r.category
        }));

        return {
            ok: true,
            result: {
                url: window.location.href,
                title: document.title || '',
                issues: serializableResults,
                summary: summary,
                numExecuted: report.numExecuted,
                ruleTime: report.ruleTime,
                badgeStats: badgeStats
            }
        };

        // ============================================================
        // INLINE CSS (Production mode - minified)
        // ============================================================

        function getIbmPopoverCSS() {
            // Minified CSS from axe-popover/index.css - same as run_axe.js
            return `@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap");:root{--gray-50:#f9fafb;--gray-100:#f3f4f6;--gray-200:#e5e7eb;--gray-300:#d1d5db;--gray-400:#9ca3af;--gray-500:#6b7280;--gray-600:#4b5563;--gray-700:#374151;--gray-800:#1f2937;--gray-900:#111827;--blue:#2563eb;--blue-light:#60a5fa;--blue-bg:#eff6ff;--green:#10b981;--green-bg:#f0fdf4;--red:#dc2626;--red-bg:#fef2f2;--orange:#ea580c;--color-text:var(--gray-800);--color-text-muted:var(--gray-500);--color-text-inverse:#ffffff;--color-bg:rgba(255,255,255,0.75);--color-bg-subtle:var(--gray-50);--color-border:var(--gray-200);--color-primary:var(--blue);--impact-critical:var(--red);--impact-serious:var(--orange);--impact-moderate:var(--blue);--impact-minor:var(--gray-500);--font-sans:"Inter",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;--font-mono:ui-monospace,SFMono-Regular,monospace;--text-xs:11px;--text-sm:13px;--text-base:14px;--text-lg:16px;--space-sm:4px;--space-md:8px;--space-lg:16px;--radius-sm:4px;--radius-md:8px;--radius-lg:12px;--shadow-popover:0 20px 60px rgba(0,0,0,0.12),0 8px 20px rgba(0,0,0,0.08);--shadow-badge:0 3px 6px rgba(0,0,0,0.5);--popover-max-width:480px;--popover-min-width:380px;--popover-max-height:80vh;--nav-button-size:28px;--transition-fast:0.15s ease;--transition-base:0.2s ease;--animation-duration:0.15s;--animation-distance:20px;--blur-popover:blur(20px) saturate(180%)}.visually-hidden{opacity:0 !important;clip-path:inset(100%);clip:rect(1px,1px,1px,1px);height:1px;overflow:hidden;position:absolute;white-space:nowrap;width:1px}[popover].inspekt-axe-popover{position:absolute;margin:0;inset:unset;position-area:block-end span-inline-end;position-try-fallbacks:--bottom-left,--top-right,--top-left,flip-block,flip-inline;max-width:var(--popover-max-width);min-width:var(--popover-min-width);max-height:var(--popover-max-height);width:max-content;background:var(--color-bg);border:2px solid var(--color-border);border-radius:var(--radius-lg);box-shadow:var(--shadow-popover);backdrop-filter:var(--blur-popover);-webkit-backdrop-filter:var(--blur-popover);font-family:var(--font-sans);font-size:var(--text-lg);line-height:1.5;color:var(--color-text);padding:0;overflow:hidden;overscroll-behavior:contain;transition:opacity var(--transition-base),box-shadow var(--transition-base);&:popover-open{animation:popoverFadeIn var(--animation-duration) ease-out}}@position-try --bottom-left{position-area:block-end span-inline-start}@position-try --top-right{position-area:block-start span-inline-end}@position-try --top-left{position-area:block-start span-inline-start}[popover].inspekt-axe-popover--detached{position:fixed;position-anchor:unset;position-area:unset;position-try-fallbacks:unset;inset:unset;border-color:var(--green);box-shadow:0 25px 70px rgba(0,0,0,0.15),0 10px 25px rgba(0,0,0,0.1)}[popover].inspekt-axe-popover--dragging{cursor:grabbing !important;user-select:none;opacity:0.5 !important;box-shadow:0 30px 80px rgba(0,0,0,0.2),0 12px 30px rgba(0,0,0,0.15) !important;& *{cursor:grabbing !important;user-select:none}}.inspekt-axe-popover__body{&::-webkit-scrollbar{width:8px}&::-webkit-scrollbar-track{background:var(--gray-50)}&::-webkit-scrollbar-thumb{background:var(--gray-300);border-radius:var(--radius-sm);&:hover{background:var(--gray-400)}}}.inspekt-axe-nav{display:flex;align-items:center;justify-content:space-between;gap:var(--space-sm);min-height:40px;padding:var(--space-md) var(--space-lg);background:rgba(31,41,55,0.9);backdrop-filter:blur(10px);border-bottom:1px solid rgba(255,255,255,0.1);border-radius:var(--radius-lg) var(--radius-lg) 0 0}.inspekt-axe-nav__group{display:flex;align-items:center;gap:var(--space-sm);flex-shrink:0}.inspekt-axe-nav__drag-handle{display:none}.inspekt-axe-popover--detached .inspekt-axe-nav__drag-handle{display:flex;align-items:center;gap:var(--space-sm);padding:2px var(--space-sm);border-radius:var(--radius-sm);background:rgba(255,255,255,0.05);cursor:grab}.inspekt-axe-nav__grip{display:flex;color:rgba(255,255,255,0.4)}.inspekt-axe-nav__drag-label{font-size:9px;font-weight:600;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:0.5px;user-select:none}.inspekt-axe-nav__counter{min-width:36px;padding:0 2px;text-align:center;font-size:var(--text-sm);font-weight:600;font-variant-numeric:tabular-nums;color:rgba(255,255,255,0.7)}.inspekt-axe-nav__prev,.inspekt-axe-nav__next,.inspekt-axe-nav__detach,.inspekt-axe-nav__close{width:var(--nav-button-size);height:var(--nav-button-size);padding:0;flex-shrink:0;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:var(--radius-md);color:rgba(255,255,255,0.85);cursor:pointer;transition:all var(--transition-fast);&:hover:not(:disabled){background:rgba(255,255,255,0.15);border-color:rgba(255,255,255,0.25);color:white}&:active:not(:disabled){transform:scale(0.95)}&:focus-visible{outline:2px solid var(--blue-light);outline-offset:2px}&:disabled{opacity:0.3;cursor:not-allowed}}.inspekt-axe-nav__close{border-radius:50%;background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.25);color:#fca5a5;&:hover{background:rgba(239,68,68,0.3);border-color:rgba(239,68,68,0.5);color:#fef2f2}}.inspekt-axe-nav__skip-similar{height:var(--nav-button-size);padding:0 var(--space-md);flex-shrink:0;white-space:nowrap;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:var(--radius-md);font-size:var(--text-xs);font-weight:500;color:rgba(255,255,255,0.85);cursor:pointer;transition:all var(--transition-fast);&:hover{background:rgba(255,255,255,0.15);border-color:rgba(255,255,255,0.25);color:white}&:active{transform:scale(0.97)}&:focus-visible{outline:2px solid var(--blue-light);outline-offset:2px}}.inspekt-axe-nav__skip-similar--active{background:var(--blue);border-color:var(--blue);color:white;&:hover{background:#1d4ed8;border-color:#1d4ed8}}.inspekt-axe-nav__detach--active{background:var(--green);border-color:var(--green);color:white;&:hover{background:#059669;border-color:#059669}}.inspekt-axe-popover--detached .inspekt-axe-nav{cursor:grab}.inspekt-axe-popover--dragging .inspekt-axe-nav{cursor:grabbing !important}.inspekt-axe-popover__header{display:flex;align-items:flex-start;gap:var(--space-lg);padding:var(--space-lg);border-bottom:1px solid var(--color-border)}.inspekt-axe-popover__title{flex:1;margin:0;font-size:var(--text-base);font-weight:600;line-height:1.4;color:var(--color-text)}.inspekt-axe-popover__impact-badge{flex-shrink:0;padding:5px 11px;border-radius:var(--radius-md);font-size:var(--text-xs);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-inverse)}.inspekt-axe-popover__impact-badge--critical{background:var(--impact-critical)}.inspekt-axe-popover__impact-badge--serious{background:var(--impact-serious)}.inspekt-axe-popover__impact-badge--moderate{background:var(--impact-moderate)}.inspekt-axe-popover__impact-badge--minor{background:var(--impact-minor)}.inspekt-axe-popover__tablist{display:flex;gap:0;padding:0 var(--space-lg);background:var(--gray-50);border-bottom:1px solid var(--color-border)}.inspekt-axe-popover__tab{position:relative;top:1px;padding:var(--space-md) var(--space-lg);background:transparent;border:none;border-bottom:2px solid transparent;font-size:var(--text-base);font-weight:500;color:var(--color-text-muted);cursor:pointer;transition:all var(--transition-base);&:hover{color:var(--gray-600);background:rgba(0,0,0,0.02)}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:-2px}}.inspekt-axe-popover__tab--active{color:var(--color-primary);border-bottom-color:var(--color-primary);background:white}.inspekt-axe-popover__tabpanel[hidden]{display:none}.inspekt-axe-popover__markdown-panel{padding:0;overflow:hidden}.inspekt-axe-popover__markdown-textarea{width:100%;height:400px;max-height:calc(80vh - 200px);padding:var(--space-lg);background:white;border:none;outline:none;resize:vertical;overflow-y:auto;font-family:var(--font-mono);font-size:var(--text-sm);line-height:1.6;color:var(--color-text);&::selection{background:#bfdbfe}}.inspekt-axe-popover__body{padding:var(--space-lg);max-height:calc(80vh - 150px);overflow-y:auto}.inspekt-axe-popover__section{margin-bottom:var(--space-lg);&:last-child{margin-bottom:0}}.inspekt-axe-popover__section-label{display:block;margin-bottom:var(--space-sm);font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-muted)}.inspekt-axe-popover__section-content{font-size:var(--text-sm);line-height:1.6;color:var(--gray-600)}.inspekt-axe-popover__failure-summary{padding:var(--space-md);background:var(--red-bg);border-radius:var(--radius-md);font-size:var(--text-sm);line-height:1.6;color:#991b1b}.inspekt-axe-popover__code{padding:var(--space-md);background:var(--gray-50);border:1px solid var(--color-border);border-radius:var(--radius-md);overflow-x:auto;font-family:var(--font-mono);font-size:var(--text-sm);line-height:1.5;color:var(--color-text);white-space:pre-wrap;word-wrap:break-word}.inspekt-axe-popover__selector{padding:var(--space-sm) var(--space-md);background:var(--blue-bg);border:1px solid #bfdbfe;border-radius:var(--radius-md);overflow-x:auto;font-family:var(--font-mono);font-size:var(--text-sm);color:#1e40af;word-wrap:break-word}.inspekt-axe-popover__details{border:1px solid var(--color-border);border-radius:var(--radius-md);overflow:hidden;& summary{display:flex;align-items:center;gap:var(--space-md);padding:var(--space-md);background:var(--gray-50);list-style:none;user-select:none;cursor:pointer;font-size:var(--text-sm);font-weight:500;color:var(--gray-600);&::-webkit-details-marker{display:none}&::before{content:"\\25B6";font-size:10px;color:var(--color-text-muted);transition:transform var(--transition-base)}&:hover{background:var(--gray-100)}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:-2px}}&[open] summary::before{transform:rotate(90deg)}}.inspekt-axe-popover__details-content{padding:var(--space-md);background:white}.inspekt-axe-popover__checks{margin-top:var(--space-md)}.inspekt-axe-popover__check-group{margin-bottom:var(--space-md);&:last-child{margin-bottom:0}}.inspekt-axe-popover__check-title{margin-bottom:var(--space-sm);font-size:var(--text-sm);font-weight:600;color:var(--gray-600)}.inspekt-axe-popover__check-list{list-style:none;padding:0;margin:0}.inspekt-axe-popover__check-item{margin-bottom:var(--space-sm);padding:var(--space-md);background:var(--gray-50);border-radius:var(--radius-sm);font-size:var(--text-sm)}.inspekt-axe-popover__check-item--pass{background:var(--green-bg);border-left-color:var(--green);color:#166534}.inspekt-axe-popover__check-item--fail{background:var(--red-bg);border-left-color:var(--red);color:#991b1b}.inspekt-axe-popover__check-message{display:block;margin-bottom:var(--space-sm);font-weight:500}.inspekt-axe-popover__check-data{display:block;font-size:var(--text-xs);color:var(--color-text-muted)}.inspekt-axe-popover__tags{display:flex;flex-wrap:wrap;gap:var(--space-sm);margin-top:var(--space-md)}.inspekt-axe-popover__tag{display:inline-block;padding:3px var(--space-md);background:var(--gray-100);border:1px solid var(--gray-300);border-radius:9999px;font-size:var(--text-xs);font-weight:500;color:var(--gray-600)}.inspekt-axe-popover__tag--wcag{background:var(--blue-bg);border-color:#bfdbfe;color:#1e40af}.inspekt-axe-popover__footer{padding:var(--space-lg);background:var(--gray-50);border-top:1px solid var(--color-border)}.inspekt-axe-popover__learn-more{display:inline-flex;align-items:center;gap:var(--space-sm);padding:var(--space-md) var(--space-lg);background:var(--color-primary);border-radius:var(--radius-md);text-decoration:none;font-size:var(--text-base);font-weight:500;color:var(--color-text-inverse);transition:background var(--transition-base);&:hover{background:#1d4ed8}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:2px}&::after{content:"\\2192"}}button.inspekt-axe-badge{pointer-events:auto;cursor:pointer;border:2px solid white;background:inherit;transition:transform var(--transition-fast),box-shadow var(--transition-fast);&:hover{transform:scale(1.1);box-shadow:var(--shadow-badge)}&:focus-visible{outline:3px solid var(--color-primary);outline-offset:2px;transform:scale(1.1)}&:active{transform:scale(0.95)}}@keyframes popoverFadeIn{from{opacity:0;transform:scale(0.95)}to{opacity:1;transform:scale(1)}}@keyframes popoverExitUp{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(calc(-1 * var(--animation-distance)))}}@keyframes popoverExitDown{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(var(--animation-distance))}}@keyframes popoverExitLeft{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(calc(-1 * var(--animation-distance)))}}@keyframes popoverExitRight{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(var(--animation-distance))}}@keyframes popoverExitUpLeft{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),calc(-1 * var(--animation-distance)) )}}@keyframes popoverExitUpRight{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate( var(--animation-distance),calc(-1 * var(--animation-distance)) )}}@keyframes popoverExitDownLeft{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),var(--animation-distance) )}}@keyframes popoverExitDownRight{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate(var(--animation-distance),var(--animation-distance))}}@keyframes popoverEnterFromUp{from{opacity:0;transform:translateY(calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translateY(0)}}@keyframes popoverEnterFromDown{from{opacity:0;transform:translateY(var(--animation-distance))}to{opacity:1;transform:translateY(0)}}@keyframes popoverEnterFromLeft{from{opacity:0;transform:translateX(calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translateX(0)}}@keyframes popoverEnterFromRight{from{opacity:0;transform:translateX(var(--animation-distance))}to{opacity:1;transform:translateX(0)}}@keyframes popoverEnterFromUpLeft{from{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),calc(-1 * var(--animation-distance)) )}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromUpRight{from{opacity:0;transform:translate( var(--animation-distance),calc(-1 * var(--animation-distance)) )}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromDownLeft{from{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),var(--animation-distance) )}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromDownRight{from{opacity:0;transform:translate(var(--animation-distance),var(--animation-distance))}to{opacity:1;transform:translate(0,0)}}[popover].inspekt-axe-popover{&.exit-up{animation:popoverExitUp var(--animation-duration) ease-out forwards}&.exit-down{animation:popoverExitDown var(--animation-duration) ease-out forwards}&.exit-left{animation:popoverExitLeft var(--animation-duration) ease-out forwards}&.exit-right{animation:popoverExitRight var(--animation-duration) ease-out forwards}&.exit-up-left{animation:popoverExitUpLeft var(--animation-duration) ease-out forwards}&.exit-up-right{animation:popoverExitUpRight var(--animation-duration) ease-out forwards}&.exit-down-left{animation:popoverExitDownLeft var(--animation-duration) ease-out forwards}&.exit-down-right{animation:popoverExitDownRight var(--animation-duration) ease-out forwards}&.enter-from-up{animation:popoverEnterFromUp var(--animation-duration) ease-out forwards}&.enter-from-down{animation:popoverEnterFromDown var(--animation-duration) ease-out forwards}&.enter-from-left{animation:popoverEnterFromLeft var(--animation-duration) ease-out forwards}&.enter-from-right{animation:popoverEnterFromRight var(--animation-duration) ease-out forwards}&.enter-from-up-left{animation:popoverEnterFromUpLeft var(--animation-duration) ease-out forwards}&.enter-from-up-right{animation:popoverEnterFromUpRight var(--animation-duration) ease-out forwards}&.enter-from-down-left{animation:popoverEnterFromDownLeft var(--animation-duration) ease-out forwards}&.enter-from-down-right{animation:popoverEnterFromDownRight var(--animation-duration) ease-out forwards}}@media (prefers-contrast:high){[popover].inspekt-axe-popover{border:2px solid currentColor}.inspekt-axe-popover__impact-badge{border:1px solid white}}@media (prefers-color-scheme:dark){:root{--color-text:var(--gray-50);--color-text-muted:var(--gray-400);--color-bg:rgba(31,41,55,0.75);--color-bg-subtle:var(--gray-900);--color-border:var(--gray-700);--green-bg:#14532d;--red-bg:#7f1d1d;--blue-bg:#1e3a5f}.inspekt-axe-popover__header{border-bottom-color:var(--gray-700)}.inspekt-axe-popover__tablist{border-bottom-color:var(--gray-700);background:rgba(17,24,39,0.5)}.inspekt-axe-popover__tab{color:var(--gray-400);&:hover{color:var(--gray-300);background:rgba(255,255,255,0.05)}}.inspekt-axe-popover__tab--active{color:var(--blue-light);border-bottom-color:var(--blue-light);background:rgba(31,41,55,0.5)}.inspekt-axe-popover__markdown-textarea{color:var(--gray-200);background:var(--gray-800)}.inspekt-axe-popover__details{& summary{background:var(--gray-900);color:var(--gray-200);&::before{color:var(--gray-400)}&:hover{background:var(--gray-800)}}}.inspekt-axe-popover__details-content{background:var(--gray-800)}.inspekt-axe-popover__check-item{background:var(--gray-900);border-left-color:var(--gray-600);color:var(--gray-300)}.inspekt-axe-popover__failure-summary{color:#fecaca}.inspekt-axe-popover__tag{background:var(--gray-700);border-color:var(--gray-600);color:var(--gray-300)}.inspekt-axe-popover__tag--wcag{background:var(--blue-bg);border-color:var(--blue);color:#93c5fd}.inspekt-axe-popover__selector{background:var(--blue-bg);border-color:var(--blue);color:#93c5fd}.inspekt-axe-popover__footer{border-top-color:var(--gray-700);background:rgba(17,24,39,0.5)}.inspekt-axe-popover__body{&::-webkit-scrollbar-track{background:var(--gray-900)}&::-webkit-scrollbar-thumb{background:var(--gray-600);&:hover{background:var(--gray-500)}}}.inspekt-axe-nav{background:rgba(17,24,39,0.85);border-bottom-color:rgba(17,24,39,0.3)}.inspekt-axe-nav__prev,.inspekt-axe-nav__next,.inspekt-axe-nav__detach{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover:not(:disabled){background:var(--gray-700);border-color:var(--gray-500)}}.inspekt-axe-nav__skip-similar{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover{background:var(--gray-700);border-color:var(--gray-500)}}.inspekt-axe-nav__skip-similar--active{background:var(--blue);border-color:var(--blue);color:white}.inspekt-axe-nav__close{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover{background:#7f1d1d;border-color:var(--red);color:#fecaca}}.inspekt-axe-nav__counter{color:var(--gray-400)}}`;
        }


    } catch (error) {
        console.error('[Inspekt IBM] Error:', error);
        return {
            ok: false,
            error: error.message || String(error)
        };
    }
})();
