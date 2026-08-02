"""
Thoth AI Provider - OpenAI-compatible API.

Thoth is a custom AI gateway that supports multiple backends
while providing an OpenAI-compatible API interface.

This is the default provider for Inspekt.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from inspekt.services import http_client
from inspekt.services.ai_providers.base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)


class ThothProvider(AIProvider):
    """
    Thoth AI provider (OpenAI-compatible API).

    Configuration:
        Environment variables:
            - THOTH_API_KEY: API key for authentication

        Config file (config.json):
            - ai.endpoint: API endpoint URL
            - ai.text-model: Default text model
            - ai.vision-model: Default vision model
            - ai.timeout: Request timeout in seconds
            - ai.max-tokens: Default max tokens
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the Thoth provider.

        Args:
            config: AI configuration dict
        """
        self._config = config or {}

    @property
    def name(self) -> str:
        return "thoth"

    def is_available(self) -> bool:
        """Check if Thoth is configured with an API key."""
        return bool(self._get_api_key())

    def _get_api_key(self) -> str | None:
        """Get the Thoth API key from environment or config."""
        # Environment variable has priority
        if key := os.environ.get("THOTH_API_KEY"):
            return key

        # Fall back to config
        return self._config.get("api-key")

    def _get_endpoint(self) -> str:
        """Get the Thoth API endpoint."""
        return self._config.get("endpoint", "https://thoth.elevenways.be/v1/chat/completions")

    def get_default_text_model(self) -> str:
        return self._config.get("text-model", "gpt-4o-mini")

    def get_default_vision_model(self) -> str:
        return self._config.get("vision-model", "claude-sonnet-4-20250514")

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
        Generate text using Thoth API.

        Args:
            prompt: Input text prompt
            model: Model to use (default from config)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Additional options (ignored)

        Returns:
            AIResponse with generated content
        """
        api_key = self._get_api_key()
        if not api_key:
            raise AIProviderError(
                "THOTH_API_KEY environment variable not set. "
                "Please set your Thoth API key to use AI features.",
                provider=self.name,
            )

        use_model = model or self.get_default_text_model()
        use_timeout = timeout or self._config.get("timeout", 30)
        use_max_tokens = max_tokens or self._config.get("max-tokens", 500)
        endpoint = self._get_endpoint()

        try:
            response = http_client.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": use_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": use_max_tokens,
                },
                timeout=use_timeout,
            )

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"].strip()
                    usage = result.get("usage")

                    return AIResponse(
                        content=content,
                        model=use_model,
                        provider=self.name,
                        usage=usage,
                        raw_response=result,
                    )
                else:
                    raise AIProviderError(
                        f"Unexpected API response format: {result}",
                        provider=self.name,
                        response=result,
                    )
            else:
                error_body = None
                try:
                    error_body = response.json()
                except Exception:
                    pass

                raise AIProviderError(
                    f"Thoth API returned status {response.status_code}",
                    provider=self.name,
                    status_code=response.status_code,
                    response=error_body,
                )

        except requests.Timeout:
            raise AIProviderError(
                f"API request timed out after {use_timeout} seconds",
                provider=self.name,
            )
        except requests.RequestException as e:
            raise AIProviderError(
                f"API request failed: {e}",
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
        Generate text from an image using Thoth API.

        Args:
            prompt: Text prompt describing the analysis
            image_data_url: Base64-encoded image (data:image/...;base64,...)
            model: Vision model to use
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Additional options (ignored)

        Returns:
            AIResponse with generated content
        """
        api_key = self._get_api_key()
        if not api_key:
            raise AIProviderError(
                "THOTH_API_KEY environment variable not set",
                provider=self.name,
            )

        use_model = model or self.get_default_vision_model()
        use_timeout = timeout or self._config.get("timeout", 60)
        use_max_tokens = max_tokens or self._config.get("max-tokens", 1024)
        endpoint = self._get_endpoint()

        # Extract base64 data from data URL
        if ";base64," in image_data_url:
            base64_data = image_data_url.split(";base64,")[1]
        else:
            raise AIProviderError(
                "Invalid image data URL format (expected data:image/...;base64,...)",
                provider=self.name,
            )

        try:
            response = http_client.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json={
                    "model": use_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_data}",
                                        "detail": "auto",  # Let the model decide based on image size
                                    },
                                },
                            ],
                        }
                    ],
                    "max_tokens": use_max_tokens,
                },
                timeout=use_timeout,
            )

            if response.status_code == 200:
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"].strip()
                    usage = result.get("usage")
                    logger.debug(f"Vision response: {len(content)} chars")

                    return AIResponse(
                        content=content,
                        model=use_model,
                        provider=self.name,
                        usage=usage,
                        raw_response=result,
                    )
                else:
                    raise AIProviderError(
                        f"Unexpected API response format: {result}",
                        provider=self.name,
                        response=result,
                    )
            else:
                error_body = None
                try:
                    error_body = response.json()
                except Exception:
                    pass

                raise AIProviderError(
                    f"Vision API returned status {response.status_code}",
                    provider=self.name,
                    status_code=response.status_code,
                    response=error_body,
                )

        except requests.Timeout:
            raise AIProviderError(
                f"Vision API timed out after {use_timeout} seconds",
                provider=self.name,
            )
        except requests.RequestException as e:
            raise AIProviderError(
                f"Vision API request failed: {e}",
                provider=self.name,
            )
