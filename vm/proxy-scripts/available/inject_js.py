"""Inject JavaScript into HTML responses.

Inserts a <script> tag into HTML responses, either referencing an external
file or containing inline code. Useful for injecting analytics, polyfills,
or custom behavior into proxied pages.

Config:
  url: str — URL of external JS file to inject (optional)
  inline: str — inline JavaScript code to inject (optional)
  position: str — "head" or "body" (default: "body")

At least one of 'url' or 'inline' must be provided. If both are given,
the external script is inserted first, followed by the inline script.
"""

from mitmproxy import http


class InjectJS:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.js_url = config.get("url", "")
        self.inline = config.get("inline", "")
        self.position = config.get("position", "body")

    def configure(self, config: dict):
        self.js_url = config.get("url", "")
        self.inline = config.get("inline", "")
        self.position = config.get("position", "body")

    def response(self, flow: http.HTTPFlow):
        if not self.js_url and not self.inline:
            return
        if flow.response is None:
            return

        content_type = flow.response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return

        html = flow.response.get_text(strict=False)
        if not html:
            return

        # Build the tags to inject
        tags = ""
        if self.js_url:
            tags += f'<script src="{self.js_url}"></script>\n'
        if self.inline:
            tags += f"<script>{self.inline}</script>\n"

        if self.position == "head":
            if "</head>" in html:
                html = html.replace("</head>", f"{tags}</head>", 1)
            elif "</body>" in html:
                html = html.replace("</body>", f"{tags}</body>", 1)
            else:
                html += tags
        else:
            # Default: before </body>
            if "</body>" in html:
                html = html.replace("</body>", f"{tags}</body>", 1)
            elif "</head>" in html:
                html = html.replace("</head>", f"</head>\n{tags}", 1)
            else:
                html += tags

        flow.response.set_text(html)
