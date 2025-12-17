"""
Accessibility command handlers.

Implements: run_axe_audit, run_autocomplete_check
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from inspekt.core.schemas.accessibility import (
    AxeParams,
    AxeResponse,
    AxeSummary,
    AutocompleteParams,
    AutocompleteResponse,
    AutocompleteSummary,
)

if TYPE_CHECKING:
    from inspekt.services.bridge_executor import BridgeExecutor

logger = logging.getLogger(__name__)


def get_executor() -> BridgeExecutor:
    """Get the bridge executor instance."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


def _build_axe_config(
    level: str, tags: str | None, include_passes: bool, include_incomplete: bool
) -> dict:
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
    config = {"runOnly": {"type": "tag", "values": axe_tags}, "resultTypes": ["violations"]}

    # Add optional result types
    if include_passes:
        config["resultTypes"].append("passes")
    if include_incomplete:
        config["resultTypes"].append("incomplete")

    return config


async def run_axe_audit(params: AxeParams) -> AxeResponse:
    """
    Run axe-core accessibility audit on the current page.

    Uses the axe-core library to analyze the page for WCAG conformance.
    """
    executor = get_executor()

    # Build axe configuration
    config = _build_axe_config(
        params.level, params.tags, params.include_passes, params.include_incomplete
    )

    # Load axe-core library (bundled locally)
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    axe_lib_path = scripts_dir / "vendor" / "axe-core.min.js"
    script_path = scripts_dir / "run_axe.js"

    if not axe_lib_path.exists():
        return AxeResponse(
            success=False,
            url=None,
            title=None,
            message=f"axe-core library not found: {axe_lib_path}",
        )

    if not script_path.exists():
        return AxeResponse(
            success=False,
            url=None,
            title=None,
            message=f"Audit script not found: {script_path}",
        )

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
        script = f"""(async function() {{
    // Load axe-core library
    {axe_lib}

    // Run audit
    const auditResult = await {audit_script};
    return auditResult;
}})()"""

        # Execute the script
        result = await asyncio.to_thread(executor.execute, script, params.timeout)

        if not result.get("ok"):
            return AxeResponse(
                success=False,
                url=None,
                title=None,
                message=f"Execution failed: {result.get('error', 'Unknown error')}",
            )

        data = result.get("result", {})

        # Check if script execution failed
        if not data.get("ok"):
            return AxeResponse(
                success=False,
                url=None,
                title=None,
                message=f"Axe execution failed: {data.get('error', 'Unknown error')}",
            )

        # Build summary
        summary_data = data.get("summary", {})
        summary = AxeSummary(
            violation_count=summary_data.get("violation_count", 0),
            pass_count=summary_data.get("pass_count", 0),
            incomplete_count=summary_data.get("incomplete_count", 0),
            critical_count=summary_data.get("critical_count", 0),
            serious_count=summary_data.get("serious_count", 0),
            moderate_count=summary_data.get("moderate_count", 0),
            minor_count=summary_data.get("minor_count", 0),
        )

        return AxeResponse(
            success=True,
            result={
                "url": data.get("url"),
                "title": data.get("title"),
                "timestamp": data.get("timestamp"),
                "axe_version": data.get("axeVersion"),
                "config": config,
                "violations": data.get("violations", []),
                "passes": data.get("passes", []) if params.include_passes else [],
                "incomplete": data.get("incomplete", []) if params.include_incomplete else [],
                "summary": summary,
            },
            url=data.get("url"),
            title=data.get("title"),
            message=f"Audit complete: {summary.violation_count} violations found",
        )

    except Exception as e:
        logger.error(f"Axe audit error: {e}")
        return AxeResponse(
            success=False,
            url=None,
            title=None,
            message=f"Error: {str(e)}",
        )


async def run_autocomplete_check(params: AutocompleteParams) -> AutocompleteResponse:
    """
    Check autocomplete attributes on form fields per WCAG 2.1 SC 1.3.5.

    Uses multi-language heuristics to predict appropriate autocomplete values.
    """
    executor = get_executor()

    try:
        from inspekt.services.autocomplete_service import get_autocomplete_service

        service = get_autocomplete_service()

        # Run the autocomplete check
        result = await service.check_autocomplete(
            bridge_executor=executor,
            confidence_threshold=params.confidence_threshold,
            include_hidden=params.include_hidden,
            include_disabled=params.include_disabled,
        )

        # Check if there was an error
        if "error" in result and result.get("summary", {}).get("analyzed", 0) == 0:
            return AutocompleteResponse(
                success=False,
                url=None,
                title=None,
                message=f"Check failed: {result.get('error', 'Unknown error')}",
            )

        # Get current page info
        page_info_result = await asyncio.to_thread(
            executor.execute,
            "JSON.stringify({url: window.location.href, title: document.title})",
            5.0,
        )
        page_data = {}
        if page_info_result.get("ok"):
            try:
                page_data = json.loads(page_info_result.get("result", "{}"))
            except json.JSONDecodeError:
                pass

        # Build summary
        summary_data = result.get("summary", {})
        summary = AutocompleteSummary(
            total=summary_data.get("total", 0),
            analyzed=summary_data.get("analyzed", 0),
            needs_autocomplete=summary_data.get("needsAutocomplete", 0),
            has_autocomplete=summary_data.get("hasAutocomplete", 0),
            has_correct_autocomplete=summary_data.get("hasCorrectAutocomplete", 0),
            violations=summary_data.get("violations", 0),
            warnings=summary_data.get("warnings", 0),
        )

        return AutocompleteResponse(
            success=True,
            result={
                "summary": summary,
                "fields": result.get("fields", []),
            },
            url=page_data.get("url"),
            title=page_data.get("title"),
            message=f"Check complete: {summary.violations} violations, {summary.warnings} warnings",
        )

    except Exception as e:
        logger.error(f"Autocomplete check error: {e}")
        return AutocompleteResponse(
            success=False,
            url=None,
            title=None,
            message=f"Error: {str(e)}",
        )
