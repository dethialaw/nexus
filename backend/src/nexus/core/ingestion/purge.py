"""Purge: the retention windows of Articles, Purge traces and Executions."""

from datetime import timedelta

from nexus.core.ingestion.normalization import RETENTION_WINDOW
from nexus.core.ingestion.ports import IngestionUnitOfWork
from nexus.core.shared.ports import Clock

PURGE_TRACE_RETENTION = timedelta(days=365)
EXECUTION_RETENTION = timedelta(days=90)


async def purge_expired(uow: IngestionUnitOfWork, clock: Clock) -> None:
    """One transaction: expired Articles become Purge traces, old traces and Executions go."""
    now = clock.now()
    async with uow:
        await uow.articles.purge_collected_before(now - RETENTION_WINDOW, now)
        await uow.purge_traces.delete_purged_before(now - PURGE_TRACE_RETENTION)
        await uow.executions.delete_started_before(now - EXECUTION_RETENTION)
        await uow.commit()
