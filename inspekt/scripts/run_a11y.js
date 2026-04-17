// Inspekt Unified Accessibility Audit Script
// Runs any combination of engines (axe, eac, hcs, sia), creating unified badges
// Note: Engine libraries are injected before this script based on config.__engines
// Note: shared-popover/popover-core.js is injected before this script
(async function() {
    try {
        // Configuration from Python
        const config = __A11Y_CONFIG__;

        const showBadges = config.__showBadges !== false;
        const interactiveBadges = config.__interactiveBadges === true;
        const devCss = config.__devCss === true;
        const engines = config.__engines || ['axe', 'eac'];  // Default for backwards compatibility
        const includeRecommendations = config.__includeRecommendations === true;

        console.log('[Inspekt A11Y] Config:', { showBadges, interactiveBadges, devCss, engines, includeRecommendations });

        // Clean config flags
        delete config.__showBadges;
        delete config.__interactiveBadges;
        delete config.__devCss;
        delete config.__engines;
        delete config.__includeRecommendations;

        // Verify required libraries are available based on configured engines
        if (engines.includes('axe') && typeof axe === 'undefined') {
            throw new Error('axe-core library not found');
        }
        if (engines.includes('eac') && typeof ace === 'undefined') {
            throw new Error('IBM Equal Access (ace) library not found');
        }
        if (engines.includes('hcs') && typeof HTMLCS === 'undefined') {
            throw new Error('HTML CodeSniffer (HTMLCS) library not found');
        }
        if (engines.includes('sia') && typeof window.Alfa === 'undefined') {
            throw new Error('Siteimprove Alfa library not found');
        }
        if (!window.__inspektPopoverCore__) {
            throw new Error('Shared popover core not found');
        }

        const popoverCore = window.__inspektPopoverCore__;
        const popoverContent = window.__inspektPopoverContent__;

        if (!popoverContent) {
            throw new Error('Shared popover content not found');
        }

        // Initialize popover core with active engines
        popoverCore.initSkippedRuleIds(engines);

        // ============================================================
        // SEVERITY MAPPING
        // ============================================================

        const SEVERITY_PRIORITY = {
            'critical': 4,
            'serious': 3,
            'moderate': 2,
            'minor': 1
        };

        // Per-engine severity mapping to unified format
        const ENGINE_SEVERITY_MAPPERS = {
            axe: (issue) => issue.impact || 'minor',
            eac: (issue) => ({
                'violation': 'critical',
                'potentialviolation': 'serious',
                'recommendation': 'moderate',
                'potentialrecommendation': 'minor',
                'manual': 'minor'
            })[issue.level] || 'minor',
            hcs: (issue) => ({
                1: 'critical',  // Error
                2: 'moderate',  // Warning
                3: 'minor'      // Notice
            })[issue.type] || 'minor',
            sia: (issue) => ({
                'failed': 'serious',
                'cantTell': 'moderate',
                'passed': 'minor',
                'inapplicable': 'minor'
            })[issue.outcome] || 'moderate'
        };

        // Engine display names for UI
        const ENGINE_DISPLAY_NAMES = {
            axe: 'Axe',
            eac: 'IBM Equal Access',
            hcs: 'HTML CodeSniffer',
            sia: 'Siteimprove Alfa'
        };

        function getHighestSeverity(sources) {
            let highest = 'minor';
            let highestPriority = 0;

            // Iterate over all engines dynamically
            for (const engineId of Object.keys(sources)) {
                const engineIssues = sources[engineId] || [];
                const mapper = ENGINE_SEVERITY_MAPPERS[engineId];
                if (!mapper) continue;

                engineIssues.forEach(issue => {
                    const severity = mapper(issue);
                    const priority = SEVERITY_PRIORITY[severity] || 0;
                    if (priority > highestPriority) {
                        highestPriority = priority;
                        highest = severity;
                    }
                });
            }

            return highest;
        }

        // Helper to create empty sources object for configured engines
        function createEmptySources() {
            const sources = {};
            engines.forEach(e => sources[e] = []);
            return sources;
        }

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
        // RUN ENGINE AUDITS (conditional based on engines array)
        // ============================================================

        // Store results per engine
        const engineResults = {};

        // --- AXE AUDIT ---
        if (engines.includes('axe')) {
            console.log('[Inspekt A11Y] Running axe-core…');
            const axeConfig = {
                resultTypes: ['violations', 'incomplete'],
                elementRef: true,
                runOnly: config.axeRunOnly || { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }
            };

            // Build context with exclude selectors (to skip Inspekt UI elements)
            const axeExclude = config.axeExclude || [];
            const axeContext = axeExclude.length > 0
                ? { exclude: axeExclude }
                : document;

            try {
                const axeResults = await axe.run(axeContext, axeConfig);
                engineResults.axe = {
                    violations: axeResults.violations,
                    incomplete: axeResults.incomplete
                };
                console.log('[Inspekt A11Y] Axe complete:', {
                    violations: axeResults.violations.length,
                    incomplete: axeResults.incomplete.length
                });
            } catch (axeError) {
                console.warn('[Inspekt A11Y] Axe error:', axeError.message);
                engineResults.axe = { violations: [], incomplete: [] };
            }
        }

        // --- IBM EQUAL ACCESS (EAC) AUDIT ---
        if (engines.includes('eac')) {
            console.log('[Inspekt A11Y] Running IBM Equal Access…');
            try {
                const checker = new ace.Checker();
                const guidelines = config.ibmGuidelines || ['WCAG_2_2'];
                const report = await checker.check(document, guidelines);

                // Process IBM results (filter out Inspekt UI elements)
                const rawEacResults = (report.results || []).filter(r => {
                    const [policy, confidence] = r.value || [];
                    return confidence === 'FAIL' || confidence === 'POTENTIAL' || confidence === 'MANUAL';
                }).map(r => {
                    const [policy, confidence] = r.value || [];
                    let level = 'recommendation';
                    if (confidence === 'FAIL') {
                        level = policy === 'VIOLATION' ? 'violation' : 'potentialviolation';
                    } else if (confidence === 'POTENTIAL') {
                        level = 'potentialviolation';
                    } else if (confidence === 'MANUAL') {
                        level = 'manual';
                    }

                    return {
                        ruleId: r.ruleId,
                        level: level,
                        message: r.message,
                        node: r.node,
                        snippet: r.snippet || (r.node ? r.node.outerHTML?.substring(0, 150) : '')
                    };
                });

                // Filter out violations on Inspekt UI elements
                const filteredCount = rawEacResults.filter(r => isInspektUIElement(r.node)).length;
                engineResults.eac = rawEacResults.filter(r => !isInspektUIElement(r.node));

                console.log('[Inspekt A11Y] IBM complete:', {
                    issues: engineResults.eac.length,
                    filteredInspektUI: filteredCount
                });
            } catch (ibmError) {
                console.warn('[Inspekt A11Y] IBM error:', ibmError.message);
                engineResults.eac = [];
            }
        }

        // --- HTML CODESNIFFER (HCS) AUDIT ---
        if (engines.includes('hcs')) {
            console.log('[Inspekt A11Y] Running HTML CodeSniffer…');
            try {
                const hcsResults = await new Promise((resolve, reject) => {
                    const standard = config.hcsStandard || 'WCAG2AA';
                    HTMLCS.process(standard, document, (error) => {
                        if (error) {
                            reject(new Error(error));
                            return;
                        }
                        resolve(HTMLCS.getMessages());
                    });
                });

                // Process HCS results - filter for errors and warnings (and exclude Inspekt UI)
                const rawHcsResults = hcsResults.filter(msg => msg.type <= 2).map(msg => ({
                    type: msg.type,  // 1=Error, 2=Warning, 3=Notice
                    code: msg.code,
                    msg: msg.msg,
                    node: msg.element,
                    snippet: msg.element ? msg.element.outerHTML?.substring(0, 150) : ''
                }));

                // Filter out violations on Inspekt UI elements
                const filteredCount = rawHcsResults.filter(r => isInspektUIElement(r.node)).length;
                engineResults.hcs = rawHcsResults.filter(r => !isInspektUIElement(r.node));

                console.log('[Inspekt A11Y] HCS complete:', {
                    issues: engineResults.hcs.length,
                    filteredInspektUI: filteredCount
                });
            } catch (hcsError) {
                console.warn('[Inspekt A11Y] HCS error:', hcsError.message);
                engineResults.hcs = [];
            }
        }

        // --- SITEIMPROVE ALFA (SIA) AUDIT ---
        if (engines.includes('sia')) {
            console.log('[Inspekt A11Y] Running Siteimprove Alfa…');
            try {
                // Alfa uses runAudit() which returns outcomes array
                const conformance = config.siaConformance || 'WCAG2.2:AA';
                const alfaConfig = {
                    conformance: conformance,
                    includePassed: false,
                    includeCantTell: true,
                    includeInapplicable: false
                };

                const rawOutcomes = await window.Alfa.runAudit(alfaConfig);

                // Helper function to resolve XPath to DOM element
                const resolveXPath = (xpath) => {
                    if (!xpath) return null;
                    try {
                        const result = document.evaluate(
                            xpath,
                            document,
                            null,
                            XPathResult.FIRST_ORDERED_NODE_TYPE,
                            null
                        );
                        return result.singleNodeValue;
                    } catch (e) {
                        // XPath resolution can fail for some paths
                        return null;
                    }
                };

                // Filter for failed/cantTell outcomes and resolve elements via XPath
                let elementsResolved = 0;
                const rawSiaResults = rawOutcomes
                    .filter(r => r.outcome === 'failed' || r.outcome === 'cantTell')
                    .map(r => {
                        // Try to resolve element from XPath path
                        let node = null;
                        if (r.path) {
                            node = resolveXPath(r.path);
                            if (node) elementsResolved++;
                        }

                        return {
                            outcome: r.outcome,
                            rule: r.rule,
                            title: r.ruleTitle || r.title || r.rule,
                            message: r.message || '',
                            node: node,  // Resolved DOM element from XPath
                            target: r.target ? String(r.target).substring(0, 200) : '',
                            path: r.path,  // Keep path for debugging
                            requirements: r.ruleRequirements || r.requirements || []
                        };
                    });

                // Filter out violations on Inspekt UI elements
                const filteredCount = rawSiaResults.filter(r => isInspektUIElement(r.node)).length;
                engineResults.sia = rawSiaResults.filter(r => !isInspektUIElement(r.node));

                console.log('[Inspekt A11Y] Alfa complete:', {
                    issues: engineResults.sia.length,
                    elementsResolved: elementsResolved,
                    filteredInspektUI: filteredCount,
                    note: elementsResolved > 0 ? 'Alfa issues can be visualized with badges' : 'No elements could be resolved'
                });
            } catch (siaError) {
                console.warn('[Inspekt A11Y] Alfa error:', siaError.message);
                engineResults.sia = [];
            }
        }

        // ============================================================
        // MERGE VIOLATIONS BY ELEMENT
        // ============================================================

        // Map: element -> unified violation data
        const elementMap = new Map();

        // Helper to ensure element entry exists
        function ensureElementEntry(element) {
            if (!element || element.nodeType !== 1) return null;
            if (!elementMap.has(element)) {
                elementMap.set(element, {
                    element: element,
                    sources: createEmptySources()
                });
            }
            return elementMap.get(element);
        }

        // Process Axe results (violations + incomplete)
        if (engineResults.axe) {
            engineResults.axe.violations.forEach(violation => {
                violation.nodes.forEach(node => {
                    const entry = ensureElementEntry(node.element);
                    if (!entry) return;

                    entry.sources.axe.push({
                        ruleId: violation.id,
                        impact: violation.impact,
                        help: violation.help,
                        description: violation.description,
                        helpUrl: violation.helpUrl,
                        failureSummary: node.failureSummary,
                        html: node.html,
                        target: node.target,
                        tags: violation.tags,
                        any: node.any,
                        all: node.all,
                        none: node.none
                    });
                });
            });

            engineResults.axe.incomplete.forEach(violation => {
                violation.nodes.forEach(node => {
                    const entry = ensureElementEntry(node.element);
                    if (!entry) return;

                    entry.sources.axe.push({
                        ruleId: violation.id,
                        impact: 'moderate',
                        help: violation.help,
                        description: violation.description,
                        helpUrl: violation.helpUrl,
                        isIncomplete: true,
                        failureSummary: node.failureSummary,
                        html: node.html,
                        target: node.target,
                        tags: violation.tags
                    });
                });
            });
        }

        // Process IBM (EAC) results
        if (engineResults.eac) {
            engineResults.eac.forEach(issue => {
                const entry = ensureElementEntry(issue.node);
                if (!entry) return;

                entry.sources.eac.push({
                    ruleId: issue.ruleId,
                    level: issue.level,
                    message: issue.message,
                    snippet: issue.snippet
                });
            });
        }

        // Process HTML CodeSniffer (HCS) results
        if (engineResults.hcs) {
            engineResults.hcs.forEach(issue => {
                const entry = ensureElementEntry(issue.node);
                if (!entry) return;

                entry.sources.hcs.push({
                    type: issue.type,
                    code: issue.code,
                    msg: issue.msg,
                    snippet: issue.snippet
                });
            });
        }

        // Process Siteimprove Alfa (SIA) results
        if (engineResults.sia) {
            engineResults.sia.forEach(issue => {
                const entry = ensureElementEntry(issue.node);
                if (!entry) return;

                entry.sources.sia.push({
                    outcome: issue.outcome,
                    rule: issue.rule,
                    title: issue.title,
                    message: issue.message,
                    path: issue.path,
                    requirements: issue.requirements
                });
            });
        }

        // Helper to check if an issue is a recommendation (not a violation)
        function isRecommendationIssue(engineId, issue) {
            if (engineId === 'eac') {
                return ['recommendation', 'potentialrecommendation'].includes(issue.level);
            }
            if (engineId === 'hcs') {
                return issue.type === 3;  // type 3 = notice
            }
            if (engineId === 'sia') {
                return issue.outcome === 'cantTell';
            }
            if (engineId === 'axe') {
                return issue.isIncomplete === true;
            }
            return false;
        }

        // Check if all issues for an element are recommendations (no violations)
        function isRecommendationOnly(sources) {
            let hasAnyIssue = false;
            for (const engineId of Object.keys(sources)) {
                const issues = sources[engineId] || [];
                for (const issue of issues) {
                    hasAnyIssue = true;
                    if (!isRecommendationIssue(engineId, issue)) {
                        return false;  // Found a violation, not recommendation-only
                    }
                }
            }
            return hasAnyIssue;  // Only true if we have issues and all are recommendations
        }

        // Convert to array and calculate highest severity
        const unifiedViolations = Array.from(elementMap.values()).map((data, index) => {
            const severity = getHighestSeverity(data.sources);
            const isRecommendation = isRecommendationOnly(data.sources);

            // Calculate per-engine counts and flags dynamically
            const engineCounts = {};
            const hasEngine = {};
            let totalCount = 0;

            engines.forEach(engineId => {
                const count = (data.sources[engineId] || []).length;
                engineCounts[engineId] = count;
                hasEngine[engineId] = count > 0;
                totalCount += count;
            });

            return {
                index: index,
                badgeId: `inspekt-badge-${index + 1}`,
                popoverId: `inspekt-popover-${index + 1}`,
                element: data.element,
                sources: data.sources,
                highestImpact: severity,
                isRecommendation: isRecommendation,  // Track if this is recommendation-only
                engineCounts: engineCounts,
                hasEngine: hasEngine,
                totalCount: totalCount,
                // Backwards compatibility
                hasAxe: hasEngine.axe || false,
                hasIbm: hasEngine.eac || false,
                axeCount: engineCounts.axe || 0,
                ibmCount: engineCounts.eac || 0
            };
        });

        console.log('[Inspekt A11Y] Unified violations:', unifiedViolations.length);

        // ============================================================
        // INJECT BADGES AND POPOVERS
        // ============================================================

        // Build engine stats for return value
        function buildEngineStats() {
            const stats = {};
            engines.forEach(engineId => {
                if (engineResults[engineId]) {
                    if (engineId === 'axe') {
                        stats[engineId] = {
                            count: (engineResults.axe.violations || []).length,
                            violations: (engineResults.axe.violations || []).length,
                            incomplete: (engineResults.axe.incomplete || []).length
                        };
                    } else {
                        stats[engineId] = {
                            count: Array.isArray(engineResults[engineId]) ? engineResults[engineId].length : 0
                        };
                    }
                }
            });
            return stats;
        }

        // Always remove ALL existing Inspekt UI elements (prevents accumulation on re-runs)
        // This includes badges/popovers from unified, axe-only, and ibm-only scripts
        INSPEKT_UI_SELECTORS.forEach(selector => {
            document.querySelectorAll(selector).forEach(el => el.remove());
        });

        // Reset popover state with configured engines
        popoverCore.reset(engines);

        if (!showBadges || unifiedViolations.length === 0) {
            return {
                ok: true,
                result: {
                    url: window.location.href,
                    engines: engines,
                    engineStats: buildEngineStats(),
                    unifiedElements: unifiedViolations.length,
                    badgeStats: null,
                    // Backwards compatibility
                    axeViolations: engineResults.axe?.violations?.length || 0,
                    axeIncomplete: engineResults.axe?.incomplete?.length || 0,
                    ibmIssues: engineResults.eac?.length || 0
                }
            };
        }

        // Inject CSS
        await injectUnifiedCSS(devCss);

        // Create badges and popovers
        let badgeCount = 0;
        unifiedViolations.forEach((violation, idx) => {
            const badgeNumber = idx + 1;

            // Create badge
            const badge = createUnifiedBadge(violation, badgeNumber);
            if (!badge) return;

            // Create popover using shared popover content module
            const popover = popoverContent.createUnifiedPopover(violation, badgeNumber, engines, popoverCore);

            document.body.appendChild(badge);
            document.body.appendChild(popover);

            // Add to popover state
            popoverCore.addViolation(violation);

            // Bind badge click
            if (interactiveBadges) {
                badge.addEventListener('click', (e) => {
                    e.stopPropagation();
                    popoverCore.navigateToViolation(idx);
                });
            }

            badgeCount++;
        });

        console.log(`[Inspekt A11Y] Created ${badgeCount} unified badges`);

        // Calculate per-engine badge breakdown
        const perEngineBadges = {};
        engines.forEach(engineId => {
            perEngineBadges[engineId] = unifiedViolations.filter(v =>
                v.hasEngine[engineId] && Object.values(v.hasEngine).filter(Boolean).length === 1
            ).length;
        });

        const withMultipleSources = unifiedViolations.filter(v =>
            Object.values(v.hasEngine).filter(Boolean).length > 1
        ).length;

        return {
            ok: true,
            result: {
                url: window.location.href,
                engines: engines,
                engineStats: buildEngineStats(),
                unifiedElements: unifiedViolations.length,
                badgeStats: {
                    badgesCreated: badgeCount,
                    perEngine: perEngineBadges,
                    withMultipleSources: withMultipleSources,
                    // Backwards compatibility
                    withBothSources: unifiedViolations.filter(v => v.hasAxe && v.hasIbm).length,
                    axeOnly: unifiedViolations.filter(v => v.hasAxe && !v.hasIbm).length,
                    ibmOnly: unifiedViolations.filter(v => !v.hasAxe && v.hasIbm).length
                },
                // Backwards compatibility
                axeViolations: engineResults.axe?.violations?.length || 0,
                axeIncomplete: engineResults.axe?.incomplete?.length || 0,
                ibmIssues: engineResults.eac?.length || 0
            }
        };

        // ============================================================
        // HELPER FUNCTIONS
        // ============================================================

        function escapeHtml(text) {
            if (typeof text !== 'string') return text || '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        async function injectUnifiedCSS(devMode) {
            const existingStyles = document.getElementById('inspekt-unified-styles');
            if (existingStyles) return;

            if (devMode) {
                // Dev mode: load from external server
                const link = document.createElement('link');
                link.id = 'inspekt-unified-styles';
                link.rel = 'stylesheet';
                link.href = 'http://localhost:3456/unified-popover/index.css';
                document.head.appendChild(link);
                await new Promise(resolve => setTimeout(resolve, 100));
            } else {
                // Production: use inline CSS (minified popover CSS)
                const style = document.createElement('style');
                style.id = 'inspekt-unified-styles';
                style.textContent = getUnifiedCSS();
                document.head.appendChild(style);
            }

            // Always inject badge CSS (needs !important overrides)
            const existingBadgeStyles = document.getElementById('inspekt-badge-styles');
            if (!existingBadgeStyles) {
                const badgeStyle = document.createElement('style');
                badgeStyle.id = 'inspekt-badge-styles';
                badgeStyle.textContent = getBadgeCSS();
                document.head.appendChild(badgeStyle);
            }
        }

        /**
         * Returns the unified popover CSS (minified).
         * This includes both base popover CSS and source-tabs for multi-engine support.
         * To update: run `python scripts/build_popover_css.py --apply`
         * @returns {string} CSS content
         */
        function getUnifiedCSS() {
            return `@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap");:root{--gray-50:#f9fafb;--gray-100:#f3f4f6;--gray-200:#e5e7eb;--gray-300:#d1d5db;--gray-400:#9ca3af;--gray-500:#6b7280;--gray-600:#4b5563;--gray-700:#374151;--gray-800:#1f2937;--gray-900:#111827;--blue:#2563eb;--blue-light:#60a5fa;--blue-bg:#eff6ff;--green:#10b981;--green-bg:#f0fdf4;--red:#dc2626;--red-bg:#fef2f2;--orange:#ea580c;--color-text:var(--gray-800);--color-text-muted:var(--gray-500);--color-text-inverse:#ffffff;--color-bg:rgba(255,255,255,0.75);--color-bg-subtle:var(--gray-50);--color-border:var(--gray-200);--color-primary:var(--blue);--impact-critical:var(--red);--impact-serious:var(--orange);--impact-moderate:var(--blue);--impact-minor:var(--gray-500);--font-sans:"Inter",-apple-system,BlinkMacSystemFont,system-ui,sans-serif;--font-mono:ui-monospace,SFMono-Regular,monospace;--text-xs:11px;--text-sm:13px;--text-base:14px;--text-lg:16px;--space-sm:4px;--space-md:8px;--space-lg:16px;--radius-sm:4px;--radius-md:8px;--radius-lg:12px;--shadow-popover:0 20px 60px rgba(0,0,0,0.12),0 8px 20px rgba(0,0,0,0.08);--shadow-badge:0 3px 6px rgba(0,0,0,0.5);--popover-max-width:480px;--popover-min-width:380px;--popover-max-height:80vh;--nav-button-size:28px;--transition-fast:0.15s ease;--transition-base:0.2s ease;--animation-duration:0.15s;--animation-distance:20px;--blur-popover:blur(20px) saturate(180%)}.visually-hidden{opacity:0 !important;clip-path:inset(100%);clip:rect(1px,1px,1px,1px);height:1px;overflow:hidden;position:absolute;white-space:nowrap;width:1px}[popover].inspekt-axe-popover{position:absolute;margin:0;inset:unset;position-area:block-end span-inline-end;position-try-fallbacks:--bottom-left,--top-right,--top-left,flip-block,flip-inline;max-width:var(--popover-max-width);min-width:var(--popover-min-width);max-height:var(--popover-max-height);width:max-content;background:var(--color-bg);border:2px solid var(--color-border);border-radius:var(--radius-lg);box-shadow:var(--shadow-popover);backdrop-filter:var(--blur-popover);-webkit-backdrop-filter:var(--blur-popover);font-family:var(--font-sans);font-size:var(--text-lg);line-height:1.5;color:var(--color-text);padding:0;overflow:hidden;overscroll-behavior:contain;transition:opacity var(--transition-base),box-shadow var(--transition-base);&:popover-open{animation:popoverFadeIn var(--animation-duration) ease-out}}@position-try --bottom-left{position-area:block-end span-inline-start}@position-try --top-right{position-area:block-start span-inline-end}@position-try --top-left{position-area:block-start span-inline-start}[popover].inspekt-axe-popover--detached{position:fixed;position-anchor:unset;position-area:unset;position-try-fallbacks:unset;inset:unset;border-color:var(--green);box-shadow:0 25px 70px rgba(0,0,0,0.15),0 10px 25px rgba(0,0,0,0.1)}[popover].inspekt-axe-popover--dragging{cursor:grabbing !important;user-select:none;opacity:0.5 !important;box-shadow:0 30px 80px rgba(0,0,0,0.2),0 12px 30px rgba(0,0,0,0.15) !important;& *{cursor:grabbing !important;user-select:none}}.inspekt-axe-popover__body{&::-webkit-scrollbar{width:8px}&::-webkit-scrollbar-track{background:var(--gray-50)}&::-webkit-scrollbar-thumb{background:var(--gray-300);border-radius:var(--radius-sm);&:hover{background:var(--gray-400)}}}.inspekt-axe-nav{display:flex;align-items:center;justify-content:space-between;gap:var(--space-sm);min-height:40px;padding:var(--space-md) var(--space-lg);background:rgba(31,41,55,0.9);backdrop-filter:blur(10px);border-bottom:1px solid rgba(255,255,255,0.1);border-radius:var(--radius-lg) var(--radius-lg) 0 0}.inspekt-axe-nav__group{display:flex;align-items:center;gap:var(--space-sm);flex-shrink:0}.inspekt-axe-nav__drag-handle{display:none}.inspekt-axe-popover--detached .inspekt-axe-nav__drag-handle{display:flex;align-items:center;gap:var(--space-sm);padding:2px var(--space-sm);border-radius:var(--radius-sm);background:rgba(255,255,255,0.05);cursor:grab}.inspekt-axe-nav__grip{display:flex;color:rgba(255,255,255,0.4)}.inspekt-axe-nav__drag-label{font-size:9px;font-weight:600;color:rgba(255,255,255,0.5);text-transform:uppercase;letter-spacing:0.5px;user-select:none}.inspekt-axe-nav__counter{min-width:36px;padding:0 2px;text-align:center;font-size:var(--text-sm);font-weight:600;font-variant-numeric:tabular-nums;color:rgba(255,255,255,0.7)}.inspekt-axe-nav__prev,.inspekt-axe-nav__next,.inspekt-axe-nav__detach,.inspekt-axe-nav__close{width:var(--nav-button-size);height:var(--nav-button-size);padding:0;flex-shrink:0;display:flex;align-items:center;justify-content:center;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:var(--radius-md);color:rgba(255,255,255,0.85);cursor:pointer;transition:all var(--transition-fast);&:hover:not(:disabled){background:rgba(255,255,255,0.15);border-color:rgba(255,255,255,0.25);color:white}&:active:not(:disabled){transform:scale(0.95)}&:focus-visible{outline:2px solid var(--blue-light);outline-offset:2px}&:disabled{opacity:0.3;cursor:not-allowed}}.inspekt-axe-nav__close{border-radius:50%;background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.25);color:#fca5a5;&:hover{background:rgba(239,68,68,0.3);border-color:rgba(239,68,68,0.5);color:#fef2f2}}.inspekt-axe-nav__skip-similar{height:var(--nav-button-size);padding:0 var(--space-md);flex-shrink:0;white-space:nowrap;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.12);border-radius:var(--radius-md);font-size:var(--text-xs);font-weight:500;color:rgba(255,255,255,0.85);cursor:pointer;transition:all var(--transition-fast);&:hover{background:rgba(255,255,255,0.15);border-color:rgba(255,255,255,0.25);color:white}&:active{transform:scale(0.97)}&:focus-visible{outline:2px solid var(--blue-light);outline-offset:2px}}.inspekt-axe-nav__skip-similar--active{background:var(--blue);border-color:var(--blue);color:white;&:hover{background:#1d4ed8;border-color:#1d4ed8}}.inspekt-axe-nav__detach--active{background:var(--green);border-color:var(--green);color:white;&:hover{background:#059669;border-color:#059669}}.inspekt-axe-popover--detached .inspekt-axe-nav{cursor:grab}.inspekt-axe-popover--dragging .inspekt-axe-nav{cursor:grabbing !important}.inspekt-axe-popover__header{display:flex;align-items:flex-start;gap:var(--space-lg);padding:var(--space-lg);border-bottom:1px solid var(--color-border)}.inspekt-axe-popover__title{flex:1;margin:0;font-size:var(--text-base);font-weight:600;line-height:1.4;color:var(--color-text)}.inspekt-axe-popover__impact-badge{flex-shrink:0;padding:5px 11px;border-radius:var(--radius-md);font-size:var(--text-xs);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-inverse)}.inspekt-axe-popover__impact-badge--critical{background:var(--impact-critical)}.inspekt-axe-popover__impact-badge--serious{background:var(--impact-serious)}.inspekt-axe-popover__impact-badge--moderate{background:var(--impact-moderate)}.inspekt-axe-popover__impact-badge--minor{background:var(--impact-minor)}.inspekt-axe-popover__tablist{display:flex;gap:0;padding:0 var(--space-lg);background:var(--gray-50);border-bottom:1px solid var(--color-border)}.inspekt-axe-popover__tab{position:relative;top:1px;padding:var(--space-md) var(--space-lg);background:transparent;border:none;border-bottom:2px solid transparent;font-size:var(--text-base);font-weight:500;color:var(--color-text-muted);cursor:pointer;transition:all var(--transition-base);&:hover{color:var(--gray-600);background:rgba(0,0,0,0.02)}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:-2px}}.inspekt-axe-popover__tab--active{color:var(--color-primary);border-bottom-color:var(--color-primary);background:white}.inspekt-axe-popover__tabpanel[hidden]{display:none}.inspekt-axe-popover__markdown-panel{padding:0;overflow:hidden}.inspekt-axe-popover__markdown-textarea{width:100%;height:400px;max-height:calc(80vh - 200px);padding:var(--space-lg);background:white;border:none;outline:none;resize:vertical;overflow-y:auto;font-family:var(--font-mono);font-size:var(--text-sm);line-height:1.6;color:var(--color-text);&::selection{background:#bfdbfe}}.inspekt-axe-popover__body{padding:var(--space-lg);max-height:calc(80vh - 150px);overflow-y:auto}.inspekt-axe-popover__section{margin-bottom:var(--space-lg);&:last-child{margin-bottom:0}}.inspekt-axe-popover__section-label{display:block;margin-bottom:var(--space-sm);font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-muted)}.inspekt-axe-popover__section-content{font-size:var(--text-sm);line-height:1.6;color:var(--gray-600)}.inspekt-axe-popover__failure-summary{padding:var(--space-md);background:var(--red-bg);border-radius:var(--radius-md);font-size:var(--text-sm);line-height:1.6;color:#991b1b}.inspekt-axe-popover__code{padding:var(--space-md);background:var(--gray-50);border:1px solid var(--color-border);border-radius:var(--radius-md);overflow-x:auto;font-family:var(--font-mono);font-size:var(--text-sm);line-height:1.5;color:var(--color-text);white-space:pre-wrap;word-wrap:break-word}.inspekt-axe-popover__selector{padding:var(--space-sm) var(--space-md);background:var(--blue-bg);border:1px solid #bfdbfe;border-radius:var(--radius-md);overflow-x:auto;font-family:var(--font-mono);font-size:var(--text-sm);color:#1e40af;word-wrap:break-word}.inspekt-axe-popover__details{border:1px solid var(--color-border);border-radius:var(--radius-md);overflow:hidden;& summary{display:flex;align-items:center;gap:var(--space-md);padding:var(--space-md);background:var(--gray-50);list-style:none;user-select:none;cursor:pointer;font-size:var(--text-sm);font-weight:500;color:var(--gray-600);&::-webkit-details-marker{display:none}&::before{content:"\\25B6";font-size:10px;color:var(--color-text-muted);transition:transform var(--transition-base)}&:hover{background:var(--gray-100)}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:-2px}}&[open] summary::before{transform:rotate(90deg)}}.inspekt-axe-popover__details-content{padding:var(--space-md);background:white}.inspekt-axe-popover__checks{margin-top:var(--space-md)}.inspekt-axe-popover__check-group{margin-bottom:var(--space-md);&:last-child{margin-bottom:0}}.inspekt-axe-popover__check-title{margin-bottom:var(--space-sm);font-size:var(--text-sm);font-weight:600;color:var(--gray-600)}.inspekt-axe-popover__check-list{list-style:none;padding:0;margin:0}.inspekt-axe-popover__check-item{margin-bottom:var(--space-sm);padding:var(--space-md);background:var(--gray-50);border-radius:var(--radius-sm);font-size:var(--text-sm)}.inspekt-axe-popover__check-item--pass{background:var(--green-bg);border-left-color:var(--green);color:#166534}.inspekt-axe-popover__check-item--fail{background:var(--red-bg);border-left-color:var(--red);color:#991b1b}.inspekt-axe-popover__check-message{display:block;margin-bottom:var(--space-sm);font-weight:500}.inspekt-axe-popover__check-data{display:block;font-size:var(--text-xs);color:var(--color-text-muted)}.inspekt-axe-popover__tags{display:flex;flex-wrap:wrap;gap:var(--space-sm);margin-top:var(--space-md)}.inspekt-axe-popover__tag{display:inline-block;padding:3px var(--space-md);background:var(--gray-100);border:1px solid var(--gray-300);border-radius:9999px;font-size:var(--text-xs);font-weight:500;color:var(--gray-600)}.inspekt-axe-popover__tag--wcag{background:var(--blue-bg);border-color:#bfdbfe;color:#1e40af}.inspekt-axe-popover__footer{padding:var(--space-lg);background:var(--gray-50);border-top:1px solid var(--color-border)}.inspekt-axe-popover__learn-more{display:inline-flex;align-items:center;gap:var(--space-sm);padding:var(--space-md) var(--space-lg);background:var(--color-primary);border-radius:var(--radius-md);text-decoration:none;font-size:var(--text-base);font-weight:500;color:var(--color-text-inverse);transition:background var(--transition-base);&:hover{background:#1d4ed8}&:focus-visible{outline:2px solid var(--color-primary);outline-offset:2px}&::after{content:"\\2192"}}button.inspekt-axe-badge{pointer-events:auto;cursor:pointer;border:2px solid white;background:inherit;transition:transform var(--transition-fast),box-shadow var(--transition-fast);&:hover{transform:scale(1.1);box-shadow:var(--shadow-badge)}&:focus-visible{outline:3px solid var(--color-primary);outline-offset:2px;transform:scale(1.1)}&:active{transform:scale(0.95)}}@keyframes popoverFadeIn{from{opacity:0;transform:scale(0.95)}to{opacity:1;transform:scale(1)}}@keyframes popoverExitUp{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(calc(-1 * var(--animation-distance)))}}@keyframes popoverExitDown{from{opacity:1;transform:translateY(0)}to{opacity:0;transform:translateY(var(--animation-distance))}}@keyframes popoverExitLeft{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(calc(-1 * var(--animation-distance)))}}@keyframes popoverExitRight{from{opacity:1;transform:translateX(0)}to{opacity:0;transform:translateX(var(--animation-distance))}}@keyframes popoverExitUpLeft{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),calc(-1 * var(--animation-distance)) )}}@keyframes popoverExitUpRight{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate( var(--animation-distance),calc(-1 * var(--animation-distance)) )}}@keyframes popoverExitDownLeft{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),var(--animation-distance) )}}@keyframes popoverExitDownRight{from{opacity:1;transform:translate(0,0)}to{opacity:0;transform:translate(var(--animation-distance),var(--animation-distance))}}@keyframes popoverEnterFromUp{from{opacity:0;transform:translateY(calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translateY(0)}}@keyframes popoverEnterFromDown{from{opacity:0;transform:translateY(var(--animation-distance))}to{opacity:1;transform:translateY(0)}}@keyframes popoverEnterFromLeft{from{opacity:0;transform:translateX(calc(-1 * var(--animation-distance)))}to{opacity:1;transform:translateX(0)}}@keyframes popoverEnterFromRight{from{opacity:0;transform:translateX(var(--animation-distance))}to{opacity:1;transform:translateX(0)}}@keyframes popoverEnterFromUpLeft{from{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),calc(-1 * var(--animation-distance)) )}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromUpRight{from{opacity:0;transform:translate( var(--animation-distance),calc(-1 * var(--animation-distance)) )}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromDownLeft{from{opacity:0;transform:translate( calc(-1 * var(--animation-distance)),var(--animation-distance) )}to{opacity:1;transform:translate(0,0)}}@keyframes popoverEnterFromDownRight{from{opacity:0;transform:translate(var(--animation-distance),var(--animation-distance))}to{opacity:1;transform:translate(0,0)}}[popover].inspekt-axe-popover{&.exit-up{animation:popoverExitUp var(--animation-duration) ease-out forwards}&.exit-down{animation:popoverExitDown var(--animation-duration) ease-out forwards}&.exit-left{animation:popoverExitLeft var(--animation-duration) ease-out forwards}&.exit-right{animation:popoverExitRight var(--animation-duration) ease-out forwards}&.exit-up-left{animation:popoverExitUpLeft var(--animation-duration) ease-out forwards}&.exit-up-right{animation:popoverExitUpRight var(--animation-duration) ease-out forwards}&.exit-down-left{animation:popoverExitDownLeft var(--animation-duration) ease-out forwards}&.exit-down-right{animation:popoverExitDownRight var(--animation-duration) ease-out forwards}&.enter-from-up{animation:popoverEnterFromUp var(--animation-duration) ease-out forwards}&.enter-from-down{animation:popoverEnterFromDown var(--animation-duration) ease-out forwards}&.enter-from-left{animation:popoverEnterFromLeft var(--animation-duration) ease-out forwards}&.enter-from-right{animation:popoverEnterFromRight var(--animation-duration) ease-out forwards}&.enter-from-up-left{animation:popoverEnterFromUpLeft var(--animation-duration) ease-out forwards}&.enter-from-up-right{animation:popoverEnterFromUpRight var(--animation-duration) ease-out forwards}&.enter-from-down-left{animation:popoverEnterFromDownLeft var(--animation-duration) ease-out forwards}&.enter-from-down-right{animation:popoverEnterFromDownRight var(--animation-duration) ease-out forwards}}@media (prefers-contrast:high){[popover].inspekt-axe-popover{border:2px solid currentColor}.inspekt-axe-popover__impact-badge{border:1px solid white}}@media (prefers-color-scheme:dark){:root{--color-text:var(--gray-50);--color-text-muted:var(--gray-400);--color-bg:rgba(31,41,55,0.75);--color-bg-subtle:var(--gray-900);--color-border:var(--gray-700);--green-bg:#14532d;--red-bg:#7f1d1d;--blue-bg:#1e3a5f}.inspekt-axe-popover__header{border-bottom-color:var(--gray-700)}.inspekt-axe-popover__tablist{border-bottom-color:var(--gray-700);background:rgba(17,24,39,0.5)}.inspekt-axe-popover__tab{color:var(--gray-400);&:hover{color:var(--gray-300);background:rgba(255,255,255,0.05)}}.inspekt-axe-popover__tab--active{color:var(--blue-light);border-bottom-color:var(--blue-light);background:rgba(31,41,55,0.5)}.inspekt-axe-popover__markdown-textarea{color:var(--gray-200);background:var(--gray-800)}.inspekt-axe-popover__details{& summary{background:var(--gray-900);color:var(--gray-200);&::before{color:var(--gray-400)}&:hover{background:var(--gray-800)}}}.inspekt-axe-popover__details-content{background:var(--gray-800)}.inspekt-axe-popover__check-item{background:var(--gray-900);border-left-color:var(--gray-600);color:var(--gray-300)}.inspekt-axe-popover__failure-summary{color:#fecaca}.inspekt-axe-popover__tag{background:var(--gray-700);border-color:var(--gray-600);color:var(--gray-300)}.inspekt-axe-popover__tag--wcag{background:var(--blue-bg);border-color:var(--blue);color:#93c5fd}.inspekt-axe-popover__selector{background:var(--blue-bg);border-color:var(--blue);color:#93c5fd}.inspekt-axe-popover__footer{border-top-color:var(--gray-700);background:rgba(17,24,39,0.5)}.inspekt-axe-popover__body{&::-webkit-scrollbar-track{background:var(--gray-900)}&::-webkit-scrollbar-thumb{background:var(--gray-600);&:hover{background:var(--gray-500)}}}.inspekt-axe-nav{background:rgba(17,24,39,0.85);border-bottom-color:rgba(17,24,39,0.3)}.inspekt-axe-nav__prev,.inspekt-axe-nav__next,.inspekt-axe-nav__detach{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover:not(:disabled){background:var(--gray-700);border-color:var(--gray-500)}}.inspekt-axe-nav__skip-similar{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover{background:var(--gray-700);border-color:var(--gray-500)}}.inspekt-axe-nav__skip-similar--active{background:var(--blue);border-color:var(--blue);color:white}.inspekt-axe-nav__close{background:var(--gray-800);border-color:var(--gray-600);color:var(--gray-300);&:hover{background:#7f1d1d;border-color:var(--red);color:#fecaca}}.inspekt-axe-nav__counter{color:var(--gray-400)}}:root{--axe-blue:var(--blue);--axe-blue-light:var(--blue-light);--axe-blue-bg:var(--blue-bg);--ibm-red:#da1e28;--ibm-red-light:#fa4d56;--ibm-red-bg:#fff1f1;--hcs-purple:#9c27b0;--hcs-purple-light:#ba68c8;--hcs-purple-bg:#f3e5f5;--sia-green:#00a651;--sia-green-light:#4caf50;--sia-green-bg:#e8f5e9}.inspekt-popover__source-tabs{display:flex;gap:0;padding:0;background:var(--gray-800);border-bottom:1px solid var(--gray-700)}.inspekt-popover__source-tab{flex:1;position:relative;padding:var(--space-md) var(--space-lg);background:transparent;border:none;border-bottom:3px solid transparent;font-size:var(--text-sm);font-weight:600;color:rgba(255,255,255,0.6);cursor:pointer;transition:all var(--transition-fast);display:flex;align-items:center;justify-content:center;gap:var(--space-sm);&:hover:not(.inspekt-popover__source-tab--active){color:rgba(255,255,255,0.85);background:rgba(255,255,255,0.05)}&:focus-visible{outline:2px solid var(--blue-light);outline-offset:-2px}}.inspekt-popover__source-tab[data-source="axe"]{&.inspekt-popover__source-tab--active{color:white;border-bottom-color:var(--axe-blue);background:rgba(37,99,235,0.1)}}.inspekt-popover__source-tab[data-source="ibm"],.inspekt-popover__source-tab[data-source="eac"]{&.inspekt-popover__source-tab--active{color:white;border-bottom-color:var(--ibm-red);background:rgba(218,30,40,0.1)}}.inspekt-popover__source-tab[data-source="hcs"]{&.inspekt-popover__source-tab--active{color:white;border-bottom-color:var(--hcs-purple);background:rgba(156,39,176,0.1)}}.inspekt-popover__source-tab[data-source="sia"]{&.inspekt-popover__source-tab--active{color:white;border-bottom-color:var(--sia-green);background:rgba(0,166,81,0.1)}}.inspekt-popover__source-icon{width:14px;height:14px;flex-shrink:0}.inspekt-popover__source-count{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;border-radius:9px;font-size:11px;font-weight:700;font-variant-numeric:tabular-nums;color:white}.inspekt-popover__source-tab[data-source="axe"] .inspekt-popover__source-count{background:var(--axe-blue)}.inspekt-popover__source-tab[data-source="ibm"] .inspekt-popover__source-count,.inspekt-popover__source-tab[data-source="eac"] .inspekt-popover__source-count{background:var(--ibm-red)}.inspekt-popover__source-tab[data-source="hcs"] .inspekt-popover__source-count{background:var(--hcs-purple)}.inspekt-popover__source-tab[data-source="sia"] .inspekt-popover__source-count{background:var(--sia-green)}.inspekt-popover__source-tab:disabled{opacity:0.4;cursor:not-allowed}.inspekt-popover__source-panel{display:none}.inspekt-popover__source-panel--active{display:block}.inspekt-popover__source-indicator{display:inline-flex;align-items:center;gap:var(--space-sm);padding:3px var(--space-md);border-radius:9999px;font-size:var(--text-xs);font-weight:600;text-transform:uppercase;letter-spacing:0.3px}.inspekt-popover__source-indicator--axe{background:var(--blue-bg);color:var(--axe-blue);border:1px solid #bfdbfe}.inspekt-popover__source-indicator--ibm,.inspekt-popover__source-indicator--eac{background:var(--ibm-red-bg);color:var(--ibm-red);border:1px solid #ffc8c8}.inspekt-popover__source-indicator--hcs{background:var(--hcs-purple-bg);color:var(--hcs-purple);border:1px solid #ce93d8}.inspekt-popover__source-indicator--sia{background:var(--sia-green-bg);color:var(--sia-green);border:1px solid #81c784}.inspekt-popover__combined-header{display:flex;flex-wrap:wrap;align-items:center;gap:var(--space-md);padding:var(--space-lg);background:var(--gray-50);border-bottom:1px solid var(--color-border)}.inspekt-popover__issue-count{font-size:var(--text-lg);font-weight:700;color:var(--color-text)}.inspekt-popover__source-badges{display:flex;gap:var(--space-sm)}@media (prefers-color-scheme:dark){.inspekt-popover__source-tabs{background:rgba(17,24,39,0.9);border-bottom-color:var(--gray-800)}.inspekt-popover__source-tab[data-source="axe"].inspekt-popover__source-tab--active{background:rgba(37,99,235,0.2)}.inspekt-popover__source-tab[data-source="ibm"].inspekt-popover__source-tab--active,.inspekt-popover__source-tab[data-source="eac"].inspekt-popover__source-tab--active{background:rgba(218,30,40,0.2)}.inspekt-popover__source-tab[data-source="hcs"].inspekt-popover__source-tab--active{background:rgba(156,39,176,0.2)}.inspekt-popover__source-tab[data-source="sia"].inspekt-popover__source-tab--active{background:rgba(0,166,81,0.2)}.inspekt-popover__source-indicator--axe{background:rgba(37,99,235,0.2);border-color:var(--axe-blue);color:var(--axe-blue-light)}.inspekt-popover__source-indicator--ibm,.inspekt-popover__source-indicator--eac{background:rgba(218,30,40,0.2);border-color:var(--ibm-red);color:var(--ibm-red-light)}.inspekt-popover__source-indicator--hcs{background:rgba(156,39,176,0.2);border-color:var(--hcs-purple);color:var(--hcs-purple-light)}.inspekt-popover__source-indicator--sia{background:rgba(0,166,81,0.2);border-color:var(--sia-green);color:var(--sia-green-light)}.inspekt-popover__combined-header{background:rgba(17,24,39,0.5);border-bottom-color:var(--gray-700)}.inspekt-popover__issue-count{color:var(--gray-100)}}.inspekt-popover__level-badge{flex-shrink:0;padding:5px 11px;border-radius:var(--radius-md);font-size:var(--text-xs);font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:var(--color-text-inverse)}.inspekt-popover__level-badge--violation{background:var(--impact-critical)}.inspekt-popover__level-badge--potentialviolation{background:var(--impact-serious)}.inspekt-popover__level-badge--recommendation{background:var(--impact-moderate)}.inspekt-popover__level-badge--potentialrecommendation,.inspekt-popover__level-badge--manual{background:var(--impact-minor)}.inspekt-popover__ibm-message{padding:var(--space-md);background:var(--red-bg);border-radius:var(--radius-md);font-size:var(--text-sm);line-height:1.6;color:#991b1b}.inspekt-popover__ibm-rule{display:inline-block;padding:3px var(--space-md);background:var(--gray-100);border:1px solid var(--gray-300);border-radius:var(--radius-sm);font-family:var(--font-mono);font-size:var(--text-xs);color:var(--gray-600)}.inspekt-popover__ibm-help{display:inline-flex;align-items:center;gap:var(--space-sm);padding:var(--space-md) var(--space-lg);background:var(--ibm-red);border-radius:var(--radius-md);text-decoration:none;font-size:var(--text-sm);font-weight:500;color:white;transition:background var(--transition-base);&:hover{background:#b81921}&:focus-visible{outline:2px solid var(--ibm-red);outline-offset:2px}}.inspekt-popover__ibm-wcag-tag{display:inline-block;padding:3px var(--space-md);background:var(--ibm-red-bg);border:1px solid #ffc8c8;border-radius:9999px;font-size:var(--text-xs);font-weight:500;color:var(--ibm-red)}.inspekt-popover__issue-list{list-style:none;padding:0;margin:0}.inspekt-popover__issue-item{padding:var(--space-lg);border-bottom:1px solid var(--color-border);&:last-child{border-bottom:none}}.inspekt-popover__issue-header{display:flex;align-items:flex-start;gap:var(--space-md);margin-bottom:var(--space-md)}.inspekt-popover__issue-title{flex:1;margin:0;font-size:var(--text-base);font-weight:600;line-height:1.4;color:var(--color-text)}.inspekt-popover__issue-details{margin-top:var(--space-md)}.inspekt-badge{all:initial;position:absolute !important;border-radius:50% !important;width:32px !important;height:32px !important;min-width:32px !important;min-height:32px !important;max-width:32px !important;max-height:32px !important;box-sizing:border-box !important;display:flex !important;align-items:center !important;justify-content:center !important;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif !important;font-size:13px !important;font-weight:bold !important;color:white !important;z-index:2147483647 !important;box-shadow:0 2px 4px rgba(0,0,0,0.4) !important;border:2px solid white !important;user-select:none !important;line-height:1 !important;margin:0 !important;padding:0 !important}.inspekt-badge--combined{position:relative;overflow:hidden;&::before,&::after{content:"";position:absolute;width:50%;height:100%;top:0}&::before{left:0;background:var(--axe-blue)}&::after{right:0;background:var(--ibm-red)}}.inspekt-badge--combined .inspekt-badge__text{position:relative;z-index:1}.inspekt-badge--critical{background:var(--impact-critical) !important}.inspekt-badge--serious{background:var(--impact-serious) !important}.inspekt-badge--moderate{background:var(--impact-moderate) !important}.inspekt-badge--minor{background:var(--impact-minor) !important}.inspekt-badge--dimmed{opacity:0.3 !important;filter:grayscale(50%)}.inspekt-badge--active{animation:badgePulse 1.5s ease-in-out infinite;box-shadow:0 0 0 4px rgba(37,99,235,0.3),0 2px 4px rgba(0,0,0,0.4) !important}@keyframes badgePulse{0%,100%{transform:scale(1)}50%{transform:scale(1.1)}}button.inspekt-badge{pointer-events:auto !important;cursor:pointer !important;transition:transform 0.15s ease,box-shadow 0.15s ease,opacity 0.2s ease !important;&:hover:not(:disabled){transform:scale(1.1)}&:focus-visible{outline:3px solid var(--color-primary);outline-offset:2px;transform:scale(1.1)}&:active:not(:disabled){transform:scale(0.95)}}@media (prefers-color-scheme:dark){.inspekt-popover__ibm-message{background:rgba(127,29,29,0.3);color:#fecaca}.inspekt-popover__ibm-rule{background:var(--gray-700);border-color:var(--gray-600);color:var(--gray-300)}.inspekt-popover__ibm-wcag-tag{background:rgba(218,30,40,0.2);border-color:var(--ibm-red);color:var(--ibm-red-light)}.inspekt-popover__issue-item{border-bottom-color:var(--gray-700)}}`;
        }

        /**
         * Returns badge-specific CSS with !important overrides.
         * These are separate because badges need aggressive style isolation.
         */
        function getBadgeCSS() {
            return `
                .inspekt-badge {
                    all: initial;
                    position: absolute !important;
                    border-radius: 50% !important;
                    width: 32px !important;
                    height: 32px !important;
                    display: flex !important;
                    align-items: center !important;
                    justify-content: center !important;
                    font-family: -apple-system, BlinkMacSystemFont, sans-serif !important;
                    font-size: 13px !important;
                    font-weight: bold !important;
                    color: white !important;
                    z-index: 2147483647 !important;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.4) !important;
                    border: 2px solid white !important;
                    cursor: pointer !important;
                    pointer-events: auto !important;
                    transition: transform 0.15s ease !important;
                }
                .inspekt-badge:hover { transform: scale(1.1); }
                .inspekt-badge--critical { background: #dc2626 !important; }
                .inspekt-badge--serious { background: #ea580c !important; }
                .inspekt-badge--moderate { background: #2563eb !important; }
                .inspekt-badge--minor { background: #6b7280 !important; }
                /* Recommendation badges have dotted outline instead of solid */
                .inspekt-badge--recommendation {
                    background: #0891b2 !important;  /* cyan-600 */
                    border: 2px dotted white !important;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.3), inset 0 0 0 1px rgba(255,255,255,0.2) !important;
                }
                .inspekt-badge--recommendation:hover {
                    box-shadow: 0 3px 6px rgba(0,0,0,0.4), inset 0 0 0 1px rgba(255,255,255,0.3) !important;
                }
                .inspekt-badge--combined::after {
                    content: '';
                    position: absolute;
                    bottom: -4px;
                    right: -4px;
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    background: linear-gradient(135deg, #2563eb 50%, #da1e28 50%);
                    border: 1px solid white;
                }
                .inspekt-badge--active {
                    animation: badgePulse 1.5s ease-in-out infinite;
                }
                @keyframes badgePulse {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.1); }
                }
            `;
        }

        function createUnifiedBadge(violation, badgeNumber) {
            const element = violation.element;
            if (!element || element.nodeType !== 1) return null;

            const badge = document.createElement('button');
            badge.id = violation.badgeId;
            badge.setAttribute('data-inspekt-badge', badgeNumber);

            // Use recommendation class (dotted border) for recommendation-only items
            if (violation.isRecommendation) {
                badge.className = 'inspekt-badge inspekt-badge--recommendation';
            } else {
                badge.className = `inspekt-badge inspekt-badge--${violation.highestImpact}`;
            }

            // Add combined indicator if multiple engines have issues
            const activeEngineCount = Object.values(violation.hasEngine).filter(Boolean).length;
            if (activeEngineCount > 1) {
                badge.classList.add('inspekt-badge--combined');
            }

            badge.innerHTML = `<span class="inspekt-badge__text">${badgeNumber}</span>`;

            // Build dynamic title showing per-engine counts
            const issueType = violation.isRecommendation ? 'recommendation' : 'issue';
            const engineParts = engines
                .filter(e => violation.hasEngine[e])
                .map(e => `${ENGINE_DISPLAY_NAMES[e]}: ${violation.engineCounts[e]}`);
            badge.title = `${violation.totalCount} ${issueType}${violation.totalCount > 1 ? 's' : ''} (${engineParts.join(', ')})`;

            // Set anchor name for CSS positioning
            badge.style.anchorName = `--badge-${badgeNumber}`;

            // Position badge
            const rect = element.getBoundingClientRect();
            badge.style.top = `${window.scrollY + rect.top - 16}px`;
            badge.style.left = `${window.scrollX + rect.left - 16}px`;

            return badge;
        }

    } catch (error) {
        console.error('[Inspekt A11Y] Error:', error);
        return {
            ok: false,
            error: error.message || String(error)
        };
    }
})();
