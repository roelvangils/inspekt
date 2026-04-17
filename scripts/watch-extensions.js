#!/usr/bin/env bun

/**
 * Extension File Watcher (bun-native)
 *
 * Watches extensions/{chrome,firefox,shared}/ for changes and prints
 * targeted reload instructions. Zero deps — uses fs.watch with
 * { recursive: true }, supported natively by bun on macOS, Linux, Windows.
 *
 * Usage: bun scripts/watch-extensions.js  (or `make dev-extension`)
 */

import { watch } from "node:fs";
import { extname, basename, join, relative } from "node:path";

const ROOT = process.cwd();
const ROOTS = ["extensions/chrome", "extensions/shared", "extensions/firefox"];
const WATCH_EXT = new Set([".html", ".css", ".js"]);
const IGNORE_SEGMENTS = ["node_modules", "build", ".DS_Store"];

const C = {
  reset: "\x1b[0m",
  bold:  "\x1b[1m",
  cyan:  "\x1b[36m",
  yellow:"\x1b[33m",
  green: "\x1b[32m",
  blue:  "\x1b[34m",
  dim:   "\x1b[2m",
};

console.log(`${C.bold}${C.cyan}Watching extension files for changes…${C.reset}`);
for (const r of ROOTS) {
  console.log(`${C.dim}monitoring${C.reset} ${r}/**/*.{html,css,js}`);
}

function shouldIgnore(file) {
  if (!WATCH_EXT.has(extname(file))) return true;
  if (IGNORE_SEGMENTS.some((seg) => file.includes(`/${seg}/`))) return true;
  if (basename(file).startsWith(".")) return true;
  return false;
}

function componentType(file) {
  if (file.includes("/popup/")) return "popup";
  if (file.includes("panel.")) return "panel";
  if (file.includes("devtools.")) return "devtools";
  if (file.includes("/modules/") || file.includes("/components/")) return "panel-module";
  return "other";
}

function printReloadSteps(type, file) {
  const rel = relative(ROOT, file);
  const ext = extname(file).slice(1).toUpperCase();
  console.log(`${C.bold}${C.green}changed${C.reset} ${C.cyan}${rel}${C.reset} ${C.dim}(${type} · ${ext})${C.reset}`);

  const steps = {
    popup: [
      `Go to ${C.cyan}chrome://extensions${C.reset}`,
      `Click ${C.green}reload${C.reset} on the Inspekt card`,
      `Click the extension icon to re-open the popup`,
    ],
    panel: [
      `Go to ${C.cyan}chrome://extensions${C.reset}`,
      `Click ${C.green}reload${C.reset} on the Inspekt card`,
      `${C.yellow}Close${C.reset} DevTools (${C.dim}Ctrl+Shift+I${C.reset})`,
      `${C.yellow}Reopen${C.reset} DevTools`,
      `Select the ${C.green}Inspekt${C.reset} panel tab`,
    ],
    "panel-module": [
      `Go to ${C.cyan}chrome://extensions${C.reset}`,
      `Click ${C.green}reload${C.reset} on the Inspekt card`,
      `${C.yellow}Close${C.reset} and ${C.yellow}reopen${C.reset} DevTools`,
      `Select the ${C.green}Inspekt${C.reset} panel tab`,
    ],
    devtools: [
      `Go to ${C.cyan}chrome://extensions${C.reset}`,
      `Click ${C.green}reload${C.reset} on the Inspekt card`,
      `${C.yellow}Close and reopen${C.reset} DevTools`,
    ],
    other: [
      `Go to ${C.cyan}chrome://extensions${C.reset}`,
      `Click ${C.green}reload${C.reset} on the Inspekt card`,
    ],
  }[type];

  for (let i = 0; i < steps.length; i++) {
    console.log(`${C.dim}${i + 1}.${C.reset} ${steps[i]}`);
  }
  console.log(`${C.dim}${"─".repeat(60)}${C.reset}`);
}

// Debounce: many editors fire multiple events per save.
const recent = new Map();
const DEBOUNCE_MS = 150;

for (const root of ROOTS) {
  try {
    watch(join(ROOT, root), { recursive: true }, (_evt, filename) => {
      if (!filename) return;
      const full = join(ROOT, root, filename);
      if (shouldIgnore(full)) return;

      const now = Date.now();
      const last = recent.get(full) ?? 0;
      if (now - last < DEBOUNCE_MS) return;
      recent.set(full, now);

      printReloadSteps(componentType(full), full);
    });
  } catch (err) {
    console.error(`${C.yellow}[warn] could not watch ${root}:${C.reset}`, err.message);
  }
}

process.on("SIGINT", () => {
  console.log(`\n${C.cyan}stopping file watcher${C.reset}`);
  process.exit(0);
});
