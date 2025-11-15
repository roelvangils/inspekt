"""Configuration management for Inspekt."""

import json
import os
from pathlib import Path
from typing import Any

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
}


def find_config_file() -> Path | None:
    """
    Find the config.json file.

    Searches in order:
    1. Current directory (project root)
    2. ~/.inspekt/config.json

    Returns:
        Path to config file if found, None otherwise
    """
    # Check current directory
    local_config = Path("config.json")
    if local_config.exists():
        return local_config

    # Check ~/.inspekt/
    home_config = Path.home() / ".inspekt" / "config.json"
    if home_config.exists():
        return home_config

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
            elif key == "ai" and isinstance(user_config["ai"], dict):
                # Nested AI config - merge deeply
                if isinstance(config.get("ai"), dict):
                    config["ai"].update(user_config["ai"])
                else:
                    config["ai"] = user_config["ai"]
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
