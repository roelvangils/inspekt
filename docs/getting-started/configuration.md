# Configuration

Customize Inspekt for your specific workflow with comprehensive configuration options. This guide covers everything from basic settings to advanced control mode customization.

---

## Configuration File Location

Inspekt uses a JSON configuration file:

```
config.json
```

The file is located in the **project root directory** where you installed Inspekt.

!!! tip "Create Config File"
    If `config.json` doesn't exist, create it in the project root:
    ```bash
    cd /path/to/zen-bridge
    touch config.json
    ```

---

## Configuration Structure

The configuration file has two main sections:

1. **`ai-language`** - Language for AI operations (summarize, describe)
2. **`control`** - Keyboard control mode settings

### Complete Default Configuration

```json
{
  "ai-language": "auto",
  "control": {
    "auto-refocus": "only-spa",
    "focus-outline": "custom",
    "speak-name": false,
    "speak-all": true,
    "announce-role": false,
    "announce-on-page-load": false,
    "navigation-wrap": true,
    "scroll-on-focus": true,
    "click-delay": 0,
    "focus-color": "#0066ff",
    "focus-size": 3,
    "focus-animation": true,
    "focus-glow": true,
    "sound-on-focus": "none",
    "selector-strategy": "id-first",
    "refocus-timeout": 2000,
    "verbose": true,
    "verbose-logging": false
  }
}
```

---

## AI Language Configuration

### `ai-language`

Controls the language used for AI-powered features (`inspektsummarize` and `inspektdescribe`).

**Type**: `string`
**Default**: `"auto"`
**Options**: `"auto"`, `"en"`, `"nl"`, `"fr"`, `"de"`, `"es"`, etc.

=== "Auto-detect (Default)"

    ```json
    {
      "ai-language": "auto"
    }
    ```

    Automatically detects the page language and uses it for AI operations.

=== "Fixed Language"

    ```json
    {
      "ai-language": "en"
    }
    ```

    Always use English for AI operations, regardless of page language.

=== "Multiple Languages"

    ```json
    {
      "ai-language": "nl"
    }
    ```

    Use Dutch for summaries and descriptions.

**Supported Languages**: Any language code supported by your AI provider (mods).

!!! note "Requires mods"
    AI features require [mods](https://github.com/charmbracelet/mods) to be installed. The language setting is passed to the AI model in the prompt.

---

## Control Mode Configuration

The `control` section customizes keyboard navigation behavior when using `inspektcontrol`.

### Auto-Refocus Settings

#### `auto-refocus`

When to automatically refocus the previously focused element after page navigation.

**Type**: `"always"` | `"only-spa"` | `"never"`
**Default**: `"only-spa"`

=== "only-spa (Default)"

    ```json
    {
      "control": {
        "auto-refocus": "only-spa"
      }
    }
    ```

    Only refocus on Single Page Applications (SPAs) where the URL changes without a full page reload.

    **Use case**: Modern web apps like Gmail, Twitter, GitHub.

=== "always"

    ```json
    {
      "control": {
        "auto-refocus": "always"
      }
    }
    ```

    Always try to refocus after any page change, including full page reloads.

    **Use case**: Aggressive refocus behavior for maximum continuity.

=== "never"

    ```json
    {
      "control": {
        "auto-refocus": "never"
      }
    }
    ```

    Never automatically refocus. Focus returns to `<body>` after navigation.

    **Use case**: You prefer manual navigation from the top of each page.

#### `refocus-timeout`

Maximum time to wait for refocus operation to complete.

**Type**: `number` (milliseconds)
**Default**: `2000`
**Range**: `100` - `10000`

```json
{
  "control": {
    "refocus-timeout": 2000
  }
}
```

Increase for slow-loading pages, decrease for faster feedback.

---

### Focus Visual Settings

#### `focus-outline`

Visual style for focused elements.

**Type**: `"custom"` | `"original"` | `"none"`
**Default**: `"custom"`

=== "custom (Default)"

    ```json
    {
      "control": {
        "focus-outline": "custom"
      }
    }
    ```

    Use Inspekt's custom blue outline with glow effect.

=== "original"

    ```json
    {
      "control": {
        "focus-outline": "original"
      }
    }
    ```

    Keep the browser's default focus outline.

=== "none"

    ```json
    {
      "control": {
        "focus-outline": "none"
      }
    }
    ```

    No focus outline (not recommended for accessibility).

#### `focus-color`

Color of the custom focus outline.

**Type**: `string` (CSS color)
**Default**: `"#0066ff"`

```json
{
  "control": {
    "focus-color": "#ff6600"
  }
}
```

**Examples**:

- `"#0066ff"` - Blue (default)
- `"#ff0000"` - Red
- `"rgb(255, 0, 0)"` - Red (RGB)
- `"orange"` - Orange (named color)

#### `focus-size`

Width of the focus outline in pixels.

**Type**: `number` (pixels)
**Default**: `3`
**Range**: `1` - `10`

```json
{
  "control": {
    "focus-size": 5
  }
}
```

Larger values create more prominent outlines.

#### `focus-animation`

Enable animated focus transitions.

**Type**: `boolean`
**Default**: `true`

```json
{
  "control": {
    "focus-animation": true
  }
}
```

Smooth fade-in effect when focus changes.

#### `focus-glow`

Enable glow effect around focused elements.

**Type**: `boolean`
**Default**: `true`

```json
{
  "control": {
    "focus-glow": true
  }
}
```

Adds a soft glow shadow for better visibility.

---

### Navigation Behavior

#### `navigation-wrap`

Whether navigation wraps from last element to first (and vice versa).

**Type**: `boolean`
**Default**: `true`

```json
{
  "control": {
    "navigation-wrap": true
  }
}
```

When `true`, pressing ++tab++ on the last focusable element jumps to the first.

#### `scroll-on-focus`

Automatically scroll focused elements into view.

**Type**: `boolean`
**Default**: `true`

```json
{
  "control": {
    "scroll-on-focus": true
  }
}
```

Ensures focused elements are always visible.

#### `click-delay`

Delay before executing click actions (in milliseconds).

**Type**: `number` (milliseconds)
**Default**: `0`
**Range**: `0` - `5000`

```json
{
  "control": {
    "click-delay": 100
  }
}
```

Useful if pages need time to settle before clicks.

---

### Audio Feedback

#### `sound-on-focus`

Play a sound when focus changes.

**Type**: `"none"` | `"beep"` | `"click"` | `"subtle"`
**Default**: `"none"`

=== "none (Default)"

    ```json
    {
      "control": {
        "sound-on-focus": "none"
      }
    }
    ```

    No sound effects.

=== "beep"

    ```json
    {
      "control": {
        "sound-on-focus": "beep"
      }
    }
    ```

    Short beep on focus change.

=== "click"

    ```json
    {
      "control": {
        "sound-on-focus": "click"
      }
    }
    ```

    Click sound on focus change.

=== "subtle"

    ```json
    {
      "control": {
        "sound-on-focus": "subtle"
      }
    }
    ```

    Subtle tone on focus change.

!!! note "Browser Support"
    Sound effects require browser support for the Web Audio API.

---

### Speech Announcements

#### `speak-all`

Speak all terminal output via text-to-speech (macOS only).

**Type**: `boolean`
**Default**: `true`

```json
{
  "control": {
    "speak-all": true
  }
}
```

Uses macOS `say` command to read terminal messages aloud.

#### `speak-name`

Speak element name when focused.

**Type**: `boolean`
**Default**: `false`

```json
{
  "control": {
    "speak-name": true
  }
}
```

Announces accessible name of focused element (from `aria-label`, text content, etc.).

#### `announce-role`

Announce element role (button, link, heading, etc.).

**Type**: `boolean`
**Default**: `false`

```json
{
  "control": {
    "announce-role": true
  }
}
```

Example: "Submit button" instead of just "Submit".

#### `announce-on-page-load`

Announce page title when a new page loads.

**Type**: `boolean`
**Default**: `false`

```json
{
  "control": {
    "announce-on-page-load": true
  }
}
```

Helps orient you when navigating between pages.

---

### Element Selection Strategy

#### `selector-strategy`

Strategy for generating element selectors for refocus operations.

**Type**: `"id-first"` | `"aria-first"` | `"css-first"`
**Default**: `"id-first"`

=== "id-first (Default)"

    ```json
    {
      "control": {
        "selector-strategy": "id-first"
      }
    }
    ```

    Prefer `id` attributes, fall back to ARIA, then CSS selectors.

    **Best for**: Most web pages with proper IDs.

=== "aria-first"

    ```json
    {
      "control": {
        "selector-strategy": "aria-first"
      }
    }
    ```

    Prefer ARIA labels, fall back to ID, then CSS.

    **Best for**: Accessibility-focused applications.

=== "css-first"

    ```json
    {
      "control": {
        "selector-strategy": "css-first"
      }
    }
    ```

    Use CSS selectors based on tag/class/structure.

    **Best for**: Pages with dynamic IDs.

---

### Logging and Debugging

#### `verbose`

Show detailed terminal announcements during control mode.

**Type**: `boolean`
**Default**: `true`

```json
{
  "control": {
    "verbose": true
  }
}
```

When `true`, prints messages like "Focused: Submit button" to the terminal.

#### `verbose-logging`

Enable verbose logging in the browser console.

**Type**: `boolean`
**Default**: `false`

```json
{
  "control": {
    "verbose-logging": true
  }
}
```

Useful for debugging control mode behavior. Check browser DevTools console.

---

## Example Configurations

### Minimal Configuration

For users who just want AI in a different language:

```json
{
  "ai-language": "nl"
}
```

All control settings use defaults.

### Accessibility-Focused Configuration

For users relying on screen readers and audio feedback:

```json
{
  "ai-language": "en",
  "control": {
    "auto-refocus": "always",
    "speak-all": true,
    "speak-name": true,
    "announce-role": true,
    "announce-on-page-load": true,
    "sound-on-focus": "subtle",
    "verbose": true,
    "selector-strategy": "aria-first"
  }
}
```

### Performance-Optimized Configuration

Minimal visual effects for faster performance:

```json
{
  "ai-language": "auto",
  "control": {
    "focus-animation": false,
    "focus-glow": false,
    "scroll-on-focus": false,
    "speak-all": false,
    "verbose": false,
    "verbose-logging": false
  }
}
```

### High-Contrast Configuration

Enhanced visibility with bold outlines:

```json
{
  "ai-language": "auto",
  "control": {
    "focus-outline": "custom",
    "focus-color": "#ffff00",
    "focus-size": 5,
    "focus-animation": true,
    "focus-glow": true
  }
}
```

### Developer/Debug Configuration

Maximum logging and visibility:

```json
{
  "ai-language": "auto",
  "control": {
    "auto-refocus": "always",
    "verbose": true,
    "verbose-logging": true,
    "refocus-timeout": 5000,
    "focus-color": "#ff00ff",
    "focus-size": 4
  }
}
```

---

## Applying Configuration Changes

### Reload Configuration

Configuration is loaded when:

1. **Server starts** - `inspektserver start`
2. **Control mode starts** - `inspektcontrol`

To apply changes:

=== "Restart Control Mode"

    ```bash
    # Press 'q' in control mode to quit, then restart
    inspektcontrol
    ```

=== "Restart Server"

    ```bash
    inspektserver stop
    inspektserver start --daemon
    ```

!!! tip "Live Reload"
    Control mode configuration is sent to the browser when you start `inspektcontrol`, so you just need to quit and restart control mode to apply changes.

---

## Customizing AI Prompts

AI prompts are stored in separate files for easy customization:

### Summary Prompt

**Location**: `prompts/summary.prompt`

Edit this file to change how articles are summarized:

```markdown
Provide a concise, structured summary of the following article.
Focus on the main points and key takeaways.

Article content:
{content}
```

### Description Prompt

**Location**: `prompts/describe.prompt`

Edit this file to change how pages are described:

```markdown
Describe this webpage in a way that would be helpful for someone
using a screen reader. Focus on navigation, main content, and structure.

Page structure:
{content}
```

**Variables available**: `{content}`, `{url}`, `{title}`, `{language}`

---

## Configuration Hierarchy

Configuration is loaded in the following order (later values override earlier ones):

1. **Default values** (hardcoded in `zen/domain/models.py`)
2. **`config.json`** (project root)
3. **Command-line flags** (where applicable)

Example:

```bash
# Default verbose=true, but config.json sets verbose=false
# Result: verbose=false

# But if you pass a flag:
inspektcontrol --verbose
# Result: verbose=true (flag overrides config)
```

!!! note "No CLI Flags for Config"
    Currently, Inspekt doesn't support command-line flags for most configuration options. Edit `config.json` to customize behavior.

---

## Troubleshooting Configuration

### Configuration Not Loading

**Problem**: Changes to `config.json` don't seem to apply.

**Solutions**:

1. **Check JSON syntax**:
   ```bash
   # Validate JSON
   python3 -c "import json; json.load(open('config.json'))"
   ```

2. **Check file location**:
   ```bash
   # Ensure config.json is in project root
   ls -la config.json
   ```

3. **Restart server and control mode**:
   ```bash
   inspektserver stop
   inspektserver start --daemon
   inspektcontrol
   ```

### Invalid Configuration Value

**Problem**: Server or control mode fails to start.

**Solution**: Check for invalid values:

- `auto-refocus`: Must be `"always"`, `"only-spa"`, or `"never"`
- `focus-outline`: Must be `"custom"`, `"original"`, or `"none"`
- `sound-on-focus`: Must be `"none"`, `"beep"`, `"click"`, or `"subtle"`
- `selector-strategy`: Must be `"id-first"`, `"aria-first"`, or `"css-first"`
- `refocus-timeout`: Must be number >= 100
- `focus-size`: Must be number >= 1

### Configuration Ignored

**Problem**: Some settings don't seem to work.

**Check**:

1. **Feature support**: Some features (like TTS) only work on macOS
2. **Browser compatibility**: Sound effects require Web Audio API
3. **Spelling**: JSON keys are case-sensitive and use hyphens

---

## Advanced: Programmatic Configuration

You can load and validate configuration programmatically:

```python
from zen.domain.models import ZenConfig

# Load from file
with open('config.json') as f:
    config_dict = json.load(f)

# Validate with Pydantic
config = ZenConfig(**config_dict)

# Access settings
print(config.ai_language)  # "auto"
print(config.control.auto_refocus)  # "only-spa"
print(config.control.focus_color)  # "#0066ff"
```

This is useful for building extensions or integrating Inspekt into other tools.

---

## Next Steps

Now that you've configured Inspekt to your liking:

<div class="grid cards" markdown>

-   :books: __User Guide__

    ---

    Learn all commands and features in depth.

    [:octicons-arrow-right-24: User Guide](../guide/overview.md)

-   :control_knobs: __Control Mode Guide__

    ---

    Master keyboard navigation with control mode.

    [:octicons-arrow-right-24: Control Mode](../guide/control-mode.md)

-   :robot: __AI Features__

    ---

    Explore AI-powered summarization and description.

    [:octicons-arrow-right-24: AI Features](../guide/ai-features.md)

-   :hammer_and_wrench: __API Reference__

    ---

    Complete reference for all configuration models.

    [:octicons-arrow-right-24: Models Reference](../api/models.md)

</div>

---

## Recording and Replay Audio

The `audio` section controls audio feedback during `inspekt record` and `inspekt replay`.

### `audio.output`

Where to play audio feedback sounds.

**Type**: `"cli"` | `"browser"` | `"off"`
**Default**: `"cli"`

=== "cli (Default)"

    ```json
    {
      "audio": {
        "output": "cli"
      }
    }
    ```

    Play sounds via system audio (macOS `afplay`, Linux `aplay`).

    **Advantages**:
    - Works immediately, no browser interaction needed
    - Plays asynchronously, doesn't slow down replay
    - Works over SSH if your terminal supports audio

=== "browser"

    ```json
    {
      "audio": {
        "output": "browser"
      }
    }
    ```

    Play sounds via Web Audio API in the browser.

    **Note**: Requires clicking in the browser window first (browser autoplay policy).

    **Use case**: When terminal audio is not available.

=== "off"

    ```json
    {
      "audio": {
        "output": "off"
      }
    }
    ```

    Disable all audio feedback.

    **Use case**: CI/CD environments, quiet operation.

### `audio.volume`

Volume level for audio feedback.

**Type**: `number` (0.0 to 1.0)
**Default**: `0.5`

```json
{
  "audio": {
    "output": "cli",
    "volume": 0.7
  }
}
```

---

## Configuration Reference

Quick reference for all available settings:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `ai-language` | `string` | `"auto"` | Language for AI operations |
| `audio.output` | `string` | `"cli"` | Audio output: cli, browser, or off |
| `audio.volume` | `number` | `0.5` | Audio volume (0.0 to 1.0) |
| `control.auto-refocus` | `string` | `"only-spa"` | When to auto-refocus |
| `control.focus-outline` | `string` | `"custom"` | Focus outline style |
| `control.speak-name` | `boolean` | `false` | Speak element name |
| `control.speak-all` | `boolean` | `true` | Speak all terminal output |
| `control.announce-role` | `boolean` | `false` | Announce element role |
| `control.announce-on-page-load` | `boolean` | `false` | Announce page title on load |
| `control.navigation-wrap` | `boolean` | `true` | Wrap navigation at end |
| `control.scroll-on-focus` | `boolean` | `true` | Scroll to focused element |
| `control.click-delay` | `number` | `0` | Delay before clicks (ms) |
| `control.focus-color` | `string` | `"#0066ff"` | Focus outline color |
| `control.focus-size` | `number` | `3` | Focus outline width (px) |
| `control.focus-animation` | `boolean` | `true` | Animate focus transitions |
| `control.focus-glow` | `boolean` | `true` | Add glow effect |
| `control.sound-on-focus` | `string` | `"none"` | Sound on focus change |
| `control.selector-strategy` | `string` | `"id-first"` | Element selector strategy |
| `control.refocus-timeout` | `number` | `2000` | Refocus timeout (ms) |
| `control.verbose` | `boolean` | `true` | Terminal announcements |
| `control.verbose-logging` | `boolean` | `false` | Browser console logging |
