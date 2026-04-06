"""Inject a CSS stylesheet into HTML responses.

Inserts a <link> tag before </head> so the stylesheet participates in the
normal cascade — no !important needed. This is fundamentally different from
JS-based injection because the browser applies the styles during initial
parsing, before first paint.

Config:
  url: str — URL of the stylesheet to inject (required)
  media: str — media attribute for the <link> tag (optional, default: "all")
"""

import re

from mitmproxy import http


class InjectCSS:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.css_url = config.get("url", "")
        self.media = config.get("media", "all")

    def configure(self, config: dict):
        self.css_url = config.get("url", "")
        self.media = config.get("media", "all")

    def response(self, flow: http.HTTPFlow):
        if not self.css_url:
            return
        if flow.response is None:
            return

        content_type = flow.response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return

        html = flow.response.get_text(strict=False)
        if not html:
            return

        link_tag = f'<link rel="stylesheet" href="{self.css_url}" media="{self.media}">'

        # Insert before </head> if present, otherwise before </body>, otherwise append
        if "</head>" in html:
            html = html.replace("</head>", f"{link_tag}\n</head>", 1)
        elif "</body>" in html:
            html = html.replace("</body>", f"{link_tag}\n</body>", 1)
        else:
            html += link_tag

        flow.response.set_text(html)
