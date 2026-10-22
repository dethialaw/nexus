"""Ports shared by every core section."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import TracebackType
from typing import Protocol, Self

from nexus.core.shared.errors import NexusError


class Clock(Protocol):
    def now(self) -> datetime:
        """Return the current time, timezone-aware, in UTC."""
        ...


class UnitOfWork(Protocol):
    """One transaction. Sections extend it with the repositories they need.

    Leaving the context without `commit()` rolls the transaction back.
    """

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class FetchUsage(StrEnum):
    """Why a page is fetched; the adapter derives its protections from it."""

    FEED = "feed"
    LINKED_PAGE = "linked_page"
    AGENT_PAGE = "agent_page"


@dataclass(frozen=True, slots=True)
class FetchResponse:
    status: int
    body: bytes
    final_url: str


class FetchError(NexusError):
    """The request could not complete: refused URL, network error, timeout, oversized body."""


class HttpFetcher(Protocol):
    """Every HTTP call to a publisher's site (backend/AGENTS.md, Récupération web)."""

    async def fetch(self, url: str, usage: FetchUsage) -> FetchResponse:
        """Raise `FetchError` when no response could be read; any status is returned."""
        ...
