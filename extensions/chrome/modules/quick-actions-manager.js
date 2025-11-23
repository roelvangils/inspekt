/**
 * Quick Actions Manager
 * Main orchestrator for configurable Quick Actions feature
 */

import { DEFAULT_ACTIONS, DEFAULT_CONFIG, getActionById, getActionsInOrder } from '../utils/quick-actions-config.js';
import { ActionTile } from '../components/quick-actions/action-tile.js';
import { DragHandler } from '../components/quick-actions/drag-handler.js';
import { KeyboardHandler } from '../components/quick-actions/keyboard-handler.js';
import { ManagePanel } from '../components/quick-actions/manage-panel.js';
import { copyToClipboard } from '../utils/clipboard.js';

// Import modular handlers
import { handlePickElement } from '../handlers/pick-element.js';
import { handleCopyInspectedCommand } from '../handlers/copy-inspected-command.js';
import { handleCopySelector } from '../handlers/copy-selector.js';
import { handleCopyClickCommand } from '../handlers/copy-click-command.js';
import { handleShowInElements } from '../handlers/show-in-elements.js';
import { handleHighlightElement } from '../handlers/highlight-element.js';
import { handleTakeNodeScreenshot } from '../handlers/screenshot.js';
import { handleNavigateParent } from '../handlers/navigate-parent.js';
import { handleNavigateChild } from '../handlers/navigate-child.js';
import { handleNavigatePrevSibling } from '../handlers/navigate-prev-sibling.js';
import { handleNavigateNextSibling } from '../handlers/navigate-next-sibling.js';
import { handleHideElement } from '../handlers/hide-element.js';
import { handleUnhideAll } from '../handlers/unhide-all-elements.js';

export class QuickActionsManager {
    constructor(dependencies) {
        // Dependencies from panel.js
        this.elementDisplay = dependencies.elementDisplay;
        this.elementPicker = dependencies.elementPicker;
        this.elementHighlighter = dependencies.elementHighlighter;
        this.settingsManager = dependencies.settingsManager;

        // Configuration
        this.config = null;

        // DOM elements
        this.grid = document.getElementById('actionsGrid');
        this.panel = document.getElementById('managePanel');

        // Sub-components
        this.dragHandler = null;
        this.keyboardHandler = null;
        this.managePanel = null;
    }

    /**
     * Initialize manager
     */
    async init() {
        console.log('[Quick Actions] Initializing manager...');
        console.log('[Quick Actions] Dependencies:', {
            elementDisplay: this.elementDisplay,
            elementPicker: this.elementPicker,
            elementHighlighter: this.elementHighlighter,
            settingsManager: this.settingsManager
        });

        await this.loadConfig();
        console.log('[Quick Actions] Config loaded:', this.config);

        this.initializeComponents();
        console.log('[Quick Actions] Components initialized');

        this.render();
        console.log('[Quick Actions] Rendered');

        this.setupElementMonitoring();

        console.log('[Quick Actions] Manager initialized successfully');
    }

    /**
     * Load configuration from chrome.storage.local
     */
    async loadConfig() {
        return new Promise((resolve) => {
            chrome.storage.local.get(['quickActionsConfig'], (result) => {
                if (result.quickActionsConfig) {
                    const savedConfig = result.quickActionsConfig;
                    console.log('[Quick Actions] Found saved config:', savedConfig);

                    // Check if saved config has all required fields and actions
                    const hasValidOrder = savedConfig.order && savedConfig.order.length === DEFAULT_CONFIG.order.length;

                    if (hasValidOrder) {
                        // Use saved config
                        this.config = savedConfig;
                        console.log('[Quick Actions] Using saved config');
                    } else {
                        // Saved config is incomplete, reset to defaults
                        this.config = { ...DEFAULT_CONFIG };
                        console.log('[Quick Actions] Saved config incomplete, resetting to defaults');
                        console.log('[Quick Actions] Default order:', DEFAULT_CONFIG.order);
                        // Save the corrected config
                        this.saveConfig();
                    }
                } else {
                    // Use default config
                    this.config = { ...DEFAULT_CONFIG };
                    console.log('[Quick Actions] No saved config, using defaults');
                    console.log('[Quick Actions] Default order:', DEFAULT_CONFIG.order);
                }
                resolve();
            });
        });
    }

    /**
     * Save configuration to chrome.storage.local
     */
    saveConfig() {
        chrome.storage.local.set({ quickActionsConfig: this.config }, () => {
            console.log('[Quick Actions] Configuration saved', this.config);
        });
    }

    /**
     * Initialize sub-components
     */
    initializeComponents() {
        // Drag handler
        this.dragHandler = new DragHandler(
            this.grid,
            this.handleReorder.bind(this)
        );
        this.dragHandler.init();

        // Keyboard handler
        this.keyboardHandler = new KeyboardHandler(
            this.config.shortcuts,
            this.executeAction.bind(this)
        );
        this.keyboardHandler.init();

        // Manage panel
        this.managePanel = new ManagePanel(
            this.panel,
            this.handleRestore.bind(this)
        );
        this.managePanel.init();
    }

    /**
     * Render all action tiles
     */
    render() {
        console.log('[Quick Actions] Rendering tiles...');
        console.log('[Quick Actions] Grid element:', this.grid);

        // Clear grid
        this.grid.innerHTML = '';

        // Get active actions (not removed) in configured order
        const activeActionIds = this.config.order.filter(
            id => !this.config.removed.includes(id)
        );
        console.log('[Quick Actions] Active action IDs:', activeActionIds);

        const activeActions = getActionsInOrder(activeActionIds);
        console.log('[Quick Actions] Active actions:', activeActions);

        // Render each action tile
        activeActions.forEach(action => {
            const tile = this.createActionTile(action);
            this.grid.appendChild(tile);
        });

        console.log('[Quick Actions] Tiles appended to grid:', this.grid.children.length);

        // Update manage panel with removed actions
        this.managePanel.update(this.config.removed);

        // Update element-dependent states
        this.updateElementStates();
    }

    /**
     * Create an action tile
     * @param {Object} action - Action definition
     * @returns {HTMLElement} Tile element
     */
    createActionTile(action) {
        const currentElement = this.elementDisplay.getCurrentElement();
        // Explicitly check - if requiresElement is not set, default to false
        const isDisabled = (action.requiresElement === true) && !currentElement;

        console.log('[Quick Actions] Creating tile for:', action.id, 'RequiresElement:', action.requiresElement, 'Disabled:', isDisabled);

        const tile = new ActionTile(action, {
            shortcut: this.config.shortcuts[action.id],
            onRemove: this.handleRemove.bind(this),
            onClick: this.executeAction.bind(this),
            isDisabled: isDisabled
        });

        return tile.render();
    }

    /**
     * Execute an action
     * @param {string} actionId - Action ID
     */
    executeAction(actionId) {
        console.log('[Quick Actions] executeAction called with:', actionId);

        const action = getActionById(actionId);
        if (!action) {
            console.error('[Quick Actions] Unknown action:', actionId);
            return;
        }

        console.log('[Quick Actions] Action found:', action.label, 'Handler:', action.handler);

        // Check if element required and available
        const currentElement = this.elementDisplay.getCurrentElement();
        if (action.requiresElement && !currentElement) {
            console.log('[Quick Actions] Action requires element:', actionId);
            return;
        }

        // Execute handler
        const handler = this.handlers[action.handler];
        if (handler) {
            console.log('[Quick Actions] Executing handler:', action.handler);

            // Create context object with all dependencies and utilities
            const context = {
                elementDisplay: this.elementDisplay,
                elementPicker: this.elementPicker,
                elementHighlighter: this.elementHighlighter,
                settingsManager: this.settingsManager,
                copyToClipboard: copyToClipboard
            };

            // Call handler with context
            handler(context);
        } else {
            console.error('[Quick Actions] No handler for:', action.handler);
        }
    }

    /**
     * Action handlers registry
     * Maps handler names to imported handler functions
     */
    handlers = {
        activatePicker: handlePickElement,
        copyInspectedCommand: handleCopyInspectedCommand,
        copySelectorToClipboard: handleCopySelector,
        copyClickCommand: handleCopyClickCommand,
        showInElementsPanel: handleShowInElements,
        highlightElement: handleHighlightElement,
        takeNodeScreenshot: handleTakeNodeScreenshot,
        navigateToParent: handleNavigateParent,
        navigateToChild: handleNavigateChild,
        navigateToPrevSibling: handleNavigatePrevSibling,
        navigateToNextSibling: handleNavigateNextSibling,
        hideElement: handleHideElement,
        unhideAll: handleUnhideAll
    };

    /**
     * Handle tile reorder (from drag-drop)
     * @param {Array<string>} newOrder - New order of action IDs
     */
    handleReorder(newOrder) {
        // Update config
        this.config.order = newOrder;

        // Save to storage
        this.saveConfig();

        console.log('[Quick Actions] Order updated:', newOrder);
    }

    /**
     * Handle tile removal
     * @param {string} actionId - Action ID to remove
     * @param {HTMLElement} tile - Tile element (for animation)
     */
    handleRemove(actionId, tile) {
        // Add fade animation
        tile.classList.add('fade-out-scale');

        // Wait for animation, then update state
        setTimeout(() => {
            // Add to removed list
            this.config.removed.push(actionId);

            // Save config
            this.saveConfig();

            // Re-render
            this.render();

            console.log('[Quick Actions] Action removed:', actionId);
        }, 300);
    }

    /**
     * Handle tile restore
     * @param {string} actionId - Action ID to restore
     */
    handleRestore(actionId) {
        // Remove from removed list
        this.config.removed = this.config.removed.filter(id => id !== actionId);

        // Save config
        this.saveConfig();

        // Re-render
        this.render();

        console.log('[Quick Actions] Action restored:', actionId);
    }

    /**
     * Setup element monitoring to update action states
     */
    setupElementMonitoring() {
        // Listen for element changes
        // The ElementMonitor will dispatch events or we can poll
        // For now, we'll create a polling mechanism
        setInterval(() => {
            this.updateElementStates();
        }, 500);
    }

    /**
     * Update element-dependent action states
     */
    updateElementStates() {
        const currentElement = this.elementDisplay.getCurrentElement();
        const hasElement = currentElement !== null;

        // Update all tiles that require an element
        DEFAULT_ACTIONS.forEach(action => {
            if (action.requiresElement) {
                const tile = this.grid.querySelector(`[data-action-id="${action.id}"]`);
                if (tile) {
                    tile.disabled = !hasElement;
                }
            }
        });
    }

    /**
     * Get current configuration
     * @returns {Object} Current config
     */
    getConfig() {
        return this.config;
    }

    /**
     * Reset to default configuration
     */
    resetToDefaults() {
        this.config = { ...DEFAULT_CONFIG };
        this.saveConfig();
        this.render();
        this.keyboardHandler.updateShortcuts(this.config.shortcuts);
        console.log('[Quick Actions] Reset to defaults');
    }
}
