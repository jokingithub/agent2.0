# -*- coding: utf-8 -*-
import asyncio
import importlib.util
from pathlib import Path
from typing import List, Any
from langchain_core.tools import Tool, BaseTool
from logger import logger

# 假设这些服务已经存在
from dataBase.ConfigService import ToolService, SkillService, SubAgentService

_tool_service = ToolService()
_skill_service = SkillService()
_sub_agent_service = SubAgentService()


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

async def _call_remote_mcp(url: str, tool_name: str, arg_name: str, arg_value: str) -> str:
    """异步调用远程 MCP 服务"""
    try:
        from fastmcp import Client
        # 使用 SSE 协议连接
        async with Client.from_url(url) as client:
            # 构造参数字典，例如 {"city": "北京"}
            kwargs = {arg_name: arg_value}
            result = await client.call_tool(tool_name, kwargs)
            
            # 提取文本内容
            if hasattr(result, "content") and isinstance(result.content, list):
                return "\n".join([str(c.text) for c in result.content if hasattr(c, "text")])
            return str(result)
    except Exception as e:
        logger.error(f"MCP 调用失败 [{tool_name}]: {e}")
        return f"工具调用失败: {e}"

def _create_mcp_tool(tool_config: dict) -> Tool:
    """将数据库记录转换为 LangChain Tool"""
    name = tool_config.get("name", "unnamed")
    description = tool_config.get("description", "")
    url = tool_config.get("url", "http://localhost:9001/sse")
    
    config = tool_config.get("config") or {}
    remote_tool_name = config.get("remote_tool_name", name)
    # 映射参数名，如果没配则默认为 query
    arg_name = config.get("arg_name", "query")

    def sync_wrapper(input_str: str) -> str:
        """LangChain 通常是同步调用，这里做转换"""
        try:
            # 在同步环境中运行异步逻辑
            return asyncio.run(_call_remote_mcp(url, remote_tool_name, arg_name, input_str))
        except Exception as e:
            return f"系统错误: {e}"

    return Tool(
        name=name,
        description=description,
        func=sync_wrapper
    )

def load_tool_from_config(tool_id: str, sub_agent_id: str | None = None) -> Tool | None:
    """加载单个工具入口"""
    tool_config = _tool_service.get_by_id(tool_id)
    if not _is_tool_exposed_to_agent(tool_config, sub_agent_id):
        if tool_config:
            logger.info(
                f"工具未暴露给子Agent，跳过: tool={tool_config.get('name')} agent={sub_agent_id}"
            )
        return None

    t_type = str(tool_config.get("type", "")).lower()
    
    # 只要是 mcp 或 http 类型，统一走 MCP 协议调用
    if t_type in ["mcp", "http"]:
        return _create_mcp_tool(tool_config)
    
    logger.warning(f"跳过不支持的工具类型: {t_type}")
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