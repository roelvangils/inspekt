# CodeMirror vendored bundle

**Version:** unknown (minified bundle has no embedded version marker)
**Family:** CodeMirror 6 (`@codemirror/*` modular npm packages)
**License:** MIT
**Source:** https://codemirror.net/

The file `codemirror.min.js` is a local esbuild-produced bundle that
exposes the editor as the `CM` global, used by `vm/js/editor.js`.
CodeMirror 6 is distributed as many small `@codemirror/*` packages rather
than a single `codemirror` package, so there is no single version number
to record — each sub-package has its own release cadence.

## Rebuilding

If you want to refresh to the latest `@codemirror/*` releases:

```bash
cd /tmp && mkdir cm-bundle && cd cm-bundle
npm init -y
npm install \
  @codemirror/state @codemirror/view @codemirror/commands \
  @codemirror/language @codemirror/search @codemirror/autocomplete \
  @codemirror/lint @codemirror/theme-one-dark \
  @codemirror/lang-javascript @codemirror/lang-html @codemirror/lang-css \
  @codemirror/lang-json @codemirror/lang-markdown @codemirror/lang-python \
  @codemirror/lang-xml @codemirror/lang-yaml @lezer/highlight

# Write an entry.js that re-exports what editor.js uses as `CM.*`
# (EditorState, EditorView, keymap, lineNumbers, etc.) then bundle:
npx esbuild entry.js --bundle --format=iife --global-name=CM \
  --minify --target=es2020 --outfile=codemirror.bundled.min.js

cp codemirror.bundled.min.js /path/to/inspekt/vm/vendor/codemirror.min.js
```

The exact export surface required by `editor.js` is the `CM.*` names it
imports: grep for `CM\.` in `vm/js/editor.js` before writing `entry.js`.
