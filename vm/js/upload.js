// =============================================
// =============================================
// Upload Overlay
// =============================================

let _uploadActive = false;
let _stagedFiles = [];  // Array of { file: File, id: number, rejected?: string }
let _uploadIdCounter = 0;
const MAX_UPLOAD_FILES = 5;
const MAX_UPLOAD_SIZE = 1_048_576; // 1 MB
// Binary/disallowed file extensions
const BINARY_EXTENSIONS = new Set([
    'png','jpg','jpeg','gif','webp','bmp','ico','avif','svg',
    'pdf','zip','gz','tar','7z','rar','bz2',
    'exe','dll','so','dylib','bin','dmg','iso','img',
    'mp3','mp4','wav','ogg','flac','avi','mkv','mov','webm',
    'woff','woff2','ttf','otf','eot',
    'class','pyc','pyo','o','a','wasm',
    'db','sqlite','sqlite3',
]);

/** Check if a file is likely binary based on extension */
function _isBinaryExtension(name) {
    const ext = (name.split('.').pop() || '').toLowerCase();
    return BINARY_EXTENSIONS.has(ext);
}

/** Show the upload overlay on the terminal panel */
/** Trigger upload from the toolbar button (no CLI tool involved) */
function triggerUploadFromToolbar() {
    // Reset server state and show the overlay
    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/upload-reset`, { method: 'POST' }).catch(() => {});
    showUploadOverlay();
}

/** Show the upload overlay on the terminal panel */
function showUploadOverlay() {
    const overlay = document.getElementById('uploadOverlay');
    const dropzone = document.getElementById('uploadDropzone');
    const fileInput = document.getElementById('uploadFileInput');

    // Reset state
    _stagedFiles = [];
    _uploadIdCounter = 0;
    fileInput.value = '';
    dropzone.classList.remove('dragover');
    _uploadActive = true;
    _renderUploadUI();

    overlay.classList.add('active');

    // Make terminal/editor inert so keystrokes don't pass through
    document.getElementById('terminalContainer').inert = true;
    document.getElementById('editorContainer').inert = true;

    // Focus the browse button after fade-in completes so Enter opens file chooser
    setTimeout(() => {
        document.getElementById('uploadBrowseBtn').focus();
    }, 220);

    // Drag-and-drop handlers
    dropzone.ondragover = (e) => { e.preventDefault(); dropzone.classList.add('dragover'); };
    dropzone.ondragleave = (e) => {
        if (!dropzone.contains(e.relatedTarget)) dropzone.classList.remove('dragover');
    };
    dropzone.ondrop = (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        stageFiles(e.dataTransfer.files);
    };
}

/** Stage files for upload (don't upload yet) */
function stageFiles(fileList) {
    for (const file of fileList) {
        if (_stagedFiles.length >= MAX_UPLOAD_FILES) {
            showToast(`Maximum ${MAX_UPLOAD_FILES} files allowed`, 'error');
            break;
        }
        const entry = { file, id: ++_uploadIdCounter };
        // Check for rejection reasons
        if (file.size > MAX_UPLOAD_SIZE) {
            entry.rejected = 'Too large';
        } else if (_isBinaryExtension(file.name)) {
            entry.rejected = 'Not allowed';
        }
        _stagedFiles.push(entry);
    }
    _renderUploadUI();
}

/** Remove a staged file by id */
function unstageFile(id) {
    _stagedFiles = _stagedFiles.filter(f => f.id !== id);
    document.getElementById('uploadFileInput').value = '';
    _renderUploadUI();
}

/** Rename a staged file (called from inline input) */
function renameStaged(id, newName) {
    const entry = _stagedFiles.find(f => f.id === id);
    if (!entry || entry.rejected) return;
    newName = (newName || '').replace(/[/\\]/g, '').trim();
    entry.rename = newName || entry.file.name;
}

/** Select only the filename part (not extension) in an input */
function _selectFilenameStem(input) {
    const val = input.value;
    const dotIndex = val.lastIndexOf('.');
    if (dotIndex > 0) {
        input.setSelectionRange(0, dotIndex);
    } else {
        input.select();
    }
}

/** Render the upload overlay UI based on current staged files */
function _renderUploadUI() {
    const list = document.getElementById('uploadFileList');
    const progress = document.getElementById('uploadProgress');
    const uploadBtn = document.getElementById('uploadSubmitBtn');
    const dropHint = document.getElementById('uploadDropHint');
    const browseBtn = document.getElementById('uploadBrowseBtn');

    progress.style.display = 'none';

    const validFiles = _stagedFiles.filter(f => !f.rejected);

    if (_stagedFiles.length === 0) {
        list.innerHTML = '';
        list.style.display = 'none';
        dropHint.style.display = '';
        browseBtn.style.display = '';
        uploadBtn.style.display = 'none';
    } else {
        dropHint.style.display = 'none';
        list.style.display = '';
        browseBtn.style.display = _stagedFiles.length < MAX_UPLOAD_FILES ? '' : 'none';

        // Only show upload button if there are valid files
        uploadBtn.style.display = validFiles.length > 0 ? '' : 'none';

        list.innerHTML = _stagedFiles.map(f => {
            const fSize = f.file.size > 1024 ? `${(f.file.size / 1024).toFixed(1)} KB` : `${f.file.size} B`;
            const displayName = f.rename || f.file.name;

            if (f.rejected) {
                // Rejected file: non-editable name + red badge
                return `<div class="upload-file-entry rejected">
                    <span class="upload-file-name rejected">${_esc(displayName)}</span>
                    <span class="upload-file-badge rejected">${_esc(f.rejected)}</span>
                    <button class="upload-file-remove" onclick="unstageFile(${f.id})" title="Remove">×</button>
                </div>`;
            }

            return `<div class="upload-file-entry">
                <input class="upload-file-name" value="${_esc(displayName)}" data-upload-id="${f.id}" spellcheck="false"
                       onfocus="_selectFilenameStem(this)" onchange="renameStaged(${f.id}, this.value)" onblur="renameStaged(${f.id}, this.value)">
                <span class="upload-file-size">${fSize}</span>
                <button class="upload-file-remove" onclick="unstageFile(${f.id})" title="Remove">×</button>
            </div>`;
        }).join('');

        if (validFiles.length > 0) {
            const totalSize = validFiles.reduce((s, f) => s + f.file.size, 0);
            const sizeStr = totalSize > 1024 ? `${(totalSize / 1024).toFixed(1)} KB` : `${totalSize} B`;
            uploadBtn.textContent = `Upload ${validFiles.length} file${validFiles.length > 1 ? 's' : ''} (${sizeStr})`;
        }
    }
}

/** Actually upload all staged files */
async function submitUpload() {
    if (_stagedFiles.length === 0) return;

    const progress = document.getElementById('uploadProgress');
    const progressFill = document.getElementById('uploadProgressFill');
    const progressText = document.getElementById('uploadProgressText');
    const uploadBtn = document.getElementById('uploadSubmitBtn');

    progress.style.display = '';
    uploadBtn.disabled = true;
    uploadBtn.style.opacity = '0.5';
    progressFill.style.width = '0%';
    progressText.textContent = `Reading files…`;

    try {
        // Read valid (non-rejected) files as base64
        const validStaged = _stagedFiles.filter(f => !f.rejected);
        const filesData = [];
        for (let i = 0; i < validStaged.length; i++) {
            const staged = validStaged[i];
            const f = staged.file;
            const uploadName = staged.rename || f.name;
            progressText.textContent = `Reading ${uploadName}…`;
            const data = await f.arrayBuffer();
            const bytes = new Uint8Array(data);

            // Check for binary content (null bytes in first 512)
            const sample = bytes.slice(0, 512);
            if (sample.includes(0)) {
                showToast(`${uploadName}: binary files are not allowed`, 'error');
                continue;
            }

            // Convert to base64
            let binary = '';
            for (let j = 0; j < bytes.length; j++) binary += String.fromCharCode(bytes[j]);
            const b64 = btoa(binary);

            filesData.push({ name: uploadName, data: b64, size: f.size });
            progressFill.style.width = Math.round(((i + 1) / validStaged.length) * 50) + '%';
        }

        if (filesData.length === 0) {
            progressText.textContent = 'No valid files to upload';
            uploadBtn.disabled = false;
            uploadBtn.style.opacity = '';
            return;
        }

        progressText.textContent = `Uploading ${filesData.length} file(s)…`;
        progressFill.style.width = '50%';

        const resp = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/upload`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: filesData })
        });
        const result = await resp.json();

        if (result.ok) {
            progressFill.style.width = '100%';
            const count = (result.uploaded || []).length;
            progressText.textContent = `Uploaded ${count} file(s) ✓`;

            await new Promise(r => setTimeout(r, 800));
            _closeUploadOverlay();

            if (result.errors && result.errors.length > 0) {
                showToast(result.errors.join('; '), 'error', 5000);
            }
        } else {
            progressText.textContent = result.error || 'Upload failed';
            progressFill.style.width = '0%';
            uploadBtn.disabled = false;
            uploadBtn.style.opacity = '';
        }
    } catch (err) {
        progressText.textContent = `Error: ${_esc(err.message)}`;
        uploadBtn.disabled = false;
        uploadBtn.style.opacity = '';
    }
}

/** Cancel the upload and close the overlay */
/** Close the upload overlay and return focus to terminal */
function _closeUploadOverlay() {
    _uploadActive = false;
    _stagedFiles = [];
    document.getElementById('uploadOverlay').classList.remove('active');
    // Restore terminal/editor interaction and return focus after fade-out
    document.getElementById('terminalContainer').inert = false;
    document.getElementById('editorContainer').inert = false;
    setTimeout(() => { if (terminal) terminal.focus(); }, 220);
}

function cancelUpload() {
    _closeUploadOverlay();
    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/file/upload-reset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'cancelled' })
    }).catch(() => {});
}

// Escape key closes upload overlay (capture phase, before other handlers)
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape' && _uploadActive) {
        e.preventDefault();
        e.stopImmediatePropagation();
        cancelUpload();
    }
}, true);

