"""
Debugging command schemas.

Input/output models for debugging commands:
- get_console_logs
- clear_console_logs
"""

from typing import Literal

from pydantic import BaseModel, Field


class GetConsoleLogsParams(BaseModel):
    """Parameters for get_console_logs command."""

    level: Literal["all", "error", "warn", "log", "info", "debug"] | None = Field(
        default="all",
        description="Filter by log level: all (default), error, warn, log, info, or debug",
    )
    limit: int | None = Field(
        default=100, description="Maximum number of messages to return (default: 100)"
    )


class ConsoleEntry(BaseModel):
    """A single console log entry."""

    level: str = Field(..., description="Log level: error, warn, log, info, or debug")
    timestamp: str = Field(
        ..., description="Timestamp when the message was logged (ISO 8601)"
    )
    message: str = Field(..., description="The logged message content")


class GetConsoleLogsResponse(BaseModel):
    """Response from get_console_logs command."""

    success: bool = Field(..., description="Whether the operation succeeded")
    entries: list[ConsoleEntry] = Field(
        default=[], description="List of console log entries"
    )
    count: int = Field(default=0, description="Number of entries returned")
    hooked: bool = Field(
        default=False, description="Whether console hooks are active on the page"
    )
    message: str | None = Field(default=None, description="Success or error message")


class ClearConsoleLogsResponse(BaseModel):
    """Response from clear_console_logs command."""

    success: bool = Field(..., description="Whether the operation succeeded")
    message: str | None = Field(default=None, description="Success or error message")
