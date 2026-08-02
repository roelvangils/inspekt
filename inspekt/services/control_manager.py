"""
Control Manager Service - State management for control mode.

This service handles:
- Control mode state tracking
- Notification polling and handling
- Auto-restart logic
- Accessibility announcements coordination
"""

from __future__ import annotations

import subprocess
from typing import Any

import requests


class ControlNotification:
    """Represents a notification from the browser during control mode."""

    def __init__(self, notification_type: str, message: str, data: dict[str, Any] | None = None):
        """
        Initialize a control notification.

        Args:
            notification_type: Type of notification (e.g., "refocus")
            message: Human-readable message
            data: Additional notification data
        """
        self.type = notification_type
        self.message = message
        self.data = data or {}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlNotification:
        """Create notification from API response dictionary."""
        return cls(
            notification_type=data.get("type", "unknown"),
            message=data.get("message", ""),
            data=data,
        )


class ControlManager:
    """Service for managing browser control mode state and notifications."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        """
        Initialize the control manager.

        Args:
            host: Bridge server host
            port: Bridge server port
        """
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    def check_notifications(self, timeout: float = 0.5) -> list[ControlNotification]:
        """
        Check for pending notifications from the browser.

        Args:
            timeout: Request timeout in seconds

        Returns:
            List of notifications (empty if none available or on error)
        """
        try:
            resp = requests.get(
                f"{self.base_url}/notifications",
                timeout=timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok") and data.get("notifications"):
                    return [ControlNotification.from_dict(n) for n in data["notifications"]]
        except (requests.RequestException, ValueError):
            # Silently ignore notification check errors
            pass

        return []

    def handle_refocus_notification(
        self,
        notification: ControlNotification,
        speak_enabled: bool = False,
        speak_command: str = "say",
    ) -> None:
        """
        Handle a refocus notification by announcing it.

        Args:
            notification: The refocus notification
            speak_enabled: If True, use text-to-speech
            speak_command: Command to use for TTS (default: "say" for macOS)
        """
        import sys

        # Always print the message
        sys.stderr.write(f"\r\n{notification.message}\r\n")
        sys.stderr.flush()

        # Optionally speak the message
        if speak_enabled:
            try:
                subprocess.run(
                    [speak_command, notification.message],
                    check=False,
                    timeout=5,
                    capture_output=True,
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                # TTS not available or timed out, continue silently
                pass

    def announce_accessible_name(
        self,
        accessible_name: str,
        role: str | None = None,
        announce_role: bool = False,
        speak_command: str = "say",
    ) -> None:
        """
        Announce the accessible name of a focused element via text-to-speech.

        Args:
            accessible_name: The accessible name to announce
            role: Element role (e.g., "button", "link")
            announce_role: If True, prepend role to announcement
            speak_command: Command to use for TTS (default: "say" for macOS)
        """
        if not accessible_name.strip():
            return

        # Build the text to speak
        speak_text = accessible_name.strip()

        # Optionally announce role
        if announce_role and role:
            speak_text = f"{role}, {speak_text}"

        try:
            subprocess.run(
                [speak_command, speak_text],
                check=False,
                timeout=5,
                capture_output=True,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # TTS not available or timed out, continue silently
            pass

    def check_needs_restart(self, result: dict[str, Any]) -> bool:
        """
        Check if control mode needs to be restarted (e.g., after navigation).

        Args:
            result: Execution result from bridge

        Returns:
            True if restart is needed
        """
        if not result.get("ok"):
            return False

        response = result.get("result", {})
        if isinstance(response, dict):
            return response.get("needsRestart", False)

        return False

    def format_restart_message(self, verbose: bool = False) -> str:
        """
        Get the restart message to display.

        Args:
            verbose: If True, include more details

        Returns:
            Formatted restart message
        """
        if verbose:
            return "🔄 Reinitializing control mode after navigation (verbose mode)...\r\n"
        else:
            return "🔄 Reinitializing after navigation...\r\n"

    def format_success_message(self, verbose: bool = False) -> str:
        """
        Get the success message after restart.

        Args:
            verbose: If True, include more details

        Returns:
            Formatted success message
        """
        if verbose:
            return "✅ Control restored successfully!\r\n"
        else:
            return "✅ Control restored!\r\n"


# Global manager instance (lazy-initialized)
_default_manager: ControlManager | None = None


def get_control_manager(
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ControlManager:
    """
    Get the default control manager instance (singleton pattern).

    Args:
        host: Bridge server host
        port: Bridge server port

    Returns:
        Shared ControlManager instance
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = ControlManager(host=host, port=port)
    return _default_manager
