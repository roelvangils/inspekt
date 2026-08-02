/**
 * Inspekt Overlay Bus — MAIN-world API stub.
 *
 * Defines window.InspektOverlayBus. Every method is a thin postMessage
 * wrapper that hands off to the isolated-world content script (overlay-bus.js)
 * which holds the WebSocket and observers.
 *
 * Rendering happens host-side (over the noVNC canvas) so the page DOM is
 * never mutated by overlay UI. See plan in
 * docs/development/overlay-bus.md (TBD).
 *
 * Injected into MAIN at tab-load by background.js (alongside
 * injectMainWorldVars), to bypass page CSP that would otherwise block
 * inline script in run_at=document_start manifest entries.
 *
 * The bus only exists when the producer transport is reachable; isolated-side
 * handshake sets window.__INSPEKT_OVERLAY_BUS_READY__ once connected, so
 * feature scripts (run_axe.js, inspect, recorder, …) can detect it via
 *   if (window.InspektOverlayBus && window.__INSPEKT_OVERLAY_BUS_READY__) { … }
 */
(function () {
    'use strict';
    if (window.InspektOverlayBus) return;

    const ORIGIN = location.origin;
    const PENDING_EVENT_HANDLERS = new Map();  // id -> Map<eventName, Set<cb>>
    let _ridSeq = 0;
    function _rid() { return 'ovb_' + (Date.now()) + '_' + (++_ridSeq); }

    function post(type, body) {
        try {
            window.postMessage(
                Object.assign({}, body, {
                    type: 'INSPEKT_OVERLAY_' + type,
                    source: 'inspekt-page',
                    requestId: body && body.requestId || _rid(),
                }),
                ORIGIN
            );
        } catch (e) {
            // Cross-origin frame or detached document — swallow.
        }
    }

    // Listen for messages flowing back from isolated → main:
    //   INSPEKT_OVERLAY_BUS_READY  — connection state (mirror to MAIN-world flag)
    //   INSPEKT_OVERLAY_EVENT      — consumer-originated click/focus/pointerenter
    window.addEventListener('message', (e) => {
        if (e.source !== window) return;
        const m = e.data;
        if (!m || m.source !== 'inspekt-overlay-isolated') return;
        if (m.type === 'INSPEKT_OVERLAY_BUS_READY') {
            window.__INSPEKT_OVERLAY_BUS_READY__ = !!m.ready;
            return;
        }
        if (m.type === 'INSPEKT_OVERLAY_EVENT') {
            const handlers = PENDING_EVENT_HANDLERS.get(m.id);
            if (!handlers) return;
            const set = handlers.get(m.event);
            if (!set) return;
            for (const cb of set) {
                try { cb(m.payload || {}, m); } catch (err) { console.error('[InspektOverlayBus] cb error', err); }
            }
        }
    });

    function _normalizeRect(rect) {
        if (!rect) return null;
        // Accept DOMRect or POJO with left/top/width/height.
        return {
            left:   +rect.left   || 0,
            top:    +rect.top    || 0,
            width:  +rect.width  || 0,
            height: +rect.height || 0,
        };
    }

    // ── MAIN-world element tracking ────────────────────────────────────────
    // For shadow-DOM targets we cannot pass a CSS selector across the
    // postMessage bridge; the isolated content script's `document.querySelector`
    // can't pierce shadow roots. So when a caller passes `opts.element`, we
    // own the observers here in MAIN-world and just forward rect updates as
    // postMessages. The isolated side flags the overlay as `_mainTracked` and
    // skips its own observer install.
    const _MAIN_TRACKED = new Map();        // id -> { el, ro, io, recompute }
    let _mainScrollAttached = false;

    function _recomputeAllMainTracked() {
        for (const [id, t] of Array.from(_MAIN_TRACKED.entries())) {
            if (!t || typeof t.recompute !== 'function') continue;
            t.recompute();
        }
    }

    function _ensureMainScrollListener() {
        if (_mainScrollAttached) return;
        _mainScrollAttached = true;
        window.addEventListener('scroll', _recomputeAllMainTracked, { capture: true, passive: true });
        window.addEventListener('resize', _recomputeAllMainTracked, { passive: true });
    }

    function _detachMainTracking(id) {
        const t = _MAIN_TRACKED.get(id);
        if (!t) return;
        try { if (t.ro) t.ro.disconnect(); } catch (_) {}
        try { if (t.io) t.io.disconnect(); } catch (_) {}
        _MAIN_TRACKED.delete(id);
    }

    function _attachMainTracking(id, el) {
        _detachMainTracking(id);
        const recompute = () => {
            if (!el || !el.isConnected) {
                post('CLEAR', { id });
                _detachMainTracking(id);
                return;
            }
            const r = el.getBoundingClientRect();
            post('UPDATE', { id, rect: _normalizeRect(r) });
        };
        let ro = null, io = null;
        try {
            ro = new ResizeObserver(recompute);
            ro.observe(el);
        } catch (_) {}
        try {
            io = new IntersectionObserver(recompute, { threshold: [0, 0.5, 1] });
            io.observe(el);
        } catch (_) {}
        _MAIN_TRACKED.set(id, { el, ro, io, recompute });
        _ensureMainScrollListener();
    }

    // The isolated content script may have already broadcast BUS_READY before
    // we registered our listener (it loads at document_start; we are injected
    // later via chrome.scripting from the background script). Ping it for the
    // current state so we don't miss the initial signal.
    post('PING', {});

    window.InspektOverlayBus = {
        /**
         * Create or replace an overlay.
         * @param {string} id     Stable id (e.g. 'axe:badge:3'). Re-emitting overwrites.
         * @param {string} kind   Renderer type: 'highlight' | 'badge' | 'tooltip' | 'popover' | …
         * @param {DOMRect|object} rect   {left,top,width,height} in page CSS px.
         * @param {object}  [payload]   Renderer-specific data.
         * @param {object}  [opts]      {interactive,track,events,anchor,selector,element,…}
         *
         * If `opts.element` is a live Element (used for shadow-DOM targets that
         * can't be expressed as a flat CSS selector), MAIN-world owns the
         * observers and only rect-update postMessages cross the bridge.
         */
        set(id, kind, rect, payload, opts) {
            const sid = String(id);
            let optsForWire = opts || null;
            if (opts && opts.element instanceof Element) {
                // Strip `element` (DOM nodes don't survive postMessage) and
                // flag the isolated side to skip its own selector-based tracker.
                optsForWire = Object.assign({}, opts, { _mainTracked: true });
                delete optsForWire.element;
                if (opts.track) {
                    _attachMainTracking(sid, opts.element);
                }
            }
            post('SET', {
                id: sid,
                kind: String(kind),
                rect: _normalizeRect(rect),
                payload: payload || null,
                opts: optsForWire,
            });
            return id;
        },

        /** Patch rect / payload of an existing overlay. */
        update(id, partial) {
            const body = { id: String(id) };
            if (partial && partial.rect) body.rect = _normalizeRect(partial.rect);
            if (partial && partial.payload) body.payload = partial.payload;
            if (partial && partial.opts) body.opts = partial.opts;
            post('UPDATE', body);
        },

        /** Remove a single overlay by id. */
        clear(id) {
            const sid = String(id);
            post('CLEAR', { id: sid });
            PENDING_EVENT_HANDLERS.delete(sid);
            _detachMainTracking(sid);
        },

        /** Remove all overlays whose id starts with `prefix`. */
        clearAll(prefix) {
            post('CLEAR_ALL', { prefix: prefix == null ? '' : String(prefix) });
            if (prefix == null || prefix === '') {
                PENDING_EVENT_HANDLERS.clear();
                for (const k of Array.from(_MAIN_TRACKED.keys())) _detachMainTracking(k);
            } else {
                for (const k of Array.from(PENDING_EVENT_HANDLERS.keys())) {
                    if (k.startsWith(prefix)) PENDING_EVENT_HANDLERS.delete(k);
                }
                for (const k of Array.from(_MAIN_TRACKED.keys())) {
                    if (k.startsWith(prefix)) _detachMainTracking(k);
                }
            }
        },

        /**
         * Track a live element by selector — isolated content script attaches
         * ResizeObserver/IntersectionObserver to push rect updates automatically.
         */
        track(id, selector, opts) {
            post('TRACK', {
                id: String(id),
                selector: String(selector),
                opts: opts || null,
            });
        },

        /**
         * Subscribe to events on an overlay. Currently: 'click', 'focus', 'pointerenter'.
         * Returns an unsubscribe function.
         */
        on(id, event, cb) {
            id = String(id);
            event = String(event);
            let byId = PENDING_EVENT_HANDLERS.get(id);
            if (!byId) { byId = new Map(); PENDING_EVENT_HANDLERS.set(id, byId); }
            let set = byId.get(event);
            if (!set) { set = new Set(); byId.set(event, set); }
            set.add(cb);
            return function off() {
                const _byId = PENDING_EVENT_HANDLERS.get(id);
                if (!_byId) return;
                const _set = _byId.get(event);
                if (!_set) return;
                _set.delete(cb);
                if (_set.size === 0) _byId.delete(event);
                if (_byId.size === 0) PENDING_EVENT_HANDLERS.delete(id);
            };
        },

        /**
         * Inspect-mode helper. Emits highlight + tooltip overlays for the
         * inspected element. Called from CDP Runtime.evaluate scripts in the
         * control server, so it lives here as a single install rather than
         * being re-templated into every evaluate payload.
         *
         * `persistent=true` enables producer observers (track:true) so subsequent
         * rect changes (scroll, resize) flow through the bus without polling.
         * No-op when the producer transport isn't ready.
         */
        _emitInspect(rect, selector, siblingIndex, siblingCount, persistent) {
            if (!window.__INSPEKT_OVERLAY_BUS_READY__) return;
            const opts = persistent ? { track: true, selector } : {};
            let tooltipText = selector || '';
            if (siblingIndex && siblingCount > 1) {
                tooltipText += ' (' + siblingIndex + '/' + siblingCount + ')';
            }
            tooltipText += ' • ' + Math.round(rect.width) + '×' + Math.round(rect.height);
            this.set('inspect:highlight', 'highlight', rect,
                { selector, siblingIndex, siblingCount }, opts);
            this.set('inspect:tooltip', 'tooltip', rect,
                { text: tooltipText }, opts);
        },

        /** Snapshot of overlays this page has currently emitted (best-effort). */
        snapshot() {
            // The authoritative registry lives in the isolated world; we ask it.
            return new Promise((resolve) => {
                const rid = _rid();
                function handler(e) {
                    if (e.source !== window) return;
                    const m = e.data;
                    if (!m || m.source !== 'inspekt-overlay-isolated') return;
                    if (m.type === 'INSPEKT_OVERLAY_SNAPSHOT_RESPONSE' && m.requestId === rid) {
                        window.removeEventListener('message', handler);
                        resolve(m.entries || []);
                    }
                }
                window.addEventListener('message', handler);
                post('SNAPSHOT', { requestId: rid });
                setTimeout(() => {
                    window.removeEventListener('message', handler);
                    resolve([]);
                }, 1000);
            });
        },
    };
})();
