// =============================================
// Plugin Dropdown
// =============================================

let pluginDropdownOpen = false;
let pluginsCache = [];
const loadedPlugins = new Set();
const enabledProxyPlugins = new Set();

const PUZZLE_OUTLINE_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.611 1.611a2.404 2.404 0 0 1-1.704.706 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.16 8.74c.24-.24.33-.59.274-.862-.058-.284-.27-.546-.535-.728a2.5 2.5 0 1 1 3.258-3.258c.18.264.443.477.728.535.272.056.621-.034.862-.274l1.557-1.557c.47-.47 1.088-.706 1.704-.706.617 0 1.234.236 1.704.706l1.568 1.568c.23.23.556.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02Z"/></svg>';
const PUZZLE_FILLED_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" stroke="none"><path d="M19.439 7.85c-.049.322.059.648.289.878l1.568 1.568c.47.47.706 1.087.706 1.704s-.235 1.233-.706 1.704l-1.611 1.611a.98.98 0 0 1-.837.276c-.47-.07-.802-.48-.968-.925a2.501 2.501 0 1 0-3.214 3.214c.446.166.855.497.925.968a.979.979 0 0 1-.276.837l-1.611 1.611a2.404 2.404 0 0 1-1.704.706 2.402 2.402 0 0 1-1.704-.706l-1.568-1.568a1.026 1.026 0 0 0-.877-.29c-.493.074-.84.504-1.02.968a2.5 2.5 0 1 1-3.237-3.237c.464-.18.894-.527.967-1.02a1.026 1.026 0 0 0-.289-.877l-1.568-1.568A2.402 2.402 0 0 1 1.998 12c0-.617.236-1.234.706-1.704L4.16 8.74c.24-.24.33-.59.274-.862-.058-.284-.27-.546-.535-.728a2.5 2.5 0 1 1 3.258-3.258c.18.264.443.477.728.535.272.056.621-.034.862-.274l1.557-1.557c.47-.47 1.088-.706 1.704-.706.617 0 1.234.236 1.704.706l1.568 1.568c.23.23.556.338.877.29.493-.074.84-.504 1.02-.968a2.5 2.5 0 1 1 3.237 3.237c-.464.18-.894.527-.967 1.02Z"/></svg>';
const PLUGIN_PLAY_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';
const PLUGIN_UNLOAD_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>';
const PLUGIN_EDIT_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>';
const PLUGIN_CONFIG_SVG = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

function togglePluginDropdown() {
    if (pluginDropdownOpen) {
        closePluginDropdown();
    } else {
        openPluginDropdown();
    }
}

async function openPluginDropdown() {
    openPopout('pluginDropdown', 'urlBarPluginIcon', closePluginDropdown);
    pluginDropdownOpen = true;

    const list = document.getElementById('pluginList');
    list.innerHTML = '<div class="plugin-empty">Loading…</div>';

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins`);
        const data = await response.json();
        if (data.ok) {
            pluginsCache = data.plugins || [];
            // Sync proxy enabled state from proxy status endpoint
            await _syncProxyEnabledState();
            renderPluginList();
            updatePluginIconState();
        } else {
            list.innerHTML = '<div class="plugin-empty">Failed to load plugins</div>';
        }
    } catch (e) {
        list.innerHTML = '<div class="plugin-empty">Connection error</div>';
    }
}

async function _syncProxyEnabledState() {
    // Read the mitmproxy config to know which proxy scripts are currently enabled
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/proxy/status`);
        const status = await resp.json();
        enabledProxyPlugins.clear();
        if (status.ok && status.active_scripts) {
            status.active_scripts.forEach(s => enabledProxyPlugins.add(s));
        }
    } catch (e) { /* ignore */ }
}

function closePluginDropdown() {
    dismissActivePopout();
    pluginDropdownOpen = false;
}

function renderPluginList() {
    const list = document.getElementById('pluginList');
    if (pluginsCache.length === 0) {
        list.innerHTML = '<div class="plugin-empty">No plugins yet.<br>Click "Manage" to add some.</div>';
        return;
    }

    const proxyPlugins = pluginsCache.filter(p => p.engine === 'proxy');
    const jsPlugins = pluginsCache.filter(p => p.engine !== 'proxy');

    let html = '';

    // Proxy section
    if (proxyPlugins.length > 0) {
        html += '<div class="plugin-section-header">Proxy</div>';
        html += proxyPlugins.map(p => _renderProxyRow(p)).join('');
    }

    // JS section
    if (jsPlugins.length > 0) {
        html += '<div class="plugin-section-header">JavaScript</div>';
        html += jsPlugins.map(p => _renderJsRow(p)).join('');
    }

    list.innerHTML = html;
}

function _renderProxyRow(p) {
    const isEnabled = enabledProxyPlugins.has(p.code);
    const desc = p.description ? p.description.replace(/"/g, '&quot;') : p.name;
    const hasConfig = p.proxy_config && Object.keys(p.proxy_config).length > 0;
    const configJson = JSON.stringify(p.proxy_config || {}, null, 2);
    return `<div class="plugin-row" data-plugin-id="${p.id}">
        <button class="plugin-autorun-toggle"
                role="switch"
                aria-checked="${isEnabled}"
                aria-label="Toggle ${p.name.replace(/"/g, '&quot;')}"
                title="${isEnabled ? 'Disable' : 'Enable'} proxy script"
                onclick="toggleProxyPlugin('${p.id}')"></button>
        <span class="plugin-name" title="${desc}">${p.name}</span>
        <button class="plugin-action-btn config-btn ${hasConfig ? 'has-config' : ''}"
                aria-label="Configure ${p.name.replace(/"/g, '&quot;')}"
                title="Configure"
                onclick="toggleProxyConfig('${p.id}')">${PLUGIN_CONFIG_SVG}</button>
    </div>
    <div class="plugin-config-inline" id="config-${p.id}">
        <textarea id="config-textarea-${p.id}" spellcheck="false">${configJson}</textarea>
        <div class="config-actions">
            <button onclick="toggleProxyConfig('${p.id}')">Cancel</button>
            <button class="apply" onclick="applyProxyConfig('${p.id}')">Apply</button>
        </div>
    </div>`;
}

function _renderJsRow(p) {
    const isLoaded = loadedPlugins.has(p.id);
    const canUnload = isLoaded && p.unload_mode && p.unload_mode !== 'none';
    const runCountHtml = p.run_count > 0 ? `<span class="plugin-run-count">×${p.run_count}</span>` : '';
    const desc = p.description ? p.description.replace(/"/g, '&quot;') : p.name;
    return `<div class="plugin-row" data-plugin-id="${p.id}">
        <button class="plugin-autorun-toggle"
                role="switch"
                aria-checked="${!!p.autorun}"
                aria-label="Autorun ${p.name.replace(/"/g, '&quot;')}"
                title="Auto-run on page load"
                onclick="togglePluginAutorun('${p.id}')"></button>
        <span class="plugin-name" title="${desc}">${p.name}${runCountHtml}</span>
        ${canUnload
            ? `<button class="plugin-action-btn unload-btn" aria-label="Unload ${p.name.replace(/"/g, '&quot;')}" title="Unload" onclick="unloadPlugin('${p.id}')">${PLUGIN_UNLOAD_SVG}</button>`
            : `<button class="plugin-action-btn run-btn" aria-label="Run ${p.name.replace(/"/g, '&quot;')}" title="Run" onclick="runPlugin('${p.id}')">${PLUGIN_PLAY_SVG}</button>`
        }
        <button class="plugin-action-btn" aria-label="Edit ${p.name.replace(/"/g, '&quot;')}" title="Edit" onclick="editPlugin('${p.id}')">${PLUGIN_EDIT_SVG}</button>
    </div>`;
}

function updatePluginIconState() {
    const icon = document.getElementById('urlBarPluginIcon');
    if (!icon) return;
    const hasAutorun = pluginsCache.some(p => p.engine !== 'proxy' && p.autorun);
    const hasEnabledProxy = enabledProxyPlugins.size > 0;
    const isActive = hasAutorun || hasEnabledProxy;
    icon.classList.toggle('has-autorun', isActive);
    icon.innerHTML = isActive ? PUZZLE_FILLED_SVG : PUZZLE_OUTLINE_SVG;
}

async function toggleProxyPlugin(pluginId) {
    const plugin = pluginsCache.find(p => p.id === pluginId);
    if (!plugin) return;

    const isEnabled = enabledProxyPlugins.has(plugin.code);
    const endpoint = isEnabled ? 'unload' : 'run';
    // Auto-scope to current tab's domain
    const currentDomain = _getCurrentDomain();
    const domainParam = (!isEnabled && currentDomain) ? `?domain=${encodeURIComponent(currentDomain)}` : '';

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/${pluginId}/${endpoint}${domainParam}`, { method: 'POST' });
        const data = await response.json();

        if (data.ok) {
            if (isEnabled) {
                enabledProxyPlugins.delete(plugin.code);
                showToast(`${plugin.name} disabled`, 'success');
            } else {
                enabledProxyPlugins.add(plugin.code);
                const scopeMsg = currentDomain ? ` on ${currentDomain}` : '';
                showToast(`${plugin.name} enabled${scopeMsg}`, 'success');
            }
            renderPluginList();
            updatePluginIconState();
        } else {
            showToast(`✗ ${plugin.name}: ${data.error || data.detail || 'failed'}`, 'error');
        }
    } catch (e) {
        showToast('Failed to toggle proxy plugin', 'error');
    }
}

function _getCurrentDomain() {
    try {
        const urlBar = document.getElementById('urlBar');
        if (urlBar && urlBar.value) {
            const url = new URL(urlBar.value);
            return url.hostname;
        }
    } catch (e) { }
    return '';
}

function toggleProxyConfig(pluginId) {
    const panel = document.getElementById(`config-${pluginId}`);
    if (panel) panel.classList.toggle('open');
}

async function applyProxyConfig(pluginId) {
    const textarea = document.getElementById(`config-textarea-${pluginId}`);
    if (!textarea) return;

    let newConfig;
    try {
        newConfig = JSON.parse(textarea.value);
    } catch (e) {
        showToast('Invalid JSON', 'error');
        return;
    }

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/${pluginId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ proxy_config: newConfig })
        });
        const data = await response.json();
        if (data.ok) {
            // Update cache
            const plugin = pluginsCache.find(p => p.id === pluginId);
            if (plugin) plugin.proxy_config = newConfig;
            toggleProxyConfig(pluginId);
            showToast('Config updated', 'success');

            // If the proxy script is currently enabled, re-enable it with new config
            if (plugin && enabledProxyPlugins.has(plugin.code)) {
                const currentDomain = _getCurrentDomain();
                const domainParam = currentDomain ? `?domain=${encodeURIComponent(currentDomain)}` : '';
                await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/${pluginId}/run${domainParam}`, { method: 'POST' });
            }
        } else {
            showToast(`Failed: ${data.error || data.detail || 'unknown error'}`, 'error');
        }
    } catch (e) {
        showToast('Failed to update config', 'error');
    }
}

async function runPlugin(pluginId) {
    const row = document.querySelector(`.plugin-row[data-plugin-id="${pluginId}"]`);
    const btn = row ? row.querySelector('.run-btn') : null;
    if (btn) btn.classList.add('loading');

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/${pluginId}/run?capture_console=true`, { method: 'POST' });
        const data = await response.json();
        const plugin = pluginsCache.find(p => p.id === pluginId);
        const name = plugin ? plugin.name : pluginId;

        if (data.ok) {
            if (plugin && plugin.unload_mode && plugin.unload_mode !== 'none') {
                loadedPlugins.add(pluginId);
            }
            if (plugin) plugin.run_count = (plugin.run_count || 0) + 1;
            renderPluginList();

            const timeMs = data.execution_time_ms || 0;
            showToast(`✓ ${name} executed in ${timeMs}ms`, 'success');

            if (data.console_output && data.console_output.length > 0) {
                const logs = data.console_output.filter(e => e.level === 'log');
                const toShow = logs.slice(0, 3);
                toShow.forEach((entry, i) => {
                    setTimeout(() => showToast(entry.text, '', 4000), (i + 1) * 500);
                });
                if (logs.length > 3) {
                    setTimeout(() => showToast(`…and ${logs.length - 3} more log entries`, '', 3000), 2000);
                }
            }
        } else {
            showToast(`✗ ${name}: ${data.error || 'execution failed'}`, 'error');
        }
    } catch (e) {
        showToast('Plugin execution failed', 'error');
    }

    if (btn) btn.classList.remove('loading');
}

async function unloadPlugin(pluginId) {
    const row = document.querySelector(`.plugin-row[data-plugin-id="${pluginId}"]`);
    const btn = row ? row.querySelector('.unload-btn') : null;
    if (btn) btn.classList.add('loading');

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/${pluginId}/unload?capture_console=true`, { method: 'POST' });
        const data = await response.json();
        const plugin = pluginsCache.find(p => p.id === pluginId);
        const name = plugin ? plugin.name : pluginId;

        if (data.ok) {
            loadedPlugins.delete(pluginId);
            renderPluginList();
            showToast(`${name} unloaded`, 'success');
        } else {
            showToast(`✗ ${name}: ${data.error || 'unload failed'}`, 'error');
        }
    } catch (e) {
        showToast('Plugin unload failed', 'error');
    }

    if (btn) btn.classList.remove('loading');
}

async function togglePluginAutorun(pluginId) {
    const plugin = pluginsCache.find(p => p.id === pluginId);
    if (!plugin) return;

    const newState = !plugin.autorun;
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/plugins/${pluginId}/autorun`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: newState })
        });
        const data = await response.json();
        if (data.ok) {
            plugin.autorun = newState;
            renderPluginList();
            updatePluginIconState();
            showToast(`${plugin.name} autorun ${newState ? 'enabled' : 'disabled'}`, 'success');
        } else {
            showToast(`Failed to toggle autorun: ${data.error || data.detail || 'unknown error'}`, 'error');
        }
    } catch (e) {
        showToast('Failed to toggle autorun', 'error');
    }
}

function editPlugin(pluginId) {
    navigateTo(`http://inspekt/plugins?id=${pluginId}`);
    closePluginDropdown();
}

function openPluginManager() {
    navigateTo('http://inspekt/plugins');
    closePluginDropdown();
}

