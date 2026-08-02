"""
OpenAI AI Provider - GPT models.

Supports GPT-4, GPT-4o, GPT-3.5 Turbo, and other OpenAI models
via the OpenAI API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from inspekt.services.ai_providers.base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)

# Try to import openai package
try:
    import openai

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenAIProvider(AIProvider):
    """
    OpenAI AI provider (GPT models).

    Configuration:
        Environment variables:
            - OPENAI_API_KEY: API key for authentication

        Config file (config.json):
            - ai.providers.openai.default-text-model: Default text model
            - ai.providers.openai.default-vision-model: Default vision model
    """

    # Default models
    DEFAULT_TEXT_MODEL = "gpt-4o-mini"
    DEFAULT_VISION_MODEL = "gpt-4o-mini"

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the OpenAI provider.

        Args:
            config: AI configuration dict
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "The 'openai' package is not installed. Install it with: pip install openai"
            )

        self._config = config or {}
        self._provider_config = self._config.get("providers", {}).get("openai", {})
        self._client: openai.OpenAI | None = None

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        """Check if OpenAI is configured with an API key."""
        return OPENAI_AVAILABLE and bool(self._get_api_key())

    def _get_api_key(self) -> str | None:
        """Get the OpenAI API key from environment."""
        return os.environ.get("OPENAI_API_KEY")

    def _get_client(self) -> openai.OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            api_key = self._get_api_key()
            if not api_key:
                raise AIProviderError(
                    "OPENAI_API_KEY environment variable not set",
                    provider=self.name,
                )
            self._client = openai.OpenAI(api_key=api_key)
        return self._client

    def get_default_text_model(self) -> str:
        return self._provider_config.get("default-text-model", self.DEFAULT_TEXT_MODEL)

    def get_default_vision_model(self) -> str:
        return self._provider_config.get("default-vision-model", self.DEFAULT_VISION_MODEL)

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
        Generate text using GPT.

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
            response = client.chat.completions.create(
                model=use_model,
                max_tokens=use_max_tokens,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
            )

            content = response.choices[0].message.content or ""
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return AIResponse(
                content=content,
                model=use_model,
                provider=self.name,
                usage=usage,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except openai.APITimeoutError:
            raise AIProviderError(
                "API request timed out",
                provider=self.name,
            )
        except openai.APIStatusError as e:
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
        Generate text from an image using GPT-4 Vision.

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

        try:
            response = client.chat.completions.create(
                model=use_model,
                max_tokens=use_max_tokens,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": image_data_url,
                                    "detail": "low",
                                },
                            },
                        ],
                    }
                ],
                timeout=timeout,
            )

            content = response.choices[0].message.content or ""
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }

            return AIResponse(
                content=content,
                model=use_model,
                provider=self.name,
                usage=usage,
                raw_response=response.model_dump() if hasattr(response, "model_dump") else None,
            )

        except openai.APITimeoutError:
            raise AIProviderError(
                "Vision API request timed out",
                provider=self.name,
            )
        except openai.APIStatusError as e:
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
