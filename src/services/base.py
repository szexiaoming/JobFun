"""Minimal interface implemented by use-case-level application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from src.services.context import RequestContext


@runtime_checkable
class ApplicationService(Protocol):
    """Common contract for services invoked by Streamlit or HTTP adapters."""

    @property
    def context(self) -> RequestContext:
        """Return the trusted request context for this service invocation."""
        ...


@dataclass(frozen=True)
class BaseApplicationService:
    """Convenience base for services that only need request context initially."""

    context: RequestContext
