"""
Ollama AI Provider - Local LLMs.

Supports running models locally via Ollama, including:
- Llama 3
- Mistral
- CodeLlama
- And many other open-source models

Ollama must be installed and running locally.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from inspekt.services import http_client

from inspekt.services.ai_providers.base import AIProvider, AIProviderError, AIResponse

logger = logging.getLogger(__name__)


class OllamaProvider(AIProvider):
    """
    Ollama AI provider (local LLMs).

    Configuration:
        Environment variables:
            - OLLAMA_HOST: Ollama server URL (default: http://localhost:11434)

        Config file (config.json):
            - ai.providers.ollama.endpoint: API endpoint URL
            - ai.providers.ollama.default-text-model: Default text model
            - ai.providers.ollama.default-vision-model: Default vision model
    """

    # Default settings
    DEFAULT_ENDPOINT = "http://localhost:11434"
    DEFAULT_TEXT_MODEL = "llama3.2"
    DEFAULT_VISION_MODEL = "llava"

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the Ollama provider.

        Args:
            config: AI configuration dict
        """
        self._config = config or {}
        self._provider_config = self._config.get("providers", {}).get("ollama", {})

    @property
    def name(self) -> str:
        return "ollama"

    def is_available(self) -> bool:
        """
        Check if Ollama is available.

        Tests connection to the Ollama server.
        """
        try:
            endpoint = self._get_endpoint()
            response = http_client.get(f"{endpoint}/api/tags", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def _get_endpoint(self) -> str:
        """Get the Ollama API endpoint."""
        # Environment variable has priority
        if host := os.environ.get("OLLAMA_HOST"):
            return host.rstrip("/")

        # Fall back to config
        return self._provider_config.get("endpoint", self.DEFAULT_ENDPOINT).rstrip("/")

    def get_default_text_model(self) -> str:
        return self._provider_config.get("default-text-model", self.DEFAULT_TEXT_MODEL)

    def get_default_vision_model(self) -> str:
        return self._provider_config.get(
            "default-vision-model", self.DEFAULT_VISION_MODEL
        )

    def supports_vision(self) -> bool:
        # Ollama supports vision with specific models (llava, etc.)
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
        Generate text using Ollama.

        Args:
            prompt: Input text prompt
            model: Model to use (default from config)
            max_tokens: Maximum tokens to generate (maps to num_predict)
            timeout: Request timeout in seconds
            **kwargs: Additional options

        Returns:
            AIResponse with generated content
        """
        endpoint = self._get_endpoint()
        use_model = model or self.get_default_text_model()
        use_timeout = timeout or self._config.get("timeout", 60)

        options = {}
        if max_tokens:
            options["num_predict"] = max_tokens

        try:
            response = http_client.post(
                f"{endpoint}/api/generate",
                json={
                    "model": use_model,
                    "prompt": prompt,
                    "stream": False,
                    "options": options,
                },
                timeout=use_timeout,
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get("response", "")

                # Ollama provides some usage stats
                usage = None
                if "eval_count" in result:
                    usage = {
                        "prompt_tokens": result.get("prompt_eval_count", 0),
                        "completion_tokens": result.get("eval_count", 0),
                    }

                return AIResponse(
                    content=content,
                    model=use_model,
                    provider=self.name,
                    usage=usage,
                    raw_response=result,
                )
            else:
                raise AIProviderError(
                    f"Ollama returned status {response.status_code}",
                    provider=self.name,
                    status_code=response.status_code,
                )

        except requests.Timeout:
            raise AIProviderError(
                f"Request timed out after {use_timeout}s. "
                "Ollama may be loading the model - try again.",
                provider=self.name,
            )
        except requests.ConnectionError:
            raise AIProviderError(
                f"Cannot connect to Ollama at {endpoint}. "
                "Make sure Ollama is running: ollama serve",
                provider=self.name,
            )
        except requests.RequestException as e:
            raise AIProviderError(
                f"Request failed: {e}",
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
        Generate text from an image using Ollama (requires llava or similar).

        Args:
            prompt: Text prompt describing the analysis
            image_data_url: Base64-encoded image (data:image/...;base64,...)
            model: Vision model to use (default: llava)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Additional options

        Returns:
            AIResponse with generated content
        """
        endpoint = self._get_endpoint()
        use_model = model or self.get_default_vision_model()
        use_timeout = timeout or self._config.get("timeout", 120)

        # Extract base64 data from data URL
        if ";base64," in image_data_url:
            base64_data = image_data_url.split(";base64,")[1]
        else:
            raise AIProviderError(
                "Invalid image data URL format",
                provider=self.name,
            )

        options = {}
        if max_tokens:
            options["num_predict"] = max_tokens

        try:
            response = http_client.post(
                f"{endpoint}/api/generate",
                json={
                    "model": use_model,
                    "prompt": prompt,
                    "images": [base64_data],
                    "stream": False,
                    "options": options,
                },
                timeout=use_timeout,
            )

            if response.status_code == 200:
                result = response.json()
                content = result.get("response", "")

                usage = None
                if "eval_count" in result:
                    usage = {
                        "prompt_tokens": result.get("prompt_eval_count", 0),
                        "completion_tokens": result.get("eval_count", 0),
                    }

                return AIResponse(
                    content=content,
                    model=use_model,
                    provider=self.name,
                    usage=usage,
                    raw_response=result,
                )
            else:
                raise AIProviderError(
                    f"Ollama vision returned status {response.status_code}",
                    provider=self.name,
                    status_code=response.status_code,
                )

        except requests.Timeout:
            raise AIProviderError(
                f"Vision request timed out after {use_timeout}s. "
                "Vision models can be slow - try increasing timeout.",
                provider=self.name,
            )
        except requests.ConnectionError:
            raise AIProviderError(
                f"Cannot connect to Ollama at {endpoint}. "
                "Make sure Ollama is running: ollama serve",
                provider=self.name,
            )
        except requests.RequestException as e:
            raise AIProviderError(
                f"Vision request failed: {e}",
                provider=self.name,
            )

    def list_models(self) -> list[str]:
        """
        List available models in Ollama.

        Returns:
            List of model names
        """
        endpoint = self._get_endpoint()
        try:
            response = http_client.get(f"{endpoint}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []
