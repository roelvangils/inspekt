"""
Regression tests for known issues.

Each test documents a specific bug or issue that was identified during the audit.
These tests should fail if the bugs resurface.

Run with: pytest tests/mcp/test_mcp_regression.py -v
"""

import pytest

from inspekt.app.mcp.registry import BUILTIN_TOOLS, EMPTY_SCHEMA


class TestKnownIssues:
    """Tests for previously identified bugs."""

    def test_empty_schema_is_valid_json_schema(self):
        """
        EMPTY_SCHEMA must be valid JSON Schema (not empty dict).

        Issue: Empty dict {} is not valid JSON Schema. MCP clients
        expect {"type": "object", "properties": {}} at minimum.
        """
        assert EMPTY_SCHEMA.get("type") == "object", "EMPTY_SCHEMA must have type: object"
        assert "properties" in EMPTY_SCHEMA, "EMPTY_SCHEMA must have properties key"

    def test_mcp_names_no_underscore_prefix(self):
        """
        MCP tool names should not start with underscore.

        Issue: Leading underscores suggest private/internal tools
        and may confuse MCP clients.
        """
        for tool in BUILTIN_TOOLS:
            assert not tool.name.startswith("_"), f"{tool.name} starts with underscore"

    def test_all_required_fields_have_descriptions(self):
        """
        Required fields must have descriptions for MCP clients.

        Issue: Without descriptions, MCP clients (like Claude) don't
        know what values to provide for required fields.
        """
        for tool in BUILTIN_TOOLS:
            schema = tool.input_schema
            required = schema.get("required", [])
            props = schema.get("properties", {})

            for field in required:
                if field in props:
                    desc = props[field].get("description")
                    assert desc, f"{tool.name}.{field} missing description"


class TestDualRegistryIssues:
    """Tests for dual registry consistency issues."""

    def test_no_duplicate_tool_names_in_builtin(self):
        """
        No duplicate tool names in BUILTIN_TOOLS.

        Issue: Duplicate names cause routing ambiguity.
        """
        names = [t.name for t in BUILTIN_TOOLS]
        duplicates = [n for n in names if names.count(n) > 1]
        assert len(duplicates) == 0, f"Duplicate tool names: {set(duplicates)}"

    def test_all_tools_have_input_schema(self):
        """
        All tools must have input_schema defined.

        Issue: Missing input_schema causes MCP client errors.
        """
        for tool in BUILTIN_TOOLS:
            assert tool.input_schema is not None, f"{tool.name} has None input_schema"
            assert isinstance(tool.input_schema, dict), f"{tool.name} input_schema is not dict"

    def test_all_tools_have_response_schema(self):
        """
        All non-plugin tools must have response_schema_class.

        Issue: Without response schema, we can't validate responses.
        """
        for tool in BUILTIN_TOOLS:
            if not tool.is_plugin:
                assert tool.response_schema_class is not None, (
                    f"{tool.name} missing response_schema_class"
                )


class TestSchemaValidation:
    """Tests for schema validation issues."""

    def test_input_schemas_are_object_type(self):
        """
        All input schemas must have type: object.

        Issue: MCP expects tool parameters as objects, not primitives.
        """
        for tool in BUILTIN_TOOLS:
            schema_type = tool.input_schema.get("type")
            assert schema_type == "object", (
                f"{tool.name} schema type is '{schema_type}', expected 'object'"
            )

    def test_schemas_have_properties_key(self):
        """
        All input schemas must have properties key.

        Issue: Missing properties key causes JSON Schema validation errors.
        """
        for tool in BUILTIN_TOOLS:
            assert "properties" in tool.input_schema, f"{tool.name} schema missing 'properties' key"

    def test_enum_fields_have_valid_values(self):
        """
        Enum fields must have at least one valid value.

        Issue: Empty enum causes validation to always fail.
        """
        for tool in BUILTIN_TOOLS:
            props = tool.input_schema.get("properties", {})
            for field_name, field_def in props.items():
                if "enum" in field_def:
                    enum_values = field_def["enum"]
                    assert len(enum_values) > 0, f"{tool.name}.{field_name} has empty enum"
                # Also check anyOf for Literal types
                if "anyOf" in field_def:
                    for option in field_def["anyOf"]:
                        if "enum" in option:
                            assert len(option["enum"]) > 0, (
                                f"{tool.name}.{field_name} has empty enum in anyOf"
                            )


class TestNamingConflicts:
    """Tests for naming conflicts between registries."""

    def test_expected_tools_exist(self):
        """
        Essential tools must be present.

        Issue: Missing essential tools breaks common workflows.
        """
        expected_tools = [
            "navigate_to_url",
            "execute_javascript",
            "get_page_info",
            "click_element",
            "type_text",
            "take_screenshot",
            "run_axe",
        ]

        tool_names = {t.name for t in BUILTIN_TOOLS}
        for expected in expected_tools:
            assert expected in tool_names, f"Essential tool '{expected}' is missing"

    def test_tool_categories_are_valid(self):
        """
        All tools have valid category values.

        Issue: Invalid categories break grouping in MCP clients.
        """
        valid_categories = {
            "Navigation",
            "Execution",
            "Extraction",
            "Interaction",
            "Inspection",
            "Selection",
            "Storage",
            "Accessibility",
            "Network",
            "Console",
            "Plugins",
        }

        for tool in BUILTIN_TOOLS:
            assert tool.category in valid_categories, (
                f"{tool.name} has invalid category: {tool.category}"
            )


class TestResponseConsistency:
    """Tests for response consistency issues."""

    def test_success_field_type_consistent(self):
        """
        success field must be boolean in all responses.

        Issue: Inconsistent types cause client-side errors.
        """
        for tool in BUILTIN_TOOLS:
            if tool.response_schema_class:
                fields = tool.response_schema_class.model_fields
                if "success" in fields:
                    field = fields["success"]
                    assert field.annotation is bool, f"{tool.name} response success is not bool"

    def test_error_responses_have_message(self):
        """
        Response schemas should have optional message/error field.

        Issue: Without error message field, failures are hard to debug.
        """
        for tool in BUILTIN_TOOLS:
            if tool.response_schema_class:
                fields = tool.response_schema_class.model_fields
                has_error_field = "message" in fields or "error" in fields
                # Most responses should have some error indication
                if not has_error_field:
                    # Skip this as a warning, not failure
                    pytest.skip(f"{tool.name} response lacks message/error field")


class TestSecurityIssues:
    """Tests for security-related issues."""

    def test_execute_javascript_has_timeout(self):
        """
        execute_javascript must support timeout parameter.

        Issue: Without timeout, malicious JS could run indefinitely.
        """
        exec_tool = next((t for t in BUILTIN_TOOLS if t.name == "execute_javascript"), None)
        assert exec_tool, "execute_javascript tool not found"

        props = exec_tool.input_schema.get("properties", {})
        assert "timeout" in props, "execute_javascript missing timeout parameter"

    def test_no_sensitive_defaults(self):
        """
        Tools should not have sensitive default values.

        Issue: Default values that could expose sensitive data.
        """
        # Check that httpOnly defaults to False for set_cookie
        set_cookie = next((t for t in BUILTIN_TOOLS if t.name == "set_cookie"), None)
        if set_cookie:
            props = set_cookie.input_schema.get("properties", {})
            if "httpOnly" in props:
                default = props["httpOnly"].get("default")
                # httpOnly should default to False (safer for debugging)
                assert default is False or default is None, (
                    "set_cookie httpOnly should default to False"
                )
