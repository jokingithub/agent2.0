import os
import sys
from pathlib import Path
from typing import Any, Callable

from fastmcp import FastMCP

# 确保从 mcp_service 目录直接启动时，也能导入项目根目录模块
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

mcp = FastMCP("DynamicServer")


def _is_enabled(value: Any) -> bool:
    """兼容 bool / 字符串 / 空值 的 enabled 判断。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _safe_eval(expression: str) -> str:
    """简单安全计算（仅用于示例）。"""
    try:
        result = eval(expression, {"__builtins__": {}})
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"


def _read_file_content(file_id: str) -> str:
    """按 file_id 读取文件内容。"""
    try:
        from dataBase.Service import FileService

        file_service = FileService()
        file_info = file_service.get_file_info(file_id)
        if not file_info:
            return f"未找到文件 ID: {file_id}"

        return str({"file_name": file_info.get("file_name", ""), "content": file_info.get("content", "")})
    except Exception as e:
        return f"读取文件错误: {e}"


def _resolve_handler(tool_name: str, tool_config: dict[str, Any]) -> Callable[[str], str]:
    """根据工具名或配置选择处理函数。"""
    config = tool_config.get("config") or {}
    handler_name = str(config.get("handler", "")).strip().lower()
    normalized_name = tool_name.strip().lower()

    if handler_name in {"calculate", "calc"} or normalized_name in {"calc_tool", "calculate"}:
        return _safe_eval

    if handler_name in {"read_file", "file"} or normalized_name in {"read_file", "read_file_tool"}:
        return _read_file_content

    if handler_name in {"email", "send_email"} or normalized_name == "email_tool":
        return lambda query: f"[模拟发送邮件] 内容: {query}"

    # 默认回显
    return lambda query: f"工具 {tool_name} 收到指令: {query}"

def create_tool(name: str, description: str = "", handler: Callable[[str], str] | None = None):
    """闭包工厂：动态创建函数"""
    def dynamic_func(query: str) -> str:
        if handler is None:
            return f"工具 {name} 收到指令: {query}"
        return handler(query)
    
    # 动态修改函数名和文档，这对模型理解至关重要
    dynamic_func.__name__ = name
    dynamic_func.__doc__ = description or f"这是动态生成的 {name} 工具描述"
    return dynamic_func


def load_active_tools() -> list[dict[str, Any]]:
    """优先从数据库读取启用的 MCP 工具，读取失败则回退默认工具。"""
    env_tools = os.getenv("MCP_ACTIVE_TOOLS", "").strip()
    if env_tools:
        names = [n.strip() for n in env_tools.split(",") if n.strip()]
        return [{"name": n, "description": f"动态工具 {n}", "config": {}} for n in names]

    try:
        from dataBase.ConfigService import ToolService

        service = ToolService()
        rows = service.get_all()
        mcp_tools = []
        for row in rows:
            if str(row.get("type", "")).strip().lower() != "mcp":
                continue
            if not _is_enabled(row.get("enabled", True)):
                continue
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            mcp_tools.append(row)

        if mcp_tools:
            return mcp_tools
    except Exception as e:
        print(f"[mcp_service] 从数据库加载工具失败，使用默认工具: {e}")

    # 默认兜底
    return [
        {"name": "search_tool", "description": "搜索工具", "config": {}},
        {"name": "calc_tool", "description": "计算工具", "config": {"handler": "calculate"}},
        {"name": "email_tool", "description": "邮件工具", "config": {"handler": "email"}},
    ]


for tool in load_active_tools():
    tool_name = str(tool.get("name", "")).strip()
    if not tool_name:
        continue
    description = str(tool.get("description", "")).strip()
    handler = _resolve_handler(tool_name, tool)
    func = create_tool(tool_name, description=description, handler=handler)
    mcp.add_tool(func)  # 编程式注册

if __name__ == "__main__":
    # 默认使用可远程调用的 streamable-http，便于主系统替换本地工具调用。
    # 如需兼容本地stdio模式，可设置 MCP_TRANSPORT=stdio。
    transport = os.getenv("MCP_TRANSPORT", "streamable-http")

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "9001"))
        # FastMCP v3 支持 streamable-http / sse 等传输。
        mcp.run(transport=transport, host=host, port=port)