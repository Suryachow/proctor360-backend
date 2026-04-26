from pydantic import BaseModel, Field


class StartExamRequest(BaseModel):
    exam_code: str
    verification_code: str
    live_image_base64: str
    live_id_image_base64: str | None = None
    device_fingerprint: str | None = None


class SessionResponse(BaseModel):
    session_id: int
    status: str
    risk_score: float


class ExamQuestionOut(BaseModel):
    id: int
    prompt: str
    options: list[str]


class AvailableExamOut(BaseModel):
    exam_code: str
    title: str
    question_count: int
    is_public: bool


class AnswerSaveRequest(BaseModel):
    session_id: int
    question_id: int
    selected_option: str = Field(pattern="^[ABCDabcd]$")


class AnswerSaveResponse(BaseModel):
    ok: bool
    answered_count: int


class SessionAnswersOut(BaseModel):
    session_id: int
    answers: dict[int, str]


class AssignedExamOut(BaseModel):
    exam_code: str
    title: str
    question_count: int
    has_attempt: bool
    is_public: bool


class TopicBreakdownOut(BaseModel):
    topic: str
    correct: int
    incorrect: int
    unanswered: int
    mastery_percent: float


class ExamReportOut(BaseModel):
    stage: str
    overall_summary: str
    integrity_band: str
    strengths: list[str]
    improvement_areas: list[str]
    recommended_actions: list[str]
    topic_breakdown: list[TopicBreakdownOut]
    score_percent: float
    evidence_summary: list[dict] = []
    evidence_count: int = 0
    credibility_score: float | None = None
    client_proctor_metrics: dict | None = None


class SubmitExamResponse(BaseModel):
    ok: bool
    status: str
    correct_answers: int
    total_questions: int
    score_percent: float
    report: ExamReportOut


class AttemptedExamOut(BaseModel):
    session_id: int
    exam_code: str
    title: str
    status: str
    started_at: str
    ended_at: str | None = None
    correct_answers: int
    total_questions: int
    score_percent: float


class StudentDashboardOut(BaseModel):
    assigned_exams: list[AssignedExamOut]
    attempted_exams: list[AttemptedExamOut]


class EventRequest(BaseModel):
    session_id: int
    event_type: str
    detail: str = ""
    metadata: dict = Field(default_factory=dict)


class FrameAnalyzeRequest(BaseModel):
    session_id: int
    image_base64: str
    include_advanced: bool = False
    device_fingerprint: str | None = None
