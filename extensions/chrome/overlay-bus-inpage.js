/**
 * Inspekt Overlay Bus — in-page consumer (non-VM mode).
 *
 * Renders bus overlays into a shadow root attached to the inspected
 * page's <html>, so axe scans / screen readers / recorders walking the
 * page DOM don't see them. Same renderer factory the VM-mode host
 * consumer uses (extensions/chrome/overlay-bus-renderers.js), so adding
 * a kind once works in both modes.
 *
 * Loaded as a content script in the isolated world. The producer
 * (overlay-bus.js, also isolated) calls `__inspektOverlayInPageConsumer.dispatch(op)`
 * directly when the WS transport is unavailable — they share JS context
 * so no postMessage round-trip is needed for op delivery. Events flowing
 * the other way (overlay click → producer's bus.on callback) go through
 * the same INSPEKT_OVERLAY_EVENT postMessage envelope used in VM mode.
 *
 * v1 scope:
 *   * Kinds: highlight, tooltip, badge, outline, panel, pointer, region, backdrop
 *   * a11y-badge is NOT supported (popover-core uses document.getElementById,
 *     which can't reach into shadow DOM). Non-VM a11y rendering keeps using
 *     run_a11y.js's existing in-page DOM path until popover-core is made
 *     shadow-aware (separate refactor — tracked in
 *     docs/development/overlay-bus-consumers.md).
 */
(function () {
    'use strict';
    if (window.__inspektOverlayInPageConsumer__) return;

    // ---- Shadow root host -------------------------------------------------
    // Attach to <html>, NOT <body>, so:
    //   * page scripts that replace document.body (rare but real) don't kill us
    //   * page-traversal patterns that start at body don't see our root
    // Mode 'open' so devtools can inspect — the data-inspekt-overlay-host
    // attribute is the canonical exclude marker for axe/scan code.
    let _shadowRoot = null;
    let _container = null;

    function _ensureShadowRoot() {
        if (_shadowRoot) return _shadowRoot;
        const host = document.createElement('div');
        // data-inspekt-overlay-host is the canonical exclude marker — see
        // engine-tracker.js's __inspektUISelectors__ list. Anything Inspekt
        // injects that should NOT show up in scans gets this attribute.
        host.setAttribute('data-inspekt-overlay-host', '');
        // Inspekt's overlays should not appear in the user's accessibility
        // testing — the whole point of the bus is keeping our UI out of
        // their a11y / SR / recorder output. aria-hidden=true ensures
        // assistive tech ignores everything inside this subtree. The
        // tradeoff: a developer running Inspekt while themselves using
        // AT can't interact with our overlays via AT in non-VM mode.
        // Acceptable for v1; revisit if it becomes a real limitation.
        host.setAttribute('aria-hidden', 'true');
        // Don't take any layout space. Children are absolute-positioned.
        host.style.cssText = 'position:fixed; top:0; left:0; width:0; height:0; z-index:2147483647; pointer-events:none;';
        document.documentElement.appendChild(host);
        _shadowRoot = host.attachShadow({ mode: 'open' });

        // Inline the styles we need for v1 kinds. The host control panel
        // pulls these from /css/overlay-bus.css + /css/vnc.css, but the
        // shadow root needs them inline (CSS @import behind chrome-extension://
        // URLs is gnarly to support; simpler to ship the styles with the JS).
        const style = document.createElement('style');
        style.textContent = INPAGE_CSS;
        _shadowRoot.appendChild(style);

        // The "container" is the element we append all overlays to.
        _container = document.createElement('div');
        _container.id = 'overlay-bus-container';
        // The container itself takes no layout space — children position
        // absolutely against the viewport via fixed positioning.
        _container.style.cssText = 'position:fixed; top:0; left:0; width:100vw; height:100vh; pointer-events:none; overflow:visible;';
        _shadowRoot.appendChild(_container);
        return _shadowRoot;
    }

    // CSS that lives inside the shadow root.
    //
    // INTENTIONALLY DUPLICATES vm/css/overlay-bus.css + the relevant slice
    // of vm/css/vnc.css (.vnc-overlay-highlight, .vnc-overlay-tooltip).
    // The control panel can `<link>` external stylesheets; this consumer
    // can't fetch them via @import without web_accessible_resources +
    // chrome-extension:// origin acrobatics, so we ship the styles inline
    // with the JS. Keep the two sources in sync when adding/changing
    // visual properties of a kind. Behavior-only renderer changes don't
    // need to touch this string.
    //
    // v1 covers the generic kinds; a11y-badge is skipped (see header).
    const INPAGE_CSS = `
        /* Reset to make styling predictable inside the shadow root */
        * { box-sizing: border-box; }

        :host { all: initial; }

        #overlay-bus-container > * {
            position: absolute;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }

        /* Highlight */
        .vnc-overlay-highlight, .bus-overlay-highlight {
            border: 2px solid #2563eb;
            background: rgba(37, 99, 235, 0.08);
            border-radius: 1px;
            transition: left .15s, top .15s, width .15s, height .15s;
            pointer-events: none;
        }

        /* Tooltip */
        .vnc-overlay-tooltip, .bus-overlay-tooltip {
            background: linear-gradient(135deg, #2563eb, #1e40af);
            color: #fff;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            line-height: 1.4;
            white-space: nowrap;
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            pointer-events: none;
        }

        /* Badge */
        .bus-overlay-badge {
            width: 32px; height: 32px;
            border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: 13px; font-weight: bold; color: #fff;
            box-shadow: 0 2px 4px rgba(0,0,0,0.4);
            border: 2px solid #fff;
            user-select: none;
            line-height: 1;
            pointer-events: auto;
            cursor: pointer;
            transition: transform .15s, box-shadow .15s;
        }
        .bus-overlay-badge:hover { transform: scale(1.1); box-shadow: 0 3px 6px rgba(0,0,0,0.5); }
        .bus-overlay-badge--critical { background: #dc2626; }
        .bus-overlay-badge--serious  { background: #ea580c; }
        .bus-overlay-badge--moderate { background: #2563eb; }
        .bus-overlay-badge--minor    { background: #6b7280; }

        /* Outline */
        .bus-overlay-outline { border-radius: 2px; }
        .bus-overlay-outline__label {
            position: absolute; top: -22px; left: -2px;
            padding: 2px 8px; background: #2563eb; color: #fff;
            font-size: 10px; font-weight: 600; border-radius: 3px;
            white-space: nowrap; pointer-events: none;
        }

        /* Panel */
        .bus-overlay-panel {
            background: rgba(31,31,41,0.96); color: #fff;
            border: 1px solid rgba(255,255,255,0.12);
            border-radius: 10px;
            box-shadow: 0 18px 60px rgba(0,0,0,0.45), 0 6px 18px rgba(0,0,0,0.25);
            backdrop-filter: blur(18px) saturate(180%);
            -webkit-backdrop-filter: blur(18px) saturate(180%);
            font-size: 13px; line-height: 1.5;
            overflow: auto;
            pointer-events: auto;
        }
        .bus-overlay-panel__header {
            display: flex; align-items: center; justify-content: space-between;
            padding: 10px 14px;
            background: rgba(0,0,0,0.25);
            border-bottom: 1px solid rgba(255,255,255,0.08);
            position: sticky; top: 0; z-index: 1;
        }
        .bus-overlay-panel__title { font-weight: 600; font-size: 13px; }
        .bus-overlay-panel__close {
            width: 24px; height: 24px; border-radius: 50%; border: 0;
            background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.85);
            font-size: 18px; line-height: 1; cursor: pointer;
            display: inline-flex; align-items: center; justify-content: center;
        }
        .bus-overlay-panel__close:hover { background: rgba(239,68,68,0.3); color: #fff; }
        .bus-overlay-panel__body { padding: 12px 14px; }

        /* Pointer */
        .bus-overlay-pointer {
            border-radius: 50%;
            border: 2px solid #2563eb;
            box-sizing: border-box;
            pointer-events: none;
        }
        .bus-overlay-pointer--click {
            animation: ovb-click 600ms ease-out forwards;
        }
        .bus-overlay-pointer--pulse {
            animation: ovb-pulse 1.2s ease-in-out infinite;
        }
        .bus-overlay-pointer--cursor { background: #2563eb; opacity: 0.6; }
        @keyframes ovb-click {
            0%   { transform: scale(0.4); opacity: 0.9; }
            100% { transform: scale(1.6); opacity: 0;   }
        }
        @keyframes ovb-pulse {
            0%, 100% { transform: scale(0.95); opacity: 0.5; }
            50%      { transform: scale(1.15); opacity: 1;   }
        }

        /* Region (spotlight) */
        .bus-overlay-region { pointer-events: none; }
        .bus-overlay-region__label {
            position: absolute; bottom: -32px; left: 50%; transform: translateX(-50%);
            padding: 4px 12px;
            background: rgba(31,31,41,0.96); color: #fff;
            border-radius: 4px;
            font-size: 12px; font-weight: 500; white-space: nowrap;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }

        /* Backdrop */
        .bus-overlay-backdrop { /* color/opacity from inline style */ }

        /* Unknown fallback */
        .bus-overlay-unknown { outline: 2px dashed magenta; background: transparent; }
    `;

    // ---- vncOverlay shim --------------------------------------------------
    // Mirrors the API of vm/js/vnc-overlay.js's `vncOverlay` so the shared
    // renderer factory works unchanged. State is per-shadow-root.
    function _makeVncOverlayShim() {
        const overlays = Object.create(null);

        function ensureContainer() { _ensureShadowRoot(); return _container; }

        return {
            _overlays: overlays,
            _ensureContainer: ensureContainer,
            isVisible(id) { return !!overlays[id]; },
            getElement(id) { return overlays[id] ? overlays[id].element : null; },
            show(id, rect, options) {
                ensureContainer();
                if (overlays[id]) this.dismiss(id, false);
                const el = document.createElement('div');
                el.dataset.overlayId = id;
                el.style.position = 'absolute';
                el.style.pointerEvents = 'none';
                _container.appendChild(el);
                overlays[id] = { element: el };
                if (rect) {
                    if (rect.left   != null) el.style.left   = rect.left   + 'px';
                    if (rect.top    != null) el.style.top    = rect.top    + 'px';
                    if (rect.width  != null) el.style.width  = rect.width  + 'px';
                    if (rect.height != null) el.style.height = rect.height + 'px';
                }
                const opts = options || {};
                if (opts.text !== undefined) el.textContent = opts.text;
                else if (opts.html !== undefined) el.innerHTML = opts.html;
                if (opts.className) el.className = opts.className;
                if (opts.style) Object.assign(el.style, opts.style);
                el.style.display = 'block';
                return el;
            },
            update(id, rect) {
                const e = overlays[id]; if (!e) return;
                const el = e.element;
                if (rect.left   != null) el.style.left   = rect.left   + 'px';
                if (rect.top    != null) el.style.top    = rect.top    + 'px';
                if (rect.width  != null) el.style.width  = rect.width  + 'px';
                if (rect.height != null) el.style.height = rect.height + 'px';
            },
            setContent(id, contentObj) {
                const e = overlays[id]; if (!e) return null;
                if (!contentObj) return e.element;
                if (contentObj.text !== undefined) e.element.textContent = contentObj.text;
                else if (contentObj.html !== undefined) e.element.innerHTML = contentObj.html;
                return e.element;
            },
            setStyle(id, styleObj) {
                const e = overlays[id]; if (!e || !styleObj) return null;
                Object.assign(e.element.style, styleObj);
                return e.element;
            },
            dismiss(id, animate) {
                const e = overlays[id]; if (!e) return;
                const el = e.element;
                delete overlays[id];
                if (animate) {
                    el.style.transition = 'opacity .15s ease';
                    el.style.opacity = '0';
                    setTimeout(() => el.remove(), 150);
                } else {
                    el.remove();
                }
            },
            dismissAll(animate) {
                for (const id of Object.keys(overlays)) this.dismiss(id, animate);
            },
        };
    }

    // ---- Build registry on demand -----------------------------------------
    let _registry = null;
    function _getRegistry() {
        if (_registry) return _registry;
        if (!window.__inspektCreateOverlayRenderers__) {
            console.error('[overlay-bus-inpage] renderer factory not loaded — script order error');
            return null;
        }
        const shim = _makeVncOverlayShim();
        _registry = window.__inspektCreateOverlayRenderers__({
            vncOverlay: shim,
            // Identity transform: the producer is in the same page, so its
            // page CSS px IS our render CSS px. No canvas scaling.
            transformRect: (r) => r,
            // a11y-badge intentionally not registered: popoverCore +
            // popoverContent absent → factory skips that kind. v1 leaves
            // run_a11y.js's in-page DOM path untouched for non-VM users.
            popoverCore: null,
            popoverContent: null,
            sendEvent: (sessionId, id, event, payload) => {
                // Producer (overlay-bus.js) listens for postMessage with
                // source 'inspekt-overlay-isolated' and forwards the event
                // to the registered bus.on callback in MAIN. Same envelope
                // shape used by the VM-mode WS path.
                window.postMessage({
                    source: 'inspekt-overlay-isolated',
                    type: 'INSPEKT_OVERLAY_EVENT',
                    sessionId, id, event,
                    payload: payload || {},
                }, location.origin);
            },
            containerRoot: document.documentElement,
        });
        return _registry;
    }

    // ---- State + dispatch -------------------------------------------------
    // Same shape as the host consumer's per-session state, scoped to one
    // page (we never have multiple producer sessions in non-VM mode).
    const SESSIONS = new Map(); // sessionId -> Map<id, entry>

    function _getOrCreateSession(sessionId) {
        let s = SESSIONS.get(sessionId);
        if (!s) { s = new Map(); SESSIONS.set(sessionId, s); }
        return s;
    }

    function _applySet(sessionId, op) {
        const id = op.id; if (typeof id !== 'string') return;
        const reg = _getRegistry(); if (!reg) return;
        const session = _getOrCreateSession(sessionId);
        const entry = {
            id, kind: op.kind || 'unknown',
            rect: op.rect || null,
            payload: op.payload || null,
            opts: op.opts || null,
        };
        const prev = session.get(id);
        if (prev && prev.kind !== entry.kind) reg.rendererFor(prev.kind).remove(id, sessionId, prev);
        session.set(id, entry);
        try { reg.rendererFor(entry.kind).render(id, sessionId, entry); }
        catch (e) { console.error('[overlay-bus-inpage] render', e); }
    }

    function _applyUpdate(sessionId, op) {
        const id = op.id; if (typeof id !== 'string') return;
        const reg = _getRegistry(); if (!reg) return;
        const session = SESSIONS.get(sessionId); if (!session) return;
        const entry = session.get(id); if (!entry) return;
        if (op.rect) entry.rect = op.rect;
        if (op.payload) entry.payload = Object.assign({}, entry.payload, op.payload);
        if (op.opts) entry.opts = Object.assign({}, entry.opts, op.opts);
        try { reg.rendererFor(entry.kind).render(id, sessionId, entry); }
        catch (e) { console.error('[overlay-bus-inpage] re-render', e); }
    }

    function _applyClear(sessionId, op) {
        const id = op.id; if (typeof id !== 'string') return;
        const reg = _getRegistry(); if (!reg) return;
        const session = SESSIONS.get(sessionId); if (!session) return;
        const entry = session.get(id); if (!entry) return;
        session.delete(id);
        try { reg.rendererFor(entry.kind).remove(id, sessionId, entry); }
        catch (e) { console.error('[overlay-bus-inpage] remove', e); }
    }

    function dispatch(op) {
        if (!op || typeof op !== 'object') return;
        const t = op.type;
        // sessionId is informational in non-VM (one page = one session) but
        // we still thread it through so renderer ids namespace correctly.
        const sid = op.sessionId || 'inpage:0';
        switch (t) {
            case 'overlay.set':    _applySet(sid, op);    return;
            case 'overlay.update': _applyUpdate(sid, op); return;
            case 'overlay.clear':  _applyClear(sid, op);  return;
            case 'overlay.batch': {
                for (const child of (op.ops || [])) {
                    if (!child || !child.type) continue;
                    if (child.type === 'overlay.set')    _applySet(sid, child);
                    else if (child.type === 'overlay.update') _applyUpdate(sid, child);
                    else if (child.type === 'overlay.clear')  _applyClear(sid, child);
                }
                return;
            }
            // session.start / session.end / snapshot are server-lifecycle
            // messages that don't reach an in-page consumer (no server in
            // this mode, one page = one session). Producer dispatches
            // overlay.set/update/clear/batch only.
        }
    }

    // ---- Public surface ---------------------------------------------------
    window.__inspektOverlayInPageConsumer__ = {
        connected: true,
        dispatch,
        // Producer can call this to verify the consumer is alive without
        // round-tripping through postMessage.
        ping() { return true; },
    };
})();
