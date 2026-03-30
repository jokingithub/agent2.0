# -*- coding: utf-8 -*-
"""Supervisor - 按 scene_id 查 scene → role → sub_agents，配置驱动路由"""

from typing import Optional, Dict, List, Tuple
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from app.core.llm import get_model, get_model_by_level_id
from app.core.agents_config import AGENT_REGISTRY
from dataBase.ConfigService import SceneService, RoleService, SubAgentService
from logger import logger

_scene_service = SceneService()
_role_service = RoleService()
_sub_agent_service = SubAgentService()


class SupervisorDecision(BaseModel):
    next: str = Field(description="下一步路由：sub_agent名称 或 FINISH")
    answer: str = Field(default="", description="如果选择FINISH，这里填直接回答内容")
    reason: str = Field(default="", description="路由原因")


# ============================================================
# 配置加载
# ============================================================

def _load_role_by_scene(scene_id: str) -> Optional[Dict]:
    """
    按 scene_id(scene_code) 查 scenes 表 → 拿第一个 role_id → 查 roles 表
    返回 role 文档，或 None
    """
    if not scene_id or scene_id == "default":
        return None

    try:
        scene = _scene_service.get_by_code(scene_id)
        if not scene:
            logger.info(f"scene_code '{scene_id}' 不存在，走兜底")
            return None

        role_ids = scene.get("available_role_ids", [])
        if not role_ids:
            logger.info(f"scene '{scene_id}' 没有关联 role，走兜底")
            return None

        # 一个 scene 只对应一个 role，取第一个
        role_id = role_ids[0]
        role = _role_service.get_by_id(role_id)
        if not role:
            logger.warning(f"role_id '{role_id}' 不存在（scene='{scene_id}'），走兜底")
            return None

        logger.info(f"scene '{scene_id}' → role '{role.get('name')}' (id={role_id})")
        return role

    except Exception as e:
        logger.warning(f"加载 scene→role 失败: {e}")
        return None


def _load_sub_agents_for_role(role: Dict) -> Dict[str, str]:
    """
    从 role.sub_agent_ids 查 sub_agents 表，返回 {name: description}
    """
    sub_agent_ids = role.get("sub_agent_ids", [])
    if not sub_agent_ids:
        return {}

    try:
        result = {}
        for sa_id in sub_agent_ids:
            sa = _sub_agent_service.get_by_id(sa_id)
            if sa and sa.get("name"):
                name = sa["name"]
                desc = sa.get("description") or sa.get("system_prompt", "")[:80]
                result[name] = desc
        return result
    except Exception as e:
        logger.warning(f"加载 sub_agents 失败: {e}")
        return {}


def _load_fallback_config() -> Tuple[Optional[Dict], Dict[str, str]]:
    """
    兜底：从 roles 全表找 name=supervisor，从 sub_agents 全表构建路由
    """
    role = None
    try:
        roles = _role_service.get_all()
        for r in roles:
            if r.get("name") in ("supervisor", "主管", "Supervisor"):
                role = r
                break
    except Exception:
        pass

    # 兜底 agent 列表
    try:
        agents = _sub_agent_service.get_all()
        if agents:
            agent_map = {}
            for a in agents:
                name = a.get("name", "")
                desc = a.get("description") or a.get("system_prompt", "")[:80]
                if name:
                    agent_map[name] = desc
            if agent_map:
                return role, agent_map
    except Exception:
        pass

    return role, AGENT_REGISTRY


# ============================================================
# Supervisor 节点
# ============================================================

def supervisor_node(state):
    scene_id = state.get("scene_id", "default")
    messages = state.get("messages", [])

    # ---- Step 1: 按 scene 加载 role ----
    role = _load_role_by_scene(scene_id)

    if role:
        # 配置驱动
        available_subagents = _load_sub_agents_for_role(role)
        system_prompt = role.get("system_prompt", "")
        model_id = role.get("main_model_id")
    else:
        # 兜底
        fallback_role, available_subagents = _load_fallback_config()
        if fallback_role:
            system_prompt = fallback_role.get("system_prompt", "")
            model_id = fallback_role.get("main_model_id")
            role = fallback_role
        else:
            system_prompt = ""
            model_id = None

    role_name = role.get("name") if role else "fallback"

    # 默认提示词兜底
    if not system_prompt:
        system_prompt = (
            "你是团队主管。请根据对话进度，在可用 subagent 中选择下一步。"
            "如果任务已完成或你可以直接回答，返回 FINISH。"
        )

    # ---- Step 2: 构建 LLM ----
    if model_id:
        llm_base = get_model_by_level_id(model_id)
    else:
        llm_base = get_model("high")

    # ---- Step 3: 构建路由列表 ----
    if not available_subagents:
        available_subagents = AGENT_REGISTRY

    routable = tuple(list(available_subagents.keys()) + ["FINISH"])
    sub_agent_names = list(available_subagents.keys())

    logger.info(
        f"Supervisor: scene='{scene_id}', "
        f"role='{role_name}', "
        f"sub_agents={sub_agent_names}"
    )

    # ---- Step 4: 快速终止（上一条是 sub_agent 的 AIMessage，任务已完成）----
    if messages:
        last = messages[-1]
        if isinstance(last, AIMessage):
            has_tools = bool(getattr(last, "tool_calls", None))
            content = (last.content or "") if isinstance(last.content, str) else str(last.content or "")
            if (not has_tools) and content.strip():
                return {
                    "next": "FINISH",
                    "role_name": role_name,
                }

    # ---- Step 5: 路由决策（一次 LLM 调用：直接回答 or 路由到 sub_agent）----
    llm_decision = llm_base.with_structured_output(SupervisorDecision)

    route_prompt = (
        f"{system_prompt}\n\n"
        f"---\n"
        f"你现在需要决策：\n"
        f"1. 如果用户的问题你可以直接回答（不需要专业子Agent处理），选择 next=\"FINISH\" 并在 answer 中给出回答。\n"
        f"2. 如果需要专业子Agent处理，选择对应的 sub_agent 名称。\n\n"
        f"可用 sub_agent 及其职责:\n"
    )
    for name, desc in available_subagents.items():
        route_prompt += f"  - {name}: {desc}\n"
    route_prompt += f"\nnext 只允许在 {list(routable)} 中选择。"

    try:
        decision = llm_decision.invoke([
            ("system", route_prompt),
            *messages,
        ])
        next_node = decision.next if decision.next in routable else "FINISH"
        logger.info(f"Supervisor 决策: next={next_node}, reason={decision.reason}")

        # 如果是 FINISH 且有直接回答，把回答作为消息返回
        if next_node == "FINISH" and decision.answer and decision.answer.strip():
            return {
                "messages": [AIMessage(content=decision.answer)],
                "next": "FINISH",
                "role_name": role_name,
            }

        return {
            "next": next_node,
            "role_name": role_name,
        }

    except Exception as e:
        logger.error(f"路由决策失败: {e}，默认 FINISH")
        return {
            "next": "FINISH",
            "role_name": role_name,
        }
