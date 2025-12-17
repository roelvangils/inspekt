"""FFmpeg detection and installation utilities for video recording."""

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import click


def get_ffmpeg_path() -> Path | None:
    """
    Find the ffmpeg executable path.

    Returns:
        Path to ffmpeg if found, None otherwise
    """
    ffmpeg_path = shutil.which("ffmpeg")
    return Path(ffmpeg_path) if ffmpeg_path else None


def get_ffmpeg_version() -> str | None:
    """
    Get the installed ffmpeg version string.

    Returns:
        Version string (e.g., "6.1.1") if ffmpeg is installed, None otherwise
    """
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return None

    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        # Parse version from first line: "ffmpeg version 6.1.1 Copyright..."
        first_line = result.stdout.split("\n")[0]
        if "version" in first_line:
            parts = first_line.split()
            for i, part in enumerate(parts):
                if part == "version" and i + 1 < len(parts):
                    return parts[i + 1]
        return "unknown"
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
        return None


def is_ffmpeg_installed() -> bool:
    """Check if ffmpeg is available on the system."""
    return get_ffmpeg_path() is not None


def get_install_command() -> tuple[str, str] | None:
    """
    Get the platform-specific install command for ffmpeg.

    Returns:
        Tuple of (command, description) or None if platform not supported
    """
    system = platform.system().lower()

    if system == "darwin":
        # macOS - check for Homebrew
        if shutil.which("brew"):
            return ("brew install ffmpeg", "Homebrew")
        return None

    elif system == "linux":
        # Linux - check for common package managers
        if shutil.which("apt"):
            return ("sudo apt install -y ffmpeg", "apt")
        elif shutil.which("dnf"):
            return ("sudo dnf install -y ffmpeg", "dnf")
        elif shutil.which("pacman"):
            return ("sudo pacman -S --noconfirm ffmpeg", "pacman")
        elif shutil.which("yum"):
            return ("sudo yum install -y ffmpeg", "yum")
        return None

    elif system == "windows":
        # Windows - suggest manual download
        return None

    return None


def prompt_install_ffmpeg() -> bool:
    """
    Prompt the user to install ffmpeg.

    Returns:
        True if ffmpeg was installed successfully, False otherwise
    """
    install_info = get_install_command()
    system = platform.system().lower()

    click.echo()
    click.secho("ffmpeg not found", fg="yellow", bold=True)
    click.echo("Video recording requires ffmpeg for encoding.")
    click.echo()

    if system == "windows":
        click.echo("Please download ffmpeg from:")
        click.secho("  https://ffmpeg.org/download.html", fg="cyan")
        click.echo()
        click.echo("After installation, add ffmpeg to your PATH and try again.")
        return False

    if install_info is None:
        click.echo("Could not detect a supported package manager.")
        click.echo("Please install ffmpeg manually from:")
        click.secho("  https://ffmpeg.org/download.html", fg="cyan")
        return False

    command, pkg_manager = install_info

    click.echo(f"Install ffmpeg using {pkg_manager}?")
    click.secho(f"  {command}", fg="cyan")
    click.echo()

    if not click.confirm("Proceed with installation?", default=True):
        click.echo("Aborted. Please install ffmpeg manually to use video recording.")
        return False

    # Run the install command
    click.echo()
    click.echo(f"Running: {command}")
    click.echo()

    try:
        # Use shell=True for commands with sudo
        result = subprocess.run(
            command,
            shell=True,
            check=False,
        )

        if result.returncode == 0:
            # Verify installation
            if is_ffmpeg_installed():
                version = get_ffmpeg_version()
                click.secho(f"ffmpeg {version} installed successfully!", fg="green")
                return True
            else:
                click.secho("Installation completed but ffmpeg not found in PATH.", fg="yellow")
                click.echo("You may need to restart your terminal.")
                return False
        else:
            click.secho("Installation failed.", fg="red")
            click.echo("Please try installing ffmpeg manually.")
            return False

    except (subprocess.SubprocessError, OSError) as e:
        click.secho(f"Installation error: {e}", fg="red")
        return False


def ensure_ffmpeg(auto_prompt: bool = True) -> bool:
    """
    Ensure ffmpeg is available, optionally prompting for installation.

    Args:
        auto_prompt: If True and ffmpeg is not found, prompt user to install

    Returns:
        True if ffmpeg is available, False otherwise
    """
    if is_ffmpeg_installed():
        return True

    if auto_prompt:
        return prompt_install_ffmpeg()

    return False


def get_ffmpeg_info() -> dict:
    """
    Get detailed information about the ffmpeg installation.

    Returns:
        Dictionary with ffmpeg info:
        - installed: bool
        - path: str or None
        - version: str or None
    """
    path = get_ffmpeg_path()
    return {
        "installed": path is not None,
        "path": str(path) if path else None,
        "version": get_ffmpeg_version() if path else None,
    }


def get_ffprobe_path() -> Path | None:
    """
    Find the ffprobe executable path.

    Returns:
        Path to ffprobe if found, None otherwise
    """
    ffprobe_path = shutil.which("ffprobe")
    return Path(ffprobe_path) if ffprobe_path else None


def probe_video(video_path: Path | str) -> dict | None:
    """
    Probe a video file to get its metadata using ffprobe.

    Args:
        video_path: Path to the video file

    Returns:
        Dictionary with video info:
        - width: int (video width in pixels)
        - height: int (video height in pixels)
        - duration: float (duration in seconds)
        - file_size: int (file size in bytes)
        - codec: str (video codec name)
        - fps: float (frames per second)
        Or None if probing fails
    """
    ffprobe_path = get_ffprobe_path()
    if not ffprobe_path:
        return None

    video_path = Path(video_path)
    if not video_path.exists():
        return None

    try:
        # Run ffprobe to get JSON output with stream and format info
        result = subprocess.run(
            [
                str(ffprobe_path),
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-select_streams", "v:0",  # First video stream only
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return None

        import json
        data = json.loads(result.stdout)

        # Extract video stream info
        streams = data.get("streams", [])
        video_stream = streams[0] if streams else {}

        # Extract format info
        format_info = data.get("format", {})

        # Parse FPS from r_frame_rate (e.g., "30/1" or "30000/1001")
        fps = 0.0
        r_frame_rate = video_stream.get("r_frame_rate", "0/1")
        if "/" in r_frame_rate:
            num, den = r_frame_rate.split("/")
            if int(den) > 0:
                fps = int(num) / int(den)

        return {
            "width": video_stream.get("width", 0),
            "height": video_stream.get("height", 0),
            "duration": float(format_info.get("duration", 0)),
            "file_size": int(format_info.get("size", 0)),
            "codec": video_stream.get("codec_name", "unknown"),
            "fps": round(fps, 2),
        }

    except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError, ValueError, json.JSONDecodeError):
        return None


def merge_audio_video(
    video_path: Path | str,
    audio_path: Path | str,
    output_path: Path | str,
    timeout: int = 300
) -> dict:
    """
    Merge an audio track with a video file using FFmpeg.

    The video stream is copied without re-encoding (fast), and the audio
    is encoded as AAC for broad compatibility.

    Args:
        video_path: Path to the input video file (MP4, WebM, etc.)
        audio_path: Path to the audio file (WAV, MP3, etc.)
        output_path: Path for the output video with audio
        timeout: Maximum time in seconds to wait for FFmpeg (default 300s / 5 min)

    Returns:
        Dictionary with result:
        - ok: bool (True if successful)
        - error: str (error message if failed)
        - output_path: str (path to output file if successful)
    """
    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        return {"ok": False, "error": "FFmpeg not found"}

    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)

    if not video_path.exists():
        return {"ok": False, "error": f"Video file not found: {video_path}"}

    if not audio_path.exists():
        return {"ok": False, "error": f"Audio file not found: {audio_path}"}

    # Build FFmpeg command
    # -y: Overwrite output without asking
    # -i: Input files (video first, then audio)
    # -c:v copy: Copy video stream without re-encoding (fast)
    # -c:a aac: Encode audio as AAC (broad compatibility)
    # -b:a 128k: Audio bitrate
    # -shortest: Match duration to shortest stream
    # -map 0:v:0: Use video from first input
    # -map 1:a:0: Use audio from second input
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-map", "0:v:0",
        "-map", "1:a:0",
        str(output_path)
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        if result.returncode == 0 and output_path.exists():
            return {
                "ok": True,
                "output_path": str(output_path)
            }
        else:
            error_msg = result.stderr.strip() if result.stderr else "Unknown error"
            # Truncate long error messages
            if len(error_msg) > 500:
                error_msg = error_msg[:500] + "..."
            return {
                "ok": False,
                "error": f"FFmpeg failed: {error_msg}"
            }

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"FFmpeg timed out after {timeout}s"}
    except (subprocess.SubprocessError, OSError) as e:
        return {"ok": False, "error": f"FFmpeg error: {e}"}


if __name__ == "__main__":
    # Test the module
    info = get_ffmpeg_info()
    if info["installed"]:
        print(f"ffmpeg found: {info['path']}")
        print(f"Version: {info['version']}")
    else:
        print("ffmpeg not installed")
        sys.exit(1)
