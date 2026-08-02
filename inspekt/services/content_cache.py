"""
Content caching service for 'inspekt describe' and 'inspekt summarize' commands.

This module provides intelligent content caching with fingerprinting:
- Caches AI-generated descriptions and summaries
- Detects content changes via fingerprinting
- Supports multiple languages
- Configurable TTL and similarity thresholds
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from typing import Any

from inspekt.config import get_data_dir, load_config


class ContentCache:
    """Manages caching for AI-generated content (describe, summarize)."""

    def __init__(self):
        """Initialize the content cache with SQLite database."""
        self.db_path = get_data_dir() / "action_cache.db"
        self._init_database()
        self.config = self._load_config()

    def _load_config(self) -> dict[str, Any]:
        """Load cache configuration from config.json."""
        try:
            config = load_config()
            return config.get("cache", self._default_config())
        except Exception:
            return self._default_config()

    def _default_config(self) -> dict[str, Any]:
        """Return default cache configuration."""
        return {
            "describe": {
                "enabled": True,
                "ttl_hours": 12,
                "similarity_threshold": 0.85,
                "max_entries": 100,
            },
            "summarize": {
                "enabled": True,
                "ttl_days": 7,
                "similarity_threshold": 0.90,
                "max_entries": 50,
            },
            "ask": {
                "enabled": True,
                "ttl_hours": 1,
                "max_entries": 200,
            },
            "extract": {
                "enabled": True,
                "ttl_days": 7,
                "similarity_threshold": 0.90,
                "max_entries": 100,
            },
            "element_ask": {
                "enabled": True,
                "ttl_hours": 1,
                "max_entries": 200,
            },
        }

    def _init_database(self):
        """Initialize SQLite database with content cache table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Content cache table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS content_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                command TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                cached_output TEXT NOT NULL,
                language TEXT,
                last_updated INTEGER NOT NULL,
                hit_count INTEGER DEFAULT 0,
                UNIQUE(url, command, language)
            )
        """
        )

        # Create index for faster lookups
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_url_command_lang
            ON content_cache(url, command, language)
        """
        )

        conn.commit()
        conn.close()

    def is_enabled(self, command: str) -> bool:
        """Check if caching is enabled for a command."""
        command_config = self.config.get(command, {})
        return command_config.get("enabled", True)

    def create_describe_fingerprint(self, page_data: dict) -> str:
        """
        Create a fingerprint for a page (describe command).

        Includes: title, headings, landmarks, element counts, text excerpt
        """
        fingerprint = {
            "pageTitle": page_data.get("title", ""),
            "headingStructure": [
                f"H{h['level']}:{h['text'][:30]}" for h in page_data.get("headings", [])[:15]
            ],
            "landmarks": [lm.get("role") for lm in page_data.get("landmarks", [])],
            "mainTextExcerpt": page_data.get("mainText", "")[:200],
            "elementCounts": {
                "links": page_data.get("linkCount", 0),
                "buttons": page_data.get("buttonCount", 0),
                "images": page_data.get("imageCount", 0),
            },
        }
        return json.dumps(fingerprint, sort_keys=True)

    def create_summarize_fingerprint(self, article_data: dict) -> str:
        """
        Create a fingerprint for an article (summarize command).

        Includes: title, length, content hash, excerpt, publish date
        """
        article_text = article_data.get("text", "")
        article_length = len(article_text.split())

        # Create content hash from first 500 and last 100 characters
        content_sample = (
            article_text[:500] + article_text[-100:] if len(article_text) > 600 else article_text
        )
        content_hash = hashlib.sha256(content_sample.encode()).hexdigest()[:16]

        fingerprint = {
            "articleTitle": article_data.get("title", ""),
            "articleLength": article_length,
            "contentHash": content_hash,
            "excerpt": article_text[:500] if article_text else "",
            "publishDate": article_data.get("publishedDate", ""),
        }
        return json.dumps(fingerprint, sort_keys=True)

    def create_ask_fingerprint(self, question: str) -> str:
        """
        Create a fingerprint for an ask command.

        For ask, the fingerprint is simply the question itself.
        """
        fingerprint = {
            "question": question,
        }
        return json.dumps(fingerprint, sort_keys=True)

    def create_extract_fingerprint(self, article_data: dict, engine: str) -> str:
        """
        Create a fingerprint for extracted article content.

        Includes: title, content hash, content length, publish date, engine
        """
        html_content = article_data.get("htmlContent", "")
        content_length = len(html_content)

        # Create content hash from first 1000 and last 200 characters
        if len(html_content) > 1200:
            content_sample = html_content[:1000] + html_content[-200:]
        else:
            content_sample = html_content
        content_hash = hashlib.sha256(content_sample.encode()).hexdigest()[:16]

        fingerprint = {
            "articleTitle": article_data.get("title", ""),
            "contentLength": content_length,
            "contentHash": content_hash,
            "publishDate": article_data.get("publishedDate", ""),
            "engine": engine,
        }
        return json.dumps(fingerprint, sort_keys=True)

    def create_element_ask_fingerprint(self, element_data: dict, question: str) -> str:
        """
        Create a fingerprint for element_ask command.

        Includes: element tag, id, accessible name, text content hash, and question.
        This allows caching of AI responses for the same element + question combination.
        """
        # Get element identifier components
        tag = element_data.get("tag", "unknown")
        element_id = element_data.get("id", "")

        # Get accessibility info
        a11y = element_data.get("accessibility", {})
        accessible_name = a11y.get("accessibleName", "")

        # Get text content hash (for detecting content changes)
        text_content = element_data.get("textContent", "")
        text_hash = hashlib.sha256(text_content.encode()).hexdigest()[:16] if text_content else ""

        # Get dimensions (element size can indicate state changes)
        dims = element_data.get("dimensions", {})
        width = dims.get("width", 0)
        height = dims.get("height", 0)

        fingerprint = {
            "tag": tag,
            "id": element_id,
            "accessibleName": accessible_name[:100],  # Truncate for consistency
            "textHash": text_hash,
            "dimensions": f"{width}x{height}",
            "question": question,
        }
        return json.dumps(fingerprint, sort_keys=True)

    def get_element_cache_key(self, element_data: dict, question: str) -> str:
        """
        Generate a cache key for element_ask.

        Combines element identity and question into a hash suitable for the 'language' field.
        """
        tag = element_data.get("tag", "unknown")
        element_id = element_data.get("id", "")
        a11y = element_data.get("accessibility", {})
        accessible_name = a11y.get("accessibleName", "")[:50]

        # Create a composite key from element identity + question
        key_parts = f"{tag}:{element_id}:{accessible_name}:{question}"
        return hashlib.sha256(key_parts.encode()).hexdigest()[:24]

    def get_question_hash(self, question: str) -> str:
        """
        Get a hash of the question for use as cache key.

        This is used in the language field for ask command caching.
        """
        return hashlib.sha256(question.encode()).hexdigest()[:16]

    def calculate_similarity(self, fingerprint1: str, fingerprint2: str, command: str) -> float:
        """
        Calculate similarity between two fingerprints.

        Returns a score between 0.0 and 1.0.
        """
        try:
            fp1 = json.loads(fingerprint1)
            fp2 = json.loads(fingerprint2)

            if command == "describe":
                return self._calculate_describe_similarity(fp1, fp2)
            elif command == "summarize":
                return self._calculate_summarize_similarity(fp1, fp2)
            elif command == "ask":
                return self._calculate_ask_similarity(fp1, fp2)
            elif command == "extract":
                return self._calculate_extract_similarity(fp1, fp2)
            elif command == "element_ask":
                return self._calculate_element_ask_similarity(fp1, fp2)
            else:
                return 0.0
        except Exception:
            return 0.0

    def _calculate_describe_similarity(self, fp1: dict, fp2: dict) -> float:
        """Calculate similarity for page descriptions."""
        # Compare page title
        title_similarity = 1.0 if fp1.get("pageTitle") == fp2.get("pageTitle") else 0.0

        # Compare headings
        headings1 = set(fp1.get("headingStructure", []))
        headings2 = set(fp2.get("headingStructure", []))
        if headings1 or headings2:
            heading_similarity = len(headings1 & headings2) / len(headings1 | headings2)
        else:
            heading_similarity = 1.0

        # Compare landmarks
        landmarks1 = set(fp1.get("landmarks", []))
        landmarks2 = set(fp2.get("landmarks", []))
        if landmarks1 or landmarks2:
            landmark_similarity = len(landmarks1 & landmarks2) / len(landmarks1 | landmarks2)
        else:
            landmark_similarity = 1.0

        # Compare element counts
        counts1 = fp1.get("elementCounts", {})
        counts2 = fp2.get("elementCounts", {})
        count_similarities = []
        for key in ["links", "buttons", "images"]:
            c1 = counts1.get(key, 0)
            c2 = counts2.get(key, 0)
            if c1 or c2:
                count_similarities.append(1.0 - abs(c1 - c2) / max(c1, c2, 1))
            else:
                count_similarities.append(1.0)
        count_similarity = (
            sum(count_similarities) / len(count_similarities) if count_similarities else 1.0
        )

        # Compare text excerpt
        text1 = fp1.get("mainTextExcerpt", "")
        text2 = fp2.get("mainTextExcerpt", "")
        text_similarity = 1.0 if text1 == text2 else (0.5 if text1 and text2 else 0.0)

        # Weighted average
        similarity = (
            title_similarity * 0.2
            + heading_similarity * 0.25
            + landmark_similarity * 0.2
            + count_similarity * 0.2
            + text_similarity * 0.15
        )
        return similarity

    def _calculate_summarize_similarity(self, fp1: dict, fp2: dict) -> float:
        """Calculate similarity for article summaries."""
        # Compare title
        title_similarity = 1.0 if fp1.get("articleTitle") == fp2.get("articleTitle") else 0.0

        # Compare content hash (most important)
        hash_similarity = 1.0 if fp1.get("contentHash") == fp2.get("contentHash") else 0.0

        # Compare article length
        length1 = fp1.get("articleLength", 0)
        length2 = fp2.get("articleLength", 0)
        if length1 and length2:
            length_similarity = 1.0 - abs(length1 - length2) / max(length1, length2)
        else:
            length_similarity = 0.0

        # Compare publish date
        date_similarity = 1.0 if fp1.get("publishDate") == fp2.get("publishDate") else 0.0

        # Weighted average (hash is most important for articles)
        similarity = (
            title_similarity * 0.15
            + hash_similarity * 0.55
            + length_similarity * 0.15
            + date_similarity * 0.15
        )
        return similarity

    def _calculate_ask_similarity(self, fp1: dict, fp2: dict) -> float:
        """Calculate similarity for ask questions (exact match only)."""
        # For ask, we require exact question match
        return 1.0 if fp1.get("question") == fp2.get("question") else 0.0

    def _calculate_extract_similarity(self, fp1: dict, fp2: dict) -> float:
        """Calculate similarity for article extraction."""
        # Must use same engine
        if fp1.get("engine") != fp2.get("engine"):
            return 0.0

        # Compare title
        title_similarity = 1.0 if fp1.get("articleTitle") == fp2.get("articleTitle") else 0.0

        # Compare content hash (most important - determines if content changed)
        hash_similarity = 1.0 if fp1.get("contentHash") == fp2.get("contentHash") else 0.0

        # Compare content length (within 5% tolerance)
        length1 = fp1.get("contentLength", 0)
        length2 = fp2.get("contentLength", 0)
        if length1 and length2:
            length_ratio = min(length1, length2) / max(length1, length2)
            length_similarity = 1.0 if length_ratio >= 0.95 else length_ratio
        else:
            length_similarity = 0.0

        # Compare publish date
        date_similarity = 1.0 if fp1.get("publishDate") == fp2.get("publishDate") else 0.0

        # Weighted average (hash is most important for extract)
        similarity = (
            title_similarity * 0.15
            + hash_similarity * 0.55
            + length_similarity * 0.15
            + date_similarity * 0.15
        )
        return similarity

    def _calculate_element_ask_similarity(self, fp1: dict, fp2: dict) -> float:
        """
        Calculate similarity for element_ask questions.

        Requires exact match on question and high similarity on element identity.
        """
        # Question must match exactly
        if fp1.get("question") != fp2.get("question"):
            return 0.0

        # Element tag must match
        if fp1.get("tag") != fp2.get("tag"):
            return 0.0

        # Element ID should match if present
        id1, id2 = fp1.get("id", ""), fp2.get("id", "")
        if id1 and id2 and id1 != id2:
            return 0.0

        # Text content hash should match (content unchanged)
        hash_similarity = 1.0 if fp1.get("textHash") == fp2.get("textHash") else 0.0

        # Accessible name should be similar
        name1 = fp1.get("accessibleName", "")
        name2 = fp2.get("accessibleName", "")
        name_similarity = 1.0 if name1 == name2 else (0.8 if name1 and name2 else 0.5)

        # Dimensions should be close (element hasn't resized significantly)
        dims1 = fp1.get("dimensions", "0x0")
        dims2 = fp2.get("dimensions", "0x0")
        dims_similarity = 1.0 if dims1 == dims2 else 0.7

        # Weighted average
        similarity = hash_similarity * 0.5 + name_similarity * 0.3 + dims_similarity * 0.2
        return similarity

    def get_cached_content(
        self, url: str, command: str, current_fingerprint: str, language: str = "auto"
    ) -> dict | None:
        """
        Retrieve cached content if page/article hasn't changed significantly.

        Returns dict with 'output' and 'similarity' if found, else None.
        """
        if not self.is_enabled(command):
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get cached content
            cursor.execute(
                """
                SELECT fingerprint, cached_output, last_updated, hit_count
                FROM content_cache
                WHERE url = ? AND command = ? AND language = ?
                LIMIT 1
            """,
                (url, command, language),
            )

            row = cursor.fetchone()
            if not row:
                return None

            cached_fingerprint, cached_output, last_updated, hit_count = row

            # Check if cache is fresh
            command_config = self.config.get(command, {})
            if command in ("describe", "ask", "element_ask"):
                default_hours = 12 if command == "describe" else 1
                ttl_seconds = command_config.get("ttl_hours", default_hours) * 3600
            else:  # summarize, extract
                ttl_seconds = command_config.get("ttl_days", 7) * 86400

            if time.time() - last_updated > ttl_seconds:
                return None

            # Check similarity (skip if no fingerprint provided - just check freshness)
            if current_fingerprint:
                similarity = self.calculate_similarity(
                    cached_fingerprint, current_fingerprint, command
                )

                # For ask and element_ask, require high threshold (0.85)
                # This ensures question + element identity must match closely
                if command in ("ask", "element_ask"):
                    threshold = command_config.get("similarity_threshold", 0.85)
                else:
                    threshold = command_config.get(
                        "similarity_threshold", 0.85 if command == "describe" else 0.90
                    )

                if similarity < threshold:
                    return None
            else:
                # No fingerprint provided - trust the cache if it's fresh
                similarity = 1.0

            # Update hit count
            cursor.execute(
                """
                UPDATE content_cache
                SET hit_count = hit_count + 1
                WHERE url = ? AND command = ? AND language = ?
            """,
                (url, command, language),
            )
            conn.commit()

            # Calculate cache age
            age_seconds = int(time.time() - last_updated)

            return {
                "output": cached_output,
                "similarity": similarity,
                "age_seconds": age_seconds,
                "hit_count": hit_count + 1,
            }

        finally:
            conn.close()

    def store_content(
        self, url: str, command: str, fingerprint: str, output: str, language: str = "auto"
    ):
        """Store AI-generated content in cache."""
        if not self.is_enabled(command):
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            timestamp = int(time.time())

            # Store/update content cache
            cursor.execute(
                """
                INSERT INTO content_cache (url, command, fingerprint, cached_output, language, last_updated, hit_count)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT(url, command, language)
                DO UPDATE SET
                    fingerprint = excluded.fingerprint,
                    cached_output = excluded.cached_output,
                    last_updated = excluded.last_updated,
                    hit_count = 0
            """,
                (url, command, fingerprint, output, language, timestamp),
            )

            conn.commit()

            # Cleanup old entries
            self._cleanup_cache(cursor, command)
            conn.commit()

        finally:
            conn.close()

    def _cleanup_cache(self, cursor: sqlite3.Cursor, command: str):
        """Remove old cache entries to stay within limits."""
        command_config = self.config.get(command, {})
        max_entries = command_config.get("max_entries", 100 if command == "describe" else 50)

        cursor.execute(
            """
            DELETE FROM content_cache
            WHERE command = ? AND id NOT IN (
                SELECT id FROM content_cache
                WHERE command = ?
                ORDER BY last_updated DESC
                LIMIT ?
            )
        """,
            (command, command, max_entries),
        )

    def clear_cache(self, command: str | None = None):
        """Clear cache entries for a specific command or all."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if command:
            cursor.execute("DELETE FROM content_cache WHERE command = ?", (command,))
        else:
            cursor.execute("DELETE FROM content_cache")

        conn.commit()
        conn.close()

    def get_stats(self, command: str | None = None) -> dict:
        """Get cache statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        stats = {}

        try:
            if command:
                # Stats for specific command
                cursor.execute(
                    """
                    SELECT COUNT(*), SUM(hit_count), AVG(hit_count)
                    FROM content_cache
                    WHERE command = ?
                """,
                    (command,),
                )
                row = cursor.fetchone()
                stats[command] = {
                    "total_entries": row[0] or 0,
                    "total_hits": row[1] or 0,
                    "avg_hits_per_entry": row[2] or 0.0,
                }
            else:
                # Stats for all commands
                for cmd in ["describe", "summarize", "ask"]:
                    cursor.execute(
                        """
                        SELECT COUNT(*), SUM(hit_count), AVG(hit_count)
                        FROM content_cache
                        WHERE command = ?
                    """,
                        (cmd,),
                    )
                    row = cursor.fetchone()
                    stats[cmd] = {
                        "total_entries": row[0] or 0,
                        "total_hits": row[1] or 0,
                        "avg_hits_per_entry": row[2] or 0.0,
                    }

        finally:
            conn.close()

        return stats
