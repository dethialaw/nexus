"""ORM layer of the snapshot and append-only guards (ADR-0005).

The database trigger is the last layer; these listeners fail earlier, with a clear error.
"""

from typing import Any

from sqlalchemy import event, inspect
from sqlalchemy.orm import Mapper, ORMExecuteState, Session

from nexus.adapters.persistence.models import (
    BriefingCompositionRow,
    BriefingRow,
    CitationRow,
    EntryRow,
    InterestVersionRow,
    MessageRow,
    RelevanceScoreRow,
    SameEventJudgmentRow,
    SignalRow,
)
from nexus.core.delivery.entities import BriefingStatus

GUARDED_MODELS: tuple[type[Any], ...] = (
    EntryRow,
    CitationRow,
    BriefingRow,
    BriefingCompositionRow,
    InterestVersionRow,
    MessageRow,
    SignalRow,
    SameEventJudgmentRow,
    RelevanceScoreRow,
)
GUARDED_TABLES = frozenset(model.__tablename__ for model in GUARDED_MODELS)


class SnapshotUpdateError(RuntimeError):
    """An UPDATE was attempted on a snapshot or append-only table."""


def _refuse_update(mapper: Mapper[Any], connection: Any, target: Any) -> None:
    if isinstance(target, BriefingRow) and _committed_status(target) == BriefingStatus.FAILED:
        return
    raise SnapshotUpdateError(f"{target.__tablename__} rows are never updated")


def _committed_status(briefing: BriefingRow) -> str:
    history = inspect(briefing).attrs.status.history
    return str(history.deleted[0]) if history.deleted else briefing.status


for _model in GUARDED_MODELS:
    event.listen(_model, "before_update", _refuse_update)


class GuardedSession(Session):
    """Session refusing bulk `UPDATE` statements on guarded tables, `briefing` included:
    a failed Briefing is replaced through the unit of work, where `before_update` checks it."""


@event.listens_for(GuardedSession, "do_orm_execute")
def _refuse_bulk_update(state: ORMExecuteState) -> None:
    if not state.is_update:
        return
    table = getattr(state.statement, "table", None)
    name = getattr(table, "name", None)
    if name in GUARDED_TABLES:
        raise SnapshotUpdateError(f"bulk UPDATE refused on {name}")
