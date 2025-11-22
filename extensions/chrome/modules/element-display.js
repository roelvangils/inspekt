/**
 * Element Display Module
 * Renders current element information in the UI
 */

import { evalInPage } from '../utils/devtools.js';
import { handleNavigateParent } from '../handlers/navigate-parent.js';
import { handleNavigateChild } from '../handlers/navigate-child.js';
import { handleNavigatePrevSibling } from '../handlers/navigate-prev-sibling.js';
import { handleNavigateNextSibling } from '../handlers/navigate-next-sibling.js';

export class ElementDisplay {
    constructor(elementHighlighter = null) {
        this.currentElement = null;
        this.inspectedElement = document.getElementById('inspectedElement');
        this.elementHighlighter = elementHighlighter;

        // Note: Action buttons are now managed by QuickActionsManager
        // No longer need to reference them here
    }

    /**
     * Update display with new element
     * @param {Object} element - Element data
     */
    update(element) {
        this.currentElement = element;
        // Note: Button states are now handled by QuickActionsManager.updateElementStates()
        this.renderElementCard(element);
    }

    /**
     * Get current element
     * @returns {Object|null} Current element data
     */
    getCurrentElement() {
        return this.currentElement;
    }

    /**
     * Render element card
     * @param {Object} element - Element data
     */
    renderElementCard(element) {
        const card = document.createElement('div');
        card.className = 'element-card';

        // Tag line
        const tagLine = document.createElement('div');
        tagLine.className = 'element-tag';
        tagLine.textContent = `<${element.tag}>`;
        if (element.id) {
            tagLine.textContent += `#${element.id}`;
        }
        if (element.classes.length > 0) {
            tagLine.textContent += `.${element.classes.slice(0, 2).join('.')}`;
        }
        card.appendChild(tagLine);

        // Info container
        const infoContainer = document.createElement('div');
        infoContainer.className = 'element-info';

        if (element.selector) {
            infoContainer.appendChild(this.createInfoRow('Selector', element.selector));
        }

        if (element.role) {
            infoContainer.appendChild(this.createInfoRow('Role', element.role));
        }

        if (element.accessibleName) {
            infoContainer.appendChild(this.createInfoRow('Accessible Name', element.accessibleName));
        }

        if (element.textContent) {
            const shortText = element.textContent.length > 60
                ? element.textContent.substring(0, 60) + '...'
                : element.textContent;
            infoContainer.appendChild(this.createInfoRow('Text', shortText));
        }

        card.appendChild(infoContainer);

        // Add navigation buttons
        const navContainer = this.createNavigationButtons();
        card.appendChild(navContainer);

        // Update DOM
        this.inspectedElement.innerHTML = '';
        this.inspectedElement.appendChild(card);
    }

    /**
     * Create navigation buttons
     * @returns {HTMLElement} Navigation container
     */
    createNavigationButtons() {
        const container = document.createElement('div');
        container.className = 'element-navigation';

        // Row 1: Parent and Child buttons
        const row1 = document.createElement('div');
        row1.className = 'nav-row';

        const parentBtn = this.createNavButton('parent', 'keyboard_arrow_up', 'Parent');
        const childBtn = this.createNavButton('child', 'keyboard_arrow_down', 'Child');

        row1.appendChild(parentBtn);
        row1.appendChild(childBtn);

        // Row 2: Prev and Next Sibling buttons
        const row2 = document.createElement('div');
        row2.className = 'nav-row';

        const prevBtn = this.createNavButton('prev', 'keyboard_arrow_left', 'Prev');
        const nextBtn = this.createNavButton('next', 'keyboard_arrow_right', 'Next');

        row2.appendChild(prevBtn);
        row2.appendChild(nextBtn);

        container.appendChild(row1);
        container.appendChild(row2);

        // Update button states asynchronously
        this.updateNavigationStates(parentBtn, childBtn, prevBtn, nextBtn);

        return container;
    }

    /**
     * Create a single navigation button
     * @param {string} direction - Direction (parent, child, prev, next)
     * @param {string} icon - Material icon name
     * @param {string} label - Button label
     * @returns {HTMLElement} Button element
     */
    createNavButton(direction, icon, label) {
        const btn = document.createElement('button');
        btn.className = `nav-btn nav-btn-${direction}`;
        btn.setAttribute('data-direction', direction);

        const iconSpan = document.createElement('span');
        iconSpan.className = 'material-icons';
        iconSpan.textContent = icon;

        const labelSpan = document.createElement('span');
        labelSpan.className = 'nav-label';
        labelSpan.id = `navLabel${direction.charAt(0).toUpperCase() + direction.slice(1)}`;
        labelSpan.textContent = label;

        btn.appendChild(iconSpan);
        btn.appendChild(labelSpan);

        // Wire click handler
        btn.addEventListener('click', () => this.handleNavigation(direction));

        return btn;
    }

    /**
     * Handle navigation button click
     * @param {string} direction - Direction to navigate
     */
    handleNavigation(direction) {
        const context = {
            elementDisplay: this,
            elementHighlighter: this.elementHighlighter
        };

        switch (direction) {
            case 'parent':
                handleNavigateParent(context);
                break;
            case 'child':
                handleNavigateChild(context);
                break;
            case 'prev':
                handleNavigatePrevSibling(context);
                break;
            case 'next':
                handleNavigateNextSibling(context);
                break;
        }
    }

    /**
     * Update navigation button states based on DOM availability
     * @param {HTMLElement} parentBtn - Parent button
     * @param {HTMLElement} childBtn - Child button
     * @param {HTMLElement} prevBtn - Previous sibling button
     * @param {HTMLElement} nextBtn - Next sibling button
     */
    updateNavigationStates(parentBtn, childBtn, prevBtn, nextBtn) {
        evalInPage(
            `(function() {
                const el = window.__INSPEKT_INSPECTED_ELEMENT__;
                if (!el) return null;

                const parent = el.parentElement;
                const child = el.firstElementChild;
                const prevSibling = el.previousElementSibling;
                const nextSibling = el.nextElementSibling;

                return {
                    hasParent: parent && parent !== document.body && parent !== document.documentElement,
                    parentTag: parent ? parent.tagName.toLowerCase() : null,
                    hasChild: !!child,
                    childTag: child ? child.tagName.toLowerCase() : null,
                    hasPrev: !!prevSibling,
                    prevTag: prevSibling ? prevSibling.tagName.toLowerCase() : null,
                    hasNext: !!nextSibling,
                    nextTag: nextSibling ? nextSibling.tagName.toLowerCase() : null
                };
            })()`,
            (result) => {
                if (!result) return;

                // Update parent button
                const parentLabel = document.getElementById('navLabelParent');
                if (result.hasParent) {
                    parentBtn.disabled = false;
                    parentBtn.title = `Navigate to parent: <${result.parentTag}>`;
                    if (parentLabel) parentLabel.textContent = `Parent: <${result.parentTag}>`;
                } else {
                    parentBtn.disabled = true;
                    parentBtn.title = 'No parent available';
                    if (parentLabel) parentLabel.textContent = 'No parent';
                }

                // Update child button
                const childLabel = document.getElementById('navLabelChild');
                if (result.hasChild) {
                    childBtn.disabled = false;
                    childBtn.title = `Navigate to child: <${result.childTag}>`;
                    if (childLabel) childLabel.textContent = `Child: <${result.childTag}>`;
                } else {
                    childBtn.disabled = true;
                    childBtn.title = 'No children';
                    if (childLabel) childLabel.textContent = 'No children';
                }

                // Update prev sibling button
                const prevLabel = document.getElementById('navLabelPrev');
                if (result.hasPrev) {
                    prevBtn.disabled = false;
                    prevBtn.title = `Navigate to previous: <${result.prevTag}>`;
                    if (prevLabel) prevLabel.textContent = `Prev: <${result.prevTag}>`;
                } else {
                    prevBtn.disabled = true;
                    prevBtn.title = 'No previous sibling';
                    if (prevLabel) prevLabel.textContent = 'No prev';
                }

                // Update next sibling button
                const nextLabel = document.getElementById('navLabelNext');
                if (result.hasNext) {
                    nextBtn.disabled = false;
                    nextBtn.title = `Navigate to next: <${result.nextTag}>`;
                    if (nextLabel) nextLabel.textContent = `Next: <${result.nextTag}>`;
                } else {
                    nextBtn.disabled = true;
                    nextBtn.title = 'No next sibling';
                    if (nextLabel) nextLabel.textContent = 'No next';
                }
            }
        );
    }

    /**
     * Create info row element
     * @param {string} label - Label text
     * @param {string} value - Value text
     * @returns {HTMLElement} Info row element
     */
    createInfoRow(label, value) {
        const row = document.createElement('div');
        row.className = 'info-row';

        const labelSpan = document.createElement('span');
        labelSpan.className = 'info-label';
        labelSpan.textContent = label + ':';

        const valueSpan = document.createElement('span');
        valueSpan.className = 'info-value';
        valueSpan.textContent = value;

        row.appendChild(labelSpan);
        row.appendChild(valueSpan);

        return row;
    }

    /**
     * Clear display
     */
    clear() {
        this.currentElement = null;
        this.inspectedElement.innerHTML = '<p class="placeholder">No element selected. Right-click an element and select "Inspect".</p>';

        // Note: Button states are now handled by QuickActionsManager.updateElementStates()
    }
}
