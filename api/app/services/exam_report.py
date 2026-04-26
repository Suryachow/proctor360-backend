from collections import defaultdict
from typing import Any
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.entities import Exam, ExamAnswer, ExamQuestion, ExamSession, EvidenceFrame, Question, Violation
from app.services.violation_engine import classify_risk_level

def build_exam_report(db: Session, session: ExamSession, student_email: str) -> dict[str, Any]:
    exam = db.query(Exam).filter(Exam.code == session.exam_code).first()
    if not exam:
        return {
            "stage": "Diagnostic",
            "overall_summary": "Session data is incomplete.",
            "integrity_band": "Unknown",
            "strengths": [],
            "improvement_areas": [],
            "recommended_actions": [],
            "topic_breakdown": [],
            "score_percent": 0.0
        }

    # 📊 1. GATHER DATA
    links = db.query(ExamQuestion).filter(ExamQuestion.exam_id == exam.id).all()
    question_ids = [link.question_id for link in links]
    questions = db.query(Question).filter(Question.id.in_(question_ids)).all() if question_ids else []
    
    answers = db.query(ExamAnswer).filter(ExamAnswer.session_id == session.id).all()
    answer_map = {a.question_id: a for a in answers}
    
    violations = db.query(Violation).filter(Violation.session_id == session.id).all()
    violation_counts = defaultdict(int)
    for v in violations:
        violation_counts[v.event_type] += 1

    # 📈 2. CALCULATE METRICS
    total_q = len(question_ids)
    correct_all = sum(1 for a in answers if a.is_correct)
    score_percent = round((correct_all / total_q) * 100, 2) if total_q else 0.0

    # 🧠 3. TOPIC BREAKDOWN
    topic_map = defaultdict(lambda: {"correct": 0, "incorrect": 0, "unanswered": 0, "total": 0})
    for q in questions:
        topic_name = q.topic.title()
        topic_map[topic_name]["total"] += 1
        ans = answer_map.get(q.id)
        if not ans:
            topic_map[topic_name]["unanswered"] += 1
        elif ans.is_correct:
            topic_map[topic_name]["correct"] += 1
        else:
            topic_map[topic_name]["incorrect"] += 1

    topic_breakdown = []
    for topic_name, m in topic_map.items():
        topic_breakdown.append({
            "topic": topic_name,
            "correct": m["correct"],
            "incorrect": m["incorrect"],
            "unanswered": m["unanswered"],
            "mastery_percent": round((m["correct"] / m["total"]) * 100, 2) if m["total"] else 0.0
        })

    # 🛡️ 4. INTEGRITY PROVISO
    phone_vios = violation_counts.get("phone_detected", 0)
    risk = session.risk_score
    if risk > 80 or phone_vios > 3:
        integrity_band = "Critical Risk"
    elif risk > 40:
        integrity_band = "Moderate Concern"
    else:
        integrity_band = "Highly Reliable"

    risk_level = classify_risk_level(risk)

    # 🏁 5. FINALIZE
    summary = f"Candidate achieved {score_percent}% in '{exam.title}'. "
    if integrity_band == "Critical Risk":
        summary += "AI detected high-confidence integrity anomalies; the risk engine escalated the session for human validation."
    else:
        summary += "Assessment behavior remained within the enterprise policy envelope and did not require manual escalation."

    # 📸 6. EVIDENCE GALLERY
    evidence_frames = (
        db.query(EvidenceFrame)
        .filter(EvidenceFrame.session_id == session.id)
        .order_by(EvidenceFrame.timestamp.asc())
        .all()
    )

    evidence_summary = []
    for ef in evidence_frames:
        reason = (ef.ai_analysis or {}).get("reason", "unknown")
        evidence_summary.append({
            "id": ef.id,
            "reason": reason,
            "timestamp": ef.timestamp.isoformat() if ef.timestamp else None,
            "frame_index": ef.frame_index,
        })

    # Get client-side credibility score if stored
    client_metrics = {}
    if session.report_data and isinstance(session.report_data, dict):
        client_metrics = session.report_data.get("client_proctor_metrics", {})

    credibility_score = client_metrics.get("credibilityScore", None)

    return {
        "stage": "Audit Complete" if integrity_band != "Critical Risk" else "Integrity Flag",
        "overall_summary": f"{summary} Risk level: {risk_level.replace('_', ' ').title()}.",
        "integrity_band": integrity_band,
        "strengths": [t["topic"] for t in topic_breakdown if t["mastery_percent"] >= 70][:3],
        "improvement_areas": [t["topic"] for t in topic_breakdown if t["mastery_percent"] < 50][:3],
        "recommended_actions": [
            "Review conceptual basics in weak topics." if score_percent < 60 else "Advance to higher complexity tiers.",
            "Maintain proctoring compliance; unauthorized device patterns detected." if phone_vios > 0 else "Excellent focus retention noted.",
            "Human proctor review required before finalizing punitive action." if integrity_band == "Critical Risk" else "No human validation needed beyond routine audit."
        ],
        "topic_breakdown": topic_breakdown,
        "score_percent": score_percent,
        "evidence_summary": evidence_summary,
        "evidence_count": len(evidence_frames),
        "credibility_score": credibility_score,
        "client_proctor_metrics": client_metrics if client_metrics else None,
    }
