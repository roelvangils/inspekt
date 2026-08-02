"""
Mozilla Readability library version management and update service.

Handles checking for updates, downloading, and installing the Mozilla Readability
library used for article content extraction.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

import requests
from packaging import version

from inspekt.services import http_client

# Cache TTL for npm version checks (1 day)
_VERSION_CACHE_TTL = 86400


class ReadabilityUpdater:
    """Service for managing Mozilla Readability library updates."""

    def __init__(self):
        """Initialize the Readability updater service."""
        self.vendor_dir = Path(__file__).parent.parent / "scripts" / "vendor" / "readability"
        self.lib_path = self.vendor_dir / "Readability.js"
        self.version_file = self.vendor_dir / "readability.version.json"
        self.backup_path = self.vendor_dir / "Readability.backup.js"
        self.npm_package = "@mozilla/readability"
        self.npm_registry_url = "https://registry.npmjs.org/@mozilla/readability/latest"
        self.raw_github_url = "https://raw.githubusercontent.com/mozilla/readability/main/Readability.js"
        self._cache_file = Path(__file__).parent.parent.parent / ".cache" / "readability_latest_version.json"

    def get_current_version(self) -> str | None:
        """
        Get the currently installed version of Readability.

        Returns:
            Version string (e.g., "0.6.0") or None if not found
        """
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
        Check npm registry for the latest version of Readability.

        Results are cached for 1 day to avoid repeated network requests.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Dictionary with version info or None if check fails
            {
                "version": "0.6.0",
                "tarball": "https://…",
                "shasum": "abc123…",
                "release_date": "2024-03-15T12:00:00.000Z"
            }
        """
        # Check cache first
        if self._cache_file.exists():
            try:
                with open(self._cache_file) as f:
                    cached = json.load(f)
                # Check if cache is still valid (1 day TTL)
                if time.time() - cached.get("_timestamp", 0) < _VERSION_CACHE_TTL:
                    return {k: v for k, v in cached.items() if not k.startswith("_")}
            except (OSError, json.JSONDecodeError):
                pass

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
                self._cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_data = {**result, "_timestamp": time.time()}
                with open(self._cache_file, "w") as f:
                    json.dump(cache_data, f)
            except OSError:
                pass

            return result
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            return None

    def is_update_available(self) -> tuple[bool, str | None, str | None, str | None]:
        """
        Check if an update is available.

        Returns:
            Tuple of (update_available, current_version, latest_version, release_date)
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
        """Check if Readability is installed and valid."""
        return self.lib_path.exists() and self.test_installation()

    def download_version(self, ver: str) -> Path | None:
        """
        Download a specific version of Readability to a temporary file.

        Uses the GitHub raw URL since the npm package requires additional processing.

        Args:
            ver: Version string (e.g., "0.6.0")

        Returns:
            Path to downloaded file or None if download fails
        """
        # Use GitHub raw URL for the specific tag
        url = f"https://raw.githubusercontent.com/mozilla/readability/v{ver}/Readability.js"

        try:
            response = http_client.get(url, timeout=30.0)
            # If tagged version doesn't exist, try main branch
            if response.status_code == 404:
                response = http_client.get(self.raw_github_url, timeout=30.0)
            response.raise_for_status()

            temp_file = tempfile.NamedTemporaryFile(mode="wb", delete=False, suffix=".js")
            temp_file.write(response.content)
            temp_file.close()

            return Path(temp_file.name)
        except requests.RequestException:
            return None

    def verify_checksum(self, file_path: Path) -> str:
        """
        Calculate SHA256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            SHA256 checksum as hex string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def backup_current_version(self) -> bool:
        """
        Backup the current Readability library.

        Returns:
            True if backup successful or nothing to backup, False otherwise
        """
        if not self.lib_path.exists():
            return True

        try:
            shutil.copy2(self.lib_path, self.backup_path)
            return True
        except OSError:
            return False

    def restore_backup(self) -> bool:
        """
        Restore Readability from backup.

        Returns:
            True if restore successful, False otherwise
        """
        if not self.backup_path.exists():
            return False

        try:
            shutil.copy2(self.backup_path, self.lib_path)
            return True
        except OSError:
            return False

    def install_version(self, source_path: Path, ver: str) -> bool:
        """
        Install a new version of Readability.

        Args:
            source_path: Path to downloaded Readability file
            ver: Version string

        Returns:
            True if installation successful, False otherwise
        """
        try:
            self.vendor_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, self.lib_path)

            checksum = self.verify_checksum(self.lib_path)

            metadata = {
                "name": "@mozilla/readability",
                "version": ver,
                "source": "https://github.com/mozilla/readability",
                "downloaded": datetime.utcnow().strftime("%Y-%m-%d"),
                "file": "Readability.js",
                "license": "Apache-2.0",
                "checksum": f"sha256:{checksum}",
            }

            with open(self.version_file, "w") as f:
                json.dump(metadata, f, indent=2)

            return True
        except (OSError, json.JSONDecodeError):
            return False

    def test_installation(self) -> bool:
        """
        Test that the installed Readability library is valid.

        Returns:
            True if library loads and contains Readability constructor, False otherwise
        """
        if not self.lib_path.exists():
            return False

        try:
            with open(self.lib_path) as f:
                content = f.read()

            # Basic sanity check: file should contain Readability function
            if "function Readability" not in content:
                return False
            if len(content) < 50000:  # Readability.js is ~100KB
                return False

            return True
        except OSError:
            return False

    def update_to_latest(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> tuple[bool, str]:
        """
        Update Readability to the latest version.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates

        Returns:
            Tuple of (success: bool, message: str)
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
        progress(f"{action} @mozilla/readability@{latest}…")

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
            return True, f"Installed @mozilla/readability {latest}"
        return True, f"Updated to @mozilla/readability {latest}"

    def ensure_installed(
        self, progress_callback: Callable[[str], None] | None = None
    ) -> tuple[bool, str]:
        """Ensure the library is installed (download if missing)."""
        if self.lib_path.exists() and self.test_installation():
            current = self.get_current_version()
            return True, f"@mozilla/readability {current} is installed"

        return self.update_to_latest(progress_callback)


def get_readability_updater() -> ReadabilityUpdater:
    """
    Get the Readability updater service instance.

    Returns:
        ReadabilityUpdater instance
    """
    return ReadabilityUpdater()
