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
    CONTROL = "Control"
    RECORDING = "Recording"
    UTILITIES = "Utilities"


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
    Category.CONTROL,
    Category.RECORDING,
    Category.UTILITIES,
]


class EmptyParams(BaseModel):
    """Empty parameter model for commands with no inputs."""

    pass


class EmptyResponse(BaseModel):
    """Empty response model for commands with no output."""

    pass


@dataclass
class SubcommandDefinition:
    """Definition for a subcommand within a command group."""

    name: str
    description: str
    params_schema: type[BaseModel] = EmptyParams
    examples: list[str] = field(default_factory=list)


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
            description="Navigate to a URL in the browser…",
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

    # === URL Scheme (inspekt:// deep links) ===
    url_scheme: str | None = None  # Scheme name, e.g., "open" → inspekt://open
    url_scheme_params: dict[str, str] = field(default_factory=dict)  # Param name → description
    url_scheme_examples: list[str] = field(default_factory=list)  # Example URLs
    url_scheme_output_mode: str | None = None  # Default output mode for scheme
    url_scheme_allowed_output_modes: list[str] = field(default_factory=list)  # Allowed modes
    url_scheme_timeout: int | None = None  # Timeout in seconds for scheme execution

    # === Command Groups ===
    is_group: bool = False  # True if this is a group with subcommands
    subcommands: list[SubcommandDefinition] = field(default_factory=list)  # Subcommand definitions

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

    def has_url_scheme(self) -> bool:
        """Check if this command has a URL scheme registered."""
        return self.url_scheme is not None

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
