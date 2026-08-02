"""
Utility command definitions.

These commands provide various helper functionality for development,
debugging, and file management.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)

# =============================================================================
# REPL COMMAND
# =============================================================================

repl = CommandDefinition(
    id="repl",
    name="REPL",
    category=Category.UTILITIES,
    description="""Start an interactive REPL session.

Execute JavaScript interactively in the browser context.
Console output is shown automatically. Type 'exit' or press Ctrl+D to quit.

Useful for:
- Exploring the DOM interactively
- Testing JavaScript snippets
- Debugging page behavior
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,  # CLI-only (interactive terminal)
    cli_name="repl",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt repl",
    ],
)


# =============================================================================
# USERSCRIPT COMMAND
# =============================================================================

userscript = CommandDefinition(
    id="userscript",
    name="Userscript",
    category=Category.UTILITIES,
    description="""Display the userscript that needs to be installed in your browser.

Shows the location of the userscript.js file and installation instructions
for userscript managers like Tampermonkey, Greasemonkey, or Violentmonkey.
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="userscript",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt userscript",
    ],
)


# =============================================================================
# DOWNLOAD COMMAND
# =============================================================================

download = CommandDefinition(
    id="download",
    name="Download",
    category=Category.UTILITIES,
    description="""Find and download files from the current page.

Discovers images, PDFs, videos, audio files, documents and archives.
Uses interactive selection with gum choose if available.

**Options:**
- `-o, --output`: Output directory (default: ~/Downloads/<domain>)
- `--list`: Only list files without downloading
- `--json`: Output as JSON (requires --list)
- `--open`: Open downloaded file in default application
- `--reveal`: Reveal downloaded file in file explorer
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="download",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt download",
        "inspekt download --list",
        "inspekt download --list --json",
        "inspekt download -o ./files",
        "inspekt download --open",
    ],
)


# =============================================================================
# SAVE COMMAND
# =============================================================================

save = CommandDefinition(
    id="save",
    name="Save Page",
    category=Category.UTILITIES,
    description="""Save the current page as a self-contained HTML file.

Uses SingleFile to capture the complete DOM state including:
- JavaScript-rendered content
- Embedded images, fonts, and CSS
- Current scroll position and form states

**Options:**
- `-o, --output`: Output file path
- `-d, --dir`: Output directory (default: current directory)
- `--no-images`: Skip embedding images (faster, smaller)
- `--remote-images`: Keep image URLs instead of embedding
- `--optimize`: Enable aggressive optimization for large pages
- `--compress`: Compress HTML output
- `--open`: Open saved file after completion
- `--reveal`: Reveal in file explorer after completion
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="save",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt save",
        "inspekt save -o page.html",
        "inspekt save --no-images",
        "inspekt save --optimize --compress",
        "inspekt save --open",
    ],
)


# =============================================================================
# VALIDATE COMMAND
# =============================================================================

validate = CommandDefinition(
    id="validate",
    name="Validate Recording",
    category=Category.UTILITIES,
    description="""Validate a recording YAML file.

Checks the recording file for:
- Valid YAML syntax
- Required fields and structure
- Valid action types and parameters
- Consistent metadata

**Options:**
- `--strict`: Treat warnings as errors
- `--json`: Output results as JSON
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="validate",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt validate recording.yaml",
        "inspekt validate --strict recording.yaml",
        "inspekt validate --json recording.yaml",
    ],
)


# =============================================================================
# ROBOTS COMMAND
# =============================================================================

robots = CommandDefinition(
    id="robots",
    name="Robots.txt",
    category=Category.UTILITIES,
    description="""Fetch and display robots.txt for the current domain.

Shows the robots.txt file with syntax highlighting and analysis.
Useful for checking crawling permissions before automation.
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="robots",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt robots",
    ],
)


# =============================================================================
# YOLO COMMAND
# =============================================================================

yolo = CommandDefinition(
    id="yolo",
    name="YOLO Mode",
    category=Category.UTILITIES,
    description="""YOLO mode - bypass ALL restrictions for 1 hour.

When yolo mode is active:
- CLI skips domain permission prompts
- Browser extension skips domain checks
- CSP bypass enabled for current domain
- All domains are allowed without confirmation

This is useful for development or when working across many domains.
Yolo mode automatically expires after 1 hour.

**Options:**
- `-d, --disable`: Disable yolo mode
- `-s, --status`: Check yolo mode status
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="yolo",
    api_path=None,
    mcp_enabled_default=False,
    examples=[
        "inspekt yolo",
        "inspekt yolo --status",
        "inspekt yolo --disable",
    ],
)


# =============================================================================
# DOMAIN COMMAND (GROUP)
# =============================================================================

domain = CommandDefinition(
    id="domain",
    name="Domain Management",
    category=Category.UTILITIES,
    description="""Manage allowed domains for browser automation.

Control which domains can be automated. Parent domains grant access
to subdomains (e.g., github.com allows www.github.com).

**Subcommands:**
- `add`: Add a domain to the allowed list
- `remove`: Remove a domain from the allowed list
- `list`: List all allowed domains
- `check`: Check if a domain is allowed
- `clear`: Clear all allowed domains
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="domain",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="add",
            description="Add a domain to the allowed list",
            params_schema=EmptyParams,
            examples=["inspekt domain add github.com"],
        ),
        SubcommandDefinition(
            name="remove",
            description="Remove a domain from the allowed list",
            params_schema=EmptyParams,
            examples=["inspekt domain remove github.com"],
        ),
        SubcommandDefinition(
            name="list",
            description="List all allowed domains",
            params_schema=EmptyParams,
            examples=["inspekt domain list", "inspekt domain list --json"],
        ),
        SubcommandDefinition(
            name="csp",
            description="Manage CSP bypass rules",
            params_schema=EmptyParams,
            examples=["inspekt domain csp"],
        ),
        SubcommandDefinition(
            name="bypass",
            description="Bypass domain check temporarily",
            params_schema=EmptyParams,
            examples=["inspekt domain bypass"],
        ),
    ],
    examples=[
        "inspekt domain add github.com",
        "inspekt domain list",
        "inspekt domain csp",
    ],
)


# =============================================================================
# INFO COMMAND (GROUP)
# =============================================================================

info = CommandDefinition(
    id="info",
    name="Page Info",
    category=Category.UTILITIES,
    description="""Page information and analysis.

Without a subcommand, shows a brief summary. Use subcommands for detailed info.

**Subcommands:**
- `all`: Complete output (all categories)
- `performance`: Load times and Core Web Vitals
- `meta`: Meta tags, Open Graph, Twitter Card
- `seo`: SEO analysis including robots.txt
- `security`: HTTPS status, security headers
- `cookies`: Cookie analysis
- `storage`: localStorage/sessionStorage analysis
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="info",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="all",
            description="Complete output (all categories)",
            params_schema=EmptyParams,
            examples=["inspekt info all"],
        ),
        SubcommandDefinition(
            name="performance",
            description="Load times and Core Web Vitals",
            params_schema=EmptyParams,
            examples=["inspekt info performance"],
        ),
        SubcommandDefinition(
            name="meta",
            description="Meta tags, Open Graph, Twitter Card",
            params_schema=EmptyParams,
            examples=["inspekt info meta"],
        ),
        SubcommandDefinition(
            name="seo",
            description="SEO analysis including robots.txt",
            params_schema=EmptyParams,
            examples=["inspekt info seo"],
        ),
        SubcommandDefinition(
            name="security",
            description="HTTPS status, security headers",
            params_schema=EmptyParams,
            examples=["inspekt info security"],
        ),
        SubcommandDefinition(
            name="accessibility",
            description="Accessibility overview",
            params_schema=EmptyParams,
            examples=["inspekt info accessibility"],
        ),
        SubcommandDefinition(
            name="resources",
            description="Page resources (scripts, stylesheets, images)",
            params_schema=EmptyParams,
            examples=["inspekt info resources"],
        ),
        SubcommandDefinition(
            name="storage",
            description="localStorage/sessionStorage analysis",
            params_schema=EmptyParams,
            examples=["inspekt info storage"],
        ),
        SubcommandDefinition(
            name="tech",
            description="Detected technologies and frameworks",
            params_schema=EmptyParams,
            examples=["inspekt info tech"],
        ),
        SubcommandDefinition(
            name="domain",
            description="Domain and DNS information",
            params_schema=EmptyParams,
            examples=["inspekt info domain"],
        ),
        SubcommandDefinition(
            name="layout",
            description="Page layout and viewport info",
            params_schema=EmptyParams,
            examples=["inspekt info layout"],
        ),
    ],
    examples=[
        "inspekt info",
        "inspekt info all",
        "inspekt info performance",
        "inspekt info tech",
        "inspekt info --json",
    ],
)


# =============================================================================
# EXPORT ALL COMMANDS
# =============================================================================

UTILITIES_COMMANDS = [
    repl,
    userscript,
    download,
    save,
    validate,
    robots,
    yolo,
    domain,
    info,
]
