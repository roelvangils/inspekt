// =============================================
// URL Bar Popout Manager (shared dismissal logic)
// =============================================
//
// Both the page-info popout and the plugin dropdown are
// "URL bar popouts" — glassmorphism panels anchored to
// the URL bar. This manager ensures only one is open at
// a time and provides a single outside-click + Escape
// handler that works for any popout.

/** @type {{ panel: HTMLElement, trigger: HTMLElement, close: () => void } | null} */
let activePopout = null;

function openPopout(panelId, triggerId, closeFn) {
    // Close whichever popout is currently open
    if (activePopout) activePopout.close();

    const panel = document.getElementById(panelId);
    const trigger = document.getElementById(triggerId);
    panel.classList.add('show');
    if (trigger) trigger.setAttribute('aria-expanded', 'true');

    activePopout = { panel, trigger, close: closeFn };

    // Register outside-click (delayed so the opening click doesn't immediately close)
    setTimeout(() => document.addEventListener('mousedown', onPopoutOutsideClick, true), 0);
}

function dismissActivePopout() {
    if (!activePopout) return;
    activePopout.panel.classList.remove('show');
    if (activePopout.trigger) activePopout.trigger.setAttribute('aria-expanded', 'false');
    document.removeEventListener('mousedown', onPopoutOutsideClick, true);
    activePopout = null;
}

function onPopoutOutsideClick(e) {
    if (!activePopout) return;
    if (!activePopout.panel.contains(e.target) &&
        (!activePopout.trigger || !activePopout.trigger.contains(e.target))) {
        activePopout.close();
    }
}

// Single Escape handler for all popouts
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && activePopout) {
        activePopout.close();
    }
});

// --- Page Info Popout ---

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
    document.querySelectorAll('.page-info-tab').forEach(t => {
        t.classList.toggle('active', t.dataset.tab === 'summary');
    });

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

