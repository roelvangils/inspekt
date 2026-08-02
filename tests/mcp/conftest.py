"""
Shared fixtures for MCP tests.

These fixtures provide mocked dependencies for testing MCP tools
without requiring a running bridge server or browser.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch


@pytest.fixture
def reset_registry():
    """Reset CommandRegistry singleton before each test."""
    import inspekt.core.commands as commands_module
    from inspekt.core.registry import CommandRegistry

    # Save current state — the singleton AND the registration guard flag.
    # Restoring only the instance leaves _commands_registered=True, which
    # makes later register_all_commands() calls no-op on an empty registry.
    old_instance = CommandRegistry._instance
    old_registered = commands_module._commands_registered

    # Reset for test isolation
    CommandRegistry._instance = None
    commands_module._commands_registered = False

    yield

    commands_module._commands_registered = old_registered
    # Restore after test
    CommandRegistry._instance = old_instance


@pytest.fixture
def mock_bridge_executor():
    """
    Mock BridgeExecutor that doesn't require WebSocket connection.

    Returns a mock that simulates successful bridge communication.
    """
    with patch("inspekt.services.bridge_executor.BridgeExecutor") as MockExecutor:
        instance = Mock()
        instance.host = "127.0.0.1"
        instance.port = 8765
        instance.is_server_running.return_value = True
        instance.has_active_browser_connection.return_value = True
        instance.execute.return_value = {
            "ok": True,
            "result": {"url": "https://example.com", "title": "Example"}
        }
        MockExecutor.return_value = instance
        yield instance


@pytest.fixture
def mock_script_loader():
    """Mock ScriptLoader that returns test scripts."""
    with patch("inspekt.services.script_loader.ScriptLoader") as MockLoader:
        instance = Mock()
        instance.load_script_sync.return_value = "console.log('test');"
        instance.load_script_async = AsyncMock(return_value="console.log('test');")
        MockLoader.return_value = instance
        yield instance


@pytest.fixture
def tool_provider(mock_bridge_executor, mock_script_loader):
    """Create ToolProvider with mocked dependencies."""
    from inspekt.app.mcp.tools import ToolProvider

    return ToolProvider(mock_bridge_executor, mock_script_loader)


@pytest.fixture
def mcp_router(reset_registry):
    """Create MCPToolRouter with real registry."""
    from inspekt.core.commands import register_all_commands
    from inspekt.core.generators.mcp import MCPToolRouter

    register_all_commands()
    return MCPToolRouter()
