/**
 * Virtual Scrollbar Controller — macOS-style overlay scrollbar for VNC viewport.
 *
 * Renders a thin overlay scrollbar on the right edge of the VNC container that
 * reflects the scroll position of the page inside the VM. Supports thumb dragging,
 * track clicking, and auto-hide with hover activation.
 *
 * The thumb color adapts automatically via CSS mix-blend-mode: difference
 * combined with filter: grayscale(1) — no JS needed for color logic.
 *
 * Globals this module reads:
 *   VNC_HOST, CONTROL_PORT — server connection (from control-panel.html)
 *   rfb — noVNC RFB instance (from control-panel.html)
 *
 * Globals this module exposes:
 *   stopScrollbarPolling() — pause polling (on VNC disconnect)
 *   startScrollbarPolling() — resume polling (on VNC connect)
 */

// =============================================
// Virtual Scrollbar Controller
// =============================================

(function initVirtualScrollbar() {
    const scrollbar = document.getElementById('vScrollbar');
    const track = document.getElementById('vScrollbarTrack');
    const thumb = document.getElementById('vScrollbarThumb');
    const container = document.getElementById('vncContainer');

    let scrollState = { top: 0, scrollHeight: 0, clientHeight: 0, hasVerticalScroll: false };
    let isDragging = false;
    let dragOffsetY = 0;
    let hideTimer = null;
    let pollTimer = null;
    let pollInterval = 500;       // idle rate
    const activePollInterval = 80; // during/after scroll
    const hideDelay = 1500;        // ms before auto-hide
    let activePollResetTimer = null;
    let lastScrollSendTime = 0;
    const scrollSendThrottle = 50; // ms between scroll-to requests during drag

    // --- Polling scroll state from control server ---
    function pollScrollState() {
        // During drag, thumb position is updated optimistically — no need to poll
        if (isDragging) return;
        fetch(`http://${VNC_HOST}:${CONTROL_PORT}/scroll-state`)
            .then(r => r.json())
            .then(data => {
                if (data.ok) {
                    scrollState = data;
                    updateThumb();
                }
            })
            .catch(() => {})
            .finally(() => {
                pollTimer = setTimeout(pollScrollState, pollInterval);
            });
    }

    // --- Lifecycle: allow VNC connect/disconnect to control polling ---
    window.stopScrollbarPolling = function() {
        clearTimeout(pollTimer);
        pollTimer = null;
    };
    window.startScrollbarPolling = function() {
        if (pollTimer) return; // already running
        pollTimer = setTimeout(pollScrollState, 500);
    };

    // --- Thumb positioning ---
    function updateThumb() {
        if (!scrollState.hasVerticalScroll) {
            scrollbar.classList.remove('visible');
            return;
        }
        const trackHeight = track.offsetHeight;
        const ratio = scrollState.clientHeight / scrollState.scrollHeight;
        const thumbHeight = Math.max(30, Math.round(trackHeight * ratio));
        const maxThumbTop = trackHeight - thumbHeight;
        const scrollRange = scrollState.scrollHeight - scrollState.clientHeight;
        const thumbTop = scrollRange > 0
            ? Math.round((scrollState.top / scrollRange) * maxThumbTop)
            : 0;

        thumb.style.height = thumbHeight + 'px';
        thumb.style.top = thumbTop + 'px';
    }

    // --- Show / hide ---
    function show() {
        if (!scrollState.hasVerticalScroll) return;
        scrollbar.classList.add('visible');
        scheduleHide();
    }

    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => {
            if (!isDragging) scrollbar.classList.remove('visible');
        }, hideDelay);
    }

    // --- Boost poll rate temporarily ---
    function setActivePollRate() {
        pollInterval = activePollInterval;
        // Return to idle rate after 2s of no further triggers
        clearTimeout(activePollResetTimer);
        activePollResetTimer = setTimeout(() => {
            pollInterval = 500;
        }, 2000);
    }

    // --- Send scroll command to VM (throttled) ---
    function sendScrollTo(targetTop, force) {
        const now = Date.now();
        if (!force && now - lastScrollSendTime < scrollSendThrottle) return;
        lastScrollSendTime = now;
        fetch(`http://${VNC_HOST}:${CONTROL_PORT}/scroll-to`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ top: Math.round(targetTop) })
        }).catch(() => {});
    }

    // --- Thumb drag ---
    function onDragStart(e) {
        e.preventDefault();
        isDragging = true;
        scrollbar.classList.add('dragging');
        thumb.classList.add('dragging');
        const thumbRect = thumb.getBoundingClientRect();
        dragOffsetY = e.clientY - thumbRect.top;
        // Capture pointer so drag continues even outside the scrollbar area
        thumb.setPointerCapture(e.pointerId);
        thumb.addEventListener('pointermove', onDragMove);
        thumb.addEventListener('pointerup', onDragEnd);
    }

    function onDragMove(e) {
        if (!isDragging) return;
        const trackRect = track.getBoundingClientRect();
        const thumbHeight = thumb.offsetHeight;
        const maxY = trackRect.height - thumbHeight;
        const currentY = Math.max(0, Math.min(e.clientY - trackRect.top - dragOffsetY, maxY));

        // Optimistic visual update
        thumb.style.top = currentY + 'px';

        // Calculate and send scroll position
        const scrollRatio = maxY > 0 ? currentY / maxY : 0;
        const targetScrollTop = scrollRatio * (scrollState.scrollHeight - scrollState.clientHeight);
        sendScrollTo(targetScrollTop);
    }

    function onDragEnd(e) {
        // Send final position unthrottled to ensure exact landing
        const trackRect = track.getBoundingClientRect();
        const thumbHeight = thumb.offsetHeight;
        const maxY = trackRect.height - thumbHeight;
        const currentY = Math.max(0, Math.min(e.clientY - trackRect.top - dragOffsetY, maxY));
        const scrollRatio = maxY > 0 ? currentY / maxY : 0;
        const targetScrollTop = scrollRatio * (scrollState.scrollHeight - scrollState.clientHeight);
        sendScrollTo(targetScrollTop, true);

        isDragging = false;
        scrollbar.classList.remove('dragging');
        thumb.classList.remove('dragging');
        thumb.releasePointerCapture(e.pointerId);
        thumb.removeEventListener('pointermove', onDragMove);
        thumb.removeEventListener('pointerup', onDragEnd);
        scheduleHide();
        // Restart polling (was paused during drag) and refocus VNC
        pollScrollState();
        if (rfb) rfb.focus();
    }

    // --- Track click (jump to position) ---
    function onTrackClick(e) {
        if (e.target === thumb) return;
        const trackRect = track.getBoundingClientRect();
        const clickRatio = (e.clientY - trackRect.top) / trackRect.height;
        const targetScrollTop = clickRatio * (scrollState.scrollHeight - scrollState.clientHeight);
        sendScrollTo(targetScrollTop);
        show();
        setActivePollRate();
    }

    // --- Wheel detection on VNC container ---
    container.addEventListener('wheel', () => {
        show();
        setActivePollRate();
    }, { passive: true, capture: true });

    // --- Hover zone along right edge ---
    const hoverZone = document.getElementById('vScrollbarHoverZone');
    hoverZone.addEventListener('mouseenter', () => {
        setActivePollRate();
        show();
    });
    hoverZone.addEventListener('mouseleave', () => {
        scheduleHide();
    });
    // Keep scrollbar visible while hovering the scrollbar itself
    scrollbar.addEventListener('mouseenter', () => {
        clearTimeout(hideTimer);
    });
    scrollbar.addEventListener('mouseleave', () => {
        if (!isDragging) scheduleHide();
    });

    // --- Bind events ---
    thumb.addEventListener('pointerdown', onDragStart);
    track.addEventListener('click', onTrackClick);

    // --- Start polling ---
    pollTimer = setTimeout(pollScrollState, 1000); // initial delay for page load
})();
