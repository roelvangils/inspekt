/**
 * Inspekt DevTools Panel - Modular Entry Point
 *
 * This panel provides a comprehensive UI for interacting with Inspekt from DevTools.
 * Architecture: ES6 modules for maintainability and extensibility.
 */

// Import managers
import { ConnectionManager } from './modules/connection-manager.js';
import { SettingsManager } from './modules/settings-manager.js';
import { ThemeManager } from './modules/theme-manager.js';
import { ElementMonitor } from './modules/element-monitor.js';
import { ElementDisplay } from './modules/element-display.js';
import { HistoryManager } from './modules/history-manager.js';
import { QuickActionsManager } from './modules/quick-actions-manager.js';

// Import components
import { ElementHighlighter } from './components/element-highlighter.js';
import { ElementPicker } from './components/element-picker.js';

// Manager instances
let connectionManager;
let settingsManager;
let themeManager;
let elementMonitor;
let elementDisplay;
let historyManager;
let quickActionsManager;
let elementHighlighter;
let elementPicker;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('[Inspekt Panel] DOMContentLoaded - Starting initialization…');

    try {
        initializeManagers();
        console.log('[Inspekt Panel] Initialized (Modular Architecture with Configurable Quick Actions)');
    } catch (error) {
        console.error('[Inspekt Panel] Initialization error:', error);
    }
});

/**
 * Initialize all managers and components
 */
function initializeManagers() {
    console.log('[Panel] Initializing managers…');

    // Core managers
    console.log('[Panel] Creating core managers…');
    connectionManager = new ConnectionManager();
    settingsManager = new SettingsManager();
    themeManager = new ThemeManager();

    // Element handling
    console.log('[Panel] Creating element handlers…');
    elementDisplay = new ElementDisplay(); // elementHighlighter assigned below
    historyManager = new HistoryManager();
    elementMonitor = new ElementMonitor();

    // Components
    console.log('[Panel] Creating components…');
    elementHighlighter = new ElementHighlighter(elementDisplay);
    elementPicker = new ElementPicker();

    // Complete circular dependency: ElementDisplay needs ElementHighlighter
    elementDisplay.elementHighlighter = elementHighlighter;

    // Initialize all managers (non-async)
    console.log('[Panel] Initializing managers…');
    connectionManager.init();
    settingsManager.init();
    themeManager.init();
    elementHighlighter.init();
    elementPicker.init();

    // Quick Actions Manager (async init)
    console.log('[Panel] Creating QuickActionsManager…');
    quickActionsManager = new QuickActionsManager({
        elementDisplay,
        elementPicker,
        elementHighlighter,
        settingsManager
    });
    console.log('[Panel] QuickActionsManager created, calling init…');
    quickActionsManager.init();

    // Start element monitoring
    console.log('[Panel] Starting element monitoring…');
    elementMonitor.init();

    // Listen for element changes
    elementMonitor.onElementChange((element) => {
        // Update display
        elementDisplay.update(element);

        // Add to history if tracking is enabled
        if (settingsManager.getSettings().trackHistory) {
            historyManager.add(element);
        }

        // Update pick element button state
        updatePickElementButtonState(element);
    });

    // Setup pick element button
    setupPickElementButton();

    console.log('[Panel] All managers initialized');
}

/**
 * Setup the permanent Pick Element button in Quick Actions heading
 */
function setupPickElementButton() {
    const pickElementBtn = document.getElementById('pickElementBtn');
    if (!pickElementBtn) {
        console.error('[Panel] Pick Element button not found');
        return;
    }

    // Add click handler
    pickElementBtn.addEventListener('click', () => {
        console.log('[Panel] Pick Element button clicked');
        elementPicker.activate();
    });

    // Initialize state
    const currentElement = elementDisplay.getCurrentElement();
    updatePickElementButtonState(currentElement);

    console.log('[Panel] Pick Element button initialized');
}

/**
 * Update pick element button dimmed state based on element selection
 * @param {Object|null} element - Current element or null
 */
function updatePickElementButtonState(element) {
    const pickElementBtn = document.getElementById('pickElementBtn');
    if (!pickElementBtn) return;

    if (element) {
        // Element is selected - dim the button
        pickElementBtn.classList.add('dimmed');
    } else {
        // No element selected - normal state
        pickElementBtn.classList.remove('dimmed');
    }
}
