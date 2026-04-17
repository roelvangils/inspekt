# Adding New Tiles to the Quick Actions System

This guide explains the modular architecture for adding new tiles (Quick Actions) to the Inspekt Chrome extension panel.

## Architecture Overview

The Quick Actions system uses a configuration-driven, modular architecture with clear separation of concerns:

- **Configuration**: `utils/quick-actions-config.js` - Single source of truth for all tile definitions
- **Manager**: `modules/quick-actions-manager.js` - Orchestrates tiles, state, and user interactions
- **Handlers**: `handlers/` - Individual handler functions for each tile action
- **Components**: `components/quick-actions/` - Reusable UI components (tiles, keyboard, drag-drop, manage panel)

## Step-by-Step Process for Adding a New Tile

### 1. Define the Action Configuration

Edit `/extensions/chrome/utils/quick-actions-config.js` and add a new entry to the `DEFAULT_ACTIONS` array:

```javascript
export const DEFAULT_ACTIONS = [
    // ... existing actions ...
    {
        id: 'myNewAction',              // Unique identifier (camelCase)
        icon: 'material_icon_name',     // Material Icon name (see Material Icons library)
        label: 'Action Title',           // Main title displayed on tile
        hint: 'Brief description',       // Subtext shown below title
        handler: 'handleMyAction',       // Handler function name
        shortcut: 'X',                   // Keyboard shortcut (single letter)
        requiresElement: false           // true = disabled when no element selected
    }
];
```

**Field Descriptions:**

- `id`: Unique identifier used internally. Use camelCase naming convention.
- `icon`: Name of a Material Icon (e.g., `gps_fixed`, `content_copy`, `search`). See [Material Icons](https://fonts.google.com/icons).
- `label`: The main text displayed on the tile. Keep it short (2-4 words).
- `hint`: Descriptive text shown below the label. Explains what the action does.
- `handler`: Name of the handler function that will be called when the tile is clicked or keyboard shortcut pressed.
- `shortcut`: Single keyboard key (A-Z, 0-9). Should be unique across all tiles.
- `requiresElement`: (Optional) Set to `true` if the action requires an element to be selected. The tile will be automatically disabled when no element is selected.

### 2. Create the Handler Function

Create a new file in `/extensions/chrome/handlers/` for your action:

**File**: `/extensions/chrome/handlers/my-action.js`

```javascript
/**
 * Handler for the "My New Action" quick action
 * @param {Object} context - Manager context with dependencies
 * @returns {Promise<void>|void}
 */
export function handleMyAction(context) {
    // Access dependencies via context:
    const currentElement = context.elementDisplay.getCurrentElement();
    const settings = context.settingsManager.getSettings();

    // Example: Check if element is required
    if (!currentElement) {
        console.warn('No element selected');
        return;
    }

    // Implement your action logic here
    console.log('Action executed for element:', currentElement.selector);

    // Example: Use utilities
    // context.copyToClipboard(event, 'text to copy', 'Label', settings);
    // context.elementHighlighter.highlight(currentElement);
}
```

**Available Context Properties:**

- `context.elementDisplay` - Access current element data via `getCurrentElement()`
- `context.elementPicker` - Control element picker via `activate()`, `deactivate()`
- `context.elementHighlighter` - Highlight elements via `highlight(element)`
- `context.settingsManager` - Access settings via `getSettings()`
- `context.copyToClipboard(event, text, label, settings)` - Copy text with feedback

### 3. Register the Handler

Edit `/extensions/chrome/modules/quick-actions-manager.js` and import your handler:

```javascript
// At the top with other imports
import { handleMyAction } from '../handlers/my-action.js';

// In the setupHandlers() method
setupHandlers() {
    this.handlers = {
        // ... existing handlers ...
        handleMyAction: handleMyAction,
    };
}
```

### 4. Test Your New Tile

That's it! The system will automatically:

- ✅ Render the new tile in the Quick Actions grid
- ✅ Set up the keyboard shortcut
- ✅ Handle drag-and-drop reordering
- ✅ Enable remove/restore functionality
- ✅ Persist user configuration to Chrome storage
- ✅ Manage disabled state (if `requiresElement: true`)

**To test:**

1. Reload the Chrome extension
2. Open the DevTools panel
3. Verify your new tile appears in the Quick Actions section
4. Click the tile or press the keyboard shortcut
5. Verify the handler executes correctly

## Tile States

Tiles can have multiple states:

### 1. Disabled State

When `requiresElement: true` is set in the config, the tile will automatically be disabled when no element is selected.

**Visual changes:**
- Reduced opacity (0.5)
- Cursor changes to `not-allowed`
- Click and keyboard shortcut are blocked

**State update:**
The system polls every 500ms to check if an element is selected and updates tile states accordingly.

### 2. Picking State

Applied when the element picker is active.

**CSS class**: `picking`

**Visual changes:**
- Special styling to indicate picker is active
- Tile text may change dynamically

### 3. Element Selected State

Applied when an element has been picked and is currently selected.

**CSS class**: `element-selected`

**Visual changes:**
- Tile may show selected element tag (e.g., "`<div>` is currently selected")

### 4. Custom States

You can add custom states to tiles by:

1. Adding CSS classes to the tile element
2. Updating the tile's text content dynamically
3. Using the tile's `disabled` property

**Example:**

```javascript
export function handleMyAction(context) {
    const tile = document.querySelector(`[data-action-id="myNewAction"]`);

    // Add custom state class
    tile.classList.add('processing');

    // Update tile text
    const label = tile.querySelector('.action-label');
    label.textContent = 'Processing…';

    // Perform async action
    await doSomethingAsync();

    // Remove state class
    tile.classList.remove('processing');
    label.textContent = 'Action Title';
}
```

## Advanced Features

### Dynamic Tile Text

You can update tile text dynamically based on state:

```javascript
export function handleMyAction(context) {
    const tile = document.querySelector(`[data-action-id="myNewAction"]`);
    const label = tile.querySelector('.action-label');
    const hint = tile.querySelector('.action-hint');

    if (someCondition) {
        label.textContent = 'New Label';
        hint.textContent = 'New description';
    }
}
```

### Visual Feedback

Use the existing notification system for user feedback:

```javascript
export function handleMyAction(context) {
    try {
        // Perform action

        // Show success feedback (you may need to create this utility)
        showNotification('Success!', 'success');
    } catch (error) {
        showNotification('Error: ' + error.message, 'error');
    }
}
```

### Async Handlers

Handlers can be async:

```javascript
export async function handleMyAction(context) {
    const currentElement = context.elementDisplay.getCurrentElement();

    // Show loading state
    const tile = document.querySelector(`[data-action-id="myNewAction"]`);
    tile.classList.add('loading');

    try {
        // Perform async operation
        const result = await chrome.runtime.sendMessage({
            action: 'processElement',
            selector: currentElement.selector
        });

        console.log('Result:', result);
    } finally {
        tile.classList.remove('loading');
    }
}
```

## Best Practices

### 1. Handler Naming

- Use descriptive, action-oriented names: `handleCopySelector`, `handleHighlightElement`
- Match the handler name in config to the actual function name
- Use camelCase convention

### 2. Error Handling

Always handle errors gracefully:

```javascript
export function handleMyAction(context) {
    try {
        const currentElement = context.elementDisplay.getCurrentElement();

        if (!currentElement) {
            console.warn('No element selected for action');
            return;
        }

        // Action logic

    } catch (error) {
        console.error('Error in handleMyAction:', error);
        // Show user-friendly error message
    }
}
```

### 3. Element Validation

If your action requires an element, always validate:

```javascript
export function handleMyAction(context) {
    const currentElement = context.elementDisplay.getCurrentElement();

    if (!currentElement) {
        console.warn('No element selected');
        return;
    }

    if (!currentElement.selector) {
        console.error('Element has no selector');
        return;
    }

    // Safe to use currentElement now
}
```

### 4. Keep Handlers Focused

Each handler should do one thing well:

- ✅ Good: `handleCopySelector` - copies selector to clipboard
- ❌ Bad: `handleCopyAndHighlightAndNavigate` - does too many things

If you need complex behavior, break it into multiple tiles or create utility functions.

### 5. Use Existing Utilities

Leverage existing utilities instead of reimplementing:

- `copyToClipboard()` - For copying text with visual feedback
- `elementHighlighter.highlight()` - For highlighting elements
- `elementPicker.activate()` - For activating element picker

### 6. Keyboard Shortcuts

Choose intuitive shortcuts:

- First letter of action name (e.g., `P` for Pick, `H` for Highlight)
- Avoid conflicts with existing shortcuts
- Avoid common browser shortcuts (Ctrl+S, etc.)

### 7. Icons

Choose icons that clearly represent the action:

- Use Material Icons library
- Prefer commonly recognized icons (camera for screenshot, copy for clipboard)
- Maintain visual consistency with existing tiles

## Modular Architecture Benefits

The current architecture provides:

1. **Easy Extension**: Add new tiles with just 2 files (config + handler)
2. **Separation of Concerns**: UI, state, and logic are separate
3. **Automatic Features**: Keyboard shortcuts, drag-drop, persistence all work automatically
4. **Reusable Components**: Tiles, keyboard handler, drag handler are all reusable
5. **Configuration-Driven**: Single source of truth for all tile definitions
6. **Dependency Injection**: Handlers receive all dependencies via context
7. **State Management**: Automatic handling of element selection state

## Future Improvements

Potential enhancements to the architecture:

1. **Plugin System**: Allow external scripts to register tiles
2. **Event Bus**: Replace polling with event-driven state updates
3. **TypeScript**: Add type definitions for better IDE support
4. **Custom Icons**: Support SVG icons in addition to Material Icons
5. **Tile Categories**: Group tiles by category (Element, Clipboard, Navigation)
6. **Conditional Visibility**: Hide tiles based on context (e.g., only show in certain pages)

## File Structure Reference

```
extensions/chrome/
├── utils/
│   └── quick-actions-config.js      # Tile configurations
├── handlers/
│   ├── pick-element.js              # Handler for Pick Element
│   ├── copy-selector.js             # Handler for Copy Selector
│   ├── screenshot.js                # Handler for Screenshot
│   └── utils/                       # Shared handler utilities
│       ├── clipboard.js
│       └── element-helpers.js
├── modules/
│   └── quick-actions-manager.js     # Main orchestrator
├── components/
│   └── quick-actions/
│       ├── action-tile.js           # Tile component
│       ├── keyboard-handler.js      # Keyboard shortcuts
│       ├── drag-handler.js          # Drag-and-drop reordering
│       └── manage-panel.js          # Remove/restore UI
└── panel.js                         # Entry point
```

## Example: Complete Tile Implementation

Here's a complete example of adding a "Copy XPath" tile:

### 1. Config (`quick-actions-config.js`)

```javascript
{
    id: 'copyXPath',
    icon: 'account_tree',
    label: 'Copy XPath',
    hint: 'Copy element XPath to clipboard',
    handler: 'handleCopyXPath',
    shortcut: 'X',
    requiresElement: true
}
```

### 2. Handler (`handlers/copy-xpath.js`)

```javascript
/**
 * Handler for copying element XPath to clipboard
 * @param {Object} context - Manager context
 */
export function handleCopyXPath(context) {
    const currentElement = context.elementDisplay.getCurrentElement();

    if (!currentElement || !currentElement.selector) {
        console.warn('No element selected for XPath copy');
        return;
    }

    // Send message to content script to get XPath
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        chrome.tabs.sendMessage(tabs[0].id, {
            action: 'getXPath',
            selector: currentElement.selector
        }, (response) => {
            if (response && response.xpath) {
                // Use existing clipboard utility
                context.copyToClipboard(
                    event,
                    response.xpath,
                    'XPath',
                    context.settingsManager.getSettings()
                );
            }
        });
    });
}
```

### 3. Register (`quick-actions-manager.js`)

```javascript
import { handleCopyXPath } from '../handlers/copy-xpath.js';

setupHandlers() {
    this.handlers = {
        // ... other handlers ...
        handleCopyXPath: handleCopyXPath,
    };
}
```

Done! Your new "Copy XPath" tile is now fully functional with all features automatically working.

---

**Questions?** Check the existing handlers in `/extensions/chrome/handlers/` for more examples and patterns.
