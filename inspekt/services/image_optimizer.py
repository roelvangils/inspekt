"""
Image optimization service for Inspekt.

Provides PNG optimization using oxipng (a Rust-based PNG optimizer).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import click


def is_oxipng_installed() -> bool:
    """
    Check if oxipng is installed and available.

    Returns:
        bool: True if oxipng is installed, False otherwise
    """
    return shutil.which("oxipng") is not None


def prompt_install_oxipng() -> bool:
    """
    Prompt user to install oxipng.

    Returns:
        bool: True if user wants to install, False otherwise
    """
    click.echo("\n📦 oxipng is not installed.")
    click.echo("oxipng is a fast PNG optimizer written in Rust that can reduce file sizes by 10-50%.")
    click.echo("\nInstallation options:")
    click.echo("  • macOS:   brew install oxipng")
    click.echo("  • Linux:   cargo install oxipng  (requires Rust)")
    click.echo("  • Windows: cargo install oxipng  (requires Rust)")
    click.echo("\nOr download from: https://github.com/shssoichiro/oxipng/releases")

    return click.confirm("\nWould you like to install oxipng now via cargo?", default=False)


def install_oxipng_via_cargo() -> bool:
    """
    Attempt to install oxipng using cargo.

    Returns:
        bool: True if installation succeeded, False otherwise
    """
    # Check if cargo is installed
    if not shutil.which("cargo"):
        click.echo("\n❌ Error: Rust/cargo is not installed.", err=True)
        click.echo("Install Rust from: https://rustup.rs/", err=True)
        click.echo("Then run: cargo install oxipng", err=True)
        return False

    click.echo("\n📦 Installing oxipng via cargo...")
    click.echo("This may take a few minutes...")

    try:
        # Run cargo install oxipng
        result = subprocess.run(
            ["cargo", "install", "oxipng"],
            check=True,
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            click.echo("✅ oxipng installed successfully!")
            return True
        else:
            click.echo(f"❌ Installation failed: {result.stderr}", err=True)
            return False

    except subprocess.CalledProcessError as e:
        click.echo(f"❌ Installation failed: {e.stderr}", err=True)
        return False
    except Exception as e:
        click.echo(f"❌ Unexpected error during installation: {e}", err=True)
        return False


def optimize_png(file_path: Path, level: int = 3, strip: bool = True) -> int | None:
    """
    Optimize a PNG file using oxipng.

    Args:
        file_path: Path to the PNG file to optimize
        level: Optimization level (0-6, default: 3)
               Higher = slower but better compression
        strip: Whether to strip metadata (default: True)

    Returns:
        int: Optimized file size in bytes, or None if optimization failed/skipped

    Raises:
        FileNotFoundError: If file doesn't exist
    """
    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Check if oxipng is installed
    if not is_oxipng_installed():
        # First time - prompt for installation
        if prompt_install_oxipng():
            if install_oxipng_via_cargo():
                # Verify installation
                if not is_oxipng_installed():
                    click.echo("❌ Installation completed but oxipng is still not available.", err=True)
                    click.echo("You may need to restart your shell or add cargo bin to PATH.", err=True)
                    return None
            else:
                return None
        else:
            click.echo("\n💡 Tip: Install oxipng for automatic PNG optimization with --optimize flag.")
            return None

    # Run oxipng
    try:
        args = [
            "oxipng",
            str(file_path),
            f"-o{level}",  # Optimization level
            "--quiet",    # Suppress progress output
        ]

        if strip:
            args.append("--strip=all")  # Strip all metadata

        result = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True
        )

        # Get optimized file size
        return file_path.stat().st_size

    except subprocess.CalledProcessError as e:
        # oxipng returns non-zero if file couldn't be optimized further
        # This is normal - file might already be optimal
        if "already optimized" in e.stderr.lower() or e.returncode == 2:
            return file_path.stat().st_size
        raise RuntimeError(f"oxipng failed: {e.stderr}")

    except Exception as e:
        raise RuntimeError(f"Unexpected error during optimization: {e}")


def optimize_png_batch(file_paths: list[Path], level: int = 3, strip: bool = True) -> dict[Path, int]:
    """
    Optimize multiple PNG files.

    Args:
        file_paths: List of paths to PNG files
        level: Optimization level (0-6, default: 3)
        strip: Whether to strip metadata (default: True)

    Returns:
        dict: Map of file paths to optimized sizes (None if failed)
    """
    if not is_oxipng_installed():
        click.echo("Warning: oxipng is not installed. Skipping optimization.", err=True)
        return {path: None for path in file_paths}

    results = {}
    for path in file_paths:
        try:
            size = optimize_png(path, level=level, strip=strip)
            results[path] = size
        except Exception as e:
            click.echo(f"Warning: Failed to optimize {path}: {e}", err=True)
            results[path] = None

    return results
