"""Ingestion: from Source to Article."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class Connector(StrEnum):
    RSS = "rss"
    HACKERNEWS = "hackernews"
    REDDIT = "reddit"


class DeactivationReason(StrEnum):
    MAINTAINER = "maintainer"
    REPEATED_FAILURES = "repeated_failures"
    REMOVED_FROM_CATALOG = "removed_from_catalog"


class LinkedPageStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    FETCHED = "fetched"
    REUSED = "reused"
    FAILED = "failed"
    TIMEOUT = "timeout"
    TOO_LARGE = "too_large"
    BLOCKED_BY_ROBOTS = "blocked_by_robots"


class ExcerptOrigin(StrEnum):
    SOURCE = "source"
    LINKED_PAGE = "linked_page"
    BOTH = "both"


class ExecutionResult(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class FailureCause(StrEnum):
    TECHNICAL = "technical"
    COLLECTION = "collection"


class CollectionResult(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class AnomalyKind(StrEnum):
    CATALOG_SYNC_BLOCKED = "catalog_sync_blocked"


@dataclass(frozen=True, slots=True)
class Anomaly:
    """A warning recorded on an Execution without making it fail."""

    kind: AnomalyKind
    detail: str


@dataclass(frozen=True, slots=True)
class Source:
    id: int
    source_key: str
    connector: Connector
    config: Mapping[str, Any]
    owner_user_id: int | None
    deactivation_reason: DeactivationReason | None
    last_collected_at: datetime | None

    @property
    def is_active(self) -> bool:
        return self.deactivation_reason is None

    @property
    def is_common(self) -> bool:
        return self.owner_user_id is None


@dataclass(frozen=True, slots=True)
class Execution:
    id: int
    started_at: datetime
    finished_at: datetime | None = None
    result: ExecutionResult | None = None
    failure_cause: FailureCause | None = None
    error_detail: str | None = None
    anomalies: tuple[Anomaly, ...] = field(default=())
