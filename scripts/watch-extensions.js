#!/usr/bin/env node

/**
 * Extension File Watcher
 *
 * Watches extension HTML/CSS/JS files for changes and provides
 * clear instructions for reloading extensions during development.
 *
 * Usage: npm run watch:extensions
 */

const chokidar = require('chokidar');
const path = require('path');

// ANSI color codes for terminal output
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  cyan: '\x1b[36m',
  yellow: '\x1b[33m',
  green: '\x1b[32m',
  blue: '\x1b[34m',
};

console.log(`${colors.bright}${colors.cyan}👀 Watching extension files for changes...${colors.reset}\n`);
console.log(`${colors.yellow}Monitoring:${colors.reset}`);
console.log(`  - extensions/chrome/**/*.{html,css,js}`);
console.log(`  - extensions/shared/**/*.{html,css,js}`);
console.log(`  - extensions/firefox/**/*.{html,css,js}`);
console.log();

// Create file watcher
const watcher = chokidar.watch([
  'extensions/chrome/**/*.html',
  'extensions/chrome/**/*.css',
  'extensions/chrome/**/*.js',
  'extensions/shared/**/*.html',
  'extensions/shared/**/*.css',
  'extensions/shared/**/*.js',
  'extensions/firefox/**/*.html',
  'extensions/firefox/**/*.css',
  'extensions/firefox/**/*.js',
], {
  ignored: [
    /(^|[\/\\])\../,  // Ignore dotfiles
    '**/node_modules/**',
    '**/build/**',
    '**/*.zip',
    '**/*.xpi',
  ],
  persistent: true,
  ignoreInitial: true,
});

// Track which component was changed
function getComponentType(filePath) {
  if (filePath.includes('/popup/')) {
    return 'popup';
  } else if (filePath.includes('panel.')) {
    return 'panel';
  } else if (filePath.includes('devtools.')) {
    return 'devtools';
  } else if (filePath.includes('/modules/') || filePath.includes('/components/')) {
    return 'panel-module';
  }
  return 'other';
}

function getFileType(filePath) {
  const ext = path.extname(filePath);
  return ext.substring(1).toUpperCase();
}

function printReloadInstructions(componentType, filePath) {
  const fileType = getFileType(filePath);
  const fileName = path.basename(filePath);

  console.log(`${colors.bright}${colors.green}✨ File changed:${colors.reset} ${colors.cyan}${filePath}${colors.reset}`);
  console.log(`${colors.yellow}Component:${colors.reset} ${componentType} (${fileType})`);
  console.log();

  if (componentType === 'popup') {
    console.log(`${colors.bright}${colors.blue}📝 Reload Steps:${colors.reset}`);
    console.log(`  1. Go to ${colors.cyan}chrome://extensions${colors.reset} (or press ${colors.yellow}Ctrl+Shift+R${colors.reset} if shortcut configured)`);
    console.log(`  2. Click ${colors.green}reload icon${colors.reset} on Inspekt extension card`);
    console.log(`  3. Click ${colors.green}extension icon${colors.reset} in toolbar to see changes`);
  } else if (componentType === 'panel' || componentType === 'panel-module') {
    console.log(`${colors.bright}${colors.blue}📝 Reload Steps (DevTools Panel):${colors.reset}`);
    console.log(`  1. Go to ${colors.cyan}chrome://extensions${colors.reset} (or press ${colors.yellow}Ctrl+Shift+R${colors.reset} if shortcut configured)`);
    console.log(`  2. Click ${colors.green}reload icon${colors.reset} on Inspekt extension card`);
    console.log(`  3. ${colors.bright}${colors.yellow}Close DevTools completely${colors.reset} (Ctrl+Shift+I)`);
    console.log(`  4. ${colors.bright}${colors.yellow}Reopen DevTools${colors.reset} (Ctrl+Shift+I)`);
    console.log(`  5. Click ${colors.green}"Inspekt"${colors.reset} panel tab`);
    console.log();
    console.log(`  ${colors.yellow}Note:${colors.reset} CSS-only changes might work with just DevTools close/reopen`);
  } else if (componentType === 'devtools') {
    console.log(`${colors.bright}${colors.blue}📝 Reload Steps:${colors.reset}`);
    console.log(`  1. Go to ${colors.cyan}chrome://extensions${colors.reset} (or press ${colors.yellow}Ctrl+Shift+R${colors.reset} if shortcut configured)`);
    console.log(`  2. Click ${colors.green}reload icon${colors.reset} on Inspekt extension card`);
    console.log(`  3. ${colors.bright}${colors.yellow}Close and reopen DevTools${colors.reset}`);
  } else {
    console.log(`${colors.bright}${colors.blue}📝 Reload Steps:${colors.reset}`);
    console.log(`  1. Go to ${colors.cyan}chrome://extensions${colors.reset} (or press ${colors.yellow}Ctrl+Shift+R${colors.reset} if shortcut configured)`);
    console.log(`  2. Click ${colors.green}reload icon${colors.reset} on Inspekt extension card`);
  }

  console.log();
  console.log(`${colors.cyan}${'─'.repeat(80)}${colors.reset}\n`);
}

// Watch for file changes
watcher.on('change', (filePath) => {
  const componentType = getComponentType(filePath);
  printReloadInstructions(componentType, filePath);
});

// Handle errors
watcher.on('error', (error) => {
  console.error(`${colors.bright}${colors.yellow}⚠️  Watcher error:${colors.reset}`, error);
});

// Graceful shutdown
process.on('SIGINT', () => {
  console.log(`\n${colors.cyan}👋 Stopping file watcher...${colors.reset}`);
  watcher.close();
  process.exit(0);
});
