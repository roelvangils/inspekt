/**
 * Element Outline Utility
 * Provides reusable functions for adding/removing persistent outlines to elements
 */

import { evalInPage } from './devtools.js';

/**
 * Add persistent outline to currently inspected element
 * @param {string} borderStyle - CSS outline style (default: '2px solid #0066ff')
 * @param {string} backgroundColor - CSS background color (default: 'rgba(0, 102, 255, 0.1)')
 * @param {Function} callback - Optional callback(result, error) after outline applied
 */
export function addPersistentOutline(borderStyle = '2px solid #0066ff', backgroundColor = 'rgba(0, 102, 255, 0.1)', callback = null) {
    evalInPage(
        `(function() {
            const el = window.__INSPEKT_INSPECTED_ELEMENT__;
            if (!el) return { success: false, error: 'No element selected' };

            // Remove any existing outline from previous element
            const existing = document.querySelector('[data-inspekt-outline="true"]');
            if (existing && existing !== el) {
                const originalOutline = existing.getAttribute('data-inspekt-original-outline');
                const originalBg = existing.getAttribute('data-inspekt-original-bg');
                const originalTransition = existing.getAttribute('data-inspekt-original-transition');

                if (originalOutline !== null) {
                    existing.style.outline = originalOutline;
                }
                if (originalBg !== null) {
                    existing.style.backgroundColor = originalBg;
                }
                if (originalTransition !== null) {
                    existing.style.transition = originalTransition;
                }

                existing.style.outlineOffset = '';
                existing.removeAttribute('data-inspekt-outline');
                existing.removeAttribute('data-inspekt-original-outline');
                existing.removeAttribute('data-inspekt-original-bg');
                existing.removeAttribute('data-inspekt-original-transition');
            }

            // Store original styles if not already stored
            if (!el.hasAttribute('data-inspekt-outline')) {
                el.setAttribute('data-inspekt-original-outline', el.style.outline || '');
                el.setAttribute('data-inspekt-original-bg', el.style.backgroundColor || '');
                el.setAttribute('data-inspekt-original-transition', el.style.transition || '');
            }

            el.setAttribute('data-inspekt-outline', 'true');

            // Add smooth transition for morph effect
            el.style.transition = 'outline 0.15s cubic-bezier(0.4, 0, 0.2, 1), background-color 0.15s cubic-bezier(0.4, 0, 0.2, 1)';

            // Apply outline and background
            el.style.outline = '${borderStyle}';
            el.style.outlineOffset = '2px';
            el.style.backgroundColor = '${backgroundColor}';

            return {
                success: true,
                tag: el.tagName.toLowerCase(),
                selector: el.getAttribute('data-inspekt-selector') || el.tagName
            };
        })()`,
        (result, error) => {
            if (callback) {
                callback(result, error);
            }
        }
    );
}

/**
 * Remove persistent outline from current element
 * @param {Function} callback - Optional callback(result, error) after outline removed
 */
export function removePersistentOutline(callback = null) {
    evalInPage(
        `(function() {
            const el = document.querySelector('[data-inspekt-outline="true"]');
            if (!el) return { success: false, error: 'No outline to remove' };

            // Restore original styles
            const originalOutline = el.getAttribute('data-inspekt-original-outline');
            const originalBg = el.getAttribute('data-inspekt-original-bg');
            const originalTransition = el.getAttribute('data-inspekt-original-transition');

            if (originalOutline !== null) {
                el.style.outline = originalOutline;
            }

            if (originalBg !== null) {
                el.style.backgroundColor = originalBg;
            }

            if (originalTransition !== null) {
                el.style.transition = originalTransition;
            }

            el.style.outlineOffset = '';

            // Remove data attributes
            el.removeAttribute('data-inspekt-outline');
            el.removeAttribute('data-inspekt-original-outline');
            el.removeAttribute('data-inspekt-original-bg');
            el.removeAttribute('data-inspekt-original-transition');

            return {
                success: true,
                tag: el.tagName.toLowerCase()
            };
        })()`,
        (result, error) => {
            if (callback) {
                callback(result, error);
            }
        }
    );
}
