from core.decorators import register_tool
from core.utils import fetch_external_api
import os

@register_tool(category="search", description="调用外部搜索引擎查询实时信息。")
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