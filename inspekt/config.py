"""Configuration management for Inspekt."""

import json
import os
from pathlib import Path
from typing import Any

# Environment variable for isolated mode
ISOLATED_ENV_VAR = "INSPEKT_ISOLATED"


def is_isolated_mode() -> bool:
    """
    Check if isolated mode is enabled.

    Isolated mode bypasses all privacy protections and is intended
    for use in Docker VM environments where the browser is sandboxed.

    Enabled via:
    - Environment variable: INSPEKT_ISOLATED=1
    - CLI flag: --isolated (when starting bridge server)

    Returns:
        True if isolated mode is enabled, False otherwise
    """
    return os.environ.get(ISOLATED_ENV_VAR, "").lower() in ("1", "true", "yes")


def is_dev_mode() -> bool:
    """
    Check if running from source repository (development mode).

    Development mode is detected by checking if a Makefile exists
    in the parent directory of the inspekt package. This indicates
    we're running from the source checkout rather than a pip install.

    Returns:
        True if running from source repository, False otherwise
    """
    # Get the directory containing this config.py file (inspekt/)
    package_dir = Path(__file__).parent
    # Check for Makefile in parent (the repo root)
    repo_root = package_dir.parent
    return (repo_root / "Makefile").exists()


def tips_enabled() -> bool:
    """Check if tips/hints should be displayed.

    Disabled via --no-tips flag (INSPEKT_NO_TIPS=1) or config tips.enabled=false.
    Flag takes precedence over config.
    """
    if os.environ.get("INSPEKT_NO_TIPS") == "1":
        return False
    config = load_config()
    return config.get("tips", {}).get("enabled", True)


# Bridge server ports
# In isolated mode (VM), the bridge runs on different ports to avoid conflicts
BRIDGE_HTTP_PORT_DEFAULT = 8765
BRIDGE_HTTP_PORT_ISOLATED = 8767
BRIDGE_WS_PORT_DEFAULT = 8766
BRIDGE_WS_PORT_ISOLATED = 8768


def get_bridge_port() -> int:
    """
    Get the correct bridge HTTP port based on environment.

    Returns:
        8767 in isolated mode (VM), 8765 otherwise
    """
    return BRIDGE_HTTP_PORT_ISOLATED if is_isolated_mode() else BRIDGE_HTTP_PORT_DEFAULT


def get_bridge_ws_port() -> int:
    """
    Get the correct bridge WebSocket port based on environment.

    Returns:
        8768 in isolated mode (VM), 8766 otherwise
    """
    return BRIDGE_WS_PORT_ISOLATED if is_isolated_mode() else BRIDGE_WS_PORT_DEFAULT


# Default configuration
DEFAULT_CONFIG: dict[str, Any] = {
    "ai-language": "auto",
    "ai": {
        "endpoint": "https://thoth.elevenways.be/v1/chat/completions",
        "text-model": "gpt-4o-mini",
        "vision-model": "gpt-4o-mini",
        "timeout": 30,
        "max-tokens": 500,
    },
    "typing": {
        "human-like-typo-rate": 0.05,
        "human-like-skill": 0.7,
    },
    "paths": {
        "recordings": ".",  # Current directory
        "screenshots": ".",  # Current directory
        "downloads": "~/Downloads",  # User's Downloads folder
    },
    "screenshot": {
        "optimize": True,
        "format": "png",
        "scale": 2,
        "quality": 0.92,
        "margin": 0,
        "margin-color": "auto",
    },
    "html_selection": {
        "compact": False,
        "pretty": True,
        "colors": True,
        "theme": "monokai",  # Pygments theme: monokai, vim, github-dark, etc.
        "indent": 2,  # Number of spaces for indentation
    },
    "control": {
        "auto-refocus": "only-spa",
        "focus-outline": "custom",
        "speak-name": False,
        "speak-all": True,
        "announce-role": False,
        "announce-on-page-load": False,
        "navigation-wrap": True,
        "scroll-on-focus": True,
        "click-delay": 0,
        "focus-color": "#0066ff",
        "focus-size": 3,
        "focus-animation": True,
        "focus-glow": True,
        "sound-on-focus": "none",
        "selector-strategy": "id-first",
        "refocus-timeout": 2000,
        "verbose": True,
        "verbose-logging": False,
    },
    "axe": {
        "show-badges": True,
    },
    "a11y": {
        "show-compliance-warning": True,  # Show warning about automated checker limitations
    },
    "audio": {
        "output": "cli",  # "cli" (Python/system audio) | "browser" (Web Audio) | "off"
        "volume": 0.5,  # 0.0 to 1.0
    },
    "replay": {
        "validate": True,  # Run preflight validation before replay
        "skip-ahead": True,  # Show skip-ahead prompt for long delays
        "skip-threshold": 5,  # Seconds before showing skip prompt
    },
    "video": {
        "fps": 10,  # Frame rate for video recording (5-30)
        "quality": 80,  # JPEG quality for frames (50-100)
        "format": "mp4",  # Output format (mp4 or webm)
    },
    "record": {
        "max-actions-per-second": 15,  # Rate limit to prevent runaway recordings
        "synthetic-dialogs": False,  # Use non-blocking HTML overlays instead of native dialogs
    },
    "tips": {
        "enabled": True,  # Show contextual tips and hints in CLI output
    },
    "nerdfont": False,  # Enable Nerdfont glyphs in terminal output
    "show-milliseconds": True,  # Show milliseconds in record/replay timestamps
    "permissions": {
        "allow-local-files": True,  # Allow file:// URLs without adding to domain list
    },
    "transport": {
        "type": "auto",  # "auto" (Unix on macOS/Linux, TCP on Windows), "unix", "tcp", "http"
        "socket-path": None,  # Override socket path (default: ~/.inspekt/inspekt.sock)
        "auto-start": False,  # Auto-start server if not running (disabled by default)
        "connect-timeout": 5.0,  # Timeout for connection attempts (seconds)
        "max-retries": 50,  # Max retries when auto-starting server
        "retry-delay": 0.1,  # Delay between retries (seconds)
    },
    "do": {
        "synonyms-file": None,  # Custom path to synonyms YAML file (default: built-in)
        "literal-match-threshold": 0.8,  # Minimum score for literal text matching
        "substring-match-threshold": 0.5,  # Minimum score for substring matching
        "use-fuzzy-matching": True,  # Enable typo-tolerant fuzzy matching
        "max-fuzzy-distance": 2,  # Maximum Levenshtein distance for fuzzy matches
    },
    "summarize": {
        "extractor": "readability",  # "readability" (Mozilla) or "custom" (built-in lightweight)
    },
    "pdf-report": {
        "show-cover-page": True,  # Include first page preview
        "show-issue-screenshots": True,  # Capture screenshots of issue locations
        "show-metadata": True,  # Show enhanced document metadata
        "show-text-discrepancy-section": True,  # Compare text layer vs OCR
        "cover-max-height": 400,  # Max height in pixels for cover preview
        "issue-screenshot-dpi": 150,  # DPI for issue screenshots
        "max-issues-per-rule": 1,  # Max screenshots per rule type
        "text-discrepancy-threshold": 0.10,  # 10% difference triggers warning
        "max-ocr-pages": 50,  # Limit OCR processing for large documents (smart sampling)
        "ocr-analyze-all": False,  # Analyze all pages (disables sampling)
        "ocr-include-thumbnails": True,  # Include page thumbnails in text layer analysis
    },
    "tts": {
        "default-voice": "margot",
        "voices": {
            "margot": {
                "voice-id": "RwI6GdsC2IOUEWwiv1aM",
                "language-code": "nl",
                "model-id": "eleven_v3",
                "output-format": "mp3_44100_192",
                "voice-settings": {
                    "stability": 0,
                    "similarity-boost": 1,
                    "style": 1,
                    "use-speaker-boost": False,
                },
            },
        },
    },
    "mcp": {
        "enabled": True,
        "bridge-port": 8765,
        "resource-cache-ttl": 5,
        "enabled-tools": [
            "navigate_to_url",
            "go_back",
            "reload_page",
            "execute_javascript",
            "extract_links",
            "extract_outline",
            "extract_page_info",
            "extract_article",
            "click_element",
            "type_text",
            "get_page_info",
            "take_screenshot",
            "get_selected_text",
            "get_cookies",
            "set_cookie",
        ],
        "enabled-resources": [
            "current-url",
            "page-title",
            "page-metadata",
            "browser-info",
            "connection-status",
        ],
    },
}


def find_config_file() -> Path | None:
    """
    Find the config.json file.

    Searches in order:
    1. Current directory (project root)
    2. ~/.config/inspekt.json (XDG Base Directory)
    3. ~/.inspekt/config.json (legacy, backward compatibility)

    Returns:
        Path to config file if found, None otherwise
    """
    # Check current directory (resolve to absolute path so that
    # config_file.parent always gives a stable directory for data.db)
    local_config = Path("config.json")
    if local_config.exists():
        return local_config.resolve()

    # Check ~/.config/inspekt.json (XDG Base Directory standard)
    xdg_config = Path.home() / ".config" / "inspekt.json"
    if xdg_config.exists():
        return xdg_config

    # Check ~/.inspekt/config.json (legacy path for backward compatibility)
    legacy_config = Path.home() / ".inspekt" / "config.json"
    if legacy_config.exists():
        return legacy_config

    return None


def get_data_dir() -> Path:
    """
    Get the directory for storing persistent data (data.db, caches, etc.).

    Always uses a fixed, user-level directory so that data is consistent
    regardless of the working directory or how a process was started.

    Resolution order:
    1. ~/.config/inspekt/ (XDG Base Directory standard, if ~/.config/inspekt.json exists)
    2. ~/.inspekt/ (legacy or default)

    Note: Local config.json in the project root is intentionally NOT used
    for data storage — it only affects configuration. This prevents the
    CLI and API server from using different databases when started from
    different working directories.

    Returns:
        Absolute path to the data directory (created if needed)
    """
    # If user has XDG-style config, use XDG-style data dir
    xdg_config = Path.home() / ".config" / "inspekt.json"
    if xdg_config.exists():
        config_dir = Path.home() / ".config" / "inspekt"
    else:
        config_dir = Path.home() / ".inspekt"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_config() -> dict[str, Any]:
    """
    Load configuration from file or return defaults.

    Returns:
        Configuration dictionary with all settings
    """
    config_file = find_config_file()

    if config_file is None:
        return DEFAULT_CONFIG.copy()

    try:
        with open(config_file) as f:
            user_config = json.load(f)

        # Merge with defaults (user config takes precedence)
        config = DEFAULT_CONFIG.copy()

        # Merge root-level properties
        for key in user_config:
            if key == "control" and isinstance(user_config["control"], dict):
                # Nested control config - merge deeply
                if isinstance(config["control"], dict):
                    config["control"].update(user_config["control"])
            elif key == "typing" and isinstance(user_config["typing"], dict):
                # Nested typing config - merge deeply
                if isinstance(config.get("typing"), dict):
                    config["typing"].update(user_config["typing"])
                else:
                    config["typing"] = user_config["typing"]
            elif key == "screenshot" and isinstance(user_config["screenshot"], dict):
                # Nested screenshot config - merge deeply
                if isinstance(config.get("screenshot"), dict):
                    config["screenshot"].update(user_config["screenshot"])
                else:
                    config["screenshot"] = user_config["screenshot"]
            elif key == "ai" and isinstance(user_config["ai"], dict):
                # Nested AI config - merge deeply
                if isinstance(config.get("ai"), dict):
                    config["ai"].update(user_config["ai"])
                else:
                    config["ai"] = user_config["ai"]
            elif key == "mcp" and isinstance(user_config["mcp"], dict):
                # Nested MCP config - merge deeply
                if isinstance(config.get("mcp"), dict):
                    config["mcp"].update(user_config["mcp"])
                else:
                    config["mcp"] = user_config["mcp"]
            elif key == "permissions" and isinstance(user_config["permissions"], dict):
                # Nested permissions config - merge deeply
                if isinstance(config.get("permissions"), dict):
                    config["permissions"].update(user_config["permissions"])
                else:
                    config["permissions"] = user_config["permissions"]
            elif key == "audio" and isinstance(user_config["audio"], dict):
                # Nested audio config - merge deeply
                if isinstance(config.get("audio"), dict):
                    config["audio"].update(user_config["audio"])
                else:
                    config["audio"] = user_config["audio"]
            elif key == "paths" and isinstance(user_config["paths"], dict):
                # Nested paths config - merge deeply
                if isinstance(config.get("paths"), dict):
                    config["paths"].update(user_config["paths"])
                else:
                    config["paths"] = user_config["paths"]
            elif key == "record" and isinstance(user_config["record"], dict):
                # Nested record config - merge deeply
                if isinstance(config.get("record"), dict):
                    config["record"].update(user_config["record"])
                else:
                    config["record"] = user_config["record"]
            elif key == "video" and isinstance(user_config["video"], dict):
                # Nested video config - merge deeply
                if isinstance(config.get("video"), dict):
                    config["video"].update(user_config["video"])
                else:
                    config["video"] = user_config["video"]
            elif key == "a11y" and isinstance(user_config["a11y"], dict):
                # Nested a11y config - merge deeply
                if isinstance(config.get("a11y"), dict):
                    config["a11y"].update(user_config["a11y"])
                else:
                    config["a11y"] = user_config["a11y"]
            elif key == "do" and isinstance(user_config["do"], dict):
                # Nested do config - merge deeply
                if isinstance(config.get("do"), dict):
                    config["do"].update(user_config["do"])
                else:
                    config["do"] = user_config["do"]
            elif key == "summarize" and isinstance(user_config["summarize"], dict):
                # Nested summarize config - merge deeply
                if isinstance(config.get("summarize"), dict):
                    config["summarize"].update(user_config["summarize"])
                else:
                    config["summarize"] = user_config["summarize"]
            elif key == "pdf-report" and isinstance(user_config["pdf-report"], dict):
                # Nested pdf-report config - merge deeply
                if isinstance(config.get("pdf-report"), dict):
                    config["pdf-report"].update(user_config["pdf-report"])
                else:
                    config["pdf-report"] = user_config["pdf-report"]
            elif key == "transport" and isinstance(user_config["transport"], dict):
                # Nested transport config - merge deeply
                if isinstance(config.get("transport"), dict):
                    config["transport"].update(user_config["transport"])
                else:
                    config["transport"] = user_config["transport"]
            elif key == "tts" and isinstance(user_config["tts"], dict):
                # Nested TTS config - merge deeply (including voices dict)
                if isinstance(config.get("tts"), dict):
                    # Deep merge: update top-level keys
                    for tts_key, tts_value in user_config["tts"].items():
                        if tts_key == "voices" and isinstance(tts_value, dict):
                            # Merge voices dict (add/update individual voices)
                            if "voices" not in config["tts"]:
                                config["tts"]["voices"] = {}
                            config["tts"]["voices"].update(tts_value)
                        else:
                            config["tts"][tts_key] = tts_value
                else:
                    config["tts"] = user_config["tts"]
            elif key == "tips" and isinstance(user_config["tips"], dict):
                if isinstance(config.get("tips"), dict):
                    config["tips"].update(user_config["tips"])
                else:
                    config["tips"] = user_config["tips"]
            else:
                # Root-level properties like ai-language - overwrite
                config[key] = user_config[key]

        return config
    except (OSError, json.JSONDecodeError):
        # If config file is invalid, fall back to defaults
        # Could log error here if verbose logging is enabled
        return DEFAULT_CONFIG.copy()


def validate_control_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize control configuration.

    Args:
        config: Configuration dictionary

    Returns:
        Validated configuration with normalized values
    """
    control = config.get("control", {})
    validated = {}

    # auto-refocus: "always" | "only-spa" | "never"
    auto_refocus = control.get("auto-refocus", "only-spa")
    if auto_refocus not in ["always", "only-spa", "never"]:
        auto_refocus = "only-spa"
    validated["auto-refocus"] = auto_refocus

    # focus-outline: "custom" | "original" | "none"
    focus_outline = control.get("focus-outline", "custom")
    if focus_outline not in ["custom", "original", "none"]:
        focus_outline = "custom"
    validated["focus-outline"] = focus_outline

    # speak-name: boolean
    validated["speak-name"] = bool(control.get("speak-name", False))

    # speak-all: boolean (speak all terminal output)
    validated["speak-all"] = bool(control.get("speak-all", True))

    # announce-role: boolean
    validated["announce-role"] = bool(control.get("announce-role", False))

    # announce-on-page-load: boolean
    validated["announce-on-page-load"] = bool(control.get("announce-on-page-load", False))

    # navigation-wrap: boolean
    validated["navigation-wrap"] = bool(control.get("navigation-wrap", True))

    # scroll-on-focus: boolean
    validated["scroll-on-focus"] = bool(control.get("scroll-on-focus", True))

    # click-delay: non-negative integer (milliseconds)
    click_delay = control.get("click-delay", 0)
    try:
        click_delay = max(0, int(click_delay))
    except (ValueError, TypeError):
        click_delay = 0
    validated["click-delay"] = click_delay

    # focus-color: string (CSS color)
    validated["focus-color"] = str(control.get("focus-color", "#0066ff"))

    # focus-size: positive integer (pixels)
    focus_size = control.get("focus-size", 3)
    try:
        focus_size = max(1, int(focus_size))
    except (ValueError, TypeError):
        focus_size = 3
    validated["focus-size"] = focus_size

    # focus-animation: boolean
    validated["focus-animation"] = bool(control.get("focus-animation", True))

    # focus-glow: boolean
    validated["focus-glow"] = bool(control.get("focus-glow", True))

    # sound-on-focus: "none" | "beep" | "click" | "subtle"
    sound_on_focus = control.get("sound-on-focus", "none")
    if sound_on_focus not in ["none", "beep", "click", "subtle"]:
        sound_on_focus = "none"
    validated["sound-on-focus"] = sound_on_focus

    # selector-strategy: "id-first" | "aria-first" | "css-first"
    selector_strategy = control.get("selector-strategy", "id-first")
    if selector_strategy not in ["id-first", "aria-first", "css-first"]:
        selector_strategy = "id-first"
    validated["selector-strategy"] = selector_strategy

    # refocus-timeout: positive integer (milliseconds)
    refocus_timeout = control.get("refocus-timeout", 2000)
    try:
        refocus_timeout = max(100, int(refocus_timeout))
    except (ValueError, TypeError):
        refocus_timeout = 2000
    validated["refocus-timeout"] = refocus_timeout

    # verbose: boolean (terminal announcements)
    validated["verbose"] = bool(control.get("verbose", True))

    # verbose-logging: boolean (browser console logging)
    validated["verbose-logging"] = bool(control.get("verbose-logging", False))

    return validated


def get_control_config() -> dict[str, Any]:
    """
    Get validated control configuration.

    Returns:
        Validated control configuration dictionary
    """
    config = load_config()
    return validate_control_config(config)


# Convenience function to check if config file exists
def has_config_file() -> bool:
    """Check if a config file exists."""
    return find_config_file() is not None


# Convenience function to get config file path
def get_config_path() -> str | None:
    """Get the path to the config file being used, if any."""
    config_file = find_config_file()
    return str(config_file) if config_file else None


def validate_ai_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalize AI configuration.

    Supports both legacy flat config and new multi-provider config:

    Legacy (still supported):
        ai:
          endpoint: https://thoth.elevenways.be/v1/chat/completions
          text-model: gpt-4o-mini

    New multi-provider:
        ai:
          default-provider: thoth
          command-defaults:
            summarize: {provider: anthropic, model: claude-3-5-haiku-20241022}
          providers:
            anthropic: {enabled: true, default-text-model: claude-3-5-haiku-20241022}
          fallback-chain: [thoth, openai, anthropic, ollama]

    Args:
        config: Configuration dictionary

    Returns:
        Validated AI configuration with normalized values
    """
    ai_config = config.get("ai", {})
    validated = {}

    # === Legacy config (for backward compatibility with Thoth) ===

    # endpoint: URL string (Thoth endpoint)
    validated["endpoint"] = str(
        ai_config.get("endpoint", "https://thoth.elevenways.be/v1/chat/completions")
    )

    # text-model: model name string
    validated["text-model"] = str(ai_config.get("text-model", "gpt-4o-mini"))

    # vision-model: model name string
    validated["vision-model"] = str(ai_config.get("vision-model", "gpt-4o-mini"))

    # timeout: positive integer (seconds)
    timeout = ai_config.get("timeout", 30)
    try:
        timeout = max(1, int(timeout))
    except (ValueError, TypeError):
        timeout = 30
    validated["timeout"] = timeout

    # max-tokens: positive integer
    max_tokens = ai_config.get("max-tokens", 500)
    try:
        max_tokens = max(1, int(max_tokens))
    except (ValueError, TypeError):
        max_tokens = 500
    validated["max-tokens"] = max_tokens

    # api-key: from environment variable THOTH_API_KEY
    validated["api-key"] = os.environ.get("THOTH_API_KEY", "")

    # === New multi-provider config ===

    # default-provider: which provider to use by default
    validated["default-provider"] = str(ai_config.get("default-provider", "thoth"))

    # command-defaults: per-command provider/model overrides
    # Example: {"summarize": {"provider": "anthropic", "model": "claude-3-5-haiku"}}
    validated["command-defaults"] = ai_config.get("command-defaults", {})

    # providers: per-provider configuration
    # Example: {"anthropic": {"enabled": true, "default-text-model": "…"}}
    validated["providers"] = ai_config.get("providers", {})

    # fallback-chain: order to try providers if primary is unavailable
    fallback = ai_config.get("fallback-chain", ["thoth", "openai", "anthropic", "ollama"])
    if isinstance(fallback, list):
        validated["fallback-chain"] = [str(p) for p in fallback]
    else:
        validated["fallback-chain"] = ["thoth", "openai", "anthropic", "ollama"]

    return validated


def get_ai_config() -> dict[str, Any]:
    """
    Get validated AI configuration.

    Returns:
        Validated AI configuration dictionary with API key from environment
    """
    config = load_config()
    return validate_ai_config(config)


def get_typing_config() -> dict[str, Any]:
    """
    Get typing configuration with validation.

    Returns:
        Typing configuration dictionary with validated values
    """
    config = load_config()
    typing_config = config.get("typing", {})

    # Validate typo rate: must be between 0 and 1
    typo_rate = typing_config.get("human-like-typo-rate", 0.05)
    try:
        typo_rate = float(typo_rate)
        typo_rate = max(0.0, min(1.0, typo_rate))
    except (ValueError, TypeError):
        typo_rate = 0.05

    # Validate skill: must be between 0 and 1 (0 = beginner, 1 = expert)
    skill = typing_config.get("human-like-skill", 0.7)
    try:
        skill = float(skill)
        skill = max(0.0, min(1.0, skill))
    except (ValueError, TypeError):
        skill = 0.7

    return {
        "human-like-typo-rate": typo_rate,
        "human-like-skill": skill,
    }


def get_screenshot_config() -> dict[str, Any]:
    """
    Get screenshot configuration with validation.

    Returns:
        Screenshot configuration dictionary with validated values
    """
    config = load_config()
    screenshot_config = config.get("screenshot", {})

    # Validate optimize: boolean
    optimize = screenshot_config.get("optimize", True)
    optimize = bool(optimize)

    # Validate format: must be png, jpg, or webp
    format_val = screenshot_config.get("format", "png").lower()
    if format_val not in ["png", "jpg", "webp"]:
        format_val = "png"

    # Validate scale: positive integer
    scale = screenshot_config.get("scale", 2)
    try:
        scale = max(1, int(scale))
    except (ValueError, TypeError):
        scale = 2

    # Validate quality: float between 0 and 1
    quality = screenshot_config.get("quality", 0.92)
    try:
        quality = float(quality)
        quality = max(0.0, min(1.0, quality))
    except (ValueError, TypeError):
        quality = 0.92

    # Validate margin: non-negative integer
    margin = screenshot_config.get("margin", 0)
    try:
        margin = max(0, int(margin))
    except (ValueError, TypeError):
        margin = 0

    # Validate margin-color: string
    margin_color = str(screenshot_config.get("margin-color", "auto"))

    return {
        "optimize": optimize,
        "format": format_val,
        "scale": scale,
        "quality": quality,
        "margin": margin,
        "margin-color": margin_color,
    }


def get_html_selection_config() -> dict[str, Any]:
    """
    Get HTML selection configuration with validation.

    Returns:
        HTML selection configuration dictionary with validated values
    """
    config = load_config()
    html_selection_config = config.get("html_selection", {})

    # Validate compact: boolean
    compact = html_selection_config.get("compact", False)
    compact = bool(compact)

    # Validate pretty: boolean
    pretty = html_selection_config.get("pretty", True)
    pretty = bool(pretty)

    # Validate colors: boolean
    colors = html_selection_config.get("colors", True)
    colors = bool(colors)

    # Validate theme: string (validate against Pygments styles if available)
    theme = html_selection_config.get("theme", "monokai")
    theme = str(theme) if theme else "monokai"
    try:
        from pygments.styles import get_style_by_name

        get_style_by_name(theme)
    except Exception:
        # Invalid theme, fall back to monokai
        theme = "monokai"

    # Validate indent: integer between 1-8 spaces (default: 2)
    indent = html_selection_config.get("indent", 2)
    try:
        indent = max(1, min(8, int(indent)))  # Clamp to 1-8
    except (ValueError, TypeError):
        indent = 2

    return {
        "compact": compact,
        "pretty": pretty,
        "colors": colors,
        "theme": theme,
        "indent": indent,
    }


def get_permissions_config() -> dict[str, Any]:
    """
    Get permissions configuration with validation.

    Returns:
        Permissions configuration dictionary with validated values
    """
    config = load_config()
    permissions_config = config.get("permissions", {})

    # Validate allow-local-files: boolean (default True)
    allow_local_files = permissions_config.get("allow-local-files", True)
    allow_local_files = bool(allow_local_files)

    return {
        "allow-local-files": allow_local_files,
    }


def is_nerdfont_enabled() -> bool:
    """
    Check if Nerdfont glyphs are enabled in config.

    Returns:
        True if nerdfont option is enabled, False otherwise
    """
    config = load_config()
    return bool(config.get("nerdfont", False))


def get_paths_config() -> dict[str, Path]:
    """
    Get paths configuration with validation and expansion.

    Expands ~ to home directory and resolves relative paths.

    Returns:
        Dictionary with 'recordings', 'screenshots', 'downloads' as Path objects
    """
    config = load_config()
    paths_config = config.get("paths", {})

    def resolve_path(path_str: str, default: str) -> Path:
        """Resolve a path string to an absolute Path."""
        if not path_str:
            path_str = default

        # Expand ~ to home directory
        path = Path(path_str).expanduser()

        # If relative, resolve to absolute (relative to cwd)
        if not path.is_absolute():
            path = Path.cwd() / path

        return path

    return {
        "recordings": resolve_path(paths_config.get("recordings", "."), "."),
        "screenshots": resolve_path(paths_config.get("screenshots", "."), "."),
        "downloads": resolve_path(paths_config.get("downloads", "~/Downloads"), "~/Downloads"),
    }


def get_audio_config() -> dict[str, Any]:
    """
    Get audio configuration with validation.

    Returns:
        Audio configuration dictionary with validated values:
        - output: "cli" | "browser" | "off"
        - volume: float between 0.0 and 1.0
    """
    config = load_config()
    audio_config = config.get("audio", {})

    # Validate output: must be cli, browser, or off
    output = audio_config.get("output", "cli").lower()
    if output not in ["cli", "browser", "off"]:
        output = "cli"

    # Validate volume: float between 0 and 1
    volume = audio_config.get("volume", 0.5)
    try:
        volume = float(volume)
        volume = max(0.0, min(1.0, volume))
    except (ValueError, TypeError):
        volume = 0.5

    return {
        "output": output,
        "volume": volume,
    }


def get_replay_config() -> dict[str, Any]:
    """
    Get replay configuration with validation.

    Returns:
        Replay configuration dictionary with validated values:
        - validate: bool (whether to run preflight validation)
        - skip-ahead: bool (show skip-ahead prompt for long delays)
        - skip-threshold: int/float (seconds before showing skip prompt)
    """
    config = load_config()
    replay_config = config.get("replay", {})

    # Validate: must be boolean
    validate = replay_config.get("validate", True)
    if not isinstance(validate, bool):
        validate = True

    # Skip-ahead: must be boolean
    skip_ahead = replay_config.get("skip-ahead", True)
    if not isinstance(skip_ahead, bool):
        skip_ahead = True

    # Skip-threshold: must be positive number
    skip_threshold = replay_config.get("skip-threshold", 5)
    if not isinstance(skip_threshold, (int, float)) or skip_threshold < 1:
        skip_threshold = 5

    return {
        "validate": validate,
        "skip-ahead": skip_ahead,
        "skip-threshold": skip_threshold,
    }


def get_record_config() -> dict[str, Any]:
    """
    Get record configuration with validation.

    Returns:
        Record configuration dictionary with validated values:
        - max-actions-per-second: int (rate limit, minimum 1, default 15)
        - synthetic-dialogs: bool (use non-blocking overlays for JS dialogs, default False)
    """
    config = load_config()
    record_config = config.get("record", {})

    # Validate max-actions-per-second: must be positive integer
    max_actions = record_config.get("max-actions-per-second", 15)
    try:
        max_actions = max(1, int(max_actions))
    except (ValueError, TypeError):
        max_actions = 15

    # Validate synthetic-dialogs: must be boolean
    synthetic_dialogs = record_config.get("synthetic-dialogs", False)
    synthetic_dialogs = bool(synthetic_dialogs)

    return {
        "max-actions-per-second": max_actions,
        "synthetic-dialogs": synthetic_dialogs,
    }


def get_video_config() -> dict[str, Any]:
    """
    Get video recording configuration with validation.

    Returns:
        Video configuration dictionary with validated values:
        - fps: int (frame rate, 5-30, default 10)
        - quality: int (JPEG quality, 50-100, default 80)
        - format: str (mp4 or webm, default mp4)
    """
    config = load_config()
    video_config = config.get("video", {})

    # Validate fps: must be between 5 and 30
    fps = video_config.get("fps", 10)
    try:
        fps = max(5, min(30, int(fps)))
    except (ValueError, TypeError):
        fps = 10

    # Validate quality: must be between 50 and 100
    quality = video_config.get("quality", 80)
    try:
        quality = max(50, min(100, int(quality)))
    except (ValueError, TypeError):
        quality = 80

    # Validate format: must be mp4 or webm
    format_val = video_config.get("format", "mp4").lower()
    if format_val not in ["mp4", "webm"]:
        format_val = "mp4"

    return {
        "fps": fps,
        "quality": quality,
        "format": format_val,
    }


def get_a11y_config() -> dict[str, Any]:
    """
    Get accessibility testing configuration with validation.

    Returns:
        A11y configuration dictionary with validated values:
        - show-compliance-warning: bool (show warning about automated checker limitations)
    """
    config = load_config()
    a11y_config = config.get("a11y", {})

    # Validate show-compliance-warning: must be boolean (default True)
    show_warning = a11y_config.get("show-compliance-warning", True)
    show_warning = bool(show_warning)

    return {
        "show-compliance-warning": show_warning,
    }


def get_viewport_offsets() -> dict[str, int] | None:
    """
    Get cached viewport offsets from config file.

    Viewport offsets are the difference between window bounds and actual viewport
    size due to browser chrome (toolbar, scrollbars). Once calibrated, these offsets
    allow instant viewport resizing without trial-and-error.

    Returns:
        Dictionary with 'width' and 'height' offset values, or None if not calibrated.
        Returns None if offsets are invalid (negative or > 1000px).
    """
    config = load_config()
    offsets = config.get("viewport_offsets")

    if offsets and isinstance(offsets, dict):
        width = offsets.get("width")
        height = offsets.get("height")

        # Handle numeric types (int or float) - convert to int
        if isinstance(width, (int, float)) and isinstance(height, (int, float)):
            width = int(width)
            height = int(height)

            # Validate bounds: offsets must be 0-1000px (reasonable browser chrome range)
            if 0 <= width <= 1000 and 0 <= height <= 1000:
                return {"width": width, "height": height}

    return None


def save_viewport_offsets(width_offset: int, height_offset: int) -> bool:
    """
    Save viewport offsets to config file for future use.

    These offsets represent the difference between requested window size and
    actual viewport size (due to browser chrome). Storing them allows instant
    viewport resizing on subsequent runs.

    Args:
        width_offset: Horizontal offset (window_width - viewport_width), must be 0-1000
        height_offset: Vertical offset (window_height - viewport_height), must be 0-1000

    Returns:
        True if saved successfully, False otherwise (invalid values, permission error, etc.)
    """
    import shutil
    import tempfile

    # Type validation: convert to int if numeric
    try:
        width_offset = int(width_offset)
        height_offset = int(height_offset)
    except (ValueError, TypeError):
        return False  # Non-numeric values

    # Bounds validation: offsets must be 0-1000px (reasonable browser chrome range)
    # Negative offsets are invalid (would mean viewport > window, impossible)
    # Offsets > 1000px suggest corrupted data
    if not (0 <= width_offset <= 1000) or not (0 <= height_offset <= 1000):
        return False

    # Find existing config file or determine where to create one
    config_file = find_config_file()

    if config_file is None:
        # Create in XDG Base Directory standard location
        config_file = Path.home() / ".config" / "inspekt.json"
        try:
            config_file.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False  # Cannot create directory

    # Verify parent directory is writable
    if not os.access(config_file.parent, os.W_OK):
        return False

    # Load existing config or start fresh
    config: dict[str, Any] = {}
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError):
            # If existing config is corrupted, start fresh but preserve what we can
            config = {}

    # Update viewport offsets
    config["viewport_offsets"] = {
        "width": width_offset,
        "height": height_offset,
    }

    # Atomic write: write to temp file, then rename
    # This prevents data loss if write is interrupted (disk full, crash, etc.)
    try:
        # Create temp file in same directory (required for atomic rename on same filesystem)
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=config_file.parent,
            suffix=".tmp",
            delete=False,
        ) as f:
            json.dump(config, f, indent=2)
            temp_path = Path(f.name)

        # Atomic rename (on POSIX systems, this is guaranteed atomic)
        shutil.move(str(temp_path), str(config_file))
        return True
    except OSError:
        # Clean up temp file if it exists
        try:
            if temp_path.exists():
                temp_path.unlink()
        except (OSError, NameError):
            pass
        return False


def get_do_config() -> dict[str, Any]:
    """
    Get `inspekt do` command configuration with validation.

    Returns:
        Do command configuration dictionary with validated values:
        - synonyms-file: Optional path to custom synonyms YAML file
        - literal-match-threshold: float (0.0-1.0, default 0.8)
        - substring-match-threshold: float (0.0-1.0, default 0.5)
        - use-fuzzy-matching: bool (default True)
        - max-fuzzy-distance: int (default 2)
    """
    config = load_config()
    do_config = config.get("do", {})

    # synonyms-file: optional path string
    synonyms_file = do_config.get("synonyms-file")
    if synonyms_file is not None:
        # Expand ~ and resolve path
        synonyms_file = str(Path(synonyms_file).expanduser())

    # literal-match-threshold: float between 0 and 1
    literal_threshold = do_config.get("literal-match-threshold", 0.8)
    try:
        literal_threshold = max(0.0, min(1.0, float(literal_threshold)))
    except (ValueError, TypeError):
        literal_threshold = 0.8

    # substring-match-threshold: float between 0 and 1
    substring_threshold = do_config.get("substring-match-threshold", 0.5)
    try:
        substring_threshold = max(0.0, min(1.0, float(substring_threshold)))
    except (ValueError, TypeError):
        substring_threshold = 0.5

    # use-fuzzy-matching: boolean
    use_fuzzy = do_config.get("use-fuzzy-matching", True)
    use_fuzzy = bool(use_fuzzy)

    # max-fuzzy-distance: positive integer
    max_distance = do_config.get("max-fuzzy-distance", 2)
    try:
        max_distance = max(1, int(max_distance))
    except (ValueError, TypeError):
        max_distance = 2

    return {
        "synonyms-file": synonyms_file,
        "literal-match-threshold": literal_threshold,
        "substring-match-threshold": substring_threshold,
        "use-fuzzy-matching": use_fuzzy,
        "max-fuzzy-distance": max_distance,
    }


def get_summarize_config() -> dict[str, Any]:
    """
    Get `inspekt summarize` command configuration with validation.

    Returns:
        Summarize command configuration dictionary with validated values:
        - extractor: "readability" (Mozilla Readability) or "custom" (built-in lightweight)
    """
    config = load_config()
    summarize_config = config.get("summarize", {})

    # extractor: must be "readability" or "custom"
    extractor = summarize_config.get("extractor", "readability").lower()
    if extractor not in ["readability", "custom"]:
        extractor = "readability"

    return {
        "extractor": extractor,
    }


def get_extract_config() -> dict[str, Any]:
    """
    Get `inspekt extract` command configuration with validation.

    Returns:
        Extract command configuration dictionary with validated values:
        - engine: "readability" (Mozilla Readability) or "defuddle" (Obsidian's modern extractor)
    """
    config = load_config()
    extract_config = config.get("extract", {})

    # engine: must be "readability" or "defuddle"
    engine = extract_config.get("engine", "readability").lower()
    if engine not in ["readability", "defuddle"]:
        engine = "readability"

    return {
        "engine": engine,
    }


def get_tts_config() -> dict[str, Any]:
    """
    Get TTS (text-to-speech) configuration with validation.

    Returns:
        TTS configuration dictionary with validated values:
        - default-voice: name of the default voice to use
        - voices: dictionary of voice configurations
        - api-key: ElevenLabs API key from environment variable

    Voice configuration includes:
        - voice-id: ElevenLabs voice ID
        - language-code: ISO 639-1 language code
        - model-id: ElevenLabs model (e.g., eleven_v3)
        - output-format: Audio format (e.g., mp3_44100_192)
        - voice-settings: stability, similarity-boost, style, use-speaker-boost
    """
    config = load_config()
    tts_config = config.get("tts", {})

    # Get API key from environment variable
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")

    # default-voice: string (defaults to "margot")
    default_voice = tts_config.get("default-voice", "margot")

    # voices: dictionary of voice configurations
    voices = tts_config.get("voices", {})

    # Validate each voice configuration
    validated_voices = {}
    for voice_name, voice_config in voices.items():
        if not isinstance(voice_config, dict):
            continue

        # Required: voice-id
        voice_id = voice_config.get("voice-id")
        if not voice_id:
            continue

        # Optional settings with defaults
        validated_voice = {
            "voice-id": str(voice_id),
            "language-code": str(voice_config.get("language-code", "en")),
            "model-id": str(voice_config.get("model-id", "eleven_v3")),
            "output-format": str(voice_config.get("output-format", "mp3_44100_192")),
        }

        # Voice settings with defaults matching ElevenLabs defaults
        voice_settings = voice_config.get("voice-settings", {})
        if isinstance(voice_settings, dict):
            # stability: float 0-1
            stability = voice_settings.get("stability", 0.5)
            try:
                stability = max(0.0, min(1.0, float(stability)))
            except (ValueError, TypeError):
                stability = 0.5

            # similarity-boost: float 0-1
            similarity_boost = voice_settings.get("similarity-boost", 0.75)
            try:
                similarity_boost = max(0.0, min(1.0, float(similarity_boost)))
            except (ValueError, TypeError):
                similarity_boost = 0.75

            # style: float 0-1
            style = voice_settings.get("style", 0)
            try:
                style = max(0.0, min(1.0, float(style)))
            except (ValueError, TypeError):
                style = 0

            # use-speaker-boost: boolean
            use_speaker_boost = bool(voice_settings.get("use-speaker-boost", False))

            validated_voice["voice-settings"] = {
                "stability": stability,
                "similarity-boost": similarity_boost,
                "style": style,
                "use-speaker-boost": use_speaker_boost,
            }
        else:
            validated_voice["voice-settings"] = {
                "stability": 0.5,
                "similarity-boost": 0.75,
                "style": 0,
                "use-speaker-boost": False,
            }

        validated_voices[voice_name.lower()] = validated_voice

    return {
        "default-voice": default_voice,
        "voices": validated_voices,
        "api-key": api_key,
    }


def get_tts_voice(voice_name: str | None = None) -> dict[str, Any] | None:
    """
    Get configuration for a specific TTS voice.

    Args:
        voice_name: Name of the voice to get. If None, uses default voice.

    Returns:
        Voice configuration dictionary or None if voice not found.
    """
    tts_config = get_tts_config()

    if voice_name is None:
        voice_name = tts_config.get("default-voice", "margot")

    voice_name = voice_name.lower()
    voices = tts_config.get("voices", {})

    if voice_name not in voices:
        return None

    voice = voices[voice_name].copy()
    voice["api-key"] = tts_config.get("api-key", "")
    return voice


def get_transport_config() -> dict[str, Any]:
    """
    Get transport configuration with validation.

    Supports environment variable overrides:
        - INSPEKT_TRANSPORT: Force transport type ("auto", "unix", "tcp", "http")
        - INSPEKT_SOCKET_PATH: Override socket path

    Returns:
        Transport configuration dictionary with validated values:
        - type: "auto" | "unix" | "tcp" | "http"
        - socket-path: Optional path override (None = use default)
        - auto-start: bool (auto-start server if not running)
        - connect-timeout: float (seconds)
        - max-retries: int (retries when auto-starting)
        - retry-delay: float (seconds between retries)
    """
    config = load_config()
    transport_config = config.get("transport", {})

    # The "type" key must be one of the valid transport types
    # Environment variable takes precedence
    transport_type = os.environ.get("INSPEKT_TRANSPORT")
    if transport_type is None:
        transport_type = transport_config.get("type", "auto")
    transport_type = str(transport_type).lower()
    if transport_type not in ["auto", "unix", "tcp", "http"]:
        transport_type = "auto"

    # socket-path: optional path override
    # Environment variable takes precedence
    socket_path = os.environ.get("INSPEKT_SOCKET_PATH")
    if socket_path is None:
        socket_path = transport_config.get("socket-path")
    # Expand ~ if a path is provided
    if socket_path:
        socket_path = str(Path(socket_path).expanduser())

    # auto-start: boolean (default False for safety)
    auto_start = transport_config.get("auto-start", False)
    auto_start = bool(auto_start)

    # connect-timeout: positive float (seconds)
    connect_timeout = transport_config.get("connect-timeout", 5.0)
    try:
        connect_timeout = max(0.1, float(connect_timeout))
    except (ValueError, TypeError):
        connect_timeout = 5.0

    # max-retries: positive integer
    max_retries = transport_config.get("max-retries", 50)
    try:
        max_retries = max(1, int(max_retries))
    except (ValueError, TypeError):
        max_retries = 50

    # retry-delay: positive float (seconds)
    retry_delay = transport_config.get("retry-delay", 0.1)
    try:
        retry_delay = max(0.01, float(retry_delay))
    except (ValueError, TypeError):
        retry_delay = 0.1

    return {
        "type": transport_type,
        "socket-path": socket_path,
        "auto-start": auto_start,
        "connect-timeout": connect_timeout,
        "max-retries": max_retries,
        "retry-delay": retry_delay,
    }


def get_pdf_report_config() -> dict[str, Any]:
    """
    Get PDF report configuration with validation.

    Returns:
        PDF report configuration dictionary with validated values:
        - show-cover-page: bool (include first page preview)
        - show-issue-screenshots: bool (capture issue location screenshots)
        - show-metadata: bool (show enhanced document metadata)
        - show-text-discrepancy-section: bool (compare text layer vs OCR)
        - cover-max-height: int (max height in pixels for cover preview)
        - issue-screenshot-dpi: int (DPI for issue screenshots, 72-300)
        - max-issues-per-rule: int (max screenshots per rule type)
        - text-discrepancy-threshold: float (0.0-1.0, triggers warning)
        - max-ocr-pages: int (limit OCR processing for large documents)
    """
    config = load_config()
    pdf_report_config = config.get("pdf-report", {})

    # show-cover-page: boolean (default True)
    show_cover_page = pdf_report_config.get("show-cover-page", True)
    show_cover_page = bool(show_cover_page)

    # show-issue-screenshots: boolean (default True)
    show_issue_screenshots = pdf_report_config.get("show-issue-screenshots", True)
    show_issue_screenshots = bool(show_issue_screenshots)

    # show-metadata: boolean (default True)
    show_metadata = pdf_report_config.get("show-metadata", True)
    show_metadata = bool(show_metadata)

    # show-text-discrepancy-section: boolean (default True)
    show_text_discrepancy_section = pdf_report_config.get("show-text-discrepancy-section", True)
    show_text_discrepancy_section = bool(show_text_discrepancy_section)

    # cover-max-height: positive integer (default 400)
    cover_max_height = pdf_report_config.get("cover-max-height", 400)
    try:
        cover_max_height = max(100, min(1200, int(cover_max_height)))
    except (ValueError, TypeError):
        cover_max_height = 400

    # issue-screenshot-dpi: integer between 72 and 300 (default 150)
    issue_screenshot_dpi = pdf_report_config.get("issue-screenshot-dpi", 150)
    try:
        issue_screenshot_dpi = max(72, min(300, int(issue_screenshot_dpi)))
    except (ValueError, TypeError):
        issue_screenshot_dpi = 150

    # max-issues-per-rule: positive integer (default 1)
    max_issues_per_rule = pdf_report_config.get("max-issues-per-rule", 1)
    try:
        max_issues_per_rule = max(1, min(10, int(max_issues_per_rule)))
    except (ValueError, TypeError):
        max_issues_per_rule = 1

    # text-discrepancy-threshold: float between 0 and 1 (default 0.10)
    text_discrepancy_threshold = pdf_report_config.get("text-discrepancy-threshold", 0.10)
    try:
        text_discrepancy_threshold = max(0.0, min(1.0, float(text_discrepancy_threshold)))
    except (ValueError, TypeError):
        text_discrepancy_threshold = 0.10

    # max-ocr-pages: positive integer (default 50)
    max_ocr_pages = pdf_report_config.get("max-ocr-pages", 50)
    try:
        max_ocr_pages = max(1, min(500, int(max_ocr_pages)))
    except (ValueError, TypeError):
        max_ocr_pages = 50

    # ocr-analyze-all: boolean (default False)
    ocr_analyze_all = pdf_report_config.get("ocr-analyze-all", False)
    ocr_analyze_all = bool(ocr_analyze_all)

    # ocr-include-thumbnails: boolean (default True)
    ocr_include_thumbnails = pdf_report_config.get("ocr-include-thumbnails", True)
    ocr_include_thumbnails = bool(ocr_include_thumbnails)

    return {
        "show-cover-page": show_cover_page,
        "show-issue-screenshots": show_issue_screenshots,
        "show-metadata": show_metadata,
        "show-text-discrepancy-section": show_text_discrepancy_section,
        "cover-max-height": cover_max_height,
        "issue-screenshot-dpi": issue_screenshot_dpi,
        "max-issues-per-rule": max_issues_per_rule,
        "text-discrepancy-threshold": text_discrepancy_threshold,
        "max-ocr-pages": max_ocr_pages,
        "ocr-analyze-all": ocr_analyze_all,
        "ocr-include-thumbnails": ocr_include_thumbnails,
    }
