"""Unit tests for bridge_ws pure functions.

These cover the parsing/validation/bookkeeping helpers that operate on
bridge_ws's module-level state, without starting any server. Integration
tests for the HTTP/WS surface live in tests/integration/test_bridge_http.py
and test_bridge_ws_protocol.py.
"""

import time

import pytest

from inspekt import bridge_ws


@pytest.fixture(autouse=True)
def reset_bridge_state():
    """Clear all bridge_ws module-level state before and after each test.

    bridge_ws keeps its runtime state in module globals; without this,
    tests pass alone but fail in suite order.
    """

    def _clear():
        bridge_ws.active_connections.clear()
        bridge_ws.browser_info.clear()
        bridge_ws.pending_requests.clear()
        bridge_ws.completed_requests.clear()
        bridge_ws.pending_events.clear()
        bridge_ws.ack_events.clear()
        bridge_ws.instance_ids.clear()
        bridge_ws.instance_aliases.clear()
        bridge_ws.instance_id_to_ws.clear()
        bridge_ws.connection_times.clear()
        bridge_ws.set_active_connection(None)

    _clear()
    yield
    _clear()


class TestParseUserAgent:
    """Table-driven tests for parse_user_agent."""

    @pytest.mark.parametrize(
        ("user_agent", "expected_name", "expected_version"),
        [
            ("", "Unknown", ""),
            (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) "
                "Gecko/20100101 Firefox/119.0",
                "Firefox",
                "119.0",
            ),
            (
                "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 "
                "Firefox/120.0 Zen/1.0.1",
                "Zen Browser",
                "1.0.1",
            ),
        ],
    )
    def test_known_browsers(self, user_agent, expected_name, expected_version):
        name, version = bridge_ws.parse_user_agent(user_agent)
        assert name == expected_name
        assert version == expected_version

    def test_chrome_ua_returns_name_and_version(self):
        ua = (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        name, version = bridge_ws.parse_user_agent(ua)
        assert name == "Chrome"
        assert version.startswith("120")


class TestIsValidBrowserInfo:
    """Accept/reject cases for is_valid_browser_info."""

    def test_none_and_empty_rejected(self):
        assert bridge_ws.is_valid_browser_info(None) is False
        assert bridge_ws.is_valid_browser_info({}) is False

    def test_unknown_ua_rejected(self):
        info = {"userAgent": "Unknown", "extensionVersion": "1.0.0"}
        assert bridge_ws.is_valid_browser_info(info) is False

    def test_short_ua_rejected(self):
        info = {"userAgent": "short", "extensionVersion": "1.0.0"}
        assert bridge_ws.is_valid_browser_info(info) is False

    def test_missing_extension_version_rejected(self):
        info = {"userAgent": "Mozilla/5.0 (Macintosh) Chrome/120.0"}
        assert bridge_ws.is_valid_browser_info(info) is False

    def test_valid_info_accepted(self):
        info = {
            "userAgent": "Mozilla/5.0 (Macintosh) Chrome/120.0",
            "extensionVersion": "1.0.0",
        }
        assert bridge_ws.is_valid_browser_info(info) is True


class TestCleanupOldRequests:
    """cleanup_old_requests drops entries older than MAX_REQUEST_AGE."""

    def test_expired_requests_removed_fresh_kept(self):
        now = time.time()
        old = now - bridge_ws.MAX_REQUEST_AGE - 1
        bridge_ws.pending_requests["expired"] = {"timestamp": old, "code": "1"}
        bridge_ws.pending_requests["fresh"] = {"timestamp": now, "code": "2"}
        bridge_ws.completed_requests["expired-done"] = {"timestamp": old}

        bridge_ws.cleanup_old_requests()

        assert "expired" not in bridge_ws.pending_requests
        assert "fresh" in bridge_ws.pending_requests
        assert "expired-done" not in bridge_ws.completed_requests


class TestQueueHelpers:
    """get_queue_stats / clear_queue over module state."""

    def test_stats_reflect_pending_and_completed(self):
        now = time.time()
        bridge_ws.pending_requests["a"] = {"timestamp": now - 5, "type": "execute"}
        bridge_ws.completed_requests["b"] = {"timestamp": now}

        stats = bridge_ws.get_queue_stats()

        assert stats["pending_count"] == 1
        assert stats["completed_count"] == 1
        assert stats["pending_requests"][0]["request_id"] == "a"
        assert stats["oldest_pending_age"] >= 4

    def test_clear_queue_wakes_waiters_and_clears(self):
        import asyncio

        now = time.time()
        bridge_ws.pending_requests["a"] = {"timestamp": now - 10}
        event = asyncio.Event()
        bridge_ws.pending_events["a"] = event

        result = bridge_ws.clear_queue()

        assert result["cleared"] == 1
        assert not bridge_ws.pending_requests
        assert event.is_set()

    def test_clear_queue_older_than_filters(self):
        now = time.time()
        bridge_ws.pending_requests["old"] = {"timestamp": now - 100}
        bridge_ws.pending_requests["new"] = {"timestamp": now}

        result = bridge_ws.clear_queue(older_than=50)

        assert result["cleared"] == 1
        assert "new" in bridge_ws.pending_requests
        assert "old" not in bridge_ws.pending_requests


class TestResolveInstance:
    """resolve_instance: id, alias, numeric index, and misses.

    WebSocket connections are stand-in objects — resolve_instance only uses
    them as dict keys / set members.
    """

    class FakeWS:
        pass

    def _connect(self, instance_id: str) -> "TestResolveInstance.FakeWS":
        ws = self.FakeWS()
        bridge_ws.active_connections.add(ws)
        bridge_ws.instance_ids[instance_id] = ws
        bridge_ws.browser_info[ws] = {
            "userAgent": "Mozilla/5.0 (Macintosh) Chrome/120.0",
            "extensionVersion": "1.0.0",
        }
        bridge_ws.connection_times[ws] = time.time()
        return ws

    def test_empty_identifier_returns_none(self):
        assert bridge_ws.resolve_instance("") is None
        assert bridge_ws.resolve_instance(None) is None

    def test_resolve_by_instance_id(self):
        ws = self._connect("b7x2")
        assert bridge_ws.resolve_instance("b7x2") is ws

    def test_resolve_by_alias(self):
        ws = self._connect("b7x2")
        bridge_ws.instance_aliases["homepage"] = "b7x2"
        assert bridge_ws.resolve_instance("homepage") is ws

    def test_resolve_by_numeric_index(self):
        ws = self._connect("b7x2")
        assert bridge_ws.resolve_instance("0") is ws

    def test_disconnected_instance_not_resolved(self):
        ws = self._connect("b7x2")
        bridge_ws.active_connections.discard(ws)
        assert bridge_ws.resolve_instance("b7x2") is None

    def test_unknown_identifier_returns_none(self):
        assert bridge_ws.resolve_instance("nope") is None
        assert bridge_ws.resolve_instance("99") is None
