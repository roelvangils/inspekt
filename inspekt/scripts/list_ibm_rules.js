// Inspekt IBM Equal Access Rules Listing Script
// Note: ace.js library is injected before this script executes
(async function() {
    try {
        // Verify ace is available
        if (typeof ace === 'undefined') {
            throw new Error('IBM Equal Access (ace) library not found - this should not happen');
        }

        // Create a checker instance to access rules
        const checker = new ace.Checker();

        // Get guideline information
        const guidelines = checker.getGuidelines();
        const guidelineIds = checker.getGuidelineIds();

        // Extract rules from guidelines
        const rulesMap = new Map();

        guidelines.forEach(guideline => {
            if (guideline.checkpoints) {
                guideline.checkpoints.forEach(checkpoint => {
                    if (checkpoint.rules) {
                        checkpoint.rules.forEach(rule => {
                            if (!rulesMap.has(rule.id)) {
                                rulesMap.set(rule.id, {
                                    id: rule.id,
                                    description: rule.description || '',
                                    help: rule.help || '',
                                    helpUrl: rule.helpUrl || '',
                                    level: rule.level || 'violation',
                                    wcag: [],
                                    guidelines: []
                                });
                            }
                            const ruleData = rulesMap.get(rule.id);
                            if (checkpoint.num && !ruleData.wcag.includes(checkpoint.num)) {
                                ruleData.wcag.push(checkpoint.num);
                            }
                            if (guideline.id && !ruleData.guidelines.includes(guideline.id)) {
                                ruleData.guidelines.push(guideline.id);
                            }
                        });
                    }
                });
            }
        });

        // Convert to array and sort alphabetically
        const rules = Array.from(rulesMap.values()).sort((a, b) =>
            a.id.localeCompare(b.id)
        );

        // Calculate statistics
        const stats = {
            total: rules.length,
            byGuideline: {},
            byLevel: {
                violation: 0,
                potentialviolation: 0,
                recommendation: 0,
                manual: 0
            }
        };

        // Count rules by guideline
        guidelineIds.forEach(gid => {
            stats.byGuideline[gid] = rules.filter(r =>
                r.guidelines.includes(gid)
            ).length;
        });

        // Count rules by level
        rules.forEach(r => {
            const level = r.level?.toLowerCase() || 'violation';
            if (stats.byLevel.hasOwnProperty(level)) {
                stats.byLevel[level]++;
            }
        });

        // Get version from checker if available
        let aceVersion = 'unknown';
        try {
            // Try to access version - exact location depends on build
            aceVersion = ace.version || ace.VERSION || 'unknown';
        } catch (e) {
            // Version not accessible
        }

        return {
            ok: true,
            rules: rules,
            stats: stats,
            guidelines: guidelineIds,
            aceVersion: aceVersion,
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
