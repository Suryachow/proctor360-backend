from datetime import datetime
from pydantic import BaseModel, Field


class ViolationOut(BaseModel):
    id: int
    session_id: int
    event_type: str
    severity: str
    risk_delta: float
    detail: str
    ai_confidence: float | None = None
    policy_category: str | None = None
    policy_action: str | None = None
    human_review_required: bool = False
    explainability: str | None = None
    created_at: datetime


class SessionOut(BaseModel):
    session_id: int
    student_email: str
    exam_code: str
    status: str
    risk_score: float


class QuestionCreate(BaseModel):
    prompt: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    correct_option: str = Field(pattern="^[ABCDabcd]$")
    topic: str = "general"


class BulkQuestionUploadRequest(BaseModel):
    questions: list[QuestionCreate]


class ExamCreateRequest(BaseModel):
    code: str
    title: str
    question_ids: list[int]
    student_emails: list[str] = Field(default_factory=list)


class ExamCreateResponse(BaseModel):
    exam_code: str
    title: str
    verification_code: str
    question_count: int
    assigned_students: int
    is_public: bool


class AutoGenerateExamRequest(BaseModel):
    topic: str
    difficulty: str = Field(pattern="^(easy|medium|hard)$")
    question_count: int = Field(ge=3, le=50)
    image_question_count: int = Field(default=0, ge=0, le=20)
    diagram_question_count: int = Field(default=0, ge=0, le=20)
    admin_request: str | None = None
    code: str | None = None
    title: str | None = None
    student_emails: list[str] = Field(default_factory=list)


class AutoGenerateExamResponse(ExamCreateResponse):
    topic: str
    difficulty: str
    image_question_count: int
    diagram_question_count: int
    generated_question_ids: list[int]


class ProctorIncidentSnipOut(BaseModel):
    timestamp: datetime
    event_type: str
    severity: str
    detail: str
    ai_confidence: float | None = None
    policy_category: str | None = None
    policy_action: str | None = None
    human_review_required: bool = False
    explainability: str | None = None


class ProctorExamReportOut(BaseModel):
    session_id: int
    exam_code: str
    student_email: str
    status: str
    risk_score: float
    unusual_activity_detected: bool
    incident_snips: list[ProctorIncidentSnipOut]
    recommendation: str
