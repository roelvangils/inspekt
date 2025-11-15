/**
 * Navigate to Previous Sibling Element Handler
 *
 * Navigates from the currently inspected element to its previous sibling element in the DOM tree.
 * Keyboard shortcut: L (left)
 */

import { evalInPage } from '../utils/devtools.js';
import { addPersistentOutline } from '../utils/element-outline.js';

export function handleNavigatePrevSibling(context) {
    console.log('[Navigate Prev Sibling] Executing navigation to previous sibling element');

    const currentElement = context.elementDisplay.getCurrentElement();

    if (!currentElement) {
        console.warn('[Navigate Prev Sibling] No element selected');
        return;
    }

    evalInPage(
        `(function() {
            const el = window.__INSPEKT_INSPECTED_ELEMENT__;
            if (!el) {
                return { ok: false, error: 'No element selected' };
            }

            // Get previous sibling element (not text node)
            const prevSibling = el.previousElementSibling;

            if (!prevSibling) {
                return { ok: false, error: 'No previous sibling' };
            }

            // Update inspected element to previous sibling
            window.__INSPEKT_INSPECTED_ELEMENT__ = prevSibling;

            // Scroll into view
            prevSibling.scrollIntoView({ behavior: 'smooth', block: 'center' });

            return {
                ok: true,
                siblingTag: prevSibling.tagName.toLowerCase()
            };
        })()`,
        (result, error) => {
            if (error || !result.ok) {
                console.error('[Navigate Prev Sibling] Error:', error || result.error);
                return;
            }

            console.log('[Navigate Prev Sibling] Successfully navigated to previous sibling:', result.siblingTag);

            // Apply persistent outline to visually show the navigated element
            addPersistentOutline();
        }
    );
}
