# Video Recording Tutorial

Learn how to record your replay sessions as video files for documentation, bug reports, and team collaboration.

## Prerequisites

Before you start, make sure you have:

1. **Inspekt installed** and the browser extension active
2. **A recording file** (`.yaml`) to replay
3. **ffmpeg** (will be auto-installed if missing)

## Quick Start

### Step 1: Create a Test Recording

If you don't have a recording yet, let's create a simple one:

```bash
# Start recording (auto-generates filename)
inspekt record

# Or specify a custom filename
inspekt record my-test.yaml
```

Perform a few actions (click some links, scroll around), then press ++ctrl+c++ to stop recording.

### Step 2: Replay with Video

Now replay your recording with video capture:

```bash
# Basic video recording (auto-names the file)
inspekt replay test-recording.yaml --video
```

This will:

1. Check if ffmpeg is installed (offer to install if not)
2. Start capturing frames from the browser
3. Execute all replay steps
4. Encode the frames into `test-recording_replay.mp4`

### Step 3: Watch Your Video

After encoding completes, you'll see:

```
✓ Video saved: /path/to/test-recording_replay.mp4
  2.4 MB • 45.0s • 450 frames @ 10 FPS
```

The file path is clickable in most modern terminals - just click to open!

## Customization Options

### Custom Filename

```bash
# Specify your own filename
inspekt replay test-recording.yaml --video=my-demo.mp4

# Use WebM format for smaller files
inspekt replay test-recording.yaml --video=my-demo.webm
```

### Frame Rate

Higher FPS = smoother video but larger files:

```bash
# Smoother video (15 FPS)
inspekt replay test-recording.yaml --video --fps=15

# Smaller file (5 FPS)
inspekt replay test-recording.yaml --video --fps=5
```

| FPS | Use Case |
|-----|----------|
| 5 | Presentations, slides |
| 10 | Default - good balance |
| 15 | Smooth demonstrations |
| 30 | High-quality recordings |

### Slow Motion for Clarity

Combine with speed options for clearer demonstrations:

```bash
# Half-speed replay with video
inspekt replay test-recording.yaml --slow --video=tutorial.mp4

# Quarter-speed for detailed walkthroughs
inspekt replay test-recording.yaml --very-slow --video=detailed-demo.mp4
```

### Auto-Open After Recording

Use `--open` to automatically open the video in your default player:

```bash
# Record and open immediately
inspekt replay test-recording.yaml --video --open

# Works on all platforms (macOS, Linux, Windows)
inspekt replay login-flow.yaml --video=demo.mp4 --open
```

## Try It Now!

Here's a complete example you can run right now:

```bash
# 1. Open a test page
inspekt open https://httpbin.org/forms/post

# 2. Record some interactions (saves to httpbin-form.yaml)
inspekt record httpbin-form.yaml
# Fill in the form fields, click Submit, then Ctrl+C to stop

# 3. Replay with video capture
inspekt replay httpbin-form.yaml --video --slow

# 4. Check your video!
# The file path in the output is clickable
```

Or use auto-generated filenames:

```bash
# Record (creates inspekt_YYYYMMDD_HHMMSS_domain_path.yaml)
inspekt record

# Replay the most recent recording with video
inspekt replay --video
```

## Video Dimensions

The video dimensions **exactly match your browser's viewport size**. Whatever you see in the browser is what you get in the video - pixel for pixel.

| Viewport | Video Output |
|----------|--------------|
| 1920×1080 | 1920×1080 |
| 1000×500 | 1000×500 |
| 375×667 (mobile) | 375×667 |

### Consistent Dimensions with --match-viewport

For reproducible videos across different machines, use `--match-viewport`:

```bash
# Resize browser to match recording, then capture video
inspekt replay checkout-flow.yaml --match-viewport --video
```

This is perfect for:

- **CI/CD pipelines** - Same video dimensions every time
- **Visual regression** - Compare videos frame-by-frame
- **Documentation** - Consistent output across team members

### Recording at Specific Sizes

To create videos at specific dimensions:

```bash
# 1. Record with viewport requirement
inspekt record --viewport 1280x720 my-test.yaml

# 2. Replay with matching viewport
inspekt replay my-test.yaml --match-viewport --video
# Result: 1280×720 video
```

## What's in the Video?

The recorded video includes Inspekt's visual overlay:

- **Target circles** - Pulsing indicators showing where clicks happen
- **Typing feedback** - Shows text being entered into fields
- **Action indicators** - Visual cues for navigation and other actions

This makes the video self-explanatory for viewers!

## Troubleshooting

### "ffmpeg not found"

Inspekt will offer to install ffmpeg automatically:

```
ffmpeg not found. Install with: brew install ffmpeg? [Y/n]
```

Type `y` to install, or install manually:

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu/Debian"
    ```bash
    sudo apt install ffmpeg
    ```

=== "Windows"
    Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### "Could not start video recording"

This usually means the Chrome DevTools Protocol connection failed. Try:

1. Make sure DevTools (F12) is **closed** in the browser
2. Refresh the page
3. Check the Inspekt extension is active

### No frames captured

If you see "No frames captured for video":

1. Ensure the browser tab is visible (not minimized)
2. Try a slower replay speed: `--slow`
3. Check browser console for errors

## Configuration

Set default video settings in your `config.json`:

```json
{
  "video": {
    "fps": 10,
    "quality": 80,
    "format": "mp4"
  }
}
```

CLI options always override config settings.

## Next Steps

- Learn about [Recording & Replay](recording-replay.md) for more recording tips
- Check the [replay command reference](../commands/replay.md) for all options
- Try [accessibility testing](accessibility-testing.md) with video evidence
