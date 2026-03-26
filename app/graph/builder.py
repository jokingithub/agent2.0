# -*- coding: utf-8 -*-
# 文件：app/graph/builder.py

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage
from pathlib import Path

from app.core.state import AgentState
from app.core.agents_config import AGENT_REGISTRY
from app.agents.quotation import quotation_node
from app.agents.supervisor import supervisor_node
from app.agents.reviewer import reviewer_node
from app.agents.generic import generic_agent_node
from app.tools.factory import load_skill_as_tool
from dataBase.ConfigService import SubAgentService
from logger import logger

_ROOT = Path(__file__).resolve().parents[2]
_CALCULATE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "calculate_skill"))
_READ_FILE_TOOL = load_skill_as_tool(str(_ROOT / "app" / "skills" / "readFile_skill"))

# 硬编码节点映射（兜底）
_HARDCODED_NODES = {
    "quotation": quotation_node,
    "reviewer": reviewer_node,
}


def route_after_quotation(state: AgentState) -> str:
    """报价节点后路由：有 tool_calls 则执行工具，否则结束。"""
    messages = state.get("messages", [])
    if not messages:
        return "done"

    last_message = messages[-1]
    if isinstance(last_message, AIMessage) and getattr(last_message, "tool_calls", None):
        return "tool"
    return "done"


def create_graph():
    workflow = StateGraph(AgentState)

    # ============================================================
    # 1. 固定节点
    # ============================================================
    workflow.add_node("Supervisor", supervisor_node)

    # ============================================================
    # 2. 从 sub_agents 表动态注册节点
    # ============================================================
    registered_names = set()

    try:
        all_sub_agents = SubAgentService().get_all()
        if all_sub_agents:
            for sa in all_sub_agents:
                name = sa.get("name", "")
                agent_id = sa.get("_id", "")
                if not name or not agent_id:
                    continue

                # 如果有同名硬编码节点，优先用硬编码（保留工具调用等特殊逻辑）
                if name in _HARDCODED_NODES:
                    logger.info(f"graph: '{name}' 使用硬编码节点（保留特殊逻辑）")
                    workflow.add_node(name, _HARDCODED_NODES[name])
                else:
                    logger.info(f"graph: '{name}' 使用配置驱动节点 (id={agent_id})")
                    workflow.add_node(name, generic_agent_node(agent_id))

                registered_names.add(name)

            logger.info(f"graph: 从配置表注册了 {len(registered_names)} 个 sub_agent 节点: {registered_names}")
    except Exception as e:
        logger.warning(f"graph: 从配置表加载 sub_agents 失败: {e}，使用硬编码兜底")

    # ============================================================
    # 3. 硬编码兜底：配置表里没有的，补上
    # ============================================================
    for name, node_fn in _HARDCODED_NODES.items():
        if name not in registered_names:
            logger.info(f"graph: '{name}' 兜底注册（配置表中不存在）")
            workflow.add_node(name, node_fn)
            registered_names.add(name)

    # 同时把 AGENT_REGISTRY 里的也兜底（以防有额外的）
    for name in AGENT_REGISTRY:
        if name not in registered_names:
            logger.info(f"graph: '{name}' 从 AGENT_REGISTRY 兜底注册")
            # 没有硬编码实现，也没有配置，跳过（不注册空节点）
            # 如果需要可以用 generic_agent_node，但没有 id 无法创建
            pass

    # ============================================================
    # 4. 工具节点（保持现有）
    # ============================================================
    workflow.add_node("call_calculate_tool", ToolNode([_READ_FILE_TOOL, _CALCULATE_TOOL]))
    workflow.add_node("call_read_file_tool", ToolNode([_READ_FILE_TOOL]))

    # ============================================================
    # 5. 条件路由
    # ============================================================

    # Supervisor → 任意已注册节点 或 FINISH
    supervisor_routes = {name: name for name in registered_names}
    supervisor_routes["FINISH"] = END
    workflow.add_conditional_edges("Supervisor", lambda x: x["next"], supervisor_routes)

    # ============================================================
    # 6. 各 sub_agent 的出边
    # ============================================================

    # quotation: 有工具调用逻辑
    if "quotation" in registered_names:
        workflow.add_conditional_edges(
            "quotation",
            route_after_quotation,
            {
                "tool": "call_calculate_tool",
                "done": END,
            },
        )
        workflow.add_edge("call_calculate_tool", "quotation")

    # reviewer: 有工具调用逻辑
    if "reviewer" in registered_names:
        workflow.add_conditional_edges(
            "reviewer",
            route_after_quotation,
            {
                "tool": "call_read_file_tool",
                "done": END,
            },
        )
        workflow.add_edge("call_read_file_tool", "reviewer")

    # 其他配置驱动的节点：执行完直接 END
    for name in registered_names:
        if name not in ("quotation", "reviewer"):
            workflow.add_edge(name, END)

    # ============================================================
    # 7. 入口
    # ============================================================
    workflow.set_entry_point("Supervisor")

    compiled = workflow.compile()
    logger.info(f"graph: 编译完成，节点={list(registered_names | {'Supervisor'})}")
    return compiled
