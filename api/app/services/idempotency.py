from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import IdempotencyRecord


def get_idempotent_response(
    db: Session,
    scope: str,
    actor_id: str,
    idempotency_key: str,
):
    if not idempotency_key:
        return None

    record = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.idempotency_key == idempotency_key,
            IdempotencyRecord.expires_at >= datetime.utcnow(),
        )
        .first()
    )
    if not record:
        return None
    return record.response_payload


def store_idempotent_response(
    db: Session,
    scope: str,
    actor_id: str,
    idempotency_key: str,
    response_payload: dict,
):
    if not idempotency_key:
        return

    expires_at = datetime.utcnow() + timedelta(seconds=max(60, settings.idempotency_ttl_seconds))
    existing = (
        db.query(IdempotencyRecord)
        .filter(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        .first()
    )

    if existing:
        existing.response_payload = response_payload
        existing.expires_at = expires_at
        return

    db.add(
        IdempotencyRecord(
            scope=scope,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            response_payload=response_payload,
            expires_at=expires_at,
        )
    )


def delete_expired_idempotency_records(
    db: Session,
    batch_size: int | None = None,
) -> int:
    """Delete expired idempotency records in bounded batches."""
    limit = max(1, batch_size or settings.idempotency_cleanup_batch_size)
    expired_ids = (
        db.query(IdempotencyRecord.id)
        .filter(IdempotencyRecord.expires_at < datetime.utcnow())
        .order_by(IdempotencyRecord.id.asc())
        .limit(limit)
        .all()
    )
    if not expired_ids:
        return 0

    id_values = [row[0] for row in expired_ids]
    deleted = (
        db.query(IdempotencyRecord)
        .filter(IdempotencyRecord.id.in_(id_values))
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)
