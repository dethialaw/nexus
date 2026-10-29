"""Sources managed by `nexus-admin`."""

from nexus.core.ingestion.ports import SourceUnitOfWork
from nexus.core.ingestion.subscriptions import UnknownSourceError
from nexus.core.shared.ports import Clock


async def reactivate_source(uow: SourceUnitOfWork, clock: Clock, source_key: str) -> bool:
    """Put a Source back in collection, its failure count starting over; idempotent.

    False when it was already active.
    """
    async with uow:
        source = await uow.sources.get_by_key(source_key)
        if source is None:
            raise UnknownSourceError(f"no Source with source_key {source_key!r}")
        changed = await uow.sources.reactivate(source.id, clock.now())
        await uow.commit()
    return changed
