/**
 * Quick Actions Configuration
 * Defines default actions, shortcuts, and configuration structure
 */

/**
 * Default Quick Actions definitions
 * Each action has metadata for rendering and execution
 */
export const DEFAULT_ACTIONS = [
    {
        id: 'pickElement',
        icon: 'gps_fixed',
        label: 'Pick Element',
        hint: 'Select element on page',
        handler: 'activatePicker',
        shortcut: 'P'
        // Note: requiresElement is NOT set, so this is always enabled
    },
    {
        id: 'inspected',
        icon: 'search',
        label: 'inspekt inspected',
        hint: 'Show element details',
        handler: 'copyInspectedCommand',
        shortcut: 'I',
        requiresElement: true
    },
    {
        id: 'copySelector',
        icon: 'content_copy',
        label: 'Copy Selector',
        hint: 'Copy CSS selector',
        handler: 'copySelectorToClipboard',
        shortcut: 'C',
        requiresElement: true
    },
    {
        id: 'copyCommand',
        icon: 'code',
        label: 'Copy Click Command',
        hint: 'inspekt click "selector"',
        handler: 'copyClickCommand',
        shortcut: 'M',
        requiresElement: true
    },
    {
        id: 'showInElements',
        icon: 'push_pin',
        label: 'Show in Elements',
        hint: 'Switch to Elements tab',
        handler: 'showInElementsPanel',
        shortcut: 'E',
        requiresElement: true
    },
    {
        id: 'highlight',
        icon: 'auto_awesome',
        label: 'Highlight Element',
        hint: 'Flash element briefly',
        handler: 'highlightElement',
        shortcut: 'H',
        requiresElement: true
    },
    {
        id: 'takeNodeScreenshot',
        icon: 'camera_alt',
        label: 'Take Node Screenshot',
        hint: 'Capture and display element',
        handler: 'takeNodeScreenshot',
        shortcut: 'S',
        requiresElement: true
    },
    {
        id: 'navigateParent',
        icon: 'keyboard_arrow_up',
        label: 'Navigate to Parent',
        hint: 'Select parent element',
        handler: 'navigateToParent',
        shortcut: 'U',
        requiresElement: true
    },
    {
        id: 'navigateChild',
        icon: 'keyboard_arrow_down',
        label: 'Navigate to Child',
        hint: 'Select first child',
        handler: 'navigateToChild',
        shortcut: 'D',
        requiresElement: true
    },
    {
        id: 'navigatePrevSibling',
        icon: 'keyboard_arrow_left',
        label: 'Navigate to Prev Sibling',
        hint: 'Select previous sibling',
        handler: 'navigateToPrevSibling',
        shortcut: 'L',
        requiresElement: true
    },
    {
        id: 'navigateNextSibling',
        icon: 'keyboard_arrow_right',
        label: 'Navigate to Next Sibling',
        hint: 'Select next sibling',
        handler: 'navigateToNextSibling',
        shortcut: 'R',
        requiresElement: true
    }
];

/**
 * Default configuration structure
 * Stored in chrome.storage.local under key 'quickActionsConfig'
 */
export const DEFAULT_CONFIG = {
    version: 1,  // For future migrations
    order: DEFAULT_ACTIONS.map(a => a.id),
    removed: [],  // Array of removed action IDs
    shortcuts: Object.fromEntries(
        DEFAULT_ACTIONS.map(a => [a.id, a.shortcut])
    )
};

/**
 * Get action by ID
 * @param {string} actionId - Action ID
 * @returns {Object|null} Action definition or null
 */
export function getActionById(actionId) {
    return DEFAULT_ACTIONS.find(a => a.id === actionId) || null;
}

/**
 * Get actions in specified order
 * @param {Array<string>} order - Array of action IDs
 * @returns {Array<Object>} Ordered actions
 */
export function getActionsInOrder(order) {
    return order
        .map(id => getActionById(id))
        .filter(action => action !== null);
}

/**
 * Validate configuration
 * @param {Object} config - Configuration object
 * @returns {boolean} True if valid
 */
export function validateConfig(config) {
    if (!config || typeof config !== 'object') return false;
    if (!Array.isArray(config.order)) return false;
    if (!Array.isArray(config.removed)) return false;
    if (!config.shortcuts || typeof config.shortcuts !== 'object') return false;
    return true;
}
