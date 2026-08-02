"""
Screen reader simulator handlers.

Implements: sr_walk, sr_announce
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from inspekt.core.schemas.screen_reader import (
    SRAnnounceParams,
    SRAnnounceResponse,
    SRDifference,
    SRElementAnnouncement,
    SRWalkParams,
    SRWalkResponse,
    SRWalkSummary,
)

if TYPE_CHECKING:
    from inspekt.services.bridge_executor import BridgeExecutor
    from inspekt.services.script_loader import ScriptLoader

logger = logging.getLogger(__name__)

# Cache loaded data files
_announcements_data: dict | None = None
_verbosity_data: dict | None = None
_known_bugs_data: dict | None = None


def get_executor() -> BridgeExecutor:
    """Get the bridge executor instance."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


def get_script_loader() -> ScriptLoader:
    """Get the script loader instance."""
    from inspekt.services.script_loader import ScriptLoader

    return ScriptLoader()


def _load_data_file(filename: str) -> dict:
    """Load a JSON data file from the screen-reader-rules directory."""
    data_dir = Path(__file__).parent.parent.parent / "data" / "screen-reader-rules"
    path = data_dir / filename
    with open(path) as f:
        return json.load(f)


def _get_announcements() -> dict:
    """Get announcement rules (cached)."""
    global _announcements_data
    if _announcements_data is None:
        _announcements_data = _load_data_file("announcements.json")
    return _announcements_data


def _get_verbosity() -> dict:
    """Get verbosity levels (cached)."""
    global _verbosity_data
    if _verbosity_data is None:
        _verbosity_data = _load_data_file("verbosity-levels.json")
    return _verbosity_data


def _get_known_bugs() -> dict:
    """Get known bugs data (cached)."""
    global _known_bugs_data
    if _known_bugs_data is None:
        _known_bugs_data = _load_data_file("known-bugs.json")
    return _known_bugs_data


def get_bug_details(bug_id: str) -> dict | None:
    """Get full details for a known bug by ID."""
    bugs = _get_known_bugs()
    for bug in bugs.get("bugs", []):
        if bug["id"] == bug_id:
            return bug
    return None


def _build_sr_script(config: dict) -> str:
    """Build the complete SR simulator script with injected data."""
    loader = get_script_loader()
    script = loader.load_script_sync("screen_reader_simulator.js")

    announcements = _get_announcements()
    verbosity = _get_verbosity()
    known_bugs = _get_known_bugs()

    # Replace placeholders with actual data
    script = script.replace("__SR_ANNOUNCEMENTS__", json.dumps(announcements, ensure_ascii=False))
    script = script.replace("__SR_VERBOSITY__", json.dumps(verbosity, ensure_ascii=False))
    script = script.replace("__SR_KNOWN_BUGS__", json.dumps(known_bugs, ensure_ascii=False))
    script = script.replace("__SR_CONFIG__", json.dumps(config, ensure_ascii=False))

    return script


async def sr_walk(params: SRWalkParams) -> SRWalkResponse:
    """
    Walk through a page simulating screen reader announcements.

    Linearizes the page into reading order and generates the text that
    JAWS, NVDA, and/or VoiceOver would announce for each element.
    """
    executor = get_executor()

    config = {
        "mode": "walk",
        "screenReader": params.screen_reader,
        "verbosity": params.verbosity,
        "maxElements": params.max_elements,
    }

    script = _build_sr_script(config)

    try:
        result = await asyncio.to_thread(executor.execute, script, 30.0)

        if not result.get("ok"):
            return SRWalkResponse(
                success=False,
                error=result.get("error", "Execution failed"),
            )

        data = result.get("result", {})

        if not data.get("ok"):
            return SRWalkResponse(
                success=False,
                error=data.get("error", "Walk failed"),
            )

        # Parse announcements
        announcements = [SRElementAnnouncement(**a) for a in data.get("announcements", [])]

        # Parse summary
        summary_data = data.get("summary", {})
        summary = SRWalkSummary(**summary_data) if summary_data else None

        # Parse differences
        differences = [SRDifference(**d) for d in data.get("differences", [])]

        return SRWalkResponse(
            success=True,
            url=data.get("url", ""),
            title=data.get("title", ""),
            element_count=data.get("element_count", 0),
            announcements=announcements,
            summary=summary,
            differences=differences,
            difference_count=data.get("difference_count", 0),
        )

    except Exception as e:
        logger.error(f"SR walk failed: {e}")
        return SRWalkResponse(
            success=False,
            error=str(e),
        )


async def sr_announce(params: SRAnnounceParams) -> SRAnnounceResponse:
    """
    Simulate screen reader announcement for a specific element.

    If no selector is provided, announces the currently focused element.
    """
    executor = get_executor()

    config = {
        "mode": "walk",
        "screenReader": params.screen_reader,
        "verbosity": params.verbosity,
        "maxElements": 1,
    }

    # Use full walk and extract the matching element
    script = _build_sr_script(config)

    try:
        result = await asyncio.to_thread(executor.execute, script, 15.0)

        if not result.get("ok"):
            return SRAnnounceResponse(
                success=False,
                error=result.get("error", "Execution failed"),
            )

        data = result.get("result", {})
        items = data.get("announcements", [])

        if params.selector and items:
            # Filter to matching selector
            matching = [a for a in items if a.get("selector") == params.selector]
            if matching:
                items = matching

        if not items:
            return SRAnnounceResponse(
                success=False,
                error="No element found"
                + (f" matching '{params.selector}'" if params.selector else ""),
            )

        item = items[0]
        return SRAnnounceResponse(
            success=True,
            selector=item.get("selector"),
            role=item.get("role"),
            name=item.get("name"),
            jaws=item.get("jaws"),
            nvda=item.get("nvda"),
            voiceover=item.get("voiceover"),
        )

    except Exception as e:
        logger.error(f"SR announce failed: {e}")
        return SRAnnounceResponse(
            success=False,
            error=str(e),
        )
