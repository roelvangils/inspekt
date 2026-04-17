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
 * Usage:
 *   bun scripts/bundle-vm.mjs            # one-shot
 *   bun scripts/bundle-vm.mjs --watch    # re-bundle on change, stays alive
 */

import { readFileSync, writeFileSync, mkdirSync, watch } from "node:fs";
import { resolve, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { transformSync } from "esbuild";

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(__dirname, "..");
const vmDir = resolve(projectRoot, "vm");
const distDir = resolve(vmDir, "dist");

const watchMode = process.argv.includes("--watch");

function extractPaths(html, startMarker, endMarker, attrPattern) {
  const re = new RegExp(`${startMarker}([\\s\\S]*?)${endMarker}`);
  const block = html.match(re);
  if (!block) throw new Error(`Markers ${startMarker} / ${endMarker} not found in HTML`);
  return [...block[1].matchAll(attrPattern)].map((m) => m[1]);
}

function concat(paths) {
  return paths
    .map((p) => {
      const filePath = resolve(vmDir, p.replace(/^\//, ""));
      try {
        return readFileSync(filePath, "utf8");
      } catch {
        throw new Error(`File not found: ${filePath} (from ${p})`);
      }
    })
    .join("\n");
}

function bundleOnce() {
  const html = readFileSync(resolve(vmDir, "control-panel.html"), "utf8");

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

  const cssResult = transformSync(concat(cssPaths), {
    loader: "css", minify: true, target: ["chrome120"],
  });
  const jsResult = transformSync(concat(jsPaths), {
    loader: "js", minify: true, target: ["chrome120"],
  });

  mkdirSync(distDir, { recursive: true });
  writeFileSync(resolve(distDir, "app.min.css"), cssResult.code);
  writeFileSync(resolve(distDir, "app.min.js"), jsResult.code);

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

  const cssKB = (cssResult.code.length / 1024).toFixed(1);
  const jsKB = (jsResult.code.length / 1024).toFixed(1);
  const ts = new Date().toLocaleTimeString();
  console.log(
    `[${ts}] Bundled ${cssPaths.length} CSS (${cssKB} KB) + ${jsPaths.length} JS (${jsKB} KB) → vm/dist/`
  );
}

bundleOnce();

if (!watchMode) {
  process.exit(0);
}

// --- Watch mode ---

console.log(`Watching vm/{control-panel.html,css,js} — Ctrl+C to stop`);

const debounceMs = 120;
let pending = null;

function schedule() {
  if (pending) clearTimeout(pending);
  pending = setTimeout(() => {
    pending = null;
    try {
      bundleOnce();
    } catch (err) {
      console.error(`[bundle error] ${err.message}`);
    }
  }, debounceMs);
}

// Watch the three things that feed into the bundle.
for (const target of ["control-panel.html", "css", "js"]) {
  const p = join(vmDir, target);
  try {
    watch(p, { recursive: true }, (_evt, filename) => {
      if (!filename) return schedule();
      if (/\.(css|js|html)$/.test(filename)) schedule();
    });
  } catch (err) {
    console.error(`[watch error] could not watch ${target}: ${err.message}`);
  }
}

process.on("SIGINT", () => {
  console.log("\nStopping bundler");
  process.exit(0);
});
