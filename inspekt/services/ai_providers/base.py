"""
Base classes for AI providers.

Defines the abstract interface that all providers must implement,
plus the standard response type.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AIResponse:
    """
    Standard response from any AI provider.

    Attributes:
        content: The generated text content
        model: Model identifier used for generation
        provider: Provider name (e.g., "thoth", "anthropic", "openai")
        usage: Token usage statistics (if available)
        raw_response: Full API response for debugging
    """

    content: str
    model: str
    provider: str
    usage: dict[str, int] | None = None
    raw_response: dict[str, Any] | None = field(default=None, repr=False)

    def __str__(self) -> str:
        return self.content


class AIProvider(ABC):
    """
    Abstract base class for AI providers.

    All providers must implement:
    - name: Provider identifier
    - is_available(): Check if provider is configured
    - call_text(): Text generation
    - call_vision(): Vision analysis (optional, defaults to NotImplementedError)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier (e.g., 'thoth', 'anthropic')."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is properly configured (has API key, etc.)."""
        ...

    @abstractmethod
    def call_text(
        self,
        prompt: str,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> AIResponse:
        """
        Generate text from a prompt.

        Args:
            prompt: Input text prompt
            model: Model to use (provider-specific default if None)
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Provider-specific options

        Returns:
            AIResponse with generated content

        Raises:
            AIProviderError: If the API call fails
        """
        ...

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
        Generate text from an image and prompt.

        Args:
            prompt: Text prompt describing the analysis
            image_data_url: Base64-encoded image (data:image/...;base64,...)
            model: Vision model to use
            max_tokens: Maximum tokens to generate
            timeout: Request timeout in seconds
            **kwargs: Provider-specific options

        Returns:
            AIResponse with generated content

        Raises:
            NotImplementedError: If provider doesn't support vision
            AIProviderError: If the API call fails
        """
        raise NotImplementedError(f"Provider '{self.name}' does not support vision")

    def supports_vision(self) -> bool:
        """Check if this provider supports vision/image analysis."""
        # Override in subclasses that support vision
        return False

    def get_default_text_model(self) -> str:
        """Get the default text model for this provider."""
        return "default"

    def get_default_vision_model(self) -> str:
        """Get the default vision model for this provider."""
        return self.get_default_text_model()


class AIProviderError(Exception):
    """
    Exception raised when an AI provider call fails.

    Attributes:
        message: Error description
        provider: Provider that raised the error
        status_code: HTTP status code (if applicable)
        response: Raw error response (if available)
    """

    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        status_code: int | None = None,
        response: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.status_code = status_code
        self.response = response

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code:
            parts.append(f"(HTTP {self.status_code})")
        return " ".join(parts)
