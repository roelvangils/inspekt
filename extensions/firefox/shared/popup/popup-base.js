/**
 * Inspekt - Popup Script (Shared)
 *
 * Handles the settings panel UI and displays connection status
 * Works with both Chrome and Firefox (via browser adapters)
 */

// Browser API detection - works for both chrome and firefox
// IMPORTANT: Check for `browser` first since Firefox has a `chrome` object for compatibility
// but `browser` is the proper Firefox API with Promise support
const BrowserAPI = {
    // Get tabs API
    getTabs: async (query) => {
        const api = typeof browser !== 'undefined' ? browser : chrome;
        return await api.tabs.query(query);
    },

    // Get manifest
    getManifest: () => {
        const api = typeof browser !== 'undefined' ? browser : chrome;
        return api.runtime.getManifest();
    },

    // Reload tab
    reloadTab: async (tabId) => {
        const api = typeof browser !== 'undefined' ? browser : chrome;
        return await api.tabs.reload(tabId);
    },

    // Execute script in tab (browser-specific)
    executeScript: async (tabId, code) => {
        // Chrome (MV3) uses scripting.executeScript
        if (typeof chrome !== 'undefined' && chrome.scripting && chrome.scripting.executeScript) {
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

/**
 * Check if the Inspekt server is running by pinging the API
 * @returns {Promise<boolean>} true if server is responding
 */
async function checkServerRunning() {
    // Firefox popups have restricted network access - route through background script
    if (typeof browser !== 'undefined' && browser.runtime) {
        try {
            const response = await browser.runtime.sendMessage({ type: 'CHECK_SERVER_RUNNING' });
            return response && response.running === true;
        } catch (e) {
            console.warn('[Inspekt Popup] Background script check failed:', e.message);
            return false;
        }
    }

    // Chrome - direct fetch works fine
    try {
        const isVMBrowser = navigator.userAgent.includes('Linux') &&
                            (navigator.userAgent.includes('Chromium') ||
                             navigator.userAgent.includes('Chrome') ||
                             navigator.userAgent.includes('Firefox'));
        const port = isVMBrowser ? 8767 : 8765;

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        const response = await fetch(`http://127.0.0.1:${port}/health`, {
            method: 'GET',
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        return response.ok;
    } catch (e) {
        // Network error, timeout, or server not running
        return false;
    }
}

/**
 * Send a message to a tab's content script with a timeout
 * Firefox-specific helper since browser.tabs.sendMessage can hang indefinitely
 * @param {number} tabId - The tab ID to send to
 * @param {object} message - The message to send
 * @param {number} timeout - Timeout in milliseconds (default 3000)
 * @returns {Promise<any>} The response from the content script
 */
async function sendMessageWithTimeout(tabId, message, timeout = 3000) {
    const api = typeof browser !== 'undefined' ? browser : chrome;

    return Promise.race([
        api.tabs.sendMessage(tabId, message),
        new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Content script did not respond')), timeout)
        )
    ]);
}

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

    // Load CSP bypass status
    await loadCspBypassStatus();

    // Setup CSP bypass toggle handler
    setupCspBypassHandler();

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
        // Step 1: Check if the server is running
        const serverRunning = await checkServerRunning();

        if (!serverRunning) {
            setStatus(statusDot, statusText, 'disconnected',
                '❌ Server not running. Run: inspekt start');
            return;
        }

        // Step 2: Get active tab
        const tabs = await BrowserAPI.getTabs({ active: true, currentWindow: true });
        if (!tabs[0]) {
            setStatus(statusDot, statusText, 'disconnected', 'No active tab');
            return;
        }

        const tab = tabs[0];

        // Step 3: Check if content script is loaded and WebSocket is connected
        try {
            // For Chrome: use scripting.executeScript with MAIN world access
            if (typeof chrome !== 'undefined' && chrome.scripting) {
                const results = await chrome.scripting.executeScript({
                    target: { tabId: tab.id },
                    world: 'MAIN',
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
                } else {
                    setStatus(statusDot, statusText, 'checking',
                        '⏳ Initializing...');
                }
            }
            // For Firefox: use message passing to content script with timeout
            else if (typeof browser !== 'undefined' && browser.tabs) {
                console.log('[Inspekt Popup] Sending GET_WS_STATUS to tab:', tab.id);

                const response = await sendMessageWithTimeout(tab.id, {
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
                    // Response received but no status - content script is loading
                    console.warn('[Inspekt Popup] No valid status in response:', response);
                    setStatus(statusDot, statusText, 'checking',
                        '⏳ Extension loading...');
                }
            }
        } catch (error) {
            // Content script not available or didn't respond
            // But server IS running (we checked above)
            console.warn('[Inspekt Popup] Content script error:', error.message);
            setStatus(statusDot, statusText, 'disconnected',
                '⚠️ Extension not active on this page');
        }

    } catch (error) {
        // Unexpected error (e.g., tabs API failed)
        console.error('[Inspekt Popup] Unexpected error:', error);
        setStatus(statusDot, statusText, 'disconnected',
            '❌ Unable to check status');
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

// ============================================================================
// CSP BYPASS MANAGEMENT
// ============================================================================

async function loadCspBypassStatus() {
    const toggle = document.getElementById('csp-bypass-toggle');
    const domainSpan = document.getElementById('csp-current-domain');
    const messageDiv = document.getElementById('csp-bypass-message');

    try {
        // Get current tab
        const tabs = await BrowserAPI.getTabs({ active: true, currentWindow: true });
        if (!tabs[0] || !tabs[0].url.startsWith('http')) {
            // Hide CSP section for non-http pages
            document.querySelector('.csp-bypass').style.display = 'none';
            return;
        }

        const tab = tabs[0];
        const url = new URL(tab.url);
        const currentDomain = url.hostname;

        // Update domain display
        domainSpan.textContent = currentDomain;

        // Check if CSP bypass is enabled for this domain
        const api = typeof chrome !== 'undefined' ? chrome : browser;
        const response = await api.runtime.sendMessage({
            type: 'CSP_BYPASS_STATUS',
            domain: currentDomain
        });

        if (response && response.ok) {
            toggle.checked = response.enabled;

            if (response.enabled) {
                messageDiv.textContent = 'CSP bypass is active. Refresh the page if issues persist.';
                messageDiv.classList.remove('hidden');
                messageDiv.classList.add('success');
            } else {
                messageDiv.classList.add('hidden');
            }
        }
    } catch (error) {
        console.error('[Inspekt Popup] Error loading CSP bypass status:', error);
    }
}

function setupCspBypassHandler() {
    const toggle = document.getElementById('csp-bypass-toggle');
    const messageDiv = document.getElementById('csp-bypass-message');

    toggle.addEventListener('change', async (e) => {
        const enabled = e.target.checked;

        try {
            // Get current tab
            const tabs = await BrowserAPI.getTabs({ active: true, currentWindow: true });
            if (!tabs[0]) return;

            const tab = tabs[0];
            const url = new URL(tab.url);
            const currentDomain = url.hostname;

            const api = typeof chrome !== 'undefined' ? chrome : browser;

            if (enabled) {
                // Enable CSP bypass
                const response = await api.runtime.sendMessage({
                    type: 'CSP_BYPASS_ENABLE',
                    domain: currentDomain
                });

                if (response && response.ok) {
                    messageDiv.textContent = response.message;
                    messageDiv.classList.remove('hidden', 'error');
                    messageDiv.classList.add('success');
                } else {
                    messageDiv.textContent = response?.error || 'Failed to enable CSP bypass';
                    messageDiv.classList.remove('hidden', 'success');
                    messageDiv.classList.add('error');
                    toggle.checked = false;
                }
            } else {
                // Disable CSP bypass
                const response = await api.runtime.sendMessage({
                    type: 'CSP_BYPASS_DISABLE',
                    domain: currentDomain
                });

                if (response && response.ok) {
                    messageDiv.textContent = response.message;
                    messageDiv.classList.remove('hidden', 'error');
                    messageDiv.classList.add('success');
                } else {
                    messageDiv.textContent = response?.error || 'Failed to disable CSP bypass';
                    messageDiv.classList.remove('hidden', 'success');
                    messageDiv.classList.add('error');
                    toggle.checked = true;
                }
            }

        } catch (error) {
            console.error('[Inspekt Popup] Error toggling CSP bypass:', error);
            messageDiv.textContent = 'Error: ' + error.message;
            messageDiv.classList.remove('hidden', 'success');
            messageDiv.classList.add('error');
        }
    });
}
