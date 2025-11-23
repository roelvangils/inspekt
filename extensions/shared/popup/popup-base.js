/**
 * Inspekt - Popup Script (Shared)
 *
 * Handles the settings panel UI and displays connection status
 * Works with both Chrome and Firefox (via browser adapters)
 */

// Browser API detection - works for both chrome and firefox
const BrowserAPI = {
    // Get tabs API
    getTabs: async (query) => {
        const api = typeof chrome !== 'undefined' ? chrome : browser;
        return await api.tabs.query(query);
    },

    // Get manifest
    getManifest: () => {
        const api = typeof chrome !== 'undefined' ? chrome : browser;
        return api.runtime.getManifest();
    },

    // Reload tab
    reloadTab: async (tabId) => {
        const api = typeof chrome !== 'undefined' ? chrome : browser;
        return await api.tabs.reload(tabId);
    },

    // Execute script in tab (browser-specific)
    executeScript: async (tabId, code) => {
        const api = typeof chrome !== 'undefined' ? chrome : browser;

        // Chrome (MV3) uses scripting.executeScript
        if (typeof chrome !== 'undefined' && chrome.scripting) {
            return await chrome.scripting.executeScript({
                target: { tabId: tabId },
                func: new Function(code)
            });
        }

        // Firefox (MV2) uses tabs.executeScript with code string
        if (typeof browser !== 'undefined' && browser.tabs) {
            return await browser.tabs.executeScript(tabId, {
                code: `(function() { ${code} })()`
            });
        }

        throw new Error('Unable to execute script: no browser API available');
    }
};

document.addEventListener('DOMContentLoaded', async () => {
    // Display version
    const manifest = BrowserAPI.getManifest();
    document.getElementById('version').textContent = `v${manifest.version}`;

    // Load allowed domains
    await loadAllowedDomains();

    // Load temp bypass status
    await loadTempBypassStatus();

    // Setup temp bypass dropdown handler
    setupTempBypassHandler();

    // Check connection status
    await checkConnectionStatus();

    // Refresh status every 5 seconds
    setInterval(checkConnectionStatus, 5000);

    // Refresh temp bypass status every 10 seconds
    setInterval(loadTempBypassStatus, 10000);
});

async function checkConnectionStatus() {
    const statusDot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    try {
        // Get active tab
        const tabs = await BrowserAPI.getTabs({ active: true, currentWindow: true });
        if (!tabs[0]) {
            setStatus(statusDot, statusText, 'disconnected', 'No active tab');
            return;
        }

        const tab = tabs[0];

        // Check if content script is loaded and WebSocket is connected
        try {
            const api = typeof chrome !== 'undefined' ? chrome : browser;

            // For Chrome: use scripting.executeScript
            if (typeof chrome !== 'undefined' && chrome.scripting) {
                const results = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    func: () => {
                        return (window.__INSPEKT_WS_CONNECTED__ === true) ? 'connected' :
                               (window.__INSPEKT_BRIDGE_EXTENSION__ ? 'loaded' : 'not-loaded');
                    }
                });

                if (results && results[0]) {
                    const status = results[0].result;

                    if (status === 'connected') {
                        setStatus(statusDot, statusText, 'connected',
                            '✅ Connected to localhost:8766');
                    } else if (status === 'loaded') {
                        setStatus(statusDot, statusText, 'checking',
                            '⏳ Extension loaded, connecting to server...');
                    } else {
                        setStatus(statusDot, statusText, 'checking',
                            '⏳ Extension loading...');
                    }
                }
            }
            // For Firefox: use message passing to content script
            else if (typeof browser !== 'undefined' && browser.tabs) {
                console.log('[Inspekt Popup] Sending GET_WS_STATUS to tab:', tab.id);
                const response = await browser.tabs.sendMessage(tab.id, {
                    type: 'GET_WS_STATUS'
                });
                console.log('[Inspekt Popup] Received status response:', response);

                if (response && response.status) {
                    const status = response.status;

                    if (status === 'connected') {
                        setStatus(statusDot, statusText, 'connected',
                            '✅ Connected to localhost:8766');
                    } else if (status === 'loaded') {
                        setStatus(statusDot, statusText, 'checking',
                            '⏳ Extension loaded, connecting to server...');
                    } else {
                        setStatus(statusDot, statusText, 'checking',
                            '⏳ Extension loading...');
                    }
                } else {
                    console.warn('[Inspekt Popup] No valid status in response:', response);
                }
            }
        } catch (error) {
            // Script execution failed - likely the tab doesn't allow content scripts
            setStatus(statusDot, statusText, 'disconnected',
                '❌ Extension not available on this page');
        }

    } catch (error) {
        console.error('[Inspekt Popup] Error checking status:', error);
        setStatus(statusDot, statusText, 'disconnected',
            '❌ Server not running. Run: inspekt server start');
    }
}

function setStatus(dot, text, status, message) {
    // Remove all status classes
    dot.classList.remove('connected', 'disconnected');
    text.classList.remove('connected', 'disconnected');

    // Add appropriate class
    if (status === 'connected') {
        dot.classList.add('connected');
        text.classList.add('connected');
    } else if (status === 'disconnected') {
        dot.classList.add('disconnected');
        text.classList.add('disconnected');
    }
    // 'checking' uses default animation

    text.innerHTML = message;
}

async function loadAllowedDomains() {
    const currentDomainStatus = document.getElementById('current-domain-status');
    const domainsList = document.getElementById('allowed-domains-list');

    try {
        // Get current tab
        const tabs = await BrowserAPI.getTabs({ active: true, currentWindow: true });
        if (!tabs[0]) return;

        const tab = tabs[0];
        const url = new URL(tab.url);
        const currentDomain = url.hostname;

        // Get allowed domains (now returns object with metadata)
        const allowedDomainsObj = await InspektPermissions.getAllowedDomains();
        const allowedDomainsList = Object.keys(allowedDomainsObj);

        // Check if current domain is allowed (using subdomain matching)
        const isCurrentAllowed = await InspektPermissions.isAllowed(currentDomain);

        // Show current domain status
        currentDomainStatus.innerHTML = `
            <div>
                <div class="domain-name">Current: ${currentDomain}</div>
                <span class="domain-badge ${isCurrentAllowed ? 'allowed' : 'denied'}">
                    ${isCurrentAllowed ? '✅ Allowed' : '❌ Not Allowed'}
                </span>
            </div>
            ${!isCurrentAllowed ? `
                <button id="allow-current-btn">⚡ Allow This Domain</button>
            ` : `
                <button id="remove-current-btn" class="remove">Remove</button>
            `}
        `;

        // Add event listener for current domain button
        if (!isCurrentAllowed) {
            document.getElementById('allow-current-btn').addEventListener('click', async () => {
                await InspektPermissions.allowDomain(currentDomain);
                await loadAllowedDomains();
                // Reload the tab to trigger connection
                await BrowserAPI.reloadTab(tab.id);
            });
        } else {
            document.getElementById('remove-current-btn').addEventListener('click', async () => {
                await InspektPermissions.removeDomain(currentDomain);
                await loadAllowedDomains();
            });
        }

        // Show all allowed domains (except current)
        const otherDomains = allowedDomainsList.filter(d => d !== currentDomain);

        if (otherDomains.length === 0) {
            domainsList.innerHTML = '<div class="no-domains">No other domains allowed</div>';
        } else {
            domainsList.innerHTML = otherDomains.map(domain => {
                const metadata = allowedDomainsObj[domain];
                const addedDate = metadata && metadata.addedAt
                    ? new Date(metadata.addedAt).toLocaleDateString()
                    : 'Unknown';

                return `
                    <div class="domain-item">
                        <div class="domain-info">
                            <span class="domain-name">${domain}</span>
                            <span class="domain-date">Added: ${addedDate}</span>
                        </div>
                        <button class="remove-domain-btn" data-domain="${domain}">Remove</button>
                    </div>
                `;
            }).join('');

            // Add remove listeners
            document.querySelectorAll('.remove-domain-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    const domain = e.target.getAttribute('data-domain');
                    await InspektPermissions.removeDomain(domain);
                    await loadAllowedDomains();
                });
            });
        }

    } catch (error) {
        console.error('[Inspekt Popup] Error loading domains:', error);
        currentDomainStatus.innerHTML = '<div class="no-domains">Unable to load domain information</div>';
    }
}

async function loadTempBypassStatus() {
    const bypassStatus = document.getElementById('temp-bypass-status');
    const bypassRemaining = document.getElementById('bypass-remaining');
    const bypassDropdown = document.getElementById('temp-bypass-duration');

    try {
        const status = await InspektPermissions.getTempBypassStatus();

        if (status.enabled) {
            // Show countdown
            bypassStatus.classList.remove('hidden');
            bypassRemaining.textContent = `${status.remainingMinutes} min`;

            // Select the appropriate option (or closest match)
            const closestOption = [60, 30, 15, 5].find(val => val >= status.remainingMinutes) || 5;
            bypassDropdown.value = closestOption.toString();
        } else {
            // Hide countdown
            bypassStatus.classList.add('hidden');
            bypassDropdown.value = '0';
        }
    } catch (error) {
        console.error('[Inspekt Popup] Error loading temp bypass status:', error);
        bypassStatus.classList.add('hidden');
    }
}

function setupTempBypassHandler() {
    const bypassDropdown = document.getElementById('temp-bypass-duration');

    bypassDropdown.addEventListener('change', async (e) => {
        const minutes = parseInt(e.target.value);

        try {
            await InspektPermissions.setTempBypass(minutes);
            await loadTempBypassStatus();

            // Show visual feedback
            if (minutes > 0) {
                console.log(`[Inspekt] Temp bypass enabled for ${minutes} minutes`);
            } else {
                console.log('[Inspekt] Temp bypass disabled');
            }
        } catch (error) {
            console.error('[Inspekt Popup] Error setting temp bypass:', error);
        }
    });
}
