"""Ports shared by every core section."""

from datetime import datetime
from types import TracebackType
from typing import Protocol, Self


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
