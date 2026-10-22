"""Users."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.adapters.persistence.models import AppUserRow
from nexus.core.profile.entities import User


def user_to_domain(row: AppUserRow) -> User:
    return User(
        id=row.id, handle=row.handle, timezone=row.timezone, briefing_hour=row.briefing_hour
    )


class SqlUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self, handle: str, timezone: str, briefing_hour: int, *, created_at: datetime
    ) -> User:
        statement = (
            insert(AppUserRow)
            .values(
                handle=handle, timezone=timezone, briefing_hour=briefing_hour, created_at=created_at
            )
            .on_conflict_do_update(
                index_elements=[AppUserRow.handle],
                set_={"timezone": timezone, "briefing_hour": briefing_hour},
            )
            .returning(AppUserRow)
        )
        row = (await self._session.scalars(statement)).one()
        return user_to_domain(row)

    async def get_by_handle(self, handle: str) -> User | None:
        row = await self._session.scalar(select(AppUserRow).where(AppUserRow.handle == handle))
        return None if row is None else user_to_domain(row)
