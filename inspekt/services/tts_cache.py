"""
TTS audio caching service with text similarity matching.

This module provides intelligent audio caching for text-to-speech:
- Caches generated audio files to avoid redundant API calls
- Uses text similarity matching (90% threshold) for fuzzy cache hits
- Supports multiple voices with separate cache entries
- Configurable TTL and similarity thresholds
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
from pathlib import Path
from typing import Any

from inspekt.config import get_data_dir, load_config


class TTSCache:
    """Manages caching for TTS-generated audio files."""

    def __init__(self):
        """Initialize the TTS cache with SQLite database and audio storage."""
        config_dir = get_data_dir()

        # Database for metadata
        self.db_path = config_dir / "tts_cache.db"

        # Directory for audio files
        self.audio_dir = config_dir / "tts_audio"
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        self._init_database()
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        """Load cache configuration from config.json."""
        try:
            config = load_config()
            cache_config = config.get("cache", {})
            return cache_config.get("tts", self._default_config())
        except Exception:
            return self._default_config()

    def _default_config(self) -> dict[str, Any]:
        """Return default TTS cache configuration."""
        return {
            "enabled": True,
            "ttl_days": 30,  # Audio files valid for 30 days
            "similarity_threshold": 0.90,  # 90% text similarity for cache hit
            "max_entries": 500,  # Maximum cached audio files
            "max_size_mb": 500,  # Maximum total cache size in MB
        }

    def _init_database(self):
        """Initialize SQLite database with TTS cache table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tts_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text_hash TEXT NOT NULL,
                text_content TEXT NOT NULL,
                voice_name TEXT NOT NULL,
                audio_path TEXT NOT NULL,
                audio_size INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed INTEGER NOT NULL,
                hit_count INTEGER DEFAULT 0,
                UNIQUE(text_hash, voice_name)
            )
        """
        )

        # Create index for faster lookups
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_voice_created
            ON tts_cache(voice_name, created_at)
        """
        )

        conn.commit()
        conn.close()

    def is_enabled(self) -> bool:
        """Check if TTS caching is enabled."""
        return self.config.get("enabled", True)

    def _hash_text(self, text: str) -> str:
        """Create a hash of the text for exact matching."""
        # Normalize text before hashing
        normalized = self._normalize_text(text)
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison (lowercase, collapse whitespace)."""
        # Lowercase and collapse whitespace
        normalized = text.lower()
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _tokenize(self, text: str) -> set[str]:
        """Tokenize text into words for similarity comparison."""
        normalized = self._normalize_text(text)
        # Split on whitespace and punctuation, keep only alphanumeric tokens
        tokens = re.findall(r"\b\w+\b", normalized)
        return set(tokens)

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate Jaccard similarity between two texts.

        Returns a score between 0.0 and 1.0.
        """
        tokens1 = self._tokenize(text1)
        tokens2 = self._tokenize(text2)

        if not tokens1 and not tokens2:
            return 1.0  # Both empty = identical
        if not tokens1 or not tokens2:
            return 0.0  # One empty = no similarity

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    def get_cached_audio(self, text: str, voice_name: str) -> dict | None:
        """
        Retrieve cached audio if text is similar enough.

        First tries exact hash match, then looks for similar text entries.

        Args:
            text: The text to speak
            voice_name: Name of the voice

        Returns:
            Dict with 'audio_path', 'similarity', 'hit_count' if found, else None.
        """
        if not self.is_enabled():
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            text_hash = self._hash_text(text)
            now = int(time.time())
            threshold = self.config.get("similarity_threshold", 0.90)
            ttl_seconds = self.config.get("ttl_days", 30) * 86400

            # First, try exact hash match
            cursor.execute(
                """
                SELECT id, text_content, audio_path, audio_size, created_at, hit_count
                FROM tts_cache
                WHERE text_hash = ? AND voice_name = ?
                LIMIT 1
            """,
                (text_hash, voice_name),
            )

            row = cursor.fetchone()
            if row:
                cache_id, cached_text, audio_path, _audio_size, created_at, hit_count = row

                # Check if cache is fresh
                if now - created_at <= ttl_seconds:
                    audio_file = Path(audio_path)
                    if audio_file.exists():
                        # Update access time and hit count
                        cursor.execute(
                            """
                            UPDATE tts_cache
                            SET last_accessed = ?, hit_count = hit_count + 1
                            WHERE id = ?
                        """,
                            (now, cache_id),
                        )
                        conn.commit()

                        return {
                            "audio_path": audio_path,
                            "audio_bytes": audio_file.read_bytes(),
                            "similarity": 1.0,
                            "hit_count": hit_count + 1,
                            "exact_match": True,
                        }

            # No exact match, search for similar text
            cursor.execute(
                """
                SELECT id, text_content, audio_path, audio_size, created_at, hit_count
                FROM tts_cache
                WHERE voice_name = ? AND created_at > ?
                ORDER BY created_at DESC
                LIMIT 100
            """,
                (voice_name, now - ttl_seconds),
            )

            rows = cursor.fetchall()
            best_match = None
            best_similarity = 0.0

            for row in rows:
                cache_id, cached_text, audio_path, _audio_size, created_at, hit_count = row

                similarity = self.calculate_similarity(text, cached_text)
                if similarity >= threshold and similarity > best_similarity:
                    audio_file = Path(audio_path)
                    if audio_file.exists():
                        best_match = {
                            "cache_id": cache_id,
                            "audio_path": audio_path,
                            "audio_bytes": audio_file.read_bytes(),
                            "similarity": similarity,
                            "hit_count": hit_count,
                        }
                        best_similarity = similarity

                        # If we found a very high match (>95%), stop searching
                        if similarity > 0.95:
                            break

            if best_match:
                # Update access time and hit count
                cursor.execute(
                    """
                    UPDATE tts_cache
                    SET last_accessed = ?, hit_count = hit_count + 1
                    WHERE id = ?
                """,
                    (now, best_match["cache_id"]),
                )
                conn.commit()

                return {
                    "audio_path": best_match["audio_path"],
                    "audio_bytes": best_match["audio_bytes"],
                    "similarity": best_match["similarity"],
                    "hit_count": best_match["hit_count"] + 1,
                    "exact_match": False,
                }

            return None

        finally:
            conn.close()

    def store_audio(self, text: str, voice_name: str, audio_bytes: bytes) -> str:
        """
        Store generated audio in cache.

        Args:
            text: The text that was spoken
            voice_name: Name of the voice used
            audio_bytes: Raw MP3 audio data

        Returns:
            Path to the stored audio file.
        """
        if not self.is_enabled():
            return ""

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            text_hash = self._hash_text(text)
            now = int(time.time())

            # Generate unique filename
            filename = f"{text_hash[:16]}_{voice_name}_{now}.mp3"
            audio_path = self.audio_dir / filename

            # Write audio file
            audio_path.write_bytes(audio_bytes)
            audio_size = len(audio_bytes)

            # Store metadata
            cursor.execute(
                """
                INSERT INTO tts_cache
                    (text_hash, text_content, voice_name, audio_path, audio_size, created_at, last_accessed, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(text_hash, voice_name)
                DO UPDATE SET
                    text_content = excluded.text_content,
                    audio_path = excluded.audio_path,
                    audio_size = excluded.audio_size,
                    created_at = excluded.created_at,
                    last_accessed = excluded.last_accessed,
                    hit_count = 0
            """,
                (text_hash, text, voice_name, str(audio_path), audio_size, now, now),
            )

            conn.commit()

            # Cleanup old entries
            self._cleanup_cache(cursor)
            conn.commit()

            return str(audio_path)

        finally:
            conn.close()

    def _cleanup_cache(self, cursor: sqlite3.Cursor):
        """Remove old cache entries to stay within limits."""
        max_entries = self.config.get("max_entries", 500)
        max_size_bytes = self.config.get("max_size_mb", 500) * 1024 * 1024
        ttl_seconds = self.config.get("ttl_days", 30) * 86400
        now = int(time.time())

        # Remove expired entries
        cursor.execute(
            """
            SELECT id, audio_path FROM tts_cache
            WHERE created_at < ?
        """,
            (now - ttl_seconds,),
        )
        expired_rows = cursor.fetchall()
        for row in expired_rows:
            cache_id, audio_path = row
            # Delete audio file
            audio_file = Path(audio_path)
            if audio_file.exists():
                try:
                    audio_file.unlink()
                except Exception:
                    pass
            # Delete database entry
            cursor.execute("DELETE FROM tts_cache WHERE id = ?", (cache_id,))

        # Check total size
        cursor.execute("SELECT SUM(audio_size) FROM tts_cache")
        total_size = cursor.fetchone()[0] or 0

        # If over size limit, remove oldest entries
        if total_size > max_size_bytes:
            cursor.execute(
                """
                SELECT id, audio_path, audio_size FROM tts_cache
                ORDER BY last_accessed ASC
            """
            )
            rows = cursor.fetchall()
            bytes_to_remove = total_size - max_size_bytes

            removed_bytes = 0
            for row in rows:
                if removed_bytes >= bytes_to_remove:
                    break
                cache_id, audio_path, audio_size = row
                # Delete audio file
                audio_file = Path(audio_path)
                if audio_file.exists():
                    try:
                        audio_file.unlink()
                    except Exception:
                        pass
                # Delete database entry
                cursor.execute("DELETE FROM tts_cache WHERE id = ?", (cache_id,))
                removed_bytes += audio_size

        # Check entry count limit
        cursor.execute("SELECT COUNT(*) FROM tts_cache")
        count = cursor.fetchone()[0]

        if count > max_entries:
            # Remove oldest entries beyond limit
            cursor.execute(
                """
                SELECT id, audio_path FROM tts_cache
                ORDER BY last_accessed ASC
                LIMIT ?
            """,
                (count - max_entries,),
            )
            rows = cursor.fetchall()
            for row in rows:
                cache_id, audio_path = row
                audio_file = Path(audio_path)
                if audio_file.exists():
                    try:
                        audio_file.unlink()
                    except Exception:
                        pass
                cursor.execute("DELETE FROM tts_cache WHERE id = ?", (cache_id,))

    def clear_cache(self, voice_name: str | None = None):
        """Clear cache entries for a specific voice or all voices."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            if voice_name:
                cursor.execute(
                    "SELECT audio_path FROM tts_cache WHERE voice_name = ?",
                    (voice_name,),
                )
            else:
                cursor.execute("SELECT audio_path FROM tts_cache")

            rows = cursor.fetchall()
            for row in rows:
                audio_file = Path(row[0])
                if audio_file.exists():
                    try:
                        audio_file.unlink()
                    except Exception:
                        pass

            if voice_name:
                cursor.execute("DELETE FROM tts_cache WHERE voice_name = ?", (voice_name,))
            else:
                cursor.execute("DELETE FROM tts_cache")

            conn.commit()
        finally:
            conn.close()

    def get_stats(self) -> dict:
        """Get cache statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT
                    COUNT(*) as entries,
                    SUM(audio_size) as total_size,
                    SUM(hit_count) as total_hits,
                    AVG(hit_count) as avg_hits
                FROM tts_cache
            """
            )
            row = cursor.fetchone()

            # Get per-voice stats
            cursor.execute(
                """
                SELECT voice_name, COUNT(*), SUM(audio_size), SUM(hit_count)
                FROM tts_cache
                GROUP BY voice_name
            """
            )
            voice_stats = {}
            for vrow in cursor.fetchall():
                voice_name, count, size, hits = vrow
                voice_stats[voice_name] = {
                    "entries": count,
                    "size_bytes": size or 0,
                    "hits": hits or 0,
                }

            return {
                "total_entries": row[0] or 0,
                "total_size_bytes": row[1] or 0,
                "total_size_mb": (row[1] or 0) / (1024 * 1024),
                "total_hits": row[2] or 0,
                "avg_hits_per_entry": row[3] or 0.0,
                "by_voice": voice_stats,
            }
        finally:
            conn.close()
