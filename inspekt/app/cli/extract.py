"""
Extract command group - Extract structured content from web pages.

This module provides commands for extracting and exporting content:
- article: Extract article as Markdown with YAML frontmatter
- images: Download all images from the current page
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path

import click

from inspekt.app.cli.base import builtin_open
from inspekt.app.cli.icons import (
    analyze as analyze_icon,
)
from inspekt.app.cli.icons import (
    cached as cached_icon,
)
from inspekt.app.cli.icons import (
    get_icon,
)
from inspekt.app.cli.icons import (
    info as info_icon,
)
from inspekt.app.cli.icons import (
    progress as progress_icon,
)
from inspekt.app.cli.icons import (
    success as success_icon,
)
from inspekt.app.cli.url_builder import url_scheme
from inspekt.client import BridgeClient
from inspekt.services.content_cache import ContentCache


def _speak_text(text: str, voice_name: str, audio_output: str | None = None) -> None:
    """
    Speak text using TTS service, with support for long content and audio file output.

    Args:
        text: The text to speak.
        voice_name: Name of the voice to use, or empty string for default voice.
        audio_output: Optional path to save audio as MP3 file instead of playing.
    """
    import os

    from inspekt.config import get_tts_config
    from inspekt.services.text_splitter import (
        ELEVENLABS_CHAR_LIMIT,
        chunk_text_for_tts,
        get_text_stats,
        truncate_at_sentence_boundary,
    )
    from inspekt.services.tts_service import (
        TTSError,
        generate_audio,
        is_tts_available,
        speak_text,
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

    speak_icon = get_icon("speak") or "\U0001f50a"  # Speaker icon

    # Check if content exceeds ElevenLabs limit
    if len(text) > ELEVENLABS_CHAR_LIMIT:
        stats = get_text_stats(text)
        chunk_count = stats["chunks_needed"]

        click.echo()
        click.secho(f"Content is {len(text):,} characters", fg="yellow", err=True)
        click.echo(
            f"ElevenLabs has a {ELEVENLABS_CHAR_LIMIT:,} character limit per request.", err=True
        )
        click.echo(err=True)
        click.echo("Options:", err=True)
        click.echo("  1. Truncate at sentence boundary (one API request)", err=True)
        click.echo(
            f"  2. Split into {chunk_count} chunks (multiple requests, play sequentially)", err=True
        )
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
            # Split into chunks and process
            chunks = chunk_text_for_tts(text)
            _process_tts_chunks(chunks, voice_name, audio_output, detached)
            return
        else:
            # Cancel
            click.echo("Cancelled.", err=True)
            return

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
            click.echo(success_icon(f"Saved: {output_path}"), err=True)
        except TTSError as e:
            click.echo(click.style(f"TTS error: {e}", fg="red"), err=True)
    else:
        # Play audio
        click.echo()
        if detached:
            click.echo(f"{speak_icon} Preparing audio…", err=True)
        else:
            click.echo(f"{speak_icon} Speaking with voice '{voice_name}'…", err=True)

        try:
            speak_text(
                text,
                voice_name=voice_name,
                detached=detached,
                on_error=lambda msg: click.echo(
                    click.style(f"TTS error: {msg}", fg="red"), err=True
                ),
            )
        except TTSError as e:
            click.echo(click.style(f"TTS error: {e}", fg="red"), err=True)


def _process_tts_chunks(
    chunks: list[str],
    voice_name: str,
    audio_output: str | None,
    detached: bool,
) -> None:
    """
    Process multiple TTS chunks with prefetching for minimal gaps.

    For playback mode: Uses hybrid approach:
    - Chunk 1: Progressive streaming (speak_text) for immediate playback
    - Chunks 2+: Prefetched in background while previous chunk plays

    For file output: Uses generate_audio() to buffer audio bytes, then saves.

    Args:
        chunks: List of text chunks to convert to speech.
        voice_name: Name of the voice to use.
        audio_output: Optional path to save combined audio.
        detached: Whether to use detached playback mode.
    """
    from concurrent.futures import Future, ThreadPoolExecutor

    from inspekt.services.tts_service import TTSError, generate_audio, play_audio_bytes, speak_text

    speak_icon = get_icon("speak") or "\U0001f50a"
    all_audio_bytes: list[bytes] = []

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
            combined = b"".join(all_audio_bytes)
            output_path.write_bytes(combined)
            click.echo(success_icon(f"Saved: {output_path}"), err=True)
        return

    # PLAYBACK MODE: Hybrid prefetch approach
    # - Chunk 1: Progressive streaming for immediate playback
    # - Chunks 2+: Prefetched while previous chunk plays
    with ThreadPoolExecutor(max_workers=1) as executor:
        prefetch_future: Future | None = None

        for i, chunk in enumerate(chunks, 1):
            is_first_chunk = i == 1
            is_last_chunk = i == len(chunks)
            next_chunk = chunks[i] if not is_last_chunk else None

            click.echo(f"  Chunk {i}/{len(chunks)} ({len(chunk):,} chars)", err=True)

            if is_first_chunk:
                # First chunk: Use speak_text() for progressive streaming
                # Start prefetching chunk 2 when audio begins playing
                # Bind next_chunk at definition time: on_start fires while audio
                # plays, possibly after the loop has moved to the next chunk
                def start_prefetch(next_chunk=next_chunk):
                    nonlocal prefetch_future
                    if next_chunk:
                        prefetch_future = executor.submit(generate_audio, next_chunk, voice_name)

                try:
                    speak_text(
                        chunk,
                        voice_name=voice_name,
                        detached=detached,
                        on_start=start_prefetch,
                        on_error=lambda msg: click.echo(
                            click.style(f"    TTS error: {msg}", fg="red"), err=True
                        ),
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
                            prefetch_future = executor.submit(
                                generate_audio, next_chunk, voice_name
                            )

                        # Play the prefetched audio
                        play_audio_bytes(audio_bytes)
                    else:
                        # Fallback: no prefetch available, generate and play
                        audio_bytes = generate_audio(chunk, voice_name=voice_name)
                        play_audio_bytes(audio_bytes)

                except TTSError as e:
                    click.secho(f"    ✗ {e}", fg="red", err=True)


def _format_age(seconds: int) -> str:
    """Format age in seconds to human-readable string (e.g., '5m', '2h', '1d')."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"


def _truncate(text: str, max_len: int = 60) -> str:
    """Truncate text with ellipsis if longer than max_len."""
    if len(text) > max_len:
        return text[: max_len - 1] + "…"
    return text


@click.group()
def extract():
    """Extract structured content from web pages."""
    pass


@extract.command()
@url_scheme(
    "article",
    param_map={"output_json": "json", "no_frontmatter": "no_frontmatter"},
    defaults={
        "engine": None,
        "no_images": False,
        "flatten": False,
        "no_frontmatter": False,
        "speak": None,
    },
    exclude_params=["cache_images", "output", "force_refresh", "output_json", "verbose"],
)
@click.option(
    "--engine",
    "-e",
    type=click.Choice(["readability", "defuddle"], case_sensitive=False),
    default=None,
    help="Extraction engine (default: from config or 'readability')",
)
@click.option(
    "--cache-images",
    is_flag=True,
    help="Download and cache images locally",
)
@click.option(
    "--no-images",
    is_flag=True,
    help="Remove images from the output",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: stdout)",
)
@click.option(
    "--force-refresh",
    is_flag=True,
    help="Bypass cache, re-extract content",
)
@click.option(
    "--json",
    "-j",
    "output_json",
    is_flag=True,
    help="Output as JSON with metadata",
)
@click.option(
    "--no-frontmatter",
    is_flag=True,
    help="Skip YAML frontmatter, add title as H1 heading instead",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show extraction details (cache status, stats)",
)
@click.option(
    "--flatten",
    is_flag=True,
    help="Strip inline formatting (links, bold, italic) for TTS",
)
@click.option(
    "--speak",
    is_flag=False,
    flag_value="default",  # Use default voice from config
    default=None,
    metavar="VOICE",
    help="Read the article aloud using TTS (--speak for default voice, --speak margot for specific)",
)
def article(
    engine: str | None,
    cache_images: bool,
    no_images: bool,
    output: str | None,
    force_refresh: bool,
    output_json: bool,
    no_frontmatter: bool,
    verbose: bool,
    flatten: bool,
    speak: str | None,
):
    """
    Extract article content as Markdown with YAML frontmatter.

    Supports two extraction engines:
    - readability: Mozilla Readability (Firefox Reader View) - stable, well-tested
    - defuddle: Obsidian's modern extractor - better for SPAs, more metadata

    Examples:
        inspekt extract article                        # Use default engine
        inspekt extract article --engine defuddle      # Use Defuddle
        inspekt extract article -o article.md          # Save to file
        inspekt extract article --cache-images         # Cache images locally
        inspekt extract article --no-images            # Strip images from output
        inspekt extract article --json                 # Output as JSON
        inspekt extract article --speak margot         # Read article aloud
    """
    from inspekt.config import get_extract_config
    from inspekt.services.image_cache import ImageCache
    from inspekt.services.markdown_converter import (
        apply_extract_filters,
        clean_trailing_content,
        convert_frontmatter_to_h1,
        convert_html_to_markdown,
        flatten_inline_markdown,
        generate_frontmatter,
        replace_image_urls,
        strip_images,
    )

    # Validate mutually exclusive options
    if cache_images and no_images:
        click.echo(
            "Error: --cache-images and --no-images cannot be used together.",
            err=True,
        )
        sys.exit(1)

    # --cache-images implies --force-refresh (we need fresh HTML to get current image URLs)
    if cache_images:
        force_refresh = True

    # Determine which engine to use
    if engine is None:
        config = get_extract_config()
        engine = config.get("engine", "readability")

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code

        click.echo(
            _style_with_inline_code(
                "Error: Bridge server is not running. Start it with `inspekt start`.",
                base_fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    # Set up paths based on engine
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"

    if engine == "defuddle":
        lib_path = scripts_dir / "vendor" / "defuddle" / "defuddle.js"
        extraction_script_path = scripts_dir / "extract_article_defuddle.js"
        engine_name = "Defuddle"
        install_hint = None  # Defuddle ships with inspekt
    else:
        lib_path = scripts_dir / "vendor" / "readability" / "Readability.js"
        extraction_script_path = scripts_dir / "extract_article_readability.js"
        engine_name = "Readability"
        install_hint = "Run `inspekt update readability` to install it."

    if not lib_path.exists():
        click.echo(f"Error: {engine_name} library not found.", err=True)
        if install_hint:
            click.echo(install_hint, err=True)
        sys.exit(1)

    if not extraction_script_path.exists():
        click.echo(f"Error: Extraction script not found: {extraction_script_path}", err=True)
        sys.exit(1)

    # Get current URL for cache lookup (before extraction)
    try:
        url_result = client.execute("window.location.href", timeout=5.0)
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    current_url = url_result.get("result", "") if url_result.get("ok") else ""

    # Initialize cache
    content_cache = ContentCache()
    cached_result = None
    cache_hit = False

    # Check cache (unless force-refresh)
    if not force_refresh and current_url and content_cache.is_enabled("extract"):
        # Create a minimal fingerprint for lookup (engine is part of key)
        # We'll verify with full fingerprint after extraction
        cached_result = content_cache.get_cached_content(
            url=current_url,
            command="extract",
            current_fingerprint="",  # Will check similarity after retrieval
            language=engine,  # Use engine as "language" to separate caches
        )
        if cached_result:
            cache_hit = True

    if cache_hit and cached_result:
        # Cache hit - use cached markdown
        full_markdown = cached_result.get("output", "")

        # Show verbose cache info
        if verbose:
            age_str = _format_age(cached_result.get("age_seconds", 0))
            click.echo(
                cached_icon(f"Cache hit ({age_str} old, hit #{cached_result.get('hit_count', 1)})"),
                err=True,
            )

        # Convert frontmatter to H1 if --no-frontmatter was used
        if no_frontmatter and full_markdown.startswith("---\n"):
            full_markdown = convert_frontmatter_to_h1(full_markdown)

        # For cached results, we skip image processing
        images = []
    else:
        # Cache miss or force-refresh - do extraction
        # Get page title for progress message (only needed in verbose mode)
        page_title_for_display = None
        if verbose and not output_json:
            title_script = "document.title || window.location.hostname"
            try:
                title_result = client.execute(title_script, timeout=5.0)
                if title_result.get("ok"):
                    page_title_for_display = _truncate(title_result.get("result", ""))
            except (ConnectionError, TimeoutError, RuntimeError):
                pass  # Non-critical, continue without title

            # Show progress
            if page_title_for_display:
                click.echo(
                    analyze_icon(
                        f'Extracting article from "{page_title_for_display}" ({engine_name})…'
                    ),
                    err=True,
                )
            else:
                click.echo(analyze_icon(f"Extracting article content ({engine_name})…"), err=True)

        # Load scripts
        with builtin_open(lib_path) as f:
            lib_code = f.read()
        with builtin_open(extraction_script_path) as f:
            extraction_script = f.read()

        # Build combined script with ASI protection (parentheses around return value)
        script = f"""(function() {{
try {{
{lib_code}
return ({extraction_script})
}} catch (outerError) {{
  return {{ error: 'Extraction error: ' + outerError.message }};
}}
}})()"""

        # Execute extraction
        try:
            result = client.execute(script, timeout=30.0)
        except (ConnectionError, TimeoutError, RuntimeError) as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        if not result.get("ok"):
            click.echo(f"Error: {result.get('error')}", err=True)
            sys.exit(1)

        article_data = result.get("result") or {}

        if article_data.get("error"):
            click.echo(f"Error: {article_data['error']}", err=True)
            sys.exit(1)

        html_content = article_data.get("htmlContent", "")
        if not html_content:
            click.echo(
                "Error: No HTML content extracted. This page may not be an article.",
                err=True,
            )
            sys.exit(1)

        # Convert HTML to Markdown
        extraction_url = article_data.get("url", current_url)
        markdown_body, images = convert_html_to_markdown(html_content, base_url=extraction_url)

        # Handle image caching if requested
        cached_paths: dict[str, Path | None] = {}
        if cache_images and images:
            if verbose and not output_json:
                click.echo(progress_icon(f"Caching {len(images)} images…"), err=True)

            image_cache = ImageCache()
            image_urls = [img["src"] for img in images if img["src"]]

            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in image_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)

            # Per-image progress only in verbose mode
            progress_callback = None
            if verbose and not output_json:

                def on_progress(url: str, success: bool, current: int, total: int):
                    status = click.style("✓", fg="green") if success else click.style("✗", fg="red")
                    display_url = _truncate(url, 70)
                    click.echo(f"  {status} [{current}/{total}] {display_url}", err=True)

                progress_callback = on_progress

            cached_paths = image_cache.download_batch(unique_urls, on_progress=progress_callback)

            # Replace URLs in markdown with local paths
            url_mapping = {url: str(path) for url, path in cached_paths.items() if path is not None}
            markdown_body = replace_image_urls(markdown_body, url_mapping)

            # Count successes
            successes = sum(1 for p in cached_paths.values() if p is not None)
            if not output_json:
                click.echo(success_icon(f"Cached {successes}/{len(unique_urls)} images"), err=True)

        # Apply post-processing filters (removes reading time, share buttons, etc.)
        markdown_body = apply_extract_filters(markdown_body)

        # Clean up trailing content (empty lines and orphaned headings)
        markdown_body = clean_trailing_content(markdown_body)

        # Generate header (frontmatter or H1)
        if no_frontmatter:
            # Add title as H1 heading instead of frontmatter
            title = article_data.get("title", "").strip()
            if title:
                full_markdown = f"# {title}\n\n{markdown_body}"
            else:
                full_markdown = markdown_body
        else:
            # Generate YAML frontmatter
            frontmatter = generate_frontmatter(article_data)
            full_markdown = frontmatter + markdown_body

        # Store in cache (don't cache if images were downloaded - they have local paths)
        if current_url and content_cache.is_enabled("extract") and not cache_images:
            fingerprint = content_cache.create_extract_fingerprint(article_data, engine)
            content_cache.store_content(
                url=current_url,
                command="extract",
                fingerprint=fingerprint,
                output=full_markdown,
                language=engine,  # Use engine as "language" to separate caches
            )

        # Show verbose extraction stats
        if verbose:
            word_count = len(markdown_body.split())
            char_count = len(markdown_body)
            image_count = len(images)
            article_title = article_data.get("title", "Untitled")
            author = article_data.get("byline", "")

            click.echo(info_icon(f"Extracted: {_truncate(article_title)}"), err=True)
            stats_parts = [f"{word_count:,} words", f"{char_count:,} chars"]
            if image_count:
                stats_parts.append(f"{image_count} images")
            if author:
                stats_parts.append(f"by {author}")
            click.echo(f"  {' · '.join(stats_parts)}", err=True)

    # Strip images if requested
    if no_images:
        full_markdown = strip_images(full_markdown)

    # Flatten inline formatting for TTS
    if flatten:
        full_markdown = flatten_inline_markdown(full_markdown)

    # Output
    if output_json:
        if cache_hit:
            # For cache hits, we don't have article_data, so parse from markdown
            json_output = {
                "markdown": full_markdown,
                "metadata": {},
                "stats": {
                    "content_length": len(full_markdown),
                    "image_count": 0,
                },
                "engine": engine,
                "cached": True,
            }
        else:
            # Build JSON output from fresh extraction
            json_output = {
                "markdown": full_markdown,
                "metadata": {
                    "title": article_data.get("title"),
                    "author": article_data.get("byline"),
                    "date": article_data.get("publishedDate"),
                    "url": article_data.get("url"),
                    "siteName": article_data.get("siteName"),
                    "lang": article_data.get("lang"),
                },
                "stats": {
                    "content_length": len(markdown_body),
                    "image_count": len(images),
                },
                "engine": engine,
                "cached": False,
            }

            if cache_images:
                json_output["images"] = [
                    {
                        "src": img["src"],
                        "alt": img["alt"],
                        "cached": str(cached_paths.get(img["src"]))
                        if cached_paths.get(img["src"])
                        else None,
                    }
                    for img in images
                ]
                json_output["stats"]["images_cached"] = sum(
                    1 for p in cached_paths.values() if p is not None
                )

        from inspekt.app.cli.table import print_json

        print_json(json_output, summary="extracted article")

    elif output:
        output_path = Path(output)

        # Smart output detection by extension
        audio_extensions = {".mp3", ".wav", ".m4a", ".aac"}
        is_audio_output = output_path.suffix.lower() in audio_extensions

        if is_audio_output:
            # Audio output - generate TTS and save to file
            # Use speak voice if provided, otherwise default
            voice = speak if speak else "default"

            # Prepare text for TTS
            from inspekt.services.markdown_converter import flatten_inline_markdown

            tts_text = flatten_inline_markdown(full_markdown)
            # Remove frontmatter for TTS
            if tts_text.startswith("---\n"):
                end_idx = tts_text.find("\n---\n", 4)
                if end_idx > 0:
                    tts_text = tts_text[end_idx + 5 :].strip()

            _speak_text(tts_text, voice, audio_output=str(output_path))
        else:
            # Text/markdown output
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with builtin_open(output_path, "w", encoding="utf-8") as f:
                f.write(full_markdown)
            click.echo(success_icon(f"Saved to: {output_path}"), err=True)

            # Also speak if --speak was provided
            if speak:
                from inspekt.services.markdown_converter import flatten_inline_markdown

                tts_text = flatten_inline_markdown(full_markdown)
                # Remove frontmatter for TTS
                if tts_text.startswith("---\n"):
                    end_idx = tts_text.find("\n---\n", 4)
                    if end_idx > 0:
                        tts_text = tts_text[end_idx + 5 :].strip()
                _speak_text(tts_text, speak)

    else:
        # Output to stdout
        click.echo(full_markdown)

        # Speak the article if --speak is provided
        if speak:
            # For TTS, strip markdown formatting and use plain text
            from inspekt.services.markdown_converter import flatten_inline_markdown

            tts_text = flatten_inline_markdown(full_markdown)
            # Remove frontmatter for TTS
            if tts_text.startswith("---\n"):
                end_idx = tts_text.find("\n---\n", 4)
                if end_idx > 0:
                    tts_text = tts_text[end_idx + 5 :].strip()
            _speak_text(tts_text, speak)


@extract.command()
@click.option(
    "--output-dir",
    "-d",
    type=click.Path(file_okay=False),
    help="Output directory (default: ~/Downloads/{domain}/images/)",
)
@click.option(
    "--optimize",
    is_flag=True,
    help="Optimize images: convert JPG to WebP, optimize PNG with oxipng",
)
@click.option(
    "--resize-to-width",
    type=int,
    default=None,
    help="Resize images to max width in pixels (only downscales, never upscales)",
)
@click.option(
    "--resize-to-height",
    type=int,
    default=None,
    help="Resize images to max height in pixels (only downscales, never upscales)",
)
@click.option(
    "--min-width",
    type=int,
    default=0,
    help="Skip images narrower than this (pixels)",
)
@click.option(
    "--max-width",
    type=int,
    default=None,
    help="Skip images wider than this (pixels)",
)
@click.option(
    "--min-height",
    type=int,
    default=0,
    help="Skip images shorter than this (pixels)",
)
@click.option(
    "--max-height",
    type=int,
    default=None,
    help="Skip images taller than this (pixels)",
)
@click.option(
    "--prefer-best-quality",
    is_flag=True,
    help="Download highest resolution from srcset instead of default src",
)
@click.option(
    "--include-background-images",
    is_flag=True,
    help="Also extract CSS background images",
)
@click.option(
    "--rich-output",
    is_flag=True,
    help="Generate HTML gallery with lightbox",
)
@click.option(
    "--thumbnail-width",
    type=int,
    default=300,
    help="Thumbnail width for gallery (default: 300px)",
)
@click.option(
    "--json",
    "-j",
    "output_json",
    is_flag=True,
    help="Output results as JSON",
)
@click.option(
    "--open",
    "open_dir",
    is_flag=True,
    help="Open output directory after download",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress progress output",
)
@click.option(
    "--force-refresh",
    is_flag=True,
    help="Re-download images even if they already exist locally",
)
def images(
    output_dir: str | None,
    optimize: bool,
    resize_to_width: int | None,
    resize_to_height: int | None,
    min_width: int,
    max_width: int | None,
    min_height: int,
    max_height: int | None,
    prefer_best_quality: bool,
    include_background_images: bool,
    rich_output: bool,
    thumbnail_width: int,
    output_json: bool,
    open_dir: bool,
    quiet: bool,
    force_refresh: bool,
):
    """
    Download all images from the current page.

    Images are saved to ~/Downloads/{domain}/images/ by default.
    Supports filtering by dimensions, optimization, and HTML gallery generation.

    Images that already exist in the output directory (by filename) are skipped
    unless --force-refresh is used.

    \b
    Examples:
        inspekt extract images                       # Download all images
        inspekt extract images --rich-output         # Create HTML gallery with lightbox
        inspekt extract images --force-refresh       # Re-download all images
        inspekt extract images --optimize            # Optimize during download
        inspekt extract images --min-width 200       # Skip small images
        inspekt extract images --prefer-best-quality # Get highest resolution from srcset
        inspekt extract images --resize-to-width 800 # Resize large images
    """
    import io
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from urllib.parse import unquote, urlparse

    import requests
    from PIL import Image

    from inspekt.app.cli.icons import warning as warning_icon
    from inspekt.app.cli.save import extract_domain_from_url, sanitize_filename
    from inspekt.app.cli.table import print_hint
    from inspekt.config import get_paths_config
    from inspekt.services.html_image_optimizer import optimize_image as optimize_image_bytes
    from inspekt.services.image_gallery import GalleryImage, generate_gallery_html
    from inspekt.services.image_optimizer import is_oxipng_installed

    # Validate mutually exclusive options
    if resize_to_width and resize_to_height:
        click.echo(
            "Error: --resize-to-width and --resize-to-height cannot be used together.",
            err=True,
        )
        sys.exit(1)

    client = BridgeClient()

    if not client.is_alive():
        from inspekt.app.cli.table import _style_with_inline_code

        click.echo(
            _style_with_inline_code(
                "Error: Bridge server is not running. Start it with `inspekt start`.",
                base_fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    # Load and execute the extraction script
    scripts_dir = Path(__file__).parent.parent.parent / "scripts"
    script_path = scripts_dir / "extract_images.js"

    if not script_path.exists():
        click.echo(f"Error: Extraction script not found: {script_path}", err=True)
        sys.exit(1)

    with builtin_open(script_path) as f:
        extraction_script = f.read()

    # Build script with configuration
    config_json = json.dumps({"includeBackgroundImages": include_background_images})
    script = f"({extraction_script})({config_json})"

    if not quiet:
        click.echo(analyze_icon("Extracting images from page…"), err=True)

    try:
        result = client.execute(script, timeout=30.0)
    except (ConnectionError, TimeoutError, RuntimeError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    if not result.get("ok"):
        click.echo(f"Error: {result.get('error')}", err=True)
        sys.exit(1)

    data = result.get("result") or {}

    if data.get("error"):
        click.echo(f"Error: {data['error']}", err=True)
        sys.exit(1)

    all_images = data.get("images", [])
    page_url = data.get("pageUrl", "")
    page_title = data.get("pageTitle", "")

    # Guard against extracting from Inspekt's own pages (galleries, reports,
    # dashboard, …). The VM web root serves galleries at http://inspekt/images/
    # so re-extracting would nest galleries inside galleries.
    page_host = urlparse(page_url).hostname if page_url else None
    if page_host == "inspekt":
        click.echo(
            "Refusing to extract images from an Inspekt page "
            f"({page_url}). Navigate to a real website first.",
            err=True,
        )
        sys.exit(1)

    if not all_images:
        click.echo("No images found on this page.", err=True)
        sys.exit(0)

    if not quiet:
        data_uri_count = data.get("dataUriCount", 0)
        external_count = data.get("externalCount", 0)
        click.echo(
            f"  Found {len(all_images)} images ({external_count} external, {data_uri_count} data URIs)",
            err=True,
        )

    # Filter images by dimensions
    def passes_dimension_filter(img: dict) -> bool:
        """Check if image passes dimension filters."""
        # Use natural dimensions if available, otherwise use displayed
        width = img.get("naturalWidth") or img.get("displayedWidth") or 0
        height = img.get("naturalHeight") or img.get("displayedHeight") or 0

        # Skip if dimensions are unknown and filters are set
        if (
            (min_width > 0 or max_width or min_height > 0 or max_height)
            and width == 0
            and height == 0
        ):
            return True  # Include unknowns, let download determine size

        if min_width > 0 and width < min_width:
            return False
        if max_width and width > max_width:
            return False
        if min_height > 0 and height < min_height:
            return False
        return not (max_height and height > max_height)

    filtered_images = [img for img in all_images if passes_dimension_filter(img)]

    # Blob URIs can't be dereferenced server-side — browser-only scheme. Skip.
    # Data URIs are decoded inline in download_image() below.
    external_images = [img for img in filtered_images if not img.get("isBlobUri")]

    if not external_images:
        click.echo("No downloadable images after filtering.", err=True)
        sys.exit(0)

    skipped_count = len(all_images) - len(external_images)
    if skipped_count > 0 and not quiet:
        click.echo(f"  Skipped {skipped_count} images (filtered or blob URIs)", err=True)

    # Determine output directory. When running inside the VM and generating
    # a rich gallery without an explicit --output-dir, drop the artifact into
    # the VM web root so it can be opened as a virtual tab at
    # http://inspekt/images/<domain>/ instead of being zipped + downloaded.
    from inspekt.config import is_isolated_mode

    domain = extract_domain_from_url(page_url)
    www_images_root = Path("/home/inspekt/www/images")
    www_root_mode = (
        rich_output
        and not output_dir
        and is_isolated_mode()
        and bool(domain)
        and www_images_root.parent.exists()
    )

    if output_dir:
        output_path = Path(output_dir).expanduser()
    elif www_root_mode:
        output_path = www_images_root / domain
    else:
        paths = get_paths_config()
        downloads_dir = paths["downloads"]
        if domain:
            output_path = downloads_dir / domain / "images"
        else:
            output_path = downloads_dir / "images"

    output_path.mkdir(parents=True, exist_ok=True)

    # Create thumbnails directory if needed
    thumbs_dir = output_path / "thumbnails" if rich_output else None
    if thumbs_dir:
        thumbs_dir.mkdir(parents=True, exist_ok=True)

    # Thread-safe tracking for duplicate detection
    seen_hashes: set[str] = set()
    seen_hashes_lock = threading.Lock()

    # Download and process images
    def download_image(img: dict) -> dict:
        """Download a single image and optionally process it."""
        # Choose URL based on prefer-best-quality flag
        url = img.get("bestQualitySrc") if prefer_best_quality else img.get("src")
        if not url:
            return {"success": False, "error": "No URL", "img": img}

        is_data_uri = bool(img.get("isDataUri"))

        _MIME_TO_EXT = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
            "image/avif": ".avif",
            "image/bmp": ".bmp",
            "image/x-icon": ".ico",
        }

        data_uri_bytes = None
        if is_data_uri:
            # Decode up-front so the filename can include the content hash and
            # the correct mime-derived extension. The same bytes feed the main
            # processing path further down.
            from inspekt.services.html_image_optimizer import parse_data_uri

            parsed = parse_data_uri(url)
            if not parsed:
                return {"success": False, "error": "Malformed data URI", "img": img}
            mime_type, data_uri_bytes = parsed
            data_ext = _MIME_TO_EXT.get(mime_type, ".bin")
            data_hash = hashlib.sha256(data_uri_bytes).hexdigest()[:12]
            original_filename = f"data_{data_hash}{data_ext}"
        else:
            # Generate filename
            original_filename = img.get("filename")
            if not original_filename:
                # Generate from URL hash
                parsed = urlparse(url)
                path_parts = parsed.path.split("/")
                original_filename = path_parts[-1] if path_parts else "image"
                if not original_filename or original_filename == "":
                    url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]
                    original_filename = f"image_{url_hash}.jpg"

            # URL-decode filename (converts %20 to spaces, etc.)
            original_filename = unquote(original_filename)

        # Clean filename (converts spaces to underscores, removes invalid chars)
        safe_filename = sanitize_filename(Path(original_filename).stem, max_length=80)
        extension = Path(original_filename).suffix.lower() or ".jpg"

        # Check if file already exists (cache check)
        final_path = output_path / f"{safe_filename}{extension}"

        if final_path.exists() and not force_refresh:
            # File already cached - return cached result
            try:
                file_size = final_path.stat().st_size
                pil_image = Image.open(final_path)
                actual_width, actual_height = pil_image.size
                pil_image.close()

                # Check if thumbnail exists too (for rich output)
                thumb_path = None
                if thumbs_dir:
                    potential_thumb = thumbs_dir / f"thumb_{final_path.stem}.webp"
                    if potential_thumb.exists():
                        thumb_path = potential_thumb

                cached_url = url[:60] + "…" if is_data_uri and len(url) > 60 else url
                return {
                    "success": True,
                    "cached": True,
                    "path": final_path,
                    "thumb_path": thumb_path,
                    "filename": final_path.name,
                    "width": actual_width,
                    "height": actual_height,
                    "file_size": file_size,
                    "alt": img.get("alt", ""),
                    "title": img.get("title", ""),
                    "original_url": cached_url,
                    "was_resized": False,
                    "was_optimized": False,
                    # Data URIs are never publicly reachable; for normal URLs,
                    # unknown — if VM rich-output needs this it fills in via
                    # a HEAD probe after the download loop.
                    "publicly_reachable": False if is_data_uri else None,
                    "img": img,
                }
            except Exception:
                pass  # If we can't read cached file, re-download it

        # Ensure unique filename if file exists (only relevant with --force-refresh)
        if final_path.exists():
            counter = 1
            while final_path.exists():
                final_path = output_path / f"{safe_filename}_{counter}{extension}"
                counter += 1

        try:
            if is_data_uri:
                image_bytes = data_uri_bytes
            else:
                response = requests.get(
                    url,
                    timeout=30.0,
                    stream=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    },
                )
                response.raise_for_status()
                image_bytes = response.content

            # Check for duplicate content
            content_hash = hashlib.md5(image_bytes).hexdigest()
            with seen_hashes_lock:
                if content_hash in seen_hashes:
                    return {
                        "success": False,
                        "error": "Duplicate",
                        "img": img,
                        "is_duplicate": True,
                    }
                seen_hashes.add(content_hash)

            # Get actual dimensions from image
            actual_width = 0
            actual_height = 0
            try:
                pil_image = Image.open(io.BytesIO(image_bytes))
                actual_width, actual_height = pil_image.size
            except Exception:
                pass

            # Check dimension filters again with actual dimensions
            if min_width > 0 and actual_width < min_width:
                return {"success": False, "error": "Too narrow", "img": img}
            if max_width and actual_width > max_width:
                return {"success": False, "error": "Too wide", "img": img}
            if min_height > 0 and actual_height < min_height:
                return {"success": False, "error": "Too short", "img": img}
            if max_height and actual_height > max_height:
                return {"success": False, "error": "Too tall", "img": img}

            # Resize if requested
            target_width = resize_to_width
            target_height = resize_to_height
            was_resized = False

            if target_width or target_height:
                try:
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    orig_w, orig_h = pil_image.size

                    # Convert palette images with transparency to RGBA before resize
                    if pil_image.mode == "P" and "transparency" in pil_image.info:
                        pil_image = pil_image.convert("RGBA")

                    if target_width and orig_w > target_width:
                        ratio = target_width / orig_w
                        new_h = int(orig_h * ratio)
                        pil_image = pil_image.resize(
                            (target_width, new_h), Image.Resampling.LANCZOS
                        )
                        was_resized = True
                        actual_width, actual_height = target_width, new_h
                    elif target_height and orig_h > target_height:
                        ratio = target_height / orig_h
                        new_w = int(orig_w * ratio)
                        pil_image = pil_image.resize(
                            (new_w, target_height), Image.Resampling.LANCZOS
                        )
                        was_resized = True
                        actual_width, actual_height = new_w, target_height

                    if was_resized:
                        output_buffer = io.BytesIO()
                        fmt = "PNG" if extension.lower() == ".png" else "JPEG"
                        pil_image.save(output_buffer, format=fmt, quality=85)
                        image_bytes = output_buffer.getvalue()
                except Exception:
                    pass  # Keep original if resize fails

            # Optimize if requested
            was_optimized = False
            if optimize:
                mime_type = (
                    "image/jpeg"
                    if extension.lower() in (".jpg", ".jpeg")
                    else f"image/{extension[1:]}"
                )
                try:
                    optimized_bytes, new_mime = optimize_image_bytes(
                        image_bytes,
                        mime_type,
                        target_width=None,  # Already resized above
                        webp_quality=85,
                        optimize_png=is_oxipng_installed(),
                    )
                    if len(optimized_bytes) < len(image_bytes):
                        image_bytes = optimized_bytes
                        was_optimized = True
                        # Update extension if converted to webp
                        if new_mime == "image/webp" and extension.lower() not in (".webp",):
                            final_path = final_path.with_suffix(".webp")
                except Exception:
                    pass  # Keep original if optimization fails

            # Write to file
            with open(final_path, "wb") as f:
                f.write(image_bytes)

            file_size = len(image_bytes)

            # Generate thumbnail if needed
            thumb_path = None
            if thumbs_dir:
                try:
                    pil_image = Image.open(io.BytesIO(image_bytes))
                    orig_w, orig_h = pil_image.size

                    # Convert palette images with transparency to RGBA first
                    if pil_image.mode == "P" and "transparency" in pil_image.info:
                        pil_image = pil_image.convert("RGBA")

                    # Calculate thumbnail size
                    ratio = min(thumbnail_width / orig_w, thumbnail_width / orig_h)
                    if ratio < 1:
                        new_size = (int(orig_w * ratio), int(orig_h * ratio))
                        pil_image = pil_image.resize(new_size, Image.Resampling.LANCZOS)

                    thumb_filename = f"thumb_{final_path.stem}.webp"
                    thumb_path = thumbs_dir / thumb_filename

                    # Convert to RGB for WebP output
                    if pil_image.mode == "RGBA":
                        background = Image.new("RGB", pil_image.size, (255, 255, 255))
                        background.paste(pil_image, mask=pil_image.split()[3])
                        pil_image = background
                    elif pil_image.mode not in ("RGB", "L"):
                        pil_image = pil_image.convert("RGB")

                    pil_image.save(thumb_path, "WEBP", quality=80)
                except Exception:
                    thumb_path = None  # Use original as thumbnail

            # Data URIs can't be "fetched" from outside, so mark unreachable
            # and store a truncated marker instead of the full base64 blob.
            if is_data_uri:
                stored_url = url[:60] + "…" if len(url) > 60 else url
                publicly_reachable = False
            else:
                # Just fetched successfully with no cookies/auth/referer,
                # so the URL is reachable from any client that can speak HTTP.
                stored_url = url
                publicly_reachable = True

            return {
                "success": True,
                "path": final_path,
                "thumb_path": thumb_path,
                "filename": final_path.name,
                "width": actual_width,
                "height": actual_height,
                "file_size": file_size,
                "alt": img.get("alt", ""),
                "title": img.get("title", ""),
                "original_url": stored_url,
                "was_resized": was_resized,
                "was_optimized": was_optimized,
                "publicly_reachable": publicly_reachable,
                "img": img,
            }

        except requests.exceptions.RequestException as e:
            return {"success": False, "error": str(e), "img": img}
        except Exception as e:
            return {"success": False, "error": str(e), "img": img}

    # Download images in parallel
    results = []
    failed_count = 0
    total = len(external_images)

    if not quiet:
        click.echo(progress_icon(f"Downloading {total} images…"), err=True)

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_img = {executor.submit(download_image, img): img for img in external_images}

        for i, future in enumerate(as_completed(future_to_img), 1):
            result = future.result()
            results.append(result)

            if not quiet:
                if result["success"]:
                    filename = result["filename"]
                    extras = []
                    if result.get("cached"):
                        # Cached image - show with cyan color and cached indicator
                        status = click.style("●", fg="cyan")
                        extras.append("cached")
                    else:
                        # Freshly downloaded
                        status = click.style("✓", fg="green")
                        if result.get("was_resized"):
                            extras.append("resized")
                        if result.get("was_optimized"):
                            extras.append("optimized")
                    extra_str = f" ({', '.join(extras)})" if extras else ""
                    click.echo(f"  {status} [{i}/{total}] {filename}{extra_str}", err=True)
                elif result.get("is_duplicate"):
                    status = click.style("≡", fg="yellow")
                    filename = result["img"].get("filename") or "image"
                    click.echo(
                        f"  {status} [{i}/{total}] {filename} (duplicate, skipped)", err=True
                    )
                else:
                    status = click.style("✗", fg="red")
                    error = result.get("error", "Unknown error")[:50]
                    url = result["img"].get("src", "unknown")[:50]
                    click.echo(f"  {status} [{i}/{total}] {url} - {error}", err=True)
                    failed_count += 1

    # Count successes, cached, and duplicates
    successful = [r for r in results if r["success"]]
    cached = [r for r in successful if r.get("cached")]
    downloaded = [r for r in successful if not r.get("cached")]
    duplicates = [r for r in results if r.get("is_duplicate")]
    success_count = len(successful)
    cached_count = len(cached)
    downloaded_count = len(downloaded)
    duplicate_count = len(duplicates)

    # Calculate total size
    total_size = sum(r.get("file_size", 0) for r in successful)
    total_size_str = _format_size(total_size)

    if not quiet:
        click.echo("", err=True)
        extras = []
        if cached_count > 0:
            extras.append(f"{cached_count} cached")
        if duplicate_count > 0:
            extras.append(f"{duplicate_count} duplicates")
        if failed_count > 0:
            extras.append(f"{failed_count} failed")

        if cached_count == success_count and success_count > 0:
            # All images were cached
            click.echo(
                cached_icon(f"All {success_count} images already cached"),
                err=True,
            )
        elif extras:
            click.echo(
                warning_icon(f"Downloaded {downloaded_count}/{total} images ({', '.join(extras)})"),
                err=True,
            )
        else:
            click.echo(success_icon(f"Downloaded {success_count} images"), err=True)
        click.echo(f"  {total_size_str} total · {output_path}", err=True)

    # Generate HTML gallery if requested
    if rich_output and successful:
        gallery_images = []
        for r in successful:
            # Read SVG content for code preview (SVG files only, max 5KB)
            svg_content = None
            file_path = r["path"]
            if file_path.suffix.lower() == ".svg":
                try:
                    content = file_path.read_text(encoding="utf-8")
                    # Only embed if under 10KB to avoid bloating HTML
                    if len(content) <= 10000:
                        # Pretty-print SVG with proper indentation
                        try:
                            import warnings

                            from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

                            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
                            # Try xml parser (requires lxml), fall back to html.parser
                            try:
                                soup = BeautifulSoup(content, "xml")
                            except Exception:
                                soup = BeautifulSoup(content, "html.parser")
                            svg_content = soup.prettify()
                        except Exception:
                            # If prettify fails, use raw content
                            svg_content = content
                except Exception:
                    pass  # Skip if can't read

            js_img = r.get("img") or {}
            gallery_images.append(
                GalleryImage(
                    filename=r["filename"],
                    file_path=r["path"],
                    thumbnail_path=r.get("thumb_path"),
                    width=r.get("width", 0),
                    height=r.get("height", 0),
                    file_size=r.get("file_size", 0),
                    alt=r.get("alt", ""),
                    title=r.get("title", ""),
                    original_url=r.get("original_url", ""),
                    is_optimized=r.get("was_optimized", False),
                    svg_content=svg_content,
                    source_type=js_img.get("sourceType", "img"),
                    accessible_name=js_img.get("accessibleName", ""),
                    accessible_name_source=js_img.get("accessibleNameSource", "alt attribute"),
                    is_linked=bool(js_img.get("isLinked", False)),
                    link_href=js_img.get("linkHref", ""),
                    nearest_heading_text=js_img.get("nearestHeadingText", ""),
                )
            )

        from inspekt.config import is_isolated_mode

        vm_bundle = is_isolated_mode()

        if vm_bundle:
            # HEAD-probe cached images to determine which originals are still
            # publicly reachable; downloaded ones already know from their GET.
            unknown_idx = [
                i
                for i, r in enumerate(successful)
                if r.get("publicly_reachable") is None and r.get("original_url")
            ]

            def _probe(url: str) -> bool:
                try:
                    resp = requests.head(
                        url,
                        timeout=5.0,
                        allow_redirects=True,
                        headers={"Referer": page_url} if page_url else None,
                    )
                    if resp.status_code == 405:
                        resp = requests.get(
                            url,
                            timeout=5.0,
                            stream=True,
                            headers={"Referer": page_url} if page_url else None,
                        )
                        resp.close()
                    return 200 <= resp.status_code < 400
                except requests.exceptions.RequestException:
                    return False

            if unknown_idx:
                with ThreadPoolExecutor(max_workers=8) as probe_pool:
                    futures = {
                        probe_pool.submit(_probe, successful[i]["original_url"]): i
                        for i in unknown_idx
                    }
                    for fut in as_completed(futures):
                        successful[futures[fut]]["publicly_reachable"] = fut.result()

            # Inline thumbnails as data URIs and set full_src override per image.
            import base64
            import mimetypes

            for gimg, r in zip(gallery_images, successful, strict=False):
                thumb_path = r.get("thumb_path")
                if thumb_path and thumb_path.exists():
                    thumb_bytes = thumb_path.read_bytes()
                    thumb_mime = mimetypes.guess_type(thumb_path.name)[0] or "image/webp"
                    gimg.thumbnail_data_uri = f"data:{thumb_mime};base64," + base64.b64encode(
                        thumb_bytes
                    ).decode("ascii")
                if r.get("publicly_reachable") and r.get("original_url"):
                    gimg.full_src_override = r["original_url"]

        gallery_html = generate_gallery_html(
            images=gallery_images,
            page_title=page_title,
            page_url=page_url,
            output_dir=output_path,
        )

        # In www-root mode the file must be named index.html so StaticFiles
        # (html=True) serves it for http://inspekt/images/<domain>/ without a
        # trailing filename. Legacy paths keep the historical gallery.html.
        gallery_filename = "index.html" if www_root_mode else "gallery.html"
        gallery_path = output_path / gallery_filename
        with open(gallery_path, "w", encoding="utf-8") as f:
            f.write(gallery_html)

        if not quiet:
            click.echo(success_icon(f"Gallery created: {gallery_path}"), err=True)

        if www_root_mode:
            from inspekt.app.cli.util import open_in_tab

            open_in_tab(f"http://inspekt/images/{domain}/")
        else:
            from inspekt.app.cli.util import open_or_download

            if vm_bundle:
                # Build /tmp/gallery-{domain}.zip containing gallery.html plus any
                # originals that weren't publicly reachable (so the host can open
                # it offline). Publicly reachable ones are referenced by URL.
                import zipfile

                zip_domain = extract_domain_from_url(page_url) or "gallery"
                zip_path = Path(f"/tmp/gallery-{sanitize_filename(zip_domain, max_length=80)}.zip")
                zip_path.unlink(missing_ok=True)

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.write(gallery_path, arcname="gallery.html")
                    for r in successful:
                        if not r.get("publicly_reachable"):
                            file_path = r["path"]
                            if file_path.exists():
                                zf.write(file_path, arcname=file_path.name)

                if not quiet:
                    bundled = sum(1 for r in successful if not r.get("publicly_reachable"))
                    linked = len(successful) - bundled
                    click.echo(
                        success_icon(
                            f"Packaged gallery: {bundled} bundled, {linked} linked · "
                            f"{_format_size(zip_path.stat().st_size)}"
                        ),
                        err=True,
                    )
                open_or_download(zip_path)
            else:
                # Open gallery in browser
                open_or_download(gallery_path)

    if not quiet and not rich_output:
        print_hint("Use --rich-output to generate an HTML gallery with lightbox")

    # Output JSON if requested
    if output_json:
        json_output = {
            "page_url": page_url,
            "page_title": page_title,
            "output_dir": str(output_path),
            "total_found": len(all_images),
            "downloaded": downloaded_count,
            "cached": cached_count,
            "duplicates": duplicate_count,
            "failed": failed_count,
            "total_size_bytes": total_size,
            "images": [
                {
                    "filename": r["filename"],
                    "path": str(r["path"]),
                    "width": r.get("width", 0),
                    "height": r.get("height", 0),
                    "file_size": r.get("file_size", 0),
                    "alt": r.get("alt", ""),
                    "original_url": r.get("original_url", ""),
                    "was_resized": r.get("was_resized", False),
                    "was_optimized": r.get("was_optimized", False),
                    "was_cached": r.get("cached", False),
                }
                for r in successful
            ],
        }
        if rich_output:
            json_output["gallery_path"] = str(gallery_path)
            if www_root_mode:
                json_output["gallery_url"] = f"http://inspekt/images/{domain}/"

        from inspekt.app.cli.table import print_json

        count = json_output.get("downloaded", len(json_output.get("images", [])))
        print_json(json_output, summary=f"{count} images")

    # Open directory if requested
    if open_dir:
        from inspekt.app.cli.util import reveal_or_download

        reveal_or_download(output_path)


def _format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
