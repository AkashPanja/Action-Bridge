"""Database-backed job worker (FR-9.x).

Run standalone:  python -m app.worker
Runs one process (required for SQLite; see spec section 10). On PostgreSQL the
claim is atomic, so multiple workers are safe. Handles SIGINT/SIGTERM for
graceful shutdown. Jobs left `running` are re-queued on startup (FR-9.4).
"""

import asyncio
import logging
import os
import signal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.services import job_service
from app.services import pipeline  # noqa: F401 - registers extract/webhook job kinds
from app.services.job_service import AsyncSessionLocal

logger = logging.getLogger("app.worker")

_shutdown = asyncio.Event()


def _request_shutdown(*_args):
    _shutdown.set()


async def run_once(max_jobs_in_flight: int = 8) -> int:
    """Claim and execute up to max_jobs_in_flight jobs. Returns jobs completed."""
    done = 0
    in_flight: set[asyncio.Task] = set()
    while len(in_flight) < max_jobs_in_flight:
        async with AsyncSessionLocal() as db:
            job = await job_service.claim_next(db)
        if not job:
            break
        in_flight.add(asyncio.create_task(job_service.run_job(job.id)))
    if in_flight:
        await asyncio.gather(*in_flight)
        done = len(in_flight)
    return done


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_shutdown)
        except NotImplementedError:
            pass  # Windows: SIGTERM handler unsupported

    poll_s = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    logger.info("Worker starting (poll=%ss).", poll_s)

    async with AsyncSessionLocal() as db:
        # M2+ tables may not exist on old DBs; requeue only the jobs table.
        try:
            revived = await job_service.requeue_running(db)
            if revived:
                logger.info("Re-queued %d interrupted job(s).", revived)
        except Exception as exc:  # noqa: BLE001 - worker must survive a fresh/migrating DB
            logger.warning("Could not requeue interrupted jobs: %s", exc)

    email_cycle = 0
    while not _shutdown.is_set():
        try:
            async with AsyncSessionLocal() as db:
                from app.services import processing_service

                try:
                    settings = await processing_service.get_settings(db)
                except Exception:
                    settings = {}
            if settings.get("paused"):
                await asyncio.sleep(poll_s)
                continue
            max_flight = int(settings.get("max_jobs_in_flight", 8))
            completed = await run_once(max_jobs_in_flight=max_flight)
            # Email triggers on a slower cadence (~every 30s): cheap no-op
            # when nothing is due. Skipped entirely while paused above.
            email_cycle += 1
            if email_cycle >= 15:
                email_cycle = 0
                try:
                    async with AsyncSessionLocal() as db:
                        from app.services import email_poll

                        outcomes = await email_poll.poll_due_triggers(db)
                    for outcome in outcomes:
                        if outcome.get("error"):
                            logger.warning(
                                "Trigger %s poll error: %s",
                                outcome.get("trigger_id"), outcome.get("error"),
                            )
                except Exception:
                    logger.exception("Email poll cycle error; backing off.")
            await asyncio.sleep(0 if completed else poll_s)
        except Exception:  # noqa: BLE001 - worker loop must never die
            logger.exception("Worker loop error; backing off.")
            await asyncio.sleep(poll_s)

    logger.info("Worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
