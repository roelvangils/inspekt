"""
Remote API server for headless browser operations.

Provides an HTTP API for running Inspekt commands in headless Chrome,
enabling cloud deployment and remote automation.

Run directly:
    python -m inspekt.services.headless.api

Or via Docker:
    docker-compose up -d api

API Endpoints:
    GET  /health              - Health check
    GET  /screenshot          - Capture screenshot
    GET  /accessibility       - Run accessibility audit
    GET  /index               - Index page content
    POST /execute             - Execute custom JavaScript
"""

import asyncio
import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from inspekt.services.headless import HeadlessChromePool, HeadlessContext


@dataclass
class APIResponse:
    """Standard API response format."""

    ok: bool
    data: Any | None = None
    error: str | None = None
    duration_ms: float | None = None

    def to_json(self) -> str:
        result = {"ok": self.ok}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return json.dumps(result)

    def to_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")


class HeadlessAPIServer:
    """
    HTTP API server for headless browser operations.

    Simple asyncio-based HTTP server that provides REST endpoints
    for common Inspekt operations.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8080):
        self.host = host
        self.port = port
        self._server = None
        self._start_time = time.time()
        self._request_count = 0

    async def start(self) -> None:
        """Start the HTTP server."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port,
        )

        print("Inspekt Headless API Server")
        print(f"Listening on http://{self.host}:{self.port}")
        print()
        print("Endpoints:")
        print("  GET  /health         - Health check")
        print("  GET  /screenshot     - Capture screenshot")
        print("  GET  /accessibility  - Run accessibility audit")
        print("  GET  /index          - Index page content")
        print("  POST /execute        - Execute custom JavaScript")
        print()

        # Pre-warm Chrome pool
        print("Warming up Chrome pool…")
        await HeadlessChromePool.warmup()
        print("Ready!")
        print()

        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop the server and clean up."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        await HeadlessChromePool.shutdown()

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming HTTP connection."""
        try:
            # Read request line
            request_line = await reader.readline()
            if not request_line:
                return

            request = request_line.decode("utf-8").strip()
            parts = request.split(" ")
            if len(parts) < 2:
                return

            method = parts[0]
            path_with_query = parts[1]

            # Parse path and query
            parsed = urlparse(path_with_query)
            path = parsed.path
            query = parse_qs(parsed.query)

            # Read headers
            headers = {}
            while True:
                line = await reader.readline()
                if line == b"\r\n" or line == b"\n" or not line:
                    break
                header = line.decode("utf-8").strip()
                if ": " in header:
                    key, value = header.split(": ", 1)
                    headers[key.lower()] = value

            # Read body for POST requests
            body = None
            if method == "POST" and "content-length" in headers:
                content_length = int(headers["content-length"])
                body = await reader.read(content_length)

            # Route request
            self._request_count += 1
            start_time = time.time()

            try:
                response = await self._route_request(method, path, query, body)
            except Exception as e:
                response = APIResponse(ok=False, error=str(e))

            duration_ms = (time.time() - start_time) * 1000
            response.duration_ms = duration_ms

            # Send response
            await self._send_response(writer, response)

        except Exception as e:
            print(f"Connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _route_request(
        self,
        method: str,
        path: str,
        query: dict,
        body: bytes | None,
    ) -> APIResponse:
        """Route request to appropriate handler."""
        # Extract common parameters
        url = query.get("url", [None])[0]

        if path == "/health":
            return await self._handle_health()

        elif path == "/screenshot":
            selector = query.get("selector", [None])[0]
            isolate = query.get("isolate", ["false"])[0].lower() == "true"
            format = query.get("format", ["png"])[0]
            return await self._handle_screenshot(url, selector, isolate, format)

        elif path == "/accessibility":
            level = query.get("level", ["21aa"])[0]
            return await self._handle_accessibility(url, level)

        elif path == "/index":
            return await self._handle_index(url)

        elif path == "/execute" and method == "POST":
            return await self._handle_execute(url, body)

        elif path == "/stats":
            return await self._handle_stats()

        else:
            return APIResponse(
                ok=False,
                error=f"Unknown endpoint: {method} {path}",
            )

    async def _handle_health(self) -> APIResponse:
        """Health check endpoint."""
        pool_stats = HeadlessChromePool.get_stats()
        return APIResponse(
            ok=True,
            data={
                "status": "healthy",
                "uptime_seconds": time.time() - self._start_time,
                "request_count": self._request_count,
                "chrome_pool": pool_stats,
            },
        )

    async def _handle_stats(self) -> APIResponse:
        """Get server statistics."""
        pool_stats = HeadlessChromePool.get_stats()
        return APIResponse(
            ok=True,
            data={
                "uptime_seconds": time.time() - self._start_time,
                "request_count": self._request_count,
                "chrome_pool": pool_stats,
            },
        )

    async def _handle_screenshot(
        self,
        url: str | None,
        selector: str | None,
        isolate: bool,
        format: str,
    ) -> APIResponse:
        """Capture screenshot."""
        if not url:
            return APIResponse(ok=False, error="Missing required parameter: url")

        if not selector:
            return APIResponse(ok=False, error="Missing required parameter: selector")

        try:
            async with HeadlessContext(url=url, timeout=30.0) as ctx:
                image_data = await ctx.screenshot(
                    selector=selector,
                    isolate=isolate,
                    format=format,
                )

                # Return base64-encoded image
                return APIResponse(
                    ok=True,
                    data={
                        "image": base64.b64encode(image_data).decode("ascii"),
                        "format": format,
                        "size_bytes": len(image_data),
                        "url": ctx.url,
                    },
                )

        except Exception as e:
            return APIResponse(ok=False, error=str(e))

    async def _handle_accessibility(
        self,
        url: str | None,
        level: str,
    ) -> APIResponse:
        """Run accessibility audit."""
        if not url:
            return APIResponse(ok=False, error="Missing required parameter: url")

        try:
            from inspekt.services.script_loader import ScriptLoader

            loader = ScriptLoader()

            async with HeadlessContext(url=url, timeout=60.0) as ctx:
                # Load and execute axe script
                axe_script = loader.load_script_sync("run_axe.js")

                axe_options = {
                    "level": level,
                    "showBadges": False,
                    "interactive": False,
                }

                code = axe_script.replace("OPTIONS_PLACEHOLDER", json.dumps(axe_options))
                result = await ctx.execute_script(code)

                if not result.get("ok"):
                    return APIResponse(ok=False, error=result.get("error"))

                return APIResponse(
                    ok=True,
                    data={
                        "url": ctx.url,
                        "level": level,
                        "violations": result.get("violations", []),
                        "passes": result.get("passes", []),
                        "incomplete": result.get("incomplete", []),
                        "summary": {
                            "violations": len(result.get("violations", [])),
                            "passes": len(result.get("passes", [])),
                            "incomplete": len(result.get("incomplete", [])),
                        },
                    },
                )

        except Exception as e:
            return APIResponse(ok=False, error=str(e))

    async def _handle_index(self, url: str | None) -> APIResponse:
        """Index page content."""
        if not url:
            return APIResponse(ok=False, error="Missing required parameter: url")

        try:
            from pathlib import Path

            script_path = Path(__file__).parent.parent.parent / "scripts" / "index_page.js"
            if not script_path.exists():
                return APIResponse(ok=False, error="Index script not found")

            with open(script_path) as f:
                script = f.read()

            async with HeadlessContext(url=url, timeout=30.0) as ctx:
                result = await ctx.execute_script(script)

                if not result.get("ok"):
                    return APIResponse(ok=False, error=result.get("error"))

                return APIResponse(
                    ok=True,
                    data={
                        "url": ctx.url,
                        "content": result.get("result", ""),
                    },
                )

        except Exception as e:
            return APIResponse(ok=False, error=str(e))

    async def _handle_execute(
        self,
        url: str | None,
        body: bytes | None,
    ) -> APIResponse:
        """Execute custom JavaScript."""
        if not url:
            return APIResponse(ok=False, error="Missing required parameter: url")

        if not body:
            return APIResponse(ok=False, error="Missing request body (JavaScript code)")

        try:
            script = body.decode("utf-8")

            async with HeadlessContext(url=url, timeout=30.0) as ctx:
                result = await ctx.execute_script(script)

                return APIResponse(
                    ok=True,
                    data={
                        "url": ctx.url,
                        "result": result,
                    },
                )

        except Exception as e:
            return APIResponse(ok=False, error=str(e))

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        response: APIResponse,
    ) -> None:
        """Send HTTP response."""
        body = response.to_bytes()

        headers = [
            "HTTP/1.1 200 OK" if response.ok else "HTTP/1.1 400 Bad Request",
            "Content-Type: application/json",
            f"Content-Length: {len(body)}",
            "Access-Control-Allow-Origin: *",
            "Connection: close",
            "",
            "",
        ]

        writer.write("\r\n".join(headers).encode("utf-8"))
        writer.write(body)
        await writer.drain()


async def main():
    """Run the API server."""
    host = os.environ.get("INSPEKT_API_HOST", "0.0.0.0")
    port = int(os.environ.get("INSPEKT_API_PORT", "8080"))

    server = HeadlessAPIServer(host=host, port=port)

    try:
        await server.start()
    except KeyboardInterrupt:
        print("\nShutting down…")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
