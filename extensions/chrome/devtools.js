/**
 * Inspekt DevTools Integration
 *
 * Automatically captures elements selected in Chrome DevTools inspector.
 * When you inspect an element (right-click → Inspect), it's automatically
 * stored and available via `inspekt inspected` command.
 *
 * Also provides:
 * - Custom DevTools panel with settings and quick actions
 * - Network request monitoring with HAR export capability
 */

// ============================================================================
// NETWORK MONITORING
// ============================================================================

// Store for network requests (HAR entries)
let networkEntries = [];
let harLog = null;

/**
 * Initialize network monitoring
 * Captures all network requests for HAR export
 */
function initNetworkMonitoring() {
    console.log('[Inspekt DevTools] Initializing network monitoring…');

    // Listen for completed network requests
    chrome.devtools.network.onRequestFinished.addListener((request) => {
        // Store the request entry
        networkEntries.push({
            request: request,
            timestamp: Date.now()
        });

        // Log for debugging (can be disabled in production)
        // console.log('[Inspekt Network] Request captured:', request.request.url);
    });

    // Listen for page navigation (clears network log)
    chrome.devtools.network.onNavigated.addListener((url) => {
        console.log('[Inspekt DevTools] Page navigated, clearing network log');
        networkEntries = [];
        harLog = null;
    });

    console.log('[Inspekt DevTools] Network monitoring active');
}

/**
 * Get HAR log from DevTools Network API
 * Returns a promise that resolves with the full HAR data
 */
function getHAR() {
    return new Promise((resolve, reject) => {
        try {
            chrome.devtools.network.getHAR((harData) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                    return;
                }

                // Transform HAR entries to include more useful data
                const entries = harData.entries.map((entry, index) => {
                    // Parse URL for easier filtering
                    let urlParts = {};
                    try {
                        const url = new URL(entry.request.url);
                        urlParts = {
                            domain: url.hostname,
                            path: url.pathname,
                            filename: url.pathname.split('/').pop() || url.pathname,
                            protocol: url.protocol.replace(':', '')
                        };
                    } catch (e) {
                        urlParts = {
                            domain: '',
                            path: entry.request.url,
                            filename: entry.request.url,
                            protocol: 'unknown'
                        };
                    }

                    // Determine resource type
                    const mimeType = entry.response.content?.mimeType || '';
                    let resourceType = 'other';
                    if (mimeType.includes('javascript') || urlParts.filename.endsWith('.js')) {
                        resourceType = 'script';
                    } else if (mimeType.includes('css') || urlParts.filename.endsWith('.css')) {
                        resourceType = 'stylesheet';
                    } else if (mimeType.includes('image') || /\.(png|jpg|jpeg|gif|webp|svg|ico|avif)$/i.test(urlParts.filename)) {
                        resourceType = 'image';
                    } else if (mimeType.includes('font') || /\.(woff2?|ttf|otf|eot)$/i.test(urlParts.filename)) {
                        resourceType = 'font';
                    } else if (mimeType.includes('html')) {
                        resourceType = 'document';
                    } else if (mimeType.includes('json') || entry.request.url.includes('/api/')) {
                        resourceType = 'fetch';
                    } else if (mimeType.includes('xml')) {
                        resourceType = 'xml';
                    } else if (mimeType.includes('video')) {
                        resourceType = 'video';
                    } else if (mimeType.includes('audio')) {
                        resourceType = 'audio';
                    }

                    // Calculate timing breakdown
                    const timings = entry.timings || {};

                    return {
                        index: index + 1,
                        url: entry.request.url,
                        name: urlParts.filename,
                        domain: urlParts.domain,
                        path: urlParts.path,
                        type: resourceType,
                        method: entry.request.method,

                        // Response info (NOT available in Performance API!)
                        status: entry.response.status,
                        statusText: entry.response.statusText,
                        mimeType: mimeType,

                        // Size info
                        transferSize: entry.response._transferSize || entry.response.bodySize || 0,
                        bodySize: entry.response.bodySize || 0,
                        headerSize: entry.response.headersSize || 0,

                        // Timing info (in ms)
                        timing: {
                            total: Math.round(entry.time || 0),
                            blocked: Math.round(Math.max(0, timings.blocked || 0)),
                            dns: Math.round(Math.max(0, timings.dns || 0)),
                            connect: Math.round(Math.max(0, timings.connect || 0)),
                            ssl: Math.round(Math.max(0, timings.ssl || 0)),
                            send: Math.round(Math.max(0, timings.send || 0)),
                            wait: Math.round(Math.max(0, timings.wait || 0)),  // TTFB
                            receive: Math.round(Math.max(0, timings.receive || 0))
                        },

                        // Request/Response headers (NOT available in Performance API!)
                        requestHeaders: entry.request.headers,
                        responseHeaders: entry.response.headers,

                        // Initiator info
                        initiator: entry._initiator || null,

                        // Start time
                        startedDateTime: entry.startedDateTime,

                        // Server IP
                        serverIPAddress: entry.serverIPAddress || null,

                        // Connection info
                        connection: entry.connection || null,

                        // Cache status
                        fromCache: entry.response.status === 304 ||
                                   (entry.response._transferSize === 0 && entry.response.bodySize > 0),

                        // Raw HAR entry for full access
                        _raw: entry
                    };
                });

                // Build summary
                const summary = {
                    totalRequests: entries.length,
                    totalTransferSize: entries.reduce((sum, e) => sum + (e.transferSize || 0), 0),
                    totalBodySize: entries.reduce((sum, e) => sum + (e.bodySize || 0), 0),

                    // Status code breakdown
                    byStatus: {},

                    // Type breakdown
                    byType: {},

                    // Domain breakdown
                    byDomain: {},

                    // Timing stats
                    averageDuration: 0,
                    slowestRequest: null,
                    largestRequest: null,

                    // Error counts
                    errors: 0,
                    redirects: 0,
                    cached: 0
                };

                // Calculate breakdowns
                entries.forEach(entry => {
                    // By status
                    const statusGroup = Math.floor(entry.status / 100) * 100;
                    summary.byStatus[statusGroup] = (summary.byStatus[statusGroup] || 0) + 1;

                    // By type
                    summary.byType[entry.type] = (summary.byType[entry.type] || 0) + 1;

                    // By domain
                    summary.byDomain[entry.domain] = (summary.byDomain[entry.domain] || 0) + 1;

                    // Errors (4xx, 5xx)
                    if (entry.status >= 400) summary.errors++;

                    // Redirects (3xx)
                    if (entry.status >= 300 && entry.status < 400) summary.redirects++;

                    // Cached
                    if (entry.fromCache) summary.cached++;
                });

                // Average duration
                if (entries.length > 0) {
                    summary.averageDuration = Math.round(
                        entries.reduce((sum, e) => sum + e.timing.total, 0) / entries.length
                    );

                    // Slowest
                    const slowest = entries.reduce((max, e) =>
                        e.timing.total > max.timing.total ? e : max
                    );
                    summary.slowestRequest = {
                        name: slowest.name,
                        url: slowest.url,
                        duration: slowest.timing.total,
                        status: slowest.status
                    };

                    // Largest
                    const largest = entries.reduce((max, e) =>
                        (e.transferSize || 0) > (max.transferSize || 0) ? e : max
                    );
                    summary.largestRequest = {
                        name: largest.name,
                        url: largest.url,
                        size: largest.transferSize,
                        status: largest.status
                    };
                }

                resolve({
                    ok: true,
                    source: 'devtools',
                    url: harData.pages?.[0]?.title || 'Unknown',
                    timestamp: new Date().toISOString(),
                    entries: entries,
                    summary: summary,
                    // Include raw HAR for full export
                    rawHAR: harData
                });
            });
        } catch (error) {
            reject(error);
        }
    });
}

// Initialize network monitoring when devtools loads
initNetworkMonitoring();

// ============================================================================
// DEVTOOLS PANEL
// ============================================================================

// Create the Inspekt panel in DevTools
chrome.devtools.panels.create(
    'Inspekt',              // Panel title
    'icons/icon-16.png',    // Icon path
    'panel.html',           // Panel HTML page
    (panel) => {
        console.log('[Inspekt DevTools] Panel created successfully');

        // Panel lifecycle events
        panel.onShown.addListener((window) => {
            console.log('[Inspekt DevTools] Panel opened');
        });

        panel.onHidden.addListener(() => {
            console.log('[Inspekt DevTools] Panel hidden');
        });
    }
);

// Monitor element selection in the Elements panel
chrome.devtools.panels.elements.onSelectionChanged.addListener(() => {
    // When user selects an element in DevTools inspector
    // $0 is the currently selected element in DevTools
    chrome.devtools.inspectedWindow.eval(
        `(function() {
            // Check if $0 is available and is a valid element
            if (typeof $0 !== 'undefined' && $0 && $0.nodeType === 1) {
                // Store the element in the global variable
                window.__INSPEKT_INSPECTED_ELEMENT__ = $0;

                // Track selection source and timestamp
                window.__INSPEKT_SELECTION_SOURCE__ = 'devtools';
                window.__INSPEKT_SELECTION_TIME__ = Date.now();

                // Get element info for console feedback
                const tag = $0.tagName.toLowerCase();
                const id = $0.id ? '#' + $0.id : '';
                const cls = $0.className && typeof $0.className === 'string' ?
                    '.' + $0.className.trim().split(/\\s+/).slice(0, 2).join('.') : '';
                const selector = tag + id + cls;

                // Log confirmation
                console.log(
                    '%c[Inspekt]%c ✓ Element auto-stored: %c<' + selector + '>%c (DevTools)',
                    'color: #0066ff; font-weight: bold',
                    'color: inherit',
                    'color: #00aa00; font-weight: bold',
                    'color: #666; font-style: italic'
                );
                console.log('[Inspekt] Run in terminal: inspekt inspected');

                return { success: true, selector: selector };
            } else {
                return { success: false, reason: 'No valid element selected' };
            }
        })()`,
        (result, error) => {
            if (error) {
                console.error('[Inspekt DevTools] Error storing element:', error);
            } else if (result && result.success) {
                // Successfully stored
                console.log('[Inspekt DevTools] Element stored:', result.selector);
            }
        }
    );
});

// Initialize DevTools integration
console.log('[Inspekt DevTools] Integration loaded');
console.log('[Inspekt DevTools] Elements are now automatically tracked when inspected');

// ============================================================================
// DEVTOOLS <-> BACKGROUND COMMUNICATION
// ============================================================================

/**
 * Create a connection to the background script for HAR requests
 */
let backgroundConnection = null;

function connectToBackground() {
    backgroundConnection = chrome.runtime.connect({
        name: 'devtools-' + chrome.devtools.inspectedWindow.tabId
    });

    backgroundConnection.onMessage.addListener((message) => {
        console.log('[Inspekt DevTools] Message from background:', message);

        if (message.type === 'GET_HAR') {
            // Background is requesting HAR data
            getHAR()
                .then(harData => {
                    backgroundConnection.postMessage({
                        type: 'HAR_RESPONSE',
                        requestId: message.requestId,
                        data: harData
                    });
                })
                .catch(error => {
                    backgroundConnection.postMessage({
                        type: 'HAR_RESPONSE',
                        requestId: message.requestId,
                        error: String(error)
                    });
                });
        }
    });

    backgroundConnection.onDisconnect.addListener(() => {
        console.log('[Inspekt DevTools] Disconnected from background, reconnecting…');
        backgroundConnection = null;
        // Reconnect after a short delay
        setTimeout(connectToBackground, 1000);
    });

    console.log('[Inspekt DevTools] Connected to background script for HAR requests');
}

// Connect to background script
connectToBackground();

// Also expose getHAR globally for the DevTools panel to use directly
window.inspektGetHAR = getHAR;
