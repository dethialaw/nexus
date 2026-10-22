"""Services of the profile section."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from nexus.core.profile.entities import User
from nexus.core.profile.ports import ProfileUnitOfWork
from nexus.core.shared.errors import NexusError
from nexus.core.shared.ports import Clock

# A non-personal identifier: an e-mail address never fits.
HANDLE_PATTERN = re.compile(r"[a-z0-9_-]{3,32}")


class InvalidUserError(NexusError):
    """A User value is refused before reaching the database."""


async def upsert_user(
    uow: ProfileUnitOfWork, clock: Clock, handle: str, timezone: str, briefing_hour: int
) -> User:
    """Create the User, or update its timezone and Briefing hour; idempotent."""
    if not HANDLE_PATTERN.fullmatch(handle):
        raise InvalidUserError(f"handle must match {HANDLE_PATTERN.pattern}: {handle!r}")
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise InvalidUserError(f"timezone is not an IANA name: {timezone!r}") from error
    if not 0 <= briefing_hour <= 23:
        raise InvalidUserError(f"briefing hour must be between 0 and 23: {briefing_hour}")
    async with uow:
        user = await uow.users.upsert(handle, timezone, briefing_hour, created_at=clock.now())
        await uow.commit()
    return user
