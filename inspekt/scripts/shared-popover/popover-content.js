/**
 * Shared Popover Content Generator
 *
 * Creates Axe-style popovers for both Axe and IBM accessibility results.
 * Uses a normalized violation data structure that works with both tools.
 */

(function() {
    'use strict';

    /**
     * Escape HTML to prevent XSS
     */
    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Generate Markdown content from normalized violation data
     * @param {number} badgeNumber - The badge number
     * @param {Object} data - Normalized violation data
     * @returns {string} Markdown formatted content
     */
    function generateMarkdown(badgeNumber, data) {
        const impactLabel = data.impact.charAt(0).toUpperCase() + data.impact.slice(1);

        let markdown = `# Accessibility Violation #${badgeNumber}\n\n`;
        markdown += `**Impact:** ${impactLabel}\n\n`;
        markdown += `## ${data.title}\n\n`;

        if (data.description) {
            markdown += `${data.description}\n\n`;
        }

        // What's Wrong / Failure Summary
        if (data.failureSummary) {
            markdown += `### What's Wrong\n\n`;
            markdown += `${data.failureSummary}\n\n`;
        }

        // HTML Snippet
        if (data.html) {
            markdown += `### HTML Snippet\n\n`;
            markdown += `\`\`\`html\n${data.html}\n\`\`\`\n\n`;
        }

        // CSS Selector
        if (data.selector && data.selector.length > 0) {
            const selectorText = Array.isArray(data.selector) ? data.selector.join(', ') : data.selector;
            markdown += `### CSS Selector\n\n`;
            markdown += `\`${selectorText}\`\n\n`;
        }

        // Fix Details (Axe only - has checks)
        if (data.checks && (data.checks.any || data.checks.all || data.checks.none)) {
            markdown += `### Fix Details\n\n`;

            if (data.checks.all && data.checks.all.length > 0) {
                markdown += `#### Required Fixes (all must pass):\n\n`;
                data.checks.all.forEach((check, idx) => {
                    const status = check.result ? '✓' : '✗';
                    markdown += `${idx + 1}. ${status} ${check.message}\n`;
                });
                markdown += `\n`;
            }

            if (data.checks.any && data.checks.any.length > 0) {
                markdown += `#### Possible Fixes (at least one must pass):\n\n`;
                data.checks.any.forEach((check, idx) => {
                    const status = check.result ? '✓' : '✗';
                    markdown += `${idx + 1}. ${status} ${check.message}\n`;
                });
                markdown += `\n`;
            }

            if (data.checks.none && data.checks.none.length > 0) {
                markdown += `#### Must Not Occur:\n\n`;
                data.checks.none.forEach((check, idx) => {
                    const status = check.result ? '✓' : '✗';
                    markdown += `${idx + 1}. ${status} ${check.message}\n`;
                });
                markdown += `\n`;
            }
        }

        // WCAG Tags
        if (data.tags && data.tags.length > 0) {
            markdown += `### Standards\n\n`;
            markdown += data.tags.join(', ') + '\n\n';
        }

        // Learn More Link
        if (data.helpUrl) {
            const linkText = data.source === 'ibm'
                ? `IBM Accessibility - ${data.ruleId}`
                : `Deque University - ${data.ruleId}`;
            markdown += `### Learn More\n\n`;
            markdown += `[${linkText}](${data.helpUrl})\n`;
        }

        return markdown;
    }

    /**
     * Creates a popover element with detailed violation information.
     *
     * @param {string} popoverId - Unique ID for the popover element
     * @param {string} badgeId - ID of the badge that triggers this popover
     * @param {number} badgeNumber - The badge number
     * @param {Object} data - Normalized violation data:
     *   - source: 'axe' | 'ibm'
     *   - impact: 'critical' | 'serious' | 'moderate' | 'minor'
     *   - title: string (rule description)
     *   - description: string (optional, full description)
     *   - failureSummary: string (what's wrong)
     *   - html: string (element HTML snippet)
     *   - selector: string[] (CSS selectors)
     *   - checks: { any: [], all: [], none: [] } | null (Axe only)
     *   - tags: string[] (WCAG tags)
     *   - helpUrl: string (documentation link)
     *   - ruleId: string (rule identifier)
     * @param {Object} popoverCore - Reference to window.__inspektPopoverCore__
     * @returns {HTMLElement} The popover element
     */
    function createPopover(popoverId, badgeId, badgeNumber, data, popoverCore) {
        const popover = document.createElement('div');
        popover.id = popoverId;
        popover.setAttribute('popover', 'auto');
        popover.className = 'inspekt-axe-popover';
        popover.setAttribute('data-inspekt-popover', badgeNumber);
        popover.setAttribute('style', `position-anchor: --badge-${badgeNumber};`);

        const impact = data.impact || 'minor';
        const impactLabel = impact.charAt(0).toUpperCase() + impact.slice(1);

        // Determine learn more text based on source
        const learnMoreText = data.source === 'ibm'
            ? 'Learn more at IBM Accessibility'
            : 'Learn more at Deque University';

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
                    <button class="inspekt-axe-nav__skip-similar" type="button" title="Skip similar violations">
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
                <h3 class="inspekt-axe-popover__title">${escapeHtml(data.title)}</h3>
            </div>
            <div role="tablist" aria-label="Violation details" class="inspekt-axe-popover__tablist">
                <button role="tab"
                        aria-selected="true"
                        aria-controls="panel-details-${badgeNumber}"
                        id="tab-details-${badgeNumber}"
                        class="inspekt-axe-popover__tab inspekt-axe-popover__tab--active"
                        tabindex="0"
                        type="button">
                    Details
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
                 id="panel-details-${badgeNumber}"
                 aria-labelledby="tab-details-${badgeNumber}"
                 class="inspekt-axe-popover__tabpanel inspekt-axe-popover__body">
        `;

        // What's Wrong / Failure Summary
        if (data.failureSummary) {
            content += `
                <div class="inspekt-axe-popover__section">
                    <span class="inspekt-axe-popover__section-label">What's wrong</span>
                    <div class="inspekt-axe-popover__failure-summary">${escapeHtml(data.failureSummary)}</div>
                </div>
            `;
        }

        // HTML Snippet (collapsible)
        if (data.html) {
            content += `
                <div class="inspekt-axe-popover__section">
                    <details class="inspekt-axe-popover__details">
                        <summary>HTML Snippet</summary>
                        <div class="inspekt-axe-popover__details-content">
                            <pre class="inspekt-axe-popover__code">${escapeHtml(data.html)}</pre>
                        </div>
                    </details>
                </div>
            `;
        }

        // CSS Selector
        if (data.selector && data.selector.length > 0) {
            const selectorText = Array.isArray(data.selector) ? data.selector.join(', ') : data.selector;
            content += `
                <div class="inspekt-axe-popover__section">
                    <span class="inspekt-axe-popover__section-label">CSS Selector</span>
                    <div class="inspekt-axe-popover__selector">${escapeHtml(selectorText)}</div>
                </div>
            `;
        }

        // Fix Details - ONLY for Axe (IBM doesn't have checks)
        if (data.checks && (data.checks.any || data.checks.all || data.checks.none)) {
            const hasChecks = (data.checks.all && data.checks.all.length > 0) ||
                              (data.checks.any && data.checks.any.length > 0) ||
                              (data.checks.none && data.checks.none.length > 0);

            if (hasChecks) {
                content += `<div class="inspekt-axe-popover__section">`;
                content += `<span class="inspekt-axe-popover__section-label">Fix Details</span>`;
                content += `<div class="inspekt-axe-popover__checks">`;

                // "All" checks (must all pass)
                if (data.checks.all && data.checks.all.length > 0) {
                    content += `<div class="inspekt-axe-popover__check-group">`;
                    content += `<div class="inspekt-axe-popover__check-title">Required Fixes (all must pass):</div>`;
                    content += `<ul class="inspekt-axe-popover__check-list">`;
                    data.checks.all.forEach(check => {
                        const status = check.result ? 'pass' : 'fail';
                        content += `<li class="inspekt-axe-popover__check-item inspekt-axe-popover__check-item--${status}">`;
                        content += `<span class="inspekt-axe-popover__check-message">${escapeHtml(check.message)}</span>`;
                        content += `</li>`;
                    });
                    content += `</ul></div>`;
                }

                // "Any" checks (at least one must pass)
                if (data.checks.any && data.checks.any.length > 0) {
                    content += `<div class="inspekt-axe-popover__check-group">`;
                    content += `<div class="inspekt-axe-popover__check-title">Possible Fixes (at least one must pass):</div>`;
                    content += `<ul class="inspekt-axe-popover__check-list">`;
                    data.checks.any.forEach(check => {
                        const status = check.result ? 'pass' : 'fail';
                        content += `<li class="inspekt-axe-popover__check-item inspekt-axe-popover__check-item--${status}">`;
                        content += `<span class="inspekt-axe-popover__check-message">${escapeHtml(check.message)}</span>`;
                        content += `</li>`;
                    });
                    content += `</ul></div>`;
                }

                // "None" checks (must all not be present)
                if (data.checks.none && data.checks.none.length > 0) {
                    content += `<div class="inspekt-axe-popover__check-group">`;
                    content += `<div class="inspekt-axe-popover__check-title">Must Not Occur:</div>`;
                    content += `<ul class="inspekt-axe-popover__check-list">`;
                    data.checks.none.forEach(check => {
                        const status = check.result ? 'pass' : 'fail';
                        content += `<li class="inspekt-axe-popover__check-item inspekt-axe-popover__check-item--${status}">`;
                        content += `<span class="inspekt-axe-popover__check-message">${escapeHtml(check.message)}</span>`;
                        content += `</li>`;
                    });
                    content += `</ul></div>`;
                }

                content += `</div></div>`;
            }
        }

        // WCAG Tags
        if (data.tags && data.tags.length > 0) {
            content += `
                <div class="inspekt-axe-popover__section">
                    <span class="inspekt-axe-popover__section-label">Standards</span>
                    <div class="inspekt-axe-popover__tags">
            `;
            data.tags.forEach(tag => {
                const isWCAG = tag.toLowerCase().includes('wcag');
                const tagClass = isWCAG ? 'inspekt-axe-popover__tag--wcag' : '';
                content += `<span class="inspekt-axe-popover__tag ${tagClass}">${escapeHtml(tag)}</span>`;
            });
            content += `</div></div>`;
        }

        content += `</div>`; // Close default tabpanel

        // Markdown tabpanel with editable textarea
        const markdownContent = generateMarkdown(badgeNumber, data);
        content += `
            <div role="tabpanel"
                 id="panel-markdown-${badgeNumber}"
                 aria-labelledby="tab-markdown-${badgeNumber}"
                 class="inspekt-axe-popover__tabpanel inspekt-axe-popover__markdown-panel"
                 hidden>
                <div class="inspekt-axe-popover__markdown-header">
                    <button class="inspekt-axe-popover__copy-btn" type="button" title="Copy markdown to clipboard">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                        </svg>
                        Copy
                    </button>
                </div>
                <textarea class="inspekt-axe-popover__markdown-textarea"
                          aria-label="Markdown formatted violation details (editable)"
                          spellcheck="false">${escapeHtml(markdownContent)}</textarea>
            </div>
        `;

        // Footer with Reveal in DevTools and Learn More buttons
        content += `
            <div class="inspekt-axe-popover__footer">
                <button class="inspekt-axe-popover__reveal-btn" type="button" title="Reveal element in DevTools Elements panel">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <rect x="3" y="3" width="18" height="18" rx="2"/>
                        <path d="M9 9l6 6M15 9l-6 6"/>
                    </svg>
                    Reveal in DevTools
                </button>
        `;
        if (data.helpUrl) {
            content += `
                <a href="${escapeHtml(data.helpUrl)}" target="_blank" rel="noopener noreferrer" class="inspekt-axe-popover__learn-more">
                    ${learnMoreText}
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                        <polyline points="15 3 21 3 21 9"/>
                        <line x1="10" y1="14" x2="21" y2="3"/>
                    </svg>
                </a>
            `;
        }
        content += `</div>`;

        popover.innerHTML = content;

        // Bind event listeners
        bindPopoverEvents(popover, popoverCore);

        return popover;
    }

    /**
     * Bind all event listeners to the popover
     */
    function bindPopoverEvents(popover, popoverCore) {
        const prevBtn = popover.querySelector('.inspekt-axe-nav__prev');
        const nextBtn = popover.querySelector('.inspekt-axe-nav__next');
        const closeBtn = popover.querySelector('.inspekt-axe-nav__close');
        const skipBtn = popover.querySelector('.inspekt-axe-nav__skip-similar');
        const detachBtn = popover.querySelector('.inspekt-axe-nav__detach');

        // Navigation
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                const prevIndex = popoverCore.getPreviousViolationIndex();
                if (prevIndex >= 0) {
                    popoverCore.navigateToViolation(prevIndex);
                }
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                const nextIndex = popoverCore.getNextViolationIndex();
                if (nextIndex >= 0) {
                    popoverCore.navigateToViolation(nextIndex);
                }
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                popover.hidePopover();
            });
        }

        // Skip similar
        if (skipBtn) {
            skipBtn.addEventListener('click', () => {
                const isActive = popoverCore.toggleSkipSimilar();
                skipBtn.classList.toggle('inspekt-axe-nav__skip-similar--active', isActive);
                popoverCore.updateBadgeDimming();
                popoverCore.updateNavigationControls(popover);
            });
        }

        // Detach
        if (detachBtn) {
            detachBtn.addEventListener('click', () => {
                popoverCore.toggleDetach(popover);
            });
        }

        // Reveal in DevTools button
        const revealBtn = popover.querySelector('.inspekt-axe-popover__reveal-btn');
        if (revealBtn) {
            revealBtn.addEventListener('click', () => {
                const violation = popoverCore.getViolations()[popoverCore.getCurrentIndex()];
                if (violation && violation.element) {
                    if (typeof inspect === 'function') {
                        inspect(violation.element);
                    } else {
                        console.log('[Inspekt] inspect() not available - open DevTools first');
                    }
                }
            });
        }

        // Tab switching functionality
        const tabs = popover.querySelectorAll('[role="tab"]');
        const tabPanels = popover.querySelectorAll('[role="tabpanel"]');

        function switchTab(newTab) {
            tabs.forEach(tab => {
                tab.setAttribute('aria-selected', 'false');
                tab.setAttribute('tabindex', '-1');
                tab.classList.remove('inspekt-axe-popover__tab--active');
            });
            tabPanels.forEach(panel => {
                panel.hidden = true;
            });

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

        tabs.forEach(tab => {
            tab.addEventListener('click', () => switchTab(tab));

            tab.addEventListener('keydown', (e) => {
                let targetTab = null;
                if (e.key === 'ArrowLeft') {
                    const idx = Array.from(tabs).indexOf(tab);
                    targetTab = tabs[idx === 0 ? tabs.length - 1 : idx - 1];
                } else if (e.key === 'ArrowRight') {
                    const idx = Array.from(tabs).indexOf(tab);
                    targetTab = tabs[(idx + 1) % tabs.length];
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

        // Copy button functionality
        const copyBtn = popover.querySelector('.inspekt-axe-popover__copy-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
                const textarea = popover.querySelector('.inspekt-axe-popover__markdown-textarea');
                if (textarea) {
                    try {
                        await navigator.clipboard.writeText(textarea.value);
                        copyBtn.classList.add('inspekt-axe-popover__copy-btn--copied');
                        const originalHTML = copyBtn.innerHTML;
                        copyBtn.innerHTML = `
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Copied!
                        `;
                        setTimeout(() => {
                            copyBtn.classList.remove('inspekt-axe-popover__copy-btn--copied');
                            copyBtn.innerHTML = originalHTML;
                        }, 2000);
                    } catch (err) {
                        console.error('[Inspekt] Failed to copy:', err);
                    }
                }
            });
        }

        // Handle popover toggle event
        popover.addEventListener('toggle', (e) => {
            if (e.newState === 'open') {
                popoverCore.handlePopoverOpen(popover);
                setTimeout(() => {
                    popover.setAttribute('tabindex', '-1');
                    popover.focus();
                }, 0);
            } else if (e.newState === 'closed') {
                popover.removeAttribute('tabindex');
            }
        });

        // Keyboard navigation
        popover.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                popover.hidePopover();
                e.stopPropagation();
            } else if (e.key === 'ArrowLeft' && !e.target.matches('textarea') && !e.target.matches('[role="tab"]')) {
                const prevIndex = popoverCore.getPreviousViolationIndex();
                if (prevIndex >= 0) {
                    popoverCore.navigateToViolation(prevIndex);
                    e.preventDefault();
                }
            } else if (e.key === 'ArrowRight' && !e.target.matches('textarea') && !e.target.matches('[role="tab"]')) {
                const nextIndex = popoverCore.getNextViolationIndex();
                if (nextIndex >= 0) {
                    popoverCore.navigateToViolation(nextIndex);
                    e.preventDefault();
                }
            }
        });
    }

    /**
     * Normalize Axe violation data to common format
     */
    function normalizeAxeData(violation, node) {
        return {
            source: 'axe',
            impact: violation.impact || node.impact || 'minor',
            title: violation.help,
            description: violation.description,
            failureSummary: node.failureSummary,
            html: node.html,
            selector: node.target,
            checks: {
                any: node.any || [],
                all: node.all || [],
                none: node.none || []
            },
            tags: violation.tags || [],
            helpUrl: violation.helpUrl,
            ruleId: violation.id
        };
    }

    /**
     * Normalize IBM issue data to common format
     */
    function normalizeIbmData(issue) {
        // Map IBM level to Axe impact
        const levelToImpact = {
            'violation': 'critical',
            'potentialviolation': 'serious',
            'recommendation': 'moderate',
            'potentialrecommendation': 'minor',
            'manual': 'minor'
        };

        return {
            source: 'ibm',
            impact: levelToImpact[issue.level] || 'minor',
            title: issue.ruleId,
            description: issue.message,
            failureSummary: issue.message,
            html: issue.snippet,
            selector: issue.path ? [issue.path] : [],
            checks: null, // IBM doesn't have checks
            tags: issue.wcag || [],
            helpUrl: issue.helpUrl || null,
            ruleId: issue.ruleId
        };
    }

    /**
     * Normalize HTML CodeSniffer issue data to common format
     */
    function normalizeHcsData(issue) {
        // HTMLCS type: 1=Error, 2=Warning, 3=Notice
        const typeToImpact = {
            1: 'critical',
            2: 'moderate',
            3: 'minor'
        };

        // Extract element HTML if available
        let html = '';
        if (issue.element && issue.element.outerHTML) {
            html = issue.element.outerHTML.substring(0, 500);
        }

        // Generate selector from element
        let selector = [];
        if (issue.element) {
            try {
                const tagName = issue.element.tagName.toLowerCase();
                const id = issue.element.id ? `#${issue.element.id}` : '';
                const classes = issue.element.className ?
                    `.${issue.element.className.trim().split(/\s+/).join('.')}` : '';
                selector = [tagName + id + classes];
            } catch (e) {
                selector = [];
            }
        }

        return {
            source: 'hcs',
            impact: typeToImpact[issue.type] || 'minor',
            title: issue.code || 'HTML CodeSniffer Issue',
            description: issue.msg,
            failureSummary: issue.msg,
            html: html,
            selector: selector,
            checks: null, // HTMLCS doesn't have checks
            tags: [], // HTMLCS doesn't provide WCAG tags directly
            helpUrl: null, // HTMLCS doesn't provide help URLs
            ruleId: issue.code || 'unknown'
        };
    }

    /**
     * Normalize Siteimprove Alfa issue data to common format
     */
    function normalizeSiaData(issue) {
        // Alfa outcome: failed, cantTell, passed, inapplicable
        const outcomeToImpact = {
            'failed': 'serious',
            'cantTell': 'moderate',
            'passed': 'minor',
            'inapplicable': 'minor'
        };

        // Extract element HTML if available
        let html = '';
        if (issue.target && issue.target.outerHTML) {
            html = issue.target.outerHTML.substring(0, 500);
        }

        return {
            source: 'sia',
            impact: outcomeToImpact[issue.outcome] || 'moderate',
            title: issue.title || issue.rule || 'Siteimprove Alfa Issue',
            description: issue.message || '',
            failureSummary: issue.message || '',
            html: html,
            selector: issue.path ? [issue.path] : [],
            checks: null, // Alfa doesn't have Axe-style checks
            tags: issue.requirements || [], // WCAG requirements
            helpUrl: issue.rule ? `https://alfa.siteimprove.com/rules/${issue.rule}` : null,
            ruleId: issue.rule || 'unknown'
        };
    }

    /**
     * Engine normalizer registry for dynamic engine support
     */
    const ENGINE_NORMALIZERS = {
        axe: normalizeAxeData,
        eac: normalizeIbmData,
        ibm: normalizeIbmData, // Alias for backwards compatibility
        hcs: normalizeHcsData,
        sia: normalizeSiaData
    };

    /**
     * Engine display names for UI
     */
    const ENGINE_DISPLAY_NAMES = {
        axe: 'Axe',
        eac: 'IBM Equal Access',
        ibm: 'IBM Equal Access',
        hcs: 'HTML CodeSniffer',
        sia: 'Siteimprove Alfa'
    };

    /**
     * Creates a unified popover for multi-engine violations.
     * Uses the same advanced styling as createPopover() but supports multiple engines.
     *
     * @param {Object} violation - Unified violation data:
     *   - popoverId: string
     *   - badgeId: string
     *   - element: DOM element
     *   - sources: { axe: [...], eac: [...], hcs: [...], sia: [...] }
     *   - hasEngine: { axe: bool, eac: bool, ... }
     *   - engineCounts: { axe: number, eac: number, ... }
     *   - totalCount: number
     *   - highestImpact: string
     * @param {number} badgeNumber - Badge number for display
     * @param {Array} engines - List of active engine IDs
     * @param {Object} popoverCore - Reference to window.__inspektPopoverCore__
     * @returns {HTMLElement} The popover element
     */
    function createUnifiedPopover(violation, badgeNumber, engines, popoverCore) {
        const popover = document.createElement('div');
        popover.id = violation.popoverId;
        popover.setAttribute('popover', 'auto');
        popover.className = 'inspekt-axe-popover';
        popover.setAttribute('data-inspekt-popover', badgeNumber);
        popover.setAttribute('style', `position-anchor: --badge-${badgeNumber};`);

        const impactLabel = violation.highestImpact.charAt(0).toUpperCase() + violation.highestImpact.slice(1);
        const activeEngines = engines.filter(e => violation.hasEngine[e]);

        // Build navigation bar with all advanced features
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
                    <button class="inspekt-axe-nav__skip-similar" type="button" title="Skip similar violations">
                        Skip similar
                    </button>
                    <button class="inspekt-axe-nav__detach" type="button" aria-pressed="false" title="Detach popover (drag freely on page)">
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
                <span class="inspekt-axe-popover__impact-badge inspekt-axe-popover__impact-badge--${violation.highestImpact}">${impactLabel}</span>
                <h3 class="inspekt-axe-popover__title">${violation.totalCount} issue${violation.totalCount > 1 ? 's' : ''} on this element</h3>
            </div>
        `;

        // Source tabs (only if multiple engines have issues)
        if (activeEngines.length > 1) {
            content += `<div class="inspekt-popover__source-tabs">`;
            activeEngines.forEach((engineId, idx) => {
                const activeClass = idx === 0 ? 'inspekt-popover__source-tab--active' : '';
                const displayName = ENGINE_DISPLAY_NAMES[engineId] || engineId;
                const count = violation.engineCounts[engineId];
                content += `
                    <button class="inspekt-popover__source-tab ${activeClass}" data-source="${engineId}">
                        ${displayName} <span class="inspekt-popover__source-count">${count}</span>
                    </button>
                `;
            });
            content += `</div>`;
        }

        // Generate content panels for each engine
        activeEngines.forEach((engineId, idx) => {
            const isMultiple = activeEngines.length > 1;
            const isFirst = idx === 0;
            const panelClass = isMultiple ? `inspekt-popover__source-panel${isFirst ? ' inspekt-popover__source-panel--active' : ''}` : '';
            const hiddenAttr = isMultiple && !isFirst ? 'hidden' : '';

            content += `<div class="${panelClass}" data-source="${engineId}" ${hiddenAttr}>`;
            content += `<div class="inspekt-axe-popover__body">`;

            // Render each issue from this engine
            const issues = violation.sources[engineId] || [];
            issues.forEach((issue, issueIdx) => {
                if (issueIdx > 0) {
                    content += '<hr class="inspekt-axe-popover__divider">';
                }

                // Get issue details based on engine
                const details = getIssueDetails(engineId, issue);

                content += `
                    <div class="inspekt-axe-popover__section">
                        <span class="inspekt-axe-popover__section-label">${escapeHtml(details.label)}</span>
                        <div class="inspekt-axe-popover__section-content" style="font-weight:600;">${escapeHtml(details.title)}</div>
                    </div>
                `;

                if (details.message) {
                    content += `
                        <div class="inspekt-axe-popover__section">
                            <span class="inspekt-axe-popover__section-label">What's wrong</span>
                            <div class="inspekt-axe-popover__failure-summary">${escapeHtml(details.message)}</div>
                        </div>
                    `;
                }

                if (details.helpUrl) {
                    content += `
                        <div class="inspekt-axe-popover__section">
                            <a href="${escapeHtml(details.helpUrl)}" target="_blank" rel="noopener noreferrer" class="inspekt-axe-popover__learn-more">
                                Learn more at ${details.helpSource}
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                                    <polyline points="15 3 21 3 21 9"/>
                                    <line x1="10" y1="14" x2="21" y2="3"/>
                                </svg>
                            </a>
                        </div>
                    `;
                }

                // CSS selector — engines that expose it (axe.target, eac/sia
                // sometimes have a path). Shows users which DOM element this
                // finding is anchored to.
                const selectorText = (() => {
                    if (engineId === 'axe' && Array.isArray(issue.target)) {
                        return issue.target.flat(Infinity).join(' ');
                    }
                    if (issue.path) return issue.path;
                    return null;
                })();
                if (selectorText) {
                    content += `
                        <div class="inspekt-axe-popover__section">
                            <span class="inspekt-axe-popover__section-label">CSS Selector</span>
                            <div class="inspekt-axe-popover__selector">${escapeHtml(selectorText)}</div>
                        </div>
                    `;
                }

                // Offending HTML snippet — collapsible so it doesn't dominate
                // the popover when violations have large markup. Open by
                // default for axe (where it's usually short and informative).
                const htmlSnippet = issue.html || issue.snippet || null;
                if (htmlSnippet) {
                    const openAttr = engineId === 'axe' ? 'open' : '';
                    content += `
                        <div class="inspekt-axe-popover__section">
                            <details class="inspekt-axe-popover__details" ${openAttr}>
                                <summary>HTML Snippet</summary>
                                <div class="inspekt-axe-popover__details-content">
                                    <pre class="inspekt-axe-popover__code">${escapeHtml(htmlSnippet)}</pre>
                                </div>
                            </details>
                        </div>
                    `;
                }
            });

            content += `</div></div>`;
        });

        popover.innerHTML = content;

        // Bind all event handlers
        bindUnifiedPopoverEvents(popover, popoverCore);

        return popover;
    }

    /**
     * Get formatted issue details based on engine type
     */
    function getIssueDetails(engineId, issue) {
        switch (engineId) {
            case 'axe':
                return {
                    label: issue.isIncomplete ? 'Needs Review' : 'Violation',
                    title: issue.help || issue.ruleId,
                    message: issue.failureSummary,
                    helpUrl: issue.helpUrl,
                    helpSource: 'Deque University'
                };
            case 'eac':
            case 'ibm':
                const levelNames = {
                    'violation': 'Violation',
                    'potentialviolation': 'Needs Review',
                    'recommendation': 'Recommendation',
                    'manual': 'Manual Check'
                };
                return {
                    label: levelNames[issue.level] || issue.level,
                    title: issue.ruleId,
                    message: issue.message,
                    helpUrl: issue.helpUrl,
                    helpSource: 'IBM Accessibility'
                };
            case 'hcs':
                const typeNames = { 1: 'Error', 2: 'Warning', 3: 'Notice' };
                return {
                    label: typeNames[issue.type] || 'Issue',
                    title: issue.code || 'HTML CodeSniffer Issue',
                    message: issue.msg,
                    helpUrl: null,
                    helpSource: null
                };
            case 'sia':
                const outcomeNames = { 'failed': 'Failed', 'cantTell': 'Needs Review' };
                return {
                    label: outcomeNames[issue.outcome] || issue.outcome,
                    title: issue.title || issue.rule,
                    message: issue.message,
                    helpUrl: issue.rule ? `https://alfa.siteimprove.com/rules/${issue.rule}` : null,
                    helpSource: 'Siteimprove Alfa'
                };
            default:
                return {
                    label: 'Issue',
                    title: issue.ruleId || 'Unknown',
                    message: issue.message || JSON.stringify(issue),
                    helpUrl: null,
                    helpSource: null
                };
        }
    }

    /**
     * Bind all event handlers for unified popover
     */
    function bindUnifiedPopoverEvents(popover, popoverCore) {
        // Document-level Arrow nav listener — installed once total, on
        // the first popover that comes through this function. Idempotent.
        _installDocLevelKeyHandler(popoverCore);

        const prevBtn = popover.querySelector('.inspekt-axe-nav__prev');
        const nextBtn = popover.querySelector('.inspekt-axe-nav__next');
        const closeBtn = popover.querySelector('.inspekt-axe-nav__close');
        const skipBtn = popover.querySelector('.inspekt-axe-nav__skip-similar');
        const detachBtn = popover.querySelector('.inspekt-axe-nav__detach');

        // Navigation
        prevBtn?.addEventListener('click', () => {
            const prevIndex = popoverCore.getPreviousViolationIndex();
            if (prevIndex >= 0) popoverCore.navigateToViolation(prevIndex);
        });

        nextBtn?.addEventListener('click', () => {
            const nextIndex = popoverCore.getNextViolationIndex();
            if (nextIndex >= 0) popoverCore.navigateToViolation(nextIndex);
        });

        closeBtn?.addEventListener('click', () => popover.hidePopover());

        // Skip similar
        skipBtn?.addEventListener('click', () => {
            const isActive = popoverCore.toggleSkipSimilar();
            skipBtn.classList.toggle('inspekt-axe-nav__skip-similar--active', isActive);
            popoverCore.updateBadgeDimming();
            popoverCore.updateNavigationControls(popover);
        });

        // Detach
        detachBtn?.addEventListener('click', () => {
            popoverCore.toggleDetach(popover);
        });

        // Source tabs switching
        const sourceTabs = popover.querySelectorAll('.inspekt-popover__source-tab');
        const sourcePanels = popover.querySelectorAll('.inspekt-popover__source-panel');

        sourceTabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const source = tab.dataset.source;

                sourceTabs.forEach(t => t.classList.remove('inspekt-popover__source-tab--active'));
                tab.classList.add('inspekt-popover__source-tab--active');

                sourcePanels.forEach(p => {
                    if (p.dataset.source === source) {
                        p.classList.add('inspekt-popover__source-panel--active');
                        p.hidden = false;
                    } else {
                        p.classList.remove('inspekt-popover__source-panel--active');
                        p.hidden = true;
                    }
                });
            });
        });

        // Toggle event
        popover.addEventListener('toggle', (e) => {
            if (e.newState === 'open') {
                popoverCore.handlePopoverOpen(popover);
                setTimeout(() => {
                    popover.setAttribute('tabindex', '-1');
                    popover.focus();
                }, 0);
            } else if (e.newState === 'closed') {
                popover.removeAttribute('tabindex');
            }
        });

        // Per-popover Escape handler (popover-scoped — it only matters
        // when this specific popover is open and has focus).
        popover.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                popover.hidePopover();
                e.stopPropagation();
            }
        });
    }

    // ============================================================
    // Document-level keyboard navigation
    // ============================================================
    // Arrow-key navigation between violations needs to work regardless
    // of where focus is, because the View Transitions API moves focus
    // away from the popover during the morph (captured elements get
    // visibility:hidden) and we can't rely on focus landing back on the
    // new popover before the user presses another key. Worse, in VM
    // mode the noVNC canvas tends to grab focus, which forwards
    // ArrowLeft/Right to the inspected page where they trigger
    // horizontal scroll / browser behaviour.
    //
    // Strategy: register ONE keydown listener on the document at
    // capture phase. It fires regardless of focus, gates on "is any
    // unified popover open", and short-circuits when the user is
    // typing in an input/textarea. Self-installs on first popover
    // creation; idempotent.
    let _docKeyListenerInstalled = false;
    function _installDocLevelKeyHandler(popoverCore) {
        if (_docKeyListenerInstalled) return;
        _docKeyListenerInstalled = true;
        document.addEventListener('keydown', (e) => {
            if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
            // Only trigger when a unified popover is currently open.
            const open = document.querySelector('[popover].inspekt-axe-popover:popover-open');
            if (!open) return;
            // Bail ONLY when focus is on a form control INSIDE the open
            // popover (e.g. the legacy markdown-export textarea — user is
            // legitimately typing). Form controls OUTSIDE the popover
            // (noVNC keeps a hidden <textarea> for input capture; xterm
            // wraps a textarea; the URL bar is an <input>) should NOT
            // block our handler — those just happen to have focus, the
            // user's intent is to navigate the popover.
            if (open.contains(e.target)) {
                const tag = e.target?.tagName;
                if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
                if (e.target?.isContentEditable) return;
            }
            // Stop here so noVNC's canvas listener doesn't see the keydown
            // and forward ArrowLeft/Right to the inspected page.
            e.preventDefault();
            e.stopPropagation();
            if (e.key === 'ArrowLeft') {
                const prevIndex = popoverCore.getPreviousViolationIndex();
                if (prevIndex >= 0) popoverCore.navigateToViolation(prevIndex);
            } else {
                const nextIndex = popoverCore.getNextViolationIndex();
                if (nextIndex >= 0) popoverCore.navigateToViolation(nextIndex);
            }
        }, true /* capture: catch the key before noVNC's listener on the canvas */);
    }

    // Export to global scope
    window.__inspektPopoverContent__ = {
        createPopover,
        createUnifiedPopover,
        generateMarkdown,
        normalizeAxeData,
        normalizeIbmData,
        normalizeHcsData,
        normalizeSiaData,
        ENGINE_NORMALIZERS,
        ENGINE_DISPLAY_NAMES,
        escapeHtml
    };

})();
