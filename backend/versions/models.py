from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class DirectoryManifest(Base):
    __tablename__ = "directory_manifests"

    version_id: Mapped[int] = mapped_column(ForeignKey("outline_versions.id"), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    base_version_id: Mapped[int | None] = mapped_column(ForeignKey("outline_versions.id"))
    # 小量节点元数据按版本冻结；正文仍引用原内容表，不复制正文或学习记录。
    tree_json: Mapped[dict] = mapped_column(JSON)
    brief_json: Mapped[dict | None] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DirectoryContentSelection(Base):
    __tablename__ = "directory_content_selections"

    outline_version_id: Mapped[int] = mapped_column(ForeignKey("directory_manifests.version_id"), primary_key=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("points.id"), primary_key=True)
    content_version_id: Mapped[int] = mapped_column(ForeignKey("point_content_versions.id"))


class DirectoryDraft(Base):
    __tablename__ = "directory_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    base_version_id: Mapped[int] = mapped_column(ForeignKey("directory_manifests.version_id"))
    revision: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="editing")
    additions_json: Mapped[list] = mapped_column(JSON, default=list)
    # 供后续资料/局部结构工作流沿用，AI 操作开始时固定职责路由。
    routing_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    published_version_id: Mapped[int | None] = mapped_column(ForeignKey("outline_versions.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
