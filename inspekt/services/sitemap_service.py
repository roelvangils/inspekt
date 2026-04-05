"""
Sitemap service - Fetch, parse, cache, and navigate sitemaps.

Supports:
- Auto-discovery via robots.txt Sitemap: directives and /sitemap.xml fallback
- Regular sitemaps (<urlset>) and sitemap index files (<sitemapindex>)
- Gzip-compressed sitemaps (.xml.gz)
- Session-based caching for fast repeated access
- Tree-based path grouping for display
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import logging
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from inspekt.config import get_data_dir, is_isolated_mode
from inspekt.services import http_client

logger = logging.getLogger(__name__)

# Sitemap XML namespace
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


# Cache directory — use the Docker volume in VM (shared between root API server
# and inspekt terminal user), standard cache dir otherwise.
def _get_cache_dir() -> Path:
    if is_isolated_mode():
        # Fixed path on the inspekt-vm-data Docker volume, accessible to all users
        return Path("/root/.config/inspekt/sitemaps")
    return Path.home() / ".cache" / "inspekt" / "sitemaps"


CACHE_DIR = _get_cache_dir()

# Cache TTL: 1 hour
CACHE_TTL = 3600


@dataclass
class SitemapEntry:
    """A single URL entry from a sitemap."""

    loc: str
    lastmod: str = ""
    changefreq: str = ""
    priority: str = ""
    title: str = ""
    # HTTP response metadata (populated during title fetch)
    http_status: int = 0
    final_url: str = ""       # After redirects — differs from loc if redirected
    canonical_url: str = ""   # From <link rel="canonical">
    content_length: int = 0
    etag: str = ""
    lang: str = ""            # From <html lang="...">


@dataclass
class SitemapResult:
    """Parsed sitemap data."""

    origin: str = ""
    source_url: str = ""
    discovered_via: str = ""  # "robots.txt", "/sitemap.xml", "direct", etc.
    is_index: bool = False
    entries: list[SitemapEntry] = field(default_factory=list)
    child_sitemaps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fetch_time: float = 0.0

    @property
    def total_urls(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {
            "origin": self.origin,
            "source_url": self.source_url,
            "discovered_via": self.discovered_via,
            "is_index": self.is_index,
            "total_urls": self.total_urls,
            "child_sitemaps": self.child_sitemaps,
            "entries": [
                {
                    "loc": e.loc,
                    **({"lastmod": e.lastmod} if e.lastmod else {}),
                    **({"changefreq": e.changefreq} if e.changefreq else {}),
                    **({"priority": e.priority} if e.priority else {}),
                    **({"title": e.title} if e.title else {}),
                    **({"http_status": e.http_status} if e.http_status else {}),
                    **({"final_url": e.final_url} if e.final_url else {}),
                    **({"canonical_url": e.canonical_url} if e.canonical_url else {}),
                    **({"content_length": e.content_length} if e.content_length else {}),
                    **({"etag": e.etag} if e.etag else {}),
                    **({"lang": e.lang} if e.lang else {}),
                }
                for e in self.entries
            ],
            "errors": self.errors,
        }


@dataclass
class TreeNode:
    """A node in the URL path tree."""

    name: str
    full_path: str = ""
    entry: Optional[SitemapEntry] = None
    children: dict[str, "TreeNode"] = field(default_factory=dict)
    entry_index: int = -1  # 1-based index for --open navigation

    @property
    def has_entry(self) -> bool:
        return self.entry is not None


def discover_sitemap(origin: str) -> tuple[list[str], str]:
    """
    Auto-discover sitemap URLs for an origin.

    Collects ALL Sitemap: directives from robots.txt, then probes
    common fallback locations. Returns multiple URLs when a site
    has per-language or per-section sitemaps.

    Args:
        origin: The site origin (e.g., "https://example.com")

    Returns:
        Tuple of (list_of_sitemap_urls, discovery_method)
    """
    found: list[str] = []

    # Step 1: Collect ALL Sitemap: directives from robots.txt
    robots_url = f"{origin}/robots.txt"
    try:
        response = http_client.get(
            robots_url,
            timeout=5,
            headers={"User-Agent": "Inspekt-CLI-Sitemap"},
            allow_redirects=True,
        )
        if response.status_code == 200:
            for line in response.text.splitlines():
                stripped = line.strip()
                if stripped.lower().startswith("sitemap:"):
                    _, _, sitemap_url = stripped.partition(":")
                    sitemap_url = sitemap_url.strip()
                    if sitemap_url and sitemap_url not in found:
                        found.append(sitemap_url)
    except requests.RequestException:
        pass

    if found:
        return found, "robots.txt"

    # Step 2: Fall back to well-known paths
    for path in ["/sitemap.xml", "/sitemap_index.xml"]:
        probe_url = f"{origin}{path}"
        try:
            response = http_client.get(
                probe_url,
                timeout=5,
                headers={"User-Agent": "Inspekt-CLI-Sitemap"},
                allow_redirects=True,
            )
            if response.status_code == 200:
                return [probe_url], path
        except requests.RequestException:
            pass

    # Step 3: Probe for language-prefixed sitemaps (common CMS pattern)
    # Try a few common language codes — only add those that exist
    common_langs = ["en", "nl", "fr", "de", "es", "it", "pt"]
    for lang in common_langs:
        probe_url = f"{origin}/{lang}/sitemap.xml"
        try:
            response = http_client.get(
                probe_url,
                timeout=3,
                headers={"User-Agent": "Inspekt-CLI-Sitemap"},
                allow_redirects=True,
            )
            if response.status_code == 200:
                found.append(probe_url)
        except requests.RequestException:
            pass

    if found:
        return found, "language probe"

    return [], "not found"


def fetch_sitemap(
    url: str, flatten: bool = False, max_children: int = 10
) -> SitemapResult:
    """
    Fetch and parse a sitemap URL.

    Handles regular sitemaps, sitemap index files, and gzip-compressed sitemaps.
    For sitemap indexes, optionally flattens child sitemaps into a single list.

    Args:
        url: Sitemap URL to fetch
        flatten: If True, recursively fetch child sitemaps and merge entries
        max_children: Maximum number of child sitemaps to fetch when flattening

    Returns:
        SitemapResult with parsed data
    """
    result = SitemapResult(source_url=url)
    start = time.time()

    # Parse origin from URL
    parsed = urlparse(url)
    result.origin = f"{parsed.scheme}://{parsed.netloc}"

    # Fetch the sitemap
    try:
        response = http_client.get(
            url,
            timeout=10,
            headers={"User-Agent": "Inspekt-CLI-Sitemap"},
            allow_redirects=True,
        )

        if response.status_code != 200:
            result.errors.append(f"HTTP {response.status_code} for {url}")
            result.fetch_time = time.time() - start
            return result

        content = response.content

        # Handle gzip-compressed sitemap files (.xml.gz)
        # Note: transport-level gzip (Content-Encoding) is already handled by requests
        if url.endswith(".gz"):
            try:
                content = gzip.decompress(content)
            except Exception as e:
                result.errors.append(f"Gzip decompression failed: {e}")
                result.fetch_time = time.time() - start
                return result

        # Parse as text
        if isinstance(content, bytes):
            xml_text = content.decode("utf-8", errors="replace")
        else:
            xml_text = content

    except requests.Timeout:
        result.errors.append(f"Timeout fetching {url}")
        result.fetch_time = time.time() - start
        return result
    except requests.RequestException as e:
        result.errors.append(f"Request failed: {e}")
        result.fetch_time = time.time() - start
        return result

    # Parse XML
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        result.errors.append(f"XML parse error: {e}")
        result.fetch_time = time.time() - start
        return result

    # Detect sitemap index vs regular sitemap
    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

    if tag == "sitemapindex":
        result.is_index = True
        for sitemap_elem in root.findall(f"{NS}sitemap"):
            loc = sitemap_elem.find(f"{NS}loc")
            if loc is not None and loc.text:
                result.child_sitemaps.append(loc.text.strip())

        # Optionally flatten child sitemaps
        if flatten and result.child_sitemaps:
            for child_url in result.child_sitemaps[:max_children]:
                child_result = fetch_sitemap(child_url, flatten=False)
                result.entries.extend(child_result.entries)
                result.errors.extend(child_result.errors)

    elif tag == "urlset":
        for url_elem in root.findall(f"{NS}url"):
            entry = _parse_url_element(url_elem)
            if entry:
                result.entries.append(entry)

    else:
        result.errors.append(f"Unknown root element: {root.tag}")

    result.fetch_time = time.time() - start
    return result


def _parse_url_element(url_elem: ET.Element) -> Optional[SitemapEntry]:
    """Parse a single <url> element into a SitemapEntry."""
    loc = url_elem.find(f"{NS}loc")
    if loc is None or not loc.text:
        return None

    entry = SitemapEntry(loc=loc.text.strip())

    lastmod = url_elem.find(f"{NS}lastmod")
    if lastmod is not None and lastmod.text:
        entry.lastmod = lastmod.text.strip()

    changefreq = url_elem.find(f"{NS}changefreq")
    if changefreq is not None and changefreq.text:
        entry.changefreq = changefreq.text.strip()

    priority = url_elem.find(f"{NS}priority")
    if priority is not None and priority.text:
        entry.priority = priority.text.strip()

    return entry


def build_tree(entries: list[SitemapEntry], origin: str) -> TreeNode:
    """
    Build a tree from sitemap entries based on URL path segments.

    Args:
        entries: List of sitemap entries
        origin: The site origin to strip from URLs

    Returns:
        Root TreeNode with children organized by path
    """
    parsed_origin = urlparse(origin)
    root = TreeNode(name=parsed_origin.netloc, full_path="/")

    idx = 1  # 1-based index for --open navigation
    for entry in entries:
        parsed = urlparse(entry.loc)
        path = parsed.path.rstrip("/") or "/"

        # Split path into segments
        if path == "/":
            segments = []
        else:
            segments = [s for s in path.split("/") if s]

        # Walk the tree, creating nodes as needed
        current = root
        for i, segment in enumerate(segments):
            if segment not in current.children:
                partial_path = "/" + "/".join(segments[: i + 1])
                current.children[segment] = TreeNode(
                    name=segment, full_path=partial_path
                )
            current = current.children[segment]

        # Attach the entry to the deepest node
        current.entry = entry
        current.entry_index = idx
        idx += 1

    return root


def find_node_by_path(
    root: TreeNode, path: str
) -> tuple[TreeNode | None, TreeNode | None]:
    """Find a node and its parent by URL path. Returns (node, parent).

    Args:
        root: The root TreeNode (from build_tree)
        path: URL path, e.g. "/blog/my-post" or "/"

    Returns:
        Tuple of (node, parent). Both are None if the path doesn't exist in the tree.
        Parent is None when the node is the root.
    """
    path = path.rstrip("/") or "/"

    if path == "/":
        return root, None

    segments = [s for s in path.strip("/").split("/") if s]
    parent = None
    current = root
    for seg in segments:
        if seg in current.children:
            parent = current
            current = current.children[seg]
        else:
            return None, None
    return current, parent


def find_ancestors(root: TreeNode, path: str) -> list[TreeNode]:
    """Return the list of TreeNodes from root to the node at the given path.

    Args:
        root: The root TreeNode
        path: URL path to trace, e.g. "/a/b/c"

    Returns:
        List of TreeNodes [root, child_a, child_b, child_c].
        Empty list if the path doesn't exist in the tree.
    """
    path = path.rstrip("/") or "/"

    if path == "/":
        return [root]

    segments = [s for s in path.strip("/").split("/") if s]
    ancestors = [root]
    current = root
    for seg in segments:
        if seg in current.children:
            current = current.children[seg]
            ancestors.append(current)
        else:
            return []
    return ancestors


def get_stats(result: SitemapResult) -> dict[str, Any]:
    """
    Compute statistics for a sitemap result.

    Returns:
        Dictionary with stats: total_urls, depth distribution, freshness, etc.
    """
    entries = result.entries

    if not entries:
        return {"total_urls": 0}

    # Depth distribution
    depths: dict[int, int] = {}
    for entry in entries:
        parsed = urlparse(entry.loc)
        path = parsed.path.rstrip("/") or "/"
        depth = 0 if path == "/" else path.count("/")
        depths[depth] = depths.get(depth, 0) + 1

    # Change frequency distribution
    freqs: dict[str, int] = {}
    for entry in entries:
        if entry.changefreq:
            freqs[entry.changefreq] = freqs.get(entry.changefreq, 0) + 1

    # Priority distribution
    priorities: dict[str, int] = {}
    for entry in entries:
        if entry.priority:
            priorities[entry.priority] = priorities.get(entry.priority, 0) + 1

    # Lastmod stats
    has_lastmod = sum(1 for e in entries if e.lastmod)

    # Duplicate title stats
    title_counts: dict[str, int] = {}
    for e in entries:
        if e.title:
            title_counts[e.title] = title_counts.get(e.title, 0) + 1
    dupe_groups = {t: c for t, c in title_counts.items() if c >= 2}

    # HTTP status stats
    non_200 = sum(1 for e in entries if e.http_status and e.http_status != 200)

    return {
        "total_urls": len(entries),
        "child_sitemaps": len(result.child_sitemaps),
        "depth_distribution": dict(sorted(depths.items())),
        "changefreq_distribution": dict(sorted(freqs.items())),
        "priority_distribution": dict(
            sorted(priorities.items(), key=lambda x: float(x[0]), reverse=True)
        ),
        "urls_with_lastmod": has_lastmod,
        "urls_without_lastmod": len(entries) - has_lastmod,
        "duplicate_title_groups": len(dupe_groups),
        "duplicate_title_entries": sum(dupe_groups.values()),
        "non_200_urls": non_200,
    }


# ============================================================================
# Title fetching
# ============================================================================

# Progressive chunk sizes for title fetching — most titles are in the first 16 KB,
# but some SPAs inline 50-80 KB of scripts before the <title> tag
_TITLE_CHUNK_SIZES = [16_384, 32_768, 65_536, 131_072, 524_288]

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CANONICAL_RE = re.compile(r'<link[^>]*rel="canonical"[^>]*href="([^"]+)"', re.I)
_HTML_LANG_RE = re.compile(r'<html[^>]*\blang="([^"]+)"', re.I)


def _extract_title(text: str) -> str:
    """Extract and clean a <title> from HTML text. Returns empty string if not found."""
    match = _TITLE_RE.search(text)
    if not match:
        return ""
    title = match.group(1).strip()
    title = re.sub(r"\s+", " ", title)
    title = html.unescape(title)
    # Strip ALL invisible/control Unicode characters that can corrupt terminal output
    title = "".join(
        c for c in title
        if unicodedata.category(c) not in ("Cf", "Cc") or c in ("\n", "\t")
    )
    title = title.strip()
    return title


# Patterns for extracting dates from HTML (ordered by reliability)
_DATE_META_PATTERNS = [
    # Open Graph / article dates (most reliable)
    re.compile(r'<meta[^>]*property="article:modified_time"[^>]*content="([^"]+)"', re.I),
    re.compile(r'<meta[^>]*property="article:published_time"[^>]*content="([^"]+)"', re.I),
    re.compile(r'<meta[^>]*property="og:updated_time"[^>]*content="([^"]+)"', re.I),
    # Reversed attribute order (some CMSs do this)
    re.compile(r'<meta[^>]*content="([^"]+)"[^>]*property="article:modified_time"', re.I),
    re.compile(r'<meta[^>]*content="([^"]+)"[^>]*property="article:published_time"', re.I),
    # Dublin Core
    re.compile(r'<meta[^>]*name="dcterms\.modified"[^>]*content="([^"]+)"', re.I),
    re.compile(r'<meta[^>]*name="DC\.date"[^>]*content="([^"]+)"', re.I),
    # Generic
    re.compile(r'<meta[^>]*name="date"[^>]*content="([^"]+)"', re.I),
    re.compile(r'<meta[^>]*name="last-modified"[^>]*content="([^"]+)"', re.I),
]

_JSON_LD_RE = re.compile(
    r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.I | re.DOTALL
)


def _extract_date_from_html(text: str) -> str:
    """Extract a publication/modification date from HTML meta tags or JSON-LD.

    Returns an ISO date string, or empty if not found.
    """
    # Try meta tags first
    for pattern in _DATE_META_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()

    # Try JSON-LD structured data
    for match in _JSON_LD_RE.finditer(text):
        try:
            data = json.loads(match.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                # Prefer dateModified over datePublished
                for key in ("dateModified", "datePublished"):
                    if key in item and isinstance(item[key], str):
                        return item[key]
        except (json.JSONDecodeError, TypeError):
            continue

    return ""


def _fetch_single_title(url: str, timeout: float = 3.0) -> dict:
    """
    Fetch a page progressively until the <title> tag is found.

    Also captures HTTP metadata: status code, final URL (after redirects),
    canonical URL, ETag, Content-Length, and lang attribute.

    Returns:
        Dict with keys: title, date, http_status, final_url,
        canonical_url, content_length, etag, lang.
    """
    empty = {
        "title": "", "date": "", "http_status": 0, "final_url": "",
        "canonical_url": "", "content_length": 0, "etag": "", "lang": "",
    }
    try:
        response = http_client.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": "Inspekt-CLI-Sitemap/1.0",
                "Accept": "text/html",
                "Accept-Encoding": "identity",
            },
            allow_redirects=True,
            stream=True,
            max_bytes=_TITLE_CHUNK_SIZES[-1],
        )

        # Capture response metadata from headers
        meta = {
            "http_status": response.status_code,
            "final_url": str(response.url) if str(response.url) != url else "",
            "etag": response.headers.get("ETag", ""),
            "content_length": _safe_int(response.headers.get("Content-Length", "")),
        }

        if response.status_code != 200:
            return {**empty, **meta}

        # Capture Last-Modified header as fallback date
        last_modified = response.headers.get("Last-Modified", "")

        # Use a single iterator — can't restart iter_content after breaking
        stream = response.iter_content(chunk_size=4096)
        content = b""

        for limit in _TITLE_CHUNK_SIZES:
            for chunk in stream:
                content += chunk
                if len(content) >= limit:
                    break

            text = content.decode("utf-8", errors="replace")
            title = _extract_title(text)
            if title:
                response.close()
                date = last_modified or _extract_date_from_html(text)
                return {
                    **meta,
                    "title": title,
                    "date": date,
                    "canonical_url": _extract_canonical(text),
                    "lang": _extract_lang(text),
                }

            if len(content) < limit:
                break

        response.close()
        text = content.decode("utf-8", errors="replace")
        date = last_modified or _extract_date_from_html(text)
        return {
            **meta,
            "title": "",
            "date": date,
            "canonical_url": _extract_canonical(text),
            "lang": _extract_lang(text),
        }

    except (requests.RequestException, OSError) as e:
        logger.debug(f"Title fetch failed for {url}: {type(e).__name__}: {e}")
        return empty


def _safe_int(value: str) -> int:
    """Parse an integer from a string, returning 0 on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _extract_canonical(text: str) -> str:
    """Extract canonical URL from <link rel="canonical"> tag."""
    m = _CANONICAL_RE.search(text)
    return html.unescape(m.group(1).strip()) if m else ""


def _extract_lang(text: str) -> str:
    """Extract language from <html lang="..."> attribute. Normalizes to base code."""
    m = _HTML_LANG_RE.search(text)
    if not m:
        return ""
    # "nl-BE" → "nl", "en-US" → "en"
    return m.group(1).split("-")[0].lower()


def debug_title_fetch(url: str) -> dict:
    """Diagnostic: fetch a single title and report what happened at each step."""
    import os

    info = {
        "url": url,
        "restricted_mode": os.environ.get("INSPEKT_RESTRICTED") == "1",
    }

    try:
        response = http_client.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Inspekt-CLI-Sitemap/1.0",
                "Accept": "text/html",
                "Accept-Encoding": "identity",
            },
            allow_redirects=True,
            stream=True,
            max_bytes=_TITLE_CHUNK_SIZES[-1],
        )

        info["status"] = response.status_code
        info["response_type"] = type(response).__name__

        # For ProxyResponse, check raw body size before iter_content
        if hasattr(response, "_body"):
            info["proxy_body_len"] = len(response._body)
        if hasattr(response, "text"):
            info["text_len"] = len(response.text)

        if response.status_code != 200:
            info["error"] = f"HTTP {response.status_code}"
            return info

        content = b""
        for chunk in response.iter_content(chunk_size=4096):
            content += chunk
            if len(content) >= _TITLE_CHUNK_SIZES[-1]:
                break
        response.close()

        info["bytes_read"] = len(content)
        text = content.decode("utf-8", errors="replace")
        info["has_title_tag"] = "<title" in text.lower()

        if "<title" in text.lower():
            idx = text.lower().index("<title")
            info["title_tag_at_byte"] = idx

        title = _extract_title(text)
        info["title"] = title or "(not found)"

        # Show start of content for debugging
        info["content_start"] = text[:200].replace("\n", "\\n")

    except Exception as e:
        info["error"] = f"{type(e).__name__}: {e}"

    return info


def _parse_http_date(http_date: str) -> str:
    """Convert an HTTP Last-Modified date to ISO 8601 format.

    'Thu, 03 Apr 2026 12:00:00 GMT' → '2026-04-03T12:00:00+00:00'
    Returns empty string if unparseable.
    """
    from datetime import datetime, timezone
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(http_date)
        return dt.isoformat()
    except Exception:
        return ""


def fetch_titles(
    entries: list[SitemapEntry],
    max_concurrent: int = 20,
    timeout: float = 3.0,
    progress_callback=None,
) -> int:
    """
    Fetch page titles for sitemap entries concurrently.

    Uses adaptive concurrency: starts at max_concurrent and backs off
    if the server starts dropping connections (>30% failure rate in a
    rolling window). This prevents overwhelming servers that have
    connection limits.

    Modifies entries in-place, setting the `title` field. Skips entries
    that already have a title.

    Args:
        entries: List of SitemapEntry objects to enrich
        max_concurrent: Maximum number of concurrent requests
        timeout: Timeout per request in seconds
        progress_callback: Optional callable(completed, total) for progress

    Returns:
        Number of titles successfully fetched
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Filter to entries that need titles
    # Skip entries that already have a title, and entries that were already
    # checked but got no title (e.g., 404 pages) — don't retry those.
    to_fetch = [(i, e) for i, e in enumerate(entries) if not e.title and e.http_status == 0]
    if not to_fetch:
        return 0

    total = len(to_fetch)
    fetched = 0
    completed = 0

    # Adaptive concurrency — starts at max_concurrent, backs off on failures.
    # Uses a simple gate: _throttled_fetch checks active count before proceeding.
    min_concurrency = 5
    concurrency_limit = max_concurrent
    active_count = 0
    gate_lock = threading.Lock()
    gate_ready = threading.Condition(gate_lock)

    # Rolling failure window: track last 50 results (True=success, False=failure)
    recent_results: list[bool] = []
    backoff_lock = threading.Lock()

    def _throttled_fetch(url: str) -> dict:
        nonlocal active_count
        with gate_ready:
            while active_count >= concurrency_limit:
                gate_ready.wait()
            active_count += 1
        try:
            return _fetch_single_title(url, timeout)
        finally:
            with gate_ready:
                active_count -= 1
                gate_ready.notify()

    def _maybe_backoff(success: bool):
        """Reduce concurrency if the server is struggling (>30% failure rate)."""
        nonlocal concurrency_limit
        with backoff_lock:
            recent_results.append(success)
            if len(recent_results) > 50:
                recent_results.pop(0)
            if len(recent_results) < 20:
                return

            failure_rate = 1 - sum(recent_results) / len(recent_results)
            if failure_rate > 0.3 and concurrency_limit > min_concurrency:
                new_limit = max(concurrency_limit // 2, min_concurrency)
                if new_limit < concurrency_limit:
                    concurrency_limit = new_limit
                    logger.debug(f"Backing off: concurrency → {concurrency_limit} (failure rate: {failure_rate:.0%})")

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {}
        for idx, entry in to_fetch:
            future = executor.submit(_throttled_fetch, entry.loc)
            futures[future] = idx

        for future in as_completed(futures):
            idx = futures[future]
            completed += 1
            try:
                result = future.result()
                success = bool(result["title"] or result["http_status"])
                _maybe_backoff(success)

                if result["title"]:
                    entries[idx].title = result["title"]
                    fetched += 1
                # Use extracted date as fallback when sitemap has no lastmod
                last_modified = result["date"]
                if last_modified and not entries[idx].lastmod:
                    parsed = _parse_http_date(last_modified)
                    entries[idx].lastmod = parsed if parsed else last_modified
                # Apply HTTP response metadata
                entries[idx].http_status = result["http_status"]
                entries[idx].final_url = result["final_url"]
                entries[idx].canonical_url = result["canonical_url"]
                entries[idx].content_length = result["content_length"]
                entries[idx].etag = result["etag"]
                entries[idx].lang = result["lang"]
            except Exception:
                _maybe_backoff(False)

            if progress_callback:
                progress_callback(completed, total)

    return fetched


# ============================================================================
# Language detection
# ============================================================================

# ISO 639-1 two-letter language codes
LANG_CODES = {
    "aa", "ab", "af", "ak", "am", "an", "ar", "as", "av", "ay", "az",
    "ba", "be", "bg", "bh", "bi", "bm", "bn", "bo", "br", "bs",
    "ca", "ce", "ch", "co", "cr", "cs", "cu", "cv", "cy",
    "da", "de", "dv", "dz",
    "ee", "el", "en", "eo", "es", "et", "eu",
    "fa", "ff", "fi", "fj", "fo", "fr", "fy",
    "ga", "gd", "gl", "gn", "gu", "gv",
    "ha", "he", "hi", "ho", "hr", "ht", "hu", "hy", "hz",
    "ia", "id", "ie", "ig", "ii", "ik", "io", "is", "it", "iu",
    "ja", "jv",
    "ka", "kg", "ki", "kj", "kk", "kl", "km", "kn", "ko", "kr", "ks", "ku", "kv", "kw", "ky",
    "la", "lb", "lg", "li", "ln", "lo", "lt", "lu", "lv",
    "mg", "mh", "mi", "mk", "ml", "mn", "mr", "ms", "mt", "my",
    "na", "nb", "nd", "ne", "ng", "nl", "nn", "no", "nr", "nv", "ny",
    "oc", "oj", "om", "or", "os",
    "pa", "pi", "pl", "ps", "pt",
    "qu",
    "rm", "rn", "ro", "ru", "rw",
    "sa", "sc", "sd", "se", "sg", "si", "sk", "sl", "sm", "sn", "so", "sq", "sr", "ss", "st", "su", "sv", "sw",
    "ta", "te", "tg", "th", "ti", "tk", "tl", "tn", "to", "tr", "ts", "tt", "tw", "ty",
    "ug", "uk", "ur", "uz",
    "ve", "vi", "vo",
    "wa", "wo",
    "xh",
    "yi", "yo",
    "za", "zh", "zu",
}


def detect_languages(entries: list[SitemapEntry]) -> set[str]:
    """
    Detect languages in sitemap entries.

    Prefers the HTML lang attribute (from title fetch) when available.
    Falls back to detecting 2-letter ISO 639-1 codes as the first path
    segment (e.g., /en/about, /nl/contact). Returns languages only when
    2+ languages are found.
    """
    # Prefer HTML lang attribute when entries have been enriched
    html_langs = {e.lang for e in entries if e.lang}
    if len(html_langs) >= 2:
        return html_langs

    # Fallback: detect from URL path prefixes
    lang_counts: dict[str, int] = {}
    for entry in entries:
        parsed = urlparse(entry.loc)
        parts = [p for p in parsed.path.split("/") if p]
        if parts and parts[0].lower() in LANG_CODES:
            lang = parts[0].lower()
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    candidates = {lang for lang, count in lang_counts.items() if count >= 3}
    return candidates if len(candidates) >= 2 else set()


# Common title separators (ordered by frequency in the wild)
_TITLE_SEPARATORS = [" | ", " - ", " — ", " · ", " :: ", " // ", " – "]


def detect_site_name(entries: list[SitemapEntry], threshold: float = 0.5) -> str:
    """
    Detect the site name by finding the fragment that repeats across most titles.

    Splits each title on common separators (|, -, —, ·) and counts which
    fragment appears most often. If it appears in more than `threshold` of
    titled entries, it's the site name.

    Args:
        entries: Sitemap entries (must have titles already fetched)
        threshold: Minimum fraction of titles that must contain the fragment

    Returns:
        The detected site name, or empty string if none found
    """
    titles = [e.title for e in entries if e.title]
    if len(titles) < 3:
        return ""

    # Split all titles on separators and count fragment frequency
    fragment_counts: dict[str, int] = {}
    for title in titles:
        # Try each separator, use the first one that splits the title
        parts = [title]
        for sep in _TITLE_SEPARATORS:
            if sep in title:
                parts = [p.strip() for p in title.split(sep) if p.strip()]
                break

        for part in parts:
            fragment_counts[part] = fragment_counts.get(part, 0) + 1

    if not fragment_counts:
        return ""

    # The site name is the most frequent fragment that appears in enough titles
    most_common = max(fragment_counts.items(), key=lambda x: x[1])
    name, count = most_common

    if count >= len(titles) * threshold:
        return name

    return ""


def strip_site_name(title: str, site_name: str) -> str:
    """
    Remove the site name from a page title.

    Handles both "Site Name | Page Title" and "Page Title | Site Name" patterns,
    with any common separator.

    Args:
        title: The full page title
        site_name: The detected site name to remove

    Returns:
        The cleaned title, or original if site name not found
    """
    if not site_name or not title:
        return title

    # Try removing with each separator
    for sep in _TITLE_SEPARATORS:
        # Site name at the start: "Site Name | Page Title"
        prefix = f"{site_name}{sep}"
        if title.startswith(prefix):
            cleaned = title[len(prefix):].strip()
            if cleaned:
                return cleaned

        # Site name at the end: "Page Title | Site Name"
        suffix = f"{sep}{site_name}"
        if title.endswith(suffix):
            cleaned = title[:-len(suffix)].strip()
            if cleaned:
                return cleaned

    return title


# ============================================================================
# Caching
# ============================================================================


def _cache_key(origin: str) -> str:
    """Generate a cache filename for an origin."""
    return hashlib.sha256(origin.encode()).hexdigest()[:16]


def save_to_cache(result: SitemapResult) -> Path:
    """Save a sitemap result to the cache directory."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{_cache_key(result.origin)}.json"

    data = {
        "cached_at": time.time(),
        "result": result.to_dict(),
    }

    cache_file.write_text(json.dumps(data, indent=2))
    return cache_file


def load_from_cache(origin: str) -> Optional[SitemapResult]:
    """
    Load a sitemap result from cache if it exists and is fresh.

    Returns:
        SitemapResult if cache hit, None if miss or stale
    """
    cache_file = CACHE_DIR / f"{_cache_key(origin)}.json"

    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text())

        # Check TTL
        cached_at = data.get("cached_at", 0)
        if time.time() - cached_at > CACHE_TTL:
            return None

        # Reconstruct SitemapResult
        r = data["result"]

        # Strip stale "cache(...)" wrapping from old cache entries (bug fix)
        via = r.get("discovered_via", "")
        while via.startswith("cache (") and via.endswith(")"):
            via = via[7:-1]

        result = SitemapResult(
            origin=r["origin"],
            source_url=r["source_url"],
            discovered_via=via or "unknown",
            is_index=r.get("is_index", False),
            child_sitemaps=r.get("child_sitemaps", []),
            errors=r.get("errors", []),
        )

        for entry_data in r.get("entries", []):
            result.entries.append(
                SitemapEntry(
                    loc=entry_data["loc"],
                    lastmod=entry_data.get("lastmod", ""),
                    changefreq=entry_data.get("changefreq", ""),
                    priority=entry_data.get("priority", ""),
                    title=entry_data.get("title", ""),
                    http_status=entry_data.get("http_status", 0),
                    final_url=entry_data.get("final_url", ""),
                    canonical_url=entry_data.get("canonical_url", ""),
                    content_length=entry_data.get("content_length", 0),
                    etag=entry_data.get("etag", ""),
                    lang=entry_data.get("lang", ""),
                )
            )

        return result

    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def clear_cache(origin: Optional[str] = None) -> int:
    """
    Clear the sitemap cache.

    Args:
        origin: If provided, clear only this origin's cache. Otherwise clear all.

    Returns:
        Number of cache files removed
    """
    if not CACHE_DIR.exists():
        return 0

    if origin:
        cache_file = CACHE_DIR / f"{_cache_key(origin)}.json"
        if cache_file.exists():
            cache_file.unlink()
            return 1
        return 0

    count = 0
    for f in CACHE_DIR.glob("*.json"):
        f.unlink()
        count += 1
    return count
