/**
 * Inspekt Overlay Bus — host-side consumer.
 *
 * WebSocket client to the in-VM overlay-bus server (port 8890). Receives
 * overlay data emitted by Chromium-side producers (extension content
 * script via window.InspektOverlayBus) and renders it on top of the noVNC
 * canvas via vncOverlay + _vmRectToOverlayRect.
 *
 * No DOM is mutated inside the page — that is the whole point of this
 * subsystem. See architecture in docs/development/overlay-bus.md (TBD).
 *
 * Globals consumed:
 *   VNC_HOST, vncOverlay, _vmRectToOverlayRect (from vnc-overlay.js)
 *
 * Globals exposed:
 *   overlayBus — { state, dispatch(msg), getEntries(sessionId) }
 */

(function () {
    'use strict';

    if (typeof vncOverlay === 'undefined') {
        console.error('[overlay-bus] vncOverlay not loaded yet — script order error');
        return;
    }

    // detectPort + VNC_HOST come from config.js; same shape as CONTROL_PORT/TERMINAL_PORT.
    const OVERLAY_BUS_PORT = detectPort('overlay_bus_port', 8890, 890);

    const RECONNECT_BASE_MS = 250;
    const RECONNECT_MAX_MS = 5000;
    const PROTOCOL_VERSION = 1;

    // sessionId -> Map<id, {kind, rect, payload, opts}>
    const SESSIONS = new Map();

    let socket = null;
    let connectAttempts = 0;
    let reconnectTimer = null;

    // ---- Renderers ---------------------------------------------------------
    // Per-kind renderers live in extensions/chrome/overlay-bus-renderers.js
    // (single source of truth, also loaded by the in-page consumer for
    // non-VM mode). The host shell here just provides the env: the existing
    // global vncOverlay primitive + the canvas-aware rect transform.
    if (!window.__inspektCreateOverlayRenderers__) {
        console.error('[overlay-bus] overlay-bus-renderers.js not loaded — script order error');
        return;
    }
    const _renderers = window.__inspektCreateOverlayRenderers__({
        vncOverlay: vncOverlay,
        transformRect: _vmRectToOverlayRect,
        popoverCore: window.__inspektPopoverCore__ || null,
        popoverContent: window.__inspektPopoverContent__ || null,
        sendEvent: function (sessionId, id, event, payload) {
            // Defined later in this file via window.overlayBus.sendEvent;
            // forward through that so events flow over the WS.
            if (window.overlayBus && window.overlayBus.sendEvent) {
                window.overlayBus.sendEvent(sessionId, id, event, payload);
            }
        },
        containerRoot: document.getElementById('vncContainer'),
    });
    const _rendererFor = _renderers.rendererFor;


    // ---- State + dispatch --------------------------------------------------

    function _getOrCreateSession(sessionId) {
        let s = SESSIONS.get(sessionId);
        if (!s) {
            s = new Map();
            SESSIONS.set(sessionId, s);
        }
        return s;
    }

    function _applySet(sessionId, op) {
        const id = op.id;
        if (typeof id !== 'string') return;
        const session = _getOrCreateSession(sessionId);
        const entry = {
            id,
            kind: op.kind || 'unknown',
            rect: op.rect || null,
            payload: op.payload || null,
            opts: op.opts || null,
        };
        // If kind changed, remove old renderer's overlay first so we don't
        // leak DOM from a previous renderer.
        const prev = session.get(id);
        if (prev && prev.kind !== entry.kind) {
            _rendererFor(prev.kind).remove(id, sessionId, prev);
        }
        session.set(id, entry);
        try {
            _rendererFor(entry.kind).render(id, sessionId, entry);
        } catch (e) {
            console.error('[overlay-bus] render failed:', e);
        }
    }

    function _applyUpdate(sessionId, op) {
        const id = op.id;
        if (typeof id !== 'string') return;
        const session = SESSIONS.get(sessionId);
        if (!session) return;
        const entry = session.get(id);
        if (!entry) return;
        if (op.rect) entry.rect = op.rect;
        if (op.payload) entry.payload = Object.assign({}, entry.payload, op.payload);
        if (op.opts) entry.opts = Object.assign({}, entry.opts, op.opts);
        try {
            _rendererFor(entry.kind).render(id, sessionId, entry);
        } catch (e) {
            console.error('[overlay-bus] re-render failed:', e);
        }
    }

    function _applyClear(sessionId, op) {
        const id = op.id;
        if (typeof id !== 'string') return;
        const session = SESSIONS.get(sessionId);
        if (!session) return;
        const entry = session.get(id);
        if (!entry) return;
        session.delete(id);
        try {
            _rendererFor(entry.kind).remove(id, sessionId, entry);
        } catch (e) {
            console.error('[overlay-bus] remove failed:', e);
        }
    }

    function _endSession(sessionId, reason) {
        const session = SESSIONS.get(sessionId);
        if (!session) return;
        // Animate dismiss — use vncOverlay.dismiss(animate=true) per renderer.
        for (const [id, entry] of session.entries()) {
            try {
                _rendererFor(entry.kind).remove(id, sessionId, entry);
            } catch (e) {
                console.error('[overlay-bus] session-end remove failed:', e);
            }
        }
        SESSIONS.delete(sessionId);
        if (reason) console.debug('[overlay-bus] session end:', sessionId, reason);
    }

    function _applySnapshot(sessionId, entries) {
        // Replace the session entirely. Anything we had locally that isn't in
        // the snapshot is removed.
        const session = SESSIONS.get(sessionId);
        if (session) {
            for (const [id, entry] of session.entries()) {
                _rendererFor(entry.kind).remove(id, sessionId, entry);
            }
            SESSIONS.delete(sessionId);
        }
        for (const e of entries) {
            _applySet(sessionId, {
                type: 'overlay.set',
                id: e.id,
                kind: e.kind,
                rect: e.rect,
                payload: e.payload,
                opts: e.opts,
            });
        }
    }

    function dispatch(msg) {
        if (!msg || typeof msg !== 'object') return;
        const t = msg.type;
        const sid = msg.sessionId;
        if (typeof sid !== 'string') return;
        switch (t) {
            case 'overlay.set':    _applySet(sid, msg); return;
            case 'overlay.update': _applyUpdate(sid, msg); return;
            case 'overlay.clear':  _applyClear(sid, msg); return;
            case 'overlay.batch': {
                const ops = Array.isArray(msg.ops) ? msg.ops : [];
                for (const op of ops) {
                    op.sessionId = sid;
                    if (op.type === 'overlay.set')    _applySet(sid, op);
                    else if (op.type === 'overlay.update') _applyUpdate(sid, op);
                    else if (op.type === 'overlay.clear')  _applyClear(sid, op);
                }
                return;
            }
            case 'overlay.snapshot':
                _applySnapshot(sid, Array.isArray(msg.entries) ? msg.entries : []);
                return;
            case 'overlay.session.start':
                // No-op locally; we lazily create state on first set.
                return;
            case 'overlay.session.end':
                _endSession(sid, msg.reason || '');
                return;
            case 'overlay.suppress': {
                // Producer detected scroll/resize; the canvas pixel stream
                // will lag the DOM overlays for ~150 ms. CSS blurs + dims
                // everything except detached popovers until unsuppress.
                const c = vncOverlay._ensureContainer();
                if (c) c.classList.add('bus-scrolling');
                return;
            }
            case 'overlay.unsuppress': {
                const c = vncOverlay._ensureContainer();
                if (c) c.classList.remove('bus-scrolling');
                return;
            }
        }
    }

    // ---- Connection management --------------------------------------------

    function _wsUrl() {
        return `ws://${VNC_HOST}:${OVERLAY_BUS_PORT}/overlay/ws?role=consumer`;
    }

    function _connect() {
        if (socket) return;
        try {
            socket = new WebSocket(_wsUrl());
        } catch {
            _scheduleReconnect();
            return;
        }
        socket.addEventListener('open', () => {
            connectAttempts = 0;
            console.log('[overlay-bus] consumer connected');
        });
        socket.addEventListener('close', () => {
            socket = null;
            // Sessions stay; the server will resend snapshots on reconnect.
            _scheduleReconnect();
        });
        socket.addEventListener('error', () => {
            // 'close' will follow.
        });
        socket.addEventListener('message', (e) => {
            let msg;
            try { msg = JSON.parse(e.data); } catch { return; }
            dispatch(msg);
        });
    }

    function _scheduleReconnect() {
        if (reconnectTimer) return;
        const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, connectAttempts), RECONNECT_MAX_MS);
        connectAttempts++;
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            _connect();
        }, delay);
    }

    // Reposition all entries when the canvas resizes / scales / letterboxes
    // change. Without this, the overlay positions drift relative to the page
    // when the user resizes the host window.
    function _repositionAll() {
        for (const [sessionId, session] of SESSIONS.entries()) {
            for (const [id, entry] of session.entries()) {
                try { _rendererFor(entry.kind).render(id, sessionId, entry); } catch {}
            }
        }
    }
    window.addEventListener('resize', _repositionAll);

    // ---- Public API --------------------------------------------------------
    window.overlayBus = {
        get connected() { return !!(socket && socket.readyState === WebSocket.OPEN); },
        dispatch,
        sessions: SESSIONS,
        repositionAll: _repositionAll,
        // Re-export the factory's registerRenderer so feature scripts can
        // register a custom kind on a running consumer without touching the
        // factory file. Forward into the closed-over registry.
        registerRenderer: _renderers.registerRenderer,
        // Send a consumer→producer event (used by interactive overlays in Phase 6).
        sendEvent(sessionId, id, event, payload) {
            if (!socket || socket.readyState !== WebSocket.OPEN) return;
            try {
                socket.send(JSON.stringify({
                    v: PROTOCOL_VERSION,
                    type: 'overlay.event',
                    sessionId,
                    id,
                    event,
                    payload: payload || {},
                }));
            } catch {}
        },
    };

    _connect();
})();
