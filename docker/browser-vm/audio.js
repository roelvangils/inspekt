/**
 * Audio Streaming — WebSocket-based audio from VM to browser.
 *
 * Streams audio from the VM via WebSocket using MediaSource Extensions (MSE).
 * Audio is encoded as WebM/Opus in the VM and fed to a <audio> element via
 * a SourceBuffer in sequence mode.
 *
 * Globals this module reads:
 *   VNC_HOST — VM hostname (from control-panel.html)
 *   showToast(message, type) — toast notifications (from control-panel.html)
 *
 * Globals this module exposes:
 *   toggleAudio() — toggle audio on/off
 *   isAudioEnabled — current audio state
 *   updateAudioButton() — sync button UI with state
 */

// =============================================
// Audio Streaming
// =============================================

const AUDIO_PORT = 6081;
let isAudioEnabled = false;
let audioSocket = null;
let audioElement = null;
let mediaSource = null;
let sourceBuffer = null;
let audioDataQueue = [];
let directFeed = true;

function initAudioElement() {
    if (!audioElement) {
        audioElement = document.createElement('audio');
        audioElement.id = 'vmAudio';
        document.body.appendChild(audioElement);
    }
}

function updateAudioButton() {
    const iconOff = document.getElementById('audioIconOff');
    const iconOn = document.getElementById('audioIconOn');
    const btn = document.getElementById('audioBtn');

    if (isAudioEnabled) {
        iconOff.style.display = 'none';
        iconOn.style.display = 'block';
        btn.classList.add('active');
    } else {
        iconOff.style.display = 'block';
        iconOn.style.display = 'none';
        btn.classList.remove('active');
    }
}

async function toggleAudio() {
    if (isAudioEnabled) {
        await stopAudio();
        showToast('Audio disabled', 'info');
    } else {
        await startAudio();
    }
    updateAudioButton();
}

async function startAudio() {
    if (isAudioEnabled) return;

    initAudioElement();

    const mime = 'audio/webm; codecs="opus"';
    if (!MediaSource.isTypeSupported(mime)) {
        showToast('Audio codec not supported by browser', 'error');
        return;
    }

    try {
        mediaSource = new MediaSource();
        audioElement.src = URL.createObjectURL(mediaSource);

        await new Promise((resolve, reject) => {
            mediaSource.addEventListener('sourceopen', () => {
                try {
                    sourceBuffer = mediaSource.addSourceBuffer(mime);
                    sourceBuffer.mode = 'sequence';

                    sourceBuffer.addEventListener('updateend', () => {
                        if (sourceBuffer.updating) return;

                        if (audioDataQueue.length === 0) {
                            directFeed = true;
                            return;
                        }

                        const data = audioDataQueue.shift();
                        try {
                            sourceBuffer.appendBuffer(data);
                        } catch (e) {
                            if (e.name === 'QuotaExceededError') {
                                emptyAudioBuffer();
                            }
                        }
                    });

                    resolve();
                } catch (e) {
                    reject(e);
                }
            }, { once: true });

            mediaSource.addEventListener('error', reject, { once: true });
        });

        // Connect to audio WebSocket.
        // Specify 'binary' subprotocol — websockify requires it for
        // raw binary data (without it, data may be base64-encoded).
        const wsUrl = `ws://${VNC_HOST}:${AUDIO_PORT}`;
        audioSocket = new WebSocket(wsUrl);
        audioSocket.binaryType = 'arraybuffer';

        audioSocket.addEventListener('open', async () => {
            console.log('[Audio] WebSocket connected');
            isAudioEnabled = true;
            updateAudioButton();

            // Try to play immediately — the user's click on the audio
            // button counts as a user gesture for autoplay policy.
            audioElement.playbackRate = 1.003; // Slight speedup to reduce drift
            try {
                await audioElement.play();
                console.log('[Audio] Playback started');
                showToast('Audio enabled', 'success');
            } catch (e) {
                if (e.name === 'NotAllowedError') {
                    // Autoplay blocked — wait for a user click
                    console.log('[Audio] Autoplay blocked, waiting for click');
                    showToast('Audio enabled — click anywhere to start playback', 'success');
                    document.body.addEventListener('click', async () => {
                        try {
                            await audioElement.play();
                            console.log('[Audio] Playback started (after click)');
                        } catch (err) {
                            console.error('[Audio] Playback error:', err);
                        }
                    }, { capture: true, once: true });
                } else if (e.name !== 'AbortError') {
                    console.error('[Audio] Playback error:', e);
                }
            }
        });

        audioSocket.addEventListener('message', (event) => {
            feedAudioData(event.data);
        });

        audioSocket.addEventListener('error', async () => {
            console.error('[Audio] WebSocket error');
            showToast('Audio connection failed', 'error');
            await stopAudio();
        });

        audioSocket.addEventListener('close', async () => {
            console.log('[Audio] WebSocket closed');
            if (isAudioEnabled) {
                showToast('Audio connection closed', 'info');
                await stopAudio();
            }
        });

    } catch (e) {
        console.error('[Audio] Setup error:', e);
        showToast(`Audio setup failed: ${e.message}`, 'error');
        await stopAudio();
    }
}

function feedAudioData(data) {
    if (!sourceBuffer || mediaSource.readyState !== 'open') return;

    if (directFeed && !sourceBuffer.updating) {
        try {
            sourceBuffer.appendBuffer(data);
            directFeed = false;
        } catch (e) {
            if (e.name === 'QuotaExceededError') {
                emptyAudioBuffer();
                audioDataQueue.push(data);
            }
        }
    } else {
        audioDataQueue.push(data);
    }
}

function emptyAudioBuffer() {
    if (!sourceBuffer || sourceBuffer.buffered.length === 0) return;
    const bufferEnd = sourceBuffer.buffered.end(0);
    const removeEnd = bufferEnd - 30; // Keep 30 seconds
    if (removeEnd > 0) {
        sourceBuffer.remove(0, removeEnd);
    }
}

async function stopAudio() {
    isAudioEnabled = false;
    directFeed = true;
    audioDataQueue = [];

    if (audioSocket) {
        audioSocket.close();
        audioSocket = null;
    }

    if (audioElement) {
        audioElement.pause();
        audioElement.removeAttribute('src');
        audioElement.currentTime = 0;
    }

    if (mediaSource && mediaSource.readyState === 'open') {
        try {
            mediaSource.endOfStream();
        } catch (e) {}
    }
    mediaSource = null;
    sourceBuffer = null;

    updateAudioButton();
}
