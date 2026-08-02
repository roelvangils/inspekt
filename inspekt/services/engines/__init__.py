"""
Accessibility Engine Registry.

Provides discovery and access to built-in accessibility testing engines.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import AccessibilityEngine

# Registry of built-in engines (populated on first access)
_ENGINES: dict[str, type[AccessibilityEngine]] | None = None


def _load_engines() -> dict[str, type[AccessibilityEngine]]:
    """Load engine classes on first access to avoid circular imports."""
    from .axe_engine import AxeEngine
    from .htmlcs_engine import HtmlcsEngine
    from .ibm_engine import IbmEngine
    from .sia_engine import SiaEngine

    return {
        "axe": AxeEngine,
        "eac": IbmEngine,
        "hcs": HtmlcsEngine,
        "sia": SiaEngine,
    }


def _get_engines() -> dict[str, type[AccessibilityEngine]]:
    """Get the engines registry, loading if needed."""
    global _ENGINES
    if _ENGINES is None:
        _ENGINES = _load_engines()
    return _ENGINES


def get_engine(engine_id: str) -> AccessibilityEngine:
    """
    Get an engine instance by ID.

    Args:
        engine_id: Engine identifier (e.g., "axe", "ibm")

    Returns:
        Engine instance

    Raises:
        ValueError: If engine not found
    """
    engines = _get_engines()
    engine_class = engines.get(engine_id.lower())
    if not engine_class:
        available = ", ".join(sorted(engines.keys()))
        raise ValueError(f"Unknown engine '{engine_id}'. Available: {available}")
    return engine_class()


def list_engines() -> list[str]:
    """List all available engine IDs in default order."""
    return list(_get_engines().keys())


def get_all_engines() -> list[AccessibilityEngine]:
    """Get instances of all available engines."""
    return [engine_class() for engine_class in _get_engines().values()]


def register_engine(engine_id: str, engine_class: type[AccessibilityEngine]) -> None:
    """
    Register a new engine (for future extensibility).

    Args:
        engine_id: Unique identifier
        engine_class: Engine class implementing AccessibilityEngine
    """
    engines = _get_engines()
    engines[engine_id.lower()] = engine_class


# Re-export base classes for convenience
from .base import (
    AccessibilityEngine,
    AuditResult,
    EngineInfo,
    ImpactLevel,
    NormalizedViolation,
)

__all__ = [
    "AccessibilityEngine",
    "AuditResult",
    "EngineInfo",
    "ImpactLevel",
    "NormalizedViolation",
    "get_all_engines",
    "get_engine",
    "list_engines",
    "register_engine",
]
