"""
VM management command definitions.
"""

from inspekt.core.commands.base import (
    Category,
    CommandDefinition,
    EmptyParams,
    EmptyResponse,
    SubcommandDefinition,
)

vm = CommandDefinition(
    id="vm",
    name="Browser VM",
    category=Category.UTILITIES,
    description="""Manage the Inspekt Browser VM.

The Browser VM is a Docker-based virtual machine with Chromium
and the Inspekt extension pre-installed. Access it via noVNC
in your browser.

**Subcommands:**
- `start`: Build and start the VM
- `stop`: Stop the VM
- `restart`: Restart the VM
- `status`: Check VM status
- `open`: Open the control panel in browser
- `logs`: View VM logs
- `shell`: Open a shell in the VM container
""",
    params_schema=EmptyParams,
    response_schema=EmptyResponse,
    handler=None,
    cli_name="vm",
    api_path=None,
    mcp_enabled_default=False,
    is_group=True,
    subcommands=[
        SubcommandDefinition(
            name="start",
            description="Build and start the VM",
            params_schema=EmptyParams,
            examples=["inspekt vm start", "inspekt vm start --build"],
        ),
        SubcommandDefinition(
            name="stop",
            description="Stop the VM",
            params_schema=EmptyParams,
            examples=["inspekt vm stop"],
        ),
        SubcommandDefinition(
            name="restart",
            description="Restart the VM",
            params_schema=EmptyParams,
            examples=["inspekt vm restart"],
        ),
        SubcommandDefinition(
            name="status",
            description="Check VM status",
            params_schema=EmptyParams,
            examples=["inspekt vm status", "inspekt vm status --json"],
        ),
        SubcommandDefinition(
            name="open",
            description="Open the control panel in browser",
            params_schema=EmptyParams,
            examples=["inspekt vm open"],
        ),
        SubcommandDefinition(
            name="logs",
            description="View VM logs",
            params_schema=EmptyParams,
            examples=["inspekt vm logs", "inspekt vm logs -f"],
        ),
        SubcommandDefinition(
            name="shell",
            description="Open a shell in the VM container",
            params_schema=EmptyParams,
            examples=["inspekt vm shell"],
        ),
        SubcommandDefinition(
            name="cleanup",
            description="Remove stopped VM containers and images",
            params_schema=EmptyParams,
            examples=["inspekt vm cleanup", "inspekt vm cleanup --force"],
        ),
    ],
    examples=[
        "inspekt vm start",
        "inspekt vm open",
        "inspekt vm stop",
        "inspekt vm status",
    ],
)


VM_COMMANDS = [vm]
