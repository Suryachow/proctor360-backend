"""Phase 1 Advanced Proctoring API Endpoints

Includes:
- Multi-Camera Proctoring (1A)
- Audio Intelligence Engine (1B)
- Behavioral Fingerprinting (1C)
- Eye Tracking + Attention Score (1D)
- Zero Trust Architecture (1E)
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_current_student, get_current_admin
from app.db.session import get_db
from app.models.entities import (
    ExamSession, Student, SecondaryCamera, CameraSyncFrame, AudioSample,
    BehavioralMetric, TypingPattern, MouseMovement, EyeGazeSample, AttentionScore,
    DeviceVerificationCheck, IdentityReverificationEvent, Violation
)
from app.services.ws_manager import ws_manager

router = APIRouter(prefix="/phase1", tags=["phase1_advanced_proctoring"])


# ============================================================================
# PHASE 1A: MULTI-CAMERA PROCTORING
# ============================================================================

@router.post("/camera/register-secondary")
async def register_secondary_camera(
    payload: dict,  # {session_id, device_id, camera_type}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Register secondary camera (mobile/tablet) for side-view proctoring."""
    session_id = payload.get("session_id")
    device_id = payload.get("device_id", "").strip()
    camera_type = payload.get("camera_type", "mobile")  # 'mobile', 'tablet'
    
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check if already registered
    existing = db.query(SecondaryCamera).filter(
        SecondaryCamera.session_id == session_id,
        SecondaryCamera.device_id == device_id
    ).first()
    if existing:
        return {"ok": True, "camera_id": existing.id, "message": "Camera already registered"}
    
    camera = SecondaryCamera(
        session_id=session_id,
        device_id=device_id,
        camera_type=camera_type,
        is_active=True
    )
    db.add(camera)
    session.multi_camera_enabled = True
    db.commit()
    db.refresh(camera)
    
    await ws_manager.broadcast("admin_violations", {
        "session_id": session_id,
        "event_type": "secondary_camera_registered",
        "severity": "info",
        "student_email": current_student.email,
        "camera_type": camera_type,
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {
        "ok": True,
        "camera_id": camera.id,
        "device_id": device_id,
        "camera_type": camera_type,
        "registration_time": camera.registration_time.isoformat()
    }


@router.post("/camera/submit-secondary-frame")
async def submit_secondary_frame(
    payload: dict,  # {session_id, camera_id, frame_base64, timestamp}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Submit frame from secondary camera with cheating detection."""
    session_id = payload.get("session_id")
    camera_id = payload.get("camera_id")
    frame_base64 = payload.get("frame_base64", "")
    frame_timestamp = payload.get("timestamp")
    
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id,
        ExamSession.status == "active"
    ).first()
    if not session:
        raise HTTPException(status_code=400, detail="Session inactive")
    
    camera = db.query(SecondaryCamera).filter(SecondaryCamera.id == camera_id).first()
    if not camera or not camera.is_active:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    # Analyze frame for side-view cheating indicators
    cheating_indicators = await _analyze_side_camera_frame(frame_base64)
    
    frame_count = db.query(CameraSyncFrame).filter(CameraSyncFrame.session_id == session_id).count()
    frame = CameraSyncFrame(
        session_id=session_id,
        secondary_camera_id=camera_id,
        frame_base64=frame_base64,
        timestamp=frame_timestamp or datetime.utcnow(),
        frame_index=frame_count + 1,
        cheating_indicators=cheating_indicators
    )
    db.add(frame)
    camera.last_frame_timestamp = datetime.utcnow()
    db.commit()
    
    # Trigger violations if cheating detected
    if cheating_indicators and cheating_indicators.get("threat_level", "low") == "high":
        violation = Violation(
            session_id=session_id,
            event_type="secondary_camera_cheating_detected",
            severity="high",
            risk_delta=35.0,
            detail=f"Side camera detected cheating indicators: {cheating_indicators.get('indicators', [])}"
        )
        db.add(violation)
        session.risk_score += 35.0
        db.commit()
        
        await ws_manager.broadcast("admin_violations", {
            "session_id": session_id,
            "event_type": "secondary_camera_cheating",
            "severity": "high",
            "detail": f"Side view threat: {cheating_indicators.get('reason', '')}",
            "student_email": current_student.email,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    return {
        "ok": True,
        "frame_id": frame.id,
        "cheating_detected": cheating_indicators.get("threat_level") == "high",
        "indicators": cheating_indicators.get("indicators", [])
    }


async def _analyze_side_camera_frame(frame_base64: str) -> dict:
    """Analyze secondary camera frame for cheating indicators."""
    # Simplified analysis (in production, use AI engine)
    return {
        "threat_level": "low",
        "indicators": [],
        "reason": "No cheating detected in side view",
        "confidence": 0.95
    }


# ============================================================================
# PHASE 1B: AUDIO INTELLIGENCE ENGINE
# ============================================================================

@router.post("/audio/submit-sample")
async def submit_audio_sample(
    payload: dict,  # {session_id, audio_base64, duration_seconds}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Submit audio sample for Whisper transcription and voice analysis."""
    session_id = payload.get("session_id")
    audio_base64 = payload.get("audio_base64", "")
    duration_seconds = payload.get("duration_seconds", 0.0)
    
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id,
        ExamSession.status == "active"
    ).first()
    if not session:
        raise HTTPException(status_code=400, detail="Session inactive")
    
    # Analyze audio with Whisper
    audio_analysis = await _analyze_audio_with_whisper(audio_base64, duration_seconds)
    
    sample_count = db.query(AudioSample).filter(AudioSample.session_id == session_id).count()
    sample = AudioSample(
        session_id=session_id,
        audio_base64=audio_base64,
        duration_seconds=duration_seconds,
        timestamp=datetime.utcnow(),
        sample_index=sample_count + 1,
        audio_analysis=audio_analysis
    )
    db.add(sample)
    session.audio_enabled = True
    db.commit()
    
    # Check for cheating keywords or multiple voices
    risk_events = []
    if audio_analysis.get("voice_count", 1) > 1:
        violation = Violation(
            session_id=session_id,
            event_type="multiple_voices_detected",
            severity="high",
            risk_delta=25.0,
            detail=f"Multiple voices detected: {audio_analysis.get('voice_count', 0)}"
        )
        db.add(violation)
        session.risk_score += 25.0
        risk_events.append("multiple_voices")
    
    if audio_analysis.get("cheating_keywords_detected"):
        violation = Violation(
            session_id=session_id,
            event_type="cheating_keywords_detected",
            severity="medium",
            risk_delta=15.0,
            detail=f"Cheating keywords: {audio_analysis.get('detected_keywords', [])}"
        )
        db.add(violation)
        session.risk_score += 15.0
        risk_events.append("cheating_keywords")
    
    db.commit()
    
    if risk_events:
        await ws_manager.broadcast("admin_violations", {
            "session_id": session_id,
            "event_type": "audio_threat_detected",
            "severity": "high" if "multiple_voices" in risk_events else "medium",
            "detail": f"Audio analysis detected: {', '.join(risk_events)}",
            "student_email": current_student.email,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    return {
        "ok": True,
        "sample_id": sample.id,
        "transcription": audio_analysis.get("transcription", ""),
        "voice_count": audio_analysis.get("voice_count", 1),
        "cheating_keywords_detected": audio_analysis.get("cheating_keywords_detected", False),
        "detected_keywords": audio_analysis.get("detected_keywords", [])
    }


async def _analyze_audio_with_whisper(audio_base64: str, duration: float) -> dict:
    """Analyze audio using Whisper API for transcription and keyword detection."""
    # Placeholder: Integration with Whisper API
    return {
        "transcription": "[Audio transcription would appear here]",
        "voice_count": 1,
        "cheating_keywords_detected": False,
        "detected_keywords": [],
        "noise_classification": "normal",
        "confidence": 0.92
    }


# ============================================================================
# PHASE 1C: BEHAVIORAL FINGERPRINTING
# ============================================================================

@router.post("/behavior/typing-pattern")
async def submit_typing_pattern(
    payload: dict,  # {session_id, wpm, accuracy, keystroke_interval, hold_distribution}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Submit typing pattern for baseline establishment/impersonation detection."""
    session_id = payload.get("session_id")
    wpm = payload.get("wpm", 0.0)
    accuracy = payload.get("accuracy_percent", 100.0)
    keystroke_interval = payload.get("avg_keystroke_interval_ms", 50.0)
    hold_distribution = payload.get("hold_time_distribution", {})
    
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    pattern = TypingPattern(
        session_id=session_id,
        wpm=wpm,
        accuracy_percent=accuracy,
        avg_keystroke_interval_ms=keystroke_interval,
        hold_time_distribution=hold_distribution,
        timestamp=datetime.utcnow()
    )
    db.add(pattern)
    
    # Check if baseline is established (first 5 minutes)
    baseline_window = session.started_at + timedelta(minutes=5)
    is_in_baseline = datetime.utcnow() < baseline_window
    
    if not is_in_baseline:
        # Compare against baseline
        baseline_pattern = db.query(TypingPattern).filter(
            TypingPattern.session_id == session_id,
            TypingPattern.timestamp < baseline_window
        ).order_by(TypingPattern.timestamp).first()
        
        if baseline_pattern:
            wpm_deviation = abs(wpm - baseline_pattern.wpm) / (baseline_pattern.wpm or 1) * 100
            accuracy_deviation = abs(accuracy - baseline_pattern.accuracy_percent)
            
            if wpm_deviation > 30 or accuracy_deviation > 25:  # Thresholds
                violation = Violation(
                    session_id=session_id,
                    event_type="typing_pattern_deviation",
                    severity="medium",
                    risk_delta=20.0,
                    detail=f"Typing pattern changed: WPM deviation {wpm_deviation:.1f}%, accuracy {accuracy_deviation:.1f}%"
                )
                db.add(violation)
                session.risk_score += 20.0
                session.behavioral_consistency_score = max(0, session.behavioral_consistency_score - 15)
    
    db.commit()
    return {
        "ok": True,
        "pattern_id": pattern.id,
        "wpm": wpm,
        "accuracy": accuracy,
        "baseline_established": is_in_baseline
    }


@router.post("/behavior/mouse-movement")
async def submit_mouse_movement(
    payload: dict,  # {session_id, velocity, acceleration, jitter, teleport_events}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Submit mouse movement pattern for RDP/automation detection."""
    session_id = payload.get("session_id")
    velocity = payload.get("velocity_px_per_sec", 0.0)
    acceleration = payload.get("acceleration_px_per_sec2", 0.0)
    jitter = payload.get("jitter_score", 0.5)
    teleport_events = payload.get("teleport_events", 0)
    
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    movement = MouseMovement(
        session_id=session_id,
        velocity_px_per_sec=velocity,
        acceleration_px_per_sec2=acceleration,
        jitter_score=jitter,
        teleport_events=teleport_events,
        timestamp=datetime.utcnow()
    )
    db.add(movement)
    
    # Detect RDP signatures
    if teleport_events > 5 or (velocity > 1000 and jitter < 0.2):  # Unnatural movement
        violation = Violation(
            session_id=session_id,
            event_type="suspicious_pointer_behavior_detected",
            severity="high",
            risk_delta=35.0,
            detail=f"Possible RDP/remote control: teleports={teleport_events}, velocity={velocity:.1f}px/s"
        )
        db.add(violation)
        session.risk_score += 35.0
        session.behavioral_consistency_score = max(0, session.behavioral_consistency_score - 20)
    
    db.commit()
    return {"ok": True, "movement_id": movement.id, "rdp_suspicious": teleport_events > 5}


# ============================================================================
# PHASE 1D: EYE TRACKING & ATTENTION SCORE
# ============================================================================

@router.post("/eye-tracking/gaze-sample")
async def submit_gaze_sample(
    payload: dict,  # {session_id, gaze_x, gaze_y, pupil_diameter, confidence}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Submit eye gaze sample for attention tracking."""
    session_id = payload.get("session_id")
    gaze_x = payload.get("gaze_x", 0.5)
    gaze_y = payload.get("gaze_y", 0.5)
    pupil_diameter = payload.get("pupil_diameter_mm")
    confidence = payload.get("confidence", 0.8)
    
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Determine region of interest
    is_on_screen = 0 <= gaze_x <= 1 and 0 <= gaze_y <= 1
    region = "question_area" if is_on_screen else "off_screen"
    
    sample = EyeGazeSample(
        session_id=session_id,
        gaze_x=gaze_x,
        gaze_y=gaze_y,
        pupil_diameter_mm=pupil_diameter,
        confidence=confidence,
        is_on_screen=is_on_screen,
        region_of_interest=region,
        timestamp=datetime.utcnow()
    )
    db.add(sample)
    session.eye_tracking_enabled = True
    db.commit()
    
    return {"ok": True, "sample_id": sample.id, "region": region, "on_screen": is_on_screen}


@router.get("/eye-tracking/attention-score/{session_id}")
def get_attention_score(
    session_id: int,
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Get aggregated attention score for exam session."""
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Calculate attention from gaze samples
    gaze_samples = db.query(EyeGazeSample).filter(EyeGazeSample.session_id == session_id).all()
    if not gaze_samples:
        return {
            "session_id": session_id,
            "attention_percent": 100.0,
            "focus_score": 100.0,
            "gaze_stability": 0.0,
            "samples_count": 0
        }
    
    on_screen_count = sum(1 for s in gaze_samples if s.is_on_screen)
    attention_percent = (on_screen_count / len(gaze_samples)) * 100
    
    # Calculate gaze stability (lower variance = higher stability)
    gaze_positions = [(s.gaze_x, s.gaze_y) for s in gaze_samples]
    avg_x = sum(p[0] for p in gaze_positions) / len(gaze_positions)
    avg_y = sum(p[1] for p in gaze_positions) / len(gaze_positions)
    variance = sum((p[0]-avg_x)**2 + (p[1]-avg_y)**2 for p in gaze_positions) / len(gaze_positions)
    gaze_stability = max(0, 1.0 - min(variance, 1.0))
    
    focus_score = (attention_percent * 0.7) + (gaze_stability * 30)
    
    return {
        "session_id": session_id,
        "attention_percent": round(attention_percent, 1),
        "focus_score": round(focus_score, 1),
        "gaze_stability": round(gaze_stability, 2),
        "samples_count": len(gaze_samples)
    }


# ============================================================================
# PHASE 1E: ZERO TRUST ARCHITECTURE
# ============================================================================

@router.post("/zero-trust/verify-device")
async def verify_device(
    payload: dict,  # {session_id, device_fingerprint, network_info}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Continuous device verification check during exam."""
    session_id = payload.get("session_id")
    device_fingerprint = payload.get("device_fingerprint", "")
    network_info = payload.get("network_info", {})
    
    session = db.query(ExamSession).filter(
        ExamSession.id == session_id,
        ExamSession.student_id == current_student.id
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check device fingerprint match
    if session.device_fingerprint and session.device_fingerprint != device_fingerprint:
        result = "fail"
        detail = "Device fingerprint changed during exam"
        violation_type = "device_fingerprint_mismatch"
        risk_delta = 50.0
    else:
        result = "pass"
        detail = "Device verified"
        violation_type = None
        risk_delta = 0.0
    
    # Check for VPN/proxy
    is_vpn = _detect_vpn(network_info)
    if is_vpn:
        result = "fail"
        detail = "VPN detected"
        violation_type = "vpn_detected"
        risk_delta = 30.0
    
    check = DeviceVerificationCheck(
        session_id=session_id,
        check_type="combined_device_network",
        check_timestamp=datetime.utcnow(),
        result=result,
        details={"device_match": session.device_fingerprint == device_fingerprint, "vpn": is_vpn}
    )
    db.add(check)
    
    if violation_type:
        violation = Violation(
            session_id=session_id,
            event_type=violation_type,
            severity="high",
            risk_delta=risk_delta,
            detail=detail
        )
        db.add(violation)
        session.risk_score += risk_delta
        session.device_integrity_score = max(0, session.device_integrity_score - 50)
    
    db.commit()
    
    if result == "fail":
        await ws_manager.broadcast("admin_violations", {
            "session_id": session_id,
            "event_type": violation_type or "device_verification_failed",
            "severity": "high",
            "detail": detail,
            "student_email": current_student.email,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    return {"ok": True, "check_id": check.id, "result": result, "detail": detail}


@router.post("/zero-trust/request-identity-reverification")
async def request_identity_reverification(
    session_id: int,
    current_admin = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """Admin requests identity re-verification for a session."""
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    event = IdentityReverificationEvent(
        session_id=session_id,
        scheduled_time=datetime.utcnow()
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    
    await ws_manager.broadcast(f"admin_violations", {
        "session_id": session_id,
        "event_type": "identity_reverification_requested",
        "severity": "info",
        "detail": "Admin requested identity re-verification",
        "timestamp": datetime.utcnow().isoformat()
    })
    
    return {"ok": True, "reverification_event_id": event.id, "scheduled_time": event.scheduled_time.isoformat()}


@router.post("/zero-trust/submit-reverification")
async def submit_reverification(
    payload: dict,  # {reverification_event_id, live_image_base64}
    current_student: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """Student responds to re-verification request."""
    event_id = payload.get("reverification_event_id")
    live_image_base64 = payload.get("live_image_base64", "")
    
    event = db.query(IdentityReverificationEvent).filter(IdentityReverificationEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Reverification event not found")
    
    session = db.query(ExamSession).filter(ExamSession.id == event.session_id).first()
    
    # Verify identity against registered face
    student = db.query(Student).filter(Student.id == session.student_id).first()
    similarity = await _verify_identity_biometric(student.registered_face_image, live_image_base64)
    
    event.actual_time = datetime.utcnow()
    event.live_image_base64 = live_image_base64
    event.similarity_score = similarity
    event.passed = similarity > 0.65  # Threshold
    
    if not event.passed:
        violation = Violation(
            session_id=event.session_id,
            event_type="identity_reverification_failed",
            severity="high",
            risk_delta=50.0,
            detail=f"Identity re-verification failed: similarity {similarity:.2f}"
        )
        db.add(violation)
        session.risk_score += 50.0
        session.device_integrity_score = max(0, session.device_integrity_score - 50)
    
    db.commit()
    
    return {"ok": True, "passed": event.passed, "similarity_score": round(similarity, 2)}


def _detect_vpn(network_info: dict) -> bool:
    """Detect VPN/proxy usage from network metadata."""
    # Simplified detection
    return network_info.get("is_vpn", False) or network_info.get("is_proxy", False)


async def _verify_identity_biometric(registered_image: str, live_image: str) -> float:
    """Verify identity by comparing registered face with live image."""
    # Placeholder: Would call AI engine
    return 0.85  # Similarity score 0-1

