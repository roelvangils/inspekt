"""
Domain management service.

Manages allowed domains in SQLite database:
- Add/remove allowed domains
- Check if domain is allowed
- Auto-sync with browser extension storage
- Subdomain matching support
- Domain normalization (strips www. prefix)
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from typing import Any

from inspekt.config import get_data_dir


def normalize_domain(domain: str) -> str:
    """
    Normalize a domain name for storage.

    - Strips 'www.' prefix (since subdomains are automatically allowed)
    - Converts to lowercase
    - Strips whitespace

    Examples:
        www.github.com -> github.com
        WWW.Example.COM -> example.com
        api.github.com -> api.github.com (preserved, not www)
    """
    domain = domain.strip().lower()

    # Strip www. prefix - subdomains are allowed when parent is allowed
    if domain.startswith("www."):
        domain = domain[4:]

    return domain


class DomainService:
    """Manages allowed domains storage and validation."""

    def __init__(self):
        """Initialize domain service."""
        self.db_path = get_data_dir() / "data.db"
        self._ensure_yolo_table()

    def _ensure_yolo_table(self) -> None:
        """Ensure yolo_mode table exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS yolo_mode (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    enabled INTEGER DEFAULT 0,
                    expires_at INTEGER,
                    CHECK (id = 1)
                )
            """)
            conn.commit()
        finally:
            conn.close()

    def enable_yolo_mode(self, duration_minutes: int = 60) -> dict[str, Any]:
        """
        Enable yolo mode (bypass all domain checks) for specified duration.

        Args:
            duration_minutes: How long to enable yolo mode (default: 60 minutes)

        Returns:
            {"ok": True, "expires_at": unix_timestamp}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            expires_at = int(time.time()) + (duration_minutes * 60)
            cursor.execute("""
                INSERT OR REPLACE INTO yolo_mode (id, enabled, expires_at)
                VALUES (1, 1, ?)
            """, (expires_at,))
            conn.commit()
            return {"ok": True, "expires_at": expires_at, "duration_minutes": duration_minutes}
        finally:
            conn.close()

    def disable_yolo_mode(self) -> dict[str, Any]:
        """Disable yolo mode."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE yolo_mode SET enabled = 0 WHERE id = 1")
            conn.commit()
            return {"ok": True, "enabled": False}
        finally:
            conn.close()

    def is_yolo_mode_active(self) -> bool:
        """
        Check if yolo mode is currently active (not expired).

        Automatically disables yolo mode if expired.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT enabled, expires_at FROM yolo_mode WHERE id = 1")
            row = cursor.fetchone()

            if not row or not row[0]:
                return False

            # Check if expired
            expires_at = row[1]
            if expires_at and int(time.time()) >= expires_at:
                # Auto-disable expired yolo mode
                cursor.execute("UPDATE yolo_mode SET enabled = 0 WHERE id = 1")
                conn.commit()
                return False

            return True
        except Exception:
            return False
        finally:
            conn.close()

    def get_yolo_status(self) -> dict[str, Any]:
        """
        Get yolo mode status with remaining time.

        Returns:
            {"enabled": bool, "remaining_minutes": int, "expires_at": unix_timestamp}
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT enabled, expires_at FROM yolo_mode WHERE id = 1")
            row = cursor.fetchone()

            if not row or not row[0]:
                return {"enabled": False}

            expires_at = row[1]
            now = int(time.time())

            if now >= expires_at:
                return {"enabled": False}

            remaining_seconds = expires_at - now
            remaining_minutes = remaining_seconds // 60

            return {
                "enabled": True,
                "expires_at": expires_at,
                "remaining_minutes": remaining_minutes,
                "remaining_seconds": remaining_seconds
            }
        except Exception:
            return {"enabled": False}
        finally:
            conn.close()

    def add_domain(
        self, domain: str, permanent: bool = True
    ) -> dict[str, Any]:
        """Add domain to allowed list (normalized to base domain)."""
        normalized = normalize_domain(domain)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Check if already exists
            cursor.execute(
                "SELECT domain FROM allowed_domains WHERE domain = ?",
                (normalized,),
            )
            already_exists = cursor.fetchone() is not None

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
                (normalized, timestamp, 1 if permanent else 0),
            )

            conn.commit()

            return {
                "ok": True,
                "domain": normalized,
                "original": domain if domain != normalized else None,
                "permanent": permanent,
                "added_at": timestamp,
                "already_exists": already_exists,
            }

        finally:
            conn.close()

    def remove_domain(self, domain: str) -> dict[str, Any]:
        """Remove domain from allowed list (normalized to base domain)."""
        normalized = normalize_domain(domain)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM allowed_domains WHERE domain = ?",
                (normalized,),
            )

            deleted = cursor.rowcount > 0
            conn.commit()

            return {
                "ok": True,
                "deleted": deleted,
                "domain": normalized,
                "original": domain if domain != normalized else None,
            }

        finally:
            conn.close()

    def is_allowed(self, domain: str) -> bool:
        """
        Check if domain is allowed.

        Checks in order:
        1. Isolated mode - if active, all domains are allowed (Docker VM)
        2. Yolo mode - if active, all domains are allowed (time-limited)
        3. Domain list - checks if domain or parent domain is in allowed list

        Supports subdomain matching:
        - If 'github.com' is allowed, 'www.github.com' is also allowed
        - If 'api.github.com' is allowed, only 'api.github.com' is allowed

        The domain is normalized before checking.
        """
        # Check isolated mode first - bypasses ALL domain checks (Docker VM)
        from inspekt.config import is_isolated_mode
        if is_isolated_mode():
            return True

        # Check yolo mode - bypasses all domain checks (time-limited)
        if self.is_yolo_mode_active():
            return True

        # Normalize input (lowercase, strip whitespace)
        domain = domain.strip().lower()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Direct match (also try normalized version without www)
            normalized = normalize_domain(domain)
            cursor.execute(
                "SELECT domain FROM allowed_domains WHERE domain = ? OR domain = ?",
                (domain, normalized),
            )
            if cursor.fetchone():
                return True

            # Check parent domains (subdomain matching)
            # Example: For 'api.github.com', check 'github.com'
            parts = normalized.split(".")
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
                ORDER BY domain ASC
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

    def get_domains_for_browser_sync(self) -> dict[str, dict[str, Any]]:
        """
        Get all domains in browser extension storage format.

        Returns a dictionary suitable for chrome.storage.sync:
        {
            "github.com": {"addedAt": "2025-01-15T10:30:00Z", "permanent": true},
            "localhost": {"addedAt": "2025-01-14T08:15:00Z", "permanent": true}
        }
        """
        domains_list = self.get_all_domains()
        domains = {}

        for item in domains_list:
            # Convert Unix timestamp to ISO format
            dt = datetime.fromtimestamp(item["added_at"], tz=UTC)
            iso_timestamp = dt.isoformat().replace("+00:00", "Z")

            domains[item["domain"]] = {
                "addedAt": iso_timestamp,
                "permanent": item["permanent"]
            }

        return domains

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

        Domains are normalized (www. prefix stripped) before import.

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

                # Normalize domain
                domain = normalize_domain(domain)

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
