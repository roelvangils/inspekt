"""
Overlay Bus DOM-cleanliness invariant.

Asserts that when the Inspekt accessibility audit runs in VM mode (with the
overlay bus producer transport "ready"), badges and popovers are emitted to
window.InspektOverlayBus instead of being injected into the inspected page's
DOM. Host-side rendering over the noVNC canvas — not in-page — is the
defining promise of the bus.

This is an integration test, not a true VM e2e test: it spins up a headless
Chromium via Playwright and stubs window.InspektOverlayBus + the ready flag
to simulate the in-VM environment, then runs run_axe.js end-to-end against a
seeded violation. If any future change makes the audit script fall back to
the DOM badge path while the bus is reachable, the assertions below break.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not PLAYWRIGHT_AVAILABLE, reason="Playwright not installed"),
]


# Stub of window.InspektOverlayBus that the badge-emit path expects to find.
# Records all calls so the test can also assert the bus path was actually
# taken (vs. the script silently no-opping). Mirrors the API surface of
# extensions/chrome/overlay-bus-main.js so a missing method is a regression.
_BUS_STUB_JS = """
(function () {
    const calls = [];
    window.__inspektBusCalls = calls;
    window.__INSPEKT_OVERLAY_BUS_READY__ = true;
    window.InspektOverlayBus = {
        set:      function (id, kind, rect, payload, opts) {
            calls.push({ method: 'set', id: String(id), kind: String(kind) });
            return id;
        },
        update:   function (id, partial) { calls.push({ method: 'update', id: String(id) }); },
        clear:    function (id) { calls.push({ method: 'clear', id: String(id) }); },
        clearAll: function (prefix) { calls.push({ method: 'clearAll', prefix: prefix || '' }); },
        track:    function (id, selector, opts) { calls.push({ method: 'track', id: String(id) }); },
        on:       function (id, event, cb) { return function () {}; },
        snapshot: function () { return Promise.resolve([]); },
        _emitInspect: function () {},
    };
})();
"""


@pytest.fixture(scope="module")
def project_root() -> Path:
    return Path(__file__).parent.parent.parent


@pytest.fixture(scope="module")
def axe_lib_source(project_root: Path) -> str:
    path = project_root / "inspekt" / "scripts" / "vendor" / "axe-core.min.js"
    if not path.exists():
        pytest.skip(f"axe-core library not found at {path}")
    return path.read_text()


@pytest.fixture(scope="module")
def run_axe_template(project_root: Path) -> str:
    path = project_root / "inspekt" / "scripts" / "run_axe.js"
    return path.read_text()


@pytest.fixture(scope="module")
def chromium():
    """Module-scoped headless Chromium. Skipped if launch fails (e.g. on CI
    without browser binaries installed)."""
    pw = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
    except Exception as e:
        # Stop playwright before skipping: .start() leaves an event loop
        # running in the main thread, which breaks later pytest-asyncio tests.
        if pw is not None:
            pw.stop()
        pytest.skip(f"Failed to launch Chromium: {e}")
        return  # unreachable, satisfies type checkers

    yield browser
    browser.close()
    pw.stop()


def _run_axe_and_emit(page, run_axe_template: str, *, persistent: bool = False) -> dict:
    """Templated invocation of run_axe.js. Returns the audit result dict."""
    config = {
        "runOnly": {"type": "rule", "values": ["button-name"]},
        "__showBadges": True,
        "__interactiveBadges": False,
        "__devCss": False,
        "__persistent": persistent,
    }
    audit_script = run_axe_template.replace("__AXE_CONFIG__", json.dumps(config))
    # The audit script is `(async function () { ... })();` — already a Promise
    # at the top-level expression. Wrap so page.evaluate can await it.
    wrapper = f"(async () => {{ return await {audit_script}; }})()"
    return page.evaluate(wrapper)


class TestOverlayBusDomCleanliness:
    """
    Invariant: in VM mode, run_axe.js emits to window.InspektOverlayBus and
    leaves the inspected page's DOM untouched.
    """

    def test_no_dom_badges_when_bus_ready(
        self, chromium, axe_lib_source: str, run_axe_template: str
    ) -> None:
        ctx = chromium.new_context()
        try:
            # Seed the bus stub before any other script runs. add_init_script
            # applies to every navigation in this context, including the
            # set_content below.
            ctx.add_init_script(_BUS_STUB_JS)
            page = ctx.new_page()
            # Empty <button> triggers axe's `button-name` rule (no accessible name).
            page.set_content(
                "<!doctype html><html><body><button id='b'></button></body></html>"
            )
            page.add_script_tag(content=axe_lib_source)

            result = _run_axe_and_emit(page, run_axe_template)
            assert result is not None, "run_axe.js returned undefined"

            # Bus was actually exercised (vs. silently bypassed).
            bus_calls = page.evaluate("window.__inspektBusCalls")
            methods = [c["method"] for c in bus_calls]
            assert "set" in methods, (
                f"Expected at least one InspektOverlayBus.set() call; "
                f"got methods={methods!r}"
            )
            assert any(
                c["method"] == "set" and c["kind"] == "badge" for c in bus_calls
            ), f"Expected a 'badge' overlay set call; got {bus_calls!r}"

            # ── DOM-cleanliness invariant ──────────────────────────────
            in_page_badges = page.evaluate(
                "document.querySelectorAll("
                "'[data-inspekt-axe-badge], [data-inspekt-axe-popover]'"
                ").length"
            )
            assert in_page_badges == 0, (
                f"Expected zero in-page badge/popover nodes when bus is ready; "
                f"found {in_page_badges}"
            )

            body_html = page.evaluate("document.body.innerHTML")
            assert "inspekt-badge-" not in body_html, (
                "Page DOM contains 'inspekt-badge-' substring — DOM badge "
                "injection must not run when bus is ready"
            )
            assert "inspekt-popover-" not in body_html, (
                "Page DOM contains 'inspekt-popover-' substring — DOM popover "
                "injection must not run when bus is ready"
            )
        finally:
            ctx.close()
