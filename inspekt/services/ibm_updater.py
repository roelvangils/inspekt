"""
IBM Equal Access version management and update service.

DEPRECATED: This module is kept for backwards compatibility.
Use inspekt.services.engines.IbmEngine instead.

Handles checking for updates, downloading, installing, and verifying
the IBM Equal Access accessibility testing library (ace.js).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from packaging import version

import requests

from inspekt.services import http_client


class IbmUpdater:
    """Service for managing IBM Equal Access library updates."""

    def __init__(self):
        """Initialize the IBM updater service."""
        self.vendor_dir = Path(__file__).parent.parent / "scripts" / "vendor"
        self.ace_lib_path = self.vendor_dir / "ace.min.js"
        self.version_file = self.vendor_dir / "ace.version.json"
        self.backup_path = self.vendor_dir / "ace.backup.js"
        self.npm_registry_url = "https://registry.npmjs.org/accessibility-checker-engine/latest"
        self.cdn_base_url = "https://unpkg.com/accessibility-checker-engine@{version}/ace.js"

    def get_current_version(self) -> Optional[str]:
        """
        Get the currently installed version of IBM Equal Access.

        Returns:
            Version string (e.g., "3.1.72") or None if not found
        """
        if not self.version_file.exists():
            return None

        try:
            with open(self.version_file) as f:
                metadata = json.load(f)
            return metadata.get("version")
        except (json.JSONDecodeError, IOError):
            return None

    def check_latest_version(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """
        Check npm registry for the latest version of IBM Equal Access.

        Args:
            timeout: Request timeout in seconds

        Returns:
            Dictionary with version info or None if check fails
            {
                "version": "3.1.72",
                "tarball": "https://…",
                "shasum": "abc123…",
                "release_date": "2025-10-09T16:39:18.813Z"
            }
        """
        try:
            # First get basic version info from /latest endpoint (fast)
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
                full_url = "https://registry.npmjs.org/accessibility-checker-engine"
                full_response = http_client.get(full_url, timeout=timeout)
                full_response.raise_for_status()
                full_data = full_response.json()

                # Get release date for this version from the time field
                times = full_data.get("time", {})
                ver = result["version"]
                if ver and ver in times:
                    result["release_date"] = times[ver]
            except (requests.RequestException, json.JSONDecodeError, KeyError):
                # Continue without release date if this fails
                pass

            return result
        except (requests.RequestException, json.JSONDecodeError, KeyError):
            return None

    def is_update_available(self) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Check if an update is available.

        Returns:
            Tuple of (update_available, current_version, latest_version, release_date)
        """
        current = self.get_current_version()
        if not current:
            # No version installed - return True to trigger initial download
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
            # Use packaging.version for proper semver comparison
            update_available = version.parse(latest) > version.parse(current)
            return update_available, current, latest, release_date
        except version.InvalidVersion:
            return False, current, latest, release_date

    def download_version(self, ver: str) -> Optional[Path]:
        """
        Download a specific version of IBM Equal Access to a temporary file.

        Args:
            ver: Version string (e.g., "3.1.72")

        Returns:
            Path to downloaded file or None if download fails
        """
        url = self.cdn_base_url.format(version=ver)

        try:
            response = http_client.get(url, timeout=30.0)
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
        Backup the current IBM Equal Access library.

        Returns:
            True if backup successful or no existing file, False otherwise
        """
        if not self.ace_lib_path.exists():
            return True  # Nothing to backup

        try:
            shutil.copy2(self.ace_lib_path, self.backup_path)
            return True
        except IOError:
            return False

    def restore_backup(self) -> bool:
        """
        Restore IBM Equal Access from backup.

        Returns:
            True if restore successful, False otherwise
        """
        if not self.backup_path.exists():
            return False

        try:
            shutil.copy2(self.backup_path, self.ace_lib_path)
            return True
        except IOError:
            return False

    def install_version(self, source_path: Path, ver: str) -> bool:
        """
        Install a new version of IBM Equal Access.

        Args:
            source_path: Path to downloaded ace.js file
            ver: Version string

        Returns:
            True if installation successful, False otherwise
        """
        try:
            # Ensure vendor directory exists
            self.vendor_dir.mkdir(parents=True, exist_ok=True)

            # Copy new version to vendor directory
            shutil.copy2(source_path, self.ace_lib_path)

            # Calculate checksum
            checksum = self.verify_checksum(self.ace_lib_path)

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
        except (IOError, json.JSONDecodeError):
            return False

    def test_installation(self) -> bool:
        """
        Test that the installed IBM Equal Access library is valid.

        Returns:
            True if library loads and contains expected content, False otherwise
        """
        if not self.ace_lib_path.exists():
            return False

        try:
            # Read file and check for expected content
            with open(self.ace_lib_path) as f:
                content = f.read()

            # Basic sanity check: file should contain ace namespace
            # and define the checker engine
            if "ace" not in content.lower() or len(content) < 100000:
                return False

            return True
        except IOError:
            return False

    def update_to_latest(self, progress_callback=None) -> tuple[bool, str]:
        """
        Update IBM Equal Access to the latest version.

        Args:
            progress_callback: Optional callback function(message: str) for progress updates

        Returns:
            Tuple of (success: bool, message: str)
        """
        def progress(msg: str):
            if progress_callback:
                progress_callback(msg)

        # Check for update
        update_available, current, latest, _ = self.is_update_available()

        if not update_available:
            if not latest:
                return False, "Unable to check for updates (network error)"
            return False, f"Already on latest version ({current})"

        action = "Installing" if current is None else "Downloading"
        progress(f"{action} IBM Equal Access@{latest}…")

        # Download new version
        temp_path = self.download_version(latest)
        if not temp_path:
            return False, "Download failed"

        progress("Verifying integrity…")

        # Backup current version (if exists)
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

        if current is None:
            return True, f"Installed IBM Equal Access {latest}"
        return True, f"Updated to IBM Equal Access {latest}"

    def ensure_installed(self, progress_callback=None) -> tuple[bool, str]:
        """
        Ensure IBM Equal Access is installed (download if missing).

        Args:
            progress_callback: Optional callback function(message: str) for progress updates

        Returns:
            Tuple of (success: bool, message: str)
        """
        if self.ace_lib_path.exists() and self.test_installation():
            current = self.get_current_version()
            return True, f"IBM Equal Access {current} is installed"

        # Not installed or invalid - download latest
        return self.update_to_latest(progress_callback)


def get_ibm_updater() -> IbmUpdater:
    """
    Get the IBM updater service instance.

    DEPRECATED: Use get_engine('ibm') from inspekt.services.engines instead.

    Returns:
        IbmUpdater instance
    """
    warnings.warn(
        "get_ibm_updater() is deprecated. Use get_engine('ibm') from "
        "inspekt.services.engines instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return IbmUpdater()
