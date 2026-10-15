"""Profile: users, Interests and their journal, relevance scores and Signals."""

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
