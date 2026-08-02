"""
Unit tests for MCP tool generation and validation.

No external dependencies - all bridge calls mocked.
Run with: pytest tests/mcp/test_mcp_unit.py -v
"""

import json

import pytest
from pydantic import ValidationError

from inspekt.app.mcp import schemas
from inspekt.app.mcp.registry import BUILTIN_TOOLS, get_all_tools


class TestMCPToolGeneration:
    """Tests for generate_mcp_tool() function."""

    def test_generate_tool_has_required_fields(self, reset_registry):
        """Generated tool must have name, description, inputSchema."""
        from inspekt.core.commands import register_all_commands
        from inspekt.core.generators.mcp import generate_mcp_tool
        from inspekt.core.registry import get_registry

        register_all_commands()
        registry = get_registry()

        for cmd in registry.get_for_mcp():
            tool = generate_mcp_tool(cmd, registry)
            assert tool.name, f"{cmd.id} missing name"
            assert tool.description, f"{cmd.id} missing description"
            assert tool.input_schema, f"{cmd.id} missing inputSchema"
            assert tool.input_schema.get("type") == "object", f"{cmd.id} schema type not 'object'"

    def test_all_builtin_tools_have_unique_names(self):
        """No duplicate tool names allowed."""
        tools = get_all_tools()
        names = [t.name for t in tools]
        duplicates = [n for n in names if names.count(n) > 1]
        assert len(names) == len(set(names)), f"Duplicate names found: {set(duplicates)}"

    def test_builtin_tool_count(self):
        """Verify expected number of built-in tools."""
        tools = BUILTIN_TOOLS
        assert len(tools) >= 20, f"Expected at least 20 tools, got {len(tools)}"

    def test_all_tools_have_categories(self):
        """Every tool must have a category."""
        for tool in BUILTIN_TOOLS:
            assert tool.category, f"{tool.name} missing category"

    def test_all_tools_have_descriptions(self):
        """Every tool must have a non-empty description."""
        for tool in BUILTIN_TOOLS:
            assert tool.description, f"{tool.name} missing description"
            assert len(tool.description) > 10, f"{tool.name} description too short"


class TestParameterValidation:
    """Tests for Pydantic schema validation."""

    def test_navigate_params_requires_url(self):
        """URL is required for navigate_to_url."""
        with pytest.raises(ValidationError):
            schemas.NavigateToUrlParams()

    def test_navigate_params_accepts_valid_url(self):
        """Valid URL passes validation."""
        params = schemas.NavigateToUrlParams(url="https://example.com")
        assert params.url == "https://example.com"

    def test_navigate_params_wait_for_optional(self):
        """wait_for is optional with valid literals."""
        params = schemas.NavigateToUrlParams(url="https://example.com", wait_for="load")
        assert params.wait_for == "load"

        params = schemas.NavigateToUrlParams(url="https://example.com", wait_for="networkidle")
        assert params.wait_for == "networkidle"

    def test_execute_js_requires_code(self):
        """Code is required for execute_javascript."""
        with pytest.raises(ValidationError):
            schemas.ExecuteJavaScriptParams()

    def test_execute_js_timeout_default(self):
        """Timeout has default value of 30."""
        params = schemas.ExecuteJavaScriptParams(code="1+1")
        assert params.timeout == 30

    def test_execute_js_custom_timeout(self):
        """Custom timeout is accepted."""
        params = schemas.ExecuteJavaScriptParams(code="1+1", timeout=60)
        assert params.timeout == 60

    def test_click_element_requires_selector(self):
        """Selector is required for click_element."""
        with pytest.raises(ValidationError):
            schemas.ClickElementParams()

    def test_click_element_click_type_enum(self):
        """click_type only accepts valid literals."""
        # Valid types
        params = schemas.ClickElementParams(selector="#btn", click_type="single")
        assert params.click_type == "single"

        params = schemas.ClickElementParams(selector="#btn", click_type="double")
        assert params.click_type == "double"

        params = schemas.ClickElementParams(selector="#btn", click_type="right")
        assert params.click_type == "right"

    def test_type_text_requires_text(self):
        """Text is required for type_text."""
        with pytest.raises(ValidationError):
            schemas.TypeTextParams()

    def test_type_text_typing_speed_enum(self):
        """typing_speed only accepts valid literals."""
        for speed in ["instant", "fast", "normal", "slow"]:
            params = schemas.TypeTextParams(text="hello", typing_speed=speed)
            assert params.typing_speed == speed

    def test_run_axe_level_validation(self):
        """WCAG level must be valid."""
        # Valid levels
        for level in ["2a", "2aa", "2aaa", "21a", "21aa", "22aa"]:
            params = schemas.RunAxeParams(level=level)
            assert params.level == level

    def test_check_autocomplete_confidence_bounds(self):
        """Confidence threshold must be 0-1."""
        # Valid
        params = schemas.CheckAutocompleteParams(confidence_threshold=0.5)
        assert params.confidence_threshold == 0.5

        params = schemas.CheckAutocompleteParams(confidence_threshold=0.0)
        assert params.confidence_threshold == 0.0

        params = schemas.CheckAutocompleteParams(confidence_threshold=1.0)
        assert params.confidence_threshold == 1.0

    def test_get_selected_text_format_enum(self):
        """format only accepts valid literals."""
        for fmt in ["text", "html", "markdown"]:
            params = schemas.GetSelectedTextParams(format=fmt)
            assert params.format == fmt

    def test_take_screenshot_target_enum(self):
        """target only accepts valid literals."""
        for target in ["viewport", "page", "element"]:
            params = schemas.TakeScreenshotParams(target=target)
            assert params.target == target

    def test_take_screenshot_format_enum(self):
        """format only accepts valid literals."""
        for fmt in ["png", "jpeg"]:
            params = schemas.TakeScreenshotParams(format=fmt)
            assert params.format == fmt

    def test_set_cookie_requires_name_and_value(self):
        """name and value are required for set_cookie."""
        with pytest.raises(ValidationError):
            schemas.SetCookieParams()

        with pytest.raises(ValidationError):
            schemas.SetCookieParams(name="test")

        # Valid
        params = schemas.SetCookieParams(name="test", value="value")
        assert params.name == "test"
        assert params.value == "value"

    def test_get_console_logs_level_enum(self):
        """level only accepts valid literals."""
        for level in ["all", "error", "warn", "log", "info", "debug"]:
            params = schemas.GetConsoleLogsParams(level=level)
            assert params.level == level


class TestResponseSerialization:
    """Tests for response model serialization."""

    def test_navigate_response_to_json(self):
        """NavigateResponse serializes to valid JSON."""
        response = schemas.NavigateResponse(
            success=True, url="https://example.com", title="Example", message="OK"
        )
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["success"] is True
        assert parsed["url"] == "https://example.com"
        assert parsed["title"] == "Example"

    def test_navigate_response_without_optional_fields(self):
        """NavigateResponse works without optional message."""
        response = schemas.NavigateResponse(
            success=True, url="https://example.com", title="Example"
        )
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["success"] is True

    def test_execute_javascript_response(self):
        """ExecuteJavaScriptResponse serializes correctly."""
        response = schemas.ExecuteJavaScriptResponse(success=True, result={"foo": "bar"})
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["success"] is True
        assert parsed["result"] == {"foo": "bar"}

    def test_execute_javascript_response_with_console(self):
        """ExecuteJavaScriptResponse includes console output."""
        response = schemas.ExecuteJavaScriptResponse(
            success=True, result=42, console_output=["log: hello", "log: world"]
        )
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["console_output"] == ["log: hello", "log: world"]

    def test_get_page_info_response(self):
        """GetPageInfoResponse serializes correctly."""
        response = schemas.GetPageInfoResponse(
            success=True,
            url="https://example.com",
            title="Example",
            viewport_width=1920,
            viewport_height=1080,
            scroll_x=0,
            scroll_y=100,
        )
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["viewport_width"] == 1920
        assert parsed["scroll_y"] == 100

    def test_extract_links_response(self):
        """ExtractLinksResponse serializes correctly."""
        response = schemas.ExtractLinksResponse(
            success=True,
            links=[
                schemas.LinkInfo(
                    url="https://example.com/page1",  # Note: uses 'url' not 'href'
                    text="Page 1",
                    type="internal",
                )
            ],
            count=1,
        )
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["count"] == 1
        assert len(parsed["links"]) == 1
        assert parsed["links"][0]["url"] == "https://example.com/page1"

    def test_run_axe_response_empty_violations(self):
        """RunAxeResponse serializes with empty violations."""
        # Note: summary is optional and typed as AxeSummary
        response = schemas.RunAxeResponse(
            success=True,
            url="https://example.com",
            violations=[],
        )
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["success"] is True
        assert isinstance(parsed["violations"], list)
        assert len(parsed["violations"]) == 0


class TestHandlerResolution:
    """Tests for handler import and resolution."""

    def test_get_handler_from_callable(self):
        """Direct function reference works."""
        from inspekt.core.commands.base import Category, CommandDefinition
        from inspekt.core.generators.mcp import get_handler

        async def test_handler(params):
            return {"success": True}

        cmd = CommandDefinition(
            id="test",
            name="Test",
            category=Category.NAVIGATION,
            description="Test command for unit testing",
            params_schema=schemas.NavigateToUrlParams,
            response_schema=schemas.NavigateResponse,
            handler=test_handler,
        )

        handler = get_handler(cmd)
        assert handler is test_handler

    def test_get_handler_from_string_path(self, reset_registry):
        """String path handler resolution works."""
        from inspekt.core.commands import register_all_commands
        from inspekt.core.generators.mcp import get_handler
        from inspekt.core.registry import get_registry

        register_all_commands()
        registry = get_registry()

        # Find a command with string handler path
        for cmd in registry.get_for_mcp():
            if isinstance(cmd.handler, str):
                handler = get_handler(cmd)
                assert callable(handler), f"{cmd.id} handler not callable"
                break


class TestInputSchemas:
    """Tests for input schema generation."""

    def test_all_input_schemas_are_objects(self):
        """All input schemas must be JSON Schema objects."""
        for tool in BUILTIN_TOOLS:
            schema = tool.input_schema
            assert schema.get("type") == "object", f"{tool.name} schema type not 'object'"

    def test_required_fields_listed(self):
        """Required fields appear in 'required' array."""
        # NavigateToUrlParams has required 'url'
        navigate_tool = next(t for t in BUILTIN_TOOLS if t.name == "navigate_to_url")
        schema = navigate_tool.input_schema
        assert "url" in schema.get("required", [])

    def test_optional_fields_have_defaults(self):
        """Optional fields have default values or aren't required."""
        # ExecuteJavaScriptParams has optional 'timeout'
        exec_tool = next(t for t in BUILTIN_TOOLS if t.name == "execute_javascript")
        schema = exec_tool.input_schema
        required = schema.get("required", [])
        assert "timeout" not in required
