"""`nexus-batch`: runs one Execution."""

import asyncio
import logging
import os
import sys
from pyexpat import EXPAT_VERSION

from nexus.bootstrap import Container, build_container
from nexus.core.ingestion.entities import AnomalyKind, ExecutionResult
from nexus.core.pipeline import ExecutionReport, run_execution

logger = logging.getLogger("nexus.batch")


def exit_code(report: ExecutionReport) -> int:
    """Non-zero when the maintainer must be alerted; `partial`, `feed_moved` and
    `no_source_to_collect` stay at 0."""
    execution = report.execution
    kinds = {anomaly.kind for anomaly in execution.anomalies}
    alerting = {AnomalyKind.CATALOG_SYNC_BLOCKED, AnomalyKind.SOURCE_DEACTIVATED}
    return 1 if execution.result is ExecutionResult.FAILED or kinds & alerting else 0


def render_summary(report: ExecutionReport) -> str:
    execution = report.execution
    lines = [
        f"## Execution {execution.id}: {execution.result}",
        "",
        f"expat version: {EXPAT_VERSION}",
    ]
    if execution.error_detail:
        lines.append(f"Error: {execution.error_detail}")
    lines += ["", "### Collections", ""]
    if not report.collections:
        lines.append("None.")
    for outcome in report.collections:
        collection = outcome.collection
        line = (
            f"- source {collection.source_id}: {collection.result}, "
            f"{collection.article_count} new Articles, "
            f"{outcome.unreadable_count} unreadable items, "
            f"{outcome.excluded_count} excluded items"
        )
        if collection.error_detail:
            line += f", error: {collection.error_detail}"
        lines.append(line)
    lines += ["", "### Anomalies", ""]
    if not execution.anomalies:
        lines.append("None.")
    lines += [f"- {anomaly.kind}: {anomaly.detail}" for anomaly in execution.anomalies]
    lines += ["", "### Catalog sync: configs updated", ""]
    if not report.updated_source_keys:
        lines.append("None.")
    lines += [f"- {source_key}" for source_key in report.updated_source_keys]
    return "\n".join(lines) + "\n"


def write_summary(summary: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as file:
            file.write(summary)
    else:
        logger.info("\n%s", summary)


async def run(container: Container | None = None) -> int:
    container = container or build_container()
    try:
        report = await run_execution(
            container.uow_factory, container.clock, container.source_catalog, container.connectors
        )
    finally:
        await container.dispose()
    write_summary(render_summary(report))
    return exit_code(report)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    sys.exit(asyncio.run(run()))


if __name__ == "__main__":
    main()
