/**
 * Inspekt - Popup Script (Chrome)
 *
 * Handles the settings panel UI and displays connection status
 */

document.addEventListener('DOMContentLoaded', async () => {
    // Display version
    const manifest = chrome.runtime.getManifest();
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
        // Get active tab
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tabs[0]) {
            setStatus(statusDot, statusText, 'disconnected', 'No active tab');
            return;
        }

        const tab = tabs[0];

        // Try to check if content script is loaded and WebSocket is connected
        // Must check in MAIN world where these variables are set
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
                    '<span class="material-icons md-inline">check</span> Connected to localhost:8766');
            } else if (status === 'loaded') {
                setStatus(statusDot, statusText, 'checking',
                    'Extension loaded, connecting to server…');
            } else {
                setStatus(statusDot, statusText, 'checking',
                    'Extension loading…');
            }
        } else {
            setStatus(statusDot, statusText, 'checking',
                'Initializing…');
        }

    } catch (error) {
        console.error('[Inspekt Popup] Error checking status:', error);
        setStatus(statusDot, statusText, 'disconnected',
            'Server not running. Run: inspekt start');
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
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
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
                    ${isCurrentAllowed ? '<span class="material-icons md-inline">check</span> Allowed' : '<span class="material-icons md-inline">close</span> Not Allowed'}
                </span>
            </div>
            ${!isCurrentAllowed ? `
                <button id="allow-current-btn"><span class="material-icons md-18">bolt</span> Allow This Domain</button>
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
                chrome.tabs.reload(tab.id);
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
    const cspSection = document.querySelector('.csp-bypass');

    try {
        // Get current tab
        const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
        if (!tabs[0] || !tabs[0].url || !tabs[0].url.startsWith('http')) {
            // Hide CSP section for non-http pages
            if (cspSection) cspSection.style.display = 'none';
            return;
        }

        const tab = tabs[0];
        const url = new URL(tab.url);
        const currentDomain = url.hostname;

        // Update domain display
        domainSpan.textContent = currentDomain;

        // Check if CSP bypass is enabled for this domain
        const response = await chrome.runtime.sendMessage({
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

    if (!toggle) return;

    toggle.addEventListener('change', async (e) => {
        const enabled = e.target.checked;

        try {
            // Get current tab
            const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
            if (!tabs[0]) return;

            const tab = tabs[0];
            const url = new URL(tab.url);
            const currentDomain = url.hostname;

            if (enabled) {
                // Enable CSP bypass
                const response = await chrome.runtime.sendMessage({
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
                const response = await chrome.runtime.sendMessage({
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
