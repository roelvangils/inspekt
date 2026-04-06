/**
 * Preview Tree Panel Component
 *
 * A hierarchical structure tree panel for the PDF Interactive Preview.
 * Shows the PDF structure tree filtered to the current page, with colored
 * tag labels matching the existing Structure Tree section.
 *
 * Features:
 * - Hierarchical tree with expand/collapse
 * - Hide Generic Tags (Span, Div, NonStruct, Private)
 * - Hide Identical Siblings (collapse 3+ consecutive same-type siblings)
 * - Collapse All / Expand All toggle
 * - Cmd/Ctrl+Click to expand/collapse all children
 * - Bidirectional sync with canvas via reading order correlation
 */

// Generic PDF tags that add noise without semantic meaning
// These are structural containers without semantic value
// Note: Named differently to avoid conflict with structure-tree.js
const PREVIEW_GENERIC_TAGS = [
    // Inline/block containers
    'Span', 'Div',
    // Explicitly non-structural
    'NonStruct', 'Private',
    // Document-level containers
    'StructTreeRoot', 'Document', 'DocumentFragment', 'Part',
    // Non-content elements (page artifacts)
    'Artifact'
];

class PreviewTreePanel {
    constructor(container, options = {}) {
        this.container = container;
        this.options = {
            structureTree: null,      // Full hierarchical structure tree
            readingOrderMap: {},      // Maps page number to array of node_ids
            tags: [],                 // Flat tags for current page (for canvas sync)
            pageNumber: 1,
            onNodeSelect: null,       // (tagIndex, nodeId, source) => void
            onNodeHover: null,        // (tagIndex) => void
            ...options
        };

        this.structureTree = this.options.structureTree;
        this.readingOrderMap = this.options.readingOrderMap;
        this.tags = this.options.tags;
        this.pageNumber = this.options.pageNumber;

        this.selectedNodeId = null;
        this.selectedTagIndex = -1;
        this.isCollapsed = false;
        this.isTreeExpanded = true;  // For Collapse All / Expand All

        // Filter states
        this.hideGenericTags = false;
        this.hideIdenticalSiblings = false;

        // Expanded nodes tracking
        this.expandedNodes = new Set();

        // Build node_id to tag index mapping for canvas sync
        this.nodeIdToTagIndex = new Map();
        this.tagIndexToNodeId = new Map();
        this.buildNodeMappings();

        // Load preferences from localStorage
        this.loadPreferences();
        this.init();
    }

    init() {
        this.render();
        this.setupEventListeners();
    }

    /**
     * Build mappings between node IDs and tag indices.
     *
     * The challenge is that the structure tree and canvas tags come from
     * different extraction methods:
     * - Structure tree: from PDFStructureExtractor with node_ids
     * - Canvas tags: from PDFTagVisualizer (often without node_ids)
     *
     * We correlate by POSITION: the N-th content node in the tree for this
     * page should match the N-th tag in the canvas tags array.
     */
    buildNodeMappings() {
        this.nodeIdToTagIndex = new Map();
        this.tagIndexToNodeId = new Map();

        // Collect all node_ids from structure tree that appear on this page
        // in reading order (depth-first traversal order)
        const pageNodeIds = [];
        if (this.structureTree) {
            this._collectPageNodeIds(this.structureTree, this.pageNumber - 1, pageNodeIds);
        }

        // Map by position: pageNodeIds[i] corresponds to this.tags[i]
        const minLength = Math.min(pageNodeIds.length, this.tags.length);
        for (let i = 0; i < minLength; i++) {
            const nodeId = pageNodeIds[i];
            this.nodeIdToTagIndex.set(nodeId, i);
            this.tagIndexToNodeId.set(i, nodeId);
        }

    }

    /**
     * Collect node_ids for LEAF nodes on the specified page
     * in depth-first (reading) order.
     *
     * Note: We collect leaf nodes (nodes without children) because these
     * correspond to the actual content elements shown on the canvas.
     * The canvas tags are extracted from PyMuPDF which shows leaf-level
     * structure elements.
     */
    _collectPageNodeIds(node, pageNum, result, stats = null) {
        if (!node) return;

        // Initialize stats on first call
        if (!stats) {
            stats = { pageNumbers: new Set(), leafNodes: 0, totalNodes: 0 };
        }

        stats.totalNodes++;

        // Track all page numbers we see
        if (node.page_number !== null && node.page_number !== undefined) {
            stats.pageNumbers.add(node.page_number);
        }

        const hasChildren = node.children && node.children.length > 0;
        const isOnPage = node.page_number === pageNum;
        const isLeaf = !hasChildren;

        // Collect leaf nodes on the target page
        if (isOnPage && isLeaf && node.node_id) {
            result.push(node.node_id);
            stats.leafNodes++;
        }

        // Recurse into children (maintains reading order)
        if (hasChildren) {
            node.children.forEach(child => this._collectPageNodeIds(child, pageNum, result, stats));
        }

    }

    /**
     * Get tag index for a node ID
     */
    getTagIndexForNodeId(nodeId) {
        if (this.nodeIdToTagIndex.has(nodeId)) {
            return this.nodeIdToTagIndex.get(nodeId);
        }
        return -1;
    }

    /**
     * Get node ID for a tag index
     */
    getNodeIdForTagIndex(tagIndex) {
        if (this.tagIndexToNodeId.has(tagIndex)) {
            return this.tagIndexToNodeId.get(tagIndex);
        }
        return null;
    }

    render() {
        const collapsedClass = this.isCollapsed ? 'collapsed' : '';

        this.container.className = `preview-tree-panel ${collapsedClass}`;
        this.container.innerHTML = `
            <div class="tree-panel-header">
                <h4 class="tree-panel-title">
                    <span class="icon material-icons" style="font-size: 18px;">account_tree</span>
                    <span>Structure</span>
                </h4>
                <button class="tree-collapse-btn" title="${this.isCollapsed ? 'Expand panel' : 'Collapse panel'}" aria-expanded="${!this.isCollapsed}">
                    <span class="icon">${this.isCollapsed ? '&#9654;' : '&#9664;'}</span>
                </button>
            </div>
            <div class="tree-panel-toolbar">
                <button class="tree-toolbar-btn toggle-all-btn" title="Collapse All / Expand All">
                    ${this.isTreeExpanded ? 'Collapse' : 'Expand'}
                </button>
                <label class="tree-toolbar-checkbox" title="Hide generic containers: Span, Div, Document, Part, Artifact, etc.">
                    <input type="checkbox" class="hide-generic-checkbox" ${this.hideGenericTags ? 'checked' : ''}>
                    <span>Hide generic</span>
                </label>
                <label class="tree-toolbar-checkbox" title="Collapse 3+ consecutive identical siblings">
                    <input type="checkbox" class="hide-siblings-checkbox" ${this.hideIdenticalSiblings ? 'checked' : ''}>
                    <span>Hide siblings</span>
                </label>
            </div>
            <div class="tree-panel-content">
                ${this.renderTreeContent()}
            </div>
            <div class="tree-panel-footer">
                <span>Page ${this.pageNumber}</span>
            </div>
        `;

        // Update references
        this.collapseBtn = this.container.querySelector('.tree-collapse-btn');
        this.contentArea = this.container.querySelector('.tree-panel-content');
        this.toggleAllBtn = this.container.querySelector('.toggle-all-btn');
    }

    renderTreeContent() {
        if (!this.structureTree) {
            return this.renderFlatTagList();
        }

        // Filter tree to show only nodes with content on current page
        let filteredTree = this.filterTreeByPage(this.structureTree, this.pageNumber - 1);

        if (!filteredTree) {
            return `
                <div class="tree-empty-state">
                    <span class="icon material-icons" style="font-size: 32px;">description</span>
                    <p>No structure on this page</p>
                </div>
            `;
        }

        // Apply filters
        if (this.hideGenericTags) {
            filteredTree = this.filterOutGenericTags(filteredTree);
        }

        if (!filteredTree) {
            return `
                <div class="tree-empty-state">
                    <span class="icon material-icons" style="font-size: 32px;">filter_alt</span>
                    <p>All tags filtered out</p>
                </div>
            `;
        }

        let html = `<ul class="tree-list" role="tree">${this.renderNode(filteredTree, 0)}</ul>`;

        // Apply identical siblings collapsing after rendering
        // This is handled via CSS/JS after initial render

        return html;
    }

    /**
     * Filter tree to only include nodes with content on the specified page
     */
    filterTreeByPage(node, pageNum) {
        if (!node) return null;

        const isOnPage = node.page_number === pageNum;

        let filteredChildren = [];
        if (node.children && node.children.length > 0) {
            filteredChildren = node.children
                .map(child => this.filterTreeByPage(child, pageNum))
                .filter(child => child !== null);
        }

        if (isOnPage || filteredChildren.length > 0) {
            return {
                ...node,
                children: filteredChildren,
                _isOnPage: isOnPage
            };
        }

        return null;
    }

    /**
     * Filter out generic tags, promoting their children up the tree.
     * Generic tags are "unwrapped" - removed but their children remain.
     */
    filterOutGenericTags(node, isRoot = true) {
        if (!node) return null;

        // Recursively process and collect children
        // For generic children, we promote their children up
        let newChildren = [];
        if (node.children && node.children.length > 0) {
            for (const child of node.children) {
                const promoted = this._collectNonGenericDescendants(child);
                newChildren.push(...promoted);
            }
        }

        // If THIS node is generic (not the root), it should have been
        // handled by the parent. But if it's the root and generic,
        // we need to return a virtual wrapper or the first child.
        if (PREVIEW_GENERIC_TAGS.includes(node.tag_type)) {
            if (isRoot) {
                // Root is generic - return a wrapper with promoted children
                // or if there's only one child, return that child as new root
                if (newChildren.length === 1) {
                    return newChildren[0];
                } else if (newChildren.length > 1) {
                    // Keep the generic root but with promoted children
                    return { ...node, children: newChildren };
                }
                return null;
            }
            // Non-root generic nodes are handled by parent's _collectNonGenericDescendants
            return null;
        }

        // Non-generic node - keep it with its processed children
        return { ...node, children: newChildren };
    }

    /**
     * Recursively collect non-generic nodes, promoting through generic ancestors.
     * Returns an array of nodes (possibly empty).
     */
    _collectNonGenericDescendants(node) {
        if (!node) return [];

        const isGeneric = PREVIEW_GENERIC_TAGS.includes(node.tag_type);

        if (isGeneric) {
            // This node is generic - skip it but collect its children's descendants
            let results = [];
            if (node.children && node.children.length > 0) {
                for (const child of node.children) {
                    results.push(...this._collectNonGenericDescendants(child));
                }
            }
            return results;
        } else {
            // This node is NOT generic - keep it, but filter its children
            let newChildren = [];
            if (node.children && node.children.length > 0) {
                for (const child of node.children) {
                    newChildren.push(...this._collectNonGenericDescendants(child));
                }
            }
            return [{ ...node, children: newChildren }];
        }
    }

    /**
     * Render a tree node and its children recursively
     */
    renderNode(node, depth) {
        if (!node || depth > 15) return '';

        const hasChildren = node.children && node.children.length > 0;
        const isSelected = node.node_id === this.selectedNodeId;
        const shouldExpand = this.isTreeExpanded && (this.expandedNodes.size === 0 || this.expandedNodes.has(node.node_id));
        const isExpanded = shouldExpand || depth < 2;
        const isOnPage = node._isOnPage;
        const tagIndex = this.getTagIndexForNodeId(node.node_id);
        const hasBbox = tagIndex !== undefined && tagIndex >= 0;

        // Build CSS classes
        let nodeClasses = ['tree-node'];
        if (isSelected) nodeClasses.push('selected');
        if (!hasBbox) nodeClasses.push('no-bbox');
        if (isOnPage) nodeClasses.push('on-page');

        // Text preview
        let textPreview = '';
        if (node.text_content) {
            const preview = node.text_content.length > 35
                ? node.text_content.substring(0, 35) + '...'
                : node.text_content;
            textPreview = `<span class="tree-text-preview">"${this.escapeHtml(preview)}"</span>`;
        }

        // Heading preview (bold)
        if (node.is_heading && node.text_content) {
            const preview = node.text_content.length > 30
                ? node.text_content.substring(0, 30) + '...'
                : node.text_content;
            textPreview = `<span class="tree-heading-preview">${this.escapeHtml(preview)}</span>`;
        }

        // Alt text indicator
        let altIndicator = '';
        if (node.alt_text) {
            altIndicator = '<span class="tree-alt-indicator" title="Has alt text">✓</span>';
        }

        // Issue indicator
        let issueIndicator = '';
        if (node.has_issues) {
            issueIndicator = '<span class="tree-issue-indicator" title="Has issues">⚠</span>';
        }

        // Process children for identical sibling collapsing
        let childrenHtml = '';
        if (hasChildren) {
            if (this.hideIdenticalSiblings) {
                childrenHtml = this.renderChildrenWithSiblingCollapse(node.children, depth + 1);
            } else {
                childrenHtml = node.children.map(child => this.renderNode(child, depth + 1)).join('');
            }
        }

        // Build node HTML
        let html = '<li class="tree-item">';

        if (hasChildren) {
            html += `
                <details ${isExpanded ? 'open' : ''} data-node-id="${node.node_id}">
                    <summary class="${nodeClasses.join(' ')}"
                             data-node-id="${node.node_id}"
                             data-tag-index="${tagIndex >= 0 ? tagIndex : ''}"
                             role="treeitem"
                             aria-selected="${isSelected}">
                        <span class="tree-tag-label tag-${node.tag_type}">${this.escapeHtml(node.tag_type)}</span>
                        ${textPreview}
                        ${altIndicator}
                        ${issueIndicator}
                    </summary>
                    <ul class="tree-children" role="group">
                        ${childrenHtml}
                    </ul>
                </details>
            `;
        } else {
            html += `
                <div class="${nodeClasses.join(' ')}"
                     data-node-id="${node.node_id}"
                     data-tag-index="${tagIndex >= 0 ? tagIndex : ''}"
                     role="treeitem"
                     aria-selected="${isSelected}">
                    <span class="tree-toggle-placeholder"></span>
                    <span class="tree-tag-label tag-${node.tag_type}">${this.escapeHtml(node.tag_type)}</span>
                    ${textPreview}
                    ${altIndicator}
                    ${issueIndicator}
                </div>
            `;
        }

        html += '</li>';
        return html;
    }

    /**
     * Render children with identical sibling collapsing
     */
    renderChildrenWithSiblingCollapse(children, depth) {
        let html = '';
        let i = 0;

        while (i < children.length) {
            const current = children[i];
            const currentType = current.tag_type;

            // Find consecutive siblings of the same type
            let consecutiveCount = 1;
            while (i + consecutiveCount < children.length &&
                   children[i + consecutiveCount].tag_type === currentType) {
                consecutiveCount++;
            }

            if (consecutiveCount >= 3) {
                // Render first sibling
                html += this.renderNode(current, depth);

                // Add "show more" toggle for the rest
                const hiddenCount = consecutiveCount - 1;
                html += `
                    <li class="tree-item sibling-group">
                        <button class="sibling-toggle" data-count="${hiddenCount}" data-tag-type="${currentType}">
                            Show ${hiddenCount} more ${currentType} siblings
                        </button>
                        <ul class="hidden-siblings" hidden>
                            ${children.slice(i + 1, i + consecutiveCount).map(child => this.renderNode(child, depth)).join('')}
                        </ul>
                    </li>
                `;
                i += consecutiveCount;
            } else {
                // Render normally
                html += this.renderNode(current, depth);
                i++;
            }
        }

        return html;
    }

    /**
     * Fallback: render flat tag list
     */
    renderFlatTagList() {
        if (this.tags.length === 0) {
            return `
                <div class="tree-empty-state">
                    <span class="icon material-icons" style="font-size: 32px;">description</span>
                    <p>No structure tags on this page</p>
                </div>
            `;
        }

        let html = '<ul class="tree-list tree-flat" role="tree">';

        for (let i = 0; i < this.tags.length; i++) {
            const tag = this.tags[i];
            const isSelected = i === this.selectedTagIndex;

            let textPreview = '';
            if (tag.text_preview) {
                const preview = tag.text_preview.length > 35
                    ? tag.text_preview.substring(0, 35) + '...'
                    : tag.text_preview;
                textPreview = `<span class="tree-text-preview">"${this.escapeHtml(preview)}"</span>`;
            }

            html += `
                <li class="tree-item">
                    <div class="tree-node ${isSelected ? 'selected' : ''}"
                         data-tag-index="${i}"
                         data-node-id="${this.getNodeIdForTagIndex(i) || ''}"
                         role="treeitem"
                         aria-selected="${isSelected}">
                        <span class="tree-reading-order">${tag.reading_order}</span>
                        <span class="tree-tag-label tag-${tag.tag_type}">${tag.tag_type}</span>
                        ${textPreview}
                    </div>
                </li>
            `;
        }

        html += '</ul>';
        return html;
    }

    setupEventListeners() {
        // Panel collapse toggle
        this.container.addEventListener('click', (e) => {
            const collapseBtn = e.target.closest('.tree-collapse-btn');
            if (collapseBtn) {
                this.toggleCollapsed();
                return;
            }

            // Toggle All button
            const toggleAllBtn = e.target.closest('.toggle-all-btn');
            if (toggleAllBtn) {
                this.toggleAllNodes();
                return;
            }

            // Sibling toggle
            const siblingToggle = e.target.closest('.sibling-toggle');
            if (siblingToggle) {
                this.handleSiblingToggle(siblingToggle);
                return;
            }

            // Node click (with Cmd/Ctrl modifier check)
            const node = e.target.closest('.tree-node');
            if (node) {
                const nodeId = node.dataset.nodeId;
                const tagIndex = node.dataset.tagIndex;

                // Check for Cmd/Ctrl+click to expand/collapse children
                if ((e.metaKey || e.ctrlKey) && nodeId) {
                    e.preventDefault();
                    this.toggleNodeChildren(nodeId);
                    return;
                }

                // Normal click - select node
                if (tagIndex !== '' && tagIndex !== undefined) {
                    this.handleNodeClick(parseInt(tagIndex, 10), nodeId);
                }
            }
        });

        // Checkbox changes
        this.container.addEventListener('change', (e) => {
            if (e.target.classList.contains('hide-generic-checkbox')) {
                this.hideGenericTags = e.target.checked;
                this.savePreferences();
                this.refreshTree();
            } else if (e.target.classList.contains('hide-siblings-checkbox')) {
                this.hideIdenticalSiblings = e.target.checked;
                this.savePreferences();
                this.refreshTree();
            }
        });

        // Track expanded/collapsed state
        this.container.addEventListener('toggle', (e) => {
            if (e.target.tagName === 'DETAILS') {
                const nodeId = e.target.dataset.nodeId;
                if (nodeId) {
                    if (e.target.open) {
                        this.expandedNodes.add(nodeId);
                    } else {
                        this.expandedNodes.delete(nodeId);
                    }
                }
            }
        }, true);

        // Hover events
        this.container.addEventListener('mouseenter', (e) => {
            const node = e.target.closest('.tree-node');
            if (node && !node.classList.contains('no-bbox') && this.options.onNodeHover) {
                const tagIndex = node.dataset.tagIndex;
                if (tagIndex !== '' && tagIndex !== undefined) {
                    this.options.onNodeHover(parseInt(tagIndex, 10));
                }
            }
        }, true);

        this.container.addEventListener('mouseleave', (e) => {
            const node = e.target.closest('.tree-node');
            if (node && this.options.onNodeHover) {
                this.options.onNodeHover(-1);
            }
        }, true);

        // Keyboard navigation
        this.container.addEventListener('keydown', (e) => {
            this.handleKeyDown(e);
        });
    }

    /**
     * Toggle all nodes expanded/collapsed
     */
    toggleAllNodes() {
        this.isTreeExpanded = !this.isTreeExpanded;

        const details = this.container.querySelectorAll('details');
        details.forEach(d => {
            d.open = this.isTreeExpanded;
        });

        // Update button text
        if (this.toggleAllBtn) {
            this.toggleAllBtn.textContent = this.isTreeExpanded ? 'Collapse' : 'Expand';
        }
    }

    /**
     * Toggle all children of a specific node (Cmd/Ctrl+Click)
     */
    toggleNodeChildren(nodeId) {
        const parentDetails = this.container.querySelector(`details[data-node-id="${nodeId}"]`);
        if (!parentDetails) return;

        // Get all descendant details
        const childDetails = parentDetails.querySelectorAll('details');
        if (childDetails.length === 0) return;

        // Check if any child is open
        const anyChildOpen = Array.from(childDetails).some(d => d.open);
        const shouldOpen = !anyChildOpen;

        // Toggle all descendants
        childDetails.forEach(d => d.open = shouldOpen);

        // Keep parent open so user sees the effect
        parentDetails.open = true;
    }

    /**
     * Handle sibling toggle click
     */
    handleSiblingToggle(button) {
        const siblingGroup = button.closest('.sibling-group');
        const hiddenSiblings = siblingGroup.querySelector('.hidden-siblings');
        const count = button.dataset.count;
        const tagType = button.dataset.tagType;

        if (hiddenSiblings.hidden) {
            hiddenSiblings.hidden = false;
            button.textContent = `Hide ${count} ${tagType} siblings`;
        } else {
            hiddenSiblings.hidden = true;
            button.textContent = `Show ${count} more ${tagType} siblings`;
        }
    }

    handleNodeClick(tagIndex, nodeId) {
        this.selectedTagIndex = tagIndex;
        this.selectedNodeId = nodeId;

        this.updateSelectionVisual();

        if (this.options.onNodeSelect) {
            this.options.onNodeSelect(tagIndex, nodeId, 'tree');
        }
    }

    updateSelectionVisual() {
        // Remove selection from all previously selected nodes
        const prevSelected = this.container.querySelectorAll('.tree-node.selected');
        prevSelected.forEach(node => {
            node.classList.remove('selected', 'highlight-flash');
            node.setAttribute('aria-selected', 'false');
        });

        if (this.selectedNodeId) {
            const node = this.container.querySelector(`.tree-node[data-node-id="${this.selectedNodeId}"]`);
            if (node) {
                node.classList.add('selected');
                node.setAttribute('aria-selected', 'true');

                // Add a brief flash effect to make selection more noticeable
                node.classList.add('highlight-flash');
                setTimeout(() => node.classList.remove('highlight-flash'), 600);
            }
        }
    }

    handleKeyDown(e) {
        const focusedNode = this.container.querySelector('.tree-node:focus');
        if (!focusedNode) return;

        switch (e.key) {
            case 'Enter':
            case ' ':
                e.preventDefault();
                const tagIndex = focusedNode.dataset.tagIndex;
                const nodeId = focusedNode.dataset.nodeId;
                if (tagIndex !== '' && tagIndex !== undefined) {
                    this.handleNodeClick(parseInt(tagIndex, 10), nodeId);
                }
                break;
        }
    }

    /**
     * Select a node in the tree (called from canvas sync)
     */
    selectNode(tagIndex, options = {}) {
        const { scrollIntoView = true } = options;

        this.selectedTagIndex = tagIndex;
        this.selectedNodeId = this.getNodeIdForTagIndex(tagIndex);

        if (!this.selectedNodeId) {
            return;
        }

        // FIRST expand the path to make the node visible (before updating visual)
        this.expandPathToNode(this.selectedNodeId);

        // Now update the visual selection
        this.updateSelectionVisual();

        // Scroll into view if requested
        if (scrollIntoView) {
            const node = this.container.querySelector(`.tree-node[data-node-id="${this.selectedNodeId}"]`);
            if (node) {
                this.scrollNodeIntoView(node);
            }
        }
    }

    /**
     * Expand all parent details elements to reveal a node
     */
    expandPathToNode(nodeId) {
        const node = this.container.querySelector(`.tree-node[data-node-id="${nodeId}"]`);
        if (!node) return;

        let parent = node.parentElement;
        while (parent && parent !== this.container) {
            if (parent.tagName === 'DETAILS' && !parent.open) {
                parent.open = true;
                const parentNodeId = parent.dataset.nodeId;
                if (parentNodeId) {
                    this.expandedNodes.add(parentNodeId);
                }
            }
            parent = parent.parentElement;
        }
    }

    deselectNode() {
        this.selectedTagIndex = -1;
        this.selectedNodeId = null;
        this.updateSelectionVisual();
    }

    scrollNodeIntoView(node) {
        if (!this.contentArea || !node) return;

        const nodeRect = node.getBoundingClientRect();
        const contentRect = this.contentArea.getBoundingClientRect();

        if (nodeRect.top < contentRect.top || nodeRect.bottom > contentRect.bottom) {
            node.scrollIntoView({
                behavior: 'smooth',
                block: 'nearest'
            });
        }
    }

    /**
     * Refresh the tree (after filter changes)
     */
    refreshTree() {
        const content = this.container.querySelector('.tree-panel-content');
        if (content) {
            content.innerHTML = this.renderTreeContent();
        }
    }

    /**
     * Update with new page data
     */
    setPage(pageNumber, tags, structureTree = null, readingOrderMap = null) {
        this.pageNumber = pageNumber;
        this.tags = tags;
        if (structureTree) {
            this.structureTree = structureTree;
        }
        if (readingOrderMap) {
            this.readingOrderMap = readingOrderMap;
        }
        this.selectedTagIndex = -1;
        this.selectedNodeId = null;
        this.buildNodeMappings();
        this.render();
        this.setupEventListeners();
    }

    toggleCollapsed() {
        this.isCollapsed = !this.isCollapsed;
        this.container.classList.toggle('collapsed', this.isCollapsed);

        if (this.collapseBtn) {
            this.collapseBtn.title = this.isCollapsed ? 'Expand panel' : 'Collapse panel';
            this.collapseBtn.setAttribute('aria-expanded', !this.isCollapsed);
            const icon = this.collapseBtn.querySelector('.icon');
            if (icon) {
                icon.innerHTML = this.isCollapsed ? '&#9654;' : '&#9664;';
            }
        }

        this.savePreferences();
    }

    savePreferences() {
        try {
            localStorage.setItem('inspekt-preview-tree-prefs', JSON.stringify({
                collapsed: this.isCollapsed,
                hideGenericTags: this.hideGenericTags,
                hideIdenticalSiblings: this.hideIdenticalSiblings
            }));
        } catch (e) {}
    }

    loadPreferences() {
        try {
            const saved = localStorage.getItem('inspekt-preview-tree-prefs');
            if (saved) {
                const prefs = JSON.parse(saved);
                this.isCollapsed = prefs.collapsed || false;
                this.hideGenericTags = prefs.hideGenericTags || false;
                this.hideIdenticalSiblings = prefs.hideIdenticalSiblings || false;
            }
        } catch (e) {}
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    getSelectedTag() {
        if (this.selectedTagIndex >= 0 && this.selectedTagIndex < this.tags.length) {
            return this.tags[this.selectedTagIndex];
        }
        return null;
    }
}

// Export for use as module
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PreviewTreePanel;
}
