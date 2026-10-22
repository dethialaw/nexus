"""Subscriptions of a User to Sources, managed by `nexus-admin`."""

from dataclasses import dataclass

from nexus.core.ingestion.entities import Source
from nexus.core.ingestion.ports import SubscriptionUnitOfWork
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
