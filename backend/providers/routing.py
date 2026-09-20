from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.courses.models import Course
from backend.database import get_engine
from backend.intake.models import IntakeSession
from backend.providers import secrets
from backend.providers.models import LLMModelConfig, LLMRoleBinding, LlmProvider
from backend.providers.roles import CAPABILITY_KEYS, ROLE_BY_KEY, ROLE_DEFINITIONS, get_role
from backend.providers.schemas import (
    CapabilityName,
    ModelCapabilityDeclaration,
    ModelCapabilityStatus,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
    ModelRuntimePolicy,
    ResolvedRoleRead,
    RoutingSnapshot,
    RoleBindingRead,
    RoleBindingWrite,
    RoleDefinitionRead,
    RoleRuntime,
    ScopeType,
)
from backend.versions.models import DirectoryDraft


STRICTLY_VERIFIED_CAPABILITIES = {"vision", "embeddings"}


def _state(*, supported: bool) -> dict:
    return {
        "supported": supported,
        "status": "unverified" if supported else "unsupported",
        "checked_at": None,
        "error_code": None,
    }


def initial_capabilities(declaration: ModelCapabilityDeclaration) -> dict:
    values = declaration.model_dump()
    return {key: _state(supported=bool(values[key])) for key in CAPABILITY_KEYS}


def legacy_capabilities() -> dict:
    """旧连接已实际用于文本、结构化结果和目录流，仍标明未独立检测。"""
    return initial_capabilities(
        ModelCapabilityDeclaration(
            text_chat=True,
            structured_output=True,
            streaming=True,
            vision=False,
            embeddings=False,
        )
    )


def _model_read(model: LLMModelConfig) -> ModelConfigRead:
    return ModelConfigRead(
        id=model.id,
        provider_id=model.provider_id,
        label=model.label,
        model=model.model,
        capabilities=ModelCapabilityStatus.model_validate(model.capabilities_json),
        runtime_policy=ModelRuntimePolicy.model_validate(model.runtime_policy_json or {}),
        is_enabled=model.is_enabled,
        revision=model.revision,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def ensure_first_model(db: Session, provider: LlmProvider) -> LLMModelConfig:
    model = db.scalar(
        select(LLMModelConfig)
        .where(LLMModelConfig.provider_id == provider.id)
        .order_by(LLMModelConfig.id)
    )
    if model is not None:
        return model
    now = datetime.now(timezone.utc)
    model = LLMModelConfig(
        provider_id=provider.id,
        label=provider.model,
        model=provider.model,
        capabilities_json=legacy_capabilities(),
        runtime_policy_json={},
        is_enabled=True,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(model)
    db.flush()
    return model


def sync_legacy_global_default(
    db: Session, model: LLMModelConfig | None
) -> None:
    """让旧“切换当前供应商”按钮与新的全局默认对话路由保持一致。"""
    binding = db.scalar(
        select(LLMRoleBinding)
        .where(
            LLMRoleBinding.scope_key == "global",
            LLMRoleBinding.role_key == "default.chat",
        )
        .with_for_update()
    )
    if model is None:
        if binding is not None:
            db.delete(binding)
        return
    now = datetime.now(timezone.utc)
    if binding is None:
        db.add(
            LLMRoleBinding(
                scope_type="global",
                scope_id=None,
                scope_key="global",
                role_key="default.chat",
                model_config_id=model.id,
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
        return
    binding.model_config_id = model.id
    binding.revision += 1
    binding.updated_at = now


def list_models(db: Session, provider_id: int | None = None) -> list[ModelConfigRead]:
    statement = select(LLMModelConfig).order_by(LLMModelConfig.provider_id, LLMModelConfig.id)
    if provider_id is not None:
        if db.get(LlmProvider, provider_id) is None:
            raise HTTPException(404, "没有找到这个模型连接。")
        statement = statement.where(LLMModelConfig.provider_id == provider_id)
    return [_model_read(item) for item in db.scalars(statement).all()]


def get_model(db: Session, model_config_id: int) -> LLMModelConfig:
    model = db.get(LLMModelConfig, model_config_id)
    if model is None:
        raise HTTPException(404, "没有找到这个模型配置。")
    return model


def create_model(
    db: Session, provider_id: int, data: ModelConfigCreate
) -> ModelConfigRead:
    if db.get(LlmProvider, provider_id) is None:
        raise HTTPException(404, "没有找到这个模型连接。")
    now = datetime.now(timezone.utc)
    model = LLMModelConfig(
        provider_id=provider_id,
        label=data.label,
        model=data.model,
        capabilities_json=initial_capabilities(data.capabilities),
        runtime_policy_json=data.runtime_policy.model_dump(exclude_none=True),
        is_enabled=True,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(model)
    try:
        db.flush()
        result = _model_read(model)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "这个连接下已存在同名模型配置。") from error
    return result


def _merge_capabilities(current: dict, declaration: ModelCapabilityDeclaration) -> dict:
    declared = declaration.model_dump()
    updated: dict[str, dict] = {}
    for capability in CAPABILITY_KEYS:
        supported = bool(declared[capability])
        previous = current.get(capability, {})
        if not supported:
            updated[capability] = _state(supported=False)
        elif previous.get("supported"):
            updated[capability] = {
                "supported": True,
                "status": previous.get("status", "unverified"),
                "checked_at": previous.get("checked_at"),
                "error_code": previous.get("error_code"),
            }
        else:
            updated[capability] = _state(supported=True)
    return updated


def update_model(
    db: Session, model_config_id: int, data: ModelConfigUpdate
) -> ModelConfigRead:
    model = db.scalar(
        select(LLMModelConfig)
        .where(LLMModelConfig.id == model_config_id)
        .with_for_update()
    )
    if model is None:
        raise HTTPException(404, "没有找到这个模型配置。")
    if model.revision != data.expected_revision:
        raise HTTPException(409, "模型配置已被更新，请刷新后重试。")
    identifier_changed = data.model is not None and data.model != model.model
    if data.label is not None:
        model.label = data.label
    if data.model is not None:
        model.model = data.model
    if data.runtime_policy is not None:
        model.runtime_policy_json = data.runtime_policy.model_dump(exclude_none=True)
    if data.is_enabled is not None:
        model.is_enabled = data.is_enabled
    if data.capabilities is not None:
        model.capabilities_json = _merge_capabilities(
            model.capabilities_json, data.capabilities
        )
    if identifier_changed:
        # 检测结果属于原模型标识，换模型后不能继续沿用。
        model.capabilities_json = {
            key: _state(supported=bool(value.get("supported")))
            for key, value in model.capabilities_json.items()
        }
    model.revision += 1
    model.updated_at = datetime.now(timezone.utc)
    try:
        db.flush()
        result = _model_read(model)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "这个连接下已存在同名模型配置。") from error
    return result


def reset_capability(
    db: Session,
    model_config_id: int,
    capability: CapabilityName,
    expected_revision: int,
) -> ModelConfigRead:
    model = db.scalar(
        select(LLMModelConfig)
        .where(LLMModelConfig.id == model_config_id)
        .with_for_update()
    )
    if model is None:
        raise HTTPException(404, "没有找到这个模型配置。")
    if model.revision != expected_revision:
        raise HTTPException(409, "模型配置已被更新，请刷新后重试。")
    capabilities = dict(model.capabilities_json)
    current = dict(capabilities[capability])
    if not current.get("supported"):
        raise HTTPException(409, "模型没有声明支持这项能力。")
    capabilities[capability] = _state(supported=True)
    model.capabilities_json = capabilities
    model.revision += 1
    model.updated_at = datetime.now(timezone.utc)
    db.flush()
    result = _model_read(model)
    db.commit()
    return result


def record_capability_verification(
    db: Session,
    model_config_id: int,
    capability: CapabilityName,
    *,
    status: str,
    error_code: str | None = None,
) -> ModelConfigRead:
    """仅供完成真实探测的服务端代码调用，不暴露为可自报的 HTTP API。"""
    if status not in {"verified", "failed"}:
        raise ValueError("检测程序只能记录 verified 或 failed。")
    if status == "failed" and not error_code:
        raise ValueError("失败检测必须提供非敏感错误码。")
    if error_code is not None and (len(error_code) > 80 or not error_code.replace("_", "").replace("-", "").replace(".", "").isalnum()):
        raise ValueError("error_code 只能包含字母、数字、点、横线和下划线。")
    model = db.get(LLMModelConfig, model_config_id)
    if model is None:
        raise HTTPException(404, "没有找到这个模型配置。")
    capabilities = dict(model.capabilities_json)
    current = dict(capabilities[capability])
    if not current.get("supported"):
        raise HTTPException(409, "模型没有声明支持这项能力。")
    capabilities[capability] = {
        "supported": True,
        "status": status,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "error_code": error_code if status == "failed" else None,
    }
    model.capabilities_json = capabilities
    model.revision += 1
    model.updated_at = datetime.now(timezone.utc)
    db.flush()
    return _model_read(model)


def list_roles() -> list[RoleDefinitionRead]:
    return [
        RoleDefinitionRead(
            key=item.key,
            name=item.name,
            description=item.description,
            required_capabilities=list(item.required_capabilities),
            default_role=item.default_role,
        )
        for item in ROLE_DEFINITIONS
    ]


def _canonical_scope(
    db: Session, scope_type: ScopeType, scope_id: str | None
) -> tuple[str | None, str, int | None]:
    """返回规范 ID、唯一 scope_key，以及可继承的 course_id。"""
    if scope_type == "global":
        if scope_id is not None:
            raise HTTPException(422, "global 范围不能提供 scope_id。")
        return None, "global", None
    if scope_id is None or not str(scope_id).strip():
        raise HTTPException(422, f"{scope_type} 范围必须提供 scope_id。")
    raw_id = str(scope_id).strip()
    if scope_type in {"course", "intake"}:
        try:
            numeric_id = int(raw_id)
        except ValueError as error:
            raise HTTPException(422, f"{scope_type} 的 scope_id 必须是整数。") from error
        if numeric_id <= 0:
            raise HTTPException(422, f"{scope_type} 的 scope_id 必须是正整数。")
        canonical_id = str(numeric_id)
        if scope_type == "course":
            if db.get(Course, numeric_id) is None:
                raise HTTPException(404, "没有找到这个课程。")
            return canonical_id, f"course:{canonical_id}", numeric_id
        intake = db.get(IntakeSession, numeric_id)
        if intake is None:
            raise HTTPException(404, "没有找到这次需求确认会话。")
        return canonical_id, f"intake:{canonical_id}", intake.course_id
    draft = db.get(DirectoryDraft, raw_id)
    if draft is None:
        raise HTTPException(404, "没有找到这个目录草稿。")
    return raw_id, f"directory_draft:{raw_id}", draft.course_id


def _model_capability_errors(model: LLMModelConfig, role_key: str) -> list[str]:
    role = get_role(role_key)
    if not model.is_enabled:
        return ["模型已停用"]
    status = ModelCapabilityStatus.model_validate(model.capabilities_json)
    errors: list[str] = []
    for capability in role.required_capabilities:
        state = getattr(status, capability)
        if not state.supported or state.status in {"unsupported", "failed"}:
            errors.append(f"缺少 {capability} 能力")
        elif capability in STRICTLY_VERIFIED_CAPABILITIES and state.status != "verified":
            errors.append(f"{capability} 能力尚未验证")
    return errors


def _binding_read(db: Session, binding: LLMRoleBinding) -> RoleBindingRead:
    return RoleBindingRead(
        id=binding.id,
        scope_type=binding.scope_type,
        scope_id=binding.scope_id,
        role_key=binding.role_key,
        model_config_id=binding.model_config_id,
        revision=binding.revision,
        model=_model_read(get_model(db, binding.model_config_id)),
    )


def list_bindings(
    db: Session,
    *,
    scope_type: ScopeType | None = None,
    scope_id: str | None = None,
) -> list[RoleBindingRead]:
    statement = select(LLMRoleBinding).order_by(
        LLMRoleBinding.scope_type, LLMRoleBinding.scope_id, LLMRoleBinding.role_key
    )
    if scope_type is not None:
        canonical_id, scope_key, _ = _canonical_scope(db, scope_type, scope_id)
        statement = statement.where(LLMRoleBinding.scope_key == scope_key)
    elif scope_id is not None:
        raise HTTPException(422, "提供 scope_id 时也必须提供 scope_type。")
    return [_binding_read(db, item) for item in db.scalars(statement).all()]


def put_binding(
    db: Session, role_key: str, data: RoleBindingWrite
) -> RoleBindingRead:
    try:
        get_role(role_key)
    except ValueError as error:
        raise HTTPException(404, "未知的模型职责。") from error
    canonical_id, scope_key, _ = _canonical_scope(
        db, data.scope_type, data.scope_id
    )
    model = get_model(db, data.model_config_id)
    if errors := _model_capability_errors(model, role_key):
        raise HTTPException(409, "这个模型不能承担该职责：" + "；".join(errors) + "。")
    binding = db.scalar(
        select(LLMRoleBinding)
        .where(
            LLMRoleBinding.scope_key == scope_key,
            LLMRoleBinding.role_key == role_key,
        )
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if binding is None:
        if data.expected_revision != 0:
            raise HTTPException(409, "职责绑定已发生变化，请刷新后重试。")
        binding = LLMRoleBinding(
            scope_type=data.scope_type,
            scope_id=canonical_id,
            scope_key=scope_key,
            role_key=role_key,
            model_config_id=model.id,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        db.add(binding)
    else:
        if binding.revision != data.expected_revision:
            raise HTTPException(409, "职责绑定已被更新，请刷新后重试。")
        binding.model_config_id = model.id
        binding.revision += 1
        binding.updated_at = now
    try:
        db.flush()
        result = _binding_read(db, binding)
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(409, "职责绑定已被其他操作更新，请刷新后重试。") from error
    return result


def delete_binding(
    db: Session,
    role_key: str,
    *,
    scope_type: ScopeType,
    scope_id: str | None,
    expected_revision: int,
) -> None:
    try:
        get_role(role_key)
    except ValueError as error:
        raise HTTPException(404, "未知的模型职责。") from error
    _, scope_key, _ = _canonical_scope(db, scope_type, scope_id)
    binding = db.scalar(
        select(LLMRoleBinding)
        .where(
            LLMRoleBinding.scope_key == scope_key,
            LLMRoleBinding.role_key == role_key,
        )
        .with_for_update()
    )
    if binding is None:
        raise HTTPException(404, "没有找到这个职责绑定。")
    if binding.revision != expected_revision:
        raise HTTPException(409, "职责绑定已被更新，请刷新后重试。")
    db.delete(binding)
    db.commit()


@dataclass(frozen=True)
class _Resolved:
    binding: LLMRoleBinding | None
    model: LLMModelConfig | None
    provider: LlmProvider | None
    source: str
    requested_scope_id: str | None


def _fingerprint(
    *,
    provider_id: int | None,
    base_url: str,
    model_config_id: int | None,
    model_revision: int | None,
    model: str,
    runtime_policy: dict,
) -> str:
    # 只使用冻结的公开配置，不让 key_ref 或密钥进入快照、日志或哈希输入。
    payload = {
        "provider_id": provider_id,
        "base_url": base_url.rstrip("/"),
        "model_config_id": model_config_id,
        "model_revision": model_revision,
        "model": model,
        "runtime_policy": runtime_policy,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _scope_chain(
    db: Session, scope_type: ScopeType, scope_id: str | None
) -> tuple[str | None, list[tuple[str, str]]]:
    canonical_id, scope_key, course_id = _canonical_scope(db, scope_type, scope_id)
    scopes = [(scope_type, scope_key)]
    if scope_type in {"intake", "directory_draft"} and course_id is not None:
        scopes.append(("course", f"course:{course_id}"))
    if scope_type != "global":
        scopes.append(("global", "global"))
    return canonical_id, scopes


def _resolve(
    db: Session,
    role_key: str,
    *,
    scope_type: ScopeType,
    scope_id: str | None,
    catalog: tuple | None = None,
) -> _Resolved:
    try:
        role = get_role(role_key)
    except ValueError as error:
        raise HTTPException(404, "未知的模型职责。") from error
    canonical_id, scopes, rows = catalog or _routing_catalog(db, scope_type, scope_id)
    candidate_roles = (role_key,) if role.default_role == role_key else (role_key, role.default_role)
    available = {
        (binding.scope_key, binding.role_key): (binding, model, provider)
        for provider, model, binding in rows if binding is not None
    }
    for candidate_scope_type, scope_key in scopes:
        for candidate_role in candidate_roles:
            candidate = available.get((scope_key, candidate_role))
            if candidate is None:
                continue
            binding, model, provider = candidate
            if errors := _model_capability_errors(model, role_key):
                # 已明确绑定的模型失效时不能静默把资料发给另一家。
                raise HTTPException(
                    409,
                    f"已配置的模型当前不能承担 {role_key}：" + "；".join(errors) + "。",
                )
            return _Resolved(
                binding=binding,
                model=model,
                provider=provider,
                source=f"{candidate_scope_type}:{candidate_role}",
                requested_scope_id=canonical_id,
            )

    # 兼容旧设置：只允许已在生产中使用过的文本/结构化/流能力。
    if any(item in role.required_capabilities for item in STRICTLY_VERIFIED_CAPABILITIES):
        raise HTTPException(503, f"尚未给 {role_key} 配置已验证的模型能力。")
    provider = next((provider for provider, _, _ in rows if provider.is_active), None)
    if provider is not None:
        model = next((model for item, model, _ in rows if item.id == provider.id and model is not None), None)
        if model is None:
            model = ensure_first_model(db, provider)
        if errors := _model_capability_errors(model, role_key):
            raise HTTPException(409, f"当前活动模型不能承担 {role_key}：" + "；".join(errors) + "。")
        return _Resolved(None, model, provider, "legacy.active_provider", canonical_id)

    # 环境变量仍是兼容回退；公开解析不读取或返回密钥。
    from backend.providers.service import _environment_config

    try:
        _environment_config()
    except RuntimeError as error:
        raise HTTPException(503, f"尚未给 {role_key} 配置可用模型。") from error
    return _Resolved(None, None, None, "legacy.environment", canonical_id)


def _routing_catalog(db: Session, scope_type: ScopeType, scope_id: str | None) -> tuple:
    canonical_id, scopes = _scope_chain(db, scope_type, scope_id)
    # 一次 SQL 固定整个工作流的模型和绑定，而非逐职责读取 READ COMMITTED 下的新版本。
    rows = db.execute(
        select(LlmProvider, LLMModelConfig, LLMRoleBinding)
        .outerjoin(LLMModelConfig, LLMModelConfig.provider_id == LlmProvider.id)
        .outerjoin(LLMRoleBinding, (LLMRoleBinding.model_config_id == LLMModelConfig.id)
                   & LLMRoleBinding.scope_key.in_([key for _, key in scopes]))
        .order_by(LlmProvider.id, LLMModelConfig.id)
        .execution_options(populate_existing=True)
    ).all()
    return canonical_id, scopes, rows


def resolve_role_read(
    db: Session,
    role_key: str,
    *,
    scope_type: ScopeType = "global",
    scope_id: str | None = None,
    _catalog: tuple | None = None,
) -> ResolvedRoleRead:
    role = ROLE_BY_KEY.get(role_key)
    if role is None:
        raise HTTPException(404, "未知的模型职责。")
    resolved = _resolve(
        db, role_key, scope_type=scope_type, scope_id=scope_id, catalog=_catalog
    )
    if resolved.model is None:
        from backend.providers.service import _environment_config

        environment = _environment_config()
        base_url = str(environment.base_url).rstrip("/")
        runtime_policy = ModelRuntimePolicy()
        return ResolvedRoleRead(
            requested_role=role_key,
            requested_scope_type=scope_type,
            requested_scope_id=resolved.requested_scope_id,
            resolution_source=resolved.source,
            binding_id=None,
            provider_id=None,
            provider_name="NUS (.env)",
            base_url=base_url,
            model_config_id=None,
            model=environment.model,
            model_revision=None,
            runtime_policy=runtime_policy,
            config_fingerprint=_fingerprint(
                provider_id=None,
                base_url=base_url,
                model_config_id=None,
                model_revision=None,
                model=environment.model,
                runtime_policy=runtime_policy.model_dump(exclude_none=True),
            ),
            required_capabilities=list(role.required_capabilities),
            capabilities=ModelCapabilityStatus.model_validate(legacy_capabilities()),
        )
    runtime_policy = ModelRuntimePolicy.model_validate(
        resolved.model.runtime_policy_json or {}
    )
    return ResolvedRoleRead(
        requested_role=role_key,
        requested_scope_type=scope_type,
        requested_scope_id=resolved.requested_scope_id,
        resolution_source=resolved.source,
        binding_id=resolved.binding.id if resolved.binding else None,
        provider_id=resolved.provider.id,
        provider_name=resolved.provider.name,
        base_url=resolved.provider.base_url,
        model_config_id=resolved.model.id,
        model=resolved.model.model,
        model_revision=resolved.model.revision,
        runtime_policy=runtime_policy,
        config_fingerprint=_fingerprint(
            provider_id=resolved.provider.id,
            base_url=resolved.provider.base_url,
            model_config_id=resolved.model.id,
            model_revision=resolved.model.revision,
            model=resolved.model.model,
            runtime_policy=runtime_policy.model_dump(exclude_none=True),
        ),
        required_capabilities=list(role.required_capabilities),
        capabilities=ModelCapabilityStatus.model_validate(resolved.model.capabilities_json),
    )


def resolve_routing_snapshot(
    db: Session,
    role_keys: list[str] | tuple[str, ...],
    *,
    scope_type: ScopeType = "global",
    scope_id: str | None = None,
) -> dict:
    """解析一次并返回可直接持久化的非敏感路由快照。

    保留输入顺序并去重，使指纹和调试输出稳定。这里只保存
    provider_id；key_ref 和 API key 都不会进入返回值。
    """
    unique_roles = list(dict.fromkeys(role_keys))
    if not unique_roles:
        raise HTTPException(422, "路由快照至少需要一个模型职责。")
    catalog = _routing_catalog(db, scope_type, scope_id)
    routes = {
        role_key: resolve_role_read(
            db,
            role_key,
            scope_type=scope_type,
            scope_id=scope_id,
            _catalog=catalog,
        )
        for role_key in unique_roles
    }
    return RoutingSnapshot(routes=routes).model_dump(mode="json")


def runtime_from_snapshot(route: dict | ResolvedRoleRead) -> RoleRuntime:
    """仅用快照构造运行配置，不重新解析当前职责绑定。"""
    try:
        frozen = (
            route
            if isinstance(route, ResolvedRoleRead)
            else ResolvedRoleRead.model_validate(route)
        )
    except Exception as error:
        raise HTTPException(409, "模型路由快照无法识别。") from error

    policy = frozen.runtime_policy
    expected_fingerprint = _fingerprint(
        provider_id=frozen.provider_id,
        base_url=frozen.base_url,
        model_config_id=frozen.model_config_id,
        model_revision=frozen.model_revision,
        model=frozen.model,
        runtime_policy=policy.model_dump(exclude_none=True),
    )
    if expected_fingerprint != frozen.config_fingerprint:
        raise HTTPException(409, "模型路由快照校验失败。")

    if frozen.provider_id is None:
        # 环境配置的 URL/模型/参数已在快照中冻结；此处只读当前密钥，
        # 以允许用户旋转凭据而不改变旧任务的模型路由。
        from backend.providers.service import _environment_config

        try:
            environment = _environment_config()
        except RuntimeError as error:
            raise HTTPException(503, "该任务的环境模型凭据已不可用。") from error
        api_key = environment.api_key
    else:
        with Session(get_engine()) as db:
            provider = db.get(LlmProvider, frozen.provider_id)
            if provider is None:
                raise HTTPException(503, "该任务的模型连接已不可用。")
            # 只借 provider_id 找凭据；不读它的 URL、旧 model 或 active 状态。
            api_key = secrets.get_api_key(provider.key_ref)

    return RoleRuntime(
        requested_role=frozen.requested_role,
        resolution_source=frozen.resolution_source,
        provider_id=frozen.provider_id,
        model_config_id=frozen.model_config_id,
        model_revision=frozen.model_revision,
        provider_name=frozen.provider_name,
        base_url=frozen.base_url,
        model=frozen.model,
        runtime_policy=policy,
        config_fingerprint=frozen.config_fingerprint,
        api_key=api_key,
    )


def resolve_role_runtime(
    role_key: str,
    *,
    scope_type: ScopeType = "global",
    scope_id: str | None = None,
) -> RoleRuntime:
    """解析一次职责并只在构造 SDK 前从钥匙串取密钥。"""
    with Session(get_engine()) as db:
        frozen = resolve_role_read(
            db, role_key, scope_type=scope_type, scope_id=scope_id
        )
    # 不再二次查询“当前激活连接”，避免环境回退被并发切换到另一家。
    return runtime_from_snapshot(frozen)
