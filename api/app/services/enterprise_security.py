import hashlib
import secrets
from datetime import datetime

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app.models.entities import ApiKey, PermissionMatrix


def get_tenant_slug_header(x_tenant_id: str | None = Header(default=None)) -> str:
    tenant_slug = (x_tenant_id or "default").strip().lower()
    return tenant_slug or "default"


def has_permission(db: Session, tenant_slug: str, role: str, resource: str, action: str) -> bool:
    row = (
        db.query(PermissionMatrix)
        .filter(
            PermissionMatrix.tenant_slug == tenant_slug,
            PermissionMatrix.role == role,
            PermissionMatrix.resource == resource,
            PermissionMatrix.action == action,
        )
        .first()
    )
    if not row:
        return role == "admin"
    return row.effect.lower() == "allow"


def assert_permission(db: Session, tenant_slug: str, role: str, resource: str, action: str):
    if not has_permission(db, tenant_slug, role, resource, action):
        raise HTTPException(status_code=403, detail="Permission denied by tenant policy")


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def issue_api_key(tenant_slug: str) -> tuple[str, str]:
    raw = f"pk_{tenant_slug}_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw)


def validate_api_key(db: Session, raw_key: str, required_scope: str, tenant_slug: str | None = None) -> ApiKey:
    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    key_hash = hash_api_key(raw_key)
    api_key = db.query(ApiKey).filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True)).first()
    if not api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if tenant_slug and api_key.tenant_slug != tenant_slug:
        raise HTTPException(status_code=403, detail="API key tenant mismatch")

    scopes = {scope.strip() for scope in api_key.scopes.split(",") if scope.strip()}
    if required_scope not in scopes and "*" not in scopes:
        raise HTTPException(status_code=403, detail="API key scope denied")

    api_key.last_used_at = datetime.utcnow()
    db.commit()
    return api_key
