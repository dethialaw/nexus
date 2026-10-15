"""Source Catalog and its synchronisation with the common Sources.

The rules are listed in `docs/specs/0001-squelette-du-monorepo.md` (Catalogue de Sources).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from nexus.core.ingestion.entities import Anomaly, AnomalyKind, DeactivationReason, Source
from nexus.core.ingestion.source_config import SourceConfig

MIN_BLOCKING_DISAPPEARANCES = 3
BLOCKING_DISAPPEARANCE_RATIO = 0.2


class CatalogEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    config: SourceConfig

    @property
    def source_key(self) -> str:
        return self.config.source_key


class SourceCatalog(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sources: tuple[CatalogEntry, ...]
    retired: tuple[str, ...]

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        listed = [entry.source_key for entry in self.sources]
        duplicates = {key for key in listed if listed.count(key) > 1}
        duplicates |= {key for key in self.retired if self.retired.count(key) > 1}
        if duplicates:
            raise ValueError(f"duplicated source_key: {sorted(duplicates)}")
        both = set(listed) & set(self.retired)
        if both:
            raise ValueError(f"source_key both listed and retired: {sorted(both)}")
        return self


@dataclass(frozen=True, slots=True)
class CatalogSyncPlan:
    """What the repository applies. Empty, with an anomaly, when the sync is blocked."""

    to_insert: tuple[CatalogEntry, ...] = ()
    to_deactivate: tuple[str, ...] = ()
    to_reactivate: tuple[str, ...] = ()
    anomaly: Anomaly | None = None


def sync_source_catalog(catalog: SourceCatalog, sources: Iterable[Source]) -> CatalogSyncPlan:
    """Plan the upsert of the catalog onto the common Sources; private Sources are ignored."""
    common = {source.source_key: source for source in sources if source.is_common}
    active = {key for key, source in common.items() if source.is_active}
    listed = {entry.source_key for entry in catalog.sources}
    retired = set(catalog.retired)

    disappeared = sorted(active - listed - retired)
    threshold = max(MIN_BLOCKING_DISAPPEARANCES, BLOCKING_DISAPPEARANCE_RATIO * len(active))
    if not catalog.sources or len(disappeared) > threshold:
        detail = (
            "catalog has no [[source]]"
            if not catalog.sources
            else f"{len(disappeared)} active common Sources missing from the catalog: "
            + ", ".join(disappeared)
        )
        return CatalogSyncPlan(anomaly=Anomaly(AnomalyKind.CATALOG_SYNC_BLOCKED, detail))

    return CatalogSyncPlan(
        to_insert=tuple(entry for entry in catalog.sources if entry.source_key not in common),
        to_deactivate=tuple(sorted((active & retired) | set(disappeared))),
        to_reactivate=tuple(
            sorted(
                key
                for key in listed & common.keys()
                if common[key].deactivation_reason is DeactivationReason.REMOVED_FROM_CATALOG
            )
        ),
    )
