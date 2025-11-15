// Get, set, or delete sessionStorage items
(function() {
    const action = 'ACTION_PLACEHOLDER'; // 'list', 'get', 'set', 'delete', 'clear'
    const key = 'KEY_PLACEHOLDER';
    const value = 'VALUE_PLACEHOLDER';

    // Check if sessionStorage is available
    function isAvailable() {
        try {
            const test = '__storage_test__';
            window.sessionStorage.setItem(test, test);
            window.sessionStorage.removeItem(test);
            return true;
        } catch (e) {
            return false;
        }
    }

    if (!isAvailable()) {
        return {
            ok: false,
            error: 'sessionStorage is not available (may be disabled or in private mode)'
        };
    }

    // Helper function to check if a string should be split into an array
    function splitDelimitedString(value) {
        // Check for pipe-separated values
        if (value.includes('|')) {
            return value.split('|').map(s => s.trim());
        }

        // Check for comma-separated values
        // Only split if there are multiple items (has commas)
        if (value.includes(',')) {
            const parts = value.split(',').map(s => s.trim());
            // Only treat as array if we have multiple non-empty parts
            if (parts.length > 1 && parts.every(p => p.length > 0)) {
                return parts;
            }
        }

        return null; // Not a delimited string
    }

    // Helper function to recursively transform values (including nested objects)
    function transformValueRecursive(obj) {
        if (obj === null || obj === undefined) {
            return obj;
        }

        // If it's an array, transform each element
        if (Array.isArray(obj)) {
            return obj.map(item => transformValueRecursive(item));
        }

        // If it's an object, transform each property
        if (typeof obj === 'object') {
            const result = {};
            for (const key in obj) {
                if (obj.hasOwnProperty(key)) {
                    result[key] = transformValueRecursive(obj[key]);
                }
            }
            return result;
        }

        // If it's a string, check if it's delimited
        if (typeof obj === 'string') {
            const delimited = splitDelimitedString(obj);
            if (delimited) {
                return delimited;
            }
        }

        // Return as-is for other types (numbers, booleans, etc.)
        return obj;
    }

    // Helper function to transform storage values
    function transformValue(value) {
        // Try to parse as JSON first
        try {
            const parsed = JSON.parse(value);
            // Recursively transform to handle nested delimited strings
            return transformValueRecursive(parsed);
        } catch (e) {
            // Not valid JSON, check for delimited values at top level
            const delimited = splitDelimitedString(value);
            if (delimited) {
                return delimited;
            }

            // Return as plain string
            return value;
        }
    }

    // Get all sessionStorage items
    function getAllItems() {
        const items = {};
        const length = window.sessionStorage.length;

        for (let i = 0; i < length; i++) {
            const itemKey = window.sessionStorage.key(i);
            if (itemKey !== null) {
                const rawValue = window.sessionStorage.getItem(itemKey);
                items[itemKey] = transformValue(rawValue);
            }
        }

        return items;
    }

    // Get a specific item
    function getItem(itemKey) {
        return window.sessionStorage.getItem(itemKey);
    }

    // Set an item
    function setItem(itemKey, itemValue) {
        try {
            window.sessionStorage.setItem(itemKey, itemValue);
            return true;
        } catch (e) {
            throw new Error(`Failed to set item: ${e.message}`);
        }
    }

    // Delete an item
    function deleteItem(itemKey) {
        window.sessionStorage.removeItem(itemKey);
        return true;
    }

    // Clear all items
    function clearAll() {
        const count = window.sessionStorage.length;
        window.sessionStorage.clear();
        return count;
    }

    // Execute action
    try {
        switch (action) {
            case 'list':
                const allItems = getAllItems();
                return {
                    ok: true,
                    action: 'list',
                    count: Object.keys(allItems).length,
                    items: allItems,
                    storageType: 'sessionStorage',
                    origin: window.location.origin,
                    hostname: window.location.hostname
                };

            case 'get':
                const itemValue = getItem(key);
                return {
                    ok: true,
                    action: 'get',
                    key: key,
                    value: itemValue,
                    exists: itemValue !== null,
                    storageType: 'sessionStorage'
                };

            case 'set':
                setItem(key, value);
                return {
                    ok: true,
                    action: 'set',
                    key: key,
                    value: value,
                    storageType: 'sessionStorage'
                };

            case 'delete':
                deleteItem(key);
                return {
                    ok: true,
                    action: 'delete',
                    key: key,
                    storageType: 'sessionStorage'
                };

            case 'clear':
                const deletedCount = clearAll();
                return {
                    ok: true,
                    action: 'clear',
                    deleted: deletedCount,
                    storageType: 'sessionStorage'
                };

            default:
                return {
                    ok: false,
                    error: 'Invalid action: ' + action,
                    storageType: 'sessionStorage'
                };
        }
    } catch (error) {
        return {
            ok: false,
            error: error.message,
            action: action,
            storageType: 'sessionStorage'
        };
    }
})()
