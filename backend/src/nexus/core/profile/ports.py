"""Ports of the profile section."""

from datetime import datetime
from typing import Protocol

from nexus.core.profile.entities import User
from nexus.core.shared.ports import UnitOfWork


class UserRepository(Protocol):
    async def upsert(
        self, handle: str, timezone: str, briefing_hour: int, *, created_at: datetime
    ) -> User:
        """Create the User, or update its timezone and Briefing hour if the handle exists."""
        ...

    async def get_by_handle(self, handle: str) -> User | None: ...


class ProfileUnitOfWork(UnitOfWork, Protocol):
    @property
    def users(self) -> UserRepository: ...
