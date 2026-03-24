# -*- coding: utf-8 -*-
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gateway.store import GatewayConfigStore

store = GatewayConfigStore()
bearer_scheme = HTTPBearer(auto_error=False)


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="缺少 Authorization")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization 格式错误，应为 Bearer <token>")

    token = parts[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="token 不能为空")
    return token


def require_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> str:
    if credentials is None:
        raise HTTPException(status_code=401, detail="缺少 Authorization")

    if credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization 格式错误，应为 Bearer <token>")

    token = (credentials.credentials or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="token 不能为空")

    if not store.validate_token(token):
        raise HTTPException(status_code=401, detail="token 校验失败")
    return token
