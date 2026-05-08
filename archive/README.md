# archive/

Historical notes from earlier refactors and migrations. Kept for context
on why things are the way they are; not required reading.

Everything here is frozen — do not update these documents. If you need
to add new historical context, add a new file rather than editing old
ones, so the archive stays an honest record.

Current architecture reference: [`../docs/architecture.html`](../docs/architecture.html).

## `scripts/`

One-shot migrations, abandoned dev tools, and helpers no longer wired
into the active build. None of these are referenced from `Makefile`,
`Procfile.dev`, GitHub workflows, or any `CLAUDE.md`. Restore one
back to `../scripts/` only if you also wire it into a real entry
point — otherwise it just rots here again.

| Script | What it did |
|---|---|
| `build_codemirror.mjs` | Built CodeMirror bundle for the in-VM editor (replaced by vendored prebuilt) |
| `build-axe-css.js` / `cors-server.py` | Live-reload dev pair for iterating on axe popover CSS (replaced by `--dev-css` flag) |
| `ellipsis_sweep.py` | One-shot codemod replacing `...` with `…` across the codebase |
| `rename_refactor.py` | One-shot codemod for the folder rename in commit `fb50f42` |
| `update_google_fonts.py` | One-shot fetch of Google Fonts CSS for offline embedding |
