/**
 * Structure Tree Interactive Features
 * Provides expand/collapse controls, keyboard modifiers, resizable panel,
 * figure tooltips, and filtering options for the PDF structure tree visualization.
 */

// Generic PDF tags that add noise without semantic meaning
const GENERIC_TAGS = ['Span', 'Div', 'NonStruct', 'Private'];

class StructureTree {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        if (!this.container) {
            console.warn(`StructureTree: Container with id "${containerId}" not found`);
            return;
        }
        this.isExpanded = true;
        this.hideGenericTags = false;
        this.hideIdenticalSiblings = false;

        // Store original tree HTML for re-rendering
        this.treeList = this.container.querySelector(':scope > ul');
        this.originalTreeHTML = this.treeList ? this.treeList.innerHTML : '';

        this.init();
    }

    init() {
        this.loadHeight();
        this.loadPreferences();
        this.initResizeHandle();
        this.initKeyboardModifiers();
        this.initFigureTooltips();
        this.initToggleButton();
        this.initFilterCheckboxes();
        this.initSiblingToggles();
        this.updateGenericTagTooltip();
        this.updateIdenticalSiblingsTooltip();

        // Apply initial filters based on saved preferences
        if (this.hideGenericTags || this.hideIdenticalSiblings) {
            this.applyFilters();
        }
    }

    // Toggle button initialization
    initToggleButton() {
        const btn = this.container.querySelector('.toggle-all-btn');
        if (!btn) return;

        btn.addEventListener('click', () => this.toggleAll());
    }

    // Initialize filter checkboxes
    initFilterCheckboxes() {
        const hideGenericCheckbox = this.container.querySelector('#hide-generic-tags');
        const hideSiblingsCheckbox = this.container.querySelector('#hide-all-identical-siblings');

        if (hideGenericCheckbox) {
            hideGenericCheckbox.checked = this.hideGenericTags;
            hideGenericCheckbox.addEventListener('change', (e) => {
                this.hideGenericTags = e.target.checked;
                this.savePreferences();
                this.applyFilters();
            });
        }

        if (hideSiblingsCheckbox) {
            hideSiblingsCheckbox.checked = this.hideIdenticalSiblings;
            hideSiblingsCheckbox.addEventListener('change', (e) => {
                this.hideIdenticalSiblings = e.target.checked;
                this.savePreferences();
                this.applyFilters();
            });
        }
    }

    // Initialize click handlers for "Show more siblings" links
    initSiblingToggles() {
        this.container.addEventListener('click', (e) => {
            const toggle = e.target.closest('.sibling-toggle');
            if (!toggle) return;

            e.preventDefault();
            const siblingGroup = toggle.closest('.sibling-group');
            if (!siblingGroup) return;

            const hiddenSiblings = Array.from(siblingGroup.querySelectorAll('.hidden-sibling'));
            const isExpanded = toggle.getAttribute('aria-expanded') === 'true';
            const count = hiddenSiblings.length;
            const tagType = toggle.dataset.tagType || 'sibling';

            // Disable button during animation
            toggle.disabled = true;

            if (isExpanded) {
                // Collapsing: fade out from bottom to top, then hide
                const reversed = [...hiddenSiblings].reverse();
                let index = 0;
                const fadeOutNext = () => {
                    if (index < reversed.length) {
                        const sibling = reversed[index];
                        sibling.classList.add('fading-out');
                        index++;
                        setTimeout(fadeOutNext, 15);
                    } else {
                        // After all faded, wait for last transition then hide all
                        setTimeout(() => {
                            reversed.forEach(s => {
                                s.hidden = true;
                                s.classList.remove('fading-out');
                            });
                            toggle.disabled = false;
                        }, 100);
                    }
                };
                fadeOutNext();
            } else {
                // Expanding: show all invisible, then fade in from top to bottom
                hiddenSiblings.forEach(s => {
                    s.hidden = false;
                    s.classList.add('fading-in');
                });

                let index = 0;
                const fadeInNext = () => {
                    if (index < hiddenSiblings.length) {
                        hiddenSiblings[index].classList.add('visible');
                        index++;
                        setTimeout(fadeInNext, 15);
                    } else {
                        // Clean up classes after animation
                        setTimeout(() => {
                            hiddenSiblings.forEach(s => {
                                s.classList.remove('fading-in', 'visible');
                            });
                            toggle.disabled = false;
                        }, 100);
                    }
                };
                fadeInNext();
            }

            toggle.setAttribute('aria-expanded', !isExpanded);
            toggle.textContent = isExpanded
                ? `Show ${count} more ${tagType} siblings`
                : `Hide ${count} ${tagType} siblings`;
        });
    }

    // Apply all active filters
    applyFilters() {
        if (!this.treeList) return;

        // Restore original tree
        this.treeList.innerHTML = this.originalTreeHTML;

        // Apply filters in order
        if (this.hideGenericTags) {
            this.filterGenericTags();
        }

        if (this.hideIdenticalSiblings) {
            this.collapseIdenticalSiblings();
        }

        // Re-initialize tooltips after DOM changes
        this.initFigureTooltips();
    }

    // Filter out generic tags from the tree
    filterGenericTags() {
        GENERIC_TAGS.forEach(tagType => {
            // Find all list items containing generic tags
            const tagElements = this.treeList.querySelectorAll(`.tag-${tagType}`);

            tagElements.forEach(tagEl => {
                const listItem = tagEl.closest('li');
                if (!listItem) return;

                // Check if this is a leaf node (no children) or has children
                const details = listItem.querySelector('details');

                if (details) {
                    // Has children - move children up and remove this node
                    const childrenUl = details.querySelector('ul');
                    if (childrenUl) {
                        // Insert children before this list item
                        const children = Array.from(childrenUl.children);
                        children.forEach(child => {
                            listItem.parentNode.insertBefore(child.cloneNode(true), listItem);
                        });
                    }
                }

                // Remove the generic tag node
                listItem.remove();
            });
        });
    }

    // Collapse identical consecutive siblings
    collapseIdenticalSiblings() {
        const allUls = this.treeList.querySelectorAll('ul');

        // Process each ul including the root
        [this.treeList, ...allUls].forEach(ul => {
            this.processIdenticalSiblings(ul);
        });
    }

    // Process a single ul for identical siblings
    processIdenticalSiblings(ul) {
        const children = Array.from(ul.children).filter(li => !li.classList.contains('more-items'));
        if (children.length <= 1) return;

        // Group consecutive siblings by tag type
        let i = 0;
        while (i < children.length) {
            const currentLi = children[i];
            const currentTag = this.getTagType(currentLi);

            if (!currentTag) {
                i++;
                continue;
            }

            // Find consecutive siblings with the same tag
            const siblings = [currentLi];
            let j = i + 1;

            while (j < children.length) {
                const nextTag = this.getTagType(children[j]);
                if (nextTag === currentTag) {
                    siblings.push(children[j]);
                    j++;
                } else {
                    break;
                }
            }

            // If we have 3 or more identical siblings, collapse them
            if (siblings.length >= 3) {
                this.createSiblingGroup(siblings, currentTag);
            }

            i = j;
        }
    }

    // Get the tag type from a list item
    getTagType(li) {
        const tag = li.querySelector('.tag');
        if (!tag) return null;

        // Extract tag type from class (e.g., "tag tag-P" -> "P")
        const classes = Array.from(tag.classList);
        const tagClass = classes.find(c => c.startsWith('tag-') && c !== 'tag-');
        return tagClass ? tagClass.replace('tag-', '') : null;
    }

    // Create a collapsible group for identical siblings
    createSiblingGroup(siblings, tagType) {
        if (siblings.length < 2) return;

        const firstSibling = siblings[0];
        const parent = firstSibling.parentNode;

        // Create wrapper for the group
        const wrapper = document.createElement('div');
        wrapper.className = 'sibling-group';

        // Keep the first sibling visible
        parent.insertBefore(wrapper, firstSibling);
        wrapper.appendChild(firstSibling);

        // Hide the rest and add to wrapper
        for (let i = 1; i < siblings.length; i++) {
            siblings[i].classList.add('hidden-sibling');
            siblings[i].hidden = true;
            wrapper.appendChild(siblings[i]);
        }

        // Add "Show more" toggle
        const toggleLi = document.createElement('li');
        toggleLi.className = 'sibling-toggle-item';
        toggleLi.innerHTML = `
            <button class="sibling-toggle" aria-expanded="false" data-tag-type="${tagType}">
                Show ${siblings.length - 1} more ${tagType} siblings
            </button>
        `;
        wrapper.appendChild(toggleLi);
    }

    // Count generic tags in the tree
    countGenericTags() {
        let count = 0;
        GENERIC_TAGS.forEach(tagType => {
            const elements = this.treeList?.querySelectorAll(`.tag-${tagType}`) || [];
            count += elements.length;
        });
        return count;
    }

    // Update the tooltip for the generic tags checkbox
    updateGenericTagTooltip() {
        const label = this.container.querySelector('label[for="hide-generic-tags"]');
        if (!label) return;

        const count = this.countGenericTags();
        const tooltipText = count > 0
            ? `Will hide ${count} generic element${count !== 1 ? 's' : ''} to make the tree easier to navigate.`
            : 'No generic elements found in this tree.';

        label.setAttribute('title', tooltipText);
    }

    // Count identical siblings that would be collapsed (3+ consecutive same-type siblings)
    countIdenticalSiblings() {
        if (!this.treeList) return { groups: 0, hiddenCount: 0 };

        let groups = 0;
        let hiddenCount = 0;
        const allUls = [this.treeList, ...this.treeList.querySelectorAll('ul')];

        allUls.forEach(ul => {
            const children = Array.from(ul.children).filter(li =>
                li.tagName === 'LI' && !li.classList.contains('more-items')
            );
            if (children.length <= 1) return;

            let i = 0;
            while (i < children.length) {
                const currentTag = this.getTagType(children[i]);
                if (!currentTag) {
                    i++;
                    continue;
                }

                let consecutiveCount = 1;
                let j = i + 1;
                while (j < children.length && this.getTagType(children[j]) === currentTag) {
                    consecutiveCount++;
                    j++;
                }

                if (consecutiveCount >= 3) {
                    groups++;
                    hiddenCount += consecutiveCount - 1; // First one stays visible
                }
                i = j;
            }
        });

        return { groups, hiddenCount };
    }

    // Update the tooltip for the identical siblings checkbox
    updateIdenticalSiblingsTooltip() {
        const label = this.container.querySelector('label[for="hide-all-identical-siblings"]');
        if (!label) return;

        const { groups, hiddenCount } = this.countIdenticalSiblings();
        let tooltipText;

        if (groups > 0) {
            tooltipText = `Will collapse ${groups} group${groups !== 1 ? 's' : ''} of identical siblings, hiding ${hiddenCount} element${hiddenCount !== 1 ? 's' : ''}. Each group shows only the first element with a "Show more" button.`;
        } else {
            tooltipText = 'No groups of 3 or more identical consecutive siblings found in this tree.';
        }

        label.setAttribute('title', tooltipText);
    }

    // Expand/Collapse All
    expandAll() {
        this.container.querySelectorAll('details').forEach(d => d.open = true);
        this.isExpanded = true;
        this.updateButtonLabel(true);
    }

    collapseAll() {
        this.container.querySelectorAll('details').forEach(d => d.open = false);
        this.isExpanded = false;
        this.updateButtonLabel(false);
    }

    toggleAll() {
        if (this.isExpanded) {
            this.collapseAll();
        } else {
            this.expandAll();
        }
    }

    updateButtonLabel(expanded) {
        const btn = this.container.querySelector('.toggle-all-btn');
        if (!btn) return;
        btn.textContent = expanded ? 'Collapse All' : 'Expand All';
        btn.setAttribute('aria-expanded', expanded);
    }

    // Multi-level toggle via Ctrl/Cmd+click
    initKeyboardModifiers() {
        this.container.addEventListener('click', (e) => {
            const summary = e.target.closest('summary');
            if (!summary) return;

            // Check for Ctrl (Windows/Linux) or Cmd (Mac)
            if (e.ctrlKey || e.metaKey) {
                e.preventDefault();
                const details = summary.closest('details');
                if (!details) return;

                const childDetails = details.querySelectorAll('details');
                if (childDetails.length === 0) return; // No children to toggle

                // Check if any child is open to determine action
                const anyChildOpen = Array.from(childDetails).some(d => d.open);
                const shouldOpen = !anyChildOpen;

                // Toggle all descendant details, but keep clicked node open
                childDetails.forEach(d => d.open = shouldOpen);
                details.open = true; // Always keep clicked node open so user sees the effect
            }
        });
    }

    // Vertical resize handle
    initResizeHandle() {
        const handle = this.container.querySelector('.resize-handle');
        if (!handle) return;

        let startY, startHeight;

        const onMouseDown = (e) => {
            e.preventDefault();
            startY = e.clientY;
            startHeight = this.container.offsetHeight;
            document.body.style.cursor = 'ns-resize';
            document.body.style.userSelect = 'none';

            document.addEventListener('mousemove', onDrag);
            document.addEventListener('mouseup', onRelease);
        };

        const onDrag = (e) => {
            const delta = e.clientY - startY;
            const newHeight = Math.max(200, Math.min(800, startHeight + delta));
            this.container.style.height = newHeight + 'px';
        };

        const onRelease = () => {
            document.removeEventListener('mousemove', onDrag);
            document.removeEventListener('mouseup', onRelease);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            this.saveHeight(this.container.offsetHeight);
        };

        handle.addEventListener('mousedown', onMouseDown);

        // Keyboard accessibility for resize handle
        handle.setAttribute('tabindex', '0');
        handle.setAttribute('role', 'separator');
        handle.setAttribute('aria-orientation', 'horizontal');
        handle.setAttribute('aria-valuenow', this.container.offsetHeight);
        handle.setAttribute('aria-valuemin', '200');
        handle.setAttribute('aria-valuemax', '800');
        handle.setAttribute('aria-label', 'Resize structure tree panel');

        handle.addEventListener('keydown', (e) => {
            const step = e.shiftKey ? 50 : 10;
            let newHeight = this.container.offsetHeight;

            switch (e.key) {
                case 'ArrowUp':
                    e.preventDefault();
                    newHeight = Math.max(200, newHeight - step);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    newHeight = Math.min(800, newHeight + step);
                    break;
                case 'Home':
                    e.preventDefault();
                    newHeight = 200;
                    break;
                case 'End':
                    e.preventDefault();
                    newHeight = 800;
                    break;
                default:
                    return;
            }

            this.container.style.height = newHeight + 'px';
            handle.setAttribute('aria-valuenow', newHeight);
            this.saveHeight(newHeight);
        });
    }

    saveHeight(height) {
        try {
            localStorage.setItem('inspekt-structure-tree-height', height);
        } catch (e) {
            // localStorage may not be available
        }
    }

    loadHeight() {
        try {
            const saved = localStorage.getItem('inspekt-structure-tree-height');
            if (saved) {
                const height = parseInt(saved, 10);
                if (height >= 200 && height <= 800) {
                    this.container.style.height = height + 'px';
                }
            }
        } catch (e) {
            // localStorage may not be available
        }
    }

    savePreferences() {
        try {
            localStorage.setItem('inspekt-structure-tree-prefs', JSON.stringify({
                hideGenericTags: this.hideGenericTags,
                hideIdenticalSiblings: this.hideIdenticalSiblings
            }));
        } catch (e) {
            // localStorage may not be available
        }
    }

    loadPreferences() {
        try {
            const saved = localStorage.getItem('inspekt-structure-tree-prefs');
            if (saved) {
                const prefs = JSON.parse(saved);
                this.hideGenericTags = prefs.hideGenericTags || false;
                this.hideIdenticalSiblings = prefs.hideIdenticalSiblings || false;
            }
        } catch (e) {
            // localStorage may not be available or invalid JSON
        }
    }

    // Figure tooltip with image preview
    initFigureTooltips() {
        const tooltip = document.getElementById('structure-figure-tooltip');
        if (!tooltip) return;

        const figureElements = this.container.querySelectorAll('.tag-Figure[data-thumbnail]');

        figureElements.forEach(el => {
            // Remove existing listeners by cloning
            const newEl = el.cloneNode(true);
            el.parentNode.replaceChild(newEl, el);

            newEl.addEventListener('mouseenter', (e) => {
                const thumb = newEl.dataset.thumbnail;
                if (!thumb) return;

                tooltip.innerHTML = `<img src="data:image/png;base64,${thumb}" alt="Figure preview">`;
                tooltip.hidden = false;
                this.positionTooltip(tooltip, e.target);
            });

            newEl.addEventListener('mouseleave', () => {
                tooltip.hidden = true;
            });

            newEl.addEventListener('focus', (e) => {
                const thumb = newEl.dataset.thumbnail;
                if (!thumb) return;

                tooltip.innerHTML = `<img src="data:image/png;base64,${thumb}" alt="Figure preview">`;
                tooltip.hidden = false;
                this.positionTooltip(tooltip, e.target);
            });

            newEl.addEventListener('blur', () => {
                tooltip.hidden = true;
            });

            // Make focusable for keyboard users
            if (newEl.dataset.thumbnail) {
                newEl.setAttribute('tabindex', '0');
                newEl.setAttribute('role', 'img');
                newEl.setAttribute('aria-label', 'Figure with preview available');
            }
        });
    }

    positionTooltip(tooltip, target) {
        const rect = target.getBoundingClientRect();
        const tooltipWidth = 240;

        // Position to the right of the element by default
        let left = rect.right + 8;
        let top = rect.top;

        // If tooltip would go off the right edge, position to the left
        if (left + tooltipWidth > window.innerWidth) {
            left = rect.left - tooltipWidth - 8;
        }

        // If tooltip would go off the left edge, center it below
        if (left < 8) {
            left = Math.max(8, rect.left);
            top = rect.bottom + 8;
        }

        // Keep within vertical viewport
        const tooltipHeight = tooltip.offsetHeight || 150;
        if (top + tooltipHeight > window.innerHeight) {
            top = window.innerHeight - tooltipHeight - 8;
        }
        if (top < 8) {
            top = 8;
        }

        tooltip.style.left = left + 'px';
        tooltip.style.top = top + 'px';
    }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    // Look for structure tree containers
    const container = document.getElementById('structure-tree-panel');
    if (container) {
        window.structureTree = new StructureTree('structure-tree-panel');
    }
});

// Export for use as module
if (typeof module !== 'undefined' && module.exports) {
    module.exports = StructureTree;
}
