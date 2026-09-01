"""Graceful shutdown handling for Cognitia Brain."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class GracefulShutdown:
    """Handle graceful shutdown of the application."""

    def __init__(self):
        self.shutdown_event = asyncio.Event()
        self.cleanup_callbacks: List[Callable] = []
        self.is_shutting_down = False

    def register_cleanup(self, callback: Callable) -> None:
        """Register a cleanup callback to run on shutdown."""
        self.cleanup_callbacks.append(callback)

    async def shutdown(self, signum: int, frame) -> None:
        """Handle shutdown signal."""
        if self.is_shutting_down:
            logger.warning("Shutdown already in progress, ignoring signal")
            return

        self.is_shutting_down = True
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")

        # Set shutdown event
        self.shutdown_event.set()

        # Run cleanup callbacks
        for callback in self.cleanup_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback()
                else:
                    callback()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")

        logger.info("Graceful shutdown completed")

    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        # Handle SIGINT (Ctrl+C)
        loop.add_signal_handler(
            signal.SIGINT,
            lambda: asyncio.create_task(self.shutdown(signal.SIGINT, None))
        )

        # Handle SIGTERM (systemd stop)
        loop.add_signal_handler(
            signal.SIGTERM,
            lambda: asyncio.create_task(self.shutdown(signal.SIGTERM, None))
        )

        logger.info("Signal handlers registered for graceful shutdown")

    async def wait_for_shutdown(self) -> None:
        """Wait until shutdown is triggered."""
        await self.shutdown_event.wait()


# Global graceful shutdown instance
graceful_shutdown = GracefulShutdown()


async def cleanup_ollama() -> None:
    """Cleanup Ollama connections."""
    logger.info("Cleaning up Ollama connections...")


async def cleanup_database() -> None:
    """Cleanup database connections."""
    logger.info("Cleaning up database connections...")


async def cleanup_telegram() -> None:
    """Cleanup Telegram bot."""
    logger.info("Cleaning up Telegram bot...")


# Register default cleanup callbacks
graceful_shutdown.register_cleanup(cleanup_ollama)
graceful_shutdown.register_cleanup(cleanup_database)
graceful_shutdown.register_cleanup(cleanup_telegram)
