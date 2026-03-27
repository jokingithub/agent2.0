from core.config import mcp, tool_service, TOOL_URL
from logger import logger

def register_tool(category: str, arg_name: str, description: str = None):
    def decorator(func):
        final_desc = description or (func.__doc__ or "未分类工具").split('\n')[0].strip()
        tool_name = func.__name__
        
        # 1. 注册到 FastMCP
        mcp.tool()(func)
        
        # 2. 同步到数据库
        try:
            tool_payload = {
                "name": tool_name,
                "type": "mcp",
                "category": category,
                "url": TOOL_URL,
                "enabled": True,
                "description": final_desc,
                "config": {"remote_tool_name": tool_name, "arg_name": arg_name},
            }
            tool_service.upsert_mcp_tool(tool_payload)
            logger.info(f"✅ MCP工具同步成功: {tool_name}")
        except Exception as e:
            logger.error(f"❌ MCP工具同步失败 [{tool_name}]: {e}")
        return func
    return decorator