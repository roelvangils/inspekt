"""Find and replace text in HTML responses.

Applies find/replace rules to HTML responses. Useful for accessibility
remediation previews — e.g., what would this page look like if all
<div role="button"> elements were actual <button> elements?

Config:
  rules: list of {find: str, replace: str, regex: bool}
    - find: string or regex pattern to match
    - replace: replacement string (supports regex backreferences if regex=true)
    - regex: whether to treat 'find' as a regex (default: false)

Example config:
  {
    "rules": [
      {"find": "<div role=\"button\"", "replace": "<button", "regex": false},
      {"find": "</div>(<!--\\s*end button\\s*-->)", "replace": "</button>\\1", "regex": true}
    ]
  }
"""

import re

from mitmproxy import http


class FindReplace:
    def __init__(self, config: dict | None = None):
        config = config or {}
        self.rules = config.get("rules", [])

    def configure(self, config: dict):
        self.rules = config.get("rules", [])

    def response(self, flow: http.HTTPFlow):
        if not self.rules:
            return
        if flow.response is None:
            return

        content_type = flow.response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return

        html = flow.response.get_text(strict=False)
        if not html:
            return

        modified = False
        for rule in self.rules:
            find = rule.get("find", "")
            replace = rule.get("replace", "")
            use_regex = rule.get("regex", False)

            if not find:
                continue

            if use_regex:
                new_html = re.sub(find, replace, html)
            else:
                new_html = html.replace(find, replace)

            if new_html != html:
                html = new_html
                modified = True

        if modified:
            flow.response.set_text(html)
