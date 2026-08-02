"""
AI command handlers.

Implements: summarize, describe, ask, do, md_link, element_describe, element_ask

These handlers use the AIIntegrationService to:
- Extract content from the browser
- Call AI providers for content analysis
- Return structured responses
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
from typing import TYPE_CHECKING

from PIL import Image

from inspekt.core.commands.base import EmptyParams
from inspekt.core.schemas.ai import (
    AskParams,
    AskResponse,
    DescribeParams,
    DescribeResponse,
    DoParams,
    DoResponse,
    ElementAskParams,
    ElementAskResponse,
    ElementDescribeParams,
    ElementDescribeResponse,
    MdLinkResponse,
    SummarizeParams,
    SummarizeResponse,
)

if TYPE_CHECKING:
    from pathlib import Path

    from inspekt.services.bridge_executor import BridgeExecutor
    from inspekt.services.script_loader import ScriptLoader

logger = logging.getLogger(__name__)


def get_executor() -> BridgeExecutor:
    """Get the bridge executor instance."""
    from inspekt.services.bridge_executor import BridgeExecutor

    return BridgeExecutor()


def get_script_loader() -> ScriptLoader:
    """Get the script loader instance."""
    from inspekt.services.script_loader import ScriptLoader

    return ScriptLoader()


def get_ai_service():
    """Get the AI integration service."""
    from inspekt.services.ai_integration import get_ai_service

    return get_ai_service()


async def summarize(params: SummarizeParams) -> SummarizeResponse:
    """
    Summarize the current article using AI.

    Extracts article content using Mozilla Readability and generates
    a concise summary using the configured AI model.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load and execute the article extraction script
        script = await script_loader.load_script_async("extract_article.js")
        result = await asyncio.to_thread(executor.execute, script, 30.0)

        if not result.get("ok"):
            return SummarizeResponse(
                title="",
                summary=f"Failed to extract article: {result.get('error', 'Unknown error')}",
                byline=None,
                cached=False,
            )

        article = result.get("result", {})

        # Handle case where no article content found
        if not article or not article.get("content"):
            return SummarizeResponse(
                title=article.get("title", "Untitled"),
                summary="No article content found on this page.",
                byline=article.get("byline"),
                cached=False,
            )

        title = article.get("title", "Untitled")
        content = article.get("content", "")
        byline = article.get("byline")

        # If format is "full", return the full article
        if params.format == "full":
            return SummarizeResponse(
                title=title,
                summary=content,
                byline=byline,
                cached=False,
            )

        # Generate AI summary
        ai_service = get_ai_service()

        summary = ai_service.generate_summary(
            article=article,
            language_override=params.language,
            debug=False,
        )

        return SummarizeResponse(
            title=title,
            summary=summary or "Failed to generate summary.",
            byline=byline,
            cached=False,
        )

    except Exception as e:
        logger.error(f"Summarize error: {e}")
        return SummarizeResponse(
            title="",
            summary=f"Error: {str(e)}",
            byline=None,
            cached=False,
        )


async def describe(params: DescribeParams) -> DescribeResponse:
    """
    Generate an AI-powered description of the page for screen reader users.

    Extracts page structure and uses AI to create a natural description.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load and execute the page structure extraction script
        script = await script_loader.load_script_async("extract_page_structure.js")
        result = await asyncio.to_thread(executor.execute, script, 30.0)

        if not result.get("ok"):
            return DescribeResponse(
                description=f"Failed to extract page structure: {result.get('error', 'Unknown error')}",
                cached=False,
            )

        page_structure = result.get("result", "")

        if not page_structure or not isinstance(page_structure, str):
            return DescribeResponse(
                description="No page structure extracted.",
                cached=False,
            )

        # Generate AI description
        ai_service = get_ai_service()

        description = ai_service.generate_description(
            page_structure=page_structure,
            language_override=params.language,
            debug=False,
        )

        return DescribeResponse(
            description=description or "Failed to generate description.",
            cached=False,
        )

    except Exception as e:
        logger.error(f"Describe error: {e}")
        return DescribeResponse(
            description=f"Error: {str(e)}",
            cached=False,
        )


async def ask(params: AskParams) -> AskResponse:
    """
    Ask a question about the current page using AI.

    Uses the page index to provide context for answering questions.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load and execute the index page script to get page content
        script = await script_loader.load_script_async("index_page.js")
        result = await asyncio.to_thread(executor.execute, script, 30.0)

        if not result.get("ok"):
            return AskResponse(
                answer=f"Failed to index page: {result.get('error', 'Unknown error')}",
                cached=False,
            )

        page_index = result.get("result", {})

        # Build context from page index
        context_parts = []

        if page_index.get("title"):
            context_parts.append(f"Page Title: {page_index['title']}")

        if page_index.get("url"):
            context_parts.append(f"URL: {page_index['url']}")

        if page_index.get("content"):
            context_parts.append(f"\nPage Content:\n{page_index['content']}")

        if page_index.get("headings"):
            headings = page_index["headings"]
            if isinstance(headings, list):
                heading_text = "\n".join([h.get("text", "") for h in headings if h.get("text")])
                context_parts.append(f"\nHeadings:\n{heading_text}")

        context = "\n".join(context_parts)

        # Build prompt for AI
        ai_service = get_ai_service()

        prompt = f"""Based on the following page content, answer this question: {params.question}

{context}

Please provide a concise, accurate answer based only on the information provided."""

        answer = ai_service.call_ai(prompt=prompt, command="ask")

        return AskResponse(
            answer=answer,
            cached=False,
        )

    except Exception as e:
        logger.error(f"Ask error: {e}")
        return AskResponse(
            answer=f"Error: {str(e)}",
            cached=False,
        )


async def do(params: DoParams) -> DoResponse:
    """
    Find and execute actionable elements matching a natural language instruction.

    Uses AI to match the instruction with clickable elements on the page.
    """
    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Load and execute the actionable elements extraction script
        script = await script_loader.load_script_async("extract_actionable_elements.js")
        result = await asyncio.to_thread(executor.execute, script, 15.0)

        if not result.get("ok"):
            return DoResponse(
                success=False,
                element_tag=None,
                element_text=None,
                confidence=None,
            )

        # Extract actionable elements from the structured result
        data = result.get("result", {})
        elements = data.get("actionableElements", []) if isinstance(data, dict) else data

        if not elements:
            return DoResponse(
                success=False,
                element_tag=None,
                element_text="No actionable elements found on page",
                confidence=None,
            )

        # Build element descriptions for AI matching
        element_descriptions = []
        for i, el in enumerate(elements[:50]):  # Limit to first 50 elements
            desc = f"{i}: [{el.get('tag', 'unknown')}] {el.get('text', '')[:100]}"
            if el.get("href"):
                desc += f" -> {el.get('href')[:50]}"
            element_descriptions.append(desc)

        elements_text = "\n".join(element_descriptions)

        # Ask AI to match instruction to element
        ai_service = get_ai_service()

        prompt = f"""Given this user instruction: "{params.instruction}"

And these clickable elements on the page:
{elements_text}

Which element number (0-{len(elements)-1}) best matches the user's intent?
Respond with ONLY the number and a confidence score (0-100) in format: NUMBER,CONFIDENCE
Example: 5,85"""

        response = ai_service.call_ai(prompt=prompt, command="do", max_tokens=50)

        # Parse AI response
        match = re.match(r"(\d+)\s*,\s*(\d+)", response.strip())
        if not match:
            return DoResponse(
                success=False,
                element_tag=None,
                element_text=f"Could not parse AI response: {response}",
                confidence=None,
            )

        element_index = int(match.group(1))
        confidence = int(match.group(2)) / 100.0

        if element_index >= len(elements):
            return DoResponse(
                success=False,
                element_tag=None,
                element_text="AI returned invalid element index",
                confidence=confidence,
            )

        target_element = elements[element_index]

        # Only auto-click if confidence >= 75%
        if confidence >= 0.75:
            # Click the element using actionId as class selector
            action_id = target_element.get('actionId', '')
            selector = f".{action_id}" if action_id else ""
            click_script = f"""
            (function() {{
                const selector = {json.dumps(selector)};
                const el = document.querySelector(selector);
                if (el) {{
                    el.click();
                    return {{
                        success: true,
                        tag: el.tagName.toLowerCase(),
                        text: el.textContent.trim().substring(0, 100)
                    }};
                }}
                return {{ success: false }};
            }})()
            """
            click_result = await asyncio.to_thread(executor.execute, click_script, 5.0)

            if click_result.get("ok") and click_result.get("result", {}).get("success"):
                return DoResponse(
                    success=True,
                    element_tag=target_element.get("tag"),
                    element_text=target_element.get("text", "")[:100],
                    confidence=confidence,
                )

        return DoResponse(
            success=False,
            element_tag=target_element.get("tag"),
            element_text=f"Match found but confidence too low ({confidence:.0%}): {target_element.get('text', '')[:100]}",
            confidence=confidence,
        )

    except Exception as e:
        logger.error(f"Do error: {e}")
        return DoResponse(
            success=False,
            element_tag=None,
            element_text=str(e),
            confidence=None,
        )


async def md_link(params: EmptyParams) -> MdLinkResponse:
    """
    Get a Markdown-formatted link for the current page.

    Returns [title](url) format with a cleaned page title.
    """
    executor = get_executor()

    try:
        # Get page info with simple JavaScript
        code = """
        (function() {
            return {
                url: window.location.href,
                title: document.title
            };
        })()
        """
        result = await asyncio.to_thread(executor.execute, code, 5.0)

        if not result.get("ok"):
            return MdLinkResponse(
                url="",
                title="",
                raw_title="",
                website_name="",
                markdown="",
            )

        data = result.get("result", {})
        url = data.get("url", "")
        raw_title = data.get("title", "")

        # Clean the title - strip website name suffixes
        # Splits on " |", " -", " –", " —"
        cleaned_title = raw_title
        website_name = ""

        for separator in [" | ", " - ", " – ", " — "]:
            if separator in raw_title:
                parts = raw_title.split(separator)
                # Usually the website name is the last part
                cleaned_title = parts[0].strip()
                website_name = parts[-1].strip() if len(parts) > 1 else ""
                break

        # Create markdown link
        markdown = f"[{cleaned_title}]({url})"

        return MdLinkResponse(
            url=url,
            title=cleaned_title,
            raw_title=raw_title,
            website_name=website_name,
            markdown=markdown,
        )

    except Exception as e:
        logger.error(f"Markdown link error: {e}")
        return MdLinkResponse(
            url="",
            title="",
            raw_title="",
            website_name="",
            markdown="",
        )


# === Element AI Helpers ===


def _precheck_element_sync(executor, source: str, timeout: float = 3.0) -> dict:
    """
    Quick SYNCHRONOUS pre-check to validate element exists before expensive operations.

    This runs synchronously (not async) to ensure fast-fail behavior - if the bridge
    is unresponsive, we timeout cleanly without background threads lingering.

    Returns dict with:
        - ok: True if element is valid
        - error: Error message if validation failed
        - hint: Helpful hint for the user
        - tag: Element tag name (if ok)

    Uses a short timeout (default 3s) to fail fast on stale connections.
    """
    precheck_code = f"""(function() {{
        if ('{source}' === 'inspected') {{
            const el = window.__INSPEKT_INSPECTED_ELEMENT__;
            if (!el) return {{ ok: false, error: 'No element selected', hint: 'Select an element in DevTools first' }};
            if (!document.body.contains(el)) return {{ ok: false, error: 'Element was removed from the page', hint: 'The page may have changed. Select a new element.' }};
            return {{ ok: true, tag: el.tagName.toLowerCase() }};
        }} else if ('{source}' === 'focused') {{
            const el = document.activeElement;
            if (!el || el === document.body) return {{ ok: false, error: 'No element focused', hint: 'Tab to an element or click an input/button' }};
            return {{ ok: true, tag: el.tagName.toLowerCase() }};
        }} else if ('{source}' === 'selection') {{
            const sel = window.getSelection();
            if (!sel || sel.isCollapsed) return {{ ok: false, error: 'No text selected', hint: 'Select some text on the page first' }};
            return {{ ok: true, tag: 'selection' }};
        }}
        return {{ ok: true }};
    }})()"""

    try:
        # Run synchronously with fast_poll=True for short HTTP timeout
        result = executor.execute(
            precheck_code,
            timeout,  # Use the provided timeout directly
            False,    # retry_on_timeout
            True,     # skip_domain_check (pre-check shouldn't prompt)
            True,     # fast_poll (short HTTP timeout for fail-fast)
        )
    except TimeoutError:
        return {
            "ok": False,
            "error": "Bridge connection timed out",
            "hint": "Try refreshing the page or restarting `inspekt start`"
        }
    except ConnectionError as e:
        return {
            "ok": False,
            "error": str(e),
            "hint": "Make sure `inspekt start` is running"
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Pre-check failed: {e}",
            "hint": "Try refreshing the page"
        }

    if not result.get("ok"):
        return {
            "ok": False,
            "error": result.get("error", "Bridge not responding"),
            "hint": "Try refreshing the page"
        }

    precheck_data = result.get("result", {})
    if not precheck_data.get("ok"):
        return {
            "ok": False,
            "error": precheck_data.get("error", "Unknown error"),
            "hint": precheck_data.get("hint", "")
        }

    return {"ok": True, "tag": precheck_data.get("tag", "unknown")}


async def _get_element_data(executor, script_loader, source: str) -> dict:
    """
    Get element data for inspected, focused, or selection source.

    Returns dict with element metadata or error information.
    """
    if source == "selection":
        # For selection, get the selection info
        script = await script_loader.load_script_async("get_selection.js")
        result = await asyncio.to_thread(executor.execute, script, 10.0)

        if not result.get("ok"):
            return {"error": result.get("error", "Failed to get selection")}

        selection_data = result.get("result", {})
        if not selection_data.get("hasSelection"):
            return {"error": "No text is currently selected", "hint": "Select some text on the page first"}

        # Return selection data in a format similar to element data
        return {
            "ok": True,
            "tag": "selection",
            "textContent": selection_data.get("text", ""),
            "htmlContent": selection_data.get("html", ""),
            "accessibility": {
                "accessibleName": selection_data.get("text", "")[:100],
                "accessibleNameSource": "selected text",
            },
            "dimensions": selection_data.get("position", {}),
            "container": selection_data.get("container", {}),
            "isSelection": True,
        }
    else:
        # For inspected or focused, use get_element_data.js
        script = await script_loader.load_script_async("get_element_data.js")
        # Replace the placeholder with the source type
        script = script.replace("'SOURCE_TYPE_PLACEHOLDER'", f"'{source}'")
        result = await asyncio.to_thread(executor.execute, script, 10.0)

        if not result.get("ok"):
            return {"error": result.get("error", "Failed to get element data")}

        element_data = result.get("result", {})
        if element_data.get("error"):
            return element_data  # Pass through error with hint

        return element_data


# ============================================================================
# COMPREHENSIVE MODE: Event Handlers & Accessibility Tree
# ============================================================================


async def _get_event_handlers(executor, script_loader, source: str) -> dict:
    """
    Get inline event handlers from element using get_event_handlers.js.

    Returns dict with handlers list and summary, or error info.
    """
    try:
        script = await script_loader.load_script_async("get_event_handlers.js")
        script = script.replace("'SOURCE_TYPE_PLACEHOLDER'", f"'{source}'")
        result = await asyncio.to_thread(executor.execute, script, 10.0)

        if not result.get("ok"):
            return {"ok": False, "error": result.get("error", "Failed to get event handlers")}

        return result.get("result", {})
    except Exception as e:
        logger.warning(f"Failed to get event handlers: {e}")
        return {"ok": False, "error": str(e)}


def _get_cdp_event_listeners(executor, script_loader, source: str) -> dict | None:
    """
    Get event listeners via CDP DOMDebugger.getEventListeners.

    This requires debugger attachment and returns all addEventListener() listeners.
    Uses a JavaScript bridge script that sends postMessage to the extension.
    Returns None if CDP is unavailable or fails.
    """
    try:
        script = script_loader.load_with_substitution_sync(
            "get_event_listeners_cdp.js",
            {"SOURCE_TYPE_PLACEHOLDER": source}
        )
        response = executor.execute(script, timeout=20.0)

        if response and response.get("ok"):
            result = response.get("result", {})
            if result.get("ok"):
                return result
        return None
    except Exception as e:
        logger.warning(f"CDP event listeners unavailable: {e}")
        return None


def _get_accessibility_tree(executor, script_loader, source: str, depth: int = 10) -> dict | None:
    """
    Get partial accessibility tree via CDP Accessibility.getPartialAXTree.

    Returns the accessibility tree for the element and its descendants.
    Uses a JavaScript bridge script that sends postMessage to the extension.
    Returns None if CDP is unavailable or fails.
    """
    try:
        script = script_loader.load_with_substitution_sync(
            "get_accessibility_tree_cdp.js",
            {
                "SOURCE_TYPE_PLACEHOLDER": source,
                "DEPTH_PLACEHOLDER": str(depth),
            }
        )
        response = executor.execute(script, timeout=20.0)

        if response and response.get("ok"):
            result = response.get("result", {})
            if result.get("ok"):
                return result
        return None
    except Exception as e:
        logger.warning(f"CDP accessibility tree unavailable: {e}")
        return None


def _merge_event_handlers(inline_handlers: dict, cdp_listeners: dict) -> dict:
    """
    Merge inline handlers with CDP-retrieved addEventListener listeners.
    """
    if not inline_handlers.get("ok"):
        inline_handlers = {"ok": True, "handlers": [], "summary": {}, "totalCount": 0}

    merged_handlers = list(inline_handlers.get("handlers", []))
    merged_summary = dict(inline_handlers.get("summary", {}))

    # Add CDP listeners
    if cdp_listeners and cdp_listeners.get("ok"):
        for listener in cdp_listeners.get("listeners", []):
            merged_handlers.append({
                "selector": "(CDP)",
                "type": listener.get("type", "unknown"),
                "source": "addEventListener",
                "code": listener.get("handler", {}).get("description", "[function]"),
                "element": "",
                "useCapture": listener.get("useCapture", False),
                "passive": listener.get("passive", False),
                "once": listener.get("once", False),
                "lineNumber": listener.get("lineNumber"),
                "columnNumber": listener.get("columnNumber"),
            })
            event_type = listener.get("type", "unknown")
            merged_summary[event_type] = merged_summary.get(event_type, 0) + 1

    return {
        "ok": True,
        "handlers": merged_handlers,
        "summary": merged_summary,
        "totalCount": len(merged_handlers),
        "cdpAvailable": cdp_listeners is not None and cdp_listeners.get("ok", False),
    }


def _format_audit_section_for_prompt(audit_results: dict) -> str:
    """
    Format accessibility audit results for the AI prompt.
    """
    if not audit_results:
        return "--- ACCESSIBILITY AUDIT ---\nNo audit results available."

    lines = ["--- ACCESSIBILITY AUDIT ---"]

    # Summary
    summary = audit_results.get("summary", {})
    violations_count = summary.get("violations", 0)
    warnings_count = summary.get("warnings", 0)
    passes_count = summary.get("passes", 0)
    engines = ", ".join(summary.get("engines_used", []))

    lines.append(f"Engines: {engines or 'none'}")
    lines.append(f"Summary: {violations_count} violations, {warnings_count} warnings, {passes_count} passes")

    # Violations (most important)
    violations = audit_results.get("violations", [])
    if violations:
        lines.append("\nVIOLATIONS:")
        for v in violations[:10]:  # Limit to 10 for prompt size
            impact = v.get("impact", "unknown")
            wcag = ", ".join(v.get("wcag", [])) or "N/A"
            engines = ", ".join(v.get("engines", []))
            lines.append(f"  [{impact.upper()}] {v.get('description', 'No description')}")
            lines.append(f"    Rule: {v.get('rule_id', 'unknown')} | WCAG: {wcag} | Found by: {engines}")

    # Warnings (if few violations)
    warnings = audit_results.get("warnings", [])
    if warnings and violations_count < 5:
        lines.append("\nWARNINGS (needs review):")
        for w in warnings[:5]:
            lines.append(f"  - {w.get('description', 'No description')} ({w.get('rule_id', 'unknown')})")

    if not violations and not warnings:
        lines.append("\nNo accessibility issues found by automated testing.")
        lines.append("(Note: Automated testing catches ~30-50% of accessibility issues)")

    return "\n".join(lines)


def _format_event_handlers_section(handlers_data: dict) -> str:
    """
    Format event handlers for the AI prompt.
    """
    lines = ["--- EVENT HANDLERS ---"]

    if not handlers_data.get("ok"):
        lines.append("Event handler extraction failed.")
        return "\n".join(lines)

    handlers = handlers_data.get("handlers", [])
    summary = handlers_data.get("summary", {})
    cdp_available = handlers_data.get("cdpAvailable", False)

    if not handlers:
        lines.append("No event handlers found on this element or its descendants.")
        if not cdp_available:
            lines.append("(Note: Only inline handlers checked; addEventListener listeners require DevTools)")
        return "\n".join(lines)

    # Summary by event type
    if summary:
        summary_str = ", ".join(f"{k}: {v}" for k, v in sorted(summary.items()))
        lines.append(f"Summary: {summary_str}")

    # List handlers (limit for prompt size)
    lines.append(f"\nHandlers ({len(handlers)} total):")
    for h in handlers[:15]:  # Limit to 15
        source = h.get("source", "unknown")
        event_type = h.get("type", "unknown")
        code = h.get("code", "")
        if len(code) > 100:
            code = code[:100] + "…"

        if source == "addEventListener":
            line_info = ""
            if h.get("lineNumber"):
                line_info = f" (line {h['lineNumber']})"
            lines.append(f"  [{event_type}] addEventListener{line_info}: {code}")
        else:
            lines.append(f"  [{event_type}] {source}: {code}")

    if len(handlers) > 15:
        lines.append(f"  ... and {len(handlers) - 15} more handlers")

    if not cdp_available:
        lines.append("\n(Note: addEventListener listeners unavailable; only inline handlers shown)")

    return "\n".join(lines)


def _format_accessibility_tree_section(ax_tree: dict) -> str:
    """
    Format accessibility tree for the AI prompt.
    """
    lines = ["--- ACCESSIBILITY TREE ---"]

    if not ax_tree or not ax_tree.get("ok"):
        lines.append("Accessibility tree unavailable.")
        lines.append("(Requires Chrome DevTools Protocol access)")
        return "\n".join(lines)

    nodes = ax_tree.get("nodes", [])
    if not nodes:
        lines.append("Empty accessibility tree.")
        return "\n".join(lines)

    lines.append(f"Nodes: {len(nodes)}")

    def format_node(node: dict, indent: int = 0) -> list[str]:
        """Recursively format a single AXTree node."""
        result = []
        prefix = "  " * indent

        role = node.get("role", {}).get("value", "unknown") if node.get("role") else "unknown"
        name = node.get("name", {}).get("value", "") if node.get("name") else ""

        if node.get("ignored"):
            return result  # Skip ignored nodes

        # Format: role "name"
        if name:
            result.append(f'{prefix}{role} "{name}"')
        else:
            result.append(f"{prefix}{role}")

        # Add key properties
        properties = node.get("properties", [])
        for prop in properties:
            prop_name = prop.get("name", "")
            prop_value = prop.get("value", {}).get("value", "")
            if prop_name in ["focusable", "disabled", "expanded", "pressed", "checked", "selected", "required"]:
                if prop_value:
                    result.append(f"{prefix}  {prop_name}: {prop_value}")

        return result

    # Build tree structure
    for node in nodes[:20]:  # Limit nodes for prompt size
        node_lines = format_node(node, indent=0)
        lines.extend(node_lines)

    if len(nodes) > 20:
        lines.append(f"  ... and {len(nodes) - 20} more nodes")

    return "\n".join(lines)


def _format_comprehensive_prompt(
    base_prompt: str,
    element_context: str,
    audit_results: dict | None,
    event_handlers: dict | None,
    accessibility_tree: dict | None,
    question: str,
    language: str | None,
) -> str:
    """
    Format the comprehensive prompt with all diagnostics for the AI.
    """
    sections = [base_prompt]

    # Element metadata (always included)
    sections.append(f"--- ELEMENT METADATA ---\n{element_context}")

    # Accessibility audit
    if audit_results:
        sections.append(_format_audit_section_for_prompt(audit_results))

    # Event handlers
    if event_handlers:
        sections.append(_format_event_handlers_section(event_handlers))

    # Accessibility tree
    if accessibility_tree:
        sections.append(_format_accessibility_tree_section(accessibility_tree))

    # User question
    sections.append(f"--- USER QUESTION ---\n{question}")

    # Language instruction
    if language:
        sections.append(f"Provide your response in {language}.")

    return "\n\n".join(sections)


async def _take_element_screenshot(executor, script_loader, source: str) -> str | None:
    """
    Take a screenshot of the element.

    Returns base64 data URL or None if failed.
    """
    script = await script_loader.load_script_async("screenshot_unified.js")

    # Determine selector based on source
    if source == "inspected":
        selector = "$0"  # DevTools inspected element
    elif source == "focused":
        selector = "focused"  # Special selector for focused element
    else:
        selector = "selection"  # Selection area

    # Configure for element screenshot
    options = {
        "selector": selector,
        "format": "jpeg",
        "quality": 85,
    }

    # Replace placeholders
    script = script.replace("'MODE_PLACEHOLDER'", "'node'")
    script = script.replace("OPTIONS_PLACEHOLDER", json.dumps(options))

    result = await asyncio.to_thread(executor.execute, script, 30.0)

    if result.get("ok"):
        data = result.get("result", {})
        # Return the data URL (already includes data:image/... prefix)
        return data.get("dataUrl") or data.get("data")

    logger.warning(f"Screenshot failed: {result.get('error')}")
    return None


def _optimize_screenshot_for_ai(data_url: str, max_size: int = 1024, quality: int = 75) -> str:
    """
    Optimize a screenshot for AI vision processing.

    Converts to JPEG and resizes if too large to reduce API payload size
    and improve processing speed.

    Args:
        data_url: Base64 data URL (data:image/...;base64,...)
        max_size: Maximum width/height in pixels
        quality: JPEG quality (1-100)

    Returns:
        Optimized base64 data URL
    """
    try:
        # Parse data URL
        if ";base64," not in data_url:
            logger.warning("Invalid data URL format, returning as-is")
            return data_url

        header, base64_data = data_url.split(";base64,", 1)

        # Decode base64
        image_bytes = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to RGB if necessary (e.g., RGBA or palette mode)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')

        # Resize if too large
        width, height = img.size
        if width > max_size or height > max_size:
            if width > height:
                new_width = max_size
                new_height = int(height * (max_size / width))
            else:
                new_height = max_size
                new_width = int(width * (max_size / height))

            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            logger.debug(f"Resized image from {width}x{height} to {new_width}x{new_height}")

        # Convert to JPEG in memory
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        buffer.seek(0)

        # Encode to base64
        optimized_base64 = base64.b64encode(buffer.read()).decode('utf-8')
        optimized_url = f"data:image/jpeg;base64,{optimized_base64}"

        original_size = len(base64_data)
        new_size = len(optimized_base64)
        reduction = (1 - new_size / original_size) * 100
        logger.debug(f"Optimized image: {original_size} -> {new_size} bytes ({reduction:.1f}% reduction)")

        return optimized_url

    except Exception as e:
        logger.warning(f"Failed to optimize screenshot: {e}, returning original")
        return data_url


def _optimize_screenshot_for_report(data_url: str) -> str:
    """
    Optimize a screenshot for rich HTML report using PNG + oxipng.

    Converts to PNG and applies lossless oxipng compression for
    high quality at smaller file sizes.

    Args:
        data_url: Base64 data URL (data:image/...;base64,...)

    Returns:
        Optimized base64 data URL (PNG format)
    """
    from inspekt.services.image_optimizer import is_oxipng_installed, optimize_png_data

    try:
        # Parse data URL
        if ";base64," not in data_url:
            logger.warning("Invalid data URL format, returning as-is")
            return data_url

        header, base64_data = data_url.split(";base64,", 1)

        # Decode base64
        image_bytes = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(image_bytes))

        # Convert to PNG in memory
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', optimize=True)
        png_bytes = buffer.getvalue()

        original_size = len(png_bytes)

        # Apply oxipng optimization if available
        if is_oxipng_installed():
            png_bytes = optimize_png_data(png_bytes, level=3, strip=True)
            new_size = len(png_bytes)
            reduction = (1 - new_size / original_size) * 100
            logger.debug(f"oxipng optimization: {original_size} -> {new_size} bytes ({reduction:.1f}% reduction)")

        # Encode to base64
        optimized_base64 = base64.b64encode(png_bytes).decode('utf-8')
        return f"data:image/png;base64,{optimized_base64}"

    except Exception as e:
        logger.warning(f"Failed to optimize screenshot for report: {e}, returning original")
        return data_url


def _build_debug_data(
    prompt: str,
    provider_name: str,
    model: str,
    image_size_kb: int,
    question: str,
) -> dict:
    """
    Build debug data for rich report when --debug is used.

    Returns dict with prompt, parameters, and cURL command.
    """
    import os
    import shlex

    # Build API parameters
    api_params = {
        "provider": provider_name,
        "model": model,
        "max_tokens": 4096,
        "image_size_kb": image_size_kb,
    }

    # Generate cURL command based on provider
    curl_command = _generate_curl_command(provider_name, model, prompt, image_size_kb)

    return {
        "prompt": prompt,
        "question": question,
        "api_params": api_params,
        "curl_command": curl_command,
    }


def _generate_curl_command(provider_name: str, model: str, prompt: str, image_size_kb: int) -> str:
    """
    Generate a representative cURL command for the AI API call.

    This shows how the API request would look - actual implementation
    may vary based on SDK usage.
    """
    import shlex

    # Truncate prompt for display (show first/last 500 chars if too long)
    display_prompt = prompt
    if len(prompt) > 1200:
        display_prompt = prompt[:500] + "\n\n... [truncated] ...\n\n" + prompt[-500:]

    # Escape for shell
    escaped_prompt = shlex.quote(display_prompt)

    if provider_name.lower() == "anthropic":
        return f'''curl https://api.anthropic.com/v1/messages \\
  -H "Content-Type: application/json" \\
  -H "x-api-key: $ANTHROPIC_API_KEY" \\
  -H "anthropic-version: 2023-06-01" \\
  -d '{{
    "model": "{model}",
    "max_tokens": 4096,
    "messages": [
      {{
        "role": "user",
        "content": [
          {{
            "type": "image",
            "source": {{
              "type": "base64",
              "media_type": "image/jpeg",
              "data": "<{image_size_kb}KB base64 image data>"
            }}
          }},
          {{
            "type": "text",
            "text": {escaped_prompt}
          }}
        ]
      }}
    ]
  }}'
'''
    elif provider_name.lower() == "openai":
        return f'''curl https://api.openai.com/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $OPENAI_API_KEY" \\
  -d '{{
    "model": "{model}",
    "max_tokens": 4096,
    "messages": [
      {{
        "role": "user",
        "content": [
          {{
            "type": "image_url",
            "image_url": {{
              "url": "data:image/jpeg;base64,<{image_size_kb}KB base64 image data>"
            }}
          }},
          {{
            "type": "text",
            "text": {escaped_prompt}
          }}
        ]
      }}
    ]
  }}'
'''
    else:
        return f"# cURL command not available for provider: {provider_name}"


def _format_element_context(element_data: dict) -> str:
    """
    Format element metadata as context for AI prompt.
    """
    lines = []

    # Basic info
    tag = element_data.get("tag", "unknown")
    lines.append(f"Element: <{tag}>")

    if element_data.get("id"):
        lines.append(f"ID: {element_data['id']}")

    if element_data.get("classes"):
        lines.append(f"Classes: {', '.join(element_data['classes'])}")

    # Accessibility info
    a11y = element_data.get("accessibility", {})
    if a11y.get("accessibleName"):
        lines.append(f"Accessible Name: \"{a11y['accessibleName']}\"")
        lines.append(f"Name Source: {a11y.get('accessibleNameSource', 'unknown')}")

    if a11y.get("role"):
        lines.append(f"Role: {a11y['role']}")

    if a11y.get("ariaLabel"):
        lines.append(f"aria-label: \"{a11y['ariaLabel']}\"")

    lines.append(f"Focusable: {'Yes' if a11y.get('focusable') else 'No'}")

    if a11y.get("tabIndex") is not None:
        lines.append(f"tabindex: {a11y['tabIndex']}")

    if a11y.get("disabled"):
        lines.append("State: Disabled")

    # Dimensions
    dims = element_data.get("dimensions", {})
    if dims.get("width") and dims.get("height"):
        lines.append(f"Size: {dims['width']}×{dims['height']}px")

    # Visibility
    lines.append(f"Visible: {'Yes' if element_data.get('visible') else 'No'}")

    # Styles (key ones for accessibility)
    styles = element_data.get("styles", {})
    if styles.get("color"):
        lines.append(f"Text Color: {styles['color']}")
    if styles.get("backgroundColor"):
        lines.append(f"Background: {styles['backgroundColor']}")
    if styles.get("fontSize"):
        lines.append(f"Font Size: {styles['fontSize']}")

    # Semantic info
    semantic = element_data.get("semantic", {})
    semantic_flags = []
    if semantic.get("isInteractive"):
        semantic_flags.append("Interactive")
    if semantic.get("isFormElement"):
        semantic_flags.append("Form Element")
    if semantic.get("isLandmark"):
        semantic_flags.append("Landmark")
    if semantic_flags:
        lines.append(f"Semantic: {', '.join(semantic_flags)}")

    # Text content (truncated)
    text = element_data.get("textContent", "")
    if text:
        lines.append(f"Text Content: \"{text[:100]}{'…' if len(text) > 100 else ''}\"")

    return "\n".join(lines)


async def element_describe(params: ElementDescribeParams) -> ElementDescribeResponse:
    """
    Generate an AI-powered accessibility description of a specific element.

    Uses vision AI to analyze a screenshot of the element along with its
    metadata to provide a concise, accessibility-focused description.
    """
    import click

    def debug_print(msg: str) -> None:
        if params.debug:
            click.secho(f"[DEBUG] {msg}", fg="cyan", err=True)

    executor = get_executor()
    script_loader = get_script_loader()

    try:
        # Pre-check: Quick validation with short timeout (fail fast on stale state)
        debug_print("Pre-check: Validating element exists (3s timeout)")
        precheck = _precheck_element_sync(executor, params.source)

        if not precheck.get("ok"):
            error = precheck.get("error", "Unknown error")
            hint = precheck.get("hint", "")
            debug_print(f"Pre-check failed: {error}")
            return ElementDescribeResponse(
                description=f"Error: {error}" + (f" ({hint})" if hint else ""),
                element_type="unknown",
                accessible_name=None,
                source=params.source,
            )

        debug_print(f"Pre-check passed: element <{precheck.get('tag', '?')}> exists")

        # Step 1: Get element data
        debug_print(f"Step 1: Getting element data for source='{params.source}'")
        element_data = await _get_element_data(executor, script_loader, params.source)

        if element_data.get("error"):
            debug_print(f"Error getting element data: {element_data.get('error')}")
            return ElementDescribeResponse(
                description=f"Error: {element_data['error']}" + (f" ({element_data.get('hint', '')})" if element_data.get('hint') else ""),
                element_type="unknown",
                accessible_name=None,
                source=params.source,
            )

        debug_print(f"Element data: tag=<{element_data.get('tag')}>, id={element_data.get('id')}, classes={element_data.get('classes')}")
        if params.debug:
            a11y = element_data.get("accessibility", {})
            debug_print(f"Accessibility: name='{a11y.get('accessibleName', '')}', role={a11y.get('role')}, focusable={a11y.get('focusable')}")

        # Step 2: Take screenshot
        debug_print("Step 2: Taking element screenshot")
        screenshot = await _take_element_screenshot(executor, script_loader, params.source)

        if not screenshot:
            debug_print("Screenshot failed - element may be hidden or off-screen")
            return ElementDescribeResponse(
                description="Failed to capture element screenshot. The element may be hidden or off-screen.",
                element_type=element_data.get("tag", "unknown"),
                accessible_name=element_data.get("accessibility", {}).get("accessibleName"),
                source=params.source,
            )

        debug_print(f"Screenshot captured: {len(screenshot)} chars ({len(screenshot) * 3 // 4 // 1024} KB approx)")

        # Step 3: Optimize screenshot for AI (resize and convert to JPEG)
        debug_print("Step 3: Optimizing screenshot (resize to 1024px max, JPEG 80%)")
        optimized_screenshot = _optimize_screenshot_for_ai(screenshot, max_size=1024, quality=80)
        reduction = (1 - len(optimized_screenshot) / len(screenshot)) * 100
        debug_print(f"Optimized: {len(screenshot)} → {len(optimized_screenshot)} chars ({reduction:.1f}% reduction)")

        # Step 4: Load prompt and format with element context
        debug_print("Step 4: Loading prompt and formatting context")
        ai_service = get_ai_service()
        base_prompt = ai_service.load_prompt("element-describe.prompt")
        context = _format_element_context(element_data)

        full_prompt = f"{base_prompt}\n\n--- ELEMENT METADATA ---\n{context}"

        # Add language instruction if specified
        if params.language:
            full_prompt += f"\n\nProvide your response in {params.language}."
            debug_print(f"Added language instruction: {params.language}")

        debug_print(f"Prompt length: {len(full_prompt)} chars")
        if params.debug:
            click.secho("\n--- FULL PROMPT ---", fg="cyan", err=True)
            click.echo(full_prompt, err=True)
            click.secho("--- END PROMPT ---\n", fg="cyan", err=True)

        # Step 5: Call vision AI
        manager = ai_service.get_provider_manager()
        provider, _ = manager.resolve_provider(None, "element_describe")
        vision_model = provider.get_default_vision_model()
        debug_print(f"Step 5: Calling vision AI (provider={provider.name}, model={vision_model})")

        description = ai_service.call_ai_vision(
            prompt=full_prompt,
            image_data_url=optimized_screenshot,
            command="element_describe",
        )

        debug_print(f"AI response received: {len(description)} chars")

        return ElementDescribeResponse(
            description=description,
            element_type=element_data.get("tag", "unknown"),
            accessible_name=element_data.get("accessibility", {}).get("accessibleName"),
            source=params.source,
        )

    except Exception as e:
        logger.error(f"Element describe error: {e}")
        return ElementDescribeResponse(
            description=f"Error: {str(e)}",
            element_type="unknown",
            accessible_name=None,
            source=params.source,
        )


def _run_scoped_audits(client, source: str = "inspected") -> dict:
    """
    Run all accessibility engines scoped to the inspected element.

    Returns consolidated audit results from axe, ibm, and hcs engines.
    Each engine is executed with the inspected element as the scope/context.
    """
    import json
    from pathlib import Path

    results = {"axe": None, "ibm": None, "hcs": None}
    engines_used = []

    # Verify inspected element exists
    if source == "inspected":
        check_result = client.execute(
            "(function() { return !!window.__INSPEKT_INSPECTED_ELEMENT__; })()",
            timeout=5.0
        )
        if not check_result.get("ok") or not check_result.get("result"):
            return {
                "violations": [],
                "warnings": [],
                "passes": [],
                "summary": {
                    "violations": 0,
                    "warnings": 0,
                    "passes": 0,
                    "engines_used": [],
                    "error": "No element inspected"
                }
            }

    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    vendor_dir = scripts_dir / "vendor"

    # Run axe-core with scoped context
    try:
        axe_result = _run_scoped_axe(client, scripts_dir, vendor_dir)
        if axe_result and not axe_result.get("error"):
            results["axe"] = axe_result
            engines_used.append("axe")
    except Exception as e:
        logger.warning(f"Axe scoped audit failed: {e}")

    # Run IBM with scoped context
    try:
        ibm_result = _run_scoped_ibm(client, scripts_dir, vendor_dir)
        if ibm_result and not ibm_result.get("error"):
            results["ibm"] = ibm_result
            engines_used.append("ibm")
    except Exception as e:
        logger.warning(f"IBM scoped audit failed: {e}")

    # Run HTMLCS with scoped context
    try:
        hcs_result = _run_scoped_htmlcs(client, scripts_dir, vendor_dir)
        if hcs_result and not hcs_result.get("error"):
            results["hcs"] = hcs_result
            engines_used.append("hcs")
    except Exception as e:
        logger.warning(f"HTMLCS scoped audit failed: {e}")

    return _consolidate_audit_results(results, engines_used)


def _run_scoped_axe(client, scripts_dir: Path, vendor_dir: Path) -> dict | None:
    """Run axe-core scoped to the inspected element."""
    import json

    axe_lib_path = vendor_dir / "axe-core.min.js"
    script_path = scripts_dir / "run_axe.js"

    if not axe_lib_path.exists() or not script_path.exists():
        return {"error": "axe-core not found"}

    # Load scripts
    with open(axe_lib_path) as f:
        axe_lib = f.read()
    with open(script_path) as f:
        audit_script = f.read()

    # Build config for WCAG 2.1 AA
    config = {
        "runOnly": {
            "type": "tag",
            "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
        },
        "resultTypes": ["violations", "passes", "incomplete"],
        "__showBadges": False,
    }

    # Replace config placeholder
    audit_script = audit_script.replace("__AXE_CONFIG__", json.dumps(config))

    # KEY: Replace 'document' with inspected element reference for scoping
    # This replaces the first occurrence (the axe.run context parameter)
    audit_script = audit_script.replace(
        "document",
        "window.__INSPEKT_INSPECTED_ELEMENT__",
        1
    )

    # Check if axe is already loaded
    is_loaded = client.execute(
        "(function() { return typeof axe !== 'undefined'; })()",
        timeout=5.0
    )

    if not is_loaded.get("result"):
        # Inject axe-core library
        axe_wrapped = f"(function() {{ {axe_lib} return typeof axe !== 'undefined'; }})()"
        result = client.execute(axe_wrapped, timeout=15.0)
        if not result.get("ok") or not result.get("result"):
            return {"error": "Failed to load axe-core"}

    # Run scoped audit
    result = client.execute(audit_script, timeout=30.0)
    if not result.get("ok"):
        return {"error": result.get("error")}

    data = result.get("result", {})
    if not data.get("ok"):
        return {"error": data.get("error")}

    return {
        "violations": data.get("violations", []),
        "passes": data.get("passes", []),
        "incomplete": data.get("incomplete", []),
        "url": data.get("url", ""),
    }


def _run_scoped_ibm(client, scripts_dir: Path, vendor_dir: Path) -> dict | None:
    """Run IBM Equal Access scoped to the inspected element."""
    import json

    ace_lib_path = vendor_dir / "ace.min.js"
    script_path = scripts_dir / "run_ibm.js"

    if not ace_lib_path.exists() or not script_path.exists():
        return {"error": "IBM Equal Access not found"}

    # Load scripts
    with open(ace_lib_path) as f:
        ace_lib = f.read()
    with open(script_path) as f:
        audit_script = f.read()

    # Build config with scoped context flag
    config = {
        "policies": ["WCAG_2_1"],
        "failLevels": ["violation", "potentialviolation"],
        "reportLevels": ["violation", "potentialviolation", "recommendation"],
        "__showBadges": False,
        "__context": "inspected",  # KEY: Tell script to use inspected element
    }

    # Replace config placeholder
    audit_script = audit_script.replace("__IBM_CONFIG__", json.dumps(config))

    # Check if ace is already loaded
    is_loaded = client.execute(
        "(function() { return typeof window.ace !== 'undefined'; })()",
        timeout=5.0
    )

    if not is_loaded.get("result"):
        # Inject ace library
        ace_wrapped = f"(function() {{ {ace_lib}; window.ace = ace; return typeof window.ace !== 'undefined'; }})()"
        result = client.execute(ace_wrapped, timeout=15.0)
        if not result.get("ok") or not result.get("result"):
            return {"error": "Failed to load IBM Equal Access"}

    # Run scoped audit
    result = client.execute(audit_script, timeout=30.0)
    if not result.get("ok"):
        return {"error": result.get("error")}

    data = result.get("result", {})
    if not data.get("ok"):
        return {"error": data.get("error")}

    audit_result = data.get("result", {})
    return {
        "issues": audit_result.get("issues", []),
        "summary": audit_result.get("summary", {}),
        "url": audit_result.get("url", ""),
    }


def _run_scoped_htmlcs(client, scripts_dir: Path, vendor_dir: Path) -> dict | None:
    """Run HTML_CodeSniffer scoped to the inspected element."""
    import json

    htmlcs_lib_path = vendor_dir / "htmlcs.min.js"
    script_path = scripts_dir / "run_htmlcs.js"

    if not htmlcs_lib_path.exists() or not script_path.exists():
        return {"error": "HTML_CodeSniffer not found"}

    # Load scripts
    with open(htmlcs_lib_path) as f:
        htmlcs_lib = f.read()
    with open(script_path) as f:
        audit_script = f.read()

    # Build config
    config = {
        "standard": "WCAG2AA",
        "includeNotices": False,
        "includeWarnings": True,
        "__context": "inspected",  # Flag for scoping
    }

    # Replace config placeholder
    audit_script = audit_script.replace("__HTMLCS_CONFIG__", json.dumps(config))

    # KEY: Modify HTMLCS to run on inspected element instead of document
    # HTMLCS.process(standard, element, successCallback, errorCallback)
    # Replace the 'document' argument with the inspected element
    audit_script = audit_script.replace(
        "HTMLCS.process(standard, document,",
        "HTMLCS.process(standard, (config.__context === 'inspected' && window.__INSPEKT_INSPECTED_ELEMENT__) ? window.__INSPEKT_INSPECTED_ELEMENT__ : document,",
    )

    # Check if htmlcs is already loaded
    is_loaded = client.execute(
        "(function() { return typeof HTMLCS !== 'undefined'; })()",
        timeout=5.0
    )

    if not is_loaded.get("result"):
        # Inject htmlcs library
        htmlcs_wrapped = f"(function() {{ {htmlcs_lib}; return typeof HTMLCS !== 'undefined'; }})()"
        result = client.execute(htmlcs_wrapped, timeout=15.0)
        if not result.get("ok") or not result.get("result"):
            return {"error": "Failed to load HTML_CodeSniffer"}

    # Run scoped audit
    result = client.execute(audit_script, timeout=30.0)
    if not result.get("ok"):
        return {"error": result.get("error")}

    data = result.get("result", {})
    if not data.get("ok"):
        return {"error": data.get("error")}

    return {
        "messages": data.get("messages", []),
        "summary": data.get("summary", {}),
        "url": data.get("url", ""),
    }


def _consolidate_audit_results(raw_results: dict, engines_used: list) -> dict:
    """
    Consolidate results from all engines into a unified structure.

    Groups by status (violations/warnings/passes) with engine badges.
    """
    violations = []
    warnings = []
    passes = []

    # Process axe results
    if raw_results.get("axe"):
        axe = raw_results["axe"]
        for v in axe.get("violations", []):
            violations.append({
                "rule_id": v.get("id", "unknown"),
                "description": v.get("description", v.get("help", "")),
                "wcag": _extract_wcag_tags(v.get("tags", [])),
                "impact": v.get("impact", "moderate"),
                "engines": ["axe"],
                "instances": [
                    {
                        "engine": "axe",
                        "html": n.get("html", ""),
                        "message": n.get("failureSummary", ""),
                        "help_url": v.get("helpUrl", ""),
                    }
                    for n in v.get("nodes", [])[:3]  # Limit to 3 instances
                ]
            })
        for p in axe.get("passes", []):
            passes.append({
                "rule_id": p.get("id", "unknown"),
                "engines": ["axe"],
            })
        for i in axe.get("incomplete", []):
            warnings.append({
                "rule_id": i.get("id", "unknown"),
                "description": i.get("description", i.get("help", "")),
                "wcag": _extract_wcag_tags(i.get("tags", [])),
                "impact": i.get("impact", "moderate"),
                "engines": ["axe"],
                "instances": [
                    {
                        "engine": "axe",
                        "html": n.get("html", ""),
                        "message": n.get("message", "Needs manual review"),
                        "help_url": i.get("helpUrl", ""),
                    }
                    for n in i.get("nodes", [])[:3]
                ]
            })

    # Process IBM results
    if raw_results.get("ibm"):
        ibm = raw_results["ibm"]
        for issue in ibm.get("issues", []):
            level = str(issue.get("level", "violation")).lower()
            item = {
                "rule_id": issue.get("ruleId", "unknown"),
                "description": issue.get("message", ""),
                "wcag": [issue.get("reasonId", "")],
                "impact": _map_ibm_level_to_impact(level),
                "engines": ["ibm"],
                "instances": [{
                    "engine": "ibm",
                    "html": issue.get("snippet", ""),
                    "message": issue.get("message", ""),
                    "help_url": issue.get("help", ""),
                }]
            }
            if level == "violation":
                violations.append(item)
            elif level == "potentialviolation" or level == "recommendation":
                warnings.append(item)
            else:
                passes.append({"rule_id": item["rule_id"], "engines": ["ibm"]})

    # Process HTMLCS results
    if raw_results.get("hcs"):
        hcs = raw_results["hcs"]
        for msg in hcs.get("messages", []):
            msg_type = str(msg.get("type", "")).lower()
            item = {
                "rule_id": msg.get("code", "unknown"),
                "description": msg.get("msg", ""),
                "wcag": _extract_wcag_from_code(msg.get("code", "")),
                "impact": "serious" if msg_type == "error" else "moderate",
                "engines": ["hcs"],
                "instances": [{
                    "engine": "hcs",
                    "html": msg.get("element", ""),
                    "message": msg.get("msg", ""),
                    "help_url": "",
                }]
            }
            if msg_type == "error":
                violations.append(item)
            elif msg_type == "warning":
                warnings.append(item)
            # Skip notices for now

    return {
        "violations": violations,
        "warnings": warnings,
        "passes": passes,
        "summary": {
            "violations": len(violations),
            "warnings": len(warnings),
            "passes": len(passes),
            "engines_used": engines_used
        }
    }


def _extract_wcag_tags(tags: list) -> list:
    """Extract WCAG success criteria from axe tags."""
    wcag = []
    for tag in tags:
        if tag.startswith("wcag"):
            # Extract SC number like "wcag111" -> "1.1.1"
            sc = tag.replace("wcag", "")
            if len(sc) >= 3 and sc.isdigit():
                wcag.append(f"{sc[0]}.{sc[1]}.{sc[2:]}")
    return wcag


def _extract_wcag_from_code(code: str) -> list:
    """Extract WCAG SC from HTMLCS code like 'WCAG2AA.Principle1.Guideline1_3.1_3_1.H42'."""
    wcag = []
    parts = code.split(".")
    for part in parts:
        if part.startswith("Guideline"):
            # Extract from format like "Guideline1_3"
            nums = part.replace("Guideline", "").replace("_", ".")
            if nums:
                wcag.append(nums)
        elif "_" in part and part[0].isdigit():
            # Format like "1_3_1" -> "1.3.1"
            wcag.append(part.replace("_", "."))
    return wcag[:1] if wcag else []


def _map_ibm_level_to_impact(level: str) -> str:
    """Map IBM Equal Access levels to impact strings."""
    mapping = {
        "violation": "serious",
        "potentialviolation": "moderate",
        "recommendation": "minor",
        "manual": "moderate",
    }
    return mapping.get(str(level).lower(), "moderate")


async def _collect_rich_report_data(
    executor,
    script_loader,
    element_data: dict,
    screenshot: str,
    source: str,
    current_url: str,
    debug_data: dict | None = None,
) -> dict:
    """
    Collect additional data for rich HTML report generation.

    Returns dict with HTML, CSS tree, accessibility, page context, element tree,
    and optionally debug data (prompt, AI params, cURL command).
    """
    # 1. Get HTML content (already in element_data)
    html_original = element_data.get("htmlContent", "")

    # 2. Get CSS tree via get_computed_css.js
    css_tree = {}
    try:
        js_options = json.dumps({
            "allProperties": False,
            "includeDefaults": False,
            "roundPixels": True,
        })
        css_script = script_loader.load_with_substitution_sync(
            "get_computed_css.js",
            {"OPTIONS_PLACEHOLDER": js_options, "SOURCE_TYPE_PLACEHOLDER": source}
        )
        css_result = await asyncio.to_thread(executor.execute, css_script, 30.0)
        if css_result.get("ok"):
            css_response = css_result.get("result", {})
            if css_response.get("ok"):
                css_tree = css_response.get("root", {})
    except Exception as e:
        logger.warning(f"Failed to get CSS for rich report: {e}")

    # 3. Get page context
    context_script = """
    (function() {
        return {
            url: window.location.href,
            title: document.title,
            lang: document.documentElement.lang || '',
            viewport: {
                width: window.innerWidth,
                height: window.innerHeight
            }
        };
    })()
    """
    page_context = {}
    try:
        context_result = await asyncio.to_thread(executor.execute, context_script, 5.0)
        if context_result.get("ok"):
            page_context = context_result.get("result", {})
    except Exception as e:
        logger.warning(f"Failed to get page context for rich report: {e}")
        page_context = {"url": current_url}

    # 4. Build element tree (parent chain) from xpath
    element_tree = []
    xpath = element_data.get("xpath", "")
    if xpath:
        # Parse xpath like /html/body/div[2]/main/section/article/figure/img
        parts = xpath.strip("/").split("/")
        for part in parts[:-1]:  # Exclude the element itself
            # Extract tag name (remove index like [2])
            tag = part.split("[")[0] if "[" in part else part
            element_tree.append({"tag": tag, "id": "", "classes": []})

    # 5. Accessibility data (already in element_data)
    accessibility = element_data.get("accessibility", {})

    # 6. Run accessibility audits (scoped to the inspected element)
    audit_results = None
    try:
        audit_results = await asyncio.to_thread(
            _run_scoped_audits, executor.client, source
        )
    except Exception as e:
        logger.warning(f"Failed to run accessibility audits: {e}")
        audit_results = {
            "violations": [],
            "warnings": [],
            "passes": [],
            "summary": {
                "violations": 0,
                "warnings": 0,
                "passes": 0,
                "engines_used": [],
                "error": str(e)
            }
        }

    # 7. Optimize screenshot for report (PNG + oxipng)
    optimized_screenshot = _optimize_screenshot_for_report(screenshot)

    result = {
        "html_original": html_original,
        "css_tree": css_tree,
        "screenshot": optimized_screenshot,
        "accessibility": accessibility,
        "page_context": page_context,
        "element_tree": element_tree,
        "audit_results": audit_results,
    }

    # 8. Include debug data if provided
    if debug_data:
        result["debug_data"] = debug_data

    return result


async def element_ask(params: ElementAskParams) -> ElementAskResponse:
    """
    Ask a question about a specific element using AI.

    Uses vision AI to analyze a screenshot of the element along with its
    metadata to answer questions about accessibility, design, or functionality.

    Supports caching: if the same question is asked about the same element
    (identified by tag, id, accessible name, and text content hash),
    the cached response is returned.

    When rich_output=True, also collects HTML, CSS, and context data for
    generating a rich HTML report.
    """
    import click
    from inspekt.services.content_cache import ContentCache

    def debug_print(msg: str) -> None:
        if params.debug:
            click.secho(f"[DEBUG] {msg}", fg="cyan", err=True)

    executor = get_executor()
    script_loader = get_script_loader()
    content_cache = ContentCache()

    try:
        # Pre-check: Quick validation with short timeout (fail fast on stale state)
        debug_print("Pre-check: Validating element exists (3s timeout)")
        precheck = _precheck_element_sync(executor, params.source)

        if not precheck.get("ok"):
            error = precheck.get("error", "Unknown error")
            hint = precheck.get("hint", "")
            debug_print(f"Pre-check failed: {error}")
            return ElementAskResponse(
                answer=f"Error: {error}" + (f" ({hint})" if hint else ""),
                element_type="unknown",
                source=params.source,
            )

        debug_print(f"Pre-check passed: element <{precheck.get('tag', '?')}> exists")

        # Step 0: Get current URL for cache key
        url_code = "(function() { return window.location.href; })()"
        url_result = await asyncio.to_thread(executor.execute, url_code, 5.0)
        current_url = url_result.get("result", "") if url_result.get("ok") else ""
        debug_print(f"Step 0: Got URL for cache: {current_url[:50]}…")

        # Step 1: Get element data
        debug_print(f"Step 1: Getting element data for source='{params.source}'")
        element_data = await _get_element_data(executor, script_loader, params.source)

        if element_data.get("error"):
            debug_print(f"Error getting element data: {element_data.get('error')}")
            return ElementAskResponse(
                answer=f"Error: {element_data['error']}" + (f" ({element_data.get('hint', '')})" if element_data.get('hint') else ""),
                element_type="unknown",
                source=params.source,
            )

        debug_print(f"Element data: tag=<{element_data.get('tag')}>, id={element_data.get('id')}, classes={element_data.get('classes')}")

        # Step 1.5: Check cache (unless debug mode is on)
        if not params.debug and current_url and content_cache.is_enabled("element_ask"):
            fingerprint = content_cache.create_element_ask_fingerprint(element_data, params.question)
            cache_key = content_cache.get_element_cache_key(element_data, params.question)
            debug_print(f"Step 1.5: Checking cache with key={cache_key[:16]}…")

            cached = content_cache.get_cached_content(
                url=current_url,
                command="element_ask",
                current_fingerprint=fingerprint,
                language=cache_key,  # Use element+question hash as language field
            )

            if cached:
                age_seconds = cached.get("age_seconds", 0)
                if age_seconds < 60:
                    age_str = f"{age_seconds}s"
                elif age_seconds < 3600:
                    age_str = f"{age_seconds // 60}m"
                else:
                    age_str = f"{age_seconds // 3600}h"

                debug_print(f"Cache hit! Age: {age_str}, similarity: {cached.get('similarity', 1.0):.2f}")

                return ElementAskResponse(
                    answer=cached["output"],
                    element_type=element_data.get("tag", "unknown"),
                    source=params.source,
                    cached=True,
                )

        # Step 2: Take screenshot
        debug_print("Step 2: Taking element screenshot")
        screenshot = await _take_element_screenshot(executor, script_loader, params.source)

        if not screenshot:
            debug_print("Screenshot failed - element may be hidden or off-screen")
            return ElementAskResponse(
                answer="Failed to capture element screenshot. The element may be hidden or off-screen.",
                element_type=element_data.get("tag", "unknown"),
                source=params.source,
            )

        debug_print(f"Screenshot captured: {len(screenshot)} chars ({len(screenshot) * 3 // 4 // 1024} KB approx)")

        # Step 3: Optimize screenshot for AI (resize and convert to JPEG)
        debug_print("Step 3: Optimizing screenshot (resize to 1024px max, JPEG 80%)")
        optimized_screenshot = _optimize_screenshot_for_ai(screenshot, max_size=1024, quality=80)
        reduction = (1 - len(optimized_screenshot) / len(screenshot)) * 100
        debug_print(f"Optimized: {len(screenshot)} → {len(optimized_screenshot)} chars ({reduction:.1f}% reduction)")

        # Step 4: Load prompt and format with element context and question
        debug_print("Step 4: Loading prompt and formatting context")
        ai_service = get_ai_service()
        base_prompt = ai_service.load_prompt("element-ask.prompt")
        context = _format_element_context(element_data)

        # Comprehensive mode: collect additional diagnostics for the prompt
        audit_results = None
        event_handlers = None
        accessibility_tree = None

        if params.comprehensive:
            debug_print("Step 4a: Comprehensive mode - collecting extended diagnostics")

            # Get accessibility audit results
            try:
                debug_print("  - Running scoped accessibility audits (axe, IBM, HCS)")
                audit_results = await asyncio.to_thread(
                    _run_scoped_audits, executor.client, params.source
                )
                debug_print(f"  - Audit complete: {audit_results.get('summary', {}).get('violations', 0)} violations")
            except Exception as e:
                debug_print(f"  - Audit failed: {e}")
                audit_results = None

            # Get event handlers (inline + CDP)
            try:
                debug_print("  - Extracting event handlers")
                inline_handlers = await _get_event_handlers(executor, script_loader, params.source)
                cdp_listeners = _get_cdp_event_listeners(executor, script_loader, params.source)
                event_handlers = _merge_event_handlers(inline_handlers, cdp_listeners)
                debug_print(f"  - Found {event_handlers.get('totalCount', 0)} handlers (CDP: {event_handlers.get('cdpAvailable', False)})")
            except Exception as e:
                debug_print(f"  - Event handlers failed: {e}")
                event_handlers = None

            # Get accessibility tree
            try:
                debug_print("  - Getting accessibility tree via CDP")
                accessibility_tree = _get_accessibility_tree(executor, script_loader, params.source, depth=10)
                if accessibility_tree:
                    debug_print(f"  - A11y tree: {accessibility_tree.get('count', 0)} nodes")
                else:
                    debug_print("  - A11y tree unavailable (CDP may require DevTools)")
            except Exception as e:
                debug_print(f"  - A11y tree failed: {e}")
                accessibility_tree = None

            # Build comprehensive prompt
            full_prompt = _format_comprehensive_prompt(
                base_prompt=base_prompt,
                element_context=context,
                audit_results=audit_results,
                event_handlers=event_handlers,
                accessibility_tree=accessibility_tree,
                question=params.question,
                language=params.language,
            )
        else:
            # Standard prompt (no comprehensive diagnostics)
            full_prompt = f"{base_prompt}\n\n--- ELEMENT METADATA ---\n{context}\n\n--- USER QUESTION ---\n{params.question}"

            # Add language instruction if specified
            if params.language:
                full_prompt += f"\n\nProvide your response in {params.language}."
                debug_print(f"Added language instruction: {params.language}")

        debug_print(f"Prompt length: {len(full_prompt)} chars, Question: '{params.question}'")
        if params.debug:
            click.secho("\n--- FULL PROMPT ---", fg="cyan", err=True)
            click.echo(full_prompt, err=True)
            click.secho("--- END PROMPT ---\n", fg="cyan", err=True)

        # Step 5: Call vision AI
        manager = ai_service.get_provider_manager()
        provider, _ = manager.resolve_provider(None, "element_ask")
        vision_model = provider.get_default_vision_model()
        debug_print(f"Step 5: Calling vision AI (provider={provider.name}, model={vision_model})")

        answer = ai_service.call_ai_vision(
            prompt=full_prompt,
            image_data_url=optimized_screenshot,
            command="element_ask",
        )

        debug_print(f"AI response received: {len(answer)} chars")

        # Step 6: Store in cache (if caching is enabled and we have a URL)
        if current_url and content_cache.is_enabled("element_ask") and not params.debug:
            fingerprint = content_cache.create_element_ask_fingerprint(element_data, params.question)
            cache_key = content_cache.get_element_cache_key(element_data, params.question)
            content_cache.store_content(
                url=current_url,
                command="element_ask",
                fingerprint=fingerprint,
                output=answer,
                language=cache_key,
            )
            debug_print("Step 6: Stored response in cache")

        # Step 7: Collect rich report data if requested
        rich_data = None
        if params.rich_output:
            debug_print("Step 7: Collecting rich report data (HTML, CSS, context)")

            # Build debug data if debug mode is enabled
            debug_data = None
            if params.debug:
                debug_data = _build_debug_data(
                    prompt=full_prompt,
                    provider_name=provider.name,
                    model=vision_model,
                    image_size_kb=len(optimized_screenshot) * 3 // 4 // 1024,
                    question=params.question,
                )

            rich_data = await _collect_rich_report_data(
                executor,
                script_loader,
                element_data,
                screenshot,  # Use original screenshot (not optimized) for better quality in report
                params.source,
                current_url,
                debug_data=debug_data,
            )
            debug_print(f"Rich data collected: HTML={len(rich_data.get('html_original', ''))} chars, CSS tree present={bool(rich_data.get('css_tree'))}")

        return ElementAskResponse(
            answer=answer,
            element_type=element_data.get("tag", "unknown"),
            source=params.source,
            cached=False,
            rich_data=rich_data,
        )

    except Exception as e:
        logger.error(f"Element ask error: {e}")
        return ElementAskResponse(
            answer=f"Error: {str(e)}",
            element_type="unknown",
            source=params.source,
        )
