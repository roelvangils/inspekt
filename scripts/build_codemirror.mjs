#!/usr/bin/env node
/**
 * Bundle CodeMirror 6 into a single IIFE file for the Inspekt Browser VM.
 *
 * Usage: node scripts/build_codemirror.mjs
 * Output: vm/vendor/codemirror.min.js
 *
 * Exposes everything on window.CM so control-panel.html can use:
 *   new CM.EditorView({ ... })
 *   CM.javascript(), CM.json(), CM.oneDark, etc.
 */

import { build } from "esbuild";
import { mkdirSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outfile = resolve(__dirname, "../vm/vendor/codemirror.min.js");

// Ensure output directory exists
mkdirSync(dirname(outfile), { recursive: true });

await build({
  stdin: {
    contents: `
// Re-export everything the editor needs on window.CM
export { EditorState, Compartment, StateEffect } from "@codemirror/state";
export { EditorView, keymap, lineNumbers, highlightActiveLineGutter, highlightSpecialChars, drawSelection, dropCursor, rectangularSelection, crosshairCursor, highlightActiveLine } from "@codemirror/view";
export { defaultHighlightStyle, syntaxHighlighting, indentOnInput, bracketMatching, foldGutter, foldKeymap, HighlightStyle } from "@codemirror/language";
export { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
export { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
export { autocompletion, completionKeymap, closeBrackets, closeBracketsKeymap } from "@codemirror/autocomplete";

// Language support
export { javascript } from "@codemirror/lang-javascript";
export { html } from "@codemirror/lang-html";
export { css } from "@codemirror/lang-css";
export { json } from "@codemirror/lang-json";
export { python } from "@codemirror/lang-python";
export { markdown } from "@codemirror/lang-markdown";

// Theme
export { oneDark } from "@codemirror/theme-one-dark";

// Syntax highlighting tags (for building custom themes from terminal palettes)
export { tags } from "@lezer/highlight";
`,
    resolveDir: resolve(__dirname, ".."),
    loader: "js",
  },
  bundle: true,
  minify: true,
  format: "iife",
  globalName: "CM",
  outfile,
  target: ["es2020"],
  logLevel: "info",
});

console.log(`\nCodeMirror 6 bundle written to: ${outfile}`);
