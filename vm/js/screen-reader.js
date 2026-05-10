// =============================================
// Screen Reader Simulator
// =============================================

let srActive = false;
let srScreenReader = null;
let srKeyMap = null;
let srCheatSheetVisible = false;
let srPreviousAnnouncement = '';

// ── SR Profiles ─────────────────────────────────
// Per-screen-reader configuration for visual presentation,
// focus indicators, and caption style. Shared navigation
// engine reads these to render the appropriate UI.
// ─────────────────────────────────────────────────
const SR_PROFILES = {
    jaws: {
        id: 'jaws',
        name: 'JAWS',
        fullName: 'Job Access With Speech',
        platform: 'Windows',
        captionStyle: 'docked',
        accentColor: '#2196f3',
        focusIndicator: {
            style: 'colored-border',
            borderColor: '#2196f3',
            borderWidth: 3,
            borderRadius: 2,
            backgroundColor: 'rgba(33, 150, 243, 0.06)',
            shadowColor: 'rgba(33, 150, 243, 0.25)',
        },
        caption: {
            showTTSButton: true,
            showLogButton: true,
        },
        // Future: specialWindows, modes, remediationHints
    },
    nvda: {
        id: 'nvda',
        name: 'NVDA',
        fullName: 'NonVisual Desktop Access',
        platform: 'Windows',
        captionStyle: 'docked',
        accentColor: '#9c27b0',
        focusIndicator: {
            style: 'colored-border',
            borderColor: '#9c27b0',
            borderWidth: 3,
            borderRadius: 2,
            backgroundColor: 'rgba(156, 39, 176, 0.06)',
            shadowColor: 'rgba(156, 39, 176, 0.25)',
        },
        caption: {
            showTTSButton: true,
            showLogButton: true,
        },
    },
    voiceover: {
        id: 'voiceover',
        name: 'VoiceOver',
        fullName: 'VoiceOver for macOS',
        platform: 'macOS',
        captionStyle: 'floating',
        accentColor: '#333',
        focusIndicator: {
            style: 'colored-border',
            borderColor: '#333',
            borderWidth: 3,
            borderRadius: 2,
            backgroundColor: 'rgba(0, 0, 0, 0.06)',
            shadowColor: 'rgba(0, 0, 0, 0.25)',
            // Alternative: VoiceOver-style cursor (togglable)
            altStyle: 'voiceover-cursor',
            altBorderColor: '#333',
            altBorderWidth: 4,
            altBorderRadius: 8,
            altBackgroundColor: 'rgba(0, 0, 0, 0.08)',
            altShadowColor: 'rgba(0, 0, 0, 0.35)',
        },
        caption: {
            showTTSButton: false,
            showLogButton: true,
        },
        floating: {
            defaultPosition: { left: 20, bottom: 60 },
            minWidth: 280,
            minHeight: 48,
            defaultWidth: 480,
            opacity: 0.95,
        },
    },
};

// ── SR Caption Manager ────────────────────────
// Manages per-SR caption UI (docked bar vs floating
// panel), focus indicators, and speech log.
// ─────────────────────────────────────────────────
const SRCaptionManager = {
    _profile: null,
    _floatingPanel: null,
    _dragState: null,
    _resizeObserver: null,
    _speechLogVisible: false,

    start(srId) {
        this._profile = SR_PROFILES[srId];
        if (!this._profile) return;

        const profile = this._profile;

        // Show focus indicator with profile-driven styling
        const indicator = document.getElementById('srFocusIndicator');
        indicator.style.display = 'block';
        this._applyFocusIndicatorStyle();

        // Caption: docked or floating
        if (profile.captionStyle === 'floating') {
            this._createFloatingCaption();
            document.getElementById('srCaptions').style.display = 'none';
        } else {
            document.getElementById('srCaptions').style.display = 'flex';
            // Configure docked bar based on profile
            const ttsBtn = document.getElementById('srTTSBtn');
            if (ttsBtn) ttsBtn.style.display = profile.caption.showTTSButton ? '' : 'none';
        }
    },

    stop() {
        // Remove floating panel if present
        if (this._floatingPanel) {
            this._saveFloatingPosition();
            this._floatingPanel.remove();
            this._floatingPanel = null;
            if (this._resizeObserver) {
                this._resizeObserver.disconnect();
                this._resizeObserver = null;
            }
        }
        // Hide docked caption
        document.getElementById('srCaptions').style.display = 'none';
        // Hide focus indicator
        document.getElementById('srFocusIndicator').style.display = 'none';
        // Hide speech log
        this._hideSpeechLog();
        this._profile = null;
    },

    update(result) {
        const profile = this._profile;
        if (!profile) return;

        const announcement = result.announcement || '';
        const role = result.role || '';

        if (profile.captionStyle === 'floating' && this._floatingPanel) {
            // Update floating panel
            srPreviousAnnouncement = this._floatingPanel.querySelector('.sr-floating-text')?.textContent || '';
            const textEl = this._floatingPanel.querySelector('.sr-floating-text');
            if (textEl) textEl.textContent = announcement;
            const posEl = this._floatingPanel.querySelector('.sr-floating-position');
            if (posEl && result.position) {
                posEl.textContent = `${result.position.index + 1} / ${result.position.total}`;
            }
        } else {
            // Update docked bar
            srPreviousAnnouncement = document.getElementById('srCaptionText').textContent;
            document.getElementById('srCaptionText').textContent = announcement;
            document.getElementById('srCaptionHistory').textContent = srPreviousAnnouncement || '';
            if (result.position) {
                document.getElementById('srPosition').textContent =
                    `${result.position.index + 1} / ${result.position.total}`;
            }
        }

        // Focus indicator position
        if (result.rect) {
            this.updateFocusIndicator(result.rect);
        }

        // Focus label (role)
        document.getElementById('srFocusLabel').textContent = role;

        // Speech log
        if (announcement) {
            this.appendToLog(announcement, role);
        }
    },

    updateFocusIndicator(vmRect) {
        const indicator = document.getElementById('srFocusIndicator');
        const vncContainer = document.getElementById('vncContainer');
        const canvas = vncContainer.querySelector('canvas');
        if (!canvas) return;

        const canvasRect = canvas.getBoundingClientRect();
        const containerRect = vncContainer.getBoundingClientRect();
        const resolution = currentResolution || { width: canvasRect.width, height: canvasRect.height };
        const scaleX = canvasRect.width / resolution.width;
        const scaleY = canvasRect.height / resolution.height;
        const offsetX = canvasRect.left - containerRect.left;
        const offsetY = canvasRect.top - containerRect.top;

        indicator.style.left = (offsetX + vmRect.x * scaleX) + 'px';
        indicator.style.top = (offsetY + vmRect.y * scaleY) + 'px';
        indicator.style.width = (vmRect.width * scaleX) + 'px';
        indicator.style.height = (vmRect.height * scaleY) + 'px';
    },

    // ── Focus indicator styling ──────────────────
    _applyFocusIndicatorStyle() {
        const profile = this._profile;
        if (!profile) return;
        const fi = profile.focusIndicator;
        const useAlt = fi.altStyle && localStorage.getItem('sr-vo-cursor') === 'true';
        const indicator = document.getElementById('srFocusIndicator');
        const label = document.getElementById('srFocusLabel');

        indicator.style.borderColor = useAlt ? fi.altBorderColor : fi.borderColor;
        indicator.style.borderWidth = (useAlt ? fi.altBorderWidth : fi.borderWidth) + 'px';
        indicator.style.borderRadius = (useAlt ? fi.altBorderRadius : fi.borderRadius) + 'px';
        indicator.style.backgroundColor = useAlt ? fi.altBackgroundColor : fi.backgroundColor;
        indicator.style.boxShadow = `0 0 0 2px ${useAlt ? fi.altShadowColor : fi.shadowColor}`;
        if (label) label.style.background = useAlt ? fi.altBorderColor : fi.borderColor;
    },

    // ── Floating caption ─────────────────────────
    _createFloatingCaption() {
        if (this._floatingPanel) return; // Already exists

        const profile = this._profile;
        const floating = profile.floating;

        const panel = document.createElement('div');
        panel.className = 'sr-floating-caption';
        panel.id = 'srFloatingCaption';

        panel.innerHTML = `
            <div class="sr-floating-header">
                <span class="sr-floating-text"></span>
                <button class="sr-floating-close" title="Stop simulation (Escape)">&times;</button>
            </div>
            <div class="sr-floating-meta">
                <span class="sr-floating-position"></span>
            </div>
        `;

        // Restore saved position or use defaults
        const saved = this._loadFloatingPosition();
        if (saved) {
            panel.style.left = saved.left + 'px';
            panel.style.top = saved.top + 'px';
            if (saved.width) panel.style.width = saved.width + 'px';
            if (saved.height) panel.style.height = saved.height + 'px';
        } else {
            panel.style.left = floating.defaultPosition.left + 'px';
            panel.style.bottom = floating.defaultPosition.bottom + 'px';
            panel.style.width = floating.defaultWidth + 'px';
        }

        panel.style.minWidth = floating.minWidth + 'px';
        panel.style.minHeight = floating.minHeight + 'px';

        // Max width = 80% of canvas
        const canvas = document.querySelector('#vncContainer canvas:not(.device-backdrop)');
        if (canvas) {
            panel.style.maxWidth = Math.round(canvas.offsetWidth * 0.8) + 'px';
        }

        // Close button
        panel.querySelector('.sr-floating-close').addEventListener('click', (e) => {
            e.stopPropagation();
            stopSRSimulation();
        });

        // Insert into VNC container (overlays the canvas)
        document.getElementById('vncContainer').appendChild(panel);
        this._floatingPanel = panel;

        // Setup drag
        this._setupDrag(panel);

        // Track resize for persistence
        this._resizeObserver = new ResizeObserver(() => {
            this._saveFloatingPosition();
        });
        this._resizeObserver.observe(panel);
    },

    _setupDrag(panel) {
        let isDragging = false, startX, startY, startLeft, startTop;

        // Entire panel surface is draggable (like real VoiceOver)
        panel.addEventListener('mousedown', (e) => {
            if (e.target.closest('.sr-floating-close')) return;
            isDragging = true;
            startX = e.clientX;
            startY = e.clientY;
            startLeft = panel.offsetLeft;
            startTop = panel.offsetTop;
            e.preventDefault();
        });

        // Attach to document so dragging continues even when cursor leaves the panel
        const onMove = (e) => {
            if (!isDragging) return;
            panel.style.left = (startLeft + e.clientX - startX) + 'px';
            panel.style.top = (startTop + e.clientY - startY) + 'px';
            panel.style.bottom = 'auto'; // Clear bottom positioning once manually moved
        };

        const onUp = () => {
            if (isDragging) {
                isDragging = false;
                this._saveFloatingPosition();
            }
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);

        // Store cleanup refs
        panel._dragCleanup = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
        };
    },

    _saveFloatingPosition() {
        if (!this._floatingPanel) return;
        const p = this._floatingPanel;
        localStorage.setItem('sr-voiceover-caption-pos', JSON.stringify({
            left: p.offsetLeft, top: p.offsetTop,
            width: p.offsetWidth, height: p.offsetHeight,
        }));
    },

    _loadFloatingPosition() {
        try {
            const raw = localStorage.getItem('sr-voiceover-caption-pos');
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    },

    // ── Speech log ───────────────────────────────
    appendToLog(text, role) {
        const entries = document.getElementById('srSpeechLogEntries');
        if (!entries) return;

        const entry = document.createElement('div');
        entry.className = 'sr-speech-log-entry';
        if (role) {
            entry.innerHTML = `<span class="sr-log-role">${role}</span>${this._escapeHtml(text)}`;
        } else {
            entry.textContent = text;
        }
        entries.appendChild(entry);

        // Cap at 200 entries
        while (entries.children.length > 200) {
            entries.removeChild(entries.firstChild);
        }

        // Auto-scroll
        entries.scrollTop = entries.scrollHeight;
    },

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    },

    toggleSpeechLog() {
        const log = document.getElementById('srSpeechLog');
        if (!log) return;
        this._speechLogVisible = !this._speechLogVisible;
        log.style.display = this._speechLogVisible ? 'flex' : 'none';
        const btn = document.getElementById('srLogBtn');
        if (btn) btn.classList.toggle('active', this._speechLogVisible);
    },

    clearSpeechLog() {
        const entries = document.getElementById('srSpeechLogEntries');
        if (entries) entries.innerHTML = '';
    },

    _hideSpeechLog() {
        this._speechLogVisible = false;
        const log = document.getElementById('srSpeechLog');
        if (log) log.style.display = 'none';
        const btn = document.getElementById('srLogBtn');
        if (btn) btn.classList.remove('active');
    },
};

// SR Popout (launcher dropdown)
function toggleSRPopout() {
    if (srActive) {
        stopSRSimulation();
        return;
    }
    const isOpen = document.getElementById('srPopout').classList.contains('show');
    if (isOpen) {
        closeSRPopout();
    } else {
        openPopout('srPopout', 'srBtn', closeSRPopout);
    }
}

function closeSRPopout() {
    // dismissActivePopout() owns the show-class, aria-expanded, and focus
    // return. Don't touch them manually here — that caused a stale-state
    // bug where the trigger's focus was never restored on close.
    dismissActivePopout();
}

// Start simulation
async function startSRSimulation(screenReader) {
    closeSRPopout();

    const verbosity = document.getElementById('srVerbosity').value;

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/start`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                screenReader,
                verbosity,
                startFromFocus: document.getElementById('srStartFromFocus').checked,
                syncFocus: document.getElementById('srSyncFocus').checked,
                syncMouse: document.getElementById('srSyncMouse').checked,
            })
        });
        const result = await response.json();

        if (!result.ok) {
            showToast('Failed to start SR simulation: ' + (result.error || 'Unknown error'), 'error');
            return;
        }

        // Activate SR state
        srActive = true;
        srScreenReader = screenReader;

        // Load keyboard commands
        if (!srKeyMap) {
            const kcResp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/keyboard-commands`);
            const kcData = await kcResp.json();
            srKeyMap = kcData.commands;
        }

        // Start resolution polling for coordinate mapping
        startSRResolutionPolling();

        // Start mouse tracking if enabled
        if (document.getElementById('srSyncMouse').checked) {
            startSRMouseTracking();
        }

        // Update UI via caption manager
        document.getElementById('srBtn').classList.add('sr-active');
        SRCaptionManager.start(screenReader);

        // Show first element
        if (result.announcement) {
            updateSRUI(result);
        }

        // Highlight active option in popout
        document.querySelectorAll('.sr-option').forEach(o => o.classList.remove('active'));
        const activeOpt = document.querySelector(`.sr-option[data-sr="${screenReader}"]`);
        if (activeOpt) activeOpt.classList.add('active');

    } catch (e) {
        showToast('SR simulation error: ' + e.message, 'error');
    }
}

// Stop simulation
async function stopSRSimulation() {
    try {
        await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/stop`, { method: 'POST' });
    } catch (e) { /* ignore cleanup errors */ }

    srActive = false;
    srScreenReader = null;
    srPreviousAnnouncement = '';
    stopSRResolutionPolling();
    stopSRMouseTracking();

    // Hide UI via caption manager
    document.getElementById('srBtn').classList.remove('sr-active');
    SRCaptionManager.stop();
    document.getElementById('srCheatSheet').style.display = 'none';
    srCheatSheetVisible = false;

    document.querySelectorAll('.sr-option').forEach(o => o.classList.remove('active'));

    showToast('Screen reader simulation ended');
}

// ── Mouse moves SR focus ─────────────────────────────
// When enabled, hovering over elements in the VNC canvas
// moves the SR cursor to that element and announces it.
// Mirrors VoiceOver's "Moves VoiceOver cursor" option.
// ──────────────────────────────────────────────────────
let _srMouseHandler = null;
let _srMouseDebounce = null;

function startSRMouseTracking() {
    const canvas = document.querySelector('#vncContainer canvas:not(.device-backdrop)');
    if (!canvas) return;

    _srMouseHandler = function(e) {
        if (!srActive) return;

        // Debounce: max 5 calls/second
        if (_srMouseDebounce) return;
        _srMouseDebounce = setTimeout(() => { _srMouseDebounce = null; }, 200);

        const vm = _clientToVm(e.clientX, e.clientY);
        if (!vm) return;

        fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/navigate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'point-at', params: { x: vm.x, y: vm.y } })
        })
        .then(r => r.json())
        .then(result => {
            if (result.ok && result.announcement) {
                updateSRUI(result);
                if (document.getElementById('srTTSCheckbox').checked) {
                    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/speak`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: result.announcement, lang: result.language || 'en' })
                    }).catch(() => {});
                }
            }
        })
        .catch(() => {});
    };

    canvas.addEventListener('mousemove', _srMouseHandler);
}

function stopSRMouseTracking() {
    if (_srMouseHandler) {
        const canvas = document.querySelector('#vncContainer canvas:not(.device-backdrop)');
        if (canvas) canvas.removeEventListener('mousemove', _srMouseHandler);
        _srMouseHandler = null;
    }
    if (_srMouseDebounce) {
        clearTimeout(_srMouseDebounce);
        _srMouseDebounce = null;
    }
}

// Navigate (called by keyboard handler)
let _srNavigating = false;
async function srNavigate(action, params) {
    if (!srActive || _srNavigating) return;
    _srNavigating = true;

    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/navigate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action, params })
        });
        const result = await response.json();

        if (result.ok) {
            updateSRUI(result);

            // TTS
            if (document.getElementById('srTTSCheckbox').checked && result.announcement) {
                fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/speak`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: result.announcement,
                        lang: result.language || 'en'
                    })
                }).catch(() => {});
            }

            // Auto-scroll
            if (result.rect) {
                fetch(`http://${VNC_HOST}:${CONTROL_PORT}/sr/scroll`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ y: result.rect.y })
                }).then(r => r.json()).then(scrollResult => {
                    // Update focus indicator with new rect after scroll
                    if (scrollResult.ok && scrollResult.rect) {
                        updateSRFocusIndicator(scrollResult.rect);
                    }
                }).catch(() => {});
            }
        }
    } catch (e) {
        console.error('SR navigate error:', e);
    } finally {
        _srNavigating = false;
    }
}

// Update all SR UI elements
// Delegates to SRCaptionManager for per-SR UI updates
function updateSRUI(result) {
    SRCaptionManager.update(result);
}

// Delegates to SRCaptionManager for focus indicator positioning
function updateSRFocusIndicator(vmRect) {
    SRCaptionManager.updateFocusIndicator(vmRect);
}

// TTS toggle
function toggleSRTTS() {
    const cb = document.getElementById('srTTSCheckbox');
    cb.checked = !cb.checked;
    const btn = document.getElementById('srTTSBtn');
    btn.classList.toggle('active', cb.checked);
}

// VoiceOver cursor toggle — persists preference and re-applies focus style
function onVOCursorToggle() {
    const checked = document.getElementById('srVOCursor').checked;
    localStorage.setItem('sr-vo-cursor', checked ? 'true' : 'false');
    if (srActive && srScreenReader === 'voiceover') {
        SRCaptionManager._applyFocusIndicatorStyle();
    }
}
// Restore VO cursor checkbox from localStorage on page load
(function() {
    const cb = document.getElementById('srVOCursor');
    if (cb && localStorage.getItem('sr-vo-cursor') === 'true') cb.checked = true;
})();

// Cheat sheet
function toggleSRCheatSheet() {
    const sheet = document.getElementById('srCheatSheet');
    if (srCheatSheetVisible) {
        sheet.style.display = 'none';
        srCheatSheetVisible = false;
    } else {
        buildSRCheatSheet();
        sheet.style.display = 'flex';
        srCheatSheetVisible = true;
    }
}

function buildSRCheatSheet() {
    if (!srKeyMap || !srScreenReader) return;

    const templates = srKeyMap._cheat_sheet_templates;
    if (!templates || !templates[srScreenReader]) return;

    const srNames = { jaws: 'JAWS', nvda: 'NVDA', voiceover: 'VoiceOver' };
    document.getElementById('srCheatTitle').textContent =
        srNames[srScreenReader] + ' Shortcuts';

    const grid = document.getElementById('srCheatGrid');
    grid.innerHTML = '';

    const sections = templates[srScreenReader];
    for (const [sectionName, shortcuts] of Object.entries(sections)) {
        const title = document.createElement('div');
        title.className = 'sr-cheat-section-title';
        title.textContent = sectionName;
        grid.appendChild(title);

        for (const [key, desc] of shortcuts) {
            const row = document.createElement('div');
            row.className = 'sr-cheat-row';
            const keySpan = document.createElement('span');
            keySpan.className = 'sr-cheat-key';
            keySpan.textContent = key;
            const descSpan = document.createElement('span');
            descSpan.className = 'sr-cheat-desc';
            descSpan.textContent = desc;
            row.appendChild(keySpan);
            row.appendChild(descSpan);
            grid.appendChild(row);
        }
    }
}

// SR Keyboard interception (capture phase — before VNC gets the keys)
document.addEventListener('keydown', (e) => {
    if (!srActive) return;

    // Don't intercept when terminal is focused
    const termOverlay = document.getElementById('terminalOverlay');
    if (termOverlay && termOverlay.classList.contains('open')) return;

    // Don't intercept when a UI input (address bar, search, etc.) is focused
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) return;

    // Cheat sheet: dismiss on any key
    if (srCheatSheetVisible) {
        if (e.key !== '?' && e.key !== 'F1') {
            toggleSRCheatSheet();
            e.preventDefault();
            e.stopPropagation();
            return;
        }
    }

    // Map key to SR action
    const action = mapSRKeyToAction(e);
    if (!action) return;

    e.preventDefault();
    e.stopPropagation();

    // Handle special actions
    if (action === 'toggle-cheat-sheet') {
        toggleSRCheatSheet();
        return;
    }
    if (action === 'stop-simulation') {
        stopSRSimulation();
        return;
    }

    // Navigate
    srNavigate(action.action || action, action.params);

}, true);  // capture phase

// Key mapping
function mapSRKeyToAction(event) {
    if (event.key === 'Escape') return 'stop-simulation';
    if (event.key === '?' || event.key === 'F1') return 'toggle-cheat-sheet';

    if (!srKeyMap || !srScreenReader) return null;

    const sr = srKeyMap[srScreenReader];
    if (!sr) return null;

    // Get the reading/browse mode
    const mode = sr.reading || sr.browse;
    if (!mode) return null;

    const key = event.key;
    const shift = event.shiftKey;

    // Quick nav (single letter shortcuts: h, k, f, b, t, l, i, g, r, etc.)
    const quickNav = mode.quick_nav || {};
    if (!event.ctrlKey && !event.altKey && !event.metaKey) {
        // Try with Shift prefix
        if (shift) {
            const shiftCombo = 'Shift+' + key.toLowerCase();
            if (quickNav[shiftCombo]) return quickNav[shiftCombo];
        }

        // Single letter (lowercase)
        if (key.length === 1 && !shift) {
            if (quickNav[key]) return quickNav[key];
            if (quickNav[key.toLowerCase()]) return quickNav[key.toLowerCase()];
        }

        // Number keys for heading levels
        if (key >= '1' && key <= '6') {
            const headingEntry = quickNav[key];
            if (headingEntry) {
                return { action: headingEntry.action, params: { level: parseInt(key) } };
            }
        }
    }

    // Navigation keys (arrows, Tab, Home, End)
    // Check modifier combos BEFORE plain key (Shift+Tab before Tab)
    const nav = mode.navigation || {};

    if (event.ctrlKey) {
        const ctrlCombo = 'Ctrl+' + key;
        if (nav[ctrlCombo]) return nav[ctrlCombo];
    }

    if (shift) {
        const shiftCombo = 'Shift+' + key;
        if (nav[shiftCombo]) return nav[shiftCombo];
    }

    if (nav[key]) return nav[key];

    // Action keys (Enter, Space)
    const actions = mode.actions || {};
    if (actions[key]) return actions[key];

    return null;
}

// Resolution tracking for focus indicator coordinate mapping
let currentResolution = null;
let srResolutionPollTimer = null;

function startSRResolutionPolling() {
    if (srResolutionPollTimer) return; // Already polling
    async function poll() {
        if (!srActive) { srResolutionPollTimer = null; return; }
        try {
            const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/resolution`);
            const data = await resp.json();
            if (data.ok) currentResolution = { width: data.width, height: data.height };
        } catch (e) {}
        srResolutionPollTimer = setTimeout(poll, 5000);
    }
    poll();
}

function stopSRResolutionPolling() {
    if (srResolutionPollTimer) {
        clearTimeout(srResolutionPollTimer);
        srResolutionPollTimer = null;
    }
}
