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
    "audio": {
        "output": "cli",  # "cli" (Python/system audio) | "browser" (Web Audio) | "off"
        "volume": 0.5,  # 0.0 to 1.0
    },
    "nerdfont": False,  # Enable Nerdfont glyphs in terminal output
    "permissions": {
        "allow-local-files": True,  # Allow file:// URLs without adding to domain list
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
    # Check current directory
    local_config = Path("config.json")
    if local_config.exists():
        return local_config

    # Check ~/.config/inspekt.json (XDG Base Directory standard)
    xdg_config = Path.home() / ".config" / "inspekt.json"
    if xdg_config.exists():
        return xdg_config

    # Check ~/.inspekt/config.json (legacy path for backward compatibility)
    legacy_config = Path.home() / ".inspekt" / "config.json"
    if legacy_config.exists():
        return legacy_config

    return None


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

    Args:
        config: Configuration dictionary

    Returns:
        Validated AI configuration with normalized values
    """
    ai_config = config.get("ai", {})
    validated = {}

    # endpoint: URL string
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
        # Clamp between 0 and 1
        typo_rate = max(0.0, min(1.0, typo_rate))
    except (ValueError, TypeError):
        typo_rate = 0.05

    return {
        "human-like-typo-rate": typo_rate,
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
        HTML selection configuration dictionary with validated boolean values
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

    # Validate theme: string
    theme = html_selection_config.get("theme", "monokai")
    theme = str(theme) if theme else "monokai"

    return {
        "compact": compact,
        "pretty": pretty,
        "colors": colors,
        "theme": theme,
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
        "recordings": resolve_path(
            paths_config.get("recordings", "."), "."
        ),
        "screenshots": resolve_path(
            paths_config.get("screenshots", "."), "."
        ),
        "downloads": resolve_path(
            paths_config.get("downloads", "~/Downloads"), "~/Downloads"
        ),
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
