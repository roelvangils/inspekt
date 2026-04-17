# ninja-keys vendored bundle

**Version:** 1.2.2 (last updated July 2022 — no releases since)
**Bundle:** `ninja-keys.min.js` — self-contained ESM with Lit dependencies

## Inspekt patches

Three small patches marked with `[INSPEKT PATCH]`:

1. **`ninja-action.js`** — `content` field for secondary text + pin button on selected items
2. **`base-styles.js`** — Move `backdrop-filter` from full-page overlay to modal panel only

## How to rebuild

```bash
cd /tmp && mkdir ninja-bundle && cd ninja-bundle
npm init -y && npm install ninja-keys@1.2.2

# Apply patches to dist/ files (see below), then:
echo 'import "ninja-keys";' > entry.js
npx esbuild entry.js --bundle --format=esm --minify --outfile=ninja-keys.bundled.min.js --target=es2020

cp ninja-keys.bundled.min.js /path/to/inspekt/docker/browser-vm/vendor/ninja-keys.min.js
```

## Patch 1: `dist/ninja-action.js`

### 1a. In `render()`, before the return statement:

```js
// [INSPEKT PATCH] Render optional content field as secondary text (only when selected)
const content = (this.selected && this.action.content)
    ? html `<span class="ninja-content" part="ninja-content">${this.action.content}</span>`
    : '';
// [INSPEKT PATCH] Pin button — only on selected items
const pinBtn = this.selected
    ? html `<button class="ninja-pin" part="ninja-pin" title="Pin/unpin" @click=${(e) => {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent('togglePin', { detail: this.action, bubbles: true, composed: true }));
    }}><svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor"><path d="M4.456 2.013..."/></svg></button>`
    : '';
```

### 1b. In the return template:

```js
${icon}
<div class="ninja-title">${this.action.title}${content}</div>
${hotkey}
${pinBtn}
```

### 1c. In `styles`, add before `.ninja-hotkeys`:

```css
.ninja-content {
  margin-left: 0.75em;
  font-size: 0.85em;
  color: var(--ninja-secondary-text-color);
  opacity: 0.5;
  white-space: nowrap;
}
.ninja-pin {
  flex-shrink: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--ninja-secondary-text-color);
  opacity: 0.4;
  padding: 2px 4px;
  margin-left: 0.5em;
  border-radius: 4px;
  display: flex;
  align-items: center;
  transition: opacity 0.15s;
}
.ninja-pin:hover {
  opacity: 1;
  color: var(--ninja-accent-color);
}
```

## Patch 2: `dist/base-styles.js`

### 2a. In `.modal`, remove the backdrop-filter lines:

```css
/* Remove these two lines: */
-webkit-backdrop-filter: var(--ninja-backdrop-filter);
backdrop-filter: var(--ninja-backdrop-filter);
```

### 2b. In `.modal-content`, add backdrop-filter:

```css
.modal-content {
  /* ... existing styles ... */
  -webkit-backdrop-filter: var(--ninja-backdrop-filter);
  backdrop-filter: var(--ninja-backdrop-filter);
}
```
