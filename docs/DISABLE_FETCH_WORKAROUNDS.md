# Workarounds to Prefer Inspekt Tools Over Built-in Fetch

## Problem

Claude Code has a built-in `Fetch` tool that it may prefer over Inspekt's browser automation tools because:
- Fetch is simpler and faster
- Fetch doesn't require browser state
- Fetch works for basic HTTP requests

However, Inspekt tools are better when you need:
- JavaScript execution
- Dynamic content
- Browser interaction
- Live DOM access

## Solutions

### ✅ Solution 1: Improved Tool Descriptions (Implemented)

**Status**: ✅ **IMPLEMENTED**

We've enhanced all tool descriptions to be more compelling and explicitly mention advantages over simple HTTP fetch.

**Key improvements**:
- `navigate_to_url`: Now says "Use this instead of simple HTTP fetch when you need…"
- `extract_links`: Says "Better than parsing HTML as it uses the live DOM"
- `extract_outline`: Says "Use this when asked about page structure, headings, or outline"

**How it helps**: Claude's decision-making is heavily influenced by tool descriptions. By mentioning use cases that overlap with Fetch and emphasizing advantages, Claude is more likely to choose Inspekt tools.

### ❌ Solution 2: Disable Fetch (Not Possible)

**Status**: ❌ **NOT POSSIBLE**

You **cannot disable built-in tools** in Claude Code. The Fetch tool is built into the Claude Code runtime and cannot be removed via configuration.

### ✅ Solution 3: User Prompting (Recommended)

**Status**: ✅ **RECOMMENDED**

Train Claude in your conversation with explicit instructions:

```
"For all web tasks, use browser automation tools from Inspekt instead of Fetch"
```

Or be specific in each request:

```
❌ "Get the links from example.com"
   → Might use Fetch

✅ "Use the browser to navigate to example.com and extract links"
   → Will use Inspekt

✅ "Navigate to example.com and extract links"
   → Will use Inspekt
```

### ✅ Solution 4: Claude Code Custom Instructions

**Status**: ✅ **AVAILABLE** (if Claude Code supports it)

If Claude Code supports custom instructions or system prompts, add:

```
When working with web pages:
- Always use Inspekt browser automation tools (navigate_to_url, extract_*)
- Only use Fetch when explicitly requested or when browser automation is not needed
- Prefer browser-based extraction for dynamic content, JavaScript-heavy sites, and interactive pages
```

Check Claude Code documentation for how to set persistent instructions.

### ⚠️ Solution 5: Add Fetch Alias (Advanced)

**Status**: ⚠️ **POSSIBLE BUT NOT RECOMMENDED**

We could add a tool called `fetch` or `fetch_url` that just wraps `navigate_to_url`:

```python
types.Tool(
    name="fetch_url",
    description="Fetch content from a URL using the browser. Better than HTTP fetch as it executes JavaScript and returns live DOM content.",
    inputSchema=schemas.NavigateToUrlParams.model_json_schema(),
),
```

**Why not recommended**: This is confusing and doesn't actually override the built-in Fetch.

### ✅ Solution 6: Context-Aware Prompting

**Status**: ✅ **BEST PRACTICE**

Use language that triggers browser tool usage:

| Phrase | Likely Tool |
|--------|-------------|
| "Fetch from…" | Built-in Fetch |
| "Navigate to…" | navigate_to_url |
| "Open in browser…" | navigate_to_url |
| "Use the browser to…" | Inspekt tools |
| "Extract from current page…" | Inspekt tools |
| "Get links from…" | Could be either |
| "Get links from the browser…" | extract_links |

---

## Recommended Workflow

1. **Always use improved tool descriptions** (already done ✅)
2. **Be explicit in prompts** when you want browser automation
3. **Train Claude** at the start of conversations:
   ```
   "For this session, always use Inspekt browser tools for web tasks"
   ```
4. **Use browser-specific language**: "navigate", "browser", "current page"

---

## Testing the Changes

After updating tool descriptions, test with:

```bash
# Remove and re-add MCP server
claude mcp remove inspekt -s local
claude mcp add --transport stdio inspekt -- inspekt mcp start

# Test different phrasings in Claude Code:

# ❌ Might use Fetch:
"Get the heading structure from example.com"

# ✅ Should use Inspekt:
"Navigate to example.com and extract the heading structure"

# ✅ Should use Inspekt:
"Use the browser to get the heading hierarchy from example.com"
```

---

## Why Fetch Can't Be Disabled

Claude Code's built-in tools are part of the core runtime and include:

- **Fetch**: HTTP requests
- **Read**: File reading
- **Write**: File writing
- **Bash**: Shell commands
- **Edit**: File editing

These are baked into the Claude Code binary and cannot be disabled via:
- MCP configuration
- CLI flags
- Environment variables
- Configuration files

The only way to influence tool selection is through:
1. Better tool descriptions (what we did)
2. User prompting
3. Context and conversation history

---

**Last Updated**: 2025-11-19
**Status**: Using improved descriptions + user prompting strategy
