// Inspekt axe-core accessibility audit (audit-only).
//
// Loaded by API / MCP / headless / `inspekt a11y -e axe` paths that just
// need axe results — they never enable badges. The deprecated `inspekt
// axe` CLI used to inject DOM badges + popovers from this script; that
// CLI was removed and the visual UI now flows through the Overlay Bus
// (see `inspekt/scripts/run_a11y.js` + `vm/js/overlay-bus.js`). This
// script returns serializable audit results and nothing else.
//
// axe-core library is concatenated before this script by the caller.
(async function() {
    try {
        if (typeof axe === 'undefined') {
            throw new Error('axe-core library not found - this should not happen');
        }

        const config = __AXE_CONFIG__;

        // The legacy CLI passed visual flags through here; ignore them
        // for back-compat with any caller that still sets them.
        delete config.__showBadges;
        delete config.__interactiveBadges;
        delete config.__devCss;
        delete config.__persistent;
        delete config.elementRef;  // No longer needed — we don't keep DOM refs.

        const results = await axe.run(document, config);

        const summary = {
            violationCount: results.violations.length,
            passCount: results.passes.length,
            incompleteCount: results.incomplete.length,
            inapplicableCount: results.inapplicable.length,
            criticalCount: results.violations.filter(v => v.impact === 'critical').length,
            seriousCount:  results.violations.filter(v => v.impact === 'serious').length,
            moderateCount: results.violations.filter(v => v.impact === 'moderate').length,
            minorCount:    results.violations.filter(v => v.impact === 'minor').length,
        };

        const violations = results.violations.map(v => ({
            id: v.id,
            impact: v.impact,
            description: v.description,
            help: v.help,
            helpUrl: v.helpUrl,
            tags: v.tags,
            nodes: v.nodes.map(n => ({
                html: n.html,
                target: n.target,
                failureSummary: n.failureSummary,
                impact: n.impact,
            })),
            nodeCount: v.nodes.length,
        }));

        const passes = results.passes.map(p => ({
            id: p.id,
            description: p.description,
            help: p.help,
            tags: p.tags,
            nodeCount: p.nodes.length,
        }));

        const incomplete = results.incomplete.map(i => ({
            id: i.id,
            impact: i.impact,
            description: i.description,
            help: i.help,
            helpUrl: i.helpUrl,
            tags: i.tags,
            nodeCount: i.nodes.length,
        }));

        return {
            ok: true,
            url: window.location.href,
            title: document.title,
            timestamp: new Date().toISOString(),
            violations,
            passes,
            incomplete,
            inapplicable: results.inapplicable.map(r => r.id),
            summary,
            axeVersion: axe.version,
        };
    } catch (error) {
        return {
            ok: false,
            error: error.message,
            stack: error.stack,
            url: window.location.href,
        };
    }
})()
