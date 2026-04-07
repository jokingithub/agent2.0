# -*- coding: utf-8 -*-
"""Supervisor 辅助函数"""

from typing import Optional, Dict
from dataBase.ConfigService import SceneService, RoleService, SubAgentService
from langchain_core.messages import AIMessage
from logger import logger

_scene_service = SceneService()
_role_service = RoleService()
_sub_agent_service = SubAgentService()


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
    """从 messages 中提取已完成的子Agent任务摘要。

    识别规则：
    - 如果 AIMessage 的 name 属性非空且不是 Supervisor，则视为子Agent返回
    - 处理 _marker 为 sub_agent_completed_no_summary 的情况
    """
    completed_details = []

    for msg in messages:
        if isinstance(msg, AIMessage):
            agent_name = getattr(msg, "name", "") or ""
            if agent_name in ("Supervisor", ""):
                continue
            content = msg.content or ""
            marker = msg.additional_kwargs.get("_marker", "") if msg.additional_kwargs else ""
            if marker == "sub_agent_completed_no_summary":
                summary = "(已执行，无额外输出)"
            elif content:
                summary = content[:150]
            else:
                summary = "(已执行)"
            completed_details.append(f"- {agent_name}: {summary}")

    if not completed_details:
        return ""

    return (
        "## 已完成的子任务\n"
        "以下子Agent已经执行完毕（在对话历史中可见）：\n"
        + "\n".join(completed_details)
        + "\n\n请根据这些结果判断是否还有未完成的任务。"
    )
