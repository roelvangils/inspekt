"""
Content extraction and AI-powered analysis commands.

This module provides commands for extracting and analyzing page content:
- describe: AI-powered page description for screen reader users
- do: AI-powered action matching for natural language navigation
- outline: Display heading structure as nested outline
- links: Extract and display links with optional enrichment
- summarize: AI-powered article summary

These commands use external AI tools (mods) and helper scripts for
content extraction.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import click

from inspekt.app.cli.base import builtin_open, get_ai_language
from inspekt.app.cli.icons import analyze as analyze_icon
from inspekt.app.cli.icons import cached as cached_icon
from inspekt.app.cli.icons import error, get_indicator, success
from inspekt.app.cli.icons import generate as generate_icon
from inspekt.app.cli.interaction import _focus_browser_if_requested, _send_text
from inspekt.app.cli.table import print_wrapped
from inspekt.app.cli.url_builder import url_scheme
from inspekt.client import BridgeClient
from inspekt.config import get_do_config
from inspekt.services.action_cache import ActionCache
from inspekt.services.action_matcher import ActionMatcher
from inspekt.services.ai_integration import get_ai_service
from inspekt.services.content_cache import ContentCache
from inspekt.services.formatting_utils import format_filesize


def _speak_text(text: str, voice_name: str, audio_output: str | None = None, force_refresh: bool = False) -> None:
    """
    Speak text using TTS service, with caching and support for long content.

    Audio is cached based on text content similarity (90% threshold). If similar
    text was spoken before, the cached audio is played instead of calling the API.

    Args:
        text: The text to speak.
        voice_name: Name of the voice to use, or empty string for default voice.
        audio_output: Optional path to save audio as MP3 file instead of playing.
        force_refresh: If True, bypass cache and regenerate audio.
    """
    import os

    from inspekt.app.cli.icons import get_icon
    from inspekt.config import get_tts_config
    from inspekt.services.text_splitter import (
        ELEVENLABS_CHAR_LIMIT,
        chunk_text_for_tts,
        get_text_stats,
        truncate_at_sentence_boundary,
    )
    from inspekt.services.tts_cache import TTSCache
    from inspekt.services.tts_service import (
        TTSError,
        generate_audio,
        is_tts_available,
        play_audio_bytes,
    )

    # Check if TTS is available
    available, error_msg = is_tts_available()
    if not available:
        click.echo()
        click.echo(click.style(f"TTS unavailable: {error_msg}", fg="yellow"), err=True)
        return

    # Use default voice if none specified or "default" sentinel
    if not voice_name or voice_name == "default":
        tts_config = get_tts_config()
        voice_name = tts_config.get("default-voice", "margot")

    # Check if we're being called from URL handler (needs detached mode)
    # Detached mode buffers audio to temp file so playback survives process termination
    detached = os.environ.get("INSPEKT_TTS_DETACHED") == "1"

    speak_icon = get_icon("speak") or "\U0001F50A"  # Speaker icon
    cached_icon = get_icon("cached") or "⚡"

    # Initialize TTS cache
    tts_cache = TTSCache()

    # Check if content exceeds ElevenLabs limit
    if len(text) > ELEVENLABS_CHAR_LIMIT:
        stats = get_text_stats(text)
        chunk_count = stats["chunks_needed"]

        click.echo()
        click.secho(f"Content is {len(text):,} characters", fg="yellow", err=True)
        click.echo(f"ElevenLabs has a {ELEVENLABS_CHAR_LIMIT:,} character limit per request.", err=True)
        click.echo(err=True)
        click.echo("Options:", err=True)
        click.echo("  1. Truncate at sentence boundary (one API request)", err=True)
        click.echo(f"  2. Split into {chunk_count} chunks (multiple requests, play sequentially)", err=True)
        click.echo("  3. Cancel", err=True)
        click.echo(err=True)

        choice = click.prompt(
            "Choose",
            type=click.Choice(["1", "2", "3"]),
            default="2",
            err=True,
        )

        if choice == "1":
            # Truncate at sentence boundary
            text = truncate_at_sentence_boundary(text)
            click.echo(f"Truncated to {len(text):,} characters", err=True)
        elif choice == "2":
            # Split into chunks and process (caching handled per-chunk)
            chunks = chunk_text_for_tts(text)
            _process_tts_chunks(chunks, voice_name, audio_output, detached, force_refresh)
            return
        else:
            # Cancel
            click.echo("Cancelled.", err=True)
            return

    # Check cache first (unless force_refresh or saving to file)
    if not force_refresh and not audio_output:
        cached = tts_cache.get_cached_audio(text, voice_name)
        if cached:
            click.echo()
            similarity_pct = int(cached["similarity"] * 100)
            if cached.get("exact_match"):
                click.echo(f"{cached_icon} {speak_icon} Playing cached audio (voice: {voice_name})…", err=True)
            else:
                click.echo(f"{cached_icon} {speak_icon} Playing cached audio ({similarity_pct}% match, voice: {voice_name})…", err=True)

            try:
                play_audio_bytes(cached["audio_bytes"])
                return
            except TTSError as e:
                # Cache playback failed, fall through to regenerate
                click.echo(click.style(f"Cache playback failed: {e}", fg="yellow"), err=True)

    # Single request path (short content or truncated)
    if audio_output:
        # Save to file
        click.echo()
        click.echo(f"{speak_icon} Generating audio…", err=True)
        try:
            audio_bytes = generate_audio(text, voice_name=voice_name)
            output_path = Path(audio_output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(audio_bytes)
            click.echo(success(f"Saved: {output_path}"), err=True)
            # Also cache the audio
            tts_cache.store_audio(text, voice_name, audio_bytes)
        except TTSError as e:
            click.echo(click.style(f"TTS error: {e}", fg="red"), err=True)
    else:
        # Generate and play audio
        click.echo()
        if detached:
            click.echo(f"{speak_icon} Preparing audio…", err=True)
        else:
            click.echo(f"{speak_icon} Speaking with voice '{voice_name}'…", err=True)

        try:
            # Generate audio first so we can cache it
            audio_bytes = generate_audio(text, voice_name=voice_name)

            # Cache the generated audio
            tts_cache.store_audio(text, voice_name, audio_bytes)

            # Play the audio
            play_audio_bytes(audio_bytes)
        except TTSError as e:
            click.echo(click.style(f"TTS error: {e}", fg="red"), err=True)


def _process_tts_chunks(
    chunks: list[str],
    voice_name: str,
    audio_output: str | None,
    detached: bool,
    force_refresh: bool = False,
) -> None:
    """
    Process multiple TTS chunks with prefetching and caching.

    For playback mode: Uses hybrid approach:
    - Chunk 1: Progressive streaming (speak_text) for immediate playback
    - Chunks 2+: Prefetched in background while previous chunk plays

    For file output: Uses generate_audio() to buffer audio bytes, then saves.

    Each chunk is cached individually for future reuse.

    Args:
        chunks: List of text chunks to convert to speech.
        voice_name: Name of the voice to use.
        audio_output: Optional path to save combined audio.
        detached: Whether to use detached playback mode.
        force_refresh: If True, bypass cache and regenerate audio.
    """
    from concurrent.futures import Future, ThreadPoolExecutor

    from inspekt.app.cli.icons import get_icon
    from inspekt.services.tts_cache import TTSCache
    from inspekt.services.tts_service import TTSError, generate_audio, play_audio_bytes, speak_text

    speak_icon = get_icon("speak") or "\U0001F50A"
    cached_icon = get_icon("cached") or "⚡"
    all_audio_bytes: list[bytes] = []
    tts_cache = TTSCache()

    click.echo()
    click.echo(f"{speak_icon} Processing {len(chunks)} chunks…", err=True)

    if audio_output:
        # SAVING TO FILE: Buffer all audio (no prefetch needed, just generate sequentially)
        for i, chunk in enumerate(chunks, 1):
            click.echo(f"  Chunk {i}/{len(chunks)} ({len(chunk):,} chars)…", err=True, nl=False)
            try:
                audio_bytes = generate_audio(chunk, voice_name=voice_name)
                click.secho(" ✓", fg="green", err=True)
                all_audio_bytes.append(audio_bytes)
            except TTSError as e:
                click.secho(f" ✗ {e}", fg="red", err=True)

        # Save combined audio
        if all_audio_bytes:
            output_path = Path(audio_output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            combined = b''.join(all_audio_bytes)
            output_path.write_bytes(combined)
            click.echo(success(f"Saved: {output_path}"), err=True)
        return

    # PLAYBACK MODE: Hybrid prefetch approach
    # - Chunk 1: Progressive streaming for immediate playback
    # - Chunks 2+: Prefetched while previous chunk plays
    with ThreadPoolExecutor(max_workers=1) as executor:
        prefetch_future: Future | None = None

        for i, chunk in enumerate(chunks, 1):
            is_first_chunk = (i == 1)
            is_last_chunk = (i == len(chunks))
            next_chunk = chunks[i] if not is_last_chunk else None

            click.echo(f"  Chunk {i}/{len(chunks)} ({len(chunk):,} chars)", err=True)

            if is_first_chunk:
                # First chunk: Use speak_text() for progressive streaming
                # Start prefetching chunk 2 when audio begins playing
                def start_prefetch():
                    nonlocal prefetch_future
                    if next_chunk:
                        prefetch_future = executor.submit(generate_audio, next_chunk, voice_name)

                try:
                    speak_text(
                        chunk,
                        voice_name=voice_name,
                        detached=detached,
                        on_start=start_prefetch,
                        on_error=lambda msg: click.echo(click.style(f"    TTS error: {msg}", fg="red"), err=True),
                    )
                except TTSError as e:
                    click.secho(f"    ✗ {e}", fg="red", err=True)
            else:
                # Subsequent chunks: Use prefetched audio
                try:
                    # Get prefetched audio (should be ready or nearly ready)
                    if prefetch_future:
                        audio_bytes = prefetch_future.result()  # Blocks if not ready yet
                        prefetch_future = None

                        # Start prefetching next chunk before playing current
                        if next_chunk:
                            prefetch_future = executor.submit(generate_audio, next_chunk, voice_name)

                        # Play the prefetched audio
                        play_audio_bytes(audio_bytes)
                    else:
                        # Fallback: no prefetch available, generate and play
                        audio_bytes = generate_audio(chunk, voice_name=voice_name)
                        play_audio_bytes(audio_bytes)

                except TTSError as e:
                    click.secho(f"    ✗ {e}", fg="red", err=True)


def _parse_page_structure(markdown_structure: str) -> dict:
    """Parse markdown page structure to extract data for fingerprinting."""
    data = {}

    # Extract title
    title_match = re.search(r"\*\*Title:\*\* (.+)", markdown_structure)
    data["title"] = title_match.group(1) if title_match else ""

    # Extract headings
    headings = []
    for match in re.finditer(r"^(#{1,6})\s+(.+)$", markdown_structure, re.MULTILINE):
        level = len(match.group(1))
        text = match.group(2).strip()
        headings.append({"level": level, "text": text})
    data["headings"] = headings

    # Extract landmarks (look for sections like ### Landmarks)
    landmarks = []
    landmarks_section = re.search(r"###\s+Landmarks\s*\n(.+?)(?:\n#{1,3}\s|$)", markdown_structure, re.DOTALL)
    if landmarks_section:
        for line in landmarks_section.group(1).split("\n"):
            if line.strip().startswith("-"):
                # Extract landmark role (e.g., "- navigation")
                role = line.strip().lstrip("- ").split()[0].lower()
                landmarks.append({"role": role})
    data["landmarks"] = landmarks

    # Extract counts
    link_match = re.search(r"(\d+)\s+links?", markdown_structure)
    data["linkCount"] = int(link_match.group(1)) if link_match else 0

    button_match = re.search(r"(\d+)\s+buttons?", markdown_structure)
    data["buttonCount"] = int(button_match.group(1)) if button_match else 0

    image_match = re.search(r"(\d+)\s+images?", markdown_structure)
    data["imageCount"] = int(image_match.group(1)) if image_match else 0

    # Extract main text excerpt (first paragraph or content)
    text_match = re.search(r"###\s+Main Content\s*\n(.+?)(?:\n#{1,3}\s|$)", markdown_structure, re.DOTALL)
    if text_match:
        data["mainText"] = text_match.group(1).strip()[:200]
    else:
        data["mainText"] = ""

    return data


@click.command()
@url_scheme(
    "describe",
    param_map={"output_json": "json"},
    defaults={"format": "summary", "language": None},
    exclude_params=["debug", "force_refresh", "output_json"],
)
@click.option(
    "--language", "--lang", type=str, default=None, help="Language for AI output (overrides config)"
)
@click.option("--debug", is_flag=True, help="Show the full prompt instead of calling AI")
@click.option("--force-refresh", is_flag=True, help="Force refresh, bypass cache")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON with metadata")
def describe(language, debug, force_refresh, output_json):
    """
    Generate an AI-powered description of the page for screen reader users.

    Extracts page structure (landmarks, headings, links, images, forms) and
    uses AI to create a concise, natural description perfect for blind users
    to understand what the page offers at a glance.

    Examples:
        inspekt describe
        inspekt describe --json
    """
    import time

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Load and execute the extraction script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "extract_page_structure.js"

    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        with builtin_open(script_path) as f:
            script = f.read()

        if not output_json:
            click.echo(analyze_icon("Analyzing page structure…"), err=True)
        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        # The script now returns a markdown-formatted string
        page_structure = result.get("result", "")

        if not page_structure or not isinstance(page_structure, str):
            click.echo("Error: No page structure extracted", err=True)
            sys.exit(1)

        # Extract page language from the structure for language detection
        # Look for "**Language:** xx" pattern
        page_lang = None
        lang_match = re.search(r"\*\*Language:\*\* (\w+)", page_structure)
        if lang_match:
            page_lang = lang_match.group(1)

        # Determine target language for AI
        target_lang = get_ai_language(language_override=language, page_lang=page_lang)

        # Extract URL and title for metadata
        url_match = re.search(r"\*\*URL:\*\* (.+)", page_structure)
        current_url = url_match.group(1) if url_match else ""

        title_match = re.search(r"\*\*Title:\*\* (.+)", page_structure)
        page_title = title_match.group(1) if title_match else ""

        # Parse page structure for fingerprinting
        page_data = _parse_page_structure(page_structure)

        # Try cache first (unless force refresh or debug mode)
        content_cache = ContentCache()
        cached_result = None
        from_cache = False
        cache_timestamp = None
        cache_similarity = None

        if not force_refresh and not debug and content_cache.is_enabled("describe"):
            fingerprint = content_cache.create_describe_fingerprint(page_data)
            cached_result = content_cache.get_cached_content(current_url, "describe", fingerprint, target_lang or "auto")

            if cached_result:
                from_cache = True
                cache_similarity = cached_result["similarity"]
                age_seconds = cached_result["age_seconds"]
                cache_timestamp = time.time() - age_seconds

                if output_json:
                    # Get AI service for model info
                    ai_service = get_ai_service()
                    model_info = ai_service.get_model_info()

                    json_output = {
                        "description": cached_result["output"],
                        "url": current_url,
                        "title": page_title,
                        "language": target_lang or page_lang,
                        "from_cache": True,
                        "cache": {
                            "similarity": cache_similarity,
                            "cached_at": cache_timestamp,
                            "age_seconds": age_seconds,
                        },
                        "ai": model_info,
                    }
                    from inspekt.app.cli.table import print_json
                    print_json(json_output, summary="page description (cached)")
                    return

                # Format age for display
                if age_seconds < 3600:
                    age_str = f"{age_seconds // 60} minutes ago"
                elif age_seconds < 86400:
                    age_str = f"{age_seconds // 3600} hours ago"
                else:
                    age_str = f"{age_seconds // 86400} days ago"

                click.echo(cached_icon(f"Using cached description (similarity: {cache_similarity:.0%}, cached {age_str})"), err=True)
                click.echo()
                print_wrapped(cached_result["output"], fg="white", bold=False)
                return

        # Use AI service for description generation
        ai_service = get_ai_service()

        if not output_json:
            click.echo(generate_icon("Generating description…"), err=True)

        output = ai_service.generate_description(
            page_structure=page_structure,
            language_override=language,
            debug=debug
        )

        # If debug mode, generate_description returns None after showing prompt
        if debug:
            return

        # Store in cache for future use
        generation_timestamp = time.time()
        if content_cache.is_enabled("describe") and current_url:
            fingerprint = content_cache.create_describe_fingerprint(page_data)
            content_cache.store_content(current_url, "describe", fingerprint, output, target_lang or "auto")
            if not output_json:
                click.echo(success("Description cached for future use"), err=True)

        if output_json:
            model_info = ai_service.get_model_info()
            json_output = {
                "description": output,
                "url": current_url,
                "title": page_title,
                "language": target_lang or page_lang,
                "from_cache": False,
                "generated_at": generation_timestamp,
                "ai": model_info,
            }
            from inspekt.app.cli.table import print_json
            print_json(json_output, summary="page description")
        else:
            click.echo()
            print_wrapped(output, fg="white", bold=False)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _parse_compound_instruction(instruction: str) -> tuple[str, str | None]:
    """
    Parse a compound instruction into (action, payload).

    Examples:
        "search for cats"    → ("search", "cats")
        "select English"     → ("select", "English")
        "check remember me"  → ("check", "remember me")
        "login"              → ("login", None)
        "type hello world"   → ("type", "hello world")
    """
    instruction = instruction.strip()
    lower = instruction.lower()

    # Patterns: "verb + preposition + payload" or "verb + payload"
    compound_patterns = [
        # "search for X", "look for X", "find X"
        (r"^(?:search|look|find)\s+(?:for\s+)?(.+)$", "search"),
        # "type X", "enter X", "write X", "input X"
        (r"^(?:type|enter|write|input)\s+(.+)$", "type"),
        # "select X", "choose X", "pick X"
        (r"^(?:select|choose|pick)\s+(.+)$", "select"),
        # "check X", "enable X", "turn on X"
        (r"^(?:check|enable|tick)\s+(.+)$", "check"),
        # "uncheck X", "disable X", "turn off X"
        (r"^(?:uncheck|disable|untick)\s+(.+)$", "uncheck"),
    ]

    import re
    for pattern, action in compound_patterns:
        m = re.match(pattern, lower)
        if m:
            # Use original case for the payload
            payload_start = m.start(1)
            payload = instruction[payload_start:]
            return action, payload

    return instruction, None


def _execute_element_action(client: BridgeClient, action_id: str, element: dict,
                            instruction: str | None = None):
    """Helper function to execute an action on an element."""
    # Step 1: Get element info and highlight it
    inspect_script = f"""
(function() {{
    const element = document.querySelector('.{action_id}');
    if (!element) {{
        return {{ ok: false, error: 'Element not found' }};
    }}

    // Scroll element into view
    element.scrollIntoView({{ behavior: 'smooth', block: 'center' }});

    // Highlight briefly
    const originalOutline = element.style.outline;
    element.style.outline = '3px solid #00ff00';

    setTimeout(() => {{
        element.style.outline = originalOutline;
    }}, 500);

    const result = {{
        ok: true,
        element: {{
            tag: element.tagName.toLowerCase(),
            text: element.textContent.trim().substring(0, 100),
            href: element.href || null
        }},
        action: 'click'
    }};

    // Determine action type based on element
    if (element.href) {{
        // Parse URLs to get path
        try {{
            const currentUrl = new URL(window.location.href);
            const targetUrl = new URL(element.href);

            result.action = 'navigate';
            result.element.path = targetUrl.pathname + targetUrl.search + targetUrl.hash;
            result.element.isExternal = currentUrl.origin !== targetUrl.origin;
        }} catch (e) {{
            // If URL parsing fails, keep as click
        }}
    }}

    return result;
}})();
"""

    # Get element info first
    result = client.execute(inspect_script, timeout=10.0)

    if not result.get("ok"):
        click.echo(click.style(error(f"Failed to execute action: {result.get('error')}"), fg="red"), err=True)
        sys.exit(1)

    action_result = result.get("result", {})
    element_info = action_result.get("element", {})
    action_type = action_result.get("action", "click")

    # Parse compound instruction for smart form interaction
    parsed_action, payload = None, None
    if instruction:
        parsed_action, payload = _parse_compound_instruction(instruction)

    el_type = element.get("type", "")

    # Step 2: Smart execution based on element type and instruction
    if action_type == "navigate":
        # Navigate using window.location.href
        navigate_script = f"""
(function() {{
    const element = document.querySelector('.{action_id}');
    if (element && element.href) {{
        window.location.href = element.href;
    }}
    return {{ ok: true }};
}})();
"""
        client.execute(navigate_script, timeout=5.0)

        # Show navigation info
        click.echo(click.style(success("Action executed successfully!"), fg="green", bold=True))
        path = element_info.get("path", "")
        is_external = element_info.get("isExternal", False)

        if is_external:
            click.echo(f"  Navigated to: {element_info.get('href')}")
        else:
            click.echo(f"  Navigated to: {path}")

        if element_info.get('text'):
            click.echo(f"  Text: {element_info.get('text')}")

    elif el_type == "select" and payload:
        # Smart select: find matching option and select it
        escaped_payload = json.dumps(payload)
        select_script = f"""
(function() {{
    const el = document.querySelector('.{action_id}');
    if (!el || el.tagName !== 'SELECT') return {{ ok: false, error: 'Not a select element' }};
    const payload = {escaped_payload}.toLowerCase();
    let matched = null;
    for (const opt of el.options) {{
        if (opt.text.trim().toLowerCase().includes(payload) || opt.value.toLowerCase().includes(payload)) {{
            matched = opt;
            break;
        }}
    }}
    if (!matched) return {{ ok: false, error: 'No matching option found for: ' + payload }};
    el.value = matched.value;
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    return {{ ok: true, selected: matched.text.trim() }};
}})();
"""
        select_result = client.execute(select_script, timeout=5.0)
        select_data = select_result.get("result", {})
        if select_data.get("ok"):
            click.echo(click.style(success("Action executed successfully!"), fg="green", bold=True))
            click.echo(f"  Selected: {select_data.get('selected')}")
        else:
            click.echo(click.style(error(select_data.get("error", "Failed to select option")), fg="red"), err=True)

    elif el_type.startswith("input-") and el_type in ("input-checkbox", "input-radio") and parsed_action in ("check", "uncheck"):
        # Smart checkbox/radio: set to desired state
        want_checked = parsed_action == "check"
        current_checked = element.get("checked", False)
        if want_checked == current_checked:
            click.echo(click.style(success("Already in desired state"), fg="green", bold=True))
            click.echo(f"  {'Checked' if current_checked else 'Unchecked'}: {element.get('text', 'N/A')[:80]}")
        else:
            click_script = f"""
(function() {{
    const el = document.querySelector('.{action_id}');
    if (el) el.click();
    return {{ ok: true }};
}})();
"""
            client.execute(click_script, timeout=5.0)
            click.echo(click.style(success("Action executed successfully!"), fg="green", bold=True))
            click.echo(f"  {'Checked' if want_checked else 'Unchecked'}: {element.get('text', 'N/A')[:80]}")

    elif el_type.startswith("input-") and payload and parsed_action in ("search", "type"):
        # Smart input: focus and type the payload
        focus_script = f"""
(function() {{
    const el = document.querySelector('.{action_id}');
    if (!el) return {{ ok: false, error: 'Element not found' }};
    el.focus();
    el.value = '';
    return {{ ok: true }};
}})();
"""
        client.execute(focus_script, timeout=5.0)

        # Use _send_text to type the payload
        _send_text(payload, f".{action_id}", 0, clear=True)

        click.echo(click.style(success("Action executed successfully!"), fg="green", bold=True))
        click.echo(f"  Typed into <{element_info.get('tag')}>: {payload}")

        # If this was a search action, also press Enter
        if parsed_action == "search":
            import time
            time.sleep(0.3)
            press_script = """
(function() {
    const el = document.activeElement;
    if (el) {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        el.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
        // Also try submitting the parent form
        const form = el.closest('form');
        if (form) form.submit();
    }
    return { ok: true };
})();
"""
            client.execute(press_script, timeout=5.0)
            click.echo("  Submitted search")

    else:
        # Default: regular click for non-links
        click_script = f"""
(function() {{
    const element = document.querySelector('.{action_id}');
    if (element) {{
        element.click();
    }}
    return {{ ok: true }};
}})();
"""
        client.execute(click_script, timeout=5.0)

        # Show click info
        click.echo(click.style(success("Action executed successfully!"), fg="green", bold=True))
        click.echo(f"  Clicked: <{element_info.get('tag')}>")
        if element_info.get('text'):
            click.echo(f"  Text: {element_info.get('text')}")


def _execute_multi_step(client: BridgeClient, steps: list[dict], actionable_elements: list[dict]):
    """
    Execute a multi-step action plan returned by AI.

    Supported step actions: click, type, press, select.
    """
    import time

    total = len(steps)
    for i, step in enumerate(steps, 1):
        action = step.get("action")
        reasoning = step.get("reasoning", "")
        click.echo(f"  Step {i}/{total}: {reasoning}", err=True)

        if action == "click":
            action_id = step.get("actionId")
            if not action_id:
                click.echo(click.style("    Skipped: no actionId", fg="yellow"), err=True)
                continue
            click_script = f"""
(function() {{
    const el = document.querySelector('.{action_id}');
    if (!el) return {{ ok: false, error: 'Element not found' }};
    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    el.click();
    return {{ ok: true }};
}})();
"""
            result = client.execute(click_script, timeout=10.0)
            if not result.get("ok") or not result.get("result", {}).get("ok", True):
                err_msg = result.get("result", {}).get("error", result.get("error", "Unknown error"))
                click.echo(click.style(f"    Failed: {err_msg}", fg="red"), err=True)

        elif action == "type":
            text = step.get("text", "")
            if not text:
                click.echo(click.style("    Skipped: no text", fg="yellow"), err=True)
                continue
            escaped_text = json.dumps(text)
            type_script = f"""
(function() {{
    const el = document.activeElement;
    if (!el) return {{ ok: false, error: 'No focused element' }};
    el.value = {escaped_text};
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    return {{ ok: true }};
}})();
"""
            client.execute(type_script, timeout=5.0)

        elif action == "press":
            key = step.get("key", "Enter")
            press_script = f"""
(function() {{
    const el = document.activeElement || document.body;
    el.dispatchEvent(new KeyboardEvent('keydown', {{ key: '{key}', code: '{key}', bubbles: true }}));
    el.dispatchEvent(new KeyboardEvent('keyup', {{ key: '{key}', code: '{key}', bubbles: true }}));
    if ('{key}' === 'Enter') {{
        const form = el.closest('form');
        if (form) form.submit();
    }}
    return {{ ok: true }};
}})();
"""
            client.execute(press_script, timeout=5.0)

        elif action == "select":
            action_id = step.get("actionId")
            value = step.get("value", "")
            if not action_id or not value:
                click.echo(click.style("    Skipped: missing actionId or value", fg="yellow"), err=True)
                continue
            escaped_value = json.dumps(value)
            select_script = f"""
(function() {{
    const el = document.querySelector('.{action_id}');
    if (!el || el.tagName !== 'SELECT') return {{ ok: false, error: 'Not a select element' }};
    const target = {escaped_value}.toLowerCase();
    for (const opt of el.options) {{
        if (opt.text.trim().toLowerCase().includes(target)) {{
            el.value = opt.value;
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return {{ ok: true }};
        }}
    }}
    return {{ ok: false, error: 'No matching option' }};
}})();
"""
            client.execute(select_script, timeout=5.0)

        else:
            click.echo(click.style(f"    Unknown action: {action}", fg="yellow"), err=True)

        # Brief pause between steps for page responsiveness
        if i < total:
            time.sleep(0.3)

    click.echo(click.style(success(f"Completed {total} steps"), fg="green", bold=True))


def _partition_elements_by_viewport(actionable_elements: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Partition actionable elements into viewport-visible and off-viewport groups.

    Elements with `inViewport=True` are prioritized for matching since they're
    what the user can currently see.

    Args:
        actionable_elements: List of all actionable elements from the page

    Returns:
        Tuple of (viewport_elements, offscreen_elements)
    """
    viewport_elements = []
    offscreen_elements = []

    for el in actionable_elements:
        if el.get("inViewport", False):
            viewport_elements.append(el)
        else:
            offscreen_elements.append(el)

    # Sort viewport elements by overlap (more visible elements first)
    viewport_elements.sort(key=lambda x: x.get("viewportOverlap", 0), reverse=True)

    return viewport_elements, offscreen_elements


def _try_matching_strategies(
    matcher: ActionMatcher,
    cache: ActionCache,
    action_normalized: str,
    elements: list[dict],
    languages: list[str],
    current_url: str,
    page_data: dict,
    scope_label: str,
    verbose: bool = False,
    skip_cache: bool = False,
) -> tuple[dict | None, str | None, float]:
    """
    Try all non-AI matching strategies on a set of elements.

    This helper function runs through the waterfall matching strategies:
    1. Cache lookup (skipped if skip_cache=True)
    2. Literal text matching
    3. Common action patterns
    4. Substring matching
    5. Fuzzy matching
    6. Synonym matching

    Args:
        matcher: ActionMatcher instance
        cache: ActionCache instance
        action_normalized: Normalized action text
        elements: List of elements to search through
        languages: List of language codes for multilingual matching
        current_url: Current page URL for cache lookup
        page_data: Full page data for fingerprinting
        scope_label: Label for diagnostic logging (e.g., "viewport", "full page")
        verbose: Whether to show verbose diagnostic messages
        skip_cache: If True, skip cache lookup (for testing matchers)

    Returns:
        Tuple of (matched_element, match_method, match_score) or (None, None, 0.0)
    """
    matched_element = None
    match_method = None
    match_score = 0.0

    if not elements:
        if verbose:
            click.echo(f"  No elements in {scope_label} scope", err=True)
        return None, None, 0.0

    if verbose:
        click.echo(f"  Trying {len(elements)} elements in {scope_label}…", err=True)

    # 1. TRY CACHE (skip if --no-cache flag is set)
    if cache.is_enabled() and not matched_element and not skip_cache:
        fingerprint = cache.calculate_page_fingerprint(page_data)
        cached_action = cache.get_cached_action(current_url, action_normalized, fingerprint)

        if cached_action:
            # Try to find element using cached identifier
            cached_id = cached_action["identifier"]
            for el in elements:
                if (el.get("type") == cached_id.get("type") and
                    el.get("text") == cached_id.get("text") and
                    el.get("href") == cached_id.get("href")):
                    matched_element = el
                    match_method = "CACHED"
                    match_score = 1.0
                    click.echo(click.style(
                        cached_icon(f"Found cached match in {scope_label} (similarity: {cached_action['similarity']:.0%})"),
                        fg="cyan", bold=True
                    ), err=True)
                    break

    # 2. TRY LITERAL MATCHING
    if not matched_element:
        literal_match = matcher.find_literal_match(action_normalized, elements)
        if literal_match:
            matched_element = literal_match["element"]
            match_method = "LITERAL"
            match_score = literal_match["score"]
            click.echo(click.style(
                success(f"Found literal match in {scope_label} (score: {match_score:.0%})"),
                fg="cyan", bold=True
            ), err=True)

    # 3. TRY COMMON ACTIONS
    if not matched_element:
        common_match = matcher.find_common_action_match(action_normalized, elements, languages)
        if common_match:
            matched_element = common_match["element"]
            match_method = "COMMON"
            match_score = common_match["score"]
            click.echo(click.style(
                success(f"Found common action match in {scope_label} (score: {match_score:.0%})"),
                fg="cyan", bold=True
            ), err=True)

    # 4. TRY SUBSTRING MATCHING (e.g., "bewijs" matches "Bewijsstukken")
    if not matched_element:
        substring_match = matcher.find_substring_match(action_normalized, elements)
        if substring_match:
            matched_element = substring_match["element"]
            match_method = "SUBSTRING"
            match_score = substring_match["score"]
            match_type = substring_match.get("match_type", "substring")
            click.echo(click.style(
                success(f"Found substring match in {scope_label} (score: {match_score:.0%}, type: {match_type})"),
                fg="cyan", bold=True
            ), err=True)

    # 5. TRY FUZZY MATCHING
    if not matched_element:
        fuzzy_match = matcher.find_fuzzy_match(action_normalized, elements)
        if fuzzy_match:
            matched_element = fuzzy_match["element"]
            match_method = "FUZZY"
            match_score = fuzzy_match["score"]
            click.echo(click.style(
                success(f"Found fuzzy match in {scope_label} (score: {match_score:.0%})"),
                fg="cyan", bold=True
            ), err=True)

    # 6. TRY SYNONYM MATCHING
    if not matched_element:
        synonym_match = matcher.find_synonym_match(action_normalized, elements)
        if synonym_match:
            matched_element = synonym_match["element"]
            match_method = "SYNONYM"
            match_score = synonym_match["score"]
            click.echo(click.style(
                success(f"Found synonym match in {scope_label} (score: {match_score:.0%})"),
                fg="cyan", bold=True
            ), err=True)

    if verbose and not matched_element:
        click.echo(f"  No match found in {scope_label}", err=True)

    return matched_element, match_method, match_score


@click.command()
@url_scheme(
    "do",
    exclude_params=["debug", "no_execute", "force_ai", "no_cache", "focus", "verbose"],
)
@click.argument("instruction", type=str)
@click.option("--debug", is_flag=True, help="Show the full prompt instead of calling AI")
@click.option("--no-execute", is_flag=True, help="Show matches but don't execute any actions")
@click.option("--force-ai", is_flag=True, help="Force AI matching, bypass cache and literal matching")
@click.option("--no-cache", is_flag=True, help="Bypass cache lookup and don't cache results (useful for testing)")
@click.option("--focus", "-f", is_flag=True, default=False,
              help="Focus the browser window before executing action (macOS only)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed diagnostic logging")
def do(instruction, debug, no_execute, force_ai, no_cache, focus, verbose):
    """
    Find and execute actionable elements matching a natural language instruction.

    This command analyzes the page for clickable elements (links, buttons, forms)
    and uses AI to match them with your instruction. It adds temporary classes
    to actionable elements and returns a ranked list of matches with probability
    scores.

    If the top match has a probability >= 75%, it automatically executes the action.
    For lower confidence matches, it asks for confirmation before executing.

    The element is briefly highlighted in green before clicking, and you'll see
    confirmation of what was clicked.

    Examples:
        inspekt do "Go to the homepage"          # Auto-executes if high confidence
        inspekt do "Click the login button"      # Asks for confirmation if lower confidence
        inspekt do "Search for products"
        inspekt do "Submit form" --no-execute    # Just show matches, don't execute
        inspekt do "Login" --focus               # Focus browser before executing
        inspekt do "bewijs" --no-cache -v        # Test matchers without cache
    """
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Focus browser AFTER connection is verified (and domain is approved)
    # This ensures the focus doesn't happen before the domain permission prompt
    _focus_browser_if_requested(focus)

    # Load and execute the extraction script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "extract_actionable_elements.js"

    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        with builtin_open(script_path) as f:
            script = f.read()

        click.echo("Analyzing page for actionable elements…", err=True)
        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        # Get the extracted data
        page_data = result.get("result", {})

        if not page_data or not isinstance(page_data, dict):
            click.echo("Error: No page data extracted", err=True)
            sys.exit(1)

        actionable_elements = page_data.get("actionableElements", [])
        total_actions = page_data.get("totalActions", 0)

        if total_actions == 0:
            click.echo("No actionable elements found on this page.", err=True)
            sys.exit(0)

        # Check for active modal — try modal elements first, fall back to all
        active_modal = page_data.get("activeModal")
        all_elements = actionable_elements  # keep original list for fallback
        if active_modal:
            modal_type = active_modal.get("type", "modal")
            modal_count = active_modal.get("modalElementCount", 0)
            click.echo(click.style(
                f"Detected {modal_type} overlay — trying {modal_count} modal elements first",
                fg="yellow"
            ), err=True)
            actionable_elements = active_modal.get("modalElements", actionable_elements)
            total_actions = len(actionable_elements)
            page_data["actionableElements"] = actionable_elements
            page_data["totalActions"] = total_actions

        # Display element counts including viewport info
        viewport_count = page_data.get("viewportActionsCount", 0)
        click.echo(f"Found {total_actions} actionable elements (prioritizing {viewport_count} in viewport)", err=True)

        # Initialize cache and matcher with config
        cache = ActionCache()

        # Load do command config and convert to matcher config format
        do_config = get_do_config()
        matcher_config = {
            "synonyms_file": do_config.get("synonyms-file"),
            "literal_match_threshold": do_config.get("literal-match-threshold", 0.8),
            "substring_match_threshold": do_config.get("substring-match-threshold", 0.5),
            "use_fuzzy_matching": do_config.get("use-fuzzy-matching", True),
            "max_fuzzy_distance": do_config.get("max-fuzzy-distance", 2),
        }
        matcher = ActionMatcher(matcher_config)

        # Get current URL and detect page language
        current_url = page_data.get("pageUrl", "")
        page_lang = page_data.get("language", "en")

        # Determine languages to use for matching (prioritize page language)
        if page_lang and page_lang != "unknown":
            # Use page language + English as fallback
            languages = [page_lang, "en"] if page_lang != "en" else ["en"]
        else:
            # Default to common European languages + English
            languages = ["en", "nl", "fr", "de", "es"]

        # Normalize the action (with language support)
        action_normalized = cache.normalize_action(instruction, languages)

        # Partition elements by viewport visibility for prioritized matching
        viewport_elements, offscreen_elements = _partition_elements_by_viewport(actionable_elements)

        if verbose:
            click.echo(f"  Viewport elements: {len(viewport_elements)}", err=True)
            click.echo(f"  Off-screen elements: {len(offscreen_elements)}", err=True)

        # Variables to track matching method and result
        matched_element = None
        match_method = None
        match_score = 0.0
        search_scope = None  # Track where the match was found

        # WATERFALL APPROACH with VIEWPORT PRIORITIZATION
        # Try viewport elements first, then expand to full page if needed
        if not force_ai:
            click.echo(f"Searching for matches (action: '{action_normalized}')…", err=True)

            # PHASE 1: Search within viewport elements first
            if viewport_elements:
                if verbose:
                    click.echo("Phase 1: Searching in viewport…", err=True)

                matched_element, match_method, match_score = _try_matching_strategies(
                    matcher=matcher,
                    cache=cache,
                    action_normalized=action_normalized,
                    elements=viewport_elements,
                    languages=languages,
                    current_url=current_url,
                    page_data=page_data,
                    scope_label="viewport",
                    verbose=verbose,
                    skip_cache=no_cache,
                )

                if matched_element:
                    search_scope = "viewport"

            # PHASE 2: If no viewport match, search off-screen elements
            if not matched_element and offscreen_elements:
                if verbose:
                    click.echo("Phase 2: Expanding search to off-screen elements…", err=True)

                matched_element, match_method, match_score = _try_matching_strategies(
                    matcher=matcher,
                    cache=cache,
                    action_normalized=action_normalized,
                    elements=offscreen_elements,
                    languages=languages,
                    current_url=current_url,
                    page_data=page_data,
                    scope_label="off-screen",
                    verbose=verbose,
                    skip_cache=no_cache,
                )

                if matched_element:
                    search_scope = "off-screen"

            # PHASE 3: If modal was active but no match found, retry with ALL elements
            if not matched_element and active_modal and all_elements:
                click.echo(click.style(
                    "No match in modal — expanding search to full page",
                    fg="yellow"
                ), err=True)
                full_viewport, full_offscreen = _partition_elements_by_viewport(all_elements)
                for scope_els, scope_name in [(full_viewport, "full-page viewport"), (full_offscreen, "full-page off-screen")]:
                    if matched_element or not scope_els:
                        continue
                    matched_element, match_method, match_score = _try_matching_strategies(
                        matcher=matcher, cache=cache,
                        action_normalized=action_normalized,
                        elements=scope_els, languages=languages,
                        current_url=current_url, page_data=page_data,
                        scope_label=scope_name, verbose=verbose,
                        skip_cache=no_cache,
                    )
                    if matched_element:
                        search_scope = scope_name

        # If we found a match without AI, skip to execution
        if matched_element and not debug:
            # Determine execution based on match score
            should_execute = False

            if match_score >= 0.8:
                # High confidence match (80%+) - auto-execute
                click.echo()
                scope_info = f" in {search_scope}" if search_scope else ""
                click.echo(click.style(f"High confidence match{scope_info} (confidence: {match_score:.0%}) [{match_method}]", fg="green", bold=True))
                click.echo(f"  → {matched_element.get('type')}: {matched_element.get('text', 'N/A')[:80]}")
                if matched_element.get('href'):
                    click.echo(f"  → URL: {matched_element.get('href')}")
                should_execute = True
            else:
                # Low confidence - fall back to AI
                matched_element = None
                click.echo(click.style(f"Match confidence too low ({match_score:.0%}), falling back to AI…", fg="yellow"), err=True)

            # Execute if approved
            if should_execute and not no_execute:
                click.echo()
                click.echo("Executing action…", err=True)

                # Get the action ID for this element
                action_id = matched_element.get("actionId")

                # Execute using the existing execution logic (will add below)
                # For now, set a flag to skip AI and use this element
                _execute_element_action(client, action_id, matched_element, instruction)

                # Store in cache for future use (skip if --no-cache)
                if cache.is_enabled() and match_method != "CACHED" and not no_cache:
                    cache.store_action(current_url, instruction, action_normalized, matched_element, page_data)
                    click.echo(click.style(success("Action cached for future use"), fg="green"), err=True)

                return  # Exit successfully without calling AI

        # If no match found or --force-ai, continue to AI
        if not matched_element or force_ai:
            if force_ai:
                click.echo(click.style("Forcing AI matching (--force-ai)…", fg="yellow"), err=True)
            else:
                click.echo(click.style("No automatic match found, using AI…", fg="yellow"), err=True)

        # Read the prompt
        prompt_path = Path(__file__).parent.parent.parent.parent / "prompts" / "do.prompt"

        if not prompt_path.exists():
            click.echo(f"Error: Prompt file not found: {prompt_path}", err=True)
            sys.exit(1)

        with builtin_open(prompt_path) as f:
            prompt = f.read().strip()

        # Format the page data for the AI with viewport-prioritized elements
        # Put viewport elements first so AI gives them preference
        prioritized_elements = viewport_elements + offscreen_elements

        # Mark elements with their visibility status for AI context
        elements_with_visibility = []
        for el in prioritized_elements:
            el_copy = dict(el)
            # Add visibility hint for AI (viewport elements are more likely targets)
            if el.get("inViewport", False):
                el_copy["_visibility"] = "currently visible in viewport"
            else:
                el_copy["_visibility"] = "off-screen (requires scrolling)"
            elements_with_visibility.append(el_copy)

        page_structure = {
            "pageTitle": page_data.get("pageTitle"),
            "pageUrl": page_data.get("pageUrl"),
            "language": page_data.get("language"),
            "landmarks": page_data.get("landmarks", []),
            "headings": page_data.get("headings", []),
            # Elements are ordered: viewport first, then off-screen
            "actionableElements": elements_with_visibility,
            "_note": f"Elements are prioritized: first {len(viewport_elements)} are in viewport, rest are off-screen"
        }

        # Combine prompt with instruction and page data
        full_input = f"{prompt}\n\n---\n\nUSER INSTRUCTION:\n{instruction}\n\n---\n\nPAGE DATA:\n{json.dumps(page_structure, indent=2)}"

        # Debug mode: show the full prompt instead of calling AI
        if debug:
            click.echo("=" * 80)
            click.echo("DEBUG: Full prompt that would be sent to AI")
            click.echo("=" * 80)
            click.echo()
            click.echo(full_input)
            click.echo()
            click.echo("=" * 80)
            return

        click.echo("Finding matching actions with AI…", err=True)

        # Call AI service using the multi-provider system
        # The 'do' command uses a fast model for simple text matching
        ai_service = get_ai_service()

        try:
            raw_output = ai_service.call_ai(
                prompt=full_input,
                command="do",  # Allows command-specific model defaults
                max_tokens=500,  # Response is just JSON, doesn't need many tokens
                timeout=30.0,
            )
        except Exception as e:
            click.echo(f"Error calling AI service: {e}", err=True)
            click.echo("Hint: Check your API key configuration with `inspekt config`", err=True)
            sys.exit(1)

        # Parse the JSON response
        raw_output = raw_output.strip()
        response = None

        try:
            response = json.loads(raw_output)
        except json.JSONDecodeError:
            # Try to strip markdown code blocks (```json ... ```)
            if raw_output.startswith("```"):
                # Remove opening ```json or ``` and closing ```
                lines = raw_output.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]  # Remove first line
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]  # Remove last line
                raw_output = "\n".join(lines).strip()

                try:
                    response = json.loads(raw_output)
                except json.JSONDecodeError as e:
                    click.echo(f"Error: AI returned invalid JSON even after stripping markdown: {e}", err=True)
                    click.echo("Raw response:", err=True)
                    click.echo(raw_output, err=True)
                    sys.exit(1)
            else:
                click.echo("Error: AI returned invalid JSON", err=True)
                click.echo("Raw response:", err=True)
                click.echo(raw_output, err=True)
                sys.exit(1)

        # Output the results (now correctly outside the exception handler)
        click.echo()
        click.echo(f"Interpretation: {response.get('interpretation', 'N/A')}")
        click.echo()

        # Check for multi-step action plan from AI
        steps = response.get("steps")
        if steps and isinstance(steps, list) and len(steps) > 0:
            click.echo(f"AI planned {len(steps)} step(s):")
            click.echo()
            for i, step in enumerate(steps, 1):
                action = step.get("action", "?")
                reasoning = step.get("reasoning", "")
                detail = ""
                if action == "click":
                    detail = f" → {step.get('actionId', '?')}"
                elif action == "type":
                    detail = f" → \"{step.get('text', '')}\""
                elif action == "press":
                    detail = f" → {step.get('key', '?')}"
                elif action == "select":
                    detail = f" → {step.get('value', '?')}"
                click.echo(f"  {i}. {action}{detail}")
                if reasoning:
                    click.echo(f"     {reasoning}")
            click.echo()

            if not no_execute:
                click.echo(click.style("Executing multi-step action…", fg="green", bold=True))
                click.echo()
                try:
                    _execute_multi_step(client, steps, actionable_elements)

                    # Cache the first element for future single-step use
                    first_action_id = next((s.get("actionId") for s in steps if s.get("actionId")), None)
                    if first_action_id and cache.is_enabled() and not no_cache:
                        first_element = next((el for el in actionable_elements if el.get("actionId") == first_action_id), None)
                        if first_element:
                            cache.store_action(current_url, instruction, action_normalized, first_element, page_data)
                except (ConnectionError, TimeoutError, RuntimeError) as e:
                    click.echo(click.style(error(f"Error during multi-step execution: {e}"), fg="red"), err=True)
                    sys.exit(1)

            return  # Done — skip single-match handling

        matches = response.get("matches", [])
        if not matches:
            click.echo("No matching actions found.")
            sys.exit(0)

        click.echo(f"Found {len(matches)} matching action(s) [AI]:")
        click.echo()

        for i, match in enumerate(matches, 1):
            action_id = match.get("actionId")
            probability = match.get("probability", 0)
            reasoning = match.get("reasoning", "")

            # Find the full element details
            element = next((el for el in actionable_elements if el.get("actionId") == action_id), None)

            # Determine visibility status for display
            visibility_info = ""
            if element:
                if element.get("inViewport", False):
                    visibility_info = " [viewport]"
                else:
                    visibility_info = " [off-screen]"

            click.echo(f"{i}. {action_id}{visibility_info} (probability: {probability:.0%})")
            if element:
                click.echo(f"   Type: {element.get('type')}")
                click.echo(f"   Text: {element.get('text', 'N/A')[:100]}")
                if element.get('href'):
                    click.echo(f"   URL: {element.get('href')}")
                if element.get('context'):
                    ctx = element['context']
                    if ctx.get('type') == 'heading':
                        click.echo(f"   Context: Under heading '{ctx.get('text', '')[:50]}'")
                    elif ctx.get('type') == 'landmark':
                        click.echo(f"   Context: In {ctx.get('role')} landmark")
            click.echo(f"   Reasoning: {reasoning}")
            click.echo()

        # Check if we should auto-execute or ask for confirmation
        if not no_execute:
            top_match = matches[0]
            top_probability = top_match.get("probability", 0)
            top_action_id = top_match.get("actionId")
            top_element = next((el for el in actionable_elements if el.get("actionId") == top_action_id), None)

            should_execute = False

            # Determine visibility for the message
            visibility_note = ""
            if top_element:
                if top_element.get("inViewport", False):
                    visibility_note = " in viewport"
                else:
                    visibility_note = " (off-screen)"

            if top_probability >= 0.8:
                # High confidence (80%+) - auto-execute
                click.echo(click.style(f"High confidence match{visibility_note} (confidence: {top_probability:.0%}) [AI]", fg="green", bold=True))
                if top_element:
                    click.echo(f"  → {top_element.get('type')}: {top_element.get('text', 'N/A')[:80]}")
                    if top_element.get('href'):
                        click.echo(f"  → URL: {top_element.get('href')}")
                click.echo(click.style("Auto-executing…", fg="green"))
                should_execute = True
            else:
                # Lower confidence - ask for confirmation
                click.echo()
                click.echo(click.style(f"Would you like to execute this action?{visibility_note} (confidence: {top_probability:.0%})", fg="yellow", bold=True))
                if top_element:
                    click.echo(f"  → {top_element.get('type')}: {top_element.get('text', 'N/A')[:80]}")
                    if top_element.get('href'):
                        click.echo(f"  → URL: {top_element.get('href')}")
                click.echo()

                # Ask for confirmation
                if click.confirm("Execute action?", default=True):
                    should_execute = True
                else:
                    click.echo("Action cancelled.")

            if should_execute:
                # Execute the action
                click.echo()
                click.echo("Executing action…", err=True)

                try:
                    _execute_element_action(client, top_action_id, top_element, instruction)

                    # Store in cache for future use [AI] (skip if --no-cache)
                    if cache.is_enabled() and not no_cache:
                        cache.store_action(current_url, instruction, action_normalized, top_element, page_data)
                        click.echo(click.style(success("Action cached for future use [AI]"), fg="green"), err=True)

                except (ConnectionError, TimeoutError, RuntimeError) as e:
                    click.echo(click.style(error(f"Error executing action: {e}"), fg="red"), err=True)
                    sys.exit(1)

        # Output as JSON for easy parsing (only in verbose mode to reduce noise)
        if verbose:
            click.echo()
            click.echo("JSON Output:")
            click.echo(json.dumps(response, indent=2))

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _process_outline_headings(headings: list) -> list:
    """
    Process headings to:
    1. Insert placeholders for missing heading levels
    2. Mark duplicates (2nd+ occurrence)
    3. Mark empty headings
    4. Pass through ARIA type info
    """
    processed = []
    seen_texts = {}  # text -> first occurrence (case-insensitive)
    expected_level = 1  # Track expected next level

    for heading in headings:
        level = heading["level"]
        text = heading["text"]
        text_lower = text.lower().strip()

        # Insert missing levels before this heading
        while expected_level < level:
            processed.append({
                "level": expected_level,
                "text": "",
                "type": "missing",
                "is_missing": True,
                "is_empty": False,
                "is_duplicate": False
            })
            expected_level += 1

        # Check for duplicates (2nd+ occurrence only, skip empty text)
        is_duplicate = text_lower and text_lower in seen_texts
        if text_lower and not is_duplicate:
            seen_texts[text_lower] = True

        # Check for empty headings (real heading but no text content)
        is_empty = not text.strip()

        processed.append({
            "level": level,
            "text": text,
            "type": heading.get("type", "native"),
            "is_missing": False,
            "is_empty": is_empty,
            "is_duplicate": is_duplicate
        })

        # Update expected level: after H2, expect H2 or H3 next
        # But if next heading is H1 again, that resets context
        expected_level = level + 1

    return processed


@click.command()
@url_scheme(
    "outline",
    param_map={"output_json": "json"},
    exclude_params=["truncate"],
)
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON")
@click.option("--truncate", type=int, default=None, help="Truncate headings to specified number of characters")
def outline(output_json, truncate):
    """
    Display the page's heading structure as a nested outline.

    Shows all headings (H1-H6 and ARIA headings) in a hierarchical view.
    Indicates missing levels (red), duplicates (yellow), and ARIA headings (gray).

    Examples:
        inspekt outline
        inspekt outline --json
        inspekt outline --truncate 80
    """
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Load and execute the extract_outline script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "extract_outline.js"

    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        with builtin_open(script_path) as f:
            script = f.read()

        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        data = result.get("result", {})
        headings = data.get("headings", [])

        if not headings:
            if output_json:
                from inspekt.app.cli.table import print_json
                print_json({"headings": [], "count": 0}, summary="0 headings")
            else:
                click.echo("No headings found on this page.", err=True)
            sys.exit(0)

        # Process headings to detect missing levels, duplicates, and empty headings
        processed_headings = _process_outline_headings(headings)

        # Calculate counts
        total_real = len([h for h in processed_headings if not h.get("is_missing")])
        missing_count = len([h for h in processed_headings if h.get("is_missing")])
        duplicate_count = len([h for h in processed_headings if h.get("is_duplicate")])
        empty_count = len([h for h in processed_headings if h.get("is_empty")])

        output_data = {
            "headings": processed_headings,
            "count": total_real,
            "missing_count": missing_count,
            "duplicate_count": duplicate_count,
            "empty_count": empty_count,
            "url": data.get("url", ""),
            "title": data.get("title", ""),
        }
        toast_summary = f"{total_real} headings"

        if output_json:
            from inspekt.app.cli.table import print_json
            print_json(output_data, summary=toast_summary)
            return

        # Display the outline with proper indentation
        for heading in processed_headings:
            level = heading["level"]
            is_missing = heading.get("is_missing", False)
            is_empty = heading.get("is_empty", False)
            is_duplicate = heading.get("is_duplicate", False)
            is_aria = heading.get("type") == "aria"

            # Calculate indentation (3 spaces per level)
            indent = "   " * (level - 1)

            if is_missing:
                # Missing level: red label and [Missing] text
                level_label = click.style(f"H{level}", fg="red")
                heading_text = click.style("[Missing]", fg="red")
            elif is_empty:
                # Empty heading: magenta label and [Empty] text
                level_label = click.style(f"H{level}", fg="magenta")
                heading_text = click.style("[Empty]", fg="magenta")
            else:
                # Normal heading: gray label
                level_label = click.style(f"H{level}", fg="bright_black")
                text = heading["text"]

                # Truncate headings only if --truncate is specified
                if truncate and len(text) > truncate:
                    text = text[:truncate - 1] + "…"

                heading_text = text

                # Add indicators
                indicators = []
                if is_duplicate:
                    indicators.append(click.style("[Duplicate]", fg="yellow"))
                if is_aria:
                    indicators.append(click.style("[ARIA]", fg="bright_black"))

                if indicators:
                    heading_text = f"{heading_text} {' '.join(indicators)}"

            from inspekt.app.cli.sitemap import wrap_styled_line
            for line in wrap_styled_line(
                prefix=f"{indent}{level_label} ",
                text=heading_text,
            ):
                click.echo(line)

        # Show summary with issue counts
        click.echo("", err=True)
        summary_parts = [f"Total: {total_real} headings"]
        if missing_count:
            summary_parts.append(click.style(f"{missing_count} missing", fg="red"))
        if empty_count:
            summary_parts.append(click.style(f"{empty_count} empty", fg="magenta"))
        if duplicate_count:
            summary_parts.append(click.style(f"{duplicate_count} duplicates", fg="yellow"))
        click.echo(" | ".join(summary_parts), err=True)

        # VM terminal: offer a "Data ready to copy" toast in default mode too
        from inspekt.app.cli.table import emit_copyable_data
        outline_rows = []
        for h in processed_headings:
            flags = []
            if h.get("is_missing"):
                flags.append("missing")
            if h.get("is_empty"):
                flags.append("empty")
            if h.get("is_duplicate"):
                flags.append("duplicate")
            if h.get("type") == "aria":
                flags.append("aria")
            level = h["level"]
            text = "" if h.get("is_missing") else h.get("text", "")
            outline_rows.append([
                f"H{level}",
                "  " * (level - 1) + text,
                ", ".join(flags),
            ])
        emit_copyable_data(
            headers=["Level", "Heading", "Flags"],
            rows=outline_rows,
            json_data=output_data,
            summary=toast_summary,
        )

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _enrich_link_metadata(url: str) -> dict:
    """
    Fetch metadata for a single external link using curl.

    Returns dict with: http_status, mime_type, file_size, filename, page_title, page_language
    """
    enrichment = {
        "http_status": None,
        "mime_type": None,
        "file_size": None,
        "filename": None,
        "page_title": None,
        "page_language": None,
    }

    try:
        # First, do a HEAD request to get headers
        head_result = subprocess.run(
            ["curl", "-L", "-I", "-s", "-m", "5", "--user-agent", "inspekt/1.0", url],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if head_result.returncode != 0:
            return enrichment

        headers = head_result.stdout

        # Parse HTTP status code
        status_match = re.search(r"HTTP/[\d.]+ (\d+)", headers)
        if status_match:
            enrichment["http_status"] = int(status_match.group(1))

        # Parse Content-Type
        content_type_match = re.search(r"(?i)^Content-Type:\s*([^\r\n;]+)", headers, re.MULTILINE)
        if content_type_match:
            enrichment["mime_type"] = content_type_match.group(1).strip()

        # Parse Content-Length
        content_length_match = re.search(r"(?i)^Content-Length:\s*(\d+)", headers, re.MULTILINE)
        if content_length_match:
            enrichment["file_size"] = int(content_length_match.group(1))

        # Parse Content-Disposition for filename
        content_disp_match = re.search(
            r'(?i)^Content-Disposition:.*filename[*]?=["\']?([^"\'\r\n;]+)', headers, re.MULTILINE
        )
        if content_disp_match:
            enrichment["filename"] = content_disp_match.group(1).strip()

        # Parse Content-Language
        content_lang_match = re.search(
            r"(?i)^Content-Language:\s*([^\r\n;]+)", headers, re.MULTILINE
        )
        if content_lang_match:
            enrichment["page_language"] = content_lang_match.group(1).strip()

        # If this looks like HTML, fetch partial content to get title and lang
        mime_type = enrichment.get("mime_type", "").lower()
        if mime_type and ("html" in mime_type or mime_type == "text/html"):
            # Fetch first 16KB of content
            get_result = subprocess.run(
                [
                    "curl",
                    "-L",
                    "-s",
                    "-m",
                    "5",
                    "--user-agent",
                    "inspekt/1.0",
                    "--max-filesize",
                    "16384",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if get_result.returncode == 0:
                html_content = get_result.stdout

                # Extract page title
                title_match = re.search(r"<title[^>]*>([^<]+)</title>", html_content, re.IGNORECASE)
                if title_match:
                    # Decode HTML entities and clean up
                    title = title_match.group(1).strip()
                    title = re.sub(r"\s+", " ", title)  # Normalize whitespace
                    enrichment["page_title"] = title

                # Extract language from <html lang="…">
                if not enrichment["page_language"]:
                    lang_match = re.search(
                        r'<html[^>]+lang=["\']?([^"\'\s>]+)', html_content, re.IGNORECASE
                    )
                    if lang_match:
                        enrichment["page_language"] = lang_match.group(1).strip()

    except (subprocess.TimeoutExpired, subprocess.SubprocessError, Exception):
        # Silently fail - return partial data
        pass

    return enrichment


def _enrich_external_links(links: list) -> list:
    """
    Enrich external links with metadata using parallel curl requests.
    Only processes up to 50 external links.

    Returns the same list with enrichment data added to external links.
    """
    # Filter to get external links only
    external_links = [
        link for link in links if link.get("external") or link.get("type") == "external"
    ]

    # Check if we should skip enrichment
    if len(external_links) > 50:
        return links

    # Create a mapping of URL to link object
    url_to_link = {}
    urls_to_enrich = []

    for link in external_links:
        url = link.get("url") or link.get("href")
        if url:
            url_to_link[url] = link
            urls_to_enrich.append(url)

    # Fetch metadata in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_url = {executor.submit(_enrich_link_metadata, url): url for url in urls_to_enrich}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                enrichment = future.result()
                # Add enrichment data to the link object
                link_obj = url_to_link[url]
                link_obj.update(enrichment)
            except Exception:
                # Skip failed enrichments
                pass

    return links


@click.command()
@click.option("--only-internal", is_flag=True, help="Show only internal links (same domain)")
@click.option("--only-external", is_flag=True, help="Show only external links (different domain)")
@click.option("--alphabetically", is_flag=True, help="Sort links alphabetically")
@click.option("--only-urls", is_flag=True, help="Show only URLs without anchor text")
@click.option(
    "--json", "-j", "output_json", is_flag=True, help="Output as JSON with detailed link information"
)
@click.option(
    "--enrich-external",
    is_flag=True,
    help="Fetch additional metadata for external links (MIME type, file size, page title, language, HTTP status)",
)
def links(only_internal, only_external, alphabetically, only_urls, output_json, enrich_external):
    """
    Extract all links from the current page.

    By default, shows all links with their anchor text.
    Use filters to show only internal or external links.

    Examples:
        inspekt links                           # All links with anchor text
        inspekt links --only-internal           # Only links on same domain
        inspekt links --only-external           # Only links to other domains
        inspekt links --alphabetically          # Sort alphabetically
        inspekt links --only-urls               # Show only URLs
        inspekt links --only-external --only-urls  # External URLs only
        inspekt links --enrich-external         # Add metadata for external links
    """
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Check for conflicting flags
    if only_internal and only_external:
        click.echo("Error: Cannot use --only-internal and --only-external together", err=True)
        sys.exit(1)

    # Load and execute the extract_links script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "extract_links.js"

    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        with builtin_open(script_path) as f:
            script = f.read()

        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        data = result.get("result", {})
        all_links = data.get("links", [])
        domain = data.get("domain", "")

        if not all_links:
            click.echo("No links found on this page.", err=True)
            sys.exit(0)

        # Filter links
        filtered_links = all_links
        if only_internal:
            filtered_links = [link for link in all_links if link["type"] == "internal"]
        elif only_external:
            filtered_links = [link for link in all_links if link["type"] == "external"]

        if not filtered_links:
            filter_type = "internal" if only_internal else "external" if only_external else "total"
            click.echo(f"No {filter_type} links found.", err=True)
            sys.exit(0)

        # Enrich external links if requested
        if enrich_external:
            filtered_links = _enrich_external_links(filtered_links)

        # Sort if requested
        if alphabetically:
            if only_urls:
                # Sort by URL
                filtered_links.sort(key=lambda x: x["href"].lower())
            else:
                # Sort by anchor text
                filtered_links.sort(key=lambda x: x["text"].lower())

        # If JSON output is requested, output JSON and exit
        if output_json:
            output_data = {"links": filtered_links, "total": len(filtered_links), "domain": domain}
            from inspekt.app.cli.table import print_json
            print_json(output_data, summary=f"{len(filtered_links)} links")
            return

        # Output links
        if only_urls:
            # Just print URLs, one per line
            for link in filtered_links:
                click.echo(link["href"])
        else:
            # Print with anchor text
            for link in filtered_links:
                text = link["text"]
                href = link["href"]
                # Truncate long text
                if len(text) > 60:
                    text = text[:57] + "…"
                # Show type indicator
                ext_icon = get_indicator("external") or "↗"
                int_icon = get_indicator("internal") or "→"
                type_indicator = ext_icon if link["type"] == "external" else int_icon
                click.echo(f"{type_indicator} {text}")
                click.echo(f"  {href}")

                # Show enrichment data if available
                if enrich_external and link.get("type") == "external":
                    enrichment_lines = []

                    if link.get("http_status") is not None:
                        enrichment_lines.append(f"HTTP {link['http_status']}")

                    if link.get("mime_type"):
                        enrichment_lines.append(link["mime_type"])

                    if link.get("file_size") is not None:
                        size_str = format_filesize(link["file_size"])
                        enrichment_lines.append(size_str)

                    if link.get("filename"):
                        enrichment_lines.append(f"File: {link['filename']}")

                    if link.get("page_title"):
                        title = link["page_title"]
                        if len(title) > 60:
                            title = title[:57] + "…"
                        enrichment_lines.append(f"Title: {title}")

                    if link.get("page_language"):
                        enrichment_lines.append(f"Lang: {link['page_language']}")

                    if enrichment_lines:
                        click.echo(f"  {' | '.join(enrichment_lines)}")

                click.echo("")

        # Show summary
        total = len(all_links)
        shown = len(filtered_links)
        if only_internal or only_external:
            filter_type = "internal" if only_internal else "external"
            click.echo(f"Showing {shown} {filter_type} links (of {total} total)", err=True)
        else:
            click.echo(f"Total: {shown} links", err=True)

        # VM terminal: offer a "Data ready to copy" toast
        from inspekt.app.cli.table import emit_copyable_data
        link_rows = [
            [link.get("type", ""), link.get("text", "") or "", link.get("href", "") or ""]
            for link in filtered_links
        ]
        emit_copyable_data(
            headers=["Type", "Text", "URL"],
            rows=link_rows,
            json_data={"links": filtered_links, "total": shown, "domain": domain},
            summary=f"{shown} link{'s' if shown != 1 else ''}",
        )

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@url_scheme(
    "summarize",
    defaults={"format": "summary", "language": None, "speak": None},
    exclude_params=["debug", "force_refresh", "output_json", "output"],
)
@click.option(
    "--format",
    type=click.Choice(["summary", "full"]),
    default="summary",
    help="Output format (summary or full article)",
)
@click.option(
    "--language", "--lang", type=str, default=None, help="Language for AI output (overrides config)"
)
@click.option("--debug", is_flag=True, help="Show the full prompt instead of calling AI")
@click.option("--force-refresh", is_flag=True, help="Force refresh, bypass cache")
@click.option("--json", "-j", "output_json", is_flag=True, help="Output as JSON with metadata")
@click.option(
    "--output", "-o",
    type=click.Path(),
    help="Save output to file (.txt for text, .mp3 for audio)",
)
@click.option(
    "--speak",
    is_flag=False,
    flag_value="default",  # Use default voice from config
    default=None,
    metavar="VOICE",
    help="Read the summary aloud using TTS (--speak for default voice, --speak margot for specific)",
)
def summarize(format, language, debug, force_refresh, output_json, output, speak):
    """
    Summarize the current article using AI.

    Extracts article content using Mozilla Readability and generates
    a concise summary using the mods command.

    Examples:
        inspekt summarize                    # Get AI summary
        inspekt summarize --format full      # Show full extracted article
        inspekt summarize --json             # Output as JSON with metadata
        inspekt summarize --speak margot     # Read summary aloud with Margot voice
    """
    import time

    from inspekt.config import get_summarize_config

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Get extractor config
    summarize_config = get_summarize_config()
    extractor = summarize_config.get("extractor", "readability")

    # Determine which script to use based on extractor config
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"

    if extractor == "readability":
        # Use Mozilla Readability
        readability_lib_path = scripts_dir / "vendor" / "readability" / "Readability.js"
        extraction_script_path = scripts_dir / "extract_article_readability.js"

        if not readability_lib_path.exists():
            click.echo("Error: Mozilla Readability library not found.", err=True)
            click.echo("Run `inspekt update readability` to install it.", err=True)
            sys.exit(1)

        if not extraction_script_path.exists():
            click.echo(f"Error: Script not found: {extraction_script_path}", err=True)
            sys.exit(1)

        # Load both the library and the extraction script
        with builtin_open(readability_lib_path) as f:
            readability_lib = f.read()
        with builtin_open(extraction_script_path) as f:
            extraction_script = f.read()

        # Wrap everything in a single IIFE to work with AsyncFunction execution
        # The bridge wraps code in AsyncFunction which doesn't allow top-level
        # var/function declarations, so we nest everything in an IIFE
        #
        # IMPORTANT: The extraction_script starts with comments, so we must use
        # parentheses after 'return' to prevent ASI (Automatic Semicolon Insertion)
        # from making it 'return;' which would return undefined
        script = f"""(function() {{
try {{
// Define Readability in this scope
{readability_lib}

// Now run extraction (parentheses prevent ASI after return)
return ({extraction_script})
}} catch (outerError) {{
  return {{ error: 'Outer wrapper error: ' + outerError.message, stack: outerError.stack, url: window.location.href }};
}}
}})()"""
    else:
        # Use custom lightweight extractor
        script_path = scripts_dir / "extract_article.js"

        if not script_path.exists():
            click.echo(f"Error: Script not found: {script_path}", err=True)
            sys.exit(1)

        with builtin_open(script_path) as f:
            script = f.read()

    try:
        # Get page title first for the progress message
        page_title_for_display = None
        if not output_json:
            title_script = "document.title || window.location.hostname"
            title_result = client.execute(title_script, timeout=5.0)
            if title_result.get("ok"):
                page_title_for_display = title_result.get("result", "")
                # Truncate long titles for display
                if page_title_for_display and len(page_title_for_display) > 60:
                    page_title_for_display = page_title_for_display[:57] + "…"

        if not output_json:
            if page_title_for_display:
                click.echo(analyze_icon(f'Extracting article content from "{page_title_for_display}"…'), err=True)
            else:
                click.echo(analyze_icon("Extracting article content…"), err=True)
        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        article = result.get("result") or {}

        if not article:
            click.echo("Error: No content extracted. The page may not be an article or may have restricted access.", err=True)
            sys.exit(1)

        if article.get("error"):
            click.echo(f"Error: {article['error']}", err=True)
            sys.exit(1)

        title = article.get("title", "Untitled")
        content = article.get("content", "")
        byline = article.get("byline", "")
        page_lang = article.get("lang")

        if not content:
            click.echo("Error: No content extracted. This page may not be an article.", err=True)
            sys.exit(1)

        # If full format, just show the extracted article
        if format == "full":
            click.echo(f"Title: {title}")
            if byline:
                click.echo(f"By: {byline}")
            click.echo("")
            click.echo(content)
            return

        # Determine target language for AI
        target_lang = get_ai_language(language_override=language, page_lang=page_lang)

        # Get current URL for caching (from article extraction result)
        current_url = article.get("url", "")

        # Prepare article data for fingerprinting
        article_data = {
            "title": title,
            "text": content,
            "publishedDate": article.get("publishedDate", ""),
        }

        # Try cache first (unless force refresh or debug mode)
        content_cache = ContentCache()
        cached_result = None

        if not force_refresh and not debug and content_cache.is_enabled("summarize"):
            fingerprint = content_cache.create_summarize_fingerprint(article_data)
            cached_result = content_cache.get_cached_content(current_url, "summarize", fingerprint, target_lang or "auto")

            if cached_result:
                cache_similarity = cached_result["similarity"]
                age_seconds = cached_result["age_seconds"]
                cache_timestamp = time.time() - age_seconds

                if output_json:
                    # Get AI service for model info
                    ai_service = get_ai_service()
                    model_info = ai_service.get_model_info()

                    json_output = {
                        "summary": cached_result["output"],
                        "title": title,
                        "byline": byline or None,
                        "url": current_url,
                        "language": target_lang or page_lang,
                        "from_cache": True,
                        "cache": {
                            "similarity": cache_similarity,
                            "cached_at": cache_timestamp,
                            "age_seconds": age_seconds,
                        },
                        "ai": model_info,
                    }
                    from inspekt.app.cli.table import print_json
                    print_json(json_output, summary="article summary (cached)")
                    return

                # Format age for display
                if age_seconds < 3600:
                    age_str = f"{age_seconds // 60} minutes ago"
                elif age_seconds < 86400:
                    age_str = f"{age_seconds // 3600} hours ago"
                else:
                    age_str = f"{age_seconds // 86400} days ago"

                click.echo(cached_icon(f"Using cached summary (similarity: {cache_similarity:.0%}, cached {age_str})"), err=True)
                click.echo()
                if byline:
                    click.echo(f"By: {byline}")
                    click.echo("")
                print_wrapped(cached_result["output"], fg="white", bold=False)

                # Speak the summary if --speak is provided
                if speak:
                    _speak_text(cached_result["output"], speak)

                return

        # Use AI service for summary generation
        ai_service = get_ai_service()

        # Show byline before AI call if in debug mode
        if debug and byline:
            click.echo(f"Article by: {byline}", err=True)
            click.echo("", err=True)

        if not output_json:
            click.echo(generate_icon("Generating summary…"), err=True)

        summary_text = ai_service.generate_summary(
            article=article,
            language_override=language,
            debug=debug
        )

        # If debug mode, generate_summary returns None after showing prompt
        if debug:
            return

        # Store in cache for future use
        generation_timestamp = time.time()
        if content_cache.is_enabled("summarize") and current_url:
            fingerprint = content_cache.create_summarize_fingerprint(article_data)
            content_cache.store_content(current_url, "summarize", fingerprint, summary_text, target_lang or "auto")
            if not output_json:
                click.echo(success("Summary cached for future use"), err=True)

        if output_json:
            model_info = ai_service.get_model_info()
            json_output = {
                "summary": summary_text,
                "title": title,
                "byline": byline or None,
                "url": current_url,
                "language": target_lang or page_lang,
                "from_cache": False,
                "generated_at": generation_timestamp,
                "ai": model_info,
            }
            from inspekt.app.cli.table import print_json
            print_json(json_output, summary="article summary")
        elif output:
            # Smart output detection by extension
            output_path = Path(output)
            audio_extensions = {'.mp3', '.wav', '.m4a', '.aac'}
            is_audio_output = output_path.suffix.lower() in audio_extensions

            if is_audio_output:
                # Audio output - generate TTS and save to file
                voice = speak if speak else "default"
                _speak_text(summary_text, voice, audio_output=str(output_path))
            else:
                # Text output
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(summary_text)
                click.echo(success(f"Saved to: {output_path}"), err=True)

                # Also speak if --speak was provided
                if speak:
                    _speak_text(summary_text, speak)
        else:
            click.echo()
            if byline:
                click.echo(f"By: {byline}")
                click.echo("")
            print_wrapped(summary_text, fg="white", bold=False)

            # Speak the summary if --speak is provided
            if speak:
                _speak_text(summary_text, speak)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@click.option("--no-cache", is_flag=True, help="Don't save to cache")
@click.option("--output", "-o", type=click.Path(), help="Save to specific file instead of cache")
@click.option("--headless", is_flag=True, help="Run in headless Chrome (no browser extension required)")
@click.option("--mirror-session", is_flag=True, help="Mirror cookies/storage from live browser (implies --headless)")
@click.option("--url", "headless_url", default=None, help="URL to index in headless mode")
def index(no_cache, output, headless, mirror_session, headless_url):
    """
    Index the current page with full semantic structure and accessible names.

    Creates a comprehensive Markdown representation of the page including:
    - Page landmarks and semantic structure
    - All headings with hierarchy
    - Main content paragraphs
    - Lists and their items
    - Interactive elements (links, buttons, form controls) with accessible names
    - Images with alt text

    The indexed page is saved to cache and can be used by the 'inspekt ask' command
    to answer questions about the page content.

    Examples:
        inspekt index                    # Index and cache current page
        inspekt index --no-cache         # Index but don't cache
        inspekt index -o page.md         # Save to specific file
        inspekt index --headless --url https://example.com  # Index in headless mode
    """
    # ========== HEADLESS MODE ==========
    if headless or mirror_session:
        import asyncio

        from inspekt.services.headless import HeadlessContext

        if mirror_session:
            headless = True

        if not headless_url and not mirror_session:
            click.echo("Error: --headless requires --url or --mirror-session", err=True)
            sys.exit(1)

        async def index_headless():
            """Index page in headless Chrome."""
            script_path = Path(__file__).parent.parent.parent / "scripts" / "index_page.js"
            if not script_path.exists():
                return {"ok": False, "error": f"Script not found: {script_path}"}

            with builtin_open(script_path) as f:
                script = f.read()

            if mirror_session:
                click.echo("  Headless mode with session mirroring", err=True)
            else:
                click.echo("  Headless mode", err=True)

            try:
                async with HeadlessContext(
                    url=headless_url,
                    mirror_session=mirror_session,
                    timeout=30.0,
                ) as ctx:
                    click.echo(f"URL: {ctx.url}", err=True)
                    click.echo("Indexing page structure…", err=True)

                    result = await ctx.execute_script(script)
                    return {"ok": True, "result": result, "url": ctx.url}

            except Exception as e:
                return {"ok": False, "error": str(e)}

        # Run async indexing
        index_result = asyncio.run(index_headless())

        if not index_result.get("ok"):
            click.echo(f"Error: {index_result.get('error')}", err=True)
            sys.exit(1)

        result = index_result.get("result", {})
        current_url = index_result.get("url", "unknown")

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        markdown_content = result.get("result", "")

        # Save to file or cache (same logic as normal mode)
        if output:
            output_path = Path(output)
            output_path.write_text(markdown_content)
            click.echo(f"Saved to: {output_path}", err=True)
        elif not no_cache:
            from urllib.parse import urlparse

            from inspekt.services.content_cache import ContentCache
            content_cache = ContentCache()
            parsed = urlparse(current_url)
            domain = parsed.netloc
            path = parsed.path.strip("/").replace("/", "_") or "index"
            filename = f"inspekt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{domain}_{path}.yaml"
            cache_path = Path(filename)
            cache_path.write_text(markdown_content)
            click.echo(f"Saved to: {cache_path}", err=True)
        else:
            click.echo(markdown_content)

        return  # Exit early - headless mode complete

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Load and execute the index_page script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "index_page.js"

    if not script_path.exists():
        click.echo(f"Error: Script not found: {script_path}", err=True)
        sys.exit(1)

    try:
        with builtin_open(script_path) as f:
            script = f.read()

        click.echo("Indexing page structure…", err=True)
        result = client.execute(script, timeout=30.0)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        # The script returns an object with markdown and optional largestImage
        script_result = result.get("result", {})

        # Handle both old format (string) and new format (object)
        if isinstance(script_result, str):
            # Old format: just markdown
            indexed_content = script_result
            largest_image = None
        elif isinstance(script_result, dict):
            # New format: object with markdown and largestImage
            indexed_content = script_result.get("markdown", "")
            largest_image = script_result.get("largestImage")
        else:
            click.echo("Error: Unexpected result format", err=True)
            sys.exit(1)

        if not indexed_content:
            click.echo("Error: No content indexed", err=True)
            sys.exit(1)

        # If there's a largest image, get vision AI description
        if largest_image:
            try:
                # Get AI service
                ai_service = get_ai_service()

                # Get image data URL (either from browser or download server-side)
                image_data_url = largest_image.get("dataUrl")

                # If we have a URL but no dataUrl, download and convert it
                if not image_data_url and largest_image.get("url"):
                    image_data_url = ai_service.download_and_convert_image(largest_image["url"])

                if image_data_url:
                    click.echo("Analyzing largest image with vision AI…", err=True)
                    vision_description = ai_service.get_image_description(image_data_url)
                else:
                    click.echo("Warning: No image data available for analysis", err=True)
                    vision_description = None

                if vision_description:
                    # Find the image in the markdown and add the description
                    img_alt = largest_image.get("alt", "")
                    img_width = largest_image.get("width", 0)
                    img_height = largest_image.get("height", 0)

                    click.echo(f"Inserting description for image: alt='{img_alt[:50]}…', size={img_width}x{img_height}", err=True)

                    # Create pattern to find this specific image
                    if img_alt:
                        # Image with alt text (no regex escaping needed for plain string replace)
                        pattern = f"![{img_alt}] ({img_width}x{img_height}px)"
                        replacement = f"![{img_alt}] ({img_width}x{img_height}px)\n\nVisual description of this image: \"{vision_description}\""

                        if pattern in indexed_content:
                            indexed_content = indexed_content.replace(pattern, replacement, 1)
                            click.echo(success("Vision description inserted"), err=True)
                        else:
                            click.echo(f"Warning: Could not find image pattern in markdown: {pattern}", err=True)
                    else:
                        # Image without alt text - add description at the top of main content
                        # Find where main content starts (after the "---" separator)
                        parts = indexed_content.split('---\n\n', 1)
                        if len(parts) == 2:
                            header = parts[0] + '---\n\n'
                            content = parts[1]
                            indexed_content = header + f"![Largest image on page (no alt text)] ({img_width}x{img_height}px)\n\nVisual description of this image: \"{vision_description}\"\n\n" + content
                            click.echo(success("Vision description inserted (no alt text)"), err=True)
                else:
                    click.echo("Warning: No vision description received", err=True)

            except Exception as e:
                click.echo(f"Warning: Failed to analyze image: {e}", err=True)
                # Continue without image description

        # Output to stdout
        click.echo(indexed_content)

        # Save to cache or file if requested
        if output:
            # Save to specific file
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with builtin_open(output_path, 'w', encoding='utf-8') as f:
                f.write(indexed_content)
            click.echo(f"\n{success(f'Saved to: {output_path}')}", err=True)

        elif not no_cache:
            # Save to cache directory
            # Extract URL from the indexed content
            url_match = re.search(r"\*\*URL:\*\* (.+)", indexed_content)
            current_url = url_match.group(1) if url_match else "unknown"

            # Create cache directory
            cache_dir = Path.home() / ".cache" / "inspekt" / "indexed_pages"
            cache_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename from URL (sanitize for filesystem)
            import hashlib
            url_hash = hashlib.sha256(current_url.encode()).hexdigest()[:12]

            # Also create a readable filename from URL
            from urllib.parse import urlparse
            parsed = urlparse(current_url)
            readable_name = parsed.netloc.replace(':', '_') + parsed.path.replace('/', '_')
            readable_name = re.sub(r'[^\w\-_.]', '_', readable_name)[:50]

            filename = f"{readable_name}_{url_hash}.md"
            cache_path = cache_dir / filename

            with builtin_open(cache_path, 'w', encoding='utf-8') as f:
                f.write(indexed_content)

            click.echo(f"\n{success(f'Cached to: {cache_path}')}", err=True)

            # Also save a metadata file with URL and timestamp
            import time
            metadata = {
                "url": current_url,
                "timestamp": time.time(),
                "filename": filename
            }

            metadata_path = cache_dir / f"{readable_name}_{url_hash}.json"
            with builtin_open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)

    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@click.command()
@url_scheme(
    "ask",
    exclude_params=["debug", "no_cache"],
)
@click.argument("question", type=str)
@click.option("--debug", is_flag=True, help="Show the full prompt instead of calling AI")
@click.option("--no-cache", is_flag=True, help="Force re-index instead of using cache")
def ask(question, debug, no_cache):
    """
    Ask a question about the current page using AI.

    By default, this command uses the cached index of the current page
    (created by 'inspekt index'). Use --no-cache to force re-indexing.

    The AI has access to the full semantic structure, all text content,
    interactive elements, accessible names, and vision AI descriptions.

    Examples:
        inspekt index                              # First, index the page
        inspekt ask "What is this page about?"     # Uses cache
        inspekt ask "What's the nutriscore?"       # Uses cache
        inspekt ask "What's in the image?"         # Vision description from cache
        inspekt ask "Summarize" --no-cache         # Force re-index
    """
    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code
        click.echo(_style_with_inline_code("Error: Bridge server is not running. Start it with `inspekt start`.", base_fg="red"), err=True)
        sys.exit(1)

    # Initialize content cache for AI response caching
    content_cache = ContentCache()
    indexed_content = None
    current_url = None

    # Get current URL (needed for AI response caching)
    try:
        url_script = "window.location.href"
        url_result = client.execute(url_script, timeout=5.0)
        if url_result.get("ok"):
            current_url = url_result.get("result", "")
    except Exception as e:
        click.echo(f"Warning: Could not get URL: {e}", err=True)

    # Check for cached AI response (always, regardless of --no-cache flag)
    if current_url:
        fingerprint = content_cache.create_ask_fingerprint(question)
        question_hash = content_cache.get_question_hash(question)

        cached = content_cache.get_cached_content(
            current_url, "ask", fingerprint, question_hash
        )

        if cached:
            # Found cached AI response
            age_minutes = cached["age_seconds"] // 60
            if age_minutes < 1:
                age_str = "just now"
            elif age_minutes < 60:
                age_str = f"{age_minutes}m ago"
            else:
                age_str = f"{age_minutes // 60}h ago"

            click.echo(cached_icon(f"Using cached AI response ({age_str})"), err=True)
            click.echo()
            click.echo(cached["output"])
            return

    # Try page index cache first (unless --no-cache is specified)
    if not no_cache and current_url:
        try:
            # Look for cache file matching this URL
            cache_dir = Path.home() / ".cache" / "inspekt" / "indexed_pages"

            if cache_dir.exists():
                import hashlib
                url_hash = hashlib.sha256(current_url.encode()).hexdigest()[:12]

                # Find cache file with this URL hash
                cache_files = list(cache_dir.glob(f"*_{url_hash}.md"))

                if cache_files:
                    # Use the most recent one
                    cache_file = max(cache_files, key=lambda p: p.stat().st_mtime)
                    with builtin_open(cache_file, 'r', encoding='utf-8') as f:
                        indexed_content = f.read()
                    click.echo(cached_icon("Using cached index for current page"), err=True)
                else:
                    click.echo("No cache found for current page, indexing…", err=True)
            else:
                click.echo("No cache directory, indexing…", err=True)
        except Exception as e:
            click.echo(f"Warning: Could not check cache: {e}", err=True)

    if not indexed_content:
        # Index the current page
        script_path = Path(__file__).parent.parent.parent / "scripts" / "index_page.js"

        if not script_path.exists():
            click.echo(f"Error: Script not found: {script_path}", err=True)
            sys.exit(1)

        try:
            with builtin_open(script_path) as f:
                script = f.read()

            click.echo("Indexing current page…", err=True)
            result = client.execute(script, timeout=30.0)

            if not result.get("ok"):
                click.echo(f"Error: {result.get('error')}", err=True)
                sys.exit(1)

            # Handle both old format (string) and new format (object)
            script_result = result.get("result", {})
            if isinstance(script_result, str):
                indexed_content = script_result
            elif isinstance(script_result, dict):
                indexed_content = script_result.get("markdown", "")
            else:
                click.echo("Error: Unexpected result format", err=True)
                sys.exit(1)

            if not indexed_content:
                click.echo("Error: No content indexed", err=True)
                sys.exit(1)

        except (ConnectionError, TimeoutError, RuntimeError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    # Prepare the prompt for AI
    prompt = """You are a helpful assistant that answers questions about web pages.

You will be provided with a comprehensive index of a web page that includes:
- Page structure with landmarks and headings
- Main content text
- All interactive elements (links, buttons, forms) with their accessible names
- Images with alt text
- Lists and other semantic information

Answer the user's question based ONLY on the information provided in the page index.
Be concise and accurate. If the information is not available in the index, say so.
Provide specific references when possible (e.g., "In the Main Content section…" or "The navigation includes…").

User Question: {question}

---

PAGE INDEX:

{indexed_content}
"""

    full_input = prompt.format(question=question, indexed_content=indexed_content)

    # Debug mode: show the full prompt instead of calling AI
    if debug:
        click.echo("=" * 80)
        click.echo("DEBUG: Full prompt that would be sent to AI")
        click.echo("=" * 80)
        click.echo()
        click.echo(full_input)
        click.echo()
        click.echo("=" * 80)
        return

    click.echo("Asking AI…", err=True)
    click.echo()

    # Call AI service
    ai_service = get_ai_service()
    ai_response = ai_service.call_thoth_text(full_input)
    click.echo(ai_response)

    # Store response in cache (if we have a URL)
    if current_url and not debug:
        fingerprint = content_cache.create_ask_fingerprint(question)
        question_hash = content_cache.get_question_hash(question)
        content_cache.store_content(current_url, "ask", fingerprint, ai_response, question_hash)
