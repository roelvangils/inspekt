"""Smoke tests to verify basic functionality and imports."""


class TestImports:
    """Test that all modules can be imported without errors."""

    def test_import_inspekt_package(self):
        """Test importing the inspekt package."""
        import inspekt

        assert hasattr(inspekt, "__version__")
        assert inspekt.__version__ == "1.0.0"

    def test_import_cli(self):
        """Test importing the CLI module."""
        from inspekt.app import cli

        assert hasattr(cli, "cli")
        assert callable(cli.cli)

    def test_import_client(self):
        """Test importing the client module."""
        from inspekt import client

        assert hasattr(client, "BridgeClient")
        assert callable(client.BridgeClient)

    def test_import_config(self):
        """Test importing the config module."""
        from inspekt import config

        assert hasattr(config, "load_config")
        assert hasattr(config, "DEFAULT_CONFIG")
        assert callable(config.load_config)

    def test_import_bridge_ws(self):
        """Test importing the bridge_ws module."""
        from inspekt import bridge_ws

        assert hasattr(bridge_ws, "main")
        assert callable(bridge_ws.main)


class TestProjectStructure:
    """Test that essential project files and directories exist."""

    def test_project_root_exists(self, project_root):
        """Test that project root directory exists."""
        assert project_root.exists()
        assert project_root.is_dir()

    def test_inspekt_package_exists(self, project_root):
        """Test that inspekt package exists."""
        inspekt_dir = project_root / "inspekt"
        assert inspekt_dir.exists()
        assert inspekt_dir.is_dir()
        assert (inspekt_dir / "__init__.py").exists()

    def test_scripts_directory_exists(self, scripts_dir):
        """Test that scripts directory exists and contains JavaScript files."""
        assert scripts_dir.exists()
        assert scripts_dir.is_dir()

        # Check for at least some key scripts
        expected_scripts = [
            "control.js",
            "extract_links.js",
            "click_element.js",
            "get_inspected.js",
        ]

        for script in expected_scripts:
            script_path = scripts_dir / script
            assert script_path.exists(), f"Missing script: {script}"
            assert script_path.suffix == ".js"

    def test_documentation_exists(self, project_root):
        """Test that documentation files exist."""
        docs = [
            "README.md",
            "CHANGELOG.md",
            "CLAUDE.md",
            "CONTRIBUTING.md",
            "SECURITY.md",
        ]

        for doc in docs:
            doc_path = project_root / doc
            assert doc_path.exists(), f"Missing documentation: {doc}"

    def test_configuration_files_exist(self, project_root):
        """Test that configuration files exist."""
        configs = [
            "pyproject.toml",
            ".editorconfig",
            ".pre-commit-config.yaml",
        ]

        for config in configs:
            config_path = project_root / config
            assert config_path.exists(), f"Missing config file: {config}"


class TestConfig:
    """Test configuration loading."""

    def test_default_config_structure(self):
        """Test that DEFAULT_CONFIG has expected structure."""
        from inspekt.config import DEFAULT_CONFIG

        assert "ai-language" in DEFAULT_CONFIG
        assert "control" in DEFAULT_CONFIG
        assert isinstance(DEFAULT_CONFIG["control"], dict)

    def test_load_config_returns_dict(self):
        """Test that load_config returns a dictionary."""
        from inspekt.config import load_config

        config = load_config()
        assert isinstance(config, dict)
        assert "ai-language" in config
        assert "control" in config

    def test_validate_control_config(self, sample_config):
        """Test control config validation."""
        from inspekt.config import validate_control_config

        validated = validate_control_config(sample_config)
        assert isinstance(validated, dict)

        # Check key fields exist
        assert "auto-refocus" in validated
        assert "focus-outline" in validated
        assert "navigation-wrap" in validated

    def test_validate_control_config_with_invalid_values(self):
        """Test that validation normalizes invalid values."""
        from inspekt.config import validate_control_config

        invalid_config = {
            "control": {
                "auto-refocus": "invalid",
                "click-delay": -5,
                "focus-size": 0,
            }
        }

        validated = validate_control_config(invalid_config)

        # Should fall back to defaults
        assert validated["auto-refocus"] == "only-spa"
        assert validated["click-delay"] == 0
        assert validated["focus-size"] >= 1  # Normalized to minimum 1


class TestClient:
    """Test BridgeClient basic functionality (without running server)."""

    def test_bridge_client_instantiation(self):
        """Test that BridgeClient can be instantiated."""
        from inspekt.client import BridgeClient

        client = BridgeClient()
        assert client is not None
        assert hasattr(client, "base_url")
        assert client.base_url == "http://127.0.0.1:8765"

    def test_bridge_client_custom_host_port(self):
        """Test BridgeClient with custom host and port."""
        from inspekt.client import BridgeClient

        client = BridgeClient(host="localhost", port=9999)
        assert client.base_url == "http://localhost:9999"

    def test_bridge_client_has_methods(self):
        """Test that BridgeClient has expected methods."""
        from inspekt.client import BridgeClient

        client = BridgeClient()
        assert hasattr(client, "is_alive")
        assert hasattr(client, "execute")
        assert hasattr(client, "execute_file")
        assert callable(client.is_alive)
        assert callable(client.execute)
        assert callable(client.execute_file)


class TestCLI:
    """Test CLI basic functionality."""

    def test_cli_command_group_exists(self):
        """Test that main CLI command group exists."""
        from inspekt.app.cli import cli

        assert cli is not None
        assert hasattr(cli, "name")

    def test_cli_has_commands(self):
        """Test that CLI has expected commands."""
        import click

        from inspekt.app.cli import cli

        # The group lazy-loads commands, so cli.commands is empty until
        # list_commands() resolves them.
        commands = cli.list_commands(click.Context(cli))

        expected_commands = [
            "eval",
            "exec",
            "start",
            "status",
            "control",
            "links",  # Note: command is 'links' not 'extract-links'
        ]

        for cmd in expected_commands:
            assert cmd in commands, f"Missing CLI command: {cmd}"


class TestBridgeWS:
    """Test bridge WebSocket server basic functionality."""

    def test_bridge_ws_constants(self):
        """Test that bridge_ws has expected constants."""
        from inspekt import bridge_ws

        assert hasattr(bridge_ws, "HOST")
        assert hasattr(bridge_ws, "PORT")
        assert bridge_ws.HOST == "127.0.0.1"
        assert bridge_ws.PORT == 8765

    def test_cleanup_old_requests_function_exists(self):
        """Test that cleanup function exists."""
        from inspekt import bridge_ws

        assert hasattr(bridge_ws, "cleanup_old_requests")
        assert callable(bridge_ws.cleanup_old_requests)

    def test_websocket_handler_exists(self):
        """Test that WebSocket handler exists."""
        from inspekt import bridge_ws

        assert hasattr(bridge_ws, "websocket_handler")
        assert callable(bridge_ws.websocket_handler)

    def test_http_handlers_exist(self):
        """Test that HTTP handlers exist."""
        from inspekt import bridge_ws

        handlers = [
            "handle_http_run",
            "handle_http_result",
            "handle_http_notifications",
            "handle_http_health",
            "handle_http_reinit_control",
        ]

        for handler in handlers:
            assert hasattr(bridge_ws, handler), f"Missing handler: {handler}"
            assert callable(getattr(bridge_ws, handler))
