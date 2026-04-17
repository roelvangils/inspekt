"""Force the Accept-Language request header.

Overrides the Accept-Language header on all requests to simulate a different
language preference. Useful for testing internationalization (i18n) and
verifying that content negotiation works correctly.

Config:
  language: str — language code, e.g., "nl", "fr-BE", "en-US" (required)

Example: language "fr-BE" sets the header to:
  Accept-Language: fr-BE,fr;q=0.9,en;q=0.5
"""

from mitmproxy import http


class ForceLanguage:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.language = config.get("language", "")

    def configure(self, config: dict):
        self.language = config.get("language", "")

    def request(self, flow: http.HTTPFlow):
        if not self.language:
            return

        # Build Accept-Language with the primary language and fallbacks
        lang = self.language
        parts = [f"{lang}"]

        # Add base language fallback if a region variant is specified (e.g., fr-BE -> fr)
        if "-" in lang:
            base = lang.split("-")[0]
            parts.append(f"{base};q=0.9")

        # Add English as a low-priority fallback (unless already requesting English)
        if not lang.startswith("en"):
            parts.append("en;q=0.5")

        flow.request.headers["Accept-Language"] = ",".join(parts)
