// =============================================
// Command Palette (ninja-keys)
// =============================================

// --- UI Commands: control panel actions (not from Inspekt registry) ---
// `content` can be a string (static) or a function (resolved each time the palette opens).
// For tab commands, it shows the active tab's page title.

function _activeTabContent() {
    const tab = tabs.find(t => t.id === activeTabId);
    if (!tab || !tab.title) return '';
    const title = tab.title;
    // Truncate title at ~30 chars with ellipsis, wrapped in typographic quotes
    const maxLen = 40;
    const truncated = title.length > maxLen ? title.substring(0, maxLen) + '\u2026' : title;
    const quoted = `\u201C${truncated}\u201D`;
    // Extract domain from URL
    try {
        const domain = new URL(tab.url).hostname.replace(/^www\./, '');
        return `${quoted} (${domain})`;
    } catch {
        return quoted;
    }
}

const UI_COMMANDS = [
    // Tabs
    { id: 'ui:new-tab',       title: 'New Cloud Tab',            section: 'Tabs',           keywords: 'create add open cloud',   handler: () => createNewTab(),                                                       content: () => `${tabs.length} tab${tabs.length !== 1 ? 's' : ''} open` },
    { id: 'ui:new-local-tab', title: 'New Local Tab',            section: 'Tabs',           keywords: 'local iframe host embed', handler: () => createLocalTab(),                                                     content: 'Load a URL in an iframe (bypasses VM)' },
    { id: 'ui:open-urls-clipboard', title: 'Open URLs from Clipboard', section: 'Tabs',     keywords: 'clipboard paste urls bulk batch', handler: () => openUrlsFromClipboard(),                                        content: 'Parse URLs from clipboard, open as cloud tabs' },
    { id: 'ui:close-tab',     title: 'Close Tab',                section: 'Tabs',           keywords: 'remove delete',            handler: () => closeTab(activeTabId),                                                content: _activeTabContent },
    { id: 'ui:duplicate-tab', title: 'Duplicate Tab',            section: 'Tabs',           keywords: 'copy clone',               handler: () => duplicateTab(activeTabId),                                            content: _activeTabContent },
    { id: 'ui:pin-tab',       title: 'Pin/Unpin Tab',            section: 'Tabs',           keywords: 'lock stick',               handler: () => togglePinTab(activeTabId),                                            content: _activeTabContent },
    { id: 'ui:close-others',  title: 'Close Other Tabs',         section: 'Tabs',           keywords: 'close all other',          handler: () => closeOtherTabs(activeTabId),                                          content: () => `${tabs.length - 1} other tab${tabs.length - 1 !== 1 ? 's' : ''}` },
    { id: 'ui:host-browser',  title: 'Open in Host Browser',     section: 'Tabs',           keywords: 'external open outside',    handler: () => openInHostBrowser(activeTabId),                                       content: _activeTabContent },
    { id: 'ui:tab-grid',      title: 'Tab Overview',             section: 'Tabs',           keywords: 'grid overview all tabs',    handler: () => toggleTabGrid(),                                                      content: () => `${tabs.length} tab${tabs.length !== 1 ? 's' : ''}` },
    // Terminal
    { id: 'ui:terminal',      title: 'Toggle Terminal',          section: 'Terminal',       keywords: 'shell console cli',         handler: () => toggleTerminal(),                                                     content: 'Open terminal overlay' },
    { id: 'ui:split-view',    title: 'Toggle Split View',        section: 'Terminal',       keywords: 'split side by side layout', handler: () => toggleSplitMode(),                                                    content: 'Side-by-side terminal and browser' },
    { id: 'ui:flip-split',    title: 'Flip Split Layout',        section: 'Terminal',       keywords: 'swap flip position',        handler: () => { if (terminalMode !== 'split') enterSplitMode(); flipSplitLayout(); }, content: 'Swap terminal and browser positions' },
    { id: 'ui:move-terminal', title: 'Move Terminal Left/Right', section: 'Terminal',       keywords: 'move position left right',  handler: () => toggleTerminalPosition(),                                             content: 'Move terminal to opposite side' },
    // View
    { id: 'ui:devtools',      title: 'Toggle DevTools',          section: 'View',           keywords: 'developer tools debug',     handler: () => toggleDevTools(),                                                     content: 'Chrome DevTools' },
    { id: 'ui:inspect',       title: 'Toggle Element Inspector', section: 'View',           keywords: 'inspect hover highlight',   handler: () => toggleHoverInspect(),                                                 content: 'Highlight elements on hover' },
    { id: 'ui:fullscreen',    title: 'Toggle Fullscreen',        section: 'View',           keywords: 'fullscreen maximize',       handler: () => toggleFullscreen(),                                                   content: 'Enter or exit fullscreen' },
    { id: 'ui:zoom-in',       title: 'Zoom In',                  section: 'View',           keywords: 'enlarge bigger',            handler: () => handleZoom('in'),                                                     content: 'Increase page zoom' },
    { id: 'ui:zoom-out',      title: 'Zoom Out',                 section: 'View',           keywords: 'shrink smaller',            handler: () => handleZoom('out'),                                                    content: 'Decrease page zoom' },
    { id: 'ui:zoom-reset',    title: 'Reset Zoom',               section: 'View',           keywords: 'zoom default 100%',         handler: () => handleZoom('reset'),                                                  content: 'Reset to 100%' },
    { id: 'ui:page-info',     title: 'Page Info',                section: 'View',           keywords: 'meta seo performance',      handler: () => togglePageInfo(),                                                     content: 'SEO, meta, performance' },
    { id: 'ui:audio',         title: 'Toggle Audio',             section: 'View',           keywords: 'sound mute unmute',         handler: () => toggleAudio(),                                                        content: 'Stream audio from VM' },
    { id: 'ui:screen-reader', title: 'Screen Reader Simulator',  section: 'Accessibility',  keywords: 'sr voiceover jaws nvda',    handler: () => toggleSRPopout(),                                                     content: 'JAWS, NVDA, VoiceOver' },
    { id: 'ui:vision-off',        title: 'Vision: Normal',           section: 'Accessibility',  keywords: 'vision simulate clear reset',       handler: () => clearVisionSimulation(),                                      content: 'Remove vision simulation' },
    { id: 'ui:vision-protanopia',  title: 'Vision: Protanopia',       section: 'Accessibility',  keywords: 'vision color blind red',            handler: () => setVisionSimulation('protanopia'),                            content: 'Red-blind simulation' },
    { id: 'ui:vision-deuteranopia',title: 'Vision: Deuteranopia',     section: 'Accessibility',  keywords: 'vision color blind green',          handler: () => setVisionSimulation('deuteranopia'),                          content: 'Green-blind simulation' },
    { id: 'ui:vision-tritanopia',  title: 'Vision: Tritanopia',       section: 'Accessibility',  keywords: 'vision color blind blue',           handler: () => setVisionSimulation('tritanopia'),                            content: 'Blue-blind simulation' },
    { id: 'ui:vision-achromatopsia',title:'Vision: Achromatopsia',    section: 'Accessibility',  keywords: 'vision color blind gray monochrome',handler: () => setVisionSimulation('achromatopsia'),                         content: 'Total color blindness' },
    { id: 'ui:vision-tunnel',      title: 'Vision: Tunnel Vision',    section: 'Accessibility',  keywords: 'vision tunnel peripheral field',    handler: () => setVisionSimulation('tunnel-vision'),                         content: 'Peripheral vision loss' },
    { id: 'ui:vision-scotoma',     title: 'Vision: Central Scotoma',  section: 'Accessibility',  keywords: 'vision scotoma macular central blind spot', handler: () => setVisionSimulation('central-scotoma'),                  content: 'Central vision loss (AMD)' },
    { id: 'ui:vision-cataracts',   title: 'Vision: Cataracts',        section: 'Accessibility',  keywords: 'vision cataracts blur yellow',      handler: () => setVisionSimulation('cataracts'),                             content: 'Cloudy lens simulation' },
    { id: 'ui:vision-low',         title: 'Vision: Low Vision',       section: 'Accessibility',  keywords: 'vision blur acuity low',            handler: () => setVisionSimulation('low-vision-moderate'),                   content: 'Blurred vision (20/100)' },
    { id: 'ui:vision-near-total',  title: 'Vision: Near-Total Loss',  section: 'Accessibility',  keywords: 'vision blur profound blind screen reader',    handler: () => setVisionSimulation('near-total-loss'),              content: 'Profound low vision — shapes only' },
    { id: 'ui:vision-light-only',  title: 'Vision: Light Perception', section: 'Accessibility',  keywords: 'vision light perception blind dark total',    handler: () => setVisionSimulation('light-perception'),             content: 'Light/dark only — screen reader essential' },
    { id: 'ui:vision-keratoconus', title: 'Vision: Keratoconus',      section: 'Accessibility',  keywords: 'vision keratoconus distortion cornea warp',  handler: () => setVisionSimulation('keratoconus'),                  content: 'Corneal distortion + ghosting' },
    { id: 'ui:vision-metamorphopsia',title:'Vision: Metamorphopsia',   section: 'Accessibility',  keywords: 'vision wavy distortion lines bent',          handler: () => setVisionSimulation('metamorphopsia'),               content: 'Wavy/bent line distortion' },
    { id: 'ui:vision-diplopia',    title: 'Vision: Diplopia',          section: 'Accessibility', keywords: 'vision double diplopia ghost strabismus',     handler: () => setVisionSimulation('diplopia'),                     content: 'Double vision (mouse-reactive)' },
    { id: 'ui:vision-floaters',    title: 'Vision: Diabetic Floaters', section: 'Accessibility', keywords: 'vision floaters dark spots diabetic drift',   handler: () => setVisionSimulation('diabetic-floaters'),            content: 'Drifting dark blobs' },
    { id: 'ui:vision-scarring',    title: 'Vision: Corneal Scarring', section: 'Accessibility',  keywords: 'vision scar cornea blur patch opacity',      handler: () => setVisionSimulation('corneal-scarring'),             content: 'Localized blur + distortion' },
    { id: 'ui:vision-nystagmus',   title: 'Vision: Nystagmus',        section: 'Accessibility',  keywords: 'vision nystagmus jitter shake oscillation',   handler: () => setVisionSimulation('nystagmus'),                    content: 'Involuntary eye oscillation' },
    { id: 'ui:vision-snow',        title: 'Vision: Visual Snow',      section: 'Accessibility',  keywords: 'vision snow static noise grain flicker',      handler: () => setVisionSimulation('visual-snow'),                  content: 'Persistent TV-static overlay' },
    { id: 'ui:vision-glaucoma',    title: 'Vision: Glaucoma',         section: 'Accessibility',  keywords: 'vision glaucoma peripheral scotoma patchy',   handler: () => setVisionSimulation('glaucoma'),                     content: 'Patchy peripheral scotomas' },
    { id: 'ui:vision-hemianopia',  title: 'Vision: Hemianopia',       section: 'Accessibility',  keywords: 'vision hemianopia half field stroke left',    handler: () => setVisionSimulation('hemianopia'),                   content: 'Left visual field loss' },
    // Motor impairment simulators
    { id: 'ui:motor-parkinsons',   title: "Motor: Parkinson's Tremor", section: 'Accessibility', keywords: 'motor parkinson tremor shake cursor hand',    handler: () => setMotorSimulation('parkinsons'),                    content: 'Resting tremor (4-6 Hz)' },
    { id: 'ui:motor-essential',    title: 'Motor: Essential Tremor',   section: 'Accessibility', keywords: 'motor essential tremor action intention',     handler: () => setMotorSimulation('essential-tremor'),              content: 'Action tremor — worsens on reach' },
    { id: 'ui:motor-spasm',        title: 'Motor: Muscle Spasms',      section: 'Accessibility', keywords: 'motor spasm jerk involuntary cerebral palsy', handler: () => setMotorSimulation('muscle-spasm'),                  content: 'Sudden involuntary cursor jumps' },
    { id: 'ui:motor-limited',      title: 'Motor: Limited Fine Motor', section: 'Accessibility', keywords: 'motor limited dexterity arthritis precision', handler: () => setMotorSimulation('limited-mobility'),              content: 'Reduced cursor precision' },
    { id: 'ui:motor-off',          title: 'Motor: Normal',             section: 'Accessibility', keywords: 'motor clear reset normal off',                 handler: () => clearMotorSimulation(),                              content: 'Remove motor simulation' },
    // Navigation
    { id: 'ui:back',          title: 'Go Back',                  section: 'Navigation',     keywords: 'previous history back',     handler: () => goBack(),                                                             content: 'Navigate to previous page' },
    { id: 'ui:forward',       title: 'Go Forward',               section: 'Navigation',     keywords: 'next history forward',      handler: () => goForward(),                                                          content: 'Navigate to next page' },
    { id: 'ui:reload',        title: 'Reload Page',              section: 'Navigation',     keywords: 'refresh reload',            handler: () => reloadPage(),                                                         content: _activeTabContent },
    // Restart
    { id: 'ui:customize-toolbar', title: 'Customize Toolbar',       section: 'View',           keywords: 'toolbar buttons customize rearrange', handler: () => openCustomizeSheet(),                                           content: 'Add, remove, and reorder buttons' },
    { id: 'ui:restart-browser', title: 'Restart Browser',          section: 'Restart',        keywords: 'restart chromium refresh config', handler: () => performRestartBrowser(),                                          content: 'Apply config changes' },
    { id: 'ui:restart-all',     title: 'Restart All Services',     section: 'Restart',        keywords: 'restart reboot vnc proxy terminal', handler: () => performRestartAll(),                                            content: 'Browser, VNC, proxy, terminal' },
    { id: 'ui:reset-env',       title: 'Reset Environment',        section: 'Restart',        keywords: 'reset fresh clean destroy',   handler: () => performResetEnvironment(),                                             content: 'Clear all browsing data' },
];

// --- Inspekt command configuration ---

// Categories that get nested submenus in the palette
const NESTED_CATEGORIES = new Set([
    'Extraction', 'Interaction', 'Accessibility', 'Inspection', 'Selection', 'Storage'
]);

// Categories hidden from the palette (not useful in VM context)
const HIDDEN_CATEGORIES = new Set(['Control']);

// No icons — emojis look unprofessional. Commands are identified by title only.
const CATEGORY_ICONS = {};

// Output routing overrides (command cli_name → output mode)
// Default: 'panel' for most commands, 'toast' for navigation-like commands
const OUTPUT_OVERRIDES = {
    // Toast (quick, no structured output)
    'open': 'toast', 'back': 'toast', 'forward': 'toast', 'reload': 'toast',
    'top': 'toast', 'bottom': 'toast', 'click': 'toast', 'type': 'toast',
    'focus': 'toast', 'page-up': 'toast', 'page-down': 'toast',
    'paste': 'toast', 'press': 'toast',
    // Terminal (interactive or long output)
    'ask': 'terminal', 'js': 'terminal', 'record': 'terminal', 'replay': 'terminal',
    'do': 'terminal', 'sitemap': 'terminal',
};

// Commands that need argument prompts before execution
// Value is array of field definitions, or 'terminal' to route to terminal for input
const PARAM_PROMPTS = {
    'open': [{ name: 'url', label: 'URL', placeholder: 'https://example.com' }],
    'click': [{ name: 'selector', label: 'CSS Selector', placeholder: '.button, #submit' }],
    'type': [{ name: 'text', label: 'Text to type', placeholder: 'Hello world' }],
    'focus': [{ name: 'selector', label: 'CSS Selector', placeholder: '#email, .input' }],
    'press': [{ name: 'keys', label: 'Keys', placeholder: 'Tab, Enter, Ctrl+A' }],
    'ask': [{ name: 'question', label: 'Question', placeholder: 'What color is the logo?' }],
    'do': [{ name: 'action', label: 'Action', placeholder: 'Click the login button' }],
    'js': 'terminal',
};

// --- Pinned commands (localStorage-backed) ---

function getPinnedCommandIds() {
    try { return JSON.parse(localStorage.getItem('inspekt_pinned_commands')) || []; }
    catch { return []; }
}
function savePinnedCommandIds(ids) {
    localStorage.setItem('inspekt_pinned_commands', JSON.stringify(ids));
}
function togglePinCommand(id) {
    const ids = getPinnedCommandIds();
    const idx = ids.indexOf(id);
    if (idx >= 0) ids.splice(idx, 1); else ids.push(id);
    savePinnedCommandIds(ids);
    return idx < 0; // true = just pinned, false = just unpinned
}

// --- Registry fetch ---

let _registryData = null;

async function fetchRegistryCommands() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/commands/by-category`, {
            signal: AbortSignal.timeout(5000),
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        _registryData = data;
        return data;
    } catch (err) {
        console.warn('[CommandPalette] Failed to load registry:', err.message);
        return null;
    }
}

// --- Build palette data ---

function getOutputMode(cliName, category) {
    if (OUTPUT_OVERRIDES[cliName]) return OUTPUT_OVERRIDES[cliName];
    // Convention: Navigation-like categories default to toast, others to panel
    if (category === 'Navigation') return 'toast';
    return 'panel';
}

function buildCommandPaletteData(registryData) {
    const items = [];

    // === UI Commands (always available, sync) ===
    for (const cmd of UI_COMMANDS) {
        // Resolve content: string stays as-is, function is called for dynamic values
        const content = typeof cmd.content === 'function' ? cmd.content() : (cmd.content || '');
        items.push({
            id: cmd.id,
            title: cmd.title,
            section: cmd.section,
            keywords: cmd.keywords || '',
            hotkey: cmd.hotkey,
            handler: cmd.handler,
            content,
        });
    }

    // === Inspekt Commands (from registry API) ===
    if (registryData && registryData.categories) {
        for (const [category, commands] of Object.entries(registryData.categories)) {
            if (HIDDEN_CATEGORIES.has(category)) continue;

            const isNested = NESTED_CATEGORIES.has(category);
            const parentId = `cat:${category.toLowerCase().replace(/\s+/g, '-')}`;
            const catIcon = CATEGORY_ICONS[category] || '';

            if (isNested && commands.length > 2) {
                // Add parent item for nested category
                items.push({
                    id: parentId,
                    title: category,
                    icon: catIcon,
                    section: 'Inspekt',
                    keywords: category.toLowerCase(),
                    children: commands.map(c => `inspekt:${c.id}`),
                });
            }

            for (const cmd of commands) {
                const cliName = cmd.cli_name;
                const outputMode = getOutputMode(cliName, category);
                const useNesting = isNested && commands.length > 2;

                items.push({
                    id: `inspekt:${cmd.id}`,
                    title: cmd.name,
                    icon: catIcon,
                    section: useNesting ? undefined : category,
                    parent: useNesting ? parentId : undefined,
                    keywords: `${cliName} ${cmd.description || ''} ${category}`.toLowerCase(),
                    handler: () => executeInspektCommand(cmd, outputMode),
                    content: cmd.description || '',
                });
            }
        }
    }

    // === Pinned Commands (prepend "Pinned" section at top) ===
    const pinnedIds = getPinnedCommandIds();
    if (pinnedIds.length > 0) {
        const pinnedItems = [];
        for (const pinnedId of pinnedIds) {
            const original = items.find(i => i.id === pinnedId);
            if (original) {
                pinnedItems.push({
                    ...original,
                    id: `pinned:${original.id}`,  // Unique ID to avoid ninja-keys dedup
                    section: 'Pinned',
                    parent: undefined,             // Always show at top level
                    content: original.content,
                });
            }
        }
        // Pinned section first, then everything else
        return [...pinnedItems, ...items];
    }

    return items;
}

// --- Helpers ---

// Shell-escape a single argument (POSIX single-quote wrapping)
function shellQuote(s) {
    return "'" + s.replace(/'/g, "'\\''") + "'";
}

// --- Argument prompt overlay ---

let _activePromptOverlay = null;

function promptForArgs(title, fields) {
    // Dismiss any existing prompt to prevent stacking
    if (_activePromptOverlay) { _activePromptOverlay.remove(); _activePromptOverlay = null; }

    return new Promise((resolve) => {
        // Create overlay
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;z-index:3000;background:rgba(0,0,0,0.5);display:flex;align-items:flex-start;justify-content:center;padding-top:15vh;';

        const dialog = document.createElement('div');
        dialog.style.cssText = 'background:rgba(20,20,30,0.95);backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:20px;width:500px;max-width:90vw;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,sans-serif;';

        const titleEl = document.createElement('div');
        titleEl.textContent = title;
        titleEl.style.cssText = 'font-size:14px;font-weight:600;margin-bottom:16px;color:#aaa;';
        dialog.appendChild(titleEl);

        const input = document.createElement('input');
        input.type = 'text';
        input.placeholder = fields[0].placeholder || '';
        input.style.cssText = 'width:100%;padding:10px 14px;border:1px solid rgba(255,255,255,0.15);border-radius:8px;background:rgba(255,255,255,0.05);color:#fff;font-size:15px;outline:none;box-sizing:border-box;';
        input.addEventListener('focus', () => { input.style.borderColor = '#667eea'; });
        input.addEventListener('blur', () => { input.style.borderColor = 'rgba(255,255,255,0.15)'; });
        dialog.appendChild(input);

        const hint = document.createElement('div');
        hint.textContent = 'Press Enter to run, Escape to cancel';
        hint.style.cssText = 'font-size:11px;color:#666;margin-top:10px;text-align:center;';
        dialog.appendChild(hint);

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);
        _activePromptOverlay = overlay;

        function cleanup(value) {
            overlay.remove();
            _activePromptOverlay = null;
            resolve(value);
        }

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                const val = input.value.trim();
                cleanup(val || null);
            } else if (e.key === 'Escape') {
                e.preventDefault();
                cleanup(null);
            }
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cleanup(null);
        });

        // Focus after a tick (palette may still be closing)
        requestAnimationFrame(() => input.focus());
    });
}

// --- Execute Inspekt command ---

async function executeInspektCommand(cmd, outputMode) {
    const cliName = cmd.cli_name;
    const title = cmd.name;
    const icon = CATEGORY_ICONS[cmd.category] || '';

    // Check if command needs arguments
    const promptDef = PARAM_PROMPTS[cliName];

    if (promptDef === 'terminal') {
        // Interactive command — open terminal and let user type
        toggleTerminal();
        showToast(`Opening terminal for ${title}…`);
        setTimeout(() => {
            if (terminalSocket && terminalSocket.readyState === WebSocket.OPEN) {
                terminalSocket.send(`inspekt ${cliName} `);
            }
        }, 400);
        return;
    }

    let commandStr = cliName;

    if (promptDef && Array.isArray(promptDef)) {
        const value = await promptForArgs(title, promptDef);
        if (value === null) return; // Cancelled
        commandStr = `${cliName} ${shellQuote(value)}`;
    }

    if (outputMode === 'terminal') {
        toggleTerminal();
        showToast(`Running ${title}…`);
        setTimeout(() => {
            if (terminalSocket && terminalSocket.readyState === WebSocket.OPEN) {
                terminalSocket.send(`inspekt ${commandStr}\n`);
            }
        }, 400);
        return;
    }

    if (outputMode === 'toast') {
        showToast(`Running ${title}…`);
        try {
            const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${encodeURIComponent(commandStr)}`);
            const data = await response.json();
            if (data.ok) {
                showToast(`${title} completed`, 'success');
            } else {
                showToast(`Error: ${data.error}`, 'error', 5000);
            }
        } catch (error) {
            showToast(`Failed: ${error.message}`, 'error');
        }
        return;
    }

    // Default: panel output
    showToast(`Running ${title}…`);
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${encodeURIComponent(commandStr)}`);
        const data = await response.json();

        if (data.ok) {
            const content = formatOutputForPanel(cliName, data.output);
            openOutputPanel(title, icon, content);
            showToast(`${title} completed`, 'success');
        } else {
            showToast(`Error: ${data.error}`, 'error', 5000);
        }
    } catch (error) {
        showToast(`Failed: ${error.message}`, 'error');
    }
}

// Output Panel Functions
function openOutputPanel(title, icon, content) {
    const panel = document.getElementById('outputPanel');
    document.getElementById('outputPanelTitle').textContent = title;
    document.getElementById('outputPanelIcon').textContent = icon;
    document.getElementById('outputPanelContent').innerHTML = content;
    panel.classList.add('open');
}

function closeOutputPanel() {
    document.getElementById('outputPanel').classList.remove('open');
}

// Format command output for panel display
function formatOutputForPanel(commandId, output) {
    // Try to parse as JSON first
    let data;
    try {
        data = typeof output === 'string' ? JSON.parse(output) : output;
    } catch {
        // Plain text output
        return `<pre style="white-space: pre-wrap; font-family: 'JetBrains Mono NF', monospace; font-size: 12px;">${escapeHtml(output)}</pre>`;
    }

    // Format based on command type
    if (commandId === 'axe' || commandId.startsWith('axe ')) {
        return formatAxeOutput(data);
    }
    if (commandId === 'outline') {
        return formatOutlineOutput(data);
    }
    if (commandId === 'links') {
        return formatLinksOutput(data);
    }
    if (commandId === 'info') {
        return formatInfoOutput(data);
    }
    if (commandId.includes('cookies') || commandId.includes('storage')) {
        return formatStorageOutput(data);
    }
    if (commandId === 'console' || commandId.startsWith('console ')) {
        return formatConsoleOutput(data);
    }

    // Default: pretty print JSON
    return `<pre style="white-space: pre-wrap; font-family: 'JetBrains Mono NF', monospace; font-size: 12px;">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatAxeOutput(data) {
    if (!data.violations || data.violations.length === 0) {
        return `<div style="padding: 20px; text-align: center; color: #10b981;">
            <div style="font-size: 48px; margin-bottom: 10px;">✓</div>
            <div style="font-size: 18px; font-weight: 600;">No accessibility violations found!</div>
        </div>`;
    }

    let html = `<div style="margin-bottom: 10px; color: #f59e0b;">Found ${data.violations.length} violation(s)</div>`;
    html += '<table><thead><tr><th>Impact</th><th>Rule</th><th>Description</th><th>Count</th></tr></thead><tbody>';

    data.violations.forEach(v => {
        const impactColor = {
            critical: '#ef4444',
            serious: '#f97316',
            moderate: '#f59e0b',
            minor: '#3b82f6'
        }[v.impact] || '#888';

        html += `<tr>
            <td><span style="color: ${impactColor}; font-weight: 600;">${v.impact}</span></td>
            <td style="font-family: monospace;">${escapeHtml(v.id)}</td>
            <td>${escapeHtml(v.description)}</td>
            <td>${v.nodes?.length || 1}</td>
        </tr>`;
    });

    html += '</tbody></table>';
    return html;
}

function formatOutlineOutput(data) {
    if (!data.headings || data.headings.length === 0) {
        return '<div style="padding: 20px; text-align: center; color: #888;">No headings found on this page.</div>';
    }

    let html = '<div style="font-family: monospace; line-height: 1.8;">';
    data.headings.forEach(h => {
        const indent = (parseInt(h.level.replace('h', '')) - 1) * 20;
        const color = h.level === 'h1' ? '#60a5fa' : h.level === 'h2' ? '#34d399' : '#888';
        html += `<div style="padding-left: ${indent}px;">
            <span style="color: ${color}; font-weight: 600;">${h.level}</span> ${escapeHtml(h.text)}
        </div>`;
    });
    html += '</div>';
    return html;
}

function formatLinksOutput(data) {
    const links = data.links || data;
    if (!links || links.length === 0) {
        return '<div style="padding: 20px; text-align: center; color: #888;">No links found on this page.</div>';
    }

    let html = `<div style="margin-bottom: 10px;">Found ${links.length} link(s)</div>`;
    html += '<table><thead><tr><th>Text</th><th>URL</th><th>Type</th></tr></thead><tbody>';

    links.slice(0, 100).forEach(link => {
        html += `<tr>
            <td>${escapeHtml(link.text || '(no text)')}</td>
            <td style="max-width: 300px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(link.href || link.url)}</td>
            <td>${link.type || '-'}</td>
        </tr>`;
    });

    if (links.length > 100) {
        html += `<tr><td colspan="3" style="text-align: center; color: #888;">... and ${links.length - 100} more</td></tr>`;
    }

    html += '</tbody></table>';
    return html;
}

function formatInfoOutput(data) {
    let html = '<table>';
    const fields = ['title', 'url', 'description', 'author', 'language', 'viewport'];
    fields.forEach(field => {
        if (data[field]) {
            html += `<tr><th style="text-align: left; width: 120px;">${field}</th><td>${escapeHtml(String(data[field]))}</td></tr>`;
        }
    });
    html += '</table>';
    return html;
}

function formatStorageOutput(data) {
    const items = data.cookies || data.items || data;
    if (!items || items.length === 0) {
        return '<div style="padding: 20px; text-align: center; color: #888;">No items found.</div>';
    }

    let html = '<table><thead><tr><th>Name</th><th>Value</th></tr></thead><tbody>';
    items.forEach(item => {
        const name = item.name || item.key;
        const value = item.value || '';
        html += `<tr>
            <td style="font-family: monospace;">${escapeHtml(name)}</td>
            <td style="max-width: 400px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(value.substring(0, 100))}${value.length > 100 ? '…' : ''}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    return html;
}

function formatConsoleOutput(data) {
    const logs = data.logs || data.messages || data;
    if (!logs || logs.length === 0) {
        return '<div style="padding: 20px; text-align: center; color: #888;">Console is empty.</div>';
    }

    let html = '<div style="font-family: monospace; font-size: 12px; line-height: 1.6;">';
    logs.forEach(log => {
        const color = {
            error: '#ef4444',
            warn: '#f59e0b',
            info: '#3b82f6',
            log: '#888'
        }[log.level] || '#888';
        html += `<div style="padding: 4px 8px; border-bottom: 1px solid #333;">
            <span style="color: ${color};">[${log.level}]</span> ${escapeHtml(log.text || log.message)}
        </div>`;
    });
    html += '</div>';
    return html;
}

// ── Page analysis output formatters ──

function formatPerformanceOutput(metrics) {
    const rows = [
        ['Page Load Time', metrics.page_load_time + ' ms'],
        ['DOM Interactive', metrics.dom_interactive + ' ms'],
        ['DOM Processing', metrics.dom_processing + ' ms'],
        ['DNS Lookup', metrics.dns_lookup + ' ms'],
        ['TCP Connection', metrics.tcp_connection + ' ms'],
        ['Request Time', metrics.request_time + ' ms'],
        ['Response Time', metrics.response_time + ' ms'],
        ['Navigation Type', metrics.navigation_type],
        ['Redirects', metrics.redirect_count],
        ['Resources', metrics.resource_count],
    ];
    if (metrics.memory) {
        rows.push(['JS Heap Used', metrics.memory.used_heap + ' MB']);
        rows.push(['JS Heap Total', metrics.memory.total_heap + ' MB']);
        rows.push(['JS Heap Limit', metrics.memory.heap_limit + ' MB']);
    }
    let html = '<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>';
    rows.forEach(([metric, value]) => {
        html += `<tr><td>${escapeHtml(metric)}</td><td style="font-family: monospace;">${escapeHtml(String(value))}</td></tr>`;
    });
    html += '</tbody></table>';
    return html;
}

function formatImageAnalysisOutput(data) {
    if (!data.images || data.images.length === 0) {
        return `<div style="padding: 20px; text-align: center; color: #888;">No visible images found (${data.totalImages} total, all hidden).</div>`;
    }
    let html = `<div style="margin-bottom: 10px; color: #94a3b8;">${data.visibleImages} visible of ${data.totalImages} total images</div>`;
    html += '<table><thead><tr><th>#</th><th>Alt Text</th><th>Size</th><th>Rendered</th><th>Loaded</th></tr></thead><tbody>';
    data.images.forEach(img => {
        const altColor = img.alt ? '#10b981' : '#ef4444';
        const altText = img.alt || '(missing)';
        html += `<tr>
            <td>${img.index}</td>
            <td style="color: ${altColor}; max-width: 200px; overflow: hidden; text-overflow: ellipsis;">${escapeHtml(altText)}</td>
            <td style="font-family: monospace;">${img.naturalWidth}\u00d7${img.naturalHeight}</td>
            <td style="font-family: monospace;">${img.width}\u00d7${img.height}</td>
            <td>${img.complete ? '\u2705' : '\u274c'}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    return html;
}

function formatTablesOutput(data) {
    if (!data.tables || data.tables.length === 0) {
        return '<div style="padding: 20px; text-align: center; color: #888;">No tables found.</div>';
    }
    let html = `<div style="margin-bottom: 10px; color: #94a3b8;">Found ${data.count} table(s)</div>`;
    data.tables.forEach((table, idx) => {
        html += `<div style="margin-bottom: 16px;">`;
        html += `<div style="font-weight: 600; margin-bottom: 6px;">Table ${idx + 1} (${table.rows} rows \u00d7 ${table.columns} cols)</div>`;
        if (table.data.length === 0) {
            html += '<div style="color: #888; font-style: italic;">Empty table</div>';
        } else if (Array.isArray(table.data[0])) {
            // Array rows (no headers)
            html += '<table><tbody>';
            table.data.slice(0, 20).forEach(row => {
                html += '<tr>' + row.map(cell => `<td>${escapeHtml(cell)}</td>`).join('') + '</tr>';
            });
            html += '</tbody></table>';
        } else {
            // Object rows (with headers)
            const keys = Object.keys(table.data[0]);
            html += '<table><thead><tr>' + keys.map(k => `<th>${escapeHtml(k)}</th>`).join('') + '</tr></thead><tbody>';
            table.data.slice(0, 20).forEach(row => {
                html += '<tr>' + keys.map(k => `<td>${escapeHtml(row[k] || '')}</td>`).join('') + '</tr>';
            });
            html += '</tbody></table>';
        }
        if (table.data.length > 20) {
            html += `<div style="color: #888; font-size: 11px; margin-top: 4px;">\u2026 and ${table.data.length - 20} more rows</div>`;
        }
        html += '</div>';
    });
    return html;
}

// Initialize command palette
async function initCommandPalette() {
    // Wait for config to load before checking if palette is disabled
    await _configReady;

    // Check if command palette is disabled in config
    if (getConfig('advanced.command-palette', true) === false) {
        console.log('[CommandPalette] Disabled via config');
        const btn = document.getElementById('cmdPaletteBtn');
        if (btn) btn.style.display = 'none';
        return;
    }

    const ninja = document.getElementById('commandPalette');
    if (!ninja) {
        console.error('[CommandPalette] <ninja-keys> element not found in DOM');
        return;
    }

    // Wait for web component to be defined (5s timeout)
    const timeout = new Promise((_, reject) =>
        setTimeout(() => reject(new Error('ninja-keys not defined after 5s')), 5000)
    );
    try {
        await Promise.race([customElements.whenDefined('ninja-keys'), timeout]);
    } catch (err) {
        console.error('[CommandPalette]', err.message);
        return;
    }

    // Fetch Inspekt commands from registry API
    const registryData = await fetchRegistryCommands();
    const items = buildCommandPaletteData(registryData);

    // If registry failed, add a retry action
    if (!registryData) {
        items.push({
            id: 'meta:retry-load',
            title: 'Retry Loading Inspekt Commands',
            icon: '🔄',
            section: 'System',
            handler: async () => {
                const data = await fetchRegistryCommands();
                if (data) {
                    ninja.data = buildCommandPaletteData(data);
                    showToast(`Loaded ${Object.values(data.categories).flat().length} Inspekt commands`, 'success');
                } else {
                    showToast('Inspekt API not available', 'error');
                }
            },
        });
    }

    ninja.data = items;

    const uiCount = UI_COMMANDS.length;
    const pinnedCount = getPinnedCommandIds().length;
    const inspektCount = items.length - uiCount - pinnedCount;
    console.log(`[CommandPalette] Initialized: ${uiCount} UI + ${inspektCount} Inspekt` + (pinnedCount ? ` + ${pinnedCount} pinned` : '') + ` = ${items.length} total`);
}

// Initialize on DOM ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCommandPalette);
} else {
    setTimeout(initCommandPalette, 500);
}

// Refresh dynamic content (tab titles, counts) each time the palette opens.
// Monkey-patch ninja.open() to rebuild data before showing — Lit's `visible`
// is an internal @state() that doesn't reflect to attributes, so we can't
// use MutationObserver. This is the cleanest alternative.
{
    const ninja = document.getElementById('commandPalette');
    if (ninja) {
        customElements.whenDefined('ninja-keys').then(() => {
            const origOpen = ninja.open.bind(ninja);
            ninja.open = function(options) {
                ninja.data = buildCommandPaletteData(_registryData);
                return origOpen(options);
            };

            // Track the currently selected action for pinning
            let _paletteSelectedAction = null;
            ninja.addEventListener('change', (e) => {
                const actions = e.detail?.actions || [];
                const idx = ninja._selected ?? 0;
                _paletteSelectedAction = actions[idx] || null;
            });

            // Cmd/Ctrl+D to pin/unpin the selected command.
            // Listens on document because ninja-keys uses Shadow DOM —
            // keydown events from the internal input don't bubble to the host.
            document.addEventListener('keydown', (e) => {
                if (!ninja.visible) return;
                if (e.key === 'd' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (!_paletteSelectedAction) return;
                    // Resolve the real ID (strip "pinned:" prefix if selecting from Pinned section)
                    let actionId = _paletteSelectedAction.id;
                    if (actionId.startsWith('pinned:')) actionId = actionId.slice(7);
                    const wasPinned = togglePinCommand(actionId);
                    const title = _paletteSelectedAction.title;
                    showToast(wasPinned ? `Pinned: ${title}` : `Unpinned: ${title}`, 'success', 2000);
                    // Rebuild data to reflect pin change (palette stays open)
                    ninja.data = buildCommandPaletteData(_registryData);
                }
            });

            // Handle pin button clicks from ninja-action component
            ninja.addEventListener('togglePin', (e) => {
                const action = e.detail;
                if (!action) return;
                let actionId = action.id;
                if (actionId.startsWith('pinned:')) actionId = actionId.slice(7);
                const wasPinned = togglePinCommand(actionId);
                showToast(wasPinned ? `Pinned: ${action.title}` : `Unpinned: ${action.title}`, 'success', 2000);
                ninja.data = buildCommandPaletteData(_registryData);
            });
        });
    }
}
