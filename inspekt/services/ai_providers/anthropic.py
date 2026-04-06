"""
Anthropic AI Provider - Claude models.

Supports Claude 3.5 Sonnet, Claude 3 Haiku, and other Claude models
via the Anthropic API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from inspekt.services.ai_providers.base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)

# Try to import anthropic package
try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class AnthropicProvider(AIProvider):
    """
    Anthropic AI provider (Claude models).

    Configuration:
        Environment variables:
            - ANTHROPIC_API_KEY: API key for authentication

        Config file (config.json):
            - ai.providers.anthropic.default-text-model: Default text model
            - ai.providers.anthropic.default-vision-model: Default vision model
    """

    # Default models
    DEFAULT_TEXT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_VISION_MODEL = "claude-sonnet-4-20250514"

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the Anthropic provider.

        Args:
            config: AI configuration dict
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "The 'anthropic' package is not installed. "
                "Install it with: pip install anthropic"
            )

        self._config = config or {}
        self._provider_config = self._config.get("providers", {}).get("anthropic", {})
        self._client: anthropic.Anthropic | None = None

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        """Check if Anthropic is configured with an API key."""
        return ANTHROPIC_AVAILABLE and bool(self._get_api_key())

    def _get_api_key(self) -> str | None:
        """Get the Anthropic API key from environment."""
        return os.environ.get("ANTHROPIC_API_KEY")

    def _get_client(self) -> anthropic.Anthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            api_key = self._get_api_key()
            if not api_key:
                raise AIProviderError(
                    "ANTHROPIC_API_KEY environment variable not set",
                    provider=self.name,
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def get_default_text_model(self) -> str:
        return self._provider_config.get("default-text-model", self.DEFAULT_TEXT_MODEL)

    def get_default_vision_model(self) -> str:
        return self._provider_config.get(
            "default-vision-model", self.DEFAULT_VISION_MODEL
        )

    def supports_vision(self) -> bool:
        return True

    def call_text(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """
        Generate text using Claude.

        Args:
            prompt: Input text prompt
            model: Model to use (default from config)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Additional options

        Returns:
            AIResponse with generated content
        """
        client = self._get_client()
        use_model = model or self.get_default_text_model()
        use_max_tokens = max_tokens or self._config.get("max-tokens", 1024)

        try:
            message = client.messages.create(
                model=use_model,
                max_tokens=use_max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

            content = message.content[0].text if message.content else ""
            usage = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            }

            return AIResponse(
                content=content,
                model=use_model,
                provider=self.name,
                usage=usage,
                raw_response=message.model_dump() if hasattr(message, "model_dump") else None,
            )

        except anthropic.APITimeoutError:
            raise AIProviderError(
                f"API request timed out",
                provider=self.name,
            )
        except anthropic.APIStatusError as e:
            raise AIProviderError(
                f"API error: {e.message}",
                provider=self.name,
                status_code=e.status_code,
            )
        except Exception as e:
            raise AIProviderError(
                f"Unexpected error: {e}",
                provider=self.name,
            )

    def call_vision(
        self,
        prompt: str,
        image_data_url: str,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """
        Generate text from an image using Claude.

        Args:
            prompt: Text prompt describing the analysis
            image_data_url: Base64-encoded image (data:image/...;base64,...)
            model: Vision model to use
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Additional options

        Returns:
            AIResponse with generated content
        """
        client = self._get_client()
        use_model = model or self.get_default_vision_model()
        use_max_tokens = max_tokens or self._config.get("max-tokens", 1024)

        # Parse data URL
        if ";base64," in image_data_url:
            media_type_part, base64_data = image_data_url.split(";base64,")
            media_type = media_type_part.replace("data:", "")
        else:
            raise AIProviderError(
                "Invalid image data URL format",
                provider=self.name,
            )

        try:
            message = client.messages.create(
                model=use_model,
                max_tokens=use_max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": base64_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            content = message.content[0].text if message.content else ""
            usage = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            }

            return AIResponse(
                content=content,
                model=use_model,
                provider=self.name,
                usage=usage,
                raw_response=message.model_dump() if hasattr(message, "model_dump") else None,
            )

        except anthropic.APITimeoutError:
            raise AIProviderError(
                f"Vision API request timed out",
                provider=self.name,
            )
        except anthropic.APIStatusError as e:
            raise AIProviderError(
                f"Vision API error: {e.message}",
                provider=self.name,
                status_code=e.status_code,
            )
        except Exception as e:
            raise AIProviderError(
                f"Unexpected error: {e}",
                provider=self.name,
            )
