# Handoff: Sitemap-Aware Navigation in Inspekt VM

## What You're Building

Add **structural navigation** to the Inspekt VM's right-click context menu: **Up** (navigate to parent page) and **Down** (submenu showing child pages) buttons that traverse the sitemap tree. Browsers have Back/Forward (temporal), but no concept of moving through a site's content hierarchy. This feature makes that possible.

Additionally, the sitemap should be **auto-fetched in the background** whenever a new domain is visited, so the navigation data is ready before the user right-clicks.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  control-panel.html (Frontend)                              │
│  ├── updateCurrentUrl() — detects URL changes               │
│  │   ├── maybeFetchSitemap() — triggers auto-fetch          │
│  │   └── refreshSitemapNav() — pre-fetches tree for menu    │
│  └── showVNCContextMenu() — builds context menu items       │
│      └── Up/Down buttons use _sitemapNav cached data        │
├─────────────────────────────────────────────────────────────┤
│  API Layer (FastAPI)                                        │
│  └── /api/sitemaps/ router                                  │
│      ├── POST /fetch — trigger sitemap discovery + fetch    │
│      ├── GET /tree — get neighborhood (parent/children)     │
│      └── GET /status — check if sitemap is cached           │
├─────────────────────────────────────────────────────────────┤
│  Service Layer                                              │
│  └── sitemap_service.py                                     │
│      ├── discover_sitemap() — find sitemap URL              │
│      ├── fetch_sitemap() — parse XML                        │
│      ├── build_tree() — URL path → tree hierarchy           │
│      ├── fetch_titles() — enrich entries with page titles   │
│      └── save/load_from_cache() — persistent JSON cache     │
└─────────────────────────────────────────────────────────────┘
```

---

## Decisions Already Made

| Decision | Choice |
|----------|--------|
| API approach | Dedicated FastAPI endpoints (not shell-out) |
| Auto-fetch scope | Sitemap XML only (structure, no titles) on new domain |
| Title enrichment | Lazy — enrich current page + children + siblings on navigation, max 50 entries, 10 concurrent requests |
| Enrichment guardrail | Stop enriching if a level has 50+ un-enriched entries |
| Down submenu cap | 25 items maximum |
| Overflow display | `"(X more pages)"` as a disabled menu item (no "Show all in terminal" link) |
| Up at root | Navigate to sitemap index URL if one exists; otherwise dim the button |
| Not in sitemap | Dim both buttons with tooltip "This page is not in the sitemap" |
| Loading state | Dim buttons with tooltip "Loading sitemap..." until ready; spinner item in submenu if tree data not yet loaded |
| Cache location in VM | Persistent Docker volume at `/root/.config/inspekt/sitemaps/` (via `get_data_dir()`) |
| Cache TTL | 1 hour (existing: 3600 seconds) |
| Rate limiting | 10 concurrent requests for background enrichment (vs 30 for CLI) |

---

## Part 1: VM-Persistent Cache

### File: `inspekt/services/sitemap_service.py`

**Current** (line 38):
```python
CACHE_DIR = Path.home() / ".cache" / "inspekt" / "sitemaps"
```

**Change to:**
```python
from inspekt.config import is_isolated_mode, get_data_dir

def _get_cache_dir() -> Path:
    """Use persistent Docker volume in VM, standard cache dir otherwise."""
    if is_isolated_mode():
        return get_data_dir() / "sitemaps"  # /root/.config/inspekt/sitemaps/
    return Path.home() / ".cache" / "inspekt" / "sitemaps"

CACHE_DIR = _get_cache_dir()
```

**Why:** In the VM, `~/.cache/` is lost on container restart. `get_data_dir()` returns `/root/.config/inspekt/` which is backed by the `inspekt-vm-data` Docker volume (already used for `data.db`).

**Reference:** See `inspekt/config.py` lines 268-295 for `get_data_dir()`.

---

## Part 2: API Endpoints

### New file: `inspekt/app/api/routers/sitemap.py`

Follow the **robots router pattern** (`inspekt/app/api/routers/robots.py`):
- Dedicated Pydantic response models
- `router = APIRouter()`
- Helper functions for business logic
- HTTPException for errors

### Endpoint 1: `POST /api/sitemaps/fetch`

Triggers sitemap discovery and fetch for an origin. Returns immediately if cached.

**Request body:**
```python
class SitemapFetchRequest(BaseModel):
    origin: str = Field(..., description="Site origin, e.g. https://example.com")
```

**Response:**
```python
class SitemapFetchResponse(BaseModel):
    ok: bool
    cached: bool = False
    total_urls: int = 0
    source_url: str = ""
    discovered_via: str = ""
```

**Implementation:**
1. `load_from_cache(origin)` — if hit, return with `cached: true`
2. `discover_sitemap(origin)` — find sitemap URL(s)
3. `fetch_sitemap(url, flatten=True)` — parse XML, no titles
4. `save_to_cache(result)`
5. Return summary

**Important:** This does NOT fetch titles. It only fetches the XML sitemap structure. Title enrichment happens lazily via the `/tree` endpoint.

### Endpoint 2: `GET /api/sitemaps/tree`

Returns the current page's neighborhood: parent, children, siblings.

**Query params:**
```python
@router.get("/tree")
def get_sitemap_tree(
    origin: str = Query(..., description="Site origin"),
    path: str = Query(..., description="Current page path, e.g. /blog/post-1"),
    enrich: bool = Query(True, description="Enrich titles for returned nodes"),
):
```

**Response model:**
```python
class SitemapNodeInfo(BaseModel):
    path: str
    url: str
    title: str = ""
    index: int = 0
    lastmod: str = ""

class SitemapTreeResponse(BaseModel):
    ok: bool
    in_sitemap: bool = False
    current: SitemapNodeInfo | None = None
    parent: SitemapNodeInfo | None = None
    children: list[SitemapNodeInfo] = []
    children_total: int = 0
    siblings: list[SitemapNodeInfo] = []
```

**Implementation:**
1. `load_from_cache(origin)` — if no cache, return `in_sitemap: false`
2. `build_tree(result.entries, origin)` — construct tree
3. Walk tree to find node matching `path` (strip trailing slash, handle `/` as root)
4. If not found, return `in_sitemap: false`
5. Collect: parent node, sibling nodes (same parent's children minus current), child nodes
6. If `enrich=true`:
   - Collect entry indices for current + parent + children + siblings
   - Skip if all already have titles
   - Cap at 50 entries, call `fetch_titles(entries_subset, max_concurrent=10, timeout=3.0)`
   - Re-save to cache
7. Sort children by title (alphabetically) for the submenu
8. Return at most 25 children, set `children_total` to actual count
9. Build `SitemapNodeInfo` objects from tree nodes

**Tree walking helper:**
```python
def _find_node_by_path(root: TreeNode, path: str) -> tuple[TreeNode | None, TreeNode | None]:
    """Find a node and its parent by URL path. Returns (node, parent)."""
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
```

### Endpoint 3: `GET /api/sitemaps/status`

Quick cache check — used by the frontend before triggering a fetch.

**Query params:** `origin: str`

**Response:**
```python
class SitemapStatusResponse(BaseModel):
    ok: bool
    cached: bool = False
    total_urls: int = 0
    age_seconds: float = 0
```

**Implementation:**
1. Check if cache file exists for `_cache_key(origin)`
2. If exists, read `cached_at` timestamp, compute age
3. If age > TTL, return `cached: false`
4. Return summary without loading full result (just read the JSON header)

### Register in `server.py`

**File:** `inspekt/app/api/server.py`

Add to the import block (line ~212):
```python
from inspekt.app.api.routers import (
    ...
    sitemap as sitemap_router,    # ADD THIS (use alias to avoid conflict with CLI sitemap)
)
```

Add to the router registration (after line 248):
```python
app.include_router(sitemap_router.router, prefix="/api/sitemaps", tags=["Sitemaps"])
```

---

## Part 3: Auto-Fetch on Domain Change

### File: `docker/browser-vm/control-panel.html`

Add these variables near the top of the `<script>` section (near other global state):

```javascript
let _sitemapReady = false;           // Has the sitemap been fetched for current origin?
let _sitemapFetchedOrigins = new Set(); // Origins we've already fetched this session
let _sitemapNav = null;              // Cached tree response for current page
```

### `maybeFetchSitemap(url)` — New function

```javascript
async function maybeFetchSitemap(url) {
    try {
        const origin = new URL(url).origin;
        if (_sitemapFetchedOrigins.has(origin)) return;
        _sitemapFetchedOrigins.add(origin);

        // Check if already cached (fast, no fetch)
        const statusResp = await fetch(`/api/sitemaps/status?origin=${encodeURIComponent(origin)}`);
        const status = await statusResp.json();
        if (status.ok && status.cached) {
            _sitemapReady = true;
            return;
        }

        // Fetch sitemap structure in background (XML only, no titles)
        const resp = await fetch('/api/sitemaps/fetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ origin })
        });
        const data = await resp.json();
        if (data.ok && data.total_urls > 0) {
            _sitemapReady = true;
            showToast(`Sitemap indexed (${data.total_urls} pages)`, 'dark');
        }
    } catch (e) {
        console.debug('[Sitemap] Auto-fetch failed:', e);
    }
}
```

### `refreshSitemapNav(url)` — New function

Pre-fetches the tree data so it's ready when the user right-clicks:

```javascript
async function refreshSitemapNav(url) {
    if (!_sitemapReady) {
        _sitemapNav = null;
        return;
    }
    try {
        const u = new URL(url);
        const resp = await fetch(
            `/api/sitemaps/tree?origin=${encodeURIComponent(u.origin)}&path=${encodeURIComponent(u.pathname)}`
        );
        const data = await resp.json();
        _sitemapNav = data.ok ? data : null;
    } catch (e) {
        _sitemapNav = null;
    }
}
```

### Integration point in `updateCurrentUrl()`

**File:** `docker/browser-vm/control-panel.html`, line ~6029

After the existing `triggerAutorunPlugins(currentUrl);` line, add:

```javascript
// Trigger autorun plugins on navigation
triggerAutorunPlugins(currentUrl);
// Sitemap: auto-fetch on new domain, refresh tree for context menu
maybeFetchSitemap(currentUrl);
refreshSitemapNav(currentUrl);
```

Both calls are fire-and-forget (no `await`), so they don't block URL polling.

---

## Part 4: Context Menu Integration

### File: `docker/browser-vm/control-panel.html`, function `showVNCContextMenu()` (line ~12906)

### Add NAV_ICONS.down

**At line 4576** (after the `reload` icon), add:

```javascript
down: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M20 12l-1.41-1.41L13 16.17V4h-2v12.17l-5.58-5.59L4 12l8 8 8-8z"/></svg>',
```

(`NAV_ICONS.up` already exists at line 4575.)

### Modify the navRow in `showVNCContextMenu()`

**Current** (lines 12934-12938):
```javascript
items.push({ navRow: [
    { label: 'Reload', icon: NAV_ICONS.reload, action: () => reloadPage() },
    { label: 'Back', icon: NAV_ICONS.back, action: () => goBack(), disabled: !canGoBack() },
    { label: 'Forward', icon: NAV_ICONS.forward, action: () => goForward(), disabled: !canGoForward() },
] });
```

**Change to:**
```javascript
// Navigation row: Back, Forward, Reload + sitemap Up/Down
const sitemapUp = _sitemapNav && _sitemapNav.in_sitemap && _sitemapNav.parent;
const sitemapDown = _sitemapNav && _sitemapNav.in_sitemap && _sitemapNav.children_total > 0;
const sitemapNotReady = !_sitemapReady;
const notInSitemap = _sitemapReady && (!_sitemapNav || !_sitemapNav.in_sitemap);

items.push({ navRow: [
    { label: 'Reload', icon: NAV_ICONS.reload, action: () => reloadPage() },
    { label: 'Back', icon: NAV_ICONS.back, action: () => goBack(), disabled: !canGoBack() },
    { label: 'Forward', icon: NAV_ICONS.forward, action: () => goForward(), disabled: !canGoForward() },
    { label: 'Up', icon: NAV_ICONS.up, action: () => _sitemapGoUp(),
      disabled: !sitemapUp,
      title: sitemapNotReady ? 'Loading sitemap\u2026' :
             notInSitemap ? 'This page is not in the sitemap' :
             !sitemapUp ? 'Already at the top' :
             _sitemapNav.parent.title || _sitemapNav.parent.path },
    { label: 'Down', icon: NAV_ICONS.down, action: () => {},  // submenu handles it
      disabled: !sitemapDown,
      title: sitemapNotReady ? 'Loading sitemap\u2026' :
             notInSitemap ? 'This page is not in the sitemap' :
             !sitemapDown ? 'No child pages' :
             `${_sitemapNav.children_total} child pages` },
] });
```

**Wait** — the navRow pattern doesn't support submenus on individual buttons. The Down button needs to open a submenu. Let me reconsider.

**Better approach:** Keep the navRow for Reload/Back/Forward. Add Up and Down as **separate menu items** right after the navRow, before the separator. The Down item uses the `children` property for its submenu.

```javascript
// Standard navigation row
items.push({ navRow: [
    { label: 'Reload', icon: NAV_ICONS.reload, action: () => reloadPage() },
    { label: 'Back', icon: NAV_ICONS.back, action: () => goBack(), disabled: !canGoBack() },
    { label: 'Forward', icon: NAV_ICONS.forward, action: () => goForward(), disabled: !canGoForward() },
] });

// Sitemap navigation (Up/Down)
if (_sitemapReady && _sitemapNav && _sitemapNav.in_sitemap) {
    // Up: navigate to parent
    const parentInfo = _sitemapNav.parent;
    items.push({
        label: parentInfo
            ? `\u2191 ${parentInfo.title || parentInfo.path}`
            : '\u2191 Parent page',
        action: parentInfo ? () => _sitemapGoUp() : null,
        disabled: !parentInfo,
        title: parentInfo ? parentInfo.url : 'Already at the top',
    });

    // Down: submenu with children
    if (_sitemapNav.children_total > 0) {
        const childItems = _sitemapNav.children.map(child => ({
            label: child.title || child.path,
            action: () => navigateToSitemapUrl(child.url),
        }));
        if (_sitemapNav.children_total > 25) {
            childItems.push({
                label: `(${_sitemapNav.children_total - 25} more pages)`,
                disabled: true,
            });
        }
        items.push({
            label: `\u2193 Child pages (${_sitemapNav.children_total})`,
            children: childItems,
        });
    } else {
        items.push({
            label: '\u2193 Child pages',
            disabled: true,
            title: 'No child pages',
        });
    }
} else if (_sitemapReady) {
    // Sitemap loaded but page not in it
    items.push({ label: '\u2191 Parent page', disabled: true, title: 'This page is not in the sitemap' });
    items.push({ label: '\u2193 Child pages', disabled: true, title: 'This page is not in the sitemap' });
} else {
    // Sitemap still loading
    items.push({ label: '\u2191 Parent page', disabled: true, title: 'Loading sitemap\u2026' });
    items.push({ label: '\u2193 Child pages', disabled: true, title: 'Loading sitemap\u2026' });
}

items.push({ separator: true });
```

### Navigation helper functions

```javascript
function _sitemapGoUp() {
    if (_sitemapNav && _sitemapNav.parent && _sitemapNav.parent.url) {
        navigateToSitemapUrl(_sitemapNav.parent.url);
    }
}

function navigateToSitemapUrl(url) {
    // Use the same navigation mechanism as "Open Link in New Tab" but in current tab
    fetch(`http://${VNC_HOST}:${CONTROL_PORT}/navigate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
    }).catch(e => console.warn('[Sitemap] Navigation failed:', e));
}
```

**Note:** Check how existing navigation works in the control panel (e.g., `goBack()`, `goForward()`, URL bar navigation). Use the same mechanism. The control server likely has a `/navigate` endpoint or uses CDP.

---

## Key Reference Files

| File | What to look at |
|------|----------------|
| `inspekt/services/sitemap_service.py` | Lines 38 (CACHE_DIR), 122 (discover_sitemap), 199 (fetch_sitemap), 325 (build_tree), 697 (fetch_titles), 921 (save_to_cache), 935 (load_from_cache) |
| `inspekt/app/api/routers/robots.py` | Full file — **pattern to follow** for Pydantic models, router setup, error handling |
| `inspekt/app/api/server.py` | Lines 212-248 — router imports and registration |
| `inspekt/app/api/models.py` | `CommandResponse` — standard response pattern |
| `inspekt/config.py` | Lines 12-26 (`is_isolated_mode`), 268-295 (`get_data_dir`) |
| `docker/browser-vm/control-panel.html` | Lines 4572-4577 (NAV_ICONS), 5994-6052 (updateCurrentUrl), 6847-6872 (triggerAutorunPlugins), 12906-13000 (showVNCContextMenu) |
| `docker/browser-vm/context-menu.js` | Submenu system — `children` property on items, `_openSubmenu()` function, disabled/title handling |

---

## Data Flow Example

**User visits `https://stad.gent/nl/jeugd/turnen`:**

1. `updateCurrentUrl()` detects new URL
2. `maybeFetchSitemap("https://stad.gent/nl/jeugd/turnen")`:
   - New origin → checks `/api/sitemaps/status?origin=https://stad.gent`
   - Not cached → `POST /api/sitemaps/fetch` with `{"origin": "https://stad.gent"}`
   - Backend: discovers sitemap via robots.txt, fetches XML, caches structure
   - Toast: "Sitemap indexed (4200 pages)"
   - Sets `_sitemapReady = true`
3. `refreshSitemapNav("https://stad.gent/nl/jeugd/turnen")`:
   - `GET /api/sitemaps/tree?origin=https://stad.gent&path=/nl/jeugd/turnen`
   - Backend: loads cache, builds tree, finds node at `/nl/jeugd/turnen`
   - Enriches titles for: parent (`/nl/jeugd`), current page, children, siblings (10 concurrent requests)
   - Returns parent + 15 children + 8 siblings with titles
   - `_sitemapNav` cached in JS

4. **User right-clicks:**
   - `showVNCContextMenu()` reads `_sitemapNav` (already loaded)
   - Shows: `↑ Jeugd` (parent), `↓ Child pages (15)` with submenu
   - Submenu shows 15 child pages with titles, sorted alphabetically

5. **User clicks a child page:**
   - `navigateToSitemapUrl(child.url)` navigates the browser
   - `updateCurrentUrl()` fires → `refreshSitemapNav()` updates tree for new page

---

## Testing Checklist

- [ ] Cache persists across `make vm-rebuild`
- [ ] `POST /api/sitemaps/fetch` returns summary for a real site
- [ ] `GET /api/sitemaps/tree` returns parent/children/siblings
- [ ] `GET /api/sitemaps/status` reports cached/not-cached correctly
- [ ] Toast appears on first visit to a new domain
- [ ] Context menu shows Up/Down after sitemap loads
- [ ] Down submenu shows child pages with titles
- [ ] Up navigates to parent page
- [ ] Buttons dimmed when page not in sitemap
- [ ] Buttons dimmed with "Loading..." before sitemap is ready
- [ ] "(X more pages)" appears when children > 25
- [ ] At root: Up goes to sitemap index URL or is dimmed
- [ ] No duplicate fetches for same origin in a session
- [ ] `python3 -m pytest tests/unit/ -x -q` passes

---

## Implementation Order

### Session 1: Backend
1. VM-persistent cache path in `sitemap_service.py`
2. Create `inspekt/app/api/routers/sitemap.py` with all 3 endpoints
3. Register router in `server.py`
4. Test endpoints with curl

### Session 2: Frontend
1. Add `NAV_ICONS.down` icon
2. Add `maybeFetchSitemap()` and `refreshSitemapNav()` functions
3. Hook into `updateCurrentUrl()`
4. Add Up/Down items to `showVNCContextMenu()`
5. Add `_sitemapGoUp()` and `navigateToSitemapUrl()` helpers
6. Test in VM
