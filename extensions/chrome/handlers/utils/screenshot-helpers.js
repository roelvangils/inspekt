/**
 * Screenshot utilities for capturing element screenshots
 */

/**
 * Screenshot cache to avoid redundant captures
 */
const screenshotCache = {
    selector: null,
    bounds: null,
    scrollX: null,
    scrollY: null,
    blob: null,
    timestamp: null
};

/**
 * Check if cached screenshot is still valid
 * @param {string} selector - Element selector
 * @param {Object} newBounds - Current element bounds
 * @returns {boolean} True if cache is valid
 */
function isCacheValid(selector, newBounds) {
    if (!screenshotCache.blob || screenshotCache.selector !== selector) {
        return false;
    }

    const cached = screenshotCache.bounds;

    // Compare bounds (must match exactly)
    if (cached.x !== newBounds.x || cached.y !== newBounds.y ||
        cached.width !== newBounds.width || cached.height !== newBounds.height) {
        return false;
    }

    // Compare scroll position
    if (cached.scrollX !== newBounds.scrollX || cached.scrollY !== newBounds.scrollY) {
        return false;
    }

    // Compare device pixel ratio (in case window moved between displays)
    if (cached.devicePixelRatio !== newBounds.devicePixelRatio) {
        return false;
    }

    return true;
}

/**
 * Capture a screenshot of a specific element
 * @param {Object} element - Element object with bounds information
 * @returns {Promise<Blob>} Screenshot image as blob
 */
export async function captureElementScreenshot(element) {
    console.log('[Screenshot Helpers] Starting capture for element:', element.selector);

    // Get the element's position and size
    const rect = await getElementBounds(element);
    console.log('[Screenshot Helpers] Got element bounds:', rect);

    if (!rect) {
        throw new Error('Could not get element bounds');
    }

    // Check if cached screenshot is still valid
    if (isCacheValid(element.selector, rect)) {
        console.log('[Screenshot Helpers] Using cached screenshot (element unchanged)');
        return screenshotCache.blob;
    }

    console.log('[Screenshot Helpers] Cache miss - capturing new screenshot');

    // Capture the visible tab
    console.log('[Screenshot Helpers] Capturing visible tab…');
    const dataUrl = await captureVisibleTab();
    console.log('[Screenshot Helpers] Tab captured, data URL length:', dataUrl.length);

    // Crop to element bounds with 2x quality and padding
    console.log('[Screenshot Helpers] Cropping image to bounds…');
    const blob = await cropImage(dataUrl, rect);
    console.log('[Screenshot Helpers] Blob created, size:', blob.size);

    // Update cache
    screenshotCache.selector = element.selector;
    screenshotCache.bounds = {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        devicePixelRatio: rect.devicePixelRatio,
        scrollX: rect.scrollX,
        scrollY: rect.scrollY
    };
    screenshotCache.blob = blob;
    screenshotCache.timestamp = Date.now();

    return blob;
}

/**
 * Get element bounds from the page
 * @param {Object} element - Element object
 * @returns {Promise<DOMRect>} Element bounds
 */
async function getElementBounds(element) {
    return new Promise((resolve, reject) => {
        // Use chrome.devtools.inspectedWindow.tabId for DevTools context
        const tabId = chrome.devtools.inspectedWindow.tabId;

        chrome.tabs.sendMessage(
            tabId,
            {
                action: 'getElementBounds',
                selector: element.selector
            },
            (response) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                    return;
                }

                if (response && response.success && response.bounds) {
                    resolve(response.bounds);
                } else {
                    reject(new Error(response?.error || 'Could not get element bounds'));
                }
            }
        );
    });
}

/**
 * Capture the visible tab as a data URL
 * @returns {Promise<string>} Data URL of screenshot
 */
async function captureVisibleTab() {
    return new Promise((resolve, reject) => {
        chrome.tabs.captureVisibleTab(
            null,
            { format: 'png' },
            (dataUrl) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                    return;
                }

                resolve(dataUrl);
            }
        );
    });
}

/**
 * Crop an image to specific bounds with 2x quality and smart padding
 * @param {string} dataUrl - Source image data URL
 * @param {DOMRect} rect - Bounds to crop to
 * @returns {Promise<Blob>} Cropped image as blob with 2x resolution and padding
 */
async function cropImage(dataUrl, rect) {
    return new Promise((resolve, reject) => {
        const img = new Image();

        img.onload = () => {
            const canvas = document.createElement('canvas');
            const ctx = canvas.getContext('2d');

            // Use device pixel ratio from the page context (passed in rect)
            // DevTools panel DPR might differ from page DPR
            const dpr = rect.devicePixelRatio || window.devicePixelRatio || 1;

            console.log('[Screenshot Helpers] Device pixel ratio (page):', rect.devicePixelRatio);
            console.log('[Screenshot Helpers] Device pixel ratio (panel):', window.devicePixelRatio);
            console.log('[Screenshot Helpers] Using DPR:', dpr);
            console.log('[Screenshot Helpers] Image size:', img.width, 'x', img.height);
            console.log('[Screenshot Helpers] Element rect:', rect);
            console.log('[Screenshot Helpers] Rect values - x:', rect.x, 'y:', rect.y, 'width:', rect.width, 'height:', rect.height);

            // Calculate source coordinates accounting for device pixel ratio
            const sourceX = rect.x * dpr;
            const sourceY = rect.y * dpr;
            const sourceWidth = rect.width * dpr;
            const sourceHeight = rect.height * dpr;

            console.log('[Screenshot Helpers] Source crop:', sourceX, sourceY, sourceWidth, sourceHeight);

            // ENHANCEMENT: 2x quality and 20px padding
            const scaleFactor = 2;  // Always output at 2x resolution
            const paddingPx = 20;
            const paddingScaled = paddingPx * scaleFactor;  // 40px at 2x

            // Set canvas size to 2x with padding
            canvas.width = (rect.width * scaleFactor) + (paddingScaled * 2);
            canvas.height = (rect.height * scaleFactor) + (paddingScaled * 2);

            console.log('[Screenshot Helpers] Output canvas size (2x + padding):', canvas.width, 'x', canvas.height);

            // Sample top-left pixel color for smart padding
            const tempCanvas = document.createElement('canvas');
            const tempCtx = tempCanvas.getContext('2d');
            tempCanvas.width = 1;
            tempCanvas.height = 1;

            // Draw just the top-left pixel from the element
            tempCtx.drawImage(img, sourceX, sourceY, 1, 1, 0, 0, 1, 1);
            const pixelData = tempCtx.getImageData(0, 0, 1, 1).data;

            // Handle transparent pixels - fallback to white
            let bgColor;
            if (pixelData[3] === 0) {
                bgColor = 'rgb(255, 255, 255)';  // White for transparent
                console.log('[Screenshot Helpers] Top-left pixel is transparent, using white padding');
            } else {
                bgColor = `rgb(${pixelData[0]}, ${pixelData[1]}, ${pixelData[2]})`;
                console.log('[Screenshot Helpers] Sampled padding color:', bgColor);
            }

            // Fill entire canvas with sampled color
            ctx.fillStyle = bgColor;
            ctx.fillRect(0, 0, canvas.width, canvas.height);

            // Draw the element screenshot at 2x resolution, centered with padding
            ctx.drawImage(
                img,
                sourceX, sourceY, sourceWidth, sourceHeight,  // Source (device pixels)
                paddingScaled, paddingScaled,                  // Destination offset (padding)
                rect.width * scaleFactor, rect.height * scaleFactor  // Destination size (2x)
            );

            // Convert to blob
            canvas.toBlob((blob) => {
                if (blob) {
                    console.log('[Screenshot Helpers] Cropped blob size:', blob.size);
                    resolve(blob);
                } else {
                    reject(new Error('Failed to create blob from canvas'));
                }
            }, 'image/png');
        };

        img.onerror = () => {
            reject(new Error('Failed to load image'));
        };

        img.src = dataUrl;
    });
}

/**
 * Show screenshot in a modal overlay
 * Users can right-click to copy or download the image
 * @param {string} dataUrl - Screenshot data URL
 * @param {string} selector - Element selector for context
 * @param {number} width - Image width in pixels
 * @param {number} height - Image height in pixels
 * @param {number} filesize - File size in bytes
 */
export function showScreenshotModal(dataUrl, selector, width, height, filesize) {
    console.log('[Screenshot] Showing screenshot modal');

    // Format filesize
    const filesizeKB = Math.round(filesize / 1024);

    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.className = 'screenshot-modal-overlay';
    overlay.innerHTML = `
        <div class="screenshot-modal">
            <div class="screenshot-modal-header">
                <h3>Element Screenshot (${width}×${height}, ${filesizeKB}KB)</h3>
                <button class="screenshot-modal-close" title="Close (Esc)">
                    <span class="material-icons">close</span>
                </button>
            </div>
            <div class="screenshot-modal-body">
                <div class="screenshot-selector">${escapeHtml(selector)}</div>
                <div class="screenshot-container">
                    <div class="screenshot-background" style="background-image: url('${dataUrl}');"></div>
                    <img src="${dataUrl}" alt="Element screenshot" class="screenshot-image">
                </div>
                <div class="screenshot-instructions">
                    <span class="material-icons">info</span>
                    <span>Right-click the image to copy or save it, or drag it to your desired location.</span>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    // Close handlers
    const closeModal = () => {
        overlay.classList.add('fade-out');
        setTimeout(() => {
            document.body.removeChild(overlay);
        }, 200);
    };

    const closeButton = overlay.querySelector('.screenshot-modal-close');
    closeButton.addEventListener('click', closeModal);

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            closeModal();
        }
    });

    document.addEventListener('keydown', function escHandler(e) {
        if (e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            e.stopImmediatePropagation();
            closeModal();
            document.removeEventListener('keydown', escHandler, true);
        }
    }, true);

    // Fade in animation
    requestAnimationFrame(() => {
        overlay.classList.add('show');
    });
}

/**
 * Escape HTML to prevent XSS
 * @param {string} str - String to escape
 * @returns {string} Escaped string
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Temporarily hide element outline for screenshot
 * @param {string} selector - Element selector
 * @returns {Promise<boolean>} True if outline was hidden
 */
export async function hideElementOutline(selector) {
    return new Promise((resolve, reject) => {
        const tabId = chrome.devtools.inspectedWindow.tabId;

        chrome.tabs.sendMessage(
            tabId,
            {
                action: 'hideOutline',
                selector: selector
            },
            (response) => {
                if (chrome.runtime.lastError) {
                    console.warn('[Screenshot] Could not hide outline:', chrome.runtime.lastError.message);
                    resolve(false);
                    return;
                }

                if (response && response.success) {
                    resolve(true);
                } else {
                    resolve(false);
                }
            }
        );
    });
}

/**
 * Restore element outline after screenshot
 * @param {string} selector - Element selector
 * @returns {Promise<void>}
 */
export async function showElementOutline(selector) {
    return new Promise((resolve, reject) => {
        const tabId = chrome.devtools.inspectedWindow.tabId;

        chrome.tabs.sendMessage(
            tabId,
            {
                action: 'showOutline',
                selector: selector
            },
            (response) => {
                if (chrome.runtime.lastError) {
                    console.warn('[Screenshot] Could not restore outline:', chrome.runtime.lastError.message);
                    resolve();
                    return;
                }
                resolve();
            }
        );
    });
}

/**
 * Scroll element into view if needed
 * @param {string} selector - Element selector
 * @returns {Promise<void>}
 */
export async function scrollElementIntoView(selector) {
    return new Promise((resolve, reject) => {
        // Use chrome.devtools.inspectedWindow.tabId for DevTools context
        const tabId = chrome.devtools.inspectedWindow.tabId;

        chrome.tabs.sendMessage(
            tabId,
            {
                action: 'scrollIntoView',
                selector: selector
            },
            (response) => {
                if (chrome.runtime.lastError) {
                    reject(new Error(chrome.runtime.lastError.message));
                    return;
                }

                if (response && response.success) {
                    resolve();
                } else {
                    reject(new Error(response?.error || 'Could not scroll element into view'));
                }
            }
        );
    });
}
