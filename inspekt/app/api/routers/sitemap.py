"""Sitemap API endpoints for structural navigation.

Provides endpoints for fetching, caching, and querying sitemap data.
Used by the VM control panel for Up/Down navigation in the context menu.
"""

import logging

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from inspekt.services import sitemap_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================


class SitemapFetchRequest(BaseModel):
    """Request body for sitemap fetch."""

    origin: str = Field(..., description="Site origin, e.g. https://example.com")


class SitemapFetchResponse(BaseModel):
    """Response from sitemap fetch."""

    ok: bool
    cached: bool = False
    total_urls: int = 0
    source_url: str = ""
    discovered_via: str = ""
    error: str = ""


class SitemapNodeInfo(BaseModel):
    """Info about a single node in the sitemap tree.

    Recursive: children may themselves contain children (up to 4 levels).
    """

    path: str
    url: str
    title: str = ""
    lastmod: str = ""
    exists: bool = True
    children: list["SitemapNodeInfo"] = []
    children_total: int = 0


# Required for Pydantic v2 self-referencing models
SitemapNodeInfo.model_rebuild()


class SitemapTreeResponse(BaseModel):
    """Response from sitemap tree query."""

    ok: bool
    in_sitemap: bool = False
    current: SitemapNodeInfo | None = None
    parent: SitemapNodeInfo | None = None
    children: list[SitemapNodeInfo] = []
    children_total: int = 0
    siblings: list[SitemapNodeInfo] = []


class SitemapStatusResponse(BaseModel):
    """Response from sitemap status check."""

    ok: bool
    cached: bool = False
    total_urls: int = 0
    age_seconds: float = 0


# ============================================================================
# Helpers
# ============================================================================


def _find_node_by_path(
    root: sitemap_service.TreeNode, path: str
) -> tuple[sitemap_service.TreeNode | None, sitemap_service.TreeNode | None]:
    """Find a node and its parent by URL path. Returns (node, parent)."""
    # Normalize: strip trailing slash, treat empty as root
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


def _node_to_info(
    node: sitemap_service.TreeNode, origin: str, site_name: str = ""
) -> SitemapNodeInfo:
    """Convert a TreeNode to a SitemapNodeInfo response object."""
    entry = node.entry
    path = node.full_path or "/"
    url = f"{origin}{path}"
    title = entry.title if entry else ""
    if title and site_name:
        title = sitemap_service.strip_site_name(title, site_name)
    # A node "exists" if it hasn't been checked yet (http_status=0) or got a 2xx/3xx
    exists = not entry or entry.http_status == 0 or entry.http_status < 400
    return SitemapNodeInfo(
        path=path,
        url=url,
        title=title,
        exists=exists,
        lastmod=entry.lastmod if entry else "",
    )


def _enrich_nodes(
    nodes: list[sitemap_service.TreeNode],
    origin: str,
    result: sitemap_service.SitemapResult,
) -> None:
    """Enrich a set of tree nodes with page titles (in-place, max 50).

    For "virtual" nodes (path segments not in the sitemap), creates a
    SitemapEntry and attempts to fetch the title from the URL. Entries
    that get a title are added to result.entries so they're cached.
    """
    entries_to_enrich = []
    virtual_entries = []
    for node in nodes:
        if node.entry and not node.entry.title:
            entries_to_enrich.append(node.entry)
        elif not node.entry and node.full_path and node.full_path != "/":
            # Virtual node — create an entry so we can fetch its title
            entry = sitemap_service.SitemapEntry(loc=f"{origin}{node.full_path}")
            node.entry = entry
            entries_to_enrich.append(entry)
            virtual_entries.append(entry)
    if not entries_to_enrich:
        return

    # Cap at 50 entries, use lower concurrency for background enrichment
    entries_to_enrich = entries_to_enrich[:50]
    try:
        sitemap_service.fetch_titles(
            entries_to_enrich, max_concurrent=10, timeout=3.0
        )
        # Persist virtual entries that got a title into the cache so
        # subsequent /tree calls don't need to re-fetch them.
        # Check by URL to avoid duplicates from repeated calls.
        cached_urls = {e.loc for e in result.entries}
        for entry in virtual_entries:
            if entry.title and entry.loc not in cached_urls:
                result.entries.append(entry)
        sitemap_service.save_to_cache(result)
    except Exception as e:
        logger.debug("Title enrichment failed: %s", e)


def _sort_key(node: sitemap_service.TreeNode, site_name: str = "") -> str:
    """Sort key for tree nodes: stripped title (lowercase), falling back to name."""
    title = node.entry.title if node.entry and node.entry.title else ""
    if title and site_name:
        title = sitemap_service.strip_site_name(title, site_name)
    return title.lower() if title else node.name.lower()


def _build_recursive_children(
    node: sitemap_service.TreeNode,
    origin: str,
    site_name: str = "",
    max_depth: int = 4,
    per_level: int = 25,
    _depth: int = 0,
) -> list[SitemapNodeInfo]:
    """Build a recursive list of SitemapNodeInfo from a node's children.

    Each child that itself has children is recursed up to max_depth levels.
    Children are sorted by title and capped at per_level items.
    """
    if _depth >= max_depth:
        return []

    child_nodes = sorted(
        node.children.values(), key=lambda n: _sort_key(n, site_name)
    )[:per_level]

    result = []
    for child in child_nodes:
        info = _node_to_info(child, origin, site_name)
        grandchild_count = len(child.children)
        if grandchild_count > 0:
            info.children_total = grandchild_count
            info.children = _build_recursive_children(
                child, origin, site_name, max_depth, per_level, _depth + 1
            )
        result.append(info)

    return result


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/fetch", response_model=SitemapFetchResponse)
def fetch_sitemap(request: SitemapFetchRequest):
    """Trigger sitemap discovery and fetch for an origin.

    Returns immediately if the sitemap is already cached.
    Only fetches the XML structure — no page titles.
    """
    origin = request.origin.rstrip("/")

    # Check cache first
    cached = sitemap_service.load_from_cache(origin)
    if cached:
        return SitemapFetchResponse(
            ok=True,
            cached=True,
            total_urls=cached.total_urls,
            source_url=cached.source_url,
            discovered_via=cached.discovered_via,
        )

    # Discover sitemap URL(s)
    try:
        urls, method = sitemap_service.discover_sitemap(origin)
    except Exception as e:
        return SitemapFetchResponse(ok=False, error=f"Discovery failed: {e}")

    if not urls:
        return SitemapFetchResponse(ok=False, error="No sitemap found")

    # Fetch and parse the first discovered sitemap (flatten index sitemaps)
    try:
        result = sitemap_service.fetch_sitemap(urls[0], flatten=True)
        result.origin = origin
        result.discovered_via = method
        result.source_url = urls[0]
    except Exception as e:
        return SitemapFetchResponse(ok=False, error=f"Fetch failed: {e}")

    if not result.entries:
        return SitemapFetchResponse(
            ok=False, error="Sitemap was empty", source_url=result.source_url
        )

    # Cache the result
    sitemap_service.save_to_cache(result)

    return SitemapFetchResponse(
        ok=True,
        cached=False,
        total_urls=result.total_urls,
        source_url=result.source_url,
        discovered_via=method,
    )


@router.get("/tree", response_model=SitemapTreeResponse)
def get_sitemap_tree(
    origin: str = Query(..., description="Site origin"),
    path: str = Query(..., description="Current page path, e.g. /blog/post-1"),
    enrich: bool = Query(True, description="Enrich titles for returned nodes"),
):
    """Get the current page's neighborhood: parent, children, siblings.

    Used by the context menu to build Up/Down navigation items.
    """
    origin = origin.rstrip("/")

    # Load from cache
    result = sitemap_service.load_from_cache(origin)
    if not result:
        return SitemapTreeResponse(ok=True, in_sitemap=False)

    # Build tree and find current node
    tree = sitemap_service.build_tree(result.entries, origin)
    node, parent = _find_node_by_path(tree, path)

    if node is None:
        return SitemapTreeResponse(ok=True, in_sitemap=False)

    total_children = len(node.children)

    # Collect sibling nodes (same parent's children minus current)
    sibling_nodes = []
    if parent:
        sibling_nodes = sorted(
            [c for c in parent.children.values() if c is not node],
            key=lambda n: n.name,
        )

    # Enrich titles breadth-first across all levels. Level 1 children
    # get priority, then level 2, etc. _enrich_nodes caps at 50 entries
    # and results are cached so subsequent calls are instant.
    nodes_to_enrich = []
    if enrich:
        # BFS: collect nodes level by level (same order as the submenu tree)
        nodes_to_enrich = [node]
        if parent:
            nodes_to_enrich.append(parent)
        queue = [node]
        while queue and len(nodes_to_enrich) < 60:
            current = queue.pop(0)
            children = sorted(current.children.values(), key=lambda n: n.name)[:25]
            nodes_to_enrich.extend(children)
            for child in children:
                if child.children:
                    queue.append(child)
        nodes_to_enrich.extend(sibling_nodes[:10])
        _enrich_nodes(nodes_to_enrich, origin, result)

    # Detect site name from enriched nodes to strip from titles
    enriched_entries = [
        n.entry for n in nodes_to_enrich
        if n.entry and n.entry.title
    ]
    site_name = sitemap_service.detect_site_name(enriched_entries)

    # Build recursive children (up to 4 levels, 25 per level)
    recursive_children = _build_recursive_children(node, origin, site_name)

    return SitemapTreeResponse(
        ok=True,
        in_sitemap=True,
        current=_node_to_info(node, origin, site_name),
        parent=_node_to_info(parent, origin, site_name) if parent else None,
        children=recursive_children,
        children_total=total_children,
        siblings=[_node_to_info(s, origin, site_name) for s in sibling_nodes[:25]],
    )


@router.get("/status", response_model=SitemapStatusResponse)
def get_sitemap_status(
    origin: str = Query(..., description="Site origin"),
):
    """Quick cache check — used by the frontend before triggering a fetch."""
    origin = origin.rstrip("/")

    # load_from_cache handles TTL validation and returns None if stale
    result = sitemap_service.load_from_cache(origin)
    if not result:
        return SitemapStatusResponse(ok=True, cached=False)

    return SitemapStatusResponse(
        ok=True, cached=True, total_urls=result.total_urls
    )
