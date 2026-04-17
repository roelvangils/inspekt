/**
 * PDF Interactive Preview Component
 *
 * Provides Equidox-style interactive preview with:
 * - Clickable tag regions
 * - Keyboard navigation (Tab/Shift+Tab)
 * - Details panel showing tag info
 * - Reading order visualization
 * - Reading flow simulation
 *
 * Usage:
 *   const preview = new PDFInteractivePreview(containerId, {
 *     pageImage: 'data:image/png;base64,…',
 *     tags: [...],
 *     imageWidth: 1275,  // Pre-calculated: pageWidth * (dpi / 72)
 *     imageHeight: 1650, // Pre-calculated: pageHeight * (dpi / 72)
 *     onTagSelect: (tag) => { ... }
 *   });
 */

class PDFInteractivePreview {
    constructor(containerId, options = {}) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.error(`Container not found: ${containerId}`);
            return;
        }

        this.options = {
            pageImage: options.pageImage || null,
            tags: options.tags || [],
            pageWidth: options.pageWidth || 612,
            pageHeight: options.pageHeight || 792,
            dpi: options.dpi || 150,
            // Pre-calculated image dimensions (prevents layout shift)
            imageWidth: options.imageWidth || null,
            imageHeight: options.imageHeight || null,
            onTagSelect: options.onTagSelect || null,
            ...options
        };

        // Overlay state - consolidated toggle management
        this.overlayState = {
            enabled: true,      // Master toggle
            showNumbers: true,  // Reading order circles
            showTags: true,     // Tag type labels
            showBoxes: true,    // Bounding rectangles
            showBitmapImages: true,  // Untagged bitmap images (amber)
            showVectorImages: false  // Untagged vector graphics (purple, BETA)
        };

        // Animation state for reading flow simulation
        this.animationState = {
            isRunning: false,
            isPaused: false,
            currentTagIndex: 0,
            timeoutId: null
        };

        // Circle spread state - for spreading overlapping reading order circles on hover
        this.circleSpreadState = {
            hoveredCircleIndex: -1,
            spreadCircles: new Map(),  // Map<tagIndex, {originalX, originalY, targetX, targetY, currentX, currentY}>
            isAnimating: false,
            animationStartTime: null,
            animationFrameId: null,
            animationDirection: null,  // 'spread' or 'collapse'
            // Debounce state
            pendingHoverIndex: -1,     // Circle index waiting to trigger spread
            debounceTimeoutId: null,   // Timeout ID for debounce
            debounceDelay: 250,        // ms to wait before triggering spread
            // Performance cache
            circleCentersCache: null,  // Array of {x, y} or null, indexed by tag index
            circleCentersCacheIsLarge: null,  // Whether cache was computed for large circles
            canvasRect: null,          // Cached bounding rect
            canvasRectTime: 0          // When rect was last cached
        };

        this.selectedTagIndex = -1;
        this.selectedType = 'tag';  // 'tag', 'image', or 'vector'
        this.hoveredTagIndex = -1;  // For tree panel hover highlighting
        this.scale = 1;
        this.tags = this.options.tags;

        // Pan state for Space+drag and two-finger drag
        this.isPanning = false;
        this.isSpacePressed = false;
        this.panStart = { x: 0, y: 0 };
        this.panOffset = { x: 0, y: 0 };  // Current pan offset (used with CSS translate)
        this.panOffsetStart = { x: 0, y: 0 };  // Pan offset when drag started

        // Untagged images and vector graphics
        this.untaggedImages = this.options.untaggedImages || [];
        this.vectorGraphics = this.options.vectorGraphics || [];

        // Calculate image dimensions if not provided
        if (!this.options.imageWidth || !this.options.imageHeight) {
            this.options.imageWidth = Math.round(this.options.pageWidth * (this.options.dpi / 72));
            this.options.imageHeight = Math.round(this.options.pageHeight * (this.options.dpi / 72));
        }

        this.imageWidth = this.options.imageWidth;
        this.imageHeight = this.options.imageHeight;

        this.init();
    }

    init() {
        this.container.innerHTML = '';
        this.container.classList.add('pdf-interactive-preview');

        // Create toolbar first (goes at top)
        this.createToolbar();

        // Create main content wrapper (three-column layout)
        this.mainContent = document.createElement('div');
        this.mainContent.className = 'preview-main-content';

        // Create tree panel (left)
        this.createTreePanel();

        // Create preview area (center)
        this.createPreviewArea();

        // Create details panel (right)
        this.createDetailsPanel();

        // Add main content to container
        this.container.appendChild(this.mainContent);

        // Setup event listeners
        this.setupEventListeners();

        // Initial render
        this.render();
    }

    createTreePanel() {
        // Create container for tree panel
        this.treePanelContainer = document.createElement('div');
        this.treePanelContainer.className = 'preview-tree-panel';

        // Initialize the tree panel component
        this.treePanel = new PreviewTreePanel(this.treePanelContainer, {
            structureTree: this.options.structureTree || null,  // Hierarchical tree data
            readingOrderMap: this.options.readingOrderMap || {},  // For tree/canvas correlation
            tags: this.tags,
            pageNumber: this.options.pageNum || 1,
            onNodeSelect: (tagIndex, nodeId, source) => {
                // Sync from tree to canvas
                this.selectTag(tagIndex, source);
            },
            onNodeHover: (tagIndex) => {
                // Optional: highlight on hover
                this.highlightTagOnHover(tagIndex);
            }
        });

        this.mainContent.appendChild(this.treePanelContainer);
    }

    /**
     * Highlight a tag on hover (from tree panel)
     */
    highlightTagOnHover(tagIndex) {
        // Store hovered index for rendering
        this.hoveredTagIndex = tagIndex;
        this.render();
    }

    createPreviewArea() {
        this.previewArea = document.createElement('div');
        this.previewArea.className = 'preview-area';
        this.previewArea.tabIndex = 0;
        this.previewArea.setAttribute('role', 'application');
        this.previewArea.setAttribute('aria-label', 'PDF page preview with interactive tag regions');

        // Create canvas container
        this.canvasContainer = document.createElement('div');
        this.canvasContainer.className = 'canvas-container';

        // Background image
        if (this.options.pageImage) {
            this.bgImage = document.createElement('img');
            this.bgImage.src = this.options.pageImage;
            this.bgImage.className = 'page-background';
            this.bgImage.alt = 'PDF page';
            // Set dimensions immediately to prevent layout shift
            this.bgImage.style.width = `${this.imageWidth}px`;
            this.bgImage.style.height = `${this.imageHeight}px`;
            this.bgImage.onload = () => this.onImageLoad();
            this.canvasContainer.appendChild(this.bgImage);
        }

        // Overlay canvas for drawing tag regions - set dimensions immediately
        this.canvas = document.createElement('canvas');
        this.canvas.className = 'tag-overlay-canvas';
        this.canvas.width = this.imageWidth;
        this.canvas.height = this.imageHeight;
        this.ctx = this.canvas.getContext('2d');
        this.canvasContainer.appendChild(this.canvas);

        // Tag regions container (for accessibility)
        this.tagRegions = document.createElement('div');
        this.tagRegions.className = 'tag-regions';
        this.tagRegions.setAttribute('role', 'list');
        this.tagRegions.setAttribute('aria-label', 'PDF structure tags');
        this.canvasContainer.appendChild(this.tagRegions);

        this.previewArea.appendChild(this.canvasContainer);
        this.mainContent.appendChild(this.previewArea);
    }

    createDetailsPanel() {
        this.detailsPanel = document.createElement('div');
        this.detailsPanel.className = 'details-panel';
        this.detailsPanel.innerHTML = `
            <h3 class="details-title">Tag Details</h3>
            <div class="details-content">
                <p class="no-selection">Click on a tag region to view details, or use Tab to navigate.</p>
            </div>
        `;
        this.mainContent.appendChild(this.detailsPanel);
    }

    createToolbar() {
        this.toolbar = document.createElement('div');
        this.toolbar.className = 'preview-toolbar';
        this.toolbar.innerHTML = `
            <div class="toolbar-group">
                <button class="toolbar-btn" data-action="zoom-out" title="Zoom out">
                    <span class="icon">−</span>
                </button>
                <span class="zoom-level">100%</span>
                <button class="toolbar-btn" data-action="zoom-in" title="Zoom in">
                    <span class="icon">+</span>
                </button>
                <button class="toolbar-btn" data-action="zoom-fit" title="Fit to width">
                    <span class="icon">⊡</span>
                </button>
            </div>
            <div class="toolbar-group">
                <div class="overlay-dropdown">
                    <button class="dropdown-trigger" aria-expanded="false" aria-haspopup="true">
                        <span>Overlays</span>
                        <span class="dropdown-arrow">▼</span>
                    </button>
                    <div class="dropdown-menu" role="menu">
                        <label class="dropdown-item master-toggle" role="menuitemcheckbox">
                            <input type="checkbox" data-toggle="overlay-master" checked>
                            <span class="checkbox-icon"></span>
                            <span>Show overlays</span>
                        </label>
                        <div class="dropdown-divider"></div>
                        <label class="dropdown-item" role="menuitemcheckbox">
                            <input type="checkbox" data-toggle="show-numbers" checked>
                            <span class="checkbox-icon"></span>
                            <span>Show numbers</span>
                        </label>
                        <label class="dropdown-item" role="menuitemcheckbox">
                            <input type="checkbox" data-toggle="show-tags" checked>
                            <span class="checkbox-icon"></span>
                            <span>Show tags</span>
                        </label>
                        <label class="dropdown-item" role="menuitemcheckbox">
                            <input type="checkbox" data-toggle="show-boxes" checked>
                            <span class="checkbox-icon"></span>
                            <span>Show boxes</span>
                        </label>
                        <div class="dropdown-divider"></div>
                        <label class="dropdown-item" role="menuitemcheckbox">
                            <input type="checkbox" data-toggle="show-bitmap-images" checked>
                            <span class="checkbox-icon"></span>
                            <span class="dropdown-icon" style="color: #f59e0b;">🖼</span>
                            <span>Bitmap images</span>
                        </label>
                        <label class="dropdown-item" role="menuitemcheckbox">
                            <input type="checkbox" data-toggle="show-vector-images">
                            <span class="checkbox-icon"></span>
                            <span class="dropdown-icon" style="color: #8b5cf6;">◇</span>
                            <span>Vector images</span>
                            <span class="beta-tag">BETA</span>
                        </label>
                    </div>
                </div>
            </div>
            <div class="toolbar-group simulate-controls">
                <button class="toolbar-btn simulate-btn" data-action="simulate-reading" title="Simulate reading flow">
                    <span class="icon">▶</span>
                    <span class="btn-label">Simulate</span>
                </button>
                <button class="toolbar-btn pause-btn" data-action="pause-simulation" title="Pause simulation" style="display: none;">
                    <span class="icon">⏸</span>
                </button>
                <button class="toolbar-btn stop-btn" data-action="stop-simulation" title="Stop simulation" style="display: none;">
                    <span class="icon">⏹</span>
                </button>
            </div>
            <div class="toolbar-group">
                <button class="toolbar-btn" data-action="prev-tag" title="Previous tag (Shift+Tab)">
                    <span class="icon">◀</span>
                </button>
                <span class="tag-counter">0 / ${this.tags.length}</span>
                <button class="toolbar-btn" data-action="next-tag" title="Next tag (Tab)">
                    <span class="icon">▶</span>
                </button>
            </div>
        `;
        this.container.appendChild(this.toolbar);

        this.zoomLevelSpan = this.toolbar.querySelector('.zoom-level');
        this.tagCounterSpan = this.toolbar.querySelector('.tag-counter');
        this.simulateBtn = this.toolbar.querySelector('.simulate-btn');
        this.pauseBtn = this.toolbar.querySelector('.pause-btn');
        this.stopBtn = this.toolbar.querySelector('.stop-btn');
    }

    setupEventListeners() {
        // Canvas click
        this.canvas.addEventListener('click', (e) => this.handleCanvasClick(e));

        // Canvas mouse move for circle hover detection (spread feature)
        this.canvas.addEventListener('mousemove', (e) => this.handleCanvasMouseMove(e));
        this.canvas.addEventListener('mouseleave', (e) => this.handleCanvasMouseLeave(e));

        // Keyboard navigation
        this.previewArea.addEventListener('keydown', (e) => this.handleKeyDown(e));

        // Pinch-to-zoom on trackpad (wheel event with ctrlKey)
        // Also supports mouse wheel zoom with Ctrl held
        this.previewArea.addEventListener('wheel', (e) => this.handleWheel(e), { passive: false });

        // Space+drag panning (like Figma/Photoshop hand tool)
        this.previewArea.addEventListener('mousedown', (e) => this.handlePanStart(e));
        this.previewArea.addEventListener('mousemove', (e) => this.handlePanMove(e));
        this.previewArea.addEventListener('mouseup', (e) => this.handlePanEnd(e));
        this.previewArea.addEventListener('mouseleave', (e) => this.handlePanEnd(e));

        // Track Space key for pan mode
        document.addEventListener('keydown', (e) => this.handleSpaceDown(e));
        document.addEventListener('keyup', (e) => this.handleSpaceUp(e));

        // Toolbar buttons
        this.toolbar.addEventListener('click', (e) => {
            const action = e.target.closest('[data-action]')?.dataset.action;
            if (action) this.handleToolbarAction(action);
        });

        // Overlay dropdown
        this.setupDropdownListeners();

        // Window resize
        window.addEventListener('resize', () => this.onResize());

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.overlay-dropdown')) {
                this.closeDropdown();
            }
        });

        // Keyboard navigation for dropdown
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeDropdown();
            }
        });
    }

    handleWheel(e) {
        // Pinch-to-zoom is reported as wheel event with ctrlKey = true
        // Also handle Ctrl+wheel for mouse users
        if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            e.stopPropagation();

            // Calculate zoom based on wheel delta
            // Negative deltaY = zoom in, positive = zoom out
            const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;

            // Get mouse position relative to preview area for zoom-to-point
            const rect = this.previewArea.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;

            // Calculate new scale
            const newScale = Math.max(0.25, Math.min(4, this.scale * zoomFactor));

            if (newScale !== this.scale) {
                // Zoom towards mouse pointer:
                // Calculate where the mouse is pointing in content coordinates
                const contentX = (mouseX - this.panOffset.x) / this.scale;
                const contentY = (mouseY - this.panOffset.y) / this.scale;

                // Calculate new pan offset to keep that point under the mouse
                const newPanX = mouseX - contentX * newScale;
                const newPanY = mouseY - contentY * newScale;

                // Apply zoom and pan together
                this.scale = newScale;
                this.panOffset.x = newPanX;
                this.panOffset.y = newPanY;
                this.updateTransform();
                this.zoomLevelSpan.textContent = `${Math.round(this.scale * 100)}%`;
            }
        } else {
            // Two-finger drag for panning (no modifier key)
            // Prevent the page from scrolling, only pan the preview
            e.preventDefault();
            e.stopPropagation();

            // Apply pan - use deltaX and deltaY from trackpad gesture
            // Subtract because dragging right should move content left (natural scrolling)
            this.panOffset.x -= e.deltaX;
            this.panOffset.y -= e.deltaY;
            this.updateTransform();
        }
    }

    /**
     * Handle Space key down - enter pan mode
     */
    handleSpaceDown(e) {
        // Only activate when preview area is focused and not in an input
        if (e.code !== 'Space') return;
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

        // Check if preview area or its children are focused
        if (!this.previewArea.contains(document.activeElement) && document.activeElement !== this.previewArea) {
            return;
        }

        // Prevent page scroll
        e.preventDefault();

        if (!this.isSpacePressed) {
            this.isSpacePressed = true;
            this.previewArea.classList.add('pan-mode');
        }
    }

    /**
     * Handle Space key up - exit pan mode
     */
    handleSpaceUp(e) {
        if (e.code !== 'Space') return;

        this.isSpacePressed = false;
        this.isPanning = false;
        this.previewArea.classList.remove('pan-mode', 'panning');
    }

    /**
     * Handle mouse down - start panning if Space is held
     */
    handlePanStart(e) {
        if (!this.isSpacePressed) return;

        e.preventDefault();
        this.isPanning = true;
        this.panStart = { x: e.clientX, y: e.clientY };
        this.panOffsetStart = {
            x: this.panOffset.x,
            y: this.panOffset.y
        };
        this.previewArea.classList.add('panning');
    }

    /**
     * Handle mouse move - pan if dragging with Space held
     */
    handlePanMove(e) {
        if (!this.isPanning) return;

        e.preventDefault();
        const dx = e.clientX - this.panStart.x;
        const dy = e.clientY - this.panStart.y;

        // Move content in the same direction as the drag
        this.panOffset.x = this.panOffsetStart.x + dx;
        this.panOffset.y = this.panOffsetStart.y + dy;
        this.updateTransform();
    }

    /**
     * Handle mouse up / leave - stop panning
     */
    handlePanEnd(e) {
        if (this.isPanning) {
            this.isPanning = false;
            this.previewArea.classList.remove('panning');
        }
    }

    // ==========================================
    // Circle Spread Feature - Helper Methods
    // ==========================================

    /**
     * Invalidate the circle centers cache (call when tags change or overlay settings change)
     */
    invalidateCircleCentersCache() {
        this.circleSpreadState.circleCentersCache = null;
        this.circleSpreadState.circleCentersCacheIsLarge = null;
    }

    /**
     * Ensure circle centers cache is populated and valid
     * @returns {Array} Array of {x, y} objects indexed by tag index
     */
    ensureCircleCentersCache() {
        const isLarge = !this.overlayState.showTags;

        // Check if cache is valid
        if (this.circleSpreadState.circleCentersCache !== null &&
            this.circleSpreadState.circleCentersCacheIsLarge === isLarge) {
            return this.circleSpreadState.circleCentersCache;
        }

        // Rebuild cache
        const cache = new Array(this.tags.length);
        for (let i = 0; i < this.tags.length; i++) {
            const tag = this.tags[i];
            if (tag.scaledBbox) {
                const [x0, y0] = tag.scaledBbox;
                cache[i] = { x: x0 - 4, y: y0 - 4 };
            } else {
                cache[i] = null;
            }
        }

        this.circleSpreadState.circleCentersCache = cache;
        this.circleSpreadState.circleCentersCacheIsLarge = isLarge;
        return cache;
    }

    /**
     * Get cached canvas bounding rect (caches for 100ms to avoid layout thrashing)
     * @returns {DOMRect} Canvas bounding client rect
     */
    getCachedCanvasRect() {
        const now = performance.now();
        // Invalidate cache after 100ms or if null
        if (!this.circleSpreadState.canvasRect ||
            now - this.circleSpreadState.canvasRectTime > 100) {
            this.circleSpreadState.canvasRect = this.canvas.getBoundingClientRect();
            this.circleSpreadState.canvasRectTime = now;
        }
        return this.circleSpreadState.canvasRect;
    }

    /**
     * Get the center position of a reading order circle for a given tag
     * @param {Object} tag - Tag object with scaledBbox
     * @param {boolean} isLarge - Whether using large circles (when tags are hidden)
     * @returns {{x: number, y: number}} Center coordinates of the circle
     */
    getCircleCenter(tag, isLarge = false) {
        if (!tag.scaledBbox) return null;
        const [x0, y0] = tag.scaledBbox;
        // Circle center is always at (x0 - 4, y0 - 4) regardless of radius
        return { x: x0 - 4, y: y0 - 4 };
    }

    /**
     * Find which circle (if any) is at the given canvas coordinates
     * Uses squared distance comparison to avoid expensive Math.sqrt
     * @param {number} x - X coordinate in canvas space
     * @param {number} y - Y coordinate in canvas space
     * @returns {number} Tag index or -1 if no circle found
     */
    findCircleAtPoint(x, y) {
        if (!this.overlayState.showNumbers) return -1;

        const isLarge = !this.overlayState.showTags;
        const radius = isLarge ? 18 : 14;
        const radiusSquared = radius * radius;  // Compare squared distances

        // Get cached circle centers
        const centers = this.ensureCircleCentersCache();

        // Check circles in reverse order (top circles first - higher reading order drawn last)
        for (let i = this.tags.length - 1; i >= 0; i--) {
            const center = centers[i];
            if (!center) continue;

            // Check if there's a spread position for this circle
            const spreadState = this.circleSpreadState.spreadCircles.get(i);
            const centerX = spreadState ? spreadState.currentX : center.x;
            const centerY = spreadState ? spreadState.currentY : center.y;

            // Quick bounding box check before expensive distance calc
            const dx = x - centerX;
            const dy = y - centerY;

            // Early exit: if dx or dy alone exceeds radius, skip
            if (dx > radius || dx < -radius || dy > radius || dy < -radius) {
                continue;
            }

            // Squared distance comparison (avoids Math.sqrt)
            const distanceSquared = dx * dx + dy * dy;
            if (distanceSquared <= radiusSquared) {
                return i;
            }
        }
        return -1;
    }

    /**
     * Find all circles that overlap with the target circle
     * Uses squared distance comparison for performance
     * @param {number} targetIndex - Index of the target circle
     * @returns {number[]} Array of indices of overlapping circles
     */
    findOverlappingCircles(targetIndex) {
        const overlapping = [targetIndex];

        // Get cached centers
        const centers = this.ensureCircleCentersCache();
        const targetCenter = centers[targetIndex];
        if (!targetCenter) return overlapping;

        const isLarge = !this.overlayState.showTags;
        const radius = isLarge ? 18 : 14;

        // Overlap threshold: circles touching + buffer
        const overlapThreshold = radius * 2 + 30;
        const thresholdSquared = overlapThreshold * overlapThreshold;

        for (let i = 0; i < this.tags.length; i++) {
            if (i === targetIndex) continue;

            const otherCenter = centers[i];
            if (!otherCenter) continue;

            const dx = otherCenter.x - targetCenter.x;
            const dy = otherCenter.y - targetCenter.y;

            // Quick bounding box check
            if (dx > overlapThreshold || dx < -overlapThreshold ||
                dy > overlapThreshold || dy < -overlapThreshold) {
                continue;
            }

            // Squared distance comparison
            const distanceSquared = dx * dx + dy * dy;
            if (distanceSquared < thresholdSquared) {
                overlapping.push(i);
            }
        }

        return overlapping;
    }

    /**
     * Calculate spread positions for overlapping circles
     * @param {number} anchorIndex - Index of the hovered circle
     * @param {number[]} overlappingIndices - Indices of all overlapping circles
     * @returns {Map} Map of index -> {originalX, originalY, targetX, targetY, currentX, currentY}
     */
    calculateSpreadPositions(anchorIndex, overlappingIndices) {
        const positions = new Map();
        const isLarge = !this.overlayState.showTags;
        const radius = isLarge ? 18 : 14;
        const spacing = radius * 2 + 8; // Circle diameter + gap

        // Limit to closest 10 circles to avoid overwhelming spreads
        const limitedIndices = overlappingIndices.slice(0, 10);

        // Get cached centers
        const centers = this.ensureCircleCentersCache();

        // Get original positions and sort by X coordinate
        const circleData = limitedIndices
            .filter(idx => centers[idx] !== null)
            .map(idx => {
                const center = centers[idx];
                return { index: idx, x: center.x, y: center.y };
            })
            .sort((a, b) => a.x - b.x);

        // Find anchor position in sorted array
        const anchorData = circleData.find(c => c.index === anchorIndex);
        const anchorSortedIdx = circleData.findIndex(c => c.index === anchorIndex);

        // Guard: if anchor not found or no circles, return empty
        if (!anchorData || circleData.length === 0) {
            return positions;
        }

        // Center the spread around the anchor's original position
        const startX = anchorData.x - (anchorSortedIdx * spacing);

        // Calculate target positions
        circleData.forEach((circle, sortedIdx) => {
            let targetX = startX + (sortedIdx * spacing);
            let targetY = circle.y;

            // Clamp to canvas bounds
            const margin = radius + 5;
            targetX = Math.max(margin, Math.min(this.canvas.width - margin, targetX));
            targetY = Math.max(margin, Math.min(this.canvas.height - margin, targetY));

            positions.set(circle.index, {
                originalX: circle.x,
                originalY: circle.y,
                targetX: targetX,
                targetY: targetY,
                currentX: circle.x,
                currentY: circle.y
            });
        });

        return positions;
    }

    // ==========================================
    // Circle Spread Feature - Animation System
    // ==========================================

    /**
     * Linear interpolation
     */
    lerp(start, end, t) {
        return start + (end - start) * t;
    }

    /**
     * Ease-out cubic for smooth deceleration
     */
    easeOutCubic(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    /**
     * Start the spread animation when hovering over overlapping circles
     * @param {number} hoveredIndex - Index of the hovered circle
     */
    startSpreadAnimation(hoveredIndex) {
        // Cancel any existing animation
        if (this.circleSpreadState.animationFrameId) {
            cancelAnimationFrame(this.circleSpreadState.animationFrameId);
        }

        // Find overlapping circles
        const overlapping = this.findOverlappingCircles(hoveredIndex);

        // Only spread if there are multiple overlapping circles
        if (overlapping.length <= 1) {
            this.circleSpreadState.hoveredCircleIndex = hoveredIndex;
            this.render();
            return;
        }

        // Calculate target positions
        const positions = this.calculateSpreadPositions(hoveredIndex, overlapping);

        // If we're already spread, update current positions from existing state
        if (this.circleSpreadState.spreadCircles.size > 0) {
            positions.forEach((pos, idx) => {
                const existing = this.circleSpreadState.spreadCircles.get(idx);
                if (existing) {
                    pos.currentX = existing.currentX;
                    pos.currentY = existing.currentY;
                }
            });
        }

        // Update state
        this.circleSpreadState.hoveredCircleIndex = hoveredIndex;
        this.circleSpreadState.spreadCircles = positions;
        this.circleSpreadState.isAnimating = true;
        this.circleSpreadState.animationStartTime = performance.now();
        this.circleSpreadState.animationDirection = 'spread';

        // Start animation loop
        this.animateSpread();
    }

    /**
     * Start the collapse animation when mouse leaves the circles
     */
    startCollapseAnimation() {
        // Cancel any existing animation
        if (this.circleSpreadState.animationFrameId) {
            cancelAnimationFrame(this.circleSpreadState.animationFrameId);
        }

        if (this.circleSpreadState.spreadCircles.size === 0) {
            return;
        }

        // Swap targets with originals for collapse
        this.circleSpreadState.spreadCircles.forEach((pos) => {
            const tempX = pos.targetX;
            const tempY = pos.targetY;
            pos.targetX = pos.originalX;
            pos.targetY = pos.originalY;
            pos.originalX = tempX;
            pos.originalY = tempY;
        });

        this.circleSpreadState.hoveredCircleIndex = -1;
        this.circleSpreadState.isAnimating = true;
        this.circleSpreadState.animationStartTime = performance.now();
        this.circleSpreadState.animationDirection = 'collapse';

        // Start animation loop
        this.animateSpread();
    }

    /**
     * Animation loop for spreading/collapsing circles
     */
    animateSpread() {
        const duration = 200; // ms
        const elapsed = performance.now() - this.circleSpreadState.animationStartTime;
        const rawProgress = Math.min(1, elapsed / duration);
        const progress = this.easeOutCubic(rawProgress);

        // Update current positions via lerp
        this.circleSpreadState.spreadCircles.forEach((pos) => {
            pos.currentX = this.lerp(pos.originalX, pos.targetX, progress);
            pos.currentY = this.lerp(pos.originalY, pos.targetY, progress);
        });

        // Render
        this.render();

        // Continue or finish animation
        if (rawProgress < 1) {
            this.circleSpreadState.animationFrameId = requestAnimationFrame(() => this.animateSpread());
        } else {
            // Animation complete
            this.circleSpreadState.isAnimating = false;
            this.circleSpreadState.animationFrameId = null;

            // Clean up if collapsed
            if (this.circleSpreadState.animationDirection === 'collapse') {
                this.circleSpreadState.spreadCircles.clear();
                this.circleSpreadState.hoveredCircleIndex = -1;
                this.render();
            }
        }
    }

    // ==========================================
    // Circle Spread Feature - Event Handlers
    // ==========================================

    /**
     * Handle mouse move over canvas for circle hover detection
     */
    handleCanvasMouseMove(e) {
        // Skip if panning or reading flow is running
        if (this.isPanning || this.animationState.isRunning) return;

        // Skip if numbers aren't shown
        if (!this.overlayState.showNumbers) return;

        // Convert client coordinates to canvas coordinates (using cached rect)
        const rect = this.getCachedCanvasRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        // Find circle at point
        const circleIndex = this.findCircleAtPoint(x, y);

        // Update cursor
        this.canvas.style.cursor = circleIndex >= 0 ? 'pointer' : 'default';

        // Check for hover state changes
        if (circleIndex >= 0) {
            // Hovering over a circle
            if (circleIndex !== this.circleSpreadState.hoveredCircleIndex &&
                circleIndex !== this.circleSpreadState.pendingHoverIndex) {
                // New circle - start debounce timer
                this.clearSpreadDebounce();
                this.circleSpreadState.pendingHoverIndex = circleIndex;
                this.circleSpreadState.debounceTimeoutId = setTimeout(() => {
                    // Debounce complete - trigger spread
                    this.circleSpreadState.pendingHoverIndex = -1;
                    this.startSpreadAnimation(circleIndex);
                }, this.circleSpreadState.debounceDelay);
            }
            // If same circle as pending or hovered, do nothing (wait for debounce or already spread)
        } else {
            // Not over any circle directly
            this.clearSpreadDebounce();

            // Check if we should collapse
            if (this.circleSpreadState.hoveredCircleIndex >= 0 ||
                this.circleSpreadState.spreadCircles.size > 0) {
                // If circles are spread, check if mouse is still within the spread zone
                // This prevents flickering when moving between spread circles
                if (this.circleSpreadState.spreadCircles.size > 0 &&
                    this.isPointInSpreadZone(x, y)) {
                    // Still within spread zone - don't collapse yet
                    return;
                }
                this.startCollapseAnimation();
            }
        }
    }

    /**
     * Check if a point is within the bounding box of spread circles (with padding)
     * This prevents collapse when moving between spread circles
     */
    isPointInSpreadZone(x, y) {
        if (this.circleSpreadState.spreadCircles.size === 0) return false;

        const isLarge = !this.overlayState.showTags;
        const radius = isLarge ? 18 : 14;
        const padding = radius + 10;  // Extra padding around the spread zone

        let minX = Infinity, minY = Infinity;
        let maxX = -Infinity, maxY = -Infinity;

        // Find bounding box of all spread circles
        this.circleSpreadState.spreadCircles.forEach((pos) => {
            minX = Math.min(minX, pos.currentX);
            maxX = Math.max(maxX, pos.currentX);
            minY = Math.min(minY, pos.currentY);
            maxY = Math.max(maxY, pos.currentY);
        });

        // Expand by radius + padding
        minX -= radius + padding;
        maxX += radius + padding;
        minY -= radius + padding;
        maxY += radius + padding;

        return x >= minX && x <= maxX && y >= minY && y <= maxY;
    }

    /**
     * Clear any pending spread debounce timer
     */
    clearSpreadDebounce() {
        if (this.circleSpreadState.debounceTimeoutId) {
            clearTimeout(this.circleSpreadState.debounceTimeoutId);
            this.circleSpreadState.debounceTimeoutId = null;
        }
        this.circleSpreadState.pendingHoverIndex = -1;
    }

    /**
     * Handle mouse leaving the canvas
     */
    handleCanvasMouseLeave(e) {
        // Clear any pending debounce
        this.clearSpreadDebounce();

        if (this.circleSpreadState.spreadCircles.size > 0) {
            this.startCollapseAnimation();
        }
    }

    /**
     * Reset circle spread state (called when overlays change, page changes, etc.)
     */
    resetCircleSpreadState() {
        // Clear any pending debounce
        this.clearSpreadDebounce();

        // Cancel any running animation
        if (this.circleSpreadState.animationFrameId) {
            cancelAnimationFrame(this.circleSpreadState.animationFrameId);
        }

        // Reset state
        this.circleSpreadState.hoveredCircleIndex = -1;
        this.circleSpreadState.spreadCircles.clear();
        this.circleSpreadState.isAnimating = false;
        this.circleSpreadState.animationStartTime = null;
        this.circleSpreadState.animationFrameId = null;
        this.circleSpreadState.animationDirection = null;

        // Invalidate caches
        this.invalidateCircleCentersCache();
        this.circleSpreadState.canvasRect = null;
    }

    setupDropdownListeners() {
        const dropdown = this.toolbar.querySelector('.overlay-dropdown');
        const trigger = dropdown.querySelector('.dropdown-trigger');
        const menu = dropdown.querySelector('.dropdown-menu');

        // Toggle dropdown
        trigger.addEventListener('click', (e) => {
            e.stopPropagation();
            const isOpen = dropdown.classList.contains('open');
            if (isOpen) {
                this.closeDropdown();
            } else {
                dropdown.classList.add('open');
                trigger.setAttribute('aria-expanded', 'true');
            }
        });

        // Handle checkbox changes
        menu.addEventListener('change', (e) => {
            const toggle = e.target.dataset.toggle;
            if (toggle) {
                this.handleOverlayChange(toggle, e.target.checked);
            }
        });
    }

    closeDropdown() {
        const dropdown = this.toolbar.querySelector('.overlay-dropdown');
        const trigger = dropdown.querySelector('.dropdown-trigger');
        dropdown.classList.remove('open');
        trigger.setAttribute('aria-expanded', 'false');
    }

    handleOverlayChange(toggle, checked) {
        // Stop any running animation when overlays change
        this.stopReadingFlowSimulation();

        // Reset circle spread state when overlays change
        this.resetCircleSpreadState();

        if (toggle === 'overlay-master') {
            // Master toggle affects all sub-toggles
            this.overlayState.enabled = checked;
            this.overlayState.showNumbers = checked;
            this.overlayState.showTags = checked;
            this.overlayState.showBoxes = checked;
            this.overlayState.showBitmapImages = checked;
            // Note: Vector images stay at user's preference (BETA feature)

            // Update all sub-checkboxes (except vector images which is independent)
            const menu = this.toolbar.querySelector('.dropdown-menu');
            menu.querySelectorAll('input[data-toggle]:not([data-toggle="overlay-master"]):not([data-toggle="show-vector-images"])').forEach(input => {
                input.checked = checked;
                input.indeterminate = false;
            });
        } else {
            // Individual toggle
            const stateKey = this.getStateKey(toggle);
            if (stateKey) {
                this.overlayState[stateKey] = checked;
            }

            // Update master toggle state
            this.updateMasterToggleState();
        }

        this.render();
    }

    getStateKey(toggle) {
        const mapping = {
            'show-numbers': 'showNumbers',
            'show-tags': 'showTags',
            'show-boxes': 'showBoxes',
            'show-bitmap-images': 'showBitmapImages',
            'show-vector-images': 'showVectorImages'
        };
        return mapping[toggle];
    }

    updateMasterToggleState() {
        const masterCheckbox = this.toolbar.querySelector('input[data-toggle="overlay-master"]');
        const { showNumbers, showTags, showBoxes, showBitmapImages } = this.overlayState;
        // Note: showVectorImages is not included as it's a BETA feature

        const allChecked = showNumbers && showTags && showBoxes && showBitmapImages;
        const noneChecked = !showNumbers && !showTags && !showBoxes && !showBitmapImages;

        if (allChecked) {
            masterCheckbox.checked = true;
            masterCheckbox.indeterminate = false;
            this.overlayState.enabled = true;
        } else if (noneChecked) {
            masterCheckbox.checked = false;
            masterCheckbox.indeterminate = false;
            this.overlayState.enabled = false;
        } else {
            // Mixed state - indeterminate
            masterCheckbox.checked = false;
            masterCheckbox.indeterminate = true;
            this.overlayState.enabled = true; // Still considered "enabled" if any sub-toggle is on
        }
    }

    onImageLoad() {
        // Canvas dimensions already set in createPreviewArea()
        // Just trigger render and fit to width
        this.render();

        // Fit to width after initial render for better default view
        requestAnimationFrame(() => {
            this.fitToWidth();
        });
    }

    onResize() {
        // Invalidate canvas rect cache immediately (position may have changed)
        this.circleSpreadState.canvasRect = null;

        // Debounce resize and auto-fit to width
        clearTimeout(this.resizeTimeout);
        this.resizeTimeout = setTimeout(() => this.fitToWidth(), 100);
    }

    handleCanvasClick(e) {
        // Stop any running animation when user clicks
        this.stopReadingFlowSimulation();

        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this.canvas.width / rect.width;
        const scaleY = this.canvas.height / rect.height;
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        // First check if a reading order circle was clicked (including spread positions)
        // This takes priority since circles may be positioned away from their tag's bbox
        const circleIndex = this.findCircleAtPoint(x, y);
        if (circleIndex >= 0) {
            this.selectElement('tag', circleIndex);
            return;
        }

        // Find clicked element (tag, image, or vector) by bounding box
        const clickedElement = this.findElementAtPoint(x, y);
        if (clickedElement) {
            this.selectElement(clickedElement.type, clickedElement.index);
        } else {
            // Clicked on empty area - deselect
            this.deselectTag();
        }
    }

    /**
     * Select an element (tag, image, or vector)
     */
    selectElement(type, index) {
        this.selectedType = type;
        this.selectedTagIndex = index;
        this.render();
        this.updateDetailsPanel();
        this.updateTagCounter();

        // Scroll element into view
        if (type === 'tag') {
            this.scrollTagIntoView(index);
            // Callback
            if (this.options.onTagSelect) {
                this.options.onTagSelect(this.tags[index], index);
            }
        } else if (type === 'image') {
            this.scrollImageIntoView(index);
        } else if (type === 'vector') {
            this.scrollVectorIntoView(index);
        }

        // Announce for screen readers
        this.announceSelection();
    }

    scrollImageIntoView(index) {
        const img = this.untaggedImages[index];
        if (!img.scaledBbox) return;

        const [x0, y0, x1, y1] = img.scaledBbox;
        const centerX = (x0 + x1) / 2 * this.scale;
        const centerY = (y0 + y1) / 2 * this.scale;

        const previewRect = this.previewArea.getBoundingClientRect();
        const scrollLeft = centerX - previewRect.width / 2;
        const scrollTop = centerY - previewRect.height / 2;

        this.previewArea.scrollTo({
            left: Math.max(0, scrollLeft),
            top: Math.max(0, scrollTop),
            behavior: 'smooth'
        });
    }

    scrollVectorIntoView(index) {
        const vg = this.vectorGraphics[index];
        if (!vg.scaledBbox) return;

        const [x0, y0, x1, y1] = vg.scaledBbox;
        const centerX = (x0 + x1) / 2 * this.scale;
        const centerY = (y0 + y1) / 2 * this.scale;

        const previewRect = this.previewArea.getBoundingClientRect();
        const scrollLeft = centerX - previewRect.width / 2;
        const scrollTop = centerY - previewRect.height / 2;

        this.previewArea.scrollTo({
            left: Math.max(0, scrollLeft),
            top: Math.max(0, scrollTop),
            behavior: 'smooth'
        });
    }

    handleKeyDown(e) {
        // Check for Cmd/Ctrl + Plus/Minus for zoom (only when preview is focused)
        const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
        const modifierKey = isMac ? e.metaKey : e.ctrlKey;

        if (modifierKey && (e.key === '=' || e.key === '+')) {
            // Zoom in (= is the unshifted key, + is shifted)
            e.preventDefault();
            e.stopPropagation();
            this.setZoom(this.scale * 1.25);
            return;
        } else if (modifierKey && e.key === '-') {
            // Zoom out
            e.preventDefault();
            e.stopPropagation();
            this.setZoom(this.scale / 1.25);
            return;
        } else if (modifierKey && e.key === '0') {
            // Reset zoom / fit to width
            e.preventDefault();
            e.stopPropagation();
            this.fitToWidth();
            return;
        }

        if (e.key === 'Tab') {
            e.preventDefault();
            // Stop animation on keyboard navigation
            this.stopReadingFlowSimulation();
            if (e.shiftKey) {
                this.selectPreviousTag();
            } else {
                this.selectNextTag();
            }
        } else if (e.key === 'Escape') {
            this.stopReadingFlowSimulation();
            this.deselectTag();
        } else if (e.key === 'Enter' || e.key === ' ') {
            if (this.selectedTagIndex >= 0) {
                // Could trigger an action on the selected tag
                e.preventDefault();
            }
        }
    }

    handleToolbarAction(action) {
        switch (action) {
            case 'zoom-in':
                this.setZoom(this.scale * 1.25);
                break;
            case 'zoom-out':
                this.setZoom(this.scale / 1.25);
                break;
            case 'zoom-fit':
                this.fitToWidth();
                break;
            case 'prev-tag':
                // When paused, navigate without stopping
                if (this.animationState.isPaused) {
                    this.navigateWhilePaused('prev');
                } else {
                    this.stopReadingFlowSimulation();
                    this.selectPreviousTag();
                }
                break;
            case 'next-tag':
                // When paused, navigate without stopping
                if (this.animationState.isPaused) {
                    this.navigateWhilePaused('next');
                } else {
                    this.stopReadingFlowSimulation();
                    this.selectNextTag();
                }
                break;
            case 'simulate-reading':
                this.toggleReadingFlowSimulation();
                break;
            case 'pause-simulation':
                this.pauseReadingFlowSimulation();
                break;
            case 'resume-simulation':
                this.resumeReadingFlowSimulation();
                break;
            case 'stop-simulation':
                this.stopReadingFlowSimulation();
                break;
        }
    }

    // Reading Flow Simulation
    toggleReadingFlowSimulation() {
        if (this.animationState.isPaused) {
            // Resume from paused state
            this.resumeReadingFlowSimulation();
        } else if (this.animationState.isRunning) {
            // Stop if running (clicking simulate again acts as stop)
            this.stopReadingFlowSimulation();
        } else {
            // Start fresh
            this.startReadingFlowSimulation();
        }
    }

    startReadingFlowSimulation() {
        if (this.tags.length === 0) return;

        this.animationState.isRunning = true;
        this.animationState.isPaused = false;
        this.animationState.currentTagIndex = 0;

        // Update button visibility: hide simulate, show pause & stop
        this.simulateBtn.style.display = 'none';
        this.pauseBtn.style.display = 'inline-flex';
        this.stopBtn.style.display = 'inline-flex';

        // Create veil overlay
        this.createVeilOverlay();

        // Start animation
        this.animateReadingFlow();
    }

    pauseReadingFlowSimulation() {
        if (!this.animationState.isRunning || this.animationState.isPaused) return;

        this.animationState.isPaused = true;

        // Clear the pending timeout
        if (this.animationState.timeoutId) {
            clearTimeout(this.animationState.timeoutId);
            this.animationState.timeoutId = null;
        }

        // Update pause button to show resume icon
        this.pauseBtn.querySelector('.icon').textContent = '▶';
        this.pauseBtn.title = 'Resume simulation';
        this.pauseBtn.dataset.action = 'resume-simulation';

        // Now that we're paused, show the details panel for the current tag
        this.updateDetailsPanel();
    }

    resumeReadingFlowSimulation() {
        if (!this.animationState.isRunning || !this.animationState.isPaused) return;

        this.animationState.isPaused = false;

        // Update pause button back to pause icon
        this.pauseBtn.querySelector('.icon').textContent = '⏸';
        this.pauseBtn.title = 'Pause simulation';
        this.pauseBtn.dataset.action = 'pause-simulation';

        // Continue animation from current position
        this.animateReadingFlow();
    }

    stopReadingFlowSimulation() {
        if (!this.animationState.isRunning) return;

        this.animationState.isRunning = false;
        this.animationState.isPaused = false;

        if (this.animationState.timeoutId) {
            clearTimeout(this.animationState.timeoutId);
            this.animationState.timeoutId = null;
        }

        // Update button visibility: show simulate, hide pause & stop
        if (this.simulateBtn) {
            this.simulateBtn.style.display = 'inline-flex';
        }
        if (this.pauseBtn) {
            this.pauseBtn.style.display = 'none';
            // Reset pause button state
            this.pauseBtn.querySelector('.icon').textContent = '⏸';
            this.pauseBtn.title = 'Pause simulation';
            this.pauseBtn.dataset.action = 'pause-simulation';
        }
        if (this.stopBtn) {
            this.stopBtn.style.display = 'none';
        }

        // Remove veil overlay
        if (this.veilCanvas) {
            this.veilCanvas.remove();
            this.veilCanvas = null;
            this.veilCtx = null;
        }

        // Update details panel now that simulation has stopped
        this.updateDetailsPanel();
    }

    /**
     * Navigate to prev/next tag while simulation is paused
     */
    navigateWhilePaused(direction) {
        if (!this.animationState.isPaused) return;

        // Update the animation state's current index
        if (direction === 'prev') {
            this.animationState.currentTagIndex = Math.max(0, this.animationState.currentTagIndex - 1);
        } else {
            this.animationState.currentTagIndex = Math.min(this.tags.length - 1, this.animationState.currentTagIndex + 1);
        }

        // Update the selected tag
        this.selectedTagIndex = this.animationState.currentTagIndex;

        // Redraw the veil for the new position
        this.drawVeilForCurrentTag();

        // Update UI
        this.render();
        this.updateDetailsPanel();
        this.updateTagCounter();
        this.scrollTagIntoView(this.animationState.currentTagIndex);
    }

    /**
     * Draw the veil overlay for the current tag (used during pause navigation)
     */
    drawVeilForCurrentTag() {
        const tag = this.tags[this.animationState.currentTagIndex];
        if (!tag?.scaledBbox || !this.veilCtx) return;

        // Draw 50% veil
        this.veilCtx.clearRect(0, 0, this.veilCanvas.width, this.veilCanvas.height);

        // Detect dark mode
        const isDarkMode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        this.veilCtx.fillStyle = isDarkMode ? 'rgba(0, 0, 0, 0.5)' : 'rgba(255, 255, 255, 0.5)';
        this.veilCtx.fillRect(0, 0, this.veilCanvas.width, this.veilCanvas.height);

        // Cut out current element (transparent)
        const [x0, y0, x1, y1] = tag.scaledBbox;
        const padding = 4;
        this.veilCtx.clearRect(x0 - padding, y0 - padding, (x1 - x0) + padding * 2, (y1 - y0) + padding * 2);

        // Highlight border
        this.veilCtx.strokeStyle = '#3b82f6';
        this.veilCtx.lineWidth = 3;
        this.veilCtx.strokeRect(x0 - padding, y0 - padding, (x1 - x0) + padding * 2, (y1 - y0) + padding * 2);
    }

    createVeilOverlay() {
        this.veilCanvas = document.createElement('canvas');
        this.veilCanvas.className = 'reading-veil-canvas';
        this.veilCanvas.width = this.canvas.width;
        this.veilCanvas.height = this.canvas.height;
        this.veilCtx = this.veilCanvas.getContext('2d');
        this.canvasContainer.appendChild(this.veilCanvas);
    }

    animateReadingFlow() {
        if (!this.animationState.isRunning) return;

        const tag = this.tags[this.animationState.currentTagIndex];
        if (!tag?.scaledBbox) {
            // Skip tags without bounding boxes
            this.animationState.currentTagIndex++;
            if (this.animationState.currentTagIndex < this.tags.length) {
                this.animationState.timeoutId = setTimeout(() => this.animateReadingFlow(), 50);
            } else {
                this.stopReadingFlowSimulation();
            }
            return;
        }

        // Draw 50% veil
        this.veilCtx.clearRect(0, 0, this.veilCanvas.width, this.veilCanvas.height);

        // Detect dark mode
        const isDarkMode = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        this.veilCtx.fillStyle = isDarkMode ? 'rgba(0, 0, 0, 0.5)' : 'rgba(255, 255, 255, 0.5)';
        this.veilCtx.fillRect(0, 0, this.veilCanvas.width, this.veilCanvas.height);

        // Cut out current element (transparent)
        const [x0, y0, x1, y1] = tag.scaledBbox;
        const padding = 4;
        this.veilCtx.clearRect(x0 - padding, y0 - padding, (x1 - x0) + padding * 2, (y1 - y0) + padding * 2);

        // Highlight border
        this.veilCtx.strokeStyle = '#3b82f6';
        this.veilCtx.lineWidth = 3;
        this.veilCtx.strokeRect(x0 - padding, y0 - padding, (x1 - x0) + padding * 2, (y1 - y0) + padding * 2);

        // Update selected tag (but don't update details panel during playback)
        this.selectedTagIndex = this.animationState.currentTagIndex;
        this.render();
        // Note: Details panel is NOT updated during playback - only when paused
        this.updateTagCounter();
        this.scrollTagIntoView(this.animationState.currentTagIndex);

        // Next element
        this.animationState.currentTagIndex++;
        if (this.animationState.currentTagIndex < this.tags.length) {
            this.animationState.timeoutId = setTimeout(() => this.animateReadingFlow(), 250);
        } else {
            // Animation complete - keep last element selected, remove veil
            this.animationState.timeoutId = setTimeout(() => {
                this.stopReadingFlowSimulation();
            }, 500);
        }
    }

    setZoom(newScale) {
        this.scale = Math.max(0.25, Math.min(4, newScale));
        this.updateTransform();
        this.zoomLevelSpan.textContent = `${Math.round(this.scale * 100)}%`;

        // Update veil canvas size if it exists
        if (this.veilCanvas) {
            this.veilCanvas.width = this.canvas.width;
            this.veilCanvas.height = this.canvas.height;
        }
    }

    /**
     * Update the canvas container transform (scale + translate for pan)
     */
    updateTransform() {
        this.canvasContainer.style.transform =
            `translate(${this.panOffset.x}px, ${this.panOffset.y}px) scale(${this.scale})`;
        this.canvasContainer.style.transformOrigin = 'top left';
    }

    /**
     * Set pan offset and update transform
     */
    setPan(x, y) {
        this.panOffset.x = x;
        this.panOffset.y = y;
        this.updateTransform();
    }

    /**
     * Reset pan to center/origin
     */
    resetPan() {
        this.panOffset = { x: 0, y: 0 };
        this.updateTransform();
    }

    fitToWidth() {
        const containerWidth = this.previewArea.clientWidth - 40;
        const newScale = containerWidth / this.imageWidth;
        // Reset pan when fitting to width
        this.panOffset = { x: 0, y: 0 };
        this.setZoom(newScale);
    }

    /**
     * Find element at point - returns { type: 'tag'|'image'|'vector', index: number } or null
     */
    findElementAtPoint(x, y) {
        // Check tags first (they have priority as they're in the structure tree)
        for (let i = this.tags.length - 1; i >= 0; i--) {
            const tag = this.tags[i];
            if (!tag.scaledBbox) continue;
            const [x0, y0, x1, y1] = tag.scaledBbox;
            if (x >= x0 && x <= x1 && y >= y0 && y <= y1) {
                return { type: 'tag', index: i };
            }
        }

        // Check untagged images (if overlay enabled)
        if (this.overlayState.showBitmapImages) {
            for (let i = this.untaggedImages.length - 1; i >= 0; i--) {
                const img = this.untaggedImages[i];
                if (!img.scaledBbox) continue;
                const [x0, y0, x1, y1] = img.scaledBbox;
                if (x >= x0 && x <= x1 && y >= y0 && y <= y1) {
                    return { type: 'image', index: i };
                }
            }
        }

        // Check vector graphics (if overlay enabled)
        if (this.overlayState.showVectorImages) {
            for (let i = this.vectorGraphics.length - 1; i >= 0; i--) {
                const vg = this.vectorGraphics[i];
                if (!vg.scaledBbox) continue;
                const [x0, y0, x1, y1] = vg.scaledBbox;
                if (x >= x0 && x <= x1 && y >= y0 && y <= y1) {
                    return { type: 'vector', index: i };
                }
            }
        }

        return null;
    }

    // Legacy method for backwards compatibility
    findTagAtPoint(x, y) {
        const result = this.findElementAtPoint(x, y);
        if (result && result.type === 'tag') {
            return result.index;
        }
        return -1;
    }

    selectTag(index, source = 'external') {
        if (index < 0 || index >= this.tags.length) return;

        this.selectedType = 'tag';
        this.selectedTagIndex = index;
        this.render();
        this.updateDetailsPanel();
        this.updateTagCounter();

        // Pan to bring tag into view if it's outside the viewport
        this.scrollTagIntoView(index);

        // Sync to tree panel (avoid loop if selection came from tree)
        if (source !== 'tree' && this.treePanel) {
            this.treePanel.selectNode(index, { source: 'canvas', scrollIntoView: true });
        }

        // Callback
        if (this.options.onTagSelect) {
            this.options.onTagSelect(this.tags[index], index);
        }

        // Announce for screen readers
        this.announceSelection();
    }

    selectNextTag() {
        const newIndex = this.selectedTagIndex < this.tags.length - 1
            ? this.selectedTagIndex + 1
            : 0;
        this.selectTag(newIndex);
    }

    selectPreviousTag() {
        const newIndex = this.selectedTagIndex > 0
            ? this.selectedTagIndex - 1
            : this.tags.length - 1;
        this.selectTag(newIndex);
    }

    deselectTag() {
        this.selectedTagIndex = -1;
        this.selectedType = 'tag';
        this.render();
        this.updateDetailsPanel();
        this.updateTagCounter();

        // Sync to tree panel
        if (this.treePanel) {
            this.treePanel.deselectNode();
        }
    }

    /**
     * Pan the canvas to bring a tag into view if it's outside the viewport.
     * Only pans the minimum amount necessary - doesn't center.
     * Uses CSS transform-based panning, not scroll.
     */
    scrollTagIntoView(index, options = {}) {
        const { animate = true } = options;
        const tag = this.tags[index];
        if (!tag || !tag.scaledBbox) return;

        const [x0, y0, x1, y1] = tag.scaledBbox;

        // Get viewport dimensions
        const previewRect = this.previewArea.getBoundingClientRect();
        const viewportWidth = previewRect.width;
        const viewportHeight = previewRect.height;

        // Calculate tag bounds in viewport coordinates
        // viewport position = (content position * scale) + panOffset
        const tagLeft = x0 * this.scale + this.panOffset.x;
        const tagRight = x1 * this.scale + this.panOffset.x;
        const tagTop = y0 * this.scale + this.panOffset.y;
        const tagBottom = y1 * this.scale + this.panOffset.y;

        // Margin from viewport edges
        const margin = 60;

        // Calculate how much we need to pan (if any)
        let panDeltaX = 0;
        let panDeltaY = 0;

        // Check horizontal visibility
        if (tagRight < margin) {
            // Tag is off the left edge - pan right to bring it in
            panDeltaX = margin - tagLeft;
        } else if (tagLeft > viewportWidth - margin) {
            // Tag is off the right edge - pan left to bring it in
            panDeltaX = (viewportWidth - margin) - tagRight;
        }

        // Check vertical visibility
        if (tagBottom < margin) {
            // Tag is above the viewport - pan down to bring it in
            panDeltaY = margin - tagTop;
        } else if (tagTop > viewportHeight - margin) {
            // Tag is below the viewport - pan up to bring it in
            panDeltaY = (viewportHeight - margin) - tagBottom;
        }

        // Only pan if needed
        if (panDeltaX !== 0 || panDeltaY !== 0) {
            const newPanX = this.panOffset.x + panDeltaX;
            const newPanY = this.panOffset.y + panDeltaY;

            if (animate) {
                this.animatePanTo(newPanX, newPanY);
            } else {
                this.panOffset.x = newPanX;
                this.panOffset.y = newPanY;
                this.updateTransform();
            }
        }
    }

    /**
     * Smoothly animate pan to a target position
     */
    animatePanTo(targetX, targetY, duration = 300) {
        const startX = this.panOffset.x;
        const startY = this.panOffset.y;
        const startTime = performance.now();

        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Ease-out cubic
            const eased = 1 - Math.pow(1 - progress, 3);

            this.panOffset.x = startX + (targetX - startX) * eased;
            this.panOffset.y = startY + (targetY - startY) * eased;
            this.updateTransform();

            if (progress < 1) {
                requestAnimationFrame(animate);
            }
        };

        requestAnimationFrame(animate);
    }

    updateDetailsPanel() {
        const content = this.detailsPanel.querySelector('.details-content');

        if (this.selectedTagIndex < 0) {
            content.innerHTML = '<p class="no-selection">Click on a tag region to view details, or use Tab to navigate.</p>';
            return;
        }

        // Handle different element types
        if (this.selectedType === 'image') {
            this.showImageDetails(content, this.untaggedImages[this.selectedTagIndex]);
            return;
        }

        if (this.selectedType === 'vector') {
            this.showVectorDetails(content, this.vectorGraphics[this.selectedTagIndex]);
            return;
        }

        const tag = this.tags[this.selectedTagIndex];
        const color = this.getTagColor(tag.tag_type);

        // Build image audit link for Figure tags
        let imageAuditLink = '';
        if (tag.tag_type === 'Figure' && tag.image_page !== undefined && tag.image_index !== undefined) {
            const targetId = `image-page-${tag.image_page}-index-${tag.image_index}`;
            imageAuditLink = `
                <div class="detail-section">
                    <a href="#${targetId}" class="image-audit-link" data-target="${targetId}">
                        View in Images Audit →
                    </a>
                </div>
            `;
        }

        // Build text preview with copy and speak buttons
        let textPreviewSection = '';
        if (tag.text_preview) {
            const isTruncated = tag.text_preview.length >= 200;
            const displayText = this.escapeHtml(tag.text_preview) + (isTruncated ? '…' : '');
            const langCode = tag.detected_language || (typeof DOCUMENT_LANGUAGE !== 'undefined' ? DOCUMENT_LANGUAGE : 'en');
            textPreviewSection = `
                <div class="detail-section">
                    <div class="label-with-actions">
                        <label>Text Preview</label>
                        <div class="text-actions">
                            <button class="speak-text-btn" data-text="${this.escapeHtml(tag.text_preview).replace(/"/g, '&quot;')}" data-lang="${langCode}" title="Read aloud">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon>
                                    <path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>
                                    <path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>
                                </svg>
                            </button>
                            <button class="stop-speech-btn" title="Stop speaking" style="display: none;">
                                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="6" y="6" width="12" height="12" rx="2" ry="2"></rect>
                                </svg>
                            </button>
                        </div>
                    </div>
                    <div class="text-preview-container">
                        <div class="text-preview">${displayText}</div>
                        <button class="copy-text-btn" data-text="${this.escapeHtml(tag.text_preview).replace(/"/g, '&quot;')}">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                            </svg>
                            <span class="copy-text-label">Copy</span>
                        </button>
                    </div>
                </div>
            `;
        }

        // Build language tag section
        let languageSection = '';
        if (tag.detected_language) {
            const langName = this.getLanguageDisplayName(tag.detected_language);
            languageSection = `
                <div class="detail-section">
                    <label>Detected Language</label>
                    <span class="language-tag">${langName}</span>
                </div>
            `;
        }

        content.innerHTML = `
            <div class="tag-detail-header">
                <span class="tag-badge" style="background: ${color}">${tag.tag_type}</span>
                <span class="reading-order">#${tag.reading_order}</span>
            </div>
            ${textPreviewSection}
            ${languageSection}
            ${tag.alt_text ? `
                <div class="detail-section">
                    <label>Alt Text</label>
                    <div class="alt-text">${this.escapeHtml(tag.alt_text)}</div>
                </div>
            ` : ''}
            ${tag.has_issues ? `
                <div class="detail-section issue-warning">
                    <label>⚠️ Issues</label>
                    <div class="issues-list">Accessibility issues detected</div>
                </div>
            ` : ''}
            ${imageAuditLink}
            <div class="detail-section">
                <label>Bounding Box</label>
                <div class="bbox-info">
                    (${tag.bbox ? tag.bbox.map(n => Math.round(n)).join(', ') : 'N/A'})
                </div>
            </div>
            ${this.renderTagCallout(tag.tag_type)}
        `;

        // Setup click handler for image audit link
        const auditLink = content.querySelector('.image-audit-link');
        if (auditLink) {
            auditLink.addEventListener('click', (e) => {
                e.preventDefault();
                const targetId = auditLink.dataset.target;
                const targetRow = document.getElementById(targetId);
                if (targetRow) {
                    // Scroll to the row
                    targetRow.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    // Add highlight animation
                    targetRow.classList.add('highlight-row');
                    setTimeout(() => {
                        targetRow.classList.remove('highlight-row');
                    }, 2000);
                }
            });
        }

        // Setup copy button handler
        const copyBtn = content.querySelector('.copy-text-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', async () => {
                const text = copyBtn.dataset.text;
                try {
                    await navigator.clipboard.writeText(text);
                    copyBtn.classList.add('copied');
                    copyBtn.querySelector('.copy-text-label').textContent = 'Copied!';
                    setTimeout(() => {
                        copyBtn.classList.remove('copied');
                        copyBtn.querySelector('.copy-text-label').textContent = 'Copy';
                    }, 2000);
                } catch (err) {
                    console.error('Failed to copy text:', err);
                }
            });
        }

        // Setup text-to-speech handlers
        const speakBtn = content.querySelector('.speak-text-btn');
        const stopBtn = content.querySelector('.stop-speech-btn');
        if (speakBtn && stopBtn) {
            speakBtn.addEventListener('click', () => {
                const text = speakBtn.dataset.text;
                const lang = speakBtn.dataset.lang;
                this.speakText(text, lang, speakBtn, stopBtn);
            });

            stopBtn.addEventListener('click', () => {
                this.stopSpeaking(speakBtn, stopBtn);
            });
        }
    }

    getLanguageDisplayName(code) {
        const languageNames = {
            'en': 'English',
            'nl': 'Dutch',
            'fr': 'French',
            'de': 'German',
            'es': 'Spanish',
            'it': 'Italian',
            'pt': 'Portuguese'
        };
        return languageNames[code] || code.toUpperCase();
    }

    /**
     * Speak text using the Web Speech API
     */
    speakText(text, lang, speakBtn, stopBtn) {
        // Stop any current speech first
        if (window.speechSynthesis.speaking) {
            window.speechSynthesis.cancel();
        }

        const utterance = new SpeechSynthesisUtterance(text);

        // Find a voice matching the language
        const voices = window.speechSynthesis.getVoices();
        const matchingVoice = voices.find(voice => voice.lang.startsWith(lang)) ||
                             voices.find(voice => voice.lang.startsWith('en'));
        if (matchingVoice) {
            utterance.voice = matchingVoice;
        }
        utterance.lang = lang;

        // Update button states
        speakBtn.style.display = 'none';
        stopBtn.style.display = 'flex';
        speakBtn.classList.add('speaking');

        // Handle speech end
        utterance.onend = () => {
            this.stopSpeaking(speakBtn, stopBtn);
        };

        utterance.onerror = () => {
            this.stopSpeaking(speakBtn, stopBtn);
        };

        window.speechSynthesis.speak(utterance);
    }

    /**
     * Stop any ongoing speech
     */
    stopSpeaking(speakBtn, stopBtn) {
        window.speechSynthesis.cancel();
        speakBtn.style.display = 'flex';
        stopBtn.style.display = 'none';
        speakBtn.classList.remove('speaking');
    }

    /**
     * Get tag reference information from the PDF_TAG_REFERENCE global
     */
    getTagReference(tagType) {
        if (typeof PDF_TAG_REFERENCE === 'undefined' || !PDF_TAG_REFERENCE.tags) {
            return null;
        }
        return PDF_TAG_REFERENCE.tags.find(t => t.pdfTag === tagType);
    }

    /**
     * Render simple markdown-like formatting for callouts
     */
    renderMarkdown(text) {
        if (!text) return '';
        return text
            // Code: `text` -> <code>text</code>
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            // Bold: **text** -> <strong>text</strong>
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            // Links: [text](url) -> <a href="url">text</a>
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
            // Paragraphs: double newlines
            .replace(/\n\n/g, '</p><p>')
            // Single newlines to breaks
            .replace(/\n/g, '<br>');
    }

    /**
     * Render the educational callout for a tag type
     */
    renderTagCallout(tagType) {
        const tagRef = this.getTagReference(tagType);
        if (!tagRef || !tagRef.callout) {
            return '';
        }

        const htmlEquiv = tagRef.htmlEquivalent
            ? `<div class="callout-html-equiv">
                <span class="callout-label">HTML equivalent:</span>
                <code>${this.escapeHtml(tagRef.htmlEquivalent)}</code>
               </div>`
            : '';

        const semanticBadge = tagRef.semanticType
            ? `<span class="semantic-badge semantic-${tagRef.semanticType.toLowerCase()}">${tagRef.semanticType}</span>`
            : '';

        return `
            <div class="tag-callout">
                <div class="callout-header">
                    <span class="callout-title">About the ${tagType} tag</span>
                    ${semanticBadge}
                </div>
                ${htmlEquiv}
                <div class="callout-content">
                    <p>${this.renderMarkdown(tagRef.callout)}</p>
                </div>
                ${tagRef.documentationUrl ? `
                    <div class="callout-footer">
                        <a href="${tagRef.documentationUrl}" target="_blank" rel="noopener" class="callout-link">
                            Learn more about PDF structure tags →
                        </a>
                    </div>
                ` : ''}
            </div>
        `;
    }

    updateTagCounter() {
        const current = this.selectedTagIndex >= 0 ? this.selectedTagIndex + 1 : 0;
        this.tagCounterSpan.textContent = `${current} / ${this.tags.length}`;
    }

    announceSelection() {
        // Create live region for screen reader announcement
        let liveRegion = document.getElementById('pdf-preview-live');
        if (!liveRegion) {
            liveRegion = document.createElement('div');
            liveRegion.id = 'pdf-preview-live';
            liveRegion.setAttribute('aria-live', 'polite');
            liveRegion.setAttribute('aria-atomic', 'true');
            liveRegion.className = 'sr-only';
            document.body.appendChild(liveRegion);
        }

        if (this.selectedType === 'image') {
            const img = this.untaggedImages[this.selectedTagIndex];
            liveRegion.textContent = `Selected untagged image, ${Math.round(img.width)} by ${Math.round(img.height)} pixels. This image is not accessible to screen readers.`;
        } else if (this.selectedType === 'vector') {
            const vg = this.vectorGraphics[this.selectedTagIndex];
            liveRegion.textContent = `Selected untagged vector graphic, ${Math.round(vg.width)} by ${Math.round(vg.height)} pixels. This graphic is not accessible to screen readers.`;
        } else {
            const tag = this.tags[this.selectedTagIndex];
            liveRegion.textContent = `Selected ${tag.tag_type}, reading order ${tag.reading_order}${tag.text_preview ? `, ${tag.text_preview}` : ''}`;
        }
    }

    render() {
        if (!this.ctx || !this.imageWidth) return;

        // Clear canvas
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

        // If overlays are completely disabled, don't draw anything
        if (!this.overlayState.enabled && !this.overlayState.showNumbers && !this.overlayState.showTags && !this.overlayState.showBoxes) {
            this.updateAccessibleRegions();
            return;
        }

        // Calculate scale from PDF to image coordinates
        const pdfToImageScale = this.imageWidth / (this.options.pageWidth * (this.options.dpi / 72));

        // Draw tag regions
        this.tags.forEach((tag, index) => {
            if (!tag.bbox) return;

            // Scale bbox from PDF coordinates to image coordinates
            const [x0, y0, x1, y1] = tag.bbox;
            const pageHeight = this.options.pageHeight;

            // PDF coords have origin at bottom-left, image at top-left
            const scaledBbox = [
                x0 * (this.options.dpi / 72),
                (pageHeight - y1) * (this.options.dpi / 72),
                x1 * (this.options.dpi / 72),
                (pageHeight - y0) * (this.options.dpi / 72)
            ];
            tag.scaledBbox = scaledBbox;

            const isSelected = this.selectedType === 'tag' && index === this.selectedTagIndex;
            const isHovered = index === this.hoveredTagIndex;
            this.drawTagRegion(scaledBbox, tag, isSelected, index, isHovered);
        });

        // Draw reading order connections
        if (this.overlayState.showNumbers && this.tags.length > 1) {
            this.drawReadingOrderConnections();
        }

        // Draw untagged bitmap images
        // NOTE: Image bboxes from PyMuPDF are already in top-left origin (screen coords)
        // No Y-flip needed unlike structure tree tags
        if (this.overlayState.enabled && this.overlayState.showBitmapImages && this.untaggedImages.length > 0) {
            this.untaggedImages.forEach((img, index) => {
                if (!img.bbox) return;

                // Scale bbox - PyMuPDF coords are already top-left origin
                const [x0, y0, x1, y1] = img.bbox;
                const scaleFactor = this.options.dpi / 72;

                const scaledBbox = [
                    x0 * scaleFactor,
                    y0 * scaleFactor,
                    x1 * scaleFactor,
                    y1 * scaleFactor
                ];
                img.scaledBbox = scaledBbox;

                const isSelected = this.selectedType === 'image' && index === this.selectedTagIndex;
                this.drawImageRegion(scaledBbox, img, isSelected);
            });
        }

        // Draw vector graphics (BETA)
        // NOTE: Vector bboxes from PyMuPDF are already in top-left origin (screen coords)
        // No Y-flip needed unlike structure tree tags
        if (this.overlayState.enabled && this.overlayState.showVectorImages && this.vectorGraphics.length > 0) {
            this.vectorGraphics.forEach((vg, index) => {
                if (!vg.bbox) return;

                // Scale bbox - PyMuPDF coords are already top-left origin
                const [x0, y0, x1, y1] = vg.bbox;
                const scaleFactor = this.options.dpi / 72;

                const scaledBbox = [
                    x0 * scaleFactor,
                    y0 * scaleFactor,
                    x1 * scaleFactor,
                    y1 * scaleFactor
                ];
                vg.scaledBbox = scaledBbox;

                const isSelected = this.selectedType === 'vector' && index === this.selectedTagIndex;
                this.drawVectorRegion(scaledBbox, vg, isSelected);
            });
        }

        // Update accessible tag regions
        this.updateAccessibleRegions();
    }

    drawTagRegion(bbox, tag, isSelected, index, isTreeHovered = false) {
        const [x0, y0, x1, y1] = bbox;
        const color = this.getTagColor(tag.tag_type);

        // Parse color
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);

        // Draw bounding box (fill and stroke)
        if (this.overlayState.showBoxes) {
            // Fill - stronger highlight when selected or hovered from tree
            if (isSelected) {
                this.ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.3)`;
            } else if (isTreeHovered) {
                this.ctx.fillStyle = `rgba(59, 130, 246, 0.2)`; // Blue glow for tree hover
            } else {
                this.ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.1)`;
            }
            this.ctx.fillRect(x0, y0, x1 - x0, y1 - y0);

            // Stroke - emphasized when hovered from tree
            if (isSelected) {
                this.ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, 1)`;
                this.ctx.lineWidth = 3;
            } else if (isTreeHovered) {
                this.ctx.strokeStyle = 'rgba(59, 130, 246, 0.9)'; // Blue border for tree hover
                this.ctx.lineWidth = 2;
            } else {
                this.ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, 0.6)`;
                this.ctx.lineWidth = 2;
            }
            this.ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
        }

        // Reading order number
        if (this.overlayState.showNumbers) {
            // Size configuration - use larger labels when tags are hidden for better visibility
            const isLarge = !this.overlayState.showTags;
            const radius = isLarge ? 18 : 14;
            const fontSize = isLarge ? 16 : 14;
            const fontWeight = isLarge ? 'bold ' : '';

            // Check for animated position from circle spread state
            let circleCenterX, circleCenterY;
            const spreadState = this.circleSpreadState.spreadCircles.get(index);

            if (spreadState) {
                // Use animated position
                circleCenterX = spreadState.currentX;
                circleCenterY = spreadState.currentY;
            } else {
                // Use original position
                circleCenterX = x0 - 4;
                circleCenterY = y0 - 4;
            }

            // Determine if this circle is hovered
            const isHovered = index === this.circleSpreadState.hoveredCircleIndex;

            // Draw circle with hover highlight
            this.ctx.beginPath();
            this.ctx.arc(circleCenterX, circleCenterY, radius, 0, Math.PI * 2);

            // Fill color: red if selected, blue if hovered, dark slate otherwise
            if (isSelected) {
                this.ctx.fillStyle = '#dc2626';
            } else if (isHovered) {
                this.ctx.fillStyle = '#2563eb';
            } else {
                this.ctx.fillStyle = '#1e293b';
            }
            this.ctx.fill();

            // Border: thicker when hovered
            this.ctx.strokeStyle = '#fff';
            this.ctx.lineWidth = isHovered ? 3 : 2;
            this.ctx.stroke();

            // Number text
            this.ctx.fillStyle = '#fff';
            this.ctx.font = `${fontWeight}${fontSize}px system-ui, sans-serif`;
            this.ctx.textAlign = 'center';
            this.ctx.textBaseline = 'middle';
            this.ctx.fillText(String(tag.reading_order), circleCenterX, circleCenterY);
        }

        // Label (tag type)
        if (this.overlayState.showTags) {
            // Size configuration
            const isLarge = !this.overlayState.showNumbers; // Larger when numbers are hidden
            const labelFontSize = isLarge ? 14 : 12;
            const labelHeight = isLarge ? 22 : 18;
            const labelPaddingY = isLarge ? 4 : 3;

            this.ctx.font = `${labelFontSize}px system-ui, sans-serif`;
            this.ctx.fillStyle = `rgba(${r}, ${g}, ${b}, 0.9)`;
            const labelText = tag.tag_type;
            const labelWidth = this.ctx.measureText(labelText).width + 10;
            this.ctx.fillRect(x0 + 2, y0 + 2, labelWidth, labelHeight);

            this.ctx.fillStyle = '#fff';
            this.ctx.textAlign = 'left';
            this.ctx.textBaseline = 'top';
            this.ctx.fillText(labelText, x0 + 7, y0 + 2 + labelPaddingY);
        }

        // Issue indicator (always show if there are issues)
        if (tag.has_issues) {
            this.ctx.fillStyle = '#dc2626';
            this.ctx.beginPath();
            this.ctx.moveTo(x1 - 15, y0 + 5);
            this.ctx.lineTo(x1 - 9, y0 + 15);
            this.ctx.lineTo(x1 - 3, y0 + 5);
            this.ctx.closePath();
            this.ctx.fill();
        }
    }

    drawReadingOrderConnections() {
        this.ctx.strokeStyle = 'rgba(30, 64, 175, 0.3)';
        this.ctx.lineWidth = 1;
        this.ctx.setLineDash([4, 4]);

        for (let i = 0; i < this.tags.length - 1; i++) {
            const tag1 = this.tags[i];
            const tag2 = this.tags[i + 1];
            if (!tag1.scaledBbox || !tag2.scaledBbox) continue;

            const [x0_1, y0_1, x1_1, y1_1] = tag1.scaledBbox;
            const [x0_2, y0_2, x1_2, y1_2] = tag2.scaledBbox;

            const cx1 = (x0_1 + x1_1) / 2;
            const cy1 = (y0_1 + y1_1) / 2;
            const cx2 = (x0_2 + x1_2) / 2;
            const cy2 = (y0_2 + y1_2) / 2;

            this.ctx.beginPath();
            this.ctx.moveTo(cx1, cy1);
            this.ctx.lineTo(cx2, cy2);
            this.ctx.stroke();
        }

        this.ctx.setLineDash([]);
    }

    /**
     * Draw an untagged image region with dotted amber border
     */
    drawImageRegion(bbox, imageData, isSelected) {
        const ctx = this.ctx;
        const [x0, y0, x1, y1] = bbox;
        const width = x1 - x0;
        const height = y1 - y0;

        // Dotted border
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = isSelected ? '#d97706' : 'rgba(245, 158, 11, 0.8)';
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.strokeRect(x0, y0, width, height);
        ctx.setLineDash([]);

        // Semi-transparent fill when selected
        if (isSelected) {
            ctx.fillStyle = 'rgba(245, 158, 11, 0.15)';
            ctx.fillRect(x0, y0, width, height);
        }

        // Small image icon in top-left corner
        const iconSize = 20;
        const iconPadding = 4;

        // Icon background circle
        ctx.fillStyle = '#f59e0b';
        ctx.beginPath();
        ctx.arc(x0 + iconPadding + iconSize/2, y0 + iconPadding + iconSize/2, iconSize/2, 0, Math.PI * 2);
        ctx.fill();

        // Icon symbol (simplified image icon)
        ctx.fillStyle = 'white';
        ctx.font = 'bold 12px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('🖼', x0 + iconPadding + iconSize/2, y0 + iconPadding + iconSize/2);
    }

    /**
     * Draw a vector graphic region with dotted purple border
     */
    drawVectorRegion(bbox, vectorData, isSelected) {
        const ctx = this.ctx;
        const [x0, y0, x1, y1] = bbox;
        const width = x1 - x0;
        const height = y1 - y0;

        // Dotted border
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = isSelected ? '#7c3aed' : 'rgba(139, 92, 246, 0.8)';
        ctx.lineWidth = isSelected ? 3 : 2;
        ctx.strokeRect(x0, y0, width, height);
        ctx.setLineDash([]);

        // Semi-transparent fill when selected
        if (isSelected) {
            ctx.fillStyle = 'rgba(139, 92, 246, 0.15)';
            ctx.fillRect(x0, y0, width, height);
        }

        // Small vector icon in top-left corner
        const iconSize = 20;
        const iconPadding = 4;

        // Icon background circle
        ctx.fillStyle = '#8b5cf6';
        ctx.beginPath();
        ctx.arc(x0 + iconPadding + iconSize/2, y0 + iconPadding + iconSize/2, iconSize/2, 0, Math.PI * 2);
        ctx.fill();

        // Icon symbol (diamond for vector)
        ctx.fillStyle = 'white';
        ctx.font = 'bold 12px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('◇', x0 + iconPadding + iconSize/2, y0 + iconPadding + iconSize/2);
    }

    updateAccessibleRegions() {
        // Clear existing regions
        this.tagRegions.innerHTML = '';

        // Create accessible buttons for each tag
        this.tags.forEach((tag, index) => {
            if (!tag.scaledBbox) return;

            const [x0, y0, x1, y1] = tag.scaledBbox;
            const region = document.createElement('button');
            region.className = 'tag-region-btn';
            region.setAttribute('role', 'listitem');
            region.style.cssText = `
                position: absolute;
                left: ${x0}px;
                top: ${y0}px;
                width: ${x1 - x0}px;
                height: ${y1 - y0}px;
                background: transparent;
                border: none;
                cursor: pointer;
            `;
            region.setAttribute('aria-label', `${tag.tag_type}, reading order ${tag.reading_order}${tag.text_preview ? `, ${tag.text_preview}` : ''}`);
            region.addEventListener('click', () => {
                this.stopReadingFlowSimulation();
                this.selectTag(index);
            });

            this.tagRegions.appendChild(region);
        });
    }

    /**
     * Show details for an untagged image
     */
    showImageDetails(content, imageData) {
        const thumbnailHtml = imageData.preview_src
            ? `<div class="detail-section">
                <label>Preview</label>
                <img src="${imageData.preview_src}"
                     class="image-preview-thumb" alt="Image preview">
               </div>`
            : '';

        content.innerHTML = `
            <div class="tag-detail-header">
                <span class="tag-badge untagged-image-badge" style="background: #f59e0b;">
                    <span class="badge-icon">🖼</span>
                    Untagged Image
                </span>
            </div>

            <div class="untagged-warning">
                <div class="warning-header">
                    <span class="warning-icon">⚠️</span>
                    <strong>This image is NOT tagged</strong>
                </div>
                <p>This image is not exposed to assistive technology. Screen reader users cannot perceive it.</p>
            </div>

            ${thumbnailHtml}

            <div class="detail-section">
                <label>Dimensions</label>
                <span>${Math.round(imageData.width)} × ${Math.round(imageData.height)} px</span>
            </div>

            ${imageData.image_type ? `
            <div class="detail-section">
                <label>Type</label>
                <span>${this.escapeHtml(imageData.image_type)}</span>
            </div>
            ` : ''}

            <div class="detail-section">
                <label>Bounding Box</label>
                <div class="bbox-info">
                    (${imageData.bbox ? imageData.bbox.map(n => Math.round(n)).join(', ') : 'N/A'})
                </div>
            </div>

            <div class="untagged-guidance">
                <p><strong>To fix:</strong> Add a <code>&lt;Figure&gt;</code> tag to the PDF structure tree with appropriate alt text.</p>
            </div>
        `;
    }

    /**
     * Show details for an untagged vector graphic
     */
    showVectorDetails(content, vectorData) {
        const thumbnailHtml = vectorData.preview_src
            ? `<div class="detail-section">
                <label>Preview</label>
                <img src="${vectorData.preview_src}"
                     class="image-preview-thumb" alt="Vector graphic preview">
               </div>`
            : '';

        content.innerHTML = `
            <div class="tag-detail-header">
                <span class="tag-badge untagged-vector-badge" style="background: #8b5cf6;">
                    <span class="badge-icon">◇</span>
                    Untagged Vector
                </span>
                <span class="beta-badge">BETA</span>
            </div>

            <div class="untagged-warning vector-warning">
                <div class="warning-header">
                    <span class="warning-icon">⚠️</span>
                    <strong>This vector graphic is NOT tagged</strong>
                </div>
                <p>This graphic is not exposed to assistive technology. Screen reader users cannot perceive it.</p>
            </div>

            ${thumbnailHtml}

            <div class="detail-section">
                <label>Dimensions</label>
                <span>${Math.round(vectorData.width)} × ${Math.round(vectorData.height)} px</span>
            </div>

            ${vectorData.path_count ? `
            <div class="detail-section">
                <label>Path Count</label>
                <span>${vectorData.path_count} paths</span>
            </div>
            ` : ''}

            <div class="detail-section">
                <label>Bounding Box</label>
                <div class="bbox-info">
                    (${vectorData.bbox ? vectorData.bbox.map(n => Math.round(n)).join(', ') : 'N/A'})
                </div>
            </div>

            <div class="untagged-guidance">
                <p><strong>To fix:</strong> Add a <code>&lt;Figure&gt;</code> tag to the PDF structure tree, or mark as decorative using <code>/Artifact</code>.</p>
            </div>
        `;
    }

    getTagColor(tagType) {
        const colors = {
            'H1': '#dc2626', 'H2': '#ea580c', 'H3': '#ca8a04',
            'H4': '#65a30d', 'H5': '#16a34a', 'H6': '#0d9488',
            'P': '#0284c7', 'Span': '#7c3aed',
            'Figure': '#a855f7', 'Table': '#06b6d4',
            'L': '#f97316', 'LI': '#fb923c',
            'Link': '#eab308', 'Form': '#ec4899',
            'Document': '#1f2937', 'Sect': '#4b5563'
        };
        return colors[tagType] || '#9ca3af';
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Public API
    setTags(tags) {
        this.tags = tags;
        this.selectedTagIndex = -1;
        this.stopReadingFlowSimulation();
        this.resetCircleSpreadState();
        this.render();
        this.updateTagCounter();
    }

    setPageImage(imageDataUrl) {
        this.options.pageImage = imageDataUrl;
        if (this.bgImage) {
            this.bgImage.src = imageDataUrl;
        }
    }

    getSelectedTag() {
        return this.selectedTagIndex >= 0 ? this.tags[this.selectedTagIndex] : null;
    }

    // Method to update dimensions when switching pages
    updateDimensions(imageWidth, imageHeight) {
        this.imageWidth = imageWidth;
        this.imageHeight = imageHeight;
        this.canvas.width = imageWidth;
        this.canvas.height = imageHeight;
        if (this.bgImage) {
            this.bgImage.style.width = `${imageWidth}px`;
            this.bgImage.style.height = `${imageHeight}px`;
        }
        if (this.veilCanvas) {
            this.veilCanvas.width = imageWidth;
            this.veilCanvas.height = imageHeight;
        }
    }
}

// Export for use in reports
if (typeof window !== 'undefined') {
    window.PDFInteractivePreview = PDFInteractivePreview;
}
