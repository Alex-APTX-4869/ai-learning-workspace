from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class OutlineVersion(Base):
    __tablename__ = "outline_versions"
    __table_args__ = (
        UniqueConstraint(
            "course_id", "version_number", name="uq_outline_course_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(200))
    outline_json: Mapped[dict] = mapped_column(JSON)
    additional_requirements: Mapped[str] = mapped_column(Text, default="")
    reference_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("outline_versions.id")
    )
    # 保存生成这版目录时实际冻结的非敏感模型路由；历史行为空。
    routing_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class CourseOutlineSelection(Base):
    __tablename__ = "course_outline_selections"

    course_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("courses.id"), primary_key=True
    )
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outline_versions.id"), unique=True
    )
