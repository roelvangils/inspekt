// =============================================
// Port Configuration (supports local dev & server deployment)
// =============================================
// Use 127.0.0.1 instead of localhost to force IPv4 (Docker port forwarding issue)
const VNC_HOST = window.location.hostname || 'localhost';

// Smart port detection:
// - Inside container: page=6080 → control=8888, terminal=8889
// - External mapping: page=7080 → control=7888, terminal=7889
// - Override via URL params: ?control_port=X&terminal_port=Y&vnc_port=Z
const urlParams = new URLSearchParams(window.location.search);
const pagePort = parseInt(window.location.port) || 80;

function detectPort(paramName, internalDefault, portSuffix) {
    // 1. Check URL param override (highest priority)
    const override = urlParams.get(paramName);
    if (override) return parseInt(override);

    // 2. If served from internal container port (6080), use internal defaults
    if (pagePort === 6080) return internalDefault;

    // 3. Calculate from page port: replace last 3 digits
    //    e.g., 7080 → 7888 (base 7000 + suffix 888)
    const base = Math.floor(pagePort / 1000) * 1000;
    return base + portSuffix;
}

const VNC_PORT = urlParams.get('vnc_port') ? parseInt(urlParams.get('vnc_port')) : pagePort;
const CONTROL_PORT = detectPort('control_port', 8888, 888);
const TERMINAL_PORT = detectPort('terminal_port', 8889, 889);

// Log port configuration for debugging
console.log('[Inspekt] Port config:', { pagePort, VNC_PORT, CONTROL_PORT, TERMINAL_PORT });

// =============================================
// Shared Nav Icons (reused across context menus)
// =============================================
const NAV_ICONS = {
    back:    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg>',
    forward: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 4l-1.41 1.41L16.17 11H4v2h12.17l-5.58 5.59L12 20l8-8z"/></svg>',
    up:      '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M4 12l1.41 1.41L11 7.83V20h2V7.83l5.58 5.59L20 12l-8-8-8 8z"/></svg>',
    reload:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/></svg>',
    down:    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z"/></svg>',
};

// =============================================
// VM Configuration (from inspekt-config.yaml)
// =============================================
let _vmConfig = {};

async function loadVMConfig() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/config`, {
            signal: AbortSignal.timeout(3000),
        });
        const data = await resp.json();
        if (data.ok) {
            _vmConfig = data.config || {};
            console.log('[Config] Loaded:', Object.keys(_vmConfig).join(', '));
        }
    } catch (e) {
        console.warn('[Config] Failed to load:', e.message);
    }
}

// Helper: read a dotted key path from the loaded config.
// Returns defaultValue if key is missing, null, empty, or wrong type.
function getConfig(path, defaultValue) {
    let obj = _vmConfig;
    for (const key of path.split('.')) {
        if (obj == null || typeof obj !== 'object') return defaultValue;
        obj = obj[key];
    }
    if (obj == null || obj === '') return defaultValue;
    // Type check: if a default is provided, ensure the value matches its type
    if (defaultValue !== undefined && typeof obj !== typeof defaultValue) {
        console.warn(`[Config] Type mismatch for "${path}": expected ${typeof defaultValue}, got ${typeof obj}`);
        return defaultValue;
    }
    return obj;
}

// Load config early — store the promise so other init code can await it
const _configReady = loadVMConfig();

// =============================================
// Terminal Trigger Words
// =============================================
// Scans terminal output for configurable keywords and shows a
// notification toast + plays a subtle sound when detected.
// Debounced to avoid flooding during stack traces.

let _triggerWordRegex = null;
let _triggerLastFired = 0;
const _TRIGGER_DEBOUNCE_MS = 3000;

// Build the regex after config loads
_configReady.then(() => {
    const words = getConfig('terminal.trigger-words', ['error', 'fail']);
    if (Array.isArray(words) && words.length > 0) {
        // Build a case-insensitive regex matching any of the words at word boundaries
        const escaped = words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
        _triggerWordRegex = new RegExp('\\b(' + escaped.join('|') + ')\\b', 'i');
        console.log(`[TriggerWords] Watching for: ${words.join(', ')}`);
    }
});

// =============================================
// Toast Position
// =============================================
// Resolved from appearance.toast-position after config loads.
// Read by showToast() in vnc.js on every call.
var _toastPositionClass = 'pos-top-center';
const _TOAST_POSITIONS = [
    'top-left', 'top-center', 'top-right',
    'bottom-left', 'bottom-center', 'bottom-right',
];
_configReady.then(() => {
    const pos = getConfig('appearance.toast-position', 'top-center');
    _toastPositionClass = 'pos-' + (_TOAST_POSITIONS.includes(pos) ? pos : 'top-center');
});

// Notification beep via Web Audio API (no external sound file needed)
let _audioCtx = null;
function playNotificationBeep() {
    try {
        if (!_audioCtx) _audioCtx = new AudioContext();
        const osc = _audioCtx.createOscillator();
        const gain = _audioCtx.createGain();
        osc.connect(gain);
        gain.connect(_audioCtx.destination);
        osc.frequency.value = 880; // A5 note
        gain.gain.value = 0.08;    // Subtle volume
        osc.start();
        gain.gain.exponentialRampToValueAtTime(0.001, _audioCtx.currentTime + 0.15);
        osc.stop(_audioCtx.currentTime + 0.15);
    } catch { /* Audio not available */ }
}

// Scan a chunk of terminal output for trigger words
function checkTriggerWords(text) {
    if (!_triggerWordRegex) return;

    // Strip ANSI escape codes for clean matching
    const plain = text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
    const match = plain.match(_triggerWordRegex);
    if (!match) return;

    // Debounce — don't fire again within 3 seconds
    const now = Date.now();
    if (now - _triggerLastFired < _TRIGGER_DEBOUNCE_MS) return;
    _triggerLastFired = now;

    // Extract the line containing the match for context
    const lines = plain.split(/\r?\n/);
    const matchedLine = lines.find(l => _triggerWordRegex.test(l)) || match[0];
    const trimmedLine = matchedLine.trim().substring(0, 120);

    playNotificationBeep();
    showToast(trimmedLine, { type: 'error', duration: 5000, dismissible: true });
}

// =============================================
// Shared State (cross-module variables)
// =============================================
// These are declared here (loaded first) so all modules
// can read/write them regardless of bundle concatenation order.

// VNC / RFB
var rfb = null;

// Terminal
var terminal = null;
var terminalSocket = null;
var fitAddon = null;
var isTerminalOpen = false;
var hasTerminalSession = false;
var _terminalPromptDomain = 'inspekt';

// Editor
var editorView = null;
var editorCurrentPath = null;
var editorIsReadOnly = false;
var editorIsDirty = false;
var activePanel = 'terminal';

// Split mode & position
var terminalPosition = localStorage.getItem('terminalPosition') || 'right';
var terminalMode = localStorage.getItem('terminalMode') || 'floating';
var splitRatio = parseFloat(localStorage.getItem('splitRatio')) || 0.5;
var splitFlipped = localStorage.getItem('splitFlipped') === 'true';
var isDraggingSplitHandle = false;

// VNC connection state
var isConnected = false;

// Global mouse position tracking
var _lastMouseX = window.innerWidth / 2, _lastMouseY = window.innerHeight / 2;
