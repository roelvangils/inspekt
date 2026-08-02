/**
 * Inspekt Overlay Bus — shared renderer factory.
 *
 * Single source of truth for kind→renderer logic. Loaded by BOTH:
 *   • the VM-mode host consumer (vm/js/overlay-bus.js) — renders over the
 *     noVNC canvas
 *   • the non-VM in-page consumer (extensions/chrome/overlay-bus-inpage.js)
 *     — renders into a shadow DOM attached to the inspected page
 *
 * Adding a new visual element to Inspekt is "add a kind here", not "find
 * the place that injects DOM and copy it again."
 *
 * Exposes a single global:
 *   window.__inspektCreateOverlayRenderers__(env) → { rendererFor, wireInteractive, registerRenderer }
 *
 * `env` provides the host-context-specific pieces:
 *   - vncOverlay        — overlay primitive { show, update, dismiss, isVisible, getElement, setStyle, setContent, _ensureContainer, _overlays }
 *   - transformRect(r)  — page CSS px → host CSS px (identity in non-VM, canvas-aware in VM)
 *   - sendEvent(sessionId, id, event, payload)  — round-trip events to the producer
 *   - popoverCore?      — window.__inspektPopoverCore__ (a11y-badge only)
 *   - popoverContent?   — window.__inspektPopoverContent__ (a11y-badge only)
 *   - containerRoot?    — element for measuring viewport (default: document.documentElement)
 *
 * Each renderer must be idempotent: re-rendering the same entry must not
 * duplicate DOM. Renderers receive entry = { kind, rect, payload, opts }.
 */
(function () {
    'use strict';
    if (window.__inspektCreateOverlayRenderers__) return;

    function _escape(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    window.__inspektCreateOverlayRenderers__ = function (env) {
        const vncOverlay = env.vncOverlay;
        const transformRect = env.transformRect || ((r) => r);
        const popoverCore = env.popoverCore || null;
        const popoverContent = env.popoverContent || null;
        const sendEvent = env.sendEvent || function () {};
        const containerRoot = env.containerRoot || document.documentElement;

        if (!vncOverlay) throw new Error('overlay-bus-renderers: env.vncOverlay required');

        const RENDERERS = Object.create(null);

        function _domId(sessionId, id) {
            return 'bus:' + sessionId + ':' + id;
        }

        // ---- Highlight kind ------------------------------------------------
        RENDERERS.highlight = {
            render(id, sessionId, entry) {
                const r = entry.rect ? transformRect(entry.rect) : null;
                const oid = _domId(sessionId, id);
                const payload = entry.payload || {};
                const className = 'vnc-overlay-highlight bus-overlay' +
                    (payload.className ? (' ' + payload.className) : '');
                if (vncOverlay.isVisible(oid)) {
                    vncOverlay.update(oid, r || {});
                } else {
                    vncOverlay.show(oid, r, { className });
                }
            },
            remove(id, sessionId) {
                vncOverlay.dismiss(_domId(sessionId, id), true);
            },
        };

        // ---- Generic Badge kind --------------------------------------------
        const BADGE_SIZE = 32;
        const BADGE_OFFSET = -16;

        RENDERERS.badge = {
            render(id, sessionId, entry) {
                const r = entry.rect ? transformRect(entry.rect) : null;
                if (!r) return;
                const oid = _domId(sessionId, id);
                const payload = entry.payload || {};
                const opts = entry.opts || {};
                const impact = (payload.impact || 'minor').toString().toLowerCase();
                const text = payload.text != null ? String(payload.text) : '';
                const className =
                    'bus-overlay bus-overlay-badge bus-overlay-badge--' + impact;
                const offsetX = payload.offsetX != null ? +payload.offsetX : 0;
                const badgeRect = {
                    left: r.left + BADGE_OFFSET + offsetX,
                    top:  r.top  + BADGE_OFFSET,
                    width: BADGE_SIZE,
                    height: BADGE_SIZE,
                };
                if (vncOverlay.isVisible(oid)) {
                    vncOverlay.update(oid, badgeRect);
                    const el = vncOverlay.getElement && vncOverlay.getElement(oid);
                    if (el) el.textContent = text;
                } else {
                    vncOverlay.show(oid, badgeRect, { className, text });
                    if (opts.interactive) {
                        wireInteractive(oid, sessionId, id, opts.events || ['click']);
                    }
                }
            },
            remove(id, sessionId) {
                vncOverlay.dismiss(_domId(sessionId, id), true);
            },
        };

        // ---- Tooltip kind --------------------------------------------------
        RENDERERS.tooltip = {
            render(id, sessionId, entry) {
                const r = entry.rect ? transformRect(entry.rect) : null;
                if (!r) return;
                const oid = _domId(sessionId, id);
                const payload = entry.payload || {};
                const text = payload.text != null ? String(payload.text) : '';
                const tooltipTop = r.top >= 28 ? r.top - 28 : r.top + r.height + 4;
                const tooltipLeft = Math.max(0, r.left);
                const tooltipRect = { left: tooltipLeft, top: tooltipTop };
                const className = 'bus-overlay bus-overlay-tooltip vnc-overlay-tooltip';
                if (vncOverlay.isVisible(oid)) {
                    const el = vncOverlay.getElement && vncOverlay.getElement(oid);
                    if (el) {
                        el.style.left = tooltipLeft + 'px';
                        el.style.top  = tooltipTop  + 'px';
                        el.textContent = text;
                    }
                } else {
                    vncOverlay.show(oid, tooltipRect, {
                        className, text,
                        style: { width: 'auto', height: 'auto' },
                    });
                }
            },
            remove(id, sessionId) {
                vncOverlay.dismiss(_domId(sessionId, id), true);
            },
        };

        // ---- a11y-badge kind (full unified popover via shared modules) ----
        // Only registered when popoverCore + popoverContent are available
        // (host-side). In-page consumer skips this kind in v1 because the
        // popover modules use document.getElementById to wire badges to
        // popovers — that lookup doesn't pierce shadow boundaries, so it
        // would silently break inside the in-page consumer's shadow root.
        // Non-VM a11y rendering keeps using run_a11y.js's in-page DOM path
        // until popover-core is made shadow-aware (separate refactor).
        if (popoverCore && popoverContent) {
            const _a11yResetSessions = new Set();

            function _ensureA11ySession(sessionId, engines) {
                if (_a11yResetSessions.has(sessionId)) return;
                _a11yResetSessions.add(sessionId);
                if (Array.isArray(engines)) popoverCore.reset(engines);
                document.querySelectorAll(
                    '#vncOverlayContainer .inspekt-badge, #vncOverlayContainer [popover].inspekt-axe-popover'
                ).forEach(el => el.remove());
            }
            function _badgeClassFor(v) {
                const impact = (v.isRecommendation ? 'minor' : (v.highestImpact || 'minor')).toLowerCase();
                let cls = 'inspekt-badge inspekt-badge--' + impact;
                const activeCount = v.hasEngine ? Object.values(v.hasEngine).filter(Boolean).length : 0;
                if (activeCount > 1) cls += ' inspekt-badge--combined';
                return cls;
            }
            function _badgeTitleFor(v, engines) {
                const issueType = v.isRecommendation ? 'recommendation' : 'issue';
                const NAMES = { axe:'axe-core', eac:'IBM Equal Access', hcs:'HTML CodeSniffer', sia:'Siteimprove Alfa' };
                const parts = (engines || []).filter(e => v.hasEngine && v.hasEngine[e])
                    .map(e => `${NAMES[e] || e}: ${(v.engineCounts || {})[e] || 0}`);
                const total = v.totalCount || 0;
                return `${total} ${issueType}${total === 1 ? '' : 's'} (${parts.join(', ')})`;
            }

            RENDERERS['a11y-badge'] = {
                render(id, sessionId, entry) {
                    const payload = entry.payload || {};
                    const violation = payload.violation;
                    const engines = payload.engines || [];
                    const badgeNumber = payload.badgeNumber || 1;
                    if (!violation) return;
                    _ensureA11ySession(sessionId, engines);
                    const container = vncOverlay._ensureContainer
                        ? vncOverlay._ensureContainer()
                        : document.getElementById('vncOverlayContainer');
                    const r = entry.rect ? transformRect(entry.rect) : null;
                    if (!r) return;
                    let badge = document.getElementById(violation.badgeId);
                    if (badge) {
                        badge.style.left = (r.left - 16) + 'px';
                        badge.style.top  = (r.top  - 16) + 'px';
                        return;
                    }
                    badge = document.createElement('button');
                    badge.type = 'button';
                    badge.id = violation.badgeId;
                    badge.setAttribute('data-inspekt-badge', String(badgeNumber));
                    badge.className = _badgeClassFor(violation);
                    badge.innerHTML = `<span class="inspekt-badge__text">${badgeNumber}</span>`;
                    badge.title = _badgeTitleFor(violation, engines);
                    badge.setAttribute('popovertarget', violation.popoverId);
                    badge.setAttribute('style',
                        `anchor-name: --badge-${badgeNumber}; left: ${r.left - 16}px; top: ${r.top - 16}px;`);
                    container.appendChild(badge);
                    const popover = popoverContent.createUnifiedPopover(violation, badgeNumber, engines, popoverCore);
                    container.appendChild(popover);
                    popoverCore.addViolation({ ...violation, element: badge });
                },
                remove(id, sessionId, entry) {
                    const v = (entry && entry.payload || {}).violation;
                    if (!v) return;
                    const badge = document.getElementById(v.badgeId);
                    if (badge) badge.remove();
                    const popover = document.getElementById(v.popoverId);
                    if (popover) popover.remove();
                },
            };
        }

        // ---- Outline kind --------------------------------------------------
        RENDERERS.outline = {
            render(id, sessionId, entry) {
                const r = entry.rect ? transformRect(entry.rect) : null;
                if (!r) return;
                const oid = _domId(sessionId, id);
                const payload = entry.payload || {};
                const color = payload.color || 'var(--accent, #2563eb)';
                const borderStyle = payload.style === 'dashed' ? 'dashed' : 'solid';
                const className = 'bus-overlay bus-overlay-outline ' +
                    (payload.style === 'dashed' ? 'bus-overlay-outline--dashed' : 'bus-overlay-outline--solid') +
                    (payload.className ? (' ' + payload.className) : '');
                const styleObj = {
                    background: 'transparent',
                    border: '2px ' + borderStyle + ' ' + color,
                    borderRadius: '2px',
                    pointerEvents: 'none',
                };
                const html = payload.label
                    ? '<span class="bus-overlay-outline__label">' + _escape(payload.label) + '</span>'
                    : '';
                if (vncOverlay.isVisible(oid)) {
                    vncOverlay.update(oid, r);
                    if (payload.label != null) vncOverlay.setContent(oid, { html });
                } else {
                    vncOverlay.show(oid, r, { className, html, style: styleObj });
                }
            },
            remove(id, sessionId) { vncOverlay.dismiss(_domId(sessionId, id), true); },
        };

        // ---- Panel kind ----------------------------------------------------
        const PANEL_DEFAULTS = { width: 360, maxHeight: 400, margin: 12 };

        function _panelPosition(rect, position) {
            const cw = containerRoot.clientWidth || window.innerWidth;
            const ch = containerRoot.clientHeight || window.innerHeight;
            const w  = PANEL_DEFAULTS.width;
            const m  = PANEL_DEFAULTS.margin;
            if (rect) {
                const r = transformRect(rect);
                return {
                    left: Math.min(cw - w - m, Math.max(m, r.left + r.width + m)),
                    top:  Math.min(ch - 64,    Math.max(m, r.top)),
                    width: w,
                };
            }
            const corner = position || 'top-right';
            const top  = corner.startsWith('top') ? m : ch - PANEL_DEFAULTS.maxHeight - m;
            const left = corner.endsWith('right') ? cw - w - m : m;
            return { left, top, width: w };
        }

        RENDERERS.panel = {
            render(id, sessionId, entry) {
                const oid = _domId(sessionId, id);
                const payload = entry.payload || {};
                const opts = entry.opts || {};
                const rect = _panelPosition(entry.rect, payload.position);
                const closeable = payload.closeable !== false;
                const titleHtml = payload.title
                    ? '<div class="bus-overlay-panel__title">' + _escape(payload.title) + '</div>'
                    : '';
                const closeHtml = closeable
                    ? '<button type="button" class="bus-overlay-panel__close" aria-label="Close">×</button>'
                    : '';
                const html = (titleHtml || closeHtml
                    ? '<header class="bus-overlay-panel__header">' + titleHtml + closeHtml + '</header>'
                    : '') +
                    '<div class="bus-overlay-panel__body">' + (payload.html || '') + '</div>';
                const styleObj = {
                    maxHeight: (payload.maxHeight || PANEL_DEFAULTS.maxHeight) + 'px',
                    pointerEvents: 'auto',
                };
                if (payload.maxWidth) styleObj.width = payload.maxWidth + 'px';
                if (vncOverlay.isVisible(oid)) {
                    vncOverlay.update(oid, rect);
                    vncOverlay.setContent(oid, { html });
                } else {
                    vncOverlay.show(oid, rect, { className: 'bus-overlay bus-overlay-panel', html, style: styleObj });
                    const el = vncOverlay.getElement && vncOverlay.getElement(oid);
                    if (el && closeable) {
                        el.addEventListener('click', (e) => {
                            if (e.target && e.target.matches && e.target.matches('.bus-overlay-panel__close')) {
                                sendEvent(sessionId, id, 'close', {});
                                vncOverlay.dismiss(oid, true);
                            }
                        });
                    }
                    if (opts.interactive) wireInteractive(oid, sessionId, id, opts.events || ['click']);
                }
            },
            remove(id, sessionId) { vncOverlay.dismiss(_domId(sessionId, id), true); },
        };

        // ---- Pointer kind --------------------------------------------------
        RENDERERS.pointer = {
            render(id, sessionId, entry) {
                const oid = _domId(sessionId, id);
                if (!entry.rect) return;
                const r = transformRect(entry.rect);
                const payload = entry.payload || {};
                const variant = payload.variant || 'click';
                const size = payload.size || 32;
                const className = 'bus-overlay bus-overlay-pointer bus-overlay-pointer--' + variant;
                const styleObj = {
                    pointerEvents: 'none',
                    width: size + 'px',
                    height: size + 'px',
                    left: (r.left - size / 2) + 'px',
                    top:  (r.top  - size / 2) + 'px',
                };
                if (payload.color) styleObj.borderColor = payload.color;
                if (payload.duration) styleObj.animationDuration = payload.duration + 'ms';
                vncOverlay.dismiss(oid, false);
                vncOverlay.show(oid, null, { className, style: styleObj });
                if (variant !== 'cursor') {
                    const ttl = payload.duration || 600;
                    setTimeout(() => vncOverlay.dismiss(oid, false), ttl + 50);
                }
            },
            remove(id, sessionId) { vncOverlay.dismiss(_domId(sessionId, id), false); },
        };

        // ---- Region kind (spotlight) --------------------------------------
        RENDERERS.region = {
            render(id, sessionId, entry) {
                const oid = _domId(sessionId, id);
                const payload = entry.payload || {};
                if (!entry.rect) return;
                const r = transformRect(entry.rect);
                const cw = containerRoot.clientWidth || window.innerWidth;
                const ch = containerRoot.clientHeight || window.innerHeight;
                const darkness = payload.darkness != null ? payload.darkness : 0.55;
                const borderColor = payload.borderColor || 'var(--accent, #2563eb)';
                const styleObj = {
                    left: r.left + 'px',
                    top: r.top + 'px',
                    width: r.width + 'px',
                    height: r.height + 'px',
                    pointerEvents: 'none',
                    boxShadow: `0 0 0 ${Math.max(cw, ch) * 2}px rgba(0,0,0,${darkness})`,
                    outline: '2px solid ' + borderColor,
                    outlineOffset: '0',
                };
                const className = 'bus-overlay bus-overlay-region';
                const labelHtml = payload.label
                    ? '<div class="bus-overlay-region__label">' + _escape(payload.label) + '</div>'
                    : '';
                if (vncOverlay.isVisible(oid)) {
                    vncOverlay.update(oid, r);
                    vncOverlay.setStyle(oid, styleObj);
                    if (payload.label != null) vncOverlay.setContent(oid, { html: labelHtml });
                } else {
                    vncOverlay.show(oid, null, { className, html: labelHtml, style: styleObj });
                }
            },
            remove(id, sessionId) { vncOverlay.dismiss(_domId(sessionId, id), true); },
        };

        // ---- Backdrop kind ------------------------------------------------
        RENDERERS.backdrop = {
            render(id, sessionId, entry) {
                const oid = _domId(sessionId, id);
                const payload = entry.payload || {};
                const cw = containerRoot.clientWidth || window.innerWidth;
                const ch = containerRoot.clientHeight || window.innerHeight;
                const opacity = payload.opacity != null ? payload.opacity : 0.45;
                const color = payload.color || '#000';
                const styleObj = {
                    left: '0px', top: '0px',
                    width: cw + 'px', height: ch + 'px',
                    background: color,
                    opacity: String(opacity),
                    pointerEvents: payload.dismissible ? 'auto' : 'none',
                    zIndex: '5',
                };
                if (vncOverlay.isVisible(oid)) {
                    vncOverlay.setStyle(oid, styleObj);
                } else {
                    vncOverlay.show(oid, null, { className: 'bus-overlay bus-overlay-backdrop', style: styleObj });
                    if (payload.dismissible) {
                        const el = vncOverlay.getElement && vncOverlay.getElement(oid);
                        if (el) {
                            el.addEventListener('click', () => sendEvent(sessionId, id, 'click', {}));
                        }
                    }
                }
            },
            remove(id, sessionId) { vncOverlay.dismiss(_domId(sessionId, id), true); },
        };

        // ---- Unknown fallback ---------------------------------------------
        const UNKNOWN_RENDERER = {
            render(id, sessionId, entry) {
                console.warn('[overlay-bus] unknown kind:', entry.kind, 'id=', id);
                const r = entry.rect ? transformRect(entry.rect) : null;
                const oid = _domId(sessionId, id);
                const style = { outline: '2px dashed magenta', background: 'transparent', pointerEvents: 'none' };
                if (vncOverlay.isVisible(oid)) vncOverlay.update(oid, r || {});
                else vncOverlay.show(oid, r, { className: 'bus-overlay bus-overlay-unknown', style });
            },
            remove(id, sessionId) { vncOverlay.dismiss(_domId(sessionId, id), false); },
        };

        // ---- Interactive overlay wiring -----------------------------------
        function wireInteractive(oid, sessionId, id, events) {
            const el = vncOverlay.getElement && vncOverlay.getElement(oid);
            if (!el) return;
            if (vncOverlay.setStyle) vncOverlay.setStyle(oid, { pointerEvents: 'auto' });
            if (events.includes('focus')) el.setAttribute('tabindex', '0');
            for (const ev of events) {
                el.addEventListener(ev, (e) => {
                    let payload = {};
                    if (e instanceof MouseEvent) {
                        payload = {
                            clientX: e.clientX, clientY: e.clientY,
                            shiftKey: e.shiftKey, metaKey: e.metaKey,
                            ctrlKey: e.ctrlKey, altKey: e.altKey,
                            button: e.button,
                        };
                    }
                    sendEvent(sessionId, id, ev, payload);
                });
            }
        }

        function rendererFor(kind) {
            return RENDERERS[kind] || UNKNOWN_RENDERER;
        }

        function registerRenderer(kind, renderer) {
            RENDERERS[kind] = renderer;
        }

        return { rendererFor, wireInteractive, registerRenderer, RENDERERS };
    };
})();
