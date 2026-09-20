from datetime import datetime
from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base
from backend.materials.models import now


class PageRecognition(Base):
    __tablename__ = "material_page_recognitions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("material_batches.id"), index=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("material_files.id"))
    process_id: Mapped[str] = mapped_column(ForeignKey("material_processes.id"))
    page: Mapped[int]
    input_hash: Mapped[str] = mapped_column(String(64), index=True)
    image_hash: Mapped[str] = mapped_column(String(64))
    preview: Mapped[str] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text)
    route_json: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    review: Mapped[str] = mapped_column(String(24), default="pending")
    review_note: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(default=now)


class PageAdoption(Base):
    """每页的草稿选择；分析开始后固定进 manifest。"""
    __tablename__ = "material_page_adoptions"
    file_id: Mapped[str] = mapped_column(ForeignKey("material_files.id"), primary_key=True)
    page: Mapped[int] = mapped_column(primary_key=True)
    process_id: Mapped[str] = mapped_column(ForeignKey("material_processes.id"))
    recognition_id: Mapped[str] = mapped_column(ForeignKey("material_page_recognitions.id"))
    recognition_revision: Mapped[int]
    result_hash: Mapped[str] = mapped_column(String(64))
