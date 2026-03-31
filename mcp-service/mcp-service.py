# -*- coding: utf-8 -*-
import sys
from pathlib import Path

# 确保项目根目录在路径中
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config import mcp, PORT
from logger import logger
import tools  # 👈 这一步会自动触发 tools 目录下所有模块的装饰器注册逻辑

if __name__ == "__main__":
    logger.info(f"🚀 MCP 服务启动中... 端口: {PORT}")
    # 注意：这里 host 用 0.0.0.0 方便容器化
    mcp.run(transport="sse", host="0.0.0.0", port=PORT)