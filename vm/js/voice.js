// =============================================
// Voice Command System (Push-to-Talk + Continuous)
// =============================================
// Two modes, both triggered by F8 (or Cmd+Shift+Space):
//   - Hold F8:  push-to-talk (speak while held, executes on release)
//   - Tap F8:   toggle continuous mode (executes after each sentence)
//
// Uses Web Speech API for recognition, routes transcript
// to inspekt commands via control server REST API.

let _voiceRecognition = null;
let _voiceTranscript = '';
let _voiceIsListening = false;
let _voicePageLang = 'en';
let _voiceMode = 'idle'; // 'idle' | 'hold' | 'continuous'

// Threshold (ms) to distinguish a tap from a hold
const VOICE_TAP_THRESHOLD = 300;
let _voiceKeyDownTime = 0;
let _voiceKeyHeld = false;

// Fetch the current page language from the VM's active tab.
// Called on navigation changes by updateCurrentUrl() in navigation.js.
async function updateVoicePageLang() {
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/page-info`, { signal: AbortSignal.timeout(2000) });
        const data = await resp.json();
        const lang = data?.data?.meta?.specifiedLanguage || data?.meta?.specifiedLanguage;
        if (data.ok && lang) {
            _voicePageLang = lang;
            console.log('[Voice] Page language:', _voicePageLang);
        }
    } catch {}
}

// ── Direct command patterns ──
// Matched before falling back to `inspekt do`
const VOICE_COMMANDS = [
    { pattern: /^(?:go\s+)?back$/i,                          action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/back`) },
    { pattern: /^(?:go\s+)?forward$/i,                       action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/forward`) },
    { pattern: /^reload|refresh$/i,                           action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/reload-page`) },
    { pattern: /^page\s*up|scroll\s*up$/i,                    action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/keys/send?keys=Page_Up`) },
    { pattern: /^page\s*down|scroll\s*down$/i,                action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/keys/send?keys=Page_Down`) },
    { pattern: /^(?:go\s+to\s+)?(?:the\s+)?top|scroll.*top$/i, action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/keys/send?keys=Home`) },
    { pattern: /^(?:go\s+to\s+)?(?:the\s+)?bottom|scroll.*bottom$/i, action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/keys/send?keys=End`) },
    { pattern: /^(?:take\s+a?\s*)?screenshot$/i,              action: () => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/screenshot/viewport`) },
    { pattern: /^(?:go\s+to|open|navigate\s+to)\s+(https?:\/\/.+)$/i, action: (m) => fetch(`http://${VNC_HOST}:${CONTROL_PORT}/navigate?url=${encodeURIComponent(m[1])}`) },
    { pattern: /^stop(?:\s+listening)?$/i,                    action: () => { _stopContinuousMode(); return Promise.resolve(); } },
];

// ── Recognition setup ──

async function _createRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        showToast('Speech recognition is not supported in this browser', { type: 'error' });
        return null;
    }

    // Fetch current page language
    try {
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/page-info`, { signal: AbortSignal.timeout(1500) });
        const data = await resp.json();
        const lang = data?.data?.meta?.specifiedLanguage || data?.meta?.specifiedLanguage;
        if (data.ok && lang) {
            _voicePageLang = lang;
        }
    } catch {}

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    const langMap = { en: 'en-US', nl: 'nl-NL', fr: 'fr-FR', de: 'de-DE', es: 'es-ES',
                      pt: 'pt-PT', it: 'it-IT', pl: 'pl-PL', ja: 'ja-JP', ko: 'ko-KR',
                      zh: 'zh-CN', ar: 'ar-SA', ru: 'ru-RU', sv: 'sv-SE', da: 'da-DK' };
    const pageLang = (_voicePageLang || 'en').split('-')[0].toLowerCase();
    recognition.lang = langMap[pageLang] || _voicePageLang || 'en-US';

    return recognition;
}

function _showOverlay(mode) {
    const overlay = document.getElementById('voiceOverlay');
    const transcriptEl = document.getElementById('voiceTranscript');
    const langLabel = document.getElementById('voiceLang');
    const hintEl = document.querySelector('.voice-hint');

    if (overlay) {
        overlay.classList.remove('error');
        overlay.classList.add('active');
        overlay.dataset.mode = mode;
    }
    if (langLabel && _voiceRecognition) langLabel.textContent = _voiceRecognition.lang;
    if (transcriptEl) {
        transcriptEl.textContent = 'Listening\u2026';
        transcriptEl.classList.add('interim');
    }
    if (hintEl) {
        hintEl.style.display = mode === 'continuous' ? '' : 'none';
        hintEl.textContent = 'Tap F8 to stop';
    }
}

function _hideOverlay() {
    const overlay = document.getElementById('voiceOverlay');
    if (overlay) overlay.classList.remove('active', 'error');
    const hintEl = document.querySelector('.voice-hint');
    if (hintEl) hintEl.style.display = 'none';
}

// ── Hold mode (push-to-talk) ──

async function startHoldMode() {
    if (_voiceIsListening) return;

    const recognition = await _createRecognition();
    if (!recognition) return;

    _voiceIsListening = true;
    _voiceMode = 'hold';
    _voiceTranscript = '';
    _voiceRecognition = recognition;

    const transcriptEl = document.getElementById('voiceTranscript');

    recognition.onresult = (event) => {
        let interim = '';
        let final_ = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) final_ += event.results[i][0].transcript;
            else interim += event.results[i][0].transcript;
        }
        if (final_) _voiceTranscript += final_;
        if (transcriptEl) {
            const display = _voiceTranscript + interim;
            transcriptEl.textContent = display || 'Listening\u2026';
            transcriptEl.classList.toggle('interim', !display);
        }
    };

    recognition.onerror = (event) => {
        console.warn('[Voice] Error:', event.error);
        const overlay = document.getElementById('voiceOverlay');
        if (overlay) overlay.classList.add('error');
        if (transcriptEl) {
            transcriptEl.textContent = event.error === 'not-allowed' ? 'Microphone access denied' : `Error: ${event.error}`;
            transcriptEl.classList.remove('interim');
        }
    };

    recognition.onend = () => {};

    _showOverlay('hold');
    try { recognition.start(); } catch (e) {
        console.error('[Voice] Failed to start:', e);
        _voiceIsListening = false;
        _voiceMode = 'idle';
        _hideOverlay();
    }
}

function stopHoldMode() {
    if (!_voiceIsListening || _voiceMode !== 'hold') return;
    _voiceIsListening = false;
    _voiceMode = 'idle';

    if (!_voiceRecognition) return;

    _voiceRecognition.onend = () => {
        _voiceRecognition = null;
        _hideOverlay();
        const transcript = _voiceTranscript.trim();
        if (transcript) {
            console.log('[Voice] Hold transcript:', transcript);
            routeVoiceCommand(transcript);
        }
    };

    try { _voiceRecognition.stop(); } catch {}
}

// ── Continuous mode (tap to toggle) ──

async function startContinuousMode() {
    if (_voiceIsListening) return;

    const recognition = await _createRecognition();
    if (!recognition) return;

    _voiceIsListening = true;
    _voiceMode = 'continuous';
    _voiceTranscript = '';
    _voiceRecognition = recognition;

    const transcriptEl = document.getElementById('voiceTranscript');

    recognition.onresult = (event) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            if (event.results[i].isFinal) {
                const sentence = event.results[i][0].transcript.trim();
                if (sentence) {
                    console.log('[Voice] Continuous sentence:', sentence);
                    // Show what we're executing
                    if (transcriptEl) {
                        transcriptEl.textContent = sentence;
                        transcriptEl.classList.remove('interim');
                    }
                    // Execute, then reset display
                    routeVoiceCommand(sentence).then(() => {
                        if (_voiceMode === 'continuous' && transcriptEl) {
                            transcriptEl.textContent = 'Listening\u2026';
                            transcriptEl.classList.add('interim');
                        }
                    });
                }
            } else {
                interim += event.results[i][0].transcript;
            }
        }
        // Show interim text while speaking
        if (interim && transcriptEl) {
            transcriptEl.textContent = interim;
            transcriptEl.classList.add('interim');
        }
    };

    recognition.onerror = (event) => {
        console.warn('[Voice] Error:', event.error);
        if (event.error === 'no-speech' || event.error === 'aborted') return; // normal in continuous
        const overlay = document.getElementById('voiceOverlay');
        if (overlay) overlay.classList.add('error');
        if (transcriptEl) {
            transcriptEl.textContent = `Error: ${event.error}`;
            transcriptEl.classList.remove('interim');
        }
    };

    // Web Speech API can stop unexpectedly — restart in continuous mode
    recognition.onend = () => {
        if (_voiceMode === 'continuous') {
            console.log('[Voice] Restarting continuous recognition');
            try { recognition.start(); } catch {
                _stopContinuousMode();
            }
        }
    };

    _showOverlay('continuous');
    try { recognition.start(); } catch (e) {
        console.error('[Voice] Failed to start:', e);
        _voiceIsListening = false;
        _voiceMode = 'idle';
        _hideOverlay();
    }
}

function _stopContinuousMode() {
    if (_voiceMode !== 'continuous') return;
    _voiceIsListening = false;
    _voiceMode = 'idle';

    if (_voiceRecognition) {
        _voiceRecognition.onend = () => {}; // prevent auto-restart
        try { _voiceRecognition.stop(); } catch {}
        _voiceRecognition = null;
    }

    _hideOverlay();
    showToast('Voice control stopped', { type: 'info', duration: 1500 });
}

// ── Logging ──

function _voiceLog(level, message, detail) {
    const ts = new Date().toLocaleTimeString('en-GB', { hour12: false });
    const prefix = `[Voice ${ts}]`;
    const line = detail ? `${prefix} ${message}: ${detail}` : `${prefix} ${message}`;
    console[level === 'error' ? 'error' : level === 'warn' ? 'warn' : 'log'](line);

    // Also log to control server (appends to /tmp/voice.log inside container)
    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/api/internal/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'voice', level, message: line }),
    }).catch(() => {});
}

// ── Command routing ──

async function routeVoiceCommand(text) {
    _voiceLog('info', 'Routing command', text);

    // Try direct command patterns first
    for (const cmd of VOICE_COMMANDS) {
        const match = text.match(cmd.pattern);
        if (match) {
            _voiceLog('info', 'Direct match', cmd.pattern.source);
            try {
                await cmd.action(match);
                showToast(text, { type: 'success', duration: 2000 });
            } catch (e) {
                _voiceLog('error', 'Direct command failed', e.message);
            }
            return;
        }
    }

    // Fallback: route to `inspekt do`
    _voiceLog('info', 'Routing to inspekt do', text);
    try {
        const encoded = encodeURIComponent(`do "${text}"`);
        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/inspekt/${encoded}`);
        const data = await resp.json();
        if (data.ok) {
            _voiceLog('info', 'Action executed', data.output?.substring(0, 200));
            showToast('Action executed', { type: 'success', duration: 2000 });
        } else {
            _voiceLog('warn', 'No match', data.error || 'unknown');
        }
    } catch (e) {
        _voiceLog('error', 'inspekt do failed', e.message);
    }
}

// ── Tauri event listener ──

window.addEventListener('tauri-menu', (e) => {
    const action = e.detail?.action;
    if (action === 'voiceStart') startHoldMode();
    if (action === 'voiceStop') stopHoldMode();
});

// ── Keyboard handler ──
// Tap F8 = toggle continuous mode
// Hold F8 = push-to-talk (hold to speak, release to execute)

function _isVoiceKey(e) {
    return e.code === 'F8' || (e.code === 'Space' && (e.metaKey || e.ctrlKey) && e.shiftKey);
}

window.addEventListener('keydown', (e) => {
    if (_isVoiceKey(e) && !e.repeat) {
        e.preventDefault();
        e.stopPropagation();

        // If continuous mode is active, stop it
        if (_voiceMode === 'continuous') {
            _stopContinuousMode();
            return;
        }

        _voiceKeyHeld = true;
        _voiceKeyDownTime = Date.now();

        // Start recognition immediately (works for both tap and hold)
        startHoldMode();
    }
}, true);

window.addEventListener('keyup', (e) => {
    if (!_voiceKeyHeld || !(e.code === 'F8' || e.code === 'Space')) return;

    const holdDuration = Date.now() - _voiceKeyDownTime;
    _voiceKeyHeld = false;

    if (holdDuration < VOICE_TAP_THRESHOLD) {
        // Short tap — switch to continuous mode
        // Stop the hold-mode recognition first, then start continuous
        if (_voiceRecognition) {
            _voiceRecognition.onend = () => {};
            try { _voiceRecognition.stop(); } catch {}
            _voiceRecognition = null;
        }
        _voiceIsListening = false;
        _voiceMode = 'idle';
        console.log('[Voice] Tap detected — entering continuous mode');
        startContinuousMode();
    } else {
        // Long hold — stop and execute (normal push-to-talk)
        console.log('[Voice] Hold released — executing');
        stopHoldMode();
    }
}, true);
