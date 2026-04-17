"""Strip Content-Security-Policy headers from all responses.

This removes the CSP headers that would otherwise block injected scripts,
styles, and other resources. Useful for accessibility testing tools that
need to inject content into pages with strict CSP policies.

Config: none required
"""

from mitmproxy import http

# Headers that enforce content security policies
CSP_HEADERS = [
    "content-security-policy",
    "content-security-policy-report-only",
    "x-content-security-policy",
    "x-webkit-csp",
]


class StripCSP:
    def responseheaders(self, flow: http.HTTPFlow):
        if flow.response is None:
            return
        for header in CSP_HEADERS:
            if header in flow.response.headers:
                del flow.response.headers[header]
