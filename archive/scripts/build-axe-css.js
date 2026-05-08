#!/usr/bin/env node
/**
 * Build script for Axe Popover CSS
 *
 * Concatenates modular CSS files, minifies them, and updates
 * the embedded CSS in run_axe.js for production use.
 *
 * Usage: npm run build:axe-css
 */

const fs = require('fs');
const path = require('path');

const CSS_DIR = path.join(__dirname, '..', 'inspekt', 'scripts', 'axe-popover');
const RUN_AXE_PATH = path.join(__dirname, '..', 'inspekt', 'scripts', 'run_axe.js');

// Order matters - matches @import order in index.css
const CSS_FILES = [
  'tokens.css',
  'base.css',
  'nav.css',
  'content.css',
  'badges.css',
  'animations.css',
  'themes.css'
];

/**
 * Basic CSS minification (no dependencies required)
 */
function minifyCSS(css) {
  return css
    // Remove comments (but keep important ones)
    .replace(/\/\*(?!\!)[^*]*\*+([^/*][^*]*\*+)*\//g, '')
    // Remove newlines and multiple spaces
    .replace(/\s+/g, ' ')
    // Remove spaces around punctuation
    .replace(/\s*([{};:,>~+])\s*/g, '$1')
    // Remove trailing semicolons before closing braces
    .replace(/;}/g, '}')
    // Remove spaces in selectors
    .replace(/\s*([()])\s*/g, '$1')
    // Trim
    .trim();
}

/**
 * Read and concatenate all CSS files
 */
function buildCSS() {
  let combined = '';

  // Extract Google Fonts import from tokens.css first
  const tokensContent = fs.readFileSync(path.join(CSS_DIR, 'tokens.css'), 'utf8');
  const fontImportMatch = tokensContent.match(/@import url\([^)]+\);/);
  if (fontImportMatch) {
    combined = fontImportMatch[0];
  }

  // Concatenate all files
  for (const file of CSS_FILES) {
    const filePath = path.join(CSS_DIR, file);
    let content = fs.readFileSync(filePath, 'utf8');

    // Remove @import statements (we handle fonts separately)
    content = content.replace(/@import url\([^)]+\);/g, '');

    // Remove file header comments
    content = content.replace(/\/\*\*[\s\S]*?\*\//g, '');

    combined += content;
  }

  return minifyCSS(combined);
}

/**
 * Update the getPopoverCSS() function in run_axe.js
 */
function updateRunAxe(minifiedCSS) {
  let content = fs.readFileSync(RUN_AXE_PATH, 'utf8');

  // Escape backticks and ${} for template literal
  const escapedCSS = minifiedCSS
    .replace(/\\/g, '\\\\')
    .replace(/`/g, '\\`')
    .replace(/\$\{/g, '\\${');

  // Find and replace the getPopoverCSS function body
  const regex = /(function getPopoverCSS\(\) \{\s*return `)[^`]*(`;)/;

  if (!regex.test(content)) {
    console.error('Could not find getPopoverCSS() function in run_axe.js');
    process.exit(1);
  }

  content = content.replace(regex, `$1${escapedCSS}$2`);

  fs.writeFileSync(RUN_AXE_PATH, content, 'utf8');
}

// Main
console.log('Building Axe Popover CSS…');
console.log(`  Source: ${CSS_DIR}`);

const minifiedCSS = buildCSS();
const originalSize = CSS_FILES.reduce((sum, file) => {
  return sum + fs.statSync(path.join(CSS_DIR, file)).size;
}, 0);

console.log(`  Original: ${(originalSize / 1024).toFixed(1)} KB (${CSS_FILES.length} files)`);
console.log(`  Minified: ${(minifiedCSS.length / 1024).toFixed(1)} KB`);
console.log(`  Reduction: ${((1 - minifiedCSS.length / originalSize) * 100).toFixed(0)}%`);

updateRunAxe(minifiedCSS);
console.log(`  Updated: ${RUN_AXE_PATH}`);
console.log('Done!');
