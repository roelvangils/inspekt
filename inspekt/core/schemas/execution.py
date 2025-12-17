"""
Execution command schemas.

Input/output models for execution commands:
- execute_javascript
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ExecuteJavaScriptParams(BaseModel):
    """Parameters for execute_javascript command."""

    code: str = Field(
        ..., description="JavaScript code to execute in the browser context"
    )
    timeout: Optional[int] = Field(
        default=30, description="Execution timeout in seconds (default: 30)"
    )


class ExecuteJavaScriptResponse(BaseModel):
    """Response from execute_javascript command."""

    success: bool = Field(..., description="Whether execution succeeded")
    result: Any = Field(..., description="The return value from the JavaScript code")
    console_output: Optional[list[str]] = Field(
        default=None, description="Console messages during execution"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if execution failed"
    )
