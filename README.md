# Inspekt

**Browser automation and inspection from the command line.**

A powerful CLI tool for browser automation, debugging, and interactive development. Control your browser, inspect elements, extract data, automate tasks, and interact with web pages—all from your terminal.

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/roelvangils/inspekt)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Documentation](https://img.shields.io/badge/docs-mkdocs-blue.svg)](https://roelvangils.github.io/inspekt/)

---

📚 **[Read the Full Documentation →](https://roelvangils.github.io/inspekt/)**

Comprehensive guides, API reference, tutorials, and examples. Beautiful Material theme with search, dark mode, and interactive examples.

> **🛠️ Hacking on Inspekt?** Clone the repo and run `bun run dev` — it brings up the full stack (CLI, browser extension, Browser VM, desktop app) under [overmind](https://github.com/DarthSim/overmind). See **[CONTRIBUTING.md](CONTRIBUTING.md)** for setup, the [`docs/development/`](docs/development/) folder for per-surface guides, and [`docs/architecture.html`](docs/architecture.html) for a visual map of how the pieces wire together.

---

## ✨ Features

- **MCP Server** - Use with Claude Desktop and AI assistants via Model Context Protocol
- **Execute JavaScript** - Run code in your active browser tab from the terminal
- **Interactive REPL** - Live JavaScript experimentation with instant feedback
- **AI Integration** - Article summarization and page descriptions powered by AI
- **Accessibility Testing** - WCAG compliance audits with axe-core, rule-specific checks, auto-element selection
- **Element Interaction** - Click, inspect, highlight, and wait for elements
- **Keyboard Control** - Navigate pages entirely from your keyboard with auto-refocus
- **Data Extraction** - Links, images, tables, metadata, and more
- **File Downloads** - Interactive file finder and downloader
- **Real-time Monitoring** - Watch keyboard events and browser activity
- **Smart Help** - Enhanced help system shows all available flags for each command
- **Fast & Reliable** - WebSocket-based architecture for instant responses

## 🏗️ Architecture Highlights

- **Modular Architecture** - Clean hexagonal design with 4 layers
- **Comprehensive Testing** - 1000+ tests with strong coverage on core services
- **Enhanced Performance** - Eliminated blocking I/O for faster responses
- **Better Documentation** - Complete architecture and security docs
- **Type Safety** - Full type hints with Pydantic validation
- **CI/CD Pipeline** - Automated testing on Python 3.11-3.13

## 📦 Installation

### 1. Install the CLI tool

**Requirements:** macOS (the installer handles everything else, including Python)

```bash
# One-command install (interactive: CLI only, Browser VM, or both)
curl -fsSL https://raw.githubusercontent.com/roelvangils/inspekt/main/install.sh | bash
```

Or from a clone:

```bash
git clone https://github.com/roelvangils/inspekt.git
cd inspekt

./install.sh --cli-only   # fast path, no Docker
# or, if you already have uv:
make dev                  # creates .venv and installs with dev extras
```

### 2. Choose Your Browser Integration

Inspekt works with either a browser extension (recommended) or a userscript. Choose one:

#### Option A: Browser Extension (Recommended)

✅ **Works on all websites** including those with strict Content Security Policy (CSP)
✅ **Bypasses CSP restrictions** on GitHub, Gmail, banking sites, etc.
✅ **No CSP warnings** in the console
✅ **Full page access** in all contexts

**Chrome/Edge:**
1. Open `chrome://extensions/` (or `edge://extensions/`)
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select the `extensions/chrome` directory
5. The extension will connect automatically to `localhost:8766`

**Firefox:**
1. Open `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select `extensions/firefox/manifest.json`

#### Option B: Userscript (Alternative)

⚠️ **Limited by CSP** - won't work on sites like GitHub, Gmail, banking sites
⚠️ **Console warnings** on CSP-protected pages
✅ **Easy to update** via userscript manager
✅ **Works fine** on most regular websites

1. **Install a userscript manager**:
   - [Violentmonkey](https://violentmonkey.github.io/) (recommended)
   - [Tampermonkey](https://www.tampermonkey.net/)
   - [Greasemonkey](https://www.greasespot.net/) (Firefox only)

2. **Create a new userscript** and copy the contents of `userscript_ws.js`

3. **Save and enable** the script

To view the userscript:
```bash
inspekt userscript
```

> **Recommendation:** Use the browser extension for the best experience, especially if you work with sites that have Content Security Policy restrictions.

### 3. Start the bridge server

```bash
# Start (daemonizes bridge + API by default)
inspekt start

# Or keep it in the foreground
inspekt start --foreground

# Check server status
inspekt status
```

## 🚀 Quick Start

### CLI Usage

```bash
# Execute JavaScript code
inspekt eval "document.title"

# Get page information
inspekt info

# Extract all links
inspekt links --only-external

# Run accessibility audit
inspekt axe
inspekt axe --rule color-contrast
inspekt axe --list-rules

# Start interactive REPL
inspekt repl

# Summarize article with AI
inspekt summarize

# Control browser with keyboard
inspekt control

# Get help with all commands and flags
inspekt --help
```

### HTTP API Usage

```bash
# Start the API server (runs on http://localhost:8767)
uvicorn inspekt.app.api.server:app --host 127.0.0.1 --port 8767

# Or in the background
uvicorn inspekt.app.api.server:app --host 127.0.0.1 --port 8767 &

# Check API health
curl http://localhost:8767/health

# Get page information
curl http://localhost:8767/api/extraction/info

# Execute JavaScript
curl -X POST http://localhost:8767/api/execution/eval \
  -H "Content-Type: application/json" \
  -d '{"code": "document.title"}'

# Navigate to a URL
curl -X POST http://localhost:8767/api/navigation/open \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "wait": true}'

# View API documentation
open http://localhost:8767/docs
```

### MCP Server for AI Assistants

Use Inspekt with Claude Desktop and other AI assistants via the Model Context Protocol (MCP):

```bash
# Test MCP server connectivity
inspekt mcp test

# View available tools and resources
inspekt mcp info

# Start MCP server (for use with Claude Desktop)
inspekt mcp start
```

**Configure Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "inspekt": {
      "command": "inspekt",
      "args": ["mcp", "start"]
    }
  }
}
```

Once configured, Claude can:
- Navigate web pages and extract information
- Automate browser interactions through natural language
- Click elements, fill forms, and take screenshots
- Access real-time page data during conversations

**Available Tools:** 15 tools across 6 categories (navigation, execution, extraction, interaction, inspection, storage)

**Available Resources:** 5 read-only resources (current URL, page title, metadata, browser info, connection status)

📚 **[Complete MCP Integration Guide →](docs/MCP_INTEGRATION.md)**

## 📖 Usage Guide

### Execute JavaScript

```bash
# Simple expression
inspekteval "document.title"

# Complex code
inspekteval "Array.from(document.querySelectorAll('a')).map(a => a.href)"

# Show URL and title metadata
inspekteval "document.title" --url --title

# JSON output format
inspekteval "({url: location.href, title: document.title})" --format json

# Execute from file
inspekteval --file script.js
inspektexec script.js

# Use stdin
echo "console.log('Hello')" | inspekteval
cat script.js | inspekteval
```

### Interactive REPL

Start a live JavaScript session:

```bash
inspektrepl
```

Example session:
```javascript
inspekt> document.title
"Example Domain"

inspekt> document.querySelectorAll('p').length
2

inspekt> Array.from(document.links).map(a => a.href)
["https://example.com/page1", "https://example.com/page2"]

inspekt> exit
Goodbye!
```

### Page Information

```bash
# Basic info
inspektinfo

# Extended info (language, meta tags, cookies)
inspektinfo --extended

# JSON output
inspektinfo --json
```

Output:
```
URL:      https://example.com
Title:    Example Domain
Domain:   example.com
Protocol: https:
State:    complete
Size:     1280x720
```

### Element Interaction

**Click elements:**
```bash
# Click by selector
inspektclick "button#submit"

# Double-click
inspektdouble-click "div.editable"

# Right-click (context menu)
inspektright-click "a.download"
```

**Inspect elements:**
```bash
# Inspect by selector
inspektinspect "h1"

# Get details of inspected element
inspektinspected

# In browser DevTools Console, you can also use:
# inspektStore($0)  - Store currently inspected element
# Then: inspektinspected
```

**Highlight elements:**
```bash
# Highlight with default color (red)
inspekthighlight "h1, h2"

# Custom color
inspekthighlight "a" --color blue

# Clear highlights
inspekthighlight --clear
```

**Wait for elements:**
```bash
# Wait for element to exist (default: 30s timeout)
inspektwait "button#submit"

# Wait for element to be visible
inspektwait ".modal-dialog" --visible

# Wait for element to be hidden
inspektwait ".loading-spinner" --hidden

# Wait for text content
inspektwait "div.result" --text "Success"

# Custom timeout
inspektwait "div.notification" --timeout 10
```

### Extract Links

```bash
# Show all links
inspektlinks

# Only URLs (one per line)
inspektlinks --only-urls

# Filter to internal links
inspektlinks --only-internal

# Filter to external links
inspektlinks --only-external

# Sort alphabetically
inspektlinks --alphabetically

# Get enriched metadata (MIME type, size, title, status)
inspektlinks --enrich-external

# Combine filters
inspektlinks --only-external --only-urls --alphabetically
```

**Example output:**
```
→ Home Page
  https://example.com/

↗ External Resource
  https://other-site.com/page

Total: 15 links (8 internal, 7 external)
```

**Practical uses:**
```bash
# Export external links for analysis
inspektlinks --only-external --only-urls > external-links.txt

# Count total links
inspektlinks --only-urls | wc -l

# Find all PDF links
inspektlinks --only-urls | grep "\.pdf$"
```

### Page Outline

Display heading hierarchy:

```bash
inspektoutline
```

Output:
```
H1 Getting Started
   H2 Installation
      H3 Prerequisites
      H3 Setup
   H2 Configuration
      H3 Basic Settings
      H3 Advanced Options
         H4 Environment Variables

Total: 7 headings
```

**Features:**
- Native HTML headings (H1-H6)
- ARIA headings (`role="heading"` with `aria-level`)
- Hierarchical indentation
- Colored output for readability

**Use cases:**
- Accessibility audits
- Verify heading hierarchy
- SEO analysis
- Quick page structure overview

### Accessibility Testing

Run WCAG compliance audits using the industry-standard axe-core library:

```bash
# Full WCAG 2.1 Level AA audit (default)
inspekt axe

# Test specific WCAG level
inspekt axe --level 21aa
inspekt axe --level 2aaa

# Check a specific accessibility rule
inspekt axe --rule color-contrast
inspekt axe --rule link-name
inspekt axe --rule aria-allowed-attr

# List all available rules (~104 rules)
inspekt axe --list-rules

# Include passing checks
inspekt axe --include-passes

# Output as JSON
inspekt axe --json > audit-results.json
```

**Features:**
- **WCAG Standards**: Test against WCAG 2.0/2.1/2.2 (Level A, AA, AAA)
- **104 Accessibility Rules**: Comprehensive coverage of accessibility issues
- **Auto-Element Selection**: Single violations are automatically highlighted in browser
- **Detailed Reports**: CSS selectors, HTML snippets, failure summaries, and help URLs
- **Rule-Specific Checks**: Target specific issues like color contrast, ARIA attributes, etc.

**Example Output:**
```
Running Accessibility Check (Rule: color-contrast)

Rule: color-contrast
Impact: serious
Help: Elements must meet minimum color contrast ratio thresholds
Documentation: https://dequeuniversity.com/rules/axe/4.11/color-contrast

Found 1 violation:

1. [serious]
   Selector: .header__text
   HTML: <span class="header__text">Welcome</span>
   Issue: Element has insufficient color contrast of 3.2:1
          Expected contrast ratio of 4.5:1

✓ Element auto-selected and highlighted in browser
  Run 'inspekt inspected' to view full element details
```

**Disable auto-selection:**
```bash
inspekt axe --rule color-contrast --no-select
```

### AI-Powered Features

**Article Summarization:**

```bash
# Generate concise summary
inspektsummarize

# Show full extracted article
inspektsummarize --format full
```

Requires [mods](https://github.com/charmbracelet/mods) to be installed.

**Page Descriptions for Screen Readers:**

```bash
inspektdescribe
```

Generates a natural-language description perfect for blind users:

```
This webpage is in Dutch, but is also available in English and French.
At the top you can navigate to services, articles, careers, about us
and contact us. The main part contains a rather long article about an
empathy lab with five headings. The footer contains standard links
such as a sitemap and privacy statement.
```

**What it analyzes:**
- Available languages
- Navigation menus
- Page landmarks
- Heading structure
- Main content type and length
- Significant images
- Forms and interactive elements
- Footer utilities

Requires [mods](https://github.com/charmbracelet/mods) to be installed.

### Download Files

Find and download files interactively:

```bash
# Interactive selection
inspektdownload

# List files without downloading
inspektdownload --list

# Custom output directory
inspektdownload --output ~/Downloads
```

**Supported file types:**
- Images (jpg, png, gif, svg, webp)
- Documents (pdf, docx, xlsx, pptx, txt, csv)
- Videos (mp4, webm, avi, mov)
- Audio (mp3, wav, ogg)
- Archives (zip, rar, tar.gz, 7z)

### Keyboard Control Mode

Navigate and interact with pages using only your keyboard:

```bash
inspektcontrol
```

**Controls:**
- `Tab` / `Shift+Tab` - Navigate forward/backward
- `Arrow Keys` - Move focus directionally
- `Enter` / `Space` - Activate focused element
- `Escape` - Return to body
- `q` - Quit control mode

**Features:**
- Auto-refocus after navigation
- Visual feedback with blue outlines
- Real-time terminal announcements
- Optional text-to-speech (macOS)
- Persistent across page loads

**Configuration** (`config.json`):
```json
{
  "control": {
    "verbose": true,       // Terminal announcements
    "speak-all": true,     // Text-to-speech
    "verbose-logging": false
  }
}
```

**Example workflow:**
```bash
inspektcontrol
# Tab to link → Enter → Page loads → Element auto-refocuses → Continue tabbing
```

### Text Selection

```bash
# Get selected text with metadata
inspektselection text

# Get as HTML
inspektselection html

# Get as Markdown
inspektselection markdown

# Raw text only (no formatting)
inspektselection text --raw

# Use in scripts
inspektselection text --raw | pbcopy
inspektselection markdown --raw > selection.md

# Get as JSON (includes markdown)
inspektselection text --json
```

### Type or Paste Text

Type text character by character or paste instantly:

```bash
# Paste text instantly (fastest, clears existing text)
inspektpaste "Hello World"

# Type text at maximum speed (clears existing text)
inspekttype "Hello World"

# Type with human-like random delays (~100 WPM with realistic typos)
inspekttype "Hello, how are you?" --speed 0

# Type at controlled speed (10 characters per second)
inspekttype "test@example.com" --speed 10

# Type without clearing existing text (append mode)
inspekttype "append this" --no-clear

# Paste without clearing (append mode)
inspektpaste " more text" --no-clear

# Type into specific element
inspekttype "password123" --selector "input[type=password]"

# Paste into specific element
inspektpaste "username" --selector "#username"
```

#### Human-like Typing (`--speed 0`)

The `--speed 0` option simulates realistic human typing with random variations:

**Why it's useful:**
- **Bot detection bypass**: Many websites detect automation by analyzing typing patterns. Human-like typing makes your automation look more natural.
- **Form testing**: Test how forms behave with realistic user input timing.
- **Demo recordings**: Create more believable demonstrations or tutorials.
- **Rate limiting**: Some services rate-limit based on input speed; human-like typing avoids triggering these limits.

**How it works:**
- **Base speed**: ~100 WPM (words per minute), similar to fast casual typing
- **Random variation**: Each character has ±50% timing variation (60-180ms per character)
- **Realistic typos**: 3% chance to type wrong adjacent key, then backspace and correct (QWERTY layout)
- **Contextual pauses**:
  - Longer pauses after punctuation (`.!?` = +150-350ms)
  - Slight pauses after commas (`,` = +50-125ms)
  - Occasional thinking pauses after spaces (15% chance = +100-250ms)
  - Slower on numbers and special characters (+30%)

**Example:**
```bash
# Simulate human filling out a form
inspekttype "john.doe@example.com" --speed 0 --selector "#email"
inspekttype "My name is John, and I'm interested in your product." --speed 0 --selector "#message"
```

**Note:** By default, both `type` and `paste` clear any existing text in the input field before inserting new text. Use `--no-clear` to append instead.

### Take Screenshots

```bash
# Screenshot by selector
inspektscreenshot --selector "h1" --output screenshot.png

# Use inspected element ($0 in DevTools)
inspektscreenshot --selector "$0" --output element.png
```

### Navigation

```bash
# Navigate to URL
inspektopen https://example.com

# Navigate and wait for load
inspektopen https://example.com --wait

# Browser history
inspektback
inspektforward

# Reload page
inspektreload

# Hard reload (bypass cache)
inspektreload --hard
```

### Watch Events

Monitor browser activity in real-time:

```bash
# Watch keyboard input
inspektwatch input
```

Output:
```
Watching keyboard input... (Press Ctrl+C to stop)
H e l l o [SPACE] W o r l d [ENTER]
```

### Unified Storage Management

Manage cookies, localStorage, and sessionStorage with a single unified command:

```bash
# List all storage types (cookies, localStorage, sessionStorage)
inspekt storage list
inspekt storage list --all

# List specific storage types
inspekt storage list --cookies
inspekt storage list --local
inspekt storage list --session
inspekt storage list --cookies --local  # Multiple types

# Get a storage item or cookie
inspekt storage get user_token --local
inspekt storage get session_id --cookies
inspekt storage get temp_data --session

# Set a storage item
inspekt storage set user_token abc123 --local
inspekt storage set preferences '{"theme":"dark"}' --session

# Set a cookie with options
inspekt storage set session_id xyz789 --cookies
inspekt storage set auth_token abc --cookies --secure --max-age 3600
inspekt storage set tracking abc --cookies --same-site Strict --path /

# Delete a storage item or cookie
inspekt storage delete user_token --local
inspekt storage delete session_id --cookies

# Clear storage (with confirmation prompt)
inspekt storage clear --all
inspekt storage clear --cookies
inspekt storage clear --local --session

# JSON output for programmatic use
inspekt storage list --json
inspekt storage get user_token --local --json
```

**Cookie-specific options:**
- `--max-age <seconds>` - Cookie lifetime
- `--expires <date>` - Expiration date
- `--path <path>` - Cookie path (default: /)
- `--domain <domain>` - Cookie domain
- `--secure` - HTTPS only
- `--same-site <Strict|Lax|None>` - SameSite attribute

**Legacy Cookie Commands (Deprecated):**

The `inspekt cookies` command is deprecated and will be removed in v2.0.0. Use `inspekt storage --cookies` instead:

```bash
# Old (deprecated)          # New (recommended)
inspekt cookies list        → inspekt storage list --cookies
inspekt cookies get name    → inspekt storage get name --cookies
inspekt cookies set n v     → inspekt storage set n v --cookies
inspekt cookies delete name → inspekt storage delete name --cookies
inspekt cookies clear       → inspekt storage clear --cookies
```

### Robots.txt Inspection

Fetch and parse robots.txt files with RFC 9309 compliance:

```bash
# Inspect robots.txt for current page
inspekt robots

# Get structured JSON output
inspekt robots --json

# Show validation errors and warnings
inspekt robots --validate

# Inspect specific URL directly
inspekt robots --url https://example.com
```

**Features:**
- RFC 9309 compliant parsing (with `protego` library)
- Extracts user-agent groups, rules, and sitemaps
- Shows file metadata (size, encoding, last-modified)
- Validates syntax and reports non-standard directives
- Handles missing robots.txt (404) gracefully
- JSON output includes comments with line numbers

**Install protego for full RFC 9309 compliance:**
```bash
pip install protego
```

## 🎯 Practical Examples

### Web Scraping

```bash
# Extract all product prices
inspekteval "Array.from(document.querySelectorAll('.price')).map(el => el.textContent)"

# Get all image URLs
inspekteval "Array.from(document.images).map(img => img.src)" --format json

# Extract table data
inspektexec inspekt/scripts/extract_table.js --format json > data.json
```

### Authenticated Data Extraction

```bash
# Extract dashboard data (while logged in)
inspekteval "
  Array.from(document.querySelectorAll('.dashboard-item')).map(item => ({
    title: item.querySelector('.title').textContent,
    value: item.querySelector('.value').textContent
  }))
" --format json > dashboard.json
```

### Form Automation

```bash
# Fill form fields
inspekteval "document.querySelector('#email').value = 'user@example.com'"
inspekteval "document.querySelector('#password').value = 'secret'"
inspektclick "button[type=submit]"
inspektwait ".success-message" --visible
```

### Performance Monitoring

```bash
# Page load time
inspekteval "(performance.timing.loadEventEnd - performance.timing.navigationStart) + 'ms'"

# Memory usage
inspekteval "Math.round(performance.memory.usedJSHeapSize / 1048576) + 'MB'"

# Full performance metrics
inspektexec inspekt/scripts/performance_metrics.js --format json
```

### Debugging & Development

```bash
# Check React/Redux state
inspekteval "window.__REDUX_DEVTOOLS_EXTENSION__?.store.getState()" --format json

# Inspect app state
inspekteval "window.myApp?.state" --format json

# Console log monitoring
inspektwatch
```

### SEO Analysis

```bash
# Extract metadata
inspektexec inspekt/scripts/extract_metadata.js --format json

# Get all headings
inspektoutline

# Find broken internal links
inspektlinks --only-internal --only-urls | xargs -I {} curl -s -o /dev/null -w "%{http_code} {}\n" {}

# Check external link status
inspektlinks --enrich-external --json
```

### Shell Integration

```bash
# Use in scripts
TITLE=$(inspekteval "document.title" --format raw)
echo "Current page: $TITLE"

# Monitor for changes
while true; do
  inspekteval "document.querySelectorAll('.notification').length" --format raw
  sleep 5
done

# Process with other tools
inspektlinks --only-urls | grep "github" | sort | uniq
```

## 🛠️ Built-in Scripts

Inspekt includes ready-to-use scripts for common tasks:

```bash
# Extract all images
inspektexec inspekt/scripts/extract_images.js --format json

# Extract table data to JSON
inspektexec inspekt/scripts/extract_table.js --format json > data.json

# Get SEO metadata (Open Graph, Twitter Cards, etc.)
inspektexec inspekt/scripts/extract_metadata.js --format json

# Performance metrics
inspektexec inspekt/scripts/performance_metrics.js --format json

# Inject jQuery
inspektexec inspekt/scripts/inject_jquery.js
# Then use: inspekteval "$('a').length"

# Highlight elements
# Edit inspekt/scripts/highlight_selector.js to change selector
inspektexec inspekt/scripts/highlight_selector.js
```

## 📚 Command Reference

Run `inspekt --help` to see all commands with their available flags and options:

```bash
inspekt --help
```

The enhanced help system shows:
- All available commands
- Complete flag documentation for each command
- Default values
- Usage examples

For command-specific help:
```bash
inspekteval --help
inspektlinks --help
inspektcontrol --help
```

## ⚙️ Configuration

**Server Ports:**
- HTTP: `127.0.0.1:8765` (CLI ⟷ Server)
- WebSocket: `127.0.0.1:8766` (Server ⟷ Browser)

**Config File:** `config.json`

```json
{
  "control": {
    "verbose": true,
    "speak-all": true,
    "verbose-logging": false
  }
}
```

**Customizable Prompts:**
- `prompts/summary.prompt` - AI summarization prompt
- `prompts/describe.prompt` - Page description prompt

## 🌐 HTTP API

Inspekt includes a FastAPI-powered REST API that exposes all CLI commands as HTTP endpoints. This allows you to control the browser from any HTTP client, integrate with other tools, or build web-based frontends.

### Starting the API Server

```bash
# Start the API server
uvicorn inspekt.app.api.server:app --host 127.0.0.1 --port 8767

# Or with auto-reload for development
uvicorn inspekt.app.api.server:app --host 127.0.0.1 --port 8767 --reload

# Or run in the background
uvicorn inspekt.app.api.server:app --host 127.0.0.1 --port 8767 &
```

### Interactive Documentation

FastAPI automatically generates interactive API documentation:

- **Swagger UI**: http://localhost:8767/docs
- **ReDoc**: http://localhost:8767/redoc
- **OpenAPI Schema**: http://localhost:8767/openapi.json

### Available Endpoints

#### Navigation (`/api/navigation/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/open` | POST | Navigate to a URL |
| `/back` | POST | Go back in history |
| `/forward` | POST | Go forward in history |
| `/reload` | POST | Reload current page |
| `/pageup` | POST | Scroll up one page |
| `/pagedown` | POST | Scroll down one page |
| `/top` | POST | Scroll to top |
| `/bottom` | POST | Scroll to bottom |

#### Execution (`/api/execution/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/eval` | POST | Execute JavaScript code |

#### Extraction (`/api/extraction/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/info` | GET | Get page information |
| `/links` | GET | Extract all links |

### Example API Calls

**Health Check:**
```bash
curl http://localhost:8767/health
```

**Get Page Info:**
```bash
curl http://localhost:8767/api/extraction/info | jq
```

**Execute JavaScript:**
```bash
curl -X POST http://localhost:8767/api/execution/eval \
  -H "Content-Type: application/json" \
  -d '{
    "code": "document.querySelector(\"h1\").textContent",
    "timeout": 5.0
  }' | jq
```

**Navigate to URL:**
```bash
curl -X POST http://localhost:8767/api/navigation/open \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "wait": true,
    "timeout": 30
  }' | jq
```

**Extract Links:**
```bash
curl "http://localhost:8767/api/extraction/links?include_text=true" | jq
```

**Scroll Page:**
```bash
curl -X POST http://localhost:8767/api/navigation/pagedown
curl -X POST http://localhost:8767/api/navigation/top
```

### Response Format

All API endpoints return JSON in this format:

```json
{
  "ok": true,
  "result": <command result>,
  "error": null,
  "url": "https://example.com",
  "title": "Page Title"
}
```

When an error occurs:

```json
{
  "ok": false,
  "result": null,
  "error": "Error message here",
  "url": null,
  "title": null
}
```

### HTTP Status Codes

- `200 OK` - Command executed successfully
- `400 Bad Request` - Invalid parameters
- `500 Internal Server Error` - Command execution failed
- `503 Service Unavailable` - Bridge server not running
- `504 Gateway Timeout` - Command timeout

### Architecture

The API follows the same hexagonal architecture as the CLI:

```
HTTP Request → FastAPI Router → Service Layer → Bridge Executor → Browser
                                       ↓
                                  Same services
                                  used by CLI
```

This means:
- ✅ **No code duplication** - CLI and API share the same business logic
- ✅ **Consistent behavior** - Both interfaces produce identical results
- ✅ **Easy maintenance** - Add a new command once, get CLI + API for free
- ✅ **Type safety** - Pydantic models validate all requests/responses

## 🏗 Architecture

Inspekt follows a **hexagonal architecture** with clear separation of concerns:

- **Domain Layer** - Pure business logic with Pydantic models
- **Adapter Layer** - I/O operations (filesystem, WebSocket)
- **Service Layer** - Application services and orchestration
- **Application Layer** - CLI commands and server

This design ensures:
- ✅ High testability (97%+ coverage on services)
- ✅ Clear dependencies (no circular imports)
- ✅ Easy extensibility (add new commands/services)
- ✅ Maintainable codebase (avg 362 lines per module)

See [docs/development/architecture.md](docs/development/architecture.md) for details, or open [`docs/architecture.html`](docs/architecture.html) in a browser for a visual map.

## 🛠 Development

### Running Tests

```bash
# Run all tests
make test

# Run specific test suites
pytest tests/unit/ -v              # Unit tests
pytest tests/integration/ -v       # Integration tests
pytest tests/e2e/ -v               # E2E tests (requires Playwright)

# Check code quality
make lint                          # Linting with ruff
make typecheck                     # Type checking with mypy
make format                        # Auto-format code
```

### Project Structure

```
inspekt/              # repo root
├── inspekt/          # Python package (CLI, bridge, services, scripts)
├── extensions/       # browser extensions (chrome, firefox, shared)
├── vm/               # Docker image for the standalone virtual browser
├── apps/
│   ├── desktop/      # Tauri shell around the VM control panel
│   └── pdf-viewer/   # Tauri PDF accessibility report viewer
├── scripts/          # build/dev helpers (bundle-vm, bump_version, …)
└── docs/             # mkdocs site + architecture.html (visual map)
```

For a visual walk-through of how the three run modes (CLI + extension,
control-panel + VM, Tauri + VM) wire together, open
[`docs/architecture.html`](docs/architecture.html) in a browser.

### Documentation

- [docs/development/architecture.md](docs/development/architecture.md) — System architecture and design
- [docs/architecture.html](docs/architecture.html) — Visual map of CLI / VM / desktop / extension wiring
- [SECURITY.md](SECURITY.md) — Security model and best practices
- [docs/api/protocol.md](docs/api/protocol.md) — WebSocket protocol specification
- [CONTRIBUTING.md](CONTRIBUTING.md) — Development guide
- [archive/REFACTOR_PLAN.md](archive/REFACTOR_PLAN.md) — Historical refactor notes

## 🐛 Troubleshooting

### "Bridge server is not running"

Start the server:
```bash
inspekt start
```

### "No response from browser"

1. Verify userscript is installed and enabled
2. Open a browser tab (userscript only works in visible tabs)
3. Check browser console for errors
4. Ensure WebSocket connection is established

### Commands timeout

```bash
# Increase timeout
inspekteval "slow_operation()" --timeout 30

# Check if tab is active (inactive tabs may throttle execution)
```

### WebSocket connection issues

```bash
# Restart the server
inspekt stop
inspekt start

# Check server status
inspekt status

# View server logs
inspekt start  # (foreground mode to see logs)
```


## 📝 License

MIT License - see [LICENSE](LICENSE) file for details

## 👏 Credits

Created by **Roel van Gils**

Inspired by the original KM JS Bridge concept.

Special thanks to:
- [Mozilla Readability](https://github.com/mozilla/readability) for article extraction
- [mods](https://github.com/charmbracelet/mods) for AI integration
- The open-source community

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines and [docs/development/architecture.md](docs/development/architecture.md) for system design details.

## 📖 More Resources

- **[docs/guide/examples.md](docs/guide/examples.md)** — 50+ real-world use cases and workflows
- **GitHub Issues** - Bug reports and feature requests
- **Wiki** - Additional documentation and guides

---

**Inspekt v2.0.0** - Control your browser from the command line.
