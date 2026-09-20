from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class TutorSession(Base):
    # 新表保留旧会话 ID；旧表直到迁移及回退验证完毕均不删除。
    __tablename__ = "version_tutor_sessions"
    __table_args__ = (
        UniqueConstraint("outline_version_id", "content_version_id", name="uq_tutor_outline_content"),
        Index("uq_tutor_legacy_content", "content_version_id", unique=True,
              postgresql_where=text("outline_version_id IS NULL"), sqlite_where=text("outline_version_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    point_id: Mapped[int] = mapped_column(ForeignKey("points.id"), index=True)
    outline_version_id: Mapped[int | None] = mapped_column(ForeignKey("directory_manifests.version_id"))
    content_version_id: Mapped[int] = mapped_column(ForeignKey("point_content_versions.id"))
    card_index: Mapped[int] = mapped_column(Integer, default=0)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(default=False)
    pending_request_id: Mapped[str | None] = mapped_column(String(36))
    responses: Mapped[dict] = mapped_column(JSON, default=dict)


class TutorTurn(Base):
    __tablename__ = "version_tutor_turns"
    __table_args__ = (UniqueConstraint("session_id", "request_id", name="uq_version_tutor_request"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("version_tutor_sessions.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    payload_hash: Mapped[str] = mapped_column(String(64))
    revision_before: Mapped[int] = mapped_column(Integer)
    card_id: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    # 每条用户消息单独冻结讲师模型；翻页/作答等纯程序操作保持为空。
    routing_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    user_message: Mapped[str | None] = mapped_column(Text)
    reply_markdown: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    teacher_action: Mapped[str | None] = mapped_column(String(32))
