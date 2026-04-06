"""Simulate slow network connections.

Adds configurable delay to responses, useful for testing loading states,
skeleton screens, progressive enhancement, and performance under poor
network conditions.

Config:
  delay_ms: int — delay in milliseconds to add to each response (default: 1000)
  url_pattern: str — only throttle URLs matching this pattern (optional, default: all)
"""

import fnmatch
import time

from mitmproxy import http


class Throttle:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.delay_ms = config.get("delay_ms", 1000)
        self.url_pattern = config.get("url_pattern", "")

    def configure(self, config: dict):
        self.delay_ms = config.get("delay_ms", 1000)
        self.url_pattern = config.get("url_pattern", "")

    def response(self, flow: http.HTTPFlow):
        if self.delay_ms <= 0:
            return

        if self.url_pattern:
            url = flow.request.pretty_url
            if not fnmatch.fnmatch(url, self.url_pattern):
                return

        time.sleep(self.delay_ms / 1000.0)
