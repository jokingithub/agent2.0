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
            
            # 提取文本内容
            if hasattr(result, "content") and isinstance(result.content, list):
                return "\n".join([str(c.text) for c in result.content if hasattr(c, "text")])
            return str(result)
    except Exception as e:
        logger.error(f"MCP 调用失败 [{tool_name}]: {e}")
        return f"工具调用失败: {e}"


def _build_mcp_kwargs(input_value: Any, arg_name: str = "query", arg_names: list[str] | None = None) -> dict:
    """将 LangChain 输入转换为 MCP kwargs。

    规则：
    - dict 输入：
      - 若配置了 arg_names，则按白名单过滤后透传；
      - 否则若已包含 arg_name 键，直接透传；
      - 否则包装为 {arg_name: input_value}（适配 data:dict 场景）。
    - str 输入：尝试 JSON 解析为 dict，失败则按单参数包装。
    - 其他输入：转为字符串按单参数包装。
    """
    if isinstance(input_value, dict):
        # 先清理 None 值，避免把默认空字段（如 data=None）透传给远端 MCP
        cleaned = {k: v for k, v in input_value.items() if v is not None}

        if arg_names:
            filtered = {k: cleaned.get(k) for k in arg_names if k in cleaned}
            if filtered:
                return filtered
        if arg_name in cleaned:
            return cleaned
        return {arg_name: cleaned}

    if isinstance(input_value, str):
        text = input_value.strip()
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    if arg_names:
                        filtered = {k: parsed.get(k) for k in arg_names if k in parsed}
                        if filtered:
                            return filtered
                    if arg_name in parsed:
                        return parsed
                    return {arg_name: parsed}
            except Exception:
                pass
        return {arg_name: input_value}

    return {arg_name: str(input_value)}

def _create_mcp_tool(tool_config: dict) -> Tool:
    """将数据库记录转换为 LangChain Tool"""
    name = tool_config.get("name", "unnamed")
    description = tool_config.get("description", "")
    url = tool_config.get("url", "http://localhost:9001/sse")
    
    config = tool_config.get("config") or {}
    remote_tool_name = config.get("remote_tool_name", name)
    # 映射参数名，如果没配则默认为 query
    arg_name = config.get("arg_name", "query")
    arg_names = config.get("arg_names") if isinstance(config.get("arg_names"), list) else None

    # 生成 StructuredTool 入参模型，避免 SimpleTool 的单参数限制
    dynamic_fields: dict[str, tuple[type, Any]] = {}
    if arg_names:
        for k in arg_names:
            dynamic_fields[k] = (Any, None)
    else:
        dynamic_fields[arg_name] = (Any, None)
    # 运行时注入常用字段，声明为可选，避免校验报错
    dynamic_fields.setdefault("app_id", (str, None))

    class _MCPArgsBase(BaseModel):
        model_config = ConfigDict(extra="allow")

    MCPArgsSchema = create_model(
        f"MCPArgs_{name}",
        __base__=_MCPArgsBase,
        **dynamic_fields,
    )

    def sync_wrapper(**tool_kwargs: Any) -> str:
        """StructuredTool 调用入口，接收多参数 kwargs。"""
        try:
            kwargs = _build_mcp_kwargs(tool_kwargs, arg_name=arg_name, arg_names=arg_names)
            # 在同步环境中运行异步逻辑
            return asyncio.run(_call_remote_mcp(url, remote_tool_name, kwargs))
        except Exception as e:
            return f"系统错误: {e}"

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

    tools = []
    for tid in all_tool_ids:
        t = load_tool_from_config(tid, sub_agent_id=sub_agent_id)
        if t:
            tools.append(t)
    return tools