"""Unit tests for Pydantic domain models."""

import pytest
from pydantic import ValidationError

from inspekt.domain.models import (
    ControlConfig,
    ExecuteRequest,
    ExecuteResult,
    HealthResponse,
    PingMessage,
    PongMessage,
    RefocusNotification,
    ReinitControlRequest,
    RunRequest,
    RunResponse,
    ZenConfig,
    create_execute_request,
    create_pong_message,
    parse_incoming_message,
)


class TestExecuteRequest:
    """Test ExecuteRequest model."""

    def test_valid_execute_request(self):
        """Test creating a valid execute request."""
        req = ExecuteRequest(request_id="test-123", code="console.log('test')")
        assert req.type == "execute"
        assert req.request_id == "test-123"
        assert req.code == "console.log('test')"

    def test_execute_request_missing_fields(self):
        """Test execute request with missing required fields."""
        with pytest.raises(ValidationError):
            ExecuteRequest(request_id="test-123")  # Missing code

    def test_create_execute_request_helper(self):
        """Test helper function for creating execute requests."""
        req = create_execute_request("id-123", "alert('hi')")
        assert isinstance(req, ExecuteRequest)
        assert req.request_id == "id-123"
        assert req.code == "alert('hi')"


class TestExecuteResult:
    """Test ExecuteResult model."""

    def test_valid_result_success(self):
        """Test creating a successful result."""
        result = ExecuteResult(
            request_id="test-123",
            ok=True,
            result={"data": "test"},
            url="https://example.com",
            title="Example",
        )
        assert result.type == "result"
        assert result.ok is True
        assert result.result == {"data": "test"}
        assert result.error is None

    def test_valid_result_error(self):
        """Test creating an error result."""
        result = ExecuteResult(
            request_id="test-123",
            ok=False,
            error="ReferenceError: foo is not defined",
        )
        assert result.ok is False
        assert result.error == "ReferenceError: foo is not defined"
        assert result.result is None


class TestWebSocketMessages:
    """Test WebSocket message models."""

    def test_ping_message(self):
        """Test ping message."""
        ping = PingMessage()
        assert ping.type == "ping"

    def test_pong_message(self):
        """Test pong message."""
        pong = PongMessage()
        assert pong.type == "pong"

    def test_create_pong_helper(self):
        """Test pong creation helper."""
        pong = create_pong_message()
        assert isinstance(pong, PongMessage)
        assert pong.type == "pong"

    def test_reinit_control_request(self):
        """Test reinit control request."""
        req = ReinitControlRequest(config={"verbose": True})
        assert req.type == "reinit_control"
        assert req.config == {"verbose": True}

    def test_refocus_notification(self):
        """Test refocus notification."""
        notif = RefocusNotification(success=True, message="Focused on button")
        assert notif.type == "refocus_notification"
        assert notif.success is True
        assert notif.message == "Focused on button"


class TestHTTPModels:
    """Test HTTP API models."""

    def test_run_request_valid(self):
        """Test valid run request."""
        req = RunRequest(code="document.title")
        assert req.code == "document.title"

    def test_run_request_empty_code(self):
        """Test run request with empty code."""
        with pytest.raises(ValidationError):
            RunRequest(code="")  # min_length=1

    def test_run_response(self):
        """Test run response."""
        resp = RunResponse(ok=True, request_id="test-123")
        assert resp.ok is True
        assert resp.request_id == "test-123"
        assert resp.error is None

    def test_health_response(self):
        """Test health response."""
        resp = HealthResponse(
            ok=True,
            timestamp=1234567890.0,
            server_version="1.0.0",
            uptime_seconds=42.0,
            host="127.0.0.1",
            port=8765,
            websocket_port=8766,
            connected_browsers=1,
            pending=0,
            completed=5,
            total_processed=5,
            total_succeeded=5,
            total_failed=0,
            last_activity=1234567890.0,
        )
        assert resp.ok is True
        assert resp.timestamp == 1234567890.0
        assert resp.connected_browsers == 1


class TestControlConfig:
    """Test ControlConfig model."""

    def test_default_control_config(self):
        """Test control config with all defaults."""
        config = ControlConfig()
        assert config.auto_refocus == "only-spa"
        assert config.focus_outline == "custom"
        assert config.speak_name is False
        assert config.navigation_wrap is True
        assert config.click_delay == 0
        assert config.focus_color == "#0066ff"
        assert config.focus_size == 3

    def test_control_config_with_values(self):
        """Test control config with custom values."""
        config = ControlConfig(auto_refocus="always", focus_outline="none", click_delay=100)
        assert config.auto_refocus == "always"
        assert config.focus_outline == "none"
        assert config.click_delay == 100

    def test_control_config_validation_auto_refocus(self):
        """Test auto_refocus validation."""
        with pytest.raises(ValidationError):
            ControlConfig(auto_refocus="invalid")

    def test_control_config_validation_focus_size(self):
        """Test focus_size validation (must be >= 1)."""
        with pytest.raises(ValidationError):
            ControlConfig(focus_size=0)

    def test_control_config_validation_click_delay(self):
        """Test click_delay validation (must be >= 0)."""
        with pytest.raises(ValidationError):
            ControlConfig(click_delay=-1)

    def test_control_config_alias_support(self):
        """Test that aliases work (kebab-case)."""
        config = ControlConfig(**{"auto-refocus": "never", "click-delay": 50})
        assert config.auto_refocus == "never"
        assert config.click_delay == 50


class TestZenConfig:
    """Test ZenConfig model."""

    def test_default_zen_config(self):
        """Test zen config with defaults."""
        config = ZenConfig()
        assert config.ai_language == "auto"
        assert isinstance(config.control, ControlConfig)
        assert config.control.auto_refocus == "only-spa"

    def test_zen_config_with_custom_control(self):
        """Test zen config with custom control settings."""
        config = ZenConfig(
            ai_language="en",
            control=ControlConfig(auto_refocus="always", verbose=False),
        )
        assert config.ai_language == "en"
        assert config.control.auto_refocus == "always"
        assert config.control.verbose is False

    def test_zen_config_alias_support(self):
        """Test zen config with aliases."""
        config = ZenConfig(**{"ai-language": "nl"})
        assert config.ai_language == "nl"


class TestParseIncomingMessage:
    """Test parse_incoming_message function."""

    def test_parse_execute_result(self):
        """Test parsing an execute result message."""
        data = {
            "type": "result",
            "request_id": "test-123",
            "ok": True,
            "result": "test",
        }
        msg = parse_incoming_message(data)
        assert isinstance(msg, ExecuteResult)
        assert msg.request_id == "test-123"

    def test_parse_ping(self):
        """Test parsing a ping message."""
        data = {"type": "ping"}
        msg = parse_incoming_message(data)
        assert isinstance(msg, PingMessage)

    def test_parse_reinit_control(self):
        """Test parsing a reinit control message."""
        data = {"type": "reinit_control", "config": {"verbose": True}}
        msg = parse_incoming_message(data)
        assert isinstance(msg, ReinitControlRequest)
        assert msg.config == {"verbose": True}

    def test_parse_refocus_notification(self):
        """Test parsing a refocus notification."""
        data = {"type": "refocus_notification", "success": True, "message": "OK"}
        msg = parse_incoming_message(data)
        assert isinstance(msg, RefocusNotification)

    def test_parse_unknown_type(self):
        """Test parsing unknown message type."""
        data = {"type": "unknown"}
        with pytest.raises(ValueError, match="Unknown message type"):
            parse_incoming_message(data)
