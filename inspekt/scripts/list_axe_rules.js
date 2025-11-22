// Inspekt Axe-core Rules Listing Script
// Note: axe-core library is injected before this script executes
(async function() {
    try {
        // Verify axe-core is available
        if (typeof axe === 'undefined') {
            throw new Error('axe-core library not found - this should not happen');
        }

        // Get all available rules
        // getRules() returns all rules that match the given tags
        // If no tags specified, returns all rules
        const allRules = axe.getRules();

        // Sort rules alphabetically by ID
        const sortedRules = allRules.sort((a, b) => a.ruleId.localeCompare(b.ruleId));

        // Format rule data
        const rules = sortedRules.map(rule => ({
            id: rule.ruleId,
            description: rule.description || '',
            help: rule.help || '',
            helpUrl: rule.helpUrl || '',
            tags: rule.tags || [],
            // Group rules by WCAG level for easier filtering
            wcagLevel: rule.tags.find(t => t.match(/wcag2{0,2}(a{1,3}|[0-9]{2}a{1,2})/i)) || 'other'
        }));

        // Calculate statistics
        const stats = {
            total: rules.length,
            wcag2a: rules.filter(r => r.tags.includes('wcag2a')).length,
            wcag2aa: rules.filter(r => r.tags.includes('wcag2aa')).length,
            wcag2aaa: rules.filter(r => r.tags.includes('wcag2aaa')).length,
            wcag21a: rules.filter(r => r.tags.includes('wcag21a')).length,
            wcag21aa: rules.filter(r => r.tags.includes('wcag21aa')).length,
            wcag22aa: rules.filter(r => r.tags.includes('wcag22aa')).length,
            bestPractice: rules.filter(r => r.tags.includes('best-practice')).length,
            experimental: rules.filter(r => r.tags.includes('experimental')).length
        };

        return {
            ok: true,
            rules: rules,
            stats: stats,
            axeVersion: axe.version,
            timestamp: new Date().toISOString()
        };

    } catch (error) {
        return {
            ok: false,
            error: error.message,
            stack: error.stack
        };
    }
})()
