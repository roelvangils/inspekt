"""
Command handlers - Implementation logic for all Inspekt commands.

Each handler is an async function that:
1. Receives validated input (Pydantic model)
2. Executes the command logic
3. Returns a validated response (Pydantic model)

Handlers are interface-agnostic - they work for CLI, API, and MCP.
"""
