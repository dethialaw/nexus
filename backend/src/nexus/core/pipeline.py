"""Chaining of one Execution.

The skeleton only opens and closes it; catalog sync, Collections and Compositions come next.
"""

from collections.abc import Callable

from nexus.core.ingestion.entities import Execution, ExecutionResult
from nexus.core.ingestion.ports import IngestionUnitOfWork
from nexus.core.ingestion.services import close_execution, open_execution
from nexus.core.shared.ports import Clock


async def run_execution(uow_factory: Callable[[], IngestionUnitOfWork], clock: Clock) -> Execution:
    execution = await open_execution(uow_factory(), clock)
    return await close_execution(uow_factory(), clock, execution, ExecutionResult.SUCCESS)
