"""
Screencast service for capturing browser frames via Chrome DevTools Protocol.

Uses the CDP Page.startScreencast API to stream frames from the browser
to the Python CLI for video recording.
"""

import atexit
import base64
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import requests

from inspekt.config import get_bridge_port, load_config

# Track temp directories for cleanup on exit (prevents leaks on Ctrl+C)
_temp_dirs_to_cleanup: list[Path] = []


def _cleanup_temp_dirs():
    """Clean up any temp directories created by ScreencastCapture instances."""
    for temp_dir in _temp_dirs_to_cleanup:
        if temp_dir.exists():
            try:
                shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass  # Best effort cleanup
    _temp_dirs_to_cleanup.clear()


# Register cleanup handler
atexit.register(_cleanup_temp_dirs)


class ScreencastError(Exception):
    """Error during screencast capture."""

    pass


class ScreencastCapture:
    """
    Captures browser frames using Chrome DevTools Protocol screencast.

    The screencast API streams frames from the browser as they change,
    which is more efficient than periodic screenshots.

    Usage:
        capture = ScreencastCapture()
        capture.start()
        # ... do browser interactions ...
        frames = capture.stop()
        # frames is list of (timestamp, image_bytes) tuples
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int | None = None,
        fps: int | None = None,
        quality: int | None = None,
        format: str = "jpeg",
    ):
        """
        Initialize screencast capture.

        Args:
            host: Bridge server host
            port: Bridge server port. If None, auto-detects based on environment.
            fps: Target frame rate (5-30). If None, uses config default.
            quality: JPEG quality (50-100). If None, uses config default.
            format: Image format ('jpeg' or 'png')
        """
        # Auto-detect port based on environment (VM vs normal)
        if port is None:
            port = get_bridge_port()

        self.base_url = f"http://{host}:{port}"
        self._session = requests.Session()

        # Load defaults from config
        config = load_config()
        video_config = config.get("video", {})

        self.fps = fps if fps is not None else video_config.get("fps", 10)
        self.quality = quality if quality is not None else video_config.get("quality", 80)
        self.format = format

        # Clamp values to valid ranges
        self.fps = max(5, min(30, self.fps))
        self.quality = max(50, min(100, self.quality))

        # State tracking
        self._is_capturing = False
        self._frames: list[tuple[float, bytes]] = []
        self._start_time: float = 0
        self._temp_dir: Path | None = None

    @property
    def is_capturing(self) -> bool:
        """Whether screencast is currently active."""
        return self._is_capturing

    @property
    def frame_count(self) -> int:
        """Number of frames captured so far."""
        return len(self._frames)

    def start(self) -> dict[str, Any]:
        """
        Start screencast capture.

        Returns:
            Response dict with ok status

        Raises:
            ScreencastError: If capture fails to start
        """
        if self._is_capturing:
            return {"ok": True, "message": "Already capturing"}

        try:
            response = self._session.post(
                f"{self.base_url}/screencast/start",
                json={
                    "fps": self.fps,
                    "quality": self.quality,
                    "format": self.format,
                },
                timeout=10.0,
            )

            if response.status_code != 200:
                raise ScreencastError(f"Failed to start screencast: HTTP {response.status_code}")

            data = response.json()
            if not data.get("ok"):
                raise ScreencastError(
                    f"Failed to start screencast: {data.get('error', 'Unknown error')}"
                )

            self._is_capturing = True
            self._frames = []
            self._start_time = time.time()

            return data

        except requests.RequestException as e:
            raise ScreencastError(f"Failed to start screencast: {e}")

    def stop(self) -> list[tuple[float, bytes]]:
        """
        Stop screencast capture and return collected frames.

        Returns:
            List of (timestamp, image_bytes) tuples

        Note:
            Always returns collected frames, even if stop request fails.
            This ensures frames aren't lost due to browser disconnection.
        """
        if not self._is_capturing:
            return self._frames

        # First, stop the CDP screencast on the browser side
        # This prevents new frames from being generated
        try:
            response = self._session.post(
                f"{self.base_url}/screencast/stop",
                timeout=5.0,
            )

            if response.status_code != 200:
                print(f"[Screencast] Warning: stop returned HTTP {response.status_code}")

        except requests.RequestException as e:
            print(f"[Screencast] Warning: stop request failed: {e}")

        # Wait a moment for frames in transit to arrive at the bridge
        # CDP frames are POSTed asynchronously from extension to bridge
        time.sleep(0.3)

        # Now collect any remaining frames (multiple attempts for reliability)
        for _ in range(3):
            collected = self._collect_frames()
            if collected == 0:
                break  # No more frames arriving
            time.sleep(0.1)

        self._is_capturing = False
        return self._frames

    def _collect_frames(self) -> int:
        """
        Collect pending frames from the bridge server.

        Returns:
            Number of new frames collected
        """
        try:
            response = self._session.get(
                f"{self.base_url}/screencast/frames",
                timeout=5.0,
            )

            if response.status_code != 200:
                return 0

            data = response.json()
            if not data.get("ok"):
                return 0

            frames_data = data.get("frames", [])
            new_count = 0

            for frame in frames_data:
                timestamp = frame.get("timestamp", time.time())
                image_b64 = frame.get("data", "")

                if image_b64:
                    try:
                        image_bytes = base64.b64decode(image_b64)
                        self._frames.append((timestamp, image_bytes))
                        new_count += 1
                    except Exception:
                        pass  # Skip invalid frames

            return new_count

        except requests.RequestException:
            return 0

    def collect_pending(self) -> int:
        """
        Collect any pending frames from the server.

        Call this periodically during long operations to prevent
        frame buffer overflow on the server.

        Returns:
            Number of new frames collected
        """
        if not self._is_capturing:
            return 0
        return self._collect_frames()

    def get_frames(self) -> list[tuple[float, bytes]]:
        """
        Get all collected frames.

        Returns:
            List of (timestamp, image_bytes) tuples
        """
        return self._frames.copy()

    def set_capturing(self, value: bool):
        """
        Set the capturing state.

        This is a public method to set the capture state flag, allowing
        external code to mark capture as active without accessing private attributes.

        Args:
            value: Whether capture is active
        """
        self._is_capturing = value

    def save_frames_to_disk(self, output_dir: Path | None = None) -> Path:
        """
        Save all frames to disk as individual image files.

        Args:
            output_dir: Directory to save frames. If None, uses temp directory.

        Returns:
            Path to directory containing frame files
        """
        if output_dir is None:
            if self._temp_dir is None:
                self._temp_dir = Path(tempfile.mkdtemp(prefix="inspekt_screencast_"))
                # Register for cleanup on exit (prevents leaks on Ctrl+C)
                _temp_dirs_to_cleanup.append(self._temp_dir)
            output_dir = self._temp_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        ext = "jpg" if self.format == "jpeg" else self.format

        for i, (_timestamp, image_bytes) in enumerate(self._frames):
            frame_path = output_dir / f"frame_{i:05d}.{ext}"
            frame_path.write_bytes(image_bytes)

        return output_dir

    def clear(self):
        """Clear all collected frames."""
        self._frames = []

    def get_duration(self) -> float:
        """
        Get estimated duration of captured content in seconds.

        Returns:
            Duration based on first and last frame timestamps
        """
        if len(self._frames) < 2:
            return 0.0

        first_ts = self._frames[0][0]
        last_ts = self._frames[-1][0]
        return last_ts - first_ts

    def get_stats(self) -> dict[str, Any]:
        """
        Get statistics about the capture.

        Returns:
            Dictionary with frame count, duration, avg fps, etc.
        """
        duration = self.get_duration()
        frame_count = len(self._frames)

        # Calculate total size
        total_size = sum(len(data) for _, data in self._frames)

        return {
            "frame_count": frame_count,
            "duration_seconds": round(duration, 2),
            "average_fps": round(frame_count / duration, 1) if duration > 0 else 0,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "target_fps": self.fps,
            "quality": self.quality,
            "format": self.format,
        }

    def check_interrupted(self) -> dict[str, Any] | None:
        """
        Check if screencast was interrupted (e.g., user opened DevTools).

        Returns:
            Dict with interrupt info if interrupted, None otherwise.
            Dict contains: reason (str), frames_captured (int), timestamp (float)
        """
        try:
            response = self._session.get(
                f"{self.base_url}/screencast/status",
                timeout=2.0,
            )

            if response.status_code != 200:
                return None

            data = response.json()
            return data.get("interrupted")

        except requests.RequestException:
            return None


# Convenience function for simple captures
def capture_screencast(
    duration_seconds: float,
    fps: int = 10,
    quality: int = 80,
    host: str = "127.0.0.1",
    port: int | None = None,
) -> list[tuple[float, bytes]]:
    """
    Capture screencast for a specified duration.

    Simple helper for capturing a fixed-duration screencast.

    Args:
        duration_seconds: How long to capture
        fps: Target frame rate
        quality: JPEG quality (50-100)
        host: Bridge server host
        port: Bridge server port. If None, auto-detects based on environment.

    Returns:
        List of (timestamp, image_bytes) tuples
    """
    capture = ScreencastCapture(host=host, port=port, fps=fps, quality=quality)
    capture.start()

    # Collect frames periodically during capture
    end_time = time.time() + duration_seconds
    while time.time() < end_time:
        time.sleep(0.5)
        capture.collect_pending()

    return capture.stop()
