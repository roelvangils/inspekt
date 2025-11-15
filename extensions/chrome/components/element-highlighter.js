/**
 * Element Highlighter Component
 * Provides spotlight highlighting for elements
 */

import { evalInPage } from '../utils/devtools.js';

export class ElementHighlighter {
    constructor(elementDisplay) {
        this.elementDisplay = elementDisplay;
        this.btnHighlight = document.getElementById('btnHighlight');

        // Listen for highlight events from history
        window.addEventListener('inspekt:highlight-element', (e) => {
            this.highlight(e.detail.forceNew);
        });
    }

    /**
     * Initialize highlighter
     */
    init() {
        // Event listener is already set up in constructor
    }

    /**
     * Highlight current element with spotlight effect
     * @param {boolean} forceNew - If true, dismiss existing highlight and create new one
     */
    highlight(forceNew = false) {
        const currentElement = this.elementDisplay.getCurrentElement();
        if (!currentElement) return;

        evalInPage(
            `(function() {
                const forceNew = ${forceNew};
                const el = window.__INSPEKT_INSPECTED_ELEMENT__;
                if (!el) return false;

                // Check if highlight is already active
                const highlightedEl = document.querySelector('[data-zen-highlighted="true"]');

                if (highlightedEl) {
                    // Restore previous element's styles
                    const originalStyles = highlightedEl.getAttribute('data-zen-original-styles');
                    if (originalStyles) {
                        highlightedEl.style.cssText = originalStyles;
                    }
                    highlightedEl.removeAttribute('data-zen-highlighted');
                    highlightedEl.removeAttribute('data-zen-original-styles');

                    // If not forcing new, just dismiss and return
                    if (!forceNew) {
                        return { dismissed: true };
                    }
                    // Otherwise continue to create new highlight below
                }

                // Check if element is in viewport
                const rect = el.getBoundingClientRect();
                const isInViewport = (
                    rect.top >= 0 &&
                    rect.left >= 0 &&
                    rect.bottom <= window.innerHeight &&
                    rect.right <= window.innerWidth
                );

                // Scroll into view if needed
                if (!isInViewport) {
                    el.scrollIntoView({
                        behavior: 'smooth',
                        block: 'center',
                        inline: 'center'
                    });
                }

                // Wait a bit for scroll to complete, then apply highlight
                setTimeout(() => {
                    // Store original styles
                    el.setAttribute('data-zen-original-styles', el.style.cssText);
                    el.setAttribute('data-zen-highlighted', 'true');

                    // Get background color - walk up the tree if transparent
                    const computedStyle = window.getComputedStyle(el);
                    let bgColor = computedStyle.backgroundColor;
                    if (!bgColor || bgColor === 'rgba(0, 0, 0, 0)' || bgColor === 'transparent') {
                        let parent = el.parentElement;
                        while (parent && (!bgColor || bgColor === 'rgba(0, 0, 0, 0)' || bgColor === 'transparent')) {
                            bgColor = window.getComputedStyle(parent).backgroundColor;
                            parent = parent.parentElement;
                        }
                        // Fallback to white if still transparent
                        if (!bgColor || bgColor === 'rgba(0, 0, 0, 0)' || bgColor === 'transparent') {
                            bgColor = 'rgb(255, 255, 255)';
                        }
                    }

                    // Apply highlight styles directly to element
                    const originalPosition = computedStyle.position;
                    const needsPositionChange = originalPosition === 'static';

                    // Build new style rules
                    el.style.position = needsPositionChange ? 'relative' : originalPosition;
                    el.style.isolation = 'isolate';
                    el.style.zIndex = '1';
                    el.style.transform = 'scale(1)';
                    el.style.transformOrigin = 'center center';
                    el.style.transition = 'transform 0.4s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.4s ease-out';
                    el.style.boxShadow = '0 0 0 4px #0066ff, 0 0 0 8px rgba(0, 102, 255, 0.3), 0 20px 60px rgba(0, 102, 255, 0.5), 0 0 100px rgba(0, 102, 255, 0.3)';
                    el.style.backgroundColor = bgColor;

                    // Scale factor - larger than before
                    const scale = 1.3;

                    // Animate in
                    requestAnimationFrame(() => {
                        requestAnimationFrame(() => {
                            el.style.transform = 'scale(' + scale + ')';
                        });
                    });

                    // Keep visible for 5 seconds, then fade out over 0.5s
                    setTimeout(() => {
                        // Animate out
                        el.style.transition = 'transform 0.5s ease-out, box-shadow 0.5s ease-out';
                        el.style.transform = 'scale(' + (scale * 0.95) + ')';
                        el.style.boxShadow = 'none';

                        // Restore original styles after fade completes
                        setTimeout(() => {
                            const originalStyles = el.getAttribute('data-zen-original-styles');
                            if (originalStyles) {
                                el.style.cssText = originalStyles;
                            }
                            el.removeAttribute('data-zen-highlighted');
                            el.removeAttribute('data-zen-original-styles');
                        }, 500);
                    }, 5000);

                }, isInViewport ? 0 : 500); // Wait for scroll if needed

                return { created: true };
            })()`,
            (result, error) => {
                if (result) {
                    this.btnHighlight.classList.add('success-flash');
                    setTimeout(() => this.btnHighlight.classList.remove('success-flash'), 500);
                }
            }
        );
    }
}
