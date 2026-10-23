"""SQL implementation of the `UnitOfWork` ports: one session, one transaction."""

from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.repositories.article import SqlArticleRepository
from nexus.adapters.persistence.repositories.collection import SqlCollectionRepository
from nexus.adapters.persistence.repositories.execution import SqlExecutionRepository
from nexus.adapters.persistence.repositories.purge_trace import SqlPurgeTraceRepository
from nexus.adapters.persistence.repositories.source import SqlSourceRepository
from nexus.adapters.persistence.repositories.subscription import SqlSubscriptionRepository
from nexus.adapters.persistence.repositories.user import SqlUserRepository


class SqlUnitOfWork:
    articles: SqlArticleRepository
    collections: SqlCollectionRepository
    executions: SqlExecutionRepository
    purge_traces: SqlPurgeTraceRepository
    sources: SqlSourceRepository
    subscriptions: SqlSubscriptionRepository
    users: SqlUserRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        await self._session.begin()
        self.articles = SqlArticleRepository(self._session)
        self.collections = SqlCollectionRepository(self._session)
        self.executions = SqlExecutionRepository(self._session)
        self.purge_traces = SqlPurgeTraceRepository(self._session)
        self.sources = SqlSourceRepository(self._session)
        self.subscriptions = SqlSubscriptionRepository(self._session)
        self.users = SqlUserRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            if session.in_transaction():
                await session.rollback()
        finally:
            await session.close()
            self._session = None

    async def commit(self) -> None:
        await self._require_session().commit()

    def _require_session(self) -> AsyncSession:
        if self._session is None:
            raise RuntimeError("unit of work used outside of `async with`")
        return self._session
