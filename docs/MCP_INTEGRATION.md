# MCP Integration Guide for Inspekt

This guide explains how to use Inspekt as an MCP (Model Context Protocol) server with AI assistants like Claude Desktop and ChatGPT.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Available Tools](#available-tools)
- [Available Resources](#available-resources)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)
- [Advanced Configuration](#advanced-configuration)

---

## Overview

The Inspekt MCP Server exposes browser automation capabilities as **tools** (actions) and **resources** (read-only data) that AI assistants can use during conversations.

### What is MCP?

The Model Context Protocol (MCP) is an open protocol that enables AI models to interact with external tools and data sources in a standardized way. By running Inspekt as an MCP server, you can:

- Let Claude navigate web pages and extract information during conversations
- Automate browser interactions through natural language
- Access real-time browser state as context for AI responses
- Build AI-powered web automation workflows

### Architecture

```
┌─────────────────┐
│ Claude Desktop  │
│  (or other AI)  │
└────────┬────────┘
         │ MCP Protocol (stdio)
         ▼
┌─────────────────┐
│ Inspekt MCP     │
│ Server          │
└────────┬────────┘
         │ HTTP/WebSocket
         ▼
┌─────────────────┐
│ Bridge Server   │
│ (inspekt)       │
└────────┬────────┘
         │ WebSocket
         ▼
┌─────────────────┐
│ Browser         │
│ (Chrome/Firefox)│
└─────────────────┘
```

---

## Prerequisites

Before setting up the MCP server, ensure you have:

1. **Python 3.11 or higher**
2. **Inspekt installed** (`pip install inspekt` or installed from source)
3. **Bridge server running** (required for browser communication)
4. **Browser with Inspekt extension or userscript installed**
5. **Claude Desktop** (or another MCP-compatible AI client)

---

## Installation

### Step 1: Install Inspekt with MCP Support

If you already have Inspekt installed, update to get MCP support:

```bash
pip install --upgrade inspekt
```

Or install from source:

```bash
git clone https://github.com/roelvangils/inspekt.git
cd inspekt
pip install -e .
```

### Step 2: Verify Installation

Check that the MCP commands are available:

```bash
inspekt mcp --help
```

You should see:

```
Usage: inspekt mcp [OPTIONS] COMMAND [ARGS]...

  Manage the MCP server for AI assistant integration.

Commands:
  info   Show information about available MCP tools and resources.
  start  Start the MCP server in stdio mode.
  test   Test MCP server connectivity and basic functionality.
```

### Step 3: Start the Bridge Server

The MCP server requires the bridge server to communicate with the browser:

```bash
inspekt start --daemon
```

Verify the bridge server is running:

```bash
inspekt status
```

### Step 4: Test MCP Server

Run the connectivity test:

```bash
inspekt mcp test
```

If all tests pass, you're ready to configure Claude Desktop!

---

## Configuration

### Claude Desktop Setup

To use Inspekt with Claude Desktop, you need to add it to your MCP configuration.

**Configuration file location:**

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

**Add Inspekt to your config:**

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

**Full example with multiple MCP servers:**

```json
{
  "mcpServers": {
    "inspekt": {
      "command": "inspekt",
      "args": ["mcp", "start"],
      "env": {
        "PYTHONUNBUFFERED": "1"
      }
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/Users/username/Documents"]
    }
  }
}
```

### Custom Bridge Port

If your bridge server runs on a different port:

```json
{
  "mcpServers": {
    "inspekt": {
      "command": "inspekt",
      "args": ["mcp", "start", "--bridge-port", "8765"]
    }
  }
}
```

### Resource Cache TTL

Adjust how long resources are cached (default: 5 seconds):

```json
{
  "mcpServers": {
    "inspekt": {
      "command": "inspekt",
      "args": ["mcp", "start", "--cache-ttl", "10"]
    }
  }
}
```

### Restart Claude Desktop

After editing the config, **completely quit and restart Claude Desktop** for changes to take effect.

---

## Usage

Once configured, Claude Desktop can use Inspekt tools during conversations. You don't need to explicitly invoke tools – Claude will automatically choose when to use them based on context.

### Example Conversations

**Navigation and extraction:**

> **You:** "Go to https://example.com and tell me what links are on the page"
>
> **Claude:** *Uses `navigate_to_url` and `extract_links` tools automatically*
>
> "I've navigated to example.com and found 5 links on the page: …"

**Page analysis:**

> **You:** "What's the main content of this page?"
>
> **Claude:** *Uses `extract_article` tool*
>
> "I've extracted the main article content. It's about…"

**Browser interaction:**

> **You:** "Click the 'Sign In' button and type my email"
>
> **Claude:** *Uses `click_element` and `type_text` tools*
>
> "I've clicked the Sign In button and entered your email…"

### Checking Available Tools

In Claude Desktop, you can ask:

> "What browser automation tools do you have available?"

Claude will list all Inspekt MCP tools it can use.

---

## Available Tools

The MCP server exposes 15 tools across 6 categories:

### Navigation (3 tools)

| Tool | Description | Parameters |
|------|-------------|------------|
| `navigate_to_url` | Navigate to a URL | `url`, `wait_for` (optional) |
| `go_back` | Navigate browser history backward | None |
| `reload_page` | Reload the current page | `hard` (optional) |

### Execution (1 tool)

| Tool | Description | Parameters |
|------|-------------|------------|
| `execute_javascript` | Execute arbitrary JavaScript | `code`, `timeout` (optional) |

### Extraction (4 tools)

| Tool | Description | Parameters |
|------|-------------|------------|
| `extract_links` | Extract all links from page | `filter_type`, `include_anchors` |
| `extract_outline` | Extract heading hierarchy | None |
| `extract_page_info` | Extract comprehensive metadata | None |
| `extract_article` | Extract main article content | None |

### Interaction (2 tools)

| Tool | Description | Parameters |
|------|-------------|------------|
| `click_element` | Click an element by selector | `selector`, `click_type` |
| `type_text` | Type text into focused element | `text`, `typing_speed`, `submit` |

### Inspection (2 tools)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_page_info` | Get current page info | None |
| `take_screenshot` | Capture screenshot | `target`, `selector`, `format`, `quality` |

### Storage (3 tools)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_selected_text` | Get selected text | `format` (text/html/markdown) |
| `get_cookies` | Get all cookies for page | None |
| `set_cookie` | Set a cookie | `name`, `value`, `domain`, `path`, etc. |

---

## Available Resources

Resources provide read-only access to current browser state:

| Resource URI | Description | MIME Type |
|--------------|-------------|-----------|
| `inspekt-mcp://current-url` | Current page URL | text/plain |
| `inspekt-mcp://page-title` | Current page title | text/plain |
| `inspekt-mcp://page-metadata` | Extended page metadata (JSON) | application/json |
| `inspekt-mcp://browser-info` | Browser information (JSON) | application/json |
| `inspekt-mcp://connection-status` | Connection status (JSON) | application/json |

Resources are automatically cached for 5 seconds (configurable with `--cache-ttl`).

---

## Examples

### Web Scraping Workflow

> **You:** "Go to https://news.ycombinator.com, extract the top 10 links, and summarize what topics are trending"

Claude will:
1. Navigate to Hacker News
2. Extract links from the page
3. Analyze the link titles and descriptions
4. Provide a summary of trending topics

### Form Automation

> **You:** "Go to https://example.com/contact, fill in the form with my name 'John Doe' and email 'john@example.com', and submit it"

Claude will:
1. Navigate to the contact page
2. Click the name field and type "John Doe"
3. Click the email field and type "john@example.com"
4. Submit the form

### Page Analysis

> **You:** "What's the main article on this page about? Give me a 2-sentence summary"

Claude will:
1. Use `extract_article` to get the main content
2. Analyze and summarize it

### Screenshot Documentation

> **You:** "Take a screenshot of the entire page and describe what you see"

Claude will:
1. Use `take_screenshot` with `target=page`
2. Analyze the screenshot
3. Describe the page layout and content

---

## Troubleshooting

### MCP Server Not Appearing in Claude Desktop

**Symptoms:** Claude doesn't show Inspekt tools, or you get "MCP initialization failed"

**Solutions:**
1. Check the config file path is correct for your OS
2. Verify JSON syntax (use [jsonlint.com](https://jsonlint.com))
3. Ensure `inspekt` command is in your PATH
4. Completely quit and restart Claude Desktop (not just close window)
5. Check Claude Desktop logs for errors

**Log locations:**
- **macOS**: `~/Library/Logs/Claude/mcp*.log`
- **Windows**: `%APPDATA%\Claude\logs\mcp*.log`
- **Linux**: `~/.config/Claude/logs/mcp*.log`

### Bridge Server Not Running

**Symptoms:** Tools fail with "Bridge server is not running"

**Solutions:**
1. Start the bridge server: `inspekt start --daemon`
2. Verify it's running: `inspekt status`
3. Check the port is correct (default: 8765)

### Browser Not Connected

**Symptoms:** Tools execute but return errors or timeouts

**Solutions:**
1. Ensure browser has Inspekt extension/userscript installed
2. Check extension is active (icon should be colored, not greyed out)
3. Reload the page in the browser
4. Check browser console for WebSocket connection errors

### Tools Failing with "Unknown tool"

**Symptoms:** Claude says tool doesn't exist

**Solutions:**
1. Verify MCP server version: `pip show inspekt`
2. Update to latest: `pip install --upgrade inspekt`
3. Restart Claude Desktop completely
4. Check `inspekt mcp info` shows all tools

### Permission Errors

**Symptoms:** "Permission denied" when starting MCP server

**Solutions:**
1. Check `inspekt` is executable: `which inspekt`
2. Reinstall Inspekt: `pip install --force-reinstall inspekt`
3. Use full path in config: `/path/to/inspekt mcp start`

---

## Advanced Configuration

### Disable Specific Tools

Edit your Inspekt config file (`~/.config/inspekt.json`):

```json
{
  "mcp": {
    "enabled-tools": [
      "navigate_to_url",
      "extract_links",
      "get_page_info"
    ]
  }
}
```

Only specified tools will be available to Claude.

### Disable Specific Resources

```json
{
  "mcp": {
    "enabled-resources": [
      "current-url",
      "page-title"
    ]
  }
}
```

### Custom Resource Cache TTL

```json
{
  "mcp": {
    "resource-cache-ttl": 10
  }
}
```

Cache resources for 10 seconds instead of default 5.

### Multiple Bridge Servers

If you run multiple bridge servers on different ports:

```json
{
  "mcpServers": {
    "inspekt-dev": {
      "command": "inspekt",
      "args": ["mcp", "start", "--bridge-port", "8765"]
    },
    "inspekt-prod": {
      "command": "inspekt",
      "args": ["mcp", "start", "--bridge-port", "8770"]
    }
  }
}
```

---

## Security Considerations

### Tool Execution Scope

- All tools execute in the context of the **active browser tab**
- Tools cannot access tabs from other windows or profiles
- JavaScript execution is sandboxed within the page context

### Data Privacy

- MCP server runs **locally** on your machine
- No data is sent to external servers (except the web pages you visit)
- Resources are cached in memory only (not persisted to disk)
- All communication uses localhost (127.0.0.1)

### Recommended Practices

1. **Only use with trusted pages**: Don't navigate to malicious sites
2. **Review tool calls**: Check what Claude is doing before confirming
3. **Limit tool access**: Disable tools you don't need in config
4. **Keep bridge server local**: Don't expose it to the network
5. **Use HTTPS**: Always navigate to HTTPS URLs when possible

---

## Contributing

Found a bug or want to improve the MCP integration?

1. Report issues: [GitHub Issues](https://github.com/roelvangils/inspekt/issues)
2. Submit PRs: [Contributing Guide](development/contributing.md)
3. Discuss: [GitHub Discussions](https://github.com/roelvangils/inspekt/discussions)

---

## License

The MCP integration is part of Inspekt and is licensed under the MIT License.

---

**Last Updated:** 2025-11-19
**Inspekt Version:** 1.0.0+
**MCP Protocol Version:** 1.0
