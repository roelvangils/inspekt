/**
 * Navigate to Child Element Handler
 *
 * Navigates from the currently inspected element to its first child element in the DOM tree.
 * Keyboard shortcut: D (down)
 */

import { evalInPage } from '../utils/devtools.js';

export function handleNavigateChild(context) {
    console.log('[Navigate Child] Executing navigation to child element');

    const currentElement = context.elementDisplay.getCurrentElement();

    if (!currentElement) {
        console.warn('[Navigate Child] No element selected');
        return;
    }

    evalInPage(
        `(function() {
            const el = window.__INSPEKT_INSPECTED_ELEMENT__;
            if (!el) {
                return { ok: false, error: 'No element selected' };
            }

            // Get first child element (not text node)
            const child = el.firstElementChild;

            if (!child) {
                return { ok: false, error: 'No child elements' };
            }

            // Update inspected element to child
            window.__INSPEKT_INSPECTED_ELEMENT__ = child;

            // Scroll into view
            child.scrollIntoView({ behavior: 'smooth', block: 'center' });

            return {
                ok: true,
                childTag: child.tagName.toLowerCase()
            };
        })()`,
        (result, error) => {
            if (error || !result.ok) {
                console.error('[Navigate Child] Error:', error || result.error);
                return;
            }

            console.log('[Navigate Child] Successfully navigated to child:', result.childTag);

            // Trigger spotlight highlight to draw attention to navigated element
            context.elementHighlighter.highlight(true);
        }
    );
}
