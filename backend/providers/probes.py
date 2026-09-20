from __future__ import annotations

import json
import math
import base64
import random
import struct
import zlib
from datetime import datetime, timezone
from typing import Annotated

from fastapi import HTTPException
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from openai import APIError, APITimeoutError
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.providers import routing, secrets
from backend.providers.models import LLMModelConfig, LlmProvider
from backend.providers.schemas import CapabilityName, ModelConfigRead, ModelRuntimePolicy


class CapabilityProbeRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    capabilities: Annotated[list[CapabilityName], Field(min_length=1, max_length=5)]


def _vision_challenge() -> tuple[str, list[str]]:
    """本地合成随机四色图；忽略图片、只回复 OK 不能通过检测。"""
    colors = [("red", b"\xff\x00\x00"), ("green", b"\x00\x80\x00"),
              ("blue", b"\x00\x00\xff"), ("yellow", b"\xff\xff\x00")]
    random.SystemRandom().shuffle(colors)
    pixels = b"".join(b"\x00" + colors[(y // 64) * 2][1] * 64
                      + colors[(y // 64) * 2 + 1][1] * 64 for y in range(128))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", 128, 128, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode(), [c[0] for c in colors]


def _chat_model(
    *, base_url: str, model: str, api_key: str, policy: ModelRuntimePolicy
) -> ChatOpenAI:
    kwargs = {
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "timeout": min(policy.request_timeout_seconds or 30, 30),
        "max_retries": 0,
        "max_completion_tokens": min(policy.max_output_tokens or 256, 256),
    }
    if policy.temperature is not None:
        kwargs["temperature"] = policy.temperature
    return ChatOpenAI(**kwargs)


def _reply_text(reply) -> str:
    if not isinstance(reply.content, str) or not reply.content.strip():
        raise ValueError("empty_or_non_text_response")
    return reply.content.strip()


def _run_probe(
    capability: CapabilityName,
    *,
    base_url: str,
    model: str,
    api_key: str,
    policy: ModelRuntimePolicy,
) -> None:
    if capability == "embeddings":
        vector = OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=min(policy.request_timeout_seconds or 30, 30),
            max_retries=0,
            check_embedding_ctx_length=False,
        ).embed_query("能力检测：学习课程")
        if not vector or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
            raise ValueError("invalid_embedding")
        return

    client = _chat_model(
        base_url=base_url, model=model, api_key=api_key, policy=policy
    )
    if capability == "text_chat":
        _reply_text(client.invoke("只回复 OK。"))
    elif capability == "structured_output":
        text = _reply_text(client.invoke('只返回合法 JSON：{"ok":true}'))
        if text.startswith("```") and text.endswith("```"):
            text = "\n".join(text.splitlines()[1:-1])
        value = json.loads(text)
        if not isinstance(value, dict) or value.get("ok") is not True:
            raise ValueError("invalid_structured_output")
    elif capability == "streaming":
        received_text = False
        stream = client.stream("只回复 OK。")
        try:
            for chunk in stream:
                received_text |= isinstance(chunk.content, str) and bool(chunk.content)
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
        if not received_text:
            raise ValueError("empty_stream")
    elif capability == "vision":
        image, expected = _vision_challenge()
        message = HumanMessage(content=[
            {"type": "text", "text": '按左上、右上、左下、右下顺序识别图片四个方块的颜色。只返回 JSON 字符串数组，颜色用 red、green、blue、yellow 英文名。'},
            {"type": "image_url", "image_url": {"url": image}},
        ])
        if json.loads(_reply_text(client.invoke([message]))) != expected:
            raise ValueError("incorrect_visual_answer")
    else:  # Pydantic 已限制枚举；保留 fail-closed 防未来漏实现。
        raise ValueError("unsupported_probe")


def _safe_error_code(error: Exception) -> str:
    if isinstance(error, APITimeoutError):
        return "provider_timeout"
    if isinstance(error, APIError):
        return "provider_api_error"
    if isinstance(error, (ValueError, json.JSONDecodeError)):
        return "invalid_probe_response"
    return "provider_request_failed"


def probe_capabilities(
    db: Session, model_config_id: int, data: CapabilityProbeRequest
) -> ModelConfigRead:
    model = db.get(LLMModelConfig, model_config_id)
    if model is None:
        raise HTTPException(404, "没有找到这个模型配置。")
    if model.revision != data.expected_revision:
        raise HTTPException(409, "模型配置已被更新，请刷新后重试。")
    requested = list(dict.fromkeys(data.capabilities))
    capabilities = dict(model.capabilities_json)
    unsupported = [
        name for name in requested if not capabilities[name].get("supported")
    ]
    if unsupported:
        raise HTTPException(
            409, "模型没有声明这些能力：" + "、".join(unsupported) + "。"
        )
    provider = db.get(LlmProvider, model.provider_id)
    if provider is None:
        raise HTTPException(503, "模型连接已不存在。")
    # 这里只取值构造 SDK；不写入数据库、响应或异常。
    api_key = secrets.get_api_key(provider.key_ref)
    base_url, model_name = provider.base_url, model.model
    policy = ModelRuntimePolicy.model_validate(model.runtime_policy_json or {})
    expected_revision = model.revision
    db.rollback()

    results: dict[str, tuple[str, str | None]] = {}
    for capability in requested:
        try:
            _run_probe(
                capability,
                base_url=base_url,
                model=model_name,
                api_key=api_key,
                policy=policy,
            )
            results[capability] = ("verified", None)
        except Exception as error:
            # 只持久化有限错误码，绝不回显供应商异常正文。
            results[capability] = ("failed", _safe_error_code(error))

    model = db.scalar(
        select(LLMModelConfig)
        .where(LLMModelConfig.id == model_config_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if model is None:
        raise HTTPException(404, "模型配置已被删除，本次检测结果没有保存。")
    if model.revision != expected_revision or model.model != model_name:
        raise HTTPException(409, "检测期间模型配置已经变化，本次结果没有保存。")
    updated = dict(model.capabilities_json)
    checked_at = datetime.now(timezone.utc).isoformat()
    for capability, (status, error_code) in results.items():
        updated[capability] = {
            "supported": True,
            "status": status,
            "checked_at": checked_at,
            "error_code": error_code,
        }
    model.capabilities_json = updated
    model.revision += 1
    model.updated_at = datetime.now(timezone.utc)
    db.flush()
    result = routing._model_read(model)
    db.commit()
    return result
