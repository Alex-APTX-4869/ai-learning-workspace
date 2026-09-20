from typing import TypeVar

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIError, APITimeoutError
from pydantic import BaseModel, ValidationError

from backend.providers.service import resolve_active_provider
from backend.providers.routing import resolve_role_runtime, runtime_from_snapshot
from backend.providers.schemas import ResolvedRoleRead, RoutingSnapshot

Result = TypeVar("Result", bound=BaseModel)


def _route_from_snapshot(
    snapshot: dict | RoutingSnapshot, role: str | None
) -> ResolvedRoleRead:
    if role is None:
        raise ValueError("使用工作流路由快照时必须指定 role。")
    frozen = (
        snapshot
        if isinstance(snapshot, RoutingSnapshot)
        else RoutingSnapshot.model_validate(snapshot)
    )
    route = frozen.routes.get(role)
    if route is None:
        raise ValueError(f"路由快照中没有 {role} 职责。")
    return route


def get_llm(
    *,
    role: str | None = None,
    route: dict | ResolvedRoleRead | None = None,
    snapshot: dict | RoutingSnapshot | None = None,
) -> ChatOpenAI:
    if route is not None and snapshot is not None:
        raise ValueError("route 和 snapshot 不能同时提供。")

    if snapshot is not None:
        route = _route_from_snapshot(snapshot, role)
    if route is not None:
        frozen = (
            route
            if isinstance(route, ResolvedRoleRead)
            else ResolvedRoleRead.model_validate(route)
        )
        if role is not None and frozen.requested_role != role:
            raise ValueError("指定 role 与路由快照不一致。")
        runtime = runtime_from_snapshot(frozen)
        policy = runtime.runtime_policy
        kwargs = {
            "model": runtime.model,
            "api_key": runtime.api_key.get_secret_value(),
            "base_url": runtime.base_url,
            "timeout": policy.request_timeout_seconds or 180,
            "max_retries": (
                policy.max_retries if policy.max_retries is not None else 0
            ),
        }
        if policy.temperature is not None:
            kwargs["temperature"] = policy.temperature
        if policy.max_output_tokens is not None:
            kwargs["max_completion_tokens"] = policy.max_output_tokens
        return ChatOpenAI(**kwargs)

    if role is not None:
        runtime = resolve_role_runtime(role)
        policy = runtime.runtime_policy
        kwargs = {
            "model": runtime.model,
            "api_key": runtime.api_key.get_secret_value(),
            "base_url": runtime.base_url,
            "timeout": policy.request_timeout_seconds or 180,
            "max_retries": (
                policy.max_retries if policy.max_retries is not None else 0
            ),
        }
        if policy.temperature is not None:
            kwargs["temperature"] = policy.temperature
        if policy.max_output_tokens is not None:
            kwargs["max_completion_tokens"] = policy.max_output_tokens
        return ChatOpenAI(**kwargs)

    # 迁移期保留旧入口；新持久任务必须显式传入快照。
    provider = resolve_active_provider()
    return ChatOpenAI(
        model=provider.model,
        api_key=provider.api_key.get_secret_value(),
        base_url=provider.base_url,
        timeout=180,
        max_retries=0,
    )


def generate_json(
    prompt: str,
    schema: type[Result],
    *,
    role: str | None = None,
    route: dict | ResolvedRoleRead | None = None,
    snapshot: dict | RoutingSnapshot | None = None,
) -> Result:
    return _generate_json(
        prompt, schema, role=role, route=route, snapshot=snapshot
    )


def generate_json_messages(
    system_prompt: str,
    user_payload: str,
    schema: type[Result],
    *,
    role: str | None = None,
    route: dict | ResolvedRoleRead | None = None,
    snapshot: dict | RoutingSnapshot | None = None,
) -> Result:
    """把规则和用户资料放在不同角色消息中，避免混淆指令与数据。"""
    return _generate_json(
        [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_payload),
        ],
        schema,
        role=role,
        route=route,
        snapshot=snapshot,
    )


def stream_text_messages(
    system_prompt: str,
    user_payload: str,
    *,
    role: str | None = None,
    route: dict | ResolvedRoleRead | None = None,
    snapshot: dict | RoutingSnapshot | None = None,
):
    """逐块返回模型文字；调用方负责定义和校验更高层流协议。"""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_payload),
    ]
    try:
        llm = (
            get_llm()
            if role is None and route is None and snapshot is None
            else get_llm(role=role, route=route, snapshot=snapshot)
        )
        for reply in llm.stream(messages):
            if not isinstance(reply.content, str):
                raise HTTPException(502, "模型返回了无法识别的流式内容。")
            if reply.content:
                yield reply.content
    except APITimeoutError as error:
        raise HTTPException(504, "AI 生成超时，本次内容没有保存。") from error
    except APIError as error:
        raise HTTPException(502, "模型服务暂时不可用，请稍后重试。") from error


def _generate_json(
    model_input,
    schema: type[Result],
    *,
    role: str | None = None,
    route: dict | ResolvedRoleRead | None = None,
    snapshot: dict | RoutingSnapshot | None = None,
) -> Result:
    try:
        llm = (
            get_llm()
            if role is None and route is None and snapshot is None
            else get_llm(role=role, route=route, snapshot=snapshot)
        )
        reply = llm.invoke(model_input)
    except APITimeoutError as error:
        raise HTTPException(504, "AI 生成超时，已有内容仍保留，请稍后重试。") from error
    except APIError as error:
        raise HTTPException(502, "模型服务暂时不可用，请稍后重试。") from error

    if not isinstance(reply.content, str):
        raise HTTPException(502, "模型未返回可识别的文字结果，请重试。")
    content = reply.content.strip()
    # 兼容模型偶尔附加的代码围栏，实际结构仍交给 Pydantic 校验。
    if content.startswith("```") and content.endswith("```"):
        content = "\n".join(content.splitlines()[1:-1])
    try:
        return schema.model_validate_json(content)
    except ValidationError as error:
        raise HTTPException(502, "模型返回的数据结构不完整，本次未保存，请重试。") from error
