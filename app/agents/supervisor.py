# -*- coding: utf-8 -*-
"""Supervisor - 运行时按 scene -> role -> sub_agents 决策"""

from typing import Optional, Dict, Tuple
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage

from app.core.llm import get_model, get_model_by_level_id
from dataBase.ConfigService import SceneService, RoleService, SubAgentService
from logger import logger

_scene_service = SceneService()
_role_service = RoleService()
_sub_agent_service = SubAgentService()


class SupervisorDecision(BaseModel):
    next: str = Field(description="下一步路由：sub_agent名称 或 FINISH")
    answer: str = Field(default="", description="如果选择 FINISH，可直接给答案")
    reason: str = Field(default="", description="决策原因")


def _load_role_by_scene(scene_id: str) -> Optional[Dict]:
    if not scene_id or scene_id == "default":
        return None

    try:
        scene = _scene_service.get_by_code(scene_id)
        if not scene:
            return None

        role_ids = scene.get("available_role_ids", []) or []
        if not role_ids:
            return None

        role_id = role_ids[0]  # 当前约定：一个 scene 一个 role（取第一个）
        role = _role_service.get_by_id(role_id)
        return role
    except Exception as e:
        logger.warning(f"_load_role_by_scene 失败 scene={scene_id}, err={e}")
        return None


def _load_sub_agents_for_role(role: Dict) -> Dict[str, str]:
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


def _load_all_sub_agents_from_db() -> Dict[str, str]:
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
        logger.warning(f"_load_all_sub_agents_from_db 失败: {e}")
    return result


def supervisor_node(state):
    scene_id = state.get("scene_id", "default")
    selected_role_id = state.get("selected_role_id", "")  # ← 新增
    messages = state.get("messages", [])

    # 1) 优先用前端指定的 role_id
    role = None
    if selected_role_id:
        try:
            role = _role_service.get_by_id(selected_role_id)
            if role:
                logger.info(f"Supervisor: 使用前端指定 role_id={selected_role_id}")
        except Exception as e:
            logger.warning(f"加载指定 role 失败 role_id={selected_role_id}, err={e}")

    # 2) 没指定或加载失败，走场景默认
    if not role:
        role = _load_role_by_scene(scene_id)

    # 后面逻辑不变 ↓
    if role:
        available_subagents = _load_sub_agents_for_role(role)
        system_prompt = role.get("system_prompt", "")
        model_id = role.get("main_model_id")
        role_name = role.get("name", "unknown")
    else:
        available_subagents = _load_all_sub_agents_from_db()
        system_prompt = (
            "你是团队主管。请判断是否需要路由给某个子Agent；"
            "如果可以直接回答，则返回 FINISH 并给出 answer。"
        )
        model_id = None
        role_name = "fallback"

    if not available_subagents:
        # 没有可路由子Agent，直接结束
        return {
            "next": "FINISH",
            "role_name": role_name,
            "messages": [AIMessage(content="当前未配置可用子Agent，请联系管理员。")],
        }

    # 2) LLM
    llm_base = get_model_by_level_id(model_id) if model_id else get_model("high")
    llm_decision = llm_base.with_structured_output(SupervisorDecision)

    # 3) prompt
    routable_names = list(available_subagents.keys())
    route_prompt = (
        f"{system_prompt}\n\n"
        "你要在以下动作中二选一：\n"
        "A) 直接回答：next='FINISH'，并在 answer 写最终答复\n"
        "B) 路由子Agent：next=某个 sub_agent 名称\n\n"
        "可用 sub_agent 列表：\n"
    )
    for name, desc in available_subagents.items():
        route_prompt += f"- {name}: {desc}\n"
    route_prompt += "\n务必严格选择：FINISH 或上述 sub_agent 名称之一。"

    logger.info(f"Supervisor: scene={scene_id}, role={role_name}, sub_agents={routable_names}")

    try:
        decision = llm_decision.invoke([("system", route_prompt), *messages])
        nxt = (decision.next or "").strip()

        if nxt == "FINISH":
            if decision.answer and decision.answer.strip():
                return {
                    "next": "FINISH",
                    "role_name": role_name,
                    "messages": [AIMessage(content=decision.answer)],
                }
            return {"next": "FINISH", "role_name": role_name}

        if nxt in available_subagents:
            return {
                "next": "RUN_AGENT",          # 固定路由键
                "current_agent": nxt,         # 动态目标
                "role_name": role_name,
                "available_sub_agents": routable_names,
                "role_config": role or None,
            }

        # 非法输出兜底
        logger.warning(f"Supervisor 非法next='{nxt}'，兜底FINISH")
        return {"next": "FINISH", "role_name": role_name}

    except Exception as e:
        logger.error(f"Supervisor 决策失败: {e}")
        return {"next": "FINISH", "role_name": role_name}
