# Overlay Bus consumers — migration inventory

Phase 0 deliverable for the Overlay Bus unification. Every place Inspekt
injects visual UI into the **inspected page DOM**, categorised so we can
schedule migrations data-driven instead of guessing.

> **Scope:** "page-DOM injection" = scripts that run inside the inspected
> page (MAIN or isolated content-script world) and append element / style
> nodes to `document.body`, `document.documentElement`, or
> `document.head`. Host-side UI in `vm/js/*.js` is listed separately as
> reference — those overlays already live outside the page, no migration
> needed.

## At a glance

| Category | Count | Migration cost |
|---|---|---|
| **Migrated** (fully via bus) | 2 | — |
| **Partially migrated** | 1 | ½ day |
| **Not migrated, page UI** | 11 | est. 3–4 days total |
| **Out of scope** (style-only / mutation, not "visual UI") | 4 | document the convention, no migration |
| **Host-side UI, no migration needed** | many | — |

---

## Migrated

| Consumer | File | Bus kind | Notes |
|---|---|---|---|
| Unified a11y badges + popovers | `inspekt/scripts/run_a11y.js:599-744` | `a11y-badge` | Producer emits to bus when `__INSPEKT_OVERLAY_BUS_READY__`. Host consumer reuses `popover-content.js` + `popover-core.js` so VM and non-VM render identical UI. |
| Inspect highlight + tooltip | `vm/servers/control-server.py:24-46` (`INSPECT_BUS_EMIT_JS_HELPER`) inlined into `/inspect/element-at-point`, `/inspect/set-at-point`, `/inspect/navigate`; cleared by `/inspect/clear` | `highlight` + `tooltip` | Replaces 200 ms `_pollInspectRect` polling. Producer-side observers track scroll/resize. |

## Partially migrated

| Consumer | File | Status | Action |
|---|---|---|---|
| `run_axe.js` legacy axe-only path | `inspekt/scripts/run_axe.js:1288-1822` | `emitBadgesViaOverlayBus()` exists; legacy DOM-injection branch still present | Decide whether to keep the legacy path or delete it (the unified `inspekt a11y -e axe` path covers it via `run_a11y.js`). Lean delete. |

---

## Not migrated — concrete migration targets

Sorted by suggested migration order (low risk first, high-value last).

### 1. Inspect info panel — already host-side, just route through bus
- **File:** `vm/js/inspect.js:163-220` (`_showInspectInfoPanel`)
- **What:** Floating Element Inspector card with selector, attributes, computed styles, dimensions. Currently rendered via `vncOverlay.show('inspect-info-panel', null, {html, …})` directly.
- **Anchor:** Viewport (top-right of canvas).
- **Interactive:** Yes — close button.
- **Lifetime:** Persistent until the user toggles inspect off.
- **Suggested kind:** `panel`.
- **Complexity:** Low. ~30 LOC change.
- **Why first:** Host-only already, so no new transport surface; just exercises a new `panel` renderer end-to-end. Cheap proof of the kind.

### 2. `inspekt highlight` CLI / "highlight selector" preview
- **File:** `inspekt/scripts/highlight_selector.js:19` — sets `data-inspekt-highlight="N"` on matched elements; styling done by host CSS (no new DOM).
- **What:** Marks elements that match a CSS selector for the user to verify the selector visually.
- **Style strategy:** attribute-only. The actual highlight styling currently lives in user-side CSS or extension panel.
- **Decision:** This is a *style mutation*, not visual UI injection. Either:
  - **Keep as-is** (no migration; document as the "use the bus instead" exemplar of why direct DOM mutation is sometimes simpler), or
  - **Migrate** to one `highlight` overlay per match. Better isolation but heavier.
- **Recommendation:** Keep as-is for v1; revisit when we add a generic "highlight matched elements" plugin API that needs DOM cleanliness.

### 3. Engine tracker / list_axe_rules / list_ibm_rules
- **Files:**
  - `inspekt/scripts/engine-tracker.js` — registry of `__inspektUISelectors__`; **doesn't inject UI itself**, just maintains the exclude list.
  - `inspekt/scripts/list_axe_rules.js`, `list_ibm_rules.js` — return data; no DOM injection.
- **Decision:** No migration. Update `engine-tracker.js`'s `__inspektUISelectors__` to add bus-overlay selectors so the in-page consumer's shadow root is also excluded from audit scans.

### 4. Hidden-elements visualisation (extension)
- **File:** `extensions/chrome/modules/hidden-elements.js`
- **What:** Hides DOM elements (display:none / visibility:hidden) per persistence rules. **Not visual UI** — it removes UI rather than adding.
- **Decision:** No migration. Keep as direct mutation.

### 5. Screenshot pseudo-state override
- **File:** `inspekt/scripts/screenshot_pseudo.js:182-184`
- **What:** Injects one `<style id="inspekt-pseudo-state-override">` to force `:hover` / `:focus` / `:active` for screenshots.
- **Decision:** Pure CSS injection, not visual UI. **No migration**, but should be excluded from page-DOM-cleanliness invariant tests as a documented exception.

### 6. Screenshot redaction
- **File:** `inspekt/scripts/screenshot_redact.js`
- **What:** Applies `__inspekt-redacted__` class to sensitive form fields before capture, removes after.
- **Decision:** Class-mutation, not new UI. **No migration**; treat as documented exception.

### 7. `replay_step.js` force-visible attribute
- **File:** `inspekt/scripts/replay_step.js:1078`
- **What:** Tags `data-inspekt-force-visible` during replay focus to drive a host-side polyfill style.
- **Decision:** Attribute mutation, not new UI. **No migration**.

### 8. Recorder dialog backdrop + alerts
- **File:** `inspekt/scripts/record_events.js:2739-2950`
- **What:** Injects a full-page modal during recording: backdrop + dialog box + buttons + (optional) input. Used to capture user confirmation / inputs without disturbing the page state under test.
- **Anchor:** Viewport (full-screen).
- **Interactive:** Yes — dialog is a focus trap with OK/Cancel.
- **Lifetime:** Per dialog; removed on confirm/cancel.
- **Suggested kind:** New `modal` kind. Or compose `panel` + `backdrop`.
- **Complexity:** Medium. Focus trap + keyboard handling needs to live in the renderer.
- **Notes:** During recording, the recorder needs to know whether a click landed on its own dialog vs the page — currently uses `data-inspekt-dialog="true"` on the backdrop. After migration, click landing inside the host overlay container is unambiguous (separate DOM tree), so the discriminator goes away.

### 9. Recorder control mode / control focus indicator
- **File:** `inspekt/scripts/control.js:33, 109`
- **What:** Injects `<style id="inspekt-control-styles">` with a `[data-inspekt-control-focus]::after` rule, then tags whichever element is "virtually focused" with that attribute.
- **Anchor:** Tagged element (via CSS pseudo-element on the element itself).
- **Interactive:** No (visual only).
- **Lifetime:** Session (until control mode ends).
- **Suggested kind:** `outline` — but currently uses CSS-on-tagged-element rather than a sibling overlay. Migration replaces with `bus.set('control:focus', 'outline', rect, {color, glow})` per current focus.
- **Complexity:** Low.
- **Notes:** Removes one `<style>` injection from page `<head>`.

### 10. Replay visual feedback — large surface
- **File:** `inspekt/scripts/replay_visual.js` (~3000 LOC, **48 hits**)
- **What:** Multiple overlays during `inspekt replay`:
  - `inspekt-overlay` (line 685) — full-page dim
  - `inspekt-circle` (689) — animated cursor pulse for clicks
  - `inspekt-typing` (694) — typing animation indicator
  - `inspekt-focus-ring` (700) — visual focus ring for tab navigation
  - `inspekt-spotlight` (1670) — spotlight cut-out highlighting current target
  - `inspekt-target-indicator` (1727) — arrow / label pointing at target
  - `inspekt-select-preview` (931) — hovers + selection box during interactive replay
  - `inspekt-drag-target` (1987) — drag-and-drop visualisation
  - `inspekt-interactive-overlay` (2150) — covers page during pause/decision
  - `inspekt-assertion-overlay` (2614) — pass/fail flash on assertion steps
  - `inspekt-input-lock-styles` (2802) — disables interaction during automated step
  - `inspekt-dialog-styles` (2915) + `inspekt-dialog-backdrop` (2925) + `inspekt-dialog` (2929) — inline confirmation prompts
- **Suggested split into kinds:** `pointer` (click pulse + cursor), `outline` (focus ring), `panel` (target indicator, dialog), `region` (spotlight), `backdrop` (interactive-overlay, assertion-overlay), `style-mask` (input-lock — same exception class as redaction).
- **Complexity:** **High** — biggest single migration. Best done in 2–3 PRs (pointer+outline first, then dialog/backdrop/spotlight, then assertion + drag).
- **State owner:** Mixed — most are "consumer paints, producer dictates". Dialog is interactive, needs round-trip events.
- **Notes:** Recorder & replay also work outside VM, so this *forces* the in-page consumer (Phase 3 of the plan) to be solid.

### 11. Screenshot selection UI
- **File:** `inspekt/scripts/screenshot_selection.js:63-228` — 7 elements:
  - `inspekt-selection-styles` (63) — style block
  - `inspekt-selection-overlay` (197) — dim
  - `inspekt-selection-box` (202) — drag rect (dashed)
  - `inspekt-snapped-box` (207) — snapped-to-element rect (solid)
  - `inspekt-selection-hint` (212) — instruction tooltip
  - `inspekt-snap-badge` (218) — snapped element label
  - `inspekt-combined-box` (223) — debug
  - `inspekt-debug-panel` (228) — debug
- **What:** Interactive screenshot region selection: user drags, the script snaps to nearest element, shows hints.
- **Anchor:** Mouse position + matched element rects.
- **Interactive:** Yes — full pointer drag handling.
- **Lifetime:** Transient (until user confirms or cancels).
- **Suggested kinds:** `region` (selection box, snapped box, dim), `tooltip` (hint, snap-badge).
- **Complexity:** **High** — drag handling is the trickiest part. The renderer needs pointer events; producer-side mouse capture needs to happen for drag.
- **Notes:** This is the only migration where the *producer* doesn't own all input events — the renderer captures the drag and reports rect changes back. Will exercise the `overlay.event` consumer→producer channel meaningfully.

### 12. Extension element picker (non-VM mode)
- **File:** `extensions/chrome/element_picker.js:20-340`
- **What:** When the user clicks the DevTools panel's "Inspect" button outside VM, this MAIN-world script overlays the page with crosshair cursor + hover highlight + tooltip until they click an element.
- **DOM injected:**
  - `__inspekt_picker_style__` (`<style>`) — pulse keyframes
  - `__inspekt_picker_indicator__` (banner top-center)
  - overlay (full-page, crosshair cursor)
  - highlightBox (animated, follows hover)
  - tooltip (tag name)
- **Suggested kinds:** `highlight` + `tooltip` + `panel` (banner) + `style-mask` for cursor change.
- **Complexity:** Medium.
- **Notes:** This is the canonical **non-VM** path. Until Phase 3 (in-page consumer) lands, this consumer can't migrate — it's the litmus test that the in-page consumer works.

### 13. IBM badges + popovers (`run_ibm.js`)
- **File:** `inspekt/scripts/run_ibm.js:265-486` — `getIbmPopoverCSS`, `injectBadgeStyles`, `data-inspekt-badge` on each badge.
- **What:** Same shape as `run_axe.js` but for IBM Equal Access — separate DOM injection path.
- **Status today:** When the user runs `inspekt a11y -e eac`, this script is what injects (because in single-engine mode the unified `run_a11y.js` path may delegate to the engine-specific scripts; verify before migrating). When `inspekt a11y -e axe,eac` runs, it goes through `run_a11y.js` and is already migrated.
- **Suggested kind:** `a11y-badge` — already covers it.
- **Complexity:** Low (mostly removal — the bus path in `run_a11y.js` handles eac just fine; verify and delete the standalone DOM-injection path here).

---

## Out-of-scope (host-only, already isolated)

These render into host DOM (control panel) and don't pollute the inspected page. Listed so future audits don't flag them.

| File | What it renders | Where |
|---|---|---|
| `vm/js/vnc-overlay.js` | Inspect highlight + tooltip + info panel primitives | `#vncOverlayContainer` (sibling of canvas) |
| `vm/js/cdp-modal.js` | DevTools-mode chooser modal | host body |
| `vm/js/command-palette.js` | Cmd+K palette (ninja-keys) | host body |
| `vm/js/context-menu.js`, `vnc-context-menu.js`, `context-menu-items.js` | Right-click menus | host body |
| `vm/js/audio.js` | Audio relay UI | host body |
| `vm/js/focus-overlay.js` | "Click to interact" prompt over canvas | host body |
| `vm/js/voice.js`, `vision-sim.js`, `motor-sim.js` | Voice / vision / motor simulator panels | host body |
| `vm/js/scrollbar.js`, `screen-reader.js`, `terminal.js`, `editor.js`, `tabs.js`, `popout-manager.js`, … | Various host control panel components | host body |
| `extensions/chrome/components/element-highlighter.js`, `element-picker.js` | DevTools panel components — orchestrators that call `evalInPage()`; **the actual injection happens in the in-page scripts they call** | DevTools panel |

---

## Recommended migration order

Reordered from the audit findings (risk-balanced, value-weighted):

| Order | Consumer | Effort | Value |
|---|---|---|---|
| 1 | Inspect info panel | low | proves `panel` kind |
| 2 | Recorder control focus indicator | low | proves `outline` for tagged elements |
| 3 | IBM standalone badges (or delete them) | low | shrinks DOM-injection surface |
| 4 | Replay click pulses + focus ring (subset of replay_visual) | medium | proves `pointer` kind, validates non-VM consumer for replay |
| 5 | Replay dialog + assertion overlays | medium | proves `modal` / `backdrop` kinds, exercises focus trap |
| 6 | Replay spotlight + target indicator | medium | proves `region` kind |
| 7 | Recorder dialog backdrop | medium | reuses `modal` from replay |
| 8 | Extension element picker (non-VM) | medium | first true exercise of in-page consumer |
| 9 | Screenshot selection UI | high | exercises drag-event consumer→producer round-trip |
| 10 | Replay drag/select preview | high | reuses screenshot selection's drag plumbing |
| 11 | `run_axe.js` legacy path: delete | trivial | dead-code removal |

Items 1–3 can ship in any order (independent). Items 4–6 must come after the
`replay_visual` work is broken into kinds. Item 8 is the gate for non-VM
mode validity. Items 9–10 share a renderer.

## Decisions that fall out of this audit

1. **Three new kinds needed for v1 unification** beyond what's already there: `panel`, `outline`, `pointer`. Two more for full coverage: `modal` (or `backdrop` + `panel` composed), `region` (a rectangular cut-out / spotlight).
2. **`engine-tracker.js`'s `__inspektUISelectors__` needs an entry for the bus's host-element marker** so axe / scans don't pick it up.
3. **Three legitimate exceptions** to the "no DOM injection" rule, codified in the lint rule allow-list:
   - `screenshot_redact.js` — class-mutation for redaction
   - `screenshot_pseudo.js` — pseudo-state CSS override
   - `replay_step.js` — `data-inspekt-force-visible` attribute toggle for focus polyfill
   None inject *visual UI*; all three mutate page styles intentionally.
4. **`highlight_selector.js`** is borderline — currently attribute-only. Keep as-is for v1; revisit if it grows.
5. **Replay visual is the biggest single migration** by line count and complexity. Splitting into 2–3 PRs is mandatory.
6. **The non-VM in-page consumer (plan Phase 3) is on the critical path** — items 8, 4, 5 all need it. Without it, those features only work in VM mode.

## Net page-DOM cleanup after full migration

Today (a fresh page after running `inspekt a11y --show-badges --interactive` and `inspekt replay`):

```
[data-inspekt-axe-badge]      0   (already migrated)
[data-inspekt-badge]          0   (already migrated)
[data-inspekt-axe-popover]    0   (already migrated)
[data-inspekt-control-focus]  N
[data-inspekt-dialog]         1+
[data-inspekt-force-visible]  0–1
[data-inspekt-highlight]      N
#inspekt-replay-*             ~12
#inspekt-spotlight            1
#inspekt-control-styles       1
#inspekt-dialog-*             1+
#inspekt-input-lock-styles    1
#inspekt-pseudo-state-override 0–1
#inspekt-selection-*          7   (during selection only)
__inspekt_picker_*            3   (non-VM picker only)
```

After full migration:

```
__inspekt-redacted__          N    (style class, exempt)
data-inspekt-force-visible    0–1  (attribute-only, exempt)
data-inspekt-highlight        N    (attribute-only, exempt — to revisit)
inspekt-pseudo-state-override 0–1  (style only, exempt)
```

Net delta: **all visual UI injection sites collapse to zero**. Only style /
attribute mutations remain, with documented exemptions.
