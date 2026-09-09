from functools import lru_cache
from typing import TypeVar

from fastapi import HTTPException
from langchain_openai import ChatOpenAI
from openai import APIError, APITimeoutError
from pydantic import BaseModel, ValidationError

from backend.core.config import nus_settings

Result = TypeVar("Result", bound=BaseModel)


@lru_cache
def get_llm() -> ChatOpenAI:
    try:
        key, url, model = nus_settings()
    except RuntimeError:
        raise HTTPException(503, "请先在后端 .env 中配置 NUS 模型信息。")

    return ChatOpenAI(model=model, api_key=key, base_url=url, timeout=180, max_retries=0)


def generate_json(prompt: str, schema: type[Result]) -> Result:
    try:
        reply = get_llm().invoke(prompt)
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
        raise HTTPException(502, "模型返回的课程结构不完整，本次未保存，请重试。") from error
