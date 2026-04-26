import secrets
import csv
import hashlib
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.core.security import hash_password
from app.models.entities import AuditLog, Certificate, Exam, ExamEnrollment, ExamAnswer, EvidenceFrame, ExamQuestion, ExamSession, Question, Student, Violation
from app.schemas.admin import (
    AutoGenerateExamRequest,
    AutoGenerateExamResponse,
    BulkQuestionUploadRequest,
    ExamCreateRequest,
    ExamCreateResponse,
    ProctorExamReportOut,
    ProctorIncidentSnipOut,
)
from app.services.ai_question_agent import generate_questions_with_ai_agent

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


@router.post("/questions/bulk")
def upload_questions(payload: BulkQuestionUploadRequest, db: Session = Depends(get_db)):
    if not payload.questions:
        raise HTTPException(status_code=400, detail="At least one question is required")

    created = []
    for q in payload.questions:
        question = Question(
            prompt=q.prompt.strip(),
            option_a=q.option_a.strip(),
            option_b=q.option_b.strip(),
            option_c=q.option_c.strip(),
            option_d=q.option_d.strip(),
            correct_option=q.correct_option.upper(),
            topic=q.topic.strip() or "general",
        )
        db.add(question)
        created.append(question)

    db.commit()
    for question in created:
        db.refresh(question)

    return {
        "ok": True,
        "created_count": len(created),
        "question_ids": [question.id for question in created],
    }


@router.post("/questions/upload-csv")
async def upload_questions_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    content = (await file.read()).decode("utf-8-sig")
    reader = csv.DictReader(StringIO(content))
    required_columns = {"prompt", "option_a", "option_b", "option_c", "option_d", "correct_option"}
    if not reader.fieldnames or not required_columns.issubset({name.strip() for name in reader.fieldnames}):
        raise HTTPException(
            status_code=400,
            detail="CSV must include prompt, option_a, option_b, option_c, option_d, correct_option columns",
        )

    created = []
    for row in reader:
        prompt = (row.get("prompt") or "").strip()
        option_a = (row.get("option_a") or "").strip()
        option_b = (row.get("option_b") or "").strip()
        option_c = (row.get("option_c") or "").strip()
        option_d = (row.get("option_d") or "").strip()
        correct_option = (row.get("correct_option") or "").strip().upper()
        topic = (row.get("topic") or "general").strip() or "general"

        if not prompt or not option_a or not option_b or not option_c or not option_d:
            raise HTTPException(status_code=400, detail="CSV rows cannot have empty prompt/options")
        if correct_option not in {"A", "B", "C", "D"}:
            raise HTTPException(status_code=400, detail="correct_option must be one of A/B/C/D")

        question = Question(
            prompt=prompt,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            correct_option=correct_option,
            topic=topic,
        )
        db.add(question)
        created.append(question)

    if not created:
        raise HTTPException(status_code=400, detail="CSV has no data rows")

    db.commit()
    for question in created:
        db.refresh(question)

    return {
        "ok": True,
        "created_count": len(created),
        "question_ids": [question.id for question in created],
    }


@router.get("/questions")
def list_questions(db: Session = Depends(get_db)):
    questions = db.query(Question).order_by(Question.created_at.desc()).all()
    return [
        {
            "id": q.id,
            "prompt": q.prompt,
            "topic": q.topic,
            "correct_option": q.correct_option,
        }
        for q in questions
    ]


@router.post("/exams", response_model=ExamCreateResponse)
def create_exam(payload: ExamCreateRequest, db: Session = Depends(get_db)):
    import traceback
    try:
        code = payload.code.strip().upper()
        if not code:
            raise HTTPException(status_code=400, detail="Exam code is required")

        existing_exam = db.query(Exam).filter(Exam.code == code).first()
        if existing_exam:
            raise HTTPException(status_code=400, detail="Exam code already exists")

        question_ids = sorted(set(payload.question_ids))
        if not question_ids:
            raise HTTPException(status_code=400, detail="At least one question must be selected")

        questions = db.query(Question).filter(Question.id.in_(question_ids)).all()
        existing_question_ids = {q.id for q in questions}
        missing = [qid for qid in question_ids if qid not in existing_question_ids]
        if missing:
            raise HTTPException(status_code=400, detail=f"Question IDs not found: {missing}")

        normalized_emails = sorted(
            {
                email.strip().lower()
                for email in payload.student_emails
                if email and email.strip()
            }
        )

        verification_code = f"{secrets.randbelow(900000) + 100000}"
        exam = Exam(
            code=code,
            title=payload.title.strip(),
            otp_hash=hash_password(verification_code),
            otp_plain=verification_code,
            is_active=True,
        )
        db.add(exam)
        db.flush()

        for question_id in question_ids:
            db.add(ExamQuestion(exam_id=exam.id, question_id=question_id))

        for email in normalized_emails:
            db.add(ExamEnrollment(exam_id=exam.id, student_email=email))

        db.commit()

        return ExamCreateResponse(
            exam_code=exam.code,
            title=exam.title,
            verification_code=verification_code,
            question_count=len(question_ids),
            assigned_students=len(normalized_emails),
            is_public=len(normalized_emails) == 0,
        )
    except HTTPException:
        raise
    except Exception as e:
        print("[ERROR] Exception in create_exam:", str(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.post("/exams/auto-generate", response_model=AutoGenerateExamResponse)
async def auto_generate_exam(payload: AutoGenerateExamRequest, db: Session = Depends(get_db)):
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    normalized_emails = sorted(
        {
            email.strip().lower()
            for email in payload.student_emails
            if email and email.strip()
        }
    )

    existing_prompt_keys = {
        " ".join((prompt or "").strip().lower().split())
        for (prompt,) in db.query(Question.prompt).all()
    }

    try:
        selected_questions = await generate_questions_with_ai_agent(
            topic=topic,
            difficulty=payload.difficulty,
            question_count=payload.question_count,
            image_question_count=payload.image_question_count,
            diagram_question_count=payload.diagram_question_count,
            admin_request=payload.admin_request,
            existing_prompt_keys=existing_prompt_keys,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    created_questions = []
    for q in selected_questions[: payload.question_count]:
        question = Question(
            prompt=q["prompt"].strip(),
            option_a=q["option_a"].strip(),
            option_b=q["option_b"].strip(),
            option_c=q["option_c"].strip(),
            option_d=q["option_d"].strip(),
            correct_option=q["correct_option"].upper(),
            topic=q["topic"].strip() or topic.lower(),
        )
        db.add(question)
        created_questions.append(question)

    code_candidate = (payload.code or "").strip().upper()
    code = code_candidate if code_candidate else f"{topic[:6].upper()}-{payload.difficulty[:1].upper()}{secrets.randbelow(900) + 100}"

    existing_exam = db.query(Exam).filter(Exam.code == code).first()
    if existing_exam:
        raise HTTPException(status_code=400, detail="Exam code already exists")

    title_candidate = (payload.title or "").strip()
    title = title_candidate if title_candidate else f"{topic.title()} {payload.difficulty.title()} Assessment"

    verification_code = f"{secrets.randbelow(900000) + 100000}"
    exam = Exam(
        code=code,
        title=title,
        otp_hash=hash_password(verification_code),
        otp_plain=verification_code,
        is_active=True,
    )
    db.add(exam)
    db.flush()

    question_ids = []
    image_question_count = 0
    diagram_question_count = 0
    for question in created_questions:
        db.flush()
        question_ids.append(question.id)
        if "[[IMAGE_URL]]" in question.prompt:
            image_question_count += 1
        if "[[DIAGRAM_MERMAID]]" in question.prompt:
            diagram_question_count += 1
        db.add(ExamQuestion(exam_id=exam.id, question_id=question.id))

    for email in normalized_emails:
        db.add(ExamEnrollment(exam_id=exam.id, student_email=email))

    db.commit()

    return AutoGenerateExamResponse(
        exam_code=exam.code,
        title=exam.title,
        verification_code=verification_code,
        question_count=len(question_ids),
        assigned_students=len(normalized_emails),
        is_public=len(normalized_emails) == 0,
        topic=topic,
        difficulty=payload.difficulty,
        image_question_count=image_question_count,
        diagram_question_count=diagram_question_count,
        generated_question_ids=question_ids,
    )


@router.get("/exams")
def list_exams(db: Session = Depends(get_db)):
    try:
        exams = db.query(Exam).order_by(Exam.created_at.desc()).all()
        return [
            {
                "exam_code": exam.code,
                "title": exam.title,
                "verification_code": exam.otp_plain or "",
                "is_active": exam.is_active,
                "is_public": len(exam.enrollments) == 0,
                "question_count": len(exam.question_links),
                "assigned_students": len(exam.enrollments),
                "created_at": exam.created_at,
            }
            for exam in exams
        ]
    except Exception as e:
        import traceback
        print("[ERROR] Exception in list_exams:", str(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


@router.post("/exams/{exam_code}/terminate")
def terminate_exam(exam_code: str, db: Session = Depends(get_db)):
    normalized_code = exam_code.strip().upper()
    exam = db.query(Exam).filter(Exam.code == normalized_code).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    if not exam.is_active:
        return {"ok": True, "exam_code": exam.code, "is_active": False, "terminated_sessions": 0}

    exam.is_active = False

    active_sessions = (
        db.query(ExamSession)
        .filter(ExamSession.exam_code == exam.code, ExamSession.status.in_(["active", "paused"]))
        .all()
    )
    for session in active_sessions:
        session.status = "terminated"
        session.ended_at = datetime.utcnow()

    db.commit()
    return {
        "ok": True,
        "exam_code": exam.code,
        "is_active": exam.is_active,
        "terminated_sessions": len(active_sessions),
    }


@router.get("/students")
def list_students(db: Session = Depends(get_db)):
    rows = (
        db.query(Student, func.count(ExamSession.id).label("session_count"))
        .outerjoin(ExamSession, ExamSession.student_id == Student.id)
        .group_by(Student.id)
        .order_by(Student.id.desc())
        .all()
    )

    return [
        {
            "id": student.id,
            "email": student.email,
            "device_hash": student.device_hash,
            "is_active": student.is_active,
            "has_registered_face": bool(student.registered_face_image),
            "session_count": int(session_count or 0),
        }
        for student, session_count in rows
    ]


@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    rows = (
        db.query(ExamSession, Student)
        .join(Student, ExamSession.student_id == Student.id)
        .order_by(ExamSession.started_at.desc())
        .all()
    )
    return [
        {
            "session_id": session.id,
            "student_email": student.email,
            "exam_code": session.exam_code,
            "status": session.status,
            "risk_score": session.risk_score,
        }
        for session, student in rows
    ]


@router.get("/violations/{session_id}")
def list_violations(session_id: int, db: Session = Depends(get_db)):
    violations = (
        db.query(Violation)
        .filter(Violation.session_id == session_id)
        .order_by(Violation.created_at.desc())
        .all()
    )
    return [
        {
            "id": v.id,
            "session_id": v.session_id,
            "event_type": v.event_type,
            "severity": v.severity,
            "risk_delta": v.risk_delta,
            "detail": v.detail,
            "ai_confidence": v.ai_confidence,
            "policy_category": v.policy_category,
            "policy_action": v.policy_action,
            "human_review_required": v.human_review_required,
            "explainability": v.explainability,
            "created_at": v.created_at,
        }
        for v in violations
    ]


@router.post("/action/{session_id}/{action}")
async def session_action(session_id: int, action: str, db: Session = Depends(get_db)):
    """Admin action: warn, pause, or terminate a session. Broadcasts to admin dashboard in real-time."""
    from app.services.ws_manager import ws_manager
    
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if action not in {"warn", "pause", "terminate"}:
        raise HTTPException(status_code=400, detail="Unsupported action")

    if action == "pause":
        session.status = "paused"
    elif action == "terminate":
        session.status = "terminated"
        session.ended_at = datetime.utcnow()

    violation = Violation(
        session_id=session.id,
        event_type=f"admin_{action}",
        severity="medium" if action != "terminate" else "high",
        risk_delta=10.0 if action != "terminate" else 40.0,
        detail="Manual admin intervention",
        ai_confidence=None,
        policy_category="workflow",
        policy_action=action,
        human_review_required=(action != "terminate"),
        explainability=f"Human proctor performed {action} on session {session.id}.",
    )
    session.risk_score += violation.risk_delta

    db.add(violation)
    db.commit()
    
    # Broadcast admin action to all listeners (including the student's client)
    student = db.query(Student).filter(Student.id == session.student_id).first()
    await ws_manager.broadcast("admin_violations", {
        "session_id": session.id,
        "event_type": f"admin_{action}",
        "severity": violation.severity,
        "risk_delta": violation.risk_delta,
        "detail": f"Proctor {action}: {violation.detail}",
        "student_email": student.email if student else "unknown",
        "timestamp": violation.created_at.isoformat()
    })
    
    return {"ok": True, "status": session.status, "risk_score": session.risk_score}


@router.get("/proctor-report/{session_id}", response_model=ProctorExamReportOut)
def get_proctor_report(session_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(ExamSession, Student)
        .join(Student, ExamSession.student_id == Student.id)
        .filter(ExamSession.id == session_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    session, student = row
    violations = (
        db.query(Violation)
        .filter(Violation.session_id == session.id)
        .order_by(Violation.created_at.desc())
        .all()
    )

    unusual_events = {
        "multiple_faces",
        "unknown_person_detected",
        "phone_detected",
        "second_screen_detected",
        "object_book_detected",
    }

    snips = [
        ProctorIncidentSnipOut(
            timestamp=v.created_at,
            event_type=v.event_type,
            severity=v.severity,
            detail=v.detail,
            ai_confidence=v.ai_confidence,
            policy_category=v.policy_category,
            policy_action=v.policy_action,
            human_review_required=v.human_review_required,
            explainability=v.explainability,
        )
        for v in violations
        if v.event_type in unusual_events
    ][:12]

    if snips:
        recommendation = "Unusual multi-entity behavior detected. Review incident snips and verify exam integrity evidence."
    else:
        recommendation = "No unusual multi-entity behavior was detected beyond single-student patterns."

    return ProctorExamReportOut(
        session_id=session.id,
        exam_code=session.exam_code,
        student_email=student.email,
        status=session.status,
        risk_score=session.risk_score,
        unusual_activity_detected=len(snips) > 0,
        incident_snips=snips,
        recommendation=recommendation,
    )


@router.get("/audit/logs")
def get_audit_logs(limit: int = 200, db: Session = Depends(get_db)):
    capped_limit = 200 if limit > 200 else max(limit, 1)
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(capped_limit).all()
    return [
        {
            "id": row.id,
            "actor_email": row.actor_email,
            "actor_role": row.actor_role,
            "action": row.action,
            "resource": row.resource,
            "status_code": row.status_code,
            "ip_address": row.ip_address,
            "user_agent": row.user_agent,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.get("/analytics/global")
def get_global_analytics(db: Session = Depends(get_db)):
    """Get platform-wide analytics: exam completion rates, integrity scores, intervention frequency."""
    total_sessions = db.query(ExamSession).count()
    
    submitted = db.query(ExamSession).filter(ExamSession.status.in_(["submitted", "auto_submitted"])).count()
    success_rate = round((submitted / total_sessions) * 100, 1) if total_sessions > 0 else 0.0
    
    avg_risk = db.query(func.avg(ExamSession.risk_score)).scalar() or 0.0
    integrity_benchmark = round(100.0 - min(avg_risk, 100.0), 1)
    
    violation_count = db.query(Violation).count()
    critical_count = db.query(Violation).filter(Violation.severity == "high").count()
    intervention_rate = round((critical_count / total_sessions) * 100, 1) if total_sessions > 0 else 0.0
    
    # Cohort breakdown by exam
    exam_stats = []
    exams = db.query(Exam).filter(Exam.is_active.is_(True)).all()
    for exam in exams:
        exam_sessions = db.query(ExamSession).filter(ExamSession.exam_code == exam.code).count()
        exam_passed = db.query(ExamSession).filter(
            ExamSession.exam_code == exam.code,
            ExamSession.status.in_(["submitted", "auto_submitted"])
        ).count()
        pass_rate = round((exam_passed / exam_sessions) * 100, 1) if exam_sessions > 0 else 0.0
        exam_stats.append({
            "exam_code": exam.code,
            "exam_title": exam.title,
            "total_candidates": exam_sessions,
            "pass_rate": pass_rate
        })
    
    return {
        "success_rate": success_rate,
        "integrity_benchmark": integrity_benchmark,
        "intervention_frequency": intervention_rate,
        "total_sessions": total_sessions,
        "total_violations": violation_count,
        "critical_violations": critical_count,
        "avg_risk_score": round(avg_risk, 2),
        "exam_cohort_stats": exam_stats
    }


@router.get("/evidence/{session_id}")
def get_session_evidence(session_id: int, db: Session = Depends(get_db)):
    """Get violation timeline and captured evidence frames for a session."""
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    violations = db.query(Violation).filter(Violation.session_id == session_id).order_by(Violation.created_at.asc()).all()
    frames = db.query(EvidenceFrame).filter(EvidenceFrame.session_id == session_id).order_by(EvidenceFrame.timestamp.asc()).all()
    
    violation_timeline = [
        {
            "id": v.id,
            "timestamp": v.created_at.isoformat(),
            "event_type": v.event_type,
            "severity": v.severity,
            "detail": v.detail,
            "risk_delta": v.risk_delta
        }
        for v in violations
    ]
    
    evidence_frames = [
        {
            "id": f.id,
            "violation_id": f.violation_id,
            "timestamp": f.timestamp.isoformat(),
            "frame_index": f.frame_index,
            "ai_analysis": f.ai_analysis or {}
        }
        for f in frames
    ]
    
    student = db.query(Student).filter(Student.id == session.student_id).first()

    return {
        "session_id": session_id,
        "student_email": student.email if student else "unknown",
        "exam_code": session.exam_code,
        "total_violations": len(violations),
        "total_frames": len(frames),
        "violation_timeline": violation_timeline,
        "evidence_frames": evidence_frames
    }


@router.post("/certificates/issue")
def issue_certificate(payload: dict, db: Session = Depends(get_db)):
    """Issue a completion certificate for a passing exam session."""
    from app.schemas.exam import ExamReportOut
    from app.services.exam_report import build_exam_report
    
    student_email = payload.get("student_email", "").strip().lower()
    session_id = payload.get("session_id")
    
    # Find session by email if session_id not provided
    if not session_id:
        # Get most recent submitted session for this student
        student = db.query(Student).filter(Student.email == student_email).first()
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        session = db.query(ExamSession).filter(
            ExamSession.student_id == student.id,
            ExamSession.status.in_(["submitted", "auto_submitted"])
        ).order_by(ExamSession.ended_at.desc()).first()
    else:
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    student = db.query(Student).filter(Student.id == session.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Check if certificate already issued
    existing = db.query(Certificate).filter(Certificate.session_id == session.id).first()
    if existing:
        return {"ok": False, "message": "Certificate already issued for this session", "certificate_id": existing.id}
    
    # Get exam score
    correct_count = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id, ExamAnswer.is_correct.is_(True)).count()
    total_questions = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id).count()
    score_percent = round((correct_count / total_questions) * 100, 1) if total_questions > 0 else 0.0
    
    # Determine integrity band from risk_score and violations
    high_risk_violations = db.query(Violation).filter(
        Violation.session_id == session.id,
        Violation.event_type.in_(["phone_detected", "multiple_faces", "unknown_person_detected", "device_fingerprint_mismatch"])
    ).count()
    
    if session.risk_score >= 80.0 or high_risk_violations >= 3:
        integrity_band = "Critical Risk"
    elif session.risk_score >= 40.0:
        integrity_band = "Moderate"
    else:
        integrity_band = "Highly Reliable"
    
    # Generate certificate with tamper-proof hash
    cert_data = f"{student.email}:{session.id}:{score_percent}:{session.exam_code}"
    verification_hash = hashlib.sha256(cert_data.encode()).hexdigest()
    
    certificate = Certificate(
        session_id=session.id,
        student_email=student.email,
        exam_code=session.exam_code,
        score_percent=score_percent,
        integrity_band=integrity_band,
        verification_hash=verification_hash,
        expires_at=None
    )
    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    
    return {
        "ok": True,
        "certificate_id": certificate.id,
        "student_email": student.email,
        "exam_code": session.exam_code,
        "score_percent": score_percent,
        "integrity_band": integrity_band,
        "verification_hash": verification_hash,
        "issued_at": certificate.issued_at.isoformat()
    }
