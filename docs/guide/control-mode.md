# Control Mode

Master keyboard-only navigation with Inspekt Control Mode. Navigate pages entirely from your terminal using Tab, Enter, and Arrow keys.

## Overview

`inspekt control` provides keyboard-only navigation for accessibility testing and hands-free browsing. It's perfect for:

- **Accessibility testing** - Verify keyboard navigation
- **Hands-free browsing** - Navigate without a mouse
- **Screen reader compatibility** - Test with keyboard + voice
- **Focus management testing** - Verify focus indicators
- **Navigation persistence** - Auto-refocus after page loads

## Starting Control Mode

```bash
inspekt control
```

**What happens:**

1. Terminal enters **raw mode** (captures all keyboard input)
2. Browser receives keyboard events in real-time
3. Focus indicators appear on interactive elements
4. Terminal displays announcements and feedback
5. Mode persists across page navigations

**To exit:** Press `Ctrl+D` or `q`

---

## Keyboard Navigation

### Basic Controls

| Key | Action |
|-----|--------|
| `Tab` | Navigate forward through focusable elements |
| `Shift+Tab` | Navigate backward |
| `Enter` | Activate focused element (click/submit) |
| `Space` | Activate focused element |
| `Arrow Keys` | Navigate directionally |
| `Escape` | Return focus to body |
| `q` | Quit control mode |
| `Ctrl+D` | Quit control mode |

### How It Works

Control mode captures your keystrokes and sends them to the browser:

1. **You press Tab** in terminal
2. **Zen sends Tab** to browser
3. **Browser shifts focus** to next element
4. **Element is highlighted** with blue outline
5. **Terminal announces** element name and role

### Visual Feedback

Focused elements get a **blue outline** (`outline: 2px solid blue`) so you can see what's focused.

### Terminal Announcements

Control mode announces element details in your terminal:

```
Focus: Submit Button (button)
Focus: Email Input (input)
Focus: Privacy Policy (link)
```

---

## Features

### Auto-refocus After Navigation

Control mode persists across page navigations:

```bash
inspekt control
# Tab to a link
# Press Enter → Page loads
# → Focus automatically returns to the link
# Continue tabbing from there
```

This is **unique** to Inspekt - the focus persists even after navigation!

### Text-to-Speech (macOS)

Enable voice announcements:

```bash
# Set in config.json
{
  "control": {
    "speak-all": true
  }
}
```

Focused elements are announced via macOS `say` command:

```
"Submit Button"
"Email Input"
"Privacy Policy Link"
```

Perfect for **testing screen reader workflows** without actual screen reader.

### Accessibility Names

Control mode extracts **accessible names** for elements:

- `aria-label` attribute
- `aria-labelledby` reference
- Associated `<label>` text
- Button/link text content
- `alt` text for images
- `title` attribute

This matches what screen readers announce!

### Configuration

Edit `config.json` in project root:

```json
{
  "control": {
    "verbose": true,
    "speak-all": true,
    "verbose-logging": false
  }
}
```

**Options:**

- `verbose` (default: `true`) - Show terminal announcements
- `speak-all` (default: `true`) - Enable text-to-speech on macOS
- `verbose-logging` (default: `false`) - Detailed debug output

---

## Practical Examples

### Example 1: Form Navigation

```bash
inspekt control

# Tab to first field → "Email Input"
# Type: test@example.com
# Tab to next field → "Password Input"
# Type: password123
# Tab to submit → "Submit Button"
# Press Enter → Form submits
# → Focus returns to submit button after page loads
```

### Example 2: Link Navigation

```bash
inspekt control

# Tab through navigation → "Home", "About", "Contact"
# Tab to main content link → "Read More"
# Press Enter → Article opens
# → Focus returns to "Read More" link position
# Continue navigating from there
```

### Example 3: Modal Interaction

```bash
inspekt control

# Tab to button → "Open Modal"
# Press Enter → Modal opens
# Tab through modal → "Close Button", "Save Button"
# Press Enter on "Close" → Modal closes
# Continue navigating
```

### Example 4: Accessibility Audit

```bash
inspekt control

# Tab through entire page
# Verify:
# - All interactive elements reachable?
# - Focus indicators visible?
# - Logical tab order?
# - No focus traps?
# - Keyboard shortcuts work?
```

---

## Advanced Usage

### Combine with Other Commands

**Take screenshots of focused elements:**
```bash
# Start control mode in one terminal
inspekt control

# In another terminal:
inspekt eval "document.activeElement"
inspekt screenshot --selector "$0" --output focused.png
```

**Extract focused element info:**
```bash
# While in control mode (other terminal):
inspekt eval "
  const el = document.activeElement;
  return {
    tag: el.tagName,
    text: el.textContent,
    role: el.getAttribute('role'),
    label: el.getAttribute('aria-label')
  };
" --format json
```

**Verify focus order:**
```bash
# While in control mode (other terminal):
inspekt eval "
  const focusable = Array.from(document.querySelectorAll(
    'a, button, input, select, textarea, [tabindex]:not([tabindex=\"-1\"])'
  ));
  return focusable.map((el, i) => ({
    index: i,
    tag: el.tagName,
    text: el.textContent?.substring(0, 30),
    tabIndex: el.tabIndex
  }));
" --format json
```

### Test Focus Traps

```bash
inspekt control

# Navigate into component
# Try to Tab out
# If trapped → Accessibility issue!
```

### Test Skip Links

```bash
inspekt control

# First Tab should focus skip link
# Press Enter
# Verify focus jumps to main content
```

### Test Keyboard Shortcuts

```bash
inspekt control

# Try:
# - Ctrl+F for search
# - Escape to close modals
# - Arrow keys for sliders
# - Space for checkboxes
```

---

## Use Cases

### 1. Accessibility Testing

Verify keyboard navigation compliance:

- [ ] All interactive elements reachable via Tab
- [ ] Logical tab order (left-to-right, top-to-bottom)
- [ ] Focus indicators visible
- [ ] No keyboard traps
- [ ] Skip links present and functional
- [ ] Modals trap focus appropriately
- [ ] Dropdowns navigable with arrows
- [ ] Forms completable without mouse

### 2. Screen Reader Testing

Test with keyboard + voice:

```bash
# Enable text-to-speech
# Edit config.json: "speak-all": true

inspekt control
# Navigate and listen to announcements
# Verify meaningful names
# Check announcement order
```

### 3. Focus Management Testing

Test focus behavior:

```bash
inspekt control
# Open modal → Focus should enter modal
# Close modal → Focus should return to trigger
# Submit form → Focus should go to success message
# Navigate → Focus should persist (unique to Inspekt!)
```

### 4. Keyboard-Only Workflows

Browse without a mouse:

```bash
inspekt control
# Navigate entirely from terminal
# Perfect for accessibility demos
# Great for focus management testing
```

---

## How Control Mode Works Internally

### 1. Terminal Setup

```python
import sys, tty, termios

# Save terminal settings
old_settings = termios.tcgetattr(sys.stdin)

# Enter raw mode (no buffering, no echo)
tty.setraw(sys.stdin)
```

### 2. Key Capture Loop

```python
while True:
    char = sys.stdin.read(1)  # Read single character

    # Handle special keys
    if char == '\t':  # Tab
        send_key_to_browser('Tab')
    elif char == '\r':  # Enter
        send_key_to_browser('Enter')
    # ... etc
```

### 3. Browser Script

```javascript
// control.js (injected in browser)
document.addEventListener('inspektControl', (event) => {
  const {key, shiftKey, ctrlKey, altKey} = event.detail;

  // Simulate keyboard event
  const keyEvent = new KeyboardEvent('keydown', {
    key, shiftKey, ctrlKey, altKey,
    bubbles: true
  });

  document.activeElement.dispatchEvent(keyEvent);
});
```

### 4. Focus Tracking

```javascript
document.addEventListener('focus', (event) => {
  const element = event.target;

  // Highlight focused element
  element.style.outline = '2px solid blue';

  // Send announcement to terminal
  const name = getAccessibleName(element);
  sendToTerminal(`Focus: ${name}`);
}, true);
```

### 5. Auto-refocus

```javascript
// Store focused element before navigation
let lastFocused = null;

document.addEventListener('focus', (e) => {
  lastFocused = e.target;
}, true);

// Restore after page load
window.addEventListener('load', () => {
  if (lastFocused) {
    lastFocused.focus();
  }
});
```

---

## Configuration Options

### config.json

```json
{
  "control": {
    "verbose": true,
    "speak-all": true,
    "verbose-logging": false
  }
}
```

### Verbose Mode

**Enabled (default):**
```
Focus: Submit Button (button)
Focus: Email Input (input)
Activated: Submit Button
```

**Disabled:**
```
(no terminal output)
```

### Text-to-Speech

**Enabled (macOS only):**
```bash
# Uses `say` command
say "Submit Button"
say "Email Input"
```

**Disabled (default on Linux):**
```
(no voice output)
```

---

## Troubleshooting

### Keys Not Working

**Problem:** Keys pressed but nothing happens in browser

**Solutions:**
1. Verify browser tab is active
2. Check userscript is running
3. Refresh page
4. Restart control mode

### Focus Not Visible

**Problem:** Can't see what's focused

**Solutions:**
1. Check element has focus styles
2. Try forcing outline:
   ```bash
   inspekt eval "document.activeElement.style.outline = '3px solid red'"
   ```
3. Some elements have `outline: none` - accessibility issue!

### Control Mode Exits Immediately

**Problem:** Mode starts and exits right away

**Solutions:**
1. Don't press `q` or `Ctrl+D` immediately
2. Check terminal supports raw mode
3. Try `inspekt control --help` first

### Can't Exit Control Mode

**Problem:** Can't quit with `q` or `Ctrl+D`

**Solutions:**
1. Press `Ctrl+C` (force quit)
2. Close terminal window
3. Restart terminal

### Voice Not Working

**Problem:** No text-to-speech on macOS

**Solutions:**
1. Verify `say` command works: `say "test"`
2. Check config: `"speak-all": true`
3. macOS only - not available on Linux/Windows

---

## Best Practices

### 1. Test on Real Content

Don't just test on example pages - test your actual site:

```bash
inspekt control
# Navigate your production site
# Verify real user workflows
```

### 2. Document Issues

Create accessibility audit reports:

```bash
# While in control mode, document issues:
# - Elements not reachable
# - Poor focus indicators
# - Illogical tab order
# - Keyboard traps
```

### 3. Compare with Screen Readers

Test with actual screen readers too:

- **NVDA** (Windows)
- **JAWS** (Windows)
- **VoiceOver** (macOS)
- **Orca** (Linux)

Inspekt control mode is a **supplement**, not a replacement.

### 4. Test Different Browsers

Keyboard behavior varies by browser:

```bash
# Test in Chrome
inspekt control

# Test in Firefox
inspekt control

# Test in Safari
inspekt control
```

---

## Next Steps

- **[Advanced Usage](advanced.md)** - Scripting and automation patterns
- **[Element Interaction](element-interaction.md)** - Click, wait, and interact commands

---

## Quick Reference

| Command | Action |
|---------|--------|
| `inspekt control` | Start keyboard control mode |
| `Tab` | Navigate forward |
| `Shift+Tab` | Navigate backward |
| `Enter` | Activate focused element |
| `Escape` | Return to body |
| `q` or `Ctrl+D` | Quit control mode |

**Config options:**
```json
{
  "control": {
    "verbose": true,        // Terminal announcements
    "speak-all": true,      // Text-to-speech (macOS)
    "verbose-logging": false // Debug output
  }
}
```

---

## Resources

- [WebAIM: Keyboard Accessibility](https://webaim.org/techniques/keyboard/)
- [WCAG 2.1: Keyboard Accessible](https://www.w3.org/WAI/WCAG21/Understanding/keyboard)
- [A11Y Project: Focus](https://www.a11yproject.com/posts/how-to-style-focus-states/)
