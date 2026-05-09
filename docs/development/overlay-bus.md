# Overlay Bus

The Overlay Bus is the unified path for any Inspekt feature that needs to
render visual UI on top of the inspected page. Producers emit overlay
*data* via a single API; mode-aware consumers render it.

The page DOM stays clean — Inspekt's own overlays don't pollute axe scans,
screen-reader output, recordings, or anything else that walks the page.

## Why

Before the bus, every Inspekt feature that wanted to show a badge / popover
/ tooltip / panel / outline injected DOM directly into the inspected
page. That had three structural problems:

1. **DOM pollution.** Inspekt is an a11y / QA testing tool; every
   `<button data-inspekt-badge>` it appended showed up in the page's
   accessibility tree, screen-reader output, axe scans, and recorder
   output. We were testing our own UI alongside the page.
2. **VNC compression.** Overlays rendered inside Chromium-in-VM got
   compressed and rescaled through the noVNC pipeline. Crisp host-side
   rendering is faster and looks better.
3. **Code duplication.** Every feature wrote its own DOM-injection
   plumbing (style tag, exclude selectors for axe, tracking observers,
   cleanup on navigation, …). Same code, six times.

The bus solves all three with one abstraction.

## Mental model

The producer is mode-agnostic. A transport switch in the isolated content
script picks **VM mode** (WebSocket → host control panel) or **non-VM
mode** (in-process → in-page consumer rendering into a shadow root)
depending on whether the WS server is reachable. The same renderer
factory runs in both consumers, so a kind painted host-side and a kind
painted in-page is the same code.

```
                     ┌───────────── PRODUCER (every page) ────────────┐
                     │                                                │
                     │  MAIN world (page ctx)                         │
                     │    feature scripts: run_a11y, inspect,         │
                     │    recorder, plugins, SR cursor …              │
                     │      │                                         │
                     │      │ window.InspektOverlayBus.set(…)         │
                     │      │ ── postMessage ──▶                      │
                     │  ISOLATED content script                       │
                     │    extensions/chrome/overlay-bus.js            │
                     │    - WS to localhost:8890 (tries first)        │
                     │    - falls back after ~750 ms to in-process    │
                     │    - observers (RO/IO/MO + scroll/resize)      │
                     │    - rAF batch coalescer                       │
                     │      │                                         │
                     └──────┼─────────────────────────────────────────┘
                            │
        WS reachable? ──────┼──── No  ──▶  IN-PAGE CONSUMER (same isolated world)
        ▼ Yes                              extensions/chrome/overlay-bus-inpage.js
                                           - shadow root attached to <html>
   VM-MODE TRANSPORT                       - vncOverlay shim → shadow DOM
   ws://localhost:8890/overlay/ws          - identity rect transform
        │                                  - factory(env)  ◀─┐
        ▼                                                    │
   vm/servers/overlay-bus-server.py                          │
   - pubsub fanout per session                               │
   - snapshot replay on consumer reconnect                   │
        │                                                    │
        ▼                                                    │
   HOST CONSUMER (control panel)                             │
   vm/js/overlay-bus.js                                      │
   - WS subscriber                                           │
   - vncOverlay over noVNC canvas                            │
   - canvas-aware rect transform                             │
   - factory(env)  ────────────────────────────────────────▶ Both consumers
                                                             load the same
                                                             renderer factory:
                                                             extensions/chrome/
                                                             overlay-bus-renderers.js
```

Three pieces, separable by concern:

- **Producer** — any MAIN-world script. Calls `window.InspektOverlayBus.set(...)`.
  Doesn't know which mode it's in or what kind of consumer is rendering.
  Implemented in `extensions/chrome/overlay-bus-main.js` (MAIN-world stub)
  + `extensions/chrome/overlay-bus.js` (isolated content script, transport
  switch, observers, rAF batcher).

- **Transport switch.** The producer's isolated script tries WS to
  `localhost:8890` first. After two failed attempts (~750 ms) it
  activates the in-page consumer in the same isolated world and dispatches
  ops in-process. WS reconnect keeps polling cheaply at the 5 s cap; if
  the VM control panel comes online later, the producer flips back to
  WS. Mode is exposed to feature scripts only as a single
  `window.__INSPEKT_OVERLAY_BUS_READY__` boolean — they don't see the
  transport.

- **Consumer.** Two implementations, same renderer factory:
  - **Host consumer** (`vm/js/overlay-bus.js`): WS subscriber, renders into
    `#vncOverlayContainer` over the noVNC canvas, uses `_vmRectToOverlayRect`
    to convert page CSS px to host CSS px (canvas scaling + letterboxing).
  - **In-page consumer** (`extensions/chrome/overlay-bus-inpage.js`): runs
    in the producer's isolated world, lazily attaches a shadow root to
    `<html>` (host element marked with `data-inspekt-overlay-host` and
    `aria-hidden="true"` so it's invisible to scans / AT). Rect transform
    is identity — page coords are render coords. The shadow root keeps
    overlays out of `document.body.querySelectorAll([data-inspekt-*])` and
    out of the page accessibility tree.

## Renderer factory

Single source of truth: `extensions/chrome/overlay-bus-renderers.js`.
Self-contained IIFE that exposes one global:

```js
window.__inspektCreateOverlayRenderers__(env) → {
    rendererFor(kind),
    wireInteractive(oid, sessionId, id, events),
    registerRenderer(kind, renderer),
    RENDERERS,
}
```

`env` provides the host-context-specific pieces:

| field | host consumer | in-page consumer |
|---|---|---|
| `vncOverlay` | the global from `vm/js/vnc-overlay.js` | a shim defined in `overlay-bus-inpage.js` operating on the shadow root |
| `transformRect(r)` | `_vmRectToOverlayRect` (canvas-aware) | identity `r => r` |
| `containerRoot` | `#vncContainer` | `document.documentElement` |
| `popoverCore`, `popoverContent` | `window.__inspektPopoverCore__` / `__inspektPopoverContent__` (loaded by the control panel) | `null` (a11y-badge unavailable in v1, see below) |
| `sendEvent(...)` | forwards via WS through `window.overlayBus.sendEvent` | posts `INSPEKT_OVERLAY_EVENT` to MAIN — same envelope shape |

Adding a new kind = add a renderer to the factory. Both consumers pick it
up automatically. No mode-specific code.

### a11y-badge limitation in v1

The factory only registers `a11y-badge` when `popoverCore` and
`popoverContent` are both available. Reason: those modules use
`document.getElementById(violation.popoverId)` to wire popovers to
badges, and `getElementById` doesn't pierce shadow boundaries. Inside
the in-page consumer's shadow root, that lookup would silently miss.

Until popover-core is made shadow-aware (separate refactor), non-VM
a11y rendering keeps using `inspekt/scripts/run_a11y.js`'s in-page DOM
path. Tracked in
[`docs/development/overlay-bus-consumers.md`](./overlay-bus-consumers.md).

## Transport state machine

Inside `extensions/chrome/overlay-bus.js` the producer holds a single
state variable `_transport`:

| state | meaning | how to enter | what `_sendRaw` does |
|---|---|---|---|
| `'pending'` | initial — neither WS nor in-page is the active sink | document_start | queue in `_outboundQueue` |
| `'ws'` | WS to control panel is OPEN | `socket.open` handler | `socket.send(JSON.stringify(msg))` |
| `'inpage'` | fallback active; in-page consumer is the sink | `_activateInPageFallback()` after `WS_FALLBACK_AFTER_ATTEMPTS` failures | `__inspektOverlayInPageConsumer__.dispatch(msg)` directly |

Transition rules:
- `'pending'` → `'ws'`: WS opens. On-open handler pushes the current
  REGISTRY as a snapshot so the server is in sync, then drains
  `_outboundQueue`.
- `'pending'` → `'inpage'`: WS reconnect's failure-counter hits the
  threshold. Activator drains the queue locally and replays REGISTRY as
  a snapshot to the in-page consumer.
- `'ws'` → `'pending'`: WS closes. Reconnect loop keeps trying.
- `'inpage'` → `'ws'`: WS reconnect later succeeds. Producer's open
  handler flips state back. The in-page consumer's shadow-root state
  isn't auto-cleaned (mode-swap mid-session is rare; v1 doesn't bother).
- `'inpage'` is sticky in non-VM: WS will keep failing forever, reconnect
  polls cheaply at the 5 s cap.

`window.__INSPEKT_OVERLAY_BUS_READY__` (mirrored to MAIN by the producer's
`postMessage`) flips `true` when state becomes `'ws'` *or* `'inpage'`,
flips `false` only when state goes back to `'pending'` (i.e. a WS
disconnect with no in-page fallback active).

## Page-DOM cleanliness invariants

After a feature emits via the bus, the inspected page should contain no
Inspekt visual UI — both modes:

| What to check | VM mode | Non-VM mode |
|---|---|---|
| `document.body.querySelectorAll('[data-inspekt-*]').length` | 0 | 0 |
| `document.body.innerHTML.includes('inspekt-')` | false | false |
| Where the overlays actually live | `#vncOverlayContainer` (host control panel, separate browser window) | shadow root of `[data-inspekt-overlay-host]` element on `<html>` |

The `[data-inspekt-overlay-host]` element on `<html>` is intentionally
*not* in `document.body` — it sits as a sibling, invisible to anything
that walks `body`. It carries `aria-hidden="true"` so AT ignores the
subtree (Inspekt overlays must not appear in the user's accessibility
testing). The same exclude attribute is in
`engine-tracker.js`'s `__inspektUISelectors__` for axe / scan code.

## Producer API

```js
window.InspektOverlayBus = {
  set(id, kind, rect, payload, opts),  // create or replace
  update(id, partial),                  // patch rect / payload
  clear(id),
  clearAll(prefix),                     // e.g. clearAll('axe:')
  track(id, selector, opts),            // attach RO/IO observers
  on(id, event, cb),                    // 'click' | 'focus' | 'pointerenter' | 'close'
  snapshot(),                           // returns Promise<entry[]>
};
```

- `id` is a stable per-session string — re-emitting overwrites. Namespace
  it (`'axe:badge:3'`, `'inspect:highlight'`, `'recorder:click:42'`) so
  features don't collide.
- `rect` is `{left, top, width, height}` in **page CSS px**. The consumer
  transforms to host px via `_vmRectToOverlayRect()`.
- `opts.track: true` + `opts.selector` (or `opts.element`) enables
  observer-driven rect updates from the producer side. No more polling.
- `opts.interactive: true` + `opts.events: ['click', …]` makes the host
  overlay respond to those DOM events and round-trip them back to the
  producer's `bus.on(id, event, cb)` callback.

`bus.on` callbacks fire after the consumer handles the event (via the
`overlay.event` server message). Network round-trip is one frame in VM
mode, microtask-level in non-VM (when in-process transport lands).

### Connection state

The MAIN-world stub mirrors the bus connection on
`window.__INSPEKT_OVERLAY_BUS_READY__` (boolean). Feature scripts that
have both a bus path and a legacy in-page path branch on this flag:

```js
if (window.InspektOverlayBus && window.__INSPEKT_OVERLAY_BUS_READY__) {
    bus.set(id, 'highlight', rect, payload, { track: true, selector });
} else {
    // legacy in-page DOM path (until in-page consumer lands)
}
```

## Wire protocol

JSON, line-delimited, top-level `v: 1`:

```jsonc
// producer → server → consumer
{ "v":1, "type":"overlay.set",
  "sessionId":"<tab>:<frame>", "id":"axe:badge:1",
  "kind":"badge",
  "rect":{"left":100,"top":200,"width":24,"height":24},
  "payload":{ /* kind-specific */ },
  "opts":{ "interactive":true, "track":true, "events":["click"] } }

{ "v":1, "type":"overlay.update", "sessionId":"…", "id":"axe:badge:1",
  "rect":{ "left":105, "top":210, "width":24, "height":24 } }

{ "v":1, "type":"overlay.clear", "sessionId":"…", "id":"axe:badge:1" }

{ "v":1, "type":"overlay.batch", "sessionId":"…",
  "ops":[ /* set/update/clear */ ] }

// consumer → server → producer
{ "v":1, "type":"overlay.event", "sessionId":"…", "id":"axe:badge:1",
  "event":"click",
  "payload":{ "clientX":420, "clientY":180, "shiftKey":false } }

// scroll-suppress: producer signals "dim everything for a moment"
// when the page is being scrolled fast — VM consumers blur + dim
// non-detached overlays so the lag between DOM-side overlay updates
// and the noVNC pixel stream is hidden. Non-VM in-page consumers
// ignore these messages (no streaming delay there).
{ "v":1, "type":"overlay.suppress",   "sessionId":"…" }
{ "v":1, "type":"overlay.unsuppress", "sessionId":"…" }

// server lifecycle
{ "v":1, "type":"overlay.session.start", "sessionId":"…" }
{ "v":1, "type":"overlay.session.end",   "sessionId":"…",
  "reason":"navigate|close|timeout|disconnect" }

// bootstrap on consumer (re)connect
{ "v":1, "type":"overlay.snapshot", "sessionId":"…",
  "entries":[ /* full {id,kind,rect,payload,opts} per overlay */ ] }
```

Producer rate-limits via rAF: dirty overlays coalesced into one
`overlay.batch` per frame.

## Standard kinds (v1)

Each kind is a host-side renderer registered in `vm/js/overlay-bus.js`.
Add a new kind via `overlayBus.registerRenderer('foo', { render, remove })`.

| kind | use for | payload schema | rect required | persistent |
|---|---|---|---|---|
| `highlight` | outline + tinted fill on an element rect | `{className?, color?}` | yes | yes |
| `tooltip` | small text label anchored to a rect | `{text}` | yes | yes |
| `badge` | numbered circle on a corner | `{text, impact?, offsetX?}` | yes | yes |
| `a11y-badge` | a11y violation badge + popover (uses shared popover modules) | `{badgeNumber, engines, violation}` | yes | yes |
| `outline` | outline-only box (recorder steps, control focus, etc.) | `{className?, color?, style?, label?}` | yes | yes |
| `panel` | persistent floating card with optional close button | `{html, title?, position?, maxWidth?, maxHeight?, closeable?}` | optional | yes |
| `pointer` | animated cursor / click pulse / focus pulse at a point | `{variant: 'click'\|'pulse'\|'cursor', color?, size?, duration?}` | yes (point) | only `cursor` |
| `region` | spotlight (full-viewport dim with rect cutout) | `{darkness?, color?, label?, borderColor?}` | yes | yes |
| `backdrop` | full-viewport dim (compose with `panel` for a modal) | `{opacity?, color?, dismissible?}` | no | yes |
| `unknown` | (fallback) — dashed magenta outline if an unknown kind arrives | n/a | depends | yes |

### Composing for common UIs

Inspekt's bigger UIs compose cleanly out of these primitives:

| UI | composition |
|---|---|
| Inspect mode | `highlight` + `tooltip` + `panel` (info card) |
| a11y badges | one `a11y-badge` per violation (encapsulates popover + popoverCore) |
| Recorder click feedback | `pointer{variant:'click'}` per click |
| Recorder focus ring | `outline` with `style:'dashed'` |
| Recorder spotlight on target | `region` + (optional) `panel` arrow |
| Recorder dialog | `backdrop{dismissible:false}` + `panel{closeable:true}` |
| Screenshot region selection | `region` (live) + `tooltip` (snap label) |
| Element picker (extension) | `highlight` + `tooltip` + `panel{position:'top-center'}` (banner) |
| Plugin highlight | `outline` per matched element |

Modal = backdrop + panel composed with the same id prefix; producer emits
both, clears both. No new kind needed.

## Lifecycle

| event | what happens |
|---|---|
| Page navigates | Content-script context dies; WS closes; server emits `overlay.session.end`; consumer dismisses all overlays for that session (animated) |
| Tab close | Same as navigate |
| Element removed from DOM | Producer's MutationObserver detects `!el.isConnected` → `overlay.clear` |
| Control panel reload | Consumer reconnects; server replays current per-session snapshot |
| Producer reconnect (control-server bounce) | Producer resends full snapshot to server; server forwards to consumers |
| Idle GC | Server times out producer sessions with no traffic > 5 min |

Source of truth is the producer (in-Chromium content script). Server
holds a small cache for late-joining consumers only.

## Reloading after a code change

Different layers in the bus need different reload steps:

| Edited file | Reload to apply |
|---|---|
| `vm/js/overlay-bus.js`, `vm/css/overlay-bus.css` | Hard-reload the control panel (`Cmd+Shift+R` in the host browser) |
| `vm/control-panel.html` | Hard-reload the control panel |
| `inspekt/scripts/shared-popover/*.js`, `inspekt/scripts/{axe,unified}-popover/*.css` | Hard-reload the control panel |
| `extensions/chrome/overlay-bus-renderers.js` | Hard-reload the control panel (host loads it via `<script>`) |
| `extensions/chrome/overlay-bus.js`, `overlay-bus-main.js`, `overlay-bus-inpage.js`, `manifest.json` | **Restart Chromium** (`make vm-restart-chromium`) — extensions are loaded once at browser startup, page reload re-uses cached content scripts |
| `inspekt/scripts/run_a11y.js`, `run_axe.js`, `run_ibm.js` | Nothing — the CLI loads the script fresh each invocation |
| `vm/servers/overlay-bus-server.py` | `make vm-restart-overlay-bus` |
| `vm/entrypoint.sh`, `vm/Dockerfile`, `vm/supervisord.conf` | `make vm-rebuild` |

If you forget the Chromium restart for a content-script edit, the symptom is "the new code is on disk but doesn't run" — diagnose by sending a known-good message via Python WebSocket (server forwards) and comparing against a CDP-driven test in the live page. If the server forwards and the live page doesn't, it's a content-script staleness issue.

## Adding a new kind

1. Add a renderer to `vm/js/overlay-bus.js` (`RENDERERS.foo = { render, remove }`).
2. Document the payload schema in this file's table above.
3. Add styling to `vm/css/overlay-bus.css` if needed.
4. Producers reference it as `bus.set(id, 'foo', rect, payload, opts)`.

The renderer contract:

```js
RENDERERS.foo = {
    /**
     * Called on overlay.set or overlay.update. Must be idempotent —
     * re-rendering the same entry should not duplicate DOM.
     * @param {string} id          stable id within the session
     * @param {string} sessionId   producer session id (unique per page+frame)
     * @param {object} entry       { kind, rect, payload, opts }
     */
    render(id, sessionId, entry) { /* … */ },

    /**
     * Called on overlay.clear or overlay.session.end.
     * @param {string} id, sessionId, entry  (entry may be null on session.end)
     */
    remove(id, sessionId, entry) { /* … */ },
};
```

Idiom: use `vncOverlay.show(_domId(sessionId, id), rect, options)` to
create the overlay element. The overlay container handles `position:
absolute`, the renderer handles styling via `className` and `style`.

## What NOT to do

- **Don't `appendChild` to `document.body` from any Inspekt script.** That
  was the old way. The lint rule (Phase 5 of the unification plan) will
  enforce this.
- **Don't write a one-off renderer in your feature's script.** Add a
  `kind` if no existing one fits — that lets the next feature reuse it.
- **Don't pass DOM nodes through the bus.** The transport is JSON. Use
  `opts.element` (consumed locally by the producer's tracker) or a CSS
  selector via `opts.selector`. Overlay payloads must be serialisable.

## Documented exemptions

Three kinds of page-DOM mutations are *not* visual UI and don't go
through the bus. They're allow-listed in the future lint rule:

- `screenshot_redact.js` — class-mutation for redaction (not new UI)
- `screenshot_pseudo.js` — `<style>` injecting `:hover`/`:focus`/`:active`
  pseudo-state for screenshots
- `replay_step.js` — `data-inspekt-force-visible` attribute toggle for
  the focus-visible polyfill

## Migration status

Tracked in [`docs/development/overlay-bus-consumers.md`](./overlay-bus-consumers.md).

Consumers migrated:
- Unified a11y badges + popovers (`run_a11y.js` → `a11y-badge` kind)
- Inspect highlight + tooltip (`control-server.py` snippets → `highlight` + `tooltip`)

Consumers pending — see the inventory document for the full list and
suggested order. The plan target is zero `[data-inspekt-*]` nodes in the
inspected page DOM after every feature is migrated, with the three
exemptions above as documented carve-outs.

## File map

| Path | Role |
|---|---|
| `extensions/chrome/overlay-bus.js` | Isolated content-script producer: transport switch (WS or in-process), observers, rAF batcher |
| `extensions/chrome/overlay-bus-main.js` | MAIN-world API stub (`window.InspektOverlayBus`) |
| `extensions/chrome/overlay-bus-renderers.js` | Single source of truth for kind→renderer logic. Loaded by both consumers via `__inspektCreateOverlayRenderers__(env)`. |
| `extensions/chrome/overlay-bus-inpage.js` | Non-VM in-page consumer: shadow root + `vncOverlay` shim + factory. Activated when WS isn't reachable. |
| `extensions/chrome/manifest.json` | Registers all four content scripts in load order |
| `extensions/chrome/background.js` | Injects the MAIN-world stub at tab-load |
| `vm/servers/overlay-bus-server.py` | Asyncio + websockets pubsub server, port 8890 (VM mode only) |
| `vm/js/overlay-bus.js` | VM-mode host consumer: WS subscriber + factory + canvas-aware rect transform |
| `vm/css/overlay-bus.css` | Styles for host-side bus overlays (in-page consumer ships its own inline copy) |
| `vm/control-panel.html` | Loads the host consumer + shared popover modules + factory |
| `inspekt/scripts/shared-popover/{popover-core,popover-content}.js` | Shared popover modules (host-side a11y-badge only) |
| `inspekt/scripts/{axe,unified}-popover/*.css` | Shared popover CSS (axe / unified styles) |
