from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex


def now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    # Brand kit: default caption preset, watermark, accent colour …
    brand_kit: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Upload(Base):
    """A resumable, chunked upload in progress."""

    __tablename__ = "uploads"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer)
    received: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="uploading")  # uploading|complete
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(20))  # upload | url
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # draft -> queued -> processing -> ready | failed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    media: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # probe info
    analysis: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # summary + engine notes
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)

    clips: Mapped[list[Clip]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Clip.rank"
    )


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0)
    start: Mapped[float] = mapped_column(Float)
    end: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(255), default="")
    hook: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(40), default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Everything the editor controls: captions, aspect, crop, overlays, audio …
    edits: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reframe: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # crop path from analysis
    publish: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Post/schedule plan: {status: draft|scheduled|posted, scheduled_at, timezone, platforms: {...}, posted_at}
    post: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # pending | rendering | rendered | failed
    render_status: Mapped[str] = mapped_column(String(20), default="pending")
    render_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumb_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    srt_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rendered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    favorite: Mapped[bool] = mapped_column(default=False)
    feedback: Mapped[int] = mapped_column(Integer, default=0)  # -1, 0, +1
    feedback_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    project: Mapped[Project] = relationship(back_populates="clips")


class Job(Base):
    """Persistent background job. The worker claims queued rows atomically."""

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    clip_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))  # generate | render | publish
    # queued | running | succeeded | failed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)  # timeline of stages
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
