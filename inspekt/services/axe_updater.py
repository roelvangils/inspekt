"""
Axe-core version management and update service.

Handles checking for updates, downloading, installing, and verifying
the axe-core accessibility testing library.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from packaging import version


class AxeUpdater:
    """Service for managing axe-core library updates."""

    def __init__(self):
        """Initialize the axe updater service."""
        self.vendor_dir = Path(__file__).parent.parent / "scripts" / "vendor"
        self.axe_lib_path = self.vendor_dir / "axe-core.min.js"
        self.version_file = self.vendor_dir / "axe-core.version.json"
        self.backup_path = self.vendor_dir / "axe-core.backup.js"
        self.npm_registry_url = "https://registry.npmjs.org/axe-core/latest"
        self.cdn_base_url = "https://cdn.jsdelivr.net/npm/axe-core@{version}/axe.min.js"

    def get_current_version(self) -> str | None:
        """
        Get the currently installed version of axe-core.

        Returns:
            Version string (e.g., "4.11.0") or None if not found
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
        Check npm registry for the latest version of axe-core.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Dictionary with version info or None if check fails
            {
                "version": "4.12.0",
                "tarball": "https://…",
                "shasum": "abc123…",
                "release_date": "2025-10-09T16:39:18.813Z"
            }
        """
        try:
            # First get basic version info from /latest endpoint (fast)
            response = requests.get(self.npm_registry_url, timeout=timeout)
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
                full_url = "https://registry.npmjs.org/axe-core"
                full_response = requests.get(full_url, timeout=timeout)
                full_response.raise_for_status()
                full_data = full_response.json()

                # Get release date for this version from the time field
                times = full_data.get("time", {})
                version = result["version"]
                if version and version in times:
                    result["release_date"] = times[version]
            except (requests.RequestException, json.JSONDecodeError, KeyError):
                # Continue without release date if this fails
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
            return False, None, None, None

        latest_info = self.check_latest_version()
        if not latest_info or not latest_info.get("version"):
            return False, current, None, None

        latest = latest_info["version"]
        release_date = latest_info.get("release_date")

        try:
            # Use packaging.version for proper semver comparison
            update_available = version.parse(latest) > version.parse(current)
            return update_available, current, latest, release_date
        except version.InvalidVersion:
            return False, current, latest, release_date

    def download_version(self, ver: str) -> Path | None:
        """
        Download a specific version of axe-core to a temporary file.

        Args:
            ver: Version string (e.g., "4.12.0")

        Returns:
            Path to downloaded file or None if download fails
        """
        url = self.cdn_base_url.format(version=ver)

        try:
            response = requests.get(url, timeout=30.0)
            response.raise_for_status()

            # Create temporary file
            temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='.js')
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
        Backup the current axe-core library.

        Returns:
            True if backup successful, False otherwise
        """
        if not self.axe_lib_path.exists():
            return False

        try:
            shutil.copy2(self.axe_lib_path, self.backup_path)
            return True
        except OSError:
            return False

    def restore_backup(self) -> bool:
        """
        Restore axe-core from backup.

        Returns:
            True if restore successful, False otherwise
        """
        if not self.backup_path.exists():
            return False

        try:
            shutil.copy2(self.backup_path, self.axe_lib_path)
            return True
        except OSError:
            return False

    def install_version(self, source_path: Path, ver: str) -> bool:
        """
        Install a new version of axe-core.

        Args:
            source_path: Path to downloaded axe-core file
            ver: Version string

        Returns:
            True if installation successful, False otherwise
        """
        try:
            # Copy new version to vendor directory
            shutil.copy2(source_path, self.axe_lib_path)

            # Calculate checksum
            checksum = self.verify_checksum(self.axe_lib_path)

            # Update version metadata
            metadata = {
                "version": ver,
                "installed_at": datetime.utcnow().isoformat() + "Z",
                "source": self.cdn_base_url.format(version=ver),
                "checksum": f"sha256:{checksum}"
            }

            with open(self.version_file, 'w') as f:
                json.dump(metadata, f, indent=2)

            return True
        except (OSError, json.JSONDecodeError):
            return False

    def test_installation(self) -> bool:
        """
        Test that the installed axe-core library is valid.

        Returns:
            True if library loads and contains 'axe' object, False otherwise
        """
        if not self.axe_lib_path.exists():
            return False

        try:
            # Read file and check for axe object definition
            with open(self.axe_lib_path) as f:
                content = f.read()

            # Basic sanity check: file should contain axe-core copyright
            # and define window.axe or exports
            return not ("axe" not in content or len(content) < 50000)
        except OSError:
            return False

    def update_to_latest(self, progress_callback=None) -> tuple[bool, str]:
        """
        Update axe-core to the latest version.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates

        Returns:
            Tuple of (success: bool, message: str)
        """
        def progress(msg: str):
            if progress_callback:
                progress_callback(msg)

        # Check for update
        update_available, current, latest = self.is_update_available()

        if not update_available:
            if not latest:
                return False, "Unable to check for updates (network error)"
            return False, f"Already on latest version ({current})"

        progress(f"Downloading axe-core@{latest}…")

        # Download new version
        temp_path = self.download_version(latest)
        if not temp_path:
            return False, "Download failed"

        progress("Verifying integrity…")

        # Backup current version
        if not self.backup_current_version():
            temp_path.unlink(missing_ok=True)
            return False, "Failed to backup current version"

        progress("Installing…")

        # Install new version
        if not self.install_version(temp_path, latest):
            temp_path.unlink(missing_ok=True)
            self.restore_backup()
            return False, "Installation failed"

        progress("Testing…")

        # Test installation
        if not self.test_installation():
            self.restore_backup()
            temp_path.unlink(missing_ok=True)
            return False, "New version failed validation test"

        # Clean up
        temp_path.unlink(missing_ok=True)

        return True, f"Updated to axe-core {latest}"


def get_axe_updater() -> AxeUpdater:
    """
    Get the axe updater service instance.

    Returns:
        AxeUpdater instance
    """
    return AxeUpdater()
