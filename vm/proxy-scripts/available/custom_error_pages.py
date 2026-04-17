"""Serve branded error pages for plain HTTP requests.

For HTTPS, error pages are handled by the control panel's navigateTo()
function, which pre-checks DNS before sending Page.navigate to Chromium.
This addon handles the plain HTTP case via the request() hook, plus
optionally replaces HTTP 4xx/5xx error responses.

HTML templates are read from /opt/pages/ and support these placeholders:
  {{URL}}         — Full URL that was requested
  {{DOMAIN}}      — Hostname extracted from the URL
  {{STATUS}}      — HTTP status code (e.g. 404)
  {{STATUS_TEXT}} — HTTP status text (e.g. Not Found)
  {{ERROR_CODE}}  — Error code string (e.g. ERR_NAME_NOT_RESOLVED)

Templates are plain HTML files you can freely customise.
Location: docker/browser-vm/pages/

Config:
  intercept_http_errors: bool — Replace HTTP 4xx/5xx pages (default: false)
  http_error_min_status: int — Minimum status code to intercept (default: 502)
"""

import logging
import socket
import time
from pathlib import Path

from mitmproxy import http

logger = logging.getLogger("custom_error_pages")

PAGES_DIR = Path("/opt/pages")

# DNS cache with TTL to avoid stale entries
_dns_cache: dict[str, tuple[bool, float]] = {}  # domain -> (resolves, timestamp)
_DNS_CACHE_TTL = 60  # seconds

# Standard HTTP status texts
STATUS_TEXTS = {
    400: "Bad Request", 401: "Unauthorized", 403: "Forbidden",
    404: "Not Found", 408: "Request Timeout", 410: "Gone",
    429: "Too Many Requests", 500: "Internal Server Error",
    502: "Bad Gateway", 503: "Service Unavailable", 504: "Gateway Timeout",
}


def _load_template(name: str) -> str | None:
    """Load an HTML template from the pages directory."""
    path = PAGES_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    return None


def _fill_template(html: str, **kwargs) -> str:
    """Replace {{PLACEHOLDER}} tokens in the template."""
    for key, value in kwargs.items():
        html = html.replace("{{" + key.upper() + "}}", str(value))
    return html


def _get_domain(flow: http.HTTPFlow) -> str:
    """Extract the hostname from a flow's request."""
    try:
        return flow.request.pretty_host
    except Exception:
        return "unknown"


def _is_html_request(flow: http.HTTPFlow) -> bool:
    """Check if the request likely expects an HTML response."""
    accept = flow.request.headers.get("accept", "")
    if "text/html" in accept:
        return True
    path = flow.request.path
    if "." not in path.split("/")[-1]:
        return True
    return False


def _can_resolve(domain: str) -> bool:
    """Check if a domain resolves via DNS. Results are cached with TTL."""
    now = time.time()
    if domain in _dns_cache:
        resolves, ts = _dns_cache[domain]
        if now - ts < _DNS_CACHE_TTL:
            return resolves
    try:
        socket.getaddrinfo(domain, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        _dns_cache[domain] = (True, now)
        return True
    except socket.gaierror:
        _dns_cache[domain] = (False, now)
        return False


class CustomErrorPages:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.intercept_http_errors = config.get("intercept_http_errors", False)
        self.http_error_min_status = config.get("http_error_min_status", 502)

    def configure(self, config: dict):
        self.intercept_http_errors = config.get("intercept_http_errors", False)
        self.http_error_min_status = config.get("http_error_min_status", 502)

    def request(self, flow: http.HTTPFlow):
        """Pre-check DNS for plain HTTP requests."""
        if not _is_html_request(flow):
            return

        domain = _get_domain(flow)
        if domain in ("localhost", "127.0.0.1", "inspekt", "0.0.0.0"):
            return

        if not _can_resolve(domain):
            template = _load_template("error-dns.html")
            if not template:
                return
            url = flow.request.pretty_url
            html = _fill_template(template, url=url, domain=domain)
            flow.response = http.Response.make(
                200,
                html.encode("utf-8"),
                {
                    "Content-Type": "text/html; charset=utf-8",
                    "X-Inspekt-Error-Page": "ERR_NAME_NOT_RESOLVED",
                },
            )

    def response(self, flow: http.HTTPFlow):
        """Optionally replace HTTP error responses (4xx/5xx) with branded pages."""
        if not self.intercept_http_errors:
            return

        if not flow.response or flow.response.status_code < self.http_error_min_status:
            return

        if not _is_html_request(flow):
            return

        # Don't replace responses that have substantial content (custom 404 pages)
        if len(flow.response.content or b"") > 1024:
            return

        status = flow.response.status_code
        status_text = STATUS_TEXTS.get(status, "Error")
        domain = _get_domain(flow)
        url = flow.request.pretty_url

        template = _load_template("error-http.html")
        if not template:
            return

        html = _fill_template(
            template, url=url, domain=domain,
            status=str(status), status_text=status_text,
        )

        flow.response.content = html.encode("utf-8")
        flow.response.headers["Content-Type"] = "text/html; charset=utf-8"
        flow.response.headers["X-Inspekt-Error-Page"] = str(status)
