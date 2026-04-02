# -*- coding: utf-8 -*-
"""Supervisor - ReAct 决策（委派子Agent / 调工具 / 结束）"""

from typing import Optional, Dict, Tuple
from uuid import uuid4
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.llm import get_model, get_model_by_level_id
from dataBase.ConfigService import SceneService, RoleService, SubAgentService
from app.tools.factory import load_tools_for_role
from logger import logger

_scene_service = SceneService()
_role_service = RoleService()
_sub_agent_service = SubAgentService()


class SupervisorDecision(BaseModel):
    next_action: str = Field(
        description="下一步动作：DELEGATE_SUBAGENT / ACT_TOOL / FINISH"
    )
    target_subagent: str = Field(default="", description="当 next_action=DELEGATE_SUBAGENT 时填写")
    tool_name: str = Field(default="", description="当 next_action=ACT_TOOL 时填写")
    tool_args: Dict = Field(default_factory=dict, description="当 next_action=ACT_TOOL 时填写")
    final_answer: str = Field(default="", description="当 next_action=FINISH 时填写")
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


def supervisor_node(state, config: RunnableConfig = None):
    scene_id = state.get("scene_id", "default")
    selected_role_id = state.get("selected_role_id", "")  # ← 新增
    messages = state.get("messages", [])

    # HITL 恢复直通：如果已有明确 current_agent 且 next=RUN_AGENT，
    # 则优先继续该 subagent，避免恢复时被重新路由到主Agent决策。
    resume_next = (state.get("next") or "").strip()
    resume_agent = (state.get("current_agent") or "").strip()
    resume_mode = bool(state.get("resume_mode"))
    if resume_mode and resume_agent and (resume_next in ("", "RUN_AGENT")):
        logger.info(f"Supervisor: resume直通 sub_agent={resume_agent}")
        return {
            "next": "RUN_AGENT",
            "next_action": "DELEGATE_SUBAGENT",
            "current_agent": resume_agent,
            "current_actor": resume_agent,
            "role_name": state.get("role_name") or "resume",
            "resume_mode": False,
        }

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
    role_tool_ids = []
    if role:
        available_subagents = _load_sub_agents_for_role(role)
        system_prompt = role.get("system_prompt", "")
        model_id = role.get("main_model_id")
        role_name = role.get("name", "unknown")
        role_tool_ids = role.get("tool_ids", []) or []
    else:
        available_subagents = _load_all_sub_agents_from_db()
        system_prompt = (
            "你是团队主管。请判断是否需要路由给某个子Agent；"
            "如果可以直接回答，则返回 FINISH 并给出 answer。"
        )
        model_id = None
        role_name = "fallback"
        role_tool_ids = []

    available_tools = load_tools_for_role(role or {})
    available_tool_names = [t.name for t in available_tools]

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
        "你要在以下动作中三选一：\n"
        "A) 直接回答：next_action='FINISH'，并在 final_answer 写最终答复\n"
        "B) 路由子Agent：next_action='DELEGATE_SUBAGENT'，并在 target_subagent 写名称\n"
        "C) 调用工具：next_action='ACT_TOOL'，并填写 tool_name / tool_args\n\n"
        "可用 sub_agent 列表：\n"
    )
    for name, desc in available_subagents.items():
        route_prompt += f"- {name}: {desc}\n"
    route_prompt += "\n可用工具列表：\n"
    if available_tool_names:
        for tn in available_tool_names:
            route_prompt += f"- {tn}\n"
    else:
        route_prompt += "- （无）\n"
    route_prompt += (
        "\n约束：\n"
        "1) 仅可选择上述 sub_agent 或 tool；\n"
        "2) 当工具不足以完成任务时，优先 DELEGATE_SUBAGENT；\n"
        "3) FINISH 必须提供 final_answer。"
    )

    logger.info(f"Supervisor: scene={scene_id}, role={role_name}, sub_agents={routable_names}")

    try:
        decision = llm_decision.invoke([("system", route_prompt), *messages], config=config)
        action = (decision.next_action or "").strip().upper()

        if action == "FINISH":
            if decision.final_answer and decision.final_answer.strip():
                return {
                    "next": "FINISH",
                    "next_action": "FINISH",
                    "current_actor": "supervisor",
                    "role_name": role_name,
                    "messages": [AIMessage(content=decision.final_answer)],
                }
            return {
                "next": "FINISH",
                "next_action": "FINISH",
                "current_actor": "supervisor",
                "role_name": role_name,
            }

        if action == "DELEGATE_SUBAGENT":
            target = (decision.target_subagent or "").strip()
            if target not in available_subagents:
                logger.warning(f"Supervisor 非法target_subagent='{target}'，兜底FINISH")
                return {
                    "next": "FINISH",
                    "next_action": "FINISH",
                    "current_actor": "supervisor",
                    "role_name": role_name,
                }
            return {
                "next": "RUN_AGENT",          # 固定路由键
                "next_action": "DELEGATE_SUBAGENT",
                "current_agent": target,         # 动态目标
                "current_actor": target,
                "role_name": role_name,
                "available_sub_agents": routable_names,
                "role_config": role or None,
            }

        if action == "ACT_TOOL":
            tool_name = (decision.tool_name or "").strip()
            if not tool_name or tool_name not in available_tool_names:
                logger.warning(f"Supervisor 非法tool_name='{tool_name}'，兜底FINISH")
                return {
                    "next": "FINISH",
                    "next_action": "FINISH",
                    "current_actor": "supervisor",
                    "role_name": role_name,
                }

            tool_call = {
                "id": f"supervisor_tool_{uuid4().hex[:12]}",
                "name": tool_name,
                "args": decision.tool_args or {},
                "type": "tool_call",
            }
            ai_msg = AIMessage(content=decision.reason or f"调用工具: {tool_name}", tool_calls=[tool_call])
            return {
                "next": "RUN_TOOL",
                "next_action": "ACT_TOOL",
                "current_actor": "supervisor",
                "current_agent": "",
                "role_name": role_name,
                "role_config": role or None,
                "messages": [ai_msg],
                "last_action": {
                    "type": "ACT_TOOL",
                    "tool_name": tool_name,
                    "tool_args": decision.tool_args or {},
                },
            }

        # 非法输出兜底
        logger.warning(f"Supervisor 非法next_action='{action}'，兜底FINISH")
        return {
            "next": "FINISH",
            "next_action": "FINISH",
            "current_actor": "supervisor",
            "role_name": role_name,
        }

    except Exception as e:
        logger.error(f"Supervisor 决策失败: {e}")
        return {
            "next": "FINISH",
            "next_action": "FINISH",
            "current_actor": "supervisor",
            "role_name": role_name,
        }
