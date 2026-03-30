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


def _route_from_supervisor(state: AgentState) -> str:
    """
    兼容路由：
    - 标准: next=RUN_AGENT/FINISH
    - 兼容旧: next=某个agent名（如“可丽饼”）=> 当作 RUN_AGENT
    """
    nxt = (state.get("next") or "").strip()
    if nxt in ("RUN_AGENT", "FINISH"):
        return nxt
    if nxt:
        logger.warning(f"Supervisor next 非标准值 '{nxt}'，按 RUN_AGENT 兼容处理")
        return "RUN_AGENT"
    return "FINISH"


def create_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("Supervisor", supervisor_node)
    workflow.add_node("GenericAgentRunner", generic_agent_runner)
    workflow.add_node("GenericToolRunner", generic_tool_runner)

    workflow.add_conditional_edges(
        "Supervisor",
        _route_from_supervisor,
        {
            "RUN_AGENT": "GenericAgentRunner",
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

    workflow.add_edge("GenericToolRunner", "GenericAgentRunner")
    workflow.set_entry_point("Supervisor")
    compiled = workflow.compile()
    logger.info("graph: 编译完成（固定节点模式）")
    return compiled
