from dataclasses import replace
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nexus.adapters.persistence.models import ExecutionRow
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
