"""Add, remove, or modify HTTP response headers.

Generic header manipulation for testing purposes. Can add CORS headers,
remove X-Frame-Options, inject custom headers, etc.

Config:
  add: dict — headers to add/overwrite {name: value}
  remove: list of str — header names to remove

Example config:
  {
    "add": {
      "Access-Control-Allow-Origin": "*",
      "X-Inspekt-Modified": "true"
    },
    "remove": [
      "x-frame-options",
      "x-content-type-options"
    ]
  }
"""

from mitmproxy import http


class ModifyHeaders:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.add_headers = config.get("add", {})
        self.remove_headers = config.get("remove", [])

    def configure(self, config: dict):
        self.add_headers = config.get("add", {})
        self.remove_headers = config.get("remove", [])

    def responseheaders(self, flow: http.HTTPFlow):
        if flow.response is None:
            return

        # Remove headers
        for header in self.remove_headers:
            if header in flow.response.headers:
                del flow.response.headers[header]

        # Add/overwrite headers
        for name, value in self.add_headers.items():
            flow.response.headers[name] = value
