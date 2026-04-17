#!/usr/bin/env python3
"""
CORS-enabled HTTP server for CSS hot-reload development.

Special handling for axe-popover/index.css:
- Returns Last-Modified based on the NEWEST file in the directory
- This ensures hot-reload detects changes in any imported CSS file
"""

import os
import sys
import glob
import signal
import subprocess
from email.utils import formatdate
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse


class CORSRequestHandler(SimpleHTTPRequestHandler):
    """HTTP request handler with CORS headers and directory-aware Last-Modified."""

    def log_message(self, format, *args):
        """Only log CSS-related requests, filter out noise from other services."""
        path = args[0].split()[1] if args else ""
        # Only log requests for CSS files or axe-popover directory
        if "/axe-popover/" in path or path.endswith(".css"):
            super().log_message(format, *args)

    def log_error(self, format, *args):
        """Suppress 404 errors for non-CSS paths (noise from other services)."""
        # Don't log 404s for paths we don't care about
        pass

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_OPTIONS(self):
        """Handle preflight CORS requests."""
        self.send_response(200)
        self.end_headers()

    def send_header(self, keyword, value):
        """Override Last-Modified for index.css to use directory's newest file."""
        # Strip query string (cache-busting param) before checking path
        path_without_query = urlparse(self.path).path
        if keyword == "Last-Modified" and path_without_query.endswith("/index.css"):
            # Find the newest CSS file in the directory
            dir_path = os.path.dirname(self.translate_path(path_without_query))
            css_files = glob.glob(os.path.join(dir_path, "*.css"))

            if css_files:
                newest_mtime = max(os.path.getmtime(f) for f in css_files)
                value = formatdate(newest_mtime, usegmt=True)

        super().send_header(keyword, value)


def build_css(script_dir):
    """Run the CSS build script."""
    print("\n📦 Building CSS for production…")
    build_script = os.path.join(script_dir, "build-axe-css.js")

    if not os.path.exists(build_script):
        print(f"⚠️  Build script not found: {build_script}")
        return False

    try:
        result = subprocess.run(
            ["node", build_script],
            cwd=os.path.dirname(script_dir),
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            # Print the build output
            if result.stdout:
                for line in result.stdout.strip().split('\n'):
                    print(f"   {line}")
            print("✅ CSS built successfully!")
            return True
        else:
            print(f"❌ Build failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Build error: {e}")
        return False


def main():
    port = 8000

    # Change to inspekt/scripts directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    serve_dir = os.path.join(os.path.dirname(script_dir), "inspekt", "scripts")

    if not os.path.exists(serve_dir):
        print(f"Error: Directory not found: {serve_dir}")
        sys.exit(1)

    os.chdir(serve_dir)

    server = HTTPServer(("", port), CORSRequestHandler)
    print(f"🚀 CSS dev server running at http://localhost:{port}")
    print(f"📁 Serving: {serve_dir}")
    print(f"🔗 CSS URL: http://localhost:{port}/axe-popover/index.css")
    print(f"🔄 Hot-reload: Detects changes in ANY .css file in axe-popover/")
    print("\n💡 Press Ctrl+C to stop and build CSS for production\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass  # Ctrl+C pressed
    finally:
        # Ignore further Ctrl+C during cleanup
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        print("\n👋 Stopping server…")
        server.server_close()
        build_css(script_dir)


if __name__ == "__main__":
    main()
