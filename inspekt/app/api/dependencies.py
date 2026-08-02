"""Shared dependencies for API endpoints."""

from fastapi import HTTPException

from inspekt.client import BridgeClient
from inspekt.services.bridge_executor import get_executor


def get_bridge_executor():
    """Get bridge executor instance and ensure server is running."""
    executor = get_executor()

    if not executor.is_server_running():
        raise HTTPException(
            status_code=503, detail="Bridge server is not running. Start it with: inspekt start"
        )

    return executor


def get_bridge_client() -> BridgeClient:
    """Get bridge client instance and ensure server is running."""
    client = BridgeClient()

    if not client.is_alive():
        raise HTTPException(
            status_code=503, detail="Bridge server is not running. Start it with: inspekt start"
        )

    return client
