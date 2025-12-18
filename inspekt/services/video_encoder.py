"""
Video encoder service using ffmpeg for assembling screencast frames into video files.

Supports MP4 (H.264) and WebM (VP9) output formats.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

import click

from inspekt.services.ffmpeg_utils import ensure_ffmpeg, get_ffmpeg_path


class VideoEncoderError(Exception):
    """Error during video encoding."""
    pass


class VideoEncoder:
    """
    Encodes a sequence of image frames into a video file using ffmpeg.

    Supports:
    - MP4 with H.264 codec (best compatibility)
    - WebM with VP9 codec (smaller files, web-native)
    """

    def __init__(
        self,
        fps: int = 10,
        output_format: str = "mp4",
        crf: int = 23,
        preset: str = "medium",
        crop_top: int = 0,
    ):
        """
        Initialize video encoder.

        Args:
            fps: Output video frame rate
            output_format: 'mp4' or 'webm'
            crf: Constant Rate Factor for quality (lower = better, 0-51)
            preset: Encoding speed/quality preset for H.264
                   ('ultrafast', 'fast', 'medium', 'slow', 'veryslow')
            crop_top: Pixels to crop from top of video (e.g., automation banner)
        """
        self.fps = fps
        self.output_format = output_format.lower()
        self.crf = crf
        self.preset = preset
        self.crop_top = crop_top

        # Validate format
        if self.output_format not in ("mp4", "webm"):
            raise ValueError(f"Unsupported format: {output_format}. Use 'mp4' or 'webm'.")

    def encode_frames(
        self,
        frames_dir: Path,
        output_path: Path,
        frame_pattern: str = "frame_%05d.jpg",
        progress_callback: Callable[[int, int], None] = None,
    ) -> dict[str, Any]:
        """
        Encode frames from a directory into a video file.

        Args:
            frames_dir: Directory containing numbered frame images
            output_path: Output video file path
            frame_pattern: Pattern for frame filenames (default: frame_00000.jpg)
            progress_callback: Optional callback(current, total) for progress updates

        Returns:
            Dictionary with encoding stats:
            - ok: bool
            - output_path: str
            - file_size_bytes: int
            - duration_seconds: float
            - frame_count: int

        Raises:
            VideoEncoderError: If encoding fails
        """
        # Ensure ffmpeg is available
        if not ensure_ffmpeg(auto_prompt=True):
            raise VideoEncoderError("ffmpeg is required for video encoding")

        ffmpeg_path = get_ffmpeg_path()
        frames_dir = Path(frames_dir)
        output_path = Path(output_path)

        # Count frames
        frame_ext = frame_pattern.split(".")[-1]
        frame_files = sorted(frames_dir.glob(f"*.{frame_ext}"))
        frame_count = len(frame_files)

        if frame_count == 0:
            raise VideoEncoderError(f"No frames found in {frames_dir} matching *.{frame_ext}")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Build ffmpeg command
        input_path = frames_dir / frame_pattern

        if self.output_format == "mp4":
            cmd = self._build_mp4_command(ffmpeg_path, input_path, output_path)
        else:
            cmd = self._build_webm_command(ffmpeg_path, input_path, output_path)

        # Run ffmpeg with timeout to prevent hangs
        try:
            if progress_callback:
                result = self._run_with_progress(cmd, frame_count, progress_callback)
            else:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=300,  # 5 minute timeout to prevent indefinite hangs
                )
        except subprocess.TimeoutExpired as e:
            raise VideoEncoderError(f"ffmpeg encoding timed out after 5 minutes (frames: {frame_count})")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise VideoEncoderError(f"ffmpeg encoding failed: {error_msg}")

        # Get output file stats
        if not output_path.exists():
            raise VideoEncoderError("Output file was not created")

        file_size = output_path.stat().st_size
        duration = frame_count / self.fps

        return {
            "ok": True,
            "output_path": str(output_path),
            "file_size_bytes": file_size,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "duration_seconds": round(duration, 2),
            "frame_count": frame_count,
            "fps": self.fps,
            "format": self.output_format,
        }

    def _build_mp4_command(
        self,
        ffmpeg_path: Path,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        """Build ffmpeg command for MP4 output."""
        # Build video filter chain
        # 1. Optionally crop from top (e.g., automation banner)
        # 2. Ensure even dimensions for H.264 codec
        filters = []
        if self.crop_top > 0:
            # crop=width:height:x:y - crop from top by reducing height and starting at y offset
            filters.append(f"crop=iw:ih-{self.crop_top}:0:{self.crop_top}")
        filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")  # Ensure even dimensions

        return [
            str(ffmpeg_path),
            "-y",  # Overwrite output
            "-framerate", str(self.fps),
            "-i", str(input_path),
            "-vf", ",".join(filters),
            "-c:v", "libx264",
            "-preset", self.preset,
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",  # Compatibility with most players
            "-movflags", "+faststart",  # Enable streaming
            str(output_path),
        ]

    def _build_webm_command(
        self,
        ffmpeg_path: Path,
        input_path: Path,
        output_path: Path,
    ) -> list[str]:
        """Build ffmpeg command for WebM output."""
        # Build video filter chain
        # 1. Optionally crop from top (e.g., automation banner)
        # 2. Ensure even dimensions for VP9 codec
        filters = []
        if self.crop_top > 0:
            # crop=width:height:x:y - crop from top by reducing height and starting at y offset
            filters.append(f"crop=iw:ih-{self.crop_top}:0:{self.crop_top}")
        filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")  # Ensure even dimensions

        return [
            str(ffmpeg_path),
            "-y",  # Overwrite output
            "-framerate", str(self.fps),
            "-i", str(input_path),
            "-vf", ",".join(filters),
            "-c:v", "libvpx-vp9",
            "-crf", str(self.crf),
            "-b:v", "0",  # Use CRF mode
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

    def _run_with_progress(
        self,
        cmd: list[str],
        total_frames: int,
        progress_callback: Callable[[int, int], None],
    ) -> subprocess.CompletedProcess:
        """
        Run ffmpeg with progress tracking.

        Note: ffmpeg progress parsing is complex. This provides a simple
        estimation based on time elapsed.
        """
        # For simplicity, just run and update progress at the end
        # Real progress tracking would require parsing ffmpeg stderr
        progress_callback(0, total_frames)

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        progress_callback(total_frames, total_frames)
        return result

    def encode_from_bytes(
        self,
        frames: list[tuple[float, bytes]],
        output_path: Path,
        progress_callback: Callable[[int, int], None] = None,
    ) -> dict[str, Any]:
        """
        Encode frames directly from memory (list of bytes).

        This saves frames to a temp directory with a concat demuxer file that
        preserves the actual timestamps from CDP screencast, then encodes.

        Args:
            frames: List of (timestamp, image_bytes) tuples
            output_path: Output video file path
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Encoding result dictionary
        """
        if not frames:
            raise VideoEncoderError("No frames to encode")

        # Ensure ffmpeg is available
        if not ensure_ffmpeg(auto_prompt=True):
            raise VideoEncoderError("ffmpeg is required for video encoding")

        ffmpeg_path = get_ffmpeg_path()
        output_path = Path(output_path)

        # Create temp directory for frames
        temp_dir = Path(tempfile.mkdtemp(prefix="inspekt_video_"))

        try:
            # Save frames to disk
            if progress_callback:
                progress_callback(0, len(frames))

            for i, (timestamp, image_bytes) in enumerate(frames):
                frame_path = temp_dir / f"frame_{i:05d}.jpg"
                frame_path.write_bytes(image_bytes)

            # Create concat demuxer file with actual frame durations
            # This tells FFmpeg exactly how long to display each frame
            concat_file = temp_dir / "frames.txt"
            with open(concat_file, "w") as f:
                for i, (timestamp, _) in enumerate(frames):
                    frame_path = temp_dir / f"frame_{i:05d}.jpg"

                    # Calculate duration until next frame (or use minimum for last frame)
                    if i < len(frames) - 1:
                        duration = frames[i + 1][0] - timestamp
                        # Ensure reasonable duration (at least 1/60s, at most 10s)
                        duration = max(0.0167, min(10.0, duration))
                    else:
                        # Last frame: hold for a reasonable duration
                        # Use average of previous durations, or 0.5s if single frame
                        if len(frames) > 1:
                            avg_duration = (frames[-1][0] - frames[0][0]) / (len(frames) - 1)
                            duration = max(0.1, min(2.0, avg_duration))
                        else:
                            duration = 0.5

                    f.write(f"file '{frame_path}'\n")
                    f.write(f"duration {duration:.6f}\n")

                # FFmpeg concat demuxer requires the last file to be listed again
                # without duration to properly handle the final frame
                if frames:
                    last_frame = temp_dir / f"frame_{len(frames)-1:05d}.jpg"
                    f.write(f"file '{last_frame}'\n")

            # Build video filter chain
            filters = []
            if self.crop_top > 0:
                filters.append(f"crop=iw:ih-{self.crop_top}:0:{self.crop_top}")
            filters.append("pad=ceil(iw/2)*2:ceil(ih/2)*2")
            filter_str = ",".join(filters) if filters else "null"

            # Build ffmpeg command using concat demuxer for timestamp-aware encoding
            if self.output_format == "mp4":
                cmd = [
                    str(ffmpeg_path),
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-vf", filter_str,
                    "-c:v", "libx264",
                    "-preset", self.preset,
                    "-crf", str(self.crf),
                    "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
            else:
                cmd = [
                    str(ffmpeg_path),
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-vf", filter_str,
                    "-c:v", "libvpx-vp9",
                    "-crf", str(self.crf),
                    "-b:v", "0",
                    "-pix_fmt", "yuv420p",
                    str(output_path),
                ]

            # Run ffmpeg
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                raise VideoEncoderError(f"ffmpeg encoding timed out after 5 minutes (frames: {len(frames)})")
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                raise VideoEncoderError(f"ffmpeg encoding failed: {error_msg}")

            # Get output file stats
            if not output_path.exists():
                raise VideoEncoderError("Output file was not created")

            file_size = output_path.stat().st_size

            # Calculate actual duration from timestamps
            if len(frames) >= 2:
                actual_duration = frames[-1][0] - frames[0][0]
            else:
                actual_duration = 0.5

            return {
                "ok": True,
                "output_path": str(output_path),
                "file_size_bytes": file_size,
                "file_size_mb": round(file_size / (1024 * 1024), 2),
                "duration_seconds": round(actual_duration, 2),
                "frame_count": len(frames),
                "fps": round(len(frames) / actual_duration, 1) if actual_duration > 0 else self.fps,
                "format": self.output_format,
            }

        finally:
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)


def encode_replay_video(
    frames: list[tuple[float, bytes]],
    output_path: str | Path,
    fps: int = 10,
    format: str = None,
    progress_callback: Callable[[int, int], None] = None,
    crop_top: int = 0,
) -> dict[str, Any]:
    """
    Convenience function to encode replay frames to video.

    Args:
        frames: List of (timestamp, image_bytes) from ScreencastCapture
        output_path: Output video path (format auto-detected from extension)
        fps: Output frame rate
        format: 'mp4' or 'webm'. If None, detected from output_path extension.
        progress_callback: Optional callback(current, total)
        crop_top: Pixels to crop from top of video (e.g., automation banner)

    Returns:
        Encoding result dictionary
    """
    output_path = Path(output_path)

    # Auto-detect format from extension
    if format is None:
        ext = output_path.suffix.lower()
        if ext == ".webm":
            format = "webm"
        else:
            format = "mp4"

    encoder = VideoEncoder(fps=fps, output_format=format, crop_top=crop_top)
    return encoder.encode_from_bytes(frames, output_path, progress_callback)


def show_encoding_progress(current: int, total: int):
    """
    Default progress callback that shows a CLI progress bar.

    Args:
        current: Current frame number
        total: Total frame count
    """
    if total == 0:
        return

    pct = current / total
    bar_width = 40
    filled = int(bar_width * pct)
    bar = "█" * filled + "░" * (bar_width - filled)

    # Use carriage return to update in place
    click.echo(f"\r[{bar}] {current}/{total} frames ({pct*100:.0f}%)", nl=False)

    if current >= total:
        click.echo()  # Newline when done
