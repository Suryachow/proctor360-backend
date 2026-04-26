from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_student
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import Exam, ExamAnswer, ExamEnrollment, ExamSession, Student, Violation

router = APIRouter(prefix="/compliance", tags=["compliance"])


@router.get("/modes")
def compliance_modes():
    modes = [item.strip() for item in settings.compliance_mode.split(",") if item.strip()]
    return {"modes": modes}


@router.get("/my-data")
def download_my_data(
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    sessions = (
        db.query(ExamSession)
        .filter(ExamSession.student_id == current_student.id)
        .order_by(ExamSession.started_at.desc())
        .all()
    )

    assigned = (
        db.query(ExamEnrollment, Exam)
        .join(Exam, Exam.id == ExamEnrollment.exam_id)
        .filter(ExamEnrollment.student_email == current_student.email)
        .all()
    )

    session_payload = []
    for session in sessions:
        violations = (
            db.query(Violation)
            .filter(Violation.session_id == session.id)
            .order_by(Violation.created_at.asc())
            .all()
        )
        answers = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id).all()

        session_payload.append(
            {
                "session_id": session.id,
                "exam_code": session.exam_code,
                "status": session.status,
                "risk_score": session.risk_score,
                "started_at": session.started_at,
                "ended_at": session.ended_at,
                "violations": [
                    {
                        "event_type": v.event_type,
                        "severity": v.severity,
                        "detail": v.detail,
                        "risk_delta": v.risk_delta,
                        "created_at": v.created_at,
                    }
                    for v in violations
                ],
                "answers": [
                    {
                        "question_id": answer.question_id,
                        "selected_option": answer.selected_option,
                        "is_correct": answer.is_correct,
                        "updated_at": answer.updated_at,
                    }
                    for answer in answers
                ],
            }
        )

    return {
        "student": {
            "email": current_student.email,
            "is_active": current_student.is_active,
        },
        "assigned_exams": [
            {
                "exam_code": exam.code,
                "title": exam.title,
                "is_active": exam.is_active,
                "created_at": exam.created_at,
            }
            for _, exam in assigned
        ],
        "sessions": session_payload,
        "compliance": {
            "export_type": "GDPR-subject-access-request",
            "generated_by": "Proctor360 API",
        },
    }
