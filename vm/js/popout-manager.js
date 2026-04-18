// =============================================
// URL Bar Popout Manager (shared dismissal + a11y)
// =============================================
//
// Owns the WAI-ARIA dialog focus-management contract for every URL-bar
// flyout (page-info, plugins, screen-reader, accessibility emulation):
//
//   - Only one popout open at a time (global state).
//   - On open: move focus into the panel (first focusable, or the panel
//     itself as a tabindex=-1 fallback).
//   - While open: Tab/Shift+Tab cycle inside the panel (focus trap).
//   - Outside-click, Escape → close; focus returns to whichever element
//     triggered the open (captured from document.activeElement).
//
// Plus two opt-in widget-pattern helpers that popouts attach after
// rendering their interactive content:
//
//   - attachRadiogroupKeys(container)  — ARIA radiogroup pattern
//   - attachTablistKeys(container)     — ARIA tablist pattern
//
// Both manage arrow-key navigation, roving tabindex, and the relevant
// aria-selected / aria-checked state following the WAI-ARIA APG.

const POPOUT_FOCUSABLE_SELECTOR = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
].join(', ');

function getPopoutFocusables(panel) {
    return Array.from(panel.querySelectorAll(POPOUT_FOCUSABLE_SELECTOR))
        .filter(el => el.offsetParent !== null || el === panel);
}

function resolveFocusTarget(panel, initialFocus) {
    if (initialFocus instanceof HTMLElement) return initialFocus;
    if (typeof initialFocus === 'string') {
        const el = panel.querySelector(initialFocus);
        if (el) return el;
    }
    const focusables = getPopoutFocusables(panel);
    if (focusables.length > 0) return focusables[0];
    // Dialog fallback: make the panel itself focusable.
    if (!panel.hasAttribute('tabindex')) panel.setAttribute('tabindex', '-1');
    return panel;
}

/** @type {{ panel: HTMLElement, trigger: HTMLElement, close: () => void, previousFocus: HTMLElement | null } | null} */
let activePopout = null;

function openPopout(panelId, triggerId, closeFn, options = {}) {
    // Close whichever popout is currently open
    if (activePopout) activePopout.close();

    const panel = document.getElementById(panelId);
    const trigger = document.getElementById(triggerId);
    if (!panel) return;

    // Capture what to restore focus to on close. Default = whatever was
    // focused when the caller invoked openPopout (typically the trigger
    // after the click), falling back to the trigger element by ID.
    const previousFocus = options.returnFocus instanceof HTMLElement
        ? options.returnFocus
        : (document.activeElement instanceof HTMLElement
            ? document.activeElement
            : trigger);

    panel.classList.add('show');
    panel.setAttribute('aria-modal', 'true');
    if (trigger) trigger.setAttribute('aria-expanded', 'true');

    activePopout = { panel, trigger, close: closeFn, previousFocus };

    // Register outside-click (delayed so the opening click doesn't immediately close)
    setTimeout(() => document.addEventListener('mousedown', onPopoutOutsideClick, true), 0);

    // Move focus into the panel. Done in a microtask so any render work the
    // caller fires synchronously after openPopout has a chance to produce
    // focusable content first.
    queueMicrotask(() => {
        if (!activePopout || activePopout.panel !== panel) return;
        const target = resolveFocusTarget(panel, options.initialFocus);
        try { target.focus(); } catch (_) { /* element may have been removed */ }
    });
}

function dismissActivePopout() {
    if (!activePopout) return;
    const { panel, previousFocus } = activePopout;
    panel.classList.remove('show');
    panel.removeAttribute('aria-modal');
    if (activePopout.trigger) activePopout.trigger.setAttribute('aria-expanded', 'false');
    document.removeEventListener('mousedown', onPopoutOutsideClick, true);
    activePopout = null;

    if (previousFocus && document.body.contains(previousFocus)) {
        try { previousFocus.focus(); } catch (_) { /* element may have been removed */ }
    }
}

function onPopoutOutsideClick(e) {
    if (!activePopout) return;
    if (!activePopout.panel.contains(e.target) &&
        (!activePopout.trigger || !activePopout.trigger.contains(e.target))) {
        activePopout.close();
    }
}

// Keydown handling for the active popout: Escape closes; Tab/Shift+Tab cycle
// inside the panel. Registered once at module scope, early in capture phase
// so it pre-empts any page-level handler.
document.addEventListener('keydown', (e) => {
    if (!activePopout) return;

    if (e.key === 'Escape') {
        e.preventDefault();
        activePopout.close();
        return;
    }

    if (e.key === 'Tab') {
        const focusables = getPopoutFocusables(activePopout.panel);
        if (focusables.length === 0) {
            // Panel is empty of focusables — keep focus on the panel itself.
            e.preventDefault();
            try { activePopout.panel.focus(); } catch (_) { /* no-op */ }
            return;
        }
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        const current = document.activeElement;

        // If focus somehow escaped to outside the panel, pull it back.
        if (!activePopout.panel.contains(current)) {
            e.preventDefault();
            (e.shiftKey ? last : first).focus();
            return;
        }

        if (e.shiftKey && current === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && current === last) {
            e.preventDefault();
            first.focus();
        }
    }
}, true);

// --- Widget helpers: radiogroup + tablist ------------------------------------
//
// Both follow the WAI-ARIA Authoring Practices Guide. They expect the
// caller to have rendered the correct roles and a single selected/active
// element already; the helper wires arrow-key movement + roving tabindex
// and keeps aria-selected / aria-checked in sync.

function _rovingTabindex(items, activeIndex) {
    items.forEach((el, i) => {
        el.setAttribute('tabindex', i === activeIndex ? '0' : '-1');
    });
}

/**
 * Attach ARIA radiogroup keyboard handling to a container of [role="radio"]
 * children. Arrow/Home/End keys move both focus and selection. Click and
 * Enter/Space also select. Returns a detach function.
 *
 * The caller is responsible for wiring a `change`-like reaction (e.g.
 * re-rendering content dependent on the selection) — this helper only
 * manages focus and aria-checked.
 */
function attachRadiogroupKeys(container) {
    if (!container) return () => {};
    const radios = Array.from(container.querySelectorAll('[role="radio"]'))
        .filter(r => !r.disabled);
    if (radios.length === 0) return () => {};

    let activeIndex = radios.findIndex(r => r.getAttribute('aria-checked') === 'true');
    if (activeIndex < 0) activeIndex = 0;

    _rovingTabindex(radios, activeIndex);

    function selectAt(idx, { focus = true } = {}) {
        if (idx < 0 || idx >= radios.length) return;
        radios.forEach((r, i) => {
            r.setAttribute('aria-checked', i === idx ? 'true' : 'false');
        });
        _rovingTabindex(radios, idx);
        activeIndex = idx;
        if (focus) radios[idx].focus();
        // Synthesize a click so the popout's existing onClick logic runs
        // (e.g. selection → POST to backend, re-render). Native click-event
        // bubbles so whichever handler the chip has is triggered.
        radios[idx].click();
    }

    function onKey(e) {
        const idx = radios.indexOf(document.activeElement);
        if (idx < 0) return;
        switch (e.key) {
            case 'ArrowRight':
            case 'ArrowDown':
                e.preventDefault();
                selectAt((idx + 1) % radios.length);
                break;
            case 'ArrowLeft':
            case 'ArrowUp':
                e.preventDefault();
                selectAt((idx - 1 + radios.length) % radios.length);
                break;
            case 'Home':
                e.preventDefault();
                selectAt(0);
                break;
            case 'End':
                e.preventDefault();
                selectAt(radios.length - 1);
                break;
            case ' ':
            case 'Enter':
                e.preventDefault();
                selectAt(idx);
                break;
        }
    }

    container.addEventListener('keydown', onKey);
    return () => container.removeEventListener('keydown', onKey);
}

/**
 * Attach ARIA tablist keyboard handling to a container of [role="tab"]
 * children. Arrow keys move focus between tabs; Enter/Space activate the
 * focused tab. Home/End jump to first/last. Follows the "select-follows-
 * focus" pattern — moving focus activates the tab (as our tab content is
 * cheap to render; use `{manualActivation: true}` to disable).
 *
 * The helper maintains roving tabindex and aria-selected. Activation is
 * performed by clicking the tab (which triggers whatever existing click
 * handler the app has wired). Returns a detach function.
 */
function attachTablistKeys(container, { manualActivation = false } = {}) {
    if (!container) return () => {};
    const tabs = Array.from(container.querySelectorAll('[role="tab"]'))
        .filter(t => !t.disabled);
    if (tabs.length === 0) return () => {};

    let activeIndex = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
    if (activeIndex < 0) activeIndex = tabs.findIndex(t => t.classList.contains('active'));
    if (activeIndex < 0) activeIndex = 0;

    // Seed ARIA state in case the initial markup didn't.
    tabs.forEach((t, i) => {
        t.setAttribute('aria-selected', i === activeIndex ? 'true' : 'false');
    });
    _rovingTabindex(tabs, activeIndex);

    function activate(idx) {
        if (idx < 0 || idx >= tabs.length) return;
        tabs.forEach((t, i) => {
            t.setAttribute('aria-selected', i === idx ? 'true' : 'false');
        });
        _rovingTabindex(tabs, idx);
        activeIndex = idx;
        tabs[idx].focus();
        if (!manualActivation) tabs[idx].click();
    }

    function moveFocus(idx) {
        if (idx < 0 || idx >= tabs.length) return;
        _rovingTabindex(tabs, idx);
        tabs[idx].focus();
    }

    function onKey(e) {
        const idx = tabs.indexOf(document.activeElement);
        if (idx < 0) return;
        switch (e.key) {
            case 'ArrowRight':
            case 'ArrowDown':
                e.preventDefault();
                (manualActivation ? moveFocus : activate)((idx + 1) % tabs.length);
                break;
            case 'ArrowLeft':
            case 'ArrowUp':
                e.preventDefault();
                (manualActivation ? moveFocus : activate)((idx - 1 + tabs.length) % tabs.length);
                break;
            case 'Home':
                e.preventDefault();
                (manualActivation ? moveFocus : activate)(0);
                break;
            case 'End':
                e.preventDefault();
                (manualActivation ? moveFocus : activate)(tabs.length - 1);
                break;
            case ' ':
            case 'Enter':
                e.preventDefault();
                activate(idx);
                break;
        }
    }

    container.addEventListener('keydown', onKey);
    return () => container.removeEventListener('keydown', onKey);
}

// --- Page Info Popout --------------------------------------------------------

let pageInfoOpen = false;
let pageInfoData = null;
let pageInfoActiveTab = 'summary';

function togglePageInfo() {
    // No page info for internal Inspekt pages
    if (activeTabId && internalTabs[activeTabId]) return;

    if (pageInfoOpen) {
        closePageInfo();
    } else {
        openPageInfo();
    }
}

async function openPageInfo() {
    openPopout('pageInfoPopout', 'urlBarCloudIcon', closePageInfo);
    pageInfoOpen = true;

    const content = document.getElementById('pageInfoContent');
    content.innerHTML = '<div class="page-info-loading">Loading...</div>';

    // Reset active tab to summary
    pageInfoActiveTab = 'summary';
    const tabsContainer = document.querySelector('.page-info-tabs');
    document.querySelectorAll('.page-info-tab').forEach(t => {
        const isActive = t.dataset.tab === 'summary';
        t.classList.toggle('active', isActive);
        t.setAttribute('aria-selected', isActive ? 'true' : 'false');
        t.setAttribute('tabindex', isActive ? '0' : '-1');
        if (!t.hasAttribute('aria-controls')) {
            t.setAttribute('aria-controls', 'pageInfoContent');
        }
    });
    // Wire arrow-key navigation fresh each time in case the tabs were
    // restructured. (`attachTablistKeys` is idempotent per keydown listener.)
    if (tabsContainer && !tabsContainer._tablistAttached) {
        attachTablistKeys(tabsContainer);
        tabsContainer._tablistAttached = true;
    }

    // Fetch page info
    try {
        const response = await fetch(`http://${VNC_HOST}:${CONTROL_PORT}/page-info?tab=${activeTabId}`);
        const data = await response.json();
        if (data.ok && data.data) {
            pageInfoData = data.data;
            renderPageInfoTab(pageInfoActiveTab);
        } else {
            content.innerHTML = `<div class="page-info-loading">${data.error || 'Failed to load'}</div>`;
        }
    } catch (e) {
        content.innerHTML = '<div class="page-info-loading">Connection error</div>';
    }
}

function closePageInfo() {
    dismissActivePopout();
    pageInfoOpen = false;
    pageInfoData = null;
}
