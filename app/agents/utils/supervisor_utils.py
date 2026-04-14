# -*- coding: utf-8 -*-
"""Supervisor 辅助函数 — bind_tools 模式（无 FINISH 工具）"""

from typing import Optional, Dict, List, Tuple, Any
from dataBase.ConfigService import SceneService, RoleService, SubAgentService, ToolService
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field
from app.tools.factory import load_tool_from_config
from logger import logger

_scene_service = SceneService()
_role_service = RoleService()
_sub_agent_service = SubAgentService()
_tool_service = ToolService()

# 前缀常量
PREFIX_SUB_AGENT = "sub_agent_"


# ============================================================
# 虚拟工具定义（仅 sub_agent）
# ============================================================

class _SubAgentArgs(BaseModel):
    instruction: str = Field(description="委派给子Agent的具体任务描述，必须清晰明确")

def _create_sub_agent_tool(name: str, description: str) -> BaseTool:
    """将 sub_agent 包装为虚拟工具。"""
    def _placeholder(instruction: str) -> str:
        return f"[sub_agent placeholder] {name}: {instruction}"

    return StructuredTool.from_function(
        func=_placeholder,
        name=f"{PREFIX_SUB_AGENT}{name}",
        description=f"[子Agent] {description}",
        args_schema=_SubAgentArgs,
        infer_schema=False,
    )


# ============================================================
# 加载函数
# ============================================================

def load_role_by_scene(scene_id: str) -> Optional[Dict]:
    if not scene_id or scene_id == "default":
        return None
    try:
        scene = _scene_service.get_by_code(scene_id)
        if not scene:
            return None
        role_ids = scene.get("available_role_ids", []) or []
        if not role_ids:
            return None
        role_id = role_ids[0]
        role = _role_service.get_by_id(role_id)
        return role
    except Exception as e:
        logger.warning(f"load_role_by_scene 失败 scene={scene_id}, err={e}")
        return None


def load_sub_agents_for_role(role: Dict) -> Dict[str, str]:
    """加载 role 关联的 sub_agents，返回 {name: description}"""
    result: Dict[str, str] = {}
    if not role:
        return result
    for sa_id in role.get("sub_agent_ids", []) or []:
        try:
            sa = _sub_agent_service.get_by_id(sa_id)
            if not sa:
                continue
            name = (sa.get("name") or "").strip()
            if not name:
                continue
            desc = (sa.get("description") or sa.get("system_prompt") or "")[:120]
            result[name] = desc
        except Exception as e:
            logger.warning(f"加载 role sub_agent 失败 sa_id={sa_id}, err={e}")
    return result


def load_direct_tool_instances_for_role(role: Dict) -> List[BaseTool]:
    """加载 role 直接关联的工具实例（真实 LangChain Tool）"""
    result: List[BaseTool] = []
    if not role:
        return result
    tool_ids = role.get("tool_ids", []) or []
    for tid in tool_ids:
        try:
            tool_instance = load_tool_from_config(tid, sub_agent_id=None)
            if tool_instance:
                result.append(tool_instance)
        except Exception as e:
            logger.warning(f"加载 role direct tool 失败 tool_id={tid}, err={e}")
    return result


def build_supervisor_tools(
    sub_agents: Dict[str, str],
    direct_tools: List[BaseTool],
) -> List[BaseTool]:
    """构建 Supervisor 的统一工具列表（不含 FINISH）。

    返回的工具列表包含：
    1. sub_agent 虚拟工具（sub_agent_xxx）
    2. 真实工具实例

    顺序：sub_agent 工具 → 真实工具
    """
    tools: List[BaseTool] = []

    # sub_agent 虚拟工具
    for name, desc in sub_agents.items():
        tools.append(_create_sub_agent_tool(name, desc))

    # 真实工具
    tools.extend(direct_tools)

    return tools


def parse_tool_call_type(tool_name: str) -> Tuple[str, str]:
    """解析 tool_call 的工具名，返回 (类型, 原始名/工具名)

    Returns:
        ("sub_agent", "文件查看") — sub_agent 虚拟工具
        ("tool", "baidu_search") — 真实工具
    """
    if tool_name.startswith(PREFIX_SUB_AGENT):
        return "sub_agent", tool_name[len(PREFIX_SUB_AGENT):]
    return "tool", tool_name


def load_all_sub_agents_from_db() -> Dict[str, str]:
    result: Dict[str, str] = {}
    try:
        all_agents = _sub_agent_service.get_all() or []
        for sa in all_agents:
            name = (sa.get("name") or "").strip()
            if not name:
                continue
            desc = (sa.get("description") or sa.get("system_prompt") or "")[:120]
            result[name] = desc
    except Exception as e:
        logger.warning(f"load_all_sub_agents_from_db 失败: {e}")
    return result


def build_completed_tasks_summary(messages) -> str:
    """从 messages 中提取已完成的子Agent/工具任务摘要。"""
    completed_details = []

    for msg in messages:
        if isinstance(msg, AIMessage):
            agent_name = getattr(msg, "name", "") or ""
            if agent_name in ("Supervisor", ""):
                continue
            content = msg.content or ""
            marker = msg.additional_kwargs.get("_marker", "") if msg.additional_kwargs else ""
            if marker == "sub_agent_completed_no_summary":
                raw = msg.additional_kwargs.get("_raw_content", "")
                summary = raw[:150] if raw else "(已执行，无额外输出)"
            elif content:
                summary = content[:150]
            else:
                summary = "(已执行)"
            completed_details.append(f"- {agent_name}: {summary}")

    if not completed_details:
        return ""

    return (
        "\n\n## 已完成的子任务\n"
        "以下能力已经执行完毕（在对话历史中可见）：\n"
        + "\n".join(completed_details)
        + "\n\n请根据这些结果判断是否还有未完成的任务。"
    )
