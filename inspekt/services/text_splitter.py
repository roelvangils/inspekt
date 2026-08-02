"""
Text splitting utilities for TTS processing.

This module provides utilities to split long text into chunks that fit
within API character limits (like ElevenLabs' 5000 character limit).
"""

from __future__ import annotations

import re

# ElevenLabs character limit per request
ELEVENLABS_CHAR_LIMIT = 5000


def split_sentences(text: str) -> list[str]:
    """
    Split text into sentences using regex-based boundary detection.

    Handles common sentence-ending punctuation (.!?) followed by whitespace.
    Preserves the punctuation with the sentence it ends.

    Args:
        text: The text to split into sentences.

    Returns:
        List of sentences (including trailing punctuation).
    """
    # Split on sentence-ending punctuation followed by whitespace
    # The pattern captures the punctuation so we can keep it
    # Handles: "Hello. World" -> ["Hello.", "World"]
    # Also handles: "Hello!  World" and "Hello?\nWorld"
    pattern = r"(?<=[.!?])\s+"

    sentences = re.split(pattern, text.strip())

    # Filter out empty strings
    return [s.strip() for s in sentences if s.strip()]


def chunk_text_for_tts(
    text: str,
    max_chars: int = ELEVENLABS_CHAR_LIMIT,
) -> list[str]:
    """
    Split text into chunks that fit within the character limit.

    Always splits at sentence boundaries to ensure natural pauses.
    Each chunk will be at most max_chars characters.

    Args:
        text: The text to split into chunks.
        max_chars: Maximum characters per chunk (default: 5000).

    Returns:
        List of text chunks, each within the character limit.
    """
    sentences = split_sentences(text)
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for sentence in sentences:
        sentence_length = len(sentence)

        # If a single sentence exceeds the limit, we need to split it
        # This is a fallback for extremely long sentences
        if sentence_length > max_chars:
            # First, flush the current chunk if any
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0

            # Split the long sentence by words
            chunks.extend(_split_long_sentence(sentence, max_chars))
            continue

        # Check if adding this sentence would exceed the limit
        # Account for space between sentences
        space_needed = 1 if current_chunk else 0
        if current_length + space_needed + sentence_length > max_chars:
            # Flush current chunk and start a new one
            if current_chunk:
                chunks.append(" ".join(current_chunk))
            current_chunk = [sentence]
            current_length = sentence_length
        else:
            # Add to current chunk
            current_chunk.append(sentence)
            current_length += space_needed + sentence_length

    # Don't forget the last chunk
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """
    Split a sentence that exceeds the character limit by words.

    This is a fallback for extremely long sentences. Tries to split
    at clause boundaries (commas, semicolons) when possible.

    Args:
        sentence: The long sentence to split.
        max_chars: Maximum characters per chunk.

    Returns:
        List of chunks from the sentence.
    """
    # Try to split at clause boundaries first
    # Pattern matches comma, semicolon, or dash followed by space
    clause_pattern = r"(?<=[,;—–-])\s+"
    clauses = re.split(clause_pattern, sentence)

    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for clause in clauses:
        if len(clause) > max_chars:
            # Even the clause is too long, split by words
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_length = 0

            words = clause.split()
            word_chunk: list[str] = []
            word_length = 0

            for word in words:
                space = 1 if word_chunk else 0
                if word_length + space + len(word) > max_chars:
                    if word_chunk:
                        chunks.append(" ".join(word_chunk))
                    word_chunk = [word]
                    word_length = len(word)
                else:
                    word_chunk.append(word)
                    word_length += space + len(word)

            if word_chunk:
                chunks.append(" ".join(word_chunk))
        else:
            space = 1 if current_chunk else 0
            if current_length + space + len(clause) > max_chars:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [clause]
                current_length = len(clause)
            else:
                current_chunk.append(clause)
                current_length += space + len(clause)

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks


def truncate_at_sentence_boundary(
    text: str,
    max_chars: int = ELEVENLABS_CHAR_LIMIT,
) -> str:
    """
    Truncate text at a sentence boundary to fit within the character limit.

    Keeps as many complete sentences as possible while staying under the limit.

    Args:
        text: The text to truncate.
        max_chars: Maximum characters allowed (default: 5000).

    Returns:
        Truncated text ending at a complete sentence.
    """
    if len(text) <= max_chars:
        return text

    sentences = split_sentences(text)
    result: list[str] = []
    current_length = 0

    for sentence in sentences:
        space_needed = 1 if result else 0
        if current_length + space_needed + len(sentence) > max_chars:
            break
        result.append(sentence)
        current_length += space_needed + len(sentence)

    # If we couldn't fit even one sentence, truncate mid-sentence as last resort
    if not result and sentences:
        # Find the last word boundary before max_chars
        truncated = text[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars // 2:  # Only use if we keep at least half
            return truncated[:last_space] + "…"
        return truncated + "…"

    return " ".join(result)


def estimate_chunk_count(
    text: str,
    max_chars: int = ELEVENLABS_CHAR_LIMIT,
) -> int:
    """
    Estimate the number of chunks needed for the text.

    This is a quick estimate based on character count, not actual
    sentence boundaries. Useful for showing the user before they
    commit to chunking.

    Args:
        text: The text to estimate chunks for.
        max_chars: Maximum characters per chunk (default: 5000).

    Returns:
        Estimated number of chunks needed.
    """
    if len(text) <= max_chars:
        return 1

    # Simple estimate: divide by limit, round up
    # Add a small buffer for sentence boundary overhead
    return (len(text) + max_chars - 1) // max_chars


def get_text_stats(text: str) -> dict:
    """
    Get statistics about text for TTS processing.

    Args:
        text: The text to analyze.

    Returns:
        Dictionary with character count, word count, sentence count,
        and estimated speaking time.
    """
    char_count = len(text)
    word_count = len(text.split())
    sentence_count = len(split_sentences(text))

    # Average speaking rate: ~150 words per minute
    # This is approximate - actual TTS speed varies
    estimated_minutes = word_count / 150

    return {
        "characters": char_count,
        "words": word_count,
        "sentences": sentence_count,
        "estimated_minutes": round(estimated_minutes, 1),
        "exceeds_limit": char_count > ELEVENLABS_CHAR_LIMIT,
        "chunks_needed": estimate_chunk_count(text),
    }
