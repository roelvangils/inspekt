"""
Provider Manager - handles provider selection, configuration, and fallback.

This is the main entry point for AI operations. It:
- Loads provider configurations from config.json
- Selects the appropriate provider based on command, config, or override
- Handles fallback when a provider is unavailable
- Provides a unified interface for text and vision generation
"""

from __future__ import annotations

import logging
import os
from typing import Any

from inspekt.services.ai_providers.base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)


class ProviderManager:
    """
    Manages AI providers and handles provider selection/fallback.

    Usage:
        manager = get_provider_manager()

        # Use default provider
        response = manager.call_text("Summarize this text")

        # Use specific provider
        response = manager.call_text("Summarize", provider="anthropic")

        # Use command-specific defaults
        response = manager.call_text("Summarize", command="summarize")
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the provider manager.

        Args:
            config: AI configuration dict (loaded from config.json if None)
        """
        self._providers: dict[str, AIProvider] = {}
        self._config = config or self._load_config()
        self._load_providers()

    def _load_config(self) -> dict[str, Any]:
        """Load AI configuration from config.json."""
        from inspekt import config as inspekt_config

        return inspekt_config.get_ai_config()

    def _load_providers(self) -> None:
        """Load and register all available providers."""
        # Import providers lazily to avoid circular imports
        from inspekt.services.ai_providers.thoth import ThothProvider

        # Register Thoth provider (always available as default)
        thoth = ThothProvider(self._config)
        self._providers["thoth"] = thoth

        # Try to load optional providers
        try:
            from inspekt.services.ai_providers.anthropic import AnthropicProvider

            self._providers["anthropic"] = AnthropicProvider(self._config)
        except ImportError:
            logger.debug("Anthropic provider not available (missing anthropic package)")

        try:
            from inspekt.services.ai_providers.openai import OpenAIProvider

            self._providers["openai"] = OpenAIProvider(self._config)
        except ImportError:
            logger.debug("OpenAI provider not available (missing openai package)")

        try:
            from inspekt.services.ai_providers.ollama import OllamaProvider

            self._providers["ollama"] = OllamaProvider(self._config)
        except ImportError:
            logger.debug("Ollama provider not available")

    @property
    def default_provider(self) -> str:
        """Get the default provider name from config or environment."""
        # Environment variable has highest priority
        if env_provider := os.environ.get("INSPEKT_AI_PROVIDER"):
            return env_provider

        # Then config file
        return self._config.get("default-provider", "thoth")

    @property
    def fallback_chain(self) -> list[str]:
        """Get the fallback chain for provider selection."""
        return self._config.get(
            "fallback-chain", ["thoth", "openai", "anthropic", "ollama"]
        )

    def get_provider(self, name: str) -> AIProvider | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def list_available_providers(self) -> list[str]:
        """List providers that are currently available (configured with API keys)."""
        return [name for name, provider in self._providers.items() if provider.is_available()]

    def get_command_defaults(self, command: str) -> dict[str, Any]:
        """
        Get default provider/model for a specific command.

        Args:
            command: Command name (e.g., "summarize", "describe", "ask")

        Returns:
            Dict with provider and model defaults for this command
        """
        defaults = self._config.get("command-defaults", {})
        return defaults.get(command, {})

    def resolve_provider(
        self,
        provider: str | None = None,
        command: str | None = None,
    ) -> tuple[AIProvider, str]:
        """
        Resolve which provider to use based on overrides and config.

        Priority:
        1. Explicit provider parameter
        2. Command-specific default
        3. Global default provider
        4. First available from fallback chain

        Args:
            provider: Explicit provider name override
            command: Command name for command-specific defaults

        Returns:
            Tuple of (provider instance, resolved model name)

        Raises:
            AIProviderError: If no available provider found
        """
        resolved_model = None

        # 1. Explicit provider override
        if provider:
            if p := self.get_provider(provider):
                if p.is_available():
                    return p, resolved_model or p.get_default_text_model()
                raise AIProviderError(
                    f"Provider '{provider}' is not available (missing API key?)",
                    provider=provider,
                )
            raise AIProviderError(
                f"Unknown provider: '{provider}'",
                provider=provider,
            )

        # 2. Command-specific defaults
        if command:
            cmd_defaults = self.get_command_defaults(command)
            if cmd_provider := cmd_defaults.get("provider"):
                if p := self.get_provider(cmd_provider):
                    if p.is_available():
                        resolved_model = cmd_defaults.get("model")
                        return p, resolved_model or p.get_default_text_model()

        # 3. Global default
        default = self.default_provider
        if p := self.get_provider(default):
            if p.is_available():
                return p, p.get_default_text_model()

        # 4. Fallback chain
        for name in self.fallback_chain:
            if p := self.get_provider(name):
                if p.is_available():
                    logger.info(f"Using fallback provider: {name}")
                    return p, p.get_default_text_model()

        # No provider available
        available = self.list_available_providers()
        raise AIProviderError(
            f"No AI provider available. Checked: {self.fallback_chain}. "
            f"Available: {available or 'none'}. "
            "Please configure an API key (THOTH_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY)."
        )

    def call_text(
        self,
        prompt: str,
        provider: str | None = None,
        model: str | None = None,
        command: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """
        Generate text using the resolved provider.

        Args:
            prompt: Input prompt
            provider: Explicit provider override
            model: Explicit model override
            command: Command name for default resolution
            max_tokens: Max tokens to generate
            timeout: Request timeout
            **kwargs: Provider-specific options

        Returns:
            AIResponse with generated content
        """
        resolved_provider, default_model = self.resolve_provider(provider, command)
        use_model = model or default_model

        # Get command-specific defaults if not explicitly set
        if command and not model:
            cmd_defaults = self.get_command_defaults(command)
            use_model = cmd_defaults.get("model") or use_model

        return resolved_provider.call_text(
            prompt=prompt,
            model=use_model,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs,
        )

    def call_vision(
        self,
        prompt: str,
        image_data_url: str,
        provider: str | None = None,
        model: str | None = None,
        command: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """
        Generate text from image using the resolved provider.

        Args:
            prompt: Input prompt
            image_data_url: Base64-encoded image data URL
            provider: Explicit provider override
            model: Explicit model override
            command: Command name for default resolution
            max_tokens: Max tokens to generate
            timeout: Request timeout
            **kwargs: Provider-specific options

        Returns:
            AIResponse with generated content
        """
        resolved_provider, _ = self.resolve_provider(provider, command)
        # Use vision-specific default model, not text model
        use_model = model or resolved_provider.get_default_vision_model()

        if not resolved_provider.supports_vision():
            raise AIProviderError(
                f"Provider '{resolved_provider.name}' does not support vision",
                provider=resolved_provider.name,
            )

        return resolved_provider.call_vision(
            prompt=prompt,
            image_data_url=image_data_url,
            model=use_model,
            max_tokens=max_tokens,
            timeout=timeout,
            **kwargs,
        )


# Global manager instance (lazy-initialized)
_manager: ProviderManager | None = None


def get_provider_manager() -> ProviderManager:
    """Get the global provider manager instance (singleton)."""
    global _manager
    if _manager is None:
        _manager = ProviderManager()
    return _manager
