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
    messages = list(state.get("messages", []))

    injected_system_parts = []
    if session_files and tools:
        file_list = "\n".join(
            f"- {f.get('file_name', 'unknown')} (ID: {f.get('file_id', 'unknown')})"
            for f in session_files
        )
        injected_system_parts.append(FILE_LIST_TEMPLATE.format(file_list=file_list))
    if sub_task_instruction:
        injected_system_parts.append(SUB_TASK_INJECTION_TEMPLATE.format(instruction=sub_task_instruction))
    if injected_system_parts:
        combined = "\n\n".join(injected_system_parts)
        messages.insert(0, SystemMessage(content=combined))

    response = await agent.ainvoke({"messages": messages}, config=config)

    if isinstance(response, AIMessage):
        tool_calls = getattr(response, "tool_calls", None)
        if tool_calls:
            response.name = current_agent
            return {"messages": [response], "current_agent": current_agent}
        # 无工具调用的总结，返回特殊标记
        if response.content:
            marker_msg = AIMessage(
                content="",
                name=current_agent,
                additional_kwargs={"_marker": "sub_agent_completed_no_summary"}
            )
            return {"messages": [marker_msg], "current_agent": current_agent}

    if isinstance(response, AIMessage) and not response.name:
        response.name = current_agent
    return {"messages": [response], "current_agent": current_agent}


async def run_tools(state: AgentState, config: RunnableConfig) -> Dict:
    messages = state.get("messages", [])
    if not messages:
        return {"current_agent": state.get("current_agent", "")}

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) if isinstance(last, AIMessage) else None
    if not tool_calls:
        return {"current_agent": state.get("current_agent", "")}

    runtime_app_id = (state.get("app_id") or "").strip()
    if runtime_app_id:
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            if "args" in tc:
                tc["args"] = _inject_runtime_app_id(tc.get("args"), runtime_app_id)
            elif "arguments" in tc:
                tc["arguments"] = _inject_runtime_app_id(tc.get("arguments"), runtime_app_id)

    current_agent = (state.get("current_agent") or "").strip()
    sa = _find_sub_agent_by_name(current_agent) if current_agent else None
    sa_id = sa.get("_id") if sa else None
    if not sa_id:
        err_msgs = []
        for i, tc in enumerate(tool_calls):
            tcid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
            if not tcid:
                tcid = f"toolcall_{i}"
            err_msgs.append(
                ToolMessage(
                    content=f"工具执行失败：未找到 current_agent='{current_agent}' 对应 sub_agent 配置",
                    tool_call_id=tcid,
                )
            )
        return {"messages": err_msgs, "current_agent": current_agent}

    tools = load_tools_for_sub_agent(sa_id) or []
    if not tools:
        err_msgs = []
        for i, tc in enumerate(tool_calls):
            tcid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
            if not tcid:
                tcid = f"toolcall_{i}"
            err_msgs.append(
                ToolMessage(
                    content=f"工具执行失败：agent '{current_agent}' 当前无可用工具",
                    tool_call_id=tcid,
                )
            )
        return {"messages": err_msgs, "current_agent": current_agent}

    node = ToolNode(tools)
    result = await node.ainvoke(state, config=config)

    # HITL 处理
    if isinstance(result, dict):
        out_messages = result.get("messages") or []
        for msg in out_messages:
            if not isinstance(msg, ToolMessage):
                continue
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if not content.startswith("__HITL__"):
                continue

            try:
                payload_str = content[len("__HITL__"):].strip()
                payload = json.loads(payload_str) if payload_str else {}
            except Exception:
                payload = {}

            result["user_input_required"] = True
            result["suspended_action"] = "hitl_user_input"
            result["pending_context"] = {
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

    if isinstance(result, dict):
        result["current_agent"] = current_agent
        return result
    return {"messages": result, "current_agent": current_agent}
