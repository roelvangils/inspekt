"""
Proxy-aware HTTP client for VM restricted mode.

When INSPEKT_RESTRICTED=1 (set by terminal-server.py in the VM),
HTTP requests are routed through the bridge's /proxy endpoint,
which runs as root and is exempt from iptables restrictions.

In normal desktop mode, requests pass straight through to the
`requests` library with zero overhead.

Usage:
    from inspekt.services import http_client

    # Same API as requests.get / requests.post
    response = http_client.get("https://example.com/api")
    response = http_client.post("https://api.example.com/v1", json={"key": "value"})
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Iterator

import requests

from inspekt.config import get_bridge_port

# Detect restricted mode once at import time
_RESTRICTED = os.environ.get("INSPEKT_RESTRICTED") == "1"


class ProxyResponse:
    """
    Wraps the bridge /proxy JSON response to mimic requests.Response.

    This allows callers to use the same interface regardless of whether
    the request went through the proxy or directly via requests.
    """

    def __init__(self, data: dict[str, Any]):
        self.status_code: int = data.get("status", 0)
        self._headers: dict[str, str] = data.get("headers", {})
        self._body: str = data.get("body", "")
        self._binary: bool = data.get("binary", False)
        self._content: bytes | None = None
        self.url: str = data.get("url", "")
        self.encoding: str | None = self._detect_encoding()

    def _detect_encoding(self) -> str | None:
        """Detect encoding from Content-Type header."""
        content_type = self._headers.get("Content-Type", "")
        if "charset=" in content_type:
            return content_type.split("charset=")[-1].split(";")[0].strip()
        return None

    @property
    def headers(self) -> dict[str, str]:
        return self._headers

    @property
    def text(self) -> str:
        """Response body as text."""
        if self._binary:
            return base64.b64decode(self._body).decode("utf-8", errors="replace")
        return self._body

    @property
    def content(self) -> bytes:
        """Response body as bytes."""
        if self._content is None:
            if self._binary:
                self._content = base64.b64decode(self._body)
            else:
                self._content = self._body.encode("utf-8")
        return self._content

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 400

    def json(self, **kwargs: Any) -> Any:
        """Parse response body as JSON."""
        return json.loads(self.text, **kwargs)

    def raise_for_status(self) -> None:
        """Raise requests.HTTPError if status >= 400."""
        if self.status_code >= 400:
            raise requests.HTTPError(
                f"{self.status_code} Error",
                response=self,  # type: ignore[arg-type]
            )

    def iter_content(self, chunk_size: int = 1024) -> Iterator[bytes]:
        """
        Yield content in chunks.

        In proxy mode the response is already fully buffered,
        so this just chunks the bytes for streaming-compatible callers.
        """
        data = self.content
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def close(self) -> None:
        """No-op for proxy responses (already fully buffered)."""
        pass


def _proxy_request(method: str, url: str, **kwargs: Any) -> ProxyResponse:
    """
    Send an HTTP request through the bridge /proxy endpoint.

    Translates requests-style kwargs into the proxy's JSON payload.
    """
    bridge_port = get_bridge_port()
    proxy_url = f"http://127.0.0.1:{bridge_port}/proxy"

    # Build proxy payload
    payload: dict[str, Any] = {
        "url": url,
        "method": method.upper(),
    }

    # Map requests kwargs to proxy payload
    headers = kwargs.get("headers", {})
    if headers:
        payload["headers"] = dict(headers)

    timeout = kwargs.get("timeout")
    if timeout is not None:
        payload["timeout"] = timeout

    # Handle body: json kwarg takes precedence, then data
    json_body = kwargs.get("json")
    data = kwargs.get("data")
    if json_body is not None:
        payload["body"] = json_body
    elif data is not None:
        payload["body"] = data

    # Pass max_bytes to limit response size on the server side
    max_bytes = kwargs.get("max_bytes")
    if max_bytes is not None:
        payload["max_bytes"] = max_bytes

    # Handle query params by appending to URL
    params = kwargs.get("params")
    if params:
        from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

        parsed = urlparse(url)
        existing = parse_qs(parsed.query)
        if isinstance(params, dict):
            existing.update({k: [v] for k, v in params.items()})
        query_string = urlencode(
            {k: v[0] if isinstance(v, list) and len(v) == 1 else v for k, v in existing.items()},
            doseq=True,
        )
        url = urlunparse(parsed._replace(query=query_string))
        payload["url"] = url

    try:
        resp = requests.post(proxy_url, json=payload, timeout=max(30, (timeout or 30) + 5))
        result = resp.json()
    except requests.ConnectionError:
        raise requests.ConnectionError(
            f"Cannot reach bridge proxy at {proxy_url}. Is 'inspekt start' running?"
        )
    except requests.Timeout:
        raise requests.Timeout(f"Bridge proxy at {proxy_url} timed out")

    if not result.get("ok"):
        error = result.get("error", "unknown error")
        error_type = result.get("error_type", "")

        if error_type == "timeout":
            raise requests.Timeout(f"Upstream timeout: {error}")
        elif error_type == "connection":
            raise requests.ConnectionError(f"Upstream connection error: {error}")
        else:
            raise requests.RequestException(f"Proxy error: {error}")

    return ProxyResponse(result)


def get(url: str, **kwargs: Any) -> requests.Response | ProxyResponse:
    """
    HTTP GET — drop-in replacement for requests.get().

    In restricted mode, routes through bridge /proxy.
    In normal mode, calls requests.get() directly.

    Extra kwarg `max_bytes` is only used in proxy mode to limit response size.
    """
    if _RESTRICTED:
        return _proxy_request("GET", url, **kwargs)
    # Strip proxy-only kwargs that requests doesn't understand
    kwargs.pop("max_bytes", None)
    return requests.get(url, **kwargs)


def post(url: str, **kwargs: Any) -> requests.Response | ProxyResponse:
    """
    HTTP POST — drop-in replacement for requests.post().

    In restricted mode, routes through bridge /proxy.
    In normal mode, calls requests.post() directly.
    """
    if _RESTRICTED:
        return _proxy_request("POST", url, **kwargs)
    return requests.post(url, **kwargs)


def head(url: str, **kwargs: Any) -> requests.Response | ProxyResponse:
    """
    HTTP HEAD — drop-in replacement for requests.head().

    In restricted mode, routes through bridge /proxy.
    In normal mode, calls requests.head() directly.
    """
    if _RESTRICTED:
        return _proxy_request("HEAD", url, **kwargs)
    return requests.head(url, **kwargs)
