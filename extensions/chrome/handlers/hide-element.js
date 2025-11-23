/**
 * Hide Element Handler
 *
 * Hides the currently selected element and persists the preference to the database.
 * The element will be automatically hidden on future page loads.
 * Keyboard shortcut: V (visibility off)
 */

import { evalInPage } from '../utils/devtools.js';

const API_BASE_URL = 'http://localhost:8000';

export async function handleHideElement(context) {
    console.log('[Hide Element] Executing hide element action');

    const currentElement = context.elementDisplay.getCurrentElement();

    if (!currentElement) {
        console.warn('[Hide Element] No element selected');
        return;
    }

    if (!currentElement.selector) {
        console.error('[Hide Element] Element has no selector');
        return;
    }

    // Get current URL to extract domain
    chrome.devtools.inspectedWindow.eval(
        'window.location.hostname',
        async (domain, error) => {
            if (error || !domain) {
                console.error('[Hide Element] Failed to get domain:', error);
                alert('Failed to get current domain');
                return;
            }

            console.log('[Hide Element] Domain:', domain);
            console.log('[Hide Element] Selector:', currentElement.selector);

            // Show loading state on tile
            const tile = document.querySelector(`[data-action-id="hideElement"]`);
            if (tile) {
                tile.classList.add('processing');
                const label = tile.querySelector('.btn-label');
                const originalLabel = label ? label.textContent : null;
                if (label) {
                    label.textContent = 'Hiding...';
                }

                const restoreTileState = () => {
                    tile.classList.remove('processing');
                    if (label && originalLabel) {
                        label.textContent = originalLabel;
                    }
                };

                try {
                    // Save to persistence API
                    const response = await fetch(`${API_BASE_URL}/api/persistence/hidden`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            domain: domain,
                            selector: currentElement.selector,
                            reason: `Hidden via DevTools at ${new Date().toLocaleString()}`
                        })
                    });

                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({}));
                        throw new Error(errorData.detail || `HTTP ${response.status}`);
                    }

                    const result = await response.json();
                    console.log('[Hide Element] Saved to database:', result);

                    // Apply hiding immediately in the page
                    evalInPage(
                        `(function() {
                            const selector = ${JSON.stringify(currentElement.selector)};
                            const element = document.querySelector(selector);

                            if (!element) {
                                return { ok: false, error: 'Element not found in page' };
                            }

                            // Hide the element
                            element.style.display = 'none';

                            return { ok: true };
                        })()`,
                        (evalResult, evalError) => {
                            if (evalError || !evalResult.ok) {
                                console.error('[Hide Element] Failed to hide in page:', evalError || evalResult.error);
                            } else {
                                console.log('[Hide Element] Successfully hidden in page');
                            }
                        }
                    );

                    // Show success feedback
                    if (label) {
                        label.textContent = 'Hidden!';
                    }
                    setTimeout(() => {
                        restoreTileState();
                    }, 1500);

                } catch (error) {
                    console.error('[Hide Element] Failed to save to database:', error);

                    // Show error feedback
                    if (label) {
                        label.textContent = 'Failed';
                    }
                    setTimeout(() => {
                        restoreTileState();
                    }, 1500);

                    alert(`Failed to hide element: ${error.message}\n\nMake sure the Inspekt API server is running.`);
                }
            } else {
                // No tile found, proceed without visual feedback
                try {
                    const response = await fetch(`${API_BASE_URL}/api/persistence/hidden`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            domain: domain,
                            selector: currentElement.selector,
                            reason: `Hidden via DevTools at ${new Date().toLocaleString()}`
                        })
                    });

                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({}));
                        throw new Error(errorData.detail || `HTTP ${response.status}`);
                    }

                    // Apply hiding immediately in the page
                    evalInPage(
                        `(function() {
                            const selector = ${JSON.stringify(currentElement.selector)};
                            const element = document.querySelector(selector);

                            if (element) {
                                element.style.display = 'none';
                            }

                            return { ok: true };
                        })()`,
                        () => {}
                    );

                    console.log('[Hide Element] Element hidden successfully');

                } catch (error) {
                    console.error('[Hide Element] Failed:', error);
                    alert(`Failed to hide element: ${error.message}`);
                }
            }
        }
    );
}
