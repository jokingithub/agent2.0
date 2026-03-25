# -*- coding: utf-8 -*-
#文件：app/tools/factory.py

import importlib
import asyncio
from pathlib import Path
from typing import List

import yaml
from langchain_core.tools import BaseTool, Tool

from logger import logger
from dataBase.ConfigService import ToolService, SkillService

_tool_service = ToolService()
_skill_service = SkillService()


#============================================================
# 本地 skill 加载（保留原有逻辑）
# ============================================================

def _parse_front_matter(md_content: str) -> tuple[dict, str]:
    """解析Markdown Front Matter，返回(metadata, body)。"""
    if not md_content.startswith("---"):
        raise ValueError("skill.md 缺少 Front Matter，请以 --- 开头。")

    parts = md_content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("skill.md Front Matter 格式错误。")

    _, header_str, body = parts
    metadata = yaml.safe_load(header_str) or {}
    return metadata, body.strip()


def _load_callable(entrypoint: str):
    """按module_path:function_name 动态导入函数。"""
    if ":" not in entrypoint:
        raise ValueError("entrypoint 格式应为 'module.path:function_name'。")

    module_path, func_name = entrypoint.split(":", 1)
    module = importlib.import_module(module_path)
    func = getattr(module, func_name, None)
    if func is None:
        raise ValueError(f"未在模块 {module_path} 中找到函数 {func_name}。")
    return func


def load_skill_as_tool(skill_dir: str) -> Tool:
    """从 skill 目录加载 Tool（保留原有逻辑不变）。"""
    skill_md = Path(skill_dir) / "skill.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"未找到 {skill_md}")

    content = skill_md.read_text(encoding="utf-8")
    metadata, body = _parse_front_matter(content)

    name = metadata.get("name")
    description = metadata.get("description", "")
    custom_meta = metadata.get("metadata") or {}
    entrypoint = metadata.get("entrypoint") or custom_meta.get("entrypoint")

    if not name:
        raise ValueError("skill.md 缺少必填字段: name")
    if not entrypoint:
        raise ValueError("skill.md 缺少必填字段: metadata.entrypoint（或 entrypoint）")

    loaded = _load_callable(entrypoint)

    if isinstance(loaded, BaseTool):
        if description.strip() or body:
            loaded.description = (
                f"{description.strip()}\n\n详细说明:\n{body}".strip()if body
                else description.strip()
            )
        return loaded

    final_description = description.strip() or (loaded.__doc__ or "")
    if body:
        final_description = f"{final_description}\n\n详细说明:\n{body}".strip()

    return Tool(name=name, description=final_description, func=loaded)


# ============================================================
# 配置表工具加载（新增）
# ============================================================

def _create_mcp_tool(tool_config: dict) -> Tool:
    """从 tools 表的 MCP 类型配置创建 Tool（真实调用 FastMCP 服务）"""
    name = tool_config.get("name", "unknown_mcp_tool")
    description = tool_config.get("description", "MCP工具")
    url = tool_config.get("url", "")
    config = tool_config.get("config") or {}
    remote_tool_name = config.get("remote_tool_name", name)
    timeout = config.get("timeout", 30)

    if not url:
        logger.warning(f"MCP工具 '{name}' 缺少 url 配置")
        return Tool(name=name, description=description, func=lambda query: f"[MCP工具 '{name}' 配置缺失: url]")

    async def _invoke_mcp(query: str) -> str:
        try:
            from fastmcp import Client
        except Exception as e:
            return f"[MCP工具 '{name}' 依赖缺失: {e}. 请在主系统运行环境安装 fastmcp]"

        async with Client(url, timeout=timeout) as client:
            result = await client.call_tool(remote_tool_name, {"query": query})

            # FastMCP CallToolResult 一般提供 content 列表，按文本拼接返回。
            content = getattr(result, "content", None)
            if isinstance(content, list):
                text_parts = []
                for item in content:
                    text = getattr(item, "text", None)
                    if text is not None:
                        text_parts.append(str(text))
                    else:
                        text_parts.append(str(item))
                return "\n".join(text_parts).strip() or str(result)

            return str(result)

    def mcp_tool(query: str) -> str:
        try:
            return asyncio.run(_invoke_mcp(query))
        except Exception as e:
            logger.exception(f"调用MCP工具失败: {name}, url={url}")
            return f"[MCP工具 '{name}' 调用失败: {e}]"

    return Tool(name=name, description=description, func=mcp_tool)


def _create_http_tool(tool_config: dict) -> Tool:
    """从 tools 表的 HTTP 类型配置创建 Tool（占位）"""
    name = tool_config.get("name", "unknown_http_tool")
    description = tool_config.get("description", "HTTP工具")
    url = tool_config.get("url", "")

    def http_placeholder(query: str) -> str:
        return f"[HTTP工具 '{name}' 尚未接入，目标地址: {url}，输入: {query}]"

    return Tool(name=name, description=description, func=http_placeholder)


def load_tool_from_config(tool_id: str) -> Tool | None:
    """从 tools 表加载单个工具"""
    tool_config = _tool_service.get_by_id(tool_id)
    if not tool_config:
        logger.warning(f"tools 表未找到工具: {tool_id}")
        return None

    if not tool_config.get("enabled", True):
        logger.info(f"工具 '{tool_config.get('name')}' 已禁用，跳过")
        return None

    tool_type = tool_config.get("type", "")

    if tool_type == "mcp":
        return _create_mcp_tool(tool_config)
    elif tool_type == "http":
        return _create_http_tool(tool_config)
    else:
        logger.warning(f"未知工具类型 '{tool_type}'，工具: {tool_config.get('name')}")
        return None


def load_tools_from_config(tool_ids: List[str]) -> List[Tool]:
    """批量从 tools 表加载工具"""
    tools = []
    for tid in tool_ids:
        tool = load_tool_from_config(tid)
        if tool:
            tools.append(tool)
    return tools


def load_tools_for_sub_agent(sub_agent_id: str) -> List[Tool]:
    """
    加载子Agent的所有工具：
    1. sub_agents.tool_ids → 直接关联的工具
    2. sub_agents.skill_ids → 技能 → skills.tool_ids → 间接关联的工具
    合并去重后返回。
    """
    from dataBase.ConfigService import SubAgentService
    _sub_agent_service = SubAgentService()

    agent_config = _sub_agent_service.get_by_id(sub_agent_id)
    if not agent_config:
        logger.warning(f"sub_agents 表未找到: {sub_agent_id}")
        return []

    all_tool_ids = set()

    # 直接关联的工具
    direct_tool_ids = agent_config.get("tool_ids", [])
    all_tool_ids.update(direct_tool_ids)

    # 通过技能间接关联的工具
    skill_ids = agent_config.get("skill_ids", [])
    for sid in skill_ids:
        skill = _skill_service.get_by_id(sid)
        if skill:
            all_tool_ids.update(skill.get("tool_ids", []))

    return load_tools_from_config(list(all_tool_ids))
