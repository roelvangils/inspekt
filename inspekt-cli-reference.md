# Inspekt CLI Reference

Complete reference for all Inspekt CLI commands, generated from `--help` output.

**Generated**: 2025-12-16 19:18:18

---


===========
# OUTPUT FOR: inspekt --help

Usage: inspekt [OPTIONS] COMMAND [ARGS]...

  Inspekt - Browser automation and inspection from the command line.

Options:
  --version      Show the version and exit.
  -v, --verbose  Enable verbose output (timing, requests, state changes)
  --help         Show this message and exit.

Commands:
  ask           Ask a question about the current page using AI.
  autocomplete  Check autocomplete attributes on form fields per WCAG 2.1...
  axe           Run axe-core accessibility audit on the current page.
  back          Go back to the previous page in browser history.
  bottom        Scroll to the bottom of the page.
  click         Click on an element.
  completion    Shell tab completion setup.
  config        Open the configuration file in your default editor.
  console       Browser console message commands.
  control       Control the browser remotely from your terminal.
  cookies       [DEPRECATED] Manage browser cookies (use 'inspekt storage...
  describe      Generate an AI-powered description of the page for screen...
  do            Find and execute actionable elements matching a natural...
  domain        Manage allowed domains for browser automation.
  double-click  Double-click on an element.
  download      Find and download files from the current page.
  eval          Execute JavaScript code in the active browser tab.
  exec          Execute JavaScript from a file.
  forward       Go forward to the next page in browser history.
  index         Index the current page with full semantic structure and...
  info          Page information and analysis.
  inspect       Select an element and show its details.
  inspected     Get information about the currently inspected element.
  links         Extract all links from the current page.
  log           Evaluate an expression and log the result.
  mcp           Manage the MCP server for AI assistant integration.
  md-link       Get Markdown link for the current page.
  network       Show network requests from the current page.
  open          Navigate to a URL.
  outline       Display the page's heading structure as a nested outline.
  pagedown      Scroll down one page (one viewport height).
  pageup        Scroll up one page (one viewport height).
  paste         Paste text instantly into the browser.
  plugin        Manage custom JavaScript plugins (bookmarklets).
  queue         Manage the request queue.
  record        Record browser interactions to a YAML file.
  reload        Reload the current page.
  repl          Start an interactive REPL session.
  replay        Replay a recorded browser interaction session.
  restart       Restart bridge and API servers.
  right-click   Right-click (context menu) on an element.
  robots        Fetch and parse robots.txt for the current page.
  save          Save the current page as a single HTML file.
  screenshot    Capture screenshots of elements, viewport, or full page.
  selected      [DEPRECATED] Get the current text selection in the browser.
  selection     Get the current text selection in the browser.
  send          [DEPRECATED] Send text to the browser by typing it...
  setup         Interactive setup wizard for new users.
  start         Start Inspekt servers (bridge + API) in daemon mode.
  status        Check status of all Inspekt servers.
  stop          Stop Inspekt servers.
  storage       Manage browser storage (cookies, localStorage,...
  summarize     Summarize the current article using AI.
  top           Scroll to the top of the page.
  type          Type text character by character into the browser.
  userscript    Display the userscript that needs to be installed in your...
  validate      Validate a recording file before replay.
  vm            Manage the Inspekt Browser VM.
  wait          Wait for an element to appear, be visible, hidden, or...
  watch         Watch browser events in real-time.
  yolo          YOLO mode - bypass ALL restrictions for 1 hour.

Commands:

  ask
    Ask a question about the current page using AI.
      --debug  Show the full prompt instead of calling AI
      --no-cache  Force re-index instead of using cache

  autocomplete
    Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5.
      --threshold  Minimum confidence (0-1) to consider autocomplete required
      (default: 0.5) [default: 0.5]
      --include-hidden  Include hidden input fields in analysis
      --include-disabled  Include disabled input fields in analysis
      --json  Output results as JSON
      --timeout  Execution timeout in seconds (default: 30) [default: 30.0]

  axe
    Run axe-core accessibility audit on the current page.
      --level  WCAG conformance level to test (default: 2aa) [default: 2aa]
      --rule  Check specific accessibility rule by ID (e.g., 'color-contrast',
      'link-name')
      --list-rules  List all available axe-core rules and exit
      --tags  Additional comma-separated tags (e.g., 'best-
      practice,experimental')
      --include-passes  Include passing checks in output
      --include-incomplete  Include incomplete checks (require manual review)
      --json  Output full results as JSON
      --timeout  Timeout in seconds (default: 30) [default: 30.0]
      --no-select  Disable auto-selection of element when single violation is
      found (only applies to --rule checks)
      --scoped  Scope tests to specific elements. Use 'inspected' for the
      currently inspected element, or provide CSS selectors (comma-separated)
      --exclude  Exclude elements from testing. Can be comma-separated
      selectors or multiple --exclude flags
      --require-panel-selection  Require element to be selected via Inspekt
      panel (not DevTools). Only valid with --scoped inspected
      --show-badges  Show numbered severity badges on violating elements
      (default: from config)
      --interactive  Make badges clickable with detailed popover information
      (requires --show-badges)
      --dev-css  Load CSS from local server (http://localhost:5500) for live
      editing. Use with VS Code Live Server.
      --persistent  Monitor and re-run audit on each page navigation (press
      Ctrl+C to stop). CLI only.
      --disable-rule  Disable specific rules by ID. Supports comma-separated
      values.
      --enable-rule  Run ONLY these rules (all others disabled). Supports
      comma-separated values.

  back
    Go back to the previous page in browser history.

  bottom
    Scroll to the bottom of the page.

  click
    Click on an element.

  completion
    Shell tab completion setup.

  config
    Open the configuration file in your default editor.

  console
    Browser console message commands.

  control
    Control the browser remotely from your terminal.

  cookies
    [DEPRECATED] Manage browser cookies (use 'inspekt storage --cookies').

  describe
    Generate an AI-powered description of the page for screen reader users.
      --language, --lang  Language for AI output (overrides config)
      --debug  Show the full prompt instead of calling AI
      --force-refresh  Force refresh, bypass cache

  do
    Find and execute actionable elements matching a natural language
    instruction.
      --debug  Show the full prompt instead of calling AI
      --no-execute  Show matches but don't execute any actions
      --force-ai  Force AI matching, bypass cache and literal matching

  domain
    Manage allowed domains for browser automation.

  double-click
    Double-click on an element.

  doubleclick
    Alias for double-click command.

  download
    Find and download files from the current page.
      -o, --output  Output directory (default: ~/Downloads/<domain>)
      --list  Only list files without downloading
      --json  Output as JSON (requires --list)
      -t, --timeout  Timeout in seconds (default: 30) [default: 30.0]
      --open  Open downloaded file in default application

  end
    Alias for 'bottom' command.

  eval
    Execute JavaScript code in the active browser tab.
      -f, --file  Execute code from file
      -t, --timeout  Timeout in seconds (default: 10) [default: 10.0]
      --format  Output format [default: auto]
      --url  Also print page URL
      --title  Also print page title
      --no-console  Don't show console output

  exec
    Execute JavaScript from a file.
      -t, --timeout  Timeout in seconds [default: 10.0]
      --format  Output format [default: auto]

  forward
    Go forward to the next page in browser history.

  home
    Alias for 'top' command.

  index
    Index the current page with full semantic structure and accessible names.
      --no-cache  Don't save to cache
      --output, -o  Save to specific file instead of cache

  info
    Page information and analysis.
      --json  Output as JSON

  inspect
    Select an element and show its details.

  inspected
    Get information about the currently inspected element.
      --json  Output as JSON

  links
    Extract all links from the current page.
      --only-internal  Show only internal links (same domain)
      --only-external  Show only external links (different domain)
      --alphabetically  Sort links alphabetically
      --only-urls  Show only URLs without anchor text
      --json  Output as JSON with detailed link information
      --enrich-external  Fetch additional metadata for external links (MIME
      type, file size, page title, language, HTTP status)

  log
    Evaluate an expression and log the result.
      -t, --timeout  Timeout in seconds (default: 10) [default: 10.0]

  mcp
    Manage the MCP server for AI assistant integration.

  md-link
    Get Markdown link for the current page.
      --json  Output as JSON

  network
    Show network requests from the current page.
      --json  Output as JSON
      --sort  Sort by field (default: start time) [default: start]
      --domain  Show domain column
      --external  Show only external requests
      --limit, -n  Limit number of results

  next
    Alias for 'forward' command.

  open
    Navigate to a URL.
      --wait  Wait for page to finish loading
      --timeout, -t  Timeout in seconds when using --wait (default: 30)
      [default: 30]

  outline
    Display the page's heading structure as a nested outline.
      --json  Output as JSON
      --truncate  Truncate headings to specified number of characters

  pagedown
    Scroll down one page (one viewport height).

  pageup
    Scroll up one page (one viewport height).

  paste
    Paste text instantly into the browser.
      --selector, -s  CSS selector to focus before pasting
      --clear  Clear existing text before pasting (default: true)

  pgdown
    Alias for 'pagedown' command.

  pgup
    Alias for 'pageup' command.

  plugin
    Manage custom JavaScript plugins (bookmarklets).

  previous
    Alias for 'back' command.

  queue
    Manage the request queue.

  record
    Record browser interactions to a YAML file.
      -o, --output  Output filename (auto-generated if not specified)
      --include-hover  Record hover events on interactive elements
      --mask-passwords  Mask password input values in recording
      --min-hover-duration  Minimum hover duration in ms to record (default:
      200) [default: 200]
      --replay  Automatically replay the recording after saving to verify it
      works
      --open  Open the recording in default application after saving
      --edit, -e  Deprecated: use --open instead
      --no-audio  Disable audio feedback during replay (requires --replay)
      --no-visual  Disable visual feedback during replay (requires --replay)
      --no-feedback  Disable both audio and visual feedback during replay
      (requires --replay)
      --interactive, -i  Step through replay manually (requires --replay)
      --capture-state  Capture cookies, localStorage, and scroll position for
      replay
      --storage-keys  Comma-separated list of localStorage/sessionStorage keys
      to capture
      --checksum  Generate DOM structure checksum for state verification
      --synthetic-dialogs  Use non-blocking HTML overlays for
      alert/confirm/prompt (for automation)
      --match-viewport  Mark viewport size as a requirement for faithful
      replay
      --match-zoom-level  Mark zoom level as a requirement for faithful replay
      --force, -f  Override existing file without prompting
      --viewport  Resize browser to specific viewport before recording (e.g.,
      1024x768)

  refresh
    Reload the current page (alias for 'reload').
      --hard  Hard reload (bypass cache)

  reload
    Reload the current page.
      --hard  Hard reload (bypass cache)

  repl
    Start an interactive REPL session.

  replay
    Replay a recorded browser interaction session.
      --speed  Playback speed multiplier (e.g., 2.0 for 2x speed, 0.5 for half
      speed) [default: 1.0]
      --slow  Half speed (0.5x) - same as --speed 0.5
      --very-slow  Quarter speed (0.25x) - same as --speed 0.25
      --instant  No delays between steps - fastest playback
      --step-delay  Delay between steps in milliseconds (default: 0, instant)
      [default: 0]
      --dry-run  Show steps without executing them
      --start-step  Start from step number (1-indexed) [default: 1]
      --end-step  End at step number (1-indexed, inclusive)
      --skip-hover  Skip all hover actions
      --skip  Skip specific action types (can be used multiple times)
      --pause-on-fail  Pause and wait for Enter after each failure
      --verbose, -v  Show detailed output for each step
      --no-visual  Disable visual indicators (circle at target, typing
      indicator)
      --no-audio  Disable synthesized audio cues for actions
      --no-feedback  Disable both visual and audio feedback
      --lock  Lock input during replay (hide cursor, ignore
      keyboard/mouse/scroll)
      --restore-viewport  [DEPRECATED] Use --match-viewport instead
      --interactive, -i  Step through replay manually (Enter=next, Space=skip,
      Escape=cancel)
      --stop-on-error, -e  Stop replay on first failure (assertion or
      execution error)
      --skip-tests, -T  Skip assertion checks (run actions without evaluating
      expect conditions)
      --restore-state  Restore all captured state (cookies, localStorage,
      sessionStorage)
      --restore-cookies  Restore cookies from recording state
      --restore-storage  Restore localStorage/sessionStorage from recording
      state
      --verify-checksum  Verify DOM structure checksum matches recording
      --strict-preconditions  Halt replay if preconditions are not met
      (default: warn only)
      --strict-checksum  Halt replay if checksum does not match (default: warn
      only)
      --progress, -p  Show compact progress bar instead of step-by-step output
      --skip-validation  Skip preflight validation checks
      --video  Record replay to video file (MP4/WebM). Use filename or --video
      for auto-naming.
      --fps  Video frame rate (5-30, uses config default: 10)
      --open  Open video file in default application after creation
      --include-effects  Include audio effects in video (click sounds, etc.)
      --match-viewport  Attempt to resize browser to match recorded viewport
      dimensions
      --match-zoom-level  Attempt to set browser zoom to match recorded zoom
      level

  restart
    Restart bridge and API servers.
      --no-update-check  Skip axe-core update check
      --api-port  API server port (default: 8000) [default: 8000]
      --bridge-port  Bridge server port (default: 8765) [default: 8765]
      --host  Host to bind to (default: 127.0.0.1) [default: 127.0.0.1]
      --docs  Start local MkDocs documentation server
      --docs-port  MkDocs server port (default: 8008) [default: 8008]

  right-click
    Right-click (context menu) on an element.

  rightclick
    Alias for right-click command.

  robots
    Fetch and parse robots.txt for the current page.
      --json  Output as JSON
      --validate  Show detailed validation errors and warnings
      --url  Specify URL to inspect (overrides current page)

  save
    Save the current page as a single HTML file.
      --output, -o  Output file path (default: auto-generated from title)
      --dir, -d  Output directory (default: current directory)
      --no-images  Skip embedding images (faster, smaller file)
      --remote-images  Keep images as remote URLs instead of embedding
      (requires internet to view)
      --no-styles  Skip removing unused styles (keep all CSS)
      --include-scripts  Include JavaScript in saved page (disabled by
      default)
      --include-frames  Include iframe content (disabled by default)
      --compress  Compress HTML output (remove extra whitespace)
      --raw  Save raw page without processing (useful for debugging)
      --optimize  Optimize for smaller file size (removes unused styles/fonts,
      recommended for large pages)
      --quiet, -q  Suppress progress output
      --json  Output result as JSON (for scripting)
      --open  Open saved file in default application

  screenshot
    Capture screenshots of elements, viewport, or full page.

  selected
    [DEPRECATED] Get the current text selection in the browser.
      --raw  Output only the text without formatting
      --json  Output as JSON

  selection
    Get the current text selection in the browser.
      --json  Output as JSON with all formats

  send
    [DEPRECATED] Send text to the browser by typing it character by character.
      --selector, -s  CSS selector to focus before typing

  setup
    Interactive setup wizard for new users.
      --install-completion  Automatically install shell completion

  start
    Start Inspekt servers (bridge + API) in daemon mode.
      --bridge-only  Start only the bridge server
      --api-only  Start only the API server
      --foreground  Run in foreground (for debugging)
      --no-update-check  Skip axe-core update check
      --api-port  API server port (default: 8000) [default: 8000]
      --bridge-port  Bridge server port (default: 8765) [default: 8765]
      --host  Host to bind to (default: 127.0.0.1) [default: 127.0.0.1]
      --docs  Start local MkDocs documentation server
      --docs-port  MkDocs server port (default: 8008) [default: 8008]

  status
    Check status of all Inspekt servers.
      --json  Output as JSON

  stop
    Stop Inspekt servers.
      --bridge-only  Stop only the bridge server
      --api-only  Stop only the API server

  storage
    Manage browser storage (cookies, localStorage, sessionStorage).

  summarize
    Summarize the current article using AI.
      --format  Output format (summary or full article) [default: summary]
      --language, --lang  Language for AI output (overrides config)
      --debug  Show the full prompt instead of calling AI
      --force-refresh  Force refresh, bypass cache

  top
    Scroll to the top of the page.

  type
    Type text character by character into the browser.
      --selector, -s  CSS selector to focus before typing
      --speed  Typing speed in characters per second (default: fastest, 0:
      human-like)
      --clear  Clear existing text before typing (default: true)

  userscript
    Display the userscript that needs to be installed in your browser.

  validate
    Validate a recording file before replay.
      --strict  Treat warnings as errors (exit with error code if warnings
      found)
      --json  Output results as JSON for tooling integration

  vm
    Manage the Inspekt Browser VM.

  wait
    Wait for an element to appear, be visible, hidden, or contain text.
      --timeout, -t  Timeout in seconds (default: 30) [default: 30]
      --visible  Wait for element to be visible
      --hidden  Wait for element to be hidden
      --text  Wait for element to contain specific text

  watch
    Watch browser events in real-time.

  yolo
    YOLO mode - bypass ALL restrictions for 1 hour.
      --disable, -d  Disable yolo mode
      --status, -s  Check yolo mode status

===========
# OUTPUT FOR: inspekt ask --help

Usage: inspekt ask [OPTIONS] QUESTION

  Ask a question about the current page using AI.

  By default, this command uses the cached index of the current page (created
  by 'inspekt index'). Use --no-cache to force re-indexing.

  The AI has access to the full semantic structure, all text content,
  interactive elements, accessible names, and vision AI descriptions.

  Examples:     inspekt index                              # First, index the
  page     inspekt ask "What is this page about?"     # Uses cache     inspekt
  ask "What's the nutriscore?"       # Uses cache     inspekt ask "What's in
  the image?"         # Vision description from cache     inspekt ask
  "Summarize" --no-cache         # Force re-index

Options:
  --debug     Show the full prompt instead of calling AI
  --no-cache  Force re-index instead of using cache
  --help      Show this message and exit.

===========
# OUTPUT FOR: inspekt autocomplete --help

Usage: inspekt autocomplete [OPTIONS]

  Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5.

  Analyzes all form fields (input, textarea, select) on the current page and
  predicts appropriate autocomplete attributes using multi-language
  heuristics.

  The check uses 7 weighted matching strategies: - Label text (weight: 5) -
  highest reliability - Placeholder text (weight: 4) - Name attribute (weight:
  2) - ID attribute (weight: 2) - Field type (weight: 1) - Input type (weight:
  1) - Form type (weight: 1) - login vs signup detection

  Supports multi-language keyword matching (English, German, Dutch) with fuzzy
  substring matching for robust field identification.

  Examples:

      # Basic check (default 0.5 threshold)     inspekt autocomplete

      # Strict check (higher confidence threshold)     inspekt autocomplete
      --threshold 0.7

      # Include hidden and disabled fields     inspekt autocomplete --include-
      hidden --include-disabled

      # JSON output for programmatic use     inspekt autocomplete --json

Options:
  --threshold FLOAT   Minimum confidence (0-1) to consider autocomplete
                      required (default: 0.5)
  --include-hidden    Include hidden input fields in analysis
  --include-disabled  Include disabled input fields in analysis
  --json              Output results as JSON
  --timeout FLOAT     Execution timeout in seconds (default: 30)
  --help              Show this message and exit.

===========
# OUTPUT FOR: inspekt axe --help

Usage: inspekt axe [OPTIONS]

  Run axe-core accessibility audit on the current page.

  Analyzes the page for WCAG conformance violations using the industry-
  standard axe-core library. By default, tests against WCAG 2 Level AA
  standards.

  The audit runs in your current browser tab, testing the actual rendered page
  state including any JavaScript-generated content and your authentication
  state.

  Violations are marked with numbered badges on the page by default. Use
  --interactive to make badges clickable, revealing detailed violation
  information in accessible popovers with fix suggestions, code snippets, and
  documentation.

  When checking a single rule (--rule) with exactly one violation, the element
  is automatically selected and highlighted in the browser. Use --no-select to
  disable this behavior.

  Examples:     # Basic WCAG audits     inspekt axe
  # WCAG 2.1 Level AA audit     inspekt axe --level 21aa
  # WCAG 2.1 Level AA audit     inspekt axe --rule color-contrast
  # Check single rule

      # Interactive badges     inspekt axe --interactive
      # Clickable badges with popovers     inspekt axe --no-show-badges
      # Disable badges

      # Scoped testing     inspekt axe --scoped inspected                 #
      Test only inspected element     inspekt axe --scoped "main"
      # Test only main element     inspekt axe --scoped "main,nav,footer"
      # Test multiple regions     inspekt axe --scoped inspected --require-
      panel-selection  # Require Inspekt panel

      # Excluding elements (CSS selectors)     inspekt axe --exclude
      "header,footer"          # Exclude header and footer     inspekt axe
      --exclude header --exclude footer  # Multiple --exclude flags
      inspekt axe --scoped "main" --exclude ".ad"    # Combined scoping and
      exclusion

      # Disabling rules (exclude specific rules)     inspekt axe --disable-
      rule color-contrast           # Ignore one rule     inspekt axe
      --disable-rule color-contrast,label     # Comma-separated     inspekt
      axe --disable-rule color-contrast --disable-rule label  # Multiple flags

      # Enabling rules (run ONLY specific rules, all others disabled)
      inspekt axe --enable-rule color-contrast            # Check only
      contrast     inspekt axe --enable-rule color-contrast,label      # Check
      only these two     inspekt axe --enable-rule link-name,button-name     #
      Focus on naming rules

      # Other options     inspekt axe --list-rules                       #
      List all available rules     inspekt axe --json > audit-results.json
      # JSON output     inspekt axe --rule color-contrast --no-select  #
      Disable auto-selection

      # Persistent monitoring     inspekt axe --persistent
      # Monitor across page navigations     inspekt axe --persistent
      --interactive         # With clickable badges

Options:
  --level [2a|2aa|2aaa|21a|21aa|22aa]
                                  WCAG conformance level to test (default:
                                  2aa)
  --rule TEXT                     Check specific accessibility rule by ID
                                  (e.g., 'color-contrast', 'link-name')
  --list-rules                    List all available axe-core rules and exit
  --tags TEXT                     Additional comma-separated tags (e.g.,
                                  'best-practice,experimental')
  --include-passes                Include passing checks in output
  --include-incomplete            Include incomplete checks (require manual
                                  review)
  --json                          Output full results as JSON
  --timeout FLOAT                 Timeout in seconds (default: 30)
  --no-select                     Disable auto-selection of element when
                                  single violation is found (only applies to
                                  --rule checks)
  --scoped TEXT                   Scope tests to specific elements. Use
                                  'inspected' for the currently inspected
                                  element, or provide CSS selectors (comma-
                                  separated)
  --exclude TEXT                  Exclude elements from testing. Can be comma-
                                  separated selectors or multiple --exclude
                                  flags
  --require-panel-selection       Require element to be selected via Inspekt
                                  panel (not DevTools). Only valid with
                                  --scoped inspected
  --show-badges / --no-show-badges
                                  Show numbered severity badges on violating
                                  elements (default: from config)
  --interactive                   Make badges clickable with detailed popover
                                  information (requires --show-badges)
  --dev-css                       Load CSS from local server
                                  (http://localhost:5500) for live editing.
                                  Use with VS Code Live Server.
  --persistent                    Monitor and re-run audit on each page
                                  navigation (press Ctrl+C to stop). CLI only.
  --disable-rule RULE_ID          Disable specific rules by ID. Supports
                                  comma-separated values.
  --enable-rule RULE_ID           Run ONLY these rules (all others disabled).
                                  Supports comma-separated values.
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt back --help

Usage: inspekt back [OPTIONS]

  Go back to the previous page in browser history.

  Example:     inspekt back

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt bottom --help

Usage: inspekt bottom [OPTIONS]

  Scroll to the bottom of the page.

  Example:     inspekt bottom

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt click --help

Usage: inspekt click [OPTIONS] [SELECTOR]

  Click on an element.

  Uses the stored element from 'inspekt inspect' by default, or specify a
  selector.

  Examples:     # Click on stored element:     inspekt inspect "button#submit"
  inspekt click

      # Click directly on element:     inspekt click "button#submit"
      inspekt click ".primary-button"

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt completion --help

Usage: inspekt completion [OPTIONS] COMMAND [ARGS]...

  Shell tab completion setup.

  Generate completion scripts or install them automatically.

  Examples:
      inspekt completion install    # Auto-detect shell and install
      inspekt completion status     # Check if installed
      inspekt completion bash       # Output bash script

Options:
  --help  Show this message and exit.

Commands:
  bash       Output bash completion script.
  fish       Output fish completion script.
  install    Install shell completion automatically.
  status     Check if shell completion is installed.
  uninstall  Remove shell completion from config file.
  zsh        Output zsh completion script.

===========
# OUTPUT FOR: inspekt config --help

Usage: inspekt config [OPTIONS]

  Open the configuration file in your default editor.

  If no config file exists, creates one at ~/.config/inspekt.json with default
  settings.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt console --help

Usage: inspekt console [OPTIONS] COMMAND [ARGS]...

  Browser console message commands.

Options:
  --help  Show this message and exit.

Commands:
  clear  Clear the console message buffer.
  list   Show captured console messages from the browser.
  log    Evaluate an expression and log the result.

===========
# OUTPUT FOR: inspekt control --help

Usage: inspekt control [OPTIONS]

  Control the browser remotely from your terminal.

  All keyboard input from your terminal will be sent directly to the browser,
  allowing you to navigate, type, and interact with the page remotely.

  Supports: - Regular text input - Special keys (arrows, Enter, Tab, Escape,
  etc.) - Modifier keys (Ctrl, Alt, Shift, Cmd)

  Press Ctrl+D to exit control mode.

  Example:     inspekt control

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt cookies --help

Usage: inspekt cookies [OPTIONS] COMMAND [ARGS]...

  [DEPRECATED] Manage browser cookies (use 'inspekt storage --cookies').

Options:
  --help  Show this message and exit.

Commands:
  clear   Clear all cookies for the current page.
  delete  Delete a specific cookie.
  get     Get the value of a specific cookie.
  list    List all cookies for the current page.
  set     Set a cookie.

===========
# OUTPUT FOR: inspekt describe --help

Usage: inspekt describe [OPTIONS]

  Generate an AI-powered description of the page for screen reader users.

  Extracts page structure (landmarks, headings, links, images, forms) and uses
  AI to create a concise, natural description perfect for blind users to
  understand what the page offers at a glance.

  Examples:     inspekt describe

Options:
  --language, --lang TEXT  Language for AI output (overrides config)
  --debug                  Show the full prompt instead of calling AI
  --force-refresh          Force refresh, bypass cache
  --help                   Show this message and exit.

===========
# OUTPUT FOR: inspekt do --help

Usage: inspekt do [OPTIONS] INSTRUCTION

  Find and execute actionable elements matching a natural language
  instruction.

  This command analyzes the page for clickable elements (links, buttons,
  forms) and uses AI to match them with your instruction. It adds temporary
  classes to actionable elements and returns a ranked list of matches with
  probability scores.

  If the top match has a probability >= 75%, it automatically executes the
  action. For lower confidence matches, it asks for confirmation before
  executing.

  The element is briefly highlighted in green before clicking, and you'll see
  confirmation of what was clicked.

  Examples:     inspekt do "Go to the homepage"          # Auto-executes if
  high confidence     inspekt do "Click the login button"      # Asks for
  confirmation if lower confidence     inspekt do "Search for products"
  inspekt do "Submit form" --no-execute    # Just show matches, don't execute

Options:
  --debug       Show the full prompt instead of calling AI
  --no-execute  Show matches but don't execute any actions
  --force-ai    Force AI matching, bypass cache and literal matching
  --help        Show this message and exit.

===========
# OUTPUT FOR: inspekt domain --help

Usage: inspekt domain [OPTIONS] COMMAND [ARGS]...

  Manage allowed domains for browser automation.

Options:
  --help  Show this message and exit.

Commands:
  add     Add a domain to the allowed list.
  bypass  Set temporary bypass for all domains.
  csp     Manage CSP (Content Security Policy) bypass for strict sites.
  list    List all allowed domains.
  remove  Remove a domain from the allowed list.

===========
# OUTPUT FOR: inspekt double-click --help

Usage: inspekt double-click [OPTIONS] [SELECTOR]

  Double-click on an element.

  Uses the stored element from 'inspekt inspect' by default, or specify a
  selector.

  Examples:     inspekt double-click "div.item"     inspekt inspect "div.item"
  inspekt double-click

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt download --help

Usage: inspekt download [OPTIONS]

  Find and download files from the current page.

  Discovers images, PDFs, videos, audio files, documents and archives. Uses
  interactive selection with gum choose.

  Examples:

      inspekt download

      inspekt download --output ~/Downloads

      inspekt download --list

Options:
  -o, --output PATH    Output directory (default: ~/Downloads/<domain>)
  --list               Only list files without downloading
  --json               Output as JSON (requires --list)
  -t, --timeout FLOAT  Timeout in seconds (default: 30)
  --open               Open downloaded file in default application
  --help               Show this message and exit.

===========
# OUTPUT FOR: inspekt eval --help

Usage: inspekt eval [OPTIONS] [CODE]

  Execute JavaScript code in the active browser tab.

  Console output (console.log, console.error, etc.) is shown by default. Use
  --no-console to hide it.

  Examples:

      inspekt eval "document.title"

      inspekt eval "console.log(5+5)"

      inspekt eval --file script.js

      echo "console.log('test')" | inspekt eval

Options:
  -f, --file PATH           Execute code from file
  -t, --timeout FLOAT       Timeout in seconds (default: 10)
  --format [auto|json|raw]  Output format
  --url                     Also print page URL
  --title                   Also print page title
  --no-console              Don't show console output
  --help                    Show this message and exit.

===========
# OUTPUT FOR: inspekt exec --help

Usage: inspekt exec [OPTIONS] FILEPATH

  Execute JavaScript from a file.

  Example:

      inspekt exec script.js

Options:
  -t, --timeout FLOAT       Timeout in seconds
  --format [auto|json|raw]  Output format
  --help                    Show this message and exit.

===========
# OUTPUT FOR: inspekt forward --help

Usage: inspekt forward [OPTIONS]

  Go forward to the next page in browser history.

  Example:     inspekt forward

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt index --help

Usage: inspekt index [OPTIONS]

  Index the current page with full semantic structure and accessible names.

  Creates a comprehensive Markdown representation of the page including: -
  Page landmarks and semantic structure - All headings with hierarchy - Main
  content paragraphs - Lists and their items - Interactive elements (links,
  buttons, form controls) with accessible names - Images with alt text

  The indexed page is saved to cache and can be used by the 'inspekt ask'
  command to answer questions about the page content.

  Examples:     inspekt index                    # Index and cache current
  page     inspekt index --no-cache         # Index but don't cache
  inspekt index -o page.md         # Save to specific file

Options:
  --no-cache         Don't save to cache
  -o, --output PATH  Save to specific file instead of cache
  --help             Show this message and exit.

===========
# OUTPUT FOR: inspekt info --help

Usage: inspekt info [OPTIONS] COMMAND [ARGS]...

  Page information and analysis.

  Without a subcommand, shows a brief summary. Use subcommands for detailed
  info:

    inspekt info              Brief summary with browser/device info
    inspekt info all          Complete output (all categories)
    inspekt info performance  Load times and Core Web Vitals
    inspekt info meta         Meta tags, Open Graph, Twitter Card
    inspekt info seo          SEO analysis including robots.txt
    inspekt info security     HTTPS status, security headers
    inspekt info accessibility A11y analysis, headings, landmarks
    inspekt info resources    Scripts, stylesheets, media, fonts
    inspekt info storage      Cookies, localStorage, sessionStorage
    inspekt info tech         Detected frameworks and technologies
    inspekt info domain       IP, SSL cert, WHOIS (server-side)
    inspekt info layout       Viewport, document size, scroll

Options:
  --json  Output as JSON
  --help  Show this message and exit.

Commands:
  accessibility  Accessibility analysis: landmarks, headings, forms, ARIA.
  all            Show all information categories.
  domain         IP address, geolocation, SSL certificate, WHOIS data.
  layout         Viewport, document size, scroll position.
  meta           Meta tags, Open Graph, Twitter Card, language, encoding.
  performance    Performance metrics and Core Web Vitals.
  resources      Scripts, stylesheets, images, media, fonts, network.
  security       HTTPS status, security headers, response headers.
  seo            SEO analysis including robots.txt.
  storage        Cookies, localStorage, sessionStorage, service worker.
  tech           Detected frameworks, CMS, analytics, and technologies.

===========
# OUTPUT FOR: inspekt inspect --help

Usage: inspekt inspect [OPTIONS] [SELECTOR]

  Select an element and show its details.

  If no selector is provided, shows details of the currently selected element.

  Examples:     inspekt inspect "h1"              # Select and show details
  inspekt inspect "#header"     inspekt inspect ".main-content"     inspekt
  inspect                   # Show currently selected element

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt inspected --help

Usage: inspekt inspected [OPTIONS]

  Get information about the currently inspected element.

  Shows details about the element from DevTools inspection or from 'inspekt
  inspect'.

  To capture element from DevTools:     1. Right-click element → Inspect
  2. In DevTools Console: inspektStore()     3. Run: inspekt inspected

  Or select programmatically:     inspekt inspect "h1"     inspekt inspected

Options:
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt links --help

Usage: inspekt links [OPTIONS]

  Extract all links from the current page.

  By default, shows all links with their anchor text. Use filters to show only
  internal or external links.

  Examples:     inspekt links                           # All links with
  anchor text     inspekt links --only-internal           # Only links on same
  domain     inspekt links --only-external           # Only links to other
  domains     inspekt links --alphabetically          # Sort alphabetically
  inspekt links --only-urls               # Show only URLs     inspekt links
  --only-external --only-urls  # External URLs only     inspekt links
  --enrich-external         # Add metadata for external links

Options:
  --only-internal    Show only internal links (same domain)
  --only-external    Show only external links (different domain)
  --alphabetically   Sort links alphabetically
  --only-urls        Show only URLs without anchor text
  --json             Output as JSON with detailed link information
  --enrich-external  Fetch additional metadata for external links (MIME type,
                     file size, page title, language, HTTP status)
  --help             Show this message and exit.

===========
# OUTPUT FOR: inspekt log --help

Usage: inspekt log [OPTIONS] EXPRESSION

  Evaluate an expression and log the result.

  Shorthand for: inspekt eval "console.log(expression)"

  Examples:     inspekt log "5+5"     inspekt log "document.title"     inspekt
  log "[1,2,3].map(x => x*2)"

Options:
  -t, --timeout FLOAT  Timeout in seconds (default: 10)
  --help               Show this message and exit.

===========
# OUTPUT FOR: inspekt mcp --help

Usage: inspekt mcp [OPTIONS] COMMAND [ARGS]...

  Manage the MCP server for AI assistant integration.

Options:
  --help  Show this message and exit.

Commands:
  describe  Show detailed documentation for a specific MCP tool.
  info      Show information about available MCP tools and resources.
  start     Start the MCP server in stdio mode.
  test      Test MCP server connectivity and basic functionality.

===========
# OUTPUT FOR: inspekt md-link --help

Usage: inspekt md-link [OPTIONS]

  Get Markdown link for the current page.

  Returns [title](url) format with cleaned page title. Strips website name
  from title (splits on " |", " -", " –").

  Examples:

      inspekt md-link

      inspekt md-link --json

Options:
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network --help

Usage: inspekt network [OPTIONS] COMMAND [ARGS]...

  Show network requests from the current page.

  Automatically detects if Chrome DevTools is open. When DevTools is open,
  shows enhanced data including HTTP status codes (200, 404, 500, etc.) and
  headers. Otherwise falls back to the Performance API.

  Use subcommands to filter by resource type:     inspekt network script
  # Only scripts     inspekt network stylesheet  # Only CSS     inspekt
  network fetch       # Only fetch/XHR     inspekt network image       # Only
  images     inspekt network font        # Only fonts     inspekt network har
  # Force HAR mode (DevTools required)

  Examples:     inspekt network                    # All requests (auto-
  detects DevTools)     inspekt network --json             # Output as JSON
  inspekt network --sort=time        # Sort by duration (slowest first)
  inspekt network --sort=size        # Sort by size (largest first)
  inspekt network --external         # Only external requests     inspekt
  network --domain           # Show domain column     inspekt network -n 20
  # Limit to 20 results

Options:
  --json                          Output as JSON
  --sort [start|time|size|name|type]
                                  Sort by field (default: start time)
  --domain                        Show domain column
  --external                      Show only external requests
  -n, --limit INTEGER             Limit number of results
  --help                          Show this message and exit.

Commands:
  audio       Show only audio resources.
  css         Show only CSS resources (alias for stylesheet).
  document    Show only document/HTML resources.
  fetch       Show only fetch/XHR requests.
  font        Show only font resources.
  har         Get full network data from DevTools (HAR format).
  image       Show only image resources.
  script      Show only JavaScript resources.
  stylesheet  Show only CSS resources.
  svg         Show only SVG resources.
  video       Show only video resources.
  xhr         Show only XHR requests.

===========
# OUTPUT FOR: inspekt open --help

Usage: inspekt open [OPTIONS] URL

  Navigate to a URL.

  Examples:     # Navigate to a URL:     inspekt open "https://example.com"

      # Navigate and wait for page load:     inspekt open
      "https://example.com" --wait

      # Navigate with custom timeout:     inspekt open "https://example.com"
      --wait --timeout 60

Options:
  --wait                 Wait for page to finish loading
  -t, --timeout INTEGER  Timeout in seconds when using --wait (default: 30)
  --help                 Show this message and exit.

===========
# OUTPUT FOR: inspekt outline --help

Usage: inspekt outline [OPTIONS]

  Display the page's heading structure as a nested outline.

  Shows all headings (H1-H6 and ARIA headings) in a hierarchical view.
  Indicates missing levels (red), duplicates (yellow), and ARIA headings
  (gray).

  Examples:     inspekt outline     inspekt outline --json     inspekt outline
  --truncate 80

Options:
  --json              Output as JSON
  --truncate INTEGER  Truncate headings to specified number of characters
  --help              Show this message and exit.

===========
# OUTPUT FOR: inspekt pagedown --help

Usage: inspekt pagedown [OPTIONS]

  Scroll down one page (one viewport height).

  Example:     inspekt pagedown

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt pageup --help

Usage: inspekt pageup [OPTIONS]

  Scroll up one page (one viewport height).

  Example:     inspekt pageup

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt paste --help

Usage: inspekt paste [OPTIONS] TEXT

  Paste text instantly into the browser.

  Pastes text into the currently focused input field, or into a specific
  element if --selector is provided.

  By default, clears any existing text before pasting. This is equivalent to
  'inspekt type' with maximum speed.

  Examples:     # Paste (clears existing text):     inspekt paste "Hello
  World"

      # Paste without clearing:     inspekt paste "append this" --no-clear

      # Paste into specific element:     inspekt paste "test@example.com"
      --selector "input[type=email]"

Options:
  -s, --selector TEXT   CSS selector to focus before pasting
  --clear / --no-clear  Clear existing text before pasting (default: true)
  --help                Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin --help

Usage: inspekt plugin [OPTIONS] COMMAND [ARGS]...

  Manage custom JavaScript plugins (bookmarklets).

Options:
  --help  Show this message and exit.

Commands:
  add     Add a new plugin.
  export  Export plugins to JSON file.
  import  Import plugins from JSON file.
  list    List all plugins.
  remove  Remove a plugin.
  run     Execute a plugin in the browser.
  show    Display plugin details.
  unload  Unload/reverse a plugin's effects.

===========
# OUTPUT FOR: inspekt queue --help

Usage: inspekt queue [OPTIONS] COMMAND [ARGS]...

  Manage the request queue.

  View and manage pending requests in the bridge server queue. Use this to
  diagnose or fix stuck requests.

  Examples:     inspekt queue status    # View queue status     inspekt queue
  clear     # Clear all pending requests

Options:
  --help  Show this message and exit.

Commands:
  clear   Clear pending requests from the queue.
  status  Show queue status and pending requests.

===========
# OUTPUT FOR: inspekt record --help

Usage: inspekt record [OPTIONS] [FILENAME] COMMAND [ARGS]...

  Record browser interactions to a YAML file.

  Starts recording all user actions on the currently open browser page. Press
  Ctrl+C to stop recording and save the file.

  The recording can later be replayed with 'inspekt replay' and edited to add
  assertions for automated testing.

  Examples:
      inspekt record                    # Auto-generates filename
      inspekt record my-flow.yaml       # Record to specific file
      inspekt record -o login-flow.yaml # Same, using -o flag
      inspekt record --no-hover         # Skip hover events
      inspekt record --open             # Record and open in default app
      inspekt record --replay           # Record and replay to verify
      inspekt record --replay -i        # Record and step through replay
      inspekt record --open --replay    # Open, then replay to verify

Options:
  -o, --output TEXT               Output filename (auto-generated if not
                                  specified)
  --include-hover / --no-hover    Record hover events on interactive elements
  --mask-passwords / --no-mask-passwords
                                  Mask password input values in recording
  --min-hover-duration INTEGER    Minimum hover duration in ms to record
                                  (default: 200)
  --replay                        Automatically replay the recording after
                                  saving to verify it works
  --open                          Open the recording in default application
                                  after saving
  --no-audio                      Disable audio feedback during replay
                                  (requires --replay)
  --no-visual                     Disable visual feedback during replay
                                  (requires --replay)
  --no-feedback                   Disable both audio and visual feedback
                                  during replay (requires --replay)
  -i, --interactive               Step through replay manually (requires
                                  --replay)
  --capture-state                 Capture cookies, localStorage, and scroll
                                  position for replay
  --storage-keys TEXT             Comma-separated list of
                                  localStorage/sessionStorage keys to capture
  --checksum                      Generate DOM structure checksum for state
                                  verification
  --synthetic-dialogs             Use non-blocking HTML overlays for
                                  alert/confirm/prompt (for automation)
  --match-viewport                Mark viewport size as a requirement for
                                  faithful replay
  --match-zoom-level              Mark zoom level as a requirement for
                                  faithful replay
  -f, --force                     Override existing file without prompting
  --viewport TEXT                 Resize browser to specific viewport before
                                  recording (e.g., 1024x768)
  --help                          Show this message and exit.

Commands:
  delete    Delete a recording file.
  edit      Open a recording file in your default editor.
  list      List all saved recordings.
  show      Show details of a recording file.
  tidy      Tidy up a recording file.
  tutorial  Interactive tutorial for the record command.

===========
# OUTPUT FOR: inspekt reload --help

Usage: inspekt reload [OPTIONS]

  Reload the current page.

  Examples:     # Normal reload:     inspekt reload

      # Hard reload (bypass cache):     inspekt reload --hard

Options:
  --hard  Hard reload (bypass cache)
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt repl --help

Usage: inspekt repl [OPTIONS]

  Start an interactive REPL session.

  Execute JavaScript interactively. Console output is shown automatically.
  Type 'exit' or press Ctrl+D to quit.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt replay --help

Usage: inspekt replay [OPTIONS] [RECORDING_FILE]

  Replay a recorded browser interaction session.

  Executes all steps from a YAML recording file against the current browser.
  Reports all assertion failures at the end (continues on failure).

  Speed options:
      --slow        Half speed (0.5x)
      --very-slow   Quarter speed (0.25x)
      --instant     No delays between steps
      --speed N     Custom speed multiplier

  Filtering options:
      --skip-hover  Skip all hover actions
      --skip TYPE   Skip specific action types (hover, keypress, type, click)

  Interactive mode:
      --interactive, -i   Step through manually in the browser
                          Press Enter to execute, Space to skip, Escape to cancel

  Video recording:
      --video PATH    Record replay to video file (requires ffmpeg)
      --video         Auto-name video file based on recording
      --fps N         Custom frame rate (5-30, default: 10)

  Examples:
      inspekt replay                             # Replay most recent recording
      inspekt replay login-flow.yaml             # Replay at normal speed
      inspekt replay login-flow.yaml --slow      # Replay at half speed
      inspekt replay login-flow.yaml --instant   # Fast replay, no delays
      inspekt replay login-flow.yaml --skip-hover    # Skip hovers
      inspekt replay login-flow.yaml --dry-run   # Preview steps
      inspekt replay login-flow.yaml --pause-on-fail # Debug failures
      inspekt replay login-flow.yaml -i          # Interactive step-through
      inspekt replay login-flow.yaml --video     # Record to auto-named MP4
      inspekt replay login-flow.yaml --video=journey.mp4  # Custom filename
      inspekt replay login-flow.yaml --video --fps=15     # 15fps video
      inspekt replay login-flow.yaml --video --open       # Record and open video

Options:
  --speed FLOAT                   Playback speed multiplier (e.g., 2.0 for 2x
                                  speed, 0.5 for half speed)
  --slow                          Half speed (0.5x) - same as --speed 0.5
  --very-slow                     Quarter speed (0.25x) - same as --speed 0.25
  --instant                       No delays between steps - fastest playback
  --step-delay INTEGER            Delay between steps in milliseconds
                                  (default: 0, instant)
  --dry-run                       Show steps without executing them
  --start-step INTEGER            Start from step number (1-indexed)
  --end-step INTEGER              End at step number (1-indexed, inclusive)
  --skip-hover                    Skip all hover actions
  --skip [hover|keypress|type|click|navigate]
                                  Skip specific action types (can be used
                                  multiple times)
  --pause-on-fail                 Pause and wait for Enter after each failure
  -v, --verbose                   Show detailed output for each step
  --no-visual                     Disable visual indicators (circle at target,
                                  typing indicator)
  --no-audio                      Disable synthesized audio cues for actions
  --no-feedback                   Disable both visual and audio feedback
  --lock                          Lock input during replay (hide cursor,
                                  ignore keyboard/mouse/scroll)
  -i, --interactive               Step through replay manually (Enter=next,
                                  Space=skip, Escape=cancel)
  -e, --stop-on-error             Stop replay on first failure (assertion or
                                  execution error)
  -T, --skip-tests                Skip assertion checks (run actions without
                                  evaluating expect conditions)
  --restore-state                 Restore all captured state (cookies,
                                  localStorage, sessionStorage)
  --restore-cookies               Restore cookies from recording state
  --restore-storage               Restore localStorage/sessionStorage from
                                  recording state
  --verify-checksum               Verify DOM structure checksum matches
                                  recording
  --strict-preconditions          Halt replay if preconditions are not met
                                  (default: warn only)
  --strict-checksum               Halt replay if checksum does not match
                                  (default: warn only)
  -p, --progress                  Show compact progress bar instead of step-
                                  by-step output
  --skip-validation               Skip preflight validation checks
  --video PATH                    Record replay to video file (MP4/WebM). Use
                                  filename or --video for auto-naming.
  --fps INTEGER                   Video frame rate (5-30, uses config default:
                                  10)
  --open                          Open video file in default application after
                                  creation
  --include-effects / --no-effects
                                  Include audio effects in video (click
                                  sounds, etc.)
  --match-viewport                Attempt to resize browser to match recorded
                                  viewport dimensions
  --match-zoom-level              Attempt to set browser zoom to match
                                  recorded zoom level
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt restart --help

Usage: inspekt restart [OPTIONS]

  Restart bridge and API servers.

  This command stops any running servers, optionally checks for updates, then
  starts servers fresh in daemon mode. Use --docs to also start a local MkDocs
  documentation server.

  Examples:     inspekt restart                   # Restart servers
  inspekt restart --docs            # Include documentation server     inspekt
  restart --no-update-check # Skip update check     inspekt restart --api-port
  3000   # Use custom API port

Options:
  --no-update-check      Skip axe-core update check
  --api-port INTEGER     API server port (default: 8000)
  --bridge-port INTEGER  Bridge server port (default: 8765)
  --host TEXT            Host to bind to (default: 127.0.0.1)
  --docs                 Start local MkDocs documentation server
  --docs-port INTEGER    MkDocs server port (default: 8008)
  --help                 Show this message and exit.

===========
# OUTPUT FOR: inspekt right-click --help

Usage: inspekt right-click [OPTIONS] [SELECTOR]

  Right-click (context menu) on an element.

  Uses the stored element from 'inspekt inspect' by default, or specify a
  selector.

  Examples:     inspekt right-click "a.download-link"     inspekt inspect
  "a.download-link"     inspekt right-click

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt robots --help

Usage: inspekt robots [OPTIONS]

  Fetch and parse robots.txt for the current page.

  Retrieves the robots.txt file from the current page's origin, parses it
  according to RFC 9309, and displays the rules, sitemaps, and metadata.

  Examples:     inspekt robots     inspekt robots --json     inspekt robots
  --validate     inspekt robots --url https://example.com

Options:
  --json      Output as JSON
  --validate  Show detailed validation errors and warnings
  --url TEXT  Specify URL to inspect (overrides current page)
  --help      Show this message and exit.

===========
# OUTPUT FOR: inspekt save --help

Usage: inspekt save [OPTIONS]

  Save the current page as a single HTML file.

  Captures the current browser tab with all resources embedded inline using
  the SingleFile library. The saved page represents the CURRENT DOM STATE,
  including any JavaScript-rendered content.

  By default, pages are saved to {downloads}/{domain}/ where {downloads} is
  configured in config.json (default: ~/Downloads) and {domain} is extracted
  from the page URL (e.g. ~/Downloads/github.com/Page_Title.html).

  Features: - CSS stylesheets (inlined and deduplicated) - Images (converted
  to base64 data URIs) - Fonts (embedded from CSS) - Canvas elements
  (converted to images) - SVG graphics (fully preserved) - Web fonts
  (embedded)

  The saved file is a complete, self-contained HTML document that can be
  viewed offline in any browser.

  Examples:     inspekt save                          # Save to
  ~/Downloads/{domain}/     inspekt save -o mypage.html           # Save with
  custom name     inspekt save -d ~/archives            # Save to specific
  directory     inspekt save --remote-images          # Keep image URLs
  (smaller file, needs internet)     inspekt save --no-images              #
  Skip images entirely (fastest)     inspekt save --include-scripts        #
  Include JavaScript     inspekt save --compress               # Minimize file
  size

Options:
  -o, --output PATH    Output file path (default: auto-generated from title)
  -d, --dir DIRECTORY  Output directory (default: current directory)
  --no-images          Skip embedding images (faster, smaller file)
  --remote-images      Keep images as remote URLs instead of embedding
                       (requires internet to view)
  --no-styles          Skip removing unused styles (keep all CSS)
  --include-scripts    Include JavaScript in saved page (disabled by default)
  --include-frames     Include iframe content (disabled by default)
  --compress           Compress HTML output (remove extra whitespace)
  --raw                Save raw page without processing (useful for debugging)
  --optimize           Optimize for smaller file size (removes unused
                       styles/fonts, recommended for large pages)
  -q, --quiet          Suppress progress output
  --json               Output result as JSON (for scripting)
  --open               Open saved file in default application
  --help               Show this message and exit.

===========
# OUTPUT FOR: inspekt screenshot --help

Usage: inspekt screenshot [OPTIONS] COMMAND [ARGS]...

  Capture screenshots of elements, viewport, or full page.

Options:
  --help  Show this message and exit.

Commands:
  node      Capture a screenshot of a specific element (node).
  page      Capture a screenshot of the entire page (full height).
  viewport  Capture a screenshot of the visible viewport.

===========
# OUTPUT FOR: inspekt selected --help

Usage: inspekt selected [OPTIONS]

  [DEPRECATED] Get the current text selection in the browser.

  Please use 'inspekt selection text' instead.

Options:
  --raw   Output only the text without formatting
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt selection --help

Usage: inspekt selection [OPTIONS] COMMAND [ARGS]...

  Get the current text selection in the browser.

Options:
  --json  Output as JSON with all formats
  --help  Show this message and exit.

Commands:
  html      Get selected HTML.
  markdown  Get selected text as Markdown (converted from HTML).
  text      Get selected text (plain text).

===========
# OUTPUT FOR: inspekt send --help

Usage: inspekt send [OPTIONS] TEXT

  [DEPRECATED] Send text to the browser by typing it character by character.

  Please use 'inspekt type' or 'inspekt paste' instead.

  Examples:     inspekt type "Hello World"     inspekt paste
  "test@example.com" --selector "input[type=email]"

Options:
  -s, --selector TEXT  CSS selector to focus before typing
  --help               Show this message and exit.

===========
# OUTPUT FOR: inspekt setup --help

Usage: inspekt setup [OPTIONS]

  Interactive setup wizard for new users.

  Detects your shell and helps configure: - Tab completion for commands -
  Useful tips for getting started

  Run with --install-completion to automatically add completion to your shell
  config.

Options:
  --install-completion  Automatically install shell completion
  --help                Show this message and exit.

===========
# OUTPUT FOR: inspekt start --help

Usage: inspekt start [OPTIONS]

  Start Inspekt servers (bridge + API) in daemon mode.

  By default, starts both bridge and API servers in background. Use --bridge-
  only or --api-only to start specific servers. Use --foreground for debugging
  (only works with single server). Use --docs to also start a local MkDocs
  documentation server.

  Examples:     inspekt start                      # Start both servers in
  background     inspekt start --docs               # Include local
  documentation server     inspekt start --bridge-only        # Start only
  bridge server     inspekt start --foreground         # Start both in
  foreground (interactive)     inspekt start --no-update-check    # Skip axe-
  core update check     inspekt start --api-port 3000      # Use custom API
  port

Options:
  --bridge-only          Start only the bridge server
  --api-only             Start only the API server
  --foreground           Run in foreground (for debugging)
  --no-update-check      Skip axe-core update check
  --api-port INTEGER     API server port (default: 8000)
  --bridge-port INTEGER  Bridge server port (default: 8765)
  --host TEXT            Host to bind to (default: 127.0.0.1)
  --docs                 Start local MkDocs documentation server
  --docs-port INTEGER    MkDocs server port (default: 8008)
  --help                 Show this message and exit.

===========
# OUTPUT FOR: inspekt status --help

Usage: inspekt status [OPTIONS] COMMAND [ARGS]...

  Check status of all Inspekt servers.

  Shows comprehensive status information for both bridge and API servers,
  including connected browsers, request statistics, and uptime.

  Examples:     inspekt status        # Human-readable status     inspekt
  status --json # JSON output     inspekt status web    # Open web dashboard

Options:
  --json  Output as JSON
  --help  Show this message and exit.

Commands:
  web  Open the web-based dashboard in your browser.

===========
# OUTPUT FOR: inspekt stop --help

Usage: inspekt stop [OPTIONS]

  Stop Inspekt servers.

  By default, stops all servers (bridge, API, and MkDocs if running). Use
  --bridge-only or --api-only to stop specific servers.

  Examples:     inspekt stop                # Stop all servers     inspekt
  stop --bridge-only  # Stop only bridge server     inspekt stop --api-only
  # Stop only API server

Options:
  --bridge-only  Stop only the bridge server
  --api-only     Stop only the API server
  --help         Show this message and exit.

===========
# OUTPUT FOR: inspekt storage --help

Usage: inspekt storage [OPTIONS] COMMAND [ARGS]...

  Manage browser storage (cookies, localStorage, sessionStorage).

Options:
  --help  Show this message and exit.

Commands:
  clear   Clear all storage items.
  delete  Delete a specific storage item.
  get     Get the value of a specific storage item.
  list    List all storage items.
  set     Set a storage item.

===========
# OUTPUT FOR: inspekt summarize --help

Usage: inspekt summarize [OPTIONS]

  Summarize the current article using AI.

  Extracts article content using Mozilla Readability and generates a concise
  summary using the mods command.

  Examples:     inspekt summarize                    # Get AI summary
  inspekt summarize --format full      # Show full extracted article

Options:
  --format [summary|full]  Output format (summary or full article)
  --language, --lang TEXT  Language for AI output (overrides config)
  --debug                  Show the full prompt instead of calling AI
  --force-refresh          Force refresh, bypass cache
  --help                   Show this message and exit.

===========
# OUTPUT FOR: inspekt top --help

Usage: inspekt top [OPTIONS]

  Scroll to the top of the page.

  Example:     inspekt top

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt type --help

Usage: inspekt type [OPTIONS] TEXT

  Type text character by character into the browser.

  Types text into the currently focused input field, or into a specific
  element if --selector is provided.

  By default, clears any existing text and types as fast as possible. Use
  --speed to control typing rate and --no-clear to append instead.

  Examples:     # Type at maximum speed (clears existing text):     inspekt
  type "Hello World"

      # Type with human-like random delays (~50 WPM):     inspekt type "Hello,
      how are you?" --speed 0

      # Type at 10 characters per second:     inspekt type "test@example.com"
      --speed 10

      # Type without clearing existing text:     inspekt type "append this"
      --no-clear

      # Type into a specific field:     inspekt type "password123" --selector
      "input[type=password]"

Options:
  -s, --selector TEXT   CSS selector to focus before typing
  --speed INTEGER       Typing speed in characters per second (default:
                        fastest, 0: human-like)
  --clear / --no-clear  Clear existing text before typing (default: true)
  --help                Show this message and exit.

===========
# OUTPUT FOR: inspekt userscript --help

Usage: inspekt userscript [OPTIONS]

  Display the userscript that needs to be installed in your browser.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt validate --help

Usage: inspekt validate [OPTIONS] [RECORDING_FILE]

  Validate a recording file before replay.

  Checks for YAML syntax errors, missing files, timestamp issues, and other
  problems that could cause replay failures.

  Examples:
      inspekt validate                    # Validate most recent recording
      inspekt validate my-recording.yaml  # Validate specific file
      inspekt validate --strict           # Treat warnings as errors
      inspekt validate --json             # JSON output for CI/tooling

Options:
  --strict  Treat warnings as errors (exit with error code if warnings found)
  --json    Output results as JSON for tooling integration
  --help    Show this message and exit.

===========
# OUTPUT FOR: inspekt vm --help

Usage: inspekt vm [OPTIONS] COMMAND [ARGS]...

  Manage the Inspekt Browser VM.

  The Browser VM is a Docker-based virtual machine with Chromium and the
  Inspekt extension pre-installed. Access it via noVNC in your browser.

  Examples:     inspekt vm start    # Build and start the VM     inspekt vm
  open     # Open the control panel     inspekt vm stop     # Stop the VM
  inspekt vm status   # Check VM status     inspekt vm restart  # Restart the
  VM

Options:
  --help  Show this message and exit.

Commands:
  logs     Show VM container logs.
  open     Open the VM control panel in your browser.
  restart  Restart the Inspekt Browser VM.
  shell    Open a shell inside the VM container.
  start    Start the Inspekt Browser VM.
  status   Check the status of the Browser VM.
  stop     Stop the Inspekt Browser VM.

===========
# OUTPUT FOR: inspekt wait --help

Usage: inspekt wait [OPTIONS] SELECTOR

  Wait for an element to appear, be visible, hidden, or contain text.

  By default, waits for element to exist in the DOM.

  Examples:     # Wait for element to exist (up to 30 seconds):     inspekt
  wait "button#submit"

      # Wait for element to be visible:     inspekt wait ".modal" --visible

      # Wait for element to be hidden:     inspekt wait ".loading-spinner"
      --hidden

      # Wait for element to contain text:     inspekt wait "h1" --text
      "Success"

      # Custom timeout (10 seconds):     inspekt wait "div.result" --timeout
      10

Options:
  -t, --timeout INTEGER  Timeout in seconds (default: 30)
  --visible              Wait for element to be visible
  --hidden               Wait for element to be hidden
  --text TEXT            Wait for element to contain specific text
  --help                 Show this message and exit.

===========
# OUTPUT FOR: inspekt watch --help

Usage: inspekt watch [OPTIONS] COMMAND [ARGS]...

  Watch browser events in real-time.

Options:
  --help  Show this message and exit.

Commands:
  all    Watch all user interactions - keyboard, focus, and accessible...
  input  Watch keyboard input in real-time.

===========
# OUTPUT FOR: inspekt yolo --help

Usage: inspekt yolo [OPTIONS]

  YOLO mode - bypass ALL restrictions for 1 hour.

  When yolo mode is active: - CLI skips domain permission prompts - Browser
  extension skips domain checks - CSP bypass enabled for current domain
  (strict sites work) - All domains are allowed without confirmation

  This is useful for development or when working across many domains. Yolo
  mode automatically expires after 1 hour.

  Examples:     inspekt yolo              # Enable for 1 hour     inspekt yolo
  --status     # Check if active and time remaining     inspekt yolo --disable
  # Disable early

Options:
  -d, --disable  Disable yolo mode
  -s, --status   Check yolo mode status
  --help         Show this message and exit.

===========
# OUTPUT FOR: inspekt completion bash --help

Usage: inspekt completion bash [OPTIONS]

  Output bash completion script.

  To install manually:
      inspekt completion bash >> ~/.bashrc
      source ~/.bashrc

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt completion zsh --help

Usage: inspekt completion zsh [OPTIONS]

  Output zsh completion script.

  To install manually:
      inspekt completion zsh >> ~/.zshrc
      source ~/.zshrc

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt completion fish --help

Usage: inspekt completion fish [OPTIONS]

  Output fish completion script.

  To install manually:
      inspekt completion fish > ~/.config/fish/completions/inspekt.fish

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt console list --help

Usage: inspekt console list [OPTIONS]

  Show captured console messages from the browser.

  Displays console.log, console.error, console.warn, console.info, and
  console.debug messages that were captured since the page loaded.

  Messages are captured automatically when pages load. Use --level to filter
  by severity and --limit to control how many messages to show.

  Examples:     inspekt console list     inspekt console list --level error
  inspekt console list --limit 50 --tail     inspekt console list --json | jq
  '.entries[].message'

Options:
  -l, --level [all|error|warn|log|info|debug]
                                  Filter by log level (default: all)
  -n, --limit INTEGER             Maximum number of messages to show (default:
                                  100)
  --json                          Output as JSON
  -t, --tail                      Show most recent messages first
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt console clear --help

Usage: inspekt console clear [OPTIONS]

  Clear the console message buffer.

  Removes all captured console messages from the browser's buffer. New
  messages will continue to be captured until the page is navigated away.

  Examples:     inspekt console clear     inspekt console clear --json

Options:
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt domain add --help

Usage: inspekt domain add [OPTIONS] DOMAIN_NAME

  Add a domain to the allowed list.

  The domain is normalized (www. prefix stripped) and stored in SQLite, then
  auto-synced to the browser extension if connected.

  Parent domains grant access to subdomains (e.g., github.com allows
  www.github.com).

  Examples:     inspekt domain add github.com     inspekt domain add
  www.example.com  # Stored as example.com     inspekt domain add localhost

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt domain bypass --help

Usage: inspekt domain bypass [OPTIONS] DURATION

  Set temporary bypass for all domains.

  Allows all domains for the specified duration in minutes. Use 0 to disable
  bypass.

  Examples:     inspekt domain bypass 15     # Allow all for 15 minutes
  inspekt domain bypass 60     # Allow all for 1 hour     inspekt domain
  bypass 0      # Disable bypass

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt domain csp --help

Usage: inspekt domain csp [OPTIONS] [DOMAIN_NAME]

  Manage CSP (Content Security Policy) bypass for strict sites.

  Some websites have strict CSP that blocks Inspekt from executing JavaScript.
  This command enables bypassing CSP headers for specific domains.

  IMPORTANT: After enabling CSP bypass, you must refresh the page for changes
  to take effect.

  Examples:     inspekt domain csp www.dnsbelgium.be --enable    # Enable
  bypass     inspekt domain csp www.dnsbelgium.be --disable   # Disable bypass
  inspekt domain csp www.dnsbelgium.be --status    # Check status     inspekt
  domain csp --list                        # List all bypassed domains

Options:
  -e, --enable   Enable CSP bypass for domain
  -d, --disable  Disable CSP bypass for domain
  -s, --status   Check CSP bypass status
  -l, --list     List all CSP bypass domains
  --help         Show this message and exit.

===========
# OUTPUT FOR: inspekt domain list --help

Usage: inspekt domain list [OPTIONS]

  List all allowed domains.

  Shows all domains with their timestamps and metadata. This command reads
  directly from the local SQLite database and does not require a browser
  connection.

  Examples:     inspekt domain list              # Human-readable format
  inspekt domain list --json       # JSON format

Options:
  -j, --json  Output as JSON
  --help      Show this message and exit.

===========
# OUTPUT FOR: inspekt domain remove --help

Usage: inspekt domain remove [OPTIONS] DOMAIN_NAME

  Remove a domain from the allowed list.

  The domain is normalized (www. prefix stripped) before removal, then auto-
  synced to the browser extension if connected.

  Examples:     inspekt domain remove github.com     inspekt domain remove
  www.example.com  # Removes example.com     inspekt domain remove localhost

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt mcp describe --help

Usage: inspekt mcp describe [OPTIONS] TOOL_NAME

  Show detailed documentation for a specific MCP tool.

  Displays full parameter schemas, descriptions, return types, and usage
  examples for the specified tool.

Options:
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt mcp info --help

Usage: inspekt mcp info [OPTIONS]

  Show information about available MCP tools and resources.

  Lists all tools (actions) and resources (read-only data) that the MCP server
  exposes to AI assistants. Dynamically fetches tool definitions including any
  MCP-enabled plugins.

Options:
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt mcp start --help

Usage: inspekt mcp start [OPTIONS]

  Start the MCP server in stdio mode.

  The MCP server exposes Inspekt's browser automation capabilities as tools
  and resources for AI assistants like Claude Desktop.

  The server runs in stdio mode, which is compatible with Claude Desktop and
  other MCP clients that use standard input/output for communication.

  Make sure the bridge server is running first:     inspekt start --bridge-
  only

  Then configure your Claude Desktop config to use this server:     {
  "mcpServers": {         "inspekt": {           "command": "inspekt",
  "args": ["mcp", "start"]         }       }     }

Options:
  --bridge-port INTEGER  Bridge server port (default: 8765)
  --cache-ttl INTEGER    Resource cache TTL in seconds (default: 5)
  --help                 Show this message and exit.

===========
# OUTPUT FOR: inspekt mcp test --help

Usage: inspekt mcp test [OPTIONS]

  Test MCP server connectivity and basic functionality.

  Checks if the bridge server is running and tests basic communication with
  the browser.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network audio --help

Usage: inspekt network audio [OPTIONS]

  Show only audio resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network css --help

Usage: inspekt network css [OPTIONS]

  Show only CSS resources (alias for stylesheet).

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network document --help

Usage: inspekt network document [OPTIONS]

  Show only document/HTML resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network fetch --help

Usage: inspekt network fetch [OPTIONS]

  Show only fetch/XHR requests.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network font --help

Usage: inspekt network font [OPTIONS]

  Show only font resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network har --help

Usage: inspekt network har [OPTIONS]

  Get full network data from DevTools (HAR format).

  This command requires Chrome DevTools to be open (F12) for the active tab.
  It provides complete network data including:

  - HTTP status codes (200, 404, 500, etc.) - Request and response headers -
  Full timing breakdown - Initiator information

  If DevTools is not open, you'll get an error. Use `inspekt network` for
  basic network data that works without DevTools.

  Examples:     inspekt network har                    # Full HAR data
  inspekt network har --json             # Output as JSON     inspekt network
  har --errors           # Only failed requests     inspekt network har
  --type=script      # Only scripts     inspekt network har --sort=status
  # Sort by status code     inspekt network har --raw              # Raw HAR
  for export

Options:
  --json                          Output as JSON
  --sort [start|time|size|name|type|status]
                                  Sort by field (default: start time)
  --domain                        Show domain column
  --external                      Show only external requests
  --errors                        Show only failed requests (4xx/5xx)
  -n, --limit INTEGER             Limit number of results
  --type [script|stylesheet|fetch|image|font|document]
                                  Filter by resource type
  --raw                           Output raw HAR format (for import into other
                                  tools)
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt network image --help

Usage: inspekt network image [OPTIONS]

  Show only image resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network script --help

Usage: inspekt network script [OPTIONS]

  Show only JavaScript resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network stylesheet --help

Usage: inspekt network stylesheet [OPTIONS]

  Show only CSS resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network svg --help

Usage: inspekt network svg [OPTIONS]

  Show only SVG resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network video --help

Usage: inspekt network video [OPTIONS]

  Show only video resources.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt network xhr --help

Usage: inspekt network xhr [OPTIONS]

  Show only XHR requests.

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin add --help

Usage: inspekt plugin add [OPTIONS] NAME

  Add a new plugin.

  Provide code via --code, --file, or --url (bookmarklet). Bookmarklet URLs
  are automatically parsed and cleaned.

  Examples:     inspekt plugin add "Dark Mode" --code "(function(){...})();"
  inspekt plugin add "Text Spacing" --url "javascript:(function(){...})();"
  inspekt plugin add "Custom" --file ./my-plugin.js --category utility
  inspekt plugin add "Extractor" --code "..." --returns-data --mcp

Options:
  -c, --code TEXT         JavaScript code
  -f, --file PATH         Read code from file
  -u, --url TEXT          Bookmarklet URL (javascript:...)
  -d, --description TEXT  Plugin description
  --category TEXT         Category for organization
  -t, --tags TEXT         Comma-separated tags
  --mcp                   Expose as MCP tool
  --returns-data          Plugin returns JSON data
  --help                  Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin export --help

Usage: inspekt plugin export [OPTIONS]

  Export plugins to JSON file.

  Exports all plugins or specific ones to a JSON file that can be shared and
  imported.

  Examples:     inspekt plugin export     inspekt plugin export --output my-
  plugins.json     inspekt plugin export --ids text-spacing,dark-mode
  inspekt plugin export -o plugins.json --open

Options:
  -o, --output PATH  Output file path
  --ids TEXT         Comma-separated plugin IDs to export
  --open             Open exported file in default application
  --help             Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin import --help

Usage: inspekt plugin import [OPTIONS] FILE_PATH

  Import plugins from JSON file.

  Imports plugins from an export file. By default, existing plugins with the
  same name are skipped.

  Examples:     inspekt plugin import plugins.json     inspekt plugin import
  plugins.json --replace

Options:
  --replace  Replace existing plugins with same name
  --skip     Skip existing plugins (default)
  --help     Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin list --help

Usage: inspekt plugin list [OPTIONS]

  List all plugins.

  Shows all plugins with their metadata. Use --category to filter or --mcp to
  show only MCP-exposed plugins.

  Examples:     inspekt plugin list     inspekt plugin list --category a11y
  inspekt plugin list --mcp     inspekt plugin list --json

Options:
  -c, --category TEXT  Filter by category
  --mcp                Only show MCP-exposed plugins
  -j, --json           Output as JSON
  --help               Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin remove --help

Usage: inspekt plugin remove [OPTIONS] NAME_OR_ID

  Remove a plugin.

  Accepts plugin name or ID. Use --force to skip confirmation.

  Examples:     inspekt plugin remove text-spacing     inspekt plugin remove
  "Text Spacing Bookmarklet"     inspekt plugin remove dark-mode --force

Options:
  -f, --force  Skip confirmation
  --help       Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin run --help

Usage: inspekt plugin run [OPTIONS] NAME_OR_ID

  Execute a plugin in the browser.

  Runs the plugin code in the current browser tab and captures console output.
  If the plugin returns data, it's displayed.

  Examples:     inspekt plugin run text-spacing     inspekt plugin run "Dark
  Mode" --timeout 10     inspekt plugin run extractor --json

Options:
  -t, --timeout INTEGER  Execution timeout (seconds)
  -j, --json             Output result as JSON
  -q, --quiet            Suppress console output
  --help                 Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin show --help

Usage: inspekt plugin show [OPTIONS] NAME_OR_ID

  Display plugin details.

  Shows full plugin information including code.

  Examples:     inspekt plugin show text-spacing     inspekt plugin show "Dark
  Mode" --json

Options:
  -j, --json  Output as JSON
  --help      Show this message and exit.

===========
# OUTPUT FOR: inspekt plugin unload --help

Usage: inspekt plugin unload [OPTIONS] NAME_OR_ID

  Unload/reverse a plugin's effects.

  Behavior depends on the plugin's unload mode: - toggle: Re-runs the plugin
  code (for toggle-style plugins) - custom: Runs the custom unload code -
  none: Returns error (plugin doesn't support unloading)

  Examples:     inspekt plugin unload text-spacing     inspekt plugin unload
  "Dark Mode"

Options:
  -t, --timeout INTEGER  Execution timeout (seconds)
  -j, --json             Output result as JSON
  -q, --quiet            Suppress console output
  --help                 Show this message and exit.

===========
# OUTPUT FOR: inspekt queue clear --help

Usage: inspekt queue clear [OPTIONS]

  Clear pending requests from the queue.

  By default, clears all pending requests. Use --older-than to only clear
  requests that have been pending for a certain time.

  This is useful when requests get stuck and are blocking new ones.

  Examples:     inspekt queue clear              # Clear all     inspekt queue
  clear --older-than 30  # Clear requests older than 30s     inspekt queue
  clear -f           # Skip confirmation

Options:
  --older-than FLOAT  Only clear requests older than N seconds (default: all)
  -f, --force         Skip confirmation
  --help              Show this message and exit.

===========
# OUTPUT FOR: inspekt queue status --help

Usage: inspekt queue status [OPTIONS]

  Show queue status and pending requests.

  Displays the number of pending and completed requests, along with details
  about each pending request.

  Examples:     inspekt queue status        # Human-readable output
  inspekt queue status --json # JSON output

Options:
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt record _ delete --help

Usage: inspekt record [FILENAME] delete [OPTIONS] [RECORDING_FILE]

  Delete a recording file.

  If no file is specified, uses the most recently modified recording.

  Examples:
      inspekt record delete                # Delete last modified recording
      inspekt record delete login-flow.yaml
      inspekt record delete --force old-recording.yaml

Options:
  -f, --force  Skip confirmation
  --help       Show this message and exit.

===========
# OUTPUT FOR: inspekt record _ edit --help

Usage: inspekt record [FILENAME] edit [OPTIONS] [RECORDING_FILE]

  Open a recording file in your default editor.

  If no file is specified, uses the most recently modified recording.

  Examples:
      inspekt record edit                # Edit last modified recording
      inspekt record edit login-flow.yaml

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt record _ list --help

Usage: inspekt record [FILENAME] list [OPTIONS]

  List all saved recordings.

  Shows recordings from ~/.inspekt/recordings/ with metadata including date,
  duration, step count, and starting URL.

  Examples:
      inspekt record list              # List all recordings
      inspekt record list --limit 10   # Show last 10
      inspekt record list --json       # JSON output

Options:
  -n, --limit INTEGER  Show only the last N recordings
  --json               Output as JSON
  --help               Show this message and exit.

===========
# OUTPUT FOR: inspekt record _ show --help

Usage: inspekt record [FILENAME] show [OPTIONS] [RECORDING_FILE]

  Show details of a recording file.

  Displays metadata and step summary for a recording. If no file is specified,
  uses the most recently modified recording.

  Examples:
      inspekt record show                # Show last modified recording
      inspekt record show login-flow.yaml

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt record _ tidy --help

Usage: inspekt record [FILENAME] tidy [OPTIONS] [FILE]

  Tidy up a recording file.

  Performs comprehensive cleanup of a recording YAML file. If no file is
  specified, uses the most recently modified recording.

  Operations (all enabled by default):
  ✓ Validate YAML syntax (abort if invalid)
  ✓ Detect fragile selectors (warnings only)
  ✓ Validate timestamp order (warnings only)
  ✓ Re-number steps sequentially (0001, 0002, 0003...)
  ✓ Enrich comments with assertion info
  ✓ Normalize key order for consistency
  ✓ Remove empty/null values
  ✓ Fix indentation (2 spaces)

  Examples:
      inspekt record tidy                             # Tidy last modified
      inspekt record tidy recording.yaml              # Full tidy
      inspekt record tidy recording.yaml --dry-run    # Preview changes
      inspekt record tidy recording.yaml --force      # Replace all comments
      inspekt record tidy recording.yaml -q           # Quiet mode

Options:
  --dry-run       Preview changes without modifying the file
  --force         Replace ALL comments, ignoring user customizations
  --no-comments   Skip comment updates
  --no-normalize  Skip key order normalization
  --no-clean      Skip empty value removal
  -q, --quiet     Only show warnings and summary
  --help          Show this message and exit.

===========
# OUTPUT FOR: inspekt record _ tutorial --help

Usage: inspekt record [FILENAME] tutorial [OPTIONS]

  Interactive tutorial for the record command.

  Learn how inspekt record works through a simulated recording session with
  audio and visual feedback.

  Examples:
      inspekt record tutorial           # Show descriptions as text
      inspekt record tutorial --speak   # Use text-to-speech

Options:
  --speak  Use text-to-speech to announce each action
  --help   Show this message and exit.

===========
# OUTPUT FOR: inspekt screenshot node --help

Usage: inspekt screenshot node [OPTIONS]

  Capture a screenshot of a specific element (node).

  By default, captures the currently inspected element from DevTools. Use
  --selector to capture a specific element by CSS selector.

  The screenshot uses the Chrome extension's captureVisibleTab API for
  reliable, high-quality captures that work on all sites (including CSP-
  protected).

  Examples:     # Capture currently inspected element     inspekt screenshot
  node -o button.png

      # Capture specific element     inspekt screenshot node --selector
      "#main" -o main.png

      # With margin and auto color     inspekt screenshot node -o hero.png
      --margin 20 --margin-color auto

      # Optimize file size     inspekt screenshot node -o logo.png --optimize

      # Custom margin color     inspekt screenshot node -o card.png --margin
      10 --margin-color "#f0f0f0"

Options:
  -s, --selector TEXT             CSS selector of element (default: use
                                  currently inspected element)
  -o, --output PATH               Output file path (default: auto-generated)
  -m, --margin INTEGER            Margin in pixels around screenshot (default:
                                  from config)
  -c, --margin-color TEXT         Margin color: 'auto' (sample first pixel),
                                  hex code like '#fff', or color name
                                  (default: from config)
  --optimize / --no-optimize      Optimize PNG with oxipng to reduce file size
                                  (default: from config)
  --scale INTEGER                 Scale factor for high-DPI screenshots
                                  (default: from config)
  --format [png|jpg|webp]         Output format (default: from config)
  --quality FLOAT                 Quality for lossy formats (0.0-1.0, default:
                                  from config)
  --scroll-into-view / --no-scroll
                                  Scroll element into view before capture
                                  (default: yes)
  --hide-outline / --keep-outline
                                  Hide element outline during capture
                                  (default: yes)
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt screenshot page --help

Usage: inspekt screenshot page [OPTIONS]

  Capture a screenshot of the entire page (full height).

  Uses Chrome DevTools Protocol for single-shot full page capture. Note:
  Chrome has a maximum height limit of 16384 pixels.

  WARNING: A debugger notification banner will appear briefly during capture.
  This is a Chrome security feature and cannot be disabled.

  Examples:     inspekt screenshot page -o fullpage.png     inspekt screenshot
  page -o page.png --scale 2     inspekt screenshot page -o page.jpg --format
  jpg --quality 0.85

Options:
  -o, --output PATH        Output file path  [required]
  -m, --margin INTEGER     Margin in pixels around screenshot (default: 0)
  -c, --margin-color TEXT  Margin color: 'auto' (sample first pixel), hex
                           code, or color name (default: auto)
  --optimize               Optimize PNG with oxipng to reduce file size
  --scale INTEGER          Scale factor (1 or 2, default: 1)
  --format [png|jpg|webp]  Output format (default: png)
  --quality FLOAT          Quality for lossy formats (0.0-1.0, default: 0.92)
  --max-height INTEGER     Maximum capture height in pixels (default: 16384,
                           Chrome limit)
  --help                   Show this message and exit.

===========
# OUTPUT FOR: inspekt screenshot viewport --help

Usage: inspekt screenshot viewport [OPTIONS]

  Capture a screenshot of the visible viewport.

  Captures exactly what's visible in the browser window.

  Examples:     inspekt screenshot viewport -o viewport.png     inspekt
  screenshot viewport -o view.png --margin 10 --optimize

Options:
  -o, --output PATH        Output file path  [required]
  -m, --margin INTEGER     Margin in pixels around screenshot (default: 0)
  -c, --margin-color TEXT  Margin color: 'auto' (sample first pixel), hex
                           code, or color name (default: auto)
  --optimize               Optimize PNG with oxipng to reduce file size
  --scale INTEGER          Scale factor for high-DPI screenshots (default: 2)
  --format [png|jpg|webp]  Output format (default: png)
  --quality FLOAT          Quality for lossy formats (0.0-1.0, default: 0.92)
  --help                   Show this message and exit.

===========
# OUTPUT FOR: inspekt selection html --help

Usage: inspekt selection html [OPTIONS]

  Get selected HTML.

Options:
  --raw                     Output only the raw HTML without formatting
  --json                    Output as JSON
  --pretty / --no-pretty    Format HTML using prettier (default: from config)
  --compact / --no-compact  Remove classes and truncate long text (default:
                            from config)
  --colors / --no-colors    Apply syntax highlighting (default: from config)
  --theme TEXT              Syntax highlighting theme (e.g., monokai, vim,
                            github-dark)
  --help                    Show this message and exit.

===========
# OUTPUT FOR: inspekt selection markdown --help

Usage: inspekt selection markdown [OPTIONS]

  Get selected text as Markdown (converted from HTML).

Options:
  --raw   Output only the raw Markdown without formatting
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt selection text --help

Usage: inspekt selection text [OPTIONS]

  Get selected text (plain text).

Options:
  --raw   Output only the raw text without formatting
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt storage clear --help

Usage: inspekt storage clear [OPTIONS]

  Clear all storage items.

  By default, clears all storage types. Use flags to filter specific types.

  Examples:     inspekt storage clear --force              # Clear all types
  inspekt storage clear --cookies            # Just cookies     inspekt
  storage clear --local --session    # localStorage + sessionStorage

Options:
  -c, --cookies                   Clear cookies
  -l, --local                     Clear localStorage
  -s, --session                   Clear sessionStorage
  -a, --all                       Clear all storage types (default)
  --type [local|session|all|cookies]
                                  [DEPRECATED] Use --cookies, --local,
                                  --session, or --all instead
  --force                         Skip confirmation prompt
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt storage delete --help

Usage: inspekt storage delete [OPTIONS] KEY

  Delete a specific storage item.

  Deletes from the specified storage type. Defaults to localStorage if no type
  specified.

  Examples:     inspekt storage delete user_token                  #
  localStorage     inspekt storage delete session_id --cookies        # Cookie
  inspekt storage delete temp_data --session         # sessionStorage

Options:
  -c, --cookies                   Delete from cookies
  -l, --local                     Delete from localStorage
  -s, --session                   Delete from sessionStorage
  --type [local|session|cookies]  [DEPRECATED] Use --cookies, --local, or
                                  --session instead
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt storage get --help

Usage: inspekt storage get [OPTIONS] KEY

  Get the value of a specific storage item.

  Searches in the specified storage type. Defaults to localStorage if no type
  specified.

  Examples:     inspekt storage get user_token                # localStorage
  (default)     inspekt storage get session_id --cookies      # Cookie
  inspekt storage get temp_data --session       # sessionStorage     inspekt
  storage get preferences --local --json

Options:
  -c, --cookies                   Get from cookies
  -l, --local                     Get from localStorage
  -s, --session                   Get from sessionStorage
  --type [local|session|cookies]  [DEPRECATED] Use --cookies, --local, or
                                  --session instead
  -j, --json                      Output as JSON
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt storage list --help

Usage: inspekt storage list [OPTIONS]

  List all storage items.

  By default, lists all storage types. Use flags to filter specific types.

  Examples:     inspekt storage list                    # All types
  inspekt storage list --cookies          # Just cookies     inspekt storage
  list --local --session  # localStorage + sessionStorage     inspekt storage
  list --all --json       # All types as JSON

  Legacy examples (deprecated --type flag):     inspekt storage list
  --type=local     inspekt storage list --type=all --json

Options:
  -c, --cookies                   Include cookies
  -l, --local                     Include localStorage
  -s, --session                   Include sessionStorage
  -a, --all                       Include all storage types (default)
  --type [local|session|all|cookies]
                                  [DEPRECATED] Use --cookies, --local,
                                  --session, or --all instead
  -j, --json                      Output as JSON
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt storage set --help

Usage: inspekt storage set [OPTIONS] KEY VALUE

  Set a storage item.

  Stores in the specified storage type. Defaults to localStorage if no type
  specified.

  Examples:     inspekt storage set user_token abc123                    #
  localStorage     inspekt storage set session_id xyz --cookies             #
  Cookie     inspekt storage set temp '{"data":"value"}' --session    #
  sessionStorage

  Cookie-specific examples:     inspekt storage set session_id abc --cookies
  --max-age 3600 --secure     inspekt storage set auth_token xyz --cookies
  --path / --same-site Strict

Options:
  -c, --cookies                   Set as cookie
  -l, --local                     Set in localStorage
  -s, --session                   Set in sessionStorage
  --type [local|session|cookies]  [DEPRECATED] Use --cookies, --local, or
                                  --session instead
  --max-age INTEGER               Cookie max age in seconds
  --expires TEXT                  Cookie expiration date
  --path TEXT                     Cookie path (default: /)
  --domain TEXT                   Cookie domain
  --secure                        Secure flag (HTTPS only)
  --same-site [Strict|Lax|None]   SameSite attribute
  --help                          Show this message and exit.

===========
# OUTPUT FOR: inspekt vm logs --help

Usage: inspekt vm logs [OPTIONS]

  Show VM container logs.

  Displays the Docker container logs for debugging.

  Examples:     inspekt vm logs

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt vm open --help

Usage: inspekt vm open [OPTIONS]

  Open the VM control panel in your browser.

  Opens the web-based control panel where you can interact with the VM, run
  commands, and access Chrome and Terminal.

  Examples:     inspekt vm open

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt vm restart --help

Usage: inspekt vm restart [OPTIONS]

  Restart the Inspekt Browser VM.

  Stops the VM if running and starts it fresh.

  When running from the Inspekt source repository, dev mode is automatically
  enabled to mount local source files. Use --no-dev to disable this.

  Examples:     inspekt vm restart           # Restart the VM (auto-detects
  dev environment)     inspekt vm restart --rebuild # Rebuild and restart
  inspekt vm restart --dev     # Explicitly enable development mode
  inspekt vm restart --no-dev  # Disable auto-detected dev mode

Options:
  --rebuild  Force rebuild the Docker image
  --dev      Development mode: mount source files for live editing
  --no-dev   Disable dev mode even in source repo
  --help     Show this message and exit.

===========
# OUTPUT FOR: inspekt vm shell --help

Usage: inspekt vm shell [OPTIONS]

  Open a shell inside the VM container.

  Opens an interactive bash shell inside the running container for debugging
  or manual operations.

  Examples:     inspekt vm shell

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt vm start --help

Usage: inspekt vm start [OPTIONS]

  Start the Inspekt Browser VM.

  Builds the Docker image if needed and starts the container. The VM will be
  accessible at http://localhost:6080/control.html

  When running from the Inspekt source repository, dev mode is automatically
  enabled to mount local source files. Use --no-dev to disable this.

  Examples:     inspekt vm start           # Start the VM (auto-detects dev
  environment)     inspekt vm start --rebuild # Force rebuild the image
  inspekt vm start --no-open # Don't open browser     inspekt vm start --dev
  # Explicitly enable development mode     inspekt vm start --no-dev  #
  Disable auto-detected dev mode

Options:
  --rebuild  Force rebuild the Docker image
  --no-open  Don't open the control panel after starting
  --dev      Development mode: mount source files for live editing
  --no-dev   Disable dev mode even in source repo
  --help     Show this message and exit.

===========
# OUTPUT FOR: inspekt vm status --help

Usage: inspekt vm status [OPTIONS]

  Check the status of the Browser VM.

  Shows whether the VM is running and its connection details.

  Examples:     inspekt vm status        # Human-readable output     inspekt
  vm status --json # JSON output

Options:
  --json  Output as JSON
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt vm stop --help

Usage: inspekt vm stop [OPTIONS]

  Stop the Inspekt Browser VM.

  Stops the running container. Use 'inspekt vm start' to start it again.

  Examples:     inspekt vm stop

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt watch all --help

Usage: inspekt watch all [OPTIONS]

  Watch all user interactions - keyboard, focus, and accessible names.

  Features: - Groups regular typing on single lines - Shows special keys (Tab,
  Enter, arrows, modifiers) on separate lines - Displays accessible name when
  tabbing to focusable elements

  Press Ctrl+C to stop watching.

  Example:     inspekt watch all

Options:
  --help  Show this message and exit.

===========
# OUTPUT FOR: inspekt watch input --help

Usage: inspekt watch input [OPTIONS]

  Watch keyboard input in real-time.

  Streams all keyboard events from the browser to the terminal. Press Ctrl+C
  to stop watching.

  Example:     inspekt watch input

Options:
  --help  Show this message and exit.
