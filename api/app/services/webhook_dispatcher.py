import hashlib
import hmac
import json

import httpx
from sqlalchemy.orm import Session

from app.models.entities import WebhookSubscription


async def dispatch_webhook_event(db: Session, tenant_slug: str, event_type: str, payload: dict):
    hooks = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.tenant_slug == tenant_slug,
            WebhookSubscription.event_type == event_type,
            WebhookSubscription.is_active.is_(True),
        )
        .all()
    )

    if not hooks:
        return

    body = json.dumps(payload)
    async with httpx.AsyncClient(timeout=3.0) as client:
        for hook in hooks:
            headers = {"Content-Type": "application/json"}
            if hook.secret:
                signature = hmac.new(hook.secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
                headers["X-Proctor-Signature"] = signature
            try:
                await client.post(hook.target_url, content=body, headers=headers)
            except Exception:
                # Keep exam flow resilient even if webhook target fails.
                continue
