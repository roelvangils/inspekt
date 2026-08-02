"""
Base class for accessibility testing engines.

All engines (Axe, IBM, QualWeb) implement this interface to provide
consistent behavior for version management, updates, and execution.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from packaging import version

from inspekt.services import http_client

if TYPE_CHECKING:
    from collections.abc import Callable

# Cache TTL for npm version checks (1 day)
_VERSION_CACHE_TTL = 86400


class ImpactLevel(Enum):
    """Unified impact levels across all engines."""

    CRITICAL = "critical"
    SERIOUS = "serious"
    MODERATE = "moderate"
    MINOR = "minor"


@dataclass
class EngineInfo:
    """Metadata about an accessibility engine."""

    id: str  # e.g., "axe", "ibm", "qualweb"
    name: str  # e.g., "axe-core", "IBM Equal Access"
    npm_package: str  # e.g., "axe-core", "accessibility-checker-engine"
    description: str
    homepage: str
    current_version: str | None = None
    latest_version: str | None = None


@dataclass
class NormalizedViolation:
    """
    Unified violation format for cross-engine comparison.

    All engines must normalize their results to this format.
    """

    rule_id: str  # Engine-specific rule ID
    impact: ImpactLevel  # Normalized impact level
    title: str  # Short description of the issue
    description: str  # Full description
    help_url: str  # Documentation link
    failure_summary: str  # What's wrong with this specific element
    html_snippet: str  # The problematic HTML
    selector: list[str]  # CSS selector path
    wcag_tags: list[str]  # WCAG/standards tags (e.g., ["wcag2aa", "wcag143"])
    engine: str  # Source engine ID
    raw: dict = field(default_factory=dict)  # Original engine-specific data


@dataclass
class AuditResult:
    """Standardized audit result across all engines."""

    engine: str
    engine_version: str
    url: str
    title: str
    timestamp: str
    violations: list[NormalizedViolation]
    passes: list[dict] = field(default_factory=list)  # Simplified pass info
    incomplete: list[dict] = field(default_factory=list)  # Needs manual review
    inapplicable: list[str] = field(default_factory=list)  # Rule IDs that didn't apply
    summary: dict = field(default_factory=dict)  # Engine-specific summary stats
    raw: dict = field(default_factory=dict)  # Original engine response


class AccessibilityEngine(ABC):
    """
    Abstract base class for accessibility testing engines.

    Each engine implementation handles:
    - Library version management (check, download, update)
    - JavaScript execution script loading
    - Result normalization to unified format
    """

    # =========================================================================
    # Abstract Properties - Must be implemented by subclasses
    # =========================================================================

    @property
    @abstractmethod
    def engine_id(self) -> str:
        """Unique identifier for this engine (e.g., 'axe', 'ibm')."""
        ...

    @property
    def engine_name(self) -> str:
        """Human-readable name loaded from engines.json (e.g., 'Axe-core', 'Equal Access Checker')."""
        from inspekt.data import get_engine_metadata

        try:
            return get_engine_metadata(self.engine_id)["official_name"]
        except KeyError:
            # Fallback for engines not in metadata
            return self.engine_id

    @property
    def provider(self) -> str:
        """Provider/vendor name loaded from engines.json (e.g., 'Deque Systems', 'IBM')."""
        from inspekt.data import get_engine_metadata

        try:
            return get_engine_metadata(self.engine_id)["provider"]
        except KeyError:
            # Fallback for engines not in metadata
            return ""

    @property
    @abstractmethod
    def npm_package(self) -> str:
        """npm package name for version checking."""
        ...

    @property
    @abstractmethod
    def cdn_url_template(self) -> str:
        """
        CDN URL template with {version} placeholder.
        Example: "https://cdn.jsdelivr.net/npm/axe-core@{version}/axe.min.js"
        """
        ...

    @property
    @abstractmethod
    def lib_filename(self) -> str:
        """Filename for the library in vendor directory."""
        ...

    @property
    @abstractmethod
    def version_basename(self) -> str:
        """Base name for version file (without .version.json suffix)."""
        ...

    @property
    @abstractmethod
    def script_filename(self) -> str:
        """Filename of the execution script (e.g., 'run_axe.js')."""
        ...

    @property
    @abstractmethod
    def min_file_size(self) -> int:
        """Minimum expected file size for validation (bytes)."""
        ...

    @property
    @abstractmethod
    def validation_marker(self) -> str:
        """String that must be present in valid library file (case-insensitive)."""
        ...

    @abstractmethod
    def get_description(self) -> str:
        """Get a short description of the engine."""
        ...

    @abstractmethod
    def get_homepage(self) -> str:
        """Get the engine's homepage URL."""
        ...

    # =========================================================================
    # Common Implementation - Shared by all engines
    # =========================================================================

    def __init__(self):
        """Initialize the engine with standard paths."""
        self._vendor_dir = Path(__file__).parent.parent.parent / "scripts" / "vendor"
        self._scripts_dir = Path(__file__).parent.parent.parent / "scripts"

    @property
    def vendor_dir(self) -> Path:
        """Directory containing vendor libraries."""
        return self._vendor_dir

    @property
    def lib_path(self) -> Path:
        """Full path to the library file."""
        return self.vendor_dir / self.lib_filename

    @property
    def version_file(self) -> Path:
        """Path to version metadata JSON file."""
        return self.vendor_dir / f"{self.version_basename}.version.json"

    @property
    def backup_path(self) -> Path:
        """Path to backup file."""
        stem = Path(self.lib_filename).stem
        return self.vendor_dir / f"{stem}.backup.js"

    @property
    def npm_registry_url(self) -> str:
        """URL for npm registry latest version endpoint."""
        return f"https://registry.npmjs.org/{self.npm_package}/latest"

    @property
    def _version_cache_file(self) -> Path:
        """Path to cached npm version info."""
        cache_dir = Path(__file__).parent.parent.parent.parent / ".cache"
        cache_dir.mkdir(exist_ok=True)
        return cache_dir / f"{self.engine_id}_latest_version.json"

    @property
    def script_path(self) -> Path:
        """Full path to the execution script."""
        return self._scripts_dir / self.script_filename

    def get_info(self) -> EngineInfo:
        """Get engine metadata."""
        return EngineInfo(
            id=self.engine_id,
            name=self.engine_name,
            npm_package=self.npm_package,
            description=self.get_description(),
            homepage=self.get_homepage(),
            current_version=self.get_current_version(),
            latest_version=None,  # Populated on demand
        )

    # =========================================================================
    # Version Management - Shared implementation
    # =========================================================================

    def get_current_version(self) -> str | None:
        """Get the currently installed version."""
        if not self.version_file.exists():
            return None

        try:
            with open(self.version_file) as f:
                metadata = json.load(f)
            return metadata.get("version")
        except (OSError, json.JSONDecodeError):
            return None

    def check_latest_version(self, timeout: float = 5.0) -> dict[str, Any] | None:
        """
        Check npm registry for the latest version.

        Results are cached for 1 day to avoid repeated network requests.

        Returns dict with: version, tarball, shasum, release_date
        """
        # Check cache first
        cache_file = self._version_cache_file
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    cached = json.load(f)
                # Check if cache is still valid (1 day TTL)
                if time.time() - cached.get("_timestamp", 0) < _VERSION_CACHE_TTL:
                    # Return cached data (without the timestamp)
                    return {k: v for k, v in cached.items() if not k.startswith("_")}
            except (OSError, json.JSONDecodeError):
                pass

        # Fetch from npm
        try:
            response = http_client.get(self.npm_registry_url, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            result = {
                "version": data.get("version"),
                "tarball": data.get("dist", {}).get("tarball"),
                "shasum": data.get("dist", {}).get("shasum"),
                "release_date": None,
            }

            # Try to get release date from full package data
            try:
                full_url = f"https://registry.npmjs.org/{self.npm_package}"
                full_response = http_client.get(full_url, timeout=timeout)
                full_response.raise_for_status()
                full_data = full_response.json()

                times = full_data.get("time", {})
                ver = result["version"]
                if ver and ver in times:
                    result["release_date"] = times[ver]
            except (requests.RequestException, json.JSONDecodeError, KeyError):
                pass

            # Cache the result
            try:
                cache_data = {**result, "_timestamp": time.time()}
                with open(cache_file, "w") as f:
                    json.dump(cache_data, f)
            except OSError:
                pass  # Cache write failure is not critical

            return result
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            return None

    def is_update_available(
        self,
    ) -> tuple[bool, str | None, str | None, str | None]:
        """
        Check if an update is available.

        Returns: (update_available, current_version, latest_version, release_date)
        """
        current = self.get_current_version()

        if not current:
            # Not installed - check if we can install
            latest_info = self.check_latest_version()
            if latest_info and latest_info.get("version"):
                return True, None, latest_info["version"], latest_info.get("release_date")
            return False, None, None, None

        latest_info = self.check_latest_version()
        if not latest_info or not latest_info.get("version"):
            return False, current, None, None

        latest = latest_info["version"]
        release_date = latest_info.get("release_date")

        try:
            update_available = version.parse(latest) > version.parse(current)
            return update_available, current, latest, release_date
        except version.InvalidVersion:
            return False, current, latest, release_date

    def is_installed(self) -> bool:
        """Check if the engine library is installed and valid."""
        return self.lib_path.exists() and self.test_installation()

    # =========================================================================
    # Download and Installation
    # =========================================================================

    def download_version(self, ver: str) -> Path | None:
        """Download a specific version to a temporary file."""
        url = self.cdn_url_template.format(version=ver)

        try:
            response = http_client.get(url, timeout=30.0)
            response.raise_for_status()

            with tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".js") as temp_file:
                temp_file.write(response.content)

            return Path(temp_file.name)
        except requests.RequestException:
            return None

    def verify_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def backup_current_version(self) -> bool:
        """Backup the current library file."""
        if not self.lib_path.exists():
            return True  # Nothing to backup

        try:
            shutil.copy2(self.lib_path, self.backup_path)
            return True
        except OSError:
            return False

    def restore_backup(self) -> bool:
        """Restore library from backup."""
        if not self.backup_path.exists():
            return False

        try:
            shutil.copy2(self.backup_path, self.lib_path)
            return True
        except OSError:
            return False

    def install_version(self, source_path: Path, ver: str) -> bool:
        """Install a new version of the library."""
        try:
            self.vendor_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, self.lib_path)

            checksum = self.verify_checksum(self.lib_path)

            metadata = {
                "version": ver,
                "installed_at": datetime.utcnow().isoformat() + "Z",
                "source": self.cdn_url_template.format(version=ver),
                "checksum": f"sha256:{checksum}",
            }

            with open(self.version_file, "w") as f:
                json.dump(metadata, f, indent=2)

            return True
        except (OSError, json.JSONDecodeError):
            return False

    def test_installation(self) -> bool:
        """Validate the installed library."""
        if not self.lib_path.exists():
            return False

        try:
            with open(self.lib_path) as f:
                content = f.read()

            if self.validation_marker.lower() not in content.lower():
                return False
            return not len(content) < self.min_file_size
        except OSError:
            return False

    def update_to_latest(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> tuple[bool, str]:
        """
        Update to the latest version.

        Returns: (success, message)
        """

        def progress(msg: str):
            if progress_callback:
                progress_callback(msg)

        update_available, current, latest, _ = self.is_update_available()

        if not update_available:
            if not latest:
                return False, "Unable to check for updates (network error)"
            return False, f"Already on latest version ({current})"

        action = "Installing" if current is None else "Downloading"
        progress(f"{action} {self.engine_name}@{latest}…")

        temp_path = self.download_version(latest)
        if not temp_path:
            return False, "Download failed"

        progress("Verifying integrity…")

        if not self.backup_current_version():
            temp_path.unlink(missing_ok=True)
            return False, "Failed to backup current version"

        progress("Installing…")

        if not self.install_version(temp_path, latest):
            temp_path.unlink(missing_ok=True)
            self.restore_backup()
            return False, "Installation failed"

        progress("Testing…")

        if not self.test_installation():
            self.restore_backup()
            temp_path.unlink(missing_ok=True)
            return False, "New version failed validation test"

        temp_path.unlink(missing_ok=True)

        if current is None:
            return True, f"Installed {self.engine_name} {latest}"
        return True, f"Updated to {self.engine_name} {latest}"

    def ensure_installed(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> tuple[bool, str]:
        """Ensure the library is installed (download if missing)."""
        if self.lib_path.exists() and self.test_installation():
            current = self.get_current_version()
            return True, f"{self.engine_name} {current} is installed"

        return self.update_to_latest(progress_callback)

    # =========================================================================
    # Execution - Must be implemented by subclasses
    # =========================================================================

    @abstractmethod
    def load_library(self) -> str:
        """
        Load the library JavaScript code.

        Returns:
            JavaScript code for the library
        """
        ...

    @abstractmethod
    def load_execution_script(self, config: dict) -> str:
        """
        Load and configure the JavaScript execution script.

        Args:
            config: Engine-specific configuration

        Returns:
            JavaScript code ready for browser execution
        """
        ...

    @abstractmethod
    def normalize_results(self, raw_results: dict) -> AuditResult:
        """
        Normalize engine-specific results to unified format.

        Args:
            raw_results: Raw results from browser execution

        Returns:
            Normalized AuditResult
        """
        ...

    @abstractmethod
    def build_config(
        self,
        level: str,
        include_passes: bool = False,
        include_incomplete: bool = False,
        **kwargs,
    ) -> dict:
        """
        Build engine-specific configuration from common parameters.

        Args:
            level: WCAG level (e.g., "22aa")
            include_passes: Include passing checks
            include_incomplete: Include incomplete checks
            **kwargs: Engine-specific options

        Returns:
            Engine-specific configuration dict
        """
        ...
