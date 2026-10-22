"""Profile: users, Interests and their journal, relevance scores and Signals."""

from dataclasses import dataclass
from enum import StrEnum


class ChangeType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class InterestOrigin(StrEnum):
    DIRECT = "direct"
    ONBOARDING = "onboarding"
    NOT_INTERESTED = "not_interested"


class SignalKind(StrEnum):
    OPENED = "opened"
    NOT_INTERESTED = "not_interested"


@dataclass(frozen=True, slots=True)
class User:
    id: int
    handle: str
    timezone: str
    briefing_hour: int
