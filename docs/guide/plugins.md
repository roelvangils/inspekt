# Plugins

Manage and run custom JavaScript plugins (bookmarklets) from the CLI, API, MCP, or web dashboard. Plugins let you save reusable code snippets that execute in your browser context.

## Overview

Inspekt Plugins transform bookmarklets and custom JavaScript into managed, reusable tools that you can:

- **Run from CLI**: `inspekt plugin run my-plugin`
- **Expose as MCP tools**: Let AI agents execute your plugins
- **Manage via web dashboard**: Edit, test, and organize with a full-featured code editor
- **Import/Export**: Share plugins between machines or with colleagues

---

## Quick Start

### Run a Plugin

```bash
# List all plugins
inspekt plugin list

# Run a plugin by name or ID
inspekt plugin run "Text Spacing"

# Run with JSON output
inspekt plugin run accessibility-checker --json
```

### Manage via Web Dashboard

```bash
# Open the plugins dashboard
inspekt plugins
# Or navigate to: http://localhost:8765/plugins
```

---

## Adding Plugins

### From the Web Dashboard

1. Click **Add Plugin** in the header
2. Choose your import method:
   - **From Bookmarklet URL**: Paste a `javascript:...` URL
   - **Paste Code**: Enter raw JavaScript directly
3. Give your plugin a name and click **Add Plugin**

### From a Bookmarklet URL

This is the easiest way to import existing bookmarklets you've collected.

**What is a bookmarklet?**

A bookmarklet is a browser bookmark that contains JavaScript code instead of a URL. They start with `javascript:` and are typically URL-encoded.

**Example bookmarklet URL:**
```
javascript:(function()%7Balert(%22Hello%22)%7D)()
```

**How to import:**

1. Copy the bookmarklet URL from your browser's bookmark bar (right-click > Edit > copy the URL)
2. In the Add Plugin modal, select "From Bookmarklet URL"
3. Paste the URL into the "Bookmarklet URL" field
4. Enter a descriptive name
5. Click "Add Plugin"

**What happens behind the scenes:**

1. The `javascript:` prefix is stripped
2. The code is URL-decoded (e.g., `%7B` becomes `{`)
3. The code is optionally prettified for readability
4. A new plugin is created with the clean JavaScript

**Before:**
```
javascript:(function()%7Bvar%20d%3Ddocument%2Cs%3Dd.createElement(%27style%27)%3Bs.textContent%3D%27*%7Bline-height%3A1.5%21important%7D%27%3Bd.head.appendChild(s)%7D)()
```

**After:**
```javascript
(function () {
  var d = document,
    s = d.createElement('style');
  s.textContent = '* { line-height: 1.5 !important }';
  d.head.appendChild(s);
})();
```

### From Raw Code

If you have JavaScript code (not a bookmarklet URL), use the "Paste Code" tab:

```javascript
// Extract all headings
(function() {
  const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');
  return Array.from(headings).map(h => ({
    level: h.tagName,
    text: h.textContent.trim()
  }));
})();
```

### Via CLI

```bash
# Create from code
inspekt plugin create "My Plugin" --code "(function() { alert('hello'); })()"

# Create from file
inspekt plugin create "My Plugin" --file script.js
```

### Via API

```bash
# Create from bookmarklet
curl -X POST http://localhost:8765/api/plugins/from-bookmarklet \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Text Spacing",
    "bookmarklet": "javascript:(function()%7Balert(%22hello%22)%7D)()"
  }'

# Create from code
curl -X POST http://localhost:8765/api/plugins \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Plugin",
    "code": "(function() { return document.title; })()"
  }'
```

---

## Plugin Properties

| Property | Description |
|----------|-------------|
| **Name** | Display name for the plugin |
| **Category** | Optional grouping (e.g., "a11y", "utility", "dev") |
| **Description** | What the plugin does |
| **Credits** | Original author, source URL, license info |
| **Code** | The JavaScript to execute |
| **Returns Data** | Whether the plugin returns a value |
| **MCP Exposed** | Make available as an MCP tool for AI agents |
| **Unload Behavior** | How to reverse the plugin's effects |

---

## Unload Behavior

Some plugins inject styles or modify the DOM. The unload feature lets you reverse these changes.

### Unload Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **Toggle** | Run the same code again to unload | Self-toggling plugins (e.g., dark mode) |
| **Custom** | Run separate unload code | When reversal needs different logic |
| **Not Reversible** | No unload support | One-time actions (e.g., form submission) |

### Example: Toggle Mode

A plugin that adds then removes a CSS class:

```javascript
(function() {
  document.body.classList.toggle('debug-mode');
})();
```

First run adds the class, second run removes it.

### Example: Custom Unload Code

**Main code:**
```javascript
(function() {
  const style = document.createElement('style');
  style.id = 'my-plugin-styles';
  style.textContent = '* { outline: 1px solid red !important }';
  document.head.appendChild(style);
})();
```

**Unload code:**
```javascript
(function() {
  const style = document.getElementById('my-plugin-styles');
  if (style) style.remove();
})();
```

### Unload via CLI

```bash
# Unload a plugin
inspekt plugin unload "Text Spacing"
```

---

## MCP Integration

Expose plugins as MCP tools that AI agents can use.

### Enable MCP for a Plugin

1. Edit the plugin in the web dashboard
2. Check "Expose as MCP tool"
3. Save the plugin

### How It Works

When MCP is enabled, the plugin becomes available as an MCP tool:

```
mcp__inspekt__run_plugin_{slug}
```

For example, a plugin named "Text Spacing" becomes:

```
mcp__inspekt__run_plugin_text_spacing
```

### AI Agent Usage

AI agents can then call your plugin:

```
Use the text spacing plugin to improve readability on this page.
```

The agent will call `mcp__inspekt__run_plugin_text_spacing` and execute your code in the browser.

---

## Web Dashboard Features

### Code Editor

The built-in CodeMirror 6 editor provides:

- **Syntax highlighting** for JavaScript
- **Syntax error detection** with inline markers
- **Format button** - Prettify code with Prettier
- **Copy button** - Copy code to clipboard
- **Fullscreen mode** - Press Escape to exit

### Test Execution

Click **Test** to run the plugin in your current browser tab. The console panel shows:

- Console output (`log`, `warn`, `error`, `info`)
- Return values
- Execution time

### Import/Export

**Export:**
Click **Export** to download all plugins as JSON.

**Import:**
Click **Import** to upload a JSON file. Choose how to handle conflicts:

- **Skip existing**: Don't overwrite existing plugins
- **Replace existing**: Overwrite plugins with same ID

---

## CLI Commands

```bash
# List all plugins
inspekt plugin list
inspekt plugin list --json

# Show plugin details
inspekt plugin show <name-or-id>

# Run a plugin
inspekt plugin run <name-or-id>
inspekt plugin run <name-or-id> --json

# Unload a plugin (if supported)
inspekt plugin unload <name-or-id>

# Create a plugin
inspekt plugin create "Name" --code "..."
inspekt plugin create "Name" --file script.js

# Delete a plugin
inspekt plugin delete <name-or-id>
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/plugins` | List all plugins |
| `POST` | `/api/plugins` | Create plugin from code |
| `POST` | `/api/plugins/from-bookmarklet` | Create from bookmarklet URL |
| `GET` | `/api/plugins/{id}` | Get plugin details |
| `PUT` | `/api/plugins/{id}` | Update plugin |
| `DELETE` | `/api/plugins/{id}` | Delete plugin |
| `POST` | `/api/plugins/{id}/run` | Execute plugin |
| `POST` | `/api/plugins/{id}/unload` | Unload plugin |
| `POST` | `/api/plugins/test` | Test code without saving |
| `GET` | `/api/plugins/export` | Export all as JSON |
| `POST` | `/api/plugins/import` | Import from JSON |

---

## Example Plugins

### Accessibility: Text Spacing

WCAG 2.1 text spacing test:

```javascript
(function () {
  const style = document.createElement('style');
  style.id = 'wcag-text-spacing';
  style.textContent = `
    * {
      line-height: 1.5 !important;
      letter-spacing: 0.12em !important;
      word-spacing: 0.16em !important;
    }
    p { margin-bottom: 2em !important; }
  `;
  document.head.appendChild(style);
})();
```

### Utility: Show All Images

Display all images with their alt text:

```javascript
(function () {
  const images = document.querySelectorAll('img');
  return Array.from(images).map(img => ({
    src: img.src,
    alt: img.alt || '(no alt)',
    width: img.naturalWidth,
    height: img.naturalHeight
  }));
})();
```

### Debug: Highlight Focus

Show focus indicator on all focusable elements:

```javascript
(function () {
  const style = document.createElement('style');
  style.textContent = `
    :focus {
      outline: 3px solid #f00 !important;
      outline-offset: 2px !important;
    }
  `;
  document.head.appendChild(style);
})();
```

---

## Best Practices

### 1. Use IIFEs

Wrap code in Immediately Invoked Function Expressions to avoid polluting the global scope:

```javascript
(function () {
  // Your code here
})();
```

### 2. Return Structured Data

When extracting data, return structured objects:

```javascript
(function () {
  return {
    title: document.title,
    url: location.href,
    linkCount: document.links.length
  };
})();
```

### 3. Add Cleanup IDs

When injecting elements, use IDs for easy removal:

```javascript
// Inject
const style = document.createElement('style');
style.id = 'my-unique-plugin-id';
document.head.appendChild(style);

// Remove later
document.getElementById('my-unique-plugin-id')?.remove();
```

### 4. Handle Missing Elements

Use optional chaining and nullish coalescing:

```javascript
const text = document.querySelector('.may-not-exist')?.textContent ?? 'Not found';
```

### 5. Document Your Plugins

Use the Credits field to note:

- Original author or source
- License information
- Related documentation links

---

## Troubleshooting

### Plugin Doesn't Run

1. Check browser console for JavaScript errors
2. Verify the server is running (`inspekt status`)
3. Test the code in the web dashboard first

### Bookmarklet Import Fails

1. Ensure the URL starts with `javascript:`
2. Check for proper URL encoding
3. Try pasting the decoded code directly

### MCP Tools Not Appearing

1. Verify "Expose as MCP tool" is checked
2. Restart your MCP client (e.g., Claude Code)
3. Check MCP server connection (`/mcp` in Claude Code)

---

## See Also

- [JavaScript Execution](javascript-execution.md) - Run arbitrary JavaScript
- [MCP Integration](../MCP_INTEGRATION.md) - AI agent integration
- [API Reference](../api/http-api.md) - Full API documentation
