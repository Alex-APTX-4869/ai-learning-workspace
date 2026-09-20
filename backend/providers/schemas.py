from ipaddress import ip_address
from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    StringConstraints,
    field_validator,
    model_validator,
)

ProviderName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
ModelName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)
]
ProviderUrl = Annotated[HttpUrl, Field(max_length=1000)]


class ProviderCreate(BaseModel):
    name: ProviderName
    base_url: ProviderUrl
    model: ModelName
    api_key: SecretStr = Field(repr=False)
    activate: bool = True

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        cleaned = value.get_secret_value().strip()
        if not cleaned or len(cleaned) > 4000:
            raise ValueError("api_key 长度必须在 1 到 4000 个字符之间")
        return SecretStr(cleaned)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: HttpUrl) -> HttpUrl:
        if value.username is not None or value.password is not None:
            raise ValueError("base_url 不能包含用户名或密码")
        if value.query is not None or value.fragment is not None:
            raise ValueError("base_url 不能包含查询参数或片段")

        host = value.host.casefold().strip("[]") if value.host else ""
        is_loopback = host == "localhost"
        if not is_loopback:
            try:
                is_loopback = ip_address(host).is_loopback
            except ValueError:
                pass
        if value.scheme == "http" and not is_loopback:
            raise ValueError("非本机模型服务的 base_url 必须使用 HTTPS")
        return value


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None
    name: str
    base_url: str
    model: str
    is_active: bool
    source: Literal["saved", "environment"]
    has_api_key: bool


class ProviderRuntime(BaseModel):
    name: str
    base_url: str
    model: str
    # SecretStr 让 repr/model_dump/json 默认只出现掩码；只在构造 SDK 时显式取值。
    api_key: SecretStr = Field(repr=False)
    source: Literal["saved", "environment"]


CapabilityName = Literal[
    "text_chat", "structured_output", "streaming", "vision", "embeddings"
]
CapabilityVerificationStatus = Literal[
    "unsupported", "unverified", "verified", "failed"
]
ScopeType = Literal["global", "course", "intake", "directory_draft"]


class ModelCapabilityDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text_chat: bool = True
    structured_output: bool = False
    streaming: bool = False
    vision: bool = False
    embeddings: bool = False


class CapabilityState(BaseModel):
    supported: bool
    status: CapabilityVerificationStatus
    checked_at: datetime | None = None
    error_code: str | None = None


class ModelCapabilityStatus(BaseModel):
    text_chat: CapabilityState
    structured_output: CapabilityState
    streaming: CapabilityState
    vision: CapabilityState
    embeddings: CapabilityState


class ModelRuntimePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, ge=1, le=1_000_000)
    request_timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    max_retries: int | None = Field(default=None, ge=0, le=20)


class ModelConfigCreate(BaseModel):
    label: ProviderName
    model: ModelName
    capabilities: ModelCapabilityDeclaration = Field(
        default_factory=ModelCapabilityDeclaration
    )
    runtime_policy: ModelRuntimePolicy = Field(default_factory=ModelRuntimePolicy)


class ModelConfigUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    label: ProviderName | None = None
    model: ModelName | None = None
    capabilities: ModelCapabilityDeclaration | None = None
    runtime_policy: ModelRuntimePolicy | None = None
    is_enabled: bool | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(
            value is None
            for value in (
                self.label,
                self.model,
                self.capabilities,
                self.runtime_policy,
                self.is_enabled,
            )
        ):
            raise ValueError("至少提供一项要修改的模型配置")
        return self


class ModelConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    provider_id: int
    label: str
    model: str
    capabilities: ModelCapabilityStatus
    runtime_policy: ModelRuntimePolicy
    is_enabled: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class CapabilityResetWrite(BaseModel):
    """用户只能清除旧检测结论；verified/failed 必须由服务端实测写入。"""

    expected_revision: int = Field(ge=1)


class RoleDefinitionRead(BaseModel):
    key: str
    name: str
    description: str
    required_capabilities: list[CapabilityName]
    default_role: str


class RoleBindingWrite(BaseModel):
    scope_type: ScopeType
    scope_id: str | None = Field(default=None, max_length=64)
    model_config_id: int = Field(gt=0)
    # 新建时必须为 0；更新时必须等于服务端当前 revision。
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "global" and self.scope_id is not None:
            raise ValueError("global 范围不能提供 scope_id")
        if self.scope_type != "global":
            if self.scope_id is None or not self.scope_id.strip():
                raise ValueError(f"{self.scope_type} 范围必须提供 scope_id")
            self.scope_id = self.scope_id.strip()
        return self


class RoleBindingRead(BaseModel):
    id: int
    scope_type: ScopeType
    scope_id: str | None
    role_key: str
    model_config_id: int
    revision: int
    model: ModelConfigRead


class ResolvedRoleRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_role: str
    requested_scope_type: ScopeType
    requested_scope_id: str | None
    resolution_source: str
    binding_id: int | None
    provider_id: int | None
    provider_name: str
    base_url: str
    model_config_id: int | None
    model: str
    model_revision: int | None
    runtime_policy: ModelRuntimePolicy
    config_fingerprint: str
    required_capabilities: list[CapabilityName]
    capabilities: ModelCapabilityStatus | None


class RoutingSnapshot(BaseModel):
    """一次工作流已解析的公开路由。

    快照可直接写入 JSON 字段；凭据及其定位符始终留在服务端。
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    routes: dict[str, ResolvedRoleRead]

    @model_validator(mode="after")
    def validate_routes(self):
        if not self.routes:
            raise ValueError("路由快照至少需要一个职责")
        for role_key, route in self.routes.items():
            if role_key != route.requested_role:
                raise ValueError("路由快照的职责键与内容不一致")
        return self


class RoleRuntime(BaseModel):
    requested_role: str
    resolution_source: str
    provider_id: int | None
    model_config_id: int | None
    model_revision: int | None
    provider_name: str
    base_url: str
    model: str
    runtime_policy: ModelRuntimePolicy
    config_fingerprint: str
    api_key: SecretStr = Field(repr=False)
