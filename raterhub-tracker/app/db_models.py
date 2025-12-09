# app/db_models.py
from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    Float,
    ForeignKey,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False)
    last_login_at = Column(DateTime, nullable=True)
    password_hash = Column(String, nullable=True)
    auth_provider = Column(String, nullable=False)
    google_sub = Column(String, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    # NEW: user timezone (IANA name like "America/Denver")
    timezone = Column(String, nullable=False, default="UTC")



class Session(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    public_id = Column(String, unique=True, index=True, default=lambda: str(uuid4()))

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    # Target minutes per question (e.g. 5.5)
    target_minutes_per_question = Column(Float, nullable=True)

    # Current question tracking
    current_question_index = Column(Integer, nullable=True)
    current_question_started_at = Column(DateTime, nullable=True)

    # Pause tracking
    pause_accumulated_seconds = Column(Float, nullable=False, default=0.0)
    is_paused = Column(Boolean, nullable=False, default=False)
    pause_started_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="sessions")
    events = relationship(
        "Event",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    questions = relationship(
        "Question",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)

    type = Column(String, nullable=False)  # "NEXT", "PAUSE", "EXIT"
    timestamp = Column(DateTime, nullable=False)

    # Relationships
    session = relationship("Session", back_populates="events")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)

    index = Column(Integer, nullable=False)  # 1-based question index within session

    started_at = Column(DateTime, nullable=False)
    ended_at = Column(DateTime, nullable=False)

    # Raw time from started_at → ended_at
    raw_seconds = Column(Float, nullable=False)

    # Active time (raw minus pauses)
    active_seconds = Column(Float, nullable=False)

    # Relationships
    session = relationship("Session", back_populates="questions")
