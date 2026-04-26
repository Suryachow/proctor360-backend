from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.entities import ExamSession, Violation, WorkflowRule
from app.services.violation_engine import (
    build_explainability_statement,
    canonical_event_type,
    classify_risk_level,
    get_violation_category,
)


def evaluate_workflow_rules(
    db: Session,
    tenant_slug: str,
    session: ExamSession,
    latest_event_type: str,
    signal_snapshot: dict | None = None,
) -> list[dict]:
    signal_snapshot = signal_snapshot or {}
    latest_event_type = canonical_event_type(latest_event_type)
    confidence = signal_snapshot.get("confidence")

    rules = (
        db.query(WorkflowRule)
        .filter(WorkflowRule.tenant_slug == tenant_slug, WorkflowRule.is_active.is_(True))
        .all()
    )

    actions = []

    # Enterprise default policy when no explicit tenant rules are present.
    event_counts = Counter(canonical_event_type(v.event_type) for v in session.violations)
    recent_cutoff = datetime.utcnow() - timedelta(seconds=30)
    recent_workflow_warn = (
        db.query(Violation)
        .filter(
            Violation.session_id == session.id,
            Violation.event_type == "workflow_warn",
            Violation.created_at >= recent_cutoff,
        )
        .count()
    )

    policy_action = None
    policy_detail = None
    policy_severity = "medium"
    policy_warn_recorded = False

    category = get_violation_category(latest_event_type)
    risk_level = classify_risk_level(session.risk_score)

    if category == "critical":
        if confidence is not None and confidence < 0.70:
            policy_action = "flag_review"
            policy_severity = "medium"
            policy_detail = f"Low-confidence critical signal ({confidence:.2f}); routed to human review."
            # session.status = "paused" # Auto-pause disabled per user request
        else:
            if latest_event_type == "multiple_faces":
                policy_action = "pause"
                policy_severity = "high"
                policy_detail = build_explainability_statement(latest_event_type, confidence, event_counts[latest_event_type])
                # session.status = "paused" # Auto-pause disabled per user request
            elif latest_event_type in {"phone_detected", "face_mismatch", "screen_sharing_detected", "remote_desktop_detected", "external_person_interaction"}:
                policy_action = "terminate"
                policy_severity = "high"
                policy_detail = build_explainability_statement(latest_event_type, confidence, event_counts[latest_event_type])
                # session.status = "terminated" # Auto-termination disabled per user request
                # session.ended_at = datetime.utcnow()
            else:
                policy_action = "pause"
                policy_severity = "high"
                policy_detail = build_explainability_statement(latest_event_type, confidence, event_counts[latest_event_type])
                # session.status = "paused" # Auto-pause disabled per user request
    elif category == "major":
        repeated = event_counts[latest_event_type]
        if latest_event_type == "tab_switch" and repeated > 5:
            policy_action = "warn"
            policy_severity = "medium"
            policy_detail = f"Repeated tab switching detected ({repeated} times)."
        elif latest_event_type == "fullscreen_exit" and repeated > 2:
            policy_action = "warn"
            policy_severity = "medium"
            policy_detail = f"Repeated fullscreen exits detected ({repeated} times)."
        elif latest_event_type in {"looking_away", "gaze_deviation"} and repeated >= 4:
            policy_action = "flag_review"
            policy_severity = "high"
            policy_detail = f"Sustained attention deviation detected ({repeated} events in current session)."
        elif latest_event_type in {"multiple_voices", "copy_paste_attempt", "looking_away", "gaze_deviation", "whisper_detected"}:
            policy_action = "warn"
            policy_severity = "medium"
            policy_detail = build_explainability_statement(latest_event_type, confidence, repeated)

        if policy_action == "warn" and recent_workflow_warn > 0:
            policy_action = None
            policy_detail = None
    elif category == "minor":
        if latest_event_type == "temporary_face_loss" and event_counts[latest_event_type] <= 1:
            policy_action = "log"
            policy_detail = "Temporary face loss remains within grace window."

    if event_counts.get("no_face", 0) and event_counts.get("gaze_deviation", 0):
        combined_risk = event_counts.get("no_face", 0) + event_counts.get("gaze_deviation", 0)
        if combined_risk >= 2 and policy_action not in {"terminate", "pause"}:
            policy_action = "flag_review"
            policy_severity = "high"
            policy_detail = "Combined no-face and gaze deviation pattern exceeded the escalation threshold."

    if event_counts.get("tab_switch", 0) + event_counts.get("copy_paste_attempt", 0) > 5:
        policy_action = policy_action or "flag_review"
        policy_severity = "high"
        policy_detail = "Tab switching and copy/paste patterns indicate elevated academic integrity risk."

    if policy_action == "warn" and recent_workflow_warn == 0:
        db.add(
            Violation(
                session_id=session.id,
                event_type="workflow_warn",
                severity=policy_severity,
                risk_delta=0.0,
                detail=policy_detail or f"Workflow escalation: {latest_event_type}",
                ai_confidence=confidence,
                policy_category=category,
                policy_action=policy_action,
                human_review_required=False,
                explainability=policy_detail or build_explainability_statement(latest_event_type, confidence, event_counts[latest_event_type]),
            )
        )
        policy_warn_recorded = True
        actions.append(
            {
                "rule_id": None,
                "rule_name": "enterprise_policy_warn",
                "action": policy_action,
                "metric": latest_event_type,
                "threshold": 0,
                "source": "enterprise_policy",
            }
        )
    elif policy_action in {"pause", "terminate", "flag_review", "log"}:
        actions.append(
            {
                "rule_id": None,
                "rule_name": "enterprise_policy",
                "action": policy_action,
                "metric": latest_event_type,
                "threshold": 0,
                "source": "enterprise_policy",
                "risk_level": risk_level,
                "confidence": confidence,
                "detail": policy_detail,
            }
        )
        if policy_action == "flag_review":
            # session.status = "paused" # Auto-pause disabled per user request
            db.add(
                Violation(
                    session_id=session.id,
                    event_type="workflow_warn",
                    severity=policy_severity,
                    risk_delta=0.0,
                    detail=policy_detail or f"Human review required for {latest_event_type}",
                    ai_confidence=confidence,
                    policy_category=category,
                    policy_action=policy_action,
                    human_review_required=True,
                    explainability=policy_detail or build_explainability_statement(latest_event_type, confidence, event_counts[latest_event_type]),
                )
            )

    for rule in rules:
        triggered = False

        if rule.metric == "risk_score" and session.risk_score > rule.threshold:
            triggered = True
        elif rule.metric.startswith("event_count:"):
            event_name = rule.metric.split(":", 1)[1]
            if event_name == latest_event_type:
                count = db.query(Violation).filter(Violation.session_id == session.id, Violation.event_type == event_name).count()
                if count > rule.threshold:
                    triggered = True

        if not triggered:
            continue

        action = rule.action.lower().strip()
        if latest_event_type == "multiple_faces" and action in {"terminate", "auto_submit"}:
            action = "pause"
        if action == "warn":
            if policy_warn_recorded:
                continue
            db.add(
                Violation(
                    session_id=session.id,
                    event_type="workflow_warn",
                    severity="medium",
                    risk_delta=0.0,
                    detail=f"Workflow rule triggered warning: {rule.name}",
                    ai_confidence=confidence,
                    policy_category="workflow",
                    policy_action="warn",
                    human_review_required=False,
                    explainability=f"Workflow rule {rule.name} matched metric {rule.metric} at threshold {rule.threshold}.",
                )
            )
        elif action == "pause":
            # session.status = "paused" # Auto-pause disabled per user request
            pass
        elif action in {"terminate", "auto_submit"}:
            # session.status = "terminated" if action == "terminate" else "auto_submitted"
            # session.ended_at = datetime.utcnow()
            pass

        actions.append(
            {
                "rule_id": rule.id,
                "rule_name": rule.name,
                "action": action,
                "metric": rule.metric,
                "threshold": rule.threshold,
            }
        )

    if latest_event_type == "multiple_faces" and session.status == "terminated":
        session.status = "paused"
        session.ended_at = None

    return actions
