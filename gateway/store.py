# -*- coding: utf-8 -*-
import os
from typing import Any, Dict, Optional

from dataBase.ConfigService import GatewayAppService, GatewayEnvService, ToolService
from logger import logger


class GatewayConfigStore:
    def __init__(self):
        self.gateway_env_service = GatewayEnvService()
        self.gateway_app_service = GatewayAppService()
        self.tool_service = ToolService()

    def get_backend_base_url(self) -> str:
        """
        从 gateway_env 动态读取后端地址。
        兼容两种方式：
        1) whitelist[0] 直接放完整地址，如 http://127.0.0.1:8000
        2) 使用 port 字段，host 默认 127.0.0.1
        """
        env = self.gateway_env_service.get_current() or {}
        whitelist = env.get("whitelist") or []
        if whitelist:
            first = str(whitelist[0]).strip().rstrip("/")
            if first.startswith("http://") or first.startswith("https://"):
                return first

        env_backend = os.getenv("BACKEND_BASE_URL", "").strip().rstrip("/")
        if env_backend.startswith("http://") or env_backend.startswith("https://"):
            return env_backend

        default_port = int(os.getenv("BACKEND_PORT", "8000"))
        port = int(env.get("port", default_port))

        in_docker = os.path.exists("/.dockerenv")
        if in_docker:
            host = os.getenv("BACKEND_HOST", "main-app")
        else:
            host = os.getenv("BACKEND_HOST", "127.0.0.1")

        return f"http://{host}:{port}"

    def validate_token(self, app_id: str, token: str) -> bool:
        """
        在 gateway_apps 中按 app_id + auth_token 校验。
        """
        if not app_id:
            return False
        if not token:
            return False
        return self.gateway_app_service.validate_token(app_id, token)

    def get_tool(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """
        从 tools 动态读取工具。
        优先按 _id 匹配，不存在则按 name 匹配。
        """
        by_id = self.tool_service.get_by_id(tool_id)
        if by_id:
            return by_id

        tools = self.tool_service.query({"name": tool_id})
        if tools:
            return tools[0]

        return None

    def build_tool_target(self, tool_doc: Dict[str, Any], backend_base_url: str) -> tuple[str, str, Dict[str, str], bool, float]:
        """
        解析工具目标地址/方法/headers。
        约定字段（优先级从高到低）：
        - config.path: 路径，如 /tools/xxx
        - url: 完整url 或 路径
        - config.method / method: HTTP方法
        - config.extra_headers: dict
        - config.auth_required: bool（默认False）
        - config.timeout_sec: 数字（默认30）
        """
        config = tool_doc.get("config") or {}

        raw_path_or_url = config.get("path") or tool_doc.get("url") or ""
        if not raw_path_or_url:
            raise ValueError("工具未配置 path/url")

        raw_path_or_url = str(raw_path_or_url).strip()

        if raw_path_or_url.startswith("http://") or raw_path_or_url.startswith("https://"):
            target_url = raw_path_or_url
        else:
            if not raw_path_or_url.startswith("/"):
                raw_path_or_url = f"/{raw_path_or_url}"
            target_url = f"{backend_base_url}{raw_path_or_url}"

        method = str(config.get("method") or tool_doc.get("method") or "POST").upper()
        extra_headers = config.get("extra_headers") or {}
        if not isinstance(extra_headers, dict):
            extra_headers = {}

        auth_required = bool(config.get("auth_required", False))
        timeout_sec = float(config.get("timeout_sec", 30))

        logger.info(
            f"tool routing -> id={tool_doc.get('_id')} name={tool_doc.get('name')} method={method} target={target_url}"
        )

        return target_url, method, extra_headers, auth_required, timeout_sec
