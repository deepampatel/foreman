"""Dispatcher entry point — run as a separate process.

Learn: The dispatcher is its own process, separate from the API server.
This provides crash isolation — if the dispatcher dies, the API keeps running.

Usage:
    uv run python -m openclaw.dispatcher.main

Or via the CLI:
    openclaw-dispatcher
"""

import asyncio
import logging
import signal
import sys

from openclaw.config import settings
from openclaw.dispatcher.turn_dispatcher import DispatcherConfig, TaskDispatcher

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("openclaw.dispatcher")


async def run():
    """Run the dispatcher until interrupted."""
    # Convert SQLAlchemy URL to asyncpg URL
    db_url = settings.database_url.replace("+asyncpg", "").replace(
        "postgresql://", "postgresql://"
    )

    config = DispatcherConfig(
        database_url=db_url,
        redis_url=settings.redis_url,
    )

    dispatcher = TaskDispatcher(config)

    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(dispatcher.stop()))

    logger.info("Dispatcher starting (DB: %s)", db_url.split("@")[1] if "@" in db_url else db_url)

    try:
        await dispatcher.start()
    except asyncio.CancelledError:
        pass
    finally:
        logger.info("Dispatcher stopped. Stats: %s", dispatcher.get_stats())


def main():
    """CLI entry point."""
    asyncio.run(run())


if __name__ == "__main__":
    main()
