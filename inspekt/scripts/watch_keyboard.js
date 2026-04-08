// Watch keyboard input and send events back to server
(function() {
    const watchId = '__INSPEKT_KEYBOARD_WATCH__';

    // Check if already watching
    if (window[watchId]) {
        return { error: 'Keyboard watcher already active' };
    }

    // Create event handler
    const handler = (e) => {
        let key = '';

        // Special keys
        if (e.key === 'Enter') key = '[ENTER]';
        else if (e.key === 'Tab') key = '[TAB]';
        else if (e.key === 'Backspace') key = '[BACKSPACE]';
        else if (e.key === 'Delete') key = '[DELETE]';
        else if (e.key === 'Escape') key = '[ESC]';
        else if (e.key === 'ArrowUp') key = '[UP]';
        else if (e.key === 'ArrowDown') key = '[DOWN]';
        else if (e.key === 'ArrowLeft') key = '[LEFT]';
        else if (e.key === 'ArrowRight') key = '[RIGHT]';
        else if (e.key === 'Shift') key = '[SHIFT]';
        else if (e.key === 'Control') key = '[CTRL]';
        else if (e.key === 'Alt') key = '[ALT]';
        else if (e.key === 'Meta') key = '[META]';
        else if (e.key === 'CapsLock') key = '[CAPSLOCK]';
        else if (e.key === ' ') key = '[SPACE]';
        else if (e.key.length === 1) {
            key = e.key;
        } else {
            key = `[${e.key}]`;
        }

        // Add modifiers
        let modifiers = '';
        if (e.ctrlKey) modifiers += 'CTRL+';
        if (e.altKey) modifiers += 'ALT+';
        if (e.shiftKey && e.key !== 'Shift') modifiers += 'SHIFT+';
        if (e.metaKey) modifiers += 'META+';

        const output = modifiers ? `[${modifiers}${key}]` : key;

        // Store in events array for polling
        if (!window.__INSPEKT_KEYBOARD_EVENTS__) {
            window.__INSPEKT_KEYBOARD_EVENTS__ = [];
        }
        window.__INSPEKT_KEYBOARD_EVENTS__.push(output);
    };

    // Add listener
    document.addEventListener('keydown', handler, true);

    // Store handler for cleanup
    window[watchId] = handler;

    return {
        ok: true,
        message: 'Keyboard watcher started. Press keys to see output. Run inspekt.stopWatchingKeyboard() to stop.'
    };
})()
