"""Synchronisation of the Source Catalog at the start of an Execution."""

from pydantic import ValidationError

from nexus.core.ingestion.entities import Anomaly, AnomalyKind
from nexus.core.ingestion.ports import IngestionUnitOfWork, SourceCatalogReader
from nexus.core.ingestion.source_catalog import (
    CatalogSyncPlan,
    SourceCatalog,
    UnreadableCatalogError,
    sync_source_catalog,
)


async def synchronize_source_catalog(
    uow: IngestionUnitOfWork, reader: SourceCatalogReader
) -> CatalogSyncPlan:
    """Apply the catalog to the common Sources; a blocked plan writes nothing."""
    try:
        raw = reader.read()
    except UnreadableCatalogError as error:
        return CatalogSyncPlan(
            anomaly=Anomaly(AnomalyKind.CATALOG_SYNC_BLOCKED, f"unreadable catalog: {error}")
        )
    try:
        catalog = SourceCatalog.from_raw(raw)
    except ValidationError as error:
        return CatalogSyncPlan(
            anomaly=Anomaly(AnomalyKind.CATALOG_SYNC_BLOCKED, _invalid_catalog_detail(error))
        )
    async with uow:
        plan = sync_source_catalog(catalog, await uow.sources.list_common())
        if plan.anomaly is None:
            await uow.sources.apply_catalog_sync(plan)
            await uow.commit()
    return plan


def _invalid_catalog_detail(error: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(map(str, item['loc']))}: {item['msg']} (got {item['input']!r:.80})"
        for item in error.errors(include_url=False)
    )
    return f"invalid catalog: {problems}"
