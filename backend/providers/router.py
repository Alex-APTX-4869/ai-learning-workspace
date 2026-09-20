from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.providers import probes, routing, service
from backend.providers.schemas import (
    CapabilityName,
    CapabilityResetWrite,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
    ProviderCreate,
    ProviderRead,
    ResolvedRoleRead,
    RoleBindingRead,
    RoleBindingWrite,
    RoleDefinitionRead,
    ScopeType,
)

router = APIRouter()
providers_router = APIRouter(prefix="/llm-providers", tags=["模型连接"])
models_router = APIRouter(prefix="/llm-models", tags=["模型配置"])
roles_router = APIRouter(tags=["模型职责路由"])
Database = Annotated[Session, Depends(get_db)]


@providers_router.get("", response_model=list[ProviderRead])
def list_providers(db: Database):
    return service.list_providers(db)


@providers_router.get("/active", response_model=ProviderRead)
def get_active_provider(db: Database):
    return service.get_active_provider_read(db)


@providers_router.post("", response_model=ProviderRead, status_code=201)
def create_provider(data: ProviderCreate, db: Database):
    return service.create_provider(db, data)


@providers_router.post("/environment/activate", response_model=ProviderRead)
def activate_environment(db: Database):
    return service.activate_environment(db)


@providers_router.post("/{provider_id}/activate", response_model=ProviderRead)
def activate_provider(provider_id: int, db: Database):
    return service.activate_provider(db, provider_id)


@providers_router.get("/{provider_id}/models", response_model=list[ModelConfigRead])
def list_provider_models(provider_id: int, db: Database):
    return routing.list_models(db, provider_id)


@providers_router.post(
    "/{provider_id}/models", response_model=ModelConfigRead, status_code=201
)
def create_provider_model(provider_id: int, data: ModelConfigCreate, db: Database):
    return routing.create_model(db, provider_id, data)


@models_router.get("", response_model=list[ModelConfigRead])
def list_models(db: Database):
    return routing.list_models(db)


@models_router.get("/{model_config_id}", response_model=ModelConfigRead)
def get_model(model_config_id: int, db: Database):
    return routing._model_read(routing.get_model(db, model_config_id))


@models_router.patch("/{model_config_id}", response_model=ModelConfigRead)
def update_model(model_config_id: int, data: ModelConfigUpdate, db: Database):
    return routing.update_model(db, model_config_id, data)


@models_router.post(
    "/{model_config_id}/capabilities/{capability}/reset",
    response_model=ModelConfigRead,
)
def reset_model_capability(
    model_config_id: int,
    capability: CapabilityName,
    data: CapabilityResetWrite,
    db: Database,
):
    return routing.reset_capability(
        db, model_config_id, capability, data.expected_revision
    )


@models_router.post("/{model_config_id}/verify", response_model=ModelConfigRead)
def verify_model_capabilities(
    model_config_id: int,
    data: probes.CapabilityProbeRequest,
    db: Database,
):
    """用固定无敏感样本做真实请求；可能产生少量供应商调用费用。"""
    return probes.probe_capabilities(db, model_config_id, data)


@roles_router.get("/llm-roles", response_model=list[RoleDefinitionRead])
def list_roles():
    return routing.list_roles()


@roles_router.get("/llm-role-bindings", response_model=list[RoleBindingRead])
def list_role_bindings(
    db: Database,
    scope_type: ScopeType | None = None,
    scope_id: str | None = None,
):
    return routing.list_bindings(
        db, scope_type=scope_type, scope_id=scope_id
    )


@roles_router.put(
    "/llm-role-bindings/{role_key}", response_model=RoleBindingRead
)
def put_role_binding(role_key: str, data: RoleBindingWrite, db: Database):
    return routing.put_binding(db, role_key, data)


@roles_router.delete("/llm-role-bindings/{role_key}", status_code=204)
def delete_role_binding(
    role_key: str,
    db: Database,
    scope_type: ScopeType,
    expected_revision: Annotated[int, Query(ge=1)],
    scope_id: str | None = None,
):
    routing.delete_binding(
        db,
        role_key,
        scope_type=scope_type,
        scope_id=scope_id,
        expected_revision=expected_revision,
    )
    return Response(status_code=204)


@roles_router.get(
    "/llm-role-routing/{role_key}", response_model=ResolvedRoleRead
)
def resolve_role(
    role_key: str,
    db: Database,
    scope_type: ScopeType = "global",
    scope_id: str | None = None,
):
    return routing.resolve_role_read(
        db, role_key, scope_type=scope_type, scope_id=scope_id
    )


router.include_router(providers_router)
router.include_router(models_router)
router.include_router(roles_router)
