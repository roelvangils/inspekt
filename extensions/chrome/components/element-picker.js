/**
 * Element Picker Component
 * Activates element picker tool for selecting elements on page
 */

import { evalInPage } from '../utils/devtools.js';
import { addPersistentOutline as addOutline, removePersistentOutline as removeOutline } from '../utils/element-outline.js';

export class ElementPicker {
    constructor() {
        this.hasOutline = false;  // Track if outline is currently visible
        this.isActive = false;     // Track if picker is currently active
        this.pollInterval = null;  // Store interval ID
        this.selectedElementTag = null; // Store selected element tag for display

        // Expose cleanup method globally for debugging
        window.__inspektPickerCleanup = () => this.cleanup();
    }

    /**
     * Initialize picker
     */
    init() {
        // Event listener setup is handled by quick-actions or panel.js
        console.log('[Element Picker] Initialized - use window.__inspektPickerCleanup() to force reset if stuck');
    }

    /**
     * Update tile text to show selected element
     * @param {string} tag - Element tag name (e.g., 'p', 'div')
     */
    updateTileText(tag) {
        const btnPickElement = document.querySelector('[data-action-id="pickElement"]');
        if (!btnPickElement) return;

        const labelSpan = btnPickElement.querySelector('.btn-label');
        const hintSpan = btnPickElement.querySelector('.btn-hint');

        if (tag) {
            // Show selected element with styled tag
            labelSpan.innerHTML = `<code style="background: light-dark(rgba(0, 102, 255, 0.1), rgba(0, 102, 255, 0.2)); padding: 2px 6px; border-radius: 3px; font-family: monospace; font-size: 12px; color: light-dark(#0066ff, #66b3ff);">&lt;${tag}&gt;</code> is currently selected`;
            hintSpan.textContent = 'Click again to unselect';

            // Add a visual indicator that this tile is in "selected" state
            btnPickElement.classList.add('element-selected');
        } else {
            // Restore original text
            labelSpan.textContent = 'Pick Element';
            hintSpan.textContent = 'Select element on page';

            // Remove selected state
            btnPickElement.classList.remove('element-selected');
        }
    }

    /**
     * Activate element picker on page
     */
    activate() {
        console.log('[Element Picker] Activate called, hasOutline:', this.hasOutline, 'isActive:', this.isActive);

        // If outline is visible, toggle it off instead of activating picker
        if (this.hasOutline && !this.isActive) {
            console.log('[Element Picker] Removing outline (toggle off)');
            this.removeOutline();
            return;
        }

        // Remove any existing outline before new pick
        if (this.hasOutline) {
            this.removeOutline();
        }

        // Restore tile text for new pick
        this.updateTileText(null);

        console.log('[Element Picker] Starting picker...');

        fetch(chrome.runtime.getURL('element_picker.js'))
            .then(response => response.text())
            .then(pickerScript => {
                console.log('[Element Picker] Picker script loaded, injecting...');

                evalInPage(
                    pickerScript,
                    (result, error) => {
                        if (error) {
                            console.error('[Inspekt Panel] Error activating picker:', error);
                            return;
                        }

                        if (result && result.error) {
                            console.log('[Inspekt Panel]', result.error);
                            return;
                        }

                        console.log('[Element Picker] Picker activated successfully');

                        // Update tile state - dim and mark as picking
                        this.isActive = true;
                        this.updateTileState('picking');

                        // Start polling for picker completion
                        this.pollForCompletion();
                    }
                );
            })
            .catch(error => {
                console.error('[Inspekt Panel] Error loading picker script:', error);
            });
    }

    /**
     * Update tile visual state
     * @param {string} state - 'picking', 'picked', or 'normal'
     */
    updateTileState(state) {
        // Always query fresh (tiles are dynamically rendered)
        const btnPickElement = document.querySelector('[data-action-id="pickElement"]');

        if (!btnPickElement) {
            console.warn('[Element Picker] Pick Element tile not found');
            return;
        }

        // Remove all state classes
        btnPickElement.classList.remove('picking', 'picked');

        if (state === 'picking') {
            btnPickElement.classList.add('picking');
        } else if (state === 'picked') {
            btnPickElement.classList.add('picked');
        }
    }

    /**
     * Poll for picker completion
     */
    pollForCompletion() {
        const startTime = Date.now();
        const timeout = 60000; // 60 second timeout

        const pollInterval = setInterval(() => {
            // Check for timeout
            if (Date.now() - startTime > timeout) {
                console.warn('[Element Picker] Picker timeout, forcing cleanup');
                clearInterval(pollInterval);
                this.cleanup();
                return;
            }

            evalInPage(
                'window.__INSPEKT_PICKER_ACTIVE__',
                (isActive, error) => {
                    if (error) {
                        console.error('[Element Picker] Error checking picker status:', error);
                        return;
                    }

                    console.log('[Element Picker] Polling - isActive:', isActive);

                    // If picker is no longer active, it was completed or cancelled
                    if (!isActive) {
                        clearInterval(pollInterval);

                        // Restore tile state
                        this.isActive = false;
                        this.updateTileState('normal');

                        // Add persistent outline to selected element
                        this.addPersistentOutline();

                        console.log('[Element Picker] Picker completed successfully');
                    }
                }
            );
        }, 500);

        // Store interval ID so we can clear it if needed
        this.pollInterval = pollInterval;
    }

    /**
     * Cleanup and reset picker state
     */
    cleanup() {
        this.isActive = false;
        this.updateTileState('normal');

        // Clear polling interval if it exists
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }

        // Restore tile text if needed (in case of stuck picker)
        if (!this.hasOutline) {
            this.updateTileText(null);
        }

        // Force cleanup on the page
        evalInPage(
            `(function() {
                window.__INSPEKT_PICKER_ACTIVE__ = false;
                // Remove any picker overlays
                const overlay = document.querySelector('[style*="z-index: 2147483646"]');
                if (overlay) overlay.remove();
            })()`,
            () => console.log('[Element Picker] Force cleanup complete')
        );
    }

    /**
     * Add persistent outline to selected element
     */
    addPersistentOutline() {
        // Use shared utility with solid border and background
        addOutline('2px solid #0066ff', 'rgba(0, 102, 255, 0.1)', (result, error) => {
            if (result && result.success) {
                this.hasOutline = true;
                this.selectedElementTag = result.tag;

                // Update tile text to show selected element
                this.updateTileText(result.tag);

                console.log('[Inspekt Panel] Persistent outline added for <' + result.tag + '>');
            }
        });
    }

    /**
     * Remove persistent outline
     */
    removeOutline() {
        // Use shared utility to remove outline
        removeOutline((result, error) => {
            if (result && result.success) {
                this.hasOutline = false;
                this.selectedElementTag = null;

                // Restore tile text to original
                this.updateTileText(null);

                console.log('[Inspekt Panel] Outline removed');
            }
        });
    }
}
