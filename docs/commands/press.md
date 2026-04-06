# press

Send keyboard key presses to the browser.

## Synopsis

```bash
inspekt press "<KEYS>" [OPTIONS]
```

## Description

The `press` command sends keyboard key presses to the currently focused element in the browser. It accepts a sequence of space-separated key specifications and dispatches them one at a time.

**Recommended syntax:** Pass all keys as a single quoted string:

```bash
inspekt press "Tab*6 Enter"
```

This avoids shell globbing issues with the `*` character used in repeat syntax.

This command is the recommended replacement for the deprecated `inspekt send` command.

## Arguments

| Argument | Description |
|----------|-------------|
| `KEYS` | Space-separated key specifications (required). Can be passed as a single quoted string or as separate arguments. |

## Options

| Option | Description |
|--------|-------------|
| `--selector`, `-s` | CSS selector to focus before pressing keys |
| `--focus`, `-f` | Focus the browser window before sending keys (macOS only) |
| `--native`, `-n` | Send native OS key events via AppleScript (macOS only, auto-enables `--focus`) |
| `--wait`, `-w` | Fixed delay in seconds between key presses (0-10) |
| `--wait-min` | Minimum random delay in seconds (use with `--wait-max`) |
| `--wait-max` | Maximum random delay in seconds (use with `--wait-min`) |

!!! tip "Why use `--focus`?"
    When scripting browser interactions from the terminal, the browser window may be in the background.
    The `--focus` flag brings the browser to the foreground before sending keys, ensuring they reach the correct window.
    This is especially useful for:

    - **Accessibility testing** - Watch focus indicators while Tab navigates
    - **Demos and presentations** - Show real-time browser interaction
    - **Debugging** - Visually verify keyboard actions are working

## Native Mode

The `--native` flag sends key presses at the OS level via AppleScript System Events, rather than JavaScript keyboard events. This provides more authentic keyboard behavior and enables functionality that's impossible with JavaScript alone.

### Why Use Native Mode?

| Feature | JavaScript Events | Native Mode (`--native`) |
|---------|------------------|--------------------------|
| **Browser shortcuts** | ❌ Cannot trigger | ✅ Works (Cmd+L, Cmd+F, etc.) |
| **Page event prevention** | Can be blocked by `preventDefault()` | ✅ Cannot be blocked |
| **Focus indicators** | May need CSS polyfills | ✅ Real `:focus-visible` triggers |
| **Accessibility testing** | Good | ✅ Most authentic |
| **Cross-platform** | ✅ All browsers | ⚠️ macOS only |

### Browser Shortcuts

Browser shortcuts like `Cmd+L` (focus URL bar) or `Cmd+F` (find on page) are intercepted by the browser before they reach the web page. This means **JavaScript events cannot trigger them**.

If you try to send a browser shortcut without `--native`, Inspekt will detect this and show a helpful message:

```bash
$ inspekt press "Cmd+L"
⚠ Cmd+L is a browser shortcut (Focus the URL/address bar)

  Browser shortcuts are intercepted by the browser before reaching the page,
  so they cannot be triggered via JavaScript events.

💡 Use --native to send these as OS-level key events:

    inspekt press "Cmd+L" --native
```

### Which Shortcuts Require Native Mode?

**Not all `Cmd`/`Ctrl` shortcuts require native mode.** The key distinction is:

| Type | Examples | Works with JavaScript? |
|------|----------|----------------------|
| **Page-level** | `Cmd+A` (Select All), `Cmd+C` (Copy), `Cmd+V` (Paste), `Cmd+Z` (Undo) | ✅ Yes - operates on page content |
| **Browser-level** | `Cmd+L` (URL bar), `Cmd+F` (Find), `Cmd+P` (Print), `Cmd+T` (New tab) | ❌ No - requires `--native` |

Page-level shortcuts work because the browser forwards them to the focused element. Browser-level shortcuts control the browser UI and are intercepted before reaching the page.

### Supported Browser Shortcuts

These shortcuts are automatically detected and require `--native`:

| Category | Shortcuts |
|----------|-----------|
| **URL Bar** | `Cmd+L`, `Ctrl+L`, `Cmd+K`, `Ctrl+K` |
| **Find** | `Cmd+F`, `Ctrl+F`, `Cmd+G`, `Ctrl+G` |
| **Print & Save** | `Cmd+P`, `Ctrl+P`, `Cmd+S`, `Ctrl+S` |
| **Tab Management** | `Cmd+T`, `Cmd+W`, `Cmd+Shift+T`, `Ctrl+Tab` |
| **Window** | `Cmd+N`, `Cmd+Shift+N` (incognito), `Cmd+M` (minimize) |
| **Navigation** | `Cmd+R` (reload), `Cmd+Shift+R` (hard reload), `Cmd+[`, `Cmd+]` |
| **Bookmarks/History** | `Cmd+D`, `Cmd+Y`, `Cmd+J`, `Cmd+Shift+B` |
| **DevTools** | `Cmd+Alt+I`, `Cmd+Alt+J`, `Cmd+Alt+U` (view source) |
| **Tab Switching** | `Cmd+1` through `Cmd+9`, `Cmd+Alt+←/→` |
| **Zoom** | `Cmd+=`, `Cmd+-`, `Cmd+0` |
| **Other** | `Cmd+,` (settings), `Cmd+Q` (quit), `F11` (fullscreen) |

### Native Mode Examples

```bash
# Focus the URL bar
inspekt press "Cmd+L" --native

# Open find on page
inspekt press "Cmd+F" --native

# Reload the page
inspekt press "Cmd+R" --native

# Open a new tab
inspekt press "Cmd+T" --native

# Mixed sequence: Tab through form, then open find
inspekt press "Tab*3 Enter Cmd+F" --native

# With delay between keys
inspekt press "Cmd+L" --native --wait 0.5
```

### Requirements

Native mode requires:

- **macOS** - Uses AppleScript System Events (Windows/Linux not yet supported)
- **Accessibility permissions** - Grant in System Settings > Privacy & Security > Accessibility

!!! note "Performance"
    Native key presses are slower (~50-100ms per key) due to subprocess overhead. This is usually acceptable since accuracy matters more than speed for accessibility testing.

## Supported Keys

### Navigation Keys

| Key | Description |
|-----|-------------|
| `Tab` | Move focus to next element |
| `Enter` | Activate focused element (click button/link, submit form) |
| `Escape`, `Esc` | Cancel or close |
| `Space` | Press spacebar |
| `Backspace` | Delete character before cursor |
| `Delete`, `Del` | Delete character after cursor |

### Arrow Keys

| Key | Aliases |
|-----|---------|
| `ArrowUp` | `Up` |
| `ArrowDown` | `Down` |
| `ArrowLeft` | `Left` |
| `ArrowRight` | `Right` |

### Page Navigation

| Key | Aliases |
|-----|---------|
| `Home` | - |
| `End` | - |
| `PageUp` | `PgUp` |
| `PageDown` | `PgDown` |

### Function Keys

`F1` through `F12`

### Modifier Keys

| Modifier | Aliases | Notes |
|----------|---------|-------|
| `Ctrl` | `Control` | - |
| `Alt` | `Option` | macOS Option key |
| `Shift` | - | - |
| `Meta` | `Cmd`, `Command`, `Win`, `Windows` | macOS Command, Windows key |

## Modifier Combinations

Use `+` to combine modifiers with keys:

```bash
# Select all
inspekt press Ctrl+A

# Copy
inspekt press Ctrl+C

# Paste
inspekt press Ctrl+V

# Undo
inspekt press Ctrl+Z

# macOS: Command+C
inspekt press Cmd+C

# Multiple modifiers
inspekt press Ctrl+Shift+A
```

## Wait Tokens

Insert pauses between key presses:

| Syntax | Duration |
|--------|----------|
| `Wait` | 0.5 seconds (default) |
| `Wait(N)` | N seconds (float, max 60) |

```bash
# Tab, wait 0.5s, Tab
inspekt press Tab Wait Tab

# Tab, wait 2 seconds, Enter
inspekt press Tab Wait(2) Enter

# Wait with fractional seconds
inspekt press Tab Wait(1.5) Enter
```

## Repeat Syntax

Use `*N` to repeat a key multiple times:

| Syntax | Expands To |
|--------|------------|
| `Tab*3` | Tab, Tab, Tab |
| `Shift+Tab*2` | Shift+Tab, Shift+Tab |
| `ArrowDown*5` | 5 arrow down presses |

```bash
# Tab 6 times, then Enter
inspekt press "Tab*6 Enter"

# Navigate backward 3 times
inspekt press "Shift+Tab*3"

# Arrow navigation
inspekt press "ArrowDown*5 Enter"
```

**Limits:**

- Maximum repeat count: 100
- `Tab*0` produces an error
- `Tab*1` is equivalent to `Tab`

!!! tip "Flexible Input Syntax"
    Keys can be passed as a **single quoted string** or as **separate arguments**:

    ```bash
    # Recommended - single quoted string (avoids shell glob issues)
    inspekt press "Tab*6 Enter"
    inspekt press "Ctrl+A Ctrl+C"
    inspekt press "Tab Wait(2) Enter"

    # Also works - separate arguments (quote keys with *)
    inspekt press 'Tab*6' Enter
    inspekt press Ctrl+A Ctrl+C

    # Without quotes, zsh/bash will error on *: "no matches found: Tab*6"
    inspekt press Tab*6 Enter  # ❌ fails
    ```

    The single-string syntax is recommended because it's simpler and always works.

## Delay Options

Add delays between key presses for testing or human-like interaction.

### Fixed Delay (`--wait`)

Insert a fixed delay between all key presses:

```bash
# 250ms delay between each of the 7 key presses
inspekt press "Tab*6 Enter" --wait 0.25

# 1 second between keys
inspekt press "Tab Tab Tab" --wait 1
```

### Random Delay (`--wait-min`, `--wait-max`)

Use random delays for more human-like timing:

```bash
# Random delay between 100ms and 500ms
inspekt press "Tab*5 Enter" --wait-min 0.1 --wait-max 0.5

# Simulate natural typing rhythm
inspekt press "Ctrl+A Ctrl+C" --wait-min 0.05 --wait-max 0.2
```

**Use cases:**

- Simulate human interaction patterns
- Catch timing-dependent bugs in applications
- Accessibility testing at realistic speeds

**Note:** `--wait` and `--wait-min`/`--wait-max` are mutually exclusive.

## Examples

### Basic Usage

```bash
# Press Tab once
inspekt press Tab

# Press Enter
inspekt press Enter

# Press Escape
inspekt press Escape
```

### Multiple Keys

```bash
# Tab three times, then Enter (using repeat syntax)
inspekt press "Tab*3 Enter"

# Navigate with arrow keys
inspekt press "ArrowDown*2 Enter"

# Or without repeat syntax
inspekt press "Tab Tab Tab Enter"
```

### Modifier Combinations

```bash
# Select all and copy (page-level shortcuts - work without --native)
inspekt press "Ctrl+A Ctrl+C"

# Navigate backward with Shift+Tab
inspekt press "Shift+Tab Shift+Tab"

# Close tab (macOS) - requires --native (browser shortcut)
inspekt press "Cmd+W" --native
```

### With Waits

```bash
# Tab, wait, Tab
inspekt press "Tab Wait Tab"

# Tab, wait 2 seconds, Enter
inspekt press "Tab Wait(2) Enter"

# Complex sequence with multiple waits
inspekt press "Tab Wait(1) Tab Wait(0.5) Enter"
```

### Focus Element First

```bash
# Focus search input, then type-ahead navigation
inspekt press "Tab Tab" --selector "input#search"

# Focus form, then submit
inspekt press Enter --selector "form#login"
```

### Accessibility Testing

```bash
# Test keyboard navigation through a form
inspekt press "Tab*4 Enter"

# Navigate and activate a menu
inspekt press "Tab Enter ArrowDown*2 Enter"

# Test with human-like timing
inspekt press "Tab*6 Enter" --wait-min 0.1 --wait-max 0.3

# Focus browser first to watch the visual focus indicators
inspekt press "Tab*6 Enter" --focus
```

## Cross-Platform Notes

| Platform | Notes |
|----------|-------|
| **macOS** | Use `Cmd` for Command key shortcuts |
| **Windows/Linux** | Use `Ctrl` for most shortcuts |

The `Cmd` and `Meta` keys both map to the `metaKey` in JavaScript. On macOS, this is the Command key. On Windows/Linux, this is typically the Windows/Super key.

## Verbose Mode

Use `--verbose` or `-v` to see detailed information about each key press:

```bash
inspekt --verbose press "Tab Tab Enter"
```

Output:
```
[Verbose] Sending keys: Tab Tab Enter
Pressed 3 keys
  Tab -> input#username (dispatched)
  Tab -> input#password (dispatched)
  Enter -> input#password (dispatched)
```

## Error Handling

### Invalid Key Name

```bash
$ inspekt press NotAKey
Error: Invalid key at position 1: Unknown key: 'NotAKey'. Did you mean: Tab?
```

### Wait Exceeds Maximum

```bash
$ inspekt press Wait(100)
Error: Invalid key at position 1: Wait duration 100.0s exceeds maximum of 60 seconds
```

### Element Not Found

```bash
$ inspekt press Tab --selector "#nonexistent"
Error focusing element: Element not found: #nonexistent
```

## MCP Integration

The `press` command is available as an MCP tool for AI assistant integration:

```json
{
  "name": "press_keys",
  "params": {
    "keys": ["Tab*3", "Enter"],
    "selector": "input#search"
  }
}
```

With delay parameters:

```json
{
  "name": "press_keys",
  "params": {
    "keys": ["Tab*5", "Enter"],
    "delay": 0.25
  }
}
```

With random delay:

```json
{
  "name": "press_keys",
  "params": {
    "keys": ["Ctrl+A", "Ctrl+C"],
    "delay_min": 0.1,
    "delay_max": 0.5
  }
}
```

## Migration from `inspekt send`

The `inspekt send` command is deprecated. Here's how to migrate:

| Old Command | New Command |
|-------------|-------------|
| `inspekt send Enter` | `inspekt press Enter` |
| `inspekt send Tab` | `inspekt press Tab` |
| `inspekt send "Ctrl+a"` | `inspekt press Ctrl+A` |

Note: `inspekt send` was also used for typing text. For text input, use:

- `inspekt type "text"` - Type character by character
- `inspekt paste "text"` - Insert text instantly

## See Also

- [`type`](../guide/element-interaction.md) - Type text into input fields
- [`paste`](../guide/element-interaction.md) - Paste text instantly
- [`click`](../guide/element-interaction.md) - Click on elements
- [`control`](../guide/control-mode.md) - Interactive keyboard control mode
