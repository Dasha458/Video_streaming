"""
Who counts as one viewer.

A view is a unique viewer, so this function decides the number people read
as "how many watched this".
"""

import uuid

from starlette.requests import Request

from src.services.viewer_identity import VISITOR_HEADER, viewer_key


def _Request(
    headers: dict | None = None, client_host: str | None = "1.2.3.4"
) -> Request:
    """A real Request built from a minimal ASGI scope."""
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
        ],
    }
    if client_host:
        scope["client"] = (client_host, 12345)
    return Request(scope)


class TestSignedIn:
    def test_the_account_identifies_the_viewer(self):
        user_id = uuid.uuid4()
        assert viewer_key(_Request(), user_id) == f"user:{user_id}"

    def test_the_account_wins_over_anything_the_browser_sends(self):
        user_id = uuid.uuid4()
        request = _Request({VISITOR_HEADER: "someone-elses-id"})
        assert viewer_key(request, user_id) == f"user:{user_id}"


class TestSignedOut:
    def test_the_browser_id_identifies_the_viewer(self):
        a = viewer_key(_Request({VISITOR_HEADER: "abc"}), None)
        b = viewer_key(_Request({VISITOR_HEADER: "abc"}), None)
        assert a == b
        assert a.startswith("anon:")
        # Hashed, not stored as sent: it is client input on its way into an
        # indexed column.
        assert "abc" not in a

    def test_different_browsers_are_different_viewers(self):
        a = viewer_key(_Request({VISITOR_HEADER: "abc"}), None)
        b = viewer_key(_Request({VISITOR_HEADER: "xyz"}), None)
        assert a != b

    def test_an_empty_header_is_no_header(self):
        assert viewer_key(_Request({VISITOR_HEADER: "   "}), None).startswith("fp:")

    def test_a_long_id_cannot_overflow_the_column(self):
        key = viewer_key(_Request({VISITOR_HEADER: "x" * 5000}), None)
        assert len(key) <= 80


class TestFallback:
    def test_address_and_agent_stand_in_for_an_id(self):
        headers = {"user-agent": "Mozilla/5.0"}
        a = viewer_key(_Request(headers), None)
        b = viewer_key(_Request(headers), None)
        assert a == b
        assert a.startswith("fp:")

    def test_a_different_agent_at_the_same_address_is_a_different_viewer(self):
        a = viewer_key(_Request({"user-agent": "Firefox"}), None)
        b = viewer_key(_Request({"user-agent": "Safari"}), None)
        assert a != b

    def test_the_address_is_the_one_the_gateway_saw(self):
        """X-Forwarded-For accumulates left to right.

        Only the entries our own proxies appended can be trusted; the
        first is whatever the client chose to send, so a caller could
        otherwise mint a new viewer per request and inflate the count.
        """
        spoofed = _Request(
            {"x-forwarded-for": "9.9.9.9, 203.0.113.7", "user-agent": "UA"}
        )
        honest = _Request({"x-forwarded-for": "203.0.113.7", "user-agent": "UA"})
        assert viewer_key(spoofed, None) == viewer_key(honest, None)

    def test_a_request_with_no_client_still_resolves(self):
        assert viewer_key(_Request({}, client_host=None), None).startswith("fp:")
