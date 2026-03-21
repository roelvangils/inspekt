"""
Persistent storage service for user data.

Manages SQLite database for:
- Hidden elements tracking
- CSS overrides (future)
- User preferences per domain
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from inspekt.config import get_data_dir


class PersistenceService:
    """Manages persistent user data storage."""

    def __init__(self):
        """Initialize persistence database."""
        self.db_path = get_data_dir() / "data.db"
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Hidden elements table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS hidden_elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                selector TEXT NOT NULL,
                reason TEXT,
                created_at INTEGER NOT NULL,
                last_updated INTEGER NOT NULL,
                hit_count INTEGER DEFAULT 0,
                UNIQUE(domain, selector)
            )
        """
        )

        # Create index for domain lookups
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_domain
            ON hidden_elements(domain)
        """
        )

        # Future: CSS overrides table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS css_overrides (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                selector TEXT NOT NULL,
                property TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                last_updated INTEGER NOT NULL,
                UNIQUE(domain, selector, property)
            )
        """
        )

        # Allowed domains table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS allowed_domains (
                domain TEXT PRIMARY KEY,
                added_at INTEGER NOT NULL,
                permanent INTEGER DEFAULT 1
            )
        """
        )

        # Create index for fast lookups
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_allowed_domains
            ON allowed_domains(domain)
        """
        )

        conn.commit()
        conn.close()

    def add_hidden_element(
        self, domain: str, selector: str, reason: str = ""
    ) -> dict[str, Any]:
        """Add element to hidden list."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            timestamp = int(time.time())

            cursor.execute(
                """
                INSERT INTO hidden_elements
                (domain, selector, reason, created_at, last_updated, hit_count)
                VALUES (?, ?, ?, ?, ?, 0)
                ON CONFLICT(domain, selector)
                DO UPDATE SET
                    reason = excluded.reason,
                    last_updated = excluded.last_updated
            """,
                (domain, selector, reason, timestamp, timestamp),
            )

            conn.commit()

            return {
                "ok": True,
                "domain": domain,
                "selector": selector,
                "reason": reason,
            }

        finally:
            conn.close()

    def get_hidden_elements(self, domain: str) -> list[dict[str, Any]]:
        """Get all hidden elements for a domain."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT selector, reason, created_at, last_updated, hit_count
                FROM hidden_elements
                WHERE domain = ?
                ORDER BY last_updated DESC
            """,
                (domain,),
            )

            rows = cursor.fetchall()

            return [
                {
                    "selector": row[0],
                    "reason": row[1],
                    "created_at": row[2],
                    "last_updated": row[3],
                    "hit_count": row[4],
                }
                for row in rows
            ]

        finally:
            conn.close()

    def remove_hidden_element(self, domain: str, selector: str) -> dict[str, Any]:
        """Remove element from hidden list."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM hidden_elements WHERE domain = ? AND selector = ?",
                (domain, selector),
            )

            deleted = cursor.rowcount > 0
            conn.commit()

            return {
                "ok": True,
                "deleted": deleted,
                "domain": domain,
                "selector": selector,
            }

        finally:
            conn.close()

    def remove_all_hidden_elements(self, domain: str) -> dict[str, Any]:
        """Remove all hidden elements for a domain."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM hidden_elements WHERE domain = ?",
                (domain,),
            )

            count = cursor.rowcount
            conn.commit()

            return {"ok": True, "domain": domain, "count": count}

        finally:
            conn.close()

    def increment_hit_count(self, domain: str, selector: str):
        """Increment hit count when element is hidden."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                UPDATE hidden_elements
                SET hit_count = hit_count + 1, last_updated = ?
                WHERE domain = ? AND selector = ?
            """,
                (int(time.time()), domain, selector),
            )
            conn.commit()

        finally:
            conn.close()

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Total hidden elements
            cursor.execute("SELECT COUNT(*) FROM hidden_elements")
            total_elements = cursor.fetchone()[0]

            # Total domains with hidden elements
            cursor.execute("SELECT COUNT(DISTINCT domain) FROM hidden_elements")
            total_domains = cursor.fetchone()[0]

            # Most hidden elements by domain
            cursor.execute(
                """
                SELECT domain, COUNT(*) as count
                FROM hidden_elements
                GROUP BY domain
                ORDER BY count DESC
                LIMIT 5
            """
            )
            top_domains = [
                {"domain": row[0], "count": row[1]} for row in cursor.fetchall()
            ]

            return {
                "ok": True,
                "total_elements": total_elements,
                "total_domains": total_domains,
                "top_domains": top_domains,
                "database_path": str(self.db_path),
            }

        finally:
            conn.close()


# Global singleton instance
_persistence_service: PersistenceService | None = None


def get_persistence_service() -> PersistenceService:
    """Get the persistence service singleton."""
    global _persistence_service
    if _persistence_service is None:
        _persistence_service = PersistenceService()
    return _persistence_service
