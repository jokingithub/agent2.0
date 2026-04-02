# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parents[2])

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from fastmcp import FastMCP
from dataBase.ConfigService import ToolService
from logger import logger

# --- 配置 ---
PORT = int(os.getenv("MCP_PORT", "9001"))

# 监听地址（给 mcp.run 用，容器内用 0.0.0.0）
BIND_HOST = os.getenv("MCP_BIND_HOST", "0.0.0.0")

# 注册地址（写入 DB 给其他服务调用，必须是可达的服务名）
# 优先读 MCP_PUBLIC_URL，其次用 MCP_SERVICE_HOST 拼接，兜底 mcp-service
_service_host = os.getenv("MCP_SERVICE_HOST", "mcp-service")
TOOL_URL = os.getenv("MCP_PUBLIC_URL", f"http://{_service_host}:{PORT}/sse")

# 防呆：拒绝把 0.0.0.0 / 127.0.0.1 写进 DB
if "0.0.0.0" in TOOL_URL or "127.0.0.1" in TOOL_URL:
    logger.warning(
        f"⚠️ TOOL_URL={TOOL_URL} 包含本地地址，自动替换为 mcp-service。"
        f"建议设置环境变量 MCP_PUBLIC_URL 或 MCP_SERVICE_HOST"
    )
    TOOL_URL = f"http://mcp-service:{PORT}/sse"

# --- 初始化 ---
mcp = FastMCP("MCPServer")
tool_service = ToolService()