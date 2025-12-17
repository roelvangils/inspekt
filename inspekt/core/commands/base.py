"""
Base classes for the Unified Command Registry.

CommandDefinition is the single source of truth for all Inspekt commands.
CLI, API, and MCP interfaces are generated from these definitions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Literal

from pydantic import BaseModel


class Category(str, Enum):
    """Command categories for organization and display."""

    NAVIGATION = "Navigation"
    EXECUTION = "Execution"
    EXTRACTION = "Extraction"
    INTERACTION = "Interaction"
    INSPECTION = "Inspection"
    SELECTION = "Selection"
    STORAGE = "Storage"
    ACCESSIBILITY = "Accessibility"
    NETWORK = "Network"
    DEBUGGING = "Debugging"
    PLUGINS = "Plugins"


# Order for displaying categories in UI
CATEGORY_ORDER = [
    Category.NAVIGATION,
    Category.EXECUTION,
    Category.EXTRACTION,
    Category.INTERACTION,
    Category.INSPECTION,
    Category.SELECTION,
    Category.STORAGE,
    Category.ACCESSIBILITY,
    Category.NETWORK,
    Category.DEBUGGING,
    Category.PLUGINS,
]


class EmptyParams(BaseModel):
    """Empty parameter model for commands with no inputs."""

    pass


@dataclass
class CommandDefinition:
    """
    Unified command definition - THE SINGLE SOURCE OF TRUTH.

    All command metadata is defined here ONCE. CLI, API, and MCP
    interfaces are automatically generated from this definition.

    Example:
        navigate_to_url = CommandDefinition(
            id="navigate_to_url",
            name="Navigate to URL",
            category=Category.NAVIGATION,
            description="Navigate to a URL in the browser...",
            params_schema=NavigateParams,
            response_schema=NavigateResponse,
            handler="inspekt.core.handlers.navigation.navigate_to_url",
            cli_name="open",
            api_path="/navigation/open",
        )
    """

    # === Core Identity ===
    id: str  # Unique identifier, e.g., "navigate_to_url"
    name: str  # Human-readable name, e.g., "Navigate to URL"
    category: Category  # For grouping and display
    description: str  # Rich description for AI/docs (supports markdown)

    # === Schemas ===
    params_schema: type[BaseModel]  # Pydantic model for input validation
    response_schema: type[BaseModel]  # Pydantic model for output

    # === Handler ===
    # Either a dotted path string or the actual async function
    handler: str | Callable[..., Any]

    # === CLI Configuration ===
    cli_name: str | None = None  # Override CLI name (default: id with _ -> -)
    cli_aliases: list[str] = field(default_factory=list)  # Additional CLI aliases
    cli_hidden: bool = False  # Hide from CLI help
    cli_group: str | None = None  # Parent group (e.g., "storage" for "storage list")

    # === API Configuration ===
    api_path: str | None = None  # Override API path (default: /{id})
    api_method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "POST"
    api_tags: list[str] = field(default_factory=list)  # OpenAPI tags

    # === MCP Configuration ===
    mcp_name: str | None = None  # Override MCP tool name (default: id)
    mcp_enabled_default: bool = True  # Default MCP enabled state

    # === Metadata ===
    examples: list[str] = field(default_factory=list)  # Usage examples
    deprecated: bool = False  # Mark as deprecated
    deprecated_message: str | None = None  # Deprecation notice
    since_version: str | None = None  # Version introduced

    def get_cli_name(self) -> str:
        """Get the CLI command name."""
        if self.cli_name:
            return self.cli_name
        return self.id.replace("_", "-")

    def get_api_path(self) -> str:
        """Get the API endpoint path."""
        if self.api_path:
            return self.api_path
        return f"/{self.id.replace('_', '-')}"

    def get_mcp_name(self) -> str:
        """Get the MCP tool name."""
        if self.mcp_name:
            return self.mcp_name
        return self.id  # MCP uses snake_case

    def get_input_schema(self) -> dict[str, Any]:
        """Get JSON Schema for input parameters (for MCP)."""
        schema = self.params_schema.model_json_schema()
        # Ensure proper format for MCP (must have type: object)
        if "type" not in schema:
            schema["type"] = "object"
        if "properties" not in schema:
            schema["properties"] = {}
        return schema

    def get_response_schema(self) -> dict[str, Any]:
        """Get JSON Schema for response (for documentation)."""
        return self.response_schema.model_json_schema()

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, CommandDefinition):
            return self.id == other.id
        return False
