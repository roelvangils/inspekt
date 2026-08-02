"""
Integration tests for unified storage CLI commands.

Tests the consolidated storage command that handles cookies, localStorage,
and sessionStorage through a unified interface with flag-based filtering.
"""

import json
from unittest.mock import Mock, patch

import pytest
from click.testing import CliRunner

from inspekt.app.cli import cli


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def runner():
    """Create a Click CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_executor():
    """Mock BridgeExecutor for storage command tests."""
    with patch("inspekt.app.cli.storage.get_executor") as mock_get_executor:
        mock_instance = Mock()
        mock_instance.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "origin": "https://example.com",
                "hostname": "example.com",
                "timestamp": "2025-11-15T10:00:00.000Z",
                "storage": {
                    "cookies": {
                        "ok": True,
                        "count": 2,
                        "items": [
                            {
                                "name": "session_id",
                                "value": "abc123",
                                "domain": "example.com",
                                "path": "/",
                                "secure": True,
                                "httpOnly": True,
                            }
                        ],
                        "apiUsed": "chrome.cookies",
                    },
                    "localStorage": {
                        "ok": True,
                        "count": 3,
                        "items": {
                            "user_token": "xyz789",
                            "theme": "dark",
                            "preferences": '{"lang":"en"}',
                        },
                    },
                    "sessionStorage": {
                        "ok": True,
                        "count": 1,
                        "items": {
                            "temp_data": "temporary",
                        },
                    },
                },
                "totals": {
                    "totalItems": 6,
                    "totalSize": 512,
                    "byType": {
                        "cookies": 2,
                        "localStorage": 3,
                        "sessionStorage": 1,
                    },
                },
            },
        }
        mock_get_executor.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_script_loader():
    """Mock ScriptLoader for storage script loading."""
    with patch("inspekt.app.cli.storage.ScriptLoader") as mock_loader_class:
        mock_instance = Mock()
        # Return script with placeholders that will be replaced
        mock_instance.load_script_sync.return_value = """
(async function() {
    const action = 'ACTION_PLACEHOLDER';
    const types = TYPES_PLACEHOLDER;
    const keyName = 'KEY_PLACEHOLDER';
    const value = 'VALUE_PLACEHOLDER';
    const options = OPTIONS_PLACEHOLDER;
    return { ok: true, storage: {}, action, types, keyName, value, options };
})()
        """
        mock_loader_class.return_value = mock_instance
        yield mock_instance


# =============================================================================
# Test Unified Storage List Command
# =============================================================================


class TestStorageListUnified:
    """Test unified storage list command with various flag combinations."""

    def test_list_all_storage_types_default(self, runner, mock_executor, mock_script_loader):
        """Test listing all storage types (default behavior)."""
        result = runner.invoke(cli, ["storage", "list"])

        assert result.exit_code == 0
        mock_executor.execute.assert_called_once()

        # Check that unified script was used with all types
        code = mock_executor.execute.call_args[0][0]
        assert '["cookies", "local", "session"]' in code

    def test_list_only_cookies(self, runner, mock_executor, mock_script_loader):
        """Test listing only cookies with --cookies flag."""
        result = runner.invoke(cli, ["storage", "list", "--cookies"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert '["cookies"]' in code

    def test_list_only_local_storage(self, runner, mock_executor, mock_script_loader):
        """Test listing only localStorage with --local flag."""
        result = runner.invoke(cli, ["storage", "list", "--local"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert '["local"]' in code

    def test_list_only_session_storage(self, runner, mock_executor, mock_script_loader):
        """Test listing only sessionStorage with --session flag."""
        result = runner.invoke(cli, ["storage", "list", "--session"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert '["session"]' in code

    def test_list_multiple_types_combined(self, runner, mock_executor, mock_script_loader):
        """Test listing multiple storage types with combined flags."""
        result = runner.invoke(cli, ["storage", "list", "--cookies", "--local"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        # Should include both cookies and local
        assert "cookies" in code
        assert "local" in code

    def test_list_all_flag_explicit(self, runner, mock_executor, mock_script_loader):
        """Test listing all storage types with explicit --all flag."""
        result = runner.invoke(cli, ["storage", "list", "--all"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert '["cookies", "local", "session"]' in code

    def test_list_json_output(self, runner, mock_executor, mock_script_loader):
        """Test JSON output format."""
        result = runner.invoke(cli, ["storage", "list", "--json"])

        assert result.exit_code == 0
        # Output should be valid JSON
        output_data = json.loads(result.output)
        assert "storage" in output_data
        assert "totals" in output_data

    def test_list_legacy_type_flag_cookies(self, runner, mock_executor, mock_script_loader):
        """Test backward compatibility with --type=cookies flag."""
        result = runner.invoke(cli, ["storage", "list", "--type", "cookies"])

        assert result.exit_code == 0
        # Should show deprecation warning
        assert "deprecated" in result.output.lower() or "warning" in result.output.lower()


# =============================================================================
# Test Storage Get Command
# =============================================================================


class TestStorageGet:
    """Test unified storage get command."""

    def test_get_from_local_storage(self, runner, mock_executor, mock_script_loader):
        """Test getting a key from localStorage."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "localStorage": {
                        "ok": True,
                        "key": "user_token",
                        "value": "xyz789",
                        "exists": True,
                    }
                },
            },
        }

        result = runner.invoke(cli, ["storage", "get", "user_token", "--local"])

        assert result.exit_code == 0
        # Output shows the value
        assert "xyz789" in result.output

    def test_get_from_cookies(self, runner, mock_executor, mock_script_loader):
        """Test getting a cookie by name."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "cookies": {
                        "ok": True,
                        "key": "session_id",
                        "value": "abc123",
                        "exists": True,
                    }
                },
            },
        }

        result = runner.invoke(cli, ["storage", "get", "session_id", "--cookies"])

        assert result.exit_code == 0
        # Output shows the value
        assert "abc123" in result.output

    def test_get_nonexistent_key(self, runner, mock_executor, mock_script_loader):
        """Test getting a non-existent key."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "localStorage": {
                        "ok": True,
                        "key": "nonexistent",
                        "value": None,
                        "exists": False,
                    }
                },
            },
        }

        result = runner.invoke(cli, ["storage", "get", "nonexistent", "--local"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()


# =============================================================================
# Test Storage Set Command
# =============================================================================


class TestStorageSet:
    """Test unified storage set command."""

    def test_set_local_storage_item(self, runner, mock_executor, mock_script_loader):
        """Test setting a localStorage item."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "localStorage": {
                        "ok": True,
                        "key": "test_key",
                        "value": "test_value",
                    }
                },
            },
        }

        result = runner.invoke(cli, ["storage", "set", "test_key", "test_value", "--local"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert "test_key" in code
        assert "test_value" in code

    def test_set_cookie_basic(self, runner, mock_executor, mock_script_loader):
        """Test setting a basic cookie."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "cookies": {
                        "ok": True,
                        "key": "cookie_name",
                        "value": "cookie_value",
                    }
                },
            },
        }

        result = runner.invoke(cli, ["storage", "set", "cookie_name", "cookie_value", "--cookies"])

        assert result.exit_code == 0

    def test_set_cookie_with_options(self, runner, mock_executor, mock_script_loader):
        """Test setting a cookie with security options."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {"ok": True, "storage": {"cookies": {"ok": True}}},
        }

        result = runner.invoke(
            cli,
            [
                "storage",
                "set",
                "secure_cookie",
                "value",
                "--cookies",
                "--secure",
                "--max-age",
                "3600",
                "--same-site",
                "Strict",
            ],
        )

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        # Check that options were passed
        assert "maxAge" in code or "3600" in code
        assert "secure" in code
        assert "Strict" in code


# =============================================================================
# Test Storage Delete Command
# =============================================================================


class TestStorageDelete:
    """Test unified storage delete command."""

    def test_delete_local_storage_item(self, runner, mock_executor, mock_script_loader):
        """Test deleting a localStorage item."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "localStorage": {
                        "ok": True,
                        "key": "to_delete",
                    }
                },
            },
        }

        result = runner.invoke(cli, ["storage", "delete", "to_delete", "--local"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert "delete" in code.lower()
        assert "to_delete" in code

    def test_delete_cookie(self, runner, mock_executor, mock_script_loader):
        """Test deleting a cookie."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "cookies": {
                        "ok": True,
                        "key": "cookie_to_delete",
                    }
                },
            },
        }

        result = runner.invoke(cli, ["storage", "delete", "cookie_to_delete", "--cookies"])

        assert result.exit_code == 0


# =============================================================================
# Test Storage Clear Command
# =============================================================================


class TestStorageClear:
    """Test unified storage clear command."""

    def test_clear_all_storage_types(self, runner, mock_executor, mock_script_loader):
        """Test clearing all storage types."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "cookies": {"ok": True, "deleted": 5},
                    "localStorage": {"ok": True, "deleted": 10},
                    "sessionStorage": {"ok": True, "deleted": 3},
                },
            },
        }

        # Provide 'y' to confirmation prompt
        result = runner.invoke(cli, ["storage", "clear", "--all"], input="y\n")

        assert result.exit_code == 0
        assert "5" in result.output or "deleted" in result.output.lower()

    def test_clear_only_cookies(self, runner, mock_executor, mock_script_loader):
        """Test clearing only cookies."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "cookies": {"ok": True, "deleted": 5},
                },
            },
        }

        # Provide 'y' to confirmation prompt
        result = runner.invoke(cli, ["storage", "clear", "--cookies"], input="y\n")

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert '["cookies"]' in code

    def test_clear_local_and_session(self, runner, mock_executor, mock_script_loader):
        """Test clearing localStorage and sessionStorage together."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {
                    "localStorage": {"ok": True, "deleted": 10},
                    "sessionStorage": {"ok": True, "deleted": 3},
                },
            },
        }

        # Provide 'y' to confirmation prompt
        result = runner.invoke(cli, ["storage", "clear", "--local", "--session"], input="y\n")

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert "local" in code
        assert "session" in code


# =============================================================================
# Test Error Handling
# =============================================================================


class TestStorageErrorHandling:
    """Test error handling in storage commands."""

    def test_executor_error_handling(self, runner, mock_executor, mock_script_loader):
        """Test handling of executor errors."""
        mock_executor.execute.return_value = {
            "ok": False,
            "error": "Failed to execute storage script",
        }

        result = runner.invoke(cli, ["storage", "list"])

        assert result.exit_code == 1
        assert "error" in result.output.lower()

    def test_script_not_found_error(self, runner, mock_executor):
        """Test handling when script is not found."""
        with patch("inspekt.app.cli.storage.ScriptLoader") as mock_loader_class:
            mock_instance = Mock()
            mock_instance.load_script_sync.side_effect = FileNotFoundError("Script not found")
            mock_loader_class.return_value = mock_instance

            result = runner.invoke(cli, ["storage", "list"])

            assert result.exit_code == 1
            assert "error" in result.output.lower()

    def test_storage_action_error(self, runner, mock_executor, mock_script_loader):
        """Test handling of storage action errors."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": False,
                "error": "localStorage is not available",
            },
        }

        result = runner.invoke(cli, ["storage", "list", "--local"])

        assert result.exit_code == 1
        assert "error" in result.output.lower()


# =============================================================================
# Test Backward Compatibility
# =============================================================================


class TestBackwardCompatibility:
    """Test backward compatibility with legacy commands."""

    def test_legacy_type_flag_local(self, runner, mock_executor, mock_script_loader):
        """Test --type=local for backward compatibility."""
        result = runner.invoke(cli, ["storage", "list", "--type", "local"])

        assert result.exit_code == 0
        # Should work but show deprecation warning
        code = mock_executor.execute.call_args[0][0]
        assert "local" in code

    def test_legacy_type_flag_session(self, runner, mock_executor, mock_script_loader):
        """Test --type=session for backward compatibility."""
        result = runner.invoke(cli, ["storage", "list", "--type", "session"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        assert "session" in code

    def test_legacy_type_flag_all(self, runner, mock_executor, mock_script_loader):
        """Test --type=all for backward compatibility."""
        result = runner.invoke(cli, ["storage", "list", "--type", "all"])

        assert result.exit_code == 0
        code = mock_executor.execute.call_args[0][0]
        # Should include all types
        assert "cookies" in code
        assert "local" in code
        assert "session" in code


# =============================================================================
# Test Script Placeholder Replacement
# =============================================================================


class TestScriptPlaceholders:
    """Test that script placeholders are correctly replaced."""

    def test_action_placeholder_replacement(self, runner, mock_executor, mock_script_loader):
        """Test ACTION_PLACEHOLDER is replaced correctly."""
        result = runner.invoke(cli, ["storage", "list"])

        code = mock_executor.execute.call_args[0][0]
        assert "ACTION_PLACEHOLDER" not in code
        assert "list" in code

    def test_types_placeholder_replacement(self, runner, mock_executor, mock_script_loader):
        """Test TYPES_PLACEHOLDER is replaced with JSON array."""
        result = runner.invoke(cli, ["storage", "list", "--cookies"])

        code = mock_executor.execute.call_args[0][0]
        assert "TYPES_PLACEHOLDER" not in code
        # Should be valid JSON array
        assert '["cookies"]' in code or "['cookies']" in code

    def test_key_placeholder_replacement(self, runner, mock_executor, mock_script_loader):
        """Test KEY_PLACEHOLDER is replaced correctly."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {
                "ok": True,
                "storage": {"localStorage": {"ok": True, "key": "test", "value": "val", "exists": True}},
            },
        }

        result = runner.invoke(cli, ["storage", "get", "test_key", "--local"])

        code = mock_executor.execute.call_args[0][0]
        assert "KEY_PLACEHOLDER" not in code
        assert "test_key" in code

    def test_value_placeholder_replacement(self, runner, mock_executor, mock_script_loader):
        """Test VALUE_PLACEHOLDER is replaced correctly."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {"ok": True, "storage": {"localStorage": {"ok": True}}},
        }

        result = runner.invoke(cli, ["storage", "set", "key", "test_value", "--local"])

        code = mock_executor.execute.call_args[0][0]
        assert "VALUE_PLACEHOLDER" not in code
        assert "test_value" in code

    def test_options_placeholder_replacement(self, runner, mock_executor, mock_script_loader):
        """Test OPTIONS_PLACEHOLDER is replaced with JSON object."""
        mock_executor.execute.return_value = {
            "ok": True,
            "result": {"ok": True, "storage": {"cookies": {"ok": True}}},
        }

        result = runner.invoke(
            cli,
            ["storage", "set", "cookie", "value", "--cookies", "--secure", "--max-age", "3600"],
        )

        code = mock_executor.execute.call_args[0][0]
        assert "OPTIONS_PLACEHOLDER" not in code
        # Should contain JSON with cookie options
        assert "secure" in code
        assert "3600" in code or "maxAge" in code
