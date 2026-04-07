# -*- coding: utf-8 -*-
"""Supervisor - 运行时按 scene -> role -> sub_agents 决策，支持多轮任务编排"""

from typing import Optional, Dict, Tuple
from pydantic import BaseModel, Field
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from app.core.llm import get_model, get_model_by_level_id
from app.prompts.supervisor import SUPERVISOR_ROUTE_PROMPT, SUPERVISOR_DEFAULT_SYSTEM_PROMPT
from dataBase.ConfigService import SceneService, RoleService, SubAgentService
from logger import logger

_scene_service = SceneService()
_role_service = RoleService()
_sub_agent_service = SubAgentService()


class SupervisorDecision(BaseModel):
    next: str = Field(description="下一步路由：sub_agent名称 或 FINISH")
    instruction: str = Field(default="", description="委派给子Agent的具体任务描述")
    answer: str = Field(default="", description="如果选择 FINISH，给出最终汇总答复")
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

        role_id = role_ids[0]
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


# app/agents/supervisor.py 中的函数改动

def _build_completed_tasks_summary(messages) -> str:
    """从 messages 中提取已完成的子Agent任务摘要。

    识别模式：
    - 如果 AIMessage 的 name 属性非空且不是 "Supervisor"，说明是某个子Agent的返回
    - 如果返回内容为空或标记为 "_marker": "sub_agent_completed_no_summary"，说明是纯工具执行
    - 如果返回内容非空，说明是工具结果或总结
    """
    from langchain_core.messages import AIMessage

    completed_agents = set()
    completed_details = []

    for msg in messages:
        if isinstance(msg, AIMessage):
            agent_name = getattr(msg, "name", None) or ""

            # 跳过 Supervisor 自己的消息
            if agent_name in ("Supervisor", ""):
                continue

            # 记录这个 Agent 已执行过
            completed_agents.add(agent_name)

            # 提取内容摘要
            content = msg.content if msg.content else ""
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

def supervisor_node(state, config: RunnableConfig = None):
    scene_id = state.get("scene_id", "default")
    selected_role_id = state.get("selected_role_id", "")
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

    if role:
        available_subagents = _load_sub_agents_for_role(role)
        system_prompt = role.get("system_prompt", "")
        model_id = role.get("main_model_id")
        role_name = role.get("name", "unknown")
    else:
        available_subagents = _load_all_sub_agents_from_db()
        system_prompt = SUPERVISOR_DEFAULT_SYSTEM_PROMPT
        model_id = None
        role_name = "fallback"

    if not available_subagents:
        return {
            "next": "FINISH",
            "role_name": role_name,
            "sub_task_instruction": "",
            "messages": [AIMessage(content="当前未配置可用子Agent，请联系管理员。")],
        }

    # 2) LLM
    llm_base = get_model_by_level_id(model_id) if model_id else get_model("high")
    llm_decision = llm_base.with_structured_output(SupervisorDecision)

    # 3) 构建提示词
    routable_names = list(available_subagents.keys())

    agent_list = ""
    for name, desc in available_subagents.items():
        agent_list += f"- {name}: {desc}\n"

    completed_tasks_summary = _build_completed_tasks_summary(messages)

    route_prompt = SUPERVISOR_ROUTE_PROMPT.format(
        role_system_prompt=system_prompt,
        agent_list=agent_list,
        completed_tasks_summary=completed_tasks_summary,
    )

    logger.info(f"Supervisor: scene={scene_id}, role={role_name}, sub_agents={routable_names}")

    try:
        decision = llm_decision.invoke(
            [("system", route_prompt), *messages], config=config
        )
        nxt = (decision.next or "").strip()

        if nxt == "FINISH":
            answer = (decision.answer or "").strip()
            result = {
                "next": "FINISH",
                "role_name": role_name,
                "sub_task_instruction": "",
            }
            if answer:
                result["messages"] = [AIMessage(content=answer)]
            return result

        if nxt in available_subagents:
            instruction = (decision.instruction or "").strip()
            if not instruction:
                # 兜底：如果 LLM 没给 instruction，用原始用户消息
                instruction = f"请处理用户的请求（路由到 {nxt}）"

            logger.info(f"Supervisor: 委派 {nxt}, instruction='{instruction[:80]}...'")
            return {
                "next": "RUN_AGENT",
                "current_agent": nxt,
                "sub_task_instruction": instruction,
                "role_name": role_name,
                "available_sub_agents": routable_names,
                "role_config": role or None,
            }

        # 非法输出兜底
        logger.warning(f"Supervisor 非法next='{nxt}'，兜底FINISH")
        return {"next": "FINISH", "role_name": role_name, "sub_task_instruction": ""}

    except Exception as e:
        logger.error(f"Supervisor 决策失败: {e}")
        return {"next": "FINISH", "role_name": role_name, "sub_task_instruction": ""}
