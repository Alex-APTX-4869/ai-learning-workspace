from fastapi import HTTPException

KEYRING_SERVICE = "FastAPILearning.llm-providers"


def _keyring():
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as error:
        raise HTTPException(
            503, "缺少系统钥匙串支持，请重新安装后端依赖。"
        ) from error
    return keyring, KeyringError


def set_api_key(key_ref: str, api_key: str) -> None:
    keyring, keyring_error = _keyring()
    try:
        keyring.set_password(KEYRING_SERVICE, key_ref, api_key)
    except keyring_error as error:
        raise HTTPException(503, "无法写入系统钥匙串，请检查系统权限。") from error


def get_api_key(key_ref: str) -> str:
    keyring, keyring_error = _keyring()
    try:
        value = keyring.get_password(KEYRING_SERVICE, key_ref)
    except keyring_error as error:
        raise HTTPException(503, "无法读取系统钥匙串，请检查系统权限。") from error
    if not value:
        raise HTTPException(503, "活动模型配置的密钥已丢失，请重新配置。")
    return value


def delete_api_key(key_ref: str) -> None:
    keyring, keyring_error = _keyring()
    try:
        keyring.delete_password(KEYRING_SERVICE, key_ref)
    except keyring_error:
        # 仅用于数据库保存失败后的清理；原始保存异常更值得返回给调用方。
        return
