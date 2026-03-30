# -*- coding: utf-8 -*-
"""统一 Generic Runner（无须为每个 sub_agent 注册图节点）"""

from typing import Optional, Dict, Any, List
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.prebuilt import ToolNode

from dataBase.ConfigService import SubAgentService
from app.agents.generic import create_agent_from_config
from app.tools.factory import load_tools_for_sub_agent
from app.core.state import AgentState
from logger import logger

_sub_agent_service = SubAgentService()


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


def route_after_generic_agent(state: AgentState) -> str:
    """GenericAgentRunner 后路由：有 tool_calls -> TOOL，否则 DONE"""
    messages = state.get("messages", [])
    if not messages:
        return "DONE"

    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "TOOL"
    return "DONE"


def generic_agent_runner(state: AgentState):
    current_agent = (state.get("current_agent") or "").strip()
    if not current_agent:
        nxt = (state.get("next") or "").strip()
        if nxt and nxt not in ("RUN_AGENT", "FINISH"):
            current_agent = nxt
    if not current_agent:
        return {
            "messages": [AIMessage(content="未指定 current_agent，无法执行子Agent。")],
            "current_agent": "",
        }

    sa = _find_sub_agent_by_name(current_agent)
    if not sa:
        return {
            "messages": [AIMessage(content=f"未找到子Agent配置: {current_agent}")],
            "current_agent": current_agent,
        }

    sa_id = sa.get("_id")
    if not sa_id:
        return {
            "messages": [AIMessage(content=f"子Agent配置缺少 _id: {current_agent}")],
            "current_agent": current_agent,
        }

    result = create_agent_from_config(sa_id)
    if not result:
        return {
            "messages": [AIMessage(content=f"子Agent创建失败: {current_agent}")],
            "current_agent": current_agent,
        }

    agent, tools = result
    session_files = state.get("session_files") or []
    messages = list(state.get("messages", []))
    if session_files and tools:
        file_list = "\n".join(
            [f"- {f.get('file_name', 'unknown')} (ID: {f.get('file_id', 'unknown')})" for f in session_files]
        )
        messages.insert(0, SystemMessage(content=f"当前会话关联的文件:\n{file_list}"))

    response = agent.invoke({"messages": messages})
    return {"messages": [response], "current_agent": current_agent}


async def generic_tool_runner(state: AgentState, config: RunnableConfig):
    messages = state.get("messages", [])
    if not messages:
        return {"current_agent": state.get("current_agent", "")}

    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", None) if isinstance(last, AIMessage) else None
    if not tool_calls:
        return {"current_agent": state.get("current_agent", "")}

    current_agent = (state.get("current_agent") or "").strip()
    sa = _find_sub_agent_by_name(current_agent) if current_agent else None
    sa_id = sa.get("_id") if sa else None

    if not sa_id:
        err_msgs: List[ToolMessage] = []
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
        err_msgs: List[ToolMessage] = []
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
    if isinstance(result, dict):
        result["current_agent"] = current_agent
        return result
    return {"messages": result, "current_agent": current_agent}
