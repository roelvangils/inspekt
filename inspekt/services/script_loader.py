"""Script loader service - Loads and caches JavaScript scripts.

This service:
- Loads JavaScript files from inspekt/scripts/ directory
- Caches scripts in memory for performance
- Handles template substitution (placeholders)
- Provides both sync and async interfaces
"""

from pathlib import Path
from typing import Any

from inspekt.adapters import filesystem


class ScriptLoader:
    """Service for loading and caching JavaScript scripts."""

    def __init__(self, scripts_dir: Path | None = None):
        """Initialize script loader.

        Args:
            scripts_dir: Directory containing JavaScript files.
                        If None, uses inspekt/scripts/ relative to this file.
        """
        if scripts_dir is None:
            # Default to inspekt/scripts/
            self.scripts_dir = Path(__file__).parent.parent / "scripts"
        else:
            self.scripts_dir = scripts_dir

        self._cache: dict[str, str] = {}

    def get_script_path(self, script_name: str) -> Path:
        """Get full path to a script file.

        Args:
            script_name: Name of script (e.g., "control.js")

        Returns:
            Full path to script

        Raises:
            FileNotFoundError: If script does not exist
        """
        path = self.scripts_dir / script_name
        if not filesystem.file_exists(path):
            raise FileNotFoundError(f"Script not found: {script_name}")
        return path

    def load_script_sync(self, script_name: str, use_cache: bool = True) -> str:
        """Load script synchronously (for CLI use).

        Args:
            script_name: Name of script file (e.g., "control.js")
            use_cache: If True, use cached version if available

        Returns:
            Script contents as string

        Raises:
            FileNotFoundError: If script does not exist
        """
        if use_cache and script_name in self._cache:
            return self._cache[script_name]

        path = self.get_script_path(script_name)
        content = filesystem.read_text_sync(path)

        if use_cache:
            self._cache[script_name] = content

        return content

    async def load_script_async(self, script_name: str, use_cache: bool = True) -> str:
        """Load script asynchronously (for server use).

        Args:
            script_name: Name of script file (e.g., "control.js")
            use_cache: If True, use cached version if available

        Returns:
            Script contents as string

        Raises:
            FileNotFoundError: If script does not exist
        """
        if use_cache and script_name in self._cache:
            return self._cache[script_name]

        path = self.get_script_path(script_name)
        content = await filesystem.read_text_async(path)

        if use_cache:
            self._cache[script_name] = content

        return content

    def substitute_placeholders(
        self, script_content: str, placeholders: dict[str, Any]
    ) -> str:
        """Substitute placeholders in script with actual values.

        Args:
            script_content: Original script content
            placeholders: Dictionary mapping placeholder names to values
                         Example: {"ACTION_PLACEHOLDER": "start"}

        Returns:
            Script with placeholders replaced

        Example:
            >>> loader = ScriptLoader()
            >>> script = "const action = 'ACTION_PLACEHOLDER';"
            >>> result = loader.substitute_placeholders(
            ...     script, {"ACTION_PLACEHOLDER": "start"}
            ... )
            >>> print(result)
            const action = 'start';
        """
        result = script_content
        for placeholder, value in placeholders.items():
            # Handle different value types
            if isinstance(value, str):
                replacement = value
            elif isinstance(value, (dict, list)):
                import json

                replacement = json.dumps(value)
            else:
                replacement = str(value)

            result = result.replace(placeholder, replacement)

        return result

    def load_with_substitution_sync(
        self, script_name: str, placeholders: dict[str, Any], use_cache: bool = False
    ) -> str:
        """Load script and substitute placeholders (sync).

        Args:
            script_name: Name of script file
            placeholders: Placeholder substitutions
            use_cache: If True, use cached base script (placeholders still substituted)

        Returns:
            Script with placeholders replaced

        Note:
            Scripts with substitutions are not cached (different per request)
        """
        script = self.load_script_sync(script_name, use_cache=use_cache)
        return self.substitute_placeholders(script, placeholders)

    async def load_with_substitution_async(
        self, script_name: str, placeholders: dict[str, Any], use_cache: bool = False
    ) -> str:
        """Load script and substitute placeholders (async).

        Args:
            script_name: Name of script file
            placeholders: Placeholder substitutions
            use_cache: If True, use cached base script (placeholders still substituted)

        Returns:
            Script with placeholders replaced

        Note:
            Scripts with substitutions are not cached (different per request)
        """
        script = await self.load_script_async(script_name, use_cache=use_cache)
        return self.substitute_placeholders(script, placeholders)

    def preload_script(self, script_name: str) -> None:
        """Preload script into cache (sync).

        Args:
            script_name: Name of script to preload

        Raises:
            FileNotFoundError: If script does not exist
        """
        self.load_script_sync(script_name, use_cache=True)

    async def preload_script_async(self, script_name: str) -> None:
        """Preload script into cache (async).

        Args:
            script_name: Name of script to preload

        Raises:
            FileNotFoundError: If script does not exist
        """
        await self.load_script_async(script_name, use_cache=True)

    def clear_cache(self) -> None:
        """Clear the script cache."""
        self._cache.clear()

    def get_cached_scripts(self) -> list[str]:
        """Get list of cached script names.

        Returns:
            List of script names currently in cache
        """
        return list(self._cache.keys())
