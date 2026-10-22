"""Ports of the ingestion section."""

from datetime import datetime
from typing import Protocol

from nexus.core.ingestion.entities import Execution, Source
from nexus.core.ingestion.source_catalog import CatalogSyncPlan, RawSourceCatalog
from nexus.core.profile.ports import UserRepository
from nexus.core.shared.ports import UnitOfWork


class SourceCatalogReader(Protocol):
    def read(self) -> RawSourceCatalog:
        """Read the catalog without validating its blocks.

        Raises `UnreadableCatalogError` when the file cannot be parsed at all.
        """
        ...


class ExecutionRepository(Protocol):
    async def open(self, started_at: datetime) -> Execution:
        """Insert a new Execution, not finished yet."""
        ...

    async def close(self, execution: Execution) -> None:
        """Record the end of an Execution: `finished_at`, result, cause and anomalies."""
        ...


class SourceRepository(Protocol):
    async def list_common(self) -> tuple[Source, ...]:
        """Every common Source, active or not."""
        ...

    async def apply_catalog_sync(self, plan: CatalogSyncPlan) -> None:
        """Insert, deactivate, reactivate and update the common Sources named by the plan."""
        ...

    async def get_by_key(self, source_key: str) -> Source | None: ...


class SubscriptionRepository(Protocol):
    async def add(self, user_id: int, source_id: int, *, created_at: datetime) -> bool:
        """Subscribe; False when the Subscription already existed."""
        ...

    async def remove(self, user_id: int, source_id: int) -> bool:
        """Unsubscribe; False when there was no Subscription."""
        ...


class IngestionUnitOfWork(UnitOfWork, Protocol):
    @property
    def executions(self) -> ExecutionRepository: ...

    @property
    def sources(self) -> SourceRepository: ...


class SubscriptionUnitOfWork(UnitOfWork, Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def sources(self) -> SourceRepository: ...

    @property
    def subscriptions(self) -> SubscriptionRepository: ...
