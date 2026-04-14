# -*- coding: utf-8 -*-
"""LangGraph 图构建 — bind_tools 模式（无 FINISH 工具）

图结构：
  Supervisor ──┬── FINISH ──────────────────→ END
               ├── RUN_AGENT ──→ AgentRunner ──┬── TOOL → ToolRunner → AgentRunner
               │                               └── BACK → (结果注入) → Supervisor
               └── RUN_SUPERVISOR_TOOL ──→ SupervisorToolRunner ──┬── SUSPEND → SuspendHandler → END
                                                                  └── BACK → Supervisor
"""

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.graph import StateGraph, END
from app.core.state import AgentState
from app.agents.supervisor import supervisor_node
from app.agents.utils.agent_runner import run_agent, run_tools, run_supervisor_tools
from logger import logger
from dataBase.Service import SessionService


def route_from_supervisor(state: AgentState) -> str:
    nxt = (state.get("next") or "").strip()
    if nxt in ("RUN_AGENT", "RUN_SUPERVISOR_TOOL", "FINISH"):
        return nxt
    if nxt:
        logger.warning(f"Supervisor next 非标准值 '{nxt}'，兜底 FINISH")
    return "FINISH"


def route_after_agent(state: AgentState) -> str:
    """AgentRunner 后：有 tool_calls → TOOL，否则 → 回 Supervisor"""
    messages = state.get("messages", [])
    if not messages:
        return "BACK_TO_SUPERVISOR"
    last = messages[-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "TOOL"
    return "BACK_TO_SUPERVISOR"


def inject_sub_agent_result(state: AgentState) -> dict:
    """子Agent 完成后，将结果注入 supervisor_scratchpad 作为 ToolMessage。"""
    supervisor_pad = list(state.get("supervisor_scratchpad") or [])
    current_agent = (state.get("current_agent") or "").strip()

    from app.agents.utils.supervisor_utils import PREFIX_SUB_AGENT
    target_tool_name = f"{PREFIX_SUB_AGENT}{current_agent}"

    # 从 supervisor_scratchpad 末尾找到对应的 tool_call_id
    tool_call_id = ""
    for msg in reversed(supervisor_pad):
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                if tc_name == target_tool_name:
                    tool_call_id = tc.get("id", "") if isinstance(tc, dict) else getattr(tc, "id", "")
                    break
            if tool_call_id:
                break

    # 提取子Agent的结果
    messages = list(state.get("messages") or [])
    result_content = "(子Agent执行完成，无输出)"
    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            name = getattr(msg, "name", "") or ""
            if name == current_agent:
                marker = msg.additional_kwargs.get("_marker", "") if msg.additional_kwargs else ""
                if marker == "sub_agent_completed_no_summary":
                    raw = msg.additional_kwargs.get("_raw_content", "")
                    result_content = raw if raw else "(子Agent执行完成，无额外输出)"
                elif msg.content:
                    result_content = msg.content if isinstance(msg.content, str) else str(msg.content)
                break

    if not tool_call_id:
        logger.warning(f"inject_sub_agent_result: 未找到 tool_call_id for agent={current_agent}")
        tool_call_id = f"sub_agent_{current_agent}_result"

    tool_msg = ToolMessage(
        content=result_content,
        tool_call_id=tool_call_id,
        name=target_tool_name,
    )

    new_pad = supervisor_pad + [tool_msg]

    return {
        "supervisor_scratchpad": new_pad,
        "agent_scratchpad": [],
    }


def route_after_tool_runner(state: AgentState) -> str:
    if state.get("user_input_required"):
        return "SUSPEND"
    return "CONTINUE"


def route_after_supervisor_tool(state: AgentState) -> str:
    if state.get("user_input_required"):
        return "SUSPEND"
    return "BACK_TO_SUPERVISOR"


def _serialize_messages(msgs: list) -> list:
    """将 BaseMessage 列表序列化为可 JSON 存储的字典列表。"""
    from langchain_core.messages import messages_to_dict
    if not msgs:
        return []
    try:
        return messages_to_dict(msgs)
    except Exception as e:
        logger.warning(f"序列化消息失败: {e}")
        return []


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
                # ★ 保存完整的私有上下文和 Supervisor 上下文
                "agent_scratchpad": _serialize_messages(
                    list(state.get("agent_scratchpad") or [])
                ),
                "supervisor_scratchpad": _serialize_messages(
                    list(state.get("supervisor_scratchpad") or [])
                ),
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

    # ── 入口路由节点 ──
    def entry_router(state: AgentState):
        """入口路由：如果是 HITL 恢复且有 current_agent + agent_scratchpad，
        直接跳到 AgentRunner；否则走 Supervisor。"""
        nxt = (state.get("next") or "").strip()
        current_agent = (state.get("current_agent") or "").strip()
        agent_pad = state.get("agent_scratchpad") or []

        if nxt == "RUN_AGENT" and current_agent and agent_pad:
            # HITL 恢复场景：subagent 有保存的上下文，直接继续执行
            return "RUN_AGENT"
        # 其他情况都走 Supervisor
        return "SUPERVISOR"

    workflow.add_node("EntryRouter", lambda state: {})  # 空节点，仅做路由
    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("GenericAgentRunner", run_agent)
    workflow.add_node("GenericToolRunner", run_tools)
    workflow.add_node("SupervisorToolRunner", run_supervisor_tools)
    workflow.add_node("InjectSubAgentResult", inject_sub_agent_result)
    workflow.add_node("SuspendHandler", suspend_handler)

    # ── 入口 ──
    workflow.set_entry_point("EntryRouter")

    workflow.add_conditional_edges(
        "EntryRouter",
        entry_router,
        {
            "SUPERVISOR": "Supervisor",
            "RUN_AGENT": "GenericAgentRunner",
        },
    )

    # ── Supervisor 出口 ──
    workflow.add_conditional_edges(
        "Supervisor",
        route_from_supervisor,
        {
            "RUN_AGENT": "GenericAgentRunner",
            "RUN_SUPERVISOR_TOOL": "SupervisorToolRunner",
            "FINISH": END,
        },
    )

    # ── 子Agent 执行后 ──
    workflow.add_conditional_edges(
        "GenericAgentRunner",
        route_after_agent,
        {
            "TOOL": "GenericToolRunner",
            "BACK_TO_SUPERVISOR": "InjectSubAgentResult",
        },
    )

    # ── 子Agent 结果注入后 → 回 Supervisor ──
    workflow.add_edge("InjectSubAgentResult", "Supervisor")

    # ── 子Agent 的 ToolRunner ──
    workflow.add_conditional_edges(
        "GenericToolRunner",
        route_after_tool_runner,
        {
            "SUSPEND": "SuspendHandler",
            "CONTINUE": "GenericAgentRunner",
        }
    )

    # ── Supervisor 直接工具执行后 ──
    workflow.add_conditional_edges(
        "SupervisorToolRunner",
        route_after_supervisor_tool,
        {
            "SUSPEND": "SuspendHandler",
            "BACK_TO_SUPERVISOR": "Supervisor",
        }
    )

    # ── 挂起 → 结束 ──
    workflow.add_edge("SuspendHandler", END)

    compiled = workflow.compile()
    logger.info("graph: 编译完成（Supervisor bind_tools 模式，支持 HITL 上下文恢复）")
    return compiled