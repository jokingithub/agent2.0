# -*- coding: utf-8 -*-
from langgraph.graph import StateGraph, END
from app.core.state import AgentState
from app.agents.supervisor import supervisor_node
from app.agents.utils.agent_runner import run_agent, run_tools
from logger import logger
from dataBase.Service import SessionService


def route_from_supervisor(state: AgentState) -> str:
    nxt = (state.get("next") or "").strip()
    if nxt in ("RUN_AGENT", "FINISH"):
        return nxt
    if nxt:
        logger.warning(f"Supervisor next 非标准值 '{nxt}'，按 RUN_AGENT 兼容处理")
        return "RUN_AGENT"
    return "FINISH"


def route_after_agent(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "BACK_TO_SUPERVISOR"
    from langchain_core.messages import AIMessage
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "TOOL"
    return "BACK_TO_SUPERVISOR"


def route_after_tool_runner(state: AgentState) -> str:
    if state.get("user_input_required"):
        return "SUSPEND"
    return "CONTINUE"


def suspend_handler(state: AgentState):
    session_id = (state.get("session_id") or "").strip()
    app_id = (state.get("app_id") or "").strip()
    pending = state.get("pending_context") or {}
    if not session_id or not app_id or not pending:
        return {}

    try:
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
                "scene_id": pending.get("scene_id", "") or state.get("scene_id", ""),
                "selected_role_id": pending.get("selected_role_id", "") or state.get("selected_role_id", ""),
            }
        )
    except Exception as e:
        logger.error(f"SuspendHandler 写入挂起状态失败: {e}")

    return {}


def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("GenericAgentRunner", run_agent)
    workflow.add_node("GenericToolRunner", run_tools)
    workflow.add_node("SuspendHandler", suspend_handler)

    workflow.add_conditional_edges(
        "Supervisor",
        route_from_supervisor,
        {
            "RUN_AGENT": "GenericAgentRunner",
            "FINISH": END,
        },
    )

    workflow.add_conditional_edges(
        "GenericAgentRunner",
        route_after_agent,
        {
            "TOOL": "GenericToolRunner",
            "BACK_TO_SUPERVISOR": "Supervisor",
        },
    )

    workflow.add_conditional_edges(
        "GenericToolRunner",
        route_after_tool_runner,
        {
            "SUSPEND": "SuspendHandler",
            "CONTINUE": "GenericAgentRunner",
        }
    )

    workflow.add_edge("SuspendHandler", END)

    workflow.set_entry_point("Supervisor")
    compiled = workflow.compile()
    logger.info("graph: 编译完成（Supervisor循环模式）")
    return compiled
