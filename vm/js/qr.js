// =============================================
// QR Hand-off Modal
// =============================================
// Uses the vendored qrcode-generator (global `qrcode`) to render an SVG
// QR for the current URL, so the user can open the same page on a phone.

// Element that had focus before the modal opened — restored on close.
let _qrPrevFocus = null;
// Snapshot of body children + their prior inert state so we can un-inert on close.
let _qrInertedNodes = [];
// The URL currently represented by the QR + URL display. May differ from
// `currentUrl` after the user has shortened the link.
let _qrCurrentUrl = '';

const FOCUSABLE_SELECTOR = [
    'a[href]',
    'button:not([disabled])',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
].join(',');

function _qrEscapeHandler(e) {
    if (e.key === 'Escape') {
        e.preventDefault();
        e.stopImmediatePropagation();
        toggleQrModal(false);
    }
}

function _onQrBackdropClick(e) {
    if (e.target.id === 'qrModalOverlay') toggleQrModal(false);
}

// Keep Tab focus within the modal.
function _qrFocusTrap(e) {
    if (e.key !== 'Tab') return;
    const modal = document.querySelector('#qrModalOverlay .qr-modal');
    if (!modal) return;
    const nodes = Array.from(modal.querySelectorAll(FOCUSABLE_SELECTOR))
        .filter(el => el.offsetParent !== null || el === document.activeElement);
    if (nodes.length === 0) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
    }
}

// Mark every body-level sibling of the overlay as `inert` so AT + Tab skip them.
// Stores the prior inert state per node so we can restore on close.
function _qrSetSiblingsInert(inert) {
    const overlay = document.getElementById('qrModalOverlay');
    if (inert) {
        _qrInertedNodes = [];
        for (const node of document.body.children) {
            if (node === overlay) continue;
            _qrInertedNodes.push({ node, prev: node.inert });
            node.inert = true;
        }
    } else {
        for (const { node, prev } of _qrInertedNodes) {
            node.inert = prev;
        }
        _qrInertedNodes = [];
    }
}

function toggleQrModal(show) {
    const overlay = document.getElementById('qrModalOverlay');
    if (!overlay) return;
    const isShown = overlay.classList.contains('show');
    const next = typeof show === 'boolean' ? show : !isShown;

    if (next) {
        if (typeof dismissHistoryDropdown === 'function' && historyDropdownOpen) {
            dismissHistoryDropdown();
        }
        const url = (currentUrl || '').trim();
        if (!url || url === 'about:blank') {
            if (typeof showToast === 'function') {
                showToast('No URL to share', 'info', 2000);
            }
            return;
        }
        _qrPrevFocus = document.activeElement;
        _qrCurrentUrl = url;
        renderQrModal(url);
        _qrResetShortenButton();
        overlay.classList.add('show');
        _qrSetSiblingsInert(true);
        document.addEventListener('keydown', _qrEscapeHandler, true);
        document.addEventListener('keydown', _qrFocusTrap);
        overlay.addEventListener('click', _onQrBackdropClick);
        // Focus the title so AT announces the dialog label + the tab order
        // starts from a predictable anchor. requestAnimationFrame lets the
        // browser paint the overlay first so focus doesn't get lost.
        requestAnimationFrame(() => {
            const title = document.getElementById('qrModalTitle');
            if (title) title.focus();
        });
    } else {
        overlay.classList.remove('show');
        _qrSetSiblingsInert(false);
        document.removeEventListener('keydown', _qrEscapeHandler, true);
        document.removeEventListener('keydown', _qrFocusTrap);
        overlay.removeEventListener('click', _onQrBackdropClick);
        // Restore focus to the element that triggered the dialog
        if (_qrPrevFocus && typeof _qrPrevFocus.focus === 'function') {
            try { _qrPrevFocus.focus(); } catch { /* node detached */ }
        }
        _qrPrevFocus = null;
    }
}

function renderQrModal(url) {
    const codeEl = document.getElementById('qrModalCode');
    const urlEl = document.getElementById('qrModalUrl');
    if (!codeEl || !urlEl) return;
    urlEl.textContent = url;
    codeEl.innerHTML = '';

    if (typeof qrcode !== 'function') {
        codeEl.textContent = 'QR library not loaded';
        return;
    }

    try {
        const qr = qrcode(0, 'M');
        qr.addData(url);
        qr.make();
        codeEl.innerHTML = qr.createSvgTag({ cellSize: 10, margin: 4, scalable: true });
        const svg = codeEl.querySelector('svg');
        if (svg) {
            svg.removeAttribute('width');
            svg.removeAttribute('height');
            svg.setAttribute('role', 'img');
            svg.setAttribute('aria-label', 'QR code for ' + url);
        }
        // Retrigger the flip-in animation whenever the QR swaps (open + shorten)
        codeEl.classList.remove('flip-in');
        // Force reflow so the class re-add actually restarts the animation
        void codeEl.offsetWidth;
        codeEl.classList.add('flip-in');
    } catch (e) {
        codeEl.textContent = 'Failed to generate QR code: ' + e.message;
    }
}

async function copyQrUrl() {
    const btn = document.getElementById('qrModalCopyBtn');
    if (!_qrCurrentUrl) return;
    try {
        await navigator.clipboard.writeText(_qrCurrentUrl);
        if (btn) {
            btn.classList.add('copied');
            btn.setAttribute('aria-label', 'Copied');
            setTimeout(() => {
                btn.classList.remove('copied');
                btn.setAttribute('aria-label', 'Copy URL to clipboard');
            }, 1400);
        }
        if (typeof showToast === 'function') showToast('URL copied', 'success', 1500);
    } catch (e) {
        if (typeof showToast === 'function') showToast('Copy failed', 'error', 2000);
    }
}

function _qrResetShortenButton() {
    const btn = document.getElementById('qrModalShortenBtn');
    if (!btn) return;
    btn.disabled = false;
    btn.classList.remove('loading', 'done');
    btn.setAttribute('aria-label', 'Shorten URL');
    btn.setAttribute('title', 'Shorten URL (is.gd)');
}

async function shortenQrUrl() {
    const btn = document.getElementById('qrModalShortenBtn');
    if (!_qrCurrentUrl || !btn || btn.disabled) return;
    // Don't shorten if it's already is.gd (idempotency guard)
    if (/^https?:\/\/is\.gd\//i.test(_qrCurrentUrl)) {
        if (typeof showToast === 'function') showToast('Already a short link', 'info', 1500);
        return;
    }
    btn.disabled = true;
    btn.classList.add('loading');
    btn.setAttribute('aria-label', 'Shortening URL');
    try {
        const endpoint = 'https://is.gd/create.php?format=simple&url=' + encodeURIComponent(_qrCurrentUrl);
        const resp = await fetch(endpoint);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const short = (await resp.text()).trim();
        if (!/^https?:\/\//i.test(short)) throw new Error('Unexpected response');
        _qrCurrentUrl = short;
        renderQrModal(short);
        btn.classList.remove('loading');
        btn.classList.add('done');
        btn.setAttribute('aria-label', 'Shortened');
        btn.setAttribute('title', 'Already a short link');
        if (typeof showToast === 'function') showToast('Shortened via is.gd', 'success', 1800);
    } catch (e) {
        btn.disabled = false;
        btn.classList.remove('loading');
        btn.setAttribute('aria-label', 'Shorten URL');
        if (typeof showToast === 'function') showToast('Shortener unreachable', 'error', 2000);
        console.warn('[qr] shorten failed:', e);
    }
}
