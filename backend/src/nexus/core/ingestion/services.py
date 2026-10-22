"""Services of the ingestion section."""

from dataclasses import dataclass, replace

from pydantic import ValidationError

from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    Execution,
    ExecutionResult,
    FailureCause,
    Source,
)
from nexus.core.ingestion.ports import (
    IngestionUnitOfWork,
    SourceCatalogReader,
    SubscriptionUnitOfWork,
)
from nexus.core.ingestion.source_catalog import (
    CatalogSyncPlan,
    SourceCatalog,
    UnreadableCatalogError,
    sync_source_catalog,
)
from nexus.core.profile.entities import User
from nexus.core.shared.errors import NexusError
from nexus.core.shared.ports import Clock


class UnknownUserError(NexusError):
    """No User has this handle."""


class UnknownSourceError(NexusError):
    """No Source has this `source_key`."""


@dataclass(frozen=True, slots=True)
class SubscriptionChange:
    source: Source
    changed: bool
    """False when the command found the Subscription already in the wanted state."""


async def open_execution(uow: IngestionUnitOfWork, clock: Clock) -> Execution:
    async with uow:
        execution = await uow.executions.open(started_at=clock.now())
        await uow.commit()
    return execution


async def close_execution(
    uow: IngestionUnitOfWork,
    clock: Clock,
    execution: Execution,
    result: ExecutionResult,
    *,
    failure_cause: FailureCause | None = None,
    error_detail: str | None = None,
    anomalies: tuple[Anomaly, ...] = (),
) -> Execution:
    if (result is ExecutionResult.FAILED) != (failure_cause is not None):
        raise ValueError("a failure cause is given if and only if the Execution failed")
    closed = replace(
        execution,
        finished_at=clock.now(),
        result=result,
        failure_cause=failure_cause,
        error_detail=error_detail,
        anomalies=execution.anomalies + anomalies,
    )
    async with uow:
        await uow.executions.close(closed)
        await uow.commit()
    return closed


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


async def subscribe(
    uow: SubscriptionUnitOfWork, clock: Clock, handle: str, source_key: str
) -> SubscriptionChange:
    """Subscribe a User to a Source, inactive ones included; idempotent."""
    async with uow:
        user, source = await _user_and_source(uow, handle, source_key)
        added = await uow.subscriptions.add(user.id, source.id, created_at=clock.now())
        await uow.commit()
    return SubscriptionChange(source=source, changed=added)


async def unsubscribe(
    uow: SubscriptionUnitOfWork, handle: str, source_key: str
) -> SubscriptionChange:
    """Remove a Subscription; idempotent. An unknown key is refused, as a likely typo."""
    async with uow:
        user, source = await _user_and_source(uow, handle, source_key)
        removed = await uow.subscriptions.remove(user.id, source.id)
        await uow.commit()
    return SubscriptionChange(source=source, changed=removed)


async def _user_and_source(
    uow: SubscriptionUnitOfWork, handle: str, source_key: str
) -> tuple[User, Source]:
    user = await uow.users.get_by_handle(handle)
    if user is None:
        raise UnknownUserError(f"no User with handle {handle!r}")
    source = await uow.sources.get_by_key(source_key)
    if source is None:
        raise UnknownSourceError(f"no Source with source_key {source_key!r}")
    return user, source
