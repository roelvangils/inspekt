        (function() {
            // Theme toggle
            const html = document.documentElement;
            const themeToggle = document.querySelector('.theme-toggle');

            function getPreferredTheme() {
                const stored = localStorage.getItem('inspekt-gallery-theme');
                if (stored) return stored;
                return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
            }

            function setTheme(theme) {
                html.setAttribute('data-theme', theme);
                localStorage.setItem('inspekt-gallery-theme', theme);
            }

            // Initialize theme
            setTheme(getPreferredTheme());

            themeToggle.addEventListener('click', function() {
                const current = html.getAttribute('data-theme');
                setTheme(current === 'dark' ? 'light' : 'dark');
            });

            // Filter functionality
            const filterType = document.getElementById('filter-type');
            const filterMinWidth = document.getElementById('filter-min-width');
            const filterMinHeight = document.getElementById('filter-min-height');
            const filterBgColor = document.getElementById('filter-bg-color');
            const filterMergeDuplicates = document.getElementById('filter-merge-duplicates');
            const filterIncludeBackground = document.getElementById('filter-include-background');
            const visibleCount = document.getElementById('visible-count');
            const cards = document.querySelectorAll('.gallery-card');
            const thumbnails = document.querySelectorAll('.gallery-thumbnail');

            // Background color for transparent images
            function applyBgColor(color) {
                thumbnails.forEach(function(thumb) {
                    thumb.style.backgroundColor = color;
                });
                localStorage.setItem('inspekt-gallery-bg-color', color);
            }

            // Initialize background color from storage or default
            const storedBgColor = localStorage.getItem('inspekt-gallery-bg-color');
            if (storedBgColor) {
                filterBgColor.value = storedBgColor;
                applyBgColor(storedBgColor);
            } else {
                applyBgColor(filterBgColor.value);
            }

            filterBgColor.addEventListener('input', function() {
                applyBgColor(this.value);
            });

            function applyFilters() {
                const typeFilter = filterType.value.toLowerCase();
                const minWidth = parseInt(filterMinWidth.value) || 0;
                const minHeight = parseInt(filterMinHeight.value) || 0;
                const mergeDuplicates = filterMergeDuplicates.checked;
                const includeBackground = filterIncludeBackground ? filterIncludeBackground.checked : true;

                // First pass: apply basic filters (type, dimensions, background)
                const basicFiltered = [];
                cards.forEach(function(card) {
                    const ext = card.dataset.ext || '';
                    const width = parseInt(card.dataset.width) || 0;
                    const height = parseInt(card.dataset.height) || 0;
                    const isBackground = card.dataset.background === 'true';

                    const matchesType = !typeFilter || ext === typeFilter;
                    const matchesWidth = width >= minWidth;
                    const matchesHeight = height >= minHeight;
                    const matchesBackground = includeBackground || !isBackground;

                    if (matchesType && matchesWidth && matchesHeight && matchesBackground) {
                        basicFiltered.push(card);
                        card.classList.remove('hidden');
                    } else {
                        card.classList.add('hidden');
                    }
                });

                // Second pass: merge duplicates if enabled
                let visible = basicFiltered.length;
                if (mergeDuplicates && basicFiltered.length > 0) {
                    // Group by lowercase filename (from .filename element's title attribute)
                    const groups = {};
                    basicFiltered.forEach(function(card) {
                        const filenameEl = card.querySelector('.filename');
                        const filename = (filenameEl ? filenameEl.title : '').toLowerCase();
                        if (!groups[filename]) {
                            groups[filename] = [];
                        }
                        groups[filename].push(card);
                    });

                    // For each group with duplicates, keep only the largest file
                    visible = 0;
                    Object.values(groups).forEach(function(group) {
                        if (group.length === 1) {
                            // Single image, already visible
                            visible++;
                            return;
                        }
                        // Sort by file size descending (largest first)
                        group.sort(function(a, b) {
                            const thumbA = a.querySelector('.gallery-thumbnail');
                            const thumbB = b.querySelector('.gallery-thumbnail');
                            const sizeA = parseInt(thumbA ? thumbA.dataset.sizeBytes : 0) || 0;
                            const sizeB = parseInt(thumbB ? thumbB.dataset.sizeBytes : 0) || 0;
                            return sizeB - sizeA;
                        });
                        // Keep first (largest), hide the rest
                        visible++;
                        for (let i = 1; i < group.length; i++) {
                            group[i].classList.add('hidden');
                        }
                    });
                }

                visibleCount.textContent = visible;
            }

            filterType.addEventListener('change', applyFilters);
            filterMinWidth.addEventListener('input', applyFilters);
            filterMinHeight.addEventListener('input', applyFilters);
            filterMergeDuplicates.addEventListener('change', applyFilters);
            if (filterIncludeBackground) {
                filterIncludeBackground.addEventListener('change', applyFilters);
            }

            // Apply filters on page load (checkboxes are checked by default)
            applyFilters();

            // Lightbox functionality
            const lightbox = document.querySelector('.lightbox');
            const backdropA = document.getElementById('backdrop-a');
            const backdropB = document.getElementById('backdrop-b');
            const lightboxImage = document.querySelector('.lightbox-image');

            const lightboxCounter = document.querySelector('.lightbox-counter');
            const lightboxFilename = document.querySelector('.lightbox-filename');
            const lightboxMeta = document.querySelector('.lightbox-meta');
            const lightboxAlt = document.querySelector('.lightbox-alt');
            const lightboxAccName = document.querySelector('.lightbox-acc-name');
            const ocrToggleBtn = document.getElementById('ocr-toggle-btn');
            const ocrTextPanel = document.getElementById('ocr-text-panel');
            const ocrTextContent = document.querySelector('.ocr-text-content');
            const closeBtn = document.querySelector('.lightbox-close');
            const prevBtn = document.querySelector('.lightbox-prev');
            const nextBtn = document.querySelector('.lightbox-next');
            // thumbnails already declared above in filter section

            let currentIndex = 0;
            let lastFocusedElement = null;
            let activeBackdrop = 'a';  // Track which backdrop is currently visible
            let backdropDebounceTimer = null;  // Debounce timer for backdrop crossfade
            const BACKDROP_DEBOUNCE_MS = 150;  // Wait 150ms before updating backdrop

            // Get array of visible (non-filtered) thumbnail indices
            function getVisibleIndices() {
                const indices = [];
                thumbnails.forEach(function(thumb, index) {
                    const card = thumb.closest('.gallery-card');
                    if (card && !card.classList.contains('hidden')) {
                        indices.push(index);
                    }
                });
                return indices;
            }

            function updateBackdrop(imageSrc, isInitial) {
                if (isInitial) {
                    // Initial open: just set both to same image, show A
                    backdropA.src = imageSrc;
                    backdropB.src = imageSrc;
                    backdropA.classList.add('active');
                    backdropB.classList.remove('active');
                    activeBackdrop = 'a';
                } else {
                    // Navigation: crossfade between backdrops
                    if (activeBackdrop === 'a') {
                        backdropB.src = imageSrc;
                        backdropB.classList.add('active');
                        backdropA.classList.remove('active');
                        activeBackdrop = 'b';
                    } else {
                        backdropA.src = imageSrc;
                        backdropA.classList.add('active');
                        backdropB.classList.remove('active');
                        activeBackdrop = 'a';
                    }
                }
            }

            function updateLightbox(index, isInitial) {
                currentIndex = index;
                const thumb = thumbnails[index];
                const card = thumb.closest('.gallery-card');
                const isSvg = card && card.dataset.ext === 'svg';

                const imageSrc = thumb.dataset.fullSrc;
                lightboxImage.src = imageSrc;

                // Toggle SVG mode (solid background instead of blur)
                if (isSvg) {
                    lightbox.classList.add('svg-mode');
                    // Background color is applied by applySvgOptions() after this function
                } else {
                    lightbox.classList.remove('svg-mode');
                }

                // Debounce backdrop crossfade to prevent stacking during rapid navigation
                if (backdropDebounceTimer) {
                    clearTimeout(backdropDebounceTimer);
                }

                // Only update backdrop for non-SVG images
                if (!isSvg) {
                    if (isInitial) {
                        // Initial open: update backdrop immediately
                        updateBackdrop(imageSrc, true);
                    } else {
                        // Navigation: debounce the backdrop update
                        backdropDebounceTimer = setTimeout(function() {
                            updateBackdrop(imageSrc, false);
                        }, BACKDROP_DEBOUNCE_MS);
                    }
                }

                lightboxImage.alt = thumb.dataset.alt || 'Image ' + (index + 1);

                // Update counter based on visible (filtered) images
                const visibleIndices = getVisibleIndices();
                const positionInVisible = visibleIndices.indexOf(index) + 1;
                lightboxCounter.textContent = positionInVisible + ' / ' + visibleIndices.length;

                // Extract filename from src
                const filename = thumb.dataset.fullSrc.split('/').pop();
                lightboxFilename.textContent = filename;
                lightboxMeta.textContent = thumb.dataset.width + '×' + thumb.dataset.height + ' · ' + thumb.dataset.size;
                lightboxAlt.textContent = thumb.dataset.alt ? '"' + thumb.dataset.alt + '"' : '';

                // Handle accessible name display in lightbox
                if (lightboxAccName) {
                    var accNameB64 = thumb.dataset.accName;
                    var accNameSource = thumb.dataset.accNameSource || '';
                    if (accNameB64) {
                        try {
                            var accNameText = atob(accNameB64);
                            lightboxAccName.innerHTML = '<span class="acc-label">Accessible name:</span> ' + accNameText + ' <span class="acc-label">(from ' + accNameSource + ')</span>';
                        } catch (e) {
                            lightboxAccName.textContent = '';
                        }
                    } else if (accNameSource === 'missing alt attribute' || accNameSource === 'none') {
                        lightboxAccName.innerHTML = '<span class="acc-label" style="color:#f0883e">⚠ No accessible name (' + accNameSource + ')</span>';
                    } else if (accNameSource === 'empty alt (decorative)') {
                        lightboxAccName.innerHTML = '<span class="acc-label">Decorative image (empty alt)</span>';
                    } else if (accNameSource === 'not applicable') {
                        lightboxAccName.innerHTML = '<span class="acc-label">CSS background — accessible name not applicable</span>';
                    } else {
                        lightboxAccName.textContent = '';
                    }
                }

                // Handle OCR text panel
                const ocrB64 = thumb.dataset.ocrText;
                if (ocrB64 && ocrTextContent) {
                    try {
                        const ocrText = atob(ocrB64);
                        ocrTextContent.textContent = ocrText;
                        lightbox.classList.add('has-ocr');
                        // Reset toggle state when navigating to new image
                        if (ocrToggleBtn) {
                            ocrToggleBtn.setAttribute('aria-pressed', 'false');
                        }
                        if (ocrTextPanel) {
                            ocrTextPanel.hidden = true;
                        }
                    } catch (e) {
                        lightbox.classList.remove('has-ocr');
                    }
                } else {
                    lightbox.classList.remove('has-ocr');
                }

                // Update navigation state based on visible images
                const posIndex = visibleIndices.indexOf(index);
                prevBtn.disabled = posIndex <= 0;
                nextBtn.disabled = posIndex >= visibleIndices.length - 1;
            }

            function openLightbox(index) {
                lastFocusedElement = document.activeElement;
                lightbox.classList.add('active');
                document.body.style.overflow = 'hidden';
                updateLightbox(index, true);  // true = initial open
                closeBtn.focus();
            }

            function closeLightbox() {
                lightbox.classList.remove('active');
                lightbox.classList.remove('svg-mode');
                document.body.style.overflow = '';
                // Clear any pending backdrop update
                if (backdropDebounceTimer) {
                    clearTimeout(backdropDebounceTimer);
                    backdropDebounceTimer = null;
                }
                // Reset backdrop state
                backdropA.classList.remove('active');
                backdropB.classList.remove('active');
                if (lastFocusedElement) {
                    lastFocusedElement.focus();
                }
            }

            function showPrev() {
                const visibleIndices = getVisibleIndices();
                const currentPos = visibleIndices.indexOf(currentIndex);
                if (currentPos > 0) {
                    updateLightbox(visibleIndices[currentPos - 1], false);  // false = navigation
                }
            }

            function showNext() {
                const visibleIndices = getVisibleIndices();
                const currentPos = visibleIndices.indexOf(currentIndex);
                if (currentPos < visibleIndices.length - 1) {
                    updateLightbox(visibleIndices[currentPos + 1], false);  // false = navigation
                }
            }

            // Event listeners
            thumbnails.forEach(function(thumb, index) {
                thumb.addEventListener('click', function() {
                    openLightbox(index);
                });
            });

            closeBtn.addEventListener('click', closeLightbox);
            prevBtn.addEventListener('click', showPrev);
            nextBtn.addEventListener('click', showNext);

            // Keyboard navigation
            document.addEventListener('keydown', function(e) {
                if (!lightbox.classList.contains('active')) return;

                // Check if user is typing in the code editor - don't intercept those keys
                const isInCodeEditor = document.activeElement &&
                    (document.activeElement.classList.contains('lightbox-code-editor') ||
                     document.activeElement.tagName === 'TEXTAREA' ||
                     document.activeElement.tagName === 'INPUT');

                if (e.key === 'Escape') {
                    // Escape always works - close lightbox (or just code window if open)
                    if (!codeContainer.hidden) {
                        showImagePreview();
                        // Reset toggle button state
                        const imageToggle = document.querySelector('[data-option="preview"][data-value="image"]');
                        const codeToggle = document.querySelector('[data-option="preview"][data-value="code"]');
                        if (imageToggle) imageToggle.setAttribute('aria-pressed', 'true');
                        if (codeToggle) codeToggle.setAttribute('aria-pressed', 'false');
                        svgState.preview = 'image';
                        saveSvgOptions();
                    } else {
                        closeLightbox();
                    }
                } else if (e.key === 'ArrowLeft' && !isInCodeEditor) {
                    showPrev();
                } else if (e.key === 'ArrowRight' && !isInCodeEditor) {
                    showNext();
                }
            });

            // Close on backdrop click (but not if we just finished dragging)
            lightbox.addEventListener('click', function(e) {
                if (wasDragging) return;  // Don't close if we just finished dragging
                if (e.target === lightbox || e.target.classList.contains('lightbox-content')) {
                    closeLightbox();
                }
            });

            // SVG Preview Options
            const svgToggles = document.querySelectorAll('.svg-toggle');
            const SVG_STORAGE_KEY = 'inspekt-svg-options';

            // Load saved options from localStorage or use defaults
            function loadSvgOptions() {
                try {
                    const saved = localStorage.getItem(SVG_STORAGE_KEY);
                    if (saved) {
                        return JSON.parse(saved);
                    }
                } catch (e) {
                    console.warn('Could not load SVG options from localStorage');
                }
                return { size: 'auto', color: 'original', bg: 'current', preview: 'image' };
            }

            // Save options to localStorage
            function saveSvgOptions() {
                try {
                    localStorage.setItem(SVG_STORAGE_KEY, JSON.stringify(svgState));
                } catch (e) {
                    console.warn('Could not save SVG options to localStorage');
                }
            }

            const svgState = loadSvgOptions();

            // Code preview elements (macOS window)
            const codeContainer = document.querySelector('.lightbox-code-container');
            const macosWindow = codeContainer;
            const titlebar = codeContainer.querySelector('.macos-titlebar');
            const macosCloseBtn = codeContainer.querySelector('.macos-close');
            const minimizeBtn = codeContainer.querySelector('.macos-minimize');
            const maximizeBtn = codeContainer.querySelector('.macos-maximize');
            const filenameSpan = codeContainer.querySelector('.macos-filename');
            const codeEditor = codeContainer.querySelector('.lightbox-code-editor');
            const copyBtn = codeContainer.querySelector('.code-copy-btn');
            const imageContainer = document.querySelector('.lightbox-image-container');
            let svgCodeCache = {};  // Cache fetched SVG code

            // Draggable window state
            let isDragging = false;
            let wasDragging = false;  // Track if we just finished dragging (to prevent backdrop close)
            let dragOffset = { x: 0, y: 0 };
            let savedPosition = null;
            const CODE_WINDOW_POSITION_KEY = 'inspekt-code-window-position';

            // Load saved window position from localStorage
            function loadWindowPosition() {
                try {
                    const saved = localStorage.getItem(CODE_WINDOW_POSITION_KEY);
                    if (saved) {
                        return JSON.parse(saved);
                    }
                } catch (e) {
                    console.warn('Could not load window position from localStorage');
                }
                return null;
            }

            // Save window position to localStorage
            function saveWindowPosition(left, top) {
                try {
                    localStorage.setItem(CODE_WINDOW_POSITION_KEY, JSON.stringify({ left, top }));
                } catch (e) {
                    console.warn('Could not save window position to localStorage');
                }
            }

            // Position window in bottom-left corner (default position)
            function positionWindowBottomLeft() {
                const contentRect = document.querySelector('.lightbox-content').getBoundingClientRect();
                const windowRect = codeContainer.getBoundingClientRect();
                const left = 20;
                const top = contentRect.height - windowRect.height - 20;
                codeContainer.style.left = left + 'px';
                codeContainer.style.top = top + 'px';
                codeContainer.classList.add('dragged');
                return { left: left + 'px', top: top + 'px' };
            }

            // Get the containing block for accurate positioning
            function getContainingBlock() {
                return document.querySelector('.lightbox-content');
            }

            // Make window draggable via title bar
            titlebar.addEventListener('mousedown', (e) => {
                // Don't drag if clicking buttons
                if (e.target.closest('.macos-btn') || e.target.closest('.code-copy-btn')) return;

                e.preventDefault();
                e.stopPropagation();
                isDragging = true;

                // Get positions relative to containing block (not viewport)
                const rect = codeContainer.getBoundingClientRect();
                const containerRect = getContainingBlock().getBoundingClientRect();

                // If not yet in dragged mode, switch to absolute positioning first
                if (!codeContainer.classList.contains('dragged')) {
                    // Convert viewport coords to containing-block-relative coords
                    codeContainer.style.left = (rect.left - containerRect.left) + 'px';
                    codeContainer.style.top = (rect.top - containerRect.top) + 'px';
                    codeContainer.classList.add('dragged');
                }

                // Calculate offset from mouse to element's top-left (in viewport coords)
                dragOffset.x = e.clientX - rect.left;
                dragOffset.y = e.clientY - rect.top;
            });

            document.addEventListener('mousemove', (e) => {
                if (!isDragging) return;
                e.preventDefault();

                // Convert viewport mouse position to containing-block-relative position
                const containerRect = getContainingBlock().getBoundingClientRect();
                const x = e.clientX - dragOffset.x - containerRect.left;
                const y = e.clientY - dragOffset.y - containerRect.top;
                codeContainer.style.left = x + 'px';
                codeContainer.style.top = y + 'px';
            });

            document.addEventListener('mouseup', (e) => {
                if (isDragging) {
                    // Save position when drag ends
                    saveWindowPosition(codeContainer.style.left, codeContainer.style.top);
                    wasDragging = true;
                    // Reset wasDragging after a short delay to prevent backdrop close
                    setTimeout(() => { wasDragging = false; }, 100);
                }
                if (isResizing) {
                    // Save size when resize ends
                    saveWindowSize(codeContainer.style.width, codeContainer.style.height);
                    wasDragging = true;  // Reuse flag to prevent backdrop close
                    setTimeout(() => { wasDragging = false; }, 100);
                }
                isDragging = false;
                isResizing = false;
                resizeDirection = null;
            });

            // Prevent clicks inside the code container from closing the lightbox
            codeContainer.addEventListener('click', (e) => {
                e.stopPropagation();
            });

            // ═══════════════════════════════════════════════════════════════
            // Resize functionality
            // ═══════════════════════════════════════════════════════════════
            let isResizing = false;
            let resizeDirection = null;  // 'right', 'bottom', or 'corner'
            let resizeStartPos = { x: 0, y: 0 };
            let resizeStartSize = { width: 0, height: 0 };
            const CODE_WINDOW_SIZE_KEY = 'inspekt-code-window-size';
            const MIN_WIDTH = 300;
            const MIN_HEIGHT = 200;

            // Get resize handles
            const resizeRight = codeContainer.querySelector('.macos-resize-right');
            const resizeBottom = codeContainer.querySelector('.macos-resize-bottom');
            const resizeCorner = codeContainer.querySelector('.macos-resize-corner');

            // Load saved window size from localStorage
            function loadWindowSize() {
                try {
                    const saved = localStorage.getItem(CODE_WINDOW_SIZE_KEY);
                    if (saved) {
                        return JSON.parse(saved);
                    }
                } catch (e) {
                    console.warn('Could not load window size from localStorage');
                }
                return null;
            }

            // Save window size to localStorage
            function saveWindowSize(width, height) {
                try {
                    localStorage.setItem(CODE_WINDOW_SIZE_KEY, JSON.stringify({ width, height }));
                } catch (e) {
                    console.warn('Could not save window size to localStorage');
                }
            }

            // Start resize
            function startResize(e, direction) {
                e.preventDefault();
                e.stopPropagation();
                isResizing = true;
                resizeDirection = direction;
                resizeStartPos = { x: e.clientX, y: e.clientY };
                const rect = codeContainer.getBoundingClientRect();
                resizeStartSize = { width: rect.width, height: rect.height };

                // Ensure we have explicit width/height set
                if (!codeContainer.style.width) {
                    codeContainer.style.width = rect.width + 'px';
                }
                if (!codeContainer.style.height) {
                    codeContainer.style.height = rect.height + 'px';
                }
            }

            // Handle resize mousedown events
            if (resizeRight) {
                resizeRight.addEventListener('mousedown', (e) => startResize(e, 'right'));
            }
            if (resizeBottom) {
                resizeBottom.addEventListener('mousedown', (e) => startResize(e, 'bottom'));
            }
            if (resizeCorner) {
                resizeCorner.addEventListener('mousedown', (e) => startResize(e, 'corner'));
            }

            // Handle resize during mousemove
            document.addEventListener('mousemove', (e) => {
                if (!isResizing) return;
                e.preventDefault();

                const deltaX = e.clientX - resizeStartPos.x;
                const deltaY = e.clientY - resizeStartPos.y;

                if (resizeDirection === 'right' || resizeDirection === 'corner') {
                    const newWidth = Math.max(MIN_WIDTH, resizeStartSize.width + deltaX);
                    codeContainer.style.width = newWidth + 'px';
                }

                if (resizeDirection === 'bottom' || resizeDirection === 'corner') {
                    const newHeight = Math.max(MIN_HEIGHT, resizeStartSize.height + deltaY);
                    codeContainer.style.height = newHeight + 'px';
                }
            });

            // Close button - close editor window
            macosCloseBtn.addEventListener('click', () => {
                showImagePreview();
                // Reset toggle button state
                const imageToggle = document.querySelector('[data-option="preview"][data-value="image"]');
                const codeToggle = document.querySelector('[data-option="preview"][data-value="code"]');
                if (imageToggle) imageToggle.setAttribute('aria-pressed', 'true');
                if (codeToggle) codeToggle.setAttribute('aria-pressed', 'false');
            });

            // Minimize button - roll up/down
            minimizeBtn.addEventListener('click', () => {
                macosWindow.classList.toggle('minimized');
            });

            // Maximize button - toggle full size
            maximizeBtn.addEventListener('click', () => {
                if (macosWindow.classList.contains('maximized')) {
                    macosWindow.classList.remove('maximized');
                    if (savedPosition) {
                        codeContainer.style.left = savedPosition.left;
                        codeContainer.style.top = savedPosition.top;
                        if (savedPosition.left || savedPosition.top) {
                            codeContainer.classList.add('dragged');
                        }
                    }
                } else {
                    savedPosition = {
                        left: codeContainer.style.left,
                        top: codeContainer.style.top
                    };
                    macosWindow.classList.add('maximized');
                    codeContainer.classList.remove('dragged');
                    codeContainer.style.left = '';
                    codeContainer.style.top = '';
                }
            });

            // Live SVG preview update (debounced)
            let updateTimeout = null;

            codeEditor.addEventListener('input', () => {
                clearTimeout(updateTimeout);
                updateTimeout = setTimeout(updateSvgPreview, 150);
            });

            function updateSvgPreview() {
                const svgCode = codeEditor.value;

                try {
                    // Validate SVG by parsing
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(svgCode, 'image/svg+xml');
                    const parseError = doc.querySelector('parsererror');

                    if (parseError) {
                        codeEditor.classList.add('has-error');
                        return;
                    }

                    codeEditor.classList.remove('has-error');

                    // Create blob URL from SVG code
                    const blob = new Blob([svgCode], { type: 'image/svg+xml' });
                    const url = URL.createObjectURL(blob);

                    // Update the lightbox image
                    lightboxImage.src = url;

                } catch (e) {
                    console.warn('Invalid SVG:', e);
                    codeEditor.classList.add('has-error');
                }
            }

            // Get SVG source code - prefer embedded content, fall back to fetch
            async function getSvgCode() {
                // Get current thumbnail's embedded SVG content
                const thumb = thumbnails[currentIndex];
                const embeddedB64 = thumb?.dataset?.svgSource;

                if (embeddedB64) {
                    // Decode base64-encoded SVG content
                    try {
                        return atob(embeddedB64);
                    } catch (e) {
                        console.warn('Failed to decode embedded SVG:', e);
                    }
                }

                // Fall back to fetch (only works on http://)
                const src = lightboxImage.src;
                if (svgCodeCache[src]) {
                    return svgCodeCache[src];
                }

                if (window.location.protocol === 'file:') {
                    // Friendly message for large SVGs or missing content
                    return 'This SVG file is too large to embed in the gallery.\\n\\nTo view the source code, right-click the image and select "Open image in new tab", then view the page source.';
                }

                try {
                    const response = await fetch(src);
                    if (!response.ok) throw new Error('Failed to fetch SVG');
                    const code = await response.text();
                    svgCodeCache[src] = code;
                    return code;
                } catch (error) {
                    console.warn('Could not fetch SVG code:', error);
                    return '<!-- Could not load SVG source: ' + error.message + ' -->';
                }
            }

            // Show code preview (macOS editor window)
            async function showCodePreview() {
                const code = await getSvgCode();

                // Set code in textarea
                codeEditor.value = code;
                codeEditor.classList.remove('has-error');

                // Update filename in title bar
                const thumb = thumbnails[currentIndex];
                const filename = thumb?.closest('.gallery-card')?.querySelector('.filename')?.textContent || 'SVG';
                filenameSpan.textContent = filename;

                // Reset window state (keep position, just reset minimize/maximize)
                macosWindow.classList.remove('minimized', 'maximized');

                // Show window first (needed to calculate dimensions)
                codeContainer.hidden = false;
                lightbox.classList.add('svg-code-mode');

                // Apply saved position or default to bottom-left
                const savedPos = loadWindowPosition();
                if (savedPos && savedPos.left && savedPos.top) {
                    // Use saved position
                    codeContainer.style.left = savedPos.left;
                    codeContainer.style.top = savedPos.top;
                    codeContainer.classList.add('dragged');
                } else {
                    // Default: position in bottom-left corner (20px offset)
                    positionWindowBottomLeft();
                }

                // Apply saved size if available
                const savedSize = loadWindowSize();
                if (savedSize && savedSize.width && savedSize.height) {
                    codeContainer.style.width = savedSize.width;
                    codeContainer.style.height = savedSize.height;
                } else {
                    // Reset to default size (CSS will handle it)
                    codeContainer.style.width = '';
                    codeContainer.style.height = '';
                }
            }

            // Show image preview (hide code editor)
            function showImagePreview() {
                codeContainer.hidden = true;
                lightbox.classList.remove('svg-code-mode');
            }

            // Copy button functionality
            copyBtn.addEventListener('click', async function() {
                const code = codeEditor.value;
                try {
                    await navigator.clipboard.writeText(code);
                    this.classList.add('copied');
                    const originalHTML = this.innerHTML;
                    this.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 1 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0Z"/></svg> Copied!';
                    setTimeout(() => {
                        this.classList.remove('copied');
                        this.innerHTML = originalHTML;
                    }, 2000);
                } catch (err) {
                    console.error('Failed to copy:', err);
                }
            });

            // Helper: check if a hex color is "light" (luminance > 0.5)
            function isLightColor(hex) {
                // Handle shorthand and standard hex
                const cleanHex = hex.replace('#', '');
                let r, g, b;
                if (cleanHex.length === 3) {
                    r = parseInt(cleanHex[0] + cleanHex[0], 16);
                    g = parseInt(cleanHex[1] + cleanHex[1], 16);
                    b = parseInt(cleanHex[2] + cleanHex[2], 16);
                } else {
                    r = parseInt(cleanHex.substring(0, 2), 16);
                    g = parseInt(cleanHex.substring(2, 4), 16);
                    b = parseInt(cleanHex.substring(4, 6), 16);
                }
                // Relative luminance formula
                const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
                return luminance > 0.5;
            }

            function applySvgOptions() {
                // Remove all SVG-related classes
                lightboxImage.classList.remove(
                    'svg-size-auto', 'svg-size-50', 'svg-size-25', 'svg-size-original',
                    'svg-color-white', 'svg-color-black'
                );

                // Apply size class
                lightboxImage.classList.add('svg-size-' + svgState.size);

                // Apply color filter
                if (svgState.color === 'white') {
                    lightboxImage.classList.add('svg-color-white');
                } else if (svgState.color === 'black') {
                    lightboxImage.classList.add('svg-color-black');
                }

                // Determine the effective background color
                let effectiveBgColor;
                if (svgState.bg === 'white') {
                    effectiveBgColor = '#ffffff';
                } else if (svgState.bg === 'black') {
                    effectiveBgColor = '#000000';
                } else {
                    effectiveBgColor = filterBgColor.value || '#e5e5e5';
                }

                // Auto-contrast: prevent invisible images (bi-directional)
                const bgIsLight = isLightColor(effectiveBgColor);

                // If SVG color would be invisible on current background, adjust
                if (svgState.color === 'white' && bgIsLight) {
                    // White SVG on light background → switch background to black
                    effectiveBgColor = '#000000';
                    svgState.bg = 'black';
                } else if (svgState.color === 'black' && !bgIsLight) {
                    // Black SVG on dark background → switch background to white
                    effectiveBgColor = '#ffffff';
                    svgState.bg = 'white';
                } else if (svgState.color === 'original') {
                    // For original color, check if background change would hide a white/black SVG
                    // (Can't detect original SVG color, so skip auto-adjustment)
                } else {
                    // Background was changed - check if SVG color needs adjustment
                    if (bgIsLight && svgState.color === 'white') {
                        // Light bg + white SVG → switch SVG to black
                        svgState.color = 'black';
                        lightboxImage.classList.remove('svg-color-white');
                        lightboxImage.classList.add('svg-color-black');
                    } else if (!bgIsLight && svgState.color === 'black') {
                        // Dark bg + black SVG → switch SVG to white
                        svgState.color = 'white';
                        lightboxImage.classList.remove('svg-color-black');
                        lightboxImage.classList.add('svg-color-white');
                    }
                }

                // Apply the background color
                lightbox.style.setProperty('--lightbox-solid-bg', effectiveBgColor);

                // Update aria-pressed states to match current state
                svgToggles.forEach(function(toggle) {
                    const option = toggle.dataset.option;
                    const value = toggle.dataset.value;
                    const isActive = svgState[option] === value;
                    toggle.setAttribute('aria-pressed', isActive ? 'true' : 'false');
                });

                // Handle preview mode (image vs code)
                if (svgState.preview === 'code') {
                    showCodePreview();
                } else {
                    showImagePreview();
                }
            }

            // Handle SVG toggle button clicks
            svgToggles.forEach(function(toggle) {
                toggle.addEventListener('click', function() {
                    const option = this.dataset.option;
                    const value = this.dataset.value;

                    // Update state
                    svgState[option] = value;

                    // Save to localStorage
                    saveSvgOptions();

                    // Apply the changes (also updates aria-pressed)
                    applySvgOptions();
                });
            });

            // OCR Toggle functionality
            if (ocrToggleBtn && ocrTextPanel) {
                ocrToggleBtn.addEventListener('click', function() {
                    const isExpanded = this.getAttribute('aria-pressed') === 'true';
                    this.setAttribute('aria-pressed', isExpanded ? 'false' : 'true');
                    ocrTextPanel.hidden = isExpanded;
                });
            }

            // Clean up SVG classes when closing lightbox (but keep saved state)
            const originalCloseLightbox = closeLightbox;
            closeLightbox = function() {
                // Remove SVG-specific classes from image
                lightboxImage.classList.remove(
                    'svg-size-auto', 'svg-size-50', 'svg-size-25', 'svg-size-original',
                    'svg-color-white', 'svg-color-black'
                );
                // Hide code overlay
                codeContainer.hidden = true;
                lightbox.classList.remove('svg-code-mode');
                // Reset OCR state
                lightbox.classList.remove('has-ocr');
                if (ocrToggleBtn) {
                    ocrToggleBtn.setAttribute('aria-pressed', 'false');
                }
                if (ocrTextPanel) {
                    ocrTextPanel.hidden = true;
                }
                originalCloseLightbox();
            };

            // Apply saved SVG options when opening an SVG image
            const originalUpdateLightbox = updateLightbox;
            updateLightbox = function(index, isInitial) {
                // Reset code view when navigating
                codeContainer.hidden = true;
                imageContainer.hidden = false;
                lightbox.classList.remove('svg-code-mode');

                originalUpdateLightbox(index, isInitial);
                // If this is an SVG, apply saved options
                if (lightbox.classList.contains('svg-mode')) {
                    applySvgOptions();
                }
            };

            // Trap focus in lightbox
            lightbox.addEventListener('keydown', function(e) {
                if (e.key !== 'Tab') return;

                const focusables = lightbox.querySelectorAll('button:not([disabled])');
                const first = focusables[0];
                const last = focusables[focusables.length - 1];

                if (e.shiftKey && document.activeElement === first) {
                    e.preventDefault();
                    last.focus();
                } else if (!e.shiftKey && document.activeElement === last) {
                    e.preventDefault();
                    first.focus();
                }
            });

            // Accessible name click-to-expand handler
            document.addEventListener('click', function(e) {
                var accName = e.target.closest('.acc-name[data-expandable]');
                if (accName) {
                    accName.classList.toggle('expanded');
                }
            });

            // Also handle Enter/Space on expandable acc-name for keyboard users
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    var accName = e.target.closest('.acc-name[data-expandable]');
                    if (accName) {
                        e.preventDefault();
                        accName.classList.toggle('expanded');
                    }
                }
            });

            // "Show in context" button — navigate to source page and highlight image
            function buildHighlightScript(imgUrl) {
                return '(function(){' +
                    'var targetSrc=' + JSON.stringify(imgUrl) + ';' +
                    'var target=document.querySelector("img[src=\\""+CSS.escape(targetSrc)+"\\"]");' +
                    'if(!target){' +
                        'var allImgs=document.querySelectorAll("img");' +
                        'for(var i=0;i<allImgs.length;i++){' +
                            'if(allImgs[i].src===targetSrc||allImgs[i].currentSrc===targetSrc' +
                                '||(allImgs[i].dataset&&allImgs[i].dataset.src===targetSrc)){' +
                                'target=allImgs[i];break;' +
                            '}' +
                        '}' +
                    '}' +
                    'if(!target)return{ok:false,error:"Image not found"};' +
                    'var prev=document.getElementById("inspekt-context-overlay");' +
                    'if(prev)prev.remove();' +
                    'target.scrollIntoView({behavior:"smooth",block:"center"});' +
                    'setTimeout(function(){' +
                        'var rect=target.getBoundingClientRect();' +
                        'var sx=window.scrollX,sy=window.scrollY;' +
                        'var overlay=document.createElement("div");' +
                        'overlay.id="inspekt-context-overlay";' +
                        'overlay.style.cssText="position:absolute;' +
                            'left:"+(rect.left+sx-6)+"px;' +
                            'top:"+(rect.top+sy-6)+"px;' +
                            'width:"+(rect.width+12)+"px;' +
                            'height:"+(rect.height+12)+"px;' +
                            'border:3px solid #0969da;' +
                            'border-radius:8px;' +
                            'box-shadow:0 0 0 4px rgba(9,105,218,0.2),0 0 24px rgba(9,105,218,0.3);' +
                            'pointer-events:none;' +
                            'z-index:2147483647;' +
                            'animation:inspektCtxPulse 1.5s ease-in-out 3";' +
                        'var arrow=document.createElement("div");' +
                        'arrow.style.cssText="position:absolute;left:50%;top:-48px;' +
                            'transform:translateX(-50%);font-size:32px;line-height:1;' +
                            'filter:drop-shadow(0 2px 4px rgba(0,0,0,0.3));' +
                            'animation:inspektCtxBounce 1s ease-in-out infinite";' +
                        'arrow.textContent="\\u2B07";' +
                        'arrow.setAttribute("aria-hidden","true");' +
                        'overlay.appendChild(arrow);' +
                        'var style=document.getElementById("inspekt-context-style");' +
                        'if(!style){' +
                            'style=document.createElement("style");' +
                            'style.id="inspekt-context-style";' +
                            'style.textContent="@keyframes inspektCtxPulse{' +
                                '0%,100%{box-shadow:0 0 0 4px rgba(9,105,218,0.2),0 0 24px rgba(9,105,218,0.3)}' +
                                '50%{box-shadow:0 0 0 8px rgba(9,105,218,0.1),0 0 36px rgba(9,105,218,0.2)}' +
                            '}@keyframes inspektCtxBounce{' +
                                '0%,100%{transform:translateX(-50%) translateY(0)}' +
                                '50%{transform:translateX(-50%) translateY(-12px)}' +
                            '}";' +
                            'document.head.appendChild(style);' +
                        '}' +
                        'document.body.appendChild(overlay);' +
                        'setTimeout(function(){' +
                            'overlay.style.transition="opacity 0.4s";' +
                            'overlay.style.opacity="0";' +
                            'setTimeout(function(){overlay.remove();},400);' +
                        '},5000);' +
                    '},600);' +
                    'return{ok:true};' +
                '})()';
            }

            function injectHighlight(imgUrl) {
                return fetch('http://localhost:8000/api/execution/eval', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: buildHighlightScript(imgUrl), timeout: 10 })
                });
            }

            function urlsMatch(a, b) {
                // Compare URLs ignoring trailing slashes and hash fragments
                try {
                    var ua = new URL(a);
                    var ub = new URL(b);
                    return ua.origin === ub.origin &&
                        ua.pathname.replace(/\/+$/, '') === ub.pathname.replace(/\/+$/, '') &&
                        ua.search === ub.search;
                } catch(e) { return false; }
            }

            document.addEventListener('click', function(e) {
                var btn = e.target.closest('.gallery-context-btn');
                if (!btn || btn.classList.contains('gallery-context-btn--loading')) return;

                var pageUrl = window.__INSPEKT_PAGE_URL__;
                if (!pageUrl) return;

                // Read image URL from sibling thumbnail button
                var wrap = btn.closest('.gallery-thumbnail-wrap');
                var thumb = wrap && wrap.querySelector('.gallery-thumbnail');
                var imgUrl = thumb && thumb.getAttribute('data-url');
                if (!imgUrl) return;

                // Set loading state
                btn.classList.add('gallery-context-btn--loading');

                // Check if the browser is already on the source page
                fetch('http://localhost:8000/api/extraction/info')
                .then(function(res) { return res.json(); })
                .then(function(info) {
                    var currentUrl = info && info.result && info.result.url;
                    if (currentUrl && urlsMatch(currentUrl, pageUrl)) {
                        // Already on the source page — just scroll and highlight
                        return injectHighlight(imgUrl);
                    }
                    // Navigate first, then highlight
                    return fetch('http://localhost:8000/api/navigation/open', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: pageUrl, wait: true, timeout: 15 })
                    })
                    .then(function(res) { return res.json(); })
                    .then(function() { return injectHighlight(imgUrl); });
                })
                .then(function(res) { if (res && res.json) return res.json(); })
                .then(function() {
                    btn.classList.remove('gallery-context-btn--loading');
                })
                .catch(function(err) {
                    console.error('Show in context failed:', err);
                    btn.classList.remove('gallery-context-btn--loading');
                });
            });
        })();
