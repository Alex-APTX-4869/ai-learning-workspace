from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class LlmProvider(Base):
    __tablename__ = "llm_providers"
    __table_args__ = (
        Index(
            "uq_llm_providers_one_active",
            "is_active",
            unique=True,
            postgresql_where=text("is_active"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str] = mapped_column(String(1000))
    model: Mapped[str] = mapped_column(String(300))
    # 这里只存钥匙串条目的随机引用，绝不存 API key 本身。
    key_ref: Mapped[str] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        # 凭据定位符也属于内部实现；调试输出只展示公开身份。
        return f"LlmProvider(id={self.id!r}, name={self.name!r}, is_active={self.is_active!r})"


class LLMModelConfig(Base):
    """一个连接下可调用的具体模型及其非敏感能力元数据。"""

    __tablename__ = "llm_model_configs"
    __table_args__ = (
        UniqueConstraint("provider_id", "model", name="uq_llm_model_provider_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(ForeignKey("llm_providers.id"), index=True)
    label: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(300))
    capabilities_json: Mapped[dict] = mapped_column(JSON)
    runtime_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"LLMModelConfig(id={self.id!r}, provider_id={self.provider_id!r}, "
            f"model={self.model!r}, revision={self.revision!r})"
        )


class LLMRoleBinding(Base):
    """把固定职责绑定到全局、课程或创建/目录草稿。"""

    __tablename__ = "llm_role_bindings"
    __table_args__ = (
        UniqueConstraint("scope_key", "role_key", name="uq_llm_role_binding_scope_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    scope_type: Mapped[str] = mapped_column(String(24))
    scope_id: Mapped[str | None] = mapped_column(String(64))
    # global 使用固定值，其余是 type:id；避免 NULL 在唯一约束中的特殊语义。
    scope_key: Mapped[str] = mapped_column(String(96))
    role_key: Mapped[str] = mapped_column(String(80), index=True)
    model_config_id: Mapped[int] = mapped_column(ForeignKey("llm_model_configs.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"LLMRoleBinding(id={self.id!r}, scope_type={self.scope_type!r}, "
            f"role_key={self.role_key!r}, revision={self.revision!r})"
        )
