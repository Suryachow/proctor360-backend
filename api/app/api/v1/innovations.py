from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_student
from app.db.session import get_db
from app.models.entities import (
    AdaptiveExamDecision,
    CandidateAppeal,
    Certificate,
    CertificateRevocation,
    CohortRiskSnapshot,
    DeviceTrustSnapshot,
    Exam,
    ExamAnswer,
    ExamQuestion,
    ExamSession,
    EvidenceChainEntry,
    EvidenceFrame,
    IncidentNotificationLog,
    IncidentRoute,
    NetworkHeartbeat,
    PlagiarismAlert,
    ProctorChatMessage,
    ProctorInterventionAction,
    Question,
    QuestionQualityMetric,
    RoleAssignment,
    SubjectiveAnswer,
    TenantBranding,
    Violation,
)

router = APIRouter(prefix="/innovations", tags=["innovations"])


# ------------------------------
# 1) Live proctor interventions + chat
# ------------------------------
@router.post("/proctor/interventions")
async def create_intervention(payload: dict, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    action_type = str(payload.get("action_type") or "").strip()
    if not session_id or action_type not in {"warn", "lock_navigation", "force_reverify", "pause_timer"}:
        raise HTTPException(status_code=400, detail="Invalid intervention payload")

    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    action = ProctorInterventionAction(
        session_id=session_id,
        action_type=action_type,
        payload=payload.get("payload") or {},
        issued_by=admin.get("email", "admin@proctor360.com"),
        status="issued",
    )
    db.add(action)
    db.commit()
    db.refresh(action)

    return {
        "ok": True,
        "id": action.id,
        "session_id": action.session_id,
        "action_type": action.action_type,
        "status": action.status,
        "created_at": action.created_at.isoformat(),
    }


@router.get("/proctor/interventions/{session_id}")
def list_interventions(session_id: int, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(ProctorInterventionAction)
        .filter(ProctorInterventionAction.session_id == session_id)
        .order_by(ProctorInterventionAction.created_at.desc())
        .all()
    )
    return [
        {
            "id": row.id,
            "action_type": row.action_type,
            "payload": row.payload or {},
            "issued_by": row.issued_by,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/proctor/interventions/student/{session_id}")
def list_interventions_for_student(session_id: int, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == session_id, ExamSession.student_id == student.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = (
        db.query(ProctorInterventionAction)
        .filter(ProctorInterventionAction.session_id == session_id)
        .order_by(ProctorInterventionAction.created_at.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "action_type": row.action_type,
            "payload": row.payload or {},
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.post("/proctor/chat/admin/send")
def admin_send_chat(payload: dict, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    message = str(payload.get("message") or "").strip()
    if not session_id or not message:
        raise HTTPException(status_code=400, detail="session_id and message required")

    msg = ProctorChatMessage(
        session_id=session_id,
        sender_role="admin",
        sender_email=admin.get("email", "admin@proctor360.com"),
        message=message,
        is_read=False,
    )
    db.add(msg)
    db.commit()
    return {"ok": True, "id": msg.id}


@router.post("/proctor/chat/student/send")
def student_send_chat(payload: dict, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    message = str(payload.get("message") or "").strip()
    if not session_id or not message:
        raise HTTPException(status_code=400, detail="session_id and message required")

    msg = ProctorChatMessage(
        session_id=session_id,
        sender_role="student",
        sender_email=student.email,
        message=message,
        is_read=False,
    )
    db.add(msg)
    db.commit()
    return {"ok": True, "id": msg.id}


@router.get("/proctor/chat/{session_id}")
def list_chat_messages(session_id: int, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(ProctorChatMessage)
        .filter(ProctorChatMessage.session_id == session_id)
        .order_by(ProctorChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "sender_role": row.sender_role,
            "sender_email": row.sender_email,
            "message": row.message,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/proctor/chat/student/{session_id}")
def list_chat_messages_for_student(session_id: int, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == session_id, ExamSession.student_id == student.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    rows = (
        db.query(ProctorChatMessage)
        .filter(ProctorChatMessage.session_id == session_id)
        .order_by(ProctorChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "sender_role": row.sender_role,
            "sender_email": row.sender_email,
            "message": row.message,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


# ------------------------------
# 2) Tamper-proof evidence chain
# ------------------------------
def _append_chain_entry(db: Session, session_id: int, source_type: str, source_id: str, payload_obj: dict) -> EvidenceChainEntry:
    payload_text = json.dumps(payload_obj, sort_keys=True)
    content_hash = hashlib.sha256(payload_text.encode()).hexdigest()

    prev = (
        db.query(EvidenceChainEntry)
        .filter(EvidenceChainEntry.session_id == session_id)
        .order_by(EvidenceChainEntry.id.desc())
        .first()
    )
    prev_hash = prev.chain_hash if prev else None
    chain_hash = hashlib.sha256(f"{prev_hash or ''}:{content_hash}".encode()).hexdigest()

    entry = EvidenceChainEntry(
        session_id=session_id,
        source_type=source_type,
        source_id=source_id,
        content_hash=content_hash,
        previous_hash=prev_hash,
        chain_hash=chain_hash,
        metadata_json=payload_obj,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/evidence/chain/anchor")
def anchor_evidence(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    source_type = str(payload.get("source_type") or "manual")
    source_id = str(payload.get("source_id") or str(uuid.uuid4()))
    metadata = payload.get("metadata") or {}

    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    entry = _append_chain_entry(db, session_id, source_type, source_id, metadata)
    return {
        "ok": True,
        "chain_hash": entry.chain_hash,
        "content_hash": entry.content_hash,
        "previous_hash": entry.previous_hash,
    }


@router.get("/evidence/chain/{session_id}")
def get_chain(session_id: int, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(EvidenceChainEntry)
        .filter(EvidenceChainEntry.session_id == session_id)
        .order_by(EvidenceChainEntry.id.asc())
        .all()
    )
    return [
        {
            "id": row.id,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "content_hash": row.content_hash,
            "previous_hash": row.previous_hash,
            "chain_hash": row.chain_hash,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


@router.get("/evidence/incident-bundle/{session_id}")
def download_incident_bundle(session_id: int, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    violations = db.query(Violation).filter(Violation.session_id == session_id).all()
    chain = db.query(EvidenceChainEntry).filter(EvidenceChainEntry.session_id == session_id).all()

    bundle = {
        "session": {
            "id": session.id,
            "exam_code": session.exam_code,
            "status": session.status,
            "risk_score": session.risk_score,
        },
        "violations": [
            {
                "event_type": v.event_type,
                "severity": v.severity,
                "risk_delta": v.risk_delta,
                "detail": v.detail,
                "created_at": v.created_at.isoformat(),
            }
            for v in violations
        ],
        "chain": [
            {
                "id": c.id,
                "source_type": c.source_type,
                "chain_hash": c.chain_hash,
                "previous_hash": c.previous_hash,
                "created_at": c.created_at.isoformat(),
            }
            for c in chain
        ],
    }

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("incident_bundle.json", json.dumps(bundle, indent=2))
    mem.seek(0)

    return Response(
        content=mem.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=incident-bundle-{session_id}.zip"},
    )


# ------------------------------
# 3) Candidate appeal workflow
# ------------------------------
@router.post("/appeals")
def submit_appeal(payload: dict, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    reason = str(payload.get("reason") or "").strip()
    if not session_id or not reason:
        raise HTTPException(status_code=400, detail="session_id and reason required")

    appeal = CandidateAppeal(
        session_id=session_id,
        student_email=student.email,
        reason=reason,
        evidence_note=str(payload.get("evidence_note") or "").strip() or None,
        status="open",
    )
    db.add(appeal)
    db.commit()
    db.refresh(appeal)
    return {"ok": True, "appeal_id": appeal.id, "status": appeal.status}


@router.get("/appeals/my")
def list_my_appeals(student=Depends(get_current_student), db: Session = Depends(get_db)):
    rows = (
        db.query(CandidateAppeal)
        .filter(CandidateAppeal.student_email == student.email)
        .order_by(CandidateAppeal.created_at.desc())
        .all()
    )
    return [
        {
            "id": a.id,
            "session_id": a.session_id,
            "reason": a.reason,
            "status": a.status,
            "decision": a.decision,
            "admin_notes": a.admin_notes,
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
    ]


@router.get("/appeals/admin")
def admin_list_appeals(status: str = "open", _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    q = db.query(CandidateAppeal)
    if status != "all":
        q = q.filter(CandidateAppeal.status == status)
    rows = q.order_by(CandidateAppeal.created_at.desc()).all()
    return [
        {
            "id": a.id,
            "session_id": a.session_id,
            "student_email": a.student_email,
            "reason": a.reason,
            "status": a.status,
            "decision": a.decision,
            "admin_notes": a.admin_notes,
            "created_at": a.created_at.isoformat(),
        }
        for a in rows
    ]


@router.post("/appeals/{appeal_id}/decision")
def decide_appeal(appeal_id: int, payload: dict, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    appeal = db.query(CandidateAppeal).filter(CandidateAppeal.id == appeal_id).first()
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found")

    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"accepted", "rejected", "reviewing"}:
        raise HTTPException(status_code=400, detail="Invalid decision")

    appeal.decision = decision
    appeal.status = decision
    appeal.admin_notes = str(payload.get("admin_notes") or "").strip() or None
    if decision in {"accepted", "rejected"}:
        appeal.resolved_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "appeal_id": appeal.id, "status": appeal.status}


# ------------------------------
# 4) Advanced device trust score
# ------------------------------
@router.post("/trust/ingest")
def ingest_trust_snapshot(payload: dict, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    signals = payload.get("signals") or {}
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    penalties = 0.0
    penalties += 25.0 if signals.get("vpn") else 0.0
    penalties += 35.0 if signals.get("vm") else 0.0
    penalties += 45.0 if signals.get("remote_desktop") else 0.0
    penalties += 20.0 if signals.get("fingerprint_drift") else 0.0

    score = max(0.0, 100.0 - penalties)
    band = "low" if score >= 75 else "medium" if score >= 45 else "high"

    row = DeviceTrustSnapshot(session_id=session_id, trust_score=score, risk_band=band, signals=signals)
    db.add(row)

    session = db.query(ExamSession).filter(ExamSession.id == session_id, ExamSession.student_id == student.id).first()
    if session:
        session.device_integrity_score = score

    db.commit()
    return {"ok": True, "trust_score": score, "risk_band": band}


@router.get("/trust/{session_id}")
def get_trust_history(session_id: int, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = (
        db.query(DeviceTrustSnapshot)
        .filter(DeviceTrustSnapshot.session_id == session_id)
        .order_by(DeviceTrustSnapshot.created_at.desc())
        .all()
    )
    return [
        {
            "trust_score": r.trust_score,
            "risk_band": r.risk_band,
            "signals": r.signals or {},
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ------------------------------
# 5) Network instability resilience
# ------------------------------
@router.post("/network/heartbeat")
def heartbeat(payload: dict, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    latency = float(payload.get("latency_ms") or 0.0)
    packet_loss = float(payload.get("packet_loss_percent") or 0.0)
    jitter = float(payload.get("jitter_ms") or 0.0)
    offline_count = int(payload.get("offline_buffer_count") or 0)

    grace = latency > 1200 or packet_loss > 20.0
    row = NetworkHeartbeat(
        session_id=session_id,
        latency_ms=latency,
        packet_loss_percent=packet_loss,
        jitter_ms=jitter,
        offline_buffer_count=offline_count,
        grace_applied=grace,
    )
    db.add(row)
    db.commit()
    return {"ok": True, "grace_applied": grace}


@router.post("/network/answers/batch")
def submit_answer_batch(payload: dict, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    answers = payload.get("answers") or []
    if not session_id or not isinstance(answers, list):
        raise HTTPException(status_code=400, detail="Invalid payload")

    session = db.query(ExamSession).filter(ExamSession.id == session_id, ExamSession.student_id == student.id).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=400, detail="Session not active")

    upserts = 0
    for item in answers:
        qid = int(item.get("question_id") or 0)
        sel = str(item.get("selected_option") or "").upper()
        if not qid or sel not in {"A", "B", "C", "D"}:
            continue
        q = db.query(Question).filter(Question.id == qid).first()
        if not q:
            continue
        existing = db.query(ExamAnswer).filter(ExamAnswer.session_id == session_id, ExamAnswer.question_id == qid).first()
        if not existing:
            existing = ExamAnswer(session_id=session_id, question_id=qid, selected_option=sel, is_correct=(sel == q.correct_option))
            db.add(existing)
        else:
            existing.selected_option = sel
            existing.is_correct = (sel == q.correct_option)
        upserts += 1

    db.commit()
    return {"ok": True, "upserted": upserts}


# ------------------------------
# 6) Adaptive exam difficulty
# ------------------------------
def _difficulty_rank(tag: str) -> int:
    value = (tag or "").lower()
    if "hard" in value:
        return 3
    if "easy" in value:
        return 1
    return 2


@router.post("/adaptive/next-question")
def adaptive_next_question(payload: dict, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    previous_correct = payload.get("previous_correct")

    session = db.query(ExamSession).filter(ExamSession.id == session_id, ExamSession.student_id == student.id).first()
    if not session or session.status != "active":
        raise HTTPException(status_code=400, detail="Session not active")

    exam = db.query(Exam).filter(Exam.code == session.exam_code).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    answered_ids = {a.question_id for a in db.query(ExamAnswer).filter(ExamAnswer.session_id == session_id).all()}
    links = db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).all()
    pending_qids = [l.question_id for l in links if l.question_id not in answered_ids]
    if not pending_qids:
        return {"ok": True, "next_question": None, "chosen_difficulty": "none"}

    questions = db.query(Question).filter(Question.id.in_(pending_qids)).all()
    if previous_correct is True:
        questions = sorted(questions, key=lambda q: _difficulty_rank(q.sub_topic or q.topic), reverse=True)
        chosen = "hard"
    elif previous_correct is False:
        questions = sorted(questions, key=lambda q: _difficulty_rank(q.sub_topic or q.topic))
        chosen = "easy"
    else:
        questions = sorted(questions, key=lambda q: _difficulty_rank(q.sub_topic or q.topic))
        chosen = "medium"

    next_q = questions[0]
    decision = AdaptiveExamDecision(
        session_id=session_id,
        question_id=next_q.id,
        previous_correct=(bool(previous_correct) if previous_correct is not None else None),
        chosen_difficulty=chosen,
        rationale="Rule-based adaptation from last answer outcome",
    )
    db.add(decision)
    db.commit()

    return {
        "ok": True,
        "chosen_difficulty": chosen,
        "next_question": {
            "id": next_q.id,
            "prompt": next_q.prompt,
            "options": [next_q.option_a, next_q.option_b, next_q.option_c, next_q.option_d],
        },
    }


# ------------------------------
# 7) Plagiarism and similarity detection
# ------------------------------
@router.post("/plagiarism/subjective-answer")
def submit_subjective_answer(payload: dict, student=Depends(get_current_student), db: Session = Depends(get_db)):
    session_id = int(payload.get("session_id") or 0)
    question_prompt = str(payload.get("question_prompt") or "").strip()
    answer_text = str(payload.get("answer_text") or "").strip()
    if not session_id or not question_prompt or not answer_text:
        raise HTTPException(status_code=400, detail="session_id, question_prompt and answer_text required")

    row = SubjectiveAnswer(
        session_id=session_id,
        student_email=student.email,
        question_prompt=question_prompt,
        answer_text=answer_text,
    )
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id}


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"\W+", (text or "").lower()) if t}


@router.post("/plagiarism/run")
def run_plagiarism_scan(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    threshold = float(payload.get("threshold") or 0.72)
    answers = db.query(SubjectiveAnswer).order_by(SubjectiveAnswer.id.asc()).all()
    run_id = uuid.uuid4().hex[:16]
    created = 0

    for i in range(len(answers)):
        for j in range(i + 1, len(answers)):
            a = answers[i]
            b = answers[j]
            if a.session_id == b.session_id:
                continue
            ta, tb = _tokenize(a.answer_text), _tokenize(b.answer_text)
            denom = max(len(ta | tb), 1)
            score = len(ta & tb) / denom
            if score >= threshold:
                row = PlagiarismAlert(
                    run_id=run_id,
                    session_id_a=a.session_id,
                    session_id_b=b.session_id,
                    similarity_score=round(score, 4),
                    status="flagged",
                    details={"question_a": a.question_prompt, "question_b": b.question_prompt},
                )
                db.add(row)
                created += 1

    db.commit()
    return {"ok": True, "run_id": run_id, "alerts_created": created}


@router.get("/plagiarism/alerts")
def list_plagiarism_alerts(limit: int = 200, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.query(PlagiarismAlert).order_by(PlagiarismAlert.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "session_id_a": r.session_id_a,
            "session_id_b": r.session_id_b,
            "similarity_score": r.similarity_score,
            "status": r.status,
            "details": r.details or {},
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ------------------------------
# 8) Cohort risk analytics
# ------------------------------
@router.get("/analytics/cohort-risk")
def cohort_risk(exam_code: str | None = None, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    q = db.query(ExamSession)
    if exam_code:
        q = q.filter(ExamSession.exam_code == exam_code.strip().upper())
    sessions = q.all()

    buckets: dict[str, dict] = {}
    for s in sessions:
        hour = s.started_at.strftime("%Y-%m-%d %H:00") if s.started_at else "unknown"
        bucket = buckets.setdefault(hour, {"hour_bucket": hour, "total_sessions": 0, "high_risk_count": 0, "risk_sum": 0.0})
        bucket["total_sessions"] += 1
        bucket["risk_sum"] += float(s.risk_score or 0.0)
        if (s.risk_score or 0.0) >= 70:
            bucket["high_risk_count"] += 1

    out = []
    for hour, b in sorted(buckets.items()):
        avg = round(b["risk_sum"] / max(b["total_sessions"], 1), 2)
        out.append({
            "hour_bucket": hour,
            "total_sessions": b["total_sessions"],
            "high_risk_count": b["high_risk_count"],
            "avg_risk": avg,
        })
    return out


# ------------------------------
# 9) Role-based multi-tenant controls
# ------------------------------
@router.post("/rbac/assign-role")
def assign_role(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    email = str(payload.get("user_email") or "").strip().lower()
    role = str(payload.get("role") or "").strip().lower()
    tenant_slug = str(payload.get("tenant_slug") or "default").strip().lower()
    if not email or role not in {"super_admin", "tenant_admin", "proctor", "reviewer"}:
        raise HTTPException(status_code=400, detail="Invalid role assignment")

    row = RoleAssignment(user_email=email, role=role, tenant_slug=tenant_slug)
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id}


@router.get("/rbac/roles")
def list_roles(_: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.query(RoleAssignment).order_by(RoleAssignment.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "user_email": r.user_email,
            "role": r.role,
            "tenant_slug": r.tenant_slug,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.post("/tenant/branding")
def upsert_branding(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    tenant_slug = str(payload.get("tenant_slug") or "default").strip().lower()
    row = db.query(TenantBranding).filter(TenantBranding.tenant_slug == tenant_slug).first()
    if not row:
        row = TenantBranding(tenant_slug=tenant_slug)
        db.add(row)

    row.brand_name = str(payload.get("brand_name") or row.brand_name)
    row.primary_color = str(payload.get("primary_color") or row.primary_color)
    row.logo_url = payload.get("logo_url")
    row.policy_json = payload.get("policy_json") or row.policy_json
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "tenant_slug": tenant_slug}


@router.get("/tenant/branding/{tenant_slug}")
def get_branding(tenant_slug: str, db: Session = Depends(get_db)):
    row = db.query(TenantBranding).filter(TenantBranding.tenant_slug == tenant_slug.strip().lower()).first()
    if not row:
        return {"tenant_slug": tenant_slug, "brand_name": "Proctor360", "primary_color": "#000000", "logo_url": None, "policy_json": {}}
    return {
        "tenant_slug": row.tenant_slug,
        "brand_name": row.brand_name,
        "primary_color": row.primary_color,
        "logo_url": row.logo_url,
        "policy_json": row.policy_json or {},
        "updated_at": row.updated_at.isoformat(),
    }


# ------------------------------
# 10) Notification and incident routing
# ------------------------------
@router.post("/notifications/routes")
def create_incident_route(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    channel = str(payload.get("channel_type") or "").strip().lower()
    target = str(payload.get("target_url") or "").strip()
    if channel not in {"webhook", "slack", "teams"} or not target:
        raise HTTPException(status_code=400, detail="Invalid route payload")

    row = IncidentRoute(
        tenant_slug=str(payload.get("tenant_slug") or "default").strip().lower(),
        channel_type=channel,
        target_url=target,
        severity_min=str(payload.get("severity_min") or "medium").strip().lower(),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(row)
    db.commit()
    return {"ok": True, "id": row.id}


@router.get("/notifications/routes")
def list_incident_routes(_: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    rows = db.query(IncidentRoute).order_by(IncidentRoute.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "tenant_slug": r.tenant_slug,
            "channel_type": r.channel_type,
            "target_url": r.target_url,
            "severity_min": r.severity_min,
            "is_active": r.is_active,
        }
        for r in rows
    ]


@router.post("/notifications/dispatch-test")
def dispatch_test_notification(payload: dict, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    event_type = str(payload.get("event_type") or "test.notification")
    data = payload.get("payload") or {"message": "test"}
    rows = db.query(IncidentRoute).filter(IncidentRoute.is_active.is_(True)).all()
    count = 0
    for route in rows:
        log = IncidentNotificationLog(
            route_id=route.id,
            event_type=event_type,
            payload_json=data,
            status="simulated_sent",
            response_code=200,
        )
        db.add(log)
        count += 1
    db.commit()
    return {"ok": True, "dispatched": count}


# ------------------------------
# 11) Certificate verification portal
# ------------------------------
@router.get("/certificates/verify/{verification_hash}")
def verify_certificate(verification_hash: str, db: Session = Depends(get_db)):
    cert = db.query(Certificate).filter(Certificate.verification_hash == verification_hash).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    revoked = db.query(CertificateRevocation).filter(CertificateRevocation.verification_hash == verification_hash).first()
    return {
        "valid": revoked is None,
        "revoked": revoked is not None,
        "student_email": cert.student_email,
        "exam_code": cert.exam_code,
        "score_percent": cert.score_percent,
        "integrity_band": cert.integrity_band,
        "issued_at": cert.issued_at.isoformat(),
        "revocation_reason": revoked.reason if revoked else None,
    }


@router.post("/certificates/revoke")
def revoke_certificate(payload: dict, admin=Depends(get_current_admin), db: Session = Depends(get_db)):
    verification_hash = str(payload.get("verification_hash") or "").strip()
    reason = str(payload.get("reason") or "Administrative revocation")
    if not verification_hash:
        raise HTTPException(status_code=400, detail="verification_hash required")

    cert = db.query(Certificate).filter(Certificate.verification_hash == verification_hash).first()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    exists = db.query(CertificateRevocation).filter(CertificateRevocation.verification_hash == verification_hash).first()
    if exists:
        return {"ok": True, "already_revoked": True}

    rev = CertificateRevocation(
        certificate_id=cert.id,
        verification_hash=verification_hash,
        reason=reason,
        revoked_by=admin.get("email", "admin@proctor360.com"),
    )
    db.add(rev)
    db.commit()
    return {"ok": True, "revoked": True}


# ------------------------------
# 12) Test quality engine
# ------------------------------
@router.post("/quality/recompute")
def recompute_quality(_: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    question_ids = [qid for (qid,) in db.query(ExamAnswer.question_id).distinct().all()]
    updated = 0
    for qid in question_ids:
        rows = db.query(ExamAnswer).filter(ExamAnswer.question_id == qid).all()
        attempts = len(rows)
        if attempts == 0:
            continue

        correct = sum(1 for r in rows if r.is_correct)
        correct_rate = round(correct / attempts, 4)
        option_dist = {"A": 0, "B": 0, "C": 0, "D": 0}
        for r in rows:
            option_dist[r.selected_option] = option_dist.get(r.selected_option, 0) + 1

        # Approximate discrimination: distance from ideal 0.6 difficulty
        discrimination_index = round(1.0 - abs(correct_rate - 0.6), 4)
        flagged = correct_rate < 0.2 or correct_rate > 0.95 or discrimination_index < 0.35
        flag_reason = "too_easy_or_hard" if (correct_rate < 0.2 or correct_rate > 0.95) else "low_discrimination" if flagged else None

        metric = db.query(QuestionQualityMetric).filter(QuestionQualityMetric.question_id == qid).first()
        if not metric:
            metric = QuestionQualityMetric(question_id=qid)
            db.add(metric)

        metric.attempts = attempts
        metric.correct_rate = correct_rate
        metric.discrimination_index = discrimination_index
        metric.option_distribution = option_dist
        metric.flagged = flagged
        metric.flag_reason = flag_reason
        metric.last_computed_at = datetime.utcnow()
        updated += 1

    db.commit()
    return {"ok": True, "updated_questions": updated}


@router.get("/quality/questions")
def list_question_quality(flagged_only: bool = False, _: dict = Depends(get_current_admin), db: Session = Depends(get_db)):
    q = db.query(QuestionQualityMetric)
    if flagged_only:
        q = q.filter(QuestionQualityMetric.flagged.is_(True))
    rows = q.order_by(QuestionQualityMetric.last_computed_at.desc()).all()
    return [
        {
            "question_id": r.question_id,
            "attempts": r.attempts,
            "correct_rate": r.correct_rate,
            "discrimination_index": r.discrimination_index,
            "option_distribution": r.option_distribution or {},
            "flagged": r.flagged,
            "flag_reason": r.flag_reason,
            "last_computed_at": r.last_computed_at.isoformat(),
        }
        for r in rows
    ]
