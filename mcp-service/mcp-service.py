# -*- coding: utf-8 -*-
import sys
from pathlib import Path

# 确保项目根目录在路径中
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.config import mcp, PORT, BIND_HOST
from logger import logger
import tools

if __name__ == "__main__":
    logger.info(f"🚀 MCP 服务启动中... bind={BIND_HOST}:{PORT}, tool_url={__import__('core.config', fromlist=['TOOL_URL']).TOOL_URL}")
    mcp.run(transport="sse", host=BIND_HOST, port=PORT)