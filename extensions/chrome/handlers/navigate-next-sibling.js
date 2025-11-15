/**
 * Navigate to Next Sibling Element Handler
 *
 * Navigates from the currently inspected element to its next sibling element in the DOM tree.
 * Keyboard shortcut: R (right)
 */

import { evalInPage } from '../utils/devtools.js';

export function handleNavigateNextSibling(context) {
    console.log('[Navigate Next Sibling] Executing navigation to next sibling element');

    const currentElement = context.elementDisplay.getCurrentElement();

    if (!currentElement) {
        console.warn('[Navigate Next Sibling] No element selected');
        return;
    }

    evalInPage(
        `(function() {
            const el = window.__INSPEKT_INSPECTED_ELEMENT__;
            if (!el) {
                return { ok: false, error: 'No element selected' };
            }

            // Get next sibling element (not text node)
            const nextSibling = el.nextElementSibling;

            if (!nextSibling) {
                return { ok: false, error: 'No next sibling' };
            }

            // Update inspected element to next sibling
            window.__INSPEKT_INSPECTED_ELEMENT__ = nextSibling;

            // Scroll into view
            nextSibling.scrollIntoView({ behavior: 'smooth', block: 'center' });

            return {
                ok: true,
                siblingTag: nextSibling.tagName.toLowerCase()
            };
        })()`,
        (result, error) => {
            if (error || !result.ok) {
                console.error('[Navigate Next Sibling] Error:', error || result.error);
                return;
            }

            console.log('[Navigate Next Sibling] Successfully navigated to next sibling:', result.siblingTag);

            // Trigger spotlight highlight to draw attention to navigated element
            context.elementHighlighter.highlight(true);
        }
    );
}
