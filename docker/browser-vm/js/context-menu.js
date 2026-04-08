/**
 * Context Menu System — Generic, reusable, supports submenus.
 *
 * Creates macOS-style context menus with:
 * - Recursive submenus (max 2 levels deep)
 * - Triangle safe zone for diagonal mouse movement (Apple 1986 invention)
 * - Focus-based selection (single source of truth for mouse + keyboard)
 * - macOS selection flicker animation
 * - Scroll arrows for overflow
 * - Section headers, checkboxes, separators, navigation icon rows
 * - Full ARIA support (role="menu", menuitem, menuitemcheckbox, etc.)
 * - Platform-specific styling via CSS custom properties (--menu-*)
 *
 * Globals this module reads:
 *   _lastMouseX, _lastMouseY — mouse position (from control-panel.html)
 *   _platform — 'macos' | 'windows' | 'other' (from <head> script)
 *
 * Globals this module exposes:
 *   showContextMenu(e, items) — open a context menu at event coordinates
 *   dismissContextMenu() — close all menus
 *   _isMenuOpen() — check if any menu is open
 *   _activeMenu() — get the deepest open menu element
 *   handleMenuKeydown(e) — keyboard handler (attached by showContextMenu)
 *   _DEBUG_TRIANGLE — set to true to visualize triangle safe zone
 *   _DEBUG_DUMMY_MENU — set to true to show test menu on VNC right-click
 */

// =============================================
// State
// =============================================

// Menu stack: array of { el, parentItem, lastIdx, safeZoneActive, anchorX, anchorY }
// Index 0 is the root menu, subsequent entries are submenus.
let _menuStack = [];
let _submenuTimer = null;

// The "active" menu is always the deepest open one.
function _activeMenu() { return _menuStack.length ? _menuStack[_menuStack.length - 1].el : null; }

// Check if any context menu is open (used by capture-phase handlers in control-panel.html).
function _isMenuOpen() { return _menuStack.length > 0; }

function _menuStackEntry(menuEl) {
    return _menuStack.find(e => e.el === menuEl) || { lastIdx: -1 };
}

// =============================================
// Debug flags
// =============================================

// _DEBUG_TRIANGLE: visualize the safe zone as a colored SVG overlay (green = inside, red = outside)
// _DEBUG_DUMMY_MENU: replace the real VNC context menu with a dummy test menu for submenu testing
const _DEBUG_TRIANGLE = false;
const _DEBUG_DUMMY_MENU = false;
let _debugTriangleEl = null;

// =============================================
// Scroll constraint (for menus taller than viewport)
// =============================================

function _applyMenuScrollConstraint(menuEl, topY) {
    const VIEWPORT_MARGIN = 20;
    const scrollEl = menuEl._scrollContainer;
    if (!scrollEl) return;
    const maxHeight = window.innerHeight - topY - VIEWPORT_MARGIN;
    const arrowHeight = 24;
    const naturalHeight = scrollEl.scrollHeight;
    if (naturalHeight > maxHeight) {
        scrollEl.style.maxHeight = (maxHeight - arrowHeight * 2) + 'px';
        scrollEl.style.overflowY = 'hidden';
    }
    if (menuEl._updateScrollArrows) menuEl._updateScrollArrows();
}

// =============================================
// Triangle safe zone
// =============================================

// Test if point (px, py) is inside the triangle (ax,ay)-(bx,by)-(cx,cy).
// Uses cross-product sign test — no trig, no sqrt.
function _pointInTriangle(px, py, ax, ay, bx, by, cx, cy) {
    const d1 = (px - bx) * (ay - by) - (ax - bx) * (py - by);
    const d2 = (px - cx) * (by - cy) - (bx - cx) * (py - cy);
    const d3 = (px - ax) * (cy - ay) - (cx - ax) * (py - ay);
    return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
}

function _debugDrawTriangle(ax, ay, bx, by, cx, cy, isInside) {
    if (!_DEBUG_TRIANGLE) return;
    if (!_debugTriangleEl) {
        _debugTriangleEl = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        _debugTriangleEl.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        _debugTriangleEl.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;pointer-events:none;z-index:999999;';
        document.body.appendChild(_debugTriangleEl);
    }
    const fill = isInside ? 'rgba(0,200,0,0.25)' : 'rgba(200,0,0,0.2)';
    const stroke = isInside ? 'rgba(0,255,0,0.8)' : 'rgba(255,0,0,0.6)';
    _debugTriangleEl.innerHTML = `<polygon points="${ax},${ay} ${bx},${by} ${cx},${cy}" fill="${fill}" stroke="${stroke}" stroke-width="2"/>`;
}

function _debugClearTriangle() {
    if (_debugTriangleEl) _debugTriangleEl.innerHTML = '';
}

// Check if the cursor is inside the safe triangle toward an open submenu.
//
// The triangle fans from the mouse position at the moment the submenu opened
// (a fixed snapshot) to the submenu's near-side top and bottom corners.
// The cursor is tested against this fixed triangle on every call.
//
// macOS behavior: the safe zone is cancelled when the cursor returns from the
// submenu back to the parent menu. The `safeZoneActive` flag on each stack entry
// tracks this — set to false on submenu mouseleave, true on submenu mouseenter.
function _isInSubmenuSafeZone(parentMenuEl) {
    const parentIdx = _menuStack.findIndex(e => e.el === parentMenuEl);
    if (parentIdx < 0 || parentIdx >= _menuStack.length - 1) {
        _debugClearTriangle();
        return false;
    }

    const submenuEntry = _menuStack[parentIdx + 1];
    // macOS cancellation: if the user already visited the submenu and came back,
    // the safe zone is disabled until they re-enter the submenu.
    if (!submenuEntry.safeZoneActive) {
        _debugClearTriangle();
        return false;
    }

    const submenuRect = submenuEntry.el.getBoundingClientRect();
    const parentRect = parentMenuEl.getBoundingClientRect();

    // Determine if submenu is to the right or left of parent by comparing
    // the submenu's right edge against the parent's right edge.
    const submenuIsRight = submenuRect.right > parentRect.right;

    // The triangle fans from the mouse position at the moment the submenu
    // opened (fixed snapshot) toward the submenu's near-side corners.
    // This anchor doesn't move — the cursor is tested against this fixed triangle.
    const nearX = submenuIsRight ? submenuRect.left : submenuRect.right;
    const anchorX = submenuEntry.anchorX;
    const anchorY = submenuEntry.anchorY;

    const inside = _pointInTriangle(
        _lastMouseX, _lastMouseY,
        anchorX, anchorY,
        nearX, submenuRect.top,
        nearX, submenuRect.bottom
    );

    _debugDrawTriangle(anchorX, anchorY, nearX, submenuRect.top, nearX, submenuRect.bottom, inside);

    return inside;
}

// =============================================
// Submenu timer
// =============================================

function _clearSubmenuTimer() {
    if (_submenuTimer) { clearTimeout(_submenuTimer); _submenuTimer = null; }
}

// =============================================
// Item queries
// =============================================

// Query enabled items scoped to a specific menu element (not its submenus).
// Items live inside .context-menu-scroll, which is a direct child of .context-menu.
function _getMenuItemsOf(menuEl) {
    if (!menuEl) return [];
    const scroll = menuEl.querySelector(':scope > .context-menu-scroll');
    if (!scroll) return [];
    return Array.from(scroll.querySelectorAll(
        ':scope > [role="menuitem"]:not([aria-disabled="true"]), :scope > [role="menuitemcheckbox"]:not([aria-disabled="true"]), :scope > .context-menu-nav [role="menuitem"]:not([aria-disabled="true"])'
    ));
}

// =============================================
// Scroll lock
// =============================================

let _menuScrollLock = null;
function _lockScroll() {
    _menuScrollLock = (e) => { e.preventDefault(); };
    document.addEventListener('wheel', _menuScrollLock, { passive: false });
    document.addEventListener('touchmove', _menuScrollLock, { passive: false });
}
function _unlockScroll() {
    if (_menuScrollLock) {
        document.removeEventListener('wheel', _menuScrollLock);
        document.removeEventListener('touchmove', _menuScrollLock);
        _menuScrollLock = null;
    }
}

// =============================================
// macOS flicker animation
// =============================================

// macOS: flicker the item highlight before dismissing, matching native behavior.
// Guards against stale timeouts by checking the root menu hasn't changed.
function _flickerAndDismiss(btn, action) {
    if (_platform === 'macos') {
        const rootMenu = _menuStack.length > 0 ? _menuStack[0].el : null;
        btn.classList.add('flickering');
        setTimeout(() => {
            if (_menuStack.length > 0 && _menuStack[0].el === rootMenu) dismissContextMenu();
            action();
        }, 160);
    } else {
        dismissContextMenu();
        action();
    }
}

// =============================================
// Build menu DOM from items array
// =============================================

function _buildMenuElement(items, ariaLabel) {
    const menu = document.createElement('div');
    menu.className = 'context-menu';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', ariaLabel || 'Context menu');
    menu.tabIndex = -1;

    // Suppress native context menu inside our menu
    menu.addEventListener('contextmenu', ev => ev.preventDefault());

    // Scroll arrows for overflow — shown only when menu exceeds viewport
    const scrollUp = document.createElement('div');
    scrollUp.className = 'context-menu-scroll-arrow up';
    scrollUp.setAttribute('aria-hidden', 'true');
    scrollUp.textContent = '\u25B2'; // ▲
    menu.appendChild(scrollUp);

    const scrollContainer = document.createElement('div');
    scrollContainer.className = 'context-menu-scroll';
    menu.appendChild(scrollContainer);

    items.forEach(item => {
        if (item.hidden) return;

        if (item.separator) {
            const sep = document.createElement('div');
            sep.setAttribute('role', 'separator');
            scrollContainer.appendChild(sep);
            return;
        }

        // Section header — non-interactive dimmed label for grouping
        if (item.header) {
            const hdr = document.createElement('div');
            hdr.className = 'context-menu-header';
            hdr.setAttribute('role', 'presentation');
            hdr.textContent = item.header;
            scrollContainer.appendChild(hdr);
            return;
        }

        // Navigation icon row (Back / Forward / Reload)
        if (item.navRow) {
            const row = document.createElement('div');
            row.className = 'context-menu-nav';
            row.setAttribute('role', 'group');
            item.navRow.forEach(nav => {
                const btn = document.createElement('button');
                btn.setAttribute('role', 'menuitem');
                const tpl = document.createElement('template');
                tpl.innerHTML = nav.icon;
                btn.appendChild(tpl.content.firstChild);
                btn.setAttribute('aria-label', nav.label);
                btn.title = nav.label;
                btn.tabIndex = -1;
                if (nav.disabled) btn.setAttribute('aria-disabled', 'true');
                btn.onclick = () => {
                    if (nav.disabled) return;
                    _flickerAndDismiss(btn, nav.action);
                };
                row.appendChild(btn);
            });
            scrollContainer.appendChild(row);
            return;
        }

        // Checkbox item (toggle, does NOT dismiss menu)
        if (item.checkbox) {
            const btn = document.createElement('button');
            btn.setAttribute('role', 'menuitemcheckbox');
            btn.setAttribute('aria-checked', item.checked ? 'true' : 'false');
            btn.tabIndex = -1;

            const checkIcon = document.createElement('span');
            checkIcon.className = 'check-icon';
            const checkSvg = '<svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 5l2.5 2.5L8 3" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>';
            checkIcon.innerHTML = item.checked ? checkSvg : '';
            btn.appendChild(checkIcon);

            const label = document.createElement('span');
            label.textContent = item.label;
            btn.appendChild(label);

            btn.onclick = (ev) => {
                ev.stopPropagation();
                const newState = btn.getAttribute('aria-checked') !== 'true';
                btn.setAttribute('aria-checked', newState ? 'true' : 'false');
                checkIcon.innerHTML = newState ? checkSvg : '';
                if (item.onToggle) item.onToggle(newState);
            };
            scrollContainer.appendChild(btn);
            return;
        }

        // Regular item or submenu parent
        const btn = document.createElement('button');
        btn.setAttribute('role', 'menuitem');
        btn.tabIndex = -1;

        if (item.children && item.children.length > 0) {
            // Submenu parent: label + chevron, no action
            const labelSpan = document.createElement('span');
            labelSpan.textContent = item.label;
            labelSpan.style.flex = '1';
            btn.appendChild(labelSpan);
            const chevron = document.createElement('span');
            chevron.className = 'submenu-chevron';
            chevron.textContent = String.fromCodePoint(0x100BFB); // SF Symbols chevron.forward
            btn.appendChild(chevron);
            btn.setAttribute('aria-haspopup', 'menu');
            btn.setAttribute('aria-expanded', 'false');
            if (item.disabled) {
                btn.setAttribute('aria-disabled', 'true');
            } else {
                btn._submenuChildren = item.children;
            }
            // No onclick — submenus open via hover/keyboard, not click
        } else {
            btn.textContent = item.label;
            if (item.title) btn.title = item.title;
            if (item.disabled) {
                btn.setAttribute('aria-disabled', 'true');
            } else {
                btn.onclick = () => _flickerAndDismiss(btn, item.action);
            }
        }

        scrollContainer.appendChild(btn);
    });

    // Scroll-down arrow
    const scrollDown = document.createElement('div');
    scrollDown.className = 'context-menu-scroll-arrow down';
    scrollDown.setAttribute('aria-hidden', 'true');
    scrollDown.textContent = '\u25BC'; // ▼
    menu.appendChild(scrollDown);

    // Scroll arrow hover logic — scroll when hovering arrows
    let _scrollInterval = null;
    function _startScroll(direction) {
        _stopScroll();
        _scrollInterval = setInterval(() => {
            scrollContainer.scrollTop += direction * 4;
            _updateScrollArrows();
        }, 16); // ~60fps
    }
    function _stopScroll() {
        if (_scrollInterval) { clearInterval(_scrollInterval); _scrollInterval = null; }
    }
    function _updateScrollArrows() {
        const canScrollUp = scrollContainer.scrollTop > 0;
        const canScrollDown = scrollContainer.scrollTop < scrollContainer.scrollHeight - scrollContainer.clientHeight - 1;
        scrollUp.classList.toggle('visible', canScrollUp);
        scrollDown.classList.toggle('visible', canScrollDown);
    }

    scrollUp.addEventListener('mouseenter', () => _startScroll(-1));
    scrollUp.addEventListener('mouseleave', _stopScroll);
    scrollDown.addEventListener('mouseenter', () => _startScroll(1));
    scrollDown.addEventListener('mouseleave', _stopScroll);

    // Store references for post-positioning scroll check
    menu._scrollContainer = scrollContainer;
    menu._updateScrollArrows = _updateScrollArrows;

    return menu;
}

// =============================================
// Wire mouse events on menu items
// =============================================

function _wireMenuItemEvents(menu) {
    const menuEntry = _menuStackEntry(menu);
    const items = _getMenuItemsOf(menu);

    // Mouse enter: focus the item (single source of truth for selection)
    items.forEach((btn, i) => {
        btn.addEventListener('mouseenter', () => {
            btn.focus({ preventScroll: true });
            menuEntry.lastIdx = i;
        });

        btn.addEventListener('mouseleave', () => {
            if (btn._submenuChildren) _clearSubmenuTimer();
        });
    });

    // Focus handler: when any item receives focus (mouse or keyboard),
    // decide whether to open/close submenus.
    menu.addEventListener('focusin', (ev) => {
        const btn = ev.target;
        if (btn === menu) return; // Container itself, not an item

        // Check if cursor is in the safe triangle toward an open submenu
        const inSafeZone = _isInSubmenuSafeZone(menu);

        if (btn._submenuChildren) {
            // Submenu parent focused: start delay to open its submenu.
            // Skip if this item's submenu is already open.
            const alreadyOpen = _menuStack.some(e => e.parentItem === btn);
            if (!alreadyOpen) {
                _clearSubmenuTimer();
                _submenuTimer = setTimeout(() => _openSubmenu(btn, btn._submenuChildren, menu), 225);
            }
        } else {
            // Non-parent item focused: close deeper menus, unless cursor
            // is inside the safe triangle (moving diagonally toward submenu)
            _clearSubmenuTimer();
            if (!inSafeZone) {
                _closeSubmenusBelow(menu);
            }
        }
    });

    // When mouse leaves the menu entirely, deselect items but don't close submenus
    // (user might be moving toward a submenu).
    menu.addEventListener('mouseleave', () => {
        menu.focus({ preventScroll: true });
    });

    // Debug: continuously redraw the safe triangle as the mouse moves
    if (_DEBUG_TRIANGLE) {
        menu.addEventListener('mousemove', () => _isInSubmenuSafeZone(menu));
    }
}

// =============================================
// Submenu open/close
// =============================================

function _openSubmenu(parentItem, children, parentMenuEl) {
    // Close any submenu already open at this level or deeper
    _closeSubmenusBelow(parentMenuEl);

    // Enforce max depth: 6 menus total (root + "Child pages" + 4 drill-down levels)
    if (_menuStack.length >= 6) return;

    const VIEWPORT_MARGIN = 20;  // Minimum distance from all viewport edges
    const OVERLAP = 5;           // Horizontal overlap between parent and submenu

    const submenu = _buildMenuElement(children, 'Submenu');
    document.body.appendChild(submenu);

    const parentRect = parentMenuEl.getBoundingClientRect();
    const itemRect = parentItem.getBoundingClientRect();
    const submenuRect = submenu.getBoundingClientRect();

    // Default: attach to the right, overlapping by OVERLAP px
    let x = parentRect.right - OVERLAP;
    let y = itemRect.top - 5;

    // Flip to left side if not enough space on the right
    if (x + submenuRect.width > window.innerWidth - VIEWPORT_MARGIN) {
        x = parentRect.left - submenuRect.width + OVERLAP;
    }

    // Clamp to viewport with 20px margin on all sides
    x = Math.max(VIEWPORT_MARGIN, Math.min(x, window.innerWidth - submenuRect.width - VIEWPORT_MARGIN));
    y = Math.max(VIEWPORT_MARGIN, Math.min(y, window.innerHeight - submenuRect.height - VIEWPORT_MARGIN));

    submenu.style.left = x + 'px';
    submenu.style.top = y + 'px';
    submenu.style.zIndex = 10000 + _menuStack.length;

    // Constrain scroll container height if submenu would overflow viewport
    _applyMenuScrollConstraint(submenu, y);

    // Snapshot mouse position as the triangle anchor — where the user was when
    // the submenu appeared. This stays fixed and doesn't follow the cursor.
    _menuStack.push({ el: submenu, parentItem, lastIdx: -1, safeZoneActive: true, anchorX: _lastMouseX, anchorY: _lastMouseY });

    // Mark as expanded and keep full accent highlight. Dimming to 50%
    // happens later when focus actually moves into the submenu.
    parentItem.setAttribute('aria-expanded', 'true');
    parentItem.classList.add('submenu-parent-open');

    // Wire mouse events on submenu items
    _wireMenuItemEvents(submenu);

    // Transition from full highlight to dimmed when focus enters submenu.
    // focusin bubbles, so one listener catches all child item focuses.
    submenu.addEventListener('focusin', (ev) => {
        if (ev.target !== submenu) {
            parentItem.classList.remove('submenu-parent-open');
            parentItem.classList.add('submenu-parent-active');
        }
    });

    // Keep submenu open when mouse enters it; transition to dimmed
    submenu.addEventListener('mouseenter', () => {
        _clearSubmenuTimer();
        parentItem.classList.remove('submenu-parent-open');
        parentItem.classList.add('submenu-parent-active');
        // Re-enable safe zone when cursor enters submenu
        const entry = _menuStack.find(e => e.el === submenu);
        if (entry) entry.safeZoneActive = true;
    });

    // When mouse leaves submenu (back to parent menu), restore highlight
    // and CANCEL the safe zone (macOS behavior: once you've visited the
    // submenu and left, the safe zone no longer protects it).
    submenu.addEventListener('mouseleave', () => {
        parentItem.classList.remove('submenu-parent-active');
        parentItem.classList.add('submenu-parent-open');
        submenu.focus({ preventScroll: true });
        const entry = _menuStack.find(e => e.el === submenu);
        if (entry) entry.safeZoneActive = false;
    });

    // Focus submenu container (not an item — first ArrowDown focuses first item)
    submenu.focus({ preventScroll: true });

    // Debug: draw the triangle immediately when submenu opens
    if (_DEBUG_TRIANGLE) _isInSubmenuSafeZone(parentMenuEl);
}

function _closeSubmenusBelow(menuEl) {
    const idx = _menuStack.findIndex(e => e.el === menuEl);
    if (idx < 0) return;
    _clearSubmenuTimer();

    // Remove from deepest to shallowest
    while (_menuStack.length > idx + 1) {
        const entry = _menuStack.pop();
        entry.el.remove();
        if (entry.parentItem) {
            entry.parentItem.classList.remove('submenu-parent-active', 'submenu-parent-open');
            entry.parentItem.setAttribute('aria-expanded', 'false');
        }
    }
}

function _closeDeepestSubmenu() {
    if (_menuStack.length <= 1) return false; // Can't close root
    const entry = _menuStack.pop();
    entry.el.remove();
    if (entry.parentItem) {
        entry.parentItem.classList.remove('submenu-parent-active', 'submenu-parent-open');
        entry.parentItem.setAttribute('aria-expanded', 'false');
        entry.parentItem.focus({ preventScroll: true });
    }
    return true;
}

// =============================================
// Public API
// =============================================

function showContextMenu(e, items) {
    dismissContextMenu();

    const menu = _buildMenuElement(items, 'Context menu');
    document.body.appendChild(menu);

    // Push as root of menu stack
    _menuStack.push({ el: menu, parentItem: null, lastIdx: -1 });

    // Wire mouse events
    _wireMenuItemEvents(menu);

    // Position: keep within viewport with 20px margin on all sides
    const VIEWPORT_MARGIN = 20;
    const rect = menu.getBoundingClientRect();
    let x = e.clientX;
    let y = e.clientY;
    x = Math.max(VIEWPORT_MARGIN, Math.min(x, window.innerWidth - rect.width - VIEWPORT_MARGIN));
    y = Math.max(VIEWPORT_MARGIN, Math.min(y, window.innerHeight - rect.height - VIEWPORT_MARGIN));
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';

    // Constrain scroll container height if menu would overflow viewport
    _applyMenuScrollConstraint(menu, y);

    _lockScroll();
    menu.focus({ preventScroll: true });

    // Dismiss on outside click, Escape, or window blur
    // Next tick to avoid the originating right-click from immediately dismissing
    requestAnimationFrame(() => {
        document.addEventListener('mousedown', onMenuOutsideClick);
        document.addEventListener('keydown', handleMenuKeydown);
        window.addEventListener('blur', onMenuBlur);
    });
}

function handleMenuKeydown(e) {
    const menu = _activeMenu();
    if (!menu) return;

    // Prevent default for all menu keys
    if (['Escape', 'ArrowDown', 'ArrowUp', 'ArrowRight', 'ArrowLeft',
         'Home', 'End', 'PageUp', 'PageDown', 'Enter', ' ', 'Tab'].includes(e.key)) {
        e.preventDefault();
        e.stopPropagation();
    }

    // Escape: close deepest submenu, or entire tree if at root
    if (e.key === 'Escape') {
        if (!_closeDeepestSubmenu()) dismissContextMenu();
        return;
    }

    if (e.key === 'Tab') {
        dismissContextMenu();
        return;
    }

    const items = _getMenuItemsOf(menu);
    if (items.length === 0) return;
    const idx = items.indexOf(document.activeElement);
    const entry = _menuStackEntry(menu);

    // ArrowRight: open submenu if focused item has children
    if (e.key === 'ArrowRight') {
        if (idx >= 0 && items[idx]._submenuChildren) {
            _openSubmenu(items[idx], items[idx]._submenuChildren, menu);
        }
        return;
    }

    // ArrowLeft: close current submenu (if not root)
    if (e.key === 'ArrowLeft') {
        _closeDeepestSubmenu();
        return;
    }

    // Enter/Space: open submenu if parent item, otherwise activate.
    // .click() triggers the onclick handler which calls _flickerAndDismiss(),
    // so the macOS flicker animation plays on keyboard activation too.
    if (e.key === 'Enter' || e.key === ' ') {
        if (idx >= 0) {
            if (items[idx]._submenuChildren) {
                _openSubmenu(items[idx], items[idx]._submenuChildren, menu);
            } else {
                document.activeElement.click();
            }
        }
        return;
    }

    // Effective index: resume from last known position if no item focused
    let ei = idx;
    if (ei < 0 && entry.lastIdx >= 0 && entry.lastIdx < items.length) {
        ei = entry.lastIdx;
    }

    // Focus helper: focus item and update the stack entry's last index
    let target = -1;
    if (e.key === 'ArrowDown') {
        target = ei < 0 ? 0 : Math.min(ei + 1, items.length - 1);
    } else if (e.key === 'ArrowUp') {
        target = ei < 0 ? items.length - 1 : Math.max(ei - 1, 0);
    } else if (e.key === 'Home' || e.key === 'PageUp') {
        target = 0;
    } else if (e.key === 'End' || e.key === 'PageDown') {
        target = items.length - 1;
    } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
        const char = e.key.toLowerCase();
        target = items.findIndex(item => item.textContent.trim().toLowerCase().startsWith(char));
    }
    if (target >= 0) {
        items[target].focus({ preventScroll: true });
        entry.lastIdx = target;
    }
}

function onMenuOutsideClick(e) {
    if (_menuStack.length === 0) return;
    const inside = _menuStack.some(entry => entry.el.contains(e.target));
    if (!inside) dismissContextMenu();
}

function onMenuBlur() {
    dismissContextMenu();
}

function dismissContextMenu() {
    if (_menuStack.length === 0) return;
    _clearSubmenuTimer();
    _debugClearTriangle();
    _unlockScroll();
    document.removeEventListener('mousedown', onMenuOutsideClick);
    document.removeEventListener('keydown', handleMenuKeydown);
    window.removeEventListener('blur', onMenuBlur);
    for (const entry of _menuStack) entry.el.remove();
    _menuStack = [];
}
