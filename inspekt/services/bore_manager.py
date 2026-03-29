"""
Bore tunnel client binary management.

Handles downloading, installing, and version-checking the bore tunnel client
for the `inspekt tunnel` command. bore is a minimal TCP tunnel tool that
exposes local ports to a remote server.

See: https://github.com/ekzhang/bore
"""

from __future__ import annotations

import json
import platform
import stat
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import requests

from inspekt.config import get_data_dir


# bore release metadata
BORE_GITHUB_REPO = "ekzhang/bore"
BORE_DEFAULT_VERSION = "0.5.2"

# Platform mappings for bore release artifacts
_PLATFORM_MAP = {
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Linux", "x86_64"): "x86_64-unknown-linux-musl",
    ("Linux", "aarch64"): "aarch64-unknown-linux-musl",
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
}


class BoreManager:
    """Manages the bore tunnel client binary."""

    def __init__(self):
        self._bin_dir = get_data_dir() / "bin"
        self._version_file = self._bin_dir / "bore.version.json"

    @property
    def binary_path(self) -> Path:
        """Path to the bore binary."""
        name = "bore.exe" if platform.system() == "Windows" else "bore"
        return self._bin_dir / name

    def is_installed(self) -> bool:
        """Check if bore binary exists and is executable."""
        return self.binary_path.exists() and self.binary_path.stat().st_mode & stat.S_IXUSR

    def get_installed_version(self) -> Optional[str]:
        """Get the installed bore version from metadata."""
        if not self._version_file.exists():
            return None
        try:
            with open(self._version_file) as f:
                data = json.load(f)
            return data.get("version")
        except (json.JSONDecodeError, IOError):
            return None

    def install(self, version: Optional[str] = None) -> Path:
        """
        Download and install the bore client binary.

        Args:
            version: Specific version to install (e.g. "0.5.2").
                     If None, uses the latest release or default.

        Returns:
            Path to the installed binary.

        Raises:
            RuntimeError: If platform is unsupported or download fails.
        """
        if version is None:
            version = self._get_latest_version() or BORE_DEFAULT_VERSION

        target = self._detect_platform_target()
        url = self._get_download_url(version, target)

        # Ensure bin directory exists
        self._bin_dir.mkdir(parents=True, exist_ok=True)

        # Download and extract
        self._download_and_extract(url, target)

        # Make executable
        self.binary_path.chmod(self.binary_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP)

        # Write version metadata
        with open(self._version_file, "w") as f:
            json.dump({"version": version, "target": target}, f, indent=2)

        return self.binary_path

    def _detect_platform_target(self) -> str:
        """Detect the platform target triple for bore releases."""
        system = platform.system()
        machine = platform.machine()

        target = _PLATFORM_MAP.get((system, machine))
        if target is None:
            raise RuntimeError(
                f"Unsupported platform: {system} {machine}. "
                f"Supported: macOS (Intel/Apple Silicon), Linux (x86_64/ARM64), Windows (x86_64)"
            )
        return target

    def _get_download_url(self, version: str, target: str) -> str:
        """Build the GitHub release download URL."""
        ext = "zip" if "windows" in target else "tar.gz"
        filename = f"bore-v{version}-{target}.{ext}"
        return f"https://github.com/{BORE_GITHUB_REPO}/releases/download/v{version}/{filename}"

    def _get_latest_version(self) -> Optional[str]:
        """Fetch the latest bore version from GitHub API."""
        try:
            resp = requests.get(
                f"https://api.github.com/repos/{BORE_GITHUB_REPO}/releases/latest",
                timeout=5,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.ok:
                tag = resp.json().get("tag_name", "")
                return tag.lstrip("v") if tag else None
        except (requests.RequestException, KeyError, ValueError):
            pass
        return None

    def _download_and_extract(self, url: str, target: str) -> None:
        """Download the archive and extract the bore binary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Download
            resp = requests.get(url, timeout=30, stream=True)
            resp.raise_for_status()

            if "windows" in target:
                archive_path = tmp_path / "bore.zip"
                with open(archive_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                with zipfile.ZipFile(archive_path) as zf:
                    # Extract bore.exe from the zip
                    for name in zf.namelist():
                        if name.endswith("bore.exe"):
                            zf.extract(name, tmp_path)
                            extracted = tmp_path / name
                            extracted.rename(self.binary_path)
                            return
                raise RuntimeError("bore.exe not found in zip archive")
            else:
                archive_path = tmp_path / "bore.tar.gz"
                with open(archive_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                with tarfile.open(archive_path, "r:gz") as tf:
                    # Extract bore binary from the tarball
                    for member in tf.getmembers():
                        if member.name.endswith("/bore") or member.name == "bore":
                            tf.extract(member, tmp_path)
                            extracted = tmp_path / member.name
                            extracted.rename(self.binary_path)
                            return
                raise RuntimeError("bore binary not found in tar archive")
