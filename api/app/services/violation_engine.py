from datetime import datetime

RISK_LEVELS = [
    (30.0, "safe"),
    (60.0, "suspicious"),
    (80.0, "high_risk"),
    (100.0, "critical"),
]

EVENT_POLICY = {
    "no_face": {"weight": 8.0, "category": "critical", "half_life_seconds": 300.0, "threshold": 1},
    "temporary_face_loss": {"weight": 3.0, "category": "minor", "half_life_seconds": 45.0, "threshold": 1},
    "multiple_faces": {"weight": 12.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "phone_detected": {"weight": 15.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "face_mismatch": {"weight": 20.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "unknown_person_detected": {"weight": 18.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "face_similarity_drop": {"weight": 35.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "external_person_interaction": {"weight": 18.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "screen_sharing_detected": {"weight": 40.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "remote_desktop_detected": {"weight": 40.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "tab_switch": {"weight": 3.0, "category": "major", "half_life_seconds": 60.0, "threshold": 8},
    "fullscreen_exit": {"weight": 5.0, "category": "major", "half_life_seconds": 90.0, "threshold": 3},
    "gaze_deviation": {"weight": 4.0, "category": "major", "half_life_seconds": 120.0, "threshold": 5},
    "looking_away": {"weight": 4.0, "category": "major", "half_life_seconds": 120.0, "threshold": 5},
    "multiple_voices": {"weight": 10.0, "category": "major", "half_life_seconds": 120.0, "threshold": 1},
    "whisper_detected": {"weight": 12.0, "category": "major", "half_life_seconds": 120.0, "threshold": 1},
    "copy_paste_attempt": {"weight": 8.0, "category": "major", "half_life_seconds": 60.0, "threshold": 2},
    "developer_tools_detected": {"weight": 45.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "device_fingerprint_mismatch": {"weight": 50.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "virtual_machine_detected": {"weight": 45.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "virtual_webcam_detected": {"weight": 40.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "virtual_microphone_detected": {"weight": 35.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "vpn_detected": {"weight": 30.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "suspicious_pointer_behavior": {"weight": 35.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "suspicious_keyboard_pattern": {"weight": 30.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1},
    "audio_spike": {"weight": 10.0, "category": "minor", "half_life_seconds": 30.0, "threshold": 1},
    "lighting_issue": {"weight": 4.0, "category": "minor", "half_life_seconds": 30.0, "threshold": 1},
    "window_blur": {"weight": 5.0, "category": "minor", "half_life_seconds": 30.0, "threshold": 1},
    "mouse_left_window": {"weight": 5.0, "category": "minor", "half_life_seconds": 30.0, "threshold": 1},
    "workflow_warn": {"weight": 0.0, "category": "workflow", "half_life_seconds": 0.0, "threshold": 1},
}

EVENT_ALIASES = {
    "face_similarity_drop": "face_mismatch",
    "unknown_person_detected": "face_mismatch",
    "remote_desktop_detected": "remote_desktop_detected",
    "screen_sharing_detected": "screen_sharing_detected",
    "no_device": "temporary_face_loss",
    "suspicious_pose": "looking_away",
    "looking_away": "looking_away",
}

EXPLAINABLE_REASONS = {
    "tab_switch": "Browser tab hidden during active exam.",
    "fullscreen_exit": "Fullscreen mode exited while exam is active.",
    "copy_paste_attempt": "Clipboard or shortcut interaction was blocked.",
    "no_face": "No face found in frame.",
    "temporary_face_loss": "Brief face loss detected within the grace window.",
    "multiple_faces": "More than one face detected in frame.",
    "phone_detected": "Phone-like object detected by vision heuristics.",
    "face_mismatch": "Face in frame does not match registered student profile.",
    "external_person_interaction": "Another person appears to be interacting with the candidate.",
    "screen_sharing_detected": "Screen sharing or remote collaboration tool detected.",
    "remote_desktop_detected": "Remote Desktop Protocol (RDP) or similar remote access detected.",
    "audio_spike": "Audio amplitude crossed suspicious threshold.",
    "looking_away": "Gaze moved away from exam area repeatedly.",
    "gaze_deviation": "Eye gaze deviation sustained above policy threshold.",
    "lighting_issue": "Lighting conditions may have reduced visibility briefly.",
    "multiple_voices": "Multiple simultaneous voices detected.",
    "whisper_detected": "Whisper-like voice signature detected.",
    "suspicious_behavior": "Combined behavior signals exceed baseline.",
    "device_fingerprint_mismatch": "Device identification changed during exam. Possible exam switching to different device.",
    "developer_tools_detected": "Browser developer tools were opened during exam.",
    "window_blur": "Exam application lost focus/window was minimized.",
    "mouse_left_window": "Mouse cursor left the exam application window.",
    "workflow_warn": "Admin issued warning for suspicious activity.",
    "suspicious_pointer_behavior": "Mouse cursor showed unnatural jumping/teleportation patterns typical of remote control.",
    "suspicious_keyboard_pattern": "Keyboard input pattern consistent with robotic/automated typing or remote control.",
    "virtual_machine_detected": "Virtual machine environment detected. Exam must be taken on native OS.",
    "virtual_webcam_detected": "Virtual or emulated webcam detected. Physical device required.",
    "virtual_microphone_detected": "Virtual or emulated microphone detected. Physical device required.",
    "vpn_detected": "VPN or proxy connection detected. Direct internet connection required.",
}


CRITICAL_EVENTS = {
    "no_face",
    "multiple_faces",
    "phone_detected",
    "face_mismatch",
    "external_person_interaction",
    "screen_sharing_detected",
    "remote_desktop_detected",
    "developer_tools_detected",
    "device_fingerprint_mismatch",
    "virtual_machine_detected",
    "virtual_webcam_detected",
    "virtual_microphone_detected",
    "vpn_detected",
    "suspicious_pointer_behavior",
    "suspicious_keyboard_pattern",
}

MAJOR_EVENTS = {
    "tab_switch",
    "fullscreen_exit",
    "gaze_deviation",
    "looking_away",
    "multiple_voices",
    "whisper_detected",
    "copy_paste_attempt",
}

MINOR_EVENTS = {
    "temporary_face_loss",
    "lighting_issue",
    "window_blur",
    "mouse_left_window",
    "audio_spike",
}


def canonical_event_type(event_type: str) -> str:
    normalized = str(event_type or "").strip().lower()
    return EVENT_ALIASES.get(normalized, normalized)


def get_policy_profile(event_type: str) -> dict:
    canonical = canonical_event_type(event_type)
    profile = EVENT_POLICY.get(canonical)
    if profile:
        return profile
    if canonical in CRITICAL_EVENTS:
        return {"weight": 50.0, "category": "critical", "half_life_seconds": 0.0, "threshold": 1}
    if canonical in MAJOR_EVENTS:
        return {"weight": 10.0, "category": "major", "half_life_seconds": 90.0, "threshold": 2}
    if canonical in MINOR_EVENTS:
        return {"weight": 5.0, "category": "minor", "half_life_seconds": 30.0, "threshold": 1}
    return {"weight": 5.0, "category": "minor", "half_life_seconds": 45.0, "threshold": 1}


def get_violation_category(event_type: str) -> str:
    return get_policy_profile(event_type)["category"]


def get_risk_delta(event_type: str, severity_mult: float = 1.0) -> float:
    base = get_policy_profile(event_type)["weight"]
    return base * severity_mult


def get_reason(event_type: str) -> str:
    return EXPLAINABLE_REASONS.get(canonical_event_type(event_type), "Policy rule matched an unusual behavior pattern.")


def get_severity(risk_delta: float) -> str:
    if risk_delta >= 30:
        return "high"
    if risk_delta >= 15:
        return "medium"
    return "low"


def classify_risk_level(total_risk: float) -> str:
    risk = normalize_risk(total_risk)
    if risk < 30:
        return "safe"
    if risk < 60:
        return "suspicious"
    if risk < 80:
        return "high_risk"
    return "critical"


def build_explainability_statement(event_type: str, confidence: float | None = None, frequency: int = 1) -> str:
    canonical = canonical_event_type(event_type)
    reason = get_reason(canonical)
    confidence_text = f" confidence={round(float(confidence), 2)}" if confidence is not None else ""
    repeat_text = f" repeated {frequency} time(s)" if frequency > 1 else ""
    return f"{reason}{repeat_text}{confidence_text}".strip()


def calculate_decayed_risk(violations: list, current_time: datetime | None = None) -> float:
    """Risk Score = sum(weight * frequency * time factor) with category-aware decay."""
    if not violations:
        return 0.0

    if current_time is None:
        current_time = datetime.utcnow()

    total_score = 0.0
    for v in violations:
        profile = get_policy_profile(v.event_type)
        half_life_seconds = float(profile.get("half_life_seconds") or 0.0)
        if half_life_seconds <= 0.0:
            time_factor = 1.0
        else:
            created_at = getattr(v, "created_at", current_time) or current_time
            time_diff = max((current_time - created_at).total_seconds(), 0.0)
            time_factor = 2.0 ** (-time_diff / half_life_seconds)

        severity_mult = 1.0 if getattr(v, "severity", "medium") != "high" else 1.15
        total_score += float(v.risk_delta or 0.0) * time_factor * severity_mult

    return normalize_risk(total_score)


def should_auto_submit(total_risk: float, confidence: float | None = None) -> bool:
    if confidence is not None and confidence < 0.70:
        return False
    return total_risk >= 90.0


def normalize_risk(total_risk: float) -> float:
    return max(0.0, min(100.0, round(float(total_risk), 2)))


def risk_level_from_score(total_risk: float) -> str:
    risk = normalize_risk(total_risk)
    for threshold, label in RISK_LEVELS:
        if risk < threshold:
            return label
    return "critical"
