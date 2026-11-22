"""Injectable readiness checks without touching user data."""

from __future__ import annotations

from collections.abc import Callable, Mapping


ReadinessProbe = Callable[[], Mapping[str, bool]]


def default_readiness_probe() -> Mapping[str, bool]:
    """Report skeleton configuration readiness only.

    Database and object-storage probes are added with their request-scoped
    adapters; this iteration intentionally avoids opening the global SQLite DB.
    """
    return {"configuration": True}
