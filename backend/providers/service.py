from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.core.config import nus_settings
from backend.database import get_engine
from backend.providers import secrets
from backend.providers.models import LlmProvider
from backend.providers.routing import ensure_first_model, sync_legacy_global_default
from backend.providers.schemas import (
    ProviderCreate,
    ProviderRead,
    ProviderRuntime,
)


def _saved_read(provider: LlmProvider) -> ProviderRead:
    return ProviderRead(
        id=provider.id,
        name=provider.name,
        base_url=provider.base_url,
        model=provider.model,
        is_active=provider.is_active,
        source="saved",
        has_api_key=True,
    )


def _environment_read(*, active: bool) -> ProviderRead:
    config = _environment_config()
    return ProviderRead(
        id=None,
        name="NUS (.env)",
        base_url=str(config.base_url).rstrip("/"),
        model=config.model,
        is_active=active,
        source="environment",
        has_api_key=True,
    )


def _environment_config() -> ProviderCreate:
    key, url, model = nus_settings()
    try:
        # .env 与 UI 保存的 provider 共用同一组 URL/长度安全边界。
        return ProviderCreate(
            name="NUS (.env)",
            base_url=url,
            model=model,
            api_key=key,
            activate=False,
        )
    except ValidationError as error:
        raise RuntimeError("NUS 环境变量中的模型配置无效") from error


def list_providers(db: Session) -> list[ProviderRead]:
    saved = [
        _saved_read(item)
        for item in db.scalars(select(LlmProvider).order_by(LlmProvider.id)).all()
    ]
    try:
        environment = _environment_read(
            active=not any(item.is_active for item in saved)
        )
    except RuntimeError:
        return saved
    return [environment, *saved]


def get_active_provider_read(db: Session) -> ProviderRead:
    provider = db.scalar(select(LlmProvider).where(LlmProvider.is_active.is_(True)))
    if provider is not None:
        return _saved_read(provider)
    try:
        return _environment_read(active=True)
    except RuntimeError as error:
        raise HTTPException(404, "尚未配置可用的模型供应商。") from error


def create_provider(db: Session, data: ProviderCreate) -> ProviderRead:
    key_ref = uuid4().hex
    secrets.set_api_key(key_ref, data.api_key.get_secret_value())
    try:
        if data.activate:
            db.execute(update(LlmProvider).values(is_active=False))
            db.flush()
        provider = LlmProvider(
            name=data.name,
            base_url=str(data.base_url).rstrip("/"),
            model=data.model,
            key_ref=key_ref,
            is_active=data.activate,
        )
        db.add(provider)
        db.flush()
        # 旧 API 仍一次提交连接和首个模型；新结构在数据库中把两者分开。
        first_model = ensure_first_model(db, provider)
        if data.activate:
            sync_legacy_global_default(db, first_model)
        result = _saved_read(provider)
        db.commit()
    except Exception:
        db.rollback()
        secrets.delete_api_key(key_ref)
        raise
    return result


def activate_provider(db: Session, provider_id: int) -> ProviderRead:
    providers = db.scalars(select(LlmProvider).with_for_update()).all()
    provider = next((item for item in providers if item.id == provider_id), None)
    if provider is None:
        raise HTTPException(404, "没有找到这个模型供应商。")
    # 激活前确认钥匙串条目仍存在；密钥值不会进入响应或日志。
    secrets.get_api_key(provider.key_ref)
    for item in providers:
        item.is_active = item.id == provider_id
    sync_legacy_global_default(db, ensure_first_model(db, provider))
    db.commit()
    db.refresh(provider)
    return _saved_read(provider)


def activate_environment(db: Session) -> ProviderRead:
    try:
        environment = _environment_read(active=True)
    except RuntimeError as error:
        raise HTTPException(404, "NUS 环境变量尚未完整配置。") from error
    providers = db.scalars(select(LlmProvider).with_for_update()).all()
    for provider in providers:
        provider.is_active = False
    # 环境变量没有数据库模型行；只撤销兼容默认，不触碰专项职责。
    sync_legacy_global_default(db, None)
    db.commit()
    return environment


def resolve_active_provider() -> ProviderRuntime:
    with Session(get_engine()) as db:
        provider = db.scalar(
            select(LlmProvider).where(LlmProvider.is_active.is_(True))
        )
        if provider is not None:
            return ProviderRuntime(
                name=provider.name,
                base_url=provider.base_url,
                model=provider.model,
                api_key=secrets.get_api_key(provider.key_ref),
                source="saved",
            )

    try:
        config = _environment_config()
    except RuntimeError as error:
        raise HTTPException(503, "请先配置模型供应商或 NUS 环境变量。") from error
    return ProviderRuntime(
        name="NUS (.env)",
        base_url=str(config.base_url).rstrip("/"),
        model=config.model,
        api_key=config.api_key,
        source="environment",
    )
