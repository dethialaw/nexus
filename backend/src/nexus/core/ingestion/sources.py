"""Sources managed by `nexus-admin`."""

from nexus.core.ingestion.ports import SourceUnitOfWork
from nexus.core.ingestion.subscriptions import UnknownSourceError


async def reactivate_source(uow: SourceUnitOfWork, source_key: str) -> bool:
    """Put a Source back in collection; idempotent. False when it was already active."""
    async with uow:
        source = await uow.sources.get_by_key(source_key)
        if source is None:
            raise UnknownSourceError(f"no Source with source_key {source_key!r}")
        changed = await uow.sources.reactivate(source.id)
        await uow.commit()
    return changed
