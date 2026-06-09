from __future__ import annotations

import asyncio
import logging

from src_python.main import run_task

logger = logging.getLogger(__name__)


async def check_options_task() -> None:
    logger.info("running task")
    await run_task()
    logger.info("Task finished successfully")


if __name__ == "__main__":
    asyncio.run(check_options_task())

