# -*- coding: utf-8 -*-
import asyncio
import importlib.util
import json
from pathlib import Path
from typing import List, Any
from langchain_core.tools import Tool, BaseTool, StructuredTool
import importlib
from pydantic import BaseModel, ConfigDict, create_model
from logger import logger

# 假设这些服务已经存在
from dataBase.ConfigService import ToolService, SkillService, SubAgentService

_tool_service = ToolService()
_skill_service = SkillService()
_sub_agent_service = SubAgentService()

def _load_callable(entrypoint: str):
    """动态加载 Python 可调用对象

    Args:
        entrypoint: 格式 "module.path:callable_name"

    Returns:
        加载的函数或工具对象
    """
    if ":" not in entrypoint:
        raise ValueError(f"entrypoint 格式错误，应为 'module:callable'，实际: {entrypoint}")

    module_path, callable_name = entrypoint.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
        return getattr(module, callable_name)
    except (ImportError, AttributeError) as e:
        raise ImportError(f"无法加载 {entrypoint}: {e}")

def load_skill_as_tool(skill_dir: str) -> BaseTool:
    """从技能目录加载本地工具（*.py 中由 @tool 装饰导出的对象）。"""
    skill_path = Path(skill_dir)
    if not skill_path.exists() or not skill_path.is_dir():
        raise FileNotFoundError(f"技能目录不存在: {skill_dir}")

    py_files = sorted([p for p in skill_path.glob("*.py") if p.name != "__init__.py"])
    if not py_files:
        raise FileNotFoundError(f"技能目录下未找到Python文件: {skill_dir}")

    errors = []
    for py_file in py_files:
        module_name = f"skill_{skill_path.name}_{py_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(py_file))
            if spec is None or spec.loader is None:
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, BaseTool):
                    return attr
        except Exception as e:
            errors.append(f"{py_file.name}: {e}")

    raise RuntimeError(
        f"未在技能目录中找到可用工具对象: {skill_dir}；错误: {'; '.join(errors) if errors else '无'}"
    )


def _is_tool_exposed_to_agent(tool_config: dict, sub_agent_id: str | None) -> bool:
    """判断工具是否允许暴露给指定子 Agent。

    规则：
    1) enabled=False -> 不暴露
    2) config.expose_to_agent=False -> 不暴露
    3) config.allowed_sub_agent_ids 存在且非空 -> 仅白名单内暴露
    """
    if not tool_config or not tool_config.get("enabled", True):
        return False

    config = tool_config.get("config") or {}

    if not config.get("expose_to_agent", True):
        return False

    allowed_sub_agents = config.get("allowed_sub_agent_ids") or []
    if allowed_sub_agents:
        return bool(sub_agent_id and sub_agent_id in allowed_sub_agents)

    return True

async def _call_remote_mcp(url: str, tool_name: str, kwargs: dict) -> str:
    """异步调用远程 MCP 服务"""
    try:
        from fastmcp import Client
        # 使用 SSE 协议连接
        if hasattr(Client, "from_url"):
            client_ctx = Client.from_url(url)
        else:
            client_ctx = Client(url)

        async with client_ctx as client:
            result = await client.call_tool(tool_name, kwargs)

            # 提取文本内容（兼容 TextContent / dict / 其他对象）
            if hasattr(result, "content") and isinstance(result.content, list):
                parts: list[str] = []
                for c in result.content:
                    text_value = None

                    # 1) 典型对象：c.text
                    if hasattr(c, "text"):
                        text_value = getattr(c, "text", None)

                    # 2) dict 结构：{"text": "..."}
                    if text_value is None and isinstance(c, dict):
                        text_value = c.get("text")

                    # 3) 支持 pydantic/dataclass 风格对象
                    if text_value is None and hasattr(c, "model_dump"):
                        try:
                            dumped = c.model_dump()
                            if isinstance(dumped, dict):
                                text_value = dumped.get("text")
                        except Exception:
                            pass

                    # 有 text 则优先使用
                    if text_value is not None:
                        parts.append(str(text_value))
                        continue

                    # 无 text 时不丢弃，保留结构化内容避免“空返回”
                    if isinstance(c, dict):
                        parts.append(json.dumps(c, ensure_ascii=False))
                    else:
                        parts.append(str(c))

                joined = "\n".join([p for p in parts if p is not None and str(p).strip() != ""]).strip()
                if joined:
                    return joined

                # content 存在但为空时，回退到整体字符串，避免吞返回
                return str(result)
            return str(result)
    except Exception as e:
        logger.error(f"MCP 调用失败 [{tool_name}]: {e}")
        return f"工具调用失败: {e}"

def _build_mcp_kwargs(input_value: Any, arg_defs: dict[str, dict]) -> dict:
    # 支持 str(JSON) / dict 输入
    if isinstance(input_value, str):
        text = input_value.strip()
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    source = parsed
                else:
                    raise ValueError("字符串参数必须是JSON对象")
            except Exception:
                raise ValueError("参数必须是对象(dict)或可解析为对象的JSON字符串")
        else:
            source = {}
    elif isinstance(input_value, dict):
        source = {k: v for k, v in input_value.items() if v is not None}
    else:
        raise ValueError("参数必须是对象(dict)")

    result: dict[str, Any] = {}
    missing_required: list[str] = []

    for name, meta in arg_defs.items():
        required = bool((meta or {}).get("required", False))
        has_default = "default" in (meta or {})

        if name in source:
            result[name] = source[name]
        elif has_default:
            result[name] = meta["default"]
        elif required:
            missing_required.append(name)

    if missing_required:
        raise ValueError(f"缺少必填参数: {', '.join(missing_required)}")

    return result

def _type_name_to_py(type_name: str):
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "array": list,
        "object": dict,
        "any": Any,
    }
    return mapping.get((type_name or "any").lower(), Any)

def _create_mcp_tool(tool_config: dict) -> Tool:
    name = tool_config.get("name", "unnamed")
    description = tool_config.get("description", "")
    url = tool_config.get("url", "http://localhost:9001/sse")

    config = tool_config.get("config") or {}
    remote_tool_name = config.get("remote_tool_name", name)

    # 新格式：arg_names 是 dict
    arg_defs = config.get("arg_names") if isinstance(config.get("arg_names"), dict) else {}
    if not arg_defs:
        # 你说 tool 少，可以直接强约束，避免静默退化
        raise ValueError(f"MCP工具[{name}]缺少 config.arg_names(字典格式)")

    dynamic_fields: dict[str, tuple[type, Any]] = {}
    for arg_name, meta in arg_defs.items():
        meta = meta or {}
        py_type = _type_name_to_py(meta.get("type", "any"))
        required = bool(meta.get("required", False))
        default = ... if required and "default" not in meta else meta.get("default", None)
        dynamic_fields[arg_name] = (py_type, default)

    class _MCPArgsBase(BaseModel):
        model_config = ConfigDict(extra="allow")

    MCPArgsSchema = create_model(
        f"MCPArgs_{name}",
        __base__=_MCPArgsBase,
        **dynamic_fields,
    )

    def sync_wrapper(**tool_kwargs: Any) -> str:
        try:
            kwargs = _build_mcp_kwargs(tool_kwargs, arg_defs=arg_defs)
            return asyncio.run(_call_remote_mcp(url, remote_tool_name, kwargs))
        except Exception as e:
            return f"工具参数错误或调用失败: {e}"

    return StructuredTool.from_function(
        func=sync_wrapper,
        name=name,
        description=description,
        args_schema=MCPArgsSchema,
        infer_schema=False,
    )


def _create_http_tool(tool_config: dict) -> Tool:
    """HTTP 工具占位实现（当前项目未启用真实 HTTP 调用）。"""
    name = tool_config.get("name", "unnamed_http_tool")
    description = tool_config.get("description", "HTTP 工具")

    def sync_wrapper(input_value: Any) -> str:
        return f"HTTP 工具暂未实现: {name}，输入: {input_value}"

    return Tool(
        name=name,
        description=description,
        func=sync_wrapper,
    )

def load_tool_from_config(tool_id: str, sub_agent_id: str | None = None) -> Tool | None:
    """从 tools 表加载单个工具"""
    tool_config = _tool_service.get_by_id(tool_id)
    if not tool_config:
        logger.warning(f"tools 表未找到工具: {tool_id}")
        return None

    # 检查工具是否对该 sub_agent 可见
    if not _is_tool_exposed_to_agent(tool_config, sub_agent_id):
        return None

    if not tool_config.get("enabled", True):
        logger.info(f"工具 '{tool_config.get('name')}' 已禁用，跳过")
        return None

    tool_type = tool_config.get("type", "")

    if tool_type == "local":
        entrypoint = tool_config.get("config", {}).get("entrypoint")
        if not entrypoint:
            logger.warning(f"local 工具缺少 entrypoint: {tool_config.get('name')}")
            return None
        try:
            loaded = _load_callable(entrypoint)
            if isinstance(loaded, BaseTool):
                return loaded
            return Tool(
                name=tool_config.get("name", "unknown"),
                description=tool_config.get("description", ""),
                func=loaded
            )
        except Exception as e:
            logger.error(f"加载 local 工具失败: {e}")
            return None

    elif tool_type == "mcp":
        return _create_mcp_tool(tool_config)
    elif tool_type == "http":
        return _create_http_tool(tool_config)
    else:
        logger.warning(f"未知工具类型 '{tool_type}'，工具: {tool_config.get('name')}")
        return None


def load_tools_from_ids(tool_ids: List[str], sub_agent_id: str | None = None) -> List[Tool]:
    """按工具ID列表加载工具。"""
    tools: List[Tool] = []
    for tid in tool_ids or []:
        t = load_tool_from_config(tid, sub_agent_id=sub_agent_id)
        if t:
            tools.append(t)
    return tools


def load_tools_for_role(role_config: dict | None) -> List[Tool]:
    """为主Agent（role/supervisor）加载可用工具。"""
    if not role_config:
        return []
    tool_ids = role_config.get("tool_ids", []) or []
    return load_tools_from_ids(tool_ids, sub_agent_id=None)

def load_tools_for_sub_agent(sub_agent_id: str) -> List[Tool]:
    """为子 Agent 加载所有关联工具"""
    agent_config = _sub_agent_service.get_by_id(sub_agent_id)
    if not agent_config:
        return []

    all_tool_ids = set(agent_config.get("tool_ids", []))
    
    # 合并技能关联的工具
    for sid in agent_config.get("skill_ids", []):
        skill = _skill_service.get_by_id(sid)
        if skill:
            all_tool_ids.update(skill.get("tool_ids", []))

    return load_tools_from_ids(list(all_tool_ids), sub_agent_id=sub_agent_id)