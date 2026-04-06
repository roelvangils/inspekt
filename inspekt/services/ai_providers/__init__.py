"""
AI Provider abstraction layer.

Provides a unified interface for multiple AI backends:
- Thoth (OpenAI-compatible, default)
- Anthropic (Claude)
- OpenAI (GPT)
- Ollama (local LLMs)
"""

from inspekt.services.ai_providers.base import AIProvider, AIResponse
from inspekt.services.ai_providers.manager import ProviderManager, get_provider_manager

__all__ = [
    "AIProvider",
    "AIResponse",
    "ProviderManager",
    "get_provider_manager",
]
