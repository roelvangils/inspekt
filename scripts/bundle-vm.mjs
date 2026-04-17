#!/usr/bin/env bun

/**
 * Bundle control panel CSS + JS for production.
 *
 * Reads vm/control-panel.html, extracts file lists from
 * APP_CSS_START/END and APP_JS_START/END marker comments, concatenates
 * them in order, minifies with esbuild, and writes:
 *
 *   vm/dist/control.html  (production HTML with bundle refs)
 *   vm/dist/app.min.css   (all app CSS, minified)
 *   vm/dist/app.min.js    (all app JS, minified)
 *
 * Usage: bun scripts/bundle-vm.mjs
 */

import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { transformSync } from "esbuild";

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, "..");
const vmDir = resolve(projectRoot, "vm");
const distDir = resolve(vmDir, "dist");

// --- Parse HTML markers ---

const html = readFileSync(resolve(vmDir, "control-panel.html"), "utf8");

function extractPaths(html, startMarker, endMarker, attrPattern) {
  const re = new RegExp(`${startMarker}([\\s\\S]*?)${endMarker}`);
  const block = html.match(re);
  if (!block) throw new Error(`Markers ${startMarker} / ${endMarker} not found in HTML`);
  return [...block[1].matchAll(attrPattern)].map((m) => m[1]);
}

const cssPaths = extractPaths(
  html,
  "<!-- APP_CSS_START -->",
  "<!-- APP_CSS_END -->",
  /href="([^"]+\.css)"/g
);

const jsPaths = extractPaths(
  html,
  "<!-- APP_JS_START -->",
  "<!-- APP_JS_END -->",
  /src="([^"]+\.js)"/g
);

if (cssPaths.length === 0) throw new Error("No CSS files found between markers");
if (jsPaths.length === 0) throw new Error("No JS files found between markers");

// --- Concatenate source files ---

function concat(paths) {
  return paths
    .map((p) => {
      const filePath = resolve(vmDir, p.replace(/^\//, ""));
      try {
        return readFileSync(filePath, "utf8");
      } catch (err) {
        throw new Error(`File not found: ${filePath} (from ${p})`);
      }
    })
    .join("\n");
}

const cssSource = concat(cssPaths);
const jsSource = concat(jsPaths);

// --- Minify with esbuild ---

const cssResult = transformSync(cssSource, {
  loader: "css",
  minify: true,
  target: ["chrome120"],
});

const jsResult = transformSync(jsSource, {
  loader: "js",
  minify: true,
  target: ["chrome120"],
});

// --- Write bundles ---

mkdirSync(distDir, { recursive: true });
writeFileSync(resolve(distDir, "app.min.css"), cssResult.code);
writeFileSync(resolve(distDir, "app.min.js"), jsResult.code);

// --- Generate production HTML ---

const prodHtml = html
  .replace(
    /<!-- APP_CSS_START -->[\s\S]*?<!-- APP_CSS_END -->/,
    '<!-- Bundled CSS -->\n    <link rel="stylesheet" href="/dist/app.min.css">'
  )
  .replace(
    /<!-- APP_JS_START -->[\s\S]*?<!-- APP_JS_END -->/,
    '<!-- Bundled JS -->\n    <script src="/dist/app.min.js" defer></script>'
  );

writeFileSync(resolve(distDir, "control.html"), prodHtml);

// --- Report ---

const cssKB = (cssResult.code.length / 1024).toFixed(1);
const jsKB = (jsResult.code.length / 1024).toFixed(1);
const cssCount = cssPaths.length;
const jsCount = jsPaths.length;

console.log(
  `Bundled ${cssCount} CSS (${cssKB} KB) + ${jsCount} JS (${jsKB} KB) → dist/`
);
