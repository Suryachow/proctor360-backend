"""Phase 1 Service Layer: Advanced Proctoring Business Logic

Handles:
- Behavioral analysis and impersonation detection
- Zero trust verification workflows
- Multi-camera synchronization
- Audio analysis with keyword detection
"""
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import statistics

from app.models.entities import (
    ExamSession, BehavioralMetric, TypingPattern, MouseMovement,
    EyeGazeSample, AttentionScore, IdentityReverificationEvent,
    DeviceVerificationCheck, Violation
)


class BehavioralAnalysisService:
    """Analyze behavioral patterns for impersonation detection."""
    
    TYPING_BASELINE_WINDOW = 5 * 60  # First 5 minutes
    WPM_DEVIATION_THRESHOLD = 30  # percent
    ACCURACY_DEVIATION_THRESHOLD = 25  # percent
    
    @staticmethod
    def establish_baseline(db: Session, session_id: int, start_time: datetime):
        """Establish behavioral baseline from first 5 minutes."""
        baseline_end = start_time + timedelta(seconds=BehavioralAnalysisService.TYPING_BASELINE_WINDOW)
        
        typing_patterns = db.query(TypingPattern).filter(
            TypingPattern.session_id == session_id,
            TypingPattern.timestamp <= baseline_end
        ).all()
        
        if not typing_patterns:
            return None
        
        baseline = {
            "wpm_mean": statistics.mean([p.wpm for p in typing_patterns]),
            "accuracy_mean": statistics.mean([p.accuracy_percent for p in typing_patterns]),
            "keystroke_interval_mean": statistics.mean([p.avg_keystroke_interval_ms for p in typing_patterns]),
            "sample_count": len(typing_patterns)
        }
        
        if len(typing_patterns) > 1:
            baseline["wpm_stdev"] = statistics.stdev([p.wpm for p in typing_patterns])
            baseline["accuracy_stdev"] = statistics.stdev([p.accuracy_percent for p in typing_patterns])
        
        return baseline
    
    @staticmethod
    def detect_impersonation(db: Session, session_id: int, baseline: dict) -> list:
        """Detect if user is impersonator based on behavioral deviation."""
        if not baseline:
            return []
        
        current_patterns = db.query(TypingPattern).filter(
            TypingPattern.session_id == session_id
        ).order_by(TypingPattern.timestamp.desc()).limit(5).all()
        
        if not current_patterns:
            return []
        
        detections = []
        for pattern in current_patterns:
            wpm_deviation = abs(pattern.wpm - baseline["wpm_mean"]) / (baseline["wpm_mean"] or 1) * 100
            accuracy_deviation = abs(pattern.accuracy_percent - baseline["accuracy_mean"])
            
            if wpm_deviation > BehavioralAnalysisService.WPM_DEVIATION_THRESHOLD:
                detections.append({
                    "type": "typing_speed_change",
                    "severity": "medium",
                    "deviation_percent": round(wpm_deviation, 1),
                    "baseline": round(baseline["wpm_mean"], 1),
                    "current": round(pattern.wpm, 1)
                })
            
            if accuracy_deviation > BehavioralAnalysisService.ACCURACY_DEVIATION_THRESHOLD:
                detections.append({
                    "type": "accuracy_drop",
                    "severity": "medium",
                    "baseline": round(baseline["accuracy_mean"], 1),
                    "current": round(pattern.accuracy_percent, 1)
                })
        
        return detections
    
    @staticmethod
    def calculate_behavioral_consistency(db: Session, session_id: int) -> float:
        """Calculate 0-100 behavioral consistency score."""
        detections = db.query(Violation).filter(
            Violation.session_id == session_id,
            Violation.event_type.in_([
                "typing_pattern_deviation",
                "suspicious_pointer_behavior",
                "suspicious_keyboard_pattern"
            ])
        ).count()
        
        # Start at 100, deduct for each behavioural violation
        consistency = max(0, 100 - (detections * 15))
        return float(consistency)


class ZeroTrustService:
    """Manage continuous device and identity verification."""
    
    RE_VERIFICATION_INTERVAL = 10 * 60  # Re-verify every 10 minutes
    DEVICE_FINGERPRINT_WEIGHT = 0.4
    NETWORK_VERIFICATION_WEIGHT = 0.35
    IDENTITY_VERIFICATION_WEIGHT = 0.25
    
    @staticmethod
    def schedule_reverifications(db: Session, session_id: int):
        """Schedule periodic identity re-verifications."""
        session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
        if not session:
            return []
        
        events = []
        current = session.started_at + timedelta(seconds=ZeroTrustService.RE_VERIFICATION_INTERVAL)
        end = session.ended_at or datetime.utcnow() + timedelta(hours=1)
        
        while current < end:
            event = IdentityReverificationEvent(
                session_id=session_id,
                scheduled_time=current
            )
            db.add(event)
            events.append(event)
            current += timedelta(seconds=ZeroTrustService.RE_VERIFICATION_INTERVAL)
        
        db.commit()
        return events
    
    @staticmethod
    def calculate_device_integrity_score(db: Session, session_id: int) -> float:
        """Calculate 0-100 device integrity score based on verification checks."""
        checks = db.query(DeviceVerificationCheck).filter(
            DeviceVerificationCheck.session_id == session_id
        ).all()
        
        if not checks:
            return 100.0
        
        passed = sum(1 for c in checks if c.result == "pass")
        integrity = (passed / len(checks)) * 100 if checks else 100.0
        return float(integrity)
    
    @staticmethod
    def evaluate_trust_score(
        device_integrity: float,
        identity_verified: bool,
        network_clean: bool
    ) -> float:
        """Calculate composite trust score from all verification dimensions."""
        score = (
            device_integrity * ZeroTrustService.DEVICE_FINGERPRINT_WEIGHT +
            (100 if identity_verified else 0) * ZeroTrustService.IDENTITY_VERIFICATION_WEIGHT +
            (100 if network_clean else 0) * ZeroTrustService.NETWORK_VERIFICATION_WEIGHT
        )
        return float(min(100, max(0, score)))


class AttentionTrackingService:
    """Analyze eye tracking data for attention patterns."""
    
    ATTENTION_WINDOW = 60  # 1-minute aggregation windows
    LOW_ATTENTION_THRESHOLD = 60  # % time looking at screen
    
    @staticmethod
    def calculate_attention_score(db: Session, session_id: int, window_minutes: int = 1) -> dict:
        """Calculate attention score for a time window."""
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(minutes=window_minutes)
        
        gaze_samples = db.query(EyeGazeSample).filter(
            EyeGazeSample.session_id == session_id,
            EyeGazeSample.timestamp >= start_time,
            EyeGazeSample.timestamp <= end_time
        ).all()
        
        if not gaze_samples:
            return {
                "attention_percent": 0.0,
                "focus_score": 0.0,
                "gaze_stability": 0.0,
                "sample_count": 0
            }
        
        on_screen = sum(1 for s in gaze_samples if s.is_on_screen)
        attention_percent = (on_screen / len(gaze_samples)) * 100
        
        # Calculate gaze stability
        positions = [(s.gaze_x, s.gaze_y) for s in gaze_samples if s.is_on_screen]
        if positions:
            avg_x = statistics.mean([p[0] for p in positions])
            avg_y = statistics.mean([p[1] for p in positions])
            variance = statistics.variance(
                [(p[0]-avg_x)**2 + (p[1]-avg_y)**2 for p in positions]
            ) if len(positions) > 1 else 0
            gaze_stability = max(0, 1.0 - min(variance, 1.0))
        else:
            gaze_stability = 0.0
        
        focus_score = (attention_percent * 0.7) + (gaze_stability * 30)
        
        # Store aggregate
        score = AttentionScore(
            session_id=session_id,
            window_start_time=start_time,
            window_end_time=end_time,
            attention_percent=round(attention_percent, 1),
            focus_score=round(focus_score, 1),
            gaze_stability=round(gaze_stability, 2)
        )
        
        return {
            "attention_percent": round(attention_percent, 1),
            "focus_score": round(focus_score, 1),
            "gaze_stability": round(gaze_stability, 2),
            "sample_count": len(gaze_samples)
        }
    
    @staticmethod
    def detect_low_attention(db: Session, session_id: int) -> bool:
        """Check if recent attention is below threshold."""
        recent_score = AttentionTrackingService.calculate_attention_score(db, session_id, window_minutes=1)
        return recent_score["attention_percent"] < AttentionTrackingService.LOW_ATTENTION_THRESHOLD
