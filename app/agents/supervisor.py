# -*- coding: utf-8 -*-
"""Supervisor 节点 — bind_tools 模式（无 FINISH 工具）

纯文本输出 = 最终回复（streaming），有 tool_calls = 继续执行。
"""

import json
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, SystemMessage
from app.core.llm import get_model, get_model_by_level_id
from app.prompts.supervisor import SUPERVISOR_SYSTEM_PROMPT, SUPERVISOR_DEFAULT_SYSTEM_PROMPT
from app.agents.utils.supervisor_utils import (
    load_role_by_scene,
    load_sub_agents_for_role,
    load_direct_tool_instances_for_role,
    load_all_sub_agents_from_db,
    build_completed_tasks_summary,
    build_supervisor_tools,
    parse_tool_call_type,
)
from dataBase.ConfigService import RoleService
from logger import logger

_role_service = RoleService()


def _try_parse_tool_calls_from_content(response: AIMessage) -> list:
    """尝试从 AIMessage.content 中解析出被错误输出为文本的 tool_calls。

    某些模型（如 Gemini）会把 function call 以 JSON 文本形式输出到 content 中，
    而不是放在 tool_calls 字段。这里做兜底解析。
    """
    content = (response.content or "").strip()
    if not content:
        return []

    try:
        parsed = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(parsed, dict):
        return []

    raw_calls = parsed.get("tool_calls")
    if not isinstance(raw_calls, list) or not raw_calls:
        return []

    result = []
    for rc in raw_calls:
        if not isinstance(rc, dict):
            continue

        # 格式1: {"id": "...", "type": "function", "function": {"name": "...", "arguments": "..."}}
        func_info = rc.get("function")
        if isinstance(func_info, dict):
            name = func_info.get("name", "")
            raw_args = func_info.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except (json.JSONDecodeError, TypeError):
                    args = {"raw": raw_args}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
            tc_id = rc.get("id", f"parsed_{name}_{id(rc)}")
            result.append({"name": name, "args": args, "id": tc_id})
            continue

        # 格式2: {"name": "...", "args": {...}, "id": "..."}
        name = rc.get("name", "")
        if name:
            args = rc.get("args", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {"raw": args}
            tc_id = rc.get("id", f"parsed_{name}_{id(rc)}")
            result.append({"name": name, "args": args if isinstance(args, dict) else {}, "id": tc_id})

    if result:
        response.content = ""
        if hasattr(response, "tool_calls"):
            response.tool_calls = result

    return result


def supervisor_node(state, config: RunnableConfig = None):
    scene_id = state.get("scene_id", "default")
    selected_role_id = state.get("selected_role_id", "")
    messages = state.get("messages", [])

    # ── 加载 role ──
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
        sub_agents = load_sub_agents_for_role(role)
        direct_tool_instances = load_direct_tool_instances_for_role(role)
        system_prompt_base = role.get("system_prompt", "")
        model_id = role.get("main_model_id")
        role_name = role.get("name", "unknown")
        role_tool_ids = role.get("tool_ids", []) or []
    else:
        sub_agents = load_all_sub_agents_from_db()
        direct_tool_instances = []
        system_prompt_base = SUPERVISOR_DEFAULT_SYSTEM_PROMPT
        model_id = None
        role_name = "fallback"
        role_tool_ids = []

    available_tools = load_tools_for_role(role or {})
    available_tool_names = [t.name for t in available_tools]

    # ── 构建工具列表（不含 FINISH）──
    supervisor_tools = build_supervisor_tools(sub_agents, direct_tool_instances)

    if not supervisor_tools:
        # 没有任何工具，Supervisor 只能直接回复
        logger.info("Supervisor: 无可用工具，将作为纯对话模式运行")

    # ── 构建 system prompt ──
    completed_tasks_summary = build_completed_tasks_summary(messages)
    system_prompt = SUPERVISOR_SYSTEM_PROMPT.format(
        role_system_prompt=system_prompt_base,
        completed_tasks_summary=completed_tasks_summary,
    )

    # ── 构建 LLM ──
    llm_base = get_model_by_level_id(model_id) if model_id else get_model("high")

    if supervisor_tools:
        llm_final = llm_base.bind_tools(supervisor_tools)
    else:
        llm_final = llm_base

    tool_names = [t.name for t in supervisor_tools]
    logger.info(f"Supervisor: scene={scene_id}, role={role_name}, tools={tool_names}")

    # ── 构建调用消息 ──
    supervisor_pad = list(state.get("supervisor_scratchpad") or [])

    if supervisor_pad:
        invoke_messages = [SystemMessage(content=system_prompt)] + list(messages) + supervisor_pad
    else:
        invoke_messages = [SystemMessage(content=system_prompt)] + list(messages)

    try:
        response = llm_final.invoke(invoke_messages, config=config)

        # 日志
        raw_log = {
            "content": getattr(response, "content", ""),
            "tool_calls": getattr(response, "tool_calls", None),
        }
        logger.info(
            "RAW_SUPERVISOR_DECISION agent=Supervisor payload=%s",
            json.dumps(raw_log, ensure_ascii=False, default=str),
        )

        tool_calls = getattr(response, "tool_calls", None)

        # ── 兜底：某些模型会把 tool_calls 输出到 content 文本中 ──
        if not tool_calls and isinstance(response, AIMessage) and response.content:
            tool_calls = _try_parse_tool_calls_from_content(response)
            if tool_calls:
                logger.info("Supervisor: 从 content 文本中解析出 tool_calls（模型兜底）")

        if not tool_calls:
            # ── 纯文本输出 = 最终回复 → FINISH ──
            text_content = ""
            if isinstance(response, AIMessage):
                text_content = response.content if isinstance(response.content, str) else str(response.content or "")
            else:
                text_content = str(response)

            return {
                "next": "FINISH",
                "role_name": role_name,
                "sub_task_instruction": "",
                "agent_scratchpad": [],
                "supervisor_scratchpad": [],
                "messages": [AIMessage(content=text_content)] if text_content else [],
            }

        # ── 有 tool_calls，解析第一个 ──
        first_tc = tool_calls[0]
        tc_name = first_tc.get("name", "") if isinstance(first_tc, dict) else getattr(first_tc, "name", "")
        tc_args = first_tc.get("args", {}) if isinstance(first_tc, dict) else getattr(first_tc, "args", {})
        tc_id = first_tc.get("id", "") if isinstance(first_tc, dict) else getattr(first_tc, "id", "")

        cap_type, real_name = parse_tool_call_type(tc_name)

        if cap_type == "sub_agent":
            instruction = tc_args.get("instruction", "") if isinstance(tc_args, dict) else str(tc_args)
            new_pad = supervisor_pad + [response]
            return {
                "next": "RUN_AGENT",
                "current_agent": real_name,
                "sub_task_instruction": instruction or f"请处理用户请求（路由到 {real_name}）",
                "role_name": role_name,
                "available_sub_agents": list(sub_agents.keys()),
                "role_config": role or None,
                "agent_scratchpad": [],
                "supervisor_scratchpad": new_pad,
                "user_input_required": False,
                "suspended_action": "",
                "pending_context": {},
            }

        if cap_type == "tool":
            response.name = "Supervisor"
            new_pad = supervisor_pad + [response]
            return {
                "next": "RUN_SUPERVISOR_TOOL",
                "role_name": role_name,
                "role_config": role or None,
                "supervisor_scratchpad": new_pad,
                "user_input_required": False,
                "suspended_action": "",
                "pending_context": {},
            }

        # 未知类型，兜底
        logger.warning(f"Supervisor 未知 tool_call name='{tc_name}'，兜底 FINISH")
        return {
            "next": "FINISH",
            "role_name": role_name,
            "sub_task_instruction": "",
            "agent_scratchpad": [],
            "supervisor_scratchpad": [],
        }

    except Exception as e:
        logger.error(f"Supervisor 决策失败: {e}", exc_info=True)
        return {
            "next": "FINISH",
            "role_name": role_name,
            "sub_task_instruction": "",
            "agent_scratchpad": [],
            "supervisor_scratchpad": [],
            "messages": [AIMessage(content="系统处理异常，请稍后重试。")],
        }
