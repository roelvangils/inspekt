# Sitemap-Aware Navigation

The VM context menu provides **structural navigation** — Up (parent page) and Down (child pages) — by traversing the site's sitemap tree. Browsers have Back/Forward (temporal), but no concept of moving through a site's content hierarchy.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  control-panel.html (Frontend)                              │
│  ├── updateCurrentUrl() — detects URL changes               │
│  │   ├── maybeFetchSitemap() — triggers auto-fetch          │
│  │   └── refreshSitemapNav() — pre-fetches tree for menu    │
│  └── showVNCContextMenu() — builds context menu items       │
│      └── _buildSitemapSubmenuItems() — recursive builder    │
├─────────────────────────────────────────────────────────────┤
│  API Layer (FastAPI)                                        │
│  └── /api/sitemaps/ router (sitemap.py)                     │
│      ├── POST /fetch — trigger sitemap discovery + fetch    │
│      ├── GET  /tree  — get recursive neighborhood           │
│      └── GET  /status — check if sitemap is cached          │
├─────────────────────────────────────────────────────────────┤
│  Service Layer                                              │
│  └── sitemap_service.py                                     │
│      ├── discover_sitemap() — find sitemap URL via robots   │
│      ├── fetch_sitemap() — parse XML into SitemapEntry list │
│      ├── build_tree() — URL paths → tree hierarchy          │
│      ├── fetch_titles() — enrich entries with page titles   │
│      ├── detect_site_name() / strip_site_name() — clean up  │
│      └── save/load_from_cache() — persistent JSON cache     │
├─────────────────────────────────────────────────────────────┤
│  CLI                                                        │
│  └── inspekt sitemap                                        │
│      └── Shares the same cache — titles from browsing are   │
│          reused, and CLI-fetched titles are available to VM  │
└─────────────────────────────────────────────────────────────┘
```

## End-to-End Flow

### 1. URL Change Detection

`control-panel.html` polls the browser URL every 2 seconds via `updateCurrentUrl()`. When it detects a new URL, it fires two async calls (fire-and-forget, no `await`):

```javascript
maybeFetchSitemap(currentUrl);   // once per domain
refreshSitemapNav(currentUrl);   // every URL change
```

`maybeFetchSitemap` resets `_sitemapReady` and `_sitemapNav` **synchronously** before its first `await`, so stale data from a previous domain is cleared immediately.

### 2. Sitemap Fetch (Once Per Domain)

`maybeFetchSitemap(url)` extracts the origin (e.g., `https://stad.gent`) and checks if we've already fetched this domain's sitemap this session. If not:

1. **Cache check** — `GET /api/sitemaps/status` asks the server if a fresh cache exists. If yes, skip to step 3.
2. **Discovery** — `POST /api/sitemaps/fetch` triggers `discover_sitemap(origin)`, which fetches `robots.txt` and looks for `Sitemap:` directives. Falls back to probing `/sitemap.xml`.
3. **XML fetch** — `fetch_sitemap(url, flatten=True)` downloads and parses the XML. For sitemap index files (`<sitemapindex>`), it recursively fetches child sitemaps and merges all `<url>` entries.
4. **Cache** — saves the result (list of `SitemapEntry` objects) as JSON. **No titles are fetched at this stage** — only URLs, lastmod, and other XML-provided metadata.
5. **Toast** — shows "Sitemap indexed (N pages)" in the VM.

!!! info "Retry & Error Handling"
    - **Network error**: `_sitemapReady` is set to `true` (so the menu isn't stuck on "Loading…"), but the origin is NOT added to `_sitemapFetchedOrigins` — navigating within the domain retries.
    - **No sitemap found**: marked as done permanently. Context menu simply doesn't show Up/Down items.
    - **API not ready at startup**: retries on next URL change.

### 3. Tree Building and Title Enrichment

`refreshSitemapNav(url)` calls `GET /api/sitemaps/tree?origin=...&path=/nl`. An `AbortController` cancels any in-flight request so stale responses from a previous navigation don't overwrite the current one.

#### 3a. Load Cache

Reads the JSON cache with N `SitemapEntry` objects (URLs, possibly with titles from previous enrichment).

#### 3b. Build Tree

`build_tree(entries, origin)` converts the flat URL list into a path-based tree. For each entry URL, it splits the path into segments and creates tree nodes for every segment:

```
Sitemap entry: https://stad.gent/nl/burgerzaken/identiteitskaart

Tree nodes created:
  root (stad.gent)      ← full_path="/"
    └── nl               ← full_path="/nl"           entry=None  (VIRTUAL)
         └── burgerzaken  ← full_path="/nl/burgerzaken"  entry=None  (VIRTUAL)
              └── identiteitskaart  ← entry=SitemapEntry(loc="https://...")
```

Only the **deepest node** gets the `SitemapEntry` attached. Intermediate path segments are "virtual" nodes — they exist for tree structure but don't have a corresponding entry in the sitemap XML.

!!! warning "Virtual Nodes"
    A virtual node at `/nl/burgerzaken` does NOT mean that URL doesn't exist as a real page — it just means the site owner didn't include it in their sitemap. The page may well exist and have a title. Virtual nodes are enriched in the next step.

#### 3c. Find Current Node

`_find_node_by_path(tree, "/nl")` walks the tree to locate the node matching the current page's path. Returns `(node, parent)`.

#### 3d. Enrich Titles (BFS, Cached)

`_enrich_nodes()` collects nodes **breadth-first** (level 1 first, then level 2, etc.) and enriches up to 50 entries per request:

- **Real nodes** (have an entry but no title) — added to the enrich list
- **Virtual nodes** (no entry) — a `SitemapEntry(loc=origin+path)` is created, attached to the node, and added to the enrich list

`fetch_titles()` does concurrent HTTP GET requests (max 10, 3s timeout each) to each URL and extracts the `<title>` tag. If a URL returns 404, the title stays empty and `http_status` is set to 404.

**Caching enriched titles:** After enrichment, virtual entries that got a title are appended to `result.entries` (with duplicate URL checking) and saved to cache. This means subsequent `/tree` calls find those entries already in the cache — `build_tree` attaches them to the correct nodes, and `_enrich_nodes` skips them (already titled).

!!! note "Performance"
    - First call for a page: ~0.2-0.4s (enriches 50 titles via HTTP)
    - Subsequent calls: ~0.02s (all titles cached)
    - The BFS order ensures level 1 children (most visible in the submenu) get priority

#### 3e. Site Name Stripping

`detect_site_name()` finds the common fragment across titles (e.g., "Stad Gent" in "Burgerzaken | Stad Gent"). `strip_site_name()` removes it for display. Both functions exist in `sitemap_service.py` and are reused by the CLI.

**Important:** The cache always stores **raw titles** (with site name). Stripping happens at display time in both the API (via `_node_to_info`) and the CLI (after loading from cache). This means each consumer is independent and the cache stays a clean source of truth.

#### 3f. Build Recursive Response

`_build_recursive_children()` walks the tree up to **4 levels deep**, converting each `TreeNode` into a `SitemapNodeInfo` with nested `children`:

```json
{
  "path": "/nl/blaarmeersen",
  "url": "https://stad.gent/nl/blaarmeersen",
  "title": "Blaarmeersen",
  "exists": true,
  "children_total": 6,
  "children": [
    { "path": "/nl/blaarmeersen/recreatie", "title": "Recreatie", "children_total": 5, "children": [...] },
    { "path": "/nl/blaarmeersen/sporten", "title": "Sporten", "children_total": 9, "children": [...] }
  ]
}
```

Children are sorted by title (alphabetically, with site name stripped) and capped at 25 per level.

### 4. Context Menu

When the user right-clicks, `showVNCContextMenu()` reads `_sitemapNav` (already cached in JS from step 3) **synchronously** — no API call needed.

The Up/Down section only appears when sitemap data exists for the current page. Sites without sitemaps, or pages not in the sitemap, simply don't show the section — no disabled items cluttering the menu.

#### Recursive Submenu Builder

`_buildSitemapSubmenuItems(children, childrenTotal)` recursively maps API children to menu items:

- **Leaf nodes** (no children): `{ label, action: navigateTo(url) }` — click navigates
- **Branch nodes** (has children): `{ label, children: [...] }` — opens a submenu
- **Branch nodes that are real pages**: prepend `Open "[title]"` as the first submenu item so the page itself remains navigable

Items are split into **titled** (shown first) and **untitled** groups:
- Titled items appear at the top with their real page titles
- Untitled items appear below a separator with a "Not in sitemap" header, showing the last path segment as label (e.g., `/duiken-de-blaarmeersen`)

#### 404 Handling

The `exists` field on `SitemapNodeInfo` is `false` when `http_status >= 400`:

- **Branch nodes that don't exist**: shown (they have children), but the "Open" item is omitted from their submenu
- **Leaf nodes that don't exist**: hidden entirely

#### Context Menu Depth Limit

The context menu system supports up to **6 menus total** (root + "↓ Child pages" submenu + 4 drill-down levels). This is set in `context-menu.js` line 456.

## Data Flow Diagram

```
User visits stad.gent/nl
        │
        ▼
updateCurrentUrl() detects URL change
        │
        ├──▶ maybeFetchSitemap("https://stad.gent/nl")
        │         │
        │         ├─ GET /api/sitemaps/status → not cached
        │         ├─ POST /api/sitemaps/fetch
        │         │     ├─ GET robots.txt → finds sitemap.xml
        │         │     ├─ GET sitemap.xml → <sitemapindex> with 3 children
        │         │     ├─ GET child1.xml → 1500 <url> entries
        │         │     ├─ GET child2.xml → 1200 <url> entries
        │         │     ├─ GET child3.xml → 1305 <url> entries
        │         │     └─ Cache: 4005 SitemapEntry objects (titles empty)
        │         │
        │         ├─ Toast: "Sitemap indexed (4005 pages)"
        │         └─ calls refreshSitemapNav()
        │
        └──▶ refreshSitemapNav("https://stad.gent/nl")
                  │
                  └─ GET /api/sitemaps/tree?origin=...&path=/nl
                        │
                        ├─ Load 4005 entries from cache
                        ├─ build_tree() → tree with ~70 children under /nl
                        ├─ _find_node_by_path("/nl") → node + parent
                        ├─ _enrich_nodes() (BFS, max 50):
                        │     ├─ Level 1: 25 children enriched
                        │     ├─ Level 2: 25 more children enriched
                        │     ├─ Virtual entries with titles added to cache
                        │     └─ save_to_cache() for persistence
                        ├─ detect_site_name() → "Stad Gent"
                        ├─ _build_recursive_children() → 4 levels deep
                        │
                        └─ Response: recursive tree with titles

     _sitemapNav = response  (cached in JS)

     User right-clicks → context menu reads _sitemapNav instantly
     Hover "Blaarmeersen" → submenu with 6 children
     Hover "Recreatie" → submenu with 5 children (4 levels deep)
```

## Shared Cache Between CLI and VM

The CLI `inspekt sitemap` command and the VM's API layer share the **same JSON cache** at `~/.cache/inspekt/sitemaps/` (or Docker volume in VM). This means:

- **Browsing enriches the CLI**: Navigating pages in the VM triggers `/tree` calls that enrich titles and save them to cache. When you later run `inspekt sitemap`, those titles are already available.
- **CLI enriches the VM**: Running `inspekt sitemap` fetches titles for all entries. The next time the VM's context menu loads, it finds cached titles.
- **The CLI reports cache status**: `142 of 4005 titles already cached` before fetching the remaining ones.

**Raw titles in cache:** The cache always stores raw titles (e.g., "Burgerzaken | Stad Gent"). Site name stripping happens at display time in both consumers. `strip_site_name()` is idempotent, so calling it on already-stripped titles is safe.

## Cache

### Location

| Environment | Path |
|-------------|------|
| Normal (CLI) | `~/.cache/inspekt/sitemaps/<hash>.json` |
| VM (Docker) | `/root/.config/inspekt/sitemaps/<hash>.json` (persistent Docker volume) |

The hash is `sha256(origin)[:16]`. Cache TTL is 1 hour (3600 seconds).

### What's Cached

The JSON cache stores the full `SitemapResult`:

- All `SitemapEntry` objects (URL, title, lastmod, HTTP status, etc.)
- Virtual entries that were enriched (appended after title fetch, deduplicated by URL)
- Discovery metadata (source URL, discovered via robots.txt/probe)
- Timestamp for TTL validation

## Key Files

| File | Role |
|------|------|
| `inspekt/services/sitemap_service.py` | Service layer: discovery, XML parsing, tree building, title fetching, caching, site name detection |
| `inspekt/app/api/routers/sitemap.py` | API layer: 3 FastAPI endpoints, recursive tree builder, BFS enrichment, 404 detection |
| `inspekt/app/api/server.py` | Router registration at `/api/sitemaps` |
| `inspekt/app/cli/sitemap.py` | CLI command: tree display, interactive picker, cache-aware title fetching |
| `docker/browser-vm/control-panel.html` | Frontend: auto-fetch, tree pre-loading, recursive submenu builder, abort controller |
| `docker/browser-vm/js/context-menu.js` | Generic context menu system (recursive submenus, depth limit of 6) |

## Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Auto-fetch scope | XML structure only (no titles) | Keep initial fetch fast (<1s); titles are enriched lazily |
| Title enrichment | Lazy, BFS-ordered, on `/tree` request | Only fetch titles for pages the user will actually see; level 1 gets priority |
| Virtual node handling | Create entries, fetch real titles, cache results | Don't guess — verify via HTTP; persist so subsequent calls are instant |
| Enrichment concurrency | 10 (API) / 20 (CLI) | Background API shouldn't overload; CLI is user-initiated |
| Enrichment cap | 50 entries per `/tree` request | Keeps response time under 0.5s; deeper levels enrich on navigation |
| Recursive depth | 4 levels in API response, 6 menu levels total | Practical limit for context menu UX |
| Children per level | 25 | Context menu readability; overflow shown as "(N more pages)" |
| Cache stores raw titles | Site name stripped at display time | Each consumer (CLI/API) is independent; cache is source of truth |
| 404 handling | `exists: false` field on SitemapNodeInfo | Leaf 404s hidden; branch 404s shown (gateway to children) but "Open" item omitted |
| Cache persistence in VM | Docker volume at `/root/.config/inspekt/` | Survives container restarts (same as `data.db`) |
| Retry on network error | Don't mark origin as fetched | API might not be ready at startup; retry on next nav |
| AbortController on refreshSitemapNav | Cancel stale in-flight requests | Prevents race condition where old response overwrites newer one |
| Context menu hidden when no data | Don't show disabled items | Sites without sitemaps get a clean menu; no clutter |
