/**
 * Inspekt Overlay Bus — isolated-world producer.
 *
 * Holds the WebSocket to the host overlay-bus server (port 8890) and
 * forwards data emitted by MAIN-world feature scripts (axe, inspect,
 * recorder, …) without touching page DOM. The host control panel renders
 * overlays on top of the noVNC canvas.
 *
 * MAIN ↔ isolated bridge: window.postMessage with INSPEKT_OVERLAY_* envelope.
 *
 * v1 scope (this phase): connection + set/update/clear/clearAll/snapshot
 * passthrough. Observers (ResizeObserver / IntersectionObserver) and
 * rAF-coalesced batching land in Phase 3.
 *
 * Loaded as a content script at run_at: document_start, isolated world,
 * all_frames: false.
 */
(function () {
    'use strict';

    const PROTOCOL_VERSION = 1;
    const PRODUCER_PATH = '/overlay/ws';
    const RECONNECT_BASE_MS = 250;
    const RECONNECT_MAX_MS = 5000;
    // If the VM-mode WS hasn't connected after this many failed attempts,
    // fall back to the in-page consumer (extensions/chrome/overlay-bus-inpage.js)
    // and route ops in-process. Net cost outside VM is two failed WS
    // attempts (~750 ms total: 250 ms first delay + 500 ms second) on first
    // emission. The in-page consumer is loaded by the manifest in every
    // page, so it's already in this isolated world.
    const WS_FALLBACK_AFTER_ATTEMPTS = 2;

    // ---- Transport state machine ------------------------------------------
    // Transport modes:
    //   'pending' — neither WS nor in-page is the active sink yet.
    //               Ops queue in _outboundQueue. Initial state.
    //   'ws'      — WebSocket to the VM control panel is OPEN. Set by
    //               socket.open handler. Ops serialise + send over WS.
    //   'inpage'  — Fallback: WS gave up; we route ops directly to
    //               window.__inspektOverlayInPageConsumer__ in this same
    //               isolated world. Set by _activateInPageFallback.
    //
    // Once 'inpage' is active, WS reconnect keeps trying in the background
    // (cheap 5 s polling at the cap). If WS later connects, the open
    // handler flips _transport back to 'ws' and the on-open snapshot push
    // catches the server up to current state. Visual state in the inpage
    // consumer's shadow root won't be cleared automatically — mode swap
    // mid-session is rare enough that v1 doesn't bother.
    let _transport = 'pending';

    // Heuristic: only run inside the VM. The bus is meant for VM mode where
    // overlays render host-side; outside the VM, in-page DOM injection is
    // the existing path. We detect the VM by the presence of the noVNC-served
    // control panel's known port mapping; the safest check is environment
    // injection from the extension. For now we always attempt — the WS will
    // simply fail to connect outside the VM and the bus stays in disconnected
    // state, which the MAIN-world stub treats as "no bus available".
    //
    // Top-frame only — manifest has all_frames: false but cross-frame
    // re-exec from top-level history-pushState is safe to deduplicate.
    if (window.__INSPEKT_OVERLAY_PRODUCER__) return;
    window.__INSPEKT_OVERLAY_PRODUCER__ = true;

    // Session id — we don't have access to the CDP target/frame ids from a
    // content script, so we synthesize a stable id per-document. The host
    // control panel filters consumers by active tab via its own URL/title
    // tracking, so this id only needs to be unique across simultaneously
    // open producer documents.
    const SESSION_ID = _generateSessionId();

    const REGISTRY = new Map();         // id -> {kind, rect, payload, opts}
    const TRACKED = new Map();          // id -> {el, ro, io, selector}
    const DIRTY = new Map();            // id -> latest op (set/update/clear) — coalesced per frame
    let _rafScheduled = false;
    let _scrollResizeAttached = false;
    let socket = null;
    let connected = false;
    let connectAttempts = 0;
    let reconnectTimer = null;
    let _outboundQueue = [];

    function _generateSessionId() {
        // tabTargetId:frameId is plan-spec; we don't have either, so use a
        // random per-document id. Format kept as `<tab>:<frame>` shape so
        // server log lines look uniform with future CDP-aware producers.
        const r = (Math.random().toString(36).slice(2, 10));
        return 'doc-' + r + ':0';
    }

    function _wsUrl() {
        // Producer is loopback-only inside the VM container (iptables enforced).
        // The page is served from the actual web origin (the inspected site),
        // not from localhost:6080. We always connect to localhost:8890 — the
        // container only allows outbound to the inspekt UID's localhost
        // ports, but the producer here runs as root (Chromium kiosk),
        // unaffected by those iptables rules.
        return 'ws://localhost:8890' + PRODUCER_PATH +
               '?role=producer&session=' + encodeURIComponent(SESSION_ID);
    }

    function _connect() {
        if (socket) return;
        try {
            socket = new WebSocket(_wsUrl());
        } catch (e) {
            _scheduleReconnect();
            return;
        }
        socket.addEventListener('open', () => {
            connected = true;
            connectAttempts = 0;
            _transport = 'ws';
            // Push current registry as a fresh snapshot so a reconnected
            // server has the producer-side truth.
            const entries = [];
            REGISTRY.forEach((entry, id) => {
                entries.push({
                    id,
                    kind: entry.kind,
                    rect: entry.rect,
                    payload: entry.payload,
                    opts: entry.opts,
                });
            });
            try {
                socket.send(JSON.stringify({
                    v: PROTOCOL_VERSION,
                    type: 'overlay.snapshot',
                    sessionId: SESSION_ID,
                    entries,
                }));
            } catch {}
            // Flush any queued ops captured before connection.
            const q = _outboundQueue;
            _outboundQueue = [];
            for (const msg of q) _sendRaw(msg);
            // Mirrored into MAIN-world `window.__INSPEKT_OVERLAY_BUS_READY__`
            // by overlay-bus-main.js's message handler — isolated and MAIN
            // have separate window objects, so postMessage is the only path.
            window.postMessage({
                source: 'inspekt-overlay-isolated',
                type: 'INSPEKT_OVERLAY_BUS_READY',
                ready: true,
            }, location.origin);
        });
        socket.addEventListener('close', () => {
            socket = null;
            // Only flip the bus to "not ready" if we have no other
            // transport. With the in-page consumer active, the bus stays
            // ready and ops keep flowing locally.
            if (_transport !== 'inpage') {
                connected = false;
                _transport = 'pending';
                window.postMessage({
                    source: 'inspekt-overlay-isolated',
                    type: 'INSPEKT_OVERLAY_BUS_READY',
                    ready: false,
                }, location.origin);
            }
            _scheduleReconnect();
        });
        socket.addEventListener('error', () => {
            // 'close' will follow.
        });
        socket.addEventListener('message', (e) => {
            let msg;
            try { msg = JSON.parse(e.data); } catch { return; }
            if (!msg || typeof msg !== 'object') return;
            // Server forwards consumer-originated overlay.event messages
            // straight through to us. Bridge to MAIN.
            if (msg.type === 'overlay.event') {
                window.postMessage({
                    source: 'inspekt-overlay-isolated',
                    type: 'INSPEKT_OVERLAY_EVENT',
                    id: msg.id,
                    event: msg.event,
                    payload: msg.payload || {},
                }, location.origin);
            }
        });
    }

    function _scheduleReconnect() {
        if (reconnectTimer) return;
        // After WS_FALLBACK_AFTER_ATTEMPTS failed attempts, switch to the
        // in-page consumer if one is loaded in this isolated world. We
        // keep a low-frequency WS reconnect after that just in case the
        // VM control panel comes online later.
        if (_transport !== 'ws' && connectAttempts >= WS_FALLBACK_AFTER_ATTEMPTS) {
            _activateInPageFallback();
        }
        const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, connectAttempts), RECONNECT_MAX_MS);
        connectAttempts++;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            _connect();
        }, delay);
    }

    function _activateInPageFallback() {
        // Idempotent: re-entering after activation (e.g. on a subsequent
        // failed WS reconnect that re-runs _scheduleReconnect's threshold
        // check) is a no-op. Also defers to a successful WS if one races
        // in between attempts — `_transport === 'ws'` early-exits.
        if (_transport === 'inpage' || _transport === 'ws') return;
        const inpage = window.__inspektOverlayInPageConsumer__;
        if (!inpage || typeof inpage.dispatch !== 'function') return;
        _transport = 'inpage';
        connected = true;
        // Drain anything we queued while WS was being attempted. Done
        // before any new _sendRaw can race because we're synchronous
        // inside the reconnect timer callback that just flipped transport.
        const q = _outboundQueue; _outboundQueue = [];
        for (const msg of q) _dispatchInPage(msg);
        // Replay current registry as a snapshot. Most pages emit set→clear
        // pairs faster than the ~750 ms WS-failure window so REGISTRY is
        // usually empty here, but a producer that emitted-and-tracked an
        // overlay before the fallback fired needs the snapshot to bring
        // the in-page consumer in sync.
        const entries = [];
        REGISTRY.forEach((entry, id) => entries.push({
            id, kind: entry.kind, rect: entry.rect, payload: entry.payload, opts: entry.opts,
        }));
        if (entries.length) {
            inpage.dispatch({ v: PROTOCOL_VERSION, type: 'overlay.snapshot', sessionId: SESSION_ID, entries });
        }
        // Mark the bus ready in MAIN so feature scripts that branch on
        // __INSPEKT_OVERLAY_BUS_READY__ start emitting through the bus.
        window.postMessage({
            source: 'inspekt-overlay-isolated',
            type: 'INSPEKT_OVERLAY_BUS_READY',
            ready: true,
        }, location.origin);
    }

    function _dispatchInPage(msg) {
        const inpage = window.__inspektOverlayInPageConsumer__;
        if (!inpage) return;
        try { inpage.dispatch(msg); } catch (e) { console.error('[overlay-bus] inpage dispatch', e); }
    }

    function _sendRaw(msg) {
        msg.v = PROTOCOL_VERSION;
        msg.sessionId = SESSION_ID;
        if (_transport === 'inpage') {
            _dispatchInPage(msg);
            return;
        }
        if (_transport === 'ws' && socket && socket.readyState === WebSocket.OPEN) {
            try { socket.send(JSON.stringify(msg)); } catch {}
            return;
        }
        // Pending: queue. Either WS will connect or the in-page fallback
        // will drain the queue once it activates.
        _outboundQueue.push(msg);
        if (_outboundQueue.length > 1000) _outboundQueue.shift();
    }

    function _applyLocal(op) {
        const id = op.id;
        if (typeof id !== 'string') return;
        if (op.type === 'overlay.set') {
            REGISTRY.set(id, {
                kind: op.kind || 'unknown',
                rect: op.rect || null,
                payload: op.payload || null,
                opts: op.opts || null,
            });
        } else if (op.type === 'overlay.update') {
            const existing = REGISTRY.get(id);
            if (!existing) return;
            if (op.rect) existing.rect = op.rect;
            if (op.payload) existing.payload = Object.assign({}, existing.payload, op.payload);
            if (op.opts) existing.opts = Object.assign({}, existing.opts, op.opts);
        } else if (op.type === 'overlay.clear') {
            REGISTRY.delete(id);
            _detachTracking(id);
        }
    }

    // --- rAF-coalesced batch flush -----------------------------------------
    // Every mutation is enqueued in DIRTY (id -> last-op). On the next rAF we
    // collapse to a single overlay.batch. Idle pages send zero traffic.

    function _enqueue(op) {
        if (!op || typeof op.id !== 'string') return;
        // Last write wins per id within a frame: a set+update+update collapses
        // to a set with the latest rect/payload merged.
        const existing = DIRTY.get(op.id);
        if (existing) {
            // If a clear comes in after a set, the clear wins.
            if (op.type === 'overlay.clear') {
                DIRTY.set(op.id, op);
            } else if (existing.type === 'overlay.clear') {
                // A set after a clear in the same frame is unusual; honor the
                // latest as a set (replace).
                DIRTY.set(op.id, op);
            } else if (existing.type === 'overlay.set' && op.type === 'overlay.update') {
                // Merge update into the queued set.
                if (op.rect) existing.rect = op.rect;
                if (op.payload) existing.payload = Object.assign({}, existing.payload, op.payload);
                if (op.opts) existing.opts = Object.assign({}, existing.opts, op.opts);
            } else if (existing.type === 'overlay.update' && op.type === 'overlay.update') {
                if (op.rect) existing.rect = op.rect;
                if (op.payload) existing.payload = Object.assign({}, existing.payload, op.payload);
                if (op.opts) existing.opts = Object.assign({}, existing.opts, op.opts);
            } else {
                DIRTY.set(op.id, op);
            }
        } else {
            DIRTY.set(op.id, op);
        }
        if (_rafScheduled) return;
        _rafScheduled = true;
        // requestAnimationFrame ties our flush rate to the page's frame loop
        // — when scrolling, observers fire per-frame, and we send one batch
        // per frame. Background tabs rAF-throttle, which is the right
        // behavior here too.
        requestAnimationFrame(_flush);
    }

    function _flush() {
        _rafScheduled = false;
        if (DIRTY.size === 0) return;
        const ops = Array.from(DIRTY.values());
        DIRTY.clear();
        for (const op of ops) _applyLocal(op);
        if (ops.length === 1) {
            _sendRaw(ops[0]);
        } else {
            _sendRaw({ type: 'overlay.batch', ops });
        }
    }

    // --- Element tracking via observers ------------------------------------

    function _resolveSelector(selector) {
        if (typeof selector !== 'string' || !selector) return null;
        // axe target arrays come through as single CSS selectors (joined with ' > ').
        try { return document.querySelector(selector); } catch { return null; }
    }

    function _attachTracking(id, selector) {
        if (!selector) return;
        // Tear down any prior tracking for this id (selector may have changed).
        _detachTracking(id);
        const el = _resolveSelector(selector);
        if (!el) return;

        const recompute = () => {
            if (!el.isConnected) {
                _enqueue({ type: 'overlay.clear', id });
                _detachTracking(id);
                return;
            }
            const r = el.getBoundingClientRect();
            _enqueue({
                type: 'overlay.update',
                id,
                rect: { left: r.left, top: r.top, width: r.width, height: r.height },
            });
        };

        let ro = null, io = null;
        try {
            ro = new ResizeObserver(recompute);
            ro.observe(el);
        } catch {}
        try {
            io = new IntersectionObserver(recompute, { root: null, threshold: [0, 0.5, 1] });
            io.observe(el);
        } catch {}
        TRACKED.set(id, { el, ro, io, selector, recompute });

        _ensureScrollResizeListeners();
    }

    function _detachTracking(id) {
        const t = TRACKED.get(id);
        if (!t) return;
        try { if (t.ro) t.ro.disconnect(); } catch {}
        try { if (t.io) t.io.disconnect(); } catch {}
        TRACKED.delete(id);
    }

    function _detachAllTracking() {
        for (const id of Array.from(TRACKED.keys())) _detachTracking(id);
    }

    function _recomputeAllTracked() {
        // Called from scroll/resize listeners. Ancestor scroll moves an
        // element's viewport rect without triggering ResizeObserver, so we
        // need to fan out manually. Each recompute enqueues at most one
        // update per id; the rAF coalescer collapses bursts.
        for (const t of TRACKED.values()) {
            if (t && typeof t.recompute === 'function') t.recompute();
        }
    }

    // ---- Scroll-suppress signal -------------------------------------------
    // VM mode renders overlays host-side over the noVNC canvas. The DOM
    // overlays update on every scroll event (~16 ms) but the noVNC pixel
    // stream lags (~50–150 ms), so during fast scrolls the overlays
    // "race" the canvas. We emit overlay.suppress on scroll-start and
    // overlay.unsuppress after a short settling window; the consumer
    // dims/blurs everything except detached popovers in between, hiding
    // the discrepancy. Non-VM mode (in-page consumer) ignores these
    // messages — there's no streaming delay there.
    const SCROLL_SETTLE_MS = 150;
    let _scrollSuppressActive = false;
    let _scrollSuppressTimer = null;

    function _signalScrolling() {
        if (!_scrollSuppressActive) {
            _scrollSuppressActive = true;
            _sendRaw({ type: 'overlay.suppress' });
        }
        if (_scrollSuppressTimer) clearTimeout(_scrollSuppressTimer);
        _scrollSuppressTimer = setTimeout(() => {
            _scrollSuppressActive = false;
            _scrollSuppressTimer = null;
            _sendRaw({ type: 'overlay.unsuppress' });
        }, SCROLL_SETTLE_MS);
    }

    function _onScrollOrResize() {
        _signalScrolling();
        _recomputeAllTracked();
    }

    function _ensureScrollResizeListeners() {
        if (_scrollResizeAttached) return;
        _scrollResizeAttached = true;
        // capture: true catches scrolls in any scrollable ancestor.
        // passive: true keeps scroll perf intact.
        window.addEventListener('scroll', _onScrollOrResize, { capture: true, passive: true });
        window.addEventListener('resize', _onScrollOrResize, { passive: true });
    }

    // MutationObserver on the body catches subtree removals so we can clear
    // overlays whose tracked element disappeared (the IntersectionObserver
    // fires on visibility changes but NOT on disconnect alone — the element
    // can be removed while still intersecting nothing if it was already
    // off-screen). One observer total, not per-id.
    let _domMutationObserver = null;
    function _ensureDomMutationObserver() {
        if (_domMutationObserver || !document.documentElement) return;
        try {
            _domMutationObserver = new MutationObserver(() => {
                if (TRACKED.size === 0) return;
                for (const [id, t] of Array.from(TRACKED.entries())) {
                    if (!t.el || !t.el.isConnected) {
                        _enqueue({ type: 'overlay.clear', id });
                        _detachTracking(id);
                    }
                }
            });
            _domMutationObserver.observe(document.documentElement, {
                childList: true,
                subtree: true,
            });
        } catch {}
    }

    // --- MAIN ↔ isolated bridge ---
    window.addEventListener('message', (e) => {
        if (e.source !== window) return;
        const m = e.data;
        if (!m || m.source !== 'inspekt-page') return;
        const t = m.type;
        if (typeof t !== 'string' || !t.startsWith('INSPEKT_OVERLAY_')) return;

        switch (t) {
            case 'INSPEKT_OVERLAY_SET': {
                const op = {
                    type: 'overlay.set',
                    id: m.id,
                    kind: m.kind,
                    rect: m.rect,
                    payload: m.payload || null,
                    opts: m.opts || null,
                };
                _enqueue(op);
                // _mainTracked: the MAIN-world stub owns observers for this
                // overlay (used for shadow-DOM elements that can't be expressed
                // as a flat CSS selector). Skip our own tracker install.
                if (m.opts && m.opts._mainTracked) return;
                // Attach tracking immediately if requested. Tracking observers
                // emit further updates via _enqueue, which the rAF flush
                // coalesces with the initial set into one batch.
                const selector = m.opts && (m.opts.selector ||
                    (Array.isArray(m.opts.target) && m.opts.target[0]));
                if (m.opts && m.opts.track && selector) {
                    _ensureDomMutationObserver();
                    _attachTracking(m.id, selector);
                }
                return;
            }
            case 'INSPEKT_OVERLAY_UPDATE': {
                const op = { type: 'overlay.update', id: m.id };
                if (m.rect) op.rect = m.rect;
                if (m.payload) op.payload = m.payload;
                if (m.opts) op.opts = m.opts;
                _enqueue(op);
                return;
            }
            case 'INSPEKT_OVERLAY_CLEAR': {
                _enqueue({ type: 'overlay.clear', id: m.id });
                return;
            }
            case 'INSPEKT_OVERLAY_CLEAR_ALL': {
                const prefix = m.prefix || '';
                for (const id of Array.from(REGISTRY.keys())) {
                    if (!prefix || id.startsWith(prefix)) {
                        _enqueue({ type: 'overlay.clear', id });
                    }
                }
                return;
            }
            case 'INSPEKT_OVERLAY_TRACK': {
                if (typeof m.id !== 'string') return;
                _ensureDomMutationObserver();
                _attachTracking(m.id, m.selector);
                return;
            }
            case 'INSPEKT_OVERLAY_PING': {
                // MAIN stub asks us to re-broadcast current connection state
                // (it can miss the original BUS_READY message due to load-order).
                window.postMessage({
                    source: 'inspekt-overlay-isolated',
                    type: 'INSPEKT_OVERLAY_BUS_READY',
                    ready: connected,
                }, location.origin);
                return;
            }
            case 'INSPEKT_OVERLAY_SNAPSHOT': {
                const entries = [];
                REGISTRY.forEach((entry, id) => {
                    entries.push({
                        id,
                        kind: entry.kind,
                        rect: entry.rect,
                        payload: entry.payload,
                        opts: entry.opts,
                    });
                });
                window.postMessage({
                    source: 'inspekt-overlay-isolated',
                    type: 'INSPEKT_OVERLAY_SNAPSHOT_RESPONSE',
                    requestId: m.requestId,
                    entries,
                }, location.origin);
                return;
            }
        }
    });

    // Cleanup on navigation — service handles session.end via close.
    window.addEventListener('pagehide', () => {
        _detachAllTracking();
        try { if (_domMutationObserver) _domMutationObserver.disconnect(); } catch {}
        try { if (socket) socket.close(); } catch {}
    });

    _connect();
})();
