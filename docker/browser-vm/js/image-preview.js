// =============================================
// Image Preview
// =============================================

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico', 'avif']);
let _previewImagePath = null;

/** Check if a file path is an image based on extension */
function isImageFile(filePath) {
    const ext = (filePath.split('.').pop() || '').toLowerCase();
    return IMAGE_EXTENSIONS.has(ext);
}

/** Open an image in the preview modal */
function previewImage(filePath) {
    _previewImagePath = filePath;
    const overlay = document.getElementById('imagePreviewOverlay');
    const img = document.getElementById('imagePreviewImg');
    const filename = document.getElementById('imagePreviewFilename');
    const meta = document.getElementById('imagePreviewMeta');

    filename.textContent = filePath.split('/').pop();

    // Load image via the /download endpoint (serves with correct Content-Type)
    const url = `http://${VNC_HOST}:${CONTROL_PORT}/download?path=${encodeURIComponent(filePath)}`;
    img.onload = function() {
        meta.textContent = `${this.naturalWidth} × ${this.naturalHeight}`;
    };
    img.onerror = function() {
        meta.textContent = 'Failed to load';
    };
    img.src = url;

    overlay.classList.add('open');
}

/** Close the image preview modal */
function closeImagePreview() {
    const overlay = document.getElementById('imagePreviewOverlay');
    overlay.classList.remove('open');
    // Clear src to stop loading
    document.getElementById('imagePreviewImg').src = '';
    _previewImagePath = null;
}

/** Download the currently previewed image */
function downloadPreviewImage() {
    if (_previewImagePath) triggerFileDownload(_previewImagePath);
}

// Escape key closes image preview
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && document.getElementById('imagePreviewOverlay').classList.contains('open')) {
        e.preventDefault();
        e.stopImmediatePropagation();
        closeImagePreview();
    }
}, true); // capture phase — before other Escape handlers



