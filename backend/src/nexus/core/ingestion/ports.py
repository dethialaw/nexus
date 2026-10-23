"""Ports of the ingestion section."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from nexus.core.ingestion.entities import (
    Article,
    CollectionResult,
    Execution,
    RawArticleBatch,
    Source,
    SourceCollection,
)
from nexus.core.ingestion.source_catalog import CatalogSyncPlan, RawSourceCatalog
from nexus.core.profile.ports import UserRepository
from nexus.core.shared.ports import HttpValidators, UnitOfWork


class SourceCatalogReader(Protocol):
    def read(self) -> RawSourceCatalog:
        """Read the catalog without validating its blocks.

        Raises `UnreadableCatalogError` when the file cannot be parsed at all.
        """
        ...


class RawArticleReader(Protocol):
    """A Connector: reads one Source into raw Articles."""

    async def read(self, source: Source) -> RawArticleBatch:
        """Raise `CollectionError`, with its cause, when the Collection fails."""
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

    async def list_to_collect(self) -> tuple[Source, ...]:
        """Active Sources with at least one Subscription."""
        ...

    async def mark_collected(
        self, source_id: int, collected_at: datetime, validators: HttpValidators
    ) -> None:
        """Record a successful Collection: the HTTP validators replace the stored ones."""
        ...

    async def deactivate_for_repeated_failures(self, source_id: int) -> bool:
        """Deactivate an active Source (`repeated_failures`); False when already inactive."""
        ...

    async def reactivate(self, source_id: int) -> bool:
        """Reactivate an inactive Source; False when it was already active."""
        ...


class ArticleRepository(Protocol):
    async def insert_new(self, articles: Sequence[Article]) -> int:
        """Insert the Articles not yet known to their Source; return how many were inserted."""
        ...


class CollectionRepository(Protocol):
    async def add(self, collection: SourceCollection) -> None: ...

    async def recent_results(self, source_id: int, limit: int) -> tuple[CollectionResult, ...]:
        """Results of the last Collections of a Source, the most recent first."""
        ...


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

    @property
    def articles(self) -> ArticleRepository: ...

    @property
    def collections(self) -> CollectionRepository: ...


class SourceUnitOfWork(UnitOfWork, Protocol):
    @property
    def sources(self) -> SourceRepository: ...


class SubscriptionUnitOfWork(UnitOfWork, Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def sources(self) -> SourceRepository: ...

    @property
    def subscriptions(self) -> SubscriptionRepository: ...
