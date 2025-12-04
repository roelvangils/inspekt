"""
Commands API endpoints.

Exposes the unified command registry for dashboard and tooling.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from inspekt.core.commands import register_all_commands
from inspekt.core.registry import get_registry

router = APIRouter()

# Ensure commands are registered
register_all_commands()


class CommandSummary(BaseModel):
    """Summary of a command for listing."""

    id: str
    name: str
    category: str
    description: str
    cli_name: str
    api_path: str
    mcp_name: str
    mcp_enabled: bool


class CommandDetail(BaseModel):
    """Full command details including schemas."""

    id: str
    name: str
    category: str
    description: str
    cli_name: str
    cli_aliases: list[str]
    api_path: str
    api_method: str
    mcp_name: str
    mcp_enabled: bool
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    examples: list[str]
    deprecated: bool
    deprecated_message: str | None
    # Schema annotations (field-level customizations)
    schema_annotations: dict[str, Any] = {}
    # Customization flags
    has_custom_description: bool = False
    has_custom_mcp_name: bool = False
    has_custom_examples: bool = False
    has_custom_schema_annotations: bool = False
    # Default values (for reset comparison)
    default_description: str | None = None
    default_mcp_name: str | None = None
    default_examples: list[str] | None = None


class CommandListResponse(BaseModel):
    """Response for listing all commands."""

    commands: list[CommandSummary]
    total: int
    categories: list[str]


class CategoryListResponse(BaseModel):
    """Response for commands grouped by category."""

    categories: dict[str, list[CommandSummary]]


class MCPToggleRequest(BaseModel):
    """Request to toggle MCP enabled state."""

    enabled: bool


class MCPToggleResponse(BaseModel):
    """Response from toggling MCP state."""

    command_id: str
    mcp_enabled: bool
    message: str


class CommandConfigRequest(BaseModel):
    """Request to update command configuration."""

    description: str | None = None
    mcp_name: str | None = None
    examples: list[str] | None = None
    schema_annotations: dict[str, Any] | None = None


class CommandConfigResponse(BaseModel):
    """Response from updating command configuration."""

    command_id: str
    updated_fields: list[str]
    message: str


class MCPPreviewResponse(BaseModel):
    """Response showing what AI models receive via MCP."""

    tool_definition: dict[str, Any]
    is_customized: dict[str, bool]


class ResetRequest(BaseModel):
    """Request to reset custom fields to defaults."""

    fields: list[str]  # ["description", "mcp_name", "examples"] or ["all"]


class ResetResponse(BaseModel):
    """Response from resetting fields."""

    command_id: str
    reset_fields: list[str]
    message: str


@router.get("/", response_model=CommandListResponse)
def list_commands():
    """
    List all registered commands.

    Returns a summary of each command including its CLI name,
    API path, and MCP enabled state.
    """
    registry = get_registry()
    commands = []
    categories_set = set()

    for cmd in registry.get_all():
        categories_set.add(cmd.category.value)
        commands.append(
            CommandSummary(
                id=cmd.id,
                name=cmd.name,
                category=cmd.category.value,
                description=cmd.description.split("\n")[0],  # First line only
                cli_name=cmd.get_cli_name(),
                api_path=cmd.get_api_path(),
                mcp_name=cmd.get_mcp_name(),
                mcp_enabled=registry.is_mcp_enabled(cmd.id),
            )
        )

    return CommandListResponse(
        commands=commands,
        total=len(commands),
        categories=sorted(categories_set),
    )


@router.get("/by-category", response_model=CategoryListResponse)
def list_commands_by_category():
    """
    List all commands grouped by category.

    Returns commands organized by their category for easier
    navigation and display.
    """
    registry = get_registry()
    categories: dict[str, list[CommandSummary]] = {}

    for category, cmds in registry.get_grouped_by_category().items():
        cat_name = category.value
        categories[cat_name] = [
            CommandSummary(
                id=cmd.id,
                name=cmd.name,
                category=cat_name,
                description=cmd.description.split("\n")[0],
                cli_name=cmd.get_cli_name(),
                api_path=cmd.get_api_path(),
                mcp_name=cmd.get_mcp_name(),
                mcp_enabled=registry.is_mcp_enabled(cmd.id),
            )
            for cmd in cmds
        ]

    return CategoryListResponse(categories=categories)


@router.get("/mcp/enabled")
def list_mcp_enabled():
    """
    List all commands that have MCP enabled.

    Returns only the commands that are currently exposed
    via the MCP server.
    """
    registry = get_registry()
    commands = []

    for cmd in registry.get_for_mcp():
        commands.append(
            {
                "id": cmd.id,
                "name": cmd.name,
                "mcp_name": cmd.get_mcp_name(),
                "description": cmd.description.split("\n")[0],
            }
        )

    return {"commands": commands, "total": len(commands)}


@router.get("/{command_id}", response_model=CommandDetail)
def get_command(command_id: str):
    """
    Get detailed information about a specific command.

    Returns the full command definition including input/output
    schemas, examples, and configuration. Uses effective values
    (custom if set, otherwise defaults).
    """
    registry = get_registry()
    cmd = registry.get(command_id)

    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '{command_id}' not found")

    # Get customization status
    customized = registry.is_customized(command_id)

    return CommandDetail(
        id=cmd.id,
        name=cmd.name,
        category=cmd.category.value,
        # Use effective values (custom or default)
        description=registry.get_description(cmd),
        cli_name=cmd.get_cli_name(),
        cli_aliases=cmd.cli_aliases,
        api_path=cmd.get_api_path(),
        api_method=cmd.api_method,
        mcp_name=registry.get_effective_mcp_name(cmd),
        mcp_enabled=registry.is_mcp_enabled(cmd.id),
        input_schema=cmd.get_input_schema(),
        output_schema=cmd.get_response_schema(),
        examples=registry.get_effective_examples(cmd),
        deprecated=cmd.deprecated,
        deprecated_message=cmd.deprecated_message,
        # Schema annotations
        schema_annotations=registry.get_schema_annotations(command_id),
        # Customization flags
        has_custom_description=customized["description"],
        has_custom_mcp_name=customized["mcp_name"],
        has_custom_examples=customized["examples"],
        has_custom_schema_annotations=customized["schema_annotations"],
        # Default values for comparison/reset
        default_description=cmd.description,
        default_mcp_name=cmd.get_mcp_name(),
        default_examples=cmd.examples,
    )


@router.post("/{command_id}/mcp", response_model=MCPToggleResponse)
def toggle_mcp(command_id: str, request: MCPToggleRequest):
    """
    Enable or disable MCP for a specific command.

    This setting persists to the database and takes effect
    immediately for the MCP server.
    """
    registry = get_registry()
    cmd = registry.get(command_id)

    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '{command_id}' not found")

    registry.set_mcp_enabled(command_id, request.enabled)

    state = "enabled" if request.enabled else "disabled"
    return MCPToggleResponse(
        command_id=command_id,
        mcp_enabled=request.enabled,
        message=f"MCP {state} for {cmd.name}",
    )


@router.put("/{command_id}/config", response_model=CommandConfigResponse)
def update_command_config(command_id: str, request: CommandConfigRequest):
    """
    Update custom configuration for a command.

    These settings override the code defaults and persist to database.
    Set a field to empty string to reset to default.
    """
    registry = get_registry()
    cmd = registry.get(command_id)

    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '{command_id}' not found")

    updated = []

    if request.description is not None:
        # Empty string means reset to default
        value = request.description if request.description.strip() else None
        registry.set_custom_description(command_id, value)
        updated.append("description")

    if request.mcp_name is not None:
        value = request.mcp_name if request.mcp_name.strip() else None
        registry.set_custom_mcp_name(command_id, value)
        updated.append("mcp_name")

    if request.examples is not None:
        # Empty list means reset to default
        value = request.examples if request.examples else None
        registry.set_custom_examples(command_id, value)
        updated.append("examples")

    if request.schema_annotations is not None:
        # Empty dict means reset to default
        value = request.schema_annotations if request.schema_annotations else None
        registry.set_schema_annotations(command_id, value)
        updated.append("schema_annotations")

    return CommandConfigResponse(
        command_id=command_id,
        updated_fields=updated,
        message=f"Updated {len(updated)} field(s) for {cmd.name}",
    )


@router.get("/{command_id}/mcp-preview", response_model=MCPPreviewResponse)
def get_mcp_preview(command_id: str):
    """
    Get MCP tool preview for a command.

    Shows exactly what AI models will receive when this command
    is exposed via MCP.
    """
    registry = get_registry()
    cmd = registry.get(command_id)

    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '{command_id}' not found")

    # Build the tool definition as MCP would see it (with annotations merged)
    tool_definition = {
        "name": registry.get_effective_mcp_name(cmd),
        "description": registry.get_description(cmd),
        "inputSchema": registry.get_effective_input_schema(cmd),
    }

    return MCPPreviewResponse(
        tool_definition=tool_definition,
        is_customized=registry.is_customized(command_id),
    )


@router.post("/{command_id}/reset", response_model=ResetResponse)
def reset_command_config(command_id: str, request: ResetRequest):
    """
    Reset custom fields to their default values.

    Pass field names in the `fields` array: ["description", "mcp_name", "examples"]
    Or use ["all"] to reset everything.
    """
    registry = get_registry()
    cmd = registry.get(command_id)

    if not cmd:
        raise HTTPException(status_code=404, detail=f"Command '{command_id}' not found")

    reset_fields = []

    if "all" in request.fields:
        registry.reset_custom_field(command_id, "all")
        reset_fields = ["description", "mcp_name", "examples", "schema_annotations"]
    else:
        for field in request.fields:
            if field in ["description", "mcp_name", "examples", "schema_annotations"]:
                registry.reset_custom_field(command_id, field)
                reset_fields.append(field)

    return ResetResponse(
        command_id=command_id,
        reset_fields=reset_fields,
        message=f"Reset {len(reset_fields)} field(s) to default for {cmd.name}",
    )
