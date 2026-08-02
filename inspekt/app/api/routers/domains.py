"""Domain Management API endpoints.

This module provides HTTP API endpoints for managing allowed domains
for browser automation.

Domain management uses SQLite as the primary storage, with automatic sync
to browser extension storage.
"""

from datetime import UTC

import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from inspekt.services.domain_service import get_domain_service

router = APIRouter()

# Bridge server configuration (same as in domain.py CLI)
BRIDGE_HTTP_HOST = "127.0.0.1"
BRIDGE_HTTP_PORT = 8765


# ============================================================================
# Request/Response Models
# ============================================================================


class DomainAddRequest(BaseModel):
    """Request model for adding a domain."""

    domain: str = Field(..., description="Domain name to add to the allow list")

    model_config = {"json_schema_extra": {"example": {"domain": "github.com"}}}


class DomainRemoveRequest(BaseModel):
    """Request model for removing a domain."""

    domain: str = Field(..., description="Domain name to remove from the allow list")

    model_config = {"json_schema_extra": {"example": {"domain": "github.com"}}}


class DomainBypassRequest(BaseModel):
    """Request model for setting temporary bypass."""

    duration: int = Field(
        ..., description="Duration in minutes (0 to disable, -1 to get status only)"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [{"duration": 15}, {"duration": 60}, {"duration": 0}, {"duration": -1}]
        }
    }


class DomainAddResponse(BaseModel):
    """Response model for add domain operation."""

    ok: bool
    already_exists: bool | None = None
    error: str | None = None


class DomainRemoveResponse(BaseModel):
    """Response model for remove domain operation."""

    ok: bool
    not_found: bool | None = None
    error: str | None = None


class DomainListResponse(BaseModel):
    """Response model for list domains operation."""

    ok: bool
    domains: dict | None = None
    error: str | None = None


class DomainBypassResponse(BaseModel):
    """Response model for bypass operation."""

    ok: bool
    enabled: bool | None = None
    expiresAt: str | None = None
    remainingMinutes: int | None = None
    error: str | None = None


class CspGlobalRequest(BaseModel):
    """Request model for global CSP bypass."""

    enabled: bool = Field(..., description="Enable or disable global CSP bypass")

    model_config = {"json_schema_extra": {"examples": [{"enabled": True}, {"enabled": False}]}}


class CspGlobalResponse(BaseModel):
    """Response model for global CSP bypass operation."""

    ok: bool
    enabled: bool | None = None
    enabledAt: str | None = None
    error: str | None = None


# ============================================================================
# API Endpoints
# ============================================================================


@router.post("/add", response_model=DomainAddResponse)
def add_domain(request: DomainAddRequest):
    """
    Add a domain to the allowed list.

    The domain will be added to SQLite database and synced to browser extension storage.
    Parent domains grant access to subdomains (e.g., github.com allows www.github.com).

    Args:
        request: Domain add request with domain name

    Returns:
        Success/failure status with optional flags

    Raises:
        HTTPException: If database operation fails or sync fails

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/domains/add \\
          -H "Content-Type: application/json" \\
          -d '{"domain": "github.com"}'
        ```

        Response:
        ```json
        {
          "ok": true,
          "already_exists": false
        }
        ```
    """
    try:
        domain_service = get_domain_service()

        # Check if domain already exists
        already_exists = domain_service.is_allowed(request.domain)

        # Add to SQLite
        result = domain_service.add_domain(request.domain)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail="Failed to add domain to database")

        # Sync to browser extension
        _sync_domains_to_browser()

        return {"ok": True, "already_exists": already_exists}

    except HTTPException:
        # Already well-formed (e.g. 503 from bridge proxy) — don't rewrap as 500
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")


@router.delete("/remove", response_model=DomainRemoveResponse)
def remove_domain(request: DomainRemoveRequest):
    """
    Remove a domain from the allowed list.

    The domain will be removed from SQLite database and synced to browser extension storage.

    Args:
        request: Domain remove request with domain name

    Returns:
        Success/failure status with optional flags

    Raises:
        HTTPException: If database operation fails or sync fails

    Examples:
        ```bash
        curl -X DELETE http://localhost:8000/api/domains/remove \\
          -H "Content-Type: application/json" \\
          -d '{"domain": "github.com"}'
        ```

        Response:
        ```json
        {
          "ok": true,
          "not_found": false
        }
        ```
    """
    try:
        domain_service = get_domain_service()

        # Remove from SQLite
        result = domain_service.remove_domain(request.domain)

        if not result.get("ok"):
            raise HTTPException(status_code=500, detail="Failed to remove domain from database")

        not_found = not result.get("deleted", False)

        # Sync to browser extension
        _sync_domains_to_browser()

        return {"ok": True, "not_found": not_found}

    except HTTPException:
        # Already well-formed (e.g. 503 from bridge proxy) — don't rewrap as 500
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")


@router.get("/list", response_model=DomainListResponse)
def list_domains():
    """
    List all allowed domains.

    Returns all domains from SQLite database with their metadata including
    timestamps and other properties.

    Returns:
        Dictionary of domains with metadata

    Raises:
        HTTPException: If database operation fails

    Examples:
        ```bash
        curl http://localhost:8000/api/domains/list
        ```

        Response:
        ```json
        {
          "ok": true,
          "domains": {
            "github.com": {
              "addedAt": "2024-01-15T10:30:00Z",
              "permanent": true
            },
            "localhost": {
              "addedAt": "2024-01-14T08:15:00Z",
              "permanent": true
            }
          }
        }
        ```
    """
    try:
        from datetime import datetime

        domain_service = get_domain_service()

        # Get all domains from SQLite
        domains_list = domain_service.get_all_domains()

        # Convert to the expected format
        domains = {}
        for item in domains_list:
            # Convert Unix timestamp to ISO format
            dt = datetime.fromtimestamp(item["added_at"], tz=UTC)
            iso_timestamp = dt.isoformat().replace("+00:00", "Z")

            domains[item["domain"]] = {"addedAt": iso_timestamp, "permanent": item["permanent"]}

        return {"ok": True, "domains": domains}

    except HTTPException:
        # Already well-formed (e.g. 503 from bridge proxy) — don't rewrap as 500
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")


@router.post("/bypass", response_model=DomainBypassResponse)
def set_bypass(request: DomainBypassRequest):
    """
    Set or query temporary bypass for all domains.

    Allows all domains for the specified duration in minutes. When bypass is active,
    the extension will allow automation on any domain regardless of the allow list.

    Special values:
    - duration=0: Disable bypass
    - duration=-1: Query current bypass status without modifying it

    Args:
        request: Bypass request with duration in minutes

    Returns:
        Bypass status including enabled flag, expiration time, and remaining minutes

    Raises:
        HTTPException: If bridge server is unreachable or request fails

    Examples:
        ```bash
        # Enable bypass for 15 minutes
        curl -X POST http://localhost:8000/api/domains/bypass \\
          -H "Content-Type: application/json" \\
          -d '{"duration": 15}'

        # Check bypass status
        curl -X POST http://localhost:8000/api/domains/bypass \\
          -H "Content-Type: application/json" \\
          -d '{"duration": -1}'

        # Disable bypass
        curl -X POST http://localhost:8000/api/domains/bypass \\
          -H "Content-Type: application/json" \\
          -d '{"duration": 0}'
        ```

        Response (active):
        ```json
        {
          "ok": true,
          "enabled": true,
          "expiresAt": "2024-01-15T11:45:00Z",
          "remainingMinutes": 12
        }
        ```

        Response (inactive):
        ```json
        {
          "ok": true,
          "enabled": false
        }
        ```
    """
    try:
        import requests

        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/bypass",
            json={"duration": request.duration},
            timeout=10.0,
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Bridge server returned HTTP {response.status_code}",
            )

    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to bridge server. Ensure server is running: inspekt start",
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request to bridge server timed out")
    except HTTPException:
        # Already well-formed (e.g. 503 from bridge proxy) — don't rewrap as 500
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")


@router.post("/sync")
def sync_domains():
    """
    Sync allowed domains from SQLite to browser extension storage.

    This endpoint triggers a sync operation that sends all domains from the SQLite
    database to the browser extension's chrome.storage.sync.

    Returns:
        Success status

    Raises:
        HTTPException: If sync operation fails

    Examples:
        ```bash
        curl -X POST http://localhost:8000/api/domains/sync
        ```

        Response:
        ```json
        {
          "ok": true,
          "synced": 5
        }
        ```
    """
    try:
        result = _sync_domains_to_browser()
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {e!s}")


@router.post("/csp-global", response_model=CspGlobalResponse)
def toggle_global_csp(request: CspGlobalRequest):
    """
    Enable or disable global CSP bypass for all domains.

    When enabled, Content Security Policy headers are stripped from all responses,
    allowing scripts to run on sites with strict CSP policies.

    Args:
        request: CSP global request with enabled flag

    Returns:
        Success status with current enabled state

    Raises:
        HTTPException: If bridge server is unreachable or request fails

    Examples:
        ```bash
        # Enable global CSP bypass
        curl -X POST http://localhost:8000/api/domains/csp-global \\
          -H "Content-Type: application/json" \\
          -d '{"enabled": true}'

        # Disable global CSP bypass
        curl -X POST http://localhost:8000/api/domains/csp-global \\
          -H "Content-Type: application/json" \\
          -d '{"enabled": false}'
        ```

        Response:
        ```json
        {
          "ok": true,
          "enabled": true
        }
        ```
    """
    try:
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/csp/global",
            json={"enabled": request.enabled},
            timeout=10.0,
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Bridge server returned HTTP {response.status_code}",
            )

    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to bridge server. Ensure server is running: inspekt start",
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request to bridge server timed out")
    except HTTPException:
        # Already well-formed (e.g. 503 from bridge proxy) — don't rewrap as 500
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")


@router.get("/csp-global", response_model=CspGlobalResponse)
def get_global_csp_status():
    """
    Get the current global CSP bypass status.

    Returns:
        Current enabled state of global CSP bypass

    Raises:
        HTTPException: If bridge server is unreachable or request fails

    Examples:
        ```bash
        curl http://localhost:8000/api/domains/csp-global
        ```

        Response:
        ```json
        {
          "ok": true,
          "enabled": true,
          "enabledAt": "2024-01-15T10:30:00Z"
        }
        ```
    """
    try:
        response = requests.get(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/csp/global", timeout=10.0
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Bridge server returned HTTP {response.status_code}",
            )

    except requests.exceptions.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="Could not connect to bridge server. Ensure server is running: inspekt start",
        )
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Request to bridge server timed out")
    except HTTPException:
        # Already well-formed (e.g. 503 from bridge proxy) — don't rewrap as 500
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {e!s}")


# ============================================================================
# Helper Functions
# ============================================================================


def _sync_domains_to_browser():
    """
    Sync allowed domains from SQLite to browser extension storage.

    Sends a SYNC_ALLOWED_DOMAINS message to the bridge server, which forwards
    the domain list to all connected browser extensions.
    """
    try:
        domain_service = get_domain_service()

        # Get all domains from SQLite
        domains_list = domain_service.get_all_domains()

        # Convert to browser storage format
        from datetime import datetime

        domains = {}
        for item in domains_list:
            # Convert Unix timestamp to ISO format
            dt = datetime.fromtimestamp(item["added_at"], tz=UTC)
            iso_timestamp = dt.isoformat().replace("+00:00", "Z")

            domains[item["domain"]] = {"addedAt": iso_timestamp, "permanent": item["permanent"]}

        # Send sync request to bridge server
        response = requests.post(
            f"http://{BRIDGE_HTTP_HOST}:{BRIDGE_HTTP_PORT}/domains/sync",
            json={"domains": domains},
            timeout=10.0,
        )

        if response.status_code == 200:
            return {"ok": True, "synced": len(domains)}
        else:
            # Sync failed, but don't raise error (graceful degradation)
            return {"ok": False, "error": f"Bridge server returned HTTP {response.status_code}"}

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        # Bridge server not available, but domain was saved to SQLite
        # This is okay - sync will happen when server starts
        return {"ok": False, "error": "Bridge server not available (domain saved to database)"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
