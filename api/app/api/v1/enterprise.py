from datetime import datetime
from io import BytesIO
import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.entities import (
    ApiKey,
    Exam,
    ExamSession,
    IntegrationConfig,
    PermissionMatrix,
    Tenant,
    TenantExamBinding,
    Violation,
    WebhookSubscription,
    WorkflowRule,
)
from app.services.enterprise_security import assert_permission, issue_api_key, validate_api_key

router = APIRouter(prefix="/enterprise", tags=["enterprise"])


def _tenant_slug(x_tenant_id: str | None) -> str:
    return (x_tenant_id or "default").strip().lower() or "default"


@router.post("/tenants")
def create_tenant(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    slug = (payload.get("slug") or "").strip().lower()
    name = (payload.get("name") or "").strip()
    if not slug or not name:
        raise HTTPException(status_code=400, detail="name and slug are required")

    existing = db.query(Tenant).filter(Tenant.slug == slug).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tenant slug already exists")

    tenant = Tenant(slug=slug, name=name)
    db.add(tenant)
    db.commit()
    return {"ok": True, "slug": slug, "name": name}


@router.get("/tenants")
def list_tenants(_: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [{"slug": row.slug, "name": row.name, "is_active": row.is_active, "created_at": row.created_at} for row in rows]


@router.post("/permissions")
def upsert_permission(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    tenant_slug = (payload.get("tenant_slug") or "default").strip().lower()
    role = (payload.get("role") or "admin").strip().lower()
    resource = (payload.get("resource") or "*").strip().lower()
    action = (payload.get("action") or "*").strip().lower()
    effect = (payload.get("effect") or "allow").strip().lower()

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
        row = PermissionMatrix(
            tenant_slug=tenant_slug,
            role=role,
            resource=resource,
            action=action,
            effect=effect,
        )
        db.add(row)
    else:
        row.effect = effect

    db.commit()
    return {"ok": True}


@router.get("/permissions")
def list_permissions(tenant_slug: str = "default", _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.query(PermissionMatrix).filter(PermissionMatrix.tenant_slug == tenant_slug).all()
    return [
        {
            "id": row.id,
            "tenant_slug": row.tenant_slug,
            "role": row.role,
            "resource": row.resource,
            "action": row.action,
            "effect": row.effect,
        }
        for row in rows
    ]


@router.post("/workflow/rules")
def create_workflow_rule(
    payload: dict,
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    assert_permission(db, tenant_slug, "admin", "workflow", "write")

    name = (payload.get("name") or "").strip() or "Rule"
    metric = (payload.get("metric") or "risk_score").strip()
    threshold = float(payload.get("threshold") or 70)
    action = (payload.get("action") or "warn").strip().lower()

    rule = WorkflowRule(
        tenant_slug=tenant_slug,
        name=name,
        metric=metric,
        threshold=threshold,
        action=action,
        is_active=True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"ok": True, "id": rule.id}


@router.get("/workflow/rules")
def list_workflow_rules(
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    assert_permission(db, tenant_slug, "admin", "workflow", "read")
    rows = (
        db.query(WorkflowRule)
        .filter(WorkflowRule.tenant_slug == tenant_slug)
        .order_by(WorkflowRule.created_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "name": row.name,
            "metric": row.metric,
            "threshold": row.threshold,
            "action": row.action,
            "is_active": row.is_active,
        }
        for row in rows
    ]


@router.post("/public/api-keys")
def create_api_key(
    payload: dict,
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    assert_permission(db, tenant_slug, "admin", "api_keys", "write")
    name = (payload.get("name") or "Public integration key").strip()
    scopes = payload.get("scopes") or ["exams:read"]
    if not isinstance(scopes, list):
        raise HTTPException(status_code=400, detail="scopes must be an array")

    raw_key, key_hash = issue_api_key(tenant_slug)
    row = ApiKey(tenant_slug=tenant_slug, name=name, key_hash=key_hash, scopes=",".join(scopes), is_active=True)
    db.add(row)
    db.commit()
    return {"ok": True, "api_key": raw_key, "name": name, "scopes": scopes}


@router.get("/public/api-keys")
def list_api_keys(
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    rows = db.query(ApiKey).filter(ApiKey.tenant_slug == tenant_slug).all()
    return [
        {
            "id": row.id,
            "name": row.name,
            "scopes": [scope for scope in row.scopes.split(",") if scope],
            "is_active": row.is_active,
            "created_at": row.created_at,
            "last_used_at": row.last_used_at,
        }
        for row in rows
    ]


@router.post("/public/webhooks")
def create_webhook(
    payload: dict,
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    event_type = (payload.get("event_type") or "exam.completed").strip()
    target_url = (payload.get("target_url") or "").strip()
    secret = (payload.get("secret") or "").strip()
    if not target_url:
        raise HTTPException(status_code=400, detail="target_url is required")

    row = WebhookSubscription(
        tenant_slug=tenant_slug,
        event_type=event_type,
        target_url=target_url,
        secret=secret,
        is_active=True,
    )
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id}


@router.get("/public/webhooks")
def list_webhooks(
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    rows = db.query(WebhookSubscription).filter(WebhookSubscription.tenant_slug == tenant_slug).all()
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "target_url": row.target_url,
            "is_active": row.is_active,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/integrations/lms")
def upsert_lms_integration(
    payload: dict,
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    provider = (payload.get("provider") or "moodle").strip().lower()
    config = payload.get("config") or {}
    row = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.tenant_slug == tenant_slug,
            IntegrationConfig.kind == "lms",
            IntegrationConfig.provider == provider,
        )
        .first()
    )
    if not row:
        row = IntegrationConfig(
            tenant_slug=tenant_slug,
            kind="lms",
            provider=provider,
            config_json=json.dumps(config),
            is_active=True,
        )
        db.add(row)
    else:
        row.config_json = json.dumps(config)
    db.commit()
    return {"ok": True, "provider": provider}


@router.post("/integrations/sso")
def upsert_sso_integration(
    payload: dict,
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    provider = (payload.get("provider") or "google").strip().lower()
    config = payload.get("config") or {}
    row = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.tenant_slug == tenant_slug,
            IntegrationConfig.kind == "sso",
            IntegrationConfig.provider == provider,
        )
        .first()
    )
    if not row:
        row = IntegrationConfig(
            tenant_slug=tenant_slug,
            kind="sso",
            provider=provider,
            config_json=json.dumps(config),
            is_active=True,
        )
        db.add(row)
    else:
        row.config_json = json.dumps(config)
    db.commit()
    return {"ok": True, "provider": provider}


@router.get("/integrations")
def list_integrations(
    _: dict = Depends(get_current_admin),
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    rows = db.query(IntegrationConfig).filter(IntegrationConfig.tenant_slug == tenant_slug).all()
    return [
        {
            "id": row.id,
            "kind": row.kind,
            "provider": row.provider,
            "config": json.loads(row.config_json or "{}"),
            "is_active": row.is_active,
        }
        for row in rows
    ]


@router.get("/public/exams/{exam_code}/summary")
def public_exam_summary(
    exam_code: str,
    x_api_key: str = Header(default=""),
    x_tenant_id: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    tenant_slug = _tenant_slug(x_tenant_id)
    validate_api_key(db, x_api_key, "exams:read", tenant_slug)

    exam = db.query(Exam).filter(Exam.code == exam_code.strip().upper()).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    sessions = db.query(ExamSession).filter(ExamSession.exam_code == exam.code).all()
    completed = [s for s in sessions if s.status in {"submitted", "auto_submitted", "terminated"}]
    avg_risk = round(sum(s.risk_score for s in completed) / len(completed), 2) if completed else 0.0
    return {
        "exam_code": exam.code,
        "title": exam.title,
        "question_count": len(exam.question_links),
        "session_count": len(sessions),
        "completed_count": len(completed),
        "avg_risk": avg_risk,
        "tenant_slug": tenant_slug,
    }


@router.get("/forensics/timeline/{session_id}")
def forensics_timeline(session_id: int, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    violations = (
        db.query(Violation)
        .filter(Violation.session_id == session.id)
        .order_by(Violation.created_at.asc())
        .all()
    )

    cumulative = 0.0
    replay = []
    for item in violations:
        cumulative += item.risk_delta
        replay.append(
            {
                "timestamp": item.created_at,
                "event_type": item.event_type,
                "detail": item.detail,
                "risk_delta": item.risk_delta,
                "cumulative_risk": round(cumulative, 2),
            }
        )

    return {"session_id": session.id, "exam_code": session.exam_code, "status": session.status, "timeline": replay}


@router.get("/forensics/report/{session_id}")
def forensics_report_pdf(session_id: int, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    exam = db.query(Exam).filter(Exam.code == session.exam_code).first()
    violations = db.query(Violation).filter(Violation.session_id == session.id).order_by(Violation.created_at.asc()).all()
    integrity_score = max(0.0, min(100.0, round(100.0 - session.risk_score, 2)))

    pdf = FPDF(orientation='L')
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, "Proctoring Forensics Report", ln=True)
    pdf.cell(0, 10, f"Session ID: {session.id}", ln=True)
    pdf.cell(0, 10, f"Exam: {session.exam_code} - {(exam.title if exam else session.exam_code)}", ln=True)
    pdf.cell(0, 10, f"Status: {session.status}", ln=True)
    pdf.cell(0, 10, f"Risk Score: {session.risk_score}", ln=True)
    pdf.cell(0, 10, f"Integrity Score: {integrity_score}", ln=True)
    pdf.ln(4)
    pdf.multi_cell(0, 8, "Violation Timeline:")
    for item in violations:
        line = f"{item.created_at} | {item.event_type} | +{item.risk_delta} | {item.detail[:120]}"
        pdf.multi_cell(0, 7, line)

    raw_content = pdf.output(dest="S")
    if isinstance(raw_content, str):
        content = raw_content.encode("latin-1")
    else:
        content = bytes(raw_content)
    filename = f"forensics-session-{session.id}.pdf"
    return StreamingResponse(BytesIO(content), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={filename}"})


@router.post("/bind/exam")
def bind_exam_to_tenant(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    tenant_slug = (payload.get("tenant_slug") or "default").strip().lower()
    exam_code = (payload.get("exam_code") or "").strip().upper()
    if not exam_code:
        raise HTTPException(status_code=400, detail="exam_code is required")

    row = (
        db.query(TenantExamBinding)
        .filter(TenantExamBinding.tenant_slug == tenant_slug, TenantExamBinding.exam_code == exam_code)
        .first()
    )
    if not row:
        row = TenantExamBinding(tenant_slug=tenant_slug, exam_code=exam_code, created_at=datetime.utcnow())
        db.add(row)
        db.commit()

    return {"ok": True, "tenant_slug": tenant_slug, "exam_code": exam_code}
