from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


ACTIVE_JOB_SQL = (
    "status IN ('queued', 'planning', 'writing', 'reviewing', 'revising', 'needs_attention')"
)


class SectionPlan(Base):
    __tablename__ = "section_plans"
    __table_args__ = (
        UniqueConstraint(
            "section_id", "version_number", name="uq_section_plan_version"
        ),
        UniqueConstraint(
            "section_id", "context_hash", name="uq_section_plan_context"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sections.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    context_hash: Mapped[str] = mapped_column(String(64))
    plan_json: Mapped[dict] = mapped_column(JSON)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class PointContentVersion(Base):
    __tablename__ = "point_content_versions"
    __table_args__ = (
        UniqueConstraint(
            "point_id", "version_number", name="uq_point_content_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    point_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("points.id"), index=True
    )
    # 为 null 仅用于诚实包装早期 Point.content_markdown；新 AI 版本必须有规划。
    plan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("section_plans.id")
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    origin: Mapped[str] = mapped_column(String(32), default="generated")
    content_json: Mapped[dict] = mapped_column(JSON)
    review_json: Mapped[dict] = mapped_column(JSON)
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    context_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class PointContentSelection(Base):
    __tablename__ = "point_content_selections"

    point_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("points.id"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("point_content_versions.id"), unique=True
    )
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LearningGenerationJob(Base):
    __tablename__ = "learning_generation_jobs"
    __table_args__ = (
        # 规划覆盖整个小节：同一小节只跑一个内容任务，避免并发生成冲突分工。
        Index(
            "uq_learning_job_active_version_section",
            "outline_version_id",
            "section_id",
            unique=True,
            postgresql_where=text(f"outline_version_id IS NOT NULL AND {ACTIVE_JOB_SQL}"),
            sqlite_where=text(f"outline_version_id IS NOT NULL AND {ACTIVE_JOB_SQL}"),
        ),
        Index(
            "uq_learning_job_active_legacy_section",
            "section_id",
            unique=True,
            postgresql_where=text(f"outline_version_id IS NULL AND {ACTIVE_JOB_SQL}"),
            sqlite_where=text(f"outline_version_id IS NULL AND {ACTIVE_JOB_SQL}"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id"), index=True
    )
    section_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sections.id"), index=True
    )
    point_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("points.id"), index=True
    )
    # null 只代表迁移前的历史任务；新任务始终固定目录版本。
    outline_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("directory_manifests.version_id"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued")
    revision_count: Mapped[int] = mapped_column(Integer, default=0)
    plan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("section_plans.id")
    )
    content_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("point_content_versions.id")
    )
    context_hash: Mapped[str] = mapped_column(String(64))
    structure_hash: Mapped[str] = mapped_column(String(64))
    context_json: Mapped[dict] = mapped_column(JSON)
    # 任务开始时一次性冻结所有可能执行的 content.* 职责。
    routing_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    expected_selected_version_id: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class LearningJobStep(Base):
    __tablename__ = "learning_job_steps"
    __table_args__ = (
        UniqueConstraint("job_id", "step_key", name="uq_learning_job_step"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_generation_jobs.id"), index=True
    )
    step_key: Mapped[str] = mapped_column(String(64))
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="running")
    output_json: Mapped[dict | list | None] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
