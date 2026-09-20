from urllib.parse import urlsplit, urlunsplit

SENSITIVE_KEYS = {"api_key", "authorization", "password", "secret", "token"}
REDACTED = "[REDACTED]"
REDACTED_URL = "[REDACTED_URL]"


def _is_sensitive_key(value: object) -> bool:
    normalized = "".join(character for character in str(value).casefold() if character.isalnum())
    return normalized in {
        "apikey",
        "authorization",
        "password",
        "secret",
        "clientsecret",
        "token",
        "accesstoken",
        "refreshtoken",
    }


def _redact_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        has_credentials = parsed.username is not None or parsed.password is not None
        has_query = parsed.query != ""
        if not parsed.scheme or (not has_credentials and not has_query):
            return value
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        # 无法安全解析的 URL 绝不回退返回原文。
        return REDACTED_URL
    if not hostname:
        return REDACTED_URL
    if port is not None:
        hostname += f":{port}"
    # 校验错误中不需要查询参数；它们可能包含未知命名的密钥。
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def redact_sensitive(value, *, sensitive: bool = False):
    if sensitive:
        return REDACTED
    if isinstance(value, dict):
        return {
            key: redact_sensitive(
                item, sensitive=str(key).casefold() in SENSITIVE_KEYS
                or _is_sensitive_key(key)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str):
        return _redact_url(value)
    return value


def redact_validation_errors(errors: list[dict]) -> list[dict]:
    # FastAPI 默认的 input/ctx 可能包含整个请求体。响应只保留前端定位字段
    # 所需的最小信息，从而也覆盖 apiKey/client_secret 等未知别名。
    return [
        {
            key: redact_sensitive(error[key])
            for key in ("type", "loc", "msg", "url")
            if key in error
        }
        for error in errors
    ]
