from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base

def now():
    return datetime.now(timezone.utc)

class MaterialBatch(Base):
    __tablename__ = "material_batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    intro: Mapped[str] = mapped_column(Text, default="")
    completeness: Mapped[str] = mapped_column(String(16), default="partial")
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(24), default="editing", index=True)
    manifest_json: Mapped[dict | None] = mapped_column(JSON)
    context_json: Mapped[dict | None] = mapped_column(JSON)
    routing_snapshot_json: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    intake_id: Mapped[int | None] = mapped_column(ForeignKey("intake_sessions.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class MaterialFile(Base):
    __tablename__ = "material_files"
    __table_args__ = (UniqueConstraint("batch_id", "request_id", name="uq_material_upload_request"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("material_batches.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36))
    filename: Mapped[str] = mapped_column(String(240))
    suffix: Mapped[str] = mapped_column(String(10))
    sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int]
    annotations_json: Mapped[list] = mapped_column(JSON, default=list)
    included: Mapped[bool] = mapped_column(default=True)
    text_only_accepted: Mapped[bool] = mapped_column(default=False)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class MaterialProcess(Base):
    __tablename__ = "material_processes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("material_files.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    report_json: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class MaterialAnalysisStep(Base):
    __tablename__ = "material_analysis_steps"
    __table_args__ = (UniqueConstraint("batch_id", "input_hash", name="uq_material_analysis_input"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("material_batches.id"), index=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="running")
    result_json: Mapped[dict | None] = mapped_column(JSON)
