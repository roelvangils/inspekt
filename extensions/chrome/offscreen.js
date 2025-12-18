/**
 * Offscreen Document for Clipboard and Video Capture Operations
 *
 * Chrome Manifest V3 service workers don't have access to:
 * - Clipboard API with images
 * - MediaRecorder for video capture
 *
 * This offscreen document runs in a DOM context and provides these capabilities.
 */

console.log('[Offscreen] Clipboard and video capture handler loaded');

// Video capture state
let mediaRecorder = null;
let recordedChunks = [];
let mediaStream = null;
let captureStartTime = null;

// Listen for messages from the background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[Offscreen] Received message:', message.type, 'target:', message.target);

    // Only process messages meant for the offscreen document
    if (message.target !== 'offscreen') {
        return false;
    }

    // Video capture: Start recording
    if (message.type === 'OFFSCREEN_START_VIDEO_CAPTURE') {
        console.log('[Offscreen] Starting video capture...');
        startVideoCapture(message.streamId, message.settings)
            .then(() => {
                console.log('[Offscreen] Video capture started successfully');
                sendResponse({ success: true });
            })
            .catch((error) => {
                console.error('[Offscreen] Failed to start video capture:', error);
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    // Video capture: Stop recording and get video data
    if (message.type === 'OFFSCREEN_STOP_VIDEO_CAPTURE') {
        console.log('[Offscreen] Stopping video capture...');
        stopVideoCapture()
            .then((videoData) => {
                console.log('[Offscreen] Video capture stopped, data size:', videoData?.size || 0);
                sendResponse({ success: true, videoData: videoData });
            })
            .catch((error) => {
                console.error('[Offscreen] Failed to stop video capture:', error);
                sendResponse({ success: false, error: error.message });
            });
        return true;
    }

    // Video capture: Get status
    if (message.type === 'OFFSCREEN_VIDEO_STATUS') {
        const status = {
            recording: mediaRecorder?.state === 'recording',
            duration: captureStartTime ? (Date.now() - captureStartTime) / 1000 : 0,
            chunksCount: recordedChunks.length
        };
        sendResponse({ success: true, status: status });
        return false;
    }

    if (message.type === 'OFFSCREEN_COPY_IMAGE') {
        console.log('[Offscreen] Processing clipboard copy request...');

        copyImageToClipboard(message.dataUrl)
            .then(() => {
                console.log('[Offscreen] Image successfully copied to clipboard');
                sendResponse({ success: true });
            })
            .catch((error) => {
                console.error('[Offscreen] Failed to copy image:', error);
                sendResponse({ success: false, error: error.message });
            });

        return true; // Keep message channel open for async response
    }

    // Don't respond to messages not meant for us
    return false;
});

/**
 * Copy image to clipboard from data URL
 * @param {string} dataUrl - Image data URL (base64 encoded)
 * @returns {Promise<void>}
 */
async function copyImageToClipboard(dataUrl) {
    try {
        // Convert data URL to blob
        const response = await fetch(dataUrl);
        const blob = await response.blob();

        console.log('[Offscreen] Converted data URL to blob, size:', blob.size);

        // Focus the document before clipboard write (required by Chrome)
        window.focus();

        // Use a textarea workaround for clipboard write
        // This is more reliable than navigator.clipboard in offscreen documents
        await writeImageToClipboardViaDOM(blob);

        console.log('[Offscreen] Successfully wrote image to clipboard');
    } catch (error) {
        console.error('[Offscreen] Clipboard write failed:', error);
        throw error;
    }
}

/**
 * Write image to clipboard using button click workaround
 * Offscreen documents need a user gesture to write to clipboard
 * We simulate this by creating a button and programmatically clicking it
 * @param {Blob} blob - Image blob
 * @returns {Promise<void>}
 */
async function writeImageToClipboardViaDOM(blob) {
    console.log('[Offscreen] Using button-click workaround for clipboard write...');

    return new Promise((resolve, reject) => {
        // Create a button that will trigger the clipboard write
        const button = document.createElement('button');
        button.textContent = 'Copy';
        button.style.position = 'fixed';
        button.style.top = '0';
        button.style.left = '0';
        document.body.appendChild(button);

        // Add click handler that does the clipboard write
        button.addEventListener('click', async () => {
            try {
                console.log('[Offscreen] Button clicked, writing to clipboard...');

                // Create ClipboardItem with the image
                const clipboardItem = new ClipboardItem({
                    'image/png': blob
                });

                // Write to clipboard (this works because it's in a click handler)
                await navigator.clipboard.write([clipboardItem]);

                console.log('[Offscreen] Clipboard write successful!');

                // Clean up
                document.body.removeChild(button);
                resolve();
            } catch (error) {
                console.error('[Offscreen] Clipboard write failed:', error);
                document.body.removeChild(button);
                reject(error);
            }
        });

        // Programmatically click the button to trigger the handler
        console.log('[Offscreen] Programmatically clicking button...');
        button.click();
    });
}

// ============================================================================
// VIDEO CAPTURE FUNCTIONS
// ============================================================================

/**
 * Start video capture using MediaRecorder
 * @param {string} streamId - Media stream ID from tabCapture
 * @param {object} settings - Capture settings (fps, quality, etc.)
 */
async function startVideoCapture(streamId, settings = {}) {
    console.log('[Offscreen] Starting video capture with streamId:', streamId);

    // Clean up any previous recording
    if (mediaRecorder) {
        try {
            mediaRecorder.stop();
        } catch (e) {}
        mediaRecorder = null;
    }
    if (mediaStream) {
        mediaStream.getTracks().forEach(track => track.stop());
        mediaStream = null;
    }
    recordedChunks = [];

    try {
        // Get the media stream from the stream ID
        mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: false,
            video: {
                mandatory: {
                    chromeMediaSource: 'tab',
                    chromeMediaSourceId: streamId
                }
            }
        });

        console.log('[Offscreen] Got media stream:', mediaStream.getVideoTracks()[0]?.getSettings());

        // Configure MediaRecorder
        const fps = settings.fps || 15;
        const quality = settings.quality || 80;

        // Choose codec - prefer VP9 for better quality, fall back to VP8
        let mimeType = 'video/webm;codecs=vp9';
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = 'video/webm;codecs=vp8';
        }
        if (!MediaRecorder.isTypeSupported(mimeType)) {
            mimeType = 'video/webm';
        }

        console.log('[Offscreen] Using MIME type:', mimeType);

        // Calculate bitrate based on quality (rough estimate)
        // Higher quality = higher bitrate
        const videoBitsPerSecond = Math.round(2000000 * (quality / 100)); // 2 Mbps at 100%

        mediaRecorder = new MediaRecorder(mediaStream, {
            mimeType: mimeType,
            videoBitsPerSecond: videoBitsPerSecond
        });

        // Collect data chunks
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                recordedChunks.push(event.data);
                console.log('[Offscreen] Recorded chunk:', event.data.size, 'bytes, total chunks:', recordedChunks.length);
            }
        };

        mediaRecorder.onerror = (event) => {
            console.error('[Offscreen] MediaRecorder error:', event.error);
        };

        mediaRecorder.onstop = () => {
            console.log('[Offscreen] MediaRecorder stopped, total chunks:', recordedChunks.length);
        };

        // Start recording with timeslice for regular data chunks (every 1 second)
        mediaRecorder.start(1000);
        captureStartTime = Date.now();

        console.log('[Offscreen] MediaRecorder started, state:', mediaRecorder.state);

    } catch (error) {
        console.error('[Offscreen] Failed to start video capture:', error);
        throw error;
    }
}

/**
 * Stop video capture and return the recorded data as base64
 * @returns {Promise<object>} Object with base64 video data and metadata
 */
async function stopVideoCapture() {
    console.log('[Offscreen] Stopping video capture...');

    if (!mediaRecorder) {
        console.log('[Offscreen] No active recording');
        return null;
    }

    return new Promise((resolve, reject) => {
        const duration = captureStartTime ? (Date.now() - captureStartTime) / 1000 : 0;

        mediaRecorder.onstop = async () => {
            console.log('[Offscreen] MediaRecorder stopped, processing', recordedChunks.length, 'chunks');

            try {
                // Stop all tracks
                if (mediaStream) {
                    mediaStream.getTracks().forEach(track => track.stop());
                    mediaStream = null;
                }

                if (recordedChunks.length === 0) {
                    console.log('[Offscreen] No chunks recorded');
                    resolve(null);
                    return;
                }

                // Combine chunks into a single blob
                const blob = new Blob(recordedChunks, { type: 'video/webm' });
                console.log('[Offscreen] Created blob, size:', blob.size);

                // Convert to base64
                const reader = new FileReader();
                reader.onloadend = () => {
                    const base64 = reader.result.split(',')[1]; // Remove data URL prefix
                    console.log('[Offscreen] Converted to base64, length:', base64.length);

                    resolve({
                        data: base64,
                        mimeType: 'video/webm',
                        size: blob.size,
                        duration: duration
                    });
                };
                reader.onerror = () => {
                    reject(new Error('Failed to convert video to base64'));
                };
                reader.readAsDataURL(blob);

            } catch (error) {
                console.error('[Offscreen] Error processing video:', error);
                reject(error);
            } finally {
                // Clean up
                mediaRecorder = null;
                recordedChunks = [];
                captureStartTime = null;
            }
        };

        // Request final data and stop
        if (mediaRecorder.state === 'recording') {
            mediaRecorder.requestData(); // Get any pending data
            mediaRecorder.stop();
        } else {
            console.log('[Offscreen] MediaRecorder not recording, state:', mediaRecorder.state);
            resolve(null);
        }
    });
}
