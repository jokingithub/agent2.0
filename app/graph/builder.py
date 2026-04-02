# -*- coding: utf-8 -*-
from langgraph.graph import StateGraph, END
from app.core.state import AgentState
from app.agents.supervisor import supervisor_node
from app.agents.generic_runner import (
    generic_agent_runner,
    generic_tool_runner,
    route_after_generic_agent,
)
from logger import logger
from dataBase.Service import SessionService


def _route_from_supervisor(state: AgentState) -> str:
    """
    兼容路由：
    - 标准: next=RUN_AGENT/FINISH
    - 兼容旧: next=某个agent名=> 当作 RUN_AGENT
    """
    next_action = (state.get("next_action") or "").strip().upper()
    if next_action == "ACT_TOOL":
        return "RUN_TOOL"
    if next_action == "DELEGATE_SUBAGENT":
        return "RUN_AGENT"
    if next_action == "FINISH":
        return "FINISH"

    nxt = (state.get("next") or "").strip()
    if nxt in ("RUN_AGENT", "RUN_TOOL", "FINISH"):
        return nxt
    if nxt:
        logger.warning(f"Supervisor next 非标准值 '{nxt}'，按 RUN_AGENT 兼容处理")
        return "RUN_AGENT"
    return "FINISH"


def _route_after_tool_runner(state: AgentState) -> str:
    """ToolRunner 后路由：HITL 挂起 or 继续 agent。"""
    if state.get("user_input_required"):
        return "SUSPEND"
    current_actor = (state.get("current_actor") or "").strip()
    if current_actor == "supervisor":
        return "BACK_TO_SUPERVISOR"
    return "CONTINUE_SUBAGENT"


def _suspend_handler(state: AgentState):
    """将 HITL 挂起信息写入 session，结束当前轮图执行。"""
    session_id = (state.get("session_id") or "").strip()
    app_id = (state.get("app_id") or "").strip()
    pending = state.get("pending_context") or {}
    if not session_id or not app_id or not pending:
        return {}

    try:
        trace_data = state.get("trace") if isinstance(state.get("trace"), list) else []
        if len(trace_data) > 20:
            trace_data = trace_data[-20:]

        svc = SessionService()
        svc.suspend_session(
            session_id=session_id,
            app_id=app_id,
            interaction_id=pending.get("interaction_id", ""),
            question=pending.get("question", ""),
            input_type=pending.get("input_type", "text"),
            expected_input=pending.get("expected_input") or [],
            expected_schema=pending.get("expected_schema") or {},
            timeout_seconds=int(pending.get("timeout_seconds", 300) or 300),
            context={
                "session_files": state.get("session_files") or [],
                "messages": [],
                "tool_call_id": pending.get("tool_call_id", ""),
                "current_agent": pending.get("current_agent", "") or state.get("current_agent", ""),
                "current_actor": pending.get("current_actor", "") or state.get("current_actor", ""),
                "next": state.get("next", ""),
                "react_step": state.get("react_step", 0),
                "max_steps": state.get("max_steps", 12),
                "scene_id": pending.get("scene_id", "") or state.get("scene_id", ""),
                "selected_role_id": pending.get("selected_role_id", "") or state.get("selected_role_id", ""),
                "last_action": state.get("last_action") if isinstance(state.get("last_action"), dict) else None,
                "last_observation": state.get("last_observation") if isinstance(state.get("last_observation"), dict) else None,
                "trace": trace_data,
            },
        )
    except Exception as e:
        logger.error(f"SuspendHandler 写入挂起状态失败: {e}")

    return {}


def create_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("GenericAgentRunner", generic_agent_runner)
    workflow.add_node("GenericToolRunner", generic_tool_runner)
    workflow.add_node("SuspendHandler", _suspend_handler)

    workflow.add_conditional_edges(
        "Supervisor",
        _route_from_supervisor,
        {
            "RUN_AGENT": "GenericAgentRunner",
            "RUN_TOOL": "GenericToolRunner",
            "FINISH": END,
        },
    )

    workflow.add_conditional_edges(
        "GenericAgentRunner",
        route_after_generic_agent,
        {
            "TOOL": "GenericToolRunner",
            "DONE": END,
        },
    )

    workflow.add_conditional_edges(
        "GenericToolRunner",
        _route_after_tool_runner,
        {
            "SUSPEND": "SuspendHandler",
            "CONTINUE_SUBAGENT": "GenericAgentRunner",
            "BACK_TO_SUPERVISOR": "Supervisor",
        },
    )
    workflow.add_edge("SuspendHandler", END)
    workflow.set_entry_point("Supervisor")
    compiled = workflow.compile()
    logger.info("graph: 编译完成（固定节点模式）")
    return compiled
