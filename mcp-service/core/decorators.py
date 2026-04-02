from core.config import mcp, tool_service, TOOL_URL
from logger import logger
import inspect
from typing import Any, get_origin, get_args, Union

def _annotation_to_type_name(annotation: Any) -> str:
    if annotation is inspect._empty:
        return "any"

    origin = get_origin(annotation)
    args = get_args(annotation)

    # Optional[T] / Union[T, None]
    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _annotation_to_type_name(non_none[0])
        return "any"

    if annotation is str:
        return "string"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is bool:
        return "boolean"
    if annotation in (dict,):
        return "object"
    if annotation in (list, tuple, set):
        return "array"

    if origin in (list, tuple, set):
        return "array"
    if origin in (dict,):
        return "object"

    return "any"

def register_tool(category: str, description: str = None):
    def decorator(func):
        final_desc = description or (func.__doc__ or "未分类工具").split('\n')[0].strip()
        tool_name = func.__name__

        # 1) 注册到 FastMCP
        mcp.tool()(func)

        # 2) 从函数签名构建 arg_names(字典)
        sig = inspect.signature(func)
        arg_names: dict[str, dict[str, Any]] = {}

        for p in sig.parameters.values():
            if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue

            field = {
                "type": _annotation_to_type_name(p.annotation),
                "required": p.default is inspect._empty,
            }
            if p.default is not inspect._empty:
                field["default"] = p.default

            arg_names[p.name] = field

        # 3) 同步到数据库
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
                    "arg_names": arg_names,  # <- 字典格式
                    "expose_to_agent": True,
                },
            }
            tool_service.upsert_mcp_tool(tool_payload)
            logger.info(f"✅ MCP工具同步成功: {tool_name}, args={list(arg_names.keys())}")
        except Exception as e:
            logger.error(f"❌ MCP工具同步失败 [{tool_name}]: {e}")

        return func
    return decorator