"""`nexus-batch`: runs one Execution."""

import asyncio
import logging

from nexus.bootstrap import Container, build_container
from nexus.core.pipeline import run_execution

logger = logging.getLogger("nexus.batch")


async def run(container: Container | None = None) -> None:
    container = container or build_container()
    try:
        execution = await run_execution(container.uow_factory, container.clock)
        logger.info("execution %s finished: %s", execution.id, execution.result)
    finally:
        await container.dispose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
