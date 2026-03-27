# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

# --- 1. 核心修复：手动将项目根目录添加到搜索路径 ---
# __file__ 是 .../mcp-service/core/config.py
# .parent 是 .../mcp-service/core/
# .parents[1] 是 .../mcp-service/
# .parents[2] 是 .../ (即 dataBase 和 logger 所在的根目录)
_ROOT = str(Path(__file__).resolve().parents[2])

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# --- 2. 现在可以安全导入外部模块了 ---
from fastmcp import FastMCP
from dataBase.ConfigService import ToolService  # 此时可以找到了
from logger import logger                       # 此时可以找到了

# --- 3. 原有配置信息 ---
# 获取环境变量或设置默认值
PORT = int(os.getenv("MCP_PORT", "9001"))
# 注意：如果是在 Docker 容器内，HOST_FOR_CLIENT 建议设为 0.0.0.0 或具体的内网 IP
HOST_FOR_CLIENT = os.getenv("MCP_HOST", "127.0.0.1")
TOOL_URL = f"http://{HOST_FOR_CLIENT}:{PORT}/sse"

# --- 4. 初始化实例 ---
mcp = FastMCP("MCPServer")
tool_service = ToolService()