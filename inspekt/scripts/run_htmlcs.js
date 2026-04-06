// Inspekt HTML_CodeSniffer Accessibility Audit Script
// Note: HTMLCS library is injected before this script executes
(async function() {
    try {
        // Verify HTMLCS is available (it should be loaded before this script)
        if (typeof HTMLCS === 'undefined') {
            throw new Error('HTML_CodeSniffer library not found - this should not happen');
        }

        // Configuration object injected from Python
        const config = __HTMLCS_CONFIG__;

        const standard = config.standard || 'WCAG2AA';
        const includeNotices = config.includeNotices === true;
        const includeWarnings = config.includeWarnings !== false;  // Default true

        // Run HTMLCS audit
        const messages = await new Promise((resolve, reject) => {
            HTMLCS.process(standard, document, function() {
                const msgs = HTMLCS.getMessages();
                resolve(msgs);
            }, function(error) {
                reject(new Error(error || 'HTMLCS processing failed'));
            });
        });

        // Filter messages based on config
        let filteredMessages = messages.filter(msg => {
            // Type 1 = Error, Type 2 = Warning, Type 3 = Notice
            if (msg.type === 1) return true;  // Always include errors
            if (msg.type === 2) return includeWarnings;
            if (msg.type === 3) return includeNotices;
            return false;
        });

        // Convert messages to serializable format
        const serializedMessages = filteredMessages.map(msg => {
            // Get a CSS selector for the element
            let selector = '';
            if (msg.element && msg.element.nodeType === 1) {
                try {
                    selector = getUniqueSelector(msg.element);
                } catch (e) {
                    selector = msg.element.tagName ? msg.element.tagName.toLowerCase() : '';
                }
            }

            // Get HTML snippet
            let htmlSnippet = '';
            if (msg.element && msg.element.outerHTML) {
                // Truncate long HTML
                htmlSnippet = msg.element.outerHTML;
                if (htmlSnippet.length > 500) {
                    htmlSnippet = htmlSnippet.substring(0, 500) + '...';
                }
            }

            return {
                type: msg.type,
                code: msg.code,
                message: msg.msg,
                selector: selector,
                element: htmlSnippet
            };
        });

        // Calculate summary statistics
        const errorCount = serializedMessages.filter(m => m.type === 1).length;
        const warningCount = serializedMessages.filter(m => m.type === 2).length;
        const noticeCount = serializedMessages.filter(m => m.type === 3).length;

        return {
            ok: true,
            url: window.location.href,
            title: document.title,
            timestamp: new Date().toISOString(),
            standard: standard,
            messages: serializedMessages,
            summary: {
                errorCount: errorCount,
                warningCount: warningCount,
                noticeCount: noticeCount,
                totalCount: serializedMessages.length
            },
            version: typeof HTMLCS.version !== 'undefined' ? HTMLCS.version : 'unknown'
        };

    } catch (error) {
        return {
            ok: false,
            error: error.message,
            stack: error.stack,
            url: window.location.href
        };
    }

    // Helper function to generate a unique CSS selector for an element
    function getUniqueSelector(element) {
        if (!element || element.nodeType !== 1) return '';

        // If element has an ID, use it
        if (element.id) {
            return '#' + CSS.escape(element.id);
        }

        // Build selector from tag + classes + nth-child
        const parts = [];
        let current = element;

        while (current && current.nodeType === 1 && current !== document.documentElement) {
            let selector = current.tagName.toLowerCase();

            // Add ID if present
            if (current.id) {
                selector = '#' + CSS.escape(current.id);
                parts.unshift(selector);
                break;
            }

            // Add classes if present
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
                    child => child.tagName === current.tagName
                );
                if (siblings.length > 1) {
                    const index = siblings.indexOf(current) + 1;
                    selector += ':nth-of-type(' + index + ')';
                }
            }

            parts.unshift(selector);
            current = current.parentElement;
        }

        return parts.join(' > ');
    }
})()
