"""
Who is calling, as far as the address goes.

One place, because more than one thing is keyed on it -- unique views and
the per-endpoint rate limits -- and two copies of a rule like this drift
into two different answers.

``request.client.host`` is not that answer. Behind the gateway it is the
gateway's own container address, so everything keyed on it collapses into
a single caller: every visitor counted as one viewer, every user sharing
one rate-limit bucket.

X-Forwarded-For is not the answer either. It is a list whose first entry
the client writes, and whose last entry is our own edge; picking the
right one means knowing the proxy topology here, in the one place that
cannot see it.

The gateway settles it. nginx resolves the real client -- from Caddy's
X-Real-IP in the public deployment, from the connection itself when
nothing sits in front of it -- and overwrites X-Real-IP on the way
through, so a caller cannot supply it. See gateway/nginx.conf and
gateway/prod-realip.conf.
"""

from fastapi import Request

#: Written by the gateway, never by the caller.
REAL_IP_HEADER = "X-Real-IP"


def client_ip(request: Request) -> str:
    """The caller's address as the gateway resolved it."""
    real_ip = (request.headers.get(REAL_IP_HEADER) or "").strip()
    if real_ip:
        return real_ip
    # No gateway in front at all -- a direct call, or a test client.
    return request.client.host if request.client else "unknown"
