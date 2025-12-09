# app/models.py
from datetime import datetime
from typing import Optional, Literal

from pydantic import BaseModel, Field, EmailStr

EventType = Literal["NEXT", "PAUSE", "EXIT", "UNDO"]


class EventIn(BaseModel):
    """Event sent from the browser JS / client."""
    type: EventType = Field(..., description="Event type: NEXT, PAUSE, UNDO or EXIT")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Client-side timestamp (ISO 8601). Server will also record its own."
    )
    

class EventOut(BaseModel):
    """Basic response confirming event was processed."""
    status: str
    message: str
    server_timestamp: datetime
    session_id: str
    total_questions: int
    last_event_type: EventType
    last_question_index: int

    # For NEXT/EXIT when a question is closed
    last_question_active_seconds: Optional[float] = None
    last_question_raw_seconds: Optional[float] = None
    last_question_active_mmss: Optional[str] = None


class SessionQuestionSummary(BaseModel):
    index: int
    started_at: datetime
    ended_at: datetime
    raw_seconds: float
    active_seconds: float
    active_mmss: str
    over_under_target_seconds: Optional[float] = None
    over_under_target_mmss: Optional[str] = None


class SessionSummary(BaseModel):
    session_id: str
    user_external_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    is_active: bool
    target_minutes_per_question: float

    total_questions: int
    total_raw_seconds: float
    total_active_seconds: float
    avg_active_seconds: float
    avg_active_mmss: str

    pace_label: str
    pace_emoji: str
    score: int

    questions: list[SessionQuestionSummary]


class HealthStatus(BaseModel):
    status: str
    timestamp: datetime

class TodaySessionItem(BaseModel):
    session_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    is_active: bool

    total_questions: int
    total_active_seconds: float
    avg_active_seconds: float
    avg_active_mmss: str

    pace_label: str
    pace_emoji: str
    score: int


class TodaySummary(BaseModel):
    date: datetime
    user_external_id: str

    total_sessions: int
    total_questions: int
    total_active_seconds: float
    total_active_mmss: str

    sessions: list[TodaySessionItem]

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: int
    email: EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str
