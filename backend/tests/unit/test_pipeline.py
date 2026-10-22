"""Seam 2, catalog side: `run_execution` with in-memory repositories."""

import pytest

from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    DeactivationReason,
    ExecutionResult,
    FailureCause,
)
from nexus.core.ingestion.services import close_execution, open_execution
from nexus.core.ingestion.source_catalog import UnreadableCatalogError
from nexus.core.pipeline import ExecutionReport
from tests.unit.execution_harness import RMC, RMC_KEY, Harness, reddit, rss, stored_rmc
from tests.unit.fakes import FakeClock, InMemoryExecutionRepository, InMemoryUnitOfWork


def blocked(report: ExecutionReport) -> list[Anomaly]:
    return [
        anomaly
        for anomaly in report.execution.anomalies
        if anomaly.kind is AnomalyKind.CATALOG_SYNC_BLOCKED
    ]


async def test_an_execution_is_opened_then_closed_as_success() -> None:
    harness = Harness()

    report = await harness.run()

    execution = report.execution
    assert harness.executions.rows == {execution.id: execution}
    assert execution.result is ExecutionResult.SUCCESS
    assert execution.finished_at is not None
    assert execution.finished_at > execution.started_at


async def test_catalog_sources_are_inserted_as_active_common_sources() -> None:
    harness = Harness()

    await harness.run([reddit("python"), reddit("rust")])

    assert sorted(harness.sources.rows) == ["reddit:python", "reddit:rust"]
    assert all(s.is_active and s.is_common for s in harness.sources.rows.values())


async def test_an_invalid_config_blocks_the_whole_sync_but_not_the_execution() -> None:
    harness = Harness()
    await harness.run([reddit("python")])

    report = await harness.run([reddit("python"), reddit("rust"), reddit("r/bad")])

    assert sorted(harness.sources.rows) == ["reddit:python"]
    assert report.execution.result is ExecutionResult.SUCCESS
    [anomaly] = blocked(report)
    assert "r/bad" in anomaly.detail


async def test_an_unreadable_catalog_blocks_the_sync_but_not_the_execution() -> None:
    harness = Harness()

    report = await harness.run(error=UnreadableCatalogError("line 3: expected '='"))

    assert harness.sources.rows == {}
    assert report.execution.result is ExecutionResult.SUCCESS
    [anomaly] = blocked(report)
    assert "line 3" in anomaly.detail


async def test_a_changed_config_is_updated_and_reported() -> None:
    harness = Harness()
    await harness.run([rss(RMC)])

    report = await harness.run([rss(RMC, exclude_url_patterns=["_DN-"])])

    assert harness.sources.rows[RMC_KEY].config["exclude_url_patterns"] == ["_DN-"]
    assert report.updated_source_keys == (RMC_KEY,)


async def test_an_identical_config_is_not_rewritten_even_in_another_form() -> None:
    harness = Harness(stored_rmc({"feed_url": RMC, "connector": "rss"}))

    report = await harness.run([rss(RMC, exclude_url_patterns=[])])

    assert harness.sources.config_writes == 0
    assert report.updated_source_keys == ()


async def test_an_inactive_source_gets_its_config_without_being_reactivated() -> None:
    harness = Harness(stored_rmc(rss(RMC), DeactivationReason.REPEATED_FAILURES))

    report = await harness.run([rss(RMC, exclude_url_patterns=["_DN-"])])

    source = harness.sources.rows[RMC_KEY]
    assert source.config["exclude_url_patterns"] == ["_DN-"]
    assert source.deactivation_reason is DeactivationReason.REPEATED_FAILURES
    assert report.updated_source_keys == (RMC_KEY,)


async def test_a_sync_blocked_by_the_threshold_updates_no_config() -> None:
    harness = Harness(stored_rmc(rss(RMC)))
    await harness.run([rss(RMC), *(reddit(f"s{i}") for i in range(4))])

    report = await harness.run([rss(RMC, exclude_url_patterns=["_DN-"])])

    assert blocked(report)
    assert report.updated_source_keys == ()
    assert "exclude_url_patterns" not in harness.sources.rows[RMC_KEY].config


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
