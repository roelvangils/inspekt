"""Block requests matching URL patterns.

Matched requests receive a 204 No Content response, preventing the resource
from loading. Useful for blocking analytics, ads, third-party scripts, or
testing how a page behaves without specific resources.

Config:
  patterns: list of str — URL patterns to block (supports * wildcards)

Example config:
  {
    "patterns": [
      "*google-analytics.com*",
      "*doubleclick.net*",
      "*.facebook.com/tr*",
      "*hotjar.com*"
    ]
  }
"""

import fnmatch

from mitmproxy import http


class BlockResources:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.patterns = config.get("patterns", [])

    def configure(self, config: dict):
        self.patterns = config.get("patterns", [])

    def request(self, flow: http.HTTPFlow):
        if not self.patterns:
            return

        url = flow.request.pretty_url
        for pattern in self.patterns:
            if fnmatch.fnmatch(url, pattern):
                flow.response = http.Response.make(
                    204,
                    b"",
                    {"X-Inspekt-Blocked": f"Matched pattern: {pattern}"},
                )
                return
