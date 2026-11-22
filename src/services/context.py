"""Transport-independent request identity passed into application services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Trusted request metadata assembled by a delivery adapter.

    Authentication is introduced in Iteration 0.21. Until then ``user_id`` is
    deliberately ``None`` and no service may use a fallback user.
    """

    request_id: str
    user_id: int | None = None
    username: str = ""
    roles: tuple[str, ...] = ()
    idempotency_key: str | None = None
