# Adding New Commands

This guide explains how to add a new command to Inspekt. Commands are defined
in **two places** to ensure the dashboard shows all commands:

1. **CommandDefinition** in `inspekt/core/commands/` (metadata)
2. **Click command** in `inspekt/app/cli/` (implementation)

## Quick Start

### Step 1: Choose a Category

Commands are organized by category. Pick the appropriate one:

| Category | Use Case | Module |
|----------|----------|--------|
| Navigation | URL loading, scrolling, history | `navigation.py` |
| Execution | JavaScript execution | `execution.py` |
| Extraction | Content extraction (links, outline) | `extraction.py` |
| Interaction | User input (click, type, paste) | `interaction.py` |
| Inspection | Screenshots, page info | `inspection.py` |
| Selection | Text selection operations | `selection.py` |
| Storage | Cookies, localStorage | `storage.py` |
| Accessibility | A11y testing (axe, ibm) | `accessibility.py` |
| Network | Network inspection | `network.py` |
| Debugging | Console, logging | `debugging.py`, `console.py` |
| Control | Server management | `control.py` |
| Recording | Record/replay | `recording.py` |
| Utilities | Misc tools | `utilities.py` |
| Plugins | Plugin/MCP management | `plugin.py`, `mcp_management.py` |

### Step 2: Add CommandDefinition

Add your command to the appropriate file in `inspekt/core/commands/`:

```python
from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
)

my_command = CommandDefinition(
    id="my_command",                    # Unique ID (snake_case)
    name="My Command",                  # Human-readable name
    category=Category.UTILITIES,        # Pick from Category enum
    description="""Rich description for AI assistants.

Supports **markdown** formatting. Include:
- What the command does
- Key options
- Use cases
""",
    params_schema=EmptyParams,          # Pydantic model for inputs
    response_schema=EmptyResponse,      # Pydantic model for outputs
    handler=None,                       # Handler path or None for CLI-only
    cli_name="my-cmd",                  # CLI command name (kebab-case)
    cli_aliases=["mc"],                 # Optional aliases
    api_path=None,                      # API path or None
    mcp_enabled_default=False,          # Enable for MCP?
    examples=[
        "inspekt my-cmd",
        "inspekt my-cmd --verbose",
    ],
)
```

### Step 3: Add to Command List

Add your command to the module's export list:

```python
MY_CATEGORY_COMMANDS = [
    existing_command,
    my_command,  # Add here
]
```

### Step 4: Create Click Command

In the appropriate `inspekt/app/cli/` module:

```python
@click.command()
@click.option("--verbose", is_flag=True, help="Verbose output")
def my_cmd(verbose):
    """Short description for CLI help."""
    # Implementation here
    pass
```

### Step 5: Register Click Command

In `inspekt/app/cli/__init__.py`:

```python
cli.add_lazy_command("my-cmd", "my_module", "my_cmd")
```

### Step 6: Verify

Run the validation test:

```bash
pytest tests/unit/test_command_registry_sync.py -v
```

## Command Types

### CLI-Only Commands

For commands that only work in the terminal (interactive, server management):

```python
handler=None,           # No unified handler
api_path=None,          # Not exposed via API
mcp_enabled_default=False,  # Not an MCP tool
```

### Unified Commands

For commands with full API/MCP support:

```python
handler="inspekt.core.handlers.my_module.my_command",
api_path="/category/my-cmd",
mcp_enabled_default=True,
```

### Command Groups

For commands with subcommands (like `inspekt cookies list`):

```python
from inspekt.core.commands.base import SubcommandDefinition

my_group = CommandDefinition(
    id="my_group",
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="list",
            description="List items",
            params_schema=EmptyParams,
            examples=["inspekt my-group list"],
        ),
        SubcommandDefinition(
            name="add",
            description="Add an item",
            params_schema=AddParams,
            examples=["inspekt my-group add item"],
        ),
    ],
    # ...
)
```

## Best Practices

1. **Description Quality**: Write clear descriptions - they're shown to AI assistants
2. **Examples**: Include 2-3 realistic examples
3. **Naming**: Use kebab-case for CLI, snake_case for IDs
4. **Categories**: Use existing categories; only add new ones if truly needed
5. **Validation**: Always run the sync test after adding commands

## Automatic Propagation

Once registered, your command automatically appears in:

- **CLI**: `inspekt my-cmd --help`
- **Dashboard**: http://localhost:8000/commands
- **API**: `POST /api/commands/my_command` (if configured)
- **MCP**: Available to AI assistants (if enabled)

## Validation

The CI test in `tests/unit/test_command_registry_sync.py` ensures:

1. All CLI commands have CommandDefinitions
2. No duplicate CLI names or command IDs
3. All categories are valid
4. The registry loads without errors

If you see failures, check:

- Did you add the command to the module's export list?
- Is the command name unique?
- Are there import errors in your module?
