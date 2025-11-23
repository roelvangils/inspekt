"""Execution API endpoints for running JavaScript code."""

from fastapi import APIRouter, HTTPException
from inspekt.app.api.models import EvalRequest, CommandResponse
from inspekt.app.api.dependencies import get_bridge_client

router = APIRouter()


@router.post("/eval", response_model=CommandResponse)
def execute_javascript(request: EvalRequest):
    """
    Execute JavaScript code in the browser.

    This endpoint mirrors the `zen eval` CLI command.

    Args:
        request: JavaScript code and timeout

    Returns:
        Command execution result with the value returned by the code

    Examples:
        ```bash
        # Get document title
        curl -X POST http://localhost:8767/api/execution/eval \\
          -H "Content-Type: application/json" \\
          -d '{"code": "document.title"}'

        # Get page URL
        curl -X POST http://localhost:8767/api/execution/eval \\
          -H "Content-Type: application/json" \\
          -d '{"code": "window.location.href"}'

        # Execute complex code
        curl -X POST http://localhost:8767/api/execution/eval \\
          -H "Content-Type: application/json" \\
          -d '{"code": "document.querySelectorAll(\"a\").length", "timeout": 5.0}'
        ```
    """
    client = get_bridge_client()

    try:
        result = client.execute(request.code, timeout=request.timeout)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Execution failed"))

        return result

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Bridge server connection error: {str(e)}")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Execution timeout: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")
