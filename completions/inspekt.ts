/**
 * Fig Completion Spec for Inspekt CLI
 *
 * This provides native autocompletion in terminals that support Fig specs,
 * including Warp (which acquired Fig) and Amazon Q Developer CLI.
 *
 * Installation:
 *   mkdir -p ~/.fig/user/autocomplete
 *   cp completions/inspekt.ts ~/.fig/user/autocomplete/inspekt.ts
 *
 * For Warp, the spec is automatically compiled and loaded.
 */

// Generator for YAML recording files
const recordingFilesGenerator: Fig.Generator = {
  script: ["bash", "-c", "ls -t *.yaml 2>/dev/null | head -20"],
  postProcess: (output) => {
    if (!output) return [];
    return output.split("\n").filter(Boolean).map((file) => ({
      name: file,
      description: "Recording file",
      icon: "fig://icon?type=yaml",
    }));
  },
};

// Generator for MP4/WebM video files
const videoFilesGenerator: Fig.Generator = {
  script: ["bash", "-c", "ls -t *.{mp4,webm} 2>/dev/null | head -10"],
  postProcess: (output) => {
    if (!output) return [];
    return output.split("\n").filter(Boolean).map((file) => ({
      name: file,
      description: "Video file",
      icon: "fig://icon?type=video",
    }));
  },
};

// Common options shared across commands
const jsonOption: Fig.Option = {
  name: "--json",
  description: "Output results as JSON",
};

const timeoutOption: Fig.Option = {
  name: "--timeout",
  description: "Execution timeout in seconds (default: 30)",
  args: { name: "seconds", default: "30" },
};

const verboseOption: Fig.Option = {
  name: ["-v", "--verbose"],
  description: "Show detailed output",
};

const completionSpec: Fig.Spec = {
  name: "inspekt",
  description: "Browser automation and inspection from the command line",
  options: [
    { name: "--version", description: "Show the version and exit" },
    { name: ["-v", "--verbose"], description: "Enable verbose output (timing, requests, state changes)" },
    { name: "--help", description: "Show this message and exit" },
  ],
  subcommands: [
    // === Navigation Commands ===
    {
      name: "open",
      description: "Navigate to a URL",
      args: {
        name: "url",
        description: "The URL to navigate to",
      },
      options: [
        { name: "--wait", description: "Wait condition: load, domcontentloaded, or networkidle", args: { name: "condition", suggestions: ["load", "domcontentloaded", "networkidle"] } },
        timeoutOption,
        jsonOption,
      ],
    },
    {
      name: "back",
      description: "Go back to the previous page in browser history",
    },
    {
      name: "forward",
      description: "Go forward to the next page in browser history",
    },
    {
      name: "reload",
      description: "Reload the current page",
      options: [
        { name: "--hard", description: "Hard reload (bypass cache)" },
      ],
    },

    // === Scrolling Commands ===
    {
      name: "top",
      description: "Scroll to the top of the page",
    },
    {
      name: "bottom",
      description: "Scroll to the bottom of the page",
    },
    {
      name: "pageup",
      description: "Scroll up one page (one viewport height)",
    },
    {
      name: "pagedown",
      description: "Scroll down one page (one viewport height)",
    },

    // === Interaction Commands ===
    {
      name: "click",
      description: "Click on an element",
      args: { name: "selector", description: "CSS selector for the element" },
    },
    {
      name: "double-click",
      description: "Double-click on an element",
      args: { name: "selector", description: "CSS selector for the element" },
    },
    {
      name: "right-click",
      description: "Right-click (context menu) on an element",
      args: { name: "selector", description: "CSS selector for the element" },
    },
    {
      name: "type",
      description: "Type text character by character into the browser",
      args: { name: "text", description: "The text to type" },
      options: [
        { name: "--submit", description: "Press Enter after typing" },
        { name: "--speed", description: "Typing speed: instant, fast, normal, slow", args: { name: "speed", suggestions: ["instant", "fast", "normal", "slow"] } },
      ],
    },
    {
      name: "paste",
      description: "Paste text instantly into the browser",
      args: { name: "text", description: "The text to paste" },
    },
    {
      name: "do",
      description: "Find and execute actionable elements matching a natural language query",
      args: { name: "query", description: "Natural language description of what to do" },
    },
    {
      name: "wait",
      description: "Wait for an element to appear, be visible, hidden, or removed",
      args: { name: "selector", description: "CSS selector for the element" },
      options: [
        { name: "--state", description: "State to wait for", args: { name: "state", suggestions: ["visible", "hidden", "attached", "detached"] } },
        timeoutOption,
      ],
    },

    // === Extraction Commands ===
    {
      name: "links",
      description: "Extract all links from the current page",
      options: [
        { name: "--filter", description: "Filter links by type", args: { name: "type", suggestions: ["internal", "external", "all"] } },
        { name: "--include-anchors", description: "Include same-page anchor links" },
        jsonOption,
      ],
    },
    {
      name: "outline",
      description: "Display the page's heading structure as a nested outline",
      options: [jsonOption],
    },
    {
      name: "selection",
      description: "Get the current text selection in the browser",
      options: [
        { name: "--format", description: "Output format", args: { name: "format", suggestions: ["text", "html", "markdown"] } },
        jsonOption,
      ],
    },
    {
      name: "screenshot",
      description: "Capture screenshots of elements, viewport, or full page",
      options: [
        { name: "--target", description: "What to capture", args: { name: "target", suggestions: ["viewport", "page", "element"] } },
        { name: "--selector", description: "CSS selector for element screenshot", args: { name: "selector" } },
        { name: "--format", description: "Image format", args: { name: "format", suggestions: ["png", "jpeg"] } },
        { name: "--quality", description: "JPEG quality (1-100)", args: { name: "quality" } },
        { name: "--output", description: "Output file path", args: { name: "path", template: "filepaths" } },
      ],
    },
    {
      name: "index",
      description: "Index the current page with full semantic structure",
      options: [
        { name: "--no-cache", description: "Force re-index instead of using cache" },
        jsonOption,
      ],
    },

    // === AI Commands ===
    {
      name: "ask",
      description: "Ask a question about the current page using AI",
      args: { name: "question", description: "The question to ask" },
      options: [
        { name: "--debug", description: "Show the full prompt instead of calling AI" },
        { name: "--no-cache", description: "Force re-index instead of using cache" },
      ],
    },
    {
      name: "describe",
      description: "Generate an AI-powered description of the page for screen readers",
      options: [
        { name: "--no-cache", description: "Force regeneration instead of using cache" },
        jsonOption,
      ],
    },
    {
      name: "summarize",
      description: "Summarize the current article using AI",
      options: [
        { name: "--debug", description: "Show the full prompt instead of calling AI" },
        jsonOption,
      ],
    },

    // === Accessibility Commands ===
    {
      name: "axe",
      description: "Run axe-core accessibility audit on the current page",
      options: [
        { name: "--level", description: "WCAG conformance level", args: { name: "level", suggestions: ["2a", "2aa", "2aaa", "21a", "21aa", "22aa"] } },
        { name: "--rule", description: "Check specific accessibility rule by ID", args: { name: "rule" } },
        { name: "--list-rules", description: "List all available axe-core rules and exit" },
        { name: "--tags", description: "Additional comma-separated tags", args: { name: "tags" } },
        { name: "--include-passes", description: "Include passing checks in output" },
        { name: "--include-incomplete", description: "Include incomplete checks (require manual review)" },
        timeoutOption,
        jsonOption,
      ],
    },
    {
      name: "autocomplete",
      description: "Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5",
      options: [
        { name: "--threshold", description: "Minimum confidence (0-1)", args: { name: "threshold", default: "0.5" } },
        { name: "--include-hidden", description: "Include hidden input fields" },
        { name: "--include-disabled", description: "Include disabled input fields" },
        timeoutOption,
        jsonOption,
      ],
    },

    // === Recording & Replay Commands ===
    {
      name: "record",
      description: "Record browser interactions to a YAML file",
      args: {
        name: "filename",
        description: "Output filename (auto-generated if not specified)",
        isOptional: true,
      },
      options: [
        { name: ["-o", "--output"], description: "Output filename", args: { name: "filename" } },
        { name: "--include-hover", description: "Record hover events on interactive elements" },
        { name: "--no-hover", description: "Skip hover events" },
        { name: "--mask-passwords", description: "Mask password input values" },
        { name: "--no-mask-passwords", description: "Don't mask password input values" },
        { name: "--min-hover-duration", description: "Minimum hover duration in ms", args: { name: "ms", default: "200" } },
        { name: "--replay", description: "Automatically replay after saving to verify" },
        { name: "--open", description: "Open the recording in default application after saving" },
        { name: "--no-audio", description: "Disable audio feedback during replay" },
        { name: "--no-visual", description: "Disable visual feedback during replay" },
        { name: "--no-feedback", description: "Disable both audio and visual feedback" },
        { name: ["-i", "--interactive"], description: "Step through replay manually" },
        { name: "--capture-state", description: "Capture cookies, localStorage, and scroll position" },
        { name: "--storage-keys", description: "Comma-separated list of storage keys to capture", args: { name: "keys" } },
        { name: "--checksum", description: "Generate DOM structure checksum for verification" },
        { name: "--synthetic-dialogs", description: "Use non-blocking HTML overlays for alert/confirm/prompt" },
        { name: "--match-viewport", description: "Mark viewport size as requirement for faithful replay" },
        { name: "--match-zoom-level", description: "Mark zoom level as requirement for faithful replay" },
        { name: ["-f", "--force"], description: "Override existing file without prompting" },
        { name: "--viewport", description: "Resize browser to specific viewport before recording", args: { name: "WxH", description: "e.g., 1024x768" } },
        { name: "--faithful", description: "Capture focus styles for pixel-perfect keyboard navigation (experimental)" },
      ],
      subcommands: [
        { name: "list", description: "List all saved recordings" },
        { name: "show", description: "Show details of a recording file", args: { name: "file", generators: recordingFilesGenerator } },
        { name: "edit", description: "Open a recording file in your default editor", args: { name: "file", generators: recordingFilesGenerator } },
        { name: "delete", description: "Delete a recording file", args: { name: "file", generators: recordingFilesGenerator } },
        { name: "tidy", description: "Tidy up a recording file", args: { name: "file", generators: recordingFilesGenerator } },
        { name: "tutorial", description: "Interactive tutorial for the record command" },
      ],
    },
    {
      name: "replay",
      description: "Replay a recorded browser interaction session",
      args: {
        name: "recording_file",
        description: "The YAML recording file to replay",
        isOptional: true,
        generators: recordingFilesGenerator,
      },
      options: [
        { name: "--speed", description: "Playback speed multiplier (e.g., 2.0 for 2x)", args: { name: "multiplier" } },
        { name: "--slow", description: "Half speed (0.5x)" },
        { name: "--very-slow", description: "Quarter speed (0.25x)" },
        { name: "--instant", description: "No delays between steps" },
        { name: "--step-delay", description: "Delay between steps in milliseconds", args: { name: "ms", default: "0" } },
        { name: "--dry-run", description: "Show steps without executing them" },
        { name: "--start-step", description: "Start from step number (1-indexed)", args: { name: "step" } },
        { name: "--end-step", description: "End at step number (1-indexed, inclusive)", args: { name: "step" } },
        { name: "--skip-hover", description: "Skip all hover actions" },
        { name: "--skip", description: "Skip specific action types", args: { name: "type", suggestions: ["hover", "keypress", "type", "click", "navigate"] } },
        { name: "--pause-on-fail", description: "Pause and wait for Enter after each failure" },
        { name: ["-v", "--verbose"], description: "Show detailed output for each step" },
        { name: "--no-visual", description: "Disable visual indicators" },
        { name: "--no-audio", description: "Disable audio cues" },
        { name: "--no-feedback", description: "Disable both visual and audio feedback" },
        { name: "--lock", description: "Lock input during replay" },
        { name: ["-i", "--interactive"], description: "Step through replay manually" },
        { name: ["-e", "--stop-on-error"], description: "Stop on first failure" },
        { name: ["-T", "--skip-tests"], description: "Skip assertion checks" },
        { name: "--restore-state", description: "Restore all captured state" },
        { name: "--restore-cookies", description: "Restore cookies from recording" },
        { name: "--restore-storage", description: "Restore localStorage/sessionStorage" },
        { name: "--verify-checksum", description: "Verify DOM structure checksum matches" },
        { name: "--strict-preconditions", description: "Halt if preconditions are not met" },
        { name: "--strict-checksum", description: "Halt if checksum does not match" },
        { name: ["-p", "--progress"], description: "Show compact progress bar" },
        { name: "--skip-validation", description: "Skip preflight validation checks" },
        { name: "--video", description: "Record replay to video file", args: { name: "path", isOptional: true } },
        { name: "--smooth", description: "Record smooth video with continuous frames" },
        { name: "--compact", description: "Record compact video with 1 frame per action" },
        { name: "--fps", description: "Video frame rate (5-30)", args: { name: "fps", default: "10" } },
        { name: "--open", description: "Open video file after creation" },
        { name: "--include-effects", description: "Include audio effects in video" },
        { name: "--no-effects", description: "Exclude audio effects from video" },
        { name: "--match-viewport", description: "Resize browser to match recorded viewport" },
        { name: "--match-zoom-level", description: "Set browser zoom to match recording" },
        { name: "--faithful", description: "Use captured focus styles for pixel-perfect replay" },
      ],
    },
    {
      name: "validate",
      description: "Validate a recording file before replay",
      args: {
        name: "recording_file",
        description: "The YAML recording file to validate",
        generators: recordingFilesGenerator,
      },
    },

    // === Storage Commands ===
    {
      name: "storage",
      description: "Manage browser storage (cookies, localStorage, sessionStorage)",
      subcommands: [
        {
          name: "cookies",
          description: "Manage cookies",
          subcommands: [
            { name: "list", description: "List all cookies for current page", options: [jsonOption] },
            {
              name: "set",
              description: "Set a cookie",
              args: [
                { name: "name", description: "Cookie name" },
                { name: "value", description: "Cookie value" },
              ],
              options: [
                { name: "--domain", description: "Cookie domain", args: { name: "domain" } },
                { name: "--path", description: "Cookie path", args: { name: "path", default: "/" } },
                { name: "--secure", description: "Secure flag" },
                { name: "--httponly", description: "HttpOnly flag" },
                { name: "--samesite", description: "SameSite attribute", args: { name: "value", suggestions: ["Strict", "Lax", "None"] } },
                { name: "--expires", description: "Expiration date", args: { name: "date" } },
              ],
            },
            { name: "delete", description: "Delete a cookie", args: { name: "name", description: "Cookie name" } },
            { name: "clear", description: "Clear all cookies" },
          ],
        },
        {
          name: "local",
          description: "Manage localStorage",
          subcommands: [
            { name: "list", description: "List all localStorage items", options: [jsonOption] },
            { name: "get", description: "Get a localStorage item", args: { name: "key" } },
            { name: "set", description: "Set a localStorage item", args: [{ name: "key" }, { name: "value" }] },
            { name: "delete", description: "Delete a localStorage item", args: { name: "key" } },
            { name: "clear", description: "Clear all localStorage" },
          ],
        },
        {
          name: "session",
          description: "Manage sessionStorage",
          subcommands: [
            { name: "list", description: "List all sessionStorage items", options: [jsonOption] },
            { name: "get", description: "Get a sessionStorage item", args: { name: "key" } },
            { name: "set", description: "Set a sessionStorage item", args: [{ name: "key" }, { name: "value" }] },
            { name: "delete", description: "Delete a sessionStorage item", args: { name: "key" } },
            { name: "clear", description: "Clear all sessionStorage" },
          ],
        },
      ],
    },
    {
      name: "cookies",
      description: "[DEPRECATED] Manage browser cookies (use 'inspekt storage cookies')",
    },

    // === Info & Inspection Commands ===
    {
      name: "info",
      description: "Page information and analysis",
      options: [jsonOption],
    },
    {
      name: "inspect",
      description: "Select an element and show its details",
    },
    {
      name: "inspected",
      description: "Get information about the currently inspected element",
      options: [jsonOption],
    },
    {
      name: "md-link",
      description: "Get Markdown link for the current page",
    },
    {
      name: "robots",
      description: "Fetch and parse robots.txt for the current page",
      options: [jsonOption],
    },
    {
      name: "network",
      description: "Show network requests from the current page",
      options: [
        { name: "--type", description: "Filter by resource type", args: { name: "type", suggestions: ["script", "stylesheet", "fetch", "xhr", "image", "font", "document"] } },
        { name: "--sort", description: "Sort field", args: { name: "field", suggestions: ["start", "time", "size", "name", "type"] } },
        { name: "--errors-only", description: "Only show failed requests" },
        { name: "--limit", description: "Maximum entries to return", args: { name: "count" } },
        jsonOption,
      ],
    },

    // === Console Commands ===
    {
      name: "console",
      description: "Browser console message commands",
      subcommands: [
        {
          name: "list",
          description: "List captured console messages",
          options: [
            { name: "--level", description: "Filter by log level", args: { name: "level", suggestions: ["all", "error", "warn", "log", "info", "debug"] } },
            { name: "--limit", description: "Maximum messages to return", args: { name: "count", default: "100" } },
            { name: "--tail", description: "Show most recent messages first" },
            jsonOption,
          ],
        },
        {
          name: "log",
          description: "Evaluate a JavaScript expression and log the result",
          args: { name: "expression", description: "JavaScript expression to evaluate" },
          options: [
            { name: "-t", description: "Timeout in seconds", args: { name: "seconds", default: "10" } },
          ],
        },
        {
          name: "clear",
          description: "Clear the console message buffer",
        },
      ],
    },
    {
      name: "eval",
      description: "Execute JavaScript code in the active browser tab",
      args: { name: "code", description: "JavaScript code to execute" },
      options: [
        timeoutOption,
        jsonOption,
      ],
    },
    {
      name: "exec",
      description: "Execute JavaScript from a file",
      args: { name: "file", description: "JavaScript file to execute", template: "filepaths" },
    },
    {
      name: "log",
      description: "Evaluate an expression and log the result",
      args: { name: "expression", description: "JavaScript expression to evaluate" },
    },

    // === Plugin Commands ===
    {
      name: "plugin",
      description: "Manage custom JavaScript plugins (bookmarklets)",
      subcommands: [
        { name: "list", description: "List installed plugins" },
        { name: "add", description: "Add a new plugin", args: { name: "file", template: "filepaths" } },
        { name: "remove", description: "Remove a plugin", args: { name: "name" } },
        { name: "run", description: "Run a plugin", args: { name: "name" } },
        { name: "edit", description: "Edit a plugin", args: { name: "name" } },
        { name: "show", description: "Show plugin source", args: { name: "name" } },
      ],
    },

    // === Server Management Commands ===
    {
      name: "start",
      description: "Start Inspekt servers (bridge + API) in daemon mode",
      options: [
        { name: "--bridge-only", description: "Start only the bridge server" },
        { name: "--port", description: "Bridge server port", args: { name: "port", default: "8765" } },
        { name: "--foreground", description: "Run in foreground instead of daemon mode" },
      ],
    },
    {
      name: "stop",
      description: "Stop Inspekt servers",
    },
    {
      name: "restart",
      description: "Restart bridge and API servers",
    },
    {
      name: "status",
      description: "Check status of all Inspekt servers",
      options: [jsonOption],
    },

    // === VM Commands ===
    {
      name: "vm",
      description: "Manage the Inspekt Browser VM",
      subcommands: [
        {
          name: "start",
          description: "Start the Inspekt Browser VM",
          options: [
            { name: "--dev", description: "Enable development mode (mount local source files)" },
            { name: "--no-dev", description: "Disable development mode" },
            { name: "--rebuild", description: "Force rebuild of the Docker image" },
            { name: "--no-cache", description: "Rebuild without using Docker cache" },
          ],
        },
        { name: "stop", description: "Stop the Inspekt Browser VM" },
        {
          name: "restart",
          description: "Restart the Inspekt Browser VM",
          options: [
            { name: "--dev", description: "Enable development mode" },
            { name: "--no-dev", description: "Disable development mode" },
          ],
        },
        { name: "status", description: "Check the status of the Browser VM" },
        { name: "open", description: "Open the VM control panel in your browser" },
        { name: "logs", description: "Show VM container logs", options: [{ name: "-f", description: "Follow log output" }] },
        { name: "shell", description: "Open a shell inside the VM container" },
        { name: "cleanup", description: "Clean up ALL VM containers and free ports" },
      ],
    },

    // === MCP Commands ===
    {
      name: "mcp",
      description: "Manage the MCP server for AI assistant integration",
      subcommands: [
        {
          name: "start",
          description: "Start the MCP server in stdio mode",
          options: [
            { name: "--bridge-port", description: "Bridge server port", args: { name: "port", default: "8765" } },
            { name: "--cache-ttl", description: "Resource cache TTL in seconds", args: { name: "seconds", default: "5" } },
          ],
        },
        {
          name: "info",
          description: "Show information about available MCP tools and resources",
          options: [jsonOption],
        },
        {
          name: "describe",
          description: "Show detailed documentation for a specific MCP tool",
          args: { name: "tool_name", description: "Name of the MCP tool" },
          options: [jsonOption],
        },
        { name: "test", description: "Test MCP server connectivity and basic functionality" },
      ],
    },

    // === Setup & Configuration Commands ===
    {
      name: "setup",
      description: "Interactive setup wizard for new users",
    },
    {
      name: "config",
      description: "Open the configuration file in your default editor",
    },
    {
      name: "userscript",
      description: "Display the userscript that needs to be installed in your browser",
    },
    {
      name: "completion",
      description: "Shell tab completion setup",
      subcommands: [
        {
          name: "install",
          description: "Install shell completion",
          args: { name: "shell", suggestions: ["bash", "zsh", "fish"] },
        },
        { name: "status", description: "Check completion installation status" },
        { name: "uninstall", description: "Remove shell completion" },
      ],
    },
    {
      name: "domain",
      description: "Manage allowed domains for browser automation",
      subcommands: [
        { name: "list", description: "List allowed domains" },
        { name: "add", description: "Add a domain to allowed list", args: { name: "domain" } },
        { name: "remove", description: "Remove a domain from allowed list", args: { name: "domain" } },
        { name: "clear", description: "Clear all allowed domains" },
      ],
    },
    {
      name: "queue",
      description: "Manage the request queue",
      subcommands: [
        { name: "list", description: "List queued requests" },
        { name: "clear", description: "Clear the queue" },
      ],
    },
    {
      name: "yolo",
      description: "YOLO mode - bypass ALL restrictions for 1 hour",
    },

    // === Other Commands ===
    {
      name: "watch",
      description: "Watch browser events in real-time",
      options: [
        { name: "--events", description: "Event types to watch", args: { name: "events" } },
      ],
    },
    {
      name: "download",
      description: "Find and download files from the current page",
      args: { name: "query", description: "Search query for files to download", isOptional: true },
    },
    {
      name: "save",
      description: "Save the current page as a single HTML file",
      options: [
        { name: "--output", description: "Output file path", args: { name: "path", template: "filepaths" } },
        { name: "--remote-images", description: "Keep image URLs instead of embedding" },
        { name: "--no-images", description: "Skip images entirely" },
        { name: "--optimize", description: "Aggressive cleanup for large pages" },
        { name: "--compress", description: "Minimize HTML/CSS output" },
        jsonOption,
      ],
    },
    {
      name: "repl",
      description: "Start an interactive REPL session",
    },
    {
      name: "control",
      description: "Control the browser remotely from your terminal",
    },
  ],
};

export default completionSpec;
