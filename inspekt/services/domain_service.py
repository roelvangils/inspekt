"""
Domain management service.

Manages allowed domains in SQLite database:
- Add/remove allowed domains
- Check if domain is allowed
- Sync with browser extension storage
- Subdomain matching support
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from inspekt.config import find_config_file


class DomainService:
    """Manages allowed domains storage and validation."""

    def __init__(self):
        """Initialize domain service."""
        # Use same database as persistence service
        config_file = find_config_file()
        if config_file:
            config_dir = config_file.parent
        else:
            config_dir = Path.home() / ".inspekt"
            config_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = config_dir / "data.db"

    def add_domain(
        self, domain: str, permanent: bool = True
    ) -> dict[str, Any]:
        """Add domain to allowed list."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            timestamp = int(time.time())

            cursor.execute(
                """
                INSERT INTO allowed_domains (domain, added_at, permanent)
                VALUES (?, ?, ?)
                ON CONFLICT(domain)
                DO UPDATE SET
                    permanent = excluded.permanent,
                    added_at = excluded.added_at
            """,
                (domain, timestamp, 1 if permanent else 0),
            )

            conn.commit()

            return {
                "ok": True,
                "domain": domain,
                "permanent": permanent,
                "added_at": timestamp,
            }

        finally:
            conn.close()

    def remove_domain(self, domain: str) -> dict[str, Any]:
        """Remove domain from allowed list."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM allowed_domains WHERE domain = ?",
                (domain,),
            )

            deleted = cursor.rowcount > 0
            conn.commit()

            return {
                "ok": True,
                "deleted": deleted,
                "domain": domain,
            }

        finally:
            conn.close()

    def is_allowed(self, domain: str) -> bool:
        """
        Check if domain is allowed.

        Supports subdomain matching:
        - If 'github.com' is allowed, 'www.github.com' is also allowed
        - If 'api.github.com' is allowed, only 'api.github.com' is allowed
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Direct match
            cursor.execute(
                "SELECT domain FROM allowed_domains WHERE domain = ?",
                (domain,),
            )
            if cursor.fetchone():
                return True

            # Check parent domains (subdomain matching)
            # Example: For 'www.github.com', check 'github.com'
            parts = domain.split(".")
            for i in range(1, len(parts)):
                parent_domain = ".".join(parts[i:])
                cursor.execute(
                    "SELECT domain FROM allowed_domains WHERE domain = ?",
                    (parent_domain,),
                )
                if cursor.fetchone():
                    return True

            return False

        finally:
            conn.close()

    def get_all_domains(self) -> list[dict[str, Any]]:
        """Get all allowed domains."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT domain, added_at, permanent
                FROM allowed_domains
                ORDER BY added_at DESC
            """
            )

            rows = cursor.fetchall()

            return [
                {
                    "domain": row[0],
                    "added_at": row[1],
                    "permanent": bool(row[2]),
                }
                for row in rows
            ]

        finally:
            conn.close()

    def clear_all_domains(self) -> dict[str, Any]:
        """Remove all allowed domains."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM allowed_domains")
            count = cursor.rowcount
            conn.commit()

            return {"ok": True, "count": count}

        finally:
            conn.close()

    def import_domains(
        self, domains: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Import domains from browser storage format.

        Expected format:
        [
            {"domain": "github.com", "addedAt": "2025-01-15T10:30:00Z", "permanent": true},
            {"domain": "localhost", "addedAt": "2025-01-14T08:15:00Z", "permanent": true}
        ]
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            imported = 0
            for item in domains:
                domain = item.get("domain")
                if not domain:
                    continue

                # Convert ISO timestamp to Unix timestamp if needed
                added_at = item.get("addedAt", item.get("added_at"))
                if isinstance(added_at, str):
                    # ISO format - use current time as fallback
                    added_at = int(time.time())
                elif isinstance(added_at, (int, float)):
                    added_at = int(added_at)
                else:
                    added_at = int(time.time())

                permanent = item.get("permanent", True)

                cursor.execute(
                    """
                    INSERT INTO allowed_domains (domain, added_at, permanent)
                    VALUES (?, ?, ?)
                    ON CONFLICT(domain) DO NOTHING
                """,
                    (domain, added_at, 1 if permanent else 0),
                )

                if cursor.rowcount > 0:
                    imported += 1

            conn.commit()

            return {
                "ok": True,
                "imported": imported,
                "total": len(domains),
            }

        finally:
            conn.close()


# Global singleton instance
_domain_service: DomainService | None = None


def get_domain_service() -> DomainService:
    """Get the domain service singleton."""
    global _domain_service
    if _domain_service is None:
        _domain_service = DomainService()
    return _domain_service
