"""Inspekt — execute JavaScript in your browser from the command line.

Package layout (hexagonal — outer layers may import inner, never the
reverse):

    app/         Entry points: cli/, api/ (FastAPI), mcp/ (Model Context
                 Protocol). User-facing surfaces that translate input
                 into core command calls.

    core/        Command registry and dispatch. commands/ enumerates
                 what Inspekt can do; handlers/ executes; schemas/ holds
                 request/response types; generators/ builds derived code
                 (e.g. MCP tool manifest from the registry).

    services/    Business logic — the bulk of the package (~80 files).
                 Subdivided by capability: ai_providers/, engines/
                 (axe, alfa, IBM Equal Access), headless/ (Playwright).

    domain/      Pydantic models that flow between layers.
    adapters/    I/O at system boundaries (filesystem, etc.).
    transport/   Bridge protocol — WebSocket/HTTP between CLI and browser.
    shared/      Cross-cutting utilities with no other natural home.

    data/, i18n/, man/, static/, scripts/   Non-code assets bundled with
                 the package (axe-core builds, JS snippets injected
                 into pages, generated man pages, translations).

Architecture overview: ../docs/architecture.html
"""

__version__ = "1.0.0"
