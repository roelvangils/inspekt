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

from inspekt.services import http_client

logger = logging.getLogger(__name__)

# Sitemap XML namespace
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

# Cache directory
CACHE_DIR = Path.home() / ".cache" / "inspekt" / "sitemaps"

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
    }


# ============================================================================
# Title fetching
# ============================================================================

# Progressive chunk sizes for title fetching — most titles are in the first 16 KB,
# but some SPAs inline 50-80 KB of scripts before the <title> tag
_TITLE_CHUNK_SIZES = [16_384, 32_768, 65_536, 131_072, 524_288]

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


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


def _fetch_single_title(url: str, timeout: float = 3.0) -> tuple[str, str]:
    """
    Fetch a page progressively until the <title> tag is found.

    Also captures the Last-Modified header as a fallback date for sitemaps
    that don't include lastmod.

    Returns:
        Tuple of (title, last_modified_header). Either may be empty.
    """
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

        if response.status_code != 200:
            return "", ""

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

            title = _extract_title(content.decode("utf-8", errors="replace"))
            if title:
                response.close()
                return title, last_modified

            if len(content) < limit:
                break

        response.close()
        return "", last_modified

    except (requests.RequestException, OSError) as e:
        logger.debug(f"Title fetch failed for {url}: {type(e).__name__}: {e}")
        return "", ""


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
    max_concurrent: int = 30,
    timeout: float = 3.0,
    progress_callback=None,
) -> int:
    """
    Fetch page titles for sitemap entries concurrently.

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
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Filter to entries that need titles
    to_fetch = [(i, e) for i, e in enumerate(entries) if not e.title]
    if not to_fetch:
        return 0

    total = len(to_fetch)
    fetched = 0
    completed = 0

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {}
        for idx, entry in to_fetch:
            future = executor.submit(_fetch_single_title, entry.loc, timeout)
            futures[future] = idx

        for future in as_completed(futures):
            idx = futures[future]
            completed += 1
            try:
                title, last_modified = future.result()
                if title:
                    entries[idx].title = title
                    fetched += 1
                # Use Last-Modified header as fallback when sitemap has no lastmod
                if last_modified and not entries[idx].lastmod:
                    entries[idx].lastmod = _parse_http_date(last_modified)
            except Exception:
                pass

            if progress_callback:
                progress_callback(completed, total)

    return fetched


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
