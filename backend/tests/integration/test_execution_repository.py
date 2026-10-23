from dataclasses import replace
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import (
    ExecutionRow,
    SourceCollectionRow,
    SourceRow,
)
from nexus.adapters.persistence.unit_of_work import SqlUnitOfWork
from nexus.core.ingestion.entities import Anomaly, AnomalyKind, ExecutionResult
from tests.integration.seed import NOW


async def test_open_then_close_an_execution(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlUnitOfWork(session_factory) as uow:
        opened = await uow.executions.open(started_at=NOW)
        await uow.commit()

    assert opened.finished_at is None
    assert opened.anomalies == ()

    closed = replace(
        opened,
        finished_at=NOW + timedelta(minutes=1),
        result=ExecutionResult.SUCCESS,
        anomalies=(Anomaly(AnomalyKind.CATALOG_SYNC_BLOCKED, "empty catalog"),),
    )
    async with SqlUnitOfWork(session_factory) as uow:
        await uow.executions.close(closed)
        await uow.commit()

    async with session_factory() as session:
        row = (await session.execute(select(ExecutionRow))).scalar_one()
    assert (row.finished_at, row.result) == (closed.finished_at, "success")
    assert row.anomalies == [{"kind": "catalog_sync_blocked", "detail": "empty catalog"}]


async def test_leaving_without_commit_rolls_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlUnitOfWork(session_factory) as uow:
        await uow.executions.open(started_at=NOW)

    async with session_factory() as session:
        assert (await session.execute(select(ExecutionRow))).first() is None


async def test_delete_started_before_removes_old_executions_with_collections_and_keeps_compositions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        session.add(SourceRow(source_key="rss:a", connector="rss", config={}, is_active=True))
        await session.flush()
        old = ExecutionRow(started_at=NOW - timedelta(days=91), anomalies=[])
        recent = ExecutionRow(started_at=NOW - timedelta(days=89), anomalies=[])
        session.add_all([old, recent])
        await session.flush()
        session.add_all(
            [
                SourceCollectionRow(
                    execution_id=execution.id,
                    source_id=1,
                    result="success",
                    article_count=0,
                    unreadable_count=0,
                    started_at=NOW,
                    finished_at=NOW,
                )
                for execution in (old, recent)
            ]
        )
        await session.commit()

    async with SqlUnitOfWork(session_factory) as uow:
        deleted = await uow.executions.delete_started_before(NOW - timedelta(days=90))
        await uow.commit()

    assert deleted == 1
    async with session_factory() as session:
        assert (await session.scalars(select(ExecutionRow.id))).all() == [2]
        assert (await session.scalars(select(SourceCollectionRow.execution_id))).all() == [2]
