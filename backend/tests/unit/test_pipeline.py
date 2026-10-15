import pytest

from nexus.core.ingestion.entities import ExecutionResult, FailureCause
from nexus.core.ingestion.services import close_execution, open_execution
from nexus.core.pipeline import run_execution
from tests.unit.fakes import FakeClock, InMemoryExecutionRepository, InMemoryUnitOfWork


async def test_an_empty_execution_is_opened_then_closed_as_success() -> None:
    repository = InMemoryExecutionRepository()

    execution = await run_execution(lambda: InMemoryUnitOfWork(repository), FakeClock())

    assert repository.rows == {execution.id: execution}
    assert execution.result is ExecutionResult.SUCCESS
    assert execution.finished_at is not None
    assert execution.finished_at > execution.started_at


async def test_a_failure_cause_is_required_exactly_when_the_execution_failed() -> None:
    repository = InMemoryExecutionRepository()
    clock = FakeClock()
    execution = await open_execution(InMemoryUnitOfWork(repository), clock)

    with pytest.raises(ValueError, match="failure cause"):
        await close_execution(
            InMemoryUnitOfWork(repository), clock, execution, ExecutionResult.FAILED
        )
    with pytest.raises(ValueError, match="failure cause"):
        await close_execution(
            InMemoryUnitOfWork(repository),
            clock,
            execution,
            ExecutionResult.SUCCESS,
            failure_cause=FailureCause.TECHNICAL,
        )
