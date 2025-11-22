/**
 * Manage Panel Component
 * Inline expansion panel for restoring removed Quick Actions
 */

import { getActionById } from '../../utils/quick-actions-config.js';
import { ActionTile } from './action-tile.js';

export class ManagePanel {
    constructor(panelElement, onRestoreCallback) {
        this.panel = panelElement;
        this.content = document.getElementById('manageContent');
        this.manageBtn = document.getElementById('manageActionsBtn');
        this.closeBtn = this.panel.querySelector('.manage-close');
        this.actionsGrid = document.getElementById('actionsGrid');
        this.onRestore = onRestoreCallback;
        this.isOpen = false;
    }

    /**
     * Initialize manage panel
     */
    init() {
        this.setupEventListeners();
    }

    /**
     * Setup event listeners
     */
    setupEventListeners() {
        // Toggle panel on manage button click
        this.manageBtn.addEventListener('click', () => {
            this.toggle();
        });

        // Close on close button click
        if (this.closeBtn) {
            this.closeBtn.addEventListener('click', () => {
                this.close();
            });
        }

        // Close on Escape key (use capture phase to prevent DevTools console from opening)
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.isOpen) {
                e.preventDefault();
                e.stopPropagation();
                this.close();
            }
        }, true);
    }

    /**
     * Toggle panel open/close
     */
    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    /**
     * Open panel
     */
    open() {
        this.panel.style.display = 'block';
        this.isOpen = true;
        this.manageBtn.classList.add('active');
        // Show close buttons on tiles
        this.actionsGrid.classList.add('manage-active');
    }

    /**
     * Close panel
     */
    close() {
        this.panel.style.display = 'none';
        this.isOpen = false;
        this.manageBtn.classList.remove('active');
        // Hide close buttons on tiles
        this.actionsGrid.classList.remove('manage-active');
    }

    /**
     * Update panel content with removed actions
     * @param {Array<string>} removedActionIds - Array of removed action IDs
     */
    update(removedActionIds) {
        if (removedActionIds.length === 0) {
            this.content.innerHTML = '<p class="placeholder">No removed actions.</p>';
            return;
        }

        // Clear content
        this.content.innerHTML = '';

        // Render removed action tiles
        removedActionIds.forEach(actionId => {
            const action = getActionById(actionId);
            if (action) {
                const tile = this.createRemovedTile(action);
                this.content.appendChild(tile);
            }
        });
    }

    /**
     * Create a removed action tile
     * @param {Object} action - Action definition
     * @returns {HTMLElement} Removed tile element
     */
    createRemovedTile(action) {
        const tile = ActionTile.createRemovedTile(action, (actionId, element) => {
            this.restoreAction(actionId, element);
        });
        return tile;
    }

    /**
     * Restore an action (with animation)
     * @param {string} actionId - Action ID to restore
     * @param {HTMLElement} element - Tile element (for animation)
     */
    restoreAction(actionId, element) {
        // Add fade out animation
        element.classList.add('fade-out-scale');

        // Wait for animation to complete, then restore
        setTimeout(() => {
            if (this.onRestore) {
                this.onRestore(actionId);
            }
        }, 300);
    }

    /**
     * Show panel (if it has content)
     */
    show() {
        if (this.content.children.length > 0) {
            this.open();
        }
    }

    /**
     * Hide panel
     */
    hide() {
        this.close();
    }
}
