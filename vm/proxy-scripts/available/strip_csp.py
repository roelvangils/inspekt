"""Strip Content-Security-Policy from HTTP responses.

Removes CSP response headers AND — optionally, enabled by default — neutralises
`<meta http-equiv="Content-Security-Policy">` tags in HTML bodies by replacing
the `http-equiv` attribute with an inert marker (`data-inspekt-stripped-csp`).
The element stays in the DOM so it's visible that Inspekt tripped it.

Header stripping alone isn't enough for sites that deliver CSP via meta tag —
the browser parses those tags from the HTML itself before any extension runs,
so a proxy rewrite of the body is the only way to defeat them.

Config (passed via /tmp/mitmproxy_config.json):
  strip_meta (bool, default true) — neutralise <meta http-equiv="Content-Security-Policy"> tags
"""

import re

from mitmproxy import http

# Headers that enforce content security policies
CSP_HEADERS = [
    "content-security-policy",
    "content-security-policy-report-only",
    "x-content-security-policy",
    "x-webkit-csp",
]

# Match the http-equiv="Content-Security-Policy" attribute inside a <meta> tag.
# Case-insensitive on both the attribute name and the value. The value may be
# quoted with single or double quotes. Anchoring on the attribute (not the
# whole tag) keeps the rewrite surgical — other attributes on the same tag
# (like `content=...` which we leave visible) stay intact.
_META_CSP_RE = re.compile(
    rb"""http-equiv\s*=\s*(["'])content-security-policy\1""",
    re.IGNORECASE,
)


class StripCSP:
    def __init__(self, config: dict | None = None) -> None:
        self._strip_meta = True
        self.configure(config or {})

    def configure(self, config: dict) -> None:
        """Called by master_addon.py when config changes."""
        self._strip_meta = bool(config.get("strip_meta", True))

    def responseheaders(self, flow: http.HTTPFlow) -> None:
        if flow.response is None:
            return
        for header in CSP_HEADERS:
            if header in flow.response.headers:
                del flow.response.headers[header]

    def response(self, flow: http.HTTPFlow) -> None:
        if not self._strip_meta or flow.response is None:
            return
        # Only scan HTML payloads — rewriting e.g. a JS/JSON/image body is
        # pointless and potentially corrupting.
        ctype = flow.response.headers.get("content-type", "").lower()
        if "html" not in ctype:
            return
        body = flow.response.content
        if not body:
            return
        new_body, count = _META_CSP_RE.subn(b'data-inspekt-stripped-csp="1"', body)
        if count:
            flow.response.content = new_body
