from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    device_hash: Mapped[str] = mapped_column(String(255))
    registered_face_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sessions: Mapped[list["ExamSession"]] = relationship(back_populates="student")

class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    prompt: Mapped[str] = mapped_column(Text)
    option_a: Mapped[str] = mapped_column(Text)
    option_b: Mapped[str] = mapped_column(Text)
    option_c: Mapped[str] = mapped_column(Text)
    option_d: Mapped[str] = mapped_column(Text)
    correct_option: Mapped[str] = mapped_column(String(1))
    topic: Mapped[str] = mapped_column(String(120), default="general", index=True)
    sub_topic: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    exam_links: Mapped[list["ExamQuestion"]] = relationship(back_populates="question")

class Exam(Base):
    __tablename__ = "exams"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    otp_hash: Mapped[str] = mapped_column(String(255))
    otp_plain: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    question_links: Mapped[list["ExamQuestion"]] = relationship(back_populates="exam", cascade="all, delete-orphan")
    enrollments: Mapped[list["ExamEnrollment"]] = relationship(back_populates="exam", cascade="all, delete-orphan")
    otp_uses: Mapped[list["ExamOtpUse"]] = relationship(back_populates="exam", cascade="all, delete-orphan")

class ExamQuestion(Base):
    __tablename__ = "exam_questions"
    __table_args__ = (UniqueConstraint("exam_id", "question_id", name="uq_exam_question"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    exam: Mapped["Exam"] = relationship(back_populates="question_links")
    question: Mapped["Question"] = relationship(back_populates="exam_links")

class ExamEnrollment(Base):
    __tablename__ = "exam_enrollments"
    __table_args__ = (UniqueConstraint("exam_id", "student_email", name="uq_exam_enrollment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    student_email: Mapped[str] = mapped_column(String(255), index=True)
    exam: Mapped["Exam"] = relationship(back_populates="enrollments")

class ExamOtpUse(Base):
    __tablename__ = "exam_otp_uses"
    __table_args__ = (UniqueConstraint("exam_id", "student_email", name="uq_exam_otp_use"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_id: Mapped[int] = mapped_column(ForeignKey("exams.id"), index=True)
    student_email: Mapped[str] = mapped_column(String(255), index=True)
    used_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    exam: Mapped["Exam"] = relationship(back_populates="otp_uses")

class ExamSession(Base):
    __tablename__ = "exam_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    exam_code: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(50), default="active")
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    device_integrity_score: Mapped[float] = mapped_column(Float, default=100.0)
    attention_score: Mapped[float] = mapped_column(Float, default=100.0)
    behavioral_consistency_score: Mapped[float] = mapped_column(Float, default=100.0)
    multi_camera_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    audio_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    eye_tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    device_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registered_face_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_id_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    face_similarity_history: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ENHANCED REPORT FEAT: Permanent Profile Storage Cache
    report_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    student: Mapped["Student"] = relationship(back_populates="sessions")
    violations: Mapped[list["Violation"]] = relationship(back_populates="session")
    answers: Mapped[list["ExamAnswer"]] = relationship(back_populates="session", cascade="all, delete-orphan")

class ExamAnswer(Base):
    __tablename__ = "exam_answers"
    __table_args__ = (UniqueConstraint("session_id", "question_id", name="uq_session_question_answer"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    selected_option: Mapped[str] = mapped_column(String(1))
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    # ENHANCED REPORT FEAT: Timing Data for Lag Analysis
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    session: Mapped["ExamSession"] = relationship(back_populates="answers")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor_email: Mapped[str] = mapped_column(String(255), index=True)
    actor_role: Mapped[str] = mapped_column(String(50), default="admin")
    action: Mapped[str] = mapped_column(String(100))
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class PermissionMatrix(Base):
    __tablename__ = "permission_matrix"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True)
    role: Mapped[str] = mapped_column(String(50), index=True)
    resource: Mapped[str] = mapped_column(String(100), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    effect: Mapped[str] = mapped_column(String(20), default="allow")

class WorkflowRule(Base):
    __tablename__ = "workflow_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    metric: Mapped[str] = mapped_column(String(100))
    threshold: Mapped[float] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(255))
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    scopes: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class WebhookSubscription(Base):
    __tablename__ = "webhook_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    target_url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class IntegrationConfig(Base):
    __tablename__ = "integration_configs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True)
    kind: Mapped[str] = mapped_column(String(50), index=True) # e.g. lms, sso
    provider: Mapped[str] = mapped_column(String(100), index=True)
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

class TenantExamBinding(Base):
    __tablename__ = "tenant_exam_bindings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True)
    exam_code: Mapped[str] = mapped_column(String(100), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    student_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    admin_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Violation(Base):
    __tablename__ = "violations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    risk_delta: Mapped[float] = mapped_column(Float, default=0.0)
    detail: Mapped[str] = mapped_column(Text, default="")
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    policy_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    policy_action: Mapped[str | None] = mapped_column(String(30), nullable=True)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    explainability: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    session: Mapped["ExamSession"] = relationship(back_populates="violations")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("scope", "actor_id", "idempotency_key", name="uq_idempotency_scope_actor_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    scope: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str] = mapped_column(String(255), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    response_payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# PHASE 1A: Multi-Camera Proctoring
class SecondaryCamera(Base):
    """Secondary camera registrations (mobile device, side camera)."""
    __tablename__ = "secondary_cameras"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    device_id: Mapped[str] = mapped_column(String(255), index=True)
    camera_type: Mapped[str] = mapped_column(String(50))  # 'mobile', 'tablet', 'webcam'
    registration_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_frame_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_offset_ms: Mapped[int] = mapped_column(Integer, default=0)  # Time offset from primary
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CameraSyncFrame(Base):
    """Synchronized frames from secondary cameras."""
    __tablename__ = "camera_sync_frames"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    primary_frame_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    secondary_camera_id: Mapped[int] = mapped_column(ForeignKey("secondary_cameras.id"), index=True)
    frame_base64: Mapped[str] = mapped_column(Text)  # Compressed frame
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    frame_index: Mapped[int] = mapped_column(Integer)
    cheating_indicators: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Side-cam specific analysis
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# PHASE 1B: Audio Intelligence
class AudioSample(Base):
    """Audio samples for speech-to-text and voice analysis."""
    __tablename__ = "audio_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    audio_base64: Mapped[str] = mapped_column(Text)  # Compressed audio chunk
    duration_seconds: Mapped[float] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    sample_index: Mapped[int] = mapped_column(Integer)
    audio_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Whisper + voice detection
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# PHASE 1C: Behavioral Fingerprinting
class BehavioralMetric(Base):
    """Accumulated behavioral metrics for impersonation detection."""
    __tablename__ = "behavioral_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    metric_type: Mapped[str] = mapped_column(String(50), index=True)  # 'typing_speed', 'mouse_movement', 'scroll_pattern'
    baseline_value: Mapped[float] = mapped_column(Float)  # Established in first 5 minutes
    current_value: Mapped[float] = mapped_column(Float)
    deviation_percent: Mapped[float] = mapped_column(Float)  # 0-100%
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence_score: Mapped[float] = mapped_column(Float)  # 0-1
    collected_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TypingPattern(Base):
    """Typing speed and accuracy signatures."""
    __tablename__ = "typing_patterns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    wpm: Mapped[float] = mapped_column(Float)  # Words per minute
    accuracy_percent: Mapped[float] = mapped_column(Float)  # Keystroke accuracy
    avg_keystroke_interval_ms: Mapped[float] = mapped_column(Float)
    hold_time_distribution: Mapped[dict] = mapped_column(JSON)  # Time held per key distribution
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MouseMovement(Base):
    """Mouse movement patterns for detecting RDP/automation."""
    __tablename__ = "mouse_movements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    velocity_px_per_sec: Mapped[float] = mapped_column(Float)
    acceleration_px_per_sec2: Mapped[float] = mapped_column(Float)
    jitter_score: Mapped[float] = mapped_column(Float)  # 0-1, higher = more natural
    teleport_events: Mapped[int] = mapped_column(Integer, default=0)  # Abrupt jumps
    timestamp: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# PHASE 1D: Eye Tracking & Attention Score
class EyeGazeSample(Base):
    """Real-time eye gaze tracking samples."""
    __tablename__ = "eye_gaze_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    gaze_x: Mapped[float] = mapped_column(Float)  # Normalized 0-1
    gaze_y: Mapped[float] = mapped_column(Float)  # Normalized 0-1
    pupil_diameter_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)  # 0-1, tracking quality
    is_on_screen: Mapped[bool] = mapped_column(Boolean)  # Looking at exam area?
    region_of_interest: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 'question_area', etc.
    timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AttentionScore(Base):
    """Aggregated attention scores per time window."""
    __tablename__ = "attention_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    window_start_time: Mapped[datetime] = mapped_column(DateTime)
    window_end_time: Mapped[datetime] = mapped_column(DateTime)
    attention_percent: Mapped[float] = mapped_column(Float)  # % time looking at screen
    focus_score: Mapped[float] = mapped_column(Float)  # 0-100
    gaze_stability: Mapped[float] = mapped_column(Float)  # 0-1, higher = more stable
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# PHASE 1E: Zero Trust Architecture
class DeviceVerificationCheck(Base):
    """Device verification checks throughout exam."""
    __tablename__ = "device_verification_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    check_type: Mapped[str] = mapped_column(String(100), index=True)  # 'device_fingerprint', 'vpn_detection'
    check_timestamp: Mapped[datetime] = mapped_column(DateTime)
    result: Mapped[str] = mapped_column(String(20))  # 'pass', 'fail', 'warning'
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Check details
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IdentityReverificationEvent(Base):
    """Planned identity re-verifications during exam."""
    __tablename__ = "identity_reverification_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    scheduled_time: Mapped[datetime] = mapped_column(DateTime)
    actual_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    live_image_base64: Mapped[str | None] = mapped_column(Text, nullable=True)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Certificate(Base):
    """Exam completion certificates with tamper-proof verification."""
    __tablename__ = "certificates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    student_email: Mapped[str] = mapped_column(String(255), index=True)
    exam_code: Mapped[str] = mapped_column(String(100), index=True)
    score_percent: Mapped[float] = mapped_column(Float)
    integrity_band: Mapped[str] = mapped_column(String(50))  # "Highly Reliable", "Moderate", "Critical Risk"
    verification_hash: Mapped[str] = mapped_column(String(255), unique=True, index=True)  # SHA256 for public verification
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvidenceFrame(Base):
    """Captured frames and violation snapshots for evidence review."""
    __tablename__ = "evidence_frames"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    violation_id: Mapped[int | None] = mapped_column(ForeignKey("violations.id"), nullable=True)
    frame_base64: Mapped[str] = mapped_column(Text)  # Compressed frame data
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    frame_index: Mapped[int] = mapped_column(Integer)  # Frame number in sequence
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # Cached AI analysis
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProctorInterventionAction(Base):
    __tablename__ = "proctor_intervention_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(80), index=True)  # warn, lock_navigation, force_reverify, pause_timer
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    issued_by: Mapped[str] = mapped_column(String(255), default="admin@proctor360.com")
    status: Mapped[str] = mapped_column(String(30), default="issued")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProctorChatMessage(Base):
    __tablename__ = "proctor_chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    sender_role: Mapped[str] = mapped_column(String(30), index=True)  # admin, student
    sender_email: Mapped[str] = mapped_column(String(255), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvidenceChainEntry(Base):
    __tablename__ = "evidence_chain_entries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(50), index=True)  # frame, audio, chat, intervention
    source_id: Mapped[str] = mapped_column(String(120), index=True)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)
    previous_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chain_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CandidateAppeal(Base):
    __tablename__ = "candidate_appeals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    student_email: Mapped[str] = mapped_column(String(255), index=True)
    reason: Mapped[str] = mapped_column(Text)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)  # open, reviewing, accepted, rejected
    decision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DeviceTrustSnapshot(Base):
    __tablename__ = "device_trust_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    trust_score: Mapped[float] = mapped_column(Float, default=100.0)
    risk_band: Mapped[str] = mapped_column(String(20), default="low")
    signals: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class NetworkHeartbeat(Base):
    __tablename__ = "network_heartbeats"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    packet_loss_percent: Mapped[float] = mapped_column(Float, default=0.0)
    jitter_ms: Mapped[float] = mapped_column(Float, default=0.0)
    offline_buffer_count: Mapped[int] = mapped_column(Integer, default=0)
    grace_applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdaptiveExamDecision(Base):
    __tablename__ = "adaptive_exam_decisions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    question_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    previous_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    chosen_difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    rationale: Mapped[str] = mapped_column(Text, default="adaptive policy")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SubjectiveAnswer(Base):
    __tablename__ = "subjective_answers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("exam_sessions.id"), index=True)
    student_email: Mapped[str] = mapped_column(String(255), index=True)
    question_prompt: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PlagiarismAlert(Base):
    __tablename__ = "plagiarism_alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    session_id_a: Mapped[int] = mapped_column(Integer, index=True)
    session_id_b: Mapped[int] = mapped_column(Integer, index=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="flagged")
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CohortRiskSnapshot(Base):
    __tablename__ = "cohort_risk_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    exam_code: Mapped[str] = mapped_column(String(100), index=True)
    hour_bucket: Mapped[str] = mapped_column(String(30), index=True)
    center: Mapped[str] = mapped_column(String(100), default="global")
    avg_risk: Mapped[float] = mapped_column(Float, default=0.0)
    high_risk_count: Mapped[int] = mapped_column(Integer, default=0)
    total_sessions: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_email: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(40), index=True)  # super_admin, tenant_admin, proctor, reviewer
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True, default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TenantBranding(Base):
    __tablename__ = "tenant_branding"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True, unique=True)
    brand_name: Mapped[str] = mapped_column(String(255), default="Proctor360")
    primary_color: Mapped[str] = mapped_column(String(20), default="#000000")
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    policy_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IncidentRoute(Base):
    __tablename__ = "incident_routes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_slug: Mapped[str] = mapped_column(String(100), index=True, default="default")
    channel_type: Mapped[str] = mapped_column(String(30), index=True)  # webhook, slack, teams
    target_url: Mapped[str] = mapped_column(Text)
    severity_min: Mapped[str] = mapped_column(String(20), default="medium")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IncidentNotificationLog(Base):
    __tablename__ = "incident_notification_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    route_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    response_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CertificateRevocation(Base):
    __tablename__ = "certificate_revocations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    certificate_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    verification_hash: Mapped[str] = mapped_column(String(255), index=True)
    reason: Mapped[str] = mapped_column(Text)
    revoked_by: Mapped[str] = mapped_column(String(255), default="admin@proctor360.com")
    revoked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QuestionQualityMetric(Base):
    __tablename__ = "question_quality_metrics"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    question_id: Mapped[int] = mapped_column(Integer, index=True, unique=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    correct_rate: Mapped[float] = mapped_column(Float, default=0.0)
    discrimination_index: Mapped[float] = mapped_column(Float, default=0.0)
    option_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    flag_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


