/**
 * Engine Tracker - Prevents re-injection of accessibility engines
 *
 * Provides global tracking for loaded engines and UI elements to:
 * 1. Prevent re-injecting engine libraries on repeated audits
 * 2. Track Inspekt UI elements for exclusion from scans
 * 3. Provide a reset function to clean up all state
 */

(function() {
  'use strict';

  // Initialize tracking Set if not already present
  if (!window.__inspektLoadedEngines__) {
    window.__inspektLoadedEngines__ = new Set();
  }

  // Selectors for Inspekt UI elements that should be excluded from scans
  window.__inspektUISelectors__ = [
    '[data-inspekt-badge]',
    '[data-inspekt-axe-popover]',
    '[data-inspekt-ibm-popover]',
    '.inspekt-axe-popover',
    '.inspekt-ibm-popover',
    '#inspekt-badge-styles',
    '#inspekt-axe-popover-styles',
    '#inspekt-axe-popover-additional-styles',
    '#inspekt-ibm-popover-styles',
    '#inspekt-ibm-badge-styles'
  ];

  /**
   * Mark an engine as loaded to prevent re-injection
   * @param {string} engine - Engine name (axe, ibm, htmlcs, sia)
   */
  window.__inspektMarkEngineLoaded__ = function(engine) {
    window.__inspektLoadedEngines__.add(engine);
  };

  /**
   * Check if an engine is already loaded
   * @param {string} engine - Engine name to check
   * @returns {boolean} True if engine is already loaded
   */
  window.__inspektIsEngineLoaded__ = function(engine) {
    return window.__inspektLoadedEngines__.has(engine);
  };

  /**
   * Get list of all loaded engines
   * @returns {string[]} Array of loaded engine names
   */
  window.__inspektGetLoadedEngines__ = function() {
    return Array.from(window.__inspektLoadedEngines__);
  };

  /**
   * Reset all accessibility audit state and remove UI elements
   * @returns {object} Result object with ok status and message
   */
  window.__inspektResetAll__ = function() {
    try {
      // Remove all badges and popovers
      window.__inspektUISelectors__.forEach(function(sel) {
        document.querySelectorAll(sel).forEach(function(el) {
          el.remove();
        });
      });

      // Clear engine tracking
      window.__inspektLoadedEngines__.clear();

      // Clear axe-specific state
      if (window.__inspektSeenViolations__) {
        window.__inspektSeenViolations__.clear();
      }
      if (window.__inspektLastBadgeNumber__ !== undefined) {
        window.__inspektLastBadgeNumber__ = 0;
      }
      if (window.__inspektDirty__ !== undefined) {
        window.__inspektDirty__ = false;
      }
      if (window.__inspektPersistentListenersInstalled__) {
        window.__inspektPersistentListenersInstalled__ = false;
      }

      // Clear IBM-specific state
      if (window.__inspektIbmSeenIssues__) {
        window.__inspektIbmSeenIssues__.clear();
      }
      if (window.__inspektIbmLastBadgeNumber__ !== undefined) {
        window.__inspektIbmLastBadgeNumber__ = 0;
      }
      if (window.__inspektIbmDirty__ !== undefined) {
        window.__inspektIbmDirty__ = false;
      }
      if (window.__inspektIbmPersistentListenersInstalled__) {
        window.__inspektIbmPersistentListenersInstalled__ = false;
      }

      // Clear shared popover state
      if (window.__inspektPopoverCore__) {
        if (typeof window.__inspektPopoverCore__.reset === 'function') {
          window.__inspektPopoverCore__.reset();
        }
      }

      // Note: We don't unload the actual engine libraries (axe, ace, etc.)
      // as they are benign once loaded and expensive to re-load.
      // We just clear the tracking so a fresh audit can be run.

      return {
        ok: true,
        message: 'All Inspekt UI elements removed and state reset'
      };
    } catch (error) {
      return {
        ok: false,
        error: error.message
      };
    }
  };

  /**
   * Check if Inspekt tracker is initialized
   * @returns {boolean} Always true once this script has run
   */
  window.__inspektTrackerInitialized__ = true;

})();
