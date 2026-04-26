import asyncio
import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.observability import IDEMPOTENCY_CLEANUP_DELETED_TOTAL, IDEMPOTENCY_CLEANUP_RUNS_TOTAL
from app.services.idempotency import delete_expired_idempotency_records

logger = logging.getLogger(__name__)


async def run_idempotency_cleanup_loop(stop_event: asyncio.Event):
    """Continuously cleans expired idempotency records in small batches."""
    interval = max(30, settings.idempotency_cleanup_interval_seconds)
    batch_size = max(1, settings.idempotency_cleanup_batch_size)

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            if stop_event.is_set():
                break
        except asyncio.TimeoutError:
            pass

        db = SessionLocal()
        try:
            deleted = delete_expired_idempotency_records(db, batch_size=batch_size)
            db.commit()
            IDEMPOTENCY_CLEANUP_RUNS_TOTAL.inc()
            if deleted > 0:
                IDEMPOTENCY_CLEANUP_DELETED_TOTAL.inc(deleted)
            if deleted > 0:
                logger.info("idempotency_cleanup", extra={"deleted": deleted, "batch_size": batch_size})
        except Exception:
            db.rollback()
            logger.exception("idempotency_cleanup_failed")
        finally:
            db.close()
