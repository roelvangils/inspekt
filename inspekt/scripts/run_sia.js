// Inspekt Siteimprove Alfa Accessibility Audit Script
// Note: Alfa library bundle is injected before this script executes
(async function() {
    // =========================================================================
    // Helper Functions (defined first for clarity)
    // =========================================================================

    // Helper function to get rule title from rule URI
    function getRuleTitle(ruleUri) {
        // Map of known Alfa rule IDs to titles
        const ruleTitles = {
            // Core document rules
            'sia-r1': 'Document has title',
            'sia-r2': 'Image has accessible name',
            'sia-r3': 'Id attribute unique',
            'sia-r4': 'Html has lang attribute',
            'sia-r5': 'Html lang attribute valid',
            'sia-r6': 'Html lang and xml:lang match',
            'sia-r7': 'Lang attribute valid',
            // Form and interactive elements
            'sia-r8': 'Form field has accessible name',
            'sia-r9': 'Meta refresh no delay',
            'sia-r10': 'Autocomplete valid',
            'sia-r11': 'Link has accessible name',
            'sia-r12': 'Button has accessible name',
            'sia-r13': 'Iframe has accessible name',
            'sia-r14': 'Visible label in accessible name',
            'sia-r15': 'Iframe equivalent purpose',
            'sia-r16': 'Role has required states',
            'sia-r17': 'Aria-hidden not focusable',
            'sia-r18': 'Aria states permitted',
            'sia-r19': 'Aria state value valid',
            'sia-r20': 'Aria attribute defined',
            'sia-r21': 'Role attribute valid',
            // Media rules
            'sia-r22': 'Video has captions',
            'sia-r23': 'Audio has transcript',
            'sia-r24': 'Video has transcript',
            'sia-r25': 'Video has audio description',
            'sia-r26': 'Video visual-only is media alternative',
            'sia-r27': 'Video auditory has alternative',
            'sia-r28': 'Image button has accessible name',
            'sia-r29': 'Audio is media alternative',
            'sia-r30': 'Audio has text alternative',
            'sia-r31': 'Video is media alternative',
            'sia-r32': 'Video visual-only has audio track',
            'sia-r33': 'Video visual-only has transcript',
            'sia-r34': 'Video visual-only has description track',
            'sia-r35': 'Video visual-only has alternative',
            'sia-r36': 'Video has description track',
            'sia-r37': 'Video has strict alternative',
            'sia-r38': 'Video has accessible alternative',
            'sia-r39': 'Image filename not accessible name',
            'sia-r40': 'Region has accessible name',
            // Link and table rules
            'sia-r41': 'Links same name same purpose',
            'sia-r42': 'Role has required parent',
            'sia-r43': 'SVG has accessible name',
            'sia-r44': 'Orientation not restricted',
            'sia-r45': 'Headers refer to same table',
            'sia-r46': 'Header cells have data cells',
            'sia-r47': 'Viewport allows zoom',
            'sia-r48': 'Autoplay audio max 3 seconds',
            'sia-r49': 'Autoplay has control mechanism',
            'sia-r50': 'Avoids autoplay audio',
            // Structure rules
            'sia-r53': 'Headings structured',
            'sia-r54': 'Live region is atomic',
            'sia-r55': 'Landmarks same name same purpose',
            'sia-r56': 'Landmarks unique names',
            'sia-r57': 'Text in landmark',
            'sia-r58': 'Repeated content bypassable',
            'sia-r59': 'Document has headings',
            'sia-r60': 'Group has accessible name',
            'sia-r61': 'Starts with level 1 heading',
            'sia-r62': 'Links in text distinguishable',
            'sia-r63': 'Object has accessible name',
            'sia-r64': 'Heading has accessible name',
            'sia-r65': 'Visible focus indicator',
            'sia-r66': 'Text has enhanced contrast',
            'sia-r67': 'Decorative not exposed',
            'sia-r68': 'Role has required children',
            'sia-r69': 'Text has minimum contrast',
            'sia-r70': 'No obsolete elements',
            // Text styling rules
            'sia-r71': 'Text not justified',
            'sia-r72': 'Text not all uppercase',
            'sia-r73': 'Sufficient line height',
            'sia-r74': 'Font size not absolute',
            'sia-r75': 'Font size not too small',
            'sia-r76': 'Th elements are headers',
            'sia-r77': 'Data cells have headers',
            'sia-r78': 'Headings have content between',
            'sia-r79': 'Preformatted is code or figure',
            'sia-r80': 'Line height not absolute',
            'sia-r81': 'Links same context same purpose',
            'sia-r82': 'Error describes invalid field',
            'sia-r83': 'Text not clipped on resize',
            'sia-r84': 'Scrollable keyboard accessible',
            'sia-r85': 'Text not all italics',
            'sia-r86': 'Decorative not exposed',
            'sia-r87': 'First focusable is skip link',
            'sia-r88': 'Link text minimum contrast',
            'sia-r89': 'Link text enhanced contrast',
            'sia-r90': 'Presentational no focusable',
            // Text spacing rules
            'sia-r91': 'Letter spacing adjustable',
            'sia-r92': 'Word spacing adjustable',
            'sia-r93': 'Line height adjustable',
            'sia-r94': 'Menuitem has accessible name',
            'sia-r95': 'Iframe no negative tabindex',
            'sia-r96': 'Meta refresh no delay strict',
            // Bypass and content rules
            'sia-r97': 'Collapsible content blocks',
            'sia-r98': 'Heading at main content start',
            'sia-r99': 'Main content in landmark',
            'sia-r100': 'Instrument to main content',
            'sia-r101': 'No repeated content before main',
            'sia-r102': 'Skip link or no repeated content',
            'sia-r103': 'Widget text minimum contrast',
            'sia-r104': 'Widget text enhanced contrast',
            // Newer rules
            'sia-r109': 'Lang subtag matches default',
            'sia-r110': 'Role attribute has valid value',
            'sia-r111': 'Target size enhanced',
            'sia-r113': 'Target size minimum',
            'sia-r114': 'Page title is descriptive',
            'sia-r115': 'Heading is descriptive',
            'sia-r116': 'Summary has accessible name',
            'sia-r117': 'Error suggestion provided',
        };

        const ruleId = ruleUri.split('/').pop() || ruleUri;
        return ruleTitles[ruleId] || ruleId;
    }

    // Helper function to get rule description
    function getRuleDescription(ruleUri) {
        // For now return empty - full descriptions would bloat the script
        // The help URL provides detailed information
        return '';
    }

    // Helper function to get WCAG requirements for a rule
    function getRuleRequirements(ruleUri) {
        // Map of known Alfa rules to WCAG success criteria
        const ruleRequirements = {
            // Core document rules
            'sia-r1': ['wcag:2.4.2'],
            'sia-r2': ['wcag:1.1.1'],
            'sia-r3': ['wcag:4.1.1'],
            'sia-r4': ['wcag:3.1.1'],
            'sia-r5': ['wcag:3.1.1', 'wcag:3.1.2'],
            'sia-r6': ['wcag:3.1.1'],
            'sia-r7': ['wcag:3.1.2'],
            // Form and interactive elements
            'sia-r8': ['wcag:4.1.2'],
            'sia-r9': ['wcag:2.2.1', 'wcag:2.2.4', 'wcag:3.2.5'],
            'sia-r10': ['wcag:1.3.5'],
            'sia-r11': ['wcag:4.1.2', 'wcag:2.4.4'],
            'sia-r12': ['wcag:4.1.2'],
            'sia-r13': ['wcag:4.1.2'],
            'sia-r14': ['wcag:2.5.3'],
            'sia-r15': ['wcag:4.1.2'],
            'sia-r16': ['wcag:4.1.2'],
            'sia-r17': ['wcag:4.1.2'],
            'sia-r18': ['wcag:4.1.2'],
            'sia-r19': ['wcag:4.1.2'],
            'sia-r20': ['wcag:4.1.2'],
            'sia-r21': ['wcag:4.1.2'],
            // Media rules
            'sia-r22': ['wcag:1.2.2'],
            'sia-r23': ['wcag:1.2.1'],
            'sia-r24': ['wcag:1.2.8'],
            'sia-r25': ['wcag:1.2.5'],
            'sia-r26': ['wcag:1.2.1'],
            'sia-r27': ['wcag:1.2.2'],
            'sia-r28': ['wcag:1.1.1', 'wcag:4.1.2'],
            'sia-r29': ['wcag:1.2.1'],
            'sia-r30': ['wcag:1.2.1'],
            'sia-r31': ['wcag:1.2.1'],
            'sia-r32': ['wcag:1.2.1'],
            'sia-r33': ['wcag:1.2.1'],
            'sia-r34': ['wcag:1.2.1'],
            'sia-r35': ['wcag:1.2.1'],
            'sia-r36': ['wcag:1.2.5'],
            'sia-r37': ['wcag:1.2.5'],
            'sia-r38': ['wcag:1.2.3', 'wcag:1.2.5'],
            'sia-r39': ['wcag:1.1.1'],
            'sia-r40': ['wcag:1.3.1'],
            // Link and table rules
            'sia-r41': ['wcag:2.4.4', 'wcag:2.4.9'],
            'sia-r42': ['wcag:1.3.1'],
            'sia-r43': ['wcag:1.1.1'],
            'sia-r44': ['wcag:1.3.4'],
            'sia-r45': ['wcag:1.3.1'],
            'sia-r46': ['wcag:1.3.1'],
            'sia-r47': ['wcag:1.4.4'],
            'sia-r48': ['wcag:1.4.2'],
            'sia-r49': ['wcag:1.4.2'],
            'sia-r50': ['wcag:1.4.2'],
            // Structure rules
            'sia-r53': ['wcag:1.3.1', 'wcag:2.4.6'],
            'sia-r54': ['wcag:4.1.3'],
            'sia-r55': ['wcag:1.3.1'],
            'sia-r56': ['wcag:1.3.1'],
            'sia-r57': ['wcag:1.3.1'],
            'sia-r58': ['wcag:2.4.1'],
            'sia-r59': ['wcag:1.3.1'],
            'sia-r60': ['wcag:1.3.1'],
            'sia-r61': ['wcag:1.3.1'],
            'sia-r62': ['wcag:1.4.1'],
            'sia-r63': ['wcag:1.1.1'],
            'sia-r64': ['wcag:2.4.6'],
            'sia-r65': ['wcag:2.4.7'],
            'sia-r66': ['wcag:1.4.6'],
            'sia-r67': ['wcag:1.1.1'],
            'sia-r68': ['wcag:1.3.1'],
            'sia-r69': ['wcag:1.4.3'],
            'sia-r70': ['wcag:4.1.1'],
            // Text styling rules
            'sia-r71': ['wcag:1.4.8'],
            'sia-r72': ['wcag:1.4.8'],
            'sia-r73': ['wcag:1.4.8', 'wcag:1.4.12'],
            'sia-r74': ['wcag:1.4.4'],
            'sia-r75': ['wcag:1.4.4'],
            'sia-r76': ['wcag:1.3.1'],
            'sia-r77': ['wcag:1.3.1'],
            'sia-r78': ['wcag:1.3.1'],
            'sia-r79': ['wcag:1.3.1'],
            'sia-r80': ['wcag:1.4.12'],
            'sia-r81': ['wcag:2.4.4'],
            'sia-r82': ['wcag:3.3.1'],
            'sia-r83': ['wcag:1.4.4'],
            'sia-r84': ['wcag:2.1.1'],
            'sia-r85': ['wcag:1.4.8'],
            'sia-r86': ['wcag:1.3.1'],
            'sia-r87': ['wcag:2.4.1'],
            'sia-r88': ['wcag:1.4.3'],
            'sia-r89': ['wcag:1.4.6'],
            'sia-r90': ['wcag:4.1.2'],
            // Text spacing rules
            'sia-r91': ['wcag:1.4.12'],
            'sia-r92': ['wcag:1.4.12'],
            'sia-r93': ['wcag:1.4.12'],
            'sia-r94': ['wcag:4.1.2'],
            'sia-r95': ['wcag:2.1.1'],
            'sia-r96': ['wcag:2.2.1', 'wcag:2.2.4', 'wcag:3.2.5'],
            // Bypass and content rules
            'sia-r97': ['wcag:2.4.1'],
            'sia-r98': ['wcag:2.4.1'],
            'sia-r99': ['wcag:2.4.1'],
            'sia-r100': ['wcag:2.4.1'],
            'sia-r101': ['wcag:2.4.1'],
            'sia-r102': ['wcag:2.4.1'],
            'sia-r103': ['wcag:1.4.3'],
            'sia-r104': ['wcag:1.4.6'],
            // Newer rules
            'sia-r109': ['wcag:3.1.1'],
            'sia-r110': ['wcag:4.1.2'],
            'sia-r111': ['wcag:2.5.5'],
            'sia-r113': ['wcag:2.5.8'],
            'sia-r114': ['wcag:2.4.2'],
            'sia-r115': ['wcag:2.4.6'],
            'sia-r116': ['wcag:4.1.2'],
            'sia-r117': ['wcag:3.3.3'],
        };

        const ruleId = ruleUri.split('/').pop() || ruleUri;
        return ruleRequirements[ruleId] || [];
    }

    // =========================================================================
    // WCAG Success Criteria Level and Version Data
    // =========================================================================

    // Complete mapping of WCAG Success Criteria to their conformance level and version
    const WCAG_SC_LEVELS = {
        // WCAG 2.0 Level A
        '1.1.1': { level: 'A', version: '2.0' },
        '1.2.1': { level: 'A', version: '2.0' },
        '1.2.2': { level: 'A', version: '2.0' },
        '1.2.3': { level: 'A', version: '2.0' },
        '1.3.1': { level: 'A', version: '2.0' },
        '1.3.2': { level: 'A', version: '2.0' },
        '1.3.3': { level: 'A', version: '2.0' },
        '1.4.1': { level: 'A', version: '2.0' },
        '1.4.2': { level: 'A', version: '2.0' },
        '2.1.1': { level: 'A', version: '2.0' },
        '2.1.2': { level: 'A', version: '2.0' },
        '2.2.1': { level: 'A', version: '2.0' },
        '2.2.2': { level: 'A', version: '2.0' },
        '2.3.1': { level: 'A', version: '2.0' },
        '2.4.1': { level: 'A', version: '2.0' },
        '2.4.2': { level: 'A', version: '2.0' },
        '2.4.3': { level: 'A', version: '2.0' },
        '2.4.4': { level: 'A', version: '2.0' },
        '3.1.1': { level: 'A', version: '2.0' },
        '3.2.1': { level: 'A', version: '2.0' },
        '3.2.2': { level: 'A', version: '2.0' },
        '3.3.1': { level: 'A', version: '2.0' },
        '3.3.2': { level: 'A', version: '2.0' },
        '4.1.1': { level: 'A', version: '2.0' },
        '4.1.2': { level: 'A', version: '2.0' },
        // WCAG 2.0 Level AA
        '1.2.4': { level: 'AA', version: '2.0' },
        '1.2.5': { level: 'AA', version: '2.0' },
        '1.4.3': { level: 'AA', version: '2.0' },
        '1.4.4': { level: 'AA', version: '2.0' },
        '1.4.5': { level: 'AA', version: '2.0' },
        '2.4.5': { level: 'AA', version: '2.0' },
        '2.4.6': { level: 'AA', version: '2.0' },
        '2.4.7': { level: 'AA', version: '2.0' },
        '3.1.2': { level: 'AA', version: '2.0' },
        '3.2.3': { level: 'AA', version: '2.0' },
        '3.2.4': { level: 'AA', version: '2.0' },
        '3.3.3': { level: 'AA', version: '2.0' },
        '3.3.4': { level: 'AA', version: '2.0' },
        // WCAG 2.0 Level AAA
        '1.2.6': { level: 'AAA', version: '2.0' },
        '1.2.7': { level: 'AAA', version: '2.0' },
        '1.2.8': { level: 'AAA', version: '2.0' },
        '1.2.9': { level: 'AAA', version: '2.0' },
        '1.4.6': { level: 'AAA', version: '2.0' },
        '1.4.7': { level: 'AAA', version: '2.0' },
        '1.4.8': { level: 'AAA', version: '2.0' },
        '1.4.9': { level: 'AAA', version: '2.0' },
        '2.1.3': { level: 'AAA', version: '2.0' },
        '2.2.3': { level: 'AAA', version: '2.0' },
        '2.2.4': { level: 'AAA', version: '2.0' },
        '2.2.5': { level: 'AAA', version: '2.0' },
        '2.3.2': { level: 'AAA', version: '2.0' },
        '2.4.8': { level: 'AAA', version: '2.0' },
        '2.4.9': { level: 'AAA', version: '2.0' },
        '2.4.10': { level: 'AAA', version: '2.0' },
        '3.1.3': { level: 'AAA', version: '2.0' },
        '3.1.4': { level: 'AAA', version: '2.0' },
        '3.1.5': { level: 'AAA', version: '2.0' },
        '3.1.6': { level: 'AAA', version: '2.0' },
        '3.2.5': { level: 'AAA', version: '2.0' },
        '3.3.5': { level: 'AAA', version: '2.0' },
        '3.3.6': { level: 'AAA', version: '2.0' },
        // WCAG 2.1 new criteria (Level A)
        '2.1.4': { level: 'A', version: '2.1' },
        '2.5.1': { level: 'A', version: '2.1' },
        '2.5.2': { level: 'A', version: '2.1' },
        '2.5.3': { level: 'A', version: '2.1' },
        '2.5.4': { level: 'A', version: '2.1' },
        // WCAG 2.1 new criteria (Level AA)
        '1.3.4': { level: 'AA', version: '2.1' },
        '1.3.5': { level: 'AA', version: '2.1' },
        '1.4.10': { level: 'AA', version: '2.1' },
        '1.4.11': { level: 'AA', version: '2.1' },
        '1.4.12': { level: 'AA', version: '2.1' },
        '1.4.13': { level: 'AA', version: '2.1' },
        '4.1.3': { level: 'AA', version: '2.1' },
        // WCAG 2.1 new criteria (Level AAA)
        '1.3.6': { level: 'AAA', version: '2.1' },
        '2.5.5': { level: 'AAA', version: '2.1' },
        '2.5.6': { level: 'AAA', version: '2.1' },
        // WCAG 2.2 new criteria (Level A)
        '3.2.6': { level: 'A', version: '2.2' },
        '3.3.7': { level: 'A', version: '2.2' },
        // WCAG 2.2 new criteria (Level AA)
        '2.4.11': { level: 'AA', version: '2.2' },
        '2.4.12': { level: 'AA', version: '2.2' },
        '2.4.13': { level: 'AA', version: '2.2' },
        '2.5.7': { level: 'AA', version: '2.2' },
        '2.5.8': { level: 'AA', version: '2.2' },
        '3.3.8': { level: 'AA', version: '2.2' },
        '3.3.9': { level: 'AA', version: '2.2' },
    };

    // Check if a WCAG SC matches the requested conformance level
    function matchesConformance(requirement, wcagVersion, wcagLevel) {
        // requirement format: "wcag:1.4.3"
        const sc = requirement.replace('wcag:', '');
        const scInfo = WCAG_SC_LEVELS[sc];

        if (!scInfo) {
            // Unknown SC - include by default to avoid hiding issues
            return true;
        }

        const scLevel = scInfo.level;
        const scVersion = scInfo.version;

        // Check version compatibility
        // WCAG 2.0 only includes 2.0 criteria
        // WCAG 2.1 includes 2.0 and 2.1 criteria
        // WCAG 2.2 includes 2.0, 2.1, and 2.2 criteria
        if (wcagVersion === 'WCAG2.0' && scVersion !== '2.0') return false;
        if (wcagVersion === 'WCAG2.1' && scVersion === '2.2') return false;
        // WCAG2.2 includes all versions

        // Check level compatibility (A ⊂ AA ⊂ AAA)
        // Level A only includes A criteria
        // Level AA includes A and AA criteria
        // Level AAA includes A, AA, and AAA criteria
        if (wcagLevel === 'A' && scLevel !== 'A') return false;
        if (wcagLevel === 'AA' && scLevel === 'AAA') return false;
        // AAA includes all levels

        return true;
    }

    // Check if an outcome should be included based on conformance filtering
    function outcomeMatchesConformance(outcome, wcagVersion, wcagLevel) {
        const requirements = getRuleRequirements(outcome.rule);

        // If no requirements known, include by default
        if (!requirements || requirements.length === 0) {
            return true;
        }

        // Include if ANY requirement matches (rule can apply to multiple SC)
        return requirements.some(req => matchesConformance(req, wcagVersion, wcagLevel));
    }

    // =========================================================================
    // Main Audit Logic
    // =========================================================================

    try {
        // Verify Alfa is available (it should be loaded before this script)
        if (typeof Alfa === 'undefined') {
            throw new Error('Siteimprove Alfa library not found - this should not happen');
        }

        // Configuration object injected from Python
        const config = __SIA_CONFIG__;

        // Extract version from config (injected by Python)
        const alfaVersion = config.__version__ || 'unknown';
        delete config.__version__;  // Don't pass to Alfa

        const includePassed = config.includePassed === true;
        const includeCantTell = config.includeCantTell === true;
        const includeInapplicable = config.includeInapplicable === true;

        // Run Alfa audit using the bundled runAudit function
        const startTime = performance.now();
        const rawOutcomes = await Alfa.runAudit(config);
        const auditTime = Math.round(performance.now() - startTime);

        // Apply WCAG conformance level filtering
        // config.conformance format: "WCAG2.2:AA" or "WCAG2.1:A"
        const conformance = config.conformance || 'WCAG2.1:AA';
        const [wcagVersion, wcagLevel] = conformance.split(':');

        // Filter outcomes by WCAG level BEFORE counting
        const filteredRawOutcomes = rawOutcomes.filter(outcome =>
            outcomeMatchesConformance(outcome, wcagVersion, wcagLevel)
        );

        // Track how many were filtered out for debugging
        const filteredOutCount = rawOutcomes.length - filteredRawOutcomes.length;

        // Filter and transform outcomes based on config
        const outcomes = [];
        const summary = {
            passed: 0,
            failed: 0,
            cantTell: 0,
            inapplicable: 0
        };
        // Track unique rules with failures for rule-level counting
        const failedRules = new Set();

        for (const outcome of filteredRawOutcomes) {
            const outcomeType = outcome.outcome;

            // Count all outcomes for summary
            if (outcomeType === 'passed') summary.passed++;
            else if (outcomeType === 'failed') {
                summary.failed++;
                // Track unique failed rules
                if (outcome.rule) {
                    failedRules.add(outcome.rule);
                }
            }
            else if (outcomeType === 'cantTell') summary.cantTell++;
            else if (outcomeType === 'inapplicable') summary.inapplicable++;

            // Filter based on config
            if (outcomeType === 'passed' && !includePassed) continue;
            if (outcomeType === 'cantTell' && !includeCantTell) continue;
            if (outcomeType === 'inapplicable' && !includeInapplicable) continue;

            // Transform to serializable format
            let selector = '';
            let htmlSnippet = '';
            let target = outcome.target;

            // Try to extract element info from target
            if (target) {
                // Target is typically a string representation
                const targetStr = String(target);

                // Try to find the element in the DOM for more info
                try {
                    // Target format is often like "Element<html, ...>" or similar
                    // We'll try to extract useful selector info
                    if (targetStr.includes('Element<')) {
                        // Extract tag name from Element<tagname, ...>
                        const match = targetStr.match(/Element<(\w+)/);
                        if (match) {
                            selector = match[1].toLowerCase();
                        }
                    }
                } catch (e) {
                    // Ignore parsing errors
                }
            }

            outcomes.push({
                rule: outcome.rule,
                outcome: outcomeType,
                target: target ? String(target) : null,
                selector: selector,
                html: htmlSnippet,
                // Additional fields for normalization
                title: getRuleTitle(outcome.rule),
                description: getRuleDescription(outcome.rule),
                requirements: getRuleRequirements(outcome.rule)
            });
        }

        return {
            ok: true,
            url: window.location.href,
            title: document.title,
            timestamp: new Date().toISOString(),
            outcomes: outcomes,
            summary: {
                passedCount: summary.passed,
                failedCount: summary.failed,
                failedRuleCount: failedRules.size,  // Unique rules with failures
                cantTellCount: summary.cantTell,
                inapplicableCount: summary.inapplicable,
                totalOutcomes: filteredRawOutcomes.length,
                totalRawOutcomes: rawOutcomes.length,
                filteredOutByLevel: filteredOutCount,
                auditTimeMs: auditTime
            },
            conformance: conformance,
            version: alfaVersion
        };

    } catch (error) {
        return {
            ok: false,
            error: error.message,
            stack: error.stack,
            url: window.location.href
        };
    }
})();
