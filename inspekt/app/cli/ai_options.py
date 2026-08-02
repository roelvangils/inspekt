"""
AI CLI Options - shared decorators for AI commands.

Provides --provider and --model options for commands that use AI.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

import click


def ai_options(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that adds --provider and --model options to a command.

    Usage:
        @click.command()
        @ai_options
        def summarize(provider, model, ...):
            ...

    The decorator adds:
        --provider, -p: AI provider to use (thoth, anthropic, openai, ollama)
        --model, -m: Specific model to use (overrides provider default)
    """

    @click.option(
        "--provider",
        "-p",
        type=click.Choice(["thoth", "anthropic", "openai", "ollama"]),
        default=None,
        help="AI provider to use (default: from config)",
    )
    @click.option(
        "--model",
        "-m",
        type=str,
        default=None,
        help="Specific model to use (overrides provider default)",
    )
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return wrapper


def get_ai_context(
    provider: str | None = None,
    model: str | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    """
    Get AI execution context with resolved provider and model.

    Args:
        provider: Explicit provider override from CLI
        model: Explicit model override from CLI
        command: Command name for command-specific defaults

    Returns:
        Dict with:
            - provider_manager: ProviderManager instance
            - provider: Resolved provider name
            - model: Resolved model name
    """
    from inspekt.services.ai_providers import get_provider_manager

    manager = get_provider_manager()

    # Resolve provider and model
    resolved_provider, resolved_model = manager.resolve_provider(
        provider=provider, command=command
    )

    # Model override from CLI takes precedence
    if model:
        resolved_model = model

    return {
        "provider_manager": manager,
        "provider": resolved_provider,
        "model": resolved_model,
    }
