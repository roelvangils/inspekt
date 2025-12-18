# Recording, Playback & Video Export Architecture

This document explains how Inspekt's recording, playback, and video export systems work together.

## High-Level Overview

```mermaid
flowchart TB
    subgraph Recording["1. Recording Phase"]
        Browser1[Browser Tab] --> Extension1[Chrome Extension]
        Extension1 --> |DOM Events| RecordScript[record_events.js]
        RecordScript --> |Action Data| Bridge1[Bridge Server]
        Bridge1 --> |WebSocket| CLI1[inspekt record]
        CLI1 --> |Save| YAML[recording.yaml]
    end

    subgraph Playback["2. Playback Phase"]
        YAML --> CLI2[inspekt replay]
        CLI2 --> |Parse Steps| ReplayScript[replay_step.js]
        CLI2 --> |Visual Overlay| VisualScript[replay_visual.js]
        ReplayScript --> Extension2[Chrome Extension]
        Extension2 --> |Execute Actions| Browser2[Browser Tab]
    end

    subgraph VideoExport["3. Video Export Phase"]
        Browser2 --> |Mode Selection| ModeSwitch{--smooth?}
        ModeSwitch --> |Yes| SmoothMode[Smooth Mode]
        ModeSwitch --> |No| CompactMode[Compact Mode]
        SmoothMode --> |tabCapture + MediaRecorder| WebM[video.webm]
        CompactMode --> |Screenshots| Encoder[FFmpeg Encoder]
        Encoder --> MP4[video.mp4]
    end

    style Recording fill:#e8f5e9
    style Playback fill:#e3f2fd
    style VideoExport fill:#fff3e0
```

## Recording Flow

When you run `inspekt record`, the following happens:

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant Extension as Chrome Extension
    participant Bridge as Bridge Server (WS)
    participant CLI as inspekt record

    User->>CLI: inspekt record output.yaml
    CLI->>Bridge: Connect WebSocket
    CLI->>Extension: Inject record_events.js

    Note over Extension: Listening for DOM events

    User->>Browser: Click element
    Browser->>Extension: mousedown/click events
    Extension->>Extension: Compute selector & accessible name
    Extension->>Bridge: POST /action {type: click, target: {...}}
    Bridge->>CLI: WebSocket message
    CLI->>CLI: Append to steps[]

    User->>Browser: Type text
    Browser->>Extension: input/keydown events
    Extension->>Bridge: POST /action {type: type, value: "..."}
    Bridge->>CLI: WebSocket message

    User->>Browser: Press Tab
    Browser->>Extension: keydown event (Tab)
    Extension->>Extension: Capture focused element
    Extension->>Bridge: POST /action {type: keypress, key: Tab}
    Bridge->>CLI: WebSocket message

    User->>CLI: Ctrl+C (stop)
    CLI->>CLI: Write YAML file
    CLI->>User: Recording saved!
```

### Recording YAML Structure

```yaml
metadata:
  created_at: "2025-12-18T20:00:00"
  url: "https://example.com"
  viewport:
    width: 1280
    height: 720

steps:
  - action: navigate
    url: "https://example.com"
    timestamp: 0

  - action: click
    target:
      selector: "button.login"
      accessible_name: "Log in"
      tag: button
    timestamp: 1250

  - action: type
    target:
      selector: "input[name=email]"
      accessible_name: "Email address"
    value: "user@example.com"
    timestamp: 2100

  - action: keypress
    key: Tab
    timestamp: 3500
```

## Playback Flow

When you run `inspekt replay recording.yaml`, the following happens:

```mermaid
sequenceDiagram
    participant CLI as inspekt replay
    participant Bridge as Bridge Server
    participant Extension as Chrome Extension
    participant Browser
    participant Visual as Visual Overlay

    CLI->>CLI: Load & parse YAML
    CLI->>Bridge: Connect
    CLI->>Extension: Inject replay_visual.js
    Visual->>Browser: Show overlay UI

    loop For each step
        CLI->>CLI: Wait for timestamp delay
        CLI->>Extension: Execute replay_step.js with step data

        alt Click Action
            Extension->>Browser: Find element by selector
            Extension->>Browser: Scroll into view
            Visual->>Browser: Show click indicator
            Extension->>Browser: Dispatch click event
        else Type Action
            Extension->>Browser: Focus input element
            Extension->>Browser: Clear existing value
            loop For each character
                Extension->>Browser: Dispatch keydown/input/keyup
                Visual->>Browser: Update typing display
            end
        else Tab Keypress
            Extension->>Extension: Request CDP key dispatch
            Extension->>Browser: Input.dispatchKeyEvent (rawKeyDown)
            Browser->>Browser: Native focus navigation
            Visual->>Browser: Show focus ring
        else Navigate Action
            Extension->>Browser: window.location = url
            CLI->>CLI: Wait for page load
        end

        Extension->>CLI: Return result {ok: true/false}
        CLI->>CLI: Log step status
    end

    CLI->>User: Replay complete!
```

### Tab Key Special Handling (CDP)

Tab navigation requires special handling to trigger `:focus-visible`:

```mermaid
flowchart LR
    subgraph JavaScript["JavaScript Event (doesn't work)"]
        JS[dispatchEvent] --> |KeyboardEvent| NoFocus[No :focus-visible]
    end

    subgraph CDP["CDP Key Dispatch (works!)"]
        CDP_Cmd[Input.dispatchKeyEvent] --> |rawKeyDown| Native[Native Browser Input]
        Native --> Focus[:focus-visible triggers]
    end

    style JavaScript fill:#ffcdd2
    style CDP fill:#c8e6c9
```

## Video Export Modes

Inspekt supports two video recording modes, each optimized for different use cases:

### Mode Comparison

| Feature | Smooth Mode (`--smooth`) | Compact Mode (default) |
|---------|-------------------------|----------------------|
| **Capture Method** | tabCapture + MediaRecorder | Action screenshots |
| **Frame Rate** | Continuous (configurable FPS) | 1 frame per action |
| **File Size** | Larger (real video) | Smaller (slideshow) |
| **Animations** | Captures smoothly | May miss animations |
| **Scrolling** | Smooth scroll visible | Jump between positions |
| **Output Format** | WebM (native) or MP4 | MP4 or WebM |
| **Best For** | Demos, presentations | Documentation, diffs |

### Smooth Mode (`--smooth`)

Uses browser's native tab capture API (like screen sharing) with MediaRecorder for real video recording.

```mermaid
sequenceDiagram
    participant CLI as inspekt replay --video --smooth
    participant Bridge as Bridge Server
    participant Content as content.js
    participant Background as background.js
    participant Offscreen as offscreen.js
    participant MediaRecorder

    CLI->>Content: postMessage(START_SMOOTH_CAPTURE)
    Content->>Background: chrome.runtime.sendMessage
    Background->>Background: chrome.tabCapture.getMediaStreamId()
    Background->>Offscreen: Start MediaRecorder with streamId
    Offscreen->>MediaRecorder: new MediaRecorder(stream)
    MediaRecorder->>MediaRecorder: Recording chunks...

    Note over CLI: Replay executes all steps

    CLI->>Content: postMessage(STOP_SMOOTH_CAPTURE)
    Content->>Background: chrome.runtime.sendMessage
    Background->>Offscreen: Stop and get video data
    Offscreen->>Offscreen: Combine chunks to blob
    Offscreen->>Background: Base64 video data
    Background->>Bridge: POST /video/captured
    CLI->>Bridge: GET /video/get
    CLI->>CLI: Crop to viewport with FFmpeg
    CLI->>CLI: Save video file
```

**Key characteristics:**
- Records continuously at specified FPS (default: 10)
- Captures animations, scrolling, hover effects smoothly
- Uses VP9 codec in WebM container
- Video cropped to viewport dimensions (removes black bars from tab capture)
- Requires offscreen document for MediaRecorder (MV3 limitation)

### Compact Mode (default)

Takes a screenshot after each action, creating a slideshow-style video.

```mermaid
sequenceDiagram
    participant CLI as inspekt replay --video
    participant Extension as Chrome Extension
    participant FFmpeg

    Note over CLI: Initialize frame list

    loop For each step
        CLI->>CLI: Execute step
        CLI->>Extension: captureVisibleTab()
        Extension->>CLI: Screenshot bytes
        CLI->>CLI: frames.append((timestamp, bytes))
    end

    CLI->>CLI: Sort frames by timestamp
    CLI->>FFmpeg: Create concat demuxer
    FFmpeg->>CLI: video.mp4
```

**Key characteristics:**
- One frame per action (minimal file size)
- Uses FFmpeg concat demuxer for timing
- Each frame shown for duration until next action
- Good for documentation and visual diffs
- No animation capture between actions

### FFmpeg Concat Demuxer (Compact Mode)

The concat demuxer tells FFmpeg exactly how long to show each frame:

```
file '/tmp/frame_00000.jpg'
duration 2.300000
file '/tmp/frame_00001.jpg'
duration 0.200000
file '/tmp/frame_00002.jpg'
duration 1.500000
file '/tmp/frame_00002.jpg'
```

> **Note**: The last frame is listed twice (without duration) as required by FFmpeg's concat demuxer format.

## Component Architecture

```mermaid
graph TB
    subgraph CLI["Python CLI"]
        record[inspekt/app/cli/record.py]
        replay[inspekt/app/cli/replay.py]
        encoder[inspekt/services/video_encoder.py]
    end

    subgraph Bridge["Bridge Server"]
        bridge_ws[inspekt/bridge_ws.py]
        client[inspekt/client.py]
        video_endpoints["/video/captured<br>/video/get"]
    end

    subgraph Extension["Chrome Extension"]
        background[background.js]
        content[content.js]
        offscreen[offscreen.js]
        record_events[scripts/record_events.js]
        replay_step[scripts/replay_step.js]
        replay_visual[scripts/replay_visual.js]
    end

    record --> bridge_ws
    replay --> client
    replay --> encoder

    client --> bridge_ws
    bridge_ws <--> background
    bridge_ws <--> video_endpoints
    background <--> content
    background <--> offscreen
    content --> record_events
    content --> replay_step
    content --> replay_visual
```

## Key Files Reference

| Component | File | Purpose |
|-----------|------|---------|
| Record CLI | `inspekt/app/cli/record.py` | Recording command, YAML output |
| Replay CLI | `inspekt/app/cli/replay.py` | Playback command, video modes |
| Bridge Server | `inspekt/bridge_ws.py` | WebSocket server, video endpoints |
| Bridge Client | `inspekt/client.py` | Python ↔ Extension communication |
| Video Encoder | `inspekt/services/video_encoder.py` | FFmpeg wrapper (compact mode) |
| Recording Script | `inspekt/scripts/record_events.js` | DOM event capture |
| Replay Script | `inspekt/scripts/replay_step.js` | Action execution |
| Visual Overlay | `inspekt/scripts/replay_visual.js` | UI feedback during replay |
| Background.js | `extensions/chrome/background.js` | tabCapture, CDP, message routing |
| Content.js | `extensions/chrome/content.js` | postMessage bridge |
| Offscreen.js | `extensions/chrome/offscreen.js` | MediaRecorder for smooth mode |

## Usage Examples

```bash
# Smooth mode - continuous video recording (captures animations)
inspekt replay recording.yaml --video demo.webm --smooth
inspekt replay recording.yaml --video demo.mp4 --smooth --fps 15

# Compact mode - screenshot per action (smaller files)
inspekt replay recording.yaml --video output.mp4
inspekt replay recording.yaml --video output.webm --compact

# Additional options
inspekt replay recording.yaml --video --open          # Open after creation
inspekt replay recording.yaml --video --include-effects  # Add audio cues
```

---

*Last updated: 2025-12-19*
