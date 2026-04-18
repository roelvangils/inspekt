/**
 * Unhide All Elements Handler
 *
 * Restores all hidden elements for the current domain.
 * Removes all hidden element records from the database and shows them in the page.
 * Keyboard shortcut: B (bring back)
 */

import { evalInPage } from '../utils/devtools.js';

const API_BASE_URL = 'http://localhost:8000';

export async function handleUnhideAll(context) {
    console.log('[Unhide All] Executing unhide all elements action');

    // Get current URL to extract domain
    chrome.devtools.inspectedWindow.eval(
        'window.location.hostname',
        async (domain, error) => {
            if (error || !domain) {
                console.error('[Unhide All] Failed to get domain:', error);
                alert('Failed to get current domain');
                return;
            }

            console.log('[Unhide All] Domain:', domain);

            // Show loading state on tile
            const tile = document.querySelector(`[data-action-id="unhideAll"]`);
            if (tile) {
                tile.classList.add('processing');
                const label = tile.querySelector('.btn-label');
                const originalLabel = label ? label.textContent : null;
                if (label) {
                    label.textContent = 'Restoring…';
                }

                const restoreTileState = () => {
                    tile.classList.remove('processing');
                    if (label && originalLabel) {
                        label.textContent = originalLabel;
                    }
                };

                try {
                    // First, get the list of hidden elements so we can restore them
                    const getResponse = await fetch(
                        `${API_BASE_URL}/api/persistence/hidden?domain=${encodeURIComponent(domain)}`
                    );

                    if (!getResponse.ok) {
                        const errorData = await getResponse.json().catch(() => ({}));
                        throw new Error(errorData.detail || `HTTP ${getResponse.status}`);
                    }

                    const hiddenData = await getResponse.json();
                    const hiddenElements = hiddenData.elements || [];

                    if (hiddenElements.length === 0) {
                        console.log('[Unhide All] No hidden elements found for this domain');
                        if (label) {
                            label.textContent = 'Nothing to restore';
                        }
                        setTimeout(() => {
                            restoreTileState();
                        }, 1500);
                        return;
                    }

                    console.log(`[Unhide All] Found ${hiddenElements.length} hidden elements`);

                    // Delete all hidden elements from database
                    const deleteResponse = await fetch(
                        `${API_BASE_URL}/api/persistence/hidden/all?domain=${encodeURIComponent(domain)}`,
                        { method: 'DELETE' }
                    );

                    if (!deleteResponse.ok) {
                        const errorData = await deleteResponse.json().catch(() => ({}));
                        throw new Error(errorData.detail || `HTTP ${deleteResponse.status}`);
                    }

                    const result = await deleteResponse.json();
                    console.log('[Unhide All] Removed from database:', result);

                    // Restore elements in the page
                    const selectors = hiddenElements.map(el => el.selector);
                    evalInPage(
                        `(function() {
                            const selectors = ${JSON.stringify(selectors)};
                            let restoredCount = 0;

                            selectors.forEach(selector => {
                                try {
                                    const element = document.querySelector(selector);
                                    if (element && element.style.display === 'none') {
                                        element.style.display = '';
                                        restoredCount++;
                                    }
                                } catch (error) {
                                    console.warn('Failed to restore element:', selector, error);
                                }
                            });

                            return { ok: true, restoredCount: restoredCount };
                        })()`,
                        (evalResult, evalError) => {
                            if (evalError || !evalResult.ok) {
                                console.error('[Unhide All] Failed to restore in page:', evalError || evalResult.error);
                            } else {
                                console.log(`[Unhide All] Restored ${evalResult.restoredCount} elements in page`);
                            }
                        }
                    );

                    // Show success feedback
                    if (label) {
                        label.textContent = `Restored ${result.count}!`;
                    }
                    setTimeout(() => {
                        restoreTileState();
                    }, 1500);

                } catch (error) {
                    console.error('[Unhide All] Failed:', error);

                    // Show error feedback
                    if (label) {
                        label.textContent = 'Failed';
                    }
                    setTimeout(() => {
                        restoreTileState();
                    }, 1500);

                    alert(`Failed to unhide elements: ${error.message}\n\nMake sure the Inspekt API server is running.`);
                }
            } else {
                // No tile found, proceed without visual feedback
                try {
                    // Get hidden elements
                    const getResponse = await fetch(
                        `${API_BASE_URL}/api/persistence/hidden?domain=${encodeURIComponent(domain)}`
                    );

                    if (!getResponse.ok) {
                        throw new Error(`HTTP ${getResponse.status}`);
                    }

                    const hiddenData = await getResponse.json();
                    const hiddenElements = hiddenData.elements || [];

                    if (hiddenElements.length === 0) {
                        console.log('[Unhide All] No hidden elements found');
                        return;
                    }

                    // Delete from database
                    await fetch(
                        `${API_BASE_URL}/api/persistence/hidden/all?domain=${encodeURIComponent(domain)}`,
                        { method: 'DELETE' }
                    );

                    // Restore in page
                    const selectors = hiddenElements.map(el => el.selector);
                    evalInPage(
                        `(function() {
                            const selectors = ${JSON.stringify(selectors)};
                            selectors.forEach(selector => {
                                try {
                                    const element = document.querySelector(selector);
                                    if (element) {
                                        element.style.display = '';
                                    }
                                } catch (error) {
                                    console.warn('Failed to restore element:', selector, error);
                                }
                            });
                            return { ok: true };
                        })()`,
                        () => {}
                    );

                    console.log('[Unhide All] All elements restored successfully');

                } catch (error) {
                    console.error('[Unhide All] Failed:', error);
                    alert(`Failed to unhide elements: ${error.message}`);
                }
            }
        }
    );
}
