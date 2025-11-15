/**
 * Navigate to Parent Element Handler
 *
 * Navigates from the currently inspected element to its parent element in the DOM tree.
 * Keyboard shortcut: U (up)
 */

import { evalInPage } from '../utils/devtools.js';

export function handleNavigateParent(context) {
    console.log('[Navigate Parent] Executing navigation to parent element');

    const currentElement = context.elementDisplay.getCurrentElement();

    if (!currentElement) {
        console.warn('[Navigate Parent] No element selected');
        return;
    }

    evalInPage(
        `(function() {
            const el = window.__INSPEKT_INSPECTED_ELEMENT__;
            if (!el) {
                return { ok: false, error: 'No element selected' };
            }

            const parent = el.parentElement;

            // Check if parent exists and is not body/html (which we want to avoid)
            if (!parent) {
                return { ok: false, error: 'No parent element' };
            }

            if (parent === document.body) {
                return { ok: false, error: 'Already at <body> element' };
            }

            if (parent === document.documentElement) {
                return { ok: false, error: 'Already at <html> element' };
            }

            // Update inspected element to parent
            window.__INSPEKT_INSPECTED_ELEMENT__ = parent;

            // Scroll into view
            parent.scrollIntoView({ behavior: 'smooth', block: 'center' });

            return {
                ok: true,
                parentTag: parent.tagName.toLowerCase()
            };
        })()`,
        (result, error) => {
            if (error || !result.ok) {
                console.error('[Navigate Parent] Error:', error || result.error);
                return;
            }

            console.log('[Navigate Parent] Successfully navigated to parent:', result.parentTag);

            // Trigger spotlight highlight to draw attention to navigated element
            context.elementHighlighter.highlight(true);
        }
    );
}
