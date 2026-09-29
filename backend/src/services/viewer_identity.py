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

The address comes from :mod:`src.core.client_address`, which is also what
the rate limits are keyed on -- the same rule, decided once.
"""

import hashlib
from uuid import UUID

from fastapi import Request

from src.core.client_address import client_ip

#: Sent by the SPA; see frontend/src/lib/visitorId.ts.
VISITOR_HEADER = "X-Visitor-Id"

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
        f"{client_ip(request)}|{request.headers.get('user-agent', '')}"
    )


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:40]
