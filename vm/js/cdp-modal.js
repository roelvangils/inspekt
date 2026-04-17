// =============================================
// CDP Setup Modal
// =============================================

function openCdpModal() {
    const overlay = document.getElementById('cdpModalOverlay');
    overlay.classList.add('open');
    fetchCdpConnectionInfo();
}

function closeCdpModal() {
    const overlay = document.getElementById('cdpModalOverlay');
    overlay.classList.remove('open');
}

async function fetchCdpConnectionInfo() {
    const wsUrlElement = document.getElementById('cdpWebSocketUrl');
    const hostPortElement = document.getElementById('cdpHostPort');

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/devtools/connection-info`);
        const data = await response.json();

        if (data.ok) {
            cdpConnectionInfo = data;

            // Update WebSocket URL (replace localhost with actual host for external access)
            if (data.primary_ws_url) {
                const externalWsUrl = data.primary_ws_url.replace('localhost', VNC_HOST);
                wsUrlElement.textContent = externalWsUrl;
            } else {
                wsUrlElement.textContent = 'No debuggable page found';
            }

            // Update host:port display
            hostPortElement.textContent = `${VNC_HOST}:${data.cdp_port}`;
        } else {
            wsUrlElement.textContent = 'Error: ' + (data.error || 'Unknown error');
        }
    } catch (e) {
        wsUrlElement.textContent = 'Error: Failed to fetch connection info';
        console.error('[CDP] Failed to fetch connection info:', e);
    }
}

function switchCdpTab(button, tabName) {
    // Update tab buttons
    document.querySelectorAll('.cdp-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    button.classList.add('active');

    // Update tab content
    document.querySelectorAll('.cdp-tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(`cdp-tab-${tabName}`).classList.add('active');
}

function copyCdpText(text, button) {
    writeClipboard(text).then(() => {
        const originalText = button.textContent;
        button.textContent = 'Copied!';
        button.classList.add('copied');
        setTimeout(() => {
            button.textContent = originalText;
            button.classList.remove('copied');
        }, 2000);
    }).catch(err => {
        console.error('[CDP] Failed to copy:', err);
        showToast('Failed to copy to clipboard', 'error');
    });
}

function openChromeInspect() {
    // Note: chrome:// URLs cannot be opened programmatically due to browser security
    // Show instructions instead
    showToast('Copy "chrome://inspect/#devices" and paste in your browser\'s address bar');
    copyCdpText('chrome://inspect/#devices', document.querySelector('.cdp-actions .primary'));
    closeCdpModal();
}

function openDevToolsInVM() {
    closeCdpModal();
    // Open DevTools inside the VM
    toggleDevToolsInVM();
}

// Run Inspekt command via the control server bridge and copy output to clipboard.
async function runInspektForClipboard(command, label) {
    try {
        showToast(`Copying ${label}…`);
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${encodeURIComponent(command)}`);
        const data = await response.json();
        if (data.ok && data.output) {
            await writeClipboard(data.output.trim());
            showToast(`${label} copied!`, 'success');
        } else {
            showToast(data.error || 'No selection found', 'error');
        }
    } catch (e) {
        showToast('Failed: ' + e.message, 'error');
    }
}

// Run a slow Inspekt command (AI-powered) with persistent loading toast
async function runInspektAI(command, loadingLabel, successLabel) {
    try {
        showToast(`${loadingLabel}…`, '', 60000);  // persistent toast during AI processing
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${encodeURIComponent(command)}`);
        const data = await response.json();
        if (data.ok && data.output) {
            await writeClipboard(data.output.trim());
            showToast(`${successLabel} copied to clipboard!`, 'success');
        } else {
            showToast(data.error || 'Command failed', 'error');
        }
    } catch (e) {
        showToast('Failed: ' + e.message, 'error');
    }
}

// Last captured region for "Repeat Last Region" in screenshot submenu
let _lastScreenshotRegion = null;  // { x, y, w, h } in VM CSS pixels

// Download a screenshot from the given endpoint
async function screenshotToDownload(endpoint, filename) {
    try {
        showToast('Capturing screenshot…', '', 15000);
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}${endpoint}`);
        const data = await resp.json();
        if (!data.ok) { showToast(data.error || 'Screenshot failed', 'error'); return; }
        // Convert base64 to blob and trigger download
        const byteChars = atob(data.data);
        const byteArray = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) byteArray[i] = byteChars.charCodeAt(i);
        const blob = new Blob([byteArray], { type: 'image/png' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        showToast('Screenshot saved!', 'success');
    } catch (e) {
        showToast('Screenshot failed: ' + e.message, 'error');
    }
}

// Interactive region selection for screenshots.
// Shows a crosshair overlay on the VNC canvas and lets the user drag to select a region.
function startRegionSelection() {
    const container = document.getElementById('vncContainer');
    if (!container) return;

    // Disable VNC keyboard while selecting
    if (typeof rfb !== 'undefined' && rfb && rfb._keyboard) rfb._keyboard.ungrab();

    const overlay = document.createElement('div');
    Object.assign(overlay.style, {
        position: 'absolute', inset: '0', zIndex: '9999',
        cursor: 'crosshair', background: 'rgba(0,0,0,0.08)',
    });
    container.style.position = 'relative';
    container.appendChild(overlay);

    const selBox = document.createElement('div');
    Object.assign(selBox.style, {
        position: 'absolute', border: '2px dashed #0066ff',
        background: 'rgba(0, 102, 255, 0.12)', borderRadius: '2px',
        pointerEvents: 'none', display: 'none',
    });
    overlay.appendChild(selBox);

    const sizeLabel = document.createElement('div');
    Object.assign(sizeLabel.style, {
        position: 'absolute', padding: '2px 6px', borderRadius: '3px',
        background: 'rgba(0,0,0,0.7)', color: '#fff', fontSize: '11px',
        fontFamily: 'system-ui, sans-serif', pointerEvents: 'none',
        whiteSpace: 'nowrap', display: 'none',
    });
    overlay.appendChild(sizeLabel);

    showToast('Drag to select a region', '', 4000);

    let startX = 0, startY = 0, dragging = false;

    function onKey(e) {
        if (e.key === 'Escape') {
            cleanup();
            showToast('Selection cancelled', '', 2000);
        }
    }

    function cleanup() {
        overlay.remove();
        document.removeEventListener('keydown', onKey);
        document.removeEventListener('mouseup', onMouseUp);
        if (typeof rfb !== 'undefined' && rfb && rfb._keyboard) rfb._keyboard.grab();
    }

    overlay.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        startX = e.clientX;
        startY = e.clientY;
        dragging = true;
        selBox.style.display = 'block';
        sizeLabel.style.display = 'block';
        selBox.style.left = (e.clientX - overlay.getBoundingClientRect().left) + 'px';
        selBox.style.top = (e.clientY - overlay.getBoundingClientRect().top) + 'px';
        selBox.style.width = '0';
        selBox.style.height = '0';
    });

    overlay.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        const rect = overlay.getBoundingClientRect();
        const x = Math.min(startX, e.clientX) - rect.left;
        const y = Math.min(startY, e.clientY) - rect.top;
        const w = Math.abs(e.clientX - startX);
        const h = Math.abs(e.clientY - startY);
        Object.assign(selBox.style, {
            left: x + 'px', top: y + 'px',
            width: w + 'px', height: h + 'px',
        });
        // Show size label near bottom-right of selection
        const vm1 = _clientToVm(Math.min(startX, e.clientX), Math.min(startY, e.clientY));
        const vm2 = _clientToVm(Math.max(startX, e.clientX), Math.max(startY, e.clientY));
        const vmW = Math.round(vm2.x - vm1.x);
        const vmH = Math.round(vm2.y - vm1.y);
        sizeLabel.textContent = `${vmW}\u00d7${vmH}`;
        sizeLabel.style.left = (x + w + 6) + 'px';
        sizeLabel.style.top = (y + h - 2) + 'px';
    });

    // Listen on document so mouseup outside the overlay still completes the selection
    async function onMouseUp(e) {
        if (!dragging) return;
        dragging = false;

        // Convert both corners to VM coordinates
        const vm1 = _clientToVm(Math.min(startX, e.clientX), Math.min(startY, e.clientY));
        const vm2 = _clientToVm(Math.max(startX, e.clientX), Math.max(startY, e.clientY));
        const regionW = vm2.x - vm1.x;
        const regionH = vm2.y - vm1.y;

        cleanup();

        if (regionW < 4 || regionH < 4) {
            showToast('Selection too small', 'error');
            return;
        }

        // Send viewport-relative coords; server adds scroll offset automatically
        const region = { x: vm1.x, y: vm1.y, w: regionW, h: regionH };
        _lastScreenshotRegion = region;

        const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        screenshotToDownload(
            `/screenshot/region?x=${region.x}&y=${region.y}&w=${region.w}&h=${region.h}`,
            `region-${Math.round(region.w)}x${Math.round(region.h)}-${ts}.png`
        );
    }
    document.addEventListener('mouseup', onMouseUp);

    document.addEventListener('keydown', onKey);

    // Also cancel if overlay is right-clicked
    overlay.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        cleanup();
    });
}

// Copy image data to host clipboard (converts to PNG since clipboard API requires it)
async function copyImageToClipboard(imageSrc) {
    try {
        showToast('Copying image\u2026', '', 15000);
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/image/fetch?url=${encodeURIComponent(imageSrc)}`
        );
        const data = await resp.json();
        if (!data.ok) { showToast(data.error || 'Failed to fetch image', 'error'); return; }

        const byteChars = atob(data.data);
        const byteArray = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) byteArray[i] = byteChars.charCodeAt(i);

        let pngBlob;
        if (data.format === 'png') {
            pngBlob = new Blob([byteArray], { type: 'image/png' });
        } else {
            // Clipboard API requires PNG — convert via canvas on the host
            const srcBlob = new Blob([byteArray], { type: `image/${data.format}` });
            const bitmap = await createImageBitmap(srcBlob);
            const canvas = document.createElement('canvas');
            canvas.width = bitmap.width;
            canvas.height = bitmap.height;
            canvas.getContext('2d').drawImage(bitmap, 0, 0);
            pngBlob = await new Promise(r => canvas.toBlob(r, 'image/png'));
            bitmap.close();
        }

        await writeImageToClipboard(pngBlob);
        showToast('Image copied!', 'success');
    } catch (e) {
        showToast('Failed to copy image: ' + e.message, 'error');
    }
}

// Download image file to host
async function downloadImage(imageSrc) {
    try {
        showToast('Downloading image\u2026', '', 15000);
        const resp = await fetch(
            `http://${VNC_HOST}:${CONTROL_PORT}/image/fetch?url=${encodeURIComponent(imageSrc)}`
        );
        const data = await resp.json();
        if (!data.ok) { showToast(data.error || 'Failed to fetch image', 'error'); return; }

        const byteChars = atob(data.data);
        const byteArray = new Uint8Array(byteChars.length);
        for (let i = 0; i < byteChars.length; i++) byteArray[i] = byteChars.charCodeAt(i);

        // Determine filename from URL
        let filename = 'image.png';
        try {
            const basename = new URL(imageSrc).pathname.split('/').pop();
            if (basename && basename.includes('.')) filename = decodeURIComponent(basename);
            else if (basename) filename = basename + '.png';
        } catch {}

        const mimeType = data.format === 'jpeg' ? 'image/jpeg'
                       : data.format === 'webp' ? 'image/webp'
                       : data.format === 'gif' ? 'image/gif'
                       : 'image/png';
        const blob = new Blob([byteArray], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        showToast(`Downloaded: ${filename}`, 'success');
    } catch (e) {
        showToast('Download failed: ' + e.message, 'error');
    }
}

// Show prompt dialog for "Ask" AI commands
function showAskDialog(scope) {
    // scope: 'selection', 'inspected', or 'page'
    const scopeLabels = { selection: 'selection', inspected: 'element', page: 'page' };
    const question = prompt(`Ask about the ${scopeLabels[scope] || scope}:`);
    if (!question || !question.trim()) return;

    // Shell-quote the question so shlex.split() treats it as one token
    const q = '"' + question.trim().replace(/\\/g, '\\\\').replace(/"/g, '\\"') + '"';

    let command;
    if (scope === 'selection') command = `selection ask ${q}`;
    else if (scope === 'inspected') command = `inspected ask ${q}`;
    else command = `ask ${q}`;

    runInspektAI(command, 'Thinking', 'Answer');
}

// Run Inspekt command
async function runInspekt(command) {
    document.querySelectorAll('.dropdown-menu').forEach(m => m.classList.remove('show'));
    showToast(`Running inspekt ${command}…`);

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${command}`);
        const data = await response.json();
        if (data.ok) {
            showToast(`inspekt ${command} completed`, 'success');
            console.log(data.output);
        } else {
            showToast(`Error: ${data.error}`, 'error', 5000);
        }
    } catch (error) {
        showToast('Command failed: ' + error.message, 'error');
    }
}


