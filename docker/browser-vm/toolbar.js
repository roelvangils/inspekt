// =============================================
// Customizable Toolbar for Inspekt VM
// =============================================
//
// A macOS-style customizable toolbar. Buttons are defined in a registry
// (TOOLBAR_BUTTONS) and rendered dynamically based on user preferences
// stored in localStorage. Users can:
//
//   - Show/hide buttons via a "Customize Toolbar" sheet
//   - Reorder buttons by dragging (only in customize mode)
//   - Switch display mode: icon+text, icon only, text only
//   - Access everything via right-click context menu on the toolbar
//
// Architecture:
//   TOOLBAR_BUTTONS (registry) + localStorage prefs → renderToolbarButtons() → DOM
//
// Dependencies (globals from control-panel.html):
//   - VNC_HOST, CONTROL_PORT       (server config)
//   - showContextMenu(), showToast() (UI helpers)
//   - toggleTerminal(), toggleDevTools(), toggleHoverInspect(),
//     toggleAudio(), toggleSRPopout(), openRecordingsModal(),
//     handleZoom(), toggleAutoScan(), toggleTabGrid(),
//     openRestartModal(), toggleDropdown()  (button action handlers)
//   - Sortable                     (SortableJS library)

// =============================================
// 1. Button Registry
// =============================================
// Each entry defines a toolbar button. Keys are unique IDs.
// Special fields:
//   - id:           DOM id to assign (for code that references getElementById)
//   - iconAlt:      Second SVG for toggle buttons (e.g. audio on/off)
//   - group:        Groups consecutive buttons visually (e.g. zoom controls)
//   - afterRender:  Called after the button's wrapper is added to DOM
//   - beforeRemove: Called before the button is removed from DOM
//   - customRender: Function that returns custom DOM instead of a standard button

const TOOLBAR_DEFAULT_BUTTONS = [
    'terminal', 'commands', 'devtools', 'inspect', 'audio', 'sr',
    'auto-scan', 'inspekt', 'restart'
];

const TOOLBAR_BUTTONS = {
    terminal: {
        id: null,
        label: 'Terminal',
        title: 'Open terminal',
        icon: '<svg viewBox="0 0 24 24"><path d="M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 14H4V8h16v10z"/><path d="M7 15l4-4-4-4"/></svg>',
        onclick: () => toggleTerminal()
    },
    commands: {
        id: 'cmdPaletteBtn',
        label: 'Commands',
        title: 'Command Palette (\u2318K)',
        icon: '<svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 0 0 1.48-5.34c-.47-2.78-2.79-5-5.59-5.34A6.505 6.505 0 0 0 3.03 9.8c0 3.22 2.34 5.9 5.42 6.44a6.5 6.5 0 0 0 2.66-.13l.27.28v.79l4.26 4.25c.41.41 1.07.41 1.48 0l.01-.01c.41-.41.41-1.07 0-1.48L15.5 14zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/></svg>',
        onclick: () => document.getElementById('commandPalette')?.open()
    },
    devtools: {
        id: 'devtoolsBtn',
        label: 'DevTools',
        title: 'Toggle DevTools (D)',
        icon: '<svg viewBox="0 0 24 24"><path d="M22.7 19l-9.1-9.1c.9-2.3.4-5-1.5-6.9-2-2-5-2.4-7.4-1.3L9 6 6 9 1.6 4.7C.4 7.1.9 10.1 2.9 12.1c1.9 1.9 4.6 2.4 6.9 1.5l9.1 9.1c.4.4 1 .4 1.4 0l2.3-2.3c.5-.4.5-1.1.1-1.4z"/></svg>',
        onclick: () => toggleDevTools()
    },
    inspect: {
        id: 'inspectBtn',
        label: 'Inspect',
        title: 'Toggle Element Inspector (I)',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3A8.994 8.994 0 0 0 13 3.06V1h-2v2.06A8.994 8.994 0 0 0 3.06 11H1v2h2.06A8.994 8.994 0 0 0 11 20.94V23h2v-2.06A8.994 8.994 0 0 0 20.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/></svg>',
        onclick: () => toggleHoverInspect()
    },
    audio: {
        id: 'audioBtn',
        label: 'Audio',
        title: 'Toggle Audio (A)',
        icon: '<svg id="audioIconOff" viewBox="0 0 24 24"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>',
        iconAlt: '<svg id="audioIconOn" viewBox="0 0 24 24" style="display:none;"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>',
        onclick: () => toggleAudio()
    },
    sr: {
        id: 'srBtn',
        label: 'SR',
        title: 'Screen Reader Simulator',
        icon: '<svg viewBox="0 0 24 24"><path d="M17 20c-.29 0-.56-.06-.76-.15-.71-.37-1.21-.88-1.71-2.38-.51-1.56-1.47-2.29-2.39-3-.79-.61-1.61-1.24-2.32-2.53C9.29 10.98 9 9.93 9 9c0-2.8 2.2-5 5-5s5 2.2 5 5h2c0-3.93-3.07-7-7-7S7 5.07 7 9c0 1.26.38 2.65 1.07 3.9.91 1.65 1.98 2.48 2.85 3.15.81.62 1.39 1.07 1.71 2.05.6 1.82 1.37 2.84 2.73 3.55A3.999 3.999 0 0 0 21 18h-2c0 1.1-.9 2-2 2zM7.64 2.64L6.22 1.22C4.23 3.21 3 5.96 3 9s1.23 5.79 3.22 7.78l1.41-1.41C6.01 13.74 5 11.49 5 9s1.01-4.74 2.64-6.36zM11.5 9a2.5 2.5 0 0 0 5 0 2.5 2.5 0 0 0-5 0z" fill="currentColor"/></svg>',
        onclick: () => toggleSRPopout(),
        wrapperClass: 'toolbar-btn-wrapper',
        afterRender: (wrapper) => {
            const popout = document.getElementById('srPopout');
            if (popout) { wrapper.appendChild(popout); popout.style.display = ''; }
        },
        beforeRemove: () => {
            const popout = document.getElementById('srPopout');
            const container = document.getElementById('srPopoutContainer');
            if (popout && container) { container.appendChild(popout); popout.style.display = 'none'; }
        }
    },
    'auto-scan': {
        id: null,
        label: 'Auto Scan',
        title: 'Auto-scan tabs for accessibility issues after 5 seconds',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z"/></svg>',
        customRender: () => {
            const label = document.createElement('label');
            label.className = 'auto-scan-toggle toolbar-auto-scan';
            label.title = 'Auto-scan tabs for accessibility issues after 5 seconds';
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.onchange = function() { toggleAutoScan(this.checked); };
            const span = document.createElement('span');
            span.textContent = 'Auto-scan';
            span.className = 'toolbar-btn-label';
            label.appendChild(checkbox);
            label.appendChild(span);
            return label;
        }
    },
    inspekt: {
        id: null,
        label: 'Inspekt',
        title: 'Run Inspekt commands',
        icon: '<svg viewBox="0 0 24 24"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>',
        customRender: () => {
            const dropdown = document.createElement('div');
            dropdown.className = 'dropdown toolbar-inspekt-dropdown';
            dropdown.innerHTML = `
                <button onclick="toggleDropdown(this)" title="Run Inspekt commands">
                    <svg viewBox="0 0 24 24"><path d="M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z"/></svg>
                    <span class="toolbar-btn-label">Inspekt</span>
                    <svg viewBox="0 0 24 24" style="width:12px;height:12px;margin-left:2px;"><path d="M7 10l5 5 5-5z"/></svg>
                </button>
                <div class="dropdown-menu">
                    <button class="dropdown-item" onclick="runInspekt('info')">
                        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>
                        Page Info
                    </button>
                    <button class="dropdown-item" onclick="runInspekt('axe')">
                        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/></svg>
                        Accessibility Audit
                    </button>
                    <button class="dropdown-item" onclick="runInspekt('links')">
                        <svg viewBox="0 0 24 24"><path d="M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z"/></svg>
                        Extract Links
                    </button>
                    <button class="dropdown-item" onclick="runInspekt('outline')">
                        <svg viewBox="0 0 24 24"><path d="M3 13h2v-2H3v2zm0 4h2v-2H3v2zm0-8h2V7H3v2zm4 4h14v-2H7v2zm0 4h14v-2H7v2zM7 7v2h14V7H7z"/></svg>
                        Page Outline
                    </button>
                    <div class="dropdown-divider"></div>
                    <button class="dropdown-item" onclick="runInspekt('screenshot')">
                        <svg viewBox="0 0 24 24"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>
                        Screenshot
                    </button>
                </div>
            `;
            return dropdown;
        }
    },
    restart: {
        id: null,
        label: 'Restart',
        title: 'Restart environment',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"/></svg>',
        onclick: () => openRestartModal()
    },
    vision: {
        id: null,
        label: 'Vision',
        title: 'Vision simulator',
        icon: '<svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>',
        customRender: () => buildVisionDropdown()
    },
    'grid-view': {
        id: null,
        label: 'Grid View',
        title: 'Tab overview',
        icon: '<svg viewBox="0 0 24 24"><rect x="3" y="3" width="8" height="8" rx="1.5" fill="currentColor"/><rect x="13" y="3" width="8" height="8" rx="1.5" fill="currentColor"/><rect x="3" y="13" width="8" height="8" rx="1.5" fill="currentColor"/><rect x="13" y="13" width="8" height="8" rx="1.5" fill="currentColor"/></svg>',
        onclick: () => toggleTabGrid()
    },
    recordings: {
        id: null,
        label: 'Recordings',
        title: 'Recordings',
        icon: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="currentColor"/></svg>',
        onclick: () => openRecordingsModal()
    },
    screenshot: {
        id: null,
        label: 'Screenshot',
        title: 'Take Screenshot',
        icon: '<svg viewBox="0 0 24 24"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z"/></svg>',
        onclick: () => takeToolbarScreenshot()
    },
    'zoom-in': {
        id: null, label: 'Zoom In', title: 'Zoom In', group: 'zoom',
        icon: '<svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/><path d="M12 10h-2v2H8v-2H6V8h2V6h2v2h2v2z"/></svg>',
        onclick: () => handleZoom('in')
    },
    'zoom-out': {
        id: null, label: 'Zoom Out', title: 'Zoom Out', group: 'zoom',
        icon: '<svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/><path d="M6 8h6v2H6z"/></svg>',
        onclick: () => handleZoom('out')
    },
    'zoom-reset': {
        id: null, label: 'Reset', title: 'Reset Zoom', group: 'zoom',
        icon: '<svg viewBox="0 0 24 24"><path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/><path d="M8 9h3v1H8z"/><path d="M10 7v3h-1V7z"/></svg>',
        onclick: () => handleZoom('reset')
    }
};


// =============================================
// 2. Preferences (localStorage)
// =============================================

/**
 * Read toolbar preferences from localStorage.
 * Returns { displayMode: string, buttons: string[] }.
 * Falls back to defaults if missing or corrupted.
 */
function getToolbarPrefs() {
    try {
        const stored = localStorage.getItem('inspekt_toolbar');
        if (stored) {
            const parsed = JSON.parse(stored);
            if (parsed && Array.isArray(parsed.buttons)) {
                // Filter out any button IDs that no longer exist in the registry
                parsed.buttons = parsed.buttons.filter(b => TOOLBAR_BUTTONS[b]);
                // Migration: append new default buttons that didn't exist when
                // the user last saved their prefs. We track "known" buttons so
                // we can distinguish "newly added to defaults" from "user removed it".
                const knownButtons = new Set(parsed._knownDefaults || []);
                const newDefaults = TOOLBAR_DEFAULT_BUTTONS.filter(b => !knownButtons.has(b));
                if (newDefaults.length > 0) {
                    parsed.buttons.push(...newDefaults);
                    parsed._knownDefaults = [...TOOLBAR_DEFAULT_BUTTONS];
                    localStorage.setItem('inspekt_toolbar', JSON.stringify(parsed));
                }
                return parsed;
            }
        }
    } catch { /* corrupted localStorage — use defaults */ }
    return { displayMode: 'icon-and-text', buttons: [...TOOLBAR_DEFAULT_BUTTONS] };
}

function saveToolbarPrefs(prefs) {
    // Track which defaults exist so future migrations can detect new ones
    prefs._knownDefaults = [...TOOLBAR_DEFAULT_BUTTONS];
    localStorage.setItem('inspekt_toolbar', JSON.stringify(prefs));
}


// =============================================
// 3. Toolbar Rendering
// =============================================

/** Whether the customize sheet is currently open. */
let _toolbarCustomizing = false;

/** SortableJS instances — stored so we can enable/disable and destroy them. */
let _toolbarSortable = null;
let _sheetSortable = null;

/**
 * Render all toolbar buttons into #toolbarButtons based on the current
 * preferences and display mode. Called on page load, after drag-drop,
 * display mode change, and customize sheet open/close.
 */
function renderToolbarButtons() {
    const container = document.getElementById('toolbarButtons');
    if (!container) return;

    const prefs = getToolbarPrefs();
    const displayMode = prefs.displayMode || 'icon-and-text';

    // Lifecycle: call beforeRemove on all buttons before clearing the DOM
    _callLifecycleHooks('beforeRemove');

    // Destroy existing SortableJS instance before clearing DOM
    if (_toolbarSortable) {
        _toolbarSortable.destroy();
        _toolbarSortable = null;
    }

    // Reset container classes
    container.innerHTML = '';
    container.className = 'toolbar-buttons';
    if (displayMode === 'icon-only') container.classList.add('display-icon-only');
    else if (displayMode === 'text-only') container.classList.add('display-text-only');
    if (_toolbarCustomizing) container.classList.add('toolbar-customizing');

    // Show placeholder when toolbar is empty (in customize mode)
    if (prefs.buttons.length === 0 && _toolbarCustomizing) {
        const placeholder = document.createElement('div');
        placeholder.className = 'toolbar-empty-placeholder';
        placeholder.textContent = 'Drag buttons here';
        container.appendChild(placeholder);
    }

    // Render each button (handling grouped buttons like zoom)
    let i = 0;
    while (i < prefs.buttons.length) {
        const key = prefs.buttons[i];
        const def = TOOLBAR_BUTTONS[key];
        if (!def) { i++; continue; }

        if (def.group) {
            i = _renderButtonGroup(container, prefs.buttons, i, def.group);
        } else {
            _renderSingleButton(container, key, def);
            i++;
        }
    }

    // Initialize SortableJS on the toolbar container
    _toolbarSortable = new Sortable(container, {
        animation: 150,
        easing: 'cubic-bezier(0.25, 1, 0.5, 1)',
        group: { name: 'toolbar', pull: true, put: true },
        draggable: '.toolbar-btn-wrapper',
        ghostClass: 'toolbar-btn-ghost',
        chosenClass: 'toolbar-btn-chosen',
        dragClass: 'toolbar-btn-drag',
        disabled: !_toolbarCustomizing,
        emptyInsertThreshold: 20,
        onSort: _onToolbarSort,
        onAdd: _onToolbarAdd,
        onRemove: _onToolbarRemove
    });
}

/** Call a lifecycle hook (beforeRemove or afterRender) on all buttons that define it. */
function _callLifecycleHooks(hookName) {
    for (const def of Object.values(TOOLBAR_BUTTONS)) {
        if (def[hookName]) def[hookName]();
    }
}

/** Render a group of consecutive buttons (e.g. zoom in/out/reset) as a joined cluster. */
function _renderButtonGroup(container, buttons, startIdx, groupName) {
    const groupDiv = document.createElement('div');
    groupDiv.className = 'toolbar-zoom-group';

    let i = startIdx;
    while (i < buttons.length && TOOLBAR_BUTTONS[buttons[i]]?.group === groupName) {
        groupDiv.appendChild(_createToolbarButton(buttons[i], TOOLBAR_BUTTONS[buttons[i]]));
        i++;
    }

    const wrapper = _createButtonWrapper(groupName + '-group');
    wrapper.appendChild(groupDiv);
    if (_toolbarCustomizing) {
        wrapper.appendChild(_createRemoveBadge(groupName + '-group'));
    }
    container.appendChild(wrapper);
    return i;
}

/** Render a single (non-grouped) button with optional remove badge. */
function _renderSingleButton(container, key, def) {
    const wrapper = _createButtonWrapper(key, def.wrapperClass);

    if (def.customRender) {
        wrapper.appendChild(def.customRender());
    } else {
        wrapper.appendChild(_createToolbarButton(key, def));
    }

    if (_toolbarCustomizing) {
        wrapper.appendChild(_createRemoveBadge(key));
    }

    // Lifecycle: let the button hook into the DOM (e.g. SR re-parents its popout)
    if (def.afterRender) def.afterRender(wrapper);

    container.appendChild(wrapper);
}

/** Create a wrapper div for a toolbar button (used for drag-and-drop targeting). */
function _createButtonWrapper(buttonKey, className) {
    const wrapper = document.createElement('div');
    wrapper.className = className || 'toolbar-btn-wrapper';
    wrapper.dataset.buttonKey = buttonKey;
    return wrapper;
}

/** Create a <button> element from a registry definition. */
function _createToolbarButton(key, def) {
    const btn = document.createElement('button');
    if (def.id) btn.id = def.id;
    btn.title = def.title;
    btn.onclick = def.onclick;
    btn.innerHTML = def.icon + (def.iconAlt || '')
        + '<span class="toolbar-btn-label">' + def.label + '</span>';
    return btn;
}

/** Create the red minus badge shown during customize mode. */
function _createRemoveBadge(key) {
    const badge = document.createElement('span');
    badge.className = 'toolbar-btn-remove';
    badge.textContent = '\u2212'; // minus sign
    badge.title = 'Remove from toolbar';
    badge.onclick = (e) => { e.stopPropagation(); _animateRemoveFromToolbar(key); };
    return badge;
}


// =============================================
// 4. SortableJS Event Handlers
// =============================================

/** Called when items are reordered within the toolbar. */
function _onToolbarSort(evt) {
    // Remove placeholder if it exists
    const placeholder = evt.to.querySelector('.toolbar-empty-placeholder');
    if (placeholder) placeholder.remove();

    _syncPrefsFromDOM();
}

/** Called when an item is added to the toolbar from the sheet. */
function _onToolbarAdd(evt) {
    // Remove placeholder if it exists
    const placeholder = evt.to.querySelector('.toolbar-empty-placeholder');
    if (placeholder) placeholder.remove();

    const itemEl = evt.item;
    const buttonKey = itemEl.dataset.buttonKey;

    if (!buttonKey || !TOOLBAR_BUTTONS[buttonKey]) {
        itemEl.remove();
        return;
    }

    // Replace the sheet-style element with a proper toolbar button wrapper
    const def = TOOLBAR_BUTTONS[buttonKey];
    const group = def.group;

    if (group) {
        // Adding a group: insert all group members
        const keysToAdd = Object.keys(TOOLBAR_BUTTONS).filter(k => TOOLBAR_BUTTONS[k].group === group);
        const wrapper = _createButtonWrapper(group + '-group');
        const groupDiv = document.createElement('div');
        groupDiv.className = 'toolbar-zoom-group';
        for (const k of keysToAdd) {
            groupDiv.appendChild(_createToolbarButton(k, TOOLBAR_BUTTONS[k]));
        }
        wrapper.appendChild(groupDiv);
        if (_toolbarCustomizing) wrapper.appendChild(_createRemoveBadge(group + '-group'));
        itemEl.replaceWith(wrapper);
    } else {
        const wrapper = _createButtonWrapper(buttonKey, def.wrapperClass);
        if (def.customRender) {
            wrapper.appendChild(def.customRender());
        } else {
            wrapper.appendChild(_createToolbarButton(buttonKey, def));
        }
        if (_toolbarCustomizing) wrapper.appendChild(_createRemoveBadge(buttonKey));
        if (def.afterRender) def.afterRender(wrapper);
        itemEl.replaceWith(wrapper);
    }

    _syncPrefsFromDOM();
    if (_toolbarCustomizing) _renderCustomizeSheet();
}

/** Called when an item is removed from the toolbar (dragged to sheet). */
function _onToolbarRemove(evt) {
    const buttonKey = evt.item.dataset.buttonKey;
    if (!buttonKey) return;

    // Call beforeRemove lifecycle hook
    const def = TOOLBAR_BUTTONS[buttonKey];
    if (def?.beforeRemove) def.beforeRemove();

    // For groups, remove all group members from prefs
    if (buttonKey.endsWith('-group')) {
        const groupName = buttonKey.replace('-group', '');
        const prefs = getToolbarPrefs();
        prefs.buttons = prefs.buttons.filter(b => TOOLBAR_BUTTONS[b]?.group !== groupName);
        saveToolbarPrefs(prefs);
    } else {
        _syncPrefsFromDOM();
    }

    // Show empty placeholder if needed
    _showEmptyPlaceholderIfNeeded();

    if (_toolbarCustomizing) _renderCustomizeSheet();
}

/** Read the current DOM order and sync it back to localStorage. */
function _syncPrefsFromDOM() {
    const container = document.getElementById('toolbarButtons');
    if (!container) return;

    const prefs = getToolbarPrefs();
    const newButtons = [];

    container.querySelectorAll('.toolbar-btn-wrapper').forEach(wrapper => {
        const key = wrapper.dataset.buttonKey;
        if (!key) return;

        if (key.endsWith('-group')) {
            // Expand group key back into individual button keys
            const groupName = key.replace('-group', '');
            const groupKeys = Object.keys(TOOLBAR_BUTTONS).filter(k => TOOLBAR_BUTTONS[k].group === groupName);
            newButtons.push(...groupKeys);
        } else if (TOOLBAR_BUTTONS[key]) {
            newButtons.push(key);
        }
    });

    prefs.buttons = newButtons;
    saveToolbarPrefs(prefs);
}

/** Show the "Drag buttons here" placeholder if toolbar is empty during customize mode. */
function _showEmptyPlaceholderIfNeeded() {
    const container = document.getElementById('toolbarButtons');
    if (!container || !_toolbarCustomizing) return;
    if (container.querySelectorAll('.toolbar-btn-wrapper').length === 0 &&
        !container.querySelector('.toolbar-empty-placeholder')) {
        const placeholder = document.createElement('div');
        placeholder.className = 'toolbar-empty-placeholder';
        placeholder.textContent = 'Drag buttons here';
        container.appendChild(placeholder);
    }
}


// =============================================
// 5. FLIP Animation for Removal (minus badge click)
// =============================================

/**
 * Animate a button flying from its toolbar position to the customize sheet
 * using the FLIP technique (First, Last, Invert, Play), then remove it.
 */
function _animateRemoveFromToolbar(key) {
    const wrapper = document.querySelector(`#toolbarButtons [data-button-key="${key}"]`);
    if (!wrapper) {
        _removeFromToolbar(key);
        return;
    }

    // If sheet is not open, just do a simple fade (shouldn't happen, but safety)
    const sheet = document.getElementById('customizeSheet');
    if (!sheet || !sheet.classList.contains('open')) {
        wrapper.classList.add('toolbar-btn-removing');
        wrapper.addEventListener('transitionend', () => _removeFromToolbar(key), { once: true });
        setTimeout(() => { if (wrapper.parentElement) _removeFromToolbar(key); }, 350);
        return;
    }

    // Find the target sheet button to fly toward
    const resolvedKey = key.endsWith('-group') ? key.replace('-group', '') : key;
    // Look up the first key for groups
    const sheetTarget = document.querySelector(`#customizeSheetButtons [data-button-key="${resolvedKey}"]`);

    // FLIP: First — capture current position
    const first = wrapper.getBoundingClientRect();

    // Create a fixed-position clone for the animation
    const clone = wrapper.cloneNode(true);
    // Remove the minus badge from clone
    const cloneBadge = clone.querySelector('.toolbar-btn-remove');
    if (cloneBadge) cloneBadge.remove();

    clone.style.position = 'fixed';
    clone.style.left = first.left + 'px';
    clone.style.top = first.top + 'px';
    clone.style.width = first.width + 'px';
    clone.style.height = first.height + 'px';
    clone.style.zIndex = '10001';
    clone.style.pointerEvents = 'none';
    clone.style.margin = '0';
    clone.className = 'toolbar-btn-wrapper toolbar-btn-flyout';
    document.body.appendChild(clone);

    // Hide the original immediately so the gap closes (other items slide via SortableJS animation)
    wrapper.style.display = 'none';

    // Compute target position
    let targetRect;
    if (sheetTarget) {
        targetRect = sheetTarget.getBoundingClientRect();
    } else {
        // Fallback: center of the sheet
        const sheetRect = sheet.getBoundingClientRect();
        targetRect = {
            left: sheetRect.left + sheetRect.width / 2 - first.width / 2,
            top: sheetRect.top + 20,
            width: first.width,
            height: first.height
        };
    }

    // FLIP: animate using Web Animations API
    const deltaX = targetRect.left - first.left;
    const deltaY = targetRect.top - first.top;
    const scaleX = targetRect.width / first.width;
    const scaleY = targetRect.height / first.height;

    const animation = clone.animate([
        {
            transform: 'translate(0, 0) scale(1)',
            opacity: 1
        },
        {
            transform: `translate(${deltaX}px, ${deltaY}px) scale(${scaleX}, ${scaleY})`,
            opacity: 0.3
        }
    ], {
        duration: 300,
        easing: 'cubic-bezier(0.25, 1, 0.5, 1)',
        fill: 'forwards'
    });

    animation.onfinish = () => {
        clone.remove();
        _removeFromToolbar(key);
    };

    // Safety fallback
    setTimeout(() => {
        if (clone.parentElement) clone.remove();
        if (wrapper.parentElement) _removeFromToolbar(key);
    }, 400);
}

/** Remove a button (or its entire group) from the toolbar. */
function _removeFromToolbar(key) {
    const prefs = getToolbarPrefs();

    if (key.endsWith('-group')) {
        const groupName = key.replace('-group', '');
        prefs.buttons = prefs.buttons.filter(b => TOOLBAR_BUTTONS[b]?.group !== groupName);
    } else {
        const group = TOOLBAR_BUTTONS[key]?.group;
        if (group) {
            prefs.buttons = prefs.buttons.filter(b => TOOLBAR_BUTTONS[b]?.group !== group);
        } else {
            prefs.buttons = prefs.buttons.filter(b => b !== key);
        }
    }

    _saveAndRender(prefs);
}

/** Add a button (or its entire group) to the end of the toolbar. */
function _addToToolbarEnd(key) {
    const prefs = getToolbarPrefs();
    if (prefs.buttons.includes(key)) return;

    const group = TOOLBAR_BUTTONS[key]?.group;
    if (group) {
        const keysToAdd = Object.keys(TOOLBAR_BUTTONS).filter(
            k => TOOLBAR_BUTTONS[k].group === group && !prefs.buttons.includes(k)
        );
        prefs.buttons.push(...keysToAdd);
    } else {
        prefs.buttons.push(key);
    }
    _saveAndRender(prefs);
}

/** Save preferences and re-render both toolbar and customize sheet. */
function _saveAndRender(prefs) {
    saveToolbarPrefs(prefs);
    renderToolbarButtons();
    if (_toolbarCustomizing) _renderCustomizeSheet();
}


// =============================================
// 6. Context Menu (right-click on toolbar)
// =============================================

function _setupToolbarContextMenu() {
    const controlBar = document.getElementById('controlBar');
    if (!controlBar) return;

    controlBar.addEventListener('contextmenu', (e) => {
        // Don't override context menu on URL bar or its dropdowns
        if (e.target.closest('.url-bar-wrapper')) return;
        // Don't show during customize mode
        if (_toolbarCustomizing) return;

        e.preventDefault();
        const prefs = getToolbarPrefs();
        const mode = prefs.displayMode || 'icon-and-text';

        // macOS-style: checkmark prefix on the active mode, whitespace on others
        const check = '\u2009\u2713\u2009';
        const blank = '\u2009\u2009\u2009\u2009';

        showContextMenu(e, [
            { label: (mode === 'icon-and-text' ? check : blank) + 'Icon & Text',  action: () => _setDisplayMode('icon-and-text') },
            { label: (mode === 'icon-only'    ? check : blank) + 'Icon Only',      action: () => _setDisplayMode('icon-only') },
            { label: (mode === 'text-only'    ? check : blank) + 'Text Only',      action: () => _setDisplayMode('text-only') },
            { separator: true },
            { label: blank + 'Customize Toolbar\u2026', action: () => openCustomizeSheet() }
        ]);
    });
}

/** Switch display mode and update all UI (toolbar, sheet, toggle buttons). */
function _setDisplayMode(mode) {
    const prefs = getToolbarPrefs();
    prefs.displayMode = mode;
    saveToolbarPrefs(prefs);
    renderToolbarButtons();
    _syncDisplayModeUI(mode);
    if (_toolbarCustomizing) _renderCustomizeSheet();
}

/** Sync the display mode toggle buttons and sheet button classes. */
function _syncDisplayModeUI(mode) {
    // Update segmented control in the sheet footer
    const toggles = document.getElementById('customizeDisplayModes');
    if (toggles) {
        toggles.querySelectorAll('button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.mode === mode);
        });
    }
    // Apply display mode class to sheet buttons so their appearance matches
    const sheetBtns = document.getElementById('customizeSheetButtons');
    if (sheetBtns) {
        sheetBtns.classList.remove('display-icon-only', 'display-text-only');
        if (mode === 'icon-only') sheetBtns.classList.add('display-icon-only');
        else if (mode === 'text-only') sheetBtns.classList.add('display-text-only');
    }
}


// =============================================
// 7. Customize Sheet
// =============================================

function openCustomizeSheet() {
    if (_toolbarCustomizing) return;
    _toolbarCustomizing = true;
    renderToolbarButtons();

    const backdrop = document.getElementById('customizeSheetBackdrop');
    const sheet = document.getElementById('customizeSheet');
    const controlBar = document.getElementById('controlBar');
    backdrop.classList.add('open');
    sheet.offsetHeight; // force reflow for transition
    sheet.classList.add('open');

    // Disable all non-toolbar interactions in the control bar
    if (controlBar) controlBar.classList.add('control-bar-customizing');

    _renderCustomizeSheet();
    _syncDisplayModeUI(getToolbarPrefs().displayMode || 'icon-and-text');

    // Enable dragging on toolbar
    if (_toolbarSortable) _toolbarSortable.option('disabled', false);

    // Escape closes the sheet (macOS behavior)
    document.addEventListener('keydown', _onCustomizeKeydown);

    // Backdrop click closes — but only on real clicks (not drag releases)
    backdrop.addEventListener('click', _onBackdropClick);
}

function closeCustomizeSheet() {
    if (!_toolbarCustomizing) return;
    _toolbarCustomizing = false;

    const sheet = document.getElementById('customizeSheet');
    const backdrop = document.getElementById('customizeSheetBackdrop');
    const controlBar = document.getElementById('controlBar');
    sheet?.classList.remove('open');
    backdrop?.classList.remove('open');
    backdrop?.removeEventListener('click', _onBackdropClick);
    document.removeEventListener('keydown', _onCustomizeKeydown);

    // Re-enable all control bar interactions
    if (controlBar) controlBar.classList.remove('control-bar-customizing');

    // Disable dragging and destroy sheet sortable
    if (_toolbarSortable) _toolbarSortable.option('disabled', true);
    if (_sheetSortable) {
        _sheetSortable.destroy();
        _sheetSortable = null;
    }

    renderToolbarButtons();
}

function _onCustomizeKeydown(e) {
    if (e.key === 'Escape' && _toolbarCustomizing) {
        e.preventDefault();
        e.stopPropagation();
        closeCustomizeSheet();
    }
}

function _onBackdropClick(e) {
    // Only close if the click is directly on the backdrop, not on the sheet or during a drag
    if (e.target.id === 'customizeSheetBackdrop') {
        closeCustomizeSheet();
    }
}

/** Render the available buttons in the customize sheet. */
function _renderCustomizeSheet() {
    const container = document.getElementById('customizeSheetButtons');
    if (!container) return;
    container.innerHTML = '';

    // Destroy existing sheet sortable before re-creating
    if (_sheetSortable) {
        _sheetSortable.destroy();
        _sheetSortable = null;
    }

    const prefs = getToolbarPrefs();
    const inToolbar = new Set(prefs.buttons);
    const seenGroups = new Set();

    for (const [key, def] of Object.entries(TOOLBAR_BUTTONS)) {
        // For grouped buttons, render one representative item per group
        if (def.group) {
            if (seenGroups.has(def.group)) continue;
            seenGroups.add(def.group);

            const groupKeys = Object.keys(TOOLBAR_BUTTONS).filter(k => TOOLBAR_BUTTONS[k].group === def.group);
            const anyInToolbar = groupKeys.some(k => inToolbar.has(k));

            const btn = _createSheetButton(key, def.icon, 'Zoom Controls', anyInToolbar);
            container.appendChild(btn);
        } else {
            const btn = _createSheetButton(key, def.icon, def.label, inToolbar.has(key));
            container.appendChild(btn);
        }
    }

    // Initialize SortableJS on the sheet container
    _sheetSortable = new Sortable(container, {
        animation: 150,
        easing: 'cubic-bezier(0.25, 1, 0.5, 1)',
        group: { name: 'toolbar', pull: true, put: true },
        draggable: '.sheet-btn:not(.in-toolbar)',
        ghostClass: 'sheet-btn-ghost',
        sort: false, // Don't allow reordering within the sheet
        onEnd: (evt) => {
            // If item was dropped back in the sheet (not moved to toolbar), re-render
            if (evt.from === evt.to) {
                _renderCustomizeSheet();
            }
        }
    });
}

/** Create a single button element for the customize sheet. */
function _createSheetButton(key, icon, label, isInToolbar) {
    const btn = document.createElement('div');
    btn.className = 'sheet-btn' + (isInToolbar ? ' in-toolbar' : '');
    btn.dataset.buttonKey = key;
    btn.innerHTML = icon + '<span>' + label + '</span>';

    if (!isInToolbar) {
        // Double-click adds to the end of the toolbar (convenience)
        btn.addEventListener('dblclick', () => _addToToolbarEnd(key));
    }
    return btn;
}

/** Reset the toolbar to the default button set. */
function resetToolbarToDefaults() {
    _saveAndRender({ displayMode: 'icon-and-text', buttons: [...TOOLBAR_DEFAULT_BUTTONS] });
    _syncDisplayModeUI('icon-and-text');
    showToast('Toolbar restored to defaults', 'info');
}


// =============================================
// 8. Screenshot Button Action
// =============================================

async function takeToolbarScreenshot() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/screenshot`);
        if (!resp.ok) throw new Error('Screenshot failed');
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'inspekt-screenshot-' + new Date().toISOString().replace(/[:.]/g, '-') + '.png';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast('Screenshot saved', 'success');
    } catch (e) {
        showToast('Screenshot failed: ' + e.message, 'error');
    }
}


// =============================================
// 9. Initialization
// =============================================

function initToolbar() {
    renderToolbarButtons();
    _setupToolbarContextMenu();
}
