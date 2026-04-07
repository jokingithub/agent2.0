# -*- coding: utf-8 -*-
import json
from typing import Optional, Dict, Any, List
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode
from dataBase.ConfigService import SubAgentService
from app.agents.utils.agent_creator import create_agent_from_config
from app.tools.factory import load_tools_for_sub_agent
from app.core.state import AgentState
from app.prompts.sub_agent import SUB_TASK_INJECTION_TEMPLATE, FILE_LIST_TEMPLATE
from logger import logger

_sub_agent_service = SubAgentService()

def _inject_runtime_app_id(args: Any, app_id: str) -> Any:
    """将运行时 app_id 注入 tool args"""
    if not app_id:
        return args
    if isinstance(args, dict):
        data = args.get("data")
        if isinstance(data, dict):
            data["app_id"] = app_id
            args.pop("app_id", None)
            return args
        args["app_id"] = app_id
        return args
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                parsed.setdefault("app_id", app_id)
                data = parsed.get("data")
                if isinstance(data, dict):
                    data.setdefault("app_id", app_id)
                return parsed
        except Exception:
            pass
        return {"query": args, "app_id": app_id}
    return {"query": str(args), "app_id": app_id}

def _find_sub_agent_by_name(name: str) -> Optional[Dict[str, Any]]:
    if not name:
        return None
    try:
        all_agents = _sub_agent_service.get_all() or []
        for a in all_agents:
            if a.get("name") == name:
                return a
    except Exception as e:
        logger.warning(f"查找 sub_agent 失败 name={name}, err={e}")
    return None

async def run_agent(state: AgentState, config: RunnableConfig = None) -> Dict:
    current_agent = (state.get("current_agent") or "").strip()
    if not current_agent:
        nxt = (state.get("next") or "").strip()
        if nxt and nxt not in ("RUN_AGENT", "FINISH"):
            current_agent = nxt
    if not current_agent:
        return {"messages": [AIMessage(content="未指定 current_agent，无法执行子Agent。")], "current_agent": ""}

    sa = _find_sub_agent_by_name(current_agent)
    if not sa:
        return {"messages": [AIMessage(content=f"未找到子Agent配置: {current_agent}")], "current_agent": current_agent}

    sa_id = sa.get("_id")
    if not sa_id:
        return {"messages": [AIMessage(content=f"子Agent配置缺少 _id: {current_agent}")], "current_agent": current_agent}

    result = create_agent_from_config(sa_id)
    if not result:
        return {"messages": [AIMessage(content=f"子Agent创建失败: {current_agent}")], "current_agent": current_agent}

    agent, tools = result
    session_files = state.get("session_files") or []
    sub_task_instruction = (state.get("sub_task_instruction") or "").strip()

    # 只使用私有上下文，不使用全局 messages
    private_messages = list(state.get("agent_scratchpad") or [])
    if not private_messages:
        from langchain_core.messages import HumanMessage
        injected_parts = []
        if session_files and tools:
            file_list = "\n".join(
                f"- {f.get('file_name', 'unknown')} (ID: {f.get('file_id', 'unknown')})"
                for f in session_files
            )
            injected_parts.append(FILE_LIST_TEMPLATE.format(file_list=file_list))
        if sub_task_instruction:
            injected_parts.append(SUB_TASK_INJECTION_TEMPLATE.format(instruction=sub_task_instruction))

        if injected_parts:
            private_messages.append(SystemMessage(content="\n\n".join(injected_parts)))
        private_messages.append(HumanMessage(content=sub_task_instruction or "请完成当前任务"))

    response = await agent.ainvoke({"messages": private_messages}, config=config)

    def _dump_ai_message_raw(msg: AIMessage) -> str:
        data = {
            "type": "AIMessage",
            "name": getattr(msg, "name", ""),
            "content": getattr(msg, "content", ""),
            "tool_calls": getattr(msg, "tool_calls", None),
            "additional_kwargs": getattr(msg, "additional_kwargs", {}) or {},
            "response_metadata": getattr(msg, "response_metadata", {}) or {},
        }
        return json.dumps(data, ensure_ascii=False, default=str)

    if isinstance(response, AIMessage):
        logger.info("RAW_SUBAGENT_OUTPUT agent=%s payload=%s", current_agent, _dump_ai_message_raw(response))
    else:
        logger.info("RAW_SUBAGENT_OUTPUT agent=%s payload=%s", current_agent, str(response))

    if isinstance(response, AIMessage):
        tool_calls = getattr(response, "tool_calls", None)
        if tool_calls:
            response.name = current_agent
            new_pad = private_messages + [response]
            return {
                "messages": [response],              # 全局保留审计
                "agent_scratchpad": new_pad,         # 私有上下文继续
                "current_agent": current_agent,
            }

        raw_content = response.content if isinstance(response.content, str) else str(response.content or "")
        marker_msg = AIMessage(
            content="",
            name=current_agent,
            additional_kwargs={
                "_marker": "sub_agent_completed_no_summary",
                "_raw_content": raw_content,
                "_raw_response_metadata": getattr(response, "response_metadata", {}) or {},
            },
        )
        return {
            "messages": [marker_msg],
            "agent_scratchpad": [],                 # 子任务完成，清空私有上下文
            "current_agent": current_agent,
        }

    return {
        "messages": [response],
        "agent_scratchpad": [],
        "current_agent": current_agent,
    }


async def run_tools(state: AgentState, config: RunnableConfig) -> Dict:
    current_agent = (state.get("current_agent") or "").strip()
    scratchpad = list(state.get("agent_scratchpad") or [])
    if not scratchpad:
        return {"current_agent": current_agent, "agent_scratchpad": scratchpad}

    last = scratchpad[-1]
    tool_calls = getattr(last, "tool_calls", None) if isinstance(last, AIMessage) else None
    if not tool_calls:
        return {"current_agent": current_agent, "agent_scratchpad": scratchpad}

    runtime_app_id = (state.get("app_id") or "").strip()
    if runtime_app_id:
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            if "args" in tc:
                tc["args"] = _inject_runtime_app_id(tc.get("args"), runtime_app_id)
            elif "arguments" in tc:
                tc["arguments"] = _inject_runtime_app_id(tc.get("arguments"), runtime_app_id)

    sa = _find_sub_agent_by_name(current_agent) if current_agent else None
    sa_id = sa.get("_id") if sa else None
    if not sa_id:
        err_msgs = []
        for i, tc in enumerate(tool_calls):
            tcid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None) or f"toolcall_{i}"
            err_msgs.append(
                ToolMessage(
                    content=f"工具执行失败：未找到 current_agent='{current_agent}' 对应 sub_agent 配置",
                    tool_call_id=tcid,
                )
            )
        return {"messages": err_msgs, "current_agent": current_agent, "agent_scratchpad": scratchpad + err_msgs}

    tools = load_tools_for_sub_agent(sa_id) or []
    if not tools:
        err_msgs = []
        for i, tc in enumerate(tool_calls):
            tcid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None) or f"toolcall_{i}"
            err_msgs.append(
                ToolMessage(
                    content=f"工具执行失败：agent '{current_agent}' 当前无可用工具",
                    tool_call_id=tcid,
                )
            )
        return {"messages": err_msgs, "current_agent": current_agent, "agent_scratchpad": scratchpad + err_msgs}

    node = ToolNode(tools)
    result = await node.ainvoke({"messages": scratchpad}, config=config)

    out_messages = result.get("messages") if isinstance(result, dict) else (result or [])
    out_messages = out_messages or []
    logger.info(
        "RAW_TOOL_OUTPUT agent=%s payload=%s",
        current_agent,
        json.dumps({"messages": [str(m) for m in out_messages]}, ensure_ascii=False, default=str),
    )

    new_pad = scratchpad + out_messages
    ret: Dict[str, Any] = {
        "messages": out_messages,          # 全局审计
        "agent_scratchpad": new_pad,       # 私有上下文继续
        "current_agent": current_agent,
    }

    for msg in out_messages:
        if not isinstance(msg, ToolMessage):
            continue
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if not content.startswith("__HITL__"):
            continue
        try:
            payload = json.loads(content[len("__HITL__"):].strip() or "{}")
        except Exception:
            payload = {}

        ret["user_input_required"] = True
        ret["suspended_action"] = "hitl_user_input"
        ret["pending_context"] = {
            "interaction_id": payload.get("interaction_id", ""),
            "question": payload.get("question", ""),
            "input_type": payload.get("input_type", "text"),
            "timeout_seconds": int(payload.get("timeout_seconds", 300) or 300),
            "expected_input": payload.get("expected_input") or [],
            "expected_schema": payload.get("expected_schema") or {},
            "tool_call_id": getattr(msg, "tool_call_id", "") or "",
            "current_agent": current_agent,
            "scene_id": state.get("scene_id", ""),
            "selected_role_id": state.get("selected_role_id", ""),
        }
        break

    return ret