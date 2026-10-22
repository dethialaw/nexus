"""`nexus-batch` entry point: exit codes and summary."""

from datetime import UTC, datetime
from pathlib import Path
from pyexpat import EXPAT_VERSION
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.core.ingestion.collection import CollectionOutcome
from nexus.core.ingestion.entities import (
    Anomaly,
    AnomalyKind,
    CollectionResult,
    Execution,
    ExecutionResult,
    SourceCollection,
)
from nexus.core.pipeline import ExecutionReport
from nexus.entrypoints.batch import __main__ as batch

NOW = datetime(2026, 10, 22, tzinfo=UTC)


def report(
    result: ExecutionResult, *kinds: str, collections: tuple[CollectionOutcome, ...] = ()
) -> ExecutionReport:
    anomalies = tuple(Anomaly(AnomalyKind(kind), f"detail of {kind}") for kind in kinds)
    return ExecutionReport(
        execution=Execution(1, NOW, NOW, result, anomalies=anomalies),
        updated_source_keys=("rss:example.org/feed",),
        collections=collections,
    )


class FakeContainer(SimpleNamespace):
    async def dispose(self) -> None:
        self.disposed = True


async def run_batch(monkeypatch: pytest.MonkeyPatch, fixed: ExecutionReport) -> int:
    async def fake_run_execution(*_: Any) -> ExecutionReport:
        return fixed

    monkeypatch.setattr(batch, "run_execution", fake_run_execution)
    container = FakeContainer(uow_factory=None, clock=None, source_catalog=None, connectors={})
    code = await batch.run(container)  # type: ignore[arg-type]
    assert container.disposed
    return code


@pytest.mark.parametrize(
    ("result", "kinds", "expected"),
    [
        (ExecutionResult.SUCCESS, (), 0),
        (ExecutionResult.PARTIAL, (), 0),
        (ExecutionResult.SUCCESS, ("no_source_to_collect",), 0),
        (ExecutionResult.SUCCESS, ("feed_moved",), 0),
        (ExecutionResult.FAILED, (), 1),
        (ExecutionResult.SUCCESS, ("catalog_sync_blocked",), 1),
        (ExecutionResult.PARTIAL, ("source_deactivated",), 1),
    ],
)
async def test_exit_code(
    monkeypatch: pytest.MonkeyPatch,
    result: ExecutionResult,
    kinds: tuple[str, ...],
    expected: int,
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert await run_batch(monkeypatch, report(result, *kinds)) == expected


async def test_summary_goes_to_the_step_summary_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    collection = SourceCollection(1, 7, CollectionResult.FAILED, 0, "boom", NOW, NOW)
    fixed = report(
        ExecutionResult.FAILED,
        "feed_moved",
        collections=(CollectionOutcome(collection, unreadable_count=2, excluded_count=3),),
    )

    await run_batch(monkeypatch, fixed)

    text = target.read_text()
    assert "failed" in text
    assert "source 7" in text
    assert "0 new Articles, 2 unreadable items, 3 excluded items, error: boom" in text
    assert "feed_moved: detail of feed_moved" in text
    assert "rss:example.org/feed" in text
    assert f"expat version: {EXPAT_VERSION}" in text


async def test_summary_goes_to_the_log_without_step_summary(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    caplog.set_level("INFO", logger="nexus.batch")

    await run_batch(monkeypatch, report(ExecutionResult.SUCCESS))

    assert EXPAT_VERSION in caplog.text
    assert "Execution 1: success" in caplog.text
