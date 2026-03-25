# -*- coding: utf-8 -*-
import random
import os
import httpx  # 推荐使用 httpx 处理异步请求
import asyncio
from pathlib import Path
import sys

# 兼容容器/脚本直接运行：把项目根目录加入导入路径
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastmcp import FastMCP
from logger import logger
from dataBase.ConfigService import ToolService

# --- 配置区 ---
PORT = int(os.getenv("MCP_PORT", "9001"))
HOST_FOR_CLIENT = os.getenv("MCP_HOST", "127.0.0.1")
TOOL_URL = f"http://{HOST_FOR_CLIENT}:{PORT}/sse"

mcp = FastMCP("MCPServer")
_tool_service = ToolService()

# ============================================================
# HTTP 调用核心助手 (预留的通用接口)
# ============================================================

async def fetch_external_api(
    url: str, 
    method: str = "GET", 
    params: dict = None, 
    json_data: dict = None, 
    headers: dict = None,
    timeout: int = 10
):
    """
    预留的通用 HTTP 调用函数。
    支持 GET/POST，内置错误处理。
    """
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"🌐 请求外部接口: [{method}] {url}")
            response = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
            return response.json() if "application/json" in response.headers.get("content-type", "") else response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ 接口返回异常: {e.response.status_code} - {e.response.text}")
            return f"接口错误: {e.response.status_code}"
        except Exception as e:
            logger.error(f"❌ 网络请求失败: {str(e)}")
            return f"网络调用失败: {str(e)}"

# ============================================================
# 统一注册装饰器 (保持不变)
# ============================================================

def register_tool(category: str, arg_name: str, description: str = None):
    def decorator(func):
        final_desc = description or (func.__doc__ or "未分类工具").split('\n')[0].strip()
        tool_name = func.__name__
        mcp.tool()(func)
        try:
            tool_payload = {
                "name": tool_name,
                "type": "mcp",
                "category": category,
                "url": TOOL_URL,
                "enabled": True,
                "description": final_desc,
                "config": {
                    "remote_tool_name": tool_name,
                    "arg_name": arg_name,
                },
            }
            doc_id = _tool_service.upsert_mcp_tool(tool_payload)
            logger.info(f"✅ MCP工具同步成功: {tool_name} (ID: {doc_id})")
        except Exception as e:
            logger.error(f"❌ MCP工具同步失败 [{tool_name}]: {e}")
        return func
    return decorator

# ============================================================
# 工具定义
# ============================================================

# 1. 原生本地逻辑工具
@register_tool(category="weather", arg_name="city")
def get_weather_local(city: str) -> str:
    """获取模拟天气。"""
    return f"{city}天气：晴，25℃"

# 2. 预留：通过 HTTP 调用外部搜索接口 (示例)
@register_tool(category="search", arg_name="keyword", description="调用外部搜索引擎查询实时信息。")
async def web_search_api(keyword: str) -> str:
    """这是一个调用外部 HTTP 接口的示例工具。"""
    # 这里填写实际的 API 地址
    api_url = "https://api.example.com/search" 
    api_key = os.getenv("SEARCH_API_KEY", "your_key")
    
    # 使用预留的助手函数进行调用
    result = await fetch_external_api(
        url=api_url,
        params={"q": keyword, "key": api_key}
    )
    
    # 假设返回结果是字典，我们根据逻辑处理后返回字符串给模型
    if isinstance(result, dict):
        return f"搜索结果: {result.get('data', '无内容')}"
    return str(result)

# 3. 预留：通过 HTTP 调用自建微服务 (示例)
@register_tool(category="crm", arg_name="user_id", description="从内部 CRM 系统获取客户画像。")
async def get_customer_info(user_id: str) -> str:
    """调用内部微服务获取数据。"""
    service_url = "http://internal-crm-service:8080/v1/user/detail"
    
    result = await fetch_external_api(
        url=service_url,
        method="POST",
        json_data={"uid": user_id},
        headers={"Authorization": "Bearer internal-token"}
    )
    return str(result)

# 4. 其它本地工具...
@register_tool(category="math", arg_name="expression")
def calculate(expression: str) -> str:
    """执行数学运算。"""
    try:
        return f"结果: {eval(expression, {'__builtins__': {}})}"
    except:
        return "计算错误"

if __name__ == "__main__":
    logger.info(f"🚀 MCP 服务启动中... 端口: {PORT}")
    mcp.run(transport="sse", host="0.0.0.0", port=PORT)