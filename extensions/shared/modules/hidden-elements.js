/**
 * Hidden Elements Module
 *
 * Manages persistent element hiding across page loads.
 * - Fetches hidden elements from persistence API
 * - Applies hiding on page load
 * - Monitors DOM for dynamically-added elements
 * - Provides utilities for hide/unhide operations
 */

// Log immediately to verify module loads
console.log('[Hidden Elements] Module script started');

const API_BASE_URL = 'http://localhost:8000';

class HiddenElementsManager {
    constructor() {
        this.hiddenSelectors = [];
        this.domain = window.location.hostname;
        this.observer = null;
        this.isInitialized = false;
    }

    /**
     * Initialize the hidden elements manager
     */
    async init() {
        if (this.isInitialized) {
            console.log('[Hidden Elements] Already initialized');
            return;
        }

        console.log(`[Hidden Elements] Initializing for domain: ${this.domain}`);

        try {
            // Fetch hidden elements from API
            await this.loadHiddenElements();

            // Apply hiding to existing elements
            this.applyHiding();

            // Start observing for dynamically-added elements
            this.startObserver();

            this.isInitialized = true;
            console.log('[Hidden Elements] Initialization complete');
        } catch (error) {
            console.error('[Hidden Elements] Initialization failed:', error);
        }
    }

    /**
     * Load hidden elements from persistence API
     */
    async loadHiddenElements() {
        try {
            const response = await fetch(
                `${API_BASE_URL}/api/persistence/hidden?domain=${encodeURIComponent(this.domain)}`
            );

            if (!response.ok) {
                // If API is not available, silently fail
                console.log('[Hidden Elements] API not available, skipping');
                return;
            }

            const data = await response.json();
            this.hiddenSelectors = data.elements.map(el => el.selector);

            console.log(`[Hidden Elements] Loaded ${this.hiddenSelectors.length} hidden selectors`);
        } catch (error) {
            // Network error - API server not running
            console.log('[Hidden Elements] Could not reach API server');
        }
    }

    /**
     * Apply hiding to all matching elements
     */
    applyHiding() {
        if (this.hiddenSelectors.length === 0) {
            return;
        }

        let hiddenCount = 0;

        this.hiddenSelectors.forEach(selector => {
            try {
                const elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    if (element.style.display !== 'none') {
                        element.style.display = 'none';
                        hiddenCount++;
                    }
                });
            } catch (error) {
                console.warn('[Hidden Elements] Invalid selector:', selector, error);
            }
        });

        if (hiddenCount > 0) {
            console.log(`[Hidden Elements] Applied hiding to ${hiddenCount} elements`);
        }
    }

    /**
     * Start MutationObserver to handle dynamically-added elements
     */
    startObserver() {
        if (this.hiddenSelectors.length === 0) {
            console.log('[Hidden Elements] No hidden selectors, skipping observer');
            return;
        }

        this.observer = new MutationObserver((mutations) => {
            // Check if any added nodes match hidden selectors
            let needsApply = false;

            for (const mutation of mutations) {
                if (mutation.addedNodes.length > 0) {
                    needsApply = true;
                    break;
                }
            }

            if (needsApply) {
                this.applyHiding();
            }
        });

        // Observe the entire document for added nodes
        this.observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        console.log('[Hidden Elements] MutationObserver started');
    }

    /**
     * Stop the MutationObserver
     */
    stopObserver() {
        if (this.observer) {
            this.observer.disconnect();
            this.observer = null;
            console.log('[Hidden Elements] MutationObserver stopped');
        }
    }

    /**
     * Reload hidden elements from API and reapply
     */
    async reload() {
        console.log('[Hidden Elements] Reloading...');
        await this.loadHiddenElements();
        this.applyHiding();
    }

    /**
     * Unhide all elements (restore display)
     */
    unhideAll() {
        if (this.hiddenSelectors.length === 0) {
            return;
        }

        let restoredCount = 0;

        this.hiddenSelectors.forEach(selector => {
            try {
                const elements = document.querySelectorAll(selector);
                elements.forEach(element => {
                    if (element.style.display === 'none') {
                        element.style.display = '';
                        restoredCount++;
                    }
                });
            } catch (error) {
                console.warn('[Hidden Elements] Invalid selector:', selector, error);
            }
        });

        // Clear the hidden selectors list
        this.hiddenSelectors = [];

        // Stop observer since there's nothing to hide
        this.stopObserver();

        console.log(`[Hidden Elements] Restored ${restoredCount} elements`);
    }

    /**
     * Check if a selector is currently hidden
     * @param {string} selector - CSS selector to check
     * @returns {boolean} True if hidden
     */
    isHidden(selector) {
        return this.hiddenSelectors.includes(selector);
    }
}

// Create singleton instance
const hiddenElementsManager = new HiddenElementsManager();

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        hiddenElementsManager.init();
    });
} else {
    // DOM already loaded
    hiddenElementsManager.init();
}

// Export for external use
window.__INSPEKT_HIDDEN_ELEMENTS__ = hiddenElementsManager;

console.log('[Hidden Elements] Module loaded');
