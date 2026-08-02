"""Unit tests for ControlManager service."""

import subprocess
from unittest.mock import Mock, patch

import requests

from inspekt.services.control_manager import (
    ControlManager,
    ControlNotification,
    get_control_manager,
)


class TestControlNotification:
    """Test ControlNotification class."""

    def test_initialization_with_all_parameters(self):
        """Test initializing a ControlNotification with all parameters."""
        data = {"key": "value", "extra": "data"}
        notification = ControlNotification(
            notification_type="refocus", message="Focus restored", data=data
        )
        assert notification.type == "refocus"
        assert notification.message == "Focus restored"
        assert notification.data == {"key": "value", "extra": "data"}

    def test_initialization_without_data(self):
        """Test initializing a ControlNotification without data parameter."""
        notification = ControlNotification(notification_type="refocus", message="Focus restored")
        assert notification.type == "refocus"
        assert notification.message == "Focus restored"
        assert notification.data == {}

    def test_from_dict_with_all_fields(self):
        """Test creating ControlNotification from dict with all fields."""
        data = {
            "type": "refocus",
            "message": "Focus restored",
            "extra": "data",
        }
        notification = ControlNotification.from_dict(data)
        assert notification.type == "refocus"
        assert notification.message == "Focus restored"
        assert notification.data == data

    def test_from_dict_with_missing_type(self):
        """Test creating ControlNotification from dict with missing type field."""
        data = {"message": "Some message"}
        notification = ControlNotification.from_dict(data)
        assert notification.type == "unknown"
        assert notification.message == "Some message"

    def test_from_dict_with_missing_message(self):
        """Test creating ControlNotification from dict with missing message field."""
        data = {"type": "refocus"}
        notification = ControlNotification.from_dict(data)
        assert notification.type == "refocus"
        assert notification.message == ""

    def test_from_dict_with_empty_dict(self):
        """Test creating ControlNotification from empty dict."""
        notification = ControlNotification.from_dict({})
        assert notification.type == "unknown"
        assert notification.message == ""
        assert notification.data == {}

    def test_notification_attributes(self):
        """Test accessing notification attributes."""
        data = {"type": "refocus", "message": "Test", "foo": "bar"}
        notification = ControlNotification.from_dict(data)
        assert hasattr(notification, "type")
        assert hasattr(notification, "message")
        assert hasattr(notification, "data")
        assert notification.data["foo"] == "bar"


class TestControlManagerInitialization:
    """Test ControlManager initialization."""

    def test_default_host_and_port(self):
        """Test ControlManager initialization with default host and port."""
        manager = ControlManager()
        assert manager.host == "127.0.0.1"
        assert manager.port == 8765
        assert manager.base_url == "http://127.0.0.1:8765"

    def test_custom_host_and_port(self):
        """Test ControlManager initialization with custom host and port."""
        manager = ControlManager(host="localhost", port=9000)
        assert manager.host == "localhost"
        assert manager.port == 9000
        assert manager.base_url == "http://localhost:9000"

    def test_base_url_construction(self):
        """Test that base_url is correctly constructed from host and port."""
        manager = ControlManager(host="192.168.1.100", port=8080)
        assert manager.base_url == "http://192.168.1.100:8080"


class TestCheckNotifications:
    """Test check_notifications method."""

    @patch("inspekt.services.control_manager.requests.get")
    def test_successful_response_with_notifications(self, mock_get):
        """Test check_notifications with successful response containing notifications."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "notifications": [
                {"type": "refocus", "message": "Focus restored"},
                {"type": "navigation", "message": "Page loaded"},
            ],
        }
        mock_get.return_value = mock_response

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert len(notifications) == 2
        assert notifications[0].type == "refocus"
        assert notifications[0].message == "Focus restored"
        assert notifications[1].type == "navigation"
        assert notifications[1].message == "Page loaded"
        mock_get.assert_called_once_with("http://127.0.0.1:8765/notifications", timeout=0.5)

    @patch("inspekt.services.control_manager.requests.get")
    def test_successful_response_with_ok_false(self, mock_get):
        """Test check_notifications when response has ok=False."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": False,
            "notifications": [{"type": "test", "message": "Test"}],
        }
        mock_get.return_value = mock_response

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert notifications == []

    @patch("inspekt.services.control_manager.requests.get")
    def test_successful_response_with_empty_notifications(self, mock_get):
        """Test check_notifications with empty notifications array."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "notifications": []}
        mock_get.return_value = mock_response

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert notifications == []

    @patch("inspekt.services.control_manager.requests.get")
    def test_successful_response_without_notifications_field(self, mock_get):
        """Test check_notifications when response lacks notifications field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True}
        mock_get.return_value = mock_response

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert notifications == []

    @patch("inspekt.services.control_manager.requests.get")
    def test_non_200_status_code(self, mock_get):
        """Test check_notifications with non-200 status code."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert notifications == []

    @patch("inspekt.services.control_manager.requests.get")
    def test_request_exception(self, mock_get):
        """Test check_notifications with RequestException."""
        mock_get.side_effect = requests.RequestException("Connection error")

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert notifications == []

    @patch("inspekt.services.control_manager.requests.get")
    def test_value_error_invalid_json(self, mock_get):
        """Test check_notifications with ValueError (invalid JSON)."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert notifications == []

    @patch("inspekt.services.control_manager.requests.get")
    def test_custom_timeout(self, mock_get):
        """Test check_notifications with custom timeout."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "notifications": []}
        mock_get.return_value = mock_response

        manager = ControlManager()
        manager.check_notifications(timeout=2.0)

        mock_get.assert_called_once_with("http://127.0.0.1:8765/notifications", timeout=2.0)

    @patch("inspekt.services.control_manager.requests.get")
    def test_timeout_exception(self, mock_get):
        """Test check_notifications with timeout exception."""
        mock_get.side_effect = requests.Timeout("Request timed out")

        manager = ControlManager()
        notifications = manager.check_notifications()

        assert notifications == []


class TestHandleRefocusNotification:
    """Test handle_refocus_notification method."""

    @patch("sys.stderr")
    @patch("inspekt.services.control_manager.subprocess.run")
    def test_handle_refocus_without_speak(self, mock_subprocess, mock_stderr):
        """Test handling refocus notification without speak enabled."""
        notification = ControlNotification("refocus", "Focus restored to button")
        manager = ControlManager()

        manager.handle_refocus_notification(notification, speak_enabled=False)

        # Check that message was written to stderr
        mock_stderr.write.assert_called()
        calls = mock_stderr.write.call_args_list
        assert any("Focus restored to button" in str(call) for call in calls)
        mock_stderr.flush.assert_called_once()

        # Subprocess should not be called
        mock_subprocess.assert_not_called()

    @patch("sys.stderr")
    @patch("inspekt.services.control_manager.subprocess.run")
    def test_handle_refocus_with_speak_enabled(self, mock_subprocess, mock_stderr):
        """Test handling refocus notification with speak enabled."""
        notification = ControlNotification("refocus", "Focus restored to button")
        manager = ControlManager()

        manager.handle_refocus_notification(notification, speak_enabled=True)

        # Check that message was written to stderr
        mock_stderr.write.assert_called()
        mock_stderr.flush.assert_called_once()

        # Subprocess should be called with speak command
        mock_subprocess.assert_called_once_with(
            ["say", "Focus restored to button"],
            check=False,
            timeout=5,
            capture_output=True,
        )

    @patch("sys.stderr")
    @patch("inspekt.services.control_manager.subprocess.run")
    def test_handle_refocus_with_custom_speak_command(self, mock_subprocess, mock_stderr):
        """Test handling refocus notification with custom speak command."""
        notification = ControlNotification("refocus", "Test message")
        manager = ControlManager()

        manager.handle_refocus_notification(
            notification, speak_enabled=True, speak_command="espeak"
        )

        mock_subprocess.assert_called_once_with(
            ["espeak", "Test message"],
            check=False,
            timeout=5,
            capture_output=True,
        )

    @patch("sys.stderr")
    @patch("inspekt.services.control_manager.subprocess.run")
    def test_handle_refocus_with_speak_timeout(self, mock_subprocess, mock_stderr):
        """Test handling refocus notification when speak command times out."""
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd=["say", "test"], timeout=5)
        notification = ControlNotification("refocus", "Test message")
        manager = ControlManager()

        # Should not raise exception
        manager.handle_refocus_notification(notification, speak_enabled=True)

        mock_stderr.write.assert_called()
        mock_stderr.flush.assert_called_once()

    @patch("sys.stderr")
    @patch("inspekt.services.control_manager.subprocess.run")
    def test_handle_refocus_with_speak_command_not_found(self, mock_subprocess, mock_stderr):
        """Test handling refocus notification when speak command is not found."""
        mock_subprocess.side_effect = FileNotFoundError("say command not found")
        notification = ControlNotification("refocus", "Test message")
        manager = ControlManager()

        # Should not raise exception
        manager.handle_refocus_notification(notification, speak_enabled=True)

        mock_stderr.write.assert_called()
        mock_stderr.flush.assert_called_once()


class TestAnnounceAccessibleName:
    """Test announce_accessible_name method."""

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_without_role(self, mock_subprocess):
        """Test announcing accessible name without role."""
        manager = ControlManager()

        manager.announce_accessible_name("Submit Button")

        mock_subprocess.assert_called_once_with(
            ["say", "Submit Button"],
            check=False,
            timeout=5,
            capture_output=True,
        )

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_with_role_and_announce_role_true(self, mock_subprocess):
        """Test announcing accessible name with role when announce_role is True."""
        manager = ControlManager()

        manager.announce_accessible_name("Submit Button", role="button", announce_role=True)

        mock_subprocess.assert_called_once_with(
            ["say", "button, Submit Button"],
            check=False,
            timeout=5,
            capture_output=True,
        )

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_with_role_and_announce_role_false(self, mock_subprocess):
        """Test announcing accessible name with role when announce_role is False."""
        manager = ControlManager()

        manager.announce_accessible_name("Submit Button", role="button", announce_role=False)

        mock_subprocess.assert_called_once_with(
            ["say", "Submit Button"],
            check=False,
            timeout=5,
            capture_output=True,
        )

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_with_empty_accessible_name(self, mock_subprocess):
        """Test that empty accessible name does not trigger speech."""
        manager = ControlManager()

        manager.announce_accessible_name("")

        mock_subprocess.assert_not_called()

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_with_whitespace_only_accessible_name(self, mock_subprocess):
        """Test that whitespace-only accessible name does not trigger speech."""
        manager = ControlManager()

        manager.announce_accessible_name("   ")

        mock_subprocess.assert_not_called()

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_strips_whitespace(self, mock_subprocess):
        """Test that accessible name is stripped of whitespace."""
        manager = ControlManager()

        manager.announce_accessible_name("  Submit Button  ")

        mock_subprocess.assert_called_once_with(
            ["say", "Submit Button"],
            check=False,
            timeout=5,
            capture_output=True,
        )

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_with_custom_speak_command(self, mock_subprocess):
        """Test announcing with custom speak command."""
        manager = ControlManager()

        manager.announce_accessible_name("Test", speak_command="espeak")

        mock_subprocess.assert_called_once_with(
            ["espeak", "Test"],
            check=False,
            timeout=5,
            capture_output=True,
        )

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_with_timeout(self, mock_subprocess):
        """Test announcing when subprocess times out."""
        mock_subprocess.side_effect = subprocess.TimeoutExpired(cmd=["say", "test"], timeout=5)
        manager = ControlManager()

        # Should not raise exception
        manager.announce_accessible_name("Test")

    @patch("inspekt.services.control_manager.subprocess.run")
    def test_announce_with_command_not_found(self, mock_subprocess):
        """Test announcing when speak command is not found."""
        mock_subprocess.side_effect = FileNotFoundError("say command not found")
        manager = ControlManager()

        # Should not raise exception
        manager.announce_accessible_name("Test")


class TestCheckNeedsRestart:
    """Test check_needs_restart method."""

    def test_needs_restart_true(self):
        """Test check_needs_restart when needsRestart is True."""
        manager = ControlManager()
        result = {"ok": True, "result": {"needsRestart": True}}

        assert manager.check_needs_restart(result) is True

    def test_needs_restart_false(self):
        """Test check_needs_restart when needsRestart is False."""
        manager = ControlManager()
        result = {"ok": True, "result": {"needsRestart": False}}

        assert manager.check_needs_restart(result) is False

    def test_needs_restart_with_ok_false(self):
        """Test check_needs_restart when ok is False."""
        manager = ControlManager()
        result = {"ok": False, "result": {"needsRestart": True}}

        assert manager.check_needs_restart(result) is False

    def test_needs_restart_with_missing_needs_restart_field(self):
        """Test check_needs_restart when needsRestart field is missing."""
        manager = ControlManager()
        result = {"ok": True, "result": {}}

        assert manager.check_needs_restart(result) is False

    def test_needs_restart_with_non_dict_result(self):
        """Test check_needs_restart when result is not a dict."""
        manager = ControlManager()
        result = {"ok": True, "result": "not a dict"}

        assert manager.check_needs_restart(result) is False

    def test_needs_restart_with_result_as_list(self):
        """Test check_needs_restart when result is a list."""
        manager = ControlManager()
        result = {"ok": True, "result": [1, 2, 3]}

        assert manager.check_needs_restart(result) is False

    def test_needs_restart_with_missing_result_field(self):
        """Test check_needs_restart when result field is missing."""
        manager = ControlManager()
        result = {"ok": True}

        assert manager.check_needs_restart(result) is False

    def test_needs_restart_with_none_result(self):
        """Test check_needs_restart when result is None."""
        manager = ControlManager()
        result = {"ok": True, "result": None}

        assert manager.check_needs_restart(result) is False


class TestFormatMessages:
    """Test message formatting methods."""

    def test_format_restart_message_normal_mode(self):
        """Test format_restart_message in normal mode."""
        manager = ControlManager()
        message = manager.format_restart_message(verbose=False)

        assert "Reinitializing after navigation" in message
        assert message.endswith("\r\n")

    def test_format_restart_message_verbose_mode(self):
        """Test format_restart_message in verbose mode."""
        manager = ControlManager()
        message = manager.format_restart_message(verbose=True)

        assert "Reinitializing control mode after navigation (verbose mode)" in message
        assert message.endswith("\r\n")

    def test_format_success_message_normal_mode(self):
        """Test format_success_message in normal mode."""
        manager = ControlManager()
        message = manager.format_success_message(verbose=False)

        assert "Control restored!" in message
        assert message.endswith("\r\n")

    def test_format_success_message_verbose_mode(self):
        """Test format_success_message in verbose mode."""
        manager = ControlManager()
        message = manager.format_success_message(verbose=True)

        assert "Control restored successfully!" in message
        assert message.endswith("\r\n")


class TestSingletonPattern:
    """Test get_control_manager singleton pattern."""

    def test_get_control_manager_returns_instance(self):
        """Test that get_control_manager returns a ControlManager instance."""
        # Reset the global variable first
        import inspekt.services.control_manager

        inspekt.services.control_manager._default_manager = None

        manager = get_control_manager()

        assert isinstance(manager, ControlManager)
        assert manager.host == "127.0.0.1"
        assert manager.port == 8765

    def test_get_control_manager_returns_same_instance(self):
        """Test that get_control_manager returns the same instance on multiple calls."""
        # Reset the global variable first
        import inspekt.services.control_manager

        inspekt.services.control_manager._default_manager = None

        manager1 = get_control_manager()
        manager2 = get_control_manager()

        assert manager1 is manager2

    def test_get_control_manager_with_custom_params(self):
        """Test get_control_manager with custom host and port."""
        # Reset the global variable first
        import inspekt.services.control_manager

        inspekt.services.control_manager._default_manager = None

        manager = get_control_manager(host="localhost", port=9000)

        assert manager.host == "localhost"
        assert manager.port == 9000

    def test_get_control_manager_ignores_params_on_subsequent_calls(self):
        """Test that get_control_manager ignores parameters on subsequent calls."""
        # Reset the global variable first
        import inspekt.services.control_manager

        inspekt.services.control_manager._default_manager = None

        manager1 = get_control_manager(host="localhost", port=9000)
        manager2 = get_control_manager(host="different", port=8888)

        # Should return the same instance with original parameters
        assert manager1 is manager2
        assert manager2.host == "localhost"
        assert manager2.port == 9000
