"""Accessibility API endpoints for running accessibility audits."""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from inspekt.app.api.models import AxeRequest, AutocompleteRequest, CommandResponse
from inspekt.app.api.dependencies import get_bridge_client
from inspekt.services.autocomplete_service import get_autocomplete_service

router = APIRouter()


def _build_axe_config(level: str, tags: str | None, include_passes: bool, include_incomplete: bool) -> dict:
    """
    Build axe-core configuration object from request parameters.

    Args:
        level: WCAG level (2a, 2aa, 2aaa, 21a, 21aa, 22aa)
        tags: Additional comma-separated tags
        include_passes: Whether to include passing checks
        include_incomplete: Whether to include incomplete checks

    Returns:
        Configuration dict for axe.run()
    """
    # Map WCAG levels to axe tags
    level_mapping = {
        "2a": ["wcag2a"],
        "2aa": ["wcag2a", "wcag2aa"],
        "2aaa": ["wcag2a", "wcag2aa", "wcag2aaa"],
        "21a": ["wcag2a", "wcag21a"],
        "21aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        "22aa": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"],
    }

    # Get base tags from level
    axe_tags = level_mapping.get(level.lower(), ["wcag2a", "wcag2aa"])

    # Add additional tags if specified
    if tags:
        additional_tags = [tag.strip() for tag in tags.split(",")]
        axe_tags.extend(additional_tags)

    # Build config
    config = {
        "runOnly": {
            "type": "tag",
            "values": axe_tags
        },
        "resultTypes": ["violations"]
    }

    # Add optional result types
    if include_passes:
        config["resultTypes"].append("passes")
    if include_incomplete:
        config["resultTypes"].append("incomplete")

    return config


@router.post("/axe", response_model=CommandResponse)
def run_axe_audit(request: AxeRequest):
    """
    Run axe-core accessibility audit on the current page.

    Analyzes the page for WCAG conformance violations using the industry-standard
    axe-core library. By default, tests against WCAG 2 Level AA standards.

    The audit runs in the current browser tab, testing the actual rendered page
    state including any JavaScript-generated content and authentication state.

    Args:
        request: Axe audit configuration

    Returns:
        Audit results with violations, passes, incomplete checks, and summary

    Examples:
        ```bash
        # Basic audit (WCAG 2 Level AA)
        curl -X POST http://localhost:8767/api/accessibility/axe \\
          -H "Content-Type: application/json" \\
          -d '{}'

        # WCAG 2.1 Level AA audit
        curl -X POST http://localhost:8767/api/accessibility/axe \\
          -H "Content-Type: application/json" \\
          -d '{"level": "21aa"}'

        # Include best practices
        curl -X POST http://localhost:8767/api/accessibility/axe \\
          -H "Content-Type: application/json" \\
          -d '{"tags": "best-practice", "include_incomplete": true}'

        # Full audit with all results
        curl -X POST http://localhost:8767/api/accessibility/axe \\
          -H "Content-Type: application/json" \\
          -d '{"include_passes": true, "include_incomplete": true}'
        ```
    """
    client = get_bridge_client()

    # Build axe configuration
    config = _build_axe_config(
        request.level,
        request.tags,
        request.include_passes,
        request.include_incomplete
    )

    # Load axe-core library (bundled locally)
    axe_lib_path = Path(__file__).parent.parent.parent.parent / "scripts" / "vendor" / "axe-core.min.js"
    if not axe_lib_path.exists():
        raise HTTPException(status_code=500, detail=f"axe-core library not found: {axe_lib_path}")

    # Load the run_axe script
    script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "run_axe.js"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail=f"Script not found: {script_path}")

    try:
        # Read axe-core library
        with open(axe_lib_path) as f:
            axe_lib = f.read()

        # Read audit script
        with open(script_path) as f:
            audit_script = f.read()

        # Replace config placeholder
        audit_script = audit_script.replace("__AXE_CONFIG__", json.dumps(config))

        # Combine: axe-core library + audit script in a single async IIFE
        # This avoids semicolon issues with AsyncFunction wrapper
        script = f"""(async function() {{
    // Load axe-core library
    {axe_lib}

    // Run audit
    const auditResult = await {audit_script};
    return auditResult;
}})()"""

        # Execute the script
        result = client.execute(script, timeout=request.timeout)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail=result.get("error", "Execution failed"))

        data = result.get("result", {})

        # Check if script execution failed
        if not data.get("ok"):
            raise HTTPException(status_code=500, detail=data.get("error", "Axe execution failed"))

        # Return the full result
        return {
            "ok": True,
            "result": {
                "url": data.get("url"),
                "title": data.get("title"),
                "timestamp": data.get("timestamp"),
                "axeVersion": data.get("axeVersion"),
                "config": config,
                "violations": data.get("violations", []),
                "passes": data.get("passes", []) if request.include_passes else [],
                "incomplete": data.get("incomplete", []) if request.include_incomplete else [],
                "summary": data.get("summary", {})
            },
            "url": data.get("url"),
            "title": data.get("title")
        }

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Bridge server connection error: {str(e)}")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Execution timeout: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")


@router.post("/autocomplete-check", response_model=CommandResponse)
async def run_autocomplete_check(request: AutocompleteRequest):
    """
    Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5.

    Analyzes all form fields (input, textarea, select) on the current page and
    predicts appropriate autocomplete attributes using multi-language heuristics
    based on the Autocomplete-Check extension logic.

    The check uses 7 matching strategies with weighted confidence scoring:
    - Label text (weight: 5) - highest reliability
    - Placeholder text (weight: 4)
    - Name attribute (weight: 2)
    - ID attribute (weight: 2)
    - Field type (weight: 1)
    - Input type (weight: 1)
    - Form type (weight: 1) - login vs signup detection

    Supports multi-language keyword matching (English, German, Dutch) with
    fuzzy substring matching for robust field identification.

    Args:
        request: Autocomplete check configuration

    Returns:
        Analysis results with summary statistics and per-field predictions

    Examples:
        ```bash
        # Basic check (default 0.5 threshold)
        curl -X POST http://localhost:8767/api/accessibility/autocomplete-check \\
          -H "Content-Type: application/json" \\
          -d '{}'

        # Strict check (higher confidence threshold)
        curl -X POST http://localhost:8767/api/accessibility/autocomplete-check \\
          -H "Content-Type: application/json" \\
          -d '{"confidence_threshold": 0.7}'

        # Include hidden and disabled fields
        curl -X POST http://localhost:8767/api/accessibility/autocomplete-check \\
          -H "Content-Type: application/json" \\
          -d '{"include_hidden": true, "include_disabled": true}'
        ```

    Result format:
        ```json
        {
          "ok": true,
          "result": {
            "summary": {
              "total": 10,
              "analyzed": 8,
              "needsAutocomplete": 5,
              "hasAutocomplete": 3,
              "hasCorrectAutocomplete": 2,
              "violations": 3,
              "warnings": 1
            },
            "fields": [
              {
                "selector": "#email",
                "tagName": "input",
                "type": "email",
                "label": "Email Address",
                "currentAutocomplete": null,
                "predictedAutocomplete": "email",
                "confidence": 0.85,
                "status": "missing",
                "level": "violation",
                "message": "Missing autocomplete attribute…",
                "wcagCompliant": false
              }
            ]
          }
        }
        ```
    """
    try:
        client = get_bridge_client()
        service = get_autocomplete_service()

        # Run the autocomplete check
        result = await service.check_autocomplete(
            bridge_executor=client,
            confidence_threshold=request.confidence_threshold,
            include_hidden=request.include_hidden,
            include_disabled=request.include_disabled
        )

        # Check if there was an error
        if "error" in result and result.get("summary", {}).get("analyzed", 0) == 0:
            raise HTTPException(status_code=500, detail=result.get("error", "Autocomplete check failed"))

        # Get current page info
        page_info = client.execute("JSON.stringify({url: window.location.href, title: document.title})")
        page_data = {}
        if page_info.get("ok"):
            try:
                page_data = json.loads(page_info.get("result", "{}"))
            except:
                pass

        return {
            "ok": True,
            "result": result,
            "url": page_data.get("url"),
            "title": page_data.get("title")
        }

    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=f"Bridge server connection error: {str(e)}")
    except TimeoutError as e:
        raise HTTPException(status_code=504, detail=f"Execution timeout: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution error: {str(e)}")
