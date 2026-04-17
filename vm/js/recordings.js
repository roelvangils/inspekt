// =============================================
// Recordings Modal Functions
// =============================================

// Open recordings modal
function openRecordingsModal() {
    document.getElementById('recordingsModalOverlay').classList.add('open');
    loadRecordings();
}

// Close recordings modal
function closeRecordingsModal() {
    document.getElementById('recordingsModalOverlay').classList.remove('open');
}

// Load recordings list
async function loadRecordings() {
    const container = document.getElementById('recordingsList');

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/recordings`);
        const data = await response.json();

        if (!data.ok || !data.recordings || data.recordings.length === 0) {
            container.innerHTML = `
                <div class="recordings-empty">
                    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="4" fill="currentColor"/></svg>
                    <p>No recordings yet</p>
                    <small>Use <code>inspekt record</code> to create recordings</small>
                </div>
            `;
            return;
        }

        container.innerHTML = data.recordings.map(r => {
            const duration = formatDuration(r.duration_ms);
            const date = formatDate(r.created_at);
            const url = r.url.replace(/^https?:\/\//, '').substring(0, 30);

            return `
                <div class="recording-item">
                    <div class="recording-info">
                        <div class="recording-name">${escapeHtml(r.name)}</div>
                        <div class="recording-meta">${date} • ${duration} • ${r.steps} steps • ${url}</div>
                    </div>
                    <span class="recording-badge">${r.steps}</span>
                    <button class="recording-btn download" onclick="downloadRecording('${escapeHtml(r.name)}')">Download</button>
                    <button class="recording-btn delete" onclick="deleteRecording('${escapeHtml(r.name)}')">Delete</button>
                </div>
            `;
        }).join('');
    } catch (e) {
        console.error('[Recordings] Failed to load:', e);
        container.innerHTML = `
            <div class="recordings-empty">
                <p>Failed to load recordings</p>
                <small>${e.message}</small>
            </div>
        `;
    }
}

// Format duration in ms to human readable
function formatDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    const minutes = Math.floor(ms / 60000);
    const seconds = Math.floor((ms % 60000) / 1000);
    return `${minutes}m ${seconds}s`;
}

// Format date string
function formatDate(dateStr) {
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch (e) {
        return dateStr ? dateStr.substring(0, 10) : 'N/A';
    }
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Download single recording
function downloadRecording(name) {
    const url = `http://${VNC_HOST}:${CONTROL_PORT}/recordings/${encodeURIComponent(name)}/download`;
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast(`Downloading ${name}`);
}

// Download all recordings as ZIP
function downloadAllRecordings() {
    const url = `http://${VNC_HOST}:${CONTROL_PORT}/recordings/download-all`;
    const a = document.createElement('a');
    a.href = url;
    a.download = 'inspekt-recordings.zip';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    showToast('Downloading all recordings as ZIP');
}

// Delete recording
async function deleteRecording(name) {
    if (!confirm(`Delete recording "${name}"?`)) return;

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/recordings/${encodeURIComponent(name)}/delete`);
        const data = await response.json();

        if (data.ok) {
            showToast(`Deleted ${name}`);
            loadRecordings();
        } else {
            showToast(`Failed to delete: ${data.error}`);
        }
    } catch (e) {
        showToast(`Error: ${e.message}`);
    }
}

// Perform soft restart (supervisorctl restart all)
// Tier 1: Restart just the browser (Chromium).
// VNC stays connected, terminal stays open, proxy keeps running.
async function performRestartBrowser() {
    const keepTabs = document.getElementById('keepTabsCheckbox').checked;
    if (keepTabs) saveTabsToStorage();

    closeRestartModal();
    showToast('Restarting browser…');

    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/restart-browser`);
    } catch (e) { /* expected */ }

    // Browser restart is quick — just poll for CDP to come back
    let attempts = 0;
    const interval = setInterval(async () => {
        attempts++;
        try {
            const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs`, {
                signal: AbortSignal.timeout(2000)
            });
            if (resp.ok) {
                clearInterval(interval);
                showToast('Browser restarted', 'success');
                // Re-fetch tabs and restore if needed
                await fetchTabs();
                if (keepTabs) await restoreTabsFromStorage();
            }
        } catch {
            if (attempts >= 15) {
                clearInterval(interval);
                showToast('Browser restart timed out — try Restart All Services', 'error');
            }
        }
    }, 1000);
}

// Tier 2: Restart all services (VNC, browser, proxy, terminal).
// VNC disconnects briefly, then auto-reconnects.
async function performRestartAll() {
    const keepTabs = document.getElementById('keepTabsCheckbox').checked;
    if (keepTabs) saveTabsToStorage();

    closeRestartModal();
    showToast('Restarting all services…');
    updateStatus(false);

    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/reboot`);
    } catch (e) { /* expected — connection drops */ }

    pollForReconnection();
}

// Tier 3: Reset the entire environment (container restart).
// Fresh Chromium profile, no cookies/cache/history.
// Plugins and bind-mounted data survive.
async function performResetEnvironment() {
    const keepTabs = document.getElementById('keepTabsCheckbox').checked;
    if (keepTabs) saveTabsToStorage();

    closeRestartModal();
    showToast('Resetting environment... This may take ~10 seconds.');
    updateStatus(false);

    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/hard-reboot`);
    } catch (e) { /* expected — connection drops */ }

    pollForReconnection();
}

// Poll for server reconnection after restart
function pollForReconnection() {
    let attempts = 0;
    const maxAttempts = 60; // 60 seconds timeout

    const interval = setInterval(async () => {
        attempts++;
        try {
            const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/tabs`, {
                signal: AbortSignal.timeout(2000)
            });
            if (resp.ok) {
                clearInterval(interval);
                showToast('Environment restarted!', 'success');
                // Reload page to reinitialize VNC connection
                setTimeout(() => location.reload(), 500);
            }
        } catch (e) {
            // Still down, keep polling
            if (attempts >= maxAttempts) {
                clearInterval(interval);
                showToast('Restart timeout - please refresh manually', 'error');
            }
        }
    }, 1000);
}

// Toggle fullscreen
function toggleFullscreen() {
    const container = document.getElementById('vncContainer');

    if (document.fullscreenElement) {
        document.exitFullscreen();
    } else {
        container.requestFullscreen();
    }
}

// Check health periodically
async function checkHealth() {
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/health`, {
            signal: AbortSignal.timeout(2000)
        });
        if (response.ok) {
            if (!isConnected) updateStatus(true);
        }
    } catch {
        if (isConnected) updateStatus(false);
    }
}

