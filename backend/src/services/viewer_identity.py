"""
Who counts as one viewer.

A view is a unique viewer, not a page load, so every visit has to resolve
to a stable identity before it can be recorded. There are three, in
descending order of how much we trust them:

1. the signed-in user;
2. an id the browser keeps for itself and sends back on each visit;
3. failing both, a hash of the caller's address and user agent.

The third is a fallback, not an identity: everyone behind one NAT with the
same browser build collapses into a single viewer, which undercounts
rather than inflates. That is the safer direction for a number people read
as "how many watched this".

The address comes from the gateway, which is the only party that can know
it. The application does not try to work it out of X-Forwarded-For.
"""

import hashlib
from uuid import UUID

from fastapi import Request

#: Sent by the SPA; see frontend/src/lib/visitorId.ts.
VISITOR_HEADER = "X-Visitor-Id"

#: Written by the gateway, never by the caller. See gateway/nginx.conf.
REAL_IP_HEADER = "X-Real-IP"

_MAX_VISITOR_ID = 64


def viewer_key(request: Request, user_id: UUID | None) -> str:
    """A stable identity for whoever is making this request."""
    if user_id is not None:
        return f"user:{user_id}"

    visitor = (request.headers.get(VISITOR_HEADER) or "").strip()
    if visitor:
        # Length-capped and hashed rather than stored raw: it is client
        # input on its way into an indexed column.
        return "anon:" + _digest(visitor[:_MAX_VISITOR_ID])

    return "fp:" + _digest(
        f"{_client_ip(request)}|{request.headers.get('user-agent', '')}"
    )


def _client_ip(request: Request) -> str:
    """The caller's address, as decided at the edge.

    X-Forwarded-For is deliberately not parsed here. It is a list the
    client writes the first entry of, and working out which entries are
    ours means knowing the proxy topology -- in the application, where it
    would silently be wrong the day a proxy is added or removed. Taking
    the last hop is not a fix either: that is our own edge's address, and
    it would merge every visitor into one.

    The gateway settles it instead. nginx resolves the real client (from
    Caddy's X-Real-IP in the public deployment, from the connection
    itself when nothing is in front of it) and overwrites X-Real-IP with
    the answer on the way here, so this header cannot be supplied by a
    caller. See gateway/nginx.conf and gateway/prod-realip.conf.
    """
    real_ip = (request.headers.get(REAL_IP_HEADER) or "").strip()
    if real_ip:
        return real_ip
    # No gateway in front at all -- a direct call, e.g. in tests.
    return request.client.host if request.client else "unknown"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
