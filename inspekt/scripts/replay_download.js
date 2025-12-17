// Download monitoring for replay
// This script handles download detection and capture during replay sessions
(function() {
    const config = DOWNLOAD_CONFIG_PLACEHOLDER;
    const action = config.action; // 'start', 'wait', 'stop'
    const sessionId = config.sessionId || 'replay-downloads';
    const timeout = config.timeout || 30000;
    const expectedFilename = config.expectedFilename || null;

    // ==================== START MONITORING ====================
    if (action === 'start') {
        // Initialize download tracking
        window.__INSPEKT_REPLAY_DOWNLOADS__ = {
            sessionId: sessionId,
            pending: new Map(),
            completed: [],
            handler: null
        };

        const state = window.__INSPEKT_REPLAY_DOWNLOADS__;

        // Message handler for download events
        state.handler = function(event) {
            if (event.source !== window) return;
            const message = event.data;
            if (!message || message.source !== 'inspekt-extension') return;

            // Handle download start
            if (message.type === 'INSPEKT_DOWNLOAD_STARTED') {
                const download = message.download;
                if (!download) return;
                state.pending.set(download.id, {
                    ...download,
                    startTime: Date.now()
                });
                console.log('[Inspekt Replay] Download started:', download.filename);
            }

            // Handle download complete
            if (message.type === 'INSPEKT_DOWNLOAD_COMPLETE') {
                const download = message.download;
                if (!download) return;

                if (download.state === 'complete') {
                    state.completed.push({
                        id: download.id,
                        filename: download.filename,
                        url: download.url,
                        mime_type: download.mime_type,
                        size: download.size,
                        fullPath: download.fullPath,
                        download_start: download.download_start,
                        download_end: download.download_end,
                        completedAt: Date.now()
                    });
                    console.log('[Inspekt Replay] Download completed:', download.filename, download.fullPath);
                }
                state.pending.delete(download.id);
            }
        };

        window.addEventListener('message', state.handler);

        // Request download monitoring from extension
        window.postMessage({
            type: 'INSPEKT_START_DOWNLOAD_MONITORING',
            source: 'inspekt-page',
            sessionId: sessionId,
            requestId: `replay-dm-start-${Date.now()}`
        }, location.origin);

        return { ok: true, action: 'start', message: 'Download monitoring started' };
    }

    // ==================== WAIT FOR DOWNLOAD ====================
    if (action === 'wait') {
        const state = window.__INSPEKT_REPLAY_DOWNLOADS__;
        if (!state) {
            return { ok: false, error: 'Download monitoring not started' };
        }

        return new Promise((resolve) => {
            const startTime = Date.now();
            let resolved = false;

            function checkForDownload() {
                if (resolved) return;

                // Check completed downloads
                for (let i = state.completed.length - 1; i >= 0; i--) {
                    const download = state.completed[i];

                    // If we have an expected filename, check for match
                    if (expectedFilename) {
                        // Match by filename (allowing for Chrome's duplicate naming like "file (1).json")
                        const baseExpected = expectedFilename.replace(/\s*\(\d+\)(\.[^.]+)?$/, '$1');
                        const baseActual = download.filename.replace(/\s*\(\d+\)(\.[^.]+)?$/, '$1');

                        if (baseActual !== baseExpected) {
                            continue;
                        }
                    }

                    // Found a matching download
                    resolved = true;
                    // Remove from completed list (so we don't match it again)
                    state.completed.splice(i, 1);
                    resolve({
                        ok: true,
                        action: 'wait',
                        download: download
                    });
                    return;
                }

                // Check timeout
                if (Date.now() - startTime > timeout) {
                    resolved = true;
                    resolve({
                        ok: false,
                        action: 'wait',
                        error: `Download timeout after ${timeout}ms`,
                        pendingCount: state.pending.size
                    });
                    return;
                }

                // Keep checking
                setTimeout(checkForDownload, 100);
            }

            checkForDownload();
        });
    }

    // ==================== STOP MONITORING ====================
    if (action === 'stop') {
        const state = window.__INSPEKT_REPLAY_DOWNLOADS__;
        if (!state) {
            return { ok: true, action: 'stop', message: 'Not monitoring' };
        }

        // Remove handler
        if (state.handler) {
            window.removeEventListener('message', state.handler);
        }

        // Request stop from extension
        window.postMessage({
            type: 'INSPEKT_STOP_DOWNLOAD_MONITORING',
            source: 'inspekt-page',
            sessionId: state.sessionId
        }, location.origin);

        // Cleanup
        const stats = {
            completed: state.completed.length,
            pending: state.pending.size
        };
        delete window.__INSPEKT_REPLAY_DOWNLOADS__;

        return { ok: true, action: 'stop', message: 'Download monitoring stopped', stats };
    }

    // ==================== GET STATUS ====================
    if (action === 'status') {
        const state = window.__INSPEKT_REPLAY_DOWNLOADS__;
        if (!state) {
            return { ok: true, action: 'status', monitoring: false };
        }
        return {
            ok: true,
            action: 'status',
            monitoring: true,
            completed: state.completed.length,
            pending: state.pending.size,
            downloads: state.completed
        };
    }

    return { ok: false, error: `Unknown action: ${action}` };
})();
