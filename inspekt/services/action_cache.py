"""
Action caching service for the 'inspekt do' command.

This module provides intelligent caching and matching for user actions:
1. Cache: Store successful action → element mappings per URL
2. Literal matching: Find elements whose text matches the action
3. Common actions: Dictionary of frequent actions
4. Advanced matching: Fuzzy text matching, synonyms, URL patterns

This dramatically reduces AI calls and speeds up repeated actions.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from inspekt.config import get_data_dir, load_config


class ActionCache:
    """Manages caching and intelligent matching for user actions."""

    def __init__(self):
        """Initialize the action cache with SQLite database."""
        self.db_path = get_data_dir() / "action_cache.db"
        self._init_database()
        self.config = self._load_config()
        self.filler_words = self._load_filler_words()

    def _load_config(self) -> dict[str, Any]:
        """Load cache configuration from config.json."""
        try:
            from inspekt.config import load_config

            config = load_config()
            return config.get("cache", self._default_config())
        except Exception:
            return self._default_config()

    def _default_config(self) -> dict[str, Any]:
        """Return default cache configuration."""
        return {
            "enabled": True,
            "ttl_hours": 24,
            "max_urls": 100,
            "max_actions_per_url": 10,
            "max_total_actions": 1000,
            "similarity_threshold": 0.8,
            "literal_match_threshold": 0.8,
            "use_fuzzy_matching": True,
            "max_fuzzy_distance": 2,
        }

    def _load_filler_words(self) -> dict[str, set[str]]:
        """Load filler words from i18n JSON file."""
        try:
            i18n_path = Path(__file__).parent.parent / "i18n" / "filler_words.json"
            if not i18n_path.exists():
                return self._get_default_filler_words()

            with open(i18n_path, encoding="utf-8") as f:
                data = json.load(f)

            # Flatten all categories into a single set per language
            filler_words = {}
            for lang, categories in data.items():
                if lang.startswith("$"):  # Skip JSON schema fields
                    continue
                words = set()
                for category_words in categories.values():
                    words.update(category_words)
                filler_words[lang] = words

            return filler_words
        except Exception:
            return self._get_default_filler_words()

    def _get_default_filler_words(self) -> dict[str, set[str]]:
        """Return default English filler words as fallback."""
        return {
            "en": {
                "go", "open", "click", "navigate", "visit", "access",
                "show", "display", "view", "see", "find", "get",
                "take", "bring", "load", "press",
                "the", "a", "an", "to", "on", "at", "in", "of", "for", "with", "from", "by",
                "my", "me", "i", "want", "need",
                "page", "button", "link", "image", "icon", "field", "form", "input", "menu", "tab", "section", "area",
                "please", "now", "then", "next", "first", "also", "just", "only",
            }
        }

    def _init_database(self):
        """Initialize SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Page cache table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS page_cache (
                url TEXT PRIMARY KEY,
                fingerprint TEXT,
                last_updated INTEGER,
                actionable_elements TEXT
            )
        """
        )

        # Action cache table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS action_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT,
                action_normalized TEXT,
                action_original TEXT,
                element_selector TEXT,
                element_identifier TEXT,
                success_count INTEGER DEFAULT 1,
                last_used INTEGER,
                FOREIGN KEY (url) REFERENCES page_cache(url)
            )
        """
        )

        # Create index for faster lookups
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_url_action
            ON action_cache(url, action_normalized)
        """
        )

        conn.commit()
        conn.close()

    def is_enabled(self) -> bool:
        """Check if caching is enabled."""
        return self.config.get("enabled", True)

    def normalize_action(self, action: str, languages: list[str] | None = None) -> str:
        """
        Normalize action text by removing filler words and punctuation.

        Supports multiple languages. If languages not specified, uses English + common European languages.

        Args:
            action: The action text to normalize
            languages: List of language codes to use for filler word removal (e.g., ['nl', 'en'])

        Examples:
            "Please click the login button" → "login"
            "Ga naar de About Us pagina" → "about us"
            "Navigeer naar mijn instellingen" → "instellingen"
        """
        # Convert to lowercase
        action = action.lower()

        # Remove punctuation
        import string
        action = action.translate(str.maketrans("", "", string.punctuation))

        # Determine which languages to use for filtering
        if languages is None:
            # Default: try common European languages + English
            languages = ["en", "nl", "fr", "de", "es"]

        # Combine filler words from all specified languages
        combined_filler_words = set()
        for lang in languages:
            if lang in self.filler_words:
                combined_filler_words.update(self.filler_words[lang])

        # Fallback to English if no filler words found
        if not combined_filler_words and "en" in self.filler_words:
            combined_filler_words = self.filler_words["en"]

        # Split into words and filter
        words = action.split()
        filtered_words = [w for w in words if w not in combined_filler_words]

        return " ".join(filtered_words)

    def calculate_page_fingerprint(self, page_data: dict) -> str:
        """
        Calculate a fingerprint for the page structure.

        Returns a JSON string representing the page structure.
        """
        fingerprint = {
            "actionable_count": page_data.get("totalActions", 0),
            "heading_structure": [
                f"H{h['level']}:{h['text'][:30]}" for h in page_data.get("headings", [])[:10]
            ],
            "landmarks": [lm.get("role") for lm in page_data.get("landmarks", [])],
        }
        return json.dumps(fingerprint, sort_keys=True)

    def calculate_similarity(self, fingerprint1: str, fingerprint2: str) -> float:
        """
        Calculate similarity between two page fingerprints.

        Returns a score between 0.0 and 1.0.
        """
        try:
            fp1 = json.loads(fingerprint1)
            fp2 = json.loads(fingerprint2)

            # Compare actionable element counts
            count1 = fp1.get("actionable_count", 0)
            count2 = fp2.get("actionable_count", 0)
            count_similarity = 1.0 - abs(count1 - count2) / max(count1, count2, 1)

            # Compare headings
            headings1 = set(fp1.get("heading_structure", []))
            headings2 = set(fp2.get("heading_structure", []))
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

            # Weighted average
            similarity = (count_similarity * 0.4 + heading_similarity * 0.3 + landmark_similarity * 0.3)
            return similarity
        except Exception:
            return 0.0

    def get_cached_action(
        self, url: str, action_normalized: str, current_fingerprint: str
    ) -> dict | None:
        """
        Retrieve cached action for a URL if page structure is similar enough.

        Returns element identifier dict if found and page is similar, else None.
        """
        if not self.is_enabled():
            return None

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Get page cache
            cursor.execute("SELECT fingerprint, last_updated FROM page_cache WHERE url = ?", (url,))
            page_row = cursor.fetchone()

            if not page_row:
                return None

            cached_fingerprint, last_updated = page_row

            # Check if cache is fresh
            ttl_seconds = self.config.get("ttl_hours", 24) * 3600
            if time.time() - last_updated > ttl_seconds:
                return None

            # Check similarity
            similarity = self.calculate_similarity(cached_fingerprint, current_fingerprint)
            threshold = self.config.get("similarity_threshold", 0.8)

            if similarity < threshold:
                return None

            # Get action cache
            cursor.execute(
                """
                SELECT element_identifier, element_selector
                FROM action_cache
                WHERE url = ? AND action_normalized = ?
                ORDER BY last_used DESC
                LIMIT 1
            """,
                (url, action_normalized),
            )

            action_row = cursor.fetchone()
            if not action_row:
                return None

            element_identifier, element_selector = action_row

            # Update usage stats
            cursor.execute(
                """
                UPDATE action_cache
                SET last_used = ?, success_count = success_count + 1
                WHERE url = ? AND action_normalized = ?
            """,
                (int(time.time()), url, action_normalized),
            )
            conn.commit()

            return {
                "identifier": json.loads(element_identifier),
                "selector": element_selector,
                "similarity": similarity,
            }

        finally:
            conn.close()

    def store_action(
        self, url: str, action_original: str, action_normalized: str, element: dict, page_data: dict
    ):
        """Store successful action execution in cache."""
        if not self.is_enabled():
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Calculate fingerprint
            fingerprint = self.calculate_page_fingerprint(page_data)
            timestamp = int(time.time())

            # Store/update page cache
            cursor.execute(
                """
                INSERT OR REPLACE INTO page_cache (url, fingerprint, last_updated, actionable_elements)
                VALUES (?, ?, ?, ?)
            """,
                (url, fingerprint, timestamp, json.dumps(page_data.get("actionableElements", []))),
            )

            # Create element identifier and selector
            element_identifier = {
                "type": element.get("type"),
                "text": element.get("text"),
                "href": element.get("href"),
                "context": element.get("context"),
            }

            # Try to create a CSS selector
            element_selector = self._create_selector(element)

            # Store action cache
            cursor.execute(
                """
                INSERT INTO action_cache
                (url, action_normalized, action_original, element_selector, element_identifier, last_used)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    url,
                    action_normalized,
                    action_original,
                    element_selector,
                    json.dumps(element_identifier),
                    timestamp,
                ),
            )

            conn.commit()

            # Cleanup old entries
            self._cleanup_cache(cursor)
            conn.commit()

        finally:
            conn.close()

    def _create_selector(self, element: dict) -> str:
        """Create a CSS selector for an element."""
        # Try to create a simple selector based on href or text
        if element.get("href"):
            href = element["href"]
            return f"a[href='{href}']"
        elif element.get("text"):
            # Not a perfect selector, but can help
            return f"*:contains('{element['text'][:50]}')"
        return ""

    def _cleanup_cache(self, cursor: sqlite3.Cursor):
        """Remove old cache entries to stay within limits."""
        # Remove old URLs
        max_urls = self.config.get("max_urls", 100)
        cursor.execute(
            """
            DELETE FROM page_cache
            WHERE url NOT IN (
                SELECT url FROM page_cache
                ORDER BY last_updated DESC
                LIMIT ?
            )
        """,
            (max_urls,),
        )

        # Remove old actions
        max_actions = self.config.get("max_total_actions", 1000)
        cursor.execute(
            """
            DELETE FROM action_cache
            WHERE id NOT IN (
                SELECT id FROM action_cache
                ORDER BY last_used DESC
                LIMIT ?
            )
        """,
            (max_actions,),
        )

    def clear_cache(self):
        """Clear all cache entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM action_cache")
        cursor.execute("DELETE FROM page_cache")
        conn.commit()
        conn.close()
