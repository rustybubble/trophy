"""Ask the ref over the live 3D track (agent-3-droid-realtime §5): a judge's question is routed, by keyword rules, to
the matching check(s) in the session's library, the check runs on the stored track, and Claude phrases the result.
Claude never computes geometry; without a matching check the service answers "give me a moment" and queues a
pending check for the Droid. Requires ``ANTHROPIC_API_KEY``: there is no template or offline answer."""

from .phrase import AskConfigError, AskUpstreamError, Phraser
from .router import CheckCall, Query, route
from .service import make_app, serve
from .store import TrackStore

__all__ = [
    "AskConfigError",
    "AskUpstreamError",
    "CheckCall",
    "Phraser",
    "Query",
    "TrackStore",
    "make_app",
    "route",
    "serve",
]
