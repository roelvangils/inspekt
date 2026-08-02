"""
Selection API endpoints - Get selected text from the browser.

This module provides HTTP API endpoints for text selection:
- GET /api/selection - Get all selection formats (text, HTML, markdown)
- GET /api/selection/text - Get selected text (plain text)
- GET /api/selection/html - Get selected HTML
- GET /api/selection/markdown - Get selected text as Markdown
"""

from __future__ import annotations

import subprocess
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from inspekt.app.api.dependencies import get_bridge_client
from inspekt.app.api.models import CommandResponse
from inspekt.services.script_loader import ScriptLoader

router = APIRouter()


# Response Models
class SelectionResponse(BaseModel):
    """Response model for selection operations."""

    ok: bool = Field(..., description="Whether the command executed successfully")
    result: dict[str, Any] | None = Field(None, description="Selection data")
    error: str | None = Field(None, description="Error message if ok=False")


# Helper Functions
def get_selection_data() -> dict[str, Any] | None:
    """Helper function to get selection data from browser."""
    client = get_bridge_client()

    # Load the get_selection.js script
    loader = ScriptLoader()
    try:
        code = loader.load_script_sync("get_selection.js")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"Script not found: {e!s}")

    try:
        result = client.execute(code, timeout=60.0)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error"))

        response = result.get("result", {})

        if not response.get("hasSelection"):
            return None

        return response

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def html_to_markdown(html_content: str) -> str:
    """Convert HTML to Markdown using html2markdown CLI."""
    try:
        result = subprocess.run(
            ["html2markdown"],
            input=html_content,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            # Fallback: return HTML if conversion fails
            return html_content
    except Exception:
        # Fallback: return HTML if conversion fails
        return html_content


# Endpoints
@router.get("", response_model=SelectionResponse)
@router.get("/", response_model=SelectionResponse)
def get_selection():
    """
    Get the current text selection in all formats.

    Mirrors 'inspekt selection --json' CLI command.

    Returns selection in three formats:
    - text: Plain text
    - html: HTML markup
    - markdown: Markdown (converted from HTML)

    Also includes:
    - hasSelection: Whether any text is currently selected
    - length: Length of selected text
    - position: Selection position and size
    - container: Information about containing element

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "hasSelection": true,
            "text": "Selected text",
            "html": "<strong>Selected text</strong>",
            "markdown": "**Selected text**",
            "length": 13,
            "position": {"x": 100, "y": 200, "width": 80, "height": 20},
            "container": {"tag": "p", "id": "content"}
        }
    }
    ```
    """
    response = get_selection_data()

    if response is None:
        # No selection
        return {
            "ok": True,
            "result": {
                "hasSelection": False,
                "text": "",
                "html": "",
                "markdown": "",
                "length": 0,
            },
            "error": None,
        }

    # Generate markdown from HTML
    html = response.get("html", "")
    text_content = response.get("text", "")
    markdown_content = html_to_markdown(html) if html else text_content

    # Return all three formats
    output = {
        "hasSelection": True,
        "text": text_content,
        "html": html,
        "markdown": markdown_content,
        "length": response.get("length", 0),
        "position": response.get("position", {}),
        "container": response.get("container", {}),
    }

    return {
        "ok": True,
        "result": output,
        "error": None,
    }


@router.get("/text", response_model=SelectionResponse)
def get_selection_text():
    """
    Get selected text (plain text).

    Mirrors 'inspekt selection text --json' CLI command.

    Returns only the plain text content of the current selection.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "hasSelection": true,
            "text": "Selected text",
            "length": 13
        }
    }
    ```
    """
    response = get_selection_data()

    if response is None:
        # No selection
        return {
            "ok": True,
            "result": {
                "hasSelection": False,
                "text": "",
                "length": 0,
            },
            "error": None,
        }

    text_content = response.get("text", "")

    return {
        "ok": True,
        "result": {
            "hasSelection": True,
            "text": text_content,
            "length": response.get("length", 0),
        },
        "error": None,
    }


@router.get("/html", response_model=SelectionResponse)
def get_selection_html():
    """
    Get selected HTML.

    Mirrors 'inspekt selection html --json' CLI command.

    Returns the HTML markup of the current selection.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "hasSelection": true,
            "html": "<strong>Selected text</strong>",
            "length": 13
        }
    }
    ```
    """
    response = get_selection_data()

    if response is None:
        # No selection
        return {
            "ok": True,
            "result": {
                "hasSelection": False,
                "html": "",
                "length": 0,
            },
            "error": None,
        }

    html_content = response.get("html", "")

    return {
        "ok": True,
        "result": {
            "hasSelection": True,
            "html": html_content,
            "length": response.get("length", 0),
        },
        "error": None,
    }


@router.get("/markdown", response_model=SelectionResponse)
def get_selection_markdown():
    """
    Get selected text as Markdown (converted from HTML).

    Mirrors 'inspekt selection markdown --json' CLI command.

    Converts the HTML markup of the selection to Markdown format.

    Example response:
    ```json
    {
        "ok": true,
        "result": {
            "hasSelection": true,
            "markdown": "**Selected text**",
            "length": 13
        }
    }
    ```
    """
    response = get_selection_data()

    if response is None:
        # No selection
        return {
            "ok": True,
            "result": {
                "hasSelection": False,
                "markdown": "",
                "length": 0,
            },
            "error": None,
        }

    html_content = response.get("html", "")
    text_content = response.get("text", "")
    markdown_content = html_to_markdown(html_content) if html_content else text_content

    return {
        "ok": True,
        "result": {
            "hasSelection": True,
            "markdown": markdown_content,
            "length": response.get("length", 0),
        },
        "error": None,
    }
