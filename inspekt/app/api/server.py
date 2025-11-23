"""HTTP API server for Inspekt CLI commands.

This server exposes all CLI commands as HTTP endpoints, allowing
browser automation and control via REST API calls.

Start the server with:
    uvicorn inspekt.app.api.server:app --host 127.0.0.1 --port 8000 --reload

Or use the CLI:
    inspekt api start
"""

import time
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from inspekt.services.bridge_executor import get_executor
from inspekt import __version__

# Configure logging to filter out /health endpoint requests
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1

# Apply filter to uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# API Server tracking
api_server_start_time = time.time()
total_api_requests = 0
total_api_succeeded = 0
total_api_failed = 0

# Create FastAPI app
app = FastAPI(
    title="Inspekt API",
    description="HTTP API for browser automation and control via command line",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Add CORS middleware (allow all origins for local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request tracking middleware
@app.middleware("http")
async def track_requests(request: Request, call_next):
    """Track API request statistics."""
    global total_api_requests, total_api_succeeded, total_api_failed

    # Don't track the health endpoint itself to avoid counting issues
    if request.url.path == "/health":
        return await call_next(request)

    total_api_requests += 1

    try:
        response = await call_next(request)

        # Count as success if status code is 2xx or 3xx
        if 200 <= response.status_code < 400:
            total_api_succeeded += 1
        else:
            total_api_failed += 1

        return response
    except Exception as e:
        total_api_failed += 1
        raise


# Exception handlers
@app.exception_handler(ConnectionError)
async def connection_error_handler(request, exc):
    """Handle bridge connection errors."""
    return JSONResponse(
        status_code=503,
        content={
            "ok": False,
            "error": f"Bridge server connection error: {str(exc)}",
            "detail": "Is the bridge server running? Start it with: inspekt server start",
        },
    )


@app.exception_handler(TimeoutError)
async def timeout_error_handler(request, exc):
    """Handle command timeout errors."""
    return JSONResponse(
        status_code=504, content={"ok": False, "error": f"Command timeout: {str(exc)}"}
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request, exc):
    """Handle runtime errors from command execution."""
    return JSONResponse(status_code=500, content={"ok": False, "error": f"Runtime error: {str(exc)}"})


# Health check endpoint
@app.get("/health")
async def health_check():
    """Check API server health and return statistics."""
    # Calculate uptime
    uptime_seconds = time.time() - api_server_start_time

    return {
        "api": "running",
        "api_version": __version__,
        "api_uptime_seconds": uptime_seconds,
        "api_total_requests": total_api_requests,
        "api_succeeded": total_api_succeeded,
        "api_failed": total_api_failed,
    }


@app.get("/")
async def root():
    """API root endpoint with basic info and links."""
    return {
        "name": "Inspekt API",
        "version": __version__,
        "description": "HTTP API for browser automation commands",
        "docs": "/docs",
        "health": "/health",
        "status": "/status",
        "endpoints": {
            "navigation": "/api/navigation/*",
            "extraction": "/api/extraction/*",
            "execution": "/api/execution/*",
            "interaction": "/api/interaction/*",
            "inspection": "/api/inspection/*",
            "selection": "/api/selection/*",
            "cookies": "/api/cookies/*",
            "storage": "/api/storage/*",
            "persistence": "/api/persistence/*",
            "accessibility": "/api/accessibility/*",
        },
    }


@app.get("/status", response_class=HTMLResponse)
async def status_dashboard():
    """Live status dashboard showing bridge and API server health."""
    # Read the dashboard HTML file
    dashboard_path = Path(__file__).parent / "dashboard.html"
    try:
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>Dashboard not found</h1><p>dashboard.html file is missing</p>",
            status_code=500
        )


# Import and register routers
from inspekt.app.api.routers import (
    navigation,
    execution,
    extraction,
    interaction,
    inspection,
    selection,
    cookies,
    storage,
    domains,
    robots,
    persistence,
    accessibility,
)

app.include_router(navigation.router, prefix="/api/navigation", tags=["Navigation"])
app.include_router(execution.router, prefix="/api/execution", tags=["Execution"])
app.include_router(extraction.router, prefix="/api/extraction", tags=["Extraction"])
app.include_router(interaction.router, prefix="/api/interaction", tags=["Interaction"])
app.include_router(inspection.router, prefix="/api/inspection", tags=["Inspection"])
app.include_router(selection.router, prefix="/api/selection", tags=["Selection"])
app.include_router(cookies.router, prefix="/api/cookies", tags=["Cookies"])
app.include_router(storage.router, prefix="/api/storage", tags=["Storage"])
app.include_router(domains.router, prefix="/api/domains", tags=["Domains"])
app.include_router(robots.router, prefix="/api/robots", tags=["Robots"])
app.include_router(persistence.router, prefix="/api/persistence", tags=["Persistence"])
app.include_router(accessibility.router, prefix="/api/accessibility", tags=["Accessibility"])
