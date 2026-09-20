from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class IntakeSession(Base):
    """一次创建课程前的需求确认会话。"""

    __tablename__ = "intake_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    initial_name: Mapped[str] = mapped_column(String(200))
    initial_intro: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="choosing_depth")
    depth_options: Mapped[list[dict]] = mapped_column(JSON, default=list)
    selected_depth: Mapped[dict | None] = mapped_column(JSON)
    question_count: Mapped[int | None]
    current_question: Mapped[dict | None] = mapped_column(JSON)
    brief: Mapped[dict | None] = mapped_column(JSON)
    # 一次需求确认从第一轮起固定所有相关职责的非敏感模型路由。
    routing_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id"), unique=True
    )
    # 每次成功推进状态都加一。模型返回后先比较版本，避免旧结果覆盖新状态。
    version: Mapped[int] = mapped_column(default=0)
    extension_proposal: Mapped[dict | None] = mapped_column(JSON)
    extension_history: Mapped[list] = mapped_column(JSON, default=list)
    turns: Mapped[list[IntakeTurn]] = relationship(
        back_populates="session",
        order_by="IntakeTurn.position",
        cascade="all, delete-orphan",
    )

    @property
    def answers(self) -> list[dict]:
        """保持 API 简洁，同时让数据库中的每轮记录可以独立审计。"""
        return [turn.answer_json for turn in self.turns if turn.answer_json]


class IntakeTurn(Base):
    """一次提问及其回答；每题独立保存，便于恢复和以后重做。"""

    __tablename__ = "intake_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_intake_turn_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("intake_sessions.id"))
    position: Mapped[int]
    question_json: Mapped[dict] = mapped_column(JSON)
    answer_json: Mapped[dict | None] = mapped_column(JSON)
    session: Mapped[IntakeSession] = relationship(back_populates="turns")
