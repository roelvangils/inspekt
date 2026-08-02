"""HTTP API server for Inspekt CLI commands.

This server exposes all CLI commands as HTTP endpoints, allowing
browser automation and control via REST API calls.

Start the server with:
    uvicorn inspekt.app.api.server:app --host 127.0.0.1 --port 8000 --reload

Or use the CLI:
    inspekt api start
"""

import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from inspekt import __version__
from inspekt.app.api.routers import (
    accessibility,
    browser,
    commands,
    cookies,
    display,
    domains,
    execution,
    extraction,
    inspection,
    interaction,
    navigation,
    network,
    persistence,
    plugins,
    robots,
    selection,
    storage,
)
from inspekt.app.api.routers import (
    sitemap as sitemap_router,
)

# Set up Jinja2 templates
templates_dir = Path(__file__).parent
templates = Jinja2Templates(directory=str(templates_dir))

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
    except Exception:
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
            "error": f"Bridge server connection error: {exc!s}",
            "detail": "Is the bridge server running? Start it with: inspekt start",
        },
    )


@app.exception_handler(TimeoutError)
async def timeout_error_handler(request, exc):
    """Handle command timeout errors."""
    return JSONResponse(
        status_code=504, content={"ok": False, "error": f"Command timeout: {exc!s}"}
    )


@app.exception_handler(RuntimeError)
async def runtime_error_handler(request, exc):
    """Handle runtime errors from command execution."""
    return JSONResponse(status_code=500, content={"ok": False, "error": f"Runtime error: {exc!s}"})


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


@app.get("/error/{page_name}")
async def error_page(page_name: str, request: Request):
    """Serve custom error pages (e.g. /error/dns?domain=example.com).

    Templates live in /opt/pages/ with placeholders like {{DOMAIN}}.
    Used by the control panel for DNS failures and blocked URLs.
    """
    import html as html_module

    # Whitelist of known error pages — prevents path traversal and arbitrary file reads
    ALLOWED_PAGES = {"dns", "connection", "http", "blocked"}
    safe_name = page_name.replace("/", "").replace("..", "")
    if safe_name not in ALLOWED_PAGES:
        raise HTTPException(status_code=404, detail=f"Unknown error page: {safe_name}")

    template_path = Path("/opt/pages") / f"error-{safe_name}.html"

    if not template_path.exists():
        raise HTTPException(status_code=404, detail=f"Error page template missing: {safe_name}")

    html = template_path.read_text(encoding="utf-8")

    # Fill placeholders from query params
    for key in ("url", "domain", "status", "status_text", "error_code", "message"):
        value = request.query_params.get(key, "")
        html = html.replace("{{" + key.upper() + "}}", html_module.escape(value))

    return HTMLResponse(content=html)


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
            "network": "/api/network/*",
            "plugins": "/api/plugins/*",
        },
        "ui": {
            "status": "/status",
            "plugins": "/plugins",
        },
    }


@app.get("/status", response_class=HTMLResponse)
async def status_dashboard(request: Request):
    """Live status dashboard showing bridge and API server health."""
    try:
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"active_page": "dashboard"}
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Dashboard not found</h1><p>Error: {e}</p>",
            status_code=500
        )


# Register routers
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
app.include_router(network.router, prefix="/api/network", tags=["Network"])
app.include_router(plugins.router, prefix="/api/plugins", tags=["Plugins"])
app.include_router(browser.router, prefix="/api/browser", tags=["Browser"])
app.include_router(commands.router, prefix="/api/commands", tags=["Commands"])
app.include_router(display.router, prefix="/api/display", tags=["Display"])
app.include_router(sitemap_router.router, prefix="/api/sitemaps", tags=["Sitemaps"])


@app.get("/plugins", response_class=HTMLResponse)
async def plugins_ui(request: Request):
    """Plugin management UI."""
    try:
        return templates.TemplateResponse(
            request=request,
            name="plugins.html",
            context={"active_page": "plugins"}
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Plugins UI not found</h1><p>Error: {e}</p>",
            status_code=500
        )


@app.get("/commands", response_class=HTMLResponse)
async def commands_ui(request: Request):
    """Commands dashboard UI - view and manage all Inspekt commands."""
    try:
        return templates.TemplateResponse(
            request=request,
            name="commands.html",
            context={"active_page": "commands"}
        )
    except Exception as e:
        return HTMLResponse(
            content=f"<h1>Commands UI not found</h1><p>Error: {e}</p>",
            status_code=500
        )


# Mount static files for gallery assets (CSS, JS)
# This serves files from inspekt/static/ at /static/
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount the VM web root last so registered routes keep precedence.
# Galleries, reports and other generated artifacts are written under
# /home/inspekt/www/<kind>/<slug>/ and reachable at http://inspekt/<kind>/<slug>/.
www_root = Path("/home/inspekt/www")
if www_root.exists():
    app.mount("/", StaticFiles(directory=str(www_root), html=True), name="www")
