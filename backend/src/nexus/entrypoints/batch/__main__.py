"""`nexus-batch`: runs one Execution."""

import asyncio
import logging

from nexus.bootstrap import Container, build_container
from nexus.core.pipeline import run_execution

logger = logging.getLogger("nexus.batch")


async def run(container: Container | None = None) -> None:
    container = container or build_container()
    try:
        report = await run_execution(
            container.uow_factory, container.clock, container.source_catalog, container.connectors
        )
        execution = report.execution
        logger.info("execution %s finished: %s", execution.id, execution.result)
        for anomaly in execution.anomalies:
            logger.warning("anomaly %s: %s", anomaly.kind, anomaly.detail)
        for collection in report.collections:
            logger.info(
                "collection of source %s: %s, %s new Articles%s",
                collection.source_id,
                collection.result,
                collection.article_count,
                f" ({collection.error_detail})" if collection.error_detail else "",
            )
        for source_key in report.updated_source_keys:
            logger.info("catalog sync updated the config of %s", source_key)
    finally:
        await container.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
