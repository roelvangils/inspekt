// Inspekt Axe-core Accessibility Audit Script
// Note: axe-core library is injected before this script executes
(async function() {
    try {
        // Verify axe-core is available
        if (typeof axe === 'undefined') {
            throw new Error('axe-core library not found - this should not happen');
        }

        // Configuration object injected from Python
        // Will be replaced with actual config via string substitution
        const config = __AXE_CONFIG__;

        // Run axe-core audit
        const results = await axe.run(document, config);

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

        // Process violations to include node count
        const violations = results.violations.map(violation => ({
            id: violation.id,
            impact: violation.impact,
            description: violation.description,
            help: violation.help,
            helpUrl: violation.helpUrl,
            tags: violation.tags,
            nodes: violation.nodes.map(node => ({
                html: node.html,
                target: node.target,
                failureSummary: node.failureSummary,
                impact: node.impact
            })),
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
