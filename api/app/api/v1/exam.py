import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.api.deps import get_current_student
from app.core.security import verify_password
from app.db.session import get_db
from app.models.entities import Exam, ExamAnswer, ExamEnrollment, ExamOtpUse, ExamQuestion, ExamSession, EvidenceFrame, Question, Student, TenantExamBinding, Violation
from app.schemas.exam import (
    AnswerSaveRequest, AnswerSaveResponse, AssignedExamOut, AttemptedExamOut,
    AvailableExamOut, ExamReportOut, EventRequest, ExamQuestionOut,
    FrameAnalyzeRequest, SessionAnswersOut, SessionResponse,
    StartExamRequest, StudentDashboardOut, SubmitExamResponse,
)
from app.services.ai_client import analyze_frame
from app.services.exam_report import build_exam_report
from app.services.exam_report_pdf import build_exam_report_pdf
from app.services.idempotency import get_idempotent_response, store_idempotent_response
from app.services.webhook_dispatcher import dispatch_webhook_event
from app.services.workflow_engine import evaluate_workflow_rules
from app.services.violation_engine import (
    build_explainability_statement,
    calculate_decayed_risk,
    canonical_event_type,
    get_reason,
    get_risk_delta,
    get_severity,
    get_violation_category,
    normalize_risk,
    should_auto_submit,
)
from app.services.ws_manager import ws_manager


router = APIRouter(prefix="/exam", tags=["exam"])
logger = logging.getLogger(__name__)

TEMPORAL_POSE_TRACKERS: dict[int, dict] = defaultdict(
    lambda: {
        "samples": deque(maxlen=32),
        "last_emit_at": None,
        "last_seen_at": None,
    }
)

SIGNAL_PERSISTENCE_TRACKERS: dict[int, dict] = defaultdict(
    lambda: {
        "window": deque(maxlen=4),
        "last_seen_at": None,
        "multiple_faces_first_seen_at": None,
    }
)


def _evaluate_temporal_face_angle_drift(
    session_id: int,
    face_count: int,
    ai_metrics: dict,
    normalized_events: list[dict],
) -> list[dict]:
    now = datetime.utcnow()

    # Opportunistic cleanup for stale sessions.
    stale_cutoff = now - timedelta(minutes=30)
    stale_ids = [sid for sid, state in TEMPORAL_POSE_TRACKERS.items() if state.get("last_seen_at") and state["last_seen_at"] < stale_cutoff]
    for sid in stale_ids:
        TEMPORAL_POSE_TRACKERS.pop(sid, None)

    tracker = TEMPORAL_POSE_TRACKERS[session_id]
    tracker["last_seen_at"] = now

    pose_proxy = ai_metrics.get("pose_proxy") or {}
    center_x = pose_proxy.get("center_x")
    profile_ratio = pose_proxy.get("profile_ratio")

    if face_count != 1 or center_x is None or profile_ratio is None:
        tracker["samples"].clear()
        return []

    tracker["samples"].append(
        {
            "at": now,
            "center_x": float(center_x),
            "profile_ratio": float(profile_ratio),
        }
    )

    # Keep only recent consecutive observations.
    recent = [s for s in tracker["samples"] if (now - s["at"]).total_seconds() <= 24]
    if len(recent) < 6:
        return []

    center_values = [s["center_x"] for s in recent]
    ratio_values = [s["profile_ratio"] for s in recent]
    center_span = max(center_values) - min(center_values)
    off_center_count = sum(1 for cx in center_values if abs(cx - 0.5) > 0.16)
    side_profile_count = sum(1 for r in ratio_values if r < 0.78)

    has_instant_lookaway = any(
        canonical_event_type(item.get("event_type")) in {"looking_away", "gaze_deviation"}
        for item in normalized_events
    )
    sustained_drift = (
        (off_center_count >= 5)
        or (side_profile_count >= 4)
        or (center_span >= 0.24 and off_center_count >= 4)
    )
    if not sustained_drift or has_instant_lookaway:
        return []

    last_emit_at = tracker.get("last_emit_at")
    if last_emit_at and (now - last_emit_at).total_seconds() < 10:
        return []

    tracker["last_emit_at"] = now
    confidence = min(0.95, 0.60 + (off_center_count * 0.04) + (side_profile_count * 0.03))

    return [
        {
            "event_type": "looking_away",
            "detail": "Temporal head-angle drift detected across consecutive frames",
            "confidence": float(round(confidence, 3)),
            "score": float(round(confidence, 3)),
            "rationale": "Session-level drift model observed sustained off-center head-angle behavior over time.",
            "explainability": (
                f"Temporal drift: off_center_count={off_center_count}, "
                f"side_profile_count={side_profile_count}, center_span={center_span:.2f}"
            ),
        }
    ]


def _apply_signal_persistence_filter(session_id: int, normalized_events: list[dict]) -> list[dict]:
    now = datetime.utcnow()

    # Opportunistic cleanup for stale sessions.
    stale_cutoff = now - timedelta(minutes=30)
    stale_ids = [
        sid
        for sid, state in SIGNAL_PERSISTENCE_TRACKERS.items()
        if state.get("last_seen_at") and state["last_seen_at"] < stale_cutoff
    ]
    for sid in stale_ids:
        SIGNAL_PERSISTENCE_TRACKERS.pop(sid, None)

    tracker = SIGNAL_PERSISTENCE_TRACKERS[session_id]
    tracker["last_seen_at"] = now

    frame_event_types = {
        canonical_event_type(item.get("event_type"))
        for item in normalized_events
        if item.get("event_type")
    }
    tracker["window"].append(frame_event_types)

    guarded_types = {"multiple_faces", "phone_detected"}
    filtered_events = []
    multiple_faces_seen_this_frame = "multiple_faces" in frame_event_types

    if multiple_faces_seen_this_frame:
        if tracker.get("multiple_faces_first_seen_at") is None:
            tracker["multiple_faces_first_seen_at"] = now
    else:
        tracker["multiple_faces_first_seen_at"] = None

    for item in normalized_events:
        etype = canonical_event_type(item.get("event_type"))
        if etype not in guarded_types:
            filtered_events.append(item)
            continue

        if etype == "multiple_faces":
            first_seen_at = tracker.get("multiple_faces_first_seen_at")
            if first_seen_at and (now - first_seen_at).total_seconds() >= 30:
                filtered_events.append(item)
            continue

        seen_count = sum(1 for frame_types in tracker["window"] if etype in frame_types)
        if seen_count >= 2:
            filtered_events.append(item)

    return filtered_events


def _serialize_stored_report(session: ExamSession, exam_title: str | None = None) -> dict:
    report = session.report_data or {}
    return {
        "id": f"session-{session.id}",
        "session_id": session.id,
        "exam_code": session.exam_code,
        "exam_title": exam_title or session.exam_code,
        "score_percent": float(report.get("score_percent") or 0.0),
        "integrity_band": report.get("integrity_band") or "Unknown",
        "stage": report.get("stage") or "Generated",
        "stored_at": (session.ended_at or session.started_at).isoformat() if (session.ended_at or session.started_at) else datetime.utcnow().isoformat(),
        "report": report,
    }

def _compute_session_result(db: Session, session: ExamSession) -> tuple[int, int, float]:
    exam = db.query(Exam).filter(Exam.code == session.exam_code).first()
    if not exam: return 0, 0, 0.0
    total = len(exam.question_links)
    correct = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id, ExamAnswer.is_correct.is_(True)).count()
    percent = round((correct / total) * 100, 2) if total else 0.0
    return correct, total, percent

def _tenant_for_exam(db: Session, exam_code: str) -> str:
    binding = db.query(TenantExamBinding).filter(TenantExamBinding.exam_code == exam_code).first()
    return binding.tenant_slug if binding else "default"


def _is_exam_public(exam: Exam) -> bool:
    return len(exam.enrollments) == 0


def _is_student_allowed_for_exam(exam: Exam, student_email: str) -> bool:
    if _is_exam_public(exam):
        return True
    return any(enrollment.student_email == student_email for enrollment in exam.enrollments)

@router.get("/available", response_model=list[AvailableExamOut])
def list_available_exams(current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    rows = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.created_at.desc()).all()
    return [
        AvailableExamOut(
            exam_code=e.code,
            title=e.title,
            question_count=len(e.question_links),
            is_public=_is_exam_public(e),
        )
        for e in rows
        if _is_student_allowed_for_exam(e, current_student.email)
    ]

@router.get("/{exam_code}/questions", response_model=list[ExamQuestionOut])
def get_exam_questions(exam_code: str, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.code == exam_code.strip().upper(), Exam.is_active.is_(True)).first()
    if not exam: raise HTTPException(status_code=404, detail="Assessment not found")
    if not _is_student_allowed_for_exam(exam, current_student.email):
        raise HTTPException(status_code=403, detail="You are not assigned to this exam")
    links = db.query(ExamQuestion, Question).join(Question, Question.id == ExamQuestion.question_id).filter(ExamQuestion.exam_id == exam.id).all()
    return [ExamQuestionOut(id=q.id, prompt=q.prompt, options=[q.option_a, q.option_b, q.option_c, q.option_d]) for _, q in links]

@router.post("/answer", response_model=AnswerSaveResponse)
def save_answer(payload: AnswerSaveRequest, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == payload.session_id, ExamSession.student_id == current_student.id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Exam Session not found")
        
    if session.status != "active":
        # Relaxed for now per user request to 'remove this one'
        logger.warning("Attempted answer save on inactive session %s (status=%s)", session.id, session.status)
        return AnswerSaveResponse(ok=False, answered_count=db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id).count())

    q = db.query(Question).filter(Question.id == payload.question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    try:
        ans = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id, ExamAnswer.question_id == payload.question_id).first()
        if not ans:
            ans = ExamAnswer(
                session_id=session.id, 
                question_id=payload.question_id, 
                selected_option=payload.selected_option.upper(), 
                is_correct=payload.selected_option.upper() == q.correct_option
            )
            db.add(ans)
        else:
            ans.selected_option = payload.selected_option.upper()
            ans.is_correct = payload.selected_option.upper() == q.correct_option
        
        db.commit()
    except IntegrityError:
        db.rollback()
        # If it's a duplicate, just return success since the answer is already there
        logger.warning("Duplicate answer save attempt ignored for session_id=%s, question_id=%s", session.id, payload.question_id)
    except Exception as e:
        db.rollback()
        logger.error("Failed to save answer: %s", str(e))
        raise HTTPException(status_code=500, detail="Database fault during neural sync")

    answered_count = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id).count()
    return AnswerSaveResponse(ok=True, answered_count=answered_count)

@router.get("/answers/{session_id}", response_model=SessionAnswersOut)
def get_saved_answers(session_id: int, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == session_id, ExamSession.student_id == current_student.id).first()
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    return SessionAnswersOut(session_id=session.id, answers={a.question_id: a.selected_option for a in session.answers})

@router.get("/dashboard", response_model=StudentDashboardOut)
def student_dashboard(current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    exams = db.query(Exam).filter(Exam.is_active.is_(True)).all()
    sessions = db.query(ExamSession).filter(ExamSession.student_id == current_student.id).order_by(ExamSession.started_at.desc()).all()
    attempted_codes = {s.exam_code for s in sessions}
    
    assigned = [
        AssignedExamOut(
            exam_code=e.code,
            title=e.title,
            question_count=len(e.question_links),
            has_attempt=e.code in attempted_codes,
            is_public=_is_exam_public(e),
        )
        for e in exams
        if _is_student_allowed_for_exam(e, current_student.email)
    ]
    attempted = []
    for s in sessions:
        exam = db.query(Exam).filter(Exam.code == s.exam_code).first()
        c, t, p = _compute_session_result(db, s)
        attempted.append(AttemptedExamOut(session_id=s.id, exam_code=s.exam_code, title=exam.title if exam else s.exam_code, status=s.status, started_at=s.started_at.isoformat(), ended_at=s.ended_at.isoformat() if s.ended_at else None, correct_answers=c, total_questions=t, score_percent=p))
    return StudentDashboardOut(assigned_exams=assigned, attempted_exams=attempted)

@router.post("/start", response_model=SessionResponse)
async def start_exam(payload: StartExamRequest, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    exam = db.query(Exam).filter(Exam.code == payload.exam_code.upper()).first()
    if not exam: raise HTTPException(status_code=404, detail="Exam target not found")
    if not _is_student_allowed_for_exam(exam, current_student.email):
        raise HTTPException(status_code=403, detail="You are not assigned to this exam")
    if not verify_password(payload.verification_code, exam.otp_hash):
         raise HTTPException(status_code=403, detail="Neural Validation OTP Mismatch")
    
    # ENHANCED AUTH: Verify Identity against Registered Profile
    if current_student.registered_face_image and len(current_student.registered_face_image) > 500:
        try:
            ai_res = await analyze_frame(payload.live_image_base64, reference_face_image_base64=current_student.registered_face_image)
            metrics = ai_res.get("metrics", {})
            sim = metrics.get("identity_similarity")
            if sim is not None and sim < 0.45: # Tolerant 0.45 for demo node
                 raise HTTPException(status_code=403, detail="Visual Identity Verification Failure. Biometric Mismatch.")
        except HTTPException: raise
        except Exception: pass # Allow if AI engine is down in demo mode
    
    session = ExamSession(
        student_id=current_student.id,
        exam_code=payload.exam_code.upper(),
        device_fingerprint=payload.device_fingerprint or "demo_terminal",
        registered_face_image=payload.live_image_base64,
        registered_id_image=payload.live_id_image_base64
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionResponse(session_id=session.id, status=session.status, risk_score=session.risk_score)

@router.post("/submit/{session_id}", response_model=SubmitExamResponse)
async def submit_exam(session_id: int, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == session_id, ExamSession.student_id == current_student.id).first()
    if not session: raise HTTPException(status_code=404, detail="Terminal Session Missing")
    if session.status == "active": session.status = "submitted"
    session.ended_at = datetime.utcnow()
    
    # ENHANCED REPORT FEAT: Locking Report into Profile Storage
    report = build_exam_report(db, session, current_student.email)
    session.report_data = report
    db.commit()
    
    c, t, p = _compute_session_result(db, session)
    return SubmitExamResponse(ok=True, status=session.status, correct_answers=c, total_questions=t, score_percent=p, report=ExamReportOut(**report))

@router.get("/report/{session_id}", response_model=ExamReportOut)
def get_exam_report(session_id: int, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == session_id, ExamSession.student_id == current_student.id).first()
    if not session: raise HTTPException(status_code=404, detail="Session not found")
    
    # Return from profile storage if available
    if session.report_data: return ExamReportOut(**session.report_data)
    
    report = build_exam_report(db, session, current_student.email)
    session.report_data = report
    db.commit()
    return ExamReportOut(**report)


@router.get("/reports")
def get_stored_reports(current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    sessions = (
        db.query(ExamSession)
        .filter(
            ExamSession.student_id == current_student.id,
            ExamSession.report_data.isnot(None),
        )
        .order_by(ExamSession.ended_at.desc(), ExamSession.started_at.desc())
        .all()
    )

    exam_codes = {session.exam_code for session in sessions}
    exam_title_map = {}
    if exam_codes:
        exams = db.query(Exam).filter(Exam.code.in_(exam_codes)).all()
        exam_title_map = {exam.code: exam.title for exam in exams}

    return [_serialize_stored_report(session, exam_title_map.get(session.exam_code)) for session in sessions]


@router.delete("/reports/{session_id}")
def delete_stored_report(session_id: int, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == session_id, ExamSession.student_id == current_student.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.report_data = None
    db.commit()
    return {"ok": True, "session_id": session_id}


@router.delete("/reports")
def clear_stored_reports(current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    sessions = (
        db.query(ExamSession)
        .filter(
            ExamSession.student_id == current_student.id,
            ExamSession.report_data.isnot(None),
        )
        .all()
    )

    cleared = 0
    for session in sessions:
        session.report_data = None
        cleared += 1

    db.commit()
    return {"ok": True, "cleared_count": cleared}

@router.get("/report/{session_id}/pdf")
def get_exam_report_pdf(session_id: int, current_student: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    session = db.query(ExamSession).filter(ExamSession.id == session_id, ExamSession.student_id == current_student.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    pdf_bytes = build_exam_report_pdf(db, session, current_student.email)
    return Response(content=pdf_bytes, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Integrity_Report_{session_id}.pdf"})

@router.post("/frame")
async def analyze_exam_frame(
    payload: FrameAnalyzeRequest,
    x_idempotency_key: str | None = Header(default=None),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if x_idempotency_key:
        cached = get_idempotent_response(
            db,
            scope="exam.frame",
            actor_id=str(current_student.id),
            idempotency_key=x_idempotency_key,
        )
        if cached is not None:
            return cached

    session = db.query(ExamSession).filter(ExamSession.id == payload.session_id, ExamSession.student_id == current_student.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Terminal Session Missing")
    if session.status not in {"active", "paused"}:
        response_payload = {
            "total_risk": session.risk_score,
            "session_status": session.status,
            "critical_violation_detected": should_auto_submit(session.risk_score),
            "ai_signals": [],
            "metrics": {"face_count": 0, "suspicious_score": 0.0},
            "policy_actions": [],
        }
        store_idempotent_response(db, "exam.frame", str(current_student.id), x_idempotency_key or "", response_payload)
        db.commit()
        return response_payload
    
    policy_actions = []
    try:
        ai_res = await analyze_frame(payload.image_base64, include_advanced=bool(payload.include_advanced))
        ai_metrics = ai_res.get("metrics", {}) or {}
        raw_events = ai_res.get("events", []) or []
        normalized_events = []
        for event in raw_events:
            confidence = event.get("confidence")
            if confidence is None:
                confidence = event.get("score")
            if confidence is None:
                confidence = 0.0
            normalized_event = dict(event)
            normalized_event["confidence"] = float(confidence)
            normalized_event["score"] = float(confidence)
            normalized_events.append(normalized_event)

        temporal_events = _evaluate_temporal_face_angle_drift(
            session.id,
            int(ai_metrics.get("face_count") or 0),
            ai_metrics,
            normalized_events,
        )
        if temporal_events:
            normalized_events.extend(temporal_events)

        normalized_events = _apply_signal_persistence_filter(session.id, normalized_events)
        
        new_violations = []
        for event in normalized_events:
            etype = canonical_event_type(event["event_type"])
            confidence = event.get("confidence")
            delta = get_risk_delta(etype)
            explainability = event.get("explainability") or build_explainability_statement(etype, confidence)
            v = Violation(
                session_id=session.id, 
                event_type=etype, 
                severity=get_severity(delta), 
                risk_delta=delta, 
                detail=f"{event.get('detail', '')} | {explainability}".strip(" |"),
                ai_confidence=confidence,
                policy_category=get_violation_category(etype),
                policy_action="signal",
                human_review_required=(confidence is not None and confidence < 0.70),
                explainability=explainability,
            )
            db.add(v)
            new_violations.append(v)
        
        db.commit()
        db.refresh(session)

        session.risk_score = calculate_decayed_risk(session.violations)
        
        # Broadcast violations to admin dashboard in real-time
        for v in new_violations:
            await ws_manager.broadcast("admin_violations", {
                "session_id": session.id,
                "event_type": v.event_type,
                "severity": v.severity,
                "risk_delta": v.risk_delta,
                "detail": v.detail,
                "student_email": current_student.email,
                "timestamp": v.created_at.isoformat()
            })
        
        for event in normalized_events:
            event_type = canonical_event_type(event["event_type"])
            actions = evaluate_workflow_rules(
                db,
                "default",
                session,
                event_type,
                signal_snapshot={
                    "confidence": event.get("confidence"),
                    "event": event,
                    "metrics": ai_metrics,
                },
            )
            if actions:
                policy_actions.extend(actions)
                for action in actions:
                    await ws_manager.broadcast("admin_violations", {
                        "session_id": session.id,
                        "event_type": f"workflow_{action['action']}",
                        "severity": "high" if action["action"] in ["terminate", "auto_submit", "flag_review"] else "medium",
                        "rule_name": action["rule_name"],
                        "student_email": current_student.email,
                        "timestamp": datetime.utcnow().isoformat(),
                    })

        signal_confidence = max((float(event.get("confidence") or 0.0) for event in normalized_events), default=0.0)
        if signal_confidence <= 0.0:
            signal_confidence = float(ai_metrics.get("suspicious_score") or 0.0)

        identity_similarity = ai_metrics.get("identity_similarity")
        identity_mismatch_detected = any(
            canonical_event_type(event.get("event_type")) == "face_mismatch"
            for event in normalized_events
        ) or any(
            canonical_event_type(event.get("event_type")) == "unknown_person_detected"
            for event in normalized_events
        ) or (
            identity_similarity is not None and float(identity_similarity) < 0.45
        )

        if identity_mismatch_detected:
            # session.status = "auto_submitted"
            # session.ended_at = datetime.utcnow()
            logger.info("Identity mismatch detected for session %s - auto-submit disabled", session.id)

        if session.status == "active" and should_auto_submit(session.risk_score, confidence=signal_confidence):
            # session.status = "auto_submitted"
            # session.ended_at = datetime.utcnow()
            logger.info("High risk detected for session %s - auto-submit disabled", session.id)
        db.commit()
        
        response_payload = {
            "total_risk": session.risk_score,
            "session_status": session.status,
            "critical_violation_detected": should_auto_submit(session.risk_score),
            "identity_mismatch_detected": identity_mismatch_detected,
            "ai_signals": normalized_events,
            "metrics": ai_metrics,
            "policy_actions": policy_actions,
        }
        store_idempotent_response(db, "exam.frame", str(current_student.id), x_idempotency_key or "", response_payload)
        db.commit()
        return response_payload
    except Exception:
        # Keep candidate flow resilient while still emitting diagnostics for operators.
        logger.exception("Frame analysis failed for session_id=%s", payload.session_id)
        response_payload = {
            "total_risk": session.risk_score,
            "critical_violation_detected": False,
            "ai_signals": [],
            "metrics": {"face_count": 0, "suspicious_score": 0.0},
            "policy_actions": [],
        }
        store_idempotent_response(db, "exam.frame", str(current_student.id), x_idempotency_key or "", response_payload)
        db.commit()
        return response_payload

@router.post("/event")
async def log_exam_event(
    payload: EventRequest,
    x_idempotency_key: str | None = Header(default=None),
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    if x_idempotency_key:
        cached = get_idempotent_response(
            db,
            scope="exam.event",
            actor_id=str(current_student.id),
            idempotency_key=x_idempotency_key,
        )
        if cached is not None:
            return cached

    session = db.query(ExamSession).filter(ExamSession.id == payload.session_id, ExamSession.student_id == current_student.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Terminal Session Missing")
    if session.status not in {"active", "paused"}:
        response_payload = {"total_risk": session.risk_score, "session_status": session.status}
        store_idempotent_response(db, "exam.event", str(current_student.id), x_idempotency_key or "", response_payload)
        db.commit()
        return response_payload
    
    delta = get_risk_delta(payload.event_type)
    event_type = canonical_event_type(payload.event_type)
    explainability = build_explainability_statement(event_type, None)
    v = Violation(
        session_id=session.id,
        event_type=event_type,
        severity=get_severity(delta),
        risk_delta=delta,
        detail=f"{payload.detail or get_reason(event_type)} | {explainability}",
        ai_confidence=None,
        policy_category=get_violation_category(event_type),
        policy_action="signal",
        human_review_required=False,
        explainability=explainability,
    )
    db.add(v)
    session.risk_score = normalize_risk(session.risk_score + delta)
    if event_type == "face_mismatch" or event_type == "unknown_person_detected":
        # session.status = "auto_submitted"
        # session.ended_at = datetime.utcnow()
        logger.info("Identity violation for session %s - auto-submit disabled", session.id)
    elif should_auto_submit(session.risk_score):
        # session.status = "auto_submitted"
        # session.ended_at = datetime.utcnow()
        logger.info("Critical risk for session %s - auto-submit disabled", session.id)
    db.commit()
    db.refresh(session)
    
    actions = evaluate_workflow_rules(db, "default", session, event_type, signal_snapshot={"confidence": None, "event": {"event_type": event_type}})
    for action in actions:
        await ws_manager.broadcast("admin_violations", {
            "session_id": session.id,
            "event_type": f"workflow_{action['action']}",
            "severity": "high" if action["action"] in ["terminate", "auto_submit", "flag_review"] else "medium",
            "rule_name": action["rule_name"],
            "student_email": current_student.email,
            "timestamp": datetime.utcnow().isoformat()
        })
    db.commit()

    # Broadcast violation to admin dashboard
    broadcast_data = {
        "session_id": session.id,
        "event_type": v.event_type,
        "severity": v.severity,
        "risk_delta": v.risk_delta,
        "detail": v.detail,
        "student_email": current_student.email,
        "timestamp": v.created_at.isoformat()
    }
    await ws_manager.broadcast("admin_violations", broadcast_data)


    
    response_payload = {
        "total_risk": session.risk_score,
        "session_status": session.status,
        "identity_mismatch_detected": event_type in {"face_mismatch", "unknown_person_detected"},
    }
    store_idempotent_response(db, "exam.event", str(current_student.id), x_idempotency_key or "", response_payload)
    db.commit()
    return response_payload


@router.post("/evidence")
async def upload_evidence(
    payload: dict,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Receive client-side captured evidence screenshots and proctoring metrics.

    The local proctor engine (MediaPipe + COCO-SSD) captures evidence frames
    during the exam and uploads them in bulk when the exam is submitted.
    """
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")

    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == session_id, ExamSession.student_id == current_student.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    shots = payload.get("evidence_shots", [])
    metrics = payload.get("metrics", {})
    saved = 0

    for idx, shot in enumerate(shots[:60]):
        image_data = shot.get("image", "")
        reason = shot.get("reason", "unknown")
        timestamp = shot.get("time")

        if not image_data or len(image_data) < 100:
            continue

        frame = EvidenceFrame(
            session_id=session.id,
            violation_id=None,
            frame_base64=image_data,
            timestamp=datetime.utcfromtimestamp(timestamp / 1000) if timestamp else datetime.utcnow(),
            frame_index=idx,
            ai_analysis={"reason": reason, "source": "local_proctor_engine"},
        )
        db.add(frame)
        saved += 1

    # Store client-side metrics into report_data if report exists
    if metrics and session.report_data:
        report = dict(session.report_data)
        report["client_proctor_metrics"] = metrics
        report["evidence_count"] = saved
        session.report_data = report
    elif metrics:
        session.report_data = {
            "client_proctor_metrics": metrics,
            "evidence_count": saved,
        }

    db.commit()
    return {"ok": True, "saved_evidence_frames": saved}


@router.get("/evidence/{session_id}")
def get_student_evidence(
    session_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Retrieve captured evidence frames for a student's own session."""
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == session_id, ExamSession.student_id == current_student.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    frames = (
        db.query(EvidenceFrame)
        .filter(EvidenceFrame.session_id == session_id)
        .order_by(EvidenceFrame.timestamp.asc())
        .all()
    )

    return {
        "session_id": session_id,
        "evidence_count": len(frames),
        "frames": [
            {
                "id": f.id,
                "reason": (f.ai_analysis or {}).get("reason", "unknown"),
                "timestamp": f.timestamp.isoformat() if f.timestamp else None,
                "image": f.frame_base64,
            }
            for f in frames
        ],
    }
