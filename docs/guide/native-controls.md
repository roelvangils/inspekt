# Recording and Replaying Native Controls

This guide explains how Inspekt handles native HTML controls that use **closed Shadow DOM** during recording and replay. This includes media elements (`<audio>`, `<video>`) and several input types (`range`, `date`, `time`, `color`, etc.).

## Understanding Closed Shadow DOM

Several native HTML elements use **closed Shadow DOM** to render their internal controls. This is a security and UX decision by browser vendors - they don't want scripts tampering with native controls.

### Affected Elements

| Element | Internal Controls |
|---------|------------------|
| `<audio controls>` | Play/pause, progress bar, volume, mute |
| `<video controls>` | Play/pause, progress bar, volume, mute, fullscreen |
| `<input type="range">` | Slider track and thumb |
| `<input type="date">` | Calendar picker, day/month/year segments |
| `<input type="time">` | Hour/minute/second spinners |
| `<input type="datetime-local">` | Combined date and time controls |
| `<input type="month">` | Month/year picker |
| `<input type="week">` | Week/year picker |
| `<input type="number">` | Spinner increment/decrement buttons |
| `<input type="color">` | Color picker dialog |

### The Problem

```javascript
// These all return null - access denied!
document.querySelector('audio').shadowRoot;
document.querySelector('input[type="range"]').shadowRoot;
document.querySelector('input[type="date"]').shadowRoot;
```

Without intervention:
1. JavaScript cannot detect which internal control has focus
2. JavaScript cannot directly click internal buttons or drag sliders
3. Synthetic keyboard events don't trigger native behaviors
4. Tab navigation can get "stuck" inside the Shadow DOM

---

## Inspekt's Solution

Inspekt treats all native controls with closed Shadow DOM as **single Tab stops** and handles interaction keypresses **silently** via APIs.

### Key Principles

1. **Single Tab stop**: Tab/Shift+Tab moves focus to the next/previous DOM element, not internal controls
2. **Silent interaction**: Arrow keys, Space, etc. use APIs to change values but are **never recorded**
3. **Final value only**: When you Tab away, the final value is recorded as a `type` action (for inputs)

### Why Not Record Keypresses?

Recording individual keypresses would create unreliable recordings:
- Multiple `ArrowRight` keypresses in a row might not produce the same final value
- Step sizes vary by element and step attribute
- Date/time pickers have complex multi-segment navigation
- Media seek positions depend on playback state

Instead, Inspekt captures the **intent**: you wanted the slider to be at 75%, not "press ArrowRight 15 times."

---

## Native Control Warnings

When you start recording on a page with native controls, Inspekt displays informational notes:

```
i Note: This page contains 1 audio element with native controls.
  Media players are treated as a single Tab stop during recording.
  Use Space/Enter to play/pause, Arrow keys for seek/volume.

i Note: This page contains 2 range sliders and 1 date picker.
  Native inputs are treated as a single Tab stop during recording.
  Arrow keys adjust values (not recorded). Only the final value is recorded on Tab.
```

---

## Media Elements (Audio/Video)

### Supported Keyboard Shortcuts

While focused on a media element, these keys work but are **not recorded**:

| Key | Action |
|-----|--------|
| `Space` or `Enter` | Toggle play/pause |
| `ArrowLeft` | Seek back 5 seconds |
| `ArrowRight` | Seek forward 5 seconds |
| `ArrowUp` | Increase volume 10% |
| `ArrowDown` | Decrease volume 10% |
| `M` | Toggle mute |

### Recording Behavior

```yaml
# Tab to the audio player - this IS recorded
- timestamp: 1000
  action: keypress
  key: Tab
  target:
    selector: "audio#player"
    tag: audio

# Press Space to play - NOT recorded, uses API silently

# Press ArrowRight to seek - NOT recorded, uses API silently

# Tab away - this IS recorded
- timestamp: 5000
  action: keypress
  key: Tab
  target:
    selector: "#next-button"
    tag: button
```

Note: Media state changes (play/pause, volume, etc.) are ephemeral and not recorded because media always starts fresh during replay.

---

## Range Sliders

### Supported Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `ArrowLeft` / `ArrowDown` | Decrease by step |
| `ArrowRight` / `ArrowUp` | Increase by step |
| `Home` | Jump to minimum |
| `End` | Jump to maximum |
| `PageUp` | Increase by 10x step |
| `PageDown` | Decrease by 10x step |

### Recording Behavior

```yaml
# Tab to the range slider
- timestamp: 1000
  action: keypress
  key: Tab
  target:
    selector: "input#volume"
    tag: input
    input_type: range

# Press ArrowRight multiple times - NOT recorded

# Tab away (final value IS recorded)
- timestamp: 3000
  action: type
  target:
    selector: "input#volume"
    tag: input
  value: "75"

- timestamp: 3100
  action: keypress
  key: Tab
  target:
    selector: "#next-element"
```

### Replay Behavior

During replay, the `type` action sets the value directly:

```javascript
element.value = "75";
element.dispatchEvent(new Event('input', { bubbles: true }));
element.dispatchEvent(new Event('change', { bubbles: true }));
```

---

## Date and Time Inputs

### Supported Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `ArrowUp` / `ArrowRight` | Step up (next day/hour/etc.) |
| `ArrowDown` / `ArrowLeft` | Step down (previous day/hour/etc.) |

Note: The exact behavior depends on the browser and which segment (day, month, year) is focused within the picker.

### Recording Behavior

```yaml
# Tab to date picker
- timestamp: 1000
  action: keypress
  key: Tab
  target:
    selector: "input#birthdate"
    tag: input
    input_type: date

# Use arrow keys to select date - NOT recorded

# Tab away (final value IS recorded)
- timestamp: 5000
  action: type
  target:
    selector: "input#birthdate"
    tag: input
  value: "2024-03-15"
```

---

## Number Inputs

Number inputs behave slightly differently from range sliders:

- `ArrowUp` / `ArrowDown` use `stepUp()` / `stepDown()` - NOT recorded
- `ArrowLeft` / `ArrowRight` move the cursor within the field - normal behavior
- Typing digits is recorded as normal `type` actions

### Recording Behavior

```yaml
# Tab to number input
- timestamp: 1000
  action: keypress
  key: Tab
  target:
    selector: "input#quantity"
    tag: input
    input_type: number

# Press ArrowUp to increment - NOT recorded

# Type some digits - recorded as type action
- timestamp: 2000
  action: type
  target:
    selector: "input#quantity"
  value: "42"
```

---

## Color Pickers

Color inputs open a native color picker dialog. The interaction is captured when the dialog closes:

```yaml
# Tab to color picker
- timestamp: 1000
  action: keypress
  key: Tab
  target:
    selector: "input#bgcolor"
    tag: input
    input_type: color

# Open picker and select color - NOT recorded

# Tab away (final value IS recorded)
- timestamp: 5000
  action: type
  target:
    selector: "input#bgcolor"
  value: "#ff5500"
```

---

## Display in Recording Output

When you Tab to native controls, the recording output shows descriptive labels:

```
0021   00:25   keypress    Tab (Submit Button)
0022   00:26   keypress    Tab (Native Range Slider)
0023   00:30   type        input[type="range"] (value: 75)
0024   00:31   keypress    Tab (Native Date Picker)
0025   00:35   type        input[type="date"] (value: 2024-03-15)
0026   00:36   keypress    Tab (Native Audio Player)
0027   00:40   keypress    Tab (Next Button)
```

---

## Limitations

### What Works

- Tab/Shift+Tab navigation (single tab stop)
- Arrow key adjustments via APIs
- Capturing final values on blur
- Reliable replay via direct value setting

### What Doesn't Work

1. **Clicking specific internal controls**
   - Cannot click specific points on a slider
   - Cannot click specific days in a calendar
   - Cannot click play button on media player

2. **Precise mouse-based interactions**
   - Cannot drag slider to exact position
   - Cannot scrub through media timeline with mouse

3. **Complex date picker navigation**
   - Cannot navigate between month views
   - Cannot record specific calendar navigation patterns

### Why These Limitations Exist

These are **browser security restrictions**, not Inspekt limitations. Closed Shadow DOM is intentional:

1. **Security** - Prevents malicious scripts from hijacking controls
2. **Consistency** - Ensures users see standard browser controls
3. **Accessibility** - Browser vendors ensure their controls meet accessibility standards

---

## Best Practices

### 1. Use Tab, Then Arrow Keys

```yaml
# Good pattern for adjusting a slider:
- action: keypress
  key: Tab
  # Focus the slider (recorded)

# Use arrow keys to adjust (not recorded, just use them)

- action: keypress
  key: Tab
  # Move away - final value is captured
```

### 2. Don't Click Native Controls

Mouse clicks on native controls:
- Target the outer element, not internal controls
- May not produce reliable results during replay
- Are less accessible than keyboard interaction

### 3. Use Custom Controls for Complex Testing

If you need to test specific slider positions or calendar navigation:

```html
<!-- Custom range slider with accessible, automatable controls -->
<div class="custom-slider">
  <input type="hidden" id="volume-value" value="50">
  <div class="slider-track">
    <div class="slider-thumb" role="slider"
         aria-valuemin="0" aria-valuemax="100"
         aria-valuenow="50" tabindex="0">
    </div>
  </div>
</div>
```

### 4. Add Assertions for Final Values

Verify values after interaction:

```yaml
- action: keypress
  key: Tab  # Move away from slider
- action: inspekt
  command: "js 'document.querySelector(\"#volume\").value'"
  expect:
    output-contains: "75"
```

---

## Technical Reference

### Input Step APIs

Inspekt uses these methods during recording:

```javascript
// For range, number, date, time, etc.
element.stepUp();    // Increment by step
element.stepDown();  // Decrement by step

// Setting values directly
element.value = newValue;
element.dispatchEvent(new Event('input', { bubbles: true }));
element.dispatchEvent(new Event('change', { bubbles: true }));
```

### Media Element APIs

```javascript
// Play/pause
element.play();
element.pause();

// Seek
element.currentTime = newTime;

// Volume
element.volume = 0.5;  // 0.0 to 1.0
element.muted = true;
```

---

## Summary

- Native controls with **closed Shadow DOM** cannot have their internal elements accessed
- Inspekt treats them as **single Tab stops** for reliable recording/replay
- Interaction keypresses are **handled silently** via APIs (not recorded)
- Only the **final value** is recorded when focus leaves the element
- During replay, values are **set directly** via the element's value property
- For complex testing scenarios, consider **custom controls** instead of native ones

## Related Documentation

- [Recording and Replaying](recording-replay.md)
- [Keyboard Navigation Testing](accessibility-testing.md)
- [Shadow DOM Support](recording-replay.md#shadow-dom-support)
