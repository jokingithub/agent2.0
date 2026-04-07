# -*- coding: utf-8 -*-
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage
from app.core.llm import get_model, get_model_by_level_id
from app.prompts.supervisor import SUPERVISOR_ROUTE_PROMPT, SUPERVISOR_DEFAULT_SYSTEM_PROMPT
from app.agents.utils.supervisor_utils import (
    load_role_by_scene,
    load_sub_agents_for_role,
    load_all_sub_agents_from_db,
    build_completed_tasks_summary,
)
from dataBase.ConfigService import RoleService
import json
from logger import logger

_role_service = RoleService()

def supervisor_node(state, config: RunnableConfig = None):
    scene_id = state.get("scene_id", "default")
    selected_role_id = state.get("selected_role_id", "")
    messages = state.get("messages", [])

    role = None
    if selected_role_id:
        try:
            role = _role_service.get_by_id(selected_role_id)
            if role:
                logger.info(f"Supervisor: 使用指定 role_id={selected_role_id}")
        except Exception as e:
            logger.warning(f"加载指定 role 失败 role_id={selected_role_id}, err={e}")

    if not role:
        role = load_role_by_scene(scene_id)

    if role:
        available_subagents = load_sub_agents_for_role(role)
        system_prompt = role.get("system_prompt", "")
        model_id = role.get("main_model_id")
        role_name = role.get("name", "unknown")
    else:
        available_subagents = load_all_sub_agents_from_db()
        system_prompt = SUPERVISOR_DEFAULT_SYSTEM_PROMPT
        model_id = None
        role_name = "fallback"

    if not available_subagents:
        return {
            "next": "FINISH",
            "role_name": role_name,
            "sub_task_instruction": "",
            "agent_scratchpad": [],
            "messages": [AIMessage(content="当前未配置可用子Agent，请联系管理员。")],
        }

    from pydantic import BaseModel, Field

    class SupervisorDecision(BaseModel):
        next: str = Field(description="下一步路由：sub_agent名称 或 FINISH")
        instruction: str = Field(default="", description="委派给子Agent的具体任务描述")
        answer: str = Field(default="", description="如果选择 FINISH，给出最终汇总答复")
        reason: str = Field(default="", description="决策原因")

    llm_base = get_model_by_level_id(model_id) if model_id else get_model("high")
    llm_decision = llm_base.with_structured_output(SupervisorDecision)

    routable_names = list(available_subagents.keys())
    agent_list = "\n".join(f"- {n}: {d}" for n, d in available_subagents.items())
    completed_tasks_summary = build_completed_tasks_summary(messages)

    route_prompt = SUPERVISOR_ROUTE_PROMPT.format(
        role_system_prompt=system_prompt,
        agent_list=agent_list,
        completed_tasks_summary=completed_tasks_summary,
    )
    logger.info(f"Supervisor: scene={scene_id}, role={role_name}, agents={routable_names}")

    try:
        decision = llm_decision.invoke([("system", route_prompt), *messages], config=config)
        raw_decision = decision.model_dump() if hasattr(decision, "model_dump") else str(decision)
        logger.info(
            "RAW_SUPERVISOR_DECISION agent=Supervisor payload=%s",
            json.dumps(raw_decision, ensure_ascii=False, default=str),
        )

        nxt = (decision.next or "").strip()

        if nxt == "FINISH":
            answer = (decision.answer or "").strip()
            res = {
                "next": "FINISH",
                "role_name": role_name,
                "sub_task_instruction": "",
                "agent_scratchpad": [],
            }
            if answer:
                res["messages"] = [AIMessage(content=answer)]
            return res

        if nxt in available_subagents:
            instr = (decision.instruction or "").strip() or f"请处理用户请求（路由到 {nxt}）"
            return {
                "next": "RUN_AGENT",
                "current_agent": nxt,
                "sub_task_instruction": instr,
                "role_name": role_name,
                "available_sub_agents": routable_names,
                "role_config": role or None,
                "agent_scratchpad": [],  # 关键：新任务清空私有上下文
                "user_input_required": False,
                "suspended_action": "",
                "pending_context": {},
            }

        logger.warning(f"Supervisor 非法next='{nxt}'，兜底FINISH")
        return {
            "next": "FINISH",
            "role_name": role_name,
            "sub_task_instruction": "",
            "agent_scratchpad": [],
        }

    except Exception as e:
        logger.error(f"Supervisor 决策失败: {e}")
        return {
            "next": "FINISH",
            "role_name": role_name,
            "sub_task_instruction": "",
            "agent_scratchpad": [],
        }