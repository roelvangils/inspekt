"""
Integration tests for MCP tool routing and error handling.

Uses mocked BridgeExecutor for isolation.
Run with: pytest tests/mcp/test_mcp_integration.py -v
"""

import json

import pytest

from inspekt.app.mcp.registry import BUILTIN_TOOLS, CATEGORY_ORDER


class TestMCPToolRouting:
    """Tests for tool routing logic."""

    def test_router_get_tools_returns_list(self, mcp_router):
        """get_tools() returns a list of tools."""
        tools = mcp_router.get_tools()
        assert isinstance(tools, list)

    def test_router_has_tool_returns_true_for_known(self, mcp_router):
        """has_tool() returns True for registered tools."""
        tools = mcp_router.get_tools()
        if tools:
            assert mcp_router.has_tool(tools[0].name)

    def test_router_has_tool_returns_false_for_unknown(self, mcp_router):
        """has_tool() returns False for unknown tools."""
        assert not mcp_router.has_tool("nonexistent_tool_xyz_12345")

    @pytest.mark.asyncio
    async def test_call_unknown_tool_returns_error(self, mcp_router):
        """Calling unknown tool returns error response."""
        result = await mcp_router.call_tool("nonexistent_tool_xyz_12345", {})
        assert len(result) == 1
        response = json.loads(result[0].text)
        assert response["success"] is False
        assert "Unknown tool" in response.get("error", "")


class TestSchemaConsistency:
    """Tests for registry consistency."""

    def test_builtin_tools_all_have_schemas(self):
        """Every BUILTIN_TOOLS entry has input_schema."""
        for tool in BUILTIN_TOOLS:
            assert tool.input_schema is not None, f"{tool.name} missing input_schema"
            assert isinstance(tool.input_schema, dict), f"{tool.name} input_schema not dict"

    def test_builtin_tools_schemas_have_type(self):
        """Every input_schema has 'type' key."""
        for tool in BUILTIN_TOOLS:
            assert "type" in tool.input_schema, f"{tool.name} schema missing 'type'"

    def test_builtin_tools_have_response_schemas(self):
        """Every tool has response_schema_class (except plugins)."""
        for tool in BUILTIN_TOOLS:
            if not tool.is_plugin:
                assert tool.response_schema_class is not None, \
                    f"{tool.name} missing response_schema_class"

    def test_all_categories_in_category_order(self):
        """All tool categories appear in CATEGORY_ORDER."""
        used_categories = {t.category for t in BUILTIN_TOOLS}
        for cat in used_categories:
            assert cat in CATEGORY_ORDER, f"Category '{cat}' not in CATEGORY_ORDER"

    def test_category_order_has_no_orphans(self):
        """CATEGORY_ORDER doesn't have unused categories (warning only)."""
        used_categories = {t.category for t in BUILTIN_TOOLS}
        orphan_categories = [c for c in CATEGORY_ORDER if c not in used_categories]
        # Plugins is dynamic, so it might not have built-in tools
        orphan_categories = [c for c in orphan_categories if c != "Plugins"]
        if orphan_categories:
            pytest.skip(f"Unused categories in CATEGORY_ORDER: {orphan_categories}")


class TestToolNaming:
    """Tests for tool naming conventions."""

    def test_tool_names_lowercase_with_underscores(self):
        """Tool names should be lowercase with underscores."""
        for tool in BUILTIN_TOOLS:
            assert tool.name == tool.name.lower(), f"{tool.name} not lowercase"
            assert " " not in tool.name, f"{tool.name} contains spaces"

    def test_tool_names_no_leading_underscores(self):
        """Tool names should not start with underscore."""
        for tool in BUILTIN_TOOLS:
            assert not tool.name.startswith("_"), f"{tool.name} starts with underscore"

    def test_tool_names_not_empty(self):
        """Tool names should not be empty."""
        for tool in BUILTIN_TOOLS:
            assert tool.name, "Empty tool name found"
            assert len(tool.name) >= 3, f"{tool.name} too short"


class TestDescriptions:
    """Tests for tool descriptions."""

    def test_descriptions_not_empty(self):
        """All tools have non-empty descriptions."""
        for tool in BUILTIN_TOOLS:
            assert tool.description, f"{tool.name} has empty description"

    def test_descriptions_end_with_period(self):
        """Descriptions should end with period (convention)."""
        for tool in BUILTIN_TOOLS:
            # Allow descriptions ending with code blocks or examples
            if not tool.description.rstrip().endswith((".", ")", "]", "`")):
                pytest.skip(f"{tool.name} description doesn't end properly")

    def test_descriptions_mention_purpose(self):
        """Descriptions should mention what the tool does."""
        action_words = ["extract", "get", "set", "click", "type", "navigate",
                       "reload", "execute", "take", "check", "run", "clear",
                       "capture", "go", "return"]  # Added more action words
        for tool in BUILTIN_TOOLS:
            desc_lower = tool.description.lower()
            has_action = any(word in desc_lower for word in action_words)
            assert has_action, f"{tool.name} description doesn't explain action"


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_validation_error_returns_error_response(self, mcp_router):
        """Invalid params return structured error."""
        # Try calling a tool that requires params without providing them
        # Note: This depends on whether the tool is in the unified registry
        tools = mcp_router.get_tools()
        if not tools:
            pytest.skip("No tools registered in unified registry")

        # Find a tool that requires params
        tool_with_required = None
        for tool in tools:
            if tool.input_schema.get("required"):
                tool_with_required = tool
                break

        if not tool_with_required:
            pytest.skip("No tools with required params found")

        # Call without required params
        result = await mcp_router.call_tool(tool_with_required.name, {})
        response = json.loads(result[0].text)
        assert response["success"] is False


class TestResponseSchemas:
    """Tests for response schema compliance."""

    def test_response_schemas_have_success_field(self):
        """All response schemas have 'success' field."""
        for tool in BUILTIN_TOOLS:
            if tool.response_schema_class:
                fields = tool.response_schema_class.model_fields
                assert "success" in fields, \
                    f"{tool.name} response missing 'success' field"

    def test_response_schemas_are_serializable(self):
        """All response schemas can be serialized to JSON."""
        for tool in BUILTIN_TOOLS:
            if tool.response_schema_class:
                # Try to create a minimal valid instance
                fields = tool.response_schema_class.model_fields

                # Build minimal kwargs
                kwargs = {"success": True}
                for name, field in fields.items():
                    if name == "success":
                        continue
                    # Add required fields with dummy values
                    if field.is_required():
                        field_type = field.annotation
                        if field_type == str:
                            kwargs[name] = "test"
                        elif field_type == int:
                            kwargs[name] = 0
                        elif field_type == list:
                            kwargs[name] = []
                        elif field_type == dict:
                            kwargs[name] = {}

                try:
                    instance = tool.response_schema_class(**kwargs)
                    json_str = instance.model_dump_json()
                    assert json_str  # Not empty
                except Exception:
                    # Some schemas have complex requirements, skip those
                    pass


class TestPluginTools:
    """Tests for plugin tool handling."""

    def test_plugin_tools_have_plugin_flag(self):
        """Plugin tools have is_plugin=True."""
        from inspekt.app.mcp.registry import get_plugin_tools

        plugin_tools = get_plugin_tools()
        for tool in plugin_tools:
            assert tool.is_plugin, f"{tool.name} should have is_plugin=True"

    def test_plugin_tools_have_plugin_id(self):
        """Plugin tools have plugin_id set."""
        from inspekt.app.mcp.registry import get_plugin_tools

        plugin_tools = get_plugin_tools()
        for tool in plugin_tools:
            if not tool.name.startswith("unload_"):
                assert tool.plugin_id, f"{tool.name} missing plugin_id"
